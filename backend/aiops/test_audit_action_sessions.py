from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from rbac.models import PermissionDefinition, Role
from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsPendingAction


class AIOpsAuditActionSessionTests(TestCase):
    url = '/api/aiops/admin/audit/actions/'

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='action-auditor', password='test')
        permission, _ = PermissionDefinition.objects.get_or_create(
            code='aiops.audit.view', defaults={'name': '审计查看', 'category': 'aiops'},
        )
        role = Role.objects.create(code='action-auditor', name='动作审计员')
        role.permissions.add(permission)
        role.users.add(self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.session = AIOpsChatSession.objects.create(user=self.user, title='订单扩容')
        self.question = AIOpsChatMessage.objects.create(session=self.session, role='user', content='生成扩容草稿')
        self.answer = AIOpsChatMessage.objects.create(
            session=self.session, role='assistant', content='请确认草稿',
            metadata={'orchestration_user_message_id': self.question.id},
        )
        self.action = AIOpsPendingAction.objects.create(
            session=self.session, message=self.answer,
            action_type=AIOpsPendingAction.ACTION_EXECUTE_HOST_TASK, title='扩容草稿',
        )
        self.other_session = AIOpsChatSession.objects.create(user=self.user, title='支付巡检')
        self.other_action = AIOpsPendingAction.objects.create(
            session=self.other_session,
            action_type=AIOpsPendingAction.ACTION_EXECUTE_HOST_TASK, title='巡检草稿',
        )

    def test_session_scope_returns_all_rounds_and_current_title(self):
        second = AIOpsPendingAction.objects.create(
            session=self.session, action_type=AIOpsPendingAction.ACTION_EXECUTE_HOST_TASK, title='第二轮草稿',
        )
        self.session.title = '订单服务扩容'
        self.session.save(update_fields=['title'])
        response = self.client.get(self.url, {'session_id': self.session.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item['id'] for item in response.data['results']}, {self.action.id, second.id})
        for item in response.data['results']:
            self.assertEqual(item['session'], self.session.id)
            self.assertEqual(item['session_title'], '订单服务扩容')
        row = next(item for item in response.data['results'] if item['id'] == self.action.id)
        self.assertEqual(row['message'], self.answer.id)

    def test_round_scope_includes_action_attached_to_assistant_reply(self):
        for message in (self.question, self.answer):
            with self.subTest(role=message.role):
                response = self.client.get(self.url, {'session_id': self.session.id, 'message_id': message.id})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([item['id'] for item in response.data['results']], [self.action.id])

    def test_session_and_message_scopes_cannot_leak_other_sessions(self):
        response = self.client.get(self.url, {'session_id': self.other_session.id, 'message_id': self.question.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)
        for parameter in ('session_id', 'message_id'):
            for value in ('invalid', '-1'):
                with self.subTest(parameter=parameter, value=value):
                    response = self.client.get(self.url, {parameter: value})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data['count'], 0)

    def test_unscoped_list_keeps_actions_without_messages(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)
        row = next(item for item in response.data['results'] if item['id'] == self.other_action.id)
        self.assertEqual(row['session_title'], '支付巡检')
        self.assertIsNone(row['message'])

    def test_session_scope_still_requires_audit_permission(self):
        self.client.force_authenticate(get_user_model().objects.create_user(username='no-action-audit'))
        self.assertEqual(self.client.get(self.url, {'session_id': self.session.id}).status_code, 403)
