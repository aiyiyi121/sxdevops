from threading import Barrier, Lock
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase

from ops.k8s_views import _build_live_summary, _get_cluster_server_version


class K8sSummaryPerformanceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch('ops.k8s_views._get_k8s_client')
    def test_live_summary_bounds_concurrency_and_preserves_partial_results(self, mock_get_client):
        barrier = Barrier(4)
        lock = Lock()
        started = 0
        active = 0
        peak = 0

        def load_items():
            nonlocal started, active, peak
            with lock:
                started += 1
                position = started
                active += 1
                peak = max(peak, active)
            try:
                if position <= 4:
                    barrier.wait(timeout=3)
                return SimpleNamespace(items=[])
            finally:
                with lock:
                    active -= 1

        api = MagicMock()
        methods = (
            'list_namespace', 'list_node', 'list_pod_for_all_namespaces',
            'list_service_for_all_namespaces', 'list_ingress_for_all_namespaces',
            'list_persistent_volume_claim_for_all_namespaces', 'list_config_map_for_all_namespaces',
            'list_secret_for_all_namespaces', 'list_deployment_for_all_namespaces',
            'list_stateful_set_for_all_namespaces', 'list_daemon_set_for_all_namespaces',
            'list_job_for_all_namespaces', 'list_cron_job_for_all_namespaces',
        )
        for method in methods:
            getattr(api, method).side_effect = load_items
        api.list_ingress_for_all_namespaces.side_effect = TimeoutError('read timed out')
        api.list_secret_for_all_namespaces.side_effect = PermissionError('forbidden')
        api.list_namespace.side_effect = lambda: SimpleNamespace(items=[SimpleNamespace()])
        for name in ('CoreV1Api', 'AppsV1Api', 'BatchV1Api', 'NetworkingV1Api'):
            getattr(mock_get_client.return_value, name).return_value = api

        mock_get_client.return_value.VersionApi.return_value.get_code.return_value.git_version = 'v1.31.4'
        payload = _build_live_summary(SimpleNamespace(pk=1, kubeconfig='live', name='live-cluster', status='connected'))

        self.assertEqual(payload['server_version'], 'v1.31.4')
        self.assertEqual(peak, 4)
        self.assertEqual(started, 10)
        self.assertEqual(payload['namespaces_total'], 1)
        self.assertTrue(payload['degraded'])
        self.assertEqual(payload['unavailable_resources'], ['ingresses', 'secrets'])
        self.assertFalse(any(item['level'] == 'success' for item in payload['alerts']))
        for method in methods:
            getattr(api, method).assert_called_once_with()

    @patch('ops.k8s_views._get_k8s_client')
    def test_server_version_caches_each_cluster_and_closes_owned_client(self, get_client):
        get_code = get_client.return_value.VersionApi.return_value.get_code
        get_code.side_effect = [SimpleNamespace(git_version='v1.31.4'), SimpleNamespace(git_version='v1.30.8')]
        first = SimpleNamespace(pk=1, kubeconfig='live')
        second = SimpleNamespace(pk=2, kubeconfig='live')
        self.assertEqual(_get_cluster_server_version(first), 'v1.31.4')
        self.assertEqual(_get_cluster_server_version(first), 'v1.31.4')
        self.assertEqual(_get_cluster_server_version(second), 'v1.30.8')
        self.assertEqual(get_code.call_count, 2)
        self.assertEqual(get_client.return_value.ApiClient.return_value.close.call_count, 2)

    @patch('ops.k8s_views._get_k8s_client')
    def test_server_version_failure_is_cached_without_failing_live_summary(self, get_client):
        k8s = get_client.return_value
        k8s.VersionApi.return_value.get_code.side_effect = TimeoutError('read timed out')
        for name in ('CoreV1Api', 'AppsV1Api', 'BatchV1Api', 'NetworkingV1Api'):
            getattr(k8s, name).return_value = MagicMock()
        cluster = SimpleNamespace(pk=1, kubeconfig='live', name='live-cluster', status='connected')
        payload = _build_live_summary(cluster)
        self.assertEqual(payload['server_version'], '')
        self.assertNotIn('degraded', payload)
        self.assertEqual(_get_cluster_server_version(cluster), '')
        k8s.VersionApi.return_value.get_code.assert_called_once()
        k8s.ApiClient.return_value.close.assert_not_called()
