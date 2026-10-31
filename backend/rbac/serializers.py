from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from ops.models import K8sCluster

from .models import K8sClusterGrant, PermissionDefinition, Role, UserGroup
from .registry import BUILTIN_ROLES
from .services import get_user_effective_permissions
from .security import (
    group_permission_codes, require_delegable_permissions, require_manageable_role, require_manageable_user,
    require_safe_account_removal, revoke_user_credentials, role_permission_codes,
)


User = get_user_model()


class K8sClusterGrantSerializer(serializers.ModelSerializer):
    cluster = serializers.PrimaryKeyRelatedField(queryset=K8sCluster.objects.all())
    namespaces = serializers.ListField(child=serializers.RegexField(r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$', max_length=63), required=False)

    class Meta:
        model = K8sClusterGrant
        fields = ['cluster', 'role', 'namespaces', 'allow_exec']
        validators = []

    def validate(self, attrs):
        attrs['namespaces'] = sorted(set(attrs.get('namespaces', [])))
        if attrs.get('role') == 'viewer' and attrs.get('allow_exec'):
            raise serializers.ValidationError('只读角色不能使用 Pod 终端。')
        return attrs


class K8sUserAccessSerializer(serializers.Serializer):
    unrestricted = serializers.BooleanField()
    grants = K8sClusterGrantSerializer(many=True)

    def validate_grants(self, value):
        ids = [item['cluster'].pk for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError('同一集群只能配置一条授权。')
        return value


class PermissionDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermissionDefinition
        fields = '__all__'


class RoleLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'code', 'name']


class GroupLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserGroup
        fields = ['id', 'code', 'name']


class UserLiteSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'display_name']

    def get_display_name(self, obj):
        full_name = f'{obj.first_name} {obj.last_name}'.strip()
        return full_name or obj.username


class RoleSerializer(serializers.ModelSerializer):
    can_manage = serializers.SerializerMethodField()
    permission_ids = serializers.PrimaryKeyRelatedField(
        queryset=PermissionDefinition.objects.all(), many=True, write_only=True, required=False
    )
    permissions = PermissionDefinitionSerializer(many=True, read_only=True)
    user_count = serializers.SerializerMethodField()
    group_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            'id', 'code', 'name', 'description', 'is_builtin', 'created_at', 'updated_at',
            'permission_ids', 'permissions', 'user_count', 'group_count',
            'can_manage',
        ]
        read_only_fields = ['is_builtin', 'created_at', 'updated_at']

    def get_user_count(self, obj):
        return obj.users.count()

    def get_group_count(self, obj):
        return obj.user_groups.count()

    def get_can_manage(self, obj):
        actor = getattr(self.context.get('request'), 'user', None)
        try:
            require_manageable_role(actor, obj)
        except PermissionDenied:
            return False
        from .services import user_has_permissions
        return not obj.is_builtin and user_has_permissions(actor, ['rbac.role.manage'])

    def validate(self, attrs):
        actor = getattr(self.context.get('request'), 'user', None)
        if attrs.get('code') in {role['code'] for role in BUILTIN_ROLES}:
            raise serializers.ValidationError({'code': '该编码由内置角色保留。'})
        if self.instance:
            if self.instance.is_builtin:
                raise serializers.ValidationError('内置角色由系统维护，请新建自定义角色后授权。')
            require_manageable_role(actor, self.instance)
        permissions = attrs.get('permission_ids', [])
        require_delegable_permissions(actor, [permission.code for permission in permissions])
        return attrs

    def create(self, validated_data):
        permission_ids = validated_data.pop('permission_ids', [])
        instance = super().create(validated_data)
        if permission_ids is not None:
            instance.permissions.set(permission_ids)
        return instance

    def update(self, instance, validated_data):
        permission_ids = validated_data.pop('permission_ids', None)
        instance = super().update(instance, validated_data)
        if permission_ids is not None:
            instance.permissions.set(permission_ids)
        return instance


class UserGroupSerializer(serializers.ModelSerializer):
    can_manage = serializers.SerializerMethodField()
    role_ids = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all(), many=True, write_only=True, required=False)
    user_ids = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True, write_only=True, required=False)
    roles = RoleLiteSerializer(many=True, read_only=True)
    users = UserLiteSerializer(many=True, read_only=True)

    class Meta:
        model = UserGroup
        fields = [
            'id', 'code', 'name', 'description', 'is_builtin', 'created_at', 'updated_at',
            'role_ids', 'user_ids', 'roles', 'users',
            'can_manage',
        ]
        read_only_fields = ['is_builtin', 'created_at', 'updated_at']

    def get_can_manage(self, obj):
        actor = getattr(self.context.get('request'), 'user', None)
        try:
            require_delegable_permissions(actor, group_permission_codes([obj]))
            for user in obj.users.all():
                require_manageable_user(actor, user)
        except PermissionDenied:
            return False
        from .services import user_has_permissions
        return user_has_permissions(actor, ['rbac.group.manage'])

    def validate(self, attrs):
        actor = getattr(self.context.get('request'), 'user', None)
        if self.instance:
            if self.instance.is_builtin and attrs.get('code', self.instance.code) != self.instance.code:
                raise serializers.ValidationError({'code': '内置用户组编码不能修改。'})
            require_delegable_permissions(actor, group_permission_codes([self.instance]))
        require_delegable_permissions(actor, role_permission_codes(attrs.get('role_ids', [])))
        if 'role_ids' in attrs or 'user_ids' in attrs:
            targets = {user.pk: user for user in attrs.get('user_ids', [])}
            if self.instance:
                targets.update({user.pk: user for user in self.instance.users.all()})
            for target in targets.values():
                require_manageable_user(actor, target)
        return attrs

    def create(self, validated_data):
        role_ids = validated_data.pop('role_ids', [])
        user_ids = validated_data.pop('user_ids', [])
        instance = super().create(validated_data)
        instance.roles.set(role_ids)
        instance.users.set(user_ids)
        return instance

    def update(self, instance, validated_data):
        role_ids = validated_data.pop('role_ids', None)
        user_ids = validated_data.pop('user_ids', None)
        instance = super().update(instance, validated_data)
        if role_ids is not None:
            instance.roles.set(role_ids)
        if user_ids is not None:
            instance.users.set(user_ids)
        return instance


class SystemModuleSettingUpdateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    enabled = serializers.BooleanField(required=False)
    sort_order = serializers.IntegerField(min_value=0, max_value=32767, allow_null=True, required=False)


class UserSerializer(serializers.ModelSerializer):
    is_preview = serializers.SerializerMethodField()
    preview_permissions = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()
    can_remove = serializers.SerializerMethodField()
    k8s_unrestricted = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=False, trim_whitespace=False)
    role_ids = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all(), many=True, write_only=True, required=False)
    group_ids = serializers.PrimaryKeyRelatedField(queryset=UserGroup.objects.all(), many=True, write_only=True, required=False)
    roles = RoleLiteSerializer(source='rbac_roles', many=True, read_only=True)
    user_groups = GroupLiteSerializer(source='rbac_groups', many=True, read_only=True)
    effective_permissions = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser',
            'date_joined', 'last_login', 'password', 'role_ids', 'group_ids', 'roles', 'user_groups',
            'effective_permissions', 'display_name', 'k8s_unrestricted',
            'can_manage', 'can_remove',
            'is_preview', 'preview_permissions',
        ]
        read_only_fields = ['date_joined', 'last_login', 'is_staff', 'is_superuser']

    def get_can_manage(self, obj):
        actor = getattr(self.context.get('request'), 'user', None)
        try:
            require_manageable_user(actor, obj)
        except PermissionDenied:
            return False
        from .services import user_has_permissions
        return user_has_permissions(actor, ['rbac.user.manage'])

    def get_is_preview(self, obj):
        from .preview import is_preview_user
        return is_preview_user(obj)

    def get_preview_permissions(self, obj):
        if not self.get_is_preview(obj):
            return []
        from .registry import PERMISSION_DEFINITIONS
        from sxdevops.features import filter_feature_permissions
        return filter_feature_permissions([code for code, *_ in PERMISSION_DEFINITIONS])

    def get_can_remove(self, obj):
        actor = getattr(self.context.get('request'), 'user', None)
        if not self.get_can_manage(obj) or actor.pk == obj.pk:
            return False
        return not (obj.is_active and obj.is_superuser and User.objects.filter(is_active=True, is_superuser=True).count() <= 1)

    def get_effective_permissions(self, obj):
        return sorted(get_user_effective_permissions(obj))

    def get_k8s_unrestricted(self, obj):
        from .k8s_access import get_k8s_grants
        return get_k8s_grants(obj) is None

    def get_display_name(self, obj):
        full_name = f'{obj.first_name} {obj.last_name}'.strip()
        return full_name or obj.username

    def validate(self, attrs):
        actor = getattr(self.context.get('request'), 'user', None)
        if self.instance:
            require_manageable_user(actor, self.instance)
            if attrs.get('username', self.instance.username) != self.instance.username:
                raise serializers.ValidationError({'username': '创建后不能修改用户名。'})
            if attrs.get('is_active') is False and self.instance.is_active:
                require_safe_account_removal(actor, self.instance)
        require_delegable_permissions(actor, role_permission_codes(attrs.get('role_ids', [])))
        require_delegable_permissions(actor, group_permission_codes(attrs.get('group_ids', [])))
        if 'password' in attrs:
            candidate = User(**{key: attrs.get(key, getattr(self.instance, key, ''))
                                for key in ('username', 'email', 'first_name', 'last_name')})
            validate_password(attrs['password'], user=candidate)
        elif not self.instance:
            raise serializers.ValidationError({'password': '创建用户时必须提供密码。'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop('password', None)
        role_ids = validated_data.pop('role_ids', [])
        group_ids = validated_data.pop('group_ids', [])
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            raise serializers.ValidationError({'password': '创建用户时必须提供密码。'})
        user.save()
        user.rbac_roles.set(role_ids)
        user.rbac_groups.set(group_ids)
        from .k8s_access import get_k8s_grants
        from .models import K8sUserAccess
        actor = getattr(self.context.get('request'), 'user', None)
        if actor and get_k8s_grants(actor) is not None:
            K8sUserAccess.objects.create(user=user, unrestricted=False)
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        role_ids = validated_data.pop('role_ids', None)
        group_ids = validated_data.pop('group_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        if role_ids is not None:
            instance.rbac_roles.set(role_ids)
        if group_ids is not None:
            instance.rbac_groups.set(group_ids)
        if password or not instance.is_active:
            revoke_user_credentials(instance)
        return instance


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)
