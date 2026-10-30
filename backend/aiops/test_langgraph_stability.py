import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from . import langgraph_pilot, services
from .audit_executions import execution_detail, execution_queryset
from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsGraphNodeRun, AIOpsModelInvocation, AIOpsModelProvider, AIOpsPendingAction


class FormatterEvidenceScopeTests(SimpleTestCase):
    def outputs(self, alerts=0, logs=0, **alert_counts):
        return [
            {'tool_name': 'query_alerts', 'tool_output': {'summary': {'count': alerts, **alert_counts}}},
            {'tool_name': 'query_logs', 'tool_output': {'summary': {'count': logs}}},
        ]

    def test_counts_and_missing_evidence_are_checked_per_subject(self):
        cases = [
            ('告警0条。面板返回1条指标序列，最新值80，31个采样点。', self.outputs(), False),
            ('告警0条；日志10条，可能与下游超时相关。', self.outputs(logs=10), False),
            ('发现10条告警。暂无日志样本。', self.outputs(alerts=10), False),
            ('告警1条，严重告警0条。工作负载异常3个。', self.outputs(alerts=1, critical=0), False),
            ('当前没有告警。', self.outputs(alerts=1), True),
            ('告警查询未命中。', self.outputs(alerts=1), True),
            ('发现1条相关告警。', self.outputs(), True),
            ('告警数量：1条。', self.outputs(), True),
            ('没有日志。', self.outputs(logs=10), True),
            ('日志0条。', self.outputs(logs=10), True),
            ('日志命中3条。', self.outputs(), True),
            ('发现3条日志。', self.outputs(), True),
            ('日志0条。建议查询最近10条日志以核对采集。', self.outputs(), False),
            ('没有严重告警。', self.outputs(alerts=1, critical=1), True),
            ('未确认告警0条。', self.outputs(alerts=1, active=1), True),
        ]
        for content, outputs, expected in cases:
            with self.subTest(content=content):
                self.assertEqual(services._content_conflicts_with_tool_facts(content, outputs), expected)

    def test_slo_profile_does_not_require_invented_incident_or_target(self):
        profile = services._detect_formatter_profile('分析电商测试环境最近30分钟的 SLO 风险', None, 'analysis')
        self.assertEqual(profile, 'slo')
        template = services._formatter_template_for_profile(profile)
        self.assertIn('没有明确 SLO 目标', template)
        self.assertNotIn('已定位到', template)
        self.assertEqual(services._detect_formatter_profile('分析 SLO 风险', {'name': '任务'}, 'action'), 'task')

    def test_slo_with_series_and_no_alerts_passes_validation(self):
        answer = '结论：成功率最新值80，目标未提供，尚不能判定 SLO 是否达标。\n依据：\n- 告警0条。\n- 面板返回1条指标序列，31个采样点。\n建议操作：\n- 核对统计口径与目标。\n可继续查看：监控看板、告警中心'
        self.assertEqual(services._formatter_repair_issue(answer, collected_tool_outputs=self.outputs(), profile='slo'), '')


class LangGraphStabilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username='stability-regression', password='test')
        self.session = AIOpsChatSession.objects.create(user=self.user)
        self.message = AIOpsChatMessage.objects.create(session=self.session, role='user', content='查看知识图谱')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        checkpoint = mock.patch.dict('os.environ', {
            'AIOPS_LANGGRAPH_CHECKPOINT_BACKEND': 'sqlite',
            'AIOPS_LANGGRAPH_CHECKPOINT_PATH': self.directory.name + '/stability.sqlite3',
        })
        checkpoint.start()
        self.addCleanup(checkpoint.stop)
        langgraph_pilot.close_langgraph_resources()
        self.addCleanup(langgraph_pilot.close_langgraph_resources)

    @mock.patch('aiops.langgraph_pilot.run_langgraph_chat', side_effect=langgraph_pilot.LangGraphPilotUnavailable('checkpoint unavailable'))
    @mock.patch('aiops.services._build_chat_result_legacy')
    def test_compatibility_result_and_audit_expose_degradation(self, legacy, graph):
        legacy.return_value = {'content': '证据回复', 'message_type': 'analysis', 'metadata': {'preserved': True}}
        emit = mock.Mock()
        result = services._build_chat_result(self.session, self.message, self.user, '查看知识图谱', analysis_only=True, progress_callback=emit)
        self.assertTrue(result['metadata']['orchestration_degraded'])
        self.assertEqual(result['metadata']['orchestration_engine'], 'legacy')
        self.assertTrue(result['metadata']['preserved'])
        self.assertTrue(legacy.call_args.kwargs['analysis_only'])
        self.assertIn('无法从节点断点恢复', emit.call_args.kwargs['text'])
        assistant = AIOpsChatMessage.objects.create(session=self.session, role='assistant', content=result['content'], metadata=result['metadata'])
        message = execution_queryset().get(pk=self.message.id)
        self.assertEqual(message.assistant_message_id, assistant.id)
        with mock.patch('aiops.langgraph_pilot.get_langgraph_chat_graph') as get_graph:
            detail = execution_detail(message)
        self.assertEqual(detail['checkpoint']['status'], 'degraded')
        self.assertEqual(detail['status'], 'completed')
        get_graph.assert_not_called()

    @mock.patch('aiops.langgraph_pilot.run_langgraph_chat', side_effect=RuntimeError('unexpected runtime failure'))
    @mock.patch('aiops.services._build_chat_result_legacy')
    def test_runtime_failure_does_not_silently_run_compatibility(self, legacy, graph):
        with self.assertRaises(RuntimeError):
            services._build_chat_result(self.session, self.message, self.user, '查看知识图谱')
        legacy.assert_not_called()

    @mock.patch('aiops.services.requests.post')
    @mock.patch('aiops.langgraph_pilot.run_langgraph_chat', side_effect=langgraph_pilot.LangGraphPilotUnavailable('unavailable'))
    def test_compatibility_model_audit_links_to_origin_and_scope_is_reset(self, graph, post):
        from .langgraph_execution import model_audit_scope

        provider = AIOpsModelProvider.objects.create(name='compatibility-model', base_url='https://example.com/v1', default_model='test')
        provider.set_api_key('test-key')
        provider.save(update_fields=['api_key_encrypted'])
        post.return_value.status_code = 200
        post.return_value.json.return_value = {'choices': [{'message': {'content': '证据回复'}}]}

        def legacy(*args, **kwargs):
            services._request_model_completion(provider, {'model': 'test', 'messages': []}, purpose='answer_formatting')
            return {'content': '证据回复', 'metadata': {}, 'message_type': 'analysis'}

        with mock.patch('aiops.services._build_chat_result_legacy', side_effect=legacy):
            services._build_chat_result(self.session, self.message, self.user, '查看知识图谱')
        audit = AIOpsModelInvocation.objects.get()
        self.assertEqual(audit.message_id, self.message.id)
        self.assertEqual(audit.session_id, self.session.id)
        self.assertEqual(audit.username, self.user.username)
        self.assertEqual(model_audit_scope(), {})

    def action(self):
        self.message.metadata = {'langgraph_thread_id': 'stability-chat'}
        self.message.save(update_fields=['metadata'])
        assistant = AIOpsChatMessage.objects.create(
            session=self.session, role='assistant', content='待确认草稿', metadata={'langgraph_thread_id': 'stability-chat'},
        )
        return AIOpsPendingAction.objects.create(
            session=self.session, message=assistant, title='隔离测试草稿', action_type='execute_host_task',
        )

    @mock.patch('aiops.services.confirm_action', return_value={'preview': 'confirmed'})
    def test_action_wait_and_execution_are_audited_without_repeating_confirmation(self, confirm):
        action = self.action()
        langgraph_pilot.start_action_confirmation(action.id)
        langgraph_pilot.start_action_confirmation(action.id)
        waiting = AIOpsGraphNodeRun.objects.get(message=action.message, node='action_confirmation')
        self.assertEqual(waiting.status, 'waiting')
        waiting.started_at = timezone.now() - timedelta(seconds=30)
        waiting.save(update_fields=['started_at'])
        result = langgraph_pilot.confirm_langgraph_action(action, self.user)
        self.assertEqual(result, {'preview': 'confirmed'})
        self.assertEqual(langgraph_pilot.confirm_langgraph_action(action, self.user), result)
        self.assertEqual(confirm.call_count, 1)
        self.assertEqual(AIOpsGraphNodeRun.objects.filter(message=action.message).count(), 3)
        detail = execution_detail(execution_queryset().get(pk=self.message.id))
        confirmation = next(node for node in detail['actions'][0]['nodes'] if node['node'] == 'action_confirmation')
        self.assertEqual(confirmation['status'], 'completed')
        self.assertGreaterEqual(confirmation['waiting_ms'], 29000)
        self.assertLess(confirmation['duration_ms'], 5000)
        self.assertEqual(detail['node_count'], 0)

    @mock.patch('aiops.services.confirm_action', side_effect=PermissionError('permission revoked token=hidden-secret'))
    def test_failed_action_remains_pending_and_records_redacted_failure(self, confirm):
        action = self.action()
        langgraph_pilot.start_action_confirmation(action.id)
        with self.assertRaises(PermissionError):
            langgraph_pilot.confirm_langgraph_action(action, self.user)
        action.refresh_from_db()
        self.assertEqual(action.status, 'pending')
        failed = AIOpsGraphNodeRun.objects.get(message=action.message, node='action_execute')
        self.assertEqual(failed.status, 'failed')
        self.assertNotIn('hidden-secret', failed.error)
        confirm.side_effect = None
        confirm.return_value = {'preview': 'retried'}
        self.assertEqual(langgraph_pilot.confirm_langgraph_action(action, self.user), {'preview': 'retried'})
        self.assertEqual(AIOpsGraphNodeRun.objects.filter(message=action.message, node='action_execute').count(), 2)

    def test_action_audit_is_scoped_to_the_originating_round(self):
        action = self.action()
        langgraph_pilot.start_action_confirmation(action.id)
        other = AIOpsChatMessage.objects.create(session=self.session, role='user', content='下一轮', metadata={'langgraph_thread_id': 'other-round'})
        self.assertEqual(execution_detail(execution_queryset().get(pk=other.id))['actions'], [])
        action.status = 'canceled'
        action.save(update_fields=['status', 'updated_at'])
        detail = execution_detail(execution_queryset().get(pk=self.message.id))
        self.assertEqual(detail['actions'][0]['nodes'][-1]['status'], 'canceled')

    @mock.patch('aiops.langgraph_pilot.get_langgraph_chat_graph')
    @mock.patch('aiops.langgraph_pilot._get_checkpointer')
    def test_retention_cleans_old_action_audit_and_preserves_recent_execution(self, checkpointer, graph):
        from .langgraph_management import cleanup_checkpoints

        action = self.action()
        action.status = 'canceled'
        action.save(update_fields=['status'])
        old = timezone.now() - timedelta(days=31)
        AIOpsChatMessage.objects.filter(pk=self.message.id).update(created_at=old)
        action_thread = langgraph_pilot._action_graph_config(action)['configurable']['thread_id']
        run = AIOpsGraphNodeRun.objects.create(message=action.message, thread_id=action_thread, node='action_execute', status='failed')
        graph.return_value.get_state.return_value = SimpleNamespace(values={'status': 'completed'}, next=())
        self.assertEqual(cleanup_checkpoints(apply=True)['skipped'], 1)
        AIOpsGraphNodeRun.objects.filter(pk=run.id).update(started_at=old, finished_at=old)
        self.assertEqual(cleanup_checkpoints(apply=True)['deleted'], ['stability-chat'])
        self.assertFalse(AIOpsGraphNodeRun.objects.filter(pk=run.id).exists())
        self.assertEqual(checkpointer.return_value.delete_thread.call_count, 2)
