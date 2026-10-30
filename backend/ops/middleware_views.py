from copy import deepcopy

from django.core.cache import cache
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from rbac.permissions import build_rbac_permission

MIDDLEWARE_DEMO_CACHE_KEY = 'ops:middleware:demo:state'
MIDDLEWARE_DEMO_CACHE_TTL = 86400


def _now_iso():
    return timezone.now().isoformat()


def _now_label():
    return timezone.localtime().strftime('%Y-%m-%d %H:%M')


MIDDLEWARE_DEMO_TEMPLATE = {
    'updated_at': '',
    'redis': {
        'clusters': [
            {'id': 'redis-cls-order', 'name': 'order-cache', 'environment': 'prod', 'status': 'healthy', 'mode': 'Redis Cluster', 'slot_coverage': '16384/16384', 'memory_total_gb': 96, 'ops_per_sec': 18234, 'hit_rate': 99.2},
            {'id': 'redis-cls-member', 'name': 'member-session', 'environment': 'prod', 'status': 'warning', 'mode': 'Master / Replica', 'slot_coverage': 'N/A', 'memory_total_gb': 48, 'ops_per_sec': 6640, 'hit_rate': 97.6},
        ],
        'instances': [
            {'id': 'redis-order-master', 'cluster': 'order-cache', 'environment': 'prod', 'name': 'redis-order-master', 'role': 'master', 'endpoint': '10.21.0.11:6379', 'version': '7.2.4', 'status': 'healthy', 'memory_usage': 68, 'qps': 18234, 'connections': 836, 'replication_delay_ms': 0, 'persistence': 'AOF + RDB', 'last_sync': '2026-03-28 08:36'},
            {'id': 'redis-order-replica-01', 'cluster': 'order-cache', 'environment': 'prod', 'name': 'redis-order-replica-01', 'role': 'replica', 'endpoint': '10.21.0.12:6379', 'version': '7.2.4', 'status': 'healthy', 'memory_usage': 64, 'qps': 17482, 'connections': 792, 'replication_delay_ms': 12, 'persistence': 'AOF + RDB', 'last_sync': '2026-03-28 08:36'},
            {'id': 'redis-member-master', 'cluster': 'member-session', 'environment': 'prod', 'name': 'redis-member-master', 'role': 'master', 'endpoint': '10.21.2.17:6379', 'version': '7.0.15', 'status': 'healthy', 'memory_usage': 71, 'qps': 6640, 'connections': 240, 'replication_delay_ms': 0, 'persistence': 'AOF', 'last_sync': '2026-03-28 08:31'},
            {'id': 'redis-member-replica-02', 'cluster': 'member-session', 'environment': 'prod', 'name': 'redis-member-replica-02', 'role': 'replica', 'endpoint': '10.21.2.18:6379', 'version': '7.0.15', 'status': 'warning', 'memory_usage': 72, 'qps': 6120, 'connections': 228, 'replication_delay_ms': 248, 'persistence': 'AOF', 'last_sync': '2026-03-28 08:19'},
        ],
        'hot_keys': [
            {'id': 'redis-hot-1', 'key': 'cart:active:city-310', 'cluster': 'order-cache', 'ops_per_sec': 4820, 'memory_kb': 320, 'risk': 'high'},
            {'id': 'redis-hot-2', 'key': 'member:session:token', 'cluster': 'member-session', 'ops_per_sec': 2310, 'memory_kb': 180, 'risk': 'medium'},
            {'id': 'redis-hot-3', 'key': 'promotion:sku:flash-sale', 'cluster': 'order-cache', 'ops_per_sec': 1880, 'memory_kb': 96, 'risk': 'medium'},
        ],
        'events': [
            {'id': 'redis-evt-1', 'time': '2026-03-28 08:41', 'level': 'warning', 'title': 'Replication delay raised', 'detail': 'redis-member-replica-02 delay reached 248ms.'},
            {'id': 'redis-evt-2', 'time': '2026-03-28 07:55', 'level': 'info', 'title': 'RDB snapshot finished', 'detail': 'Snapshot archive was flushed to object storage.'},
        ],
    },
    'rocketmq': {
        'clusters': [
            {'id': 'rmq-cls-trade', 'name': 'trade-mq', 'environment': 'prod', 'status': 'healthy', 'nameserver_count': 2, 'broker_count': 2, 'tps': 12400, 'topic_count': 128},
            {'id': 'rmq-cls-audit', 'name': 'audit-mq', 'environment': 'test', 'status': 'warning', 'nameserver_count': 2, 'broker_count': 1, 'tps': 940, 'topic_count': 36},
        ],
        'brokers': [
            {'id': 'rmq-trade-master-a', 'cluster': 'trade-mq', 'environment': 'prod', 'name': 'broker-a', 'role': 'master', 'endpoint': '10.22.0.21:10911', 'version': '5.2.0', 'status': 'healthy', 'tps': 12400, 'topic_count': 128, 'disk_usage': 63, 'consumer_lag': 120},
            {'id': 'rmq-trade-slave-a', 'cluster': 'trade-mq', 'environment': 'prod', 'name': 'broker-a-s', 'role': 'slave', 'endpoint': '10.22.0.22:10911', 'version': '5.2.0', 'status': 'healthy', 'tps': 11820, 'topic_count': 128, 'disk_usage': 58, 'consumer_lag': 120},
            {'id': 'rmq-audit-master', 'cluster': 'audit-mq', 'environment': 'test', 'name': 'broker-c', 'role': 'master', 'endpoint': '10.22.1.31:10911', 'version': '5.1.4', 'status': 'warning', 'tps': 940, 'topic_count': 36, 'disk_usage': 81, 'consumer_lag': 4820},
        ],
        'consumer_groups': [
            {'id': 'cg-trade-billing', 'cluster': 'trade-mq', 'group': 'GID_BILLING', 'topic': 'trade-order-events', 'clients': 18, 'retry': 0, 'lag': 120, 'status': 'healthy'},
            {'id': 'cg-trade-stock', 'cluster': 'trade-mq', 'group': 'GID_STOCK_SYNC', 'topic': 'trade-stock-events', 'clients': 11, 'retry': 2, 'lag': 840, 'status': 'warning'},
            {'id': 'cg-audit-etl', 'cluster': 'audit-mq', 'group': 'GID_AUDIT_ETL', 'topic': 'audit-log', 'clients': 4, 'retry': 3, 'lag': 4820, 'status': 'warning'},
        ],
        'topics': [
            {'id': 'topic-trade-order', 'cluster': 'trade-mq', 'name': 'trade-order-events', 'messages_24h': '810M', 'retention_hours': 72, 'dead_letter': 0},
            {'id': 'topic-trade-stock', 'cluster': 'trade-mq', 'name': 'trade-stock-events', 'messages_24h': '240M', 'retention_hours': 72, 'dead_letter': 18},
            {'id': 'topic-audit-log', 'cluster': 'audit-mq', 'name': 'audit-log', 'messages_24h': '46M', 'retention_hours': 168, 'dead_letter': 214},
        ],
        'events': [
            {'id': 'rmq-evt-1', 'time': '2026-03-28 08:46', 'level': 'warning', 'title': 'Consumer lag increased', 'detail': 'GID_AUDIT_ETL lag reached 4820.'},
            {'id': 'rmq-evt-2', 'time': '2026-03-28 08:20', 'level': 'info', 'title': 'Broker inspection finished', 'detail': 'broker-a disk usage dropped back to 63%.'},
        ],
    },
    'elasticsearch': {
        'clusters': [
            {'id': 'es-search-prod', 'name': 'search-prod', 'environment': 'prod', 'health': 'green', 'nodes': 6, 'indices': 218, 'storage': '18.4TB', 'qps': 9480, 'unassigned_shards': 0, 'hot_threads': 1},
            {'id': 'es-observe-logs', 'name': 'observe-logs', 'environment': 'prod', 'health': 'yellow', 'nodes': 3, 'indices': 96, 'storage': '9.1TB', 'qps': 5220, 'unassigned_shards': 3, 'hot_threads': 7},
        ],
        'nodes': [
            {'id': 'es-search-01', 'cluster': 'search-prod', 'name': 'es-search-01', 'role': 'master,data_hot', 'endpoint': '10.23.0.11:9200', 'status': 'online', 'heap_usage': 58, 'cpu_usage': 29, 'disk_usage': 61},
            {'id': 'es-search-02', 'cluster': 'search-prod', 'name': 'es-search-02', 'role': 'data_hot,ingest', 'endpoint': '10.23.0.12:9200', 'status': 'online', 'heap_usage': 63, 'cpu_usage': 37, 'disk_usage': 64},
            {'id': 'es-observe-01', 'cluster': 'observe-logs', 'name': 'es-observe-01', 'role': 'master,data_hot', 'endpoint': '10.23.2.11:9200', 'status': 'online', 'heap_usage': 72, 'cpu_usage': 54, 'disk_usage': 76},
            {'id': 'es-observe-02', 'cluster': 'observe-logs', 'name': 'es-observe-02', 'role': 'data_hot,ingest', 'endpoint': '10.23.2.12:9200', 'status': 'online', 'heap_usage': 84, 'cpu_usage': 78, 'disk_usage': 81},
        ],
        'indices': [
            {'id': 'es-index-1', 'cluster': 'search-prod', 'name': 'product-search-2026.03.28', 'status': 'green', 'docs': '1.28B', 'size': '620GB', 'shards': '12/1', 'lifecycle': 'hot'},
            {'id': 'es-index-2', 'cluster': 'search-prod', 'name': 'suggest-search-2026.03.28', 'status': 'green', 'docs': '360M', 'size': '148GB', 'shards': '6/1', 'lifecycle': 'warm'},
            {'id': 'es-index-3', 'cluster': 'observe-logs', 'name': 'app-log-2026.03.28', 'status': 'yellow', 'docs': '2.84B', 'size': '1.8TB', 'shards': '18/1', 'lifecycle': 'hot'},
            {'id': 'es-index-4', 'cluster': 'observe-logs', 'name': 'audit-log-2026.03.28', 'status': 'yellow', 'docs': '420M', 'size': '420GB', 'shards': '8/1', 'lifecycle': 'warm'},
        ],
        'tasks': [
            {'id': 'es-task-1', 'cluster': 'observe-logs', 'name': 'rebalance-shards', 'progress': 62, 'status': 'running'},
            {'id': 'es-task-2', 'cluster': 'search-prod', 'name': 'ilm-rollover', 'progress': 100, 'status': 'completed'},
            {'id': 'es-task-3', 'cluster': 'observe-logs', 'name': 'snapshot-retention', 'progress': 45, 'status': 'warning'},
        ],
        'events': [
            {'id': 'es-evt-1', 'time': '2026-03-28 08:43', 'level': 'warning', 'title': 'Shard allocation degraded', 'detail': 'Three shards are still unassigned.'},
            {'id': 'es-evt-2', 'time': '2026-03-28 08:17', 'level': 'warning', 'title': 'Heap usage elevated', 'detail': 'es-observe-02 heap usage reached 84%.'},
        ],
    },
}

