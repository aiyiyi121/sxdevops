import json
from collections import Counter
from datetime import timedelta
from math import ceil

from django.core.cache import cache
from django.utils import timezone

from multicloud.models import CloudCredential


WAF_REGIONS = {
    'cn-hangzhou': '中国内地',
    'ap-southeast-1': '海外地区',
}
DEFAULT_REGION = 'cn-hangzhou'
SUPPORTED_HOURS = {1, 6, 24, 72, 168, 720}
HEALTHY_RESOURCE_STATUSES = {'active', 'online', 'normal', '1'}
RULE_TYPE_FILTER_ALIASES = {
    'waf': {
        'waf', 'waf_base', 'xss', 'sqli', 'sql_injection', 'code_exec',
        'code_execution', 'cmdi', 'command_injection', 'arbitrary_file_uploading',
        'arbitrary_file_reading', 'logic_flaw',
    },
    'sqli': {'sqli', 'sql_injection'},
    'code_exec': {'code_exec', 'code_execution'},
    'cmdi': {'cmdi', 'command_injection'},
    'scanner_behavior': {'scanner_behavior', 'scanner', 'antiscan'},
    'cc_system': {'cc_system', 'cc'},
    'blacklist': {'blacklist', 'ip_blacklist'},
}


class WafServiceError(ValueError):
    pass


class WafConfigurationError(WafServiceError):
    pass


def list_waf_accounts():
    return [
        {
            'id': item.id,
            'name': item.name,
            'account_id': item.account_id,
            'account_name': item.account_name,
            'default_region': normalize_region(item.default_region),
            'owner': item.owner,
            'configured': bool(item.access_key_id and item.access_key_secret and item.is_enabled),
        }
        for item in CloudCredential.objects.filter(provider='aliyun', is_enabled=True).order_by('name')
    ]


def normalize_region(value):
    region = str(value or '').strip()
    if region in WAF_REGIONS:
        return region
    if region.startswith('cn-') and region != 'cn-hongkong':
        return 'cn-hangzhou'
    if region:
        return 'ap-southeast-1'
    return DEFAULT_REGION


def get_waf_credential(credential_id):
    queryset = CloudCredential.objects.filter(provider='aliyun', is_enabled=True)
    if credential_id not in (None, ''):
        try:
            queryset = queryset.filter(pk=int(credential_id))
        except (TypeError, ValueError) as exc:
            raise WafConfigurationError('云账号参数无效。') from exc
    credential = queryset.order_by('name').first()
    if credential is None:
        raise WafConfigurationError('未找到已启用的阿里云账号，请先在多云管理中配置账号凭据。')
    if credential.auth_mode != 'aksk' or not credential.access_key_id or not credential.access_key_secret:
        raise WafConfigurationError(f'阿里云账号“{credential.name}”未配置可用的 AK/SK 凭据。')
    return credential


def _sdk_modules():
    try:
        from alibabacloud_tea_openapi import models as open_api_models
        from alibabacloud_waf_openapi20211001 import models as waf_models
        from alibabacloud_waf_openapi20211001.client import Client as WafClient
    except ImportError as exc:
        raise WafConfigurationError('后端未安装阿里云 WAF 3.0 SDK，请安装 requirements.txt 依赖。') from exc
    return open_api_models, waf_models, WafClient


def _build_client(credential, region_id):
    open_api_models, _, client_class = _sdk_modules()
    config = open_api_models.Config(
        access_key_id=credential.access_key_id,
        access_key_secret=credential.access_key_secret,
        region_id=region_id,
        connect_timeout=10000,
        read_timeout=20000,
    )
    return client_class(config)


def _body_map(response):
    body = getattr(response, 'body', response)
    if body is None:
        return {}
    if hasattr(body, 'to_map'):
        return body.to_map()
    return body if isinstance(body, dict) else {}


def _error_message(exc):
    message = getattr(exc, 'message', '') or str(exc) or exc.__class__.__name__
    code = getattr(exc, 'code', '')
    return f'{code}: {message}' if code and code not in message else message


def _call(label, callback, warnings, fallback):
    try:
        return callback()
    except Exception as exc:
        warnings.append({'source': label, 'message': _error_message(exc)})
        return fallback


