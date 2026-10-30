from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0035_costoptimizationtask_costoptimizationprogress'),
    ]

    operations = [
        migrations.AlterField(
            model_name='configitem',
            name='environment',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='环境'),
        ),
    ]
