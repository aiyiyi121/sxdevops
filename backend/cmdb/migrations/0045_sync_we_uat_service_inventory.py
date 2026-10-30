from django.db import migrations


def sync_we_uat_service_inventory(apps, schema_editor):
    # Private inventory is provisioned outside public migrations.
    return


class Migration(migrations.Migration):
    dependencies = [
        ('cmdb', '0044_rename_we_environment_nodes'),
    ]

    operations = [
        migrations.RunPython(sync_we_uat_service_inventory, migrations.RunPython.noop),
    ]
