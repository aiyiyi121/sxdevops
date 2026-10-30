from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('rbac', '0010_site_setting'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sitesetting',
            name='site_name',
            field=models.CharField(default='exampleOps', max_length=10, verbose_name='网站名称'),
        ),
    ]
