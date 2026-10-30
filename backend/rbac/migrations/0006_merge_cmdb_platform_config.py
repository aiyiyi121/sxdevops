from django.db import migrations


def merge_cmdb_platform_config(apps, schema_editor):
    setting_model = apps.get_model('rbac', 'SystemModuleSetting')
    settings = setting_model.objects.using(schema_editor.connection.alias)
    legacy_settings = settings.filter(code__in=['cmdb.sync', 'cmdb.model-config', 'cmdb.ipam'])
    enabled = legacy_settings.filter(enabled=True).exists() if legacy_settings.exists() else True
    was_default = legacy_settings.filter(is_default=True).exists()
    legacy_settings.filter(is_default=True).update(is_default=False)
    combined, _ = settings.get_or_create(code='cmdb.platform-config', defaults={'enabled': enabled})
    if was_default:
        combined.is_default = True
        combined.save(using=schema_editor.connection.alias, update_fields=['is_default'])


class Migration(migrations.Migration):
    dependencies = [
        ('rbac', '0005_systemmodulesetting_single_default'),
    ]

    operations = [
        migrations.RunPython(merge_cmdb_platform_config, migrations.RunPython.noop),
    ]
