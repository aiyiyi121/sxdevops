from django.apps import AppConfig
from django.db.models.signals import post_migrate


def sync_builtin_cmdb(sender, **kwargs):
    from .builtins import ensure_builtin_cmdb

    ensure_builtin_cmdb()


class CmdbConfig(AppConfig):
    name = 'cmdb'

    def ready(self):
        from . import signals  # noqa: F401
        post_migrate.connect(sync_builtin_cmdb, sender=self)
