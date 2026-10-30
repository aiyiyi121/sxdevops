import base64
import hashlib
import uuid

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone


User = get_user_model()


def _build_fernet():
    seed = f"{settings.SECRET_KEY}:aiops:model-provider".encode('utf-8')
    key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
    return Fernet(key)


class AIOpsModelProvider(models.Model):
    PROVIDER_OPENAI_COMPATIBLE = 'openai_compatible'
    PROVIDER_CHOICES = [
        (PROVIDER_OPENAI_COMPATIBLE, 'OpenAI Compatible'),
    ]
    CURRENCY_USD = 'USD'
    CURRENCY_CNY = 'CNY'
    CURRENCY_CHOICES = [
        (CURRENCY_USD, 'USD'),
        (CURRENCY_CNY, 'CNY'),
    ]

    STATUS_UNKNOWN = 'unknown'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_UNKNOWN, '未知'),
        (STATUS_SUCCESS, '成功'),
        (STATUS_FAILED, '失败'),
    ]

    name = models.CharField('提供商名称', max_length=128, unique=True)
    provider_type = models.CharField('提供商类型', max_length=32, choices=PROVIDER_CHOICES, default=PROVIDER_OPENAI_COMPATIBLE)
    base_url = models.CharField('Base URL', max_length=255, blank=True, default='')
    provider_preset = models.CharField('供应商预设', max_length=64, blank=True, default='')
    api_key_encrypted = models.TextField('API Key 密文', blank=True, default='')
    default_model = models.CharField('默认模型', max_length=128, blank=True, default='')
    backup_model = models.CharField('备用模型', max_length=128, blank=True, default='')
    temperature = models.FloatField('温度', default=0.2)
    max_tokens = models.PositiveIntegerField('最大 Tokens', default=10000)
    timeout_seconds = models.PositiveIntegerField('超时(秒)', default=30)
    price_currency = models.CharField('计费币种', max_length=3, choices=CURRENCY_CHOICES, default=CURRENCY_USD)
    input_token_price_per_1m = models.DecimalField('输入 Token 单价/百万', max_digits=10, decimal_places=6, default=0)
    output_token_price_per_1m = models.DecimalField('输出 Token 单价/百万', max_digits=10, decimal_places=6, default=0)
    is_enabled = models.BooleanField('启用', default=True)
    last_test_status = models.CharField('最近测试状态', max_length=16, choices=STATUS_CHOICES, default=STATUS_UNKNOWN)
    last_test_message = models.CharField('最近测试信息', max_length=255, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'AIOps 模型提供商'
        verbose_name_plural = 'AIOps 模型提供商'

    def __str__(self):
        return self.name

    @property
    def has_api_key(self):
        return bool(self.api_key_encrypted)

    def set_api_key(self, value):
        value = (value or '').strip()
        if not value:
            self.api_key_encrypted = ''
            return
        self.api_key_encrypted = _build_fernet().encrypt(value.encode('utf-8')).decode('utf-8')

    def get_api_key(self):
        if not self.api_key_encrypted:
            return ''
        try:
            return _build_fernet().decrypt(self.api_key_encrypted.encode('utf-8')).decode('utf-8')
        except (InvalidToken, TypeError, ValueError):
            return ''


def default_capability_codes():
    return ['troubleshoot', 'event.analysis', 'log.query_generate', 'slo.analysis', 'host_task.generate', 'cmdb']


class AIOpsAgentConfig(models.Model):
    name = models.CharField('配置名称', max_length=64, default='default', unique=True)
    default_provider = models.ForeignKey(
        AIOpsModelProvider,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_configs',
        verbose_name='默认模型提供商',
    )
    system_prompt = models.TextField('系统提示词', blank=True, default='')
    welcome_message = models.CharField('欢迎语', max_length=255, blank=True, default='你好，我可以帮你结合平台上下文查询资源、根因分析、生成待执行任务等。')
    suggested_questions = models.JSONField('建议问题', default=list, blank=True)
    is_enabled = models.BooleanField('启用机器人', default=True)
    allow_action_execution = models.BooleanField('允许生成待执行任务', default=True)
    require_confirmation = models.BooleanField('任务中心确认', default=True)
    show_evidence = models.BooleanField('展示证据来源', default=True)
    allow_analysis = models.BooleanField('允许关联分析', default=True)
    enabled_capability_codes = models.JSONField('启用的问答类型', default=default_capability_codes, blank=True)
    enabled_mcp_server_ids = models.JSONField('启用的 MCP', default=list, blank=True)
    enabled_skill_ids = models.JSONField('启用的 Skill', default=list, blank=True)
    max_history_messages = models.PositiveIntegerField('最大历史消息数', default=12)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = 'AIOps 机器人配置'
        verbose_name_plural = 'AIOps 机器人配置'

    def __str__(self):
        return self.name


class AIOpsMCPServer(models.Model):
    SERVER_HTTP = 'http'
    SERVER_STDIO = 'stdio'
    SERVER_PLATFORM_BUILTIN = 'platform_builtin'
    SERVER_TYPE_CHOICES = [
        (SERVER_HTTP, 'HTTP'),
        (SERVER_STDIO, 'STDIO'),
        (SERVER_PLATFORM_BUILTIN, '平台内置'),
    ]

    name = models.CharField('名称', max_length=128, unique=True)
    server_type = models.CharField('类型', max_length=16, choices=SERVER_TYPE_CHOICES, default=SERVER_HTTP)
    endpoint_or_command = models.CharField('地址或命令', max_length=255, blank=True, default='')
    description = models.CharField('描述', max_length=255, blank=True, default='')
    auth_config = models.JSONField('鉴权配置', default=dict, blank=True)
    tool_whitelist = models.JSONField('启用工具', default=list, blank=True)
    is_builtin = models.BooleanField('内置', default=False)
    is_enabled = models.BooleanField('启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'AIOps MCP 服务'
        verbose_name_plural = 'AIOps MCP 服务'

    def __str__(self):
        return self.name


class AIOpsSkill(models.Model):
    SOURCE_INLINE = 'inline'
    SOURCE_LOCAL = 'local'
    RISK_READ_ONLY = 'read_only'
    RISK_DRAFT = 'draft'
    RISK_WRITE = 'write'
    RISK_EXECUTE = 'execute'
    SOURCE_CHOICES = [
        (SOURCE_INLINE, '平台内置'),
        (SOURCE_LOCAL, '本地文件'),
    ]
    RISK_CHOICES = [
        (RISK_READ_ONLY, '只读'),
        (RISK_DRAFT, '草稿'),
        (RISK_WRITE, '写入'),
        (RISK_EXECUTE, '执行'),
    ]

    name = models.CharField('名称', max_length=128, unique=True)
    slug = models.SlugField('标识', max_length=128, unique=True)
    description = models.CharField('描述', max_length=255, blank=True, default='')
    category = models.CharField('分类', max_length=64, blank=True, default='')
    applicable_actions = models.JSONField('挂载的问答类型', default=list, blank=True)
    examples = models.JSONField('示例问题', default=list, blank=True)
    builtin_tools = models.JSONField('内置工具', default=list, blank=True)
    recommended_tools = models.JSONField('推荐工具', default=list, blank=True)
    max_iterations = models.PositiveIntegerField('最大轮次', default=0)
    risk_level = models.CharField('风险等级', max_length=16, choices=RISK_CHOICES, default=RISK_READ_ONLY)
    output_contract = models.JSONField('输出约束', default=dict, blank=True)
    source_type = models.CharField('来源类型', max_length=16, choices=SOURCE_CHOICES, default=SOURCE_INLINE)
    content = models.TextField('内容', blank=True, default='')
    allowed_role_codes = models.JSONField('允许角色', default=list, blank=True)
    is_builtin = models.BooleanField('内置', default=False)
    is_enabled = models.BooleanField('启用', default=True)
    builtin_version = models.PositiveSmallIntegerField('内置目录版本', default=0, editable=False)
    merged_into = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True,
        related_name='merged_sources', verbose_name='已合并到', editable=False,
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'AIOps Skill'
        verbose_name_plural = 'AIOps Skill'

    def __str__(self):
        return self.name


class AIOpsKnowledgeEnvironment(models.Model):
    name = models.CharField('知识图谱环境名', max_length=128, unique=True)
    aliases = models.JSONField('环境别名', default=list, blank=True)
    description = models.CharField('描述', max_length=255, blank=True, default='')
    event_environments = models.JSONField('事件中心环境', default=list, blank=True)
    grafana_folder_keys = models.JSONField('监控看板目录', default=list, blank=True)
    metric_datasource_ids = models.JSONField('指标数据源', default=list, blank=True)
    log_datasource_ids = models.JSONField('日志中心数据源', default=list, blank=True)
    tracing_datasource_ids = models.JSONField('链路追踪数据源', default=list, blank=True)
    observability_link_ids = models.JSONField('可观测性关联配置', default=list, blank=True)
    alert_environments = models.JSONField('告警中心环境', default=list, blank=True)
    posture_environments = models.JSONField('系统态势环境', default=list, blank=True)
    k8s_cluster_ids = models.JSONField('K8s 集群', default=list, blank=True)
    k8s_namespaces = models.JSONField('K8s 命名空间', default=dict, blank=True)
    docker_host_ids = models.JSONField('Docker 环境', default=list, blank=True)
    task_resource_environment_ids = models.JSONField('任务资源底座环境', default=list, blank=True)
    association_snapshot = models.JSONField('关联快照', default=dict, blank=True)
    child_node_snapshot = models.JSONField('子节点快照', default=dict, blank=True)
    snapshot_generated_at = models.DateTimeField('快照生成时间', null=True, blank=True)
    is_default = models.BooleanField('默认图谱', default=False)
    is_enabled = models.BooleanField('启用', default=True)
    created_by = models.CharField('创建人', max_length=64, blank=True, default='')
    updated_by = models.CharField('更新人', max_length=64, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['name', 'id']
        verbose_name = 'AIOps 知识图谱环境关联'
        verbose_name_plural = 'AIOps 知识图谱环境关联'

    def __str__(self):
        return self.name


class AIOpsChatSession(models.Model):
    context = models.JSONField('上下文', default=dict, blank=True)
    STATUS_ACTIVE = 'active'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, '进行中'),
        (STATUS_ARCHIVED, '已归档'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='aiops_sessions', verbose_name='用户')
    mirror_source = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mirrored_sessions',
        verbose_name='镜像来源',
    )
    title = models.CharField('标题', max_length=128, default='新会话')
    status = models.CharField('状态', max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    last_message_at = models.DateTimeField('最后消息时间', default=timezone.now)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-last_message_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['user', 'mirror_source'], name='aiops_session_user_mirror_source_uniq'),
        ]
        verbose_name = 'AIOps 会话'
        verbose_name_plural = 'AIOps 会话'

    def __str__(self):
        return f'{self.user.username} / {self.title}'


