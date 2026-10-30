from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from rbac.models import PermissionDefinition, Role
from rbac.services import ensure_builtin_rbac

from .models import CIResourceAuthorization, CIResourceMetricSnapshot, CIType, ConfigItem
from .serializers import ConfigItemSerializer
from .views import _average_resource_usage_by_ci, _latest_capacity_metric_snapshots, _latest_metric_snapshot_rows_for_ci_ids


class DashboardMetricQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ci_type = CIType.objects.create(name='Metric query test')
        cls.asset = ConfigItem.objects.create(name='server-a', ci_type=ci_type)
        cls.other = ConfigItem.objects.create(name='server-b', ci_type=ci_type)
        cls.user = get_user_model().objects.create_superuser('metric-admin', password='Test@123456')

    def setUp(self):
        cache.clear()
        self.now = timezone.now()

    def snapshot(self, asset=None, metric='cpu_usage', usage=95, collected_at=None):
        return CIResourceMetricSnapshot.objects.create(
            ci=asset or self.asset, metric=metric, value=usage or 0,
            usage_percent=usage, collected_at=collected_at or self.now, unit='%',
        )

    def test_database_returns_only_latest_non_null_sample_per_asset_and_metric(self):
        self.snapshot(collected_at=self.now - timedelta(days=1))
        first = self.snapshot(usage=50)
        latest = self.snapshot(usage=60)
        self.snapshot(usage=None, collected_at=self.now + timedelta(minutes=1))
        memory = self.snapshot(metric='memory_usage', usage=20)
        other = self.snapshot(asset=self.other, usage=30)
        self.snapshot(asset=self.other, metric='disk_usage', usage=None)

        with self.assertNumQueries(3):
            rows = list(_latest_capacity_metric_snapshots(ConfigItem.objects.values('pk')))
            self.assertEqual({row.pk for row in rows}, {latest.pk, memory.pk, other.pk})
            self.assertNotIn(first.pk, {row.pk for row in rows})
            self.assertTrue(all(row.ci.ci_type.name == 'Metric query test' for row in rows))

    def test_latest_uses_collection_time_before_id_and_obeys_asset_scope(self):
        latest = self.snapshot(usage=25)
        self.snapshot(usage=98, collected_at=self.now - timedelta(days=2))
        self.snapshot(asset=self.other)

        rows = list(_latest_capacity_metric_snapshots([self.asset.pk]))

        self.assertEqual([row.pk for row in rows], [latest.pk])
        self.assertEqual(list(_latest_capacity_metric_snapshots([])), [])

    def test_history_is_not_materialized_as_models_for_dashboard_query(self):
        CIResourceMetricSnapshot.objects.bulk_create([
            CIResourceMetricSnapshot(
                ci=self.asset, metric='cpu_usage', value=99, usage_percent=99,
                collected_at=self.now - timedelta(minutes=offset + 1),
            )
            for offset in range(300)
        ])
        latest = self.snapshot(usage=25)
        with patch.object(CIResourceMetricSnapshot, 'from_db', wraps=CIResourceMetricSnapshot.from_db) as materialize:
            snapshots = _latest_capacity_metric_snapshots([self.asset.pk])
            rows = list(snapshots)

        self.assertEqual([row.pk for row in rows], [latest.pk])
        self.assertEqual(materialize.call_count, 1)
        self.assertEqual(len(snapshots._result_cache), 1)

    def test_sparse_metrics_are_returned_without_loading_frequent_history(self):
        memory = self.snapshot(metric='memory_usage', usage=0, collected_at=self.now - timedelta(days=3))
        other = self.snapshot(asset=self.other, collected_at=self.now - timedelta(days=2))
        CIResourceMetricSnapshot.objects.bulk_create([
            CIResourceMetricSnapshot(
                ci=self.asset, metric='cpu_usage', value=99, usage_percent=99,
                collected_at=self.now - timedelta(minutes=offset + 1),
            )
            for offset in range(300)
        ])
        latest = self.snapshot(usage=None)

        with patch.object(CIResourceMetricSnapshot, 'from_db', wraps=CIResourceMetricSnapshot.from_db) as materialize:
            rows = _latest_metric_snapshot_rows_for_ci_ids([self.asset.pk, self.other.pk])
        self.assertEqual({row.pk for row in rows}, {memory.pk, other.pk, latest.pk})
        self.assertEqual(materialize.call_count, 3)
        self.assertEqual(
            {row['id'] for row in ConfigItemSerializer(self.asset).data['latest_metric_snapshots']},
            {memory.pk, latest.pk},
        )

        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get('/api/cmdb/resource-metrics/latest/', {'ci_ids': f'{self.asset.pk},{self.other.pk}'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual({row['id'] for row in response.data}, {memory.pk, other.pk, latest.pk})
        response = client.get('/api/cmdb/config-items/', {'ci_type': self.asset.ci_type_id})
        self.assertEqual(response.status_code, 200, response.data)
        row = next(row for row in response.data['results'] if row['id'] == self.asset.pk)
        self.assertEqual({metric['id'] for metric in row['latest_metric_snapshots']}, {memory.pk, latest.pk})

    def test_latest_endpoint_preserves_source_date_search_and_metric_filters(self):
        earlier = self.snapshot(usage=10, collected_at=self.now - timedelta(days=1))
        CIResourceMetricSnapshot.objects.filter(pk=earlier.pk).update(source='monitor')
        latest = self.snapshot(usage=20)
        CIResourceMetricSnapshot.objects.filter(pk=latest.pk).update(source='monitor')
        self.snapshot(metric='memory_usage')
        self.snapshot(asset=self.other)
        self.snapshot(collected_at=self.now + timedelta(days=1))
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.get('/api/cmdb/resource-metrics/latest/', {
            'source': 'monitor', 'metric': 'cpu_usage', 'search': self.asset.name,
            'collected_after': (self.now - timedelta(hours=1)).isoformat(),
            'collected_before': self.now.isoformat(),
        })

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row['id'] for row in response.data], [latest.pk])

    def test_latest_endpoint_and_capacity_queries_obey_resource_authorizations(self):
        ensure_builtin_rbac()
        role = Role.objects.create(code='metric-reader', name='Metric Reader')
        role.permissions.add(
            PermissionDefinition.objects.get(code='cmdb.ci.view'),
            PermissionDefinition.objects.get(code='cmdb.dashboard.view'),
        )
        user = get_user_model().objects.create_user('metric-reader', password='Test@123456')
        user.rbac_roles.add(role)
        ConfigItem.objects.filter(pk=self.asset.pk).update(business_line='allowed')
        CIResourceAuthorization.objects.create(
            name='Allowed metrics', principal_type='user', principal=user.username,
            permission='view', business_line='allowed',
        )
        allowed = self.snapshot(metric='custom_capacity')
        self.snapshot(asset=self.other, metric='custom_capacity')
        self.snapshot(asset=self.other, metric='private_capacity')
        client = APIClient()
        client.force_authenticate(user)

        response = client.get('/api/cmdb/resource-metrics/latest/', {'metrics': 'custom_capacity'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row['id'] for row in response.data], [allowed.pk])
        for path in ('dashboard/stats/', 'governance/risks/'):
            response = client.get('/api/cmdb/' + path)
            self.assertEqual(response.status_code, 200, response.data)
            risks = response.data['capacity_waterline']['top_risks']
            self.assertEqual([(row['ci_id'], row['metric']) for row in risks], [(self.asset.pk, 'custom_capacity')])

    def test_cost_averages_are_aggregated_without_materializing_history(self):
        self.snapshot(usage=0)
        self.snapshot(usage=20)
        self.snapshot(usage=None)
        self.snapshot(usage=100, collected_at=self.now - timedelta(days=15))
        self.snapshot(metric='memory_usage', usage=0)
        self.snapshot(metric='disk_usage', usage=100)
        self.snapshot(asset=self.other, usage=100)

        with self.assertNumQueries(1), patch.object(CIResourceMetricSnapshot, 'from_db', wraps=CIResourceMetricSnapshot.from_db) as materialize:
            averages = _average_resource_usage_by_ci([self.asset.pk])

        self.assertEqual(averages, {self.asset.pk: {'cpu': Decimal('10.00'), 'memory': Decimal('0.00')}})
        self.assertEqual(materialize.call_count, 0)
        self.assertEqual(_average_resource_usage_by_ci([]), {})

    def test_merging_assets_moves_history_without_materializing_it(self):
        CIResourceMetricSnapshot.objects.bulk_create([
            CIResourceMetricSnapshot(
                ci=self.other, metric='cpu_usage', value=offset, usage_percent=offset,
                collected_at=self.now - timedelta(minutes=offset),
            )
            for offset in range(300)
        ])
        client = APIClient()
        client.force_authenticate(self.user)

        with patch.object(CIResourceMetricSnapshot, 'from_db', wraps=CIResourceMetricSnapshot.from_db) as materialize:
            response = client.post(
                f'/api/cmdb/config-items/{self.asset.pk}/merge-duplicates/',
                {'source_ids': [self.other.pk]}, format='json',
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['moved_counts']['resource_metrics'], 300)
        self.assertEqual(CIResourceMetricSnapshot.objects.filter(ci=self.asset).count(), 300)
        self.assertFalse(CIResourceMetricSnapshot.objects.filter(ci=self.other).exists())
        self.assertLessEqual(materialize.call_count, 1)

    def test_dashboard_and_governance_count_latest_waterline_values(self):
        self.snapshot(usage=99, collected_at=self.now - timedelta(days=1))
        self.snapshot(usage=20)
        self.snapshot(metric='memory_usage', usage=99)
        client = APIClient()
        client.force_authenticate(self.user)

        for path in ('dashboard/stats/', 'governance/risks/'):
            with self.subTest(path=path):
                response = client.get('/api/cmdb/' + path)
                self.assertEqual(response.status_code, 200, response.data)
                waterline = response.data['capacity_waterline']
                self.assertEqual(waterline['normal'], 1)
                self.assertEqual(waterline['exceeded'], 1)
                self.assertEqual(len(waterline['top_risks']), 1)
                self.assertEqual(waterline['top_risks'][0]['metric'], 'memory_usage')
