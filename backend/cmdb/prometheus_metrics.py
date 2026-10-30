import json
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests as http_requests


VM_METRICS = ('cpu_usage', 'memory_usage', 'disk_usage')


def _config_bool(value, default=True):
    if value is None:
        return default
    return str(value).strip().lower() not in {'0', 'false', 'no', 'off'}


def _config_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _config_value(config, *keys, default=''):
    for key in keys:
        value = (config or {}).get(key)
        if value not in (None, ''):
            return value
    return default


def _datasource_config_value(config, *keys, default=''):
    if not isinstance(config, dict):
        return default
    for key in keys:
        value = config.get(key)
        if value not in (None, ''):
            return value
    basic = config.get('prometheus.basic') if isinstance(config.get('prometheus.basic'), dict) else {}
    for key in keys:
        value = basic.get(key)
        if value not in (None, ''):
            return value
    return default


def _datasource_headers(config):
    headers = {'Accept': 'application/json'}
    configured = _datasource_config_value(config, 'headers', 'prometheus.headers', default={})
    if isinstance(configured, dict):
        for key, value in configured.items():
            header_key = str(key or '').strip()
            if header_key and value not in (None, ''):
                headers[header_key] = str(value)
    auth_type = str(_datasource_config_value(config, 'auth_type', default='none') or 'none').lower()
    bearer_token = str(_datasource_config_value(config, 'bearer_token', 'token', 'api_key', default='') or '').strip()
    if auth_type in {'bearer', 'token'} and bearer_token and 'Authorization' not in headers:
        headers['Authorization'] = f'Bearer {bearer_token}'
    return headers


def _datasource_auth(config):
    auth_type = str(_datasource_config_value(config, 'auth_type', default='none') or 'none').lower()
    username = str(_datasource_config_value(config, 'username', 'user', 'prometheus.user', default='') or '').strip()
    password = str(_datasource_config_value(config, 'password', 'prometheus.password', default='') or '').strip()
    if auth_type == 'basic' and username:
        return username, password
    if auth_type in {'', 'none'} and username and password:
        return username, password
    return None


def _select_metric_datasource(config):
    from ops.models import MetricDataSource

    queryset = MetricDataSource.objects.filter(is_enabled=True, provider=MetricDataSource.PROVIDER_PROMETHEUS)
    datasource_id = str(_config_value(config, 'metric_datasource_id', 'prometheus_metric_datasource_id') or '').strip()
    if datasource_id:
        try:
            return queryset.get(pk=datasource_id)
        except (MetricDataSource.DoesNotExist, TypeError, ValueError) as exc:
            raise ValueError('指定的 Prometheus 指标数据源不存在或已停用') from exc

    environment = str(_config_value(config, 'prometheus_environment', 'environment') or '').strip()
    if environment:
        datasource = queryset.filter(environment=environment, is_default=True).order_by('name').first()
        if datasource:
            return datasource
        datasource = queryset.filter(environment=environment).order_by('-is_default', 'name').first()
        if datasource:
            return datasource
    datasource = queryset.filter(environment='', is_default=True).order_by('name').first()
    if datasource:
        return datasource
    return queryset.order_by('-is_default', 'environment', 'name').first()


