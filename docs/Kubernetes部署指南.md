# Kubernetes 部署指南

仓库 [k8s/sxdevops.yaml](../k8s/sxdevops.yaml) 是单副本基础示例，包含应用、CMDB 调度器、MySQL 8、Redis 7 与 PVC；尚未包含 AIOps worker。正式部署需补齐下面的配置与 worker，已有环境升级另见 [v2 升级说明](releases/v2.0.0-release-guide.md)。

## 部署前准备

- 集群有可用 StorageClass 或预先准备的 PV，支持 `ReadWriteOnce`。
- 应用镜像由 CI/CD 或独立构建机从固定提交构建，并推送到节点可访问的 OCI 仓库；Kubernetes 节点不负责构建镜像。
- 将应用、调度器和新增 worker 的镜像替换为同一固定版本或 digest。清单原有的 `v1.0.0` 地址只是占位示例，不是当前发行镜像。
- 私有仓库认证通过 `imagePullSecrets` 提供，基础镜像也需满足集群网络策略。

仅在私有部署副本中配置真实参数，不把密钥提交回公共仓库。

## Secret 与应用配置

为 `sxdevops-secrets` 提供独立的 `MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD`、`SECRET_KEY`，并新增 `CMDB_PASSWORD_ENCRYPTION_KEY`。已有环境沿用原 Fernet 密钥；丢失或更换后无法解密旧凭据。

建议由受控 Secret 管理工具或发布流程提供对象。若外部管理同名 Secret，先从部署副本中移除示例 Secret 文档，避免 `apply` 重新写回示例密码。

在 `sxdevops-config` 中明确配置：

```yaml
ALLOWED_HOSTS: "<实际访问域名,必要的本机地址>"
CORS_ALLOW_ALL_ORIGINS: "0"
AIOPS_LANGGRAPH_CHECKPOINT_BACKEND: mysql
SXDEVOPS_SEED_DATA: "0"
```

所有应用进程共享数据库、Redis 和必要密钥。首次部署可以由单副本应用执行迁移；已有环境升级或多副本部署时，应让 Web、调度器及 worker 停止写入，由独立迁移 Job 执行一次完整迁移，再启动服务，避免滚动更新时并发迁移。正式环境模板同步也应按需独立执行。

## AIOps worker 与共享 checkpoint

在应用和 worker 读取的 ConfigMap 中设置 MySQL checkpoint 后，新增以下 Deployment，并替换镜像。私有仓库的 `imagePullSecrets` 也需配置到 worker。

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sxdevops-aiops-chat-worker
  namespace: sxdevops
spec:
  replicas: 1
  selector:
    matchLabels:
      app: sxdevops-aiops-chat-worker
  template:
    metadata:
      labels:
        app: sxdevops-aiops-chat-worker
    spec:
      containers:
        - name: worker
          image: your-registry/sxdevops:v2.0.0
          args: ["python", "manage.py", "run_aiops_chat_worker", "--interval", "2"]
          envFrom:
            - configMapRef:
                name: sxdevops-config
            - secretRef:
                name: sxdevops-secrets
          env:
            - name: SXDEVOPS_MIGRATE
              value: "0"
            - name: SXDEVOPS_SEED_DATA
              value: "0"
            - name: SXDEVOPS_SEED_TEMPLATES
              value: "0"
```

worker 沿用镜像入口等待数据库，部署前先完成迁移。MySQL checkpoint 保存在数据库中；若另有运行文件，按实际需求挂载持久存储。不要给不同 Pod 配置各自本地 SQLite checkpoint 来共享异步任务。

## 启动与验证

下面命令中的路径应替换为已完成上述配置的私有部署清单；worker 单独保存时也需应用。不要直接使用公共示例默认密码上线。

```bash
kubectl apply -f <私有部署清单>
kubectl -n sxdevops rollout status deployment/mysql --timeout=5m
kubectl -n sxdevops rollout status deployment/redis --timeout=5m
kubectl -n sxdevops rollout status deployment/sxdevops --timeout=10m
kubectl -n sxdevops rollout status deployment/cmdb-sync-scheduler --timeout=5m
kubectl -n sxdevops rollout status deployment/sxdevops-aiops-chat-worker --timeout=5m
kubectl -n sxdevops exec deployment/sxdevops -- python manage.py createsuperuser
kubectl -n sxdevops port-forward service/sxdevops 8000:8000
```

访问 `http://127.0.0.1:8000`。平台不提供默认密码；`seed_data` 不创建账号，也不要在业务数据库导入演示数据。

检查 Pod、存储、迁移和后台服务：

```bash
kubectl -n sxdevops get pods,svc,pvc
kubectl -n sxdevops exec deployment/sxdevops -- python manage.py check
kubectl -n sxdevops exec deployment/sxdevops -- python manage.py showmigrations
kubectl -n sxdevops logs deployment/sxdevops --tail=100
kubectl -n sxdevops logs deployment/cmdb-sync-scheduler --tail=100
kubectl -n sxdevops logs deployment/sxdevops-aiops-chat-worker --tail=100
```

外部域名通过 HTTPS Ingress 暴露应用 8000 端口，启用 WebSocket Upgrade 并验证超时。MySQL 和 Redis 保持内部访问。CMDB 调度器维持单副本；worker 与应用配置变更后要重启对应 Pod，使环境变量生效。

## 持久化、升级与回退

MySQL 与 Redis 分别使用 `mysql-data`、`redis-data` PVC。**不要用 `kubectl delete -f k8s/sxdevops.yaml` 升级：清单包含 Namespace 和 PVC，删除会危及持久数据；删除 Namespace 也会删除其中资源。** PV 是否保留还取决于存储回收策略。

升级前排空任务，备份数据库、checkpoint、私有配置、加密密钥及必要卷，并验证恢复点。保持三项应用镜像一致；数据库迁移完成后再启动新服务。`rollout undo` 只回退 Deployment，不能回退数据库迁移或状态变化；回退按[运维指南](deployment.md#回退)处理。

## 常见问题

| 现象 | 检查 |
| --- | --- |
| PVC Pending | `kubectl get storageclass`，核对 storageClassName、容量和访问模式 |
| ImagePullBackOff | 镜像是否存在、节点网络与仓库认证、worker 是否也配置拉取密钥 |
| 应用启动等待超时 | MySQL 状态、Secret、连接配置和迁移日志 |
| 聊天排队不处理 | worker、共享 MySQL checkpoint、数据库一致性与图版本 |
| 周期采集不执行 | 调度器是否运行、任务启用与到期时间、来源凭据权限 |

[文档目录](README.md)