class AIOpsChatMessage(models.Model):
    ROLE_SYSTEM = 'system'
    ROLE_USER = 'user'
    ROLE_ASSISTANT = 'assistant'
    ROLE_CHOICES = [
        (ROLE_SYSTEM, '系统'),
        (ROLE_USER, '用户'),
        (ROLE_ASSISTANT, '助手'),
    ]

    TYPE_TEXT = 'text'
    TYPE_ANALYSIS = 'analysis'
    TYPE_ACTION = 'action'
    TYPE_ERROR = 'error'
    TYPE_CHOICES = [
        (TYPE_TEXT, '文本'),
        (TYPE_ANALYSIS, '分析'),
        (TYPE_ACTION, '动作'),
        (TYPE_ERROR, '错误'),
    ]

    session = models.ForeignKey(AIOpsChatSession, on_delete=models.CASCADE, related_name='messages', verbose_name='会话')
    mirror_source = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mirrored_messages',
        verbose_name='镜像来源',
    )
    role = models.CharField('角色', max_length=16, choices=ROLE_CHOICES)
    message_type = models.CharField('消息类型', max_length=16, choices=TYPE_CHOICES, default=TYPE_TEXT)
    content = models.TextField('内容')
    citations = models.JSONField('引用', default=list, blank=True)
    tool_calls = models.JSONField('工具调用', default=list, blank=True)
    metadata = models.JSONField('元数据', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [
            models.UniqueConstraint(fields=['session', 'mirror_source'], name='aiops_message_session_mirror_source_uniq'),
        ]
        verbose_name = 'AIOps 消息'
        verbose_name_plural = 'AIOps 消息'

    def __str__(self):
        return f'{self.session_id} / {self.role}'


class AIOpsChatJob(models.Model):
    STATUS_QUEUED = 'queued'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_QUEUED, '排队中'),
        (STATUS_RUNNING, '执行中'),
        (STATUS_COMPLETED, '已完成'),
        (STATUS_FAILED, '失败'),
    ]

    assistant_message = models.OneToOneField(AIOpsChatMessage, on_delete=models.CASCADE, related_name='chat_job')
    user_message = models.ForeignKey(AIOpsChatMessage, on_delete=models.CASCADE, related_name='submitted_chat_jobs')
    thread_id = models.CharField(max_length=128, unique=True)
    analysis_only = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    attempt_count = models.PositiveIntegerField(default=0)
    claim_token = models.UUIDField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at', 'id']
        indexes = [models.Index(fields=['status', 'lease_until'], name='aiops_chat_job_queue_idx')]


