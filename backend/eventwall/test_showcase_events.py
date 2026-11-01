import os
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from eventwall.management.commands.refresh_showcase_events import GENERATOR, refresh_events
from eventwall.models import EventEnvironment, EventRecord, EventSource
from eventwall.views import _classify_event_source, _infer_event_category


class ShowcaseEventTests(TestCase):
    def setUp(self):
        EventEnvironment.objects.get_or_create(code='prod', defaults={'name': '生产环境'})

    def test_command_requires_explicit_environment_opt_in(self):
        with patch.dict(os.environ, {'SXDEVOPS_SHOWCASE_EVENTS': '0'}):
            with self.assertRaises(CommandError):
                call_command('refresh_showcase_events', stdout=StringIO())
        self.assertEqual(EventRecord.objects.count(), 0)

    def test_hour_has_all_categories_and_external_sources_without_future_times(self):
        now = timezone.now().replace(minute=1)
        self.assertEqual(refresh_events(hours=2, now=now)[0], 12)
        events = list(EventRecord.objects.all())
        self.assertEqual({_infer_event_category(e) for e in events}, {
            'application_release', 'db_change', 'config_change', 'ops_transaction', 'task_center',
        })
        self.assertEqual({_classify_event_source(e)['code'] for e in events if e.source_type == 'external'}, {'jenkins','gitlab','jira','argocd'})
        self.assertTrue(all(e.occurred_at <= now for e in events))
        self.assertTrue(all('demo' not in (e.title + e.summary + str(e.tags)).lower() for e in events))
        self.assertTrue(all(not e.application for e in events if e.metadata['event_category'] != 'application_release'))
        jenkins = EventSource.objects.get(code='jenkins')
        self.assertEqual(jenkins.auth_type, 'webhook')
        self.assertFalse(jenkins.verify_token(''))

    def test_rerun_is_idempotent_and_retention_does_not_delete_other_events(self):
        now = timezone.now()
        refresh_events(now=now)
        self.assertEqual(refresh_events(now=now)[0], 0)
        historical = EventRecord.objects.first()
        EventRecord.objects.filter(pk=historical.pk).update(occurred_at=now-timedelta(days=15))
        unrelated = EventRecord.objects.create(module='ops',category='execution',action='deploy',title='已有业务记录',occurred_at=now-timedelta(days=20))
        refresh_events(now=now+timedelta(hours=1))
        self.assertFalse(EventRecord.objects.filter(pk=historical.pk).exists())
        self.assertTrue(EventRecord.objects.filter(pk=unrelated.pk).exists())
        self.assertEqual(EventRecord.objects.filter(metadata__generated_by=GENERATOR).count(), 11)

    def test_events_use_the_configured_environment_code_and_reject_unknown_environments(self):
        EventEnvironment.objects.create(code='commerce-prod', name='电商生产环境', aliases=['commerce-production'])
        with self.assertRaises(CommandError):
            refresh_events(environment='unknown-environment')
        self.assertEqual(EventRecord.objects.count(), 0)
        refresh_events(environment='commerce-production')
        self.assertEqual(set(EventRecord.objects.values_list('environment', flat=True)), {'commerce-prod'})
        self.assertTrue(all(e.metadata['environment_name'] == '电商生产环境' for e in EventRecord.objects.all()))
