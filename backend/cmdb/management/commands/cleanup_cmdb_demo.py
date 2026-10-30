from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from cmdb.models import (
    CISourceMapping,
    CISyncJob,
    ConfigItem,
    ResourceNode,
    ResourceRequest,
)


CMDB_LEDGER_CACHE_VERSION_KEY = 'cmdb:ledger:cache-version'
DEMO_DISABLED_MESSAGE = 'Demo 模式已下线，请保留真实同步来源数据。'


def _contains_demo_mode(value):
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key or '').strip().lower()
            if normalized_key == 'demo_mode' and item is True:
                return True
            if normalized_key == 'auth_mode' and str(item or '').strip().lower() == 'demo':
                return True
            if _contains_demo_mode(item):
                return True
    if isinstance(value, (list, tuple)):
        return any(_contains_demo_mode(item) for item in value)
    return False


def _collect_marker_values(value, keys):
    markers = set()
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key or '').strip().lower()
            if normalized_key in keys and item not in (None, '', [], {}):
                markers.add(str(item).strip())
            markers.update(_collect_marker_values(item, keys))
    elif isinstance(value, (list, tuple)):
        for item in value:
            markers.update(_collect_marker_values(item, keys))
    return {item for item in markers if item}


def _collect_cloud_account_ids(value):
    account_ids = set()
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key or '').strip().lower()
            if normalized_key in {'cloud_account_id', 'multicloud_account_id'} and item not in (None, '', [], {}):
                account_ids.add(str(item).strip())
            account_ids.update(_collect_cloud_account_ids(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            account_ids.update(_collect_cloud_account_ids(item))
    return {item for item in account_ids if item}


def _or_json_equals(field, values):
    query = Q()
    for value in values:
        query |= Q(**{field: value})
    return query


def _delete_queryset(queryset, *, dry_run):
    count = queryset.count()
    if dry_run or not count:
        return count
    queryset.delete()
    return count


class Command(BaseCommand):
    help = '清理 CMDB 和多云同步中心里的 Demo 数据，只保留真实同步来源。'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='只输出将清理的数量，不执行删除。')
        parser.add_argument(
            '--purge-unmapped',
            action='store_true',
            help='同时删除没有来源映射且没有 cmdb_source 的 CMDB 台账项、资源申请和资源树节点。',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        purge_unmapped = options['purge_unmapped']

        try:
            from multicloud.models import CloudCredential
        except ImportError:
            CloudCredential = None

        demo_credentials = CloudCredential.objects.none() if CloudCredential is None else CloudCredential.objects.filter(
            Q(demo_mode=True) | Q(auth_mode__iexact='demo')
        )
        credential_markers = set()
        environment_codes = set()
        valid_credential_ids = set()
        if CloudCredential is not None:
            valid_credential_ids = {str(item) for item in CloudCredential.objects.values_list('id', flat=True)}
            for credential in demo_credentials.prefetch_related('environments'):
                for value in (
                    credential.name,
                    credential.account_id,
                    credential.account_name,
                    credential.default_region,
                ):
                    if value:
                        credential_markers.add(str(value).strip())
                for environment in credential.environments.all():
                    if environment.code:
                        environment_codes.add(str(environment.code).strip())

        marker_keys = {
            'source_account',
            'account',
            'account_id',
            'account_name',
            'cloud_account',
            'cloud_account_name',
            'cloud_account_id',
        }
        demo_job_ids = []
        for job in CISyncJob.objects.all().only('id', 'name', 'source_type', 'config'):
            config = job.config or {}
            cloud_account_ids = _collect_cloud_account_ids(config)
            has_orphan_cloud_account = bool(cloud_account_ids) and not any(item in valid_credential_ids for item in cloud_account_ids)
            if _contains_demo_mode(config) or 'demo' in str(job.name or '').lower() or has_orphan_cloud_account:
                demo_job_ids.append(job.id)
                credential_markers.update(_collect_marker_values(config, marker_keys))

        credential_markers.discard('')
        environment_codes.discard('')

        demo_mapping_query = Q(source_unique_id__icontains='demo')
        if credential_markers:
            demo_mapping_query |= Q(source_account__in=credential_markers)
        demo_mapping_ids = list(CISourceMapping.objects.filter(demo_mapping_query).values_list('id', flat=True))

        ci_query = Q(attributes__demo_mode=True) | Q(attributes__auth_mode='demo')
        if demo_mapping_ids:
            ci_query |= Q(source_mappings__id__in=demo_mapping_ids)
        if demo_job_ids:
            ci_query |= Q(sync_records__job_id__in=demo_job_ids)
        multicloud_query = Q(attributes__cmdb_source='multicloud')
        marker_query = Q()
        if credential_markers:
            marker_query |= _or_json_equals('attributes__account_id', credential_markers)
            marker_query |= _or_json_equals('attributes__account_name', credential_markers)
            marker_query |= _or_json_equals('attributes__source_account', credential_markers)
        if environment_codes:
            marker_query |= _or_json_equals('attributes__cloud_env_code', environment_codes)
        if marker_query:
            ci_query |= multicloud_query & marker_query
        if purge_unmapped:
            ci_query |= (
                Q(source_mappings__isnull=True)
                & (Q(attributes__cmdb_source__isnull=True) | Q(attributes__cmdb_source=''))
            )

        demo_ci_ids = list(ConfigItem.objects.filter(ci_query).distinct().values_list('id', flat=True))
        stats = {
            'cmdb_config_items': len(demo_ci_ids),
            'cmdb_source_mappings': len(demo_mapping_ids),
            'cmdb_sync_jobs': len(demo_job_ids),
            'multicloud_credentials': demo_credentials.count(),
            'resource_requests': ResourceRequest.objects.count() if purge_unmapped else 0,
            'resource_nodes': ResourceNode.objects.count() if purge_unmapped else 0,
        }

        self.stdout.write(
            f'CMDB Demo cleanup {"dry-run" if dry_run else "delete"}: '
            + ', '.join(f'{key}={value}' for key, value in stats.items())
        )
        if dry_run:
            self.stdout.write(self.style.WARNING('dry-run only, nothing deleted.'))
            return

        with transaction.atomic():
            _delete_queryset(ConfigItem.objects.filter(id__in=demo_ci_ids), dry_run=False)
            _delete_queryset(CISourceMapping.objects.filter(id__in=demo_mapping_ids), dry_run=False)
            _delete_queryset(CISyncJob.objects.filter(id__in=demo_job_ids), dry_run=False)
            if CloudCredential is not None:
                _delete_queryset(demo_credentials, dry_run=False)
            if purge_unmapped:
                _delete_queryset(ResourceRequest.objects.all(), dry_run=False)
                _delete_queryset(ResourceNode.objects.all(), dry_run=False)

        try:
            cache.incr(CMDB_LEDGER_CACHE_VERSION_KEY)
        except ValueError:
            cache.set(CMDB_LEDGER_CACHE_VERSION_KEY, 1, None)

        self.stdout.write(self.style.SUCCESS(DEMO_DISABLED_MESSAGE))
