import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError, wait
from collections import Counter, defaultdict
from urllib.parse import urlparse

from django.core.cache import cache
from django.db.models import Count, Max, Q
from django.utils import timezone
from sxdevops.features import is_system_posture_enabled

from eventwall.models import EventRecord, EventSource
from ops.models import (
    Alert,
    Deployment,
    DockerHost,
    GrafanaSetting,
    K8sCluster,
    LogDataSource,
    LogEntry,
    MetricDataSource,
    ObservabilityDataSourceLink,
    SystemPostureEnvironment,
    SystemPostureSystem,
    TaskResource,
    TaskResourceGroup,
    TracingDataSource,
)
from marketplace.models import ServiceDeployment
from ops.tracing_providers import load_tracing_catalog

from .models import AIOpsKnowledgeEnvironment


UNKNOWN_SYSTEM = '未标记系统'
UNKNOWN_ENV = '未标记环境'
UNKNOWN_SERVICE = '未标记服务'
UNASSIGNED_SYSTEM = '未归属系统'
GRAPH_RESPONSE_CACHE_TTL = 20
EXTERNAL_DISCOVERY_CACHE_TTL = 60
EXTERNAL_DISCOVERY_STALE_CACHE_TTL = 300
FAST_EXTERNAL_TIMEOUT = 4
FAST_TRACE_DETAIL_TIMEOUT = 2
MAX_TRACE_DETAIL_SAMPLES = 5
MOJIBAKE_HINTS = {
    '\u9422', '\u975b', '\u6662', '\u93c8', '\u9359', '\u6d5c', '\u7eef',
    '\u93ac', '\u5a34', '\u6fa7', '\u7039', '\u68ff', '\u6d60', '\u65c2',
}


CAPABILITY_DEFS = [
    ('metrics', '指标', 'datasource', '/observability/metrics'),
    ('logs', '日志', 'logs', '/logs'),
    ('tracing', '链路', 'tracing', '/observability/tracing'),
    ('dashboards', '看板', 'dashboard', '/observability/grafana'),
    ('alerts', '告警', 'alert', '/alerts'),
    ('posture', '系统态势', 'posture', '/observability/system-posture'),
    ('internal_events', '内部事件', 'internal_event', '/events/wall'),
    ('external_events', '外部事件', 'external_event', '/events/wall'),
]


def _mojibake_score(text):
    return sum(text.count(token) for token in MOJIBAKE_HINTS) + text.count(chr(0xfffd))


def _repair_text(value):
    text = str(value or '').strip()
    if not text:
        return ''
    if any('\u4e00' <= char <= '\u9fff' for char in text) and _mojibake_score(text) == 0:
        return text
    candidates = [text]
    for encoding in ('latin1', 'gbk', 'gb18030'):
        try:
            repaired = text.encode(encoding).decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if (
            repaired
            and any('\u4e00' <= char <= '\u9fff' for char in repaired)
            and '?' not in repaired
            and _mojibake_score(repaired) < _mojibake_score(text)
        ):
            candidates.append(repaired)
    return min(candidates, key=lambda item: (_mojibake_score(item), len(item)))


def _clean(value, fallback=''):
    text = _repair_text(value)
    return text or fallback


def _url_hostname(value=''):
    text = _clean(value)
    if not text:
        return ''
    try:
        parsed = urlparse(text if '://' in text else f'//{text}')
        return _clean(parsed.hostname)
    except Exception:
        return ''


def _is_demoish_text(*values):
    text = ' '.join(str(value or '') for value in values).lower()
    return any(keyword in text for keyword in ['demo', '演示', '示例', '样例'])


def _is_invalid_environment(value):
    text = _clean(value)
    if not text:
        return True
    lowered = text.lower()
    return lowered.startswith('env-') or set(text) == {'?'} or text in {'未知', 'unknown', 'null', 'none', '-'}


def _is_microservice_name(value):
    text = _clean(value)
    if not text or len(text) > 64:
        return False
    lowered = text.lower()
    if lowered.endswith('-release'):
        return False
    blocked_tokens = [
        'demo',
        'alert-demo',
        'traffic-generator',
        'prometheus',
        'alertmanager',
        'kube-state-metrics',
        'node-exporter',
        'grafana',
        'loki',
        'tempo',
    ]
    if any(token in lowered for token in blocked_tokens):
        return False
    if lowered.startswith(('kube-', 'kubernetes-', 'node-', 'job ')):
        return False
    return bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', text))


SERVICE_DISCOVERY_BLOCKED_TOKENS = {
    'alertmanager',
    'busybox',
    'coredns',
    'debug',
    'etcd',
    'grafana',
    'kube',
    'loki',
    'mysql',
    'nginx',
    'node-exporter',
    'postgres',
    'prometheus',
    'tempo',
}

SYSTEM_OWNERSHIP_KEYS = {
    'app_kubernetes_io_part_of',
    'business_line',
    'businessline',
    'biz',
    'biz_line',
    'biz_system',
    'owner_system',
    'service_namespace',
    'system',
    'system_name',
}

RUNTIME_COMPONENT_ALIASES = {
    'mysql': ('MySQL', 'DB'),
    'mariadb': ('MariaDB', 'DB'),
    'postgres': ('PostgreSQL', 'DB'),
    'postgresql': ('PostgreSQL', 'DB'),
    'mongodb': ('MongoDB', 'DB'),
    'mongo': ('MongoDB', 'DB'),
    'oracle': ('Oracle', 'DB'),
    'sqlserver': ('SQL Server', 'DB'),
    'mssql': ('SQL Server', 'DB'),
    'redis': ('Redis', '中间件'),
    'kafka': ('Kafka', '中间件'),
    'rocketmq': ('RocketMQ', '中间件'),
    'rabbitmq': ('RabbitMQ', '中间件'),
    'elasticsearch': ('Elasticsearch', '中间件'),
    'elastic': ('Elasticsearch', '中间件'),
    'nacos': ('Nacos', '中间件'),
    'zookeeper': ('ZooKeeper', '中间件'),
    'etcd': ('Etcd', '中间件'),
    'nginx': ('Nginx', '中间件'),
    'loki': ('Loki', '中间件'),
    'tempo': ('Tempo', '中间件'),
    'prometheus': ('Prometheus', '中间件'),
    'alertmanager': ('Alertmanager', '中间件'),
    'database': ('Database', 'DB'),
    'db': ('Database', 'DB'),
    '数据库': ('Database', 'DB'),
    'cache': ('Cache', '中间件'),
    '缓存': ('Cache', '中间件'),
    'mq': ('Message Queue', '中间件'),
    'queue': ('Message Queue', '中间件'),
    '消息队列': ('Message Queue', '中间件'),
}


def _node_key(kind, *parts):
    return ':'.join([kind, *[str(part).strip().replace(':', '_') for part in parts if str(part).strip()]])


def _matches_filters(value, allowed):
    return not allowed or value in allowed


def _append_unique(target, value, limit=4):
    if not value or value in target:
        return
    if len(target) < limit:
        target.append(value)


def _call_with_timeout(loader, timeout=FAST_EXTERNAL_TIMEOUT, default=None):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(loader)
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        return default
    except Exception:
        return default
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _cache_enabled():
    return 'test' not in sys.argv


def _cache_get(key):
    if not _cache_enabled():
        return None
    return cache.get(key)


def _cache_set(key, value, ttl):
    if not _cache_enabled() or value is None:
        return
    cache.set(key, value, ttl)


def _stale_cache_key(key):
    return f'{key}:stale'


def _cache_get_stale(key):
    if not _cache_enabled():
        return None
    return cache.get(_stale_cache_key(key))


def _cache_set_stale(key, value, ttl=EXTERNAL_DISCOVERY_STALE_CACHE_TTL):
    if not _cache_enabled() or value is None:
        return
    cache.set(_stale_cache_key(key), value, ttl)


def _cached_external_value(key, loader, ttl=EXTERNAL_DISCOVERY_CACHE_TTL, timeout=FAST_EXTERNAL_TIMEOUT, default=None):
    cached = _cache_get(key)
    if cached is not None:
        return cached
    value = _call_with_timeout(loader, timeout=timeout, default=default)
    if value is not None:
        _cache_set(key, value, ttl)
        _cache_set_stale(key, value)
        return value
    stale = _cache_get_stale(key)
    if stale is not None:
        return stale
    return default


def _cached_external_batch(items, ttl=EXTERNAL_DISCOVERY_CACHE_TTL, timeout=FAST_EXTERNAL_TIMEOUT, max_workers=8):
    results = {}
    pending_items = []
    for result_key, cache_key, loader, default in items:
        cached = _cache_get(cache_key)
        if cached is not None:
            results[result_key] = cached
            continue
        pending_items.append((result_key, cache_key, loader, default))

    if not pending_items:
        return results

    executor = ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(pending_items))))
    future_map = {
        executor.submit(loader): (result_key, cache_key, default)
        for result_key, cache_key, loader, default in pending_items
    }
    done, not_done = wait(future_map, timeout=timeout)
    try:
        for future in done:
            result_key, cache_key, default = future_map[future]
            try:
                value = future.result()
            except Exception:
                value = default
            if value is None:
                value = default
            results[result_key] = value
            _cache_set(cache_key, value, ttl)
            _cache_set_stale(cache_key, value)
        for future in not_done:
            result_key, cache_key, default = future_map[future]
            future.cancel()
            results[result_key] = _cache_get_stale(cache_key)
            if results[result_key] is None:
                results[result_key] = default
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return results


