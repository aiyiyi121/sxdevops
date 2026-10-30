import json

from django.core.management.base import BaseCommand

from aiops.langgraph_management import cleanup_checkpoints


class Command(BaseCommand):
    help = '清理已完成且过期的 LangGraph checkpoint；默认仅预览'

    def add_arguments(self, parser):
        parser.add_argument('--retention-days', type=int, default=None)
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        result = cleanup_checkpoints(retention_days=options['retention_days'], limit=options['limit'], apply=options['apply'])
        self.stdout.write(json.dumps(result, ensure_ascii=False))
