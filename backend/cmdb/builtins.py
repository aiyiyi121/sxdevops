from django.db import transaction
from django.db.models import Q

from .models import (
    CIField,
    CIModelGroup,
    CIRelationRule,
    CISourceMapping,
    CISyncJob,
    CIThresholdPolicy,
    CIType,
    ConfigItem,
)


MODEL_GROUPS = [
    {'code': 'business', 'name': '业务模型', 'description': '应用、系统与服务类模型。', 'sort_order': 10},
    {'code': 'compute', 'name': '计算资源', 'description': '虚拟机、云主机与容器计算资源。', 'sort_order': 20},
    {'code': 'database', 'name': '数据库', 'description': '关系型、文档型与云上数据库实例。', 'sort_order': 30},
    {'code': 'middleware', 'name': '中间件', 'description': '缓存、消息、搜索、注册配置中心等中间件资源。', 'sort_order': 40},
    {'code': 'storage', 'name': '存储', 'description': '对象存储、块存储、文件存储等容量资源。', 'sort_order': 50},
    {'code': 'bigdata', 'name': '大数据', 'description': 'Hadoop、Flink、ClickHouse、Hologres、MaxCompute、DataWorks 等大数据组件。', 'sort_order': 60},
    {'code': 'network', 'name': '网络与入口', 'description': '负载均衡、域名、网关与网络连接资源。', 'sort_order': 70},
    {'code': 'external', 'name': '其他资产', 'description': '第三方服务、办公物品及其合同、账号、供应商和保管信息。', 'sort_order': 80},
]


COMMON_FIELDS = [
    {'code': 'department', 'name': '部门', 'field_type': 'string', 'field_group': '归属信息', 'is_searchable': True, 'sort_order': 890},
]


WEB_ACCESS_ADDRESS_GROUP_CODES = {'middleware', 'bigdata'}
WEB_ACCESS_ADDRESS_TYPE_CODES = {'THIRD_PARTY_SERVICE'}
WEB_ACCESS_ADDRESS_FIELD = {
    'code': 'access_address',
    'name': '访问地址',
    'field_type': 'url',
    'field_group': '访问入口',
    'is_searchable': True,
    'sort_order': 880,
}


MANUAL_SYNC_FIELD_CODES = {
    'department',
    'owner',
    'owner_team',
    'ops_owner',
    'backup_plan',
    'contract_no',
    'expire_date',
    'service_expiry_date',
    'service_expire_warning_days',
    'cert_owner',
    'purchase_date',
    'asset_code',
    'item_category',
    'brand_model',
    'serial_number',
    'storage_location',
    'custodian',
    'usage_status',
}

OBSOLETE_MODEL_GROUP_CODES = {'data'}
OBSOLETE_CI_TYPE_MERGES = {
    'CLOUD_DATABASE': 'MYSQL',
    'EIP': 'ELASTIC_IP',
}
OBSOLETE_CI_TYPE_NAMES = {
    '云数据库': 'MYSQL',
    '机房服务器': 'IDC_SERVER',
    '物理机/宿主机': 'IDC_SERVER',
    'NAT 网关': 'NAT_GATEWAY',
    '弹性IP': 'ELASTIC_IP',
    '弹性 IP': 'ELASTIC_IP',
}
OBSOLETE_CI_TYPE_RETIRE_NAMES = {
    'Security Group',
    '安全组',
    'Docker环境',
    'vSphere资源统计',
    '数据仓库',
    'Spark',
    'Hive',
    'HBase',
    'Doris',
}
OBSOLETE_CI_TYPE_RETIRE_CODES = {
    'SECURITY_GROUP',
    'SPARK',
    'HIVE',
    'HBASE',
    'DORIS',
}
OBSOLETE_CI_TYPE_PURGE_NAMES = {'Security Group', '安全组'}
OBSOLETE_CI_TYPE_PURGE_CODES = {'SECURITY_GROUP'}
LEGACY_CI_TYPE_GROUP_MAPPINGS = {
    '物理机/宿主机': 'compute',
    'NAT 网关': 'network',
    '弹性 IP': 'network',
    '安全组': 'network',
    '防火墙': 'network',
}


