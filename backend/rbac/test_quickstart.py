from io import StringIO
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .management.commands.quickstart_admin import Command


User = get_user_model()


class QuickstartAdminTests(TestCase):
    @patch('sys.stdin.isatty', return_value=True)
    @patch.object(Command, 'wait_for_application')
    def test_initial_setup_creates_admin_using_entered_password(self, wait, isatty):
        password = 'First-Login-Only-2026!'
        with patch('django.contrib.auth.management.commands.createsuperuser.getpass.getpass', return_value=password):
            call_command('quickstart_admin', stdout=StringIO())

        admin = User.objects.get(username='admin')
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.check_password(password))

    @patch.object(Command, 'wait_for_application')
    def test_rerun_preserves_existing_administrator_and_password(self, wait):
        admin = User.objects.create_superuser(username='existing-owner', password='Keep-Original-2026!')
        original_hash = admin.password
        with patch('django.contrib.auth.management.commands.createsuperuser.getpass.getpass') as prompt:
            call_command('quickstart_admin', stdout=StringIO())

        admin.refresh_from_db()
        prompt.assert_not_called()
        self.assertEqual(admin.password, original_hash)
        self.assertFalse(User.objects.filter(username='admin').exists())

    @patch.object(Command, 'wait_for_application')
    def test_existing_regular_admin_is_not_promoted_or_reset(self, wait):
        user = User.objects.create_user(username='admin', password='Keep-Original-2026!')
        with self.assertRaisesMessage(CommandError, 'already in use'):
            call_command('quickstart_admin', stdout=StringIO())

        user.refresh_from_db()
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password('Keep-Original-2026!'))

    @patch('rbac.management.commands.quickstart_admin.time.sleep')
    @patch('rbac.management.commands.quickstart_admin.time.monotonic', side_effect=[0, 0, 2])
    @patch('rbac.management.commands.quickstart_admin.urlopen', side_effect=URLError('not ready'))
    def test_failed_startup_does_not_create_an_account(self, request, monotonic, sleep):
        with self.assertRaisesMessage(CommandError, 'startup timed out'):
            call_command('quickstart_admin', timeout=1, stdout=StringIO())

        self.assertFalse(User.objects.exists())
