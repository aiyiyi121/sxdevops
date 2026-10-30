"""Guide first-time Compose and Kubernetes users through administrator setup."""
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Wait for the application and interactively create admin only if no administrator exists.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--timeout', type=int, default=600)

    def wait_for_application(self, timeout):
        self.stdout.write('Waiting for application startup and migrations...')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urlopen('http://127.0.0.1:8000/login', timeout=3) as response:
                    if response.status == 200:
                        return
            except (HTTPError, URLError, OSError):
                pass
            time.sleep(2)
        raise CommandError('Application startup timed out. Inspect the sxdevops application logs in Compose or Kubernetes.')

    def handle(self, *args, **options):
        self.wait_for_application(options['timeout'])
        users = get_user_model().objects
        if users.filter(is_superuser=True).exists():
            self.stdout.write('An administrator already exists. Sign in with your existing account and password.')
            return
        if users.filter(username='admin').exists():
            raise CommandError('The username admin is already in use. Create an administrator manually with createsuperuser.')
        if not sys.stdin.isatty():
            raise CommandError('Run the startup script in an interactive terminal to set the administrator password.')

        self.stdout.write('Create your administrator: username admin. Enter and confirm a new password (input is hidden).')
        call_command('createsuperuser', username='admin', email='', interactive=True, stdout=self.stdout, stderr=self.stderr)
