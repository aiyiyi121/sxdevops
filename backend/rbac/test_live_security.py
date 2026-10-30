from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIRequestFactory

from ops.models import K8sCluster
from .models import K8sClusterGrant, K8sUserAccess, PermissionDefinition, Role, UserGroup
from .throttles import LoginIPThrottle, client_ip
from .websocket import TerminalRevocationMiddleware


@override_settings(WEBSOCKET_AUTH_RECHECK_SECONDS=0.02)
class LiveTerminalRevocationTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('terminal-user')
        self.token = Token.objects.create(user=self.user)
        self.role = Role.objects.create(code='terminal-test', name='terminal-test')
        for code in ('ops.host.terminal', 'ops.docker.view', 'ops.docker.exec', 'ops.k8s.exec', 'ops.k8s.terminal'):
            permission, _ = PermissionDefinition.objects.get_or_create(code=code, defaults={'name': code, 'category': 'test'})
            self.role.permissions.add(permission)
        self.role.users.add(self.user)
        self.cluster = K8sCluster.objects.create(name='terminal-test-cluster', api_server='https://192.0.2.1')
        self.cleaned = []

    async def terminal(self, scope, receive, send):
        self.assertEqual((await receive())['type'], 'websocket.connect')
        await send({'type': 'websocket.accept'})
        try:
            while True:
                message = await receive()
                if message['type'] == 'websocket.disconnect':
                    return
                await send({'type': 'websocket.send', 'text': 'accepted input'})
        finally:
            self.cleaned.append(scope['path'])

    async def check_revocation(self, paths, mutation, expected=4403):
        connections = [WebsocketCommunicator(TerminalRevocationMiddleware(self.terminal), f'{path}?token={self.token.key}') for path in paths]
        for connection in connections:
            self.assertTrue((await connection.connect())[0])
        await database_sync_to_async(mutation)()
        for connection in connections:
            result = await connection.receive_output(timeout=2)
            self.assertEqual(result, {'type': 'websocket.close', 'code': expected})
            await connection.wait(timeout=2)
        self.assertEqual(len(self.cleaned), len(paths))

    def all_paths(self):
        return ['/ws/ssh/1/', '/ws/docker/exec/1/', f'/ws/k8s/exec/{self.cluster.pk}/', f'/ws/k8s/terminal/{self.cluster.pk}/']

    def test_role_revocation_closes_all_four_idle_terminals(self):
        async_to_sync(self.check_revocation)(self.all_paths(), lambda: self.role.users.remove(self.user))

    def test_bulk_deactivation_closes_existing_connections(self):
        async_to_sync(self.check_revocation)(self.all_paths(), lambda: get_user_model().objects.filter(pk=self.user.pk).update(is_active=False), 4401)

    def test_deleted_token_closes_existing_connections(self):
        async_to_sync(self.check_revocation)(self.all_paths(), lambda: self.token.delete(), 4401)

    def test_group_permission_removal_closes_existing_connections(self):
        self.role.users.clear()
        group = UserGroup.objects.create(code='terminal-group', name='terminal-group')
        group.roles.add(self.role)
        group.users.add(self.user)
        async_to_sync(self.check_revocation)(self.all_paths(), lambda: self.role.permissions.clear())

    def test_cluster_grant_revocation_closes_existing_connections(self):
        access = K8sUserAccess.objects.create(user=self.user)
        grant = K8sClusterGrant.objects.create(access=access, cluster=self.cluster, role='admin', allow_exec=True)
        async_to_sync(self.check_revocation)(self.all_paths()[2:], lambda: grant.delete())

    def test_input_is_not_forwarded_after_revocation(self):
        async def exercise():
            connection = WebsocketCommunicator(TerminalRevocationMiddleware(self.terminal), f'/ws/ssh/1/?token={self.token.key}')
            self.assertTrue((await connection.connect())[0])
            await database_sync_to_async(self.role.permissions.clear)()
            await connection.send_to(text_data='must not reach shell')
            self.assertEqual((await connection.receive_output())['type'], 'websocket.close')
            await connection.wait()
        async_to_sync(exercise)()

    def test_rejected_accept_stops_connect_before_remote_resources_open(self):
        opened = []

        async def connecting(scope, receive, send):
            await receive()
            await send({'type': 'websocket.accept'})
            opened.append('remote connection')

        async def exercise():
            connection = WebsocketCommunicator(TerminalRevocationMiddleware(connecting), '/ws/ssh/1/')
            with patch('rbac.websocket.terminal_access_code', new=AsyncMock(return_value=4403)):
                self.assertEqual(await connection.connect(), (False, 4403))
                await connection.wait()
            self.assertEqual(opened, [])

        async_to_sync(exercise)()


@override_settings(LOGIN_TRUSTED_PROXIES=[])
class LoginRateLimitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.factory = APIRequestFactory()

    def test_untrusted_forwarded_header_cannot_rotate_client_identity(self):
        first = self.factory.post('/api/login/', REMOTE_ADDR='192.0.2.10', HTTP_X_FORWARDED_FOR='203.0.113.1')
        second = self.factory.post('/api/login/', REMOTE_ADDR='192.0.2.10', HTTP_X_FORWARDED_FOR='203.0.113.2')
        self.assertEqual(client_ip(first), client_ip(second))

    @override_settings(LOGIN_TRUSTED_PROXIES=['192.0.2.0/24'])
    def test_trusted_chain_uses_nearest_untrusted_address(self):
        request = self.factory.post('/api/login/', REMOTE_ADDR='192.0.2.10', HTTP_X_FORWARDED_FOR='1.2.3.4, 203.0.113.5, 192.0.2.20')
        self.assertEqual(client_ip(request), '203.0.113.5')

    def test_separate_throttle_instances_share_atomic_limit(self):
        request = self.factory.post('/api/login/', REMOTE_ADDR='192.0.2.10')
        with patch('rbac.throttles.time.time', return_value=120):
            for _ in range(30):
                self.assertTrue(LoginIPThrottle().allow_request(request, None))
            throttle = LoginIPThrottle()
            self.assertFalse(throttle.allow_request(request, None))
            self.assertGreater(throttle.wait(), 0)

    def test_cache_failure_denies_login(self):
        request = self.factory.post('/api/login/', REMOTE_ADDR='192.0.2.10')
        with patch.object(LoginIPThrottle.cache, 'add', side_effect=ConnectionError), self.assertLogs('rbac.throttles', level='ERROR'):
            self.assertFalse(LoginIPThrottle().allow_request(request, None))
