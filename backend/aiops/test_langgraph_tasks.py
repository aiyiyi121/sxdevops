import json
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from ops.models import HostTask, K8sCluster, TaskResource, TaskResourceGroup
from rbac.models import PermissionDefinition, Role
from rbac.services import ensure_builtin_rbac

from . import langgraph_pilot, services
from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsKnowledgeEnvironment, AIOpsMCPServer, AIOpsPendingAction, AIOpsToolInvocation


class LangGraphTaskTests(TestCase):
    def setUp(self):
        ensure_builtin_rbac()
        self.user = get_user_model().objects.create_user(username='graph-task-user')
        self.role = Role.objects.create(code='graph-task-role', name='Graph task role')
        self.role.permissions.add(*PermissionDefinition.objects.filter(code__in=[
            'aiops.chat.view', 'aiops.chat.analyze', 'aiops.task.generate', 'ops.task.resource.view', 'ops.k8s.view',
        ]))
        self.user.rbac_roles.add(self.role)
        self.agent_config = services.get_agent_config()
        self.server = AIOpsMCPServer.objects.get(name='任务中心 MCP')
        self.server.is_enabled = True
        self.server.save(update_fields=['is_enabled'])
        self.agent_config.enabled_mcp_server_ids = [self.server.id]
        self.agent_config.allow_action_execution = True
        self.agent_config.save(update_fields=['enabled_mcp_server_ids', 'allow_action_execution'])
        self.environment = TaskResourceGroup.objects.create(
            name='图任务测试环境', code='graph-task', group_type=TaskResourceGroup.GROUP_ENVIRONMENT,
        )
        self.knowledge_environment = AIOpsKnowledgeEnvironment.objects.create(
            name='图任务测试环境', task_resource_environment_ids=[self.environment.id],
        )
        self.resource = TaskResource.objects.create(
            name='graph-task-server', resource_type=TaskResource.RESOURCE_HOST,
            environment=self.environment, status=TaskResource.STATUS_ACTIVE, ip_address='10.20.30.40',
        )
        self.session = AIOpsChatSession.objects.create(
            user=self.user, title='graph-task', context={'current_environment': {'name':self.environment.name}},
        )
        self.message = AIOpsChatMessage.objects.create(
            session=self.session, role=AIOpsChatMessage.ROLE_USER,
            content='为图任务测试环境生成服务器巡检任务',
        )
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        environment_patch = mock.patch.dict('os.environ', {
            'AIOPS_LANGGRAPH_CHECKPOINT_BACKEND':'sqlite',
            'AIOPS_LANGGRAPH_CHECKPOINT_PATH': self.directory.name + '/checkpoints.sqlite3',
        })
        environment_patch.start()
        self.addCleanup(environment_patch.stop)
        langgraph_pilot.close_langgraph_resources()
        self.addCleanup(langgraph_pilot.close_langgraph_resources)
        provider_patch = mock.patch('aiops.services.get_active_provider', return_value=None)
        provider_patch.start()
        self.addCleanup(provider_patch.stop)

    def run_graph(self, **kwargs):
        return langgraph_pilot.run_langgraph_chat(self.session, self.message, self.user, self.message.content, **kwargs)

    def interrupt_before_draft(self):
        def emit(**kwargs):
            event = kwargs.get('tool_event') or {}
            if event.get('name') == 'generate_host_task' and event.get('status') == 'running':
                raise services.ChatJobLeaseLost('Controlled lease loss before draft')

        with self.assertRaises(services.ChatJobLeaseLost):
            self.run_graph(progress_callback=emit)
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id'])
        self.assertEqual(checkpoint['task_context']['resource_ids'], [self.resource.id])
        self.assertNotIn('result', checkpoint)

    def test_resources_are_checkpointed_and_resume_keeps_confirmation_boundary(self):
        self.interrupt_before_draft()
        self.assertEqual(AIOpsToolInvocation.objects.filter(session=self.session).count(), 1)
        langgraph_pilot.close_langgraph_resources()
        result = self.run_graph()
        self.assertEqual(result['tool_calls'], ['query_task_resources', 'generate_host_task'])
        self.assertEqual(result['pending_action_draft']['resource_ids'], [self.resource.id])
        self.assertEqual(AIOpsToolInvocation.objects.filter(session=self.session, tool_name='query_task_resources').count(), 1)
        self.assertFalse(HostTask.objects.exists())
        self.assertFalse(AIOpsPendingAction.objects.exists())
        assistant = AIOpsChatMessage.objects.create(session=self.session, role=AIOpsChatMessage.ROLE_ASSISTANT)
        services._apply_dispatch_result_to_message(self.session, assistant, result, self.user, question=self.message.content)
        self.assertEqual(AIOpsPendingAction.objects.filter(session=self.session).count(), 1)
        self.assertFalse(HostTask.objects.exists())
        replay = self.run_graph()
        services._apply_dispatch_result_to_message(self.session, assistant, replay, self.user, question=self.message.content)
        self.assertEqual(AIOpsPendingAction.objects.filter(session=self.session).count(), 1)
        self.assertEqual(AIOpsToolInvocation.objects.filter(session=self.session).count(), 2)
        nodes = [item['node'] for item in result['metadata']['langgraph_trace']]
        self.assertEqual(nodes[-7:], ['task_scope','task_resources','task_draft','task_synthesis','validate','action_guard','finalize'])

    def test_resume_after_draft_does_not_regenerate_it(self):
        original = services._build_evidence_bundle_result

        def stop_synthesis(**kwargs):
            if kwargs.get('execution_mode') == 'deterministic_task_generation':
                raise services.ChatJobLeaseLost('Controlled synthesis interruption')
            return original(**kwargs)

        with mock.patch('aiops.services._build_evidence_bundle_result', side_effect=stop_synthesis):
            with self.assertRaises(services.ChatJobLeaseLost):
                self.run_graph()
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id'])
        self.assertTrue(checkpoint['task_context']['draft'])
        langgraph_pilot.close_langgraph_resources()
        self.run_graph()
        self.assertEqual(AIOpsToolInvocation.objects.filter(session=self.session).count(), 2)
        self.assertFalse(HostTask.objects.exists())

    def test_revoked_permission_disabled_mcp_and_policy_block_resumed_draft(self):
        changes = ['permission','mcp','policy']
        for index, change in enumerate(changes):
            with self.subTest(change=change):
                self.message = AIOpsChatMessage.objects.create(session=self.session, role='user', content=f'为图任务测试环境生成服务器巡检任务 {index}')
                self.interrupt_before_draft()
                if change == 'permission':
                    self.role.permissions.remove(PermissionDefinition.objects.get(code='aiops.task.generate'))
                elif change == 'mcp':
                    self.server.is_enabled = False
                    self.server.save(update_fields=['is_enabled'])
                else:
                    self.agent_config.allow_action_execution = False
                    self.agent_config.save(update_fields=['allow_action_execution'])
                langgraph_pilot.close_langgraph_resources()
                result = self.run_graph()
                self.assertTrue(result['metadata']['task_generation_blocked'])
                self.assertIsNone(result['pending_action_draft'])
                audit = AIOpsToolInvocation.objects.get(message=self.message, tool_name='generate_host_task')
                self.assertEqual(audit.status, AIOpsToolInvocation.STATUS_FAILED)
                self.role.permissions.add(PermissionDefinition.objects.get(code='aiops.task.generate'))
                self.server.is_enabled = True
                self.server.save(update_fields=['is_enabled'])
                self.agent_config.allow_action_execution = True
                self.agent_config.save(update_fields=['allow_action_execution'])
        self.assertFalse(HostTask.objects.exists())

    def test_changed_target_blocks_draft_and_new_resources_do_not_expand_it(self):
        self.interrupt_before_draft()
        self.resource.status = TaskResource.STATUS_INACTIVE
        self.resource.save(update_fields=['status'])
        result = self.run_graph()
        self.assertIsNone(result['pending_action_draft'])
        self.assertIn('目标资源已变更', result['content'])
        self.resource.status = TaskResource.STATUS_ACTIVE
        self.resource.save(update_fields=['status'])
        self.message = AIOpsChatMessage.objects.create(session=self.session, role='user', content='为图任务测试环境生成服务器巡检任务')
        self.interrupt_before_draft()
        TaskResource.objects.create(name='new-server', resource_type=TaskResource.RESOURCE_HOST,
                                    environment=self.environment, status=TaskResource.STATUS_ACTIVE, ip_address='10.20.30.41')
        result = self.run_graph()
        self.assertEqual(result['pending_action_draft']['resource_ids'], [self.resource.id])

    def test_analysis_only_and_disabled_policy_do_not_call_task_tools(self):
        for analysis_only in [True, False]:
            with self.subTest(analysis_only=analysis_only):
                self.message = AIOpsChatMessage.objects.create(session=self.session, role='user', content='为图任务测试环境生成服务器巡检任务')
                self.agent_config.allow_action_execution = analysis_only
                self.agent_config.save(update_fields=['allow_action_execution'])
                with mock.patch('aiops.services._run_tool_call') as tool:
                    result = self.run_graph(analysis_only=analysis_only)
                tool.assert_not_called()
                self.assertIsNone(result['pending_action_draft'])
                self.assertTrue(result['metadata']['task_generation_blocked'])

    def test_empty_resource_selection_stops_before_draft_generation(self):
        self.resource.delete()
        result = self.run_graph()
        self.assertEqual(result['metadata']['block_reason'], 'task_resources_empty')
        self.assertIsNone(result['pending_action_draft'])
        self.assertFalse(AIOpsToolInvocation.objects.filter(session=self.session,tool_name='generate_host_task').exists())

    def test_missing_environment_stops_before_task_nodes(self):
        self.session.context = {}
        self.session.save(update_fields=['context'])
        self.message.content = '生成一份服务器巡检任务'
        self.message.save(update_fields=['content'])
        result = self.run_graph()
        self.assertTrue(result['metadata']['environment_required'])
        self.assertFalse(AIOpsToolInvocation.objects.filter(session=self.session).exists())

    def test_k8s_write_uses_resource_base_and_requires_explicit_namespace(self):
        cluster = K8sCluster.objects.create(name='graph-task-cluster', api_server='https://example.com:6443', status='connected')
        resource = TaskResource.objects.create(name='graph-task-cluster',resource_type=TaskResource.RESOURCE_K8S,
                                              environment=self.environment,cluster=cluster,status=TaskResource.STATUS_ACTIVE)
        self.message.content = '把图任务测试环境 monitoring 命名空间 deployment checkout 扩容到 3 个副本'
        self.message.save(update_fields=['content'])
        result = self.run_graph()
        self.assertIsNotNone(result['pending_action_draft'], result['content'])
        self.assertEqual(result['pending_action_draft']['resource_ids'], [resource.id])
        self.assertEqual(result['pending_action_draft']['payload']['namespace'], 'monitoring')
        self.assertEqual(result['pending_action_draft']['payload']['replicas'], 3)
        self.assertNotIn('query_k8s_resources',result['tool_calls'])
        self.message = AIOpsChatMessage.objects.create(session=self.session, role='user',content='把图任务测试环境 deployment checkout 扩容到 3 个副本')
        result = self.run_graph()
        self.assertIsNone(result['pending_action_draft'])
        self.assertIn('命名空间',result['content'])
        self.assertFalse(HostTask.objects.exists())

    def test_synthesis_rechecks_permissions_and_returns_no_stale_draft(self):
        with mock.patch('aiops.langgraph_tasks.task_synthesis_node', side_effect=services.ChatJobLeaseLost('stop synthesis')):
            langgraph_pilot.close_langgraph_resources()
            with self.assertRaises(services.ChatJobLeaseLost):
                self.run_graph()
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id'])
        self.assertTrue(checkpoint['task_context']['draft'])
        self.role.permissions.remove(PermissionDefinition.objects.get(code='aiops.task.generate'))
        langgraph_pilot.close_langgraph_resources()
        result = self.run_graph()
        self.assertIsNone(result['pending_action_draft'])
        self.assertTrue(result['metadata']['task_generation_blocked'])
        self.assertFalse(AIOpsPendingAction.objects.exists())

    def test_task_checkpoint_excludes_resource_credentials(self):
        self.resource.ssh_password = 'never-checkpoint-resource-password'
        self.resource.save(update_fields=['ssh_password'])
        self.run_graph()
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id'])
        payload = json.dumps(checkpoint, ensure_ascii=False)
        self.assertNotIn('never-checkpoint-resource-password', payload)
        self.assertNotIn('ssh_password', payload)
        self.assertNotIn('kubeconfig', payload)

    def test_lease_loss_in_formatter_does_not_checkpoint_success(self):
        from .models import AIOpsModelProvider

        provider = AIOpsModelProvider.objects.create(name='task-provider',base_url='https://example.com/v1',default_model='task-model')
        provider.set_api_key('test-key')
        provider.save(update_fields=['api_key_encrypted'])
        with mock.patch('aiops.services.get_active_provider', return_value=provider), mock.patch(
            'aiops.services._run_answer_formatter', side_effect=services.ChatJobLeaseLost('stop formatter'),
        ):
            with self.assertRaises(services.ChatJobLeaseLost):
                self.run_graph()
        checkpoint = langgraph_pilot.get_langgraph_chat_checkpoint(self.message.metadata['langgraph_thread_id'])
        self.assertNotIn('result',checkpoint)
        self.assertTrue(checkpoint['task_context']['draft'])

    def test_formatter_resume_rechecks_task_targets_without_creating_task(self):
        from .models import AIOpsModelProvider

        provider = AIOpsModelProvider.objects.create(name='task-format-provider', base_url='https://example.com/v1', default_model='task-model')
        provider.set_api_key('test-key')
        provider.save(update_fields=['api_key_encrypted'])

        def emit(**kwargs):
            current = (kwargs.get('metadata_updates') or {}).get('langgraph_current_node') or {}
            if current.get('node') == 'formatter_model' and current.get('status') == 'running':
                raise services.ChatJobLeaseLost('controlled task formatter interruption')

        with mock.patch('aiops.services.get_active_provider', return_value=provider), mock.patch('aiops.services._request_model_completion') as completion:
            with self.assertRaises(services.ChatJobLeaseLost):
                self.run_graph(progress_callback=emit)
            self.resource.ip_address = '10.20.30.41'
            self.resource.save(update_fields=['ip_address'])
            result = self.run_graph()
        completion.assert_not_called()
        self.assertIsNone(result['pending_action_draft'])
        self.assertEqual(result['metadata']['error_code'], 'formatter_permission_denied')
        self.assertFalse(HostTask.objects.exists())
        self.assertFalse(AIOpsPendingAction.objects.exists())

    def test_formatter_rejects_answer_conflicting_with_pending_task_draft(self):
        from .models import AIOpsModelProvider

        provider = AIOpsModelProvider.objects.create(name='task-fact-provider', base_url='https://example.com/v1', default_model='task-model')
        provider.set_api_key('test-key')
        provider.save(update_fields=['api_key_encrypted'])
        completion_payload = {'choices': [{'message': {'content': '结论：无法生成任务。\n执行概要：\n- 当前无法生成任务草稿。\n下一步：请重新查询。\n可继续查看：任务中心'}}]}
        with mock.patch('aiops.services.get_active_provider', return_value=provider), mock.patch(
            'aiops.services._request_model_completion', return_value=completion_payload,
        ) as completion:
            result = self.run_graph()
        self.assertEqual(completion.call_count, 3)
        self.assertTrue(result['pending_action_draft'])
        self.assertIn('草稿', result['content'])
        self.assertEqual(result['metadata']['formatter_mode'], 'fallback')
        self.assertFalse(HostTask.objects.exists())
        self.assertFalse(AIOpsPendingAction.objects.exists())
