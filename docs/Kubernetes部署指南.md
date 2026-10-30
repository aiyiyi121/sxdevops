# Kubernetes 部署指南

推荐使用 [k8s/deploy.py](../k8s/deploy.py) 一键部署。只需填写一次应用镜像地址，脚本自动生成密钥、配置存储、执行迁移、启动服务并引导设置管理员密码。Web、CMDB 调度器、AIOps worker 及两个 schema 初始化容器使用同一应用镜像，默认共享 PostgreSQL、Redis 和 PostgreSQL checkpoint；MySQL 保留为备选。

## 一键部署

执行脚本的电脑、跳板机或 CI 主机需要 Python 3 和 `kubectl`，能够通过 kubeconfig 连接目标集群即可，无需安装 Python 第三方依赖。应用及数据库运行在目标 Kubernetes 集群。集群需要默认 StorageClass，或为下述命令指定可用存储类；也可提前准备好 `postgres-data`、`redis-data` PVC（MySQL 备选使用 `mysql-data`）。应用镜像必须已存在，并能被集群所有节点拉取。

在仓库根目录执行，将示例地址替换为**自己的固定版本镜像或 digest**：

```bash
python3 k8s/deploy.py registry.example.com/your-team/sxdevops:v2.0.0
```

Windows 将 `python3` 换为 `python`。`registry.example.com` 是占位地址，仓库未提供该地址的发行镜像；脚本会拒绝占位镜像和 `latest`，避免误用。

通过 `--kubeconfig` 指定远程集群连接文件；文件内有多个 context 时，可用 `--context` 选择：

```bash
python3 k8s/deploy.py registry.example.com/your-team/sxdevops:v2.0.0 --kubeconfig ./kubeconfig --context production
```

将镜像、配置文件路径和 context 名称换成自己的值。所有资源查询、创建、迁移、管理员初始化及端口转发都会使用同一 kubeconfig 和 context，不修改文件中保存的 `current-context`。不指定这些参数时，沿用 kubectl 的 `KUBECONFIG` 环境变量或 `~/.kube/config` 及其当前 context。指定文件不存在时直接报错，不回退到默认集群。

运行后自动完成：

1. 创建 `sxdevops` 命名空间，生成独立随机的数据库密码、Django 密钥及 CMDB Fernet 密钥，保存为 `sxdevops-secrets`。
2. 创建 PostgreSQL / Redis PVC 和服务，等待卷绑定及数据库就绪。
3. 在独立 `sxdevops-migrate` Job 中执行迁移；新环境同时初始化任务模板。此时三个应用 Deployment 保持零副本。
4. 迁移成功后启动 Web、CMDB 调度器和 AIOps worker，并等待三者就绪。
5. 首次按提示输入并确认 `admin` 密码，然后自动开启本地端口转发。