class AIOpsGraphNodeRun(models.Model):
    message = models.ForeignKey(AIOpsChatMessage, on_delete=models.CASCADE, related_name='graph_node_runs')
    thread_id = models.CharField(max_length=128, db_index=True)
    node = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default='running')
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    retry_count = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=500, blank=True, default='')

    class Meta:
        ordering = ['id']
        indexes = [models.Index(fields=['status', 'started_at'], name='aiops_graph_run_status_idx')]


class AIOpsPendingAction(models.Model):
    ACTION_EXECUTE_HOST_TASK = 'execute_host_task'
    ACTION_CREATE_CMDB_ASSET = 'create_cmdb_asset'
    ACTION_CHOICES = [
        (ACTION_EXECUTE_HOST_TASK, '执行主机任务'),
        (ACTION_CREATE_CMDB_ASSET, '创建 CMDB 资产'),
    ]

    RISK_LOW = 'low'
    RISK_MEDIUM = 'medium'
    RISK_HIGH = 'high'
    RISK_CRITICAL = 'critical'
    RISK_CHOICES = [
        (RISK_LOW, '低'),
        (RISK_MEDIUM, '中'),
        (RISK_HIGH, '高'),
        (RISK_CRITICAL, '极高'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELED = 'canceled'
    STATUS_EXECUTED = 'executed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, '待确认'),
        (STATUS_CONFIRMED, '已确认'),
        (STATUS_CANCELED, '已取消'),
        (STATUS_EXECUTED, '已执行'),
        (STATUS_FAILED, '执行失败'),
    ]

    session = models.ForeignKey(AIOpsChatSession, on_delete=models.CASCADE, related_name='pending_actions', verbose_name='会话')
    mirror_source = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mirrored_actions',
        verbose_name='镜像来源',
    )
    message = models.ForeignKey(
        AIOpsChatMessage,
        on_delete=models.CASCADE,
        related_name='pending_actions',
        verbose_name='消息',
        null=True,
        blank=True,
    )
    action_type = models.CharField('动作类型', max_length=32, choices=ACTION_CHOICES)
    title = models.CharField('动作标题', max_length=128, default='')
    risk_level = models.CharField('风险等级', max_length=16, choices=RISK_CHOICES, default=RISK_LOW)
    status = models.CharField('状态', max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    action_payload = models.JSONField('动作参数', default=dict, blank=True)
    result_payload = models.JSONField('执行结果', default=dict, blank=True)
    confirmed_by = models.CharField('确认人', max_length=64, blank=True, default='')
    confirmed_at = models.DateTimeField('确认时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['session', 'mirror_source'], name='aiops_action_session_mirror_source_uniq'),
        ]
        verbose_name = 'AIOps 待确认动作'
        verbose_name_plural = 'AIOps 待确认动作'

    def __str__(self):
        return f'{self.session_id} / {self.action_type}'


class AIOpsRemediationVerification(models.Model):
    STATUS_WAITING = 'waiting'
    STATUS_RUNNING = 'running'
    STATUS_PASSED = 'passed'
    STATUS_FAILED = 'failed'
    STATUS_INCONCLUSIVE = 'inconclusive'
    STATUS_CHOICES = [
        (STATUS_WAITING, '等待任务完成'),
        (STATUS_RUNNING, '验证中'),
        (STATUS_PASSED, '告警已恢复'),
        (STATUS_FAILED, '验证未通过'),
        (STATUS_INCONCLUSIVE, '证据不足'),
    ]

    action = models.OneToOneField(AIOpsPendingAction, on_delete=models.CASCADE, related_name='verification')
    task = models.OneToOneField('ops.HostTask', on_delete=models.SET_NULL, null=True, blank=True, related_name='aiops_verification')
    environment = models.ForeignKey(AIOpsKnowledgeEnvironment, on_delete=models.SET_NULL, null=True, related_name='verifications')
    thread_id = models.CharField(max_length=128, unique=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_WAITING)
    observation_seconds = models.PositiveIntegerField(default=60)
    baseline = models.JSONField(default=dict)
    evidence = models.JSONField(default=dict, blank=True)
    summary = models.CharField(max_length=500, blank=True, default='')
    is_demo = models.BooleanField(default=False)
    checkpoint_expired = models.BooleanField(default=False)
    attempt_count = models.PositiveIntegerField(default=0)
    claim_token = models.UUIDField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['status', 'lease_until'], name='aiops_verification_queue_idx')]


