from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
import re

from django.utils import timezone

from cmdb.models import CIType, ConfigItem, CostRecord

from .models import CloudAsset, CloudCredential, CloudEnvironment, CloudSyncTask
from .sdk_adapters import CloudAdapterError, get_cloud_adapter, get_provider_sdk_capabilities


PROVIDER_CATALOG = {
    'aliyun': {
        'label': '阿里云',
        'regions': ['cn-hangzhou', 'cn-shanghai'],
        'default_region': 'cn-hangzhou',
        'resource_types': ['ecs', 'rds', 'slb', 'k8s', 'redis', 'oss', 'nat', 'eip'],
        'description': '适合国内生产环境与交易类业务。',
    },
    'tencent': {
        'label': '腾讯云',
        'regions': ['ap-guangzhou', 'ap-shanghai'],
        'default_region': 'ap-guangzhou',
        'resource_types': ['ecs', 'rds', 'slb', 'k8s', 'redis'],
        'description': '适合测试、灰度和高并发业务。',
    },
    'huawei': {
        'label': '华为云',
        'regions': ['cn-north-4', 'cn-east-3'],
        'default_region': 'cn-north-4',
        'resource_types': ['ecs', 'rds', 'k8s', 'nat', 'eip'],
        'description': '适合政企、容灾和混合云场景。',
    },
    'baidu': {
        'label': '百度智能云',
        'regions': ['bj', 'gz'],
        'default_region': 'bj',
        'resource_types': ['ecs', 'rds', 'slb', 'k8s'],
        'description': '适合 AI 与搜索类业务。',
    },
    'aws': {
        'label': 'AWS',
        'regions': ['ap-southeast-1', 'eu-central-1'],
        'default_region': 'ap-southeast-1',
        'resource_types': ['ecs', 'rds', 'slb', 'k8s', 'redis', 'oss', 'nat', 'eip'],
        'description': '适合出海与全球化业务。',
    },
    'vsphere': {
        'label': 'VMware vSphere / ESXi',
        'regions': ['private-cloud'],
        'default_region': 'private-cloud',
        'resource_types': ['ecs'],
        'description': '适合机房私有云资源接入，当前优先支持 VMware ESXi / vCenter 8.0.2 VM 资产同步。',
    },
}

DEMO_MODE_DISABLED_MESSAGE = 'Demo 模式已下线，请配置真实账号凭据。'


def _is_demo_credential(credential):
    return bool(getattr(credential, 'demo_mode', False)) or str(getattr(credential, 'auth_mode', '') or '').strip().lower() == 'demo'


CMDB_TYPE_MAP = {
    'ecs': '云主机',
    'rds': 'MySQL',
    'slb': '负载均衡',
    'k8s': 'K8s 集群',
    'redis': 'Redis',
    'oss': '对象存储',
    'nat': 'NAT 网关',
    'eip': '弹性 IP',
    'security_group': '安全组',
}

CMDB_TYPE_MAP = {
    'ecs': '云主机(ECS)',
    'rds': 'MySQL',
    'slb': '负载均衡',
    'k8s': 'K8s 集群',
    'redis': 'Redis',
    'oss': '对象存储',
    'nat': 'NAT 网关',
    'eip': '弹性 IP',
    'security_group': '安全组',
}

CMDB_TYPE_CODE_MAP = {
    'ecs': 'CLOUD_SERVER',
    'rds': 'MYSQL',
    'slb': 'LOAD_BALANCER',
    'k8s': 'K8S_CLUSTER',
    'redis': 'REDIS',
    'oss': 'OBJECT_STORAGE',
    'nat': 'NAT_GATEWAY',
    'eip': 'ELASTIC_IP',
    'security_group': 'SECURITY_GROUP',
}

VSPHERE_VM_CMDB_TYPE = {
    'name': '虚拟机',
    'code': 'VIRTUAL_MACHINE',
    'icon': 'Platform',
    'color': '#0ea5e9',
    'description': '私有云或虚拟化平台中的虚拟机实例，当前支持 vSphere / ESXi 自动注册。',
}

BASE_COST = {
    'ecs': Decimal('680'),
    'rds': Decimal('1280'),
    'slb': Decimal('320'),
    'k8s': Decimal('880'),
    'redis': Decimal('410'),
    'oss': Decimal('120'),
    'nat': Decimal('180'),
    'eip': Decimal('99'),
    'security_group': Decimal('0'),
}

RESOURCE_LINKS = {
    'slb': ['ecs', 'k8s'],
    'ecs': ['rds', 'redis'],
    'k8s': ['rds', 'redis', 'oss'],
    'nat': ['ecs', 'k8s'],
    'security_group': ['ecs', 'rds', 'redis'],
}


def build_provider_catalog():
    capabilities = get_provider_sdk_capabilities()
    catalog = {}
    for provider, meta in PROVIDER_CATALOG.items():
        catalog[provider] = {
            **meta,
            'sdk': capabilities.get(provider, {}),
        }
    return catalog


def provider_label(provider):
    return PROVIDER_CATALOG.get(provider, {}).get('label', provider)


def resource_type_label(resource_type):
    return dict(CloudAsset.RESOURCE_TYPE_CHOICES).get(resource_type, resource_type)


def _cmdb_type_meta_for_asset(asset):
    provider = (asset.provider or '').lower()
    resource_type = (asset.resource_type or '').lower()
    if provider == 'vsphere' and resource_type in {'ecs', 'vm', 'virtual_machine'}:
        return VSPHERE_VM_CMDB_TYPE
    return {
        'name': CMDB_TYPE_MAP.get(resource_type, '云主机(ECS)'),
        'code': CMDB_TYPE_CODE_MAP.get(resource_type, ''),
        'icon': '',
        'color': '#3b82f6',
        'description': '由多云模块自动创建',
    }


