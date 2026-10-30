from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from kubernetes.client import V1ObjectMeta, V1Service, V1ServicePort, V1ServiceSpec
from rest_framework.test import APIClient

from .k8s_views import get_k8s_resource_snapshot
from .models import K8sCluster


class K8sServiceListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser('service-admin', password='Test@123456')
        cls.cluster = K8sCluster.objects.create(name='live-service-test', kubeconfig='live')

    def service(self, external_ips):
        return V1Service(
            metadata=V1ObjectMeta(name='api', namespace='production'),
            spec=V1ServiceSpec(
                type='ClusterIP', cluster_ip='10.96.0.20', external_ips=external_ips,
                ports=[V1ServicePort(port=80, protocol='TCP')],
            ),
        )

    @patch('ops.k8s_views._get_k8s_client')
    def test_service_list_handles_external_ip_and_cluster_ip_only_services(self, get_client):
        client = APIClient()
        client.force_authenticate(self.user)
        for external_ips in (None, [], ['192.0.2.10', '192.0.2.11']):
            with self.subTest(external_ips=external_ips):
                cache.clear()
                api = MagicMock()
                api.list_service_for_all_namespaces.return_value = SimpleNamespace(items=[self.service(external_ips)])
                get_client.return_value.CoreV1Api.return_value = api

                response = client.get(f'/api/k8s/clusters/{self.cluster.pk}/services/?namespace=_all')

                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(len(response.data), 1)
                self.assertEqual(response.data[0]['external_ip'], ','.join(external_ips or []))
                self.assertEqual(response.data[0]['cluster_ip'], '10.96.0.20')
                self.assertEqual(response.data[0]['ports'], '80/TCP')

    @patch('ops.k8s_views._get_k8s_client')
    def test_scoped_service_snapshot_uses_current_client_field_names(self, get_client):
        cache.clear()
        api = MagicMock()
        api.list_namespaced_service.return_value = SimpleNamespace(items=[self.service(['192.0.2.10'])])
        get_client.return_value.CoreV1Api.return_value = api

        rows = get_k8s_resource_snapshot(self.cluster, 'services', ['production'])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['external_ip'], '192.0.2.10')
        api.list_namespaced_service.assert_called_once_with(namespace='production')
