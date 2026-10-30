from django.db import models


class CIModelGroup(models.Model):
    name = models.CharField("分组名称", max_length=50)
    code = models.CharField("分组编码", max_length=50, unique=True)
    description = models.CharField("描述", max_length=200, blank=True, default='')
    sort_order = models.IntegerField("排序", default=0)
    is_builtin = models.BooleanField("内置分组", default=False)
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.name


class CIType(models.Model):
    name = models.CharField("模型名称", max_length=50, unique=True)
    code = models.CharField("模型编码", max_length=50, blank=True, default='')
    group = models.ForeignKey(CIModelGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='ci_types')
    icon = models.CharField("内置图标", max_length=50, blank=True)
    color = models.CharField("主题色", max_length=20, default="#9c27b0")
    description = models.CharField("描述", max_length=200, blank=True)
    is_builtin = models.BooleanField("内置模型", default=False)
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['code'],
                condition=~models.Q(code=''),
                name='cmdb_citype_unique_nonblank_code',
            )
        ]

    def __str__(self):
        return self.name


class CITag(models.Model):
    name = models.CharField("标签名称", max_length=50, unique=True)
    category = models.CharField("标签分类", max_length=50, blank=True, default='')
    color = models.CharField("标签颜色", max_length=20, default="#245bdb")
    description = models.CharField("描述", max_length=200, blank=True, default='')
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name', 'id']

    def __str__(self):
        return self.name


class CIField(models.Model):
    SYNC_MODE_CHOICES = [
        ('source', '来源优先'),
        ('manual', '人工优先'),
    ]

    FIELD_TYPE_CHOICES = [
        ('string', '字符串'),
        ('integer', '整数'),
        ('decimal', '小数'),
        ('boolean', '布尔'),
        ('date', '日期'),
        ('datetime', '日期时间'),
        ('enum', '单选枚举'),
        ('multi_enum', '多选枚举'),
        ('ip', 'IP 地址'),
        ('url', 'URL'),
        ('json', 'JSON'),
        ('reference', '引用字段'),
    ]

    ci_type = models.ForeignKey(CIType, on_delete=models.CASCADE, related_name='fields')
    name = models.CharField("字段名称", max_length=80)
    code = models.CharField("字段编码", max_length=80)
    field_type = models.CharField("字段类型", max_length=20, choices=FIELD_TYPE_CHOICES, default='string')
    field_group = models.CharField("字段分组", max_length=80, blank=True, default='')
    required = models.BooleanField("必填", default=False)
    unique = models.BooleanField("唯一", default=False)
    default = models.JSONField("默认值", null=True, blank=True)
    options = models.JSONField("选项", default=list, blank=True)
    validation = models.JSONField("校验规则", default=dict, blank=True)
    sync_mode = models.CharField("同步方式", max_length=20, choices=SYNC_MODE_CHOICES, default='source')
    is_builtin = models.BooleanField("内置字段", default=False)
    is_display = models.BooleanField("列表展示", default=True)
    is_searchable = models.BooleanField("可搜索", default=False)
    is_sensitive = models.BooleanField("敏感字段", default=False)
    is_active = models.BooleanField("启用", default=True)
    sort_order = models.IntegerField("排序", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['ci_type_id', 'sort_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['ci_type', 'code'],
                name='cmdb_cifield_unique_type_code',
            )
        ]

    def __str__(self):
        return f"{self.ci_type.name}.{self.name}"


class ConfigItem(models.Model):
    name = models.CharField("配置项名称", max_length=100)
    ci_type = models.ForeignKey(CIType, on_delete=models.PROTECT, related_name='instances')
    business_node = models.ForeignKey(
        'ResourceNode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='business_config_items',
        verbose_name="业务线节点",
    )
    business_line = models.CharField("业务线", max_length=50, blank=True)
    environment_node = models.ForeignKey(
        'ResourceNode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='environment_config_items',
        verbose_name="环境节点",
    )
    resource_node = models.ForeignKey(
        'ResourceNode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resource_config_items',
        verbose_name="云资源节点",
    )
    environment = models.CharField("环境", max_length=50, blank=True, default='')
    admin_user = models.CharField("负责人", max_length=50, blank=True)
    status = models.CharField("状态", max_length=20, choices=[('active', '使用中'), ('stopped', '停机'), ('offline', '已下线')], default='active')
    tags = models.ManyToManyField(CITag, blank=True, related_name='config_items', verbose_name="标签")
    attributes = models.JSONField("扩展属性", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['ci_type', 'status'], name='cmdb_ci_type_status_idx'),
            models.Index(fields=['business_line', 'environment'], name='cmdb_ci_biz_env_idx'),
            models.Index(fields=['-updated_at', '-id'], name='cmdb_ci_updated_id_idx'),
        ]

    def __str__(self):
        return f"[{self.ci_type.name}] {self.name}"

    def get_environment_display(self):
        return self.environment


