from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('cmdb', '0036_configitem_environment_free_text'),
    ]

    operations = [
        migrations.AlterField(
            model_name='resourcerequest',
            name='priority',
            field=models.CharField(
                choices=[('low', '低'), ('medium', '中'), ('high', '高'), ('urgent', '紧急')],
                default='medium',
                max_length=16,
                verbose_name='优先级',
            ),
        ),
        migrations.AlterField(
            model_name='resourcerequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', '待审批'),
                    ('approved', '已批准'),
                    ('provisioning', '交付中'),
                    ('failed', '交付失败'),
                    ('rejected', '已拒绝'),
                    ('completed', '已完成'),
                ],
                default='pending',
                max_length=20,
                verbose_name='状态',
            ),
        ),
    ]
