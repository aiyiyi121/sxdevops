from django.db import migrations, models
import django.db.models.deletion


CONTROLS = [
    ('archery', '生产数据库', '生产库按库、表和操作类型授权', '查询、导出、DDL/DML 分离审批；默认不授予生产写权限，设置单次查询行数和导出量限制。', '保留登录、工单、SQL、审批、执行、导出与下载记录；每月复核生产库权限、导出记录和高危 SQL。'),
    ('registry', '生产仓库', '制品发布与标签保护', '生产仓库仅允许 CI 服务账号或指定发布账号推送；普通用户默认只读，关闭匿名访问，生产版本禁止覆盖。', '记录拉取、推送、删除、标签覆盖、权限和 Token 变更；每月复核生产仓库推送权限、机器人账号和异常下载。'),
    ('jenkins', '生产发布', 'Job、Credentials 与 Agent 权限分离', '按 Folder/项目授权；生产发布 Job 仅授权发布人员；凭据统一存入 Credentials，限制脚本审批绕过。', '记录登录、Job 配置、凭据、插件、Agent、构建和发布操作；每月复核管理员、生产 Job 权限和凭据。'),
    ('kubernetes', '生产 Namespace', 'RBAC 与高危能力限制', '禁止共享 kubeconfig；限制 cluster-admin、exec、port-forward、Secret 读取及特权容器、宿主机挂载。', '保存 API Audit Log；每月复核 cluster-admin、RoleBinding、长期 Token、生产 Namespace 写权限和 Secret 读取权限。'),
    ('nacos', '生产命名空间', '生产配置发布与敏感配置管控', '开启认证，按环境、应用和命名空间授权；生产配置发布、回滚关联变更单，禁止配置中明文保存敏感信息。', '记录登录、发布、回滚、删除、命名空间和权限变更；每月复核生产配置权限和高敏配置变更。'),
    ('third_party', 'API Key / ServiceAccount', '账号与密钥台账和轮换', '登记系统、用途、责任人、权限、创建日期、到期日和轮换记录；设置最小 Scope、来源限制和有效期。', '每月将台账与实际账号核对；离职转岗及时回收；发现泄露立即禁用或轮换并核查调用日志。'),
    ('aliyun', 'RAM / 资源组', 'RAM 子账号、MFA 与高危操作审批', '使用 RAM 子账号和角色，禁止日常使用主账号；管理员启用 MFA，禁止长期高权限 AccessKey，高危操作实行审批。', '保存 ActionTrail、RAM 登录和操作日志；每月复核 RAM 管理员、AccessKey、角色信任策略、MFA、异常登录和高危操作。'),
]


