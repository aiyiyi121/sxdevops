import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from eventwall.models import EventRecord
from ops.models import Alert, K8sCluster, LogEntry, SystemPostureSystem

from . import langgraph_pilot, services
from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsKnowledgeEnvironment, AIOpsMCPServer, AIOpsToolInvocation


class LangGraphIncidentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username='incident-regression', password='test')
        self.session = AIOpsChatSession.objects.create(user=self.user, context={'current_environment': {'name': '原环境'}})
        self.cluster = K8sCluster.objects.create(name='原集群', api_server='https://example.com')
        self.environment = AIOpsKnowledgeEnvironment.objects.create(
            name='原环境', alert_environments=['original'], event_environments=['original'],
            k8s_cluster_ids=[self.cluster.id], is_enabled=True,
        )
        AIOpsKnowledgeEnvironment.objects.create(name='新环境', alert_environments=['other'], is_enabled=True)
        self.alert = Alert.objects.create(
            title='原告警 error', fingerprint='original-fingerprint', environment='original',
            service='checkout-api', resource_type='pod', cluster=self.cluster.name,
        )
        self.message = self.new_message()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patch = mock.patch.dict('os.environ', {
            'AIOPS_LANGGRAPH_CHECKPOINT_BACKEND': 'sqlite',
            'AIOPS_LANGGRAPH_CHECKPOINT_PATH': self.directory.name + '/incident.sqlite3',
        })
        patch.start()
        self.addCleanup(patch.stop)
        langgraph_pilot.close_langgraph_resources()
        self.addCleanup(langgraph_pilot.close_langgraph_resources)
        services.get_agent_config()

    def new_message(self, question='分析原环境最新一条告警的根因'):
        return AIOpsChatMessage.objects.create(session=self.session, role='user', content=question)

    def run_graph(self, **kwargs):
        return langgraph_pilot.run_langgraph_chat(
            self.session, self.message, self.user, self.message.content, analysis_only=True, **kwargs,
        )

    def tool_result(self, session, message, user, name, arguments, **kwargs):
        output = {'summary': {'count': 1}, 'sections': [], 'citations': []}
        if name == 'query_logs':
            output['logs'] = [{'level': 'error', 'message': 'checkout dependency timeout'}]
        elif name == 'query_alert_metrics':
            output['summary'] = {'executed_count': 2, 'failed_count': 0, 'missing_count': 0, 'abnormal_count': 1}
        return {'tool_output': output, 'sections': output['sections'], 'citations': output['citations']}

    def stop_before(self, node):
        def emit(**kwargs):
            current = (kwargs.get('metadata_updates') or {}).get('langgraph_current_node') or {}
            if current.get('node') == node and current.get('status') == 'running':
                raise services.ChatJobLeaseLost('controlled interruption')
        return emit

    def test_each_evidence_phase_resumes_without_repeating_completed_queries(self):
        tools = ['query_k8s_cluster_summary', 'query_system_posture', 'query_events',
                 'query_logs', 'query_traces', 'query_alert_metrics']
        phases = ['incident_k8s', 'incident_posture', 'incident_events',
                  'incident_logs', 'incident_traces', 'incident_metrics']
        for phase in phases:
            with self.subTest(phase=phase):
                self.message = self.new_message()
                observed = []

                def tool(session, message, user, name, arguments, **kwargs):
                    observed.append((name, session.context['current_environment']['name'], arguments))
                    return self.tool_result(session, message, user, name, arguments, **kwargs)

                with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=tool):
                    with self.assertRaises(services.ChatJobLeaseLost):
                        self.run_graph(progress_callback=self.stop_before(phase))
                    self.session.context = {'current_environment': {'name': '新环境'}}
                    self.session.save(update_fields=['context'])
                    langgraph_pilot.close_langgraph_resources()
                    result = self.run_graph()
                    audit_count = AIOpsToolInvocation.objects.filter(message=self.message).count()
                    self.run_graph()
                self.assertEqual([name for name, environment, arguments in observed], tools)
                self.assertTrue(all(environment == '原环境' for name, environment, arguments in observed))
                self.assertEqual(AIOpsToolInvocation.objects.filter(message=self.message).count(), audit_count)
                self.assertEqual(result['metadata']['langgraph_runtime_summary']['resume_count'], 1)
                self.assertIn('原告警', result['content'])
                self.assertEqual(observed[-1][2]['alert_id'], self.alert.id)
                self.assertIn('原环境', observed[-2][2]['query'])
                self.assertIsNone(result['pending_action_draft'])

    def test_resume_keeps_original_alert_snapshot_when_latest_alert_changes(self):
        with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=self.tool_result):
            with self.assertRaises(services.ChatJobLeaseLost):
                self.run_graph(progress_callback=self.stop_before('incident_logs'))
            Alert.objects.filter(pk=self.alert.pk).update(title='已经变化的告警')
            newer = Alert.objects.create(title='新出现的告警', environment='original', service='other-api')
            result = self.run_graph()
        self.assertIn('原告警', result['content'])
        self.assertNotIn(newer.title, result['content'])
        self.assertNotIn('已经变化的告警', result['content'])
        self.assertEqual(result['metadata']['alert_id'], self.alert.id)

    def test_revoked_root_permission_stops_resume_before_more_queries(self):
        with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=self.tool_result) as tool:
            with self.assertRaises(services.ChatJobLeaseLost):
                self.run_graph(progress_callback=self.stop_before('incident_logs'))
            completed = tool.call_count
            self.user.is_superuser = False
            self.user.is_staff = False
            self.user.save(update_fields=['is_superuser', 'is_staff'])
            result = self.run_graph()
        self.assertEqual(tool.call_count, completed)
        self.assertIn('无权', result['content'])
        self.assertNotIn('原告警', result['content'])
        self.assertTrue(self.message.graph_node_runs.filter(node='incident_logs', status='blocked', retry_count=0).exists())

    def test_disabled_mcp_on_resume_blocks_queries_and_saved_evidence(self):
        with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=self.tool_result) as tool:
            with self.assertRaises(services.ChatJobLeaseLost):
                self.run_graph(progress_callback=self.stop_before('incident_traces'))
            completed = tool.call_count
            server = next(server for server in AIOpsMCPServer.objects.all() if 'query_alert_root_cause' in server.tool_whitelist)
            server.is_enabled = False
            server.save(update_fields=['is_enabled'])
            result = self.run_graph()
        self.assertEqual(tool.call_count, completed)
        self.assertIn('已停用', result['content'])
        self.assertNotIn('checkout dependency timeout', result['content'])

    def test_optional_permission_denial_is_a_gap_without_query_or_retry(self):
        available = services._runtime_tool_is_available

        def permitted(servers, user, name):
            return False if name == 'query_logs' else available(servers, user, name)

        with mock.patch('aiops.services._runtime_tool_is_available', side_effect=permitted), mock.patch(
            'aiops.langgraph_pilot._run_tool_call', side_effect=self.tool_result,
        ) as tool:
            result = self.run_graph()
        self.assertNotIn('query_logs', [call.args[3] for call in tool.call_args_list])
        self.assertIn('query_logs 已停用或无权访问', result['content'])
        self.assertNotIn('checkout dependency timeout', result['content'])
        self.assertTrue(self.message.graph_node_runs.filter(node='incident_logs', status='blocked', retry_count=0).exists())
        invocation = AIOpsToolInvocation.objects.get(message=self.message, tool_name='query_logs')
        self.assertEqual(invocation.status, AIOpsToolInvocation.STATUS_FAILED)

    def test_explicit_alert_outside_environment_returns_gap_without_evidence_queries(self):
        foreign = Alert.objects.create(title='其他环境私有告警', environment='other', fingerprint='b' * 64)
        for selector in [f'告警ID {foreign.id}', f'指纹 {foreign.fingerprint}']:
            with self.subTest(selector=selector):
                self.message = self.new_message(f'分析原环境这条告警的根因，{selector}')
                with mock.patch('aiops.langgraph_pilot._run_tool_call') as tool:
                    result = self.run_graph()
                tool.assert_not_called()
                self.assertIn('没有找到可分析的告警', result['content'])
                self.assertNotIn(foreign.title, result['content'])
                self.assertNotEqual(result['message_type'], AIOpsChatMessage.TYPE_ERROR)

    def test_structured_snapshots_keep_log_event_and_posture_evidence(self):
        log = LogEntry.objects.create(level='error', service='checkout-api', message='dependency timeout')
        event = EventRecord.objects.create(title='checkout release failed', result='failed', environment='original')
        system = SystemPostureSystem.objects.create(name='checkout', environment='original', core_metric={'value': 98, 'target': 99.9})
        payloads = {'query_logs': {'logs': [log]}, 'query_events': {'events': [event]},
                    'query_system_posture': {'systems': [system]}}

        def tool(session, message, user, name, arguments, **kwargs):
            output = {'summary': {}, 'sections': [], 'citations': [], **payloads.get(name, {})}
            return {'tool_output': output}

        with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=tool):
            result = self.run_graph()
        self.assertIn('基于日志中心证据', result['content'])
        self.assertIn('checkout release failed / failed', result['content'])
        self.assertIn('checkout SLA 98', result['content'])
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(result['metadata']['langgraph_thread_id'])
        self.assertEqual(checkpoint['incident_evidence']['logs']['logs'][0]['level'], 'error')

    def test_metrics_use_saved_alert_facts_after_source_alert_changes(self):
        fact = services._alert_to_fact(self.alert)
        fact.update({key: getattr(self.alert, key).isoformat() if getattr(self.alert, key) else None
                     for key in ('starts_at', 'last_received_at', 'created_at')})
        Alert.objects.filter(pk=self.alert.pk).update(title='changed', service='changed-service')
        self.session._incident_alert_snapshot = fact
        with mock.patch('aiops.services._build_alert_metric_query_plan', return_value=[]) as plan:
            result = services._run_tool_call(
                self.session, self.message, self.user, 'query_alert_metrics', {'query': '原环境', 'alert_id': self.alert.id},
            )['tool_output']
        self.assertEqual(plan.call_args.args[0].service, 'checkout-api')
        self.assertEqual(result['alert']['title'], self.alert.title)

    def test_missing_cluster_service_and_disabled_posture_skip_queries(self):
        self.environment.k8s_cluster_ids = []
        self.environment.save(update_fields=['k8s_cluster_ids'])
        Alert.objects.filter(pk=self.alert.pk).update(service='')
        with mock.patch('aiops.services.is_system_posture_enabled', return_value=False), mock.patch(
            'aiops.langgraph_pilot._run_tool_call', side_effect=self.tool_result,
        ) as tool:
            result = self.run_graph()
        self.assertEqual([call.args[3] for call in tool.call_args_list], ['query_events', 'query_alert_metrics'])
        for node in ['incident_k8s', 'incident_posture', 'incident_logs', 'incident_traces']:
            self.assertEqual(self.message.graph_node_runs.get(node=node).status, 'skipped')
        self.assertIn('未绑定 K8s 集群', result['content'])
        self.assertIn('告警未携带明确服务名', result['content'])

    def test_unfinished_previous_graph_version_is_not_resumed(self):
        with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=self.tool_result) as tool:
            with self.assertRaises(services.ChatJobLeaseLost):
                self.run_graph(progress_callback=self.stop_before('incident_logs'))
            completed = tool.call_count
            self.message.refresh_from_db()
            config = {'configurable': {'thread_id': self.message.metadata['langgraph_thread_id']}}
            langgraph_pilot.get_langgraph_chat_graph().update_state(config, {'graph_version': 9})
            with self.assertRaisesMessage(RuntimeError, '无法安全恢复旧 checkpoint'):
                self.run_graph()
        self.assertEqual(tool.call_count, completed)

    def test_partial_metrics_use_only_successful_results_and_record_failed_tool(self):
        with mock.patch('aiops.services._build_alert_metric_query_plan', return_value=[{'name': 'first'}, {'name': 'second'}]), mock.patch(
            'aiops.services.execute_promql_query', side_effect=RuntimeError('Prometheus HTTP 400'),
        ):
            result = services.query_alert_metrics(self.session, self.message, self.user, query='原环境', alert_id=self.alert.id)
        invocation = AIOpsToolInvocation.objects.get(message=self.message, tool_name='query_alert_metrics')
        self.assertEqual(invocation.status, AIOpsToolInvocation.STATUS_FAILED)
        analysis = services._infer_alert_root_cause(self.alert, metric_result={
            'summary': {'executed_count': 4, 'failed_count': 2, 'missing_count': 1},
        })
        self.assertIn('已返回 1 项有效指标结果', '\n'.join(analysis['evidence']))
        self.assertEqual(result['summary']['failed_count'], 2)

    def test_failed_metrics_and_logs_are_not_reported_as_healthy_evidence(self):
        def tool(session, message, user, name, arguments, **kwargs):
            if name == 'query_alert_metrics':
                return {'tool_output': {'summary': {'executed_count': 3, 'failed_count': 3, 'missing_count': 0}}}
            if name == 'query_logs':
                return {'tool_output': {'error': 'datasource_unavailable'}}
            return self.tool_result(session, message, user, name, arguments, **kwargs)

        with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=tool):
            result = self.run_graph()
        self.assertNotIn('未发现明显异常趋势', result['content'])
        self.assertIn('datasource_unavailable', result['content'])
        self.assertIn('3 项指标查询未完成', result['content'])
        for node in ['incident_logs', 'incident_metrics']:
            run = self.message.graph_node_runs.get(node=node)
            self.assertEqual(run.status, 'failed')
            self.assertTrue(run.error)