def _get_or_create_cmdb_type(meta):
    code = meta.get('code') or ''
    name = meta.get('name') or '云主机(ECS)'
    ci_type = CIType.objects.filter(code=code).first() if code else None
    if not ci_type:
        ci_type, _ = CIType.objects.get_or_create(
            name=name,
            defaults={
                'code': code,
                'icon': meta.get('icon', ''),
                'color': meta.get('color', '#3b82f6'),
                'description': meta.get('description', '由多云模块自动创建'),
            },
        )
    update_fields = []
    if code and not ci_type.code:
        ci_type.code = code
        update_fields.append('code')
    if meta.get('icon') and not ci_type.icon:
        ci_type.icon = meta['icon']
        update_fields.append('icon')
    if update_fields:
        ci_type.save(update_fields=[*update_fields, 'updated_at'])
    return ci_type


def _find_existing_cmdb_item_for_asset(asset, ci_type):
    source_filter = {
        'attributes__cmdb_source': 'multicloud',
        'attributes__provider': asset.provider,
        'attributes__resource_id': asset.resource_id,
    }
    matches = ConfigItem.objects.filter(**source_filter).order_by('id')
    ci = matches.filter(ci_type=ci_type).first() or matches.first()
    if ci:
        matches.exclude(id=ci.id).delete()
        return ci
    return ConfigItem.objects.filter(
        name=asset.name,
        attributes__cmdb_source='multicloud',
        attributes__provider=asset.provider,
        attributes__account_id=asset.environment.credential.account_id,
    ).order_by('id').first()


def test_credential_connection(credential):
    region = credential.default_region or PROVIDER_CATALOG.get(credential.provider, {}).get('default_region', '')
    if _is_demo_credential(credential):
        result = {
            'success': False,
            'status': 'error',
            'message': DEMO_MODE_DISABLED_MESSAGE,
            'region': region,
            'demo_mode': bool(getattr(credential, 'demo_mode', False)),
            'sdk_mode': 'disabled',
        }
    elif not credential.is_enabled:
        result = {
            'success': True,
            'status': 'warning',
            'message': 'Credential is disabled. Connectivity check skipped.',
            'region': region,
            'demo_mode': False,
            'sdk_mode': 'disabled',
        }
    else:
        adapter = get_cloud_adapter(credential)
        if not adapter:
            result = {
                'success': False,
                'status': 'warning',
                'message': f'No SDK adapter configured for provider {credential.provider}.',
                'region': region,
                'demo_mode': False,
                'sdk_mode': 'missing-adapter',
            }
        else:
            try:
                result = adapter.test_connection()
            except CloudAdapterError as exc:
                result = {
                    'success': False,
                    'status': 'warning',
                    'message': str(exc),
                    'region': region,
                    'demo_mode': False,
                    'sdk_mode': 'sdk-unavailable',
                }
            except Exception as exc:
                result = {
                    'success': False,
                    'status': 'error',
                    'message': f'Live SDK connection failed: {exc}',
                    'region': region,
                    'demo_mode': False,
                    'sdk_mode': 'sdk-error',
                }

    credential.last_test_status = result['status']
    credential.last_test_message = result['message']
    credential.save(update_fields=['last_test_status', 'last_test_message', 'updated_at'])
    return result


def _zone(region):
    if not region:
        return ''
    if region.startswith('cn-'):
        return f'{region}-a'
    if region.startswith('ap-'):
        return f'{region}-1'
    return f'{region}a'


def _factor(environment):
    return {
        'prod': Decimal('1.00'),
        'test': Decimal('0.58'),
        'dev': Decimal('0.32'),
        'shared': Decimal('0.75'),
    }.get(environment.environment_type, Decimal('0.55'))


def _asset(name, resource_type, environment, region, zone, **kwargs):
    default = {
        'name': name,
        'provider': environment.credential.provider,
        'region': region,
        'zone': zone,
        'status': 'running',
        'charge_type': '按量付费',
        'private_ip': '',
        'public_ip': '',
        'vpc_name': environment.vpc_name or f'vpc-{environment.code}',
        'spec': '',
        'cpu': 0,
        'memory_gb': Decimal('0'),
        'disk_gb': Decimal('0'),
        'monthly_cost': Decimal('0'),
        'risk_level': 'normal',
        'sync_state': 'synced',
        'tags': {},
        'metadata': {},
    }
    default.update(kwargs)
    default['resource_type'] = resource_type
    default['resource_id'] = kwargs.get('resource_id') or f'{environment.credential.provider}-{resource_type}-{environment.code}-{name}'
    return default


