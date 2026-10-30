from django.db import migrations


def rename_legacy_access_address_fields(apps, schema_editor):
    field_model = apps.get_model('cmdb', 'CIField')
    field_model.objects.filter(is_builtin=True, name='访问地址').update(name='连接地址')


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0031_backfill_sync_record_batch_ids'),
    ]

    operations = [
        migrations.RunPython(rename_legacy_access_address_fields, migrations.RunPython.noop),
    ]
