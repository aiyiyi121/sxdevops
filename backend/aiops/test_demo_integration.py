import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from ops.models import GrafanaSetting, HostTask, K8sCluster, TaskResource, TaskResourceGroup
from ops.tracing_providers import _search_jaeger_traces

from . import services


class AssistantDemoIntegrationTests(TestCase):
    def test_folder_key_catalog_can_select_environment_dashboard(self):
        GrafanaSetting.objects.create(name='demo-catalog', enabled=True, dashboards=[
            {'key': 'commerce-slo', 'folder_key': 'platform', 'title': 'Commerce SLO'},
            {'key': 'private-slo', 'folder_key': 'private', 'title': 'Private SLO'},
        ])
        environment = {'grafana_folder_keys': ['platform']}
        self.assertEqual(services._select_dashboard_key_for_analysis(environment, '评估 SLO'), 'commerce-slo')

    def test_explicit_namespace_excludes_staging_resource_and_deduplicates_target(self):
        cluster = K8sCluster(id=1, name='platform-production')
        environment = TaskResourceGroup(id=1, name='生产环境')
        sources = [
            TaskResource(id=2, name='会员预发布', cluster=cluster, environment=environment, namespace='staging'),
            TaskResource(id=1, name='订单服务', cluster=cluster, environment=environment, namespace='production'),
            TaskResource(id=3, name='订单别名', cluster=cluster, environment=environment, namespace='production'),
        ]
        targets = services._build_k8s_target_items(sources, namespace='production', name='order-api', kind='deployment')
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]['resource_id'], 1)
        self.assertEqual(targets[0]['namespace'], 'production')

    def test_unscoped_k8s_targets_preserve_distinct_namespaces(self):
        cluster = K8sCluster(id=1, name='platform-production')
        sources = [
            TaskResource(id=1, name='订单生产', cluster=cluster, namespace='production'),
            TaskResource(id=2, name='订单预发布', cluster=cluster, namespace='staging'),
        ]
        targets = services._build_k8s_target_items(sources, name='order-api', kind='deployment')
        self.assertEqual({target['namespace'] for target in targets}, {'production', 'staging'})

    def test_k8s_drafts_only_reference_resources_selected_for_final_targets(self):
        user = get_user_model().objects.create_superuser(username='demo-k8s-draft')
        cluster = K8sCluster(id=1, name='platform-production')
        environment = TaskResourceGroup(id=1, name='生产环境')
        sources = [
            TaskResource(id=2, name='订单别名', cluster=cluster, environment=environment, namespace='staging'),
            TaskResource(id=1, name='订单服务', cluster=cluster, environment=environment, namespace='production'),
            TaskResource(id=3, name='订单生产别名', cluster=cluster, environment=environment, namespace='production'),
        ]
        cases = [
            ('service', '生成任务把 production 命名空间 svc order-api 改为 NodePort', {
                'service_name': 'order-api', 'service_type': 'NodePort',
            }),
            ('helm', '生成任务在 K8s production 命名空间用 Helm 部署 Redis', {
                'software_name': 'redis', 'deployment_strategy': 'helm', 'chart': 'bitnami/redis',
            }),
            ('manifest', '生成任务在 K8s production 命名空间部署 Redis', {'software_name': 'redis'}),
            ('scale', '生成任务把 production 命名空间 deployment order-api 扩容到 3 个副本', {
                'workload_name': 'order-api', 'replicas': 3,
            }),
            ('restart', '生成任务重启 production 命名空间 pod order-api-0', {'pod_name': 'order-api-0'}),
        ]
        for case, question, arguments in cases:
            with self.subTest(case=case), mock.patch(
                'aiops.services._resolve_k8s_task_resource_targets', return_value=(sources, {'name': '生产环境'}),
            ):
                draft = services.build_task_draft(user, question, {'namespace': 'production', **arguments})

                self.assertNotIn('error', draft)
                self.assertEqual(draft['host_count'], 1)
                self.assertEqual(draft['resource_ids'], [1])
                self.assertEqual([target['resource_id'] for target in draft['k8s_targets']], [1])
                self.assertEqual([target['resource_id'] for target in draft['target_hosts']], [1])
        self.assertFalse(HostTask.objects.exists())

    def test_jaeger_finds_errors_before_applying_result_limit(self):
        def backend(url, params, config):
            if json.loads(params.get('tags', '{}')).get('error') == 'true':
                return {'data': [{'traceID': 'older-error'}]}
            return {'data': [{'traceID': 'newest-success'}]}

        def summary(trace, preferred_service=''):
            return {'trace_id': trace['traceID'], 'is_error': trace['traceID'] == 'older-error'}

        with mock.patch('ops.tracing_providers._http_get', side_effect=backend), \
                mock.patch('ops.tracing_providers._jaeger_trace_summary', side_effect=summary):
            errors = _search_jaeger_traces(
                {'query_url': 'http://jaeger'},
                {'service_id': 'order-service', 'trace_state': 'ERROR', 'limit': 1}, [],
            )
        self.assertEqual([trace['trace_id'] for trace in errors], ['older-error'])
