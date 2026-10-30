import re

from django.db import transaction
from django.utils import timezone

from multicloud.models import CloudAsset, CloudCredential, CloudEnvironment
from multicloud.sdk_adapters import CloudAdapterError, get_cloud_adapter


SUPPORTED_PROVIDERS = {
    'aliyun': {
        'label': '阿里云 ECS',
        'required_fields': ['image_id', 'instance_type', 'security_group_id', 'vswitch_id'],
    },
    'huawei': {
        'label': '华为云 ECS',
        'required_fields': ['image_id', 'flavor_ref', 'security_group_id', 'vpc_id', 'subnet_id'],
    },
    'vsphere': {
        'label': 'vSphere 虚拟机',
        'required_fields': ['template_name', 'datastore_name'],
    },
}

ALIYUN_RESOURCE_TYPES = [
    {'value': 'ecs', 'label': '云服务器 ECS', 'ci_type_code': 'CLOUD_SERVER', 'delivery': 'cloud', 'fields': ['image_id', 'instance_type', 'security_group_id', 'vswitch_id']},
    {'value': 'rds', 'label': '云数据库 RDS', 'ci_type_code': 'MYSQL', 'delivery': 'manual', 'fields': ['engine', 'instance_class', 'storage_gb']},
    {'value': 'redis', 'label': '云数据库 Redis', 'ci_type_code': 'REDIS', 'delivery': 'manual', 'fields': ['instance_class', 'capacity_gb']},
    {'value': 'mongodb', 'label': '云数据库 MongoDB', 'ci_type_code': 'MONGODB', 'delivery': 'manual', 'fields': ['instance_class', 'storage_gb']},
    {'value': 'kafka', 'label': '消息队列 Kafka', 'ci_type_code': 'KAFKA', 'delivery': 'manual', 'fields': ['instance_class', 'storage_gb']},
    {'value': 'rocketmq', 'label': '消息队列 RocketMQ', 'ci_type_code': 'ROCKETMQ', 'delivery': 'manual', 'fields': ['instance_class', 'storage_gb']},
    {'value': 'oss', 'label': '对象存储 OSS', 'ci_type_code': 'OBJECT_STORAGE', 'delivery': 'manual', 'fields': ['bucket_name', 'storage_gb']},
    {'value': 'slb', 'label': '负载均衡 SLB', 'ci_type_code': 'LOAD_BALANCER', 'delivery': 'manual', 'fields': ['instance_spec', 'vpc_id']},
    {'value': 'ack', 'label': '容器服务 ACK', 'ci_type_code': 'K8S_CLUSTER', 'delivery': 'manual', 'fields': ['cluster_version', 'node_count']},
    {'value': 'disk', 'label': '云盘', 'ci_type_code': 'BLOCK_STORAGE', 'delivery': 'manual', 'fields': ['storage_gb', 'storage_type']},
    {'value': 'nas', 'label': '文件存储 NAS', 'ci_type_code': 'FILE_STORAGE', 'delivery': 'manual', 'fields': ['storage_gb', 'storage_type']},
    {'value': 'clickhouse', 'label': '云数据库 ClickHouse', 'ci_type_code': 'CLICKHOUSE', 'delivery': 'manual', 'fields': ['instance_class', 'storage_gb']},
    {'value': 'hologres', 'label': '实时数仓 Hologres', 'ci_type_code': 'HOLOGRES', 'delivery': 'manual', 'fields': ['instance_class', 'storage_gb']},
    {'value': 'maxcompute', 'label': '大数据计算 MaxCompute', 'ci_type_code': 'MAXCOMPUTE', 'delivery': 'manual', 'fields': ['project_name', 'quota']},
    {'value': 'dataworks', 'label': '数据开发 DataWorks', 'ci_type_code': 'DATAWORKS', 'delivery': 'manual', 'fields': ['workspace_name', 'edition']},
    {'value': 'nat_gateway', 'label': 'NAT 网关', 'ci_type_code': 'NAT_GATEWAY', 'delivery': 'manual', 'fields': ['specification', 'vpc_id']},
    {'value': 'eip', 'label': '弹性公网 IP', 'ci_type_code': 'ELASTIC_IP', 'delivery': 'manual', 'fields': ['bandwidth_mbps', 'ip_count']},
    {'value': 'elasticsearch', 'label': '云搜索 Elasticsearch', 'ci_type_code': 'ELASTICSEARCH', 'delivery': 'manual', 'fields': ['instance_class', 'storage_gb']},
]
ALIYUN_RESOURCE_TYPE_MAP = {item['value']: item for item in ALIYUN_RESOURCE_TYPES}