def seed_controls(apps, schema_editor):
    Control = apps.get_model('cloudsecurity', 'InternalPlatformSecurityControl')
    Finding = apps.get_model('cloudsecurity', 'InternalPlatformSecurityFinding')
    controls = []
    for index, (platform, scope, title, requirement, evidence_requirement) in enumerate(CONTROLS, start=1):
        control, _ = Control.objects.get_or_create(
            platform=platform,
            title=title,
            defaults={
                'scope': scope,
                'requirement': requirement,
                'evidence_requirement': evidence_requirement,
                'sort_order': index * 10,
            },
        )
        controls.append(control)
    initial_findings = [
        (2, 'Jenkins 生产发布 Job 权限待复核', 'high', 'CI/CD 负责人', '核对生产 Folder 权限、管理员和 Credentials 使用范围，补充复核证据。'),
        (3, 'Kubernetes 长期 ServiceAccount Token 待清理', 'critical', '容器平台组', '识别长期 Token 与生产 Namespace 高权限绑定，完成替换或回收。'),
        (0, 'Archery 生产数据导出记录待核对', 'medium', '数据库负责人', '核对导出审批、范围、接收人和保存期限，异常项转为单独整改。'),
        (6, '阿里云 RAM 管理员 MFA 状态待确认', 'high', '云平台组', '核对 RAM 管理员 MFA、长期 AccessKey 与角色信任策略。'),
    ]
    for control_index, title, severity, owner, description in initial_findings:
        control = controls[control_index]
        Finding.objects.get_or_create(
            control=control,
            title=title,
            defaults={
                'platform': control.platform,
                'scope': control.scope,
                'description': description,
                'severity': severity,
                'owner': owner,
                'created_by': 'system',
            },
        )
    for control in controls:
        Finding.objects.get_or_create(
            control=control,
            finding_type='monthly_review',
            title=f'{control.get_platform_display()} 月度权限与审计复核',
            defaults={
                'platform': control.platform,
                'scope': control.scope,
                'description': f'按控制基线复核：{control.evidence_requirement}',
                'severity': 'medium',
                'owner': '运维组',
                'created_by': 'system',
            },
        )


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='InternalPlatformSecurityControl',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('platform', models.CharField(choices=[('archery', 'Archery'), ('registry', '镜像仓库 / Nexus'), ('jenkins', 'Jenkins'), ('kubernetes', 'Kubernetes'), ('nacos', 'Nacos'), ('third_party', '第三方服务账号'), ('aliyun', '阿里云账号')], max_length=32, verbose_name='平台')),
                ('scope', models.CharField(max_length=160, verbose_name='适用范围')),
                ('title', models.CharField(max_length=160, verbose_name='控制项')),
                ('requirement', models.TextField(verbose_name='控制要求')),
                ('evidence_requirement', models.TextField(verbose_name='留痕与复核要求')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='排序')),
                ('enabled', models.BooleanField(default=True, verbose_name='启用')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={'verbose_name': '内部平台安全控制项', 'verbose_name_plural': '内部平台安全控制项', 'ordering': ['sort_order', 'platform', 'id']},
        ),
        migrations.CreateModel(
            name='InternalPlatformSecurityFinding',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('finding_type', models.CharField(choices=[('rectification', '整改项'), ('monthly_review', '月度复核')], default='rectification', max_length=24, verbose_name='类型')),
                ('platform', models.CharField(choices=[('archery', 'Archery'), ('registry', '镜像仓库 / Nexus'), ('jenkins', 'Jenkins'), ('kubernetes', 'Kubernetes'), ('nacos', 'Nacos'), ('third_party', '第三方服务账号'), ('aliyun', '阿里云账号')], max_length=32, verbose_name='平台')),
                ('scope', models.CharField(blank=True, default='', max_length=160, verbose_name='影响范围')),
                ('title', models.CharField(max_length=200, verbose_name='标题')),
                ('description', models.TextField(blank=True, default='', verbose_name='问题描述')),
                ('severity', models.CharField(choices=[('critical', '严重'), ('high', '高'), ('medium', '中'), ('low', '低')], default='medium', max_length=16, verbose_name='严重程度')),
                ('status', models.CharField(choices=[('pending', '待处理'), ('in_progress', '整改中'), ('pending_review', '待复核'), ('closed', '已关闭'), ('ignored', '已忽略')], default='pending', max_length=24, verbose_name='状态')),
                ('owner', models.CharField(blank=True, default='', max_length=80, verbose_name='责任人')),
                ('due_date', models.DateField(blank=True, null=True, verbose_name='截止日期')),
                ('ticket_ref', models.CharField(blank=True, default='', max_length=200, verbose_name='工单号或链接')),
                ('evidence', models.TextField(blank=True, default='', verbose_name='证据或复核说明')),
                ('created_by', models.CharField(blank=True, default='', max_length=150, verbose_name='创建人')),
                ('closed_by', models.CharField(blank=True, default='', max_length=150, verbose_name='关闭人')),
                ('closed_at', models.DateTimeField(blank=True, null=True, verbose_name='关闭时间')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('control', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='findings', to='cloudsecurity.internalplatformsecuritycontrol', verbose_name='关联控制项')),
            ],
            options={'verbose_name': '内部平台安全整改项', 'verbose_name_plural': '内部平台安全整改项', 'ordering': ['status', 'due_date', '-updated_at', '-id']},
        ),
        migrations.CreateModel(
            name='InternalPlatformSecurityActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(max_length=40, verbose_name='动作')),
                ('message', models.TextField(blank=True, default='', verbose_name='说明')),
                ('actor', models.CharField(blank=True, default='', max_length=150, verbose_name='操作人')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('finding', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activities', to='cloudsecurity.internalplatformsecurityfinding', verbose_name='整改项')),
            ],
            options={'verbose_name': '内部平台安全整改记录', 'verbose_name_plural': '内部平台安全整改记录', 'ordering': ['-created_at', '-id']},
        ),
        migrations.RunPython(seed_controls, migrations.RunPython.noop),
    ]
