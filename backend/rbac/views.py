from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import PermissionDenied
from types import SimpleNamespace
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from eventwall.mixins import EventWallModelViewSetMixin
from eventwall.models import EventRecord
from eventwall.services import record_event

from .models import K8sUserAccess, PermissionDefinition, Role, SystemModuleSetting, UserGroup
from .permissions import RBACPermissionMixin, build_rbac_permission
from .serializers import (
    LoginSerializer,
    K8sClusterGrantSerializer,
    K8sUserAccessSerializer,
    PermissionDefinitionSerializer,
    RoleSerializer,
    SystemModuleSettingUpdateSerializer,
    UserGroupSerializer,
    UserSerializer,
)
from .services import (
    DEFAULT_SYSTEM_MODULE_CODE,
    SYSTEM_MODULE_CATALOG,
    SYSTEM_MODULE_PATHS,
    ensure_builtin_rbac,
    ensure_system_module_settings,
    get_system_module_settings,
    user_has_permissions,
    get_user_effective_permissions,
)
from .security import (
    group_permission_codes, require_delegable_permissions, require_manageable_role, require_manageable_user,
    require_k8s_subset, require_safe_account_removal, revoke_user_credentials,
)
from .throttles import LoginAccountThrottle, LoginIPThrottle


User = get_user_model()


class IdentityWriteMixin:
    """Keep validation, relation updates, credential revocation and audit atomic."""

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        self.authorization_before = self.authorization_snapshot(self.get_object())
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        self.authorization_before = self.authorization_snapshot(self.get_object())
        return super().destroy(request, *args, **kwargs)

    def authorization_snapshot(self, instance):
        if isinstance(instance, User):
            return {'role_ids': list(instance.rbac_roles.values_list('id', flat=True)),
                    'group_ids': list(instance.rbac_groups.values_list('id', flat=True))}
        if isinstance(instance, Role):
            return {'permission_ids': list(instance.permissions.values_list('id', flat=True))}
        return {'role_ids': list(instance.roles.values_list('id', flat=True)),
                'user_ids': list(instance.users.values_list('id', flat=True))}

    def eventwall_metadata(self, instance, action, before=None, after=None):
        return {'authorization_before': getattr(self, 'authorization_before', None),
                'authorization_after': None if action == 'delete' else self.authorization_snapshot(instance)}

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.method in {'PUT', 'PATCH', 'DELETE', 'POST'} and self.kwargs.get('pk'):
            queryset = queryset.select_for_update()
        return queryset


class UserPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class UserViewSet(IdentityWriteMixin, EventWallModelViewSetMixin, RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = User.objects.prefetch_related('rbac_roles__permissions', 'rbac_groups__roles__permissions').all().order_by('-date_joined', '-id')
    pagination_class = UserPagination
    serializer_class = UserSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']
    event_module = 'rbac'
    event_resource_type = 'rbac_user'
    event_resource_label = '用户'
    event_resource_name_fields = ('username',)
    event_exclude_fields = ('password',)
    rbac_permissions = {
        'list': ['rbac.user.view'],
        'retrieve': ['rbac.user.view'],
        'create': ['rbac.user.manage'],
        'update': ['rbac.user.manage'],
        'partial_update': ['rbac.user.manage'],
        'destroy': ['rbac.user.manage'],
        'reset_password': ['rbac.user.manage'],
        'k8s_access': ['rbac.user.manage'],
        'options': ['rbac.group.manage'],
    }

    @action(detail=False, methods=['get'])
    def options(self, request):
        candidates = self.filter_queryset(self.get_queryset())
        ids = []
        for user in candidates:
            try:
                require_manageable_user(request.user, user)
            except PermissionDenied:
                continue
            ids.append(user.pk)
        page = self.paginate_queryset(User.objects.filter(pk__in=ids).order_by('username', 'id'))
        return self.get_paginated_response([{'id': user.id, 'username': user.username} for user in page])

    def perform_destroy(self, instance):
        require_safe_account_removal(self.request.user, instance)
        revoke_user_credentials(instance)
        super().perform_destroy(instance)

    @action(detail=True, methods=['get', 'put'], url_path='k8s-access')
    @transaction.atomic
    def k8s_access(self, request, pk=None):
        user = self.get_object()
        require_manageable_user(request.user, user)
        if request.method == 'PUT':
            if user.is_superuser:
                raise ValidationError('超级管理员拥有全部集群权限，无需配置范围。')
            serializer = K8sUserAccessSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            from .k8s_access import get_k8s_grants
            proposed = None if data['unrestricted'] else {
                grant['cluster'].pk: SimpleNamespace(role=grant['role'], namespaces=grant['namespaces'],
                                                   allow_exec=grant.get('allow_exec', False))
                for grant in data['grants']
            }
            require_k8s_subset(get_k8s_grants(request.user), proposed)
            with transaction.atomic():
                User.objects.select_for_update().get(pk=user.pk)
                policy, _ = K8sUserAccess.objects.update_or_create(user=user, defaults={'unrestricted': data['unrestricted']})
                policy.grants.all().delete()
                for grant in data['grants']:
                    policy.grants.create(**grant)
                record_event(request=request, module='rbac', category='security', action='k8s_access',
                             title='配置用户 K8s 权限', summary=f'更新 {user.username} 的集群访问范围',
                             resource_type='rbac_user', resource_id=user.id, resource_name=user.username,
                             metadata={'unrestricted': policy.unrestricted, 'cluster_count': len(data['grants'])})
        policy = K8sUserAccess.objects.filter(user=user).first()
        from ops.models import K8sCluster
        from .k8s_access import get_k8s_grants
        actor_grants = get_k8s_grants(request.user)
        clusters = K8sCluster.objects.all()
        if actor_grants is not None:
            clusters = clusters.filter(pk__in=actor_grants)
        return Response({
            'unrestricted': policy.unrestricted if policy else True,
            'grants': K8sClusterGrantSerializer(policy.grants.all(), many=True).data if policy else [],
            'clusters': list(clusters.values('id', 'name')),
        })

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reset_password(self, request, pk=None):
        user = self.get_object()
        require_manageable_user(request.user, user)
        if not isinstance(request.data, dict):
            raise ValidationError({'password': '请提供包含新密码的对象。'})
        password = request.data.get('password', '')
        serializer = self.get_serializer(instance=user, data={'password': password}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record_event(
            request=request,
            module='rbac',
            category='security',
            action='reset_password',
            title='重置用户密码',
            summary=f'已重置用户 {user.username} 的密码',
            resource_type='rbac_user',
            resource_id=user.id,
            resource_name=user.username,
            severity=EventRecord.SEVERITY_WARNING,
            correlation_id=f'rbac-user:{user.id}',
            metadata={'target_user': user.username},
        )
        return Response({'success': True, 'message': f'已重置 {user.username} 的密码。'})


class RoleViewSet(IdentityWriteMixin, EventWallModelViewSetMixin, RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = Role.objects.prefetch_related('permissions').all().order_by('name')
    serializer_class = RoleSerializer
    pagination_class = None
    filter_backends = [filters.SearchFilter]
    search_fields = ['code', 'name', 'description']
    event_module = 'rbac'
    event_resource_type = 'rbac_role'
    event_resource_label = '角色'
    event_resource_name_fields = ('name', 'code')
    rbac_permissions = {
        'list': ['rbac.role.view'],
        'retrieve': ['rbac.role.view'],
        'create': ['rbac.role.manage'],
        'update': ['rbac.role.manage'],
        'partial_update': ['rbac.role.manage'],
        'destroy': ['rbac.role.manage'],
    }

    def perform_destroy(self, instance):
        if instance.is_builtin:
            raise ValidationError('内置角色不允许删除。')
        require_manageable_role(self.request.user, instance)
        super().perform_destroy(instance)


class UserGroupViewSet(IdentityWriteMixin, EventWallModelViewSetMixin, RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = UserGroup.objects.prefetch_related('roles', 'users').all().order_by('name')
    serializer_class = UserGroupSerializer
    pagination_class = None
    filter_backends = [filters.SearchFilter]
    search_fields = ['code', 'name', 'description']
    event_module = 'rbac'
    event_resource_type = 'rbac_group'
    event_resource_label = '用户组'
    event_resource_name_fields = ('name', 'code')
    rbac_permissions = {
        'list': ['rbac.group.view'],
        'retrieve': ['rbac.group.view'],
        'create': ['rbac.group.manage'],
        'update': ['rbac.group.manage'],
        'partial_update': ['rbac.group.manage'],
        'destroy': ['rbac.group.manage'],
    }

    def perform_destroy(self, instance):
        if instance.is_builtin:
            raise ValidationError('内置用户组不允许删除。')
        require_delegable_permissions(self.request.user, group_permission_codes([instance]))
        for user in instance.users.all():
            require_manageable_user(self.request.user, user)
        super().perform_destroy(instance)


class PermissionDefinitionViewSet(RBACPermissionMixin, viewsets.ReadOnlyModelViewSet):
    queryset = PermissionDefinition.objects.all().order_by('sort_order', 'code')
    serializer_class = PermissionDefinitionSerializer
    pagination_class = None
    filter_backends = [filters.SearchFilter]
    search_fields = ['code', 'name', 'description', 'category']
    rbac_permissions = {
        'list': ['rbac.permission.view'],
        'retrieve': ['rbac.permission.view'],
    }


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def system_module_settings_view(request):
    ensure_system_module_settings()

    if request.method == 'GET':
        return Response(get_system_module_settings())

    if not user_has_permissions(request.user, ['rbac.module.manage']):
        return Response({'detail': '当前用户没有执行此操作的权限。'}, status=status.HTTP_403_FORBIDDEN)

    request_payload = request.data if isinstance(request.data, dict) else request.data
    payload = request_payload.get('modules', request_payload) if isinstance(request_payload, dict) else request_payload
    if not isinstance(payload, list):
        return Response({'detail': '模块配置必须是列表。'}, status=status.HTTP_400_BAD_REQUEST)

    default_code = request_payload.get('default_code') if isinstance(request_payload, dict) else None
    if default_code is not None:
        default_code = str(default_code).strip() or DEFAULT_SYSTEM_MODULE_CODE
        if default_code not in SYSTEM_MODULE_PATHS:
            return Response({'detail': '请选择有效的登录默认页面。'}, status=status.HTTP_400_BAD_REQUEST)

    serializer = SystemModuleSettingUpdateSerializer(data=payload, many=True)
    serializer.is_valid(raise_exception=True)
    updates = {item['code']: item for item in serializer.validated_data}
    setting_map = {item.code: item for item in SystemModuleSetting.objects.all()}
    catalog_map = {item['code']: item for item in SYSTEM_MODULE_CATALOG}
    updated_items = []
    for item in get_system_module_settings():
        code = item['code']
        setting = setting_map.get(code)
        if not setting:
            continue
        if item['required']:
            setting.enabled = True
        elif 'enabled' in updates.get(code, {}):
            setting.enabled = updates[code]['enabled']
        if 'sort_order' in updates.get(code, {}):
            setting.sort_order = updates[code]['sort_order']
        setting.updated_by = request.user.username
        setting.save(update_fields=['enabled', 'sort_order', 'updated_by', 'updated_at'])
        updated_items.append({
            **item,
            'enabled': setting.enabled,
            'updated_by': setting.updated_by,
            'updated_at': setting.updated_at,
        })

    if default_code is not None:
        default_setting = setting_map.get(default_code)
        default_meta = catalog_map.get(default_code, {})
        parent_setting = setting_map.get(default_meta.get('parent_code'))
        if default_code != DEFAULT_SYSTEM_MODULE_CODE and (
            default_setting is None
            or not default_setting.enabled
            or (parent_setting is not None and not parent_setting.enabled)
        ):
            default_code = DEFAULT_SYSTEM_MODULE_CODE

        SystemModuleSetting.objects.filter(is_default=True).update(is_default=False)
        if default_code != DEFAULT_SYSTEM_MODULE_CODE:
            default_setting = setting_map[default_code]
            default_setting.is_default = True
            default_setting.updated_by = request.user.username
            default_setting.save(update_fields=['is_default', 'updated_by', 'updated_at'])

    record_event(
        request=request,
        module='rbac',
        category='system',
        action='update_module_settings',
        title='更新系统模块配置',
        summary=f'已更新系统模块显示、顺序与默认页配置，共 {len(updated_items)} 项',
        resource_type='rbac_system_module_setting',
        resource_id='module-settings',
        resource_name='系统模块配置',
        severity=EventRecord.SEVERITY_INFO,
        correlation_id='rbac-system-module-settings',
        metadata={'updated_count': len(updated_items), 'default_code': default_code},
    )
    return Response({'success': True, 'data': get_system_module_settings()})


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([LoginIPThrottle, LoginAccountThrottle])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = authenticate(
        username=serializer.validated_data['username'],
        password=serializer.validated_data['password'],
    )
    if not user:
        return Response({'detail': '用户名或密码错误。'}, status=status.HTTP_400_BAD_REQUEST)
    if not user.is_active:
        return Response({'detail': '用户已被禁用。'}, status=status.HTTP_403_FORBIDDEN)
    token, _ = Token.objects.get_or_create(user=user)
    User.objects.filter(pk=user.pk).update(last_login=timezone.now())
    user.refresh_from_db(fields=['last_login'])
    record_event(request=request, module='rbac', category='security', action='login',
                 title='用户登录', summary=f'用户 {user.username} 登录平台',
                 actor_username=user.username, resource_type='rbac_user', resource_id=user.pk,
                 resource_name=user.username)
    module_settings = get_system_module_settings()
    default_page = next((
        item['path']
        for item in module_settings
        if item['is_default'] and item['path']
    ), SYSTEM_MODULE_PATHS[DEFAULT_SYSTEM_MODULE_CODE])
    return Response({
        'token': token.key,
        'user': UserSerializer(user).data,
        'default_page': default_page,
        'module_settings': module_settings,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    token = Token.objects.filter(user=request.user).first()
    if token:
        token.delete()
    from django.contrib.auth import logout
    logout(request)
    return Response({'success': True})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user_view(request):
    return Response(UserSerializer(request.user).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, build_rbac_permission('rbac.permission.sync')])
def sync_permissions_view(request):
    ensure_builtin_rbac()
    record_event(
        request=request,
        module='rbac',
        category='system',
        action='sync_permissions',
        title='同步内置权限',
        summary='内置权限与角色已同步完成',
        resource_type='rbac_permission_registry',
        resource_id='builtin',
        resource_name='内置权限字典',
        severity=EventRecord.SEVERITY_INFO,
        correlation_id='rbac-permission-registry',
    )
    return Response({'success': True, 'message': '内置权限与角色已同步。'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def assignment_options_view(request):
    actor = request.user
    manage_users = user_has_permissions(actor, ['rbac.user.manage'])
    manage_groups = user_has_permissions(actor, ['rbac.group.manage'])
    manage_roles = user_has_permissions(actor, ['rbac.role.manage'])
    if not any((manage_users, manage_groups, manage_roles)):
        raise PermissionDenied('没有配置授权的权限。')
    ceiling = get_user_effective_permissions(actor)
    allowed_roles, allowed_groups = [], []
    for role in Role.objects.prefetch_related('permissions'):
        try:
            require_delegable_permissions(actor, role.permissions.values_list('code', flat=True))
        except PermissionDenied:
            continue
        allowed_roles.append({'id': role.id, 'name': role.name, 'code': role.code})
    for group in UserGroup.objects.all():
        try:
            require_delegable_permissions(actor, group_permission_codes([group]))
        except PermissionDenied:
            continue
        allowed_groups.append({'id': group.id, 'name': group.name, 'code': group.code})
    return Response({
        'roles': allowed_roles if manage_users or manage_groups else [],
        'groups': allowed_groups if manage_users else [],
        'permissions': PermissionDefinitionSerializer(PermissionDefinition.objects.filter(code__in=ceiling), many=True).data if manage_roles else [],
    })
