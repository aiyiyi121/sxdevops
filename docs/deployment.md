# 部署与运维

本文适用于从源码构建的 Docker Compose / Podman Compose 环境。Kubernetes 另见[集群部署指南](Kubernetes部署指南.md)，v2 的迁移差异见[升级说明](releases/v2.0.0-release-guide.md)。

## 服务与状态

| 服务 | Compose 服务名 | 职责 |
| --- | --- | --- |
| Web / ASGI | `sxdevops` | 页面、API 和 WebSocket |
| CMDB 调度器 | `cmdb-sync-scheduler` | 每 60 秒扫描到期采集任务，每轮最多 10 个；保持单实例 |
| AIOps worker | `aiops-chat-worker` | 异步聊天、租约恢复和处置效果验证 |
| MySQL / Redis | `mysql` / `redis` | 业务数据、共享 checkpoint、缓存与实时通信 |

应用、调度器和 worker 必须使用同一份发行镜像及兼容配置。只更新 Web 会造成 worker 沿用旧图或旧权限逻辑。

持久状态包括数据库、Redis 数据和 `aiops_runtime` 卷；已有凭据还依赖稳定的 `CMDB_PASSWORD_ENCRYPTION_KEY`。容器运行正常不代表后台任务正在消费，需分别检查三项应用服务。

## 首次部署配置

从固定提交或标签构建，并记录 SHA。私有配置保存在已忽略的 `.env` 和 `compose.production.local` 中，限制文件读取权限；不要提交真实域名、服务器地址或凭据。

`.env` 示例，所有占位值均须替换：

```dotenv
SECRET_KEY=<独立长随机值>
SXDEVOPS_DB_PASSWORD=<独立数据库密码>
SXDEVOPS_DB_ROOT_PASSWORD=<独立数据库管理密码>
CMDB_PASSWORD_ENCRYPTION_KEY=<首次生成或保留的原Fernet密钥>
SXDEVOPS_HOSTS=<实际访问域名,必要的本机地址>
```

`compose.production.local` 覆盖示例：

```yaml
x-app-env: &app-env
  SECRET_KEY: ${SECRET_KEY:?Set SECRET_KEY}
  MYSQL_PASSWORD: ${SXDEVOPS_DB_PASSWORD:?Set SXDEVOPS_DB_PASSWORD}
  CMDB_PASSWORD_ENCRYPTION_KEY: ${CMDB_PASSWORD_ENCRYPTION_KEY:?Set CMDB_PASSWORD_ENCRYPTION_KEY}
  DEBUG: "0"
  ALLOWED_HOSTS: ${SXDEVOPS_HOSTS:?Set SXDEVOPS_HOSTS}
  CORS_ALLOW_ALL_ORIGINS: "0"
  SXDEVOPS_SEED_DATA: "0"
  SXDEVOPS_SEED_TEMPLATES: "0"
  AIOPS_LANGGRAPH_CHECKPOINT_BACKEND: mysql

services:
  sxdevops:
    environment: *app-env
  cmdb-sync-scheduler:
    environment: *app-env
  aiops-chat-worker:
    environment: *app-env
  mysql:
    environment:
      MYSQL_PASSWORD: ${SXDEVOPS_DB_PASSWORD:?Set SXDEVOPS_DB_PASSWORD}
      MYSQL_ROOT_PASSWORD: ${SXDEVOPS_DB_ROOT_PASSWORD:?Set SXDEVOPS_DB_ROOT_PASSWORD}
```

该示例只覆盖配置，保留基础编排的命令、依赖及卷。不要在已有 MySQL 数据卷上仅修改初始化密码变量来“轮换密码”：已有账号密码须在数据库内另行变更，并同步应用配置。

启动时始终带上同一份覆盖文件：

```bash
docker compose -f docker-compose.yml -f compose.production.local up -d --build
docker compose -f docker-compose.yml -f compose.production.local exec sxdevops python manage.py createsuperuser
```

模板同步按需显式执行 `python manage.py seed_templates`；先检查模板变更，不导入业务演示数据或角色测试账号。使用 Podman 时将命令入口替换为本机支持的 `podman-compose`，并先确认覆盖文件合并结果。

