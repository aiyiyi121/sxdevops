"""Frozen built-in Skill catalog and legacy defaults for the v1 consolidation.

Keep this version stable: the 0024 data migration depends on these snapshots.
"""

from copy import deepcopy

from django.db import transaction


CATALOG_VERSION = 2
CAPABILITY_CODES = ('troubleshoot', 'event.analysis', 'log.query_generate', 'slo.analysis', 'host_task.generate', 'cmdb')
LEGACY_CAPABILITY_ALIASES = {
    'alert.root_cause': 'troubleshoot',
    'k8s.diagnose': 'troubleshoot',
    'self_heal.recommend': 'troubleshoot',
    'change.correlation': 'event.analysis',
}


LEGACY_BUILTIN_SKILLS = [
    {
        'name': 'CMDB 资产与成本分析',
        'slug': 'sx-cmdb-asset-cost-analysis',
        'category': '资产治理',
        'description': '基于用户可见资产范围组织资产盘点、成本洞察、拓扑影响和数据质量分析。',
        'source_type': 'inline',
        'applicable_actions': [],
        'examples': [
            '查询当前 CMDB 资产总量和闲置资产',
            '查询生产环境云主机，再查看其中一台的详细属性',
            '分析本月成本最高的业务和可优化资源',
            '查看订单服务关联了哪些资产',
            '分析 CMDB 数据质量风险',
            '查看未来 30 天即将到期的资产',
            '帮我新增一台云主机资产',
        ],
        'builtin_tools': [
            'query_cmdb_items',
            'query_cmdb_insights',
            'query_cost_report',
            'query_cmdb_topology',
            'query_cmdb_quality',
            'create_cmdb_asset_draft',
        ],
        'recommended_tools': ['query_recent_changes'],
        'max_iterations': 4,
        'risk_level': 'read_only',
        'output_contract': {
            'sections': ['结论', '资产或成本事实', '风险与影响', '建议动作'],
            'blocks': ['tool_trace', 'risk_notice'],
        },
        'content': """适用场景：
- CMDB 资产盘点、资产明细、负责人和状态查询。
- 基于上一轮资产结果继续追问 IP、规格、负责人、成本、到期日等属性。
- 月度成本、成本趋势、高成本资源和优化空间分析。
- 配置项上下游关系、依赖影响和数据质量风险分析。
- CMDB 概览、模型、IPAM、采集、资源申请、阈值、审计和到期提醒查询。
- 新增资产时生成动态字段表单，用户填写并确认后再写入。

取证要求：
1. 资产问题先调用 query_cmdb_items；成本问题调用 query_cost_report。
2. 依赖或影响范围问题调用 query_cmdb_topology；完整度、孤岛或治理问题调用 query_cmdb_quality。
3. 页面域查询、到期提醒和跨模块盘点调用 query_cmdb_insights。
4. 新增资产必须调用 create_cmdb_asset_draft 返回表单，未确认前不得写入。
5. 所有结果以工具返回的授权范围为准，不推测用户不可见的资产或成本。
6. 成本结论区分当前金额、历史趋势、潜在节省和建议，不把潜在节省描述为已节省。
7. CMDB 查询直接使用 CMDB 业务线和环境树节点，不依赖 AIOps 知识环境；用户未指定环境时查询全部授权资产。

输出要求：
- 先给一句结论，再列关键事实、主要风险和建议动作。
- 没有匹配数据时明确说明过滤条件和可调整的查询范围。""",
        'allowed_role_codes': [],
    },
    {
        'name': '告警证据清单',
        'slug': 'sx-alert-evidence-checklist',
        'category': '告警排障',
        'description': '规范告警根因分析的证据收集顺序、判断口径和输出结构。',
        'source_type': 'inline',
        'applicable_actions': ['alert.root_cause', 'slo.analysis', 'self_heal.recommend'],
        'examples': [
            '分析生产环境当前未恢复严重告警的根因',
            '这条告警可能影响哪些服务和依赖',
            '最近一小时 checkout 服务异常是不是告警引起的',
        ],
        'builtin_tools': ['query_alerts', 'query_alert_root_cause', 'query_alert_metrics', 'query_knowledge_graph'],
        'recommended_tools': ['query_system_posture', 'query_logs', 'query_traces', 'query_recent_changes'],
        'max_iterations': 4,
        'risk_level': 'read_only',
        'output_contract': {
            'sections': ['结论', '关键证据', '影响范围', '建议动作'],
            'blocks': ['incident_card', 'evidence_timeline', 'risk_notice'],
        },
        'content': """适用场景：
- 告警根因、告警风险、告警影响范围、告警是否需要升级等问题。
- 只负责分析和建议，不直接修改告警规则、不直接执行恢复动作。

取证顺序：
1. 先确认知识图谱环境，提取系统、服务、依赖和上下游范围。
2. 查询当前告警和历史告警，优先关注级别、状态、开始时间、持续时长、确认状态和指纹。
3. 如果有根因接口，优先读取根因候选和关联证据。
4. 按影响对象追加系统态势、日志、链路和最近变更证据。
5. 没有证据时要明确说明“暂未发现平台证据”，不能编造根因。

判断要求：
- 结论必须区分事实、推断和待验证假设。
- 根因只能基于工具事实给出置信度，不允许凭经验直接定性。
- 如果发现变更、发布、工单或事件时间线接近，要标记为候选原因而不是确定原因。

输出要求：
- 先给一句结论，再列关键证据、影响范围、建议动作。
- 建议动作只能是检查、确认、回滚评估、自愈推荐或升级处理，不直接声称已经执行。""",
        'allowed_role_codes': [],
    },
    {
        'name': 'K8s 告警排障',
        'slug': 'sx-k8s-alert-troubleshooting',
        'category': 'K8s 诊断',
        'description': '针对 K8s 相关告警组织集群、命名空间、工作负载、Pod、Event 和日志证据。',
        'source_type': 'inline',
        'applicable_actions': ['alert.root_cause', 'k8s.diagnose'],
        'examples': [
            '分析 app-prod-k8s 集群异常 Pod',
            'Deployment 副本不可用是什么原因',
            'CrashLoopBackOff 需要看哪些证据',
        ],
        'builtin_tools': ['query_k8s_cluster_summary', 'query_k8s_resources', 'query_logs', 'query_knowledge_graph'],
        'recommended_tools': ['query_alerts', 'query_system_posture', 'query_recent_changes'],
        'max_iterations': 5,
        'risk_level': 'read_only',
        'output_contract': {
            'sections': ['异常对象', 'K8s 证据', '可能原因', '处置建议'],
            'blocks': ['k8s_action', 'evidence_timeline', 'risk_notice'],
        },
        'content': """适用场景：
- K8s 集群、命名空间、工作负载、Pod、容器日志和 Event 相关异常。
- 只做只读取证和建议，不能直接执行 kubectl 写操作。

取证顺序：
1. 先确认环境对应的集群和命名空间，避免跨环境查询。
2. 查询集群摘要，获取异常工作负载、Pod 状态、资源使用和事件概览。
3. 按问题对象查询 workload、pod、event、container log。
4. 如果问题与发布或镜像相关，追加最近变更和发布记录。
5. 如果问题与业务错误相关，追加日志和链路证据。

常见判断：
- Pending 优先看资源不足、调度约束、PVC 和节点状态。
- CrashLoopBackOff 优先看容器日志、退出码、探针和配置。
- ImagePullBackOff 优先看镜像地址、凭据、仓库可达性和 tag。
- Readiness/Liveness 失败优先看探针路径、启动时间、依赖服务和资源压力。

输出要求：
- 明确异常对象、命名空间、状态、关键事件和推荐排查顺序。
- 高风险建议必须以“待确认动作”表达，不允许直接执行。""",
        'allowed_role_codes': [],
    },
    {
        'name': '回答整形器',
        'slug': 'answer-formatter',
        'category': '回答规范',
        'description': '基于工具事实重组最终回答，输出更稳定的结构化结果。',
        'source_type': 'inline',
        'applicable_actions': ['alert.root_cause', 'change.correlation', 'log.query_generate', 'k8s.diagnose', 'self_heal.recommend', 'host_task.generate'],
        'examples': ['把工具结果整理成结论、证据、建议', '将任务草稿说明成待确认动作'],
        'builtin_tools': [],
        'recommended_tools': [],
        'max_iterations': 0,
        'risk_level': 'read_only',
        'output_contract': {
            'sections': ['结论', '依据', '建议操作', '可继续查看'],
            'blocks': ['tool_trace', 'risk_notice'],
        },
        'content': """拿到工具结果后，优先整理为结论、依据、风险与建议。

要求：
- 不能脱离工具事实自由发挥。
- 如果工具没有返回证据，要明确说明证据不足。
- 如果涉及生成任务，要明确当前是任务草稿、待确认创建，还是已经在任务中心创建真实任务。
- 回答必须包含可执行的下一步，但不能声称未确认动作已经执行。
- 对告警和故障类问题，要优先保留关键事实：对象、环境、时间窗口、状态、数量、证据来源。""",
        'allowed_role_codes': [],
    },
    {
        'name': '日志模式分析',
        'slug': 'sx-log-pattern-analysis',
        'category': '日志查询',
        'description': '规范日志聚合、样本解释、错误模式归类和证据表达。',
        'source_type': 'inline',
        'applicable_actions': ['alert.root_cause', 'log.query_generate'],
        'examples': [
            '查询 order-service 最近 30 分钟 ERROR 日志',
            '登录失败日志按错误码聚合',
            '从日志里判断异常是否集中在某个 Pod',
        ],
        'builtin_tools': ['query_logs', 'query_knowledge_graph'],
        'recommended_tools': ['query_traces', 'query_alerts'],
        'max_iterations': 3,
        'risk_level': 'read_only',
        'output_contract': {
            'sections': ['查询条件', '命中概览', '错误模式', '后续建议'],
            'blocks': ['query_suggestion', 'tool_trace'],
        },
        'content': """适用场景：
- 日志查询、日志聚合、日志异常模式解释、从日志补充故障证据。

查询规范：
1. 必须携带环境和时间窗口。
2. 如果用户给出服务名，优先使用 service/app/workload 字段过滤。
3. 如果用户描述错误级别，映射到 error、warn、info 等平台可识别 level。
4. 涉及 Trace 排查时保留 trace_id、span_id、request_id 等关联字段。
5. 聚合时优先按 level、service、pod、namespace、error_code、message_pattern 分组。

分析要求：
- 日志样本只能作为证据，不能单独定性根因。
- 需要说明命中数量、样本范围、主要模式和缺失字段。
- 查询建议必须可复制，并说明每个过滤项的作用。""",
        'allowed_role_codes': [],
    },
    {
        'name': '变更影响分析',
        'slug': 'sx-change-impact-analysis',
        'category': '变更关联',
        'description': '规范发布、工单、事件与知识图谱依赖的时间线关联分析。',
        'source_type': 'inline',
        'applicable_actions': ['alert.root_cause', 'change.correlation', 'self_heal.recommend'],
        'examples': [
            '最近有哪些变更可能影响订单服务',
            '今天发布和告警时间是否接近',
            '帮我判断这个故障是否由发布引起',
        ],
        'builtin_tools': ['query_recent_changes', 'query_event_wall', 'query_knowledge_graph'],
        'recommended_tools': ['query_alerts', 'query_logs', 'query_traces'],
        'max_iterations': 4,
        'risk_level': 'read_only',
        'output_contract': {
            'sections': ['时间线', '候选变更', '影响路径', '验证建议'],
            'blocks': ['change_candidate', 'evidence_timeline', 'risk_notice'],
        },
        'content': """适用场景：
- 变更关联、发布失败诊断、变更是否导致告警或故障。

分析步骤：
1. 先确认故障或告警的开始时间，建立前后时间窗口。
2. 查询发布、工单、事件和操作记录，按时间排序。
3. 用知识图谱确认变更对象和故障对象是否存在依赖或上下游关系。
4. 如果时间接近但没有依赖关系，只能标记为弱关联。
5. 如果时间接近且依赖关系匹配，再结合日志、链路或指标判断置信度。

输出要求：
- 候选变更必须包含时间、对象、动作、操作者或来源。
- 需要给出“强关联 / 弱关联 / 暂无关联”的判断。
- 回滚建议必须说明前置验证和风险，不直接触发回滚。""",
        'allowed_role_codes': [],
    },
    {
        'name': '日志查询规范',
        'slug': 'sx-log-query-guide',
        'category': '日志查询',
        'description': '将自然语言需求转成可执行、可解释、可复制的日志查询条件。',
        'source_type': 'inline',
        'applicable_actions': ['log.query_generate', 'alert.root_cause'],
        'examples': [
            '帮我生成订单服务错误日志查询',
            '查询最近一小时支付失败日志',
            '按 trace_id 过滤链路相关日志',
        ],
        'builtin_tools': ['query_logs', 'query_knowledge_graph'],
        'recommended_tools': [],
        'max_iterations': 2,
        'risk_level': 'draft',
        'output_contract': {
            'sections': ['查询语句', '过滤条件', '字段说明', '使用建议'],
            'blocks': ['query_suggestion'],
        },
        'content': """适用场景：
- 用户要求生成日志查询、解释日志字段、给出过滤条件。

生成规则：
1. 明确环境、服务、级别、时间范围、关键词和字段过滤。
2. 查询语句必须避免过宽范围；缺少环境或时间窗口时要求补充。
3. 优先输出平台可执行参数，其次输出通用 LogQL/SQL-like 参考。
4. 对每个条件说明目的，例如缩小服务、限定错误级别、关联 trace。
5. 不要把查询生成说成已经完成排障。""",
        'allowed_role_codes': [],
    },
    {
        'name': '日志字段字典',
        'slug': 'sx-log-field-dictionary',
        'category': '日志查询',
        'description': '沉淀日志字段含义和跨工具关联字段，提升查询生成稳定性。',
        'source_type': 'inline',
        'applicable_actions': ['log.query_generate', 'alert.root_cause', 'k8s.diagnose'],
        'examples': ['service 字段怎么过滤', 'trace_id 和 request_id 怎么关联', 'namespace 和 pod 字段怎么用'],
        'builtin_tools': ['query_logs'],
        'recommended_tools': ['query_knowledge_graph'],
        'max_iterations': 0,
        'risk_level': 'read_only',
        'output_contract': {
            'sections': ['字段说明', '关联方式', '查询建议'],
            'blocks': ['query_suggestion'],
        },
        'content': """常用字段：
- environment：环境范围，必须从知识图谱或页面上下文确认。
- service/app/workload：业务服务或工作负载名称，用于限定对象。
- level/severity：日志级别，常见值为 error、warn、info、debug。
- trace_id/span_id/request_id：链路与请求关联字段。
- namespace/pod/container/node：K8s 维度字段。
- message/error/error_code：错误内容或错误码字段。

使用要求：
- 字段不存在时要说明需要确认数据源字段映射。
- 不同数据源字段名可能不同，优先使用平台返回的字段字典或样本字段。
- 不能凭空假设所有日志都有 trace_id。""",
        'allowed_role_codes': [],
    },
    {
        'name': 'K8s 排障 SOP',
        'slug': 'sx-k8s-troubleshooting',
        'category': 'K8s 诊断',
        'description': '沉淀 K8s 常见异常的只读排障路径和输出格式。',
        'source_type': 'inline',
        'applicable_actions': ['k8s.diagnose', 'alert.root_cause'],
        'examples': ['Pod Pending 怎么排查', '探针失败如何判断', '节点资源不足会影响哪些服务'],
        'builtin_tools': ['query_k8s_cluster_summary', 'query_k8s_resources', 'query_logs'],
        'recommended_tools': ['query_alerts', 'query_knowledge_graph'],
        'max_iterations': 5,
        'risk_level': 'read_only',
        'output_contract': {
            'sections': ['现象', '证据', '原因判断', '建议'],
            'blocks': ['k8s_action', 'evidence_timeline'],
        },
        'content': """排障路径：
- Pod Pending：看调度事件、资源请求、节点 taint、亲和性、PVC。
- CrashLoopBackOff：看退出码、容器日志、启动命令、环境变量、探针。
- ImagePullBackOff：看镜像地址、tag、仓库凭据、网络连通。
- OOMKilled：看内存 limit、峰值、重启次数和近期流量。
- Probe Failed：看探针路径、超时、启动时间、依赖服务状态。

边界：
- 只读取平台接口返回的集群与日志事实。
- 不直接执行扩缩容、删除 Pod、重启工作负载、修改配置等写操作。
- 写操作只能形成建议或待确认动作。""",
        'allowed_role_codes': [],
    },
    {
        'name': '容器只读取证护栏',
        'slug': 'sx-container-readonly-guard',
        'category': '安全护栏',
        'description': '限定容器和 K8s 场景只能通过平台后端接口取证，写操作必须走确认流。',
        'source_type': 'inline',
        'applicable_actions': ['k8s.diagnose', 'self_heal.recommend'],
        'examples': ['能不能直接重启这个 Pod', '帮我扩容 Deployment', '删除异常 Pod 是否安全'],
        'builtin_tools': ['query_k8s_cluster_summary', 'query_k8s_resources', 'query_container_assets'],
        'recommended_tools': ['generate_host_task'],
        'max_iterations': 0,
        'risk_level': 'draft',
        'output_contract': {
            'sections': ['安全边界', '可执行前置条件', '确认项'],
            'blocks': ['approval_form', 'risk_notice'],
        },
        'content': """安全边界：
- assistant 不能直连集群、Docker daemon 或主机执行命令。
- 查询类问题只能调用平台后端只读工具。
- 重启、扩缩容、删除、修改配置、执行脚本都属于高风险动作，必须生成待确认动作。

输出要求：
- 对用户提出的写操作，先说明风险和需要确认的目标范围。
- 必须列出目标集群、命名空间、资源类型、资源名、影响范围和回滚方式。
- 没有 dry-run 或审批信息时，不允许建议直接执行。""",
        'allowed_role_codes': [],
    },
    {
        'name': '事件时间线关联',
        'slug': 'sx-event-timeline-correlation',
        'category': '变更关联',
        'description': '将事件墙、工单、发布、告警和知识图谱关系组织成可解释时间线。',
        'source_type': 'inline',
        'applicable_actions': ['change.correlation', 'alert.root_cause'],
        'examples': ['今天有哪些事件和告警时间接近', '把故障前后的操作整理成时间线', '找出最近发布相关事件'],
        'builtin_tools': ['query_event_wall', 'query_recent_changes', 'query_knowledge_graph'],
        'recommended_tools': ['query_alerts', 'query_logs'],
        'max_iterations': 3,
        'risk_level': 'read_only',
        'output_contract': {
            'sections': ['时间线', '关键事件', '关联判断'],
            'blocks': ['evidence_timeline', 'change_candidate'],
        },
        'content': """适用场景：
- 事件、发布、工单、操作记录与告警或故障的时间线关联。

要求：
- 时间线按发生时间排序，标明来源、动作、对象和结果。
- 只把事件作为辅助证据，不能仅凭事件存在就断定根因。
- 与知识图谱无依赖关系的事件要标为弱关联。
- 如果事件时间晚于故障发生，要优先判断它可能是处置动作而非原因。""",
        'allowed_role_codes': [],
    },
    {
        'name': '自愈风险护栏',
        'slug': 'sx-self-heal-risk-guard',
        'category': '自愈安全',
        'description': '约束自愈推荐必须先评估风险、生成 dry-run 和待确认动作。',
        'source_type': 'inline',
        'applicable_actions': ['self_heal.recommend'],
        'examples': ['推荐一个自愈方案', '这个故障适合自动恢复吗', '是否可以执行巡检脚本'],
        'builtin_tools': ['query_alerts', 'query_logs', 'query_traces', 'generate_host_task', 'query_knowledge_graph'],
        'recommended_tools': ['query_recent_changes'],
        'max_iterations': 6,
        'risk_level': 'draft',
        'output_contract': {
            'sections': ['推荐结论', '适用条件', '风险', '确认项', '回滚'],
            'blocks': ['self_heal_recommendation', 'approval_form', 'risk_notice'],
        },
        'content': """自愈原则：
- 默认只推荐，不默认执行。
- 必须基于告警、日志、链路、变更、知识图谱和历史处置证据。
- 必须输出适用条件、不适用条件、风险等级、影响范围和回滚方案。
- 必须生成待确认 marker 或任务草稿，不能声称已经执行脚本。

确认前置：
- 目标环境、服务、资源范围明确。
- 具备权限和审批人。
- 有 dry-run 或等价验证结果。
- 有失败回滚和停止条件。""",
        'allowed_role_codes': [],
    },
    {
        'name': '任务模板选择',
        'slug': 'sx-task-template-selection',
        'category': '任务中心',
        'description': '约束 assistant 如何根据目标资源、环境和风险选择任务中心模板。',
        'source_type': 'inline',
        'applicable_actions': ['self_heal.recommend', 'host_task.generate'],
        'examples': ['给生产环境生成巡检任务', '选择 Redis 检查模板', '帮我安排基础健康检查', '修改 monitoring 命名空间 kube-prome Service'],
        'builtin_tools': ['query_task_resources', 'generate_host_task'],
        'recommended_tools': ['query_alerts'],
        'max_iterations': 3,
        'risk_level': 'draft',
        'output_contract': {
            'sections': ['资源范围', '模板选择', '执行策略', '确认项'],
            'blocks': ['approval_form', 'risk_notice'],
        },
        'content': """任务生成要求：
- 任务生成类请求以任务中心资源底座为权威资源来源，先查询 query_task_resources，再生成任务草稿。
- 知识图谱只用于识别环境、系统、服务和辅助元信息，不作为任务目标存在性的硬前置。
- 任务模板必须匹配资源类型和风险场景，不能为未知资源底座目标生成执行任务。
- K8s 写操作必须生成 K8s API 类型任务，不能退化成 SSH、主机脚本或空脚本任务。
- K8s Service 修改、Pod 重启、工作负载伸缩等写操作不需要先查实时 K8s 资源列表；即使 query_k8s_resources 未查到对象，也不能据此拒绝生成任务草稿。
- K8s 写操作必须明确 namespace；无法从用户输入或参数判断时，先提醒用户补充命名空间，不能默认使用 default。
- 输出要包含任务名称、目标资源数量、执行方式、执行策略、风险和确认项。
- 未确认前只能是草稿或待确认动作。""",
        'allowed_role_codes': [],
    },
    {
        'name': '回滚策略',
        'slug': 'sx-rollback-strategy',
        'category': '发布回滚',
        'description': '规范发布回滚和变更撤销建议的前置验证、影响范围和失败处理。',
        'source_type': 'inline',
        'applicable_actions': ['self_heal.recommend', 'change.correlation'],
        'examples': ['这次发布是否需要回滚', '给出回滚前检查项', '回滚失败怎么处理'],
        'builtin_tools': ['query_recent_changes', 'query_event_wall', 'query_knowledge_graph'],
        'recommended_tools': ['query_alerts', 'query_logs', 'query_traces'],
        'max_iterations': 4,
        'risk_level': 'draft',
        'output_contract': {
            'sections': ['回滚依据', '前置检查', '执行步骤', '验证方式', '失败处理'],
            'blocks': ['rollback_plan', 'approval_form', 'risk_notice'],
        },
        'content': """回滚建议要求：
- 回滚必须基于明确变更候选、故障影响和验证证据。
- 必须说明回滚目标版本、影响服务、预期影响、验证方式和停止条件。
- 如果证据不足，只能建议先验证，不能直接建议回滚。
- 高风险回滚必须走审批、dry-run 或演练确认。""",
        'allowed_role_codes': [],
    },
]


