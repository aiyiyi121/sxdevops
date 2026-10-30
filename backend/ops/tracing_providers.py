from datetime import datetime, timedelta

import requests as http_requests
from django.conf import settings
from rest_framework import status


REQUEST_TIMEOUT = 20
DEFAULT_TRACE_LIMIT = 20
TRACING_SENSITIVE_KEYS = {'authorization', 'token', 'api_key', 'password', 'client_secret'}

PROVIDER_LABELS = {
    'demo': '演示数据',
    'skywalking': 'SkyWalking',
    'tempo': 'Tempo / OpenTelemetry',
    'jaeger': 'Jaeger / OpenTelemetry',
    'zipkin': 'Zipkin / OpenTelemetry',
}

DEMO_SERVICES = [
    {'id': 'svc-gateway', 'name': 'gateway-service', 'short_name': 'gateway', 'layers': ['GENERAL'], 'group': 'sxdevops'},
    {'id': 'svc-order', 'name': 'order-service', 'short_name': 'order', 'layers': ['GENERAL'], 'group': 'sxdevops'},
    {'id': 'svc-payment', 'name': 'payment-service', 'short_name': 'payment', 'layers': ['GENERAL'], 'group': 'sxdevops'},
    {'id': 'svc-member', 'name': 'member-service', 'short_name': 'member', 'layers': ['GENERAL'], 'group': 'sxdevops'},
]

DEMO_TRACES = [
    {
        'trace_id': 'trace-demo-20260329-001',
        'segment_id': 'segment-demo-001',
        'service_id': 'svc-gateway',
        'service_name': 'gateway-service',
        'instance_name': 'gateway-prod-01',
        'endpoint_names': ['GET /api/orders/{id}', 'POST /api/payments'],
        'duration_ms': 248,
        'start': '2026-03-29T09:18:26+08:00',
        'is_error': False,
        'state': 'SUCCESS',
        'summary': '订单详情请求穿透到订单与支付服务，整体延迟稳定。',
    },
    {
        'trace_id': 'trace-demo-20260329-002',
        'segment_id': 'segment-demo-002',
        'service_id': 'svc-payment',
        'service_name': 'payment-service',
        'instance_name': 'payment-prod-02',
        'endpoint_names': ['POST /api/payments/callback'],
        'duration_ms': 1432,
        'start': '2026-03-29T09:14:11+08:00',
        'is_error': True,
        'state': 'ERROR',
        'summary': '支付回调在调用会员服务时超时，链路出现错误 Span。',
    },
    {
        'trace_id': 'trace-demo-20260329-003',
        'segment_id': 'segment-demo-003',
        'service_id': 'svc-order',
        'service_name': 'order-service',
        'instance_name': 'order-gray-01',
        'endpoint_names': ['POST /api/orders/confirm'],
        'duration_ms': 612,
        'start': '2026-03-29T09:05:48+08:00',
        'is_error': False,
        'state': 'SUCCESS',
        'summary': '灰度订单确认链路完成，数据库写入阶段耗时略高。',
    },
    {
        'trace_id': 'trace-demo-20260410-005',
        'segment_id': 'segment-demo-005',
        'service_id': 'svc-order',
        'service_name': 'order-service',
        'instance_name': 'order-prod-02',
        'endpoint_names': ['POST /api/orders/create', 'GET inventory-service /api/stock/check'],
        'duration_ms': 1824,
        'start': '2026-04-10T11:26:18+08:00',
        'is_error': True,
        'state': 'ERROR',
        'summary': '生产订单服务调用库存校验超时，触发下单失败并出现错误链路。',
    },
    {
        'trace_id': 'trace-demo-20260329-004',
        'segment_id': 'segment-demo-004',
        'service_id': 'svc-member',
        'service_name': 'member-service',
        'instance_name': 'member-prod-01',
        'endpoint_names': ['GET /api/members/{id}/profile'],
        'duration_ms': 318,
        'start': '2026-03-29T08:57:03+08:00',
        'is_error': False,
        'state': 'SUCCESS',
        'summary': '会员资料查询链路稳定，缓存命中率较高。',
    },
]

DEMO_TRACE_SPANS = {
    'trace-demo-20260329-001': [
        {'span_id': 0, 'parent_span_id': -1, 'service_code': 'gateway-service', 'service_instance_name': 'gateway-prod-01', 'endpoint_name': 'GET /api/orders/{id}', 'start_time': '2026-03-29T09:18:26.000+08:00', 'end_time': '2026-03-29T09:18:26.248+08:00', 'duration_ms': 248, 'type': 'Entry', 'peer': '', 'component': 'SpringMVC', 'is_error': False, 'layer': 'HTTP', 'tags': [{'key': 'http.method', 'value': 'GET'}, {'key': 'http.status_code', 'value': '200'}], 'logs': []},
        {'span_id': 1, 'parent_span_id': 0, 'service_code': 'order-service', 'service_instance_name': 'order-prod-01', 'endpoint_name': 'queryOrderById', 'start_time': '2026-03-29T09:18:26.024+08:00', 'end_time': '2026-03-29T09:18:26.156+08:00', 'duration_ms': 132, 'type': 'Exit', 'peer': 'order-service:20880', 'component': 'Dubbo', 'is_error': False, 'layer': 'RPC_FRAMEWORK', 'tags': [{'key': 'db.statement.count', 'value': '2'}], 'logs': []},
        {'span_id': 2, 'parent_span_id': 0, 'service_code': 'payment-service', 'service_instance_name': 'payment-prod-01', 'endpoint_name': 'queryPaymentStatus', 'start_time': '2026-03-29T09:18:26.061+08:00', 'end_time': '2026-03-29T09:18:26.199+08:00', 'duration_ms': 138, 'type': 'Exit', 'peer': 'payment-service:20880', 'component': 'Dubbo', 'is_error': False, 'layer': 'RPC_FRAMEWORK', 'tags': [{'key': 'result', 'value': 'PAID'}], 'logs': []},
    ],
    'trace-demo-20260329-002': [
        {'span_id': 0, 'parent_span_id': -1, 'service_code': 'payment-service', 'service_instance_name': 'payment-prod-02', 'endpoint_name': 'POST /api/payments/callback', 'start_time': '2026-03-29T09:14:11.000+08:00', 'end_time': '2026-03-29T09:14:12.432+08:00', 'duration_ms': 1432, 'type': 'Entry', 'peer': '', 'component': 'SpringMVC', 'is_error': True, 'layer': 'HTTP', 'tags': [{'key': 'http.method', 'value': 'POST'}, {'key': 'http.status_code', 'value': '500'}], 'logs': [{'time': '2026-03-29T09:14:12.406+08:00', 'data': [{'key': 'error.kind', 'value': 'TimeoutException'}, {'key': 'message', 'value': 'member-service request timed out'}]}]},
        {'span_id': 1, 'parent_span_id': 0, 'service_code': 'member-service', 'service_instance_name': 'member-prod-01', 'endpoint_name': 'loadMemberForPayment', 'start_time': '2026-03-29T09:14:11.202+08:00', 'end_time': '2026-03-29T09:14:12.401+08:00', 'duration_ms': 1199, 'type': 'Exit', 'peer': 'member-service:20880', 'component': 'Dubbo', 'is_error': True, 'layer': 'RPC_FRAMEWORK', 'tags': [{'key': 'timeout.ms', 'value': '1000'}], 'logs': [{'time': '2026-03-29T09:14:12.401+08:00', 'data': [{'key': 'cause', 'value': 'Read timed out'}]}]},
    ],
    'trace-demo-20260329-003': [
        {'span_id': 0, 'parent_span_id': -1, 'service_code': 'order-service', 'service_instance_name': 'order-gray-01', 'endpoint_name': 'POST /api/orders/confirm', 'start_time': '2026-03-29T09:05:48.000+08:00', 'end_time': '2026-03-29T09:05:48.612+08:00', 'duration_ms': 612, 'type': 'Entry', 'peer': '', 'component': 'SpringMVC', 'is_error': False, 'layer': 'HTTP', 'tags': [{'key': 'release', 'value': 'gray'}], 'logs': []},
        {'span_id': 1, 'parent_span_id': 0, 'service_code': 'order-service', 'service_instance_name': 'order-gray-01', 'endpoint_name': 'OrderRepository.save', 'start_time': '2026-03-29T09:05:48.198+08:00', 'end_time': '2026-03-29T09:05:48.587+08:00', 'duration_ms': 389, 'type': 'Local', 'peer': '', 'component': 'MySQL', 'is_error': False, 'layer': 'DATABASE', 'tags': [{'key': 'db.type', 'value': 'mysql'}], 'logs': []},
    ],
    'trace-demo-20260410-005': [
        {'span_id': 0, 'parent_span_id': -1, 'service_code': 'order-service', 'service_instance_name': 'order-prod-02', 'endpoint_name': 'POST /api/orders/create', 'start_time': '2026-04-10T11:26:18.000+08:00', 'end_time': '2026-04-10T11:26:19.824+08:00', 'duration_ms': 1824, 'type': 'Entry', 'peer': '', 'component': 'SpringMVC', 'is_error': True, 'layer': 'HTTP', 'tags': [{'key': 'http.method', 'value': 'POST'}, {'key': 'http.status_code', 'value': '500'}, {'key': 'environment', 'value': 'prod'}], 'logs': [{'time': '2026-04-10T11:26:19.801+08:00', 'data': [{'key': 'error.kind', 'value': 'TimeoutException'}, {'key': 'message', 'value': 'inventory-service request timed out'}]}]},
        {'span_id': 1, 'parent_span_id': 0, 'service_code': 'inventory-service', 'service_instance_name': 'inventory-prod-01', 'endpoint_name': 'GET /api/stock/check', 'start_time': '2026-04-10T11:26:18.114+08:00', 'end_time': '2026-04-10T11:26:19.795+08:00', 'duration_ms': 1681, 'type': 'Exit', 'peer': 'inventory-service:8080', 'component': 'SpringMVC', 'is_error': True, 'layer': 'RPC_FRAMEWORK', 'tags': [{'key': 'environment', 'value': 'prod'}, {'key': 'timeout.ms', 'value': '1500'}], 'logs': [{'time': '2026-04-10T11:26:19.795+08:00', 'data': [{'key': 'cause', 'value': 'Read timed out'}]}]},
    ],
    'trace-demo-20260329-004': [
        {'span_id': 0, 'parent_span_id': -1, 'service_code': 'member-service', 'service_instance_name': 'member-prod-01', 'endpoint_name': 'GET /api/members/{id}/profile', 'start_time': '2026-03-29T08:57:03.000+08:00', 'end_time': '2026-03-29T08:57:03.318+08:00', 'duration_ms': 318, 'type': 'Entry', 'peer': '', 'component': 'SpringMVC', 'is_error': False, 'layer': 'HTTP', 'tags': [{'key': 'cache.hit', 'value': 'true'}], 'logs': []},
        {'span_id': 1, 'parent_span_id': 0, 'service_code': 'member-service', 'service_instance_name': 'member-prod-01', 'endpoint_name': 'Redis GET member:profile', 'start_time': '2026-03-29T08:57:03.021+08:00', 'end_time': '2026-03-29T08:57:03.057+08:00', 'duration_ms': 36, 'type': 'Exit', 'peer': 'redis-member-01:6379', 'component': 'Jedis', 'is_error': False, 'layer': 'CACHE', 'tags': [{'key': 'cache.hit', 'value': 'true'}], 'logs': []},
    ],
}