class ConfigItemPassword(models.Model):
    config_item = models.OneToOneField(
        ConfigItem,
        on_delete=models.CASCADE,
        related_name='login_password',
        verbose_name="关联资产",
    )
    username = models.CharField("登录用户名", max_length=150, blank=True, default='')
    password_ciphertext = models.TextField("密码密文")
    remark = models.CharField("备注", max_length=255, blank=True, default='')
    created_by = models.CharField("创建人", max_length=150, blank=True, default='')
    updated_by = models.CharField("更新人", max_length=150, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']

    def __str__(self):
        return f"{self.config_item.name} 登录凭据"


class IPSubnet(models.Model):
    name = models.CharField("子网名称", max_length=100)
    cidr = models.CharField("CIDR", max_length=50, unique=True)
    vlan_name = models.CharField("VLAN / Port Group", max_length=100, blank=True, default='')
    gateway = models.CharField("网关", max_length=45, blank=True, default='')
    description = models.CharField("说明", max_length=200, blank=True, default='')
    excluded_addresses = models.JSONField("保留地址", default=list, blank=True)
    last_scanned_at = models.DateTimeField("最近扫描时间", null=True, blank=True)
    created_by = models.CharField("创建人", max_length=80, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['cidr', 'id']

    def __str__(self):
        return f"{self.name} ({self.cidr})"


class IPAddress(models.Model):
    STATUS_CHOICES = [
        ('available', '空闲'),
        ('in_use', '使用中'),
        ('offline', '停机'),
        ('reserved', '已保留'),
    ]
    REACHABILITY_CHOICES = [
        ('unknown', '未扫描'),
        ('reachable', '可达'),
        ('unreachable', '不通'),
    ]

    subnet = models.ForeignKey(IPSubnet, on_delete=models.CASCADE, related_name='addresses')
    address = models.CharField("IP 地址", max_length=45)
    status = models.CharField("地址状态", max_length=20, choices=STATUS_CHOICES, default='available')
    reachability = models.CharField("扫描状态", max_length=20, choices=REACHABILITY_CHOICES, default='unknown')
    ci = models.ForeignKey(ConfigItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='ip_addresses')
    linked_ci_names = models.JSONField("关联资产", default=list, blank=True)
    note = models.CharField("备注", max_length=200, blank=True, default='')
    last_scanned_at = models.DateTimeField("最近扫描时间", null=True, blank=True)
    created_by = models.CharField("创建人", max_length=80, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['subnet_id', 'address']
        constraints = [
            models.UniqueConstraint(fields=['subnet', 'address'], name='cmdb_ipaddress_unique_subnet_ip'),
        ]
        indexes = [
            models.Index(fields=['subnet', 'status'], name='cmdb_ip_subnet_status_idx'),
        ]

    def __str__(self):
        return self.address


class CISourceMapping(models.Model):
    SYNC_STATUS_CHOICES = [
        ('success', '成功'),
        ('failed', '失败'),
        ('missing', '来源缺失'),
        ('conflict', '冲突'),
    ]

    ci = models.ForeignKey(ConfigItem, on_delete=models.CASCADE, related_name='source_mappings')
    source_type = models.CharField("来源类型", max_length=50)
    source_account = models.CharField("来源账号", max_length=100, blank=True, default='')
    source_region = models.CharField("来源地域", max_length=100, blank=True, default='')
    source_unique_id = models.CharField("来源唯一标识", max_length=200)
    last_seen_at = models.DateTimeField("最后发现时间", null=True, blank=True)
    sync_status = models.CharField("同步状态", max_length=20, choices=SYNC_STATUS_CHOICES, default='success')
    raw_payload = models.JSONField("原始数据", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['ci', 'source_type'], name='cmdb_src_ci_type_idx'),
            models.Index(fields=['source_type', 'source_account'], name='cmdb_src_type_account_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['source_type', 'source_account', 'source_region', 'source_unique_id'],
                name='cmdb_source_mapping_unique_source',
            )
        ]

    def __str__(self):
        return f"{self.source_type}:{self.source_unique_id}"


class CIRelation(models.Model):
    EVIDENCE_SOURCE_CHOICES = [
        ('manual', '人工维护'),
        ('import', '批量导入'),
        ('sync', '同步发现'),
        ('governance', '治理建议'),
        ('system', '系统联动'),
    ]

    source = models.ForeignKey(ConfigItem, on_delete=models.CASCADE, related_name='outgoing_relations')
    target = models.ForeignKey(ConfigItem, on_delete=models.CASCADE, related_name='incoming_relations')
    relation_type = models.CharField(
        "关系类型",
        max_length=50,
        choices=[
            ('depends_on', '业务依赖'),
            ('runs_on', '部署在'),
            ('connects_to', '连接到'),
        ],
    )
    description = models.CharField("描述", max_length=200, blank=True)
    evidence_source = models.CharField("关系来源", max_length=30, choices=EVIDENCE_SOURCE_CHOICES, default='manual')
    confidence = models.PositiveSmallIntegerField("置信度", default=100)
    evidence = models.JSONField("关系证据", default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'target', 'relation_type'],
                name='cmdb_cirelation_unique_relation',
            )
        ]


