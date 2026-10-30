import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('aiops', '0026_rename_skill_binding_label'),
        ('ops', '0059_task_resource_cmdb'),
    ]

    operations = [
        migrations.CreateModel(
            name='AIOpsRemediationVerification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('thread_id', models.CharField(max_length=128, unique=True)),
                ('status', models.CharField(choices=[('waiting', '等待任务完成'), ('running', '验证中'), ('passed', '告警已恢复'), ('failed', '验证未通过'), ('inconclusive', '证据不足')], default='waiting', max_length=16)),
                ('observation_seconds', models.PositiveIntegerField(default=60)),
                ('baseline', models.JSONField(default=dict)),
                ('evidence', models.JSONField(blank=True, default=dict)),
                ('summary', models.CharField(blank=True, default='', max_length=500)),
                ('is_demo', models.BooleanField(default=False)),
                ('checkpoint_expired', models.BooleanField(default=False)),
                ('attempt_count', models.PositiveIntegerField(default=0)),
                ('claim_token', models.UUIDField(blank=True, null=True)),
                ('lease_until', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('action', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='verification', to='aiops.aiopspendingaction')),
                ('environment', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='verifications', to='aiops.aiopsknowledgeenvironment')),
                ('task', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='aiops_verification', to='ops.hosttask')),
            ],
            options={
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['status', 'lease_until'], name='aiops_verification_queue_idx')],
            },
        ),
    ]
