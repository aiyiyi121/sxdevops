from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from rest_framework.test import APIClient

from .models import SystemModuleSetting
from .services import ensure_system_module_settings, get_default_system_page, get_system_module_settings


INCOMPLETE_MODULE_CODES = {'cmdb.requests', 'cmdb.thresholds', 'cmdb.views', 'observability.rum'}


class SystemModuleVisibilityTests(TestCase):
    def test_incomplete_modules_are_hidden_on_initialization(self):
        SystemModuleSetting.objects.all().delete()

        settings = {item['code']: item for item in get_system_module_settings()}

        self.assertEqual({code for code, item in settings.items() if item['incomplete']}, INCOMPLETE_MODULE_CODES)
        for code, item in settings.items():
            with self.subTest(code=code):
                self.assertEqual(item['enabled'], code not in INCOMPLETE_MODULE_CODES)
                self.assertEqual(SystemModuleSetting.objects.get(code=code).enabled, item['enabled'])

    def test_initialization_preserves_manually_enabled_incomplete_module(self):
        SystemModuleSetting.objects.update_or_create(code='observability.rum', defaults={'enabled': True})

        ensure_system_module_settings()

        settings = {item['code']: item for item in get_system_module_settings()}
        self.assertTrue(settings['observability.rum']['enabled'])
        self.assertTrue(settings['observability.rum']['incomplete'])

    def test_module_api_exposes_incomplete_status_and_allows_manual_enable(self):
        admin = get_user_model().objects.create_superuser(username='module-visibility-admin', password='test-password')
        client = APIClient()
        client.force_authenticate(admin)

        response = client.get('/api/module-settings/')

        self.assertEqual(response.status_code, 200)
        settings = {item['code']: item for item in response.json()}
        for code in INCOMPLETE_MODULE_CODES:
            with self.subTest(code=code):
                self.assertTrue(settings[code]['incomplete'])
                self.assertFalse(settings[code]['enabled'])

        response = client.put('/api/module-settings/', {
            'modules': [{'code': 'observability.rum', 'enabled': True}],
        }, format='json')

        self.assertEqual(response.status_code, 200)
        settings = {item['code']: item for item in client.get('/api/module-settings/').json()}
        self.assertTrue(settings['observability.rum']['enabled'])
        self.assertTrue(settings['observability.rum']['incomplete'])
        self.assertFalse(settings['cmdb.requests']['enabled'])

    def test_migration_hides_existing_incomplete_modules_and_resets_hidden_default(self):
        ensure_system_module_settings()
        SystemModuleSetting.objects.filter(code__in=INCOMPLETE_MODULE_CODES).update(enabled=True)
        SystemModuleSetting.objects.filter(is_default=True).update(is_default=False)
        SystemModuleSetting.objects.filter(code='observability.rum').update(is_default=True, sort_order=0)
        SystemModuleSetting.objects.filter(code='containers.docker').update(enabled=False)

        migration = import_module('rbac.migrations.0009_hide_incomplete_modules')
        migration.hide_incomplete_modules(apps, SimpleNamespace(connection=connection))

        self.assertFalse(SystemModuleSetting.objects.filter(code__in=INCOMPLETE_MODULE_CODES, enabled=True).exists())
        self.assertFalse(SystemModuleSetting.objects.filter(is_default=True).exists())
        self.assertEqual(get_default_system_page(), '/dashboard')
        self.assertEqual(SystemModuleSetting.objects.get(code='observability.rum').sort_order, 0)
        self.assertFalse(SystemModuleSetting.objects.get(code='containers.docker').enabled)
        self.assertTrue(SystemModuleSetting.objects.get(code='system.modules').enabled)
