from django.core.management import call_command
from django.test import TestCase

from cmdb.models import CISourceMapping, CISyncJob, CIType, ConfigItem, ResourceNode, ResourceRequest
from multicloud.models import CloudCredential, CloudEnvironment


class CleanupCmdbDemoCommandTests(TestCase):
    def setUp(self):
        self.ci_type = CIType.objects.create(name='Server', code='TEST_SERVER')
        self.demo_credential = CloudCredential.objects.create(
            provider='aliyun',
            name='aliyun-demo',
            account_id='100001',
            account_name='trade-prod',
            auth_mode='demo',
            access_key_id='demo-ak',
            access_key_secret='demo-sk',
            default_region='cn-hangzhou',
            demo_mode=True,
        )
        self.demo_environment = CloudEnvironment.objects.create(
            credential=self.demo_credential,
            name='demo-env',
            code='trade-prod-hz',
            region='cn-hangzhou',
        )
        self.demo_synced_ci = ConfigItem.objects.create(
            name='demo-ecs',
            ci_type=self.ci_type,
            attributes={
                'cmdb_source': 'multicloud',
                'account_id': self.demo_credential.account_id,
                'account_name': self.demo_credential.account_name,
                'cloud_env_code': self.demo_environment.code,
            },
        )
        self.real_synced_ci = ConfigItem.objects.create(
            name='real-ecs',
            ci_type=self.ci_type,
            attributes={'cmdb_source': 'multicloud', 'account_id': 'real-account'},
        )
        CISourceMapping.objects.create(
            ci=self.real_synced_ci,
            source_type='aliyun_ecs',
            source_account='real-account',
            source_region='cn-hangzhou',
            source_unique_id='i-real-001',
        )
        self.manual_ci = ConfigItem.objects.create(name='manual-demo', ci_type=self.ci_type, attributes={})
        self.demo_job = CISyncJob.objects.create(
            name='Demo sync',
            source_type='aliyun_ecs',
            config={'auth_mode': 'demo', 'source_account': 'trade-prod'},
        )
        self.orphan_ci = ConfigItem.objects.create(
            name='stale-prod-ecs',
            ci_type=self.ci_type,
            attributes={'source_account': 'stale-prod', 'source_unique_id': 'i-stale-prod-001'},
        )
        CISourceMapping.objects.create(
            ci=self.orphan_ci,
            source_type='aliyun_ecs',
            source_account='stale-prod',
            source_region='cn-hangzhou',
            source_unique_id='i-stale-prod-001',
        )
        self.orphan_job = CISyncJob.objects.create(
            name='Stale cloud account sync',
            source_type='aliyun_ecs',
            config={'cloud_account_id': '999999', 'source_account': 'stale-prod'},
        )
        ResourceRequest.objects.create(applicant='tester', resource_type='server', reason='demo')
        ResourceNode.objects.create(name='demo-node', node_type='biz')

    def test_dry_run_does_not_delete_data(self):
        call_command('cleanup_cmdb_demo', '--dry-run', '--purge-unmapped')

        self.assertTrue(ConfigItem.objects.filter(id=self.demo_synced_ci.id).exists())
        self.assertTrue(ConfigItem.objects.filter(id=self.manual_ci.id).exists())
        self.assertTrue(CloudCredential.objects.filter(id=self.demo_credential.id).exists())

    def test_cleanup_removes_demo_and_unmapped_data_but_keeps_real_synced_items(self):
        call_command('cleanup_cmdb_demo', '--purge-unmapped')

        self.assertFalse(ConfigItem.objects.filter(id=self.demo_synced_ci.id).exists())
        self.assertFalse(ConfigItem.objects.filter(id=self.manual_ci.id).exists())
        self.assertFalse(CISyncJob.objects.filter(id=self.demo_job.id).exists())
        self.assertFalse(ConfigItem.objects.filter(id=self.orphan_ci.id).exists())
        self.assertFalse(CISyncJob.objects.filter(id=self.orphan_job.id).exists())
        self.assertFalse(CloudCredential.objects.filter(id=self.demo_credential.id).exists())
        self.assertFalse(ResourceRequest.objects.exists())
        self.assertFalse(ResourceNode.objects.exists())
        self.assertTrue(ConfigItem.objects.filter(id=self.real_synced_ci.id).exists())
        self.assertTrue(CISourceMapping.objects.filter(ci=self.real_synced_ci).exists())
