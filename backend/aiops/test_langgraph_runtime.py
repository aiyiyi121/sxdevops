import json
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from rbac.models import PermissionDefinition, Role
from rbac.services import ensure_builtin_rbac
from ops.models import Alert

from . import langgraph_pilot, services
from .langgraph_runtime import build_agent_context
from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsMCPServer, AIOpsModelProvider, AIOpsToolInvocation


class LangGraphRuntimeTests(TestCase):
    def setUp(self):
        ensure_builtin_rbac()
        self.user = get_user_model().objects.create_user(username='graph-runtime-user')
        self.role = Role.objects.create(code='graph-runtime-role', name='Graph runtime role')
        self.role.permissions.add(*PermissionDefinition.objects.filter(code__in=[
            'aiops.chat.view', 'aiops.chat.analyze', 'aiops.knowledge.view',
        ]))
        self.user.rbac_roles.add(self.role)
        self.provider = AIOpsModelProvider.objects.create(
            name='graph-provider', base_url='https://example.com/v1', default_model='graph-model', is_enabled=True,
        )
        self.provider.set_api_key('checkpoint-must-not-contain-this-key')
        self.provider.save(update_fields=['api_key_encrypted'])
        self.agent_config = services.get_agent_config()
        self.server = AIOpsMCPServer.objects.get(name='知识图谱 MCP')
        self.server.is_enabled = True
        self.server.save(update_fields=['is_enabled'])
        self.agent_config.default_provider = self.provider
        self.agent_config.enabled_mcp_server_ids = [self.server.id]
        self.agent_config.save(update_fields=['default_provider', 'enabled_mcp_server_ids'])
        self.session = AIOpsChatSession.objects.create(user=self.user, title='graph-runtime')
        self.message = AIOpsChatMessage.objects.create(
            session=self.session, role=AIOpsChatMessage.ROLE_USER, content='检查资源关联',
        )
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.checkpoint_env = mock.patch.dict('os.environ', {
            'AIOPS_LANGGRAPH_CHECKPOINT_BACKEND': 'sqlite',
            'AIOPS_LANGGRAPH_CHECKPOINT_PATH': self.directory.name + '/checkpoints.sqlite3',
        })
        self.checkpoint_env.start()
        self.addCleanup(self.checkpoint_env.stop)
        langgraph_pilot.close_langgraph_resources()
        self.addCleanup(langgraph_pilot.close_langgraph_resources)
        self.context = self.build_context([self.server])
        self.runtime = mock.patch('aiops.services._build_chat_result_legacy', return_value={'_agent_context': self.context})
        self.runtime.start()
        self.addCleanup(self.runtime.stop)
        self.formatter = mock.patch('aiops.services._run_answer_formatter', return_value={'used': False})
        self.formatter.start()
        self.addCleanup(self.formatter.stop)

    def build_context(self, servers):
        tools, registry, clients, diagnostics = services._build_runtime_tool_registry(servers, self.user)
        try:
            return build_agent_context(
                provider=self.provider, active_mcp_servers=servers, active_skills=[],
                knowledge_environment={'name': 'prod'}, analysis_scope={'environment': 'prod'},
                selected_action=None, messages=[{'role': 'user', 'content': self.message.content}],
                tools=tools, registry=registry, mcp_diagnostics=diagnostics,
            )
        finally:
            for client in clients:
                client.close()

    def run_graph(self, **kwargs):
        return langgraph_pilot.run_langgraph_chat(self.session, self.message, self.user, self.message.content, **kwargs)

    def tool_plan(self, count=2, tool_name='query_knowledge_graph'):
        return {'choices': [{'message': {'tool_calls': [
            {'id': f'call_{index}', 'type': 'function', 'function': {'name': tool_name, 'arguments': '{}'}}
            for index in range(count)
        ]}}]}

    def tool_result(self):
        return {'tool_output': {'summary': {'node_count': 2}},
                'sections': [{'title': '关联证据', 'items': ['已找到两个资源']}],
                'citations': [], 'message_type': AIOpsChatMessage.TYPE_ANALYSIS}

    @mock.patch('aiops.services._request_model_completion')
    @mock.patch('aiops.services._run_tool_call')
    def test_resume_preserves_completed_plan_first_tool_and_call_ids(self, tool, completion):
        completion.side_effect = [self.tool_plan(), {'choices': [{'message': {'content': '已完成关联检查'}}]}]
        tool.side_effect = [self.tool_result(), services.ChatJobLeaseLost('worker lease moved'), self.tool_result()]
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph()
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id'])
        self.assertEqual(checkpoint['agent_context']['call_index'], 1)
        self.assertEqual(checkpoint['agent_context']['rounds'], 1)
        self.assertEqual(checkpoint['agent_context']['messages'][-1]['tool_call_id'], 'call_0')
        self.assertNotIn('result', checkpoint)
        langgraph_pilot.close_langgraph_resources()
        result = self.run_graph()
        replay = self.run_graph()
        self.assertEqual(result['content'], replay['content'])
        self.assertEqual(completion.call_count, 2)
        self.assertEqual(tool.call_count, 3)
        planning_messages = completion.call_args.args[1]['messages']
        self.assertEqual([item['tool_call_id'] for item in planning_messages if item['role'] == 'tool'], ['call_0', 'call_1'])
        self.assertEqual(result['metadata']['langgraph_agent_rounds'], 2)

    @mock.patch('aiops.services._request_model_completion')
    def test_no_tool_retry_is_bounded(self, completion):
        completion.return_value = {'choices': [{'message': {'content': '没有证据的回答'}}]}
        result = self.run_graph()
        self.assertEqual(result['metadata']['error_code'], 'no_tool_called')
        self.assertEqual(completion.call_count, 2)

    @mock.patch('aiops.services._request_model_completion')
    @mock.patch('aiops.services._run_tool_call')
    def test_round_and_tool_budgets_fit_graph_limit(self, tool, completion):
        completion.return_value = self.tool_plan(count=8)
        tool.return_value = self.tool_result()
        result = self.run_graph()
        self.assertEqual(completion.call_count, 6)
        self.assertEqual(tool.call_count, 48)
        self.assertEqual(result['metadata']['langgraph_agent_rounds'], 6)

    @mock.patch('aiops.services._request_model_completion')
    @mock.patch('aiops.services._run_tool_call')
    def test_excessive_tool_plan_stops_before_any_tool(self, tool, completion):
        completion.return_value = self.tool_plan(count=9)
        result = self.run_graph()
        self.assertEqual(result['metadata']['error_code'], 'runtime_error')
        tool.assert_not_called()

    @mock.patch('aiops.services._request_model_completion')
    @mock.patch('aiops.services._run_tool_call')
    def test_revoked_tool_permission_is_audited_on_resume(self, tool, completion):
        completion.return_value = self.tool_plan()
        tool.side_effect = [self.tool_result(), services.ChatJobLeaseLost('lease moved')]
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph()
        self.role.permissions.remove(PermissionDefinition.objects.get(code='aiops.knowledge.view'))
        result = self.run_graph()
        self.assertEqual(tool.call_count, 2)
        self.assertEqual(completion.call_count, 1)
        audit = AIOpsToolInvocation.objects.get(session=self.session)
        self.assertEqual(audit.status, AIOpsToolInvocation.STATUS_FAILED)
        self.assertIn('未授权', audit.response_summary['error'])
        self.assertEqual(result['metadata']['formatter_mode'], 'fallback')

    @mock.patch('aiops.services._request_model_completion')
    def test_lease_loss_during_planning_is_not_checkpointed_as_failure(self, completion):
        completion.side_effect = services.ChatJobLeaseLost('lease moved')
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph()
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id'])
        self.assertEqual(checkpoint['agent_context']['rounds'], 0)
        self.assertNotIn('result', checkpoint)

    @mock.patch('aiops.services._request_model_completion')
    @mock.patch('aiops.services._run_tool_call')
    def test_lease_loss_during_synthesis_preserves_tool_evidence(self, tool, completion):
        completion.side_effect = [self.tool_plan(count=1), {'choices': [{'message': {'content': '已检查'}}]}]
        tool.return_value = self.tool_result()
        with mock.patch('aiops.services._run_answer_formatter', side_effect=services.ChatJobLeaseLost('lease moved')):
            with self.assertRaises(services.ChatJobLeaseLost):
                self.run_graph()
        langgraph_pilot.close_langgraph_resources()
        self.run_graph()
        self.assertEqual(tool.call_count, 1)
        self.assertEqual(completion.call_count, 2)

    @mock.patch('aiops.services._request_model_completion')
    @mock.patch('aiops.services._run_tool_call')
    def test_lease_loss_after_formatter_does_not_save_synthesis_result(self, tool, completion):
        completion.side_effect = [self.tool_plan(count=1), {'choices': [{'message': {'content': '已检查'}}]}]
        tool.return_value = self.tool_result()

        def callback(**kwargs):
            if (kwargs.get('step') or {}).get('title') == '工具链回复完成':
                raise services.ChatJobLeaseLost('lease moved after formatter')

        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(progress_callback=callback)
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id'])
        self.assertNotIn('result', checkpoint)
        self.assertEqual(len(checkpoint['agent_context']['outputs']), 1)

    @mock.patch('aiops.services._create_mcp_client_session')
    @mock.patch('aiops.services._request_model_completion')
    def test_external_client_reconnects_and_checkpoint_has_no_credentials(self, completion, create_client):
        server = AIOpsMCPServer.objects.create(
            name='Graph external', server_type=AIOpsMCPServer.SERVER_HTTP, endpoint_or_command='https://example.com/mcp',
            tool_whitelist=['query_service'], auth_config={'token': 'never-checkpoint-mcp-token'},
        )
        self.agent_config.enabled_mcp_server_ids = [server.id]
        self.agent_config.save(update_fields=['enabled_mcp_server_ids'])
        clients = [mock.Mock(), mock.Mock()]
        for client in clients:
            client.list_tools.return_value = [{'name': 'query_service', 'description': 'Read service',
                                               'inputSchema': {'type': 'object', 'properties': {}}}]
            client.call_tool.return_value = {'content': [{'type': 'text', 'text': 'service ready'}]}
        create_client.side_effect = clients
        self.context = self.build_context([server])
        alias = next(iter(self.context['registry']))
        with mock.patch('aiops.services._build_chat_result_legacy', return_value={'_agent_context': self.context}):
            completion.side_effect = [self.tool_plan(count=1, tool_name=alias), {'choices': [{'message': {'content': '已检查'}}]}]
            self.run_graph()
        self.assertEqual(create_client.call_count, 2)
        clients[0].call_tool.assert_not_called()
        clients[1].call_tool.assert_called_once_with('query_service', {})
        for client in clients:
            client.close.assert_called_once()
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id'])
        payload = json.dumps(checkpoint, ensure_ascii=False)
        for forbidden in ['never-checkpoint-mcp-token', 'checkpoint-must-not-contain-this-key', 'client_session', 'api_key_encrypted', 'auth_config']:
            self.assertNotIn(forbidden, payload)

    @mock.patch('aiops.services._request_model_completion')
    @mock.patch('aiops.services._run_tool_call')
    def test_analysis_only_cannot_execute_unregistered_task_generator(self, tool, completion):
        completion.side_effect = [self.tool_plan(count=1, tool_name='generate_host_task'),
                                  {'choices': [{'message': {'content': '工具不可用'}}]}]
        result = self.run_graph(analysis_only=True)
        tool.assert_not_called()
        self.assertIsNone(result['pending_action_draft'])
        self.assertEqual(result['metadata']['langgraph_action_decision'], 'none')

    @mock.patch('aiops.services._request_model_completion')
    @mock.patch('aiops.services._run_tool_call')
    def test_disabled_server_blocks_pending_tool_after_restart(self, tool, completion):
        completion.return_value = self.tool_plan()
        tool.side_effect = [self.tool_result(), services.ChatJobLeaseLost('lease moved')]
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph()
        self.server.is_enabled = False
        self.server.save(update_fields=['is_enabled'])
        langgraph_pilot.close_langgraph_resources()
        self.run_graph()
        self.assertEqual(tool.call_count, 2)
        self.assertEqual(AIOpsToolInvocation.objects.get(session=self.session).status, AIOpsToolInvocation.STATUS_FAILED)

    @mock.patch('aiops.services._request_model_completion')
    @mock.patch('aiops.services._run_tool_call')
    def test_alert_evidence_keeps_facts_without_checkpointing_model_objects(self, tool, completion):
        alert = Alert.objects.create(title='Scoped latency warning', source='prometheus', level='warning')
        tool.return_value = {**self.tool_result(), 'tool_output': {'alerts': [alert], 'summary': {'count': 1}}}
        completion.side_effect = [self.tool_plan(count=1), {'choices': [{'message': {'content': '已有证据'}}]}]
        self.run_graph()
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id'])
        stored = checkpoint['agent_context']['outputs'][0]['tool_output']['alerts'][0]
        self.assertEqual(stored['id'], alert.id)
        self.assertEqual(stored['title'], alert.title)
        self.assertIsInstance(stored, dict)

    @mock.patch('aiops.services._create_mcp_client_session')
    @mock.patch('aiops.services._request_model_completion')
    def test_changed_external_schema_is_denied_and_client_closed(self, completion, create_client):
        server = AIOpsMCPServer.objects.create(name='Schema external', server_type=AIOpsMCPServer.SERVER_HTTP,
                                              tool_whitelist=['query_service'])
        self.agent_config.enabled_mcp_server_ids = [server.id]
        self.agent_config.save(update_fields=['enabled_mcp_server_ids'])
        discovery, resumed = mock.Mock(), mock.Mock()
        discovery.list_tools.return_value = [{'name': 'query_service', 'inputSchema': {'type': 'object', 'properties': {}}}]
        resumed.list_tools.return_value = [{'name': 'query_service', 'inputSchema': {'type': 'object', 'properties': {'host': {'type': 'string'}}}}]
        create_client.side_effect = [discovery, resumed]
        context = self.build_context([server])
        alias = next(iter(context['registry']))
        completion.side_effect = [self.tool_plan(count=1, tool_name=alias), {'choices': [{'message': {'content': '参数已变化'}}]}]
        with mock.patch('aiops.services._build_chat_result_legacy', return_value={'_agent_context': context}):
            self.run_graph()
        resumed.call_tool.assert_not_called()
        resumed.close.assert_called_once()
        audit = AIOpsToolInvocation.objects.get(session=self.session)
        self.assertIn('参数定义已变化', audit.response_summary['error'])
