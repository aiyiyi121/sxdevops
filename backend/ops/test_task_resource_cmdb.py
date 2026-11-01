from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from cmdb.models import CIResourceAuthorization, CIType, ConfigItem, ResourceNode
from ops.host_tasks import TaskResourceHostTarget, open_ssh_client
from ops.models import K8sCluster, TaskResource, TaskResourceGroup
from rbac.models import PermissionDefinition, Role
from rbac.services import ensure_builtin_rbac


class TaskResourceCmdbTests(TestCase):
    def setUp(self):
        ensure_builtin_rbac()
        self.user = get_user_model().objects.create_superuser('resource-admin', password='test-password')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.ci_type, _ = CIType.objects.get_or_create(code='VIRTUAL_MACHINE', defaults={'name': '测试虚拟机'})
        self.environment = TaskResourceGroup.objects.create(name='执行测试环境', group_type='environment')

    def asset(self, **values):
        defaults = {'name': 'cmdb-vm-01', 'ci_type': self.ci_type, 'attributes': {}}
        defaults.update(values)
        return ConfigItem.objects.create(**defaults)

    def connect(self, config_item, **values):
        payload = {'cmdb_ci': config_item.pk, 'environment': self.environment.pk, 'ip_address': '10.11.12.13'}
        payload.update(values)
        return self.client.post('/api/task-resources/', payload, format='json')

    def test_unconnected_assets_only_appear_in_picker(self):
        config_item = self.asset()
        options = self.client.get('/api/task-resources/cmdb-options/').json()['results']
        self.assertIn(config_item.pk, [item['id'] for item in options])
        self.assertEqual(self.client.get('/api/task-resources/').json()['count'], 0)
        self.assertEqual(self.client.get('/api/task-resources/stats/').json()['total'], 0)
        self.assertFalse(TaskResourceGroup.objects.filter(cmdb_node__isnull=False).exists())

    def test_scope_trees_preserve_cmdb_hierarchy_without_connecting_assets(self):
        business = ResourceNode.objects.create(name='支付业务', node_type='biz')
        environment = ResourceNode.objects.create(name='生产环境', node_type='env', parent=business)
        self.asset(business_node=business, environment_node=environment)
        resource_tree = self.client.get('/api/task-resources/scope-tree/').json()
        picker_tree = self.client.get('/api/task-resources/cmdb-tree/').json()
        resource_business = next(node for node in resource_tree if node['scope_business'] == f'node:{business.pk}')
        picker_business = next(node for node in picker_tree if node['scope_business'] == f'node:{business.pk}')
        self.assertEqual(resource_business['resource_count'], 0)
        self.assertEqual(resource_business['cmdb_node'], business.pk)
        self.assertEqual(resource_business['children'][0]['cmdb_parent'], business.pk)
        self.assertEqual(resource_business['children'][0]['name'], environment.name)
        self.assertEqual(picker_business['resource_count'], 1)
        self.assertEqual(picker_business['children'][0]['scope_environment'], f'node:{environment.pk}')
        self.assertFalse(TaskResource.objects.exists())
        self.assertFalse(TaskResourceGroup.objects.filter(cmdb_node__isnull=False).exists())

    def test_picker_filters_by_business_and_environment_identity(self):
        business = ResourceNode.objects.create(name='支付业务', node_type='biz')
        other_business = ResourceNode.objects.create(name='订单业务', node_type='biz')
        environment = ResourceNode.objects.create(name='生产环境', node_type='env', parent=business)
        other_environment = ResourceNode.objects.create(name='生产环境', node_type='env', parent=other_business)
        staging = ResourceNode.objects.create(name='测试环境', node_type='env', parent=business)
        selected = self.asset(name='payment-prod', business_node=business, environment_node=environment)
        self.asset(name='order-prod', business_node=other_business, environment_node=other_environment)
        self.asset(name='payment-staging', business_node=business, environment_node=staging)
        business_response = self.client.get('/api/task-resources/cmdb-options/', {'scope_business': f'node:{business.pk}'})
        self.assertEqual(business_response.data['count'], 2)
        response = self.client.get('/api/task-resources/cmdb-options/', {
            'scope_business': f'node:{business.pk}', 'scope_environment': f'node:{environment.pk}',
        })
        self.assertEqual([row['id'] for row in response.data['results']], [selected.pk])
        response = self.client.get('/api/task-resources/cmdb-options/', {'scope_business': 'node:invalid'})
        self.assertEqual(response.data['count'], 0)

    def test_resource_tree_counts_and_stats_only_include_connected_resources(self):
        business = ResourceNode.objects.create(name='支付业务', node_type='biz')
        environment = ResourceNode.objects.create(name='生产环境', node_type='env', parent=business)
        config_item = self.asset(business_node=business, environment_node=environment)
        connected = self.connect(config_item, status='warning')
        self.assertEqual(connected.status_code, 201, connected.data)
        self.asset(name='not-connected', business_node=business, environment_node=environment)
        TaskResource.objects.create(name='manual', environment=self.environment, ip_address='10.1.1.2')
        tree = self.client.get('/api/task-resources/scope-tree/').json()
        branch = next(node for node in tree if node['scope_business'] == f'node:{business.pk}')
        self.assertEqual(branch['resource_count'], 1)
        self.assertEqual(branch['children'][0]['resource_count'], 1)
        params = {'scope_business': f'node:{business.pk}', 'scope_environment': f'node:{environment.pk}'}
        response = self.client.get('/api/task-resources/', params)
        self.assertEqual([row['id'] for row in response.data['results']], [connected.data['id']])
        counts = self.client.get('/api/task-resources/stats/', params).json()
        self.assertEqual(counts['total'], 1)
        self.assertEqual(counts['host'], 1)
        self.assertEqual(counts['warning'], 1)

    def test_manual_and_legacy_text_scopes_remain_filterable(self):
        system = TaskResourceGroup.objects.create(name='手工业务', group_type='system', parent=self.environment)
        manual = TaskResource.objects.create(name='manual', environment=self.environment, system=system, ip_address='10.1.1.2')
        unassigned = TaskResource.objects.create(name='unassigned', environment=self.environment, ip_address='10.1.1.3')
        config_item = self.asset(business_line='历史业务', environment='历史环境')
        connected = self.connect(config_item)
        for token, expected in [('name:手工业务', manual.pk), ('unassigned', unassigned.pk), ('name:历史业务', connected.data['id'])]:
            response = self.client.get('/api/task-resources/', {'scope_business': token})
            self.assertEqual([row['id'] for row in response.data['results']], [expected])
        response = self.client.get('/api/task-resources/cmdb-options/', {
            'scope_business': 'name:历史业务', 'scope_environment': 'name:历史环境',
        })
        self.assertEqual([row['id'] for row in response.data['results']], [config_item.pk])
        tree = self.client.get('/api/task-resources/scope-tree/').json()
        self.assertEqual(sum(node['resource_count'] for node in tree), 3)

    def test_resource_trees_stop_at_environments_while_preserving_asset_counts(self):
        business = ResourceNode.objects.create(name='支付业务', node_type='biz')
        production = ResourceNode.objects.create(name='prod', node_type='env', parent=business)
        staging = ResourceNode.objects.create(name='test', node_type='env', parent=business)
        selected = self.asset(name='payment-api', business_node=business, environment_node=production,
                              attributes={'system': '  ', 'business_system': '支付核心'})
        other = self.asset(name='payment-test', business_node=business, environment_node=staging,
                           attributes={'system': '支付核心'})
        self.asset(name='risk-api', business_node=business, environment_node=production,
                   attributes={'app_name': '风控系统'})
        connected = self.connect(selected)
        self.connect(other)

        tree = self.client.get('/api/task-resources/scope-tree/').json()
        branch = next(node for node in tree if node['scope_business'] == f'node:{business.pk}')
        environment = next(node for node in branch['children'] if node['cmdb_node'] == production.pk)
        self.assertEqual(environment['children'], [])
        self.assertTrue(all(not env['children'] for biz in tree for env in biz['children']))
        picker_tree = self.client.get('/api/task-resources/cmdb-tree/').json()
        self.assertTrue(all(not env['children'] for biz in picker_tree for env in biz['children']))
        self.assertEqual(environment['resource_count'], 1)
        self.assertEqual(environment['asset_count'], 2)
        self.assertIn('payment-api', environment['search_names'])
        params = {'scope_business': f'node:{business.pk}', 'scope_environment': f'node:{production.pk}',
                  'scope_system': 'name:支付核心'}
        response = self.client.get('/api/task-resources/', params)
        self.assertEqual([row['id'] for row in response.data['results']], [connected.data['id']])
        self.assertEqual(self.client.get('/api/task-resources/stats/', params).data['total'], 1)
        picker = self.client.get('/api/task-resources/cmdb-options/', params)
        self.assertEqual([row['id'] for row in picker.data['results']], [selected.pk])
        self.assertEqual(self.client.get('/api/task-resources/', {'scope_system': 'node:invalid'}).data['count'], 0)

    def test_linked_resources_follow_current_cmdb_nodes_without_rewriting_connection_groups(self):
        old_business = ResourceNode.objects.create(name='旧业务', node_type='biz')
        old_environment = ResourceNode.objects.create(name='旧环境', node_type='env', parent=old_business)
        business = ResourceNode.objects.create(name='新业务', node_type='biz')
        environment = ResourceNode.objects.create(name='prod', node_type='env', parent=business)
        asset = self.asset(business_node=old_business, environment_node=old_environment)
        connected = self.connect(asset)
        resource = TaskResource.objects.get(pk=connected.data['id'])
        previous_groups = (resource.environment_id, resource.system_id)
        ConfigItem.objects.filter(pk=asset.pk).update(business_node=business, environment_node=environment,
                                                    attributes={'system': '订单系统'})
        params = {'scope_business': f'node:{business.pk}', 'scope_environment': f'node:{environment.pk}',
                  'scope_system': 'name:订单系统'}
        self.assertEqual(self.client.get('/api/task-resources/', params).data['count'], 1)
        self.assertEqual(self.client.get('/api/task-resources/stats/', params).data['total'], 1)
        tree = self.client.get('/api/task-resources/scope-tree/').json()
        branch = next(node for node in tree if node['cmdb_node'] == business.pk)
        self.assertEqual(branch['children'][0]['resource_count'], 1)
        self.assertEqual(branch['children'][0]['children'], [])
        self.assertEqual(self.client.get('/api/task-resources/', {'scope_business': f'node:{old_business.pk}'}).data['count'], 0)
        resource.refresh_from_db()
        self.assertEqual((resource.environment_id, resource.system_id), previous_groups)

    def test_manual_resources_keep_manual_source_and_do_not_create_cmdb_assets(self):
        before = ConfigItem.objects.count()
        response = self.client.post('/api/task-resources/', {
            'name': 'manual-host', 'environment': self.environment.pk,
            'ip_address': '10.1.1.2', 'source_type': 'cmdb',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['source_type'], 'manual')
        self.assertIsNone(response.data['cmdb_ci'])
        self.assertEqual(ConfigItem.objects.count(), before)

    def test_connect_uses_cmdb_values_and_allows_supplements_without_writeback(self):
        config_item = self.asset()
        response = self.connect(config_item, owner='任务负责人', ssh_user='runner', ssh_port=2222, ssh_password='local-secret')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['source_type'], 'cmdb')
        self.assertEqual(response.data['name'], config_item.name)
        self.assertEqual(response.data['owner'], '任务负责人')
        self.assertTrue(response.data['has_ssh_password'])
        self.assertNotIn('ssh_password', response.data)
        config_item.refresh_from_db()
        self.assertEqual(config_item.attributes, {})
        self.assertEqual(config_item.admin_user, '')
        resource = TaskResource.objects.get(pk=response.data['id'])
        self.assertEqual(resource.ssh_user, 'runner')
        self.assertEqual(resource.ssh_port, 2222)

    def test_cmdb_values_override_client_values_and_create_only_selected_groups(self):
        business = ResourceNode.objects.create(name='支付系统', node_type='biz')
        environment = ResourceNode.objects.create(name='联调环境', node_type='env', parent=business)
        config_item = self.asset(business_node=business, environment_node=environment, attributes={'private_ip': '10.20.30.40'})
        response = self.client.post('/api/task-resources/', {'cmdb_ci': config_item.pk, 'name': '伪造名称'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['name'], config_item.name)
        self.assertEqual(response.data['ip_address'], '10.20.30.40')
        self.assertEqual(response.data['environment_name'], environment.name)
        self.assertEqual(response.data['system_name'], business.name)
        self.assertEqual(TaskResourceGroup.objects.get(pk=response.data['environment']).cmdb_node_id, environment.pk)

    def test_asset_updates_refresh_managed_values_and_preserve_execution_settings(self):
        config_item = self.asset()
        response = self.connect(config_item, ssh_user='runner', ssh_password='local-secret', owner='本地补充')
        self.assertEqual(response.status_code, 201, response.data)
        config_item.name = 'cmdb-vm-renamed'
        config_item.attributes = {'private_ip': '10.30.40.50'}
        config_item.save()
        resource = TaskResource.objects.get(pk=response.data['id'])
        self.assertEqual(resource.name, 'cmdb-vm-renamed')
        self.assertEqual(resource.ip_address, '10.30.40.50')
        self.assertEqual(resource.owner, '本地补充')
        self.assertEqual(resource.ssh_user, 'runner')
        self.assertEqual(resource.ssh_password, 'local-secret')

    def test_duplicate_link_and_incompatible_asset_are_rejected(self):
        config_item = self.asset()
        self.assertEqual(self.connect(config_item).status_code, 201)
        self.assertEqual(self.connect(config_item).status_code, 400)
        other_type = CIType.objects.create(code='TEST_DATABASE', name='测试数据库')
        database = self.asset(name='database', ci_type=other_type)
        self.assertEqual(self.connect(database).status_code, 400)

    def test_cmdb_link_cannot_be_cleared_or_replaced(self):
        config_item = self.asset()
        resource_id = self.connect(config_item).data['id']
        other = self.asset(name='other-vm')
        for value in (None, other.pk):
            response = self.client.patch(f'/api/task-resources/{resource_id}/', {'cmdb_ci': value}, format='json')
            self.assertEqual(response.status_code, 400, response.data)

    def test_removing_resource_preserves_asset_and_marks_it_available_for_reconnect(self):
        config_item = self.asset()
        response = self.connect(config_item)
        self.assertEqual(self.client.delete(f"/api/task-resources/{response.data['id']}/").status_code, 204)
        self.assertTrue(ConfigItem.objects.filter(pk=config_item.pk).exists())
        options = self.client.get('/api/task-resources/cmdb-options/').json()['results']
        self.assertFalse(next(item for item in options if item['id'] == config_item.pk)['connected'])

    def test_deleted_source_preserves_resource_and_blocks_execution(self):
        config_item = self.asset()
        response = self.connect(config_item)
        config_item.delete()
        resource = TaskResource.objects.get(pk=response.data['id'])
        self.assertIsNone(resource.cmdb_ci_id)
        self.assertEqual(resource.source_type, 'cmdb')
        with patch('ops.host_tasks.paramiko.SSHClient') as ssh_client:
            with self.assertRaisesMessage(ValueError, '关联 CMDB 资产已删除'):
                open_ssh_client(TaskResourceHostTarget(resource), 10)
            ssh_client.assert_not_called()

    def test_stopped_source_blocks_new_task_submission(self):
        config_item = self.asset(status='stopped')
        response = self.connect(config_item)
        self.assertEqual(response.status_code, 201, response.data)
        response = self.client.post('/api/host-tasks/', {
            'name': 'test-offline-source', 'task_type': 'check_connection',
            'resource_ids': [response.data['id']],
        }, format='json')
        self.assertEqual(response.status_code, 400, response.data)

    def test_picker_and_binding_respect_cmdb_resource_scope(self):
        user = get_user_model().objects.create_user('scoped-operator', password='test-password')
        role = Role.objects.create(code='scoped-resource', name='范围内资源接入')
        role.permissions.add(*PermissionDefinition.objects.filter(code__in=[
            'ops.task.resource.manage', 'ops.task.resource.view', 'cmdb.ci.view',
        ]))
        role.users.add(user)
        CIResourceAuthorization.objects.create(principal_type='user', principal=user.username, permission='view', business_line='allowed')
        allowed = self.asset(name='allowed-vm', business_line='allowed', attributes={'system': 'allowed-system'})
        forbidden = self.asset(name='forbidden-vm', business_line='forbidden', attributes={'system': 'hidden-system'})
        self.client.force_authenticate(user)
        response = self.client.get('/api/task-resources/cmdb-options/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(allowed.pk, [item['id'] for item in response.data['results']])
        self.assertNotIn(forbidden.pk, [item['id'] for item in response.data['results']])
        tree = self.client.get('/api/task-resources/cmdb-tree/').json()
        self.assertEqual(sum(node['resource_count'] for node in tree), 1)
        self.assertFalse(any(node['name'] == 'forbidden' for node in tree))
        scope_tree = self.client.get('/api/task-resources/scope-tree/').json()
        self.assertNotIn('hidden-system', str(scope_tree))
        self.assertNotIn('forbidden-vm', str(scope_tree))
        self.assertIn('allowed-vm', str(scope_tree))
        response = self.client.get('/api/task-resources/cmdb-options/', {'scope_business': 'name:forbidden'})
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(self.connect(forbidden).status_code, 403)

    def test_resource_management_without_cmdb_view_cannot_use_picker_or_bind(self):
        user = get_user_model().objects.create_user('resource-only', password='test-password')
        role = Role.objects.create(code='resource-only', name='仅资源管理')
        role.permissions.add(PermissionDefinition.objects.get(code='ops.task.resource.manage'))
        role.users.add(user)
        config_item = self.asset()
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get('/api/task-resources/cmdb-options/').status_code, 403)
        self.assertEqual(self.client.get('/api/task-resources/cmdb-tree/').status_code, 403)
        self.assertEqual(self.connect(config_item).status_code, 403)

    def test_k8s_asset_requires_existing_cluster_connection(self):
        ci_type, _ = CIType.objects.get_or_create(code='K8S_CLUSTER', defaults={'name': '测试 K8s 集群'})
        config_item = self.asset(name='cmdb-cluster', ci_type=ci_type)
        response = self.connect(config_item, resource_type='k8s')
        self.assertEqual(response.status_code, 400)
        cluster = K8sCluster.objects.create(name='runtime-cluster', api_server='https://127.0.0.1:6443')
        response = self.connect(config_item, resource_type='k8s', cluster=cluster.pk)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['name'], config_item.name)
        self.assertEqual(response.data['cluster'], cluster.pk)
