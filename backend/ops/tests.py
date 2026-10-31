from urllib.parse import quote
import copy
from datetime import datetime, timedelta
from decimal import Decimal
import ssl
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import OperationalError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from ops.models import (
    Alert,
    AlertAction,
    AlertIntegration,
    AlertNotificationChannel,
    AlertNotificationRule,
    AlertRecipient,
    AlertRecipientGroup,
    DockerHost,
    SystemPostureSystem,
    SystemPostureSLAHistory,
    GrafanaSetting,
    Host,
    K8sCluster,
    K8sConfigRevision,
    LogDataSource,
    MetricDataSource,
    ObservabilityDataSourceLink,
    TracingDataSource,
)
from ops.k8s_views import _K8sApiProxy, _prepare_kubeconfig, _resource_stale_cache_key, _summary_stale_cache_key
from ops.observability_views import ECOMMERCE_DEPENDENCIES, ECOMMERCE_SERVICE_SPECS
from ops.tracing_providers import (
    _build_topology_from_trace_details,
    _search_skywalking_traces,
    _tempo_flatten_trace,
    _trace_detail_from_spans,
)


TEST_LOG_PROVIDER_CONFIGS = {
    'loki': {
        'endpoint': 'http://loki.example:3100',
    },
    'elk': {
        'endpoint': 'https://es.example.com:9200',
        'auth_type': 'none',
        'index_pattern': 'logs-*',
        'time_field': '@timestamp',
        'message_fields': 'message,log,msg',
    },
    'sls': {
        'endpoint': 'cn-hangzhou.log.aliyuncs.com',
        'project': 'demo-project',
        'logstore': 'app-logstore',
        'topic': '',
        'access_key_id': 'test-ak',
        'access_key_secret': 'test-sk',
    },
}

TEST_OBSERVABILITY_CONFIG = {
    'skywalking': {
        'enabled': True,
        'ui_url': 'http://skywalking.example.com',
        'oap_url': 'http://skywalking-oap.example.com',
        'graphql_path': '/graphql',
        'default_layer': '',
        'demo_mode': True,
    },
    'grafana': {
        'enabled': True,
        'url': 'http://grafana.example.com',
        'default_path': '/d/apm-overview',
        'demo_mode': True,
    },
}


class MockHttpResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = str(payload)
        self.headers = headers or {}

    def json(self):
        return self.payload


