from django.db import migrations, models


def convert_idle_statuses_to_stopped(apps, schema_editor):
    ConfigItem = apps.get_model('cmdb', 'ConfigItem')
    ConfigItem.objects.filter(status='idle').update(status='stopped')


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0037_resource_request_cloud_provisioning'),
    ]

    operations = [
        migrations.RunPython(convert_idle_statuses_to_stopped, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='configitem',
            name='status',
            field=models.CharField(
                choices=[
                    ('active', '使用中'),
                    ('stopped', '停机'),
                    ('offline', '已下线'),
                ],
                default='active',
                max_length=20,
                verbose_name='状态',
            ),
        ),
    ]
