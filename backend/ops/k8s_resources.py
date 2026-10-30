"""Typed resource operations inspired by KubePi's resource workbench."""
import copy
import difflib
import base64
import uuid
import yaml
from django.core.cache import cache
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from eventwall.services import record_event
from rbac.k8s_access import k8s_scope

# type: (kind, apiVersion, client, method suffix, demo collection)
RESOURCE_TYPES = {
    'pod': ('Pod', 'v1', 'CoreV1Api', 'pod', 'pods'),
    'namespace': ('Namespace', 'v1', 'CoreV1Api', 'namespace', 'namespaces'),
    'node': ('Node', 'v1', 'CoreV1Api', 'node', 'nodes'),
    'service': ('Service', 'v1', 'CoreV1Api', 'service', 'services'),
    'endpoints': ('Endpoints', 'v1', 'CoreV1Api', 'endpoints', 'endpoints'),
    'configmap': ('ConfigMap', 'v1', 'CoreV1Api', 'config_map', 'configmaps'),
    'secret': ('Secret', 'v1', 'CoreV1Api', 'secret', 'secrets'),
    'pv': ('PersistentVolume', 'v1', 'CoreV1Api', 'persistent_volume', 'pvs'),
    'pvc': ('PersistentVolumeClaim', 'v1', 'CoreV1Api', 'persistent_volume_claim', 'pvcs'),
    'deployment': ('Deployment', 'apps/v1', 'AppsV1Api', 'deployment', 'deployments'),
    'statefulset': ('StatefulSet', 'apps/v1', 'AppsV1Api', 'stateful_set', 'statefulsets'),
    'daemonset': ('DaemonSet', 'apps/v1', 'AppsV1Api', 'daemon_set', 'daemonsets'),
    'job': ('Job', 'batch/v1', 'BatchV1Api', 'job', 'jobs'),
    'cronjob': ('CronJob', 'batch/v1', 'BatchV1Api', 'cron_job', 'cronjobs'),
    'ingress': ('Ingress', 'networking.k8s.io/v1', 'NetworkingV1Api', 'ingress', 'ingresses'),
    'ingressclass': ('IngressClass', 'networking.k8s.io/v1', 'NetworkingV1Api', 'ingress_class', 'ingressclasses'),
    'networkpolicy': ('NetworkPolicy', 'networking.k8s.io/v1', 'NetworkingV1Api', 'network_policy', 'networkpolicies'),
    'storageclass': ('StorageClass', 'storage.k8s.io/v1', 'StorageV1Api', 'storage_class', 'storageclasses'),
    'hpa': ('HorizontalPodAutoscaler', 'autoscaling/v2', 'AutoscalingV2Api', 'horizontal_pod_autoscaler', 'hpas'),
    'resourcequota': ('ResourceQuota', 'v1', 'CoreV1Api', 'resource_quota', 'resourcequotas'),
    'limitrange': ('LimitRange', 'v1', 'CoreV1Api', 'limit_range', 'limitranges'),
}
CLUSTER_TYPES = {'node', 'namespace', 'pv', 'storageclass', 'ingressclass'}


def summarize_endpoints(subsets):
    return {
        'addresses': ', '.join(address['ip'] for subset in subsets for address in subset.get('addresses', []) or []),
        'not_ready_addresses': ', '.join(address['ip'] for subset in subsets for address in subset.get('notReadyAddresses', []) or []),
        'ports': ', '.join(dict.fromkeys(
            f"{port['port']}/{port.get('protocol') or 'TCP'}" for subset in subsets for port in subset.get('ports', []) or []
        )),
    }