MIDDLEWARE_IMPORT_TEMPLATES = {
    'redis': {
        'clusters': {
            'ha-read': {'name': 'read-cache-template', 'environment': 'test', 'status': 'healthy', 'mode': 'Redis Cluster', 'slot_coverage': '16384/16384', 'memory_total_gb': 64, 'ops_per_sec': 15600, 'hit_rate': 99.4},
            'session': {'name': 'session-cache-template', 'environment': 'dev', 'status': 'healthy', 'mode': 'Sentinel', 'slot_coverage': 'N/A', 'memory_total_gb': 24, 'ops_per_sec': 4200, 'hit_rate': 98.3},
        },
        'instances': {
            'master': {'cluster': 'order-cache', 'name': 'redis-template-master', 'environment': 'test', 'role': 'master', 'endpoint': '10.88.0.10:6379', 'version': '7.2.4', 'status': 'healthy', 'memory_usage': 46, 'qps': 3600, 'connections': 180, 'replication_delay_ms': 0, 'persistence': 'AOF + RDB'},
            'replica': {'cluster': 'order-cache', 'name': 'redis-template-replica', 'environment': 'test', 'role': 'replica', 'endpoint': '10.88.0.11:6379', 'version': '7.2.4', 'status': 'healthy', 'memory_usage': 41, 'qps': 3200, 'connections': 150, 'replication_delay_ms': 12, 'persistence': 'AOF + RDB'},
        },
    },
    'rocketmq': {
        'clusters': {
            'trade': {'name': 'trade-template', 'environment': 'test', 'status': 'healthy', 'nameserver_count': 2, 'tps': 6800, 'topic_count': 42},
            'audit': {'name': 'audit-template', 'environment': 'dev', 'status': 'warning', 'nameserver_count': 2, 'tps': 1600, 'topic_count': 18},
        },
        'instances': {
            'master': {'cluster': 'trade-mq', 'name': 'broker-template-master', 'environment': 'test', 'role': 'master', 'endpoint': '10.89.0.20:10911', 'version': '5.2.0', 'status': 'healthy', 'tps': 3600, 'topic_count': 28, 'disk_usage': 46, 'consumer_lag': 0},
            'slave': {'cluster': 'trade-mq', 'name': 'broker-template-slave', 'environment': 'test', 'role': 'slave', 'endpoint': '10.89.0.21:10911', 'version': '5.2.0', 'status': 'healthy', 'tps': 3200, 'topic_count': 28, 'disk_usage': 40, 'consumer_lag': 80},
        },
    },
    'elasticsearch': {
        'clusters': {
            'search': {'name': 'search-template', 'environment': 'test', 'health': 'green', 'storage': '2.4TB', 'qps': 4200},
            'logs': {'name': 'logs-template', 'environment': 'dev', 'health': 'yellow', 'storage': '1.1TB', 'qps': 2100},
        },
        'instances': {
            'hot': {'cluster': 'search-prod', 'name': 'es-template-hot', 'role': 'data_hot,ingest', 'endpoint': '10.90.0.11:9200', 'status': 'online', 'heap_usage': 42, 'cpu_usage': 24, 'disk_usage': 38},
            'warm': {'cluster': 'search-prod', 'name': 'es-template-warm', 'role': 'data_warm', 'endpoint': '10.90.0.12:9200', 'status': 'online', 'heap_usage': 36, 'cpu_usage': 18, 'disk_usage': 34},
        },
    },
}


