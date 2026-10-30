from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import PermissionDefinition, Role, SystemModuleSetting
from .services import ensure_builtin_rbac, get_system_module_settings


class SystemModuleOrderTests(TestCase):
    def setUp(self):
        ensure_builtin_rbac()
        get_system_module_settings()
        self.admin = get_user_model().objects.create_superuser(username='menu-order-admin', password='test-password')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def update_modules(self, modules):
        return self.client.put('/api/module-settings/', {'modules': modules}, format='json')

    def test_default_order_places_containers_after_aiops_and_security_before_system(self):
        roots = [item['code'] for item in get_system_module_settings() if not item['parent_code']]
        self.assertEqual(roots[roots.index('aiops') + 1], 'containers')
        self.assertEqual(roots[roots.index('system') - 1], 'cloudsecurity')

    def test_custom_parent_and_child_order_survives_reload_and_login(self):
        response = self.update_modules([
            {'code': 'containers', 'sort_order': 0},
            {'code': 'containers.docker', 'sort_order': 0},
        ])
        self.assertEqual(response.status_code, 200)
        settings = self.client.get('/api/module-settings/').json()
        self.assertEqual([item['code'] for item in settings[:3]], ['containers', 'containers.docker', 'containers.k8s'])
        login = self.client.post('/api/auth/login/', {'username': self.admin.username, 'password': 'test-password'}, format='json')
        self.assertEqual(login.status_code, 200)
        self.assertEqual([item['code'] for item in login.json()['module_settings'][:3]], ['containers', 'containers.docker', 'containers.k8s'])

    def test_sort_only_update_preserves_visibility_and_default_page(self):
        get_system_module_settings()
        SystemModuleSetting.objects.filter(is_default=True).update(is_default=False)
        SystemModuleSetting.objects.filter(code='containers.docker').update(enabled=False)
        SystemModuleSetting.objects.filter(code='aiops.chat').update(is_default=True)
        response = self.update_modules([{'code': 'containers.docker', 'sort_order': 0}])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SystemModuleSetting.objects.get(code='containers.docker').enabled)
        self.assertTrue(SystemModuleSetting.objects.get(code='aiops.chat').is_default)

    def test_null_order_restores_default_and_required_menus_remain_visible(self):
        self.update_modules([{'code': 'containers', 'sort_order': 0}])
        response = self.update_modules([
            {'code': 'containers', 'sort_order': None},
            {'code': 'system', 'sort_order': 0, 'enabled': False},
        ])
        self.assertEqual(response.status_code, 200)
        settings = {item['code']: item for item in response.json()['data']}
        self.assertEqual(settings['containers']['sort_order'], settings['containers']['default_sort_order'])
        self.assertTrue(settings['system']['enabled'])
        self.assertEqual(response.json()['data'][0]['code'], 'system')

    def test_invalid_sort_rejects_entire_update(self):
        for value in [-1, 'invalid', 32768]:
            with self.subTest(value=value):
                response = self.update_modules([
                    {'code': 'containers', 'sort_order': 0, 'enabled': False},
                    {'code': 'aiops', 'sort_order': value},
                ])
                self.assertEqual(response.status_code, 400)
                containers = SystemModuleSetting.objects.get(code='containers')
                self.assertIsNone(containers.sort_order)
                self.assertTrue(containers.enabled)

    def test_sort_updates_require_module_management_permission(self):
        reader = get_user_model().objects.create_user(username='menu-order-reader')
        self.client.force_authenticate(reader)
        self.assertEqual(self.client.get('/api/module-settings/').status_code, 200)
        self.assertEqual(self.update_modules([{'code': 'containers', 'sort_order': 0}]).status_code, 403)
        role = Role.objects.create(code='menu-order-editor', name='菜单排序管理员')
        role.permissions.add(PermissionDefinition.objects.get(code='rbac.module.manage'))
        reader.rbac_roles.add(role)
        self.assertEqual(self.update_modules([{'code': 'containers', 'sort_order': 0}]).status_code, 200)
