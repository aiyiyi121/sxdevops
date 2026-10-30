import io
import tempfile
from datetime import timedelta
from unittest import mock

import requests
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from cmdb.models import CIType, ConfigItem, ResourceNode
from ops.models import Alert, Deployment, K8sCluster, LogDataSource, LogEntry

from . import langgraph_pilot, services
from .langgraph_analysis import build_analysis_context
from .langgraph_execution import GraphNodeTimeout, instrument_node, query_get
from .langgraph_management import cleanup_checkpoints
from .models import AIOpsChatJob, AIOpsChatMessage, AIOpsChatSession, AIOpsGraphNodeRun, AIOpsKnowledgeEnvironment, AIOpsMCPServer, AIOpsModelInvocation, AIOpsModelProvider, AIOpsPendingAction


class LangGraphOperationsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username='graph-operations', password='test')
        self.session = AIOpsChatSession.objects.create(user=self.user, title='graph-operations')
        self.message = AIOpsChatMessage.objects.create(session=self.session, role='user', content='分析测试环境')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patch = mock.patch.dict('os.environ', {'AIOPS_LANGGRAPH_CHECKPOINT_BACKEND': 'sqlite',
                                               'AIOPS_LANGGRAPH_CHECKPOINT_PATH': self.directory.name + '/graph.sqlite3',
                                               'AIOPS_LANGGRAPH_NODE_TIMEOUT_SECONDS': '180', 'AIOPS_LANGGRAPH_QUERY_RETRIES': '1'})
        patch.start()
        self.addCleanup(patch.stop)
        langgraph_pilot.close_langgraph_resources()
        self.addCleanup(langgraph_pilot.close_langgraph_resources)
        config = services.get_agent_config()
        AIOpsMCPServer.objects.update(is_enabled=True)
        config.enabled_mcp_server_ids = list(AIOpsMCPServer.objects.values_list('id', flat=True))
        config.save(update_fields=['enabled_mcp_server_ids'])

    def run_graph(self, **kwargs):
        return langgraph_pilot.run_langgraph_chat(self.session, self.message, self.user, self.message.content, **kwargs)

    def simple_result(self):
        return {'content': '完成', 'metadata': {}, 'tool_calls': [], 'citations': [], 'pending_action_draft': None}

    def finish_graph(self):
        with mock.patch('aiops.services._build_chat_result_legacy', return_value=self.simple_result()):
            return self.run_graph()

    def expire_records(self):
        old = timezone.now() - timedelta(days=40)
        AIOpsChatMessage.objects.filter(pk=self.message.pk).update(created_at=old)
        AIOpsGraphNodeRun.objects.filter(message__session=self.session).update(started_at=old, finished_at=old)

    @mock.patch('aiops.services.requests.post')
    def test_node_model_calls_link_implicit_formatter_and_parameter_audits(self, post):
        provider = AIOpsModelProvider.objects.create(name='audit-model', base_url='https://example.com', default_model='test')
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            'choices': [{'message': {'content': '完成'}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
        }

        def format_answer(state, config=None):
            for purpose in [AIOpsModelInvocation.PURPOSE_PARAMETER_EXTRACTION, AIOpsModelInvocation.PURPOSE_ANSWER_FORMATTING]:
                services._request_model_completion(provider, {'model': 'test', 'messages': []}, purpose=purpose)
            return {'trace': [{'node': 'format', 'status': 'completed'}]}

        instrument_node('format', format_answer)({
            'session_id': self.session.id, 'message_id': self.message.id, 'user_id': self.user.id,
        })
        invocations = list(AIOpsModelInvocation.objects.order_by('id'))
        self.assertEqual(len(invocations), 2)
        for invocation in invocations:
            self.assertEqual(invocation.session_id, self.session.id)
            self.assertEqual(invocation.message_id, self.message.id)
            self.assertEqual(invocation.username, self.user.username)
            self.assertEqual(invocation.total_tokens, 15)
        services._request_model_completion(provider, {'model': 'test', 'messages': []}, purpose=AIOpsModelInvocation.PURPOSE_MODEL_PROBE)
        probe = AIOpsModelInvocation.objects.latest('id')
        self.assertIsNone(probe.session_id)
        self.assertIsNone(probe.message_id)
        self.assertEqual(probe.username, '')

    def test_model_audit_scope_preserves_explicit_identity_and_resets_after_failure(self):
        provider = AIOpsModelProvider.objects.create(name='audit-model', base_url='https://example.com', default_model='test')
        other_user = get_user_model().objects.create_user(username='other-model-user')
        other_session = AIOpsChatSession.objects.create(user=other_user)
        other_message = AIOpsChatMessage.objects.create(session=other_session, role='user', content='另一个问题')

        def fail_after_audit(state, config=None):
            services._record_model_invocation(
                provider, {}, status_value='failed', session=other_session, message=other_message, user=other_user,
            )
            raise ValueError('failed node')

        with self.assertRaises(ValueError):
            instrument_node('fail', fail_after_audit)({
                'session_id': self.session.id, 'message_id': self.message.id, 'user_id': self.user.id,
            })
        explicit = AIOpsModelInvocation.objects.latest('id')
        self.assertEqual(explicit.session_id, other_session.id)
        self.assertEqual(explicit.message_id, other_message.id)
        self.assertEqual(explicit.username, other_user.username)
        services._record_model_invocation(provider, {}, status_value='success')
        independent = AIOpsModelInvocation.objects.latest('id')
        self.assertIsNone(independent.session_id)
        self.assertIsNone(independent.message_id)
        self.assertEqual(independent.username, '')

    def test_readonly_transient_retry_records_duration_and_retry_count(self):
        def query(state, config=None):
            result = services._run_tool_call(self.session, self.message, self.user, 'query_alerts', {})
            return {'trace': [{'node': 'query', 'status': 'completed'}], 'result': result}

        with mock.patch('aiops.services._run_tool_call_once', side_effect=[requests.Timeout('temporary'), {'tool_output': {}}]) as tool:
            update = instrument_node('query', query)({'message_id': self.message.id}, {'configurable': {'thread_id': 'retry'}})
        self.assertEqual(tool.call_count, 2)
        run = AIOpsGraphNodeRun.objects.get(node='query')
        self.assertEqual(run.retry_count, 1)
        self.assertEqual(run.status, 'completed')
        self.assertEqual(update['trace'][0]['run_id'], run.id)
        self.assertGreaterEqual(run.duration_ms, 0)

    def test_permissions_write_tools_and_external_tools_are_not_retried(self):
        for tool_name, entry, exception in [
            ('query_alerts', None, PermissionError('denied')),
            ('generate_host_task', None, requests.Timeout('timeout')),
            ('query_alerts', {'kind': 'external'}, requests.Timeout('timeout')),
        ]:
            with self.subTest(tool_name=tool_name, entry=entry):
                def call(state, config=None):
                    services._run_tool_call(self.session, self.message, self.user, tool_name, {}, registry_entry=entry)
                with mock.patch('aiops.services._run_tool_call_once', side_effect=exception) as tool:
                    with self.assertRaises(type(exception)):
                        instrument_node('denied', call)({'message_id': self.message.id})
                self.assertEqual(tool.call_count, 1)

    def test_datasource_get_retries_transport_error_and_limits_timeout(self):
        client = mock.Mock()
        client.get.side_effect = [requests.ConnectionError('temporary'), mock.Mock(status_code=200)]
        def query(state, config=None):
            query_get(client, 'https://example.com', timeout=1000)
            return {'trace': [{'node': 'data', 'status': 'completed'}]}
        instrument_node('data', query)({'message_id': self.message.id})
        self.assertEqual(client.get.call_count, 2)
        self.assertLessEqual(client.get.call_args.kwargs['timeout'], 180)
        self.assertEqual(AIOpsGraphNodeRun.objects.get(node='data').retry_count, 1)

    def test_timeout_and_lease_loss_persist_failure_without_success(self):
        function = lambda state, config=None: {'trace': [{'node': 'slow', 'status': 'completed'}]}
        with mock.patch.dict('os.environ', {'AIOPS_LANGGRAPH_NODE_TIMEOUT_SECONDS': '1'}), mock.patch(
            'aiops.langgraph_execution.time.monotonic', side_effect=[0, 2, 2],
        ):
            with self.assertRaises(GraphNodeTimeout):
                instrument_node('slow', function)({'message_id': self.message.id})
        self.assertEqual(AIOpsGraphNodeRun.objects.get(node='slow').status, 'failed')
        with self.assertRaises(services.ChatJobLeaseLost):
            instrument_node('lease', mock.Mock(side_effect=services.ChatJobLeaseLost('lost')))({'message_id': self.message.id})
        self.assertEqual(AIOpsGraphNodeRun.objects.get(node='lease').status, 'interrupted')

    def test_analysis_resumes_next_evidence_and_pins_environment(self):
        for kind, stop_tool in [('alerts', 'query_alert_metrics'), ('service', 'query_logs')]:
            with self.subTest(kind=kind):
                self.message = AIOpsChatMessage.objects.create(session=self.session, role='user', content='分析环境异常')
                context = build_analysis_context(kind=kind, question=self.message.content, scoped_question=self.message.content,
                    environment={'name': '原环境'}, scope={}, provider=None, skills=[], action=None)
                context['service'] = 'checkout-api' if kind == 'service' else ''
                observed = []
                def tool(session, message, user, name, arguments, **kwargs):
                    observed.append((name, session.context['current_environment']['name']))
                    output = {'alerts': [{'id': 123, 'fingerprint': '', 'level': 'critical', 'status': 'active'}]} if name == 'query_alerts' else {}
                    return {'tool_output': output, 'sections': [], 'citations': []}
                def emit(**kwargs):
                    event = kwargs.get('tool_event') or {}
                    if event.get('name') == stop_tool and event.get('status') == 'running':
                        raise services.ChatJobLeaseLost('controlled stop')
                with mock.patch('aiops.services._build_chat_result_legacy', return_value={'_analysis_context': context}), mock.patch(
                    'aiops.services._run_tool_call', side_effect=tool), mock.patch('aiops.services.is_system_posture_enabled', return_value=False):
                    with self.assertRaises(services.ChatJobLeaseLost):
                        self.run_graph(progress_callback=emit)
                    self.session.context = {'current_environment': {'name': '新环境'}}
                    self.session.save(update_fields=['context'])
                    langgraph_pilot.close_langgraph_resources()
                    result = self.run_graph()
                    self.run_graph()
                self.assertEqual([name for name, environment in observed].count('query_alerts'), 1)
                self.assertTrue(all(environment == '原环境' for name, environment in observed))
                self.assertTrue(result['metadata']['langgraph_analysis_checkpointed'])
                self.assertEqual(result['metadata']['langgraph_runtime_summary']['resume_count'], 1)
                self.assertIsNone(result['pending_action_draft'])

    def test_revoked_tool_permission_on_resume_does_not_call_it(self):
        context = build_analysis_context(kind='alerts', question='分析告警', scoped_question='分析告警',
            environment={'name': '测试'}, scope={}, provider=None, skills=[], action=None)
        with mock.patch('aiops.services._build_chat_result_legacy', return_value={'_analysis_context': context}), mock.patch(
            'aiops.services._runtime_tool_is_available', return_value=False), mock.patch('aiops.services._run_tool_call') as tool:
            result = self.run_graph()
        tool.assert_not_called()
        self.assertIn('无权访问', result['content'])
        self.assertTrue(self.message.graph_node_runs.filter(status='blocked').exists())

    def test_explicit_analysis_bypasses_matching_cmdb_catalog(self):
        AIOpsKnowledgeEnvironment.objects.create(name='验证环境', is_enabled=True)
        for question, mode in [('帮我分析下验证环境告警', 'deterministic_alert_environment_analysis'),
                               ('分析下验证环境订单服务最近一小时有什么异常', 'deterministic_service_rca')]:
            with self.subTest(question=question):
                self.message = AIOpsChatMessage.objects.create(session=self.session, role='user', content=question)
                with mock.patch('aiops.services.get_active_provider', return_value=None), mock.patch(
                    'aiops.services._cmdb_tool_for_question', return_value='query_cmdb_items'), mock.patch(
                    'aiops.services._run_tool_call', return_value={'tool_output': {}, 'sections': [], 'citations': []}) as tool:
                    result = self.run_graph()
                self.assertEqual(result['metadata']['execution_mode'], mode)
                self.assertTrue(result['metadata']['langgraph_analysis_checkpointed'])
                self.assertNotIn('query_cmdb_items', [call.args[3] for call in tool.call_args_list])

    def test_explicit_evidence_queries_bypass_cmdb_and_container_matching(self):
        AIOpsKnowledgeEnvironment.objects.create(name='电商测试环境', is_enabled=True)
        cases = [
            ('查询电商测试环境知识图谱，列出服务与依赖关系', 'query_knowledge_graph'),
            ('查询电商测试环境 order-service 的依赖关系', 'query_knowledge_graph'),
            ('查看电商测试环境最近30分钟有哪些告警', 'query_alerts'),
            ('查询电商测试环境 order-service 最近30分钟 ERROR 日志', 'query_logs'),
            ('查询电商测试环境 order-service 最近30分钟错误链路', 'query_traces'),
            ('查询电商测试环境 PromQL ecommerce_checkout_outcomes_total{namespace="ecommerce"}', 'query_grafana_promql'),
        ]
        for question, expected_tool in cases:
            with self.subTest(question=question):
                self.message = AIOpsChatMessage.objects.create(session=self.session, role='user', content=question)
                with mock.patch('aiops.services.get_active_provider', return_value=None), mock.patch(
                    'aiops.services._cmdb_tool_for_question', return_value='query_cmdb_items'), mock.patch(
                    'aiops.services._run_tool_call', return_value={'tool_output': {}, 'sections': [], 'citations': []}) as tool:
                    result = self.run_graph(analysis_only=True)
                self.assertEqual(result['tool_calls'], [expected_tool])
                self.assertEqual([call.args[3] for call in tool.call_args_list], [expected_tool])
                self.assertEqual(result['metadata']['current_environment'], '电商测试环境')
                if expected_tool == 'query_knowledge_graph' and 'order-service' in question:
                    self.assertEqual(tool.call_args.args[4]['service'], 'order-service')
                if expected_tool == 'query_traces':
                    self.assertEqual(tool.call_args.args[4]['duration_minutes'], 30)
                    self.assertTrue(tool.call_args.args[4]['errors_only'])
                if expected_tool == 'query_grafana_promql':
                    self.assertEqual(tool.call_args.args[4]['promql'], 'ecommerce_checkout_outcomes_total{namespace="ecommerce"}')

    def test_unmaintained_knowledge_environment_cmdb_scope_returns_gap(self):
        AIOpsKnowledgeEnvironment.objects.create(name='电商测试环境', aliases=['电商测试'], is_enabled=True)
        business = ResourceNode.objects.create(name='其他业务', node_type='biz')
        environment = ResourceNode.objects.create(name='测试', node_type='env', parent=business)
        ci_type = CIType.objects.create(name='回归主机', code='regression-host')
        asset = ConfigItem.objects.create(name='other-test-host', ci_type=ci_type, environment_node=environment, environment='test')
        result = services.query_cmdb_items(self.session, self.message, self.user,
            query='查询电商测试环境 CMDB 主机资产', environment='测试', search_terms=[])
        self.assertEqual(result['summary']['count'], 0)
        self.assertTrue(result['summary']['environment_unmapped'])
        self.assertEqual(result['summary']['environment'], '电商测试环境')
        self.assertIn('尚未维护', result['sections'][0]['items'][0])
        scoped_environment = ResourceNode.objects.create(name='电商测试环境', node_type='env', parent=business)
        asset.environment_node = scoped_environment
        asset.save(update_fields=['environment_node'])
        result = services.query_cmdb_items(self.session, self.message, self.user,
            query='查询电商测试环境 CMDB 主机资产', environment='测试', search_terms=[])
        self.assertEqual([item['id'] for item in result['items']], [asset.id])

    def test_alert_followup_keeps_resolved_environment_without_cmdb_context(self):
        AIOpsKnowledgeEnvironment.objects.create(name='电商测试环境', is_enabled=True)
        for question in ['查看电商测试环境最近30分钟有哪些告警', '再分析一下这个环境最近30分钟告警的原因']:
            self.message = AIOpsChatMessage.objects.create(session=self.session, role='user', content=question)
            with mock.patch('aiops.services.get_active_provider', return_value=None), mock.patch(
                'aiops.services._cmdb_question_has_catalog_reference', return_value=True), mock.patch(
                'aiops.services._run_tool_call', return_value={'tool_output': {}, 'sections': [], 'citations': []}):
                result = self.run_graph(analysis_only=True)
            self.session.refresh_from_db()
            self.assertEqual(self.session.context['current_environment']['name'], '电商测试环境')
            self.assertIn('query_alerts', result['tool_calls'])
            self.assertNotIn('query_cmdb_items', result['tool_calls'])
            self.assertFalse(result['metadata'].get('environment_required'))

    def test_scoped_changes_exclude_other_business_and_cluster_namespaces(self):
        cluster = K8sCluster.objects.create(name='电商回归集群', api_server='https://example.com')
        AIOpsKnowledgeEnvironment.objects.create(name='电商测试环境', aliases=['电商测试'],
            k8s_cluster_ids=[cluster.id], k8s_namespaces={str(cluster.id): ['ecommerce']})
        matched = Deployment.objects.create(app_name='order', business_line='ecommerce', version='v1',
            environment='test', cluster=cluster, namespace='ecommerce')
        Deployment.objects.create(app_name='order-center', business_line='其他业务', version='v2', environment='test')
        Deployment.objects.create(app_name='order', business_line='ecommerce', version='v3', environment='test',
            cluster=cluster, namespace='other')
        Deployment.objects.create(app_name='order', business_line='ecommerce', version='v4', environment='test')
        result = services._run_tool_call(self.session, self.message, self.user, 'query_recent_changes',
            {'query': '电商测试环境 order', 'system_name': 'ecommerce', 'service': 'order'})['tool_output']
        self.assertEqual(result['summary']['count'], 1)
        self.assertIn(matched.version, result['sections'][0]['items'][0])
        self.assertNotIn('order-center', str(result))
        self.assertEqual(result['summary']['environment'], '电商测试环境')
        matched.delete()
        result = services.query_recent_changes(self.session, self.message, self.user,
            query='电商测试环境 order', system_name='ecommerce', service='order')
        self.assertEqual(result['summary']['count'], 0)
        self.assertIn('变更证据缺口', str(result['sections']))

    def test_disabled_bound_log_source_does_not_fall_back_to_local_logs(self):
        datasource = LogDataSource.objects.create(name='电商停用日志源', provider='loki', is_enabled=False)
        AIOpsKnowledgeEnvironment.objects.create(name='电商测试环境', log_datasource_ids=[datasource.id])
        LogEntry.objects.create(service='order', level='error', message='其他环境的错误样本')
        with mock.patch('aiops.services.run_log_provider_query') as query:
            result = services.query_logs(self.session, self.message, self.user,
                query='电商测试环境 order', service='order', level='error')
        query.assert_not_called()
        self.assertEqual(result['logs'], [])
        self.assertTrue(result['summary']['evidence_unavailable'])
        self.assertIn('未启用', str(result['sections']))
        self.assertNotIn('其他环境的错误样本', str(result))

    def test_self_heal_trace_uses_bound_environment_datasource(self):
        AIOpsKnowledgeEnvironment.objects.create(name='电商测试环境', tracing_datasource_ids=[222])
        state = {'session_id': self.session.id, 'message_id': self.message.id, 'user_id': self.user.id,
                 'self_heal_service': 'order', 'self_heal_environment': {'name': '电商测试环境'}}
        with mock.patch('aiops.services._query_live_traces', return_value=(
            {'traces': [], 'tracing': {'datasource_id': 222}}, {'name': 'order'}, 'order',
        )) as query:
            langgraph_pilot._self_heal_traces_node(state)
        self.assertEqual(query.call_args.kwargs['datasource_ids'], [222])
        self.assertEqual(query.call_args.kwargs['query'], 'order')

    def test_alert_window_uses_original_question_in_graph_and_direct_query(self):
        AIOpsKnowledgeEnvironment.objects.create(name='电商测试环境', alert_environments=['电商测试'])
        current = timezone.now()
        recent = Alert.objects.create(title='recent', environment='电商测试', last_received_at=current)
        previous = Alert.objects.create(title='previous', environment='电商测试',
            starts_at=current - timedelta(minutes=45), last_received_at=current - timedelta(minutes=45))
        Alert.objects.filter(pk=previous.pk).update(created_at=current - timedelta(minutes=45))
        self.message.content = '查看电商测试环境最近30分钟有哪些告警'
        for query, date_filter in [('电商测试环境', 'last_hour'), ('查看电商测试环境最近30分钟有哪些告警', '')]:
            with self.subTest(query=query):
                result = services.query_alerts(self.session, self.message, self.user, query=query, date_filter=date_filter)
                self.assertEqual([alert.id for alert in result['alerts']], [recent.id])
                self.assertEqual(result['summary']['duration_minutes'], 30)
                self.assertEqual(result['summary']['date_filter'], 'last_minutes')

    def test_retention_preview_and_apply_delete_completed_checkpoint_only(self):
        self.finish_graph()
        self.expire_records()
        preview = cleanup_checkpoints(retention_days=30)
        self.assertEqual(len(preview['eligible']), 1)
        self.assertTrue(langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id']))
        result = cleanup_checkpoints(retention_days=30, apply=True)
        self.assertEqual(len(result['deleted']), 1)
        self.assertFalse(langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id']))
        with self.assertRaisesMessage(ValueError, '清理'):
            self.run_graph()
        self.assertTrue(AIOpsChatMessage.objects.filter(pk=self.message.pk).exists())

    def test_retention_protects_active_jobs_pending_actions_and_recent_runs(self):
        self.finish_graph()
        self.expire_records()
        assistant = AIOpsChatMessage.objects.create(session=self.session, role='assistant', content='')
        job = AIOpsChatJob.objects.create(assistant_message=assistant, user_message=self.message,
                                         thread_id=self.message.metadata['langgraph_thread_id'])
        self.assertEqual(cleanup_checkpoints(apply=True)['deleted'], [])
        job.delete()
        action = AIOpsPendingAction.objects.create(session=self.session, message=assistant, action_type='execute_host_task')
        self.assertEqual(cleanup_checkpoints(apply=True)['deleted'], [])
        action.delete()
        AIOpsGraphNodeRun.objects.filter(message=self.message).update(started_at=timezone.now())
        self.assertEqual(cleanup_checkpoints(apply=True)['deleted'], [])

    def test_cleanup_failure_keeps_tombstone_and_retries_deletion(self):
        self.finish_graph()
        self.expire_records()
        saver = langgraph_pilot._get_checkpointer()
        with mock.patch.object(saver, 'delete_thread', side_effect=RuntimeError('storage unavailable')):
            with self.assertRaises(RuntimeError):
                cleanup_checkpoints(apply=True)
        self.message.refresh_from_db()
        self.assertTrue(self.message.metadata['langgraph_checkpoint_cleanup_pending'])
        with self.assertRaises(ValueError):
            self.run_graph()
        self.assertEqual(len(cleanup_checkpoints(apply=True)['deleted']), 1)

    def test_retention_cleans_terminal_synchronous_action_checkpoint(self):
        self.finish_graph()
        assistant = AIOpsChatMessage.objects.create(session=self.session, role='assistant', content='',
            metadata={'langgraph_thread_id': self.message.metadata['langgraph_thread_id']})
        action = AIOpsPendingAction.objects.create(session=self.session, message=assistant, action_type='execute_host_task')
        langgraph_pilot.start_action_confirmation(action.id)
        action_config = langgraph_pilot._action_graph_config(action)
        self.assertTrue(langgraph_pilot.get_langgraph_action_graph().get_state(action_config).values)
        action.status = AIOpsPendingAction.STATUS_CANCELED
        action.save(update_fields=['status'])
        self.expire_records()
        self.assertEqual(len(cleanup_checkpoints(apply=True)['deleted']), 1)
        self.assertFalse(langgraph_pilot.get_langgraph_action_graph().get_state(action_config).values)
        self.assertTrue(AIOpsPendingAction.objects.filter(pk=action.id).exists())

    def test_inspection_reports_failures_without_checkpoint_payload(self):
        self.finish_graph()
        output = io.StringIO()
        call_command('inspect_aiops_graph', thread_id=self.message.metadata['langgraph_thread_id'], stdout=output)
        self.assertIn('duration_ms', output.getvalue())
        self.assertIn('resume_count', output.getvalue())
        self.assertNotIn('ssh_password', output.getvalue())