@override_settings(LOG_PROVIDER_CONFIGS=TEST_LOG_PROVIDER_CONFIGS)
class LogViewsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_superuser('ops-admin', 'ops@example.com', 'Admin@123456')
        self.client.force_authenticate(user=self.user)

    def test_log_providers_returns_loki_elk_and_sls(self):
        response = self.client.get('/api/log/providers/')

        self.assertEqual(response.status_code, 200)
        providers = response.json()['providers']
        self.assertEqual([item['id'] for item in providers], ['loki', 'elk', 'sls'])
        self.assertEqual(providers[0]['defaults']['endpoint'], 'http://loki.example:3100')

    def test_can_create_log_datasource(self):
        response = self.client.post(
            '/api/log/datasources/',
            {
                'name': 'Production Loki',
                'provider': 'loki',
                'description': 'Production application logs',
                'is_enabled': True,
                'is_default': True,
                'config': {'endpoint': 'http://loki.internal:3100'},
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload['name'], 'Production Loki')
        self.assertEqual(payload['config']['endpoint'], 'http://loki.internal:3100')

    @patch('ops.log_views.http_requests.get')
    def test_datasource_test_connection_uses_saved_config(self, mock_get):
        create_response = self.client.post(
            '/api/log/datasources/',
            {
                'name': 'Loki Test Source',
                'provider': 'loki',
                'config': {'endpoint': 'http://saved-loki:3100'},
            },
            format='json',
        )
        datasource_id = create_response.json()['id']

        mock_get.return_value = MockHttpResponse({'data': ['job', 'namespace']})

        response = self.client.post(f'/api/log/datasources/{datasource_id}/test_connection/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['preview_kind'], 'labels')
        mock_get.assert_called_once()

    @patch('ops.log_views.http_requests.get')
    def test_loki_query_normalizes_response(self, mock_get):
        mock_get.return_value = MockHttpResponse(
            {
                'data': {
                    'result': [
                        {
                            'stream': {'job': 'gateway', 'level': 'error'},
                            'values': [
                                ['1710000000000000000', 'request timeout'],
                                ['1710000001000000000', 'handled request'],
                            ],
                        }
                    ]
                }
            }
        )

        response = self.client.post(
            '/api/log/query/',
            {
                'provider': 'loki',
                'query': '{job="gateway"}',
                'start_ms': '1710000000000',
                'end_ms': '1710003600000',
                'limit': 100,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['provider'], 'loki')
        self.assertEqual(payload['total'], 2)
        self.assertEqual(payload['logs'][0]['source'], 'gateway')
        self.assertEqual(payload['logs'][0]['level'], 'error')
        self.assertTrue(payload['logs'][0]['timestamp'].endswith('Z'))
        mock_get.assert_called_once()

    @patch('ops.log_views.http_requests.get')
    def test_loki_query_can_use_saved_datasource(self, mock_get):
        create_response = self.client.post(
            '/api/log/datasources/',
            {
                'name': 'Saved Loki',
                'provider': 'loki',
                'config': {'endpoint': 'http://saved-loki:3100'},
            },
            format='json',
        )
        datasource_id = create_response.json()['id']
        mock_get.return_value = MockHttpResponse(
            {
                'data': {
                    'result': [
                        {
                            'stream': {'job': 'api'},
                            'values': [['1710000000000000000', 'api started']],
                        }
                    ]
                }
            }
        )

        response = self.client.post(
            '/api/log/query/',
            {
                'datasource_id': datasource_id,
                'query': '{job="api"}',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['logs'][0]['source'], 'api')

    def test_demo_loki_catalog_and_query_return_fake_logs(self):
        response = self.client.post(
            '/api/log/datasources/',
            {
                'name': 'Loki Demo CN',
                'provider': 'loki',
                'config': {
                    'endpoint': 'http://demo-loki.example.com:3100',
                    'demo_mode': True,
                },
            },
            format='json',
        )
        datasource_id = response.json()['id']

        catalog_response = self.client.post(
            '/api/log/providers/loki/catalog/',
            {
                'datasource_id': datasource_id,
                'action': 'labels',
            },
            format='json',
        )
        self.assertEqual(catalog_response.status_code, 200)
        self.assertIn('job', catalog_response.json()['items'])

        query_response = self.client.post(
            '/api/log/query/',
            {
                'datasource_id': datasource_id,
                'query': '{job="gateway-service"} |= "timeout"',
                'limit': 50,
            },
            format='json',
        )

        self.assertEqual(query_response.status_code, 200)
        payload = query_response.json()
        self.assertEqual(payload['provider'], 'loki')
        self.assertGreaterEqual(payload['total'], 1)
        self.assertEqual(payload['logs'][0]['source'], 'gateway-service')
        self.assertIn('timeout', payload['logs'][0]['message'])
        self.assertIn('trace_id', payload['logs'][0]['attributes'])

        label_values_response = self.client.post(
            '/api/log/providers/loki/catalog/',
            {
                'datasource_id': datasource_id,
                'action': 'label_values',
                'label': 'release',
            },
            format='json',
        )
        self.assertEqual(label_values_response.status_code, 200)
        self.assertIn('gray', label_values_response.json()['items'])

    def test_demo_loki_supports_stacktrace_and_gray_release_queries(self):
        response = self.client.post(
            '/api/log/datasources/',
            {
                'name': 'Loki Demo Spring Cloud',
                'provider': 'loki',
                'config': {
                    'endpoint': 'http://demo-loki.example.com:3100',
                    'demo_mode': True,
                },
            },
            format='json',
        )

        stack_response = self.client.post(
            '/api/log/query/',
            {
                'datasource_id': response.json()['id'],
                'query': '{job="payment-service"} |= "NullPointerException"',
                'limit': 20,
            },
            format='json',
        )
        self.assertEqual(stack_response.status_code, 200)
        self.assertGreaterEqual(stack_response.json()['total'], 1)
        self.assertIn('PaymentCallbackController', stack_response.json()['logs'][0]['message'])

        gray_response = self.client.post(
            '/api/log/query/',
            {
                'datasource_id': response.json()['id'],
                'query': '{release="gray"} |= "tenantId"',
                'limit': 20,
            },
            format='json',
        )
        self.assertEqual(gray_response.status_code, 200)
        self.assertGreaterEqual(gray_response.json()['total'], 1)
        self.assertEqual(gray_response.json()['logs'][0]['attributes']['release'], 'gray')

    @patch('ops.log_views.http_requests.request')
    def test_elk_catalog_lists_indices(self, mock_request):
        mock_request.return_value = MockHttpResponse(
            [
                {'index': 'logs-prod-2026.03.15', 'docs.count': '12', 'store.size': '48kb'},
                {'index': 'logs-stage-2026.03.15', 'docs.count': '6', 'store.size': '18kb'},
            ]
        )

        response = self.client.post(
            '/api/log/providers/elk/catalog/',
            {
                'config': {'endpoint': 'https://es.example.com:9200'},
                'index_pattern': 'logs-*',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['kind'], 'indices')
        self.assertEqual(payload['items'][0]['name'], 'logs-prod-2026.03.15')
        self.assertEqual(payload['items'][1]['docs_count'], '6')

    @patch('ops.log_views.http_requests.request')
    def test_elk_query_accepts_iso_timestamps(self, mock_request):
        mock_request.return_value = MockHttpResponse(
            {
                'took': 21,
                'hits': {
                    'total': {'value': 1},
                    'hits': [
                        {
                            '_index': 'logs-prod-2026.03.15',
                            '_source': {
                                '@timestamp': '2026-03-15T08:30:00Z',
                                'message': 'payment error in checkout',
                                'level': 'ERROR',
                                'service': {'name': 'payment'},
                            },
                        }
                    ],
                },
            }
        )

        response = self.client.post(
            '/api/log/query/',
            {
                'provider': 'elk',
                'query': 'service.name:"payment"',
                'source': 'logs-prod-*',
                'start_ms': '1710000000000',
                'end_ms': '1710003600000',
                'limit': 50,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['provider'], 'elk')
        self.assertEqual(payload['took_ms'], 21)
        self.assertEqual(payload['logs'][0]['timestamp'], '2026-03-15T08:30:00Z')
        self.assertEqual(payload['logs'][0]['level'], 'error')
        self.assertEqual(payload['logs'][0]['source'], 'logs-prod-2026.03.15')

    @patch('ops.log_views.http_requests.request')
    def test_elk_query_preserves_integer_total_from_elasticsearch(self, mock_request):
        mock_request.return_value = MockHttpResponse({
            'took': 5,
            'hits': {
                'total': 17,
                'hits': [{'_index': 'logs-prod', '_source': {'@timestamp': '2026-03-15T08:30:00Z', 'message': 'ok'}}],
            },
        })

        response = self.client.post(
            '/api/log/query/',
            {'provider': 'elk', 'query': '', 'source': 'logs-*'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total'], 17)

    def test_demo_elk_query_returns_fake_logs_without_network(self):
        response = self.client.post(
            '/api/log/datasources/',
            {
                'name': 'ELK Demo CN',
                'provider': 'elk',
                'config': {
                    'endpoint': 'https://demo-elastic.example.com:9200',
                    'index_pattern': 'logs-demo-*',
                    'time_field': '@timestamp',
                    'message_fields': 'message,log,msg',
                    'demo_mode': True,
                    'demo_indices': ['logs-demo-app-2026.03.15', 'logs-demo-security-2026.03.15'],
                },
            },
            format='json',
        )
        datasource_id = response.json()['id']

        query_response = self.client.post(
            '/api/log/query/',
            {
                'datasource_id': datasource_id,
                'query': 'payment error',
                'source': 'logs-demo-*',
            },
            format='json',
        )

        self.assertEqual(query_response.status_code, 200)
        payload = query_response.json()
        self.assertEqual(payload['provider'], 'elk')
        self.assertGreaterEqual(payload['total'], 1)
        self.assertIn('payment', payload['logs'][0]['message'])
        self.assertIn('trace_id', payload['logs'][0]['attributes'])
        self.assertIn('com.sxdevops', payload['logs'][0]['message'])

    def test_demo_elk_query_honors_high_limit_when_matches_are_available(self):
        response = self.client.post(
            '/api/log/datasources/',
            {
                'name': 'ELK Demo Large',
                'provider': 'elk',
                'config': {
                    'endpoint': 'https://demo-elastic.example.com:9200',
                    'index_pattern': 'logs-demo-*',
                    'demo_mode': True,
                },
            },
            format='json',
        )

        query_response = self.client.post(
            '/api/log/query/',
            {
                'datasource_id': response.json()['id'],
                'query': '',
                'source': 'logs-demo-*',
                'limit': 200,
            },
            format='json',
        )

        self.assertEqual(query_response.status_code, 200)
        payload = query_response.json()
        self.assertGreaterEqual(payload['total'], 200)
        self.assertEqual(len(payload['logs']), 200)

    def test_demo_elk_query_supports_structured_lucene_filters(self):
        response = self.client.post(
            '/api/log/datasources/',
            {
                'name': 'ELK Demo Filters',
                'provider': 'elk',
                'config': {
                    'endpoint': 'https://demo-elastic.example.com:9200',
                    'index_pattern': 'logs-demo-*',
                    'demo_mode': True,
                },
            },
            format='json',
        )

        query_response = self.client.post(
            '/api/log/query/',
            {
                'datasource_id': response.json()['id'],
                'query': 'level:error AND service.name:"payment-service" AND host.name:"payment-02"',
                'source': 'logs-demo-*',
            },
            format='json',
        )

        self.assertEqual(query_response.status_code, 200)
        payload = query_response.json()
        self.assertGreater(payload['total'], 0)
        self.assertTrue(all(item['attributes']['service']['name'] == 'payment-service' for item in payload['logs']))
        self.assertTrue(all(item['attributes']['host']['name'] == 'payment-02' for item in payload['logs']))
        self.assertTrue(all(item['level'] == 'error' for item in payload['logs']))

    def test_demo_elk_query_supports_or_groups_used_by_slow_request_preset(self):
        response = self.client.post(
            '/api/log/datasources/',
            {
                'name': 'ELK Demo Slow Query',
                'provider': 'elk',
                'config': {'endpoint': 'https://demo-elastic.example.com:9200', 'index_pattern': 'logs-demo-*', 'demo_mode': True},
            },
            format='json',
        )

        query_response = self.client.post(
            '/api/log/query/',
            {
                'datasource_id': response.json()['id'],
                'query': 'message:(timeout OR slow OR latency)',
                'source': 'logs-demo-*',
            },
            format='json',
        )

        self.assertEqual(query_response.status_code, 200)
        self.assertGreater(query_response.json()['total'], 0)
        self.assertTrue(any('timeout' in item['message'].lower() for item in query_response.json()['logs']))

    def test_demo_elk_query_uses_configured_index_pattern_when_source_empty(self):
        response = self.client.post(
            '/api/log/datasources/',
            {
                'name': 'ELK Demo Empty',
                'provider': 'elk',
                'config': {
                    'endpoint': 'https://demo-elastic.example.com:9200',
                    'index_pattern': 'logs-demo-*',
                    'demo_mode': True,
                },
            },
            format='json',
        )

        query_response = self.client.post(
            '/api/log/query/',
            {'datasource_id': response.json()['id'], 'query': '*', 'source': ''},
            format='json',
        )

        self.assertEqual(query_response.status_code, 200)
        self.assertGreater(query_response.json()['total'], 0)


@override_settings(LOG_PROVIDER_CONFIGS=TEST_LOG_PROVIDER_CONFIGS, OBSERVABILITY_CONFIG=TEST_OBSERVABILITY_CONFIG)
class ObservabilityViewsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_superuser('observer-admin', 'observer@example.com', 'Admin@123456')
        self.client.force_authenticate(user=self.user)

    def _enable_default_ecommerce_system(self, **overrides):
        payload = {
            'name': '交易系统核心',
            'is_enabled': True,
            'created_by': 'observer-admin',
            'updated_by': 'observer-admin',
        }
        payload.update(overrides)
        return SystemPostureSystem.objects.create(**payload)

    def _mock_ecommerce_prometheus_get(
        self,
        success_rate=96.5,
        conflict_rate=3.5,
        checkout_5xx_rate=0,
        checkout_rps=0.2,
        checkout_p95_seconds=0.42,
        deployment_metrics=True,
        up_values=None,
    ):
        def vector(*items):
            return {
                'status': 'success',
                'data': {
                    'resultType': 'vector',
                    'result': list(items),
                },
            }

        def scalar(value):
            return vector({'metric': {}, 'value': [1777862400, str(value)]})

        def series(label, value, label_name='deployment'):
            return {'metric': {label_name: label}, 'value': [1777862400, str(value)]}

        def labeled_series(labels, value):
            return {'metric': labels, 'value': [1777862400, str(value)]}

        def fake_get(url, params=None, **kwargs):
            query = (params or {}).get('query', '')
            if 'outcome="success"' in query:
                return MockHttpResponse(scalar(success_rate))
            if 'outcome="conflict"' in query:
                return MockHttpResponse(scalar(conflict_rate))
            if 'path="/api/checkout",status=~"5.."' in query:
                return MockHttpResponse(scalar(checkout_5xx_rate))
            if 'path="/api/checkout"' in query and 'sum(rate(ecommerce_http_requests_total' in query and 'status' not in query:
                return MockHttpResponse(scalar(checkout_rps))
            if 'sum by (le)' in query and 'path="/api/checkout"' in query:
                return MockHttpResponse(scalar(checkout_p95_seconds))
            if 'sum by (service)' in query and 'status!~"[45].."' in query:
                return MockHttpResponse(vector(
                    series('api-gateway', success_rate, label_name='service'),
                    series('cart', 100, label_name='service'),
                    series('order', 100, label_name='service'),
                    series('inventory', 100, label_name='service'),
                    series('catalog', 100, label_name='service'),
                ))
            if 'sum by (service,path)' in query and 'status!~"[45].."' in query:
                return MockHttpResponse(vector(
                    labeled_series({'service': 'api-gateway', 'path': '/api/checkout'}, success_rate),
                    labeled_series({'service': 'api-gateway', 'path': '/api/cart/<user_id>/items'}, 100),
                    labeled_series({'service': 'api-gateway', 'path': '/api/cart/<user_id>'}, 100),
                    labeled_series({'service': 'api-gateway', 'path': '/api/products'}, 100),
                    labeled_series({'service': 'order', 'path': '/orders'}, 100),
                    labeled_series({'service': 'inventory', 'path': '/availability'}, 100),
                ))
            if 'sum by (service,path)' in query and 'status' not in query:
                return MockHttpResponse(vector(
                    labeled_series({'service': 'api-gateway', 'path': '/api/checkout'}, checkout_rps),
                    labeled_series({'service': 'api-gateway', 'path': '/api/cart/<user_id>/items'}, 0.01),
                    labeled_series({'service': 'api-gateway', 'path': '/api/cart/<user_id>'}, 0.01),
                    labeled_series({'service': 'api-gateway', 'path': '/api/products'}, 0.01),
                    labeled_series({'service': 'order', 'path': '/orders'}, 0.02),
                    labeled_series({'service': 'inventory', 'path': '/availability'}, 0.02),
                ))
            if query.startswith('up{'):
                if up_values is None:
                    return MockHttpResponse(vector())
                return MockHttpResponse(vector(*[
                    series(service, value, label_name='service')
                    for service, value in up_values.items()
                ]))
            if 'kube_deployment_status_replicas_available' in query or 'kube_deployment_spec_replicas' in query:
                if not deployment_metrics:
                    return MockHttpResponse(vector())
                return MockHttpResponse(vector(
                    series('api-gateway', 1),
                    series('cart', 1),
                    series('order', 1),
                    series('inventory', 1),
                    series('catalog', 1),
                    series('postgres', 1),
                    series('redis', 1),
                    series('kafka', 1),
                ))
            return MockHttpResponse(vector())

        return fake_get

    def test_datasource_link_resolves_trace_to_loki_query(self):
        log_source = LogDataSource.objects.create(
            name='电商-k3s-loki',
            provider='loki',
            config={'endpoint': 'http://loki.example:3100'},
        )
        trace_source = TracingDataSource.objects.create(
            name='电商-k3s-tempo',
            provider='tempo',
            config={'query_url': 'http://tempo.example:3200'},
        )
        ObservabilityDataSourceLink.objects.create(
            name='电商 k3s Loki ↔ Tempo',
            log_datasource=log_source,
            tracing_datasource=trace_source,
            is_default=True,
            trace_id_fields=['trace_id', 'traceId'],
            log_query_template='${__tags} | json | trace_id="${__trace.traceId}"',
            log_label_mappings=[{'trace_tag': 'service.name', 'log_label': 'container'}],
        )

        response = self.client.post(
            '/api/observability/datasource-links/resolve_trace_to_logs/',
            {
                'trace_id': '0123456789abcdef0123456789abcdef',
                'tracing_datasource_id': trace_source.id,
                'tags': {'service.name': 'checkout'},
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['log_datasource']['id'], log_source.id)
        self.assertEqual(payload['query'], '{container="checkout"} | json | trace_id="0123456789abcdef0123456789abcdef"')

    def test_datasource_link_resolves_trace_to_loki_query_with_zero_padded_trace_id(self):
        log_source = LogDataSource.objects.create(
            name='电商-k3s-loki',
            provider='loki',
            config={'endpoint': 'http://loki.example:3100'},
        )
        trace_source = TracingDataSource.objects.create(
            name='电商-k3s-tempo',
            provider='tempo',
            config={'query_url': 'http://tempo.example:3200'},
        )
        ObservabilityDataSourceLink.objects.create(
            name='电商 k3s Loki ↔ Tempo',
            log_datasource=log_source,
            tracing_datasource=trace_source,
            is_default=True,
            trace_id_fields=['trace_id', 'traceId'],
            log_query_template='${__tags} | json | trace_id="${__trace.traceId}"',
            log_label_mappings=[{'trace_tag': 'service.name', 'log_label': 'container'}],
        )

        response = self.client.post(
            '/api/observability/datasource-links/resolve_trace_to_logs/',
            {
                'trace_id': '8e3554cc72d7f903d71408b205ab5a2',
                'tracing_datasource_id': trace_source.id,
                'tags': {'service.name': 'api-gateway'},
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload['query'],
            '{container="api-gateway"} | json | trace_id="08e3554cc72d7f903d71408b205ab5a2"',
        )

    def test_datasource_link_resolves_trace_to_loki_query_with_multi_zero_padding(self):
        log_source = LogDataSource.objects.create(
            name='电商-k3s-loki',
            provider='loki',
            config={'endpoint': 'http://loki.example:3100'},
        )
        trace_source = TracingDataSource.objects.create(
            name='电商-k3s-tempo',
            provider='tempo',
            config={'query_url': 'http://tempo.example:3200'},
        )
        ObservabilityDataSourceLink.objects.create(
            name='电商 k3s Loki ↔ Tempo',
            log_datasource=log_source,
            tracing_datasource=trace_source,
            is_default=True,
            trace_id_fields=['trace_id', 'traceId'],
            log_query_template='${__tags} | json | trace_id="${__trace.traceId}"',
            log_label_mappings=[{'trace_tag': 'service.name', 'log_label': 'container'}],
        )

        response = self.client.post(
            '/api/observability/datasource-links/resolve_trace_to_logs/',
            {
                'trace_id': '1234567890abcdef1234567890abcd',
                'tracing_datasource_id': trace_source.id,
                'tags': {'service.name': 'order-service'},
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload['query'],
            '{container="order-service"} | json | trace_id="001234567890abcdef1234567890abcd"',
        )

    def test_datasource_link_resolves_trace_to_grafana_dashboard(self):
        log_source = LogDataSource.objects.create(
            name='电商-k3s-loki',
            provider='loki',
            config={'endpoint': 'http://loki.example:3100'},
        )
        trace_source = TracingDataSource.objects.create(
            name='电商-k3s-tempo',
            provider='tempo',
            config={'query_url': 'http://tempo.example:3200'},
        )
        ObservabilityDataSourceLink.objects.create(
            name='电商 k3s Loki ↔ Tempo',
            log_datasource=log_source,
            tracing_datasource=trace_source,
            is_default=True,
            trace_to_grafana_enabled=True,
            grafana_dashboard_key='apm-overview',
            grafana_variable_mappings=[{'trace_tag': 'service.name', 'variable': 'service'}],
        )

        response = self.client.post(
            '/api/observability/datasource-links/resolve_trace_to_grafana/',
            {
                'trace_id': '0123456789abcdef0123456789abcdef',
                'tracing_datasource_id': trace_source.id,
                'tags': {'service.name': 'checkout'},
                'from': 1710000000000,
                'to': 1710000300000,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['dashboard']['key'], 'apm-overview')
        self.assertEqual(payload['query']['dashboard'], 'apm-overview')
        self.assertEqual(payload['query']['traceId'], '0123456789abcdef0123456789abcdef')
        self.assertEqual(payload['query']['var-service'], 'checkout')
        self.assertEqual(payload['query']['from'], 1710000000000)

    def test_datasource_link_resolves_log_to_grafana_dashboard(self):
        log_source = LogDataSource.objects.create(
            name='电商-k3s-loki',
            provider='loki',
            config={'endpoint': 'http://loki.example:3100'},
        )
        trace_source = TracingDataSource.objects.create(
            name='电商-k3s-tempo',
            provider='tempo',
            config={'query_url': 'http://tempo.example:3200'},
        )
        ObservabilityDataSourceLink.objects.create(
            name='电商 k3s Loki ↔ Tempo',
            log_datasource=log_source,
            tracing_datasource=trace_source,
            is_default=True,
            log_to_grafana_enabled=True,
            grafana_dashboard_key='apm-overview',
            log_label_mappings=[{'trace_tag': 'service.name', 'log_label': 'container'}],
            grafana_variable_mappings=[{'trace_tag': 'service.name', 'variable': 'service'}],
        )

        response = self.client.post(
            '/api/observability/datasource-links/resolve_log_to_grafana/',
            {
                'trace_id': '0123456789abcdef0123456789abcdef',
                'log_datasource_id': log_source.id,
                'attributes': {'container': 'checkout'},
                'message': 'checkout failed',
                'from': 1710000000000,
                'to': 1710000300000,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['dashboard']['key'], 'apm-overview')
        self.assertEqual(payload['query']['dashboard'], 'apm-overview')
        self.assertEqual(payload['query']['source'], 'log')
        self.assertEqual(payload['query']['traceId'], '0123456789abcdef0123456789abcdef')
        self.assertEqual(payload['query']['var-service'], 'checkout')

    def test_datasource_link_resolves_trace_to_workload_dashboard(self):
        log_source = LogDataSource.objects.create(
            name='电商-k3s-loki',
            provider='loki',
            config={'endpoint': 'http://loki.example:3100'},
        )
        trace_source = TracingDataSource.objects.create(
            name='电商-k3s-tempo',
            provider='tempo',
            config={'query_url': 'http://tempo.example:3200'},
        )
        ObservabilityDataSourceLink.objects.create(
            name='电商 k3s Loki ↔ Tempo',
            log_datasource=log_source,
            tracing_datasource=trace_source,
            is_default=True,
            trace_to_grafana_enabled=True,
            grafana_dashboard_key='apm-overview',
            grafana_variable_mappings=[
                {'trace_tag': 'service.name', 'variable': 'workload'},
                {'trace_tag': 'service.namespace', 'variable': 'namespace'},
                {'trace_tag': 'workload.type', 'variable': 'workload_type'},
            ],
        )

        response = self.client.post(
            '/api/observability/datasource-links/resolve_trace_to_grafana/',
            {
                'trace_id': '0123456789abcdef0123456789abcdef',
                'tracing_datasource_id': trace_source.id,
                'dashboard_key': 'Kubernetes / Compute Resources / Workload',
                'tags': {'service.name': 'checkout', 'service.namespace': 'default'},
                'from': 1710000000000,
                'to': 1710000300000,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['dashboard']['key'], 'kubernetes-compute-resources-workload')
        self.assertEqual(payload['query']['dashboard'], 'kubernetes-compute-resources-workload')
        self.assertEqual(payload['query']['traceId'], '0123456789abcdef0123456789abcdef')
        self.assertEqual(payload['query']['var-workload'], 'checkout')
        self.assertEqual(payload['query']['var-namespace'], 'default')
        self.assertEqual(payload['query']['from'], 1710000000000)

    def test_datasource_link_resolves_log_to_workload_dashboard(self):
        log_source = LogDataSource.objects.create(
            name='电商-k3s-loki',
            provider='loki',
            config={'endpoint': 'http://loki.example:3100'},
        )
        trace_source = TracingDataSource.objects.create(
            name='电商-k3s-tempo',
            provider='tempo',
            config={'query_url': 'http://tempo.example:3200'},
        )
        ObservabilityDataSourceLink.objects.create(
            name='电商 k3s Loki ↔ Tempo',
            log_datasource=log_source,
            tracing_datasource=trace_source,
            is_default=True,
            log_to_grafana_enabled=True,
            grafana_dashboard_key='apm-overview',
            log_label_mappings=[
                {'trace_tag': 'service.name', 'log_label': 'app'},
                {'trace_tag': 'service.namespace', 'log_label': 'namespace'},
            ],
            grafana_variable_mappings=[
                {'trace_tag': 'service.name', 'variable': 'workload'},
                {'trace_tag': 'service.namespace', 'variable': 'namespace'},
            ],
        )

        response = self.client.post(
            '/api/observability/datasource-links/resolve_log_to_grafana/',
            {
                'trace_id': '0123456789abcdef0123456789abcdef',
                'log_datasource_id': log_source.id,
                'attributes': {'app': 'checkout', 'namespace': 'default'},
                'message': 'checkout failed',
                'dashboard_key': 'Kubernetes / Compute Resources / Workload',
                'from': 1710000000000,
                'to': 1710000300000,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['dashboard']['key'], 'kubernetes-compute-resources-workload')
        self.assertEqual(payload['query']['dashboard'], 'kubernetes-compute-resources-workload')
        self.assertEqual(payload['query']['source'], 'log')
        self.assertEqual(payload['query']['traceId'], '0123456789abcdef0123456789abcdef')
        self.assertEqual(payload['query']['var-workload'], 'checkout')
        self.assertEqual(payload['query']['var-namespace'], 'default')
        self.assertEqual(payload['query']['var-workload_type'], 'deployment')

    def test_datasource_link_resolves_log_to_workload_dashboard_without_trace_id(self):
        log_source = LogDataSource.objects.create(
            name='电商-k3s-loki',
            provider='loki',
            config={'endpoint': 'http://loki.example:3100'},
        )
        trace_source = TracingDataSource.objects.create(
            name='电商-k3s-tempo',
            provider='tempo',
            config={'query_url': 'http://tempo.example:3200'},
        )
        ObservabilityDataSourceLink.objects.create(
            name='电商 k3s Loki ↔ Tempo',
            log_datasource=log_source,
            tracing_datasource=trace_source,
            is_default=True,
            log_to_grafana_enabled=True,
            grafana_dashboard_key='kubernetes-compute-resources-workload',
            log_label_mappings=[
                {'trace_tag': 'service.name', 'log_label': 'app'},
                {'trace_tag': 'service.namespace', 'log_label': 'namespace'},
            ],
            grafana_variable_mappings=[
                {'trace_tag': 'service.name', 'variable': 'workload'},
                {'trace_tag': 'service.namespace', 'variable': 'namespace'},
                {'trace_tag': 'workload.type', 'variable': 'workload_type'},
            ],
        )

        response = self.client.post(
            '/api/observability/datasource-links/resolve_log_to_grafana/',
            {
                'log_datasource_id': log_source.id,
                'attributes': {'app': 'checkout', 'namespace': 'default', 'workload_type': 'deployment', 'trace_id': '0123456789abcdef0123456789abcdef'},
                'message': 'checkout failed trace_id=0123456789abcdef0123456789abcdef',
                'dashboard_key': 'Kubernetes / Compute Resources / Workload',
                'ignore_trace_id': True,
                'from': 1710000000000,
                'to': 1710000300000,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['dashboard']['key'], 'kubernetes-compute-resources-workload')
        self.assertNotIn('traceId', payload['query'])
        self.assertEqual(payload['query']['var-workload'], 'checkout')
        self.assertEqual(payload['query']['var-namespace'], 'default')
        self.assertEqual(payload['query']['var-workload_type'], 'deployment')

    def test_datasource_link_resolves_workload_dashboard_to_loki_query(self):
        log_source = LogDataSource.objects.create(
            name='电商-k3s-loki',
            provider='loki',
            config={'endpoint': 'http://loki.example:3100'},
        )
        trace_source = TracingDataSource.objects.create(
            name='电商-k3s-tempo',
            provider='tempo',
            config={'query_url': 'http://tempo.example:3200'},
        )
        ObservabilityDataSourceLink.objects.create(
            name='电商 k3s Loki ↔ Tempo',
            log_datasource=log_source,
            tracing_datasource=trace_source,
            is_default=True,
            grafana_dashboard_key='kubernetes-compute-resources-workload',
            log_label_mappings=[
                {'trace_tag': 'service.name', 'log_label': 'container'},
                {'trace_tag': 'service.namespace', 'log_label': 'namespace'},
            ],
            grafana_variable_mappings=[
                {'trace_tag': 'service.name', 'variable': 'workload'},
                {'trace_tag': 'service.namespace', 'variable': 'namespace'},
            ],
        )

        response = self.client.post(
            '/api/observability/datasource-links/resolve_grafana_to_logs/',
            {
                'dashboard_key': 'kubernetes-compute-resources-workload',
                'var-workload': 'checkout',
                'var-namespace': 'default',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['log_datasource']['id'], log_source.id)
        self.assertEqual(payload['tags']['service.name'], 'checkout')
        self.assertEqual(payload['tags']['service.namespace'], 'default')
        self.assertEqual(payload['query'], '{container="checkout",namespace="default"}')

    def test_datasource_link_resolves_workload_dashboard_to_trace_target(self):
        log_source = LogDataSource.objects.create(
            name='电商-k3s-loki',
            provider='loki',
            config={'endpoint': 'http://loki.example:3100'},
        )
        trace_source = TracingDataSource.objects.create(
            name='电商-k3s-tempo',
            provider='tempo',
            config={'query_url': 'http://tempo.example:3200'},
        )
        ObservabilityDataSourceLink.objects.create(
            name='电商 k3s Loki ↔ Tempo',
            log_datasource=log_source,
            tracing_datasource=trace_source,
            is_default=True,
            grafana_dashboard_key='kubernetes-compute-resources-workload',
            grafana_variable_mappings=[
                {'trace_tag': 'service.name', 'variable': 'workload'},
                {'trace_tag': 'service.namespace', 'variable': 'namespace'},
            ],
        )

        response = self.client.post(
            '/api/observability/datasource-links/resolve_grafana_to_trace/',
            {
                'dashboard_key': 'Kubernetes / Compute Resources / Workload',
                'query': {
                    'var-workload': 'checkout',
                    'var-namespace': 'default',
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['tracing_datasource']['id'], trace_source.id)
        self.assertEqual(payload['service'], 'checkout')
        self.assertEqual(payload['tags']['service.namespace'], 'default')

    def test_datasource_link_resolve_grafana_to_trace_requires_dashboard_match(self):
        log_source = LogDataSource.objects.create(
            name='电商-k3s-loki',
            provider='loki',
            config={'endpoint': 'http://loki.example:3100'},
        )
        trace_source = TracingDataSource.objects.create(
            name='电商-k3s-tempo',
            provider='tempo',
            config={'query_url': 'http://tempo.example:3200'},
        )
        ObservabilityDataSourceLink.objects.create(
            name='电商 k3s Loki ↔ Tempo',
            log_datasource=log_source,
            tracing_datasource=trace_source,
            is_default=True,
            grafana_dashboard_key='kubernetes-compute-resources-workload',
            grafana_variable_mappings=[
                {'trace_tag': 'service.name', 'variable': 'workload'},
                {'trace_tag': 'service.namespace', 'variable': 'namespace'},
            ],
        )

        response = self.client.post(
            '/api/observability/datasource-links/resolve_grafana_to_trace/',
            {
                'dashboard_key': 'Node Exporter / Nodes',
                'query': {
                    'var-job': 'node-exporter',
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['detail'], '未找到可用的 Grafana 看板到链路关联')

    def test_datasource_link_resolve_grafana_to_logs_requires_dashboard_match(self):
        log_source = LogDataSource.objects.create(
            name='电商-k3s-loki',
            provider='loki',
            config={'endpoint': 'http://loki.example:3100'},
        )
        trace_source = TracingDataSource.objects.create(
            name='电商-k3s-tempo',
            provider='tempo',
            config={'query_url': 'http://tempo.example:3200'},
        )
        ObservabilityDataSourceLink.objects.create(
            name='电商 k3s Loki ↔ Tempo',
            log_datasource=log_source,
            tracing_datasource=trace_source,
            is_default=True,
            grafana_dashboard_key='kubernetes-compute-resources-workload',
            log_label_mappings=[
                {'trace_tag': 'service.name', 'log_label': 'container'},
            ],
            grafana_variable_mappings=[
                {'trace_tag': 'service.name', 'variable': 'workload'},
            ],
        )

        response = self.client.post(
            '/api/observability/datasource-links/resolve_grafana_to_logs/',
            {
                'dashboard_key': 'Node Exporter / Nodes',
                'query': {
                    'var-job': 'node-exporter',
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['detail'], '未找到可用的 Grafana 看板到日志关联')

    def test_datasource_link_resolves_log_to_trace_target(self):
        log_source = LogDataSource.objects.create(
            name='电商-k3s-loki',
            provider='loki',
            config={'endpoint': 'http://loki.example:3100'},
        )
        trace_source = TracingDataSource.objects.create(
            name='电商-k3s-tempo',
            provider='tempo',
            config={'query_url': 'http://tempo.example:3200'},
        )
        ObservabilityDataSourceLink.objects.create(
            name='电商 k3s Loki ↔ Tempo',
            log_datasource=log_source,
            tracing_datasource=trace_source,
            trace_id_fields=['trace_id'],
        )

        response = self.client.post(
            '/api/observability/datasource-links/resolve_log_to_trace/',
            {
                'log_datasource_id': log_source.id,
                'attributes': {'trace_id': 'abcdef0123456789abcdef0123456789'},
                'message': 'checkout failed',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['trace_id'], 'abcdef0123456789abcdef0123456789')
        self.assertEqual(payload['tracing_datasource']['id'], trace_source.id)

    def test_observability_overview_falls_back_to_demo_without_skywalking_oap(self):
        with override_settings(
            OBSERVABILITY_CONFIG={
                'skywalking': {
                    'enabled': True,
                    'ui_url': '',
                    'oap_url': '',
                    'graphql_path': '/graphql',
                    'default_layer': '',
                    'demo_mode': True,
                },
                'grafana': {
                    'enabled': True,
                    'url': '',
                    'default_path': '',
                    'demo_mode': True,
                },
            }
        ):
            response = self.client.get('/api/observability/overview/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['modules']['tracing']['source'], 'demo')
        self.assertEqual(payload['modules']['tracing']['provider'], 'skywalking')
        self.assertEqual(payload['modules']['grafana']['source'], 'demo')
        self.assertEqual(payload['summary']['dashboard_count'], 5)
        self.assertGreaterEqual(payload['summary']['service_count'], 1)
        self.assertTrue(any(item['provider'] == 'demo' for item in payload['providers']))

    def test_observability_system_posture_returns_business_cards_and_topology(self):
        response = self.client.get('/api/observability/system-posture/?system=observability-stack')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['selected_system_id'], 'observability-stack')
        self.assertGreaterEqual(payload['summary']['system_count'], 3)
        self.assertGreaterEqual(len(payload['systems']), 3)
        self.assertTrue(payload['selected_system']['children'])
        self.assertTrue(payload['selected_system']['dependencies'])
        self.assertGreaterEqual(payload['topology']['node_count'], 1)
        self.assertTrue(any(item['id'] == 'system-posture' for item in payload['data_sources']))
        selected_rule_config = payload['selected_system']['form']['rule_config']
        self.assertEqual(selected_rule_config['drilldown']['levels'][0]['kind'], 'system')
        self.assertIn('grafana', [item['id'] for item in selected_rule_config['drilldown']['services']])
        self.assertTrue(any(link['type'] == 'upstream' for link in selected_rule_config['topology']['links']))
        edge = next(item for item in payload['systems'] if item['id'] == 'platform-edge')
        self.assertEqual(edge['status'], 'critical')
        self.assertEqual(edge['core_metric']['status'], 'critical')
        self.assertGreater(edge['health_score'], 50)
        self.assertTrue(all(item['status'] in {'healthy', 'unknown'} for item in edge['dependencies']))
        edge_rule_config = edge['form']['rule_config']
        self.assertIn('nginx-ingress', [item['id'] for item in edge_rule_config['drilldown']['services']])
        self.assertTrue(any(link['source'] == 'waf-rule' and link['target'] == 'platform-edge' for link in edge_rule_config['topology']['links']))
        for action in payload['quick_actions']:
            if action['key'] in {'trace', 'log'}:
                self.assertNotIn('traceId', action.get('query') or {})
                self.assertNotIn('trace_id', action.get('query') or {})

    def test_observability_system_posture_history_persists_daily_sla_snapshot(self):
        response = self.client.get('/api/observability/system-posture/history/?days=7')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['days']), 7)
        self.assertEqual(payload['summary']['system_count'], 0)
        self.assertEqual(SystemPostureSLAHistory.objects.count(), 0)
        self.assertEqual(payload['context']['captured'], 0)
        self.assertEqual(payload['context']['source'], 'sla_history')

        refresh_response = self.client.get('/api/observability/system-posture/history/?days=7&refresh=1')
        self.assertEqual(refresh_response.status_code, 200)
        payload = refresh_response.json()
        self.assertGreaterEqual(payload['summary']['system_count'], 3)
        self.assertGreaterEqual(len(payload['systems']), 3)
        self.assertGreaterEqual(SystemPostureSLAHistory.objects.count(), 3)
        first_system = payload['systems'][0]
        self.assertEqual(len(first_system['records']), 1)
        self.assertIn('sla', first_system['records'][0])
        self.assertEqual(payload['context']['source'], 'sla_history')

        backfill_response = self.client.get('/api/observability/system-posture/history/?days=7&backfill=1')
        self.assertEqual(backfill_response.status_code, 200)
        self.assertGreaterEqual(SystemPostureSLAHistory.objects.count(), 8)

    def test_observability_system_posture_history_skips_locked_writes(self):
        self.client.get('/api/observability/system-posture/history/?days=7&refresh=1')
        with patch(
            'ops.observability_views.SystemPostureSLAHistory.objects.update_or_create',
            side_effect=OperationalError('database is locked'),
        ):
            response = self.client.get('/api/observability/system-posture/history/?days=7&refresh=1')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['context']['source'], 'sla_history')
        self.assertGreaterEqual(payload['summary']['system_count'], 3)

    @override_settings(OBSERVABILITY_CONFIG={
        **TEST_OBSERVABILITY_CONFIG,
        'prometheus': {
            'enabled': True,
            'query_url': 'http://prometheus.example.com',
            'timeout': 3,
        },
    })
    @patch('ops.observability_views.http_requests.get')
    def test_observability_system_posture_uses_live_ecommerce_prometheus_metrics(self, mock_get):
        self._enable_default_ecommerce_system()
        mock_get.side_effect = self._mock_ecommerce_prometheus_get()

        response = self.client.get('/api/observability/system-posture/?system=交易系统核心')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        selected = payload['selected_system']
        self.assertEqual(selected['name'], '交易系统核心')
        self.assertTrue(selected['builtin_backed'])
        self.assertEqual(selected['core_metric']['label'], '系统成功率')
        self.assertGreater(selected['core_metric']['value'], 96.5)
        self.assertLess(selected['core_metric']['value'], 100)
        self.assertEqual(selected['core_metric']['status'], 'healthy')
        self.assertTrue(selected['live']['enabled'])
        self.assertEqual(selected['live']['core_metric_key'], 'checkout_success_rate')
        self.assertEqual(selected['live']['core_metric_key'], 'checkout_success_rate')
        self.assertNotIn('window', selected['rule_config'])
        self.assertNotIn('window', selected['form']['rule_config'])
        self.assertEqual(selected['live']['window'], '30m')
        self.assertEqual(selected['rule_config']['health_score']['weights']['success_rate'], 0.62)
        conflict_rule = next(item for item in selected['rule_config']['root_cause_rules'] if item['id'] == 'inventory-conflict')
        self.assertTrue(conflict_rule['count_as_fault'])
        self.assertIn('order', [item['service_id'] for item in conflict_rule['affected_services']])
        self.assertIn('rule_config', selected['form'])
        self.assertEqual(selected['children'][0]['id'], 'api-gateway')
        conflict_metric = next(item for item in selected['metrics'] if item['label'] == 'Checkout 409占比')
        self.assertEqual(conflict_metric['value'], 3.5)
        self.assertEqual(conflict_metric['status'], 'critical')
        gateway = next(item for item in selected['children'] if item['id'] == 'api-gateway')
        gateway_success = next(item for item in gateway['metrics'] if item['label'] == '成功率')
        self.assertLess(gateway_success['value'], 100)
        self.assertGreater(gateway_success['value'], 96.5)
        gateway_checkout = next(item for item in gateway['children'] if item['id'] == 'gateway-checkout')
        gateway_checkout_success = next(item for item in gateway_checkout['metrics'] if item['label'] == '成功率')
        self.assertEqual(gateway_checkout_success['value'], 96.5)
        self.assertEqual(gateway_checkout_success['status'], 'critical')
        self.assertEqual(gateway_checkout['status'], 'critical')
        order = next(item for item in selected['children'] if item['id'] == 'order')
        self.assertEqual(order['status'], 'critical')
        order_api = next(item for item in order['children'] if item['id'] == 'order-create')
        self.assertEqual(order_api['status'], 'critical')
        inventory = next(item for item in selected['children'] if item['id'] == 'inventory')
        self.assertEqual(inventory['status'], 'critical')
        inventory_api = next(item for item in inventory['children'] if item['id'] == 'inventory-availability')
        self.assertIn('库存', inventory_api['hint'])
        self.assertGreater(selected['health_score'], 80)
        self.assertLessEqual(selected['health_score'], 100)

    @override_settings(OBSERVABILITY_CONFIG={
        **TEST_OBSERVABILITY_CONFIG,
        'prometheus': {
            'enabled': True,
            'query_url': 'http://prometheus.example.com',
            'timeout': 3,
        },
    })
    @patch('ops.observability_views.http_requests.get')
    def test_ecommerce_conflict_can_be_configured_as_fault(self, mock_get):
        system = self._enable_default_ecommerce_system()
        mock_get.side_effect = self._mock_ecommerce_prometheus_get()
        system.rule_config = {
            'root_cause_rules': [
                {
                    'id': 'inventory-conflict',
                    'metric': 'checkout_conflict_rate',
                    'min_rate': 1,
                    'critical_rate': 3,
                    'min_rps': 0.001,
                    'count_as_fault': True,
                    'target_service_id': 'inventory',
                    'target_interface_id': 'inventory-availability',
                    'metric_label': '库存冲突率',
                    'critical_message': '409 冲突按故障计算',
                },
            ],
        }
        system.save(update_fields=['rule_config'])

        response = self.client.get('/api/observability/system-posture/?system=交易系统核心')

        self.assertEqual(response.status_code, 200)
        selected = response.json()['selected_system']
        conflict_metric = next(item for item in selected['metrics'] if item['label'] == 'Checkout 409占比')
        self.assertEqual(conflict_metric['status'], 'critical')
        inventory = next(item for item in selected['children'] if item['id'] == 'inventory')
        self.assertEqual(inventory['status'], 'critical')
        inventory_api = next(item for item in inventory['children'] if item['id'] == 'inventory-availability')
        self.assertEqual(inventory_api['status'], 'critical')

    @override_settings(OBSERVABILITY_CONFIG={
        **TEST_OBSERVABILITY_CONFIG,
        'prometheus': {
            'enabled': True,
            'query_url': 'http://prometheus.example.com',
            'timeout': 3,
        },
    })
    @patch('ops.observability_views.http_requests.get')
    def test_observability_system_posture_marks_ecommerce_down_when_runtime_targets_down(self, mock_get):
        self._enable_default_ecommerce_system()
        mock_get.side_effect = self._mock_ecommerce_prometheus_get(
            success_rate=99.9,
            conflict_rate=0,
            checkout_5xx_rate=0,
            deployment_metrics=False,
            up_values={
                'api-gateway': 0,
                'cart': 0,
                'order': 0,
                'inventory': 0,
                'catalog': 0,
            },
        )

        response = self.client.get('/api/observability/system-posture/?system=交易系统核心')

        self.assertEqual(response.status_code, 200)
        selected = response.json()['selected_system']
        self.assertEqual(selected['status'], 'critical')
        self.assertEqual(selected['health_score'], 0)
        self.assertEqual(selected['core_metric']['label'], '环境可用率')
        self.assertEqual(selected['core_metric']['value'], 0)
        self.assertEqual(selected['core_metric']['target'], 99)
        self.assertEqual(selected['live']['runtime_availability'], 0)
        self.assertTrue(any(item['label'] == '环境可用率' and item['value'] == 0 and item['target'] == 99 for item in selected['metrics']))
        self.assertTrue(all(item['status'] == 'critical' for item in selected['children']))

    @override_settings(OBSERVABILITY_CONFIG={
        **TEST_OBSERVABILITY_CONFIG,
        'prometheus': {
            'enabled': True,
            'query_url': 'http://prometheus.example.com',
            'timeout': 3,
        },
    })
    @patch('ops.observability_views.http_requests.get')
    def test_observability_system_posture_does_not_fallback_to_demo_rate_when_live_metrics_missing(self, mock_get):
        self._enable_default_ecommerce_system()
        mock_get.side_effect = self._mock_ecommerce_prometheus_get(
            success_rate=None,
            conflict_rate=None,
            checkout_5xx_rate=None,
            checkout_rps=None,
            checkout_p95_seconds=None,
            deployment_metrics=False,
        )

        response = self.client.get('/api/observability/system-posture/?system=交易系统核心')

        self.assertEqual(response.status_code, 200)
        selected = response.json()['selected_system']
        self.assertEqual(selected['status'], 'critical')
        self.assertEqual(selected['health_score'], 0)
        self.assertEqual(selected['core_metric']['label'], '环境可用率')
        self.assertEqual(selected['core_metric']['value'], 0)
        self.assertEqual(selected['core_metric']['target'], 99)
        self.assertTrue(selected['live']['unavailable'])
        self.assertNotEqual(selected['core_metric']['value'], 93.8)

    @override_settings(OBSERVABILITY_CONFIG=TEST_OBSERVABILITY_CONFIG)
    def test_observability_system_posture_does_not_use_demo_success_rate_when_live_source_not_ready(self):
        self._enable_default_ecommerce_system()
        response = self.client.get('/api/observability/system-posture/?system=交易系统核心')

        self.assertEqual(response.status_code, 200)
        selected = response.json()['selected_system']
        self.assertEqual(selected['status'], 'critical')
        self.assertEqual(selected['health_score'], 0)
        self.assertEqual(selected['core_metric']['label'], '环境可用率')
        self.assertEqual(selected['core_metric']['value'], 0)
        self.assertEqual(selected['core_metric']['target'], 99)
        self.assertTrue(selected['live']['unavailable'])
        self.assertNotEqual(selected['core_metric']['value'], 93.8)

    @override_settings(OBSERVABILITY_CONFIG=TEST_OBSERVABILITY_CONFIG)
    def test_custom_ecommerce_posture_does_not_use_saved_demo_slo_when_live_source_not_ready(self):
        SystemPostureSystem.objects.create(
            name='电商交易核心',
            environment='ecommerce-test-k3s',
            domain='业务域',
            base_status='critical',
            health_score=94,
            core_metric={'label': '下单成功率', 'value': 93.8, 'target': 90, 'unit': '%', 'direction': 'higher'},
            metrics=[{'label': '下单成功率', 'value': 93.8, 'target': 99.95, 'unit': '%', 'direction': 'higher'}],
            rule_config={
                'enabled': True,
                'namespace': 'ecommerce',
                'service_pattern': 'api-gateway|cart|order|inventory|catalog',
                'prometheus': {
                    'scalars': {
                        'checkout_success_rate': {
                            'label': '下单成功率',
                            'target': 90,
                            'unit': '%',
                            'direction': 'higher',
                            'query': '100 * sum(rate(ecommerce_checkout_outcomes_total{namespace="{namespace}",service="api-gateway",outcome="success"}[{window}])) / clamp_min(sum(rate(ecommerce_checkout_outcomes_total{namespace="{namespace}",service="api-gateway",outcome=~"success|conflict"}[{window}])), 0.000001)',
                        },
                    },
                },
                'core_metric': {'metric': 'checkout_success_rate', 'label': '下单成功率', 'target': 90, 'unit': '%', 'direction': 'higher'},
                'drilldown': {
                    'services': [{'id': 'api-gateway', 'name': 'API 网关', 'paths': []}],
                    'dependencies': [{'id': 'postgres', 'name': 'PostgreSQL'}],
                },
            },
        )

        response = self.client.get('/api/observability/system-posture/?system=电商交易核心')

        self.assertEqual(response.status_code, 200)
        selected = response.json()['selected_system']
        self.assertEqual(selected['name'], '电商交易核心')
        self.assertTrue(selected['live']['unavailable'])
        self.assertEqual(selected['core_metric']['label'], '环境可用率')
        self.assertEqual(selected['core_metric']['value'], 0)
        self.assertEqual(selected['core_metric']['target'], 90)
        self.assertNotEqual(selected['core_metric']['value'], 93.8)

    @override_settings(OBSERVABILITY_CONFIG=TEST_OBSERVABILITY_CONFIG)
    def test_system_posture_history_refreshes_today_custom_ecommerce_slo(self):
        today = timezone.localdate()
        system = SystemPostureSystem.objects.create(
            name='电商交易核心',
            environment='ecommerce-test-k3s',
            domain='业务域',
            base_status='critical',
            health_score=94,
            core_metric={'label': '下单成功率', 'value': 93.8, 'target': 90, 'unit': '%', 'direction': 'higher'},
            metrics=[{'label': '下单成功率', 'value': 93.8, 'target': 99.95, 'unit': '%', 'direction': 'higher'}],
            rule_config={
                'enabled': True,
                'namespace': 'ecommerce',
                'prometheus': {
                    'scalars': {
                        'checkout_success_rate': {
                            'label': '下单成功率',
                            'target': 90,
                            'unit': '%',
                            'direction': 'higher',
                            'query': '100 * sum(rate(ecommerce_checkout_outcomes_total{namespace="{namespace}",service="api-gateway",outcome="success"}[{window}])) / clamp_min(sum(rate(ecommerce_checkout_outcomes_total{namespace="{namespace}",service="api-gateway",outcome=~"success|conflict"}[{window}])), 0.000001)',
                        },
                    },
                },
                'core_metric': {'metric': 'checkout_success_rate', 'label': '下单成功率', 'target': 90, 'unit': '%', 'direction': 'higher'},
                'drilldown': {
                    'services': [{'id': 'api-gateway', 'name': 'API 网关', 'paths': []}],
                    'dependencies': [{'id': 'postgres', 'name': 'PostgreSQL'}],
                },
            },
        )
        system_key = f'custom-{system.id}'
        SystemPostureSLAHistory.objects.create(
            day=today,
            system_key=system_key,
            system_name='电商交易核心',
            environment='ecommerce-test-k3s',
            domain='业务域',
            status='healthy',
            sla_value=Decimal('93.800'),
            sla_target=Decimal('90.000'),
            health_score=94,
            metric_label='下单成功率',
            metric_unit='%',
            snapshot={},
        )

        response = self.client.get('/api/observability/system-posture/history/?days=7&refresh=1')

        self.assertEqual(response.status_code, 200)
        record = SystemPostureSLAHistory.objects.get(day=today, system_key=system_key)
        self.assertEqual(record.sla_value, Decimal('0.000'))
        self.assertEqual(record.status, 'critical')
        payload_system = next(item for item in response.json()['systems'] if item['id'] == system_key)
        payload_record = next(item for item in payload_system['records'] if item['day'] == today.isoformat())
        self.assertEqual(payload_record['sla'], 0.0)
        self.assertNotEqual(payload_record['sla'], 93.8)

    @override_settings(OBSERVABILITY_CONFIG={
        **TEST_OBSERVABILITY_CONFIG,
        'prometheus': {
            'enabled': True,
            'query_url': 'http://prometheus.example.com',
            'timeout': 3,
        },
    })
    @patch('ops.observability_views.http_requests.get')
    def test_custom_ecommerce_posture_uses_live_history_and_keeps_drilldown(self, mock_get):
        today = timezone.localdate()
        system = SystemPostureSystem.objects.create(
            name='电商交易核心',
            environment='ecommerce-test-k3s',
            domain='业务域',
            base_status='healthy',
            health_score=94,
            core_metric={'label': '下单成功率', 'value': 93.8, 'target': 90, 'unit': '%', 'direction': 'higher'},
            metrics=[{'label': '下单成功率', 'value': 93.8, 'target': 90, 'unit': '%', 'direction': 'higher'}],
            rule_config={
                'enabled': True,
                'namespace': 'ecommerce',
                'prometheus': {
                    'scalars': {
                        'checkout_success_rate': {
                            'label': '下单成功率',
                            'target': 90,
                            'unit': '%',
                            'direction': 'higher',
                            'query': '100 * sum(rate(ecommerce_checkout_outcomes_total{namespace="{namespace}",service="api-gateway",outcome="success"}[{window}])) / clamp_min(sum(rate(ecommerce_checkout_outcomes_total{namespace="{namespace}",service="api-gateway",outcome=~"success|conflict"}[{window}])), 0.000001)',
                        },
                    },
                },
                'core_metric': {'metric': 'checkout_success_rate', 'label': '下单成功率', 'target': 90, 'unit': '%', 'direction': 'higher'},
                'drilldown': {
                    'services': copy.deepcopy(ECOMMERCE_SERVICE_SPECS),
                    'dependencies': copy.deepcopy(ECOMMERCE_DEPENDENCIES),
                },
            },
        )
        system_key = f'custom-{system.id}'
        SystemPostureSLAHistory.objects.create(
            day=today,
            system_key=system_key,
            system_name='电商交易核心',
            environment='ecommerce-test-k3s',
            domain='业务域',
            status='healthy',
            sla_value=Decimal('93.800'),
            sla_target=Decimal('90.000'),
            health_score=94,
            metric_label='下单成功率',
            metric_unit='%',
            snapshot={},
        )
        mock_get.side_effect = self._mock_ecommerce_prometheus_get()

        posture_response = self.client.get(f'/api/observability/system-posture/?system={system_key}')
        history_response = self.client.get('/api/observability/system-posture/history/?days=7&refresh=1')

        self.assertEqual(posture_response.status_code, 200)
        selected = posture_response.json()['selected_system']
        self.assertEqual(selected['core_metric']['label'], '系统成功率')
        self.assertGreater(selected['core_metric']['value'], 96.5)
        self.assertLess(selected['core_metric']['value'], 100)
        self.assertTrue(selected['children'])
        self.assertTrue(selected['children'][0]['children'])
        self.assertTrue(selected['dependencies'])

        self.assertEqual(history_response.status_code, 200)
        payload_system = next(item for item in history_response.json()['systems'] if item['id'] == system_key)
        payload_record = next(item for item in payload_system['records'] if item['day'] == today.isoformat())
        self.assertGreater(payload_record['sla'], 96.5)
        self.assertLess(payload_record['sla'], 100)
        self.assertNotEqual(payload_record['sla'], 93.8)

    @override_settings(OBSERVABILITY_CONFIG={
        **TEST_OBSERVABILITY_CONFIG,
        'prometheus': {
            'enabled': True,
            'query_url': 'http://prometheus.example.com',
            'timeout': 3,
        },
    })
    @patch('ops.observability_views.http_requests.get')
    def test_observability_system_posture_applies_selected_time_range_to_prometheus(self, mock_get):
        self._enable_default_ecommerce_system()
        mock_get.side_effect = self._mock_ecommerce_prometheus_get()

        response = self.client.get(
            '/api/observability/system-posture/?system=交易系统核心'
            '&start=2026-05-07T10:00:00Z&end=2026-05-07T10:30:00Z'
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        selected = payload['selected_system']
        self.assertEqual(selected['rule_config']['window'], '30m')
        self.assertNotIn('window', selected['form']['rule_config'])
        self.assertEqual(selected['live']['window'], '30m')
        self.assertEqual(payload['context']['time_range']['window'], '30m')
        query_calls = [call for call in mock_get.call_args_list if '/api/v1/query' in call.args[0]]
        self.assertTrue(query_calls)
        self.assertTrue(any('[30m]' in (call.kwargs.get('params') or {}).get('query', '') for call in query_calls))
        self.assertTrue(all((call.kwargs.get('params') or {}).get('time') for call in query_calls))

    @override_settings(OBSERVABILITY_CONFIG={
        **TEST_OBSERVABILITY_CONFIG,
        'prometheus': {
            'enabled': True,
            'query_url': 'http://prometheus.example.com',
            'timeout': 3,
        },
    })
    @patch('ops.observability_views.http_requests.get')
    def test_observability_system_posture_uses_configured_ecommerce_rules(self, mock_get):
        system = SystemPostureSystem.objects.create(
            name='交易系统核心',
            domain='核心业务',
            tier='交易链路',
            owner='commerce-oncall',
            rule_config={
                'core_metric': {'target': 95},
                'status_rules': {
                    'critical': {'health_score_lt': 50, 'success_rate_lt': 90, 'checkout_5xx_rate_gte': 5},
                    'warning': {'health_score_lt': 80, 'success_rate_lt': 95, 'checkout_conflict_rate_gte': 10, 'checkout_p95_ms_gt': 500},
                },
                'root_cause_rules': [
                    {
                        'id': 'inventory-conflict',
                        'label': '库存冲突',
                        'metric': 'checkout_conflict_rate',
                        'min_rate': 10,
                        'critical_rate': 50,
                        'min_rps': 0.001,
                        'zero_success_is_critical': True,
                        'target_service_id': 'inventory',
                        'target_interface_id': 'inventory-availability',
                        'metric_label': '库存冲突率',
                        'warning_message': '库存冲突超过配置阈值。',
                        'critical_message': '库存冲突达到故障阈值。',
                    }
                ],
            },
        )
        mock_get.side_effect = self._mock_ecommerce_prometheus_get()

        response = self.client.get(f'/api/observability/system-posture/?system=custom-{system.id}')

        self.assertEqual(response.status_code, 200)
        selected = response.json()['selected_system']
        self.assertEqual(selected['name'], '交易系统核心')
        self.assertNotIn('window', selected['rule_config'])
        self.assertNotIn('window', selected['form']['rule_config'])
        self.assertEqual(selected['live']['window'], '30m')
        self.assertEqual(selected['rule_config']['core_metric']['target'], 95)
        self.assertEqual(selected['status'], 'healthy')
        inventory = next(item for item in selected['children'] if item['id'] == 'inventory')
        self.assertEqual(inventory['status'], 'healthy')
        conflict_metric = next(item for item in selected['metrics'] if item['label'] == 'Checkout 409占比')
        self.assertEqual(conflict_metric['target'], 10)
        self.assertEqual(conflict_metric['status'], 'healthy')

    def test_observability_system_posture_requires_system_posture_permission(self):
        limited_user = get_user_model().objects.create_user('system-posture-viewer', password='Admin@123456')
        self.client.force_authenticate(user=limited_user)

        response = self.client.get('/api/observability/system-posture/')

        self.assertEqual(response.status_code, 403)

    def test_system_posture_cards_can_be_managed_and_rendered(self):
        payload = {
            'name': '增长活动平台',
            'domain': '营销增长',
            'tier': '业务系统',
            'owner': 'growth-oncall',
            'summary': '活动投放、领券和转化链路的业务级卡片。',
            'base_status': 'warning',
            'health_score': 82,
            'keywords': ['增长活动', 'growth'],
            'core_metric': {'label': '转化成功率', 'value': 97.5, 'target': 99, 'unit': '%', 'direction': 'higher'},
            'metrics': [{'label': '转化成功率', 'value': 97.5, 'target': 99, 'unit': '%', 'direction': 'higher'}],
            'service_specs': [
                {
                    'id': 'growth-core',
                    'name': 'growth-service',
                    'role': '活动核心服务',
                    'base_status': 'warning',
                    'metrics': [{'label': '错误率', 'value': 1.1, 'target': 0.5, 'unit': '%', 'direction': 'lower'}],
                    'interfaces': [
                        {
                            'id': 'growth-coupon-api',
                            'name': '发券接口',
                            'base_status': 'warning',
                            'hint': '发券成功率低于目标',
                            'metrics': [{'label': 'P95', 'value': 260, 'target': 180, 'unit': 'ms', 'direction': 'lower'}],
                        }
                    ],
                }
            ],
            'dependencies': [
                {
                    'id': 'growth-redis',
                    'name': 'Redis 缓存',
                    'role': 'downstream',
                    'kind': '缓存',
                    'base_status': 'healthy',
                    'metrics': [{'label': '命中率', 'value': 98, 'target': 95, 'unit': '%', 'direction': 'higher'}],
                    'impact': '缓存穿透会影响活动接口耗时。',
                }
            ],
            'playbook': ['确认活动配置', '检查发券接口', '对齐最近发布'],
            'focus_service_id': 'growth-core',
            'focus_interface_id': 'growth-coupon-api',
            'sort_order': 5,
        }

        create_response = self.client.post('/api/observability/system-posture/systems/', payload, format='json')
        self.assertEqual(create_response.status_code, 201)
        system_id = create_response.json()['id']

        overview_response = self.client.get(f'/api/observability/system-posture/?system=custom-{system_id}')
        self.assertEqual(overview_response.status_code, 200)
        overview = overview_response.json()
        self.assertEqual(overview['selected_system_id'], f'custom-{system_id}')
        self.assertEqual(overview['selected_system']['name'], '增长活动平台')
        self.assertTrue(overview['selected_system']['editable'])
        self.assertEqual(overview['selected_system']['source_id'], system_id)
        self.assertEqual(overview['selected_system']['sort_order'], 5)
        self.assertEqual(overview['selected_system']['children'][0]['id'], 'growth-core')
        rendered_card = next(item for item in overview['systems'] if item['id'] == f'custom-{system_id}')
        self.assertEqual(rendered_card['sort_order'], 5)

        payload['owner'] = 'growth-sre'
        payload['health_score'] = 91
        payload['base_status'] = 'healthy'
        payload['sort_order'] = 3
        update_response = self.client.put(
            f'/api/observability/system-posture/systems/{system_id}/',
            payload,
            format='json',
        )
        self.assertEqual(update_response.status_code, 200)

        updated_overview = self.client.get(f'/api/observability/system-posture/?system=custom-{system_id}').json()
        self.assertEqual(updated_overview['selected_system']['owner'], 'growth-sre')
        self.assertEqual(updated_overview['selected_system']['sort_order'], 3)
        self.assertEqual(updated_overview['selected_system']['health_score'], 98)
        self.assertEqual(updated_overview['selected_system']['status'], 'critical')
        self.assertIsNone(updated_overview['selected_system']['children'][0]['health_score'])
        self.assertEqual(updated_overview['selected_system']['children'][0]['children'][0]['status'], 'unknown')

        delete_response = self.client.delete(f'/api/observability/system-posture/systems/{system_id}/')
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(SystemPostureSystem.objects.filter(id=system_id).exists())

    def test_system_posture_custom_card_without_structure_stays_unknown(self):
        create_response = self.client.post(
            '/api/observability/system-posture/systems/',
            {'name': 'Minimal Posture Card'},
            format='json',
        )
        self.assertEqual(create_response.status_code, 201)
        system_id = create_response.json()['id']

        overview_response = self.client.get(f'/api/observability/system-posture/?system=custom-{system_id}')
        self.assertEqual(overview_response.status_code, 200)
        selected = overview_response.json()['selected_system']
        self.assertEqual(selected['status'], 'unknown')
        self.assertIsNone(selected['health_score'])
        self.assertEqual(selected['core_metric'], {})
        self.assertEqual(selected['children'], [])
        self.assertEqual(selected['dependencies'], [])

    def test_builtin_system_posture_card_can_be_overridden_and_hidden(self):
        override = SystemPostureSystem.objects.create(
            name='交易系统核心',
            domain='交易域',
            tier='P0',
            owner='new-owner',
            summary='覆盖内置卡片配置',
            base_status='healthy',
            health_score=95,
            core_metric={'label': '下单成功率', 'value': 99.8, 'target': 99.9, 'unit': '%', 'direction': 'higher'},
            created_by='observer-admin',
            updated_by='observer-admin',
        )

        response = self.client.get('/api/observability/system-posture/?system=交易系统核心')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['selected_system']['source'], 'custom')
        self.assertTrue(payload['selected_system']['builtin_backed'])
        self.assertEqual(payload['selected_system']['source_id'], override.id)
        self.assertEqual(payload['selected_system']['owner'], 'new-owner')

        override.is_enabled = False
        override.save(update_fields=['is_enabled'])
        hidden_response = self.client.get('/api/observability/system-posture/')
        self.assertFalse(any(item['name'] == '交易系统核心' for item in hidden_response.json()['systems']))

    def test_hidden_builtin_system_is_filtered_from_history_and_today_snapshot_is_pruned(self):
        today = timezone.localdate()
        SystemPostureSystem.objects.create(
            name='交易系统核心',
            domain='交易域',
            tier='P0',
            owner='new-owner',
            summary='隐藏内置卡片',
            base_status='healthy',
            is_enabled=False,
            created_by='observer-admin',
            updated_by='observer-admin',
        )
        SystemPostureSLAHistory.objects.create(
            day=today,
            system_key='commerce-core',
            system_name='交易系统核心',
            environment='prod',
            domain='交易域',
            status='critical',
            sla_value=Decimal('93.800'),
            sla_target=Decimal('99.950'),
            health_score=82,
            metric_label='SLA',
            metric_unit='%',
            snapshot={},
        )

        response = self.client.get('/api/observability/system-posture/history/?days=7')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(any(item['id'] == 'commerce-core' for item in payload['systems']))
        self.assertTrue(SystemPostureSLAHistory.objects.filter(day=today, system_key='commerce-core').exists())

    def test_hidden_builtin_system_is_pruned_from_backfill_history(self):
        target_day = timezone.localdate() - timedelta(days=1)
        SystemPostureSystem.objects.create(
            name='交易系统核心',
            domain='交易域',
            tier='P0',
            owner='new-owner',
            summary='隐藏内置卡片',
            base_status='healthy',
            is_enabled=False,
            created_by='observer-admin',
            updated_by='observer-admin',
        )
        SystemPostureSLAHistory.objects.create(
            day=target_day,
            system_key='commerce-core',
            system_name='交易系统核心',
            environment='prod',
            domain='交易域',
            status='critical',
            sla_value=Decimal('93.800'),
            sla_target=Decimal('99.950'),
            health_score=82,
            metric_label='SLA',
            metric_unit='%',
            snapshot={},
        )

        response = self.client.get('/api/observability/system-posture/history/?days=7&backfill=1')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(any(item['id'] == 'commerce-core' for item in payload['systems']))
        self.assertFalse(SystemPostureSLAHistory.objects.filter(day=target_day, system_key='commerce-core').exists())

    def test_builtin_override_with_shallow_structure_still_renders_posture(self):
        SystemPostureSystem.objects.create(
            name='平台入口与网络',
            domain='基础设施域',
            tier='P1',
            owner='edge-owner',
            summary='浅结构覆盖',
            base_status='warning',
            service_specs=[
                {'id': 'nginx-ingress', 'name': 'Nginx Ingress', 'role': '入口层', 'interfaces': ['ingress-api', 'ingress-ssl']},
                {'id': 'dns-service', 'name': 'DNS 服务', 'role': '边界依赖', 'interfaces': ['dns-public', 'dns-private']},
            ],
            dependencies=[
                {'id': 'dns-resolver', 'role': 'upstream', 'reason': '解析质量决定入口请求是否能抵达'},
                {'id': 'origin-hosts', 'role': 'downstream', 'reason': '源站繁忙会放大入口 P95 与 5xx'},
            ],
            created_by='observer-admin',
            updated_by='observer-admin',
        )

        response = self.client.get('/api/observability/system-posture/?system=平台入口与网络')

        self.assertEqual(response.status_code, 200)
        selected = response.json()['selected_system']
        self.assertEqual(selected['name'], '平台入口与网络')
        self.assertTrue(selected['children'])
        self.assertTrue(selected['children'][0]['children'])
        self.assertTrue(all(item.get('name') for item in selected['dependencies']))

    def test_builtin_system_posture_override_inherits_rule_json_structure(self):
        SystemPostureSystem.objects.create(
            name='平台入口与网络',
            domain='基础设施域',
            tier='P1',
            owner='edge-owner',
            summary='只覆盖入口成功率目标',
            base_status='warning',
            core_metric={'label': '入口成功率', 'value': 99.1, 'target': 99, 'unit': '%', 'direction': 'higher'},
            rule_config={
                'core_metric': {
                    'label': '入口成功率',
                    'target': 99,
                    'unit': '%',
                    'direction': 'higher',
                },
            },
            created_by='observer-admin',
            updated_by='observer-admin',
        )

        response = self.client.get('/api/observability/system-posture/?system=平台入口与网络')

        self.assertEqual(response.status_code, 200)
        selected = response.json()['selected_system']
        rule_config = selected['form']['rule_config']
        self.assertEqual(rule_config['core_metric']['target'], 99)
        self.assertIn('drilldown', rule_config)
        self.assertIn('topology', rule_config)
        self.assertIn('nginx-ingress', [item['id'] for item in rule_config['drilldown']['services']])
        self.assertTrue(any(link['source'] == 'waf-rule' and link['target'] == 'platform-edge' for link in rule_config['topology']['links']))

    def test_system_posture_manage_requires_manage_permission(self):
        limited_user = get_user_model().objects.create_user('system-posture-readonly', password='Admin@123456')
        self.client.force_authenticate(user=limited_user)

        response = self.client.post(
            '/api/observability/system-posture/systems/',
            {'name': '只读用户卡片', 'base_status': 'healthy'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    @patch('ops.observability_views.user_has_permissions')
    def test_observability_overview_allows_log_only_user_without_trace_visibility(self, mock_permissions):
        existing_payload = self.client.get('/api/log/datasources/').json()
        existing_count = existing_payload.get('count', 0) if isinstance(existing_payload, dict) else len(existing_payload)
        self.client.post(
            '/api/log/datasources/',
            {
                'name': 'Overview Loki',
                'provider': 'loki',
                'config': {'endpoint': 'http://overview-loki:3100'},
            },
            format='json',
        )
        limited_user = get_user_model().objects.create_user('log-viewer', password='Admin@123456')
        self.client.force_authenticate(user=limited_user)

        def permission_side_effect(user, codes):
            code = codes[0] if codes else ''
            return code == 'ops.log.datasource.view'

        mock_permissions.side_effect = permission_side_effect

        response = self.client.get('/api/observability/overview/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload['modules']['tracing'])
        self.assertIsNone(payload['modules']['grafana'])
        self.assertEqual(payload['modules']['logs']['datasource_count'], existing_count + 1)
        self.assertEqual(len(payload['navigation']), 1)
        self.assertEqual(payload['navigation'][0]['path'], '/logs')

    @patch('ops.observability_views.user_has_permissions')
    def test_observability_overview_allows_system_posture_only_user(self, mock_permissions):
        limited_user = get_user_model().objects.create_user('posture-overview-viewer', password='Admin@123456')
        self.client.force_authenticate(user=limited_user)

        def permission_side_effect(user, codes):
            code = codes[0] if codes else ''
            return code == 'ops.observability.system_posture.view'

        mock_permissions.side_effect = permission_side_effect

        response = self.client.get('/api/observability/overview/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['navigation']), 1)
        self.assertEqual(payload['navigation'][0]['path'], '/observability/system-posture')
        self.assertIsNone(payload['modules']['tracing'])
        self.assertIsNone(payload['modules']['logs'])

    def test_observability_overview_uses_configured_grafana_dashboards(self):
        with override_settings(
            OBSERVABILITY_CONFIG={
                **TEST_OBSERVABILITY_CONFIG,
                'grafana': {
                    'enabled': True,
                    'url': 'http://grafana.example.com',
                    'default_path': '',
                    'demo_mode': True,
                    'dashboards': [
                        {
                            'key': 'custom-trace',
                            'title': '自定义链路总览',
                            'slug': 'custom-trace',
                            'path': '/d/custom-trace',
                            'panel_count': 6,
                            'tags': ['custom', 'trace'],
                            'description': '自定义链路看板',
                        }
                    ],
                },
            }
        ):
            response = self.client.get('/api/observability/overview/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['modules']['grafana']['dashboard_count'], 1)
        self.assertEqual(payload['modules']['grafana']['dashboards'][0]['key'], 'custom-trace')
        self.assertEqual(payload['modules']['grafana']['dashboards'][0]['url'], 'http://grafana.example.com/d/custom-trace')

    def test_grafana_config_endpoint_returns_defaults_when_not_persisted(self):
        response = self.client.get('/api/observability/grafana/config/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['persisted'])
        self.assertEqual(payload['url'], 'http://grafana.example.com')
        self.assertEqual(payload['default_path'], '/d/apm-overview')
        self.assertEqual(payload['folders'], [])
        self.assertGreaterEqual(len(payload['dashboards']), 1)

    def test_grafana_config_endpoint_can_persist_page_config(self):
        response = self.client.put(
            '/api/observability/grafana/config/',
            {
                'enabled': True,
                'url': '',
                'default_path': '',
                'folders': [
                    {'path': '基础设施', 'folder_collapsed': False},
                    {'path': '基础设施/节点', 'folder_collapsed': True},
                ],
                'dashboards': [
                    {
                        'key': 'infra-overview',
                        'title': '基础设施总览',
                        'slug': 'infra-overview',
                        'description': '基础设施看板',
                        'folder': '基础设施',
                        'path': '',
                        'full_url': 'http://grafana.internal.local/d/infra-overview',
                        'panel_count': 12,
                        'tags': ['infra'],
                    }
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['persisted'])
        self.assertEqual(payload['url'], '')
        self.assertEqual(payload['default_path'], '')
        self.assertEqual(len(payload['folders']), 2)
        self.assertEqual(payload['folders'][1]['path'], '基础设施/节点')

        setting = GrafanaSetting.objects.get(name='default')
        self.assertEqual(setting.url, '')
        self.assertEqual(setting.default_path, '')
        self.assertEqual(setting.folders[0]['path'], '基础设施')
        self.assertEqual(setting.dashboards[0]['folder'], '基础设施')
        self.assertEqual(setting.updated_by, 'observer-admin')

    def test_observability_overview_prefers_persisted_grafana_setting(self):
        GrafanaSetting.objects.create(
            name='default',
            enabled=True,
            url='http://grafana.persisted.example.com',
            default_path='/d/persisted-overview',
            dashboards=[
                {
                    'key': 'persisted-overview',
                    'title': '持久化看板',
                    'slug': 'persisted-overview',
                    'path': '/d/persisted-overview',
                    'panel_count': 8,
                    'tags': ['ops'],
                    'description': '来自页面保存的 Grafana 配置',
                }
            ],
            updated_by='observer-admin',
        )

        response = self.client.get('/api/observability/overview/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['modules']['grafana']['url'], 'http://grafana.persisted.example.com')
        self.assertEqual(payload['modules']['grafana']['dashboards'][0]['key'], 'persisted-overview')
        self.assertEqual(
            payload['modules']['grafana']['dashboards'][0]['url'],
            'http://grafana.persisted.example.com/d/persisted-overview',
        )

    def test_observability_overview_uses_dashboard_full_url_when_provided(self):
        GrafanaSetting.objects.create(
            name='default',
            enabled=True,
            url='',
            default_path='',
            dashboards=[
                {
                    'key': 'nightingale-style',
                    'title': '夜莺式看板',
                    'slug': 'nightingale-style',
                    'path': '',
                    'full_url': 'http://47.95.15.209:3000/d/custom-board?orgId=1&kiosk=true',
                    'panel_count': 9,
                    'tags': ['容器', '全局'],
                    'description': '直接写完整 Grafana 链接',
                }
            ],
            updated_by='observer-admin',
        )

        response = self.client.get('/api/observability/overview/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['modules']['grafana']['configured'])
        self.assertEqual(
            payload['modules']['grafana']['dashboards'][0]['url'],
            'http://47.95.15.209:3000/d/custom-board?orgId=1&kiosk=true',
        )
        self.assertEqual(
            payload['modules']['grafana']['dashboards'][0]['full_url'],
            'http://47.95.15.209:3000/d/custom-board?orgId=1&kiosk=true',
        )
        self.assertEqual(
            payload['modules']['grafana']['embed_url'],
            'http://47.95.15.209:3000/d/custom-board?orgId=1&kiosk=true',
        )

    def test_observability_overview_returns_configured_grafana_folders(self):
        GrafanaSetting.objects.create(
            name='default',
            enabled=True,
            url='',
            default_path='',
            folders=[
                {'path': '基础设施', 'folder_collapsed': False},
                {'path': '基础设施/节点', 'folder_collapsed': True},
                {'path': '应用服务', 'folder_collapsed': False},
            ],
            dashboards=[
                {
                    'key': 'node-overview',
                    'title': '节点总览',
                    'slug': 'node-overview',
                    'folder': '基础设施/节点',
                    'path': '',
                    'full_url': 'http://grafana.example.com/d/node-overview',
                    'panel_count': 6,
                    'tags': ['node'],
                    'description': '节点资源看板',
                }
            ],
            updated_by='observer-admin',
        )

        response = self.client.get('/api/observability/overview/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['modules']['grafana']['folders']), 3)
        self.assertEqual(payload['modules']['grafana']['folders'][1]['path'], '基础设施/节点')
        self.assertEqual(payload['modules']['grafana']['dashboards'][0]['folder'], '基础设施/节点')

    @patch('ops.observability_views.http_requests.get')
    def test_grafana_promql_query_uses_grafana_datasource_proxy(self, mock_get):
        mock_get.side_effect = [
            MockHttpResponse({'id': 12, 'uid': 'prometheus-infra'}),
            MockHttpResponse({
                'status': 'success',
                'data': {
                    'resultType': 'vector',
                    'result': [{'metric': {'job': 'api'}, 'value': [1710000000, '1']}],
                },
            }),
        ]

        response = self.client.post(
            '/api/observability/grafana/promql/query/',
            {'query': 'up{job="api"}', 'datasource_uid': 'prometheus-infra', 'grafana_url': 'http://grafana.internal.local'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['source'], 'grafana')
        self.assertEqual(payload['series_count'], 1)
        self.assertIn('/api/datasources/uid/prometheus-infra', mock_get.call_args_list[0].args[0])
        self.assertIn('/api/datasources/proxy/12/api/v1/query', mock_get.call_args_list[1].args[0])

    @patch('ops.observability_views.http_requests.get')
    def test_metrics_query_uses_metric_datasource(self, mock_get):
        datasource = MetricDataSource.objects.create(
            name='Retail Test Prometheus',
            environment='test',
            is_default=True,
            config={
                'query_url': 'http://prometheus.test.local:9090',
                'auth_type': 'bearer',
                'bearer_token': 'secret-token',
                'headers': {'X-Scope-OrgID': 'retail'},
            },
        )
        mock_get.return_value = MockHttpResponse({
            'status': 'success',
            'data': {
                'resultType': 'vector',
                'result': [{'metric': {'job': 'api'}, 'value': [1710000000, '1']}],
            },
        })

        response = self.client.post(
            '/api/observability/metrics/query/',
            {'query': 'up', 'metric_datasource_id': datasource.id},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['source'], 'metric_datasource')
        self.assertEqual(payload['metric_datasource']['id'], datasource.id)
        self.assertIn('/api/v1/query', mock_get.call_args.args[0])
        self.assertEqual(mock_get.call_args.kwargs['headers']['Authorization'], 'Bearer secret-token')

    @patch('ops.observability_views.http_requests.get')
    def test_metrics_series_names_uses_prometheus_label_values(self, mock_get):
        datasource = MetricDataSource.objects.create(
            name='Retail Metrics',
            environment='test',
            is_default=True,
            config={
                'query_url': 'http://prometheus.test.local:9090',
                'headers': {'X-Scope-OrgID': 'retail'},
            },
        )
        mock_get.return_value = MockHttpResponse({
            'status': 'success',
            'data': [
                'http_requests_total',
                'node_cpu_seconds_total',
                'node_memory_MemAvailable_bytes',
                'process_cpu_seconds_total',
            ],
        })

        response = self.client.get(
            '/api/observability/metrics/series-names/',
            {'metric_datasource_id': datasource.id, 'q': 'node_', 'limit': 5},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['metrics'], ['node_cpu_seconds_total', 'node_memory_MemAvailable_bytes'])
        self.assertEqual(payload['metric_datasource']['id'], datasource.id)
        self.assertIn('/api/v1/label/__name__/values', mock_get.call_args.args[0])
        self.assertEqual(mock_get.call_args.kwargs['headers']['X-Scope-OrgID'], 'retail')
        self.assertEqual(mock_get.call_args.kwargs['params']['match[]'], '{__name__=~".*node_.*"}')

    def test_metric_datasource_serializer_masks_secrets(self):
        datasource = MetricDataSource.objects.create(
            name='Secure Prometheus',
            config={
                'query_url': 'http://prometheus.local:9090',
                'password': 'secret',
                'bearer_token': 'token',
                'headers': {'Authorization': 'Bearer token', 'X-Team': 'ops'},
                'prometheus.basic': {'prometheus.user': 'admin', 'prometheus.password': 'secret'},
            },
        )

        response = self.client.get(f'/api/observability/metric/datasources/{datasource.id}/')

        self.assertEqual(response.status_code, 200)
        config = response.json()['config']
        self.assertEqual(config['password'], 'configured')
        self.assertEqual(config['bearer_token'], 'configured')
        self.assertEqual(config['headers']['Authorization'], 'configured')
        self.assertEqual(config['headers']['X-Team'], 'ops')
        self.assertEqual(config['prometheus.basic']['prometheus.password'], 'configured')

    @patch('ops.observability_views.http_requests.get')
    def test_grafana_panel_query_fetches_dashboard_targets_and_runs_range_query(self, mock_get):
        GrafanaSetting.objects.create(name='default', enabled=True, url='http://grafana.internal.local')
        mock_get.side_effect = [
            MockHttpResponse({
                'dashboard': {
                    'title': 'K8s Workload',
                    'panels': [{
                        'id': 7,
                        'title': 'CPU 使用率',
                        'targets': [{'expr': 'sum(rate(container_cpu_usage_seconds_total{namespace="$namespace"}[5m]))'}],
                    }],
                },
            }),
            MockHttpResponse({'id': 12, 'uid': 'prometheus-infra'}),
            MockHttpResponse({
                'status': 'success',
                'data': {
                    'resultType': 'matrix',
                    'result': [{'metric': {'namespace': 'prod'}, 'values': [[1710000000, '0.4'], [1710000060, '0.5']]}],
                },
            }),
        ]

        response = self.client.post(
            '/api/observability/grafana/panel/query/',
            {
                'dashboard_key': 'k8s-workload',
                'panel_title': 'CPU',
                'variables': {'namespace': 'prod'},
                'step': '60s',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['dashboard_uid'], 'k8s-workload')
        self.assertEqual(payload['panel_id'], 7)
        self.assertEqual(payload['queries'][0]['series_count'], 1)
        self.assertIn('/api/dashboards/uid/k8s-workload', mock_get.call_args_list[0].args[0])
        self.assertIn('query_range', mock_get.call_args_list[2].args[0])

    @override_settings(OBSERVABILITY_CONFIG={
        'grafana': {'enabled': True, 'url': '/grafana'},
        'prometheus': {'grafana_url': 'http://grafana.internal.local/grafana'},
    })
    def test_relative_grafana_embed_url_uses_internal_api_endpoint(self):
        from ops.observability_views import _grafana_api_base, _grafana_meta

        GrafanaSetting.objects.create(name='default', enabled=True, url='/grafana')

        self.assertEqual(_grafana_api_base(), 'http://grafana.internal.local/grafana')
        self.assertTrue(_grafana_meta()['embed_url'].startswith('/grafana/'))

    @patch('ops.observability_views.execute_promql_query')
    @patch('ops.observability_views.http_requests.get')
    def test_grafana_panel_query_resolves_configured_url_and_slo_variables(self, mock_get, mock_promql):
        from ops.observability_views import execute_dashboard_panel_queries

        GrafanaSetting.objects.create(name='default', enabled=True, url='', dashboards=[{
            'key': 'checkout-slo', 'title': 'Checkout SLO',
            'url': 'http://grafana.internal.local/grafana/d/real-slo-uid/checkout-slo',
        }])
        mock_get.return_value = MockHttpResponse({'dashboard': {
            'templating': {'list': [{'name': 'namespace', 'current': {'value': 'other'}}]},
            'panels': [
                {'id': 1, 'title': 'SLO Context', 'type': 'text'},
                {'id': 2, 'title': 'CPU', 'targets': [{'expr': 'up'}]},
                {'id': 3, 'title': 'Checkout Success Rate', 'targets': [{
                    'expr': 'sum(increase(requests_total{namespace="$namespace"}[$__range])) / $__range_s',
                }]},
            ],
        }})
        mock_promql.return_value = {'series_count': 1, 'result': []}
        end = timezone.now()

        result = execute_dashboard_panel_queries(
            'checkout-slo', panel_keywords=['success'], variables={'namespace': 'checkout'},
            start_time=end - timedelta(minutes=30), end_time=end,
        )

        self.assertEqual(result['dashboard_uid'], 'real-slo-uid')
        self.assertEqual(result['panel_id'], 3)
        self.assertEqual(mock_get.call_args.args[0], 'http://grafana.internal.local/grafana/api/dashboards/uid/real-slo-uid')
        self.assertEqual(mock_promql.call_args.args[0], 'sum(increase(requests_total{namespace="checkout"}[1800s])) / 1800')
        mock_promql.reset_mock()
        with self.assertRaisesRegex(RuntimeError, '未找到可分析'):
            execute_dashboard_panel_queries('checkout-slo', panel_id=999)
        mock_promql.assert_not_called()

    @patch('ops.observability_views.execute_promql_query')
    @patch('ops.observability_views.http_requests.get')
    def test_grafana_panel_query_rejects_unresolved_variables(self, mock_get, mock_promql):
        from ops.observability_views import execute_dashboard_panel_queries

        GrafanaSetting.objects.create(name='default', enabled=True, url='http://grafana.internal.local')
        mock_get.return_value = MockHttpResponse({'dashboard': {'panels': [{
            'id': 1, 'title': 'Latency', 'targets': [{'expr': 'up{namespace="$unknown_namespace"}'}],
        }]}})
        with self.assertRaisesRegex(RuntimeError, '未解析的查询变量'):
            execute_dashboard_panel_queries('latency')
        mock_promql.assert_not_called()

    @patch('ops.tracing_providers.http_requests.post')
    def test_tracing_catalog_uses_skywalking_graphql_when_configured(self, mock_post):
        mock_post.side_effect = [
            MockHttpResponse({
                'data': {
                    'listServices': [
                        {'id': 'service-1', 'name': 'gateway-service', 'shortName': 'gateway', 'group': 'sxdevops', 'layers': ['GENERAL']},
                        {'id': 'service-2', 'name': 'payment-service', 'shortName': 'payment', 'group': 'sxdevops', 'layers': ['GENERAL']},
                    ]
                }
            }),
            MockHttpResponse({
                'data': {
                    'getGlobalTopology': {
                        'nodes': [{'id': 'service-1', 'name': 'gateway-service', 'type': 'SERVICE', 'layers': ['GENERAL']}],
                        'calls': [{'id': 'call-1', 'source': 'service-1', 'target': 'service-2'}],
                    }
                }
            }),
            MockHttpResponse({
                'data': {
                    'queryBasicTraces': {
                        'traces': [
                            {
                                'segmentId': 'segment-1',
                                'endpointNames': ['GET /api/orders/{id}'],
                                'duration': 212,
                                'start': '2026-03-29 09:15',
                                'isError': False,
                                'traceIds': ['trace-1'],
                            }
                        ]
                    }
                }
            }),
            MockHttpResponse({
                'data': {
                    'queryTrace': {
                        'spans': [
                            {
                                'traceId': 'trace-1',
                                'segmentId': 'segment-1',
                                'spanId': 0,
                                'parentSpanId': -1,
                                'serviceCode': 'gateway-service',
                                'serviceInstanceName': 'gateway-prod-01',
                                'startTime': 1711674900000,
                                'endTime': 1711674900212,
                                'endpointName': 'GET /api/orders/{id}',
                                'type': 'Entry',
                                'peer': '',
                                'component': 'SpringMVC',
                                'isError': False,
                                'layer': 'HTTP',
                                'tags': [{'key': 'http.status_code', 'value': '200'}],
                                'logs': [],
                            }
                        ]
                    }
                }
            }),
            MockHttpResponse({
                'data': {
                    'getServiceInstances': [
                        {'id': 'gateway-prod-01', 'name': 'gateway-prod-01'},
                    ]
                }
            }),
        ]

        response = self.client.get('/api/observability/tracing/catalog/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['tracing']['source'], 'skywalking')
        self.assertEqual(payload['summary']['service_count'], 2)
        self.assertEqual(payload['summary']['topology_calls'], 1)
        self.assertEqual(payload['recent_traces'][0]['trace_id'], 'trace-1')
        self.assertEqual(payload['recent_traces'][0]['summary'], '')
        self.assertTrue(any(item['provider'] == 'demo' for item in payload['providers']))
        self.assertEqual(mock_post.call_count, 5)

    def test_tracing_catalog_can_force_demo_provider(self):
        response = self.client.get('/api/observability/tracing/catalog/?provider=demo')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['tracing']['provider'], 'demo')
        self.assertEqual(payload['tracing']['source'], 'demo')
        self.assertGreaterEqual(len(payload['recent_traces']), 1)
        self.assertGreaterEqual(len(payload['instances']), 1)

    def test_tracing_search_can_filter_demo_instance(self):
        response = self.client.post(
            '/api/observability/tracing/search/',
            {
                'provider': 'demo',
                'service_id': 'svc-order',
                'instance_name': 'order-prod-02',
                'limit': 20,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['query']['instance_name'], 'order-prod-02')
        self.assertEqual(len(payload['traces']), 1)
        self.assertEqual(payload['traces'][0]['instance_name'], 'order-prod-02')
        self.assertTrue(any(item['name'] == 'order-prod-02' for item in payload['instances']))

    @patch('ops.tracing_providers._skywalking_query')
    def test_skywalking_trace_id_search_does_not_force_first_service(self, mock_query):
        mock_query.return_value = {
            'queryBasicTraces': {
                'traces': [
                    {
                        'segmentId': 'segment-trace-only',
                        'endpointNames': ['GET /checkout'],
                        'duration': 128,
                        'start': '2026-09-20 08:00',
                        'isError': False,
                        'traceIds': ['trace-only-id'],
                    }
                ]
            }
        }

        traces = _search_skywalking_traces(
            {'oap_url': 'http://skywalking-oap.example.com', 'graphql_path': '/graphql'},
            {'trace_id': 'trace-only-id', 'limit': 'invalid'},
            [{'id': 'service-1', 'name': 'gateway-service'}],
        )

        condition = mock_query.call_args.args[1]['condition']
        self.assertNotIn('serviceId', condition)
        self.assertEqual(condition['traceId'], 'trace-only-id')
        self.assertEqual(condition['paging']['pageSize'], 20)
        self.assertEqual(traces[0]['trace_id'], 'trace-only-id')
        self.assertEqual(traces[0]['service_id'], '')

    def test_can_create_tracing_datasource(self):
        response = self.client.post(
            '/api/observability/tracing/datasources/',
            {
                'name': 'Production Tempo',
                'provider': 'tempo',
                'description': 'OTel Tempo 查询入口',
                'is_enabled': True,
                'is_default': True,
                'config': {
                    'query_url': 'http://tempo.example.com',
                    'ui_url': 'http://grafana.example.com/explore',
                    'authorization': 'Bearer secret-token',
                    'demo_mode': True,
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload['provider'], 'tempo')
        self.assertIs(payload['config']['demo_mode'], False)
        self.assertEqual(payload['config']['authorization'], 'configured')

        list_response = self.client.get('/api/observability/tracing/datasources/')
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()[0]['name'], 'Production Tempo')

    @patch('ops.observability_views.test_tracing_connection')
    def test_can_test_tracing_datasource_connection(self, mock_test_connection):
        create_response = self.client.post(
            '/api/observability/tracing/datasources/',
            {
                'name': 'Production Jaeger',
                'provider': 'jaeger',
                'description': 'Jaeger 查询入口',
                'is_enabled': True,
                'is_default': True,
                'config': {
                    'query_url': 'http://jaeger.example.com',
                    'ui_url': 'http://jaeger-ui.example.com',
                    'demo_mode': False,
                },
            },
            format='json',
        )
        datasource_id = create_response.json()['id']
        mock_test_connection.return_value = {'kind': 'services', 'count': 3, 'items': [{'id': 'svc-a'}]}

        response = self.client.post(f'/api/observability/tracing/datasources/{datasource_id}/test_connection/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['preview_count'], 3)
        mock_test_connection.assert_called_once()

    @patch('ops.tracing_providers.http_requests.get')
    def test_tracing_catalog_uses_jaeger_query_when_configured(self, mock_get):
        mock_get.side_effect = [
            MockHttpResponse({'data': ['gateway-service', 'order-service']}),
            MockHttpResponse({
                'data': [
                    {
                        'traceID': 'jaeger-trace-1',
                        'processes': {'p1': {'serviceName': 'gateway-service'}, 'p2': {'serviceName': 'order-service'}},
                        'spans': [
                            {
                                'spanID': 'span-root',
                                'processID': 'p1',
                                'operationName': 'GET /api/orders',
                                'startTime': 1711674900000000,
                                'duration': 250000,
                                'tags': [{'key': 'http.status_code', 'value': '200'}],
                                'references': [],
                            },
                            {
                                'spanID': 'span-child',
                                'processID': 'p2',
                                'operationName': 'queryOrder',
                                'startTime': 1711674900040000,
                                'duration': 120000,
                                'tags': [],
                                'references': [{'refType': 'CHILD_OF', 'spanID': 'span-root'}],
                            },
                        ],
                    }
                ]
            }),
            MockHttpResponse({
                'data': [
                    {
                        'traceID': 'jaeger-trace-1',
                        'processes': {'p1': {'serviceName': 'gateway-service'}, 'p2': {'serviceName': 'order-service'}},
                        'spans': [
                            {
                                'spanID': 'span-root',
                                'processID': 'p1',
                                'operationName': 'GET /api/orders',
                                'startTime': 1711674900000000,
                                'duration': 250000,
                                'tags': [{'key': 'http.status_code', 'value': '200'}],
                                'references': [],
                            },
                            {
                                'spanID': 'span-child',
                                'processID': 'p2',
                                'operationName': 'queryOrder',
                                'startTime': 1711674900040000,
                                'duration': 120000,
                                'tags': [],
                                'references': [{'refType': 'CHILD_OF', 'spanID': 'span-root'}],
                            },
                        ],
                    }
                ]
            }),
            MockHttpResponse({
                'data': [
                    {
                        'traceID': 'jaeger-trace-1',
                        'processes': {'p1': {'serviceName': 'gateway-service'}, 'p2': {'serviceName': 'order-service'}},
                        'spans': [
                            {
                                'spanID': 'span-root',
                                'processID': 'p1',
                                'operationName': 'GET /api/orders',
                                'startTime': 1711674900000000,
                                'duration': 250000,
                                'tags': [{'key': 'http.status_code', 'value': '200'}],
                                'references': [],
                            },
                            {
                                'spanID': 'span-child',
                                'processID': 'p2',
                                'operationName': 'queryOrder',
                                'startTime': 1711674900040000,
                                'duration': 120000,
                                'tags': [],
                                'references': [{'refType': 'CHILD_OF', 'spanID': 'span-root'}],
                            },
                        ],
                    }
                ]
            }),
        ]

        with override_settings(
            OBSERVABILITY_CONFIG={
                **TEST_OBSERVABILITY_CONFIG,
                'tracing': {'default_provider': 'jaeger'},
                'skywalking': {**TEST_OBSERVABILITY_CONFIG['skywalking'], 'enabled': False},
                'jaeger': {
                    'provider': 'jaeger',
                    'enabled': True,
                    'query_url': 'http://jaeger.example.com',
                    'ui_url': 'http://jaeger-ui.example.com',
                    'demo_mode': False,
                },
            }
        ):
            response = self.client.get('/api/observability/tracing/catalog/?provider=jaeger')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['tracing']['source'], 'jaeger')
        self.assertEqual(payload['providers'][0]['provider'], 'jaeger')
        self.assertEqual(payload['summary']['service_count'], 2)
        self.assertEqual(payload['recent_traces'][0]['trace_id'], 'jaeger-trace-1')
        self.assertEqual(payload['topology']['call_count'], 1)

    @patch('ops.tracing_providers.http_requests.get')
    def test_tracing_search_uses_requested_datasource_config(self, mock_get):
        create_default = self.client.post(
            '/api/observability/tracing/datasources/',
            {
                'name': 'Default Jaeger',
                'provider': 'jaeger',
                'is_enabled': True,
                'is_default': True,
                'config': {
                    'query_url': 'http://jaeger-default.example.com',
                    'ui_url': 'http://jaeger-default-ui.example.com',
                    'demo_mode': False,
                },
            },
            format='json',
        )
        create_alternate = self.client.post(
            '/api/observability/tracing/datasources/',
            {
                'name': 'Alternate Jaeger',
                'provider': 'jaeger',
                'is_enabled': True,
                'is_default': False,
                'config': {
                    'query_url': 'http://jaeger-alt.example.com',
                    'ui_url': 'http://jaeger-alt-ui.example.com',
                    'demo_mode': False,
                },
            },
            format='json',
        )
        datasource_id = create_alternate.json()['id']
        trace_payload = {
            'traceID': 'jaeger-trace-alt',
            'processes': {'p1': {'serviceName': 'gateway-service'}},
            'spans': [
                {
                    'spanID': 'span-root',
                    'processID': 'p1',
                    'operationName': 'GET /api/orders',
                    'startTime': 1711674900000000,
                    'duration': 250000,
                    'tags': [{'key': 'http.status_code', 'value': '200'}],
                    'references': [],
                }
            ],
        }
        mock_get.side_effect = [
            MockHttpResponse({'data': ['gateway-service']}),
            MockHttpResponse({'data': [trace_payload]}),
            MockHttpResponse({'data': [trace_payload]}),
            MockHttpResponse({'data': [trace_payload]}),
            MockHttpResponse({'data': [trace_payload]}),
            MockHttpResponse({'data': [trace_payload]}),
        ]

        response = self.client.post(
            '/api/observability/tracing/search/',
            {
                'provider': 'jaeger',
                'datasource_id': datasource_id,
                'service_id': 'gateway-service',
                'limit': 10,
            },
            format='json',
        )

        self.assertEqual(create_default.status_code, 201)
        self.assertEqual(create_alternate.status_code, 201)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(str(payload['tracing']['datasource_id']), str(datasource_id))
        self.assertEqual(payload['traces'][0]['trace_id'], 'jaeger-trace-alt')
        self.assertIn(
            'http://jaeger-alt.example.com/api/traces',
            [call.args[0] for call in mock_get.call_args_list],
        )
        self.assertEqual(
            mock_get.call_args_list[-1].args[0],
            'http://jaeger-alt.example.com/api/traces/jaeger-trace-alt',
        )

    @patch('ops.tracing_providers.http_requests.get')
    def test_tracing_search_supports_absolute_time_range(self, mock_get):
        self.client.post(
            '/api/observability/tracing/datasources/',
            {
                'name': 'Absolute Range Jaeger',
                'provider': 'jaeger',
                'is_enabled': True,
                'is_default': True,
                'config': {
                    'query_url': 'http://jaeger-absolute.example.com',
                    'ui_url': 'http://jaeger-absolute-ui.example.com',
                    'demo_mode': False,
                },
            },
            format='json',
        )
        trace_payload = {
            'traceID': 'jaeger-trace-range',
            'processes': {'p1': {'serviceName': 'gateway-service'}},
            'spans': [
                {
                    'spanID': 'span-root',
                    'processID': 'p1',
                    'operationName': 'GET /api/orders',
                    'startTime': 1711674900000000,
                    'duration': 250000,
                    'tags': [{'key': 'http.status_code', 'value': '200'}],
                    'references': [],
                }
            ],
        }
        mock_get.side_effect = [
            MockHttpResponse({'data': ['gateway-service']}),
            MockHttpResponse({'data': [trace_payload]}),
            MockHttpResponse({'data': [trace_payload]}),
            MockHttpResponse({'data': [trace_payload]}),
            MockHttpResponse({'data': [trace_payload]}),
            MockHttpResponse({'data': [trace_payload]}),
        ]

        start_time = '2026-04-10T11:00:00+08:00'
        end_time = '2026-04-10T11:45:00+08:00'
        response = self.client.post(
            '/api/observability/tracing/search/',
            {
                'provider': 'jaeger',
                'service_id': 'gateway-service',
                'start_time': start_time,
                'end_time': end_time,
                'duration_minutes': 5,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['query']['start_time'], start_time)
        self.assertEqual(payload['query']['end_time'], end_time)
        trace_calls = [
            call
            for call in mock_get.call_args_list
            if call.args[0] == 'http://jaeger-absolute.example.com/api/traces'
        ]
        params = trace_calls[-1].kwargs['params']
        self.assertEqual(params['start'], int(datetime.fromisoformat(start_time).timestamp() * 1000000))
        self.assertEqual(params['end'], int(datetime.fromisoformat(end_time).timestamp() * 1000000))

    @patch('ops.tracing_providers.http_requests.get')
    def test_trace_detail_uses_requested_datasource_config(self, mock_get):
        self.client.post(
            '/api/observability/tracing/datasources/',
            {
                'name': 'Primary Jaeger',
                'provider': 'jaeger',
                'is_enabled': True,
                'is_default': True,
                'config': {
                    'query_url': 'http://jaeger-primary.example.com',
                    'ui_url': 'http://jaeger-primary-ui.example.com',
                    'demo_mode': False,
                },
            },
            format='json',
        )
        create_alternate = self.client.post(
            '/api/observability/tracing/datasources/',
            {
                'name': 'Focused Jaeger',
                'provider': 'jaeger',
                'is_enabled': True,
                'is_default': False,
                'config': {
                    'query_url': 'http://jaeger-focused.example.com',
                    'ui_url': 'http://jaeger-focused-ui.example.com',
                    'demo_mode': False,
                },
            },
            format='json',
        )
        datasource_id = create_alternate.json()['id']
        trace_payload = {
            'traceID': 'jaeger-trace-detail',
            'processes': {'p1': {'serviceName': 'gateway-service'}},
            'spans': [
                {
                    'spanID': 'span-root',
                    'processID': 'p1',
                    'operationName': 'GET /api/orders',
                    'startTime': 1711674900000000,
                    'duration': 250000,
                    'tags': [{'key': 'http.status_code', 'value': '200'}],
                    'references': [],
                }
            ],
        }
        mock_get.side_effect = [
            MockHttpResponse({'data': ['gateway-service']}),
            MockHttpResponse({'data': [trace_payload]}),
            MockHttpResponse({'data': [trace_payload]}),
            MockHttpResponse({'data': [trace_payload]}),
            MockHttpResponse({'data': [trace_payload]}),
            MockHttpResponse({'data': [trace_payload]}),
        ]

        response = self.client.get(
            f'/api/observability/tracing/traces/jaeger-trace-detail/?provider=jaeger&datasource_id={datasource_id}'
        )

        self.assertEqual(create_alternate.status_code, 201)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['trace']['trace_id'], 'jaeger-trace-detail')
        self.assertEqual(payload['trace']['summary'], '')
        self.assertEqual(str(payload['tracing']['datasource_id']), str(datasource_id))
        self.assertEqual(
            mock_get.call_args_list[-1].args[0],
            'http://jaeger-focused.example.com/api/traces/jaeger-trace-detail',
        )

    def test_tracing_catalog_rejects_provider_datasource_mismatch(self):
        create_response = self.client.post(
            '/api/observability/tracing/datasources/',
            {
                'name': 'Mismatch Jaeger',
                'provider': 'jaeger',
                'is_enabled': True,
                'is_default': True,
                'config': {
                    'query_url': 'http://jaeger-mismatch.example.com',
                    'ui_url': 'http://jaeger-mismatch-ui.example.com',
                    'demo_mode': False,
                },
            },
            format='json',
        )
        datasource_id = create_response.json()['id']

        catalog_response = self.client.get(
            f'/api/observability/tracing/catalog/?provider=tempo&datasource_id={datasource_id}'
        )
        search_response = self.client.post(
            '/api/observability/tracing/search/',
            {'provider': 'tempo', 'datasource_id': datasource_id},
            format='json',
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(catalog_response.status_code, 400)
        self.assertEqual(search_response.status_code, 400)
        self.assertIn('provider 与链路数据源类型不一致', catalog_response.json()['detail'])
        self.assertIn('provider 与链路数据源类型不一致', search_response.json()['detail'])

    def test_trace_detail_preserves_tempo_resource_and_scope_attributes(self):
        detail = _trace_detail_from_spans('tempo-trace-1', [
            {
                'span_id': 'span-root',
                'parent_span_id': '',
                'service_code': 'api-gateway',
                'endpoint_name': 'GET /api/products',
                'start_time': '2026-05-03T12:00:00+00:00',
                'end_time': '2026-05-03T12:00:01+00:00',
                'duration_ms': 1000,
                'tags': [{'key': 'http.method', 'value': 'GET'}],
                'resource_tags': [
                    {'key': 'service.name', 'value': 'api-gateway'},
                    {'key': 'k8s.pod.name', 'value': 'api-gateway-123'},
                ],
                'scope_tags': [{'key': 'telemetry.scope.name', 'value': 'opentelemetry.instrumentation.django'}],
            }
        ])

        span = detail['spans'][0]
        self.assertEqual(span['resource_tags'][1]['key'], 'k8s.pod.name')
        self.assertEqual(span['scope_tags'][0]['value'], 'opentelemetry.instrumentation.django')

    def test_trace_topology_includes_runtime_component_dependencies(self):
        detail = _trace_detail_from_spans('tempo-runtime-trace', [
            {
                'span_id': 'root',
                'parent_span_id': '',
                'service_code': 'checkout',
                'endpoint_name': 'GET /checkout',
                'start_time': '2026-05-03T12:00:00+00:00',
                'end_time': '2026-05-03T12:00:01+00:00',
            },
            {
                'span_id': 'redis',
                'parent_span_id': 'root',
                'service_code': 'checkout',
                'endpoint_name': 'Redis GET cart',
                'start_time': '2026-05-03T12:00:00.100+00:00',
                'end_time': '2026-05-03T12:00:00.140+00:00',
                'component': 'Jedis',
                'peer': 'redis:6379',
                'layer': 'CACHE',
            },
            {
                'span_id': 'postgres',
                'parent_span_id': 'root',
                'service_code': 'checkout',
                'endpoint_name': 'SELECT products',
                'start_time': '2026-05-03T12:00:00.200+00:00',
                'end_time': '2026-05-03T12:00:00.320+00:00',
                'tags': [{'key': 'db.system', 'value': 'postgresql'}],
                'layer': 'DATABASE',
            },
        ])

        topology = _build_topology_from_trace_details([detail])

        node_ids = {node['id'] for node in topology['nodes']}
        self.assertIn('checkout', node_ids)
        self.assertIn('runtime:redis', node_ids)
        self.assertIn('runtime:postgresql', node_ids)
        self.assertTrue(any(call['source'] == 'checkout' and call['target'] == 'runtime:redis' for call in topology['calls']))
        self.assertTrue(any(call['source'] == 'checkout' and call['target'] == 'runtime:postgresql' for call in topology['calls']))

    def test_trace_topology_keeps_multi_hop_service_dependencies(self):
        detail = _trace_detail_from_spans('tempo-layered-trace', [
            {
                'span_id': 'root',
                'parent_span_id': '',
                'service_code': 'api-gateway',
                'endpoint_name': 'POST /checkout',
                'start_time': '2026-05-03T12:00:00+00:00',
                'end_time': '2026-05-03T12:00:01+00:00',
                'layer': 'HTTP',
            },
            {
                'span_id': 'order',
                'parent_span_id': 'root',
                'service_code': 'order-service',
                'endpoint_name': 'POST /orders',
                'start_time': '2026-05-03T12:00:00.100+00:00',
                'end_time': '2026-05-03T12:00:00.600+00:00',
                'layer': 'RPC_FRAMEWORK',
            },
            {
                'span_id': 'inventory',
                'parent_span_id': 'order',
                'service_code': 'inventory-service',
                'endpoint_name': 'GET /availability',
                'start_time': '2026-05-03T12:00:00.200+00:00',
                'end_time': '2026-05-03T12:00:00.500+00:00',
                'layer': 'RPC_FRAMEWORK',
            },
            {
                'span_id': 'redis',
                'parent_span_id': 'inventory',
                'service_code': 'inventory-service',
                'endpoint_name': 'Redis GET stock',
                'start_time': '2026-05-03T12:00:00.250+00:00',
                'end_time': '2026-05-03T12:00:00.300+00:00',
                'component': 'Jedis',
                'peer': 'redis-inventory:6379',
                'layer': 'CACHE',
            },
        ])

        topology = _build_topology_from_trace_details([detail])
        call_pairs = {(call['source'], call['target']) for call in topology['calls']}

        self.assertIn(('api-gateway', 'order-service'), call_pairs)
        self.assertIn(('order-service', 'inventory-service'), call_pairs)
        self.assertIn(('inventory-service', 'runtime:redis-inventory'), call_pairs)

    def test_tempo_flatten_trace_keeps_full_resource_attributes(self):
        spans = _tempo_flatten_trace({
            'batches': [
                {
                    'resource': {
                        'attributes': {
                            'service.name': {'stringValue': 'api-gateway'},
                            'k8s.namespace.name': {'stringValue': 'default'},
                            'k8s.pod.name': {'stringValue': 'api-gateway-123'},
                            'telemetry.sdk.language': {'stringValue': 'python'},
                        }
                    },
                    'scopeSpans': [
                        {
                            'scope': {'name': 'opentelemetry.instrumentation.django', 'version': '0.45b0'},
                            'spans': [
                                {
                                    'spanId': 'span-root',
                                    'name': 'GET /api/products',
                                    'startTimeUnixNano': '1770000000000000000',
                                    'endTimeUnixNano': '1770000001000000000',
                                    'attributes': [{'key': 'http.method', 'value': {'stringValue': 'GET'}}],
                                }
                            ],
                        }
                    ],
                }
            ]
        })

        self.assertEqual(len(spans), 1)
        resource_keys = {item['key'] for item in spans[0]['resource_tags']}
        scope_keys = {item['key'] for item in spans[0]['scope_tags']}
        self.assertIn('k8s.namespace.name', resource_keys)
        self.assertIn('k8s.pod.name', resource_keys)
        self.assertIn('telemetry.sdk.language', resource_keys)
        self.assertIn('telemetry.scope.name', scope_keys)

    @patch('ops.tracing_providers.http_requests.post')
    def test_trace_detail_returns_span_summary_from_skywalking(self, mock_post):
        mock_post.side_effect = [
            MockHttpResponse({
                'data': {
                    'listServices': [
                        {'id': 'service-1', 'name': 'gateway-service', 'shortName': 'gateway', 'group': 'sxdevops', 'layers': ['GENERAL']},
                    ]
                }
            }),
            MockHttpResponse({
                'data': {
                    'getGlobalTopology': {
                        'nodes': [{'id': 'service-1', 'name': 'gateway-service', 'type': 'SERVICE', 'layers': ['GENERAL']}],
                        'calls': [],
                    }
                }
            }),
            MockHttpResponse({
                'data': {
                    'queryBasicTraces': {
                        'traces': [
                            {
                                'segmentId': 'segment-1',
                                'endpointNames': ['GET /api/orders/{id}'],
                                'duration': 212,
                                'start': '2026-03-29 09:15',
                                'isError': False,
                                'traceIds': ['trace-1'],
                            }
                        ]
                    }
                }
            }),
            MockHttpResponse({
                'data': {
                    'queryTrace': {
                        'spans': [
                            {
                                'traceId': 'trace-1',
                                'segmentId': 'segment-1',
                                'spanId': 0,
                                'parentSpanId': -1,
                                'serviceCode': 'gateway-service',
                                'serviceInstanceName': 'gateway-prod-01',
                                'startTime': 1711674900000,
                                'endTime': 1711674900212,
                                'endpointName': 'GET /api/orders/{id}',
                                'type': 'Entry',
                                'peer': '',
                                'component': 'SpringMVC',
                                'isError': False,
                                'layer': 'HTTP',
                                'tags': [{'key': 'http.status_code', 'value': '200'}],
                                'logs': [],
                            }
                        ]
                    }
                }
            }),
            MockHttpResponse({
                'data': {
                    'getServiceInstances': [
                        {'id': 'gateway-prod-01', 'name': 'gateway-prod-01'},
                    ]
                }
            }),
            MockHttpResponse({
                'data': {
                    'queryTrace': {
                        'spans': [
                            {
                                'traceId': 'trace-1',
                                'segmentId': 'segment-1',
                                'spanId': 0,
                                'parentSpanId': -1,
                                'serviceCode': 'gateway-service',
                                'serviceInstanceName': 'gateway-prod-01',
                                'startTime': 1711674900000,
                                'endTime': 1711674900212,
                                'endpointName': 'GET /api/orders/{id}',
                                'type': 'Entry',
                                'peer': '',
                                'component': 'SpringMVC',
                                'isError': False,
                                'layer': 'HTTP',
                                'tags': [{'key': 'http.status_code', 'value': '200'}],
                                'logs': [],
                            }
                        ]
                    }
                }
            }),
        ]

        response = self.client.get('/api/observability/tracing/traces/trace-1/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['trace']['trace_id'], 'trace-1')
        self.assertEqual(payload['trace']['span_count'], 1)
        self.assertEqual(payload['trace']['duration_ms'], 212)
        self.assertEqual(payload['trace'].get('summary', ''), '')
        self.assertIn('gateway-service', payload['trace']['services'])

    @patch('ops.log_views.http_requests.request')
    def test_sls_catalog_lists_logstores(self, mock_request):
        mock_request.return_value = MockHttpResponse({'logstores': ['frontend', 'backend']})

        response = self.client.post('/api/log/providers/sls/catalog/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['kind'], 'logstores')
        self.assertEqual(payload['items'][0]['name'], 'frontend')
        self.assertEqual(payload['items'][1]['name'], 'backend')

    @patch('ops.log_views.http_requests.request')
    def test_live_sls_query_normalizes_array_response_and_headers(self, mock_request):
        mock_request.return_value = MockHttpResponse(
            [
                {
                    '__time__': 1770000000,
                    'level': 'ERROR',
                    'service': 'order-service',
                    'trace_id': '0123456789abcdef',
                    'message': 'order request timeout',
                }
            ],
            headers={'x-log-count': '9', 'x-log-progress': 'Complete'},
        )

        response = self.client.post(
            '/api/log/query/',
            {
                'provider': 'sls',
                'query': 'timeout OR error',
                'source': 'app-logstore',
                'limit': 100,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['total'], 9)
        self.assertEqual(payload['progress'], 'Complete')
        self.assertEqual(payload['logs'][0]['level'], 'error')
        self.assertEqual(payload['logs'][0]['attributes']['trace_id'], '0123456789abcdef')
        self.assertEqual(mock_request.call_args.args[0], 'GET')
        request_url = mock_request.call_args.args[1]
        self.assertTrue(request_url.startswith('https://demo-project.cn-hangzhou.log.aliyuncs.com/logstores/app-logstore?'))
        self.assertIn('offset=0', request_url)
        self.assertIn('line=100', request_url)
        self.assertIn('query=timeout%20OR%20error', request_url)
        self.assertTrue(mock_request.call_args.kwargs['headers']['Authorization'].startswith('LOG test-ak:'))

    def test_demo_sls_query_returns_fake_logs(self):
        response = self.client.post(
            '/api/log/datasources/',
            {
                'name': 'SLS Demo CN',
                'provider': 'sls',
                'config': {
                    'endpoint': 'cn-hangzhou.log.aliyuncs.com',
                    'project': 'demo-project',
                    'logstore': 'demo-hz-logstore',
                    'topic': 'order',
                    'access_key_id': 'demo-ak-id',
                    'access_key_secret': 'demo-ak-secret',
                    'demo_mode': True,
                    'demo_logstores': ['demo-hz-logstore', 'demo-hz-audit'],
                },
            },
            format='json',
        )
        datasource_id = response.json()['id']

        query_response = self.client.post(
            '/api/log/query/',
            {
                'datasource_id': datasource_id,
                'query': 'timeout',
                'source': 'demo-hz-logstore',
            },
            format='json',
        )

        self.assertEqual(query_response.status_code, 200)
        payload = query_response.json()
        self.assertEqual(payload['provider'], 'sls')
        self.assertGreaterEqual(payload['total'], 1)
        self.assertEqual(payload['progress'], 'Complete')
        self.assertIn('trace_id', payload['logs'][0]['attributes'])
        self.assertIn('timeout', payload['logs'][0]['message'])

    def test_demo_sls_query_honors_high_limit_when_matches_are_available(self):
        response = self.client.post(
            '/api/log/datasources/',
            {
                'name': 'SLS Demo Large',
                'provider': 'sls',
                'config': {
                    'endpoint': 'cn-shanghai.log.aliyuncs.com',
                    'project': 'demo-project',
                    'logstore': 'demo-sh-logstore',
                    'access_key_id': 'demo-ak-id',
                    'access_key_secret': 'demo-ak-secret',
                    'demo_mode': True,
                },
            },
            format='json',
        )

        query_response = self.client.post(
            '/api/log/query/',
            {
                'datasource_id': response.json()['id'],
                'query': '*',
                'source': 'demo-sh-logstore',
                'limit': 200,
            },
            format='json',
        )

        self.assertEqual(query_response.status_code, 200)
        payload = query_response.json()
        self.assertGreaterEqual(payload['total'], 200)
        self.assertEqual(len(payload['logs']), 200)

    def test_rum_overview_applies_platform_and_range_filters(self):
        response = self.client.get('/api/observability/rum/overview/?platform=mobile&range=7d')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['query'], {'platform': 'mobile', 'range': '7d'})
        self.assertEqual(len(payload['apps']), 1)
        self.assertTrue(all(item['platform'] == 'mobile' for item in payload['sessions']))
        self.assertTrue(all(item['platform'] == 'mobile' for item in payload['errors']))
        self.assertEqual(len(payload['trend']), 7)
        self.assertEqual({item['key'] for item in payload['vitals']}, {'lcp', 'inp', 'cls', 'fcp'})
        self.assertTrue(payload['sessions'][0]['trace_id'])


class ContainerManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_superuser('container-admin', 'container@example.com', 'Admin@123456')
        self.client.force_authenticate(user=self.user)
        cache.clear()

    def test_k8s_api_proxy_preserves_bound_method_owner_for_stream(self):
        class FakeApi:
            def __init__(self):
                self.api_client = object()
                self.kwargs = None

            def connect_get_namespaced_pod_exec(self, **kwargs):
                self.kwargs = kwargs
                return 'connected'

        fake_api = FakeApi()
        proxy = _K8sApiProxy(fake_api)
        wrapped = proxy.connect_get_namespaced_pod_exec

        self.assertIs(wrapped.__self__, fake_api)
        self.assertIs(wrapped.__self__.api_client, fake_api.api_client)
        self.assertEqual(wrapped(name='pod-a'), 'connected')
        self.assertEqual(fake_api.kwargs['_request_timeout'], (1.5, 3))

    def test_prepare_kubeconfig_overrides_active_cluster_server(self):
        cluster = K8sCluster.objects.create(
            name='prod-k8s',
            api_server='https://k8s.example.com:6443',
            kubeconfig=(
                'apiVersion: v1\n'
                'kind: Config\n'
                'current-context: prod\n'
                'contexts:\n'
                '  - name: prod\n'
                '    context:\n'
                '      cluster: prod-cluster\n'
                '      user: prod-user\n'
                'clusters:\n'
                '  - name: prod-cluster\n'
                '    cluster:\n'
                '      server: https://120.26.213.176:6443\n'
            ),
        )

        rendered = _prepare_kubeconfig(cluster)

        self.assertIn('server: https://k8s.example.com:6443', rendered)
        self.assertNotIn('server: https://120.26.213.176:6443', rendered)

    @patch('ops.k8s_views._get_k8s_client')
    def test_k8s_connection_reports_certificate_hint_on_ssl_error(self, mock_get_client):
        cluster = K8sCluster.objects.create(
            name='broken-k8s',
            api_server='https://120.26.213.176:6443',
            kubeconfig='apiVersion: v1\nkind: Config\ncurrent-context: broken\nclusters: []\ncontexts: []\n',
        )
        mock_get_client.side_effect = ssl.SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed')

        response = self.client.post(f'/api/k8s/clusters/{cluster.id}/test_connection/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn('证书校验失败', payload['message'])
        self.assertEqual(K8sCluster.objects.get(id=cluster.id).status, 'error')

    def test_k8s_summary_returns_demo_cluster_metrics(self):
        cluster = K8sCluster.objects.create(
            name='demo-cluster',
            kubeconfig='demo',
            status='connected',
        )

        response = self.client.get(f'/api/k8s/clusters/{cluster.id}/summary/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['cluster_name'], 'demo-cluster')
        self.assertEqual(payload['nodes_total'], 4)
        self.assertEqual(payload['nodes_ready'], 4)
        self.assertEqual(payload['pods_total'], 15)
        self.assertEqual(payload['pods_abnormal'], 2)
        self.assertEqual(payload['total_restarts'], 8)
        self.assertEqual(payload['workloads_total'], 16)
        self.assertGreaterEqual(len(payload['alerts']), 1)

    @patch('ops.k8s_views._build_demo_summary')
    def test_k8s_summary_uses_short_cache(self, mock_build_demo_summary):
        cluster = K8sCluster.objects.create(
            name='demo-cluster-cache',
            kubeconfig='demo',
            status='connected',
        )
        mock_build_demo_summary.return_value = {
            'cluster_name': cluster.name,
            'status': 'connected',
            'nodes_total': 4,
            'nodes_ready': 4,
            'pods_total': 15,
            'pods_abnormal': 0,
            'pods_restarting': 0,
            'total_restarts': 0,
            'services_total': 0,
            'ingresses_total': 0,
            'workloads_total': 0,
            'workloads_degraded': 0,
            'pvcs_total': 0,
            'pvcs_pending': 0,
            'configmaps_total': 0,
            'secrets_total': 0,
            'alerts': [],
        }

        first = self.client.get(f'/api/k8s/clusters/{cluster.id}/summary/')
        second = self.client.get(f'/api/k8s/clusters/{cluster.id}/summary/')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(mock_build_demo_summary.call_count, 1)

    @patch('ops.k8s_views._get_k8s_client')
    def test_k8s_summary_marks_payload_degraded_when_live_queries_timeout(self, mock_get_client):
        cluster = K8sCluster.objects.create(
            name='timeout-k8s',
            kubeconfig='apiVersion: v1\nkind: Config\nclusters: []\ncontexts: []\n',
            status='connected',
        )

        class FailingCoreV1Api:
            def list_namespace(self):
                raise TimeoutError('connect timed out')

            def list_node(self):
                raise TimeoutError('connect timed out')

            def list_pod_for_all_namespaces(self):
                raise TimeoutError('connect timed out')

            def list_service_for_all_namespaces(self):
                raise TimeoutError('connect timed out')

            def list_persistent_volume_claim_for_all_namespaces(self):
                raise TimeoutError('connect timed out')

            def list_config_map_for_all_namespaces(self):
                raise TimeoutError('connect timed out')

            def list_secret_for_all_namespaces(self):
                raise TimeoutError('connect timed out')

        class FailingAppsV1Api:
            def list_deployment_for_all_namespaces(self):
                raise TimeoutError('connect timed out')

            def list_stateful_set_for_all_namespaces(self):
                raise TimeoutError('connect timed out')

            def list_daemon_set_for_all_namespaces(self):
                raise TimeoutError('connect timed out')

        class FailingBatchV1Api:
            def list_job_for_all_namespaces(self):
                raise TimeoutError('connect timed out')

            def list_cron_job_for_all_namespaces(self):
                raise TimeoutError('connect timed out')

        class FailingNetworkingV1Api:
            def list_ingress_for_all_namespaces(self):
                raise TimeoutError('connect timed out')

        mock_get_client.return_value = MagicMock(
            CoreV1Api=MagicMock(return_value=FailingCoreV1Api()),
            AppsV1Api=MagicMock(return_value=FailingAppsV1Api()),
            BatchV1Api=MagicMock(return_value=FailingBatchV1Api()),
            NetworkingV1Api=MagicMock(return_value=FailingNetworkingV1Api()),
        )

        response = self.client.get(f'/api/k8s/clusters/{cluster.id}/summary/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['degraded'])
        self.assertIn('pods', payload['unavailable_resources'])
        self.assertTrue(any(item['level'] == 'warning' for item in payload['alerts']))
        self.assertFalse(any(item['level'] == 'success' for item in payload['alerts']))

    @patch('ops.k8s_views._get_k8s_client')
    def test_k8s_pods_returns_stale_cache_when_cluster_times_out(self, mock_get_client):
        cluster = K8sCluster.objects.create(
            name='stale-cache-k8s',
            kubeconfig='apiVersion: v1\nkind: Config\nclusters: []\ncontexts: []\n',
            status='connected',
        )
        stale_items = [{'name': 'cached-pod', 'namespace': 'default', 'status': 'Running', 'node': 'node-01', 'ip': '10.0.0.5', 'containers': [], 'restarts': 0, 'created': ''}]
        cache.set(_resource_stale_cache_key(cluster.id, 'pods', 'default'), stale_items, 300)
        mock_get_client.side_effect = TimeoutError('connect timed out')

        response = self.client.get(f'/api/k8s/clusters/{cluster.id}/pods/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), stale_items)

    @patch('ops.k8s_views._get_k8s_client')
    def test_k8s_summary_returns_stale_snapshot_when_build_fails(self, mock_get_client):
        cluster = K8sCluster.objects.create(
            name='summary-stale-k8s',
            kubeconfig='apiVersion: v1\nkind: Config\nclusters: []\ncontexts: []\n',
            status='connected',
        )
        cached_summary = {
            'cluster_name': cluster.name,
            'status': 'connected',
            'nodes_total': 3,
            'nodes_ready': 3,
            'pods_total': 10,
            'pods_abnormal': 0,
            'pods_restarting': 0,
            'total_restarts': 0,
            'services_total': 4,
            'ingresses_total': 1,
            'workloads_total': 6,
            'workloads_degraded': 0,
            'pvcs_total': 2,
            'pvcs_pending': 0,
            'configmaps_total': 5,
            'secrets_total': 4,
            'alerts': [{'level': 'success', 'message': 'cached'}],
        }
        cache.set(_summary_stale_cache_key(cluster.id), cached_summary, 300)
        mock_get_client.side_effect = RuntimeError('cluster unavailable')

        response = self.client.get(f'/api/k8s/clusters/{cluster.id}/summary/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['degraded'])
        self.assertEqual(payload['pods_total'], 10)
        self.assertIn('cached snapshot', payload['alerts'][0]['message'])

    @patch('ops.k8s_views._build_live_summary')
    def test_k8s_summary_does_not_cache_unreliable_zero_snapshot(self, mock_build_live_summary):
        cluster = K8sCluster.objects.create(
            name='summary-zero-degraded-k8s',
            kubeconfig='apiVersion: v1\nkind: Config\nclusters: []\ncontexts: []\n',
            status='connected',
        )
        cached_summary = {
            'cluster_name': cluster.name,
            'status': 'connected',
            'nodes_total': 2,
            'nodes_ready': 2,
            'pods_total': 8,
            'pods_abnormal': 1,
            'pods_restarting': 1,
            'total_restarts': 3,
            'services_total': 4,
            'ingresses_total': 1,
            'workloads_total': 5,
            'workloads_degraded': 0,
            'pvcs_total': 2,
            'pvcs_pending': 0,
            'configmaps_total': 5,
            'secrets_total': 4,
            'alerts': [{'level': 'success', 'message': 'cached'}],
        }
        mock_build_live_summary.return_value = {
            'cluster_name': cluster.name,
            'status': 'connected',
            'namespaces_total': 0,
            'nodes_total': 0,
            'nodes_ready': 0,
            'pods_total': 0,
            'pods_abnormal': 0,
            'pods_restarting': 0,
            'total_restarts': 0,
            'services_total': 0,
            'ingresses_total': 0,
            'workloads_total': 0,
            'workloads_degraded': 0,
            'pvcs_total': 0,
            'pvcs_pending': 0,
            'configmaps_total': 0,
            'secrets_total': 0,
            'degraded': True,
            'unavailable_resources': ['pods', 'deployments'],
            'alerts': [{'level': 'warning', 'message': 'partial collection failed'}],
        }
        cache.set(_summary_stale_cache_key(cluster.id), cached_summary, 300)

        response = self.client.get(f'/api/k8s/clusters/{cluster.id}/summary/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['degraded'])
        self.assertEqual(payload['pods_total'], 8)
        self.assertEqual(payload['workloads_total'], 5)
        self.assertIn('cached snapshot', payload['alerts'][0]['message'])

    @patch('ops.k8s_views._get_k8s_client')
    def test_k8s_pod_logs_degrade_to_empty_payload_on_timeout(self, mock_get_client):
        cluster = K8sCluster.objects.create(
            name='pod-logs-timeout-k8s',
            kubeconfig='apiVersion: v1\nkind: Config\nclusters: []\ncontexts: []\n',
            status='connected',
        )
        mock_get_client.side_effect = TimeoutError('connect timed out')

        response = self.client.get(
            f'/api/k8s/clusters/{cluster.id}/pod_logs/',
            {'pod_name': 'api-server-1', 'namespace': 'default'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['degraded'])
        self.assertEqual(payload['logs'], '')

    @patch('ops.docker_views._get_ssh_client_from_docker_host')
    @patch('ops.docker_views._ssh_exec')
    def test_list_containers_uses_json_line_format_for_broader_docker_compatibility(self, mock_ssh_exec, mock_get_client):
        host = DockerHost.objects.create(name='docker-host-01', ip_address='10.0.0.10')
        client = MagicMock()
        mock_get_client.return_value = client
        mock_ssh_exec.return_value = (0, '{"ID":"abc123","Names":"web","Image":"nginx:1.25","State":"running","Status":"Up 2h"}\n', '')

        response = self.client.get('/api/docker/containers/', {'host_id': host.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['name'], 'web')
        issued_command = mock_ssh_exec.call_args.args[1]
        self.assertIn("--format '{{json .}}'", issued_command)
        client.close.assert_called_once()

    @patch('ops.docker_views._get_ssh_client_from_docker_host')
    @patch('ops.docker_views._ssh_exec')
    def test_container_logs_quote_identifier_and_clamp_tail(self, mock_ssh_exec, mock_get_client):
        host = DockerHost.objects.create(name='docker-host-02', ip_address='10.0.0.11')
        client = MagicMock()
        mock_get_client.return_value = client
        mock_ssh_exec.return_value = (0, 'demo logs', '')
        container_id = 'demo; echo hacked'

        response = self.client.get(
            f"/api/docker/containers/{quote(container_id, safe='')}/logs/",
            {'host_id': host.id, 'tail': 99999},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['logs'], 'demo logs')
        issued_command = mock_ssh_exec.call_args.args[1]
        self.assertIn('docker logs --tail=2000', issued_command)
        self.assertIn("'demo; echo hacked'", issued_command)
        client.close.assert_called_once()

    def test_k8s_pod_exec_returns_demo_output(self):
        cluster = K8sCluster.objects.create(name='demo-cluster-exec', kubeconfig='demo', status='connected')

        response = self.client.post(
            f'/api/k8s/clusters/{cluster.id}/pod_exec/',
            {
                'pod_name': 'api-server-5f8b7c6d4-r9p2w',
                'namespace': 'production',
                'command': 'whoami && pwd',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIn('whoami && pwd', payload['output'])

    def test_k8s_kubectl_console_runs_only_against_selected_demo_cluster(self):
        cluster = K8sCluster.objects.create(name='demo-cluster-console', kubeconfig='demo', status='connected')

        response = self.client.post(
            f'/api/k8s/clusters/{cluster.id}/kubectl/',
            {'command': 'kubectl get pods -A'},
            format='json',
        )
        blocked_response = self.client.post(
            f'/api/k8s/clusters/{cluster.id}/kubectl/',
            {'command': 'kubectl get pods --kubeconfig=/tmp/other.yaml'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertIn('api-server', response.json()['stdout'])
        self.assertEqual(blocked_response.status_code, 400)
        self.assertIn('不允许使用 --kubeconfig', blocked_response.json()['message'])

    def test_k8s_kubectl_console_requires_role_even_for_legacy_demo_username(self):
        demo_user = get_user_model().objects.create_user(username='demo')
        demo_cluster = K8sCluster.objects.create(name='demo-cluster-demo-user', kubeconfig='demo', status='connected')
        live_cluster = K8sCluster.objects.create(
            name='live-cluster-demo-user',
            kubeconfig='apiVersion: v1\nkind: Config\nclusters: []\ncontexts: []\n',
            status='connected',
        )
        self.client.force_authenticate(user=demo_user)

        demo_response = self.client.post(
            f'/api/k8s/clusters/{demo_cluster.id}/kubectl/',
            {'command': 'kubectl get nodes'},
            format='json',
        )
        live_response = self.client.post(
            f'/api/k8s/clusters/{live_cluster.id}/kubectl/',
            {'command': 'kubectl get nodes'},
            format='json',
        )

        self.assertEqual(demo_response.status_code, 403)
        self.assertEqual(live_response.status_code, 403)

    def test_k8s_pods_include_openlens_list_metadata(self):
        cluster = K8sCluster.objects.create(name='demo-cluster-pod-list', kubeconfig='demo', status='connected')

        response = self.client.get(f'/api/k8s/clusters/{cluster.id}/pods/', {'namespace': 'production'})

        self.assertEqual(response.status_code, 200)
        pod = response.json()[0]
        self.assertIn('controlled_by', pod)
        self.assertIn('qos', pod)

    def test_k8s_scale_workload_updates_demo_state(self):
        cluster = K8sCluster.objects.create(name='demo-cluster-scale', kubeconfig='demo', status='connected')

        scale_response = self.client.post(
            f'/api/k8s/clusters/{cluster.id}/scale_workload/',
            {
                'workload_type': 'deployment',
                'name': 'nginx-deployment',
                'namespace': 'production',
                'replicas': 4,
            },
            format='json',
        )
        list_response = self.client.get(f'/api/k8s/clusters/{cluster.id}/deployments/', {'namespace': 'production'})

        self.assertEqual(scale_response.status_code, 200)
        self.assertEqual(list_response.status_code, 200)
        deployment = next(item for item in list_response.json() if item['name'] == 'nginx-deployment')
        self.assertEqual(deployment['replicas'], 4)

    def test_k8s_config_resource_update_and_rollback_preview_use_demo_snapshot(self):
        cluster = K8sCluster.objects.create(name='demo-cluster-config', kubeconfig='demo', status='connected')

        detail_response = self.client.get(
            f'/api/k8s/clusters/{cluster.id}/config_resource_detail/',
            {'type': 'configmap', 'name': 'nginx-config', 'namespace': 'production'},
        )
        update_response = self.client.post(
            f'/api/k8s/clusters/{cluster.id}/config_resource_update/',
            {
                'type': 'configmap',
                'name': 'nginx-config',
                'namespace': 'production',
                'content': 'worker_processes: auto\nkeepalive_timeout: 65\n',
            },
            format='json',
        )
        rollback_preview = self.client.get(
            f'/api/k8s/clusters/{cluster.id}/config_resource_rollback_preview/',
            {'type': 'configmap', 'name': 'nginx-config', 'namespace': 'production'},
        )

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(rollback_preview.status_code, 200)
        self.assertTrue(update_response.json()['resource']['rollback_available'])
        self.assertIn('worker_processes', update_response.json()['resource']['text'])
        self.assertIn('rollback', rollback_preview.json()['diff'])
        self.assertEqual(K8sConfigRevision.objects.filter(cluster=cluster).count(), 1)

    def test_k8s_config_resource_revisions_list_preview_and_targeted_rollback(self):
        cluster = K8sCluster.objects.create(name='demo-cluster-revisions', kubeconfig='demo', status='connected')

        first_update = self.client.post(
            f'/api/k8s/clusters/{cluster.id}/config_resource_update/',
            {
                'type': 'configmap',
                'name': 'nginx-config',
                'namespace': 'production',
                'content': 'worker_processes: auto\nkeepalive_timeout: 65\n',
            },
            format='json',
        )
        second_update = self.client.post(
            f'/api/k8s/clusters/{cluster.id}/config_resource_update/',
            {
                'type': 'configmap',
                'name': 'nginx-config',
                'namespace': 'production',
                'content': 'worker_processes: 4\nkeepalive_timeout: 75\n',
            },
            format='json',
        )
        revisions_response = self.client.get(
            f'/api/k8s/clusters/{cluster.id}/config_resource_revisions/',
            {'type': 'configmap', 'name': 'nginx-config', 'namespace': 'production'},
        )

        self.assertEqual(first_update.status_code, 200)
        self.assertEqual(second_update.status_code, 200)
        self.assertEqual(revisions_response.status_code, 200)
        items = revisions_response.json()['items']
        self.assertGreaterEqual(len(items), 2)
        target_revision = items[-1]
        self.assertEqual(target_revision['action'], 'update')

        preview_response = self.client.get(
            f'/api/k8s/clusters/{cluster.id}/config_resource_revision_preview/',
            {
                'type': 'configmap',
                'name': 'nginx-config',
                'namespace': 'production',
                'revision_id': target_revision['id'],
            },
        )
        rollback_response = self.client.post(
            f'/api/k8s/clusters/{cluster.id}/config_resource_rollback_to_revision/',
            {
                'type': 'configmap',
                'name': 'nginx-config',
                'namespace': 'production',
                'revision_id': target_revision['id'],
            },
            format='json',
        )
        detail_response = self.client.get(
            f'/api/k8s/clusters/{cluster.id}/config_resource_detail/',
            {'type': 'configmap', 'name': 'nginx-config', 'namespace': 'production'},
        )

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(rollback_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn('revision-', preview_response.json()['diff'])
        self.assertIn('key1', detail_response.json()['text'])
        self.assertIn('key3', detail_response.json()['text'])
        self.assertGreaterEqual(K8sConfigRevision.objects.filter(cluster=cluster).count(), 3)

    @patch('ops.docker_views._get_ssh_client_from_docker_host')
    @patch('ops.docker_views._ssh_exec')
    def test_remove_images_quotes_each_identifier(self, mock_ssh_exec, mock_get_client):
        host = DockerHost.objects.create(name='docker-host-03', ip_address='10.0.0.12')
        client = MagicMock()
        mock_get_client.return_value = client
        mock_ssh_exec.return_value = (0, 'deleted', '')

        response = self.client.delete(
            '/api/docker/images/remove/',
            {'host_id': host.id, 'image_ids': ['sha256:abc', 'bad; echo hacked']},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        issued_command = mock_ssh_exec.call_args.args[1]
        self.assertIn("docker rmi", issued_command)
        self.assertIn("'bad; echo hacked'", issued_command)
        client.close.assert_called_once()

    @patch('ops.docker_views._get_ssh_client_from_docker_host')
    @patch('ops.docker_views._ssh_exec')
    def test_prune_dangling_images_uses_docker_image_prune(self, mock_ssh_exec, mock_get_client):
        host = DockerHost.objects.create(name='docker-host-04', ip_address='10.0.0.13')
        client = MagicMock()
        mock_get_client.return_value = client
        mock_ssh_exec.return_value = (0, 'Total reclaimed space: 0B', '')

        response = self.client.post('/api/docker/images/prune/', {'host_id': host.id}, format='json')

        self.assertEqual(response.status_code, 200)
        issued_command = mock_ssh_exec.call_args.args[1]
        self.assertEqual(issued_command, 'docker image prune -f 2>&1')
        client.close.assert_called_once()

    @patch('ops.docker_views._get_ssh_client_from_docker_host')
    def test_demo_docker_host_returns_cached_container_and_image_inventory(self, mock_get_client):
        host = DockerHost.objects.create(name='app-release-test', ip_address='192.168.1.120', docker_api_version='24.0')

        container_response = self.client.get('/api/docker/containers/', {'host_id': host.id})
        image_response = self.client.get('/api/docker/images/', {'host_id': host.id})

        self.assertEqual(container_response.status_code, 200)
        self.assertEqual(image_response.status_code, 200)
        self.assertTrue(any(item['name'] == 'order-center-batch-1' for item in container_response.json()))
        self.assertTrue(any(item['repository'] == 'registry.demo.local/order-center' for item in image_response.json()))
        mock_get_client.assert_not_called()

    def test_demo_docker_container_action_logs_and_inspect_update_cached_state(self):
        host = DockerHost.objects.create(name='gateway-prod', ip_address='192.168.1.121', docker_api_version='24.0')

        container_response = self.client.get('/api/docker/containers/', {'host_id': host.id})
        self.assertEqual(container_response.status_code, 200)
        target = next(item for item in container_response.json() if item['name'] == 'member-center-failed')

        stop_response = self.client.post(
            f"/api/docker/containers/{quote(target['id'], safe='')}/action/",
            {'host_id': host.id, 'action': 'start'},
            format='json',
        )
        self.assertEqual(stop_response.status_code, 200)

        updated_list = self.client.get('/api/docker/containers/', {'host_id': host.id}).json()
        updated = next(item for item in updated_list if item['id'] == target['id'])
        self.assertEqual(updated['state'], 'running')

        logs_response = self.client.get(
            f"/api/docker/containers/{quote(target['id'], safe='')}/logs/",
            {'host_id': host.id, 'tail': 50},
        )
        inspect_response = self.client.get(
            f"/api/docker/containers/{quote(target['id'], safe='')}/inspect/",
            {'host_id': host.id},
        )

        self.assertEqual(logs_response.status_code, 200)
        self.assertEqual(inspect_response.status_code, 200)
        self.assertIn('member-center-failed', logs_response.json()['logs'])
        self.assertEqual(inspect_response.json()['State']['Status'], 'running')

    def test_demo_docker_image_remove_and_prune_update_cached_state(self):
        host = DockerHost.objects.create(name='member-prod', ip_address='192.168.1.122', docker_api_version='24.0')

        initial_images = self.client.get('/api/docker/images/', {'host_id': host.id}).json()
        dangling = next(item for item in initial_images if item['repository'] == '<none>')
        in_use = next(item for item in initial_images if item['repository'] == 'redis')

        remove_response = self.client.delete(
            '/api/docker/images/remove/',
            {'host_id': host.id, 'image_ids': [dangling['id'], in_use['id']]},
            format='json',
        )
        self.assertEqual(remove_response.status_code, 200)
        self.assertIn('跳过 1', remove_response.json()['message'])

        after_remove = self.client.get('/api/docker/images/', {'host_id': host.id}).json()
        self.assertFalse(any(item['id'] == dangling['id'] for item in after_remove))
        self.assertTrue(any(item['id'] == in_use['id'] for item in after_remove))

        prune_response = self.client.post('/api/docker/images/prune/', {'host_id': host.id}, format='json')
        self.assertEqual(prune_response.status_code, 200)
        after_prune = self.client.get('/api/docker/images/', {'host_id': host.id}).json()
        self.assertFalse(any(item['repository'] == '<none>' or item['tag'] == '<none>' for item in after_prune))


class MiddlewareViewsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = get_user_model().objects.create_superuser('middleware-admin', 'middleware@example.com', 'Admin@123456')
        self.client.force_authenticate(user=self.user)

    def test_middleware_overview_returns_all_sections(self):
        response = self.client.get('/api/middleware/overview/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('overview', payload)
        self.assertIn('redis', payload)
        self.assertIn('rocketmq', payload)
        self.assertIn('elasticsearch', payload)
        self.assertTrue(any(item['cluster'] == 'order-cache' for item in payload['redis']['instances']))
        self.assertTrue(any(item['group'] == 'GID_AUDIT_ETL' for item in payload['rocketmq']['consumer_groups']))
        self.assertTrue(any(item['health'] == 'yellow' for item in payload['elasticsearch']['clusters']))

    def test_redis_promote_action_swaps_master_role(self):
        initial = self.client.get('/api/middleware/overview/').json()
        replica = next(item for item in initial['redis']['instances'] if item['id'] == 'redis-order-replica-01')

        response = self.client.post(
            '/api/middleware/action/',
            {'module': 'redis', 'target_id': replica['id'], 'action': 'promote'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        updated_instances = response.json()['data']['redis']['instances']
        promoted = next(item for item in updated_instances if item['id'] == 'redis-order-replica-01')
        previous_master = next(item for item in updated_instances if item['id'] == 'redis-order-master')
        self.assertEqual(promoted['role'], 'master')
        self.assertEqual(promoted['replication_delay_ms'], 0)
        self.assertEqual(previous_master['role'], 'replica')
        self.assertEqual(previous_master['status'], 'warning')

    def test_elasticsearch_reroute_clears_yellow_cluster(self):
        response = self.client.post(
            '/api/middleware/action/',
            {'module': 'elasticsearch', 'target_id': 'es-observe-logs', 'action': 'reroute'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        updated_clusters = response.json()['data']['elasticsearch']['clusters']
        updated_cluster = next(item for item in updated_clusters if item['id'] == 'es-observe-logs')
        self.assertEqual(updated_cluster['health'], 'green')
        self.assertEqual(updated_cluster['unassigned_shards'], 0)

    def test_create_redis_cluster_and_instance_updates_demo_state(self):
        create_cluster = self.client.post(
            '/api/middleware/action/',
            {
                'module': 'redis',
                'action': 'create_cluster',
                'payload': {
                    'name': 'promo-cache',
                    'environment': 'test',
                    'mode': 'Sentinel',
                    'memory_total_gb': 24,
                },
            },
            format='json',
        )
        self.assertEqual(create_cluster.status_code, 200)
        self.assertTrue(any(item['name'] == 'promo-cache' for item in create_cluster.json()['data']['redis']['clusters']))

        create_instance = self.client.post(
            '/api/middleware/action/',
            {
                'module': 'redis',
                'action': 'create_instance',
                'payload': {
                    'cluster': 'promo-cache',
                    'name': 'redis-promo-master',
                    'environment': 'test',
                    'role': 'master',
                    'endpoint': '10.99.0.10:6379',
                },
            },
            format='json',
        )
        self.assertEqual(create_instance.status_code, 200)
        self.assertTrue(any(item['name'] == 'redis-promo-master' for item in create_instance.json()['data']['redis']['instances']))

    def test_create_elasticsearch_node_updates_cluster_size(self):
        response = self.client.post(
            '/api/middleware/action/',
            {
                'module': 'elasticsearch',
                'action': 'create_instance',
                'payload': {
                    'cluster': 'search-prod',
                    'name': 'es-search-07',
                    'endpoint': '10.23.0.17:9200',
                    'role': 'data_hot,ingest',
                },
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']['elasticsearch']
        self.assertTrue(any(item['name'] == 'es-search-07' for item in data['nodes']))
        updated_cluster = next(item for item in data['clusters'] if item['name'] == 'search-prod')
        self.assertEqual(updated_cluster['nodes'], 3)

    def test_update_rocketmq_cluster_renames_related_records(self):
        response = self.client.post(
            '/api/middleware/action/',
            {
                'module': 'rocketmq',
                'target_id': 'rmq-cls-audit',
                'action': 'update_cluster',
                'payload': {
                    'name': 'audit-mq-v2',
                    'environment': 'prod',
                    'status': 'healthy',
                    'nameserver_count': 3,
                },
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']['rocketmq']
        self.assertTrue(any(item['name'] == 'audit-mq-v2' for item in data['clusters']))
        self.assertTrue(any(item['cluster'] == 'audit-mq-v2' for item in data['brokers']))

    def test_delete_redis_cluster_removes_instances(self):
        response = self.client.post(
            '/api/middleware/action/',
            {'module': 'redis', 'target_id': 'redis-cls-member', 'action': 'delete_cluster'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']['redis']
        self.assertFalse(any(item['id'] == 'redis-cls-member' for item in data['clusters']))
        self.assertFalse(any(item['cluster'] == 'member-session' for item in data['instances']))

    def test_import_rocketmq_instance_template_creates_demo_broker(self):
        response = self.client.post(
            '/api/middleware/action/',
            {
                'module': 'rocketmq',
                'action': 'import_template',
                'payload': {
                    'scope': 'instance',
                    'template_key': 'slave',
                },
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        brokers = response.json()['data']['rocketmq']['brokers']
        self.assertTrue(any(item['name'].startswith('broker-template-slave') for item in brokers))


class AlertViewSetFilterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_superuser('alert-admin', 'alert@example.com', 'Admin@123456')
        self.client.force_authenticate(user=self.user)
        self.host = Host.objects.create(hostname='alert-host-01', ip_address='10.0.1.10', environment='prod', status='warning')
        Alert.objects.create(title='Critical alert', level='critical', source='monitor', message='critical issue', is_acknowledged=False, host=self.host)
        Alert.objects.create(title='Warning alert', level='warning', source='monitor', message='warning issue', is_acknowledged=True, host=self.host)

    def test_alert_list_supports_level_and_ack_filters(self):
        response = self.client.get('/api/alerts/', {'level': 'critical', 'is_acknowledged': False})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        results = payload['results'] if isinstance(payload, dict) and 'results' in payload else payload
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['level'], 'critical')
        self.assertFalse(results[0]['is_acknowledged'])


class AlertWebhookIngestTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.integration = AlertIntegration.objects.create(name='Prometheus', provider='prometheus', default_labels={'environment': 'prod'})

    def test_prometheus_webhook_creates_normalized_alert(self):
        response = self.client.post(
            f'/api/alerts/webhooks/prometheus/{self.integration.token}/',
            {
                'status': 'firing',
                'groupKey': 'service=order',
                'commonLabels': {'service': 'order-center'},
                'alerts': [{
                    'status': 'firing',
                    'fingerprint': 'fp-001',
                    'labels': {'alertname': 'HighErrorRate', 'severity': 'critical', 'instance': '10.0.1.10:9100'},
                    'annotations': {'summary': 'Order error rate high', 'description': '5xx ratio above threshold'},
                    'startsAt': '2026-05-04T10:00:00+08:00',
                }],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 202)
        alert = Alert.objects.get()
        self.assertEqual(alert.source_type, 'prometheus')
        self.assertEqual(alert.level, 'critical')
        self.assertEqual(alert.service, 'order-center')
        self.assertEqual(alert.labels['environment'], 'prod')
        self.assertEqual(alert.environment, 'prod')
        self.assertEqual(alert.status, Alert.STATUS_ACTIVE)
        self.assertTrue(AlertAction.objects.filter(alert=alert, action=AlertAction.ACTION_WEBHOOK).exists())

    def test_prometheus_webhook_prefers_app_then_job_name_then_service_for_service_field(self):
        response = self.client.post(
            f'/api/alerts/webhooks/prometheus/{self.integration.token}/',
            {
                'status': 'firing',
                'alerts': [{
                    'status': 'firing',
                    'fingerprint': 'fp-002',
                    'labels': {
                        'alertname': 'KubeJobFailed',
                        'severity': 'warning',
                        'app': 'traffic-generator',
                        'job_name': 'traffic-generator-29633802',
                        'service': 'kube-prometheus-stack-kube-state-metrics',
                    },
                    'annotations': {'summary': 'Job failed to complete.'},
                    'startsAt': '2026-05-04T10:00:00+08:00',
                }],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 202)
        alert = Alert.objects.get(fingerprint__isnull=False)
        self.assertEqual(alert.service, 'traffic-generator')

    def test_prometheus_webhook_falls_back_to_job_name_before_service(self):
        response = self.client.post(
            f'/api/alerts/webhooks/prometheus/{self.integration.token}/',
            {
                'status': 'firing',
                'alerts': [{
                    'status': 'firing',
                    'fingerprint': 'fp-003',
                    'labels': {
                        'alertname': 'KubeJobFailed',
                        'severity': 'warning',
                        'job_name': 'traffic-generator-29633802',
                        'service': 'kube-prometheus-stack-kube-state-metrics',
                    },
                    'annotations': {'summary': 'Job failed to complete.'},
                    'startsAt': '2026-05-04T10:00:00+08:00',
                }],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 202)
        alert = Alert.objects.get(fingerprint__isnull=False)
        self.assertEqual(alert.service, 'traffic-generator-29633802')

    def test_invalid_webhook_token_is_rejected(self):
        response = self.client.post('/api/alerts/webhooks/prometheus/bad-token/', {'alerts': []}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_default_labels_fill_dimensions_without_overriding_payload(self):
        from ops.alerting import normalize_alert_payload

        self.integration.default_labels = {'environment': 'prod', 'namespace': 'default', 'service': 'default-service'}
        normalized = normalize_alert_payload('prometheus', {'alerts': [{'labels': {
            'alertname': 'ScopedAlert', 'env': 'test', 'namespace': 'checkout', 'service': 'order',
        }}]}, self.integration)[0]
        self.assertEqual(normalized['environment'], 'test')
        self.assertEqual(normalized['namespace'], 'checkout')
        self.assertEqual(normalized['service'], 'order')
        defaulted = normalize_alert_payload('prometheus', {'alerts': [{'labels': {'alertname': 'Defaulted'}}]}, self.integration)[0]
        self.assertEqual(defaulted['environment'], 'prod')
        self.assertEqual(defaulted['namespace'], 'default')
        self.assertEqual(defaulted['service'], 'default-service')

    def test_provider_webhook_requires_token(self):
        response = self.client.post('/api/alerts/webhooks/prometheus/', {'alerts': []}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_generic_webhook_requires_token(self):
        response = self.client.post(
            '/api/alerts/webhooks/generic/',
            {'title': 'Generic alert', 'level': 'warning', 'resource': 'demo-resource'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Alert.objects.filter(title='Generic alert').exists())

    def test_generic_webhook_accepts_enabled_integration_token(self):
        integration = AlertIntegration.objects.create(name='Generic', provider='generic')
        response = self.client.post(
            '/api/alerts/webhooks/generic/',
            {'title': 'Generic alert', 'level': 'warning'}, format='json',
            HTTP_X_ALERT_TOKEN=integration.token,
        )
        self.assertEqual(response.status_code, 202)
        self.assertTrue(Alert.objects.filter(title='Generic alert', source_type='generic').exists())


class AlertActionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_superuser('alert-operator', 'operator@example.com', 'Admin@123456')
        self.second_user = get_user_model().objects.create_superuser('backup-operator', 'backup@example.com', 'Admin@123456')
        self.client.force_authenticate(user=self.user)
        self.alert = Alert.objects.create(title='CPU high', level='warning', source='monitor', source_type='generic', message='cpu high')

    def test_claim_and_mute_alert(self):
        claim_response = self.client.post(f'/api/alerts/{self.alert.id}/claim/')
        self.assertEqual(claim_response.status_code, 200)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.claimed_by, 'alert-operator')
        self.assertEqual(self.alert.claim_records.count(), 1)

        mute_response = self.client.post(f'/api/alerts/{self.alert.id}/mute/', {'minutes': 30}, format='json')
        self.assertEqual(mute_response.status_code, 200)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, Alert.STATUS_MUTED)
        self.assertTrue(self.alert.is_suppressed)

    def test_multiple_users_can_claim_same_alert(self):
        first_claim_response = self.client.post(f'/api/alerts/{self.alert.id}/claim/')
        self.assertEqual(first_claim_response.status_code, 200)

        self.client.force_authenticate(user=self.second_user)
        second_claim_response = self.client.post(f'/api/alerts/{self.alert.id}/claim/')
        self.assertEqual(second_claim_response.status_code, 200)

        detail_response = self.client.get(f'/api/alerts/{self.alert.id}/')
        self.assertEqual(detail_response.status_code, 200)
        payload = detail_response.json()
        self.assertEqual(payload['claimant_count'], 2)
        self.assertCountEqual([item['claimant'] for item in payload['claimants']], ['alert-operator', 'backup-operator'])
        self.assertTrue(payload['current_user_claimed'])

        unclaim_response = self.client.post(f'/api/alerts/{self.alert.id}/unclaim/')
        self.assertEqual(unclaim_response.status_code, 200)

        self.client.force_authenticate(user=self.user)
        detail_after_unclaim = self.client.get(f'/api/alerts/{self.alert.id}/')
        self.assertEqual(detail_after_unclaim.status_code, 200)
        payload_after_unclaim = detail_after_unclaim.json()
        self.assertEqual(payload_after_unclaim['claimant_count'], 1)
        self.assertEqual(payload_after_unclaim['claimants'][0]['claimant'], 'alert-operator')

    def test_notification_rule_can_be_configured(self):
        channel = AlertNotificationChannel.objects.create(name='email', channel_type='email', config={'to': ['ops@example.com']})
        recipient = AlertRecipient.objects.create(name='Ops', email='ops@example.com')
        group = AlertRecipientGroup.objects.create(name='oncall')
        group.recipients.add(recipient)
        response = self.client.post(
            '/api/alert-notification-rules/',
            {
                'name': 'critical notify',
                'min_level': 'warning',
                'matchers': [{'key': 'source_type', 'op': '==', 'value': 'generic'}],
                'channel_ids': [channel.id],
                'recipient_group_ids': [group.id],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        rule = AlertNotificationRule.objects.get(name='critical notify')
        self.assertEqual(rule.channels.count(), 1)
        self.assertEqual(rule.recipient_groups.count(), 1)
