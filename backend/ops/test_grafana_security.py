from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from unittest.mock import patch
from rest_framework.test import APIClient
from rbac.models import PermissionDefinition, Role

from .grafana_urls import validate_grafana_url
from .models import GrafanaSetting
from .serializers import GrafanaSettingSerializer


class GrafanaURLSecurityTests(SimpleTestCase):
    def test_browser_links_reject_executable_urls_and_obfuscated_authorities(self):
        for value in (
            'javascript:alert(1)', 'data:text/html,test', 'vbscript:msgbox(1)',
            '//untrusted.example/d/test', '/\\untrusted.example', '/%2funtrusted.example',
            '/%5cuntrusted.example', '/%0atest', 'https://name:secret@grafana.example/d/test',
            'https://grafana.example:invalid/d/test', 'https://grafana.example\n/d/test',
            'https:untrusted.example', None, {},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_grafana_url(value)

    def test_valid_internal_and_external_dashboards_remain_supported(self):
        for value in ('', '/grafana', '/d/nodes?var-env=demo', 'http://grafana.internal:3000', 'https://grafana.example/d/nodes'):
            self.assertEqual(validate_grafana_url(value), value)

    def test_path_fields_cannot_override_the_configured_service(self):
        for value in ('https://untrusted.example/d/nodes', '//untrusted.example/d/nodes', 'd/nodes'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_grafana_url(value, path_only=True)

    def test_serializer_checks_all_url_aliases_before_persisting(self):
        for field in ('full_url', 'url', 'path'):
            serializer = GrafanaSettingSerializer(data={
                'url': 'https://grafana.example',
                'dashboards': [{'title': 'test', field: 'javascript:alert(1)'}],
            })
            self.assertFalse(serializer.is_valid(), field)
            self.assertIn('dashboards', serializer.errors)

    def test_partial_update_rechecks_existing_unsafe_values(self):
        instance = GrafanaSetting(url='https://grafana.example', dashboards=[{'url': 'data:text/html,test'}])
        serializer = GrafanaSettingSerializer(instance=instance, data={'enabled': True}, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn('dashboards', serializer.errors)

    def test_site_proxy_and_valid_dashboards_pass_validation(self):
        serializer = GrafanaSettingSerializer(data={
            'url': '/grafana', 'default_path': '/d/nodes',
            'dashboards': [{'path': '/d/nodes', 'full_url': 'https://grafana.example/d/nodes'}],
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_overview_does_not_publish_unsafe_legacy_dashboard_links(self):
        from .observability_views import _grafana_meta

        config = {
            'enabled': True, 'url': 'javascript:alert(1)', 'default_path': '//untrusted.example',
            'dashboards': [{'title': 'test', 'url': 'data:text/html,test', 'panel_count': 0}],
        }
        with patch('ops.observability_views._grafana_config', return_value=config):
            result = _grafana_meta()
        self.assertEqual(result['url'], '')
        self.assertEqual(result['embed_url'], '')
        self.assertEqual(result['dashboards'][0]['url'], '')


class GrafanaConfigurationAPISecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username='grafana-security-admin', is_superuser=True)
        self.client.force_authenticate(user=self.user)

    def test_unsafe_dashboard_is_rejected_without_persisting(self):
        response = self.client.put('/api/observability/grafana/config/', {
            'url': '/grafana',
            'dashboards': [{'title': 'test', 'full_url': 'javascript:alert(1)'}],
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(GrafanaSetting.objects.filter(name='default').exists())

    def test_configuration_updates_still_require_manage_permission(self):
        self.user.is_superuser = False
        self.user.save(update_fields=['is_superuser'])
        viewer = Role.objects.create(code='grafana-security-viewer', name='Grafana security viewer')
        viewer.permissions.add(PermissionDefinition.objects.get(code='ops.grafana.view'))
        viewer.users.add(self.user)
        self.assertEqual(self.client.get('/api/observability/grafana/config/').status_code, 200)
        response = self.client.put('/api/observability/grafana/config/', {'url': '/grafana'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(GrafanaSetting.objects.filter(name='default').exists())

    def test_anonymous_requests_cannot_read_configuration(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/observability/grafana/config/').status_code, 401)
