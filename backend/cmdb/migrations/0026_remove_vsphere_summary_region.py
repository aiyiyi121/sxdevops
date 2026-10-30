from django.db import migrations


def remove_vsphere_summary_region(apps, schema_editor):
    CISourceMapping = apps.get_model('cmdb', 'CISourceMapping')
    ConfigItem = apps.get_model('cmdb', 'ConfigItem')
    ResourceNode = apps.get_model('cmdb', 'ResourceNode')

    mappings = CISourceMapping.objects.filter(
        source_type='vsphere_vm',
        source_unique_id__startswith='vsphere-summary:',
    ).select_related('ci')
    candidate_region_ids = set()

    for mapping in mappings:
        source_region = str(mapping.source_region or '').strip()
        if not source_region:
            continue

        config_item = mapping.ci
        account_node = ResourceNode.objects.filter(
            node_type='cloud_account',
            parent__isnull=True,
            name=mapping.source_account,
        ).order_by('id').first()
        region_node = ResourceNode.objects.filter(
            node_type='cloud_region',
            parent=account_node,
            name=source_region,
        ).order_by('id').first() if account_node else None

        attributes = dict(config_item.attributes or {})
        attributes.pop('source_region', None)
        if account_node and region_node and config_item.resource_node_id == region_node.id:
            config_item.resource_node_id = account_node.id
            attributes['resource_node_id'] = account_node.id
        config_item.attributes = attributes
        config_item.save(update_fields=['resource_node', 'attributes'])

        raw_payload = dict(mapping.raw_payload or {})
        raw_payload['source_region'] = ''
        raw_attributes = dict(raw_payload.get('attributes') or {})
        raw_attributes.pop('source_region', None)
        if 'attributes' in raw_payload:
            raw_payload['attributes'] = raw_attributes

        duplicate = CISourceMapping.objects.filter(
            source_type=mapping.source_type,
            source_account=mapping.source_account,
            source_region='',
            source_unique_id=mapping.source_unique_id,
        ).exclude(pk=mapping.pk).first()
        if duplicate:
            mapping.delete()
        else:
            mapping.source_region = ''
            mapping.raw_payload = raw_payload
            mapping.save(update_fields=['source_region', 'raw_payload', 'updated_at'])

        if region_node:
            candidate_region_ids.add(region_node.id)

    for region_node in ResourceNode.objects.filter(id__in=candidate_region_ids):
        has_children = ResourceNode.objects.filter(parent_id=region_node.id).exists()
        has_config_items = ConfigItem.objects.filter(resource_node_id=region_node.id).exists()
        if not has_children and not has_config_items:
            region_node.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0025_merge_warranty_into_service_expiry'),
    ]

    operations = [
        migrations.RunPython(remove_vsphere_summary_region, migrations.RunPython.noop),
    ]
