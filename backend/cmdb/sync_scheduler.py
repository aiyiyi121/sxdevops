import logging
import time

from django.conf import settings

from .views import run_due_collection_jobs


logger = logging.getLogger(__name__)


def run_scheduler_loop(interval_seconds=None, limit=10, operator='system-scheduler'):
    interval = max(int(interval_seconds or getattr(settings, 'CMDB_SYNC_SCHEDULER_POLL_SECONDS', 60)), 10)
    logger.info('CMDB sync scheduler started with interval=%s seconds, limit=%s', interval, limit)
    while True:
        try:
            result = run_due_collection_jobs(limit=limit, operator=operator)
            if result['executed_count']:
                logger.info('CMDB sync scheduler executed %s jobs: %s', result['executed_count'], result['summary'])
        except Exception:
            logger.exception('CMDB sync scheduler loop failed')
        time.sleep(interval)
