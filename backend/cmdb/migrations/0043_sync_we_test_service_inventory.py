from django.db import migrations


def ensure_k8s_access_address_field(CIType, CIField):
    ci_type = CIType.objects.filter(code='K8S_CLUSTER').first()
    if ci_type is None:
        return
    CIField.objects.update_or_create(
        ci_type=ci_type,
        code='access_address',
        defaults={
            'name': '访问地址',
            'field_type': 'url',
            'field_group': '访问入口',
            'required': False,
            'unique': False,
            'default': None,
            'options': [],
            'validation': {},
            'sync_mode': 'source',
            'is_builtin': False,
            'is_display': True,
            'is_searchable': True,
            'is_sensitive': False,
            'is_active': True,
            'sort_order': 880,
        },
    )


def sync_we_test_service_inventory(apps, schema_editor):
    CIType = apps.get_model('cmdb', 'CIType')
    CIField = apps.get_model('cmdb', 'CIField')
    ensure_k8s_access_address_field(CIType, CIField)


class Migration(migrations.Migration):
    dependencies = [
        ('cmdb', '0042_optimize_service_model_fields'),
    ]

    operations = [
        migrations.RunPython(sync_we_test_service_inventory, migrations.RunPython.noop),
    ]
