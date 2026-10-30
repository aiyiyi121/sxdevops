from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rbac', '0003_enable_observability_menu'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemmodulesetting',
            name='is_default',
            field=models.BooleanField(default=False, verbose_name='是否为登录默认页'),
        ),
    ]