class ObservabilityError(Exception):
    def __init__(self, message, status_code=status.HTTP_400_BAD_REQUEST, detail=None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or {}


def _observability_defaults():
    return getattr(settings, 'OBSERVABILITY_CONFIG', {}) or {}


def _provider_config(defaults, key, endpoint_keys=None):
    config = dict(defaults.get(key, {}))
    config.setdefault('provider', key)
    config.setdefault('enabled', False if key != 'skywalking' else True)
    config.setdefault('demo_mode', True)
    for endpoint_key in endpoint_keys or []:
        config.setdefault(endpoint_key, '')
    return config


def tracing_provider_defaults():
    defaults = _observability_defaults()
    return {
        'skywalking': {
            'ui_url': defaults.get('skywalking', {}).get('ui_url', ''),
            'oap_url': defaults.get('skywalking', {}).get('oap_url', ''),
            'graphql_path': defaults.get('skywalking', {}).get('graphql_path', '/graphql'),
            'default_layer': defaults.get('skywalking', {}).get('default_layer', ''),
            'demo_mode': defaults.get('skywalking', {}).get('demo_mode', True),
        },
        'tempo': {
            'ui_url': defaults.get('tempo', {}).get('ui_url', ''),
            'query_url': defaults.get('tempo', {}).get('query_url', ''),
            'demo_mode': defaults.get('tempo', {}).get('demo_mode', True),
        },
        'jaeger': {
            'ui_url': defaults.get('jaeger', {}).get('ui_url', ''),
            'query_url': defaults.get('jaeger', {}).get('query_url', ''),
            'demo_mode': defaults.get('jaeger', {}).get('demo_mode', True),
        },
        'zipkin': {
            'ui_url': defaults.get('zipkin', {}).get('ui_url', ''),
            'query_url': defaults.get('zipkin', {}).get('query_url', ''),
            'demo_mode': defaults.get('zipkin', {}).get('demo_mode', True),
        },
    }


def _public_config(config):
    masked = {}
    is_demo = bool((config or {}).get('demo_mode'))
    for key, value in (config or {}).items():
        if key in TRACING_SENSITIVE_KEYS and not is_demo:
            masked[key] = 'configured' if value else ''
        else:
            masked[key] = value
    return masked


def tracing_provider_info():
    defaults = tracing_provider_defaults()
    return [
        {
            'id': 'skywalking',
            'name': PROVIDER_LABELS['skywalking'],
            'description': '通过 SkyWalking OAP GraphQL 查询服务、Trace、Span 与全局拓扑。',
            'configured': bool(defaults['skywalking'].get('oap_url')),
            'defaults': _public_config(defaults['skywalking']),
        },
        {
            'id': 'tempo',
            'name': PROVIDER_LABELS['tempo'],
            'description': '对接 Tempo 查询接口，兼容 OpenTelemetry 采集数据。',
            'configured': bool(defaults['tempo'].get('query_url')),
            'defaults': _public_config(defaults['tempo']),
        },
        {
            'id': 'jaeger',
            'name': PROVIDER_LABELS['jaeger'],
            'description': '对接 Jaeger Query API，兼容 OpenTelemetry 与 Jaeger 原生链路。',
            'configured': bool(defaults['jaeger'].get('query_url')),
            'defaults': _public_config(defaults['jaeger']),
        },
        {
            'id': 'zipkin',
            'name': PROVIDER_LABELS['zipkin'],
            'description': '对接 Zipkin v2 API，统一展示 Span 与 Trace 详情。',
            'configured': bool(defaults['zipkin'].get('query_url')),
            'defaults': _public_config(defaults['zipkin']),
        },
    ]


def get_tracing_provider_configs():
    defaults = _observability_defaults()
    configs = {
        'skywalking': _provider_config(defaults, 'skywalking', ['ui_url', 'oap_url', 'graphql_path', 'default_layer']),
        'tempo': _provider_config(defaults, 'tempo', ['ui_url', 'query_url']),
        'jaeger': _provider_config(defaults, 'jaeger', ['ui_url', 'query_url']),
        'zipkin': _provider_config(defaults, 'zipkin', ['ui_url', 'query_url']),
    }
    configs['skywalking'].setdefault('graphql_path', '/graphql')
    configs['skywalking'].setdefault('default_layer', '')

    try:
        from .models import TracingDataSource

        querysets = {}
        for datasource in TracingDataSource.objects.filter(is_enabled=True).order_by('-is_default', 'name'):
            querysets.setdefault(datasource.provider, datasource)
        for provider_id, datasource in querysets.items():
            if provider_id not in configs:
                continue
            config = {**configs[provider_id], **(datasource.config or {})}
            config['provider'] = provider_id
            config['enabled'] = True
            config['datasource_id'] = datasource.id
            config['datasource_name'] = datasource.name
            config['description'] = datasource.description
            configs[provider_id] = config
    except Exception:
        pass

    return configs


def _default_provider_id():
    defaults = _observability_defaults()
    tracing_defaults = defaults.get('tracing', {}) if isinstance(defaults.get('tracing'), dict) else {}
    requested = tracing_defaults.get('default_provider') or 'skywalking'
    configs = get_tracing_provider_configs()
    if requested in configs and configs[requested].get('enabled'):
        return requested
    for candidate in ('skywalking', 'tempo', 'jaeger', 'zipkin'):
        if configs[candidate].get('enabled'):
            return candidate
    return 'demo'


def _resolve_provider(provider='', datasource_id=None):
    configs = get_tracing_provider_configs()
    datasource_id = str(datasource_id or '').strip()
    if datasource_id:
        try:
            from .models import TracingDataSource

            datasource = TracingDataSource.objects.get(pk=datasource_id, is_enabled=True)
            resolved_provider = datasource.provider
            if provider and provider not in ('demo', resolved_provider):
                raise ObservabilityError('provider 与链路数据源类型不一致', status.HTTP_400_BAD_REQUEST)
            config = {**configs.get(resolved_provider, {}), **(datasource.config or {})}
            config['provider'] = resolved_provider
            config['enabled'] = True
            config['datasource_id'] = datasource.id
            config['datasource_name'] = datasource.name
            config['description'] = datasource.description
            if resolved_provider == 'skywalking':
                config.setdefault('graphql_path', '/graphql')
                config.setdefault('default_layer', '')
            return resolved_provider, config
        except ObservabilityError:
            raise
        except Exception as exc:
            raise ObservabilityError('链路数据源不存在或已停用', status.HTTP_404_NOT_FOUND, {'detail': str(exc)}) from exc

    provider = (provider or '').strip().lower()
    if provider == 'demo':
        return 'demo', {'provider': 'demo', 'enabled': True, 'demo_mode': True}
    if provider and provider in configs and configs[provider].get('enabled'):
        return provider, configs[provider]
    default_provider = _default_provider_id()
    if default_provider in configs:
        return default_provider, configs[default_provider]
    return 'demo', {'provider': 'demo', 'enabled': True, 'demo_mode': True}


def _join_base_url(base, path=''):
    base = (base or '').rstrip('/')
    path = (path or '').strip()
    if not base:
        return ''
    if not path:
        return base
    if not path.startswith('/'):
        path = f'/{path}'
    return f'{base}{path}'


def _skywalking_graphql_url(config):
    base = (config.get('oap_url') or '').rstrip('/')
    graphql_path = config.get('graphql_path') or '/graphql'
    if not base:
        return ''
    if base.endswith(graphql_path):
        return base
    return _join_base_url(base, graphql_path)


def _http_json(response):
    try:
        return response.json()
    except ValueError:
        return {'raw': response.text}


def _request_headers(config=None):
    headers = {}
    authorization = (config or {}).get('authorization') or ''
    if authorization:
        headers['Authorization'] = authorization
    return headers


def _http_get(url, params=None, config=None):
    if not url:
        raise ObservabilityError('链路追踪查询地址未配置', status.HTTP_400_BAD_REQUEST)
    try:
        response = http_requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers=_request_headers(config))
    except http_requests.Timeout as exc:
        raise ObservabilityError('链路追踪查询超时', status.HTTP_504_GATEWAY_TIMEOUT, {'detail': str(exc)}) from exc
    except http_requests.ConnectionError as exc:
        raise ObservabilityError('无法连接到链路追踪后端', status.HTTP_502_BAD_GATEWAY, {'detail': str(exc)}) from exc
    payload = _http_json(response)
    if response.status_code >= 400:
        raise ObservabilityError(payload.get('message') or payload.get('error') or '链路追踪查询失败', response.status_code, payload)
    return payload


