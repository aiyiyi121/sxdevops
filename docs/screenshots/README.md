# 产品截图

保留 README 使用的当前产品截图和会话示例；逐轮验收、旧界面及临时 smoke 截图不作为正式文档资产。

## 素材目录

| 文件 | 展示内容 |
| --- | --- |
| [sxdevops-operation-flow.png](sxdevops-operation-flow.png) | 产品运转逻辑总览 |
| [v2-dashboard.png](v2-dashboard.png) | 系统态势、SLA 与历史可用率 |
| [v2-cmdb-overview.png](v2-cmdb-overview.png) | CMDB 容量、资产及治理入口 |
| [v2-cmdb-topology.png](v2-cmdb-topology.png) | 资产拓扑、业务环境树和分类关系规则 |
| [assistant-demo-20261101.png](assistant-demo-20261101.png) | 智能助手故障排查、平台取证及会话历史 |
| [execution-trace-fix-20261101.png](execution-trace-fix-20261101.png) | LangGraph 执行追踪、节点时间线及 Checkpoint |
| [v2-aiops-sessions.png](v2-aiops-sessions.png) | 智能体审计的模型与工具调用统计 |
| [session-audit-20261101.png](session-audit-20261101.png) | 智能体配置、建议问题、系统提示词与能力范围 |
| [v2-k8s-workbench.png](v2-k8s-workbench.png) | 集群容量、Requests / Limits 与 Pod 摘要 |
| [v2-logs-query.png](v2-logs-query.png) | ELK 演示查询条件、趋势和结果 |
| [系统SLO.png](系统SLO.png) | 系统 SLO、可用率、错误预算与服务详情 |
| [仪表盘.png](仪表盘.png) | Grafana 看板、请求趋势与资源指标 |
| [链路追踪.png](链路追踪.png) | 服务拓扑、Trace 列表与 Span 瀑布图 |
| [事件中心.png](事件中心.png) | 事件时间线、详情与原始记录 |
| [ops-agnet.png](ops-agnet.png) | SRE 运维智能体工程方法论 |

当前展示以本目录中的 PNG 原图为准。2026-11-01 同步更新产品介绍“界面一览”，使用最新截图并加入系统 SLO、仪表盘、链路追踪、资产拓扑及智能体配置。截图用于说明页面和流程，不证明当前线上容量、查询性能或故障修复成功率。

## 产品介绍截图映射

产品页使用 `frontend/public/promo/v2/` 下的 WebP 展示副本，保留 PNG 原图。当前副本保留原始 1679 × 944 分辨率，使用 WebP 质量 88 压缩，不裁切界面内容。

| 界面一览 | PNG 来源 | WebP 展示副本 |
| --- | --- | --- |
| 智能助手 | `assistant-demo-20261101.png` | `assistant.webp` |
| 智能体配置 | `session-audit-20261101.png` | `agent-config.webp` |
| 系统态势 | `v2-dashboard.png` | `posture.webp` |
| 系统 SLO | `系统SLO.png` | `slo.webp` |
| 仪表盘 | `仪表盘.png` | `dashboards.webp` |
| 事件中心 | `事件中心.png` | `events.webp` |
| CMDB | `v2-cmdb-overview.png` | `cmdb.webp` |
| 资产拓扑 | `v2-cmdb-topology.png` | `topology.webp` |
| 日志检索 | `v2-logs-query.png` | `logs.webp` |
| 链路追踪 | `链路追踪.png` | `tracing.webp` |
| Kubernetes | `v2-k8s-workbench.png` | `kubernetes.webp` |

Docker、智能体审计、工作台主题不再进入“界面一览”。旧可观测总览和任务执行截图在当前目录中没有对应素材，已从画廊撤下。`session-audit-20261101.png` 实际展示智能体配置，按图片内容命名展示；审计统计和执行追踪截图保留作其他文档素材。

## 维护约定

- 使用运行中产品的真实 PNG，不使用占位图。
- 修改 README 产品展示时同步检查素材；单纯修正文档导航或安装说明无需重拍界面。
- 替换或删除素材前检查 README、文档及产品页引用，更新对应链接。
- 不包含生产密码、Token、连接配置、客户数据或未脱敏的主机信息。
- 临时测试截图放在忽略的运行目录，历史素材通过 Git 查询，不在此目录逐轮积累。

[文档目录](../README.md)
