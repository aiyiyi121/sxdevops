from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0010_cifield_sync_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='cirelation',
            name='evidence_source',
            field=models.CharField(
                choices=[
                    ('manual', '人工维护'),
                    ('import', '批量导入'),
                    ('sync', '同步发现'),
                    ('governance', '治理建议'),
                    ('system', '系统联动'),
                ],
                default='manual',
                max_length=30,
                verbose_name='关系来源',
            ),
        ),
        migrations.AddField(
            model_name='cirelation',
            name='confidence',
            field=models.PositiveSmallIntegerField(default=100, verbose_name='置信度'),
        ),
        migrations.AddField(
            model_name='cirelation',
            name='evidence',
            field=models.JSONField(blank=True, default=dict, verbose_name='关系证据'),
        ),
    ]
