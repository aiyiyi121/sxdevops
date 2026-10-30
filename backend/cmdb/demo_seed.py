from decimal import Decimal

from django.utils import timezone

from .models import CIResourceMetricSnapshot, CIType, CIRelation, ConfigItem, CostRecord, ResourceNode, ResourceRequest


BIZ_COMMERCE = '电商线'
BIZ_DATA = '数据平台'
BIZ_INFRA = '基础架构'


def _log(stdout, message):
    if stdout is None:
        print(message)
    elif hasattr(stdout, 'write'):
        stdout.write(message)
    else:
        stdout(message)


def _months(limit=6):
    base = timezone.now().replace(day=1)
    months = []
    for _ in range(limit):
        months.append(base.strftime('%Y-%m'))
        base = (base - timezone.timedelta(days=1)).replace(day=1)
    months.reverse()
    return months


def ensure_ci_type(name, color, icon='Monitor', description='', code=''):
    lookup = {'code': code} if code else {'name': name}
    defaults = {'name': name, 'icon': icon, 'color': color, 'description': description}
    ci_type, _ = CIType.objects.get_or_create(**lookup, defaults=defaults)
    ci_type.name = name
    if code:
        ci_type.code = code
    ci_type.icon = ci_type.icon or icon
    ci_type.color = color
    if description:
        ci_type.description = description
    ci_type.save()
    return ci_type


def create_ci(ci_type, name, business_line, environment, admin_user, status, attributes=None):
    return ConfigItem.objects.create(
        name=name,
        ci_type=ci_type,
        business_line=business_line,
        environment=environment,
        admin_user=admin_user,
        status=status,
        attributes=attributes or {},
    )


def create_relation(source, target, relation_type, description):
    return CIRelation.objects.create(
        source=source,
        target=target,
        relation_type=relation_type,
        description=description,
    )


def create_metric(ci, metric, usage_percent, source='demo-monitor', collected_at=None):
    collected_at = collected_at or timezone.now()
    return CIResourceMetricSnapshot.objects.create(
        ci=ci,
        metric=metric,
        value=Decimal(str(usage_percent)),
        unit='%',
        usage_percent=Decimal(str(usage_percent)),
        collected_at=collected_at,
        source=source,
    )


def _provider(attributes):
    return (
        attributes.get('billing_provider')
        or attributes.get('cloud_provider')
        or attributes.get('provider')
        or ''
    )[:50]


def _build_amounts(current_amount, history_profile):
    current_amount = Decimal(str(current_amount))
    return [
        (current_amount * Decimal(str(factor))).quantize(Decimal('0.01'))
        for factor in history_profile
    ]