def _http_post(url, payload, config=None):
    if not url:
        raise ObservabilityError('链路追踪查询地址未配置', status.HTTP_400_BAD_REQUEST)
    try:
        response = http_requests.post(url, json=payload, timeout=REQUEST_TIMEOUT, headers=_request_headers(config))
    except http_requests.Timeout as exc:
        raise ObservabilityError('链路追踪查询超时', status.HTTP_504_GATEWAY_TIMEOUT, {'detail': str(exc)}) from exc
    except http_requests.ConnectionError as exc:
        raise ObservabilityError('无法连接到链路追踪后端', status.HTTP_502_BAD_GATEWAY, {'detail': str(exc)}) from exc
    body = _http_json(response)
    if response.status_code >= 400:
        raise ObservabilityError(body.get('message') or body.get('error') or '链路追踪查询失败', response.status_code, body)
    if body.get('errors'):
        error_message = body['errors'][0].get('message') or '链路追踪查询返回错误'
        raise ObservabilityError(error_message, status.HTTP_502_BAD_GATEWAY, body)
    return body


def _provider_query_url(config):
    if config.get('provider') == 'skywalking':
        return _skywalking_graphql_url(config)
    return (config.get('query_url') or '').rstrip('/')


def _provider_is_query_ready(config):
    return bool(config.get('enabled') and _provider_query_url(config))


def _provider_meta(provider_id, config, source='demo', warning=''):
    provider_name = PROVIDER_LABELS.get(provider_id, provider_id)
    if provider_id == 'demo':
        provider_name = PROVIDER_LABELS['demo']
    if source == 'demo':
        status_text = '演示模式' if provider_id == 'demo' else f'{provider_name} 演示模式'
    else:
        status_text = f'已接入 {provider_name}'
    if warning:
        status_text = f'{status_text}，{warning}'
    return {
        'provider': provider_id,
        'provider_name': provider_name,
        'datasource_id': config.get('datasource_id'),
        'datasource_name': config.get('datasource_name') or '',
        'enabled': bool(config.get('enabled', True)),
        'configured': _provider_is_query_ready(config) if provider_id != 'demo' else True,
        'source': source,
        'status_text': status_text,
        'ui_url': config.get('ui_url') or '',
        'oap_url': config.get('oap_url') or '',
        'query_url': _provider_query_url(config),
        'embed_url': config.get('ui_url') or '',
        'warning': warning,
    }


def list_provider_metas(active_provider='', include_demo_fallback=True):
    configs = get_tracing_provider_configs()
    metas = []
    for provider_id in ('skywalking', 'tempo', 'jaeger', 'zipkin'):
        config = configs[provider_id]
        if not config.get('enabled'):
            continue
        source = provider_id if _provider_is_query_ready(config) else 'demo'
        metas.append(_provider_meta(provider_id, config, source=source))
    if include_demo_fallback:
        metas.append(_provider_meta('demo', {'enabled': True}, source='demo'))
    if not metas and include_demo_fallback:
        metas.append(_provider_meta('demo', {'enabled': True}, source='demo'))
    active = active_provider or _default_provider_id()
    return [
        {
            **item,
            'active': item['provider'] == active or (item['provider'] == 'demo' and active == 'demo'),
        }
        for item in metas
    ]


def _parse_requested_datetime(value):
    raw = str(value or '').strip()
    if not raw:
        return None
    if raw.endswith('Z'):
        raw = f"{raw[:-1]}+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _duration_window(payload_or_minutes=30):
    if isinstance(payload_or_minutes, dict):
        start = _parse_requested_datetime(payload_or_minutes.get('start_time') or payload_or_minutes.get('startTime'))
        end = _parse_requested_datetime(payload_or_minutes.get('end_time') or payload_or_minutes.get('endTime'))
        if start and end:
            if end < start:
                start, end = end, start
            if end == start:
                end = start + timedelta(minutes=5)
            return start, end
        minutes = payload_or_minutes.get('duration_minutes') or 30
    else:
        minutes = payload_or_minutes
    end = datetime.now()
    start = end - timedelta(minutes=max(5, int(minutes or 30)))
    return start, end


def _duration_strings(payload_or_minutes=30):
    start, end = _duration_window(payload_or_minutes)
    return {
        'start': start.strftime('%Y-%m-%d %H%M'),
        'end': end.strftime('%Y-%m-%d %H%M'),
        'step': 'MINUTE',
    }


def _window_micros(payload_or_minutes=30):
    start, end = _duration_window(payload_or_minutes)
    return int(start.timestamp() * 1000000), int(end.timestamp() * 1000000)


def _window_ms(payload_or_minutes=30):
    start, end = _duration_window(payload_or_minutes)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _window_seconds(payload_or_minutes=30):
    start, end = _duration_window(payload_or_minutes)
    return int(start.timestamp()), int(end.timestamp())


def _to_iso_from_ms(value):
    if value in (None, ''):
        return ''
    try:
        return datetime.fromtimestamp(float(value) / 1000).isoformat()
    except (TypeError, ValueError, OSError):
        return str(value)


def _to_iso_from_micros(value):
    if value in (None, ''):
        return ''
    try:
        return datetime.fromtimestamp(float(value) / 1000000).isoformat()
    except (TypeError, ValueError, OSError):
        return str(value)


def _to_iso_from_nanos(value):
    if value in (None, ''):
        return ''
    try:
        return datetime.fromtimestamp(float(value) / 1000000000).isoformat()
    except (TypeError, ValueError, OSError):
        return str(value)


def _parse_time_ms(value):
    if value in (None, ''):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp() * 1000)
    except ValueError:
        try:
            return int(datetime.strptime(str(value), '%Y-%m-%d %H:%M').timestamp() * 1000)
        except ValueError:
            return 0


def _normalize_tags(items):
    normalized = []
    for item in items or []:
        if isinstance(item, dict):
            if 'key' in item and 'value' in item:
                normalized.append({'key': str(item.get('key')), 'value': str(item.get('value'))})
            elif 'name' in item and 'value' in item:
                normalized.append({'key': str(item.get('name')), 'value': str(item.get('value'))})
    return normalized


def _normalize_logs(items):
    normalized = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        time_value = item.get('time') or item.get('timestamp') or item.get('timeUnixNano')
        data = item.get('data') or item.get('fields') or item.get('attributes') or []
        normalized.append({
            'time': time_value,
            'data': _normalize_tags(data),
        })
    return normalized


RUNTIME_COMPONENT_HINTS = {
    'mysql': ('MySQL', 'DB'),
    'postgres': ('PostgreSQL', 'DB'),
    'postgresql': ('PostgreSQL', 'DB'),
    'mariadb': ('MariaDB', 'DB'),
    'mongodb': ('MongoDB', 'DB'),
    'mongo': ('MongoDB', 'DB'),
    'redis': ('Redis', '中间件'),
    'jedis': ('Redis', '中间件'),
    'lettuce': ('Redis', '中间件'),
    'kafka': ('Kafka', '中间件'),
    'rocketmq': ('RocketMQ', '中间件'),
    'rabbitmq': ('RabbitMQ', '中间件'),
    'elasticsearch': ('Elasticsearch', '中间件'),
    'nacos': ('Nacos', '中间件'),
    'zookeeper': ('ZooKeeper', '中间件'),
}


def _span_tags_map(span):
    result = {}
    for item in (span.get('tags') or []) + (span.get('resource_tags') or []) + (span.get('scope_tags') or []):
        key = str(item.get('key') or '').strip()
        if key:
            result[key] = str(item.get('value') or '').strip()
    return result


def _runtime_component_from_span(span):
    tag_map = _span_tags_map(span)
    values = [
        tag_map.get('db.system'),
        tag_map.get('db.type'),
        tag_map.get('messaging.system'),
        tag_map.get('peer.service'),
        span.get('component'),
        span.get('peer'),
        span.get('endpoint_name'),
        span.get('layer'),
    ]
    text = ' '.join(str(item or '').lower() for item in values)
    for hint, (technology, component_type) in RUNTIME_COMPONENT_HINTS.items():
        if hint in text:
            peer_name = str(span.get('peer') or tag_map.get('server.address') or tag_map.get('net.peer.name') or '').split(':', 1)[0].strip()
            name = peer_name if peer_name and hint in peer_name.lower() else technology
            node_key = ''.join(char.lower() if char.isalnum() else '-' for char in name).strip('-') or hint
            return {
                'id': f'runtime:{node_key}',
                'name': name,
                'type': 'RUNTIME_COMPONENT',
                'runtime_type': component_type,
                'technology': technology,
                'layers': [component_type],
            }
    return None


