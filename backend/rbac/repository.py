import logging
import time

import requests
from django.core.cache import cache
from django.db import DatabaseError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import RepositorySnapshot


logger = logging.getLogger(__name__)
REPOSITORY = 'aiyiyi121/sxdevops'
GITHUB_API_URL = f'https://api.github.com/repos/{REPOSITORY}'
SNAPSHOT_KEY = 'public:repository:stars:v1'
REFRESH_KEY = 'public:repository:stars:refresh:v1'
REFRESH_SECONDS = 15 * 60
RETRY_SECONDS = 5 * 60


def _valid_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        return False
    stars = snapshot.get('stars')
    if type(stars) is not int or not 0 <= stars <= 9223372036854775807:
        return False
    try:
        return parse_datetime(snapshot.get('updated_at', '')) is not None
    except (TypeError, ValueError):
        return False


def _database_snapshot():
    try:
        record = RepositorySnapshot.objects.filter(repository=REPOSITORY).first()
        if record is not None:
            return {'stars': record.stars, 'etag': record.etag, 'updated_at': record.updated_at.isoformat()}
    except DatabaseError:
        logger.warning('Repository statistics database is unavailable')
    return None


def _persist_snapshot(snapshot):
    try:
        RepositorySnapshot.objects.update_or_create(
            repository=REPOSITORY,
            defaults={
                'stars': snapshot['stars'],
                'etag': snapshot.get('etag', '')[:255],
                'updated_at': parse_datetime(snapshot['updated_at']),
            },
        )
    except DatabaseError:
        logger.warning('Repository statistics snapshot could not be persisted')


def repository_stats():
    """Serve the last success from Redis or the database, with bounded refreshes."""
    snapshot = None
    cached_snapshot = None
    try:
        snapshot = cache.get(SNAPSHOT_KEY)
        cached_snapshot = snapshot
        refresh = cache.add(REFRESH_KEY, True, timeout=REFRESH_SECONDS)
    except Exception:
        logger.warning('Repository statistics cache is unavailable')
        refresh = False

    if not _valid_snapshot(snapshot):
        snapshot = _database_snapshot()

    if refresh:
        try:
            headers = {
                'Accept': 'application/vnd.github+json',
                'User-Agent': 'SXDevOps-Repository-Stats',
                'X-GitHub-Api-Version': '2022-11-28',
            }
            if snapshot and isinstance(snapshot.get('etag'), str) and snapshot['etag']:
                headers['If-None-Match'] = snapshot['etag']
            response = requests.get(GITHUB_API_URL, headers=headers, timeout=(2, 3), allow_redirects=False)
            response.raise_for_status()
            if response.status_code == 304 and snapshot is not None:
                updated = {**snapshot}
            elif response.status_code == 200:
                stars = response.json().get('stargazers_count')
                if type(stars) is not int or not 0 <= stars <= 9223372036854775807:
                    raise ValueError('Invalid repository star count')
                updated = {'stars': stars, 'etag': response.headers.get('ETag', '')}
            else:
                raise ValueError('Unexpected repository response')
            updated.update(checked_at=time.time(), updated_at=timezone.now().isoformat())
            snapshot = updated
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            # Leave the last successful snapshot intact, including on rate limits.
            try:
                cache.set(REFRESH_KEY, True, timeout=RETRY_SECONDS)
            except Exception:
                logger.warning('Repository statistics retry could not be cached')
        # Persist even a pre-existing Redis snapshot when GitHub is unreachable.
        if snapshot is not None:
            _persist_snapshot(snapshot)

    if snapshot is not None and snapshot != cached_snapshot:
        try:
            # Restore evicted Redis data from durable history as well.
            cache.set(SNAPSHOT_KEY, snapshot, timeout=None)
        except Exception:
            logger.warning('Repository statistics snapshot could not be cached')

    return {
        'repository': REPOSITORY,
        'stars': snapshot['stars'] if snapshot else None,
        'updated_at': snapshot['updated_at'] if snapshot else None,
    }


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def public_repository_stats(request):
    # Fixed public repository metadata; callers cannot choose a URL or force a refresh.
    response = Response(repository_stats())
    response['Cache-Control'] = 'public, max-age=300, stale-if-error=86400'
    return response
