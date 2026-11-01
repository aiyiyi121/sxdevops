from django.test import SimpleTestCase

from .services import DEFAULT_SUGGESTED_QUESTIONS, _normalize_suggested_questions


class SuggestedQuestionConfigurationTests(SimpleTestCase):
    def test_custom_suggestions_keep_order_without_appending_demo_defaults(self):
        custom = [f'交易平台生产环境演示场景 {index} 查询' for index in range(1, 9)]
        self.assertEqual(_normalize_suggested_questions(custom), custom)

    def test_empty_suggestions_still_use_builtin_defaults(self):
        self.assertEqual(_normalize_suggested_questions([]), DEFAULT_SUGGESTED_QUESTIONS)

    def test_old_unscoped_default_alert_suggestion_is_still_repaired(self):
        self.assertEqual(
            _normalize_suggested_questions(['当前未确认的严重告警有哪些？']),
            [DEFAULT_SUGGESTED_QUESTIONS[0]],
        )
