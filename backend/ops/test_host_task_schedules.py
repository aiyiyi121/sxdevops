from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from ops.models import Host, HostTaskSchedule
from rbac.models import Role
from rbac.services import ensure_builtin_rbac


class HostTaskScheduleApiTests(TestCase):
    def setUp(self):
        ensure_builtin_rbac()
        self.client = APIClient()
        self.user = get_user_model().objects.create_user('schedule-admin', password='Admin@123456')
        role = Role.objects.get(code='ops-admin')
        role.users.add(self.user)
        self.client.force_authenticate(user=self.user)
        self.host = Host.objects.create(
            hostname='schedule-app-01',
            ip_address='192.0.2.2',
            business_line='payment',
            environment='prod',
            status='online',
            ssh_user='root',
            ssh_password='secret',
        )

    def _payload(self):
        return {
            'name': 'nightly-health-check',
            'description': 'nightly audit',
            'task_type': 'run_command',
            'payload': {'command': 'uptime && df -h'},
            'execution_mode': 'ansible',
            'execution_strategy': 'continue',
            'timeout_seconds': 30,
            'schedule_type': 'cron',
            'cron_expression': '0 2 * * *',
            'timezone': 'Asia/Shanghai',
            'overlap_policy': 'skip',
            'enabled': True,
            'target_host_ids': [self.host.id],
            'selection_filters': {},
        }

    def test_preview_schedule_returns_next_runs_and_targets(self):
        response = self.client.post('/api/host-task-schedules/preview_next_runs/', self._payload(), format='json')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['target_count'], 1)
        self.assertTrue(payload['next_runs'])

    def test_preview_schedule_supports_get_params(self):
        payload = self._payload()
        response = self.client.get(
            '/api/host-task-schedules/preview_next_runs/',
            {
                **{key: value for key, value in payload.items() if key not in {'payload', 'selection_filters', 'target_host_ids'}},
                'payload': '{"command":"uptime && df -h"}',
                'selection_filters': '{}',
                'target_host_ids': f'[{self.host.id}]',
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['target_count'], 1)
        self.assertTrue(data['next_runs'])

    def test_create_schedule_sets_target_count_and_next_run(self):
        response = self.client.post('/api/host-task-schedules/', self._payload(), format='json')

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload['target_count'], 1)
        self.assertEqual(payload['task_type'], 'run_command')
        self.assertTrue(payload['next_run_at'])
        self.assertTrue(HostTaskSchedule.objects.filter(id=payload['id']).exists())

    @patch('ops.host_tasks.start_host_task')
    def test_run_now_creates_schedule_execution(self, mock_start_host_task):
        schedule = HostTaskSchedule.objects.create(
            name='interval-refresh',
            description='refresh demo',
            task_type='refresh_metrics',
            payload={},
            selection_filters={},
            target_host_ids=[self.host.id],
            target_snapshot=[{'id': self.host.id, 'hostname': self.host.hostname, 'ip_address': self.host.ip_address}],
            target_count=1,
            execution_mode='ssh',
            execution_strategy='continue',
            timeout_seconds=20,
            schedule_type='interval',
            interval_seconds=1800,
            timezone='Asia/Shanghai',
            overlap_policy='skip',
            enabled=True,
            created_by=self.user.username,
        )

        response = self.client.post(f'/api/host-task-schedules/{schedule.id}/run_now/', {}, format='json')

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload['schedule'], schedule.id)
        self.assertEqual(payload['trigger_source'], 'manual')
        mock_start_host_task.assert_called_once()