def _unix_timestamp(value):
    try:
        timestamp = int(float(value))
    except (TypeError, ValueError):
        return None
    return timestamp // 1000 if timestamp > 100000000000 else timestamp


def _range(hours, start_time=None, end_time=None):
    custom_start = _unix_timestamp(start_time)
    custom_end = _unix_timestamp(end_time)
    if custom_start is not None or custom_end is not None:
        if custom_start is None or custom_end is None:
            raise WafServiceError('自定义时间范围需要同时提供开始和结束时间。')
        now = int(timezone.now().timestamp())
        if custom_end > now + 60:
            raise WafServiceError('结束时间不能晚于当前时间。')
        if custom_start >= custom_end:
            raise WafServiceError('开始时间必须早于结束时间。')
        if custom_start < now - 30 * 24 * 3600:
            raise WafServiceError('WAF 最多支持查询最近 30 天的数据。')
        value = max(1, ceil((custom_end - custom_start) / 3600))
        interval = max(60, int(((custom_end - custom_start) / 96) / 60) * 60)
        return value, custom_start, custom_end, interval
    try:
        value = int(hours or 24)
    except (TypeError, ValueError):
        value = 24
    if value not in SUPPORTED_HOURS:
        value = 24
    end = timezone.now()
    start = end - timedelta(hours=value)
    interval = max(60, int((value * 3600) / 96 / 60) * 60)
    return value, int(start.timestamp()), int(end.timestamp()), interval


def _account_payload(credential, region_id):
    return {
        'id': credential.id,
        'name': credential.name,
        'account_id': credential.account_id,
        'account_name': credential.account_name,
        'region_id': region_id,
        'region_label': WAF_REGIONS[region_id],
    }


def _describe_instance(client, models, region_id):
    response = client.describe_instance(models.DescribeInstanceRequest(region_id=region_id))
    payload = _body_map(response)
    instance_id = str(payload.get('InstanceId') or '').strip()
    if not instance_id:
        raise WafConfigurationError('当前阿里云账号在所选区域未开通 WAF 3.0 实例。')
    details = payload.get('Details') or {}
    return {
        'instance_id': instance_id,
        'edition': payload.get('Edition') or '',
        'status': payload.get('Status'),
        'process_status': payload.get('ProcessStatus') or '',
        'pay_type': payload.get('PayType') or '',
        'in_debt': payload.get('InDebt') or '',
        'start_time': payload.get('StartTime'),
        'end_time': payload.get('EndTime'),
        'capacity': {
            'protected_object_limit': details.get('DefenseObjectMaxCount') or 0,
            'free_qps': details.get('FreeQps') or 0,
            'elastic_qps': details.get('ElasticQps') or 0,
            'log_service': bool(details.get('LogService')),
            'bot_protection': bool(details.get('Bot')),
            'ipv6': bool(details.get('Ipv6')),
        },
    }


def _normalize_resource(item):
    detail = item.get('Detail') if isinstance(item.get('Detail'), dict) else {}
    return {
        'resource': item.get('Resource') or '',
        'description': item.get('Description') or '',
        'product': item.get('Product') or '',
        'origin': item.get('ResourceOrigin') or '',
        'status': item.get('ResourceStatus') or '',
        'group': item.get('ResourceGroup') or '',
        'instance_id': item.get('InstanceId') or '',
        'created_at': item.get('GmtCreate'),
        'updated_at': item.get('GmtModified'),
        'xff_enabled': item.get('XffStatus') == 1,
        'acw_cookie_enabled': item.get('AcwCookieStatus') == 1,
        'acw_secure_enabled': item.get('AcwSecureStatus') == 1 or item.get('AcwV3SecureStatus') == 1,
        'detail': detail,
    }


def _resource_is_healthy(item):
    return str(item.get('status') or '').strip().lower() in HEALTHY_RESOURCE_STATUSES


def _describe_resources(client, models, instance_id, region_id, page=1, page_size=50, query=''):
    request = models.DescribeDefenseResourcesRequest(
        instance_id=instance_id,
        region_id=region_id,
        page_number=page,
        page_size=page_size,
        query=query or None,
    )
    payload = _body_map(client.describe_defense_resources(request))
    return {
        'total': payload.get('TotalCount') or 0,
        'page': page,
        'page_size': page_size,
        'items': [_normalize_resource(item) for item in (payload.get('Resources') or [])],
    }


