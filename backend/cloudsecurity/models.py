from django.conf import settings
from django.db import models


class InternalPlatformSecurityControl(models.Model):
    PLATFORM_CHOICES = [
        ('archery', 'Archery'),
        ('registry', '镜像仓库 / Nexus'),
        ('jenkins', 'Jenkins'),
        ('kubernetes', 'Kubernetes'),
        ('nacos', 'Nacos'),
        ('third_party', '第三方服务账号'),
        ('aliyun', '阿里云账号'),
    ]

    platform = models.CharField('平台', max_length=32, choices=PLATFORM_CHOICES)
    scope = models.CharField('适用范围', max_length=160)
    title = models.CharField('控制项', max_length=160)
    requirement = models.TextField('控制要求')
    evidence_requirement = models.TextField('留痕与复核要求')
    sort_order = models.PositiveIntegerField('排序', default=0)
    enabled = models.BooleanField('启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['sort_order', 'platform', 'id']
        verbose_name = '内部平台安全控制项'
        verbose_name_plural = '内部平台安全控制项'

    def __str__(self):
        return f'{self.get_platform_display()} - {self.title}'


class InternalPlatformSecurityFinding(models.Model):
    TYPE_RECTIFICATION = 'rectification'
    TYPE_MONTHLY_REVIEW = 'monthly_review'
    TYPE_CHOICES = [
        (TYPE_RECTIFICATION, '整改项'),
        (TYPE_MONTHLY_REVIEW, '月度复核'),
    ]
    SEVERITY_CHOICES = [
        ('critical', '严重'),
        ('high', '高'),
        ('medium', '中'),
        ('low', '低'),
    ]
    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_PENDING_REVIEW = 'pending_review'
    STATUS_CLOSED = 'closed'
    STATUS_IGNORED = 'ignored'
    STATUS_CHOICES = [
        (STATUS_PENDING, '待处理'),
        (STATUS_IN_PROGRESS, '整改中'),
        (STATUS_PENDING_REVIEW, '待复核'),
        (STATUS_CLOSED, '已关闭'),
        (STATUS_IGNORED, '已忽略'),
    ]

    control = models.ForeignKey(
        InternalPlatformSecurityControl,
        verbose_name='关联控制项',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='findings',
    )
    finding_type = models.CharField('类型', max_length=24, choices=TYPE_CHOICES, default=TYPE_RECTIFICATION)
    platform = models.CharField('平台', max_length=32, choices=InternalPlatformSecurityControl.PLATFORM_CHOICES)
    scope = models.CharField('影响范围', max_length=160, blank=True, default='')
    title = models.CharField('标题', max_length=200)
    description = models.TextField('问题描述', blank=True, default='')
    severity = models.CharField('严重程度', max_length=16, choices=SEVERITY_CHOICES, default='medium')
    status = models.CharField('状态', max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING)
    owner = models.CharField('责任人', max_length=80, blank=True, default='')
    due_date = models.DateField('截止日期', null=True, blank=True)
    ticket_ref = models.CharField('工单号或链接', max_length=200, blank=True, default='')
    evidence = models.TextField('证据或复核说明', blank=True, default='')
    created_by = models.CharField('创建人', max_length=150, blank=True, default='')
    closed_by = models.CharField('关闭人', max_length=150, blank=True, default='')
    closed_at = models.DateTimeField('关闭时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['status', 'due_date', '-updated_at', '-id']
        verbose_name = '内部平台安全整改项'
        verbose_name_plural = '内部平台安全整改项'

    def __str__(self):
        return self.title


class InternalPlatformSecurityActivity(models.Model):
    finding = models.ForeignKey(
        InternalPlatformSecurityFinding,
        verbose_name='整改项',
        on_delete=models.CASCADE,
        related_name='activities',
    )
    action = models.CharField('动作', max_length=40)
    message = models.TextField('说明', blank=True, default='')
    actor = models.CharField('操作人', max_length=150, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = '内部平台安全整改记录'
        verbose_name_plural = '内部平台安全整改记录'


class InternalSecurityAsset(models.Model):
    SOURCE_ALIYUN = 'aliyun'
    SOURCE_VSPHERE = 'vsphere'
    SOURCE_CMDB = 'cmdb'
    SOURCE_CHOICES = [
        (SOURCE_ALIYUN, '阿里云 ECS'),
        (SOURCE_VSPHERE, '机房 vSphere'),
        (SOURCE_CMDB, 'CMDB 主机'),
    ]
    AGENT_ONLINE = 'online'
    AGENT_OFFLINE = 'offline'
    AGENT_PENDING = 'pending'
    AGENT_CHOICES = [
        (AGENT_ONLINE, '防护中'),
        (AGENT_OFFLINE, '离线'),
        (AGENT_PENDING, '待接入'),
    ]
    RISK_CLEAN = 'clean'
    RISK_LOW = 'low'
    RISK_MEDIUM = 'medium'
    RISK_HIGH = 'high'
    RISK_CRITICAL = 'critical'
    RISK_CHOICES = [
        (RISK_CLEAN, '无风险'),
        (RISK_LOW, '低风险'),
        (RISK_MEDIUM, '中风险'),
        (RISK_HIGH, '高风险'),
        (RISK_CRITICAL, '严重风险'),
    ]

    source = models.CharField('资产来源', max_length=20, choices=SOURCE_CHOICES, default=SOURCE_CMDB)
    source_id = models.CharField('来源资产 ID', max_length=128, blank=True, default='')
    name = models.CharField('主机名称', max_length=128)
    ip_address = models.GenericIPAddressField('IP 地址', null=True, blank=True)
    os_name = models.CharField('操作系统', max_length=128, blank=True, default='')
    environment = models.CharField('环境', max_length=32, blank=True, default='')
    business_line = models.CharField('业务系统', max_length=80, blank=True, default='')
    agent_status = models.CharField('Agent 状态', max_length=16, choices=AGENT_CHOICES, default=AGENT_PENDING)
    risk_level = models.CharField('风险等级', max_length=16, choices=RISK_CHOICES, default=RISK_CLEAN)
    last_seen_at = models.DateTimeField('最近心跳', null=True, blank=True)
    last_scan_at = models.DateTimeField('最近扫描', null=True, blank=True)
    is_enabled = models.BooleanField('是否启用', default=True)
    tags = models.JSONField('标签', default=list, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-risk_level', 'name', 'id']
        indexes = [
            models.Index(fields=['source', 'agent_status'], name='cloudsec_asset_src_agent'),
            models.Index(fields=['risk_level', 'updated_at'], name='cloudsec_asset_risk_upd'),
        ]
        verbose_name = '内部安全资产'
        verbose_name_plural = '内部安全资产'

    def __str__(self):
        return self.name


class InternalSecurityThreat(models.Model):
    TYPE_MALWARE = 'malware'
    TYPE_RANSOMWARE = 'ransomware'
    TYPE_SUSPICIOUS_SCRIPT = 'suspicious_script'
    TYPE_WEBSHELL = 'webshell'
    TYPE_CRYPTO_MINER = 'crypto_miner'
    TYPE_BRUTE_FORCE = 'brute_force'
    THREAT_TYPE_CHOICES = [
        (TYPE_MALWARE, '恶意文件'),
        (TYPE_RANSOMWARE, '勒索行为'),
        (TYPE_SUSPICIOUS_SCRIPT, '可疑脚本'),
        (TYPE_WEBSHELL, 'WebShell'),
        (TYPE_CRYPTO_MINER, '挖矿程序'),
        (TYPE_BRUTE_FORCE, '暴力破解'),
    ]
    SEVERITY_CHOICES = [
        ('critical', '严重'),
        ('high', '高'),
        ('medium', '中'),
        ('low', '低'),
    ]
    STATUS_OPEN = 'open'
    STATUS_PROCESSING = 'processing'
    STATUS_ISOLATED = 'isolated'
    STATUS_RESOLVED = 'resolved'
    STATUS_IGNORED = 'ignored'
    STATUS_CHOICES = [
        (STATUS_OPEN, '待处理'),
        (STATUS_PROCESSING, '处理中'),
        (STATUS_ISOLATED, '已隔离'),
        (STATUS_RESOLVED, '已解决'),
        (STATUS_IGNORED, '已忽略'),
    ]

    asset = models.ForeignKey(
        InternalSecurityAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='threats',
        verbose_name='关联资产',
    )
    source = models.CharField('检测来源', max_length=24, default='agent')
    threat_type = models.CharField('威胁类型', max_length=24, choices=THREAT_TYPE_CHOICES)
    title = models.CharField('威胁标题', max_length=200)
    severity = models.CharField('风险等级', max_length=16, choices=SEVERITY_CHOICES, default='medium')
    status = models.CharField('处理状态', max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN)
    description = models.TextField('威胁描述', blank=True, default='')
    process_path = models.CharField('进程或文件路径', max_length=255, blank=True, default='')
    command_line = models.TextField('命令行', blank=True, default='')
    file_hash = models.CharField('文件哈希', max_length=128, blank=True, default='')
    remote_ip = models.GenericIPAddressField('关联远端 IP', null=True, blank=True)
    suggestion = models.TextField('处置建议', blank=True, default='')
    owner = models.CharField('责任人', max_length=80, blank=True, default='')
    ticket_ref = models.CharField('关联工单', max_length=160, blank=True, default='')
    detected_at = models.DateTimeField('发现时间')
    resolved_at = models.DateTimeField('解决时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['status', '-severity', '-detected_at', '-id']
        indexes = [
            models.Index(fields=['status', 'severity'], name='cloudsec_threat_status_sev'),
            models.Index(fields=['threat_type', 'detected_at'], name='cloudsec_threat_type_time'),
        ]
        verbose_name = '主机安全威胁'
        verbose_name_plural = '主机安全威胁'

    def __str__(self):
        return self.title


class InternalSecurityThreatActivity(models.Model):
    ACTION_CHOICES = [
        ('progress', '标记处理中'),
        ('isolate', '隔离主机'),
        ('resolve', '确认解决'),
        ('ignore', '忽略误报'),
        ('reopen', '重新打开'),
    ]

    threat = models.ForeignKey(
        InternalSecurityThreat,
        on_delete=models.CASCADE,
        related_name='activities',
        verbose_name='威胁事件',
    )
    action = models.CharField('处置动作', max_length=24, choices=ACTION_CHOICES)
    from_status = models.CharField('原状态', max_length=16, choices=InternalSecurityThreat.STATUS_CHOICES)
    to_status = models.CharField('新状态', max_length=16, choices=InternalSecurityThreat.STATUS_CHOICES)
    message = models.TextField('处置说明', blank=True, default='')
    actor = models.CharField('操作人', max_length=150, blank=True, default='')
    created_at = models.DateTimeField('操作时间', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['threat', 'created_at'], name='cloudsec_threat_act_time')]
        verbose_name = '主机威胁处置记录'
        verbose_name_plural = '主机威胁处置记录'


class SoftwareSecurityItem(models.Model):
    DEPLOYMENT_SELF_HOSTED = 'self_hosted'
    DEPLOYMENT_ALIYUN = 'aliyun'
    DEPLOYMENT_BASE_IMAGE = 'base_image'
    DEPLOYMENT_CHOICES = [
        (DEPLOYMENT_SELF_HOSTED, '自建'),
        (DEPLOYMENT_ALIYUN, '阿里云'),
        (DEPLOYMENT_BASE_IMAGE, '基础镜像'),
    ]
    NECESSITY_REQUIRED = 'required'
    NECESSITY_RECOMMENDED = 'recommended'
    NECESSITY_NOT_NEEDED = 'not_needed'
    NECESSITY_CHOICES = [
        (NECESSITY_REQUIRED, '必要'),
        (NECESSITY_RECOMMENDED, '建议'),
        (NECESSITY_NOT_NEEDED, '暂不必要'),
    ]
    PRIORITY_CHOICES = [('P0', 'P0'), ('P1', 'P1'), ('P2', 'P2'), ('P3', 'P3')]
    STATUS_OPEN = 'open'
    STATUS_PLANNED = 'planned'
    STATUS_ACCEPTED = 'accepted'
    STATUS_DONE = 'done'
    STATUS_CHOICES = [
        (STATUS_OPEN, '待治理'),
        (STATUS_PLANNED, '已排期'),
        (STATUS_ACCEPTED, '风险接受'),
        (STATUS_DONE, '已完成'),
    ]

    row_number = models.PositiveIntegerField('表格序号', unique=True)
    deployment_type = models.CharField('部署形态', max_length=20, choices=DEPLOYMENT_CHOICES)
    software_name = models.CharField('软件或服务', max_length=160)
    latest_version = models.CharField('目标版本', max_length=160, blank=True, default='')
    current_version = models.CharField('当前版本', max_length=160, blank=True, default='')
    other_versions = models.CharField('其他环境版本', max_length=160, blank=True, default='')
    risk_summary = models.TextField('当前风险', blank=True, default='')
    upgrade_advice = models.TextField('升级建议', blank=True, default='')
    upgrade_necessity = models.CharField('升级必要性', max_length=20, choices=NECESSITY_CHOICES, default=NECESSITY_NOT_NEEDED)
    priority = models.CharField('优先级', max_length=2, choices=PRIORITY_CHOICES, default='P3')
    bug_advice = models.TextField('重大 Bug 与规避提醒', blank=True, default='')
    owner_feedback = models.TextField('负责人反馈', blank=True, default='')
    plan_time = models.CharField('升级计划', max_length=80, blank=True, default='')
    status = models.CharField('治理状态', max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN)
    last_reviewed_at = models.DateTimeField('最近评估', null=True, blank=True)
    is_active = models.BooleanField('是否启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['priority', 'software_name', 'id']
        indexes = [
            models.Index(fields=['priority', 'upgrade_necessity'], name='cloudsec_sw_prio_need'),
            models.Index(fields=['deployment_type', 'status'], name='cloudsec_sw_type_status'),
        ]
        verbose_name = '软件安全版本项'
        verbose_name_plural = '软件安全版本项'

    def __str__(self):
        return self.software_name
