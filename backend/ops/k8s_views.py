"""
Kubernetes 集群管理 API
使用 kubernetes Python 客户端连接并管理 K8s 集群
支持 demo 模式：kubeconfig 为 'demo' 时返回模拟数据
"""
import logging
import tempfile
import os
import copy
import base64
import difflib
import ssl
import shlex
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
import yaml
from django.core.cache import cache
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from .k8s_access import K8sAccessMixin
from .k8s_capacity import build_cluster_capacity, demo_cluster_capacity
from .k8s_logs import pod_log_page, LogSnapshotError
from .k8s_resources import K8sResourceMixin, RESOURCE_TYPES, patch_demo_manifest

from .models import K8sCluster, K8sConfigRevision
from .serializers import K8sClusterSerializer
from rbac.permissions import RBACPermissionMixin
from eventwall.services import record_event

logger = logging.getLogger(__name__)
K8S_SUMMARY_CACHE_TTL = 15
K8S_SERVER_VERSION_CACHE_TTL = 300
K8S_SERVER_VERSION_FAILURE_CACHE_TTL = 30
K8S_RESOURCE_CACHE_TTL = 8
K8S_DEMO_STATE_CACHE_TTL = 86400
K8S_STALE_SUMMARY_CACHE_TTL = 300
K8S_STALE_RESOURCE_CACHE_TTL = 300
K8S_API_CONNECT_TIMEOUT = 1.5
K8S_API_READ_TIMEOUT = 3
K8S_KUBECTL_TIMEOUT = 30
K8S_KUBECTL_MAX_OUTPUT = 200000
K8S_KUBECTL_BLOCKED_OPTIONS = {
    '--kubeconfig', '--context', '--cluster', '--user', '--server', '-s', '--token', '--as', '--as-group', '--as-uid',
    '--certificate-authority', '--client-certificate', '--client-key',
    '--insecure-skip-tls-verify', '--cache-dir', '--kuberc', '-f', '--filename',
    '-k', '--kustomize',
}


class _K8sApiProxy:
    def __init__(self, api):
        self._api = api

    def __getattr__(self, name):
        attr = getattr(self._api, name)
        if not callable(attr):
            return attr

        def wrapped(*args, **kwargs):
            kwargs.setdefault('_request_timeout', (K8S_API_CONNECT_TIMEOUT, K8S_API_READ_TIMEOUT))
            return attr(*args, **kwargs)

        method_owner = getattr(attr, '__self__', None)
        if method_owner is not None:
            wrapped.__self__ = method_owner
            wrapped.self = method_owner

        return wrapped


class _K8sClientProxy:
    def __init__(self, client_module, api_client):
        self._client_module = client_module
        self._api_client = api_client

    def __getattr__(self, name):
        if name == 'ApiClient':
            return lambda *args, **kwargs: self._api_client

        attr = getattr(self._client_module, name)
        if name.endswith('Api') and isinstance(attr, type):
            return lambda *args, _attr=attr, **kwargs: _K8sApiProxy(_attr(self._api_client, *args, **kwargs))
        return attr


def _is_demo(cluster):
    return cluster.kubeconfig.strip() == 'demo'


def _prepare_kubeconfig(cluster):
    kubeconfig_text = cluster.kubeconfig or ''
    api_server = (cluster.api_server or '').strip()
    if not api_server:
        return kubeconfig_text

    try:
        kubeconfig = yaml.safe_load(kubeconfig_text) or {}
    except Exception:
        return kubeconfig_text

    if not isinstance(kubeconfig, dict):
        return kubeconfig_text

    current_context_name = kubeconfig.get('current-context')
    contexts = kubeconfig.get('contexts') or []
    clusters = kubeconfig.get('clusters') or []
    context_cluster_name = ''

    for context in contexts:
        if not isinstance(context, dict):
            continue
        if context.get('name') != current_context_name:
            continue
        context_data = context.get('context') or {}
        context_cluster_name = context_data.get('cluster') or ''
        break

    if not context_cluster_name and clusters:
        first_cluster = clusters[0] if isinstance(clusters[0], dict) else {}
        context_cluster_name = first_cluster.get('name') or ''

    if not context_cluster_name:
        return kubeconfig_text

    for cluster_item in clusters:
        if not isinstance(cluster_item, dict):
            continue
        if cluster_item.get('name') != context_cluster_name:
            continue
        cluster_data = cluster_item.setdefault('cluster', {})
        if isinstance(cluster_data, dict):
            cluster_data['server'] = api_server
            return yaml.safe_dump(kubeconfig, sort_keys=False, allow_unicode=True)

    return kubeconfig_text


def _kubectl_audit_summary(args):
    """Return a useful audit label without persisting command arguments."""
    meaningful = [arg for arg in args if not arg.startswith('-')]
    return ' '.join(meaningful[:3]) or 'kubectl'


def _parse_kubectl_command(command):
    try:
        args = shlex.split(str(command or '').strip())
    except ValueError as exc:
        raise ValueError(f'命令格式错误: {exc}') from exc
    if not args or args[0] != 'kubectl':
        raise ValueError('仅支持以 kubectl 开头的命令')
    if len(args) == 1:
        raise ValueError('请输入 kubectl 子命令')
    if any(any(char in arg for char in ';|&$`\n\r') for arg in args):
        raise ValueError('命令中不允许使用 shell 控制符')
    for arg in args[1:]:
        option = arg.split('=', 1)[0]
        if option in K8S_KUBECTL_BLOCKED_OPTIONS:
            raise ValueError(f'不允许使用 {option}，控制台会自动绑定当前集群')
    return args[1:]


def _run_kubectl_command(cluster, command):
    args = _parse_kubectl_command(command)
    if _is_demo(cluster):
        resource = next((arg for arg in args if not arg.startswith('-')), '')
        if args[:2] == ['get', 'pods']:
            return 0, 'NAME                              READY   STATUS    RESTARTS   AGE\napi-server-5f8b7c6d4-r9p2w        1/1     Running   1          3d\nnginx-deployment-7c5b4f9d8-x2k9p  1/1     Running   0          4d\n', ''
        if args[:2] == ['get', 'nodes']:
            return 0, 'NAME        STATUS   ROLES           AGE   VERSION\nmaster-01   Ready    control-plane   53d   v1.29.3\nnode-01     Ready    worker          53d   v1.29.3\n', ''
        return 0, f'[演示模式] 已在集群 {cluster.name} 执行 kubectl {" ".join(args)}\n资源: {resource or "cluster"}\n', ''

    kubectl_path = shutil.which('kubectl')
    if not kubectl_path:
        raise RuntimeError('服务端未安装 kubectl，无法打开集群控制台')

    kubeconfig_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8')
    try:
        kubeconfig_file.write(_prepare_kubeconfig(cluster))
        kubeconfig_file.close()
        result = subprocess.run(
            [kubectl_path, '--kubeconfig', kubeconfig_file.name, *args],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=K8S_KUBECTL_TIMEOUT,
            check=False,
        )
        return result.returncode, result.stdout[-K8S_KUBECTL_MAX_OUTPUT:], result.stderr[-K8S_KUBECTL_MAX_OUTPUT:]
    finally:
        try:
            os.unlink(kubeconfig_file.name)
        except OSError:
            pass


# ====== Demo 模拟数据 ======
DEMO_NAMESPACES = [
    {'name': 'default', 'status': 'Active', 'created': '2026-01-15T08:00:00+08:00', 'labels': {}},
    {'name': 'kube-system', 'status': 'Active', 'created': '2026-01-15T08:00:00+08:00', 'labels': {}},
    {'name': 'monitoring', 'status': 'Active', 'created': '2026-02-01T10:30:00+08:00', 'labels': {}},
    {'name': 'production', 'status': 'Active', 'created': '2026-02-10T14:00:00+08:00', 'labels': {'env': 'prod'}},
    {'name': 'staging', 'status': 'Active', 'created': '2026-02-10T14:00:00+08:00', 'labels': {'env': 'staging'}},
]

DEMO_PODS = [
    {'name': 'nginx-deployment-7c5b4f9d8-x2k9p', 'namespace': 'production', 'status': 'Running', 'node': 'node-01', 'ip': '10.244.1.15', 'containers': [{'name': 'nginx', 'image': 'nginx:1.25', 'ready': True}], 'restarts': 0, 'created': '2026-03-05T09:00:00+08:00'},
    {'name': 'nginx-deployment-7c5b4f9d8-m3h7q', 'namespace': 'production', 'status': 'Running', 'node': 'node-02', 'ip': '10.244.2.22', 'containers': [{'name': 'nginx', 'image': 'nginx:1.25', 'ready': True}], 'restarts': 0, 'created': '2026-03-05T09:00:00+08:00'},
    {'name': 'api-server-5f8b7c6d4-r9p2w', 'namespace': 'production', 'status': 'Running', 'node': 'node-01', 'ip': '10.244.1.18', 'containers': [{'name': 'api', 'image': 'myapp/api:v2.1.0', 'ready': True}], 'restarts': 1, 'created': '2026-03-04T11:30:00+08:00'},
    {'name': 'api-server-5f8b7c6d4-t4n8k', 'namespace': 'production', 'status': 'Running', 'node': 'node-03', 'ip': '10.244.3.10', 'containers': [{'name': 'api', 'image': 'myapp/api:v2.1.0', 'ready': True}], 'restarts': 0, 'created': '2026-03-04T11:30:00+08:00'},
    {'name': 'redis-master-0', 'namespace': 'production', 'status': 'Running', 'node': 'node-02', 'ip': '10.244.2.30', 'containers': [{'name': 'redis', 'image': 'redis:7.2-alpine', 'ready': True}], 'restarts': 0, 'created': '2026-02-20T08:00:00+08:00'},
    {'name': 'mysql-primary-0', 'namespace': 'production', 'status': 'Running', 'node': 'node-01', 'ip': '10.244.1.25', 'containers': [{'name': 'mysql', 'image': 'mysql:8.0', 'ready': True}], 'restarts': 0, 'created': '2026-02-18T09:00:00+08:00'},
    {'name': 'web-frontend-6d9f8b7c5-j2m4n', 'namespace': 'staging', 'status': 'Running', 'node': 'node-03', 'ip': '10.244.3.15', 'containers': [{'name': 'frontend', 'image': 'myapp/web:v2.2.0-rc1', 'ready': True}], 'restarts': 0, 'created': '2026-03-08T16:00:00+08:00'},
    {'name': 'web-frontend-6d9f8b7c5-k7p3q', 'namespace': 'staging', 'status': 'Pending', 'node': '', 'ip': '', 'containers': [{'name': 'frontend', 'image': 'myapp/web:v2.2.0-rc1', 'ready': False}], 'restarts': 0, 'created': '2026-03-08T16:05:00+08:00'},
    {'name': 'prometheus-server-0', 'namespace': 'monitoring', 'status': 'Running', 'node': 'node-02', 'ip': '10.244.2.40', 'containers': [{'name': 'prometheus', 'image': 'prom/prometheus:v2.51.0', 'ready': True}], 'restarts': 0, 'created': '2026-02-01T10:30:00+08:00'},
    {'name': 'grafana-7f8c9d6b5-w3x2y', 'namespace': 'monitoring', 'status': 'Running', 'node': 'node-03', 'ip': '10.244.3.35', 'containers': [{'name': 'grafana', 'image': 'grafana/grafana:10.4.0', 'ready': True}], 'restarts': 2, 'created': '2026-02-01T10:35:00+08:00'},
    {'name': 'alertmanager-0', 'namespace': 'monitoring', 'status': 'Running', 'node': 'node-01', 'ip': '10.244.1.42', 'containers': [{'name': 'alertmanager', 'image': 'prom/alertmanager:v0.27.0', 'ready': True}], 'restarts': 0, 'created': '2026-02-01T10:40:00+08:00'},
    {'name': 'coredns-5d78c9689-b8k4m', 'namespace': 'kube-system', 'status': 'Running', 'node': 'node-01', 'ip': '10.244.1.3', 'containers': [{'name': 'coredns', 'image': 'registry.k8s.io/coredns:v1.11.1', 'ready': True}], 'restarts': 0, 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'etcd-master', 'namespace': 'kube-system', 'status': 'Running', 'node': 'master', 'ip': '10.0.0.1', 'containers': [{'name': 'etcd', 'image': 'registry.k8s.io/etcd:3.5.12', 'ready': True}], 'restarts': 0, 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'kube-proxy-n7x2k', 'namespace': 'kube-system', 'status': 'Running', 'node': 'node-01', 'ip': '192.168.1.21', 'containers': [{'name': 'kube-proxy', 'image': 'registry.k8s.io/kube-proxy:v1.29.3', 'ready': True}], 'restarts': 0, 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'debug-pod-manual', 'namespace': 'default', 'status': 'Failed', 'node': 'node-02', 'ip': '10.244.2.99', 'containers': [{'name': 'debug', 'image': 'busybox:latest', 'ready': False}], 'restarts': 5, 'created': '2026-03-07T20:00:00+08:00'},
]

DEMO_SERVICES = [
    {'name': 'nginx-service', 'namespace': 'production', 'type': 'LoadBalancer', 'cluster_ip': '10.96.10.50', 'external_ip': '47.95.15.100', 'ports': '80→30080/TCP, 443→30443/TCP', 'created': '2026-03-05T09:00:00+08:00'},
    {'name': 'api-service', 'namespace': 'production', 'type': 'ClusterIP', 'cluster_ip': '10.96.20.100', 'external_ip': '', 'ports': '8080/TCP', 'created': '2026-03-04T11:30:00+08:00'},
    {'name': 'redis-master', 'namespace': 'production', 'type': 'ClusterIP', 'cluster_ip': '10.96.30.10', 'external_ip': '', 'ports': '6379/TCP', 'created': '2026-02-20T08:00:00+08:00'},
    {'name': 'mysql-primary', 'namespace': 'production', 'type': 'ClusterIP', 'cluster_ip': '10.96.30.20', 'external_ip': '', 'ports': '3306/TCP', 'created': '2026-02-18T09:00:00+08:00'},
    {'name': 'web-frontend', 'namespace': 'staging', 'type': 'NodePort', 'cluster_ip': '10.96.50.10', 'external_ip': '', 'ports': '3000→31000/TCP', 'created': '2026-03-08T16:00:00+08:00'},
    {'name': 'prometheus', 'namespace': 'monitoring', 'type': 'NodePort', 'cluster_ip': '10.96.60.10', 'external_ip': '', 'ports': '9090→30090/TCP', 'created': '2026-02-01T10:30:00+08:00'},
    {'name': 'grafana', 'namespace': 'monitoring', 'type': 'NodePort', 'cluster_ip': '10.96.60.20', 'external_ip': '', 'ports': '3000→30300/TCP', 'created': '2026-02-01T10:35:00+08:00'},
    {'name': 'kubernetes', 'namespace': 'default', 'type': 'ClusterIP', 'cluster_ip': '10.96.0.1', 'external_ip': '', 'ports': '443/TCP', 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'kube-dns', 'namespace': 'kube-system', 'type': 'ClusterIP', 'cluster_ip': '10.96.0.10', 'external_ip': '', 'ports': '53/UDP, 53/TCP, 9153/TCP', 'created': '2026-01-15T08:00:00+08:00'},
]