def provider_label(provider):
    return SUPPORTED_PROVIDERS.get(provider, {}).get('label', provider or '人工交付')


def build_provisioning_options():
    credentials = CloudCredential.objects.filter(
        is_enabled=True,
        provider__in=SUPPORTED_PROVIDERS,
    ).order_by('provider', 'name')
    return {
        'providers': [
            {'value': key, 'label': value['label'], 'required_fields': value['required_fields']}
            for key, value in SUPPORTED_PROVIDERS.items()
        ],
        'credentials': [
            {
                'id': item.id,
                'provider': item.provider,
                'provider_label': provider_label(item.provider),
                'name': item.name,
                'account_name': item.account_name,
                'default_region': item.default_region,
                'health': item.last_test_status,
                'health_message': item.last_test_message,
            }
            for item in credentials
        ],
        'resource_types': ALIYUN_RESOURCE_TYPES,
        'aliyun_resource_types': ALIYUN_RESOURCE_TYPES,
    }


def validate_provisioning_specs(specs, quantity=1):
    normalized = dict(specs or {})
    mode = str(normalized.get('provisioning_mode') or 'manual').strip().lower()
    normalized['provisioning_mode'] = mode
    if mode == 'manual':
        return normalized
    if mode != 'cloud':
        raise ValueError('交付方式仅支持云平台自动交付或人工交付。')

    provider = str(normalized.get('provider') or '').strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError('自动交付当前仅支持阿里云、华为云和 vSphere。')
    normalized['provider'] = provider
    resource_type = str(normalized.get('resource_type') or normalized.get('asset_type') or 'ecs').strip().lower()
    if resource_type in {'主机', 'host'}:
        resource_type = 'ecs'
    if provider == 'aliyun' and resource_type not in ALIYUN_RESOURCE_TYPE_MAP:
        raise ValueError('阿里云资源类型不受支持，请重新选择资产类型。')
    if provider == 'aliyun' and resource_type != 'ecs':
        raise ValueError('当前仅支持阿里云 ECS 自动交付，其他阿里云资产请提交人工交付申请。')
    try:
        credential_id = int(normalized.get('cloud_credential_id'))
    except (TypeError, ValueError):
        raise ValueError('请选择用于自动交付的云账号。')
    credential = CloudCredential.objects.filter(id=credential_id, is_enabled=True).first()
    if not credential:
        raise ValueError('所选云账号不存在或已停用。')
    if credential.provider != provider:
        raise ValueError('所选云账号与目标云平台不匹配。')
    normalized['cloud_credential_id'] = credential_id
    normalized['region'] = str(normalized.get('region') or credential.default_region or '').strip()
    if not normalized['region']:
        raise ValueError('请填写目标地域或 vSphere 站点。')

    name_prefix = str(normalized.get('instance_name_prefix') or normalized.get('hostname') or '').strip()
    if not name_prefix:
        raise ValueError('请填写实例名称或批量命名前缀。')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{1,62}', name_prefix):
        raise ValueError('实例名称需为 2-63 位字母、数字、点、下划线或中划线，并以字母或数字开头。')
    normalized['instance_name_prefix'] = name_prefix

    missing = [
        field for field in SUPPORTED_PROVIDERS[provider]['required_fields']
        if not str(normalized.get(field) or '').strip()
    ]
    if missing:
        raise ValueError(f'自动交付缺少必要参数：{"、".join(missing)}。')
    if quantity < 1 or quantity > 20:
        raise ValueError('单次自动交付数量需在 1-20 台之间。')
    return normalized


