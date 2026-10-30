from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('rbac', '0009_hide_incomplete_modules'),
    ]

    operations = [
        migrations.CreateModel(
            name='SiteSetting',
            fields=[
                ('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('site_name', models.CharField(default='exampleOps', max_length=40, verbose_name='网站名称')),
                ('icon_data', models.BinaryField(blank=True, default=bytes, verbose_name='网站图标')),
                ('updated_by', models.CharField(blank=True, default='', max_length=150, verbose_name='更新人')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': '网站基础配置',
                'verbose_name_plural': '网站基础配置',
                'constraints': [models.CheckConstraint(condition=models.Q(id=1), name='rbac_single_site_setting')],
            },
        ),
    ]
