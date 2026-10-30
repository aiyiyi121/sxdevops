from django.core.management.base import BaseCommand
from django.db import transaction

from aiops.models import AIOpsChatSession


class Command(BaseCommand):
    help = 'Delete untitled AIOps chat sessions for an explicitly selected user.'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True, help='Username whose sessions should be cleaned up.')
        parser.add_argument('--title', default='新会话', help='Exact session title to clean up. Default: 新会话')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show how many sessions would be deleted without deleting them.',
        )

    def handle(self, *args, **options):
        username = str(options['username']).strip()
        title = str(options.get('title') or '新会话').strip() or '新会话'
        dry_run = bool(options.get('dry_run'))

        queryset = AIOpsChatSession.objects.filter(user__username=username, title=title)
        session_count = queryset.count()
        message_count = sum(item.messages.count() for item in queryset.only('id').iterator())

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[dry-run] matched_sessions={session_count} matched_messages={message_count} '
                    f'username={username} title={title}'
                )
            )
            return

        with transaction.atomic():
            deleted_rows, deleted_map = queryset.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'deleted_sessions={deleted_map.get("aiops.AIOpsChatSession", 0)} '
                f'deleted_messages={deleted_map.get("aiops.AIOpsChatMessage", 0)} '
                f'deleted_rows={deleted_rows} username={username} title={title}'
            )
        )