SKILL_GROUPS = [
    {
        'slug': 'answer-formatter',
        'name': '统一应答规范',
        'category': '通用规范',
        'description': '统一事实、推断、证据来源、风险与后续操作的表达规范，供所有问答类型复用。',
        'source_slugs': ['answer-formatter'],
        'applicable_actions': list(CAPABILITY_CODES),
    },
    {
        'slug': 'sx-alert-evidence',
        'name': '告警证据分析',
        'category': '证据分析',
        'description': '查询告警状态、级别、持续时间与根因候选，形成可验证的告警证据链。',
        'source_slugs': ['sx-alert-evidence-checklist'],
        'applicable_actions': ['troubleshoot', 'slo.analysis', 'event.analysis'],
        'builtin_tools': ['query_alerts', 'query_alert_root_cause', 'query_alert_metrics'],
        'recommended_tools': ['query_knowledge_graph', 'query_recent_changes'],
    },
    {
        'slug': 'sx-metric-slo-analysis',
        'name': '指标与 SLO 分析',
        'category': '证据分析',
        'description': '查询可用性、错误率、延迟和资源指标，评估服务健康与 SLO 风险。',
        'source_slugs': [],
        'applicable_actions': ['troubleshoot', 'slo.analysis', 'event.analysis'],
        'builtin_tools': ['query_alert_metrics', 'query_grafana_promql', 'query_dashboard_panel_data'],
        'recommended_tools': ['query_system_posture', 'query_traces'],
        'examples': ['评估当前环境订单服务最近一小时的 SLO 风险', '错误率升高主要由哪些指标造成', '比较当前可用性与 SLO 目标'],
        'max_iterations': 4,
        'output_contract': {
            'sections': ['指标范围', '实际值与趋势', 'SLO 判断', '缺失数据与建议'],
            'blocks': ['chart_query', 'evidence_timeline', 'risk_notice'],
        },
        'content': '先确认指标来源、时间窗口和目标值，再区分实际值、目标值、趋势与缺失数据。没有目标或错误预算时明确说明缺失，不把相关变化直接判定为根因。',
    },
    {
        'slug': 'sx-trace-evidence',
        'name': '链路证据分析',
        'category': '证据分析',
        'description': '沿调用链、服务依赖和请求跨度定位延迟、错误传播与影响路径。',
        'source_slugs': [],
        'applicable_actions': ['troubleshoot', 'slo.analysis', 'event.analysis'],
        'builtin_tools': ['query_traces', 'query_observability_links'],
        'recommended_tools': ['query_knowledge_graph', 'query_logs'],
        'examples': ['查询订单服务最近一小时的慢链路', '分析 checkout 到支付服务的错误传播路径', '哪些下游依赖导致当前请求延迟'],
        'max_iterations': 4,
        'output_contract': {
            'sections': ['链路范围', '关键跨度', '影响路径', '验证建议'],
            'blocks': ['evidence_timeline', 'incident_card', 'risk_notice'],
        },
        'content': '链路只能作为平台返回的证据，优先保留 trace、span、服务、端点、耗时和错误信息。按调用关系说明影响路径，不凭单条慢请求直接定性根因。',
    },
    {
        'slug': 'sx-system-posture',
        'name': '系统态势分析',
        'category': '证据分析',
        'description': '汇总系统、主机、服务和资源整体状态，判断异常范围与健康趋势。',
        'source_slugs': [],
        'applicable_actions': ['troubleshoot', 'slo.analysis', 'event.analysis'],
        'builtin_tools': ['query_system_posture'],
        'recommended_tools': ['query_hosts', 'query_knowledge_graph'],
        'examples': ['查看当前环境整体服务健康态势', '哪些系统和主机处于异常状态', '汇总当前环境资源压力与影响范围'],
        'max_iterations': 3,
        'output_contract': {
            'sections': ['态势摘要', '异常对象', '影响范围', '后续取证建议'],
            'blocks': ['incident_card', 'evidence_timeline', 'risk_notice'],
        },
        'content': '先确定知识图谱环境和统计窗口，再输出受影响系统、服务、主机与资源的实际状态。态势摘要用于缩小排查范围，不能替代告警、日志或链路的专项证据。',
    },
    {
        'slug': 'sx-log-analysis',
        'name': '日志查询与分析',
        'category': '证据分析',
        'description': '统一日志查询生成、字段映射、样本聚合与模式分析，供日志入口与故障排查复用。',
        'source_slugs': ['sx-log-pattern-analysis', 'sx-log-query-guide', 'sx-log-field-dictionary'],
        'applicable_actions': ['troubleshoot', 'log.query_generate'],
    },
    {
        'slug': 'sx-k8s-diagnostics',
        'name': 'K8s 诊断与取证',
        'category': '专业诊断',
        'description': '整合集群告警取证与常见工作负载排障路径，作为故障排查中的专业方法。',
        'source_slugs': ['sx-k8s-alert-troubleshooting', 'sx-k8s-troubleshooting'],
        'applicable_actions': ['troubleshoot'],
    },
    {
        'slug': 'sx-event-analysis',
        'name': '事件关联与影响分析',
        'category': '证据分析',
        'description': '统一事件、变更、工单和告警时间线，分析依赖关系、影响范围与关联置信度。',
        'source_slugs': ['sx-change-impact-analysis', 'sx-event-timeline-correlation'],
        'applicable_actions': ['troubleshoot', 'event.analysis', 'slo.analysis'],
    },
    {
        'slug': 'sx-container-safety-guard',
        'name': '容器操作安全护栏',
        'category': '安全护栏',
        'description': '限定容器与 K8s 只能通过只读工具取证，写操作必须形成待确认任务。',
        'source_slugs': ['sx-container-readonly-guard'],
        'applicable_actions': ['troubleshoot', 'host_task.generate'],
    },
    {
        'slug': 'sx-self-heal-safety',
        'name': '自愈风险评估',
        'category': '安全护栏',
        'description': '基于证据评估自愈适用条件、风险、dry-run 与回滚要求，只输出待确认建议。',
        'source_slugs': ['sx-self-heal-risk-guard'],
        'applicable_actions': ['troubleshoot'],
    },
    {
        'slug': 'sx-task-template-selection',
        'name': '任务模板编排',
        'category': '任务生成',
        'description': '按目标资源、环境和风险选择任务中心模板，生成可确认的任务草稿。',
        'source_slugs': ['sx-task-template-selection'],
        'applicable_actions': ['host_task.generate'],
    },
    {
        'slug': 'sx-rollback-strategy',
        'name': '回滚策略评估',
        'category': '变更治理',
        'description': '基于变更影响、验证证据和停止条件给出回滚或撤销建议。',
        'source_slugs': ['sx-rollback-strategy'],
        'applicable_actions': ['event.analysis', 'troubleshoot'],
    },
    {
        'slug': 'sx-cmdb-asset-cost-analysis',
        'name': 'CMDB 资产与成本分析',
        'category': '资产治理',
        'description': '统一资产盘点、成本洞察、拓扑影响与数据质量分析，遵循用户授权的 CMDB 资源范围。',
        'source_slugs': ['sx-cmdb-asset-cost-analysis'],
        'applicable_actions': ['cmdb'],
    },
]


