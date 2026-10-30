# AIOps 架构与运行机制

默认 AIOps 聊天由 LangGraph 编排，Django 业务层负责授权、工具执行、持久化和动作确认。当前聊天图版本为 `12`，动作图为 `1`，处置验证图为 `1`；这些编号用于状态兼容检查，与平台 SemVer 分开。

## 请求与执行边界

```mermaid
flowchart TD
    request[聊天与页面上下文] --> scope[问答类型、环境与权限]
    scope --> graph[LangGraph 取证与工具编排]
    graph --> runtime[Django 受控工具运行时]
    runtime --> evidence[结构化证据与调用审计]
    evidence --> answer[回复整形、事实检查与输出]
    graph --> draft[动作或任务草稿]
    draft --> confirm[Django 权限、预检与本人确认]
    confirm --> task[实际任务]
    task --> verification[观察窗口与效果验证]
```

默认同步及异步聊天都经过图编排。异步入口创建 `AIOpsChatJob`，独立 worker 领取、续租、更新消息并恢复 checkpoint；独立 `langgraph_pilot` 入口仍是只读诊断入口。

六类问答入口、十三个内置 Skill 和 MCP 挂载见[问答类型与 Skills](AIOps-问答能力与Skills.md)。Skill 提供方法和输出约束，MCP 提供工具，二者都不能绕过用户权限、资源范围、服务端动作开关和只分析模式。页面上下文只是线索，不是执行授权。

## 聊天图

`route` 和 `lane_*` 确定路线，`prepare` / `policy` 校验会话、账号、问题与服务端策略，之后进入对应分支：

| 分支 | 编排内容 |
| --- | --- |
| 单条告警 | 环境、告警事实、K8s、态势、事件、日志、Trace、指标与汇总 |
| K8s 异常 | 授权资源、固定集群、告警、事件、态势与汇总 |
| 变更 / 事件关联 | 环境、知识关系、变更、工单、事件、告警与汇总 |
| 自愈建议 | 环境、告警、知识关系、变更、日志、Trace；只形成建议或待确认块 |
| SLO | 态势、告警、指标、面板、Trace、知识关系与工作负载 |
| 服务异常 / 环境告警 | 范围、告警及按需指标、态势、日志、Trace、事件、工作负载 |
| CMDB | 优先授权的资产、成本、拓扑直接查询，未命中时回到受控运行时 |
| 通用工具 | `agent_plan → agent_tool → agent_synthesis`，逐个保存计划及工具结果 |
| 任务草稿 | `task_scope → task_resources → task_draft → task_synthesis` |

取证节点保存状态、耗时、缺口与审计。环境或告警无法唯一确认时要求补充；恢复使用最初确认的环境与目标，并重新检查当前权限及工具状态。没有集群绑定不回退到全局集群，缺少授权不发出查询。

指标证据通过授权的数据源与时间窗口查询，包含计划、摘要、异常和缺失项；`query_alert_metrics` 使用 `ops.metric.query`。PromQL 建议或未执行的查询不能当作观测事实。SLO 缺少明确目标时不自行推算达标、错误预算或烧速；变更时间接近只作为候选诱因。

## 回复整形

回复经过 `formatter_prepare → formatter_model → formatter_check`，检查工具事实、数量、日志结论和任务状态；必要时进入有界 `formatter_repair`，达到上限后采用确定性兜底，由 `formatter_finish` 输出。

普通回复最多 3 次整形，有告警事实的告警问题最多 4 次。通用工具循环最多 6 轮，每轮最多 8 个工具，聊天图递归上限为 96。未启用对应 Skill 时不增加整形请求。

每次模型结果在检查前保存，恢复不重做已完成且保存的步骤。Skill、提供商配置或权限变化时重新检查，不能直接返回不再有权查看的旧证据。数据源失败、无数据和权限不足明确展示，不替换为“健康”。

## 动作确认与处置验证

