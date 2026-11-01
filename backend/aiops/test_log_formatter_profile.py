from unittest import mock

from django.test import SimpleTestCase

from . import services
from .models import AIOpsChatMessage, AIOpsModelProvider, AIOpsSkill


class LogFormatterProfileTests(SimpleTestCase):
    def setUp(self):
        self.question = '订单服务最近一小时 ERROR/WARN 日志有什么共同模式'
        self.outputs = [{'tool_name': 'query_logs', 'tool_output': {
            'summary': {'count': 2, 'service': 'order-service', 'duration_minutes': 60, 'levels': ['error', 'warning']},
            'logs': [
                {'level': 'error', 'message': 'inventory request timeout', 'attributes': {'trace_id': 'trace-order-1'}},
                {'level': 'warning', 'message': 'inventory request timeout', 'attributes': {'trace_id': 'trace-order-2'}},
            ],
        }}]
        self.skill = AIOpsSkill(
            slug=services.ANSWER_FORMATTER_SKILL_SLUG, name='回答整形', content='严格依据工具事实回答。',
        )
        self.citations = [{'title': '日志中心', 'path': '/logs/query'}]

    def test_log_samples_select_incident_without_diagnosis_keywords(self):
        for question in [self.question, '查看生产环境 gateway 最近半小时警告日志']:
            with self.subTest(question=question):
                self.assertFalse(any(keyword in question for keyword in ['异常', '分析', '排查', '根因']))
                self.assertEqual(services._detect_formatter_profile(
                    question, None, AIOpsChatMessage.TYPE_ANALYSIS, self.outputs,
                ), 'incident')

    def test_log_prompt_requires_evidence_headings_instead_of_general_key_points(self):
        messages = services._build_answer_formatter_messages(
            question=self.question, draft_content='', sections=[], citations=self.citations,
            tool_calls=['query_logs'], pending_action_draft=None, message_type=AIOpsChatMessage.TYPE_ANALYSIS,
            formatter_skill=self.skill, active_skills=[self.skill], collected_tool_outputs=self.outputs,
        )

        self.assertIn('本轮必须包含这些一级标题：结论：/ 依据：/ 建议操作：/ 可继续查看：', messages[0]['content'])
        self.assertNotIn('关键点：', messages[0]['content'])
        self.assertIn('"formatter_profile": "incident"', messages[1]['content'])

    @mock.patch('aiops.services._request_model_completion')
    def test_valid_model_log_analysis_finishes_without_fallback(self, completion):
        answer = '\n'.join([
            '结论：订单服务最近一小时命中 2 条日志，共同模式是库存请求超时，可能影响下单。',
            '依据：',
            '- 两条日志都包含 inventory request timeout，分别为 ERROR 和 WARNING。',
            '- 样本提供 trace-order-1 与 trace-order-2，可进一步关联请求路径。',
            '建议操作：',
            '- 使用 trace_id 复核库存服务的调用耗时，再核对同时间窗发布记录。',
            '可继续查看：日志中心',
        ])
        completion.return_value = {'choices': [{'message': {'content': answer}}]}

        result = services._run_answer_formatter(
            AIOpsModelProvider(name='deepseek-test', default_model='deepseek-chat'),
            question=self.question, draft_content='', sections=[], citations=self.citations,
            tool_calls=['query_logs'], pending_action_draft=None, message_type=AIOpsChatMessage.TYPE_ANALYSIS,
            active_skills=[self.skill], collected_tool_outputs=self.outputs,
        )

        self.assertTrue(result['used'])
        self.assertFalse(result['fell_back'])
        self.assertEqual(result['reason'], 'formatted')
        self.assertEqual(result['attempts'], 1)
        self.assertEqual(result['content'], services._normalize_formatter_output(answer))
        completion.assert_called_once()

    def test_empty_log_query_does_not_force_incident_profile(self):
        outputs = [{'tool_name': 'query_logs', 'tool_output': {'summary': {'count': 0}, 'logs': []}}]

        self.assertEqual(services._detect_formatter_profile(
            self.question, None, AIOpsChatMessage.TYPE_ANALYSIS, outputs,
        ), 'general')

    def test_task_and_slo_profiles_keep_priority_over_log_samples(self):
        self.assertEqual(services._detect_formatter_profile(
            self.question, {'name': '日志巡检任务'}, AIOpsChatMessage.TYPE_ANALYSIS, self.outputs,
        ), 'task')
        self.assertEqual(services._detect_formatter_profile(
            self.question, None, AIOpsChatMessage.TYPE_ACTION, self.outputs,
        ), 'task')
        self.assertEqual(services._detect_formatter_profile(
            '查看订单服务最近一小时 SLO 情况', None, AIOpsChatMessage.TYPE_ANALYSIS, self.outputs,
        ), 'slo')
