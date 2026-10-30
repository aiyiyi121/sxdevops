from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0006_citag_configitem_tags'),
    ]

    operations = [
        migrations.CreateModel(
            name='CIResourceAuthorization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='授权名称')),
                ('principal_type', models.CharField(choices=[('user', '用户'), ('group', '用户组')], max_length=20, verbose_name='授权主体类型')),
                ('principal', models.CharField(max_length=150, verbose_name='授权主体')),
                ('permission', models.CharField(choices=[('view', '查看'), ('manage', '管理')], default='view', max_length=20, verbose_name='授权权限')),
                ('business_line', models.CharField(blank=True, default='', max_length=50, verbose_name='业务线')),
                ('environment', models.CharField(blank=True, default='', max_length=20, verbose_name='环境')),
                ('description', models.CharField(blank=True, default='', max_length=200, verbose_name='说明')),
                ('is_active', models.BooleanField(default=True, verbose_name='启用')),
                ('created_by', models.CharField(blank=True, default='', max_length=80, verbose_name='创建人')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('ci_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='resource_authorizations', to='cmdb.citype')),
            ],
            options={
                'ordering': ['-updated_at', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='ciresourceauthorization',
            constraint=models.UniqueConstraint(fields=('principal_type', 'principal', 'permission', 'business_line', 'environment', 'ci_type'), name='cmdb_resource_auth_unique_scope'),
        ),
    ]