def _resolve_prometheus_client(config):
    direct_url = str(_config_value(config, 'prometheus_query_url') or '').strip().rstrip('/')
    if direct_url:
        return {
            'base_url': direct_url,
            'headers': {'Accept': 'application/json'},
            'auth': None,
            'timeout': _config_int(_config_value(config, 'prometheus_timeout', default=6), 6),
            'verify': not _config_bool(_config_value(config, 'prometheus_tls_skip_verify', default=False), False),
            'datasource_name': '同步任务 Prometheus',
        }

    datasource = _select_metric_datasource(config)
    if not datasource:
        raise ValueError('未配置可用的 Prometheus 指标数据源')
    datasource_config = datasource.config if isinstance(datasource.config, dict) else {}
    query_url = str(_datasource_config_value(
        datasource_config,
        'query_url',
        'addr',
        'prometheus.addr',
        'internal_addr',
        'prometheus.internal_addr',
        default='',
    ) or '').strip().rstrip('/')
    parsed = urlparse(query_url)
    if not parsed.scheme or not parsed.netloc or (parsed.hostname or '').endswith('.example.com'):
        raise ValueError(f'Prometheus 指标数据源「{datasource.name}」尚未配置有效查询地址')
    timeout = _config_int(_datasource_config_value(datasource_config, 'timeout', 'prometheus.timeout', default=6), 6)
    tls_skip_verify = _config_bool(_datasource_config_value(
        datasource_config,
        'tls_skip_verify',
        'insecure_skip_verify',
        default=False,
    ), False)
    return {
        'base_url': query_url,
        'headers': _datasource_headers(datasource_config),
        'auth': _datasource_auth(datasource_config),
        'timeout': timeout,
        'verify': not tls_skip_verify,
        'datasource_name': datasource.name,
    }


def _prometheus_query(client, query):
    response = http_requests.get(
        f"{client['base_url'].rstrip('/')}/api/v1/query",
        params={'query': query},
        headers=client.get('headers') or {},
        timeout=client.get('timeout') or 6,
        auth=client.get('auth'),
        verify=client.get('verify', True),
    )
    if response.status_code >= 400:
        raise RuntimeError(f'Prometheus HTTP {response.status_code}')
    body = response.json()
    if body.get('status') != 'success':
        raise RuntimeError(body.get('error') or 'Prometheus 查询失败')
    return ((body.get('data') or {}).get('result') or [])


def _label_name(value):
    text = str(value or '').strip()
    return text if re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', text) else 'instance'


def _promql_string(value):
    return json.dumps(str(value or ''), ensure_ascii=False)


def _selector(*parts):
    normalized = []
    for part in parts:
        text = str(part or '').strip().strip('{}').strip().strip(',')
        if text:
            normalized.append(text)
    return ','.join(normalized)


def _prometheus_queries(config):
    instance_label = _label_name(_config_value(config, 'prometheus_instance_label', default='instance'))
    node_selector = _selector(_config_value(config, 'prometheus_node_selector', default=''))
    cpu_selector = _selector('mode="idle"', node_selector)
    memory_selector = _selector(node_selector)
    root_mountpoint = str(_config_value(config, 'prometheus_root_mountpoint', default='/') or '/').strip()
    filesystem_excludes = str(_config_value(
        config,
        'prometheus_filesystem_excludes',
        default='tmpfs|overlay|squashfs|nsfs',
    ) or '').strip()
    filesystem_selector = _selector(
        f'mountpoint={_promql_string(root_mountpoint)}',
        f'fstype!~{_promql_string(filesystem_excludes)}' if filesystem_excludes else '',
        node_selector,
    )
    cpu_window = str(_config_value(config, 'prometheus_cpu_window', default='1m') or '1m').strip()
    if not re.fullmatch(r'[1-9][0-9]*(?:s|m|h)', cpu_window):
        cpu_window = '1m'
    queries = {
        'cpu_usage': f'100 * (1 - avg by ({instance_label}) (rate(node_cpu_seconds_total{{{cpu_selector}}}[{cpu_window}])))',
        'memory_total_bytes': f'max by ({instance_label}) (node_memory_MemTotal_bytes{{{memory_selector}}})',
        'memory_free_bytes': f'max by ({instance_label}) (node_memory_MemFree_bytes{{{memory_selector}}})',
        'memory_available_bytes': f'max by ({instance_label}) (node_memory_MemAvailable_bytes{{{memory_selector}}})',
        'disk_total_bytes': f'max by ({instance_label}) (node_filesystem_size_bytes{{{filesystem_selector}}})',
        'disk_free_bytes': f'max by ({instance_label}) (node_filesystem_free_bytes{{{filesystem_selector}}})',
        'disk_available_bytes': f'max by ({instance_label}) (node_filesystem_avail_bytes{{{filesystem_selector}}})',
    }
    configured = config.get('prometheus_queries') if isinstance(config.get('prometheus_queries'), dict) else {}
    for key in queries:
        if configured.get(key):
            queries[key] = str(configured[key]).strip()
    return instance_label, root_mountpoint, queries


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalize_target(value):
    text = str(value or '').strip()
    if not text:
        return ''
    if '://' in text:
        parsed = urlparse(text)
        text = parsed.hostname or text
    elif text.startswith('[') and ']' in text:
        text = text[1:text.index(']')]
    elif text.count(':') == 1:
        host, port = text.rsplit(':', 1)
        if port.isdigit():
            text = host
    return text.strip().rstrip('.').lower()