def _inventory(environment):
    provider = environment.credential.provider
    factor = _factor(environment)
    region = environment.region or environment.credential.default_region or PROVIDER_CATALOG.get(provider, {}).get('default_region', '')
    zone = environment.zone or _zone(region)
    if provider == 'vsphere':
        prefix = environment.code
        return [
            _asset(
                f'{prefix}-vm-01',
                'ecs',
                environment,
                region,
                zone,
                private_ip='10.60.11.10',
                charge_type='私有云',
                spec='VMware VM / 4C8G',
                cpu=4,
                memory_gb=Decimal('8.0'),
                disk_gb=Decimal('120.0'),
                monthly_cost=Decimal('0.00'),
                tags={'role': 'vm', 'platform': 'vsphere'},
                metadata={'hypervisor': 'VMware ESXi', 'supported_version': '8.0.2', 'avg_cpu': 36, 'avg_memory': 52},
            ),
            _asset(
                f'{prefix}-vm-02',
                'ecs',
                environment,
                region,
                zone,
                private_ip='10.60.11.11',
                charge_type='私有云',
                spec='VMware VM / 2C4G',
                cpu=2,
                memory_gb=Decimal('4.0'),
                disk_gb=Decimal('80.0'),
                monthly_cost=Decimal('0.00'),
                tags={'role': 'vm', 'platform': 'vsphere'},
                metadata={'hypervisor': 'VMware ESXi', 'supported_version': '8.0.2', 'avg_cpu': 18, 'avg_memory': 41},
            ),
        ]
    ip_prefix = {
        'prod': '10.10',
        'test': '10.20',
        'dev': '10.30',
        'shared': '10.40',
    }.get(environment.environment_type, '10.50')
    public_prefix = {
        'aliyun': '47.96',
        'tencent': '119.29',
        'huawei': '124.70',
        'baidu': '180.76',
        'aws': '54.251',
    }.get(provider, '198.18')
    prefix = environment.code
    rows = [
        _asset(
            f'{prefix}-app-01',
            'ecs',
            environment,
            region,
            zone,
            private_ip=f'{ip_prefix}.11.10',
            public_ip=f'{public_prefix}.10.10',
            spec='4C8G',
            cpu=4,
            memory_gb=Decimal('8.0'),
            disk_gb=Decimal('120.0'),
            monthly_cost=(BASE_COST['ecs'] * factor).quantize(Decimal('0.01')),
            tags={'role': 'app'},
            metadata={'avg_cpu': 42, 'avg_memory': 56},
        ),
        _asset(
            f'{prefix}-batch-01',
            'ecs',
            environment,
            region,
            zone,
            private_ip=f'{ip_prefix}.11.11',
            spec='2C4G',
            cpu=2,
            memory_gb=Decimal('4.0'),
            disk_gb=Decimal('80.0'),
            status='stopped' if environment.environment_type in {'dev', 'test'} else 'running',
            monthly_cost=(BASE_COST['ecs'] * factor * Decimal('0.64')).quantize(Decimal('0.01')),
            risk_level='warning' if environment.environment_type in {'dev', 'test'} else 'normal',
            sync_state='idle' if environment.environment_type in {'dev', 'test'} else 'synced',
            tags={'role': 'batch'},
            metadata={'avg_cpu': 7, 'avg_memory': 18},
        ),
        _asset(
            f'{prefix}-mysql',
            'rds',
            environment,
            region,
            zone,
            private_ip=f'{ip_prefix}.2.20',
            charge_type='包年包月',
            spec='MySQL 8.0 / 4C16G',
            cpu=4,
            memory_gb=Decimal('16.0'),
            disk_gb=Decimal('500.0'),
            monthly_cost=(BASE_COST['rds'] * factor).quantize(Decimal('0.01')),
            risk_level='warning' if environment.environment_type == 'prod' else 'normal',
            sync_state='drift' if environment.environment_type == 'prod' else 'synced',
            tags={'role': 'database'},
            metadata={'connections': 321},
        ),
        _asset(
            f'{prefix}-ingress',
            'slb',
            environment,
            region,
            zone,
            public_ip=f'{public_prefix}.20.20',
            spec='公网型负载均衡',
            monthly_cost=(BASE_COST['slb'] * factor).quantize(Decimal('0.01')),
            risk_level='critical' if environment.environment_type == 'prod' else 'warning',
            tags={'role': 'entrypoint'},
            metadata={'cert_expire_days': 12},
        ),
        _asset(
            f'{prefix}-cluster',
            'k8s',
            environment,
            region,
            zone,
            charge_type='包年包月',
            spec='托管集群 / 3 worker',
            cpu=12,
            memory_gb=Decimal('48.0'),
            disk_gb=Decimal('300.0'),
            monthly_cost=(BASE_COST['k8s'] * factor).quantize(Decimal('0.01')),
            tags={'role': 'container'},
            metadata={'node_count': 3},
        ),
        _asset(
            f'{prefix}-redis',
            'redis',
            environment,
            region,
            zone,
            private_ip=f'{ip_prefix}.2.30',
            spec='主从 / 8GB',
            cpu=2,
            memory_gb=Decimal('8.0'),
            disk_gb=Decimal('20.0'),
            status='degraded' if environment.environment_type == 'prod' else 'running',
            monthly_cost=(BASE_COST['redis'] * factor).quantize(Decimal('0.01')),
            risk_level='warning' if environment.environment_type == 'prod' else 'normal',
            tags={'role': 'cache'},
            metadata={'hit_rate': 96.2},
        ),
    ]
    if provider in {'aliyun', 'aws'}:
        rows.append(
            _asset(
                f'{prefix}-artifacts',
                'oss',
                environment,
                region,
                zone,
                spec='标准存储 / 800GB',
                disk_gb=Decimal('800.0'),
                monthly_cost=(BASE_COST['oss'] * factor).quantize(Decimal('0.01')),
                tags={'role': 'artifact'},
            )
        )
    if provider in {'aliyun', 'huawei'}:
        rows.append(
            _asset(
                f'{prefix}-nat',
                'nat',
                environment,
                region,
                zone,
                spec='SNAT + DNAT',
                monthly_cost=(BASE_COST['nat'] * factor).quantize(Decimal('0.01')),
                tags={'role': 'egress'},
            )
        )
        rows.append(
            _asset(
                f'{prefix}-eip',
                'eip',
                environment,
                region,
                zone,
                public_ip=f'{public_prefix}.88.88',
                spec='独享带宽 20Mbps',
                monthly_cost=(BASE_COST['eip'] * factor).quantize(Decimal('0.01')),
                risk_level='warning' if environment.environment_type == 'prod' else 'normal',
                tags={'role': 'public-network'},
            )
        )
    return rows


