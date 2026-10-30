from django.db import migrations, models


def restore_default_site_name(apps, schema_editor):
    SiteSetting = apps.get_model('rbac', 'SiteSetting')
    SiteSetting.objects.using(schema_editor.connection.alias).filter(site_name='exampleOps').update(site_name='SXDevOps')


class Migration(migrations.Migration):
    dependencies = [
        ('rbac', '0011_site_name_length'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sitesetting',
            name='site_name',
            field=models.CharField(default='SXDevOps', max_length=10, verbose_name='网站名称'),
        ),
        migrations.RunPython(restore_default_site_name, migrations.RunPython.noop),
    ]
