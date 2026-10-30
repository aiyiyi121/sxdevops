from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0034_remove_cost_fields_from_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='CostOptimizationTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('month', models.CharField(max_length=7, verbose_name='归属月份')),
                ('suggestion_type', models.CharField(max_length=32, verbose_name='优化类型')),
                ('suggestion_title', models.CharField(max_length=200, verbose_name='建议标题')),
                ('suggestion_snapshot', models.JSONField(blank=True, default=dict, verbose_name='建议快照')),
                ('expected_monthly_saving', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='预估月节省')),
                ('actual_monthly_saving', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='实际月节省')),
                ('status', models.CharField(choices=[('claimed', '已认领'), ('in_progress', '处理中'), ('completed', '已完成'), ('deferred', '暂缓处理'), ('rejected', '不采纳')], default='claimed', max_length=20, verbose_name='处理状态')),
                ('owner', models.CharField(blank=True, default='', max_length=80, verbose_name='认领人')),
                ('claimed_at', models.DateTimeField(blank=True, null=True, verbose_name='认领时间')),
                ('resolved_by', models.CharField(blank=True, default='', max_length=80, verbose_name='结论确认人')),
                ('resolved_at', models.DateTimeField(blank=True, null=True, verbose_name='结论时间')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('ci', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cost_optimization_tasks', to='cmdb.configitem')),
            ],
            options={'ordering': ['-updated_at', '-id']},
        ),
        migrations.CreateModel(
            name='CostOptimizationProgress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('claimed', '已认领'), ('in_progress', '处理中'), ('completed', '已完成'), ('deferred', '暂缓处理'), ('rejected', '不采纳')], max_length=20, verbose_name='处理状态')),
                ('progress_percent', models.PositiveSmallIntegerField(default=0, verbose_name='完成度')),
                ('note', models.TextField(blank=True, default='', verbose_name='进展说明')),
                ('actual_monthly_saving', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='实际月节省')),
                ('created_by', models.CharField(blank=True, default='', max_length=80, verbose_name='记录人')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='progress_entries', to='cmdb.costoptimizationtask')),
            ],
            options={'ordering': ['-created_at', '-id']},
        ),
        migrations.AddConstraint(
            model_name='costoptimizationtask',
            constraint=models.UniqueConstraint(fields=('ci', 'month', 'suggestion_type'), name='cmdb_cost_optimization_task_unique_suggestion'),
        ),
    ]