def _summary(environment):
    assets = list(environment.assets.all())
    type_counter = Counter(asset.resource_type for asset in assets)
    risk_counter = Counter(asset.risk_level for asset in assets)
    status_counter = Counter(asset.status for asset in assets)
    total_cost = sum((asset.monthly_cost or Decimal('0')) for asset in assets)
    return {
        'asset_count': len(assets),
        'monthly_cost': float(total_cost),
        'resource_breakdown': [{'type': key, 'count': value} for key, value in sorted(type_counter.items())],
        'risk_breakdown': [{'level': key, 'count': value} for key, value in sorted(risk_counter.items())],
        'status_breakdown': [{'status': key, 'count': value} for key, value in sorted(status_counter.items())],
    }


def _inventory_for_environment(environment):
    if _is_demo_credential(environment.credential):
        raise CloudAdapterError(DEMO_MODE_DISABLED_MESSAGE)

    adapter = get_cloud_adapter(environment.credential)
    if not adapter:
        raise CloudAdapterError(f'No SDK adapter configured for provider {environment.credential.provider}.')

    rows = adapter.fetch_inventory(environment)
    if not rows:
        raise CloudAdapterError(f'{provider_label(environment.credential.provider)} SDK returned no inventory data.')

    return rows, {
        'sync_mode': 'sdk',
        'source': adapter.capability(),
    }


def sync_environment_inventory(environment, operator='', task_type='full'):
    now = timezone.now()
    task = CloudSyncTask.objects.create(
        credential=environment.credential,
        environment=environment,
        task_type=task_type,
        status='running',
        operator=operator or 'system',
        started_at=now,
        summary=f'Start syncing environment {environment.name}',
    )
    environment.sync_status = 'running'
    environment.save(update_fields=['sync_status', 'updated_at'])

    try:
        desired, sync_meta = _inventory_for_environment(environment)
        active_keys = {(item['resource_type'], item['resource_id']) for item in desired}
        for item in desired:
            CloudAsset.objects.update_or_create(
                environment=environment,
                resource_type=item['resource_type'],
                resource_id=item['resource_id'],
                defaults={**item, 'provider': environment.credential.provider, 'synced_at': now},
            )
        for stale in list(environment.assets.all()):
            if (stale.resource_type, stale.resource_id) not in active_keys:
                stale.delete()

        summary = _summary(environment)
        risks = {item['level']: item['count'] for item in summary['risk_breakdown']}
        environment.summary = {
            **summary,
            'provider': environment.credential.provider,
            'provider_label': environment.credential.get_provider_display(),
            'account_name': environment.credential.name,
            **sync_meta,
        }
        environment.status = 'warning' if risks.get('critical') or risks.get('warning') else 'active'
        environment.sync_status = 'success'
        environment.last_sync_at = now
        environment.save(update_fields=['summary', 'status', 'sync_status', 'last_sync_at', 'updated_at'])
        environment.credential.last_sync_at = now
        environment.credential.save(update_fields=['last_sync_at', 'updated_at'])

        task.status = 'success'
        task.summary = f'Synced {summary["asset_count"]} resources for {environment.name}'
        task.result = {
            **summary,
            'environment': environment.name,
            'provider': environment.credential.provider,
            'demo_mode': environment.credential.demo_mode,
            **sync_meta,
        }
        task.finished_at = timezone.now()
        task.save(update_fields=['status', 'summary', 'result', 'finished_at'])
        return task
    except Exception as exc:
        environment.sync_status = 'failed'
        environment.save(update_fields=['sync_status', 'updated_at'])
        task.status = 'failed'
        task.summary = f'Environment sync failed: {environment.name}'
        task.result = {
            'environment': environment.name,
            'provider': environment.credential.provider,
            'demo_mode': environment.credential.demo_mode,
            'error': str(exc),
        }
        task.finished_at = timezone.now()
        task.save(update_fields=['status', 'summary', 'result', 'finished_at'])
        return task


def sync_credential_environments(credential, operator=''):
    environments = list(credential.environments.all())
    if not environments:
        environments = [_ensure_default_environment(credential, operator=operator)]
    tasks = [sync_environment_inventory(environment, operator=operator, task_type='inventory') for environment in environments]
    success_count = sum(1 for task in tasks if task.status == 'success')
    return {
        'credential': credential.name,
        'count': len(tasks),
        'success_count': success_count,
        'message': (
            f'Finished {success_count}/{len(tasks)} environment sync tasks.'
            if tasks
            else 'No environments found for this credential.'
        ),
        'tasks': [task.id for task in tasks],
    }


def _slug(value):
    text = re.sub(r'[^a-zA-Z0-9-]+', '-', str(value or '').strip().lower()).strip('-')
    return text or 'default'


def _unique_environment_code(base):
    base = _slug(base)[:50]
    code = base
    index = 1
    while CloudEnvironment.objects.filter(code=code).exists():
        suffix = f'-{index}'
        code = f'{base[:64 - len(suffix)]}{suffix}'
        index += 1
    return code


def _ensure_default_environment(credential, operator=''):
    provider_meta = PROVIDER_CATALOG.get(credential.provider, {})
    region = (
        credential.default_region
        or (credential.account_id if credential.provider == 'vsphere' else '')
        or provider_meta.get('default_region')
        or 'default'
    )
    name = f'{credential.name}-默认环境'
    code = _unique_environment_code(f'{credential.provider}-{credential.id or credential.name}-default')
    return CloudEnvironment.objects.create(
        credential=credential,
        name=name,
        code=code,
        business_line=(credential.tags or {}).get('business_line', ''),
        environment_type='prod',
        region=region,
        zone='',
        vpc_name='private-cloud' if credential.provider == 'vsphere' else '',
        network_cidr='',
        owner=credential.owner,
        description='账号接入后自动创建的默认同步环境',
        tags={'auto_created': True, 'created_by': operator or 'system'},
        created_by=operator or 'system',
        updated_by=operator or 'system',
    )


