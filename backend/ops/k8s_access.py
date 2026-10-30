from rest_framework.exceptions import PermissionDenied

from rbac.k8s_access import get_k8s_grants, k8s_scope


class K8sAccessMixin:
    """Apply user scope to every cluster API, including legacy actions."""
    namespaced_lists = {'pods', 'services', 'deployments', 'statefulsets', 'daemonsets', 'jobs',
                        'cronjobs', 'ingresses', 'pvcs', 'configmaps', 'secrets', 'resources'}
    cluster_actions = {'nodes', 'capacity', 'pvs', 'storageclasses', 'update', 'partial_update', 'destroy',
                       'test_connection', 'kubectl', 'node_action'}
    secret_content_actions = {
        'resource_yaml', 'config_resource_detail', 'config_resource_preview', 'config_resource_update',
        'config_resource_revisions', 'config_resource_revision_preview', 'config_resource_rollback_preview',
        'config_resource_rollback', 'config_resource_rollback_to_revision',
    }

    def get_required_permissions(self):
        codes = super().get_required_permissions()
        if self.action in self.secret_content_actions:
            request = self.request
            data = request.query_params if request.method in {'GET', 'HEAD'} else request.data
            if hasattr(data, 'get') and str(data.get('type', '')).lower() == 'secret':
                codes = [*codes, 'ops.k8s.secret.view']
        return codes

    def get_queryset(self):
        queryset = super().get_queryset()
        grants = get_k8s_grants(self.request.user)
        return queryset if grants is None else queryset.filter(pk__in=grants)

    def get_object(self):
        cluster = super().get_object()
        scope = k8s_scope(self.request.user, cluster.pk)
        if not scope:
            raise PermissionDenied('未授权访问该集群。')
        self.k8s_access_scope = scope
        action = self.action
        data = self.request.query_params if self.request.method == 'GET' else self.request.data
        kind = str(data.get('type', '')).lower()
        cluster_resource = kind in {'node', 'namespace', 'pv', 'storageclass', 'ingressclass'} and action in {'resources', 'resource_yaml', 'resource_events', 'resource_delete'}
        own_namespace_yaml = action == 'resource_yaml' and kind == 'namespace' and data.get('name') in scope['namespaces']
        if action in self.cluster_actions or (cluster_resource and not own_namespace_yaml):
            if scope['namespaces'] or (action in {'update', 'partial_update', 'destroy', 'test_connection', 'kubectl', 'node_action'} and scope['role'] != 'admin'):
                raise PermissionDenied('此操作需要完整集群管理员权限。')
        if self.request.method not in {'GET', 'HEAD', 'OPTIONS'} and scope['role'] == 'viewer':
            raise PermissionDenied('当前集群角色为只读。')
        if action == 'pod_exec' and not scope['allow_exec']:
            raise PermissionDenied('未授权使用 Pod 终端。')
        if not own_namespace_yaml and not cluster_resource and action not in self.cluster_actions | {'retrieve', 'summary', 'namespaces', 'yaml_preview', 'yaml_apply'}:
            namespace = data.get('namespace', 'default')
            if scope['namespaces'] and namespace not in scope['namespaces']:
                if not (action in self.namespaced_lists and namespace == '_all'):
                    raise PermissionDenied('未授权访问该命名空间。')
        return cluster

    def finalize_response(self, request, response, *args, **kwargs):
        scope = getattr(self, 'k8s_access_scope', None)
        if scope and scope['namespaces'] and response.status_code < 300 and isinstance(response.data, list):
            if self.action == 'namespaces':
                response.data = [item for item in response.data if item.get('name') in scope['namespaces']]
            elif self.action in self.namespaced_lists:
                response.data = [item for item in response.data if item.get('namespace') in scope['namespaces']]
        return super().finalize_response(request, response, *args, **kwargs)
