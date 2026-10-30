import base64
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone as dt_timezone
from email.utils import formatdate
from urllib.parse import quote

import requests as http_requests
from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from eventwall.mixins import EventWallModelViewSetMixin
from eventwall.models import EventRecord
from eventwall.services import record_event
from .models import LogDataSource
from .serializers import LogDataSourceSerializer
from rbac.permissions import RBACPermissionMixin, build_rbac_permission


REQUEST_TIMEOUT = 30
DEMO_LOG_BATCHES = 48
SENSITIVE_KEYS = {
    'password',
    'api_key',
    'token',
    'bearer_token',
    'access_key_id',
    'access_key_secret',
}
TRACE_ID_KEYS = ('trace_id', 'traceId', 'traceID', 'trace.id', 'trace.trace_id', 'otelTraceID')
TRACE_ID_PATTERN = re.compile(r'(?:"?(?:trace_id|traceId|traceID|trace\.id)"?\s*[:=]\s*"?(?P<trace>[0-9a-fA-F]{16,32})"?)')


def _extract_trace_id(attributes, message=''):
    if isinstance(attributes, dict):
        for key in TRACE_ID_KEYS:
            value = attributes.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for key, value in attributes.items():
            if str(key).lower().replace('.', '_') in {'trace_id', 'traceid'} and isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(message, str) and message.strip():
        try:
            parsed = json.loads(message)
            if isinstance(parsed, dict):
                nested = _extract_trace_id(parsed, '')
                if nested:
                    return nested
        except ValueError:
            pass
        match = TRACE_ID_PATTERN.search(message)
        if match:
            return match.group('trace')
    return ''


def _with_trace_id(attributes, message=''):
    enriched = dict(attributes or {})
    trace_id = _extract_trace_id(enriched, message)
    if trace_id and not enriched.get('trace_id'):
        enriched['trace_id'] = trace_id
    return enriched


class ProviderError(Exception):
    def __init__(self, message, status_code=status.HTTP_400_BAD_REQUEST, detail=None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or {}


def _provider_defaults():
    configured = getattr(settings, 'LOG_PROVIDER_CONFIGS', None)
    if configured:
        return configured
    return {
        'loki': {
            'endpoint': getattr(settings, 'LOKI_URL', 'http://localhost:3100'),
        },
        'elk': {
            'endpoint': '',
            'auth_type': 'none',
            'index_pattern': 'logs-*',
            'time_field': '@timestamp',
            'message_fields': 'message,log,msg',
        },
        'sls': {
            'endpoint': '',
            'project': '',
            'logstore': '',
            'topic': '',
        },
    }


def _is_demo_config(config):
    return bool((config or {}).get('demo_mode'))


def _public_config(config):
    result = {}
    for key, value in (config or {}).items():
        if key in SENSITIVE_KEYS and not _is_demo_config(config):
            result[key] = 'configured' if value else ''
        else:
            result[key] = value
    return result


def _merge_config(provider, incoming=None):
    defaults = _provider_defaults().get(provider, {})
    merged = dict(defaults)
    for key, value in (incoming or {}).items():
        if value is not None and value != '':
            merged[key] = value
    return merged


def _resolve_provider_and_config(payload):
    datasource = None
    datasource_id = payload.get('datasource_id')

    if datasource_id:
        try:
            datasource = LogDataSource.objects.get(pk=datasource_id)
        except LogDataSource.DoesNotExist as exc:
            raise ProviderError('日志数据源不存在', status.HTTP_404_NOT_FOUND) from exc
        if not datasource.is_enabled:
            raise ProviderError('日志数据源已停用', status.HTTP_400_BAD_REQUEST)

    provider = payload.get('provider') or getattr(datasource, 'provider', None)
    if not provider:
        raise ProviderError('provider is required')
    if datasource and provider != datasource.provider:
        raise ProviderError('provider 与数据源类型不一致')

    config = _merge_config(provider, getattr(datasource, 'config', None))
    config = _merge_config(provider, {**config, **(payload.get('config') or {})})
    return provider, config, datasource


def _provider_info():
    defaults = _provider_defaults()
    return [
        {
            'id': 'loki',
            'name': 'Loki',
            'description': '基于标签的日志检索与 LogQL 查询。',
            'configured': bool(defaults.get('loki', {}).get('endpoint')),
            'defaults': _public_config(defaults.get('loki', {})),
        },
        {
            'id': 'elk',
            'name': 'ELK / Elasticsearch',
            'description': '使用 Lucene 语法检索 Elasticsearch 日志。',
            'configured': bool(defaults.get('elk', {}).get('endpoint')),
            'defaults': _public_config(defaults.get('elk', {})),
        },
        {
            'id': 'sls',
            'name': '阿里云 SLS',
            'description': '查询阿里云日志服务中的 Logstore。',
            'configured': bool(defaults.get('sls', {}).get('endpoint') and defaults.get('sls', {}).get('project')),
            'defaults': _public_config(defaults.get('sls', {})),
        },
    ]


def _safe_json(response):
    try:
        return response.json()
    except ValueError:
        return {'raw': response.text}


def _friendly_provider_error(provider, message):
    text = str(message or '')
    if provider == 'Loki' and 'empty-compatible value' in text:
        return 'Loki 查询条件无效：标签选择器必须至少包含一个非空匹配条件，例如 app=~".+"，不能只使用 app=~".*" 或 job!="" 这类可能匹配空值的条件。'
    return text


def _raise_for_status(response, provider):
    if response.ok:
        return
    payload = _safe_json(response)
    message = payload.get('error') or payload.get('message') or f'{provider} request failed'
    message = _friendly_provider_error(provider, message)
    raise ProviderError(message, status_code=response.status_code, detail=payload)


def _pick_message(source, fields):
    for field in fields:
        value = _get_nested(source, field)
        if value not in (None, ''):
            if isinstance(value, str):
                return value
            return json.dumps(value, ensure_ascii=False)
    return json.dumps(source, ensure_ascii=False)


def _get_nested(data, path):
    current = data
    for part in path.split('.'):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _split_fields(value, fallback):
    if isinstance(value, list):
        return [item for item in value if item]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(',') if item.strip()]
    return fallback


def _normalize_level(value):
    if value in (None, ''):
        return ''
    normalized = str(value).strip().lower()
    normalized = re.sub(r'[^a-z0-9_\u4e00-\u9fff-]+', '', normalized)
    if normalized in {'error', 'err', 'fatal', 'critical', 'crit', 'severe', '严重', '错误', '异常'}:
        return 'error'
    if normalized in {'warning', 'warn', 'warningwarn', '警告', '告警'}:
        return 'warning'
    if normalized in {'info', 'information', 'notice', '信息'}:
        return 'info'
    if normalized in {'debug', 'dbg', 'trace', 'verbose', '调试'}:
        return 'debug'
    if normalized.startswith(('err', 'fatal', 'crit', 'severe')):
        return 'error'
    if normalized.startswith('warn'):
        return 'warning'
    if normalized.startswith('info'):
        return 'info'
    if normalized.startswith(('debug', 'dbg')):
        return 'debug'
    return ''


