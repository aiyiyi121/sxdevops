from django.db import migrations


SERVICE_TYPE_CODES = ('DW', 'NIFI')


def update_dw_nifi_model_fields(apps, schema_editor):
    CIType = apps.get_model('cmdb', 'CIType')
    CIField = apps.get_model('cmdb', 'CIField')

    for ci_type in CIType.objects.filter(code__in=SERVICE_TYPE_CODES):
        CIField.objects.filter(ci_type=ci_type, code='deployment_ips').delete()
        CIField.objects.update_or_create(
            ci_type=ci_type,
            code='deployment_mode',
            defaults={
                'name': '部署方式',
                'field_type': 'enum',
                'field_group': '部署信息',
                'required': False,
                'unique': False,
                'default': None,
                'options': [
                    {'value': 'vm', 'label': '虚拟机'},
                    {'value': 'k8s', 'label': 'K8s 集群'},
                ],
                'validation': {},
                'sync_mode': 'source',
                'is_builtin': False,
                'is_display': True,
                'is_searchable': True,
                'is_sensitive': False,
                'is_active': True,
                'sort_order': 10,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('cmdb', '0039_clear_unassigned_default_environment'),
    ]

    operations = [
        migrations.RunPython(update_dw_nifi_model_fields, migrations.RunPython.noop),
    ]