def _get_demo_state():
    cached = cache.get(MIDDLEWARE_DEMO_CACHE_KEY)
    if cached:
        return cached
    state = deepcopy(MIDDLEWARE_DEMO_TEMPLATE)
    state['updated_at'] = _now_iso()
    cache.set(MIDDLEWARE_DEMO_CACHE_KEY, state, MIDDLEWARE_DEMO_CACHE_TTL)
    return state


def _set_demo_state(state):
    state['updated_at'] = _now_iso()
    cache.set(MIDDLEWARE_DEMO_CACHE_KEY, state, MIDDLEWARE_DEMO_CACHE_TTL)


def _find_by_id(items, item_id):
    return next((item for item in items if item['id'] == item_id), None)


def _append_event(events, level, title, detail):
    events.insert(0, {'id': f"evt-{len(events) + 1}-{int(timezone.now().timestamp())}", 'time': _now_label(), 'level': level, 'title': title, 'detail': detail})
    del events[8:]


def _build_id(prefix):
    return f"{prefix}-{int(timezone.now().timestamp() * 1000)}"


def _ensure_unique_name(existing_names, base_name):
    candidate = base_name
    counter = 2
    while candidate in existing_names:
        candidate = f'{base_name}-{counter}'
        counter += 1
    return candidate


def _module_status(alerts):
    return 'warning' if alerts else 'healthy'


def _build_redis_alerts(data):
    alerts = []
    replica = next((item for item in data['instances'] if item['replication_delay_ms'] >= 100), None)
    if replica:
        alerts.append({'level': 'warning', 'title': 'Replication delay', 'message': f"{replica['name']} delay {replica['replication_delay_ms']}ms"})
    hot_key = next((item for item in data['hot_keys'] if item['risk'] == 'high'), None)
    if hot_key:
        alerts.append({'level': 'info', 'title': 'Hot key', 'message': f"{hot_key['key']} reached {hot_key['ops_per_sec']} ops/s"})
    return alerts


def _build_rocketmq_alerts(data):
    alerts = []
    lagging = next((item for item in data['consumer_groups'] if item['lag'] >= 1000), None)
    if lagging:
        alerts.append({'level': 'warning', 'title': 'Consumer lag', 'message': f"{lagging['group']} lag {lagging['lag']}"})
    topic = next((item for item in data['topics'] if item['dead_letter'] >= 100), None)
    if topic:
        alerts.append({'level': 'info', 'title': 'Dead letters', 'message': f"{topic['name']} dead letter {topic['dead_letter']}"})
    return alerts


def _build_es_alerts(data):
    alerts = []
    cluster = next((item for item in data['clusters'] if item['health'] != 'green'), None)
    if cluster:
        alerts.append({'level': 'warning', 'title': 'Cluster health', 'message': f"{cluster['name']} has {cluster['unassigned_shards']} unassigned shards"})
    node = next((item for item in data['nodes'] if item['heap_usage'] >= 80 or item['disk_usage'] >= 80), None)
    if node:
        alerts.append({'level': 'info', 'title': 'Node load', 'message': f"{node['name']} heap {node['heap_usage']}%, disk {node['disk_usage']}%"})
    return alerts


def _build_payload(state):
    redis_alerts = _build_redis_alerts(state['redis'])
    rocketmq_alerts = _build_rocketmq_alerts(state['rocketmq'])
    es_alerts = _build_es_alerts(state['elasticsearch'])
    return {
        'updated_at': state['updated_at'],
        'overview': {
            'modules': [
                {'key': 'redis', 'label': 'Redis', 'status': _module_status(redis_alerts), 'alert_count': len(redis_alerts)},
                {'key': 'rocketmq', 'label': 'RocketMQ', 'status': _module_status(rocketmq_alerts), 'alert_count': len(rocketmq_alerts)},
                {'key': 'elasticsearch', 'label': 'Elasticsearch', 'status': _module_status(es_alerts), 'alert_count': len(es_alerts)},
            ]
        },
        'redis': {'summary': {'cluster_count': len(state['redis']['clusters']), 'instance_count': len(state['redis']['instances']), 'warning_count': len(redis_alerts), 'peak_qps': max(item['qps'] for item in state['redis']['instances']), 'hot_key_count': len(state['redis']['hot_keys']), 'module_status': _module_status(redis_alerts)}, 'alerts': redis_alerts, 'clusters': state['redis']['clusters'], 'instances': state['redis']['instances'], 'hot_keys': state['redis']['hot_keys'], 'events': state['redis']['events']},
        'rocketmq': {'summary': {'cluster_count': len(state['rocketmq']['clusters']), 'broker_count': len(state['rocketmq']['brokers']), 'warning_count': len(rocketmq_alerts), 'peak_tps': max(item['tps'] for item in state['rocketmq']['brokers']), 'topic_count': len(state['rocketmq']['topics']), 'module_status': _module_status(rocketmq_alerts)}, 'alerts': rocketmq_alerts, 'clusters': state['rocketmq']['clusters'], 'brokers': state['rocketmq']['brokers'], 'consumer_groups': state['rocketmq']['consumer_groups'], 'topics': state['rocketmq']['topics'], 'events': state['rocketmq']['events']},
        'elasticsearch': {'summary': {'cluster_count': len(state['elasticsearch']['clusters']), 'node_count': len(state['elasticsearch']['nodes']), 'warning_count': len(es_alerts), 'peak_qps': max(item['qps'] for item in state['elasticsearch']['clusters']), 'index_count': len(state['elasticsearch']['indices']), 'module_status': _module_status(es_alerts)}, 'alerts': es_alerts, 'clusters': state['elasticsearch']['clusters'], 'nodes': state['elasticsearch']['nodes'], 'indices': state['elasticsearch']['indices'], 'tasks': state['elasticsearch']['tasks'], 'events': state['elasticsearch']['events']},
    }


