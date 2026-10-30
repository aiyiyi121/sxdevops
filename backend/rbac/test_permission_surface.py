"""Cross-module authorization regressions for the registered HTTP and WS surface."""
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import URLResolver, get_resolver
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from aiops.models import AIOpsMCPServer
from eventwall.services import sanitize_value
from ops.models import (
    AlertIntegration, AlertNotificationChannel, HostTask, K8sCluster,
    LogDataSource, MetricDataSource, TracingDataSource,
)
from .k8s_access import validate_k8s_task_access
from .models import K8sUserAccess, PermissionDefinition, Role, UserGroup
from .permissions import RBACPermission, RBACPermissionMixin
from .registry import BUILTIN_ROLES, PERMISSION_DEFINITIONS
from .services import ensure_builtin_rbac, get_user_effective_permissions, user_has_permissions


User = get_user_model()


def api_methods():
    """Inspect registered callbacks, excluding format aliases and disabled verbs."""
    seen = set()

    def walk(patterns, prefix=''):
        for pattern in patterns:
            path = prefix + str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                if not path.startswith('admin/'):
                    yield from walk(pattern.url_patterns, path)
                continue
            callback = pattern.callback
            cls = getattr(callback, 'cls', None)
            if not path.startswith('api/') or cls is None:
                continue
            actions = getattr(callback, 'actions', {})
            methods = actions or {m: m for m in cls.http_method_names if hasattr(cls, m)}
            for method, action in list(methods.items()):
                if method in ('head', 'options') or method not in cls.http_method_names:
                    continue
                identity = (cls, method, action)
                if identity in seen:
                    continue
                seen.add(identity)
                kwargs = {key: '0' for key in pattern.pattern.regex.groupindex if key != 'format'}
                yield callback, cls, method, action, kwargs

    yield from walk(get_resolver().url_patterns)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PermissionSurfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()
        cls.user = User.objects.create_user(username='surface-user')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def grant(self, *codes):
        code = f'surface-{Role.objects.count()}'
        role = Role.objects.create(code=code, name=code)
        role.permissions.set(PermissionDefinition.objects.filter(code__in=codes))
        role.users.add(self.user)
        return role

    def test_every_registered_rbac_requirement_exists_in_catalog(self):
        catalog = {row[0] for row in PERMISSION_DEFINITIONS}
        self.assertEqual(len(catalog), len(PERMISSION_DEFINITIONS))
        inspected = 0
        for callback, cls, method, action, kwargs in api_methods():
            with self.subTest(view=cls.__name__, method=method, action=action):
                if issubclass(cls, RBACPermissionMixin):
                    mapping = cls.rbac_permissions
                    self.assertTrue(action in mapping or '*' in mapping)
                    codes = mapping.get(action, mapping.get('*')) or []
                    # Resource requests enforce an OR gate plus applicant ownership in the body.
                    if not codes:
                        self.assertEqual(cls.__name__, 'ResourceRequestViewSet')
                        self.assertIn(action, ('list', 'retrieve', 'provisioning_options'))
                else:
                    codes = [code for p in cls.permission_classes if issubclass(p, RBACPermission)
                             for code in p.required_permissions]
                self.assertTrue(set(codes).issubset(catalog), set(codes) - catalog)
                inspected += 1
        self.assertGreater(inspected, 500)
        for role in BUILTIN_ROLES:
            self.assertTrue(set(role['permissions']).difference({'*'}).issubset(catalog), role['code'])

    def test_account_without_permissions_cannot_call_business_apis(self):
        factory = APIRequestFactory()
        inspected = 0
        for callback, cls, method, action, kwargs in api_methods():
            protected = issubclass(cls, RBACPermissionMixin) or any(
                issubclass(p, RBACPermission) for p in cls.permission_classes
            )
            if not protected:
                continue
            with self.subTest(view=cls.__name__, method=method, action=action):
                request = factory.generic(method.upper(), '/api/permission-audit/', '{}', content_type='application/json')
                force_authenticate(request, self.user)
                response = callback(request, **kwargs)
                self.assertEqual(response.status_code, 403)
                inspected += 1
        self.assertGreater(inspected, 500)

    def test_read_only_role_has_no_write_or_terminal_capabilities(self):
        permissions = Role.objects.get(code='read-only').permissions.values_list('code', flat=True)
        forbidden_suffixes = {'manage', 'execute', 'exec', 'terminal', 'kubectl', 'submit', 'approve', 'sync', 'notify', 'generate', 'invoke'}
        self.assertFalse([code for code in permissions if code.rsplit('.', 1)[-1] in forbidden_suffixes])

    def test_all_websocket_terminals_require_active_account_and_platform_permission(self):
        from ops.ssh_consumer import SSHConsumer
        from ops.docker_exec_consumer import DockerExecConsumer
        from ops.k8s_exec_consumer import K8sExecConsumer
        from ops.k8s_terminal_consumer import K8sClusterTerminalConsumer
        token = Token.objects.create(user=self.user)
        for active in (True, False):
            self.user.is_active = active
            self.user.save(update_fields=['is_active'])
            for cls in (SSHConsumer, DockerExecConsumer, K8sExecConsumer, K8sClusterTerminalConsumer):
                with self.subTest(consumer=cls.__name__, active=active):
                    consumer = cls()
                    consumer.scope = {'url_route': {'kwargs': {'host_id': '0', 'cluster_id': '0'}},
                                      'query_string': f'token={token.key}&container_id=test&pod_name=test'.encode()}
                    consumer.close, consumer.accept = Mock(), Mock()
                    consumer.connect()
                    consumer.close.assert_called_once_with(code=4403 if active else 4401)
                    consumer.accept.assert_not_called()

    def test_unrestricted_k8s_user_still_needs_specific_platform_rights(self):
        self.grant('ops.task.execute')
        cluster = K8sCluster.objects.create(name='permission-cluster', api_server='demo://k8s')
        targets = [{'cluster_id': cluster.pk, 'namespace': 'default', 'name': 'test', 'kind': 'pod'}]
        for task_type, payload in [('k8s_pod_exec', {'command': 'pwd'}),
                                   ('k8s_pod_exec', {'command': 'kubectl get secrets -A'}),
                                   ('k8s_restart_pod', {})]:
            with self.subTest(task_type=task_type, payload=payload), self.assertRaises(PermissionDenied):
                validate_k8s_task_access(self.user, task_type, targets, payload)
        self.grant('ops.k8s.exec')
        validate_k8s_task_access(self.user, 'k8s_pod_exec', targets, {'command': 'pwd'})
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        with self.assertRaises(PermissionDenied):
            validate_k8s_task_access(self.user, 'k8s_pod_exec', targets, {'command': 'pwd'})

    def test_pending_and_rerun_k8s_tasks_cannot_bypass_platform_rights(self):
        self.grant('ops.task.execute')
        cluster = K8sCluster.objects.create(name='task-cluster', api_server='demo://k8s')
        task = HostTask.objects.create(name='Pending shell', target_type='k8s', task_type='k8s_pod_exec',
                                       payload={'command': 'pwd'}, created_by=self.user.username,
                                       target_snapshot=[{'cluster_id': cluster.pk, 'name': 'test', 'namespace': 'default', 'kind': 'pod'}])
        with patch('ops.views.start_k8s_task') as start:
            for action in ('execute', 'rerun'):
                response = self.client.post(f'/api/host-tasks/{task.pk}/{action}/', {}, format='json')
                self.assertEqual(response.status_code, 403, response.data)
            start.assert_not_called()

    def test_k8s_viewers_only_receive_secret_metadata_and_cannot_read_history(self):
        from django.core.cache import cache
        cache.clear()
        root = User.objects.create_superuser(username='secret-root')
        self.client.force_authenticate(root)
        cluster = K8sCluster.objects.create(name='secret-cluster', kubeconfig='demo')
        base = f'/api/k8s/clusters/{cluster.pk}/'
        manifest = 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: restricted-secret\n  namespace: production\nstringData:\n  password: private-secret-value\n'
        response = self.client.post(base + 'yaml_apply/', {'yaml': manifest}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.grant('ops.k8s.view')
        self.client.force_authenticate(self.user)
        response = self.client.get(base + 'secrets/', {'namespace': 'production'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('restricted-secret', str(response.data))
        self.assertNotIn('private-secret-value', str(response.data))
        self.assertFalse(any(set(row) & {'data', 'stringData', 'data_payload'} for row in response.data))
        params = {'type': 'secret', 'name': 'restricted-secret', 'namespace': 'production', 'revision_id': '1'}
        for action in ('resource_yaml', 'config_resource_detail', 'config_resource_revisions', 'config_resource_revision_preview'):
            self.assertEqual(self.client.get(base + action + '/', params).status_code, 403, action)
        self.grant('ops.k8s.secret.view')
        self.assertIn('private-secret-value', str(self.client.get(base + 'resource_yaml/', params).data))
        policy = K8sUserAccess.objects.create(user=self.user)
        policy.grants.create(cluster=cluster, role='viewer', namespaces=['other'])
        self.assertEqual(self.client.get(base + 'resource_yaml/', params).status_code, 403)
        cache.clear()

    def test_shared_role_cannot_change_protected_accounts_indirectly(self):
        self.grant('rbac.role.manage', 'ops.dashboard.view')
        protected = User.objects.create_superuser(username='surface-root')
        shared = Role.objects.create(code='shared-low-role', name='Shared')
        shared.permissions.add(PermissionDefinition.objects.get(code='ops.dashboard.view'))
        group = UserGroup.objects.create(code='shared-group', name='Shared group')
        group.roles.add(shared)
        group.users.add(protected)
        response = self.client.get('/api/roles/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.patch(f'/api/roles/{shared.pk}/', {'permission_ids': []}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'/api/roles/{shared.pk}/').status_code, 403)
        self.assertTrue(shared.permissions.exists())

    def test_batch_cloud_sync_cannot_write_cmdb_without_cmdb_manage(self):
        self.grant('ops.multicloud.sync')
        with patch('multicloud.views.batch_sync_targets', return_value=[]) as sync:
            self.assertEqual(self.client.post('/api/multicloud/batch-sync/', {'sync_cmdb': True}, format='json').status_code, 403)
            sync.assert_not_called()
            self.grant('cmdb.ci.manage')
            self.assertEqual(self.client.post('/api/multicloud/batch-sync/', {'sync_cmdb': True}, format='json').status_code, 200)
            sync.assert_called_once()

    def test_config_viewers_cannot_extract_mcp_or_alert_credentials(self):
        self.grant('aiops.config.view', 'ops.alert.config.view')
        mcp = AIOpsMCPServer.objects.create(name='Private MCP', server_type='http',
                                          endpoint_or_command='https://mcp.example.test/?key=private-endpoint',
                                          auth_config={'headers': {'Authorization': 'Bearer private-mcp'}, 'env': {'CUSTOM': 'private-env'}})
        integration = AlertIntegration.objects.create(name='Private webhook', provider='generic')
        channel = AlertNotificationChannel.objects.create(name='Private channel', channel_type='feishu', config={'webhook_url': 'https://example.test/private-hook'})
        for path, secrets in (
            (f'/api/aiops/admin/mcp-servers/{mcp.pk}/', ('private-endpoint', 'private-mcp', 'private-env')),
            (f'/api/alert-integrations/{integration.pk}/', (integration.token,)),
            (f'/api/alert-notification-channels/{channel.pk}/', ('private-hook',)),
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.data)
            for secret in secrets:
                self.assertNotIn(secret, str(response.data))
        self.grant('aiops.config.manage', 'ops.alert.config.manage')
        self.assertEqual(self.client.get(f'/api/aiops/admin/mcp-servers/{mcp.pk}/').data['auth_config'], mcp.auth_config)
        self.assertEqual(self.client.get(f'/api/alert-integrations/{integration.pk}/').data['token'], integration.token)
        self.assertEqual(self.client.get(f'/api/alert-notification-channels/{channel.pk}/').data['config'], channel.config)

    def test_audit_masks_nested_auth_material_without_masking_environment(self):
        result = sanitize_value({'environment': 'production', 'auth_config': {'arbitrary': 'private-auth'},
                                 'headers': {'Custom-Auth': 'private-header'}, 'env': {'CUSTOM': 'private-env'},
                                 'api_key': 'private-key', 'authorization': 'private-authz',
                                 'nested': {'apiKey': 'private-camel-key', 'X-Api-Key': 'private-header-key'},
                                 'authorization_before': {'role_ids': [1]}})
        self.assertEqual(result['environment'], 'production')
        self.assertEqual(result['authorization_before'], {'role_ids': [1]})
        self.assertNotIn('private-', str(result))

    def test_datasource_viewers_cannot_extract_nested_or_demo_flagged_credentials(self):
        self.grant('ops.log.datasource.view', 'ops.trace.datasource.view', 'ops.metric.datasource.view')
        for model, provider, path in (
            (LogDataSource, 'loki', '/api/log/datasources/'),
            (TracingDataSource, 'skywalking', '/api/observability/tracing/datasources/'),
            (MetricDataSource, 'prometheus', '/api/observability/metric/datasources/'),
        ):
            with self.subTest(model=model.__name__):
                source = model.objects.create(name=f'Private {provider}', provider=provider, config={
                    'demo_mode': True, 'bearer_token': 'private-demo-token',
                    'headers': {'X-Custom-Auth': 'private-header'},
                    'nested': {'apiKey': 'private-camel-key', 'password': 'private-password'},
                })
                response = self.client.get(f'{path}{source.pk}/')
                self.assertEqual(response.status_code, 200, response.data)
                self.assertNotIn('private-', str(response.data))

    @override_settings(SYSTEM_POSTURE_ENABLED=False)
    def test_disabled_feature_is_removed_from_effective_permissions(self):
        self.grant('ops.observability.system_posture.view', 'ops.dashboard.view')
        self.assertNotIn('ops.observability.system_posture.view', get_user_effective_permissions(self.user))
        self.assertIn('ops.dashboard.view', get_user_effective_permissions(self.user))
        self.assertFalse(user_has_permissions(self.user, ['ops.observability.system_posture.view']))
