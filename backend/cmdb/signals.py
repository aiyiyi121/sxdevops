from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from ops.models import Host

from .models import ConfigItem, ResourceNode
from .sync import (
    delete_config_item_for_host,
    delete_host_for_config_item,
    sync_config_item_to_host,
    sync_host_to_config_item,
)


def invalidate_ledger_cache(sender, **kwargs):
    # Saves outside the API (collectors, jobs and admin) must invalidate summaries too.
    if sender._meta.app_label not in {'cmdb', 'rbac', 'auth'}:
        return
    from .views import _bump_cmdb_ledger_cache_version
    _bump_cmdb_ledger_cache_version()
    # Readers may fill the new cache version before this transaction commits.
    connection = transaction.get_connection(kwargs.get('using'))
    if connection.in_atomic_block:
        transaction.on_commit(_bump_cmdb_ledger_cache_version, using=kwargs.get('using'))


post_save.connect(invalidate_ledger_cache, dispatch_uid='cmdb_ledger_save')
post_delete.connect(invalidate_ledger_cache, dispatch_uid='cmdb_ledger_delete')
m2m_changed.connect(invalidate_ledger_cache, dispatch_uid='cmdb_ledger_membership')


@receiver(post_save, sender=Host)
def sync_host_after_save(sender, instance, **kwargs):
    sync_host_to_config_item(instance)


@receiver(post_delete, sender=Host)
def sync_host_after_delete(sender, instance, **kwargs):
    delete_config_item_for_host(instance)


@receiver(post_save, sender=ConfigItem)
def sync_config_item_after_save(sender, instance, **kwargs):
    sync_config_item_to_host(instance)
    from ops.task_resources import sync_cmdb_task_resource

    sync_cmdb_task_resource(instance)


@receiver(post_save, sender=ResourceNode)
def sync_task_resource_group_after_save(sender, instance, **kwargs):
    from ops.models import TaskResourceGroup

    TaskResourceGroup.objects.filter(cmdb_node=instance).update(name=instance.name[:80])


@receiver(post_delete, sender=ConfigItem)
def sync_config_item_after_delete(sender, instance, **kwargs):
    delete_host_for_config_item(instance)
