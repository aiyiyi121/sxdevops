from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import Role
from .preview import PREVIEW_MESSAGE
from .services import ensure_builtin_rbac, get_user_effective_permissions, user_has_permissions


User = get_user_model()


@override_settings(PUBLIC_PREVIEW_USERNAMES=('product-visitor',))
class PublicPreviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()
        cls.user = User.objects.create_user(username='product-visitor', password='Preview-test-only-2468')
        cls.token = Token.objects.create(user=cls.user)
        cls.admin = User.objects.create_superuser(username='preview-test-admin', password='Admin-test-only-2468')

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    def test_profile_separates_preview_controls_from_backend_permissions(self):
        response = self.client.get('/api/auth/me/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['is_preview'])
        self.assertIn('ops.task.execute', response.data['preview_permissions'])
        self.assertNotIn('ops.task.execute', response.data['effective_permissions'])
        self.assertNotIn('ops.k8s.secret.view', response.data['effective_permissions'])
        self.assertNotIn('cmdb.password.reveal', response.data['effective_permissions'])

    def test_preview_can_browse_read_apis_and_legacy_task_reads(self):
        for path in (
            '/api/hosts/', '/api/users/', '/api/roles/', '/api/groups/', '/api/permissions/',
            '/api/module-settings/', '/api/auth/assignment-options/', '/api/users/options/',
            f'/api/users/{self.admin.pk}/k8s-access/', '/api/host-tasks/', '/api/host-tasks/stats/',
            '/api/host-task-templates/', '/api/aiops/admin/audit/sessions/',
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.data)

    def test_final_actions_are_denied_before_handlers_and_leave_data_unchanged(self):
        before = list(User.objects.values('id', 'username', 'password', 'is_active'))
        for method, path, payload in (
            ('post', '/api/hosts/', {}), ('post', '/api/host-tasks/', {}),
            ('post', '/api/users/', {'username': 'unexpected'}),
            ('patch', f'/api/users/{self.user.pk}/', {'is_active': False}),
            ('delete', f'/api/users/{self.admin.pk}/', None),
            ('post', f'/api/users/{self.admin.pk}/reset_password/', {'password': 'Changed-2468'}),
            ('put', '/api/module-settings/', []), ('post', '/api/auth/sync/', {}),
            ('post', '/api/aiops/sessions/', {}),
            ('post', '/api/k8s/clusters/999/kubectl/', {'command': 'get pods'}),
            ('post', '/api/sqlaudit/queries/', {'sql': 'SELECT 1'}),
            ('post', '/api/not-yet-registered-action/', {}),
        ):
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path, payload, format='json')
                # Unknown routes do not have a handler to authenticate or execute.
                expected = 404 if 'not-yet-registered' in path else 403
                self.assertEqual(response.status_code, expected, getattr(response, 'data', None))
                if expected == 403:
                    self.assertEqual(str(response.data['detail']), PREVIEW_MESSAGE)
        self.assertEqual(list(User.objects.values('id', 'username', 'password', 'is_active')), before)

    def test_read_query_post_still_reaches_query_handler(self):
        with patch('ops.observability_views.execute_promql_query', return_value={'status': 'success', 'data': {}}) as query:
            response = self.client.post('/api/observability/metrics/query/', {'query': 'up'}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            query.assert_called_once()

    def test_log_query_post_still_reaches_query_handler(self):
        with patch('ops.log_views._resolve_provider_and_config', return_value=('loki', {}, None)), patch(
            'ops.log_views._run_query', return_value={'logs': [], 'total': 0}
        ) as query:
            self.assertEqual(self.client.post('/api/log/query/', {'query': '{app="orders"}'}, format='json').status_code, 200)
            query.assert_called_once()

    def test_history_rebuild_get_cannot_bypass_preview_write_guard(self):
        with patch('ops.observability_views._capture_system_posture_sla_history') as capture:
            for key in ('refresh', 'backfill'):
                for value in ('1', 'true', 'yes'):
                    response = self.client.get('/api/observability/system-posture/history/', {key: value})
                    self.assertEqual(response.status_code, 403, response.data)
                    self.assertEqual(str(response.data['detail']), PREVIEW_MESSAGE)
            capture.assert_not_called()

    def test_extra_role_cannot_grant_preview_execution_or_secrets(self):
        Role.objects.get(code='platform-admin').users.add(self.user)
        for code in ('ops.task.execute', 'ops.host.terminal', 'ops.k8s.exec', 'ops.k8s.terminal',
                     'ops.docker.exec', 'ops.k8s.secret.view', 'cmdb.password.reveal', 'rbac.user.manage'):
            self.assertFalse(user_has_permissions(self.user, [code]), code)

    def test_superuser_flag_does_not_bypass_preview_ceiling(self):
        self.user.is_superuser = True
        self.assertFalse(user_has_permissions(self.user, ['ops.host.terminal']))
        self.assertNotIn('ops.host.manage', get_user_effective_permissions(self.user))

    def test_session_authentication_also_blocks_writes(self):
        self.client.credentials()
        self.client.force_login(self.user)
        self.assertEqual(self.client.post('/api/hosts/', {}, format='json').status_code, 403)

    def test_normal_admin_is_not_restricted(self):
        token = Token.objects.create(user=self.admin)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        response = self.client.patch(f'/api/users/{self.user.pk}/', {'first_name': 'Updated'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['is_superuser'])

    def test_logout_remains_available(self):
        response = self.client.post('/api/auth/logout/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Token.objects.filter(pk=self.token.pk).exists())

    @override_settings(PUBLIC_PREVIEW_USERNAMES=())
    def test_preview_is_opt_in_and_does_not_depend_on_a_reserved_username(self):
        self.assertFalse(self.client.get('/api/auth/me/').data['is_preview'])
        self.assertEqual(get_user_effective_permissions(self.user), set())
