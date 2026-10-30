"""Compact cluster capacity snapshots; never retain full Node or Pod objects."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.utils import timezone
from kubernetes.utils.quantity import parse_quantity


def _quantity(resources, name):
    return Decimal(parse_quantity(str((resources or {}).get(name, '0'))))


def _container_resources(container, field, name):
    resources = getattr(container, 'resources', None)
    values = getattr(resources, field, None) or {}
    if field == 'requests' and name not in values:
        values = getattr(resources, 'limits', None) or {}
    return _quantity(values, name)


def _pod_resources(pod, field, name):
    """Match scheduler accounting, including init sidecars and Pod overhead."""
    spec = pod.spec
    regular = sum((_container_resources(item, field, name) for item in (spec.containers or [])), Decimal(0))
    sidecars = Decimal(0)
    init_peak = Decimal(0)
    for container in (getattr(spec, 'init_containers', None) or []):
        value = _container_resources(container, field, name)
        if getattr(container, 'restart_policy', None) == 'Always':
            sidecars += value
            init_peak = max(init_peak, sidecars)
        else:
            init_peak = max(init_peak, sidecars + value)
    result = max(regular + sidecars, init_peak)
    pod_resources = getattr(spec, 'resources', None)
    pod_values = getattr(pod_resources, field, None) or {}
    if name in pod_values:
        result = _quantity(pod_values, name)
    if field == 'requests' or result:
        result += _quantity(getattr(spec, 'overhead', None), name)
    return result


def _read_items(loader):
    try:
        return loader(), True
    except Exception:
        return [], False


def build_cluster_capacity(k8s):
    core = k8s.CoreV1Api()
    custom = k8s.CustomObjectsApi()
    loaders = {
        'nodes': lambda: core.list_node().items,
        'pods': lambda: core.list_pod_for_all_namespaces().items,
        'metrics': lambda: custom.list_cluster_custom_object('metrics.k8s.io', 'v1beta1', 'nodes').get('items', []),
    }
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix='k8s-capacity') as executor:
        futures = {name: executor.submit(_read_items, loader) for name, loader in loaders.items()}
        results = {name: future.result() for name, future in futures.items()}
    nodes, nodes_available = results['nodes']
    pods, pods_available = results['pods']
    metrics, metrics_available = results['metrics']
    scheduled = [pod for pod in pods if getattr(pod.spec, 'node_name', None)
                 and pod.status.phase not in {'Succeeded', 'Failed'}]
    node_names = {node.metadata.name for node in nodes}
    samples = {item.get('metadata', {}).get('name'): item for item in metrics}
    covered = node_names & samples.keys()
    usage_complete = nodes_available and metrics_available and bool(node_names) and covered == node_names
    resources = {}
    for name in ('cpu', 'memory'):
        resource = {'usage': None, 'requests': None, 'limits': None, 'allocatable': None, 'capacity': None}
        if nodes_available:
            resource['capacity'] = sum((_quantity(node.status.capacity, name) for node in nodes), Decimal(0))
            resource['allocatable'] = sum((_quantity(node.status.allocatable, name) for node in nodes), Decimal(0))
        if pods_available:
            for field in ('requests', 'limits'):
                resource[field] = sum((_pod_resources(pod, field, name) for pod in scheduled), Decimal(0))
        if usage_complete:
            try:
                if any(name not in samples[node].get('usage', {}) for node in node_names):
                    raise ValueError('Incomplete metrics')
                resource['usage'] = sum((_quantity(samples[node]['usage'], name) for node in node_names), Decimal(0))
            except (ValueError, TypeError, ArithmeticError):
                resource['usage'] = None
        resources[name] = {
            key: (round(float(value), 9) if name == 'cpu' else int(value)) if value is not None else None
            for key, value in resource.items()
        }
    return {
        'resources': {
            **resources,
            'pods': {
                'usage': len(scheduled) if pods_available else None,
                'allocatable': int(sum((_quantity(node.status.allocatable, 'pods') for node in nodes), Decimal(0))) if nodes_available else None,
                'capacity': int(sum((_quantity(node.status.capacity, 'pods') for node in nodes), Decimal(0))) if nodes_available else None,
            },
        },
        'metrics': {
            'available': all(resources[name]['usage'] is not None for name in ('cpu', 'memory')),
            'nodes_covered': len(covered),
            'nodes_total': len(node_names),
            'sample_time': min((samples[name].get('timestamp', '') for name in covered), default=''),
        },
        'unavailable_resources': [name for name, (_, available) in results.items() if not available],
        'collected_at': timezone.now().isoformat(),
    }


def demo_cluster_capacity(pod_count):
    return {
        'resources': {
            'cpu': {'usage': 6.48, 'requests': 14.8, 'limits': 38.5, 'allocatable': 30.4, 'capacity': 32},
            'memory': {'usage': int(17.3 * 2 ** 30), 'requests': int(29.1 * 2 ** 30),
                       'limits': int(99.7 * 2 ** 30), 'allocatable': 60 * 2 ** 30, 'capacity': 64 * 2 ** 30},
            'pods': {'usage': pod_count, 'allocatable': 440, 'capacity': 440},
        },
        'metrics': {'available': True, 'nodes_covered': 4, 'nodes_total': 4, 'sample_time': timezone.now().isoformat()},
        'unavailable_resources': [],
        'collected_at': timezone.now().isoformat(),
        'demo': True,
    }