def normalize_capability_bindings(values):
    return list(dict.fromkeys(
        LEGACY_CAPABILITY_ALIASES.get(str(value).strip(), str(value).strip())
        for value in values or [] if str(value or '').strip()
    ))


def _unique_values(definitions, field):
    return list(dict.fromkeys(value for definition in definitions for value in definition.get(field, [])))


def _merge_definition(group):
    sources_by_slug = {definition['slug']: definition for definition in LEGACY_BUILTIN_SKILLS}
    sources = [sources_by_slug[slug] for slug in group['source_slugs']]
    definition = deepcopy(sources[0]) if sources else {
        'name': group['name'],
        'slug': group['slug'],
        'category': group.get('category', ''),
        'description': group.get('description', ''),
        'source_type': 'inline',
        'applicable_actions': list(group.get('applicable_actions') or []),
        'examples': list(group.get('examples') or []),
        'builtin_tools': list(group.get('builtin_tools') or []),
        'recommended_tools': list(group.get('recommended_tools') or []),
        'max_iterations': group.get('max_iterations', 0),
        'risk_level': group.get('risk_level', 'read_only'),
        'output_contract': deepcopy(group.get('output_contract') or {'sections': [], 'blocks': []}),
        'content': group.get('content', ''),
        'allowed_role_codes': list(group.get('allowed_role_codes') or []),
    }
    for field in ('name', 'slug', 'category', 'description', 'applicable_actions'):
        definition[field] = deepcopy(group[field])
    for field in ('examples', 'builtin_tools', 'recommended_tools'):
        definition[field] = list(dict.fromkeys([*_unique_values(sources, field), *group.get(field, [])]))
    if sources:
        definition['max_iterations'] = max(source.get('max_iterations', 0) for source in sources)
        risk_order = {'read_only': 0, 'draft': 1, 'write': 2, 'execute': 3}
        definition['risk_level'] = max(
            (source.get('risk_level', 'read_only') for source in sources),
            key=lambda value: risk_order.get(value, 0),
        )
        definition['output_contract'] = {
            field: _unique_values([source.get('output_contract', {}) for source in sources], field)
            for field in ('sections', 'blocks')
        }
        definition['content'] = '\n\n'.join(f"【{source['name']}】\n{source['content']}" for source in sources)
    if group.get('content'):
        definition['content'] += '\n\n' + group['content']
    definition['source_type'] = 'inline'
    return definition