def build_recommendations(limit=8):
    rows = []
    for asset in CloudAsset.objects.select_related('environment').all():
        if asset.sync_state == 'idle' and asset.monthly_cost >= Decimal('180'):
            rows.append(
                {
                    'type': 'cost',
                    'severity': 'warning',
                    'title': f'低利用率资源可降配: {asset.name}',
                    'detail': f'{asset.environment.name} 中该资源月成本 {asset.monthly_cost} 元，建议定时启停或降配。',
                    'provider': asset.provider,
                    'environment': asset.environment.name,
                    'monthly_cost': float(asset.monthly_cost),
                }
            )
        if asset.risk_level == 'critical':
            rows.append(
                {
                    'type': 'security',
                    'severity': 'danger',
                    'title': f'高危暴露项待处理: {asset.name}',
                    'detail': f'{asset.environment.name} 存在高危配置，建议优先治理公网暴露与证书有效期。',
                    'provider': asset.provider,
                    'environment': asset.environment.name,
                    'monthly_cost': float(asset.monthly_cost),
                }
            )
        if asset.sync_state == 'drift':
            rows.append(
                {
                    'type': 'governance',
                    'severity': 'info',
                    'title': f'配置漂移待纳管: {asset.name}',
                    'detail': f'{asset.environment.name} 中 {asset.resource_type} 存在漂移，建议回收 IaC / CMDB 基线。',
                    'provider': asset.provider,
                    'environment': asset.environment.name,
                    'monthly_cost': float(asset.monthly_cost),
                }
            )
    rank = {'danger': 3, 'warning': 2, 'info': 1}
    rows.sort(key=lambda item: (rank.get(item['severity'], 0), item['monthly_cost']), reverse=True)
    return rows[:limit]


def build_cost_trend(provider='', environment_id=None, resource_type='', group_by='provider'):
    assets = CloudAsset.objects.select_related('environment', 'environment__credential').all()
    if provider:
        assets = assets.filter(provider=provider)
    if environment_id:
        assets = assets.filter(environment_id=environment_id)
    if resource_type:
        assets = assets.filter(resource_type=resource_type)

    labels = []
    factors = [Decimal('0.86'), Decimal('0.90'), Decimal('0.93'), Decimal('0.97'), Decimal('1.02'), Decimal('1.00')]
    now = timezone.now()
    for offset in range(5, -1, -1):
        current = (now.replace(day=1) - timedelta(days=offset * 31)).replace(day=1)
        labels.append(current.strftime('%Y-%m'))

    groups = defaultdict(Decimal)
    for asset in assets:
        if group_by == 'resource_type':
            key = asset.resource_type
            label = resource_type_label(asset.resource_type)
        elif group_by == 'environment':
            key = str(asset.environment_id)
            label = asset.environment.name
        else:
            key = asset.provider
            label = provider_label(asset.provider)
        groups[(key, label)] += asset.monthly_cost or Decimal('0')

    series = []
    for (key, label), current_total in groups.items():
        values = [float((current_total * factor).quantize(Decimal('0.01'))) for factor in factors]
        series.append({'key': key, 'label': label, 'values': values})
    series.sort(key=lambda item: sum(item['values']), reverse=True)

    return {
        'labels': labels,
        'series': series[:8],
        'group_by': group_by,
        'filters': {
            'provider': provider,
            'environment_id': environment_id,
            'resource_type': resource_type,
        },
        'total': float(sum((asset.monthly_cost or Decimal('0')) for asset in assets)),
    }


def build_region_summary():
    rows = []
    grouped = defaultdict(lambda: {'assets': 0, 'monthly_cost': Decimal('0'), 'risk_count': 0})
    for asset in CloudAsset.objects.select_related('environment').all():
        key = (asset.provider, asset.region or '-')
        grouped[key]['assets'] += 1
        grouped[key]['monthly_cost'] += asset.monthly_cost or Decimal('0')
        if asset.risk_level in {'warning', 'critical'}:
            grouped[key]['risk_count'] += 1
    for (provider, region), item in grouped.items():
        rows.append(
            {
                'provider': provider,
                'provider_label': provider_label(provider),
                'region': region,
                'assets': item['assets'],
                'risk_count': item['risk_count'],
                'monthly_cost': float(item['monthly_cost']),
            }
        )
    rows.sort(key=lambda row: row['monthly_cost'], reverse=True)
    return rows[:12]


def build_risk_matrix():
    rows = []
    for resource_type, count in Counter(CloudAsset.objects.values_list('resource_type', flat=True)).items():
        risk_assets = CloudAsset.objects.filter(resource_type=resource_type, risk_level__in=['warning', 'critical'])
        rows.append(
            {
                'resource_type': resource_type,
                'resource_type_label': resource_type_label(resource_type),
                'total_count': count,
                'risk_count': risk_assets.count(),
                'critical_count': risk_assets.filter(risk_level='critical').count(),
                'monthly_cost': float(sum((asset.monthly_cost or Decimal('0')) for asset in CloudAsset.objects.filter(resource_type=resource_type))),
            }
        )
    rows.sort(key=lambda row: (row['critical_count'], row['risk_count'], row['monthly_cost']), reverse=True)
    return rows


