import uuid
import time
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from rbac.models import PermissionDefinition, Role
from .models import AIOpsChatJob, AIOpsChatMessage, AIOpsChatSession, AIOpsGraphNodeRun, AIOpsModelInvocation, AIOpsToolInvocation


class AIOpsAuditExecutionTests(TestCase):
    url = '/api/aiops/admin/audit/executions/'

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='execution-auditor', password='test')
        permission, _ = PermissionDefinition.objects.get_or_create(
            code='aiops.audit.view', defaults={'name': '审计查看', 'category': 'aiops'},
        )
        role = Role.objects.create(code='execution-auditor', name='执行审计员')
        role.permissions.add(permission)
        role.users.add(self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.session = AIOpsChatSession.objects.create(user=self.user, title='电商测试环境')
        self.message = self.make_message('thread-one')
        self.assistant = AIOpsChatMessage.objects.create(
            session=self.session, role='assistant', content='完成', metadata={'langgraph_thread_id': 'thread-one'},
        )

    def make_message(self, thread_id, **metadata):
        return AIOpsChatMessage.objects.create(
            session=self.session, role='user', content='查询电商测试环境指标',
            metadata={'langgraph_thread_id': thread_id, **metadata},
        )

    def make_run(self, node, status='completed', **fields):
        return AIOpsGraphNodeRun.objects.create(message=self.message, thread_id='thread-one', node=node, status=status, **fields)

    def test_requires_audit_permission_and_authentication(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, [401, 403])
        stranger = get_user_model().objects.create_user(username='no-audit')
        self.client.force_authenticate(stranger)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(f'{self.url}{self.message.id}/').status_code, 403)

    def test_execution_endpoints_are_read_only(self):
        self.assertEqual(self.client.post(self.url, {}).status_code, 405)
        self.assertEqual(self.client.patch(f'{self.url}{self.message.id}/', {}).status_code, 405)
        self.assertEqual(self.client.delete(f'{self.url}{self.message.id}/').status_code, 405)

    def test_completed_nodes_do_not_record_default_failure_text(self):
        from .langgraph_execution import finish_run
        run = self.make_run('query', 'running')
        finish_run(run, time.monotonic(), 'completed')
        run.refresh_from_db()
        self.assertEqual(run.error, '')

    @mock.patch('aiops.langgraph_pilot.get_langgraph_chat_graph')
    def test_list_aggregates_retries_and_uses_latest_graph_status_without_reading_checkpoints(self, graph):
        self.make_run('__graph__', 'failed', duration_ms=200)
        self.make_run('query', 'failed', duration_ms=40)
        self.make_run('__graph__', duration_ms=300)
        self.make_run('query', duration_ms=80, retry_count=1)
        self.message.metadata['langgraph_resume_count'] = 1
        self.message.save(update_fields=['metadata'])
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        row = response.data['results'][0]
        self.assertEqual(row['status'], 'completed')
        self.assertEqual(row['node_count'], 2)
        self.assertEqual(row['failed_node_count'], 1)
        self.assertEqual(row['graph_duration_ms'], 500)
        self.assertEqual(row['node_duration_ms'], 120)
        self.assertEqual(row['retry_count'], 1)
        self.assertEqual(row['resume_count'], 1)
        graph.assert_not_called()

    def test_job_status_takes_precedence_over_previous_attempt(self):
        self.make_run('__graph__', 'failed')
        job = AIOpsChatJob.objects.create(user_message=self.message, assistant_message=self.assistant, thread_id='thread-one')
        for status in ['queued', 'running', 'failed', 'completed']:
            job.status = status
            job.save(update_fields=['status'])
            response = self.client.get(self.url, {'status': status})
            self.assertEqual(response.data['count'], 1)
            self.assertEqual(response.data['results'][0]['status'], status)

    def test_assistant_status_fallback_is_text_and_can_be_filtered(self):
        self.assistant.metadata['langgraph_resume_status'] = 'completed'
        self.assistant.save(update_fields=['metadata'])
        response = self.client.get(self.url, {'status': 'completed'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['status'], 'completed')

    def test_cleaned_synchronous_execution_remains_completed(self):
        self.message.metadata['langgraph_checkpoint_expired'] = True
        self.message.save(update_fields=['metadata'])
        response = self.client.get(self.url, {'status': 'completed'})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['status'], 'completed')

    def test_list_filters_paginates_and_excludes_mirrors_and_non_graph_messages(self):
        self.make_message('thread-two')
        AIOpsChatMessage.objects.create(session=self.session, role='user', content='old')
        mirror = AIOpsChatSession.objects.create(user=self.user, title='镜像', mirror_source=self.session)
        AIOpsChatMessage.objects.create(session=mirror, role='user', metadata={'langgraph_thread_id': 'mirror'})
        response = self.client.get(self.url, {'page_size': 1, 'page': 2})
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], self.message.id)
        for params in [
            {'q': 'thread-one'}, {'message_id': self.message.id},
            {'session_id': self.session.id, 'username': self.user.username, 'q': '电商', 'start': timezone.now().date().isoformat()},
        ]:
            response = self.client.get(self.url, params)
            self.assertEqual(response.status_code, 200)
            self.assertGreater(response.data['count'], 0)
        self.assertEqual(self.client.get(self.url, {'end': '2000-01-01'}).data['count'], 0)
        self.assertEqual(self.client.get(self.url, {'session_id': 'invalid'}).data['count'], 0)

    @mock.patch('aiops.langgraph_pilot.get_langgraph_chat_graph')
    def test_detail_exposes_only_checkpoint_summary_and_redacts_errors(self, graph):
        graph.return_value.get_state.return_value = SimpleNamespace(
            values={'graph_version': 9, 'provider': {'api_key': 'hidden-key'}, 'result': 'hidden-result'},
            next=('query',), created_at='2026-10-10T00:00:00Z',
        )
        self.make_run('query', 'failed', error='Bearer sensitive-token token=secret')
        token = uuid.uuid4()
        AIOpsChatJob.objects.create(
            user_message=self.message, assistant_message=self.assistant, thread_id='thread-one',
            status='running', attempt_count=2, claim_token=token,
            lease_until=timezone.now() - timedelta(seconds=10), error_message='token=worker-secret',
        )
        response = self.client.get(f'{self.url}{self.message.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['checkpoint']['next'], ['query'])
        self.assertEqual(response.data['checkpoint']['graph_version'], 9)
        self.assertTrue(response.data['job']['lease_expired'])
        self.assertEqual(response.data['job']['attempt_count'], 2)
        for secret in ['hidden-key', 'hidden-result', 'sensitive-token', 'worker-secret', str(token), 'claim_token']:
            self.assertNotIn(secret, response.content.decode())

    @mock.patch('aiops.langgraph_pilot.get_langgraph_chat_graph')
    def test_expired_and_cleanup_pending_executions_survive_without_checkpoint_access(self, graph):
        for flag, expected in [('langgraph_checkpoint_expired', 'expired'), ('langgraph_checkpoint_cleanup_pending', 'cleanup_pending')]:
            self.message.metadata = {'langgraph_thread_id': 'thread-one', flag: True}
            self.message.save(update_fields=['metadata'])
            self.assertEqual(self.client.get(self.url).data['count'], 1)
            response = self.client.get(f'{self.url}{self.message.id}/')
            self.assertEqual(response.data['checkpoint']['status'], expected)
        graph.assert_not_called()

    @mock.patch('aiops.langgraph_pilot.get_langgraph_chat_graph')
    def test_cleanup_pending_takes_precedence_when_expired_is_also_marked(self, graph):
        self.message.metadata.update({'langgraph_checkpoint_expired': True, 'langgraph_checkpoint_cleanup_pending': True})
        self.message.save(update_fields=['metadata'])
        response = self.client.get(f'{self.url}{self.message.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['checkpoint']['status'], 'cleanup_pending')
        graph.assert_not_called()

    @mock.patch('aiops.langgraph_pilot.get_langgraph_chat_graph')
    def test_checkpoint_missing_or_unavailable_does_not_break_detail(self, graph):
        graph.return_value.get_state.return_value = SimpleNamespace(values={})
        self.assertEqual(self.client.get(f'{self.url}{self.message.id}/').data['checkpoint']['status'], 'missing')
        graph.side_effect = RuntimeError('storage token=secret')
        response = self.client.get(f'{self.url}{self.message.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['checkpoint']['status'], 'unavailable')
        self.assertNotIn('secret', response.content.decode())

    def test_invocation_and_session_links_filter_exact_message_without_next_round(self):
        second = self.make_message('thread-two')
        for model, endpoint, fields in [
            (AIOpsToolInvocation, 'tool-invocations', {'tool_name': 'query_metrics'}),
            (AIOpsModelInvocation, 'model-invocations', {'username': self.user.username}),
        ]:
            wanted = model.objects.create(session=self.session, message=self.message, **fields)
            model.objects.create(session=self.session, message=second, **fields)
            response = self.client.get(f'/api/aiops/admin/audit/{endpoint}/', {'session_id': self.session.id, 'message_id': self.message.id})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row['id'] for row in response.data['results']], [wanted.id])
        response = self.client.get('/api/aiops/admin/audit/sessions/', {'session_id': self.session.id, 'message_id': self.message.id})
        self.assertEqual(response.data['count'], 1)

    def test_skill_and_action_links_follow_the_same_thread(self):
        second = self.make_message('thread-two')
        trace = {'skill_trace': {'items': [{'slug': 'test-skill', 'name': '测试技能', 'status': 'used'}]},
                 'action_trace': {'code': 'test-action', 'display_name': '测试动作', 'status': 'matched'}}
        self.assistant.metadata.update(trace)
        self.assistant.save(update_fields=['metadata'])
        AIOpsChatMessage.objects.create(session=self.session, role='assistant', metadata={
            'langgraph_thread_id': second.metadata['langgraph_thread_id'], **trace,
        })
        for endpoint in ['skill-traces', 'action-traces']:
            response = self.client.get(f'/api/aiops/admin/audit/{endpoint}/', {'message_id': self.message.id})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 1)
            self.assertEqual(response.data['results'][0]['message_id'], self.assistant.id)

    def test_detail_limits_node_rows_and_keeps_totals(self):
        AIOpsGraphNodeRun.objects.bulk_create([
            AIOpsGraphNodeRun(message=self.message, thread_id='thread-one', node='query', status='completed')
            for index in range(502)
        ])
        with mock.patch('aiops.langgraph_pilot.get_langgraph_chat_graph', side_effect=RuntimeError):
            response = self.client.get(f'{self.url}{self.message.id}/')
        self.assertTrue(response.data['nodes_truncated'])
        self.assertEqual(len(response.data['nodes']), 500)
        self.assertEqual(response.data['node_count'], 502)
