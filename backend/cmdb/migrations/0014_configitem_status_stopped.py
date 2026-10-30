from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0013_extend_resource_node_cloud_tree_types'),
    ]

    operations = [
        migrations.AlterField(
            model_name='configitem',
            name='status',
            field=models.CharField(
                choices=[
                    ('active', '使用中'),
                    ('idle', '闲置'),
                    ('stopped', '停机'),
                    ('offline', '已下线'),
                ],
                default='active',
                max_length=20,
                verbose_name='状态',
            ),
        ),
    ]
