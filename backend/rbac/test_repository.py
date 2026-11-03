from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.db import OperationalError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import RepositorySnapshot
from .repository import GITHUB_API_URL, REFRESH_KEY, REPOSITORY, SNAPSHOT_KEY, repository_stats


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class RepositoryStatsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.snapshot = {'stars': 123, 'etag': '"previous"', 'updated_at': '2026-11-01T00:00:00+08:00'}

    def tearDown(self):
        cache.clear()

    def github_response(self, stars=124, status=200):
        response = Mock(status_code=status, headers={'ETag': '"latest"'})
        response.json.return_value = {'stargazers_count': stars}
        return response

    @patch('rbac.repository.requests.get')
    def test_success_is_reused_and_upstream_requests_are_bounded(self, get):
        get.return_value = self.github_response()
        self.assertEqual(repository_stats()['stars'], 124)
        self.assertEqual(repository_stats()['stars'], 124)
        get.assert_called_once()
        self.assertEqual(get.call_args.args[0], GITHUB_API_URL)
        self.assertEqual(get.call_args.kwargs['timeout'], (2, 3))
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
        self.assertEqual(RepositorySnapshot.objects.get(pk=REPOSITORY).stars, 124)

    @patch('rbac.repository.requests.get')
    def test_another_request_holds_refresh_gate(self, get):
        cache.set(SNAPSHOT_KEY, self.snapshot, None)
        cache.add(REFRESH_KEY, True, timeout=900)
        self.assertEqual(repository_stats()['stars'], 123)
        get.assert_not_called()

    @patch('rbac.repository.requests.get')
    def test_refresh_interval_and_failure_retry_interval(self, get):
        get.return_value = self.github_response()
        with patch('time.time', return_value=1000):
            self.assertEqual(repository_stats()['stars'], 124)
        with patch('time.time', return_value=1899):
            repository_stats()
        self.assertEqual(get.call_count, 1)
        get.side_effect = requests.Timeout()
        with patch('time.time', return_value=1901):
            self.assertEqual(repository_stats()['stars'], 124)
        with patch('time.time', return_value=2200):
            repository_stats()
        self.assertEqual(get.call_count, 2)
        with patch('time.time', return_value=2202):
            self.assertEqual(repository_stats()['stars'], 124)
        self.assertEqual(get.call_count, 3)

    @patch('rbac.repository.requests.get')
    def test_timeout_preserves_snapshot_and_backs_off(self, get):
        cache.set(SNAPSHOT_KEY, self.snapshot, None)
        get.side_effect = requests.Timeout()
        self.assertEqual(repository_stats()['stars'], 123)
        self.assertEqual(repository_stats()['updated_at'], self.snapshot['updated_at'])
        get.assert_called_once()
        self.assertEqual(cache.get(SNAPSHOT_KEY), self.snapshot)

    @patch('rbac.repository.requests.get')
    def test_rate_limit_preserves_last_success(self, get):
        cache.set(SNAPSHOT_KEY, self.snapshot, None)
        response = self.github_response(status=403)
        response.raise_for_status.side_effect = requests.HTTPError()
        get.return_value = response
        self.assertEqual(repository_stats()['stars'], 123)
        self.assertEqual(repository_stats()['stars'], 123)
        get.assert_called_once()

    @patch('rbac.repository.requests.get')
    def test_expired_gate_refreshes_using_etag(self, get):
        cache.set(SNAPSHOT_KEY, self.snapshot, None)
        get.return_value = self.github_response(status=304)
        result = repository_stats()
        self.assertEqual(result['stars'], 123)
        self.assertNotEqual(result['updated_at'], self.snapshot['updated_at'])
        self.assertEqual(get.call_args.kwargs['headers']['If-None-Match'], '"previous"')

    @patch('rbac.repository.requests.get')
    def test_invalid_payload_cannot_overwrite_valid_count(self, get):
        for count in [-1, True, None, '124', 2 ** 63]:
            with self.subTest(count=count):
                cache.delete(REFRESH_KEY)
                cache.set(SNAPSHOT_KEY, self.snapshot, None)
                get.return_value = self.github_response(stars=count)
                self.assertEqual(repository_stats()['stars'], 123)
                self.assertEqual(cache.get(SNAPSHOT_KEY), self.snapshot)

    @patch('rbac.repository.requests.get')
    def test_zero_is_a_valid_count(self, get):
        get.return_value = self.github_response(stars=0)
        self.assertEqual(repository_stats()['stars'], 0)

    @patch('rbac.repository.requests.get', side_effect=requests.ConnectionError())
    def test_first_fetch_failure_is_unknown_not_a_fabricated_zero(self, get):
        self.assertIsNone(repository_stats()['stars'])
        self.assertIsNone(repository_stats()['updated_at'])
        get.assert_called_once()

    @patch('rbac.repository.requests.get')
    @patch('rbac.repository.cache.get', side_effect=ConnectionError())
    def test_cache_outage_does_not_trigger_unthrottled_upstream_calls(self, cache_get, get):
        with self.assertLogs('rbac.repository', level='WARNING'):
            self.assertIsNone(repository_stats()['stars'])
        get.assert_not_called()

    def save_history(self, stars=123):
        return RepositorySnapshot.objects.create(
            repository=REPOSITORY, stars=stars, etag=self.snapshot['etag'],
            updated_at=self.snapshot['updated_at'],
        )

    @patch('rbac.repository.requests.get', side_effect=requests.Timeout())
    def test_redis_loss_and_github_timeout_use_database_history(self, get):
        record = self.save_history()
        record.refresh_from_db()
        result = repository_stats()
        self.assertEqual(result['stars'], 123)
        self.assertEqual(cache.get(SNAPSHOT_KEY)['stars'], 123)
        self.assertEqual(RepositorySnapshot.objects.get(pk=REPOSITORY).stars, 123)
        self.assertEqual(result['updated_at'], record.updated_at.isoformat())

    @patch('rbac.repository.requests.get')
    @patch('rbac.repository.cache.get', side_effect=ConnectionError())
    def test_redis_outage_uses_database_without_unthrottled_requests(self, cache_get, get):
        self.save_history()
        with self.assertLogs('rbac.repository', level='WARNING'):
            self.assertEqual(repository_stats()['stars'], 123)
        get.assert_not_called()

    @patch('rbac.repository.requests.get', side_effect=requests.Timeout())
    def test_database_history_is_available_while_another_visitor_refreshes(self, get):
        self.save_history(stars=0)
        cache.add(REFRESH_KEY, True, timeout=900)
        self.assertEqual(repository_stats()['stars'], 0)
        get.assert_not_called()

    @patch('rbac.repository.requests.get')
    def test_database_history_updates_after_upstream_recovers(self, get):
        self.save_history()
        get.return_value = self.github_response(stars=125)
        self.assertEqual(repository_stats()['stars'], 125)
        self.assertEqual(RepositorySnapshot.objects.get(pk=REPOSITORY).stars, 125)

    @patch('rbac.repository.requests.get')
    @patch('rbac.repository.cache.set', side_effect=ConnectionError())
    def test_redis_write_failure_still_returns_and_persists_fresh_result(self, cache_set, get):
        get.return_value = self.github_response(stars=125)
        with self.assertLogs('rbac.repository', level='WARNING'):
            self.assertEqual(repository_stats()['stars'], 125)
        self.assertEqual(RepositorySnapshot.objects.get(pk=REPOSITORY).stars, 125)

    @patch('rbac.repository.requests.get')
    @patch('rbac.repository.RepositorySnapshot.objects.update_or_create', side_effect=OperationalError())
    def test_database_write_failure_keeps_fresh_redis_result(self, persist, get):
        get.return_value = self.github_response()
        with self.assertLogs('rbac.repository', level='WARNING'):
            self.assertEqual(repository_stats()['stars'], 124)
        self.assertEqual(cache.get(SNAPSHOT_KEY)['stars'], 124)

    @patch('rbac.repository.requests.get', side_effect=requests.Timeout())
    @patch('rbac.repository.RepositorySnapshot.objects.filter', side_effect=OperationalError())
    def test_both_stores_unavailable_returns_unknown_without_500(self, query, get):
        with self.assertLogs('rbac.repository', level='WARNING'):
            self.assertIsNone(repository_stats()['stars'])

    @patch('rbac.repository.requests.get', side_effect=requests.Timeout())
    def test_invalid_redis_snapshot_falls_back_to_database(self, get):
        self.save_history()
        for snapshot in [{'stars': True}, {'stars': 9, 'updated_at': 'invalid'}, 'invalid']:
            with self.subTest(snapshot=snapshot):
                cache.set(SNAPSHOT_KEY, snapshot, None)
                self.assertEqual(repository_stats()['stars'], 123)

    @patch('rbac.repository.requests.get', side_effect=requests.Timeout())
    def test_existing_redis_history_is_persisted_even_if_github_fails(self, get):
        cache.set(SNAPSHOT_KEY, self.snapshot, None)
        self.assertEqual(repository_stats()['stars'], 123)
        self.assertEqual(RepositorySnapshot.objects.get(pk=REPOSITORY).stars, 123)

    @patch('cmdb.views._bump_cmdb_ledger_cache_version')
    def test_repository_history_does_not_invalidate_cmdb_ledger(self, bump):
        self.save_history()
        bump.assert_not_called()

    @patch('rbac.repository.requests.get')
    def test_endpoint_is_public_read_only_and_cannot_select_another_repository(self, get):
        get.return_value = self.github_response()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token expired-token')
        response = client.get('/api/site-settings/repository/?repository=other/project&refresh=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['repository'], 'aiyiyi121/sxdevops')
        self.assertEqual(response.json()['stars'], 124)
        self.assertIn('max-age=300', response['Cache-Control'])
        self.assertEqual(client.post('/api/site-settings/repository/', {}).status_code, 405)
        client.get('/api/site-settings/repository/?refresh=1')
        get.assert_called_once()
