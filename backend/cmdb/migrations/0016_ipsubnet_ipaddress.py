from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0015_resourcenode_is_synced'),
    ]

    operations = [
        migrations.CreateModel(
            name='IPSubnet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='子网名称')),
                ('cidr', models.CharField(max_length=50, unique=True, verbose_name='CIDR')),
                ('vlan_name', models.CharField(blank=True, default='', max_length=100, verbose_name='VLAN / Port Group')),
                ('gateway', models.CharField(blank=True, default='', max_length=45, verbose_name='网关')),
                ('description', models.CharField(blank=True, default='', max_length=200, verbose_name='说明')),
                ('excluded_addresses', models.JSONField(blank=True, default=list, verbose_name='保留地址')),
                ('last_scanned_at', models.DateTimeField(blank=True, null=True, verbose_name='最近扫描时间')),
                ('created_by', models.CharField(blank=True, default='', max_length=80, verbose_name='创建人')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['cidr', 'id']},
        ),
        migrations.CreateModel(
            name='IPAddress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('address', models.CharField(max_length=45, verbose_name='IP 地址')),
                ('status', models.CharField(choices=[('available', '空闲'), ('in_use', '使用中'), ('offline', '停机'), ('reserved', '已保留')], default='available', max_length=20, verbose_name='地址状态')),
                ('reachability', models.CharField(choices=[('unknown', '未扫描'), ('reachable', '可达'), ('unreachable', '不通')], default='unknown', max_length=20, verbose_name='扫描状态')),
                ('linked_ci_names', models.JSONField(blank=True, default=list, verbose_name='关联资产')),
                ('note', models.CharField(blank=True, default='', max_length=200, verbose_name='备注')),
                ('last_scanned_at', models.DateTimeField(blank=True, null=True, verbose_name='最近扫描时间')),
                ('created_by', models.CharField(blank=True, default='', max_length=80, verbose_name='创建人')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('ci', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ip_addresses', to='cmdb.configitem')),
                ('subnet', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='addresses', to='cmdb.ipsubnet')),
            ],
            options={'ordering': ['subnet_id', 'address']},
        ),
        migrations.AddConstraint(
            model_name='ipaddress',
            constraint=models.UniqueConstraint(fields=('subnet', 'address'), name='cmdb_ipaddress_unique_subnet_ip'),
        ),
        migrations.AddIndex(
            model_name='ipaddress',
            index=models.Index(fields=['subnet', 'status'], name='cmdb_ip_subnet_status_idx'),
        ),
    ]
