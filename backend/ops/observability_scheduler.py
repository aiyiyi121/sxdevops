from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

_scheduler_lock = threading.Lock()
_scheduler_started = False


def _seconds_until_next_hour():
    now = timezone.localtime()
    next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    return max(1, int((next_hour - now).total_seconds()))


def scheduler_should_autostart():
    blocked = {'test', 'makemigrations', 'migrate', 'collectstatic', 'shell', 'check'}
    if any(item in sys.argv for item in blocked):
        return False
    if os.environ.get('RUN_MAIN') == 'false':
        return False
    return True


def run_observability_history_scheduler_loop():
    logger.info('observability history scheduler loop started')
    startup_delay = int(os.environ.get('SXDEVOPS_OBSERVABILITY_SCHEDULER_START_DELAY', '15'))
    if startup_delay > 0:
        time.sleep(startup_delay)
    while True:
        sleep_seconds = _seconds_until_next_hour()
        time.sleep(sleep_seconds)
        try:
            from .observability_views import refresh_today_system_posture_history

            result = refresh_today_system_posture_history(force_refresh=True, actor='system-scheduler')
            logger.info('observability history scheduler refreshed today snapshot: %s', result)
        except Exception:
            logger.exception('observability history scheduler refresh failed')


def start_observability_history_scheduler():
    global _scheduler_started
    if _scheduler_started or not scheduler_should_autostart():
        return False
    with _scheduler_lock:
        if _scheduler_started:
            return False
        thread = threading.Thread(
            target=run_observability_history_scheduler_loop,
            name='observability-history-scheduler',
            daemon=True,
        )
        thread.start()
        _scheduler_started = True
        logger.info('observability history scheduler thread started')
        return True
