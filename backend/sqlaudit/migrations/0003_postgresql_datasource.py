from django.db import migrations, models


def correct_datasources(apps, schema_editor):
    sources = apps.get_model('sqlaudit', 'DataSource').objects.using(schema_editor.connection.alias)
    sources.filter(db_type='polardb', port=3306).update(port=5432)
    sources.filter(db_type='polardb').update(db_type='postgresql', charset='UTF8')


class Migration(migrations.Migration):
    dependencies = [('sqlaudit', '0002_datasource_db_type')]

    operations = [
        migrations.AddField(
            model_name='datasource', name='database',
            field=models.CharField('连接数据库', max_length=128, blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='datasource', name='db_type',
            field=models.CharField('数据库类型', max_length=16, default='mysql',
                                   choices=[('mysql', 'MySQL'), ('mongodb', 'MongoDB'), ('postgresql', 'PostgreSQL')]),
        ),
        migrations.RunPython(correct_datasources, migrations.RunPython.noop),
    ]