聊天图只返回草稿，由 Django 创建待确认动作。动作图 `review → confirmation → execute` 在确认处中断，确认 API 再检查本人身份、权限、开关与资源范围，行锁避免并发确认重复执行。任务草稿与实际任务的创建和执行沿用原业务规则。

任务资源重新校验目标，K8s 操作同时检查具体平台能力、集群和命名空间范围。已经保存的资源快照不会使后来新增目标自动进入执行范围。

效果验证在任务开始前保存告警基线，任务完成并经过观察窗口后由独立验证图检查，详见[处置效果验证](AIOps-处置效果验证.md)。恢复事件只说明告警已恢复，不能证明因果或业务整体健康。

## checkpoint、worker 与恢复

- 本地默认 SQLite 文件，Compose 使用 MySQL；应用与 worker 共用存储配置和代码版本，见[配置参考](configuration.md#aiops-checkpoint-与运行参数)。
- `AIOpsChatJob` 的租约支持过期接管。旧 worker 在更新消息和发布结果前核对租约，失去租约后不能继续写入。
- 已完成并 checkpoint 的节点复用结果；节点内部或 checkpoint 写入前中断仍可能重试当前调用，语义为至少一次，不能承诺外部调用恰好一次。
- 保存运行所需 ID、配置指纹和证据，不保存模型 API Key、MCP 鉴权配置、SSH 密码、kubeconfig 或客户端对象。checkpoint 仍包含业务证据，应按敏感数据保护。
- 每次恢复和输出重新校验账号、工具启用/白名单、MCP 选择、权限与范围。撤权不会撤销已经发出的外部请求。
- 未完成旧图状态可能拒绝跨版本恢复；升级前处理活动队列和未完成动作，切换存储不会自动迁移未完成状态。

仅平台允许的只读临时连接错误进行有界重试，默认一次；权限拒绝、业务错误、写操作及外部 MCP 不自动重试。节点默认预算 180 秒，进入工具前后检查；不能强制取消所有同步客户端或已发出的请求。

框架依赖不可用导致兼容运行时降级时，回复与审计明确提示不能断点恢复。普通运行错误保留失败，不无提示地重新执行整轮。

## 执行审计与清理

“智能体审计 → 执行追踪”按用户消息关联节点、工具、模型和动作，区分图耗时、人工等待、失败、重试与恢复；成功恢复不会抹掉此前失败记录。

只读 API 使用 `aiops.audit.view`：

```text
GET /api/aiops/admin/audit/executions/
GET /api/aiops/admin/audit/executions/<用户消息ID>/
```

列表数据库分页，详情最多展示最近 500 条节点，只返回 checkpoint 摘要，不返回完整载荷或 worker 租约令牌。历史未关联模型调用不推测归属。

默认保留 30 天。清理仅处理过期且完成的状态，跳过活动任务、待确认动作及未完成验证；保留会话正文与验证结论。worker 空闲时定期清理，`--cleanup-interval 0` 可禁用。

在 `backend` 目录运行：

```bash
python manage.py run_aiops_chat_worker --interval 2
python manage.py inspect_aiops_graph --thread-id <thread-id>
python manage.py cleanup_aiops_checkpoints
```

清理命令默认预览，明确确认范围后添加 `--apply`。诊断命令只输出运行摘要，避免直接导出完整 checkpoint。部署与备份见[运维指南](deployment.md)。

## 源码入口

- `backend/aiops/langgraph_pilot.py`：图、checkpoint 与恢复入口。
- `backend/aiops/langgraph_execution.py`：节点执行、预算与重试。
- `backend/aiops/langgraph_management.py`：诊断与保留清理。
- `backend/aiops/test_langgraph_*.py`、`test_audit_executions.py`、`test_remediation.py`：编排、审计和验证回归。

本文件路径保留给既有产品页链接，正文维护当前运行机制，历史分阶段验收已收敛到[版本验证记录](releases/v2.0.0-validation.md)。

[文档目录](README.md)
