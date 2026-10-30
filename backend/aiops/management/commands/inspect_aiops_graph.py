import json

from django.core.management.base import BaseCommand, CommandError

from aiops.langgraph_management import runtime_summary
from aiops.models import AIOpsChatJob, AIOpsChatMessage, AIOpsGraphNodeRun


class Command(BaseCommand):
    help = '查看 LangGraph 节点耗时、失败原因和恢复状态'

    def add_arguments(self, parser):
        parser.add_argument('--thread-id', required=True)

    def handle(self, *args, **options):
        from aiops.langgraph_pilot import get_langgraph_chat_graph

        thread_id = options['thread_id']
        if not AIOpsChatMessage.objects.filter(metadata__langgraph_thread_id=thread_id).exists():
            raise CommandError('聊天 thread 不存在。')
        snapshot = get_langgraph_chat_graph().get_state({'configurable': {'thread_id': thread_id}})
        result = {'thread_id': thread_id, 'next': snapshot.next, 'summary': runtime_summary(thread_id),
                  'jobs': list(AIOpsChatJob.objects.filter(thread_id=thread_id).values('id', 'status', 'attempt_count', 'error_message')),
                  'nodes': list(AIOpsGraphNodeRun.objects.filter(thread_id=thread_id).values('node', 'status', 'started_at', 'finished_at', 'duration_ms', 'retry_count', 'error'))}
        self.stdout.write(json.dumps(result, ensure_ascii=False, default=str))