def build_topology(environment_id=None, provider=''):
    credentials = CloudCredential.objects.prefetch_related('environments__assets').all()
    if provider:
        credentials = credentials.filter(provider=provider)

    selected_environment_id = int(environment_id) if str(environment_id or '').isdigit() else None
    nodes = []
    edges = []
    node_ids = set()
    edge_ids = set()
    category_map = {
        'credential': 0,
        'environment': 1,
        'compute': 2,
        'data': 3,
        'network': 4,
    }

    def push_node(node_id, name, category, **extra):
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        nodes.append({'id': node_id, 'name': name, 'category': category_map[category], **extra})

    def push_edge(source, target, value=''):
        edge_key = (source, target, value)
        if edge_key in edge_ids:
            return
        edge_ids.add(edge_key)
        edges.append({'source': source, 'target': target, 'value': value})

    for credential in credentials:
        envs = credential.environments.all()
        if selected_environment_id:
            envs = envs.filter(id=selected_environment_id)
        envs = list(envs)
        if not envs:
            continue

        credential_node_id = f'credential-{credential.id}'
        push_node(
            credential_node_id,
            credential.name,
            'credential',
            provider=credential.provider,
            provider_label=credential.get_provider_display(),
            value=len(envs),
            symbolSize=60,
        )

        for environment in envs:
            env_assets = list(environment.assets.all())
            env_node_id = f'environment-{environment.id}'
            push_node(
                env_node_id,
                environment.name,
                'environment',
                provider=credential.provider,
                provider_label=credential.get_provider_display(),
                business_line=environment.business_line,
                value=len(env_assets),
                risk_count=sum(1 for asset in env_assets if asset.risk_level in {'warning', 'critical'}),
                symbolSize=52,
            )
            push_edge(credential_node_id, env_node_id, '账号归属')

            bucket_nodes = {}
            for bucket, types in {'compute': {'ecs', 'k8s'}, 'data': {'rds', 'redis', 'oss'}, 'network': {'slb', 'nat', 'eip', 'security_group'}}.items():
                items = [asset for asset in env_assets if asset.resource_type in types]
                if not items:
                    continue
                bucket_id = f'{bucket}-{environment.id}'
                bucket_nodes[bucket] = bucket_id
                push_node(
                    bucket_id,
                    f'{environment.name}-{bucket}',
                    bucket,
                    provider=credential.provider,
                    value=len(items),
                    monthly_cost=float(sum((item.monthly_cost or Decimal('0')) for item in items)),
                    symbolSize=min(56, 24 + len(items) * 4),
                )
                push_edge(env_node_id, bucket_id, f'{len(items)} resources')

            assets_by_type = defaultdict(list)
            for asset in env_assets:
                assets_by_type[asset.resource_type].append(asset)
                category = 'compute' if asset.resource_type in {'ecs', 'k8s'} else 'data' if asset.resource_type in {'rds', 'redis', 'oss'} else 'network'
                asset_node_id = f'asset-{asset.id}'
                push_node(
                    asset_node_id,
                    asset.name,
                    category,
                    provider=asset.provider,
                    resource_type=asset.resource_type,
                    resource_type_label=asset.get_resource_type_display(),
                    risk_level=asset.risk_level,
                    value=float(asset.monthly_cost or 0),
                    symbolSize=28 if asset.risk_level == 'critical' else 22,
                    metadata=asset.metadata or {},
                )
                push_edge(bucket_nodes.get(category, env_node_id), asset_node_id, asset.get_resource_type_display())

            for source_type, target_types in RESOURCE_LINKS.items():
                for source_asset in assets_by_type.get(source_type, []):
                    for target_type in target_types:
                        target_asset = next(iter(assets_by_type.get(target_type, [])), None)
                        if target_asset:
                            push_edge(
                                f'asset-{source_asset.id}',
                                f'asset-{target_asset.id}',
                                f'{resource_type_label(source_type)} -> {resource_type_label(target_type)}',
                            )

    return {
        'categories': [
            {'name': '云账号'},
            {'name': '环境'},
            {'name': '计算层'},
            {'name': '数据层'},
            {'name': '网络层'},
        ],
        'nodes': nodes,
        'edges': edges,
        'stats': {
            'node_count': len(nodes),
            'edge_count': len(edges),
            'provider_count': len({node.get('provider') for node in nodes if node.get('provider')}),
        },
    }


def batch_sync_targets(environment_ids=None, credential_ids=None, operator='', sync_cmdb=False):
    results = []
    seen_ids = set()
    for environment in CloudEnvironment.objects.filter(id__in=(environment_ids or [])).select_related('credential'):
        seen_ids.add(environment.id)
        task = sync_environment_to_cmdb(environment, operator=operator) if sync_cmdb else sync_environment_inventory(environment, operator=operator, task_type='inventory')
        results.append(
            {
                'environment_id': environment.id,
                'environment_name': environment.name,
                'task_id': task.id,
                'status': task.status,
                'summary': task.summary,
            }
        )
    if credential_ids:
        credentials = CloudCredential.objects.filter(id__in=credential_ids).prefetch_related('environments')
        for credential in credentials:
            for environment in credential.environments.all():
                if environment.id in seen_ids:
                    continue
                task = sync_environment_to_cmdb(environment, operator=operator) if sync_cmdb else sync_environment_inventory(environment, operator=operator, task_type='inventory')
                results.append(
                    {
                        'environment_id': environment.id,
                        'environment_name': environment.name,
                        'task_id': task.id,
                        'status': task.status,
                        'summary': task.summary,
                    }
                )
                seen_ids.add(environment.id)
    return results


