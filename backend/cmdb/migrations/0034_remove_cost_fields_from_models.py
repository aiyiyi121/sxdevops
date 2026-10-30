from django.db import migrations


def remove_cost_fields_from_models(apps, schema_editor):
    ci_field_model = apps.get_model('cmdb', 'CIField')
    ci_field_model.objects.filter(
        code__in=['monthly_cost', 'cost_center'],
        is_builtin=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0033_move_access_address_to_model_fields'),
    ]

    operations = [
        migrations.RunPython(remove_cost_fields_from_models, migrations.RunPython.noop),
    ]
