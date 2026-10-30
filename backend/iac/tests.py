import copy
import io
import zipfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from cmdb.models import CIRelation, ConfigItem
from iac.models import TerraformExecution, TerraformResourceBinding, TerraformStack


class RetiredIacRouteTests(SimpleTestCase):
    def test_legacy_endpoints_remain_unpublished(self):
        for endpoint in ('catalog/', 'render/', 'bundle/', 'stacks/'):
            self.assertEqual(self.client.get(f'/api/iac/{endpoint}').status_code, 404)


@override_settings(ROOT_URLCONF='iac.test_urls')
class TerraformIacTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_superuser(
            'iac-admin',
            'iac@example.com',
            'Admin@123456',
        )
        self.client.force_authenticate(self.user)
        self.aliyun_payload = {
            'name': 'prod-web',
            'description': 'Production web baseline',
            'cloud_provider': 'aliyun',
            'region': 'cn-hangzhou',
            'zone': 'cn-hangzhou-h',
            'config': {
                'metadata': {
                    'project_name': 'sxdevops',
                    'business_line': 'platform',
                    'environment': 'prod',
                    'owner': 'iac-admin',
                },
                'network': {
                    'vpc_cidr': '10.10.0.0/16',
                    'subnet_cidr': '10.10.1.0/24',
                    'open_ingress_ports': [22, 80, 443],
                },
                'compute': {
                    'instance_name': 'prod-web-01',
                    'instance_type': 'ecs.g6.large',
                    'image_id': 'ubuntu_22_04_x64_20G_alibase_20240111.vhd',
                    'system_disk_type': 'cloud_essd',
                    'system_disk_size': 40,
                    'public_bandwidth': 5,
                },
                'resources': {
                    'rds': {
                        'enabled': False,
                        'name': 'prod-mysql',
                        'instance_type': 'mysql.n2.medium.1',
                        'engine': 'MySQL',
                        'engine_version': '8.0',
                        'storage_gb': 20,
                        'db_name': 'appdb',
                    },
                    'redis': {
                        'enabled': False,
                        'name': 'prod-redis',
                        'instance_class': 'redis.master.small.default',
                        'engine_version': '5.0',
                    },
                    'load_balancer': {
                        'enabled': False,
                        'name': 'prod-slb',
                        'address_type': 'internet',
                        'spec': 'slb.s2.small',
                    },
                    'nat_gateway': {
                        'enabled': False,
                        'name': 'prod-nat',
                        'bandwidth': 10,
                    },
                    'object_storage': {
                        'enabled': False,
                        'bucket_name': 'sxdevops-prod-artifacts',
                        'acl': 'private',
                        'storage_class': 'Standard',
                    },
                },
            },
        }

    def test_catalog_endpoint_returns_supported_providers(self):
        response = self.client.get('/api/iac/catalog/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('aliyun', payload['providers'])
        self.assertIn('huaweicloud', payload['providers'])
        self.assertIn('sections', payload['providers']['aliyun'])
        self.assertIn('secret_fields', payload['providers']['huaweicloud'])

    def test_render_endpoint_generates_aliyun_project_with_optional_resources(self):
        payload = copy.deepcopy(self.aliyun_payload)
        payload['config']['resources']['rds']['enabled'] = True
        payload['config']['resources']['object_storage']['enabled'] = True

        response = self.client.post('/api/iac/render/', payload, format='json')

        self.assertEqual(response.status_code, 200)
        rendered = response.json()
        self.assertIn('versions.tf', rendered['files'])
        self.assertIn('terraform.tfvars.example', rendered['files'])
        self.assertIn('aliyun/alicloud', rendered['files']['versions.tf'])
        self.assertIn('resource "alicloud_instance" "this"', rendered['files']['main.tf'])
        self.assertIn('resource "alicloud_db_instance" "rds"', rendered['files']['main.tf'])
        self.assertIn('resource "alicloud_oss_bucket" "bucket"', rendered['files']['main.tf'])
        self.assertEqual(rendered['summary']['compute']['instance_name'], 'prod-web-01')
        self.assertGreaterEqual(rendered['summary']['resource_count'], 6)

    def test_render_endpoint_falls_back_to_stack_name_when_instance_name_missing(self):
        payload = copy.deepcopy(self.aliyun_payload)
        payload['name'] = 'prod-api'
        payload['config']['compute']['instance_name'] = None

        response = self.client.post('/api/iac/render/', payload, format='json')

        self.assertEqual(response.status_code, 200)
        rendered = response.json()
        self.assertEqual(rendered['summary']['compute']['instance_name'], 'prod-api')
        self.assertIn('instance_name              = "prod-api"', rendered['files']['main.tf'])

    def test_render_endpoint_accepts_non_dict_compute_config(self):
        payload = copy.deepcopy(self.aliyun_payload)
        payload['config']['compute'] = None

        response = self.client.post('/api/iac/render/', payload, format='json')

        self.assertEqual(response.status_code, 200)
        rendered = response.json()
        self.assertEqual(rendered['summary']['compute']['instance_name'], 'prod-web')

    def test_render_endpoint_supports_multiple_servers_and_buckets(self):
        payload = copy.deepcopy(self.aliyun_payload)
        payload['config']['compute']['instances'] = [
            {
                'instance_name': 'prod-web-01',
                'instance_type': 'ecs.g6.large',
                'image_id': 'ubuntu_22_04_x64_20G_alibase_20240111.vhd',
                'system_disk_type': 'cloud_essd',
                'system_disk_size': 40,
                'public_bandwidth': 5,
            },
            {
                'instance_name': 'prod-web-02',
                'instance_type': 'ecs.g6.xlarge',
                'image_id': 'ubuntu_22_04_x64_20G_alibase_20240111.vhd',
                'system_disk_type': 'cloud_essd',
                'system_disk_size': 80,
                'public_bandwidth': 10,
            },
        ]
        payload['config']['resources']['object_storage'] = {
            'enabled': True,
            'bucket_name': 'sxdevops-prod-artifacts',
            'acl': 'private',
            'storage_class': 'Standard',
            'buckets': [
                {'bucket_name': 'sxdevops-prod-artifacts', 'acl': 'private', 'storage_class': 'Standard'},
                {'bucket_name': 'sxdevops-prod-logs', 'acl': 'private', 'storage_class': 'IA'},
            ],
        }

        response = self.client.post('/api/iac/render/', payload, format='json')

        self.assertEqual(response.status_code, 200)
        rendered = response.json()
        self.assertEqual(len(rendered['summary']['compute_instances']), 2)
        self.assertEqual(len(rendered['summary']['object_storage_buckets']), 2)
        self.assertIn('resource "alicloud_instance" "this_2"', rendered['files']['main.tf'])
        self.assertIn('resource "alicloud_oss_bucket" "bucket_2"', rendered['files']['main.tf'])
        self.assertIn('output "instance_ids"', rendered['files']['outputs.tf'])
        self.assertIn('output "bucket_names"', rendered['files']['outputs.tf'])

    def test_render_endpoint_uses_provider_defaults_for_blank_name_region_and_zone(self):
        payload = copy.deepcopy(self.aliyun_payload)
        payload['name'] = ''
        payload['region'] = ''
        payload['zone'] = ''

        response = self.client.post('/api/iac/render/', payload, format='json')

        self.assertEqual(response.status_code, 200)
        rendered = response.json()
        self.assertEqual(rendered['summary']['region'], 'cn-hangzhou')
        self.assertEqual(rendered['summary']['zone'], 'cn-hangzhou-h')
        self.assertIn('stack_name = "prod-web"', rendered['files']['main.tf'])

    def test_render_endpoint_accepts_chinese_stack_name(self):
        payload = copy.deepcopy(self.aliyun_payload)
        payload['name'] = '生产环境主站'

        response = self.client.post('/api/iac/render/', payload, format='json')

        self.assertEqual(response.status_code, 200)
        rendered = response.json()
        self.assertEqual(rendered['summary']['compute']['instance_name'], 'prod-web-01')
        self.assertIn('stack_name = "生产环境主站"', rendered['files']['main.tf'])

    def test_render_endpoint_exposes_custom_topology_relationships(self):
        payload = copy.deepcopy(self.aliyun_payload)
        payload['config']['resources']['rds']['enabled'] = True
        payload['config']['topology'] = {
            'relations': [
                {
                    'source': 'compute',
                    'target': 'rds',
                    'relation_type': 'connects_to',
                    'description': 'Web ECS connects to MySQL',
                }
            ]
        }

        response = self.client.post('/api/iac/render/', payload, format='json')

        self.assertEqual(response.status_code, 200)
        rendered = response.json()
        self.assertTrue(any(
            relation['source'] == 'compute'
            and relation['target'] == 'rds'
            and relation['relation_type'] == 'connects_to'
            for relation in rendered['summary']['relationships']
        ))

    def test_create_stack_persists_generated_files_and_normalized_config(self):
        response = self.client.post('/api/iac/stacks/', self.aliyun_payload, format='json')

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload['created_by'], 'iac-admin')
        self.assertEqual(payload['config']['metadata']['project_name'], 'sxdevops')
        self.assertIn('README.md', payload['generated_files'])
        self.assertNotIn('terraform.tfvars', payload['generated_files'])
        self.assertIn('terraform.tfvars.example', payload['generated_files'])
        self.assertEqual(payload['resource_count'], 4)

    def test_bundle_endpoint_returns_zip_with_sensitive_tfvars(self):
        payload = copy.deepcopy(self.aliyun_payload)
        payload['secrets'] = {
            'access_key': 'demo-ak',
            'secret_key': 'demo-sk',
            'instance_password': 'DemoPassword@123',
        }

        response = self.client.post('/api/iac/bundle/', payload, format='json')

        self.assertEqual(response.status_code, 200)
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        members = set(archive.namelist())
        self.assertIn('terraform.tfvars', members)
        tfvars_content = archive.read('terraform.tfvars').decode('utf-8')
        self.assertIn('access_key = "demo-ak"', tfvars_content)
        self.assertIn('instance_password = "DemoPassword@123"', tfvars_content)

    def test_huaweicloud_render_adds_subnet_gateway_and_eip(self):
        payload = {
            'name': 'test-web',
            'cloud_provider': 'huaweicloud',
            'region': 'cn-north-4',
            'zone': 'cn-north-4a',
            'config': {
                'metadata': {
                    'project_name': 'sxdevops',
                    'business_line': 'platform',
                    'environment': 'test',
                    'owner': 'iac-admin',
                },
                'network': {
                    'vpc_cidr': '10.20.0.0/16',
                    'subnet_cidr': '10.20.1.0/24',
                    'open_ingress_ports': '22,80,443',
                },
                'compute': {
                    'instance_name': 'test-web-01',
                    'instance_type': 's7n.large.2',
                    'image_id': 'replace-with-image-id',
                    'system_disk_type': 'SSD',
                    'system_disk_size': 40,
                    'public_bandwidth': 5,
                },
                'resources': {
                    'rds': {
                        'enabled': False,
                        'name': 'prod-mysql',
                        'flavor': 'rds.mysql.n1.medium.2',
                        'engine': 'MySQL',
                        'engine_version': '8.0',
                        'storage_gb': 40,
                        'volume_type': 'CLOUDSSD',
                        'db_name': 'appdb',
                    },
                    'redis': {
                        'enabled': False,
                        'name': 'prod-redis',
                        'capacity': 1,
                        'engine_version': '5.0',
                        'flavor': 'redis.ha.xu1.large.r2.2',
                    },
                    'load_balancer': {
                        'enabled': False,
                        'name': 'prod-elb',
                        'bandwidth': 10,
                        'type': 'External',
                    },
                    'nat_gateway': {
                        'enabled': False,
                        'name': 'prod-nat',
                        'spec': '1',
                    },
                    'object_storage': {
                        'enabled': False,
                        'bucket_name': 'sxdevops-prod-artifacts',
                        'acl': 'private',
                        'storage_class': 'STANDARD',
                    },
                },
            },
        }

        response = self.client.post('/api/iac/render/', payload, format='json')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        files = payload['files']
        self.assertEqual(payload['summary']['network']['subnet_gateway'], '10.20.1.1')
        self.assertIn('gateway_ip        = "10.20.1.1"', files['main.tf'])
        self.assertIn('huaweicloud_vpc_eip', files['main.tf'])

    @mock.patch('iac.executor.shutil.which', return_value=None)
    def test_execute_endpoint_returns_failed_execution_when_terraform_missing(self, _mock_which):
        create_response = self.client.post('/api/iac/stacks/', self.aliyun_payload, format='json')
        stack_id = create_response.json()['id']

        response = self.client.post(
            f'/api/iac/stacks/{stack_id}/execute/',
            {
                'action': 'plan',
                'secrets': {
                    'access_key': 'demo-ak',
                    'secret_key': 'demo-sk',
                    'instance_password': 'DemoPassword@123',
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['execution']['status'], 'failed')
        self.assertIn('未安装 terraform', payload['execution']['stderr'])
        self.assertEqual(TerraformExecution.objects.count(), 1)
        stack = TerraformStack.objects.get(id=stack_id)
        self.assertEqual(stack.last_execution_status, 'failed')
        self.assertEqual(stack.last_execution_action, 'plan')

    def test_sync_cmdb_endpoint_creates_bindings_and_relations(self):
        payload = copy.deepcopy(self.aliyun_payload)
        payload['config']['resources']['rds']['enabled'] = True
        payload['config']['resources']['object_storage']['enabled'] = True

        create_response = self.client.post('/api/iac/stacks/', payload, format='json')
        stack_id = create_response.json()['id']

        response = self.client.post(f'/api/iac/stacks/{stack_id}/sync_cmdb/', format='json')

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['summary']['resource_count'], 6)
        self.assertEqual(TerraformResourceBinding.objects.filter(stack_id=stack_id).count(), 6)
        self.assertEqual(ConfigItem.objects.count(), 6)
        self.assertTrue(CIRelation.objects.filter(relation_type='depends_on').exists())

    def test_sync_cmdb_endpoint_uses_custom_topology_relations(self):
        payload = copy.deepcopy(self.aliyun_payload)
        payload['config']['resources']['rds']['enabled'] = True
        payload['config']['resources']['load_balancer']['enabled'] = True
        payload['config']['topology'] = {
            'relations': [
                {
                    'source': 'load_balancer',
                    'target': 'rds',
                    'relation_type': 'connects_to',
                    'description': 'SLB forwards traffic to database proxy',
                }
            ]
        }

        create_response = self.client.post('/api/iac/stacks/', payload, format='json')
        stack_id = create_response.json()['id']

        response = self.client.post(f'/api/iac/stacks/{stack_id}/sync_cmdb/', format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(CIRelation.objects.filter(
            relation_type='connects_to',
            description='SLB forwards traffic to database proxy',
        ).exists())
        self.assertTrue(TerraformResourceBinding.objects.filter(stack_id=stack_id, resource_key='rds').exists())

        detail_response = self.client.get(f'/api/iac/stacks/{stack_id}/')
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(len(detail_response.json()['resource_bindings']), 6)

    def test_sync_cmdb_endpoint_supports_multiple_servers_and_buckets(self):
        payload = copy.deepcopy(self.aliyun_payload)
        payload['config']['compute']['instances'] = [
            {
                'instance_name': 'prod-web-01',
                'instance_type': 'ecs.g6.large',
                'image_id': 'ubuntu_22_04_x64_20G_alibase_20240111.vhd',
                'system_disk_type': 'cloud_essd',
                'system_disk_size': 40,
                'public_bandwidth': 5,
            },
            {
                'instance_name': 'prod-web-02',
                'instance_type': 'ecs.g6.xlarge',
                'image_id': 'ubuntu_22_04_x64_20G_alibase_20240111.vhd',
                'system_disk_type': 'cloud_essd',
                'system_disk_size': 80,
                'public_bandwidth': 10,
            },
        ]
        payload['config']['resources']['object_storage'] = {
            'enabled': True,
            'bucket_name': 'sxdevops-prod-artifacts',
            'acl': 'private',
            'storage_class': 'Standard',
            'buckets': [
                {'bucket_name': 'sxdevops-prod-artifacts', 'acl': 'private', 'storage_class': 'Standard'},
                {'bucket_name': 'sxdevops-prod-logs', 'acl': 'private', 'storage_class': 'IA'},
            ],
        }

        create_response = self.client.post('/api/iac/stacks/', payload, format='json')
        stack_id = create_response.json()['id']

        response = self.client.post(f'/api/iac/stacks/{stack_id}/sync_cmdb/', format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary']['resource_count'], 7)
        self.assertTrue(TerraformResourceBinding.objects.filter(stack_id=stack_id, resource_key='compute_2').exists())
        self.assertTrue(TerraformResourceBinding.objects.filter(stack_id=stack_id, resource_key='object_storage_2').exists())