def _detect_level(message, attributes=None):
    attributes = attributes or {}
    explicit_keys = (
        'detected_level',
        'detectedLevel',
        'level',
        'severity',
        'log.level',
        'severity_text',
        'severityText',
        'severityLabel',
        'priority',
    )
    for key in explicit_keys:
        raw_level = attributes.get(key)
        if raw_level in (None, '') and '.' in key:
            raw_level = _get_nested(attributes, key)
        level = _normalize_level(raw_level)
        if level:
            return level

    text = str(message or '')
    if text.strip().startswith(('{', '[')):
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            for key in explicit_keys:
                raw_level = parsed.get(key)
                if raw_level in (None, '') and '.' in key:
                    raw_level = _get_nested(parsed, key)
                level = _normalize_level(raw_level)
                if level:
                    return level

    explicit_match = re.search(
        r'(?<![A-Za-z0-9_])["\']?(?:detected_level|detectedLevel|level|severity|log\.level)["\']?\s*[:=]\s*["\']?'
        r'(error|err|fatal|critical|crit|warn|warning|info|information|debug|trace)["\']?',
        text,
        flags=re.IGNORECASE,
    )
    if explicit_match:
        return _normalize_level(explicit_match.group(1))

    token_match = re.search(
        r'(?<![A-Za-z0-9_])(error|err|fatal|critical|crit|warn|warning|info|information|debug)\b',
        text,
        flags=re.IGNORECASE,
    )
    if token_match:
        return _normalize_level(token_match.group(1))

    lower = text.lower()
    if any(token in lower for token in ('fatal', 'panic', 'exception', 'traceback')):
        return 'error'
    if re.search(r'(?<![a-z0-9_])error(?![a-z0-9_])', lower):
        return 'error'
    if re.search(r'(?<![a-z0-9_])warn(?:ing)?(?![a-z0-9_])', lower):
        return 'warning'
    if re.search(r'(?<![a-z0-9_])debug(?![a-z0-9_])', lower):
        return 'debug'
    return 'unknown'


def _normalize_ms(value, default):
    if value in (None, ''):
        return default
    value = int(value)
    if value > 1_000_000_000_000:
        return value
    return value * 1000


def _time_bounds(payload):
    now_ms = int(datetime.now(dt_timezone.utc).timestamp() * 1000)
    default_start = now_ms - 3600 * 1000
    start_ms = _normalize_ms(payload.get('start_ms'), default_start)
    end_ms = _normalize_ms(payload.get('end_ms'), now_ms)
    if start_ms > end_ms:
        start_ms, end_ms = end_ms, start_ms
    return start_ms, end_ms


def _iso_from_ms(value):
    if value in (None, ''):
        return ''
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ''
        try:
            value = int(float(stripped))
        except ValueError:
            normalized = stripped.replace('Z', '+00:00')
            try:
                dt = datetime.fromisoformat(normalized)
            except ValueError:
                return stripped
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=dt_timezone.utc)
            return dt.astimezone(dt_timezone.utc).isoformat().replace('+00:00', 'Z')
    else:
        value = int(float(value))

    if value > 1_000_000_000_000:
        dt = datetime.fromtimestamp(value / 1000, tz=dt_timezone.utc)
    else:
        dt = datetime.fromtimestamp(value, tz=dt_timezone.utc)
    return dt.isoformat().replace('+00:00', 'Z')


def _iso_from_ns(value):
    return _iso_from_ms(int(value) / 1_000_000)


def _sanitize_limit(value, default=200, maximum=2000):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


def _normalize_endpoint(endpoint):
    if not endpoint:
        return ''
    endpoint = endpoint.strip()
    if endpoint.startswith('http://') or endpoint.startswith('https://'):
        return endpoint.rstrip('/')
    return f'http://{endpoint.rstrip("/")}'


def _extract_query_terms(query):
    if not query or query == '*':
        return []
    normalized = re.sub(r'[":=(){}\[\],]', ' ', str(query))
    tokens = [token for token in re.split(r'\s+', normalized) if token]
    ignored = {
        'and', 'or', 'not', 'service', 'name', 'level', 'message', 'log', 'host',
        'source', 'severity', 'status', 'app', 'env', 'query', 'topic',
    }
    return [token.lower() for token in tokens if token.lower() not in ignored and len(token) > 1]


def _matches_demo_query(message, attributes, query):
    text = str(query or '').strip()
    field_clauses = re.findall(r'(?P<field>[A-Za-z_][A-Za-z0-9_.-]*):(?:"(?P<quoted>[^"]+)"|(?P<bare>[^\s()]+))', text)
    field_values = {}
    for field, quoted, bare in field_clauses:
        value = (quoted or bare or '').strip().lower()
        if value:
            field_values.setdefault(field, []).append(value)

    def get_field_value(field):
        aliases = {
            'service.name': ('service.name', 'service', 'service_name'),
            'host.name': ('host.name', 'host', 'host_name'),
            'trace.id': ('trace.id', 'trace_id', 'traceId', 'traceID'),
            'level': ('level', 'log.level', 'severity'),
        }
        for key in aliases.get(field, (field,)):
            value = _get_nested(attributes or {}, key) if '.' in key else (attributes or {}).get(key)
            if value not in (None, ''):
                if isinstance(value, dict) and 'name' in value:
                    value = value['name']
                return str(value).lower()
        return ''

    for field, expected_values in field_values.items():
        actual = get_field_value(field)
        if not actual or not any(expected in actual for expected in expected_values):
            return False

    haystack = ' '.join([str(message), json.dumps(attributes or {}, ensure_ascii=False)]).lower()
    generic_query = re.sub(r'(?P<field>[A-Za-z_][A-Za-z0-9_.-]*):(?:"[^"]+"|[^\s()]+)', ' ', text)
    generic_query = re.sub(r'\b[A-Za-z_][A-Za-z0-9_.-]*:\s*(?=\()', ' ', generic_query)
    groups = [group for group in re.split(r'\bAND\b', generic_query, flags=re.IGNORECASE) if group.strip()]
    for group in groups:
        terms = _extract_query_terms(group)
        if not terms:
            continue
        if re.search(r'\bOR\b', group, flags=re.IGNORECASE):
            if not any(term in haystack for term in terms):
                return False
        elif not all(term in haystack for term in terms):
            return False
    return True


def _demo_time_points(start_ms, end_ms, count):
    span = max(end_ms - start_ms, 1)
    step = max(int(span / max(count, 1)), 60_000)
    return [start_ms + step * index for index in range(count)]


