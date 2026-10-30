from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0029_clear_waterline_change_logs'),
    ]

    operations = [
        migrations.AddField(
            model_name='cisyncrecord',
            name='batch_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=32, verbose_name='执行批次'),
        ),
    ]
