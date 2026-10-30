from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from aiops.models import AIOpsChatSession
from eventwall.models import EventRecord
from ops.models import K8sCluster
from .models import K8sUserAccess, PermissionDefinition, Role, UserGroup
from .permissions import RBACPermissionMixin
from .services import ensure_builtin_rbac


User = get_user_model()


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class IdentityAdministrationSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser(username='root-security', password='RootSecure#735')
        self.target = User.objects.create_user(username='ordinary-target', password='InitialSecure#735')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def tearDown(self):
        cache.clear()

    def grant(self, user, *codes):
        role = Role.objects.create(code=f'role-{user.pk}', name=f'Role {user.pk}')
        role.permissions.set(PermissionDefinition.objects.filter(code__in=codes))
        role.users.add(user)
        return role

    def as_delegate(self, *codes):
        actor = User.objects.create_user(username='delegated-operator')
        self.grant(actor, *codes)
        self.client.force_authenticate(actor)
        return actor

    def test_user_manager_cannot_take_over_system_administrator(self):
        self.as_delegate('rbac.user.manage', 'rbac.user.view')
        for staff in (False, True):
            target = self.admin if not staff else User.objects.create_user(username='staff-account', is_staff=True)
            with self.subTest(username=target.username):
                self.assertEqual(self.client.patch(f'/api/users/{target.pk}/', {'email': 'changed@example.com'}).status_code, 403)
                self.assertEqual(self.client.post(f'/api/users/{target.pk}/reset_password/', {'password': 'ChangedSecure#735'}).status_code, 403)
                self.assertEqual(self.client.delete(f'/api/users/{target.pk}/').status_code, 403)
                self.assertEqual(self.client.put(f'/api/users/{target.pk}/k8s-access/', {'unrestricted': True, 'grants': []}, format='json').status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password('RootSecure#735'))

    def test_disabled_privileged_account_cannot_bypass_target_protection(self):
        elevated = Role.objects.get(code='platform-admin')
        elevated.users.add(self.target)
        self.target.is_active = False
        self.target.save()
        self.as_delegate('rbac.user.manage')
        self.assertEqual(self.client.patch(f'/api/users/{self.target.pk}/', {'is_active': True}).status_code, 403)

    def test_user_role_and_group_assignments_cannot_exceed_actor_permissions(self):
        high_role = Role.objects.get(code='platform-admin')
        group = UserGroup.objects.create(code='high-access', name='High access')
        group.roles.add(high_role)
        self.as_delegate('rbac.user.manage', 'rbac.role.manage', 'rbac.group.manage')
        for payload in ({'role_ids': [high_role.pk]}, {'group_ids': [group.pk]}):
            self.assertEqual(self.client.patch(f'/api/users/{self.target.pk}/', payload, format='json').status_code, 403)
        sensitive = PermissionDefinition.objects.get(code='ops.host.terminal')
        self.assertEqual(self.client.post('/api/roles/', {'code': 'elevated', 'name': 'Elevated', 'permission_ids': [sensitive.pk]}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/groups/', {'code': 'elevated', 'name': 'Elevated', 'role_ids': [high_role.pk]}, format='json').status_code, 403)
        self.assertFalse(self.target.rbac_roles.exists())

    def test_manager_cannot_downgrade_high_role_then_reset_its_user(self):
        high_role = self.grant(self.target, 'ops.host.terminal')
        self.as_delegate('rbac.role.manage', 'rbac.user.manage', 'rbac.group.manage')
        self.assertEqual(self.client.patch(f'/api/roles/{high_role.pk}/', {'permission_ids': []}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'/api/roles/{high_role.pk}/').status_code, 403)
        self.assertEqual(self.client.post(f'/api/users/{self.target.pk}/reset_password/', {'password': 'ChangedSecure#735'}).status_code, 403)

    def test_low_group_editor_cannot_change_privileged_membership(self):
        group = UserGroup.objects.create(code='shared-observers', name='Shared observers')
        group.users.add(self.admin)
        self.as_delegate('rbac.group.manage')
        self.assertEqual(self.client.patch(f'/api/groups/{group.pk}/', {'user_ids': []}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'/api/groups/{group.pk}/').status_code, 403)
        self.assertTrue(group.users.filter(pk=self.admin.pk).exists())

    def test_safe_delegated_user_and_role_creation_still_works(self):
        self.as_delegate('rbac.user.manage', 'rbac.role.manage', 'ops.dashboard.view')
        permission = PermissionDefinition.objects.get(code='ops.dashboard.view')
        role_response = self.client.post('/api/roles/', {'code': 'viewer-custom', 'name': 'Custom viewer', 'permission_ids': [permission.pk]}, format='json')
        self.assertEqual(role_response.status_code, 201, role_response.data)
        response = self.client.post('/api/users/', {'username': 'new-viewer', 'password': 'UniqueSecure#735', 'role_ids': [role_response.data['id']]}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['effective_permissions'], ['ops.dashboard.view'])

    def test_password_reset_and_patch_revoke_tokens_and_sessions(self):
        for endpoint in ('reset_password', 'patch'):
            with self.subTest(endpoint=endpoint):
                token = Token.objects.create(user=self.target)
                target_client = Client()
                target_client.force_login(self.target)
                key = target_client.session.session_key
                if endpoint == 'patch':
                    response = self.client.patch(f'/api/users/{self.target.pk}/', {'password': ' NewSecure#735 '})
                else:
                    response = self.client.post(f'/api/users/{self.target.pk}/reset_password/', {'password': ' NewSecure#735 '})
                self.assertEqual(response.status_code, 200, response.data)
                self.assertFalse(Token.objects.filter(key=token.key).exists())
                self.assertFalse(Session.objects.filter(session_key=key).exists())
                self.target.refresh_from_db()
                self.assertTrue(self.target.check_password(' NewSecure#735 '))
        self.assertNotIn('NewSecure#735', str(list(EventRecord.objects.values('metadata', 'summary'))))

    def test_disable_reenable_does_not_restore_old_credentials(self):
        old_token = Token.objects.create(user=self.target).key
        response = self.client.patch(f'/api/users/{self.target.pk}/', {'is_active': False})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.patch(f'/api/users/{self.target.pk}/', {'is_active': True}).status_code, 200)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {old_token}')
        self.assertEqual(client.get('/api/auth/me/').status_code, 401)

    def test_self_disable_and_delete_are_rejected(self):
        self.assertEqual(self.client.patch(f'/api/users/{self.admin.pk}/', {'is_active': False}).status_code, 400)
        self.assertEqual(self.client.delete(f'/api/users/{self.admin.pk}/').status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.admin.pk, is_active=True).exists())

    def test_last_active_superuser_is_retained(self):
        inactive_admin = User.objects.create_superuser(username='inactive-root', is_active=False)
        from .security import require_safe_account_removal
        with self.assertRaises(PermissionDenied):
            require_safe_account_removal(inactive_admin, self.admin)
        # The normal UI cannot create this actor; exercise the guard independently.
        with self.assertRaisesMessage(ValidationError, '至少一个'):
            from django.db import transaction
            with transaction.atomic():
                require_safe_account_removal(SimpleNamespace(pk=-1, is_active=True, is_superuser=True), self.admin)

    def test_password_policy_uses_target_identity_and_username_is_immutable(self):
        response = self.client.patch(f'/api/users/{self.target.pk}/', {'password': self.target.username})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.patch(f'/api/users/{self.target.pk}/', {'username': 'renamed-target'}).status_code, 400)

    def test_builtin_roles_are_immutable_and_reserved_codes_cannot_be_recreated(self):
        role = Role.objects.get(code='read-only')
        self.assertEqual(self.client.patch(f'/api/roles/{role.pk}/', {'permission_ids': []}, format='json').status_code, 400)
        role.delete()
        response = self.client.post('/api/roles/', {'code': 'read-only', 'name': 'Pretend builtin'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_permission_viewer_cannot_sync_or_query_assignment_candidates(self):
        self.as_delegate('rbac.permission.view')
        self.assertEqual(self.client.get('/api/permissions/').status_code, 200)
        self.assertEqual(self.client.post('/api/auth/sync/').status_code, 403)
        self.assertEqual(self.client.get('/api/auth/assignment-options/').status_code, 403)

    def test_assignment_options_do_not_require_unrelated_view_permissions(self):
        self.as_delegate('rbac.user.manage', 'rbac.group.manage', 'rbac.role.manage')
        response = self.client.get('/api/auth/assignment-options/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('platform-admin', [row['code'] for row in response.data['roles']])
        self.assertNotIn('ops.host.terminal', [row['code'] for row in response.data['permissions']])
        users = self.client.get('/api/users/options/', {'search': 'ordinary'})
        self.assertEqual(users.status_code, 200)
        self.assertEqual(users.data['results'], [{'id': self.target.pk, 'username': self.target.username}])
        self.assertEqual(self.client.get('/api/users/').status_code, 403)

    def test_member_picker_can_find_users_beyond_first_page(self):
        User.objects.bulk_create([User(username=f'member-{index:03}') for index in range(35)])
        response = self.client.get('/api/users/options/', {'page_size': 100})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 37)

    def test_role_and_group_changes_have_authorization_audit(self):
        role = self.grant(self.target, 'ops.dashboard.view')
        response = self.client.patch(f'/api/users/{self.target.pk}/', {'role_ids': []}, format='json')
        self.assertEqual(response.status_code, 200)
        event = EventRecord.objects.filter(resource_type='rbac_user', action='update').latest('id')
        self.assertEqual(event.metadata['authorization_before']['role_ids'], [role.pk])
        self.assertEqual(event.metadata['authorization_after']['role_ids'], [])

    def test_login_and_profile_do_not_rewrite_roles_or_provision_accounts(self):
        with mock.patch('rbac.views.ensure_builtin_rbac') as sync:
            self.assertEqual(self.client.get('/api/auth/me/').status_code, 200)
            client = APIClient()
            self.assertEqual(client.post('/api/auth/login/', {'username': self.admin.username, 'password': 'RootSecure#735'}).status_code, 200)
            sync.assert_not_called()

    def test_login_accepts_valid_password_with_stale_authorization_header(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token expired-token')
        response = client.post('/api/auth/login/', {'username': self.admin.username, 'password': 'RootSecure#735'})
        self.assertEqual(response.status_code, 200)
        self.admin.refresh_from_db()
        self.assertIsNotNone(self.admin.last_login)

    def test_malformed_login_and_password_reset_payloads_return_validation_errors(self):
        client = APIClient()
        self.assertEqual(client.post('/api/auth/login/', ['invalid'], format='json').status_code, 400)
        self.assertEqual(self.client.post(f'/api/users/{self.target.pk}/reset_password/',
                                          ['invalid'], format='json').status_code, 400)

    def test_login_account_rate_limit_applies_across_ips(self):
        client = APIClient()
        for index in range(10):
            self.assertEqual(client.post('/api/auth/login/', {'username': 'absent-user', 'password': 'wrong'}, REMOTE_ADDR=f'10.0.0.{index}').status_code, 400)
        self.assertEqual(client.post('/api/auth/login/', {'username': 'absent-user', 'password': 'wrong'}, REMOTE_ADDR='10.0.1.1').status_code, 429)

    def test_scoped_administrator_cannot_remove_own_cluster_restrictions(self):
        actor = self.as_delegate('rbac.user.manage')
        policy = K8sUserAccess.objects.create(user=actor, unrestricted=False)
        cluster = K8sCluster.objects.create(name='restricted-cluster', kubeconfig='demo')
        policy.grants.create(cluster=cluster, role='viewer', namespaces=['limited'])
        response = self.client.put(f'/api/users/{actor.pk}/k8s-access/', {'unrestricted': True, 'grants': []}, format='json')
        self.assertEqual(response.status_code, 403)
        policy.refresh_from_db()
        self.assertFalse(policy.unrestricted)

    def test_unmapped_action_is_denied_even_to_superuser(self):
        view = RBACPermissionMixin()
        view.action = 'forgotten_write'
        with self.assertRaises(PermissionDenied):
            view.get_required_permissions()

    def test_ai_audit_bulk_delete_requires_manage_permission(self):
        self.as_delegate('aiops.audit.view')
        session = AIOpsChatSession.objects.create(user=self.target, title='Keep audit')
        for endpoint, key in (('sessions', 'session_ids'), ('tool-invocations', 'invocation_ids'), ('actions', 'action_ids')):
            response = self.client.post(f'/api/aiops/admin/audit/{endpoint}/bulk-delete/', {key: [session.pk]}, format='json')
            self.assertEqual(response.status_code, 403, response.content)
        self.assertTrue(AIOpsChatSession.objects.filter(pk=session.pk).exists())

    def test_ai_audit_manager_can_bulk_delete_and_cmdb_rules_keep_resource_scope(self):
        self.as_delegate('aiops.audit.manage', 'cmdb.ci.view')
        session = AIOpsChatSession.objects.create(user=self.target, title='Delete test audit')
        response = self.client.post('/api/aiops/admin/audit/sessions/bulk-delete/',
                                    {'session_ids': [session.pk]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(AIOpsChatSession.objects.filter(pk=session.pk).exists())
        self.assertEqual(self.client.get('/api/cmdb/ci-relations/available-rules/').status_code, 404)