DEMO_DEPLOYMENTS = [
    {'name': 'nginx-deployment', 'namespace': 'production', 'replicas': 2, 'ready_replicas': 2, 'available_replicas': 2, 'images': 'nginx:1.25', 'created': '2026-03-05T09:00:00+08:00'},
    {'name': 'api-server', 'namespace': 'production', 'replicas': 2, 'ready_replicas': 2, 'available_replicas': 2, 'images': 'myapp/api:v2.1.0', 'created': '2026-03-04T11:30:00+08:00'},
    {'name': 'web-frontend', 'namespace': 'staging', 'replicas': 2, 'ready_replicas': 1, 'available_replicas': 1, 'images': 'myapp/web:v2.2.0-rc1', 'created': '2026-03-08T16:00:00+08:00'},
    {'name': 'grafana', 'namespace': 'monitoring', 'replicas': 1, 'ready_replicas': 1, 'available_replicas': 1, 'images': 'grafana/grafana:10.4.0', 'created': '2026-02-01T10:35:00+08:00'},
    {'name': 'coredns', 'namespace': 'kube-system', 'replicas': 1, 'ready_replicas': 1, 'available_replicas': 1, 'images': 'registry.k8s.io/coredns:v1.11.1', 'created': '2026-01-15T08:00:00+08:00'},
]

DEMO_NODES = [
    {'name': 'master-01', 'status': 'Ready', 'roles': 'control-plane', 'version': 'v1.29.3', 'internal_ip': '192.168.1.10', 'os_image': 'Ubuntu 22.04.3 LTS', 'cpu': '8000m', 'memory': '16Gi', 'pods_count': 12, 'age': '53d', 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'node-01', 'status': 'Ready', 'roles': 'worker', 'version': 'v1.29.3', 'internal_ip': '192.168.1.21', 'os_image': 'Ubuntu 22.04.3 LTS', 'cpu': '8000m', 'memory': '14.8Gi', 'pods_count': 8, 'age': '53d', 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'node-02', 'status': 'Ready', 'roles': 'worker', 'version': 'v1.29.3', 'internal_ip': '192.168.1.22', 'os_image': 'Ubuntu 22.04.3 LTS', 'cpu': '8000m', 'memory': '14.8Gi', 'pods_count': 6, 'age': '53d', 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'node-03', 'status': 'Ready', 'roles': 'worker', 'version': 'v1.29.3', 'internal_ip': '192.168.1.23', 'os_image': 'Ubuntu 22.04.3 LTS', 'cpu': '8000m', 'memory': '14.8Gi', 'pods_count': 5, 'age': '30d', 'created': '2026-02-07T10:00:00+08:00'},
]

DEMO_STATEFULSETS = [
    {'name': 'redis-master', 'namespace': 'production', 'replicas': 1, 'ready_replicas': 1, 'current_replicas': 1, 'images': 'redis:7.2-alpine', 'created': '2026-02-20T08:00:00+08:00'},
    {'name': 'mysql-primary', 'namespace': 'production', 'replicas': 1, 'ready_replicas': 1, 'current_replicas': 1, 'images': 'mysql:8.0', 'created': '2026-02-18T09:00:00+08:00'},
    {'name': 'prometheus-server', 'namespace': 'monitoring', 'replicas': 1, 'ready_replicas': 1, 'current_replicas': 1, 'images': 'prom/prometheus:v2.51.0', 'created': '2026-02-01T10:30:00+08:00'},
]

DEMO_DAEMONSETS = [
    {'name': 'kube-proxy', 'namespace': 'kube-system', 'desired': 4, 'current': 4, 'ready': 4, 'images': 'registry.k8s.io/kube-proxy:v1.29.3', 'node_selector': '', 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'calico-node', 'namespace': 'kube-system', 'desired': 4, 'current': 4, 'ready': 4, 'images': 'calico/node:v3.27.0', 'node_selector': '', 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'node-exporter', 'namespace': 'monitoring', 'desired': 3, 'current': 3, 'ready': 3, 'images': 'prom/node-exporter:v1.7.0', 'node_selector': 'worker', 'created': '2026-02-01T10:30:00+08:00'},
]

DEMO_JOBS = [
    {'name': 'db-backup-20260309', 'namespace': 'production', 'completions': '1/1', 'duration': '45s', 'status': 'Complete', 'images': 'mysql:8.0', 'created': '2026-03-09T02:00:00+08:00'},
    {'name': 'data-migration-v2', 'namespace': 'production', 'completions': '3/3', 'duration': '12m', 'status': 'Complete', 'images': 'myapp/migrator:v2.1', 'created': '2026-03-08T10:00:00+08:00'},
]

DEMO_CRONJOBS = [
    {'name': 'db-backup', 'namespace': 'production', 'schedule': '0 2 * * *', 'suspend': False, 'active': 0, 'last_schedule': '2026-03-09T02:00:00+08:00', 'images': 'mysql:8.0', 'created': '2026-02-20T08:00:00+08:00'},
    {'name': 'log-cleanup', 'namespace': 'kube-system', 'schedule': '0 3 * * 0', 'suspend': False, 'active': 0, 'last_schedule': '2026-03-09T03:00:00+08:00', 'images': 'busybox:latest', 'created': '2026-01-20T08:00:00+08:00'},
    {'name': 'cert-renew', 'namespace': 'default', 'schedule': '0 0 1 * *', 'suspend': True, 'active': 0, 'last_schedule': '2026-03-01T00:00:00+08:00', 'images': 'certbot:latest', 'created': '2026-02-01T08:00:00+08:00'},
]

DEMO_INGRESSES = [
    {'name': 'web-ingress', 'namespace': 'production', 'class': 'nginx', 'hosts': 'app.example.com', 'address': '47.95.15.100', 'ports': '80, 443', 'created': '2026-03-05T09:00:00+08:00'},
    {'name': 'api-ingress', 'namespace': 'production', 'class': 'nginx', 'hosts': 'api.example.com', 'address': '47.95.15.100', 'ports': '80, 443', 'created': '2026-03-04T11:30:00+08:00'},
    {'name': 'grafana-ingress', 'namespace': 'monitoring', 'class': 'nginx', 'hosts': 'grafana.example.com', 'address': '47.95.15.100', 'ports': '80, 443', 'created': '2026-02-01T10:35:00+08:00'},
]

DEMO_PVS = [
    {'name': 'pv-mysql-data', 'capacity': '50Gi', 'access_modes': 'RWO', 'reclaim_policy': 'Retain', 'status': 'Bound', 'claim': 'production/mysql-data-mysql-primary-0', 'storage_class': 'local-path', 'created': '2026-02-18T09:00:00+08:00'},
    {'name': 'pv-redis-data', 'capacity': '10Gi', 'access_modes': 'RWO', 'reclaim_policy': 'Retain', 'status': 'Bound', 'claim': 'production/redis-data-redis-master-0', 'storage_class': 'local-path', 'created': '2026-02-20T08:00:00+08:00'},
    {'name': 'pv-prometheus', 'capacity': '100Gi', 'access_modes': 'RWO', 'reclaim_policy': 'Delete', 'status': 'Bound', 'claim': 'monitoring/prometheus-data', 'storage_class': 'nfs', 'created': '2026-02-01T10:30:00+08:00'},
    {'name': 'pv-available-01', 'capacity': '20Gi', 'access_modes': 'RWX', 'reclaim_policy': 'Retain', 'status': 'Available', 'claim': '', 'storage_class': 'nfs', 'created': '2026-03-01T08:00:00+08:00'},
]

DEMO_PVCS = [
    {'name': 'mysql-data-mysql-primary-0', 'namespace': 'production', 'status': 'Bound', 'volume': 'pv-mysql-data', 'capacity': '50Gi', 'access_modes': 'RWO', 'storage_class': 'local-path', 'created': '2026-02-18T09:00:00+08:00'},
    {'name': 'redis-data-redis-master-0', 'namespace': 'production', 'status': 'Bound', 'volume': 'pv-redis-data', 'capacity': '10Gi', 'access_modes': 'RWO', 'storage_class': 'local-path', 'created': '2026-02-20T08:00:00+08:00'},
    {'name': 'prometheus-data', 'namespace': 'monitoring', 'status': 'Bound', 'volume': 'pv-prometheus', 'capacity': '100Gi', 'access_modes': 'RWO', 'storage_class': 'nfs', 'created': '2026-02-01T10:30:00+08:00'},
]

DEMO_STORAGECLASSES = [
    {'name': 'local-path', 'provisioner': 'rancher.io/local-path', 'reclaim_policy': 'Delete', 'binding_mode': 'WaitForFirstConsumer', 'allow_expansion': True, 'is_default': True, 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'nfs', 'provisioner': 'nfs.csi.k8s.io', 'reclaim_policy': 'Delete', 'binding_mode': 'Immediate', 'allow_expansion': True, 'is_default': False, 'created': '2026-01-20T08:00:00+08:00'},
]

DEMO_CONFIGMAPS = [
    {'name': 'nginx-config', 'namespace': 'production', 'data_count': 3, 'created': '2026-03-05T09:00:00+08:00'},
    {'name': 'api-config', 'namespace': 'production', 'data_count': 5, 'created': '2026-03-04T11:30:00+08:00'},
    {'name': 'prometheus-config', 'namespace': 'monitoring', 'data_count': 2, 'created': '2026-02-01T10:30:00+08:00'},
    {'name': 'grafana-dashboards', 'namespace': 'monitoring', 'data_count': 8, 'created': '2026-02-01T10:35:00+08:00'},
    {'name': 'coredns', 'namespace': 'kube-system', 'data_count': 1, 'created': '2026-01-15T08:00:00+08:00'},
    {'name': 'kube-proxy', 'namespace': 'kube-system', 'data_count': 2, 'created': '2026-01-15T08:00:00+08:00'},
]

DEMO_SECRETS = [
    {'name': 'mysql-credentials', 'namespace': 'production', 'type': 'Opaque', 'data_count': 2, 'created': '2026-02-18T09:00:00+08:00'},
    {'name': 'tls-cert-production', 'namespace': 'production', 'type': 'kubernetes.io/tls', 'data_count': 2, 'created': '2026-03-01T08:00:00+08:00'},
    {'name': 'registry-credentials', 'namespace': 'production', 'type': 'kubernetes.io/dockerconfigjson', 'data_count': 1, 'created': '2026-02-15T08:00:00+08:00'},
    {'name': 'grafana-admin', 'namespace': 'monitoring', 'type': 'Opaque', 'data_count': 2, 'created': '2026-02-01T10:35:00+08:00'},
    {'name': 'default-token', 'namespace': 'default', 'type': 'kubernetes.io/service-account-token', 'data_count': 3, 'created': '2026-01-15T08:00:00+08:00'},
]


def _get_k8s_client(cluster):
    """根据 kubeconfig 创建 K8s API 客户端"""
    from kubernetes import client, config

    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    tmp.write(_prepare_kubeconfig(cluster))
    tmp.flush()
    tmp.close()

    try:
        api_client = config.new_client_from_config(config_file=tmp.name)
        return _K8sClientProxy(client, api_client)
    finally:
        os.unlink(tmp.name)


def _filter_by_ns(data, namespace):
    if namespace == '_all':
        return data
    return [d for d in data if d['namespace'] == namespace]


def _summary_cache_key(cluster_id):
    return f'ops:k8s:summary:{cluster_id}'


def _summary_stale_cache_key(cluster_id):
    return f'ops:k8s:summary-stale:{cluster_id}'


def _server_version_cache_key(cluster_id):
    return f'ops:k8s:server-version:{cluster_id}'


def _get_cluster_server_version(cluster, k8s=None):
    """Read the API server version independently of resource-list permissions."""
    if _is_demo(cluster):
        return 'v1.29.3'
    cache_key = _server_version_cache_key(cluster.pk)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    owns_client = k8s is None
    version = ''
    try:
        if owns_client:
            k8s = _get_k8s_client(cluster)
        version = k8s.VersionApi().get_code().git_version or ''
    except Exception:
        logger.debug('Could not read Kubernetes server version for cluster %s', cluster.pk, exc_info=True)
    finally:
        if owns_client and k8s is not None:
            k8s.ApiClient().close()
    cache.set(cache_key, version, K8S_SERVER_VERSION_CACHE_TTL if version else K8S_SERVER_VERSION_FAILURE_CACHE_TTL)
    return version


def _clear_summary_cache(cluster_or_id):
    cluster_id = cluster_or_id.pk if hasattr(cluster_or_id, 'pk') else cluster_or_id
    if cluster_id:
        cache.delete(_summary_cache_key(cluster_id))


def _resource_cache_version_key(cluster_id):
    return f'ops:k8s:list-version:{cluster_id}'


def _get_resource_cache_version(cluster_id):
    cache_key = _resource_cache_version_key(cluster_id)
    version = cache.get(cache_key)
    if version is None:
        version = 1
        cache.set(cache_key, version, K8S_DEMO_STATE_CACHE_TTL)
    return version


def _bump_resource_cache_version(cluster_or_id):
    cluster_id = cluster_or_id.pk if hasattr(cluster_or_id, 'pk') else cluster_or_id
    if not cluster_id:
        return
    cache_key = _resource_cache_version_key(cluster_id)
    current = cache.get(cache_key)
    if current is None:
        cache.set(cache_key, 2, K8S_DEMO_STATE_CACHE_TTL)
        return
    try:
        cache.incr(cache_key)
    except Exception:
        cache.set(cache_key, int(current) + 1, K8S_DEMO_STATE_CACHE_TTL)


def _resource_cache_key(cluster_id, resource, namespace=''):
    version = _get_resource_cache_version(cluster_id)
    scope = namespace or '_cluster'
    return f'ops:k8s:list:{cluster_id}:{version}:{resource}:{scope}'


def _resource_stale_cache_key(cluster_id, resource, namespace=''):
    scope = namespace or '_cluster'
    return f'ops:k8s:list-stale:{cluster_id}:{resource}:{scope}'


def _get_or_set_resource_cache(cluster, resource, namespace, loader, default=None):
    cache_key = _resource_cache_key(cluster.id, resource, namespace)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    stale_key = _resource_stale_cache_key(cluster.id, resource, namespace)
    fallback = [] if default is None else default
    try:
        data = loader()
    except Exception as exc:
        stale = cache.get(stale_key)
        if stale is not None:
            logger.warning(
                'K8s resource fallback to stale cache for cluster=%s resource=%s namespace=%s: %s',
                cluster.id,
                resource,
                namespace or '_cluster',
                exc,
            )
            return stale
        logger.warning(
            'K8s resource fallback to default for cluster=%s resource=%s namespace=%s: %s',
            cluster.id,
            resource,
            namespace or '_cluster',
            exc,
        )
        return fallback

    cache.set(cache_key, data, K8S_RESOURCE_CACHE_TTL)
    cache.set(stale_key, data, K8S_STALE_RESOURCE_CACHE_TTL)
    return data


def _serialize_pod_item(pod):
    containers = [{
        'name': container.name,
        'image': container.image,
        'ready': False,
    } for container in (pod.spec.containers or [])]
    if pod.status.container_statuses:
        for container_status in pod.status.container_statuses:
            for container in containers:
                if container['name'] == container_status.name:
                    container['ready'] = container_status.ready or False
                    container['restart_count'] = container_status.restart_count or 0
    return {
        'name': pod.metadata.name,
        'namespace': pod.metadata.namespace,
        'status': pod.status.phase,
        'node': pod.spec.node_name or '',
        'ip': pod.status.pod_ip or '',
        'containers': containers,
        'restarts': sum(container.get('restart_count', 0) for container in containers),
        'controlled_by': next((
            f'{reference.kind}/{reference.name}'
            for reference in (pod.metadata.owner_references or [])
            if reference.controller
        ), ''),
        'qos': pod.status.qos_class or '',
        'created': pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else '',
    }


