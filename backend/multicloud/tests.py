from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from cmdb.models import CISourceMapping, CIType, ConfigItem
from multicloud.models import CloudAsset, CloudCredential, CloudEnvironment
from multicloud.sdk_adapters import HuaweiCloudAdapter
from multicloud.services import _inventory, sync_environment_inventory, sync_environment_to_cmdb


class MultiCloudTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_superuser('multicloud-admin', 'multicloud@example.com', 'Admin@123456')
        self.client.force_authenticate(self.user)
        self.credential = CloudCredential.objects.create(
            provider='aliyun',
            name='aliyun-demo',
            account_id='100001',
            account_name='trade-prod',
            auth_mode='aksk',
            access_key_id='test-ak',
            access_key_secret='test-sk',
            default_region='cn-hangzhou',
            owner='SRE',
            demo_mode=False,
            created_by='test',
            updated_by='test',
        )
        self.environment = CloudEnvironment.objects.create(
            credential=self.credential,
            name='订单中心生产',
            code='trade-prod-hz',
            business_line='交易系统',
            environment_type='prod',
            region='cn-hangzhou',
            zone='cn-hangzhou-h',
            vpc_name='vpc-trade-prod',
            network_cidr='10.10.0.0/16',
            owner='交易系统 SRE',
            created_by='test',
            updated_by='test',
        )

    def _inventory_adapter_patch(self):
        class FakeAdapter:
            def capability(inner_self):
                return {'provider': self.credential.provider, 'installed': True, 'supports_inventory': True}

            def fetch_inventory(inner_self, environment):
                return _inventory(environment)

        return patch('multicloud.services.get_cloud_adapter', return_value=FakeAdapter())

    def test_catalog_endpoint_returns_supported_providers(self):
        response = self.client.get('/api/multicloud/catalog/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()['providers']
        self.assertIn('aliyun', payload)
        self.assertIn('resource_types', payload['aws'])
        self.assertIn('sdk', payload['aws'])

    def test_environment_sync_creates_assets_from_adapter(self):
        with self._inventory_adapter_patch():
            response = self.client.post(f'/api/multicloud/environments/{self.environment.id}/sync/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()['environment']['asset_count'], 6)
        self.assertTrue(CloudAsset.objects.filter(environment=self.environment, resource_type='ecs').exists())

    def test_credential_sync_all_runs_for_related_environments(self):
        CloudEnvironment.objects.create(
            credential=self.credential,
            name='订单中心共享',
            code='trade-shared-hz',
            business_line='交易系统',
            environment_type='shared',
            region='cn-shanghai',
            owner='平台',
            created_by='test',
            updated_by='test',
        )
        with self._inventory_adapter_patch():
            response = self.client.post(f'/api/multicloud/credentials/{self.credential.id}/sync_all/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result']['count'], 2)

    def test_vsphere_credential_sync_all_creates_default_environment(self):
        credential = CloudCredential.objects.create(
            provider='vsphere',
            name='vmware-prod',
            account_id='vcsa.prod.local',
            account_name='private-cloud-prod',
            auth_mode='secret',
            access_key_id='administrator@vsphere.local',
            access_key_secret='test-password',
            default_region='private-cloud-prod',
            owner='IDC',
            demo_mode=False,
            created_by='test',
            updated_by='test',
        )

        class FakeAdapter:
            def capability(self):
                return {'provider': 'vsphere', 'installed': True, 'supports_inventory': True}

            def fetch_inventory(self, environment):
                return _inventory(environment)

        with patch('multicloud.services.get_cloud_adapter', return_value=FakeAdapter()):
            response = self.client.post(f'/api/multicloud/credentials/{credential.id}/sync_all/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result']['count'], 1)
        environment = credential.environments.get()
        self.assertEqual(environment.region, 'private-cloud-prod')
        self.assertEqual(environment.vpc_name, 'private-cloud')
        self.assertEqual(CloudAsset.objects.filter(environment=environment, resource_type='ecs').count(), 2)

    def test_vsphere_adapter_normalizes_url_endpoint(self):
        from multicloud.sdk_adapters import VSphereCloudAdapter

        credential = CloudCredential.objects.create(
            provider='vsphere',
            name='example-vsphere',
            account_id='https://10.197.0.10/',
            auth_mode='secret',
            access_key_id='administrator@vsphere.local',
            access_key_secret='secret',
            default_region='private-cloud-prod',
        )

        host, port, username, password = VSphereCloudAdapter(credential)._connection_params()

        self.assertEqual(host, '10.197.0.10')
        self.assertEqual(port, 443)
        self.assertEqual(username, 'administrator@vsphere.local')
        self.assertEqual(password, 'secret')

    def test_vsphere_adapter_reports_invalid_login_as_cloud_adapter_error(self):
        from multicloud.sdk_adapters import CloudAdapterError, VSphereCloudAdapter

        credential = CloudCredential.objects.create(
            provider='vsphere',
            name='example-vsphere',
            account_id='https://10.197.0.10/',
            auth_mode='secret',
            access_key_id='administrator@vsphere.local',
            access_key_secret='bad-password',
            default_region='private-cloud-prod',
        )

        class FakeInvalidLogin(Exception):
            msg = 'Cannot complete login due to an incorrect user name or password.'

        class FakeFault:
            InvalidLogin = FakeInvalidLogin

        class FakeVim:
            fault = FakeFault

        class FakeVmodl:
            MethodFault = Exception

        class FakePyVmomi:
            vim = FakeVim
            vmodl = FakeVmodl

        class FakeConnect:
            @staticmethod
            def SmartConnect(**kwargs):
                raise FakeInvalidLogin()

        def fake_import(module_name):
            if module_name == 'pyVim.connect':
                return FakeConnect
            if module_name == 'pyVmomi':
                return FakePyVmomi
            raise AssertionError(module_name)

        with patch('multicloud.sdk_adapters._has_module', return_value=True), patch('multicloud.sdk_adapters.importlib.import_module', side_effect=fake_import):
            with self.assertRaisesRegex(CloudAdapterError, 'vSphere 账号认证失败'):
                VSphereCloudAdapter(credential).test_connection()

    def test_credential_list_counts_cmdb_assets_for_sync_center(self):
        ci_type, _ = CIType.objects.get_or_create(
            code='SYNC_CENTER_TEST_SERVER',
            defaults={'name': 'Sync Center Test Server'},
        )
        ci = ConfigItem.objects.create(
            name='aliyun-ecs-01',
            ci_type=ci_type,
            attributes={'source_type': 'aliyun_ecs', 'source_account': 'trade-prod'},
        )
        CISourceMapping.objects.create(
            ci=ci,
            source_type='aliyun_ecs',
            source_account='trade-prod',
            source_region='cn-hangzhou',
            source_unique_id='i-sync-center-001',
        )
        other_ci = ConfigItem.objects.create(
            name='huawei-ecs-01',
            ci_type=ci_type,
            attributes={'source_type': 'huaweicloud_ecs', 'source_account': 'trade-prod'},
        )
        CISourceMapping.objects.create(
            ci=other_ci,
            source_type='huaweicloud_ecs',
            source_account='trade-prod',
            source_region='cn-north-4',
            source_unique_id='hw-sync-center-001',
        )

        response = self.client.get('/api/multicloud/credentials/')

        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.json() if item['id'] == self.credential.id)
        self.assertEqual(row['asset_count'], 1)

    def test_credential_list_falls_back_to_inventory_asset_count(self):
        CloudAsset.objects.create(
            environment=self.environment,
            provider='aliyun',
            resource_type='ecs',
            resource_id='i-inventory-001',
            name='inventory-ecs-01',
            region='cn-hangzhou',
        )

        response = self.client.get('/api/multicloud/credentials/')

        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.json() if item['id'] == self.credential.id)
        self.assertEqual(row['asset_count'], 1)

    def test_credential_list_excludes_internal_provider_summary_assets(self):
        credential = CloudCredential.objects.create(
            provider='vsphere',
            name='vcenter-prod',
            account_id='vcenter.example.com',
            account_name='example-vsphere',
            auth_mode='secret',
        )
        vm_type, _ = CIType.objects.get_or_create(
            code='SYNC_CENTER_TEST_VM',
            defaults={'name': 'Sync Center Test VM'},
        )
        summary_type, _ = CIType.objects.get_or_create(
            code='VSPHERE_CAPACITY',
            defaults={'name': 'vSphere资源统计'},
        )
        vm = ConfigItem.objects.create(
            name='vm-01',
            ci_type=vm_type,
            attributes={'source_type': 'vsphere_vm', 'source_account': 'example-vsphere'},
        )
        summary = ConfigItem.objects.create(
            name='example-vsphere resources',
            ci_type=summary_type,
            attributes={
                'source_type': 'vsphere_vm',
                'source_account': 'example-vsphere',
                'source_unique_id': 'vsphere-summary:example-vsphere',
            },
        )
        CISourceMapping.objects.create(
            ci=vm,
            source_type='vsphere_vm',
            source_account='example-vsphere',
            source_region='private-cloud',
            source_unique_id='vm-01',
        )
        CISourceMapping.objects.create(
            ci=summary,
            source_type='vsphere_vm',
            source_account='example-vsphere',
            source_region='private-cloud',
            source_unique_id='vsphere-summary:example-vsphere',
        )

        response = self.client.get('/api/multicloud/credentials/')

        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.json() if item['id'] == credential.id)
        self.assertEqual(row['asset_count'], 1)

    def test_overview_endpoint_aggregates_assets_and_costs(self):
        with self._inventory_adapter_patch():
            sync_environment_inventory(self.environment, operator='test')
        response = self.client.get('/api/multicloud/overview/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['stats']['credential_count'], 1)
        self.assertGreaterEqual(payload['stats']['asset_count'], 6)
        self.assertTrue(payload['recommendations'])
        self.assertTrue(payload['cost_trend']['series'])

    def test_sync_cmdb_creates_cmdb_items(self):
        with self._inventory_adapter_patch():
            sync_environment_inventory(self.environment, operator='test')
        response = self.client.post(f'/api/multicloud/environments/{self.environment.id}/sync_cmdb/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertGreater(ConfigItem.objects.count(), 0)
        self.assertTrue(ConfigItem.objects.filter(attributes__cmdb_source='multicloud').exists())

    def test_vsphere_cmdb_sync_maps_ecs_assets_to_virtual_machine(self):
        credential = CloudCredential.objects.create(
            provider='vsphere',
            name='example-vsphere',
            account_id='vcsa.example.local',
            account_name='example-vsphere',
            auth_mode='secret',
            access_key_id='administrator@vsphere.local',
            access_key_secret='test-password',
            default_region='private-cloud',
            owner='IDC',
            demo_mode=False,
            created_by='test',
            updated_by='test',
        )
        environment = CloudEnvironment.objects.create(
            credential=credential,
            name='example-vsphere',
            code='example-vsphere',
            business_line='基础设施',
            environment_type='prod',
            region='private-cloud',
            owner='IDC',
            created_by='test',
            updated_by='test',
        )
        asset = CloudAsset.objects.create(
            environment=environment,
            provider='vsphere',
            resource_type='ecs',
            resource_id='vm-001',
            name='vsphere-vm-01',
            region='private-cloud',
            status='running',
            private_ip='10.197.0.21',
            cpu=4,
            memory_gb='8',
            disk_gb='120',
            metadata={'platform': 'vsphere'},
        )
        cloud_type, _ = CIType.objects.get_or_create(code='CLOUD_SERVER', defaults={'name': '云主机(ECS)'})
        ConfigItem.objects.create(
            name=asset.name,
            ci_type=cloud_type,
            attributes={
                'cmdb_source': 'multicloud',
                'provider': 'vsphere',
                'resource_id': asset.resource_id,
                'account_id': credential.account_id,
            },
        )

        sync_environment_to_cmdb(environment, operator='test')

        items = ConfigItem.objects.filter(attributes__provider='vsphere', attributes__resource_id=asset.resource_id)
        self.assertEqual(items.count(), 1)
        ci = items.get()
        self.assertEqual(ci.ci_type.name, '虚拟机')
        self.assertEqual(ci.ci_type.code, 'VIRTUAL_MACHINE')

    def test_topology_endpoint_returns_graph_payload(self):
        with self._inventory_adapter_patch():
            sync_environment_inventory(self.environment, operator='test')
        response = self.client.get('/api/multicloud/topology/', {'provider': 'aliyun'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreater(payload['stats']['node_count'], 0)
        self.assertTrue(any(node['id'].startswith('credential-') for node in payload['nodes']))
        self.assertTrue(any(edge['value'] == '账号归属' for edge in payload['edges']))

    def test_cost_trend_endpoint_supports_grouping(self):
        with self._inventory_adapter_patch():
            sync_environment_inventory(self.environment, operator='test')
        response = self.client.get('/api/multicloud/cost-trend/', {'group_by': 'resource_type', 'provider': 'aliyun'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['group_by'], 'resource_type')
        self.assertEqual(len(payload['labels']), 6)
        self.assertTrue(payload['series'])

    def test_batch_action_can_disable_credentials(self):
        response = self.client.post(
            '/api/multicloud/batch-actions/',
            {'scope': 'credentials', 'action': 'disable', 'ids': [self.credential.id]},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.credential.refresh_from_db()
        self.assertFalse(self.credential.is_enabled)

    def test_batch_action_can_mark_assets_as_drift(self):
        with self._inventory_adapter_patch():
            sync_environment_inventory(self.environment, operator='test')
        asset = CloudAsset.objects.filter(environment=self.environment).first()
        response = self.client.post(
            '/api/multicloud/batch-actions/',
            {'scope': 'assets', 'action': 'mark_drift', 'ids': [asset.id]},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        asset.refresh_from_db()
        self.assertEqual(asset.sync_state, 'drift')

    def test_real_sdk_without_valid_credentials_returns_non_healthy_status(self):
        self.credential.demo_mode = False
        self.credential.save(update_fields=['demo_mode'])
        response = self.client.post(f'/api/multicloud/credentials/{self.credential.id}/test_connection/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload['status'], {'warning', 'error'})
        self.assertNotEqual(payload['status'], 'healthy')

    @patch('multicloud.services.get_cloud_adapter')
    def test_real_sdk_inventory_sync_uses_adapter_rows(self, mocked_get_adapter):
        self.credential.provider = 'aws'
        self.credential.demo_mode = False
        self.credential.default_region = 'ap-southeast-1'
        self.credential.save(update_fields=['provider', 'demo_mode', 'default_region'])

        class FakeAdapter:
            def __init__(self, credential):
                self.credential = credential

            def capability(self):
                return {'provider': 'aws', 'installed': True, 'supports_inventory': True}

            def fetch_inventory(self, environment):
                return [
                    {
                        'name': 'aws-live-ecs-01',
                        'provider': 'aws',
                        'resource_type': 'ecs',
                        'resource_id': 'i-live-001',
                        'region': 'ap-southeast-1',
                        'zone': 'ap-southeast-1a',
                        'status': 'running',
                        'charge_type': 'on_demand',
                        'private_ip': '192.0.2.1',
                        'public_ip': '54.251.10.10',
                        'vpc_name': 'vpc-live',
                        'spec': 't3.large',
                        'cpu': 2,
                        'memory_gb': '8',
                        'disk_gb': '120',
                        'monthly_cost': '888',
                        'risk_level': 'normal',
                        'sync_state': 'synced',
                        'tags': {'Name': 'aws-live-ecs-01'},
                        'metadata': {'source': 'sdk'},
                    }
                ]

        mocked_get_adapter.side_effect = lambda credential: FakeAdapter(credential)
        response = self.client.post(f'/api/multicloud/environments/{self.environment.id}/sync/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CloudAsset.objects.filter(environment=self.environment, resource_id='i-live-001').exists())
        self.environment.refresh_from_db()
        self.assertEqual(self.environment.summary['sync_mode'], 'sdk')

    def test_huawei_ecs_specs_parse_flavor_and_attached_volumes(self):
        row = SimpleNamespace(
            flavor=SimpleNamespace(id='s6.large.2', vcpus='2', ram='8192'),
            os_extended_volumes_volumes_attached=[
                {'id': 'root-volume', 'size': '40'},
                SimpleNamespace(id='data-volume', size=100),
            ],
        )

        specs = HuaweiCloudAdapter.server_specs(row)

        self.assertEqual(specs['spec'], 's6.large.2')
        self.assertEqual(specs['cpu'], 2)
        self.assertEqual(specs['memory_gb'], Decimal('8'))
        self.assertEqual(specs['disk_gb'], Decimal('140'))
