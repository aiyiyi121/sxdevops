from django.conf import settings
from django.db import models


class PermissionDefinition(models.Model):
    code = models.CharField('权限编码', max_length=100, unique=True)
    name = models.CharField('权限名称', max_length=100)
    category = models.CharField('模块分类', max_length=50)
    description = models.CharField('描述', max_length=255, blank=True, default='')
    sort_order = models.PositiveIntegerField('排序', default=0)
    is_builtin = models.BooleanField('内置权限', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '权限'
        verbose_name_plural = '权限'
        ordering = ['sort_order', 'category', 'code']

    def __str__(self):
        return f'{self.name} ({self.code})'


class Role(models.Model):
    code = models.CharField('角色编码', max_length=64, unique=True)
    name = models.CharField('角色名称', max_length=64, unique=True)
    description = models.CharField('描述', max_length=255, blank=True, default='')
    permissions = models.ManyToManyField(PermissionDefinition, blank=True, related_name='roles', verbose_name='权限')
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='rbac_roles', verbose_name='绑定用户')
    is_builtin = models.BooleanField('内置角色', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '角色'
        verbose_name_plural = '角色'
        ordering = ['name']

    def __str__(self):
        return self.name


class UserGroup(models.Model):
    code = models.CharField('用户组编码', max_length=64, unique=True)
    name = models.CharField('用户组名称', max_length=64, unique=True)
    description = models.CharField('描述', max_length=255, blank=True, default='')
    roles = models.ManyToManyField(Role, blank=True, related_name='user_groups', verbose_name='关联角色')
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='rbac_groups', verbose_name='组内用户')
    is_builtin = models.BooleanField('内置用户组', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '用户组'
        verbose_name_plural = '用户组'
        ordering = ['name']

    def __str__(self):
        return self.name


class SiteSetting(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    site_name = models.CharField('网站名称', max_length=10, default='SXDevOps')
    icon_data = models.BinaryField('网站图标', blank=True, default=bytes)
    updated_by = models.CharField('更新人', max_length=150, blank=True, default='')
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '网站基础配置'
        verbose_name_plural = '网站基础配置'
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name='rbac_single_site_setting')]


class SystemModuleSetting(models.Model):
    code = models.CharField('模块编码', max_length=64, unique=True)
    enabled = models.BooleanField('是否显示', default=True)
    is_default = models.BooleanField('是否为登录默认页', default=False)
    sort_order = models.PositiveIntegerField('菜单顺序', null=True, blank=True, default=None)
    updated_by = models.CharField('更新人', max_length=150, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '系统模块配置'
        verbose_name_plural = '系统模块配置'
        ordering = ['code']
        constraints = [
            models.UniqueConstraint(
                fields=['is_default'],
                condition=models.Q(is_default=True),
                name='rbac_single_default_page',
            ),
        ]

    def __str__(self):
        return self.code


class K8sUserAccess(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='k8s_access')
    unrestricted = models.BooleanField('沿用平台权限范围', default=False)


class K8sClusterGrant(models.Model):
    access = models.ForeignKey(K8sUserAccess, on_delete=models.CASCADE, related_name='grants')
    cluster = models.ForeignKey('ops.K8sCluster', on_delete=models.CASCADE, related_name='user_grants')
    role = models.CharField('集群角色', max_length=16, choices=[('viewer', '只读'), ('operator', '运维'), ('admin', '管理员')])
    namespaces = models.JSONField('命名空间范围', default=list, blank=True)
    allow_exec = models.BooleanField('允许 Pod 终端', default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['access', 'cluster'], name='rbac_unique_k8s_cluster_grant')]
