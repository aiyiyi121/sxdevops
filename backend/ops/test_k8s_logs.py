import tempfile
import json
import threading
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import MagicMock, patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from ops.k8s_exec_consumer import K8sExecConsumer
from ops.k8s_terminal_consumer import K8sClusterTerminalConsumer, pty
from ops.k8s_logs import LogSnapshotError, PAGE_BYTES, pod_log_page
from ops.models import K8sCluster
from rbac.models import K8sUserAccess, PermissionDefinition, Role
from rbac.services import ensure_builtin_rbac


class K8sLogPagingTests(SimpleTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root_patch = patch('ops.k8s_logs.SNAPSHOT_ROOT', Path(self.directory.name))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.scope = ['1', '2', 'production', 'pod', 'main', False]

    def loader(self, content):
        response = MagicMock()

        def load(tail_lines):
            data = (''.join(content.splitlines(keepends=True)[-tail_lines:]) if tail_lines else content).encode('utf-8')
            response.stream.side_effect = lambda amt: (data[offset:offset + amt] for offset in range(0, len(data), amt))
            return response

        loader = MagicMock(side_effect=load)
        loader.return_value = response
        return loader

    def test_reads_every_retained_line_in_both_directions_without_reloading_kubernetes(self):
        expected = ''.join(f'2026-10-20T00:00:00Z 第 {index} 行\n' for index in range(6500))
        loader = self.loader(expected)
        page = pod_log_page({}, self.scope, loader)
        self.assertEqual(len(page['logs'].splitlines()), 500)
        collected = page['logs']
        first_page = page
        while page['before']:
            page = pod_log_page({'direction': 'older', 'cursor': page['before']}, self.scope, loader)
            collected = page['logs'] + collected
            self.assertLessEqual(len(page['logs'].encode()), PAGE_BYTES)
        self.assertEqual(collected, expected)
        forward = page['logs']
        while page['after']:
            page = pod_log_page({'direction': 'newer', 'cursor': page['after']}, self.scope, loader)
            forward += page['logs']
        self.assertEqual(forward, expected)
        latest = pod_log_page({'cursor': first_page['snapshot'], 'direction': 'latest'}, self.scope, loader)
        self.assertEqual(latest['logs'], first_page['logs'])
        self.assertEqual(loader.call_count, 2)
        self.assertEqual(loader.return_value.close.call_count, 2)
        self.assertEqual(loader.return_value.release_conn.call_count, 2)

    def test_large_utf8_line_can_be_read_without_loss_or_unbounded_page(self):
        expected = '日志' * PAGE_BYTES + '\n结束\n'
        loader = self.loader(expected)
        page = pod_log_page({}, self.scope, loader)
        result = page['logs']
        while page['before']:
            page = pod_log_page({'direction': 'older', 'cursor': page['before']}, self.scope, loader)
            self.assertLessEqual(len(page['logs'].encode()), PAGE_BYTES)
            self.assertNotIn('\ufffd', page['logs'])
            result = page['logs'] + result
        self.assertEqual(result, expected)

    def test_cursor_is_bound_to_user_namespace_container_and_previous_instance(self):
        loader = self.loader('line\n' * 700)
        cursor = pod_log_page({}, self.scope, loader)['before']
        for position, value in [(0, 'another-user'), (1, 'another-cluster'), (2, 'other-ns'), (3, 'other-pod'), (4, 'sidecar'), (5, True)]:
            other_scope = self.scope.copy()
            other_scope[position] = value
            with self.assertRaises(LogSnapshotError) as failure:
                pod_log_page({'cursor': cursor}, other_scope, loader)
            self.assertEqual(failure.exception.status_code, 410)
        with self.assertRaises(LogSnapshotError):
            pod_log_page({'cursor': cursor + 'tampered'}, self.scope, loader)

    def test_bad_page_size_is_rejected_before_streaming(self):
        loader = self.loader('line\n')
        for size in ['bad', '-1', '1001']:
            with self.assertRaises(ValidationError):
                pod_log_page({'page_size': size}, self.scope, loader)
        loader.assert_not_called()

    def test_failed_stream_removes_partial_snapshot_and_releases_connection(self):
        loader = self.loader('line\n')
        loader.side_effect = None
        loader.return_value.stream.side_effect = TimeoutError('read timeout')
        with self.assertRaises(TimeoutError):
            pod_log_page({}, self.scope, loader)
        self.assertEqual(list(Path(self.directory.name).glob('*.log')), [])
        loader.return_value.close.assert_called_once()
        loader.return_value.release_conn.assert_called_once()

    def test_initial_read_only_fetches_tail_then_collects_history_on_demand(self):
        expected = ''.join(f'{index}\n' for index in range(3000))
        loader = self.loader(expected)
        page = pod_log_page({}, self.scope, loader)
        loader.assert_called_once_with(500)
        self.assertEqual(page['logs'], ''.join(expected.splitlines(keepends=True)[-500:]))
        older = pod_log_page({'cursor': page['before'], 'direction': 'older'}, self.scope, loader)
        self.assertEqual(loader.call_args.args, (None,))
        self.assertEqual(older['logs'], ''.join(expected.splitlines(keepends=True)[-1000:-500]))

    def test_exact_tail_without_final_newline_still_allows_history(self):
        loader = self.loader('\n'.join(str(index) for index in range(600)))
        page = pod_log_page({}, self.scope, loader)
        self.assertTrue(page['before'])
        older = pod_log_page({'cursor': page['before'], 'direction': 'older'}, self.scope, loader)
        self.assertTrue(older['logs'].startswith('0\n'))

    def test_shell_exit_closes_browser_websocket(self):
        consumer = K8sExecConsumer()
        consumer._reading = True
        consumer.exec_stream = MagicMock()
        consumer.exec_stream.is_open.return_value = False
        consumer.close = MagicMock()
        consumer._read_exec_output()
        consumer.close.assert_called_once()
        consumer.exec_stream.close.assert_called_once()

    @override_settings(CHANNEL_LAYERS={'default': {'BACKEND': 'unavailable.redis.backend'}})
    def test_point_to_point_terminals_keep_working_without_channel_redis(self):
        async def exercise(consumer_type):
            class TerminalProbe(consumer_type):
                def connect(self):
                    self.accept()

                def receive(self, text_data=None, bytes_data=None):
                    self.send(text_data=text_data)

                def disconnect(self, close_code):
                    pass

            connection = WebsocketCommunicator(TerminalProbe.as_asgi(), '/')
            connected, _ = await connection.connect()
            self.assertTrue(connected)
            await connection.send_to(text_data='terminal input')
            self.assertEqual(await connection.receive_from(), 'terminal input')
            await connection.disconnect()

        for consumer_type in (K8sExecConsumer, K8sClusterTerminalConsumer):
            async_to_sync(exercise)(consumer_type)


class K8sLogAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()
        cls.user = get_user_model().objects.create_user('log-reader')
        role = Role.objects.create(code='k8s-log-reader', name='Log reader')
        role.permissions.set(PermissionDefinition.objects.filter(code='ops.k8s.view'))
        role.users.add(cls.user)
        cls.cluster = K8sCluster.objects.create(name='demo-log', kubeconfig='demo', status='connected')
        policy = K8sUserAccess.objects.create(user=cls.user)
        policy.grants.create(cluster=cls.cluster, role='viewer', namespaces=['production'])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root_patch = patch('ops.k8s_logs.SNAPSHOT_ROOT', Path(self.directory.name))
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f'/api/k8s/clusters/{self.cluster.pk}/pod_logs/'

    def test_reader_can_scroll_past_first_page_only_in_authorized_namespace(self):
        params = {'paged': '1', 'pod_name': 'api-demo', 'namespace': 'production', 'container': 'main'}
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        self.assertIn('[06000]', response.data['logs'])
        cursor = response.data['before']
        older = self.client.get(self.url, {**params, 'cursor': cursor, 'direction': 'older'})
        self.assertEqual(older.status_code, 200)
        self.assertNotEqual(older.data['logs'], response.data['logs'])
        denied = self.client.get(self.url, {**params, 'namespace': 'private', 'cursor': cursor})
        self.assertEqual(denied.status_code, 403)
        policy = K8sUserAccess.objects.get(user=self.user)
        policy.grants.all().delete()
        self.assertIn(self.client.get(self.url, {**params, 'cursor': cursor}).status_code, [403, 404])

    def test_invalid_paging_returns_validation_error(self):
        response = self.client.get(self.url, {'paged': '1', 'pod_name': 'api', 'namespace': 'production', 'page_size': 'bad'})
        self.assertEqual(response.status_code, 400)

    def test_paged_logs_preserve_container_text_without_extra_timestamps(self):
        content = '2026-10-21 09:15:00 INFO 原始日志\n没有时间的原始内容\n'
        response_stream = MagicMock()
        response_stream.stream.return_value = [content.encode('utf-8')]
        k8s = MagicMock()
        k8s.CoreV1Api.return_value.read_namespaced_pod_log.return_value = response_stream
        with patch('ops.k8s_views._is_demo', return_value=False), patch('ops.k8s_views._get_k8s_client', return_value=k8s):
            response = self.client.get(self.url, {
                'paged': '1', 'pod_name': 'api', 'namespace': 'production', 'container': 'main',
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['logs'], content)
        self.assertIs(k8s.CoreV1Api.return_value.read_namespaced_pod_log.call_args.kwargs['timestamps'], False)


@skipUnless(pty is not None, '需要 Linux PTY')
class K8sClusterShellTests(SimpleTestCase):
    @skipUnless(shutil.which('bash') and shutil.which('kubectl'), '需要 Bash 和 kubectl')
    def test_tab_uses_kubectl_native_completion_in_interactive_shell(self):
        consumer = K8sClusterTerminalConsumer()
        consumer.cluster = SimpleNamespace(name='demo-completion', kubeconfig='demo')
        received = []
        ready = threading.Event()
        completed = threading.Event()

        def receive(text_data):
            payload = json.loads(text_data)
            received.append(payload.get('data', ''))
            output = ''.join(received)
            if 'SX_READY_DONE' in output:
                ready.set()
            if 'Client Version:' in output:
                completed.set()

        consumer.send = receive
        consumer.close = MagicMock()
        self.addCleanup(consumer.disconnect, 1000)
        consumer._start_shell()
        consumer.receive(json.dumps({'type': 'input', 'data': 'printf "SX_READY_%s\\n" DONE\r'}))
        self.assertTrue(ready.wait(8), 'Shell should become ready')
        consumer.receive(json.dumps({'type': 'input', 'data': 'kubec\tver\t--client\r'}))
        self.assertTrue(completed.wait(8), ''.join(received))
        self.assertNotIn('command not found', ''.join(received))

    def test_shell_has_controlling_tty_and_notifies_browser_on_exit(self):
        consumer = K8sClusterTerminalConsumer()
        consumer.cluster = SimpleNamespace(name='demo-shell', kubeconfig='demo')
        received = []
        finished = threading.Event()
        consumer.send = lambda text_data: received.append(json.loads(text_data))
        consumer.close = lambda **kwargs: finished.set()
        self.addCleanup(consumer.disconnect, 1000)
        consumer._start_shell()
        consumer.receive(json.dumps({'type': 'input', 'data': 'stty size; printf "\\344\\270\\255\\346\\226\\207"; exit\r'}))
        self.assertTrue(finished.wait(5), 'Shell exit should close the WebSocket')
        output = ''.join(item.get('data', '') for item in received)
        self.assertIn('36 120', output)
        self.assertIn('中文', output)
        self.assertNotIn('no job control', output)
        self.assertEqual(received[0]['type'], 'connected')