def patch_demo_manifest(cluster_id, resource_type, namespace, name, patch):
    """Keep YAML-created demo resources consistent with dedicated editors."""
    from . import k8s_views as runtime
    manifests = runtime._get_demo_state(cluster_id, 'manifests', {})
    key = f'{resource_type}/{namespace}/{name}'
    if key not in manifests:
        return

    def merge(target, changes):
        for field, value in changes.items():
            if isinstance(value, dict) and isinstance(target.get(field), dict):
                merge(target[field], value)
            else:
                target[field] = copy.deepcopy(value)

    merge(manifests[key], patch)
    manifests[key]['metadata']['resourceVersion'] = uuid.uuid4().hex
    runtime._set_demo_state(cluster_id, 'manifests', manifests)


def clean_manifest(value):
    value = copy.deepcopy(value)
    value.pop('status', None)
    metadata = value.setdefault('metadata', {})
    for key in ('managedFields', 'creationTimestamp', 'uid', 'generation', 'selfLink'):
        metadata.pop(key, None)
    annotations = metadata.get('annotations') or {}
    annotations.pop('kubectl.kubernetes.io/last-applied-configuration', None)
    return value


class K8sResourceMixin:
    def _resource_context(self, cluster, resource_type, namespace, *, write=False, name=''):
        if resource_type not in RESOURCE_TYPES:
            raise ValidationError('不支持的资源类型。')
        scope = k8s_scope(self.request.user, cluster.pk)
        if not scope:
            raise PermissionDenied('未授权访问该集群。')
        if resource_type == 'secret' and self.action != 'resource_delete':
            from rbac.services import user_has_permissions
            if not user_has_permissions(self.request.user, ['ops.k8s.secret.view']):
                raise PermissionDenied('查看或预览 Secret 内容需要 ops.k8s.secret.view 权限。')
        if write and scope['role'] == 'viewer':
            raise PermissionDenied('当前集群角色为只读。')
        if resource_type in CLUSTER_TYPES:
            own_namespace = resource_type == 'namespace' and not write and name in scope['namespaces']
            if (scope['namespaces'] and not own_namespace) or (write and scope['role'] != 'admin'):
                raise PermissionDenied('集群级资源需要完整集群授权。')
            namespace = ''
        elif namespace in ('', '_all'):
            raise ValidationError('请选择具体命名空间。')
        elif scope['namespaces'] and namespace not in scope['namespaces']:
            raise PermissionDenied('未授权访问该命名空间。')
        return namespace

    def _resource_call(self, cluster, resource_type, verb, namespace='', name='', **kwargs):
        from .k8s_views import _get_k8s_client
        info = RESOURCE_TYPES[resource_type]
        api = getattr(_get_k8s_client(cluster), info[2])()
        method = f'{verb}_{"namespaced_" if resource_type not in CLUSTER_TYPES else ""}{info[3]}'
        if namespace:
            kwargs['namespace'] = namespace
        if name:
            kwargs['name'] = name
        return getattr(api, method)(**kwargs)

    def _demo_items(self, cluster, resource_type):
        from . import k8s_views as runtime
        collection = RESOURCE_TYPES[resource_type][4]
        samples = {
            'endpoints': [{'name': 'api-server', 'namespace': 'production', 'subsets': [{'addresses': [{'ip': '10.244.1.10'}], 'ports': [{'port': 8080, 'protocol': 'TCP'}]}]}],
            'ingressclass': [{'name': 'nginx', 'spec': {'controller': 'k8s.io/ingress-nginx'}, 'is_default': True}],
            'hpa': [{'name': 'api-autoscaler', 'namespace': 'production', 'spec': {'minReplicas': 2, 'maxReplicas': 8, 'scaleTargetRef': {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'name': 'api-server'}}}],
            'networkpolicy': [{'name': 'allow-web', 'namespace': 'production', 'spec': {'podSelector': {'matchLabels': {'app': 'nginx'}}, 'policyTypes': ['Ingress'], 'ingress': [{'ports': [{'port': 80, 'protocol': 'TCP'}]}]}}],
            'resourcequota': [{'name': 'production-quota', 'namespace': 'production', 'spec': {'hard': {'requests.cpu': '8', 'requests.memory': '16Gi', 'pods': '50'}}}],
            'limitrange': [{'name': 'container-defaults', 'namespace': 'production', 'spec': {'limits': [{'type': 'Container', 'default': {'cpu': '500m', 'memory': '512Mi'}}]}}],
        }
        default = getattr(runtime, f'DEMO_{collection.upper()}', samples.get(resource_type, []))
        return runtime._get_demo_state(cluster.pk, collection, default)

    def _read_manifest(self, cluster, resource_type, name, namespace):
        from . import k8s_views as runtime
        if runtime._is_demo(cluster):
            manifests = runtime._get_demo_state(cluster.pk, 'manifests', {})
            key = f'{resource_type}/{namespace}/{name}'
            if key in manifests:
                return copy.deepcopy(manifests[key])
            items = self._demo_items(cluster, resource_type)
            if not any(item['name'] == name and (not namespace or item.get('namespace') == namespace) for item in items):
                return None
            if resource_type in {'hpa', 'networkpolicy', 'resourcequota', 'limitrange', 'endpoints', 'ingressclass'}:
                item = next(item for item in items if item['name'] == name and (not namespace or item.get('namespace') == namespace))
                info = RESOURCE_TYPES[resource_type]
                metadata = {'name': name}
                if namespace:
                    metadata['namespace'] = namespace
                if resource_type == 'ingressclass' and item.get('is_default'):
                    metadata['annotations'] = {'ingressclass.kubernetes.io/is-default-class': 'true'}
                field = 'subsets' if resource_type == 'endpoints' else 'spec'
                return {'apiVersion': info[1], 'kind': info[0], 'metadata': metadata, field: item.get(field, [] if field == 'subsets' else {})}
            return yaml.safe_load(self._build_demo_yaml(resource_type, name, namespace, items))
        try:
            obj = self._resource_call(cluster, resource_type, 'read', namespace, name)
            return runtime._get_k8s_client(cluster).ApiClient().sanitize_for_serialization(obj)
        except Exception as exc:
            if getattr(exc, 'status', None) == 404:
                return None
            raise

    def _yaml_operation(self, request, cluster, *, apply=False):
        from . import k8s_views as runtime
        content = request.data.get('yaml', '')
        if not isinstance(content, str) or len(content.encode('utf-8')) > 1024 * 1024:
            raise ValidationError('YAML 不能超过 1 MB。')
        try:
            doc = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise ValidationError('YAML 格式无效，请检查缩进和文档数量。') from exc
        if not isinstance(doc, dict) or not isinstance(doc.get('metadata'), dict):
            raise ValidationError('请提供单个资源，包含 apiVersion、kind 和 metadata.name。')
        resource_type = next((key for key, info in RESOURCE_TYPES.items() if info[:2] == (doc.get('kind'), doc.get('apiVersion'))), None)
        if not resource_type:
            raise ValidationError('不支持此 kind / apiVersion。')
        name = doc['metadata'].get('name')
        if not isinstance(name, str) or not name or '/' in name or len(name) > 253:
            raise ValidationError('metadata.name 无效。')
        namespace = doc['metadata'].get('namespace') or request.data.get('namespace', 'default')
        namespace = self._resource_context(cluster, resource_type, namespace, write=True)
        doc = clean_manifest(doc)
        if namespace:
            doc['metadata']['namespace'] = namespace
        else:
            doc['metadata'].pop('namespace', None)
        current = self._read_manifest(cluster, resource_type, name, namespace)
        current_version = str((current or {}).get('metadata', {}).get('resourceVersion', ''))
        edited_version = doc['metadata'].get('resourceVersion')
        if current and edited_version and str(edited_version) != current_version:
            error = APIException('资源版本已变化，请重新加载 YAML。')
            error.status_code = 409
            raise error
        if apply and 'expected_version' in request.data:
            expected = request.data['expected_version']
            actual = current_version if current else None
            if expected != actual:
                error = APIException('资源已变化，请重新预检后再应用。')
                error.status_code = 409
                raise error
        # Resource versions from editors are retained, so stale edits fail with 409.
        if current and not doc['metadata'].get('resourceVersion'):
            doc['metadata']['resourceVersion'] = current.get('metadata', {}).get('resourceVersion')
        before = yaml.safe_dump(clean_manifest(current), sort_keys=False, allow_unicode=True) if current else ''
        after = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
        if not runtime._is_demo(cluster):
            self._resource_call(cluster, resource_type, 'replace' if current else 'create', namespace,
                                name if current else '', body=doc, **({} if apply else {'dry_run': 'All'}))
        elif apply:
            manifests = runtime._get_demo_state(cluster.pk, 'manifests', {})
            doc['metadata']['resourceVersion'] = uuid.uuid4().hex
            manifests[f'{resource_type}/{namespace}/{name}'] = doc
            runtime._set_demo_state(cluster.pk, 'manifests', manifests)
            items = self._demo_items(cluster, resource_type)
            item = next((item for item in items if item['name'] == name and (not namespace or item.get('namespace') == namespace)), None)
            if item is None:
                item = {'name': name, 'namespace': namespace, 'created': timezone.now().isoformat(), 'status': 'Active' if resource_type == 'namespace' else 'Pending'}
                items.append(item)
            spec = doc.get('spec') or {}
            item['spec'] = spec
            item.update({'labels': doc['metadata'].get('labels', {}), 'replicas': spec.get('replicas', item.get('replicas', 0))})
            if resource_type == 'cronjob':
                item['schedule'] = spec.get('schedule', '')
                item['suspend'] = spec.get('suspend', False)
            elif resource_type == 'node':
                item['unschedulable'] = spec.get('unschedulable', False)
            elif resource_type == 'service':
                item['type'] = spec.get('type', 'ClusterIP')
                item['cluster_ip'] = spec.get('clusterIP', '')
                item['ports'] = ', '.join(f"{port.get('port')}/{port.get('protocol', 'TCP')}" for port in spec.get('ports', []))
            elif resource_type == 'endpoints':
                item['subsets'] = doc.get('subsets') or []
            elif resource_type == 'ingressclass':
                item['is_default'] = (doc['metadata'].get('annotations') or {}).get('ingressclass.kubernetes.io/is-default-class') == 'true'
            containers = spec.get('template', {}).get('spec', {}).get('containers', spec.get('containers', []))
            if containers:
                item['containers'] = containers
                item['images'] = ', '.join(container.get('image', '') for container in containers)
            if resource_type in {'configmap', 'secret'}:
                item['data'] = doc.get('data', {})
                if resource_type == 'secret':
                    item['data_payload'] = {key: base64.b64decode(value).decode('utf-8') for key, value in item['data'].items()}
                    item['data_payload'].update(doc.get('stringData', {}))
                    item['type'] = doc.get('type', 'Opaque')
                else:
                    item['data_payload'] = {key: str(value) for key, value in item['data'].items()}
                item['data_count'] = len(item['data_payload'])
                item['keys'] = list(item['data_payload'])
            runtime._set_demo_state(cluster.pk, RESOURCE_TYPES[resource_type][4], items)
        if apply:
            runtime._invalidate_cluster_runtime_cache(cluster)
            self._resource_audit(cluster, 'yaml_apply', resource_type, name, namespace)
        return {'success': True, 'operation': 'update' if current else 'create', 'kind': doc['kind'], 'name': name,
                'resource_version': current_version if current else None,
                'namespace': namespace, 'diff': ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='当前', tofile='变更后')) if not apply else ''}

    def _resource_audit(self, cluster, operation, resource_type, name, namespace):
        record_event(request=self.request, module='ops', category='operation', action=operation,
                     title='K8s 资源操作', summary=f'{cluster.name}: {operation} {resource_type}/{name}',
                     resource_type='k8s_resource', resource_id=cluster.pk, resource_name=name,
                     metadata={'namespace': namespace, 'type': resource_type})

    @action(detail=True, methods=['post'])
    def yaml_preview(self, request, pk=None):
        cluster = self.get_object()
        try:
            return Response(self._yaml_operation(request, cluster))
        except APIException:
            raise
        except Exception as exc:
            return Response({'detail': f'资源预检失败: {exc}'}, status=400)

    @action(detail=True, methods=['post'])
    def yaml_apply(self, request, pk=None):
        cluster = self.get_object()
        try:
            return Response(self._yaml_operation(request, cluster, apply=True))
        except APIException:
            raise
        except Exception as exc:
            return Response({'detail': f'应用资源失败: {exc}'}, status=409 if getattr(exc, 'status', None) == 409 else 400)

    @action(detail=True, methods=['post'])
    def resource_delete(self, request, pk=None):
        from . import k8s_views as runtime
        cluster = self.get_object()
        resource_type, name = request.data.get('type'), request.data.get('name')
        namespace = self._resource_context(cluster, resource_type, request.data.get('namespace', 'default'), write=True)
        if resource_type == 'node' or not name:
            raise ValidationError('不支持删除节点，或未提供资源名称。')
        if resource_type == 'namespace' and name in {'default', 'kube-system', 'kube-public', 'kube-node-lease'}:
            raise ValidationError('不能删除 Kubernetes 系统命名空间。')
        try:
            if runtime._is_demo(cluster):
                items = self._demo_items(cluster, resource_type)
                remaining = [item for item in items if not (item['name'] == name and (not namespace or item.get('namespace') == namespace))]
                if len(items) == len(remaining):
                    return Response({'detail': '资源不存在。'}, status=404)
                runtime._set_demo_state(cluster.pk, RESOURCE_TYPES[resource_type][4], remaining)
                manifests = runtime._get_demo_state(cluster.pk, 'manifests', {})
                manifests.pop(f'{resource_type}/{namespace}/{name}', None)
                runtime._set_demo_state(cluster.pk, 'manifests', manifests)
            else:
                self._resource_call(cluster, resource_type, 'delete', namespace, name, body={'propagationPolicy': 'Background'})
            runtime._invalidate_cluster_runtime_cache(cluster)
            self._resource_audit(cluster, 'delete', resource_type, name, namespace)
            return Response({'success': True})
        except Exception as exc:
            return Response({'detail': f'删除失败: {exc}'}, status=400)

    @action(detail=True, methods=['post'])
    def workload_action(self, request, pk=None):
        from . import k8s_views as runtime
        cluster = self.get_object()
        resource_type, name, operation = request.data.get('type'), request.data.get('name'), request.data.get('operation')
        namespace = self._resource_context(cluster, resource_type, request.data.get('namespace', 'default'), write=True)
        if operation == 'restart' and resource_type in {'deployment', 'statefulset', 'daemonset'}:
            patch = {'spec': {'template': {'metadata': {'annotations': {'kubectl.kubernetes.io/restartedAt': timezone.now().isoformat()}}}}}
        elif operation in {'suspend', 'resume'} and resource_type == 'cronjob':
            patch = {'spec': {'suspend': operation == 'suspend'}}
        else:
            raise ValidationError('不支持的工作负载操作。')
        if not name:
            raise ValidationError('资源名称不能为空。')
        try:
            if runtime._is_demo(cluster):
                items = self._demo_items(cluster, resource_type)
                item = next((item for item in items if item['name'] == name and item.get('namespace') == namespace), None)
                if item is None:
                    return Response({'detail': '资源不存在。'}, status=404)
                item['suspend' if resource_type == 'cronjob' else 'restarted_at'] = patch['spec'].get('suspend', timezone.now().isoformat())
                runtime._set_demo_state(cluster.pk, RESOURCE_TYPES[resource_type][4], items)
                patch_demo_manifest(cluster.pk, resource_type, namespace, name, patch)
            else:
                self._resource_call(cluster, resource_type, 'patch', namespace, name, body=patch)
            runtime._invalidate_cluster_runtime_cache(cluster)
            self._resource_audit(cluster, operation, resource_type, name, namespace)
            return Response({'success': True})
        except Exception as exc:
            return Response({'detail': f'操作失败: {exc}'}, status=400)

    @action(detail=True, methods=['post'])
    def node_action(self, request, pk=None):
        from . import k8s_views as runtime
        cluster = self.get_object()
        name, operation = request.data.get('name'), request.data.get('operation')
        if not name or operation not in {'cordon', 'uncordon'}:
            raise ValidationError('请选择节点和调度操作。')
        try:
            if runtime._is_demo(cluster):
                items = self._demo_items(cluster, 'node')
                item = next((item for item in items if item['name'] == name), None)
                if item is None:
                    return Response({'detail': '节点不存在。'}, status=404)
                item['unschedulable'] = operation == 'cordon'
                runtime._set_demo_state(cluster.pk, 'nodes', items)
                patch_demo_manifest(cluster.pk, 'node', '', name, {'spec': {'unschedulable': item['unschedulable']}})
            else:
                self._resource_call(cluster, 'node', 'patch', name=name, body={'spec': {'unschedulable': operation == 'cordon'}})
            runtime._invalidate_cluster_runtime_cache(cluster)
            self._resource_audit(cluster, operation, 'node', name, '')
            return Response({'success': True})
        except Exception as exc:
            return Response({'detail': f'操作失败: {exc}'}, status=400)

    @action(detail=True, methods=['get'])
    def resources(self, request, pk=None):
        from . import k8s_views as runtime
        cluster = self.get_object()
        resource_type = request.query_params.get('type')
        if resource_type not in {'hpa', 'networkpolicy', 'resourcequota', 'limitrange', 'endpoints', 'ingressclass'}:
            raise ValidationError('不支持的资源类型。')
        namespace = request.query_params.get('namespace', 'default')
        if resource_type in CLUSTER_TYPES:
            namespace = self._resource_context(cluster, resource_type, namespace)
        try:
            if runtime._is_demo(cluster):
                items = self._demo_items(cluster, resource_type)
                if resource_type == 'endpoints':
                    items = [{**item, **summarize_endpoints(item.get('subsets') or [])} for item in items]
                return Response(items if resource_type in CLUSTER_TYPES else runtime._filter_by_ns(items, namespace))
            cache_key = runtime._resource_cache_key(cluster.pk, resource_type, namespace)
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached)
            info = RESOURCE_TYPES[resource_type]
            client_module = runtime._get_k8s_client(cluster)
            client = client_module.ApiClient()
            try:
                api = getattr(client_module, info[2])()
                if resource_type in CLUSTER_TYPES:
                    result = getattr(api, f'list_{info[3]}')()
                elif namespace == '_all':
                    result = getattr(api, f'list_{info[3]}_for_all_namespaces')()
                else:
                    result = getattr(api, f'list_namespaced_{info[3]}')(namespace=namespace)
                rows = []
                for item in result.items:
                    document = client.sanitize_for_serialization(item)
                    metadata = document['metadata']
                    row = {'name': metadata['name'], 'namespace': metadata.get('namespace') or '',
                           'created': metadata.get('creationTimestamp') or ''}
                    if resource_type == 'endpoints':
                        row.update(summarize_endpoints(document.get('subsets') or []))
                    else:
                        row['spec'] = document.get('spec') or {}
                    if resource_type == 'ingressclass':
                        row['is_default'] = (metadata.get('annotations') or {}).get('ingressclass.kubernetes.io/is-default-class') == 'true'
                    rows.append(row)
            finally:
                client.close()
            cache.set(cache_key, rows, runtime.K8S_RESOURCE_CACHE_TTL)
            return Response(rows)
        except Exception as exc:
            return Response({'detail': f'获取资源失败: {exc}'}, status=400)