class CIRelationRule(models.Model):
    source_type = models.ForeignKey(CIType, on_delete=models.CASCADE, related_name='outgoing_relation_rules')
    target_type = models.ForeignKey(CIType, on_delete=models.CASCADE, related_name='incoming_relation_rules')
    relation_type = models.CharField("关系类型", max_length=50)
    direction = models.CharField("方向", max_length=20, default='outgoing')
    required = models.BooleanField("必填关系", default=False)
    multiple = models.BooleanField("允许多个", default=True)
    description = models.CharField("描述", max_length=200, blank=True, default='')
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['source_type', 'target_type', 'relation_type'],
                name='cmdb_relation_rule_unique',
            )
        ]


class CIThresholdPolicy(models.Model):
    resource_type = models.ForeignKey(CIType, on_delete=models.CASCADE, related_name='threshold_policies', null=True, blank=True)
    metric = models.CharField("指标", max_length=50)
    normal_threshold = models.DecimalField("正常阈值", max_digits=8, decimal_places=2, default=70)
    warning_threshold = models.DecimalField("预警阈值", max_digits=8, decimal_places=2, default=85)
    critical_threshold = models.DecimalField("紧张阈值", max_digits=8, decimal_places=2, default=95)
    exceeded_threshold = models.DecimalField("超限阈值", max_digits=8, decimal_places=2, default=100)
    enabled = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['resource_type', 'metric'],
                name='cmdb_threshold_unique_type_metric',
            )
        ]


class CIResourceMetricSnapshot(models.Model):
    ci = models.ForeignKey(ConfigItem, on_delete=models.CASCADE, related_name='metric_snapshots')
    metric = models.CharField("指标", max_length=50)
    value = models.DecimalField("指标值", max_digits=16, decimal_places=4)
    unit = models.CharField("单位", max_length=20, blank=True, default='')
    usage_percent = models.DecimalField("使用率", max_digits=8, decimal_places=2, null=True, blank=True)
    collected_at = models.DateTimeField("采集时间")
    source = models.CharField("来源", max_length=50, blank=True, default='')

    class Meta:
        ordering = ['-collected_at', '-id']
        indexes = [
            models.Index(fields=['ci', 'metric', '-collected_at', '-id'], name='cmdb_metric_ci_latest_idx'),
            models.Index(fields=['metric', '-collected_at'], name='cmdb_metric_latest_idx'),
        ]


class CIChangeLog(models.Model):
    ci = models.ForeignKey(ConfigItem, on_delete=models.CASCADE, null=True, blank=True, related_name='change_logs')
    action = models.CharField("动作", max_length=50)
    before = models.JSONField("变更前", default=dict, blank=True)
    after = models.JSONField("变更后", default=dict, blank=True)
    diff = models.JSONField("差异", default=dict, blank=True)
    operator = models.CharField("操作人", max_length=80, blank=True, default='')
    source = models.CharField("来源", max_length=50, blank=True, default='manual')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']