def _describe_trend(client, models, instance_id, region_id, start, end, interval):
    request = models.DescribePeakTrendRequest(
        instance_id=instance_id,
        region_id=region_id,
        start_timestamp=str(start),
        end_timestamp=str(end),
        interval=str(interval),
    )
    payload = _body_map(client.describe_peak_trend(request))
    points = []
    for position, item in enumerate(payload.get('FlowChart') or []):
        attack_count = sum(int(item.get(key) or 0) for key in ('WafSum', 'CcSum', 'AclSum', 'AntiScanSum'))
        points.append({
            'timestamp': _trend_point_timestamp(item.get('Index'), start, interval, position),
            'qps': int(item.get('Count') or 0),
            'attacks': attack_count,
            'waf': int(item.get('WafSum') or 0),
            'cc': int(item.get('CcSum') or 0),
            'acl': int(item.get('AclSum') or 0),
            'anti_scan': int(item.get('AntiScanSum') or 0),
        })
    return points


def _trend_point_timestamp(index, start, interval, position):
    """WAF returns a bucket sequence for some editions and an epoch for others."""
    try:
        numeric_index = int(float(index))
    except (TypeError, ValueError):
        numeric_index = None
    if numeric_index is not None and numeric_index >= 1_000_000_000:
        return _unix_timestamp(numeric_index)
    bucket_index = numeric_index if numeric_index is not None and numeric_index >= 0 else position
    return int(start) + bucket_index * int(interval)


def _describe_top_resources(client, models, instance_id, region_id, start, end):
    request = models.DescribeRuleHitsTopResourceRequest(
        instance_id=instance_id,
        region_id=region_id,
        start_timestamp=str(start),
        end_timestamp=str(end),
    )
    payload = _body_map(client.describe_rule_hits_top_resource(request))
    return [
        {'resource': item.get('Resource') or '', 'count': int(item.get('Count') or 0)}
        for item in (payload.get('RuleHitsTopResource') or [])
    ]


def _describe_top_client_ips(client, models, instance_id, region_id, start, end):
    request = models.DescribeRuleHitsTopClientIpRequest(
        instance_id=instance_id,
        region_id=region_id,
        start_timestamp=str(start),
        end_timestamp=str(end),
    )
    payload = _body_map(client.describe_rule_hits_top_client_ip(request))
    return [
        {'client_ip': item.get('ClientIp') or '', 'count': int(item.get('Count') or 0)}
        for item in (payload.get('RuleHitsTopClientIp') or [])
    ]


def _describe_top_rule_ids(client, models, instance_id, region_id, start, end):
    request = models.DescribeRuleHitsTopRuleIdRequest(
        instance_id=instance_id,
        region_id=region_id,
        start_timestamp=str(start),
        end_timestamp=str(end),
        is_group_resource='true',
    )
    payload = _body_map(client.describe_rule_hits_top_rule_id(request))
    return [
        {
            'rule_id': item.get('RuleId') or '',
            'resource': item.get('Resource') or '',
            'count': int(item.get('Count') or 0),
        }
        for item in (payload.get('RuleHitsTopRuleId') or [])
    ]


def _base_rule_detail_cache_key(instance_id, region_id, rule_id):
    return f'cloudsecurity:waf:base-rule:{instance_id}:{region_id}:{rule_id}'