def _serialize_demo_pod_item(pod):
    item = copy.deepcopy(pod)
    name = item.get('name', '')
    controlled_by = ''
    if name.startswith('nginx-deployment'):
        controlled_by = 'ReplicaSet/nginx-deployment-7c5b4f9d8'
    elif name.startswith('api-server'):
        controlled_by = 'ReplicaSet/api-server-5f8b7c6d4'
    elif name.startswith('web-frontend'):
        controlled_by = 'ReplicaSet/web-frontend-6d9f8b7c5'
    elif name.startswith(('redis-master', 'mysql-primary', 'prometheus-server', 'alertmanager-main')):
        controlled_by = f'StatefulSet/{name.rsplit("-", 1)[0]}'
    elif name.startswith(('kube-proxy', 'node-exporter')):
        controlled_by = f'DaemonSet/{name.rsplit("-", 1)[0]}'
    item['controlled_by'] = controlled_by
    item['qos'] = 'Burstable' if controlled_by else 'BestEffort'
    return item


def _serialize_service_item(svc):
    return {
        'name': svc.metadata.name,
        'namespace': svc.metadata.namespace,
        'type': svc.spec.type,
        'cluster_ip': svc.spec.cluster_ip or '',
        'external_ip': ','.join(svc.spec.external_ips or []),
        'ports': ', '.join([
            f"{port.port}{'->'+str(port.node_port) if port.node_port else ''}/{port.protocol}"
            for port in (svc.spec.ports or [])
        ]),
        'created': svc.metadata.creation_timestamp.isoformat() if svc.metadata.creation_timestamp else '',
    }


def _serialize_deployment_item(dep):
    return {
        'name': dep.metadata.name,
        'namespace': dep.metadata.namespace,
        'replicas': dep.spec.replicas or 0,
        'ready_replicas': dep.status.ready_replicas or 0,
        'available_replicas': dep.status.available_replicas or 0,
        'images': ', '.join([container.image for container in dep.spec.template.spec.containers]),
        'created': dep.metadata.creation_timestamp.isoformat() if dep.metadata.creation_timestamp else '',
    }


def _serialize_node_item(node):
    conditions = {condition.type: condition.status for condition in (node.status.conditions or [])}
    roles = ','.join([
        label.replace('node-role.kubernetes.io/', '')
        for label in (node.metadata.labels or {})
        if label.startswith('node-role.kubernetes.io/')
    ])
    capacity = node.status.capacity or {}
    return {
        'name': node.metadata.name,
        'status': 'Ready' if conditions.get('Ready') == 'True' else 'NotReady',
        'roles': roles or 'worker',
        'version': node.status.node_info.kubelet_version if node.status.node_info else '',
        'internal_ip': next((address.address for address in (node.status.addresses or []) if address.type == 'InternalIP'), ''),
        'os_image': node.status.node_info.os_image if node.status.node_info else '',
        'cpu': capacity.get('cpu', ''),
        'memory': capacity.get('memory', ''),
        'pods_count': 0,
        'unschedulable': bool(node.spec.unschedulable),
        'age': '',
        'created': node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else '',
    }


def _selected_namespaces(namespaces):
    return [str(item).strip() for item in (namespaces or []) if str(item).strip() and str(item).strip() != '_all']


def _collect_namespaced_resource(cluster, resource, namespaces, demo_items, live_loader, default=None):
    selected = _selected_namespaces(namespaces)
    if _is_demo(cluster):
        data = list(demo_items)
        if not selected:
            return data
        return [item for item in data if item.get('namespace') in selected]
    if selected:
        data = []
        for namespace in selected:
            data.extend(_get_or_set_resource_cache(cluster, resource, namespace, lambda ns=namespace: live_loader(ns), default=default or []))
        return data
    return _get_or_set_resource_cache(cluster, resource, '_all', lambda: live_loader('_all'), default=default or [])


def get_k8s_summary_snapshot(cluster):
    cache_key = _summary_cache_key(cluster.id)
    cached = cache.get(cache_key)
    if cached:
        if _is_unreliable_zero_summary(cached):
            cache.delete(cache_key)
        else:
            return cached
    try:
        summary = _build_demo_summary(cluster) if _is_demo(cluster) else _build_live_summary(cluster)
        if cluster.status != 'connected':
            cluster.status = 'connected'
            cluster.save(update_fields=['status'])
            summary['status'] = cluster.status
        return _cache_summary_snapshot(cluster, summary)
    except Exception as exc:
        if cluster.status != 'error':
            cluster.status = 'error'
            cluster.save(update_fields=['status'])
        _clear_summary_cache(cluster)
        fallback = cache.get(_summary_stale_cache_key(cluster.id))
        if fallback is not None:
            return {
                **fallback,
                'degraded': True,
                'status': cluster.status or 'error',
                'alerts': [{'level': 'warning', 'message': 'K8s API is temporarily unavailable; returning the latest cached snapshot'}],
            }
        return _build_unavailable_summary(cluster, str(exc))


def get_k8s_pods_snapshot(cluster, namespaces=None):
    def loader(namespace):
        k8s = _get_k8s_client(cluster)
        v1 = k8s.CoreV1Api()
        pod_list = v1.list_pod_for_all_namespaces() if namespace == '_all' else v1.list_namespaced_pod(namespace=namespace)
        return [_serialize_pod_item(item) for item in pod_list.items]

    return _collect_namespaced_resource(cluster, 'pods', namespaces, _get_demo_state(cluster.id, 'pods', DEMO_PODS), loader)


def get_k8s_nodes_snapshot(cluster):
    if _is_demo(cluster):
        return _get_demo_state(cluster.id, 'nodes', DEMO_NODES)

    def loader():
        k8s = _get_k8s_client(cluster)
        return [_serialize_node_item(item) for item in k8s.CoreV1Api().list_node().items]

    return _get_or_set_resource_cache(cluster, 'nodes', '_all', loader, default=[])


