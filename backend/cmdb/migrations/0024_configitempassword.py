from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0023_backfill_cloud_resource_tree_links'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfigItemPassword',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username', models.CharField(blank=True, default='', max_length=150, verbose_name='登录用户名')),
                ('password_ciphertext', models.TextField(verbose_name='密码密文')),
                ('remark', models.CharField(blank=True, default='', max_length=255, verbose_name='备注')),
                ('created_by', models.CharField(blank=True, default='', max_length=150, verbose_name='创建人')),
                ('updated_by', models.CharField(blank=True, default='', max_length=150, verbose_name='更新人')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('config_item', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='login_password', to='cmdb.configitem', verbose_name='关联资产')),
            ],
            options={
                'ordering': ['-updated_at', '-id'],
            },
        ),
    ]
