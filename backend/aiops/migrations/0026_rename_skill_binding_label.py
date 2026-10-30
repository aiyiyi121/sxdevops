from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('aiops', '0025_refine_reusable_skills')]

    operations = [
        migrations.AlterField(
            model_name='aiopsskill',
            name='applicable_actions',
            field=models.JSONField(blank=True, default=list, verbose_name='挂载的问答类型'),
        ),
    ]