class CISyncJob(models.Model):
    STATUS_CHOICES = [
        ('pending', '待执行'),
        ('running', '执行中'),
        ('success', '成功'),
        ('partial', '部分成功'),
        ('failed', '失败'),
    ]
    MODE_CHOICES = [
        ('manual', '手动'),
        ('scheduled', '定时'),
        ('import', '导入'),
    ]

    name = models.CharField("任务名称", max_length=120)
    source_type = models.CharField("来源类型", max_length=50)
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='pending')
    mode = models.CharField("模式", max_length=20, choices=MODE_CHOICES, default='manual')
    dry_run = models.BooleanField("差异预览", default=False)
    config = models.JSONField("任务配置", default=dict, blank=True)
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    created_by = models.CharField("创建人", max_length=80, blank=True, default='')
    summary = models.JSONField("执行摘要", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return self.name


class CISyncRecord(models.Model):
    ACTION_CHOICES = [
        ('create', '新增'),
        ('update', '更新'),
        ('skip', '跳过'),
        ('fail', '失败'),
        ('conflict', '冲突'),
        ('archive_candidate', '待下线'),
    ]

    job = models.ForeignKey(CISyncJob, on_delete=models.CASCADE, related_name='records')
    ci = models.ForeignKey(ConfigItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='sync_records')
    batch_id = models.CharField("执行批次", max_length=32, blank=True, default='', db_index=True)
    action = models.CharField("动作", max_length=30, choices=ACTION_CHOICES)
    source_unique_id = models.CharField("来源唯一标识", max_length=200, blank=True, default='')
    before = models.JSONField("变更前", default=dict, blank=True)
    after = models.JSONField("变更后", default=dict, blank=True)
    diff = models.JSONField("差异", default=dict, blank=True)
    status = models.CharField("状态", max_length=20, default='success')
    error_message = models.TextField("错误信息", blank=True, default='')
    retry_status = models.CharField("重试状态", max_length=20, default='not_retried')
    retry_count = models.IntegerField("重试次数", default=0)
    last_retried_at = models.DateTimeField("最后重试时间", null=True, blank=True)
    retried_by = models.CharField("重试人", max_length=80, blank=True, default='')
    retry_result = models.CharField("重试结果", max_length=30, blank=True, default='')
    retry_error_message = models.TextField("重试错误信息", blank=True, default='')
    retry_record = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='original_retry_records',
        verbose_name="重试生成记录",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']


class CICompletionIssue(models.Model):
    STATUS_CHOICES = [
        ('open', '待处理'),
        ('assigned', '已分派'),
        ('resolved', '已解决'),
        ('ignored', '已忽略'),
    ]
    SEVERITY_CHOICES = [
        ('low', '低'),
        ('medium', '中'),
        ('high', '高'),
    ]

    ci = models.ForeignKey(ConfigItem, on_delete=models.CASCADE, related_name='completion_issues')
    missing_fields = models.JSONField("缺失字段", default=list, blank=True)
    severity = models.CharField("严重程度", max_length=20, choices=SEVERITY_CHOICES, default='medium')
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='open')
    assigned_to = models.CharField("处理人", max_length=80, blank=True, default='')
    resolved_at = models.DateTimeField("解决时间", null=True, blank=True)
    resolution_note = models.CharField("处理说明", max_length=200, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']


class CIArchiveCandidate(models.Model):
    STATUS_CHOICES = [
        ('pending', '待确认'),
        ('confirmed', '已确认'),
        ('archived', '已归档'),
        ('restored', '已恢复'),
        ('ignored', '已忽略'),
    ]

    ci = models.ForeignKey(ConfigItem, on_delete=models.CASCADE, related_name='archive_candidates')
    source_type = models.CharField("来源类型", max_length=50, blank=True, default='')
    reason = models.CharField("原因", max_length=200, blank=True, default='')
    last_seen_at = models.DateTimeField("最后发现时间", null=True, blank=True)
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='pending')
    confirmed_by = models.CharField("确认人", max_length=80, blank=True, default='')
    confirmed_at = models.DateTimeField("确认时间", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']


class CIResourceAuthorization(models.Model):
    PRINCIPAL_TYPE_CHOICES = [
        ('user', '用户'),
        ('group', '用户组'),
    ]
    PERMISSION_CHOICES = [
        ('view', '查看'),
        ('manage', '管理'),
    ]

    name = models.CharField("授权名称", max_length=120)
    principal_type = models.CharField("授权主体类型", max_length=20, choices=PRINCIPAL_TYPE_CHOICES)
    principal = models.CharField("授权主体", max_length=150)
    permission = models.CharField("授权权限", max_length=20, choices=PERMISSION_CHOICES, default='view')
    business_line = models.CharField("业务线", max_length=50, blank=True, default='')
    environment = models.CharField("环境", max_length=20, blank=True, default='')
    ci_type = models.ForeignKey(CIType, on_delete=models.CASCADE, null=True, blank=True, related_name='resource_authorizations')
    description = models.CharField("说明", max_length=200, blank=True, default='')
    is_active = models.BooleanField("启用", default=True)
    created_by = models.CharField("创建人", max_length=80, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['principal_type', 'principal', 'permission', 'business_line', 'environment', 'ci_type'],
                name='cmdb_resource_auth_unique_scope',
            )
        ]

    def __str__(self):
        return f"{self.name}({self.principal_type}:{self.principal})"


