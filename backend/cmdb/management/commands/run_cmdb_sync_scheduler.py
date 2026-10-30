from django.core.management.base import BaseCommand

from cmdb.sync_scheduler import run_scheduler_loop
from cmdb.views import run_due_collection_jobs


class Command(BaseCommand):
    help = '运行 CMDB 定时同步调度器，触发到期的资产采集任务'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='仅扫描一次到期任务并立即退出')
        parser.add_argument('--interval', type=int, default=None, help='轮询间隔秒数，默认读取 settings.CMDB_SYNC_SCHEDULER_POLL_SECONDS')
        parser.add_argument('--limit', type=int, default=10, help='单次最多执行的同步任务数量')
        parser.add_argument('--actor', type=str, default='system-scheduler', help='调度器写入记录时使用的操作人标识')

    def handle(self, *args, **options):
        limit = max(1, min(int(options.get('limit') or 10), 50))
        actor = options.get('actor') or 'system-scheduler'
        if options['once']:
            result = run_due_collection_jobs(limit=limit, operator=actor)
            self.stdout.write(self.style.SUCCESS(
                f"扫描完成：执行 {result['executed_count']} 个任务，摘要 {result['summary']}"
            ))
            return
        self.stdout.write(self.style.SUCCESS(
            f'CMDB 定时同步调度器已启动，轮询间隔={options.get("interval") or "settings 默认值"}秒，单次上限={limit}'
        ))
        run_scheduler_loop(interval_seconds=options.get('interval'), limit=limit, operator=actor)
