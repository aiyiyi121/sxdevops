from django.db import migrations


def rename_we_environment_nodes(apps, schema_editor):
    # Private environment names are managed outside public migrations.
    return


class Migration(migrations.Migration):
    dependencies = [
        ('cmdb', '0043_sync_we_test_service_inventory'),
    ]

    operations = [
        migrations.RunPython(rename_we_environment_nodes, migrations.RunPython.noop),
    ]
