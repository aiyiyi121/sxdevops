from django.db import migrations


def migrate_service_expiry_fields(apps, schema_editor):
    CIField = apps.get_model('cmdb', 'CIField')
    CIType = apps.get_model('cmdb', 'CIType')
    ConfigItem = apps.get_model('cmdb', 'ConfigItem')

    ci_type = CIType.objects.filter(code='THIRD_PARTY_SERVICE').first()
    if not ci_type:
        return

    field_renames = {
        'expire_date': {
            'code': 'service_expiry_date',
            'name': '服务到期日',
            'field_group': '服务治理',
            'field_type': 'date',
            'sort_order': 55,
        },
        'contract_expire_warning_days': {
            'code': 'service_expire_warning_days',
            'name': '到期提醒提前天数',
            'field_group': '服务治理',
            'field_type': 'integer',
            'default': 30,
            'sort_order': 60,
        },
    }
    for old_code, defaults in field_renames.items():
        old_field = CIField.objects.filter(ci_type=ci_type, code=old_code).first()
        new_field = CIField.objects.filter(ci_type=ci_type, code=defaults['code']).first()
        if old_field and not new_field:
            for key, value in defaults.items():
                setattr(old_field, key, value)
            old_field.save()
        elif old_field and new_field:
            old_field.delete()

    for item in ConfigItem.objects.filter(ci_type=ci_type).only('id', 'attributes'):
        attributes = dict(item.attributes or {})
        changed = False
        for old_code, defaults in field_renames.items():
            new_code = defaults['code']
            if new_code not in attributes and old_code in attributes:
                attributes[new_code] = attributes[old_code]
                changed = True
            if old_code in attributes:
                attributes.pop(old_code, None)
                changed = True
        if changed:
            item.attributes = attributes
            item.save(update_fields=['attributes'])


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0018_promote_asset_item_builtin'),
    ]

    operations = [
        migrations.RunPython(migrate_service_expiry_fields, migrations.RunPython.noop),
    ]
