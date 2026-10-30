from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0014_configitem_status_stopped'),
    ]

    operations = [
        migrations.AddField(
            model_name='resourcenode',
            name='is_synced',
            field=models.BooleanField(default=False, verbose_name='同步来源节点'),
        ),
    ]
