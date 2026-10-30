from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('aiops', '0020_aiopsknowledgeenvironment_is_default'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aiopspendingaction',
            name='action_type',
            field=models.CharField(
                choices=[
                    ('execute_host_task', '执行主机任务'),
                    ('create_cmdb_asset', '创建 CMDB 资产'),
                ],
                max_length=32,
                verbose_name='动作类型',
            ),
        ),
    ]
