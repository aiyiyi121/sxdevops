# vSphere 虚拟机真实运行指标接入

vSphere 继续采集虚拟机清单、规格、电源状态、宿主机和集群信息。CPU、内存和根分区使用量优先从 Prometheus 的 `node_exporter` 取得：

- CPU：`100 - idle`，口径接近 `top` 汇总行。
- 内存：`MemTotal - MemAvailable`，口径接近新版 `free -h`。
- 磁盘：根分区 `size - free`，使用率为 `used / (used + avail)`，口径接近 `df -h /`。
- Prometheus 无法访问、target 未匹配或某项指标缺失时，仅缺失项回退到 vSphere 值。

指标只存入资产水位快照。资产详情的“资产水位”列表和列表悬停信息会标注采集来源与采集时间；不会写入模型字段、扩展属性或资产变更记录。

## 1. 部署并抓取 node_exporter

在每台需要采集的 Linux 虚拟机部署 `node_exporter`（默认端口 `9100`），并让 Prometheus 抓取。示例：

```yaml
scrape_configs:
  - job_name: node-exporter
    static_configs:
      - targets:
          - 192.0.2.8:9100
          - 192.0.2.9:9100
```

在 Prometheus 查询页确认下列指标有返回值：`node_cpu_seconds_total`、`node_memory_MemTotal_bytes`、`node_memory_MemAvailable_bytes`、`node_filesystem_size_bytes`、`node_filesystem_free_bytes`、`node_filesystem_avail_bytes`。

## 2. 在平台创建指标数据源

进入“可观测性 → 指标查询 → 指标数据源”，新增 Prometheus 数据源：

- 类型：`Prometheus Like`
- 查询地址：例如 `http://prometheus.internal:9090`（填写 Prometheus API 地址，不要加 `/api/v1/query`）
- 启用：打开；同一环境建议设为默认数据源
- 认证：按 Prometheus 网关配置填写无认证、Basic Auth 或 Bearer Token

保存后使用“测试连接”，以 `up` PromQL 验证 SXDevOps 后端能访问 Prometheus。vSphere 同步会优先选择任务指定的数据源；未指定时，选择与任务环境相同的默认数据源，再回退到全局默认数据源。

## 3. 启用 vSphere 同步任务

进入“CMDB → 资产采集”，编辑 vSphere 虚拟机同步任务并打开“真实指标”。默认即可按虚拟机 Guest IP 匹配 Prometheus 的 `instance` 标签，例如虚拟机 IP 为 `192.0.2.8` 会匹配 `instance="192.0.2.8:9100"`。

保存后执行一次同步或“重新同步当前页资产水位”。资产水位悬停提示会显示 `Prometheus node_exporter`；若显示 `vSphere 回退指标`，请查看提示中的回退原因。

## 可选任务配置

同步任务的 `config` 支持以下高级配置，通常只需要指定数据源或处理非标准标签：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `prometheus_metrics_enabled` | `true` | 是否启用真实指标采集 |
| `metric_datasource_id` | 空 | 指定指标数据源 ID；优先于默认数据源 |
| `prometheus_query_url` | 空 | 直接指定 Prometheus 查询地址；仅适合无认证地址 |
| `prometheus_instance_label` | `instance` | Prometheus target 标签名 |
| `prometheus_node_selector` | 空 | 附加标签选择器，例如 `job="node-exporter"` |
| `prometheus_cpu_window` | `1m` | CPU `rate` 时间窗口 |
| `prometheus_root_mountpoint` | `/` | 根分区挂载点 |
| `prometheus_instance_map` | `{}` | 虚拟机 ID、名称或 IP 到 target 的显式映射 |
| `prometheus_queries` | `{}` | 覆盖默认 PromQL |

`prometheus_instance_map` 示例：

```json
{
  "vm-app-001": "192.0.2.8:9100",
  "192.0.2.9": "node-02.internal:9100"
}
```

认证信息优先维护在“指标数据源”，不要将密码或 Token 写入 CMDB 同步任务配置。

[文档目录](README.md)