def _demo_loki_entries(start_ms, end_ms):
    base_entries = [
        {
            'stream': {
                'job': 'gateway-service',
                'app': 'gateway-service',
                'namespace': 'prod',
                'cluster': 'cn-sh-prod',
                'region': 'cn-shanghai',
                'profile': 'prod',
                'container': 'gateway',
                'level': 'info',
                'service_name': 'gateway-service',
            },
            'thread': 'reactor-http-nio-4',
            'logger': 'com.sxdevops.gateway.filter.AccessLogFilter',
            'message': 'route matched, routeId=order-service, path=/api/orders/submit, cost=18ms',
        },
        {
            'stream': {
                'job': 'gateway-service',
                'app': 'gateway-service',
                'namespace': 'prod',
                'cluster': 'cn-sh-prod',
                'region': 'cn-shanghai',
                'profile': 'prod',
                'container': 'gateway',
                'level': 'error',
                'service_name': 'gateway-service',
            },
            'thread': 'reactor-http-nio-7',
            'logger': 'com.sxdevops.gateway.filter.ExceptionLogFilter',
            'message': 'forward request failed, uri=lb://order-service, reason=ReadTimeoutException: downstream timeout',
        },
        {
            'stream': {
                'job': 'gateway-service',
                'app': 'gateway-service',
                'namespace': 'prod',
                'cluster': 'cn-sh-prod',
                'region': 'cn-shanghai',
                'profile': 'prod',
                'container': 'gateway',
                'level': 'info',
                'service_name': 'gateway-service',
            },
            'thread': 'reactor-http-nio-3',
            'logger': 'com.sxdevops.gateway.filter.GrayReleaseRouteFilter',
            'message': 'gray release route hit, routeId=payment-service-gray, tenantId=t-ob, version=gray, header[X-Gray]=true',
        },
        {
            'stream': {
                'job': 'order-service',
                'app': 'order-service',
                'namespace': 'prod',
                'cluster': 'cn-sh-prod',
                'region': 'cn-shanghai',
                'profile': 'prod',
                'container': 'order',
                'level': 'info',
                'service_name': 'order-service',
            },
            'thread': 'http-nio-8082-exec-3',
            'logger': 'com.sxdevops.order.controller.OrderController',
            'message': 'create order success, orderNo=SO202603150001, userId=10086, amount=299.00',
        },
        {
            'stream': {
                'job': 'order-service',
                'app': 'order-service',
                'namespace': 'prod',
                'cluster': 'cn-sh-prod',
                'region': 'cn-shanghai',
                'profile': 'prod',
                'container': 'order',
                'level': 'error',
                'service_name': 'order-service',
            },
            'thread': 'http-nio-8082-exec-7',
            'logger': 'com.sxdevops.order.service.PaymentRemoteService',
            'message': 'feign invoke payment-service failed, status=500, retry=2, msg=payment status update timeout',
        },
        {
            'stream': {
                'job': 'order-service',
                'app': 'order-service',
                'namespace': 'prod',
                'cluster': 'cn-sh-prod',
                'region': 'cn-shanghai',
                'profile': 'prod',
                'container': 'order',
                'level': 'error',
                'service_name': 'order-service',
            },
            'thread': 'http-nio-8082-exec-11',
            'logger': 'com.sxdevops.order.service.impl.OrderSubmitServiceImpl',
            'message': (
                'submit order failed, orderNo=SO202603150009, tenantId=t-vip, ex=java.lang.IllegalStateException: stock lock failed\n'
                'java.lang.IllegalStateException: stock lock failed\n'
                '\tat com.sxdevops.order.service.impl.OrderSubmitServiceImpl.lockStock(OrderSubmitServiceImpl.java:214)\n'
                '\tat com.sxdevops.order.service.impl.OrderSubmitServiceImpl.submit(OrderSubmitServiceImpl.java:126)\n'
                '\tat com.sxdevops.order.controller.OrderController.submit(OrderController.java:58)\n'
                '\tat org.springframework.aop.framework.ReflectiveMethodInvocation.proceed(ReflectiveMethodInvocation.java:186)'
            ),
        },
        {
            'stream': {
                'job': 'payment-service',
                'app': 'payment-service',
                'namespace': 'prod',
                'cluster': 'cn-sh-prod',
                'region': 'cn-shanghai',
                'profile': 'prod',
                'container': 'payment',
                'level': 'info',
                'service_name': 'payment-service',
            },
            'thread': 'http-nio-8091-exec-5',
            'logger': 'com.sxdevops.payment.service.CallbackService',
            'message': 'payment callback processed successfully, channel=alipay, tradeStatus=SUCCESS',
        },
        {
            'stream': {
                'job': 'payment-service',
                'app': 'payment-service',
                'namespace': 'prod',
                'cluster': 'cn-sh-prod',
                'region': 'cn-shanghai',
                'profile': 'prod',
                'container': 'payment',
                'level': 'error',
                'service_name': 'payment-service',
            },
            'thread': 'http-nio-8091-exec-8',
            'logger': 'com.sxdevops.payment.service.SignVerifyService',
            'message': 'signature verify failed, orderNo=SO202603150001, channel=wechat, errorCode=SIGN_MISMATCH',
        },
        {
            'stream': {
                'job': 'payment-service',
                'app': 'payment-service',
                'namespace': 'prod',
                'cluster': 'cn-sh-prod',
                'region': 'cn-shanghai',
                'profile': 'prod',
                'container': 'payment',
                'level': 'error',
                'service_name': 'payment-service',
            },
            'thread': 'http-nio-8091-exec-12',
            'logger': 'com.sxdevops.payment.controller.PaymentCallbackController',
            'message': (
                'payment callback processing exception, requestId=cb-20260315-991, tenantId=t-ob, ex=java.lang.NullPointerException: callback payload is null\n'
                'java.lang.NullPointerException: callback payload is null\n'
                '\tat com.sxdevops.payment.controller.PaymentCallbackController.handle(PaymentCallbackController.java:87)\n'
                '\tat com.sxdevops.payment.controller.PaymentCallbackController.callback(PaymentCallbackController.java:52)\n'
                '\tat java.base/jdk.internal.reflect.DirectMethodHandleAccessor.invoke(DirectMethodHandleAccessor.java:104)\n'
                '\tat org.springframework.web.method.support.InvocableHandlerMethod.doInvoke(InvocableHandlerMethod.java:257)'
            ),
        },
        {
            'stream': {
                'job': 'auth-service',
                'app': 'auth-service',
                'namespace': 'prod',
                'cluster': 'cn-sh-prod',
                'region': 'cn-shanghai',
                'profile': 'prod',
                'container': 'auth',
                'level': 'warning',
                'service_name': 'auth-service',
            },
            'thread': 'http-nio-8071-exec-2',
            'logger': 'com.sxdevops.auth.filter.JwtTokenFilter',
            'message': 'token will expire soon, userId=10086, expireIn=92s, clientIp=10.20.31.18',
        },
        {
            'stream': {
                'job': 'auth-service',
                'app': 'auth-service',
                'namespace': 'prod',
                'cluster': 'cn-sh-prod',
                'region': 'cn-shanghai',
                'profile': 'prod',
                'container': 'auth',
                'level': 'error',
                'service_name': 'auth-service',
            },
            'thread': 'http-nio-8071-exec-9',
            'logger': 'com.sxdevops.auth.filter.JwtTokenFilter',
            'message': 'authentication failed, token verify error, reason=JwtException: token expired',
        },
        {
            'stream': {
                'job': 'user-service',
                'app': 'user-service',
                'namespace': 'prod',
                'cluster': 'cn-sh-prod',
                'region': 'cn-shanghai',
                'profile': 'prod',
                'container': 'user',
                'level': 'info',
                'service_name': 'user-service',
            },
            'thread': 'http-nio-8061-exec-4',
            'logger': 'com.sxdevops.user.service.UserProfileService',
            'message': 'load user profile from redis cache, userId=10086, cacheHit=true, cost=6ms',
        },
        {
            'stream': {
                'job': 'inventory-service',
                'app': 'inventory-service',
                'namespace': 'prod',
                'cluster': 'cn-hz-prod',
                'region': 'cn-hangzhou',
                'profile': 'prod',
                'container': 'inventory',
                'level': 'debug',
                'service_name': 'inventory-service',
            },
            'thread': 'scheduling-1',
            'logger': 'com.sxdevops.inventory.job.StockSyncJob',
            'message': 'stock sync task finished, warehouseCode=HZ01, total=128, changed=5',
        },
        {
            'stream': {
                'job': 'user-service',
                'app': 'user-service',
                'namespace': 'prod',
                'cluster': 'cn-sh-prod',
                'region': 'cn-shanghai',
                'profile': 'prod',
                'container': 'user',
                'level': 'info',
                'service_name': 'user-service',
            },
            'thread': 'http-nio-8061-exec-8',
            'logger': 'com.sxdevops.user.controller.UserPortalController',
            'message': 'tenant gray user routed to v2026.3-gray, tenantId=t-vip, feature=user-portrait-v2, percent=10',
        },
    ]
    timestamps = _demo_time_points(start_ms, end_ms, len(base_entries) * DEMO_LOG_BATCHES)
    entries = []
    for batch in range(DEMO_LOG_BATCHES):
        for offset, entry in enumerate(base_entries):
            current = batch * len(base_entries) + offset
            stream = dict(entry['stream'])
            stream['instance'] = f"{stream['app']}-{batch % 4 + 1:02d}"
            stream['pod'] = f"{stream['app']}-{batch + 1:02d}"
            stream['tenant_id'] = ['t-ob', 't-vip', 't-gov', 't-retail'][batch % 4]
            stream['tenant_name'] = ['欧泊电商', 'VIP 会员中心', '政务专区', '零售平台'][batch % 4]
            stream['release'] = 'gray' if batch % 5 == 0 else 'stable'
            stream['lane'] = 'canary' if batch % 5 == 0 else 'default'
            stream['env'] = 'prod-gray' if batch % 5 == 0 else 'prod'
            stream['version'] = f"2026.3.{batch % 6 + 1}-{'gray' if batch % 5 == 0 else 'release'}"
            timestamp_text = datetime.fromtimestamp(timestamps[current] / 1000, tz=dt_timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            trace_id = hashlib.md5(f"{stream['app']}-{current}-{batch}".encode('utf-8')).hexdigest()[:16]
            span_id = hashlib.sha1(f"{entry['logger']}-{current}-{batch}".encode('utf-8')).hexdigest()[:8]
            entries.append({
                'timestamp_ns': int(timestamps[current] * 1_000_000),
                'message': (
                    f"{timestamp_text} {stream['level'].upper():<5} 1 --- "
                    f"[{entry['thread']}] [{stream['app']},{trace_id},{span_id}] "
                    f"{entry['logger']} : {entry['message']}"
                ),
                'attributes': {
                    'trace_id': trace_id,
                    'span_id': span_id,
                    'thread': entry['thread'],
                    'logger': entry['logger'],
                    'tenant_id': stream['tenant_id'],
                    'tenant_name': stream['tenant_name'],
                    'release': stream['release'],
                    'lane': stream['lane'],
                    'version': stream['version'],
                },
                'stream': stream,
            })
    entries.sort(key=lambda item: item['timestamp_ns'], reverse=True)
    return entries


def _parse_demo_loki_query(query):
    parsed = {'selectors': [], 'filters': []}
    if not query:
        return parsed

    selector_match = re.search(r'\{([^}]*)\}', query)
    if selector_match:
        for raw_item in selector_match.group(1).split(','):
            item = raw_item.strip()
            if not item:
                continue
            match = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\s*(=~|!~|!=|=)\s*"([^"]*)"', item)
            if match:
                parsed['selectors'].append(match.groups())

    tail = query.split('}', 1)[1] if '}' in query else query
    for operator, value in re.findall(r'(\|=|\|~|!=|!~)\s*"([^"]*)"', tail):
        parsed['filters'].append((operator, value))
    return parsed