def _describe_base_rule_details(client, models, instance_id, region_id, rule_ids):
    """Return Alibaba Cloud WAF base-rule metadata without affecting event reads."""
    normalized_ids = []
    for rule_id in rule_ids:
        value = str(rule_id or '').strip()
        if value.isdigit() and value not in normalized_ids:
            normalized_ids.append(value)

    details = {}
    missing_ids = []
    for rule_id in normalized_ids:
        cached = cache.get(_base_rule_detail_cache_key(instance_id, region_id, rule_id))
        if cached:
            details[rule_id] = cached
        else:
            missing_ids.append(rule_id)

    try:
        for offset in range(0, len(missing_ids), 100):
            batch = [int(rule_id) for rule_id in missing_ids[offset:offset + 100]]
            request = models.DescribeBaseSystemRulesRequest(
                instance_id=instance_id,
                region_id=region_id,
                lang='zh',
                rule_ids=batch,
            )
            payload = _body_map(client.describe_base_system_rules(request))
            for item in payload.get('Rules') or []:
                if not isinstance(item, dict):
                    continue
                rule_id = str(item.get('RuleId') or '').strip()
                if not rule_id:
                    continue
                detail = {
                    'name': item.get('RuleName') or '',
                    'description': item.get('Description') or '',
                    'risk_level': item.get('RiskLevel') or '',
                }
                details[rule_id] = detail
                cache.set(_base_rule_detail_cache_key(instance_id, region_id, rule_id), detail, 6 * 60 * 60)
    except Exception:
        # Rule names enhance the display only. The primary WAF reads must stay available.
        return details
    return details


def _decorate_events_with_rule_details(events, rule_details):
    for event in events:
        rules = event.get('rules') or []
        for rule in rules:
            detail = rule_details.get(str(rule.get('id') or '').strip(), {})
            rule['name'] = rule.get('name') or detail.get('name') or ''
            rule['description'] = rule.get('description') or detail.get('description') or ''
            rule['risk_level'] = rule.get('risk_level') or detail.get('risk_level') or ''
        if rules:
            event['rule_name'] = event.get('rule_name') or rules[0].get('name') or ''
    return events


def _decorate_top_rule_ids(items, rule_details):
    for item in items:
        detail = rule_details.get(str(item.get('rule_id') or '').strip(), {})
        item['rule_name'] = detail.get('name') or ''
        item['rule_description'] = detail.get('description') or ''
    return items


def _describe_top_rule_types(client, models, instance_id, region_id, start, end):
    request = models.DescribeRuleHitsTopTuleTypeRequest(
        instance_id=instance_id,
        region_id=region_id,
        start_timestamp=str(start),
        end_timestamp=str(end),
    )
    payload = _body_map(client.describe_rule_hits_top_tule_type(request))
    return [
        {'rule_type': item.get('RuleType') or '', 'count': int(item.get('Count') or 0)}
        for item in (payload.get('RuleHitsTopTuleType') or [])
    ]


def _as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'enabled', 'on'}


def _describe_alarm_banner(client, models, instance_id, region_id):
    request = models.DescribeAlarmBannerRequest(instance_id=instance_id, region_id=region_id)
    payload = _body_map(client.describe_alarm_banner(request))
    banner = payload.get('BannerStatus') or {}
    return {
        'active': _as_bool(banner.get('Status')),
        'type': banner.get('Type') or '',
        'cause': banner.get('Cause') or '',
        'count': int(banner.get('Count') or 0),
    }


def _describe_log_status(client, models, instance_id, region_id, resource_items):
    resource_names = [str(item.get('resource') or '').strip() for item in resource_items]
    resource_names = [item for item in resource_names if item]
    if not resource_names:
        return {'total': 0, 'enabled': 0, 'trace_enabled': 0, 'items': []}
    request = models.DescribeResourceLogStatusRequest(
        instance_id=instance_id,
        region_id=region_id,
        resources=','.join(resource_names),
    )
    payload = _body_map(client.describe_resource_log_status(request))
    items = [
        {
            'resource': item.get('Resource') or '',
            'enabled': _as_bool(item.get('Status')),
            'trace_enabled': _as_bool(item.get('TraceStatus')),
        }
        for item in (payload.get('Result') or [])
    ]
    return {
        'total': len(items),
        'enabled': sum(1 for item in items if item['enabled']),
        'trace_enabled': sum(1 for item in items if item['trace_enabled']),
        'items': items,
    }