BUILTIN_SKILLS = [_merge_definition(group) for group in SKILL_GROUPS]
LEGACY_SKILL_MERGE_MAP = {slug: group['slug'] for group in SKILL_GROUPS for slug in group['source_slugs']}


def refine_consolidated_skills(skill_model, config_model):
    """Split v1 aggregate packages while preserving operator configuration.

    This is intentionally idempotent because bootstrap also invokes it for
    installations that were upgraded without running the data migration.
    """
    split_groups = {
        'sx-observability-analysis': [
            'sx-alert-evidence', 'sx-metric-slo-analysis',
            'sx-trace-evidence', 'sx-system-posture',
        ],
        'sx-safe-task-recovery': [
            'sx-container-safety-guard', 'sx-self-heal-safety',
            'sx-task-template-selection', 'sx-rollback-strategy',
        ],
    }
    legacy_group_bindings = {
        'sx-observability-analysis': {'troubleshoot', 'slo.analysis', 'event.analysis'},
        'sx-safe-task-recovery': {'troubleshoot', 'host_task.generate', 'event.analysis'},
    }
    definitions = {definition['slug']: definition for definition in BUILTIN_SKILLS}
    with transaction.atomic():
        for source_slug, target_slugs in split_groups.items():
            source = skill_model.objects.select_for_update().filter(
                slug=source_slug, is_builtin=True, merged_into__isnull=True,
            ).first()
            if not source:
                continue
            targets = []
            source_bindings = set(normalize_capability_bindings(source.applicable_actions))
            legacy_bindings = legacy_group_bindings[source_slug]
            for index, target_slug in enumerate(target_slugs):
                definition = definitions[target_slug]
                target_defaults = set(normalize_capability_bindings(definition.get('applicable_actions')))
                removed_bindings = legacy_bindings - source_bindings
                added_bindings = source_bindings - legacy_bindings
                desired_bindings = list(dict.fromkeys([
                    code for code in target_defaults if code not in removed_bindings
                ] + sorted(added_bindings)))
                target = skill_model.objects.select_for_update().filter(slug=target_slug).first()
                if target is None:
                    defaults = deepcopy(definition)
                    defaults.update(
                        is_builtin=True,
                        is_enabled=source.is_enabled,
                        builtin_version=CATALOG_VERSION,
                        allowed_role_codes=deepcopy(source.allowed_role_codes or []),
                        applicable_actions=desired_bindings,
                    )
                    if index == 0 and source.content:
                        defaults['content'] += f'\n\n【保留 v1 聚合 Skill 定制内容】\n{source.content}'
                    defaults.pop('slug')
                    target = skill_model.objects.create(slug=target_slug, **defaults)
                else:
                    changed_fields = []
                    was_archived = target.merged_into_id is not None
                    if was_archived:
                        archived_enabled = target.is_enabled
                        archived_roles = set(target.allowed_role_codes or [])
                        source_roles = set(source.allowed_role_codes or [])
                        target.merged_into_id = None
                        changed_fields.append('merged_into')
                        target.is_builtin = True
                        changed_fields.append('is_builtin')
                        target.is_enabled = bool(source.is_enabled and archived_enabled)
                        target.allowed_role_codes = sorted(
                            archived_roles & source_roles if archived_roles and source_roles
                            else (archived_roles or source_roles)
                        )
                        changed_fields.extend(['is_enabled', 'allowed_role_codes'])
                        legacy_definition = next(
                            (item for item in LEGACY_BUILTIN_SKILLS if item['slug'] == target_slug),
                            None,
                        )
                        if legacy_definition and target.content != legacy_definition.get('content'):
                            target.content = f"{definition.get('content', '')}\n\n【保留原 Skill 定制内容：{target.content}】"
                            changed_fields.append('content')
                        for field in ('name', 'description', 'category', 'examples', 'builtin_tools', 'recommended_tools', 'output_contract'):
                            setattr(target, field, deepcopy(definition.get(field)))
                            changed_fields.append(field)
                    if target.is_enabled != source.is_enabled:
                        target.is_enabled = source.is_enabled
                        changed_fields.append('is_enabled')
                    if target.allowed_role_codes != (source.allowed_role_codes or []):
                        target.allowed_role_codes = deepcopy(source.allowed_role_codes or [])
                        changed_fields.append('allowed_role_codes')
                    if index == 0 and source.content and source.content not in (target.content or ''):
                        target.content = f"{target.content or definition.get('content', '')}\n\n【保留 v1 聚合 Skill 定制内容】\n{source.content}"
                        changed_fields.append('content')
                    if target.builtin_version < CATALOG_VERSION:
                        target.builtin_version = CATALOG_VERSION
                        changed_fields.append('builtin_version')
                    if set(normalize_capability_bindings(target.applicable_actions)) == source_bindings:
                        target.applicable_actions = desired_bindings
                        changed_fields.append('applicable_actions')
                    if was_archived:
                        target.applicable_actions = desired_bindings
                        changed_fields.append('applicable_actions')
                    if changed_fields:
                        target.save(update_fields=list(dict.fromkeys(changed_fields)))
                targets.append(target)

            if not targets:
                continue
            target_ids = [target.id for target in targets]
            source.merged_into_id = targets[0].id
            source.save(update_fields=['merged_into'])
            for config in config_model.objects.select_for_update().all():
                selected = set()
                for value in config.enabled_skill_ids or []:
                    try:
                        selected.add(int(value))
                    except (ValueError, TypeError):
                        continue
                if source.id in selected:
                    selected.discard(source.id)
                    selected.update(target_ids)
                    next_ids = list(dict.fromkeys(sorted(selected)))
                    if next_ids != config.enabled_skill_ids:
                        config.enabled_skill_ids = next_ids
                        config.save(update_fields=['enabled_skill_ids'])