def _graph_cache_key(params):
    query_items = []
    if params:
        try:
            query_items = [
                (key, params.getlist(key))
                for key in sorted(params.keys())
                if key != '_'
            ]
        except AttributeError:
            query_items = sorted((params or {}).items())
    latest_config = (
        AIOpsKnowledgeEnvironment.objects
        .order_by('-updated_at')
        .values_list('updated_at', flat=True)
        .first()
    )
    task_resource_version = TaskResource.objects.aggregate(latest=Max('updated_at'), count=Count('id'))
    task_resource_group_version = TaskResourceGroup.objects.aggregate(latest=Max('updated_at'), count=Count('id'))
    raw = json.dumps(
        {
            'query': query_items,
            'latest_config': latest_config.isoformat() if latest_config else '',
            'task_resource_count': task_resource_version.get('count') or 0,
            'latest_task_resource': task_resource_version.get('latest').isoformat() if task_resource_version.get('latest') else '',
            'task_resource_group_count': task_resource_group_version.get('count') or 0,
            'latest_task_resource_group': task_resource_group_version.get('latest').isoformat() if task_resource_group_version.get('latest') else '',
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return f"aiops:knowledge_graph:v6:{hashlib.md5(raw.encode('utf-8')).hexdigest()}"


def _empty_graph(filters=None):
    result = {
        'nodes': [],
        'edges': [],
        'summary': {
            'node_count': 0,
            'edge_count': 0,
            'service_count': 0,
            'datasource_count': 0,
            'event_source_count': 0,
            'capability_count': 0,
            'infrastructure_count': 0,
            'runtime_component_count': 0,
        },
        'filters': {
            'systems': [],
            'business_lines': [],
            'environments': [],
            'services': [],
            'default_environment': '',
            **(filters or {}),
        },
        'relation_legend': [
            {'key': 'observability_link', 'label': '可观测性跳转配置'},
            {'key': 'environment_system', 'label': '环境包含系统'},
            {'key': 'system_service', 'label': '系统承载服务'},
            {'key': 'service_capability', 'label': '服务产生数据'},
            {'key': 'system_dependency', 'label': '系统依赖'},
            {'key': 'capability_datasource', 'label': '能力接入数据源'},
            {'key': 'capability_event_source', 'label': '能力接入事件源'},
            {'key': 'environment_observability', 'label': '环境关联可观测性'},
            {'key': 'environment_infrastructure', 'label': '环境运行于基础设施'},
            {'key': 'environment_resource_base', 'label': '环境关联资源底座'},
            {'key': 'service_deployment', 'label': '部署在'},
            {'key': 'infrastructure_member', 'label': '集群包含主机'},
            {'key': 'service_runtime', 'label': '服务依赖'},
            {'key': 'system_runtime', 'label': '系统依赖运行组件'},
        ],
        'environment_required': True,
    }
    return result


def _clean_list(values):
    result = []
    for value in values or []:
        text = _clean(value)
        if text and text not in result:
            result.append(text)
    return result


def _int_list(values):
    result = []
    for value in values or []:
        try:
            item = int(value)
        except (TypeError, ValueError):
            continue
        if item and item not in result:
            result.append(item)
    return result


def _enabled_knowledge_environments():
    return list(AIOpsKnowledgeEnvironment.objects.filter(is_enabled=True).order_by('-is_default', 'name', 'id'))


def resolve_knowledge_environment(name):
    text = _clean(name)
    if not text:
        return None
    config = AIOpsKnowledgeEnvironment.objects.filter(is_enabled=True, name=text).first()
    if not config:
        for item in _enabled_knowledge_environments():
            aliases = _clean_list(getattr(item, 'aliases', []) or [])
            if text in aliases:
                config = item
                break
    if not config:
        return None
    return {
        'name': config.name,
        'aliases': _clean_list(getattr(config, 'aliases', []) or []),
        'event_environments': _clean_list(config.event_environments),
        'grafana_folder_keys': _clean_list(config.grafana_folder_keys),
        'metric_datasource_ids': _int_list(getattr(config, 'metric_datasource_ids', []) or []),
        'log_datasource_ids': _int_list(config.log_datasource_ids),
        'tracing_datasource_ids': _int_list(config.tracing_datasource_ids),
        'observability_link_ids': _int_list(getattr(config, 'observability_link_ids', []) or []),
        'alert_environments': _clean_list(config.alert_environments),
        'posture_environments': _clean_list(getattr(config, 'posture_environments', []) or []) if is_system_posture_enabled() else [],
        'k8s_cluster_ids': _int_list(config.k8s_cluster_ids),
        'k8s_namespaces': config.k8s_namespaces if isinstance(config.k8s_namespaces, dict) else {},
        'docker_host_ids': _int_list(config.docker_host_ids),
        'task_resource_environment_ids': _int_list(getattr(config, 'task_resource_environment_ids', []) or []),
        'association_snapshot': config.association_snapshot if isinstance(config.association_snapshot, dict) else {},
        'child_node_snapshot': config.child_node_snapshot if isinstance(config.child_node_snapshot, dict) else {},
    }


def resolve_knowledge_environments_from_text(text):
    query = str(text or '')
    matches = []
    for config in _enabled_knowledge_environments():
        aliases = _clean_list(getattr(config, 'aliases', []) or [])
        candidates = [config.name, *aliases]
        if any(candidate and candidate in query for candidate in candidates):
            resolved = resolve_knowledge_environment(config.name)
            if resolved:
                matches.append(resolved)
    return matches


def _folder_matches(folder, selected_folders):
    return bool(_matched_configured_folder(folder, selected_folders))


def _matched_configured_folder(folder, selected_folders):
    folder = _clean(folder)
    if not folder:
        return ''
    if not selected_folders:
        return folder
    matches = [
        selected
        for selected in selected_folders
        if folder == selected or folder.startswith(f'{selected}/')
    ]
    if not matches:
        return ''
    return sorted(matches, key=len, reverse=True)[0]


def _k8s_cluster_nodes(cluster):
    try:
        from ops.k8s_views import DEMO_NODES, _get_k8s_client, _is_demo
    except Exception:
        return []

    if _is_demo(cluster):
        return list(DEMO_NODES)

    cache_key = f'aiops:kg:k8s:{cluster.id}:nodes'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        k8s = _get_k8s_client(cluster)
        v1 = k8s.CoreV1Api()
        data = []
        for node in v1.list_node().items:
            conditions = {c.type: c.status for c in (node.status.conditions or [])}
            roles = ','.join([
                label.replace('node-role.kubernetes.io/', '')
                for label in (node.metadata.labels or {})
                if label.startswith('node-role.kubernetes.io/')
            ])
            data.append({
                'name': node.metadata.name,
                'status': 'Ready' if conditions.get('Ready') == 'True' else 'NotReady',
                'roles': roles or 'worker',
                'version': node.status.node_info.kubelet_version if node.status.node_info else '',
                'internal_ip': next((a.address for a in (node.status.addresses or []) if a.type == 'InternalIP'), ''),
                'os_image': node.status.node_info.os_image if node.status.node_info else '',
                'cpu': (node.status.capacity or {}).get('cpu', ''),
                'memory': (node.status.capacity or {}).get('memory', ''),
            })
        _cache_set(cache_key, data, EXTERNAL_DISCOVERY_CACHE_TTL)
        _cache_set_stale(cache_key, data)
        return data
    except Exception:
        stale = _cache_get_stale(cache_key)
        if stale is not None:
            return stale
        return []


def _k8s_cluster_pods(cluster):
    try:
        from ops.k8s_views import DEMO_PODS, _get_k8s_client, _is_demo
    except Exception:
        return []

    if _is_demo(cluster):
        return list(DEMO_PODS)

    cache_key = f'aiops:kg:k8s:{cluster.id}:pods'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        k8s = _get_k8s_client(cluster)
        v1 = k8s.CoreV1Api()
        data = []
        for pod in v1.list_pod_for_all_namespaces().items:
            data.append({
                'name': pod.metadata.name,
                'namespace': pod.metadata.namespace,
                'node': pod.spec.node_name or '',
                'status': pod.status.phase or '',
                'containers': [
                    {
                        'name': container.name,
                        'image': container.image,
                    }
                    for container in (pod.spec.containers or [])
                ],
            })
        _cache_set(cache_key, data, EXTERNAL_DISCOVERY_CACHE_TTL)
        _cache_set_stale(cache_key, data)
        return data
    except Exception:
        stale = _cache_get_stale(cache_key)
        if stale is not None:
            return stale
        return []


def _k8s_cluster_workloads(cluster):
    try:
        from ops.k8s_views import DEMO_DAEMONSETS, DEMO_DEPLOYMENTS, DEMO_STATEFULSETS, _get_k8s_client, _is_demo
    except Exception:
        return []

    if _is_demo(cluster):
        return [
            {**item, 'workload_type': 'deployment'}
            for item in DEMO_DEPLOYMENTS
        ] + [
            {**item, 'workload_type': 'statefulset'}
            for item in DEMO_STATEFULSETS
        ] + [
            {**item, 'workload_type': 'daemonset'}
            for item in DEMO_DAEMONSETS
        ]

    cache_key = f'aiops:kg:k8s:{cluster.id}:workloads'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        k8s = _get_k8s_client(cluster)
        apps_v1 = k8s.AppsV1Api()
        workloads = []
        for item in apps_v1.list_deployment_for_all_namespaces().items:
            labels = {
                **(item.metadata.labels or {}),
                **(item.spec.template.metadata.labels or {}),
            }
            annotations = {
                **(item.metadata.annotations or {}),
                **(item.spec.template.metadata.annotations or {}),
            }
            workloads.append({
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'workload_type': 'deployment',
                'images': ','.join(container.image for container in (item.spec.template.spec.containers or [])),
                'labels': labels,
                'annotations': annotations,
            })
        for item in apps_v1.list_stateful_set_for_all_namespaces().items:
            labels = {
                **(item.metadata.labels or {}),
                **(item.spec.template.metadata.labels or {}),
            }
            annotations = {
                **(item.metadata.annotations or {}),
                **(item.spec.template.metadata.annotations or {}),
            }
            workloads.append({
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'workload_type': 'statefulset',
                'images': ','.join(container.image for container in (item.spec.template.spec.containers or [])),
                'labels': labels,
                'annotations': annotations,
            })
        for item in apps_v1.list_daemon_set_for_all_namespaces().items:
            labels = {
                **(item.metadata.labels or {}),
                **(item.spec.template.metadata.labels or {}),
            }
            annotations = {
                **(item.metadata.annotations or {}),
                **(item.spec.template.metadata.annotations or {}),
            }
            workloads.append({
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'workload_type': 'daemonset',
                'images': ','.join(container.image for container in (item.spec.template.spec.containers or [])),
                'labels': labels,
                'annotations': annotations,
            })
        _cache_set(cache_key, workloads, EXTERNAL_DISCOVERY_CACHE_TTL)
        _cache_set_stale(cache_key, workloads)
        return workloads
    except Exception:
        stale = _cache_get_stale(cache_key)
        if stale is not None:
            return stale
        return []


def _k8s_cluster_configmaps(cluster):
    try:
        from ops.k8s_views import DEMO_CONFIGMAPS, _get_k8s_client, _get_demo_state, _is_demo
    except Exception:
        return []

    if _is_demo(cluster):
        return list(_get_demo_state(cluster.id, 'configmaps', DEMO_CONFIGMAPS))

    cache_key = f'aiops:kg:k8s:{cluster.id}:configmaps'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        k8s = _get_k8s_client(cluster)
        v1 = k8s.CoreV1Api()
        data = [
            {
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'labels': item.metadata.labels or {},
                'data': item.data or {},
            }
            for item in v1.list_config_map_for_all_namespaces().items
        ]
        _cache_set(cache_key, data, EXTERNAL_DISCOVERY_CACHE_TTL)
        _cache_set_stale(cache_key, data)
        return data
    except Exception:
        stale = _cache_get_stale(cache_key)
        if stale is not None:
            return stale
        return []


def _docker_host_containers(host):
    try:
        from ops.docker_views import (
            _docker_json_command,
            _get_demo_state,
            _get_ssh_client_from_docker_host,
            _is_demo_docker_host,
            _parse_docker_ps,
            _ssh_exec,
        )
    except Exception:
        return []

    if _is_demo_docker_host(host):
        return list((_get_demo_state(host) or {}).get('containers', []))

    cache_key = f'aiops:kg:docker:{host.id}:containers'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        client = _get_ssh_client_from_docker_host(host)
        code, out, err = _ssh_exec(client, _docker_json_command('docker ps -a'))
        client.close()
        if code != 0:
            return []
        containers = _parse_docker_ps(out)
        _cache_set(cache_key, containers, EXTERNAL_DISCOVERY_CACHE_TTL)
        return containers
    except Exception:
        return []


def _normalized_runtime_text(value):
    text = re.sub(r'[^a-z0-9]+', '-', _clean(value).lower()).strip('-')
    return text


def _service_aliases(*values):
    aliases = set()
    for value in values:
        normalized = _normalized_runtime_text(value)
        if len(normalized) < 4:
            continue
        aliases.add(normalized)
        compact = normalized.replace('-', '')
        if len(compact) >= 4:
            aliases.add(compact)
    return aliases


def _service_identity_tokens(value):
    normalized = _normalized_runtime_text(value)
    if not normalized:
        return set()
    tokens = {normalized}
    parts = normalized.split('-')
    while len(parts) > 1 and parts[-1] in {'service', 'svc', 'api', 'server', 'app', 'application'}:
        parts = parts[:-1]
        stripped = '-'.join(parts)
        if stripped:
            tokens.add(stripped)
    return {token for token in tokens if len(token) >= 3}


def _service_names_related(left, right):
    left_tokens = _service_identity_tokens(left)
    right_tokens = _service_identity_tokens(right)
    return bool(left_tokens and right_tokens and left_tokens.intersection(right_tokens))


def _runtime_text_matches(service_name, *values):
    aliases = _service_aliases(service_name)
    if not aliases:
        return False

    haystacks = set()
    for value in values:
        raw = _clean(value).lower()
        if not raw:
            continue
        haystacks.add(raw)
        normalized = _normalized_runtime_text(raw)
        if normalized:
            haystacks.add(normalized)
            compact = normalized.replace('-', '')
            if compact:
                haystacks.add(compact)

    for alias in sorted(aliases, key=len, reverse=True):
        if any(alias in haystack for haystack in haystacks):
            return True
    return False


def _match_k8s_host_node_ids(cluster, member_node_ids, *service_candidates, namespace='', allow_fallback=True, pods=None):
    if not member_node_ids:
        return []

    pods = pods if pods is not None else _k8s_cluster_pods(cluster)
    matched_node_names = []
    for pod in pods:
        pod_namespace = _clean(pod.get('namespace'))
        if namespace and pod_namespace and namespace != pod_namespace:
            continue
        pod_name = _clean(pod.get('name'))
        container_values = []
        for container in pod.get('containers') or []:
            container_values.extend([
                container.get('name'),
                container.get('image'),
            ])
        if not any(_runtime_text_matches(candidate, pod_name, *container_values) for candidate in service_candidates if candidate):
            continue
        node_name = _clean(pod.get('node'))
        if node_name and node_name not in matched_node_names:
            matched_node_names.append(node_name)

    if matched_node_names:
        return [
            node_id
            for node_name, node_id in member_node_ids.items()
            if node_name in matched_node_names
        ]

    if not allow_fallback:
        return []

    fallback_names = [
        node_name
        for node_name in member_node_ids
        if 'master' not in node_name.lower() and 'control' not in node_name.lower()
    ]
    target_names = fallback_names or list(member_node_ids.keys())
    return [member_node_ids[name] for name in target_names[:3]]


def _deployment_cluster_name(deployment):
    if getattr(deployment, 'cluster_id', None) and getattr(deployment, 'cluster', None):
        return _clean(deployment.cluster.name)
    deploy_dir = _clean(getattr(deployment, 'deploy_dir', ''))
    if deploy_dir.startswith('k8s://'):
        return _clean(deploy_dir.replace('k8s://', '').split('/', 1)[0])
    return ''


def _service_host_node_ids(cluster, deployment, member_node_ids, pods=None):
    namespace = _clean(getattr(deployment, 'namespace', ''))
    return _match_k8s_host_node_ids(
        cluster,
        member_node_ids,
        _clean(getattr(deployment, 'release_name', '')),
        _clean(getattr(deployment, 'app_name', '')),
        namespace=namespace,
        allow_fallback=True,
        pods=pods,
    )


def _service_host_node_ids_for_service(cluster, service_name, member_node_ids, pods=None):
    return _match_k8s_host_node_ids(cluster, member_node_ids, service_name, allow_fallback=False, pods=pods)


def _docker_service_matches_host(host, service_name, containers=None):
    containers = containers if containers is not None else _docker_host_containers(host)
    for container in containers:
        if _runtime_text_matches(service_name, container.get('name'), container.get('image')):
            return True
    return False


def _service_candidate_allowed(value):
    service_name = _clean(value)
    if not _is_microservice_name(service_name):
        return False
    normalized = _normalized_runtime_text(service_name)
    parts = set(normalized.split('-'))
    if normalized in SERVICE_DISCOVERY_BLOCKED_TOKENS:
        return False
    if parts.intersection(SERVICE_DISCOVERY_BLOCKED_TOKENS):
        return False
    return True


def _runtime_image_basename(image):
    text = _clean(image)
    if not text:
        return ''
    text = text.rsplit('/', 1)[-1].split('@', 1)[0].split(':', 1)[0]
    return _normalized_runtime_text(text)


def _strip_k8s_workload_suffix(name):
    text = _normalized_runtime_text(name)
    text = re.sub(r'-[a-f0-9]{8,10}-[a-z0-9]{5}$', '', text)
    text = re.sub(r'-[a-z0-9]{5}$', '', text) if re.search(r'-[a-f0-9]{8,10}-', text) else text
    text = re.sub(r'-[0-9]+$', '', text)
    return text


def _strip_docker_role_suffix(name):
    text = _normalized_runtime_text(name)
    text = re.sub(r'-(batch|canary|failed|green|blue|smoke|proxy|worker)-[0-9]+$', '', text)
    text = re.sub(r'-(batch|canary|failed|green|blue|smoke|proxy|worker)$', '', text)
    text = re.sub(r'-[0-9]+$', '', text)
    return text


def _append_service_candidate(candidates, value):
    service_name = _clean(value)
    if not _service_candidate_allowed(service_name):
        return
    if service_name not in candidates:
        candidates.append(service_name)


def _metadata_key(value):
    return re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower()).strip('_')


def _metadata_system_candidates(value):
    if isinstance(value, dict):
        for key, raw in value.items():
            if _metadata_key(key) in SYSTEM_OWNERSHIP_KEYS and not isinstance(raw, (dict, list)):
                yield raw
        for nested_key in ('labels', 'annotations', 'tags', 'attributes', 'resource', 'resource_attributes', 'metadata'):
            if nested_key in value:
                yield from _metadata_system_candidates(value.get(nested_key))
        return
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and ('key' in item or 'name' in item) and 'value' in item:
                key = item.get('key') or item.get('name')
                if _metadata_key(key) in SYSTEM_OWNERSHIP_KEYS:
                    yield item.get('value')
                continue
            yield from _metadata_system_candidates(item)


def _extract_system_ownership(*sources):
    for source in sources:
        for candidate in _metadata_system_candidates(source):
            system_name = _clean(candidate)
            if system_name and not _is_invalid_environment(system_name):
                return system_name
    return ''


def _component_key_text(*values):
    return _normalized_runtime_text(' '.join(_clean(value) for value in values if _clean(value)))


def _classify_runtime_component(*values):
    raw_text = ' '.join(_clean(value) for value in values if _clean(value)).lower()
    text = _component_key_text(*values)
    if not text and not raw_text:
        return None
    compact = text.replace('-', '').replace('_', '').replace('.', '')
    for token, (technology, component_type) in RUNTIME_COMPONENT_ALIASES.items():
        if any('\u4e00' <= char <= '\u9fff' for char in token) and token in raw_text:
            return {
                'technology': technology,
                'component_type': component_type,
                'name': technology,
            }
        token_text = token.replace('-', '').replace('_', '').replace('.', '')
        if token_text and token_text in compact:
            return {
                'technology': technology,
                'component_type': component_type,
                'name': technology,
            }
    return None


def _span_tags_map(span):
    tags = span.get('tags') if isinstance(span, dict) else []
    result = {}
    for item in tags or []:
        if not isinstance(item, dict):
            continue
        key = _clean(item.get('key') or item.get('name'))
        if key:
            result[key] = _clean(item.get('value'))
    return result


def _append_runtime_component(components, name='', technology='', component_type='', source='', service_name='', environment='', infra_id='', deploy_node_id='', status='', details=None, count=1):
    component_name = _clean(name or technology)
    technology = _clean(technology or component_name)
    if not component_name:
        return
    component_id = _node_key('runtime_component', _normalized_runtime_text(component_name) or component_name)
    record = components.setdefault(component_id, {
        'id': component_id,
        'name': component_name,
        'technology': technology,
        'component_type': _clean(component_type) or '中间件',
        'sources': Counter(),
        'services': set(),
        'environments': set(),
        'infra_ids': set(),
        'deploy_node_ids': set(),
        'details': [],
        'status': status,
        'count': 0,
    })
    record['count'] += count or 1
    if source:
        record['sources'][source] += count or 1
    if service_name:
        record['services'].add(_clean(service_name))
    if environment:
        record['environments'].add(_clean(environment))
    if infra_id:
        record['infra_ids'].add(infra_id)
    if deploy_node_id:
        record['deploy_node_ids'].add(deploy_node_id)
    if status and not record.get('status'):
        record['status'] = status
    for item in details or []:
        if item not in record['details'] and len(record['details']) < 8:
            record['details'].append(item)


def _k8s_service_candidates_from_workload(workload):
    candidates = []
    _append_service_candidate(candidates, _normalized_runtime_text(workload.get('name')))
    return candidates


def _docker_service_candidates_from_container(container):
    candidates = []
    _append_service_candidate(candidates, _strip_docker_role_suffix(container.get('name')))
    if candidates:
        return candidates
    _append_service_candidate(candidates, _runtime_image_basename(container.get('image')))
    return candidates


def _discover_k8s_services(cluster, workloads=None):
    workloads = workloads if workloads is not None else _k8s_cluster_workloads(cluster)
    services = defaultdict(lambda: {'count': 0, 'source': 'k8s'})
    for workload in workloads:
        for service_name in _k8s_service_candidates_from_workload(workload):
            services[service_name]['count'] += 1
            system_name = _extract_system_ownership(workload)
            if system_name:
                services[service_name]['system_name'] = system_name
            _append_unique(services[service_name].setdefault('examples', []), _clean(workload.get('name')))
    return services


def _discover_docker_services(host, containers=None):
    containers = containers if containers is not None else _docker_host_containers(host)
    services = defaultdict(lambda: {'count': 0, 'source': 'docker'})
    for container in containers:
        for service_name in _docker_service_candidates_from_container(container):
            services[service_name]['count'] += 1
            system_name = _extract_system_ownership(container)
            if system_name:
                services[service_name]['system_name'] = system_name
            _append_unique(services[service_name].setdefault('examples', []), _clean(container.get('name')))
    return services


def _discover_k8s_components(cluster, workloads=None, pods=None):
    workloads = workloads if workloads is not None else _k8s_cluster_workloads(cluster)
    pods = pods if pods is not None else _k8s_cluster_pods(cluster)
    components = {}
    for workload in workloads or []:
        classification = _classify_runtime_component(
            workload.get('name'),
            workload.get('images'),
            workload.get('workload_type'),
        )
        if not classification:
            continue
        _append_runtime_component(
            components,
            name=_clean(workload.get('name')) or classification['name'],
            technology=classification['technology'],
            component_type=classification['component_type'],
            source='k8s',
            environment=_clean(workload.get('namespace')),
            details=[
                {'label': '来源', 'value': 'K8s 工作负载'},
                {'label': '命名空间', 'value': _clean(workload.get('namespace')) or '-'},
                {'label': '类型', 'value': _clean(workload.get('workload_type')) or '-'},
            ],
        )
    for pod in pods or []:
        for container in pod.get('containers') or []:
            classification = _classify_runtime_component(
                pod.get('name'),
                container.get('name'),
                container.get('image'),
            )
            if not classification:
                continue
            _append_runtime_component(
                components,
                name=_strip_k8s_workload_suffix(pod.get('name')) or classification['name'],
                technology=classification['technology'],
                component_type=classification['component_type'],
                source='k8s',
                environment=_clean(pod.get('namespace')),
                deploy_node_id=_node_key('infrastructure', 'k8s_host', cluster.id, _clean(pod.get('node'))) if _clean(pod.get('node')) else '',
                status=_clean(pod.get('status')),
                details=[
                    {'label': '来源', 'value': 'K8s Pod'},
                    {'label': '命名空间', 'value': _clean(pod.get('namespace')) or '-'},
                    {'label': '主机', 'value': _clean(pod.get('node')) or '-'},
                ],
            )
    return components


def _discover_docker_components(host, containers=None):
    containers = containers if containers is not None else _docker_host_containers(host)
    components = {}
    for container in containers or []:
        classification = _classify_runtime_component(container.get('name'), container.get('image'))
        if not classification:
            continue
        _append_runtime_component(
            components,
            name=_strip_docker_role_suffix(container.get('name')) or classification['name'],
            technology=classification['technology'],
            component_type=classification['component_type'],
            source='docker',
            environment=_clean(getattr(host, 'name', '')),
            deploy_node_id=_node_key('infrastructure', 'docker', host.id),
            status=_clean(container.get('status')),
            details=[
                {'label': '来源', 'value': 'Docker 容器'},
                {'label': '主机', 'value': _clean(getattr(host, 'name', '')) or '-'},
                {'label': '镜像', 'value': _clean(container.get('image')) or '-'},
            ],
        )
    return components


def _load_tracing_catalogs(datasources):
    return _cached_external_batch([
        (
            datasource.id,
            f'aiops:kg:tracing:{datasource.id}:catalog',
            lambda datasource=datasource: load_tracing_catalog(
                provider=datasource.provider,
                datasource_id=str(datasource.id),
            ),
            None,
        )
        for datasource in datasources
    ], timeout=FAST_EXTERNAL_TIMEOUT)


def _discover_tracing_services(datasources, catalogs=None):
    catalogs = catalogs if catalogs is not None else _load_tracing_catalogs(datasources)
    services = defaultdict(lambda: {'count': 0, 'source': 'tracing'})
    for datasource in datasources:
        catalog = catalogs.get(datasource.id)
        if not catalog:
            continue
        tracing_meta = catalog.get('tracing') if isinstance(catalog.get('tracing'), dict) else {}
        if tracing_meta.get('source') == 'demo':
            continue
        for item in catalog.get('services') or []:
            service_name = _clean(item.get('name') or item.get('id'))
            if not _service_candidate_allowed(service_name):
                continue
            services[service_name]['count'] += 1
            system_name = _extract_system_ownership(item)
            if system_name:
                services[service_name]['system_name'] = system_name
            _append_unique(services[service_name].setdefault('datasources', []), datasource.name)
    return services


def _load_trace_detail(datasource, trace_id):
    from ops.tracing_providers import load_trace_detail

    return load_trace_detail(
        trace_id,
        provider=datasource.provider,
        datasource_id=str(datasource.id),
    )


def _discover_tracing_components(datasources, catalogs=None):
    catalogs = catalogs if catalogs is not None else _load_tracing_catalogs(datasources)
    components = {}
    trace_samples = []
    for datasource in datasources:
        catalog = catalogs.get(datasource.id)
        if not catalog:
            continue
        tracing_meta = catalog.get('tracing') if isinstance(catalog.get('tracing'), dict) else {}
        if tracing_meta.get('source') == 'demo':
            continue
        for trace in (catalog.get('recent_traces') or [])[:MAX_TRACE_DETAIL_SAMPLES]:
            trace_id = _clean(trace.get('trace_id'))
            if not trace_id:
                continue
            trace_samples.append((datasource, trace_id))

    detail_results = _cached_external_batch([
        (
            (datasource.id, trace_id),
            f'aiops:kg:tracing:{datasource.id}:trace:{trace_id}',
            lambda datasource=datasource, trace_id=trace_id: _load_trace_detail(datasource, trace_id),
            None,
        )
        for datasource, trace_id in trace_samples
    ], timeout=FAST_TRACE_DETAIL_TIMEOUT)
    for datasource, trace_id in trace_samples:
        detail = detail_results.get((datasource.id, trace_id))
        if not detail:
            continue
        for span in detail.get('spans') or []:
            tag_map = _span_tags_map(span)
            classification = _classify_runtime_component(
                span.get('component'),
                span.get('peer'),
                span.get('endpoint_name'),
                tag_map.get('db.type'),
                tag_map.get('db.system'),
                tag_map.get('peer.service'),
            )
            if not classification:
                continue
            peer_name = _clean(span.get('peer')).split(':', 1)[0]
            component_name = peer_name or classification['name']
            _append_runtime_component(
                components,
                name=component_name,
                technology=classification['technology'],
                component_type=classification['component_type'],
                source='tracing',
                service_name=_clean(span.get('service_code')),
                details=[
                    {'label': '来源', 'value': 'Tracing Span'},
                    {'label': '组件', 'value': _clean(span.get('component')) or classification['technology']},
                    {'label': 'Peer', 'value': _clean(span.get('peer')) or '-'},
                ],
            )
    return components


def _namespaces_for_cluster(config, cluster_id):
    namespace_map = getattr(config, 'k8s_namespaces', {}) or {}
    if not isinstance(namespace_map, dict):
        return []
    values = namespace_map.get(str(cluster_id)) or namespace_map.get(cluster_id) or []
    if not isinstance(values, list):
        return []
    return _clean_list(values)


def _filter_pods_by_namespaces(pods, namespaces):
    allowed = {_clean(namespace) for namespace in namespaces if _clean(namespace)}
    if not allowed:
        return list(pods or [])
    return [
        pod
        for pod in pods or []
        if _clean(pod.get('namespace')) in allowed
    ]


def _filter_workloads_by_namespaces(workloads, namespaces):
    allowed = {_clean(namespace) for namespace in namespaces if _clean(namespace)}
    if not allowed:
        return list(workloads or [])
    return [
        workload
        for workload in workloads or []
        if _clean(workload.get('namespace')) in allowed
    ]


def _filter_configmaps_by_namespaces(configmaps, namespaces):
    allowed = {_clean(namespace) for namespace in namespaces if _clean(namespace)}
    if not allowed:
        return list(configmaps or [])
    return [
        configmap
        for configmap in configmaps or []
        if _clean(configmap.get('namespace')) in allowed
    ]


def _configmap_text(configmap):
    parts = [
        _clean(configmap.get('name')),
        _clean(configmap.get('namespace')),
    ]
    labels = configmap.get('labels') if isinstance(configmap.get('labels'), dict) else {}
    data = configmap.get('data') if isinstance(configmap.get('data'), dict) else {}
    for mapping in (labels, data):
        for key, value in mapping.items():
            parts.extend([_clean(key), _clean(value)])
    return ' '.join(part for part in parts if part)


def _configmap_scope_text(configmap):
    parts = [
        _clean(configmap.get('name')),
        _clean(configmap.get('namespace')),
    ]
    labels = configmap.get('labels') if isinstance(configmap.get('labels'), dict) else {}
    for key, value in labels.items():
        parts.extend([_clean(key), _clean(value)])
    return ' '.join(part for part in parts if part)


def _configmap_scoped_services(configmap, service_names):
    scope_text = _configmap_scope_text(configmap)
    if not scope_text:
        return []
    return [
        service_name
        for service_name in service_names
        if _service_names_related(service_name, scope_text) or _runtime_text_matches(service_name, scope_text)
    ]


def _configmap_runtime_links(configmaps, service_names, runtime_components):
    links = []
    runtime_records = list(runtime_components.values())
    for configmap in configmaps or []:
        text = _configmap_text(configmap)
        normalized_text = _normalized_runtime_text(text)
        if not normalized_text:
            continue
        matched_services = _configmap_scoped_services(configmap, service_names)
        if not matched_services:
            continue
        matched_component_ids = set()
        classification = _classify_runtime_component(text)
        for component in runtime_records:
            candidates = [
                component.get('name'),
                component.get('technology'),
                *(detail.get('value') for detail in component.get('details') or [] if isinstance(detail, dict)),
            ]
            if any(_runtime_text_matches(candidate, text) for candidate in candidates if candidate):
                matched_component_ids.add(component['id'])
                continue
            if classification and component.get('technology') == classification.get('technology'):
                matched_component_ids.add(component['id'])
        if not matched_component_ids and classification:
            temp_components = {}
            _append_runtime_component(
                temp_components,
                name=classification['name'],
                technology=classification['technology'],
                component_type=classification['component_type'],
                source='configmap',
                environment=_clean(configmap.get('namespace')),
                details=[
                    {'label': '来源', 'value': 'K8s ConfigMap'},
                    {'label': 'ConfigMap', 'value': _clean(configmap.get('name')) or '-'},
                    {'label': '命名空间', 'value': _clean(configmap.get('namespace')) or '-'},
                ],
            )
            for component in temp_components.values():
                runtime_components[component['id']] = component
                runtime_records.append(component)
                matched_component_ids.add(component['id'])
        for service_name in matched_services:
            for component_id in matched_component_ids:
                links.append({
                    'service_name': service_name,
                    'component_id': component_id,
                    'source': _clean(configmap.get('name')),
                })
    return links


def _event_source_code_for_event(event, event_source_catalog):
    metadata = event.metadata or {}
    source_code = _clean(metadata.get('event_source_code'))
    if source_code:
        return source_code
    resource_type = _clean(event.resource_type)
    for code, source in event_source_catalog.items():
        if source.source_kind != EventSource.KIND_BUILTIN:
            continue
        resource_types = (source.config or {}).get('resource_types') or []
        if resource_type and resource_type in resource_types:
            return code
    return ''


def _graph_event_source_label(source):
    label_map = {
        'builtin-workorder': '内置-工单系统',
        'builtin-task-center': '内置-事件中心',
    }
    return label_map.get(source.code, source.name)


def _related_builtin_event_source_codes(scope_records, event_sources, has_k8s=False, has_hosts=False, has_deployments=False):
    internal_records = [
        event for event in scope_records
        if event.source_type != EventRecord.SOURCE_EXTERNAL
    ]
    resource_types = {_clean(event.resource_type) for event in internal_records if _clean(event.resource_type)}
    resource_modules = {_clean(event.resource_module) for event in internal_records if _clean(event.resource_module)}
    modules = {_clean(event.module) for event in internal_records if _clean(event.module)}
    related_codes = set()

    for source in event_sources:
        if source.source_kind != EventSource.KIND_BUILTIN:
            continue
        config = source.config if isinstance(source.config, dict) else {}
        configured_types = {_clean(item) for item in (config.get('resource_types') or []) if _clean(item)}
        configured_modules = {
            _clean(item)
            for item in ((config.get('resource_modules') or []) + (config.get('modules') or []))
            if _clean(item)
        }
        if configured_types and resource_types.intersection(configured_types):
            related_codes.add(source.code)
            continue
        if configured_modules and (resource_modules.intersection(configured_modules) or modules.intersection(configured_modules)):
            related_codes.add(source.code)
            continue
        if source.source_type == EventSource.TYPE_BUILTIN_K8S and has_k8s:
            related_codes.add(source.code)
            continue
        if source.source_type == EventSource.TYPE_BUILTIN_TASK and has_hosts:
            related_codes.add(source.code)
            continue
        if source.source_type == EventSource.TYPE_BUILTIN_WORKORDER and has_deployments:
            related_codes.add(source.code)
            continue
        if not configured_types and not configured_modules:
            related_codes.add(source.code)

    return related_codes


def _node_snapshot_brief(node):
    return {
        'id': node.get('id'),
        'label': node.get('label'),
        'kind': node.get('kind'),
        'category': node.get('category'),
        'status': node.get('status'),
        'environment': node.get('environment', ''),
        'route': node.get('route', ''),
    }


def _persist_environment_snapshots(configs, nodes, edges):
    if not configs:
        return

    node_map = {node['id']: node for node in nodes}
    child_map = defaultdict(list)
    association_items = []
    for edge in edges:
        source_node = node_map.get(edge['source'])
        target_node = node_map.get(edge['target'])
        if not source_node or not target_node:
            continue
        association_items.append({
            'source': edge['source'],
            'source_label': source_node.get('label'),
            'target': edge['target'],
            'target_label': target_node.get('label'),
            'relation': edge.get('relation'),
            'label': edge.get('label'),
            'weight': edge.get('weight', 1),
        })
        child_map[edge['source']].append(_node_snapshot_brief(target_node))

    generated_at = timezone.now()
    snapshot_nodes = [_node_snapshot_brief(node) for node in nodes]
    for config in configs:
        config.association_snapshot = {
            'environment': config.name,
            'generated_at': generated_at.isoformat(),
            'nodes': snapshot_nodes,
            'edges': association_items,
        }
        config.child_node_snapshot = {
            'environment': config.name,
            'generated_at': generated_at.isoformat(),
            'children': dict(child_map),
        }
        config.snapshot_generated_at = generated_at
    AIOpsKnowledgeEnvironment.objects.bulk_update(
        configs,
        ['association_snapshot', 'child_node_snapshot', 'snapshot_generated_at'],
    )


def build_knowledge_graph(params=None):
    cache_key = _graph_cache_key(params)
    cached_graph = _cache_get(cache_key)
    if cached_graph is not None:
        return cached_graph

    params = params or {}
    if hasattr(params, 'getlist'):
        selected_system = {_clean(item) for item in (params.getlist('system') or params.getlist('business_line')) if _clean(item)}
    else:
        selected_system = set()
    selected_env = {_clean(item) for item in params.getlist('environment') if _clean(item)} if hasattr(params, 'getlist') else set()
    selected_service = {_clean(item) for item in params.getlist('service') if _clean(item)} if hasattr(params, 'getlist') else set()
    knowledge_env_configs = _enabled_knowledge_environments()
    selected_knowledge_configs = [config for config in knowledge_env_configs if config.name in selected_env]
    use_knowledge_env = bool(selected_knowledge_configs)
    event_env_to_graph = {}
    alert_env_to_graph = {}
    source_env_to_graph = {}
    selected_event_environments = set()
    selected_alert_environments = set()
    selected_posture_environments = set()
    selected_grafana_folders = set()
    selected_metric_datasource_ids = set()
    selected_log_datasource_ids = set()
    selected_tracing_datasource_ids = set()
    selected_observability_link_ids = set()
    selected_k8s_cluster_ids = set()
    selected_k8s_namespaces = defaultdict(set)
    selected_docker_host_ids = set()
    selected_task_resource_environment_ids = set()
    if use_knowledge_env:
        selected_env = {config.name for config in selected_knowledge_configs}
        for config in selected_knowledge_configs:
            for environment in _clean_list(config.event_environments):
                selected_event_environments.add(environment)
                event_env_to_graph[environment] = config.name
                source_env_to_graph.setdefault(environment, config.name)
            for environment in _clean_list(config.alert_environments):
                selected_alert_environments.add(environment)
                alert_env_to_graph[environment] = config.name
                source_env_to_graph.setdefault(environment, config.name)
            if is_system_posture_enabled():
                for environment in _clean_list(getattr(config, 'posture_environments', []) or []):
                    selected_posture_environments.add(environment)
                    source_env_to_graph.setdefault(environment, config.name)
            selected_grafana_folders.update(_clean_list(config.grafana_folder_keys))
            selected_metric_datasource_ids.update(_int_list(getattr(config, 'metric_datasource_ids', []) or []))
            selected_log_datasource_ids.update(_int_list(config.log_datasource_ids))
            selected_tracing_datasource_ids.update(_int_list(config.tracing_datasource_ids))
            selected_observability_link_ids.update(_int_list(getattr(config, 'observability_link_ids', []) or []))
            config_k8s_cluster_ids = _int_list(config.k8s_cluster_ids)
            selected_k8s_cluster_ids.update(config_k8s_cluster_ids)
            for cluster_id in config_k8s_cluster_ids:
                selected_k8s_namespaces[cluster_id].update(_namespaces_for_cluster(config, cluster_id))
            selected_docker_host_ids.update(_int_list(config.docker_host_ids))
            selected_task_resource_environment_ids.update(_int_list(getattr(config, 'task_resource_environment_ids', []) or []))

    if use_knowledge_env and selected_observability_link_ids:
        for link in ObservabilityDataSourceLink.objects.filter(id__in=selected_observability_link_ids, is_enabled=True):
            selected_log_datasource_ids.add(link.log_datasource_id)
            selected_tracing_datasource_ids.add(link.tracing_datasource_id)

    def graph_environment(source_environment, kind=''):
        environment = _clean(source_environment, UNKNOWN_ENV)
        if not use_knowledge_env:
            return environment
        if kind == 'event':
            return event_env_to_graph.get(environment, environment)
        if kind == 'alert':
            return alert_env_to_graph.get(environment, environment)
        return source_env_to_graph.get(environment, environment)

    nodes = {}
    edges = {}
    context_by_service = defaultdict(Counter)
    records_by_service = defaultdict(lambda: {
        'systems': Counter(),
        'environments': Counter(),
        'capabilities': Counter(),
        'examples': [],
    })

    def add_node(node_id, label, kind, category='', route='', status='', metric=0, description='', **extra):
        existing = nodes.get(node_id)
        if existing:
            existing['metric'] = max(existing.get('metric') or 0, metric or 0)
            if description and not existing.get('description'):
                existing['description'] = description
            for key in ('system_name', 'business_line', 'environment', 'service'):
                if extra.get(key) and not existing.get(key):
                    existing[key] = extra[key]
            return existing
        nodes[node_id] = {
            'id': node_id,
            'label': label,
            'kind': kind,
            'category': category or kind,
            'route': route,
            'status': status,
            'metric': metric or 0,
            'description': description,
            **extra,
        }
        return nodes[node_id]

    def add_edge(source, target, label, relation='related', weight=1):
        if not source or not target or source == target:
            return
        edge_id = f'{source}->{target}:{relation}:{label}'
        if edge_id in edges:
            edges[edge_id]['weight'] += weight
            return
        edges[edge_id] = {
            'id': edge_id,
            'source': source,
            'target': target,
            'label': label,
            'relation': relation,
            'weight': weight,
        }

    def add_capability_context(capability, system_name='', environment='', service='', count=1, example=''):
        system_name = _clean(system_name, UNKNOWN_SYSTEM)
        environment = _clean(environment, UNKNOWN_ENV)
        service = _clean(service, UNKNOWN_SERVICE)

        if not (
            _matches_filters(system_name, selected_system)
            and _matches_filters(environment, selected_env)
            and _matches_filters(service, selected_service)
        ):
            return

        env_id = _node_key('environment', environment)
        system_id = _node_key('system', environment, system_name)
        service_id = _node_key('service', environment, system_name, service)
        capability_id = _node_key('capability', capability)

        add_node(env_id, environment, 'environment', '环境', metric=count, environment=environment)
        add_node(
            system_id,
            system_name,
            'system',
            '系统',
            metric=count,
            system_name=system_name,
            business_line=system_name,
            environment=environment,
        )
        add_node(
            service_id,
            service,
            'service',
            '服务',
            metric=count,
            system_name=system_name,
            business_line=system_name,
            environment=environment,
            service=service,
        )
        add_edge(env_id, system_id, '包含系统', 'environment_system', count)
        add_edge(system_id, service_id, '承载服务', 'system_service', count)
        add_edge(service_id, capability_id, '产生数据', 'service_capability', count)

        record = records_by_service[service_id]
        record['systems'][system_name] += count
        record['environments'][environment] += count
        record['capabilities'][capability] += count
        _append_unique(record['examples'], example)

    def ensure_service_context_node(service, system_name='', environment='', count=1, description=''):
        system_name = _clean(system_name, UNKNOWN_SYSTEM)
        environment = _clean(environment, UNKNOWN_ENV)
        service = _clean(service, UNKNOWN_SERVICE)

        if not (
            _matches_filters(system_name, selected_system)
            and _matches_filters(environment, selected_env)
            and _matches_filters(service, selected_service)
        ):
            return None, None, None

        env_id = _node_key('environment', environment)
        system_id = _node_key('system', environment, system_name)
        service_id = _node_key('service', environment, system_name, service)

        add_node(env_id, environment, 'environment', '环境', metric=count, environment=environment)
        add_node(
            system_id,
            system_name,
            'system',
            '系统',
            metric=count,
            system_name=system_name,
            business_line=system_name,
            environment=environment,
        )
        add_node(
            service_id,
            service,
            'service',
            '服务',
            metric=count,
            description=description,
            system_name=system_name,
            business_line=system_name,
            environment=environment,
            service=service,
        )
        add_edge(env_id, system_id, '包含系统', 'environment_system', count)
        add_edge(system_id, service_id, '承载服务', 'system_service', count)
        return env_id, system_id, service_id

    def remember_service_context(service, system_name='', environment='', count=1):
        service = _clean(service)
        system_name = _clean(system_name)
        environment = _clean(environment)
        if not service or not (system_name or environment):
            return
        context_by_service[service][(system_name, environment)] += count

    def resolve_service_context(service):
        service = _clean(service)
        if not service or service not in context_by_service:
            return '', ''
        contexts = context_by_service[service]
        explicit_contexts = Counter({
            context: count
            for context, count in contexts.items()
            if context[0] and context[0] != service_fallback_system_name()
        })
        if explicit_contexts:
            return explicit_contexts.most_common(1)[0][0]
        return contexts.most_common(1)[0][0]

    alert_queryset = Alert.objects.order_by('-created_at')
    event_queryset = (
        EventRecord.objects
        .filter(is_demo=False)
        .exclude(source_type=EventRecord.SOURCE_SEED)
        .order_by('-occurred_at')
    )
    posture_queryset = SystemPostureSystem.objects.filter(is_enabled=True).order_by('sort_order', 'name') if is_system_posture_enabled() else SystemPostureSystem.objects.none()
    if use_knowledge_env:
        alert_queryset = alert_queryset.filter(environment__in=selected_alert_environments) if selected_alert_environments else Alert.objects.none()
        event_queryset = event_queryset.filter(environment__in=selected_event_environments) if selected_event_environments else EventRecord.objects.none()
        source_environments = selected_posture_environments if is_system_posture_enabled() else set()
        posture_queryset = posture_queryset.filter(environment__in=source_environments) if source_environments else SystemPostureSystem.objects.none()
    alert_records = list(alert_queryset[:200])
    event_records = list(event_queryset[:240])
    posture_systems = list(posture_queryset)

    k8s_clusters = list(K8sCluster.objects.filter(id__in=selected_k8s_cluster_ids).order_by('name', 'id')) if use_knowledge_env and selected_k8s_cluster_ids else []
    docker_hosts = list(DockerHost.objects.filter(id__in=selected_docker_host_ids).order_by('name', 'id')) if use_knowledge_env and selected_docker_host_ids else []
    task_resource_env_groups = list(TaskResourceGroup.objects.filter(id__in=selected_task_resource_environment_ids, group_type=TaskResourceGroup.GROUP_ENVIRONMENT).order_by('sort_order', 'name', 'id')) if use_knowledge_env and selected_task_resource_environment_ids else []
    infrastructure_inventory = _cached_external_batch([
        (
            ('k8s_pods', cluster.id),
            f'aiops:kg:fast:k8s:{cluster.id}:pods',
            lambda cluster=cluster: _k8s_cluster_pods(cluster),
            [],
        )
        for cluster in k8s_clusters
    ] + [
        (
            ('k8s_workloads', cluster.id),
            f'aiops:kg:fast:k8s:{cluster.id}:workloads',
            lambda cluster=cluster: _k8s_cluster_workloads(cluster),
            [],
        )
        for cluster in k8s_clusters
    ] + [
        (
            ('k8s_configmaps', cluster.id),
            f'aiops:kg:fast:k8s:{cluster.id}:configmaps',
            lambda cluster=cluster: _k8s_cluster_configmaps(cluster),
            [],
        )
        for cluster in k8s_clusters
    ] + [
        (
            ('k8s_nodes', cluster.id),
            f'aiops:kg:fast:k8s:{cluster.id}:nodes',
            lambda cluster=cluster: _k8s_cluster_nodes(cluster),
            [],
        )
        for cluster in k8s_clusters
    ] + [
        (
            ('docker_containers', host.id),
            f'aiops:kg:fast:docker:{host.id}:containers',
            lambda host=host: _docker_host_containers(host),
            [],
        )
        for host in docker_hosts
    ], timeout=FAST_EXTERNAL_TIMEOUT)
    k8s_pod_cache = {
        cluster.id: _filter_pods_by_namespaces(
            infrastructure_inventory.get(('k8s_pods', cluster.id), []),
            selected_k8s_namespaces.get(cluster.id),
        )
        for cluster in k8s_clusters
    }
    k8s_workload_cache = {
        cluster.id: _filter_workloads_by_namespaces(
            infrastructure_inventory.get(('k8s_workloads', cluster.id), []),
            selected_k8s_namespaces.get(cluster.id),
        )
        for cluster in k8s_clusters
    }
    k8s_configmap_cache = {
        cluster.id: _filter_configmaps_by_namespaces(
            infrastructure_inventory.get(('k8s_configmaps', cluster.id), []),
            selected_k8s_namespaces.get(cluster.id),
        )
        for cluster in k8s_clusters
    }
    k8s_node_cache = {
        cluster.id: infrastructure_inventory.get(('k8s_nodes', cluster.id), [])
        for cluster in k8s_clusters
    }
    docker_container_cache = {
        host.id: infrastructure_inventory.get(('docker_containers', host.id), [])
        for host in docker_hosts
    }
    tracing_datasource_queryset = TracingDataSource.objects.filter(is_enabled=True).order_by('provider', 'name')
    if use_knowledge_env:
        tracing_datasource_queryset = tracing_datasource_queryset.filter(id__in=selected_tracing_datasource_ids) if selected_tracing_datasource_ids else TracingDataSource.objects.none()
    tracing_datasources = [
        datasource
        for datasource in tracing_datasource_queryset
        if not _is_demoish_text(datasource.name, datasource.description, datasource.provider)
    ]

    def associated_config_names(field_name, item_id):
        if not use_knowledge_env:
            return []
        matched = [
            config.name
            for config in selected_knowledge_configs
            if item_id in _int_list(getattr(config, field_name, []))
        ]
        return matched or sorted(selected_env)

    def service_fallback_system_name():
        return UNASSIGNED_SYSTEM

    runtime_services = set()
    runtime_service_systems = {}
    infra_discovered_services = {}
    runtime_components = {}
    tracing_catalogs = _load_tracing_catalogs(tracing_datasources) if use_knowledge_env else {}
    tracing_discovered_services = _discover_tracing_services(tracing_datasources, tracing_catalogs) if use_knowledge_env else {}
    tracing_discovered_components = _discover_tracing_components(tracing_datasources, tracing_catalogs) if use_knowledge_env else {}

    def merge_runtime_component(component):
        component_id = component.get('id')
        if not component_id:
            return
        current = runtime_components.get(component_id)
        if not current:
            runtime_components[component_id] = component
            return
        current['count'] = (current.get('count') or 0) + (component.get('count') or 0)
        current['sources'].update(component.get('sources') or {})
        current['services'].update(component.get('services') or set())
        current['environments'].update(component.get('environments') or set())
        current['infra_ids'].update(component.get('infra_ids') or set())
        current['deploy_node_ids'].update(component.get('deploy_node_ids') or set())
        if component.get('status') and not current.get('status'):
            current['status'] = component.get('status')
        for item in component.get('details') or []:
            if item not in current['details'] and len(current['details']) < 8:
                current['details'].append(item)

    for component in tracing_discovered_components.values():
        merge_runtime_component(component)
    use_tracing_service_catalog = bool(tracing_discovered_services)

    def remember_infra_discovered_service(service_name, info, environments):
        discovered = infra_discovered_services.setdefault(service_name, {'count': 0, 'source': info.get('source')})
        discovered['count'] = (discovered.get('count') or 0) + (info.get('count') or 0)
        if info.get('system_name') and not discovered.get('system_name'):
            discovered['system_name'] = info.get('system_name')
        for example in info.get('examples') or []:
            _append_unique(discovered.setdefault('examples', []), example)
        if environments:
            discovered.setdefault('environments', set()).update(environments)
        return discovered

    for cluster in k8s_clusters:
        infra_id = _node_key('infrastructure', 'k8s', cluster.id)
        for component_id, component in _discover_k8s_components(
            cluster,
            workloads=k8s_workload_cache.get(cluster.id),
            pods=k8s_pod_cache.get(cluster.id),
        ).items():
            component['infra_ids'].add(infra_id)
            merge_runtime_component(component)
        for service_name, info in _discover_k8s_services(cluster, workloads=k8s_workload_cache.get(cluster.id)).items():
            config_names = associated_config_names('k8s_cluster_ids', cluster.id)
            remember_infra_discovered_service(service_name, info, config_names)
            if not use_tracing_service_catalog:
                runtime_services.add(service_name)
                system_name = _clean(info.get('system_name'))
                if system_name:
                    runtime_service_systems[service_name] = system_name
                else:
                    runtime_service_systems.setdefault(service_name, service_fallback_system_name())
                for config_name in config_names:
                    remember_service_context(service_name, system_name or service_fallback_system_name(), config_name, 1)
    for host in docker_hosts:
        infra_id = _node_key('infrastructure', 'docker', host.id)
        for component_id, component in _discover_docker_components(host, containers=docker_container_cache.get(host.id)).items():
            component['infra_ids'].add(infra_id)
            merge_runtime_component(component)
        for service_name, info in _discover_docker_services(host, containers=docker_container_cache.get(host.id)).items():
            config_names = associated_config_names('docker_host_ids', host.id)
            remember_infra_discovered_service(service_name, info, config_names)
            if not use_tracing_service_catalog:
                runtime_services.add(service_name)
                system_name = _clean(info.get('system_name'))
                if system_name:
                    runtime_service_systems[service_name] = system_name
                else:
                    runtime_service_systems.setdefault(service_name, service_fallback_system_name())
                for config_name in config_names:
                    remember_service_context(service_name, system_name or service_fallback_system_name(), config_name, 1)
    for service_name, info in tracing_discovered_services.items():
        runtime_services.add(service_name)
        for datasource in tracing_datasources:
            if datasource.name not in info.get('datasources', []):
                continue
            for config_name in associated_config_names('tracing_datasource_ids', datasource.id):
                system_name = _clean(info.get('system_name'))
                if system_name:
                    runtime_service_systems[service_name] = system_name
                else:
                    runtime_service_systems.setdefault(service_name, service_fallback_system_name())
                remember_service_context(service_name, system_name or service_fallback_system_name(), config_name, info.get('count') or 1)

    configmap_runtime_links = []

    for event in event_records:
        service_name = _clean(event.application)
        if _is_microservice_name(service_name) and (not use_knowledge_env or not runtime_services):
            runtime_services.add(service_name)
            if _clean(event.business_line):
                runtime_service_systems[service_name] = _clean(event.business_line)
    for system in posture_systems:
        service_specs = system.service_specs if isinstance(system.service_specs, list) else []
        for service in service_specs:
            service_name = _clean(service.get('name') or service.get('id'))
            if _is_microservice_name(service_name) and (not use_knowledge_env or not runtime_services):
                runtime_services.add(service_name)
                runtime_service_systems.setdefault(service_name, _clean(system.name))

    def matching_runtime_service_name(service):
        service = _clean(service)
        if not use_knowledge_env or not runtime_services:
            return service
        if service in runtime_services:
            return service
        return next(
            (
                runtime_service
                for runtime_service in sorted(runtime_services)
                if _service_names_related(runtime_service, service)
            ),
            '',
        )

    if use_knowledge_env:
        for service_name, info in infra_discovered_services.items():
            system_name = _clean(info.get('system_name'))
            if not system_name:
                continue
            matched_service_name = matching_runtime_service_name(service_name)
            if matched_service_name and matched_service_name in runtime_services:
                runtime_service_systems[matched_service_name] = system_name
                for environment in (info.get('environments') or selected_env):
                    remember_service_context(matched_service_name, system_name, environment, 2)

    for alert in alert_records:
        matched_service_name = matching_runtime_service_name(alert.service or alert.resource or alert.title)
        if not use_knowledge_env or matched_service_name in runtime_services:
            remember_service_context(matched_service_name, alert.business_line, graph_environment(alert.environment, 'alert'))
    for event in event_records:
        service_name = _clean(event.application)
        matched_service_name = matching_runtime_service_name(service_name or event.resource_name or event.resource_type or event.module)
        if not use_knowledge_env or matched_service_name in runtime_services:
            remember_service_context(matched_service_name, event.business_line, graph_environment(event.environment, 'event'), 3)
    for system in posture_systems:
        system_environment = graph_environment(system.environment, 'posture')
        remember_service_context(system.name, system.name, system_environment, 2)
        service_specs = system.service_specs if isinstance(system.service_specs, list) else []
        for service in service_specs:
            service_name = _clean(service.get('name') or service.get('id'))
            matched_service_name = matching_runtime_service_name(service_name)
            if not use_knowledge_env or matched_service_name in runtime_services:
                remember_service_context(matched_service_name, system.name, system_environment)
        dependencies = system.dependencies if isinstance(system.dependencies, list) else []
        for dependency in dependencies:
            classification = _classify_runtime_component(
                dependency.get('kind'),
                dependency.get('name'),
                dependency.get('id'),
                dependency.get('role'),
            )
            if not classification:
                continue
            _append_runtime_component(
                runtime_components,
                name=_clean(dependency.get('name') or dependency.get('id')) or classification['name'],
                technology=classification['technology'],
                component_type=classification['component_type'],
                source='posture',
                environment=system_environment,
                status=_clean(dependency.get('base_status') or dependency.get('status')),
                details=[
                    {'label': '来源', 'value': '系统态势依赖'},
                    {'label': '系统', 'value': _clean(system.name) or '-'},
                    {'label': '类型', 'value': _clean(dependency.get('kind')) or classification['component_type']},
                ],
            )

    if use_knowledge_env:
        for cluster in k8s_clusters:
            deployments = Deployment.objects.select_related('cluster', 'docker_host').filter(
                is_current=True,
                deploy_mode='k8s',
            ).order_by('-id')[:120]
            for deployment in deployments:
                cluster_name = _deployment_cluster_name(deployment)
                if cluster.id != getattr(deployment, 'cluster_id', None) and cluster_name != _clean(cluster.name):
                    continue
                service_name = _clean(deployment.app_name)
                if not service_name:
                    continue
                allowed_namespaces = selected_k8s_namespaces.get(cluster.id) or set()
                deployment_namespace = _clean(getattr(deployment, 'namespace', ''))
                if allowed_namespaces and deployment_namespace and deployment_namespace not in allowed_namespaces:
                    continue
                matched_service_name = matching_runtime_service_name(service_name)
                if not use_tracing_service_catalog:
                    runtime_services.add(service_name)
                    matched_service_name = service_name
                if matched_service_name:
                    remember_service_context(
                        matched_service_name,
                        _clean(getattr(deployment, 'business_line', '')),
                        next(iter(selected_env), ''),
                        2,
                    )

        for host in docker_hosts:
            deployments = Deployment.objects.select_related('cluster', 'docker_host').filter(
                is_current=True,
                deploy_mode='docker_compose',
            ).filter(
                Q(docker_host_id=host.id) | Q(host__hostname=host.name) | Q(host__ip_address=host.ip_address)
            ).order_by('-id')[:120]
            for deployment in deployments:
                service_name = _clean(deployment.app_name)
                if not service_name:
                    continue
                matched_service_name = matching_runtime_service_name(service_name)
                if not use_tracing_service_catalog:
                    runtime_services.add(service_name)
                    matched_service_name = service_name
                if matched_service_name:
                    remember_service_context(
                        matched_service_name,
                        _clean(getattr(deployment, 'business_line', '')),
                        next(iter(selected_env), ''),
                        2,
                    )

    configured_environment_options = [config.name for config in knowledge_env_configs]
    default_environment = next((config.name for config in knowledge_env_configs if getattr(config, 'is_default', False)), '')
    discovered_environment_options = sorted({
        environment
        for counter in context_by_service.values()
        for _, environment in counter
        if environment and not _is_invalid_environment(environment)
    })
    available_environment_options = configured_environment_options or discovered_environment_options

    if not selected_env:
        return _empty_graph({'environments': available_environment_options, 'default_environment': default_environment})

    for key, label, kind, route in CAPABILITY_DEFS:
        add_node(_node_key('capability', key), label, kind, '数据来源', route=route)

    infrastructure_node_ids = []
    k8s_member_node_ids = {}

    def task_resource_is_represented(resource, concrete_names, concrete_ips, concrete_cluster_ids):
        if not (concrete_names or concrete_ips or concrete_cluster_ids):
            return False
        name = _clean(resource.name)
        ip_address = _clean(resource.ip_address)
        if name and name in concrete_names:
            return True
        if ip_address and ip_address in concrete_ips:
            return True
        if resource.resource_type == TaskResource.RESOURCE_K8S and getattr(resource, 'cluster_id', None) in concrete_cluster_ids:
            return True
        return False

    def task_resource_category(resource):
        return '任务中心 K8s' if resource.resource_type == TaskResource.RESOURCE_K8S else '任务中心主机'

    def task_resource_infra_type(resource):
        return 'task_resource_k8s' if resource.resource_type == TaskResource.RESOURCE_K8S else 'task_resource_host'

    for config in selected_knowledge_configs:
        environment = config.name
        env_id = _node_key('environment', environment)
        add_node(env_id, environment, 'environment', '环境', environment=environment)
        concrete_infra_names = set()
        concrete_infra_ips = set()
        concrete_cluster_ids = set()

        posture_keys = _clean_list(getattr(config, 'posture_environments', []) or []) if is_system_posture_enabled() else []
        posture_environment_map = {
            item.key: item
            for item in SystemPostureEnvironment.objects.filter(key__in=posture_keys).order_by('sort_order', 'id')
        } if posture_keys else {}
        for posture_key in posture_keys:
            posture_env = posture_environment_map.get(posture_key)
            label = posture_env.name if posture_env else posture_key
            node_id = _node_key('posture_env', posture_key)
            system_count = sum(1 for system in posture_systems if _clean(system.environment) == posture_key)
            add_node(
                node_id,
                label,
                'posture',
                '系统态势',
                route='/observability/system-posture',
                status='enabled' if (not posture_env or posture_env.is_enabled) else 'disabled',
                metric=system_count,
                description=f'系统态势环境：{label}，关联 {system_count} 个系统',
                environment=environment,
                source_environment=posture_key,
            )
            add_edge(env_id, node_id, '关联系统态势', 'environment_observability', max(system_count, 1))

        for cluster in k8s_clusters:
            node_id = _node_key('infrastructure', 'k8s', cluster.id)
            concrete_cluster_ids.add(cluster.id)
            concrete_infra_names.add(_clean(cluster.name))
            api_host = _url_hostname(cluster.api_server)
            if api_host:
                concrete_infra_ips.add(api_host)
            add_node(
                node_id,
                cluster.name,
                'infrastructure',
                'K8s 集群',
                route='/k8s',
                status=cluster.status,
                description=cluster.description or cluster.api_server,
                environment=environment,
                infra_type='k8s',
                details=[
                    {'label': '类型', 'value': 'K8s 集群'},
                    {'label': 'API Server', 'value': cluster.api_server or '-'},
                    {'label': '状态', 'value': cluster.get_status_display() if hasattr(cluster, 'get_status_display') else cluster.status},
                ],
            )
            add_edge(env_id, node_id, '运行于', 'environment_infrastructure', 2)
            infrastructure_node_ids.append(node_id)
            cluster_nodes = k8s_node_cache.get(cluster.id, [])
            for cluster_node in cluster_nodes[:12]:
                member_id = _node_key('infrastructure', 'k8s_host', cluster.id, cluster_node.get('name'))
                concrete_infra_names.add(_clean(cluster_node.get('name')))
                concrete_infra_ips.add(_clean(cluster_node.get('internal_ip')))
                add_node(
                    member_id,
                    cluster_node.get('name') or 'unknown-node',
                    'infrastructure',
                    'K8s 主机',
                    route='/k8s',
                    status=cluster_node.get('status', ''),
                    description=f"{cluster.name} / {cluster_node.get('internal_ip') or '-'}",
                    environment=environment,
                    infra_type='k8s_host',
                    details=[
                        {'label': '所属集群', 'value': cluster.name},
                        {'label': '主机 IP', 'value': cluster_node.get('internal_ip') or '-'},
                        {'label': '角色', 'value': cluster_node.get('roles') or '-'},
                        {'label': '状态', 'value': cluster_node.get('status') or '-'},
                        {'label': '版本', 'value': cluster_node.get('version') or '-'},
                    ],
                )
                k8s_member_node_ids.setdefault(cluster.id, {})[_clean(cluster_node.get('name'))] = member_id
                add_edge(node_id, member_id, '包含主机', 'infrastructure_member', 1)

        for host in docker_hosts:
            node_id = _node_key('infrastructure', 'docker', host.id)
            concrete_infra_names.add(_clean(host.name))
            concrete_infra_ips.add(_clean(host.ip_address))
            add_node(
                node_id,
                host.name,
                'infrastructure',
                'Docker 环境',
                route='/containers/docker',
                status=host.status,
                description=host.description or host.ip_address,
                environment=environment,
                infra_type='docker',
                details=[
                    {'label': '类型', 'value': 'Docker 环境'},
                    {'label': 'IP 地址', 'value': host.ip_address or '-'},
                    {'label': '状态', 'value': host.get_status_display() if hasattr(host, 'get_status_display') else host.status},
                    {'label': 'Docker API', 'value': host.docker_api_version or '-'},
                ],
            )
            add_edge(env_id, node_id, '运行于', 'environment_infrastructure', 2)
            infrastructure_node_ids.append(node_id)

        for resource_env in task_resource_env_groups:
            resources = list(
                TaskResource.objects
                .select_related('system', 'cluster')
                .filter(environment=resource_env)
                .only(
                    'id',
                    'name',
                    'resource_type',
                    'status',
                    'ip_address',
                    'namespace',
                    'description',
                    'system__name',
                    'cluster__name',
                    'cluster_id',
                )
                .order_by('resource_type', 'name', 'id')
            )
            resource_env_node_id = ''
            if _clean(resource_env.name) != _clean(environment):
                resource_env_node_id = _node_key('infrastructure', 'task_resource_env', resource_env.id)
                add_node(
                    resource_env_node_id,
                    resource_env.name,
                    'infrastructure',
                    '资源底座环境',
                    route='/tasks/resources',
                    status='enabled',
                    metric=len(resources),
                    description=f'任务中心资源底座环境：{resource_env.name}',
                    environment=environment,
                    source_environment=resource_env.name,
                    infra_type='task_resource_environment',
                    details=[
                        {'label': '来源', 'value': '任务中心资源底座'},
                        {'label': '资源环境', 'value': resource_env.name},
                    ],
                )
                add_edge(env_id, resource_env_node_id, '关联资源底座', 'environment_resource_base', 1)
                infrastructure_node_ids.append(resource_env_node_id)
            for resource in resources:
                if task_resource_is_represented(resource, concrete_infra_names, concrete_infra_ips, concrete_cluster_ids):
                    continue
                node_id = _node_key('infrastructure', 'task_resource', resource.id)
                details = [
                    {'label': '来源', 'value': '任务中心资源底座'},
                    {'label': '资源类型', 'value': 'K8s' if resource.resource_type == TaskResource.RESOURCE_K8S else '主机'},
                    {'label': '资源环境', 'value': resource_env.name},
                    {'label': '系统', 'value': resource.system.name if resource.system_id else '-'},
                    {'label': '状态', 'value': resource.get_status_display() if hasattr(resource, 'get_status_display') else resource.status},
                ]
                if resource.ip_address:
                    details.append({'label': 'IP 地址', 'value': str(resource.ip_address)})
                if resource.resource_type == TaskResource.RESOURCE_K8S:
                    details.extend([
                        {'label': 'K8s 集群', 'value': resource.cluster.name if resource.cluster_id else '-'},
                        {'label': '命名空间', 'value': resource.namespace or '-'},
                    ])
                add_node(
                    node_id,
                    resource.name,
                    'infrastructure',
                    task_resource_category(resource),
                    route='/tasks/resources',
                    status=resource.status,
                    metric=1,
                    description=resource.description or f'任务中心资源底座资源：{resource.name}',
                    environment=environment,
                    source_environment=resource_env.name,
                    system_name=resource.system.name if resource.system_id else '',
                    infra_type=task_resource_infra_type(resource),
                    details=details,
                )
                add_edge(env_id, node_id, '关联资源底座', 'environment_resource_base', 1)
                if resource_env_node_id:
                    add_edge(resource_env_node_id, node_id, '包含资源', 'infrastructure_member', 1)
                infrastructure_node_ids.append(node_id)

    def ensure_runtime_component_node(component):
        component_id = component.get('id') or _node_key('runtime_component', component.get('name'))
        source_labels = {
            'tracing': 'Tracing',
            'k8s': 'K8s',
            'docker': 'Docker',
            'posture': '系统态势',
            'marketplace': '平台部署',
        }
        sources = [
            source_labels.get(key, key)
            for key, _ in (component.get('sources') or Counter()).most_common()
        ]
        details = list(component.get('details') or [])
        if sources:
            details.insert(0, {'label': '识别来源', 'value': ' / '.join(sources[:4])})
        details.insert(0, {'label': '类型', 'value': component.get('component_type') or '中间件'})
        details.insert(0, {'label': '技术', 'value': component.get('technology') or component.get('name')})
        add_node(
            component_id,
            component.get('name') or component.get('technology') or 'runtime-component',
            'runtime_component',
            component.get('component_type') or '中间件 / DB',
            status=component.get('status') or 'identified',
            metric=component.get('count') or 1,
            description=f"{component.get('technology') or component.get('name')}，来源：{' / '.join(sources) if sources else '自动识别'}",
            environment=next(iter(component.get('environments') or selected_env), ''),
            runtime_type=component.get('component_type') or '中间件',
            technology=component.get('technology') or component.get('name'),
            details=details[:8],
        )
        deploy_node_ids = component.get('deploy_node_ids') or set()
        for deploy_node_id in deploy_node_ids:
            if deploy_node_id in nodes:
                add_edge(component_id, deploy_node_id, '部署在', 'service_deployment', 2)
        if not deploy_node_ids:
            for infra_node_id in component.get('infra_ids') or []:
                if infra_node_id in nodes:
                    add_edge(component_id, infra_node_id, '部署在', 'service_deployment', 1)
        for service_name in component.get('services') or []:
            service_id = ensure_runtime_service_node(service_name, 'Tracing 识别到组件依赖')
            if service_id:
                add_edge(service_id, component_id, '服务依赖', 'service_runtime', 2)
        return component_id

    def add_runtime_component_node(deployment, infra_node_id, cluster=None):
        template = deployment.template
        category = _clean(template.category)
        component_type = 'DB' if category == 'database' else '中间件'
        release_name = _clean(deployment.release_name) or _clean(template.name)
        namespace = _clean(deployment.namespace)
        label = release_name if release_name == template.name else f'{template.name} / {release_name}'
        component_id = _node_key('runtime_component', 'marketplace', deployment.id)
        details = [
            {'label': '识别来源', 'value': '平台部署'},
            {'label': '技术', 'value': template.name},
            {'label': '类型', 'value': component_type},
            {'label': '版本', 'value': deployment.version},
            {'label': '状态', 'value': deployment.get_status_display() if hasattr(deployment, 'get_status_display') else deployment.status},
        ]
        if namespace:
            details.append({'label': '命名空间', 'value': namespace})
        add_node(
            component_id,
            label,
            'runtime_component',
            component_type,
            status=deployment.status,
            metric=deployment.replicas or 1,
            description=deployment.target_display,
            environment=next(iter(selected_env), ''),
            runtime_type=component_type,
            technology=template.name,
            details=details,
        )
        host_node_ids = []
        if cluster:
            host_node_ids = _match_k8s_host_node_ids(
                cluster,
                k8s_member_node_ids.get(cluster.id, {}),
                _clean(deployment.release_name),
                _clean(template.name),
                namespace=namespace,
                allow_fallback=True,
                pods=k8s_pod_cache.get(cluster.id),
            )
        if host_node_ids:
            for host_node_id in host_node_ids:
                add_edge(component_id, host_node_id, '部署在', 'service_deployment', 2)
        elif str(infra_node_id).startswith('infrastructure:docker'):
            add_edge(component_id, infra_node_id, '部署在', 'service_deployment', 2)

    if use_knowledge_env and infrastructure_node_ids:
        infra_by_k8s = {_node_key('infrastructure', 'k8s', cluster.id): cluster for cluster in k8s_clusters}
        for node_id, cluster in infra_by_k8s.items():
            deployments = ServiceDeployment.objects.select_related('template', 'cluster', 'host').filter(
                deploy_mode='k8s',
                cluster_id=cluster.id,
            ).exclude(status__in=['pending', 'removing']).order_by('template__category', 'template__name', 'id')[:80]
            for deployment in deployments:
                allowed_namespaces = selected_k8s_namespaces.get(cluster.id) or set()
                deployment_namespace = _clean(deployment.namespace)
                if allowed_namespaces and deployment_namespace and deployment_namespace not in allowed_namespaces:
                    continue
                add_runtime_component_node(deployment, node_id, cluster=cluster)

        for host in docker_hosts:
            node_id = _node_key('infrastructure', 'docker', host.id)
            deployments = ServiceDeployment.objects.select_related('template', 'cluster', 'host').filter(
                deploy_mode='docker_compose',
            ).filter(
                Q(host__hostname=host.name) | Q(host__ip_address=host.ip_address)
            ).exclude(status__in=['pending', 'removing']).order_by('template__category', 'template__name', 'id')[:80]
            for deployment in deployments:
                add_runtime_component_node(deployment, node_id)

    log_datasource_queryset = LogDataSource.objects.filter(is_enabled=True).order_by('provider', 'name')
    if use_knowledge_env:
        log_datasource_queryset = log_datasource_queryset.filter(id__in=selected_log_datasource_ids) if selected_log_datasource_ids else LogDataSource.objects.none()
    metric_datasource_queryset = MetricDataSource.objects.filter(is_enabled=True).order_by('environment', '-is_default', 'name')
    if use_knowledge_env:
        metric_datasource_queryset = metric_datasource_queryset.filter(id__in=selected_metric_datasource_ids) if selected_metric_datasource_ids else MetricDataSource.objects.none()
    for datasource in metric_datasource_queryset:
        if _is_demoish_text(datasource.name, datasource.description, datasource.provider):
            continue
        node_id = _node_key('metric_ds', datasource.id)
        add_node(
            node_id,
            datasource.name,
            'datasource',
            '指标数据源',
            route='/observability/metrics',
            status='enabled',
            description=datasource.description,
            provider=datasource.provider,
            environment=datasource.environment,
        )
        add_edge(_node_key('capability', 'metrics'), node_id, '接入指标源', 'capability_datasource')
        if use_knowledge_env:
            for config_name in associated_config_names('metric_datasource_ids', datasource.id):
                add_edge(_node_key('environment', config_name), node_id, '关联指标源', 'environment_observability')
    for datasource in log_datasource_queryset:
        if _is_demoish_text(datasource.name, datasource.description, datasource.provider):
            continue
        node_id = _node_key('log_ds', datasource.id)
        add_node(
            node_id,
            datasource.name,
            'datasource',
            '日志数据源',
            route='/logs/datasources',
            status='enabled',
            description=datasource.description,
            provider=datasource.provider,
        )
        add_edge(_node_key('capability', 'logs'), node_id, '接入日志源', 'capability_datasource')

    for datasource in tracing_datasources:
        node_id = _node_key('trace_ds', datasource.id)
        add_node(
            node_id,
            datasource.name,
            'datasource',
            '链路数据源',
            route='/observability/tracing/datasources',
            status='enabled',
            description=datasource.description,
            provider=datasource.provider,
        )
        add_edge(_node_key('capability', 'tracing'), node_id, '接入链路源', 'capability_datasource')

    dashboard_nodes = {}
    dashboard_folder_counts = Counter()

    def add_dashboard_folder_node(folder_name):
        folder_name = _matched_configured_folder(folder_name, selected_grafana_folders if use_knowledge_env else None)
        if not folder_name:
            return ''
        node_id = _node_key('dashboard_folder', folder_name)
        node = add_node(
            node_id,
            folder_name,
            'dashboard',
            'Grafana 看板目录',
            route='/observability/grafana',
            status='enabled',
            metric=dashboard_folder_counts[folder_name],
            description=f'看板目录：{folder_name}',
        )
        node['metric'] = dashboard_folder_counts[folder_name]
        node['description'] = f'看板目录：{folder_name}，包含 {dashboard_folder_counts[folder_name]} 个看板'
        add_edge(_node_key('capability', 'dashboards'), node_id, '展示看板', 'capability_dashboard')
        return node_id

    for setting in GrafanaSetting.objects.filter(enabled=True).order_by('name'):
        folders = setting.folders if isinstance(setting.folders, list) else []
        for folder in folders:
            add_dashboard_folder_node(folder.get('path') or folder.get('folder') or folder.get('name'))
        dashboards = setting.dashboards if isinstance(setting.dashboards, list) else []
        for dashboard in dashboards:
            if _is_demoish_text(dashboard.get('key'), dashboard.get('title'), dashboard.get('name'), dashboard.get('description')):
                continue
            dashboard_folder = _clean(dashboard.get('folder'))
            key = _clean(dashboard.get('key') or dashboard.get('uid') or dashboard.get('title') or dashboard.get('name'))
            if not key or not dashboard_folder:
                continue
            folder_name = _matched_configured_folder(dashboard_folder, selected_grafana_folders if use_knowledge_env else None)
            if use_knowledge_env and not folder_name:
                continue
            dashboard_folder_counts[folder_name] += 1
            node_id = add_dashboard_folder_node(folder_name)
            if node_id:
                dashboard_nodes[key] = node_id

    default_system_name = ''
    if use_knowledge_env:
        system_counter = Counter()
        for event in event_records:
            system_counter[_clean(event.business_line)] += 1
        for alert in alert_records:
            system_counter[_clean(alert.business_line)] += 1
        for system in posture_systems:
            system_counter[_clean(system.name)] += 1
        system_counter.pop('', None)
        system_counter.pop(UNKNOWN_SYSTEM, None)
        if system_counter:
            default_system_name = system_counter.most_common(1)[0][0]
        elif selected_knowledge_configs:
            default_system_name = service_fallback_system_name()

    inferred_service_names = {
        service_name
        for service_name in (
            list(runtime_services)
            + list(context_by_service.keys())
            + list(runtime_service_systems.keys())
        )
        if _clean(service_name) and _is_microservice_name(service_name)
    }
    if use_knowledge_env:
        for cluster in k8s_clusters:
            configmap_runtime_links.extend(
                _configmap_runtime_links(
                    k8s_configmap_cache.get(cluster.id),
                    inferred_service_names,
                    runtime_components,
                )
            )

    def ensure_runtime_service_node(service_name, description=''):
        service_name = _clean(service_name)
        if not service_name:
            return None
        system_name, environment = resolve_service_context(service_name)
        environment = environment or next(iter(selected_env), '')
        system_name = (
            system_name
            or runtime_service_systems.get(service_name)
            or default_system_name
            or service_fallback_system_name()
        )
        _, _, service_id = ensure_service_context_node(
            service_name,
            system_name,
            environment,
            1,
            description,
        )
        return service_id

    for component in runtime_components.values():
        ensure_runtime_component_node(component)
    for link in configmap_runtime_links:
        if link.get('component_id') not in nodes:
            continue
        service_id = ensure_runtime_service_node(link.get('service_name'), 'ConfigMap 识别到组件依赖')
        if service_id:
            add_edge(service_id, link.get('component_id'), '服务依赖', 'service_runtime', 2)

    if use_knowledge_env:
        if not use_tracing_service_catalog:
            for service_name in sorted(infra_discovered_services):
                ensure_runtime_service_node(service_name, '容器基础设施识别到服务')
        for service_name, info in sorted(tracing_discovered_services.items()):
            system_name, environment = resolve_service_context(service_name)
            environment = environment or next(iter(selected_env), '')
            system_name = system_name or runtime_service_systems.get(service_name) or default_system_name or service_fallback_system_name()
            add_capability_context(
                'tracing',
                system_name,
                environment,
                service_name,
                info.get('count') or 1,
                '链路追踪识别到服务',
            )

    if use_knowledge_env:
        for cluster in k8s_clusters:
            infra_id = _node_key('infrastructure', 'k8s', cluster.id)
            deployments = Deployment.objects.select_related('cluster', 'docker_host').filter(
                is_current=True,
                deploy_mode='k8s',
            ).order_by('-id')[:120]
            for deployment in deployments:
                cluster_name = _deployment_cluster_name(deployment)
                if cluster.id != getattr(deployment, 'cluster_id', None) and cluster_name != _clean(cluster.name):
                    continue
                service_name = _clean(deployment.app_name)
                if not service_name:
                    continue
                graph_service_name = matching_runtime_service_name(service_name) if use_tracing_service_catalog else service_name
                if use_tracing_service_catalog and not graph_service_name:
                    continue
                allowed_namespaces = selected_k8s_namespaces.get(cluster.id) or set()
                deployment_namespace = _clean(getattr(deployment, 'namespace', ''))
                if allowed_namespaces and deployment_namespace and deployment_namespace not in allowed_namespaces:
                    continue
                if not use_tracing_service_catalog:
                    runtime_services.add(graph_service_name)
                remember_service_context(
                    graph_service_name,
                    _clean(getattr(deployment, 'business_line', '')) or default_system_name,
                    next(iter(selected_env), ''),
                    2,
                )
                inferred_service_names.add(graph_service_name)
                service_id = ensure_runtime_service_node(
                    graph_service_name,
                    f'当前发布：{deployment.release_name or deployment.app_name}',
                )
                if service_id:
                    host_node_ids = _service_host_node_ids(
                        cluster,
                        deployment,
                        k8s_member_node_ids.get(cluster.id, {}),
                        pods=k8s_pod_cache.get(cluster.id),
                    )
                    if host_node_ids:
                        for host_node_id in host_node_ids:
                            add_edge(service_id, host_node_id, '部署在', 'service_deployment', 2)
                    else:
                        add_edge(service_id, infra_id, '部署在', 'service_deployment', 2)

        for host in docker_hosts:
            infra_id = _node_key('infrastructure', 'docker', host.id)
            deployments = Deployment.objects.select_related('cluster', 'docker_host').filter(
                is_current=True,
                deploy_mode='docker_compose',
            ).filter(
                Q(docker_host_id=host.id) | Q(host__hostname=host.name) | Q(host__ip_address=host.ip_address)
            ).order_by('-id')[:120]
            for deployment in deployments:
                service_name = _clean(deployment.app_name)
                if not service_name:
                    continue
                graph_service_name = matching_runtime_service_name(service_name) if use_tracing_service_catalog else service_name
                if use_tracing_service_catalog and not graph_service_name:
                    continue
                if not use_tracing_service_catalog:
                    runtime_services.add(graph_service_name)
                remember_service_context(
                    graph_service_name,
                    _clean(getattr(deployment, 'business_line', '')) or default_system_name,
                    next(iter(selected_env), ''),
                    2,
                )
                inferred_service_names.add(graph_service_name)
                service_id = ensure_runtime_service_node(
                    graph_service_name,
                    f'当前发布：{deployment.app_name}',
                )
                if service_id:
                    if _docker_service_matches_host(host, graph_service_name, containers=docker_container_cache.get(host.id)):
                        add_edge(service_id, infra_id, '部署在', 'service_deployment', 2)
                    else:
                        add_edge(service_id, infra_id, '部署在', 'service_deployment', 2)

        for cluster in k8s_clusters:
            member_node_ids = k8s_member_node_ids.get(cluster.id, {})
            for service_name in sorted(inferred_service_names):
                host_node_ids = _service_host_node_ids_for_service(
                    cluster,
                    service_name,
                    member_node_ids,
                    pods=k8s_pod_cache.get(cluster.id),
                )
                if not host_node_ids:
                    continue
                service_id = ensure_runtime_service_node(service_name, '基础设施接口识别到服务部署主机')
                if not service_id:
                    continue
                for host_node_id in host_node_ids:
                    add_edge(service_id, host_node_id, '部署在', 'service_deployment', 2)

        for host in docker_hosts:
            infra_id = _node_key('infrastructure', 'docker', host.id)
            for service_name in sorted(inferred_service_names):
                if not _docker_service_matches_host(host, service_name, containers=docker_container_cache.get(host.id)):
                    continue
                service_id = ensure_runtime_service_node(service_name, 'Docker 运行环境识别到服务部署主机')
                if service_id:
                    add_edge(service_id, infra_id, '部署在', 'service_deployment', 2)

    if use_knowledge_env and selected_grafana_folders:
        for config in selected_knowledge_configs:
            for service_name in sorted(runtime_services):
                system_name, environment = resolve_service_context(service_name)
                add_capability_context(
                    'dashboards',
                    system_name or runtime_service_systems.get(service_name) or default_system_name or service_fallback_system_name(),
                    environment or config.name,
                    service_name,
                    1,
                    '看板：已关联环境监控目录',
                )

    link_queryset = ObservabilityDataSourceLink.objects.select_related('log_datasource', 'tracing_datasource').filter(is_enabled=True).order_by('-is_default', 'name')
    if use_knowledge_env:
        if selected_observability_link_ids:
            link_queryset = link_queryset.filter(id__in=selected_observability_link_ids)
        elif selected_log_datasource_ids and selected_tracing_datasource_ids:
            link_queryset = link_queryset.filter(
                log_datasource_id__in=selected_log_datasource_ids,
                tracing_datasource_id__in=selected_tracing_datasource_ids,
            )
        else:
            link_queryset = link_queryset.none()
    for link in link_queryset:
        if _is_demoish_text(
            getattr(link.log_datasource, 'name', ''),
            getattr(link.log_datasource, 'description', ''),
            getattr(link.tracing_datasource, 'name', ''),
            getattr(link.tracing_datasource, 'description', ''),
        ):
            continue
        log_id = _node_key('log_ds', link.log_datasource_id)
        trace_id = _node_key('trace_ds', link.tracing_datasource_id)
        if link.log_to_trace_enabled or link.trace_to_log_enabled:
            add_edge(log_id, trace_id, 'Trace ID 关联', 'observability_link', 3 if link.is_default else 1)
            if use_knowledge_env:
                for environment in selected_env:
                    add_edge(_node_key('environment', environment), log_id, '关联可观测性', 'environment_observability')
                    add_edge(_node_key('environment', environment), trace_id, '关联可观测性', 'environment_observability')
        dashboard_id = dashboard_nodes.get(link.grafana_dashboard_key)
        if dashboard_id:
            if use_knowledge_env:
                for environment in selected_env:
                    add_edge(_node_key('environment', environment), dashboard_id, '关联可观测性', 'environment_observability')
            if link.log_to_grafana_enabled or link.grafana_to_log_enabled:
                add_edge(log_id, dashboard_id, '日志看板跳转', 'observability_link')
            if link.trace_to_grafana_enabled or link.grafana_to_trace_enabled:
                add_edge(trace_id, dashboard_id, '链路看板跳转', 'observability_link')

    for entry in LogEntry.objects.order_by('-timestamp')[:200]:
        matched_service_name = matching_runtime_service_name(entry.service)
        if use_knowledge_env and matched_service_name not in runtime_services:
            continue
        system_name, environment = resolve_service_context(matched_service_name)
        add_capability_context(
            'logs',
            system_name,
            environment,
            matched_service_name,
            1,
            f'日志：{entry.service}',
        )

    for alert in alert_records:
        if _is_demoish_text(alert.title, alert.service, alert.resource, alert.message):
            continue
        matched_service_name = matching_runtime_service_name(alert.service or alert.resource or alert.title)
        if use_knowledge_env and matched_service_name not in runtime_services:
            continue
        system_name = alert.business_line
        environment = graph_environment(alert.environment, 'alert')
        if not (system_name and environment):
            resolved_system, resolved_env = resolve_service_context(matched_service_name)
            system_name = system_name or resolved_system
            environment = environment or resolved_env
        if use_knowledge_env and not system_name:
            system_name = default_system_name
        add_capability_context(
            'alerts',
            system_name,
            environment,
            matched_service_name,
            2 if alert.level == 'critical' and alert.status == Alert.STATUS_ACTIVE else 1,
            f'告警：{alert.title}',
        )

    for system in posture_systems:
        system_name = system.name
        system_environment = graph_environment(system.environment, 'posture')
        if not use_knowledge_env:
            add_capability_context('posture', system_name, system_environment, system.name, 2, f'系统态势：{system.name}')
        service_specs = system.service_specs if isinstance(system.service_specs, list) else []
        for service in service_specs:
            service_name = service.get('name') or service.get('id')
            matched_service_name = matching_runtime_service_name(service_name)
            if use_knowledge_env and matched_service_name not in runtime_services:
                continue
            add_capability_context('posture', system_name, system_environment, matched_service_name, 1, f'系统态势服务：{service_name}')
            system_service_id = _node_key('service', system_environment or UNKNOWN_ENV, system_name, system.name)
            service_id = _node_key('service', system_environment or UNKNOWN_ENV, system_name, matched_service_name or UNKNOWN_SERVICE)
            add_edge(system_service_id, service_id, '系统服务拆解', 'system_service')
        dependencies = system.dependencies if isinstance(system.dependencies, list) else []
        for dependency in dependencies:
            dep_name = dependency.get('name') or dependency.get('id')
            if use_knowledge_env:
                classification = _classify_runtime_component(
                    dependency.get('kind'),
                    dep_name,
                    dependency.get('role'),
                )
                if not classification:
                    continue
                component_id = _node_key(
                    'runtime_component',
                    _normalized_runtime_text(_clean(dep_name)) or _clean(dep_name) or classification['name'],
                )
                if component_id in nodes:
                    system_id = _node_key('system', system_environment or UNKNOWN_ENV, system_name)
                    add_edge(system_id, component_id, dependency.get('role') or '依赖组件', 'system_runtime', 1)
                continue
            add_capability_context('posture', system_name, system_environment, dep_name, 1, f'依赖：{dep_name}')
            system_service_id = _node_key('service', system_environment or UNKNOWN_ENV, system_name, system.name)
            dep_id = _node_key('service', system_environment or UNKNOWN_ENV, system_name, dep_name or UNKNOWN_SERVICE)
            add_edge(system_service_id, dep_id, dependency.get('role') or '依赖', 'system_dependency')

    for event in event_records:
        if _is_demoish_text(event.title, event.application, event.resource_name):
            continue
        event_service_name = _clean(event.application)
        matched_service_name = matching_runtime_service_name(event_service_name or event.resource_name or event.resource_type or event.module)
        if use_knowledge_env and matched_service_name not in runtime_services:
            continue
        capability = 'external_events' if event.source_type == EventRecord.SOURCE_EXTERNAL else 'internal_events'
        event_system_name = event.business_line or (default_system_name if use_knowledge_env else '')
        add_capability_context(
            capability,
            event_system_name,
            graph_environment(event.environment, 'event'),
            matched_service_name,
            2 if event.severity == EventRecord.SEVERITY_DANGER else 1,
            f'事件：{event.title}',
        )
        if use_knowledge_env:
            continue
        for related in event.related_resources or []:
            related_name = related.get('name') or related.get('id')
            if not related_name:
                continue
            add_capability_context(
                capability,
                event_system_name,
                graph_environment(event.environment, 'event'),
                related_name,
                1,
                f'关联资源：{related_name}',
            )

    event_source_queryset = EventSource.objects.filter(
        Q(enabled=True) | Q(source_kind=EventSource.KIND_BUILTIN)
    ).order_by('source_kind', 'source_type', 'name')
    event_source_catalog = {source.code: source for source in event_source_queryset}
    if use_knowledge_env:
        event_source_scope_records = [event for event in event_records if _clean(event.environment) in selected_event_environments]
        event_source_scope_records.extend(
            list(
                EventRecord.objects.filter(environment__in=selected_event_environments, source_type=EventRecord.SOURCE_SEED)
                .order_by('-occurred_at')[:120]
            )
        )
    else:
        event_source_scope_records = [event for event in event_records if _matches_filters(_clean(event.environment), selected_env)]
    active_event_source_codes = {
        code
        for code in (_event_source_code_for_event(event, event_source_catalog) for event in event_source_scope_records)
        if code
    }
    active_event_source_codes.update(
        _related_builtin_event_source_codes(
            event_source_scope_records,
            event_source_queryset,
            has_k8s=bool(k8s_clusters),
            has_hosts=bool(k8s_clusters or docker_hosts),
            has_deployments=bool(inferred_service_names),
        )
    )
    for source in event_source_queryset:
        if source.code not in active_event_source_codes:
            continue
        capability = 'external_events' if source.source_kind == EventSource.KIND_EXTERNAL else 'internal_events'
        node_id = _node_key('event_source', source.id)
        add_node(
            node_id,
            _graph_event_source_label(source),
            'event_source',
            '事件源',
            route='/events/sources',
            status=source.status,
            description=source.description,
        )
        add_edge(_node_key('capability', capability), node_id, '接入事件源', 'capability_event_source')
        if use_knowledge_env:
            for environment in selected_env:
                add_edge(_node_key('environment', environment), node_id, '关联事件源', 'environment_event_source')

    for service_id, record in records_by_service.items():
        service_node = nodes.get(service_id)
        if not service_node:
            continue
        service_node['metric'] = sum(record['capabilities'].values())
        service_node['description'] = ' / '.join(record['examples'][:3])
        service_node['capabilities'] = [
            {'name': key, 'count': count}
            for key, count in record['capabilities'].most_common()
        ]

    adjacency = defaultdict(set)
    for edge in edges.values():
        adjacency[edge['source']].add(edge['target'])
        adjacency[edge['target']].add(edge['source'])
    reachable_ids = set()
    pending = [_node_key('environment', environment) for environment in selected_env]
    while pending:
        current = pending.pop()
        if current in reachable_ids:
            continue
        if current not in nodes:
            continue
        reachable_ids.add(current)
        pending.extend(adjacency.get(current, set()) - reachable_ids)

    nodes = {node_id: node for node_id, node in nodes.items() if node_id in reachable_ids}
    edges = {
        edge_id: edge
        for edge_id, edge in edges.items()
        if edge['source'] in reachable_ids and edge['target'] in reachable_ids
    }

    explicit_service_keys = {
        (node.get('environment'), node.get('service') or node.get('label'))
        for node in nodes.values()
        if node.get('kind') == 'service'
        and node.get('system_name') != service_fallback_system_name()
        and (node.get('service') or node.get('label'))
    }
    duplicate_unassigned_service_ids = {
        node_id
        for node_id, node in nodes.items()
        if node.get('kind') == 'service'
        and node.get('system_name') == service_fallback_system_name()
        and (node.get('environment'), node.get('service') or node.get('label')) in explicit_service_keys
    }
    if duplicate_unassigned_service_ids:
        nodes = {
            node_id: node
            for node_id, node in nodes.items()
            if node_id not in duplicate_unassigned_service_ids
        }
        edges = {
            edge_id: edge
            for edge_id, edge in edges.items()
            if edge['source'] not in duplicate_unassigned_service_ids and edge['target'] not in duplicate_unassigned_service_ids
        }
        unassigned_system_ids_with_services = {
            _node_key('system', node.get('environment'), service_fallback_system_name())
            for node in nodes.values()
            if node.get('kind') == 'service' and node.get('system_name') == service_fallback_system_name()
        }
        removable_unassigned_system_ids = {
            node_id
            for node_id, node in nodes.items()
            if node.get('kind') == 'system'
            and node.get('system_name') == service_fallback_system_name()
            and node_id not in unassigned_system_ids_with_services
        }
        if removable_unassigned_system_ids:
            nodes = {
                node_id: node
                for node_id, node in nodes.items()
                if node_id not in removable_unassigned_system_ids
            }
            edges = {
                edge_id: edge
                for edge_id, edge in edges.items()
                if edge['source'] not in removable_unassigned_system_ids and edge['target'] not in removable_unassigned_system_ids
            }

    visible_capability_ids = set()
    if use_knowledge_env:
        for edge in edges.values():
            if edge.get('relation') in {'capability_datasource', 'capability_dashboard'}:
                for endpoint in [edge.get('source'), edge.get('target')]:
                    if str(endpoint or '').startswith('capability:'):
                        visible_capability_ids.add(endpoint)

    filtered_nodes = sorted(
        [
            node for node in nodes.values()
            if not str(node.get('id', '')).startswith('capability:') or node.get('id') in visible_capability_ids
        ],
        key=lambda item: (item['kind'], item['label'], item['id']),
    )
    visible_ids = {node['id'] for node in filtered_nodes}
    filtered_edges = [
        edge for edge in edges.values()
        if edge['source'] in visible_ids and edge['target'] in visible_ids
    ]
    if use_knowledge_env:
        _persist_environment_snapshots(selected_knowledge_configs, filtered_nodes, filtered_edges)

    system_options = sorted({
        node.get('system_name') or node.get('business_line') or node['label']
        for node in filtered_nodes
        if node['kind'] in {'system', 'service'} and (node.get('system_name') or node.get('business_line') or node['kind'] == 'system')
    })
    environment_options = sorted({
        node.get('environment') or node['label']
        for node in filtered_nodes
        if node['kind'] in {'environment', 'system', 'service'} and (node.get('environment') or node['kind'] == 'environment')
    })
    service_options = sorted({
        node.get('service') or node['label']
        for node in filtered_nodes
        if node['kind'] == 'service'
    })

    kind_counts = Counter(node['kind'] for node in filtered_nodes)
    result = {
        'nodes': filtered_nodes,
        'edges': filtered_edges,
        'summary': {
            'node_count': len(filtered_nodes),
            'edge_count': len(filtered_edges),
            'service_count': kind_counts.get('service', 0),
            'datasource_count': kind_counts.get('datasource', 0),
            'event_source_count': kind_counts.get('event_source', 0),
            'capability_count': len(CAPABILITY_DEFS),
            'infrastructure_count': kind_counts.get('infrastructure', 0),
            'runtime_component_count': kind_counts.get('runtime_component', 0),
        },
        'filters': {
            'systems': system_options,
            'business_lines': system_options,
            'environments': available_environment_options,
            'default_environment': default_environment,
            'services': service_options,
        },
        'relation_legend': [
            {'key': 'observability_link', 'label': '可观测性跳转配置'},
            {'key': 'environment_system', 'label': '环境包含系统'},
            {'key': 'system_service', 'label': '系统承载服务'},
            {'key': 'service_capability', 'label': '服务产生数据'},
            {'key': 'system_dependency', 'label': '系统依赖'},
            {'key': 'capability_datasource', 'label': '能力接入数据源'},
            {'key': 'capability_event_source', 'label': '能力接入事件源'},
            {'key': 'environment_observability', 'label': '环境关联可观测性'},
            {'key': 'environment_infrastructure', 'label': '环境运行于基础设施'},
            {'key': 'service_deployment', 'label': '部署在'},
            {'key': 'infrastructure_member', 'label': '集群包含主机'},
            {'key': 'service_runtime', 'label': '服务依赖'},
            {'key': 'system_runtime', 'label': '系统依赖运行组件'},
        ],
    }
    _cache_set(cache_key, result, GRAPH_RESPONSE_CACHE_TTL)
    return result
