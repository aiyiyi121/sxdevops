from django.db import migrations
from django.db.models import Q


def move_access_address_to_model_fields(apps, schema_editor):
    config_item_model = apps.get_model('cmdb', 'ConfigItem')
    target_items = config_item_model.objects.filter(
        Q(ci_type__group__code__in=['middleware', 'bigdata'])
        | Q(ci_type__code='THIRD_PARTY_SERVICE')
    )
    for item in target_items.iterator():
        attributes = dict(item.attributes or {})
        legacy_address = str(attributes.get('ip_address') or '').strip()
        if not legacy_address:
            continue
        if not str(attributes.get('access_address') or '').strip():
            attributes['access_address'] = legacy_address
        attributes.pop('ip_address', None)
        item.attributes = attributes
        item.save(update_fields=['attributes'])


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0032_rename_legacy_access_address_fields'),
    ]

    operations = [
        migrations.RunPython(move_access_address_to_model_fields, migrations.RunPython.noop),
    ]