def _series_map(results, instance_label):
    mapped = {}
    for result in results:
        metric = result.get('metric') if isinstance(result, dict) else {}
        sample = result.get('value') if isinstance(result, dict) else None
        if not isinstance(metric, dict) or not isinstance(sample, (list, tuple)) or len(sample) < 2:
            continue
        target = str(metric.get(instance_label) or '').strip()
        target_key = _normalize_target(target)
        timestamp = _finite_number(sample[0])
        value = _finite_number(sample[1])
        if not target_key or timestamp is None or value is None:
            continue
        current = mapped.get(target_key)
        if not current or timestamp >= current['timestamp']:
            mapped[target_key] = {'target': target, 'timestamp': timestamp, 'value': value}
    return mapped


def _vm_identity_values(raw):
    values = []

    def add_values(value):
        if isinstance(value, dict):
            for nested_value in value.values():
                add_values(nested_value)
            return
        if isinstance(value, (list, tuple, set)):
            for nested_value in value:
                add_values(nested_value)
            return
        if value not in (None, ''):
            values.append(str(value).strip())

    for key in ('vm', 'vm_id', 'moid', 'source_unique_id', 'uuid', 'instance_id', 'name', 'guest_ip', 'private_ip', 'ip_address', 'ip', 'hostname', 'guest_hostname', 'fqdn'):
        add_values(raw.get(key))
    for key in ('InnerIpAddress', 'PrivateIpAddress', 'PublicIpAddress', 'EipAddress', 'addresses', 'Addresses'):
        add_values(raw.get(key))
    return values


def _vm_target_candidates(raw, config):
    candidates = []
    instance_map = config.get('prometheus_instance_map') if isinstance(config.get('prometheus_instance_map'), dict) else {}
    identities = _vm_identity_values(raw)
    for identity in identities:
        mapped = instance_map.get(identity)
        if mapped not in (None, ''):
            candidates.append(str(mapped).strip())
    candidates.extend(identities)
    normalized = []
    for value in candidates:
        target = _normalize_target(value)
        if target and target not in normalized:
            normalized.append(target)
    return normalized


def _sample_for_vm(series, candidates):
    for candidate in candidates:
        if candidate in series:
            return series[candidate]
    return None


def _iso_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace('+00:00', 'Z')


def _gb(value):
    return round(max(float(value or 0), 0) / 1024 / 1024 / 1024, 2)


def _percent(numerator, denominator):
    if denominator in (None, 0) or numerator is None:
        return None
    return round(min(max(float(numerator) / float(denominator) * 100, 0), 100), 2)


def _fallback_snapshots(raw):
    snapshots = raw.get('_metric_snapshots') if isinstance(raw.get('_metric_snapshots'), list) else []
    return [dict(item) for item in snapshots if isinstance(item, dict)]


def _mark_fallback(raw, error):
    item = dict(raw)
    snapshots = _fallback_snapshots(item)
    item['_metric_collection_status'] = 'fallback' if snapshots else 'no_data'
    item['_metric_collection_source'] = 'vsphere_vm' if snapshots else ''
    item['_metric_collection_error'] = str(error or '').strip()
    return item