def _trace_detail_from_spans(trace_id, spans):
    normalized_spans = []
    services = set()
    endpoints = set()
    error_count = 0
    min_start = None
    max_end = None

    for item in spans or []:
        duration_ms = item.get('duration_ms')
        start_time = item.get('start_time') or item.get('startTime') or ''
        end_time = item.get('end_time') or item.get('endTime') or ''
        start_ms = _parse_time_ms(start_time)
        end_ms = _parse_time_ms(end_time)
        if duration_ms is None:
            duration_ms = max(0, end_ms - start_ms)

        service_code = item.get('service_code') or item.get('serviceCode') or ''
        endpoint_name = item.get('endpoint_name') or item.get('endpointName') or ''
        if service_code:
            services.add(service_code)
        if endpoint_name:
            endpoints.add(endpoint_name)
        if item.get('is_error') or item.get('isError'):
            error_count += 1
        if start_ms:
            min_start = start_ms if min_start is None else min(min_start, start_ms)
        if end_ms:
            max_end = end_ms if max_end is None else max(max_end, end_ms)

        normalized_spans.append({
            'span_id': item.get('span_id') if item.get('span_id') is not None else item.get('spanId'),
            'parent_span_id': item.get('parent_span_id') if item.get('parent_span_id') is not None else item.get('parentSpanId'),
            'service_code': service_code,
            'service_instance_name': item.get('service_instance_name') or item.get('serviceInstanceName') or '',
            'endpoint_name': endpoint_name,
            'start_time': start_time,
            'end_time': end_time,
            'duration_ms': int(duration_ms or 0),
            'type': item.get('type') or item.get('kind') or '',
            'peer': item.get('peer') or '',
            'component': item.get('component') or '',
            'is_error': bool(item.get('is_error') if item.get('is_error') is not None else item.get('isError')),
            'layer': item.get('layer') or '',
            'tags': _normalize_tags(item.get('tags') or []),
            'resource_tags': _normalize_tags(item.get('resource_tags') or item.get('resourceTags') or []),
            'scope_tags': _normalize_tags(item.get('scope_tags') or item.get('scopeTags') or []),
            'logs': _normalize_logs(item.get('logs') or []),
        })

    return {
        'trace_id': trace_id,
        'span_count': len(normalized_spans),
        'duration_ms': max(0, (max_end or 0) - (min_start or 0)) if min_start is not None and max_end is not None else max([item['duration_ms'] for item in normalized_spans], default=0),
        'error_count': error_count,
        'services': sorted(services),
        'endpoints': sorted(endpoints),
        'spans': sorted(normalized_spans, key=lambda item: (_parse_time_ms(item['start_time']), str(item['span_id']))),
    }


def _build_topology_from_trace_details(details):
    nodes = {}
    calls = {}
    for detail in details or []:
        span_map = {str(item['span_id']): item for item in detail.get('spans') or []}
        for span in detail.get('spans') or []:
            service = span.get('service_code') or 'unknown'
            nodes.setdefault(service, {'id': service, 'name': service, 'type': 'SERVICE', 'layers': [span.get('layer') or 'UNSET']})
            runtime_component = _runtime_component_from_span(span)
            if runtime_component:
                nodes.setdefault(runtime_component['id'], runtime_component)
                call_id = f'{service}->{runtime_component["id"]}'
                calls.setdefault(call_id, {
                    'id': call_id,
                    'source': service,
                    'target': runtime_component['id'],
                    'count': 0,
                    'type': 'runtime_dependency',
                })
                calls[call_id]['count'] += 1
            parent_id = span.get('parent_span_id')
            parent = span_map.get(str(parent_id))
            if not parent:
                continue
            parent_service = parent.get('service_code') or 'unknown'
            nodes.setdefault(parent_service, {'id': parent_service, 'name': parent_service, 'type': 'SERVICE', 'layers': [parent.get('layer') or 'UNSET']})
            if parent_service == service:
                continue
            call_id = f'{parent_service}->{service}'
            calls.setdefault(call_id, {'id': call_id, 'source': parent_service, 'target': service, 'count': 0})
            calls[call_id]['count'] += 1
    return {
        'node_count': len(nodes),
        'call_count': len(calls),
        'nodes': list(nodes.values()),
        'calls': list(calls.values()),
    }

def _demo_services():
    return list(DEMO_SERVICES)


def _demo_topology():
    return {
        'node_count': 5,
        'call_count': 4,
        'nodes': [
            {'id': 'gateway-service', 'name': 'gateway-service', 'type': 'SERVICE', 'layers': ['HTTP']},
            {'id': 'order-service', 'name': 'order-service', 'type': 'SERVICE', 'layers': ['RPC_FRAMEWORK']},
            {'id': 'payment-service', 'name': 'payment-service', 'type': 'SERVICE', 'layers': ['RPC_FRAMEWORK']},
            {'id': 'member-service', 'name': 'member-service', 'type': 'SERVICE', 'layers': ['RPC_FRAMEWORK']},
            {'id': 'inventory-service', 'name': 'inventory-service', 'type': 'SERVICE', 'layers': ['RPC_FRAMEWORK']},
        ],
        'calls': [
            {'id': 'gateway->order', 'source': 'gateway-service', 'target': 'order-service', 'count': 12},
            {'id': 'gateway->payment', 'source': 'gateway-service', 'target': 'payment-service', 'count': 9},
            {'id': 'payment->member', 'source': 'payment-service', 'target': 'member-service', 'count': 4},
            {'id': 'order->inventory', 'source': 'order-service', 'target': 'inventory-service', 'count': 3},
        ],
    }


def _demo_search_traces(payload):
    keyword = (payload.get('keyword') or '').strip().lower()
    trace_id = (payload.get('trace_id') or '').strip().lower()
    service_id = (payload.get('service_id') or '').strip()
    instance_name = (payload.get('instance_name') or '').strip().lower()
    trace_state = payload.get('trace_state') or 'ALL'
    limit = max(1, min(int(payload.get('limit') or DEFAULT_TRACE_LIMIT), 50))
    traces = []
    for item in DEMO_TRACES:
        if service_id and item['service_id'] != service_id:
            continue
        if instance_name and instance_name not in str(item.get('instance_name') or '').lower():
            continue
        if trace_state == 'ERROR' and not item['is_error']:
            continue
        if trace_state == 'SUCCESS' and item['is_error']:
            continue
        haystack = ' '.join([item['trace_id'], item['service_name'], item['summary'], *item['endpoint_names']]).lower()
        if trace_id and trace_id not in item['trace_id'].lower():
            continue
        if keyword and keyword not in haystack:
            continue
        traces.append(dict(item))
    return traces[:limit]


def _service_name_lookup(services):
    return {
        str(item.get('id') or ''): item.get('name') or item.get('short_name') or item.get('id') or ''
        for item in (services or [])
        if item.get('id')
    }


def _trace_matches_service(trace, service_id='', service_name=''):
    if not service_id and not service_name:
        return True
    return (
        str(trace.get('service_id') or '') == str(service_id or '')
        or str(trace.get('service_name') or '') == str(service_name or '')
    )


def _trace_detail_matches_instance(detail, instance_name, service_name=''):
    expected = str(instance_name or '').strip().lower()
    if not expected:
        return True
    for span in detail.get('spans') or []:
        if service_name and span.get('service_code') != service_name:
            continue
        if str(span.get('service_instance_name') or '').strip().lower() == expected:
            return True
    return False


def _trace_summary_instance_from_detail(detail, service_name=''):
    fallback = ''
    for span in detail.get('spans') or []:
        instance_name = str(span.get('service_instance_name') or '').strip()
        if not instance_name:
            continue
        if not fallback:
            fallback = instance_name
        if service_name and span.get('service_code') == service_name:
            return instance_name
    return fallback


def _collect_instance_options(traces, detail_loader=None):
    options = {}

    def add_option(instance_name, service_name='', service_id=''):
        name = str(instance_name or '').strip()
        if not name:
            return
        service_id = str(service_id or '').strip()
        key = f'{service_id or service_name}::{name}'
        current = options.get(key) or {
            'id': name,
            'name': name,
            'service_name': service_name or '',
            'service_id': service_id,
            'count': 0,
        }
        current['count'] += 1
        options[key] = current

    for trace in traces or []:
        add_option(trace.get('instance_name') or '', trace.get('service_name') or '', trace.get('service_id') or '')

    if detail_loader:
        for trace in traces or []:
            if trace.get('instance_name'):
                continue
            detail = detail_loader(trace)
            if not detail:
                continue
            for span in detail.get('spans') or []:
                add_option(span.get('service_instance_name') or '', span.get('service_code') or '', trace.get('service_id') or '')

    return sorted(
        options.values(),
        key=lambda item: (item.get('service_name') or '', item.get('name') or ''),
    )


def _demo_trace_detail(trace_id):
    if trace_id not in DEMO_TRACE_SPANS:
        raise ObservabilityError('未找到对应的演示 Trace', status.HTTP_404_NOT_FOUND)
    detail = _trace_detail_from_spans(trace_id, DEMO_TRACE_SPANS[trace_id])
    matched = next((item for item in DEMO_TRACES if item['trace_id'] == trace_id), None)
    if matched:
        detail['service_name'] = matched['service_name']
        detail['summary'] = matched['summary']
    return detail


def _normalize_services(items):
    services = []
    for item in items or []:
        layers = item.get('layers') or item.get('layer') or []
        if isinstance(layers, str):
            layers = [layers]
        services.append({
            'id': item.get('id') or item.get('name') or item.get('serviceName') or '',
            'name': item.get('name') or item.get('shortName') or item.get('serviceName') or '',
            'short_name': item.get('shortName') or item.get('name') or item.get('serviceName') or '',
            'layers': layers,
            'group': item.get('group') or '',
        })
    return [item for item in services if item['id']]


def _skywalking_query(query, variables=None, config=None):
    endpoint = _skywalking_graphql_url(config or {})
    body = _http_post(endpoint, {'query': query, 'variables': variables or {}}, config=config)
    return body.get('data') or {}