MODEL_DEFINITIONS = [
    {
        'code': 'APP_SERVICE',
        'name': '应用服务',
        'group': 'business',
        'icon': 'Grid',
        'color': '#3b82f6',
        'description': '对外或对内提供业务能力的应用、服务或系统。',
        'fields': [
            {'code': 'service_code', 'name': '服务编码', 'field_type': 'string', 'field_group': '基础信息', 'required': True, 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'owner_team', 'name': '负责团队', 'field_type': 'string', 'field_group': '基础信息', 'required': True, 'is_searchable': True, 'sort_order': 20},
            {'code': 'language', 'name': '技术语言', 'field_type': 'string', 'field_group': '技术信息', 'sort_order': 30},
            {'code': 'repo', 'name': '代码仓库', 'field_type': 'url', 'field_group': '技术信息', 'sort_order': 40},
            {'code': 'tier', 'name': '服务等级', 'field_type': 'enum', 'field_group': '治理信息', 'options': [{'value': 'core', 'label': '核心'}, {'value': 'important', 'label': '重要'}, {'value': 'normal', 'label': '普通'}], 'sort_order': 50},
        ],
    },
    {
        'code': 'IDC_SERVER',
        'name': '物理机',
        'group': 'compute',
        'icon': 'Cpu',
        'color': '#475569',
        'description': '自建机房、托管机房或 vSphere / ESXi 中的物理宿主机。',
        'fields': [
            {'code': 'asset_sn', 'name': '资产序列号', 'field_type': 'string', 'field_group': '资产信息', 'required': True, 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'private_ip', 'name': '管理 IP', 'field_type': 'ip', 'field_group': '网络信息', 'required': False, 'is_searchable': True, 'sort_order': 20},
            {'code': 'idc', 'name': '机房/数据中心', 'field_type': 'string', 'field_group': '位置信息', 'required': False, 'is_searchable': True, 'sort_order': 30},
            {'code': 'rack', 'name': '机柜', 'field_type': 'string', 'field_group': '位置信息', 'sort_order': 40},
            {'code': 'u_position', 'name': 'U 位', 'field_type': 'string', 'field_group': '位置信息', 'sort_order': 45},
            {'code': 'lifecycle_status', 'name': '生命周期', 'field_type': 'enum', 'field_group': '生命周期', 'options': [
                {'value': 'pending_rack', 'label': '待上架'},
                {'value': 'running', 'label': '运行中'},
                {'value': 'maintenance', 'label': '维修中'},
                {'value': 'pending_offline', 'label': '待下线'},
                {'value': 'offline', 'label': '已下线'},
                {'value': 'retired', 'label': '已报废'},
            ], 'default': 'running', 'sort_order': 50},
            {'code': 'purchase_date', 'name': '采购日期', 'field_type': 'date', 'field_group': '资产信息', 'sort_order': 55},
            {'code': 'service_expiry_date', 'name': '服务到期日', 'field_type': 'date', 'field_group': '服务治理', 'sort_order': 60},
            {'code': 'service_expire_warning_days', 'name': '到期提醒提前天数', 'field_type': 'integer', 'field_group': '服务治理', 'default': 30, 'sort_order': 61},
            {'code': 'ops_owner', 'name': '运维负责人', 'field_type': 'string', 'field_group': '归属信息', 'is_searchable': True, 'sort_order': 65},
            {'code': 'vendor', 'name': '厂商', 'field_type': 'string', 'field_group': '硬件信息', 'sort_order': 70},
            {'code': 'model', 'name': '型号', 'field_type': 'string', 'field_group': '硬件信息', 'sort_order': 75},
            {'code': 'serial_number', 'name': '序列号', 'field_type': 'string', 'field_group': '硬件信息', 'is_searchable': True, 'sort_order': 80},
            {'code': 'cpu', 'name': 'CPU 核数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 85},
            {'code': 'memory_gb', 'name': '内存 GB', 'field_type': 'decimal', 'field_group': '资源规格', 'sort_order': 90},
            {'code': 'disk_gb', 'name': '磁盘 GB', 'field_type': 'decimal', 'field_group': '资源规格', 'sort_order': 95},
            {'code': 'host_name', 'name': '主机名', 'field_type': 'string', 'field_group': '虚拟化信息', 'is_searchable': True, 'sort_order': 100},
            {'code': 'datacenter', 'name': 'vSphere 数据中心', 'field_type': 'string', 'field_group': '虚拟化信息', 'is_searchable': True, 'sort_order': 105},
            {'code': 'cluster', 'name': 'vSphere 集群', 'field_type': 'string', 'field_group': '虚拟化信息', 'is_searchable': True, 'sort_order': 110},
            {'code': 'connection_state', 'name': '连接状态', 'field_type': 'string', 'field_group': '运行信息', 'sort_order': 115},
            {'code': 'power_state', 'name': '电源状态', 'field_type': 'string', 'field_group': '运行信息', 'sort_order': 120},
            {'code': 'maintenance_mode', 'name': '维护模式', 'field_type': 'boolean', 'field_group': '运行信息', 'sort_order': 125},
            {'code': 'esxi_version', 'name': 'ESXi 版本', 'field_type': 'string', 'field_group': '虚拟化信息', 'is_searchable': True, 'sort_order': 130},
            {'code': 'esxi_build', 'name': 'ESXi Build', 'field_type': 'string', 'field_group': '虚拟化信息', 'sort_order': 135},
            {'code': 'cpu_mhz', 'name': '单核 MHz', 'field_type': 'decimal', 'field_group': '资源规格', 'sort_order': 140},
            {'code': 'cpu_total_mhz', 'name': 'CPU 总 MHz', 'field_type': 'decimal', 'field_group': '资源规格', 'sort_order': 145},
            {'code': 'cpu_thread_count', 'name': 'CPU 线程数', 'field_type': 'integer', 'field_group': '硬件信息', 'sort_order': 170},
            {'code': 'cpu_package_count', 'name': 'CPU 插槽数', 'field_type': 'integer', 'field_group': '硬件信息', 'sort_order': 175},
        ],
    },
    {
        'code': 'CLOUD_SERVER',
        'name': '云主机(ECS)',
        'group': 'compute',
        'icon': 'Monitor',
        'color': '#64748b',
        'description': '云厂商虚拟机实例，优先支持阿里云 ECS 自动注册。',
        'fields': [
            {'code': 'instance_id', 'name': '实例 ID', 'field_type': 'string', 'field_group': '云资源信息', 'required': True, 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'private_ip', 'name': '私网 IP', 'field_type': 'ip', 'field_group': '网络信息', 'required': False, 'is_searchable': True, 'sort_order': 20},
            {'code': 'public_ip', 'name': '公网 IP', 'field_type': 'ip', 'field_group': '网络信息', 'is_searchable': True, 'sort_order': 30},
            {'code': 'instance_type', 'name': '实例规格', 'field_type': 'string', 'field_group': '资源规格', 'sort_order': 40},
            {'code': 'cpu', 'name': 'CPU 核数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 50},
            {'code': 'memory_gb', 'name': '内存 GB', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 60},
            {'code': 'disk_gb', 'name': '磁盘 GB', 'field_type': 'decimal', 'field_group': '资源规格', 'sort_order': 70},
            {'code': 'instance_status', 'name': '云上状态', 'field_type': 'enum', 'field_group': '运行信息', 'options': [{'value': 'Running', 'label': '运行中'}, {'value': 'Stopped', 'label': '已停止'}, {'value': 'Deleted', 'label': '已删除'}], 'sort_order': 80},
        ],
    },
    {
        'code': 'VIRTUAL_MACHINE',
        'name': '虚拟机',
        'group': 'compute',
        'icon': 'Platform',
        'color': '#0ea5e9',
        'description': '私有云或虚拟化平台中的虚拟机实例，当前支持 vSphere / ESXi 自动注册。',
        'fields': [
            {'code': 'instance_id', 'name': '实例 ID', 'field_type': 'string', 'field_group': '虚拟化信息', 'required': True, 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'private_ip', 'name': '私网 IP', 'field_type': 'ip', 'field_group': '网络信息', 'required': False, 'is_searchable': True, 'sort_order': 20},
            {'code': 'public_ip', 'name': '公网 IP', 'field_type': 'ip', 'field_group': '网络信息', 'is_searchable': True, 'sort_order': 30},
            {'code': 'instance_type', 'name': '硬件版本', 'field_type': 'string', 'field_group': '资源规格', 'sort_order': 40},
            {'code': 'cpu', 'name': 'CPU 核数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 50},
            {'code': 'memory_gb', 'name': '内存 GB', 'field_type': 'decimal', 'field_group': '资源规格', 'sort_order': 60},
            {'code': 'disk_gb', 'name': '磁盘 GB', 'field_type': 'decimal', 'field_group': '资源规格', 'sort_order': 70},
            {'code': 'datacenter', 'name': '数据中心', 'field_type': 'string', 'field_group': '虚拟化信息', 'is_searchable': True, 'sort_order': 80},
            {'code': 'cluster', 'name': '集群', 'field_type': 'string', 'field_group': '虚拟化信息', 'is_searchable': True, 'sort_order': 90},
            {'code': 'host', 'name': '宿主机', 'field_type': 'string', 'field_group': '虚拟化信息', 'is_searchable': True, 'sort_order': 100},
            {'code': 'folder', 'name': '文件夹', 'field_type': 'string', 'field_group': '虚拟化信息', 'sort_order': 110},
            {'code': 'os_type', 'name': '操作系统', 'field_type': 'string', 'field_group': '运行信息', 'sort_order': 120},
            {'code': 'instance_status', 'name': '运行状态', 'field_type': 'enum', 'field_group': '运行信息', 'options': [{'value': 'Running', 'label': '运行中'}, {'value': 'Stopped', 'label': '已停止'}, {'value': 'Deleted', 'label': '已删除'}], 'sort_order': 130},
        ],
    },
    {
        'code': 'K8S_CLUSTER',
        'name': 'K8s 集群',
        'group': 'compute',
        'icon': 'Cluster',
        'color': '#0ea5e9',
        'description': 'Kubernetes 集群及其运行入口信息。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '基础信息', 'required': True, 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'api_server', 'name': 'API Server', 'field_type': 'url', 'field_group': '连接信息', 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '基础信息', 'sort_order': 30},
            {'code': 'node_count', 'name': '节点数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
        ],
    },
    {
        'code': 'MYSQL',
        'name': 'MySQL',
        'group': 'database',
        'icon': 'Coin',
        'color': '#f97316',
        'description': '自建或云上 MySQL/RDS 实例。',
        'fields': [
            {'code': 'instance_id', 'name': '实例 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'required': True, 'is_searchable': True, 'sort_order': 20},
            {'code': 'port', 'name': '端口', 'field_type': 'integer', 'field_group': '连接信息', 'sort_order': 30},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 40},
            {'code': 'storage_gb', 'name': '存储 GB', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 50},
        ],
    },
    {
        'code': 'POSTGRESQL',
        'name': 'PostgreSQL',
        'group': 'database',
        'icon': 'Coin',
        'color': '#2563eb',
        'description': '自建或云上 PostgreSQL 实例，覆盖核心业务库与分析型库台账。',
        'fields': [
            {'code': 'instance_id', 'name': '实例 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'required': True, 'is_searchable': True, 'sort_order': 20},
            {'code': 'port', 'name': '端口', 'field_type': 'integer', 'field_group': '连接信息', 'default': 5432, 'sort_order': 30},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 40},
            {'code': 'storage_gb', 'name': '存储 GB', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 50},
            {'code': 'replica_count', 'name': '副本数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 60},
        ],
    },
    {
        'code': 'REDIS',
        'name': 'Redis',
        'group': 'middleware',
        'icon': 'Collection',
        'color': '#ef4444',
        'description': '自建或云上 Redis/Tair 缓存实例。',
        'fields': [
            {'code': 'instance_id', 'name': '实例 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'required': True, 'is_searchable': True, 'sort_order': 20},
            {'code': 'port', 'name': '端口', 'field_type': 'integer', 'field_group': '连接信息', 'sort_order': 30},
            {'code': 'memory_gb', 'name': '内存 GB', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
        ],
    },
    {
        'code': 'MONGODB',
        'name': 'MongoDB',
        'group': 'database',
        'icon': 'Document',
        'color': '#16a34a',
        'description': '自建或云上 MongoDB 实例，承接文档数据库台账和后续云 API 同步。',
        'fields': [
            {'code': 'instance_id', 'name': '实例 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'port', 'name': '端口', 'field_type': 'integer', 'field_group': '连接信息', 'sort_order': 30},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 40},
            {'code': 'storage_gb', 'name': '存储 GB', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 50},
            {'code': 'replica_count', 'name': '副本数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 60},
            {'code': 'vpc_id', 'name': 'VPC', 'field_type': 'string', 'field_group': '网络信息', 'is_searchable': True, 'sort_order': 70},
        ],
    },
    {
        'code': 'KAFKA',
        'name': 'Kafka',
        'group': 'middleware',
        'icon': 'MessageBox',
        'color': '#7c3aed',
        'description': 'Kafka 集群、Topic、分区和消息堆积治理入口。',
        'fields': [
            {'code': 'instance_id', 'name': '实例 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '接入点', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 30},
            {'code': 'topic_count', 'name': 'Topic 数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
            {'code': 'partition_count', 'name': '分区数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 50},
            {'code': 'storage_gb', 'name': '存储 GB', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 60},
            {'code': 'message_lag', 'name': '消息堆积', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 70},
            {'code': 'vpc_id', 'name': 'VPC', 'field_type': 'string', 'field_group': '网络信息', 'is_searchable': True, 'sort_order': 80},
        ],
    },
    {
        'code': 'ROCKETMQ',
        'name': 'RocketMQ',
        'group': 'middleware',
        'icon': 'MessageBox',
        'color': '#9333ea',
        'description': 'RocketMQ 实例、接入点、Topic 和 Consumer Group 台账。',
        'fields': [
            {'code': 'instance_id', 'name': '实例 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '接入点', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'http_endpoint', 'name': 'HTTP 接入点', 'field_type': 'url', 'field_group': '连接信息', 'sort_order': 30},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 40},
            {'code': 'topic_count', 'name': 'Topic 数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 50},
            {'code': 'group_count', 'name': 'Group 数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 60},
            {'code': 'message_lag', 'name': '消息堆积', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 70},
            {'code': 'vpc_id', 'name': 'VPC', 'field_type': 'string', 'field_group': '网络信息', 'is_searchable': True, 'sort_order': 80},
        ],
    },
    {
        'code': 'MIDDLEWARE',
        'name': '中间件',
        'group': 'middleware',
        'icon': 'Operation',
        'color': '#8b5cf6',
        'description': 'Kafka、RocketMQ、Elasticsearch、MongoDB 等共享中间件资源。',
        'fields': [
            {'code': 'middleware_type', 'name': '中间件类型', 'field_type': 'enum', 'field_group': '基础信息', 'required': True, 'options': [{'value': 'kafka', 'label': 'Kafka'}, {'value': 'rocketmq', 'label': 'RocketMQ'}, {'value': 'elasticsearch', 'label': 'Elasticsearch'}, {'value': 'mongodb', 'label': 'MongoDB'}], 'sort_order': 10},
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 20},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'sort_order': 30},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '基础信息', 'sort_order': 40},
        ],
    },
    {
        'code': 'ELASTICSEARCH',
        'name': 'Elasticsearch',
        'group': 'middleware',
        'icon': 'DataAnalysis',
        'color': '#0891b2',
        'description': 'Elasticsearch 集群、节点、索引容量和查询入口台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 30},
            {'code': 'node_count', 'name': '节点数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
            {'code': 'index_count', 'name': '索引数', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 50},
            {'code': 'storage_gb', 'name': '存储 GB', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 60},
        ],
    },
    {
        'code': 'RABBITMQ',
        'name': 'RabbitMQ',
        'group': 'middleware',
        'icon': 'MessageBox',
        'color': '#f97316',
        'description': 'RabbitMQ 集群、队列、交换机和消息堆积台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '接入点', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 30},
            {'code': 'queue_count', 'name': '队列数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
            {'code': 'message_lag', 'name': '消息堆积', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 50},
        ],
    },
    {
        'code': 'EMQX',
        'name': 'EMQX',
        'group': 'middleware',
        'icon': 'Connection',
        'color': '#10b981',
        'description': 'EMQX MQTT 消息接入集群、Broker 节点和连接规模台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '接入地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 30},
            {'code': 'node_count', 'name': '节点数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
            {'code': 'connection_count', 'name': '连接数', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 50},
            {'code': 'topic_count', 'name': 'Topic 数', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 60},
        ],
    },
    {
        'code': 'NACOS',
        'name': 'Nacos',
        'group': 'middleware',
        'icon': 'Service',
        'color': '#2563eb',
        'description': 'Nacos 注册中心和配置中心实例台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 30},
            {'code': 'namespace_count', 'name': '命名空间数', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 40},
            {'code': 'service_count', 'name': '服务数', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 50},
        ],
    },
    {
        'code': 'APISIX',
        'name': 'APISIX',
        'group': 'middleware',
        'icon': 'Connection',
        'color': '#2563eb',
        'description': 'APISIX API 网关集群、路由和管理入口台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'admin_endpoint', 'name': '管理地址', 'field_type': 'url', 'field_group': '连接信息', 'sort_order': 30},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 40},
            {'code': 'deployment_mode', 'name': '部署方式', 'field_type': 'enum', 'field_group': '部署信息', 'options': [{'value': 'vm', 'label': '虚拟机'}, {'value': 'k8s', 'label': 'K8s 集群'}], 'sort_order': 50},
            {'code': 'instance_count', 'name': '实例数量', 'field_type': 'integer', 'field_group': '部署信息', 'sort_order': 60},
            {'code': 'route_count', 'name': '路由数量', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 70},
        ],
    },
    {
        'code': 'SKYWALKING',
        'name': 'SkyWalking',
        'group': 'middleware',
        'icon': 'DataLine',
        'color': '#8b5cf6',
        'description': 'SkyWalking 可观测性平台、OAP 集群与服务拓扑台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 30},
            {'code': 'deployment_mode', 'name': '部署方式', 'field_type': 'enum', 'field_group': '部署信息', 'options': [{'value': 'vm', 'label': '虚拟机'}, {'value': 'k8s', 'label': 'K8s 集群'}], 'sort_order': 40},
            {'code': 'instance_count', 'name': '实例数量', 'field_type': 'integer', 'field_group': '部署信息', 'sort_order': 50},
            {'code': 'service_count', 'name': '服务数量', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 60},
        ],
    },
    {
        'code': 'ZOOKEEPER',
        'name': 'ZooKeeper',
        'group': 'middleware',
        'icon': 'Share',
        'color': '#7c3aed',
        'description': 'ZooKeeper 集群、节点与会话状态台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 30},
            {'code': 'node_count', 'name': '节点数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
        ],
    },
    {
        'code': 'OBJECT_STORAGE',
        'name': '对象存储',
        'group': 'storage',
        'icon': 'FolderOpened',
        'color': '#06b6d4',
        'description': 'OSS、COS、S3 等对象存储桶。',
        'fields': [
            {'code': 'bucket', 'name': 'Bucket', 'field_type': 'string', 'field_group': '基础信息', 'required': True, 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'url', 'field_group': '连接信息', 'sort_order': 20},
            {'code': 'storage_gb', 'name': '容量 GB', 'field_type': 'decimal', 'field_group': '容量信息', 'sort_order': 30},
        ],
    },
    {
        'code': 'BLOCK_STORAGE',
        'name': '块存储',
        'group': 'storage',
        'icon': 'Files',
        'color': '#0ea5e9',
        'description': '云盘、裸盘、虚拟化卷等块设备存储台账。',
        'fields': [
            {'code': 'volume_id', 'name': '卷 ID', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'volume_type', 'name': '卷类型', 'field_type': 'string', 'field_group': '基础信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'capacity_gb', 'name': '容量 GB', 'field_type': 'decimal', 'field_group': '容量信息', 'sort_order': 30},
            {'code': 'iops', 'name': 'IOPS', 'field_type': 'integer', 'field_group': '性能信息', 'sort_order': 40},
            {'code': 'attached_to', 'name': '挂载资源', 'field_type': 'string', 'field_group': '挂载信息', 'is_searchable': True, 'sort_order': 50},
        ],
    },
    {
        'code': 'FILE_STORAGE',
        'name': '文件存储',
        'group': 'storage',
        'icon': 'Folder',
        'color': '#14b8a6',
        'description': 'NAS、NFS、SMB 等共享文件存储台账。',
        'fields': [
            {'code': 'filesystem_id', 'name': '文件系统 ID', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'mount_target', 'name': '挂载点', 'field_type': 'string', 'field_group': '挂载信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'protocol', 'name': '协议', 'field_type': 'enum', 'field_group': '基础信息', 'options': [{'value': 'nfs', 'label': 'NFS'}, {'value': 'smb', 'label': 'SMB'}, {'value': 'posix', 'label': 'POSIX'}], 'sort_order': 30},
            {'code': 'capacity_gb', 'name': '容量 GB', 'field_type': 'decimal', 'field_group': '容量信息', 'sort_order': 40},
            {'code': 'used_gb', 'name': '已用 GB', 'field_type': 'decimal', 'field_group': '容量信息', 'sort_order': 50},
        ],
    },
    {
        'code': 'HADOOP',
        'name': 'Hadoop',
        'group': 'bigdata',
        'icon': 'DataBoard',
        'color': '#f59e0b',
        'description': 'Hadoop / HDFS / YARN 集群台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '基础信息', 'sort_order': 30},
            {'code': 'node_count', 'name': '节点数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
            {'code': 'storage_gb', 'name': '存储 GB', 'field_type': 'decimal', 'field_group': '资源规格', 'sort_order': 50},
        ],
    },
    {
        'code': 'SPARK',
        'name': 'Spark',
        'group': 'bigdata',
        'icon': 'TrendCharts',
        'color': '#f97316',
        'description': 'Spark 计算集群、任务入口和资源队列台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'master_url', 'name': 'Master 地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '基础信息', 'sort_order': 30},
            {'code': 'worker_count', 'name': 'Worker 数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
        ],
    },
    {
        'code': 'FLINK',
        'name': 'Flink',
        'group': 'bigdata',
        'icon': 'DataLine',
        'color': '#0ea5e9',
        'description': 'Flink 集群、作业入口、Slot 和实时计算资源台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'jobmanager_url', 'name': 'JobManager 地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '基础信息', 'sort_order': 30},
            {'code': 'slot_count', 'name': 'Slot 数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
        ],
    },
    {
        'code': 'HIVE',
        'name': 'Hive',
        'group': 'bigdata',
        'icon': 'DataAnalysis',
        'color': '#8b5cf6',
        'description': 'Hive Metastore、查询入口和数据仓库服务台账。',
        'fields': [
            {'code': 'service_id', 'name': '服务 ID', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'metastore_url', 'name': 'Metastore 地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '基础信息', 'sort_order': 30},
            {'code': 'database_count', 'name': '库数量', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 40},
        ],
    },
    {
        'code': 'HBASE',
        'name': 'HBase',
        'group': 'bigdata',
        'icon': 'Collection',
        'color': '#16a34a',
        'description': 'HBase 集群、RegionServer 和表容量台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '基础信息', 'sort_order': 30},
            {'code': 'regionserver_count', 'name': 'RegionServer 数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
            {'code': 'table_count', 'name': '表数量', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 50},
        ],
    },
    {
        'code': 'CLICKHOUSE',
        'name': 'ClickHouse',
        'group': 'bigdata',
        'icon': 'Histogram',
        'color': '#eab308',
        'description': 'ClickHouse 集群、分片、副本和分析库容量台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '基础信息', 'sort_order': 30},
            {'code': 'shard_count', 'name': '分片数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
            {'code': 'replica_count', 'name': '副本数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 50},
        ],
    },
    {
        'code': 'HOLOGRES',
        'name': 'Hologres',
        'group': 'bigdata',
        'icon': 'Histogram',
        'color': '#2563eb',
        'description': '阿里云 Hologres 实例、计算规格、存储容量和连接地址台账。',
        'fields': [
            {'code': 'instance_id', 'name': '实例 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 30},
            {'code': 'cpu', 'name': '计算核数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
            {'code': 'storage_gb', 'name': '存储 GB', 'field_type': 'decimal', 'field_group': '资源规格', 'sort_order': 50},
        ],
    },
    {
        'code': 'MAXCOMPUTE',
        'name': 'MaxCompute',
        'group': 'bigdata',
        'icon': 'DataBoard',
        'color': '#0ea5e9',
        'description': '阿里云 MaxCompute 项目、配额、存储和任务规模台账。',
        'fields': [
            {'code': 'project_name', 'name': '项目名称', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'region', 'name': '地域', 'field_type': 'string', 'field_group': '基础信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'quota_name', 'name': '计算配额', 'field_type': 'string', 'field_group': '资源规格', 'is_searchable': True, 'sort_order': 30},
            {'code': 'storage_gb', 'name': '存储 GB', 'field_type': 'decimal', 'field_group': '容量信息', 'sort_order': 40},
            {'code': 'table_count', 'name': '表数量', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 50},
            {'code': 'job_count', 'name': '任务数', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 60},
        ],
    },
    {
        'code': 'DATAWORKS',
        'name': 'DataWorks',
        'group': 'bigdata',
        'icon': 'Operation',
        'color': '#8b5cf6',
        'description': '阿里云 DataWorks 工作空间、调度任务和数据开发治理入口台账。',
        'fields': [
            {'code': 'workspace_id', 'name': '工作空间 ID', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'workspace_name', 'name': '工作空间名称', 'field_type': 'string', 'field_group': '基础信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'edition', 'name': '版本规格', 'field_type': 'string', 'field_group': '资源规格', 'sort_order': 30},
            {'code': 'node_count', 'name': '节点数', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 40},
            {'code': 'workflow_count', 'name': '工作流数', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 50},
        ],
    },
    {
        'code': 'DW',
        'name': 'DW',
        'group': 'bigdata',
        'icon': 'DataAnalysis',
        'color': '#7c3aed',
        'description': '数据仓库服务、计算与存储规模台账。',
        'fields': [
            {'code': 'instance_id', 'name': '实例 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 30},
            {'code': 'deployment_mode', 'name': '部署方式', 'field_type': 'enum', 'field_group': '部署信息', 'options': [{'value': 'vm', 'label': '虚拟机'}, {'value': 'k8s', 'label': 'K8s 集群'}], 'sort_order': 40},
            {'code': 'instance_count', 'name': '实例数量', 'field_type': 'integer', 'field_group': '部署信息', 'sort_order': 50},
            {'code': 'storage_gb', 'name': '存储 GB', 'field_type': 'decimal', 'field_group': '资源规格', 'sort_order': 60},
        ],
    },
    {
        'code': 'NIFI',
        'name': 'NiFi',
        'group': 'bigdata',
        'icon': 'DataAnalysis',
        'color': '#7c3aed',
        'description': 'NiFi 数据流编排集群及处理规模台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 30},
            {'code': 'deployment_mode', 'name': '部署方式', 'field_type': 'enum', 'field_group': '部署信息', 'options': [{'value': 'vm', 'label': '虚拟机'}, {'value': 'k8s', 'label': 'K8s 集群'}], 'sort_order': 40},
            {'code': 'instance_count', 'name': '实例数量', 'field_type': 'integer', 'field_group': '部署信息', 'sort_order': 50},
            {'code': 'flow_count', 'name': '数据流数量', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 60},
        ],
    },
    {
        'code': 'DOLPHINSCHEDULER',
        'name': 'DolphinScheduler',
        'group': 'bigdata',
        'icon': 'Operation',
        'color': '#0ea5e9',
        'description': 'DolphinScheduler 调度集群、工作流与 Worker 规模台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '实例信息', 'sort_order': 30},
            {'code': 'deployment_mode', 'name': '部署方式', 'field_type': 'enum', 'field_group': '部署信息', 'options': [{'value': 'vm', 'label': '虚拟机'}, {'value': 'k8s', 'label': 'K8s 集群'}], 'sort_order': 40},
            {'code': 'instance_count', 'name': '实例数量', 'field_type': 'integer', 'field_group': '部署信息', 'sort_order': 50},
            {'code': 'worker_count', 'name': 'Worker 数量', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 60},
            {'code': 'workflow_count', 'name': '工作流数量', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 70},
        ],
    },
    {
        'code': 'DORIS',
        'name': 'Doris',
        'group': 'bigdata',
        'icon': 'DataBoard',
        'color': '#2563eb',
        'description': 'Doris / StarRocks 类 OLAP 集群、FE/BE 节点和查询入口台账。',
        'fields': [
            {'code': 'cluster_id', 'name': '集群 ID', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_type': 'string', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '基础信息', 'sort_order': 30},
            {'code': 'fe_count', 'name': 'FE 节点数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 40},
            {'code': 'be_count', 'name': 'BE 节点数', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 50},
        ],
    },
    {
        'code': 'LOAD_BALANCER',
        'name': '负载均衡',
        'group': 'network',
        'icon': 'Connection',
        'color': '#10b981',
        'description': 'SLB、CLB、Nginx、网关等入口负载均衡资源。',
        'fields': [
            {'code': 'instance_id', 'name': '实例 ID', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'vip', 'name': 'VIP', 'field_type': 'ip', 'field_group': '网络信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'domain', 'name': '域名', 'field_type': 'string', 'field_group': '网络信息', 'is_searchable': True, 'sort_order': 30},
            {'code': 'bandwidth', 'name': '带宽', 'field_type': 'string', 'field_group': '资源规格', 'sort_order': 40},
        ],
    },
    {
        'code': 'NAT_GATEWAY',
        'name': 'NAT Gateway',
        'group': 'network',
        'icon': 'Guide',
        'color': '#0891b2',
        'description': 'Cloud NAT gateway inventory, egress addresses, VPC binding and forwarding scale.',
        'fields': [
            {'code': 'instance_id', 'name': 'Instance ID', 'field_type': 'string', 'field_group': 'Basic', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'gateway_type', 'name': 'Gateway Type', 'field_type': 'string', 'field_group': 'Basic', 'is_searchable': True, 'sort_order': 20},
            {'code': 'spec', 'name': 'Spec', 'field_type': 'string', 'field_group': 'Spec', 'sort_order': 30},
            {'code': 'vpc_id', 'name': 'VPC', 'field_type': 'string', 'field_group': 'Network', 'is_searchable': True, 'sort_order': 40},
            {'code': 'eip_addresses', 'name': 'EIP Addresses', 'field_type': 'string', 'field_group': 'Network', 'is_searchable': True, 'sort_order': 50},
        ],
    },
    {
        'code': 'ELASTIC_IP',
        'name': 'Elastic IP',
        'group': 'network',
        'icon': 'Link',
        'color': '#0ea5e9',
        'description': 'Public elastic IP addresses, bandwidth, billing mode and attachment target.',
        'fields': [
            {'code': 'allocation_id', 'name': 'Allocation ID', 'field_type': 'string', 'field_group': 'Basic', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'ip_address', 'name': 'IP Address', 'field_type': 'ip', 'field_group': 'Network', 'required': True, 'is_searchable': True, 'sort_order': 20},
            {'code': 'bandwidth', 'name': 'Bandwidth', 'field_type': 'string', 'field_group': 'Spec', 'sort_order': 30},
            {'code': 'internet_charge_type', 'name': 'Charge Type', 'field_type': 'string', 'field_group': 'Billing', 'sort_order': 40},
            {'code': 'attached_to', 'name': 'Attached To', 'field_type': 'string', 'field_group': 'Attachment', 'is_searchable': True, 'sort_order': 50},
        ],
    },
    {
        'code': 'NGINX',
        'name': 'Nginx',
        'group': 'network',
        'icon': 'Switch',
        'color': '#16a34a',
        'description': 'Nginx 入口环境、反向代理或网关实例。',
        'fields': [
            {'code': 'environment_name', 'name': '环境名称', 'field_type': 'string', 'field_group': '基础信息', 'required': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'private_ip', 'name': '管理 IP', 'field_type': 'ip', 'field_group': '网络信息', 'required': True, 'is_searchable': True, 'sort_order': 20},
            {'code': 'listen_ports', 'name': '监听端口', 'field_type': 'string', 'field_group': '网络信息', 'sort_order': 30},
            {'code': 'nginx_path', 'name': '配置路径', 'field_type': 'string', 'field_group': '运行信息', 'sort_order': 40},
            {'code': 'version', 'name': '版本', 'field_type': 'string', 'field_group': '运行信息', 'sort_order': 50},
            {'code': 'config_repo', 'name': '配置仓库', 'field_type': 'url', 'field_group': '运维信息', 'sort_order': 60},
            {'code': 'ops_owner', 'name': '运维负责人', 'field_type': 'string', 'field_group': '归属信息', 'is_searchable': True, 'sort_order': 70},
        ],
    },
    {
        'code': 'DOMAIN',
        'name': '域名',
        'group': 'network',
        'icon': 'Guide',
        'color': '#0891b2',
        'description': '业务域名、解析记录和入口绑定信息。',
        'fields': [
            {'code': 'domain', 'name': '域名', 'field_type': 'string', 'field_group': '基础信息', 'required': True, 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'record_type', 'name': '记录类型', 'field_type': 'enum', 'field_group': '解析信息', 'options': [{'value': 'A', 'label': 'A'}, {'value': 'CNAME', 'label': 'CNAME'}, {'value': 'AAAA', 'label': 'AAAA'}, {'value': 'TXT', 'label': 'TXT'}], 'sort_order': 20},
            {'code': 'record_value', 'name': '解析值', 'field_type': 'string', 'field_group': '解析信息', 'is_searchable': True, 'sort_order': 30},
            {'code': 'dns_provider', 'name': 'DNS 服务商', 'field_type': 'string', 'field_group': '解析信息', 'sort_order': 40},
            {'code': 'owner', 'name': '域名负责人', 'field_type': 'string', 'field_group': '归属信息', 'is_searchable': True, 'sort_order': 50},
            {'code': 'expire_date', 'name': '域名到期日', 'field_type': 'date', 'field_group': '生命周期', 'sort_order': 60},
            {'code': 'ssl_enabled', 'name': '启用 HTTPS', 'field_type': 'boolean', 'field_group': '证书信息', 'default': False, 'sort_order': 70},
        ],
    },
    {
        'code': 'CERTIFICATE',
        'name': '证书',
        'group': 'network',
        'icon': 'Key',
        'color': '#ca8a04',
        'description': 'TLS/SSL 证书、责任人、部署位置和到期信息。',
        'fields': [
            {'code': 'domain', 'name': '证书域名', 'field_type': 'string', 'field_group': '基础信息', 'required': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'common_name', 'name': 'Common Name', 'field_type': 'string', 'field_group': '证书信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'issuer', 'name': '签发机构', 'field_type': 'string', 'field_group': '证书信息', 'sort_order': 30},
            {'code': 'serial_number', 'name': '证书序列号', 'field_type': 'string', 'field_group': '证书信息', 'unique': True, 'is_searchable': True, 'sort_order': 40},
            {'code': 'algorithm', 'name': '算法', 'field_type': 'string', 'field_group': '证书信息', 'sort_order': 50},
            {'code': 'starts_at', 'name': '生效时间', 'field_type': 'datetime', 'field_group': '生命周期', 'sort_order': 60},
            {'code': 'expires_at', 'name': '到期时间', 'field_type': 'datetime', 'field_group': '生命周期', 'sort_order': 70},
            {'code': 'cert_owner', 'name': '证书负责人', 'field_type': 'string', 'field_group': '归属信息', 'is_searchable': True, 'sort_order': 80},
            {'code': 'deploy_location', 'name': '部署位置', 'field_type': 'string', 'field_group': '部署信息', 'sort_order': 90},
            {'code': 'renew_policy', 'name': '续期策略', 'field_type': 'string', 'field_group': '生命周期', 'sort_order': 100},
        ],
    },
    {
        'code': 'THIRD_PARTY_SERVICE',
        'name': '第三方服务',
        'group': 'external',
        'icon': 'Link',
        'color': '#0f766e',
        'description': '短信、OCR、财务云、支付等外部服务，不保存密钥明文。',
        'fields': [
            {'code': 'provider', 'name': '供应商', 'field_type': 'string', 'field_group': '基础信息', 'required': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'service_type', 'name': '服务类型', 'field_type': 'string', 'field_group': '基础信息', 'is_searchable': True, 'sort_order': 15},
            {'code': 'account_subject', 'name': '账号主体', 'field_type': 'string', 'field_group': '账号信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'service_endpoint', 'name': '服务地址', 'field_type': 'url', 'field_group': '连接信息', 'sort_order': 25},
            {'code': 'backup_plan', 'name': '备份方案', 'field_type': 'string', 'field_group': '连续性', 'sort_order': 45},
            {'code': 'contract_no', 'name': '合同编号', 'field_type': 'string', 'field_group': '合同信息', 'is_searchable': True, 'sort_order': 50},
            {'code': 'service_expiry_date', 'name': '服务到期日', 'field_type': 'date', 'field_group': '服务治理', 'sort_order': 55},
            {'code': 'service_expire_warning_days', 'name': '到期提醒提前天数', 'field_type': 'integer', 'field_group': '服务治理', 'default': 30, 'sort_order': 60},
        ],
    },
    {
        'code': 'ASSET_ITEM',
        'name': '资产物品',
        'group': 'external',
        'icon': 'Goods',
        'color': '#475569',
        'description': '公共手机、办公设备、会议设备等可登记、保管和盘点的实物资产。',
        'fields': [
            {'code': 'asset_code', 'name': '资产编号', 'field_type': 'string', 'field_group': '基础信息', 'required': True, 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'item_category', 'name': '物品类型', 'field_type': 'enum', 'field_group': '基础信息', 'required': True, 'is_searchable': True, 'options': [{'value': 'mobile_device', 'label': '移动终端'}, {'value': 'office_equipment', 'label': '办公设备'}, {'value': 'meeting_equipment', 'label': '会议设备'}, {'value': 'network_peripheral', 'label': '网络外设'}, {'value': 'furniture', 'label': '家具与工位'}, {'value': 'other', 'label': '其他'}], 'sort_order': 20},
            {'code': 'brand_model', 'name': '品牌型号', 'field_type': 'string', 'field_group': '基础信息', 'is_searchable': True, 'sort_order': 30},
            {'code': 'serial_number', 'name': '序列号 / IMEI', 'field_type': 'string', 'field_group': '基础信息', 'unique': True, 'is_searchable': True, 'sort_order': 40},
            {'code': 'storage_location', 'name': '存放地点', 'field_type': 'string', 'field_group': '保管信息', 'required': True, 'is_searchable': True, 'sort_order': 50},
            {'code': 'custodian', 'name': '保管人', 'field_type': 'string', 'field_group': '保管信息', 'is_searchable': True, 'sort_order': 60},
            {'code': 'usage_status', 'name': '使用状态', 'field_type': 'enum', 'field_group': '状态信息', 'is_searchable': True, 'default': 'available', 'options': [{'value': 'available', 'label': '可用'}, {'value': 'in_use', 'label': '使用中'}, {'value': 'maintenance', 'label': '维修中'}, {'value': 'retired', 'label': '已报废'}], 'sort_order': 70},
            {'code': 'purchase_date', 'name': '采购日期', 'field_type': 'date', 'field_group': '生命周期', 'sort_order': 80},
            {'code': 'service_expiry_date', 'name': '服务到期日', 'field_type': 'date', 'field_group': '服务治理', 'sort_order': 90},
            {'code': 'service_expire_warning_days', 'name': '到期提醒提前天数', 'field_type': 'integer', 'field_group': '服务治理', 'default': 30, 'sort_order': 91},
        ],
    },
]


RELATION_RULES = [
    ('APP_SERVICE', 'CLOUD_SERVER', 'runs_on', '应用服务部署在云主机上。'),
    ('APP_SERVICE', 'VIRTUAL_MACHINE', 'runs_on', '应用服务部署在虚拟机上。'),
    ('APP_SERVICE', 'K8S_CLUSTER', 'runs_on', '应用服务运行在 K8s 集群上。'),
    ('APP_SERVICE', 'MYSQL', 'depends_on', '应用服务依赖数据库。'),
    ('APP_SERVICE', 'POSTGRESQL', 'depends_on', '应用服务依赖 PostgreSQL 数据库。'),
    ('APP_SERVICE', 'REDIS', 'depends_on', '应用服务依赖缓存。'),
    ('APP_SERVICE', 'MONGODB', 'depends_on', '应用服务依赖文档数据库。'),
    ('APP_SERVICE', 'KAFKA', 'depends_on', '应用服务依赖 Kafka 消息队列。'),
    ('APP_SERVICE', 'ROCKETMQ', 'depends_on', '应用服务依赖 RocketMQ 消息队列。'),
    ('APP_SERVICE', 'RABBITMQ', 'depends_on', '应用服务依赖 RabbitMQ 消息队列。'),
    ('APP_SERVICE', 'ELASTICSEARCH', 'depends_on', '应用服务依赖 Elasticsearch 搜索服务。'),
    ('APP_SERVICE', 'NACOS', 'depends_on', '应用服务依赖 Nacos 注册配置中心。'),
    ('APP_SERVICE', 'ZOOKEEPER', 'depends_on', '应用服务依赖 ZooKeeper 协调服务。'),
    ('APP_SERVICE', 'OBJECT_STORAGE', 'depends_on', '应用服务依赖对象存储。'),
    ('APP_SERVICE', 'BLOCK_STORAGE', 'depends_on', '应用服务依赖块存储。'),
    ('APP_SERVICE', 'FILE_STORAGE', 'depends_on', '应用服务依赖文件存储。'),
    ('APP_SERVICE', 'HADOOP', 'depends_on', '应用服务依赖 Hadoop 大数据集群。'),
    ('APP_SERVICE', 'FLINK', 'depends_on', '应用服务依赖 Flink 实时计算集群。'),
    ('APP_SERVICE', 'CLICKHOUSE', 'depends_on', '应用服务依赖 ClickHouse 分析库。'),
    ('APP_SERVICE', 'HOLOGRES', 'depends_on', '应用服务依赖 Hologres 实时数仓。'),
    ('APP_SERVICE', 'MAXCOMPUTE', 'depends_on', '应用服务依赖 MaxCompute 离线计算。'),
    ('APP_SERVICE', 'DATAWORKS', 'depends_on', '应用服务依赖 DataWorks 数据开发工作空间。'),
    ('APP_SERVICE', 'EMQX', 'depends_on', '应用服务依赖 EMQX MQTT 消息接入。'),
    ('APP_SERVICE', 'LOAD_BALANCER', 'connects_to', '应用服务被负载均衡入口访问。'),
    ('APP_SERVICE', 'MIDDLEWARE', 'depends_on', '应用服务依赖中间件。'),
    ('APP_SERVICE', 'THIRD_PARTY_SERVICE', 'depends_on', '应用服务依赖第三方服务。'),
    ('LOAD_BALANCER', 'APP_SERVICE', 'connects_to', '入口资源转发到应用服务。'),
    ('NGINX', 'APP_SERVICE', 'connects_to', 'Nginx 入口转发到应用服务。'),
    ('DOMAIN', 'LOAD_BALANCER', 'connects_to', '域名解析到负载均衡入口。'),
    ('DOMAIN', 'NGINX', 'connects_to', '域名解析到 Nginx 入口。'),
    ('DOMAIN', 'CERTIFICATE', 'depends_on', '域名使用 TLS/SSL 证书。'),
    ('K8S_CLUSTER', 'IDC_SERVER', 'runs_on', 'K8s 集群运行在机房物理机上。'),
    ('K8S_CLUSTER', 'CLOUD_SERVER', 'runs_on', 'K8s 集群运行在云主机上。'),
    ('K8S_CLUSTER', 'VIRTUAL_MACHINE', 'runs_on', 'K8s 集群运行在虚拟机上。'),
]

HOSTED_ASSET_CODES = (
    'MYSQL', 'POSTGRESQL', 'REDIS', 'MONGODB', 'MIDDLEWARE', 'KAFKA', 'ROCKETMQ',
    'RABBITMQ', 'ELASTICSEARCH', 'EMQX', 'NACOS', 'ZOOKEEPER', 'HADOOP', 'FLINK',
    'CLICKHOUSE', 'HOLOGRES', 'MAXCOMPUTE', 'DATAWORKS',
)

for hosted_code in HOSTED_ASSET_CODES:
    for host_code, host_name in (
        ('IDC_SERVER', '机房物理机'),
        ('CLOUD_SERVER', '云主机'),
        ('VIRTUAL_MACHINE', '虚拟机'),
    ):
        RELATION_RULES.append((hosted_code, host_code, 'runs_on', f'{hosted_code} 运行在{host_name}上。'))

OBSOLETE_RELATION_RULES = [
    ('K8S_CLUSTER', 'APP_SERVICE', 'runs_on'),
]


THRESHOLD_POLICIES = [
    ('CLOUD_SERVER', 'cpu_usage', 70, 85, 95, 100),
    ('CLOUD_SERVER', 'memory_usage', 70, 85, 95, 100),
    ('CLOUD_SERVER', 'disk_usage', 70, 85, 95, 100),
    ('VIRTUAL_MACHINE', 'cpu_usage', 70, 85, 95, 100),
    ('VIRTUAL_MACHINE', 'memory_usage', 70, 85, 95, 100),
    ('VIRTUAL_MACHINE', 'disk_usage', 70, 85, 95, 100),
    ('MYSQL', 'storage_usage', 70, 85, 95, 100),
    ('POSTGRESQL', 'storage_usage', 70, 85, 95, 100),
    ('REDIS', 'memory_usage', 70, 85, 95, 100),
    ('MONGODB', 'storage_usage', 70, 85, 95, 100),
    ('KAFKA', 'message_lag', 1000, 5000, 20000, 50000),
    ('ROCKETMQ', 'message_lag', 1000, 5000, 20000, 50000),
    ('RABBITMQ', 'message_lag', 1000, 5000, 20000, 50000),
    ('EMQX', 'connection_usage', 70, 85, 95, 100),
    ('ELASTICSEARCH', 'storage_usage', 70, 85, 95, 100),
    ('OBJECT_STORAGE', 'storage_usage', 70, 85, 95, 100),
    ('BLOCK_STORAGE', 'storage_usage', 70, 85, 95, 100),
    ('FILE_STORAGE', 'storage_usage', 70, 85, 95, 100),
    ('HADOOP', 'storage_usage', 70, 85, 95, 100),
    ('CLICKHOUSE', 'storage_usage', 70, 85, 95, 100),
    ('HOLOGRES', 'storage_usage', 70, 85, 95, 100),
    ('MAXCOMPUTE', 'storage_usage', 70, 85, 95, 100),
    ('DATAWORKS', 'workflow_failures', 1, 5, 10, 20),
]


ALIYUN_ACCOUNT_HINT = {
    'account_ref_field': 'cloud_account_id',
    'account_setup_note': '先在多云管理创建阿里云账号，再把云账号 ID 填到 cloud_account_id；同步任务不保存 AK/SK 明文。',
}

HUAWEICLOUD_ACCOUNT_HINT = {
    'account_ref_field': 'cloud_account_id',
    'account_setup_note': '先在多云管理创建华为云账号，并填写 project_id；再把云账号 ID 填到 cloud_account_id。',
}

VSPHERE_ACCOUNT_HINT = {
    'auth_ref': 'SXDEVOPS_VSPHERE_PROD',
    'account_setup_note': 'host/username 可写入任务配置，密码通过运行环境变量 SXDEVOPS_VSPHERE_PROD_PASSWORD 提供。',
    'required_env_vars': ['SXDEVOPS_VSPHERE_PROD_PASSWORD'],
}


SYNC_JOB_TEMPLATES = [
    {
        'name': '阿里云 ECS 自动注册模板',
        'source_type': 'aliyun_ecs',
        'mode': 'scheduled',
        'config': {
            'connector': 'aliyun',
            **ALIYUN_ACCOUNT_HINT,
            'resource_type': 'ecs',
            'target_ci_type_code': 'CLOUD_SERVER',
            'unique_key': 'instance_id',
            'collection_enabled': True,
            'interval_minutes': 60,
            'schedule_label': '每 60 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': '阿里云 RDS 自动注册模板',
        'source_type': 'aliyun_rds',
        'mode': 'scheduled',
        'config': {
            'connector': 'aliyun',
            **ALIYUN_ACCOUNT_HINT,
            'resource_type': 'rds',
            'target_ci_type_code': 'MYSQL',
            'unique_key': 'instance_id',
            'collection_enabled': True,
            'interval_minutes': 120,
            'schedule_label': '每 120 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': '阿里云 Redis 自动注册模板',
        'source_type': 'aliyun_redis',
        'mode': 'scheduled',
        'config': {
            'connector': 'aliyun',
            **ALIYUN_ACCOUNT_HINT,
            'resource_type': 'redis',
            'target_ci_type_code': 'REDIS',
            'unique_key': 'instance_id',
            'collection_enabled': True,
            'interval_minutes': 120,
            'schedule_label': '每 120 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': '阿里云 MongoDB 自动注册模板',
        'source_type': 'aliyun_mongodb',
        'mode': 'scheduled',
        'config': {
            'connector': 'aliyun',
            **ALIYUN_ACCOUNT_HINT,
            'resource_type': 'mongodb',
            'target_ci_type_code': 'MONGODB',
            'unique_key': 'instance_id',
            'collection_enabled': True,
            'interval_minutes': 120,
            'schedule_label': '每 120 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': '阿里云 Kafka 自动注册模板',
        'source_type': 'aliyun_kafka',
        'mode': 'scheduled',
        'config': {
            'connector': 'aliyun',
            **ALIYUN_ACCOUNT_HINT,
            'resource_type': 'kafka',
            'target_ci_type_code': 'KAFKA',
            'unique_key': 'instance_id',
            'collection_enabled': True,
            'interval_minutes': 120,
            'schedule_label': '每 120 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': '阿里云 RocketMQ 自动注册模板',
        'source_type': 'aliyun_rocketmq',
        'mode': 'scheduled',
        'config': {
            'connector': 'aliyun',
            **ALIYUN_ACCOUNT_HINT,
            'resource_type': 'rocketmq',
            'target_ci_type_code': 'ROCKETMQ',
            'unique_key': 'instance_id',
            'collection_enabled': True,
            'interval_minutes': 120,
            'schedule_label': '每 120 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': '阿里云 OSS 自动注册模板',
        'source_type': 'aliyun_oss',
        'mode': 'scheduled',
        'config': {
            'connector': 'aliyun',
            **ALIYUN_ACCOUNT_HINT,
            'resource_type': 'oss',
            'target_ci_type_code': 'OBJECT_STORAGE',
            'unique_key': 'bucket',
            'collection_enabled': True,
            'interval_minutes': 180,
            'schedule_label': '每 180 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': '阿里云 SLB 自动注册模板',
        'source_type': 'aliyun_slb',
        'mode': 'scheduled',
        'config': {
            'connector': 'aliyun',
            **ALIYUN_ACCOUNT_HINT,
            'resource_type': 'slb',
            'target_ci_type_code': 'LOAD_BALANCER',
            'unique_key': 'instance_id',
            'collection_enabled': True,
            'interval_minutes': 120,
            'schedule_label': '每 120 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': 'vSphere 虚拟机自动注册模板',
        'source_type': 'vsphere_vm',
        'mode': 'scheduled',
        'config': {
            'connector': 'vsphere',
            **VSPHERE_ACCOUNT_HINT,
            'resource_type': 'vm',
            'target_ci_type_code': 'VIRTUAL_MACHINE',
            'unique_key': 'instance_id',
            'collection_enabled': True,
            'prometheus_metrics_enabled': True,
            'prometheus_cpu_window': '1m',
            'prometheus_root_mountpoint': '/',
            'interval_minutes': 60,
            'schedule_label': '每 60 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': '华为云 ECS 自动注册模板',
        'source_type': 'huaweicloud_ecs',
        'mode': 'scheduled',
        'config': {
            'connector': 'huaweicloud',
            **HUAWEICLOUD_ACCOUNT_HINT,
            'resource_type': 'ecs',
            'target_ci_type_code': 'CLOUD_SERVER',
            'unique_key': 'instance_id',
            'collection_enabled': True,
            'interval_minutes': 60,
            'schedule_label': '每 60 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': '华为云 RDS 自动注册模板',
        'source_type': 'huaweicloud_rds',
        'mode': 'scheduled',
        'config': {
            'connector': 'huaweicloud',
            **HUAWEICLOUD_ACCOUNT_HINT,
            'resource_type': 'rds',
            'target_ci_type_code': 'MYSQL',
            'unique_key': 'instance_id',
            'collection_enabled': True,
            'interval_minutes': 120,
            'schedule_label': '每 120 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': '华为云 Redis 自动注册模板',
        'source_type': 'huaweicloud_redis',
        'mode': 'scheduled',
        'config': {
            'connector': 'huaweicloud',
            **HUAWEICLOUD_ACCOUNT_HINT,
            'resource_type': 'redis',
            'target_ci_type_code': 'REDIS',
            'unique_key': 'instance_id',
            'collection_enabled': True,
            'interval_minutes': 120,
            'schedule_label': '每 120 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': '华为云 EIP 自动注册模板',
        'source_type': 'huaweicloud_eip',
        'mode': 'scheduled',
        'config': {
            'connector': 'huaweicloud',
            **HUAWEICLOUD_ACCOUNT_HINT,
            'resource_type': 'eip',
            'target_ci_type_code': 'ELASTIC_IP',
            'unique_key': 'allocation_id',
            'collection_enabled': True,
            'interval_minutes': 120,
            'schedule_label': '每 120 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': '华为云 OBS 自动注册模板',
        'source_type': 'huaweicloud_obs',
        'mode': 'scheduled',
        'config': {
            'connector': 'huaweicloud',
            **HUAWEICLOUD_ACCOUNT_HINT,
            'resource_type': 'obs',
            'target_ci_type_code': 'OBJECT_STORAGE',
            'unique_key': 'bucket',
            'collection_enabled': True,
            'interval_minutes': 180,
            'schedule_label': '每 180 分钟',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    },
    {
        'name': '第三方服务台账导入模板',
        'source_type': 'third_party_import',
        'mode': 'import',
        'config': {
            'connector': 'manual_import',
            'target_ci_type_code': 'THIRD_PARTY_SERVICE',
            'unique_key': 'provider',
            'sensitive_fields_policy': '不保存密钥明文，仅登记账号和服务到期信息。',
            'required_fields': ['provider'],
            'items': [
                {
                    'ci_type_code': 'THIRD_PARTY_SERVICE',
                    'name': '短信服务-生产账号',
                    'source_unique_id': 'sms-prod-account',
                    'business_line': 'core',
                    'environment': 'prod',
                    'admin_user': 'ops',
                    'attributes': {
                        'provider': '示例供应商',
                        'service_type': '短信',
                        'account_subject': '生产主体',
                        'backup_plan': '供应商控制台导出配置，每月归档',
                        'contract_no': 'HT-2026-001',
                        'service_expiry_date': '2026-12-31',
                        'service_expire_warning_days': 30,
                    },
                },
                {
                    'ci_type_code': 'THIRD_PARTY_SERVICE',
                    'name': '和风天气-生产账号',
                    'source_unique_id': 'heweather-prod-account',
                    'business_line': '电商业务线',
                    'environment': 'prod',
                    'admin_user': '应用运维',
                    'attributes': {
                        'provider': '和风天气',
                        'service_type': '天气 API',
                        'account_subject': '生产主体',
                        'backup_plan': '控制台导出应用配置，每季度归档',
                        'contract_no': 'HT-WEATHER-2026-001',
                        'service_expiry_date': '2026-12-31',
                        'service_expire_warning_days': 30,
                    },
                },
                {
                    'ci_type_code': 'THIRD_PARTY_SERVICE',
                    'name': '高德地图-生产账号',
                    'source_unique_id': 'amap-prod-account',
                    'business_line': '电商业务线',
                    'environment': 'prod',
                    'admin_user': '应用运维',
                    'attributes': {
                        'provider': '高德地图',
                        'service_type': '地图 API',
                        'account_subject': '生产主体',
                        'backup_plan': '控制台导出 Key 与额度配置，每季度归档',
                        'contract_no': 'HT-AMAP-2026-001',
                        'service_expiry_date': '2026-11-30',
                        'service_expire_warning_days': 30,
                    },
                },
            ],
        },
    },
]


ALIYUN_EXTENDED_SYNC_PRODUCTS = [
    ('aliyun_ack', 'ack', 'K8S_CLUSTER', 'cluster_id', 120, 'Aliyun ACK auto registration template'),
    ('aliyun_disk', 'disk', 'BLOCK_STORAGE', 'volume_id', 180, 'Aliyun cloud disk auto registration template'),
    ('aliyun_nas', 'nas', 'FILE_STORAGE', 'filesystem_id', 180, 'Aliyun NAS auto registration template'),
    ('aliyun_clickhouse', 'clickhouse', 'CLICKHOUSE', 'cluster_id', 180, 'Aliyun ClickHouse auto registration template'),
    ('aliyun_hologres', 'hologres', 'HOLOGRES', 'instance_id', 180, 'Aliyun Hologres auto registration template'),
    ('aliyun_maxcompute', 'maxcompute', 'MAXCOMPUTE', 'project_name', 180, 'Aliyun MaxCompute auto registration template'),
    ('aliyun_dataworks', 'dataworks', 'DATAWORKS', 'workspace_id', 180, 'Aliyun DataWorks auto registration template'),
    ('aliyun_nat_gateway', 'nat_gateway', 'NAT_GATEWAY', 'instance_id', 120, 'Aliyun NAT Gateway auto registration template'),
    ('aliyun_eip', 'eip', 'ELASTIC_IP', 'allocation_id', 120, 'Aliyun Elastic IP auto registration template'),
    ('aliyun_elasticsearch', 'elasticsearch', 'ELASTICSEARCH', 'cluster_id', 180, 'Aliyun Elasticsearch auto registration template'),
]

OBSOLETE_SYNC_SOURCE_TYPES = {'aliyun_security_group'}
OBSOLETE_PURGE_SOURCE_TYPES = {'aliyun_security_group'}
SYNC_SOURCE_TYPE_MIGRATIONS = {
    'aliyun_nfs': ('aliyun_nas', 'nas', 'Aliyun NAS auto registration template'),
}

for source_type, resource_type, target_ci_type_code, unique_key, interval_minutes, name in ALIYUN_EXTENDED_SYNC_PRODUCTS:
    SYNC_JOB_TEMPLATES.append({
        'name': name,
        'source_type': source_type,
        'mode': 'scheduled',
        'config': {
            'connector': 'aliyun',
            **ALIYUN_ACCOUNT_HINT,
            'resource_type': resource_type,
            'target_ci_type_code': target_ci_type_code,
            'unique_key': unique_key,
            'collection_enabled': True,
            'interval_minutes': interval_minutes,
            'schedule_label': f'every {interval_minutes} minutes',
            'governance': {'completion_required': ['business_line', 'admin_user', 'environment'], 'missing_means_archive_candidate': True},
            'items': [],
        },
    })


def _upsert_group(payload):
    group, _ = CIModelGroup.objects.update_or_create(
        code=payload['code'],
        defaults={
            'name': payload['name'],
            'description': payload.get('description', ''),
            'sort_order': payload.get('sort_order', 0),
            'is_builtin': True,
            'is_active': True,
        },
    )
    return group


def _upsert_ci_type(payload, groups):
    ci_type = CIType.objects.filter(code=payload['code']).first()
    if ci_type is None:
        ci_type = CIType.objects.filter(name=payload['name']).first()
    defaults = {
        'name': payload['name'],
        'code': payload['code'],
        'group': groups[payload['group']],
        'icon': payload.get('icon', ''),
        'color': payload.get('color', '#3b82f6'),
        'description': payload.get('description', ''),
        'is_builtin': True,
        'is_active': True,
    }
    if ci_type is None:
        return CIType.objects.create(**defaults)
    for key, value in defaults.items():
        setattr(ci_type, key, value)
    ci_type.save()
    return ci_type


def _retire_obsolete_groups(active_groups):
    CIModelGroup.objects.filter(code__in=OBSOLETE_MODEL_GROUP_CODES).exclude(
        id__in=[group.id for group in active_groups.values()]
    ).update(is_active=False)


def _merge_obsolete_ci_types(ci_types):
    for old_code, target_code in OBSOLETE_CI_TYPE_MERGES.items():
        old_type = CIType.objects.filter(code=old_code).first()
        target_type = ci_types.get(target_code)
        if not old_type or not target_type or old_type.id == target_type.id:
            continue
        ConfigItem.objects.filter(ci_type=old_type).update(ci_type=target_type)
        old_type.is_active = False
        old_type.is_builtin = True
        old_type.save(update_fields=['is_active', 'is_builtin', 'updated_at'])

    for old_name, target_code in OBSOLETE_CI_TYPE_NAMES.items():
        old_type = CIType.objects.filter(name=old_name).exclude(code__in=ci_types.keys()).first()
        target_type = ci_types.get(target_code)
        if not old_type or not target_type or old_type.id == target_type.id:
            continue
        ConfigItem.objects.filter(ci_type=old_type).update(ci_type=target_type)
        old_type.is_active = False
        old_type.is_builtin = True
        old_type.save(update_fields=['is_active', 'is_builtin', 'updated_at'])


def _retire_obsolete_ci_types():
    purge_type_q = Q(code__in=OBSOLETE_CI_TYPE_PURGE_CODES) | Q(name__in=OBSOLETE_CI_TYPE_PURGE_NAMES)
    purge_type_ids = list(CIType.objects.filter(purge_type_q).values_list('id', flat=True))
    if purge_type_ids:
        ConfigItem.objects.filter(ci_type_id__in=purge_type_ids).delete()
        CIField.objects.filter(ci_type_id__in=purge_type_ids).delete()
    if OBSOLETE_PURGE_SOURCE_TYPES:
        source_ci_ids = list(CISourceMapping.objects.filter(source_type__in=OBSOLETE_PURGE_SOURCE_TYPES).values_list('ci_id', flat=True))
        if source_ci_ids:
            ConfigItem.objects.filter(id__in=source_ci_ids).delete()
        CISourceMapping.objects.filter(source_type__in=OBSOLETE_PURGE_SOURCE_TYPES).delete()
    try:
        from multicloud.models import CloudAsset
        CloudAsset.objects.filter(resource_type='security_group').delete()
    except Exception:
        pass

    CIType.objects.filter(code__in=OBSOLETE_CI_TYPE_RETIRE_CODES).update(
        is_active=False,
        is_builtin=True,
    )
    CIType.objects.filter(name__in=OBSOLETE_CI_TYPE_RETIRE_NAMES).update(
        is_active=False,
        is_builtin=True,
    )
    CIRelationRule.objects.filter(source_type__code__in=OBSOLETE_CI_TYPE_RETIRE_CODES).update(is_active=False)
    CIRelationRule.objects.filter(target_type__code__in=OBSOLETE_CI_TYPE_RETIRE_CODES).update(is_active=False)
    CIRelationRule.objects.filter(source_type__name__in=OBSOLETE_CI_TYPE_RETIRE_NAMES).update(is_active=False)
    CIRelationRule.objects.filter(target_type__name__in=OBSOLETE_CI_TYPE_RETIRE_NAMES).update(is_active=False)
    CIThresholdPolicy.objects.filter(resource_type__code__in=OBSOLETE_CI_TYPE_RETIRE_CODES).update(enabled=False)
    CIThresholdPolicy.objects.filter(resource_type__name__in=OBSOLETE_CI_TYPE_RETIRE_NAMES).update(enabled=False)


def _assign_legacy_ci_type_groups(groups):
    for type_name, group_code in LEGACY_CI_TYPE_GROUP_MAPPINGS.items():
        group = groups.get(group_code)
        if not group:
            continue
        CIType.objects.filter(name=type_name).update(group=group, is_builtin=True)


def _migrate_obsolete_sync_jobs():
    for old_source_type, (new_source_type, new_resource_type, new_name) in SYNC_SOURCE_TYPE_MIGRATIONS.items():
        for job in CISyncJob.objects.filter(source_type=old_source_type):
            config = dict(job.config or {})
            config['resource_type'] = new_resource_type
            job.source_type = new_source_type
            job.name = new_name if job.created_by == 'builtin' else str(job.name or '').replace('NFS', 'NAS')
            job.config = config
            job.save(update_fields=['source_type', 'name', 'config', 'updated_at'])
        for job in CISyncJob.objects.filter(source_type=new_source_type, name__icontains='NFS'):
            job.name = str(job.name or '').replace('NFS', 'NAS')
            job.save(update_fields=['name', 'updated_at'])
        CISourceMapping.objects.filter(source_type=old_source_type).update(source_type=new_source_type)
        for ci in ConfigItem.objects.filter(attributes__source_type=old_source_type).only('id', 'attributes'):
            attributes = dict(ci.attributes or {})
            attributes['source_type'] = new_source_type
            ci.attributes = attributes
            ci.save(update_fields=['attributes', 'updated_at'])
    CISyncJob.objects.filter(source_type__in=OBSOLETE_SYNC_SOURCE_TYPES, created_by='builtin').delete()
    for job in CISyncJob.objects.filter(source_type__in=OBSOLETE_SYNC_SOURCE_TYPES):
        config = dict(job.config or {})
        config['collection_enabled'] = False
        job.status = 'pending'
        job.error_message = ''
        job.config = config
        job.save(update_fields=['status', 'error_message', 'config', 'updated_at'])


def _reclassify_postgresql_rds_items(ci_types):
    mysql_type = ci_types.get('MYSQL')
    postgresql_type = ci_types.get('POSTGRESQL')
    if not mysql_type or not postgresql_type:
        return 0
    return ConfigItem.objects.filter(ci_type=mysql_type).filter(
        Q(attributes__engine__icontains='postgres')
        | Q(attributes__engine__icontains='pgsql')
    ).update(ci_type=postgresql_type)


def _upsert_field(ci_type, payload, fallback_order=0):
    defaults = {
        'name': payload['name'],
        'field_type': payload.get('field_type', 'string'),
        'field_group': payload.get('field_group', ''),
        'required': payload.get('required', False),
        'unique': payload.get('unique', False),
        'default': payload.get('default'),
        'options': payload.get('options', []),
        'validation': payload.get('validation', {}),
        'sync_mode': payload.get('sync_mode') or ('manual' if payload['code'] in MANUAL_SYNC_FIELD_CODES else 'source'),
        'is_builtin': True,
        'is_display': payload.get('is_display', True),
        'is_searchable': payload.get('is_searchable', False),
        'is_sensitive': payload.get('is_sensitive', False),
        'is_active': True,
        'sort_order': payload.get('sort_order', fallback_order),
    }
    return CIField.objects.update_or_create(ci_type=ci_type, code=payload['code'], defaults=defaults)


def _delete_obsolete_builtin_fields(ci_type, desired_codes):
    CIField.objects.filter(ci_type=ci_type, is_builtin=True).exclude(code__in=desired_codes).delete()


@transaction.atomic
def ensure_builtin_cmdb():
    groups = {payload['code']: _upsert_group(payload) for payload in MODEL_GROUPS}
    ci_types = {}
    for payload in MODEL_DEFINITIONS:
        ci_type = _upsert_ci_type(payload, groups)
        ci_types[payload['code']] = ci_type
        model_fields = [*payload.get('fields', [])]
        if payload.get('group') in WEB_ACCESS_ADDRESS_GROUP_CODES or payload.get('code') in WEB_ACCESS_ADDRESS_TYPE_CODES:
            model_fields.append(WEB_ACCESS_ADDRESS_FIELD)
        model_fields.extend(COMMON_FIELDS)
        for index, field in enumerate(model_fields, start=1):
            _upsert_field(ci_type, field, fallback_order=index * 10)
        _delete_obsolete_builtin_fields(ci_type, {field['code'] for field in model_fields})
    _retire_obsolete_groups(groups)
    _merge_obsolete_ci_types(ci_types)
    _retire_obsolete_ci_types()
    _assign_legacy_ci_type_groups(groups)
    _migrate_obsolete_sync_jobs()
    reclassified_postgresql = _reclassify_postgresql_rds_items(ci_types)

    for source_code, target_code, relation_type, description in RELATION_RULES:
        source_type = ci_types.get(source_code)
        target_type = ci_types.get(target_code)
        if not source_type or not target_type:
            continue
        CIRelationRule.objects.update_or_create(
            source_type=source_type,
            target_type=target_type,
            relation_type=relation_type,
            defaults={
                'direction': 'outgoing',
                'required': False,
                'multiple': True,
                'description': description,
                'is_active': True,
            },
        )

    for source_code, target_code, relation_type in OBSOLETE_RELATION_RULES:
        source_type = ci_types.get(source_code)
        target_type = ci_types.get(target_code)
        if source_type and target_type:
            CIRelationRule.objects.filter(
                source_type=source_type,
                target_type=target_type,
                relation_type=relation_type,
            ).update(is_active=False)

    for type_code, metric, normal, warning, critical, exceeded in THRESHOLD_POLICIES:
        ci_type = ci_types.get(type_code)
        if not ci_type:
            continue
        CIThresholdPolicy.objects.update_or_create(
            resource_type=ci_type,
            metric=metric,
            defaults={
                'normal_threshold': normal,
                'warning_threshold': warning,
                'critical_threshold': critical,
                'exceeded_threshold': exceeded,
                'enabled': True,
            },
        )

    for payload in SYNC_JOB_TEMPLATES:
        CISyncJob.objects.update_or_create(
            name=payload['name'],
            source_type=payload['source_type'],
            defaults={
                'status': 'pending',
                'mode': payload.get('mode', 'manual'),
                'dry_run': False,
                'config': payload.get('config', {}),
                'created_by': 'builtin',
                'summary': {},
                'error_message': '',
            },
        )

    return {
        'groups': len(groups),
        'types': len(ci_types),
        'fields': CIField.objects.filter(ci_type__code__in=ci_types.keys(), is_builtin=True).count(),
        'relation_rules': CIRelationRule.objects.filter(
            source_type__code__in=ci_types.keys(),
            target_type__code__in=ci_types.keys(),
        ).count(),
        'threshold_policies': CIThresholdPolicy.objects.filter(
            resource_type__code__in=ci_types.keys(),
        ).count(),
        'sync_jobs': len(SYNC_JOB_TEMPLATES),
        'reclassified_postgresql': reclassified_postgresql,
    }
