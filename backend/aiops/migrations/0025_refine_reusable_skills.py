from django.db import migrations


def refine_skills(apps, schema_editor):
    from aiops.skill_catalog_v1 import refine_consolidated_skills

    refine_consolidated_skills(
        apps.get_model('aiops', 'AIOpsSkill'),
        apps.get_model('aiops', 'AIOpsAgentConfig'),
    )


class Migration(migrations.Migration):
    dependencies = [('aiops', '0024_consolidate_reusable_skills')]

    operations = [migrations.RunPython(refine_skills, migrations.RunPython.noop)]
