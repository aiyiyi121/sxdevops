from django.db import migrations
from django.db.models import Q


def rename_qwen_provider(apps, schema_editor):
    provider = apps.get_model('aiops', 'AIOpsModelProvider')
    provider.objects.using(schema_editor.connection.alias).filter(name='阿里千问').filter(
        Q(provider_preset='aliyun_qwen') | Q(base_url__icontains='dashscope')
    ).update(name='阿里 Qwen')


class Migration(migrations.Migration):
    dependencies = [('aiops', '0028_agent_question_scope')]

    operations = [migrations.RunPython(rename_qwen_provider, migrations.RunPython.noop)]