def _create_merged_defaults(definition, source_skills, legacy_defaults):
    defaults = deepcopy(definition)
    defaults.update(is_builtin=True, is_enabled=True, builtin_version=CATALOG_VERSION)
    defaults['is_enabled'] = all(skill.is_enabled for skill in source_skills)
    role_groups = [set(skill.allowed_role_codes) for skill in source_skills if skill.allowed_role_codes]
    if role_groups:
        defaults['allowed_role_codes'] = sorted(set.intersection(*role_groups))
        if not defaults['allowed_role_codes']:
            defaults['is_enabled'] = False
    group = next(group for group in SKILL_GROUPS if group['slug'] == definition['slug'])
    source_by_slug = {skill.slug: skill for skill in source_skills}
    legacy_tools = {
        tool for slug in group['source_slugs']
        for field in ('builtin_tools', 'recommended_tools')
        for tool in legacy_defaults[slug].get(field, [])
    }
    for field in ('builtin_tools', 'recommended_tools'):
        current_tools = []
        for slug in group['source_slugs']:
            source = source_by_slug.get(slug)
            current_tools.extend(getattr(source, field) if source else legacy_defaults[slug].get(field, []))
        defaults[field] = list(dict.fromkeys([
            *current_tools, *(tool for tool in definition[field] if tool not in legacy_tools),
        ]))
    for skill in source_skills:
        original = legacy_defaults[skill.slug]
        original_bindings = set(normalize_capability_bindings(original['applicable_actions']))
        current_bindings = set(normalize_capability_bindings(skill.applicable_actions))
        if original_bindings != current_bindings:
            defaults['applicable_actions'] = [
                code for code in defaults['applicable_actions']
                if code not in original_bindings - current_bindings
            ]
            defaults['applicable_actions'] = list(dict.fromkeys([
                *defaults['applicable_actions'], *sorted(current_bindings - original_bindings),
            ]))
        if skill.content != original['content']:
            defaults['content'] += f'\n\n【保留原 Skill 定制内容：{skill.name}】\n{skill.content}'
        for field in ('examples',):
            defaults[field] = list(dict.fromkeys([*defaults[field], *(getattr(skill, field) or [])]))
        defaults['max_iterations'] = max(defaults['max_iterations'], skill.max_iterations)
        risk_order = {'read_only': 0, 'draft': 1, 'write': 2, 'execute': 3}
        if risk_order.get(skill.risk_level, 0) > risk_order.get(defaults['risk_level'], 0):
            defaults['risk_level'] = skill.risk_level
        if skill.output_contract != original.get('output_contract', {}):
            defaults['output_contract'].setdefault('legacy_contracts', {})[skill.slug] = skill.output_contract
    return defaults


