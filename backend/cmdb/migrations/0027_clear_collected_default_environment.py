from django.db import migrations


def _is_provider_source(source_type):
    value = str(source_type or '').strip().lower()
    return value == 'vsphere_vm' or value.startswith('aliyun_') or value.startswith('huaweicloud_')


def _has_environment_tag(value):
    if isinstance(value, dict):
        normalized = {str(key).strip().lower(): item for key, item in value.items()}
        if any(normalized.get(key) not in (None, '') for key in ('environment', 'env')):
            return True
        return any(_has_environment_tag(item) for item in value.values())
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                key = str(item.get('key') or item.get('Key') or item.get('TagKey') or '').strip().lower()
                tag_value = item.get('value', item.get('Value', item.get('TagValue')))
                if key in {'environment', 'env'} and tag_value not in (None, ''):
                    return True
            if _has_environment_tag(item):
                return True
    return False


def _mapping_has_environment_tag(raw_payload):
    if not isinstance(raw_payload, dict):
        return False
    attributes = raw_payload.get('attributes') if isinstance(raw_payload.get('attributes'), dict) else {}
    return any(
        _has_environment_tag(value)
        for value in (
            raw_payload.get('tags'),
            raw_payload.get('cloud_tags'),
            attributes.get('tags'),
            attributes.get('cloud_tags'),
        )
    )


def clear_collected_default_environment(apps, schema_editor):
    ConfigItem = apps.get_model('cmdb', 'ConfigItem')
    CISourceMapping = apps.get_model('cmdb', 'CISourceMapping')
    CIChangeLog = apps.get_model('cmdb', 'CIChangeLog')

    candidate_ids = set()
    for mapping in CISourceMapping.objects.filter(
        ci__environment='prod',
        ci__environment_node__isnull=True,
    ).only('ci_id', 'source_type', 'raw_payload'):
        if not _is_provider_source(mapping.source_type):
            continue
        if _mapping_has_environment_tag(mapping.raw_payload):
            continue
        candidate_ids.add(mapping.ci_id)

    if not candidate_ids:
        return

    protected_ids = set()
    for item in ConfigItem.objects.filter(id__in=candidate_ids).only('id', 'attributes'):
        attributes = item.attributes if isinstance(item.attributes, dict) else {}
        if _has_environment_tag(attributes.get('cloud_tags')) or _has_environment_tag(attributes.get('tags')):
            protected_ids.add(item.id)

    for change in CIChangeLog.objects.filter(ci_id__in=candidate_ids).only('ci_id', 'source', 'before', 'after', 'diff'):
        if change.source in {'sync', 'collection', 'system'} or _is_provider_source(change.source):
            continue
        if any(_has_environment_tag(value) for value in (change.before, change.after, change.diff)):
            protected_ids.add(change.ci_id)

    ConfigItem.objects.filter(id__in=candidate_ids - protected_ids).update(environment='')


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0026_remove_vsphere_summary_region'),
    ]

    operations = [
        migrations.RunPython(clear_collected_default_environment, migrations.RunPython.noop),
    ]