打开 [登录页](http://127.0.0.1:8000/login)，使用 `admin` 和刚设置的密码登录。这里的本地地址是执行脚本机器上的隧道入口，服务运行在 kubeconfig 指向的集群。已有管理员时沿用原账号和密码，不重新设置。平台没有固定默认密码，也不会导入演示业务数据。

保持终端开启即可访问；`Ctrl+C` 仅停止当前命令或本地隧道，不删除集群资源。若在迁移或发布阶段中断，可执行相同命令继续；尚在运行的迁移 Job 会被复用，避免并发执行第二份迁移。

## 常用选项

| 选项 | 用途 |
| --- | --- |
| `--kubeconfig ./kubeconfig` | 指定目标集群连接文件；省略时沿用 kubectl 的默认配置解析规则 |
| `--context production` | 选择 kubeconfig 中的 context，不修改已保存的当前 context |
| `--database mysql` | 新安装选择 MySQL 8；省略默认 PostgreSQL 16，已有环境沿用 ConfigMap 中的数据库类型，禁止直接切换引擎 |
| `--namespace my-sxdevops` | 使用其他命名空间，默认 `sxdevops` |
| `--storage-class fast-storage` | 为新 PVC 指定存储类；已有 PVC 保留原配置，不能用该选项更换存储 |
| `--image-pull-secret registry-auth` | 引用目标命名空间内已有的私有仓库认证 Secret，同时用于应用、schema 初始化容器和迁移 Job |
| `--port 18000` | 改用本地 18000 端口访问 |
| `--no-port-forward` | 部署完成后退出，不开启本地隧道 |
| `--skip-admin` | 自动化部署时跳过管理员交互；之后需另行设置管理员 |
| `--upgrade` | 进入维护更新：停止旧应用进程，执行迁移，再启动同版本的三个服务 |

例如指定存储类和私有仓库认证：

```bash
python3 k8s/deploy.py registry.example.com/your-team/sxdevops:v2.0.0 --storage-class fast-storage --image-pull-secret registry-auth
```

私有镜像认证须提前放到目标命名空间，可复用已有的 registry Secret；脚本不收集或保存仓库登录密码。若集群没有默认 StorageClass，也没有预先绑定的 PVC，需要先提供存储，部署脚本无法代替集群存储系统。

## 镜像准备

Kubernetes 节点只拉取镜像，不构建源码。如果尚无应用镜像，先由 CI/CD 或独立构建机从当前版本源码构建并推送：

```bash
docker build -t registry.example.com/your-team/sxdevops:v2.0.0 .
docker push registry.example.com/your-team/sxdevops:v2.0.0
```

上述地址同样需要替换。镜像应包含 `quickstart_admin` 管理命令；发布后保持标签不可变，或使用 `image@sha256:...`。PostgreSQL 16（或备选 MySQL 8）、Redis 7 和 BusyBox 的基础镜像也必须满足节点网络策略。

## 密钥与配置

密钥由脚本自动生成，经标准输入提交给 Kubernetes，不写入公共 YAML 或命令行参数。重复运行会复用现有 Secret；若检测到已有数据库或应用却缺少 Secret，脚本会停止并提示恢复原 Secret，不生成新密钥覆盖旧环境。

**请备份 `sxdevops-secrets`，已有 CMDB 凭据必须沿用原 Fernet 密钥。** 仅恢复数据库不足以恢复加密凭据。PostgreSQL Secret 需包含 `POSTGRES_PASSWORD`、`SECRET_KEY` 和 `CMDB_PASSWORD_ENCRYPTION_KEY`；MySQL 使用 `MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD` 及相同两项应用密钥。缺失时应补回原值。

应用、调度器、worker 和迁移 Job 只引用必要的应用密钥；`MYSQL_ROOT_PASSWORD` 仅供 MySQL 使用。共享 checkpoint 默认保存在 PostgreSQL 中（MySQL 备选保存在 MySQL 中），不使用各 Pod 独立的 SQLite 文件。

首次默认使用 [PostgreSQL 清单](../k8s/sxdevops.yaml)，指定 `--database mysql` 时使用 [MySQL 清单](../k8s/sxdevops-mysql.yaml)，按所选清单的基础配置创建 `sxdevops-config`。已有 ConfigMap 的配置会被保留，包括数据库连接、域名及可信代理。公开访问前按[配置参考](configuration.md)明确设置 `ALLOWED_HOSTS`、`CORS_ALLOW_ALL_ORIGINS=0` 和实际的 `SXDEVOPS_TRUSTED_PROXIES`，通过 HTTPS Ingress 暴露应用 8000 端口并支持 WebSocket；PostgreSQL / MySQL / Redis 保持内部访问。

基础 YAML 已移除示例密码和 Secret 对象。若选择手工维护清单，须自己提供 Secret，并替换全部应用镜像。使用脚本部署后，后续继续用脚本维护，避免直接 `apply` 基础示例覆盖现有配置及迁移策略。

## 再次启动与升级

重复执行相同镜像的部署命令，会检查并等待已有服务、按需初始化管理员，再开启本地隧道；正常运行的应用、Secret 和配置不会被重新部署。

升级前进入维护窗口，排空聊天、执行任务与待确认动作，备份数据库、checkpoint、Secret、私有配置和卷，并验证恢复点。随后以新镜像运行：

```bash
python3 k8s/deploy.py registry.example.com/your-team/sxdevops:v2.0.1 --upgrade
```

脚本先将 Web、CMDB 调度器和 AIOps worker 缩至零副本并等待旧 Pod 退出，再更新配置、执行一次独立迁移 Job。迁移成功后启动三个同版本服务；迁移失败则保持应用停止，输出对应 Job 的日志命令，避免新旧代码继续写入。升级不自动重新同步任务模板；确需同步时按[运维指南](deployment.md)独立评估并执行。

CMDB 调度器保持单副本；worker 的 schema 初始化容器只检查迁移状态，不执行迁移。相同镜像下修改配置后，也可使用 `--upgrade` 在维护窗口重新部署；配置仍以现有 ConfigMap 为准。

默认 PostgreSQL 与 Redis 使用 `postgres-data`、`redis-data` PVC（MySQL 备选使用 `mysql-data`）。**不要用 `kubectl delete -f k8s/sxdevops.yaml` 升级，也不要删除 Namespace 或 PVC。** `rollout undo` 只回退 Deployment，不能回退数据库迁移；回退按[运维指南](deployment.md#回退)处理。图版本升级前应处理未完成的验证，不能假设 checkpoint 可跨图版本恢复。

## 验证与排查

以下命令按默认 kubeconfig / context 展示。部署时使用了 `--kubeconfig` 或 `--context`，排查、重设密码和端口转发时也要带相同参数，例如 `kubectl --kubeconfig ./kubeconfig --context production -n sxdevops get pods`。

```bash
kubectl -n sxdevops get pods,svc,pvc,jobs
kubectl -n sxdevops logs job/sxdevops-migrate --tail=100
kubectl -n sxdevops logs deployment/sxdevops --tail=100
kubectl -n sxdevops logs deployment/cmdb-sync-scheduler --tail=100
kubectl -n sxdevops logs deployment/aiops-chat-worker --tail=100
```

命名空间自定义时同步替换 `sxdevops`。迁移 Job 保留约一天后自动清理。自动化部署跳过管理员初始化后，可在交互终端执行：

```bash
kubectl -n sxdevops exec -it deployment/sxdevops -- python manage.py quickstart_admin
```

忘记已有 `admin` 密码时执行 `kubectl -n sxdevops exec -it deployment/sxdevops -- python manage.py changepassword admin`。

| 现象 | 检查 |
| --- | --- |
| PVC Pending / 绑定超时 | 核对默认 StorageClass、指定存储类、容量及访问模式 |
| ImagePullBackOff | 确认镜像存在、节点网络可达，私有仓库认证位于相同命名空间 |
| 迁移失败 / 应用保持零副本 | 查看 `job/sxdevops-migrate` 日志，修复后重复同一命令 |
| admin 初始化提示无交互终端 | 在交互终端运行；自动化部署可先跳过，再执行上述初始化命令 |
| 聊天排队不处理 | 检查 worker、PostgreSQL / MySQL checkpoint、数据库配置与图版本 |
| 周期采集不执行 | 检查调度器、任务启用状态及来源凭据权限 |

[文档目录](README.md)
