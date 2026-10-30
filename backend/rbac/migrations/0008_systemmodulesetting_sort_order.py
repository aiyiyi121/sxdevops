from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('rbac', '0007_k8s_user_access'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemmodulesetting',
            name='sort_order',
            field=models.PositiveIntegerField(blank=True, default=None, null=True, verbose_name='菜单顺序'),
        ),
    ]