def _load_skywalking_services(config, layer=''):
    variables = {'layer': layer or None}
    queries = [
        (
            """
            query ListServices($layer: ServiceLayer) {
              listServices(layer: $layer) {
                id
                name
                shortName
                group
                layers
              }
            }
            """,
            'listServices',
        ),
        (
            """
            query ServicesByDuration($duration: Duration!) {
              getAllServices(duration: $duration) {
                id
                name
                shortName
                group
              }
            }
            """,
            'getAllServices',
        ),
    ]
    last_error = None
    for query, field in queries:
        try:
            variables_payload = {'duration': _duration_strings(60)} if field == 'getAllServices' else variables
            data = _skywalking_query(query, variables_payload, config)
            services = _normalize_services(data.get(field))
            if services:
                return services
        except ObservabilityError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return []


def _load_skywalking_topology(config):
    query = """
    query GlobalTopology($duration: Duration!) {
      getGlobalTopology(duration: $duration) {
        nodes {
          id
          name
          type
          layers
        }
        calls {
          id
          source
          target
        }
      }
    }
    """
    data = _skywalking_query(query, {'duration': _duration_strings(30)}, config).get('getGlobalTopology') or {}
    nodes = data.get('nodes') or []
    calls = data.get('calls') or []
    return {
        'node_count': len(nodes),
        'call_count': len(calls),
        'nodes': nodes,
        'calls': calls,
    }


def _load_skywalking_instances(config, service_id, service_name=''):
    if not service_id:
        return []
    queries = [
        (
            """
            query ServiceInstances($duration: Duration!, $serviceId: ID!) {
              getServiceInstances(duration: $duration, serviceId: $serviceId) {
                id
                name
              }
            }
            """,
            'getServiceInstances',
        ),
        (
            """
            query ListInstances($duration: Duration!, $serviceId: ID!) {
              listInstances(duration: $duration, serviceId: $serviceId) {
                id
                name
              }
            }
            """,
            'listInstances',
        ),
    ]
    last_error = None
    for query, field in queries:
        try:
            data = _skywalking_query(query, {'duration': _duration_strings(60), 'serviceId': service_id}, config)
            items = data.get(field) or []
            if items:
                return [
                    {
                        'id': item.get('id') or item.get('name') or '',
                        'name': item.get('name') or item.get('id') or '',
                        'service_name': service_name or '',
                        'service_id': service_id,
                        'count': 0,
                    }
                    for item in items
                    if item.get('id') or item.get('name')
                ]
        except ObservabilityError as exc:
            last_error = exc
    if last_error and not config.get('demo_mode'):
        raise last_error
    return []