def get_k8s_resource_snapshot(cluster, resource_type, namespaces=None):
    resource_type = str(resource_type or '').strip().lower()
    if resource_type == 'pods':
        return get_k8s_pods_snapshot(cluster, namespaces)
    if resource_type == 'nodes':
        return get_k8s_nodes_snapshot(cluster)

    if resource_type == 'deployments':
        def loader(namespace):
            k8s = _get_k8s_client(cluster)
            apps_v1 = k8s.AppsV1Api()
            items = apps_v1.list_deployment_for_all_namespaces().items if namespace == '_all' else apps_v1.list_namespaced_deployment(namespace=namespace).items
            return [_serialize_deployment_item(item) for item in items]

        return _collect_namespaced_resource(cluster, 'deployments', namespaces, _get_demo_state(cluster.id, 'deployments', DEMO_DEPLOYMENTS), loader)

    if resource_type == 'services':
        def loader(namespace):
            k8s = _get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            items = v1.list_service_for_all_namespaces().items if namespace == '_all' else v1.list_namespaced_service(namespace=namespace).items
            return [_serialize_service_item(item) for item in items]

        return _collect_namespaced_resource(cluster, 'services', namespaces, _get_demo_state(cluster.id, 'services', DEMO_SERVICES), loader)

    namespaced_resources = {
        'statefulsets': (
            _get_demo_state(cluster.id, 'statefulsets', DEMO_STATEFULSETS),
            lambda apps_v1, namespace: apps_v1.list_stateful_set_for_all_namespaces().items if namespace == '_all' else apps_v1.list_namespaced_stateful_set(namespace=namespace).items,
            lambda item: {
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'replicas': item.spec.replicas or 0,
                'ready_replicas': item.status.ready_replicas or 0,
                'current_replicas': item.status.current_replicas or 0,
                'images': ', '.join([container.image for container in item.spec.template.spec.containers]),
                'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else '',
            },
            'apps',
        ),
        'daemonsets': (
            DEMO_DAEMONSETS,
            lambda apps_v1, namespace: apps_v1.list_daemon_set_for_all_namespaces().items if namespace == '_all' else apps_v1.list_namespaced_daemon_set(namespace=namespace).items,
            lambda item: {
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'desired': item.status.desired_number_scheduled or 0,
                'current': item.status.current_number_scheduled or 0,
                'ready': item.status.number_ready or 0,
                'images': ', '.join([container.image for container in item.spec.template.spec.containers]),
                'node_selector': str(item.spec.template.spec.node_selector or ''),
                'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else '',
            },
            'apps',
        ),
        'jobs': (
            DEMO_JOBS,
            lambda batch_v1, namespace: batch_v1.list_job_for_all_namespaces().items if namespace == '_all' else batch_v1.list_namespaced_job(namespace=namespace).items,
            lambda item: {
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'completions': f'{item.status.succeeded or 0}/{item.spec.completions or 1}',
                'duration': '',
                'status': 'Complete' if (item.status.succeeded or 0) >= (item.spec.completions or 1) else 'Running',
                'images': ', '.join([container.image for container in item.spec.template.spec.containers]),
                'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else '',
            },
            'batch',
        ),
        'cronjobs': (
            DEMO_CRONJOBS,
            lambda batch_v1, namespace: batch_v1.list_cron_job_for_all_namespaces().items if namespace == '_all' else batch_v1.list_namespaced_cron_job(namespace=namespace).items,
            lambda item: {
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'schedule': item.spec.schedule,
                'suspend': item.spec.suspend or False,
                'active': len(item.status.active or []),
                'last_schedule': item.status.last_schedule_time.isoformat() if item.status.last_schedule_time else '',
                'images': ', '.join([container.image for container in item.spec.job_template.spec.template.spec.containers]),
                'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else '',
            },
            'batch',
        ),
        'ingresses': (
            DEMO_INGRESSES,
            lambda net_v1, namespace: net_v1.list_ingress_for_all_namespaces().items if namespace == '_all' else net_v1.list_namespaced_ingress(namespace=namespace).items,
            lambda item: {
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'class': item.spec.ingress_class_name or '',
                'hosts': ', '.join([rule.host for rule in (item.spec.rules or []) if rule.host]),
                'address': ', '.join([target.ip or target.hostname or '' for target in (item.status.load_balancer.ingress or [])]) if item.status.load_balancer and item.status.load_balancer.ingress else '',
                'ports': '80, 443' if item.spec.tls else '80',
                'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else '',
            },
            'networking',
        ),
        'pvcs': (
            DEMO_PVCS,
            lambda v1, namespace: v1.list_persistent_volume_claim_for_all_namespaces().items if namespace == '_all' else v1.list_namespaced_persistent_volume_claim(namespace=namespace).items,
            lambda item: {
                'name': item.metadata.name,
                'namespace': item.metadata.namespace,
                'status': item.status.phase,
                'volume': item.spec.volume_name or '',
                'capacity': (item.status.capacity or {}).get('storage', ''),
                'access_modes': ','.join(item.spec.access_modes or []),
                'storage_class': item.spec.storage_class_name or '',
                'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else '',
            },
            'core',
        ),
        'configmaps': (
            DEMO_CONFIGMAPS,
            lambda v1, namespace: v1.list_config_map_for_all_namespaces().items if namespace == '_all' else v1.list_namespaced_config_map(namespace=namespace).items,
            lambda item: {'name': item.metadata.name, 'namespace': item.metadata.namespace, 'data_count': len(item.data or {}), 'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else ''},
            'core',
        ),
        'secrets': (
            DEMO_SECRETS,
            lambda v1, namespace: v1.list_secret_for_all_namespaces().items if namespace == '_all' else v1.list_namespaced_secret(namespace=namespace).items,
            lambda item: {'name': item.metadata.name, 'namespace': item.metadata.namespace, 'type': item.type or '', 'data_count': len(item.data or {}), 'created': item.metadata.creation_timestamp.isoformat() if item.metadata.creation_timestamp else ''},
            'core',
        ),
    }
    if resource_type not in namespaced_resources:
        raise ValueError(f'Unsupported K8s resource type: {resource_type}')

    demo_items, loader_fn, serializer, api_kind = namespaced_resources[resource_type]

    def loader(namespace):
        k8s = _get_k8s_client(cluster)
        if api_kind == 'apps':
            api = k8s.AppsV1Api()
        elif api_kind == 'batch':
            api = k8s.BatchV1Api()
        elif api_kind == 'networking':
            api = k8s.NetworkingV1Api()
        else:
            api = k8s.CoreV1Api()
        return [serializer(item) for item in loader_fn(api, namespace)]

    return _collect_namespaced_resource(cluster, resource_type, namespaces, demo_items, loader)


def _invalidate_cluster_runtime_cache(cluster_or_id):
    _clear_summary_cache(cluster_or_id)
    _bump_resource_cache_version(cluster_or_id)


def _demo_state_key(cluster_id, resource):
    return f'ops:k8s:demo:{cluster_id}:{resource}'


def _get_demo_state(cluster_id, resource, default):
    cache_key = _demo_state_key(cluster_id, resource)
    cached = cache.get(cache_key)
    if cached is None:
        cached = copy.deepcopy(default)
        cache.set(cache_key, cached, K8S_DEMO_STATE_CACHE_TTL)
    return cached


def _set_demo_state(cluster_id, resource, value):
    cache.set(_demo_state_key(cluster_id, resource), value, K8S_DEMO_STATE_CACHE_TTL)


def _demo_config_backup_key(cluster_id, resource_type, namespace, name):
    return f'ops:k8s:demo:backup:{cluster_id}:{resource_type}:{namespace}:{name}'


def _config_backup_key(cluster_id, resource_type, namespace, name):
    return f'ops:k8s:config:backup:{cluster_id}:{resource_type}:{namespace}:{name}'


def _config_revision_queryset(cluster, resource_type, namespace, name):
    return K8sConfigRevision.objects.filter(
        cluster=cluster,
        resource_type=resource_type,
        namespace=namespace,
        resource_name=name,
    )


def _serialize_revision(revision):
    return {
        'id': revision.id,
        'resource_type': revision.resource_type,
        'namespace': revision.namespace,
        'name': revision.resource_name,
        'secret_type': revision.secret_type,
        'operator': revision.operator,
        'action': revision.action,
        'content': revision.content,
        'created_at': revision.created_at.isoformat() if revision.created_at else '',
    }


def _build_text_diff(current_text, target_text, from_label='current', to_label='target'):
    diff = difflib.unified_diff(
        (current_text or '').splitlines(),
        (target_text or '').splitlines(),
        fromfile=from_label,
        tofile=to_label,
        lineterm='',
    )
    return '\n'.join(diff) or 'No changes.'


def _normalize_config_text(content):
    parsed = yaml.safe_load(content or '{}')
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise ValueError('配置内容必须是对象映射')
    return {str(key): '' if value is None else str(value) for key, value in parsed.items()}


def _dump_config_text(data):
    return yaml.dump(data or {}, default_flow_style=False, allow_unicode=True, sort_keys=True)


def _create_config_revision(cluster, resource_type, namespace, name, detail, username, action):
    return K8sConfigRevision.objects.create(
        cluster=cluster,
        resource_type=resource_type,
        namespace=namespace,
        resource_name=name,
        secret_type=detail.get('secret_type', ''),
        content=detail.get('text', ''),
        operator=username or '',
        action=action,
    )


def _safe_collection(label, loader, default=None, issues=None):
    fallback = [] if default is None else default
    try:
        return loader()
    except Exception as exc:
        if issues is not None:
            issues.append(label)
        logger.warning('K8s summary skipped %s: %s', label, exc)
        return fallback


def _count_ready_nodes(nodes):
    ready = 0
    for node in nodes:
        if isinstance(node, dict):
            if node.get('status') == 'Ready':
                ready += 1
            continue
        conditions = {c.type: c.status for c in (node.status.conditions or [])}
        if conditions.get('Ready') == 'True':
            ready += 1
    return ready


def _pod_status_summary(pods):
    abnormal = 0
    restarting = 0
    restarts = 0
    for pod in pods:
        if isinstance(pod, dict):
            status = pod.get('status', '')
            pod_restarts = int(pod.get('restarts', 0) or 0)
        else:
            status = pod.status.phase
            pod_restarts = sum(cs.restart_count for cs in (pod.status.container_statuses or []))

        if status not in ('Running', 'Succeeded'):
            abnormal += 1
        if pod_restarts > 0:
            restarting += 1
        restarts += pod_restarts
    return abnormal, restarting, restarts


def _build_summary_alerts(ready_nodes, total_nodes, abnormal_pods, restarting_pods, total_restarts, degraded_workloads, pending_pvcs):
    alerts = []
    if total_nodes and ready_nodes < total_nodes:
        alerts.append({'level': 'warning', 'message': f'节点健康不足：{ready_nodes}/{total_nodes} Ready'})
    if abnormal_pods:
        alerts.append({'level': 'danger', 'message': f'存在 {abnormal_pods} 个异常 Pod，需要排查调度或探针'})
    if restarting_pods:
        alerts.append({'level': 'warning', 'message': f'{restarting_pods} 个 Pod 发生重启，总次数 {total_restarts}'})
    if degraded_workloads:
        alerts.append({'level': 'warning', 'message': f'{degraded_workloads} 个工作负载副本未就绪'})
    if pending_pvcs:
        alerts.append({'level': 'warning', 'message': f'{pending_pvcs} 个 PVC 尚未绑定存储'})
    if not alerts:
        alerts.append({'level': 'success', 'message': '集群核心资源状态正常'})
    return alerts


def _build_degraded_summary_alerts(
    ready_nodes,
    total_nodes,
    abnormal_pods,
    restarting_pods,
    total_restarts,
    degraded_workloads,
    pending_pvcs,
    unavailable_resources=None,
):
    alerts = []
    unavailable_resources = unavailable_resources or []
    if unavailable_resources:
        visible = ', '.join(unavailable_resources[:4])
        if len(unavailable_resources) > 4:
            visible = f'{visible} 等 {len(unavailable_resources)} 项'
        alerts.append({'level': 'warning', 'message': f'部分 K8s 资源采集超时，已自动降级：{visible}'})
    alerts.extend(
        _build_summary_alerts(
            ready_nodes,
            total_nodes,
            abnormal_pods,
            restarting_pods,
            total_restarts,
            degraded_workloads,
            pending_pvcs,
        )
    )
    if unavailable_resources:
        alerts = [item for item in alerts if item.get('level') != 'success']
    return alerts or [{'level': 'warning', 'message': '部分 K8s 资源采集超时，已自动降级'}]


def _build_unavailable_summary(cluster, reason=''):
    message = '当前 K8s API 不可用，已返回降级结果'
    if reason:
        message = f'{message}：{reason}'
    return {
        'cluster_name': cluster.name,
        'server_version': cache.get(_server_version_cache_key(cluster.pk)) or '',
        'status': cluster.status or 'error',
        'namespaces_total': 0,
        'nodes_total': 0,
        'nodes_ready': 0,
        'pods_total': 0,
        'pods_abnormal': 0,
        'pods_restarting': 0,
        'total_restarts': 0,
        'services_total': 0,
        'ingresses_total': 0,
        'workloads_total': 0,
        'workloads_degraded': 0,
        'pvcs_total': 0,
        'pvcs_pending': 0,
        'configmaps_total': 0,
        'secrets_total': 0,
        'degraded': True,
        'unavailable_resources': ['cluster'],
        'alerts': [{'level': 'warning', 'message': message}],
    }


def _summary_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _summary_runtime_total(summary):
    return sum(
        _summary_int(summary.get(key))
        for key in (
            'nodes_total',
            'pods_total',
            'services_total',
            'ingresses_total',
            'workloads_total',
            'pvcs_total',
            'configmaps_total',
            'secrets_total',
        )
    )


def _is_unreliable_zero_summary(summary):
    if not isinstance(summary, dict):
        return False
    if not summary.get('degraded'):
        return False
    if _summary_runtime_total(summary) > 0:
        return False
    return bool(summary.get('unavailable_resources'))


def _summary_stale_payload(cluster, fallback):
    return {
        **fallback,
        'degraded': True,
        'status': fallback.get('status') or 'connected',
        'alerts': [{'level': 'warning', 'message': 'K8s API is temporarily unavailable; returning the latest cached snapshot'}],
    }


def _fallback_for_unreliable_zero_summary(cluster, summary):
    fallback = cache.get(_summary_stale_cache_key(cluster.id))
    if fallback is not None:
        return _summary_stale_payload(cluster, fallback)
    return summary


def _cache_summary_snapshot(cluster, summary, *, update_stale=True):
    payload = _fallback_for_unreliable_zero_summary(cluster, summary)
    if _is_unreliable_zero_summary(payload):
        return payload
    cache.set(_summary_cache_key(cluster.id), payload, K8S_SUMMARY_CACHE_TTL)
    if update_stale:
        cache.set(_summary_stale_cache_key(cluster.id), payload, K8S_STALE_SUMMARY_CACHE_TTL)
    return payload


def _build_demo_summary(cluster):
    nodes = _get_demo_state(cluster.id, 'nodes', DEMO_NODES)
    pods = _get_demo_state(cluster.id, 'pods', DEMO_PODS)
    deployments = _get_demo_state(cluster.id, 'deployments', DEMO_DEPLOYMENTS)
    statefulsets = _get_demo_state(cluster.id, 'statefulsets', DEMO_STATEFULSETS)
    daemonsets = _get_demo_state(cluster.id, 'daemonsets', DEMO_DAEMONSETS)
    jobs = _get_demo_state(cluster.id, 'jobs', DEMO_JOBS)
    cronjobs = _get_demo_state(cluster.id, 'cronjobs', DEMO_CRONJOBS)
    pvcs = _get_demo_state(cluster.id, 'pvcs', DEMO_PVCS)
    namespaces = _get_demo_state(cluster.id, 'namespaces', DEMO_NAMESPACES)
    services = _get_demo_state(cluster.id, 'services', DEMO_SERVICES)
    ingresses = _get_demo_state(cluster.id, 'ingresses', DEMO_INGRESSES)
    configmaps = _get_demo_state(cluster.id, 'configmaps', DEMO_CONFIGMAPS)
    secrets = _get_demo_state(cluster.id, 'secrets', DEMO_SECRETS)

    ready_nodes = _count_ready_nodes(nodes)
    abnormal_pods, restarting_pods, total_restarts = _pod_status_summary(pods)
    degraded_workloads = (
        sum(1 for item in deployments if item.get('ready_replicas', 0) < item.get('replicas', 0))
        + sum(1 for item in statefulsets if item.get('ready_replicas', 0) < item.get('replicas', 0))
        + sum(1 for item in daemonsets if item.get('ready', 0) < item.get('desired', 0))
    )
    pending_pvcs = sum(1 for pvc in pvcs if pvc.get('status') != 'Bound')
    return {
        'cluster_name': cluster.name,
        'server_version': _get_cluster_server_version(cluster),
        'status': cluster.status or 'connected',
        'namespaces_total': len(namespaces),
        'nodes_total': len(nodes),
        'nodes_ready': ready_nodes,
        'pods_total': len(pods),
        'pods_abnormal': abnormal_pods,
        'pods_restarting': restarting_pods,
        'total_restarts': total_restarts,
        'services_total': len(services),
        'ingresses_total': len(ingresses),
        'workloads_total': len(deployments) + len(statefulsets) + len(daemonsets) + len(jobs) + len(cronjobs),
        'workloads_degraded': degraded_workloads,
        'pvcs_total': len(pvcs),
        'pvcs_pending': pending_pvcs,
        'configmaps_total': len(configmaps),
        'secrets_total': len(secrets),
        'alerts': _build_summary_alerts(ready_nodes, len(nodes), abnormal_pods, restarting_pods, total_restarts, degraded_workloads, pending_pvcs),
    }


def _build_live_summary(cluster):
    k8s = _get_k8s_client(cluster)
    v1 = k8s.CoreV1Api()
    apps_v1 = k8s.AppsV1Api()
    batch_v1 = k8s.BatchV1Api()
    net_v1 = k8s.NetworkingV1Api()
    unavailable_resources = []

    loaders = {
        'namespaces': lambda: v1.list_namespace().items,
        'nodes': lambda: v1.list_node().items,
        'pods': lambda: v1.list_pod_for_all_namespaces().items,
        'services': lambda: v1.list_service_for_all_namespaces().items,
        'ingresses': lambda: net_v1.list_ingress_for_all_namespaces().items,
        'pvcs': lambda: v1.list_persistent_volume_claim_for_all_namespaces().items,
        'configmaps': lambda: v1.list_config_map_for_all_namespaces().items,
        'secrets': lambda: v1.list_secret_for_all_namespaces().items,
        'deployments': lambda: apps_v1.list_deployment_for_all_namespaces().items,
        'statefulsets': lambda: apps_v1.list_stateful_set_for_all_namespaces().items,
        'daemonsets': lambda: apps_v1.list_daemon_set_for_all_namespaces().items,
        'jobs': lambda: batch_v1.list_job_for_all_namespaces().items,
        'cronjobs': lambda: batch_v1.list_cron_job_for_all_namespaces().items,
    }
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix='k8s-summary') as executor:
        version_future = executor.submit(_get_cluster_server_version, cluster, k8s)
        futures = {
            label: executor.submit(_safe_collection, label, loader, issues=unavailable_resources)
            for label, loader in loaders.items()
        }
        collections = {label: future.result() for label, future in futures.items()}
        server_version = version_future.result()
    unavailable_resources = [label for label in loaders if label in unavailable_resources]
    namespaces = collections['namespaces']
    nodes = collections['nodes']
    pods = collections['pods']
    services = collections['services']
    ingresses = collections['ingresses']
    pvcs = collections['pvcs']
    configmaps = collections['configmaps']
    secrets = collections['secrets']
    deployments = collections['deployments']
    statefulsets = collections['statefulsets']
    daemonsets = collections['daemonsets']
    jobs = collections['jobs']
    cronjobs = collections['cronjobs']

    ready_nodes = _count_ready_nodes(nodes)
    abnormal_pods, restarting_pods, total_restarts = _pod_status_summary(pods)
    degraded_workloads = (
        sum(1 for item in deployments if (item.status.ready_replicas or 0) < (item.spec.replicas or 0))
        + sum(1 for item in statefulsets if (item.status.ready_replicas or 0) < (item.spec.replicas or 0))
        + sum(1 for item in daemonsets if (item.status.number_ready or 0) < (item.status.desired_number_scheduled or 0))
    )
    pending_pvcs = sum(1 for pvc in pvcs if (pvc.status.phase or '') != 'Bound')

    summary = {
        'cluster_name': cluster.name,
        'server_version': server_version,
        'status': cluster.status or 'connected',
        'namespaces_total': len(namespaces),
        'nodes_total': len(nodes),
        'nodes_ready': ready_nodes,
        'pods_total': len(pods),
        'pods_abnormal': abnormal_pods,
        'pods_restarting': restarting_pods,
        'total_restarts': total_restarts,
        'services_total': len(services),
        'ingresses_total': len(ingresses),
        'workloads_total': len(deployments) + len(statefulsets) + len(daemonsets) + len(jobs) + len(cronjobs),
        'workloads_degraded': degraded_workloads,
        'pvcs_total': len(pvcs),
        'pvcs_pending': pending_pvcs,
        'configmaps_total': len(configmaps),
        'secrets_total': len(secrets),
        'alerts': _build_degraded_summary_alerts(
            ready_nodes,
            len(nodes),
            abnormal_pods,
            restarting_pods,
            total_restarts,
            degraded_workloads,
            pending_pvcs,
            unavailable_resources=unavailable_resources,
        ),
    }
    if unavailable_resources:
        summary['degraded'] = True
        summary['unavailable_resources'] = unavailable_resources
    return summary


