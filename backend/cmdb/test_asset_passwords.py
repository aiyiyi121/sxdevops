from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from eventwall.models import EventRecord
from rbac.models import PermissionDefinition, Role

from .models import CIType, ConfigItem, ConfigItemPassword


@override_settings(CMDB_PASSWORD_ENCRYPTION_KEY=Fernet.generate_key().decode('utf-8'))
class ConfigItemPasswordApiTests(APITestCase):
    def setUp(self):
        self.ci_type = CIType.objects.create(name='密码测试主机', code='PASSWORD_TEST_HOST')
        self.config_item = ConfigItem.objects.create(name='prod-app-01', ci_type=self.ci_type)
        self.manager = get_user_model().objects.create_user('password-manager', password='Admin@123456')
        self.revealer = get_user_model().objects.create_user('password-revealer', password='Admin@123456')
        self.viewer = get_user_model().objects.create_user('password-viewer', password='Admin@123456')

        manage_permission, _ = PermissionDefinition.objects.update_or_create(
            code='cmdb.password.manage',
            defaults={'name': '管理 CMDB 资产密码', 'category': 'cmdb'},
        )
        reveal_permission, _ = PermissionDefinition.objects.update_or_create(
            code='cmdb.password.reveal',
            defaults={'name': '查看 CMDB 资产密码', 'category': 'cmdb'},
        )
        manager_role = Role.objects.create(code='password-manager-role', name='密码管理员')
        manager_role.permissions.add(manage_permission)
        manager_role.users.add(self.manager)
        revealer_role = Role.objects.create(code='password-revealer-role', name='密码查看员')
        revealer_role.permissions.add(reveal_permission)
        revealer_role.users.add(self.revealer)
        self.client = APIClient()

    def create_password(self, password='SxDevOps#Password123'):
        self.client.force_authenticate(self.manager)
        return self.client.post(
            '/api/cmdb/config-item-passwords/',
            {
                'config_item': self.config_item.id,
                'username': 'root',
                'password': password,
                'remark': '生产主机登录账号',
            },
            format='json',
        )

    def test_manage_permission_saves_only_ciphertext(self):
        plaintext = 'SxDevOps#Password123'
        response = self.create_password(plaintext)

        self.assertEqual(response.status_code, 201)
        stored = ConfigItemPassword.objects.get(config_item=self.config_item)
        self.assertNotEqual(stored.password_ciphertext, plaintext)
        self.assertNotIn(plaintext, stored.password_ciphertext)
        self.assertNotIn('password', response.data)
        self.assertNotIn('password_ciphertext', response.data)
        self.assertTrue(response.data['has_password'])
        self.assertEqual(stored.created_by, self.manager.username)
        self.assertEqual(stored.updated_by, self.manager.username)

    def test_reveal_permission_returns_plaintext_without_cache(self):
        plaintext = 'SxDevOps#Password123'
        create_response = self.create_password(plaintext)
        self.client.force_authenticate(self.revealer)

        response = self.client.post(
            f'/api/cmdb/config-item-passwords/{create_response.data["id"]}/reveal/',
            {'current_password': 'Admin@123456'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'username': 'root', 'password': plaintext})
        self.assertIn('no-store', response['Cache-Control'])
        event = EventRecord.objects.filter(action='reveal_password').latest('occurred_at')
        self.assertEqual(event.actor_username, self.revealer.username)
        self.assertEqual(event.resource_id, str(create_response.data['id']))
        self.assertNotIn(plaintext, str(event.metadata))
        self.assertNotIn(plaintext, event.summary)

    def test_reveal_requires_current_login_password(self):
        create_response = self.create_password()
        self.client.force_authenticate(self.revealer)

        response = self.client.post(
            f'/api/cmdb/config-item-passwords/{create_response.data["id"]}/reveal/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('current_password', response.data)
        self.assertFalse(EventRecord.objects.filter(action='reveal_password').exists())

    def test_reveal_rejects_incorrect_current_login_password(self):
        plaintext = 'SxDevOps#Password123'
        create_response = self.create_password(plaintext)
        self.client.force_authenticate(self.revealer)

        response = self.client.post(
            f'/api/cmdb/config-item-passwords/{create_response.data["id"]}/reveal/',
            {'current_password': 'WrongPassword'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('当前登录密码不正确', str(response.data))
        self.assertNotIn(plaintext, str(response.data))
        self.assertFalse(EventRecord.objects.filter(action='reveal_password').exists())

    def test_manage_permission_can_update_metadata_without_replacing_password(self):
        create_response = self.create_password()
        item = ConfigItemPassword.objects.get(pk=create_response.data['id'])
        original_ciphertext = item.password_ciphertext

        response = self.client.patch(
            f'/api/cmdb/config-item-passwords/{item.id}/',
            {'config_item': self.config_item.id, 'username': 'administrator', 'remark': '更新说明'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.password_ciphertext, original_ciphertext)
        self.assertEqual(item.username, 'administrator')

    def test_user_without_password_permission_is_denied(self):
        create_response = self.create_password()
        self.client.force_authenticate(self.viewer)

        list_response = self.client.get('/api/cmdb/config-item-passwords/', {'config_item': self.config_item.id})
        reveal_response = self.client.post(
            f'/api/cmdb/config-item-passwords/{create_response.data["id"]}/reveal/',
            {'current_password': 'Admin@123456'},
            format='json',
        )

        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(reveal_response.status_code, 403)

    @override_settings(CMDB_PASSWORD_ENCRYPTION_KEY='')
    def test_create_rejects_missing_encryption_key(self):
        response = self.create_password()

        self.assertEqual(response.status_code, 400)
        self.assertIn('CMDB_PASSWORD_ENCRYPTION_KEY', str(response.data))
        self.assertFalse(ConfigItemPassword.objects.exists())
