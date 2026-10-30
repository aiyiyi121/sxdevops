"""Gate background services on the migration-owning web deployment."""
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import OperationalError, ProgrammingError


class Command(BaseCommand):
    help = 'Wait for the application database schema before starting a worker.'

    def add_arguments(self, parser):
        parser.add_argument('--timeout', type=int, default=600)

    def handle(self, *args, **options):
        deadline = time.monotonic() + options['timeout']
        while time.monotonic() < deadline:
            try:
                executor = MigrationExecutor(connections['default'])
                if not executor.migration_plan(executor.loader.graph.leaf_nodes()):
                    self.stdout.write('Application schema is ready.')
                    return
            except (OperationalError, ProgrammingError):
                connections['default'].close()
            time.sleep(2)
        raise CommandError('Timed out waiting for application migrations; inspect the web deployment logs.')
