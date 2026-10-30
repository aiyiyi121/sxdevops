import json
import tempfile
from collections import deque
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ops.docker_exec_consumer import DockerExecConsumer
from ops.docker_views import _get_ssh_client_from_docker_host, _run_docker, _ssh_exec
from ops.models import DockerHost
from rbac.models import PermissionDefinition, Role
from rbac.services import ensure_builtin_rbac


class DockerWorkbenchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()
        cls.admin = get_user_model().objects.create_superuser('docker-admin', password='Test@123456')
        cls.viewer = get_user_model().objects.create_user('docker-viewer', password='Test@123456')
        cls.viewer.rbac_roles.add(Role.objects.get(code='read-only'))
        cls.host = DockerHost.objects.create(name='app-release-test', ip_address='192.168.1.120', status='connected')
        cls.real = DockerHost.objects.create(name='real-docker', ip_address='192.0.2.10', status='connected')

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_summary_reports_capacity_and_changes_after_container_action(self):
        url = f'/api/docker/hosts/{self.host.pk}/summary/'
        summary = self.client.get(url).json()
        self.assertEqual(summary['memory_bytes'], 16 * 1024 ** 3)
        container = self.client.get('/api/docker/containers/', {'host_id': self.host.pk}).json()[0]
        self.assertEqual(self.client.post(f'/api/docker/containers/{container["id"]}/action/', {'host_id': self.host.pk, 'action': 'stop'}).status_code, 200)
        updated = self.client.get(url).json()
        self.assertEqual(updated['running'], summary['running'] - 1)

    @patch('ops.docker_views._get_ssh_client_from_docker_host')
    @patch('ops.docker_views._ssh_exec')
    def test_summary_caches_small_allowlisted_fields_and_refresh_bypasses_cache(self, execute, connect):
        execute.return_value = (0, json.dumps({'ServerVersion': '27', 'MemTotal': 1234, 'NCPU': 4, 'RegistryConfig': {'secret': 'hidden'}}), '')
        url = f'/api/docker/hosts/{self.real.pk}/summary/'
        first = self.client.get(url)
        self.assertEqual(first.status_code, 200)
        self.assertNotIn('RegistryConfig', first.data)
        self.client.get(url)
        self.assertEqual(execute.call_count, 1)
        self.client.get(url, {'refresh': '1'})
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(connect.return_value.close.call_count, 2)

    @patch('ops.docker_views._get_ssh_client_from_docker_host')
    @patch('ops.docker_views._ssh_exec')
    def test_list_cache_invalidated_after_mutation_and_explicit_refresh(self, execute, connect):
        execute.return_value = (0, '{"ID":"abc","Names":"web","State":"running"}\n', '')
        self.client.get('/api/docker/containers/', {'host_id': self.real.pk})
        self.client.get('/api/docker/containers/', {'host_id': self.real.pk})
        self.assertEqual(execute.call_count, 1)
        self.client.post('/api/docker/containers/abc/action/', {'host_id': self.real.pk, 'action': 'stop'})
        self.client.get('/api/docker/containers/', {'host_id': self.real.pk})
        self.assertEqual(execute.call_count, 3)
        self.client.get('/api/docker/containers/', {'host_id': self.real.pk, 'refresh': '1'})
        self.assertEqual(execute.call_count, 4)

    def test_readonly_can_view_new_endpoints_but_cannot_mutate(self):
        self.client.force_authenticate(self.viewer)
        images = self.client.get('/api/docker/images/', {'host_id': self.host.pk}).data
        self.assertEqual(self.client.get(f'/api/docker/images/{images[0]["id"]}/inspect/', {'host_id': self.host.pk}).status_code, 200)
        self.assertEqual(self.client.get(f'/api/docker/hosts/{self.host.pk}/summary/').status_code, 200)
        self.assertEqual(self.client.post('/api/docker/images/prune/', {'host_id': self.host.pk}).status_code, 403)
        self.assertEqual(self.client.post('/api/docker/containers/abc/action/', {'host_id': self.host.pk, 'action': 'stop'}).status_code, 403)

    def test_invalid_host_and_option_identifiers_do_not_reach_ssh(self):
        with patch('ops.docker_views._get_ssh_client_from_docker_host') as connect:
            self.assertEqual(self.client.get('/api/docker/containers/', {'host_id': 'invalid'}).status_code, 404)
            self.assertEqual(self.client.get('/api/docker/containers/--help/inspect/', {'host_id': self.real.pk}).status_code, 400)
            self.assertEqual(self.client.delete('/api/docker/images/remove/', {'host_id': self.real.pk, 'image_ids': ['--help']}, format='json').status_code, 400)
            connect.assert_not_called()

    @patch('ops.docker_views._get_ssh_client_from_docker_host')
    @patch('ops.docker_views._ssh_exec', side_effect=TimeoutError('timeout'))
    def test_ssh_client_closed_on_command_failure(self, execute, connect):
        response = self.client.get('/api/docker/containers/', {'host_id': self.real.pk})
        self.assertEqual(response.status_code, 400)
        connect.return_value.close.assert_called_once()

    @patch('ops.docker_views.paramiko.SSHClient')
    def test_failed_ssh_handshake_closes_client(self, client_class):
        client_class.return_value.connect.side_effect = TimeoutError('handshake')
        with self.assertRaises(TimeoutError):
            _get_ssh_client_from_docker_host(self.real)
        client_class.return_value.close.assert_called_once()

    def test_large_output_is_drained_before_exit_status(self):
        channel = MagicMock()
        chunks = deque([b'x' * 65536 for _ in range(48)])
        channel.recv_ready.side_effect = lambda: bool(chunks)
        channel.recv.side_effect = lambda size: chunks.popleft()
        channel.recv_stderr_ready.return_value = False
        channel.exit_status_ready.return_value = True
        channel.recv_exit_status.side_effect = lambda: self.assertFalse(chunks) or 0
        client = MagicMock()
        client.get_transport.return_value.open_session.return_value = channel
        code, output, error = _ssh_exec(client, 'docker inspect abc')
        self.assertEqual(code, 0)
        self.assertEqual(len(output), 3 * 1024 * 1024)
        channel.close.assert_called_once()

    def test_output_limit_closes_channel_and_client(self):
        channel = MagicMock()
        channel.recv_ready.return_value = True
        channel.recv.return_value = b'x' * 65536
        channel.recv_stderr_ready.return_value = False
        client = MagicMock()
        client.get_transport.return_value.open_session.return_value = channel
        with patch('ops.docker_views._get_ssh_client_from_docker_host', return_value=client):
            with self.assertRaisesRegex(RuntimeError, '8 MB'):
                _run_docker(self.real, 'docker images')
        channel.close.assert_called_once()
        client.close.assert_called_once()

    def test_logs_browse_all_history_and_reject_cross_user_or_host_cursor(self):
        container = self.client.get('/api/docker/containers/', {'host_id': self.host.pk}).data[0]
        url = f'/api/docker/containers/{container["id"]}/log_page/'
        with tempfile.TemporaryDirectory() as folder, patch('ops.k8s_logs.SNAPSHOT_ROOT', Path(folder)):
            initial = self.client.get(url, {'host_id': self.host.pk}).json()
            self.assertEqual(len(initial['logs'].splitlines()), 500)
            cursor = initial['before']
            all_content = initial['logs']
            count = 0
            while cursor:
                result = self.client.get(url, {'host_id': self.host.pk, 'direction': 'older', 'cursor': cursor})
                self.assertEqual(result.status_code, 200, result.data)
                page = result.json()
                self.assertLessEqual(len(page['logs'].encode()), 512 * 1024)
                all_content = page['logs'] + all_content
                cursor = page['before']
                count += 1
                self.assertLess(count, 10)
            self.assertIn('request=0001', all_content)
            self.assertEqual(all_content.count('request=0001'), 1)
            self.assertEqual(all_content.count('request=2400'), 1)
            self.client.force_authenticate(self.viewer)
            self.assertEqual(self.client.get(url, {'host_id': self.host.pk, 'direction': 'older', 'cursor': initial['before']}).status_code, 410)
            self.client.force_authenticate(self.admin)
            self.assertEqual(self.client.get(url, {'host_id': self.real.pk, 'direction': 'older', 'cursor': initial['before']}).status_code, 410)

    def test_log_pagination_validation_preserves_client_error(self):
        container = self.client.get('/api/docker/containers/', {'host_id': self.host.pk}).data[0]
        url = f'/api/docker/containers/{container["id"]}/log_page/'
        for params in ({'page_size': 1001}, {'direction': 'invalid'}, {'page_size': 'invalid'}):
            response = self.client.get(url, {'host_id': self.host.pk, **params})
            self.assertEqual(response.status_code, 400, response.data)

    def consumer(self, user, container_id, shell='auto'):
        token, created = Token.objects.get_or_create(user=user)
        consumer = DockerExecConsumer()
        consumer.scope = {'url_route': {'kwargs': {'host_id': self.host.pk}}, 'query_string': f'token={token.key}&container_id={container_id}&shell={shell}'.encode()}
        consumer.accept, consumer.close, consumer.send = MagicMock(), MagicMock(), MagicMock()
        return consumer

    def test_terminal_requires_separate_execute_permission(self):
        consumer = self.consumer(self.viewer, 'abc')
        consumer.connect()
        consumer.close.assert_called_with(code=4403)
        consumer.accept.assert_not_called()
        role = Role.objects.create(code='docker-manager-test', name='Docker manager')
        role.permissions.set(PermissionDefinition.objects.filter(code__in=['ops.docker.view', 'ops.docker.manage']))
        role.users.add(self.viewer)
        consumer = self.consumer(self.viewer, 'abc')
        consumer.connect()
        consumer.close.assert_called_with(code=4403)

    def test_terminal_rejects_invalid_shell_and_stopped_container(self):
        consumer = self.consumer(self.admin, 'abc', '/bin/sh;id')
        consumer.connect()
        consumer.close.assert_called_with(code=4400)
        consumer.accept.assert_not_called()
        container = next(item for item in self.client.get('/api/docker/containers/', {'host_id': self.host.pk}).data if item['state'] != 'running')
        consumer = self.consumer(self.admin, container['id'])
        consumer.connect()
        messages = [json.loads(call.kwargs['text_data']) for call in consumer.send.call_args_list]
        self.assertIn('容器不存在或未运行', messages[0]['message'])

    def test_terminal_demo_connects_and_audits_without_ssh(self):
        container = self.client.get('/api/docker/containers/', {'host_id': self.host.pk}).data[0]
        consumer = self.consumer(self.admin, container['id'])
        with patch('ops.docker_exec_consumer._get_ssh_client_from_docker_host') as connect:
            consumer.connect()
            consumer.receive(text_data=json.dumps({'type': 'input', 'data': 'pwd\r'}))
            connect.assert_not_called()
        messages = [json.loads(call.kwargs['text_data']) for call in consumer.send.call_args_list]
        self.assertTrue(any(item['type'] == 'connected' for item in messages))
        self.assertTrue(any('/app' in item.get('data', '') for item in messages))
        from eventwall.models import EventRecord
        self.assertTrue(EventRecord.objects.filter(action='docker_exec', actor_username=self.admin.username).exists())

    @patch('ops.docker_exec_consumer.threading.Thread')
    @patch('ops.docker_exec_consumer._run_docker', return_value=(0, 'true\n', ''))
    @patch('ops.docker_exec_consumer._get_ssh_client_from_docker_host')
    def test_real_terminal_uses_container_pty_and_closes_all_resources(self, connect, execute, thread):
        consumer = self.consumer(self.admin, 'abc123')
        consumer.scope['url_route']['kwargs']['host_id'] = self.real.pk
        channel = connect.return_value.get_transport.return_value.open_session.return_value
        consumer.connect()
        channel.get_pty.assert_called_once()
        command = channel.exec_command.call_args.args[0]
        self.assertIn('docker exec -it abc123 /bin/sh -c', command)
        self.assertIn('SXDEVOPS_READY_', command)
        self.assertFalse(any(json.loads(call.kwargs['text_data'])['type'] == 'connected' for call in consumer.send.call_args_list))
        consumer.receive(text_data=json.dumps({'type': 'resize', 'cols': 9999, 'rows': -5}))
        channel.resize_pty.assert_called_with(width=500, height=5)
        consumer.disconnect(1000)
        channel.close.assert_called_once()
        connect.return_value.close.assert_called_once()
