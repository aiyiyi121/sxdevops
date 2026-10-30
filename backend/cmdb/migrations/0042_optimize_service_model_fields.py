from django.db import migrations


SERVICE_TYPE_DEFINITIONS = [
    {
        'code': 'DW',
        'name': 'DW',
        'group': 'bigdata',
        'icon': 'DataAnalysis',
        'color': '#7c3aed',
        'description': '数据仓库服务、计算与存储规模台账。',
        'fields': [
            {'code': 'instance_id', 'name': '实例 ID', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_group': '实例信息', 'sort_order': 30},
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
            {'code': 'cluster_id', 'name': '集群 ID', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_group': '实例信息', 'sort_order': 30},
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
            {'code': 'cluster_id', 'name': '集群 ID', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'version', 'name': '版本', 'field_group': '实例信息', 'sort_order': 30},
            {'code': 'deployment_mode', 'name': '部署方式', 'field_type': 'enum', 'field_group': '部署信息', 'options': [{'value': 'vm', 'label': '虚拟机'}, {'value': 'k8s', 'label': 'K8s 集群'}], 'sort_order': 40},
            {'code': 'instance_count', 'name': '实例数量', 'field_type': 'integer', 'field_group': '部署信息', 'sort_order': 50},
            {'code': 'worker_count', 'name': 'Worker 数量', 'field_type': 'integer', 'field_group': '资源规格', 'sort_order': 60},
            {'code': 'workflow_count', 'name': '工作流数量', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 70},
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
            {'code': 'cluster_id', 'name': '集群 ID', 'field_group': '实例信息', 'unique': True, 'is_searchable': True, 'sort_order': 10},
            {'code': 'endpoint', 'name': '连接地址', 'field_group': '连接信息', 'is_searchable': True, 'sort_order': 20},
            {'code': 'admin_endpoint', 'name': '管理地址', 'field_type': 'url', 'field_group': '连接信息', 'sort_order': 30},
            {'code': 'version', 'name': '版本', 'field_group': '实例信息', 'sort_order': 40},
            {'code': 'deployment_mode', 'name': '部署方式', 'field_type': 'enum', 'field_group': '部署信息', 'options': [{'value': 'vm', 'label': '虚拟机'}, {'value': 'k8s', 'label': 'K8s 集群'}], 'sort_order': 50},
            {'code': 'instance_count', 'name': '实例数量', 'field_type': 'integer', 'field_group': '部署信息', 'sort_order': 60},
            {'code': 'route_count', 'name': '路由数量', 'field_type': 'integer', 'field_group': '用量信息', 'sort_order': 70},
        ],
    },
]


def ensure_service_model_fields(apps, schema_editor):
    CIModelGroup = apps.get_model('cmdb', 'CIModelGroup')
    CIType = apps.get_model('cmdb', 'CIType')
    CIField = apps.get_model('cmdb', 'CIField')

    for definition in SERVICE_TYPE_DEFINITIONS:
        ci_type = CIType.objects.filter(code=definition['code']).first()
        if ci_type is None:
            ci_type = CIType.objects.filter(name=definition['name']).first()
        group = CIModelGroup.objects.filter(code=definition['group']).first()
        if ci_type is None:
            ci_type = CIType.objects.create(
                code=definition['code'],
                name=definition['name'],
                group=group,
                icon=definition['icon'],
                color=definition['color'],
                description=definition['description'],
                is_builtin=True,
                is_active=True,
            )
        else:
            ci_type.code = definition['code']
            ci_type.name = definition['name']
            ci_type.group = group
            ci_type.icon = definition['icon']
            ci_type.color = definition['color']
            ci_type.description = definition['description']
            ci_type.is_builtin = True
            ci_type.is_active = True
            ci_type.save()

        for field in definition['fields']:
            CIField.objects.update_or_create(
                ci_type=ci_type,
                code=field['code'],
                defaults={
                    'name': field['name'],
                    'field_type': field.get('field_type', 'string'),
                    'field_group': field['field_group'],
                    'required': False,
                    'unique': field.get('unique', False),
                    'default': None,
                    'options': field.get('options', []),
                    'validation': {},
                    'sync_mode': 'source',
                    'is_builtin': True,
                    'is_display': True,
                    'is_searchable': field.get('is_searchable', False),
                    'is_sensitive': False,
                    'is_active': True,
                    'sort_order': field['sort_order'],
                },
            )

    CIField.objects.filter(ci_type__code__in=('DW', 'NIFI'), code='deployment_ips').delete()
    CIField.objects.filter(ci_type__code__in=('DATAWORKS', 'HOLOGRES'), code='region').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('cmdb', '0041_sync_we_dev_service_inventory'),
    ]

    operations = [
        migrations.RunPython(ensure_service_model_fields, migrations.RunPython.noop),
    ]