def _sync_redis(state):
    for cluster in state['redis']['clusters']:
        items = [item for item in state['redis']['instances'] if item['cluster'] == cluster['name']]
        cluster['status'] = 'warning' if any(item['status'] != 'healthy' or item['replication_delay_ms'] >= 100 for item in items) else 'healthy'
        cluster['ops_per_sec'] = sum(item['qps'] for item in items)


def _sync_rocketmq(state):
    for cluster in state['rocketmq']['clusters']:
        brokers = [item for item in state['rocketmq']['brokers'] if item['cluster'] == cluster['name']]
        groups = [item for item in state['rocketmq']['consumer_groups'] if item['cluster'] == cluster['name']]
        cluster['status'] = 'warning' if any(item['status'] != 'healthy' or item['disk_usage'] >= 80 for item in brokers) or any(item['lag'] >= 1000 for item in groups) else 'healthy'
        cluster['tps'] = sum(item['tps'] for item in brokers)
        cluster['broker_count'] = len(brokers)
        cluster['topic_count'] = len([item for item in state['rocketmq']['topics'] if item['cluster'] == cluster['name']])


def _sync_es(state):
    for cluster in state['elasticsearch']['clusters']:
        nodes = [item for item in state['elasticsearch']['nodes'] if item['cluster'] == cluster['name']]
        indices = [item for item in state['elasticsearch']['indices'] if item['cluster'] == cluster['name']]
        cluster['unassigned_shards'] = sum(1 for item in indices if item['status'] != 'green')
        cluster['health'] = 'yellow' if cluster['unassigned_shards'] else 'green'
        cluster['hot_threads'] = sum(1 for item in nodes if item['heap_usage'] >= 80 or item['cpu_usage'] >= 75)
        cluster['nodes'] = len(nodes)
        cluster['indices'] = len(indices)


def _remove_by_id(items, item_id):
    before = len(items)
    items[:] = [item for item in items if item['id'] != item_id]
    return len(items) != before


def _redis_create_cluster(state, payload):
    name = str(payload.get('name', '')).strip()
    if not name:
        return None, 'Redis cluster name is required.'
    if any(item['name'] == name for item in state['redis']['clusters']):
        return None, 'Redis cluster already exists.'
    state['redis']['clusters'].insert(0, {
        'id': _build_id('redis-cls'),
        'name': name,
        'environment': payload.get('environment', 'test'),
        'status': payload.get('status', 'healthy'),
        'mode': payload.get('mode', 'Redis Cluster'),
        'slot_coverage': payload.get('slot_coverage', '16384/16384'),
        'memory_total_gb': int(payload.get('memory_total_gb') or 32),
        'ops_per_sec': int(payload.get('ops_per_sec') or 0),
        'hit_rate': float(payload.get('hit_rate') or 98.6),
    })
    _append_event(state['redis']['events'], 'info', f'{name} created', 'A new Redis demo cluster was added.')
    _sync_redis(state)
    return state, f'Redis cluster {name} created.'


def _redis_update_cluster(state, target_id, payload):
    cluster = _find_by_id(state['redis']['clusters'], target_id)
    if not cluster:
        return None, 'Redis cluster not found.'
    old_name = cluster['name']
    new_name = str(payload.get('name', old_name)).strip() or old_name
    if new_name != old_name and any(item['name'] == new_name for item in state['redis']['clusters']):
        return None, 'Redis cluster name already exists.'
    cluster.update({
        'name': new_name,
        'environment': payload.get('environment', cluster['environment']),
        'status': payload.get('status', cluster['status']),
        'mode': payload.get('mode', cluster['mode']),
        'slot_coverage': payload.get('slot_coverage', cluster['slot_coverage']),
        'memory_total_gb': int(payload.get('memory_total_gb') or cluster['memory_total_gb']),
        'ops_per_sec': int(payload.get('ops_per_sec') or cluster['ops_per_sec']),
        'hit_rate': float(payload.get('hit_rate') or cluster['hit_rate']),
    })
    if new_name != old_name:
        for item in state['redis']['instances']:
            if item['cluster'] == old_name:
                item['cluster'] = new_name
        for item in state['redis']['hot_keys']:
            if item['cluster'] == old_name:
                item['cluster'] = new_name
    _append_event(state['redis']['events'], 'info', f'{new_name} updated', 'Redis cluster configuration was updated.')
    _sync_redis(state)
    return state, f'Redis cluster {new_name} updated.'


def _redis_delete_cluster(state, target_id):
    cluster = _find_by_id(state['redis']['clusters'], target_id)
    if not cluster:
        return None, 'Redis cluster not found.'
    cluster_name = cluster['name']
    _remove_by_id(state['redis']['clusters'], target_id)
    state['redis']['instances'][:] = [item for item in state['redis']['instances'] if item['cluster'] != cluster_name]
    state['redis']['hot_keys'][:] = [item for item in state['redis']['hot_keys'] if item['cluster'] != cluster_name]
    _append_event(state['redis']['events'], 'warning', f'{cluster_name} removed', 'Redis cluster and related demo objects were deleted.')
    _sync_redis(state)
    return state, f'Redis cluster {cluster_name} deleted.'


