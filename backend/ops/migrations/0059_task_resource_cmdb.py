from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('cmdb', '0046_sync_we_integration_service_inventory'),
        ('ops', '0058_add_vulnerability_transaction_ticket_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='taskresource', name='source_type',
            field=models.CharField(choices=[('manual', '手工添加'), ('cmdb', 'CMDB 接入')], default='manual', max_length=16, verbose_name='资源来源'),
        ),
        migrations.AddField(
            model_name='taskresource', name='cmdb_ci',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='task_resource', to='cmdb.configitem', verbose_name='关联 CMDB 资产'),
        ),
        migrations.AddField(
            model_name='taskresourcegroup', name='cmdb_node',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='task_resource_groups', to='cmdb.resourcenode', verbose_name='CMDB 归属节点'),
        ),
    ]