def _search_skywalking_traces(config, payload, services):
    try:
        limit = int(payload.get('limit') or DEFAULT_TRACE_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_TRACE_LIMIT
    limit = max(1, min(limit, 50))
    trace_id = (payload.get('trace_id') or '').strip()
    requested_service_id = (payload.get('service_id') or '').strip()
    default_service_id = requested_service_id or (services[0]['id'] if services and not trace_id else '')
    if not default_service_id and not trace_id:
        return []
    condition = {
        'traceId': trace_id,
        'queryDuration': _duration_strings(payload),
        'minTraceDuration': payload.get('min_duration_ms') or 0,
        'maxTraceDuration': payload.get('max_duration_ms') or 0,
        'traceState': payload.get('trace_state') or 'ALL',
        'queryOrder': 'BY_START_TIME',
        'paging': {'pageNum': 1, 'pageSize': limit},
    }
    if default_service_id:
        condition['serviceId'] = default_service_id
    query = """
    query SearchTraces($condition: TraceQueryCondition) {
      queryBasicTraces(condition: $condition) {
        traces {
          segmentId
          endpointNames
          duration
          start
          isError
          traceIds
        }
      }
    }
    """
    traces_payload = _skywalking_query(query, {'condition': condition}, config).get('queryBasicTraces') or {}
    service_name = next((item['name'] for item in services if item['id'] == condition.get('serviceId')), '')
    traces = []
    for item in traces_payload.get('traces') or []:
        trace_ids = item.get('traceIds') or []
        traces.append({
            'trace_id': trace_ids[0] if trace_ids else item.get('segmentId') or '',
            'segment_id': item.get('segmentId') or '',
            'service_id': condition.get('serviceId', ''),
            'service_name': service_name,
            'instance_name': '',
            'endpoint_names': item.get('endpointNames') or [],
            'duration_ms': item.get('duration') or 0,
            'start': item.get('start') or '',
            'is_error': bool(item.get('isError')),
            'state': 'ERROR' if item.get('isError') else 'SUCCESS',
            'summary': '',
            'source_provider': 'skywalking',
        })
    return traces


def _load_skywalking_trace_detail(config, trace_id):
    query = """
    query TraceDetail($traceId: ID!) {
      queryTrace(traceId: $traceId) {
        spans {
          traceId
          segmentId
          spanId
          parentSpanId
          serviceCode
          serviceInstanceName
          startTime
          endTime
          endpointName
          type
          peer
          component
          isError
          layer
          tags {
            key
            value
          }
          logs {
            time
            data {
              key
              value
            }
          }
        }
      }
    }
    """
    data = _skywalking_query(query, {'traceId': trace_id}, config).get('queryTrace') or {}
    spans = []
    for item in data.get('spans') or []:
        spans.append({
            'span_id': item.get('spanId'),
            'parent_span_id': item.get('parentSpanId'),
            'service_code': item.get('serviceCode') or '',
            'service_instance_name': item.get('serviceInstanceName') or '',
            'endpoint_name': item.get('endpointName') or '',
            'start_time': _to_iso_from_ms(item.get('startTime')),
            'end_time': _to_iso_from_ms(item.get('endTime')),
            'duration_ms': max(0, int(item.get('endTime') or 0) - int(item.get('startTime') or 0)),
            'type': item.get('type') or '',
            'peer': item.get('peer') or '',
            'component': item.get('component') or '',
            'is_error': bool(item.get('isError')),
            'layer': item.get('layer') or '',
            'tags': item.get('tags') or [],
            'logs': item.get('logs') or [],
        })
    return _trace_detail_from_spans(trace_id, spans)


def _jaeger_base(config, path=''):
    return _join_base_url(config.get('query_url') or '', path)


def _jaeger_process_service(trace, span):
    processes = trace.get('processes') or {}
    process = processes.get(span.get('processID') or '') or {}
    return process.get('serviceName') or ''


def _tags_to_map(items):
    result = {}
    for item in _normalize_tags(items):
        result[item['key']] = item['value']
    return result


def _truthy(value):
    return str(value).lower() in {'1', 'true', 'yes', 'error'}


def _jaeger_span_error(span):
    tags = _tags_to_map(span.get('tags') or [])
    if _truthy(tags.get('error')):
        return True
    status_code = tags.get('http.status_code') or tags.get('status.code') or ''
    return str(status_code).isdigit() and int(status_code) >= 500


def _jaeger_trace_summary(trace, preferred_service=''):
    spans = trace.get('spans') or []
    if not spans:
        raise ObservabilityError('Jaeger 未返回可用 Span 数据', status.HTTP_502_BAD_GATEWAY)
    earliest = min(spans, key=lambda item: item.get('startTime', 0))
    latest_end = max((int(item.get('startTime') or 0) + int(item.get('duration') or 0)) for item in spans)
    service_name = preferred_service or _jaeger_process_service(trace, earliest)
    endpoint_name = earliest.get('operationName') or ''
    is_error = any(_jaeger_span_error(item) for item in spans)
    return {
        'trace_id': trace.get('traceID') or '',
        'segment_id': '',
        'service_id': service_name,
        'service_name': service_name,
        'instance_name': '',
        'endpoint_names': [endpoint_name] if endpoint_name else [],
        'duration_ms': max(0, int((latest_end - int(earliest.get('startTime') or 0)) / 1000)),
        'start': _to_iso_from_micros(earliest.get('startTime')),
        'is_error': is_error,
        'state': 'ERROR' if is_error else 'SUCCESS',
        'summary': '',
        'source_provider': 'jaeger',
    }


def _load_jaeger_services(config):
    payload = _http_get(_jaeger_base(config, '/api/services'), config=config)
    items = payload.get('data') if isinstance(payload, dict) else payload
    return _normalize_services([{'id': item, 'name': item, 'shortName': item, 'layers': ['OTEL']} for item in items or []])


def _search_jaeger_traces(config, payload, services):
    trace_id = (payload.get('trace_id') or '').strip()
    if trace_id:
        detail = _load_jaeger_trace_detail(config, trace_id)
        matched = next((item for item in services if item['name'] == detail.get('service_name')), None)
        return [{
            'trace_id': detail['trace_id'],
            'segment_id': '',
            'service_id': matched['id'] if matched else detail.get('service_name') or '',
            'service_name': detail.get('service_name') or '',
            'instance_name': '',
            'endpoint_names': detail.get('endpoints') or [],
            'duration_ms': detail.get('duration_ms') or 0,
            'start': min([span.get('start_time') for span in detail.get('spans') or [] if span.get('start_time')], default=''),
            'is_error': bool(detail.get('error_count')),
            'state': 'ERROR' if detail.get('error_count') else 'SUCCESS',
            'summary': '',
            'source_provider': 'jaeger',
        }]

    start, end = _window_micros(payload)
    params = {
        'service': payload.get('service_id') or '',
        'start': start,
        'end': end,
        'limit': max(1, min(int(payload.get('limit') or DEFAULT_TRACE_LIMIT), 50)),
    }
    if payload.get('min_duration_ms'):
        params['minDuration'] = f"{int(payload['min_duration_ms'])}ms"
    if payload.get('keyword'):
        params['operation'] = payload['keyword']
    raw = _http_get(_jaeger_base(config, '/api/traces'), params=params, config=config)
    traces = raw.get('data') or []
    items = [_jaeger_trace_summary(item, preferred_service=params['service']) for item in traces]
    trace_state = payload.get('trace_state') or 'ALL'
    if trace_state == 'ERROR':
        items = [item for item in items if item['is_error']]
    elif trace_state == 'SUCCESS':
        items = [item for item in items if not item['is_error']]
    return items


def _load_jaeger_trace_detail(config, trace_id):
    raw = _http_get(_jaeger_base(config, f'/api/traces/{trace_id}'), config=config)
    traces = raw.get('data') or []
    trace = traces[0] if traces else None
    if not trace:
        raise ObservabilityError('未找到对应的 Jaeger Trace', status.HTTP_404_NOT_FOUND)

    spans = []
    for item in trace.get('spans') or []:
        tags = _normalize_tags(item.get('tags') or [])
        tag_map = _tags_to_map(tags)
        process = (trace.get('processes') or {}).get(item.get('processID') or '') or {}
        process_tags = _normalize_tags(process.get('tags') or [])
        references = item.get('references') or []
        parent_ref = next((entry for entry in references if entry.get('refType') == 'CHILD_OF'), None)
        service_name = process.get('serviceName') or _jaeger_process_service(trace, item)
        resource_tags = _merge_tags(
            [{'key': 'service.name', 'value': service_name}] if service_name else [],
            process_tags,
        )
        peer = tag_map.get('peer.address') or tag_map.get('http.url') or tag_map.get('db.instance') or ''
        layer = 'HTTP'
        if tag_map.get('db.system'):
            layer = 'DATABASE'
        elif tag_map.get('messaging.system'):
            layer = 'MQ'
        elif tag_map.get('rpc.system'):
            layer = 'RPC_FRAMEWORK'
        spans.append({
            'span_id': item.get('spanID'),
            'parent_span_id': parent_ref.get('spanID') if parent_ref else '',
            'service_code': service_name,
            'service_instance_name': '',
            'endpoint_name': item.get('operationName') or '',
            'start_time': _to_iso_from_micros(item.get('startTime')),
            'end_time': _to_iso_from_micros(int(item.get('startTime') or 0) + int(item.get('duration') or 0)),
            'duration_ms': int(int(item.get('duration') or 0) / 1000),
            'type': tag_map.get('span.kind') or 'Span',
            'peer': peer,
            'component': tag_map.get('component') or tag_map.get('otel.library.name') or '',
            'is_error': _jaeger_span_error(item),
            'layer': layer,
            'tags': tags,
            'resource_tags': resource_tags,
            'logs': [
                {
                    'time': _to_iso_from_micros(log.get('timestamp')),
                    'data': _normalize_tags(log.get('fields') or []),
                }
                for log in item.get('logs') or []
            ],
        })
    detail = _trace_detail_from_spans(trace_id, spans)
    summary = _jaeger_trace_summary(trace)
    detail['service_name'] = summary.get('service_name') or ''
    detail['summary'] = ''
    return detail

def _zipkin_base(config, path=''):
    return _join_base_url(config.get('query_url') or '', path)


def _zipkin_span_error(span):
    tags = span.get('tags') or {}
    if _truthy(tags.get('error')):
        return True
    status_code = tags.get('http.status_code') or tags.get('otel.status_code') or ''
    return str(status_code).isdigit() and int(status_code) >= 500


def _zipkin_service_name(span):
    return ((span.get('localEndpoint') or {}).get('serviceName') or '')


def _load_zipkin_services(config):
    payload = _http_get(_zipkin_base(config, '/api/v2/services'), config=config)
    items = payload if isinstance(payload, list) else payload.get('data') or []
    return _normalize_services([{'id': item, 'name': item, 'shortName': item, 'layers': ['OTEL']} for item in items or []])


def _zipkin_trace_summary(trace):
    if not trace:
        raise ObservabilityError('Zipkin 未返回可用 Span 数据', status.HTTP_502_BAD_GATEWAY)
    spans = trace if isinstance(trace, list) else [trace]
    earliest = min(spans, key=lambda item: item.get('timestamp', 0))
    latest_end = max((int(item.get('timestamp') or 0) + int(item.get('duration') or 0)) for item in spans)
    service_name = _zipkin_service_name(earliest)
    is_error = any(_zipkin_span_error(item) for item in spans)
    return {
        'trace_id': earliest.get('traceId') or '',
        'segment_id': '',
        'service_id': service_name,
        'service_name': service_name,
        'instance_name': '',
        'endpoint_names': [earliest.get('name')] if earliest.get('name') else [],
        'duration_ms': max(0, int((latest_end - int(earliest.get('timestamp') or 0)) / 1000)),
        'start': _to_iso_from_micros(earliest.get('timestamp')),
        'is_error': is_error,
        'state': 'ERROR' if is_error else 'SUCCESS',
        'summary': '',
        'source_provider': 'zipkin',
    }


def _search_zipkin_traces(config, payload, services):
    trace_id = (payload.get('trace_id') or '').strip()
    if trace_id:
        detail = _load_zipkin_trace_detail(config, trace_id)
        return [{
            'trace_id': detail['trace_id'],
            'segment_id': '',
            'service_id': detail.get('service_name') or '',
            'service_name': detail.get('service_name') or '',
            'instance_name': '',
            'endpoint_names': detail.get('endpoints') or [],
            'duration_ms': detail.get('duration_ms') or 0,
            'start': min([span.get('start_time') for span in detail.get('spans') or [] if span.get('start_time')], default=''),
            'is_error': bool(detail.get('error_count')),
            'state': 'ERROR' if detail.get('error_count') else 'SUCCESS',
            'summary': '',
            'source_provider': 'zipkin',
        }]

    start_ms, end_ms = _window_ms(payload)
    lookback = max(5 * 60 * 1000, end_ms - start_ms)
    params = {
        'serviceName': payload.get('service_id') or '',
        'lookback': lookback,
        'endTs': end_ms,
        'limit': max(1, min(int(payload.get('limit') or DEFAULT_TRACE_LIMIT), 50)),
    }
    if payload.get('keyword'):
        params['spanName'] = payload['keyword']
    raw = _http_get(_zipkin_base(config, '/api/v2/traces'), params=params, config=config)
    traces = raw if isinstance(raw, list) else raw.get('data') or []
    items = [_zipkin_trace_summary(item) for item in traces]
    trace_state = payload.get('trace_state') or 'ALL'
    if trace_state == 'ERROR':
        items = [item for item in items if item['is_error']]
    elif trace_state == 'SUCCESS':
        items = [item for item in items if not item['is_error']]
    return items


def _load_zipkin_trace_detail(config, trace_id):
    raw = _http_get(_zipkin_base(config, f'/api/v2/trace/{trace_id}'), config=config)
    trace = raw if isinstance(raw, list) else raw.get('data') or []
    if not trace:
        raise ObservabilityError('未找到对应的 Zipkin Trace', status.HTTP_404_NOT_FOUND)
    spans = []
    for item in trace:
        tags = [{'key': key, 'value': value} for key, value in (item.get('tags') or {}).items()]
        tag_map = _tags_to_map(tags)
        peer = ((item.get('remoteEndpoint') or {}).get('serviceName') or tag_map.get('peer.service') or '')
        layer = 'HTTP'
        if tag_map.get('db.system'):
            layer = 'DATABASE'
        elif tag_map.get('messaging.system'):
            layer = 'MQ'
        elif item.get('kind') in {'CLIENT', 'PRODUCER', 'CONSUMER'}:
            layer = 'RPC_FRAMEWORK'
        spans.append({
            'span_id': item.get('id'),
            'parent_span_id': item.get('parentId') or '',
            'service_code': _zipkin_service_name(item),
            'service_instance_name': '',
            'endpoint_name': item.get('name') or '',
            'start_time': _to_iso_from_micros(item.get('timestamp')),
            'end_time': _to_iso_from_micros(int(item.get('timestamp') or 0) + int(item.get('duration') or 0)),
            'duration_ms': int(int(item.get('duration') or 0) / 1000),
            'type': item.get('kind') or 'Span',
            'peer': peer,
            'component': tag_map.get('component') or tag_map.get('db.system') or '',
            'is_error': _zipkin_span_error(item),
            'layer': layer,
            'tags': tags,
            'logs': [
                {
                    'time': _to_iso_from_micros(entry.get('timestamp')),
                    'data': [{'key': 'annotation', 'value': entry.get('value') or ''}],
                }
                for entry in item.get('annotations') or []
            ],
        })
    detail = _trace_detail_from_spans(trace_id, spans)
    summary = _zipkin_trace_summary(trace)
    detail['service_name'] = summary.get('service_name') or ''
    detail['summary'] = ''
    return detail


def _tempo_base(config, path=''):
    return _join_base_url(config.get('query_url') or '', path)


def _otlp_value(value):
    if not isinstance(value, dict):
        return value
    if 'value' in value:
        return _otlp_value(value.get('value'))
    for key in ('stringValue', 'intValue', 'doubleValue', 'boolValue', 'bytesValue', 'string_value', 'int_value', 'double_value', 'bool_value', 'bytes_value'):
        if key in value:
            return value[key]
    array_value = value.get('arrayValue') or value.get('array_value')
    if array_value:
        values = array_value.get('values') or []
        return ','.join(str(_otlp_value(item)) for item in values)
    kvlist_value = value.get('kvlistValue') or value.get('kvlist_value')
    if kvlist_value:
        values = kvlist_value.get('values') or []
        return ','.join(f"{item.get('key')}={_otlp_value(item.get('value') or {})}" for item in values)
    return ''


def _otlp_attributes(items):
    normalized = []
    if isinstance(items, dict):
        items = [{'key': key, 'value': value} for key, value in items.items()]
    for item in items or []:
        if not isinstance(item, dict):
            continue
        key = item.get('key')
        if not key:
            continue
        raw_value = item.get('value') if 'value' in item else {}
        normalized.append({'key': str(key), 'value': str(_otlp_value(raw_value))})
    return normalized


def _otlp_attribute_map(items):
    result = {}
    for item in _otlp_attributes(items):
        result[item['key']] = item['value']
    return result


def _merge_tags(*tag_groups):
    merged = []
    seen = set()
    for group in tag_groups:
        for item in _normalize_tags(group or []):
            key = item.get('key')
            if not key or key in seen:
                continue
            merged.append(item)
            seen.add(key)
    return merged


def _tempo_parse_search_traces(payload):
    if isinstance(payload, list):
        return payload
    for key in ('traces', 'data', 'results'):
        if isinstance(payload.get(key), list):
            return payload.get(key) or []
    return []


def _tempo_trace_summary(item):
    duration_ms = item.get('durationMs')
    if duration_ms is None and item.get('durationNano') is not None:
        duration_ms = int(int(item.get('durationNano')) / 1000000)
    if duration_ms is None and item.get('duration_ms') is not None:
        duration_ms = int(item.get('duration_ms'))
    start = item.get('startTimeUnixNano') or item.get('start_time_unix_nano')
    service_name = item.get('rootServiceName') or item.get('serviceName') or item.get('service_name') or ''
    endpoint_name = item.get('rootTraceName') or item.get('name') or item.get('spanName') or ''
    status_value = str(item.get('status') or item.get('statusCode') or '').upper()
    is_error = 'ERROR' in status_value or _truthy(item.get('error'))
    return {
        'trace_id': item.get('traceID') or item.get('traceId') or item.get('trace_id') or '',
        'segment_id': '',
        'service_id': service_name,
        'service_name': service_name,
        'instance_name': '',
        'endpoint_names': [endpoint_name] if endpoint_name else [],
        'duration_ms': int(duration_ms or 0),
        'start': _to_iso_from_nanos(start) if start else (item.get('startTime') or item.get('start') or ''),
        'is_error': is_error,
        'state': 'ERROR' if is_error else 'SUCCESS',
        'summary': '',
        'source_provider': 'tempo',
    }


def _tempo_layer_from_attrs(attributes):
    if attributes.get('db.system'):
        return 'DATABASE'
    if attributes.get('messaging.system'):
        return 'MQ'
    if attributes.get('rpc.system'):
        return 'RPC_FRAMEWORK'
    if attributes.get('http.method') or attributes.get('http.route') or attributes.get('url.path'):
        return 'HTTP'
    if attributes.get('cache.system'):
        return 'CACHE'
    return 'UNSET'


def _tempo_component_from_attrs(attributes):
    return (
        attributes.get('db.system')
        or attributes.get('rpc.system')
        or attributes.get('messaging.system')
        or attributes.get('http.scheme')
        or attributes.get('net.transport')
        or ''
    )


def _tempo_peer_from_attrs(attributes):
    host = attributes.get('peer.service') or attributes.get('server.address') or attributes.get('net.peer.name') or ''
    port = attributes.get('server.port') or attributes.get('net.peer.port') or ''
    return f'{host}:{port}' if host and port else host


def _tempo_status_is_error(status_obj):
    code = status_obj.get('code') if isinstance(status_obj, dict) else status_obj
    if isinstance(code, str):
        return 'ERROR' in code.upper()
    return int(code or 0) == 2


def _tempo_flatten_trace(raw):
    batches = raw.get('batches') or raw.get('resourceSpans') or raw.get('data') or []
    spans = []
    for resource_span in batches:
        resource = resource_span.get('resource') or {}
        resource_attr_items = _merge_tags(
            _otlp_attributes(resource.get('attributes') or {}),
            _normalize_tags(resource.get('tags') or []),
            _normalize_tags(resource_span.get('tags') or []),
        )
        resource_attrs = {item['key']: item['value'] for item in resource_attr_items}
        scope_spans = resource_span.get('scopeSpans') or resource_span.get('instrumentationLibrarySpans') or []
        for scope in scope_spans:
            scope_meta = scope.get('scope') or scope.get('instrumentationLibrary') or {}
            scope_tags = []
            if scope_meta.get('name'):
                scope_tags.append({'key': 'telemetry.scope.name', 'value': scope_meta.get('name')})
            if scope_meta.get('version'):
                scope_tags.append({'key': 'telemetry.scope.version', 'value': scope_meta.get('version')})
            scope_tags.extend(_otlp_attributes(scope_meta.get('attributes') or []))
            for span in scope.get('spans') or []:
                span_attrs = _otlp_attributes(span.get('attributes') or [])
                span_attr_map = _otlp_attribute_map(span.get('attributes') or [])
                service_name = resource_attrs.get('service.name') or span_attr_map.get('service.name') or ''
                effective_resource_tags = resource_attr_items
                if service_name and 'service.name' not in resource_attrs:
                    effective_resource_tags = _merge_tags([{'key': 'service.name', 'value': service_name}], resource_attr_items)
                logs = []
                for event in span.get('events') or []:
                    logs.append({
                        'time': _to_iso_from_nanos(event.get('timeUnixNano')),
                        'data': [{'key': 'event', 'value': event.get('name') or ''}, *_otlp_attributes(event.get('attributes') or [])],
                    })
                is_error = _tempo_status_is_error(span.get('status') or {}) or any(entry.get('name') == 'exception' for entry in span.get('events') or [])
                spans.append({
                    'span_id': span.get('spanId') or '',
                    'parent_span_id': span.get('parentSpanId') or '',
                    'service_code': service_name,
                    'service_instance_name': resource_attrs.get('service.instance.id') or '',
                    'endpoint_name': span.get('name') or '',
                    'start_time': _to_iso_from_nanos(span.get('startTimeUnixNano')),
                    'end_time': _to_iso_from_nanos(span.get('endTimeUnixNano')),
                    'duration_ms': int(max(0, (int(span.get('endTimeUnixNano') or 0) - int(span.get('startTimeUnixNano') or 0))) / 1000000),
                    'type': span.get('kind') or 'Span',
                    'peer': _tempo_peer_from_attrs(span_attr_map),
                    'component': _tempo_component_from_attrs(span_attr_map),
                    'is_error': is_error,
                    'layer': _tempo_layer_from_attrs(span_attr_map),
                    'tags': span_attrs,
                    'resource_tags': effective_resource_tags,
                    'scope_tags': scope_tags,
                    'logs': logs,
                })
    return spans


def _load_tempo_services(config):
    endpoints = [
        '/api/search/tag/service.name/values',
        '/api/v2/search/tag/service.name/values',
    ]
    last_error = None
    for path in endpoints:
        try:
            payload = _http_get(_tempo_base(config, path), config=config)
            if isinstance(payload, list):
                items = payload
            elif isinstance(payload, dict):
                items = payload.get('tagValues') or payload.get('data') or payload.get('tags') or []
            else:
                items = []
            services = [item for item in items if item and item != 'service.name']
            if services:
                return _normalize_services([{'id': item, 'name': item, 'shortName': item, 'layers': ['OTEL']} for item in services])
        except ObservabilityError as exc:
            last_error = exc
    if last_error and not config.get('demo_mode'):
        raise last_error
    return []


def _search_tempo_traces(config, payload, services):
    trace_id = (payload.get('trace_id') or '').strip()
    if trace_id:
        detail = _load_tempo_trace_detail(config, trace_id)
        return [{
            'trace_id': detail['trace_id'],
            'segment_id': '',
            'service_id': detail.get('service_name') or '',
            'service_name': detail.get('service_name') or '',
            'instance_name': '',
            'endpoint_names': detail.get('endpoints') or [],
            'duration_ms': detail.get('duration_ms') or 0,
            'start': min([span.get('start_time') for span in detail.get('spans') or [] if span.get('start_time')], default=''),
            'is_error': bool(detail.get('error_count')),
            'state': 'ERROR' if detail.get('error_count') else 'SUCCESS',
            'summary': '',
            'source_provider': 'tempo',
        }]

    start, end = _window_seconds(payload)
    service_name = payload.get('service_id') or ''
    query = f'{{resource.service.name="{service_name}"}}' if service_name else ''
    raw = _http_get(
        _tempo_base(config, '/api/search'),
        params={
            'q': query,
            'start': start,
            'end': end,
            'limit': max(1, min(int(payload.get('limit') or DEFAULT_TRACE_LIMIT), 50)),
        },
        config=config,
    )
    items = [_tempo_trace_summary(item) for item in _tempo_parse_search_traces(raw)]
    keyword = (payload.get('keyword') or '').strip().lower()
    if keyword:
        items = [
            item for item in items
            if keyword in item['trace_id'].lower()
            or keyword in item['service_name'].lower()
            or any(keyword in endpoint.lower() for endpoint in item['endpoint_names'])
        ]
    trace_state = payload.get('trace_state') or 'ALL'
    if trace_state == 'ERROR':
        items = [item for item in items if item['is_error']]
    elif trace_state == 'SUCCESS':
        items = [item for item in items if not item['is_error']]
    return items


def _load_tempo_trace_detail(config, trace_id):
    raw = _http_get(_tempo_base(config, f'/api/traces/{trace_id}'), config=config)
    spans = _tempo_flatten_trace(raw)
    if not spans:
        raise ObservabilityError('未找到对应的 Tempo Trace', status.HTTP_404_NOT_FOUND)
    detail = _trace_detail_from_spans(trace_id, spans)
    detail['service_name'] = next((item['service_code'] for item in detail['spans'] if item.get('parent_span_id') in ('', None)), detail['services'][0] if detail['services'] else '')
    detail['summary'] = ''
    return detail

def _provider_handlers():
    return {
        'skywalking': {
            'services': _load_skywalking_services,
            'search': _search_skywalking_traces,
            'detail': _load_skywalking_trace_detail,
            'topology': _load_skywalking_topology,
        },
        'tempo': {
            'services': _load_tempo_services,
            'search': _search_tempo_traces,
            'detail': _load_tempo_trace_detail,
        },
        'jaeger': {
            'services': _load_jaeger_services,
            'search': _search_jaeger_traces,
            'detail': _load_jaeger_trace_detail,
        },
        'zipkin': {
            'services': _load_zipkin_services,
            'search': _search_zipkin_traces,
            'detail': _load_zipkin_trace_detail,
        },
    }


def test_tracing_connection(provider, config):
    provider = (provider or '').strip().lower()
    handlers = _provider_handlers()
    if provider not in handlers:
        raise ObservabilityError('不支持的链路追踪 Provider', status.HTTP_400_BAD_REQUEST)

    effective_config = dict(config or {})
    effective_config['provider'] = provider
    effective_config['enabled'] = True
    if provider == 'skywalking':
        effective_config.setdefault('graphql_path', '/graphql')
        services = handlers[provider]['services'](effective_config, layer=effective_config.get('default_layer') or '')
    else:
        services = handlers[provider]['services'](effective_config)

    return {
        'kind': 'services',
        'provider': provider,
        'items': services[:10],
        'count': len(services),
    }


def _sample_topology(provider_id, config, traces):
    handler = _provider_handlers()[provider_id]['detail']
    details = []
    for item in (traces or [])[:5]:
        trace_id = item.get('trace_id')
        if not trace_id:
            continue
        try:
            details.append(handler(config, trace_id))
        except ObservabilityError:
            continue
    return _build_topology_from_trace_details(details)


def _live_catalog(provider_id, config, layer='', service_id=''):
    handlers = _provider_handlers()[provider_id]
    if provider_id == 'skywalking':
        services = handlers['services'](config, layer=layer)
        topology = handlers['topology'](config)
    else:
        services = handlers['services'](config)
        topology = {'node_count': 0, 'call_count': 0, 'nodes': [], 'calls': []}
    effective_service_id = service_id or (services[0]['id'] if services else '')
    traces = handlers['search'](config, {'service_id': effective_service_id, 'limit': 6}, services)
    if provider_id != 'skywalking':
        topology = _sample_topology(provider_id, config, traces)
        if not topology['nodes'] and services:
            topology = {
                'node_count': len(services),
                'call_count': 0,
                'nodes': [{'id': item['name'], 'name': item['name'], 'type': 'SERVICE', 'layers': item.get('layers') or ['OTEL']} for item in services],
                'calls': [],
            }
    detail_cache = {}

    def detail_loader(trace):
        trace_id = trace.get('trace_id')
        if not trace_id:
            return None
        if trace_id not in detail_cache:
            try:
                detail_cache[trace_id] = handlers['detail'](config, trace_id)
            except ObservabilityError:
                detail_cache[trace_id] = None
        return detail_cache[trace_id]

    service_name = next((item['name'] for item in services if item.get('id') == effective_service_id), '')
    instances = _collect_instance_options(traces, detail_loader=detail_loader)
    if provider_id == 'skywalking' and effective_service_id:
        direct_instances = _load_skywalking_instances(config, effective_service_id, service_name)
        if direct_instances:
            instances = direct_instances

    return {
        'tracing': _provider_meta(provider_id, config, source=provider_id),
        'providers': list_provider_metas(active_provider=provider_id),
        'services': services,
        'instances': instances,
        'topology': topology,
        'summary': {
            'service_count': len(services),
            'trace_count': len(traces),
            'error_count': len([item for item in traces if item['is_error']]),
            'topology_nodes': topology['node_count'],
            'topology_calls': topology['call_count'],
        },
        'recent_traces': traces,
    }


def _demo_catalog(provider_id, config, warning='', service_id=''):
    services = _demo_services()
    topology = _demo_topology()
    traces = _demo_search_traces({'limit': 6, 'service_id': service_id})
    return {
        'tracing': _provider_meta(provider_id, config, source='demo', warning=warning),
        'providers': list_provider_metas(active_provider=provider_id),
        'services': services,
        'instances': _collect_instance_options(traces),
        'topology': topology,
        'summary': {
            'service_count': len(services),
            'trace_count': len(DEMO_TRACES),
            'error_count': len([item for item in DEMO_TRACES if item['is_error']]),
            'topology_nodes': topology['node_count'],
            'topology_calls': topology['call_count'],
        },
        'recent_traces': traces,
    }


def load_tracing_catalog(provider='', layer='', datasource_id='', service_id=''):
    provider_id, config = _resolve_provider(provider, datasource_id=datasource_id)
    if provider_id == 'demo':
        return _demo_catalog('demo', {'enabled': True}, service_id=service_id)
    if not _provider_is_query_ready(config):
        if config.get('demo_mode'):
            return _demo_catalog(provider_id, config, service_id=service_id)
        raise ObservabilityError(f"{PROVIDER_LABELS.get(provider_id, provider_id)} 查询地址未配置", status.HTTP_400_BAD_REQUEST)
    try:
        return _live_catalog(provider_id, config, layer=layer, service_id=service_id)
    except ObservabilityError as exc:
        if config.get('demo_mode'):
            return _demo_catalog(provider_id, config, warning=f'已回退演示数据: {exc}', service_id=service_id)
        raise


def search_tracing(payload):
    provider_id = payload.get('provider') or ''
    catalog = load_tracing_catalog(
        provider=provider_id,
        layer=payload.get('layer', ''),
        datasource_id=payload.get('datasource_id', ''),
        service_id=payload.get('service_id', ''),
    )
    active_provider = catalog['tracing']['provider']
    service_name_by_id = _service_name_lookup(catalog['services'])
    selected_service_id = payload.get('service_id') or ''
    selected_service_name = service_name_by_id.get(str(selected_service_id), '')
    if catalog['tracing']['source'] == 'demo':
        traces = _demo_search_traces(payload)
        detail_loader = None
    else:
        handlers = _provider_handlers()[active_provider]
        _, active_config = _resolve_provider(
            active_provider,
            datasource_id=payload.get('datasource_id') or catalog['tracing'].get('datasource_id') or '',
        )
        traces = handlers['search'](active_config, payload, catalog['services'])
        detail_cache = {}

        def detail_loader(trace):
            trace_id = trace.get('trace_id')
            if not trace_id:
                return None
            if trace_id not in detail_cache:
                try:
                    detail_cache[trace_id] = handlers['detail'](active_config, trace_id)
                except ObservabilityError:
                    detail_cache[trace_id] = None
            return detail_cache[trace_id]

    requested_instance_name = str(payload.get('instance_name') or '').strip()
    if requested_instance_name:
        normalized_instance_name = requested_instance_name.lower()
        filtered = []
        for trace in traces:
            summary_instance_name = str(trace.get('instance_name') or '').strip()
            if summary_instance_name and normalized_instance_name == summary_instance_name.lower():
                filtered.append(trace)
                continue
            if not detail_loader:
                continue
            detail = detail_loader(trace)
            if not detail or not _trace_detail_matches_instance(detail, requested_instance_name, service_name=selected_service_name):
                continue
            trace = dict(trace)
            trace['instance_name'] = _trace_summary_instance_from_detail(detail, service_name=selected_service_name) or summary_instance_name
            filtered.append(trace)
        traces = filtered

    instances = _collect_instance_options(traces, detail_loader=detail_loader)
    if active_provider == 'skywalking' and selected_service_id:
        _, active_config = _resolve_provider(
            active_provider,
            datasource_id=payload.get('datasource_id') or catalog['tracing'].get('datasource_id') or '',
        )
        direct_instances = _load_skywalking_instances(active_config, selected_service_id, selected_service_name)
        if direct_instances:
            merged = {
                f"{item.get('service_name', '')}::{item.get('name', '')}": dict(item)
                for item in instances
            }
            for item in direct_instances:
                key = f"{item.get('service_name', '')}::{item.get('name', '')}"
                current = merged.get(key) or dict(item)
                current['count'] = max(int(current.get('count', 0) or 0), int(item.get('count', 0) or 0))
                merged[key] = current
            instances = sorted(
                merged.values(),
                key=lambda item: (item.get('service_name') or '', item.get('name') or ''),
            )
    return {
        'tracing': catalog['tracing'],
        'providers': catalog['providers'],
        'services': catalog['services'],
        'instances': instances,
        'summary': {
            **catalog['summary'],
            'match_count': len(traces),
            'error_match_count': len([item for item in traces if item['is_error']]),
        },
        'query': {
            'provider': active_provider,
            'datasource_id': payload.get('datasource_id') or catalog['tracing'].get('datasource_id') or '',
            'service_id': payload.get('service_id') or '',
            'instance_name': requested_instance_name,
            'trace_id': payload.get('trace_id') or '',
            'keyword': payload.get('keyword') or '',
            'trace_state': payload.get('trace_state') or 'ALL',
            'duration_minutes': payload.get('duration_minutes') or 30,
            'start_time': payload.get('start_time') or payload.get('startTime') or '',
            'end_time': payload.get('end_time') or payload.get('endTime') or '',
            'limit': payload.get('limit') or DEFAULT_TRACE_LIMIT,
        },
        'traces': traces,
    }


def load_trace_detail(trace_id, provider='', layer='', datasource_id=''):
    catalog = load_tracing_catalog(provider=provider, layer=layer, datasource_id=datasource_id)
    active_provider = catalog['tracing']['provider']
    if catalog['tracing']['source'] == 'demo':
        detail = _demo_trace_detail(trace_id)
    else:
        _, active_config = _resolve_provider(
            active_provider,
            datasource_id=datasource_id or catalog['tracing'].get('datasource_id') or '',
        )
        detail = _provider_handlers()[active_provider]['detail'](active_config, trace_id)
    detail['provider'] = active_provider
    return {
        'tracing': catalog['tracing'],
        'providers': catalog['providers'],
        'trace': detail,
    }