def execute_batch_action(scope, action, ids=None, operator='', payload=None):
    ids = [item for item in (ids or []) if item]
    payload = payload or {}
    results = []

    if scope == 'credentials':
        queryset = CloudCredential.objects.filter(id__in=ids)
        for credential in queryset:
            if action == 'test_connection':
                result = test_credential_connection(credential)
                results.append({'id': credential.id, 'name': credential.name, 'status': result['status'], 'detail': result['message']})
            elif action in {'enable', 'disable'}:
                credential.is_enabled = action == 'enable'
                credential.updated_by = operator or credential.updated_by
                credential.save(update_fields=['is_enabled', 'updated_by', 'updated_at'])
                results.append({'id': credential.id, 'name': credential.name, 'status': 'success', 'detail': f'Credential {action}d'})
            elif action in {'demo_on', 'demo_off'}:
                results.append({'id': credential.id, 'name': credential.name, 'status': 'failed', 'detail': DEMO_MODE_DISABLED_MESSAGE})
            else:
                raise ValueError(f'Unsupported credential batch action: {action}')

    elif scope == 'environments':
        queryset = CloudEnvironment.objects.filter(id__in=ids).select_related('credential')
        for environment in queryset:
            if action == 'sync_inventory':
                task = sync_environment_inventory(environment, operator=operator, task_type='inventory')
                results.append({'id': environment.id, 'name': environment.name, 'status': task.status, 'detail': task.summary, 'task_id': task.id})
            elif action == 'sync_cmdb':
                task = sync_environment_to_cmdb(environment, operator=operator)
                results.append({'id': environment.id, 'name': environment.name, 'status': task.status, 'detail': task.summary, 'task_id': task.id})
            elif action == 'mark_offline':
                environment.status = 'offline'
                environment.updated_by = operator or environment.updated_by
                environment.save(update_fields=['status', 'updated_by', 'updated_at'])
                results.append({'id': environment.id, 'name': environment.name, 'status': 'success', 'detail': 'Environment marked offline'})
            elif action == 'mark_active':
                environment.status = 'active'
                environment.updated_by = operator or environment.updated_by
                environment.save(update_fields=['status', 'updated_by', 'updated_at'])
                results.append({'id': environment.id, 'name': environment.name, 'status': 'success', 'detail': 'Environment marked active'})
            else:
                raise ValueError(f'Unsupported environment batch action: {action}')

    elif scope == 'assets':
        queryset = CloudAsset.objects.filter(id__in=ids)
        for asset in queryset:
            if action == 'set_warning':
                asset.risk_level = 'warning'
                asset.sync_state = payload.get('sync_state', asset.sync_state)
                asset.save(update_fields=['risk_level', 'sync_state', 'updated_at'])
                results.append({'id': asset.id, 'name': asset.name, 'status': 'success', 'detail': 'Asset risk level set to warning'})
            elif action == 'set_normal':
                asset.risk_level = 'normal'
                asset.sync_state = payload.get('sync_state', asset.sync_state)
                asset.save(update_fields=['risk_level', 'sync_state', 'updated_at'])
                results.append({'id': asset.id, 'name': asset.name, 'status': 'success', 'detail': 'Asset risk level restored to normal'})
            elif action == 'mark_drift':
                asset.sync_state = 'drift'
                asset.save(update_fields=['sync_state', 'updated_at'])
                results.append({'id': asset.id, 'name': asset.name, 'status': 'success', 'detail': 'Asset marked as drift'})
            elif action == 'mark_synced':
                asset.sync_state = 'synced'
                asset.save(update_fields=['sync_state', 'updated_at'])
                results.append({'id': asset.id, 'name': asset.name, 'status': 'success', 'detail': 'Asset marked as synced'})
            else:
                raise ValueError(f'Unsupported asset batch action: {action}')
    else:
        raise ValueError(f'Unsupported batch action scope: {scope}')

    return {
        'scope': scope,
        'action': action,
        'count': len(results),
        'results': results,
        'message': f'Batch action finished for {len(results)} {scope}.',
    }


def build_overview():
    credentials = list(CloudCredential.objects.prefetch_related('environments__assets'))
    assets = list(CloudAsset.objects.select_related('environment', 'environment__credential'))
    provider_stats = defaultdict(lambda: {'credentials': 0, 'environments': 0, 'assets': 0, 'monthly_cost': Decimal('0'), 'risk_count': 0})
    for credential in credentials:
        provider_stats[credential.provider]['credentials'] += 1
        provider_stats[credential.provider]['environments'] += credential.environments.count()
    for asset in assets:
        stat = provider_stats[asset.provider]
        stat['assets'] += 1
        stat['monthly_cost'] += asset.monthly_cost or Decimal('0')
        if asset.risk_level in {'warning', 'critical'}:
            stat['risk_count'] += 1

    provider_summary = [
        {
            'provider': key,
            'provider_label': provider_label(key),
            'credentials': value['credentials'],
            'environments': value['environments'],
            'assets': value['assets'],
            'monthly_cost': float(value['monthly_cost']),
            'risk_count': value['risk_count'],
        }
        for key, value in provider_stats.items()
    ]
    provider_summary.sort(key=lambda item: item['monthly_cost'], reverse=True)

    environment_costs = []
    for credential in credentials:
        for environment in credential.environments.all():
            monthly_cost = sum((asset.monthly_cost or Decimal('0')) for asset in environment.assets.all())
            environment_costs.append(
                {
                    'id': environment.id,
                    'name': environment.name,
                    'provider': credential.provider,
                    'provider_label': credential.get_provider_display(),
                    'environment_type': environment.environment_type,
                    'business_line': environment.business_line,
                    'asset_count': environment.assets.count(),
                    'monthly_cost': float(monthly_cost),
                    'risk_count': environment.assets.filter(risk_level__in=['warning', 'critical']).count(),
                    'sync_status': environment.sync_status,
                    'last_sync_at': environment.last_sync_at,
                }
            )
    environment_costs.sort(key=lambda item: item['monthly_cost'], reverse=True)

    top_assets = sorted(
        [
            {
                'id': asset.id,
                'name': asset.name,
                'provider': asset.provider,
                'provider_label': asset.environment.credential.get_provider_display(),
                'environment': asset.environment.name,
                'resource_type': asset.resource_type,
                'resource_type_label': asset.get_resource_type_display(),
                'monthly_cost': float(asset.monthly_cost),
                'status': asset.status,
                'risk_level': asset.risk_level,
            }
            for asset in assets
        ],
        key=lambda item: item['monthly_cost'],
        reverse=True,
    )[:10]

    resource_breakdown = Counter(asset.resource_type for asset in assets)
    risk_breakdown = Counter(asset.risk_level for asset in assets)
    tasks = CloudSyncTask.objects.select_related('credential', 'environment')[:10]

    return {
        'stats': {
            'credential_count': len(credentials),
            'environment_count': sum(item['environments'] for item in provider_summary),
            'asset_count': len(assets),
            'monthly_cost': float(sum((asset.monthly_cost or Decimal('0')) for asset in assets)),
            'risk_count': sum(1 for asset in assets if asset.risk_level in {'warning', 'critical'}),
        },
        'provider_summary': provider_summary,
        'resource_breakdown': [{'type': key, 'count': value} for key, value in sorted(resource_breakdown.items())],
        'risk_breakdown': [{'level': key, 'count': value} for key, value in sorted(risk_breakdown.items())],
        'environment_costs': environment_costs[:12],
        'cost_trend': build_cost_trend(),
        'region_summary': build_region_summary(),
        'risk_matrix': build_risk_matrix(),
        'top_assets': top_assets,
        'recent_tasks': [
            {
                'id': task.id,
                'task_type': task.task_type,
                'task_type_label': task.get_task_type_display(),
                'status': task.status,
                'summary': task.summary,
                'operator': task.operator,
                'target': task.target_display,
                'created_at': task.created_at,
                'finished_at': task.finished_at,
            }
            for task in tasks
        ],
        'recommendations': build_recommendations(),
    }