class CostRecord(models.Model):
    ci = models.ForeignKey(ConfigItem, on_delete=models.CASCADE, related_name='costs')
    month = models.CharField("归属月份", max_length=7) # YYYY-MM
    amount = models.DecimalField("金额(元)", max_digits=10, decimal_places=2)
    provider = models.CharField("云厂商", max_length=50, blank=True)
    computed_at = models.DateTimeField(auto_now_add=True)


class CostOptimizationTask(models.Model):
    STATUS_CHOICES = [
        ('claimed', '已认领'),
        ('in_progress', '处理中'),
        ('completed', '已完成'),
        ('deferred', '暂缓处理'),
        ('rejected', '不采纳'),
    ]

    ci = models.ForeignKey(ConfigItem, on_delete=models.CASCADE, related_name='cost_optimization_tasks')
    month = models.CharField('归属月份', max_length=7)
    suggestion_type = models.CharField('优化类型', max_length=32)
    suggestion_title = models.CharField('建议标题', max_length=200)
    suggestion_snapshot = models.JSONField('建议快照', default=dict, blank=True)
    expected_monthly_saving = models.DecimalField('预估月节省', max_digits=12, decimal_places=2, default=0)
    actual_monthly_saving = models.DecimalField('实际月节省', max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField('处理状态', max_length=20, choices=STATUS_CHOICES, default='claimed')
    owner = models.CharField('认领人', max_length=80, blank=True, default='')
    claimed_at = models.DateTimeField('认领时间', null=True, blank=True)
    resolved_by = models.CharField('结论确认人', max_length=80, blank=True, default='')
    resolved_at = models.DateTimeField('结论时间', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['ci', 'month', 'suggestion_type'],
                name='cmdb_cost_optimization_task_unique_suggestion',
            )
        ]


class CostOptimizationProgress(models.Model):
    task = models.ForeignKey(CostOptimizationTask, on_delete=models.CASCADE, related_name='progress_entries')
    status = models.CharField('处理状态', max_length=20, choices=CostOptimizationTask.STATUS_CHOICES)
    progress_percent = models.PositiveSmallIntegerField('完成度', default=0)
    note = models.TextField('进展说明', blank=True, default='')
    actual_monthly_saving = models.DecimalField('实际月节省', max_digits=12, decimal_places=2, null=True, blank=True)
    created_by = models.CharField('记录人', max_length=80, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']


class ResourceRequest(models.Model):
    ENV_CHOICES = [('prod', '生产'), ('test', '测试'), ('dev', '开发')]
    PRIORITY_CHOICES = [('low', '低'), ('medium', '中'), ('high', '高'), ('urgent', '紧急')]
    STATUS_CHOICES = [
        ('pending', '待审批'),
        ('approved', '已批准'),
        ('provisioning', '交付中'),
        ('failed', '交付失败'),
        ('rejected', '已拒绝'),
        ('completed', '已完成'),
    ]

    title = models.CharField("申请标题", max_length=120, blank=True, default='')
    applicant = models.CharField("申请人", max_length=50)
    approver = models.CharField("审批人", max_length=50, blank=True, default='')
    resource_type = models.CharField("资源类型", max_length=50)
    specification = models.CharField("规格说明", max_length=200, blank=True, default='')
    business_line = models.CharField("业务线", max_length=50, blank=True, default='')
    environment = models.CharField("环境", max_length=20, choices=ENV_CHOICES, blank=True, default='')
    priority = models.CharField("优先级", max_length=16, choices=PRIORITY_CHOICES, default='medium')
    quantity = models.PositiveIntegerField("数量", default=1)
    specs = models.JSONField("规格要求", default=dict, blank=True)
    reason = models.TextField("申请理由")
    approval_comment = models.TextField("审批说明", blank=True, default='')
    fulfillment_note = models.TextField("交付说明", blank=True, default='')
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_at = models.DateTimeField("审批时间", null=True, blank=True)
    completed_at = models.DateTimeField("完成时间", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ResourceNode(models.Model):
    NODE_TYPE_CHOICES = [
        ('biz', '业务线'),
        ('env', '环境'),
        ('cloud_account', '云账号'),
        ('cloud_region', '云地域'),
        ('cloud_cluster', '云集群'),
        ('cloud_host', '云宿主机'),
    ]

    name = models.CharField("节点名称", max_length=100)
    node_type = models.CharField("节点类型", max_length=20, choices=NODE_TYPE_CHOICES)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    sort_order = models.IntegerField("排序", default=0)
    is_synced = models.BooleanField("同步来源节点", default=False)

    def __str__(self):
        return self.name
