from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ops.models import GrafanaSetting

from .langgraph_pilot import _slo_panels_node
from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsKnowledgeEnvironment
from .services import query_dashboard_panel_data


class SLOServicePanelScopeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username='slo-scope-admin')
        self.session = AIOpsChatSession.objects.create(user=self.user)
        self.message = AIOpsChatMessage.objects.create(session=self.session, role='user', content='评估服务 SLO')
        self.environment = {
            'name': '交易平台生产环境', 'event_environments': ['prod'], 'alert_environments': ['prod'],
            'k8s_namespaces': {'1': ['production']}, 'grafana_folder_keys': ['commerce'],
        }
        AIOpsKnowledgeEnvironment.objects.create(**self.environment)
        GrafanaSetting.objects.create(name='default', url='http://grafana.internal.local', dashboards=[{
            'key': 'commerce-slo', 'title': 'Service SLO', 'folder': 'commerce/app',
        }])

    def state(self, service):
        return {
            'slo_environment': self.environment, 'slo_service': service,
            'slo_query': f'交易平台生产环境 {service} 最近30分钟 SLO', 'slo_duration_minutes': 30,
        }

    def panel_arguments(self, state):
        with mock.patch('aiops.langgraph_pilot._slo_collect_node', return_value={}) as collector:
            _slo_panels_node(state)
        self.assertEqual(collector.call_args.args[2:4], ('slo_panels', 'query_dashboard_panel_data'))
        return collector.call_args.args[4]

    def dashboard_payload(self):
        selector = '{environment="$environment",namespace="$namespace",service="$service"}'
        total = f'sum(rate(http_requests_total{selector}[$__rate_interval]))'
        expressions = [
            '100 * sum(rate(http_requests_total{environment="$environment",namespace="$namespace",service="$service",status!~"5.."}[$__rate_interval]))'
            + f' / clamp_min({total}, 0.001)',
            '100 * sum(rate(http_requests_total{environment="$environment",namespace="$namespace",service="$service",status=~"5.."}[$__rate_interval]))'
            + f' / clamp_min({total}, 0.001)',
            f'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{selector}[$__rate_interval])))',
            f'100 * avg_over_time(commerce_service_available{selector}[$__range])',
        ]
        return {'dashboard': {
            'title': 'Commerce SLO',
            'templating': {'list': [
                {'name': 'service', 'current': {'value': 'api-gateway'}},
                {'name': 'namespace', 'current': {'value': 'default'}},
                {'name': 'environment', 'current': {'value': 'staging'}},
            ]},
            'panels': [{'id': 1, 'title': 'Service Success, 5xx, P95 and Availability', 'targets': [
                {'expr': expression, 'datasource': {'type': 'prometheus', 'uid': 'commerce-prom'}}
                for expression in expressions
            ]}],
        }}

    @mock.patch('ops.observability_views.execute_promql_query')
    @mock.patch('ops.observability_views.http_requests.get')
    def test_order_and_payment_override_gateway_default_for_all_four_queries(self, grafana_get, promql):
        grafana_get.return_value = mock.Mock(status_code=200)
        grafana_get.return_value.json.return_value = self.dashboard_payload()
        promql.side_effect = lambda expression, **kwargs: {
            'query': expression, 'series_count': 1, 'result': [{'metric': {}, 'values': [[1, '1']]}],
        }
        end = timezone.now()
        for service in ['order-service', 'payment-service']:
            with self.subTest(service=service):
                promql.reset_mock()
                arguments = self.panel_arguments(self.state(service))
                with mock.patch('aiops.services.timezone.now', return_value=end):
                    result = query_dashboard_panel_data(self.session, self.message, self.user, **arguments)
                self.assertEqual(result['summary']['query_count'], 4)
                self.assertEqual(promql.call_count, 4)
                for call in promql.call_args_list:
                    expression = call.args[0]
                    self.assertIn(f'service="{service}"', expression)
                    self.assertIn('namespace="production"', expression)
                    self.assertIn('environment="prod"', expression)
                    self.assertNotIn('api-gateway', expression)
                    self.assertNotIn('$', expression)
                    self.assertEqual(call.kwargs['start_time'], end - timedelta(minutes=30))
                    self.assertEqual(call.kwargs['end_time'], end)
                    self.assertEqual(call.kwargs['step'], 60)
                    self.assertEqual(call.kwargs['datasource_uid'], 'commerce-prom')
                self.assertIn('[240s]', promql.call_args_list[0].args[0])
                self.assertIn('[1800s]', promql.call_args_list[3].args[0])

    def test_missing_service_does_not_override_dashboard_with_empty_value(self):
        arguments = self.panel_arguments(self.state(''))
        self.assertEqual(arguments['variables'], {'namespace': 'production', 'environment': 'prod'})
        self.assertEqual(arguments['limit'], 4)

    def test_unique_alert_source_is_used_when_event_sources_are_ambiguous(self):
        state = self.state('order-service')
        state['slo_environment'] = {**self.environment, 'event_environments': ['prod', 'staging']}
        self.assertEqual(self.panel_arguments(state)['variables']['environment'], 'prod')

    def test_ambiguous_sources_and_namespaces_are_not_inferred(self):
        state = self.state('order-service')
        state['slo_environment'] = {
            **self.environment, 'event_environments': ['prod', 'staging'],
            'alert_environments': ['prod', 'test'], 'k8s_namespaces': {'1': ['production', 'staging']},
        }
        self.assertEqual(self.panel_arguments(state)['variables'], {'service': 'order-service'})
