# 配置参考

配置实现以 [Django settings](../backend/sxdevops/settings.py)、[容器入口](../docker/entrypoint.sh)和 [Compose 编排](../docker-compose.yml)为准。

## 配置来源与优先级

后端默认读取 `backend/config.json`，可通过 `SXDEVOPS_CONFIG_FILE` 指定其他路径；相对路径按 `backend/` 解析。复制 [config.example.json](../backend/config.example.json) 后修改，不要提交真实配置。

数据库、缓存、功能开关及 CMDB 加密密钥等通过 `_setting_value` 解析的选项，优先级是 **JSON 中有效字段 → 环境变量 → 默认值**。不要以为设置环境变量一定能覆盖已有 JSON。`SECRET_KEY`、`DEBUG`、`ALLOWED_HOSTS` 和 `CORS_ALLOW_ALL_ORIGINS` 当前直接读取环境变量；LangGraph 参数也直接读取环境变量。

Compose 的 `.env` 用于变量插值，只有编排 `environment` / `env_file` 声明的值才会进入容器。仅把新变量写进 `.env`，不会自动传给应用。覆盖配置也要同步到调度器和 worker。

## 数据库与缓存

| 环境变量 | 默认 / 用途 |
| --- | --- |
| `DATABASE_ENGINE` | 默认 `postgresql`（推荐）；备选 `mysql`；本地测试显式用 `sqlite` |
| `POSTGRES_HOST` / `POSTGRES_PORT` | PostgreSQL 地址和端口；无配置默认 `127.0.0.1:5432`，Compose 为 `postgres:5432` |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | 默认库名和用户为 `sxdevops`；密码由启动脚本随机生成并保存在 `.env`，Kubernetes 保存于 Secret |
| `POSTGRES_SSLMODE` | 可选 PostgreSQL SSL 模式，如远程数据库使用 `verify-full`；证书等参数通过 JSON 的 `database.options` 配置 |
| `SQLITE_PATH` | 默认 `backend/db.sqlite3`，相对路径按 `backend/` 解析 |
| `MYSQL_HOST` / `MYSQL_PORT` | MySQL 地址和端口；Compose 为 `mysql:3306` |
| `MYSQL_DATABASE` / `MYSQL_USER` / `MYSQL_PASSWORD` | 数据库、用户与密码 |
| `DATABASE_CONN_MAX_AGE` | 可选连接复用时长（秒） |
| `REDIS_URL` | Django 共享缓存，例如 `redis://redis:6379/0` |
| `CHANNEL_REDIS_URL` | Channels 通信，例如 `redis://redis:6379/1` |
| `CACHE_BACKEND` | `redis` 或 `local`；未配 Redis 时默认进程内缓存 |
| `CACHE_IGNORE_EXCEPTIONS` | Redis 异常是否忽略；部署清单设为 `0`，登录计数失败时拒绝登录 |

JSON 示例中的 `database` 和 `cache` 字段分别映射这些设置。多实例环境应使用共享 Redis；进程内缓存无法统一登录限流计数。缓存容错不等于限流始终有效，应监控 Redis 故障并在入口网关补充限流。

## 密钥与访问入口

| 变量 | 配置要求 |
| --- | --- |
| `SECRET_KEY` | 生产显式设置稳定的长随机值，各应用进程一致；未配会在进程启动时随机生成 |
| `CMDB_PASSWORD_ENCRYPTION_KEY` | Fernet 密钥；保存资产登录凭据前配置，各实例一致并单独备份 |
| `DEBUG` | 当前默认 `0`；生产保持关闭 |
| `ALLOWED_HOSTS` | 当前默认 `*`；生产填写实际域名/IP，逗号分隔，不带协议和路径 |
| `CORS_ALLOW_ALL_ORIGINS` | 当前后端默认开启；同源生产部署显式设置 `0` |
| `SXDEVOPS_TRUSTED_PROXIES` | 默认空；逗号分隔的可信入口代理 IP/CIDR，控制登录 IP 对 `X-Forwarded-For` 的信任 |

