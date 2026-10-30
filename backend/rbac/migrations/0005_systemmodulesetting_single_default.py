from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rbac', '0004_systemmodulesetting_is_default'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='systemmodulesetting',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_default', True)),
                fields=('is_default',),
                name='rbac_single_default_page',
            ),
        ),
    ]
