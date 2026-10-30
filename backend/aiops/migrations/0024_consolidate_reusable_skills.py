import django.db.models.deletion
from django.db import migrations, models


def consolidate_skills(apps, schema_editor):
    from aiops.skill_catalog_v1 import consolidate_builtin_skills

    consolidate_builtin_skills(
        apps.get_model('aiops', 'AIOpsSkill'),
        apps.get_model('aiops', 'AIOpsAgentConfig'),
    )


class Migration(migrations.Migration):
    dependencies = [('aiops', '0023_aiops_graph_node_run')]

    operations = [
        migrations.AlterField(
            model_name='aiopsskill', name='applicable_actions',
            field=models.JSONField(blank=True, default=list, verbose_name='挂载的问答能力'),
        ),
        migrations.AddField(
            model_name='aiopsskill', name='builtin_version',
            field=models.PositiveSmallIntegerField(default=0, editable=False, verbose_name='内置目录版本'),
        ),
        migrations.AddField(
            model_name='aiopsskill', name='merged_into',
            field=models.ForeignKey(
                blank=True, editable=False, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='merged_sources', to='aiops.aiopsskill', verbose_name='已合并到',
            ),
        ),
        migrations.RunPython(consolidate_skills, migrations.RunPython.noop),
    ]
