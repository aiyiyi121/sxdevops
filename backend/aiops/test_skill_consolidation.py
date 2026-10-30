from copy import deepcopy

from django.test import TestCase

from .models import AIOpsAgentConfig, AIOpsSkill
from .serializers import AIOpsSkillSerializer
from .services import _get_selected_skills, _skills_for_action, get_agent_config
from .skill_catalog_v1 import (
    BUILTIN_SKILLS,
    LEGACY_BUILTIN_SKILLS,
    consolidate_builtin_skills,
    refine_consolidated_skills,
)


class ReusableSkillConsolidationTests(TestCase):
    def seed_legacy(self):
        skills = {}
        for definition in LEGACY_BUILTIN_SKILLS:
            skill = AIOpsSkill.objects.create(**deepcopy(definition), is_builtin=True, is_enabled=True)
            skills[skill.slug] = skill
        config = AIOpsAgentConfig.objects.create(name='default', enabled_skill_ids=[skill.pk for skill in skills.values()])
        return skills, config

    def test_default_catalog_runs_split_reusable_skills(self):
        config = get_agent_config()
        active = _get_selected_skills(config)
        self.assertEqual(len(active), 13)
        self.assertEqual({skill.slug for skill in active}, {definition['slug'] for definition in BUILTIN_SKILLS})
        selected = _skills_for_action(active, {'code': 'k8s.diagnose', 'skills': ['does-not-exist']})
        self.assertIn('sx-k8s-diagnostics', {skill.slug for skill in selected})
        self.assertIn('sx-log-analysis', {skill.slug for skill in selected})
        self.assertNotIn('sx-cmdb-asset-cost-analysis', {skill.slug for skill in selected})

    def test_merge_preserves_sources_custom_content_and_agent_selection(self):
        sources, config = self.seed_legacy()
        original = sources['sx-log-query-guide']
        original.content = '团队规范：日志查询必须额外过滤 tenant_id。'
        original.save(update_fields=['content'])
        custom = AIOpsSkill.objects.create(name='团队专有 Skill', slug='team-only', content='保留团队正文', applicable_actions=['alert.root_cause'])
        config.enabled_skill_ids.append(custom.pk)
        config.save(update_fields=['enabled_skill_ids'])

        consolidate_builtin_skills(AIOpsSkill, AIOpsAgentConfig)
        config.refresh_from_db()
        original.refresh_from_db()
        merged = AIOpsSkill.objects.get(slug='sx-log-analysis')
        self.assertEqual(original.content, '团队规范：日志查询必须额外过滤 tenant_id。')
        self.assertEqual(original.merged_into_id, merged.pk)
        self.assertIn('tenant_id', merged.content)
        self.assertIn('常用字段', merged.content)
        self.assertIn('聚合时优先', merged.content)
        self.assertIn(merged.pk, config.enabled_skill_ids)
        self.assertNotIn(original.pk, config.enabled_skill_ids)
        self.assertIn(custom.pk, config.enabled_skill_ids)
        custom.refresh_from_db()
        self.assertEqual(custom.content, '保留团队正文')
        self.assertEqual(custom.applicable_actions, ['troubleshoot'])
        self.assertEqual(AIOpsSkill.objects.filter(merged_into__isnull=True, is_builtin=True).count(), 13)

    def test_disjoint_role_limits_disable_merged_skill_without_broadening(self):
        sources, _ = self.seed_legacy()
        first = sources['sx-log-pattern-analysis']
        second = sources['sx-log-query-guide']
        first.allowed_role_codes = ['role-a']
        second.allowed_role_codes = ['role-b']
        first.save(update_fields=['allowed_role_codes'])
        second.save(update_fields=['allowed_role_codes'])

        consolidate_builtin_skills(AIOpsSkill, AIOpsAgentConfig)
        merged = AIOpsSkill.objects.get(slug='sx-log-analysis')
        self.assertFalse(merged.is_enabled)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.allowed_role_codes, ['role-a'])
        self.assertEqual(second.allowed_role_codes, ['role-b'])

    def test_disabled_source_and_strictest_risk_survive_merge(self):
        sources, _ = self.seed_legacy()
        first = sources['sx-container-readonly-guard']
        last = sources['sx-rollback-strategy']
        first.is_enabled = False
        first.risk_level = 'execute'
        last.risk_level = 'write'
        first.save(update_fields=['is_enabled', 'risk_level'])
        last.save(update_fields=['risk_level'])

        consolidate_builtin_skills(AIOpsSkill, AIOpsAgentConfig)
        merged = AIOpsSkill.objects.get(slug='sx-container-safety-guard')
        self.assertFalse(merged.is_enabled)
        self.assertEqual(merged.risk_level, 'execute')
        first.refresh_from_db()
        self.assertFalse(first.is_enabled)

    def test_merge_preserves_removed_tool_dependencies(self):
        sources, _ = self.seed_legacy()
        for slug in ('sx-log-pattern-analysis', 'sx-log-query-guide', 'sx-log-field-dictionary'):
            source = sources[slug]
            source.builtin_tools = [tool for tool in source.builtin_tools if tool != 'query_logs']
            source.recommended_tools = [tool for tool in source.recommended_tools if tool != 'query_knowledge_graph']
            source.save(update_fields=['builtin_tools', 'recommended_tools'])
        source = sources['sx-log-query-guide']
        source.builtin_tools.append('team_log_query')
        source.save(update_fields=['builtin_tools'])
        observation_source = sources['sx-alert-evidence-checklist']
        observation_source.recommended_tools.remove('query_system_posture')
        observation_source.save(update_fields=['recommended_tools'])

        consolidate_builtin_skills(AIOpsSkill, AIOpsAgentConfig)
        merged = AIOpsSkill.objects.get(slug='sx-log-analysis')
        self.assertNotIn('query_logs', merged.builtin_tools)
        self.assertNotIn('query_knowledge_graph', merged.recommended_tools)
        self.assertIn('team_log_query', merged.builtin_tools)
        self.assertIn('query_knowledge_graph', merged.builtin_tools)
        observation_merged = AIOpsSkill.objects.get(slug='sx-alert-evidence')
        self.assertNotIn('query_system_posture', observation_merged.builtin_tools)
        self.assertNotIn('query_system_posture', observation_merged.recommended_tools)
        self.assertIn('query_alerts', observation_merged.builtin_tools)

    def test_partial_agent_selection_does_not_enable_unselected_methods(self):
        sources, config = self.seed_legacy()
        config.enabled_skill_ids = [sources['sx-log-query-guide'].pk, sources['answer-formatter'].pk]
        config.save(update_fields=['enabled_skill_ids'])
        consolidate_builtin_skills(AIOpsSkill, AIOpsAgentConfig)
        config.refresh_from_db()
        self.assertEqual(config.enabled_skill_ids, [sources['answer-formatter'].pk])

    def test_legacy_selection_migrates_but_asset_switches_control_runtime(self):
        _, config = self.seed_legacy()
        config.enabled_skill_ids = []
        config.save(update_fields=['enabled_skill_ids'])
        consolidate_builtin_skills(AIOpsSkill, AIOpsAgentConfig)
        config.refresh_from_db()
        self.assertEqual(len(config.enabled_skill_ids), 10)
        config.enabled_skill_ids = []
        config.save(update_fields=['enabled_skill_ids'])
        get_agent_config()
        config.refresh_from_db()
        self.assertEqual(config.enabled_skill_ids, [])
        enabled = AIOpsSkill.objects.filter(is_enabled=True, merged_into__isnull=True)
        self.assertCountEqual(_get_selected_skills(config), enabled)
        enabled.update(is_enabled=False)
        self.assertEqual(_get_selected_skills(config), [])

    def test_bootstrap_keeps_user_edits_disabled_state_and_bindings(self):
        config = get_agent_config()
        skill = AIOpsSkill.objects.get(slug='sx-event-analysis')
        skill.content = '团队定制的事件分析方法'
        skill.applicable_actions = ['cmdb']
        skill.allowed_role_codes = ['role-a']
        skill.is_enabled = False
        skill.save(update_fields=['content', 'applicable_actions', 'allowed_role_codes', 'is_enabled'])
        get_agent_config()
        skill.refresh_from_db()
        self.assertEqual(skill.content, '团队定制的事件分析方法')
        self.assertEqual(skill.applicable_actions, ['cmdb'])
        self.assertEqual(skill.allowed_role_codes, ['role-a'])
        self.assertFalse(skill.is_enabled)
        self.assertNotIn(skill, _get_selected_skills(config))

    def test_skill_crud_cannot_change_bindings_or_merge_metadata(self):
        get_agent_config()
        skill = AIOpsSkill.objects.get(slug='sx-log-analysis')
        serializer = AIOpsSkillSerializer(skill, data={
            'content': '允许编辑专业方法', 'applicable_actions': ['cmdb'],
            'builtin_version': 999, 'merged_into': skill.pk, 'is_builtin': False,
        }, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        skill.refresh_from_db()
        self.assertEqual(skill.content, '允许编辑专业方法')
        self.assertEqual(skill.applicable_actions, ['troubleshoot', 'log.query_generate'])
        self.assertEqual(skill.builtin_version, 2)
        self.assertIsNone(skill.merged_into_id)
        self.assertTrue(skill.is_builtin)

    def test_refine_v1_aggregates_preserves_state_and_splits_bindings(self):
        observation = AIOpsSkill.objects.create(
            name='v1 可观测性证据与评估', slug='sx-observability-analysis',
            description='旧版聚合包', category='证据分析',
            applicable_actions=['troubleshoot', 'slo.analysis', 'event.analysis'],
            content='团队追加：必须标记数据缺口。', is_builtin=True,
            is_enabled=False, builtin_version=1, allowed_role_codes=['role-a'],
        )
        recovery = AIOpsSkill.objects.create(
            name='v1 安全任务与恢复方案', slug='sx-safe-task-recovery',
            description='旧版聚合包', category='任务与恢复',
            applicable_actions=['troubleshoot', 'host_task.generate', 'event.analysis'],
            content='团队追加：生产变更必须审批。', is_builtin=True,
            is_enabled=True, builtin_version=1, allowed_role_codes=['role-b'],
        )
        archived_task = AIOpsSkill.objects.create(
            name='旧版任务模板选择', slug='sx-task-template-selection',
            description='旧版任务模板', category='任务中心',
            applicable_actions=['host_task.generate'], content='旧版任务内容',
            is_builtin=True, is_enabled=True, builtin_version=2,
            merged_into=recovery,
        )
        archived_rollback = AIOpsSkill.objects.create(
            name='旧版回滚策略', slug='sx-rollback-strategy',
            description='旧版回滚', category='发布回滚',
            applicable_actions=['event.analysis'], content='旧版回滚内容',
            is_builtin=True, is_enabled=True, builtin_version=2,
            merged_into=recovery,
        )
        config = AIOpsAgentConfig.objects.create(
            name='default', enabled_skill_ids=[observation.pk, recovery.pk, archived_task.pk, archived_rollback.pk],
        )

        refine_consolidated_skills(AIOpsSkill, AIOpsAgentConfig)

        observation.refresh_from_db()
        recovery.refresh_from_db()
        self.assertIsNotNone(observation.merged_into_id)
        self.assertIsNotNone(recovery.merged_into_id)
        observation_targets = list(AIOpsSkill.objects.filter(slug__in=[
            'sx-alert-evidence', 'sx-metric-slo-analysis', 'sx-trace-evidence', 'sx-system-posture',
        ]))
        recovery_targets = list(AIOpsSkill.objects.filter(slug__in=[
            'sx-container-safety-guard', 'sx-self-heal-safety',
            'sx-task-template-selection', 'sx-rollback-strategy',
        ]))
        self.assertEqual(len(observation_targets), 4)
        self.assertEqual(len(recovery_targets), 4)
        self.assertIsNone(AIOpsSkill.objects.get(slug='sx-task-template-selection').merged_into_id)
        self.assertIsNone(AIOpsSkill.objects.get(slug='sx-rollback-strategy').merged_into_id)
        self.assertEqual(AIOpsSkill.objects.get(slug='sx-task-template-selection').allowed_role_codes, ['role-b'])
        self.assertTrue(AIOpsSkill.objects.get(slug='sx-task-template-selection').is_enabled)
        self.assertTrue(all(not target.is_enabled for target in observation_targets))
        self.assertTrue(all(target.allowed_role_codes == ['role-a'] for target in observation_targets))
        self.assertEqual(
            AIOpsSkill.objects.get(slug='sx-task-template-selection').applicable_actions,
            ['host_task.generate'],
        )
        self.assertIn('数据缺口', AIOpsSkill.objects.get(slug='sx-alert-evidence').content)
        config.refresh_from_db()
        self.assertNotIn(observation.pk, config.enabled_skill_ids)
        self.assertTrue(all(target.pk in config.enabled_skill_ids for target in observation_targets + recovery_targets))
