from django.contrib.auth import get_user_model
from django.apps import apps
from django.db import connection
from django.test import TestCase
from importlib import import_module
from types import SimpleNamespace

from .models import PermissionDefinition, Role, SystemModuleSetting, UserGroup
from .serializers import UserSerializer
from .services import (
    ensure_builtin_rbac,
    ensure_system_module_settings,
    get_user_effective_permissions,
    user_has_permissions,
)


User = get_user_model()


class CmdbPlatformConfigMigrationTests(TestCase):
    def merge_settings(self):
        migration = import_module('rbac.migrations.0006_merge_cmdb_platform_config')
        migration.merge_cmdb_platform_config(apps, SimpleNamespace(connection=connection))

    def test_merge_preserves_hidden_menu_when_all_legacy_entries_are_hidden(self):
        SystemModuleSetting.objects.filter(code='cmdb.platform-config').delete()
        for code in ['cmdb.sync', 'cmdb.model-config', 'cmdb.ipam']:
            SystemModuleSetting.objects.update_or_create(code=code, defaults={'enabled': False})

        self.merge_settings()

        self.assertFalse(SystemModuleSetting.objects.get(code='cmdb.platform-config').enabled)

    def test_merge_preserves_login_default_and_existing_visibility(self):
        SystemModuleSetting.objects.filter(is_default=True).update(is_default=False)
        SystemModuleSetting.objects.update_or_create(code='cmdb.ipam', defaults={'enabled': True, 'is_default': True})
        SystemModuleSetting.objects.update_or_create(code='cmdb.platform-config', defaults={'enabled': False})

        self.merge_settings()
        self.merge_settings()

        combined = SystemModuleSetting.objects.get(code='cmdb.platform-config')
        self.assertTrue(combined.is_default)
        self.assertFalse(combined.enabled)
        self.assertEqual(SystemModuleSetting.objects.filter(is_default=True).count(), 1)

    def test_merge_enables_entry_when_any_legacy_menu_was_visible(self):
        SystemModuleSetting.objects.filter(code='cmdb.platform-config').delete()
        SystemModuleSetting.objects.update_or_create(code='cmdb.sync', defaults={'enabled': True})
        SystemModuleSetting.objects.update_or_create(code='cmdb.model-config', defaults={'enabled': False})
        SystemModuleSetting.objects.update_or_create(code='cmdb.ipam', defaults={'enabled': False})

        self.merge_settings()

        self.assertTrue(SystemModuleSetting.objects.get(code='cmdb.platform-config').enabled)