def _match_demo_loki_selector(actual, operator, expected):
    actual = str(actual or '')
    if operator == '=':
        return actual == expected
    if operator == '!=':
        return actual != expected
    if operator == '=~':
        return re.search(expected, actual) is not None
    if operator == '!~':
        return re.search(expected, actual) is None
    return True


def _match_demo_loki_filter(message, operator, expected):
    message = str(message or '')
    if operator == '|=':
        return expected.lower() in message.lower()
    if operator == '!=':
        return expected.lower() not in message.lower()
    if operator == '|~':
        return re.search(expected, message, flags=re.IGNORECASE) is not None
    if operator == '!~':
        return re.search(expected, message, flags=re.IGNORECASE) is None
    return True


def _matches_demo_loki_query(entry, query):
    parsed = _parse_demo_loki_query(query)
    for label, operator, expected in parsed['selectors']:
        if not _match_demo_loki_selector(entry.get('stream', {}).get(label), operator, expected):
            return False
    for operator, expected in parsed['filters']:
        if not _match_demo_loki_filter(entry.get('message', ''), operator, expected):
            return False

    normalized = re.sub(r'\{[^}]*\}', ' ', query or '')
    normalized = re.sub(r'(\|=|\|~|!=|!~)\s*"[^"]*"', ' ', normalized)
    extra_terms = _extract_query_terms(normalized)
    if not extra_terms:
        return True

    haystack = ' '.join([
        entry.get('message', ''),
        json.dumps(entry.get('stream', {}), ensure_ascii=False),
        json.dumps(entry.get('attributes', {}), ensure_ascii=False),
    ]).lower()
    return all(term in haystack for term in extra_terms)


