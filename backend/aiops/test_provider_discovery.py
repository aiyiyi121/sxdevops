from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from rbac.models import PermissionDefinition, Role
from rbac.services import ensure_builtin_rbac

from .models import AIOpsModelProvider


class ProviderDraftDiscoveryTests(TestCase):
    endpoint = '/api/aiops/admin/providers/discover-models/'

    def setUp(self):
        ensure_builtin_rbac()
        self.user = get_user_model().objects.create_user(username='provider-editor')
        self.user.rbac_roles.add(Role.objects.get(code='platform-admin'))
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.payload = {'base_url': 'https://models.example.com/v1', 'api_key': 'draft-test-key'}

    @mock.patch('aiops.views.list_model_provider_models')
    def test_new_provider_discovers_without_saving_or_probing(self, discover):
        discover.return_value = {'models': [{'id': 'chat-model'}], 'count': 1}
        count = AIOpsModelProvider.objects.count()
        response = self.client.post(self.endpoint, self.payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['models'], [{'id': 'chat-model'}])
        provider = discover.call_args.args[0]
        self.assertIsNone(provider.pk)
        self.assertEqual(provider.get_api_key(), 'draft-test-key')
        self.assertEqual(discover.call_args.kwargs, {'probe': False})
        self.assertEqual(AIOpsModelProvider.objects.count(), count)
        self.assertNotIn('draft-test-key', str(response.data))

    @mock.patch('aiops.views.list_model_provider_models', return_value={'models': []})
    def test_edit_reuses_saved_key_without_persisting_draft_fields(self, discover):
        provider = AIOpsModelProvider.objects.create(name='Saved', base_url=self.payload['base_url'], default_model='old-model')
        provider.set_api_key('saved-test-key')
        provider.save()
        response = self.client.post(self.endpoint, {
            'provider_id': provider.pk, 'base_url': provider.base_url,
            'default_model': 'draft-model', 'api_key': '',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(discover.call_args.args[0].get_api_key(), 'saved-test-key')
        provider.refresh_from_db()
        self.assertEqual(provider.default_model, 'old-model')

    @mock.patch('aiops.views.list_model_provider_models')
    def test_changed_address_requires_explicit_key(self, discover):
        provider = AIOpsModelProvider.objects.create(name='Saved', base_url=self.payload['base_url'])
        provider.set_api_key('saved-test-key')
        provider.save()
        response = self.client.post(self.endpoint, {
            'provider_id': provider.pk, 'base_url': 'https://other.example.com/v1',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('api_key', response.data)
        discover.assert_not_called()

    @mock.patch('aiops.views.list_model_provider_models')
    def test_missing_key_and_invalid_url_do_not_call_supplier(self, discover):
        for payload in [{'base_url': self.payload['base_url']}, {**self.payload, 'base_url': 'invalid'}]:
            response = self.client.post(self.endpoint, payload, format='json')
            self.assertEqual(response.status_code, 400)
        discover.assert_not_called()

    @mock.patch('aiops.views.list_model_provider_models', side_effect=ValueError('Invalid key draft-test-key'))
    def test_supplier_error_redacts_key(self, discover):
        response = self.client.post(self.endpoint, self.payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('draft-test-key', str(response.data))

    @mock.patch('aiops.views.list_model_provider_models')
    def test_config_reader_cannot_discover(self, discover):
        reader = Role.objects.create(code='provider-reader', name='Provider reader')
        reader.permissions.add(PermissionDefinition.objects.get(code='aiops.config.view'))
        self.user.rbac_roles.set([reader])
        response = self.client.post(self.endpoint, self.payload, format='json')
        self.assertEqual(response.status_code, 403)
        discover.assert_not_called()

    @mock.patch('aiops.views.list_model_provider_models')
    def test_anonymous_cannot_discover(self, discover):
        self.client.force_authenticate(None)
        response = self.client.post(self.endpoint, self.payload, format='json')
        self.assertIn(response.status_code, (401, 403))
        discover.assert_not_called()
