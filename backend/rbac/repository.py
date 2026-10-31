import logging
import time

import requests
from django.core.cache import cache
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


logger = logging.getLogger(__name__)
REPOSITORY = 'aiyiyi121/sxdevops'
GITHUB_API_URL = f'https://api.github.com/repos/{REPOSITORY}'
SNAPSHOT_KEY = 'public:repository:stars:v1'
REFRESH_KEY = 'public:repository:stars:refresh:v1'
REFRESH_SECONDS = 15 * 60
RETRY_SECONDS = 5 * 60


def repository_stats():
    """Keep the last successful count; one visitor refreshes it per interval."""
    snapshot = None
    try:
        snapshot = cache.get(SNAPSHOT_KEY)
        refresh = cache.add(REFRESH_KEY, True, timeout=REFRESH_SECONDS)
    except Exception:
        logger.warning('Repository statistics cache is unavailable')
        refresh = False

    if refresh:
        try:
            headers = {
                'Accept': 'application/vnd.github+json',
                'User-Agent': 'SXDevOps-Repository-Stats',
                'X-GitHub-Api-Version': '2022-11-28',
            }
            if snapshot and snapshot.get('etag'):
                headers['If-None-Match'] = snapshot['etag']
            response = requests.get(GITHUB_API_URL, headers=headers, timeout=(2, 3), allow_redirects=False)
            response.raise_for_status()
            if response.status_code == 304 and snapshot is not None:
                updated = {**snapshot}
            elif response.status_code == 200:
                stars = response.json().get('stargazers_count')
                if type(stars) is not int or stars < 0:
                    raise ValueError('Invalid repository star count')
                updated = {'stars': stars, 'etag': response.headers.get('ETag', '')}
            else:
                raise ValueError('Unexpected repository response')
            updated.update(checked_at=time.time(), updated_at=timezone.now().isoformat())
            # The production Redis cache uses AOF and a persistent volume.
            cache.set(SNAPSHOT_KEY, updated, timeout=None)
            snapshot = updated
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            # Leave the last successful snapshot intact, including on rate limits.
            try:
                cache.set(REFRESH_KEY, True, timeout=RETRY_SECONDS)
            except Exception:
                logger.warning('Repository statistics retry could not be cached')
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
