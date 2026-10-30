from django.db import migrations, models
import django.db.models.deletion


def seed_security_posture(apps, schema_editor):
    # Private inventory is provisioned outside public migrations.
    return


class Migration(migrations.Migration):
    dependencies = [('cloudsecurity', '0001_internal_platform_security')]

    operations = [
        migrations.CreateModel(
            name='InternalSecurityAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(choices=[('aliyun', '阿里云 ECS'), ('vsphere', '机房 vSphere'), ('cmdb', 'CMDB 主机')], default='cmdb', max_length=20, verbose_name='资产来源')),
                ('source_id', models.CharField(blank=True, default='', max_length=128, verbose_name='来源资产 ID')),
                ('name', models.CharField(max_length=128, verbose_name='主机名称')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP 地址')),
                ('os_name', models.CharField(blank=True, default='', max_length=128, verbose_name='操作系统')),
                ('environment', models.CharField(blank=True, default='', max_length=32, verbose_name='环境')),
                ('business_line', models.CharField(blank=True, default='', max_length=80, verbose_name='业务系统')),
                ('agent_status', models.CharField(choices=[('online', '防护中'), ('offline', '离线'), ('pending', '待接入')], default='pending', max_length=16, verbose_name='Agent 状态')),
                ('risk_level', models.CharField(choices=[('clean', '无风险'), ('low', '低风险'), ('medium', '中风险'), ('high', '高风险'), ('critical', '严重风险')], default='clean', max_length=16, verbose_name='风险等级')),
                ('last_seen_at', models.DateTimeField(blank=True, null=True, verbose_name='最近心跳')),
                ('last_scan_at', models.DateTimeField(blank=True, null=True, verbose_name='最近扫描')),
                ('is_enabled', models.BooleanField(default=True, verbose_name='是否启用')),
                ('tags', models.JSONField(blank=True, default=list, verbose_name='标签')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={'verbose_name': '内部安全资产', 'verbose_name_plural': '内部安全资产', 'ordering': ['-risk_level', 'name', 'id'], 'indexes': [models.Index(fields=['source', 'agent_status'], name='cloudsec_asset_src_agent'), models.Index(fields=['risk_level', 'updated_at'], name='cloudsec_asset_risk_upd')]},
        ),
        migrations.CreateModel(
            name='SoftwareSecurityItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('row_number', models.PositiveIntegerField(unique=True, verbose_name='表格序号')),
                ('deployment_type', models.CharField(choices=[('self_hosted', '自建'), ('aliyun', '阿里云'), ('base_image', '基础镜像')], max_length=20, verbose_name='部署形态')),
                ('software_name', models.CharField(max_length=160, verbose_name='软件或服务')),
                ('latest_version', models.CharField(blank=True, default='', max_length=160, verbose_name='目标版本')),
                ('current_version', models.CharField(blank=True, default='', max_length=160, verbose_name='当前版本')),
                ('other_versions', models.CharField(blank=True, default='', max_length=160, verbose_name='其他环境版本')),
                ('risk_summary', models.TextField(blank=True, default='', verbose_name='当前风险')),
                ('upgrade_advice', models.TextField(blank=True, default='', verbose_name='升级建议')),
                ('upgrade_necessity', models.CharField(choices=[('required', '必要'), ('recommended', '建议'), ('not_needed', '暂不必要')], default='not_needed', max_length=20, verbose_name='升级必要性')),
                ('priority', models.CharField(choices=[('P0', 'P0'), ('P1', 'P1'), ('P2', 'P2'), ('P3', 'P3')], default='P3', max_length=2, verbose_name='优先级')),
                ('bug_advice', models.TextField(blank=True, default='', verbose_name='重大 Bug 与规避提醒')),
                ('owner_feedback', models.TextField(blank=True, default='', verbose_name='负责人反馈')),
                ('plan_time', models.CharField(blank=True, default='', max_length=80, verbose_name='升级计划')),
                ('status', models.CharField(choices=[('open', '待治理'), ('planned', '已排期'), ('accepted', '风险接受'), ('done', '已完成')], default='open', max_length=16, verbose_name='治理状态')),
                ('last_reviewed_at', models.DateTimeField(blank=True, null=True, verbose_name='最近评估')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否启用')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={'verbose_name': '软件安全版本项', 'verbose_name_plural': '软件安全版本项', 'ordering': ['priority', 'software_name', 'id'], 'indexes': [models.Index(fields=['priority', 'upgrade_necessity'], name='cloudsec_sw_prio_need'), models.Index(fields=['deployment_type', 'status'], name='cloudsec_sw_type_status')]},
        ),
        migrations.CreateModel(
            name='InternalSecurityThreat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(default='agent', max_length=24, verbose_name='检测来源')),
                ('threat_type', models.CharField(choices=[('malware', '恶意文件'), ('ransomware', '勒索行为'), ('suspicious_script', '可疑脚本'), ('webshell', 'WebShell'), ('crypto_miner', '挖矿程序'), ('brute_force', '暴力破解')], max_length=24, verbose_name='威胁类型')),
                ('title', models.CharField(max_length=200, verbose_name='威胁标题')),
                ('severity', models.CharField(choices=[('critical', '严重'), ('high', '高'), ('medium', '中'), ('low', '低')], default='medium', max_length=16, verbose_name='风险等级')),
                ('status', models.CharField(choices=[('open', '待处理'), ('processing', '处理中'), ('isolated', '已隔离'), ('resolved', '已解决'), ('ignored', '已忽略')], default='open', max_length=16, verbose_name='处理状态')),
                ('description', models.TextField(blank=True, default='', verbose_name='威胁描述')),
                ('process_path', models.CharField(blank=True, default='', max_length=255, verbose_name='进程或文件路径')),
                ('command_line', models.TextField(blank=True, default='', verbose_name='命令行')),
                ('file_hash', models.CharField(blank=True, default='', max_length=128, verbose_name='文件哈希')),
                ('remote_ip', models.GenericIPAddressField(blank=True, null=True, verbose_name='关联远端 IP')),
                ('suggestion', models.TextField(blank=True, default='', verbose_name='处置建议')),
                ('owner', models.CharField(blank=True, default='', max_length=80, verbose_name='责任人')),
                ('ticket_ref', models.CharField(blank=True, default='', max_length=160, verbose_name='关联工单')),
                ('detected_at', models.DateTimeField(verbose_name='发现时间')),
                ('resolved_at', models.DateTimeField(blank=True, null=True, verbose_name='解决时间')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('asset', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='threats', to='cloudsecurity.internalsecurityasset', verbose_name='关联资产')),
            ],
            options={'verbose_name': '主机安全威胁', 'verbose_name_plural': '主机安全威胁', 'ordering': ['status', '-severity', '-detected_at', '-id'], 'indexes': [models.Index(fields=['status', 'severity'], name='cloudsec_threat_status_sev'), models.Index(fields=['threat_type', 'detected_at'], name='cloudsec_threat_type_time')]},
        ),
        migrations.RunPython(seed_security_posture, migrations.RunPython.noop),
    ]
