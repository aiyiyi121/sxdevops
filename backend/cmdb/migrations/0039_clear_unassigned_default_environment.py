from django.db import migrations


def clear_unassigned_default_environment(apps, schema_editor):
    ConfigItem = apps.get_model('cmdb', 'ConfigItem')
    ConfigItem.objects.filter(
        environment='prod',
        environment_node__isnull=True,
    ).filter(
        business_line='',
    ).update(environment='')


class Migration(migrations.Migration):
    dependencies = [
        ('cmdb', '0038_configitem_stop_lifecycle_status'),
    ]

    operations = [
        migrations.RunPython(clear_unassigned_default_environment, migrations.RunPython.noop),
    ]