def _describe_upstream_response_codes(client, models, instance_id, region_id, start, end, interval):
    request = models.DescribeResponseCodeTrendGraphRequest(
        instance_id=instance_id,
        region_id=region_id,
        start_timestamp=str(start),
        end_timestamp=str(end),
        interval=str(interval),
        type='upstream',
    )
    payload = _body_map(client.describe_response_code_trend_graph(request))
    return [
        {
            'timestamp': item.get('Index'),
            '302': int(item.get('302Pv') or 0),
            '405': int(item.get('405Pv') or 0),
            '444': int(item.get('444Pv') or 0),
            '499': int(item.get('499Pv') or 0),
            '5xx': int(item.get('5xxPv') or 0),
        }
        for item in (payload.get('ResponseCodes') or [])
    ]


def get_waf_overview(credential_id=None, region_id=None, hours=24, start_time=None, end_time=None):
    credential = get_waf_credential(credential_id)
    region = normalize_region(region_id or credential.default_region)
    _, models, _ = _sdk_modules()
    client = _build_client(credential, region)
    try:
        instance = _describe_instance(client, models, region)
    except WafServiceError:
        raise
    except Exception as exc:
        raise WafServiceError(f'读取阿里云 WAF 实例失败：{_error_message(exc)}') from exc

    selected_hours, start, end, interval = _range(hours, start_time, end_time)
    warnings = []
    resources = _call(
        '防护对象',
        lambda: _describe_resources(client, models, instance['instance_id'], region, page_size=20),
        warnings,
        {'total': 0, 'page': 1, 'page_size': 20, 'items': []},
    )
    trend = _call(
        '防护趋势',
        lambda: _describe_trend(client, models, instance['instance_id'], region, start, end, interval),
        warnings,
        [],
    )
    top_resources = _call(
        '受攻击对象排行',
        lambda: _describe_top_resources(client, models, instance['instance_id'], region, start, end),
        warnings,
        [],
    )
    top_client_ips = _call(
        '攻击来源排行',
        lambda: _describe_top_client_ips(client, models, instance['instance_id'], region, start, end),
        warnings,
        [],
    )
    top_rule_ids = _call(
        '高频规则 ID',
        lambda: _describe_top_rule_ids(client, models, instance['instance_id'], region, start, end),
        warnings,
        [],
    )
    top_rule_ids = _decorate_top_rule_ids(
        top_rule_ids,
        _describe_base_rule_details(
            client, models, instance['instance_id'], region,
            [item.get('rule_id') for item in top_rule_ids],
        ),
    )
    top_rule_types = _call(
        '命中规则类型',
        lambda: _describe_top_rule_types(client, models, instance['instance_id'], region, start, end),
        warnings,
        [],
    )
    event_insights = _call(
        '攻击事件趋势与请求 URL',
        lambda: _describe_event_insights(client, models, instance['instance_id'], region, start, end, interval),
        warnings,
        {'event_count': 0, 'rule_hits_by_bucket': {}, 'top_urls': []},
    )
    trend = _apply_event_hits_to_trend(trend, event_insights)
    alarm = _call(
        '实例告警',
        lambda: _describe_alarm_banner(client, models, instance['instance_id'], region),
        warnings,
        {},
    )
    log_status = _call(
        '访问日志状态',
        lambda: _describe_log_status(client, models, instance['instance_id'], region, resources['items']),
        warnings,
        {'total': 0, 'enabled': 0, 'trace_enabled': 0, 'items': []},
    )
    upstream_response_codes = _call(
        '源站响应码趋势',
        lambda: _describe_upstream_response_codes(client, models, instance['instance_id'], region, start, end, interval),
        warnings,
        [],
    )
    return {
        'account': _account_payload(credential, region),
        'instance': instance,
        'range_hours': selected_hours,
        'summary': {
            'protected_resources': resources['total'],
            'request_peak_qps': max((item['qps'] for item in trend), default=0),
            'attack_count': sum(item['attacks'] for item in trend),
            'healthy_resources': sum(1 for item in resources['items'] if _resource_is_healthy(item)),
        },
        'trend': trend,
        'top_resources': top_resources[:10],
        'top_client_ips': top_client_ips[:10],
        'top_rule_ids': top_rule_ids[:10],
        'top_rule_types': top_rule_types[:10],
        'top_urls': event_insights['top_urls'][:10],
        'alarm': alarm,
        'log_status': log_status,
        'upstream_response_codes': upstream_response_codes,
        'warnings': warnings,
        'fetched_at': timezone.now().isoformat(),
    }


