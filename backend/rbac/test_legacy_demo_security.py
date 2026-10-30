from importlib import import_module
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import Client, TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from aiops.models import AIOpsChatMessage, AIOpsChatSession
from eventwall.models import EventRecord
from eventwall.services import record_event
from ops.docker_exec_consumer import DockerExecConsumer
from ops.k8s_exec_consumer import K8sExecConsumer
from ops.k8s_terminal_consumer import K8sClusterTerminalConsumer
from ops.ssh_consumer import SSHConsumer

from .models import PermissionDefinition, Role, UserGroup
from .services import ensure_builtin_rbac, get_user_effective_permissions, user_has_permissions


User = get_user_model()


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class LegacyDemoSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()

    def test_legacy_usernames_use_only_their_assigned_roles(self):
        role = Role.objects.get(code='read-only')
        for username in ('demo', 'demo_ai'):
            with self.subTest(username=username):
                user = User.objects.create_user(username=username)
                role.users.add(user)
                self.assertEqual(
                    get_user_effective_permissions(user),
                    set(role.permissions.values_list('code', flat=True)),
                )
                self.assertTrue(user_has_permissions(user, ['ops.dashboard.view']))
                self.assertFalse(user_has_permissions(user, ['ops.host.terminal']))
                self.assertFalse(user_has_permissions(user, ['rbac.user.manage']))
                client = APIClient()
                client.force_authenticate(user)
                self.assertEqual(client.get('/api/dashboard/stats/').status_code, 200)
                self.assertEqual(client.post('/api/users/', {}).status_code, 403)
                self.assertNotIn('is_demo_account', client.get('/api/auth/me/').data)

    def test_legacy_usernames_cannot_open_any_terminal_without_permission(self):
        consumers = (
            (SSHConsumer, 'host_id'),
            (DockerExecConsumer, 'host_id'),
            (K8sExecConsumer, 'cluster_id'),
            (K8sClusterTerminalConsumer, 'cluster_id'),
        )
        for username in ('demo', 'demo_ai'):
            user = User.objects.create_user(username=username)
            token = Token.objects.create(user=user)
            for consumer_class, resource_key in consumers:
                with self.subTest(username=username, consumer=consumer_class.__name__):
                    consumer = consumer_class()
                    consumer.scope = {
                        'url_route': {'kwargs': {resource_key: '1'}},
                        'query_string': f'token={token.key}&pod_name=test-pod'.encode(),
                    }
                    consumer.close = mock.Mock()
                    consumer.accept = mock.Mock()
                    consumer.connect()
                    consumer.close.assert_called_once_with(code=4403)
                    consumer.accept.assert_not_called()

    def test_inactive_users_have_no_effective_permission_even_if_superuser(self):
        user = User.objects.create_superuser(username='disabled-admin', is_active=False)
        self.assertEqual(get_user_effective_permissions(user), set())
        self.assertFalse(user_has_permissions(user, []))
        self.assertFalse(user_has_permissions(user, ['ops.host.terminal']))
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.get('/api/users/').status_code, 403)

    def test_admin_chats_are_not_copied_to_legacy_users(self):
        admin = User.objects.create_superuser(username='admin')
        role = Role.objects.get(code='read-only')
        readers = [User.objects.create_user(username=name) for name in ('demo', 'demo_ai')]
        role.users.add(*readers)
        client = APIClient()
        client.force_authenticate(admin)
        response = client.post('/api/aiops/sessions/', {'title': 'Private admin conversation'}, format='json')
        self.assertEqual(response.status_code, 201)
        source_id = response.data['id']
        AIOpsChatMessage.objects.create(
            session_id=source_id, role=AIOpsChatMessage.ROLE_USER, content='Private operational context',
        )
        for reader in readers:
            with self.subTest(username=reader.username):
                client.force_authenticate(reader)
                self.assertEqual(client.get('/api/aiops/bootstrap/').status_code, 200)
                self.assertEqual(client.get('/api/aiops/sessions/').status_code, 200)
                self.assertEqual(client.get(f'/api/aiops/sessions/{source_id}/').status_code, 404)
                self.assertFalse(AIOpsChatSession.objects.filter(user=reader).exists())

    def test_explicit_account_seed_does_not_recreate_legacy_accounts_or_log_passwords(self):
        output = StringIO()
        with mock.patch.dict('os.environ', {'SXDEVOPS_DEMO_PASSWORD': 'LocalSeed#123456'}):
            call_command('seed_rbac_demo', stdout=output)
        self.assertFalse(User.objects.filter(username__in=('demo', 'demo_ai')).exists())
        self.assertTrue(User.objects.get(username='viewer_demo').check_password('LocalSeed#123456'))
        self.assertNotIn('LocalSeed#123456', output.getvalue())

    def test_account_seed_preserves_existing_password_and_disabled_status(self):
        viewer = User.objects.create_user(username='viewer_demo', password='Existing#123456', is_active=False)
        with mock.patch.dict('os.environ', {'SXDEVOPS_DEMO_PASSWORD': 'NewSeed#123456'}):
            call_command('seed_rbac_demo', stdout=StringIO())
        viewer.refresh_from_db()
        self.assertFalse(viewer.is_active)
        self.assertTrue(viewer.check_password('Existing#123456'))
        self.assertFalse(viewer.is_staff)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class LegacyDemoAccountMigrationTests(TestCase):
    def test_cleanup_revokes_credentials_and_preserves_shared_data(self):
        from django.contrib.sessions.models import Session

        ensure_builtin_rbac()
        admin = User.objects.create_superuser(username='retained-admin')
        admin_token = Token.objects.create(user=admin)
        admin_client = Client()
        admin_client.force_login(admin)
        admin_session_key = admin_client.session.session_key
        group = UserGroup.objects.create(code='shared', name='Shared group')
        group.users.add(admin)
        role = Role.objects.get(code='platform-admin')
        group.roles.add(role)
        role.users.add(admin)
        source = AIOpsChatSession.objects.create(user=admin, title='Retained source')
        source_message = AIOpsChatMessage.objects.create(session=source, role='user', content='Retained message')
        removed_session_keys = []
        removed_tokens = []
        for username in ('demo', 'demo_ai'):
            user = User.objects.create_superuser(username=username)
            role.users.add(user)
            group.users.add(user)
            removed_tokens.append(Token.objects.create(user=user).key)
            client = Client()
            client.force_login(user)
            removed_session_keys.append(client.session.session_key)
            AIOpsChatSession.objects.create(user=user, mirror_source=source, title='Copied chat')

        record_event(module='rbac', category='security', action='legacy-operation', title='Retained audit', actor_username='demo')
        catalog_counts = (Role.objects.count(), UserGroup.objects.count(), PermissionDefinition.objects.count())
        migration = import_module('rbac.migrations.0013_remove_legacy_demo_accounts')
        migration_apps = MigrationLoader(connection).project_state([('rbac', '0013_remove_legacy_demo_accounts')]).apps
        for _ in range(2):
            migration.remove_legacy_demo_accounts(migration_apps, SimpleNamespace(connection=connection))

        self.assertFalse(User.objects.filter(username__in=('demo', 'demo_ai')).exists())
        self.assertFalse(Token.objects.filter(key__in=removed_tokens).exists())
        self.assertFalse(Session.objects.filter(session_key__in=removed_session_keys).exists())
        self.assertTrue(Session.objects.filter(session_key=admin_session_key).exists())
        self.assertTrue(Token.objects.filter(key=admin_token.key).exists())
        self.assertEqual(list(role.users.values_list('id', flat=True)), [admin.id])
        self.assertEqual(list(group.users.values_list('id', flat=True)), [admin.id])
        self.assertEqual(catalog_counts, (Role.objects.count(), UserGroup.objects.count(), PermissionDefinition.objects.count()))
        self.assertTrue(AIOpsChatSession.objects.filter(pk=source.pk).exists())
        self.assertTrue(AIOpsChatMessage.objects.filter(pk=source_message.pk).exists())
        self.assertFalse(AIOpsChatSession.objects.filter(mirror_source=source).exists())
        self.assertTrue(EventRecord.objects.filter(title='Retained audit', actor_username='demo').exists())
        for token in removed_tokens:
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
            self.assertEqual(client.get('/api/auth/me/').status_code, 401)
