import logging
import time

from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError, close_old_connections

from aiops.services import claim_async_chat_job, process_async_chat_job
from aiops.langgraph_management import cleanup_checkpoints
from aiops.remediation import claim_verification, cleanup_verifications, process_verification


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '处理数据库队列中的 LangGraph AIOps 聊天任务'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=float, default=2.0)
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--cleanup-interval', type=float, default=3600)

    def handle(self, *args, **options):
        next_cleanup = time.monotonic() + max(options['cleanup_interval'], 60)
        while True:
            close_old_connections()
            try:
                job = claim_async_chat_job()
            except (OperationalError, ProgrammingError):
                if options['once']:
                    raise
                time.sleep(max(0.1, options['interval']))
                continue
            if job:
                process_async_chat_job(job)
            verification = claim_verification()
            if verification:
                process_verification(verification)
            if not job and not verification and not options['once']:
                if options['cleanup_interval'] > 0 and time.monotonic() >= next_cleanup:
                    try:
                        cleanup_checkpoints(apply=True)
                        cleanup_verifications()
                    except Exception:
                        logger.exception('LangGraph checkpoint cleanup failed')
                    next_cleanup = time.monotonic() + max(options['cleanup_interval'], 60)
                time.sleep(max(0.1, options['interval']))
            if options['once']:
                return
