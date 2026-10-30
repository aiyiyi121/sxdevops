"""Authorization boundaries for delegated identity administration."""
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db.models import Q
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import PermissionDefinition, Role
from .services import get_user_effective_permissions


def assigned_permission_codes(user):
    # Include disabled users: disabling an account must not bypass its protection.
    return set(PermissionDefinition.objects.filter(
        Q(roles__users=user) | Q(roles__user_groups__users=user),
    ).values_list('code', flat=True))


def require_delegable_permissions(actor, codes):
    codes = set(codes)
    if actor and actor.is_active and actor.is_superuser:
        return
    if not actor or not actor.is_active or not codes.issubset(get_user_effective_permissions(actor)):
        raise PermissionDenied('不能管理或授予超出本人权限范围的授权。')
    from .k8s_access import get_k8s_grants
    if any(code.startswith('ops.k8s.') for code in codes) and get_k8s_grants(actor) is not None:
        raise PermissionDenied('受集群范围限制的管理员不能转授 K8s 平台权限，请联系超级管理员。')


def require_manageable_user(actor, target):
    if actor and actor.is_active and actor.is_superuser:
        return
    if target.is_superuser or target.is_staff:
        raise PermissionDenied('只有超级管理员可以管理系统管理员账号。')
    require_delegable_permissions(actor, assigned_permission_codes(target))
    from .k8s_access import get_k8s_grants
    actor_grants = get_k8s_grants(actor) if actor else {}
    if actor_grants is not None:
        require_k8s_subset(actor_grants, get_k8s_grants(target))


def role_permission_codes(roles):
    return set(PermissionDefinition.objects.filter(roles__in=roles).values_list('code', flat=True))


def group_permission_codes(groups):
    return role_permission_codes(Role.objects.filter(user_groups__in=groups))


def require_manageable_role(actor, role):
    require_delegable_permissions(actor, role.permissions.values_list('code', flat=True))
    from django.contrib.auth import get_user_model
    targets = get_user_model().objects.filter(
        Q(rbac_roles=role) | Q(rbac_groups__roles=role),
    ).distinct()
    for target in targets:
        require_manageable_user(actor, target)


def require_k8s_subset(ceiling, grants):
    if ceiling is None:
        return
    if grants is None:
        raise PermissionDenied('不能将集群访问范围扩展到本人授权范围之外。')
    rank = {'viewer': 0, 'operator': 1, 'admin': 2}
    for cluster_id, grant in grants.items():
        allowed = ceiling.get(cluster_id)
        if (not allowed or rank[grant.role] > rank[allowed.role]
                or (grant.allow_exec and not allowed.allow_exec)
                or (allowed.namespaces and (
                    not grant.namespaces or not set(grant.namespaces).issubset(allowed.namespaces)
                ))):
            raise PermissionDenied('不能将集群访问范围扩展到本人授权范围之外。')


def revoke_user_credentials(user):
    Token.objects.filter(user=user).delete()
    store = SessionStore()
    keys = [session.pk for session in Session.objects.only('session_key', 'session_data').iterator()
            if str(store.decode(session.session_data).get(SESSION_KEY)) == str(user.pk)]
    Session.objects.filter(pk__in=keys).delete()


def require_safe_account_removal(actor, target):
    require_manageable_user(actor, target)
    if actor.pk == target.pk:
        raise ValidationError('不能删除或停用当前登录账号。')
    if target.is_superuser and target.is_active:
        active_admins = list(type(target).objects.select_for_update().filter(is_superuser=True, is_active=True))
        if len(active_admins) <= 1:
            raise ValidationError('必须保留至少一个启用的超级管理员。')