class K8sClusterViewSet(K8sAccessMixin, K8sResourceMixin, RBACPermissionMixin, viewsets.ModelViewSet):
    """K8s 集群连接管理"""
    queryset = K8sCluster.objects.all()
    serializer_class = K8sClusterSerializer
    pagination_class = None
    rbac_permissions = {
        'list': ['ops.k8s.view'],
        'retrieve': ['ops.k8s.view'],
        'create': ['ops.k8s.manage'],
        'update': ['ops.k8s.manage'],
        'partial_update': ['ops.k8s.manage'],
        'destroy': ['ops.k8s.manage'],
        'test_connection': ['ops.k8s.manage'],
        'summary': ['ops.k8s.view'],
        'capacity': ['ops.k8s.view'],
        'namespaces': ['ops.k8s.view'],
        'pods': ['ops.k8s.view'],
        'services': ['ops.k8s.view'],
        'deployments': ['ops.k8s.view'],
        'restart_pod': ['ops.k8s.manage'],
        'pod_exec': ['ops.k8s.exec'],
        'kubectl': ['ops.k8s.kubectl'],
        'scale_workload': ['ops.k8s.manage'],
        'nodes': ['ops.k8s.view'],
        'statefulsets': ['ops.k8s.view'],
        'daemonsets': ['ops.k8s.view'],
        'jobs': ['ops.k8s.view'],
        'cronjobs': ['ops.k8s.view'],
        'ingresses': ['ops.k8s.view'],
        'pvs': ['ops.k8s.view'],
        'pvcs': ['ops.k8s.view'],
        'storageclasses': ['ops.k8s.view'],
        'configmaps': ['ops.k8s.view'],
        'secrets': ['ops.k8s.view'],
        'resource_yaml': ['ops.k8s.view'],
        'config_resource_detail': ['ops.k8s.view'],
        'config_resource_preview': ['ops.k8s.manage'],
        'config_resource_update': ['ops.k8s.manage'],
        'config_resource_revisions': ['ops.k8s.view'],
        'config_resource_revision_preview': ['ops.k8s.view'],
        'config_resource_rollback_preview': ['ops.k8s.manage'],
        'config_resource_rollback': ['ops.k8s.manage'],
        'config_resource_rollback_to_revision': ['ops.k8s.manage'],
        'workload_pods': ['ops.k8s.view'],
        'pod_logs': ['ops.k8s.view'],
        'resource_events': ['ops.k8s.view'],
        'resources': ['ops.k8s.view'],
        'yaml_preview': ['ops.k8s.manage'],
        'yaml_apply': ['ops.k8s.manage'],
        'resource_delete': ['ops.k8s.manage'],
        'workload_action': ['ops.k8s.manage'],
        'node_action': ['ops.k8s.manage'],
    }

    def perform_create(self, serializer):
        from rbac.k8s_access import get_k8s_grants
        from rest_framework.exceptions import PermissionDenied
        if get_k8s_grants(self.request.user) is not None:
            raise PermissionDenied('指定集群授权的用户不能新增集群连接。')
        instance = serializer.save()
        _invalidate_cluster_runtime_cache(instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        cache.delete_many([_server_version_cache_key(instance.pk), _summary_stale_cache_key(instance.pk)])
        _invalidate_cluster_runtime_cache(instance)

    def perform_destroy(self, instance):
        cache.delete(_server_version_cache_key(instance.pk))
        _invalidate_cluster_runtime_cache(instance)
        instance.delete()

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """测试集群连接"""
        cluster = self.get_object()
        if _is_demo(cluster):
            _invalidate_cluster_runtime_cache(cluster)
            return Response({'success': True, 'message': '连接成功 (Kubernetes v1.29.3) [演示模式]'})
        try:
            k8s = _get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            version = k8s.VersionApi().get_code()
            cluster.status = 'connected'
            cluster.save(update_fields=['status'])
            _invalidate_cluster_runtime_cache(cluster)
            return Response({
                'success': True,
                'message': f'连接成功 (Kubernetes {version.git_version})',
            })
        except Exception as e:
            cluster.status = 'error'
            cluster.save(update_fields=['status'])
            _invalidate_cluster_runtime_cache(cluster)
            error_text = str(e)
            if isinstance(e, ssl.SSLCertVerificationError) or 'CERTIFICATE_VERIFY_FAILED' in error_text or 'certificate verify failed' in error_text.lower():
                error_text = (
                    '证书校验失败：当前 API Server 地址与 kubeconfig 证书不匹配。'
                    '请改用证书 SAN 中的域名或 IP，'
                    '或者在 apiserver 证书中加入该 IP 的 SAN，'
                    '也可以在 kubeconfig 中启用 insecure-skip-tls-verify。'
                )
            return Response({'success': False, 'message': f'连接失败: {error_text}'})

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Get cluster summary."""
        cluster = self.get_object()
        allowed_namespaces = self.k8s_access_scope['namespaces']
        if allowed_namespaces:
            pods = get_k8s_pods_snapshot(cluster, allowed_namespaces)
            workloads = [item for kind in ('deployments', 'statefulsets', 'daemonsets', 'jobs', 'cronjobs')
                         for item in get_k8s_resource_snapshot(cluster, kind, allowed_namespaces)]
            pvcs = get_k8s_resource_snapshot(cluster, 'pvcs', allowed_namespaces)
            return Response({
                'status': cluster.status, 'scoped': True, 'nodes_total': 0, 'nodes_ready': 0,
                'server_version': _get_cluster_server_version(cluster),
                'pods_total': len(pods), 'pods_abnormal': sum(item.get('status') not in {'Running', 'Succeeded'} for item in pods),
                'total_restarts': sum(item.get('restarts', 0) for item in pods),
                'workloads_total': len(workloads), 'pvcs_pending': sum(item.get('status') != 'Bound' for item in pvcs), 'alerts': [],
            })
        cache_key = _summary_cache_key(cluster.id)
        cached = cache.get(cache_key)
        if cached:
            if _is_unreliable_zero_summary(cached):
                cache.delete(cache_key)
            else:
                return Response(cached)
        try:
            summary = _build_demo_summary(cluster) if _is_demo(cluster) else _build_live_summary(cluster)
            if cluster.status != 'connected':
                cluster.status = 'connected'
                cluster.save(update_fields=['status'])
                summary['status'] = cluster.status
            return Response(_cache_summary_snapshot(cluster, summary))
        except Exception as e:
            if cluster.status != 'error':
                cluster.status = 'error'
                cluster.save(update_fields=['status'])
            _clear_summary_cache(cluster)
            fallback = cache.get(_summary_stale_cache_key(cluster.id))
            if fallback is not None:
                payload = _summary_stale_payload(cluster, fallback)
            else:
                payload = _build_unavailable_summary(cluster, str(e))
            if not _is_unreliable_zero_summary(payload):
                cache.set(cache_key, payload, K8S_SUMMARY_CACHE_TTL)
            return Response(payload)

    @action(detail=True, methods=['get'])
    def capacity(self, request, pk=None):
        """Full-cluster capacity, cached independently from resource lists."""
        cluster = self.get_object()
        cache_key = _resource_cache_key(cluster.id, 'capacity')
        payload = cache.get(cache_key)
        if payload is not None:
            return Response(payload)
        if _is_demo(cluster):
            pods = _get_demo_state(cluster.id, 'pods', DEMO_PODS)
            payload = demo_cluster_capacity(sum(item.get('status') not in {'Succeeded', 'Failed'} for item in pods))
        else:
            try:
                k8s = _get_k8s_client(cluster)
                try:
                    payload = build_cluster_capacity(k8s)
                finally:
                    k8s.ApiClient().close()
            except Exception:
                return Response({'detail': '获取集群容量失败，请检查集群连接后重试。'}, status=503)
        cache.set(cache_key, payload, 30 if not payload['unavailable_resources'] else 5)
        return Response(payload)

    @action(detail=True, methods=['get'])
    def namespaces(self, request, pk=None):
        """获取命名空间列表"""
        cluster = self.get_object()
        if _is_demo(cluster):
            return Response(_get_demo_state(cluster.id, 'namespaces', DEMO_NAMESPACES))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                ns_list = v1.list_namespace()
                return [{
                    'name': ns.metadata.name,
                    'status': ns.status.phase,
                    'created': ns.metadata.creation_timestamp.isoformat() if ns.metadata.creation_timestamp else '',
                    'labels': ns.metadata.labels or {},
                } for ns in ns_list.items]

            data = _get_or_set_resource_cache(cluster, 'namespaces', '_all', loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': f'获取命名空间失败: {str(e)}'}, status=400)

    @action(detail=True, methods=['get'])
    def pods(self, request, pk=None):
        """获取 Pod 列表"""
        cluster = self.get_object()
        namespace = request.query_params.get('namespace', 'default')
        if _is_demo(cluster):
            return Response(_filter_by_ns([_serialize_demo_pod_item(pod) for pod in _get_demo_state(cluster.id, 'pods', DEMO_PODS)], namespace))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                if namespace == '_all':
                    pod_list = v1.list_pod_for_all_namespaces()
                else:
                    pod_list = v1.list_namespaced_pod(namespace=namespace)

                return [_serialize_pod_item(pod) for pod in pod_list.items]

            data = _get_or_set_resource_cache(cluster, 'pods', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': f'获取 Pod 列表失败: {str(e)}'}, status=400)

    @action(detail=True, methods=['post'])
    def kubectl(self, request, pk=None):
        """Run one kubectl command against this cluster without invoking a shell."""
        cluster = self.get_object()
        command = str(request.data.get('command', '')).strip()
        try:
            args = _parse_kubectl_command(command)
            return_code, stdout, stderr = _run_kubectl_command(cluster, command)
        except subprocess.TimeoutExpired:
            return Response({'success': False, 'message': f'命令执行超过 {K8S_KUBECTL_TIMEOUT} 秒，已停止'}, status=408)
        except (ValueError, RuntimeError) as exc:
            return Response({'success': False, 'message': str(exc)}, status=400)
        except Exception as exc:
            logger.exception('K8s kubectl console failed for cluster %s', cluster.id)
            return Response({'success': False, 'message': f'kubectl 执行失败: {exc}'}, status=400)

        success = return_code == 0
        record_event(
            module='ops',
            category='k8s',
            action='kubectl',
            title=f'K8s 控制台执行: {cluster.name}',
            summary=f'kubectl {_kubectl_audit_summary(args)}',
            result='success' if success else 'failed',
            severity='info' if success else 'warning',
            request=request,
            resource_module='ops',
            resource_type='k8s_cluster',
            resource_id=cluster.id,
            resource_name=cluster.name,
            metadata={'command_summary': _kubectl_audit_summary(args), 'exit_code': return_code},
            is_demo=_is_demo(cluster),
        )
        return Response({
            'success': success,
            'exit_code': return_code,
            'stdout': stdout,
            'stderr': stderr,
        }, status=200 if success else 400)

    @action(detail=True, methods=['get'])
    def services(self, request, pk=None):
        """获取 Service 列表"""
        cluster = self.get_object()
        namespace = request.query_params.get('namespace', 'default')
        if _is_demo(cluster):
            return Response(_filter_by_ns(_get_demo_state(cluster.id, 'services', DEMO_SERVICES), namespace))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                if namespace == '_all':
                    svc_list = v1.list_service_for_all_namespaces()
                else:
                    svc_list = v1.list_namespaced_service(namespace=namespace)

                return [{
                    'name': svc.metadata.name,
                    'namespace': svc.metadata.namespace,
                    'type': svc.spec.type,
                    'cluster_ip': svc.spec.cluster_ip or '',
                    'external_ip': ','.join(svc.spec.external_ips or []),
                    'ports': ', '.join([
                        f"{p.port}{'→'+str(p.node_port) if p.node_port else ''}/{p.protocol}"
                        for p in (svc.spec.ports or [])
                    ]),
                    'created': svc.metadata.creation_timestamp.isoformat() if svc.metadata.creation_timestamp else '',
                } for svc in svc_list.items]

            data = _get_or_set_resource_cache(cluster, 'services', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': f'获取 Service 列表失败: {str(e)}'}, status=400)

    @action(detail=True, methods=['get'])
    def deployments(self, request, pk=None):
        """获取 Deployment 列表"""
        cluster = self.get_object()
        namespace = request.query_params.get('namespace', 'default')
        if _is_demo(cluster):
            demo_items = _get_demo_state(cluster.id, 'deployments', DEMO_DEPLOYMENTS)
            return Response(_filter_by_ns(demo_items, namespace))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                apps_v1 = k8s.AppsV1Api()
                if namespace == '_all':
                    dep_list = apps_v1.list_deployment_for_all_namespaces()
                else:
                    dep_list = apps_v1.list_namespaced_deployment(namespace=namespace)

                return [{
                    'name': dep.metadata.name,
                    'namespace': dep.metadata.namespace,
                    'replicas': dep.spec.replicas or 0,
                    'ready_replicas': dep.status.ready_replicas or 0,
                    'available_replicas': dep.status.available_replicas or 0,
                    'images': ', '.join([c.image for c in dep.spec.template.spec.containers]),
                    'created': dep.metadata.creation_timestamp.isoformat() if dep.metadata.creation_timestamp else '',
                } for dep in dep_list.items]

            data = _get_or_set_resource_cache(cluster, 'deployments', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': f'获取 Deployment 列表失败: {str(e)}'}, status=400)

    @action(detail=True, methods=['post'], url_path='pods/(?P<pod_name>[^/]+)/restart')
    def restart_pod(self, request, pk=None, pod_name=None):
        """删除 Pod 以触发重启"""
        cluster = self.get_object()
        if _is_demo(cluster):
            _invalidate_cluster_runtime_cache(cluster)
            return Response({'success': True, 'message': f'Pod {pod_name} 正在重启 [演示模式]'})
        namespace = request.data.get('namespace', 'default')
        try:
            k8s = _get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
            _invalidate_cluster_runtime_cache(cluster)
            return Response({'success': True, 'message': f'Pod {pod_name} 正在重启'})
        except Exception as e:
            return Response({'success': False, 'message': f'重启失败: {str(e)}'}, status=400)

    # ====== 节点管理 ======
    @action(detail=True, methods=['get'])
    def nodes(self, request, pk=None):
        """Get node list."""
        cluster = self.get_object()
        if _is_demo(cluster):
            return Response(_get_demo_state(cluster.id, 'nodes', DEMO_NODES))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                node_list = v1.list_node()
                data = []
                for node in node_list.items:
                    conditions = {c.type: c.status for c in (node.status.conditions or [])}
                    roles = ','.join([l.replace('node-role.kubernetes.io/', '') for l in (node.metadata.labels or {}) if l.startswith('node-role.kubernetes.io/')])
                    capacity = node.status.capacity or {}
                    data.append({
                        'name': node.metadata.name,
                        'status': 'Ready' if conditions.get('Ready') == 'True' else 'NotReady',
                        'roles': roles or 'worker',
                        'version': node.status.node_info.kubelet_version if node.status.node_info else '',
                        'internal_ip': next((a.address for a in (node.status.addresses or []) if a.type == 'InternalIP'), ''),
                        'os_image': node.status.node_info.os_image if node.status.node_info else '',
                        'cpu': capacity.get('cpu', ''),
                        'memory': capacity.get('memory', ''),
                        'pods_count': 0,
                        'unschedulable': bool(node.spec.unschedulable),
                        'age': '',
                        'created': node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else '',
                    })
                return data

            data = _get_or_set_resource_cache(cluster, 'nodes', '_all', loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': f'Failed to load nodes: {str(e)}'}, status=400)

    @action(detail=True, methods=['get'])
    def statefulsets(self, request, pk=None):
        cluster = self.get_object()
        namespace = request.query_params.get('namespace', 'default')
        if _is_demo(cluster):
            demo_items = _get_demo_state(cluster.id, 'statefulsets', DEMO_STATEFULSETS)
            return Response(_filter_by_ns(demo_items, namespace))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                apps_v1 = k8s.AppsV1Api()
                items = (apps_v1.list_stateful_set_for_all_namespaces() if namespace == '_all'
                         else apps_v1.list_namespaced_stateful_set(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'replicas': i.spec.replicas or 0, 'ready_replicas': i.status.ready_replicas or 0,
                         'current_replicas': i.status.current_replicas or 0,
                         'images': ', '.join([c.image for c in i.spec.template.spec.containers]),
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'statefulsets', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['get'])
    def daemonsets(self, request, pk=None):
        cluster = self.get_object()
        namespace = request.query_params.get('namespace', 'default')
        if _is_demo(cluster):
            return Response(_filter_by_ns(_get_demo_state(cluster.id, 'daemonsets', DEMO_DAEMONSETS), namespace))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                apps_v1 = k8s.AppsV1Api()
                items = (apps_v1.list_daemon_set_for_all_namespaces() if namespace == '_all'
                         else apps_v1.list_namespaced_daemon_set(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'desired': i.status.desired_number_scheduled or 0, 'current': i.status.current_number_scheduled or 0,
                         'ready': i.status.number_ready or 0,
                         'images': ', '.join([c.image for c in i.spec.template.spec.containers]),
                         'node_selector': str(i.spec.template.spec.node_selector or ''),
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'daemonsets', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['get'])
    def jobs(self, request, pk=None):
        cluster = self.get_object()
        namespace = request.query_params.get('namespace', 'default')
        if _is_demo(cluster):
            return Response(_filter_by_ns(_get_demo_state(cluster.id, 'jobs', DEMO_JOBS), namespace))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                batch_v1 = k8s.BatchV1Api()
                items = (batch_v1.list_job_for_all_namespaces() if namespace == '_all'
                         else batch_v1.list_namespaced_job(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'completions': f'{i.status.succeeded or 0}/{i.spec.completions or 1}',
                         'duration': '', 'status': 'Complete' if (i.status.succeeded or 0) >= (i.spec.completions or 1) else 'Running',
                         'images': ', '.join([c.image for c in i.spec.template.spec.containers]),
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'jobs', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['get'])
    def cronjobs(self, request, pk=None):
        cluster = self.get_object()
        namespace = request.query_params.get('namespace', 'default')
        if _is_demo(cluster):
            return Response(_filter_by_ns(_get_demo_state(cluster.id, 'cronjobs', DEMO_CRONJOBS), namespace))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                batch_v1 = k8s.BatchV1Api()
                items = (batch_v1.list_cron_job_for_all_namespaces() if namespace == '_all'
                         else batch_v1.list_namespaced_cron_job(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'schedule': i.spec.schedule, 'suspend': i.spec.suspend or False,
                         'active': len(i.status.active or []),
                         'last_schedule': i.status.last_schedule_time.isoformat() if i.status.last_schedule_time else '',
                         'images': ', '.join([c.image for c in i.spec.job_template.spec.template.spec.containers]),
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'cronjobs', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    # ====== 网络管理 ======
    @action(detail=True, methods=['get'])
    def ingresses(self, request, pk=None):
        cluster = self.get_object()
        namespace = request.query_params.get('namespace', 'default')
        if _is_demo(cluster):
            return Response(_filter_by_ns(_get_demo_state(cluster.id, 'ingresses', DEMO_INGRESSES), namespace))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                net_v1 = k8s.NetworkingV1Api()
                items = (net_v1.list_ingress_for_all_namespaces() if namespace == '_all'
                         else net_v1.list_namespaced_ingress(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'class': i.spec.ingress_class_name or '',
                         'hosts': ', '.join([r.host for r in (i.spec.rules or []) if r.host]),
                         'address': ', '.join([lb.ip or lb.hostname or '' for lb in (i.status.load_balancer.ingress or [])]) if i.status.load_balancer and i.status.load_balancer.ingress else '',
                         'ports': '80, 443' if i.spec.tls else '80',
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'ingresses', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    # ====== 存储管理 ======
    @action(detail=True, methods=['get'])
    def pvs(self, request, pk=None):
        cluster = self.get_object()
        if _is_demo(cluster):
            return Response(_get_demo_state(cluster.id, 'pvs', DEMO_PVS))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                items = v1.list_persistent_volume().items
                return [{'name': i.metadata.name, 'capacity': (i.spec.capacity or {}).get('storage', ''),
                         'access_modes': ','.join(i.spec.access_modes or []),
                         'reclaim_policy': i.spec.persistent_volume_reclaim_policy or '',
                         'status': i.status.phase, 'claim': f'{i.spec.claim_ref.namespace}/{i.spec.claim_ref.name}' if i.spec.claim_ref else '',
                         'storage_class': i.spec.storage_class_name or '',
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'pvs', '_all', loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['get'])
    def pvcs(self, request, pk=None):
        cluster = self.get_object()
        namespace = request.query_params.get('namespace', 'default')
        if _is_demo(cluster):
            return Response(_filter_by_ns(_get_demo_state(cluster.id, 'pvcs', DEMO_PVCS), namespace))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                items = (v1.list_persistent_volume_claim_for_all_namespaces() if namespace == '_all'
                         else v1.list_namespaced_persistent_volume_claim(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'status': i.status.phase, 'volume': i.spec.volume_name or '',
                         'capacity': (i.status.capacity or {}).get('storage', ''),
                         'access_modes': ','.join(i.spec.access_modes or []),
                         'storage_class': i.spec.storage_class_name or '',
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'pvcs', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['get'])
    def storageclasses(self, request, pk=None):
        cluster = self.get_object()
        if _is_demo(cluster):
            return Response(_get_demo_state(cluster.id, 'storageclasses', DEMO_STORAGECLASSES))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                storage_v1 = k8s.StorageV1Api()
                items = storage_v1.list_storage_class().items
                return [{'name': i.metadata.name, 'provisioner': i.provisioner,
                         'reclaim_policy': i.reclaim_policy or 'Delete',
                         'binding_mode': i.volume_binding_mode or 'Immediate',
                         'allow_expansion': i.allow_volume_expansion or False,
                         'is_default': (i.metadata.annotations or {}).get('storageclass.kubernetes.io/is-default-class') == 'true',
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'storageclasses', '_all', loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    # ====== 配置管理 ======
    @action(detail=True, methods=['get'])
    def configmaps(self, request, pk=None):
        cluster = self.get_object()
        namespace = request.query_params.get('namespace', 'default')
        if _is_demo(cluster):
            demo_items = _get_demo_state(cluster.id, 'configmaps', DEMO_CONFIGMAPS)
            return Response(_filter_by_ns(demo_items, namespace))
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                items = (v1.list_config_map_for_all_namespaces() if namespace == '_all'
                         else v1.list_namespaced_config_map(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'data_count': len(i.data or {}),
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'configmaps', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['get'])
    def secrets(self, request, pk=None):
        cluster = self.get_object()
        namespace = request.query_params.get('namespace', 'default')
        if _is_demo(cluster):
            demo_items = _get_demo_state(cluster.id, 'secrets', DEMO_SECRETS)
            return Response([
                {key: value for key, value in item.items() if key not in {'data', 'stringData', 'data_payload'}}
                for item in _filter_by_ns(demo_items, namespace)
            ])
        try:
            def loader():
                k8s = _get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                items = (v1.list_secret_for_all_namespaces() if namespace == '_all'
                         else v1.list_namespaced_secret(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'type': i.type or 'Opaque', 'data_count': len(i.data or {}),
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'secrets', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    # ====== YAML 查看 ======
    def _get_demo_config_resource(self, cluster, resource_type, namespace, name):
        cache_name = 'configmaps' if resource_type == 'configmap' else 'secrets'
        defaults = DEMO_CONFIGMAPS if resource_type == 'configmap' else DEMO_SECRETS
        items = _get_demo_state(cluster.id, cache_name, defaults)
        for item in items:
            if item.get('name') == name and item.get('namespace') == namespace:
                payload = item.get('data_payload')
                if payload is None:
                    payload = {f'key{i + 1}': f'value{i + 1}' for i in range(item.get('data_count', 1))}
                return {
                    'resource_type': resource_type,
                    'name': item.get('name', name),
                    'namespace': item.get('namespace', namespace),
                    'secret_type': item.get('type', 'Opaque'),
                    'data': payload,
                    'text': _dump_config_text(payload),
                    'updated_at': item.get('updated_at', ''),
                    'updated_by': item.get('updated_by', ''),
                }
        raise ValueError(f'Resource not found: {resource_type}/{namespace}/{name}')

    def _update_demo_config_resource(self, cluster, resource_type, namespace, name, data, username):
        import datetime as _dt

        cache_name = 'configmaps' if resource_type == 'configmap' else 'secrets'
        defaults = DEMO_CONFIGMAPS if resource_type == 'configmap' else DEMO_SECRETS
        items = _get_demo_state(cluster.id, cache_name, defaults)
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        for item in items:
            if item.get('name') == name and item.get('namespace') == namespace:
                previous = item.get('data_payload')
                if previous is None:
                    previous = {f'key{i + 1}': f'value{i + 1}' for i in range(item.get('data_count', 1))}
                backup = {
                    'resource_type': resource_type,
                    'name': name,
                    'namespace': namespace,
                    'secret_type': item.get('type', 'Opaque'),
                    'data': previous,
                    'text': _dump_config_text(previous),
                    'updated_at': item.get('updated_at', ''),
                    'updated_by': item.get('updated_by', ''),
                }
                item['data_payload'] = data
                item['data_count'] = len(data)
                item['updated_at'] = now
                item['updated_by'] = username
                _set_demo_state(cluster.id, cache_name, items)
                manifests = _get_demo_state(cluster.id, 'manifests', {})
                manifest = manifests.get(f'{resource_type}/{namespace}/{name}')
                if manifest is not None:
                    manifest.pop('data', None)
                    manifest.pop('stringData', None)
                    _set_demo_state(cluster.id, 'manifests', manifests)
                    patch_demo_manifest(cluster.id, resource_type, namespace, name,
                                        {'stringData' if resource_type == 'secret' else 'data': data})
                cache.set(_demo_config_backup_key(cluster.id, resource_type, namespace, name), backup, K8S_DEMO_STATE_CACHE_TTL)
                return {
                    'resource_type': resource_type,
                    'name': name,
                    'namespace': namespace,
                    'secret_type': item.get('type', 'Opaque'),
                    'data': data,
                    'text': _dump_config_text(data),
                    'updated_at': now,
                    'updated_by': username,
                }
        raise ValueError(f'Resource not found: {resource_type}/{namespace}/{name}')

    def _get_live_config_resource(self, cluster, resource_type, namespace, name):
        k8s = _get_k8s_client(cluster)
        v1 = k8s.CoreV1Api()
        if resource_type == 'configmap':
            obj = v1.read_namespaced_config_map(name, namespace)
            data = obj.data or {}
            secret_type = ''
        else:
            obj = v1.read_namespaced_secret(name, namespace)
            data = {}
            for key, value in (obj.data or {}).items():
                try:
                    data[key] = base64.b64decode(value).decode('utf-8')
                except Exception:
                    data[key] = ''
            secret_type = obj.type or 'Opaque'
        return {
            'resource_type': resource_type,
            'name': obj.metadata.name,
            'namespace': obj.metadata.namespace,
            'secret_type': secret_type,
            'resource_version': obj.metadata.resource_version or '',
            'data': {str(key): '' if value is None else str(value) for key, value in data.items()},
            'text': _dump_config_text(data),
            'updated_at': obj.metadata.creation_timestamp.isoformat() if obj.metadata.creation_timestamp else '',
            'updated_by': '',
        }

    def _apply_live_config_resource(self, cluster, resource_type, namespace, name, data, username):
        k8s = _get_k8s_client(cluster)
        v1 = k8s.CoreV1Api()
        current = self._get_live_config_resource(cluster, resource_type, namespace, name)
        cache.set(_config_backup_key(cluster.id, resource_type, namespace, name), current, K8S_DEMO_STATE_CACHE_TTL)
        if resource_type == 'configmap':
            body = v1.read_namespaced_config_map(name, namespace)
            body.data = data
            v1.replace_namespaced_config_map(name, namespace, body)
        else:
            body = v1.read_namespaced_secret(name, namespace)
            body.data = {
                key: base64.b64encode(value.encode('utf-8')).decode('utf-8')
                for key, value in data.items()
            }
            v1.replace_namespaced_secret(name, namespace, body)
        refreshed = self._get_live_config_resource(cluster, resource_type, namespace, name)
        refreshed['updated_by'] = username
        return refreshed

    def _get_config_resource(self, cluster, resource_type, namespace, name):
        if _is_demo(cluster):
            detail = self._get_demo_config_resource(cluster, resource_type, namespace, name)
            backup = cache.get(_demo_config_backup_key(cluster.id, resource_type, namespace, name))
        else:
            detail = self._get_live_config_resource(cluster, resource_type, namespace, name)
            backup = cache.get(_config_backup_key(cluster.id, resource_type, namespace, name))
        latest_revision = _config_revision_queryset(cluster, resource_type, namespace, name).first()
        detail['rollback_available'] = bool(latest_revision or backup)
        detail['revision_count'] = _config_revision_queryset(cluster, resource_type, namespace, name).count()
        detail['latest_revision_id'] = latest_revision.id if latest_revision else None
        detail['latest_revision_at'] = latest_revision.created_at.isoformat() if latest_revision and latest_revision.created_at else ''
        return detail

    def _get_latest_config_snapshot(self, cluster, resource_type, namespace, name):
        revision = _config_revision_queryset(cluster, resource_type, namespace, name).first()
        if revision:
            snapshot = _serialize_revision(revision)
            snapshot['data'] = _normalize_config_text(revision.content)
            snapshot['text'] = revision.content
            return snapshot

        backup_key = _demo_config_backup_key(cluster.id, resource_type, namespace, name) if _is_demo(cluster) else _config_backup_key(cluster.id, resource_type, namespace, name)
        backup = cache.get(backup_key)
        if not backup:
            return None
        return backup

    @action(detail=True, methods=['post'], url_path='pod_exec')
    def pod_exec(self, request, pk=None):
        cluster = self.get_object()
        pod_name = request.data.get('pod_name', '')
        namespace = request.data.get('namespace', 'default')
        container = request.data.get('container', '')
        command = request.data.get('command', 'pwd')
        if not pod_name:
            return Response({'detail': 'Missing pod_name parameter'}, status=400)
        if not command:
            return Response({'detail': 'Missing command parameter'}, status=400)

        if _is_demo(cluster):
            output = '\n'.join([
                f'$ {command}',
                f'demo-exec on {pod_name} ({namespace})',
                'uid=1000 gid=1000 groups=1000',
                '/app',
            ])
            return Response({
                'success': True,
                'pod_name': pod_name,
                'namespace': namespace,
                'container': container or 'main',
                'command': command,
                'output': output,
            })

        try:
            from kubernetes.stream import stream

            k8s = _get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            kwargs = {
                'name': pod_name,
                'namespace': namespace,
                'command': ['/bin/sh', '-lc', command],
                'stderr': True,
                'stdin': False,
                'stdout': True,
                'tty': False,
            }
            if container:
                kwargs['container'] = container
            output = stream(v1.connect_get_namespaced_pod_exec, **kwargs)
            return Response({
                'success': True,
                'pod_name': pod_name,
                'namespace': namespace,
                'container': container or '',
                'command': command,
                'output': output or '',
            })
        except Exception as e:
            return Response({'detail': f'Pod exec failed: {str(e)}'}, status=400)

    @action(detail=True, methods=['post'], url_path='scale_workload')
    def scale_workload(self, request, pk=None):
        cluster = self.get_object()
        workload_type = request.data.get('workload_type', '')
        name = request.data.get('name', '')
        namespace = request.data.get('namespace', 'default')
        replicas = request.data.get('replicas')
        if workload_type not in ('deployment', 'statefulset'):
            return Response({'detail': 'Only Deployment and StatefulSet scaling is supported'}, status=400)
        if not name:
            return Response({'detail': 'Missing name parameter'}, status=400)
        try:
            replicas = int(replicas)
        except (TypeError, ValueError):
            return Response({'detail': 'replicas must be an integer'}, status=400)
        if replicas < 0:
            return Response({'detail': 'replicas must be greater than or equal to 0'}, status=400)

        if _is_demo(cluster):
            cache_name = 'deployments' if workload_type == 'deployment' else 'statefulsets'
            defaults = DEMO_DEPLOYMENTS if workload_type == 'deployment' else DEMO_STATEFULSETS
            items = _get_demo_state(cluster.id, cache_name, defaults)
            for item in items:
                if item.get('name') == name and item.get('namespace') == namespace:
                    item['replicas'] = replicas
                    item['ready_replicas'] = min(item.get('ready_replicas', 0), replicas)
                    if workload_type == 'deployment':
                        item['available_replicas'] = min(item.get('available_replicas', item.get('ready_replicas', 0)), replicas)
                    _set_demo_state(cluster.id, cache_name, items)
                    patch_demo_manifest(cluster.id, workload_type, namespace, name, {'spec': {'replicas': replicas}})
                    _invalidate_cluster_runtime_cache(cluster)
                    return Response({'success': True, 'message': f'{name} scaled to {replicas} replicas'})
            return Response({'detail': f'Resource not found: {workload_type}/{namespace}/{name}'}, status=404)

        try:
            k8s = _get_k8s_client(cluster)
            apps_v1 = k8s.AppsV1Api()
            body = {'spec': {'replicas': replicas}}
            if workload_type == 'deployment':
                apps_v1.patch_namespaced_deployment_scale(name, namespace, body)
            else:
                apps_v1.patch_namespaced_stateful_set_scale(name, namespace, body)
            _invalidate_cluster_runtime_cache(cluster)
            return Response({'success': True, 'message': f'{name} scaled to {replicas} replicas'})
        except Exception as e:
            return Response({'detail': f'Scale failed: {str(e)}'}, status=400)

    @action(detail=True, methods=['get'], url_path='config_resource_detail')
    def config_resource_detail(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.query_params.get('type', '')
        name = request.query_params.get('name', '')
        namespace = request.query_params.get('namespace', 'default')
        if resource_type not in ('configmap', 'secret') or not name:
            return Response({'detail': 'Valid type and name are required'}, status=400)
        try:
            return Response(self._get_config_resource(cluster, resource_type, namespace, name))
        except Exception as e:
            return Response({'detail': f'Failed to load config resource: {str(e)}'}, status=400)

    @action(detail=True, methods=['post'], url_path='config_resource_preview')
    def config_resource_preview(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.data.get('type', '')
        name = request.data.get('name', '')
        namespace = request.data.get('namespace', 'default')
        content = request.data.get('content', '')
        if resource_type not in ('configmap', 'secret') or not name:
            return Response({'detail': 'Valid type and name are required'}, status=400)
        try:
            current = self._get_config_resource(cluster, resource_type, namespace, name)
            target_data = _normalize_config_text(content)
            target_text = _dump_config_text(target_data)
            return Response({
                'content': target_text,
                'changed': current.get('text', '') != target_text,
                'diff': _build_text_diff(current.get('text', ''), target_text, 'current', 'proposed'),
            })
        except Exception as e:
            return Response({'detail': f'Preview failed: {str(e)}'}, status=400)

    @action(detail=True, methods=['post'], url_path='config_resource_update')
    def config_resource_update(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.data.get('type', '')
        name = request.data.get('name', '')
        namespace = request.data.get('namespace', 'default')
        content = request.data.get('content', '')
        if resource_type not in ('configmap', 'secret') or not name:
            return Response({'detail': 'Valid type and name are required'}, status=400)
        try:
            current = self._get_config_resource(cluster, resource_type, namespace, name)
            data = _normalize_config_text(content)
            username = request.user.username if request.user and request.user.is_authenticated else ''
            _create_config_revision(cluster, resource_type, namespace, name, current, username, 'update')
            if _is_demo(cluster):
                detail = self._update_demo_config_resource(cluster, resource_type, namespace, name, data, username)
            else:
                detail = self._apply_live_config_resource(cluster, resource_type, namespace, name, data, username)
            _invalidate_cluster_runtime_cache(cluster)
            detail['rollback_available'] = True
            detail['revision_count'] = _config_revision_queryset(cluster, resource_type, namespace, name).count()
            return Response({'success': True, 'message': f'{resource_type} updated', 'resource': detail})
        except Exception as e:
            return Response({'detail': f'Update failed: {str(e)}'}, status=400)

    @action(detail=True, methods=['get'], url_path='config_resource_revisions')
    def config_resource_revisions(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.query_params.get('type', '')
        name = request.query_params.get('name', '')
        namespace = request.query_params.get('namespace', 'default')
        if resource_type not in ('configmap', 'secret') or not name:
            return Response({'detail': 'Valid type and name are required'}, status=400)

        revisions = [
            _serialize_revision(item)
            for item in _config_revision_queryset(cluster, resource_type, namespace, name)[:20]
        ]
        return Response({'count': len(revisions), 'items': revisions})

    @action(detail=True, methods=['get'], url_path='config_resource_revision_preview')
    def config_resource_revision_preview(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.query_params.get('type', '')
        name = request.query_params.get('name', '')
        namespace = request.query_params.get('namespace', 'default')
        revision_id = request.query_params.get('revision_id')
        if resource_type not in ('configmap', 'secret') or not name or not revision_id:
            return Response({'detail': 'Valid type, name and revision_id are required'}, status=400)

        revision = _config_revision_queryset(cluster, resource_type, namespace, name).filter(id=revision_id).first()
        if not revision:
            return Response({'detail': 'Revision not found'}, status=404)

        try:
            current = self._get_config_resource(cluster, resource_type, namespace, name)
            return Response({
                'revision': _serialize_revision(revision),
                'diff': _build_text_diff(current.get('text', ''), revision.content, 'current', f'revision-{revision.id}'),
            })
        except Exception as e:
            return Response({'detail': f'Failed to load revision preview: {str(e)}'}, status=400)

    @action(detail=True, methods=['get'], url_path='config_resource_rollback_preview')
    def config_resource_rollback_preview(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.query_params.get('type', '')
        name = request.query_params.get('name', '')
        namespace = request.query_params.get('namespace', 'default')
        if resource_type not in ('configmap', 'secret') or not name:
            return Response({'detail': 'Valid type and name are required'}, status=400)
        backup = self._get_latest_config_snapshot(cluster, resource_type, namespace, name)
        if not backup:
            return Response({'detail': 'No rollback snapshot available'}, status=404)
        try:
            current = self._get_config_resource(cluster, resource_type, namespace, name)
            return Response({
                'rollback_available': True,
                'backup': backup,
                'diff': _build_text_diff(current.get('text', ''), backup.get('text', ''), 'current', 'rollback'),
            })
        except Exception as e:
            return Response({'detail': f'Failed to load rollback preview: {str(e)}'}, status=400)

    @action(detail=True, methods=['post'], url_path='config_resource_rollback')
    def config_resource_rollback(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.data.get('type', '')
        name = request.data.get('name', '')
        namespace = request.data.get('namespace', 'default')
        if resource_type not in ('configmap', 'secret') or not name:
            return Response({'detail': 'Valid type and name are required'}, status=400)
        backup = self._get_latest_config_snapshot(cluster, resource_type, namespace, name)
        if not backup:
            return Response({'detail': 'No rollback snapshot available'}, status=404)
        try:
            current = self._get_config_resource(cluster, resource_type, namespace, name)
            username = request.user.username if request.user and request.user.is_authenticated else ''
            _create_config_revision(cluster, resource_type, namespace, name, current, username, 'rollback')
            if _is_demo(cluster):
                detail = self._update_demo_config_resource(cluster, resource_type, namespace, name, backup.get('data', {}), username)
            else:
                detail = self._apply_live_config_resource(cluster, resource_type, namespace, name, backup.get('data', {}), username)
            _invalidate_cluster_runtime_cache(cluster)
            detail['rollback_available'] = True
            detail['revision_count'] = _config_revision_queryset(cluster, resource_type, namespace, name).count()
            return Response({'success': True, 'message': f'{resource_type} rolled back', 'resource': detail})
        except Exception as e:
            return Response({'detail': f'Rollback failed: {str(e)}'}, status=400)

    @action(detail=True, methods=['post'], url_path='config_resource_rollback_to_revision')
    def config_resource_rollback_to_revision(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.data.get('type', '')
        name = request.data.get('name', '')
        namespace = request.data.get('namespace', 'default')
        revision_id = request.data.get('revision_id')
        if resource_type not in ('configmap', 'secret') or not name or not revision_id:
            return Response({'detail': 'Valid type, name and revision_id are required'}, status=400)

        revision = _config_revision_queryset(cluster, resource_type, namespace, name).filter(id=revision_id).first()
        if not revision:
            return Response({'detail': 'Revision not found'}, status=404)

        try:
            current = self._get_config_resource(cluster, resource_type, namespace, name)
            target_data = _normalize_config_text(revision.content)
            username = request.user.username if request.user and request.user.is_authenticated else ''
            _create_config_revision(cluster, resource_type, namespace, name, current, username, 'rollback')
            if _is_demo(cluster):
                detail = self._update_demo_config_resource(cluster, resource_type, namespace, name, target_data, username)
            else:
                detail = self._apply_live_config_resource(cluster, resource_type, namespace, name, target_data, username)
            _invalidate_cluster_runtime_cache(cluster)
            detail['rollback_available'] = True
            detail['revision_count'] = _config_revision_queryset(cluster, resource_type, namespace, name).count()
            return Response({
                'success': True,
                'message': f'{resource_type} rolled back to revision #{revision.id}',
                'resource': detail,
                'revision': _serialize_revision(revision),
            })
        except Exception as e:
            return Response({'detail': f'Rollback failed: {str(e)}'}, status=400)

    def _build_demo_yaml(self, resource_type, name, namespace, demo_list):
        """从 demo 数据生成模拟的 YAML"""
        item = None
        for d in demo_list:
            if d.get('name') == name:
                if namespace and namespace != '_all' and d.get('namespace') and d['namespace'] != namespace:
                    continue
                item = d
                break

        if not item:
            item = demo_list[0] if demo_list else {'name': name}

        # 构建一个类似真实 K8s YAML 的结构
        api_version_map = {
            'pod': 'v1', 'service': 'v1', 'namespace': 'v1', 'node': 'v1',
            'configmap': 'v1', 'secret': 'v1', 'pv': 'v1', 'pvc': 'v1',
            'deployment': 'apps/v1', 'statefulset': 'apps/v1', 'daemonset': 'apps/v1',
            'job': 'batch/v1', 'cronjob': 'batch/v1',
            'ingress': 'networking.k8s.io/v1', 'storageclass': 'storage.k8s.io/v1',
        }
        kind_map = {
            'pod': 'Pod', 'service': 'Service', 'namespace': 'Namespace', 'node': 'Node',
            'configmap': 'ConfigMap', 'secret': 'Secret', 'pv': 'PersistentVolume',
            'pvc': 'PersistentVolumeClaim', 'deployment': 'Deployment',
            'statefulset': 'StatefulSet', 'daemonset': 'DaemonSet',
            'job': 'Job', 'cronjob': 'CronJob', 'ingress': 'Ingress',
            'storageclass': 'StorageClass',
        }

        metadata = {'name': item.get('name', name)}
        if item.get('namespace'):
            metadata['namespace'] = item['namespace']
        if item.get('labels'):
            metadata['labels'] = item['labels']
        if item.get('created'):
            metadata['creationTimestamp'] = item['created']

        result = {
            'apiVersion': api_version_map.get(resource_type, 'v1'),
            'kind': kind_map.get(resource_type, resource_type.capitalize()),
            'metadata': metadata,
        }

        # 根据资源类型添加 spec
        if resource_type == 'deployment':
            result['spec'] = {
                'replicas': item.get('replicas', 1),
                'selector': {'matchLabels': {'app': item.get('name', name)}},
                'template': {
                    'metadata': {'labels': {'app': item.get('name', name)}},
                    'spec': {'containers': [{'name': item.get('name', name), 'image': item.get('images', 'nginx:latest'), 'ports': [{'containerPort': 80}]}]},
                },
            }
            result['status'] = {'replicas': item.get('replicas', 1), 'readyReplicas': item.get('ready_replicas', 0), 'availableReplicas': item.get('available_replicas', 0)}
        elif resource_type == 'pod':
            result['spec'] = {
                'containers': [{'name': c.get('name', 'main'), 'image': c.get('image', 'nginx:latest')} for c in item.get('containers', [{'name': 'main', 'image': 'nginx'}])],
                'nodeName': item.get('node', ''),
            }
            result['status'] = {'phase': item.get('status', 'Running'), 'podIP': item.get('ip', '')}
        elif resource_type == 'service':
            result['spec'] = {
                'type': item.get('type', 'ClusterIP'),
                'clusterIP': item.get('cluster_ip', ''),
                'ports': [{'port': 80, 'protocol': 'TCP'}],
                'selector': {'app': item.get('name', name)},
            }
        elif resource_type == 'node':
            result['spec'] = {}
            result['status'] = {
                'conditions': [{'type': 'Ready', 'status': 'True' if item.get('status') == 'Ready' else 'False'}],
                'nodeInfo': {'kubeletVersion': item.get('version', ''), 'osImage': item.get('os_image', '')},
                'addresses': [{'type': 'InternalIP', 'address': item.get('internal_ip', '')}],
                'capacity': {'cpu': item.get('cpu', ''), 'memory': item.get('memory', '')},
            }
        elif resource_type == 'namespace':
            result['status'] = {'phase': item.get('status', 'Active')}
        elif resource_type == 'statefulset':
            result['spec'] = {
                'replicas': item.get('replicas', 1),
                'selector': {'matchLabels': {'app': item.get('name', name)}},
                'template': {
                    'metadata': {'labels': {'app': item.get('name', name)}},
                    'spec': {'containers': [{'name': item.get('name', name), 'image': item.get('images', 'nginx:latest')}]},
                },
            }
            result['status'] = {'replicas': item.get('replicas', 1), 'readyReplicas': item.get('ready_replicas', 0)}
        elif resource_type == 'daemonset':
            result['spec'] = {
                'selector': {'matchLabels': {'app': item.get('name', name)}},
                'template': {
                    'metadata': {'labels': {'app': item.get('name', name)}},
                    'spec': {'containers': [{'name': item.get('name', name), 'image': item.get('images', '')}]},
                },
            }
            result['status'] = {'desiredNumberScheduled': item.get('desired', 0), 'currentNumberScheduled': item.get('current', 0), 'numberReady': item.get('ready', 0)}
        elif resource_type == 'job':
            result['spec'] = {
                'template': {'spec': {'containers': [{'name': 'job', 'image': item.get('images', '')}], 'restartPolicy': 'Never'}},
            }
            result['status'] = {'succeeded': 1 if item.get('status') == 'Complete' else 0}
        elif resource_type == 'cronjob':
            result['spec'] = {
                'schedule': item.get('schedule', ''),
                'suspend': item.get('suspend', False),
                'jobTemplate': {
                    'spec': {'template': {'spec': {'containers': [{'name': 'job', 'image': item.get('images', '')}], 'restartPolicy': 'Never'}}},
                },
            }
        elif resource_type == 'ingress':
            result['spec'] = {
                'ingressClassName': item.get('class', 'nginx'),
                'rules': [{'host': h.strip(), 'http': {'paths': [{'path': '/', 'pathType': 'Prefix', 'backend': {'service': {'name': item.get('name', ''), 'port': {'number': 80}}}}]}} for h in item.get('hosts', '').split(',') if h.strip()],
            }
        elif resource_type == 'pv':
            result['spec'] = {
                'capacity': {'storage': item.get('capacity', '')},
                'accessModes': [item.get('access_modes', 'ReadWriteOnce')],
                'persistentVolumeReclaimPolicy': item.get('reclaim_policy', 'Retain'),
                'storageClassName': item.get('storage_class', ''),
            }
            if item.get('claim'):
                parts = item['claim'].split('/')
                result['spec']['claimRef'] = {'namespace': parts[0] if len(parts) > 1 else '', 'name': parts[-1]}
            result['status'] = {'phase': item.get('status', '')}
        elif resource_type == 'pvc':
            result['spec'] = {
                'accessModes': [item.get('access_modes', 'ReadWriteOnce')],
                'storageClassName': item.get('storage_class', ''),
                'resources': {'requests': {'storage': item.get('capacity', '')}},
                'volumeName': item.get('volume', ''),
            }
            result['status'] = {'phase': item.get('status', '')}
        elif resource_type == 'storageclass':
            result['provisioner'] = item.get('provisioner', '')
            result['reclaimPolicy'] = item.get('reclaim_policy', 'Delete')
            result['volumeBindingMode'] = item.get('binding_mode', 'Immediate')
            result['allowVolumeExpansion'] = item.get('allow_expansion', False)
        elif resource_type == 'configmap':
            payload = item.get('data_payload') or {f'key{i+1}': f'value{i+1}' for i in range(item.get('data_count', 1))}
            result['data'] = payload
        elif resource_type == 'secret':
            payload = item.get('data_payload') or {f'key{i+1}': f'value{i+1}' for i in range(item.get('data_count', 1))}
            result['type'] = item.get('type', 'Opaque')
            result['stringData'] = payload

        return yaml.dump(result, default_flow_style=False, allow_unicode=True, sort_keys=False)

    @action(detail=True, methods=['get'], url_path='resource_yaml')
    def resource_yaml(self, request, pk=None):
        """获取指定资源的 YAML 定义"""
        cluster = self.get_object()
        resource_type = request.query_params.get('type', '')
        name = request.query_params.get('name', '')
        namespace = request.query_params.get('namespace', 'default')

        if resource_type in RESOURCE_TYPES:
            namespace = self._resource_context(cluster, resource_type, namespace, name=name)
            try:
                manifest = self._read_manifest(cluster, resource_type, name, namespace)
                if manifest is None:
                    return Response({'detail': '资源不存在。'}, status=404)
                return Response({'yaml': yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)})
            except Exception as exc:
                return Response({'detail': f'获取 YAML 失败: {exc}'}, status=400)

        return Response({'detail': '不支持的资源类型。'}, status=400)

    # ------ 工作负载 Pod 列表 ------
    @action(detail=True, methods=['get'])
    def workload_pods(self, request, pk=None):
        cluster = self.get_object()
        workload_type = request.query_params.get('workload_type', '')
        workload_name = request.query_params.get('name', '')
        namespace = request.query_params.get('namespace', 'default')

        if _is_demo(cluster):
            # Demo: match pods whose name starts with the workload name
            import datetime as _dt
            now = _dt.datetime.now(_dt.timezone.utc)
            prefix = workload_name
            pods = []
            for p in DEMO_PODS:
                if p['name'].startswith(prefix) and (namespace == '_all' or p['namespace'] == namespace):
                    created = _dt.datetime.fromisoformat(p['created'])
                    age_delta = now - created
                    days = age_delta.days
                    hours = age_delta.seconds // 3600
                    age_str = f'{days}d' if days > 0 else f'{hours}h'
                    host_ip = ''
                    for n in DEMO_NODES:
                        if n['name'] == p.get('node', ''):
                            host_ip = n['internal_ip']
                            break
                    containers = p.get('containers', [])
                    cpu_req = '100m'
                    mem_req = '128Mi'
                    if containers:
                        img = containers[0].get('image', '')
                        if 'mysql' in img: cpu_req, mem_req = '500m', '1Gi'
                        elif 'redis' in img: cpu_req, mem_req = '250m', '256Mi'
                        elif 'prometheus' in img: cpu_req, mem_req = '500m', '512Mi'
                        elif 'nginx' in img: cpu_req, mem_req = '100m', '128Mi'
                    pods.append({
                        'name': p['name'],
                        'namespace': p['namespace'],
                        'status': p['status'],
                        'node': p.get('node', ''),
                        'pod_ip': p.get('ip', ''),
                        'host_ip': host_ip,
                        'containers': [c['name'] for c in containers],
                        'restarts': p.get('restarts', 0),
                        'cpu_request': cpu_req,
                        'memory_request': mem_req,
                        'age': age_str,
                        'created': p['created'],
                    })
            return Response(pods)

        try:
            k8s = _get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            apps_v1 = k8s.AppsV1Api()
            batch_v1 = k8s.BatchV1Api()

            # Get label selector from the workload
            label_selector = ''
            if workload_type == 'deployment':
                obj = apps_v1.read_namespaced_deployment(workload_name, namespace)
                label_selector = ','.join(f'{k}={v}' for k, v in (obj.spec.selector.match_labels or {}).items())
            elif workload_type == 'statefulset':
                obj = apps_v1.read_namespaced_stateful_set(workload_name, namespace)
                label_selector = ','.join(f'{k}={v}' for k, v in (obj.spec.selector.match_labels or {}).items())
            elif workload_type == 'daemonset':
                obj = apps_v1.read_namespaced_daemon_set(workload_name, namespace)
                label_selector = ','.join(f'{k}={v}' for k, v in (obj.spec.selector.match_labels or {}).items())
            elif workload_type == 'job':
                label_selector = f'job-name={workload_name}'
            elif workload_type == 'cronjob':
                job_list = batch_v1.list_namespaced_job(namespace)
                job_names = {
                    job.metadata.name
                    for job in job_list.items
                    if any(
                        ref.kind == 'CronJob' and ref.name == workload_name
                        for ref in (job.metadata.owner_references or [])
                    )
                }
                if not job_names:
                    return Response([])
                pod_items = v1.list_namespaced_pod(namespace).items
                pod_list_items = [
                    pod for pod in pod_items
                    if (pod.metadata.labels or {}).get('job-name') in job_names
                ]
            if workload_type != 'cronjob':
                pod_list_items = v1.list_namespaced_pod(namespace, label_selector=label_selector).items
            import datetime as _dt
            now = _dt.datetime.now(_dt.timezone.utc)
            pods = []
            for p in pod_list_items:
                age_delta = now - p.metadata.creation_timestamp.replace(tzinfo=_dt.timezone.utc)
                days = age_delta.days
                hours = age_delta.seconds // 3600
                age_str = f'{days}d' if days > 0 else f'{hours}h'
                restarts = sum(cs.restart_count for cs in (p.status.container_statuses or []))
                containers = [c.name for c in p.spec.containers]
                cpu_req = '0m'
                mem_req = '0Mi'
                if p.spec.containers:
                    res = p.spec.containers[0].resources
                    if res and res.requests:
                        cpu_req = res.requests.get('cpu', '0m')
                        mem_req = res.requests.get('memory', '0Mi')
                pods.append({
                    'name': p.metadata.name,
                    'namespace': p.metadata.namespace,
                    'status': p.status.phase,
                    'node': p.spec.node_name or '',
                    'pod_ip': p.status.pod_ip or '',
                    'host_ip': p.status.host_ip or '',
                    'containers': containers,
                    'restarts': restarts,
                    'cpu_request': cpu_req,
                    'memory_request': mem_req,
                    'age': age_str,
                    'created': p.metadata.creation_timestamp.isoformat(),
                })
            return Response(pods)
        except Exception as e:
            logger.warning('K8s workload pods degraded for cluster=%s workload=%s/%s: %s', cluster.id, workload_type, workload_name, e)
            return Response([])

    @action(detail=True, methods=['get'])
    def pod_logs(self, request, pk=None):
        cluster = self.get_object()
        pod_name = request.query_params.get('pod_name', '')
        namespace = request.query_params.get('namespace', 'default')
        container = request.query_params.get('container', '')
        if not pod_name:
            return Response({'detail': '请选择 Pod。'}, status=400)
        if request.query_params.get('paged') == '1':
            previous = request.query_params.get('previous') == 'true'
            scope = [str(request.user.pk), str(cluster.pk), namespace, pod_name, container, previous]

            def load_log_stream(tail_lines):
                if _is_demo(cluster):
                    from io import BytesIO
                    from urllib3.response import HTTPResponse
                    content = ''.join(f'2026-10-20T08:00:{index % 60:02d}.000000000Z [{index + 1:05d}] {pod_name}: 请求处理完成\n' for index in range(6000 - tail_lines if tail_lines else 0, 6000))
                    return HTTPResponse(body=BytesIO(content.encode('utf-8')), preload_content=False)
                kwargs = {
                    'name': pod_name, 'namespace': namespace, 'timestamps': False,
                    'previous': previous, '_preload_content': False,
                    '_request_timeout': (3, 20),
                }
                if container:
                    kwargs['container'] = container
                if tail_lines is not None:
                    kwargs['tail_lines'] = tail_lines
                return _get_k8s_client(cluster).CoreV1Api().read_namespaced_pod_log(**kwargs)

            try:
                return Response({**pod_log_page(request.query_params, scope, load_log_stream), 'container': container})
            except (LogSnapshotError, ValidationError):
                raise
            except Exception:
                logger.exception('K8s paged logs failed for cluster=%s pod=%s namespace=%s', cluster.pk, pod_name, namespace)
                return Response({'detail': '读取容器日志失败，请检查容器状态或切换“上次运行”。'}, status=502)
        try:
            tail_lines = max(1, min(int(request.query_params.get('tail_lines', 200)), 10000))
        except (TypeError, ValueError):
            return Response({'detail': '无效的日志行数。'}, status=400)

        if _is_demo(cluster):
            import datetime as _dt
            now = _dt.datetime.now(_dt.timezone.utc)
            lines = []
            for i in range(min(tail_lines, 50)):
                ts = (now - _dt.timedelta(minutes=50 - i)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
                if 'nginx' in pod_name:
                    msgs = [
                        f'{ts} 10.244.1.1 - - [GET /api/health HTTP/1.1] 200 15 "-" "kube-probe/1.29"',
                        f'{ts} 10.244.2.5 - - [GET / HTTP/1.1] 200 612 "-" "Mozilla/5.0"',
                        f'{ts} 10.244.1.8 - - [GET /static/css/main.css HTTP/1.1] 304 0',
                        f'{ts} 10.244.3.2 - - [POST /api/data HTTP/1.1] 201 89 "-" "curl/7.88"',
                    ]
                elif 'api' in pod_name:
                    msgs = [
                        f'{ts} INFO  [main] Application started on port 8080',
                        f'{ts} DEBUG [http] GET /api/users -> 200 (12ms)',
                        f'{ts} INFO  [db] Connection pool: active=5, idle=15, total=20',
                        f'{ts} WARN  [cache] Cache miss rate: 15.2%',
                    ]
                elif 'redis' in pod_name:
                    msgs = [
                        f'{ts} # Server initialized',
                        f'{ts} * Ready to accept connections tcp',
                        f'{ts} # 1 changes in 900 seconds. Saving...',
                        f'{ts} * Background saving started by pid 42',
                    ]
                elif 'mysql' in pod_name:
                    msgs = [
                        f'{ts} [Note] [MY-010131] [Server] mysqld: ready for connections. Version: 8.0.36',
                        f'{ts} [Note] [MY-012487] [InnoDB] DDL log recovery: begin',
                        f'{ts} [Note] [MY-012488] [InnoDB] DDL log recovery: end',
                        f"{ts} [Note] [MY-010747] [Server] Plugin 'mysql_native_password' is marked as deprecated",
                    ]
                else:
                    msgs = [
                        f'{ts} level=info msg="Starting process"',
                        f'{ts} level=info msg="Health check passed"',
                        f'{ts} level=debug msg="Processing request" duration=5ms',
                        f'{ts} level=info msg="Metrics collected" count=42',
                    ]
                lines.append(msgs[i % len(msgs)])
            return Response({'logs': '\n'.join(lines), 'container': container or 'main'})

        try:
            k8s = _get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            kwargs = {'name': pod_name, 'namespace': namespace, 'tail_lines': tail_lines}
            if container:
                kwargs['container'] = container
            log_content = v1.read_namespaced_pod_log(**kwargs)
            return Response({'logs': log_content, 'container': container or ''})
        except Exception as e:
            logger.warning('K8s pod logs degraded for cluster=%s pod=%s namespace=%s: %s', cluster.id, pod_name, namespace, e)
            return Response({'logs': '', 'container': container or '', 'degraded': True})

    @action(detail=True, methods=['get'])
    def resource_events(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.query_params.get('type', '')
        resource_name = request.query_params.get('name', '')
        namespace = request.query_params.get('namespace', 'default')

        if _is_demo(cluster):
            import datetime as _dt, random as _rand
            now = _dt.datetime.now(_dt.timezone.utc)
            events = []
            # Generate plausible events
            normal_events = [
                ('Scheduled', f'Successfully assigned {namespace}/{resource_name} to node-01'),
                ('Pulling', f'Pulling image for {resource_name}'),
                ('Pulled', f'Successfully pulled image'),
                ('Created', f'Created container for {resource_name}'),
                ('Started', f'Started container for {resource_name}'),
                ('ScalingReplicaSet', f'Scaled up replica set {resource_name}-7c5b4f9d8 to 2'),
            ]
            warning_events = [
                ('BackOff', f'Back-off restarting failed container in pod {resource_name}'),
                ('Unhealthy', f'Readiness probe failed: connection refused'),
                ('FailedScheduling', f'0/4 nodes are available: insufficient memory'),
            ]

            # Add 3-6 normal events
            for i, (reason, msg) in enumerate(normal_events[:_rand.randint(3, 5)]):
                t = (now - _dt.timedelta(hours=_rand.randint(1, 48))).isoformat()
                events.append({
                    'type': 'Normal',
                    'reason': reason,
                    'message': msg,
                    'first_time': t,
                    'last_time': t,
                    'count': 1,
                    'source': 'kubelet, node-01',
                })

            # Maybe add 1 warning for some resources
            if resource_name in ('web-frontend', 'debug-pod-manual') or 'pending' in resource_name.lower():
                warn = warning_events[_rand.randint(0, len(warning_events) - 1)]
                t = (now - _dt.timedelta(minutes=_rand.randint(5, 120))).isoformat()
                events.append({
                    'type': 'Warning',
                    'reason': warn[0],
                    'message': warn[1],
                    'first_time': t,
                    'last_time': t,
                    'count': _rand.randint(1, 8),
                    'source': 'kubelet, node-02',
                })

            # Sort by last_time desc
            events.sort(key=lambda e: e['last_time'], reverse=True)
            return Response(events)

        try:
            k8s = _get_k8s_client(cluster)
            v1 = k8s.CoreV1Api()
            kind_map = {
                'pod': 'Pod', 'node': 'Node', 'deployment': 'Deployment',
                'statefulset': 'StatefulSet', 'daemonset': 'DaemonSet',
                'job': 'Job', 'cronjob': 'CronJob', 'service': 'Service',
                'ingress': 'Ingress', 'pvc': 'PersistentVolumeClaim',
                'pv': 'PersistentVolume', 'configmap': 'ConfigMap', 'secret': 'Secret',
            }
            kind = kind_map.get(resource_type, resource_type)

            # Cluster-scoped resources (Node, PV)
            if resource_type in ('node', 'pv'):
                event_list = v1.list_event_for_all_namespaces(
                    field_selector=f'involvedObject.name={resource_name},involvedObject.kind={kind}'
                )
            else:
                event_list = v1.list_namespaced_event(
                    namespace,
                    field_selector=f'involvedObject.name={resource_name},involvedObject.kind={kind}'
                )
            events = []
            for e in event_list.items:
                events.append({
                    'type': e.type or 'Normal',
                    'reason': e.reason or '',
                    'message': e.message or '',
                    'first_time': e.first_timestamp.isoformat() if e.first_timestamp else '',
                    'last_time': e.last_timestamp.isoformat() if e.last_timestamp else '',
                    'count': e.count or 1,
                    'source': f'{e.source.component}, {e.source.host}' if e.source else '',
                })
            events.sort(key=lambda ev: ev['last_time'], reverse=True)
            return Response(events)
        except Exception as e:
            logger.warning('K8s resource events degraded for cluster=%s resource=%s/%s: %s', cluster.id, resource_type, resource_name, e)
            return Response([])