生成 Fernet 密钥：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**已有 CMDB 密文后必须保留原密钥。** 更换或丢失密钥会导致历史密码无法解密；保留数据库备份还不足以恢复凭据。

当前 settings 未提供 CORS 来源列表、CSRF 可信来源列表和 HTTPS 代理设置的同名环境变量映射。优先采用同源反向代理；确需跨域或 Session 跨站请求时，需先在 Django 配置中显式接入准确白名单及可信代理设置，再验证。不能通过写入未支持的环境变量假定其已生效。

## 初始化开关

| 变量 | 当前行为 |
| --- | --- |
| `SXDEVOPS_WAIT_FOR_DB` | 容器默认 `1`，根据有效 Django 配置等待 PostgreSQL / MySQL TCP 可连接，最长 120 秒；SQLite 跳过 |
| `SXDEVOPS_MIGRATE` | 容器默认 `1`；多实例升级应改为一次独立迁移 |
| `SXDEVOPS_WAIT_FOR_SCHEMA` | 容器默认 `0`；Compose 后台服务设为 `1`，等待当前镜像要求的迁移完成，最长 600 秒；Kubernetes 使用初始化容器完成同一检查 |
| `SXDEVOPS_SEED_DATA` | 默认 `0`；只在隔离体验环境显式导入业务演示数据 |
| `SXDEVOPS_SEED_TEMPLATES` | 容器默认 `1`；正式升级建议独立评估模板同步，后台服务保持 `0` |
| `SXDEVOPS_ADMIN_INITIAL_PASSWORD` | 迁移后在满足条件时创建初始 `admin`，不会重置现有账号；也可直接用 `createsuperuser` |
| `SXDEVOPS_DEMO_PASSWORD` | 仅供显式运行 `seed_rbac_demo` 为新测试账号设密码，不是生产登录配置 |

首次管理员推荐交互运行 `python manage.py createsuperuser`。初始化密码不应长期留在部署配置中。登录请求本身不会初始化账号或同步内置角色。

## AIOps checkpoint 与运行参数

| 变量 | 默认 / 含义 |
| --- | --- |
| `AIOPS_LANGGRAPH_CHECKPOINT_BACKEND` | 默认跟随应用数据库：`postgresql` / `mysql` / `sqlite`；可显式指定，须与数据库配置相匹配 |
| `AIOPS_LANGGRAPH_CHECKPOINT_PATH` | SQLite 文件默认 `backend/runtime/aiops-langgraph-checkpoints.sqlite3` |
| `AIOPS_LANGGRAPH_QUERY_RETRIES` | `1`，允许范围 0–3；只对平台允许的只读临时连接错误重试 |
| `AIOPS_LANGGRAPH_NODE_TIMEOUT_SECONDS` | `180` 秒节点预算；不能撤销已发出的外部请求 |
| `AIOPS_LANGGRAPH_RETENTION_DAYS` | `30` 天；完成且符合清理条件的状态才会清理 |

PostgreSQL / MySQL checkpoint 使用应用数据库配置（含 PostgreSQL SSL 选项），首次建表需要相应权限；应用和 worker 的存储后端、数据库、代码与图版本应一致。切换后端不会自动迁移未完成 checkpoint，升级前先处理活动任务。运行命令见 [AIOps 架构说明](AIOps-LangGraph-试点说明.md)。

平台数据库与 SQL 审计的业务数据源独立配置。SQL 审计支持 MySQL、PostgreSQL、MongoDB；PostgreSQL 数据源默认端口 `5432`，连接数据库留空时用 `postgres` 发现可连接库，查询和变更连接工单选定的目标库。查询使用只读事务；变更工单统一提交，失败回滚，不执行 `CREATE DATABASE`、`VACUUM`、`CREATE INDEX CONCURRENTLY` 等要求在事务外运行的操作。

[文档目录](README.md)
