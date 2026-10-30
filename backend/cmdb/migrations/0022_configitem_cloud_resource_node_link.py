from django.db import migrations, models
import django.db.models.deletion


CLOUD_NODE_TYPES = {'cloud_account', 'cloud_region', 'cloud_cluster', 'cloud_host'}


def link_existing_cloud_resource_nodes(apps, schema_editor):
    ConfigItem = apps.get_model('cmdb', 'ConfigItem')
    ResourceNode = apps.get_model('cmdb', 'ResourceNode')
    cloud_node_ids = set(
        ResourceNode.objects.filter(node_type__in=CLOUD_NODE_TYPES).values_list('id', flat=True)
    )
    for item in ConfigItem.objects.filter(resource_node__isnull=True).only('id', 'attributes'):
        attributes = item.attributes if isinstance(item.attributes, dict) else {}
        raw_node_id = attributes.get('resource_node_id')
        try:
            node_id = int(raw_node_id)
        except (TypeError, ValueError):
            continue
        if node_id in cloud_node_ids:
            ConfigItem.objects.filter(pk=item.pk).update(resource_node_id=node_id)


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0021_configitem_resource_node_links'),
    ]

    operations = [
        migrations.AddField(
            model_name='configitem',
            name='resource_node',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='resource_config_items',
                to='cmdb.resourcenode',
                verbose_name='云资源节点',
            ),
        ),
        migrations.RunPython(link_existing_cloud_resource_nodes, migrations.RunPython.noop),
    ]