class RbacPermissionTests(TestCase):
    def setUp(self):
        ensure_builtin_rbac()
        self.dashboard_permission = PermissionDefinition.objects.get(code='ops.dashboard.view')
        self.user_view_permission = PermissionDefinition.objects.get(code='rbac.user.view')

    def test_group_role_grants_effective_permission(self):
        role = Role.objects.create(code='dashboard-viewer', name='Dashboard Viewer')
        role.permissions.add(self.dashboard_permission)
        group = UserGroup.objects.create(code='observers', name='Observers')
        group.roles.add(role)

        user = User.objects.create_user(username='observer', password='Admin@123456')
        group.users.add(user)
        self.client.force_login(user)

        response = self.client.get('/api/dashboard/stats/')
        self.assertEqual(response.status_code, 200)

        denied = self.client.get('/api/hosts/')
        self.assertEqual(denied.status_code, 403)

    def test_view_only_user_cannot_create_users(self):
        role = Role.objects.create(code='user-auditor', name='User Auditor')
        role.permissions.add(self.user_view_permission)

        user = User.objects.create_user(username='auditor', password='Admin@123456')
        role.users.add(user)
        self.client.force_login(user)

        list_response = self.client.get('/api/users/')
        self.assertEqual(list_response.status_code, 200)

        create_response = self.client.post(
            '/api/users/',
            {
                'username': 'blocked-user',
                'password': 'Admin@123456',
                'email': 'blocked@example.com',
            },
        )
        self.assertEqual(create_response.status_code, 403)

    def test_legacy_demo_usernames_have_no_implicit_permissions(self):
        for username in ('demo', 'demo_ai'):
            with self.subTest(username=username):
                user = User.objects.create_user(username=username)
                self.assertEqual(get_user_effective_permissions(user), set())
                self.assertFalse(user_has_permissions(user, ['rbac.user.manage']))
                self.assertFalse(user_has_permissions(user, ['ops.host.terminal']))
                self.assertFalse(user_has_permissions(user, ['ops.k8s.exec']))

    def test_demo_account_cannot_create_users(self):
        demo_user = User.objects.create_user(username='demo', password='Demo#123')
        self.client.force_login(demo_user)

        response = self.client.post(
            '/api/users/',
            {
                'username': 'blocked-demo-created-user',
                'password': 'Admin@123456',
                'email': 'blocked-demo-created-user@example.com',
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('rbac.user.manage', response.json()['detail'])

    def test_demo_ai_account_cannot_create_users(self):
        demo_user = User.objects.create_user(username='demo_ai', password='Demo#123')
        self.client.force_login(demo_user)

        response = self.client.post(
            '/api/users/',
            {
                'username': 'blocked-demo-ai-created-user',
                'password': 'Admin@123456',
                'email': 'blocked-demo-ai-created-user@example.com',
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('rbac.user.manage', response.json()['detail'])

    def test_demo_account_cannot_call_custom_write_action(self):
        demo_user = User.objects.create_user(username='demo', password='Demo#123')
        target_user = User.objects.create_user(username='reset-target', password='Admin@123456')
        self.client.force_login(demo_user)

        response = self.client.post(
            f'/api/users/{target_user.id}/reset_password/',
            {'password': 'Admin@654321'},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('rbac.user.manage', response.json()['detail'])

    def test_module_settings_include_secondary_menu_items(self):
        ensure_system_module_settings()
        admin = User.objects.create_superuser(username='module-admin', password='Admin@123456')
        self.client.force_login(admin)

        response = self.client.get('/api/module-settings/')

        self.assertEqual(response.status_code, 200)
        settings = {item['code']: item for item in response.json()}
        self.assertEqual(settings['observability.metrics']['parent_code'], 'observability')
        self.assertEqual(settings['observability.metrics']['level'], 2)
        self.assertFalse(settings['observability.metrics']['required'])
        self.assertTrue(settings['system.modules']['required'])
        self.assertEqual(settings['observability.metrics']['path'], '/observability/metrics')
        self.assertTrue(settings['dashboard']['is_default'])
        self.assertEqual(settings['aiops.widget']['parent_code'], 'aiops')
        self.assertEqual(settings['aiops.widget']['config_type'], 'floating_entry')
        self.assertEqual(settings['aiops.widget']['path'], '')
        self.assertEqual(settings['cloudsecurity']['title'], '安全中心')
        self.assertEqual(settings['cloudsecurity']['level'], 1)
        self.assertEqual(settings['cloudsecurity.waf']['path'], '/cloud-security/waf')
        self.assertEqual(settings['cloudsecurity.waf']['parent_code'], 'cloudsecurity')
        self.assertEqual(settings['cloudsecurity.internal-platform']['path'], '/security-center/internal-platform')
        self.assertEqual(settings['cloudsecurity.internal-platform']['level'], 2)
        self.assertEqual(settings['cmdb.platform-config']['title'], '平台配置')
        self.assertEqual(settings['cmdb.platform-config']['path'], '/cmdb/platform-config')
        self.assertEqual(settings['cmdb.platform-config']['parent_code'], 'cmdb')
        self.assertEqual(settings['cmdb.platform-config']['level'], 2)
        for legacy_code in ['cmdb.sync', 'cmdb.model-config', 'cmdb.ipam']:
            self.assertNotIn(legacy_code, settings)

    def test_module_settings_can_hide_secondary_menu_but_not_system_menu(self):
        ensure_system_module_settings()
        admin = User.objects.create_superuser(username='module-editor', password='Admin@123456')
        self.client.force_login(admin)

        response = self.client.put(
            '/api/module-settings/',
            {
                'modules': [
                    {'code': 'observability.metrics', 'enabled': False},
                    {'code': 'aiops.widget', 'enabled': False},
                    {'code': 'cmdb.platform-config', 'enabled': False},
                    {'code': 'system.modules', 'enabled': False},
                ],
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SystemModuleSetting.objects.get(code='observability.metrics').enabled)
        self.assertFalse(SystemModuleSetting.objects.get(code='aiops.widget').enabled)
        self.assertFalse(SystemModuleSetting.objects.get(code='cmdb.platform-config').enabled)
        self.assertTrue(SystemModuleSetting.objects.get(code='system.modules').enabled)

    def test_module_settings_can_set_login_default_page(self):
        ensure_system_module_settings()
        admin = User.objects.create_superuser(username='default-page-editor', password='Admin@123456')
        self.client.force_login(admin)

        response = self.client.put(
            '/api/module-settings/',
            {
                'modules': [],
                'default_code': 'tasks.workbench',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(SystemModuleSetting.objects.get(code='tasks.workbench').is_default)
        settings = {item['code']: item for item in response.json()['data']}
        self.assertTrue(settings['tasks.workbench']['is_default'])
        self.assertFalse(settings['dashboard']['is_default'])

        login_response = self.client.post(
            '/api/auth/login/',
            {'username': 'default-page-editor', 'password': 'Admin@123456'},
            content_type='application/json',
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json()['default_page'], '/tasks/workbench')
        login_settings = {item['code']: item for item in login_response.json()['module_settings']}
        self.assertTrue(login_settings['tasks.workbench']['is_default'])

    def test_hidden_default_page_falls_back_to_system_posture(self):
        ensure_system_module_settings()
        admin = User.objects.create_superuser(username='default-page-fallback', password='Admin@123456')
        self.client.force_login(admin)

        response = self.client.put(
            '/api/module-settings/',
            {
                'modules': [{'code': 'tasks.workbench', 'enabled': False}],
                'default_code': 'tasks.workbench',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SystemModuleSetting.objects.filter(is_default=True).exists())
        settings = {item['code']: item for item in response.json()['data']}
        self.assertTrue(settings['dashboard']['is_default'])

    def test_user_serializer_cannot_assign_privileged_flags(self):
        user = User.objects.create_user(username='ordinary-user', password='Passw0rd!123')
        admin = User.objects.create_superuser(username='identity-admin')
        serializer = UserSerializer(user, data={'is_superuser': True, 'is_staff': True}, partial=True,
                                    context={'request': SimpleNamespace(user=admin)})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        user.refresh_from_db()
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        self.assertTrue(user.is_active)
