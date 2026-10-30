"""Platform permissions are the ceiling; user cluster grants can only narrow them."""
from .models import K8sUserAccess


def get_k8s_grants(user):
    if not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False):
        return {}
    if user.is_superuser:
        return None
    policy = K8sUserAccess.objects.filter(user=user).first()
    if policy is None or policy.unrestricted:
        return None
    return {grant.cluster_id: grant for grant in policy.grants.all()}


def k8s_scope(user, cluster_id):
    grants = get_k8s_grants(user)
    if grants is None:
        return {'role': 'admin', 'namespaces': [], 'allow_exec': True}
    grant = grants.get(int(cluster_id))
    if grant is None:
        return None
    return {'role': grant.role, 'namespaces': grant.namespaces, 'allow_exec': grant.allow_exec}


def can_access_k8s(user, cluster_id, namespace=None, *, execute=False, shell=False):
    scope = k8s_scope(user, cluster_id)
    if scope is None:
        return False
    if shell:
        return scope['role'] == 'admin' and not scope['namespaces']
    if execute and (scope['role'] == 'viewer' or not scope['allow_exec']):
        return False
    return not scope['namespaces'] or namespace in scope['namespaces']


def validate_k8s_task_access(user, task_type, targets, payload=None):
    """Keep task-center execution from bypassing an explicit cluster policy."""
    from rest_framework.exceptions import PermissionDenied
    from .services import user_has_permissions
    payload = payload or {}
    is_exec = task_type == 'k8s_pod_exec'
    for target in targets:
        cluster_id = target.get('cluster_id')
        namespace = target.get('namespace') or payload.get('namespace') or 'default'
        scope = k8s_scope(user, cluster_id) if cluster_id else None
        if not scope or scope['role'] == 'viewer' or (scope['namespaces'] and namespace not in scope['namespaces']):
            raise PermissionDenied('任务目标不在用户的 K8s 运维授权范围内。')
        kind = (payload.get('resource_kind') or target.get('kind') or '').lower()
        command = str(payload.get('command') or '').strip()
        strategy = str(payload.get('deployment_strategy') or payload.get('strategy') or '').strip().lower()
        helm = strategy == 'helm' or command.lower().startswith('helm ')
        service_patch = kind == 'service' and bool(payload.get('patch'))
        # Match the executor's dispatch order: a Service without a patch uses
        # cluster commands, and Helm strategy values are case-insensitive.
        cluster_command = is_exec and (helm or (not service_patch and (
            not str(target.get('name') or '').strip() or command.startswith('kubectl')
            or kind not in ('', 'pod')
        )))
        if cluster_command and not helm:
            permission = 'ops.k8s.kubectl'
        else:
            permission = 'ops.k8s.exec' if is_exec and not cluster_command and not service_patch else 'ops.k8s.manage'
        if not user_has_permissions(user, [permission]):
            raise PermissionDenied('缺少任务所需的 K8s 平台权限。')
        if is_exec and not cluster_command and not service_patch and not scope['allow_exec']:
            raise PermissionDenied('未授权使用 Pod 命令执行。')
        if cluster_command and (scope['role'] != 'admin' or scope['namespaces']):
            raise PermissionDenied('集群命令任务需要完整集群管理员授权。')