def _prometheus_vm_metrics(raw, series_by_metric, config, root_mountpoint):
    candidates = _vm_target_candidates(raw, config)
    samples = {
        key: _sample_for_vm(series, candidates)
        for key, series in series_by_metric.items()
    }
    metrics = {}

    cpu_sample = samples.get('cpu_usage')
    if cpu_sample:
        usage_percent = round(min(max(cpu_sample['value'], 0), 100), 2)
        metrics['cpu_usage'] = {
            'metric': 'cpu_usage',
            'value': usage_percent,
            'unit': '%',
            'usage_percent': usage_percent,
            'source': 'prometheus_node_exporter',
            'collected_at': _iso_timestamp(cpu_sample['timestamp']),
        }

    memory_total = samples.get('memory_total_bytes')
    memory_available = samples.get('memory_available_bytes')
    memory_free = samples.get('memory_free_bytes')
    if memory_total and memory_available and memory_total['value'] > 0:
        used_bytes = max(memory_total['value'] - memory_available['value'], 0)
        usage_percent = _percent(used_bytes, memory_total['value'])
        collected_timestamp = max(memory_total['timestamp'], memory_available['timestamp'])
        metrics['memory_usage'] = {
            'metric': 'memory_usage',
            'value': _gb(used_bytes),
            'unit': 'GB',
            'usage_percent': usage_percent,
            'source': 'prometheus_node_exporter',
            'collected_at': _iso_timestamp(collected_timestamp),
            'memory_total_gb': _gb(memory_total['value']),
            'memory_available_gb': _gb(memory_available['value']),
            'memory_free_gb': _gb(memory_free['value']) if memory_free else None,
        }

    disk_total = samples.get('disk_total_bytes')
    disk_free = samples.get('disk_free_bytes')
    disk_available = samples.get('disk_available_bytes')
    if disk_total and disk_free and disk_available and disk_total['value'] > 0:
        used_bytes = max(disk_total['value'] - disk_free['value'], 0)
        usage_denominator = used_bytes + max(disk_available['value'], 0)
        usage_percent = _percent(used_bytes, usage_denominator)
        collected_timestamp = max(disk_total['timestamp'], disk_free['timestamp'], disk_available['timestamp'])
        metrics['disk_usage'] = {
            'metric': 'disk_usage',
            'value': _gb(used_bytes),
            'unit': 'GB',
            'usage_percent': usage_percent,
            'source': 'prometheus_node_exporter',
            'collected_at': _iso_timestamp(collected_timestamp),
            'root_disk_total_gb': _gb(disk_total['value']),
            'root_disk_free_gb': _gb(disk_free['value']),
            'root_disk_available_gb': _gb(disk_available['value']),
            'root_mountpoint': root_mountpoint,
        }

    matched_samples = [sample for sample in samples.values() if sample]
    target = matched_samples[0]['target'] if matched_samples else ''
    return metrics, target


