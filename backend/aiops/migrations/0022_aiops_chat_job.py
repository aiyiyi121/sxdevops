import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('aiops', '0021_alter_aiopspendingaction_action_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='AIOpsChatJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('thread_id', models.CharField(max_length=128, unique=True)),
                ('analysis_only', models.BooleanField(default=False)),
                ('status', models.CharField(choices=[('queued', '排队中'), ('running', '执行中'), ('completed', '已完成'), ('failed', '失败')], default='queued', max_length=16)),
                ('attempt_count', models.PositiveIntegerField(default=0)),
                ('claim_token', models.UUIDField(blank=True, null=True)),
                ('lease_until', models.DateTimeField(blank=True, null=True)),
                ('error_message', models.CharField(blank=True, default='', max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assistant_message', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='chat_job', to='aiops.aiopschatmessage')),
                ('user_message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='submitted_chat_jobs', to='aiops.aiopschatmessage')),
            ],
            options={
                'ordering': ['created_at', 'id'],
                'indexes': [models.Index(fields=['status', 'lease_until'], name='aiops_chat_job_queue_idx')],
            },
        ),
    ]
