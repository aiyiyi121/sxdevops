from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from rbac.models import PermissionDefinition, Role
from rbac.services import ensure_builtin_rbac

from .langgraph_pilot import _chat_route_node, _chat_policy_node, _chat_after_policy, _is_chat_change_correlation_question
from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsSkill, AIOpsMCPServer
from .serializers import AIOpsAuditTraceReader
from .services import (
    _action_registry_item_by_code,
    _dispatch_with_tool_runtime,
    _get_selected_mcp_servers,
    _get_selected_skills,
    _resolve_question_category_action,
    _skills_for_action,
    _upsert_action_decision_trace,
    build_skill_marketplace_catalog,
    bootstrap_payload_for_user,
    create_external_task,
    get_agent_config,
    list_capabilities,
    update_capability_skills,
)


class AIOpsCapabilityTests(TestCase):
    def setUp(self):
        ensure_builtin_rbac()
        self.user = get_user_model().objects.create_user(username='capability-admin', password='test-password')
        self.user.rbac_roles.add(Role.objects.get(code='platform-admin'))
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        get_agent_config()

    def restricted_user(self):
        role = Role.objects.create(code='capability-reader', name='能力读者')
        role.permissions.add(*PermissionDefinition.objects.filter(code__in=['aiops.chat.view', 'aiops.chat.analyze', 'cmdb.ci.view']))
        user = get_user_model().objects.create_user(username='capability-reader', password='test-password')
        user.rbac_roles.add(role)
        return user

    def test_question_scope_persists_filters_bootstrap_and_accepts_empty(self):
        response = self.client.put('/api/aiops/admin/config/', {'enabled_capability_codes': ['cmdb', 'cmdb']}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['enabled_capability_codes'], ['cmdb'])
        self.assertEqual([item['code'] for item in bootstrap_payload_for_user(self.user)['capabilities']], ['cmdb'])
        management = self.client.get('/api/aiops/admin/capabilities/').data['capabilities']
        self.assertEqual(len(management), 6)
        disabled = next(item for item in management if item['code'] == 'troubleshoot')
        self.assertFalse(disabled['is_enabled'])
        self.assertIn('策略中停用', disabled['available_reason'])
        response = self.client.put('/api/aiops/admin/config/', {'enabled_capability_codes': []}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_agent_config().enabled_capability_codes, [])
        self.assertEqual(bootstrap_payload_for_user(self.user)['capabilities'], [])

    def test_question_scope_rejects_unknown_values_and_requires_manage_permission(self):
        response = self.client.put('/api/aiops/admin/config/', {'enabled_capability_codes': ['unknown']}, format='json')
        self.assertEqual(response.status_code, 400)
        self.client.force_authenticate(self.restricted_user())
        response = self.client.put('/api/aiops/admin/config/', {'enabled_capability_codes': []}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(get_agent_config().enabled_capability_codes), 6)

    def test_disabled_question_scope_blocks_legacy_handlers_external_tasks_and_dispatch(self):
        config = get_agent_config()
        config.enabled_capability_codes = ['cmdb']
        config.save(update_fields=['enabled_capability_codes'])
        self.assertFalse(_resolve_question_category_action('troubleshoot', '排查 Pod 重启', self.user)['available'])
        for code in ['troubleshoot', 'k8s.diagnose', 'event.analysis', 'host_task.generate']:
            with self.assertRaisesMessage(ValueError, '策略中停用'):
                create_external_task({'action_code': code}, self.user)
        session = AIOpsChatSession.objects.create(user=self.user)
        for category, question in [('log.query_generate', '查询 ERROR 日志'), ('auto', '查询最近一小时 ERROR 日志')]:
            message = AIOpsChatMessage.objects.create(session=session, role='user', content=question, metadata={'question_category': category})
            with mock.patch('aiops.services._direct_tool_fastpath') as tool, mock.patch('aiops.services._resolve_chat_environment') as environment:
                result = _dispatch_with_tool_runtime(session, message, self.user, question)
            self.assertIn('策略中停用', result['content'])
            tool.assert_not_called()
            environment.assert_not_called()

    def test_graph_scope_guard_stops_automatic_lanes_before_tool_nodes(self):
        config = get_agent_config()
        config.enabled_capability_codes = ['cmdb']
        config.save(update_fields=['enabled_capability_codes'])
        session = AIOpsChatSession.objects.create(user=self.user)
        message = AIOpsChatMessage.objects.create(session=session, role='user', content='排查 Pod 重启', metadata={'question_category': 'auto'})
        state = {'session_id': session.id, 'message_id': message.id, 'user_id': self.user.id, 'question': message.content, 'route': 'k8s'}
        result = _chat_policy_node(state)
        self.assertIn('策略中停用', result['result']['content'])
        self.assertEqual(_chat_after_policy({**state, **result}), 'validate')

    def test_asset_switches_are_authoritative_and_legacy_selection_has_no_effect(self):
        config = get_agent_config()
        enabled_skill = AIOpsSkill.objects.create(name='启用技能', slug='scope-on', is_enabled=True)
        disabled_skill = AIOpsSkill.objects.create(name='停用技能', slug='scope-off', is_enabled=False)
        enabled_mcp = AIOpsMCPServer.objects.create(name='启用服务', is_enabled=True)
        disabled_mcp = AIOpsMCPServer.objects.create(name='停用服务', is_enabled=False)
        config.enabled_skill_ids = [disabled_skill.id]
        config.enabled_mcp_server_ids = [disabled_mcp.id]
        config.save(update_fields=['enabled_skill_ids', 'enabled_mcp_server_ids'])
        self.assertIn(enabled_skill, _get_selected_skills(config, self.user))
        self.assertNotIn(disabled_skill, _get_selected_skills(config, self.user))
        self.assertIn(enabled_mcp, _get_selected_mcp_servers(config))
        self.assertNotIn(disabled_mcp, _get_selected_mcp_servers(config))
        # Default-off built-ins must retain an explicit enable after subsequent bootstrap.
        builtin = AIOpsMCPServer.objects.filter(is_builtin=True, is_enabled=False).first()
        if builtin:
            builtin.is_enabled = True
            builtin.save(update_fields=['is_enabled'])
            get_agent_config()
            builtin.refresh_from_db()
            self.assertTrue(builtin.is_enabled)

    def test_chat_and_management_share_six_capability_codes(self):
        expected = {'troubleshoot', 'event.analysis', 'log.query_generate', 'slo.analysis', 'host_task.generate', 'cmdb'}
        bootstrap = bootstrap_payload_for_user(self.user)
        public = self.client.get('/api/aiops/capabilities/')
        management = self.client.get('/api/aiops/admin/capabilities/')
        self.assertEqual(public.status_code, 200)
        self.assertEqual(management.status_code, 200)
        for items in [bootstrap['capabilities'], public.data['capabilities'], management.data['capabilities']]:
            self.assertEqual({item['code'] for item in items}, expected)
            self.assertEqual(next(item['display_name'] for item in items if item['code'] == 'event.analysis'), '事件分析')

    def test_capability_mount_is_authoritative_and_survives_bootstrap(self):
        skill = AIOpsSkill.objects.create(name='共享取证', slug='shared-evidence', applicable_actions=['cmdb'])
        response = self.client.patch('/api/aiops/admin/capabilities/event.analysis/', {'skills': [skill.slug]}, format='json')
        self.assertEqual(response.status_code, 200)
        bootstrap_payload_for_user(self.user)
        skill.refresh_from_db()
        self.assertEqual(set(skill.applicable_actions), {'cmdb', 'event.analysis'})
        handler = _action_registry_item_by_code('change.correlation', user=self.user)
        self.assertEqual(handler['skills'], [skill.slug])
        self.assertEqual(_skills_for_action(list(AIOpsSkill.objects.filter(merged_into__isnull=True)), handler), [skill])
        update_capability_skills('event.analysis', [], user=self.user)
        skill.refresh_from_db()
        handler = _action_registry_item_by_code('change.correlation', user=self.user)
        self.assertEqual(_skills_for_action([skill], {**handler, 'skills': [skill.slug]}), [])

    def test_capability_and_skill_mcp_bindings_are_derived_from_tool_dependencies(self):
        capability = next(item for item in list_capabilities(user=self.user) if item['code'] == 'troubleshoot')
        self.assertIn('可观测性 MCP', capability['mcp_server_names'])
        self.assertIn('知识图谱 MCP', capability['mcp_server_names'])
        alert_skill = next(item for item in capability['skill_details'] if item['slug'] == 'sx-alert-evidence')
        self.assertIn('可观测性 MCP', alert_skill['mcp_server_names'])
        marketplace = build_skill_marketplace_catalog(user=self.user)
        market_alert = next(item for item in marketplace['items'] if item['slug'] == 'sx-alert-evidence')
        self.assertIn('可观测性 MCP', market_alert['mcp_server_names'])

    def test_capability_mount_requires_config_permission_and_rejects_unknown_skill(self):
        response = self.client.patch('/api/aiops/admin/capabilities/event.analysis/', {'skills': ['missing-skill']}, format='json')
        self.assertEqual(response.status_code, 400)
        self.client.force_authenticate(self.restricted_user())
        self.assertEqual(self.client.get('/api/aiops/admin/capabilities/').status_code, 403)
        self.assertEqual(self.client.patch('/api/aiops/admin/capabilities/event.analysis/', {'skills': []}, format='json').status_code, 403)

    def test_troubleshooting_keeps_recovery_permission_and_filters_examples(self):
        user = self.restricted_user()
        diagnostic = _resolve_question_category_action('troubleshoot', '排查服务超时', user=user)
        recovery = _resolve_question_category_action('troubleshoot', '推荐恢复方案', user=user)
        self.assertTrue(diagnostic['available'])
        self.assertFalse(recovery['available'])
        capability = next(item for item in list_capabilities(user=user) if item['code'] == 'troubleshoot')
        self.assertFalse(any('恢复方案' in question for question in capability['suggested_questions']))
        with self.assertRaises(ValueError):
            create_external_task({'action_code': 'troubleshoot', 'input_payload': {'question': '推荐恢复方案'}}, user)

    def test_grouped_capabilities_resolve_legacy_handlers_and_external_tasks(self):
        for question, expected in [('分析告警', 'alert.root_cause'), ('排查 Pod 重启', 'k8s.diagnose'), ('推荐恢复方案', 'self_heal.recommend')]:
            self.assertEqual(_resolve_question_category_action('troubleshoot', question, self.user)['code'], expected)
        self.assertEqual(_resolve_question_category_action('event.analysis', '分析事件', self.user)['code'], 'change.correlation')
        for code in ['troubleshoot', 'event.analysis', 'log.query_generate', 'slo.analysis', 'host_task.generate', 'cmdb']:
            task = create_external_task({'action_code': code}, self.user)
            self.assertEqual(task.action_code, code)
            response = self.client.post('/api/aiops/admin/actions/preflight/', {'action_code': code}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            if code == 'cmdb':
                self.assertFalse(response.data.get('environment_required'))
            created = self.client.post('/api/aiops/a2a/tasks/', {'action_code': code}, format='json')
            self.assertEqual(created.status_code, 201, created.data)
            executed = self.client.post(f"/api/aiops/a2a/tasks/{created.data['public_id']}/run/", {}, format='json')
            self.assertEqual(executed.status_code, 200, executed.data)

    def test_event_capability_and_automatic_event_questions_enter_correlation_lane(self):
        self.assertTrue(_is_chat_change_correlation_question('梳理今天事件的影响时间线'))
        session = AIOpsChatSession.objects.create(user=self.user)
        message = AIOpsChatMessage.objects.create(session=session, role='user', content='分析当前情况', metadata={'question_category': 'event.analysis'})
        with mock.patch('aiops.langgraph_pilot._runtime', return_value=(session, message, self.user)):
            route = _chat_route_node({'message_id': message.id, 'question': message.content})
        self.assertEqual(route['route'], 'correlation')
        self.assertEqual(route['requested_action'], 'change.correlation')

    def test_cmdb_runtime_uses_mounted_skills_without_environment(self):
        session = AIOpsChatSession.objects.create(user=self.user)
        message = AIOpsChatMessage.objects.create(session=session, role='user', content='盘点 CMDB 资产', metadata={'question_category': 'cmdb'})
        with mock.patch('aiops.services._direct_tool_fastpath', return_value={'content': '完成', 'metadata': {}}) as runner:
            result = _dispatch_with_tool_runtime(session, message, self.user, message.content)
        self.assertEqual(result['metadata']['selected_capability']['code'], 'cmdb')
        self.assertTrue(runner.call_args.kwargs['active_skills'])
        self.assertTrue(all('cmdb' in skill.applicable_actions for skill in runner.call_args.kwargs['active_skills']))
        self.assertIsNone(runner.call_args.kwargs['knowledge_environment'])
        update_capability_skills('cmdb', [], user=self.user)
        with mock.patch('aiops.services._direct_tool_fastpath', return_value={'content': '完成', 'metadata': {}}) as runner:
            _dispatch_with_tool_runtime(session, message, self.user, message.content)
        self.assertEqual(runner.call_args.kwargs['active_skills'], [])

    def test_capability_trace_preserves_operation_decision_and_legacy_code(self):
        metadata = _upsert_action_decision_trace({
            'selected_action': {'code': 'self_heal.recommend', 'display_name': '自愈建议'},
            'capability_trace': {'code': 'troubleshoot', 'legacy_code': 'self_heal.recommend'},
        }, decision={'status': 'pending_confirmation'})
        self.assertEqual(metadata['capability_trace']['code'], 'troubleshoot')
        self.assertEqual(metadata['capability_trace']['legacy_code'], 'self_heal.recommend')
        self.assertEqual(metadata['capability_trace']['status'], 'pending_confirmation')

    def test_historical_audit_traces_use_capability_names_with_legacy_reference(self):
        session = AIOpsChatSession.objects.create(user=self.user)
        message = AIOpsChatMessage.objects.create(session=session, role='assistant', metadata={
            'action_trace': {'code': 'k8s.diagnose', 'display_name': 'K8s 诊断', 'status': 'pending_confirmation'},
        })
        trace = AIOpsAuditTraceReader()._action_trace_for_message(message)
        self.assertEqual(trace['code'], 'troubleshoot')
        self.assertEqual(trace['display_name'], '故障排查')
        self.assertEqual(trace['legacy_code'], 'k8s.diagnose')
        self.assertEqual(trace['status'], 'pending_confirmation')
