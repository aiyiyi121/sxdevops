from django.db import migrations


def enable_observability_menu(apps, schema_editor):
    setting_model = apps.get_model('rbac', 'SystemModuleSetting')
    setting_model.objects.filter(code='observability').update(enabled=True)


class Migration(migrations.Migration):

    dependencies = [
        ('rbac', '0002_system_module_setting'),
    ]

    operations = [
        migrations.RunPython(enable_observability_menu, migrations.RunPython.noop),
    ]
