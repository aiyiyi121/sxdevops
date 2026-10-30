from django.db import migrations


def merge_warranty_into_service_expiry(apps, schema_editor):
    CIField = apps.get_model('cmdb', 'CIField')
    CIType = apps.get_model('cmdb', 'CIType')
    ConfigItem = apps.get_model('cmdb', 'ConfigItem')

    ci_types = CIType.objects.filter(code__in=['IDC_SERVER', 'ASSET_ITEM'])
    for ci_type in ci_types:
        old_field = CIField.objects.filter(ci_type=ci_type, code='warranty_end_date').first()
        new_field = CIField.objects.filter(ci_type=ci_type, code='service_expiry_date').first()
        if old_field and not new_field:
            old_field.code = 'service_expiry_date'
            old_field.name = '服务到期日'
            old_field.field_group = '服务治理'
            old_field.save(update_fields=['code', 'name', 'field_group'])
        elif old_field and new_field:
            old_field.delete()

        for item in ConfigItem.objects.filter(ci_type=ci_type).only('id', 'attributes'):
            attributes = dict(item.attributes or {})
            changed = False
            if 'service_expiry_date' not in attributes and 'warranty_end_date' in attributes:
                attributes['service_expiry_date'] = attributes['warranty_end_date']
                changed = True
            if 'warranty_end_date' in attributes:
                attributes.pop('warranty_end_date', None)
                changed = True
            if 'warranty_expire_date' in attributes:
                attributes.setdefault('service_expiry_date', attributes['warranty_expire_date'])
                attributes.pop('warranty_expire_date', None)
                changed = True
            if 'warranty_warning_days' in attributes:
                attributes.setdefault('service_expire_warning_days', attributes['warranty_warning_days'])
                attributes.pop('warranty_warning_days', None)
                changed = True
            if changed:
                item.attributes = attributes
                item.save(update_fields=['attributes'])


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0024_configitempassword'),
    ]

    operations = [
        migrations.RunPython(merge_warranty_into_service_expiry, migrations.RunPython.noop),
    ]
