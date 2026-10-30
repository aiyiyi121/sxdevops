from django.db import migrations, models
import django.db.models.deletion


def _normalize_environment(value):
    text = str(value or '').strip().lower()
    aliases = {
        'prod': 'prod',
        'production': 'prod',
        '生产': 'prod',
        '生产环境': 'prod',
        'test': 'test',
        'testing': 'test',
        '测试': 'test',
        '测试环境': 'test',
        'dev': 'dev',
        'develop': 'dev',
        'development': 'dev',
        '开发': 'dev',
        '开发环境': 'dev',
    }
    return aliases.get(text, text)


def link_existing_config_items(apps, schema_editor):
    ConfigItem = apps.get_model('cmdb', 'ConfigItem')
    ResourceNode = apps.get_model('cmdb', 'ResourceNode')
    business_nodes = {}
    for node in ResourceNode.objects.filter(node_type='biz', parent__isnull=True).only('id', 'name'):
        business_nodes.setdefault(node.name, []).append(node)

    for item in ConfigItem.objects.all().only('id', 'business_line', 'environment'):
        candidates = business_nodes.get(item.business_line or '', [])
        if len(candidates) != 1:
            continue
        business_node = candidates[0]
        updates = {'business_node_id': business_node.id}
        environment_candidates = [
            node
            for node in ResourceNode.objects.filter(node_type='env', parent_id=business_node.id).only('id', 'name')
            if _normalize_environment(node.name) == _normalize_environment(item.environment)
        ]
        if len(environment_candidates) == 1:
            updates['environment_node_id'] = environment_candidates[0].id
        ConfigItem.objects.filter(pk=item.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0020_rename_external_group_to_other_assets'),
    ]

    operations = [
        migrations.AddField(
            model_name='configitem',
            name='business_node',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='business_config_items', to='cmdb.resourcenode', verbose_name='业务线节点'),
        ),
        migrations.AddField(
            model_name='configitem',
            name='environment_node',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='environment_config_items', to='cmdb.resourcenode', verbose_name='环境节点'),
        ),
        migrations.RunPython(link_existing_config_items, migrations.RunPython.noop),
    ]