def get_waf_resources(credential_id=None, region_id=None, page=1, page_size=20, query=''):
    credential = get_waf_credential(credential_id)
    region = normalize_region(region_id or credential.default_region)
    _, models, _ = _sdk_modules()
    client = _build_client(credential, region)
    try:
        instance = _describe_instance(client, models, region)
        result = _describe_resources(client, models, instance['instance_id'], region, page, page_size, query)
    except WafServiceError:
        raise
    except Exception as exc:
        raise WafServiceError(f'读取阿里云 WAF 防护对象失败：{_error_message(exc)}') from exc
    return {**result, 'account': _account_payload(credential, region), 'fetched_at': timezone.now().isoformat()}


def _pick(item, *keys):
    for key in keys:
        if item.get(key) not in (None, ''):
            return item[key]
    return ''


def _event_value(item, *keys):
    """Read both the SDK's snake_case event payload and legacy API casing."""
    if not isinstance(item, dict):
        return ''
    return _pick(item, *keys)


def _parse_json_value(value, fallback=None):
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _normalize_event_rules(item):
    raw_rules = _parse_json_value(_event_value(item, 'terminating_rules', 'TerminatingRules'), []) or []
    rules = []
    for rule in raw_rules if isinstance(raw_rules, list) else []:
        if not isinstance(rule, dict):
            continue
        rules.append({
            'id': _event_value(rule, 'id', 'Id', 'rule_id', 'RuleId'),
            'type': _event_value(rule, 'type', 'Type', 'rule_type', 'RuleType'),
            'name': _event_value(rule, 'name', 'Name', 'rule_name', 'RuleName'),
            'description': _event_value(rule, 'description', 'Description'),
            'action': _event_value(rule, 'action', 'Action'),
            'defense_scene': _event_value(rule, 'defense_scene', 'DefenseScene'),
            'hit': _parse_json_value(_event_value(rule, 'hit', 'Hit'), _event_value(rule, 'hit', 'Hit')),
        })
    return rules


def _normalize_event(item, index):
    if not isinstance(item, dict):
        return {'id': str(index)}
    rules = _normalize_event_rules(item)
    action = rules[0]['action'] if rules else _event_value(item, 'action', 'Action', 'defense_status', 'DefenseStatus', 'block_status', 'BlockStatus')
    rule_type = rules[0]['type'] if rules else _event_value(item, 'rule_type', 'RuleType', 'protection_type', 'ProtectionType', 'attack_type', 'AttackType')
    return {
        'id': str(_event_value(item, 'event_id', 'EventId', 'EventID', 'id', 'Id', 'request_traceid', 'RequestId') or index),
        'time': _event_value(item, 'timestamp', 'Timestamp', 'event_time', 'EventTime', 'time', 'Time', 'gmt_create', 'GmtCreate'),
        'resource': _event_value(item, 'matched_host', 'MatchedHost', 'resource', 'Resource', 'domain', 'Domain', 'host', 'Host'),
        'client_ip': _event_value(item, 'real_client_ip', 'RealClientIp', 'client_ip', 'ClientIp', 'ClientIP', 'src_ip', 'SrcIp', 'source_ip', 'SourceIp'),
        'rule_type': rule_type,
        'rule_id': rules[0]['id'] if rules else _event_value(item, 'rule_id', 'RuleId', 'RuleID'),
        'rule_name': rules[0]['name'] if rules else _event_value(item, 'rule_name', 'RuleName'),
        'action': action,
        'request_method': _event_value(item, 'request_method', 'RequestMethod', 'method', 'Method'),
        'request_path': _event_value(item, 'request_path', 'RequestPath', 'url', 'Url', 'request_uri', 'RequestUri'),
        'querystring': _event_value(item, 'querystring', 'QueryString'),
        'country': _event_value(item, 'remote_country_id', 'RemoteCountryId', 'country', 'Country', 'CountryName', 'region', 'Region'),
        'region': _event_value(item, 'remote_region_id', 'RemoteRegionId'),
        'user_agent': _event_value(item, 'http_user_agent', 'HttpUserAgent', 'user_agent', 'UserAgent'),
        'referer': _event_value(item, 'http_referer', 'HttpReferer', 'referer', 'Referer'),
        'trace_id': _event_value(item, 'request_traceid', 'RequestTraceId', 'trace_id', 'TraceId'),
        'host': _event_value(item, 'host', 'Host'),
        'matched_detail': _parse_json_value(_event_value(item, 'final_defense_scene_block_detail', 'FinalDefenseSceneBlockDetail'), {}),
        'rules': rules,
    }