def _redis_create_instance(state, payload):
    cluster_name = str(payload.get('cluster', '')).strip()
    name = str(payload.get('name', '')).strip()
    if not cluster_name or not name:
        return None, 'Redis cluster and instance name are required.'
    if not any(item['name'] == cluster_name for item in state['redis']['clusters']):
        return None, 'Target Redis cluster does not exist.'
    role = payload.get('role', 'replica')
    if role == 'master' and any(item['cluster'] == cluster_name and item['role'] == 'master' for item in state['redis']['instances']):
        return None, 'Redis cluster already has a master instance.'
    state['redis']['instances'].insert(0, {
        'id': _build_id('redis-ins'),
        'cluster': cluster_name,
        'environment': payload.get('environment', 'test'),
        'name': name,
        'role': role,
        'endpoint': payload.get('endpoint', '127.0.0.1:6379'),
        'version': payload.get('version', '7.2.4'),
        'status': payload.get('status', 'healthy'),
        'memory_usage': int(payload.get('memory_usage') or 48),
        'qps': int(payload.get('qps') or 1200),
        'connections': int(payload.get('connections') or 96),
        'replication_delay_ms': int(payload.get('replication_delay_ms') or 0),
        'persistence': payload.get('persistence', 'AOF'),
        'last_sync': _now_label(),
    })
    _append_event(state['redis']['events'], 'info', f'{name} added', f'Instance joined cluster {cluster_name}.')
    _sync_redis(state)
    return state, f'Redis instance {name} created.'


def _redis_update_instance(state, target_id, payload):
    target = _find_by_id(state['redis']['instances'], target_id)
    if not target:
        return None, 'Redis instance not found.'
    cluster_name = str(payload.get('cluster', target['cluster'])).strip() or target['cluster']
    if not any(item['name'] == cluster_name for item in state['redis']['clusters']):
        return None, 'Target Redis cluster does not exist.'
    role = payload.get('role', target['role'])
    if role == 'master':
        duplicate_master = next((item for item in state['redis']['instances'] if item['cluster'] == cluster_name and item['role'] == 'master' and item['id'] != target_id), None)
        if duplicate_master:
            return None, 'Redis cluster already has another master instance.'
    target.update({
        'cluster': cluster_name,
        'environment': payload.get('environment', target['environment']),
        'name': payload.get('name', target['name']) or target['name'],
        'role': role,
        'endpoint': payload.get('endpoint', target['endpoint']),
        'version': payload.get('version', target['version']),
        'status': payload.get('status', target['status']),
        'memory_usage': int(payload.get('memory_usage') or target['memory_usage']),
        'qps': int(payload.get('qps') or target['qps']),
        'connections': int(payload.get('connections') or target['connections']),
        'replication_delay_ms': int(payload.get('replication_delay_ms') or target['replication_delay_ms']),
        'persistence': payload.get('persistence', target['persistence']),
        'last_sync': _now_label(),
    })
    _append_event(state['redis']['events'], 'info', f"{target['name']} updated", 'Redis instance configuration was updated.')
    _sync_redis(state)
    return state, f"Redis instance {target['name']} updated."


def _redis_delete_instance(state, target_id):
    target = _find_by_id(state['redis']['instances'], target_id)
    if not target:
        return None, 'Redis instance not found.'
    instance_name = target['name']
    _remove_by_id(state['redis']['instances'], target_id)
    _append_event(state['redis']['events'], 'warning', f'{instance_name} removed', 'Redis instance was deleted from demo state.')
    _sync_redis(state)
    return state, f'Redis instance {instance_name} deleted.'


def _redis_import_template(state, payload):
    scope = payload.get('scope', 'cluster')
    template_key = payload.get('template_key')
    template = deepcopy(MIDDLEWARE_IMPORT_TEMPLATES['redis']['clusters' if scope == 'cluster' else 'instances'].get(template_key))
    if not template:
        return None, 'Redis template not found.'
    if scope == 'cluster':
        template['name'] = _ensure_unique_name([item['name'] for item in state['redis']['clusters']], template['name'])
        return _redis_create_cluster(state, template)
    template['name'] = _ensure_unique_name([item['name'] for item in state['redis']['instances']], template['name'])
    return _redis_create_instance(state, template)


def _redis_action(state, target_id, action_name, payload=None):
    payload = payload or {}
    if action_name == 'create_cluster':
        return _redis_create_cluster(state, payload)
    if action_name == 'import_template':
        return _redis_import_template(state, payload)
    if action_name == 'update_cluster':
        return _redis_update_cluster(state, target_id, payload)
    if action_name == 'delete_cluster':
        return _redis_delete_cluster(state, target_id)
    if action_name == 'create_instance':
        return _redis_create_instance(state, payload)
    if action_name == 'update_instance':
        return _redis_update_instance(state, target_id, payload)
    if action_name == 'delete_instance':
        return _redis_delete_instance(state, target_id)
    target = _find_by_id(state['redis']['instances'], target_id)
    if not target:
        return None, 'Redis instance not found.'
    if action_name == 'restart':
        target['status'] = 'healthy'
        target['replication_delay_ms'] = 0 if target['role'] == 'replica' else target['replication_delay_ms']
        target['last_sync'] = _now_label()
        _append_event(state['redis']['events'], 'info', f"{target['name']} restarted", 'Instance state recovered.')
    elif action_name == 'promote':
        if target['role'] != 'replica':
            return None, 'Only replica can be promoted.'
        master = next((item for item in state['redis']['instances'] if item['cluster'] == target['cluster'] and item['role'] == 'master'), None)
        if master:
            master['role'] = 'replica'
            master['status'] = 'warning'
            master['replication_delay_ms'] = 180
            master['last_sync'] = _now_label()
        target['role'] = 'master'
        target['status'] = 'healthy'
        target['replication_delay_ms'] = 0
        target['connections'] = int(target['connections'] * 1.2)
        target['last_sync'] = _now_label()
        _append_event(state['redis']['events'], 'warning', f"{target['cluster']} switched primary", f"{target['name']} is now the primary node.")
    elif action_name == 'resync':
        target['status'] = 'healthy'
        target['replication_delay_ms'] = 0
        target['last_sync'] = _now_label()
        _append_event(state['redis']['events'], 'info', f"{target['name']} resynced", 'Replica link returned to normal.')
    else:
        return None, 'Unsupported Redis action.'
    _sync_redis(state)
    return state, f"Redis action {action_name} completed."


