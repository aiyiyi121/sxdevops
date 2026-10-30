import json
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rbac.models import PermissionDefinition, Role
from rbac.services import ensure_builtin_rbac

from . import langgraph_pilot, services
from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsMCPServer, AIOpsModelInvocation, AIOpsModelProvider, AIOpsPendingAction, AIOpsSkill


VALID_ANSWER = '结论：已读取关联证据，需要结合服务状态判断影响。\n关键点：\n- 两个资源存在依赖关系。\n建议操作：\n- 核对服务健康状态。\n可继续查看：知识图谱'


class LangGraphFormatterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username='formatter-regression', password='test')
        self.session = AIOpsChatSession.objects.create(user=self.user)
        self.message = self.new_message()
        self.provider = AIOpsModelProvider.objects.create(
            name='formatter-provider', base_url='https://example.com/v1', default_model='formatter-model',
        )
        self.provider.set_api_key('formatter-secret-must-not-be-checkpointed')
        self.provider.save(update_fields=['api_key_encrypted'])
        self.agent_config = services.get_agent_config()
        self.skill = AIOpsSkill.objects.get(slug=services.ANSWER_FORMATTER_SKILL_SLUG)
        self.server = AIOpsMCPServer.objects.get(name='知识图谱 MCP')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        checkpoint = mock.patch.dict('os.environ', {
            'AIOPS_LANGGRAPH_CHECKPOINT_BACKEND': 'sqlite',
            'AIOPS_LANGGRAPH_CHECKPOINT_PATH': self.directory.name + '/formatter.sqlite3',
        })
        checkpoint.start()
        self.addCleanup(checkpoint.stop)
        langgraph_pilot.close_langgraph_resources()
        self.addCleanup(langgraph_pilot.close_langgraph_resources)
        self.runtime = mock.patch('aiops.services._build_chat_result_legacy', side_effect=self.build_result)
        self.runtime.start()
        self.runtime_mock = services._build_chat_result_legacy
        self.addCleanup(self.runtime.stop)
        self.outputs = [{'tool_name': 'query_knowledge_graph', 'tool_output': {'summary': {'node_count': 2}}}]
        self.model_error_policy = 'fallback'
        self.draft = None

    def new_message(self, question='查看资源依赖'):
        return AIOpsChatMessage.objects.create(session=self.session, role='user', content=question)

    def build_result(self, *args, **kwargs):
        if self.model_error_policy == 'error':
            return services._finalize_tool_runtime_answer(
                provider=self.provider, question=self.message.content, knowledge_environment={'name': '原环境'},
                analysis_scope={}, active_skills=[self.skill], selected_action=None, mcp_diagnostics=[],
                sections=[{'title': '证据', 'items': ['两个资源存在依赖关系']}], citations=[],
                executed_tool_names=['query_knowledge_graph'], collected_tool_outputs=self.outputs,
                pending_action_draft=None, message_type='analysis', final_content='', emit=lambda **kwargs: None,
            )
        return services._build_evidence_bundle_result(
            question=self.message.content, scoped_question=self.message.content,
            knowledge_environment={'name': '原环境'}, analysis_scope={}, provider=self.provider,
            active_skills=[self.skill], sections=[{'title': '证据', 'items': ['两个资源存在依赖关系']}],
            citations=[], tool_names=[item['tool_name'] for item in self.outputs], collected_tool_outputs=self.outputs,
            execution_mode='formatter_regression', extra_metadata={'preserved_marker': 'keep'},
            pending_action_draft=self.draft,
        )

    def run_graph(self, **kwargs):
        return langgraph_pilot.run_langgraph_chat(
            self.session, self.message, self.user, self.message.content, analysis_only=kwargs.pop('analysis_only', True), **kwargs,
        )

    def stop_before(self, node):
        def emit(**kwargs):
            current = (kwargs.get('metadata_updates') or {}).get('langgraph_current_node') or {}
            if current.get('node') == node and current.get('status') == 'running':
                raise services.ChatJobLeaseLost('controlled formatter interruption')
        return emit

    def completion(self, content):
        return {'choices': [{'message': {'content': content}}]}

    @mock.patch('aiops.services._request_model_completion')
    def test_model_result_resumes_at_check_without_repeated_request(self, completion):
        completion.return_value = self.completion(VALID_ANSWER)
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(progress_callback=self.stop_before('formatter_check'))
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id'])
        self.assertEqual(checkpoint['formatter_context']['attempts'], 1)
        self.assertEqual(
            checkpoint['formatter_context']['content'],
            services._normalize_formatter_output(VALID_ANSWER),
        )
        self.assertNotIn('formatter-secret', json.dumps(checkpoint))
        langgraph_pilot.close_langgraph_resources()
        result = self.run_graph()
        replay = self.run_graph()
        self.assertEqual(completion.call_count, 1)
        self.assertEqual(self.runtime_mock.call_count, 1)
        self.assertEqual(result['content'], replay['content'])
        self.assertEqual(result['metadata']['formatter_attempts'], 1)
        self.assertTrue(result['metadata']['langgraph_formatter_checkpointed'])
        self.assertEqual(result['metadata']['preserved_marker'], 'keep')
        self.assertTrue(result['metadata']['response_blocks'])
        self.assertEqual(result['metadata']['skill_trace']['items'][0]['status'], 'called')

    @mock.patch('aiops.services._request_model_completion')
    def test_resume_at_repair_preserves_issue_and_prior_attempt(self, completion):
        completion.side_effect = [self.completion('太短'), self.completion(VALID_ANSWER)]
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(progress_callback=self.stop_before('formatter_repair'))
        result = self.run_graph()
        self.assertEqual(completion.call_count, 2)
        self.assertEqual(result['metadata']['formatter_attempts'], 2)
        self.assertIn('上一次整形存在的问题', completion.call_args.args[1]['messages'][1]['content'])
        self.assertEqual(len(result['metadata']['formatter_checks']), 2)
        self.assertTrue(self.message.graph_node_runs.filter(node='formatter_check', status='failed').exists())

    @mock.patch('aiops.services._request_model_completion')
    def test_invalid_output_has_three_attempts_and_independent_fallback(self, completion):
        completion.return_value = self.completion('太短')
        result = self.run_graph()
        self.assertEqual(completion.call_count, 3)
        self.assertEqual(result['metadata']['formatter_mode'], 'fallback')
        self.assertEqual(result['metadata']['formatter_reason'], 'invalid_formatter_output')
        self.assertIn('两个资源', result['content'])
        self.assertTrue(self.message.graph_node_runs.filter(node='formatter_fallback', status='completed').exists())

    @mock.patch('aiops.services._request_model_completion')
    def test_alert_facts_have_four_attempts_and_survive_fallback(self, completion):
        self.message = self.new_message('查看原环境告警')
        self.outputs = [{'tool_name': 'query_alerts', 'tool_output': {
            'summary': {'count': 1}, 'alerts': [{'title': '连接超时', 'level': 'critical', 'status': 'active'}],
        }}]
        completion.return_value = self.completion('结论：当前没有告警。\n依据：\n- 未查到告警。\n建议操作：\n- 继续观察。\n可继续查看：告警中心')
        result = self.run_graph()
        self.assertEqual(completion.call_count, 4)
        self.assertEqual(result['metadata']['formatter_attempts'], 4)
        self.assertIn('连接超时', result['content'])
        self.assertNotIn('当前没有告警', result['content'])

    @mock.patch('aiops.services._request_model_completion')
    def test_model_error_falls_back_for_evidence_bundle(self, completion):
        completion.side_effect = services.AIOpsModelCallError('provider unavailable')
        result = self.run_graph()
        self.assertEqual(result['message_type'], 'analysis')
        self.assertIn('两个资源', result['content'])
        self.assertEqual(result['metadata']['formatter_reason'], 'model_api_error')
        self.assertEqual(completion.call_count, 1)

    @mock.patch('aiops.services._request_model_completion')
    def test_general_runtime_preserves_model_api_error_policy(self, completion):
        self.model_error_policy = 'error'
        completion.side_effect = services.AIOpsModelCallError('provider unavailable')
        result = self.run_graph()
        self.assertEqual(result['message_type'], 'error')
        self.assertEqual(result['metadata']['error_code'], 'llm_api_error')
        self.assertEqual(completion.call_count, 1)

    @mock.patch('aiops.services._request_model_completion')
    def test_lease_loss_interrupts_model_without_using_fallback(self, completion):
        completion.side_effect = [services.ChatJobLeaseLost('lease moved'), self.completion(VALID_ANSWER)]
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph()
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id'])
        self.assertEqual(checkpoint['formatter_context']['attempts'], 0)
        result = self.run_graph()
        self.assertEqual(result['metadata']['formatter_attempts'], 1)

    @mock.patch('aiops.services._request_model_completion')
    def test_skill_disabled_on_resume_does_not_call_model(self, completion):
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(progress_callback=self.stop_before('formatter_model'))
        self.skill.is_enabled = False
        self.skill.save(update_fields=['is_enabled'])
        result = self.run_graph()
        completion.assert_not_called()
        self.assertEqual(result['metadata']['formatter_reason'], 'formatter_skill_disabled')

    @mock.patch('aiops.services._request_model_completion')
    def test_provider_disabled_on_resume_falls_back_without_switching(self, completion):
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(progress_callback=self.stop_before('formatter_model'))
        self.provider.is_enabled = False
        self.provider.save(update_fields=['is_enabled'])
        result = self.run_graph()
        completion.assert_not_called()
        self.assertEqual(result['metadata']['formatter_reason'], 'formatter_error')

    @mock.patch('aiops.services._request_model_completion')
    def test_revoked_permission_on_resume_excludes_cached_answer_and_blocks_model(self, completion):
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(progress_callback=self.stop_before('formatter_model'))
        self.user.is_superuser = False
        self.user.is_staff = False
        self.user.save(update_fields=['is_superuser', 'is_staff'])
        result = self.run_graph()
        completion.assert_not_called()
        self.assertNotIn('两个资源', result['content'])
        self.assertEqual(result['metadata']['error_code'], 'formatter_permission_denied')
        self.assertFalse(result['citations'])
        self.assertFalse(result['tool_calls'])

    @mock.patch('aiops.services._request_model_completion')
    def test_disabled_evidence_mcp_blocks_cached_model_result_at_finish(self, completion):
        completion.return_value = self.completion(VALID_ANSWER)
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(progress_callback=self.stop_before('formatter_finish'))
        self.server.is_enabled = False
        self.server.save(update_fields=['is_enabled'])
        result = self.run_graph()
        self.assertEqual(completion.call_count, 1)
        self.assertNotIn('两个资源', result['content'])
        self.assertEqual(result['metadata']['error_code'], 'formatter_permission_denied')

    @mock.patch('aiops.services._request_model_completion')
    def test_legacy_formatter_keeps_local_loop(self, completion):
        completion.side_effect = [self.completion('太短'), self.completion(VALID_ANSWER)]
        result = self.build_result()
        self.assertEqual(result['metadata']['formatter_attempts'], 2)
        self.assertEqual(completion.call_count, 2)
        self.assertNotIn('langgraph_formatter_checkpointed', result['metadata'])

    @mock.patch('aiops.services.requests.post')
    def test_formatter_model_audit_links_to_message_and_resume_does_not_duplicate(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            **self.completion(VALID_ANSWER), 'usage': {'prompt_tokens': 15, 'completion_tokens': 10, 'total_tokens': 25},
        }
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(progress_callback=self.stop_before('formatter_check'))
        self.run_graph()
        self.assertEqual(post.call_count, 1)
        audit = AIOpsModelInvocation.objects.get(message=self.message)
        self.assertEqual(audit.session_id, self.session.id)
        self.assertEqual(audit.purpose, AIOpsModelInvocation.PURPOSE_ANSWER_FORMATTING)
        self.assertEqual(audit.total_tokens, 25)

    @mock.patch('aiops.services._request_model_completion')
    def test_provider_endpoint_change_on_resume_does_not_send_evidence(self, completion):
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(progress_callback=self.stop_before('formatter_model'))
        self.provider.base_url = 'https://other.example.com/v1'
        self.provider.save(update_fields=['base_url'])
        result = self.run_graph()
        completion.assert_not_called()
        self.assertEqual(result['metadata']['formatter_reason'], 'formatter_error')

    @mock.patch('aiops.services._request_model_completion')
    def test_skill_role_change_after_check_discards_saved_model_answer(self, completion):
        completion.return_value = self.completion(VALID_ANSWER)
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(progress_callback=self.stop_before('formatter_finish'))
        self.skill.allowed_role_codes = ['unassigned-role']
        self.skill.save(update_fields=['allowed_role_codes'])
        result = self.run_graph()
        self.assertEqual(completion.call_count, 1)
        self.assertEqual(result['metadata']['formatter_reason'], 'formatter_skill_disabled')
        self.assertNotIn('已读取关联证据', result['content'])

    @mock.patch('aiops.services._request_model_completion')
    def test_log_fact_conflict_is_repaired(self, completion):
        self.outputs = [{'tool_name': 'query_logs', 'tool_output': {
            'summary': {'count': 2, 'service': 'order'},
            'logs': [{'message': 'connect timeout', 'level': 'error'}, {'message': 'connect timeout', 'level': 'error'}],
        }}]
        completion.return_value = self.completion('结论：当前没有日志。\n依据：\n- 没有命中日志。\n建议操作：\n- 继续观察。\n可继续查看：日志中心')
        result = self.run_graph()
        self.assertEqual(completion.call_count, 3)
        self.assertTrue(all('工具事实冲突' in item['issue'] for item in result['metadata']['formatter_checks']))

    @mock.patch('aiops.services._request_model_completion')
    def test_revoked_permission_before_finalize_excludes_completed_model_content(self, completion):
        completion.return_value = self.completion(VALID_ANSWER)
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(progress_callback=self.stop_before('finalize'))
        self.user.is_superuser = False
        self.user.is_staff = False
        self.user.save(update_fields=['is_superuser', 'is_staff'])
        result = self.run_graph()
        self.assertEqual(completion.call_count, 1)
        self.assertNotIn('两个资源', result['content'])
        self.assertEqual(result['metadata']['error_code'], 'formatter_permission_denied')

    def prepare_cmdb_draft_user(self):
        ensure_builtin_rbac()
        self.user.is_superuser = False
        self.user.is_staff = False
        self.user.save(update_fields=['is_superuser', 'is_staff'])
        role = Role.objects.create(code='formatter-cmdb', name='Formatter CMDB')
        role.permissions.add(*PermissionDefinition.objects.filter(code__in=['aiops.chat.view', 'cmdb.ci.manage']))
        self.user.rbac_roles.add(role)
        self.draft = {'action_type': AIOpsPendingAction.ACTION_CREATE_CMDB_ASSET,
                      'name': '待确认资产', 'title': '新增 CMDB 资产', 'form_values': {'name': '待确认资产'}}
        self.outputs = [{'tool_name': 'create_cmdb_asset_draft', 'tool_output': {'requires_confirmation': True}}]
        return role

    @mock.patch('aiops.services._request_model_completion')
    def test_cmdb_draft_uses_asset_permission_without_requiring_task_generation(self, completion):
        self.prepare_cmdb_draft_user()
        completion.return_value = self.completion('结论：已生成待确认资产草稿，确认后才会写入 CMDB。\n执行概要：\n- 资产名称待确认资产。\n下一步：请确认资产表单。\n可继续查看：CMDB 资产台账')
        self.assertFalse(services._tool_allowed(self.user, 'generate_host_task'))
        result = self.run_graph(analysis_only=False)
        self.assertEqual(completion.call_count, 1)
        self.assertEqual(result['pending_action_draft'], self.draft)
        self.assertEqual(result['metadata']['formatter_reason'], 'formatted')
        self.assertFalse(AIOpsPendingAction.objects.filter(session=self.session).exists())

    @mock.patch('aiops.services._request_model_completion')
    def test_revoked_cmdb_draft_permission_discards_cached_form(self, completion):
        role = self.prepare_cmdb_draft_user()
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(analysis_only=False, progress_callback=self.stop_before('formatter_model'))
        role.permissions.remove(PermissionDefinition.objects.get(code='cmdb.ci.manage'))
        result = self.run_graph(analysis_only=False)
        completion.assert_not_called()
        self.assertIsNone(result['pending_action_draft'])
        self.assertNotIn('待确认资产', result['content'])
        self.assertEqual(result['metadata']['error_code'], 'formatter_permission_denied')

    @mock.patch('aiops.services._request_model_completion')
    def test_native_change_query_preserves_existing_permissions_without_mcp_registration(self, completion):
        self.outputs = [{'tool_name': 'query_recent_changes', 'tool_output': {'summary': {'count': 1}}}]
        completion.return_value = self.completion(VALID_ANSWER)
        result = self.run_graph()
        self.assertEqual(completion.call_count, 1)
        self.assertEqual(result['metadata']['formatter_reason'], 'formatted')

    @mock.patch('aiops.services._request_model_completion')
    def test_native_workorders_rechecks_each_original_permission_on_resume(self, completion):
        self.outputs = [{'tool_name': 'query_workorders', 'tool_output': {'summary': {'count': 2}}}]
        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(progress_callback=self.stop_before('formatter_model'))
        ensure_builtin_rbac()
        self.user.is_superuser = False
        self.user.is_staff = False
        self.user.save(update_fields=['is_superuser', 'is_staff'])
        role = Role.objects.create(code='formatter-deployments', name='Formatter deployments')
        role.permissions.add(*PermissionDefinition.objects.filter(code__in=['aiops.chat.view', 'ops.deployment.view']))
        self.user.rbac_roles.add(role)
        result = self.run_graph()
        completion.assert_not_called()
        self.assertNotIn('两个资源', result['content'])
        self.assertEqual(result['metadata']['error_code'], 'formatter_permission_denied')