@transaction.atomic
def consolidate_builtin_skills(skill_model, config_model):
    legacy_defaults = {definition['slug']: definition for definition in LEGACY_BUILTIN_SKILLS}
    definitions = {definition['slug']: definition for definition in BUILTIN_SKILLS}
    source_rows = {
        skill.slug: skill
        for skill in skill_model.objects.select_for_update().filter(
            is_builtin=True, builtin_version=0, merged_into__isnull=True,
            slug__in=LEGACY_SKILL_MERGE_MAP,
        )
    }
    replacements = {}
    newly_created_ids = []
    for group in SKILL_GROUPS:
        source_skills = [source_rows[slug] for slug in group['source_slugs'] if slug in source_rows]
        if not source_skills:
            continue
        definition = definitions[group['slug']]
        target = skill_model.objects.filter(slug=group['slug']).first()
        if target is None:
            defaults = _create_merged_defaults(definition, source_skills, legacy_defaults)
            occupied_names = set(skill_model.objects.values_list('name', flat=True))
            while defaults['name'] in occupied_names:
                defaults['name'] += '（合并）'
            defaults.pop('slug')
            target, _ = skill_model.objects.get_or_create(slug=group['slug'], defaults=defaults)
        elif target.builtin_version == 0 and target in source_skills:
            original = legacy_defaults[target.slug]
            changed_fields = []
            for field, value in definition.items():
                if field == 'slug':
                    continue
                if field == 'name' and skill_model.objects.exclude(pk=target.pk).filter(name=value).exists():
                    continue
                if getattr(target, field) == original.get(field):
                    setattr(target, field, deepcopy(value))
                    changed_fields.append(field)
            target.builtin_version = CATALOG_VERSION
            target.save(update_fields=[*changed_fields, 'builtin_version'])
        elif not target.is_builtin or target.builtin_version == 0:
            continue
        for source in source_skills:
            if source.pk == target.pk:
                continue
            source.merged_into_id = target.pk
            source.save(update_fields=['merged_into'])
            replacements[source.pk] = target.pk
    if source_rows:
        for config in config_model.objects.all():
            selected = set()
            for value in config.enabled_skill_ids or []:
                try:
                    selected.add(int(value))
                except (ValueError, TypeError):
                    continue
            if not selected:
                selected = {skill.pk for skill in source_rows.values()}
            next_ids = sorted(selected - set(replacements))
            for target_id in set(replacements.values()):
                source_ids = {source_id for source_id, mapped_id in replacements.items() if mapped_id == target_id}
                if source_ids <= selected and target_id not in next_ids:
                    next_ids.append(target_id)
            if next_ids != config.enabled_skill_ids:
                config.enabled_skill_ids = next_ids
                config.save(update_fields=['enabled_skill_ids'])
    for skill in skill_model.objects.filter(merged_into__isnull=True):
        normalized = normalize_capability_bindings(skill.applicable_actions)
        if normalized != skill.applicable_actions:
            skill.applicable_actions = normalized
            skill.save(update_fields=['applicable_actions'])

    for group in SKILL_GROUPS:
        if group['source_slugs']:
            continue
        definition = definitions[group['slug']]
        defaults = deepcopy(definition)
        defaults.update(is_builtin=True, is_enabled=True, builtin_version=CATALOG_VERSION)
        defaults.pop('slug')
        skill, created = skill_model.objects.get_or_create(slug=group['slug'], defaults=defaults)
        if created and skill.is_enabled:
            newly_created_ids.append(skill.pk)
    if newly_created_ids:
        for config in config_model.objects.all():
            selected = _coerce_skill_ids(config.enabled_skill_ids)
            next_ids = list(dict.fromkeys([*selected, *newly_created_ids]))
            if next_ids != config.enabled_skill_ids:
                config.enabled_skill_ids = next_ids
                config.save(update_fields=['enabled_skill_ids'])


def _coerce_skill_ids(values):
    normalized = []
    for value in values or []:
        try:
            normalized.append(int(value))
        except (ValueError, TypeError):
            continue
    return normalized