def _rocketmq_create_cluster(state, payload):
    name = str(payload.get('name', '')).strip()
    if not name:
        return None, 'RocketMQ cluster name is required.'
    if any(item['name'] == name for item in state['rocketmq']['clusters']):
        return None, 'RocketMQ cluster already exists.'
    state['rocketmq']['clusters'].insert(0, {
        'id': _build_id('rmq-cls'),
        'name': name,
        'environment': payload.get('environment', 'test'),
        'status': payload.get('status', 'healthy'),
        'nameserver_count': int(payload.get('nameserver_count') or 2),
        'broker_count': 0,
        'tps': int(payload.get('tps') or 0),
        'topic_count': int(payload.get('topic_count') or 0),
    })
    _append_event(state['rocketmq']['events'], 'info', f'{name} created', 'A new RocketMQ demo cluster was added.')
    _sync_rocketmq(state)
    return state, f'RocketMQ cluster {name} created.'


def _rocketmq_update_cluster(state, target_id, payload):
    cluster = _find_by_id(state['rocketmq']['clusters'], target_id)
    if not cluster:
        return None, 'RocketMQ cluster not found.'
    old_name = cluster['name']
    new_name = str(payload.get('name', old_name)).strip() or old_name
    if new_name != old_name and any(item['name'] == new_name for item in state['rocketmq']['clusters']):
        return None, 'RocketMQ cluster name already exists.'
    cluster.update({
        'name': new_name,
        'environment': payload.get('environment', cluster['environment']),
        'status': payload.get('status', cluster['status']),
        'nameserver_count': int(payload.get('nameserver_count') or cluster['nameserver_count']),
        'tps': int(payload.get('tps') or cluster['tps']),
        'topic_count': int(payload.get('topic_count') or cluster['topic_count']),
    })
    if new_name != old_name:
        for collection in ('brokers', 'consumer_groups', 'topics'):
            for item in state['rocketmq'][collection]:
                if item['cluster'] == old_name:
                    item['cluster'] = new_name
    _append_event(state['rocketmq']['events'], 'info', f'{new_name} updated', 'RocketMQ cluster configuration was updated.')
    _sync_rocketmq(state)
    return state, f'RocketMQ cluster {new_name} updated.'


def _rocketmq_delete_cluster(state, target_id):
    cluster = _find_by_id(state['rocketmq']['clusters'], target_id)
    if not cluster:
        return None, 'RocketMQ cluster not found.'
    cluster_name = cluster['name']
    _remove_by_id(state['rocketmq']['clusters'], target_id)
    for collection in ('brokers', 'consumer_groups', 'topics'):
        state['rocketmq'][collection][:] = [item for item in state['rocketmq'][collection] if item['cluster'] != cluster_name]
    _append_event(state['rocketmq']['events'], 'warning', f'{cluster_name} removed', 'RocketMQ cluster and related demo objects were deleted.')
    _sync_rocketmq(state)
    return state, f'RocketMQ cluster {cluster_name} deleted.'


def _rocketmq_create_broker(state, payload):
    cluster_name = str(payload.get('cluster', '')).strip()
    name = str(payload.get('name', '')).strip()
    if not cluster_name or not name:
        return None, 'RocketMQ cluster and broker name are required.'
    if not any(item['name'] == cluster_name for item in state['rocketmq']['clusters']):
        return None, 'Target RocketMQ cluster does not exist.'
    state['rocketmq']['brokers'].insert(0, {
        'id': _build_id('rmq-broker'),
        'cluster': cluster_name,
        'environment': payload.get('environment', 'test'),
        'name': name,
        'role': payload.get('role', 'master'),
        'endpoint': payload.get('endpoint', '127.0.0.1:10911'),
        'version': payload.get('version', '5.2.0'),
        'status': payload.get('status', 'healthy'),
        'tps': int(payload.get('tps') or 900),
        'topic_count': int(payload.get('topic_count') or 16),
        'disk_usage': int(payload.get('disk_usage') or 42),
        'consumer_lag': int(payload.get('consumer_lag') or 0),
    })
    _append_event(state['rocketmq']['events'], 'info', f'{name} added', f'Broker joined cluster {cluster_name}.')
    _sync_rocketmq(state)
    return state, f'RocketMQ broker {name} created.'


def _rocketmq_update_broker(state, target_id, payload):
    target = _find_by_id(state['rocketmq']['brokers'], target_id)
    if not target:
        return None, 'RocketMQ broker not found.'
    cluster_name = str(payload.get('cluster', target['cluster'])).strip() or target['cluster']
    if not any(item['name'] == cluster_name for item in state['rocketmq']['clusters']):
        return None, 'Target RocketMQ cluster does not exist.'
    target.update({
        'cluster': cluster_name,
        'environment': payload.get('environment', target['environment']),
        'name': payload.get('name', target['name']) or target['name'],
        'role': payload.get('role', target['role']),
        'endpoint': payload.get('endpoint', target['endpoint']),
        'version': payload.get('version', target['version']),
        'status': payload.get('status', target['status']),
        'tps': int(payload.get('tps') or target['tps']),
        'topic_count': int(payload.get('topic_count') or target['topic_count']),
        'disk_usage': int(payload.get('disk_usage') or target['disk_usage']),
        'consumer_lag': int(payload.get('consumer_lag') or target['consumer_lag']),
    })
    _append_event(state['rocketmq']['events'], 'info', f"{target['name']} updated", 'RocketMQ broker configuration was updated.')
    _sync_rocketmq(state)
    return state, f"RocketMQ broker {target['name']} updated."


def _rocketmq_delete_broker(state, target_id):
    target = _find_by_id(state['rocketmq']['brokers'], target_id)
    if not target:
        return None, 'RocketMQ broker not found.'
    broker_name = target['name']
    _remove_by_id(state['rocketmq']['brokers'], target_id)
    _append_event(state['rocketmq']['events'], 'warning', f'{broker_name} removed', 'RocketMQ broker was deleted from demo state.')
    _sync_rocketmq(state)
    return state, f'RocketMQ broker {broker_name} deleted.'


def _rocketmq_import_template(state, payload):
    scope = payload.get('scope', 'cluster')
    template_key = payload.get('template_key')
    template = deepcopy(MIDDLEWARE_IMPORT_TEMPLATES['rocketmq']['clusters' if scope == 'cluster' else 'instances'].get(template_key))
    if not template:
        return None, 'RocketMQ template not found.'
    if scope == 'cluster':
        template['name'] = _ensure_unique_name([item['name'] for item in state['rocketmq']['clusters']], template['name'])
        return _rocketmq_create_cluster(state, template)
    template['name'] = _ensure_unique_name([item['name'] for item in state['rocketmq']['brokers']], template['name'])
    return _rocketmq_create_broker(state, template)


