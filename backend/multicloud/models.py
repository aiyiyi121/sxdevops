from django.db import models


class CloudCredential(models.Model):
    PROVIDER_CHOICES = [
        ('aliyun', '阿里云'),
        ('tencent', '腾讯云'),
        ('huawei', '华为云'),
        ('baidu', '百度智能云'),
        ('aws', 'AWS'),
        ('vsphere', 'VMware vSphere / ESXi'),
    ]
    AUTH_MODE_CHOICES = [
        ('aksk', 'AK/SK'),
        ('sts', 'STS / AssumeRole'),
        ('secret', '密钥对'),
        ('demo', 'Demo'),
    ]
    HEALTH_CHOICES = [
        ('unknown', '未检测'),
        ('healthy', '健康'),
        ('warning', '告警'),
        ('error', '异常'),
    ]

    provider = models.CharField('云厂商', max_length=32, choices=PROVIDER_CHOICES)
    name = models.CharField('账号名称', max_length=128, unique=True)
    account_id = models.CharField('账号 ID', max_length=128, blank=True, default='')
    account_name = models.CharField('账号别名', max_length=128, blank=True, default='')
    auth_mode = models.CharField('认证方式', max_length=16, choices=AUTH_MODE_CHOICES, default='aksk')
    access_key_id = models.CharField('Access Key ID', max_length=255, blank=True, default='')
    access_key_secret = models.CharField('Access Key Secret', max_length=255, blank=True, default='')
    project_id = models.CharField('项目 / 租户', max_length=128, blank=True, default='')
    role_arn = models.CharField('角色 ARN', max_length=255, blank=True, default='')
    external_id = models.CharField('External ID', max_length=255, blank=True, default='')
    default_region = models.CharField('默认区域', max_length=64, blank=True, default='')
    owner = models.CharField('负责人', max_length=64, blank=True, default='')
    description = models.CharField('描述', max_length=255, blank=True, default='')
    tags = models.JSONField('标签', default=dict, blank=True)
    is_enabled = models.BooleanField('启用', default=True)
    demo_mode = models.BooleanField('Demo 模式', default=False)
    last_test_status = models.CharField('最近检测状态', max_length=16, choices=HEALTH_CHOICES, default='unknown')
    last_test_message = models.CharField('最近检测信息', max_length=255, blank=True, default='')
    last_sync_at = models.DateTimeField('最近同步时间', null=True, blank=True)
    created_by = models.CharField('创建人', max_length=64, blank=True, default='')
    updated_by = models.CharField('更新人', max_length=64, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['provider', 'name']
        verbose_name = '云账号'
        verbose_name_plural = '云账号'

    def __str__(self):
        return f'{self.get_provider_display()} / {self.name}'


class CloudEnvironment(models.Model):
    ENVIRONMENT_CHOICES = [
        ('prod', '生产'),
        ('test', '测试'),
        ('dev', '开发'),
        ('shared', '共享'),
    ]
    STATUS_CHOICES = [
        ('active', '运行中'),
        ('warning', '待治理'),
        ('offline', '已下线'),
    ]
    SYNC_STATUS_CHOICES = [
        ('never', '未同步'),
        ('running', '同步中'),
        ('success', '成功'),
        ('failed', '失败'),
    ]

    credential = models.ForeignKey(
        CloudCredential,
        on_delete=models.CASCADE,
        related_name='environments',
        verbose_name='云账号',
    )
    name = models.CharField('环境名称', max_length=128)
    code = models.CharField('环境编码', max_length=64, unique=True)
    business_line = models.CharField('系统', max_length=64, blank=True, default='')
    environment_type = models.CharField('环境类型', max_length=16, choices=ENVIRONMENT_CHOICES, default='prod')
    region = models.CharField('区域', max_length=64)
    zone = models.CharField('可用区', max_length=64, blank=True, default='')
    vpc_name = models.CharField('VPC', max_length=128, blank=True, default='')
    network_cidr = models.CharField('网段', max_length=64, blank=True, default='')
    owner = models.CharField('环境负责人', max_length=64, blank=True, default='')
    status = models.CharField('环境状态', max_length=16, choices=STATUS_CHOICES, default='active')
    sync_status = models.CharField('同步状态', max_length=16, choices=SYNC_STATUS_CHOICES, default='never')
    description = models.CharField('描述', max_length=255, blank=True, default='')
    tags = models.JSONField('标签', default=dict, blank=True)
    summary = models.JSONField('汇总', default=dict, blank=True)
    last_sync_at = models.DateTimeField('最近同步时间', null=True, blank=True)
    last_cmdb_sync_at = models.DateTimeField('最近同步到 CMDB 时间', null=True, blank=True)
    created_by = models.CharField('创建人', max_length=64, blank=True, default='')
    updated_by = models.CharField('更新人', max_length=64, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['credential__provider', 'environment_type', 'name']
        verbose_name = '云环境'
        verbose_name_plural = '云环境'
        constraints = [
            models.UniqueConstraint(
                fields=['credential', 'name'],
                name='multicloud_env_credential_name_unique',
            )
        ]

    def __str__(self):
        return f'{self.name} ({self.code})'


class CloudAsset(models.Model):
    RESOURCE_TYPE_CHOICES = [
        ('ecs', '云主机'),
        ('rds', '数据库'),
        ('slb', '负载均衡'),
        ('k8s', 'Kubernetes'),
        ('redis', 'Redis'),
        ('oss', '对象存储'),
        ('nat', 'NAT 网关'),
        ('eip', '弹性 IP'),
        ('security_group', '安全组'),
    ]
    STATUS_CHOICES = [
        ('running', '运行中'),
        ('stopped', '已停止'),
        ('degraded', '性能退化'),
        ('error', '异常'),
    ]
    RISK_CHOICES = [
        ('normal', '正常'),
        ('warning', '风险'),
        ('critical', '高危'),
    ]
    SYNC_STATE_CHOICES = [
        ('synced', '已同步'),
        ('drift', '配置漂移'),
        ('idle', '低利用率'),
    ]

    environment = models.ForeignKey(
        CloudEnvironment,
        on_delete=models.CASCADE,
        related_name='assets',
        verbose_name='环境',
    )
    provider = models.CharField('云厂商', max_length=32, choices=CloudCredential.PROVIDER_CHOICES)
    resource_type = models.CharField('资源类型', max_length=32, choices=RESOURCE_TYPE_CHOICES)
    resource_id = models.CharField('资源 ID', max_length=128)
    name = models.CharField('资源名称', max_length=128)
    region = models.CharField('区域', max_length=64, blank=True, default='')
    zone = models.CharField('可用区', max_length=64, blank=True, default='')
    status = models.CharField('资源状态', max_length=16, choices=STATUS_CHOICES, default='running')
    charge_type = models.CharField('计费方式', max_length=32, blank=True, default='')
    private_ip = models.CharField('私网 IP', max_length=128, blank=True, default='')
    public_ip = models.CharField('公网 IP', max_length=128, blank=True, default='')
    vpc_name = models.CharField('VPC', max_length=128, blank=True, default='')
    spec = models.CharField('规格', max_length=128, blank=True, default='')
    cpu = models.PositiveIntegerField('CPU', default=0)
    memory_gb = models.DecimalField('内存(GB)', max_digits=8, decimal_places=1, default=0)
    disk_gb = models.DecimalField('磁盘(GB)', max_digits=10, decimal_places=1, default=0)
    monthly_cost = models.DecimalField('月成本', max_digits=12, decimal_places=2, default=0)
    cost_currency = models.CharField('币种', max_length=8, default='CNY')
    risk_level = models.CharField('风险等级', max_length=16, choices=RISK_CHOICES, default='normal')
    sync_state = models.CharField('同步态', max_length=16, choices=SYNC_STATE_CHOICES, default='synced')
    tags = models.JSONField('标签', default=dict, blank=True)
    metadata = models.JSONField('扩展信息', default=dict, blank=True)
    synced_at = models.DateTimeField('同步时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['provider', 'resource_type', 'name']
        verbose_name = '云资源'
        verbose_name_plural = '云资源'
        constraints = [
            models.UniqueConstraint(
                fields=['environment', 'resource_type', 'resource_id'],
                name='multicloud_asset_env_type_resid_unique',
            )
        ]
        indexes = [
            models.Index(fields=['provider', 'resource_type', 'status']),
            models.Index(fields=['environment', 'risk_level', 'sync_state']),
        ]

    def __str__(self):
        return f'{self.name} ({self.resource_id})'


class CloudSyncTask(models.Model):
    TASK_TYPE_CHOICES = [
        ('full', '全量同步'),
        ('inventory', '资源同步'),
        ('cost', '成本同步'),
        ('security', '安全巡检'),
        ('cmdb', '同步 CMDB'),
    ]
    STATUS_CHOICES = [
        ('pending', '待执行'),
        ('running', '执行中'),
        ('success', '成功'),
        ('failed', '失败'),
    ]

    credential = models.ForeignKey(
        CloudCredential,
        on_delete=models.CASCADE,
        related_name='sync_tasks',
        verbose_name='云账号',
        null=True,
        blank=True,
    )
    environment = models.ForeignKey(
        CloudEnvironment,
        on_delete=models.CASCADE,
        related_name='sync_tasks',
        verbose_name='环境',
        null=True,
        blank=True,
    )
    task_type = models.CharField('任务类型', max_length=16, choices=TASK_TYPE_CHOICES, default='full')
    status = models.CharField('任务状态', max_length=16, choices=STATUS_CHOICES, default='pending')
    operator = models.CharField('执行人', max_length=64, blank=True, default='')
    summary = models.CharField('任务摘要', max_length=255, blank=True, default='')
    result = models.JSONField('任务结果', default=dict, blank=True)
    started_at = models.DateTimeField('开始时间', null=True, blank=True)
    finished_at = models.DateTimeField('结束时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = '同步任务'
        verbose_name_plural = '同步任务'

    def __str__(self):
        return f'{self.get_task_type_display()} / {self.status}'

    @property
    def target_display(self):
        if self.environment_id:
            return self.environment.name
        if self.credential_id:
            return self.credential.name
        return '未知目标'