def sync_environment_to_cmdb(environment, operator=''):
    now = timezone.now()
    task = CloudSyncTask.objects.create(
        credential=environment.credential,
        environment=environment,
        task_type='cmdb',
        status='running',
        operator=operator or 'system',
        started_at=now,
        summary=f'Sync {environment.name} to CMDB',
    )
    if _is_demo_credential(environment.credential):
        task.status = 'failed'
        task.summary = f'CMDB sync failed: {environment.name}'
        task.result = {
            'environment': environment.name,
            'provider': environment.credential.provider,
            'demo_mode': bool(getattr(environment.credential, 'demo_mode', False)),
            'error': DEMO_MODE_DISABLED_MESSAGE,
        }
        task.finished_at = now
        task.save(update_fields=['status', 'summary', 'result', 'finished_at'])
        return task
    asset_qs = environment.assets.all()
    if not asset_qs.exists():
        sync_environment_inventory(environment, operator=operator or 'system', task_type='inventory')
        asset_qs = environment.assets.all()

    current_month = timezone.now().strftime('%Y-%m')
    created_count = 0
    updated_count = 0
    for asset in asset_qs:
        ci_type = _get_or_create_cmdb_type(_cmdb_type_meta_for_asset(asset))
        defaults = {
            'business_line': environment.business_line,
            'environment': environment.environment_type if environment.environment_type in {'prod', 'test', 'dev'} else 'test',
            'admin_user': environment.owner,
            'status': {
                'running': 'active',
                'stopped': 'idle',
                'degraded': 'idle',
                'error': 'offline',
            }.get(asset.status, 'active'),
            'attributes': {
                'provider': asset.provider,
                'cloud_provider': asset.provider,
                'account_name': environment.credential.name,
                'account_id': environment.credential.account_id,
                'resource_type': asset.resource_type,
                'resource_id': asset.resource_id,
                'region': asset.region,
                'zone': asset.zone,
                'vpc_name': asset.vpc_name,
                'public_ip': asset.public_ip,
                'private_ip': asset.private_ip,
                'ip_address': asset.private_ip or asset.public_ip or '',
                'monthly_cost': float(asset.monthly_cost or 0),
                'cpu': asset.cpu,
                'memory_gb': float(asset.memory_gb or 0),
                'disk_gb': float(asset.disk_gb or 0),
                'risk_level': asset.risk_level,
                'sync_state': asset.sync_state,
                'cloud_env_code': environment.code,
                'cmdb_source': 'multicloud',
                **(asset.metadata or {}),
            },
        }
        ci = _find_existing_cmdb_item_for_asset(asset, ci_type)
        if ci:
            created = False
            ci.name = asset.name
            ci.ci_type = ci_type
            for field, value in defaults.items():
                setattr(ci, field, value)
            ci.save()
        else:
            ci, created = ConfigItem.objects.update_or_create(
                name=asset.name,
                ci_type=ci_type,
                defaults=defaults,
            )
        created_count += int(created)
        updated_count += int(not created)
        CostRecord.objects.update_or_create(
            ci=ci,
            month=current_month,
            defaults={'amount': asset.monthly_cost or Decimal('0'), 'provider': provider_label(asset.provider)},
        )

    environment.last_cmdb_sync_at = timezone.now()
    environment.save(update_fields=['last_cmdb_sync_at', 'updated_at'])
    task.status = 'success'
    task.summary = f'CMDB updated with {asset_qs.count()} resources'
    task.result = {
        'created_count': created_count,
        'updated_count': updated_count,
        'asset_count': asset_qs.count(),
        'environment': environment.name,
    }
    task.finished_at = timezone.now()
    task.save(update_fields=['status', 'summary', 'result', 'finished_at'])
    return task
