import json
from decimal import Decimal
import io
from unittest.mock import patch
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from rbac.models import PermissionDefinition, Role, UserGroup
from rbac.services import ensure_builtin_rbac
from ops.models import Host
from multicloud.models import CloudCredential

from .builtins import ensure_builtin_cmdb
from .demo_seed import seed_cmdb_demo
from .serializers import ConfigItemSerializer
from .views import PHASE_ONE_ALIYUN_MIDDLEWARE_CODES, PHASE_ONE_REQUIRED_SYNC_TYPES
from .models import (
    CIArchiveCandidate,
    CIChangeLog,
    CICompletionIssue,
    CIField,
    CIModelGroup,
    CIRelationRule,
    CIResourceMetricSnapshot,
    CIResourceAuthorization,
    CISourceMapping,
    CISyncJob,
    CISyncRecord,
    CITag,
    CIThresholdPolicy,
    CIType,
    CIRelation,
    ConfigItem,
    CostOptimizationProgress,
    CostOptimizationTask,
    CostRecord,
    IPAddress,
    IPSubnet,
    ResourceNode,
    ResourceRequest,
)


def _garbled_utf8_as_gbk(value):
    return value.encode('utf-8').decode('gbk', errors='ignore')


def _ci_type(name, **defaults):
    ci_type, _ = CIType.objects.get_or_create(name=name, defaults=defaults)
    changed = False
    for field, value in defaults.items():
        if value not in (None, '') and getattr(ci_type, field) in (None, ''):
            setattr(ci_type, field, value)
            changed = True
    if changed:
        ci_type.save()
    return ci_type


class AuthenticatedTestCase(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = get_user_model().objects.create_superuser('cmdb-admin', 'cmdb@example.com', 'Admin@123456')
        self.client.force_login(self.user)


class IPAddressManagementTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.ci_type = CIType.objects.create(name='Virtual Machine')
        self.subnet = IPSubnet.objects.create(name='应用网络', cidr='10.20.1.0/30')

    def test_address_pool_keeps_stopped_cmdb_asset_offline(self):
        stopped_ci = ConfigItem.objects.create(
            name='stopped-vm-01',
            ci_type=self.ci_type,
            status='idle',
            attributes={'private_ip': '10.20.1.1', 'instance_status': 'Stopped'},
        )

        response = self.client.get(f'/api/cmdb/ip-subnets/{self.subnet.id}/addresses/')

        self.assertEqual(response.status_code, 200)
        rows = {item['address']: item for item in response.data['items']}
        self.assertEqual(rows['10.20.1.1']['status'], 'offline')
        self.assertEqual(rows['10.20.1.1']['ci_id'], stopped_ci.id)

    @patch('cmdb.views._probe_ip', return_value=False)
    def test_scan_marks_runtime_stopped_cmdb_asset_offline(self, probe_ip):
        normal_ci = ConfigItem.objects.create(
            name='runtime-stopped-vm-01',
            ci_type=self.ci_type,
            status='idle',
            attributes={'private_ip': '10.20.1.1', 'instance_status': 'Stopped'},
        )

        response = self.client.post(f'/api/cmdb/ip-subnets/{self.subnet.id}/scan/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['offline'], 1)
        self.assertEqual(IPAddress.objects.get(subnet=self.subnet, address='10.20.1.1').status, 'offline')
        self.assertEqual(probe_ip.call_count, 2)

    @patch('cmdb.views._probe_ip', return_value=False)
    def test_scan_marks_unregistered_unreachable_address_available(self, probe_ip):
        response = self.client.post(f'/api/cmdb/ip-subnets/{self.subnet.id}/scan/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['available'], 2)
        self.assertEqual(IPAddress.objects.filter(subnet=self.subnet, status='available').count(), 2)
        self.assertEqual(probe_ip.call_count, 2)


class ConfigItemLedgerFilteringTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.ci_type = CIType.objects.create(name='Ledger Virtual Machine', code='LEDGER_VIRTUAL_MACHINE')

    def test_stopped_filter_matches_runtime_stopped_assets(self):
        displayed_as_stopped = ConfigItem.objects.create(
            name='runtime-stopped-vm',
            ci_type=self.ci_type,
            status='idle',
            attributes={'instance_status': 'Stopped'},
        )
        manually_stopped = ConfigItem.objects.create(
            name='manually-stopped-vm',
            ci_type=self.ci_type,
            status='stopped',
        )
        ConfigItem.objects.create(
            name='running-vm',
            ci_type=self.ci_type,
            status='active',
            attributes={'instance_status': 'Running'},
        )

        response = self.client.get('/api/cmdb/config-items/', {'status': 'stopped'})

        self.assertEqual(response.status_code, 200)
        result_ids = {item['id'] for item in response.data['results']}
        self.assertEqual(result_ids, {displayed_as_stopped.id, manually_stopped.id})

    def test_missing_mapping_rekeys_when_same_resource_reappears_with_new_id(self):
        ci = ConfigItem.objects.create(
            name='rekeyed-vm',
            ci_type=self.ci_type,
            status='offline',
            attributes={'instance_id': 'old-vm-id'},
        )
        mapping = CISourceMapping.objects.create(
            ci=ci,
            source_type='vsphere_vm',
            source_account='vcenter-prod',
            source_region='Datacenter',
            source_unique_id='old-vm-id',
            sync_status='missing',
        )
        candidate = CIArchiveCandidate.objects.create(ci=ci, source_type='vsphere_vm', status='pending')

        from .views import _upsert_config_item_from_payload

        result = _upsert_config_item_from_payload({
            'name': 'rekeyed-vm',
            'ci_type_code': self.ci_type.code,
            'source_type': 'vsphere_vm',
            'source_account': 'vcenter-prod',
            'source_region': 'Datacenter',
            'source_unique_id': 'new-vm-id',
            'attributes': {'instance_id': 'new-vm-id', 'instance_status': 'Running'},
        })

        self.assertEqual(result['ci'].id, ci.id)
        self.assertEqual(ConfigItem.objects.filter(name='rekeyed-vm').count(), 1)
        mapping.refresh_from_db()
        candidate.refresh_from_db()
        ci.refresh_from_db()
        self.assertEqual(mapping.source_unique_id, 'new-vm-id')
        self.assertEqual(mapping.sync_status, 'success')
        self.assertEqual(ci.status, 'active')
        self.assertEqual(candidate.status, 'restored')

    def test_resource_node_links_keep_assets_under_a_renamed_business_node(self):
        business_node = ResourceNode.objects.create(name='第三方服务', node_type='biz')
        environment_node = ResourceNode.objects.create(name='生产', node_type='env', parent=business_node)
        ci = ConfigItem.objects.create(
            name='office-phone',
            ci_type=self.ci_type,
            business_node=business_node,
            environment_node=environment_node,
            business_line=business_node.name,
            environment='prod',
        )

        business_node.name = '其他资产'
        business_node.save(update_fields=['name'])

        response = self.client.get('/api/cmdb/config-items/', {'business_node': business_node.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['id'] for item in response.data['results']], [ci.id])
        self.assertEqual(response.data['results'][0]['business_node_name'], '其他资产')

        tree_response = self.client.get('/api/cmdb/config-items/ledger-tree/', {'business_node': business_node.id})
        self.assertEqual(tree_response.status_code, 200)
        self.assertEqual(tree_response.data[0]['business_node'], business_node.id)
        self.assertEqual(tree_response.data[0]['business_node_name'], '其他资产')

    def test_environment_node_name_is_accepted_for_ledger_filtering(self):
        business_node = ResourceNode.objects.create(name='WE平台', node_type='biz')
        environment_node = ResourceNode.objects.create(name='集成', node_type='env', parent=business_node)
        ci = ConfigItem.objects.create(
            name='integration-nacos',
            ci_type=self.ci_type,
            business_node=business_node,
            environment_node=environment_node,
            business_line=business_node.name,
            environment=environment_node.name,
        )

        by_node_response = self.client.get('/api/cmdb/config-items/', {'environment_node': environment_node.id})
        self.assertEqual(by_node_response.status_code, 200, by_node_response.content)
        self.assertEqual([item['id'] for item in by_node_response.data['results']], [ci.id])

        by_name_response = self.client.get('/api/cmdb/config-items/', {'environment': environment_node.name})
        self.assertEqual(by_name_response.status_code, 200, by_name_response.content)
        self.assertEqual([item['id'] for item in by_name_response.data['results']], [ci.id])

    def test_editing_config_item_syncs_business_and_environment_from_resource_nodes(self):
        original_business_node = ResourceNode.objects.create(name='原业务线', node_type='biz')
        original_environment_node = ResourceNode.objects.create(name='开发', node_type='env', parent=original_business_node)
        target_business_node = ResourceNode.objects.create(name='目标业务线', node_type='biz')
        target_environment_node = ResourceNode.objects.create(name='生产', node_type='env', parent=target_business_node)
        ci = ConfigItem.objects.create(
            name='editable-resource',
            ci_type=self.ci_type,
            business_node=original_business_node,
            environment_node=original_environment_node,
            business_line=original_business_node.name,
            environment='dev',
        )

        response = self.client.put(
            f'/api/cmdb/config-items/{ci.id}/',
            {
                'name': ci.name,
                'ci_type': self.ci_type.id,
                'business_node': target_business_node.id,
                'environment_node': target_environment_node.id,
                'admin_user': '',
                'status': 'active',
                'attributes': {},
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['business_line'], target_business_node.name, response.data)
        self.assertEqual(response.data['environment'], target_environment_node.name, response.data)
        ci.refresh_from_db()
        self.assertEqual(ci.business_node_id, target_business_node.id)
        self.assertEqual(ci.business_line, target_business_node.name)
        self.assertEqual(ci.environment_node_id, target_environment_node.id)
        self.assertEqual(ci.environment, target_environment_node.name)

    def test_cloud_resource_node_links_keep_assets_under_a_renamed_node(self):
        resource_node = ResourceNode.objects.create(name='第三方服务', node_type='cloud_account')
        first = ConfigItem.objects.create(
            name='weather-service',
            ci_type=self.ci_type,
            resource_node=resource_node,
            attributes={'source_account': '第三方服务', 'resource_node_id': resource_node.id},
        )
        second = ConfigItem.objects.create(
            name='map-service',
            ci_type=self.ci_type,
            resource_node=resource_node,
            attributes={'source_account': '第三方服务', 'resource_node_id': resource_node.id},
        )

        resource_node.name = '其他资产'
        resource_node.save(update_fields=['name'])

        response = self.client.get('/api/cmdb/config-items/', {'resource_node': resource_node.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item['id'] for item in response.data['results']}, {first.id, second.id})

        tree_response = self.client.get('/api/cmdb/config-items/ledger-tree/', {'resource_node': resource_node.id})
        self.assertEqual(tree_response.status_code, 200)
        self.assertEqual({item['resource_node'] for item in tree_response.data}, {resource_node.id})
        self.assertEqual({item['resource_node_name'] for item in tree_response.data}, {'其他资产'})

    def test_cloud_account_filter_includes_assets_linked_to_descendant_nodes(self):
        account_node = ResourceNode.objects.create(name='example-ali', node_type='cloud_account')
        region_node = ResourceNode.objects.create(name='cn-hangzhou', node_type='cloud_region', parent=account_node)
        cluster_node = ResourceNode.objects.create(name='ecs-cluster', node_type='cloud_cluster', parent=region_node)
        ecs = ConfigItem.objects.create(
            name='example-ecs-01',
            ci_type=self.ci_type,
            resource_node=region_node,
            attributes={'resource_node_id': region_node.id},
        )
        nested_resource = ConfigItem.objects.create(
            name='example-ecs-02',
            ci_type=self.ci_type,
            resource_node=cluster_node,
            attributes={'resource_node_id': cluster_node.id},
        )

        response = self.client.get('/api/cmdb/config-items/', {'resource_node': account_node.id})

        self.assertEqual(response.status_code, 200)
        result_ids = {item['id'] for item in response.data['results']}
        self.assertEqual(result_ids, {ecs.id, nested_resource.id})

    def test_asset_item_filter_returns_assets_linked_to_other_assets_node(self):
        other_assets_node = ResourceNode.objects.create(name='其他资产', node_type='cloud_account')
        asset_item_type = CIType.objects.create(name='资产物品筛选测试', code='TEST_ASSET_ITEM_FILTER')
        asset_item = ConfigItem.objects.create(
            name='公共手机',
            ci_type=asset_item_type,
            resource_node=other_assets_node,
            attributes={'resource_node_id': other_assets_node.id},
        )

        response = self.client.get('/api/cmdb/config-items/', {
            'resource_node': other_assets_node.id,
            'ci_type': asset_item_type.id,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['id'] for item in response.data['results']], [asset_item.id])

    def test_sync_links_source_account_and_region_to_cloud_tree_node(self):
        account_node = ResourceNode.objects.create(name='sync-account', node_type='cloud_account', is_synced=True)
        from .views import _upsert_config_item_from_payload

        result = _upsert_config_item_from_payload({
            'name': 'sync-tree-vm',
            'ci_type_code': self.ci_type.code,
            'source_type': 'aliyun_ecs',
            'source_account': 'sync-account',
            'source_region': 'cn-hangzhou',
            'source_unique_id': 'sync-tree-vm-001',
        })

        resource_node = result['ci'].resource_node
        self.assertIsNotNone(resource_node)
        self.assertEqual(resource_node.node_type, 'cloud_region')
        self.assertEqual(resource_node.parent_id, account_node.id)
        self.assertEqual(resource_node.name, 'cn-hangzhou')
        self.assertEqual(result['ci'].attributes['resource_node_id'], resource_node.id)


class ConfigItemSyncIPRetentionTests(TestCase):
    def test_sync_keeps_last_valid_ip_when_source_reports_empty_ip(self):
        ci_type = CIType.objects.create(name='Sync IP Retention VM', code='SYNC_IP_RETENTION_VM')
        ci = ConfigItem.objects.create(
            name='ip-retention-vm',
            ci_type=ci_type,
            attributes={'private_ip': '10.20.1.10'},
        )
        CISourceMapping.objects.create(
            ci=ci,
            source_type='vsphere_vm',
            source_account='vcenter-prod',
            source_region='Datacenter',
            source_unique_id='vm-ip-retention-01',
        )

        from .views import _upsert_config_item_from_payload

        _upsert_config_item_from_payload({
            'name': 'ip-retention-vm',
            'ci_type_code': ci_type.code,
            'source_type': 'vsphere_vm',
            'source_account': 'vcenter-prod',
            'source_region': 'Datacenter',
            'source_unique_id': 'vm-ip-retention-01',
            'attributes': {'private_ip': '', 'instance_status': 'Stopped'},
        })

        ci.refresh_from_db()
        self.assertEqual(ci.attributes['private_ip'], '10.20.1.10')
        self.assertEqual(ci.attributes['instance_status'], 'Stopped')

    def test_sync_ignores_small_numeric_attribute_variance(self):
        ci_type = CIType.objects.create(name='Disk Rounding VM', code='DISK_ROUNDING_VM')
        ci = ConfigItem.objects.create(
            name='disk-rounding-vm',
            ci_type=ci_type,
            attributes={
                'disk_gb': 5245.74,
                'source_type': 'vsphere_vm',
                'source_account': 'vcenter-prod',
                'source_region': 'Datacenter',
                'source_unique_id': 'disk-rounding-vm-01',
            },
        )
        CISourceMapping.objects.create(
            ci=ci,
            source_type='vsphere_vm',
            source_account='vcenter-prod',
            source_region='Datacenter',
            source_unique_id='disk-rounding-vm-01',
        )

        from .views import _upsert_config_item_from_payload

        result = _upsert_config_item_from_payload({
            'name': ci.name,
            'ci_type_code': ci_type.code,
            'source_type': 'vsphere_vm',
            'source_account': 'vcenter-prod',
            'source_region': 'Datacenter',
            'source_unique_id': 'disk-rounding-vm-01',
            'attributes': {'disk_gb': 5245.63},
        })

        ci.refresh_from_db()
        self.assertEqual(result['action'], 'skip')
        self.assertEqual(ci.attributes['disk_gb'], 5245.74)
        self.assertFalse(CIChangeLog.objects.filter(ci=ci).exists())


class CollectedAssetEnvironmentTests(TestCase):
    def setUp(self):
        self.ci_type = CIType.objects.create(name='Collected Environment VM', code='COLLECTED_ENVIRONMENT_VM')

    def test_collector_keeps_missing_environment_empty(self):
        from .collectors import _vsphere_vm_item

        payload = _vsphere_vm_item({
            'vm': 'vm-no-environment-001',
            'name': 'vm-no-environment',
        }, {})

        self.assertEqual(payload['environment'], '')

    def test_sync_created_asset_keeps_missing_environment_empty(self):
        from .views import _upsert_config_item_from_payload

        result = _upsert_config_item_from_payload({
            'name': 'sync-no-environment',
            'ci_type_code': self.ci_type.code,
            'source_type': 'vsphere_vm',
            'source_account': 'vcenter-test',
            'source_region': 'Datacenter',
            'source_unique_id': 'vm-no-environment-002',
        })

        self.assertEqual(result['ci'].environment, '')

    def test_sync_preserves_existing_manually_assigned_environment(self):
        from .views import _upsert_config_item_from_payload

        ci = ConfigItem.objects.create(
            name='sync-manual-environment',
            ci_type=self.ci_type,
            environment='test',
        )
        CISourceMapping.objects.create(
            ci=ci,
            source_type='vsphere_vm',
            source_account='vcenter-test',
            source_region='Datacenter',
            source_unique_id='vm-manual-environment-001',
        )

        _upsert_config_item_from_payload({
            'name': ci.name,
            'ci_type_code': self.ci_type.code,
            'source_type': 'vsphere_vm',
            'source_account': 'vcenter-test',
            'source_region': 'Datacenter',
            'source_unique_id': 'vm-manual-environment-001',
        })

        ci.refresh_from_db()
        self.assertEqual(ci.environment, 'test')

    def test_data_cleanup_only_clears_unconfirmed_provider_defaults(self):
        from django.apps import apps
        from importlib import import_module

        production_node = ResourceNode.objects.create(name='生产', node_type='env')
        clearable = ConfigItem.objects.create(name='legacy-default-prod', ci_type=self.ci_type, environment='prod')
        tagged = ConfigItem.objects.create(
            name='tagged-prod',
            ci_type=self.ci_type,
            environment='prod',
            attributes={'cloud_tags': [{'key': 'environment', 'value': 'prod'}]},
        )
        linked = ConfigItem.objects.create(
            name='linked-prod',
            ci_type=self.ci_type,
            environment='prod',
            environment_node=production_node,
        )
        manually_changed = ConfigItem.objects.create(name='manual-prod', ci_type=self.ci_type, environment='prod')
        for index, ci in enumerate((clearable, tagged, linked, manually_changed), start=1):
            CISourceMapping.objects.create(
                ci=ci,
                source_type='vsphere_vm',
                source_unique_id=f'legacy-vm-{index}',
                raw_payload={'environment': 'prod', 'attributes': ci.attributes},
            )
        CIChangeLog.objects.create(
            ci=manually_changed,
            action='update',
            before={'environment': ''},
            after={'environment': 'prod'},
            diff={'environment': {'before': '', 'after': 'prod'}},
            source='manual',
        )
        CIChangeLog.objects.create(
            ci=clearable,
            action='update',
            before={'environment': 'prod'},
            after={'environment': 'prod'},
            diff={'attributes': {'before': {}, 'after': {'cpu': 4}}},
            source='vsphere_vm',
        )

        migration = import_module('cmdb.migrations.0027_clear_collected_default_environment')
        migration.clear_collected_default_environment(apps, None)

        clearable.refresh_from_db()
        tagged.refresh_from_db()
        linked.refresh_from_db()
        manually_changed.refresh_from_db()
        self.assertEqual(clearable.environment, '')
        self.assertEqual(tagged.environment, 'prod')
        self.assertEqual(linked.environment, 'prod')
        self.assertEqual(manually_changed.environment, 'prod')

    def test_sync_keeps_waterline_data_only_in_metric_snapshots(self):
        from .serializers import CIChangeLogSerializer
        from .views import _config_item_snapshot, _sync_metric_snapshots_from_payload, _upsert_config_item_from_payload

        payload = {
            'name': 'snapshot-only-vm',
            'ci_type_code': self.ci_type.code,
            'source_type': 'vsphere_vm',
            'source_account': 'vcenter-test',
            'source_region': 'Datacenter',
            'source_unique_id': 'snapshot-only-vm-001',
            'attributes': {
                'cpu': 4,
                'cpu_usage_percent': 36.5,
                'memory_used_gb': 5.25,
                'memory_usage_percent': 65.62,
                'disk_used_gb': 40,
                'disk_usage_percent': 40,
                'metric_collection_source': 'prometheus_node_exporter',
                'metric_collected_at': '2026-08-03T01:00:00Z',
            },
            '_metric_snapshots': [
                {'metric': 'cpu_usage', 'value': 36.5, 'unit': '%', 'usage_percent': 36.5, 'source': 'prometheus_node_exporter'},
                {'metric': 'memory_usage', 'value': 5.25, 'unit': 'GB', 'usage_percent': 65.62, 'source': 'prometheus_node_exporter'},
                {'metric': 'disk_usage', 'value': 40, 'unit': 'GB', 'usage_percent': 40, 'source': 'prometheus_node_exporter'},
            ],
        }

        result = _upsert_config_item_from_payload(payload)
        ci = result['ci']
        self.assertEqual(ci.attributes['cpu'], 4)
        self.assertNotIn('cpu_usage_percent', ci.attributes)
        self.assertNotIn('memory_used_gb', ci.attributes)
        self.assertNotIn('disk_usage_percent', ci.attributes)
        self.assertNotIn('metric_collection_source', ci.attributes)
        self.assertEqual(_sync_metric_snapshots_from_payload(ci, payload), 3)
        self.assertEqual(CIResourceMetricSnapshot.objects.filter(ci=ci).count(), 3)
        self.assertNotIn('cpu_usage_percent', _config_item_snapshot(ci)['attributes'])

        change = CIChangeLog.objects.create(
            ci=ci,
            action='update',
            before={'attributes': {'cpu': 2, 'cpu_usage_percent': 20}},
            after={'attributes': {'cpu': 4, 'cpu_usage_percent': 80}},
            diff={
                'attributes': {
                    'before': {'cpu': 2, 'cpu_usage_percent': 20},
                    'after': {'cpu': 4, 'cpu_usage_percent': 80},
                },
            },
        )
        diff_fields = CIChangeLogSerializer(change).data['diff_fields']
        self.assertEqual([item['field'] for item in diff_fields], ['attributes.cpu'])

        from django.apps import apps
        from importlib import import_module

        migration = import_module('cmdb.migrations.0029_clear_waterline_change_logs')
        migration.clear_waterline_change_logs(apps, None)
        change.refresh_from_db()
        self.assertEqual(change.before['attributes'], {'cpu': 2})
        self.assertEqual(change.after['attributes'], {'cpu': 4})
        self.assertEqual(change.diff['attributes']['before'], {'cpu': 2})
        self.assertEqual(change.diff['attributes']['after'], {'cpu': 4})

    def test_waterline_cleanup_removes_builtin_fields_and_legacy_attributes(self):
        from django.apps import apps
        from importlib import import_module

        field = CIField.objects.create(
            ci_type=self.ci_type,
            code='cpu_usage_percent',
            name='CPU 使用率',
            is_builtin=True,
        )
        ci = ConfigItem.objects.create(
            name='legacy-waterline-vm',
            ci_type=self.ci_type,
            attributes={'cpu': 4, 'cpu_usage_percent': 50, 'metric_collection_status': 'ok'},
        )

        migration = import_module('cmdb.migrations.0028_move_waterline_data_to_metric_snapshots')
        migration.move_waterline_data_to_metric_snapshots(apps, None)

        ci.refresh_from_db()
        self.assertEqual(ci.attributes, {'cpu': 4})
        self.assertFalse(CIField.objects.filter(pk=field.id).exists())
        ensure_builtin_cmdb()
        virtual_machine = CIType.objects.get(code='VIRTUAL_MACHINE')
        self.assertFalse(CIField.objects.filter(
            ci_type=virtual_machine,
            code__in={'cpu_usage_percent', 'memory_usage_percent', 'disk_usage_percent', 'metric_collection_source'},
        ).exists())


class CmdbCostAnalysisTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.current_month = timezone.now().strftime('%Y-%m')
        self.previous_month = (
            timezone.now().replace(day=1) - timezone.timedelta(days=1)
        ).strftime('%Y-%m')

        host_type = CIType.objects.create(name='Host')
        db_type = CIType.objects.create(name='Database')

        self.prod_ci = ConfigItem.objects.create(
            name='prod-db-01',
            ci_type=db_type,
            business_line='core',
            environment='prod',
            status='active',
            attributes={'monthly_cost': 1200, 'cpu': 16, 'memory_gb': 32, 'source_account': 'aliyun-production'},
        )
        self.test_ci = ConfigItem.objects.create(
            name='test-host-01',
            ci_type=host_type,
            business_line='core',
            environment='test',
            status='active',
            attributes={'monthly_cost': 600, 'cpu': 8, 'memory_gb': 16},
        )
        self.idle_ci = ConfigItem.objects.create(
            name='idle-host-01',
            ci_type=host_type,
            business_line='shared',
            environment='prod',
            status='idle',
            attributes={'monthly_cost': 300, 'cpu': 4, 'memory_gb': 8},
        )
        CostRecord.objects.create(
            ci=self.prod_ci,
            month=self.previous_month,
            amount=Decimal('1000.00'),
            provider='history',
        )

    def test_cost_report_uses_current_month_fallbacks_without_writing_cost_records(self):
        response = self.client.get('/api/cmdb/cost/report/', {'month': self.current_month})

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload['month'], self.current_month)
        self.assertEqual(payload['total_monthly_cost'], 2100.0)
        self.assertEqual(payload['top_cost_items'][0]['name'], 'prod-db-01')
        self.assertEqual(payload['by_business'][0]['business_line'], 'core')
        self.assertEqual(payload['by_business'][0]['total_cost'], 1800.0)
        self.assertEqual(payload['by_environment'][0]['environment'], 'prod')
        self.assertEqual(payload['by_cloud_account'][0]['source_account'], 'aliyun-production')
        self.assertEqual(payload['by_cloud_account'][0]['by_type'][0]['type_name'], 'Database')
        self.assertEqual(payload['by_cloud_account'][0]['by_type'][0]['total_cost'], 1200.0)
        self.assertIn('manual', {item['provider'] for item in payload['by_provider']})
        self.assertEqual(payload['total_potential_saving'], 870.0)
        self.assertEqual(payload['optimized_monthly_cost'], 1230.0)
        self.assertEqual(payload['optimization_preview']['suggestion_count'], 3)
        self.assertTrue(payload['optimization_preview']['by_type'])
        self.assertTrue(
            any(point['period'] == self.current_month for point in payload['cost_trend'])
        )
        self.assertEqual(
            CostRecord.objects.filter(month=self.current_month).count(),
            0,
        )

    def test_cost_report_supports_historical_months_without_resync(self):
        response = self.client.get('/api/cmdb/cost/report/', {'month': self.previous_month})

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload['total_monthly_cost'], 1000.0)
        self.assertEqual(len(payload['top_cost_items']), 1)
        self.assertEqual(payload['top_cost_items'][0]['name'], 'prod-db-01')
        self.assertEqual(payload['optimization_preview']['suggestion_count'], 1)

    def test_cost_report_filters_by_cloud_account(self):
        response = self.client.get('/api/cmdb/cost/report/', {
            'month': self.current_month,
            'source_account': 'aliyun-production',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['total_monthly_cost'], 1200.0)
        self.assertEqual([item['name'] for item in payload['top_cost_items']], ['prod-db-01'])
        self.assertEqual(payload['optimization_preview']['suggestion_count'], 1)

    def test_cost_report_filters_by_business_environment(self):
        response = self.client.get('/api/cmdb/cost/report/', {
            'month': self.current_month,
            'business_line': 'core',
            'environment': 'test',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['total_monthly_cost'], 600.0)
        self.assertEqual([item['name'] for item in payload['top_cost_items']], ['test-host-01'])
        self.assertEqual(payload['optimization_preview']['suggestion_count'], 1)

    def test_optimization_returns_actionable_suggestions(self):
        response = self.client.get(
            '/api/cmdb/optimization/suggestions/',
            {'month': self.current_month},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload['month'], self.current_month)
        self.assertGreaterEqual(payload['suggestion_count'], 3)
        self.assertGreater(payload['total_potential_saving'], 0)
        self.assertEqual(payload['optimized_monthly_cost'], 1230.0)
        self.assertAlmostEqual(payload['saving_rate'], 41.4)
        self.assertTrue(any(item['label'] for item in payload['by_type']))
        titles = [item['title'] for item in payload['suggestions']]
        self.assertTrue(any('prod-db-01' in title for title in titles))
        self.assertTrue(any('test-host-01' in title for title in titles))
        self.assertTrue(any('idle-host-01' in title for title in titles))
        prod_suggestion = next(item for item in payload['suggestions'] if item['ci_name'] == 'prod-db-01')
        self.assertEqual(prod_suggestion['ci_type_id'], self.prod_ci.ci_type_id)
        self.assertEqual(prod_suggestion['source_account'], 'aliyun-production')
        account_bucket = next(item for item in payload['by_cloud_account'] if item['source_account'] == 'aliyun-production')
        self.assertEqual(account_bucket['count'], 1)
        self.assertEqual(account_bucket['by_type'], [{'type_id': self.prod_ci.ci_type_id, 'count': 1}])

    def test_cost_optimization_task_claim_and_progress_are_persisted(self):
        claim_response = self.client.post(
            '/api/cmdb/optimization-tasks/claim/',
            {
                'month': self.current_month,
                'ci_id': self.idle_ci.id,
                'suggestion_type': 'reclaim',
                'note': 'Start validation with the application owner.',
            },
            content_type='application/json',
        )

        self.assertEqual(claim_response.status_code, 201)
        task = CostOptimizationTask.objects.get(ci=self.idle_ci, month=self.current_month, suggestion_type='reclaim')
        self.assertEqual(task.owner, 'cmdb-admin')
        self.assertEqual(task.status, 'claimed')
        self.assertEqual(CostOptimizationProgress.objects.filter(task=task).count(), 1)

        progress_response = self.client.post(
            f'/api/cmdb/optimization-tasks/{task.id}/progress/',
            {
                'status': 'completed',
                'progress_percent': 100,
                'actual_monthly_saving': '280.50',
                'note': 'Resource has been reclaimed and billing verified.',
            },
            content_type='application/json',
        )
        self.assertEqual(progress_response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'completed')
        self.assertEqual(task.actual_monthly_saving, Decimal('280.50'))
        self.assertEqual(task.resolved_by, 'cmdb-admin')
        self.assertEqual(CostOptimizationProgress.objects.filter(task=task).count(), 2)

        suggestions = self.client.get('/api/cmdb/optimization/suggestions/', {'month': self.current_month}).json()['suggestions']
        suggestion = next(item for item in suggestions if item['ci_id'] == self.idle_ci.id and item['type'] == 'reclaim')
        self.assertEqual(suggestion['handling']['task_id'], task.id)
        self.assertEqual(suggestion['handling']['status'], 'completed')

    def test_optimization_uses_cloud_mapping_as_authoritative_account(self):
        ci = ConfigItem.objects.create(
            name='mapped-cloud-resource-01',
            ci_type=self.prod_ci.ci_type,
            environment='prod',
            status='idle',
            attributes={
                'monthly_cost': 900,
                'cpu': 16,
                'memory_gb': 32,
                'source_account': 'legacy-account',
            },
        )
        CISourceMapping.objects.create(
            ci=ci,
            source_type='aliyun_ecs',
            source_account='example-ali',
            source_region='cn-hangzhou',
            source_unique_id='i-mapped-cloud-resource-01',
        )

        optimization_response = self.client.get(
            '/api/cmdb/optimization/suggestions/',
            {'month': self.current_month},
        )
        report_response = self.client.get(
            '/api/cmdb/cost/report/',
            {'month': self.current_month},
        )

        self.assertEqual(optimization_response.status_code, 200)
        self.assertEqual(report_response.status_code, 200)
        suggestion = next(
            item for item in optimization_response.json()['suggestions']
            if item['ci_name'] == ci.name
        )
        self.assertEqual(suggestion['source_account'], 'example-ali')
        optimization_account = next(
            item for item in optimization_response.json()['by_cloud_account']
            if item['source_account'] == 'example-ali'
        )
        self.assertEqual(optimization_account['count'], 1)
        self.assertEqual(
            optimization_account['by_type'],
            [{'type_id': ci.ci_type_id, 'count': 1}],
        )
        report_account = next(
            item for item in report_response.json()['by_cloud_account']
            if item['source_account'] == 'example-ali'
        )
        self.assertEqual(report_account['by_type'][0]['type_id'], ci.ci_type_id)

    def test_cost_items_searches_asset_name_only(self):
        response = self.client.get('/api/cmdb/cost/items/', {
            'month': self.current_month,
            'search': 'database',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 0)

        response = self.client.get('/api/cmdb/cost/items/', {
            'month': self.current_month,
            'search': 'prod-db',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)

    def test_ownership_governance_is_not_an_optimization_suggestion(self):
        ci_type = CIType.objects.create(name='Unowned Cloud Resource')
        ConfigItem.objects.create(
            name='unowned-cost-resource',
            ci_type=ci_type,
            environment='prod',
            status='active',
            attributes={'monthly_cost': 500},
        )

        response = self.client.get(
            '/api/cmdb/optimization/suggestions/',
            {'month': self.current_month},
        )

        self.assertEqual(response.status_code, 200)
        suggestions = response.json()['suggestions']
        self.assertFalse(any(item['ci_name'] == 'unowned-cost-resource' for item in suggestions))
        self.assertFalse(any(item['type'] == 'governance' for item in suggestions))

    def test_optimization_uses_recent_waterline_averages_in_evidence(self):
        CIResourceMetricSnapshot.objects.create(
            ci=self.prod_ci,
            metric='cpu_usage',
            value=Decimal('2.92'),
            unit='%',
            usage_percent=Decimal('2.92'),
            source='aliyun_cloudmonitor',
            collected_at=timezone.now(),
        )
        CIResourceMetricSnapshot.objects.create(
            ci=self.prod_ci,
            metric='memory_usage',
            value=Decimal('36.05'),
            unit='%',
            usage_percent=Decimal('36.05'),
            source='aliyun_cloudmonitor',
            collected_at=timezone.now(),
        )

        response = self.client.get(
            '/api/cmdb/optimization/suggestions/',
            {'month': self.current_month},
        )

        self.assertEqual(response.status_code, 200)
        suggestion = next(item for item in response.json()['suggestions'] if item['ci_name'] == 'prod-db-01')
        self.assertIn('近 14 天采集均值 CPU 2.9%', suggestion['evidence'])
        self.assertIn('内存 36.0%', suggestion['evidence'])

    def test_cost_endpoints_fallback_when_month_is_invalid(self):
        cost_response = self.client.get('/api/cmdb/cost/report/', {'month': '2026-13'})
        optimization_response = self.client.get('/api/cmdb/optimization/suggestions/', {'month': 'not-a-month'})

        self.assertEqual(cost_response.status_code, 200)
        self.assertEqual(optimization_response.status_code, 200)
        self.assertEqual(cost_response.json()['month'], self.current_month)
        self.assertEqual(optimization_response.json()['month'], self.current_month)

    def test_current_month_cost_endpoints_do_not_persist_cost_records(self):
        cost_response = self.client.get('/api/cmdb/cost/report/', {'month': self.current_month})
        optimization_response = self.client.get(
            '/api/cmdb/optimization/suggestions/',
            {'month': self.current_month},
        )

        self.assertEqual(cost_response.status_code, 200)
        self.assertEqual(optimization_response.status_code, 200)
        self.assertEqual(
            CostRecord.objects.filter(month=self.current_month).count(),
            0,
        )

    def test_cost_items_returns_all_monthly_costs_with_filters_and_pagination(self):
        response = self.client.get('/api/cmdb/cost/items/', {
            'month': self.current_month,
            'page': 1,
            'page_size': 2,
            'business_line': 'core',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 2)
        self.assertEqual(len(payload['results']), 2)
        self.assertEqual(payload['results'][0]['name'], 'prod-db-01')
        self.assertEqual(payload['results'][0]['monthly_cost'], 1200.0)
        self.assertEqual(payload['results'][1]['name'], 'test-host-01')


class AliyunCostSyncTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        from multicloud.models import CloudCredential

        self.credential = CloudCredential.objects.create(
            provider='aliyun',
            name='aliyun-production',
            account_id='1234567890',
            account_name='aliyun-prod',
            access_key_id='test-ak',
            access_key_secret='test-sk',
            default_region='cn-hangzhou',
        )
        ci_type, _ = CIType.objects.get_or_create(
            code='CLOUD_SERVER',
            defaults={'name': 'Cloud Server'},
        )
        self.ci = ConfigItem.objects.create(
            name='aliyun-ecs-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            attributes={
                'source_type': 'aliyun_ecs',
                'source_account': 'aliyun-prod',
                'instance_id': 'i-aliyun-001',
                'monthly_cost': 888.0,
            },
        )
        CISourceMapping.objects.create(
            ci=self.ci,
            source_type='aliyun_ecs',
            source_account='aliyun-prod',
            source_unique_id='i-aliyun-001',
        )
        self.rds_ci = ConfigItem.objects.create(
            name='aliyun-rds-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            attributes={
                'source_type': 'aliyun_rds',
                'source_account': 'aliyun-prod',
                'instance_id': 'rm-aliyun-001',
            },
        )
        CISourceMapping.objects.create(
            ci=self.rds_ci,
            source_type='aliyun_rds',
            source_account='aliyun-prod',
            source_unique_id='rm-aliyun-001',
        )

    @patch('cmdb.costs._fetch_aliyun_subscription_orders', return_value=[])
    @patch('cmdb.costs._fetch_aliyun_instance_bill_items')
    def test_sync_aliyun_cost_projects_current_month_and_keeps_manual_records(
        self, mocked_bill_items, _mocked_subscription_orders
    ):
        from datetime import date
        from cmdb.costs import sync_aliyun_monthly_costs

        mocked_bill_items.return_value = [
            {'InstanceID': 'i-aliyun-001', 'PretaxAmount': '40.00', 'Currency': 'CNY'},
            {'InstanceID': 'i-unmatched', 'PretaxAmount': '10.00', 'Currency': 'CNY'},
        ]
        CostRecord.objects.create(
            ci=self.ci,
            month='2026-08',
            amount=Decimal('9.00'),
            provider='manual',
        )

        result = sync_aliyun_monthly_costs(month='2026-08', today=date(2026, 8, 4))

        self.assertEqual(result['updated_count'], 1)
        self.assertEqual(result['unmatched_bill_count'], 1)
        self.assertEqual(result['total_monthly_cost'], 310.0)
        self.ci.refresh_from_db()
        self.assertEqual(self.ci.attributes['monthly_cost'], 310.0)
        self.assertTrue(self.ci.attributes['cost_is_projected'])
        self.assertEqual(self.ci.attributes['cost_actual_amount'], 40.0)
        self.assertEqual(
            CostRecord.objects.get(ci=self.ci, month='2026-08', provider='aliyun').amount,
            Decimal('310.00'),
        )
        self.assertTrue(CostRecord.objects.filter(ci=self.ci, month='2026-08', provider='manual').exists())

    @patch('cmdb.costs._fetch_aliyun_subscription_orders', return_value=[])
    @patch('cmdb.costs._fetch_aliyun_instance_bill_items')
    def test_sync_aliyun_cost_keeps_current_monthly_cost_for_closed_month(
        self, mocked_bill_items, _mocked_subscription_orders
    ):
        from datetime import date
        from cmdb.costs import sync_aliyun_monthly_costs

        mocked_bill_items.return_value = [
            {'InstanceID': 'i-aliyun-001', 'PretaxAmount': '58.36', 'Currency': 'CNY'},
        ]

        result = sync_aliyun_monthly_costs(month='2026-07', today=date(2026, 8, 4))

        self.assertFalse(result['projection'])
        self.assertEqual(result['total_monthly_cost'], 58.36)
        self.ci.refresh_from_db()
        self.assertEqual(self.ci.attributes['monthly_cost'], 888.0)
        self.assertNotIn('cost_billing_cycle', self.ci.attributes)
        self.assertEqual(
            CostRecord.objects.get(ci=self.ci, month='2026-07', provider='aliyun').amount,
            Decimal('58.36'),
        )

    @patch('cmdb.costs._fetch_aliyun_subscription_orders', return_value=[])
    @patch('cmdb.costs._fetch_aliyun_instance_bill_items')
    def test_cost_sync_endpoint_updates_the_selected_month(
        self, mocked_bill_items, _mocked_subscription_orders
    ):
        mocked_bill_items.return_value = [
            {'InstanceID': 'i-aliyun-001', 'PretaxAmount': '58.36', 'Currency': 'CNY'},
        ]

        response = self.client.post('/api/cmdb/cost/sync-aliyun/', {'month': '2026-07'}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['updated_count'], 1)
        self.assertTrue(CostRecord.objects.filter(ci=self.ci, month='2026-07', provider='aliyun').exists())

    @patch('cmdb.costs._fetch_aliyun_order_details')
    @patch('cmdb.costs._fetch_aliyun_subscription_orders')
    @patch('cmdb.costs._fetch_aliyun_instance_bill_items', return_value=[])
    def test_sync_aliyun_cost_amortizes_subscription_order_per_month(
        self, _mocked_bill_items, mocked_subscription_orders, mocked_order_details
    ):
        from datetime import date
        from cmdb.costs import sync_aliyun_monthly_costs

        mocked_subscription_orders.return_value = [{'OrderId': 'order-001'}]
        mocked_order_details.return_value = [{
            'SubscriptionType': 'Subscription',
            'OrderSubType': 'ProductSubOrder',
            'SubOrderId': 'sub-order-paid',
            'InstanceIDs': '["i-aliyun-001"]',
            'PretaxAmount': '300.00',
            'PaymentTime': '2026-06-04T00:01:00Z',
            'UsageStartTime': '2026-06-04T00:00:00Z',
            'UsageEndTime': '2026-09-04T00:00:00Z',
        }, {
            'SubscriptionType': 'Subscription',
            'OrderSubType': 'ProductSubOrder',
            'SubOrderId': 'sub-order-unpaid',
            'InstanceIDs': '["i-aliyun-001"]',
            'PretaxAmount': '600.00',
            'UsageStartTime': '2026-06-04T00:00:00Z',
            'UsageEndTime': '2026-09-04T00:00:00Z',
        }]

        result = sync_aliyun_monthly_costs(
            month='2026-08',
            history_months=3,
            today=date(2026, 8, 4),
        )

        self.assertEqual(result['subscription_order_count'], 1)
        self.assertEqual(result['subscription_updated_count'], 3)
        self.assertEqual(result['total_monthly_cost'], 100.0)
        self.assertEqual(
            list(
                CostRecord.objects.filter(
                    ci=self.ci,
                    provider='aliyun_subscription',
                ).order_by('month').values_list('month', 'amount')
            ),
            [
                ('2026-06', Decimal('100.00')),
                ('2026-07', Decimal('100.00')),
                ('2026-08', Decimal('100.00')),
            ],
        )
        self.ci.refresh_from_db()
        self.assertEqual(self.ci.attributes['monthly_cost'], 100.0)
        self.assertEqual(self.ci.attributes['cost_subscription_amortized_amount'], 100.0)

    @patch('cmdb.costs._fetch_aliyun_order_details')
    @patch('cmdb.costs._fetch_aliyun_subscription_orders')
    @patch('cmdb.costs._fetch_aliyun_instance_bill_items', return_value=[])
    def test_sync_aliyun_cost_amortizes_subscription_for_non_ecs_resource(
        self, _mocked_bill_items, mocked_subscription_orders, mocked_order_details
    ):
        from datetime import date
        from cmdb.costs import sync_aliyun_monthly_costs

        mocked_subscription_orders.return_value = [{'OrderId': 'rds-order-001'}]
        mocked_order_details.return_value = [{
            'ProductCode': 'rds',
            'SubscriptionType': 'Subscription',
            'OrderSubType': 'ProductSubOrder',
            'SubOrderId': 'rds-sub-order-paid',
            'DBInstanceId': 'rm-aliyun-001',
            'PretaxAmount': '600.00',
            'PaymentTime': '2026-06-04T00:01:00Z',
            'UsageStartTime': '2026-06-04T00:00:00Z',
            'UsageEndTime': '2026-09-04T00:00:00Z',
        }]

        result = sync_aliyun_monthly_costs(
            month='2026-08',
            history_months=3,
            today=date(2026, 8, 4),
        )

        self.assertEqual(result['subscription_updated_count'], 3)
        self.assertEqual(
            CostRecord.objects.get(
                ci=self.rds_ci,
                month='2026-08',
                provider='aliyun_subscription',
            ).amount,
            Decimal('200.00'),
        )

    @patch('cmdb.costs._fetch_aliyun_order_details')
    @patch('cmdb.costs._fetch_aliyun_subscription_orders')
    @patch('cmdb.costs._fetch_aliyun_instance_bill_items', return_value=[])
    def test_sync_aliyun_cost_matches_disk_subscription_by_disk_id(
        self, _mocked_bill_items, mocked_subscription_orders, mocked_order_details
    ):
        from datetime import date
        from cmdb.costs import sync_aliyun_monthly_costs

        disk_ci = ConfigItem.objects.create(
            name='aliyun-disk-01',
            ci_type=self.ci.ci_type,
            business_line='core',
            environment='prod',
            attributes={'source_type': 'aliyun_disk', 'source_account': 'aliyun-prod'},
        )
        CISourceMapping.objects.create(
            ci=disk_ci,
            source_type='aliyun_disk',
            source_account='aliyun-prod',
            source_unique_id='d-aliyun-001',
        )
        mocked_subscription_orders.return_value = [{'OrderId': 'disk-order-001'}]
        mocked_order_details.return_value = [{
            'ProductCode': 'ecs',
            'SubscriptionType': 'Subscription',
            'OrderSubType': 'ProductSubOrder',
            'SubOrderId': 'disk-sub-order-paid',
            'DiskId': 'd-aliyun-001',
            'PretaxAmount': '90.00',
            'PaymentTime': '2026-06-04T00:01:00Z',
            'UsageStartTime': '2026-06-04T00:00:00Z',
            'UsageEndTime': '2026-09-04T00:00:00Z',
        }]

        sync_aliyun_monthly_costs(
            month='2026-08',
            history_months=3,
            today=date(2026, 8, 4),
        )

        self.assertEqual(
            CostRecord.objects.get(
                ci=disk_ci,
                month='2026-08',
                provider='aliyun_subscription',
            ).amount,
            Decimal('30.00'),
        )


class CmdbTopologyTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        app_type = CIType.objects.create(name='Application')
        host_type = CIType.objects.create(name='Host')

        self.core_prod = ConfigItem.objects.create(
            name='core-app-prod',
            ci_type=app_type,
            business_line='core',
            environment='prod',
            status='active',
            attributes={'ip_address': '10.0.0.10', 'monthly_cost': 500},
        )
        self.core_db = ConfigItem.objects.create(
            name='core-db-prod',
            ci_type=host_type,
            business_line='core',
            environment='prod',
            status='active',
            attributes={'ip_address': '10.0.0.11', 'monthly_cost': 800},
        )
        self.shared_cache = ConfigItem.objects.create(
            name='shared-cache-prod',
            ci_type=host_type,
            business_line='shared',
            environment='prod',
            status='active',
            attributes={'ip_address': '10.0.1.10', 'monthly_cost': 300},
        )
        CIRelation.objects.create(
            source=self.core_prod,
            target=self.core_db,
            relation_type='depends_on',
            description='Primary dependency',
        )
        CIRelation.objects.create(
            source=self.core_prod,
            target=self.shared_cache,
            relation_type='connects_to',
            description='Cross business dependency',
        )

    def test_topology_scope_neighbors_keeps_cross_scope_neighbors(self):
        response = self.client.get(
            '/api/cmdb/topology/data/',
            {
                'business_line': 'core',
                'environment': 'prod',
                'scope': 'neighbors',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        node_names = {node['name'] for node in payload['nodes']}
        self.assertEqual(payload['meta']['scope'], 'neighbors')
        self.assertIn('core-app-prod', node_names)
        self.assertIn('core-db-prod', node_names)
        self.assertIn('shared-cache-prod', node_names)
        self.assertEqual(len(payload['meta']['matched_node_ids']), 2)
        self.assertTrue(any(edge['target_name'] == 'shared-cache-prod' for edge in payload['edges']))
        self.assertTrue(any(edge['type'] == 'connects_to' for edge in payload['edges']))

    def test_topology_scope_exact_only_returns_matching_nodes(self):
        response = self.client.get(
            '/api/cmdb/topology/data/',
            {
                'business_line': 'core',
                'environment': 'prod',
                'scope': 'exact',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        node_names = {node['name'] for node in payload['nodes']}
        self.assertEqual(payload['meta']['scope'], 'exact')
        self.assertEqual(node_names, {'core-app-prod', 'core-db-prod'})
        self.assertFalse(any(edge['target_name'] == 'shared-cache-prod' for edge in payload['edges']))

    def test_topology_scope_two_hops_expands_in_layers(self):
        shared_worker = ConfigItem.objects.create(
            name='shared-worker-prod',
            ci_type=self.core_db.ci_type,
            business_line='shared',
            environment='prod',
            status='active',
        )
        CIRelation.objects.create(
            source=self.shared_cache,
            target=shared_worker,
            relation_type='connects_to',
        )

        response = self.client.get(
            '/api/cmdb/topology/data/',
            {
                'business_line': 'core',
                'environment': 'prod',
                'scope': 'neighbors',
                'neighbor_hops': 2,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        node_names = {node['name'] for node in payload['nodes']}
        self.assertEqual(payload['meta']['neighbor_hops'], 2)
        self.assertIn('shared-cache-prod', node_names)
        self.assertIn('shared-worker-prod', node_names)

    def test_topology_neighbor_hops_are_capped_at_three(self):
        response = self.client.get(
            '/api/cmdb/topology/data/',
            {
                'business_line': 'core',
                'environment': 'prod',
                'scope': 'neighbors',
                'neighbor_hops': 99,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['meta']['neighbor_hops'], 3)


class CmdbRelationValidationTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        app_type = CIType.objects.create(name='Application', code='REL_APP')
        host_type = CIType.objects.create(name='HostResource', code='REL_HOST')
        db_type = CIType.objects.create(name='DatabaseResource', code='REL_DB')
        self.app_type = app_type
        self.host_type = host_type
        self.db_type = db_type
        self.app_a = ConfigItem.objects.create(
            name='app-a',
            ci_type=app_type,
            business_line='core',
            environment='prod',
            status='active',
        )
        self.host = ConfigItem.objects.create(
            name='host-a',
            ci_type=host_type,
            business_line='core',
            environment='prod',
            status='active',
        )
        self.db = ConfigItem.objects.create(
            name='db-a',
            ci_type=db_type,
            business_line='core',
            environment='prod',
            status='active',
        )
        self.app_b = ConfigItem.objects.create(
            name='app-b',
            ci_type=app_type,
            business_line='core',
            environment='prod',
            status='active',
        )

    def test_relation_api_rejects_self_reference(self):
        response = self.client.post(
            '/api/cmdb/ci-relations/',
            {
                'source': self.app_a.id,
                'target': self.app_a.id,
                'relation_type': 'depends_on',
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(CIRelation.objects.count(), 0)

    def test_relation_api_rejects_duplicate_relation(self):
        response = self.client.post(
            '/api/cmdb/ci-relations/',
            {
                'source': self.app_a.id,
                'target': self.app_b.id,
                'relation_type': 'depends_on',
            },
        )
        self.assertEqual(response.status_code, 201)

        duplicate_response = self.client.post(
            '/api/cmdb/ci-relations/',
            {
                'source': self.app_a.id,
                'target': self.app_b.id,
                'relation_type': 'depends_on',
            },
        )

        self.assertEqual(duplicate_response.status_code, 400)
        self.assertEqual(CIRelation.objects.count(), 1)

    def test_relation_api_enforces_model_relation_rule_when_source_has_rules(self):
        CIRelationRule.objects.create(
            source_type=self.app_type,
            target_type=self.host_type,
            relation_type='runs_on',
            multiple=True,
        )

        allowed_response = self.client.post(
            '/api/cmdb/ci-relations/',
            {
                'source': self.app_a.id,
                'target': self.host.id,
                'relation_type': 'runs_on',
            },
        )
        self.assertEqual(allowed_response.status_code, 201, allowed_response.content)

        denied_response = self.client.post(
            '/api/cmdb/ci-relations/',
            {
                'source': self.app_a.id,
                'target': self.db.id,
                'relation_type': 'depends_on',
            },
        )
        self.assertEqual(denied_response.status_code, 400)
        self.assertIn('模型关系规则', json.dumps(denied_response.json(), ensure_ascii=False))
        self.assertEqual(CIRelation.objects.count(), 1)

    def test_relation_rule_multiple_false_rejects_second_same_type_target(self):
        host_b = ConfigItem.objects.create(
            name='host-b',
            ci_type=self.host_type,
            business_line='core',
            environment='prod',
            status='active',
        )
        CIRelationRule.objects.create(
            source_type=self.app_type,
            target_type=self.host_type,
            relation_type='runs_on',
            multiple=False,
        )
        first_response = self.client.post(
            '/api/cmdb/ci-relations/',
            {'source': self.app_a.id, 'target': self.host.id, 'relation_type': 'runs_on'},
        )
        self.assertEqual(first_response.status_code, 201, first_response.content)

        second_response = self.client.post(
            '/api/cmdb/ci-relations/',
            {'source': self.app_a.id, 'target': host_b.id, 'relation_type': 'runs_on'},
        )

        self.assertEqual(second_response.status_code, 400)
        self.assertIn('不允许同一资源关联多个同类目标', json.dumps(second_response.json(), ensure_ascii=False))
        self.assertEqual(CIRelation.objects.count(), 1)

    def test_relation_available_rules_returns_rules_for_current_ci_and_direction(self):
        CIRelationRule.objects.create(
            source_type=self.app_type,
            target_type=self.host_type,
            relation_type='runs_on',
            description='应用部署到主机',
        )
        CIRelationRule.objects.create(
            source_type=self.db_type,
            target_type=self.app_type,
            relation_type='connects_to',
            description='数据库反向连接应用',
        )

        outgoing = self.client.get('/api/cmdb/ci-relations/available-rules/', {'ci': self.app_a.id})
        incoming = self.client.get('/api/cmdb/ci-relations/available-rules/', {'ci': self.app_a.id, 'direction': 'incoming'})

        self.assertEqual(outgoing.status_code, 200, outgoing.content)
        self.assertEqual(outgoing.json()[0]['relation_type'], 'runs_on')
        self.assertEqual(outgoing.json()[0]['peer_type_name'], 'HostResource')
        self.assertEqual(incoming.status_code, 200, incoming.content)
        self.assertEqual(incoming.json()[0]['relation_type'], 'connects_to')
        self.assertEqual(incoming.json()[0]['peer_type_name'], 'DatabaseResource')

    def test_relation_api_closes_island_required_relation_and_records_audit(self):
        CIRelationRule.objects.create(
            source_type=self.app_type,
            target_type=self.host_type,
            relation_type='runs_on',
            required=True,
            multiple=True,
            is_active=True,
        )

        island_response = self.client.get('/api/cmdb/island-analysis/')
        self.assertEqual(island_response.status_code, 200, island_response.content)
        missing_issue = next(
            item
            for item in island_response.json()['results']
            if item['ci_id'] == self.app_a.id and item['issue_type'] == 'missing_required_relation'
        )
        self.assertEqual(missing_issue['relation_direction'], 'outgoing')
        self.assertEqual(missing_issue['relation_candidates'][0]['id'], self.host.id)

        create_response = self.client.post(
            '/api/cmdb/ci-relations/',
            data=json.dumps({
                'source': self.app_a.id,
                'target': self.host.id,
                'relation_type': missing_issue['relation_type'],
                'description': 'created from island suggestion',
                'evidence_source': 'governance',
                'confidence': 85,
                'evidence': {
                    'issue_type': missing_issue['issue_type'],
                    'candidate_reason': missing_issue['relation_candidates'][0]['reasons'][0],
                },
            }),
            content_type='application/json',
        )

        self.assertEqual(create_response.status_code, 201, create_response.content)
        relation_id = create_response.json()['id']
        relation = CIRelation.objects.get(id=relation_id)
        self.assertEqual(relation.evidence_source, 'governance')
        self.assertEqual(relation.confidence, 85)
        self.assertEqual(relation.evidence['issue_type'], 'missing_required_relation')
        create_log = CIChangeLog.objects.filter(ci=self.app_a, action='relation_create').latest('id')
        self.assertEqual(create_log.operator, self.user.username)
        self.assertEqual(create_log.source, 'relation')
        self.assertEqual(create_log.after['source_id'], self.app_a.id)
        self.assertEqual(create_log.after['target_id'], self.host.id)
        self.assertEqual(create_log.after['relation_type'], 'runs_on')
        self.assertEqual(create_log.after['evidence_source'], 'governance')
        self.assertEqual(create_log.after['confidence'], 85)

        topology_response = self.client.get('/api/cmdb/topology/data/', {'business_line': 'core'})
        self.assertEqual(topology_response.status_code, 200, topology_response.content)
        topology_edge = next(edge for edge in topology_response.json()['edges'] if edge['id'] == relation_id)
        self.assertEqual(topology_edge['evidence_source'], 'governance')
        self.assertEqual(topology_edge['confidence'], 85)
        self.assertEqual(topology_edge['evidence']['issue_type'], 'missing_required_relation')

        island_after_create = self.client.get('/api/cmdb/island-analysis/')
        self.assertEqual(island_after_create.status_code, 200, island_after_create.content)
        app_issues = {
            item['issue_type']
            for item in island_after_create.json()['results']
            if item['ci_id'] == self.app_a.id
        }
        self.assertNotIn('missing_required_relation', app_issues)

        delete_response = self.client.delete(f'/api/cmdb/ci-relations/{relation_id}/')
        self.assertEqual(delete_response.status_code, 204, delete_response.content)
        delete_log = CIChangeLog.objects.filter(ci=self.app_a, action='relation_delete').latest('id')
        self.assertEqual(delete_log.operator, self.user.username)
        self.assertEqual(delete_log.before['source_id'], self.app_a.id)
        self.assertEqual(delete_log.before['target_id'], self.host.id)
        self.assertEqual(delete_log.before['relation_type'], 'runs_on')

    def test_relation_bulk_create_closes_required_relation_suggestions(self):
        host_b = ConfigItem.objects.create(
            name='host-bulk-b',
            ci_type=self.host_type,
            business_line='core',
            environment='prod',
            status='active',
        )
        CIRelationRule.objects.create(
            source_type=self.app_type,
            target_type=self.host_type,
            relation_type='runs_on',
            required=True,
            multiple=True,
            is_active=True,
        )

        response = self.client.post(
            '/api/cmdb/ci-relations/bulk-create/',
            data=json.dumps({
                'relations': [
                    {
                        'source': self.app_a.id,
                        'target': self.host.id,
                        'relation_type': 'runs_on',
                        'description': 'bulk island suggestion',
                        'evidence_source': 'governance',
                        'confidence': 82,
                        'evidence': {'source': 'island_analysis'},
                    },
                    {
                        'source': self.app_b.id,
                        'target': host_b.id,
                        'relation_type': 'runs_on',
                        'description': 'bulk island suggestion',
                        'evidence_source': 'governance',
                        'confidence': 78,
                        'evidence': {'source': 'island_analysis'},
                    },
                    {
                        'source': self.app_a.id,
                        'target': self.host.id,
                        'relation_type': 'runs_on',
                    },
                ],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['summary']['total'], 3)
        self.assertEqual(payload['summary']['created'], 2)
        self.assertEqual(payload['summary']['skipped'], 1)
        self.assertEqual(payload['summary']['errors'], 0)
        self.assertTrue(CIRelation.objects.filter(source=self.app_a, target=self.host, relation_type='runs_on').exists())
        self.assertTrue(CIRelation.objects.filter(source=self.app_b, target=host_b, relation_type='runs_on').exists())
        self.assertEqual(CIRelation.objects.get(source=self.app_a, target=self.host).evidence_source, 'governance')
        self.assertEqual(CIRelation.objects.get(source=self.app_b, target=host_b).confidence, 78)
        self.assertEqual(CIRelation.objects.filter(relation_type='runs_on').count(), 2)
        self.assertEqual(
            CIChangeLog.objects.filter(ci__in=[self.app_a, self.app_b], action='relation_create', source='relation').count(),
            2,
        )

        island_after = self.client.get('/api/cmdb/island-analysis/')
        self.assertEqual(island_after.status_code, 200, island_after.content)
        required_issues = [
            item for item in island_after.json()['results']
            if item['issue_type'] == 'missing_required_relation' and item['ci_id'] in {self.app_a.id, self.app_b.id}
        ]
        self.assertEqual(required_issues, [])


class CmdbResourceRequestTests(AuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        core = ResourceNode.objects.create(name='core', node_type='biz')
        ResourceNode.objects.create(name='prod', node_type='env', parent=core)
        ResourceNode.objects.create(name='test', node_type='env', parent=core)

    def test_request_workflow_records_applicant_approver_and_completion(self):
        create_response = self.client.post(
            '/api/cmdb/resource-requests/',
            data=json.dumps({
                'title': 'Order service prod host expansion',
                'resource_type': 'host',
                'specification': '4C8G',
                'business_line': 'core',
                'environment': 'prod',
                'quantity': 1,
                'priority': 'high',
                'reason': 'Traffic increase requires one more node',
                'specs': {
                    'hostname': 'order-api-ecs-03',
                    'ip_address': '10.0.0.23',
                    'os_type': 'Alibaba Cloud Linux 3',
                    'admin_user': 'sre-core',
                    'instance_type': 'ecs.g7.xlarge',
                },
            }),
            content_type='application/json',
        )

        self.assertEqual(create_response.status_code, 201)
        request_id = create_response.json()['id']
        request_obj = ResourceRequest.objects.get(pk=request_id)
        self.assertEqual(request_obj.applicant, 'cmdb-admin')
        self.assertEqual(request_obj.status, 'pending')

        approve_response = self.client.post(
            f'/api/cmdb/resource-requests/{request_id}/approve/',
            {'comment': 'capacity approved'},
        )
        self.assertEqual(approve_response.status_code, 200)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'approved')
        self.assertEqual(request_obj.approver, 'cmdb-admin')
        self.assertEqual(request_obj.approval_comment, 'capacity approved')
        self.assertIsNotNone(request_obj.approved_at)

        complete_response = self.client.post(
            f'/api/cmdb/resource-requests/{request_id}/complete/',
            {'note': 'host provisioned and synced'},
        )
        self.assertEqual(complete_response.status_code, 200)
        complete_payload = complete_response.json()
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'completed')
        self.assertEqual(request_obj.fulfillment_note, 'host provisioned and synced')
        self.assertIsNotNone(request_obj.completed_at)

        host = Host.objects.get(hostname='order-api-ecs-03')
        self.assertEqual(host.ip_address, '10.0.0.23')
        self.assertEqual(host.business_line, 'core')
        self.assertEqual(host.environment, 'prod')
        self.assertEqual(host.admin_user, 'sre-core')
        self.assertEqual(host.status, 'online')

        ci = ConfigItem.objects.get(name='order-api-ecs-03')
        self.assertIn('ECS', ci.ci_type.name)
        self.assertEqual(ci.business_line, 'core')
        self.assertEqual(ci.environment, 'prod')
        self.assertEqual(ci.admin_user, 'sre-core')
        self.assertEqual(ci.status, 'active')
        self.assertEqual(ci.attributes['ip_address'], '10.0.0.23')
        self.assertEqual(ci.attributes['os_type'], 'Alibaba Cloud Linux 3')
        self.assertEqual(ci.attributes['instance_type'], 'ecs.g7.xlarge')
        self.assertEqual(ci.attributes['source'], 'host_request')
        self.assertEqual(ci.attributes['request_id'], request_id)
        mapping = CISourceMapping.objects.get(
            ci=ci,
            source_type='resource_request',
            source_unique_id=str(request_id),
        )
        self.assertEqual(mapping.source_account, 'cmdb-admin')
        self.assertEqual(mapping.source_region, 'prod')
        self.assertEqual(mapping.sync_status, 'success')
        self.assertEqual(mapping.raw_payload['request_id'], request_id)
        self.assertEqual(mapping.raw_payload['fulfillment_note'], 'host provisioned and synced')
        change_log = CIChangeLog.objects.filter(ci=ci, source='resource_request').latest('id')
        self.assertIn(change_log.action, {'create', 'update'})
        self.assertEqual(change_log.operator, 'cmdb-admin')
        self.assertEqual(change_log.after['name'], 'order-api-ecs-03')
        request_logs = CIChangeLog.objects.filter(
            ci__isnull=True,
            source='resource_request',
            after__id=request_id,
        ).order_by('id')
        self.assertEqual(
            [item.action for item in request_logs],
            ['request_submit', 'request_approve', 'request_complete'],
        )
        submit_log = request_logs.get(action='request_submit')
        self.assertEqual(submit_log.after['name'], 'Order service prod host expansion')
        self.assertEqual(submit_log.after['ci_type_name'], '资源申请')
        approve_log = request_logs.get(action='request_approve')
        self.assertEqual(approve_log.diff['status']['before'], 'pending')
        self.assertEqual(approve_log.diff['status']['after'], 'approved')
        complete_log = request_logs.get(action='request_complete')
        self.assertEqual(complete_log.diff['status']['before'], 'approved')
        self.assertEqual(complete_log.diff['status']['after'], 'completed')
        audit_search_response = self.client.get('/api/cmdb/change-logs/', {
            'search': 'Order service prod host expansion',
            'source': 'resource_request',
            'page_size': 20,
        })
        self.assertEqual(audit_search_response.status_code, 200)
        audit_search_actions = {item['action'] for item in audit_search_response.json()['results']}
        self.assertTrue({'request_submit', 'request_approve', 'request_complete'}.issubset(audit_search_actions))
        request_audit_response = self.client.get('/api/cmdb/change-logs/', {
            'request_id': request_id,
            'source': 'resource_request',
            'page_size': 20,
        })
        self.assertEqual(request_audit_response.status_code, 200)
        request_audit_actions = [item['action'] for item in request_audit_response.json()['results']]
        self.assertEqual(
            request_audit_actions,
            ['request_complete', 'request_approve', 'request_submit'],
        )
        self.assertEqual(complete_payload['delivered_ci']['id'], ci.id)
        self.assertEqual(complete_payload['delivered_ci']['name'], 'order-api-ecs-03')
        self.assertEqual(complete_payload['delivered_ci']['source_mapping_id'], mapping.id)
        self.assertEqual(len(complete_payload['delivered_items']), 1)
        self.assertEqual(complete_payload['delivered_items'][0]['id'], ci.id)

        list_response = self.client.get('/api/cmdb/resource-requests/', {'status': 'completed'})
        self.assertEqual(list_response.status_code, 200)
        list_payload = list_response.json()
        rows = list_payload.get('results', list_payload) if isinstance(list_payload, dict) else list_payload
        delivered_row = next(item for item in rows if item['id'] == request_id)
        self.assertEqual(delivered_row['delivered_ci']['id'], ci.id)
        self.assertEqual(delivered_row['delivered_ci']['sync_status'], 'success')

    def test_provisioning_options_only_return_enabled_sanitized_supported_accounts(self):
        enabled = CloudCredential.objects.create(
            provider='aliyun',
            name='生产阿里云账号',
            account_id='10001',
            account_name='prod-main',
            access_key_id='test-ak',
            access_key_secret='test-secret',
            default_region='cn-hangzhou',
            is_enabled=True,
        )
        CloudCredential.objects.create(
            provider='huawei',
            name='停用华为云账号',
            access_key_id='test-ak',
            access_key_secret='test-secret',
            project_id='project-id',
            default_region='cn-north-4',
            is_enabled=False,
        )

        response = self.client.get('/api/cmdb/resource-requests/provisioning-options/')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual({item['value'] for item in payload['providers']}, {'aliyun', 'huawei', 'vsphere'})
        self.assertEqual(len(payload['credentials']), 1)
        self.assertEqual(payload['credentials'][0]['id'], enabled.id)
        self.assertNotIn('access_key_id', payload['credentials'][0])
        self.assertNotIn('access_key_secret', payload['credentials'][0])

    @patch('cmdb.views.provision_resource_request')
    def test_cloud_provisioning_creates_cmdb_asset_without_waiting_for_ip(self, mock_provision):
        credential = CloudCredential.objects.create(
            provider='huawei',
            name='华为云生产账号',
            access_key_id='test-ak',
            access_key_secret='test-secret',
            project_id='project-id',
            default_region='cn-north-4',
            is_enabled=True,
        )
        request_obj = ResourceRequest.objects.create(
            title='华为云订单服务扩容',
            applicant='cmdb-admin',
            approver='cmdb-admin',
            resource_type='主机',
            specification='s6.large.2',
            business_line='core',
            environment='prod',
            priority='high',
            quantity=1,
            status='approved',
            reason='生产扩容',
            specs={
                'provisioning_mode': 'cloud',
                'provider': 'huawei',
                'cloud_credential_id': credential.id,
                'region': 'cn-north-4',
                'instance_name_prefix': 'order-api-hw-01',
                'image_id': 'image-id',
                'flavor_ref': 's6.large.2',
                'security_group_id': 'sg-id',
                'vpc_id': 'vpc-id',
                'subnet_id': 'subnet-id',
            },
            approved_at=timezone.now(),
        )
        mock_provision.return_value = (credential, [{
            'provider': 'huawei',
            'instance_id': 'server-001',
            'hostname': 'order-api-hw-01',
            'private_ip': '',
            'public_ip': '',
            'region': 'cn-north-4',
            'zone': 'cn-north-4a',
            'instance_type': 's6.large.2',
            'status': 'BUILD',
        }])

        response = self.client.post(
            f'/api/cmdb/resource-requests/{request_obj.id}/provision/',
            {'note': '自动交付'},
        )

        self.assertEqual(response.status_code, 200, response.content)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'completed')
        self.assertEqual(request_obj.specs['provisioning']['status'], 'success')
        ci = ConfigItem.objects.get(name='order-api-hw-01')
        self.assertEqual(ci.ci_type.code, 'CLOUD_SERVER')
        self.assertEqual(ci.attributes['instance_id'], 'server-001')
        self.assertEqual(ci.attributes['provider'], 'huawei')
        self.assertNotIn('ip_address', ci.attributes)
        self.assertFalse(Host.objects.filter(hostname='order-api-hw-01').exists())
        self.assertTrue(CISourceMapping.objects.filter(
            ci=ci,
            source_type='resource_request',
            source_unique_id=str(request_obj.id),
        ).exists())

    @patch('cmdb.views.provision_resource_request', side_effect=RuntimeError('云平台配额不足'))
    def test_cloud_provisioning_failure_is_recorded_for_retry(self, _mock_provision):
        credential = CloudCredential.objects.create(
            provider='aliyun',
            name='阿里云生产账号',
            access_key_id='test-ak',
            access_key_secret='test-secret',
            default_region='cn-hangzhou',
            is_enabled=True,
        )
        request_obj = ResourceRequest.objects.create(
            title='阿里云交易服务扩容',
            applicant='cmdb-admin',
            approver='cmdb-admin',
            resource_type='主机',
            specification='ecs.g7.large',
            business_line='core',
            environment='prod',
            priority='urgent',
            quantity=1,
            status='approved',
            reason='生产扩容',
            specs={
                'provisioning_mode': 'cloud',
                'provider': 'aliyun',
                'cloud_credential_id': credential.id,
                'region': 'cn-hangzhou',
                'instance_name_prefix': 'trade-api-aliyun-01',
                'image_id': 'image-id',
                'instance_type': 'ecs.g7.large',
                'security_group_id': 'sg-id',
                'vswitch_id': 'vsw-id',
            },
            approved_at=timezone.now(),
        )

        response = self.client.post(f'/api/cmdb/resource-requests/{request_obj.id}/provision/')

        self.assertEqual(response.status_code, 400)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'failed')
        self.assertEqual(request_obj.specs['provisioning']['status'], 'failed')
        self.assertIn('配额不足', request_obj.specs['provisioning']['error'])
        self.assertTrue(CIChangeLog.objects.filter(
            source='resource_request',
            action='request_provision_failed',
            after__id=request_obj.id,
        ).exists())

    def test_request_completion_accepts_delivery_specs_override(self):
        request_obj = ResourceRequest.objects.create(
            title='Complete with final delivery specs',
            applicant='cmdb-admin',
            approver='cmdb-admin',
            resource_type='host',
            specification='2C4G',
            business_line='core',
            environment='prod',
            priority='high',
            quantity=1,
            status='approved',
            reason='delivery info is known after approval',
            specs={'os_type': 'Linux'},
            approved_at=timezone.now(),
        )

        response = self.client.post(
            f'/api/cmdb/resource-requests/{request_obj.id}/complete/',
            data=json.dumps({
                'note': 'filled at delivery time',
                'specs': {
                    'hostname': 'delivery-final-host-01',
                    'ip_address': '10.0.0.91',
                    'os_type': 'Alibaba Cloud Linux 3',
                    'admin_user': 'delivery-sre',
                    'instance_type': 'ecs.g7.large',
                },
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'completed')
        self.assertEqual(request_obj.specs['hostname'], 'delivery-final-host-01')
        self.assertEqual(request_obj.specs['ip_address'], '10.0.0.91')
        host = Host.objects.get(hostname='delivery-final-host-01')
        self.assertEqual(host.ip_address, '10.0.0.91')
        self.assertEqual(host.admin_user, 'delivery-sre')
        ci = ConfigItem.objects.get(name='delivery-final-host-01')
        self.assertEqual(ci.attributes['instance_type'], 'ecs.g7.large')
        mapping = CISourceMapping.objects.get(source_type='resource_request', source_unique_id=str(request_obj.id))
        self.assertEqual(mapping.ci, ci)
        complete_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            source='resource_request',
            action='request_complete',
            after__id=request_obj.id,
        ).latest('id')
        self.assertEqual(complete_log.diff['status']['after'], 'completed')
        self.assertEqual(complete_log.after['specs']['hostname'], 'delivery-final-host-01')

    def test_request_completion_supports_multiple_hosts(self):
        request_obj = ResourceRequest.objects.create(
            title='Order service batch expansion',
            applicant='cmdb-admin',
            approver='cmdb-admin',
            resource_type='host',
            specification='2C4G',
            business_line='core',
            environment='prod',
            priority='high',
            quantity=10,
            status='approved',
            reason='batch capacity expansion',
            specs={
                'os_type': 'Linux',
                'admin_user': 'sre-core',
                'hosts': [
                    {
                        'hostname': f'order-api-ecs-{index:02d}',
                        'ip_address': f'10.0.0.{20 + index}',
                        'instance_type': 'ecs.g7.large',
                    }
                    for index in range(1, 11)
                ],
            },
            approved_at=timezone.now(),
        )

        response = self.client.post(
            f'/api/cmdb/resource-requests/{request_obj.id}/complete/',
            {'note': 'batch provisioned'},
        )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        expected_names = [f'order-api-ecs-{index:02d}' for index in range(1, 11)]
        self.assertEqual(len(payload['delivered_items']), 10)
        self.assertEqual([item['name'] for item in payload['delivered_items']], expected_names)
        self.assertEqual([item['request_item_index'] for item in payload['delivered_items']], list(range(1, 11)))
        self.assertEqual(payload['delivered_ci']['name'], 'order-api-ecs-01')
        self.assertEqual(
            set(Host.objects.values_list('hostname', flat=True)),
            set(expected_names),
        )
        created_items = ConfigItem.objects.filter(name__in=expected_names)
        self.assertEqual(created_items.count(), 10)
        self.assertEqual(
            set(created_items.values_list('attributes__request_item_index', flat=True)),
            set(range(1, 11)),
        )
        mappings = CISourceMapping.objects.filter(source_type='resource_request', source_unique_id__startswith=f'{request_obj.id}:')
        self.assertEqual(mappings.count(), 10)
        self.assertEqual(
            set(mappings.values_list('source_unique_id', flat=True)),
            {f'{request_obj.id}:{index}' for index in range(1, 11)},
        )
        self.assertEqual(
            CIChangeLog.objects.filter(ci__in=created_items, source='resource_request').count(),
            10,
        )
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'completed')

    def test_request_reject_records_platform_audit_log(self):
        request_obj = ResourceRequest.objects.create(
            title='Reject host request',
            applicant='cmdb-admin',
            resource_type='host',
            specification='2C4G',
            business_line='core',
            environment='prod',
            priority='medium',
            quantity=1,
            status='pending',
            reason='not enough quota',
            specs={'hostname': 'reject-host-01', 'ip_address': '10.0.4.10'},
        )

        response = self.client.post(
            f'/api/cmdb/resource-requests/{request_obj.id}/reject/',
            {'comment': 'quota exhausted'},
        )

        self.assertEqual(response.status_code, 200)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'rejected')
        log = CIChangeLog.objects.get(
            ci__isnull=True,
            source='resource_request',
            action='request_reject',
            after__id=request_obj.id,
        )
        self.assertEqual(log.operator, 'cmdb-admin')
        self.assertEqual(log.after['name'], 'Reject host request')
        self.assertEqual(log.after['ci_type_name'], '资源申请')
        self.assertEqual(log.diff['status']['before'], 'pending')
        self.assertEqual(log.diff['status']['after'], 'rejected')
        self.assertEqual(log.diff['approval_comment']['after'], 'quota exhausted')

    def test_request_completion_rejects_duplicate_hosts_in_batch(self):
        request_obj = ResourceRequest.objects.create(
            title='Duplicate host batch expansion',
            applicant='cmdb-admin',
            approver='cmdb-admin',
            resource_type='host',
            specification='2C4G',
            business_line='core',
            environment='prod',
            priority='high',
            quantity=2,
            status='approved',
            reason='duplicate delivery data',
            specs={
                'os_type': 'Linux',
                'hosts': [
                    {'hostname': 'duplicate-ecs-01', 'ip_address': '10.0.1.24'},
                    {'hostname': 'duplicate-ecs-01', 'ip_address': '10.0.1.25'},
                ],
            },
            approved_at=timezone.now(),
        )

        response = self.client.post(
            f'/api/cmdb/resource-requests/{request_obj.id}/complete/',
            {'note': 'try duplicate batch'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'approved')
        self.assertFalse(Host.objects.filter(hostname='duplicate-ecs-01').exists())
        self.assertFalse(ConfigItem.objects.filter(name='duplicate-ecs-01').exists())
        self.assertFalse(CISourceMapping.objects.filter(source_type='resource_request', source_unique_id__startswith=f'{request_obj.id}:').exists())

    def test_request_completion_rejects_existing_host_ip_conflict(self):
        Host.objects.create(
            hostname='existing-host-01',
            ip_address='10.0.2.10',
            business_line='core',
            environment='prod',
            status='online',
        )
        request_obj = ResourceRequest.objects.create(
            title='Conflicting host request',
            applicant='cmdb-admin',
            approver='cmdb-admin',
            resource_type='host',
            specification='2C4G',
            business_line='core',
            environment='prod',
            priority='high',
            quantity=1,
            status='approved',
            reason='conflicting delivery ip',
            specs={
                'hostname': 'new-conflict-host-01',
                'ip_address': '10.0.2.10',
                'os_type': 'Linux',
            },
            approved_at=timezone.now(),
        )

        response = self.client.post(
            f'/api/cmdb/resource-requests/{request_obj.id}/complete/',
            {'note': 'try conflicting ip'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'approved')
        self.assertFalse(Host.objects.filter(hostname='new-conflict-host-01').exists())
        self.assertFalse(ConfigItem.objects.filter(name='new-conflict-host-01').exists())

    def test_request_completion_rejects_existing_ci_ip_conflict(self):
        ci_type = _ci_type('IP 冲突云主机', code='IP_CONFLICT_SERVER')
        ConfigItem.objects.create(
            name='existing-ci-host-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'ip_address': '10.0.2.20'},
        )
        request_obj = ResourceRequest.objects.create(
            title='Conflicting CI request',
            applicant='cmdb-admin',
            approver='cmdb-admin',
            resource_type='host',
            specification='2C4G',
            business_line='core',
            environment='prod',
            priority='high',
            quantity=1,
            status='approved',
            reason='conflicting ci ip',
            specs={
                'hostname': 'new-conflict-ci-host-01',
                'ip_address': '10.0.2.20',
                'os_type': 'Linux',
            },
            approved_at=timezone.now(),
        )

        response = self.client.post(
            f'/api/cmdb/resource-requests/{request_obj.id}/complete/',
            {'note': 'try conflicting ci ip'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'approved')
        self.assertFalse(Host.objects.filter(hostname='new-conflict-ci-host-01').exists())
        self.assertFalse(ConfigItem.objects.filter(name='new-conflict-ci-host-01').exists())

    def test_request_completion_rejects_existing_hostname_ip_rewrite(self):
        Host.objects.create(
            hostname='existing-same-host-01',
            ip_address='10.0.2.30',
            business_line='core',
            environment='prod',
            status='online',
        )
        request_obj = ResourceRequest.objects.create(
            title='Same hostname rewrite request',
            applicant='cmdb-admin',
            approver='cmdb-admin',
            resource_type='host',
            specification='2C4G',
            business_line='core',
            environment='prod',
            priority='high',
            quantity=1,
            status='approved',
            reason='should not rewrite host ip',
            specs={
                'hostname': 'existing-same-host-01',
                'ip_address': '10.0.2.31',
                'os_type': 'Linux',
            },
            approved_at=timezone.now(),
        )

        response = self.client.post(
            f'/api/cmdb/resource-requests/{request_obj.id}/complete/',
            {'note': 'try rewrite hostname ip'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('不能改写', response.json()['detail'])
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'approved')
        self.assertEqual(Host.objects.get(hostname='existing-same-host-01').ip_address, '10.0.2.30')
        self.assertFalse(CISourceMapping.objects.filter(source_type='resource_request', source_unique_id=str(request_obj.id)).exists())

    def test_request_completion_rejects_existing_request_mapping_identity(self):
        ci_type = _ci_type('映射冲突云主机', code='REQUEST_MAPPING_CONFLICT_SERVER')
        existing_ci = ConfigItem.objects.create(
            name='mapping-conflict-host-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            status='active',
            attributes={'ip_address': '10.0.2.40'},
        )
        request_obj = ResourceRequest.objects.create(
            title='Mapping identity conflict request',
            applicant='cmdb-admin',
            approver='cmdb-admin',
            resource_type='host',
            specification='2C4G',
            business_line='core',
            environment='prod',
            priority='high',
            quantity=1,
            status='approved',
            reason='source mapping exists already',
            specs={
                'hostname': 'mapping-conflict-host-02',
                'ip_address': '10.0.2.41',
                'os_type': 'Linux',
            },
            approved_at=timezone.now(),
        )
        CISourceMapping.objects.create(
            ci=existing_ci,
            source_type='resource_request',
            source_account='cmdb-admin',
            source_region='prod',
            source_unique_id=str(request_obj.id),
            sync_status='success',
        )

        response = self.client.post(
            f'/api/cmdb/resource-requests/{request_obj.id}/complete/',
            {'note': 'try duplicated source mapping identity'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('交付映射', response.json()['detail'])
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'approved')
        self.assertFalse(Host.objects.filter(hostname='mapping-conflict-host-02').exists())
        self.assertFalse(ConfigItem.objects.filter(name='mapping-conflict-host-02').exists())

    def test_request_completion_rejects_hostname_delivered_by_other_request(self):
        ci_type = _ci_type('申请交付云主机', code='REQUEST_DELIVERED_SERVER')
        delivered_ci = ConfigItem.objects.create(
            name='other-request-host-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            status='active',
            attributes={'ip_address': '10.0.2.50'},
        )
        CISourceMapping.objects.create(
            ci=delivered_ci,
            source_type='resource_request',
            source_account='cmdb-admin',
            source_region='prod',
            source_unique_id='other-request:1',
            sync_status='success',
        )
        request_obj = ResourceRequest.objects.create(
            title='Other request delivered hostname',
            applicant='cmdb-admin',
            approver='cmdb-admin',
            resource_type='host',
            specification='2C4G',
            business_line='core',
            environment='prod',
            priority='high',
            quantity=1,
            status='approved',
            reason='hostname already delivered by another request',
            specs={
                'hostname': 'other-request-host-01',
                'ip_address': '10.0.2.50',
                'os_type': 'Linux',
            },
            approved_at=timezone.now(),
        )

        response = self.client.post(
            f'/api/cmdb/resource-requests/{request_obj.id}/complete/',
            {'note': 'try reuse delivered hostname'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('已由资源申请', response.json()['detail'])
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'approved')
        self.assertFalse(CISourceMapping.objects.filter(source_type='resource_request', source_unique_id=str(request_obj.id)).exists())

    def test_request_completion_rejects_invalid_single_host_ip(self):
        request_obj = ResourceRequest.objects.create(
            title='Invalid host IP request',
            applicant='cmdb-admin',
            approver='cmdb-admin',
            resource_type='host',
            specification='2C4G',
            business_line='core',
            environment='prod',
            priority='high',
            quantity=1,
            status='approved',
            reason='invalid ip delivery data',
            specs={
                'hostname': 'invalid-ip-host-01',
                'ip_address': '10.0.999.20',
                'os_type': 'Linux',
            },
            approved_at=timezone.now(),
        )

        response = self.client.post(
            f'/api/cmdb/resource-requests/{request_obj.id}/complete/',
            {'note': 'try invalid ip'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'approved')
        self.assertFalse(Host.objects.filter(hostname='invalid-ip-host-01').exists())
        self.assertFalse(ConfigItem.objects.filter(name='invalid-ip-host-01').exists())

    def test_request_completion_rejects_invalid_ip_in_batch(self):
        request_obj = ResourceRequest.objects.create(
            title='Invalid batch IP request',
            applicant='cmdb-admin',
            approver='cmdb-admin',
            resource_type='host',
            specification='2C4G',
            business_line='core',
            environment='prod',
            priority='high',
            quantity=2,
            status='approved',
            reason='invalid batch ip delivery data',
            specs={
                'os_type': 'Linux',
                'hosts': [
                    {'hostname': 'invalid-batch-host-01', 'ip_address': '10.0.3.21'},
                    {'hostname': 'invalid-batch-host-02', 'ip_address': '10.0.999.22'},
                ],
            },
            approved_at=timezone.now(),
        )

        response = self.client.post(
            f'/api/cmdb/resource-requests/{request_obj.id}/complete/',
            {'note': 'try invalid batch ip'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'approved')
        self.assertFalse(Host.objects.filter(hostname__startswith='invalid-batch-host').exists())
        self.assertFalse(ConfigItem.objects.filter(name__startswith='invalid-batch-host').exists())

    def test_complete_requires_hostname_and_ip(self):
        request_obj = ResourceRequest.objects.create(
            title='Host request without delivery target',
            applicant='cmdb-admin',
            approver='cmdb-admin',
            resource_type='host',
            specification='2C4G',
            business_line='core',
            environment='prod',
            priority='medium',
            quantity=1,
            status='approved',
            reason='missing delivery info',
            specs={'os_type': 'Linux'},
            approved_at=timezone.now(),
        )

        response = self.client.post(
            f'/api/cmdb/resource-requests/{request_obj.id}/complete/',
            {'note': 'try to fulfill'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.json())
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, 'approved')
        self.assertEqual(Host.objects.count(), 0)

    def test_submitter_only_sees_own_requests(self):
        ensure_builtin_rbac()
        submit_permission = PermissionDefinition.objects.get(code='cmdb.request.submit')
        role = Role.objects.create(code='request-submit-only', name='Request Submit Only')
        role.permissions.add(submit_permission)

        submitter = get_user_model().objects.create_user('submitter', 'submitter@example.com', 'Admin@123456')
        role.users.add(submitter)

        ResourceRequest.objects.create(
            title='我的申请',
            applicant='submitter',
            resource_type='主机',
            business_line='core',
            environment='prod',
            reason='self',
        )
        ResourceRequest.objects.create(
            title='someone else request',
            applicant='someone-else',
            resource_type='Redis',
            business_line='core',
            environment='test',
            reason='other',
        )

        self.client.force_login(submitter)
        response = self.client.get('/api/cmdb/resource-requests/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = payload['results'] if 'results' in payload else payload
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['applicant'], 'submitter')

    def test_submitter_can_read_resource_node_tree_for_request_form(self):
        ensure_builtin_rbac()
        submit_permission = PermissionDefinition.objects.get(code='cmdb.request.submit')
        role = Role.objects.create(code='request-submit-tree-only', name='Request Submit Tree Only')
        role.permissions.add(submit_permission)
        submitter = get_user_model().objects.create_user('tree-submitter', 'tree-submitter@example.com', 'Admin@123456')
        role.users.add(submitter)

        ci_type = _ci_type('资源树统计云主机', code='TREE_COUNT_CLOUD_SERVER')
        ConfigItem.objects.create(
            name='tree-count-ecs-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
        )
        ResourceRequest.objects.create(
            title='tree-count request',
            applicant='cmdb-admin',
            resource_type='主机',
            business_line='core',
            environment='prod',
            reason='tree count coverage',
        )

        self.client.force_login(submitter)
        response = self.client.get('/api/cmdb/resource-nodes/tree/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['name'], 'core')
        self.assertEqual(response.json()[0]['resource_count'], 1)
        self.assertEqual(response.json()[0]['request_count'], 1)
        self.assertEqual(response.json()[0]['children'][0]['name'], 'prod')
        self.assertEqual(response.json()[0]['children'][0]['resource_count'], 1)
        self.assertEqual(response.json()[0]['children'][0]['request_count'], 1)

    def test_resource_node_rejects_invalid_tree_shape(self):
        no_parent_response = self.client.post('/api/cmdb/resource-nodes/', {
            'name': 'stage',
            'node_type': 'env',
        })
        duplicate_response = self.client.post('/api/cmdb/resource-nodes/', {
            'name': 'core',
            'node_type': 'biz',
        })
        prod = ResourceNode.objects.get(name='prod', node_type='env')
        nested_response = self.client.post('/api/cmdb/resource-nodes/', {
            'name': 'gray',
            'node_type': 'env',
            'parent': prod.id,
        })

        self.assertEqual(no_parent_response.status_code, 400)
        self.assertIn('parent', no_parent_response.json())
        self.assertEqual(duplicate_response.status_code, 400)
        self.assertIn('name', duplicate_response.json())
        self.assertEqual(nested_response.status_code, 400)
        self.assertIn('parent', nested_response.json())

    def test_resource_node_tree_supports_manual_cloud_dimension(self):
        account_response = self.client.post('/api/cmdb/resource-nodes/', {
            'name': 'aliyun-prod',
            'node_type': 'cloud_account',
        })
        self.assertEqual(account_response.status_code, 201, account_response.content)

        region_response = self.client.post('/api/cmdb/resource-nodes/', {
            'name': 'cn-hangzhou',
            'node_type': 'cloud_region',
            'parent': account_response.json()['id'],
        })
        self.assertEqual(region_response.status_code, 201, region_response.content)

        default_tree_response = self.client.get('/api/cmdb/resource-nodes/tree/')
        self.assertEqual(default_tree_response.status_code, 200)
        self.assertEqual([item['node_type'] for item in default_tree_response.json()], ['biz'])

        all_tree_response = self.client.get('/api/cmdb/resource-nodes/tree/?scope=all')
        self.assertEqual(all_tree_response.status_code, 200)
        payload = all_tree_response.json()
        self.assertEqual(payload['business'][0]['name'], 'core')
        self.assertEqual(payload['cloud'][0]['name'], 'aliyun-prod')
        self.assertEqual(payload['cloud'][0]['children'][0]['name'], 'cn-hangzhou')

    def test_resource_node_delete_is_protected_when_in_use(self):
        core = ResourceNode.objects.get(name='core', node_type='biz')
        prod = ResourceNode.objects.get(name='prod', node_type='env')
        delete_biz_response = self.client.delete(f'/api/cmdb/resource-nodes/{core.id}/')

        self.assertEqual(delete_biz_response.status_code, 400)
        self.assertIn('detail', delete_biz_response.json())

        ResourceRequest.objects.create(
            title='prod host request',
            applicant='cmdb-admin',
            resource_type='主机',
            business_line='core',
            environment='prod',
            reason='delete protection',
        )
        delete_env_response = self.client.delete(f'/api/cmdb/resource-nodes/{prod.id}/')

        self.assertEqual(delete_env_response.status_code, 400)
        self.assertIn('detail', delete_env_response.json())

    def test_request_api_accepts_supported_cloud_resources_and_rejects_unknown_types(self):
        response = self.client.post(
            '/api/cmdb/resource-requests/',
            {
                'title': '申请 Redis',
                'resource_type': 'Redis',
                'business_line': 'core',
                'environment': 'prod',
                'reason': 'not allowed',
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['resource_type'], 'redis')
        invalid = self.client.post('/api/cmdb/resource-requests/', {
            'title': '不支持的类型', 'resource_type': 'unsupported-resource', 'reason': 'validation',
        })
        self.assertEqual(invalid.status_code, 400)
        self.assertIn('resource_type', invalid.json())


class CmdbSearchAndSyncTests(AuthenticatedTestCase):
    def test_ci_type_list_hides_alias_rows(self):
        _ci_type('云主机(ECS)', code='CLOUD_SERVER', color='#64748b')
        CIType.objects.create(name='云主机', color='#64748b')
        _ci_type('K8s 集群', color='#0ea5e9')
        CIType.objects.create(name='K8s集群', color='#0ea5e9')

        response = self.client.get('/api/cmdb/ci-types/')
        self.assertEqual(response.status_code, 200)

        names = [item['name'] for item in response.json()]
        self.assertEqual(names.count('云主机(ECS)'), 1)
        self.assertEqual(names.count('K8s 集群'), 1)
        self.assertNotIn('云主机', names)
        self.assertNotIn('K8s集群', names)
        cloud_row = next(item for item in response.json() if item['name'] == '云主机(ECS)')
        self.assertEqual(cloud_row['code'], 'CLOUD_SERVER')

    def test_config_item_api_search_supports_ip_and_ci_type_name(self):
        ci_type = _ci_type('云主机(ECS)')
        ConfigItem.objects.create(
            name='order-api-ecs-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='sre-core',
            status='active',
            attributes={
                'ip_address': '192.0.2.1',
                'description': '订单服务生产主机',
                'instance_type': 'ecs.g7.large',
            },
        )

        response = self.client.get('/api/cmdb/config-items/', {'search': '192.0.2.1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)

        response = self.client.get('/api/cmdb/config-items/', {'search': '云主机'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)

    def test_config_item_api_default_page_size_is_ten(self):
        ci_type = _ci_type('分页云主机', code='PAGE_CLOUD_SERVER')
        for index in range(25):
            ConfigItem.objects.create(
                name=f'page-ecs-{index:02d}',
                ci_type=ci_type,
                business_line='core',
                environment='prod',
                admin_user='sre-core',
                status='active',
            )

        response = self.client.get('/api/cmdb/config-items/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 25)
        self.assertEqual(len(payload['results']), 10)

    def test_config_item_api_filters_phase_one_ledger_dimensions(self):
        ci_type = _ci_type('筛选云主机', code='FILTER_CLOUD_SERVER')
        matched = ConfigItem.objects.create(
            name='filter-prod-ecs-01',
            ci_type=ci_type,
            business_line='order-system',
            environment='prod',
            admin_user='sre-core',
            status='active',
            attributes={
                'department': '基础架构部',
                'system': 'order-system',
                'private_ip': '10.77.1.8',
                'zone_id': 'cn-hangzhou-h',
            },
        )
        other = ConfigItem.objects.create(
            name='filter-test-ecs-01',
            ci_type=ci_type,
            business_line='payment-system',
            environment='test',
            admin_user='sre-pay',
            status='idle',
            attributes={
                'department': '支付部',
                'system': 'payment-system',
                'zone_id': 'cn-beijing-a',
            },
        )
        CISourceMapping.objects.create(
            ci=matched,
            source_type='aliyun_ecs',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='i-filter-001',
            sync_status='success',
            last_seen_at=timezone.now(),
        )
        CISourceMapping.objects.create(
            ci=other,
            source_type='aliyun_ecs',
            source_account='test-account',
            source_region='cn-beijing',
            source_unique_id='i-filter-002',
            sync_status='success',
            last_seen_at=timezone.now(),
        )

        response = self.client.get('/api/cmdb/config-items/', {
            'ci_type': ci_type.id,
            'source_type': 'aliyun_ecs',
            'source_account': 'prod-account',
            'source_region': 'cn-hangzhou',
            'availability_zone': 'cn-hangzhou-h',
            'environment': 'prod',
            'department': '基础架构部',
            'system': 'order-system',
            'admin_user': 'sre-core',
            'status': 'active',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['id'], matched.id)
        row = payload['results'][0]
        self.assertEqual(row['source_label'], 'aliyun_ecs')
        self.assertEqual(row['source_type'], 'aliyun_ecs')
        self.assertEqual(row['source_sync_status'], 'success')
        self.assertEqual(row['source_unique_id'], 'i-filter-001')
        self.assertEqual(row['source_mappings'][0]['source_account'], 'prod-account')
        self.assertEqual(row['source_mappings'][0]['source_region'], 'cn-hangzhou')
        self.assertTrue(row['last_seen_at'])

    def test_config_item_api_ownership_filter_matches_department_or_owner_only(self):
        ci_type = _ci_type('归属筛选资产', code='OWNERSHIP_FILTER_ASSET')
        department_match = ConfigItem.objects.create(
            name='ownership-department-match',
            ci_type=ci_type,
            business_line='business-only',
            environment='prod',
            admin_user='ops-a',
            attributes={'department': '平台运维部'},
        )
        owner_match = ConfigItem.objects.create(
            name='ownership-owner-match',
            ci_type=ci_type,
            business_line='other-business',
            environment='prod',
            admin_user='平台负责人',
            attributes={'department': '其他部门'},
        )
        ConfigItem.objects.create(
            name='ownership-business-line-only',
            ci_type=ci_type,
            business_line='平台业务线',
            environment='prod',
            admin_user='ops-b',
            attributes={'department': '交付部'},
        )

        response = self.client.get('/api/cmdb/config-items/', {'ci_type': ci_type.id, 'ownership': '平台'})

        self.assertEqual(response.status_code, 200)
        result_ids = {item['id'] for item in response.json()['results']}
        self.assertEqual(result_ids, {department_match.id, owner_match.id})

    def test_config_item_api_fills_standard_ip_from_private_ip(self):
        ci_type = CIType.objects.create(name='云数据库')
        ConfigItem.objects.create(
            name='shared-rds-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            status='active',
            attributes={'private_ip': '10.20.2.20'},
        )

        response = self.client.get('/api/cmdb/config-items/', {'search': '10.20.2.20'})
        self.assertEqual(response.status_code, 200)
        row = response.json()['results'][0]
        self.assertEqual(row['attributes']['ip_address'], '10.20.2.20')

    def test_database_and_redis_ledger_filters_sync_network_and_engine(self):
        mysql_type, _ = CIType.objects.get_or_create(code='MYSQL', defaults={'name': 'MySQL/RDS'})
        redis_type, _ = CIType.objects.get_or_create(code='REDIS', defaults={'name': 'Redis'})
        rds = ConfigItem.objects.create(
            name='rds-prod-order',
            ci_type=mysql_type,
            business_line='core',
            environment='prod',
            admin_user='dba',
            status='active',
            attributes={
                'engine': 'MySQL',
                'version': '8.0',
                'instance_class': 'mysql.n2.medium',
                'storage_gb': 200,
                'storage_usage': 82,
                'vpc_id': 'vpc-rds-001',
                'network_type': 'Intranet',
            },
        )
        redis = ConfigItem.objects.create(
            name='redis-prod-cache',
            ci_type=redis_type,
            business_line='core',
            environment='prod',
            admin_user='dba',
            status='active',
            attributes={
                'engine': 'Redis',
                'version': '7.0',
                'instance_class': 'redis.master.small',
                'memory_gb': 16,
                'memory_usage': 72,
                'vpc_id': 'vpc-redis-001',
                'network_type': 'VPC',
            },
        )
        CISourceMapping.objects.create(
            ci=rds,
            source_type='aliyun_rds',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='rm-rds-prod-order',
            sync_status='success',
        )
        CISourceMapping.objects.create(
            ci=redis,
            source_type='aliyun_redis',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='r-redis-prod-cache',
            sync_status='failed',
        )

        response = self.client.get('/api/cmdb/config-items/', {
            'ci_type': mysql_type.id,
            'engine': 'MySQL',
            'vpc_id': 'vpc-rds-001',
            'network_type': 'Intranet',
            'sync_status': 'success',
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['id'], rds.id)
        self.assertEqual(payload['results'][0]['source_sync_status'], 'success')
        self.assertEqual(payload['results'][0]['attributes']['storage_gb'], 200)
        self.assertEqual(payload['results'][0]['attributes']['vpc_id'], 'vpc-rds-001')

        response = self.client.get('/api/cmdb/config-items/', {
            'ci_type': redis_type.id,
            'engine': 'Redis',
            'vpc_id': 'vpc-redis-001',
            'network_type': 'VPC',
            'sync_status': 'failed',
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['id'], redis.id)
        self.assertEqual(payload['results'][0]['source_sync_status'], 'failed')
        self.assertEqual(payload['results'][0]['attributes']['memory_gb'], 16)

    def test_p1_cloud_service_ledger_filters_storage_network_and_sync(self):
        oss_type, _ = CIType.objects.get_or_create(code='OBJECT_STORAGE', defaults={'name': '对象存储'})
        lb_type, _ = CIType.objects.get_or_create(code='LOAD_BALANCER', defaults={'name': '负载均衡'})
        bucket = ConfigItem.objects.create(
            name='prod-order-bucket',
            ci_type=oss_type,
            business_line='order',
            environment='prod',
            admin_user='storage-admin',
            status='active',
            attributes={
                'bucket': 'prod-order-bucket',
                'endpoint': 'https://oss-cn-hangzhou.aliyuncs.com',
                'storage_gb': 2048,
                'storage_class': 'Standard',
                'acl': 'private',
            },
        )
        load_balancer = ConfigItem.objects.create(
            name='prod-order-slb',
            ci_type=lb_type,
            business_line='order',
            environment='prod',
            admin_user='netops',
            status='active',
            attributes={
                'instance_id': 'lb-prod-order',
                'vip': '47.100.10.8',
                'vpc_id': 'vpc-edge-001',
                'network_type': 'internet',
                'bandwidth': 200,
            },
        )
        CISourceMapping.objects.create(
            ci=bucket,
            source_type='aliyun_oss',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='prod-order-bucket',
            sync_status='success',
        )
        CISourceMapping.objects.create(
            ci=load_balancer,
            source_type='aliyun_slb',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='lb-prod-order',
            sync_status='failed',
        )

        response = self.client.get('/api/cmdb/config-items/', {
            'ci_type': oss_type.id,
            'storage_class': 'Standard',
            'acl': 'private',
            'sync_status': 'success',
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['id'], bucket.id)
        self.assertEqual(payload['results'][0]['attributes']['storage_class'], 'Standard')
        self.assertEqual(payload['results'][0]['source_sync_status'], 'success')

        response = self.client.get('/api/cmdb/config-items/', {
            'ci_type': lb_type.id,
            'vpc_id': 'vpc-edge-001',
            'network_type': 'internet',
            'sync_status': 'failed',
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['id'], load_balancer.id)
        self.assertEqual(payload['results'][0]['attributes']['vip'], '47.100.10.8')
        self.assertEqual(payload['results'][0]['source_sync_status'], 'failed')

    def test_resource_search_matches_attributes_and_source_identity(self):
        ci_type = _ci_type('云主机(ECS)', code='CLOUD_SERVER', color='#64748b')
        ci = ConfigItem.objects.create(
            name='order-api-ecs-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='sre-core',
            status='active',
            attributes={
                'private_ip': '10.30.1.10',
                'instance_id': 'i-order-001',
                'description': '订单服务生产主机',
            },
        )
        CISourceMapping.objects.create(
            ci=ci,
            source_type='aliyun_ecs',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='i-order-001',
        )

        response = self.client.get('/api/cmdb/search/', {'q': '10.30.1.10'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['total'], 1)
        self.assertEqual(payload['results'][0]['name'], 'order-api-ecs-01')
        self.assertIn('private_ip', payload['results'][0]['key_attributes'])
        self.assertTrue(any(item['field'] == 'attributes.private_ip' for item in payload['results'][0]['matched_fields']))

        response = self.client.get('/api/cmdb/search/', {'q': 'prod-account'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['total'], 1)
        self.assertEqual(payload['results'][0]['source_type'], 'aliyun_ecs')
        self.assertTrue(any(item['field'] == 'source_account' for item in payload['results'][0]['matched_fields']))

    def test_tag_management_filters_resources_and_searches_tags(self):
        ci_type = _ci_type('云主机(ECS)', code='CLOUD_SERVER', color='#64748b')
        response = self.client.post('/api/cmdb/tags/', {
            'name': '核心系统',
            'category': '业务',
            'color': '#245bdb',
            'description': '核心链路资源',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        tag_id = response.json()['id']

        response = self.client.post('/api/cmdb/config-items/', {
            'name': 'tagged-ecs-01',
            'ci_type': ci_type.id,
            'business_line': 'core',
            'environment': 'prod',
            'admin_user': 'ops',
            'status': 'active',
            'tags': [tag_id],
            'attributes': {'private_ip': '10.40.1.20', 'instance_id': 'i-tagged-001'},
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['tag_items'][0]['name'], '核心系统')

        response = self.client.get('/api/cmdb/config-items/', {'tags': tag_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['name'], 'tagged-ecs-01')

        response = self.client.get('/api/cmdb/search/', {'q': '核心系统'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['total'], 1)
        self.assertEqual(payload['results'][0]['tag_items'][0]['name'], '核心系统')
        self.assertTrue(any(item['field'] == 'tags' for item in payload['results'][0]['matched_fields']))

        response = self.client.get('/api/cmdb/dashboard/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['name'] == '核心系统' and item['count'] == 1 for item in response.json()['ci_by_tag']))

        response = self.client.delete(f'/api/cmdb/tags/{tag_id}/')
        self.assertEqual(response.status_code, 400, response.content)
        self.assertTrue(
            CITag.objects.filter(id=tag_id, is_active=True).exists(),
            f'{response.content} {list(CITag.objects.values("id", "name", "is_active"))}',
        )

    def test_repository_summary_groups_models_and_counts_governance_risks(self):
        group = CIModelGroup.objects.create(name='仓库测试模型', code='repo_asset', is_builtin=True)
        cloud_type = _ci_type('仓库测试云主机', code='REPO_CLOUD_SERVER', color='#64748b', group=group)
        db_type = _ci_type('仓库测试Redis', code='REPO_REDIS', color='#dc2626', group=group)
        cloud_ci = ConfigItem.objects.create(
            name='repo-ecs-01',
            ci_type=cloud_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
        )
        ConfigItem.objects.create(
            name='repo-ecs-02',
            ci_type=cloud_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'department': 'ops', 'source_type': 'manual'},
        )
        db_ci = ConfigItem.objects.create(
            name='repo-redis-01',
            ci_type=db_type,
            business_line='',
            environment='prod',
            admin_user='',
            status='active',
        )
        CICompletionIssue.objects.create(
            ci=db_ci,
            missing_fields=[
                {'code': 'business_line', 'name': '业务线'},
                {'code': 'department', 'name': '部门'},
            ],
            severity='medium',
            status='open',
        )
        CIArchiveCandidate.objects.create(ci=cloud_ci, source_type='aliyun_ecs', reason='来源端消失')
        CISyncRecord.objects.create(
            job=CISyncJob.objects.create(name='repo-sync', source_type='aliyun_ecs', created_by='tester'),
            ci=cloud_ci,
            action='update',
            status='failed',
            source_unique_id='repo-ecs-01',
            error_message='同步失败',
        )

        response = self.client.get('/api/cmdb/repository/summary/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload['summary']['group_count'], 1)
        self.assertGreaterEqual(payload['summary']['model_count'], 2)
        self.assertGreaterEqual(payload['summary']['resource_count'], 3)
        self.assertEqual(payload['summary']['risk_count'], 3)

        asset_group = next(item for item in payload['groups'] if item['code'] == 'repo_asset')
        self.assertEqual(asset_group['name'], '仓库测试模型')
        self.assertEqual(asset_group['quality_score'], 33)
        cloud_model = next(item for item in asset_group['models'] if item['code'] == 'REPO_CLOUD_SERVER')
        redis_model = next(item for item in asset_group['models'] if item['code'] == 'REPO_REDIS')
        self.assertEqual(cloud_model['ci_count'], 2)
        self.assertEqual(cloud_model['archive_candidate_count'], 1)
        self.assertEqual(cloud_model['sync_failure_count'], 1)
        self.assertEqual(cloud_model['quality_score'], 42)
        self.assertEqual(cloud_model['quality_risk_count'], 2)
        self.assertEqual(cloud_model['quality_issue_counts']['no_relation'], 2)
        self.assertEqual(redis_model['quality_score'], 15)
        self.assertEqual(redis_model['completion_issue_count'], 1)
        self.assertEqual(redis_model['quality_risk_count'], 1)

    def test_model_tree_returns_grouped_models_fields_and_resource_counts(self):
        group = CIModelGroup.objects.create(name='模型树计算资源', code='tree_compute', sort_order=10, is_builtin=True)
        cloud_type = _ci_type('模型树云主机', code='TREE_CLOUD_SERVER', color='#64748b', group=group)
        redis_type = _ci_type('模型树Redis', code='TREE_REDIS', color='#dc2626', group=group)
        ungrouped_type = _ci_type('模型树未分组服务', code='TREE_UNGROUPED_SERVICE', color='#7c3aed')
        CIField.objects.create(
            ci_type=cloud_type,
            name='实例 ID',
            code='instance_id',
            field_type='string',
            required=True,
            unique=True,
            is_searchable=True,
            sort_order=10,
        )
        CIField.objects.create(
            ci_type=cloud_type,
            name='私网 IP',
            code='private_ip',
            field_type='ip',
            required=True,
            is_searchable=True,
            sort_order=20,
        )
        CIField.objects.create(ci_type=redis_type, name='连接地址', code='endpoint', field_type='string', required=True)
        ConfigItem.objects.create(
            name='tree-ecs-01',
            ci_type=cloud_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            attributes={'department': '基础架构部', 'instance_id': 'i-tree-001', 'private_ip': '10.66.1.8'},
        )
        redis = ConfigItem.objects.create(
            name='tree-redis-01',
            ci_type=redis_type,
            business_line='',
            environment='prod',
            admin_user='',
        )
        ConfigItem.objects.create(
            name='tree-unclassified-service',
            ci_type=ungrouped_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
        )
        CICompletionIssue.objects.create(
            ci=redis,
            missing_fields=[{'code': 'business_line', 'name': '业务线'}],
            severity='high',
            status='open',
        )

        response = self.client.get('/api/cmdb/model-tree/', {'include_fields': 'true'})

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['source'], 'model_tree')
        self.assertIn('tree', payload)
        self.assertGreaterEqual(payload['summary']['model_count'], 3)
        tree_group = next(item for item in payload['tree'] if item['code'] == 'tree_compute')
        self.assertEqual(tree_group['node_type'], 'group')
        self.assertEqual(tree_group['model_count'], 2)
        self.assertEqual(tree_group['resource_count'], 2)
        cloud_node = next(item for item in tree_group['children'] if item['code'] == 'TREE_CLOUD_SERVER')
        redis_node = next(item for item in tree_group['children'] if item['code'] == 'TREE_REDIS')
        self.assertEqual(cloud_node['node_type'], 'model')
        self.assertEqual(cloud_node['ci_count'], 1)
        self.assertEqual(cloud_node['field_count'], 2)
        self.assertEqual(cloud_node['required_field_count'], 2)
        self.assertEqual(cloud_node['unique_field_count'], 1)
        self.assertGreaterEqual(redis_node['risk_count'], 1)
        group_payload = next(item for item in payload['groups'] if item['code'] == 'tree_compute')
        cloud_model = next(item for item in group_payload['models'] if item['code'] == 'TREE_CLOUD_SERVER')
        self.assertEqual([field['code'] for field in cloud_model['fields']], ['instance_id', 'private_ip'])
        ungrouped = next(item for item in payload['tree'] if item['code'] == 'ungrouped')
        self.assertTrue(any(child['code'] == 'TREE_UNGROUPED_SERVICE' for child in ungrouped['children']))

    def test_island_analysis_detects_unowned_unrelated_and_unbound_resources(self):
        cloud_type = _ci_type('弹性 IP', code='EIP', color='#f59e0b')
        app_type = _ci_type('应用', code='APP', color='#245bdb')
        db_type = _ci_type('Redis', code='REDIS', color='#dc2626')
        host_type = _ci_type('云主机(ECS)', code='CLOUD_SERVER', color='#64748b')
        orphan_eip = ConfigItem.objects.create(
            name='eip-orphan-01',
            ci_type=cloud_type,
            business_line='',
            environment='prod',
            admin_user='',
            attributes={'public_ip': '39.1.1.1'},
        )
        app = ConfigItem.objects.create(
            name='order-app',
            ci_type=app_type,
            business_line='core',
            environment='prod',
            admin_user='app-owner',
        )
        db = ConfigItem.objects.create(
            name='redis-orphan-01',
            ci_type=db_type,
            business_line='',
            environment='prod',
            admin_user='',
            attributes={'endpoint': 'redis.example.internal'},
        )
        host = ConfigItem.objects.create(
            name='bound-ecs-01',
            ci_type=host_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            attributes={'instance_id': 'i-bound-001', 'private_ip': '10.0.1.8', 'department': '基础架构部'},
        )
        CISourceMapping.objects.create(
            ci=host,
            source_type='aliyun_ecs',
            source_account='prod',
            source_region='cn-hangzhou',
            source_unique_id='i-bound-001',
        )
        CIRelation.objects.create(source=app, target=host, relation_type='runs_on')

        response = self.client.get('/api/cmdb/island-analysis/')
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertGreaterEqual(payload['summary']['total'], 1)
        self.assertGreaterEqual(payload['summary']['missing_ownership'], 2)
        self.assertGreaterEqual(payload['summary']['unbound_cloud_resource'], 1)
        self.assertGreaterEqual(payload['summary']['unlinked_data_service'], 1)

        by_ci = {}
        for item in payload['results']:
            by_ci.setdefault(item['ci_id'], set()).add(item['issue_type'])
        self.assertIn('missing_ownership', by_ci[orphan_eip.id])
        self.assertIn('unbound_cloud_resource', by_ci[orphan_eip.id])
        self.assertIn('unlinked_data_service', by_ci[db.id])
        self.assertNotIn(host.id, by_ci)

        response = self.client.get('/api/cmdb/dashboard/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('island_resources', response.json()['risk_summary'])

    def test_island_analysis_detects_missing_required_relation_rules(self):
        app_type = _ci_type('应用', code='APP', color='#245bdb')
        host_type = _ci_type('云主机(ECS)', code='CLOUD_SERVER', color='#64748b')
        queue_type = _ci_type('消息队列', code='QUEUE', color='#0f766e')
        db_type = _ci_type('数据库', code='DATABASE', color='#9333ea')
        CIRelationRule.objects.create(
            source_type=app_type,
            target_type=host_type,
            relation_type='runs_on',
            direction='outgoing',
            required=True,
            multiple=True,
            is_active=True,
        )
        CIRelationRule.objects.create(
            source_type=queue_type,
            target_type=db_type,
            relation_type='depends_on',
            direction='outgoing',
            required=True,
            multiple=True,
            is_active=True,
        )
        app = ConfigItem.objects.create(
            name='order-app',
            ci_type=app_type,
            business_line='core',
            environment='prod',
            admin_user='app-owner',
            attributes={'source_type': 'manual', 'source_unique_id': 'app-order'},
        )
        host = ConfigItem.objects.create(
            name='order-ecs-01',
            ci_type=host_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            attributes={'source_type': 'manual', 'source_unique_id': 'ecs-order-01', 'instance_id': 'i-order-01'},
        )
        queue = ConfigItem.objects.create(
            name='order-mq',
            ci_type=queue_type,
            business_line='core',
            environment='prod',
            admin_user='mq-owner',
            attributes={'source_type': 'manual', 'source_unique_id': 'mq-order'},
        )

        response = self.client.get('/api/cmdb/island-analysis/')
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertGreaterEqual(payload['summary']['missing_required_relation'], 1)
        self.assertGreaterEqual(payload['summary']['relation_auto_candidate_count'], 1)
        self.assertGreaterEqual(payload['summary']['relation_manual_required_count'], 1)
        self.assertGreater(payload['summary']['candidate_coverage_rate'], 0)
        by_ci = {}
        missing_relation_issue = None
        manual_relation_issue = None
        for item in payload['results']:
            by_ci.setdefault(item['ci_id'], set()).add(item['issue_type'])
            if item['ci_id'] == app.id and item['issue_type'] == 'missing_required_relation' and item['relation_type'] == 'runs_on':
                missing_relation_issue = item
            if item['ci_id'] == queue.id and item['issue_type'] == 'missing_required_relation':
                manual_relation_issue = item
        self.assertIn('missing_required_relation', by_ci[app.id])
        self.assertIsNotNone(missing_relation_issue)
        self.assertEqual(missing_relation_issue['relation_type'], 'runs_on')
        self.assertEqual(missing_relation_issue['relation_direction'], 'outgoing')
        self.assertEqual(missing_relation_issue['peer_type'], host_type.id)
        self.assertEqual(missing_relation_issue['candidate_count'], 1)
        self.assertTrue(missing_relation_issue['can_auto_create'])
        self.assertEqual(missing_relation_issue['governance_status'], 'auto_candidate')
        self.assertEqual(missing_relation_issue['best_candidate']['id'], host.id)
        self.assertEqual(missing_relation_issue['relation_candidates'][0]['id'], host.id)
        self.assertIn('同业务线', missing_relation_issue['relation_candidates'][0]['reasons'])
        self.assertIsNotNone(manual_relation_issue)
        self.assertEqual(manual_relation_issue['candidate_count'], 0)
        self.assertFalse(manual_relation_issue['can_auto_create'])
        self.assertEqual(manual_relation_issue['governance_status'], 'manual_required')
        self.assertEqual(manual_relation_issue['relation_candidates'], [])

        dashboard_response = self.client.get('/api/cmdb/dashboard/stats/')
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertNotIn('island_resources', dashboard_response.json()['risk_summary'])

        CIRelation.objects.create(source=app, target=host, relation_type='runs_on')

        response = self.client.get('/api/cmdb/island-analysis/')
        self.assertEqual(response.status_code, 200, response.content)
        by_ci = {}
        for item in response.json()['results']:
            by_ci.setdefault(item['ci_id'], set()).add(item['issue_type'])
        self.assertNotIn('missing_required_relation', by_ci.get(app.id, set()))

    def test_island_analysis_detects_duplicate_unique_field_values(self):
        host_type = _ci_type('云主机(ECS)', code='CLOUD_SERVER', color='#64748b')
        CIField.objects.create(
            ci_type=host_type,
            name='治理唯一标识',
            code='governance_uid',
            field_type='string',
            unique=True,
            is_active=True,
        )
        first = ConfigItem.objects.create(
            name='duplicate-ecs-01',
            ci_type=host_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            attributes={
                'department': '基础架构部',
                'source_type': 'manual',
                'source_unique_id': 'duplicate-ecs-01',
                'governance_uid': 'i-duplicate-governance',
            },
        )
        second = ConfigItem.objects.create(
            name='duplicate-ecs-02',
            ci_type=host_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            attributes={
                'department': '基础架构部',
                'source_type': 'manual',
                'source_unique_id': 'duplicate-ecs-02',
                'governance_uid': 'i-duplicate-governance',
            },
        )
        CIRelation.objects.create(source=first, target=second, relation_type='same_cluster')

        response = self.client.get('/api/cmdb/island-analysis/')
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertGreaterEqual(payload['summary']['duplicate_unique_field'], 2)
        duplicate_rows = [
            item for item in payload['results']
            if item['issue_type'] == 'duplicate_unique_field'
        ]
        duplicate_ids = {item['ci_id'] for item in duplicate_rows}
        self.assertIn(first.id, duplicate_ids)
        self.assertIn(second.id, duplicate_ids)
        row = duplicate_rows[0]
        self.assertEqual(row['duplicate_field_code'], 'governance_uid')
        self.assertEqual(row['duplicate_field_name'], '治理唯一标识')
        self.assertEqual(row['duplicate_value'], 'i-duplicate-governance')
        self.assertCountEqual(row['duplicate_ci_ids'], [first.id, second.id])
        self.assertCountEqual(row['duplicate_ci_names'], [first.name, second.name])

    def test_config_item_merge_duplicates_closes_duplicate_governance_loop(self):
        host_type = _ci_type('合并云主机', code='MERGE_CLOUD_SERVER', color='#64748b')
        app_type = _ci_type('合并应用', code='MERGE_APP', color='#245bdb')
        CIField.objects.create(
            ci_type=host_type,
            name='治理唯一标识',
            code='governance_uid',
            field_type='string',
            unique=True,
            is_active=True,
        )
        core_tag = CITag.objects.create(name='核心系统', category='业务')
        source_tag = CITag.objects.create(name='csv', category='source')
        target = ConfigItem.objects.create(
            name='merge-ecs-master',
            ci_type=host_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            attributes={
                'department': '基础架构部',
                'governance_uid': 'i-merge-001',
                'private_ip': '10.60.1.8',
            },
        )
        target.tags.add(core_tag)
        duplicate = ConfigItem.objects.create(
            name='merge-ecs-duplicate',
            ci_type=host_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            attributes={
                'governance_uid': 'i-merge-001',
                'source_unique_id': 'i-merge-001-dup',
                'cpu': 8,
            },
        )
        duplicate.tags.add(source_tag)
        app = ConfigItem.objects.create(
            name='merge-app',
            ci_type=app_type,
            business_line='core',
            environment='prod',
            admin_user='app-owner',
        )
        CISourceMapping.objects.create(
            ci=duplicate,
            source_type='csv_import',
            source_account='cmdb',
            source_region='local',
            source_unique_id='i-merge-001-dup',
        )
        CIRelation.objects.create(source=duplicate, target=app, relation_type='runs_on')
        CIRelation.objects.create(source=target, target=duplicate, relation_type='same_cluster')
        CostRecord.objects.create(ci=duplicate, month='2026-07', amount=Decimal('99.50'), provider='csv')
        CIResourceMetricSnapshot.objects.create(
            ci=duplicate,
            metric='cpu',
            value=50,
            usage_percent=50,
            collected_at=timezone.now(),
            source='monitor',
        )
        CICompletionIssue.objects.create(
            ci=duplicate,
            missing_fields=[{'code': 'department', 'name': '部门'}],
            severity='medium',
        )

        before = self.client.get('/api/cmdb/island-analysis/')
        self.assertGreaterEqual(before.json()['summary']['duplicate_unique_field'], 2)

        response = self.client.post(
            f'/api/cmdb/config-items/{target.id}/merge-duplicates/',
            {
                'source_ids': [duplicate.id],
                'reason': '治理唯一标识重复，确认是同一台云主机',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['detail'], '重复资源已合并')
        self.assertEqual(payload['summary']['target']['id'], target.id)
        self.assertEqual(payload['summary']['sources'][0]['id'], duplicate.id)
        self.assertEqual(payload['moved_counts']['source_mappings'], 1)
        self.assertEqual(payload['moved_counts']['cost_records'], 1)
        self.assertEqual(payload['moved_counts']['resource_metrics'], 1)
        self.assertEqual(payload['moved_counts']['completion_issues'], 1)

        target.refresh_from_db()
        duplicate.refresh_from_db()
        self.assertEqual(target.attributes['cpu'], 8)
        self.assertEqual(duplicate.status, 'offline')
        self.assertNotIn('governance_uid', duplicate.attributes)
        self.assertEqual(duplicate.attributes['merged_into_ci_id'], target.id)
        self.assertEqual(duplicate.attributes['merged_original_attributes']['governance_uid'], 'i-merge-001')
        self.assertTrue(target.tags.filter(name='核心系统').exists())
        self.assertTrue(target.tags.filter(name='csv').exists())
        self.assertTrue(CISourceMapping.objects.filter(ci=target, source_unique_id='i-merge-001-dup').exists())
        self.assertTrue(CostRecord.objects.filter(ci=target, amount=Decimal('99.50')).exists())
        self.assertTrue(CIResourceMetricSnapshot.objects.filter(ci=target, metric='cpu').exists())
        self.assertTrue(CICompletionIssue.objects.filter(ci=target, missing_fields__0__code='department').exists())
        self.assertTrue(CIRelation.objects.filter(source=target, target=app, relation_type='runs_on').exists())
        self.assertFalse(CIRelation.objects.filter(source=target, target=duplicate).exists())
        self.assertTrue(CIChangeLog.objects.filter(ci=target, action='merge_duplicates', source='governance').exists())

        after = self.client.get('/api/cmdb/island-analysis/')
        duplicate_rows = [
            item for item in after.json()['results']
            if item['issue_type'] == 'duplicate_unique_field'
            and item.get('duplicate_value') == 'i-merge-001'
        ]
        self.assertEqual(duplicate_rows, [])

    def test_view_summary_groups_application_host_and_physical_views(self):
        app_type = _ci_type('应用', code='APP', color='#245bdb')
        host_type = _ci_type('云主机(ECS)', code='CLOUD_SERVER', color='#64748b')
        physical_type = _ci_type('物理机', code='PHYSICAL_SERVER', color='#0f766e')
        app = ConfigItem.objects.create(
            name='payment-app',
            ci_type=app_type,
            business_line='payment',
            environment='prod',
            admin_user='app-owner',
        )
        host = ConfigItem.objects.create(
            name='payment-ecs-01',
            ci_type=host_type,
            business_line='payment',
            environment='prod',
            admin_user='ops',
            attributes={
                'private_ip': '10.50.1.8',
                'cpu': 8,
                'memory_gb': 16,
                'os': 'Linux',
                'agent_status': 'online',
            },
        )
        physical = ConfigItem.objects.create(
            name='phy-pay-01',
            ci_type=physical_type,
            business_line='payment',
            environment='prod',
            admin_user='dc-ops',
            attributes={
                'private_ip': '172.16.1.10',
                'machine_room': 'A机房',
                'rack': 'R01',
                'u_position': '12U',
                'asset_sn': 'SN-PHY-001',
            },
        )
        CIRelation.objects.create(source=app, target=host, relation_type='runs_on')
        CIRelation.objects.create(source=app, target=physical, relation_type='runs_on')

        response = self.client.get('/api/cmdb/views/summary/', {'business_line': 'payment'})
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['summary']['application_count'], 1)
        self.assertEqual(payload['summary']['host_count'], 2)
        self.assertEqual(payload['summary']['physical_location_count'], 1)
        self.assertEqual(payload['summary']['unowned_host_count'], 2)
        self.assertEqual(payload['applications'][0]['host_count'], 2)
        self.assertEqual(payload['hosts'][0]['business_line'], 'payment')
        self.assertTrue(all(item['environment_display'] == 'prod' for item in payload['hosts']))
        self.assertTrue(any(item['ip'] == '10.50.1.8' for item in payload['hosts']))
        physical_row = payload['physical'][0]
        self.assertEqual(physical_row['room'], 'A机房')
        self.assertEqual(physical_row['rack'], 'R01')
        self.assertEqual(physical_row['occupied_u'], 1)
        self.assertEqual(physical_row['hosts'][0]['name'], 'phy-pay-01')

    def test_resource_authorization_scopes_ci_search_and_views(self):
        ensure_builtin_rbac()
        role = Role.objects.create(code='cmdb-reader', name='CMDB Reader')
        role.permissions.add(
            PermissionDefinition.objects.get(code='cmdb.ci.view'),
            PermissionDefinition.objects.get(code='cmdb.dashboard.view'),
            PermissionDefinition.objects.get(code='cmdb.topology.view'),
            PermissionDefinition.objects.get(code='cmdb.audit.view'),
            PermissionDefinition.objects.get(code='cmdb.cost.view'),
        )
        user = get_user_model().objects.create_user('payment-viewer', password='Admin@123456')
        user.rbac_roles.add(role)

        app_type = _ci_type('授权应用', code='AUTH_APP')
        host_type = _ci_type('授权主机', code='AUTH_HOST')
        payment_app = ConfigItem.objects.create(name='pay-app', ci_type=app_type, business_line='payment', environment='prod', admin_user='owner')
        payment_host = ConfigItem.objects.create(
            name='pay-host-01',
            ci_type=host_type,
            business_line='payment',
            environment='prod',
            admin_user='ops',
            attributes={'cpu': 16, 'memory_gb': 32, 'avg_cpu_usage': 10, 'avg_memory_usage': 20},
        )
        hr_host = ConfigItem.objects.create(
            name='hr-host-01',
            ci_type=host_type,
            business_line='hr',
            environment='prod',
            admin_user='hr-ops',
            attributes={'cpu': 32, 'memory_gb': 64, 'avg_cpu_usage': 5, 'avg_memory_usage': 12},
        )
        CIRelation.objects.create(source=payment_app, target=payment_host, relation_type='runs_on')
        CIRelation.objects.create(source=payment_app, target=hr_host, relation_type='runs_on')
        current_month = timezone.now().strftime('%Y-%m')
        CostRecord.objects.create(ci=payment_host, month=current_month, amount=Decimal('1200.00'), provider='aliyun')
        CostRecord.objects.create(ci=hr_host, month=current_month, amount=Decimal('9000.00'), provider='aliyun')
        payment_log = CIChangeLog.objects.create(
            ci=payment_host,
            action='update',
            before={'admin_user': 'ops'},
            after={'admin_user': 'sre'},
            diff={'admin_user': {'before': 'ops', 'after': 'sre'}},
            operator='cmdb-admin',
            source='manual',
        )
        hr_log = CIChangeLog.objects.create(
            ci=hr_host,
            action='update',
            before={'admin_user': 'hr-ops'},
            after={'admin_user': 'hr-sre'},
            diff={'admin_user': {'before': 'hr-ops', 'after': 'hr-sre'}},
            operator='cmdb-admin',
            source='manual',
        )
        platform_log = CIChangeLog.objects.create(
            ci=None,
            action='sync_job_update',
            before={'name': 'sync'},
            after={'name': 'sync-updated'},
            diff={'name': {'before': 'sync', 'after': 'sync-updated'}},
            operator='cmdb-admin',
            source='sync_job',
        )
        CIResourceAuthorization.objects.create(
            name='支付业务查看',
            principal_type='user',
            principal='payment-viewer',
            permission='view',
            business_line='payment',
            created_by='cmdb-admin',
        )
        sync_job = CISyncJob.objects.create(name='授权范围失败同步', source_type='manual_import')
        CISyncRecord.objects.create(
            job=sync_job,
            ci=payment_host,
            action='fail',
            status='failed',
            source_unique_id='payment-failed-001',
        )
        CISyncRecord.objects.create(
            job=sync_job,
            ci=hr_host,
            action='fail',
            status='failed',
            source_unique_id='hr-failed-001',
        )
        CISyncRecord.objects.create(
            job=sync_job,
            action='fail',
            status='failed',
            source_unique_id='global-failed-001',
        )
        hidden_job = CISyncJob.objects.create(name='隐藏失败同步', source_type='manual_import')
        CISyncRecord.objects.create(
            job=hidden_job,
            ci=hr_host,
            action='fail',
            status='failed',
            source_unique_id='hr-hidden-failed-001',
        )

        self.client.force_login(user)

        list_response = self.client.get('/api/cmdb/config-items/', {'page_size': 100})
        self.assertEqual(list_response.status_code, 200)
        list_names = {item['name'] for item in list_response.json()['results']}
        self.assertIn('pay-host-01', list_names)
        self.assertNotIn('hr-host-01', list_names)

        search_response = self.client.get('/api/cmdb/search/', {'q': 'host'})
        self.assertEqual(search_response.status_code, 200)
        search_names = {item['name'] for item in search_response.json()['results']}
        self.assertEqual(search_names, {'pay-host-01'})

        view_response = self.client.get('/api/cmdb/views/summary/')
        self.assertEqual(view_response.status_code, 200)
        view_payload = view_response.json()
        self.assertEqual({item['name'] for item in view_payload['hosts']}, {'pay-host-01'})
        self.assertEqual(view_payload['applications'][0]['host_count'], 1)

        topology_response = self.client.get('/api/cmdb/topology/data/', {'business_line': 'payment'})
        self.assertEqual(topology_response.status_code, 200)
        topology_names = {item['name'] for item in topology_response.json()['nodes']}
        self.assertIn('pay-host-01', topology_names)
        self.assertNotIn('hr-host-01', topology_names)

        dashboard_response = self.client.get('/api/cmdb/dashboard/stats/')
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(dashboard_response.json()['ci_total'], 2)
        self.assertEqual(dashboard_response.json()['risk_summary']['sync_failures'], 1)

        audit_response = self.client.get('/api/cmdb/change-logs/', {'page_size': 100})
        self.assertEqual(audit_response.status_code, 200)
        audit_ci_names = {item['ci_name'] for item in audit_response.json()['results']}
        self.assertEqual(audit_ci_names, {'pay-host-01'})
        self.assertIn(str(payment_log.id), {str(item['id']) for item in audit_response.json()['results']})
        self.assertNotIn(str(hr_log.id), {str(item['id']) for item in audit_response.json()['results']})
        self.assertNotIn(str(platform_log.id), {str(item['id']) for item in audit_response.json()['results']})

        audit_summary_response = self.client.get('/api/cmdb/change-logs/summary/')
        self.assertEqual(audit_summary_response.status_code, 200)
        self.assertEqual(audit_summary_response.json()['total'], 1)

        forbidden_audit_response = self.client.get(f'/api/cmdb/change-logs/{hr_log.id}/')
        self.assertEqual(forbidden_audit_response.status_code, 404)

        cost_list_response = self.client.get('/api/cmdb/cost-records/', {'page_size': 100})
        self.assertEqual(cost_list_response.status_code, 200)
        self.assertEqual(cost_list_response.json()['count'], 1)
        self.assertEqual(cost_list_response.json()['results'][0]['ci_name'], 'pay-host-01')

        cost_response = self.client.get('/api/cmdb/cost/report/', {'month': current_month})
        self.assertEqual(cost_response.status_code, 200)
        cost_payload = cost_response.json()
        self.assertEqual(cost_payload['total_monthly_cost'], 1200.0)
        self.assertEqual({item['name'] for item in cost_payload['top_cost_items']}, {'pay-host-01'})
        self.assertEqual(cost_payload['by_business'][0]['business_line'], 'payment')

        optimization_response = self.client.get('/api/cmdb/optimization/suggestions/', {'month': current_month})
        self.assertEqual(optimization_response.status_code, 200)
        optimization_titles = [item['title'] for item in optimization_response.json()['suggestions']]
        self.assertTrue(any('pay-host-01' in title for title in optimization_titles))
        self.assertFalse(any('hr-host-01' in title for title in optimization_titles))

    def test_platform_change_logs_are_visible_to_scoped_platform_managers(self):
        ensure_builtin_rbac()
        role = Role.objects.create(code='cmdb-scoped-sync-manager', name='CMDB Scoped Sync Manager')
        role.permissions.add(
            PermissionDefinition.objects.get(code='cmdb.audit.view'),
            PermissionDefinition.objects.get(code='cmdb.sync.view'),
            PermissionDefinition.objects.get(code='cmdb.sync.manage'),
        )
        user = get_user_model().objects.create_user('scoped-sync-manager', password='Admin@123456')
        user.rbac_roles.add(role)

        host_type = _ci_type('平台日志授权主机', code='PLATFORM_LOG_HOST')
        ConfigItem.objects.create(name='platform-log-pay-host', ci_type=host_type, business_line='payment')
        CIResourceAuthorization.objects.create(
            name='支付业务查看',
            principal_type='user',
            principal='scoped-sync-manager',
            permission='view',
            business_line='payment',
            created_by='cmdb-admin',
        )
        platform_log = CIChangeLog.objects.create(
            ci=None,
            action='sync_job_update',
            before={'name': 'sync'},
            after={'name': 'sync-updated'},
            diff={'name': {'before': 'sync', 'after': 'sync-updated'}},
            operator='cmdb-admin',
            source='sync_job',
        )

        self.client.force_login(user)
        response = self.client.get('/api/cmdb/change-logs/', {'source': 'sync_job', 'page_size': 100})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn(str(platform_log.id), {str(item['id']) for item in response.json()['results']})

    def test_sync_failure_governance_matches_authorized_record_scope(self):
        ensure_builtin_rbac()
        role = Role.objects.create(code='cmdb-sync-viewer', name='CMDB Sync Viewer')
        role.permissions.add(
            PermissionDefinition.objects.get(code='cmdb.dashboard.view'),
            PermissionDefinition.objects.get(code='cmdb.sync.view'),
        )
        user = get_user_model().objects.create_user('payment-sync-viewer', password='Admin@123456')
        user.rbac_roles.add(role)

        host_type = _ci_type('同步授权主机', code='SYNC_AUTH_HOST')
        payment_host = ConfigItem.objects.create(
            name='sync-pay-host-01',
            ci_type=host_type,
            business_line='payment',
            environment='prod',
            admin_user='ops',
        )
        hr_host = ConfigItem.objects.create(
            name='sync-hr-host-01',
            ci_type=host_type,
            business_line='hr',
            environment='prod',
            admin_user='hr-ops',
        )
        CIResourceAuthorization.objects.create(
            name='支付同步查看',
            principal_type='user',
            principal='payment-sync-viewer',
            permission='view',
            business_line='payment',
            created_by='cmdb-admin',
        )
        CISourceMapping.objects.create(
            ci=payment_host,
            source_type='manual_import',
            source_unique_id='sync-pay-host-01',
            sync_status='success',
        )
        CISourceMapping.objects.create(
            ci=hr_host,
            source_type='manual_import',
            source_unique_id='sync-hr-host-01',
            sync_status='success',
        )
        sync_job = CISyncJob.objects.create(name='同步治理范围', source_type='manual_import')
        authorized_failed = CISyncRecord.objects.create(
            job=sync_job,
            ci=payment_host,
            action='fail',
            status='failed',
            source_unique_id='sync-payment-failed-001',
        )
        CISyncRecord.objects.create(
            job=sync_job,
            ci=hr_host,
            action='fail',
            status='failed',
            source_unique_id='sync-hr-failed-001',
        )
        global_failed = CISyncRecord.objects.create(
            job=sync_job,
            action='fail',
            status='failed',
            source_unique_id='sync-global-failed-001',
        )
        CISyncRecord.objects.create(
            job=sync_job,
            ci=payment_host,
            action='create',
            status='success',
            source_unique_id='sync-payment-success-001',
        )
        hidden_job = CISyncJob.objects.create(name='隐藏失败同步', source_type='manual_import')
        CISyncRecord.objects.create(
            job=hidden_job,
            ci=hr_host,
            action='fail',
            status='failed',
            source_unique_id='sync-hr-hidden-failed-001',
        )

        self.client.force_login(user)

        records_response = self.client.get('/api/cmdb/sync-records/', {'status': 'failed', 'page_size': 100})
        self.assertEqual(records_response.status_code, 200, records_response.content)
        record_ids = {item['id'] for item in records_response.json()['results']}
        self.assertEqual(record_ids, {authorized_failed.id, global_failed.id})

        jobs_response = self.client.get('/api/cmdb/sync-jobs/', {'page_size': 100})
        self.assertEqual(jobs_response.status_code, 200, jobs_response.content)
        job_ids = {item['id'] for item in jobs_response.json()['results']}
        self.assertIn(sync_job.id, job_ids)
        self.assertNotIn(hidden_job.id, job_ids)
        job_row = next(item for item in jobs_response.json()['results'] if item['id'] == sync_job.id)
        self.assertEqual(job_row['record_count'], 3)

        dashboard_response = self.client.get('/api/cmdb/dashboard/stats/')
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(dashboard_response.json()['risk_summary']['sync_failures'], 1)

        collection_response = self.client.get('/api/cmdb/collection/summary/')
        self.assertEqual(collection_response.status_code, 200, collection_response.content)
        collection = collection_response.json()
        self.assertEqual(collection['summary']['failed_count'], 2)
        self.assertEqual(collection['summary']['collected_resource_count'], 1)
        job_row = next(item for item in collection['jobs'] if item['id'] == sync_job.id)
        self.assertEqual(job_row['record_count'], 3)
        self.assertEqual(job_row['failed_count'], 2)
        self.assertEqual(job_row['success_count'], 1)
        self.assertEqual(job_row['resource_count'], 1)
        self.assertNotIn(hidden_job.id, {item['id'] for item in collection['jobs']})

    def test_resource_authorization_api_requires_authorization_permission(self):
        ensure_builtin_rbac()
        viewer_role = Role.objects.create(code='auth-viewer-role', name='Auth Viewer Role')
        viewer_role.permissions.add(PermissionDefinition.objects.get(code='cmdb.authorization.view'))
        manager_role = Role.objects.create(code='auth-manager-role', name='Auth Manager Role')
        manager_role.permissions.add(
            PermissionDefinition.objects.get(code='cmdb.authorization.view'),
            PermissionDefinition.objects.get(code='cmdb.authorization.manage'),
        )
        viewer = get_user_model().objects.create_user('auth-viewer', password='Admin@123456')
        viewer.rbac_roles.add(viewer_role)
        manager = get_user_model().objects.create_user('auth-manager', password='Admin@123456')
        manager.rbac_roles.add(manager_role)

        CIResourceAuthorization.objects.create(
            name='研发业务查看',
            principal_type='group',
            principal='dev-team',
            permission='view',
            business_line='dev',
        )

        self.client.force_login(viewer)
        list_response = self.client.get('/api/cmdb/resource-authorizations/')
        self.assertEqual(list_response.status_code, 200)
        create_denied = self.client.post('/api/cmdb/resource-authorizations/', {
            'name': '支付业务查看',
            'principal_type': 'user',
            'principal': 'pay-user',
            'permission': 'view',
            'business_line': 'payment',
        })
        self.assertEqual(create_denied.status_code, 403)

        self.client.force_login(manager)
        create_response = self.client.post('/api/cmdb/resource-authorizations/', {
            'name': '支付业务管理',
            'principal_type': 'user',
            'principal': 'pay-owner',
            'permission': 'manage',
            'business_line': 'payment',
        })
        self.assertEqual(create_response.status_code, 201, create_response.content)
        self.assertEqual(create_response.json()['created_by'], 'auth-manager')

    def test_resource_authorization_changes_are_audited(self):
        ensure_builtin_rbac()
        role = Role.objects.create(code='auth-audit-manager-role', name='Auth Audit Manager Role')
        role.permissions.add(
            PermissionDefinition.objects.get(code='cmdb.authorization.view'),
            PermissionDefinition.objects.get(code='cmdb.authorization.manage'),
            PermissionDefinition.objects.get(code='cmdb.audit.view'),
        )
        manager = get_user_model().objects.create_user('auth-audit-manager', password='Admin@123456')
        manager.rbac_roles.add(role)
        ci_type = _ci_type('AUTH_AUDIT_HOST', code='AUTH_AUDIT_HOST')

        self.client.force_login(manager)
        create_response = self.client.post('/api/cmdb/resource-authorizations/', {
            'name': 'payment host manage',
            'principal_type': 'user',
            'principal': 'payment-owner',
            'permission': 'manage',
            'business_line': 'payment',
            'environment': 'prod',
            'ci_type': ci_type.id,
            'description': 'initial scope',
        })
        self.assertEqual(create_response.status_code, 201, create_response.content)
        auth_id = create_response.json()['id']

        create_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='authorization_create',
            source='authorization',
        ).latest('id')
        self.assertEqual(create_log.operator, 'auth-audit-manager')
        self.assertEqual(create_log.after['principal'], 'payment-owner')
        self.assertEqual(create_log.after['ci_type'], ci_type.id)

        update_response = self.client.patch(
            f'/api/cmdb/resource-authorizations/{auth_id}/',
            {
                'environment': 'test',
                'description': 'narrow test scope',
            },
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200, update_response.content)
        update_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='authorization_update',
            source='authorization',
        ).latest('id')
        self.assertEqual(update_log.diff['environment']['before'], 'prod')
        self.assertEqual(update_log.diff['environment']['after'], 'test')
        self.assertEqual(update_log.diff['description']['after'], 'narrow test scope')

        audit_response = self.client.get('/api/cmdb/change-logs/', {'source': 'authorization', 'page_size': 100})
        self.assertEqual(audit_response.status_code, 200, audit_response.content)
        actions = {item['action'] for item in audit_response.json()['results']}
        self.assertIn('authorization_create', actions)
        self.assertIn('authorization_update', actions)

        delete_response = self.client.delete(f'/api/cmdb/resource-authorizations/{auth_id}/')
        self.assertEqual(delete_response.status_code, 204, delete_response.content)
        delete_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='authorization_delete',
            source='authorization',
        ).latest('id')
        self.assertEqual(delete_log.before['id'], auth_id)
        self.assertEqual(delete_log.after, {})

    def test_model_metadata_changes_are_audited(self):
        create_group = self.client.post(
            '/api/cmdb/model-groups/',
            {
                'name': '审计分组',
                'code': 'audit_group',
                'description': 'initial group',
                'sort_order': 10,
            },
            content_type='application/json',
        )
        self.assertEqual(create_group.status_code, 201, create_group.content)
        group_id = create_group.json()['id']
        create_group_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='model_group_create',
            source='model',
        ).latest('id')
        self.assertEqual(create_group_log.after['code'], 'audit_group')

        update_group = self.client.patch(
            f'/api/cmdb/model-groups/{group_id}/',
            {'description': 'updated group', 'sort_order': 20},
            content_type='application/json',
        )
        self.assertEqual(update_group.status_code, 200, update_group.content)
        update_group_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='model_group_update',
            source='model',
        ).latest('id')
        self.assertEqual(update_group_log.diff['description']['before'], 'initial group')
        self.assertEqual(update_group_log.diff['description']['after'], 'updated group')

        create_model = self.client.post(
            '/api/cmdb/ci-types/',
            {
                'name': 'audit metadata host',
                'code': 'AUDIT_METADATA_HOST',
                'group': group_id,
                'color': '#245bdb',
                'description': 'initial model',
            },
            content_type='application/json',
        )
        self.assertEqual(create_model.status_code, 201, create_model.content)
        ci_type_id = create_model.json()['id']
        create_model_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='model_create',
            source='model',
        ).latest('id')
        self.assertEqual(create_model_log.after['code'], 'AUDIT_METADATA_HOST')
        self.assertEqual(create_model_log.operator, self.user.username)

        update_model = self.client.patch(
            f'/api/cmdb/ci-types/{ci_type_id}/',
            {'description': 'updated model'},
            content_type='application/json',
        )
        self.assertEqual(update_model.status_code, 200, update_model.content)
        update_model_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='model_update',
            source='model',
        ).latest('id')
        self.assertEqual(update_model_log.diff['description']['before'], 'initial model')
        self.assertEqual(update_model_log.diff['description']['after'], 'updated model')

        create_field = self.client.post(
            '/api/cmdb/ci-fields/',
            {
                'ci_type': ci_type_id,
                'name': '资产编号',
                'code': 'asset_id',
                'field_type': 'string',
                'field_group': '基础信息',
                'unique': True,
                'is_searchable': True,
                'sync_mode': 'manual',
            },
            content_type='application/json',
        )
        self.assertEqual(create_field.status_code, 201, create_field.content)
        field_id = create_field.json()['id']
        create_field_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='model_field_create',
            source='model',
        ).latest('id')
        self.assertEqual(create_field_log.after['code'], 'asset_id')
        self.assertEqual(create_field_log.after['ci_type'], ci_type_id)

        update_field = self.client.patch(
            f'/api/cmdb/ci-fields/{field_id}/',
            {'sort_order': 20, 'is_display': False},
            content_type='application/json',
        )
        self.assertEqual(update_field.status_code, 200, update_field.content)
        update_field_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='model_field_update',
            source='model',
        ).latest('id')
        self.assertEqual(update_field_log.diff['sort_order']['before'], 0)
        self.assertEqual(update_field_log.diff['sort_order']['after'], 20)
        self.assertEqual(update_field_log.diff['is_display']['after'], False)

        create_target_model = self.client.post(
            '/api/cmdb/ci-types/',
            {
                'name': 'audit metadata service',
                'code': 'AUDIT_METADATA_SERVICE',
                'color': '#22c55e',
                'description': 'target model',
            },
            content_type='application/json',
        )
        self.assertEqual(create_target_model.status_code, 201, create_target_model.content)
        target_type_id = create_target_model.json()['id']

        create_rule = self.client.post(
            '/api/cmdb/relation-rules/',
            {
                'source_type': ci_type_id,
                'target_type': target_type_id,
                'relation_type': 'depends_on',
                'direction': 'outgoing',
                'required': True,
                'multiple': False,
                'description': 'initial rule',
            },
            content_type='application/json',
        )
        self.assertEqual(create_rule.status_code, 201, create_rule.content)
        rule_id = create_rule.json()['id']
        create_rule_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='relation_rule_create',
            source='model',
        ).latest('id')
        self.assertEqual(create_rule_log.after['source_type'], ci_type_id)
        self.assertEqual(create_rule_log.after['target_type'], target_type_id)

        update_rule = self.client.patch(
            f'/api/cmdb/relation-rules/{rule_id}/',
            {'required': False, 'description': 'updated rule'},
            content_type='application/json',
        )
        self.assertEqual(update_rule.status_code, 200, update_rule.content)
        update_rule_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='relation_rule_update',
            source='model',
        ).latest('id')
        self.assertEqual(update_rule_log.diff['required']['before'], True)
        self.assertEqual(update_rule_log.diff['required']['after'], False)

        delete_field = self.client.delete(f'/api/cmdb/ci-fields/{field_id}/')
        self.assertEqual(delete_field.status_code, 204, delete_field.content)
        delete_field_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='model_field_delete',
            source='model',
        ).latest('id')
        self.assertEqual(delete_field_log.before['id'], field_id)

        delete_rule = self.client.delete(f'/api/cmdb/relation-rules/{rule_id}/')
        self.assertEqual(delete_rule.status_code, 204, delete_rule.content)
        delete_rule_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='relation_rule_delete',
            source='model',
        ).latest('id')
        self.assertEqual(delete_rule_log.before['id'], rule_id)

        delete_model = self.client.delete(f'/api/cmdb/ci-types/{ci_type_id}/')
        self.assertEqual(delete_model.status_code, 204, delete_model.content)
        delete_model_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='model_delete',
            source='model',
        ).latest('id')
        self.assertEqual(delete_model_log.before['id'], ci_type_id)

        delete_target_model = self.client.delete(f'/api/cmdb/ci-types/{target_type_id}/')
        self.assertEqual(delete_target_model.status_code, 204, delete_target_model.content)

        delete_group = self.client.delete(f'/api/cmdb/model-groups/{group_id}/')
        self.assertEqual(delete_group.status_code, 204, delete_group.content)
        delete_group_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='model_group_delete',
            source='model',
        ).latest('id')
        self.assertEqual(delete_group_log.before['id'], group_id)

        audit_response = self.client.get('/api/cmdb/change-logs/', {'source': 'model', 'page_size': 100})
        self.assertEqual(audit_response.status_code, 200, audit_response.content)
        actions = {item['action'] for item in audit_response.json()['results']}
        self.assertTrue({
            'model_group_create',
            'model_group_update',
            'model_group_delete',
            'model_create',
            'model_update',
            'model_field_create',
            'model_field_update',
            'model_field_delete',
            'relation_rule_create',
            'relation_rule_update',
            'relation_rule_delete',
            'model_delete',
        }.issubset(actions))

    def test_sync_and_capacity_configuration_changes_are_audited(self):
        ci_type = _ci_type('audit capacity host', code='AUDIT_CAPACITY_HOST')
        ci = ConfigItem.objects.create(
            name='audit-capacity-ecs-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='sre-core',
            status='active',
            attributes={'private_ip': '10.20.30.40'},
        )

        create_mapping = self.client.post(
            '/api/cmdb/source-mappings/',
            {
                'ci': ci.id,
                'source_type': 'aliyun_ecs',
                'source_account': 'prod-account',
                'source_region': 'cn-hangzhou',
                'source_unique_id': 'i-audit-capacity-001',
                'sync_status': 'success',
                'raw_payload': {'instance_id': 'i-audit-capacity-001'},
            },
            content_type='application/json',
        )
        self.assertEqual(create_mapping.status_code, 201, create_mapping.content)
        mapping_id = create_mapping.json()['id']
        create_mapping_log = CIChangeLog.objects.filter(
            ci=ci,
            action='source_mapping_create',
            source='source_mapping',
        ).latest('id')
        self.assertEqual(create_mapping_log.after['source_unique_id'], 'i-audit-capacity-001')

        update_mapping = self.client.patch(
            f'/api/cmdb/source-mappings/{mapping_id}/',
            {'sync_status': 'failed', 'raw_payload': {'instance_id': 'i-audit-capacity-001', 'error': 'timeout'}},
            content_type='application/json',
        )
        self.assertEqual(update_mapping.status_code, 200, update_mapping.content)
        update_mapping_log = CIChangeLog.objects.filter(
            ci=ci,
            action='source_mapping_update',
            source='source_mapping',
        ).latest('id')
        self.assertEqual(update_mapping_log.diff['sync_status']['before'], 'success')
        self.assertEqual(update_mapping_log.diff['sync_status']['after'], 'failed')

        create_policy = self.client.post(
            '/api/cmdb/threshold-policies/',
            {
                'resource_type': ci_type.id,
                'metric': 'cpu_usage',
                'normal_threshold': '60',
                'warning_threshold': '75',
                'critical_threshold': '90',
                'exceeded_threshold': '100',
                'enabled': True,
            },
            content_type='application/json',
        )
        self.assertEqual(create_policy.status_code, 201, create_policy.content)
        policy_id = create_policy.json()['id']
        create_policy_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='threshold_policy_create',
            source='threshold_policy',
        ).latest('id')
        self.assertEqual(create_policy_log.after['resource_type'], ci_type.id)
        self.assertEqual(create_policy_log.after['metric'], 'cpu_usage')

        update_policy = self.client.patch(
            f'/api/cmdb/threshold-policies/{policy_id}/',
            {'warning_threshold': '80'},
            content_type='application/json',
        )
        self.assertEqual(update_policy.status_code, 200, update_policy.content)
        update_policy_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='threshold_policy_update',
            source='threshold_policy',
        ).latest('id')
        self.assertEqual(update_policy_log.diff['warning_threshold']['before'], '75.00')
        self.assertEqual(update_policy_log.diff['warning_threshold']['after'], '80.00')

        create_metric = self.client.post(
            '/api/cmdb/resource-metrics/',
            {
                'ci': ci.id,
                'metric': 'cpu_usage',
                'value': '72.5000',
                'unit': '%',
                'usage_percent': '72.50',
                'collected_at': timezone.now().isoformat(),
                'source': 'manual',
            },
            content_type='application/json',
        )
        self.assertEqual(create_metric.status_code, 201, create_metric.content)
        metric_id = create_metric.json()['id']
        create_metric_log = CIChangeLog.objects.filter(
            ci=ci,
            action='resource_metric_create',
            source='resource_metric',
        ).latest('id')
        self.assertEqual(create_metric_log.after['metric'], 'cpu_usage')
        self.assertEqual(create_metric_log.after['usage_percent'], '72.50')

        update_metric = self.client.patch(
            f'/api/cmdb/resource-metrics/{metric_id}/',
            {'usage_percent': '88.25'},
            content_type='application/json',
        )
        self.assertEqual(update_metric.status_code, 200, update_metric.content)
        update_metric_log = CIChangeLog.objects.filter(
            ci=ci,
            action='resource_metric_update',
            source='resource_metric',
        ).latest('id')
        self.assertEqual(update_metric_log.diff['usage_percent']['before'], '72.50')
        self.assertEqual(update_metric_log.diff['usage_percent']['after'], '88.25')

        delete_metric = self.client.delete(f'/api/cmdb/resource-metrics/{metric_id}/')
        self.assertEqual(delete_metric.status_code, 204, delete_metric.content)
        delete_metric_log = CIChangeLog.objects.filter(
            ci=ci,
            action='resource_metric_delete',
            source='resource_metric',
        ).latest('id')
        self.assertEqual(delete_metric_log.before['id'], metric_id)

        delete_mapping = self.client.delete(f'/api/cmdb/source-mappings/{mapping_id}/')
        self.assertEqual(delete_mapping.status_code, 204, delete_mapping.content)
        delete_mapping_log = CIChangeLog.objects.filter(
            ci=ci,
            action='source_mapping_delete',
            source='source_mapping',
        ).latest('id')
        self.assertEqual(delete_mapping_log.before['id'], mapping_id)

        delete_policy = self.client.delete(f'/api/cmdb/threshold-policies/{policy_id}/')
        self.assertEqual(delete_policy.status_code, 204, delete_policy.content)
        delete_policy_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='threshold_policy_delete',
            source='threshold_policy',
        ).latest('id')
        self.assertEqual(delete_policy_log.before['id'], policy_id)

        audit_response = self.client.get('/api/cmdb/change-logs/', {'page_size': 200})
        self.assertEqual(audit_response.status_code, 200, audit_response.content)
        actions = {item['action'] for item in audit_response.json()['results']}
        self.assertTrue({
            'source_mapping_create',
            'source_mapping_update',
            'source_mapping_delete',
            'threshold_policy_create',
            'threshold_policy_update',
            'threshold_policy_delete',
            'resource_metric_create',
            'resource_metric_update',
            'resource_metric_delete',
        }.issubset(actions))

    def test_sync_job_configuration_changes_are_audited(self):
        create_response = self.client.post(
            '/api/cmdb/sync-jobs/',
            {
                'name': 'audit sync job',
                'source_type': 'manual_import',
                'mode': 'manual',
                'dry_run': True,
                'config': {
                    'target_ci_type_code': 'AUDIT_METADATA_HOST',
                    'collection_enabled': False,
                },
            },
            content_type='application/json',
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        job_id = create_response.json()['id']
        create_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='sync_job_create',
            source='sync_job',
        ).latest('id')
        self.assertEqual(create_log.after['name'], 'audit sync job')
        self.assertEqual(create_log.after['created_by'], self.user.username)

        update_response = self.client.patch(
            f'/api/cmdb/sync-jobs/{job_id}/',
            {
                'mode': 'scheduled',
                'config': {
                    'target_ci_type_code': 'AUDIT_METADATA_HOST',
                    'collection_enabled': False,
                    'cron': '*/5 * * * *',
                },
            },
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200, update_response.content)
        update_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='sync_job_update',
            source='sync_job',
        ).latest('id')
        self.assertEqual(update_log.diff['mode']['before'], 'manual')
        self.assertEqual(update_log.diff['mode']['after'], 'scheduled')
        self.assertIn('cron', update_log.diff['config']['after'])

        toggle_response = self.client.post(
            f'/api/cmdb/sync-jobs/{job_id}/collection-toggle/',
            {'enabled': True},
            content_type='application/json',
        )
        self.assertEqual(toggle_response.status_code, 200, toggle_response.content)
        toggle_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='sync_job_update',
            source='sync_job',
        ).latest('id')
        self.assertEqual(toggle_log.diff['config']['before']['collection_enabled'], False)
        self.assertEqual(toggle_log.diff['config']['after']['collection_enabled'], True)

        delete_response = self.client.delete(f'/api/cmdb/sync-jobs/{job_id}/')
        self.assertEqual(delete_response.status_code, 204, delete_response.content)
        delete_log = CIChangeLog.objects.filter(
            ci__isnull=True,
            action='sync_job_delete',
            source='sync_job',
        ).latest('id')
        self.assertEqual(delete_log.before['id'], job_id)

        audit_response = self.client.get('/api/cmdb/change-logs/', {'source': 'sync_job', 'page_size': 100})
        self.assertEqual(audit_response.status_code, 200, audit_response.content)
        actions = {item['action'] for item in audit_response.json()['results']}
        self.assertTrue({'sync_job_create', 'sync_job_update', 'sync_job_delete'}.issubset(actions))

    def test_resource_authorization_limits_ci_write_import_and_sync_scope(self):
        ensure_builtin_rbac()
        role = Role.objects.create(code='cmdb-scoped-manager', name='CMDB Scoped Manager')
        role.permissions.add(
            PermissionDefinition.objects.get(code='cmdb.ci.view'),
            PermissionDefinition.objects.get(code='cmdb.ci.manage'),
            PermissionDefinition.objects.get(code='cmdb.sync.view'),
            PermissionDefinition.objects.get(code='cmdb.sync.manage'),
        )
        user = get_user_model().objects.create_user('payment-manager', password='Admin@123456')
        user.rbac_roles.add(role)
        ci_type = _ci_type('授权写入云主机', code='AUTH_WRITE_HOST')
        CIResourceAuthorization.objects.create(
            name='支付业务管理',
            principal_type='user',
            principal='payment-manager',
            permission='manage',
            business_line='payment',
            created_by='cmdb-admin',
        )

        self.client.force_login(user)

        create_allowed = self.client.post('/api/cmdb/config-items/', {
            'name': 'pay-write-01',
            'ci_type': ci_type.id,
            'business_line': 'payment',
            'environment': 'prod',
            'admin_user': 'ops',
            'status': 'active',
            'attributes': {'private_ip': '10.61.1.8'},
        }, content_type='application/json')
        self.assertEqual(create_allowed.status_code, 201, create_allowed.content)

        create_denied = self.client.post('/api/cmdb/config-items/', {
            'name': 'hr-write-01',
            'ci_type': ci_type.id,
            'business_line': 'hr',
            'environment': 'prod',
            'admin_user': 'ops',
            'status': 'active',
            'attributes': {'private_ip': '10.62.1.8'},
        }, content_type='application/json')
        self.assertEqual(create_denied.status_code, 403, create_denied.content)
        self.assertFalse(ConfigItem.objects.filter(name='hr-write-01').exists())

        update_denied = self.client.patch(
            f"/api/cmdb/config-items/{create_allowed.json()['id']}/",
            {'business_line': 'hr'},
            content_type='application/json',
        )
        self.assertEqual(update_denied.status_code, 403, update_denied.content)

        dry_import = self.client.post('/api/cmdb/config-items/bulk-import/', {
            'dry_run': True,
            'source_type': 'manual_import',
            'items': [{
                'ci_type_name': '授权写入云主机',
                'ci_type_code': 'AUTH_WRITE_HOST',
                'name': 'hr-import-01',
                'business_line': 'hr',
                'environment': 'prod',
                'admin_user': 'ops',
                'source_unique_id': 'hr-import-01',
            }],
        }, content_type='application/json')
        self.assertEqual(dry_import.status_code, 200, dry_import.content)
        self.assertEqual(dry_import.json()['summary']['fail'], 1)
        self.assertIn('无权管理该资源范围', dry_import.json()['records'][0]['error_message'])
        self.assertFalse(ConfigItem.objects.filter(name='hr-import-01').exists())

        job = CISyncJob.objects.create(
            name='越权同步任务',
            source_type='manual_import',
            config={'items': [{
                'ci_type_name': '授权写入云主机',
                'ci_type_code': 'AUTH_WRITE_HOST',
                'name': 'hr-sync-01',
                'business_line': 'hr',
                'environment': 'prod',
                'admin_user': 'ops',
                'source_unique_id': 'hr-sync-01',
            }]},
        )
        sync_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')
        self.assertEqual(sync_response.status_code, 200, sync_response.content)
        self.assertEqual(sync_response.json()['summary']['fail'], 1)
        self.assertFalse(ConfigItem.objects.filter(name='hr-sync-01').exists())

    def test_resource_authorization_view_policy_does_not_grant_manage_scope(self):
        ensure_builtin_rbac()
        role = Role.objects.create(code='cmdb-view-scoped-manager', name='CMDB View Scoped Manager')
        role.permissions.add(
            PermissionDefinition.objects.get(code='cmdb.ci.view'),
            PermissionDefinition.objects.get(code='cmdb.ci.manage'),
        )
        user = get_user_model().objects.create_user('payment-view-only-manager', password='Admin@123456')
        user.rbac_roles.add(role)
        ci_type = _ci_type('授权只读云主机', code='AUTH_VIEW_ONLY_HOST')
        CIResourceAuthorization.objects.create(
            name='支付业务查看',
            principal_type='user',
            principal='payment-view-only-manager',
            permission='view',
            business_line='payment',
            created_by='cmdb-admin',
        )

        self.client.force_login(user)

        response = self.client.post('/api/cmdb/config-items/', {
            'name': 'pay-view-only-write-01',
            'ci_type': ci_type.id,
            'business_line': 'payment',
            'environment': 'prod',
            'admin_user': 'ops',
            'status': 'active',
        }, content_type='application/json')

        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(ConfigItem.objects.filter(name='pay-view-only-write-01').exists())

    def test_host_create_update_delete_syncs_to_cmdb(self):
        host = Host.objects.create(
            hostname='sync-host-01',
            ip_address='10.0.0.21',
            business_line='core',
            environment='prod',
            admin_user='ops-admin',
            os_type='Linux',
            description='由主机中心创建',
            status='online',
        )

        ci = ConfigItem.objects.get(name='sync-host-01')
        self.assertEqual(ci.attributes['ip_address'], '10.0.0.21')
        self.assertEqual(ci.attributes['private_ip'], '10.0.0.21')
        self.assertEqual(ci.attributes['asset_sn'], f'host-{host.pk}')
        self.assertEqual(ci.attributes['source_type'], 'host_asset')
        self.assertEqual(ci.attributes['source_unique_id'], str(host.pk))
        self.assertEqual(ci.attributes['ssh_port'], 22)
        self.assertEqual(ci.attributes['ops_owner'], 'ops-admin')
        self.assertEqual(ci.attributes['lifecycle_status'], 'running')
        self.assertEqual(ci.business_line, 'core')
        self.assertEqual(ci.status, 'active')
        self.assertEqual(ci.ci_type.code, 'IDC_SERVER')
        self.assertTrue(CISourceMapping.objects.filter(
            ci=ci,
            source_type='host_asset',
            source_account='sxdevops',
            source_region='local',
            source_unique_id=str(host.pk),
            sync_status='success',
        ).exists())

        host.hostname = 'sync-host-01-renamed'
        host.ip_address = '10.0.0.22'
        host.description = '由主机中心更新'
        host.status = 'offline'
        host.ssh_port = 2222
        host.save()

        ci.refresh_from_db()
        self.assertEqual(ci.name, 'sync-host-01-renamed')
        self.assertEqual(ci.attributes['ip_address'], '10.0.0.22')
        self.assertEqual(ci.attributes['private_ip'], '10.0.0.22')
        self.assertEqual(ci.attributes['description'], '由主机中心更新')
        self.assertEqual(ci.attributes['ssh_port'], 2222)
        self.assertEqual(ci.attributes['lifecycle_status'], 'offline')
        self.assertEqual(ci.status, 'offline')
        self.assertEqual(ConfigItem.objects.filter(attributes__source_unique_id=str(host.pk)).count(), 1)

        ci.name = 'sync-host-01-cmdb-renamed'
        ci.status = 'active'
        ci.attributes['private_ip'] = '10.0.0.23'
        ci.attributes.pop('ip_address', None)
        ci.save()
        host.refresh_from_db()
        self.assertEqual(Host.objects.count(), 1)
        self.assertEqual(host.hostname, 'sync-host-01-cmdb-renamed')
        self.assertEqual(host.ip_address, '10.0.0.23')
        self.assertEqual(host.status, 'online')

        host.delete()
        self.assertFalse(ConfigItem.objects.filter(name='sync-host-01-cmdb-renamed').exists())
        self.assertFalse(CISourceMapping.objects.filter(source_type='host_asset', source_unique_id=str(host.pk)).exists())

    def test_host_like_config_item_syncs_back_to_host(self):
        ci_type = _ci_type('云主机(ECS)')
        ci = ConfigItem.objects.create(
            name='cmdb-host-01',
            ci_type=ci_type,
            business_line='retail',
            environment='test',
            admin_user='cmdb-owner',
            status='active',
            attributes={
                'ip_address': '10.0.1.15',
                'os_type': 'Alibaba Cloud Linux 3',
                'description': '由 CMDB 创建',
            },
        )

        host = Host.objects.get(hostname='cmdb-host-01')
        self.assertEqual(host.ip_address, '10.0.1.15')
        self.assertEqual(host.business_line, 'retail')
        self.assertEqual(host.environment, 'test')
        self.assertEqual(host.status, 'online')

        ci.status = 'offline'
        ci.attributes['description'] = '由 CMDB 更新'
        ci.save()

        host.refresh_from_db()
        self.assertEqual(host.status, 'offline')
        self.assertEqual(host.description, '由 CMDB 更新')

    def test_stats_merge_garbled_ci_type_names(self):
        good_type = _ci_type('应用服务', color='#3b82f6')
        bad_type = CIType.objects.create(name=_garbled_utf8_as_gbk('应用服务'), color='#3b82f6')
        cloud_type = _ci_type('云主机(ECS)', color='#64748b')
        cloud_alias_type = CIType.objects.create(name='云主机', color='#64748b')
        k8s_type = _ci_type('K8s 集群', color='#0ea5e9')
        k8s_alias_type = CIType.objects.create(name='K8s集群', color='#0ea5e9')
        ConfigItem.objects.create(name='app-a', ci_type=good_type, status='active')
        ConfigItem.objects.create(name='app-b', ci_type=bad_type, status='active')
        ConfigItem.objects.create(name='host-a', ci_type=cloud_type, status='active')
        ConfigItem.objects.create(name='host-b', ci_type=cloud_alias_type, status='active')
        ConfigItem.objects.create(name='cluster-a', ci_type=k8s_type, status='active')
        ConfigItem.objects.create(name='cluster-b', ci_type=k8s_alias_type, status='active')

        response = self.client.get('/api/cmdb/config-items/stats/')
        self.assertEqual(response.status_code, 200)

        by_type = response.json()['by_type']
        app_entry = next(item for item in by_type if item['ci_type__name'] == '应用服务')
        host_entry = next(item for item in by_type if item['ci_type__name'] == '云主机(ECS)')
        k8s_entry = next(item for item in by_type if item['ci_type__name'] == 'K8s 集群')
        self.assertEqual(app_entry['count'], 2)
        self.assertEqual(host_entry['count'], 2)
        self.assertEqual(k8s_entry['count'], 2)


class CmdbPhaseOneMetadataTests(AuthenticatedTestCase):
    def test_config_item_serializer_includes_type_metadata_for_web_assets(self):
        group = CIModelGroup.objects.get(code='middleware')
        ci_type, _ = CIType.objects.get_or_create(
            code='NACOS',
            defaults={'name': 'Nacos', 'group': group},
        )
        item = ConfigItem.objects.create(
            name='nacos-console',
            ci_type=ci_type,
            attributes={'ip_address': 'https://nacos.example.com'},
        )

        data = ConfigItemSerializer(item).data

        self.assertEqual(data['ci_type_code'], 'NACOS')
        self.assertEqual(data['ci_type_group_code'], 'middleware')

    def test_builtin_access_address_fields_use_connection_address(self):
        ensure_builtin_cmdb()

        for code in ['MIDDLEWARE', 'ELASTICSEARCH', 'NACOS', 'HADOOP', 'HBASE']:
            ci_type = CIType.objects.get(code=code)
            self.assertEqual(CIField.objects.get(ci_type=ci_type, code='endpoint').name, '连接地址')

    def test_builtin_cmdb_merges_legacy_nat_gateway_type(self):
        canonical_type = CIType.objects.get(code='NAT_GATEWAY')
        legacy_type = CIType.objects.create(name='NAT 网关', code='', is_active=True)
        legacy_asset = ConfigItem.objects.create(name='legacy-nat', ci_type=legacy_type)

        ensure_builtin_cmdb()

        legacy_type.refresh_from_db()
        legacy_asset.refresh_from_db()
        self.assertFalse(legacy_type.is_active)
        self.assertEqual(legacy_asset.ci_type_id, canonical_type.id)

    def test_builtin_cmdb_initialization_is_idempotent_and_covers_phase_one_models(self):
        first_summary = ensure_builtin_cmdb()
        stale_third_party_type = CIType.objects.get(code='THIRD_PARTY_SERVICE')
        CIField.objects.update_or_create(
            ci_type=stale_third_party_type,
            code='key_owner',
            defaults={'name': '密钥负责人', 'field_type': 'string', 'is_builtin': True, 'required': True},
        )
        CIField.objects.update_or_create(
            ci_type=stale_third_party_type,
            code='key_expire_date',
            defaults={'name': '密钥到期日', 'field_type': 'date', 'is_builtin': True},
        )
        second_summary = ensure_builtin_cmdb()

        self.assertEqual(first_summary['types'], second_summary['types'])
        builtin_group_codes = set(CIModelGroup.objects.filter(is_builtin=True, is_active=True).values_list('code', flat=True))
        self.assertTrue({
            'business',
            'compute',
            'database',
            'middleware',
            'storage',
            'bigdata',
            'network',
            'external',
        }.issubset(builtin_group_codes))
        self.assertFalse(CIModelGroup.objects.filter(code='data', is_active=True).exists())

        cloud_type = CIType.objects.get(code='CLOUD_SERVER')
        idc_type = CIType.objects.get(code='IDC_SERVER')
        virtual_machine_type = CIType.objects.get(code='VIRTUAL_MACHINE')
        third_party_type = CIType.objects.get(code='THIRD_PARTY_SERVICE')
        nginx_type = CIType.objects.get(code='NGINX')
        domain_type = CIType.objects.get(code='DOMAIN')
        certificate_type = CIType.objects.get(code='CERTIFICATE')
        mysql_type = CIType.objects.get(code='MYSQL')
        postgresql_type = CIType.objects.get(code='POSTGRESQL')
        mongodb_type = CIType.objects.get(code='MONGODB')
        redis_type = CIType.objects.get(code='REDIS')
        kafka_type = CIType.objects.get(code='KAFKA')
        rocketmq_type = CIType.objects.get(code='ROCKETMQ')
        emqx_type = CIType.objects.get(code='EMQX')
        object_storage_type = CIType.objects.get(code='OBJECT_STORAGE')
        block_storage_type = CIType.objects.get(code='BLOCK_STORAGE')
        file_storage_type = CIType.objects.get(code='FILE_STORAGE')
        hologres_type = CIType.objects.get(code='HOLOGRES')
        maxcompute_type = CIType.objects.get(code='MAXCOMPUTE')
        dataworks_type = CIType.objects.get(code='DATAWORKS')
        dw_type = CIType.objects.get(code='DW')
        nifi_type = CIType.objects.get(code='NIFI')
        dolphinscheduler_type = CIType.objects.get(code='DOLPHINSCHEDULER')
        apisix_type = CIType.objects.get(code='APISIX')
        load_balancer_type = CIType.objects.get(code='LOAD_BALANCER')
        asset_item_type = CIType.objects.get(code='ASSET_ITEM')

        self.assertEqual(cloud_type.name, '云主机(ECS)')
        self.assertEqual(idc_type.name, '物理机')
        self.assertTrue(idc_type.is_builtin)
        self.assertEqual(virtual_machine_type.name, '虚拟机')
        self.assertEqual(third_party_type.group.code, 'external')
        self.assertEqual(third_party_type.group.name, '其他资产')
        self.assertTrue(asset_item_type.is_builtin)
        self.assertEqual(asset_item_type.group.code, 'external')
        self.assertEqual(nginx_type.group.code, 'network')
        self.assertEqual(domain_type.group.code, 'network')
        self.assertEqual(certificate_type.group.code, 'network')
        self.assertEqual(mysql_type.group.code, 'database')
        self.assertEqual(postgresql_type.group.code, 'database')
        self.assertEqual(mongodb_type.group.code, 'database')
        self.assertEqual(redis_type.group.code, 'middleware')
        self.assertEqual(kafka_type.group.code, 'middleware')
        self.assertEqual(rocketmq_type.group.code, 'middleware')
        self.assertEqual(emqx_type.group.code, 'middleware')
        self.assertEqual(object_storage_type.group.code, 'storage')
        self.assertEqual(block_storage_type.group.code, 'storage')
        self.assertEqual(file_storage_type.group.code, 'storage')
        for code in ['HADOOP', 'FLINK', 'CLICKHOUSE', 'HOLOGRES', 'MAXCOMPUTE', 'DATAWORKS', 'DW', 'NIFI', 'DOLPHINSCHEDULER']:
            self.assertEqual(CIType.objects.get(code=code).group.code, 'bigdata')
        self.assertEqual(apisix_type.group.code, 'middleware')
        self.assertFalse(CIType.objects.filter(code='CLOUD_DATABASE', is_active=True).exists())
        self.assertFalse(CIType.objects.filter(code__in=['SECURITY_GROUP', 'EIP'], is_active=True).exists())
        self.assertFalse(CIType.objects.filter(name__in=['Docker环境', 'vSphere资源统计', '数据仓库', 'Security Group', '安全组', 'NAT 网关', '弹性IP', '弹性 IP', 'Spark', 'Hive', 'HBase', 'Doris'], is_active=True).exists())
        self.assertEqual(load_balancer_type.group.code, 'network')

        idc_fields = set(CIField.objects.filter(ci_type=idc_type).values_list('code', flat=True))
        self.assertTrue({
            'asset_sn',
            'private_ip',
            'idc',
            'rack',
            'u_position',
            'lifecycle_status',
            'purchase_date',
            'service_expiry_date',
            'service_expire_warning_days',
            'ops_owner',
            'vendor',
            'model',
            'serial_number',
            'cpu',
            'memory_gb',
            'disk_gb',
            'host_name',
            'datacenter',
            'cluster',
            'connection_state',
            'power_state',
            'maintenance_mode',
            'esxi_version',
            'esxi_build',
            'cpu_total_mhz',
        }.issubset(idc_fields))
        self.assertTrue({'cpu_used_mhz', 'memory_used_gb'}.isdisjoint(idc_fields))
        self.assertFalse(CIField.objects.get(ci_type=idc_type, code='private_ip').required)
        self.assertFalse(CIField.objects.get(ci_type=idc_type, code='idc').required)
        cloud_fields = set(CIField.objects.filter(ci_type=cloud_type).values_list('code', flat=True))
        self.assertIn('instance_id', cloud_fields)
        self.assertIn('private_ip', cloud_fields)
        self.assertIn('department', cloud_fields)
        self.assertTrue({
            'source_type',
            'source_account',
            'source_region',
            'source_unique_id',
        }.isdisjoint(cloud_fields))
        virtual_machine_fields = set(CIField.objects.filter(ci_type=virtual_machine_type).values_list('code', flat=True))
        self.assertTrue({'instance_id', 'private_ip', 'cpu', 'memory_gb', 'disk_gb', 'datacenter', 'cluster', 'host'}.issubset(virtual_machine_fields))
        manual_sync_fields = set(CIField.objects.filter(sync_mode='manual').values_list('code', flat=True))
        self.assertTrue({
            'department',
            'ops_owner',
            'backup_plan',
            'contract_no',
            'service_expiry_date',
            'cert_owner',
        }.issubset(manual_sync_fields))
        self.assertEqual(CIField.objects.get(ci_type=cloud_type, code='private_ip').sync_mode, 'source')
        self.assertFalse(CIField.objects.get(ci_type=cloud_type, code='private_ip').required)
        third_party_fields = set(CIField.objects.filter(ci_type=third_party_type).values_list('code', flat=True))
        self.assertTrue({
            'provider',
            'service_type',
            'account_subject',
            'backup_plan',
            'contract_no',
            'service_expiry_date',
            'service_expire_warning_days',
        }.issubset(third_party_fields))
        self.assertFalse(CIField.objects.filter(ci_type=third_party_type, code__in=['account_owner', 'key_owner', 'key_expire_date', 'expire_date', 'contract_expire_warning_days']).exists())
        self.assertFalse(CIField.objects.get(ci_type=third_party_type, code='service_type').required)
        asset_item_fields = set(CIField.objects.filter(ci_type=asset_item_type).values_list('code', flat=True))
        self.assertTrue({
            'asset_code',
            'item_category',
            'brand_model',
            'serial_number',
            'storage_location',
            'custodian',
            'usage_status',
            'purchase_date',
            'service_expiry_date',
            'service_expire_warning_days',
            'department',
        }.issubset(asset_item_fields))
        self.assertFalse(CIField.objects.filter(code__in=['monthly_cost', 'cost_center']).exists())
        self.assertTrue(CIField.objects.get(ci_type=asset_item_type, code='asset_code').required)
        self.assertTrue(CIField.objects.get(ci_type=asset_item_type, code='asset_code').unique)
        self.assertTrue(CIField.objects.get(ci_type=asset_item_type, code='storage_location').required)
        self.assertEqual(CIField.objects.get(ci_type=asset_item_type, code='usage_status').default, 'available')
        nginx_fields = set(CIField.objects.filter(ci_type=nginx_type).values_list('code', flat=True))
        self.assertTrue({'environment_name', 'private_ip', 'listen_ports', 'nginx_path', 'ops_owner'}.issubset(nginx_fields))
        domain_fields = set(CIField.objects.filter(ci_type=domain_type).values_list('code', flat=True))
        self.assertTrue({'domain', 'record_type', 'record_value', 'dns_provider', 'owner', 'expire_date', 'ssl_enabled'}.issubset(domain_fields))
        certificate_fields = set(CIField.objects.filter(ci_type=certificate_type).values_list('code', flat=True))
        self.assertTrue({'domain', 'issuer', 'serial_number', 'expires_at', 'cert_owner', 'deploy_location'}.issubset(certificate_fields))
        mongodb_fields = set(CIField.objects.filter(ci_type=mongodb_type).values_list('code', flat=True))
        self.assertTrue({'instance_id', 'endpoint', 'version', 'storage_gb', 'replica_count', 'vpc_id'}.issubset(mongodb_fields))
        postgresql_fields = set(CIField.objects.filter(ci_type=postgresql_type).values_list('code', flat=True))
        self.assertTrue({'instance_id', 'endpoint', 'port', 'version', 'storage_gb', 'replica_count'}.issubset(postgresql_fields))
        kafka_fields = set(CIField.objects.filter(ci_type=kafka_type).values_list('code', flat=True))
        self.assertTrue({'instance_id', 'endpoint', 'topic_count', 'partition_count', 'message_lag', 'vpc_id'}.issubset(kafka_fields))
        rocketmq_fields = set(CIField.objects.filter(ci_type=rocketmq_type).values_list('code', flat=True))
        self.assertTrue({'instance_id', 'endpoint', 'http_endpoint', 'topic_count', 'group_count', 'message_lag'}.issubset(rocketmq_fields))
        emqx_fields = set(CIField.objects.filter(ci_type=emqx_type).values_list('code', flat=True))
        self.assertTrue({'cluster_id', 'endpoint', 'node_count', 'connection_count', 'topic_count'}.issubset(emqx_fields))
        block_storage_fields = set(CIField.objects.filter(ci_type=block_storage_type).values_list('code', flat=True))
        self.assertTrue({'volume_id', 'volume_type', 'capacity_gb', 'attached_to'}.issubset(block_storage_fields))
        file_storage_fields = set(CIField.objects.filter(ci_type=file_storage_type).values_list('code', flat=True))
        self.assertTrue({'filesystem_id', 'mount_target', 'protocol', 'capacity_gb', 'used_gb'}.issubset(file_storage_fields))
        hologres_fields = set(CIField.objects.filter(ci_type=hologres_type).values_list('code', flat=True))
        self.assertTrue({'instance_id', 'endpoint', 'version', 'cpu', 'storage_gb'}.issubset(hologres_fields))
        self.assertNotIn('region', hologres_fields)
        maxcompute_fields = set(CIField.objects.filter(ci_type=maxcompute_type).values_list('code', flat=True))
        self.assertTrue({'project_name', 'region', 'quota_name', 'storage_gb', 'job_count'}.issubset(maxcompute_fields))
        dataworks_fields = set(CIField.objects.filter(ci_type=dataworks_type).values_list('code', flat=True))
        self.assertTrue({'workspace_id', 'workspace_name', 'edition', 'node_count', 'workflow_count'}.issubset(dataworks_fields))
        self.assertNotIn('region', dataworks_fields)
        dw_fields = set(CIField.objects.filter(ci_type=dw_type).values_list('code', flat=True))
        self.assertTrue({'instance_id', 'endpoint', 'version', 'deployment_mode', 'instance_count', 'storage_gb'}.issubset(dw_fields))
        self.assertNotIn('deployment_ips', dw_fields)
        nifi_fields = set(CIField.objects.filter(ci_type=nifi_type).values_list('code', flat=True))
        self.assertTrue({'cluster_id', 'endpoint', 'version', 'deployment_mode', 'instance_count', 'flow_count'}.issubset(nifi_fields))
        self.assertNotIn('deployment_ips', nifi_fields)
        dolphinscheduler_fields = set(CIField.objects.filter(ci_type=dolphinscheduler_type).values_list('code', flat=True))
        self.assertTrue({'cluster_id', 'endpoint', 'version', 'deployment_mode', 'instance_count', 'worker_count', 'workflow_count'}.issubset(dolphinscheduler_fields))
        apisix_fields = set(CIField.objects.filter(ci_type=apisix_type).values_list('code', flat=True))
        self.assertTrue({'cluster_id', 'endpoint', 'admin_endpoint', 'version', 'deployment_mode', 'instance_count', 'route_count'}.issubset(apisix_fields))

        relation_rule = CIRelationRule.objects.filter(
            source_type__code='APP_SERVICE',
            target_type__code='CLOUD_SERVER',
            relation_type='runs_on',
        )
        self.assertEqual(relation_rule.count(), 1)
        self.assertTrue(CIRelationRule.objects.filter(
            source_type__code='APP_SERVICE',
            target_type__code='VIRTUAL_MACHINE',
            relation_type='runs_on',
        ).exists())
        self.assertTrue(CIRelationRule.objects.filter(
            source_type__code='APP_SERVICE',
            target_type__code='K8S_CLUSTER',
            relation_type='runs_on',
            is_active=True,
        ).exists())
        self.assertTrue(CIRelationRule.objects.filter(
            source_type__code='K8S_CLUSTER',
            target_type__code='CLOUD_SERVER',
            relation_type='runs_on',
            is_active=True,
        ).exists())
        self.assertFalse(CIRelationRule.objects.filter(
            source_type__code='K8S_CLUSTER',
            target_type__code='APP_SERVICE',
            relation_type='runs_on',
            is_active=True,
        ).exists())
        self.assertTrue(CIRelationRule.objects.filter(
            source_type__code='NGINX',
            target_type__code='APP_SERVICE',
            relation_type='connects_to',
        ).exists())
        self.assertTrue(CIRelationRule.objects.filter(
            source_type__code='DOMAIN',
            target_type__code='CERTIFICATE',
            relation_type='depends_on',
        ).exists())
        for target_code in [
            'POSTGRESQL',
            'MONGODB',
            'KAFKA',
            'ROCKETMQ',
            'RABBITMQ',
            'EMQX',
            'ELASTICSEARCH',
            'NACOS',
            'ZOOKEEPER',
            'OBJECT_STORAGE',
            'BLOCK_STORAGE',
            'FILE_STORAGE',
            'HADOOP',
            'FLINK',
            'CLICKHOUSE',
            'HOLOGRES',
            'MAXCOMPUTE',
            'DATAWORKS',
        ]:
            self.assertTrue(CIRelationRule.objects.filter(
                source_type__code='APP_SERVICE',
                target_type__code=target_code,
                relation_type='depends_on',
            ).exists())
        self.assertFalse(CIRelationRule.objects.filter(target_type__code__in=['SPARK', 'HIVE', 'HBASE', 'DORIS'], is_active=True).exists())
        self.assertTrue(CIThresholdPolicy.objects.filter(resource_type=cloud_type, metric='cpu_usage').exists())
        self.assertTrue(CIThresholdPolicy.objects.filter(resource_type=virtual_machine_type, metric='cpu_usage').exists())
        self.assertTrue(CISyncJob.objects.filter(name='阿里云 ECS 自动注册模板', source_type='aliyun_ecs').exists())
        for source_type in [
            'aliyun_mongodb',
            'aliyun_kafka',
            'aliyun_rocketmq',
            'aliyun_oss',
            'aliyun_slb',
            'vsphere_vm',
            'huaweicloud_ecs',
            'huaweicloud_rds',
            'huaweicloud_redis',
        ]:
            self.assertTrue(CISyncJob.objects.filter(source_type=source_type).exists())
        self.assertFalse(CISyncJob.objects.filter(source_type='idc_server_import', created_by='builtin').exists())
        vsphere_sync = CISyncJob.objects.get(source_type='vsphere_vm')
        self.assertEqual(vsphere_sync.config['target_ci_type_code'], 'VIRTUAL_MACHINE')
        self.assertEqual(vsphere_sync.config['unique_key'], 'instance_id')
        third_party_sync = CISyncJob.objects.get(source_type='third_party_import')
        third_party_items = third_party_sync.config.get('items') or []
        third_party_providers = {
            item.get('attributes', {}).get('provider')
            for item in third_party_items
        }
        self.assertTrue({'和风天气', '高德地图'}.issubset(third_party_providers))
        self.assertGreaterEqual(second_summary['relation_rules'], 10)
        self.assertGreaterEqual(second_summary['threshold_policies'], 8)

        response = self.client.post('/api/cmdb/model-groups/ensure-builtins/')
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['summary']['types'], second_summary['types'])
        self.assertGreaterEqual(payload['summary']['fields'], second_summary['fields'])
        self.assertGreaterEqual(payload['summary']['relation_rules'], second_summary['relation_rules'])
        self.assertGreaterEqual(payload['summary']['threshold_policies'], second_summary['threshold_policies'])
        self.assertEqual(payload['summary']['sync_jobs'], second_summary['sync_jobs'])
        self.assertTrue(CIChangeLog.objects.filter(action='cmdb_builtin_refresh', source='model').exists())

    def test_builtin_refresh_merges_obsolete_cloud_database_type(self):
        from multicloud.models import CloudAsset, CloudCredential, CloudEnvironment

        legacy_group = CIModelGroup.objects.create(
            code='data',
            name='数据与中间件',
            description='旧版数据资源分组',
            is_builtin=True,
        )
        legacy_type = CIType.objects.create(
            code='CLOUD_DATABASE',
            name='云数据库',
            group=legacy_group,
            is_builtin=True,
        )
        legacy_ci = ConfigItem.objects.create(
            name='legacy-rds',
            ci_type=legacy_type,
            business_line='交易系统',
            environment='prod',
        )
        docker_type = CIType.objects.create(
            code='DOCKER_ENV',
            name='Docker环境',
            group=legacy_group,
            is_builtin=True,
        )
        vsphere_capacity_type = CIType.objects.create(
            code='VSPHERE_CAPACITY',
            name='vSphere资源统计',
            group=legacy_group,
            is_builtin=True,
        )
        vsphere_capacity_ci = ConfigItem.objects.create(
            name='legacy-vsphere-capacity',
            ci_type=vsphere_capacity_type,
            business_line='交易系统',
            environment='prod',
        )
        eip_type = CIType.objects.create(code='EIP', name='弹性IP', group=legacy_group, is_builtin=True)
        eip_ci = ConfigItem.objects.create(
            name='legacy-eip',
            ci_type=eip_type,
            business_line='交易系统',
            environment='prod',
        )
        security_group_type = CIType.objects.create(code='SECURITY_GROUP', name='Security Group', group=legacy_group, is_builtin=True)
        security_group_ci = ConfigItem.objects.create(
            name='legacy-security-group',
            ci_type=security_group_type,
            business_line='交易系统',
            environment='prod',
        )
        CISourceMapping.objects.create(
            ci=security_group_ci,
            source_type='aliyun_security_group',
            source_account='prod-aliyun',
            source_region='cn-hangzhou',
            source_unique_id='sg-legacy-001',
        )
        credential = CloudCredential.objects.create(provider='aliyun', name='prod-aliyun')
        environment = CloudEnvironment.objects.create(
            credential=credential,
            name='prod',
            code='prod',
            region='cn-hangzhou',
        )
        CloudAsset.objects.create(
            environment=environment,
            provider='aliyun',
            resource_type='security_group',
            resource_id='sg-asset-001',
            name='sg-asset-001',
            region='cn-hangzhou',
        )
        data_warehouse_type = CIType.objects.create(code='', name='数据仓库', group=legacy_group, is_builtin=True)
        retired_bigdata_types = [data_warehouse_type]
        for code, name in [('SPARK', 'Spark'), ('HIVE', 'Hive'), ('HBASE', 'HBase'), ('DORIS', 'Doris')]:
            ci_type, _ = CIType.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'group': legacy_group,
                    'is_builtin': True,
                    'is_active': True,
                },
            )
            retired_bigdata_types.append(ci_type)

        ensure_builtin_cmdb()

        legacy_group.refresh_from_db()
        legacy_type.refresh_from_db()
        legacy_ci.refresh_from_db()
        docker_type.refresh_from_db()
        vsphere_capacity_type.refresh_from_db()
        vsphere_capacity_ci.refresh_from_db()
        eip_type.refresh_from_db()
        eip_ci.refresh_from_db()
        security_group_type.refresh_from_db()
        for retired_type in retired_bigdata_types:
            retired_type.refresh_from_db()
        self.assertFalse(legacy_group.is_active)
        self.assertFalse(legacy_type.is_active)
        self.assertFalse(docker_type.is_active)
        self.assertFalse(vsphere_capacity_type.is_active)
        self.assertFalse(eip_type.is_active)
        self.assertFalse(security_group_type.is_active)
        self.assertTrue(all(not retired_type.is_active for retired_type in retired_bigdata_types))
        self.assertEqual(legacy_ci.ci_type.code, 'MYSQL')
        self.assertEqual(eip_ci.ci_type.code, 'ELASTIC_IP')
        self.assertFalse(ConfigItem.objects.filter(id=security_group_ci.id).exists())
        self.assertFalse(CISourceMapping.objects.filter(source_type='aliyun_security_group').exists())
        self.assertFalse(CloudAsset.objects.filter(resource_type='security_group').exists())
        self.assertEqual(vsphere_capacity_ci.ci_type_id, vsphere_capacity_type.id)

    def test_internal_provider_summary_is_hidden_from_asset_ledger_by_default(self):
        vm_type, _ = CIType.objects.get_or_create(code='VIRTUAL_MACHINE', defaults={'name': '虚拟机'})
        summary_type, _ = CIType.objects.get_or_create(code='VSPHERE_CAPACITY', defaults={'name': 'vSphere资源统计'})
        vm_ci = ConfigItem.objects.create(
            name='example-app-vm-01',
            ci_type=vm_type,
            business_line='交易系统',
            environment='prod',
        )
        summary_ci = ConfigItem.objects.create(
            name='example-vsphere 资源统计',
            ci_type=summary_type,
            business_line='交易系统',
            environment='prod',
            attributes={
                'resource_kind': 'vsphere_capacity_summary',
                'source_unique_id': 'vsphere-summary:example-vsphere',
                'source_account': 'example-vsphere',
            },
        )
        CISourceMapping.objects.create(
            ci=summary_ci,
            source_type='vsphere_vm',
            source_account='example-vsphere',
            source_region='10.0.0.10',
            source_unique_id='vsphere-summary:example-vsphere',
        )

        ledger_response = self.client.get('/api/cmdb/config-items/')
        self.assertEqual(ledger_response.status_code, 200, ledger_response.content)
        ledger_payload = ledger_response.json()
        ledger_names = {item['name'] for item in ledger_payload['results']}
        self.assertIn(vm_ci.name, ledger_names)
        self.assertNotIn(summary_ci.name, ledger_names)
        self.assertEqual(ledger_payload['count'], 1)

        tree_response = self.client.get('/api/cmdb/config-items/ledger-tree/')
        self.assertEqual(tree_response.status_code, 200, tree_response.content)
        tree_names = {item['name'] for item in tree_response.json()}
        self.assertIn(vm_ci.name, tree_names)
        self.assertNotIn(summary_ci.name, tree_names)

        overview_tree_response = self.client.get('/api/cmdb/config-items/ledger-tree/?include_internal_summaries=1')
        self.assertEqual(overview_tree_response.status_code, 200, overview_tree_response.content)
        overview_tree_names = {item['name'] for item in overview_tree_response.json()}
        self.assertIn(vm_ci.name, overview_tree_names)
        self.assertIn(summary_ci.name, overview_tree_names)

        dashboard_response = self.client.get('/api/cmdb/dashboard/stats/')
        self.assertEqual(dashboard_response.status_code, 200, dashboard_response.content)
        dashboard_payload = dashboard_response.json()
        self.assertEqual(dashboard_payload['ci_total'], 1)
        self.assertFalse(
            any(item['type_name'] == 'vSphere资源统计' for item in dashboard_payload['ci_by_type'])
        )

    def test_asset_ledger_list_cache_is_invalidated_after_api_write(self):
        cache.clear()
        ci_type = CIType.objects.create(code='CACHE_LEDGER_HOST', name='缓存测试主机')
        ConfigItem.objects.create(name='ledger-cache-old', ci_type=ci_type, status='active')

        first_response = self.client.get('/api/cmdb/config-items/')
        self.assertEqual(first_response.status_code, 200, first_response.content)
        first_names = {item['name'] for item in first_response.json()['results']}
        self.assertIn('ledger-cache-old', first_names)
        self.assertNotIn('ledger-cache-new', first_names)

        create_response = self.client.post('/api/cmdb/config-items/', {
            'name': 'ledger-cache-new',
            'ci_type': ci_type.id,
            'business_line': '交易系统',
            'environment': 'prod',
            'status': 'active',
            'attributes': {},
        }, content_type='application/json')
        self.assertEqual(create_response.status_code, 201, create_response.content)

        second_response = self.client.get('/api/cmdb/config-items/')
        self.assertEqual(second_response.status_code, 200, second_response.content)
        second_names = {item['name'] for item in second_response.json()['results']}
        self.assertIn('ledger-cache-new', second_names)

    def test_asset_ledger_tree_cache_is_invalidated_after_api_write(self):
        cache.clear()
        ci_type = CIType.objects.create(code='CACHE_LEDGER_TREE_HOST', name='缓存测试树主机')
        ConfigItem.objects.create(name='ledger-tree-old', ci_type=ci_type, status='active')

        first_response = self.client.get('/api/cmdb/config-items/ledger-tree/')
        self.assertEqual(first_response.status_code, 200, first_response.content)
        first_names = {item['name'] for item in first_response.json()}
        self.assertIn('ledger-tree-old', first_names)
        self.assertNotIn('ledger-tree-new', first_names)

        create_response = self.client.post('/api/cmdb/config-items/', {
            'name': 'ledger-tree-new',
            'ci_type': ci_type.id,
            'business_line': '交易系统',
            'environment': 'prod',
            'status': 'active',
            'attributes': {'source_account': 'example-vsphere'},
        }, content_type='application/json')
        self.assertEqual(create_response.status_code, 201, create_response.content)

        second_response = self.client.get('/api/cmdb/config-items/ledger-tree/')
        self.assertEqual(second_response.status_code, 200, second_response.content)
        second_names = {item['name'] for item in second_response.json()}
        self.assertIn('ledger-tree-new', second_names)

    def test_builtin_refresh_merges_legacy_physical_host_type(self):
        legacy_type = CIType.objects.create(
            code='',
            name='物理机/宿主机',
            is_builtin=True,
            is_active=True,
        )
        legacy_ci = ConfigItem.objects.create(
            name='legacy-esxi-01',
            ci_type=legacy_type,
            business_line='基础设施',
            environment='prod',
        )

        ensure_builtin_cmdb()

        legacy_type.refresh_from_db()
        legacy_ci.refresh_from_db()
        self.assertFalse(legacy_type.is_active)
        self.assertEqual(legacy_ci.ci_type.code, 'IDC_SERVER')
        self.assertEqual(legacy_ci.ci_type.name, '物理机')

    def test_phase_one_manual_templates_run_and_create_core_items(self):
        ensure_builtin_cmdb()

        third_party_job = CISyncJob.objects.get(source_type='third_party_import')

        third_party_response = self.client.post(f'/api/cmdb/sync-jobs/{third_party_job.id}/run/', {}, content_type='application/json')

        self.assertEqual(third_party_response.status_code, 200, third_party_response.content)
        self.assertGreaterEqual(third_party_response.json()['summary']['create'], 3)

        third_party_providers = set(
            ConfigItem.objects.filter(ci_type__code='THIRD_PARTY_SERVICE')
            .values_list('attributes__provider', flat=True)
        )
        self.assertTrue({'和风天气', '高德地图'}.issubset(third_party_providers))
        self.assertTrue(CISourceMapping.objects.filter(source_type='third_party_import', source_unique_id='heweather-prod-account').exists())
        self.assertTrue(CISourceMapping.objects.filter(source_type='third_party_import', source_unique_id='amap-prod-account').exists())

    def test_cmdb_demo_seed_creates_total_resource_waterline(self):
        ensure_builtin_cmdb()
        seed_cmdb_demo()

        metric_names = set(CIResourceMetricSnapshot.objects.values_list('metric', flat=True))
        self.assertTrue({'cpu_usage', 'memory_usage', 'disk_usage', 'storage_usage'}.issubset(metric_names))
        idc_type = CIType.objects.get(code='IDC_SERVER')
        idc_items = {
            item.name: item.attributes
            for item in ConfigItem.objects.filter(ci_type=idc_type)
        }
        self.assertIn('idc-compute-01', idc_items)
        self.assertIn('idc-storage-01', idc_items)
        for attrs in idc_items.values():
            self.assertTrue(attrs.get('asset_sn'))
            self.assertTrue(attrs.get('private_ip'))
            self.assertTrue(attrs.get('idc'))
            self.assertTrue(attrs.get('rack'))
            self.assertTrue(attrs.get('u_position'))
            self.assertTrue(attrs.get('vendor'))
            self.assertTrue(attrs.get('model'))
            self.assertTrue(attrs.get('serial_number'))
            self.assertTrue(attrs.get('service_expiry_date'))
            self.assertGreater(attrs.get('cpu') or 0, 0)
            self.assertGreater(attrs.get('memory_gb') or 0, 0)
            self.assertGreater(attrs.get('disk_gb') or 0, 0)
        self.assertTrue(CIResourceMetricSnapshot.objects.filter(ci__name='idc-compute-01', metric='cpu_usage').exists())
        self.assertTrue(CIResourceMetricSnapshot.objects.filter(ci__name='idc-storage-01', metric='disk_usage').exists())
        third_party_type = CIType.objects.get(code='THIRD_PARTY_SERVICE')
        third_party_providers = set(
            ConfigItem.objects.filter(ci_type=third_party_type)
            .values_list('attributes__provider', flat=True)
        )
        self.assertTrue({'和风天气', '高德地图'}.issubset(third_party_providers))
        self.assertTrue(CIRelation.objects.filter(source__name='order-service', target__name='heweather-prod', relation_type='depends_on').exists())
        self.assertTrue(CIRelation.objects.filter(source__name='order-service', target__name='amap-prod', relation_type='depends_on').exists())

        response = self.client.get('/api/cmdb/dashboard/stats/')
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        waterline = payload['capacity_waterline']
        self.assertGreaterEqual(waterline['warning'], 1)
        self.assertTrue(any(
            item['metric'] == 'storage_usage'
            and item['ci_name'] == 'log-archive-oss'
            and item['status'] == 'warning'
            for item in waterline['top_risks']
        ))
        coverage = payload['phase_one_coverage']
        self.assertFalse(coverage['ready'])
        self.assertTrue(coverage['waterline']['ready'])
        self.assertTrue(coverage['waterline']['request_needed'])
        self.assertEqual(coverage['sync']['present'], len(PHASE_ONE_REQUIRED_SYNC_TYPES))
        self.assertEqual(coverage['sync']['total'], len(PHASE_ONE_REQUIRED_SYNC_TYPES))
        self.assertTrue(coverage['sync']['ready'])
        self.assertEqual(coverage['idc']['count'], 2)
        self.assertEqual(coverage['idc']['hardware_ready'], 2)
        self.assertTrue(coverage['idc']['ready'])
        self.assertEqual(coverage['cloud']['total'], 3)
        self.assertFalse(coverage['cloud']['ready'])
        self.assertEqual(coverage['aliyun_middleware']['total'], len(PHASE_ONE_ALIYUN_MIDDLEWARE_CODES))
        self.assertGreaterEqual(coverage['aliyun_middleware']['present'], 3)
        self.assertFalse(coverage['aliyun_middleware']['ready'])
        self.assertTrue(coverage['third_party']['ready'])
        third_party_providers = {
            item['label']: item['ready']
            for item in coverage['third_party']['providers']
        }
        self.assertTrue(third_party_providers['和风天气'])
        self.assertTrue(third_party_providers['高德地图'])
        self.assertTrue(any(item['type'] == 'capacity' for item in payload['application_suggestions']))

    def test_phase_one_coverage_becomes_ready_when_all_core_sources_exist(self):
        ensure_builtin_cmdb()
        seed_cmdb_demo()

        cloud_type = CIType.objects.get(code='CLOUD_SERVER')
        ConfigItem.objects.create(
            name='vmware-billing-vm-01',
            ci_type=cloud_type,
            business_line='财务线',
            environment='prod',
            admin_user='SRE-王涛',
            status='active',
            attributes={
                'instance_id': 'vm-501',
                'private_ip': '10.70.1.10',
                'cpu': 8,
                'memory_gb': 32,
                'disk_gb': 500,
                'cloud_provider': 'vSphere',
                'source_type': 'vsphere_vm',
                'source_unique_id': 'vm-501',
            },
        )
        ConfigItem.objects.create(
            name='huawei-shared-ecs-01',
            ci_type=cloud_type,
            business_line='政企线',
            environment='prod',
            admin_user='SRE-刘哲',
            status='active',
            attributes={
                'instance_id': 'hw-ecs-001',
                'private_ip': '10.80.1.10',
                'cpu': 4,
                'memory_gb': 16,
                'disk_gb': 200,
                'cloud_provider': '华为云 ECS',
                'source_type': 'huaweicloud_ecs',
                'source_unique_id': 'hw-ecs-001',
            },
        )

        middleware_specs = [
            (
                code,
                f"aliyun-{code.lower().replace('_', '-')}-prod",
                {
                    'instance_id': f'{code.lower()}-001',
                    'endpoint': f"{code.lower().replace('_', '-')}.aliyun.example.com",
                },
            )
            for code in PHASE_ONE_ALIYUN_MIDDLEWARE_CODES
        ]
        for code, name, attrs in middleware_specs:
            ConfigItem.objects.create(
                name=name,
                ci_type=CIType.objects.get(code=code),
                business_line='电商线',
                environment='prod',
                admin_user='SRE-王涛',
                status='active',
                attributes={
                    **attrs,
                    'cloud_provider': '阿里云',
                    'source_account': 'trade-prod',
                    'source_region': 'cn-hangzhou',
                    'source_type': f'aliyun_{code.lower()}',
                    'source_unique_id': attrs.get('instance_id') or attrs.get('bucket') or name,
                },
            )

        response = self.client.get('/api/cmdb/dashboard/stats/')
        self.assertEqual(response.status_code, 200, response.content)
        coverage = response.json()['phase_one_coverage']

        self.assertTrue(coverage['ready'])
        self.assertTrue(coverage['cloud']['ready'])
        self.assertEqual(coverage['cloud']['present'], 3)
        cloud_providers = {
            item['key']: item['ready']
            for item in coverage['cloud']['providers']
        }
        self.assertTrue(cloud_providers['vsphere'])
        self.assertTrue(cloud_providers['aliyun'])
        self.assertTrue(cloud_providers['huaweicloud'])
        self.assertTrue(coverage['aliyun_middleware']['ready'])
        self.assertEqual(coverage['aliyun_middleware']['present'], len(PHASE_ONE_ALIYUN_MIDDLEWARE_CODES))
        self.assertTrue(coverage['idc']['ready'])
        self.assertTrue(coverage['third_party']['ready'])
        self.assertTrue(coverage['waterline']['ready'])

    def test_third_party_service_filters_and_expiry_risk_summary(self):
        third_party_type = _ci_type('第三方服务', code='THIRD_PARTY_SERVICE')
        today = timezone.localdate()
        risky_ci = ConfigItem.objects.create(
            name='sms-prod-account',
            ci_type=third_party_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={
                'provider': '示例供应商',
                'service_type': '短信',
                'service_expiry_date': (today + timezone.timedelta(days=7)).isoformat(),
                'service_expire_warning_days': 30,
            },
        )
        normal_ci = ConfigItem.objects.create(
            name='ocr-backup-account',
            ci_type=third_party_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={
                'provider': '其他供应商',
                'service_type': 'OCR',
                'service_expiry_date': (today + timezone.timedelta(days=180)).isoformat(),
            },
        )
        missing_ci = ConfigItem.objects.create(
            name='unregistered-expiry-account',
            ci_type=third_party_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'provider': '未登记供应商', 'service_type': '推送'},
        )

        response = self.client.get('/api/cmdb/config-items/', {
            'ci_type': third_party_type.id,
            'provider': '示例供应商',
            'service_type': '短信',
            'expiry_risk': 'risk',
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        self.assertEqual([item['id'] for item in rows], [risky_ci.id])

        normal_response = self.client.get('/api/cmdb/config-items/', {
            'ci_type': third_party_type.id,
            'expiry_risk': 'normal',
        })
        normal_rows = normal_response.json().get('results', [])
        self.assertEqual([item['id'] for item in normal_rows], [normal_ci.id])

        missing_response = self.client.get('/api/cmdb/config-items/', {
            'ci_type': third_party_type.id,
            'expiry_risk': 'missing',
        })
        missing_rows = missing_response.json().get('results', [])
        self.assertEqual([item['id'] for item in missing_rows], [missing_ci.id])

        dashboard_response = self.client.get('/api/cmdb/dashboard/stats/')
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard = dashboard_response.json()
        self.assertEqual(dashboard['risk_summary']['service_expiry'], 1)
        self.assertTrue(any(item['type'].startswith('third_party_') for item in dashboard['application_suggestions']))

        summary_response = self.client.get('/api/cmdb/config-items/third-party-expiry-summary/')
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.json(), {
            'total': 3,
            'normal': 1,
            'warning': 0,
            'urgent': 1,
            'expired': 0,
            'missing': 1,
        })

        tree_response = self.client.get('/api/cmdb/config-items/ledger-tree/')
        self.assertEqual(tree_response.status_code, 200)
        tree_row = next(item for item in tree_response.json() if item['id'] == risky_ci.id)
        self.assertEqual(tree_row['ci_type_group'], third_party_type.group_id)
        self.assertEqual(tree_row['ci_type_group_code'], 'external')
        self.assertEqual(tree_row['ci_type_group_name'], '其他资产')
        self.assertEqual(tree_row['attributes']['service_expiry_date'], (today + timezone.timedelta(days=7)).isoformat())
        self.assertEqual(tree_row['attributes']['service_expire_warning_days'], 30)

    def test_idc_server_filters_lifecycle_and_service_expiry_summary(self):
        idc_type = _ci_type('物理机', code='IDC_SERVER')
        today = timezone.localdate()
        risky_ci = ConfigItem.objects.create(
            name='idc-prod-01',
            ci_type=idc_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={
                'asset_sn': 'ASSET-IDC-001',
                'private_ip': '10.60.1.10',
                'idc': 'A机房',
                'rack': 'R01',
                'u_position': '12U',
                'lifecycle_status': 'running',
                'purchase_date': (today - timezone.timedelta(days=800)).isoformat(),
                'service_expiry_date': (today + timezone.timedelta(days=7)).isoformat(),
                'service_expire_warning_days': 30,
                'ops_owner': 'idc-ops',
                'vendor': 'Dell',
                'model': 'R740',
                'serial_number': 'SN-IDC-001',
            },
        )
        ConfigItem.objects.create(
            name='idc-other-01',
            ci_type=idc_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={
                'asset_sn': 'ASSET-IDC-002',
                'private_ip': '10.60.1.11',
                'idc': 'B机房',
                'rack': 'R09',
                'lifecycle_status': 'maintenance',
                'service_expiry_date': (today + timezone.timedelta(days=180)).isoformat(),
            },
        )

        response = self.client.get('/api/cmdb/config-items/', {
            'ci_type': idc_type.id,
            'idc': 'A机房',
            'rack': 'R01',
            'lifecycle_status': 'running',
            'service_expiry_risk': 'risk',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        self.assertEqual([item['id'] for item in rows], [risky_ci.id])

        cache.clear()
        dashboard_response = self.client.get('/api/cmdb/dashboard/stats/')
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard = dashboard_response.json()
        self.assertEqual(dashboard['risk_summary']['service_expiry'], 1)
        self.assertTrue(any(item['type'] == 'asset_service_expiry' for item in dashboard['service_expiry_risks']))

    def test_cmdb_rejects_plaintext_secrets_on_ci_sync_job_and_import(self):
        third_party_type = _ci_type('第三方服务', code='THIRD_PARTY_SERVICE')
        allowed_response = self.client.post(
            '/api/cmdb/config-items/',
            data=json.dumps({
                'name': 'sms-provider-safe',
                'ci_type': third_party_type.id,
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'ops',
                'status': 'active',
                'attributes': {
                    'provider': '短信供应商',
                    'service_type': '短信',
                    'backup_plan': '备用短信通道',
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(allowed_response.status_code, 201, allowed_response.content)

        secret_ci_response = self.client.post(
            '/api/cmdb/config-items/',
            data=json.dumps({
                'name': 'sms-provider-secret',
                'ci_type': third_party_type.id,
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'ops',
                'status': 'active',
                'attributes': {
                    'provider': '短信供应商',
                    'service_type': '短信',
                    'api_key': 'plaintext-secret',
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(secret_ci_response.status_code, 400)
        self.assertFalse(ConfigItem.objects.filter(name='sms-provider-secret').exists())

        secret_job_response = self.client.post(
            '/api/cmdb/sync-jobs/',
            data=json.dumps({
                'name': '带密钥的同步任务',
                'source_type': 'aliyun_ecs',
                'mode': 'manual',
                'config': {
                    'connector': 'aliyun',
                    'resource_type': 'ecs',
                    'access_key_secret': 'plaintext-secret',
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(secret_job_response.status_code, 400)
        self.assertFalse(CISyncJob.objects.filter(name='带密钥的同步任务').exists())

        secret_import_response = self.client.post(
            '/api/cmdb/config-items/bulk-import/',
            data=json.dumps({
                'items': [{
                    'ci_type_code': 'THIRD_PARTY_SERVICE',
                    'name': 'secret-import-provider',
                    'source_unique_id': 'secret-import-provider',
                    'business_line': 'core',
                    'environment': 'prod',
                    'admin_user': 'ops',
                    'attributes': {
                        'provider': '短信供应商',
                        'service_type': '短信',
                        'token': 'plaintext-token',
                    },
                }],
            }),
            content_type='application/json',
        )
        self.assertEqual(secret_import_response.status_code, 400)
        self.assertFalse(ConfigItem.objects.filter(name='secret-import-provider').exists())

    def test_model_view_permission_can_list_ci_types_without_ci_view_permission(self):
        ensure_builtin_rbac()
        ensure_builtin_cmdb()
        permission = PermissionDefinition.objects.get(code='cmdb.model.view')
        role = Role.objects.create(code='cmdb-model-view-only', name='CMDB Model View Only')
        role.permissions.add(permission)
        viewer = get_user_model().objects.create_user('model-viewer', 'model-viewer@example.com', 'Admin@123456')
        role.users.add(viewer)

        self.client.force_login(viewer)
        response = self.client.get('/api/cmdb/ci-types/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['code'] == 'CLOUD_SERVER' for item in response.json()))

    def test_ci_view_permission_can_read_model_field_metadata_without_model_permission(self):
        ensure_builtin_rbac()
        ensure_builtin_cmdb()
        permission = PermissionDefinition.objects.get(code='cmdb.ci.view')
        role = Role.objects.create(code='cmdb-ci-view-only', name='CMDB CI View Only')
        role.permissions.add(permission)
        viewer = get_user_model().objects.create_user('ci-viewer', 'ci-viewer@example.com', 'Admin@123456')
        role.users.add(viewer)
        third_party_type = CIType.objects.get(code='THIRD_PARTY_SERVICE')

        self.client.force_login(viewer)
        types_response = self.client.get('/api/cmdb/ci-types/')
        fields_response = self.client.get('/api/cmdb/ci-fields/', {'ci_type': third_party_type.id})
        create_response = self.client.post(
            '/api/cmdb/ci-fields/',
            {
                'ci_type': third_party_type.id,
                'name': '测试字段',
                'code': 'test_field',
                'field_type': 'string',
            },
            content_type='application/json',
        )

        self.assertEqual(types_response.status_code, 200)
        self.assertEqual(fields_response.status_code, 200)
        fields_payload = fields_response.json()
        field_rows = fields_payload.get('results', fields_payload) if isinstance(fields_payload, dict) else fields_payload
        required_codes = {
            item['code']
            for item in field_rows
            if item.get('required')
        }
        self.assertIn('provider', required_codes)
        self.assertNotIn('account_owner', required_codes)
        self.assertNotIn('service_type', required_codes)
        self.assertFalse(any(item['code'] in {'account_owner', 'key_owner', 'key_expire_date'} for item in field_rows))
        self.assertEqual(create_response.status_code, 403)
        self.assertFalse(CIField.objects.filter(ci_type=third_party_type, code='test_field').exists())

    def test_topology_view_permission_can_list_ci_types_without_ci_view_permission(self):
        ensure_builtin_rbac()
        ensure_builtin_cmdb()
        permission = PermissionDefinition.objects.get(code='cmdb.topology.view')
        role = Role.objects.create(code='cmdb-topology-view-only', name='CMDB Topology View Only')
        role.permissions.add(permission)
        viewer = get_user_model().objects.create_user('topology-viewer', 'topology-viewer@example.com', 'Admin@123456')
        role.users.add(viewer)

        self.client.force_login(viewer)
        response = self.client.get('/api/cmdb/ci-types/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['code'] == 'CLOUD_SERVER' for item in response.json()))

    def test_builtin_model_metadata_cannot_be_deleted(self):
        ensure_builtin_cmdb()
        group = CIModelGroup.objects.get(code='compute')
        ci_type = CIType.objects.get(code='CLOUD_SERVER')
        field = CIField.objects.get(ci_type=ci_type, code='instance_id')

        group_response = self.client.delete(f'/api/cmdb/model-groups/{group.id}/')
        type_response = self.client.delete(f'/api/cmdb/ci-types/{ci_type.id}/')
        field_response = self.client.delete(f'/api/cmdb/ci-fields/{field.id}/')

        self.assertEqual(group_response.status_code, 400)
        self.assertEqual(type_response.status_code, 400)
        self.assertEqual(field_response.status_code, 400)
        self.assertTrue(CIType.objects.filter(code='CLOUD_SERVER').exists())
        self.assertTrue(CIField.objects.filter(ci_type=ci_type, code='instance_id').exists())

    def test_builtin_model_and_field_core_constraints_cannot_be_modified(self):
        ensure_builtin_cmdb()
        ci_type = CIType.objects.get(code='CLOUD_SERVER')
        field = CIField.objects.get(ci_type=ci_type, code='instance_id')

        type_response = self.client.patch(
            f'/api/cmdb/ci-types/{ci_type.id}/',
            {'code': 'BROKEN_CLOUD_SERVER', 'name': '错误云模型'},
            content_type='application/json',
        )
        self.assertEqual(type_response.status_code, 400)
        ci_type.refresh_from_db()
        self.assertEqual(ci_type.code, 'CLOUD_SERVER')
        self.assertEqual(ci_type.name, '云主机(ECS)')

        field_response = self.client.patch(
            f'/api/cmdb/ci-fields/{field.id}/',
            {'code': 'broken_instance_id', 'field_type': 'integer', 'required': False, 'unique': False},
            content_type='application/json',
        )
        self.assertEqual(field_response.status_code, 400)
        field.refresh_from_db()
        self.assertEqual(field.code, 'instance_id')
        self.assertEqual(field.field_type, 'string')
        self.assertTrue(field.required)
        self.assertTrue(field.unique)

        display_response = self.client.patch(
            f'/api/cmdb/ci-fields/{field.id}/',
            {'is_display': False, 'sort_order': 11, 'sync_mode': 'manual'},
            content_type='application/json',
        )
        self.assertEqual(display_response.status_code, 200, display_response.content)
        field.refresh_from_db()
        self.assertFalse(field.is_display)
        self.assertEqual(field.sort_order, 11)
        self.assertEqual(field.sync_mode, 'manual')

    def test_threshold_policy_api_validates_threshold_order(self):
        ci_type = _ci_type('阈值测试云主机', code='THRESHOLD_TEST_SERVER')

        create_response = self.client.post(
            '/api/cmdb/threshold-policies/',
            {
                'resource_type': ci_type.id,
                'metric': 'cpu_usage',
                'normal_threshold': '70',
                'warning_threshold': '85',
                'critical_threshold': '95',
                'exceeded_threshold': '100',
                'enabled': True,
            },
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        policy_id = create_response.json()['id']

        invalid_response = self.client.patch(
            f'/api/cmdb/threshold-policies/{policy_id}/',
            data=json.dumps({'warning_threshold': '60'}),
            content_type='application/json',
        )
        self.assertEqual(invalid_response.status_code, 400)
        self.assertIn('thresholds', invalid_response.json())

        list_response = self.client.get('/api/cmdb/threshold-policies/', {'resource_type': ci_type.id})
        self.assertEqual(list_response.status_code, 200)
        rows = list_response.json()['results'] if 'results' in list_response.json() else list_response.json()
        self.assertEqual(len(rows), 1)

    def test_source_mapping_api_rejects_duplicate_source_identity(self):
        ci_type = _ci_type('来源映射云主机', code='SOURCE_MAPPING_SERVER')
        first_ci = ConfigItem.objects.create(name='source-map-ecs-01', ci_type=ci_type)
        second_ci = ConfigItem.objects.create(name='source-map-ecs-02', ci_type=ci_type)

        create_response = self.client.post(
            '/api/cmdb/source-mappings/',
            {
                'ci': first_ci.id,
                'source_type': 'aliyun_ecs',
                'source_account': 'prod-account',
                'source_region': 'cn-hangzhou',
                'source_unique_id': 'i-source-map-001',
                'sync_status': 'success',
            },
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)

        duplicate_response = self.client.post(
            '/api/cmdb/source-mappings/',
            {
                'ci': second_ci.id,
                'source_type': 'aliyun_ecs',
                'source_account': 'prod-account',
                'source_region': 'cn-hangzhou',
                'source_unique_id': 'i-source-map-001',
                'sync_status': 'success',
            },
        )
        self.assertEqual(duplicate_response.status_code, 400)
        self.assertIn('source_unique_id', duplicate_response.json())

        list_response = self.client.get('/api/cmdb/source-mappings/', {'source_type': 'aliyun_ecs'})
        self.assertEqual(list_response.status_code, 200)
        rows = list_response.json()['results'] if 'results' in list_response.json() else list_response.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['ci_name'], 'source-map-ecs-01')

    def test_source_mapping_account_region_options_include_all_distinct_pairs(self):
        ci_type = _ci_type('来源账号选项云主机', code='SOURCE_ACCOUNT_OPTIONS_SERVER')
        first_ci = ConfigItem.objects.create(name='source-account-options-01', ci_type=ci_type)
        second_ci = ConfigItem.objects.create(name='source-account-options-02', ci_type=ci_type)
        third_ci = ConfigItem.objects.create(name='source-account-options-03', ci_type=ci_type)
        CISourceMapping.objects.create(
            ci=first_ci,
            source_type='aliyun_ecs',
            source_account='shared-account',
            source_region='cn-hangzhou',
            source_unique_id='source-account-options-01',
        )
        CISourceMapping.objects.create(
            ci=second_ci,
            source_type='aliyun_rds',
            source_account='shared-account',
            source_region='cn-beijing',
            source_unique_id='source-account-options-02',
        )
        CISourceMapping.objects.create(
            ci=third_ci,
            source_type='vsphere_vm',
            source_account='',
            source_region='Datacenter',
            source_unique_id='source-account-options-03',
        )

        response = self.client.get('/api/cmdb/source-mappings/account-region-options/')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json(),
            [
                {'source_account': 'shared-account', 'source_region': 'cn-beijing'},
                {'source_account': 'shared-account', 'source_region': 'cn-hangzhou'},
            ],
        )

    def test_sync_job_api_validates_field_mapping_config(self):
        valid_dict_response = self.client.post(
            '/api/cmdb/sync-jobs/',
            data=json.dumps({
                'name': '字段映射对象配置',
                'source_type': 'manual_import',
                'mode': 'manual',
                'config': {
                    'target_ci_type_code': 'FIELD_MAPPING_SERVICE',
                    'field_mapping': {
                        'business_line': 'labels.biz',
                        'admin_user': 'labels.owner',
                        'attributes.department': 'org.dept',
                    },
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(valid_dict_response.status_code, 201, valid_dict_response.content)

        valid_list_response = self.client.post(
            '/api/cmdb/sync-jobs/',
            data=json.dumps({
                'name': '字段映射列表配置',
                'source_type': 'manual_import',
                'mode': 'manual',
                'config': {
                    'target_ci_type_code': 'FIELD_MAPPING_SERVICE',
                    'field_mapping': [
                        {'target': 'business_line', 'source': 'labels.biz', 'required': True},
                        {'target': 'environment', 'source': 'labels.env', 'default': 'prod'},
                        {'target_field': 'attributes.department', 'source_field': 'org.dept'},
                    ],
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(valid_list_response.status_code, 201, valid_list_response.content)

        missing_source_response = self.client.post(
            '/api/cmdb/sync-jobs/',
            data=json.dumps({
                'name': '字段映射缺来源',
                'source_type': 'manual_import',
                'mode': 'manual',
                'config': {
                    'field_mapping': [
                        {'target': 'business_line', 'source': 'labels.biz'},
                        {'target': 'admin_user'},
                    ],
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(missing_source_response.status_code, 400)
        self.assertIn('field_mapping', json.dumps(missing_source_response.json(), ensure_ascii=False))
        self.assertFalse(CISyncJob.objects.filter(name='字段映射缺来源').exists())

        duplicate_target_response = self.client.post(
            '/api/cmdb/sync-jobs/',
            data=json.dumps({
                'name': '字段映射目标重复',
                'source_type': 'manual_import',
                'mode': 'manual',
                'config': {
                    'field_mapping': [
                        {'target': 'business_line', 'source': 'labels.biz'},
                        {'target': 'business_line', 'source': 'labels.business'},
                    ],
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(duplicate_target_response.status_code, 400)
        self.assertIn('重复', json.dumps(duplicate_target_response.json(), ensure_ascii=False))
        self.assertFalse(CISyncJob.objects.filter(name='字段映射目标重复').exists())

    def test_sync_job_field_mapping_normalizes_generic_raw_items(self):
        ci_type = _ci_type('字段映射服务', code='FIELD_MAPPING_SERVICE')
        CIField.objects.create(
            ci_type=ci_type,
            name='服务端点',
            code='endpoint',
            field_type='url',
            required=True,
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='部门',
            code='department',
            field_type='string',
            required=True,
            sync_mode='manual',
        )
        job = CISyncJob.objects.create(
            name='字段映射采集任务',
            source_type='third_party_service',
            mode='manual',
            config={
                'target_ci_type_code': 'FIELD_MAPPING_SERVICE',
                'raw_items': [{
                    'metadata': {
                        'uuid': 'svc-field-map-001',
                        'title': 'sms-provider-field-map',
                    },
                    'labels': {
                        'biz': 'core',
                        'env': 'prod',
                        'owner': 'ops',
                    },
                    'org': {'dept': '基础架构部'},
                    'spec': {'url': 'https://sms.example.com'},
                }],
                'field_mapping': {
                    'source_unique_id': 'metadata.uuid',
                    'name': 'metadata.title',
                    'business_line': 'labels.biz',
                    'environment': 'labels.env',
                    'admin_user': 'labels.owner',
                    'attributes.department': 'org.dept',
                    'attributes.endpoint': 'spec.url',
                },
            },
        )

        dry_run = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/dry-run/', {}, content_type='application/json')

        self.assertEqual(dry_run.status_code, 200, dry_run.content)
        dry_payload = dry_run.json()
        self.assertEqual(dry_payload['summary']['create'], 1)
        self.assertEqual(dry_payload['records'][0]['after']['name'], 'sms-provider-field-map')
        self.assertEqual(dry_payload['records'][0]['after']['attributes']['endpoint'], 'https://sms.example.com')
        self.assertFalse(ConfigItem.objects.filter(name='sms-provider-field-map').exists())

        run_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(run_response.status_code, 200, run_response.content)
        ci = ConfigItem.objects.get(name='sms-provider-field-map')
        self.assertEqual(ci.ci_type, ci_type)
        self.assertEqual(ci.business_line, 'core')
        self.assertEqual(ci.admin_user, 'ops')
        self.assertEqual(ci.attributes['department'], '基础架构部')
        self.assertEqual(ci.attributes['endpoint'], 'https://sms.example.com')
        self.assertTrue(CISourceMapping.objects.filter(ci=ci, source_type='third_party_service', source_unique_id='svc-field-map-001').exists())

        summary_response = self.client.get('/api/cmdb/collection/summary/')
        self.assertEqual(summary_response.status_code, 200)
        row = next(item for item in summary_response.json()['jobs'] if item['id'] == job.id)
        self.assertEqual(row['field_mapping_count'], 7)

    def test_sync_job_manage_permission_can_update_and_delete_job(self):
        ensure_builtin_rbac()
        viewer_role = Role.objects.create(code='sync-viewer-role', name='Sync Viewer Role')
        viewer_role.permissions.add(PermissionDefinition.objects.get(code='cmdb.sync.view'))
        manager_role = Role.objects.create(code='sync-manager-role', name='Sync Manager Role')
        manager_role.permissions.add(
            PermissionDefinition.objects.get(code='cmdb.sync.view'),
            PermissionDefinition.objects.get(code='cmdb.sync.manage'),
        )
        viewer = get_user_model().objects.create_user('sync-viewer', password='Admin@123456')
        viewer.rbac_roles.add(viewer_role)
        manager = get_user_model().objects.create_user('sync-manager', password='Admin@123456')
        manager.rbac_roles.add(manager_role)
        job = CISyncJob.objects.create(
            name='旧 ECS 采集任务',
            source_type='aliyun_ecs',
            mode='manual',
            config={'collection_enabled': False, 'items': []},
        )
        CISyncRecord.objects.create(
            job=job,
            action='skip',
            status='success',
            source_unique_id='sync-job-manage-001',
            after={'name': 'skip'},
        )

        self.client.force_login(viewer)
        denied_update = self.client.patch(
            f'/api/cmdb/sync-jobs/{job.id}/',
            data=json.dumps({'name': '只读用户不应更新'}),
            content_type='application/json',
        )
        self.assertEqual(denied_update.status_code, 403)

        self.client.force_login(manager)
        update_response = self.client.patch(
            f'/api/cmdb/sync-jobs/{job.id}/',
            data=json.dumps({
                'name': '生产 ECS 采集任务',
                'mode': 'scheduled',
                'dry_run': True,
                'config': {
                    'collection_enabled': True,
                    'interval_minutes': 30,
                    'full_sync': True,
                    'items': [],
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200, update_response.content)
        self.assertEqual(update_response.json()['name'], '生产 ECS 采集任务')
        self.assertEqual(update_response.json()['mode'], 'scheduled')
        self.assertTrue(update_response.json()['dry_run'])
        self.assertTrue(update_response.json()['config']['collection_enabled'])

        delete_response = self.client.delete(f'/api/cmdb/sync-jobs/{job.id}/')
        self.assertEqual(delete_response.status_code, 204, delete_response.content)
        self.assertFalse(CISyncJob.objects.filter(id=job.id).exists())
        self.assertFalse(CISyncRecord.objects.filter(source_unique_id='sync-job-manage-001').exists())

    def test_custom_model_group_crud_and_delete_protection(self):
        create_response = self.client.post('/api/cmdb/model-groups/', {
            'name': '自定义资源域',
            'code': 'custom_asset_domain',
            'description': '页面维护的自定义模型分组',
            'sort_order': 88,
            'is_active': True,
        })
        self.assertEqual(create_response.status_code, 201, create_response.content)
        group_id = create_response.json()['id']

        update_response = self.client.patch(
            f'/api/cmdb/model-groups/{group_id}/',
            {'description': '已更新说明', 'is_active': False},
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200, update_response.content)
        self.assertEqual(update_response.json()['description'], '已更新说明')
        self.assertFalse(update_response.json()['is_active'])

        CIType.objects.create(name='自定义模型', code='CUSTOM_ASSET', group_id=group_id)
        protected_response = self.client.delete(f'/api/cmdb/model-groups/{group_id}/')
        self.assertEqual(protected_response.status_code, 400)
        self.assertTrue(CIModelGroup.objects.filter(id=group_id).exists())

        CIType.objects.filter(code='CUSTOM_ASSET').delete()
        delete_response = self.client.delete(f'/api/cmdb/model-groups/{group_id}/')
        self.assertEqual(delete_response.status_code, 204, delete_response.content)
        self.assertFalse(CIModelGroup.objects.filter(id=group_id).exists())

    def test_config_item_validates_attributes_with_ci_fields(self):
        ci_type = CIType.objects.create(name='测试云主机', code='TEST_CLOUD_SERVER')
        CIField.objects.create(
            ci_type=ci_type,
            name='实例 ID',
            code='instance_id',
            field_type='string',
            required=True,
            unique=True,
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='私网 IP',
            code='private_ip',
            field_type='ip',
            required=True,
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='运行状态',
            code='instance_status',
            field_type='enum',
            options=[
                {'value': 'Running', 'label': '运行中'},
                {'value': 'Stopped', 'label': '已停止'},
            ],
        )

        response = self.client.post(
            '/api/cmdb/config-items/',
            {
                'name': 'ecs-01',
                'ci_type': ci_type.id,
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'ops',
                'status': 'active',
                'attributes': {
                    'instance_id': 'i-001',
                    'private_ip': '10.0.0.8',
                    'instance_status': 'Running',
                },
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        duplicate = self.client.post(
            '/api/cmdb/config-items/',
            {
                'name': 'ecs-02',
                'ci_type': ci_type.id,
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'ops',
                'status': 'active',
                'attributes': {
                    'instance_id': 'i-001',
                    'private_ip': '10.0.0.9',
                    'instance_status': 'Running',
                },
            },
            content_type='application/json',
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn('instance_id', json.dumps(duplicate.json(), ensure_ascii=False))

        invalid_ip = self.client.post(
            '/api/cmdb/config-items/',
            {
                'name': 'ecs-03',
                'ci_type': ci_type.id,
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'ops',
                'status': 'active',
                'attributes': {
                    'instance_id': 'i-003',
                    'private_ip': 'bad-ip',
                    'instance_status': 'Running',
                },
            },
            content_type='application/json',
        )
        self.assertEqual(invalid_ip.status_code, 400)
        self.assertIn('private_ip', json.dumps(invalid_ip.json(), ensure_ascii=False))

    def test_config_item_validates_date_datetime_range_and_normalized_unique_fields(self):
        ci_type = CIType.objects.create(name='校验增强云主机', code='VALIDATION_CLOUD_SERVER')
        CIField.objects.create(
            ci_type=ci_type,
            name='CPU',
            code='cpu',
            field_type='integer',
            unique=True,
            validation={'min': 1, 'max': 64},
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='维保到期日',
            code='warranty_end_date',
            field_type='date',
            validation={'min': '2026-01-01', 'max': '2027-12-31'},
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='最近采集时间',
            code='last_seen_at',
            field_type='datetime',
            validation={'min': '2026-01-01T00:00:00', 'max': '2026-12-31T23:59:59'},
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='资产编码',
            code='asset_code',
            field_type='string',
            validation={'min_length': 3, 'max_length': 12},
        )

        response = self.client.post(
            '/api/cmdb/config-items/',
            {
                'name': 'validation-ecs-01',
                'ci_type': ci_type.id,
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'ops',
                'status': 'active',
                'attributes': {
                    'cpu': '8',
                    'warranty_end_date': '2026-12-31',
                    'last_seen_at': '2026-07-15 10:20:30',
                    'asset_code': 'srv001',
                },
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        ci = ConfigItem.objects.get(name='validation-ecs-01')
        self.assertEqual(ci.attributes['cpu'], 8)
        self.assertEqual(ci.attributes['warranty_end_date'], '2026-12-31')
        self.assertEqual(ci.attributes['last_seen_at'], '2026-07-15T10:20:30')

        duplicate = self.client.post(
            '/api/cmdb/config-items/',
            {
                'name': 'validation-ecs-02',
                'ci_type': ci_type.id,
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'ops',
                'status': 'active',
                'attributes': {
                    'cpu': '8',
                    'warranty_end_date': '2026-12-31',
                    'last_seen_at': '2026-07-15T11:20:30',
                    'asset_code': 'srv002',
                },
            },
            content_type='application/json',
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn('cpu', json.dumps(duplicate.json(), ensure_ascii=False))

        invalid = self.client.post(
            '/api/cmdb/config-items/',
            {
                'name': 'validation-ecs-03',
                'ci_type': ci_type.id,
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'ops',
                'status': 'active',
                'attributes': {
                    'cpu': 128,
                    'warranty_end_date': '2025-12-31',
                    'last_seen_at': 'not-a-datetime',
                    'asset_code': 'ab',
                },
            },
            content_type='application/json',
        )
        invalid_payload = json.dumps(invalid.json(), ensure_ascii=False)
        self.assertEqual(invalid.status_code, 400)
        self.assertIn('cpu', invalid_payload)
        self.assertIn('warranty_end_date', invalid_payload)
        self.assertIn('last_seen_at', invalid_payload)
        self.assertIn('asset_code', invalid_payload)

        invalid_update = self.client.patch(
            f'/api/cmdb/config-items/{ci.id}/',
            {'attributes': {'last_seen_at': 'bad-datetime'}},
            content_type='application/json',
        )
        self.assertEqual(invalid_update.status_code, 400)
        self.assertIn('last_seen_at', json.dumps(invalid_update.json(), ensure_ascii=False))

    def test_sync_job_records_validation_error_for_invalid_dynamic_field_value(self):
        ci_type = CIType.objects.create(name='同步校验云主机', code='SYNC_VALIDATION_CLOUD_SERVER')
        CIField.objects.create(
            ci_type=ci_type,
            name='实例 ID',
            code='instance_id',
            field_type='string',
            required=True,
            unique=True,
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='CPU',
            code='cpu',
            field_type='integer',
            validation={'min': 1, 'max': 64},
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='维保到期日',
            code='warranty_end_date',
            field_type='date',
        )
        job = CISyncJob.objects.create(
            name='动态字段校验同步',
            source_type='csv_import',
            config={
                'items': [{
                    'ci_type_name': '同步校验云主机',
                    'ci_type_code': 'SYNC_VALIDATION_CLOUD_SERVER',
                    'name': 'sync-validation-ecs-01',
                    'source_type': 'csv_import',
                    'source_unique_id': 'sync-validation-001',
                    'business_line': 'core',
                    'environment': 'prod',
                    'admin_user': 'ops',
                    'attributes': {
                        'instance_id': 'sync-validation-001',
                        'cpu': 128,
                        'warranty_end_date': 'bad-date',
                    },
                }],
            },
        )

        dry_run = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/dry-run/', {}, content_type='application/json')
        self.assertEqual(dry_run.status_code, 200, dry_run.content)
        dry_payload = dry_run.json()
        self.assertEqual(dry_payload['summary']['fail'], 1)
        self.assertEqual(len(dry_payload['records']), 1)
        self.assertEqual(dry_payload['records'][0]['action'], 'fail')
        self.assertIn('cpu', json.dumps(dry_payload['records'][0], ensure_ascii=False))
        self.assertFalse(ConfigItem.objects.filter(name='sync-validation-ecs-01').exists())

        response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['summary']['fail'], 1)
        self.assertFalse(ConfigItem.objects.filter(name='sync-validation-ecs-01').exists())
        record = CISyncRecord.objects.get(job=job)
        self.assertEqual(record.action, 'fail')
        self.assertEqual(record.status, 'failed')
        self.assertIn('cpu', record.error_message)
        self.assertIn('warranty_end_date', record.error_message)

    def test_config_item_update_creates_change_log_with_diff(self):
        ci_type = _ci_type('审计云主机', code='AUDIT_CLOUD_SERVER')
        ci = ConfigItem.objects.create(
            name='audit-ecs-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'private_ip': '10.0.0.8', 'cpu': 2},
        )

        response = self.client.put(
            f'/api/cmdb/config-items/{ci.id}/',
            {
                'name': 'audit-ecs-01',
                'ci_type': ci_type.id,
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'platform',
                'status': 'active',
                'attributes': {'private_ip': '10.0.0.8', 'cpu': 4},
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        change_log = CIChangeLog.objects.filter(ci=ci, action='update').latest('id')
        self.assertEqual(change_log.operator, self.user.username)
        self.assertIn('admin_user', change_log.diff)
        self.assertIn('attributes', change_log.diff)
        self.assertEqual(change_log.after['admin_user'], 'platform')
        self.assertEqual(change_log.after['attributes']['cpu'], 4)

        log_response = self.client.get('/api/cmdb/change-logs/', {'ci': ci.id, 'action': 'update'})
        self.assertEqual(log_response.status_code, 200)
        log_row = log_response.json()['results'][0]
        self.assertEqual(log_row['diff_count'], 2)
        self.assertIn('负责人：ops -> platform', log_row['diff_preview'])
        diff_fields = {item['field']: item for item in log_row['diff_fields']}
        self.assertEqual(diff_fields['admin_user']['label'], '负责人')
        self.assertEqual(diff_fields['attributes.cpu']['before'], 2)
        self.assertEqual(diff_fields['attributes.cpu']['after'], 4)

    def test_change_log_summary_supports_time_range_and_filters(self):
        ci_type = _ci_type('审计汇总云主机', code='AUDIT_SUMMARY_SERVER')
        ci = ConfigItem.objects.create(name='audit-summary-ecs-01', ci_type=ci_type, status='active')
        old_log = CIChangeLog.objects.create(
            ci=ci,
            action='create',
            after={'name': ci.name},
            operator='old-ops',
            source='manual',
        )
        recent_log = CIChangeLog.objects.create(
            ci=ci,
            action='update',
            before={'admin_user': 'ops'},
            after={'admin_user': 'platform'},
            diff={'admin_user': {'before': 'ops', 'after': 'platform'}},
            operator='platform',
            source='manual',
        )
        CIChangeLog.objects.filter(id=old_log.id).update(created_at=timezone.now() - timezone.timedelta(days=10))
        CIChangeLog.objects.filter(id=recent_log.id).update(created_at=timezone.now())

        start = (timezone.now() - timezone.timedelta(days=1)).date().isoformat()
        response = self.client.get('/api/cmdb/change-logs/summary/', {'start': start, 'action': 'update'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['total'], 1)
        self.assertEqual(payload['action_counts'][0]['action'], 'update')
        self.assertEqual(payload['operator_counts'][0]['operator'], 'platform')

        response = self.client.get('/api/cmdb/change-logs/', {'start': start, 'action': 'update'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['ci_name'], 'audit-summary-ecs-01')

    def test_config_item_delete_requires_impact_confirmation(self):
        ci_type = _ci_type('删除保护云主机', code='DELETE_GUARD_SERVER')
        ci = ConfigItem.objects.create(
            name='delete-guard-ecs-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'private_ip': '10.8.1.10'},
        )
        related = ConfigItem.objects.create(
            name='delete-guard-app-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
        )
        CIRelation.objects.create(source=related, target=ci, relation_type='depends_on')
        CISourceMapping.objects.create(
            ci=ci,
            source_type='aliyun_ecs',
            source_account='prod',
            source_region='cn-shanghai',
            source_unique_id='i-delete-guard',
        )
        CICompletionIssue.objects.create(ci=ci, missing_fields=[{'code': 'owner', 'name': '负责人'}])
        CIArchiveCandidate.objects.create(ci=ci, source_type='aliyun_ecs', reason='source missing')
        CostRecord.objects.create(ci=ci, month=timezone.now().strftime('%Y-%m'), amount=Decimal('88.00'), provider='aliyun')
        job = CISyncJob.objects.create(name='删除保护同步', source_type='aliyun_ecs')
        CISyncRecord.objects.create(job=job, ci=ci, action='update', status='success', source_unique_id='i-delete-guard')

        impact_response = self.client.get(f'/api/cmdb/config-items/{ci.id}/impact/')
        self.assertEqual(impact_response.status_code, 200)
        impact = impact_response.json()
        self.assertEqual(impact['blocking_counts']['relations'], 1)
        self.assertEqual(impact['blocking_counts']['source_mappings'], 1)
        self.assertEqual(impact['blocking_counts']['open_completion_issues'], 1)
        self.assertEqual(impact['blocking_counts']['pending_archive_candidates'], 1)
        self.assertEqual(impact['blocking_counts']['cost_records'], 1)
        self.assertEqual(impact['warning_counts']['sync_records'], 1)
        self.assertFalse(impact['can_delete_without_force'])

        blocked_response = self.client.delete(f'/api/cmdb/config-items/{ci.id}/')
        self.assertEqual(blocked_response.status_code, 400)
        self.assertIn('impact', blocked_response.json())
        self.assertTrue(ConfigItem.objects.filter(id=ci.id).exists())

        force_response = self.client.delete(f'/api/cmdb/config-items/{ci.id}/?force=true')
        self.assertEqual(force_response.status_code, 204)
        self.assertFalse(ConfigItem.objects.filter(id=ci.id).exists())
        self.assertFalse(CIRelation.objects.filter(target_id=ci.id).exists())
        self.assertFalse(CISourceMapping.objects.filter(source_unique_id='i-delete-guard').exists())
        delete_log = CIChangeLog.objects.filter(action='delete').latest('id')
        self.assertIsNone(delete_log.ci)
        self.assertEqual(delete_log.before['name'], 'delete-guard-ecs-01')

    def test_config_item_impact_returns_upstream_and_downstream_scope(self):
        app_type = _ci_type('影响面应用', code='IMPACT_APP')
        service_type = _ci_type('影响面服务', code='IMPACT_SERVICE')
        db_type = _ci_type('影响面数据库', code='IMPACT_DB')
        storage_type = _ci_type('影响面存储', code='IMPACT_STORAGE')
        gateway = ConfigItem.objects.create(name='impact-gateway', ci_type=service_type, business_line='core', environment='prod')
        client = ConfigItem.objects.create(name='impact-client', ci_type=service_type, business_line='core', environment='prod')
        app = ConfigItem.objects.create(name='impact-app', ci_type=app_type, business_line='core', environment='prod')
        db = ConfigItem.objects.create(name='impact-db', ci_type=db_type, business_line='core', environment='prod')
        storage = ConfigItem.objects.create(name='impact-storage', ci_type=storage_type, business_line='core', environment='prod')
        CIRelation.objects.create(source=gateway, target=client, relation_type='connects_to')
        CIRelation.objects.create(source=client, target=app, relation_type='depends_on')
        CIRelation.objects.create(source=app, target=db, relation_type='depends_on')
        CIRelation.objects.create(source=db, target=storage, relation_type='connects_to')

        response = self.client.get(f'/api/cmdb/config-items/{app.id}/impact/', {'max_depth': 2})

        self.assertEqual(response.status_code, 200, response.content)
        impact = response.json()
        self.assertEqual(impact['max_depth'], 2)
        self.assertEqual(impact['impact_summary']['upstream_count'], 2)
        self.assertEqual(impact['impact_summary']['downstream_count'], 2)
        self.assertEqual(impact['impact_summary']['total_related_count'], 4)
        self.assertEqual(impact['impact_summary']['depth_counts']['1'], 2)
        self.assertEqual(impact['impact_summary']['depth_counts']['2'], 2)
        self.assertEqual(impact['impact_summary']['relation_type_counts']['depends_on'], 2)
        self.assertEqual(impact['impact_summary']['relation_type_counts']['connects_to'], 2)
        upstream_names = {item['name']: item['depth'] for item in impact['upstream']}
        downstream_names = {item['name']: item['depth'] for item in impact['downstream']}
        self.assertEqual(upstream_names['impact-client'], 1)
        self.assertEqual(upstream_names['impact-gateway'], 2)
        self.assertEqual(downstream_names['impact-db'], 1)
        self.assertEqual(downstream_names['impact-storage'], 2)

    def test_sync_job_upserts_resources_and_creates_governance_records(self):
        job = CISyncJob.objects.create(
            name='阿里云 ECS 同步',
            source_type='aliyun_ecs',
            config={
                'items': [
                    {
                        'ci_type_name': '云主机(ECS)',
                        'ci_type_code': 'CLOUD_SERVER',
                        'name': 'ecs-sync-01',
                        'source_type': 'aliyun_ecs',
                        'source_account': 'prod-account',
                        'source_region': 'cn-hangzhou',
                        'source_unique_id': 'i-sync-001',
                        'environment': 'prod',
                        'attributes': {
                            'instance_id': 'i-sync-001',
                            'private_ip': '10.1.1.8',
                            'cpu': 4,
                        },
                    }
                ]
            },
        )

        dry_run = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/dry-run/', {}, content_type='application/json')
        self.assertEqual(dry_run.status_code, 200)
        self.assertEqual(dry_run.json()['summary']['create'], 1)
        self.assertEqual(ConfigItem.objects.filter(name='ecs-sync-01').count(), 0)

        run_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')
        self.assertEqual(run_response.status_code, 200)
        payload = run_response.json()
        self.assertEqual(payload['summary']['create'], 1)

        ci = ConfigItem.objects.get(name='ecs-sync-01')
        self.assertEqual(ci.attributes['source_unique_id'], 'i-sync-001')
        self.assertEqual(CISourceMapping.objects.filter(ci=ci, source_unique_id='i-sync-001').count(), 1)
        self.assertEqual(CISyncRecord.objects.filter(job=job, action='create').count(), 1)
        first_batch_id = CISyncRecord.objects.get(job=job, action='create').batch_id
        self.assertTrue(first_batch_id)
        self.assertTrue(CICompletionIssue.objects.filter(ci=ci, status='open').exists())

        update_response = self.client.post(
            f'/api/cmdb/sync-jobs/{job.id}/run/',
            {
                'items': [
                    {
                        'ci_type_name': '云主机(ECS)',
                        'ci_type_code': 'CLOUD_SERVER',
                        'name': 'ecs-sync-01-renamed',
                        'source_type': 'aliyun_ecs',
                        'source_account': 'prod-account',
                        'source_region': 'cn-hangzhou',
                        'source_unique_id': 'i-sync-001',
                        'business_line': 'core',
                        'admin_user': 'ops-owner',
                        'environment': 'prod',
                        'attributes': {
                            'instance_id': 'i-sync-001',
                            'private_ip': '10.1.1.9',
                            'department': '基础架构部',
                        },
                    }
                ]
            },
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200)
        ci.refresh_from_db()
        self.assertEqual(ci.name, 'ecs-sync-01-renamed')
        self.assertEqual(ci.admin_user, 'ops-owner')
        batch_ids = set(CISyncRecord.objects.filter(job=job).values_list('batch_id', flat=True))
        self.assertEqual(len(batch_ids), 2)
        self.assertNotIn('', batch_ids)
        self.assertTrue(CICompletionIssue.objects.filter(ci=ci, status='resolved').exists())

    def test_sync_job_preserves_duplicate_cloud_resource_names_by_source_id(self):
        ci_type = _ci_type('同名云主机', code='DUPLICATE_NAME_CLOUD_SERVER')
        base_name = 'worker-k8s-for-cs-c358e0dadd8e14c08b1bc7f87a088115c'
        source_ids = ['i-bp108woxfzl1rlc35zzy', 'i-bp10ems7ngjxttf2m529', 'i-bp10thirdsame000001']
        job = CISyncJob.objects.create(
            name='同名 ECS 同步',
            source_type='aliyun_ecs',
            config={
                'items': [
                    {
                        'ci_type_name': '同名云主机',
                        'ci_type_code': 'DUPLICATE_NAME_CLOUD_SERVER',
                        'name': base_name,
                        'source_type': 'aliyun_ecs',
                        'source_account': 'prod-account',
                        'source_region': 'cn-hangzhou',
                        'source_unique_id': source_id,
                        'business_line': 'core',
                        'environment': 'prod',
                        'attributes': {'instance_id': source_id},
                    }
                    for source_id in source_ids
                ],
            },
        )

        dry_run = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/dry-run/', {}, content_type='application/json')
        self.assertEqual(dry_run.status_code, 200, dry_run.content)
        dry_payload = dry_run.json()
        self.assertEqual(dry_payload['summary']['create'], 3)
        self.assertEqual(dry_payload['summary'].get('conflict', 0), 0)
        self.assertEqual(
            [row['after']['name'] for row in dry_payload['records']],
            [base_name, base_name, base_name],
        )

        run_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')
        self.assertEqual(run_response.status_code, 200, run_response.content)
        self.assertEqual(run_response.json()['summary']['create'], 3)
        items = ConfigItem.objects.filter(ci_type=ci_type, name=base_name)
        self.assertEqual(items.count(), 3)
        for source_id in source_ids:
            mapping = CISourceMapping.objects.get(source_type='aliyun_ecs', source_unique_id=source_id)
            self.assertEqual(mapping.ci.name, base_name)

        rerun_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')
        self.assertEqual(rerun_response.status_code, 200, rerun_response.content)
        self.assertEqual(ConfigItem.objects.filter(ci_type=ci_type, name=base_name).count(), 3)

    def test_public_cloud_sync_restores_previously_suffixed_display_name(self):
        ci_type = _ci_type('历史同名云主机', code='LEGACY_DUPLICATE_NAME_CLOUD_SERVER')
        config_item = ConfigItem.objects.create(
            name='shared-cloud-resource-2',
            ci_type=ci_type,
            attributes={'instance_id': 'i-legacy-suffix-001'},
        )
        CISourceMapping.objects.create(
            ci=config_item,
            source_type='aliyun_ecs',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='i-legacy-suffix-001',
        )
        job = CISyncJob.objects.create(
            name='历史同名 ECS 同步',
            source_type='aliyun_ecs',
            config={
                'items': [{
                    'ci_type_name': '历史同名云主机',
                    'ci_type_code': 'LEGACY_DUPLICATE_NAME_CLOUD_SERVER',
                    'name': 'shared-cloud-resource',
                    'source_type': 'aliyun_ecs',
                    'source_account': 'prod-account',
                    'source_region': 'cn-hangzhou',
                    'source_unique_id': 'i-legacy-suffix-001',
                    'attributes': {'instance_id': 'i-legacy-suffix-001'},
                }],
            },
        )

        response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        config_item.refresh_from_db()
        self.assertEqual(config_item.name, 'shared-cloud-resource')
        self.assertEqual(ConfigItem.objects.filter(ci_type=ci_type).count(), 1)

    def test_sync_job_run_records_provider_permission_failure(self):
        from unittest.mock import patch
        from multicloud.models import CloudCredential

        credential = CloudCredential.objects.create(
            provider='aliyun',
            name='阿里云-权限不足账号',
            account_id='100001',
            account_name='prod-account',
            auth_mode='aksk',
            access_key_id='ak',
            access_key_secret='sk',
            default_region='cn-hangzhou',
            is_enabled=True,
        )

        job = CISyncJob.objects.create(
            name='阿里云 RDS 自动注册',
            source_type='aliyun_rds',
            config={
                'connector': 'aliyun',
                'resource_type': 'rds',
                'target_ci_type_code': 'MYSQL',
                'collection_enabled': True,
                'cloud_account_id': credential.id,
            },
        )

        error = RuntimeError(
            'HTTP Status: 403 Error:Forbidden User not authorized to operate on the specified resource, '
            'or this API does not support RAM.'
        )
        with patch('cmdb.collectors._fetch_aliyun_raw_items', side_effect=error):
            response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['summary']['fail'], 1)
        self.assertIn('云账号缺少该同步任务所需的云产品/API 权限', payload['error_message'])
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertIn('云账号缺少该同步任务所需的云产品/API 权限', job.error_message)
        record = CISyncRecord.objects.get(job=job)
        self.assertEqual(record.action, 'fail')
        self.assertEqual(record.status, 'failed')
        self.assertEqual(record.source_unique_id, 'collection')
        self.assertIn('云账号缺少该同步任务所需的云产品/API 权限', record.error_message)

    def test_sync_job_creates_relations_from_relation_hints(self):
        app_type = _ci_type('同步应用', code='SYNC_APP')
        host_type = _ci_type('同步云主机', code='SYNC_CLOUD_SERVER')
        CIRelationRule.objects.create(
            source_type=app_type,
            target_type=host_type,
            relation_type='runs_on',
            required=True,
            multiple=True,
            is_active=True,
        )
        job = CISyncJob.objects.create(
            name='应用主机关系同步',
            source_type='mixed_cmdb',
            config={
                'items': [
                    {
                        'ci_type_name': '同步云主机',
                        'ci_type_code': 'SYNC_CLOUD_SERVER',
                        'name': 'sync-order-ecs-01',
                        'source_type': 'aliyun_ecs',
                        'source_unique_id': 'i-sync-relation-001',
                        'business_line': 'core',
                        'environment': 'prod',
                        'admin_user': 'ops-owner',
                        'attributes': {'department': '交易平台', 'instance_id': 'i-sync-relation-001'},
                        'relations': [
                            {
                                'direction': 'incoming',
                                'relation_type': 'runs_on',
                                'source': {
                                    'source_type': 'cmdb_app',
                                    'source_unique_id': 'app-sync-001',
                                },
                                'confidence': 90,
                                'description': '应用部署信息来自云标签',
                            }
                        ],
                    },
                    {
                        'ci_type_name': '同步应用',
                        'ci_type_code': 'SYNC_APP',
                        'name': 'sync-order-app',
                        'source_type': 'cmdb_app',
                        'source_unique_id': 'app-sync-001',
                        'business_line': 'core',
                        'environment': 'prod',
                        'admin_user': 'app-owner',
                        'attributes': {'department': '交易平台'},
                    },
                ]
            },
        )

        response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['summary']['create'], 2)
        self.assertEqual(payload['summary']['relation_created'], 1)
        self.assertEqual(payload['summary'].get('relation_failed', 0), 0)
        app = ConfigItem.objects.get(name='sync-order-app')
        host = ConfigItem.objects.get(name='sync-order-ecs-01')
        relation = CIRelation.objects.get(source=app, target=host, relation_type='runs_on')
        self.assertEqual(relation.evidence_source, 'sync')
        self.assertEqual(relation.confidence, 90)
        self.assertEqual(relation.evidence['matched_by'], 'source_mapping')
        self.assertEqual(relation.evidence['source_unique_id'], 'i-sync-relation-001')
        host_record = CISyncRecord.objects.get(job=job, ci=host)
        self.assertEqual(host_record.after['_sync_relations']['created'], 1)
        self.assertEqual(host_record.after['_sync_relations']['failed'], 0)
        self.assertEqual(host_record.after['_sync_relations']['relations'][0]['id'], relation.id)
        self.assertTrue(CIChangeLog.objects.filter(ci=app, action='relation_create', source='relation').exists())

        island_response = self.client.get('/api/cmdb/island-analysis/')
        self.assertEqual(island_response.status_code, 200, island_response.content)
        app_required_issues = [
            item for item in island_response.json()['results']
            if item['ci_id'] == app.id and item['issue_type'] == 'missing_required_relation'
        ]
        self.assertEqual(app_required_issues, [])

        repeat_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')
        self.assertEqual(repeat_response.status_code, 200, repeat_response.content)
        self.assertEqual(repeat_response.json()['summary']['relation_skipped'], 1)
        self.assertEqual(CIRelation.objects.filter(source=app, target=host, relation_type='runs_on').count(), 1)

    def test_sync_relation_hints_match_peer_by_ip_and_tags(self):
        app_type = _ci_type('线索匹配应用', code='SYNC_HINT_APP')
        host_type = _ci_type('线索匹配云主机', code='SYNC_HINT_HOST')
        CIRelationRule.objects.create(
            source_type=app_type,
            target_type=host_type,
            relation_type='runs_on',
            multiple=True,
            is_active=True,
        )
        tag = CITag.objects.create(name='order-service', category='service')
        tagged_app = ConfigItem.objects.create(
            name='hint-existing-app',
            ci_type=app_type,
            business_line='core',
            environment='prod',
            admin_user='app-owner',
            status='active',
        )
        tagged_app.tags.add(tag)
        existing_host = ConfigItem.objects.create(
            name='hint-existing-host',
            ci_type=host_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'private_ip': '10.71.1.8', 'instance_id': 'i-existing-hint-host'},
        )
        job = CISyncJob.objects.create(
            name='关系线索匹配同步',
            source_type='mixed_cmdb',
            config={
                'items': [
                    {
                        'ci_type_name': '线索匹配云主机',
                        'ci_type_code': 'SYNC_HINT_HOST',
                        'name': 'hint-new-host',
                        'source_type': 'aliyun_ecs',
                        'source_unique_id': 'i-hint-new-host',
                        'business_line': 'core',
                        'environment': 'prod',
                        'admin_user': 'ops',
                        'attributes': {'private_ip': '10.71.1.9', 'instance_id': 'i-hint-new-host'},
                        'relations': [
                            {
                                'direction': 'incoming',
                                'relation_type': 'runs_on',
                                'source': {
                                    'ci_type_code': 'SYNC_HINT_APP',
                                    'business_line': 'core',
                                    'environment': 'prod',
                                    'tags': [{'name': 'order-service', 'category': 'service'}],
                                },
                                'confidence': 82,
                            }
                        ],
                    },
                    {
                        'ci_type_name': '线索匹配应用',
                        'ci_type_code': 'SYNC_HINT_APP',
                        'name': 'hint-new-app',
                        'source_type': 'cmdb_app',
                        'source_unique_id': 'app-hint-new',
                        'business_line': 'core',
                        'environment': 'prod',
                        'admin_user': 'app-owner',
                        'relations': [
                            {
                                'direction': 'outgoing',
                                'relation_type': 'runs_on',
                                'target': {
                                    'ci_type_code': 'SYNC_HINT_HOST',
                                    'business_line': 'core',
                                    'environment': 'prod',
                                    'private_ip': '10.71.1.8',
                                },
                                'confidence': 86,
                            }
                        ],
                    },
                ]
            },
        )

        dry_run = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/dry-run/', {}, content_type='application/json')
        self.assertEqual(dry_run.status_code, 200, dry_run.content)
        self.assertEqual(dry_run.json()['summary']['relation_preview'], 2)
        dry_matches = {
            item['matched_by']
            for record in dry_run.json()['records']
            for item in (record.get('after', {}).get('_sync_relations', {}).get('relations') or [])
        }
        self.assertTrue({'tags', 'ip'}.issubset(dry_matches))

        response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['summary']['relation_created'], 2)
        new_host = ConfigItem.objects.get(name='hint-new-host')
        new_app = ConfigItem.objects.get(name='hint-new-app')
        tag_relation = CIRelation.objects.get(source=tagged_app, target=new_host, relation_type='runs_on')
        ip_relation = CIRelation.objects.get(source=new_app, target=existing_host, relation_type='runs_on')
        self.assertEqual(tag_relation.evidence['matched_by'], 'tags')
        self.assertEqual(tag_relation.confidence, 82)
        self.assertEqual(ip_relation.evidence['matched_by'], 'ip')
        self.assertEqual(ip_relation.confidence, 86)

    def test_sync_records_expose_relation_issue_governance_rows(self):
        host_type = _ci_type('关系失败云主机', code='SYNC_RELATION_FAIL_HOST')
        job = CISyncJob.objects.create(
            name='关系失败治理同步',
            source_type='aliyun_ecs',
            config={
                'items': [{
                    'ci_type_name': '关系失败云主机',
                    'ci_type_code': 'SYNC_RELATION_FAIL_HOST',
                    'name': 'relation-fail-host-01',
                    'source_type': 'aliyun_ecs',
                    'source_unique_id': 'i-relation-fail-001',
                    'business_line': 'core',
                    'environment': 'prod',
                    'admin_user': 'ops',
                    'attributes': {'instance_id': 'i-relation-fail-001', 'private_ip': '10.72.1.8'},
                    'relations': [{
                        'direction': 'incoming',
                        'relation_type': 'runs_on',
                        'source': {
                            'ci_type_code': 'MISSING_APP',
                            'source_type': 'cmdb_app',
                            'source_unique_id': 'missing-app-001',
                        },
                    }],
                }]
            },
        )

        response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['summary']['create'], 1)
        self.assertEqual(payload['summary']['relation_failed'], 1)
        self.assertEqual(CIRelation.objects.count(), 0)
        record = CISyncRecord.objects.get(job=job, source_unique_id='i-relation-fail-001')
        self.assertEqual(record.status, 'success')
        self.assertEqual(record.after['_sync_relations']['failed'], 1)

        issue_response = self.client.get('/api/cmdb/sync-records/', {'relation_issue': 1, 'page_size': 20})

        self.assertEqual(issue_response.status_code, 200, issue_response.content)
        rows = issue_response.json()['results']
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertTrue(row['relation_issue'])
        self.assertEqual(row['relation_issue_count'], 1)
        self.assertEqual(row['relation_issue_summary']['peer_not_found'], 1)
        self.assertEqual(row['relation_issue_summary']['errors'][0]['reason'], 'peer_not_found')
        self.assertEqual(row['due_days'], 1)

    def test_dashboard_counts_relation_issues_as_sync_governance_risks(self):
        host_type = _ci_type('关系风险统计云主机', code='SYNC_RELATION_DASH_HOST')
        host = ConfigItem.objects.create(
            name='relation-dashboard-host',
            ci_type=host_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'department': 'sre', 'source_unique_id': 'i-relation-dashboard-host'},
        )
        job = CISyncJob.objects.create(name='关系风险统计同步', source_type='aliyun_ecs')
        record = CISyncRecord.objects.create(
            job=job,
            ci=host,
            action='update',
            status='success',
            source_unique_id='i-relation-dashboard-host',
            after={
                'name': host.name,
                '_sync_relations': {
                    'total': 1,
                    'created': 0,
                    'skipped': 0,
                    'failed': 1,
                    'errors': [{'index': 1, 'reason': 'peer_not_found', 'relation_type': 'runs_on'}],
                },
            },
        )
        record.created_at = timezone.now() - timezone.timedelta(days=2)
        record.save(update_fields=['created_at'])

        dashboard_response = self.client.get('/api/cmdb/dashboard/stats/')

        self.assertEqual(dashboard_response.status_code, 200, dashboard_response.content)
        payload = dashboard_response.json()
        self.assertEqual(payload['risk_summary']['sync_failures'], 1)
        self.assertEqual(payload['data_quality']['issue_counts']['sync_failures'], 1)
        self.assertEqual(payload['data_quality']['governance_workload']['sync_total'], 1)
        self.assertEqual(payload['data_quality']['governance_workload']['sync_overdue'], 1)
        self.assertTrue(any(item['title'] == '自动关系失败' for item in payload['data_quality']['governance_workload']['top_overdue_tasks']))

        repository_response = self.client.get('/api/cmdb/repository/summary/')
        self.assertEqual(repository_response.status_code, 200, repository_response.content)
        model_rows = [
            model
            for group in repository_response.json()['groups']
            for model in group['models']
            if model['id'] == host_type.id
        ]
        self.assertEqual(model_rows[0]['sync_failure_count'], 1)
        self.assertEqual(model_rows[0]['risk_count'], 1)

    def test_sync_relation_issue_candidates_can_be_resolved_manually(self):
        app_type = _ci_type('关系治理应用', code='SYNC_RELATION_GOV_APP')
        host_type = _ci_type('关系治理云主机', code='SYNC_RELATION_GOV_HOST')
        CIRelationRule.objects.create(
            source_type=app_type,
            target_type=host_type,
            relation_type='runs_on',
            multiple=True,
            is_active=True,
        )
        app = ConfigItem.objects.create(
            name='relation-governance-app',
            ci_type=app_type,
            business_line='core',
            environment='prod',
            admin_user='app-owner',
            status='active',
            attributes={'source_unique_id': 'missing-relation-governance-app'},
        )
        ConfigItem.objects.create(
            name='relation-governance-app-distractor',
            ci_type=app_type,
            business_line='core',
            environment='prod',
            admin_user='app-owner',
            status='active',
        )
        job = CISyncJob.objects.create(
            name='关系候选治理同步',
            source_type='aliyun_ecs',
            config={
                'items': [{
                    'ci_type_name': '关系治理云主机',
                    'ci_type_code': 'SYNC_RELATION_GOV_HOST',
                    'name': 'relation-governance-host',
                    'source_type': 'aliyun_ecs',
                    'source_unique_id': 'i-relation-gov-host',
                    'business_line': 'core',
                    'environment': 'prod',
                    'admin_user': 'ops',
                    'attributes': {'private_ip': '10.72.2.8', 'instance_id': 'i-relation-gov-host'},
                    'relations': [{
                        'direction': 'incoming',
                        'relation_type': 'runs_on',
                        'source': {
                            'ci_type_code': 'SYNC_RELATION_GOV_APP',
                            'source_type': 'cmdb_app',
                            'source_unique_id': 'missing-relation-governance-app',
                        },
                    }],
                }]
            },
        )
        run_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')
        self.assertEqual(run_response.status_code, 200, run_response.content)
        self.assertEqual(run_response.json()['summary']['relation_failed'], 1)
        record = CISyncRecord.objects.get(job=job, source_unique_id='i-relation-gov-host')
        host = record.ci
        self.assertEqual(record.after['_sync_relations']['failed'], 1)

        candidate_response = self.client.get(f'/api/cmdb/sync-records/{record.id}/relation-candidates/')

        self.assertEqual(candidate_response.status_code, 200, candidate_response.content)
        issues = candidate_response.json()['issues']
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['direction'], 'incoming')
        self.assertEqual(issues[0]['best_candidate']['id'], app.id)
        self.assertIn('来源ID命中', issues[0]['best_candidate']['reasons'])
        self.assertIn('同业务线', issues[0]['best_candidate']['reasons'])

        resolve_response = self.client.post(
            f'/api/cmdb/sync-records/{record.id}/resolve-relation/',
            {'error_index': issues[0]['index'], 'candidate_id': app.id},
            content_type='application/json',
        )

        self.assertEqual(resolve_response.status_code, 200, resolve_response.content)
        relation = CIRelation.objects.get(source=app, target=host, relation_type='runs_on')
        self.assertEqual(relation.evidence_source, 'governance')
        self.assertEqual(relation.evidence['sync_record_id'], record.id)
        record.refresh_from_db()
        relation_summary = record.after['_sync_relations']
        self.assertEqual(relation_summary['failed'], 0)
        self.assertEqual(relation_summary['created'], 1)
        self.assertEqual(relation_summary['errors'], [])
        self.assertEqual(relation_summary['resolved'][0]['relation_id'], relation.id)
        issue_response = self.client.get('/api/cmdb/sync-records/', {'relation_issue': 1, 'page_size': 20})
        self.assertEqual(issue_response.status_code, 200, issue_response.content)
        self.assertEqual(issue_response.json()['results'], [])
        self.assertTrue(CIChangeLog.objects.filter(ci=app, action='relation_create', source='governance').exists())

    def test_sync_job_retry_failed_resolves_relation_issues_after_peer_arrives(self):
        app_type = _ci_type('关系重试应用', code='SYNC_RELATION_RETRY_APP')
        host_type = _ci_type('关系重试云主机', code='SYNC_RELATION_RETRY_HOST')
        CIRelationRule.objects.create(
            source_type=app_type,
            target_type=host_type,
            relation_type='runs_on',
            multiple=True,
            is_active=True,
        )
        job = CISyncJob.objects.create(
            name='关系失败自动重试同步',
            source_type='aliyun_ecs',
            config={
                'items': [{
                    'ci_type_name': '关系重试云主机',
                    'ci_type_code': 'SYNC_RELATION_RETRY_HOST',
                    'name': 'relation-retry-host',
                    'source_type': 'aliyun_ecs',
                    'source_unique_id': 'i-relation-retry-host',
                    'business_line': 'core',
                    'environment': 'prod',
                    'attributes': {'private_ip': '10.72.6.11', 'instance_id': 'i-relation-retry-host'},
                    'relations': [{
                        'direction': 'incoming',
                        'relation_type': 'runs_on',
                        'source': {
                            'ci_type_code': 'SYNC_RELATION_RETRY_APP',
                            'source_type': 'cmdb_app',
                            'source_unique_id': 'missing-retry-app',
                        },
                    }],
                }]
            },
        )
        run_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')
        self.assertEqual(run_response.status_code, 200, run_response.content)
        self.assertEqual(run_response.json()['summary']['relation_failed'], 1)
        record = CISyncRecord.objects.get(job=job, source_unique_id='i-relation-retry-host')
        host = record.ci
        self.assertEqual(record.status, 'success')
        self.assertEqual(record.after['_sync_relations']['failed'], 1)

        app = ConfigItem.objects.create(
            name='relation-retry-app',
            ci_type=app_type,
            business_line='core',
            environment='prod',
            status='active',
            attributes={'source_unique_id': 'missing-retry-app'},
        )
        CISourceMapping.objects.create(
            ci=app,
            source_type='cmdb_app',
            source_unique_id='missing-retry-app',
        )

        retry_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/retry-failed/')

        self.assertEqual(retry_response.status_code, 200, retry_response.content)
        payload = retry_response.json()
        self.assertEqual(payload['summary']['relation_created'], 1)
        self.assertEqual(payload['summary']['relation_resolved'], 1)
        relation = CIRelation.objects.get(source=app, target=host, relation_type='runs_on')
        self.assertEqual(relation.evidence_source, 'sync')
        self.assertEqual(relation.evidence['matched_by'], 'source_mapping')
        record.refresh_from_db()
        self.assertEqual(record.after['_sync_relations']['failed'], 0)
        self.assertEqual(record.after['_sync_relations']['created'], 1)
        self.assertEqual(record.retry_status, 'success')
        self.assertEqual(record.retry_count, 1)
        self.assertEqual(record.retry_result, 'relation_create')
        issue_response = self.client.get('/api/cmdb/sync-records/', {'relation_issue': 1, 'page_size': 20})
        self.assertEqual(issue_response.status_code, 200, issue_response.content)
        self.assertEqual(issue_response.json()['results'], [])

    def test_sync_relation_issues_can_be_bulk_resolved_by_best_candidates(self):
        app_type = _ci_type('批量关系治理应用', code='SYNC_RELATION_BULK_APP')
        host_type = _ci_type('批量关系治理云主机', code='SYNC_RELATION_BULK_HOST')
        CIRelationRule.objects.create(
            source_type=app_type,
            target_type=host_type,
            relation_type='runs_on',
            multiple=True,
            is_active=True,
        )
        app = ConfigItem.objects.create(
            name='bulk-relation-governance-app',
            ci_type=app_type,
            business_line='core',
            environment='prod',
            status='active',
            attributes={'source_unique_id': 'bulk-missing-app'},
        )
        job = CISyncJob.objects.create(
            name='批量关系候选治理同步',
            source_type='aliyun_ecs',
            config={
                'items': [
                    {
                        'ci_type_name': '批量关系治理云主机',
                        'ci_type_code': 'SYNC_RELATION_BULK_HOST',
                        'name': 'bulk-relation-host-01',
                        'source_type': 'aliyun_ecs',
                        'source_unique_id': 'i-bulk-relation-01',
                        'business_line': 'core',
                        'environment': 'prod',
                        'attributes': {'private_ip': '10.72.3.11', 'instance_id': 'i-bulk-relation-01'},
                        'relations': [{
                            'direction': 'incoming',
                            'relation_type': 'runs_on',
                            'source': {
                                'ci_type_code': 'SYNC_RELATION_BULK_APP',
                                'source_type': 'cmdb_app',
                                'source_unique_id': 'bulk-missing-app',
                            },
                        }],
                    },
                    {
                        'ci_type_name': '批量关系治理云主机',
                        'ci_type_code': 'SYNC_RELATION_BULK_HOST',
                        'name': 'bulk-relation-host-02',
                        'source_type': 'aliyun_ecs',
                        'source_unique_id': 'i-bulk-relation-02',
                        'business_line': 'core',
                        'environment': 'prod',
                        'attributes': {'private_ip': '10.72.3.12', 'instance_id': 'i-bulk-relation-02'},
                        'relations': [{
                            'direction': 'incoming',
                            'relation_type': 'runs_on',
                            'source': {
                                'ci_type_code': 'SYNC_RELATION_BULK_APP',
                                'source_type': 'cmdb_app',
                                'source_unique_id': 'bulk-missing-app',
                            },
                        }],
                    },
                ]
            },
        )
        run_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')
        self.assertEqual(run_response.status_code, 200, run_response.content)
        self.assertEqual(run_response.json()['summary']['relation_failed'], 2)
        records = list(CISyncRecord.objects.filter(job=job).order_by('id'))
        self.assertEqual(len(records), 2)

        response = self.client.post(
            '/api/cmdb/sync-records/bulk-resolve-relations/',
            {'record_ids': [record.id for record in records]},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        summary = response.json()['summary']
        self.assertEqual(summary['total'], 2)
        self.assertEqual(summary['resolved'], 2)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(CIRelation.objects.filter(source=app, relation_type='runs_on').count(), 2)
        for record in records:
            record.refresh_from_db()
            self.assertEqual(record.after['_sync_relations']['failed'], 0)
            self.assertEqual(record.after['_sync_relations']['created'], 1)
        issue_response = self.client.get('/api/cmdb/sync-records/', {'relation_issue': 1, 'page_size': 20})
        self.assertEqual(issue_response.status_code, 200, issue_response.content)
        self.assertEqual(issue_response.json()['results'], [])

    def test_sync_relation_issue_resolution_closes_when_relation_already_exists(self):
        app_type = _ci_type('已有关系治理应用', code='SYNC_RELATION_EXISTS_APP')
        host_type = _ci_type('已有关系治理云主机', code='SYNC_RELATION_EXISTS_HOST')
        CIRelationRule.objects.create(
            source_type=app_type,
            target_type=host_type,
            relation_type='runs_on',
            multiple=True,
            is_active=True,
        )
        app = ConfigItem.objects.create(
            name='existing-relation-governance-app',
            ci_type=app_type,
            business_line='core',
            environment='prod',
            status='active',
            attributes={'source_unique_id': 'existing-relation-app'},
        )
        job = CISyncJob.objects.create(
            name='已有关系治理同步',
            source_type='aliyun_ecs',
            config={
                'items': [{
                    'ci_type_name': '已有关系治理云主机',
                    'ci_type_code': 'SYNC_RELATION_EXISTS_HOST',
                    'name': 'existing-relation-host',
                    'source_type': 'aliyun_ecs',
                    'source_unique_id': 'i-existing-relation-host',
                    'business_line': 'core',
                    'environment': 'prod',
                    'attributes': {'private_ip': '10.72.4.11', 'instance_id': 'i-existing-relation-host'},
                    'relations': [{
                        'direction': 'incoming',
                        'relation_type': 'runs_on',
                        'source': {
                            'ci_type_code': 'SYNC_RELATION_EXISTS_APP',
                            'source_type': 'cmdb_app',
                            'source_unique_id': 'existing-relation-app',
                        },
                    }],
                }]
            },
        )
        run_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')
        self.assertEqual(run_response.status_code, 200, run_response.content)
        record = CISyncRecord.objects.get(job=job)
        host = record.ci
        relation = CIRelation.objects.create(
            source=app,
            target=host,
            relation_type='runs_on',
            evidence_source='manual',
            confidence=95,
            description='外部人工已补关系',
        )
        candidate_response = self.client.get(f'/api/cmdb/sync-records/{record.id}/relation-candidates/')
        self.assertEqual(candidate_response.status_code, 200, candidate_response.content)
        issue = candidate_response.json()['issues'][0]

        resolve_response = self.client.post(
            f'/api/cmdb/sync-records/{record.id}/resolve-relation/',
            {'error_index': issue['index'], 'candidate_id': app.id},
            content_type='application/json',
        )

        self.assertEqual(resolve_response.status_code, 200, resolve_response.content)
        self.assertEqual(CIRelation.objects.filter(source=app, target=host, relation_type='runs_on').count(), 1)
        record.refresh_from_db()
        relation_summary = record.after['_sync_relations']
        self.assertEqual(relation_summary['failed'], 0)
        self.assertEqual(relation_summary['created'], 0)
        self.assertEqual(relation_summary['skipped'], 1)
        self.assertEqual(relation_summary['relations'][0]['id'], relation.id)
        self.assertEqual(relation_summary['relations'][0]['action'], 'already_exists')
        self.assertEqual(relation_summary['resolved'][0]['action'], 'already_exists')
        issue_response = self.client.get('/api/cmdb/sync-records/', {'relation_issue': 1, 'page_size': 20})
        self.assertEqual(issue_response.status_code, 200, issue_response.content)
        self.assertEqual(issue_response.json()['results'], [])

    def test_sync_job_validates_metadata_before_writing_config_item(self):
        ci_type = _ci_type('元数据校验云主机', code='SYNC_VALIDATE_CLOUD_SERVER')
        CIField.objects.create(
            ci_type=ci_type,
            name='实例 ID',
            code='instance_id',
            field_type='string',
            required=True,
            unique=True,
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='私网 IP',
            code='private_ip',
            field_type='ip',
            required=True,
        )
        job = CISyncJob.objects.create(
            name='元数据校验同步',
            source_type='aliyun_ecs',
            config={
                'items': [{
                    'ci_type_name': '元数据校验云主机',
                    'ci_type_code': 'SYNC_VALIDATE_CLOUD_SERVER',
                    'name': 'invalid-sync-ecs',
                    'source_type': 'aliyun_ecs',
                    'source_unique_id': 'i-invalid-meta-001',
                    'environment': 'prod',
                    'attributes': {
                        'instance_id': 'i-invalid-meta-001',
                        'private_ip': 'not-an-ip',
                    },
                }],
            },
        )

        dry_run = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/dry-run/', {}, content_type='application/json')
        self.assertEqual(dry_run.status_code, 200, dry_run.content)
        self.assertEqual(dry_run.json()['summary']['fail'], 1)
        self.assertIn('private_ip', dry_run.json()['records'][0]['error_message'])
        self.assertFalse(ConfigItem.objects.filter(name='invalid-sync-ecs').exists())

        run_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')
        self.assertEqual(run_response.status_code, 200, run_response.content)
        self.assertEqual(run_response.json()['summary']['fail'], 1)
        self.assertFalse(ConfigItem.objects.filter(name='invalid-sync-ecs').exists())
        record = CISyncRecord.objects.get(job=job, source_unique_id='i-invalid-meta-001')
        self.assertEqual(record.status, 'failed')
        self.assertIn('private_ip', record.error_message)

    def test_sync_job_preserves_manual_attributes_when_source_updates_known_fields(self):
        ci_type = _ci_type('保留人工字段云主机', code='SYNC_PRESERVE_CLOUD_SERVER')
        CIField.objects.create(
            ci_type=ci_type,
            name='实例 ID',
            code='instance_id',
            field_type='string',
            required=True,
            unique=True,
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='私网 IP',
            code='private_ip',
            field_type='ip',
            required=True,
        )
        CIField.objects.create(ci_type=ci_type, name='部门', code='department', field_type='string')
        CIField.objects.create(ci_type=ci_type, name='维保到期日', code='warranty_end_date', field_type='date')
        ci = ConfigItem.objects.create(
            name='preserve-sync-ecs',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={
                'instance_id': 'i-preserve-001',
                'private_ip': '10.5.1.8',
                'department': '基础架构部',
                'warranty_end_date': '2026-12-31',
                'manual_note': '人工维护字段',
            },
        )
        CISourceMapping.objects.create(
            ci=ci,
            source_type='aliyun_ecs',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='i-preserve-001',
        )
        job = CISyncJob.objects.create(
            name='保留人工字段同步',
            source_type='aliyun_ecs',
            config={
                'items': [{
                    'ci_type_name': '保留人工字段云主机',
                    'ci_type_code': 'SYNC_PRESERVE_CLOUD_SERVER',
                    'name': 'preserve-sync-ecs-renamed',
                    'source_type': 'aliyun_ecs',
                    'source_account': 'prod-account',
                    'source_region': 'cn-hangzhou',
                    'source_unique_id': 'i-preserve-001',
                    'business_line': 'core',
                    'environment': 'prod',
                    'admin_user': 'cloud-ops',
                    'attributes': {
                        'instance_id': 'i-preserve-001',
                        'private_ip': '10.5.1.9',
                        'cpu': 8,
                    },
                }],
            },
        )

        response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        ci.refresh_from_db()
        self.assertEqual(ci.name, 'preserve-sync-ecs-renamed')
        self.assertEqual(ci.business_line, 'core')
        self.assertEqual(ci.environment, 'prod')
        self.assertEqual(ci.admin_user, 'ops')
        self.assertEqual(ci.attributes['private_ip'], '10.5.1.9')
        self.assertEqual(ci.attributes['cpu'], 8)
        self.assertEqual(ci.attributes['department'], '基础架构部')
        self.assertEqual(ci.attributes['warranty_end_date'], '2026-12-31')
        self.assertEqual(ci.attributes['manual_note'], '人工维护字段')

    def test_sync_job_respects_field_level_sync_mode(self):
        ci_type = _ci_type('字段同步策略云主机', code='SYNC_MODE_CLOUD_SERVER')
        CIField.objects.create(
            ci_type=ci_type,
            name='实例 ID',
            code='instance_id',
            field_type='string',
            required=True,
            unique=True,
            sync_mode='source',
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='私网 IP',
            code='private_ip',
            field_type='ip',
            required=True,
            sync_mode='source',
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='部门',
            code='department',
            field_type='string',
            sync_mode='manual',
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='负责团队',
            code='owner_team',
            field_type='string',
            sync_mode='manual',
        )
        ci = ConfigItem.objects.create(
            name='sync-mode-ecs',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={
                'instance_id': 'i-sync-mode-001',
                'private_ip': '10.6.1.8',
                'department': '人工部门',
                'owner_team': '',
            },
        )
        CISourceMapping.objects.create(
            ci=ci,
            source_type='aliyun_ecs',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='i-sync-mode-001',
        )
        job = CISyncJob.objects.create(
            name='字段同步策略测试',
            source_type='aliyun_ecs',
            config={
                'items': [{
                    'ci_type_name': '字段同步策略云主机',
                    'ci_type_code': 'SYNC_MODE_CLOUD_SERVER',
                    'name': 'sync-mode-ecs-renamed',
                    'source_type': 'aliyun_ecs',
                    'source_account': 'prod-account',
                    'source_region': 'cn-hangzhou',
                    'source_unique_id': 'i-sync-mode-001',
                    'business_line': 'changed-core',
                    'environment': 'test',
                    'admin_user': 'cloud-ops',
                    'attributes': {
                        'instance_id': 'i-sync-mode-001',
                        'private_ip': '10.6.1.9',
                        'department': '云上部门',
                        'owner_team': '云上团队',
                    },
                }],
            },
        )

        response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        ci.refresh_from_db()
        self.assertEqual(ci.name, 'sync-mode-ecs-renamed')
        self.assertEqual(ci.business_line, 'core')
        self.assertEqual(ci.environment, 'prod')
        self.assertEqual(ci.admin_user, 'ops')
        self.assertEqual(ci.attributes['private_ip'], '10.6.1.9')
        self.assertEqual(ci.attributes['department'], '人工部门')
        self.assertEqual(ci.attributes['owner_team'], '云上团队')

    def test_sync_job_detects_source_identity_conflicts_before_upsert(self):
        ci_type = _ci_type('冲突检测云主机', code='SYNC_CONFLICT_CLOUD_SERVER')
        existing_ci = ConfigItem.objects.create(
            name='conflict-existing-ecs',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'source_unique_id': 'i-existing-001'},
        )
        CISourceMapping.objects.create(
            ci=existing_ci,
            source_type='aliyun_ecs',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='i-existing-001',
        )
        job = CISyncJob.objects.create(
            name='冲突检测同步',
            source_type='aliyun_ecs',
            config={
                'items': [
                    {
                        'ci_type_name': '冲突检测云主机',
                        'ci_type_code': 'SYNC_CONFLICT_CLOUD_SERVER',
                        'name': 'conflict-new-ecs',
                        'source_type': 'aliyun_ecs',
                        'source_account': 'prod-account',
                        'source_region': 'cn-hangzhou',
                        'source_unique_id': 'i-duplicate-001',
                        'business_line': 'core',
                        'environment': 'prod',
                        'admin_user': 'ops',
                    },
                    {
                        'ci_type_name': '冲突检测云主机',
                        'ci_type_code': 'SYNC_CONFLICT_CLOUD_SERVER',
                        'name': 'conflict-new-ecs-copy',
                        'source_type': 'aliyun_ecs',
                        'source_account': 'prod-account',
                        'source_region': 'cn-hangzhou',
                        'source_unique_id': 'i-duplicate-001',
                        'business_line': 'core',
                        'environment': 'prod',
                        'admin_user': 'ops',
                    },
                    {
                        'ci_type_name': '冲突检测云主机',
                        'ci_type_code': 'SYNC_CONFLICT_CLOUD_SERVER',
                        'name': 'conflict-existing-ecs',
                        'source_type': 'aliyun_ecs',
                        'source_account': 'prod-account',
                        'source_region': 'cn-hangzhou',
                        'source_unique_id': 'i-different-001',
                        'business_line': 'core',
                        'environment': 'prod',
                        'admin_user': 'ops',
                    },
                ],
            },
        )

        dry_run = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/dry-run/', {}, content_type='application/json')
        self.assertEqual(dry_run.status_code, 200)
        dry_payload = dry_run.json()
        self.assertEqual(dry_payload['summary']['create'], 2)
        self.assertEqual(dry_payload['summary']['conflict'], 1)
        self.assertTrue(all(row.get('error_message') for row in dry_payload['records'] if row['action'] == 'conflict'))
        self.assertFalse(ConfigItem.objects.filter(name='conflict-new-ecs').exists())

        run_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')
        self.assertEqual(run_response.status_code, 200)
        run_payload = run_response.json()
        self.assertEqual(run_payload['summary']['create'], 2)
        self.assertEqual(run_payload['summary']['conflict'], 1)
        job.refresh_from_db()
        self.assertEqual(job.status, 'partial')
        self.assertEqual(CISyncRecord.objects.filter(job=job, action='conflict', status='failed').count(), 1)
        self.assertEqual(ConfigItem.objects.filter(name='conflict-existing-ecs').count(), 2)
        self.assertFalse(ConfigItem.objects.filter(name='conflict-existing-ecs-2').exists())
        self.assertTrue(CISourceMapping.objects.filter(source_unique_id='i-different-001').exists())
        existing_ci.refresh_from_db()
        self.assertEqual(existing_ci.attributes['source_unique_id'], 'i-existing-001')

    def test_full_sync_creates_archive_candidate_for_missing_source_mapping(self):
        ci_type = _ci_type('全量同步云主机', code='FULL_SYNC_CLOUD_SERVER')
        missing_ci = ConfigItem.objects.create(
            name='ecs-missing-from-source',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'source_unique_id': 'i-full-missing'},
        )
        CISourceMapping.objects.create(
            ci=missing_ci,
            source_type='aliyun_ecs',
            source_account='prod-account',
            source_region='cn-shanghai',
            source_unique_id='i-full-missing',
            last_seen_at=timezone.now() - timezone.timedelta(days=3),
        )
        job = CISyncJob.objects.create(
            name='阿里云 ECS 全量同步',
            source_type='aliyun_ecs',
            config={
                'full_sync': True,
                'items': [
                    {
                        'ci_type_name': '全量同步云主机',
                        'ci_type_code': 'FULL_SYNC_CLOUD_SERVER',
                        'name': 'ecs-current-from-source',
                        'source_type': 'aliyun_ecs',
                        'source_account': 'prod-account',
                        'source_region': 'cn-shanghai',
                        'source_unique_id': 'i-full-current',
                        'business_line': 'core',
                        'environment': 'prod',
                        'admin_user': 'ops',
                        'attributes': {
                            'instance_id': 'i-full-current',
                            'private_ip': '10.7.1.8',
                        },
                    }
                ],
            },
        )

        dry_run = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/dry-run/', {}, content_type='application/json')
        self.assertEqual(dry_run.status_code, 200)
        self.assertEqual(dry_run.json()['summary']['archive_candidate'], 1)
        self.assertFalse(CIArchiveCandidate.objects.filter(ci=missing_ci).exists())

        run_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(run_response.status_code, 200)
        payload = run_response.json()
        self.assertEqual(payload['summary']['archive_candidate'], 1)
        candidate = CIArchiveCandidate.objects.get(ci=missing_ci, status='pending')
        self.assertEqual(candidate.source_type, 'aliyun_ecs')
        self.assertIn('i-full-missing', candidate.reason)
        self.assertTrue(CISyncRecord.objects.filter(job=job, ci=missing_ci, action='archive_candidate', source_unique_id='i-full-missing').exists())
        missing_ci.refresh_from_db()
        self.assertEqual(missing_ci.status, 'active')

    def test_sync_job_creates_archive_candidate_for_stale_source_mapping(self):
        ci_type = _ci_type('陈旧同步云主机', code='STALE_SYNC_CLOUD_SERVER')
        stale_ci = ConfigItem.objects.create(
            name='ecs-stale-source',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'source_unique_id': 'i-stale-001'},
        )
        fresh_ci = ConfigItem.objects.create(
            name='ecs-fresh-source',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'source_unique_id': 'i-fresh-001'},
        )
        other_account_ci = ConfigItem.objects.create(
            name='ecs-other-account-stale-source',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'source_unique_id': 'i-other-stale-001'},
        )
        stale_mapping = CISourceMapping.objects.create(
            ci=stale_ci,
            source_type='aliyun_ecs',
            source_account='prod-account',
            source_region='cn-shanghai',
            source_unique_id='i-stale-001',
            last_seen_at=timezone.now() - timezone.timedelta(days=15),
        )
        CISourceMapping.objects.create(
            ci=fresh_ci,
            source_type='aliyun_ecs',
            source_account='prod-account',
            source_region='cn-shanghai',
            source_unique_id='i-fresh-001',
            last_seen_at=timezone.now() - timezone.timedelta(days=2),
        )
        CISourceMapping.objects.create(
            ci=other_account_ci,
            source_type='aliyun_ecs',
            source_account='other-account',
            source_region='cn-shanghai',
            source_unique_id='i-other-stale-001',
            last_seen_at=timezone.now() - timezone.timedelta(days=20),
        )
        job = CISyncJob.objects.create(
            name='阿里云 ECS 陈旧来源治理',
            source_type='aliyun_ecs',
            config={
                'source_account': 'prod-account',
                'source_region': 'cn-shanghai',
                'stale_missing_after_days': 7,
                'items': [],
            },
        )

        dry_run = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/dry-run/', {}, content_type='application/json')

        self.assertEqual(dry_run.status_code, 200, dry_run.content)
        self.assertEqual(dry_run.json()['summary']['archive_candidate'], 1)
        self.assertEqual(dry_run.json()['records'][0]['source_unique_id'], 'i-stale-001')
        self.assertIn('超过 7 天未同步', dry_run.json()['records'][0]['after']['reason'])
        self.assertFalse(CIArchiveCandidate.objects.filter(ci=stale_ci).exists())

        run_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(run_response.status_code, 200, run_response.content)
        self.assertEqual(run_response.json()['summary']['archive_candidate'], 1)
        candidate = CIArchiveCandidate.objects.get(ci=stale_ci, status='pending')
        self.assertEqual(candidate.source_type, 'aliyun_ecs')
        self.assertIn('超过 7 天未同步', candidate.reason)
        self.assertFalse(CIArchiveCandidate.objects.filter(ci=fresh_ci).exists())
        self.assertFalse(CIArchiveCandidate.objects.filter(ci=other_account_ci).exists())
        stale_mapping.refresh_from_db()
        self.assertEqual(stale_mapping.sync_status, 'missing')
        self.assertTrue(CISyncRecord.objects.filter(job=job, ci=stale_ci, action='archive_candidate', source_unique_id='i-stale-001').exists())
        stale_ci.refresh_from_db()
        self.assertEqual(stale_ci.status, 'active')

    def test_collection_summary_groups_scheduled_jobs_and_source_health(self):
        ci_type = _ci_type('采集云主机', code='COLLECTION_CLOUD_SERVER')
        ci = ConfigItem.objects.create(
            name='ecs-collected-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            attributes={'instance_id': 'i-collected-001'},
        )
        CISourceMapping.objects.create(
            ci=ci,
            source_type='aliyun_ecs',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='i-collected-001',
            last_seen_at=timezone.now() - timezone.timedelta(minutes=90),
        )
        job = CISyncJob.objects.create(
            name='阿里云 ECS 自动采集',
            source_type='aliyun_ecs',
            mode='scheduled',
            status='partial',
            dry_run=True,
            finished_at=timezone.now() - timezone.timedelta(minutes=90),
            config={
                'collection_enabled': True,
                'interval_minutes': 60,
                'schedule_label': '每 60 分钟',
                'items': [{'source_unique_id': 'i-collected-001'}],
            },
        )
        CISyncRecord.objects.create(
            job=job,
            ci=ci,
            action='update',
            source_unique_id='i-collected-001',
            status='success',
        )
        CISyncRecord.objects.create(
            job=job,
            action='fail',
            source_unique_id='i-failed-001',
            status='failed',
            error_message='api throttled',
        )
        CISyncRecord.objects.create(
            job=job,
            ci=ci,
            action='update',
            source_unique_id='i-relation-failed-001',
            status='success',
            after={
                '_sync_relations': {
                    'total': 1,
                    'created': 0,
                    'skipped': 0,
                    'failed': 1,
                    'errors': [{'index': 1, 'reason': 'peer_not_found', 'relation_type': 'runs_on'}],
                },
            },
        )

        response = self.client.get('/api/cmdb/collection/summary/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload['summary']['scheduled_count'], 1)
        self.assertGreaterEqual(payload['summary']['enabled_count'], 1)
        self.assertGreaterEqual(payload['summary']['due_count'], 1)
        self.assertEqual(payload['summary']['failed_count'], 2)
        self.assertGreaterEqual(payload['summary']['unhealthy_count'], 1)
        job_row = next(item for item in payload['jobs'] if item['name'] == '阿里云 ECS 自动采集')
        self.assertEqual(job_row['name'], '阿里云 ECS 自动采集')
        self.assertTrue(job_row['enabled'])
        self.assertTrue(job_row['is_due'])
        self.assertEqual(job_row['health_status'], 'failed')
        self.assertEqual(job_row['resource_count'], 1)
        self.assertEqual(job_row['failed_count'], 2)
        failed_sample_ids = {item['source_unique_id'] for item in job_row['failed_samples']}
        self.assertIn('i-failed-001', failed_sample_ids)
        self.assertIn('i-relation-failed-001', failed_sample_ids)
        relation_sample = next(item for item in job_row['failed_samples'] if item['source_unique_id'] == 'i-relation-failed-001')
        self.assertTrue(relation_sample['relation_issue'])
        self.assertEqual(relation_sample['relation_issue_count'], 1)
        self.assertIn('自动关系失败', relation_sample['error_message'])
        self.assertIn(job_row['last_error_message'], {'api throttled', relation_sample['error_message']})
        source = payload['sources'][0]
        self.assertEqual(source['source_type'], 'aliyun_ecs')
        self.assertEqual(source['resource_count'], 1)
        self.assertEqual(source['health_status'], 'failed')
        self.assertEqual(source['due_count'], 1)
        self.assertEqual(source['failed_count'], 2)
        self.assertEqual(source['failed_samples'][0]['job_name'], '阿里云 ECS 自动采集')

    def test_aliyun_ecs_collector_normalizes_raw_items_for_sync(self):
        job = CISyncJob.objects.create(
            name='阿里云 ECS 原始采集',
            source_type='aliyun_ecs',
            mode='scheduled',
            config={
                'connector': 'aliyun',
                'resource_type': 'ecs',
                'target_ci_type_code': 'CLOUD_SERVER',
                'source_account': 'prod-account',
                'raw_items': [
                    {
                        'InstanceId': 'i-raw-ecs-001',
                        'InstanceName': 'prod-app-ecs-01',
                        'RegionId': 'cn-hangzhou',
                        'ZoneId': 'cn-hangzhou-h',
                        'Status': 'Running',
                        'InstanceType': 'ecs.g7.large',
                        'Cpu': 4,
                        'Memory': 8192,
                        'VpcAttributes': {
                            'VpcId': 'vpc-001',
                            'VSwitchId': 'vsw-001',
                            'PrivateIpAddress': {'IpAddress': ['10.9.1.8']},
                        },
                        'PublicIpAddress': {'IpAddress': ['47.9.1.8']},
                        'Tags': {
                            'Tag': [
                                {'Key': 'business_line', 'Value': 'core'},
                                {'Key': 'department', 'Value': '基础架构部'},
                                {'Key': 'environment', 'Value': 'prod'},
                                {'Key': 'owner', 'Value': 'sre-core'},
                            ]
                        },
                    }
                ],
            },
        )

        dry_run = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/dry-run/', {}, content_type='application/json')
        self.assertEqual(dry_run.status_code, 200, dry_run.content)
        self.assertEqual(dry_run.json()['summary']['create'], 1)
        self.assertEqual(dry_run.json()['records'][0]['after']['attributes']['private_ip'], '10.9.1.8')
        self.assertEqual(dry_run.json()['records'][0]['after']['attributes']['memory_gb'], 8.0)
        dry_after = dry_run.json()['records'][0]['after']
        self.assertIn({'id': None, 'name': 'core', 'category': 'business_line'}, dry_after['tags'])
        self.assertIn({'id': None, 'name': 'prod', 'category': 'environment'}, dry_after['tags'])

        run_response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(run_response.status_code, 200, run_response.content)
        ci = ConfigItem.objects.get(name='prod-app-ecs-01')
        self.assertEqual(ci.ci_type.code, 'CLOUD_SERVER')
        self.assertEqual(ci.business_line, 'core')
        self.assertEqual(ci.admin_user, 'sre-core')
        self.assertEqual(ci.attributes['instance_id'], 'i-raw-ecs-001')
        self.assertEqual(ci.attributes['ip_address'], '10.9.1.8')
        self.assertEqual(ci.attributes['public_ip'], '47.9.1.8')
        self.assertEqual(ci.attributes['cloud_tags'][0]['key'], 'business_line')
        tag_names = set(ci.tags.values_list('name', flat=True))
        self.assertTrue({'core', 'prod', 'sre-core'}.issubset(tag_names))
        business_tag = CITag.objects.get(name='core')
        self.assertEqual(business_tag.category, 'business_line')
        tagged_response = self.client.get('/api/cmdb/config-items/', {'tags': business_tag.id})
        self.assertEqual(tagged_response.status_code, 200)
        self.assertEqual(tagged_response.json()['results'][0]['name'], 'prod-app-ecs-01')
        self.assertEqual(CISourceMapping.objects.get(ci=ci).source_account, 'prod-account')
        self.assertFalse(CICompletionIssue.objects.filter(ci=ci).exclude(status__in=['resolved', 'ignored']).exists())

    def test_run_due_collection_jobs_executes_only_enabled_due_jobs(self):
        due_job = CISyncJob.objects.create(
            name='到期 ECS 自动采集',
            source_type='aliyun_ecs',
            mode='scheduled',
            status='success',
            finished_at=timezone.now() - timezone.timedelta(minutes=90),
            config={
                'collection_enabled': True,
                'interval_minutes': 60,
                'items': [
                    {
                        'ci_type_name': '云主机(ECS)',
                        'ci_type_code': 'CLOUD_SERVER',
                        'name': 'ecs-due-01',
                        'source_type': 'aliyun_ecs',
                        'source_unique_id': 'i-due-001',
                        'business_line': 'core',
                        'environment': 'prod',
                        'admin_user': 'ops',
                        'attributes': {'instance_id': 'i-due-001', 'private_ip': '10.8.1.8'},
                    }
                ],
            },
        )
        not_due_job = CISyncJob.objects.create(
            name='未到期 ECS 自动采集',
            source_type='aliyun_ecs',
            mode='scheduled',
            status='success',
            finished_at=timezone.now(),
            config={
                'collection_enabled': True,
                'interval_minutes': 60,
                'items': [
                    {
                        'ci_type_name': '云主机(ECS)',
                        'ci_type_code': 'CLOUD_SERVER',
                        'name': 'ecs-not-due-01',
                        'source_type': 'aliyun_ecs',
                        'source_unique_id': 'i-not-due-001',
                        'business_line': 'core',
                        'environment': 'prod',
                        'admin_user': 'ops',
                    }
                ],
            },
        )
        disabled_job = CISyncJob.objects.create(
            name='停用 ECS 自动采集',
            source_type='aliyun_ecs',
            mode='scheduled',
            status='success',
            finished_at=timezone.now() - timezone.timedelta(minutes=90),
            config={
                'collection_enabled': False,
                'interval_minutes': 60,
                'items': [
                    {
                        'ci_type_name': '云主机(ECS)',
                        'ci_type_code': 'CLOUD_SERVER',
                        'name': 'ecs-disabled-01',
                        'source_type': 'aliyun_ecs',
                        'source_unique_id': 'i-disabled-001',
                        'business_line': 'core',
                        'environment': 'prod',
                        'admin_user': 'ops',
                    }
                ],
            },
        )

        response = self.client.post('/api/cmdb/sync-jobs/run-due/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['executed_count'], 1)
        self.assertEqual(payload['jobs'][0]['id'], due_job.id)
        self.assertEqual(payload['summary']['create'], 1)
        self.assertTrue(ConfigItem.objects.filter(name='ecs-due-01').exists())
        self.assertFalse(ConfigItem.objects.filter(name='ecs-not-due-01').exists())
        self.assertFalse(ConfigItem.objects.filter(name='ecs-disabled-01').exists())
        due_job.refresh_from_db()
        not_due_job.refresh_from_db()
        disabled_job.refresh_from_db()
        self.assertEqual(due_job.status, 'success')
        self.assertEqual(not_due_job.records.count(), 0)
        self.assertEqual(disabled_job.records.count(), 0)

    def test_run_due_collection_jobs_uses_aliyun_raw_rds_items(self):
        due_job = CISyncJob.objects.create(
            name='到期 RDS 自动采集',
            source_type='aliyun_rds',
            mode='scheduled',
            status='success',
            finished_at=timezone.now() - timezone.timedelta(minutes=180),
            config={
                'connector': 'aliyun',
                'resource_type': 'rds',
                'target_ci_type_code': 'MYSQL',
                'collection_enabled': True,
                'interval_minutes': 120,
                'source_account': 'prod-account',
                'raw_items': [
                    {
                        'DBInstanceId': 'rm-raw-001',
                        'DBInstanceDescription': 'prod-order-rds',
                        'RegionId': 'cn-shanghai',
                        'DBInstanceStatus': 'Running',
                        'Engine': 'MySQL',
                        'EngineVersion': '8.0',
                        'DBInstanceClass': 'mysql.n2.medium.2c',
                        'DBInstanceStorage': 200,
                        'ConnectionString': 'rm-raw-001.mysql.rds.aliyuncs.com',
                        'Port': 3306,
                        'VpcId': 'vpc-rds-001',
                        'VSwitchId': 'vsw-rds-001',
                        'DBInstanceNetType': 'Intranet',
                        'Tags': {
                            'Tag': [
                                {'Key': 'business_line', 'Value': 'order'},
                                {'Key': 'owner', 'Value': 'dba'},
                            ]
                        },
                    }
                ],
            },
        )

        response = self.client.post('/api/cmdb/sync-jobs/run-due/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['executed_count'], 1)
        self.assertEqual(payload['jobs'][0]['id'], due_job.id)
        self.assertEqual(payload['summary']['create'], 1)
        ci = ConfigItem.objects.get(name='prod-order-rds')
        self.assertEqual(ci.ci_type.code, 'MYSQL')
        self.assertEqual(ci.business_line, 'order')
        self.assertEqual(ci.admin_user, 'dba')
        self.assertEqual(ci.attributes['endpoint'], 'rm-raw-001.mysql.rds.aliyuncs.com')
        self.assertEqual(ci.attributes['storage_gb'], 200)
        self.assertEqual(ci.attributes['vpc_id'], 'vpc-rds-001')
        self.assertEqual(ci.attributes['vswitch_id'], 'vsw-rds-001')
        self.assertEqual(ci.attributes['network_type'], 'Intranet')
        self.assertEqual(CISourceMapping.objects.get(ci=ci).sync_status, 'success')
        self.assertTrue(ci.tags.filter(name='order', category='business_line').exists())
        self.assertEqual(payload['collection']['jobs'][0]['item_count'], 1)

    def test_aliyun_rds_postgresql_engine_syncs_to_postgresql_type(self):
        ensure_builtin_cmdb()
        due_job = CISyncJob.objects.create(
            name='到期 PostgreSQL RDS 自动采集',
            source_type='aliyun_rds',
            mode='scheduled',
            status='success',
            finished_at=timezone.now() - timezone.timedelta(minutes=180),
            config={
                'connector': 'aliyun',
                'resource_type': 'rds',
                'target_ci_type_code': 'MYSQL',
                'collection_enabled': True,
                'interval_minutes': 120,
                'source_account': 'prod-account',
                'raw_items': [{
                    'DBInstanceId': 'pgm-raw-001',
                    'DBInstanceDescription': 'prod-order-postgresql',
                    'RegionId': 'cn-shanghai',
                    'DBInstanceStatus': 'Running',
                    'Engine': 'PostgreSQL',
                    'EngineVersion': '15',
                    'DBInstanceStorage': 300,
                    'ConnectionString': 'pgm-raw-001.pg.rds.aliyuncs.com',
                    'Port': 5432,
                    'VpcId': 'vpc-rds-001',
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'order'}, {'Key': 'owner', 'Value': 'dba'}]},
                }],
            },
        )

        response = self.client.post('/api/cmdb/sync-jobs/run-due/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['jobs'][0]['id'], due_job.id)
        ci = ConfigItem.objects.get(name='prod-order-postgresql')
        self.assertEqual(ci.ci_type.code, 'POSTGRESQL')
        self.assertEqual(ci.attributes['engine'], 'PostgreSQL')
        self.assertEqual(ci.attributes['endpoint'], 'pgm-raw-001.pg.rds.aliyuncs.com')
        self.assertEqual(ci.attributes['port'], 5432)

    def test_run_due_collection_jobs_uses_aliyun_raw_redis_items(self):
        due_job = CISyncJob.objects.create(
            name='到期 Redis 自动采集',
            source_type='aliyun_redis',
            mode='scheduled',
            status='success',
            finished_at=timezone.now() - timezone.timedelta(minutes=180),
            config={
                'connector': 'aliyun',
                'resource_type': 'redis',
                'target_ci_type_code': 'REDIS',
                'collection_enabled': True,
                'interval_minutes': 120,
                'source_account': 'prod-account',
                'raw_items': [
                    {
                        'InstanceId': 'r-raw-001',
                        'InstanceName': 'prod-cache-redis',
                        'RegionId': 'cn-shanghai',
                        'ZoneId': 'cn-shanghai-b',
                        'InstanceStatus': 'Normal',
                        'ConnectionDomain': 'r-raw-001.redis.rds.aliyuncs.com',
                        'Port': 6379,
                        'EngineVersion': '6.0',
                        'Capacity': 16,
                        'VpcId': 'vpc-redis-001',
                        'VSwitchId': 'vsw-redis-001',
                        'PrivateIp': '10.88.1.9',
                        'Tags': {
                            'Tag': [
                                {'Key': 'business_line', 'Value': 'order'},
                                {'Key': 'environment', 'Value': 'prod'},
                                {'Key': 'owner', 'Value': 'cache-dba'},
                            ]
                        },
                    }
                ],
            },
        )

        response = self.client.post('/api/cmdb/sync-jobs/run-due/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['executed_count'], 1)
        self.assertEqual(payload['jobs'][0]['id'], due_job.id)
        self.assertEqual(payload['summary']['create'], 1)
        ci = ConfigItem.objects.get(name='prod-cache-redis')
        self.assertEqual(ci.ci_type.code, 'REDIS')
        self.assertEqual(ci.business_line, 'order')
        self.assertEqual(ci.admin_user, 'cache-dba')
        self.assertEqual(ci.attributes['endpoint'], 'r-raw-001.redis.rds.aliyuncs.com')
        self.assertEqual(ci.attributes['memory_gb'], 16)
        self.assertEqual(ci.attributes['vpc_id'], 'vpc-redis-001')
        self.assertEqual(ci.attributes['vswitch_id'], 'vsw-redis-001')
        self.assertEqual(ci.attributes['private_ip'], '10.88.1.9')
        mapping = CISourceMapping.objects.get(ci=ci)
        self.assertEqual(mapping.source_type, 'aliyun_redis')
        self.assertEqual(mapping.sync_status, 'success')
        self.assertTrue(ci.tags.filter(name='order', category='business_line').exists())
        self.assertEqual(payload['collection']['jobs'][0]['item_count'], 1)

    def test_run_due_collection_jobs_uses_phase_one_p1_aliyun_raw_items(self):
        ensure_builtin_cmdb()
        cases = [
            {
                'name': '到期 MongoDB 自动采集',
                'source_type': 'aliyun_mongodb',
                'resource_type': 'mongodb',
                'target_code': 'MONGODB',
                'ci_name': 'prod-doc-mongodb',
                'raw': {
                    'DBInstanceId': 'dds-raw-001',
                    'DBInstanceDescription': 'prod-doc-mongodb',
                    'RegionId': 'cn-hangzhou',
                    'DBInstanceStatus': 'Running',
                    'EngineVersion': '6.0',
                    'DBInstanceStorage': 100,
                    'ConnectionString': 'dds-raw-001.mongodb.rds.aliyuncs.com',
                    'Port': 3717,
                    'ReplicaCount': 3,
                    'VpcId': 'vpc-data-001',
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'data'}, {'Key': 'owner', 'Value': 'dba'}]},
                },
                'assertions': {'endpoint': 'dds-raw-001.mongodb.rds.aliyuncs.com', 'replica_count': 3},
            },
            {
                'name': '到期 Kafka 自动采集',
                'source_type': 'aliyun_kafka',
                'resource_type': 'kafka',
                'target_code': 'KAFKA',
                'ci_name': 'prod-order-kafka',
                'raw': {
                    'InstanceId': 'alikafka-raw-001',
                    'Name': 'prod-order-kafka',
                    'RegionId': 'cn-hangzhou',
                    'Status': 'Running',
                    'Endpoint': 'alikafka-raw-001.kafka.aliyuncs.com:9092',
                    'Version': '3.3',
                    'TopicCount': 42,
                    'PartitionCount': 168,
                    'DiskSize': 500,
                    'MessageLag': 1200,
                    'VpcId': 'vpc-data-001',
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'order'}, {'Key': 'owner', 'Value': 'mq-admin'}]},
                },
                'assertions': {'topic_count': 42, 'message_lag': 1200},
            },
            {
                'name': '到期 RocketMQ 自动采集',
                'source_type': 'aliyun_rocketmq',
                'resource_type': 'rocketmq',
                'target_code': 'ROCKETMQ',
                'ci_name': 'prod-payment-rocketmq',
                'raw': {
                    'InstanceId': 'rmq-raw-001',
                    'InstanceName': 'prod-payment-rocketmq',
                    'RegionId': 'cn-hangzhou',
                    'Status': 'Running',
                    'NameSrvEndpoint': 'rmq-raw-001.rocketmq.aliyuncs.com:9876',
                    'HttpEndpoint': 'https://rmq-raw-001.rocketmq.aliyuncs.com',
                    'Version': '5.0',
                    'TopicCount': 28,
                    'GroupCount': 11,
                    'MessageLag': 300,
                    'VpcId': 'vpc-data-001',
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'payment'}, {'Key': 'owner', 'Value': 'mq-admin'}]},
                },
                'assertions': {'endpoint': 'rmq-raw-001.rocketmq.aliyuncs.com:9876', 'group_count': 11},
            },
            {
                'name': '到期 OSS 自动采集',
                'source_type': 'aliyun_oss',
                'resource_type': 'oss',
                'target_code': 'OBJECT_STORAGE',
                'ci_name': 'prod-order-bucket',
                'raw': {
                    'Name': 'prod-order-bucket',
                    'Location': 'oss-cn-hangzhou',
                    'Status': 'Available',
                    'ExtranetEndpoint': 'oss-cn-hangzhou.aliyuncs.com',
                    'StorageGB': 2048,
                    'StorageClass': 'Standard',
                    'Acl': 'private',
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'order'}, {'Key': 'owner', 'Value': 'storage-admin'}]},
                },
                'assertions': {'bucket': 'prod-order-bucket', 'storage_gb': 2048},
            },
            {
                'name': '到期 SLB 自动采集',
                'source_type': 'aliyun_slb',
                'resource_type': 'slb',
                'target_code': 'LOAD_BALANCER',
                'ci_name': 'prod-order-slb',
                'raw': {
                    'LoadBalancerId': 'lb-raw-001',
                    'LoadBalancerName': 'prod-order-slb',
                    'RegionId': 'cn-hangzhou',
                    'LoadBalancerStatus': 'active',
                    'Address': '47.100.10.8',
                    'Bandwidth': 200,
                    'LoadBalancerSpec': 'slb.s2.small',
                    'AddressType': 'internet',
                    'VpcId': 'vpc-edge-001',
                    'BackendServerCount': 4,
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'order'}, {'Key': 'owner', 'Value': 'netops'}]},
                },
                'assertions': {'vip': '47.100.10.8', 'backend_count': 4},
            },
        ]
        for case in cases:
            CISyncJob.objects.create(
                name=case['name'],
                source_type=case['source_type'],
                mode='scheduled',
                status='success',
                finished_at=timezone.now() - timezone.timedelta(minutes=180),
                config={
                    'connector': 'aliyun',
                    'resource_type': case['resource_type'],
                    'target_ci_type_code': case['target_code'],
                    'collection_enabled': True,
                    'interval_minutes': 120,
                    'source_account': 'prod-account',
                    'raw_items': [case['raw']],
                },
            )

        response = self.client.post('/api/cmdb/sync-jobs/run-due/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['executed_count'], len(cases))
        self.assertEqual(payload['summary']['create'], len(cases))
        for case in cases:
            ci = ConfigItem.objects.get(name=case['ci_name'])
            self.assertEqual(ci.ci_type.code, case['target_code'])
            self.assertTrue(ci.business_line)
            self.assertTrue(ci.admin_user)
            for key, value in case['assertions'].items():
                self.assertEqual(ci.attributes[key], value)
            mapping = CISourceMapping.objects.get(ci=ci)
            self.assertEqual(mapping.source_type, case['source_type'])
            self.assertEqual(mapping.source_account, 'prod-account')
            self.assertEqual(mapping.sync_status, 'success')

    def test_run_due_collection_jobs_uses_extended_aliyun_raw_items(self):
        ensure_builtin_cmdb()
        cases = [
            {
                'name': '到期 ACK 自动采集',
                'source_type': 'aliyun_ack',
                'resource_type': 'ack',
                'target_code': 'K8S_CLUSTER',
                'ci_name': 'prod-ack',
                'raw': {
                    'cluster_id': 'c-raw-001',
                    'name': 'prod-ack',
                    'region_id': 'cn-hangzhou',
                    'state': 'running',
                    'current_version': '1.30.1-aliyun.1',
                    'node_count': 8,
                    'api_server': 'https://prod-ack.example.com',
                    'vpc_id': 'vpc-k8s-001',
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'platform'}, {'Key': 'owner', 'Value': 'k8s-admin'}]},
                },
                'assertions': {'cluster_id': 'c-raw-001', 'node_count': 8},
            },
            {
                'name': '到期云盘自动采集',
                'source_type': 'aliyun_disk',
                'resource_type': 'disk',
                'target_code': 'BLOCK_STORAGE',
                'ci_name': 'prod-system-disk',
                'raw': {
                    'DiskId': 'd-raw-001',
                    'DiskName': 'prod-system-disk',
                    'RegionId': 'cn-hangzhou',
                    'Status': 'In_use',
                    'Category': 'cloud_essd',
                    'Size': 200,
                    'PerformanceLevel': 'PL1',
                    'InstanceId': 'i-raw-ecs-001',
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'platform'}, {'Key': 'owner', 'Value': 'storage-admin'}]},
                },
                'assertions': {'volume_id': 'd-raw-001', 'capacity_gb': 200, 'attached_to': 'i-raw-ecs-001'},
            },
            {
                'name': '到期 NAS 自动采集',
                'source_type': 'aliyun_nas',
                'resource_type': 'nas',
                'target_code': 'FILE_STORAGE',
                'ci_name': 'prod-shared-nas',
                'raw': {
                    'FileSystemId': 'nas-raw-001',
                    'Description': 'prod-shared-nas',
                    'RegionId': 'cn-hangzhou',
                    'Status': 'Running',
                    'ProtocolType': 'NFS',
                    'CapacityGB': 10240,
                    'MeteredSize': 2048,
                    'MountTargetDomain': 'nas-raw-001.cn-hangzhou.nas.aliyuncs.com',
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'platform'}, {'Key': 'owner', 'Value': 'storage-admin'}]},
                },
                'assertions': {'filesystem_id': 'nas-raw-001', 'protocol': 'nfs', 'used_gb': 2048},
            },
            {
                'name': '到期 ClickHouse 自动采集',
                'source_type': 'aliyun_clickhouse',
                'resource_type': 'clickhouse',
                'target_code': 'CLICKHOUSE',
                'ci_name': 'prod-clickhouse',
                'raw': {
                    'DBClusterId': 'cc-raw-001',
                    'DBClusterDescription': 'prod-clickhouse',
                    'RegionId': 'cn-hangzhou',
                    'DBClusterStatus': 'Running',
                    'ConnectionString': 'cc-raw-001.clickhouse.aliyuncs.com',
                    'EngineVersion': '23.8',
                    'ShardCount': 2,
                    'ReplicaCount': 2,
                    'StorageSize': 800,
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'data'}, {'Key': 'owner', 'Value': 'data-admin'}]},
                },
                'assertions': {'cluster_id': 'cc-raw-001', 'shard_count': 2, 'replica_count': 2},
            },
            {
                'name': '到期 Hologres 自动采集',
                'source_type': 'aliyun_hologres',
                'resource_type': 'hologres',
                'target_code': 'HOLOGRES',
                'ci_name': 'prod-hologres',
                'raw': {
                    'InstanceId': 'hg-raw-001',
                    'InstanceName': 'prod-hologres',
                    'RegionId': 'cn-hangzhou',
                    'Status': 'Running',
                    'Endpoint': 'hg-raw-001.hologres.aliyuncs.com',
                    'Version': '3.0',
                    'Cpu': 64,
                    'StorageGB': 2048,
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'data'}, {'Key': 'owner', 'Value': 'data-admin'}]},
                },
                'assertions': {'instance_id': 'hg-raw-001', 'cpu': 64, 'storage_gb': 2048},
            },
            {
                'name': '到期 MaxCompute 自动采集',
                'source_type': 'aliyun_maxcompute',
                'resource_type': 'maxcompute',
                'target_code': 'MAXCOMPUTE',
                'ci_name': 'prod_maxcompute',
                'raw': {
                    'ProjectName': 'prod_maxcompute',
                    'RegionId': 'cn-hangzhou',
                    'Status': 'Available',
                    'QuotaName': 'pay-as-you-go',
                    'StorageGB': 4096,
                    'TableCount': 128,
                    'JobCount': 16,
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'data'}, {'Key': 'owner', 'Value': 'data-admin'}]},
                },
                'assertions': {'project_name': 'prod_maxcompute', 'quota_name': 'pay-as-you-go', 'table_count': 128},
            },
            {
                'name': '到期 DataWorks 自动采集',
                'source_type': 'aliyun_dataworks',
                'resource_type': 'dataworks',
                'target_code': 'DATAWORKS',
                'ci_name': 'prod-dataworks',
                'raw': {
                    'ProjectId': 'dw-raw-001',
                    'ProjectName': 'prod-dataworks',
                    'RegionId': 'cn-hangzhou',
                    'Status': 'Available',
                    'ProjectMode': 'standard',
                    'NodeCount': 80,
                    'WorkflowCount': 12,
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'data'}, {'Key': 'owner', 'Value': 'data-admin'}]},
                },
                'assertions': {'workspace_id': 'dw-raw-001', 'workspace_name': 'prod-dataworks', 'workflow_count': 12},
            },
            {
                'name': '到期 NAT 自动采集',
                'source_type': 'aliyun_nat_gateway',
                'resource_type': 'nat_gateway',
                'target_code': 'NAT_GATEWAY',
                'ci_name': 'prod-nat',
                'raw': {
                    'NatGatewayId': 'ngw-raw-001',
                    'Name': 'prod-nat',
                    'RegionId': 'cn-hangzhou',
                    'Status': 'Available',
                    'NatType': 'Enhanced',
                    'Spec': 'Small',
                    'VpcId': 'vpc-edge-001',
                    'IpLists': {'IpList': [{'IpAddress': '47.100.30.8'}]},
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'edge'}, {'Key': 'owner', 'Value': 'netops'}]},
                },
                'assertions': {'instance_id': 'ngw-raw-001', 'vpc_id': 'vpc-edge-001', 'eip_addresses': '47.100.30.8'},
            },
            {
                'name': '到期 EIP 自动采集',
                'source_type': 'aliyun_eip',
                'resource_type': 'eip',
                'target_code': 'ELASTIC_IP',
                'ci_name': '47.100.30.8',
                'raw': {
                    'AllocationId': 'eip-raw-001',
                    'IpAddress': '47.100.30.8',
                    'RegionId': 'cn-hangzhou',
                    'Status': 'InUse',
                    'Bandwidth': 100,
                    'InternetChargeType': 'PayByTraffic',
                    'InstanceId': 'ngw-raw-001',
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'edge'}, {'Key': 'owner', 'Value': 'netops'}]},
                },
                'assertions': {'allocation_id': 'eip-raw-001', 'ip_address': '47.100.30.8', 'attached_to': 'ngw-raw-001'},
            },
            {
                'name': '到期 Elasticsearch 自动采集',
                'source_type': 'aliyun_elasticsearch',
                'resource_type': 'elasticsearch',
                'target_code': 'ELASTICSEARCH',
                'ci_name': 'prod-search-es',
                'raw': {
                    'instanceId': 'es-raw-001',
                    'description': 'prod-search-es',
                    'regionId': 'cn-hangzhou',
                    'status': 'active',
                    'esVersion': '8.13',
                    'nodeAmount': 3,
                    'nodeSpec': {'amount': 3, 'disk': 200},
                    'endpoint': 'es-raw-001.elasticsearch.aliyuncs.com',
                    'vpcId': 'vpc-data-001',
                    'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'data'}, {'Key': 'owner', 'Value': 'search-admin'}]},
                },
                'assertions': {'cluster_id': 'es-raw-001', 'version': '8.13', 'node_count': 3, 'storage_gb': 600.0},
            },
        ]
        for case in cases:
            CISyncJob.objects.create(
                name=case['name'],
                source_type=case['source_type'],
                mode='scheduled',
                status='success',
                finished_at=timezone.now() - timezone.timedelta(minutes=180),
                config={
                    'connector': 'aliyun',
                    'resource_type': case['resource_type'],
                    'target_ci_type_code': case['target_code'],
                    'collection_enabled': True,
                    'interval_minutes': 120,
                    'source_account': 'prod-account',
                    'raw_items': [case['raw']],
                },
            )

        response = self.client.post('/api/cmdb/sync-jobs/run-due/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['executed_count'], len(cases))
        self.assertEqual(payload['summary']['create'], len(cases))
        for case in cases:
            ci = ConfigItem.objects.get(name=case['ci_name'])
            self.assertEqual(ci.ci_type.code, case['target_code'])
            self.assertTrue(ci.business_line)
            self.assertTrue(ci.admin_user)
            for key, value in case['assertions'].items():
                self.assertEqual(ci.attributes[key], value)
            mapping = CISourceMapping.objects.get(ci=ci)
            self.assertEqual(mapping.source_type, case['source_type'])
            self.assertEqual(mapping.source_account, 'prod-account')
            self.assertEqual(mapping.sync_status, 'success')

    def test_run_due_collection_jobs_uses_vsphere_and_huaweicloud_raw_items(self):
        ensure_builtin_cmdb()
        cases = [
            {
                'name': '到期 vSphere 虚拟机自动采集',
                'source_type': 'vsphere_vm',
                'connector': 'vsphere',
                'resource_type': 'vm',
                'target_code': 'VIRTUAL_MACHINE',
                'ci_name': 'prod-vsphere-app-01',
                'raw': {
                    'vm': 'vm-421',
                    'name': 'prod-vsphere-app-01',
                    'power_state': 'poweredOn',
                    'guest_ip': '10.21.1.8',
                    'num_cpu': 8,
                    'memory_mb': 32768,
                    'provisioned_gb': 400,
                    'datacenter': 'idc-shanghai',
                    'cluster': 'cluster-a',
                    'host': 'esxi-01',
                    'guest_os': 'Ubuntu Linux',
                    'business_line': 'core',
                    'environment': 'prod',
                    'owner': 'vmops',
                },
                'assertions': {'private_ip': '10.21.1.8', 'memory_gb': 32.0, 'datacenter': 'idc-shanghai'},
            },
            {
                'name': '到期华为云 ECS 自动采集',
                'source_type': 'huaweicloud_ecs',
                'connector': 'huaweicloud',
                'resource_type': 'ecs',
                'target_code': 'CLOUD_SERVER',
                'ci_name': 'prod-hwc-ecs-01',
                'raw': {
                    'id': 'hw-ecs-001',
                    'name': 'prod-hwc-ecs-01',
                    'status': 'ACTIVE',
                    'private_ip': '10.31.1.9',
                    'floating_ip': '121.36.10.9',
                    'flavor': {'id': 's6.large.2', 'vcpus': 2, 'ram': 4096},
                    'region': 'cn-north-4',
                    'availability_zone': 'cn-north-4a',
                    'vpc_id': 'vpc-hwc-001',
                    'business_line': 'core',
                    'environment': 'prod',
                    'owner': 'cloudops',
                },
                'assertions': {'private_ip': '10.31.1.9', 'public_ip': '121.36.10.9', 'memory_gb': 4.0},
            },
            {
                'name': '到期华为云 RDS 自动采集',
                'source_type': 'huaweicloud_rds',
                'connector': 'huaweicloud',
                'resource_type': 'rds',
                'target_code': 'MYSQL',
                'ci_name': 'prod-hwc-rds-01',
                'raw': {
                    'id': 'hw-rds-001',
                    'name': 'prod-hwc-rds-01',
                    'status': 'ACTIVE',
                    'private_ip': '10.31.2.10',
                    'port': 3306,
                    'datastore': {'type': 'MySQL', 'version': '8.0'},
                    'flavor_ref': 'rds.mysql.n1.large.2',
                    'volume_size': 300,
                    'vpc_id': 'vpc-hwc-001',
                    'business_line': 'data',
                    'environment': 'prod',
                    'owner': 'dba',
                },
                'assertions': {'endpoint': '10.31.2.10', 'storage_gb': 300, 'version': '8.0'},
            },
            {
                'name': '到期华为云 Redis 自动采集',
                'source_type': 'huaweicloud_redis',
                'connector': 'huaweicloud',
                'resource_type': 'redis',
                'target_code': 'REDIS',
                'ci_name': 'prod-hwc-redis-01',
                'raw': {
                    'id': 'hw-redis-001',
                    'name': 'prod-hwc-redis-01',
                    'status': 'RUNNING',
                    'ip': '10.31.3.11',
                    'port': 6379,
                    'engine_version': '6.0',
                    'capacity': 16,
                    'vpc_id': 'vpc-hwc-001',
                    'business_line': 'data',
                    'environment': 'prod',
                    'owner': 'cache-dba',
                },
                'assertions': {'endpoint': '10.31.3.11', 'private_ip': '10.31.3.11', 'memory_gb': 16},
            },
            {
                'name': '到期华为云 EIP 自动采集',
                'source_type': 'huaweicloud_eip',
                'connector': 'huaweicloud',
                'resource_type': 'eip',
                'target_code': 'ELASTIC_IP',
                'ci_name': '121.36.10.9',
                'raw': {
                    'id': 'hw-eip-001',
                    'public_ip_address': '121.36.10.9',
                    'region': 'cn-north-4',
                    'status': 'ACTIVE',
                    'bandwidth_size': 100,
                    'type': '5_bgp',
                    'port_id': 'hw-port-001',
                    'business_line': 'edge',
                    'environment': 'prod',
                    'owner': 'netops',
                },
                'assertions': {'allocation_id': 'hw-eip-001', 'ip_address': '121.36.10.9', 'attached_to': 'hw-port-001'},
            },
            {
                'name': '到期华为云 OBS 自动采集',
                'source_type': 'huaweicloud_obs',
                'connector': 'huaweicloud',
                'resource_type': 'obs',
                'target_code': 'OBJECT_STORAGE',
                'ci_name': 'prod-hwc-bucket',
                'raw': {
                    'name': 'prod-hwc-bucket',
                    'location': 'cn-north-4',
                    'endpoint': 'obs.cn-north-4.myhuaweicloud.com',
                    'creation_date': '2026-01-01T00:00:00Z',
                    'storage_class': 'STANDARD',
                    'business_line': 'data',
                    'environment': 'prod',
                    'owner': 'storage-admin',
                },
                'assertions': {'bucket': 'prod-hwc-bucket', 'endpoint': 'https://obs.cn-north-4.myhuaweicloud.com', 'region': 'cn-north-4'},
            },
        ]
        for case in cases:
            CISyncJob.objects.create(
                name=case['name'],
                source_type=case['source_type'],
                mode='scheduled',
                status='success',
                finished_at=timezone.now() - timezone.timedelta(minutes=180),
                config={
                    'connector': case['connector'],
                    'resource_type': case['resource_type'],
                    'target_ci_type_code': case['target_code'],
                    'collection_enabled': True,
                    'interval_minutes': 120,
                    'source_account': 'prod-account',
                    'raw_items': [case['raw']],
                },
            )

        response = self.client.post('/api/cmdb/sync-jobs/run-due/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['executed_count'], len(cases))
        self.assertEqual(payload['summary']['create'], len(cases))
        for case in cases:
            ci = ConfigItem.objects.get(name=case['ci_name'])
            self.assertEqual(ci.ci_type.code, case['target_code'])
            self.assertTrue(ci.business_line)
            self.assertTrue(ci.admin_user)
            for key, value in case['assertions'].items():
                self.assertEqual(ci.attributes[key], value)
            mapping = CISourceMapping.objects.get(ci=ci)
            self.assertEqual(mapping.source_type, case['source_type'])
            self.assertEqual(mapping.source_account, 'prod-account')

    def test_collection_jobs_fetch_provider_items_from_credentials_when_raw_items_are_absent(self):
        from unittest.mock import patch
        from multicloud.models import CloudCredential

        ensure_builtin_cmdb()
        aliyun_account = CloudCredential.objects.create(
            provider='aliyun',
            name='阿里云生产账号',
            account_name='prod-aliyun',
            access_key_id='ak-test',
            access_key_secret='sk-test',
            default_region='cn-hangzhou',
        )
        huawei_account = CloudCredential.objects.create(
            provider='huawei',
            name='华为云生产账号',
            account_name='prod-huawei',
            access_key_id='ak-test',
            access_key_secret='sk-test',
            project_id='project-test',
            default_region='cn-north-4',
        )
        jobs = [
            CISyncJob.objects.create(
                name='账号采集阿里云 ECS',
                source_type='aliyun_ecs',
                mode='scheduled',
                status='success',
                finished_at=timezone.now() - timezone.timedelta(minutes=90),
                config={
                    'connector': 'aliyun',
                    'resource_type': 'ecs',
                    'target_ci_type_code': 'CLOUD_SERVER',
                    'collection_enabled': True,
                    'interval_minutes': 60,
                    'cloud_account_id': aliyun_account.id,
                },
            ),
            CISyncJob.objects.create(
                name='账号采集 vSphere 虚拟机',
                source_type='vsphere_vm',
                mode='scheduled',
                status='success',
                finished_at=timezone.now() - timezone.timedelta(minutes=90),
                config={
                    'connector': 'vsphere',
                    'resource_type': 'vm',
                    'target_ci_type_code': 'CLOUD_SERVER',
                    'collection_enabled': True,
                    'interval_minutes': 60,
                    'source_account': 'vcenter-prod',
                    'host': 'vcenter.example.com',
                    'username': 'administrator@vsphere.local',
                    'auth_ref': 'SXDEVOPS_VSPHERE_PROD',
                },
            ),
            CISyncJob.objects.create(
                name='账号采集华为云 ECS',
                source_type='huaweicloud_ecs',
                mode='scheduled',
                status='success',
                finished_at=timezone.now() - timezone.timedelta(minutes=90),
                config={
                    'connector': 'huaweicloud',
                    'resource_type': 'ecs',
                    'target_ci_type_code': 'CLOUD_SERVER',
                    'collection_enabled': True,
                    'interval_minutes': 60,
                    'cloud_account_id': huawei_account.id,
                },
            ),
        ]

        with patch('cmdb.collectors._fetch_aliyun_raw_items', return_value=[{
            'InstanceId': 'i-sdk-001',
            'InstanceName': 'sdk-aliyun-ecs-01',
            'RegionId': 'cn-hangzhou',
            'Status': 'Running',
            'VpcAttributes': {'PrivateIpAddress': {'IpAddress': ['10.1.1.8']}},
            'Tags': {'Tag': [{'Key': 'business_line', 'Value': 'core'}, {'Key': 'owner', 'Value': 'sre'}]},
        }]) as aliyun_fetch, patch('cmdb.collectors._fetch_vsphere_raw_items', return_value=[{
            'vm': 'vm-sdk-001',
            'name': 'sdk-vsphere-vm-01',
            'power_state': 'poweredOn',
            'guest_ip': '10.2.1.8',
            'num_cpu': 4,
            'memory_mb': 8192,
            'business_line': 'core',
            'owner': 'vmops',
        }]) as vsphere_fetch, patch('cmdb.collectors._fetch_huaweicloud_raw_items', return_value=[{
            'id': 'hw-sdk-001',
            'name': 'sdk-huawei-ecs-01',
            'status': 'ACTIVE',
            'private_ip': '10.3.1.8',
            'flavor': {'vcpus': 2, 'ram': 4096},
            'business_line': 'core',
            'owner': 'cloudops',
        }]) as huawei_fetch:
            response = self.client.post('/api/cmdb/sync-jobs/run-due/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['executed_count'], len(jobs))
        self.assertEqual(payload['summary'].get('create'), len(jobs), payload)
        aliyun_fetch.assert_called_once()
        vsphere_fetch.assert_called_once()
        huawei_fetch.assert_called_once()
        self.assertTrue(ConfigItem.objects.filter(name='sdk-aliyun-ecs-01', attributes__private_ip='10.1.1.8').exists())
        self.assertTrue(ConfigItem.objects.filter(name='sdk-vsphere-vm-01', attributes__private_ip='10.2.1.8').exists())
        self.assertTrue(ConfigItem.objects.filter(name='sdk-huawei-ecs-01', attributes__private_ip='10.3.1.8').exists())
        self.assertEqual(ConfigItem.objects.get(name='sdk-vsphere-vm-01').ci_type.code, 'VIRTUAL_MACHINE')
        self.assertEqual(CISourceMapping.objects.get(source_unique_id='i-sdk-001').source_account, 'prod-aliyun')
        self.assertEqual(CISourceMapping.objects.get(source_unique_id='vm-sdk-001').source_account, 'vcenter-prod')
        self.assertEqual(CISourceMapping.objects.get(source_unique_id='hw-sdk-001').source_account, 'prod-huawei')

    def test_huaweicloud_ecs_provider_fetch_attaches_ces_metric_snapshots(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from cmdb.collectors import _fetch_huaweicloud_raw_items

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def to_dict(self):
                return self.payload

        class FakeBuilder:
            def __init__(self, client):
                self.client = client

            def with_credentials(self, credentials):
                return self

            def with_region(self, region):
                return self

            def build(self):
                return self.client

        class FakeRegion:
            @staticmethod
            def value_of(region):
                return region

        class FakeListServersDetailsRequest:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class FakeShowMetricDataRequest:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        class FakeEcsClientFactory:
            @staticmethod
            def new_builder():
                return FakeBuilder(fake_ecs_client)

        class FakeCesClientFactory:
            @staticmethod
            def new_builder():
                return FakeBuilder(fake_ces_client)

        class FakeEcsClient:
            def list_servers_details(self, request):
                return FakeResponse({
                    'servers': [{
                        'id': 'hw-metric-001',
                        'name': 'hw-metric-ecs-01',
                        'status': 'ACTIVE',
                        'private_ip': '10.31.1.12',
                        'flavor': {'vcpus': 2, 'ram': 4096},
                    }],
                    'count': 1,
                })

        class FakeCesClient:
            def __init__(self):
                self.metric_names = []

            def show_metric_data(self, request):
                metric_values = {
                    'cpu_util': 35.5,
                    'mem_util': 63.2,
                    'disk_util_inband': 48.8,
                }
                self.metric_names.append(request.metric_name)
                return FakeResponse({
                    'datapoints': [{
                        'average': metric_values[request.metric_name],
                        'timestamp': '2026-07-22T00:00:00Z',
                    }],
                })

        fake_ecs_client = FakeEcsClient()
        fake_ces_client = FakeCesClient()
        modules = {
            'huaweicloudsdkcore.auth.credentials': SimpleNamespace(BasicCredentials=lambda ak, sk, project_id: object()),
            'huaweicloudsdkecs.v2': SimpleNamespace(
                EcsClient=FakeEcsClientFactory,
                ListServersDetailsRequest=FakeListServersDetailsRequest,
            ),
            'huaweicloudsdkecs.v2.region.ecs_region': SimpleNamespace(EcsRegion=FakeRegion),
            'huaweicloudsdkces.v1': SimpleNamespace(
                CesClient=FakeCesClientFactory,
                ShowMetricDataRequest=FakeShowMetricDataRequest,
            ),
            'huaweicloudsdkces.v1.region.ces_region': SimpleNamespace(CesRegion=FakeRegion),
        }

        with patch('cmdb.collectors._optional_import', side_effect=lambda module_name, install_hint: modules[module_name]):
            items = _fetch_huaweicloud_raw_items({
                'access_key_id': 'ak-test',
                'secret_key': 'sk-test',
                'project_id': 'project-test',
                'region_id': 'cn-north-4',
            }, 'ecs')

        self.assertEqual(fake_ces_client.metric_names, ['cpu_util', 'mem_util', 'disk_util_inband'])
        snapshots = items[0]['_metric_snapshots']
        self.assertEqual({row['metric'] for row in snapshots}, {'cpu_usage', 'memory_usage', 'disk_usage'})
        self.assertEqual(items[0]['_metric_collection_status'], 'success')

    def test_huaweicloud_network_and_obs_fetch_accept_sdk_response_shapes(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from cmdb.collectors import _fetch_huaweicloud_raw_items, _huaweicloud_eip_item, _huaweicloud_obs_item

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def to_dict(self):
                return self.payload

        class FakeBuilder:
            def __init__(self, client):
                self.client = client

            def with_credentials(self, credentials):
                return self

            def with_region(self, region):
                return self

            def with_endpoint(self, endpoint):
                self.endpoint = endpoint
                return self

            def build(self):
                return self.client

        class FakeRegion:
            @staticmethod
            def value_of(region):
                return region

        class FakeListPublicipsRequest:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class FakeListBucketsRequest:
            pass

        class FakeEipClientFactory:
            @staticmethod
            def new_builder():
                return FakeBuilder(fake_eip_client)

        class FakeObsClientFactory:
            @staticmethod
            def new_builder():
                return FakeBuilder(fake_obs_client)

        class FakeEipClient:
            def list_publicips(self, request):
                return FakeResponse({
                    'body': {
                        'publicips': [{
                            'id': 'hw-eip-sdk-001',
                            'publicip_address': '121.36.10.9',
                            'bandwidth': {'size': 100, 'share_type': 'PER'},
                            'status': 'ACTIVE',
                        }],
                    },
                })

        class FakeObsClient:
            def list_buckets(self, request):
                return FakeResponse({
                    'body': {
                        'buckets': [{
                            'bucket_name': 'prod-hwc-bucket',
                            'location': 'cn-east-3',
                            'creationDate': '2026-01-01T00:00:00Z',
                        }],
                    },
                })

        fake_eip_client = FakeEipClient()
        fake_obs_client = FakeObsClient()
        modules = {
            'huaweicloudsdkcore.auth.credentials': SimpleNamespace(BasicCredentials=lambda ak, sk, project_id: object()),
            'huaweicloudsdkeip.v2': SimpleNamespace(
                EipClient=FakeEipClientFactory,
                ListPublicipsRequest=FakeListPublicipsRequest,
            ),
            'huaweicloudsdkeip.v2.region.eip_region': SimpleNamespace(EipRegion=FakeRegion),
            'huaweicloudsdkobs.v1': SimpleNamespace(
                ObsClient=FakeObsClientFactory,
                ListBucketsRequest=FakeListBucketsRequest,
            ),
            'huaweicloudsdkobs.v1.obs_credentials': SimpleNamespace(ObsCredentials=lambda ak, sk: object()),
        }

        with patch('cmdb.collectors._optional_import', side_effect=lambda module_name, install_hint: modules[module_name]):
            eip_items = _fetch_huaweicloud_raw_items({
                'access_key_id': 'ak-test',
                'secret_key': 'sk-test',
                'project_id': 'project-test',
                'region_id': 'cn-east-3',
            }, 'eip')
            obs_items = _fetch_huaweicloud_raw_items({
                'access_key_id': 'ak-test',
                'secret_key': 'sk-test',
                'region_id': 'cn-east-3',
            }, 'obs')

        self.assertEqual(eip_items[0]['publicip_address'], '121.36.10.9')
        self.assertEqual(obs_items[0]['bucket_name'], 'prod-hwc-bucket')
        self.assertEqual(_huaweicloud_eip_item(eip_items[0], {})['attributes']['ip_address'], '121.36.10.9')
        obs_payload = _huaweicloud_obs_item(obs_items[0], {})
        self.assertEqual(obs_payload['attributes']['bucket'], 'prod-hwc-bucket')
        self.assertEqual(obs_payload['attributes']['endpoint'], 'https://obs.cn-east-3.myhuaweicloud.com')

    def test_demo_cloud_credential_sync_is_rejected(self):
        from unittest.mock import patch
        from multicloud.models import CloudCredential

        ensure_builtin_cmdb()
        credential = CloudCredential.objects.create(
            provider='aliyun',
            name='阿里云-交易系统生产主账号',
            account_name='trade-prod',
            auth_mode='demo',
            access_key_id='aliyun-demo-ak',
            access_key_secret='aliyun-demo-sk',
            default_region='cn-hangzhou',
            demo_mode=True,
        )
        job = CISyncJob.objects.create(
            name='Demo 阿里云 ECS 自动注册',
            source_type='aliyun_ecs',
            mode='manual',
            config={
                'connector': 'aliyun',
                'resource_type': 'ecs',
                'target_ci_type_code': 'CLOUD_SERVER',
                'collection_enabled': True,
                'cloud_account_id': credential.id,
            },
        )

        with patch('cmdb.collectors._fetch_aliyun_raw_items') as aliyun_fetch:
            response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 400, response.content)
        payload = response.json()
        self.assertIn('Demo', payload['detail'])
        self.assertFalse(ConfigItem.objects.filter(attributes__source_type='aliyun_ecs').exists())
        self.assertFalse(CISourceMapping.objects.filter(source_account='trade-prod').exists())
        aliyun_fetch.assert_not_called()

    def test_aliyun_elasticsearch_raw_fetch_uses_openapi_instances_endpoint(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from cmdb.collectors import _fetch_aliyun_elasticsearch_raw_items

        class FakeListInstanceRequest:
            def __init__(self):
                self.endpoint = ''
                self.method = ''
                self.uri_pattern = ''
                self.query = {}

            def set_accept_format(self, value):
                self.accept_format = value

            def set_endpoint(self, value):
                self.endpoint = value

            def set_protocol_type(self, value):
                self.protocol_type = value

            def set_method(self, value):
                self.method = value

            def set_uri_pattern(self, value):
                self.uri_pattern = value

            def add_query_param(self, name, value):
                self.query[name] = value

        class FakeAcsClient:
            last_request = None

            def __init__(self, access_key_id, access_key_secret, region_id):
                self.region_id = region_id

            def do_action_with_exception(self, request):
                FakeAcsClient.last_request = request
                return json.dumps({
                    'Result': [{
                        'instanceId': 'es-openapi-001',
                        'description': 'prod-search',
                    }],
                    'total': 1,
                }).encode('utf-8')

        modules = {
            'aliyunsdkcore.client': SimpleNamespace(AcsClient=FakeAcsClient),
            'aliyunsdkelasticsearch.request.v20170613.ListInstanceRequest': SimpleNamespace(ListInstanceRequest=FakeListInstanceRequest),
        }
        with patch('cmdb.collectors._optional_import', side_effect=lambda module_name, install_hint: modules[module_name]), \
                patch('cmdb.collectors._optional_import_or_none', side_effect=lambda module_name: modules.get(module_name)):
            items = _fetch_aliyun_elasticsearch_raw_items({
                'access_key_id': 'ak-test',
                'access_key_secret': 'sk-test',
                'region_id': 'cn-hangzhou',
                'endpoint': 'https://elasticsearch.console.aliyun.com/cn-hangzhou/instances',
            })

        self.assertEqual(items[0]['instanceId'], 'es-openapi-001')
        request = FakeAcsClient.last_request
        self.assertEqual(request.endpoint, 'elasticsearch.cn-hangzhou.aliyuncs.com')
        self.assertEqual(request.method, 'GET')
        self.assertEqual(request.uri_pattern, '/openapi/instances')
        self.assertEqual(request.query, {'page': 1, 'size': 100})

    def test_aliyun_ecs_payload_includes_cloudmonitor_metric_snapshots(self):
        from unittest.mock import patch
        from cmdb.collectors import _aliyun_ecs_item, _attach_aliyun_ecs_usage_metrics

        raw_items = [{
            'InstanceId': 'i-metric-001',
            'InstanceName': 'metric-ecs-01',
            'RegionId': 'cn-hangzhou',
            'Status': 'Running',
            'Cpu': 4,
            'Memory': 8192,
        }]
        snapshots = [{
            'metric': 'cpu_usage',
            'value': 42.5,
            'unit': '%',
            'usage_percent': 42.5,
            'source': 'aliyun_cloudmonitor',
        }]

        with patch('cmdb.collectors._fetch_aliyun_ecs_usage_metrics', return_value={'i-metric-001': snapshots}):
            _attach_aliyun_ecs_usage_metrics({}, object(), raw_items)

        payload = _aliyun_ecs_item(raw_items[0], {'source_type': 'aliyun_ecs'})
        self.assertEqual(payload['_metric_snapshots'], snapshots)
        self.assertEqual(payload['attributes']['cpu'], 4)
        self.assertEqual(payload['attributes']['memory_gb'], 8)
        self.assertEqual(payload['attributes']['metric_collection_status'], 'success')

    def test_aliyun_ecs_metric_collection_failure_keeps_error_context(self):
        from unittest.mock import patch
        from cmdb.collectors import _aliyun_ecs_item, _attach_aliyun_ecs_usage_metrics

        raw_items = [{
            'InstanceId': 'i-metric-denied',
            'InstanceName': 'metric-denied-ecs',
            'RegionId': 'cn-hangzhou',
            'Status': 'Running',
        }]

        with patch('cmdb.collectors._fetch_aliyun_ecs_usage_metrics', side_effect=ValueError('阿里云云监控指标采集失败：403 NoPermission')):
            _attach_aliyun_ecs_usage_metrics({}, object(), raw_items)

        payload = _aliyun_ecs_item(raw_items[0], {'source_type': 'aliyun_ecs'})
        self.assertNotIn('_metric_snapshots', payload)
        self.assertEqual(payload['attributes']['metric_collection_status'], 'failed')
        self.assertIn('NoPermission', payload['attributes']['metric_collection_error'])

    def test_aliyun_ecs_cloudmonitor_failure_falls_back_to_ecs_cpu_metric(self):
        from unittest.mock import patch
        from cmdb.collectors import _aliyun_ecs_item, _attach_aliyun_ecs_usage_metrics

        raw_items = [{
            'InstanceId': 'i-metric-fallback',
            'InstanceName': 'metric-fallback-ecs',
            'RegionId': 'cn-hangzhou',
            'Status': 'Running',
        }]
        fallback_snapshots = [{
            'metric': 'cpu_usage',
            'value': 13.5,
            'unit': '%',
            'usage_percent': 13.5,
            'source': 'aliyun_ecs_monitor',
        }]

        with patch('cmdb.collectors._fetch_aliyun_ecs_usage_metrics', side_effect=ValueError('阿里云云监控指标采集失败：403 NoPermission')):
            with patch('cmdb.collectors._fetch_aliyun_ecs_cpu_usage_from_ecs_monitor', return_value={'i-metric-fallback': fallback_snapshots}):
                _attach_aliyun_ecs_usage_metrics({}, object(), raw_items)

        payload = _aliyun_ecs_item(raw_items[0], {'source_type': 'aliyun_ecs'})
        self.assertEqual(payload['_metric_snapshots'], fallback_snapshots)
        self.assertEqual(payload['attributes']['metric_collection_status'], 'partial')
        self.assertIn('NoPermission', payload['attributes']['metric_collection_error'])
        self.assertIn('内存/磁盘当前用量仍需要云监控权限', payload['attributes']['metric_collection_error'])

    def test_aliyun_ecs_monitor_cpu_usage_prefers_latest_point(self):
        from cmdb.collectors import _aliyun_ecs_monitor_rows, _ecs_monitor_cpu_usage

        payload = {
            'MonitorData': {
                'InstanceMonitorData': [
                    {'InstanceId': 'i-001', 'CPU': '0', 'TimeStamp': '2026-07-20T01:00:00Z'},
                    {'InstanceId': 'i-001', 'CPU': '12.34', 'TimeStamp': '2026-07-20T01:01:00Z'},
                ],
            },
        }

        rows = _aliyun_ecs_monitor_rows(payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(_ecs_monitor_cpu_usage(rows[-1]), 12.34)

    def test_aliyun_cloudmonitor_zero_usage_is_valid_metric(self):
        from cmdb.collectors import _metric_point_usage

        self.assertEqual(_metric_point_usage({'Average': 0}), 0)
        self.assertEqual(_metric_point_usage({'Average': '0'}), 0)

    def test_vsphere_run_accepts_runtime_password_without_persisting_secret(self):
        from unittest.mock import patch

        ensure_builtin_cmdb()
        job = CISyncJob.objects.create(
            name='运行时密码采集 vSphere 虚拟机',
            source_type='vsphere_vm',
            mode='manual',
            config={
                'connector': 'vsphere',
                'resource_type': 'vm',
                'target_ci_type_code': 'CLOUD_SERVER',
                'collection_enabled': True,
                'source_account': 'vcenter-prod',
                'host': 'vcenter.example.com',
                'username': 'administrator@vsphere.local',
                'auth_ref': 'SXDEVOPS_VSPHERE_PROD',
            },
        )
        captured_config = {}

        def fake_vsphere_fetch(config, resource_type):
            captured_config.update(config)
            self.assertEqual(resource_type, 'vm')
            return [{
                'vm': 'vm-runtime-001',
                'name': 'runtime-vsphere-vm-01',
                'power_state': 'poweredOn',
                'guest_ip': '10.2.2.8',
                'num_cpu': 4,
                'memory_mb': 8192,
                'cpu_used_mhz': 1280,
                'cpu_usage_percent': 16.0,
                'memory_used_gb': 3.25,
                'memory_usage_percent': 40.62,
                'disk_used_gb': 120,
                'disk_usage_percent': 30.0,
                '_metric_snapshots': [
                    {'metric': 'cpu_usage', 'value': 1280, 'unit': 'MHz', 'usage_percent': 16.0, 'source': 'vsphere_vm'},
                    {'metric': 'memory_usage', 'value': 3.25, 'unit': 'GB', 'usage_percent': 40.62, 'source': 'vsphere_vm'},
                    {'metric': 'disk_usage', 'value': 120, 'unit': 'GB', 'usage_percent': 30.0, 'source': 'vsphere_vm'},
                ],
                'business_line': 'core',
                'environment': 'prod',
                'owner': 'vmops',
            }]

        with patch('cmdb.collectors._fetch_vsphere_raw_items', side_effect=fake_vsphere_fetch) as vsphere_fetch:
            response = self.client.post(
                f'/api/cmdb/sync-jobs/{job.id}/run/',
                data=json.dumps({'runtime_credentials': {'password': 'Runtime#Secret123'}}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200, response.content)
        vsphere_fetch.assert_called_once()
        self.assertEqual(captured_config['password'], 'Runtime#Secret123')
        ci = ConfigItem.objects.get(name='runtime-vsphere-vm-01')
        self.assertEqual(ci.ci_type.code, 'VIRTUAL_MACHINE')
        self.assertEqual(ci.attributes['private_ip'], '10.2.2.8')
        self.assertNotIn('cpu_usage_percent', ci.attributes)
        self.assertNotIn('memory_usage_percent', ci.attributes)
        self.assertNotIn('disk_usage_percent', ci.attributes)
        self.assertEqual(CIResourceMetricSnapshot.objects.filter(ci=ci).count(), 3)
        latest_response = self.client.get('/api/cmdb/resource-metrics/latest/', {
            'ci_ids': str(ci.id),
            'metrics': 'cpu_usage,memory_usage,disk_usage',
        })
        self.assertEqual(latest_response.status_code, 200, latest_response.content)
        latest_metrics = {item['metric']: item for item in latest_response.json()}
        self.assertEqual(set(latest_metrics), {'cpu_usage', 'memory_usage', 'disk_usage'})
        self.assertEqual(float(latest_metrics['cpu_usage']['usage_percent']), 16.0)
        job.refresh_from_db()
        self.assertNotIn('password', job.config)
        self.assertNotIn('Runtime#Secret123', json.dumps(job.config, ensure_ascii=False))

    def test_sync_job_is_marked_running_before_source_collection(self):
        from unittest.mock import patch

        job = CISyncJob.objects.create(
            name='运行状态持久化测试',
            source_type='manual_import',
            mode='manual',
        )
        observed_statuses = []

        def fake_collect_items(current_job, request_data):
            current_job.refresh_from_db()
            observed_statuses.append(current_job.status)
            return []

        with patch('cmdb.views._items_for_sync_job', side_effect=fake_collect_items):
            response = self.client.post(
                f'/api/cmdb/sync-jobs/{job.id}/run/',
                data=json.dumps({}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(observed_statuses, ['running'])
        job.refresh_from_db()
        self.assertEqual(job.status, 'success')

    def test_vsphere_prometheus_node_exporter_overrides_guest_usage_metrics(self):
        from cmdb.collectors import collect_items_for_sync_job
        from cmdb.views import _sync_metric_snapshots_from_payload
        from ops.models import MetricDataSource

        ensure_builtin_cmdb()
        MetricDataSource.objects.create(
            name='CMDB 默认 Prometheus',
            provider='prometheus',
            config={'query_url': 'http://prometheus.internal:9090'},
            is_enabled=True,
            is_default=True,
        )
        gibibyte = 1024 * 1024 * 1024
        sample_timestamp = 1785632400
        job = CISyncJob.objects.create(
            name='vSphere Guest OS 真实指标',
            source_type='vsphere_vm',
            mode='manual',
            config={
                'connector': 'vsphere',
                'resource_type': 'vm',
                'target_ci_type_code': 'VIRTUAL_MACHINE',
                'prometheus_metrics_enabled': True,
                'raw_items': [{
                    'vm': 'vm-prometheus-001',
                    'name': 'prometheus-vm-01',
                    'guest_ip': '10.2.2.8',
                    'num_cpu': 4,
                    'memory_mb': 8192,
                    'cpu_usage_percent': 16.0,
                    'memory_used_gb': 3.25,
                    'memory_usage_percent': 40.62,
                    'disk_used_gb': 50,
                    'disk_usage_percent': 50.0,
                    '_metric_snapshots': [
                        {'metric': 'cpu_usage', 'value': 1280, 'unit': 'MHz', 'usage_percent': 16.0, 'source': 'vsphere_vm'},
                        {'metric': 'memory_usage', 'value': 3.25, 'unit': 'GB', 'usage_percent': 40.62, 'source': 'vsphere_vm'},
                        {'metric': 'disk_usage', 'value': 50, 'unit': 'GB', 'usage_percent': 50.0, 'source': 'vsphere_vm'},
                    ],
                }],
            },
        )

        class PrometheusResponse:
            status_code = 200

            def __init__(self, value):
                self.value = value

            def json(self):
                return {
                    'status': 'success',
                    'data': {
                        'resultType': 'vector',
                        'result': [{
                            'metric': {'instance': '10.2.2.8:9100'},
                            'value': [sample_timestamp, str(self.value)],
                        }],
                    },
                }

        def prometheus_get(_url, params=None, **_kwargs):
            query = str((params or {}).get('query') or '')
            if 'node_cpu_seconds_total' in query:
                return PrometheusResponse(23.5)
            if 'node_memory_MemTotal_bytes' in query:
                return PrometheusResponse(8 * gibibyte)
            if 'node_memory_MemFree_bytes' in query:
                return PrometheusResponse(1 * gibibyte)
            if 'node_memory_MemAvailable_bytes' in query:
                return PrometheusResponse(3 * gibibyte)
            if 'node_filesystem_size_bytes' in query:
                return PrometheusResponse(100 * gibibyte)
            if 'node_filesystem_free_bytes' in query:
                return PrometheusResponse(40 * gibibyte)
            if 'node_filesystem_avail_bytes' in query:
                return PrometheusResponse(35 * gibibyte)
            raise AssertionError(f'未识别的 PromQL: {query}')

        with patch('cmdb.prometheus_metrics.http_requests.get', side_effect=prometheus_get) as prometheus_request:
            payload = collect_items_for_sync_job(job)[0]

        self.assertEqual(prometheus_request.call_count, 7)
        attributes = payload['attributes']
        self.assertEqual(attributes['cpu_usage_percent'], 23.5)
        self.assertEqual(attributes['memory_used_gb'], 5.0)
        self.assertEqual(attributes['memory_free_gb'], 1.0)
        self.assertEqual(attributes['memory_available_gb'], 3.0)
        self.assertEqual(attributes['memory_usage_percent'], 62.5)
        self.assertEqual(attributes['disk_used_gb'], 60.0)
        self.assertEqual(attributes['root_disk_total_gb'], 100.0)
        self.assertEqual(attributes['root_disk_available_gb'], 35.0)
        self.assertEqual(attributes['disk_usage_percent'], 63.16)
        self.assertEqual(attributes['metric_collection_status'], 'ok')
        self.assertEqual(attributes['metric_collection_source'], 'prometheus_node_exporter')
        self.assertEqual(attributes['metric_datasource'], 'CMDB 默认 Prometheus')
        self.assertEqual(attributes['prometheus_target'], '10.2.2.8:9100')
        snapshots = {item['metric']: item for item in payload['_metric_snapshots']}
        self.assertEqual(set(snapshots), {'cpu_usage', 'memory_usage', 'disk_usage'})
        self.assertTrue(all(item['source'] == 'prometheus_node_exporter' for item in snapshots.values()))
        self.assertTrue(all(item['collected_at'] == '2026-08-02T01:00:00Z' for item in snapshots.values()))

        vm_type = CIType.objects.get(code='VIRTUAL_MACHINE')
        ci = ConfigItem.objects.create(name='prometheus-vm-01', ci_type=vm_type, attributes={})
        self.assertEqual(_sync_metric_snapshots_from_payload(ci, payload), 3)
        collected_at_values = set(CIResourceMetricSnapshot.objects.filter(ci=ci).values_list('collected_at', flat=True))
        self.assertEqual(len(collected_at_values), 1)
        self.assertEqual(next(iter(collected_at_values)).isoformat(), '2026-08-02T01:00:00+00:00')

    def test_vsphere_metrics_fall_back_when_prometheus_is_not_configured(self):
        from cmdb.collectors import collect_items_for_sync_job

        job = CISyncJob.objects.create(
            name='vSphere 指标回退',
            source_type='vsphere_vm',
            mode='manual',
            config={
                'connector': 'vsphere',
                'resource_type': 'vm',
                'target_ci_type_code': 'VIRTUAL_MACHINE',
                'prometheus_metrics_enabled': True,
                'raw_items': [{
                    'vm': 'vm-fallback-001',
                    'name': 'fallback-vm-01',
                    'guest_ip': '10.2.2.9',
                    'cpu_usage_percent': 16.0,
                    'memory_used_gb': 3.25,
                    'memory_usage_percent': 40.62,
                    'disk_used_gb': 50,
                    'disk_usage_percent': 50.0,
                    '_metric_snapshots': [
                        {'metric': 'cpu_usage', 'value': 1280, 'unit': 'MHz', 'usage_percent': 16.0, 'source': 'vsphere_vm'},
                        {'metric': 'memory_usage', 'value': 3.25, 'unit': 'GB', 'usage_percent': 40.62, 'source': 'vsphere_vm'},
                        {'metric': 'disk_usage', 'value': 50, 'unit': 'GB', 'usage_percent': 50.0, 'source': 'vsphere_vm'},
                    ],
                }],
            },
        )

        with patch('cmdb.prometheus_metrics.http_requests.get') as prometheus_request:
            payload = collect_items_for_sync_job(job)[0]

        prometheus_request.assert_not_called()
        attributes = payload['attributes']
        self.assertEqual(attributes['metric_collection_status'], 'fallback')
        self.assertEqual(attributes['metric_collection_source'], 'vsphere_vm')
        self.assertIn('未配置可用的 Prometheus 指标数据源', attributes['metric_collection_error'])
        self.assertEqual(attributes['cpu_usage_percent'], 16.0)
        self.assertEqual(attributes['memory_usage_percent'], 40.62)
        self.assertEqual(attributes['disk_usage_percent'], 50.0)
        self.assertTrue(all(item['source'] == 'vsphere_vm' for item in payload['_metric_snapshots']))

    def test_public_cloud_metrics_use_prometheus_selected_on_cloud_account(self):
        from cmdb.collectors import collect_items_for_sync_job
        from multicloud.models import CloudCredential
        from ops.models import MetricDataSource

        fallback_datasource = MetricDataSource.objects.create(
            name='Fallback Prometheus',
            provider='prometheus',
            config={'query_url': 'http://fallback.prometheus.internal:9090'},
            is_enabled=True,
            is_default=True,
        )
        selected_datasource = MetricDataSource.objects.create(
            name='Account Prometheus',
            provider='prometheus',
            config={'query_url': 'http://account.prometheus.internal:9090'},
            is_enabled=True,
        )
        credential = CloudCredential.objects.create(
            provider='aliyun',
            name='public-cloud-account',
            account_id='1234567890',
            access_key_id='ak',
            access_key_secret='sk',
            default_region='cn-hangzhou',
            tags={
                'prometheus_metrics_enabled': True,
                'metric_datasource_id': str(selected_datasource.id),
            },
        )
        job = CISyncJob.objects.create(
            name='public cloud real metrics',
            source_type='aliyun_ecs',
            mode='manual',
            config={
                'connector': 'aliyun',
                'resource_type': 'ecs',
                'target_ci_type_code': 'CLOUD_SERVER',
                'cloud_account_id': str(credential.id),
                # The cloud account setting must override these legacy task settings.
                'prometheus_metrics_enabled': False,
                'metric_datasource_id': str(fallback_datasource.id),
                'raw_items': [{
                    'InstanceId': 'i-prometheus-001',
                    'InstanceName': 'public-cloud-vm-01',
                    'RegionId': 'cn-hangzhou',
                    'PrivateIpAddress': {'IpAddress': ['10.9.8.7']},
                    'Cpu': 4,
                    'Memory': 8192,
                    'Status': 'Running',
                    '_metric_snapshots': [{
                        'metric': 'cpu_usage',
                        'value': 12,
                        'unit': '%',
                        'usage_percent': 12,
                        'source': 'aliyun_cloudmonitor',
                    }],
                }],
            },
        )
        gibibyte = 1024 * 1024 * 1024
        timestamp = 1785632400
        values = {
            'node_cpu_seconds_total': 25,
            'node_memory_MemTotal_bytes': 8 * gibibyte,
            'node_memory_MemFree_bytes': 1 * gibibyte,
            'node_memory_MemAvailable_bytes': 3 * gibibyte,
            'node_filesystem_size_bytes': 100 * gibibyte,
            'node_filesystem_free_bytes': 40 * gibibyte,
            'node_filesystem_avail_bytes': 35 * gibibyte,
        }

        def prometheus_query(_client, query):
            matched_value = next(value for metric, value in values.items() if metric in query)
            return [{'metric': {'instance': '10.9.8.7:9100'}, 'value': [timestamp, str(matched_value)]}]

        with patch('cmdb.prometheus_metrics._prometheus_query', side_effect=prometheus_query) as query_request:
            payload = collect_items_for_sync_job(job)[0]

        self.assertEqual(query_request.call_count, 7)
        attributes = payload['attributes']
        snapshots = {item['metric']: item for item in payload['_metric_snapshots']}
        self.assertEqual(attributes.get('metric_collection_source'), 'prometheus_node_exporter', payload)
        self.assertEqual(attributes.get('metric_datasource'), 'Account Prometheus', payload)
        self.assertEqual(snapshots['cpu_usage']['usage_percent'], 25.0)
        self.assertEqual(snapshots['memory_usage']['usage_percent'], 62.5)
        self.assertEqual(snapshots['disk_usage']['usage_percent'], 63.16)

    def test_refresh_current_page_resource_waterline_only_updates_requested_items(self):
        from unittest.mock import patch

        ensure_builtin_cmdb()
        vm_type = CIType.objects.get(code='VIRTUAL_MACHINE')
        ci = ConfigItem.objects.create(
            name='current-page-vm-01',
            ci_type=vm_type,
            business_line='core',
            environment='prod',
            admin_user='vmops',
            attributes={'cpu': 4, 'memory_gb': 8},
        )
        CISourceMapping.objects.create(
            ci=ci,
            source_type='vsphere_vm',
            source_account='example-vsphere',
            source_region='example-DC',
            source_unique_id='vm-current-001',
            last_seen_at=timezone.now(),
        )
        job = CISyncJob.objects.create(
            name='刷新当前页 vSphere 水位',
            source_type='vsphere_vm',
            mode='manual',
            config={
                'connector': 'vsphere',
                'resource_type': 'vm',
                'target_ci_type_code': 'VIRTUAL_MACHINE',
                'collection_enabled': True,
                'source_account': 'example-vsphere',
                'host': 'vcenter.example.com',
                'username': 'administrator@vsphere.local',
                'auth_ref': 'SXDEVOPS_VSPHERE_PROD',
            },
        )

        raw_items = [
            {
                'vm': 'vm-current-001',
                'name': 'current-page-vm-01',
                'power_state': 'poweredOn',
                'guest_ip': '10.2.2.8',
                'num_cpu': 4,
                'memory_mb': 8192,
                'provisioned_gb': 120,
                'committed_gb': 60,
                'cpu_used_mhz': 1280,
                'cpu_usage_percent': 16.0,
                'memory_used_gb': 3.25,
                'memory_usage_percent': 40.62,
                'disk_used_gb': 60,
                'disk_usage_percent': 50.0,
                '_metric_snapshots': [
                    {'metric': 'cpu_usage', 'value': 1280, 'unit': 'MHz', 'usage_percent': 16.0, 'source': 'vsphere_vm'},
                    {'metric': 'memory_usage', 'value': 3.25, 'unit': 'GB', 'usage_percent': 40.62, 'source': 'vsphere_vm'},
                    {'metric': 'disk_usage', 'value': 60, 'unit': 'GB', 'usage_percent': 50.0, 'source': 'vsphere_vm'},
                ],
                'datacenter': 'example-DC',
            },
            {
                'vm': 'vm-current-002',
                'name': 'not-current-page-vm-02',
                'power_state': 'poweredOn',
                'guest_ip': '10.2.2.9',
                'num_cpu': 4,
                'memory_mb': 8192,
                'datacenter': 'example-DC',
            },
        ]

        with patch('cmdb.collectors._fetch_vsphere_raw_items', return_value=raw_items):
            response = self.client.post(
                '/api/cmdb/resource-metrics/refresh-current-page/',
                data=json.dumps({'ci_ids': [ci.id]}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['requested_count'], 1)
        self.assertEqual(payload['refreshed_count'], 1)
        self.assertEqual(payload['summary'].get('metric_snapshot'), 3)
        self.assertEqual(len(payload['latest_metrics']), 3)
        self.assertEqual(CIResourceMetricSnapshot.objects.filter(ci=ci).count(), 3)
        ci.refresh_from_db()
        self.assertNotIn('cpu_usage_percent', ci.attributes)
        self.assertFalse(ConfigItem.objects.filter(name='not-current-page-vm-02').exists())
        job.refresh_from_db()
        self.assertNotIn('archive_candidate', job.summary)

    def test_vsphere_full_sync_marks_missing_vm_offline(self):
        ensure_builtin_cmdb()
        vm_type = CIType.objects.get(code='VIRTUAL_MACHINE')
        missing_ci = ConfigItem.objects.create(
            name='test-git14',
            ci_type=vm_type,
            business_line='core',
            environment='prod',
            admin_user='vmops',
            status='active',
            attributes={
                'source_unique_id': 'vm-test-git14',
                'source_account': 'example-vsphere',
                'source_region': '10.197.0.10',
            },
        )
        missing_mapping = CISourceMapping.objects.create(
            ci=missing_ci,
            source_type='vsphere_vm',
            source_account='example-vsphere',
            source_region='10.197.0.10',
            source_unique_id='vm-test-git14',
            last_seen_at=timezone.now() - timezone.timedelta(days=1),
        )
        CIArchiveCandidate.objects.create(
            ci=missing_ci,
            source_type='vsphere_vm',
            reason='上一次全量同步未发现来源资源 vm-test-git14',
            last_seen_at=missing_mapping.last_seen_at,
            status='pending',
        )
        job = CISyncJob.objects.create(
            name='vSphere 全量同步缺失 VM 下线',
            source_type='vsphere_vm',
            mode='manual',
            config={
                'source_account': 'example-vsphere',
                'source_region': 'example-DC',
                'items': [
                    {
                        'ci_type_name': '虚拟机',
                        'ci_type_code': 'VIRTUAL_MACHINE',
                        'name': 'current-vsphere-vm-01',
                        'source_type': 'vsphere_vm',
                        'source_account': 'example-vsphere',
                        'source_region': 'example-DC',
                        'source_unique_id': 'vm-current-001',
                        'business_line': 'core',
                        'environment': 'prod',
                        'admin_user': 'vmops',
                        'attributes': {
                            'instance_id': 'vm-current-001',
                            'private_ip': '10.2.2.8',
                            'cpu': 4,
                            'memory_gb': 8,
                        },
                    },
                ],
            },
        )

        response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/run/', {}, content_type='application/json')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['summary'].get('archive_candidate'), 1, payload)
        self.assertTrue(ConfigItem.objects.filter(name='current-vsphere-vm-01', status='active').exists())
        self.assertEqual(CIArchiveCandidate.objects.filter(ci=missing_ci, source_type='vsphere_vm', status='pending').count(), 1)
        missing_mapping.refresh_from_db()
        self.assertEqual(missing_mapping.sync_status, 'missing')
        missing_ci.refresh_from_db()
        self.assertEqual(missing_ci.status, 'offline')
        self.assertEqual(missing_ci.attributes.get('sync_status'), 'missing')
        self.assertEqual(missing_ci.attributes.get('missing_source_unique_id'), 'vm-test-git14')

    def test_vsphere_vm_without_guest_ip_still_registers(self):
        from unittest.mock import patch

        ensure_builtin_cmdb()
        job = CISyncJob.objects.create(
            name='无 guest IP 的 vSphere 虚拟机采集',
            source_type='vsphere_vm',
            mode='manual',
            config={
                'connector': 'vsphere',
                'resource_type': 'vm',
                'target_ci_type_code': 'CLOUD_SERVER',
                'collection_enabled': True,
                'source_account': 'vcenter-prod',
                'host': 'vcenter.example.com',
                'username': 'administrator@vsphere.local',
                'auth_ref': 'SXDEVOPS_VSPHERE_PROD',
            },
        )

        with patch('cmdb.collectors._fetch_vsphere_raw_items', return_value=[{
            'vm': 'vm-no-ip-001',
            'name': 'vsphere-no-ip-01',
            'power_state': 'poweredOff',
            'guest_ip': '',
            'num_cpu': 2,
            'memory_mb': 4096,
            'business_line': 'core',
            'environment': 'prod',
            'owner': 'vmops',
        }]):
            response = self.client.post(
                f'/api/cmdb/sync-jobs/{job.id}/run/',
                data=json.dumps({'runtime_credentials': {'password': 'Runtime#Secret123'}}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['summary'].get('create'), 1, payload)
        self.assertNotIn('fail', payload['summary'], payload)
        ci = ConfigItem.objects.get(name='vsphere-no-ip-01')
        self.assertEqual(ci.ci_type.code, 'VIRTUAL_MACHINE')
        self.assertIn(ci.attributes.get('private_ip'), (None, ''))
        self.assertEqual(ci.status, 'stopped')
        self.assertEqual(ci.attributes.get('instance_status'), 'Stopped')
        self.assertTrue(CISourceMapping.objects.filter(source_type='vsphere_vm', source_unique_id='vm-no-ip-001', ci=ci).exists())

    def test_vsphere_capacity_summary_does_not_use_endpoint_as_region(self):
        from cmdb.collectors import _vsphere_capacity_summary_item

        payload = _vsphere_capacity_summary_item(
            {
                '__sxdevops_kind': 'vsphere_capacity_summary',
                'name': 'example-vsphere 资源统计',
                'source_account': 'example-vsphere',
                'source_region': '10.197.0.10',
                'endpoint': '10.197.0.10',
                'source_unique_id': 'vsphere-summary:example-vsphere',
                'host_count': 10,
                'vm_count': 336,
            },
            {
                'source_type': 'vsphere_vm',
                'source_account': 'example-vsphere',
                'source_region': '10.197.0.10',
                'region_id': '10.197.0.10',
                'host': '10.197.0.10',
            },
        )

        self.assertEqual(payload['source_region'], '')
        self.assertEqual(payload['attributes']['endpoint'], '10.197.0.10')

    def test_vsphere_host_registers_as_physical_machine(self):
        from unittest.mock import patch

        ensure_builtin_cmdb()
        job = CISyncJob.objects.create(
            name='vSphere 物理宿主机采集',
            source_type='vsphere_vm',
            mode='manual',
            config={
                'connector': 'vsphere',
                'resource_type': 'vm',
                'target_ci_type_code': 'VIRTUAL_MACHINE',
                'collection_enabled': True,
                'source_account': 'example-vsphere',
                'host': 'vcenter.example.com',
                'username': 'administrator@vsphere.local',
                'auth_ref': 'SXDEVOPS_VSPHERE_PROD',
            },
        )

        with patch('cmdb.collectors._fetch_vsphere_raw_items', return_value=[{
            '__sxdevops_kind': 'vsphere_host',
            'host_id': 'host-123',
            'name': 'esxi-01.example.local',
            'management_ip': '10.197.0.21',
            'datacenter': 'example-DC',
            'cluster': 'Prod-Cluster',
            'vendor': 'Dell Inc.',
            'model': 'PowerEdge R750',
            'serial_number': 'CN-ESXI-001',
            'cpu_cores': 64,
            'cpu_thread_count': 128,
            'cpu_package_count': 2,
            'cpu_mhz': 2600,
            'cpu_total_mhz': 166400,
            'cpu_used_mhz': 38200,
            'cpu_usage_percent': 22.96,
            'memory_gb': 1024,
            'memory_used_gb': 416,
            'memory_usage_percent': 40.62,
            'connection_state': 'connected',
            'power_state': 'poweredOn',
            'maintenance_mode': False,
            'esxi_version': '8.0.2',
            'esxi_build': '22380479',
            'business_line': 'infra',
            'environment': 'prod',
            'owner': 'vmops',
        }]):
            response = self.client.post(
                f'/api/cmdb/sync-jobs/{job.id}/run/',
                data=json.dumps({'runtime_credentials': {'password': 'Runtime#Secret123'}}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['summary'].get('create'), 1, payload)
        ci = ConfigItem.objects.get(name='esxi-01.example.local')
        self.assertEqual(ci.ci_type.code, 'IDC_SERVER')
        self.assertEqual(ci.ci_type.name, '物理机')
        self.assertEqual(ci.attributes['asset_sn'], 'CN-ESXI-001')
        self.assertEqual(ci.attributes['private_ip'], '10.197.0.21')
        self.assertEqual(ci.attributes['vendor'], 'Dell Inc.')
        self.assertEqual(ci.attributes['model'], 'PowerEdge R750')
        self.assertEqual(ci.attributes['cpu'], 64)
        self.assertEqual(ci.attributes['memory_gb'], 1024.0)
        self.assertEqual(ci.attributes['datacenter'], 'example-DC')
        self.assertEqual(ci.attributes['cluster'], 'Prod-Cluster')
        self.assertEqual(ci.attributes['esxi_version'], '8.0.2')
        metric_snapshots = list(
            CIResourceMetricSnapshot.objects.filter(ci=ci).order_by('metric')
        )
        self.assertEqual([item.metric for item in metric_snapshots], ['cpu_usage', 'memory_usage'])
        self.assertEqual([item.source for item in metric_snapshots], ['vsphere_host', 'vsphere_host'])
        self.assertEqual(metric_snapshots[0].usage_percent, Decimal('22.96'))
        self.assertEqual(metric_snapshots[1].usage_percent, Decimal('40.62'))
        self.assertFalse(CIResourceMetricSnapshot.objects.filter(ci=ci, metric='disk_usage').exists())
        detail_response = self.client.get(f'/api/cmdb/config-items/{ci.id}/')
        self.assertEqual(detail_response.status_code, 200, detail_response.content)
        detail_metrics = detail_response.json()['latest_metric_snapshots']
        self.assertEqual([item['metric'] for item in detail_metrics], ['memory_usage', 'cpu_usage'])
        self.assertTrue(all(item['source'] == 'vsphere_host' for item in detail_metrics))
        self.assertTrue(CISourceMapping.objects.filter(source_type='vsphere_vm', source_account='example-vsphere', source_unique_id='host:host-123', ci=ci).exists())

    def test_vsphere_cloud_account_url_is_normalized_for_collection(self):
        from multicloud.models import CloudCredential
        from cmdb.collectors import _runtime_collection_config

        credential = CloudCredential.objects.create(
            provider='vsphere',
            name='example-vsphere',
            account_id='https://10.197.0.10/',
            account_name='private-cloud-prod',
            auth_mode='secret',
            access_key_id='administrator@vsphere.local',
            access_key_secret='secret',
            default_region='private-cloud-prod',
        )

        config = _runtime_collection_config({'cloud_account_id': credential.id})

        self.assertEqual(config['host'], '10.197.0.10')
        self.assertEqual(config['vcenter_host'], '10.197.0.10')
        self.assertEqual(config['endpoint'], '10.197.0.10')
        self.assertEqual(config['port'], 443)

    def test_vsphere_invalid_login_returns_readable_collection_error(self):
        from unittest.mock import patch
        from cmdb.collectors import _fetch_vsphere_raw_items

        class FakeInvalidLogin(Exception):
            msg = 'Cannot complete login due to an incorrect user name or password.'

        class FakeFault:
            InvalidLogin = FakeInvalidLogin

        class FakeVim:
            fault = FakeFault
            VirtualMachine = object

        class FakeVmodl:
            MethodFault = Exception

        class FakePyVmomi:
            vim = FakeVim
            vmodl = FakeVmodl

        class FakeConnect:
            @staticmethod
            def SmartConnect(**kwargs):
                raise FakeInvalidLogin()

        def fake_optional_import(module_name, install_hint):
            if module_name == 'pyVim.connect':
                return FakeConnect
            if module_name == 'pyVmomi':
                return FakePyVmomi
            raise AssertionError(module_name)

        with patch('cmdb.collectors._optional_import', side_effect=fake_optional_import):
            with self.assertRaisesRegex(ValueError, 'vSphere 账号认证失败'):
                _fetch_vsphere_raw_items({
                    'host': 'https://10.197.0.10/',
                    'username': 'sx-readonly',
                    'password': 'bad-password',
                }, 'vm')

    def test_failed_sync_record_can_be_retried_individually(self):
        job = CISyncJob.objects.create(name='手动导入同步', source_type='manual_import')
        failed_record = CISyncRecord.objects.create(
            job=job,
            action='fail',
            status='failed',
            source_unique_id='retry-001',
            error_message='temporary validation error',
            after={
                'ci_type_name': '云主机(ECS)',
                'ci_type_code': 'CLOUD_SERVER',
                'name': 'ecs-retry-01',
                'source_type': 'manual_import',
                'source_unique_id': 'retry-001',
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'ops-owner',
                'attributes': {
                    'instance_id': 'retry-001',
                    'private_ip': '10.2.1.9',
                },
            },
        )

        response = self.client.post(f'/api/cmdb/sync-records/{failed_record.id}/retry/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['summary']['create'], 1)
        ci = ConfigItem.objects.get(name='ecs-retry-01')
        self.assertEqual(ci.attributes['source_unique_id'], 'retry-001')
        self.assertTrue(
            CISyncRecord.objects.filter(
                job=job,
                source_unique_id='retry-001',
                status='success',
            ).exists()
        )
        failed_record.refresh_from_db()
        retry_record = failed_record.retry_record
        self.assertEqual(failed_record.retry_status, 'success')
        self.assertEqual(failed_record.retry_count, 1)
        self.assertEqual(failed_record.retried_by, 'cmdb-admin')
        self.assertEqual(failed_record.retry_result, 'create')
        self.assertIsNotNone(failed_record.last_retried_at)
        self.assertIsNotNone(retry_record)
        self.assertEqual(retry_record.status, 'success')
        detail_response = self.client.get(f'/api/cmdb/sync-records/{failed_record.id}/')
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()['retry_status'], 'success')

    def test_failed_sync_records_list_exposes_job_context_for_governance(self):
        failed_job = CISyncJob.objects.create(name='治理失败同步', source_type='manual_import')
        success_job = CISyncJob.objects.create(name='治理成功同步', source_type='manual_import')
        failed_record = CISyncRecord.objects.create(
            job=failed_job,
            action='fail',
            status='failed',
            source_unique_id='governance-failed-001',
            error_message='missing required owner',
            after={'name': 'governance-failed-ecs-01', 'source_unique_id': 'governance-failed-001'},
        )
        CISyncRecord.objects.create(
            job=success_job,
            action='create',
            status='success',
            source_unique_id='governance-success-001',
            after={'name': 'governance-success-ecs-01'},
        )

        response = self.client.get('/api/cmdb/sync-records/', {'status': 'failed', 'page_size': 100})

        self.assertEqual(response.status_code, 200, response.content)
        results = response.json()['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], failed_record.id)
        self.assertEqual(results[0]['job_name'], '治理失败同步')
        self.assertEqual(results[0]['job_source_type'], 'manual_import')
        self.assertEqual(results[0]['source_unique_id'], 'governance-failed-001')
        self.assertEqual(results[0]['error_message'], 'missing required owner')

    def test_conflict_sync_record_can_be_resolved_to_existing_ci(self):
        ci_type = _ci_type('冲突治理云主机', code='SYNC_RESOLVE_SERVER')
        target = ConfigItem.objects.create(
            name='resolve-target-ecs-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'ip_address': '10.9.0.1'},
        )
        job = CISyncJob.objects.create(name='冲突治理同步', source_type='manual_import')
        record = CISyncRecord.objects.create(
            job=job,
            action='conflict',
            status='failed',
            source_unique_id='resolve-source-001',
            error_message='source identity requires manual binding',
            after={
                'ci_type_name': '冲突治理云主机',
                'ci_type_code': 'SYNC_RESOLVE_SERVER',
                'name': 'resolve-target-ecs-01',
                'source_type': 'manual_import',
                'source_account': 'prod-account',
                'source_region': 'cn-hangzhou',
                'source_unique_id': 'resolve-source-001',
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'ops',
            },
        )

        response = self.client.post(
            f'/api/cmdb/sync-records/{record.id}/resolve-to-ci/',
            {'ci_id': target.id, 'note': 'confirmed source identity'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        mapping = CISourceMapping.objects.get(source_type='manual_import', source_unique_id='resolve-source-001')
        self.assertEqual(mapping.ci, target)
        self.assertEqual(mapping.source_account, 'prod-account')
        self.assertEqual(mapping.source_region, 'cn-hangzhou')
        self.assertEqual(mapping.sync_status, 'success')
        self.assertEqual(mapping.raw_payload['resolved_from_sync_record'], record.id)
        record.refresh_from_db()
        self.assertEqual(record.status, 'resolved')
        self.assertEqual(record.ci, target)
        self.assertEqual(record.retry_status, 'success')
        self.assertEqual(record.retry_result, 'resolve_to_ci')
        self.assertEqual(record.retry_count, 1)
        self.assertTrue(CIChangeLog.objects.filter(ci=target, action='source_mapping_create', source='source_mapping').exists())
        failed_response = self.client.get('/api/cmdb/sync-records/', {'status': 'failed', 'page_size': 100})
        self.assertEqual(failed_response.status_code, 200)
        self.assertEqual(failed_response.json()['results'], [])

    def test_conflict_sync_record_requires_replace_existing_scope_mapping(self):
        ci_type = _ci_type('替换映射云主机', code='SYNC_REPLACE_SERVER')
        target = ConfigItem.objects.create(
            name='replace-target-ecs-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            status='active',
        )
        old_mapping = CISourceMapping.objects.create(
            ci=target,
            source_type='manual_import',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='old-source-001',
            sync_status='success',
        )
        job = CISyncJob.objects.create(name='替换映射同步', source_type='manual_import')
        record = CISyncRecord.objects.create(
            job=job,
            action='conflict',
            status='failed',
            source_unique_id='new-source-001',
            error_message='target has another source id',
            after={
                'ci_type_name': '替换映射云主机',
                'ci_type_code': 'SYNC_REPLACE_SERVER',
                'name': 'replace-target-ecs-01',
                'source_type': 'manual_import',
                'source_account': 'prod-account',
                'source_region': 'cn-hangzhou',
                'source_unique_id': 'new-source-001',
            },
        )

        denied = self.client.post(
            f'/api/cmdb/sync-records/{record.id}/resolve-to-ci/',
            {'ci_id': target.id},
            content_type='application/json',
        )
        self.assertEqual(denied.status_code, 400)
        self.assertTrue(CISourceMapping.objects.filter(id=old_mapping.id).exists())

        allowed = self.client.post(
            f'/api/cmdb/sync-records/{record.id}/resolve-to-ci/',
            {'ci_id': target.id, 'replace_existing': True, 'note': 'replace stale mapping'},
            content_type='application/json',
        )

        self.assertEqual(allowed.status_code, 200, allowed.content)
        self.assertFalse(CISourceMapping.objects.filter(id=old_mapping.id).exists())
        self.assertTrue(CISourceMapping.objects.filter(ci=target, source_unique_id='new-source-001').exists())
        record.refresh_from_db()
        self.assertEqual(record.status, 'resolved')
        self.assertTrue(CIChangeLog.objects.filter(ci=target, action='source_mapping_delete', source='source_mapping').exists())
        self.assertTrue(CIChangeLog.objects.filter(ci=target, action='source_mapping_create', source='source_mapping').exists())

    def test_conflict_sync_record_requires_rebind_when_source_identity_belongs_to_other_ci(self):
        ci_type = _ci_type('改绑映射云主机', code='SYNC_REBIND_SERVER')
        old_ci = ConfigItem.objects.create(name='old-bound-ecs-01', ci_type=ci_type, status='active')
        target = ConfigItem.objects.create(name='new-bound-ecs-01', ci_type=ci_type, status='active')
        mapping = CISourceMapping.objects.create(
            ci=old_ci,
            source_type='manual_import',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='rebind-source-001',
            sync_status='success',
        )
        job = CISyncJob.objects.create(name='改绑映射同步', source_type='manual_import')
        record = CISyncRecord.objects.create(
            job=job,
            action='conflict',
            status='failed',
            source_unique_id='rebind-source-001',
            error_message='source belongs to old ci',
            after={
                'ci_type_name': '改绑映射云主机',
                'ci_type_code': 'SYNC_REBIND_SERVER',
                'name': 'new-bound-ecs-01',
                'source_type': 'manual_import',
                'source_account': 'prod-account',
                'source_region': 'cn-hangzhou',
                'source_unique_id': 'rebind-source-001',
            },
        )

        denied = self.client.post(
            f'/api/cmdb/sync-records/{record.id}/resolve-to-ci/',
            {'ci_id': target.id},
            content_type='application/json',
        )
        self.assertEqual(denied.status_code, 400)
        mapping.refresh_from_db()
        self.assertEqual(mapping.ci, old_ci)

        allowed = self.client.post(
            f'/api/cmdb/sync-records/{record.id}/resolve-to-ci/',
            {'ci_id': target.id, 'rebind': True, 'note': 'manual rebind'},
            content_type='application/json',
        )

        self.assertEqual(allowed.status_code, 200, allowed.content)
        mapping.refresh_from_db()
        self.assertEqual(mapping.ci, target)
        record.refresh_from_db()
        self.assertEqual(record.status, 'resolved')
        self.assertTrue(CIChangeLog.objects.filter(ci=target, action='source_mapping_update', source='source_mapping').exists())

    def test_sync_job_retry_failed_updates_original_retry_status(self):
        job = CISyncJob.objects.create(name='批量失败重试', source_type='manual_import')
        failed_record = CISyncRecord.objects.create(
            job=job,
            action='fail',
            status='failed',
            source_unique_id='retry-job-001',
            error_message='temporary validation error',
            after={
                'ci_type_name': '云主机(ECS)',
                'ci_type_code': 'CLOUD_SERVER',
                'name': 'ecs-retry-job-01',
                'source_type': 'manual_import',
                'source_unique_id': 'retry-job-001',
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'ops-owner',
                'attributes': {'instance_id': 'retry-job-001', 'private_ip': '10.2.1.10'},
            },
        )

        response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/retry-failed/')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['summary'].get('create'), 1, response.json())
        failed_record.refresh_from_db()
        self.assertEqual(failed_record.retry_status, 'success')
        self.assertEqual(failed_record.retry_count, 1)
        self.assertEqual(failed_record.retry_result, 'create')
        self.assertIsNotNone(failed_record.retry_record)
        self.assertEqual(failed_record.retry_record.source_unique_id, 'retry-job-001')

    def test_sync_job_retry_failed_skips_already_successful_retries(self):
        job = CISyncJob.objects.create(name='跳过已修复失败同步', source_type='manual_import')
        retry_record = CISyncRecord.objects.create(
            job=job,
            action='create',
            status='success',
            source_unique_id='retry-already-ok',
            after={'name': 'already-fixed'},
        )
        already_fixed = CISyncRecord.objects.create(
            job=job,
            action='fail',
            status='failed',
            source_unique_id='retry-already-ok',
            error_message='previously fixed',
            retry_status='success',
            retry_count=1,
            retry_record=retry_record,
            retry_result='create',
            after={
                'ci_type_name': '云主机(ECS)',
                'ci_type_code': 'CLOUD_SERVER',
                'name': 'ecs-already-fixed',
                'source_type': 'manual_import',
                'source_unique_id': 'retry-already-ok',
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'ops-owner',
                'attributes': {'instance_id': 'retry-already-ok', 'private_ip': '10.2.1.11'},
            },
        )
        pending_failed = CISyncRecord.objects.create(
            job=job,
            action='fail',
            status='failed',
            source_unique_id='retry-pending-001',
            error_message='temporary validation error',
            after={
                'ci_type_name': '云主机(ECS)',
                'ci_type_code': 'CLOUD_SERVER',
                'name': 'ecs-retry-pending-01',
                'source_type': 'manual_import',
                'source_unique_id': 'retry-pending-001',
                'business_line': 'core',
                'environment': 'prod',
                'admin_user': 'ops-owner',
                'attributes': {'instance_id': 'retry-pending-001', 'private_ip': '10.2.1.12'},
            },
        )

        response = self.client.post(f'/api/cmdb/sync-jobs/{job.id}/retry-failed/')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['summary']['create'], 1)
        self.assertEqual(payload['summary']['skipped'], 1)
        already_fixed.refresh_from_db()
        pending_failed.refresh_from_db()
        self.assertEqual(already_fixed.retry_count, 1)
        self.assertEqual(already_fixed.retry_record_id, retry_record.id)
        self.assertEqual(pending_failed.retry_status, 'success')
        self.assertEqual(pending_failed.retry_count, 1)
        self.assertEqual(pending_failed.retry_record.source_unique_id, 'retry-pending-001')
        self.assertTrue(ConfigItem.objects.filter(name='ecs-retry-pending-01').exists())
        self.assertFalse(ConfigItem.objects.filter(name='ecs-already-fixed').exists())

    def test_sync_record_retry_rejects_non_failed_record(self):
        job = CISyncJob.objects.create(name='手动导入同步', source_type='manual_import')
        success_record = CISyncRecord.objects.create(
            job=job,
            action='skip',
            status='success',
            source_unique_id='retry-skip-001',
            after={'name': 'already-ok'},
        )

        response = self.client.post(f'/api/cmdb/sync-records/{success_record.id}/retry/')

        self.assertEqual(response.status_code, 400)
        self.assertIn('只能重试失败的同步记录', response.json()['detail'])

    def test_config_item_bulk_import_dry_run_does_not_write_data(self):
        response = self.client.post(
            '/api/cmdb/config-items/bulk-import/',
            {
                'dry_run': True,
                'source_type': 'manual_import',
                'items': [
                    {
                        'ci_type_name': '云主机(ECS)',
                        'ci_type_code': 'CLOUD_SERVER',
                        'name': 'bulk-preview-ecs-01',
                        'source_unique_id': 'bulk-preview-001',
                        'business_line': 'core',
                        'environment': 'prod',
                        'admin_user': 'ops',
                        'attributes': {
                            'instance_id': 'bulk-preview-001',
                            'private_ip': '10.3.1.10',
                            'cpu': 4,
                        },
                    }
                ],
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['dry_run'])
        self.assertEqual(payload['summary']['create'], 1)
        self.assertFalse(ConfigItem.objects.filter(name='bulk-preview-ecs-01').exists())
        self.assertFalse(CISyncJob.objects.filter(name='资源台账批量导入').exists())

    def test_config_item_bulk_import_accepts_csv_and_records_job(self):
        csv_text = (
            'ci_type_name,ci_type_code,name,source_unique_id,business_line,department,environment,admin_user,instance_id,private_ip,cpu,tags\n'
            '云主机(ECS),CLOUD_SERVER,bulk-csv-ecs-01,bulk-csv-001,core,基础架构部,prod,ops,bulk-csv-001,10.3.1.11,8,source:csv;team:core\n'
        )

        response = self.client.post(
            '/api/cmdb/config-items/bulk-import/',
            {
                'format': 'csv',
                'source_type': 'csv_import',
                'name': 'CSV 台账导入',
                'text': csv_text,
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['dry_run'])
        self.assertEqual(payload['summary']['create'], 1)
        ci = ConfigItem.objects.get(name='bulk-csv-ecs-01')
        self.assertEqual(ci.business_line, 'core')
        self.assertEqual(ci.attributes['department'], '基础架构部')
        self.assertEqual(ci.attributes['instance_id'], 'bulk-csv-001')
        self.assertEqual(ci.attributes['private_ip'], '10.3.1.11')
        self.assertEqual(ci.attributes['cpu'], 8)
        self.assertTrue(ci.tags.filter(name='csv', category='source').exists())
        self.assertTrue(ci.tags.filter(name='core', category='team').exists())
        self.assertTrue(CISourceMapping.objects.filter(ci=ci, source_type='csv_import', source_unique_id='bulk-csv-001').exists())
        job = CISyncJob.objects.get(name='CSV 台账导入')
        self.assertEqual(job.mode, 'import')
        self.assertEqual(job.status, 'success')

    def test_config_item_export_returns_filtered_csv_with_dynamic_fields(self):
        ci_type = _ci_type('导出云主机', code='EXPORT_CLOUD_SERVER')
        CIField.objects.create(
            ci_type=ci_type,
            name='私网 IP',
            code='private_ip',
            field_type='ip',
            is_display=True,
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='CPU',
            code='cpu',
            field_type='integer',
            is_display=True,
        )
        ConfigItem.objects.create(
            name='export-ecs-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={
                'private_ip': '10.4.1.10',
                'cpu': 4,
            },
        )
        CISourceMapping.objects.create(
            ci=ConfigItem.objects.get(name='export-ecs-01'),
            source_type='aliyun_ecs',
            source_account='prod-account',
            source_region='cn-hangzhou',
            source_unique_id='export-001',
        )
        ConfigItem.objects.create(
            name='export-ecs-02',
            ci_type=ci_type,
            business_line='shared',
            environment='test',
            admin_user='ops',
            status='active',
            attributes={'private_ip': '10.4.1.11', 'cpu': 2},
        )

        response = self.client.get('/api/cmdb/config-items/export/', {'business_line': 'core'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        content = response.content.decode('utf-8-sig')
        self.assertIn('模型,名称,业务线,环境,状态,负责人,部门', content)
        self.assertIn('私网 IP,CPU', content)
        self.assertIn('export-ecs-01', content)
        self.assertIn('10.4.1.10', content)
        self.assertIn('aliyun_ecs', content)
        self.assertIn('prod-account', content)
        self.assertIn('cn-hangzhou', content)
        self.assertIn('export-001', content)
        self.assertNotIn('export-ecs-02', content)

    def test_config_item_export_returns_only_selected_items(self):
        ci_type = _ci_type('批量导出云主机', code='BULK_EXPORT_CLOUD_SERVER')
        selected = ConfigItem.objects.create(name='selected-export-ecs-01', ci_type=ci_type)
        ConfigItem.objects.create(name='unselected-export-ecs-02', ci_type=ci_type)

        response = self.client.get('/api/cmdb/config-items/export/', {'ids': str(selected.id)})

        self.assertEqual(response.status_code, 200, response.content)
        content = response.content.decode('utf-8-sig')
        self.assertIn('selected-export-ecs-01', content)
        self.assertNotIn('unselected-export-ecs-02', content)

    def test_config_item_export_splits_multiple_models_into_zip(self):
        server_type = _ci_type('导出服务器', code='EXPORT_SERVER')
        database_type = _ci_type('导出数据库', code='EXPORT_DATABASE')
        server = ConfigItem.objects.create(name='multi-export-server-01', ci_type=server_type)
        database = ConfigItem.objects.create(name='multi-export-database-01', ci_type=database_type)

        response = self.client.get('/api/cmdb/config-items/export/', {'ids': f'{server.id},{database.id}'})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response['Content-Type'], 'application/zip')
        with ZipFile(io.BytesIO(response.content)) as archive:
            self.assertIn('EXPORT_SERVER.csv', archive.namelist())
            self.assertIn('EXPORT_DATABASE.csv', archive.namelist())

    def test_config_item_import_template_returns_model_fields(self):
        ci_type = _ci_type('模板云主机', code='TEMPLATE_CLOUD_SERVER')
        CIField.objects.create(
            ci_type=ci_type,
            name='私网 IP',
            code='private_ip',
            field_type='ip',
            required=True,
            is_display=True,
        )
        CIField.objects.create(
            ci_type=ci_type,
            name='CPU',
            code='cpu',
            field_type='integer',
            required=True,
            is_display=True,
        )

        response = self.client.get('/api/cmdb/config-items/import-template/', {'ci_type': ci_type.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        content = response.content.decode('utf-8-sig')
        self.assertIn('资产名称,模型,唯一标识,业务线,环境,负责人,部门,状态,来源,来源账号,来源区域,私网 IP,公网 IP,规格,CPU', content)
        self.assertNotIn('__required_fields', content)
        self.assertNotIn('扩展属性JSON', content)
        self.assertIn('ecs-prod-01,模板云主机,i-example-001,core,prod,ops,基础架构部,active', content)
        self.assertIn('基础架构部', content)
        self.assertIn('10.0.0.8,,,4', content)

    def test_config_item_import_template_returns_zip_for_multiple_models(self):
        server_type = _ci_type('模板服务器', code='TEMPLATE_SERVER')
        database_type = _ci_type('模板数据库', code='TEMPLATE_DATABASE')

        response = self.client.get('/api/cmdb/config-items/import-template/', {'ci_types': f'{server_type.id},{database_type.id}'})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response['Content-Type'], 'application/zip')
        with ZipFile(io.BytesIO(response.content)) as archive:
            self.assertIn('TEMPLATE_SERVER.csv', archive.namelist())
            self.assertIn('TEMPLATE_DATABASE.csv', archive.namelist())

    def test_config_item_bulk_import_ignores_template_metadata_columns(self):
        ci_type = _ci_type('模板导入云主机', code='TEMPLATE_IMPORT_SERVER')
        CIField.objects.create(
            ci_type=ci_type,
            name='私网 IP',
            code='private_ip',
            field_type='ip',
            required=True,
        )
        csv_text = (
            'ci_type_name,ci_type_code,name,source_unique_id,business_line,environment,admin_user,private_ip,__required_fields,__template_note\n'
            '模板导入云主机,TEMPLATE_IMPORT_SERVER,template-import-ecs-01,tmpl-import-001,core,prod,ops,10.8.1.8,private_ip(私网 IP),说明列会被忽略\n'
        )

        response = self.client.post(
            '/api/cmdb/config-items/bulk-import/',
            {
                'format': 'csv',
                'source_type': 'csv_import',
                'name': '模板说明列导入',
                'text': csv_text,
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['summary']['create'], 1)
        ci = ConfigItem.objects.get(name='template-import-ecs-01')
        self.assertEqual(ci.attributes['private_ip'], '10.8.1.8')
        self.assertNotIn('__required_fields', ci.attributes)
        self.assertNotIn('__template_note', ci.attributes)

    def test_config_item_bulk_import_accepts_utf8_bom_csv_template(self):
        csv_text = (
            '\ufeffci_type_name,ci_type_code,name,source_unique_id,business_line,environment,admin_user,instance_id,private_ip\n'
            '云主机(ECS),CLOUD_SERVER,bom-import-ecs-01,bom-import-001,core,prod,ops,i-bom-001,192.0.2.10\n'
        )

        response = self.client.post(
            '/api/cmdb/config-items/bulk-import/',
            {
                'format': 'csv',
                'source_type': 'csv_import',
                'text': csv_text,
                'dry_run': True,
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['summary'].get('create'), 1, response.json())

    def test_config_item_bulk_import_accepts_chinese_template_headers(self):
        ci_type = _ci_type('中文导入云主机', code='CHINESE_IMPORT_CLOUD_SERVER')
        csv_text = (
            '资产名称,模型,唯一标识,业务线,环境,负责人,部门,状态\n'
            'chinese-import-ecs-01,中文导入云主机,chinese-import-001,core,prod,ops,基础架构部,active\n'
        )

        response = self.client.post(
            '/api/cmdb/config-items/bulk-import/',
            {'format': 'csv', 'source_type': 'csv_import', 'text': csv_text},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        ci = ConfigItem.objects.get(name='chinese-import-ecs-01')
        self.assertEqual(ci.ci_type_id, ci_type.id)
        self.assertEqual(ci.business_line, 'core')
        self.assertEqual(ci.attributes['department'], '基础架构部')

    def test_dashboard_returns_phase_one_risks_and_waterline(self):
        ci_type = _ci_type('Redis', code='REDIS')
        ci = ConfigItem.objects.create(
            name='redis-prod-01',
            ci_type=ci_type,
            business_line='',
            environment='prod',
            admin_user='',
            status='active',
            attributes={'source_type': 'aliyun_redis', 'instance_type': 'redis.master.small.default'},
        )
        CIResourceMetricSnapshot.objects.create(
            ci=ci,
            metric='storage',
            value=92,
            unit='%',
            usage_percent=92,
            collected_at=timezone.now(),
            source='monitor',
        )
        policy = CIThresholdPolicy.objects.create(
            resource_type=ci_type,
            metric='storage',
            normal_threshold=80,
            warning_threshold=90,
            critical_threshold=96,
            exceeded_threshold=99,
        )
        completion_issue = CICompletionIssue.objects.create(
            ci=ci,
            missing_fields=[
                {'code': 'business_line', 'name': '业务线'},
                {'code': 'department', 'name': '部门'},
            ],
            severity='high',
        )
        completion_issue.created_at = timezone.now() - timezone.timedelta(days=2)
        completion_issue.save(update_fields=['created_at'])
        archive_candidate = CIArchiveCandidate.objects.create(
            ci=ci,
            source_type='aliyun_redis',
            reason='来源端连续两次未发现',
        )
        archive_candidate.created_at = timezone.now() - timezone.timedelta(days=8)
        archive_candidate.save(update_fields=['created_at'])
        sync_job = CISyncJob.objects.create(
            name='redis-sync',
            source_type='aliyun_redis',
            status='failed',
            created_by=self.user.username,
        )
        sync_record = CISyncRecord.objects.create(
            job=sync_job,
            ci=ci,
            action='fail',
            source_unique_id='redis-prod-01',
            status='failed',
            error_message='source api timeout',
        )
        sync_record.created_at = timezone.now() - timezone.timedelta(days=2)
        sync_record.save(update_fields=['created_at'])
        capacity_request = ResourceRequest.objects.create(
            title='Redis storage expansion',
            applicant='cmdb-admin',
            resource_type='主机',
            specification='redis.master.large.default',
            business_line='',
            environment='prod',
            priority='high',
            quantity=1,
            status='pending',
            reason='Storage waterline is above warning threshold',
            specs={
                'capacity_source': {
                    'ci_id': ci.id,
                    'ci_name': ci.name,
                    'metric': 'storage',
                    'usage_percent': 92,
                    'status': 'warning',
                    'policy_id': policy.id,
                }
            },
        )

        response = self.client.get('/api/cmdb/dashboard/stats/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('ci_by_source', payload)
        self.assertEqual(payload['risk_summary']['missing_owner'], 1)
        self.assertEqual(payload['risk_summary']['completion_issues'], 1)
        self.assertEqual(payload['risk_summary']['archive_candidates'], 1)
        self.assertEqual(payload['risk_summary']['sync_failures'], 1)
        self.assertEqual(payload['capacity_waterline']['warning'], 1)
        self.assertEqual(payload['capacity_waterline']['critical'], 0)
        self.assertEqual(payload['capacity_waterline']['requesting'], 1)
        capacity_risk = payload['capacity_waterline']['top_risks'][0]
        self.assertEqual(capacity_risk['thresholds']['policy_id'], policy.id)
        self.assertEqual(capacity_risk['thresholds']['policy_scope'], 'model')
        self.assertEqual(capacity_risk['thresholds']['warning_threshold'], 90.0)
        self.assertEqual(capacity_risk['policy_id'], policy.id)
        self.assertEqual(capacity_risk['policy_scope'], 'model')
        self.assertEqual(capacity_risk['warning_threshold'], 90.0)
        self.assertEqual(capacity_risk['ci_type_name'], 'Redis')
        self.assertEqual(capacity_risk['environment'], 'prod')
        self.assertEqual(capacity_risk['source_type'], 'aliyun_redis')
        self.assertEqual(capacity_risk['instance_type'], 'redis.master.small.default')
        self.assertEqual(capacity_risk['governance_status'], 'requesting')
        self.assertEqual(capacity_risk['linked_request']['id'], capacity_request.id)
        self.assertEqual(capacity_risk['linked_request']['status'], 'pending')
        self.assertEqual(payload['data_quality']['total'], 1)
        self.assertEqual(payload['data_quality']['critical'], 1)
        self.assertEqual(payload['data_quality']['issue_counts']['missing_ownership'], 1)
        self.assertEqual(payload['data_quality']['issue_counts']['no_relation'], 1)
        self.assertEqual(payload['data_quality']['issue_counts']['completion_issues'], 1)
        self.assertEqual(payload['data_quality']['issue_counts']['archive_candidates'], 1)
        self.assertEqual(payload['data_quality']['issue_counts']['sync_failures'], 1)
        self.assertEqual(payload['data_quality']['top_risks'][0]['ci_id'], ci.id)
        self.assertTrue(payload['data_quality']['model_quality'])
        self.assertEqual(payload['data_quality']['model_quality'][0]['ci_type'], ci_type.id)
        self.assertEqual(payload['data_quality']['model_quality'][0]['ci_type_name'], 'Redis')
        workload = payload['data_quality']['governance_workload']
        self.assertEqual(workload['total'], 3)
        self.assertEqual(workload['overdue_total'], 3)
        self.assertEqual(workload['completion_overdue'], 1)
        self.assertEqual(workload['archive_overdue'], 1)
        self.assertEqual(workload['sync_overdue'], 1)
        self.assertEqual(workload['top_overdue_tasks'][0]['age_days'], 8)
        self.assertTrue(any(item['assignee'] == '未分派' and item['overdue'] >= 2 for item in workload['assignee_workload']))
        self.assertTrue(payload['application_suggestions'])
        self.assertTrue(any(item['type'] == 'data_quality' for item in payload['application_suggestions']))
        capacity_suggestion = next(item for item in payload['application_suggestions'] if item['type'] == 'capacity')
        self.assertEqual(capacity_suggestion['ci_id'], ci.id)
        self.assertEqual(capacity_suggestion['metric'], 'storage')
        self.assertEqual(capacity_suggestion['usage_percent'], 92.0)
        self.assertEqual(capacity_suggestion['policy_id'], policy.id)
        self.assertEqual(capacity_suggestion['thresholds']['critical_threshold'], 96.0)
        self.assertEqual(capacity_suggestion['environment'], 'prod')
        self.assertEqual(capacity_suggestion['governance_status'], 'requesting')
        self.assertEqual(capacity_suggestion['linked_request']['id'], capacity_request.id)

        completed_at = timezone.now()
        capacity_request.status = 'completed'
        capacity_request.completed_at = completed_at
        capacity_request.save(update_fields=['status', 'completed_at', 'updated_at'])
        CIResourceMetricSnapshot.objects.create(
            ci=ci,
            metric='storage',
            value=98,
            unit='%',
            usage_percent=98,
            collected_at=completed_at + timezone.timedelta(minutes=5),
            source='monitor',
        )

        recheck_response = self.client.get('/api/cmdb/dashboard/stats/')
        self.assertEqual(recheck_response.status_code, 200)
        recheck_payload = recheck_response.json()
        self.assertEqual(recheck_payload['capacity_waterline']['requesting'], 0)
        self.assertEqual(recheck_payload['capacity_waterline']['recheck_failed'], 1)
        recheck_risk = recheck_payload['capacity_waterline']['top_risks'][0]
        self.assertEqual(recheck_risk['status'], 'critical')
        self.assertEqual(recheck_risk['governance_status'], 'recheck_failed')
        self.assertEqual(recheck_risk['linked_request']['status'], 'completed')

    def test_completion_issue_resolve_requires_real_field_completion(self):
        ci_type = _ci_type('补全测试模型', code='COMPLETION_TEST')
        CIField.objects.create(
            ci_type=ci_type,
            name='实例 ID',
            code='instance_id',
            field_type='string',
            required=True,
        )
        ci = ConfigItem.objects.create(
            name='ecs-missing-owner',
            ci_type=ci_type,
            business_line='',
            environment='prod',
            admin_user='',
            status='active',
            attributes={},
        )
        issue = CICompletionIssue.objects.create(
            ci=ci,
            missing_fields=[
                {'code': 'business_line', 'name': '业务线'},
                {'code': 'admin_user', 'name': '负责人'},
                {'code': 'department', 'name': '部门'},
                {'code': 'instance_id', 'name': '实例 ID'},
            ],
            severity='high',
        )
        issue.created_at = timezone.now() - timezone.timedelta(days=2)
        issue.save(update_fields=['created_at'])

        list_response = self.client.get('/api/cmdb/completion-issues/', {'status': 'open'})
        self.assertEqual(list_response.status_code, 200, list_response.content)
        listed_issue = next(item for item in list_response.json()['results'] if item['id'] == issue.id)
        self.assertGreaterEqual(listed_issue['age_days'], 2)
        self.assertEqual(listed_issue['due_days'], 1)
        self.assertTrue(listed_issue['is_overdue'])

        incomplete_response = self.client.post(
            f'/api/cmdb/completion-issues/{issue.id}/resolve/',
            data=json.dumps({
                'status': 'resolved',
                'note': '只补负责人还不够',
                'ci_updates': {
                    'admin_user': 'sre-core',
                },
            }),
            content_type='application/json',
        )

        self.assertEqual(incomplete_response.status_code, 400)
        self.assertIn('missing_fields', incomplete_response.json())
        issue.refresh_from_db()
        self.assertEqual(issue.status, 'open')

        complete_response = self.client.post(
            f'/api/cmdb/completion-issues/{issue.id}/resolve/',
            data=json.dumps({
                'status': 'resolved',
                'note': '补齐归属和实例 ID',
                'ci_updates': {
                    'business_line': 'core',
                    'environment': 'prod',
                    'admin_user': 'sre-core',
                    'department': '基础架构部',
                    'attributes': {
                        'instance_id': 'i-abc123',
                    },
                },
            }),
            content_type='application/json',
        )

        self.assertEqual(complete_response.status_code, 200)
        ci.refresh_from_db()
        issue.refresh_from_db()
        self.assertEqual(ci.business_line, 'core')
        self.assertEqual(ci.admin_user, 'sre-core')
        self.assertEqual(ci.attributes['department'], '基础架构部')
        self.assertEqual(ci.attributes['instance_id'], 'i-abc123')
        self.assertEqual(issue.status, 'resolved')
        self.assertEqual(issue.resolution_note, '补齐归属和实例 ID')
        self.assertTrue(CIChangeLog.objects.filter(ci=ci, action='completion_resolve').exists())

    def test_completion_issue_assign_marks_owner_and_keeps_governance_audit(self):
        ci_type = _ci_type('转派治理云主机', code='ASSIGN_GOV_CLOUD_SERVER')
        ci = ConfigItem.objects.create(
            name='assign-govern-ecs-01',
            ci_type=ci_type,
            business_line='',
            environment='prod',
            admin_user='',
            status='active',
        )
        issue = CICompletionIssue.objects.create(
            ci=ci,
            missing_fields=[
                {'code': 'business_line', 'name': '业务线'},
                {'code': 'admin_user', 'name': '负责人'},
            ],
            severity='high',
            status='open',
        )

        empty_response = self.client.post(
            f'/api/cmdb/completion-issues/{issue.id}/assign/',
            {'assigned_to': ''},
            content_type='application/json',
        )
        self.assertEqual(empty_response.status_code, 400)

        response = self.client.post(
            f'/api/cmdb/completion-issues/{issue.id}/assign/',
            {'assigned_to': 'sre-oncall', 'note': '转派给值班组补齐归属'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        issue.refresh_from_db()
        self.assertEqual(issue.status, 'assigned')
        self.assertEqual(issue.assigned_to, 'sre-oncall')
        self.assertEqual(issue.resolution_note, '转派给值班组补齐归属')
        self.assertTrue(CIChangeLog.objects.filter(ci=ci, action='completion_assign', source='governance').exists())

    def test_completion_issue_bulk_resolve_updates_common_fields(self):
        ci_type = _ci_type('批量补全云主机', code='BULK_COMPLETION_SERVER')
        first = ConfigItem.objects.create(
            name='bulk-completion-01',
            ci_type=ci_type,
            business_line='',
            environment='',
            admin_user='',
            status='active',
            attributes={},
        )
        second = ConfigItem.objects.create(
            name='bulk-completion-02',
            ci_type=ci_type,
            business_line='',
            environment='',
            admin_user='',
            status='active',
            attributes={},
        )
        first_issue = CICompletionIssue.objects.create(
            ci=first,
            missing_fields=[
                {'code': 'business_line', 'name': '业务线'},
                {'code': 'environment', 'name': '环境'},
                {'code': 'admin_user', 'name': '负责人'},
                {'code': 'department', 'name': '部门'},
            ],
            severity='high',
            status='open',
        )
        second_issue = CICompletionIssue.objects.create(
            ci=second,
            missing_fields=first_issue.missing_fields,
            severity='high',
            status='assigned',
            assigned_to='sre-oncall',
        )

        response = self.client.post(
            '/api/cmdb/completion-issues/bulk-resolve/',
            data=json.dumps({
                'issue_ids': [first_issue.id, second_issue.id],
                'note': '批量补齐归属字段',
                'ci_updates': {
                    'business_line': 'core',
                    'environment': 'prod',
                    'admin_user': 'ops',
                    'department': '基础架构部',
                },
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['summary']['total'], 2)
        self.assertEqual(payload['summary']['resolved'], 2)
        self.assertEqual(payload['summary']['remaining'], 0)
        first.refresh_from_db()
        second.refresh_from_db()
        first_issue.refresh_from_db()
        second_issue.refresh_from_db()
        self.assertEqual(first.business_line, 'core')
        self.assertEqual(second.environment, 'prod')
        self.assertEqual(first.attributes['department'], '基础架构部')
        self.assertEqual(first_issue.status, 'resolved')
        self.assertEqual(second_issue.status, 'resolved')
        self.assertEqual(CIChangeLog.objects.filter(ci__in=[first, second], action='completion_resolve', source='governance').count(), 2)

    def test_completion_issue_ignore_closes_false_positive_without_reopening(self):
        ci_type = _ci_type('忽略治理云主机', code='IGNORE_GOV_CLOUD_SERVER')
        ci = ConfigItem.objects.create(
            name='ignore-govern-ecs-01',
            ci_type=ci_type,
            business_line='',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={'private_ip': '10.9.1.10'},
        )
        issue = CICompletionIssue.objects.create(
            ci=ci,
            missing_fields=[
                {'code': 'business_line', 'name': '业务线'},
                {'code': 'department', 'name': '部门'},
            ],
            severity='medium',
            status='open',
        )

        response = self.client.post(
            f'/api/cmdb/completion-issues/{issue.id}/ignore/',
            {'note': '临时外部托管资源无需补齐业务线'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        issue.refresh_from_db()
        self.assertEqual(issue.status, 'ignored')
        self.assertEqual(issue.resolution_note, '临时外部托管资源无需补齐业务线')
        self.assertIsNotNone(issue.resolved_at)
        self.assertTrue(CIChangeLog.objects.filter(ci=ci, action='completion_ignore').exists())

        update_response = self.client.put(
            f'/api/cmdb/config-items/{ci.id}/',
            {
                'name': 'ignore-govern-ecs-01',
                'ci_type': ci_type.id,
                'business_line': '',
                'environment': 'prod',
                'admin_user': 'ops',
                'status': 'active',
                'attributes': {'private_ip': '10.9.1.11'},
            },
            content_type='application/json',
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(CICompletionIssue.objects.filter(ci=ci).count(), 1)
        self.assertFalse(CICompletionIssue.objects.filter(ci=ci).exclude(status__in=['resolved', 'ignored']).exists())

    def test_archive_candidate_confirm_and_restore_changes_ci_status(self):
        ci_type = _ci_type('第三方服务', code='THIRD_PARTY_SERVICE')
        ci = ConfigItem.objects.create(
            name='sms-provider',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
        )
        candidate = CIArchiveCandidate.objects.create(ci=ci, source_type='manual', reason='合同到期')

        confirm_response = self.client.post(f'/api/cmdb/archive-candidates/{candidate.id}/confirm/')
        self.assertEqual(confirm_response.status_code, 200)
        ci.refresh_from_db()
        self.assertEqual(ci.status, 'offline')

        restore_response = self.client.post(f'/api/cmdb/archive-candidates/{candidate.id}/restore/')
        self.assertEqual(restore_response.status_code, 200)
        ci.refresh_from_db()
        self.assertEqual(ci.status, 'active')

    def test_archive_candidate_archive_marks_offline_and_records_audit(self):
        ci_type = _ci_type('归档第三方服务', code='ARCHIVE_THIRD_PARTY_SERVICE')
        ci = ConfigItem.objects.create(
            name='archive-sms-provider',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
        )
        candidate = CIArchiveCandidate.objects.create(ci=ci, source_type='manual', reason='合同到期')

        response = self.client.post(
            f'/api/cmdb/archive-candidates/{candidate.id}/archive/',
            {'note': '合同已终止并完成资料归档'},
        )

        self.assertEqual(response.status_code, 200, response.content)
        ci.refresh_from_db()
        candidate.refresh_from_db()
        self.assertEqual(ci.status, 'offline')
        self.assertEqual(candidate.status, 'archived')
        self.assertIn('资料归档', candidate.reason)
        self.assertTrue(CIChangeLog.objects.filter(ci=ci, action='archive_archive', source='governance').exists())

    def test_archive_candidate_bulk_action_archives_candidates_with_audit(self):
        ci_type = _ci_type('批量归档服务', code='BULK_ARCHIVE_SERVICE')
        first = ConfigItem.objects.create(
            name='bulk-archive-service-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
        )
        second = ConfigItem.objects.create(
            name='bulk-archive-service-02',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
        )
        first_candidate = CIArchiveCandidate.objects.create(ci=first, source_type='manual', reason='批量下线')
        second_candidate = CIArchiveCandidate.objects.create(ci=second, source_type='manual', reason='批量下线')

        response = self.client.post(
            '/api/cmdb/archive-candidates/bulk-action/',
            {
                'candidate_ids': [first_candidate.id, second_candidate.id],
                'action': 'archive',
                'note': '批量确认不再使用',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['updated_count'], 2)
        first.refresh_from_db()
        second.refresh_from_db()
        first_candidate.refresh_from_db()
        second_candidate.refresh_from_db()
        self.assertEqual(first.status, 'offline')
        self.assertEqual(second.status, 'offline')
        self.assertEqual(first_candidate.status, 'archived')
        self.assertEqual(second_candidate.status, 'archived')
        self.assertIn('批量确认', first_candidate.reason)
        self.assertEqual(
            CIChangeLog.objects.filter(ci__in=[first, second], action='archive_archive', source='governance').count(),
            2,
        )

    def test_archive_candidate_bulk_action_rejects_missing_candidates(self):
        response = self.client.post(
            '/api/cmdb/archive-candidates/bulk-action/',
            {'candidate_ids': [999999], 'action': 'ignore'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn('candidate_ids', response.json())

    def test_config_item_lifecycle_actions_mark_candidate_and_restore(self):
        ci_type = _ci_type('生命周期云主机', code='LIFECYCLE_SERVER')
        ci = ConfigItem.objects.create(
            name='lifecycle-ecs-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
        )

        mark_response = self.client.post(
            f'/api/cmdb/config-items/{ci.id}/mark-archive-candidate/',
            {'source_type': 'manual', 'reason': '资源详情人工标记'},
        )
        self.assertEqual(mark_response.status_code, 200, mark_response.content)
        ci.refresh_from_db()
        self.assertEqual(ci.status, 'active')
        candidate = CIArchiveCandidate.objects.get(ci=ci, source_type='manual')
        self.assertEqual(candidate.status, 'pending')
        self.assertEqual(candidate.reason, '资源详情人工标记')
        self.assertTrue(CIChangeLog.objects.filter(ci=ci, action='archive_mark', source='governance').exists())

        candidate.status = 'confirmed'
        candidate.save(update_fields=['status', 'updated_at'])
        ci.status = 'offline'
        ci.save(update_fields=['status', 'updated_at'])

        restore_response = self.client.post(
            f'/api/cmdb/config-items/{ci.id}/restore-lifecycle/',
            {'status': 'active', 'note': '误标记恢复'},
        )
        self.assertEqual(restore_response.status_code, 200, restore_response.content)
        ci.refresh_from_db()
        candidate.refresh_from_db()
        self.assertEqual(ci.status, 'active')
        self.assertEqual(candidate.status, 'restored')
        self.assertTrue(CIChangeLog.objects.filter(ci=ci, action='archive_restore', source='governance').exists())

    def test_config_item_bulk_update_updates_scope_tags_attributes_and_audit(self):
        ci_type = _ci_type('批量维护云主机', code='BULK_UPDATE_SERVER')
        business_node = ResourceNode.objects.create(name='bulk-target-business', node_type='biz')
        environment_node = ResourceNode.objects.create(name='prod', node_type='env', parent=business_node)
        first = ConfigItem.objects.create(
            name='bulk-update-ecs-01',
            ci_type=ci_type,
            business_line='old',
            environment='dev',
            admin_user='old-owner',
            status='idle',
            attributes={'instance_id': 'i-bulk-001', 'department': 'old-dept'},
        )
        second = ConfigItem.objects.create(
            name='bulk-update-ecs-02',
            ci_type=ci_type,
            business_line='old',
            environment='dev',
            admin_user='old-owner',
            status='idle',
            attributes={'instance_id': 'i-bulk-002'},
        )
        tag = CITag.objects.create(name='核心业务', category='业务')

        response = self.client.post(
            '/api/cmdb/config-items/bulk-update/',
            data=json.dumps({
                'ids': [first.id, second.id],
                'updates': {
                    'business_line': business_node.name,
                    'environment': 'prod',
                    'admin_user': 'sre-core',
                    'status': 'active',
                    'attributes': {
                        'department': '基础架构部',
                        'owner_group': 'sre',
                    },
                },
                'tag_ids': [tag.id],
                'tag_action': 'append',
                'note': '批量修正资源归属',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['updated_count'], 2)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.business_line, business_node.name)
        self.assertEqual(second.environment, 'prod')
        self.assertEqual(first.business_node_id, business_node.id)
        self.assertEqual(second.business_node_id, business_node.id)
        self.assertEqual(first.environment_node_id, environment_node.id)
        self.assertEqual(second.environment_node_id, environment_node.id)
        self.assertEqual(first.admin_user, 'sre-core')
        self.assertEqual(second.status, 'active')
        self.assertEqual(first.attributes['instance_id'], 'i-bulk-001')
        self.assertEqual(first.attributes['department'], '基础架构部')
        self.assertEqual(second.attributes['owner_group'], 'sre')
        self.assertTrue(first.tags.filter(id=tag.id).exists())
        self.assertTrue(second.tags.filter(id=tag.id).exists())
        self.assertEqual(
            CIChangeLog.objects.filter(ci__in=[first, second], action='bulk_update', source='manual').count(),
            2,
        )

    def test_config_item_bulk_update_allows_tag_only_for_incomplete_items(self):
        ci_type = _ci_type('批量打标待补全资源', code='BULK_TAG_INCOMPLETE')
        CIField.objects.create(
            ci_type=ci_type,
            name='实例 ID',
            code='instance_id',
            field_type='string',
            required=True,
        )
        ci = ConfigItem.objects.create(
            name='bulk-tag-incomplete-01',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
            attributes={},
        )
        tag = CITag.objects.create(name='待治理', category='治理')

        response = self.client.post(
            '/api/cmdb/config-items/bulk-update/',
            data=json.dumps({
                'ids': [ci.id],
                'updates': {},
                'tag_ids': [tag.id],
                'tag_action': 'append',
                'note': '仅打标签',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        ci.refresh_from_db()
        self.assertTrue(ci.tags.filter(id=tag.id).exists())
        self.assertEqual(ci.attributes, {})
        self.assertTrue(CIChangeLog.objects.filter(ci=ci, action='bulk_update', source='manual').exists())

    def test_archive_candidate_ignore_keeps_ci_active_and_closes_candidate(self):
        ci_type = _ci_type('Redis', code='REDIS')
        ci = ConfigItem.objects.create(
            name='redis-false-positive',
            ci_type=ci_type,
            business_line='core',
            environment='prod',
            admin_user='ops',
            status='active',
        )
        candidate = CIArchiveCandidate.objects.create(ci=ci, source_type='aliyun_redis', reason='来源端暂时未返回')

        response = self.client.post(
            f'/api/cmdb/archive-candidates/{candidate.id}/ignore/',
            {'note': '云账号临时权限异常，先忽略'},
        )

        self.assertEqual(response.status_code, 200)
        ci.refresh_from_db()
        candidate.refresh_from_db()
        self.assertEqual(ci.status, 'active')
        self.assertEqual(candidate.status, 'ignored')
        self.assertIn('先忽略', candidate.reason)
        self.assertTrue(CIChangeLog.objects.filter(ci=ci, action='archive_ignore').exists())


