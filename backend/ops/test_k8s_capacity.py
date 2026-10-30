from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from ops.k8s_capacity import _pod_resources, build_cluster_capacity


def container(requests=None, limits=None, restart_policy=None):
    return SimpleNamespace(resources=SimpleNamespace(requests=requests, limits=limits), restart_policy=restart_policy)


def pod(containers, init_containers=None, overhead=None, phase='Running', node_name='node-1', resources=None):
    return SimpleNamespace(
        spec=SimpleNamespace(containers=containers, init_containers=init_containers, overhead=overhead,
                             node_name=node_name, resources=resources),
        status=SimpleNamespace(phase=phase),
    )


class K8sCapacityTests(SimpleTestCase):
    def k8s_client(self, pods=None, metrics=None):
        client = MagicMock()
        client.CoreV1Api.return_value.list_node.return_value.items = [SimpleNamespace(
            metadata=SimpleNamespace(name='node-1'),
            status=SimpleNamespace(capacity={'cpu': '4', 'memory': '8Gi', 'pods': '110'},
                                   allocatable={'cpu': '3500m', 'memory': '7500Mi', 'pods': '100'}),
        )]
        client.CoreV1Api.return_value.list_pod_for_all_namespaces.return_value.items = pods or []
        client.CustomObjectsApi.return_value.list_cluster_custom_object.return_value = {
            'items': metrics if metrics is not None else [
                {'metadata': {'name': 'node-1'}, 'usage': {'cpu': '1500000000n', 'memory': '2048Mi'}, 'timestamp': '2026-10-20T01:00:00Z'},
            ],
        }
        return client

    def test_quantity_units_and_scheduler_resource_accounting(self):
        workload = pod(
            [container({'cpu': '500m', 'memory': '128Mi'}, {'cpu': '2', 'memory': '1Gi'})],
            [container({'cpu': '200m', 'memory': '64Mi'}, {'cpu': '500m', 'memory': '128Mi'}, 'Always'),
             container({'cpu': '1', 'memory': '256Mi'}, {'cpu': '3', 'memory': '2Gi'})],
            {'cpu': '100m', 'memory': '16Mi'},
        )
        excluded = [pod([container({'cpu': '10'})], phase='Succeeded'),
                    pod([container({'cpu': '10'})], phase='Failed'),
                    pod([container({'cpu': '10'})], phase='Pending', node_name=None)]
        payload = build_cluster_capacity(self.k8s_client([workload, *excluded]))
        cpu, memory, pods = (payload['resources'][name] for name in ('cpu', 'memory', 'pods'))
        self.assertEqual(cpu, {'usage': 1.5, 'requests': 1.3, 'limits': 3.6, 'allocatable': 3.5, 'capacity': 4.0})
        self.assertEqual(memory['usage'], 2 * 2 ** 30)
        self.assertEqual(memory['requests'], 336 * 2 ** 20)
        self.assertEqual(memory['limits'], 2192 * 2 ** 20)
        self.assertEqual(pods, {'usage': 1, 'allocatable': 100, 'capacity': 110})
        self.assertTrue(payload['metrics']['available'])
        self.assertEqual(payload['metrics']['nodes_covered'], 1)

    def test_init_sidecar_peaks_do_not_sum_nonconcurrent_init_containers(self):
        workload = pod([container({'cpu': '1'})], [
            container({'cpu': '2'}), container({'cpu': '500m'}, restart_policy='Always'),
            container({'cpu': '3'}), container({'cpu': '1'}, restart_policy='Always'),
        ])
        self.assertEqual(float(_pod_resources(workload, 'requests', 'cpu')), 3.5)

    def test_limits_default_to_requests_and_pod_level_requests_override_containers(self):
        workload = pod([container(limits={'cpu': '2'})], overhead={'cpu': '100m'})
        self.assertEqual(float(_pod_resources(workload, 'requests', 'cpu')), 2.1)
        workload.spec.resources = SimpleNamespace(requests={'cpu': '3'}, limits={'cpu': '5'})
        self.assertEqual(float(_pod_resources(workload, 'requests', 'cpu')), 3.1)
        self.assertEqual(float(_pod_resources(workload, 'limits', 'cpu')), 5.1)

    def test_metrics_failure_preserves_capacity_without_fabricating_usage(self):
        client = self.k8s_client([pod([container({'cpu': '250m'})])])
        client.CustomObjectsApi.return_value.list_cluster_custom_object.side_effect = PermissionError('sensitive details')
        payload = build_cluster_capacity(client)
        self.assertIsNone(payload['resources']['cpu']['usage'])
        self.assertEqual(payload['resources']['cpu']['capacity'], 4)
        self.assertEqual(payload['resources']['cpu']['requests'], .25)
        self.assertEqual(payload['unavailable_resources'], ['metrics'])
        self.assertNotIn('sensitive details', str(payload))
        self.assertFalse(payload['metrics']['available'])

    def test_partial_metrics_and_missing_usage_are_not_reported_as_cluster_usage(self):
        for metrics in ([], [{'metadata': {'name': 'unknown'}, 'usage': {'cpu': '1', 'memory': '1Gi'}}],
                        [{'metadata': {'name': 'node-1'}, 'usage': {'cpu': '1'}}]):
            with self.subTest(metrics=metrics):
                payload = build_cluster_capacity(self.k8s_client(metrics=metrics))
                self.assertFalse(payload['metrics']['available'])
                self.assertIsNone(payload['resources']['memory']['usage'])

    def test_node_and_pod_failures_remain_unknown_instead_of_zero(self):
        client = self.k8s_client()
        client.CoreV1Api.return_value.list_node.side_effect = TimeoutError()
        client.CoreV1Api.return_value.list_pod_for_all_namespaces.side_effect = TimeoutError()
        payload = build_cluster_capacity(client)
        for value in payload['resources']['cpu'].values():
            self.assertIsNone(value)
        self.assertIsNone(payload['resources']['pods']['usage'])
        self.assertEqual(payload['unavailable_resources'], ['nodes', 'pods'])
