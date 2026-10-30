# 快速开始

本文用于本地开发或隔离体验。对外部署前先完成[部署配置](deployment.md)；已有数据库升级见 [v2.0.0 升级说明](releases/v2.0.0-release-guide.md)。

## Compose 体验

仓库的 [Compose 文件](../docker-compose.yml) 从源码构建镜像，并启动应用、PostgreSQL 16、Redis 7、CMDB 调度器和 AIOps worker。

安装并启动 Docker（含 Compose）后，在仓库根目录执行：

```bash
sh start.sh
```

Windows 用户执行 `.\start.cmd`，或直接双击 `start.cmd`，无需安装 Python / Node.js。

脚本自动完成密钥生成、镜像构建、服务启动、数据库迁移和任务模板同步。首次只需按提示输入并确认 `admin` 密码（终端不显示输入字符），然后打开 [登录页](http://localhost:8000/login)，使用 `admin` 和自己设置的密码登录。已有管理员时跳过创建，沿用原账号和密码。

密钥保存在仓库根目录的 `.env`，不会写入 Git；管理员密码不会保存到该文件（数据库随机密码会保存在其中）。重复运行启动脚本会保留已有 `.env` 和账号。请备份 `.env`，升级或恢复数据库时保留原密钥；检测到已有数据库却缺少 `.env` 时，脚本会停止并提示恢复原配置。

### 手动启动（可选）

如需自行管理配置，在仓库根目录创建 `.env`，密钥生成方法见[配置参考](configuration.md#密钥与访问入口)：

```dotenv
SECRET_KEY=<独立生成的长随机字符串>
CMDB_PASSWORD_ENCRYPTION_KEY=<独立生成的Fernet密钥>
POSTGRES_PASSWORD=<独立生成的数据库密码>
```

随后启动并创建管理员；等待应用迁移完成后再执行创建命令：

```bash
docker compose up -d --build
docker compose ps
docker compose exec sxdevops python manage.py createsuperuser --username admin
```

访问 `http://localhost:8000`，使用刚创建的账号登录。容器首次启动自动执行迁移和任务模板同步，默认不导入演示数据，也不提供固定登录密码。

新部署推荐 PostgreSQL，数据库密码由脚本随机生成。MySQL 8 仍可使用：Linux / macOS 执行 `sh start.sh --mysql`；Windows 执行 `.\start.cmd -Database mysql`，手动维护时改用 `docker-compose.mysql.yml`。已有 MySQL 部署继续使用此选项，不会自动迁移到 PostgreSQL。正式部署须先按[配置参考](configuration.md)覆盖；配置必须同步给应用、调度器和 worker。

## Kubernetes 部署

执行脚本的电脑或跳板机安装 Python 3 和 `kubectl`，确认能够连接目标集群、集群具备可用存储，以及节点能拉取应用镜像后，在仓库根目录执行（替换示例镜像）：

```bash
python3 k8s/deploy.py registry.example.com/your-team/sxdevops:v2.0.0
```

可追加 `--kubeconfig ./kubeconfig --context production` 选择远程集群；省略时使用 kubectl 默认配置。Windows 使用 `python`。脚本在目标集群自动生成 Secret、部署 PostgreSQL / Redis / 三项应用服务、执行独立迁移 Job，并引导设置管理员密码；完成后将服务转发到执行机的 `http://127.0.0.1:8000/login`。新安装追加 `--database mysql` 可使用 MySQL；已有安装保留原数据库类型。参数和升级步骤见[Kubernetes 部署指南](Kubernetes部署指南.md)。

## 本地开发

建议 Python 3.12、Node.js 20；这也是当前 [Dockerfile](../Dockerfile) 的运行基线。本地开发和测试继续使用 SQLite，不需要迁移现有测试库。新部署默认 PostgreSQL；本地开发先把 `backend/config.example.sqlite.json` 复制为 `backend/config.json`（已有 SQLite 配置保留即可），或在每个后端终端设置 `DATABASE_ENGINE=sqlite`。无需安装 PostgreSQL / MySQL。

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