def _apply_prometheus_metrics(raw, metrics, target, datasource_name, errors, root_mountpoint):
    item = dict(raw)
    fallback_snapshots = _fallback_snapshots(item)
    fallback_by_metric = {
        snapshot.get('metric'): snapshot
        for snapshot in fallback_snapshots
        if snapshot.get('metric') in VM_METRICS
    }
    snapshots = []
    for metric_name in VM_METRICS:
        snapshots.append(metrics.get(metric_name) or fallback_by_metric.get(metric_name))
    snapshots = [snapshot for snapshot in snapshots if snapshot]
    if snapshots:
        item['_metric_snapshots'] = snapshots

    if 'cpu_usage' in metrics:
        item['cpu_usage_percent'] = metrics['cpu_usage']['usage_percent']
    if 'memory_usage' in metrics:
        memory = metrics['memory_usage']
        item['memory_used_gb'] = memory['value']
        item['memory_usage_percent'] = memory['usage_percent']
        item['memory_total_gb'] = memory['memory_total_gb']
        item['memory_available_gb'] = memory['memory_available_gb']
        if memory['memory_free_gb'] is not None:
            item['memory_free_gb'] = memory['memory_free_gb']
    if 'disk_usage' in metrics:
        disk = metrics['disk_usage']
        item['disk_used_gb'] = disk['value']
        item['disk_usage_percent'] = disk['usage_percent']
        item['root_disk_total_gb'] = disk['root_disk_total_gb']
        item['root_disk_free_gb'] = disk['root_disk_free_gb']
        item['root_disk_available_gb'] = disk['root_disk_available_gb']
        item['root_mountpoint'] = root_mountpoint

    prometheus_metric_names = set(metrics)
    fallback_metric_names = set(fallback_by_metric) - prometheus_metric_names
    if len(prometheus_metric_names) == len(VM_METRICS):
        status = 'ok'
        source = 'prometheus_node_exporter'
    elif prometheus_metric_names:
        status = 'partial'
        source = 'prometheus_node_exporter+vsphere_vm' if fallback_metric_names else 'prometheus_node_exporter'
    else:
        status = 'fallback' if fallback_metric_names else 'no_data'
        source = 'vsphere_vm' if fallback_metric_names else ''

    missing_labels = {
        'cpu_usage': 'CPU',
        'memory_usage': '内存',
        'disk_usage': '根分区',
    }
    missing = [missing_labels[name] for name in VM_METRICS if name not in prometheus_metric_names]
    error_parts = list(errors)
    if missing:
        if target:
            error_parts.append(f'Prometheus 未返回{ "、".join(missing) }指标，缺失项已回退 vSphere')
        else:
            error_parts.append('未按虚拟机 IP 或名称匹配到 node_exporter target，已回退 vSphere')

    collected_values = [metric.get('collected_at') for metric in metrics.values() if metric.get('collected_at')]
    item['_metric_collection_status'] = status
    item['_metric_collection_source'] = source
    item['_metric_collection_error'] = '；'.join(dict.fromkeys(part for part in error_parts if part))
    item['_metric_datasource'] = datasource_name
    item['_metric_collected_at'] = max(collected_values) if collected_values else ''
    item['_prometheus_target'] = target
    return item


def enrich_vsphere_vm_metrics(raw_items, config):
    items = [dict(item) if isinstance(item, dict) else item for item in (raw_items or [])]
    if not _config_bool((config or {}).get('prometheus_metrics_enabled'), True):
        return items
    vm_indexes = [
        index
        for index, item in enumerate(items)
        if isinstance(item, dict) and not item.get('__sxdevops_kind')
    ]
    if not vm_indexes:
        return items
    try:
        client = _resolve_prometheus_client(config or {})
        instance_label, root_mountpoint, queries = _prometheus_queries(config or {})
    except Exception as exc:
        for index in vm_indexes:
            items[index] = _mark_fallback(items[index], exc)
        return items

    series_by_metric = {}
    errors = []
    for metric_name, query in queries.items():
        try:
            series_by_metric[metric_name] = _series_map(_prometheus_query(client, query), instance_label)
        except Exception as exc:
            series_by_metric[metric_name] = {}
            errors.append(f'{metric_name}: {exc}')

    for index in vm_indexes:
        metrics, target = _prometheus_vm_metrics(items[index], series_by_metric, config or {}, root_mountpoint)
        items[index] = _apply_prometheus_metrics(
            items[index],
            metrics,
            target,
            client.get('datasource_name') or '',
            errors,
            root_mountpoint,
        )
    return items


def enrich_cloud_vm_metrics(raw_items, config, fallback_source):
    items = enrich_vsphere_vm_metrics(raw_items, config)
    fallback_source = str(fallback_source or '').strip()
    if not fallback_source:
        return items
    for item in items:
        if not isinstance(item, dict):
            continue
        source = str(item.get('_metric_collection_source') or '')
        if source:
            item['_metric_collection_source'] = source.replace('vsphere_vm', fallback_source)
        error = str(item.get('_metric_collection_error') or '')
        if error:
            item['_metric_collection_error'] = error.replace('vSphere', fallback_source)
    return items