def _demo_elk_documents(start_ms, end_ms):
    base_entries = [
        {
            'index': 'logs-demo-app-2026.03.15',
            'service': 'gateway-service',
            'logger': 'com.sxdevops.gateway.filter.AccessLogFilter',
            'thread': 'reactor-http-nio-4',
            'message': 'route matched, routeId=order-service, path=/api/orders/submit, cost=18ms',
            'host': 'gateway-01',
            'env': 'prod',
        },
        {
            'index': 'logs-demo-app-2026.03.15',
            'service': 'gateway-service',
            'logger': 'com.sxdevops.gateway.filter.ExceptionLogFilter',
            'thread': 'reactor-http-nio-7',
            'message': 'forward request failed, uri=lb://order-service, reason=ReadTimeoutException: downstream timeout',
            'host': 'gateway-02',
            'env': 'prod',
        },
        {
            'index': 'logs-demo-app-2026.03.15',
            'service': 'order-service',
            'logger': 'com.sxdevops.order.controller.OrderController',
            'thread': 'http-nio-8082-exec-3',
            'message': 'create order success, orderNo=SO202603160001, tenantId=t-ob, amount=299.00',
            'host': 'order-01',
            'env': 'prod',
        },
        {
            'index': 'logs-demo-app-2026.03.15',
            'service': 'order-service',
            'logger': 'com.sxdevops.order.service.PaymentRemoteService',
            'thread': 'http-nio-8082-exec-7',
            'message': 'feign invoke payment-service failed, status=500, retry=2, msg=payment status update timeout',
            'host': 'order-02',
            'env': 'prod',
        },
        {
            'index': 'logs-demo-app-2026.03.15',
            'service': 'payment-service',
            'logger': 'com.sxdevops.payment.controller.PaymentCallbackController',
            'thread': 'http-nio-8091-exec-12',
            'message': (
                'payment callback processing exception, requestId=cb-20260316-991, tenantId=t-ob, '
                'ex=java.lang.NullPointerException: callback payload is null\n'
                'java.lang.NullPointerException: callback payload is null\n'
                '\tat com.sxdevops.payment.controller.PaymentCallbackController.handle(PaymentCallbackController.java:87)\n'
                '\tat com.sxdevops.payment.controller.PaymentCallbackController.callback(PaymentCallbackController.java:52)'
            ),
            'host': 'payment-02',
            'env': 'prod',
        },
        {
            'index': 'logs-demo-app-2026.03.15',
            'service': 'payment-service',
            'logger': 'com.sxdevops.payment.service.CallbackService',
            'thread': 'http-nio-8091-exec-5',
            'message': 'payment callback processed successfully, channel=alipay, tradeStatus=SUCCESS',
            'host': 'payment-01',
            'env': 'prod',
        },
        {
            'index': 'logs-demo-security-2026.03.15',
            'service': 'auth-service',
            'logger': 'com.sxdevops.auth.filter.JwtTokenFilter',
            'thread': 'http-nio-8071-exec-9',
            'message': 'authentication failed, token verify error, reason=JwtException: token expired',
            'host': 'auth-01',
            'env': 'prod',
        },
        {
            'index': 'logs-demo-security-2026.03.15',
            'service': 'user-service',
            'logger': 'com.sxdevops.user.controller.UserPortalController',
            'thread': 'http-nio-8061-exec-8',
            'message': 'tenant gray user routed to v2026.3-gray, tenantId=t-vip, feature=user-portrait-v2, percent=10',
            'host': 'user-01',
            'env': 'prod-gray',
        },
        {
            'index': 'logs-demo-security-2026.03.15',
            'service': 'inventory-service',
            'logger': 'com.sxdevops.inventory.job.StockSyncJob',
            'thread': 'scheduling-1',
            'message': 'stock sync task finished, warehouseCode=HZ01, total=128, changed=5',
            'host': 'inventory-01',
            'env': 'prod',
        },
        {
            'index': 'logs-demo-security-2026.03.15',
            'service': 'gateway-service',
            'logger': 'com.sxdevops.gateway.filter.GrayReleaseRouteFilter',
            'thread': 'reactor-http-nio-3',
            'message': 'gray release route hit, routeId=payment-service-gray, tenantId=t-ob, version=gray, header[X-Gray]=true',
            'host': 'gateway-01',
            'env': 'prod-gray',
        },
    ]
    timestamps = _demo_time_points(start_ms, end_ms, len(base_entries) * DEMO_LOG_BATCHES)
    docs = []
    for batch in range(DEMO_LOG_BATCHES):
        for offset, entry in enumerate(base_entries):
            current = batch * len(base_entries) + offset
            level = _detect_level(entry['message'], {'level': 'error' if 'Exception' in entry['message'] or 'failed' in entry['message'] else 'info'})
            if 'gray' in entry['env'] and level == 'unknown':
                level = 'info'
            level_text = {'error': 'ERROR', 'warning': 'WARN', 'debug': 'DEBUG', 'info': 'INFO'}.get(level, 'INFO')
            trace_id = hashlib.md5(f"elk-{entry['service']}-{current}-{batch}".encode('utf-8')).hexdigest()[:16]
            span_id = hashlib.sha1(f"elk-{entry['logger']}-{current}-{batch}".encode('utf-8')).hexdigest()[:8]
            timestamp_text = datetime.fromtimestamp(timestamps[current] / 1000, tz=dt_timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            tenant_id = ['t-ob', 't-vip', 't-gov', 't-retail'][batch % 4]
            tenant_name = ['欧泊电商', 'VIP 会员中心', '政务专区', '零售平台'][batch % 4]
            release = 'gray' if batch % 5 == 0 else 'stable'
            lane = 'canary' if batch % 5 == 0 else 'default'
            version = f"2026.3.{batch % 6 + 1}-{'gray' if release == 'gray' else 'release'}"
            docs.append({
                '_index': entry['index'],
                '_source': {
                    '@timestamp': _iso_from_ms(timestamps[current]),
                    'message': (
                        f"{timestamp_text} {level_text:<5} 1 --- "
                        f"[{entry['thread']}] [{entry['service']},{trace_id},{span_id}] "
                        f"{entry['logger']} : {entry['message']}"
                    ),
                    'level': level_text,
                    'service': {'name': entry['service']},
                    'host': {'name': entry['host']},
                    'env': entry['env'],
                    'trace_id': trace_id,
                    'span_id': span_id,
                    'thread_name': entry['thread'],
                    'logger_name': entry['logger'],
                    'tenant_id': tenant_id,
                    'tenant_name': tenant_name,
                    'release': release,
                    'lane': lane,
                    'version': version,
                    'kubernetes': {
                        'namespace': 'prod',
                        'container_name': entry['service'].replace('-service', ''),
                        'pod_name': f"{entry['service']}-{batch + 1:02d}",
                    },
                },
            })
    docs.sort(key=lambda item: item['_source']['@timestamp'], reverse=True)
    return docs


def _demo_sls_documents(start_ms, end_ms, logstore):
    base_entries = [
        ('INFO', 'order-service', 'order-01', 'http-nio-8082-exec-3', 'com.sxdevops.order.controller.OrderController', 'create order success, orderNo=SO202603160001, tenantId=t-ob, amount=299.00'),
        ('ERROR', 'order-service', 'order-02', 'http-nio-8082-exec-11', 'com.sxdevops.order.service.impl.OrderSubmitServiceImpl', 'submit order failed, orderNo=SO202603160009, tenantId=t-vip, ex=java.lang.IllegalStateException: warehouse api timeout\njava.lang.IllegalStateException: warehouse api timeout\n\tat com.sxdevops.order.service.impl.OrderSubmitServiceImpl.lockStock(OrderSubmitServiceImpl.java:214)\n\tat com.sxdevops.order.service.impl.OrderSubmitServiceImpl.submit(OrderSubmitServiceImpl.java:126)'),
        ('INFO', 'payment-service', 'payment-01', 'http-nio-8091-exec-5', 'com.sxdevops.payment.service.CallbackService', 'payment callback processed successfully, channel=alipay, tradeStatus=SUCCESS'),
        ('ERROR', 'payment-service', 'payment-02', 'http-nio-8091-exec-12', 'com.sxdevops.payment.controller.PaymentCallbackController', 'payment callback processing exception, requestId=cb-20260316-991, tenantId=t-ob, ex=java.lang.NullPointerException: callback payload is null\njava.lang.NullPointerException: callback payload is null\n\tat com.sxdevops.payment.controller.PaymentCallbackController.handle(PaymentCallbackController.java:87)'),
        ('WARN', 'auth-service', 'auth-01', 'http-nio-8071-exec-2', 'com.sxdevops.auth.filter.JwtTokenFilter', 'token will expire soon, userId=10086, expireIn=92s, clientIp=10.20.31.18'),
        ('ERROR', 'auth-service', 'auth-02', 'http-nio-8071-exec-9', 'com.sxdevops.auth.filter.JwtTokenFilter', 'authentication failed, token verify error, reason=JwtException: token expired'),
        ('INFO', 'user-service', 'user-01', 'http-nio-8061-exec-8', 'com.sxdevops.user.controller.UserPortalController', 'tenant gray user routed to v2026.3-gray, tenantId=t-vip, feature=user-portrait-v2, percent=10'),
        ('INFO', logstore or 'demo-logstore', 'sls-app-05', 'scheduling-1', 'com.sxdevops.logging.job.LogHeartbeatJob', 'demo logstore heartbeat is healthy, collector=sls-agent'),
    ]
    timestamps = _demo_time_points(start_ms, end_ms, len(base_entries) * DEMO_LOG_BATCHES)
    logs = []
    for batch in range(DEMO_LOG_BATCHES):
        for offset, entry in enumerate(base_entries):
            current = batch * len(base_entries) + offset
            level, service, host, thread_name, logger_name, message = entry
            trace_id = hashlib.md5(f"sls-{service}-{current}-{batch}".encode('utf-8')).hexdigest()[:16]
            span_id = hashlib.sha1(f"sls-{logger_name}-{current}-{batch}".encode('utf-8')).hexdigest()[:8]
            timestamp_text = datetime.fromtimestamp(timestamps[current] / 1000, tz=dt_timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            tenant_id = ['t-ob', 't-vip', 't-gov', 't-retail'][batch % 4]
            tenant_name = ['欧泊电商', 'VIP 会员中心', '政务专区', '零售平台'][batch % 4]
            release = 'gray' if batch % 5 == 0 else 'stable'
            lane = 'canary' if batch % 5 == 0 else 'default'
            version = f"2026.3.{batch % 6 + 1}-{'gray' if release == 'gray' else 'release'}"
            logs.append({
                '__time__': int(timestamps[current] / 1000),
                'level': level,
                'service': service,
                'host': host,
                'message': (
                    f"{timestamp_text} {level:<5} 1 --- "
                    f"[{thread_name}] [{service},{trace_id},{span_id}] "
                    f"{logger_name} : {message}"
                ),
                'trace_id': trace_id,
                'span_id': span_id,
                'thread_name': thread_name,
                'logger_name': logger_name,
                'tenant_id': tenant_id,
                'tenant_name': tenant_name,
                'release': release,
                'lane': lane,
                'version': version,
                '__tag__:__hostname__': host,
                'env': 'prod-gray' if release == 'gray' else 'prod',
            })
    logs.sort(key=lambda item: item['__time__'], reverse=True)
    return logs


def _loki_request(endpoint, path, params):
    url = f'{_normalize_endpoint(endpoint)}{path}'
    try:
        response = http_requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    except http_requests.Timeout as exc:
        raise ProviderError('Loki request timed out', status.HTTP_504_GATEWAY_TIMEOUT, {'detail': str(exc)}) from exc
    except http_requests.ConnectionError as exc:
        raise ProviderError('Unable to connect to Loki', status.HTTP_502_BAD_GATEWAY, {'detail': str(exc)}) from exc
    _raise_for_status(response, 'Loki')
    return _safe_json(response)


def _elk_auth_headers(config):
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    auth = None
    auth_type = config.get('auth_type', 'none')
    if auth_type == 'basic':
        auth = (config.get('username', ''), config.get('password', ''))
    elif auth_type == 'api_key' and config.get('api_key'):
        headers['Authorization'] = f'ApiKey {config["api_key"]}'
    elif auth_type == 'bearer' and config.get('bearer_token'):
        headers['Authorization'] = f'Bearer {config["bearer_token"]}'
    return headers, auth


def _elk_request(method, endpoint, path, config, params=None, body=None):
    url = f'{_normalize_endpoint(endpoint)}{path}'
    headers, auth = _elk_auth_headers(config)
    try:
        response = http_requests.request(
            method,
            url,
            params=params,
            json=body,
            headers=headers,
            auth=auth,
            timeout=REQUEST_TIMEOUT,
        )
    except http_requests.Timeout as exc:
        raise ProviderError('ELK request timed out', status.HTTP_504_GATEWAY_TIMEOUT, {'detail': str(exc)}) from exc
    except http_requests.ConnectionError as exc:
        raise ProviderError('Unable to connect to ELK', status.HTTP_502_BAD_GATEWAY, {'detail': str(exc)}) from exc
    _raise_for_status(response, 'ELK')
    return _safe_json(response)


def _sls_host(config):
    endpoint = (config.get('endpoint') or '').replace('https://', '').replace('http://', '').strip('/')
    project = config.get('project', '').strip()
    if not endpoint or not project:
        raise ProviderError('Aliyun SLS endpoint and project are required')
    return endpoint if endpoint.startswith(f'{project}.') else f'{project}.{endpoint}'


def _sls_resource(path, params):
    if not params:
        return path
    parts = []
    for key in sorted(params):
        value = params[key]
        if isinstance(value, list):
            for item in value:
                parts.append(f'{quote(str(key), safe="-_.~/")}={quote(str(item), safe="-_.~/")}')
        else:
            parts.append(f'{quote(str(key), safe="-_.~/")}={quote(str(value), safe="-_.~/")}')
    return f'{path}?{"&".join(parts)}'


def _sls_request(method, config, path, params=None):
    access_key_id = config.get('access_key_id')
    access_key_secret = config.get('access_key_secret')
    if not access_key_id or not access_key_secret:
        raise ProviderError('Aliyun SLS access key id and secret are required')

    date = formatdate(usegmt=True)
    headers = {
        'Date': date,
        'x-log-apiversion': '0.6.0',
        'x-log-signaturemethod': 'hmac-sha1',
    }
    canonical_headers = ''.join(
        f'{key.lower()}:{value}\n'
        for key, value in sorted((k, v) for k, v in headers.items() if k.lower().startswith('x-log-'))
    )
    resource = _sls_resource(path, params or {})
    string_to_sign = '\n'.join([
        method.upper(),
        '',
        '',
        date,
        f'{canonical_headers}{resource}',
    ])
    signature = base64.b64encode(
        hmac.new(access_key_secret.encode('utf-8'), string_to_sign.encode('utf-8'), hashlib.sha1).digest()
    ).decode('utf-8')
    headers['Authorization'] = f'LOG {access_key_id}:{signature}'

    url = f'https://{_sls_host(config)}{resource}'
    try:
        response = http_requests.request(method, url, headers=headers, timeout=REQUEST_TIMEOUT)
    except http_requests.Timeout as exc:
        raise ProviderError('Aliyun SLS request timed out', status.HTTP_504_GATEWAY_TIMEOUT, {'detail': str(exc)}) from exc
    except http_requests.ConnectionError as exc:
        raise ProviderError('Unable to connect to Aliyun SLS', status.HTTP_502_BAD_GATEWAY, {'detail': str(exc)}) from exc
    _raise_for_status(response, 'Aliyun SLS')
    payload = _safe_json(response)
    if isinstance(payload, list):
        response_headers = getattr(response, 'headers', {}) or {}
        raw_count = response_headers.get('x-log-count') or response_headers.get('X-Log-Count')
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            count = len(payload)
        return {
            'logs': payload,
            'count': count,
            'progress': response_headers.get('x-log-progress') or response_headers.get('X-Log-Progress') or '',
        }
    return payload


def _catalog_loki(config, payload):
    start_ms, end_ms = _time_bounds(payload)
    action = payload.get('action', 'labels')
    if _is_demo_config(config):
        entries = _demo_loki_entries(start_ms, end_ms)
        if action == 'label_values':
            label = payload.get('label')
            if not label:
                raise ProviderError('label is required for Loki label values')
            values = sorted({item['stream'].get(label) for item in entries if item['stream'].get(label) not in (None, '')})
            return {'kind': 'label_values', 'items': values}

        labels = sorted({key for item in entries for key in item.get('stream', {}).keys()})
        return {'kind': 'labels', 'items': labels}

    params = {
        'start': str(start_ms * 1_000_000),
        'end': str(end_ms * 1_000_000),
    }
    if action == 'label_values':
        label = payload.get('label')
        if not label:
            raise ProviderError('label is required for Loki label values')
        data = _loki_request(config['endpoint'], f'/loki/api/v1/label/{label}/values', params)
        return {'kind': 'label_values', 'items': data.get('data', [])}
    data = _loki_request(config['endpoint'], '/loki/api/v1/labels', params)
    return {'kind': 'labels', 'items': data.get('data', [])}


def _catalog_elk(config, payload):
    if _is_demo_config(config):
        names = config.get('demo_indices') or ['logs-demo-app-2026.03.15', 'logs-demo-security-2026.03.15']
        return {
            'kind': 'indices',
            'items': [{'name': name, 'docs_count': '1280', 'store_size': '12mb'} for name in names],
        }

    if not config.get('endpoint'):
        raise ProviderError('ELK endpoint is required')
    pattern = payload.get('index_pattern') or config.get('index_pattern') or '*'
    data = _elk_request('GET', config.get('endpoint', ''), f'/_cat/indices/{pattern}', config, params={'format': 'json'})
    items = []
    for row in data:
        index_name = row.get('index')
        if index_name:
            items.append({
                'name': index_name,
                'docs_count': row.get('docs.count'),
                'store_size': row.get('store.size'),
            })
    return {'kind': 'indices', 'items': items}


def _catalog_sls(config, payload):
    if _is_demo_config(config):
        names = config.get('demo_logstores') or [config.get('logstore') or 'demo-logstore', 'demo-audit-logstore']
        return {'kind': 'logstores', 'items': [{'name': name} for name in names]}

    data = _sls_request('GET', config, '/logstores')
    raw_items = data.get('logstores') if isinstance(data, dict) else data
    items = [{'name': item} for item in (raw_items or [])]
    return {'kind': 'logstores', 'items': items}


def _query_loki(config, payload):
    query = (payload.get('query') or '').strip()
    if not query:
        raise ProviderError('Loki query is required')
    start_ms, end_ms = _time_bounds(payload)

    if _is_demo_config(config):
        matched_logs = []
        for entry in _demo_loki_entries(start_ms, end_ms):
            if not _matches_demo_loki_query(entry, query):
                continue
            attributes = _with_trace_id({**entry['stream'], **entry.get('attributes', {})}, entry['message'])
            matched_logs.append({
                'timestamp': _iso_from_ns(entry['timestamp_ns']),
                'message': entry['message'],
                'level': _detect_level(entry['message'], entry['stream']),
                'source': entry['stream'].get('job') or entry['stream'].get('app') or 'loki',
                'attributes': attributes,
            })
        return {
            'provider': 'loki',
            'query': query,
            'source': 'LogQL',
            'total': len(matched_logs),
            'took_ms': 8,
            'logs': matched_logs[:_sanitize_limit(payload.get('limit'))],
        }

    params = {
        'query': query,
        'start': str(start_ms * 1_000_000),
        'end': str(end_ms * 1_000_000),
        'limit': _sanitize_limit(payload.get('limit')),
        'direction': payload.get('direction') or 'backward',
    }
    response = _loki_request(config['endpoint'], '/loki/api/v1/query_range', params)
    streams = response.get('data', {}).get('result', [])
    logs = []
    for stream in streams:
        labels = stream.get('stream', {})
        for timestamp, message in stream.get('values', []):
            attributes = _with_trace_id(labels, message)
            logs.append({
                'sort_key': int(timestamp),
                'timestamp': _iso_from_ns(timestamp),
                'message': message,
                'level': _detect_level(message, labels),
                'source': labels.get('job') or labels.get('app') or labels.get('service_name') or 'loki',
                'attributes': attributes,
            })
    logs.sort(key=lambda item: item['sort_key'], reverse=True)
    for item in logs:
        item.pop('sort_key', None)
    return {
        'provider': 'loki',
        'query': query,
        'source': 'LogQL',
        'total': len(logs),
        'took_ms': None,
        'logs': logs,
    }


def _query_elk(config, payload):
    index_pattern = payload.get('source') or payload.get('index_pattern') or config.get('index_pattern') or '*'
    time_field = payload.get('time_field') or config.get('time_field') or '@timestamp'
    message_fields = _split_fields(payload.get('message_fields') or config.get('message_fields'), ['message', 'log', 'msg'])
    query = (payload.get('query') or '').strip()
    start_ms, end_ms = _time_bounds(payload)

    if _is_demo_config(config):
        docs = []
        index_prefix = index_pattern.replace('*', '') if '*' in index_pattern else index_pattern
        for hit in _demo_elk_documents(start_ms, end_ms):
            if index_pattern not in ('*', hit['_index']) and not hit['_index'].startswith(index_prefix):
                continue
            if _matches_demo_query(hit['_source'].get('message', ''), hit['_source'], query):
                docs.append(hit)
        response = {
            'took': 12,
            'hits': {
                'total': {'value': len(docs)},
                'hits': docs[:_sanitize_limit(payload.get('limit'))],
            },
        }
    else:
        endpoint = config.get('endpoint')
        if not endpoint:
            raise ProviderError('ELK endpoint is required')

        body = {
            'size': _sanitize_limit(payload.get('limit')),
            'sort': [{time_field: {'order': 'desc', 'unmapped_type': 'date'}}],
            'query': {
                'bool': {
                    'filter': [{
                        'range': {
                            time_field: {
                                'gte': _iso_from_ms(start_ms),
                                'lte': _iso_from_ms(end_ms),
                                'format': 'strict_date_optional_time',
                            }
                        }
                    }],
                    'must': [{'match_all': {}}] if not query else [{
                        'query_string': {
                            'query': query,
                            'default_operator': 'AND',
                        }
                    }],
                }
            },
        }
        response = _elk_request('POST', endpoint, f'/{index_pattern}/_search', config, body=body)

    hits = response.get('hits', {}).get('hits', [])
    total = response.get('hits', {}).get('total', {})
    total_value = total.get('value') if isinstance(total, dict) else total if isinstance(total, int) else len(hits)
    logs = []
    for hit in hits:
        source = hit.get('_source') or {}
        timestamp = _get_nested(source, time_field) or hit.get('sort', [None])[0]
        attributes = dict(source)
        attributes['_index'] = hit.get('_index')
        logs.append({
            'timestamp': _iso_from_ms(timestamp) if timestamp else '',
            'message': _pick_message(source, message_fields),
            'level': _detect_level(source.get('level') or source.get('log.level') or '', source) if source else 'unknown',
            'source': hit.get('_index') or 'elasticsearch',
            'attributes': _with_trace_id(attributes, _pick_message(source, message_fields)),
        })
        if logs[-1]['level'] == 'unknown':
            logs[-1]['level'] = _detect_level(logs[-1]['message'], source)

    return {
        'provider': 'elk',
        'query': query,
        'source': index_pattern,
        'total': total_value if total_value is not None else len(logs),
        'took_ms': response.get('took'),
        'logs': logs,
    }


def _query_sls(config, payload):
    logstore = payload.get('source') or payload.get('logstore') or config.get('logstore') or 'demo-logstore'
    query = (payload.get('query') or '').strip() or '*'
    start_ms, end_ms = _time_bounds(payload)

    if _is_demo_config(config):
        matched_items = [
            item for item in _demo_sls_documents(start_ms, end_ms, logstore)
            if _matches_demo_query(item.get('message', ''), item, query)
        ]
        response = {
            'logs': matched_items[: _sanitize_limit(payload.get('limit'))],
            'count': len(matched_items),
            'progress': 'Complete',
        }
    else:
        if not logstore:
            raise ProviderError('Aliyun SLS logstore is required')
        params = {
            'type': 'log',
            'from': int(start_ms / 1000),
            'to': int(end_ms / 1000),
            'offset': 0,
            'line': _sanitize_limit(payload.get('limit')),
            'reverse': 'true',
            'query': query,
        }
        topic = payload.get('topic') or config.get('topic')
        if topic:
            params['topic'] = topic
        response = _sls_request('GET', config, f'/logstores/{logstore}', params=params)

    raw_logs = response.get('logs', [])
    logs = []
    for item in raw_logs:
        if not isinstance(item, dict):
            continue
        timestamp = item.get('__time__') or item.get('time') or item.get('@timestamp')
        logs.append({
            'timestamp': _iso_from_ms(timestamp) if timestamp else '',
            'message': _pick_message(item, ['message', 'content', 'msg', '__content__']),
            'level': _detect_level(item.get('level') or item.get('severity') or '', item),
            'source': logstore,
            'attributes': _with_trace_id(item, _pick_message(item, ['message', 'content', 'msg', '__content__'])),
        })
        if logs[-1]['level'] == 'unknown':
            logs[-1]['level'] = _detect_level(logs[-1]['message'], item)

    return {
        'provider': 'sls',
        'query': query,
        'source': logstore,
        'total': response.get('count', len(logs)),
        'took_ms': None,
        'logs': logs,
        'progress': response.get('progress'),
    }


def _get_catalog(provider, config, payload):
    if provider == 'loki':
        return _catalog_loki(config, payload)
    if provider == 'elk':
        return _catalog_elk(config, payload)
    if provider == 'sls':
        return _catalog_sls(config, payload)
    raise ProviderError('Unsupported log provider')


def _run_query(provider, config, payload):
    if provider == 'loki':
        return _query_loki(config, payload)
    if provider == 'elk':
        return _query_elk(config, payload)
    if provider == 'sls':
        return _query_sls(config, payload)
    raise ProviderError('Unsupported log provider')


def _error_response(exc):
    return Response({'error': str(exc), 'detail': exc.detail}, status=exc.status_code)


class LogDataSourceViewSet(EventWallModelViewSetMixin, RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = LogDataSource.objects.all().order_by('provider', 'name')
    serializer_class = LogDataSourceSerializer
    pagination_class = None
    event_module = 'ops'
    event_resource_type = 'log_datasource'
    event_resource_label = '日志数据源'
    event_resource_name_fields = ('name',)
    event_exclude_fields = ('config',)
    rbac_permissions = {
        'list': ['ops.log.datasource.view'],
        'retrieve': ['ops.log.datasource.view'],
        'create': ['ops.log.datasource.manage'],
        'update': ['ops.log.datasource.manage'],
        'partial_update': ['ops.log.datasource.manage'],
        'destroy': ['ops.log.datasource.manage'],
        'test_connection': ['ops.log.datasource.manage'],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        provider = self.request.query_params.get('provider')
        is_enabled = self.request.query_params.get('is_enabled')

        if provider:
            queryset = queryset.filter(provider=provider)
        if is_enabled in ('true', 'false'):
            queryset = queryset.filter(is_enabled=is_enabled == 'true')
        return queryset

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        datasource = self.get_object()
        try:
            payload = {'action': 'labels'} if datasource.provider == 'loki' else {'action': 'sources'}
            preview = _get_catalog(datasource.provider, _merge_config(datasource.provider, datasource.config), payload)
            record_event(
                request=request,
                module='ops',
                category='execution',
                action='test_log_datasource',
                title='测试日志数据源连通性',
                summary=f'日志数据源 {datasource.name} 连通性测试成功',
                resource_type='log_datasource',
                resource_id=datasource.id,
                resource_name=datasource.name,
                correlation_id=f'log-datasource:{datasource.id}',
                metadata={'provider': datasource.provider, 'preview_kind': preview.get('kind')},
            )
            return Response({
                'success': True,
                'message': f'{datasource.name} 连接成功',
                'preview_count': len(preview.get('items', [])),
                'preview_kind': preview.get('kind'),
            })
        except ProviderError as exc:
            record_event(
                request=request,
                module='ops',
                category='execution',
                action='test_log_datasource',
                title='测试日志数据源连通性',
                summary=f'日志数据源 {datasource.name} 连通性测试失败',
                result=EventRecord.RESULT_FAILED,
                severity=EventRecord.SEVERITY_WARNING,
                resource_type='log_datasource',
                resource_id=datasource.id,
                resource_name=datasource.name,
                correlation_id=f'log-datasource:{datasource.id}',
                metadata={'provider': datasource.provider, 'error': str(exc)},
            )
            return Response({'success': False, 'message': str(exc), 'detail': exc.detail}, status=exc.status_code)
        except Exception as exc:
            record_event(
                request=request,
                module='ops',
                category='execution',
                action='test_log_datasource',
                title='测试日志数据源连通性',
                summary=f'日志数据源 {datasource.name} 连通性测试失败',
                result=EventRecord.RESULT_FAILED,
                severity=EventRecord.SEVERITY_WARNING,
                resource_type='log_datasource',
                resource_id=datasource.id,
                resource_name=datasource.name,
                correlation_id=f'log-datasource:{datasource.id}',
                metadata={'provider': datasource.provider, 'error': str(exc)},
            )
            return Response(
                {'success': False, 'message': '连接测试失败', 'detail': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('ops.log.datasource.view')])
def log_providers(request):
    return Response({'providers': _provider_info()})


@api_view(['POST'])
@permission_classes([IsAuthenticated, build_rbac_permission('ops.log.query')])
def log_provider_catalog(request, provider):
    try:
        resolved_provider, config, _ = _resolve_provider_and_config({**request.data, 'provider': provider})
        if resolved_provider != provider:
            raise ProviderError('provider 与数据源类型不一致')
        return Response(_get_catalog(provider, config, request.data))
    except ProviderError as exc:
        return _error_response(exc)
    except Exception as exc:
        return Response(
            {'error': 'Unexpected log catalog failure', 'detail': str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, build_rbac_permission('ops.log.query')])
def log_query(request):
    try:
        provider, config, datasource = _resolve_provider_and_config(request.data)
        payload = dict(request.data)
        if datasource and provider == 'sls':
            payload.setdefault('source', datasource.config.get('logstore'))
        return Response(_run_query(provider, config, payload))
    except ProviderError as exc:
        return _error_response(exc)
    except Exception as exc:
        return Response(
            {'error': 'Unexpected log query failure', 'detail': str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
