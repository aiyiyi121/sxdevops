from django.db import migrations


def _root_nodes_by_name(ResourceNode):
    nodes_by_name = {}
    for node in ResourceNode.objects.filter(node_type='cloud_account', parent__isnull=True).only('id', 'name', 'is_synced'):
        nodes_by_name.setdefault(node.name, []).append(node)
    return {
        name: nodes[0]
        for name, nodes in nodes_by_name.items()
        if len(nodes) == 1
    }


def _resource_node_for_source(ResourceNode, roots, account, region):
    root = roots.get(str(account or '').strip())
    if root is None:
        return None
    region_name = str(region or '').strip()
    if not region_name:
        return root
    region_nodes = list(
        ResourceNode.objects.filter(
            node_type='cloud_region',
            parent_id=root.id,
            name=region_name,
        ).only('id')[:2]
    )
    if len(region_nodes) == 1:
        return region_nodes[0]
    if len(region_nodes) > 1:
        return root
    return ResourceNode.objects.create(
        name=region_name,
        node_type='cloud_region',
        parent_id=root.id,
        is_synced=root.is_synced,
    )


def backfill_cloud_resource_tree_links(apps, schema_editor):
    ConfigItem = apps.get_model('cmdb', 'ConfigItem')
    CISourceMapping = apps.get_model('cmdb', 'CISourceMapping')
    ResourceNode = apps.get_model('cmdb', 'ResourceNode')
    roots = _root_nodes_by_name(ResourceNode)
    if not roots:
        return

    mappings_by_ci = {}
    for mapping in CISourceMapping.objects.exclude(ci__resource_node__isnull=False).exclude(source_account='').only(
        'ci_id', 'source_account', 'source_region'
    ):
        node = _resource_node_for_source(ResourceNode, roots, mapping.source_account, mapping.source_region)
        if node is not None:
            mappings_by_ci.setdefault(mapping.ci_id, set()).add(node.id)

    for item in ConfigItem.objects.filter(resource_node__isnull=True).only('id', 'attributes'):
        node_ids = mappings_by_ci.get(item.id, set())
        if len(node_ids) != 1:
            continue
        node_id = next(iter(node_ids))
        attributes = item.attributes if isinstance(item.attributes, dict) else {}
        attributes = {**attributes, 'resource_node_id': node_id}
        ConfigItem.objects.filter(pk=item.pk).update(resource_node_id=node_id, attributes=attributes)


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0022_configitem_cloud_resource_node_link'),
    ]

    operations = [
        migrations.RunPython(backfill_cloud_resource_tree_links, migrations.RunPython.noop),
    ]
