# 执行追踪加载修复（2026-11-01）

执行追踪列表接口原先返回 HTTP 500，页面提示“执行追踪加载失败”。根因是 PostgreSQL 将助手消息 JSON 中的 `orchestration_user_message_id` 与外层整数主键直接比较，报错 `operator does not exist: jsonb = bigint`。

`backend/aiops/audit_executions.py` 改用 JSON 文本提取，并将外层主键转为文本后比较，兼容数字、字符串编号，安全忽略无效的历史值；保留 Thread 关联及现有审计权限检查。

新增回归验证仅按用户消息编号关联的助手回复、同会话多轮隔离、无效历史值、状态筛选和详情查询。PostgreSQL 回归另外发现任务确认路径预加载可空消息表时，`FOR UPDATE` 会锁定外连接的可空侧；已去掉该处消息预加载，保留动作与会话行锁。

验证结果：

- `aiops.test_audit_executions`、`aiops.test_langgraph_stability` 共 26 项测试，在隔离 SQLite 和 PostgreSQL 测试数据库中分别全部通过。
- 线上列表返回 30 条执行记录；分页、状态、用户及关键词筛选均返回 HTTP 200。
- 12 个演示会话的最新执行详情全部返回 HTTP 200，助手回复关联正确，节点、模型调用、Checkpoint 和动作追踪正常。
- 浏览器确认执行列表与详情加载成功，节点时间线和 Checkpoint 可见，中文无乱码。
- 部署文件 SHA-256 校验、Django `check` 通过，应用健康检查 HTTP 200。

发布信息：

- 已重建应用 `sxdevops-app` 和聊天 worker `sxdevops-aiops-chat-worker`，均运行当前镜像 `ca92bf4abc3c74621272bb92277b052827f649e9b9986f7250edbbdf4b340859`。
- 源码、前一镜像标识、测试及构建日志备份位于 `/opt/sxdevops/.deploy-backups/execution-audit-fix-20261101/`。
- 此次同步三个后端文件，无数据库迁移。

![执行追踪详情正常加载](screenshots/execution-trace-fix-20261101.png)