基础编排把 8000 端口发布到所有接口。正式环境应在私有部署配置中改为本机或内网监听，并由 HTTPS 反向代理统一入口；注意 Compose 的 `ports` 合并可能保留旧映射，应检查最终映射。代理需支持 WebSocket Upgrade，限制实际域名访问。不要把 MySQL、Redis 和管理终端直接暴露到公网。

配置检查可使用 Compose 的 `config --quiet`；不要把包含解析后密码的完整 `config` 输出粘贴到 Issue 或日志中。完整变量含义与优先级见[配置参考](configuration.md)。

## 备份与升级

以下命令以基础编排为例；实际操作须继续带上部署时的全部 `-f` 覆盖文件。

1. 进入维护窗口，停止接收新的聊天和执行任务，处理 queued/running 聊天、实际任务、待确认动作及未完成验证。
2. 备份业务数据库、共享 checkpoint 表或 SQLite checkpoint 文件、运行卷、私有配置与加密密钥；记录旧镜像摘要并验证备份可读取。SQLite 文件应在写入进程停止后备份，或使用 SQLite 一致性备份方式。
3. 需要跨数据库表一致性的备份时，停止所有写入方后执行。MySQL 可使用受控备份工具或 `mysqldump --single-transaction`（适用于事务表），凭据通过受限配置提供；不要在共享命令行或日志中明文传递密码。
4. 停止三项应用服务，保留数据库和卷，构建候选镜像并执行一次完整迁移。

```bash
docker compose stop sxdevops aiops-chat-worker cmdb-sync-scheduler
docker compose build sxdevops
docker compose run --rm -e SXDEVOPS_MIGRATE=0 -e SXDEVOPS_SEED_DATA=0 -e SXDEVOPS_SEED_TEMPLATES=0 sxdevops python manage.py migrate --noinput
docker compose up -d --force-recreate sxdevops cmdb-sync-scheduler aiops-chat-worker
```

重建镜像后显式重建三个应用容器，避免仅镜像更新而旧容器继续运行。不要运行 `down -v` 清理升级环境，它会删除持久卷。首次迁移后保持已有加密密钥；图版本变化前处理旧的未完成 checkpoint，不假设能够跨版本恢复。

## 上线检查

```bash
docker compose ps
docker compose logs --tail=100 sxdevops aiops-chat-worker cmdb-sync-scheduler
docker compose exec sxdevops python manage.py check
docker compose exec sxdevops python manage.py showmigrations
```

确认三项应用服务为当前镜像，首页和 API 可访问，迁移已应用。再用最小权限账号验证菜单、只读接口及越权拒绝，确认 CMDB 采集能调度、异步聊天能完成，查看执行审计。任务写入仅在明确的测试资源上验收。

生产排查不要运行演示造数或全量测试命令。发行验证应在隔离环境完成，并记录与部署镜像相同的源码提交。

## 回退

先停止接收新任务并暂停 worker，保留失败现场，切回记录过的旧镜像及兼容配置。数据库迁移、能力目录或 checkpoint 不兼容时，应按备份方案恢复状态；只回退代码不能保证旧版可读新数据。

恢复数据库会丢失备份之后的变更，必须确认恢复点，并核对外部任务是否已经执行，防止重复提交。旧版 `demo` 账号清理迁移删除的数据不能靠反向迁移恢复。

## 常见问题

| 现象 | 检查方向 |
| --- | --- |
| 无法登录或没有管理员 | 查看迁移结果；首次运行 `createsuperuser`，不使用旧演示账号 |
| 聊天一直排队 | worker 是否运行、数据库与 checkpoint 是否一致、是否存在旧图版本或过期租约 |
| 定时采集不执行 | 调度器日志、任务启用状态与到期时间；不要并行启动多个调度器 |
| CMDB 密码无法解密 | 是否沿用原 Fernet 密钥，JSON 配置是否覆盖环境变量 |
| 权限变化后仍有终端连接 | HTTP 和新连接已重新鉴权；已建立 WebSocket 需另行主动关闭 |
| 返回 403 | 分别检查能力权限、资源范围、账号状态和功能开关，不只检查菜单 |
| WebSocket 连接失败 | 代理 Upgrade / 超时、当前 Token、用户状态及对应终端权限 |
| Chrome 安全警告仍存在 | 权限修复与浏览器信誉复审分别处理；见[站点安全说明](user-permission-security.md#站点安全告警处理) |

[文档目录](README.md)
