from django.db import migrations


WATERLINE_ATTRIBUTE_CODES = {
    'cpu_used_mhz', 'cpu_usage', 'cpu_usage_percent', 'cpu_utilization', 'cpu_utilization_percent', 'cpu_used_percent',
    'memory_total_gb', 'memory_used_gb', 'memory_free_gb', 'memory_available_gb', 'memory_usage', 'memory_usage_percent',
    'memory_utilization', 'memory_utilization_percent', 'memory_used_percent',
    'disk_used_gb', 'disk_usage', 'disk_usage_percent', 'disk_utilization', 'disk_utilization_percent', 'disk_used_percent',
    'storage_used_gb', 'storage_usage', 'storage_usage_percent', 'storage_utilization', 'storage_utilization_percent', 'storage_used_percent',
    'root_disk_total_gb', 'root_disk_free_gb', 'root_disk_available_gb', 'root_mountpoint',
    'metric_collection_source', 'metric_collection_status', 'metric_collection_error', 'metrics_collection_status',
    'metric_datasource', 'metric_collected_at', 'prometheus_target',
}


def _clean_attributes(attributes):
    return {
        key: value
        for key, value in attributes.items()
        if key not in WATERLINE_ATTRIBUTE_CODES
    }


def _clean_change_payload(payload):
    if not isinstance(payload, dict):
        return payload
    cleaned = dict(payload)
    attributes = cleaned.get('attributes')
    if isinstance(attributes, dict):
        cleaned_attributes = _clean_attributes(attributes)
        for key in ('before', 'after'):
            if isinstance(cleaned_attributes.get(key), dict):
                cleaned_attributes[key] = _clean_attributes(cleaned_attributes[key])
        cleaned['attributes'] = cleaned_attributes
    return cleaned


def clear_waterline_change_logs(apps, schema_editor):
    CIChangeLog = apps.get_model('cmdb', 'CIChangeLog')

    for change in CIChangeLog.objects.all().only('id', 'before', 'after', 'diff'):
        before = _clean_change_payload(change.before)
        after = _clean_change_payload(change.after)
        diff = _clean_change_payload(change.diff)
        if (before, after, diff) != (change.before, change.after, change.diff):
            CIChangeLog.objects.filter(pk=change.pk).update(before=before, after=after, diff=diff)


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0028_move_waterline_data_to_metric_snapshots'),
    ]

    operations = [
        migrations.RunPython(clear_waterline_change_logs, migrations.RunPython.noop),
    ]
