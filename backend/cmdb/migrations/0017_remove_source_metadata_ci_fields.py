from django.db import migrations


SOURCE_METADATA_FIELD_CODES = (
    'source_type',
    'source_account',
    'source_region',
    'source_unique_id',
)


def remove_source_metadata_fields(apps, schema_editor):
    CIField = apps.get_model('cmdb', 'CIField')
    CIField.objects.filter(code__in=SOURCE_METADATA_FIELD_CODES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0016_ipsubnet_ipaddress'),
    ]

    operations = [
        migrations.RunPython(remove_source_metadata_fields, migrations.RunPython.noop),
    ]