class AIOpsToolInvocation(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, '待处理'),
        (STATUS_SUCCESS, '成功'),
        (STATUS_FAILED, '失败'),
    ]

    session = models.ForeignKey(AIOpsChatSession, on_delete=models.CASCADE, related_name='tool_invocations', verbose_name='会话')
    message = models.ForeignKey(
        AIOpsChatMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tool_invocations',
        verbose_name='消息',
    )
    tool_name = models.CharField('工具名称', max_length=64)
    status = models.CharField('状态', max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    latency_ms = models.PositiveIntegerField('耗时', default=0)
    request_payload = models.JSONField('请求参数', default=dict, blank=True)
    response_summary = models.JSONField('响应摘要', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'AIOps 工具调用'
        verbose_name_plural = 'AIOps 工具调用'

    def __str__(self):
        return f'{self.tool_name} / {self.status}'


class AIOpsModelInvocation(models.Model):
    PURPOSE_CHAT_PLANNING = 'chat_planning'
    PURPOSE_ANSWER_FORMATTING = 'answer_formatting'
    PURPOSE_PARAMETER_EXTRACTION = 'parameter_extraction'
    PURPOSE_MODEL_PROBE = 'model_probe'
    PURPOSE_CONNECTION_TEST = 'connection_test'
    PURPOSE_CHOICES = [
        (PURPOSE_CHAT_PLANNING, '聊天规划'),
        (PURPOSE_ANSWER_FORMATTING, '回答整形'),
        (PURPOSE_PARAMETER_EXTRACTION, '参数抽取'),
        (PURPOSE_MODEL_PROBE, '模型探测'),
        (PURPOSE_CONNECTION_TEST, '连接测试'),
    ]

    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_SUCCESS, '成功'),
        (STATUS_FAILED, '失败'),
    ]

    provider = models.ForeignKey(
        AIOpsModelProvider,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='model_invocations',
        verbose_name='模型提供商',
    )
    session = models.ForeignKey(
        AIOpsChatSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='model_invocations',
        verbose_name='会话',
    )
    message = models.ForeignKey(
        AIOpsChatMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='model_invocations',
        verbose_name='消息',
    )
    username = models.CharField('用户', max_length=64, blank=True, default='')
    purpose = models.CharField('调用目的', max_length=32, choices=PURPOSE_CHOICES, default=PURPOSE_CHAT_PLANNING)
    requested_model = models.CharField('请求模型', max_length=128, blank=True, default='')
    resolved_model = models.CharField('实际模型', max_length=128, blank=True, default='')
    status = models.CharField('状态', max_length=16, choices=STATUS_CHOICES, default=STATUS_SUCCESS)
    latency_ms = models.PositiveIntegerField('耗时', default=0)
    prompt_tokens = models.PositiveIntegerField('输入 Token', default=0)
    completion_tokens = models.PositiveIntegerField('输出 Token', default=0)
    total_tokens = models.PositiveIntegerField('总 Token', default=0)
    estimated_cost_usd = models.DecimalField('预估费用 USD', max_digits=12, decimal_places=6, default=0)
    estimated_cost_currency = models.CharField('预估费用币种', max_length=3, choices=AIOpsModelProvider.CURRENCY_CHOICES, default=AIOpsModelProvider.CURRENCY_USD)
    request_summary = models.JSONField('请求摘要', default=dict, blank=True)
    response_summary = models.JSONField('响应摘要', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'AIOps 模型调用'
        verbose_name_plural = 'AIOps 模型调用'

    def __str__(self):
        return f'{self.resolved_model or self.requested_model} / {self.status}'


class AIOpsExternalTask(models.Model):
    STATUS_QUEUED = 'queued'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELED = 'canceled'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_QUEUED, '排队中'),
        (STATUS_RUNNING, '执行中'),
        (STATUS_COMPLETED, '已完成'),
        (STATUS_CANCELED, '已取消'),
        (STATUS_FAILED, '失败'),
    ]

    public_id = models.UUIDField('外部任务 ID', default=uuid.uuid4, unique=True, editable=False)
    source_agent = models.CharField('来源 Agent', max_length=128, blank=True, default='')
    title = models.CharField('任务标题', max_length=128, default='AIOps 外部任务')
    action_code = models.CharField('Action', max_length=64, blank=True, default='')
    agent_mode = models.CharField('Agent 模式', max_length=32, blank=True, default='')
    status = models.CharField('状态', max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    input_payload = models.JSONField('输入参数', default=dict, blank=True)
    plan_steps = models.JSONField('计划步骤', default=list, blank=True)
    orchestration_state = models.JSONField('编排状态', default=dict, blank=True)
    agent_results = models.JSONField('Agent 结果', default=list, blank=True)
    react_trace = models.JSONField('ReAct 轨迹', default=list, blank=True)
    result_payload = models.JSONField('结果', default=dict, blank=True)
    error_message = models.CharField('错误信息', max_length=255, blank=True, default='')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='aiops_external_tasks', verbose_name='创建人')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)
    canceled_at = models.DateTimeField('取消时间', null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'AIOps A2A 外部任务'
        verbose_name_plural = 'AIOps A2A 外部任务'

    def __str__(self):
        return f'{self.public_id} / {self.action_code or self.title}'


class AIOpsRunbook(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = [
        (STATUS_DRAFT, '草稿'),
        (STATUS_PUBLISHED, '已发布'),
        (STATUS_ARCHIVED, '已归档'),
    ]

    title = models.CharField('标题', max_length=160)
    slug = models.SlugField('标识', max_length=160, unique=True)
    environment = models.CharField('环境', max_length=128, blank=True, default='')
    service = models.CharField('服务', max_length=128, blank=True, default='')
    status = models.CharField('状态', max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    version = models.PositiveIntegerField('当前版本', default=1)
    content = models.TextField('内容', blank=True, default='')
    evidence = models.JSONField('证据', default=list, blank=True)
    tags = models.JSONField('标签', default=list, blank=True)
    source_refs = models.JSONField('引用来源', default=list, blank=True)
    source_task = models.ForeignKey(AIOpsExternalTask, on_delete=models.SET_NULL, null=True, blank=True, related_name='runbooks', verbose_name='来源任务')
    source_session = models.ForeignKey(AIOpsChatSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='runbooks', verbose_name='来源会话')
    created_by = models.CharField('创建人', max_length=64, blank=True, default='')
    updated_by = models.CharField('更新人', max_length=64, blank=True, default='')
    published_at = models.DateTimeField('发布时间', null=True, blank=True)
    archived_at = models.DateTimeField('归档时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        verbose_name = 'AIOps Runbook'
        verbose_name_plural = 'AIOps Runbook'

    def __str__(self):
        return self.title


class AIOpsRunbookVersion(models.Model):
    runbook = models.ForeignKey(AIOpsRunbook, on_delete=models.CASCADE, related_name='versions', verbose_name='Runbook')
    version = models.PositiveIntegerField('版本号')
    status = models.CharField('状态', max_length=16, choices=AIOpsRunbook.STATUS_CHOICES, default=AIOpsRunbook.STATUS_DRAFT)
    title = models.CharField('标题', max_length=160)
    content = models.TextField('内容', blank=True, default='')
    evidence = models.JSONField('证据', default=list, blank=True)
    tags = models.JSONField('标签', default=list, blank=True)
    source_refs = models.JSONField('引用来源', default=list, blank=True)
    change_note = models.CharField('变更说明', max_length=255, blank=True, default='')
    created_by = models.CharField('创建人', max_length=64, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        ordering = ['-version', '-id']
        constraints = [
            models.UniqueConstraint(fields=['runbook', 'version'], name='aiops_runbook_version_uniq'),
        ]
        verbose_name = 'AIOps Runbook 版本'
        verbose_name_plural = 'AIOps Runbook 版本'

    def __str__(self):
        return f'{self.runbook_id} / v{self.version}'


class AIOpsReviewKnowledge(models.Model):
    SOURCE_SESSION = 'session'
    SOURCE_TASK = 'task'
    SOURCE_RUNBOOK = 'runbook'
    SOURCE_MANUAL = 'manual'
    SOURCE_CHOICES = [
        (SOURCE_SESSION, '会话'),
        (SOURCE_TASK, '协同任务'),
        (SOURCE_RUNBOOK, 'Runbook'),
        (SOURCE_MANUAL, '手动'),
    ]

    slug = models.SlugField('标识', max_length=160, unique=True)
    title = models.CharField('标题', max_length=160)
    summary = models.TextField('复盘摘要', blank=True, default='')
    environment = models.CharField('环境', max_length=128, blank=True, default='')
    service = models.CharField('服务', max_length=128, blank=True, default='')
    source_type = models.CharField('来源类型', max_length=16, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    evidence = models.JSONField('证据', default=list, blank=True)
    tags = models.JSONField('标签', default=list, blank=True)
    source_refs = models.JSONField('引用来源', default=list, blank=True)
    source_session = models.ForeignKey(AIOpsChatSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='review_knowledge_items', verbose_name='来源会话')
    source_task = models.ForeignKey(AIOpsExternalTask, on_delete=models.SET_NULL, null=True, blank=True, related_name='review_knowledge_items', verbose_name='来源任务')
    source_runbook = models.ForeignKey(AIOpsRunbook, on_delete=models.SET_NULL, null=True, blank=True, related_name='review_knowledge_items', verbose_name='来源 Runbook')
    created_by = models.CharField('创建人', max_length=64, blank=True, default='')
    updated_by = models.CharField('更新人', max_length=64, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        verbose_name = 'AIOps 复盘知识'
        verbose_name_plural = 'AIOps 复盘知识'

    def __str__(self):
        return self.title
