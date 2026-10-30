from importlib import import_module
from io import BytesIO
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from eventwall.models import EventRecord

from .models import PermissionDefinition, Role, SiteSetting
from .services import ensure_builtin_rbac


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SiteSettingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_builtin_rbac()
        cls.admin = get_user_model().objects.create_superuser(username='site-admin', password='test-password')
        cls.reader = get_user_model().objects.create_user(username='site-reader')
        cls.demo = get_user_model().objects.create_user(username='demo')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def icon_upload(self, color='blue', image_format='PNG', size=(48, 48)):
        output = BytesIO()
        Image.new('RGB', size, color).save(output, format=image_format)
        return SimpleUploadedFile(f'icon.{image_format.lower()}', output.getvalue(), content_type='image/png')

    def save_settings(self, **data):
        return self.client.put('/api/site-settings/manage/', {'site_name': '测试运维平台', **data}, format='multipart')

    def test_public_defaults_and_icon_do_not_require_login(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token expired-token')
        response = client.get('/api/site-settings/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'site_name': 'SXDevOps', 'icon_url': ''})
        self.assertFalse(SiteSetting.objects.exists())
        self.assertEqual(client.get('/api/site-settings/icon/').status_code, 404)

    def test_save_name_and_icon_persists_public_branding_and_audit(self):
        response = self.save_settings(site_name='  测试运维平台  ', icon=self.icon_upload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['site_name'], '测试运维平台')
        public = APIClient().get('/api/site-settings/').json()
        self.assertEqual(public, response.json())
        icon = APIClient().get(public['icon_url'])
        self.assertEqual(icon.status_code, 200)
        self.assertEqual(icon['Content-Type'], 'image/png')
        self.assertEqual(icon['X-Content-Type-Options'], 'nosniff')
        with Image.open(BytesIO(icon.content)) as image:
            self.assertEqual(image.size, (48, 48))
            self.assertEqual(image.format, 'PNG')
        self.assertEqual(SiteSetting.objects.get(pk=1).updated_by, self.admin.username)
        self.assertTrue(EventRecord.objects.filter(action='update_site_settings').exists())

    def test_name_only_update_preserves_icon_and_replacement_changes_url(self):
        first = self.save_settings(icon=self.icon_upload()).json()
        name_only = self.save_settings(site_name='另一个网站').json()
        self.assertEqual(name_only['icon_url'], first['icon_url'])
        replacement = self.save_settings(icon=self.icon_upload(color='red')).json()
        self.assertNotEqual(replacement['icon_url'], first['icon_url'])
        self.assertEqual(SiteSetting.objects.count(), 1)

    def test_reset_restores_default_icon(self):
        self.save_settings(icon=self.icon_upload())
        response = self.save_settings(site_name='SXDevOps', reset_icon=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'site_name': 'SXDevOps', 'icon_url': ''})
        self.assertEqual(APIClient().get('/api/site-settings/icon/').status_code, 404)

    def test_write_requires_module_permission_and_blocks_demo(self):
        anonymous = APIClient()
        self.assertIn(anonymous.put('/api/site-settings/manage/', {'site_name': '无权限'}, format='json').status_code, [401, 403])
        for user in [self.reader, self.demo]:
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                self.assertEqual(self.save_settings().status_code, 403)
        self.assertFalse(SiteSetting.objects.exists())
        role = Role.objects.create(code='site-editor', name='基础配置管理员')
        role.permissions.add(PermissionDefinition.objects.get(code='rbac.module.manage'))
        role.users.add(self.reader)
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.save_settings().status_code, 200)

    def test_site_name_accepts_ten_characters(self):
        for name in ['SXDevOpsXX', '运维平台网站名称设置']:
            with self.subTest(name=name):
                response = self.save_settings(site_name=name)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['site_name'], name)

    def test_default_name_migration_preserves_custom_branding(self):
        migrate_name = import_module('rbac.migrations.0012_restore_sxdevops_site_name').restore_default_site_name
        for name, expected in [('exampleOps', 'SXDevOps'), ('自定义平台', '自定义平台')]:
            with self.subTest(name=name):
                setting, _ = SiteSetting.objects.update_or_create(
                    pk=1, defaults={'site_name': name, 'icon_data': b'custom-icon', 'updated_by': 'site-owner'},
                )
                migrate_name(apps, SimpleNamespace(connection=connection))
                setting.refresh_from_db()
                self.assertEqual(setting.site_name, expected)
                self.assertEqual(bytes(setting.icon_data), b'custom-icon')
                self.assertEqual(setting.updated_by, 'site-owner')

    def test_invalid_name_cannot_partially_update_icon(self):
        initial = self.save_settings(icon=self.icon_upload()).json()
        for name in ['', '   ', 'A' * 11, '名' * 11]:
            with self.subTest(name=name):
                self.assertEqual(self.save_settings(site_name=name, reset_icon=True).status_code, 400)
        self.assertEqual(APIClient().get('/api/site-settings/').json(), initial)

    def test_icon_validation_rejects_invalid_oversized_and_conflicting_uploads(self):
        invalid_icons = [
            SimpleUploadedFile('fake.png', b'not an image', content_type='image/png'),
            SimpleUploadedFile('icon.svg', b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', content_type='image/svg+xml'),
            SimpleUploadedFile('large.png', b'0' * (1024 * 1024 + 1), content_type='image/png'),
            self.icon_upload(size=(2049, 1)),
            self.icon_upload(image_format='GIF'),
        ]
        for icon in invalid_icons:
            with self.subTest(filename=icon.name):
                self.assertEqual(self.save_settings(icon=icon).status_code, 400)
        self.assertEqual(self.save_settings(icon=self.icon_upload(), reset_icon=True).status_code, 400)
        self.assertFalse(SiteSetting.objects.exists())

    def test_supported_formats_are_resized_and_normalized_to_png(self):
        for image_format in ['PNG', 'JPEG', 'WEBP', 'ICO']:
            with self.subTest(image_format=image_format):
                response = self.save_settings(icon=self.icon_upload(image_format=image_format, size=(512, 512)))
                self.assertEqual(response.status_code, 200)
                icon = APIClient().get(response.json()['icon_url'])
                with Image.open(BytesIO(icon.content)) as image:
                    self.assertLessEqual(max(image.size), 256)
                    self.assertEqual(image.format, 'PNG')
