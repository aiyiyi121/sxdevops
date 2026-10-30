import tempfile
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from eventwall.models import EventRecord
from ops.models import Alert, Host, HostTask, HostTaskExecution, MetricDataSource
from rbac.models import PermissionDefinition, Role

from . import langgraph_pilot, remediation
from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsGraphNodeRun, AIOpsKnowledgeEnvironment, AIOpsPendingAction, AIOpsRemediationVerification
from .remediation_demo import DEMO_CASES, evaluate_remediation_demo, seed_remediation_demo


class RemediationVerificationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('verification-owner', password='test')
        self.environment = AIOpsKnowledgeEnvironment.objects.create(name='验证测试环境', alert_environments=['verification-test'])
        self.session = AIOpsChatSession.objects.create(user=self.user)
        self.message = AIOpsChatMessage.objects.create(session=self.session, role='assistant', content='任务草稿')
        self.action = AIOpsPendingAction.objects.create(
            session=self.session, message=self.message, action_type='execute_host_task', title='恢复服务',
        )
        self.base = timezone.now() - timedelta(minutes=5)
        self.alert = Alert.objects.create(
            title='order-service 错误率', message='错误率超过阈值', source='verification-test',
            environment='verification-test', service='order-service', fingerprint='order-error-rate',
            status='active', starts_at=self.base - timedelta(minutes=5), last_received_at=self.base,
        )
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        checkpoint = mock.patch.dict('os.environ', {
            'AIOPS_LANGGRAPH_CHECKPOINT_BACKEND': 'sqlite',
            'AIOPS_LANGGRAPH_CHECKPOINT_PATH': self.directory.name + '/verification.sqlite3',
        })
        checkpoint.start()
        self.addCleanup(checkpoint.stop)
        langgraph_pilot.close_langgraph_resources()
        self.addCleanup(langgraph_pilot.close_langgraph_resources)

    def configure(self, observation_seconds=0, health_policy=None):
        with mock.patch('aiops.remediation.timezone.now', return_value=self.base):
            return remediation.configure_verification(self.action, self.user, self.environment.id, self.alert.id, observation_seconds, health_policy)

    def task(self, status='success', health_policy=None):
        verification = self.configure(60 if health_policy else 0, health_policy)
        self.action.status = 'executed'
        self.action.confirmed_by = self.user.username
        self.action.confirmed_at = self.base + timedelta(seconds=1)
        self.action.save(update_fields=['status', 'confirmed_by', 'confirmed_at'])
        task = HostTask.objects.create(
            name='恢复服务', task_type='run_command', trigger_source='aiops', created_by=self.user.username,
            status=status, target_count=1, success_count=int(status == 'success'), failed_count=int(status != 'success'),
            started_at=self.base + timedelta(seconds=10), finished_at=self.base + timedelta(seconds=20),
            source_context={'source': 'aiops', 'pending_action_id': self.action.id},
        )
        HostTaskExecution.objects.create(task=task, status=status, started_at=task.started_at, finished_at=task.finished_at)
        remediation.bind_verification_task(self.action, task, self.user)
        verification.refresh_from_db()
        return verification, task

    def recover_alert(self):
        self.alert.status = 'resolved'
        self.alert.ends_at = self.base + timedelta(seconds=30)
        self.alert.last_received_at = self.base + timedelta(seconds=30)
        self.alert.save(update_fields=['status', 'ends_at', 'last_received_at'])

    def run_verification(self):
        claimed = remediation.claim_verification()
        self.assertIsNotNone(claimed)
        remediation.process_verification(claimed)
        claimed.refresh_from_db()
        return claimed

    def test_successful_task_requires_same_alert_recovery_event(self):
        verification, task = self.task()
        self.recover_alert()
        with mock.patch('ops.host_tasks.start_host_task') as execute:
            result = self.run_verification()
        self.assertEqual(result.status, 'passed')
        self.assertEqual(result.evidence['alert']['id'], self.alert.id)
        self.assertEqual(result.evidence['task']['id'], task.id)
        self.assertIn('不证明', result.summary)
        self.assertEqual(AIOpsGraphNodeRun.objects.filter(thread_id=verification.thread_id).count(), 4)
        self.assertIsNone(remediation.claim_verification())
        execute.assert_not_called()

    def test_successful_command_with_active_alert_does_not_pass(self):
        self.task()
        result = self.run_verification()
        self.assertEqual(result.status, 'failed')
        self.assertIn('仍活跃', result.summary)

    def health_policy(self, related_alert_ids=None):
        source = MetricDataSource.objects.create(name='verification-metrics', config={'query_url': 'https://metrics.example.test'})
        self.environment.metric_datasource_ids = [source.pk]
        self.environment.save(update_fields=['metric_datasource_ids'])
        return {'signals': [
            {'name': '错误率', 'datasource_id': source.pk, 'query': 'service_error_ratio{service="order-service"}', 'comparison': 'lte', 'threshold': 0.01, 'step_seconds': 15},
            {'name': '可用性', 'datasource_id': source.pk, 'query': 'service_up{service="order-service"}', 'comparison': 'eq', 'threshold': 1, 'step_seconds': 15},
        ], 'related_alert_ids': related_alert_ids or []}

    def metric_response(self, query, **kwargs):
        start, end, step = kwargs['start_time'], kwargs['end_time'], kwargs['step']
        value = 1 if query.startswith('service_up') else 0.001
        samples = [[start.timestamp() + offset, str(value)] for offset in range(0, int((end - start).total_seconds()) + 1, step)]
        return {'resultType': 'matrix', 'result': [{'metric': {'service': 'order-service'}, 'values': samples}]}

    @mock.patch('aiops.verification_health.execute_promql_query')
    def test_sustained_multi_signal_health_records_before_after_evidence(self, query):
        query.side_effect = self.metric_response
        policy = self.health_policy()
        verification, task = self.task(health_policy=policy)
        self.recover_alert()
        result = self.run_verification()
        self.assertEqual(result.status, 'passed', result.summary)
        self.assertEqual(len(result.baseline['health_policy']['baseline_signals']), 2)
        self.assertEqual(len(result.evidence['health']['signals']), 2)
        self.assertFalse(result.evidence['causality']['causal_proof'])
        self.assertEqual(result.evidence['health']['window_start'], self.alert.ends_at.isoformat())
        self.assertEqual(query.call_count, 4)

    @mock.patch('aiops.verification_health.execute_promql_query')
    def test_missing_nan_and_unhealthy_samples_never_pass(self, query):
        query.side_effect = self.metric_response
        self.task(health_policy=self.health_policy())
        self.recover_alert()
        for defect, expected in [('gap', 'inconclusive'), ('nan', 'inconclusive'), ('threshold', 'failed'), ('empty', 'inconclusive')]:
            with self.subTest(defect=defect):
                def response(expression, **kwargs):
                    payload = self.metric_response(expression, **kwargs)
                    values = payload['result'][0]['values']
                    if defect == 'gap':
                        values.pop(1)
                    elif defect == 'nan':
                        values[1][1] = 'NaN'
                    elif defect == 'threshold':
                        values[1][1] = '10'
                    else:
                        payload['result'] = []
                    return payload
                query.side_effect = response
                verification = AIOpsRemediationVerification.objects.get(action=self.action)
                state = {'verification_id': verification.pk, **remediation._task_node({'verification_id': verification.pk}),
                         **remediation._alert_node({'verification_id': verification.pk})}
                self.assertEqual(remediation._verdict_node(state)['result']['status'], expected)

    @mock.patch('aiops.verification_health.execute_promql_query')
    def test_active_related_alert_prevents_health_success(self, query):
        query.side_effect = self.metric_response
        related = Alert.objects.create(title='关联可用性告警', environment='verification-test', status='active', fingerprint='availability')
        self.task(health_policy=self.health_policy([related.pk]))
        self.recover_alert()
        self.assertEqual(self.run_verification().status, 'failed')

    def test_related_alert_requires_valid_recovery_event(self):
        related = Alert.objects.create(title='关联告警', environment='verification-test', status='active', fingerprint='related')
        self.task(health_policy={'related_alert_ids': [related.pk]})
        self.recover_alert()
        related.status = 'resolved'
        related.save(update_fields=['status'])
        result = self.run_verification()
        self.assertEqual(result.status, 'inconclusive')
        self.assertIn('恢复时间', result.summary)

    @mock.patch('aiops.verification_health.execute_promql_query')
    def test_revoked_metric_permission_blocks_existing_health_evidence(self, query):
        query.side_effect = self.metric_response
        self.task(health_policy=self.health_policy())
        self.recover_alert()
        self.user.is_superuser = False
        self.user.save(update_fields=['is_superuser'])
        role = Role.objects.create(code='verification-observer', name='验证观察者')
        for code in remediation.VERIFICATION_PERMISSIONS:
            permission, _ = PermissionDefinition.objects.get_or_create(code=code, defaults={'name': code, 'category': 'aiops'})
            role.permissions.add(permission)
        role.users.add(self.user)
        result = self.run_verification()
        self.assertEqual(result.status, 'inconclusive')
        self.assertFalse(remediation.verification_details(result, self.user)['evidence'])
        self.assertEqual(query.call_count, 2)

    @mock.patch('aiops.verification_health.execute_promql_query')
    def test_health_observation_starts_after_recovery(self, query):
        query.side_effect = self.metric_response
        self.task(health_policy=self.health_policy())
        self.recover_alert()
        with mock.patch('aiops.remediation.timezone.now', return_value=self.base + timedelta(seconds=85)):
            self.assertIsNone(remediation.claim_verification())

    @mock.patch('aiops.verification_health.execute_promql_query')
    def test_datasource_rebinding_invalidates_health_evidence(self, query):
        query.side_effect = self.metric_response
        policy = self.health_policy()
        self.task(health_policy=policy)
        self.recover_alert()
        MetricDataSource.objects.filter(pk=policy['signals'][0]['datasource_id']).update(config={'query_url': 'https://changed.example.test'})
        self.assertEqual(self.run_verification().status, 'inconclusive')

    def test_health_policy_rejects_datasource_outside_environment(self):
        policy = self.health_policy()
        self.environment.metric_datasource_ids = []
        self.environment.save(update_fields=['metric_datasource_ids'])
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            self.configure(60, policy)

    @mock.patch('aiops.verification_health.execute_promql_query', side_effect=RuntimeError('sensitive upstream error'))
    def test_baseline_query_failure_is_redacted_and_not_saved(self, query):
        with self.assertRaisesRegex(ValueError, '无法读取'):
            self.configure(60, self.health_policy())
        self.assertFalse(AIOpsRemediationVerification.objects.filter(action=self.action).exists())

    def test_verification_audit_actions_fit_database_field(self):
        verification, task = self.task()
        self.recover_alert()
        self.assertEqual(self.run_verification().status, 'passed')
        events = list(EventRecord.objects.filter(
            resource_type='aiops_verification', resource_id=str(verification.id),
        ))
        self.assertEqual(len(events), 2)
        action_field = EventRecord._meta.get_field('action')
        for event in events:
            action_field.clean(event.action, event)

    def test_missing_alert_is_inconclusive(self):
        self.task()
        self.alert.delete()
        self.assertEqual(self.run_verification().status, 'inconclusive')

    def test_observation_window_and_running_task_are_not_claimed(self):
        verification, task = self.task()
        verification.observation_seconds = 600
        verification.save(update_fields=['observation_seconds'])
        self.assertIsNone(remediation.claim_verification())
        verification.observation_seconds = 0
        verification.save(update_fields=['observation_seconds'])
        task.status = 'running'
        task.save(update_fields=['status'])
        self.assertIsNone(remediation.claim_verification())

    def test_resume_reuses_checkpointed_task_node(self):
        verification, task = self.task()
        self.recover_alert()
        claimed = remediation.claim_verification()
        with mock.patch('aiops.remediation._alert_node', side_effect=remediation._alert_node) as alert:
            from .services import ChatJobLeaseLost
            alert.side_effect = ChatJobLeaseLost('模拟 worker 中断')
            remediation.process_verification(claimed)
        AIOpsRemediationVerification.objects.filter(pk=verification.id).update(lease_until=timezone.now() - timedelta(seconds=1))
        result = self.run_verification()
        self.assertEqual(result.status, 'passed')
        self.assertEqual(result.attempt_count, 2)
        self.assertEqual(AIOpsGraphNodeRun.objects.filter(thread_id=verification.thread_id, node='verification_task').count(), 1)

    def test_lease_takeover_prevents_old_worker_publication(self):
        verification, task = self.task()
        claimed = remediation.claim_verification()
        replacement = uuid.uuid4()
        original = remediation._task_node

        def take_over(state, config=None):
            AIOpsRemediationVerification.objects.filter(pk=verification.pk).update(claim_token=replacement)
            return original(state, config)

        with mock.patch('aiops.remediation._task_node', side_effect=take_over):
            remediation.process_verification(claimed)
        verification.refresh_from_db()
        self.assertEqual(verification.status, 'running')
        self.assertEqual(verification.claim_token, replacement)
        self.assertEqual(verification.evidence, {})

    def test_permissions_are_rechecked_before_reading_and_publication(self):
        self.task()
        self.recover_alert()
        original = remediation._alert_node

        def revoke(state, config=None):
            evidence = original(state, config)
            get_user_model().objects.filter(pk=self.user.id).update(is_active=False)
            return evidence

        with mock.patch('aiops.remediation._alert_node', side_effect=revoke):
            result = self.run_verification()
        self.assertEqual(result.status, 'inconclusive')
        self.assertEqual(result.evidence, {'task': {}, 'alert': {}, 'health': {}, 'causality': {}})

    def test_environment_mapping_changes_do_not_expand_scope(self):
        self.task()
        self.environment.alert_environments.append('other-environment')
        self.environment.save(update_fields=['alert_environments'])
        self.assertEqual(self.run_verification().status, 'inconclusive')

    def test_baseline_is_idempotent_and_must_precede_task(self):
        first = self.configure()
        self.assertEqual(self.configure().id, first.id)
        self.action.result_payload = {'materialized_in_task_center': True}
        self.action.save(update_fields=['result_payload'])
        with self.assertRaises(ValueError):
            self.configure()

    def test_wrong_environment_and_unconfirmed_task_are_rejected(self):
        self.alert.environment = 'other-environment'
        self.alert.save(update_fields=['environment'])
        with self.assertRaises(ValueError):
            self.configure()
        self.alert.environment = 'verification-test'
        self.alert.save(update_fields=['environment'])
        verification = self.configure()
        task = HostTask.objects.create(name='未经确认', task_type='run_command', created_by=self.user.username)
        remediation.bind_verification_task(self.action, task, self.user)
        verification.refresh_from_db()
        self.assertIsNone(verification.task_id)

    def test_demo_corpus_uses_graph_without_executing_resources_and_is_idempotent(self):
        with mock.patch('ops.host_tasks.start_host_task') as execute:
            seed_remediation_demo(self.user)
            result = evaluate_remediation_demo(self.user)
            seed_remediation_demo(self.user)
        self.assertEqual(result['matched'], len(DEMO_CASES))
        self.assertEqual(AIOpsRemediationVerification.objects.filter(is_demo=True).count(), len(DEMO_CASES))
        execute.assert_not_called()

    def test_worker_processes_verification_even_without_chat_jobs(self):
        self.task()
        self.recover_alert()
        with mock.patch('aiops.management.commands.run_aiops_chat_worker.claim_async_chat_job', return_value=None):
            call_command('run_aiops_chat_worker', once=True)
        self.assertEqual(AIOpsRemediationVerification.objects.get().status, 'passed')

    def test_retention_cleans_checkpoint_but_keeps_verdict(self):
        verification, task = self.task()
        self.recover_alert()
        result = self.run_verification()
        AIOpsRemediationVerification.objects.filter(pk=result.pk).update(finished_at=timezone.now() - timedelta(days=31))
        remediation.cleanup_verifications()
        result.refresh_from_db()
        self.assertEqual(result.status, 'passed')
        self.assertTrue(result.checkpoint_expired)
        self.assertFalse(remediation.get_verification_graph().get_state({'configurable': {'thread_id': result.thread_id}}).values)

    def test_api_requires_permissions_and_owner_and_does_not_accept_demo_flag(self):
        client = APIClient()
        url = f'/api/aiops/actions/{self.action.id}/verification/'
        self.assertIn(client.get(url).status_code, [401, 403])
        stranger = get_user_model().objects.create_user('verification-stranger')
        client.force_authenticate(stranger)
        self.assertEqual(client.post(url, {}).status_code, 403)
        permissions = []
        for code in remediation.VERIFICATION_PERMISSIONS:
            permission, _ = PermissionDefinition.objects.get_or_create(code=code, defaults={'name': code, 'category': 'aiops'})
            permissions.append(permission)
        role = Role.objects.create(code='verification-test-role', name='验证测试')
        role.permissions.set(permissions)
        role.users.add(stranger)
        self.assertEqual(client.get(url).status_code, 404)
        client.force_authenticate(self.user)
        response = client.post(url, {'environment_id': self.environment.id, 'alert_id': self.alert.id,
                                     'observation_seconds': 0, 'is_demo': True}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['verification']['is_demo'])
        self.assertNotIn('claim_token', response.data['verification'])
        role.users.add(self.user)
        client.force_authenticate(stranger)
        audit, _ = PermissionDefinition.objects.get_or_create(code='aiops.audit.view', defaults={'name': '审计', 'category': 'aiops'})
        role.permissions.add(audit)
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(client.post(url, {'environment_id': self.environment.id, 'alert_id': self.alert.id}, format='json').status_code, 403)

    def test_cancelled_action_finishes_waiting_verification(self):
        verification = self.configure()
        from .services import cancel_action
        cancel_action(self.action, self.user)
        verification.refresh_from_db()
        self.assertEqual(verification.status, 'inconclusive')
        self.assertIsNotNone(verification.finished_at)

    def test_task_center_binds_verification_before_starting_execution(self):
        verification = self.configure()
        self.action.status = 'executed'
        self.action.confirmed_by = self.user.username
        self.action.confirmed_at = self.base
        self.action.save(update_fields=['status', 'confirmed_by', 'confirmed_at'])
        host = Host.objects.create(hostname='verification-target', ip_address='192.0.2.10')
        client = APIClient()
        client.force_authenticate(self.user)

        def verify_binding(task, targets):
            verification.refresh_from_db()
            self.assertEqual(verification.task_id, task.id)

        with mock.patch('ops.views.start_host_task', side_effect=verify_binding) as execute:
            response = client.post('/api/host-tasks/', {
                'name': '验证任务衔接', 'task_type': 'run_command', 'host_ids': [host.id],
                'payload': {'command': 'true'}, 'trigger_source': 'aiops',
                'source_context': {'source': 'aiops', 'pending_action_id': self.action.id},
            }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        execute.assert_called_once()

    def test_deleted_task_does_not_leave_verification_waiting_forever(self):
        verification, task = self.task()
        self.action.result_payload = {'materialized_in_task_center': True}
        self.action.save(update_fields=['result_payload'])
        task.delete()
        self.assertIsNone(remediation.claim_verification())
        verification.refresh_from_db()
        self.assertEqual(verification.status, 'inconclusive')

    def test_completed_checkpoint_is_not_published_after_alert_changes(self):
        verification, task = self.task()
        self.recover_alert()
        result = self.run_verification()
        result.status = 'running'
        result.claim_token = uuid.uuid4()
        result.lease_until = timezone.now() + timedelta(seconds=120)
        result.evidence = {}
        result.save(update_fields=['status', 'claim_token', 'lease_until', 'evidence'])
        self.alert.status = 'active'
        self.alert.save(update_fields=['status'])
        remediation.process_verification(result)
        result.refresh_from_db()
        self.assertEqual(result.status, 'inconclusive')
        self.assertEqual(result.evidence, {'task': {}, 'alert': {}, 'health': {}, 'causality': {}})
