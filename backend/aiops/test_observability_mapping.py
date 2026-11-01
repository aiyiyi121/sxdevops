from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from rbac.models import PermissionDefinition, Role

from . import services
from .models import AIOpsMCPServer


class LogLabelMappingTests(SimpleTestCase):
    def query_logs(self, mappings, environment=None):
        datasource = SimpleNamespace(id=8, name='production-loki', provider='loki', config={})
        link = SimpleNamespace(log_datasource_id=8, log_label_mappings=mappings)
        environment = environment or {
            'name': 'Production',
            'alert_environments': ['prod'],
            'event_environments': ['prod'],
            'k8s_namespaces': {'1': ['production']},
        }
        with mock.patch('aiops.services._build_log_datasource_scope', return_value=([datasource], [link])), mock.patch(
            'aiops.services.run_log_provider_query', return_value={'logs': [{'message': 'order request failed'}]},
        ) as provider_query:
            result = services._query_live_log_datasources(
                environment, service='order-service', levels=['error'], duration_minutes=30,
            )
        return provider_query.call_args.args[2]['query'], result

    def test_live_query_uses_configured_service_and_source_environment_labels(self):
        query, result = self.query_logs([
            {'trace_tag': 'service.name', 'log_label': 'service'},
            {'trace_tag': 'deployment.environment', 'log_label': 'environment'},
        ])

        self.assertEqual(query, '{service="order-service",environment="prod"} | json | detected_level=~"error|err|fatal|critical|crit"')
        self.assertEqual(result['logs'][0]['message'], 'order request failed')
        self.assertEqual(result['source'], 'live_log_datasource')
        self.assertNotIn('namespace=', query)
        self.assertNotIn('container=', query)

    def test_explicit_service_mapping_does_not_add_unconfigured_namespace(self):
        query, _ = self.query_logs([{'trace_tag': 'service.name', 'log_label': 'service_name'}])

        self.assertTrue(query.startswith('{service_name="order-service"} '))
        self.assertNotIn('namespace=', query)
        self.assertNotIn('container=', query)

    def test_empty_mapping_keeps_legacy_container_and_namespace_selector(self):
        query, _ = self.query_logs([])

        self.assertTrue(query.startswith('{container="order-service",namespace="production"} '))

    def test_ambiguous_environment_is_not_inferred_from_first_source(self):
        query, _ = self.query_logs([
            {'trace_tag': 'service.name', 'log_label': 'service'},
            {'trace_tag': 'deployment.environment', 'log_label': 'environment'},
        ], environment={'alert_environments': ['prod', 'staging'], 'event_environments': ['prod']})

        self.assertTrue(query.startswith('{service="order-service"} '))
        self.assertNotIn('environment=', query)


class EventToolAliasPermissionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='event-tool-alias')
        self.permission, _ = PermissionDefinition.objects.get_or_create(
            code='eventwall.view', defaults={'name': 'View event wall', 'category': 'eventwall'},
        )
        self.role = Role.objects.create(code='event-tool-alias', name='Event tool alias')
        self.role.permissions.add(self.permission)
        self.user.rbac_roles.add(self.role)
        self.server = AIOpsMCPServer(
            name='Selected event MCP', server_type=AIOpsMCPServer.SERVER_PLATFORM_BUILTIN,
            tool_whitelist=['query_event_wall', 'query_recent_changes'], is_enabled=True,
        )

    def test_event_query_alias_accepts_selected_event_wall_tool(self):
        self.assertTrue(services._runtime_tool_is_available([self.server], self.user, 'query_events'))

    def test_event_query_alias_still_requires_event_wall_permission(self):
        self.role.permissions.remove(self.permission)

        self.assertFalse(services._runtime_tool_is_available([self.server], self.user, 'query_events'))

    def test_alias_does_not_bypass_selected_platform_tool_whitelist(self):
        self.assertFalse(services._runtime_tool_is_available([], self.user, 'query_events'))
        self.server.tool_whitelist = ['query_recent_changes']
        self.assertFalse(services._runtime_tool_is_available([self.server], self.user, 'query_events'))
        self.server.tool_whitelist = ['query_event_wall']
        self.server.server_type = AIOpsMCPServer.SERVER_HTTP
        self.assertFalse(services._runtime_tool_is_available([self.server], self.user, 'query_events'))
