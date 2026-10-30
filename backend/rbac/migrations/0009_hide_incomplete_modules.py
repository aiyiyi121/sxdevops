from django.db import migrations


def hide_incomplete_modules(apps, schema_editor):
    setting_model = apps.get_model('rbac', 'SystemModuleSetting')
    setting_model.objects.using(schema_editor.connection.alias).filter(
        code__in=['cmdb.requests', 'cmdb.thresholds', 'cmdb.views', 'observability.rum'],
    ).update(enabled=False, is_default=False)


class Migration(migrations.Migration):
    dependencies = [
        ('rbac', '0008_systemmodulesetting_sort_order'),
    ]

    operations = [
        migrations.RunPython(hide_incomplete_modules, migrations.RunPython.noop),
    ]
