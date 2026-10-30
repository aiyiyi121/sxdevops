import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from eventwall.models import EventRecord
from ops.models import Alert, K8sCluster, SystemPostureSystem

from . import langgraph_pilot, services
from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsKnowledgeEnvironment, AIOpsMCPServer, AIOpsToolInvocation


class LangGraphK8sTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username='k8s-regression', password='test')
        self.session = AIOpsChatSession.objects.create(user=self.user, context={'current_environment': {'name': '原环境'}})
        self.cluster = K8sCluster.objects.create(name='原集群', api_server='https://example.com')
        self.other_cluster = K8sCluster.objects.create(name='其他集群', api_server='https://other.example.com')
        self.environment = AIOpsKnowledgeEnvironment.objects.create(
            name='原环境', alert_environments=['original'], event_environments=['original'],
            posture_environments=['original'], k8s_cluster_ids=[self.cluster.id], is_enabled=True,
        )
        AIOpsKnowledgeEnvironment.objects.create(name='新环境', k8s_cluster_ids=[self.other_cluster.id], is_enabled=True)
        self.message = self.new_message()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patch = mock.patch.dict('os.environ', {
            'AIOPS_LANGGRAPH_CHECKPOINT_BACKEND': 'sqlite',
            'AIOPS_LANGGRAPH_CHECKPOINT_PATH': self.directory.name + '/k8s.sqlite3',
        })
        patch.start()
        self.addCleanup(patch.stop)
        langgraph_pilot.close_langgraph_resources()
        self.addCleanup(langgraph_pilot.close_langgraph_resources)
        services.get_agent_config()
        for patch in [mock.patch('aiops.services.is_system_posture_enabled', return_value=True),
                      mock.patch('aiops.services._build_analysis_scope', return_value={'environment': '原环境', 'k8s_cluster_ids': [self.cluster.id]})]:
            patch.start()
            self.addCleanup(patch.stop)

    def new_message(self):
        return AIOpsChatMessage.objects.create(session=self.session, role='user', content='分析原环境 monitoring 命名空间的 K8s 异常工作负载')

    def run_graph(self, **kwargs):
        return langgraph_pilot.run_langgraph_chat(
            self.session, self.message, self.user, self.message.content, analysis_only=True, **kwargs,
        )

    def tool_result(self, session, message, user, name, arguments, **kwargs):
        return {'tool_output': {'summary': {'count': 1},
                                'sections': [{'title': name, 'items': [f'{name} 原环境证据']}], 'citations': []}}

    def stop_before(self, node):
        def emit(**kwargs):
            current = (kwargs.get('metadata_updates') or {}).get('langgraph_current_node') or {}
            if current.get('node') == node and current.get('status') == 'running':
                raise services.ChatJobLeaseLost('controlled interruption')
        return emit

    def test_each_phase_resumes_with_original_scope_and_no_repeated_queries(self):
        tools = ['query_k8s_resources', 'query_k8s_cluster_summary', 'query_alerts', 'query_events', 'query_system_posture']
        for phase in ['k8s_resources', 'k8s_cluster', 'k8s_alerts', 'k8s_events', 'k8s_posture', 'k8s_synthesis']:
            with self.subTest(phase=phase):
                self.message = self.new_message()
                observed = []

                def tool(session, message, user, name, arguments, **kwargs):
                    observed.append((name, session.context['current_environment']['name'], session._k8s_environment_snapshot, arguments))
                    return self.tool_result(session, message, user, name, arguments, **kwargs)

                with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=tool):
                    with self.assertRaises(services.ChatJobLeaseLost):
                        self.run_graph(progress_callback=self.stop_before(phase))
                    self.session.context = {'current_environment': {'name': '新环境'}}
                    self.session.save(update_fields=['context'])
                    langgraph_pilot.close_langgraph_resources()
                    result = self.run_graph()
                    run_count = self.message.graph_node_runs.exclude(node='__graph__').count()
                    self.run_graph()
                self.assertEqual([item[0] for item in observed], tools)
                self.assertTrue(all(item[1] == '原环境' and item[2]['k8s_cluster_ids'] == [self.cluster.id] for item in observed))
                self.assertIn('monitoring', observed[0][3]['query'])
                self.assertEqual(self.message.graph_node_runs.exclude(node='__graph__').count(), run_count)
                self.assertEqual(result['metadata']['langgraph_runtime_summary']['resume_count'], 1)
                self.assertIsNone(result['pending_action_draft'])
                for node in ['k8s_alerts', 'k8s_events', 'k8s_posture']:
                    self.assertTrue(self.message.graph_node_runs.filter(node=node, status='completed').exists())

    def test_revoked_core_permission_blocks_queries_and_cached_synthesis(self):
        for phase in ['k8s_events', 'k8s_synthesis']:
            with self.subTest(phase=phase):
                self.user.is_superuser = True
                self.user.save(update_fields=['is_superuser'])
                self.message = self.new_message()
                with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=self.tool_result) as tool:
                    with self.assertRaises(services.ChatJobLeaseLost):
                        self.run_graph(progress_callback=self.stop_before(phase))
                    completed = tool.call_count
                    self.user.is_superuser = False
                    self.user.is_staff = False
                    self.user.save(update_fields=['is_superuser', 'is_staff'])
                    result = self.run_graph()
                self.assertEqual(tool.call_count, completed)
                self.assertIn('无权', result['content'])
                self.assertNotIn('原环境证据', result['content'])
                self.assertTrue(self.message.graph_node_runs.filter(node=phase, status='blocked', retry_count=0).exists())

    def test_disabled_core_mcp_blocks_resume(self):
        with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=self.tool_result) as tool:
            with self.assertRaises(services.ChatJobLeaseLost):
                self.run_graph(progress_callback=self.stop_before('k8s_events'))
            completed = tool.call_count
            server = next(server for server in AIOpsMCPServer.objects.all() if 'query_k8s_resources' in server.tool_whitelist)
            server.is_enabled = False
            server.save(update_fields=['is_enabled'])
            result = self.run_graph()
        self.assertEqual(tool.call_count, completed)
        self.assertIn('已停用', result['content'])
        self.assertNotIn('原环境证据', result['content'])

    def test_initial_core_denial_stops_before_loading_scope(self):
        self.user.is_superuser = False
        self.user.is_staff = False
        self.user.save(update_fields=['is_superuser', 'is_staff'])
        with mock.patch('aiops.services._build_analysis_scope') as scope, mock.patch('aiops.langgraph_pilot._run_tool_call') as tool:
            result = self.run_graph()
        scope.assert_not_called()
        tool.assert_not_called()
        self.assertIn('无权', result['content'])

    def test_newly_enabled_mcp_is_not_added_to_resumed_scope(self):
        server = next(server for server in AIOpsMCPServer.objects.all() if 'query_event_wall' in server.tool_whitelist)
        server.is_enabled = False
        server.save(update_fields=['is_enabled'])
        with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=self.tool_result) as tool:
            with self.assertRaises(services.ChatJobLeaseLost):
                self.run_graph(progress_callback=self.stop_before('k8s_events'))
            server.is_enabled = True
            server.save(update_fields=['is_enabled'])
            result = self.run_graph()
        self.assertNotIn('query_events', [call.args[3] for call in tool.call_args_list])
        self.assertIn('query_events 已停用或无权访问', result['content'])

    def test_optional_denial_creates_gap_without_retry(self):
        available = services._runtime_tool_is_available

        def permitted(servers, user, name):
            return False if name == 'query_event_wall' else available(servers, user, name)

        with mock.patch('aiops.services._runtime_tool_is_available', side_effect=permitted), mock.patch(
            'aiops.langgraph_pilot._run_tool_call', side_effect=self.tool_result,
        ) as tool:
            result = self.run_graph()
        self.assertNotIn('query_events', [call.args[3] for call in tool.call_args_list])
        self.assertIn('query_events 已停用或无权访问', result['content'])
        self.assertTrue(self.message.graph_node_runs.filter(node='k8s_events', status='blocked', retry_count=0).exists())
        self.assertEqual(AIOpsToolInvocation.objects.get(message=self.message, tool_name='query_events').status, 'failed')

    def test_synthesis_removes_revoked_optional_cached_evidence(self):
        with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=self.tool_result):
            with self.assertRaises(services.ChatJobLeaseLost):
                self.run_graph(progress_callback=self.stop_before('k8s_synthesis'))
            available = services._runtime_tool_is_available
            with mock.patch('aiops.services._runtime_tool_is_available', side_effect=lambda servers, user, name: name != 'query_event_wall' and available(servers, user, name)):
                result = self.run_graph()
        self.assertNotIn('query_events 原环境证据', result['content'])
        self.assertIn('已移除缓存证据', result['content'])

    def test_missing_cluster_and_disabled_posture_are_explicit_skips(self):
        self.environment.k8s_cluster_ids = []
        self.environment.save(update_fields=['k8s_cluster_ids'])
        with mock.patch('aiops.services.is_system_posture_enabled', return_value=False), mock.patch(
            'aiops.langgraph_pilot._run_tool_call', side_effect=self.tool_result,
        ) as tool:
            result = self.run_graph()
        self.assertEqual([call.args[3] for call in tool.call_args_list], ['query_alerts', 'query_events'])
        for node in ['k8s_resources', 'k8s_cluster', 'k8s_posture']:
            self.assertEqual(self.message.graph_node_runs.get(node=node).status, 'skipped')
        self.assertIn('未绑定 K8s 集群', result['content'])
        self.assertIn('功能未启用', result['content'])

    def test_summary_error_marks_failed_node_and_emits_failed_progress(self):
        progress = []

        def tool(session, message, user, name, arguments, **kwargs):
            result = self.tool_result(session, message, user, name, arguments, **kwargs)
            if name == 'query_k8s_resources':
                result['tool_output']['summary']['error'] = 'K8s API unavailable'
            return result

        with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=tool):
            self.run_graph(progress_callback=lambda **kwargs: progress.append(kwargs))
        self.assertEqual(self.message.graph_node_runs.get(node='k8s_resources').status, 'failed')
        self.assertEqual(self.message.graph_node_runs.get(node='k8s_resources').error, 'K8s API unavailable')
        self.assertTrue(any(item.get('tool_event', {}).get('status') == 'failed' for item in progress))

    def test_structured_snapshots_keep_alert_event_and_posture_fields(self):
        alert = Alert.objects.create(title='original alert', environment='original', level='critical')
        event = EventRecord.objects.create(title='original release', result='failed', environment='original')
        system = SystemPostureSystem.objects.create(name='original system', environment='original', core_metric={'value': 98})
        payloads = {'query_alerts': {'alerts': [alert]}, 'query_events': {'events': [event]}, 'query_system_posture': {'systems': [system]}}

        def tool(session, message, user, name, arguments, **kwargs):
            return {'tool_output': {'summary': {}, 'sections': [], 'citations': [], **payloads.get(name, {})}}

        with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=tool):
            result = self.run_graph()
        evidence = langgraph_pilot.get_langgraph_chat_checkpoint(result['metadata']['langgraph_thread_id'])['k8s_evidence']
        self.assertEqual(evidence['query_alerts']['alerts'][0]['level'], 'critical')
        self.assertEqual(evidence['query_events']['events'][0]['title'], event.title)
        self.assertEqual(evidence['query_system_posture']['systems'][0]['core_metric'], {'value': 98})

    def test_saved_binding_is_used_after_live_environment_changes(self):
        snapshot = services.resolve_knowledge_environment(self.environment.name)
        self.environment.k8s_cluster_ids = [self.other_cluster.id]
        self.environment.alert_environments = ['other']
        self.environment.event_environments = ['other']
        self.environment.save(update_fields=['k8s_cluster_ids', 'alert_environments', 'event_environments'])
        self.session._k8s_environment_snapshot = snapshot
        original_alert = Alert.objects.create(title='original alert', environment='original')
        Alert.objects.create(title='other private alert', environment='other')
        original_event = EventRecord.objects.create(title='original release', environment='original')
        EventRecord.objects.create(title='other private release', environment='other')
        with mock.patch('aiops.services._load_k8s_namespaced_resources', return_value=[]) as load:
            services.query_k8s_resources(self.session, self.message, self.user, query='原环境 monitoring namespace', resource_type='deployments')
        self.assertEqual(load.call_args.args[0].id, self.cluster.id)
        self.assertEqual(load.call_args.args[2], ['monitoring'])
        self.assertEqual(services.query_alerts(self.session, self.message, self.user, query='原环境')['alerts'], [original_alert])
        self.assertEqual(services.query_events(self.session, self.message, self.user, query='原环境')['events'], [original_event])

    def test_unbound_environment_never_queries_another_cluster(self):
        self.environment.k8s_cluster_ids = []
        self.environment.save(update_fields=['k8s_cluster_ids'])
        with mock.patch('aiops.services._load_k8s_namespaced_resources') as resources, mock.patch('ops.k8s_views.get_k8s_summary_snapshot') as summary:
            services.query_k8s_resources(self.session, self.message, self.user, query='原环境', resource_type='deployments')
            services.query_k8s_cluster_summary(self.session, self.message, self.user, query='原环境', cluster_name=self.other_cluster.name)
        resources.assert_not_called()
        summary.assert_not_called()

    def test_graph_pins_cluster_for_summary_without_searching_question_words(self):
        with mock.patch('ops.k8s_views.get_k8s_summary_snapshot', return_value={}) as summary, mock.patch(
            'aiops.services._load_k8s_pods_for_environment', return_value=[],
        ) as pods, mock.patch('aiops.services._load_k8s_namespaced_resources', return_value=[]):
            result = self.run_graph()
        self.assertEqual(summary.call_args.args[0].id, self.cluster.id)
        self.assertEqual(pods.call_args.args[1], ['monitoring'])
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(result['metadata']['langgraph_thread_id'])
        self.assertEqual(checkpoint['k8s_cluster_id'], self.cluster.id)
        self.assertEqual(checkpoint['k8s_evidence']['query_k8s_cluster_summary']['summary']['count'], 1)
        self.assertEqual(checkpoint['k8s_evidence']['query_k8s_resources']['summary']['cluster_name'], self.cluster.name)

    def test_pod_fetch_failure_is_failed_tool_with_summary_error(self):
        with mock.patch('ops.k8s_views.get_k8s_summary_snapshot', return_value={}), mock.patch(
            'aiops.services._load_k8s_pods_for_environment', side_effect=RuntimeError('Pod fetch failed'),
        ):
            result = services.query_k8s_resources(self.session, self.message, self.user, query='原环境', cluster_name=self.cluster.name, resource_type='pods')
        self.assertEqual(result['summary']['error'], 'Pod fetch failed')
        self.assertEqual(AIOpsToolInvocation.objects.get(message=self.message, tool_name='query_k8s_cluster_summary').status, 'failed')
        self.assertEqual(AIOpsToolInvocation.objects.get(message=self.message, tool_name='query_k8s_resources').status, 'failed')

    def test_unfinished_v10_checkpoint_is_not_resumed(self):
        with mock.patch('aiops.langgraph_pilot._run_tool_call', side_effect=self.tool_result) as tool:
            with self.assertRaises(services.ChatJobLeaseLost):
                self.run_graph(progress_callback=self.stop_before('k8s_events'))
            completed = tool.call_count
            self.message.refresh_from_db()
            config = {'configurable': {'thread_id': self.message.metadata['langgraph_thread_id']}}
            langgraph_pilot.get_langgraph_chat_graph().update_state(config, {'graph_version': 10})
            with self.assertRaisesMessage(RuntimeError, '无法安全恢复旧 checkpoint'):
                self.run_graph()
        self.assertEqual(tool.call_count, completed)
