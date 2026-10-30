from django.db import migrations


def rename_external_group(apps, schema_editor):
    CIModelGroup = apps.get_model('cmdb', 'CIModelGroup')
    CIModelGroup.objects.filter(code='external').update(name='其他资产')


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0019_rename_third_party_service_expiry_fields'),
    ]

    operations = [
        migrations.RunPython(rename_external_group, migrations.RunPython.noop),
    ]
