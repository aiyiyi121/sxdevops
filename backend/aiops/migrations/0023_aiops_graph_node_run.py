import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('aiops', '0022_aiops_chat_job')]

    operations = [
        migrations.CreateModel(
            name='AIOpsGraphNodeRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('thread_id', models.CharField(db_index=True, max_length=128)),
                ('node', models.CharField(max_length=64)),
                ('status', models.CharField(default='running', max_length=16)),
                ('started_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('duration_ms', models.PositiveIntegerField(default=0)),
                ('retry_count', models.PositiveIntegerField(default=0)),
                ('error', models.CharField(blank=True, default='', max_length=500)),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='graph_node_runs', to='aiops.aiopschatmessage')),
            ],
            options={'ordering': ['id'], 'indexes': [models.Index(fields=['status', 'started_at'], name='aiops_graph_run_status_idx')]},
        ),
    ]