def _describe_security_event_records(client, models, instance_id, region_id, start, end):
    """Return every event in the selected range for consistent local aggregation."""
    date_range = models.DescribeSecurityEventLogsRequestFilterDateRange(start_date=start, end_date=end)
    request_filter = models.DescribeSecurityEventLogsRequestFilter(date_range=date_range)
    request = models.DescribeSecurityEventLogsRequest(
        instance_id=instance_id,
        region_id=region_id,
        page_number=1,
        page_size=100,
        filter=request_filter,
    )
    payload = _body_map(client.describe_security_event_logs(request))
    raw_items = list(payload.get('SecurityEventLogs') or [])
    total = int(payload.get('SecurityEventLogsTotalCount') or 0)
    for remote_page in range(2, ceil(total / 100) + 1):
        paged_request = models.DescribeSecurityEventLogsRequest(
            instance_id=instance_id,
            region_id=region_id,
            page_number=remote_page,
            page_size=100,
            filter=request_filter,
        )
        paged_payload = _body_map(client.describe_security_event_logs(paged_request))
        raw_items.extend(paged_payload.get('SecurityEventLogs') or [])

    return [_normalize_event(item, index) for index, item in enumerate(raw_items, start=1)]


def _describe_event_insights(client, models, instance_id, region_id, start, end, interval):
    """Build URL rankings and rule-hit buckets from the Attack Events data source."""
    events = _describe_security_event_records(client, models, instance_id, region_id, start, end)
    url_counts = Counter()
    rule_hits_by_bucket = Counter()
    for event in events:
        request_path = str(event.get('request_path') or '').strip()
        if request_path and request_path != '-':
            url_counts[request_path] += 1
        event_timestamp = _unix_timestamp(event.get('time'))
        if event_timestamp is None or not start <= event_timestamp <= end:
            continue
        bucket = int(start) + ((event_timestamp - int(start)) // int(interval)) * int(interval)
        rule_hits_by_bucket[bucket] += max(len(event.get('rules') or []), 1)
    return {
        'event_count': len(events),
        'rule_hits_by_bucket': dict(rule_hits_by_bucket),
        'top_urls': [
        {'url': url, 'count': count}
        for url, count in url_counts.most_common(10)
        ],
    }


def _describe_top_event_urls(client, models, instance_id, region_id, start, end):
    """Compatibility helper for callers that only need the Attack Events URL rank."""
    return _describe_event_insights(client, models, instance_id, region_id, start, end, 60)['top_urls']


def _apply_event_hits_to_trend(trend, event_insights):
    if not event_insights.get('rule_hits_by_bucket'):
        return trend
    rule_hits_by_bucket = event_insights.get('rule_hits_by_bucket') or {}
    for point in trend:
        point['attacks'] = max(
            int(point.get('attacks') or 0),
            int(rule_hits_by_bucket.get(point.get('timestamp'), 0)),
        )
    return trend


def _event_matches_filters(event, filters):
    keyword = filters.get('keyword', '').lower()
    if keyword:
        searchable = ' '.join(str(event.get(key) or '') for key in (
            'resource', 'host', 'client_ip', 'rule_type', 'rule_id', 'request_method',
            'request_path', 'querystring', 'trace_id', 'country', 'action',
        )).lower()
        if keyword not in searchable:
            return False
    for field in ('resource', 'client_ip'):
        value = filters.get(field, '').lower()
        if value and value not in str(event.get(field) or '').lower():
            return False
    for field in ('rule_type', 'action'):
        value = filters.get(field, '').lower()
        if value:
            event_value = str(event.get(field) or '').lower()
            if field == 'rule_type':
                accepted_values = RULE_TYPE_FILTER_ALIASES.get(value, {value})
                if event_value not in accepted_values:
                    return False
            elif field == 'action':
                action_aliases = {
                    'block': {'block', 'blocked', 'deny', '2'},
                    'challenge': {'challenge', 'captcha', '3'},
                    'allow': {'allow', 'pass', '0'},
                }
                if event_value not in action_aliases.get(value, {value}):
                    return False
            elif value != event_value:
                return False
    for field in ('request_url', 'rule_id'):
        value = filters.get(field, '').lower()
        if value:
            if field == 'request_url':
                request_value = ' '.join(filter(None, [str(event.get('request_path') or ''), str(event.get('querystring') or '')])).lower()
                if value not in request_value:
                    return False
            elif value not in str(event.get(field) or '').lower():
                return False
    return True


def _event_filter_values(**kwargs):
    return {
        key: str(value or '').strip()[:128]
        for key, value in kwargs.items()
    }


def get_waf_events(
    credential_id=None,
    region_id=None,
    hours=24,
    start_time=None,
    end_time=None,
    page=1,
    page_size=20,
    keyword='',
    resource='',
    client_ip='',
    rule_type='',
    action='',
    request_url='',
    rule_id='',
):
    credential = get_waf_credential(credential_id)
    region = normalize_region(region_id or credential.default_region)
    _, models, _ = _sdk_modules()
    client = _build_client(credential, region)
    selected_hours, start, end, _ = _range(hours, start_time, end_time)
    filters = _event_filter_values(
        keyword=keyword,
        resource=resource,
        client_ip=client_ip,
        rule_type=rule_type,
        action=action,
        request_url=request_url,
        rule_id=rule_id,
    )
    try:
        instance = _describe_instance(client, models, region)
        date_range = models.DescribeSecurityEventLogsRequestFilterDateRange(start_date=start, end_date=end)
        request_filter = models.DescribeSecurityEventLogsRequestFilter(date_range=date_range)
        request = models.DescribeSecurityEventLogsRequest(
            instance_id=instance['instance_id'],
            region_id=region,
            page_number=1 if any(filters.values()) else page,
            page_size=100 if any(filters.values()) else page_size,
            filter=request_filter,
        )
        payload = _body_map(client.describe_security_event_logs(request))
    except WafServiceError:
        raise
    except Exception as exc:
        raise WafServiceError(f'读取阿里云 WAF 攻击事件失败：{_error_message(exc)}') from exc
    raw_items = payload.get('SecurityEventLogs') or []
    remote_total = int(payload.get('SecurityEventLogsTotalCount') or 0)
    if any(filters.values()):
        normalized_items = [_normalize_event(item, index) for index, item in enumerate(raw_items, start=1)]
        # WAF's documented filter fields vary by edition. Normalize first so every
        # displayed filter has deterministic behavior across supported editions.
        for remote_page in range(2, ceil(remote_total / 100) + 1):
            paged_request = models.DescribeSecurityEventLogsRequest(
                instance_id=instance['instance_id'],
                region_id=region,
                page_number=remote_page,
                page_size=100,
                filter=request_filter,
            )
            paged_payload = _body_map(client.describe_security_event_logs(paged_request))
            normalized_items.extend(
                _normalize_event(item, index)
                for index, item in enumerate(paged_payload.get('SecurityEventLogs') or [], start=(remote_page - 1) * 100 + 1)
            )
        filtered_items = [item for item in normalized_items if _event_matches_filters(item, filters)]
        total = len(filtered_items)
        offset = (page - 1) * page_size
        items = filtered_items[offset:offset + page_size]
    else:
        total = remote_total
        items = [_normalize_event(item, index) for index, item in enumerate(raw_items, start=(page - 1) * page_size + 1)]
    _decorate_events_with_rule_details(
        items,
        _describe_base_rule_details(
            client, models, instance['instance_id'], region,
            [rule.get('id') for item in items for rule in item.get('rules') or []],
        ),
    )
    return {
        'account': _account_payload(credential, region),
        'range_hours': selected_hours,
        'total': total,
        'page': page,
        'page_size': page_size,
        'items': items,
        'metadata': payload.get('SecurityEventMetaData') or {},
        'fetched_at': timezone.now().isoformat(),
    }