def _rocketmq_action(state, target_id, action_name, payload=None):
    payload = payload or {}
    if action_name == 'create_cluster':
        return _rocketmq_create_cluster(state, payload)
    if action_name == 'import_template':
        return _rocketmq_import_template(state, payload)
    if action_name == 'update_cluster':
        return _rocketmq_update_cluster(state, target_id, payload)
    if action_name == 'delete_cluster':
        return _rocketmq_delete_cluster(state, target_id)
    if action_name == 'create_instance':
        return _rocketmq_create_broker(state, payload)
    if action_name == 'update_instance':
        return _rocketmq_update_broker(state, target_id, payload)
    if action_name == 'delete_instance':
        return _rocketmq_delete_broker(state, target_id)
    target = _find_by_id(state['rocketmq']['brokers'], target_id)
    if not target:
        return None, 'RocketMQ broker not found.'
    if action_name == 'restart':
        target['status'] = 'healthy'
        target['disk_usage'] = max(target['disk_usage'] - 4, 42)
        target['consumer_lag'] = max(int(target['consumer_lag'] * 0.5), 0)
        _append_event(state['rocketmq']['events'], 'info', f"{target['name']} restarted", 'Broker metrics were refreshed.')
    elif action_name == 'rebalance':
        for group in state['rocketmq']['consumer_groups']:
            if group['cluster'] != target['cluster']:
                continue
            group['lag'] = max(int(group['lag'] * 0.2), 0)
            group['retry'] = 0 if group['lag'] < 500 else group['retry']
            group['status'] = 'healthy' if group['lag'] < 1000 else 'warning'
        target['consumer_lag'] = max(int(target['consumer_lag'] * 0.2), 0)
        target['status'] = 'healthy'
        _append_event(state['rocketmq']['events'], 'warning', f"{target['cluster']} rebalanced", 'Consumer lag dropped after queue redistribution.')
    else:
        return None, 'Unsupported RocketMQ action.'
    _sync_rocketmq(state)
    return state, f"RocketMQ action {action_name} completed."


def _elasticsearch_create_cluster(state, payload):
    name = str(payload.get('name', '')).strip()
    if not name:
        return None, 'Elasticsearch cluster name is required.'
    if any(item['name'] == name for item in state['elasticsearch']['clusters']):
        return None, 'Elasticsearch cluster already exists.'
    state['elasticsearch']['clusters'].insert(0, {
        'id': _build_id('es-cls'),
        'name': name,
        'environment': payload.get('environment', 'test'),
        'health': payload.get('health', 'green'),
        'nodes': 0,
        'indices': 0,
        'storage': payload.get('storage', '1.2TB'),
        'qps': int(payload.get('qps') or 0),
        'unassigned_shards': 0,
        'hot_threads': 0,
    })
    _append_event(state['elasticsearch']['events'], 'info', f'{name} created', 'A new Elasticsearch demo cluster was added.')
    _sync_es(state)
    return state, f'Elasticsearch cluster {name} created.'


def _elasticsearch_update_cluster(state, target_id, payload):
    cluster = _find_by_id(state['elasticsearch']['clusters'], target_id)
    if not cluster:
        return None, 'Elasticsearch cluster not found.'
    old_name = cluster['name']
    new_name = str(payload.get('name', old_name)).strip() or old_name
    if new_name != old_name and any(item['name'] == new_name for item in state['elasticsearch']['clusters']):
        return None, 'Elasticsearch cluster name already exists.'
    cluster.update({
        'name': new_name,
        'environment': payload.get('environment', cluster['environment']),
        'health': payload.get('health', cluster['health']),
        'storage': payload.get('storage', cluster['storage']),
        'qps': int(payload.get('qps') or cluster['qps']),
    })
    if new_name != old_name:
        for collection in ('nodes', 'indices', 'tasks'):
            for item in state['elasticsearch'][collection]:
                if item['cluster'] == old_name:
                    item['cluster'] = new_name
    _append_event(state['elasticsearch']['events'], 'info', f'{new_name} updated', 'Elasticsearch cluster configuration was updated.')
    _sync_es(state)
    return state, f'Elasticsearch cluster {new_name} updated.'


def _elasticsearch_delete_cluster(state, target_id):
    cluster = _find_by_id(state['elasticsearch']['clusters'], target_id)
    if not cluster:
        return None, 'Elasticsearch cluster not found.'
    cluster_name = cluster['name']
    _remove_by_id(state['elasticsearch']['clusters'], target_id)
    for collection in ('nodes', 'indices', 'tasks'):
        state['elasticsearch'][collection][:] = [item for item in state['elasticsearch'][collection] if item['cluster'] != cluster_name]
    _append_event(state['elasticsearch']['events'], 'warning', f'{cluster_name} removed', 'Elasticsearch cluster and related demo objects were deleted.')
    _sync_es(state)
    return state, f'Elasticsearch cluster {cluster_name} deleted.'


def _elasticsearch_create_node(state, payload):
    cluster_name = str(payload.get('cluster', '')).strip()
    name = str(payload.get('name', '')).strip()
    if not cluster_name or not name:
        return None, 'Elasticsearch cluster and node name are required.'
    if not any(item['name'] == cluster_name for item in state['elasticsearch']['clusters']):
        return None, 'Target Elasticsearch cluster does not exist.'
    state['elasticsearch']['nodes'].insert(0, {
        'id': _build_id('es-node'),
        'cluster': cluster_name,
        'name': name,
        'role': payload.get('role', 'data_hot,ingest'),
        'endpoint': payload.get('endpoint', '127.0.0.1:9200'),
        'status': payload.get('status', 'online'),
        'heap_usage': int(payload.get('heap_usage') or 36),
        'cpu_usage': int(payload.get('cpu_usage') or 22),
        'disk_usage': int(payload.get('disk_usage') or 40),
    })
    _append_event(state['elasticsearch']['events'], 'info', f'{name} added', f'Node joined cluster {cluster_name}.')
    _sync_es(state)
    return state, f'Elasticsearch node {name} created.'


