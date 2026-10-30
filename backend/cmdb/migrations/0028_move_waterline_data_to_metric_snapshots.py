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


def move_waterline_data_to_metric_snapshots(apps, schema_editor):
    ConfigItem = apps.get_model('cmdb', 'ConfigItem')
    CIField = apps.get_model('cmdb', 'CIField')

    CIField.objects.filter(is_builtin=True, code__in=WATERLINE_ATTRIBUTE_CODES).delete()
    for item in ConfigItem.objects.exclude(attributes={}).only('id', 'attributes'):
        attributes = item.attributes if isinstance(item.attributes, dict) else {}
        cleaned = {key: value for key, value in attributes.items() if key not in WATERLINE_ATTRIBUTE_CODES}
        if cleaned != attributes:
            ConfigItem.objects.filter(pk=item.pk).update(attributes=cleaned)


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0027_clear_collected_default_environment'),
    ]

    operations = [
        migrations.RunPython(move_waterline_data_to_metric_snapshots, migrations.RunPython.noop),
    ]
