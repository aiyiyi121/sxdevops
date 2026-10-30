from django.db import migrations


SERVICE_TYPE_DEFINITIONS = [
    ('REDIS', 'Redis', 'middleware', 'Collection', '#ef4444'),
    ('K8S_CLUSTER', 'K8s 集群', 'compute', 'Cluster', '#0ea5e9'),
    ('APISIX', 'APISIX', 'middleware', 'Connection', '#2563eb'),
    ('NACOS', 'Nacos', 'middleware', 'Setting', '#0ea5e9'),
    ('SKYWALKING', 'SkyWalking', 'middleware', 'DataLine', '#8b5cf6'),
    ('ELK', 'ELK', 'middleware', 'DataAnalysis', '#eab308'),
    ('POSTGRESQL', 'PostgreSQL', 'database', 'Coin', '#2563eb'),
    ('KAFKA', 'Kafka', 'middleware', 'MessageBox', '#7c3aed'),
    ('ELASTICSEARCH', 'Elasticsearch', 'middleware', 'Search', '#10b981'),
    ('DW', 'DW', 'bigdata', 'DataAnalysis', '#7c3aed'),
    ('EMQX', 'EMQX', 'middleware', 'Connection', '#06b6d4'),
    ('ROCKETMQ', 'RocketMQ', 'middleware', 'MessageBox', '#f97316'),
    ('ZOOKEEPER', 'ZooKeeper', 'middleware', 'Operation', '#16a34a'),
    ('NIFI', 'NiFi', 'bigdata', 'DataAnalysis', '#7c3aed'),
]


def ensure_service_types(CIModelGroup, CIType):
    groups = {
        group.code: group
        for group in CIModelGroup.objects.filter(
            code__in={'compute', 'database', 'middleware', 'bigdata'},
        )
    }
    for code, name, group_code, icon, color in SERVICE_TYPE_DEFINITIONS:
        ci_type = CIType.objects.filter(code=code).first()
        if ci_type is None:
            ci_type = CIType.objects.filter(name=name).first()
        if ci_type is None:
            ci_type = CIType.objects.create(
                code=code,
                name=name,
                group=groups.get(group_code),
                icon=icon,
                color=color,
                description=f'{name} 服务资产。',
                is_builtin=False,
                is_active=True,
            )
        elif ci_type.code != code:
            ci_type.code = code
            ci_type.save(update_fields=['code', 'updated_at'])
        group = groups.get(group_code)
        if group and ci_type.group_id != group.id:
            ci_type.group = group
            ci_type.save(update_fields=['group', 'updated_at'])


def ensure_dw_and_nifi_fields(CIModelGroup, CIType, CIField):
    group = CIModelGroup.objects.filter(code='bigdata').first()
    for code, name in (('DW', 'DW'), ('NIFI', 'NiFi')):
        ci_type, _ = CIType.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'icon': 'DataAnalysis',
                'color': '#7c3aed',
                'description': f'{name} 服务资产。',
                'is_builtin': False,
                'is_active': True,
            },
        )
        if group and ci_type.group_id != group.id:
            ci_type.group = group
            ci_type.save(update_fields=['group', 'updated_at'])
        CIField.objects.filter(ci_type=ci_type, code='deployment_ips').delete()
        CIField.objects.update_or_create(
            ci_type=ci_type,
            code='deployment_mode',
            defaults={
                'name': '部署方式',
                'field_type': 'enum',
                'field_group': '部署信息',
                'options': [
                    {'value': '虚拟机', 'label': '虚拟机'},
                    {'value': 'K8s 集群', 'label': 'K8s 集群'},
                ],
                'is_active': True,
                'is_display': True,
                'is_searchable': True,
                'sort_order': 10,
            },
        )
        CIField.objects.update_or_create(
            ci_type=ci_type,
            code='instance_count',
            defaults={
                'name': '实例数量',
                'field_type': 'integer',
                'field_group': '部署信息',
                'is_active': True,
                'is_display': True,
                'sort_order': 20,
            },
        )


def sync_we_dev_service_inventory(apps, schema_editor):
    CIModelGroup = apps.get_model('cmdb', 'CIModelGroup')
    CIType = apps.get_model('cmdb', 'CIType')
    CIField = apps.get_model('cmdb', 'CIField')
    ensure_service_types(CIModelGroup, CIType)
    ensure_dw_and_nifi_fields(CIModelGroup, CIType, CIField)


class Migration(migrations.Migration):
    dependencies = [
        ('cmdb', '0040_update_dw_nifi_model_fields'),
    ]

    operations = [
        migrations.RunPython(sync_we_dev_service_inventory, migrations.RunPython.noop),
    ]