def _elasticsearch_update_node(state, target_id, payload):
    target = _find_by_id(state['elasticsearch']['nodes'], target_id)
    if not target:
        return None, 'Elasticsearch node not found.'
    cluster_name = str(payload.get('cluster', target['cluster'])).strip() or target['cluster']
    if not any(item['name'] == cluster_name for item in state['elasticsearch']['clusters']):
        return None, 'Target Elasticsearch cluster does not exist.'
    target.update({
        'cluster': cluster_name,
        'name': payload.get('name', target['name']) or target['name'],
        'role': payload.get('role', target['role']),
        'endpoint': payload.get('endpoint', target['endpoint']),
        'status': payload.get('status', target['status']),
        'heap_usage': int(payload.get('heap_usage') or target['heap_usage']),
        'cpu_usage': int(payload.get('cpu_usage') or target['cpu_usage']),
        'disk_usage': int(payload.get('disk_usage') or target['disk_usage']),
    })
    _append_event(state['elasticsearch']['events'], 'info', f"{target['name']} updated", 'Elasticsearch node configuration was updated.')
    _sync_es(state)
    return state, f"Elasticsearch node {target['name']} updated."


def _elasticsearch_delete_node(state, target_id):
    target = _find_by_id(state['elasticsearch']['nodes'], target_id)
    if not target:
        return None, 'Elasticsearch node not found.'
    node_name = target['name']
    _remove_by_id(state['elasticsearch']['nodes'], target_id)
    _append_event(state['elasticsearch']['events'], 'warning', f'{node_name} removed', 'Elasticsearch node was deleted from demo state.')
    _sync_es(state)
    return state, f'Elasticsearch node {node_name} deleted.'


def _elasticsearch_import_template(state, payload):
    scope = payload.get('scope', 'cluster')
    template_key = payload.get('template_key')
    template = deepcopy(MIDDLEWARE_IMPORT_TEMPLATES['elasticsearch']['clusters' if scope == 'cluster' else 'instances'].get(template_key))
    if not template:
        return None, 'Elasticsearch template not found.'
    if scope == 'cluster':
        template['name'] = _ensure_unique_name([item['name'] for item in state['elasticsearch']['clusters']], template['name'])
        return _elasticsearch_create_cluster(state, template)
    template['name'] = _ensure_unique_name([item['name'] for item in state['elasticsearch']['nodes']], template['name'])
    return _elasticsearch_create_node(state, template)


def _elasticsearch_action(state, target_id, action_name, payload=None):
    payload = payload or {}
    if action_name == 'create_cluster':
        return _elasticsearch_create_cluster(state, payload)
    if action_name == 'import_template':
        return _elasticsearch_import_template(state, payload)
    if action_name == 'update_cluster':
        return _elasticsearch_update_cluster(state, target_id, payload)
    if action_name == 'delete_cluster':
        return _elasticsearch_delete_cluster(state, target_id)
    if action_name == 'create_instance':
        return _elasticsearch_create_node(state, payload)
    if action_name == 'update_instance':
        return _elasticsearch_update_node(state, target_id, payload)
    if action_name == 'delete_instance':
        return _elasticsearch_delete_node(state, target_id)
    if action_name == 'restart_node':
        target = _find_by_id(state['elasticsearch']['nodes'], target_id)
        if not target:
            return None, 'Elasticsearch node not found.'
        target['status'] = 'online'
        target['heap_usage'] = max(target['heap_usage'] - 18, 36)
        target['cpu_usage'] = max(target['cpu_usage'] - 20, 18)
        target['disk_usage'] = max(target['disk_usage'] - 6, 48)
        _append_event(state['elasticsearch']['events'], 'info', f"{target['name']} restarted", 'Node returned to the cluster.')
        _sync_es(state)
        return state, f"Elasticsearch action {action_name} completed."
    target = _find_by_id(state['elasticsearch']['clusters'], target_id)
    if not target:
        return None, 'Elasticsearch cluster not found.'
    if action_name == 'reroute':
        for index in state['elasticsearch']['indices']:
            if index['cluster'] == target['name']:
                index['status'] = 'green'
        for task in state['elasticsearch']['tasks']:
            if task['cluster'] == target['name']:
                task['progress'] = min(task['progress'] + 35, 100)
                task['status'] = 'completed' if task['progress'] == 100 else 'running'
        _append_event(state['elasticsearch']['events'], 'warning', f"{target['name']} rerouted", 'Shard placement has been recalculated.')
    elif action_name == 'rollover':
        new_index = {'id': f"{target['id']}-rollover-{len(state['elasticsearch']['indices']) + 1}", 'cluster': target['name'], 'name': f"{target['name']}-rollover-{timezone.localtime().strftime('%Y.%m.%d')}", 'status': 'green', 'docs': '0', 'size': '32GB', 'shards': '6/1', 'lifecycle': 'hot'}
        for index in state['elasticsearch']['indices']:
            if index['cluster'] == target['name'] and index['lifecycle'] == 'hot':
                index['lifecycle'] = 'warm'
                break
        state['elasticsearch']['indices'].insert(0, new_index)
        state['elasticsearch']['tasks'].insert(0, {'id': f"es-task-rollover-{len(state['elasticsearch']['tasks']) + 1}", 'cluster': target['name'], 'name': 'ilm-rollover', 'progress': 100, 'status': 'completed'})
        _append_event(state['elasticsearch']['events'], 'info', f"{target['name']} rolled over", f"Created index {new_index['name']}.")
    else:
        return None, 'Unsupported Elasticsearch action.'
    _sync_es(state)
    return state, f"Elasticsearch action {action_name} completed."


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('ops.middleware.view')])
def middleware_overview(request):
    return Response(_build_payload(_get_demo_state()))


@api_view(['POST'])
@permission_classes([IsAuthenticated, build_rbac_permission('ops.middleware.manage')])
def middleware_action(request):
    module_name = request.data.get('module')
    action_name = request.data.get('action')
    target_id = request.data.get('target_id')
    payload = request.data.get('payload') or {}
    is_targetless_action = str(action_name or '').startswith('create_') or action_name == 'import_template'
    if not module_name or not action_name or (not is_targetless_action and not target_id):
        return Response({'detail': 'module and action are required, and target_id is required for update, delete and runtime actions.'}, status=400)
    state = _get_demo_state()
    if module_name == 'redis':
        state, message = _redis_action(state, target_id, action_name, payload)
    elif module_name == 'rocketmq':
        state, message = _rocketmq_action(state, target_id, action_name, payload)
    elif module_name == 'elasticsearch':
        state, message = _elasticsearch_action(state, target_id, action_name, payload)
    else:
        return Response({'detail': 'Unsupported middleware module.'}, status=400)
    if state is None:
        return Response({'detail': message}, status=400)
    _set_demo_state(state)
    return Response({'success': True, 'message': message, 'data': _build_payload(state)})
