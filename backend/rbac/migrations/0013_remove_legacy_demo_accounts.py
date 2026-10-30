from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.db import migrations


def remove_legacy_demo_accounts(apps, schema_editor):
    database = schema_editor.connection.alias
    User = apps.get_model(settings.AUTH_USER_MODEL)
    Token = apps.get_model('authtoken', 'Token')
    Session = apps.get_model('sessions', 'Session')
    users = User.objects.using(database).filter(username__in=('demo', 'demo_ai'))
    user_ids = {str(pk) for pk in users.values_list('pk', flat=True)}
    if not user_ids:
        return

    # Revoke both API tokens and Django sessions before removing the accounts.
    Token.objects.using(database).filter(user_id__in=user_ids).delete()
    store = SessionStore()
    session_keys = [
        session.pk
        for session in Session.objects.using(database).only('session_key', 'session_data').iterator()
        if str(store.decode(session.session_data).get(SESSION_KEY)) in user_ids
    ]
    Session.objects.using(database).filter(pk__in=session_keys).delete()
    # Cascades remove account bindings and copied chats; source chats and audit logs remain.
    users.delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('admin', '0003_logentry_add_action_flag_choices'),
        ('authtoken', '0004_alter_tokenproxy_options'),
        ('sessions', '0001_initial'),
        ('aiops', '0029_rename_qwen_provider'),
        ('ops', '0060_align_task_metadata_and_index_names'),
        ('rbac', '0012_restore_sxdevops_site_name'),
    ]

    operations = [
        migrations.RunPython(remove_legacy_demo_accounts, migrations.RunPython.noop),
    ]