def seed_cmdb_demo(stdout=None):
    _log(stdout, 'Clearing existing CMDB demo data...')
    CostRecord.objects.all().delete()
    CIRelation.objects.all().delete()
    ConfigItem.objects.all().delete()
    ResourceRequest.objects.all().delete()
    ResourceNode.objects.all().delete()

    _log(stdout, 'Preparing CI types...')
    type_app = ensure_ci_type('应用服务', '#3b82f6', 'Grid', '对外或对内提供业务能力的应用服务')
    type_idc_server = ensure_ci_type('物理机', '#475569', 'Cpu', '自建机房或托管机房中的物理服务器', code='IDC_SERVER')
    type_host = ensure_ci_type('云主机(ECS)', '#64748b', 'Monitor', '承载应用与数据服务的云主机')
    type_db = ensure_ci_type('MySQL', '#f97316', 'Coin', '核心关系型数据库')
    type_cache = ensure_ci_type('Redis', '#ef4444', 'Collection', '缓存与热数据服务')
    type_lb = ensure_ci_type('Nginx', '#10b981', 'Connection', '南北向网关与负载均衡')
    type_warehouse = ensure_ci_type('数据仓库', '#8b5cf6', 'Histogram', 'BI 与离线分析类数据平台')
    type_storage = ensure_ci_type('对象存储', '#06b6d4', 'FolderOpened', '日志、归档与共享文件存储')
    type_third_party = ensure_ci_type('第三方服务', '#0f766e', 'Link', '短信、OCR、财务云等外部 SaaS 能力')

    _log(stdout, 'Creating resource tree...')
    biz_ecommerce = ResourceNode.objects.create(name=BIZ_COMMERCE, node_type='biz')
    ResourceNode.objects.create(name='prod', node_type='env', parent=biz_ecommerce)
    ResourceNode.objects.create(name='test', node_type='env', parent=biz_ecommerce)
    ResourceNode.objects.create(name='dev', node_type='env', parent=biz_ecommerce)

    biz_data = ResourceNode.objects.create(name=BIZ_DATA, node_type='biz')
    ResourceNode.objects.create(name='prod', node_type='env', parent=biz_data)
    ResourceNode.objects.create(name='dev', node_type='env', parent=biz_data)

    biz_infra = ResourceNode.objects.create(name=BIZ_INFRA, node_type='biz')
    ResourceNode.objects.create(name='prod', node_type='env', parent=biz_infra)

    _log(stdout, 'Creating config items...')
    resources = {}

    resources['gateway'] = create_ci(
        type_lb,
        'gateway-prod',
        BIZ_COMMERCE,
        'prod',
        'SRE-王涛',
        'active',
        {
            'ip_address': '10.10.0.10',
            'bandwidth': '200Mbps',
            'cpu': 4,
            'memory_gb': 8,
            'avg_cpu_usage': 34,
            'avg_memory_usage': 46,
            'cloud_provider': '腾讯云 CLB',
            'monthly_cost': 260,
        },
    )
    resources['order_host_a'] = create_ci(
        type_host,
        'order-api-ecs-01',
        BIZ_COMMERCE,
        'prod',
        '应用运维-李俊',
        'active',
        {
            'ip_address': '192.0.2.1',
            'cpu': 8,
            'memory_gb': 16,
            'disk_gb': 200,
            'instance_type': 'ecs.g7.2xlarge',
            'avg_cpu_usage': 43,
            'avg_memory_usage': 52,
            'cloud_provider': '阿里云 ECS',
            'monthly_cost': 420,
        },
    )
    resources['order_host_b'] = create_ci(
        type_host,
        'order-api-ecs-02',
        BIZ_COMMERCE,
        'prod',
        '应用运维-李俊',
        'active',
        {
            'ip_address': '10.10.1.11',
            'cpu': 8,
            'memory_gb': 16,
            'disk_gb': 200,
            'instance_type': 'ecs.g7.2xlarge',
            'avg_cpu_usage': 41,
            'avg_memory_usage': 49,
            'cloud_provider': '阿里云 ECS',
            'monthly_cost': 420,
        },
    )
    resources['order_db'] = create_ci(
        type_db,
        'order-mysql-prod',
        BIZ_COMMERCE,
        'prod',
        'DBA-周宁',
        'active',
        {
            'ip_address': '10.10.2.10',
            'version': 'MySQL 8.0',
            'cpu': 16,
            'memory_gb': 64,
            'storage_gb': 1500,
            'storage_utilization': 68,
            'avg_cpu_usage': 47,
            'avg_memory_usage': 61,
            'cloud_provider': '阿里云 RDS',
            'monthly_cost': 2100,
        },
    )
    resources['order_cache'] = create_ci(
        type_cache,
        'order-redis-prod',
        BIZ_COMMERCE,
        'prod',
        'DBA-周宁',
        'active',
        {
            'ip_address': '10.10.2.11',
            'version': 'Redis 7.0',
            'cpu': 8,
            'memory_gb': 16,
            'avg_cpu_usage': 36,
            'avg_memory_usage': 63,
            'cloud_provider': '阿里云 Tair',
            'monthly_cost': 680,
        },
    )
    resources['order_service'] = create_ci(
        type_app,
        'order-service',
        BIZ_COMMERCE,
        'prod',
        '研发-张晨',
        'active',
        {
            'ip_address': '10.10.1.100',
            'language': 'Java',
            'framework': 'Spring Boot',
            'repo': 'git@gitlab.example.com:shop/order-service.git',
        },
    )
    resources['risk_service'] = create_ci(
        type_app,
        'risk-engine',
        BIZ_COMMERCE,
        'prod',
        '研发-赵羽',
        'active',
        {
            'ip_address': '10.10.1.101',
            'language': 'Go',
            'framework': 'Gin',
            'repo': 'git@gitlab.example.com:risk/risk-engine.git',
        },
    )
    resources['perf_test'] = create_ci(
        type_host,
        'order-perf-test-ecs',
        BIZ_COMMERCE,
        'test',
        '测试平台-陈芳',
        'active',
        {
            'ip_address': '192.0.2.2',
            'cpu': 16,
            'memory_gb': 32,
            'disk_gb': 500,
            'instance_type': 'ecs.g7.4xlarge',
            'avg_cpu_usage': 12,
            'avg_memory_usage': 28,
            'always_on': True,
            'cloud_provider': '阿里云 ECS',
            'monthly_cost': 860,
            'description': '性能压测结束后仍长期在线，未设置定时关机策略',
        },
    )
    resources['mysql_test'] = create_ci(
        type_db,
        'mysql-test-shared',
        BIZ_COMMERCE,
        'test',
        'QA-陈芳',
        'active',
        {
            'ip_address': '10.10.20.20',
            'version': 'MySQL 8.0',
            'cpu': 8,
            'memory_gb': 16,
            'storage_gb': 300,
            'avg_cpu_usage': 10,
            'avg_memory_usage': 24,
            'always_on': True,
            'cloud_provider': '阿里云 RDS',
            'monthly_cost': 620,
        },
    )
    resources['feature_dev'] = create_ci(
        type_host,
        'feature-x-dev-ecs',
        BIZ_COMMERCE,
        'dev',
        '研发-张晨',
        'idle',
        {
            'ip_address': '10.10.30.30',
            'cpu': 4,
            'memory_gb': 8,
            'disk_gb': 100,
            'instance_type': 'ecs.g6.xlarge',
            'avg_cpu_usage': 4,
            'avg_memory_usage': 18,
            'cloud_provider': '阿里云 ECS',
            'monthly_cost': 260,
            'description': '功能联调结束后未回收',
        },
    )

    resources['bi_warehouse'] = create_ci(
        type_warehouse,
        'clickhouse-bi-prod',
        BIZ_DATA,
        'prod',
        '数据平台-韩梅',
        'active',
        {
            'ip_address': '10.20.1.20',
            'cpu': 16,
            'memory_gb': 64,
            'storage_gb': 3000,
            'storage_utilization': 38,
            'avg_cpu_usage': 21,
            'avg_memory_usage': 42,
            'cloud_provider': '阿里云 ClickHouse',
            'monthly_cost': 2400,
            'description': 'BI 查询高峰集中在月初，其余时段容量冗余明显',
        },
    )
    resources['airflow_dev'] = create_ci(
        type_host,
        'airflow-worker-dev',
        BIZ_DATA,
        'dev',
        '数据平台-韩梅',
        'active',
        {
            'ip_address': '10.20.10.10',
            'cpu': 8,
            'memory_gb': 16,
            'disk_gb': 200,
            'avg_cpu_usage': 14,
            'avg_memory_usage': 32,
            'always_on': True,
            'cloud_provider': '阿里云 ECS',
            'monthly_cost': 760,
            'description': '仅工作日白天调度作业，但实例保持 24x7 运行',
        },
    )
    resources['data_sync'] = create_ci(
        type_host,
        'legacy-data-sync',
        BIZ_DATA,
        'prod',
        '数据集成-孙博',
        'offline',
        {
            'ip_address': '192.0.2.3',
            'cpu': 4,
            'memory_gb': 8,
            'disk_gb': 100,
            'avg_cpu_usage': 0,
            'avg_memory_usage': 0,
            'offline_days': 26,
            'cloud_provider': '阿里云 ECS',
            'monthly_cost': 520,
            'description': '旧版同步链路已切换到新链路，但资源仍在计费',
        },
    )

    resources['k8s_master'] = create_ci(
        type_host,
        'k8s-master-01',
        BIZ_INFRA,
        'prod',
        'SRE-王涛',
        'active',
        {
            'ip_address': '10.30.1.10',
            'cpu': 4,
            'memory_gb': 16,
            'avg_cpu_usage': 39,
            'avg_memory_usage': 52,
            'cloud_provider': '自建虚拟化',
            'monthly_cost': 380,
        },
    )
    resources['k8s_node_01'] = create_ci(
        type_host,
        'k8s-node-01',
        BIZ_INFRA,
        'prod',
        'SRE-王涛',
        'active',
        {
            'ip_address': '192.0.2.4',
            'cpu': 16,
            'memory_gb': 64,
            'avg_cpu_usage': 28,
            'avg_memory_usage': 44,
            'cloud_provider': '腾讯云 CVM',
            'monthly_cost': 1200,
        },
    )
    resources['k8s_node_02'] = create_ci(
        type_host,
        'k8s-node-02',
        BIZ_INFRA,
        'prod',
        'SRE-王涛',
        'active',
        {
            'ip_address': '10.30.1.12',
            'cpu': 16,
            'memory_gb': 64,
            'avg_cpu_usage': 31,
            'avg_memory_usage': 46,
            'cloud_provider': '腾讯云 CVM',
            'monthly_cost': 1200,
        },
    )
    resources['idc_compute_01'] = create_ci(
        type_idc_server,
        'idc-compute-01',
        BIZ_INFRA,
        'prod',
        '机房运维-刘洋',
        'active',
        {
            'asset_sn': 'IDC-ASSET-2024-0001',
            'private_ip': '10.40.1.21',
            'ip_address': '10.40.1.21',
            'idc': '上海张江 A1 机房',
            'rack': 'A1-R08',
            'u_position': '12U-13U',
            'lifecycle_status': 'running',
            'purchase_date': '2024-03-18',
            'service_expiry_date': '2027-03-17',
            'ops_owner': '机房运维-刘洋',
            'vendor': 'Dell',
            'model': 'PowerEdge R750',
            'serial_number': 'CN0R750240318001',
            'cpu': 64,
            'memory_gb': 256,
            'disk_gb': 4000,
            'raid_level': 'RAID10',
            'nic_count': 4,
            'power_supply': '双电源',
            'cloud_provider': '自建机房',
            'monthly_cost': 1800,
            'description': '生产 K8s 计算资源池物理节点，已登记硬件资产与服务周期信息',
        },
    )
    resources['idc_storage_01'] = create_ci(
        type_idc_server,
        'idc-storage-01',
        BIZ_INFRA,
        'prod',
        '机房运维-刘洋',
        'active',
        {
            'asset_sn': 'IDC-ASSET-2023-0038',
            'private_ip': '10.40.2.31',
            'ip_address': '10.40.2.31',
            'idc': '上海张江 A1 机房',
            'rack': 'A1-R12',
            'u_position': '20U-23U',
            'lifecycle_status': 'running',
            'purchase_date': '2023-09-06',
            'service_expiry_date': '2026-09-05',
            'ops_owner': '机房运维-刘洋',
            'vendor': 'H3C',
            'model': 'UniServer R4900 G5',
            'serial_number': 'H3C4900G52023090638',
            'cpu': 48,
            'memory_gb': 192,
            'disk_gb': 12000,
            'raid_level': 'RAID6',
            'nic_count': 6,
            'power_supply': '双电源',
            'cloud_provider': '自建机房',
            'monthly_cost': 2200,
            'description': '日志与备份存储物理节点，承载对象存储归档挂载',
        },
    )
    resources['log_storage'] = create_ci(
        type_storage,
        'log-archive-oss',
        BIZ_INFRA,
        'prod',
        'SRE-王涛',
        'active',
        {
            'storage_gb': 5000,
            'storage_utilization': 45,
            'cloud_provider': '阿里云 OSS',
            'monthly_cost': 980,
            'description': '冷热数据未分层，半年以上日志仍存放在标准存储',
        },
    )
    resources['legacy_vpn'] = create_ci(
        type_lb,
        'legacy-vpn-gateway',
        '',
        'prod',
        '',
        'active',
        {
            'ip_address': '172.16.0.10',
            'bandwidth': '20Mbps',
            'cloud_provider': '阿里云 VPN',
            'monthly_cost': 300,
            'description': '历史项目遗留专线网关，暂无负责人和业务归属',
        },
    )

    resources['ocr_platform'] = create_ci(
        type_third_party,
        'ocr-platform',
        BIZ_COMMERCE,
        'prod',
        '供应商-慧眼云',
        'active',
        {
            'provider': '慧眼 OCR',
            'endpoint': 'https://ocr.example.com',
            'cloud_provider': '慧眼 OCR',
            'monthly_cost': 650,
            'description': '证件识别与发票解析能力',
        },
    )
    resources['kingdee'] = create_ci(
        type_third_party,
        'kingdee-cloud',
        BIZ_COMMERCE,
        'prod',
        '供应商-金蝶',
        'active',
        {
            'provider': '金蝶云',
            'endpoint': 'https://api.kingdee.com',
            'cloud_provider': '金蝶云',
            'monthly_cost': 480,
            'description': '财务凭证与结算同步',
        },
    )
    resources['heweather'] = create_ci(
        type_third_party,
        'heweather-prod',
        BIZ_COMMERCE,
        'prod',
        '供应商-和风天气',
        'active',
        {
            'provider': '和风天气',
            'service_type': '天气 API',
            'account_subject': '生产主体',
            'account_owner': '应用运维-李俊',
            'key_owner': '安全运维-沈宁',
            'backup_plan': '控制台导出应用配置，每季度归档',
            'contract_no': 'HT-WEATHER-2026-001',
            'service_expiry_date': '2026-12-31',
            'service_expire_warning_days': 30,
            'endpoint': 'https://devapi.qweather.com',
            'cloud_provider': '和风天气',
            'monthly_cost': 320,
            'description': '订单履约和活动页展示天气能力，手工登记到第三方服务 CI',
        },
    )
    resources['amap'] = create_ci(
        type_third_party,
        'amap-prod',
        BIZ_COMMERCE,
        'prod',
        '供应商-高德地图',
        'active',
        {
            'provider': '高德地图',
            'service_type': '地图 API',
            'account_subject': '生产主体',
            'account_owner': '应用运维-李俊',
            'key_owner': '安全运维-沈宁',
            'backup_plan': '控制台导出 Key 与额度配置，每季度归档',
            'contract_no': 'HT-AMAP-2026-001',
            'service_expiry_date': '2026-11-30',
            'service_expire_warning_days': 30,
            'endpoint': 'https://restapi.amap.com',
            'cloud_provider': '高德地图',
            'monthly_cost': 360,
            'description': '门店定位、配送距离和地址解析能力，手工登记到第三方服务 CI',
        },
    )

    _log(stdout, 'Creating relations...')
    create_relation(resources['gateway'], resources['order_service'], 'connects_to', '网关分发订单流量')
    create_relation(resources['gateway'], resources['risk_service'], 'connects_to', '网关分发风控请求')
    create_relation(resources['order_service'], resources['order_host_a'], 'runs_on', '订单服务部署在订单节点 01')
    create_relation(resources['order_service'], resources['order_host_b'], 'runs_on', '订单服务部署在订单节点 02')
    create_relation(resources['order_service'], resources['order_db'], 'connects_to', '订单服务读写交易数据')
    create_relation(resources['order_service'], resources['order_cache'], 'connects_to', '订单服务依赖 Redis 缓存')
    create_relation(resources['risk_service'], resources['ocr_platform'], 'depends_on', '风控核验依赖 OCR 服务')
    create_relation(resources['order_service'], resources['kingdee'], 'depends_on', '账单结算同步到金蝶云')
    create_relation(resources['order_service'], resources['heweather'], 'depends_on', '订单履约页面依赖和风天气 API')
    create_relation(resources['order_service'], resources['amap'], 'depends_on', '配送地址解析依赖高德地图 API')
    create_relation(resources['perf_test'], resources['mysql_test'], 'connects_to', '压测环境连接共享测试库')
    create_relation(resources['bi_warehouse'], resources['log_storage'], 'depends_on', '离线分析依赖归档日志与数仓导入')
    create_relation(resources['airflow_dev'], resources['bi_warehouse'], 'depends_on', '开发调度任务访问数仓')
    create_relation(resources['k8s_node_01'], resources['k8s_master'], 'connects_to', '工作节点加入生产集群')
    create_relation(resources['k8s_node_02'], resources['k8s_master'], 'connects_to', '工作节点加入生产集群')
    create_relation(resources['k8s_master'], resources['idc_compute_01'], 'runs_on', '生产 K8s 控制面依赖机房计算节点')
    create_relation(resources['log_storage'], resources['idc_storage_01'], 'depends_on', '归档对象存储底层挂载机房存储节点')
    create_relation(resources['legacy_vpn'], resources['gateway'], 'connects_to', '遗留专线网关仍与入口网关打通')

    _log(stdout, 'Creating cost records...')
    history_profile = [Decimal('0.84'), Decimal('0.89'), Decimal('0.94'), Decimal('1.03'), Decimal('1.08'), Decimal('1.00')]
    resource_profiles = {
        'gateway': [Decimal('0.92'), Decimal('0.95'), Decimal('0.98'), Decimal('1.00'), Decimal('1.03'), Decimal('1.00')],
        'order_host_a': history_profile,
        'order_host_b': history_profile,
        'order_db': [Decimal('0.88'), Decimal('0.92'), Decimal('0.97'), Decimal('1.04'), Decimal('1.10'), Decimal('1.00')],
        'order_cache': [Decimal('0.86'), Decimal('0.90'), Decimal('0.95'), Decimal('1.02'), Decimal('1.05'), Decimal('1.00')],
        'perf_test': [Decimal('0.70'), Decimal('0.78'), Decimal('0.88'), Decimal('1.00'), Decimal('1.06'), Decimal('1.00')],
        'mysql_test': [Decimal('0.78'), Decimal('0.82'), Decimal('0.90'), Decimal('0.98'), Decimal('1.04'), Decimal('1.00')],
        'feature_dev': [Decimal('0.60'), Decimal('0.70'), Decimal('0.82'), Decimal('0.92'), Decimal('1.00'), Decimal('1.00')],
        'bi_warehouse': [Decimal('0.74'), Decimal('0.82'), Decimal('0.91'), Decimal('1.02'), Decimal('1.12'), Decimal('1.00')],
        'airflow_dev': [Decimal('0.68'), Decimal('0.76'), Decimal('0.85'), Decimal('0.96'), Decimal('1.05'), Decimal('1.00')],
        'data_sync': [Decimal('1.00'), Decimal('1.00'), Decimal('1.00'), Decimal('1.00'), Decimal('1.00'), Decimal('1.00')],
        'k8s_master': [Decimal('0.92'), Decimal('0.95'), Decimal('0.98'), Decimal('1.00'), Decimal('1.01'), Decimal('1.00')],
        'k8s_node_01': [Decimal('0.87'), Decimal('0.90'), Decimal('0.96'), Decimal('1.04'), Decimal('1.07'), Decimal('1.00')],
        'k8s_node_02': [Decimal('0.87'), Decimal('0.90'), Decimal('0.96'), Decimal('1.04'), Decimal('1.07'), Decimal('1.00')],
        'idc_compute_01': [Decimal('0.90'), Decimal('0.94'), Decimal('0.98'), Decimal('1.02'), Decimal('1.03'), Decimal('1.00')],
        'idc_storage_01': [Decimal('0.86'), Decimal('0.90'), Decimal('0.95'), Decimal('1.01'), Decimal('1.04'), Decimal('1.00')],
        'log_storage': [Decimal('0.80'), Decimal('0.88'), Decimal('0.96'), Decimal('1.05'), Decimal('1.11'), Decimal('1.00')],
        'legacy_vpn': [Decimal('1.00'), Decimal('1.00'), Decimal('1.00'), Decimal('1.00'), Decimal('1.00'), Decimal('1.00')],
        'ocr_platform': [Decimal('0.85'), Decimal('0.89'), Decimal('0.93'), Decimal('1.00'), Decimal('1.04'), Decimal('1.00')],
        'kingdee': [Decimal('0.88'), Decimal('0.92'), Decimal('0.96'), Decimal('1.00'), Decimal('1.02'), Decimal('1.00')],
        'heweather': [Decimal('0.82'), Decimal('0.86'), Decimal('0.91'), Decimal('0.97'), Decimal('1.03'), Decimal('1.00')],
        'amap': [Decimal('0.84'), Decimal('0.88'), Decimal('0.93'), Decimal('0.98'), Decimal('1.04'), Decimal('1.00')],
    }

    months = _months()
    for resource_key, ci in resources.items():
        attributes = ci.attributes or {}
        monthly_cost = attributes.get('monthly_cost')
        if not monthly_cost:
            continue
        provider = _provider(attributes)
        for month, amount in zip(months, _build_amounts(monthly_cost, resource_profiles.get(resource_key, history_profile))):
            CostRecord.objects.update_or_create(
                ci=ci,
                month=month,
                defaults={'amount': amount, 'provider': provider},
            )

    _log(stdout, 'Creating resource metric snapshots...')
    metric_profiles = {
        'gateway': {'cpu_usage': 34, 'memory_usage': 46},
        'order_host_a': {'cpu_usage': 43, 'memory_usage': 52, 'disk_usage': 58},
        'order_host_b': {'cpu_usage': 41, 'memory_usage': 49, 'disk_usage': 62},
        'order_db': {'cpu_usage': 47, 'memory_usage': 61, 'storage_usage': 68},
        'order_cache': {'cpu_usage': 36, 'memory_usage': 63},
        'perf_test': {'cpu_usage': 12, 'memory_usage': 28, 'disk_usage': 35},
        'mysql_test': {'cpu_usage': 10, 'memory_usage': 24, 'storage_usage': 82},
        'feature_dev': {'cpu_usage': 4, 'memory_usage': 18, 'disk_usage': 12},
        'bi_warehouse': {'cpu_usage': 21, 'memory_usage': 42, 'storage_usage': 38},
        'airflow_dev': {'cpu_usage': 14, 'memory_usage': 32, 'disk_usage': 31},
        'data_sync': {'cpu_usage': 0, 'memory_usage': 0, 'disk_usage': 3},
        'k8s_master': {'cpu_usage': 39, 'memory_usage': 52, 'disk_usage': 47},
        'k8s_node_01': {'cpu_usage': 28, 'memory_usage': 44, 'disk_usage': 53},
        'k8s_node_02': {'cpu_usage': 31, 'memory_usage': 46, 'disk_usage': 55},
        'idc_compute_01': {'cpu_usage': 57, 'memory_usage': 64, 'disk_usage': 49},
        'idc_storage_01': {'cpu_usage': 32, 'memory_usage': 58, 'disk_usage': 76},
        'log_storage': {'storage_usage': 88},
    }
    collected_at = timezone.now()
    for resource_key, metrics in metric_profiles.items():
        ci = resources.get(resource_key)
        if not ci:
            continue
        for metric, usage_percent in metrics.items():
            create_metric(ci, metric, usage_percent, collected_at=collected_at)

    _log(stdout, 'Creating host requests...')
    ResourceRequest.objects.bulk_create([
        ResourceRequest(
            title='订单服务生产扩容（order-api-ecs-02）',
            applicant='研发-张晨',
            approver='应用运维-李俊',
            resource_type='主机',
            specification='ecs.g7.2xlarge / 8C16G / 200G',
            business_line=BIZ_COMMERCE,
            environment='prod',
            priority='high',
            quantity=1,
            specs={
                'hostname': 'order-api-ecs-02',
                'ip_address': '10.10.1.11',
                'instance_type': 'ecs.g7.2xlarge',
            },
            reason='订单服务生产流量上涨，需要补齐第二台应用节点。',
            approval_comment='生产扩容方案确认，通过后已安排交付。',
            fulfillment_note='已交付并纳入主机资产与 CMDB 配置项。',
            status='completed',
            approved_at=timezone.now() - timezone.timedelta(days=12),
            completed_at=timezone.now() - timezone.timedelta(days=10),
        ),
        ResourceRequest(
            title='压测环境主机保留申请（order-perf-test-ecs）',
            applicant='测试平台-陈芳',
            approver='平台架构组',
            resource_type='主机',
            specification='ecs.g7.4xlarge / 16C32G / 500G',
            business_line=BIZ_COMMERCE,
            environment='test',
            priority='medium',
            quantity=1,
            specs={
                'hostname': 'order-perf-test-ecs',
                'ip_address': '192.0.2.2',
                'instance_type': 'ecs.g7.4xlarge',
            },
            reason='压测环境希望继续保留现有主机一个迭代周期。',
            approval_comment='当前利用率偏低，建议压测结束后及时回收，不同意长期保留。',
            status='rejected',
            approved_at=timezone.now() - timezone.timedelta(days=6),
        ),
        ResourceRequest(
            title='遗留同步主机替换申请（legacy-data-sync）',
            applicant='数据集成-孙博',
            approver='SRE-王涛',
            resource_type='主机',
            specification='通用型主机 / 4C8G / 100G',
            business_line=BIZ_DATA,
            environment='prod',
            priority='medium',
            quantity=1,
            specs={
                'hostname': 'legacy-data-sync',
                'ip_address': '192.0.2.3',
                'replacement': True,
            },
            reason='遗留同步主机已离线，需审批后执行替换或下线回收。',
            approval_comment='同意先保留窗口，待迁移计划落地后执行交付。',
            status='approved',
            approved_at=timezone.now() - timezone.timedelta(days=2),
        ),
        ResourceRequest(
            title='开发调度节点续用申请（airflow-worker-dev）',
            applicant='数据平台-韩梅',
            resource_type='主机',
            specification='开发环境调度节点 / 8C16G / 200G',
            business_line=BIZ_DATA,
            environment='dev',
            priority='low',
            quantity=1,
            specs={
                'hostname': 'airflow-worker-dev',
                'ip_address': '10.20.10.10',
            },
            reason='当前开发调度任务持续使用该主机，希望保留并补充资源说明。',
            status='pending',
        ),
    ])

    _log(
        stdout,
        f'Seeded {ConfigItem.objects.count()} config items, {CIRelation.objects.count()} relations, '
        f'{CostRecord.objects.count()} cost records, {CIResourceMetricSnapshot.objects.count()} metric snapshots '
        f'and {ResourceRequest.objects.count()} host requests.',
    )
