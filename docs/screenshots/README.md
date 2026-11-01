# 产品截图

保留 README 使用的当前产品截图和会话示例；逐轮验收、旧界面及临时 smoke 截图不作为正式文档资产。

## 素材目录

| 文件 | 展示内容 |
| --- | --- |
| [sxdevops-operation-flow.png](sxdevops-operation-flow.png) | 产品运转逻辑总览 |
| [v2-dashboard.png](v2-dashboard.png) | 系统态势、SLA 与历史可用率 |
| [v2-system-settings-charcoal.png](v2-system-settings-charcoal.png) | 炭灰主题、侧栏和系统设置 |
| [v2-cmdb-overview.png](v2-cmdb-overview.png) | CMDB 容量、资产及治理入口 |
| [v2-cmdb-topology.png](v2-cmdb-topology.png) | 资产拓扑、业务环境树和分类关系规则 |
| [assistant-demo-20261101.png](assistant-demo-20261101.png) | 智能助手故障排查、平台取证及会话历史 |
| [execution-trace-fix-20261101.png](execution-trace-fix-20261101.png) | LangGraph 执行追踪、节点时间线及 Checkpoint |
| [v2-aiops-sessions.png](v2-aiops-sessions.png) | 会话历史及执行追踪入口 |
| [v2-k8s-workbench.png](v2-k8s-workbench.png) | 集群容量、Requests / Limits 与 Pod 摘要 |
| [v2-docker-workbench.png](v2-docker-workbench.png) | 演示容器、镜像及分页操作 |
| [v2-logs-query.png](v2-logs-query.png) | ELK 演示查询条件、趋势和结果 |

系统态势、CMDB 概览和资产拓扑截图于 2026-10-30 从当前版本的本地隔离演示环境采集，使用示例数据，统一添加展示标题栏；没有连接业务资源。其余 v2 产品截图采集于 2026-10-25，炭灰系统设置截图补充于 2026-10-28。智能助手与执行追踪截图于 2026-11-01 更新，统一使用 PNG。它们用于说明页面和流程，不证明当前线上容量、查询性能或故障修复成功率。

## 维护约定

- 使用运行中产品的真实 PNG，不使用占位图。
- 修改 README 产品展示时同步检查素材；单纯修正文档导航或安装说明无需重拍界面。
- 替换或删除素材前检查 README、文档及产品页引用，更新对应链接。
- 不包含生产密码、Token、连接配置、客户数据或未脱敏的主机信息。
- 临时测试截图放在忽略的运行目录，历史素材通过 Git 查询，不在此目录逐轮积累。

[文档目录](../README.md)
