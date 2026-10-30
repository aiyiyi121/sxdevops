# 快速开始

本文用于本地开发或隔离体验。对外部署前先完成[部署配置](deployment.md)；已有数据库升级见 [v2.0.0 升级说明](releases/v2.0.0-release-guide.md)。

## Compose 体验

仓库的 [Compose 文件](../docker-compose.yml) 从源码构建镜像，并启动应用、MySQL 8、Redis 7、CMDB 调度器和 AIOps worker。

先在仓库根目录创建仅本机使用的 `.env`，填入独立随机值：

```dotenv
SECRET_KEY=<独立生成的长随机字符串>
```

可用 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成。`.env` 已被 Git 忽略。然后执行：

```bash
docker compose up -d --build
docker compose ps
docker compose exec sxdevops python manage.py createsuperuser
```

访问 `http://localhost:8000`，使用刚创建的账号登录。容器首次启动自动执行迁移和任务模板同步，默认不导入演示数据，也不提供固定登录密码。

基础 Compose 中的数据库密码、CMDB 加密密钥和开放 CORS 仅是示例值。正式部署须先按[配置参考](configuration.md)覆盖；配置必须同步给应用、调度器和 worker。

## 本地开发

建议 Python 3.12、Node.js 20；这也是当前 [Dockerfile](../Dockerfile) 的运行基线。默认使用 SQLite，不要求本地安装 MySQL。

在仓库根目录创建虚拟环境并激活：

```bash
python -m venv .venv
```

Windows PowerShell：`.\.venv\Scripts\Activate.ps1`；Linux / macOS：`source .venv/bin/activate`。随后启动后端：

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_templates
python -m daphne -b 127.0.0.1 -p 8000 sxdevops.asgi:application
```

另开终端，激活同一虚拟环境并运行异步聊天与处置验证 worker：

```bash
cd backend
python manage.py run_aiops_chat_worker --interval 2
```

若需要 CMDB 周期采集，再开一个终端运行 `python manage.py run_cmdb_sync_scheduler --interval 60 --limit 10`；只运行一个调度器实例。

前端另开终端：

```bash
cd frontend
npm ci
npm run dev
```

访问 `http://localhost:3000`。修改后端 Python 后需手动重启 Daphne；worker 也要加载同一版本的代码与配置。

## 演示数据与测试角色

仅对独立、可丢弃的数据库运行以下命令：

```bash
python manage.py seed_data
```

在 `backend` 目录执行，或使用 `docker compose exec sxdevops python manage.py seed_data`。该命令写入业务演示数据，不创建登录账号，不应在已有业务数据库上重复运行。

确需测试角色时，先在运行命令的进程中设置 `SXDEVOPS_DEMO_PASSWORD`，再执行 `python manage.py seed_rbac_demo`。它维护 `ops_demo`、`dev_demo`、`audit_demo`、`viewer_demo` 及相关用户组；不创建 `admin`、`demo` 或 `demo_ai`。未指定密码时会为新账号生成随机密码，**不会打印密码**；现有账号的密码和启用状态保持不变，但角色及用户组绑定会重新同步。

这些角色中包含运维管理和 staff 权限，不适合公网体验。公开演示应另建自定义只读角色，并隔离数据、凭据和执行网络，见[安全说明](user-permission-security.md#公开介绍与只读演示)。

## 下一步

1. 按[用户使用指南](用户使用文档.md)配置数据源、事件环境和知识环境。
2. 按 [CMDB 手册](CMDB使用手册.md)登记资产，再显式接入[任务资源](task-resource-cmdb.md)。
3. 配置模型、MCP 和 Skills，先验证只读查询，再按需要授权任务执行。

[文档目录](README.md)
