from unittest.mock import MagicMock, patch
import yaml
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from rbac.models import K8sUserAccess, Role, PermissionDefinition
from rbac.services import ensure_builtin_rbac
from ops.models import K8sCluster
from ops.k8s_exec_consumer import K8sExecConsumer
from ops.k8s_terminal_consumer import K8sClusterTerminalConsumer


class K8sWorkbenchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()
        cls.admin = get_user_model().objects.create_superuser('k8s-admin', password='Test@123456')
        cls.user = get_user_model().objects.create_user('k8s-operator', password='Test@123456')
        cls.cluster = K8sCluster.objects.create(name='demo', kubeconfig='demo', status='connected')
        cls.other = K8sCluster.objects.create(name='other', kubeconfig='demo', status='connected')
        role = Role.objects.create(code='k8s-tests', name='K8s tests')
        role.permissions.set(PermissionDefinition.objects.filter(code__startswith='ops.k8s.'))
        role.users.add(cls.user)

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.base = f'/api/k8s/clusters/{self.cluster.pk}/'

    def scope(self, role='operator', namespaces=None, allow_exec=False):
        policy = K8sUserAccess.objects.create(user=self.user)
        return policy.grants.create(cluster=self.cluster, role=role, namespaces=namespaces or [], allow_exec=allow_exec)

    def yaml(self, namespace='production', name='workbench-test'):
        return f'apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: {name}\n  namespace: {namespace}\ndata:\n  key: value\n'

    def post(self, action, payload):
        return self.client.post(self.base + action + '/', payload, format='json')

    def test_yaml_preview_does_not_mutate_and_apply_delete_roundtrip(self):
        payload = {'yaml': self.yaml()}
        response = self.post('yaml_preview', payload)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['operation'], 'create')
        self.assertEqual(self.client.get(self.base + 'resource_yaml/', {'type': 'configmap', 'name': 'workbench-test', 'namespace': 'production'}).status_code, 404)
        self.assertEqual(self.post('yaml_apply', payload).status_code, 200)
        listed = self.client.get(self.base + 'configmaps/', {'namespace': 'production'})
        self.assertTrue(any(row['name'] == 'workbench-test' for row in listed.data))
        self.assertEqual(self.post('resource_delete', {'type': 'configmap', 'name': 'workbench-test', 'namespace': 'production'}).status_code, 200)
        self.assertFalse(any(row['name'] == 'workbench-test' for row in self.client.get(self.base + 'configmaps/', {'namespace': 'production'}).data))

    def test_yaml_validates_kind_and_single_document(self):
        for content in ('[]', 'kind: Unknown\nmetadata:\n  name: test', self.yaml() + '\n---\n' + self.yaml()):
            response = self.post('yaml_apply', {'yaml': content})
            self.assertEqual(response.status_code, 400, response.data)

    def test_network_resource_yaml_roundtrip_and_list_fields(self):
        manifests = [
            ('endpoints', {'apiVersion': 'v1', 'kind': 'Endpoints',
                           'metadata': {'name': 'custom-endpoints', 'namespace': 'production'},
                           'subsets': [{'addresses': [{'ip': '192.0.2.10'}], 'notReadyAddresses': [{'ip': '192.0.2.11'}],
                                        'ports': [{'port': 8080, 'protocol': 'TCP'}]}]}),
            ('ingressclass', {'apiVersion': 'networking.k8s.io/v1', 'kind': 'IngressClass',
                              'metadata': {'name': 'custom-ingress', 'annotations': {'ingressclass.kubernetes.io/is-default-class': 'true'}},
                              'spec': {'controller': 'example.com/ingress-controller'}}),
        ]
        for resource_type, manifest in manifests:
            with self.subTest(resource_type=resource_type):
                namespace = manifest['metadata'].get('namespace', '')
                payload = {'yaml': yaml.safe_dump(manifest)}
                preview = self.post('yaml_preview', payload)
                self.assertEqual(preview.status_code, 200, preview.data)
                params = {'type': resource_type, 'name': manifest['metadata']['name'], 'namespace': namespace}
                self.assertEqual(self.client.get(self.base + 'resource_yaml/', params).status_code, 404)
                self.assertEqual(self.post('yaml_apply', payload).status_code, 200)
                detail = self.client.get(self.base + 'resource_yaml/', params)
                self.assertEqual(detail.status_code, 200, detail.data)
                document = yaml.safe_load(detail.data['yaml'])
                self.assertEqual(document['kind'], manifest['kind'])
                if resource_type == 'ingressclass':
                    self.assertNotIn('namespace', document['metadata'])
                else:
                    self.assertEqual(document['subsets'], manifest['subsets'])
                listed = self.client.get(self.base + 'resources/', {'type': resource_type, 'namespace': '_all'})
                self.assertEqual(listed.status_code, 200, listed.data)
                row = next(item for item in listed.data if item['name'] == manifest['metadata']['name'])
                if resource_type == 'endpoints':
                    self.assertEqual((row['addresses'], row['not_ready_addresses'], row['ports']), ('192.0.2.10', '192.0.2.11', '8080/TCP'))
                else:
                    self.assertEqual(row['spec']['controller'], 'example.com/ingress-controller')
                    self.assertTrue(row['is_default'])
                self.assertEqual(self.post('resource_delete', params).status_code, 200)
                self.assertEqual(self.client.get(self.base + 'resource_yaml/', params).status_code, 404)

    def test_network_resources_filter_namespaces_and_reject_cluster_scope_before_cache(self):
        self.assertEqual(self.client.get(self.base + 'resources/', {'type': 'ingressclass'}).status_code, 200)
        self.scope(namespaces=['production'])
        self.client.force_authenticate(self.user)
        for resource_type in ('endpoints', 'networkpolicy'):
            response = self.client.get(self.base + 'resources/', {'type': resource_type, 'namespace': '_all'})
            self.assertEqual(response.status_code, 200, response.data)
            self.assertTrue(response.data)
            self.assertEqual({row['namespace'] for row in response.data}, {'production'})
            self.assertEqual(self.client.get(self.base + 'resources/', {'type': resource_type, 'namespace': 'kube-system'}).status_code, 403)
        for namespace in ('production', '_all', ''):
            params = {'type': 'ingressclass', 'namespace': namespace, 'name': 'nginx'}
            self.assertEqual(self.client.get(self.base + 'resources/', params).status_code, 403)
            self.assertEqual(self.client.get(self.base + 'resource_yaml/', params).status_code, 403)
        manifest = 'apiVersion: networking.k8s.io/v1\nkind: IngressClass\nmetadata:\n  name: custom\nspec:\n  controller: example.com/controller\n'
        self.assertEqual(self.post('yaml_preview', {'yaml': manifest}).status_code, 403)
        self.assertEqual(self.post('resource_delete', {'type': 'ingressclass', 'name': 'nginx'}).status_code, 403)

    def test_ingressclass_writes_require_full_cluster_admin(self):
        grant = self.scope(role='viewer')
        self.client.force_authenticate(self.user)
        manifest = 'apiVersion: networking.k8s.io/v1\nkind: IngressClass\nmetadata:\n  name: custom\nspec:\n  controller: example.com/controller\n'
        for role in ('viewer', 'operator', 'admin'):
            grant.role = role
            grant.save()
            listed = self.client.get(self.base + 'resources/', {'type': 'ingressclass'})
            self.assertEqual(listed.status_code, 200)
            detail = self.client.get(self.base + 'resource_yaml/', {'type': 'ingressclass', 'name': 'nginx'})
            self.assertEqual(detail.status_code, 200, detail.data)
            response = self.post('yaml_preview', {'yaml': manifest})
            self.assertEqual(response.status_code, 200 if role == 'admin' else 403, response.data)

    @patch('ops.k8s_views._get_k8s_client')
    def test_live_network_lists_use_correct_api_cache_and_close_client(self, get_client):
        self.cluster.kubeconfig = 'live-config'
        self.cluster.save(update_fields=['kubeconfig'])
        module = get_client.return_value
        module.ApiClient.return_value.sanitize_for_serialization.side_effect = lambda item: item
        cases = [
            ('endpoints', 'production', module.CoreV1Api.return_value.list_namespaced_endpoints,
             {'metadata': {'name': 'api', 'namespace': 'production'}, 'subsets': [{'addresses': [{'ip': '192.0.2.10'}], 'ports': [{'port': 80}]}]}),
            ('endpoints', '_all', module.CoreV1Api.return_value.list_endpoints_for_all_namespaces,
             {'metadata': {'name': 'empty', 'namespace': 'default'}, 'subsets': None}),
            ('ingressclass', '_all', module.NetworkingV1Api.return_value.list_ingress_class,
             {'metadata': {'name': 'nginx', 'annotations': {'ingressclass.kubernetes.io/is-default-class': 'true'}}, 'spec': {'controller': 'k8s.io/ingress-nginx'}}),
            ('networkpolicy', 'production', module.NetworkingV1Api.return_value.list_namespaced_network_policy,
             {'metadata': {'name': 'allow', 'namespace': 'production'}, 'spec': {'podSelector': {}}}),
        ]
        for resource_type, namespace, method, document in cases:
            with self.subTest(resource_type=resource_type, namespace=namespace):
                method.return_value.items = [document]
                params = {'type': resource_type, 'namespace': namespace}
                first = self.client.get(self.base + 'resources/', params)
                second = self.client.get(self.base + 'resources/', params)
                self.assertEqual(first.status_code, 200, first.data)
                self.assertEqual(second.data, first.data)
                method.assert_called_once_with(**({'namespace': namespace} if namespace != '_all' else {}))
                row = first.data[0]
                if resource_type == 'endpoints':
                    self.assertEqual(row['ports'], '80/TCP' if namespace == 'production' else '')
                elif resource_type == 'ingressclass':
                    self.assertTrue(row['is_default'])
                    self.assertEqual(row['namespace'], '')
        self.assertEqual(get_client.call_count, len(cases))
        self.assertEqual(module.ApiClient.return_value.close.call_count, len(cases))
        self.scope(namespaces=['production'])
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.base + 'resources/', {'type': 'ingressclass'}).status_code, 403)
        self.assertEqual(get_client.call_count, len(cases))

    @patch('ops.k8s_views._get_k8s_client')
    def test_failed_network_list_closes_client_and_does_not_cache_empty_success(self, get_client):
        self.cluster.kubeconfig = 'live-config'
        self.cluster.save(update_fields=['kubeconfig'])
        module = get_client.return_value
        module.NetworkingV1Api.return_value.list_ingress_class.side_effect = RuntimeError('upstream unavailable')
        for attempt in range(2):
            response = self.client.get(self.base + 'resources/', {'type': 'ingressclass'})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(module.ApiClient.return_value.close.call_count, 2)

    def test_yaml_apply_rejects_resource_created_after_preview(self):
        payload = {'yaml': self.yaml()}
        preview = self.post('yaml_preview', payload)
        self.assertIsNone(preview.data['resource_version'])
        self.assertEqual(self.post('yaml_apply', payload).status_code, 200)
        response = self.post('yaml_apply', {**payload, 'expected_version': None})
        self.assertEqual(response.status_code, 409)

    def test_aiops_queries_obey_cluster_and_namespace_scope(self):
        from aiops.models import AIOpsChatMessage, AIOpsChatSession
        from aiops.services import query_container_assets, query_k8s_cluster_summary, query_k8s_resources
        self.scope(namespaces=['production'])
        session = AIOpsChatSession.objects.create(user=self.user, title='K8s scope test')
        message = AIOpsChatMessage.objects.create(session=session, role='user', content='查看集群')
        session._k8s_cluster_id = self.cluster.pk
        session._k8s_environment_snapshot = {'k8s_cluster_ids': [self.cluster.pk], 'k8s_namespaces': []}
        summary = query_k8s_cluster_summary(session, message, self.user)
        self.assertTrue(summary.get('pods'))
        self.assertEqual({row['namespace'] for row in summary['pods']}, {'production'})
        self.assertNotIn('nodes_total', summary['cluster'])
        nodes = query_k8s_resources(session, message, self.user, resource_type='nodes')
        self.assertEqual(nodes['items'], [])
        session._k8s_cluster_id = self.other.pk
        summary = query_k8s_cluster_summary(session, message, self.user)
        self.assertEqual(summary['summary']['count'], 0)
        assets = query_container_assets(session, message, self.user)
        self.assertEqual(assets['sections'], [{'title': 'Kubernetes 集群', 'items': ['demo / 已连接']}])

    def test_secret_yaml_and_config_editor_share_demo_data(self):
        manifest = 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: workbench-secret\n  namespace: production\nstringData:\n  password: demo-value\n'
        self.assertEqual(self.post('yaml_apply', {'yaml': manifest}).status_code, 200)
        response = self.client.get(self.base + 'config_resource_detail/', {'type': 'secret', 'name': 'workbench-secret', 'namespace': 'production'})
        self.assertEqual(response.data['data'], {'password': 'demo-value'})
        response = self.post('config_resource_update', {'type': 'secret', 'name': 'workbench-secret', 'namespace': 'production', 'content': 'password: updated'})
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.get(self.base + 'resource_yaml/', {'type': 'secret', 'name': 'workbench-secret', 'namespace': 'production'})
        self.assertEqual(yaml.safe_load(response.data['yaml'])['stringData'], {'password': 'updated'})

    def test_demo_yaml_tracks_scale_and_detects_edits_after_preview(self):
        manifest = 'apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: workbench-deploy\n  namespace: production\nspec:\n  replicas: 1\n'
        self.assertEqual(self.post('yaml_apply', {'yaml': manifest}).status_code, 200)
        preview = self.post('yaml_preview', {'yaml': manifest}).data
        response = self.post('scale_workload', {'workload_type': 'deployment', 'name': 'workbench-deploy', 'namespace': 'production', 'replicas': 3})
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.get(self.base + 'resource_yaml/', {'type': 'deployment', 'name': 'workbench-deploy', 'namespace': 'production'})
        self.assertEqual(yaml.safe_load(response.data['yaml'])['spec']['replicas'], 3)
        self.assertEqual(self.post('yaml_apply', {'yaml': manifest, 'expected_version': preview['resource_version']}).status_code, 409)
        old_manifest = yaml.safe_load(response.data['yaml'])
        old_manifest['metadata']['resourceVersion'] = preview['resource_version']
        self.assertEqual(self.post('yaml_preview', {'yaml': yaml.safe_dump(old_manifest)}).status_code, 409)

    def test_cluster_scope_hides_other_clusters_and_filters_all_namespaces(self):
        self.scope(namespaces=['production'])
        self.client.force_authenticate(self.user)
        response = self.client.get('/api/k8s/clusters/')
        self.assertEqual([row['id'] for row in response.data], [self.cluster.pk])
        self.assertEqual(self.client.get(f'/api/k8s/clusters/{self.other.pk}/pods/').status_code, 404)
        pods = self.client.get(self.base + 'pods/', {'namespace': '_all'})
        self.assertEqual(pods.status_code, 200)
        self.assertTrue(pods.data)
        self.assertEqual({row['namespace'] for row in pods.data}, {'production'})
        self.assertEqual({row['name'] for row in self.client.get(self.base + 'namespaces/').data}, {'production'})
        self.assertEqual(self.client.get(self.base + 'pods/', {'namespace': 'kube-system'}).status_code, 403)
        self.assertEqual(self.client.get(self.base + 'nodes/').status_code, 403)
        self.assertEqual(self.client.get(self.base + 'resource_yaml/', {'type': 'namespace', 'name': 'production'}).status_code, 200)
        self.assertEqual(self.client.get(self.base + 'resource_yaml/', {'type': 'namespace', 'name': 'kube-system'}).status_code, 403)
        summary = self.client.get(self.base + 'summary/')
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data['pods_total'], len(pods.data))
        self.assertEqual(summary.data['nodes_total'], 0)

    def test_empty_policy_denies_all_and_does_not_allow_cluster_creation(self):
        K8sUserAccess.objects.create(user=self.user)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get('/api/k8s/clusters/').data, [])
        response = self.client.post('/api/k8s/clusters/', {'name': 'new', 'kubeconfig': 'demo'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_summary_includes_server_version_for_full_and_namespace_scope(self):
        self.assertEqual(self.client.get(self.base + 'summary/').data['server_version'], 'v1.29.3')
        self.scope(namespaces=['production'])
        self.client.force_authenticate(self.user)
        summary = self.client.get(self.base + 'summary/')
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data['server_version'], 'v1.29.3')
        self.assertTrue(summary.data['scoped'])
        with patch('ops.k8s_views._get_cluster_server_version') as get_version:
            self.assertEqual(self.client.get(f'/api/k8s/clusters/{self.other.pk}/summary/').status_code, 404)
        get_version.assert_not_called()

    def test_updating_connection_clears_cached_server_version_and_old_summary(self):
        from ops.k8s_views import _server_version_cache_key, _summary_stale_cache_key

        version_key = _server_version_cache_key(self.cluster.pk)
        stale_key = _summary_stale_cache_key(self.cluster.pk)
        cache.set(version_key, 'v1.28.0', 300)
        cache.set(stale_key, {'server_version': 'v1.28.0'}, 300)
        response = self.client.patch(self.base, {'api_server': 'https://kubernetes.example.invalid:6443'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(cache.get(version_key))
        self.assertIsNone(cache.get(stale_key))

    def test_capacity_requires_full_cluster_scope_and_never_returns_a_warm_cache_to_scoped_users(self):
        first = self.client.get(self.base + 'capacity/')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data['resources']['cpu']['capacity'], 32)
        self.scope(namespaces=['production'])
        self.client.force_authenticate(self.user)
        response = self.client.get(self.base + 'capacity/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get(f'/api/k8s/clusters/{self.other.pk}/capacity/').status_code, 404)

    def test_capacity_allows_full_cluster_viewers_and_uses_short_cache(self):
        self.scope(role='viewer')
        self.client.force_authenticate(self.user)
        with patch('ops.k8s_views.demo_cluster_capacity', return_value={
            'resources': {'cpu': {'capacity': 32}}, 'unavailable_resources': [],
        }) as build:
            first = self.client.get(self.base + 'capacity/')
            second = self.client.get(self.base + 'capacity/')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.data, first.data)
        build.assert_called_once()

    def test_capacity_requires_platform_view_permission(self):
        self.scope(role='viewer')
        role = self.user.rbac_roles.get()
        role.permissions.clear()
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.base + 'capacity/').status_code, 403)

    @patch('ops.k8s_views.build_cluster_capacity')
    @patch('ops.k8s_views._get_k8s_client')
    def test_live_capacity_reuses_cached_totals_and_closes_client(self, get_client, build):
        self.cluster.kubeconfig = 'live-config'
        self.cluster.save(update_fields=['kubeconfig'])
        build.return_value = {'resources': {'cpu': {'capacity': 4}}, 'unavailable_resources': []}
        first = self.client.get(self.base + 'capacity/')
        second = self.client.get(self.base + 'capacity/')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.data, first.data)
        build.assert_called_once_with(get_client.return_value)
        get_client.return_value.ApiClient.return_value.close.assert_called_once()

    def test_other_cluster_catalogs_follow_user_authorization(self):
        self.scope(namespaces=['production'])
        role = self.user.rbac_roles.get()
        role.permissions.add(*PermissionDefinition.objects.filter(code__in=['aiops.knowledge.view', 'ops.task.execute']))
        self.cluster.name = 'authorized-cluster'
        self.cluster.save()
        self.client.force_authenticate(self.user)
        response = self.client.get('/api/aiops/knowledge-environments/catalog/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row['id'] for row in response.data['k8s_clusters']], [self.cluster.pk])
        self.assertEqual(response.data['k8s_clusters'][0]['namespaces'], ['production'])
        response = self.client.get('/api/host-tasks/resource_options/', {'resource_type': 'k8s'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual({row['cluster'] for row in response.data}, {self.cluster.pk})

    def test_namespace_and_viewer_limits_apply_to_yaml_and_legacy_actions(self):
        grant = self.scope(namespaces=['production'])
        self.client.force_authenticate(self.user)
        self.assertEqual(self.post('yaml_apply', {'yaml': self.yaml('kube-system')}).status_code, 403)
        self.assertEqual(self.post('yaml_apply', {'yaml': 'apiVersion: v1\nkind: Namespace\nmetadata:\n  name: other'}).status_code, 403)
        self.assertEqual(self.post('yaml_apply', {'yaml': self.yaml()}).status_code, 200)
        self.assertEqual(self.post('kubectl', {'command': 'kubectl get pods'}).status_code, 403)
        self.assertEqual(self.post('pod_exec', {'namespace': 'production', 'pod_name': 'test', 'command': 'pwd'}).status_code, 403)
        grant.role = 'viewer'
        grant.save()
        self.assertEqual(self.post('yaml_preview', {'yaml': self.yaml()}).status_code, 403)
        self.assertEqual(self.post('scale_workload', {'namespace': 'production', 'workload_type': 'deployment', 'name': 'nginx-deployment', 'replicas': 1}).status_code, 403)

    def test_platform_permission_is_still_required_with_cluster_grant(self):
        self.scope(role='admin')
        self.user.rbac_roles.clear()
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.base + 'pods/').status_code, 403)
        self.assertEqual(self.post('yaml_apply', {'yaml': self.yaml()}).status_code, 403)

    def test_user_management_saves_validated_policy_and_audits(self):
        path = f'/api/users/{self.user.pk}/k8s-access/'
        payload = {'unrestricted': False, 'grants': [{'cluster': self.cluster.pk, 'role': 'operator', 'namespaces': ['production'], 'allow_exec': True}]}
        response = self.client.put(path, payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['unrestricted'])
        self.assertEqual(response.data['grants'][0]['namespaces'], ['production'])
        payload['grants'][0]['namespaces'] = ['_all']
        self.assertEqual(self.client.put(path, payload, format='json').status_code, 400)
        self.assertEqual(K8sUserAccess.objects.get(user=self.user).grants.get().namespaces, ['production'])
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.put(path, {'unrestricted': True, 'grants': []}, format='json').status_code, 403)

    def test_websockets_reject_disallowed_namespace_and_cluster_shell(self):
        self.scope(namespaces=['production'], allow_exec=True)
        token = Token.objects.create(user=self.user)
        consumer = K8sExecConsumer()
        consumer.scope = {'url_route': {'kwargs': {'cluster_id': self.cluster.pk}}, 'query_string': f'token={token.key}&pod_name=test&namespace=kube-system'.encode()}
        consumer.close, consumer.accept = MagicMock(), MagicMock()
        consumer.connect()
        consumer.close.assert_called_with(code=4403)
        consumer.accept.assert_not_called()
        terminal = K8sClusterTerminalConsumer()
        terminal.scope = {'url_route': {'kwargs': {'cluster_id': self.cluster.pk}}, 'query_string': f'token={token.key}'.encode()}
        terminal.close, terminal.accept = MagicMock(), MagicMock()
        terminal.connect()
        terminal.close.assert_called_with(code=4403)
        terminal.accept.assert_not_called()

    def test_node_and_cronjob_actions_update_demo_lists(self):
        nodes = self.client.get(self.base + 'nodes/').data
        name = nodes[0]['name']
        self.assertEqual(self.post('node_action', {'name': name, 'operation': 'cordon'}).status_code, 200)
        self.assertTrue(next(row for row in self.client.get(self.base + 'nodes/').data if row['name'] == name)['unschedulable'])
        jobs = self.client.get(self.base + 'cronjobs/', {'namespace': '_all'}).data
        job = jobs[0]
        self.assertEqual(self.post('workload_action', {'type': 'cronjob', 'name': job['name'], 'namespace': job['namespace'], 'operation': 'suspend'}).status_code, 200)
        self.assertTrue(next(row for row in self.client.get(self.base + 'cronjobs/', {'namespace': '_all'}).data if row['name'] == job['name'])['suspend'])

    def test_task_center_cannot_bypass_explicit_scope(self):
        from rbac.k8s_access import validate_k8s_task_access
        from rest_framework.exceptions import PermissionDenied
        self.scope(namespaces=['production'], allow_exec=True)
        with self.assertRaises(PermissionDenied):
            validate_k8s_task_access(self.user, 'k8s_restart_pod', [{'cluster_id': self.cluster.pk, 'namespace': 'kube-system', 'name': 'test'}])
        with self.assertRaises(PermissionDenied):
            validate_k8s_task_access(self.user, 'k8s_pod_exec', [{'cluster_id': self.cluster.pk, 'namespace': 'production', 'name': 'test'}], {'command': 'kubectl get pods'})
        validate_k8s_task_access(self.user, 'k8s_pod_exec', [{'cluster_id': self.cluster.pk, 'namespace': 'production', 'name': 'test'}], {'command': 'pwd'})

    def test_task_dispatch_cannot_disguise_cluster_commands_as_service_or_helm(self):
        from rbac.k8s_access import validate_k8s_task_access
        from rest_framework.exceptions import PermissionDenied
        self.scope(namespaces=['production'], allow_exec=True)
        targets = [{'cluster_id': self.cluster.pk, 'namespace': 'production', 'name': 'test'}]
        for payload in ({'resource_kind': 'service', 'command': 'get secrets -A'},
                        {'deployment_strategy': ' HELM ', 'command': 'pwd'},
                        {'command': 'HELM upgrade example'}):
            with self.subTest(payload=payload), self.assertRaises(PermissionDenied):
                validate_k8s_task_access(self.user, 'k8s_pod_exec', targets, payload)
        validate_k8s_task_access(self.user, 'k8s_pod_exec', targets,
                                 {'resource_kind': 'service', 'patch': {'spec': {'type': 'ClusterIP'}}})

    def test_cluster_command_task_requires_platform_kubectl_permission(self):
        from rbac.k8s_access import validate_k8s_task_access
        from rest_framework.exceptions import PermissionDenied
        self.scope(role='admin')
        role = self.user.rbac_roles.get()
        role.permissions.remove(PermissionDefinition.objects.get(code='ops.k8s.kubectl'))
        with self.assertRaises(PermissionDenied):
            validate_k8s_task_access(self.user, 'k8s_pod_exec', [{'cluster_id': self.cluster.pk}], {'command': 'kubectl get pods'})

    @patch('ops.k8s_views._get_k8s_client')
    def test_live_preview_uses_server_dry_run_and_preserves_resource_version(self, get_client):
        self.cluster.kubeconfig = 'live'
        self.cluster.save()
        client = get_client.return_value
        client.ApiClient.return_value.sanitize_for_serialization.return_value = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'workbench-test', 'namespace': 'production', 'resourceVersion': '23'}, 'data': {}}
        response = self.post('yaml_preview', {'yaml': self.yaml()})
        self.assertEqual(response.status_code, 200, response.data)
        call = client.CoreV1Api.return_value.replace_namespaced_config_map.call_args.kwargs
        self.assertEqual(call['dry_run'], 'All')
        self.assertEqual(call['body']['metadata']['resourceVersion'], '23')
        self.assertEqual(call['namespace'], 'production')