def build_instance_names(specs, quantity):
    prefix = specs['instance_name_prefix']
    if quantity == 1:
        return [prefix]
    return [f'{prefix}-{index:02d}' for index in range(1, quantity + 1)]


def provision_resource_request(request_obj):
    specs = validate_provisioning_specs(request_obj.specs or {}, request_obj.quantity)
    credential = CloudCredential.objects.get(id=specs['cloud_credential_id'], is_enabled=True)
    adapter = get_cloud_adapter(credential)
    if not adapter or not adapter.capability().get('supports_provisioning'):
        raise CloudAdapterError(f'{provider_label(credential.provider)} 当前环境未启用自动交付能力。')
    resources = adapter.provision_instances(
        request_obj.id,
        specs,
        build_instance_names(specs, request_obj.quantity),
    )
    if len(resources) != request_obj.quantity:
        raise CloudAdapterError(
            f'云平台返回 {len(resources)} 台实例，与申请数量 {request_obj.quantity} 不一致。'
        )
    _sync_multicloud_assets(credential, request_obj, resources)
    return credential, resources


def _environment_code(credential, region):
    base = re.sub(r'[^a-z0-9-]+', '-', f'{credential.provider}-{credential.id}-{region}'.lower()).strip('-')[:56]
    candidate = base or f'cloud-{credential.id}'
    suffix = 1
    while CloudEnvironment.objects.exclude(credential=credential, region=region).filter(code=candidate).exists():
        suffix += 1
        candidate = f'{base[:56]}-{suffix}'
    return candidate


@transaction.atomic
def _sync_multicloud_assets(credential, request_obj, resources):
    region = str((request_obj.specs or {}).get('region') or credential.default_region or '').strip()
    environment = CloudEnvironment.objects.filter(credential=credential, region=region).first()
    if not environment:
        environment = CloudEnvironment.objects.create(
            credential=credential,
            name=f'{credential.name} / {region}',
            code=_environment_code(credential, region),
            business_line=request_obj.business_line,
            environment_type=request_obj.environment if request_obj.environment in {'prod', 'test', 'dev'} else 'shared',
            region=region,
            owner=request_obj.applicant,
            description=f'由资源申请 #{request_obj.id} 自动创建',
            created_by=request_obj.approver or request_obj.applicant,
            updated_by=request_obj.approver or request_obj.applicant,
        )
    now = timezone.now()
    for item in resources:
        raw_status = str(item.get('status') or '').lower()
        asset_status = 'stopped' if raw_status in {'stopped', 'poweredoff', 'shutoff'} else 'error' if raw_status == 'error' else 'running'
        CloudAsset.objects.update_or_create(
            environment=environment,
            resource_type='ecs',
            resource_id=item['instance_id'],
            defaults={
                'provider': credential.provider,
                'name': item['hostname'],
                'region': item.get('region') or region,
                'zone': item.get('zone') or '',
                'status': asset_status,
                'charge_type': 'private_cloud' if credential.provider == 'vsphere' else 'on_demand',
                'private_ip': item.get('private_ip') or '',
                'public_ip': item.get('public_ip') or '',
                'vpc_name': (request_obj.specs or {}).get('vpc_id') or '',
                'spec': item.get('instance_type') or request_obj.specification,
                'tags': {'sxdevops-request-id': str(request_obj.id)},
                'metadata': {
                    'resource_request_id': request_obj.id,
                    'provisioning_job_id': item.get('job_id') or '',
                },
                'synced_at': now,
            },
        )
    environment.sync_status = 'success'
    environment.last_sync_at = now
    environment.save(update_fields=['sync_status', 'last_sync_at', 'updated_at'])
