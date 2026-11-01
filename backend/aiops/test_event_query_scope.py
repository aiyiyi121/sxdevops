from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from eventwall.models import EventRecord

from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsKnowledgeEnvironment, AIOpsToolInvocation
from .services import query_events


class EventNaturalLanguageScopeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username='event-scope-admin')
        self.session = AIOpsChatSession.objects.create(user=self.user)
        self.message = AIOpsChatMessage.objects.create(session=self.session, role='user', content='查询事件')
        AIOpsKnowledgeEnvironment.objects.create(
            name='交易平台生产环境', aliases=['prod'], event_environments=['prod'],
        )
        self.release = self.event('订单服务发布', 'order-service')
        self.rollback = self.event('订单服务回滚', 'order-service')
        self.payment = self.event('支付服务发布', 'payment-service')
        self.event('测试环境订单发布', 'order-service', environment='dev')
        self.event('演示订单事件', 'order-service', is_demo=True)
        self.event('种子订单事件', 'order-service', source_type=EventRecord.SOURCE_SEED)

    def event(self, title, application, **kwargs):
        values = {
            'title': title, 'application': application, 'module': 'deploy',
            'category': 'release', 'action': 'finish', 'environment': 'prod',
            'source_type': EventRecord.SOURCE_SYSTEM,
        }
        values.update(kwargs)
        return EventRecord.objects.create(**values)

    def query(self, text, **kwargs):
        return query_events(self.session, self.message, self.user, query=text, **kwargs)

    def test_analysis_prose_keeps_service_and_drops_instruction_tokens(self):
        result = self.query(
            '请分析交易平台生产环境订单服务 order-service 最近48小时的发布、变更、告警和工单时间线，'
            '判断最近一次发布与异常有没有关联，指出证据和不确定性。'
        )
        self.assertEqual({event.id for event in result['events']}, {self.release.id, self.rollback.id})
        invocation = AIOpsToolInvocation.objects.filter(tool_name='query_events').latest('id')
        self.assertEqual(invocation.request_payload['tokens'], ['order-service'])

    def test_general_timeline_request_returns_scoped_events_without_prose_filter(self):
        result = self.query('梳理 prod 最近发布与告警的事件时间线，判断影响和不确定性')
        self.assertEqual({event.id for event in result['events']}, {
            self.release.id, self.rollback.id, self.payment.id,
        })

    def test_quoted_keyword_is_preserved_with_service_scope(self):
        result = self.query('查询 prod order-service 包含“回滚”的事件')
        self.assertEqual([event.id for event in result['events']], [self.rollback.id])

    def test_unknown_explicit_service_does_not_expand_to_all_environment_events(self):
        self.assertEqual(self.query('查看 prod missing-service 最近的发布事件')['events'], [])

    def test_explicit_last_hour_filter_is_still_applied(self):
        EventRecord.objects.filter(pk=self.release.pk).update(occurred_at=timezone.now() - timedelta(hours=2))
        result = self.query('分析 prod order-service 最近一小时事件', date_filter='last_hour')
        self.assertEqual([event.id for event in result['events']], [self.rollback.id])
