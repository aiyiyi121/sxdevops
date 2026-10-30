from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import io
import ipaddress
import json
import re
import subprocess
import sys
import uuid
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Avg, CharField, Count, F, Prefetch, Q
from django.db.models.functions import Cast
from django.http import HttpResponse
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from eventwall.mixins import EventWallModelViewSetMixin
from eventwall.models import EventRecord
from eventwall.services import build_resource, record_event
from .collectors import collect_items_for_sync_job, configured_collection_item_count
from .builtins import ensure_builtin_cmdb
from .costs import AliyunCostSyncError, sync_aliyun_monthly_costs
from .metrics import latest_metric_snapshots
from .models import (
    CIArchiveCandidate,
    CIChangeLog,
    CICompletionIssue,
    CIField,
    CIModelGroup,
    CIResourceMetricSnapshot,
    CIResourceAuthorization,
    CIRelation,
    CIRelationRule,
    CISourceMapping,
    CISyncJob,
    CISyncRecord,
    CITag,
    CIThresholdPolicy,
    CIType,
    ConfigItem,
    ConfigItemPassword,
    CostOptimizationProgress,
    CostOptimizationTask,
    CostRecord,
    IPAddress,
    IPSubnet,
    ResourceNode,
    ResourceRequest,
)
from .serializers import (
    CIArchiveCandidateSerializer,
    CIChangeLogSerializer,
    CICompletionIssueSerializer,
    CIFieldSerializer,
    CIModelGroupSerializer,
    CIResourceMetricSnapshotSerializer,
    CIResourceAuthorizationSerializer,
    CIRelationRuleSerializer,
    CIRelationSerializer,
    CISourceMappingSerializer,
    CISyncJobSerializer,
    CISyncRecordSerializer,
    CITagSerializer,
    CIThresholdPolicySerializer,
    CITypeSerializer,
    ConfigItemSerializer,
    ConfigItemPasswordRevealSerializer,
    ConfigItemPasswordSerializer,
    CostOptimizationTaskSerializer,
    CostRecordSerializer,
    IPAddressSerializer,
    IPSubnetSerializer,
    ResourceNodeSerializer,
    ResourceRequestSerializer,
    validate_config_item_attributes_by_metadata,
    validate_no_sensitive_plaintext,
)
from .passwords import ConfigItemPasswordDecryptionError, decrypt_config_item_password
from .provisioning import ALIYUN_RESOURCE_TYPE_MAP, build_provisioning_options, provision_resource_request, provider_label
from ops.models import Host
from rbac.permissions import RBACPermissionMixin, build_rbac_permission
from rbac.services import user_has_permissions
from .sync import (
    ensure_host_ci_type,
    is_placeholder_ci_type_name,
    normalize_ci_attributes,
    normalize_ci_type_name,
    resolve_config_item_type_meta,
)


SEVERITY_ORDER = {'danger': 3, 'warning': 2, 'info': 1}
TYPE_LABELS = {
    'reclaim': '资源回收',
    'schedule': '定时启停',
    'downsize': '规格缩容',
    'storage': '存储分层',
    'governance': '归属治理',
}
SEVERITY_LABELS = {
    'danger': '高优先',
    'warning': '中优先',
    'info': '治理项',
}

PHASE_ONE_REQUIRED_SYNC_TYPES = [
    'vsphere_vm',
    'aliyun_ecs',
    'aliyun_rds',
    'aliyun_ack',
    'aliyun_redis',
    'aliyun_mongodb',
    'aliyun_kafka',
    'aliyun_rocketmq',
    'aliyun_oss',
    'aliyun_disk',
    'aliyun_nas',
    'aliyun_clickhouse',
    'aliyun_hologres',
    'aliyun_maxcompute',
    'aliyun_dataworks',
    'aliyun_slb',
    'aliyun_nat_gateway',
    'aliyun_eip',
    'aliyun_elasticsearch',
    'huaweicloud_ecs',
    'huaweicloud_rds',
    'huaweicloud_redis',
    'huaweicloud_eip',
    'huaweicloud_obs',
    'third_party_import',
]
PHASE_ONE_IDC_HARDWARE_FIELDS = [
    'asset_sn',
    'vendor',
    'model',
    'serial_number',
    'cpu',
    'memory_gb',
]
PHASE_ONE_CLOUD_PROVIDERS = [
    {
        'key': 'vsphere',
        'label': 'vSphere',
        'source_types': ['vsphere_vm'],
        'keywords': ['vsphere', 'vmware'],
    },
    {
        'key': 'aliyun',
        'label': '阿里云',
        'source_types': ['aliyun_ecs'],
        'keywords': ['aliyun', 'alibaba', '阿里云'],
    },
    {
        'key': 'huaweicloud',
        'label': '华为云',
        'source_types': ['huaweicloud_ecs'],
        'keywords': ['huaweicloud', 'huawei', '华为云'],
    },
]
PHASE_ONE_ALIYUN_MIDDLEWARE_CODES = [
    'MYSQL',
    'POSTGRESQL',
    'K8S_CLUSTER',
    'REDIS',
    'MONGODB',
    'KAFKA',
    'ROCKETMQ',
    'ELASTICSEARCH',
    'OBJECT_STORAGE',
    'BLOCK_STORAGE',
    'FILE_STORAGE',
    'CLICKHOUSE',
    'HOLOGRES',
    'MAXCOMPUTE',
    'DATAWORKS',
    'LOAD_BALANCER',
    'NAT_GATEWAY',
    'ELASTIC_IP',
]
PHASE_ONE_THIRD_PARTY_PROVIDERS = [
    {'key': 'heweather', 'label': '和风天气', 'keywords': ['和风天气', 'heweather', 'qweather']},
    {'key': 'amap', 'label': '高德地图', 'keywords': ['高德地图', 'amap', '高德']},
]
PHASE_ONE_RESOURCE_METRIC_GROUPS = [
    {'key': 'cpu', 'label': 'CPU', 'metrics': ['cpu_usage']},
    {'key': 'memory', 'label': '内存', 'metrics': ['memory_usage']},
    {'key': 'disk', 'label': '磁盘', 'metrics': ['disk_usage', 'storage_usage']},
]
INTERNAL_PROVIDER_SUMMARY_CI_TYPE_CODES = {'VSPHERE_CAPACITY'}
INTERNAL_PROVIDER_SUMMARY_CI_TYPE_NAMES = {'vSphere资源统计'}
INTERNAL_PROVIDER_SUMMARY_SOURCE_PREFIXES = ('vsphere-summary:',)
IP_SCAN_WORKERS = 32


def _ip_sort_key(value):
    return int(ipaddress.ip_address(value))


def _usable_subnet_addresses(subnet):
    network = ipaddress.ip_network(subnet.cidr)
    return [str(address) for address in network.hosts()]


def _extract_ipv4_values(value):
    addresses = set()
    if isinstance(value, dict):
        for item in value.values():
            addresses.update(_extract_ipv4_values(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            addresses.update(_extract_ipv4_values(item))
    elif isinstance(value, str):
        for item in re.findall(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', value):
            try:
                parsed = ipaddress.ip_address(item)
            except ValueError:
                continue
            if parsed.version == 4:
                addresses.add(str(parsed))
    return addresses


def _cmdb_ip_index(network):
    index = defaultdict(list)
    for ci in ConfigItem.objects.select_related('ci_type').only(
        'id', 'name', 'status', 'attributes', 'ci_type__name'
    ):
        for address in _extract_ipv4_values(ci.attributes or {}):
            if ipaddress.ip_address(address) in network:
                index[address].append(ci)
    return index


def _config_item_is_stopped(ci):
    if ci.status in {'stopped', 'offline'}:
        return True
    attributes = ci.attributes or {}
    runtime_status = str(
        attributes.get('instance_status')
        or attributes.get('power_state')
        or attributes.get('runtime_status')
        or attributes.get('running_status')
        or '',
    ).strip().lower()
    return runtime_status in {'stopped', 'stop', 'inactive', 'shutoff', 'poweredoff', 'power_off', 'off'}


def _linked_ci_address_status(linked_cis):
    return 'offline' if all(_config_item_is_stopped(ci) for ci in linked_cis) else 'in_use'


def _probe_ip(address, timeout_ms=700):
    if sys.platform.startswith('win'):
        command = ['ping', '-n', '1', '-w', str(timeout_ms), address]
    else:
        command = ['ping', '-c', '1', '-W', str(max(1, timeout_ms // 1000)), address]
    try:
        return subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=max(2, timeout_ms / 1000 + 1),
            check=False,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _subnet_address_snapshot(subnet):
    network = ipaddress.ip_network(subnet.cidr)
    addresses = _usable_subnet_addresses(subnet)
    records = {row.address: row for row in subnet.addresses.select_related('ci').all()}
    cmdb_index = _cmdb_ip_index(network)
    excluded = {str(item) for item in (subnet.excluded_addresses or [])}
    rows = []
    counts = defaultdict(int)
    for address in addresses:
        record = records.get(address)
        linked_cis = cmdb_index.get(address, [])
        linked_names = [ci.name for ci in linked_cis]
        if record and record.status == 'reserved' and not linked_cis:
            status_value = 'reserved'
        elif linked_cis:
            status_value = _linked_ci_address_status(linked_cis)
        elif address in excluded:
            status_value = 'reserved'
        elif record:
            status_value = record.status
        else:
            status_value = 'available'
        reachability = record.reachability if record else 'unknown'
        rows.append({
            'id': record.id if record else None,
            'address': address,
            'status': status_value,
            'reachability': reachability,
            'ci_id': linked_cis[0].id if linked_cis else (record.ci_id if record else None),
            'ci_name': linked_names[0] if linked_names else (record.ci.name if record and record.ci else ''),
            'linked_ci_names': linked_names or (record.linked_ci_names if record else []),
            'note': record.note if record else '',
            'last_scanned_at': record.last_scanned_at if record else None,
        })
        counts[status_value] += 1
    return rows, {
        'total': len(addresses),
        'available': counts['available'],
        'in_use': counts['in_use'],
        'offline': counts['offline'],
        'reserved': counts['reserved'],
    }


def _scan_subnet(subnet, timeout_ms=700):
    network = ipaddress.ip_network(subnet.cidr)
    cmdb_index = _cmdb_ip_index(network)
    existing = {row.address: row for row in subnet.addresses.select_related('ci').all()}
    excluded = {str(item) for item in (subnet.excluded_addresses or [])}
    candidates = [address for address in _usable_subnet_addresses(subnet) if address not in excluded]
    reachability = {}
    with ThreadPoolExecutor(max_workers=min(IP_SCAN_WORKERS, max(1, len(candidates)))) as executor:
        future_map = {executor.submit(_probe_ip, address, timeout_ms): address for address in candidates}
        for future in as_completed(future_map):
            address = future_map[future]
            try:
                reachability[address] = future.result()
            except Exception:
                reachability[address] = False
    now = timezone.now()
    for address in _usable_subnet_addresses(subnet):
        linked_cis = cmdb_index.get(address, [])
        record = existing.get(address)
        if record and record.status == 'reserved' and not linked_cis:
            status_value = 'reserved'
        elif address in excluded:
            status_value = 'reserved'
        elif linked_cis:
            status_value = _linked_ci_address_status(linked_cis)
        else:
            status_value = 'in_use' if reachability.get(address, False) else 'available'
        if record is None:
            record = IPAddress(subnet=subnet, address=address, created_by='scanner')
        record.status = status_value
        record.reachability = 'reachable' if reachability.get(address, False) else 'unreachable'
        record.ci = linked_cis[0] if linked_cis else None
        record.linked_ci_names = [ci.name for ci in linked_cis]
        record.last_scanned_at = now
        record.save()
    subnet.last_scanned_at = now
    subnet.save(update_fields=['last_scanned_at', 'updated_at'])
    _, summary = _subnet_address_snapshot(subnet)
    summary['scanned_at'] = now
    return summary


def _current_month():
    return timezone.now().strftime('%Y-%m')


def _normalize_month(value):
    month = (value or '').strip()
    if not month:
        return _current_month()
    if not re.fullmatch(r'\d{4}-\d{2}', month):
        return _current_month()
    try:
        datetime.strptime(f'{month}-01', '%Y-%m-%d')
    except ValueError:
        return _current_month()
    return month


def _previous_months(limit=6, month=None):
    base = datetime.strptime(f"{_normalize_month(month)}-01", '%Y-%m-%d')
    months = []
    for _ in range(limit):
        months.append(base.strftime('%Y-%m'))
        base = (base.replace(day=1) - timezone.timedelta(days=1)).replace(day=1)
    months.reverse()
    return months


def _to_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _to_float(value):
    return float(value or 0)


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    return bool(value)


def _include_internal_provider_summaries(params):
    return _to_bool(
        params.get('include_internal_summaries')
        or params.get('include_internal_summary')
        or params.get('include_internal')
    )


def _internal_provider_summary_ci_ids():
    q = Q()
    for prefix in INTERNAL_PROVIDER_SUMMARY_SOURCE_PREFIXES:
        q |= Q(source_unique_id__startswith=prefix)
    if not q:
        return CISourceMapping.objects.none().values('ci_id')
    return CISourceMapping.objects.filter(q).values('ci_id')


def _exclude_internal_provider_summary_items(qs):
    q = (
        Q(ci_type__code__in=INTERNAL_PROVIDER_SUMMARY_CI_TYPE_CODES)
        | Q(ci_type__name__in=INTERNAL_PROVIDER_SUMMARY_CI_TYPE_NAMES)
    )
    return qs.exclude(q | Q(id__in=_internal_provider_summary_ci_ids()))


def _safe_percent(part, whole):
    if not whole:
        return 0.0
    return round(_to_float((part / whole) * Decimal('100')), 1)


def _normalize_search_text(value):
    return str(value or '').strip().lower()


def _flatten_attribute_pairs(value, prefix=''):
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f'{prefix}.{key}' if prefix else str(key)
            yield from _flatten_attribute_pairs(child, child_prefix)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_prefix = f'{prefix}[{index}]' if prefix else f'[{index}]'
            yield from _flatten_attribute_pairs(child, child_prefix)
    elif value not in (None, ''):
        yield prefix, str(value)


def _source_rows_for_ci(ci):
    mappings = getattr(ci, '_prefetched_objects_cache', {}).get('source_mappings')
    if mappings is None:
        mappings = ci.source_mappings.all()
    return [
        {
            'source_type': mapping.source_type,
            'source_account': mapping.source_account,
            'source_region': mapping.source_region,
            'source_unique_id': mapping.source_unique_id,
            'sync_status': mapping.sync_status,
            'last_seen_at': mapping.last_seen_at,
        }
        for mapping in (mappings or ())
    ]


def _source_label_for_ci(ci):
    sources = _source_rows_for_ci(ci)
    if sources:
        source = sources[0]
        return source['source_type'] or 'manual'
    attributes = ci.attributes or {}
    return attributes.get('source_type') or attributes.get('source') or 'manual'


def _phase_one_ci_text(ci):
    attributes = ci.attributes or {}
    parts = [
        getattr(ci, 'name', ''),
        getattr(getattr(ci, 'ci_type', None), 'name', ''),
        getattr(getattr(ci, 'ci_type', None), 'code', ''),
    ]
    for key, value in _flatten_attribute_pairs(attributes):
        parts.extend([key, value])
    for source in _source_rows_for_ci(ci):
        parts.extend([
            source.get('source_type'),
            source.get('source_account'),
            source.get('source_region'),
            source.get('source_unique_id'),
        ])
    return ' '.join(str(part) for part in parts if part not in (None, '')).lower()


def _phase_one_text_matches(text, keywords):
    return any(str(keyword).lower() in text for keyword in keywords)


def _phase_one_has_all_attributes(ci, field_codes):
    attributes = ci.attributes or {}
    return all(attributes.get(field) not in (None, '') for field in field_codes)


def _build_phase_one_waterline(metric_items):
    groups = []
    for definition in PHASE_ONE_RESOURCE_METRIC_GROUPS:
        rows = [item for item in metric_items if item.get('metric') in definition['metrics']]
        values = [
            max(0, min(100, round(_to_float(item.get('usage_percent')))))
            for item in rows
            if item.get('usage_percent') is not None
        ]
        risk_rows = [item for item in rows if item.get('status') in {'warning', 'critical', 'exceeded'}]
        request_open = any(
            item.get('linked_request') and item['linked_request'].get('status') in {'pending', 'approved'}
            for item in risk_rows
        )
        groups.append({
            'key': definition['key'],
            'label': definition['label'],
            'metrics': definition['metrics'],
            'count': len(values),
            'average': round(sum(values) / len(values)) if values else 0,
            'peak': max(values) if values else 0,
            'risk_count': len(risk_rows),
            'request_open': request_open,
            'ready': bool(values),
            'status': 'requesting' if request_open else 'risk' if risk_rows else 'normal' if values else 'missing',
        })
    return {
        'ready': all(item['ready'] for item in groups),
        'partial': any(item['ready'] for item in groups),
        'request_needed': any(item['risk_count'] for item in groups),
        'groups': groups,
    }


def _build_phase_one_coverage(scoped_items, scoped_ci_ids, metric_items):
    sync_counts = {
        row['source_type']: row['count']
        for row in CISyncJob.objects.filter(source_type__in=PHASE_ONE_REQUIRED_SYNC_TYPES)
        .values('source_type')
        .annotate(count=Count('id'))
    }
    sync_present = [source_type for source_type in PHASE_ONE_REQUIRED_SYNC_TYPES if sync_counts.get(source_type)]
    sync = {
        'present': len(sync_present),
        'total': len(PHASE_ONE_REQUIRED_SYNC_TYPES),
        'ready': len(sync_present) == len(PHASE_ONE_REQUIRED_SYNC_TYPES),
        'missing': [source_type for source_type in PHASE_ONE_REQUIRED_SYNC_TYPES if source_type not in sync_present],
        'source_types': [
            {
                'source_type': source_type,
                'ready': source_type in sync_present,
                'count': sync_counts.get(source_type, 0),
            }
            for source_type in PHASE_ONE_REQUIRED_SYNC_TYPES
        ],
    }

    cloud_items = list(
        scoped_items.filter(
            Q(ci_type__code='CLOUD_SERVER')
            | Q(ci_type__code='VIRTUAL_MACHINE')
            | Q(ci_type__name__icontains='云主机')
            | Q(ci_type__name__icontains='ECS')
            | Q(ci_type__name__icontains='虚拟机')
        )
        .select_related('ci_type')
        .prefetch_related('source_mappings')
    )
    cloud_provider_rows = []
    for provider in PHASE_ONE_CLOUD_PROVIDERS:
        keywords = list(provider['keywords']) + list(provider['source_types'])
        matched = [ci for ci in cloud_items if _phase_one_text_matches(_phase_one_ci_text(ci), keywords)]
        cloud_provider_rows.append({
            'key': provider['key'],
            'label': provider['label'],
            'source_types': provider['source_types'],
            'count': len(matched),
            'ready': bool(matched),
        })
    cloud_ready_count = sum(1 for item in cloud_provider_rows if item['ready'])
    cloud = {
        'count': len(cloud_items),
        'present': cloud_ready_count,
        'total': len(cloud_provider_rows),
        'providers': cloud_provider_rows,
        'ready': cloud_ready_count == len(cloud_provider_rows),
        'partial': cloud_ready_count > 0,
    }

    middleware_items = list(
        scoped_items.filter(ci_type__code__in=PHASE_ONE_ALIYUN_MIDDLEWARE_CODES)
        .select_related('ci_type')
        .prefetch_related('source_mappings')
    )
    aliyun_middleware_items = [
        ci for ci in middleware_items
        if _phase_one_text_matches(_phase_one_ci_text(ci), ['aliyun', 'alibaba', '阿里云'])
    ]
    aliyun_middleware_codes = {
        (ci.ci_type.code or '').upper()
        for ci in aliyun_middleware_items
        if (ci.ci_type.code or '').upper() in PHASE_ONE_ALIYUN_MIDDLEWARE_CODES
    }
    aliyun_middleware = {
        'count': len(aliyun_middleware_items),
        'present': len(aliyun_middleware_codes),
        'total': len(PHASE_ONE_ALIYUN_MIDDLEWARE_CODES),
        'model_codes': [
            {'code': code, 'ready': code in aliyun_middleware_codes}
            for code in PHASE_ONE_ALIYUN_MIDDLEWARE_CODES
        ],
        'ready': len(aliyun_middleware_codes) == len(PHASE_ONE_ALIYUN_MIDDLEWARE_CODES),
        'partial': bool(aliyun_middleware_items),
    }

    idc_items = list(
        scoped_items.filter(
            Q(ci_type__code__in=['IDC_SERVER', 'PHYSICAL_SERVER'])
            | Q(ci_type__name__icontains='物理机')
            | Q(ci_type__name__icontains='机房服务器')
        )
        .select_related('ci_type')
    )
    idc_hardware_ready_count = sum(
        1
        for ci in idc_items
        if _phase_one_has_all_attributes(ci, PHASE_ONE_IDC_HARDWARE_FIELDS)
    )
    idc = {
        'count': len(idc_items),
        'hardware_ready': idc_hardware_ready_count,
        'ready': bool(idc_items) and idc_hardware_ready_count == len(idc_items),
        'partial': bool(idc_items),
    }

    third_party_items = list(
        scoped_items.filter(ci_type__code='THIRD_PARTY_SERVICE')
        .select_related('ci_type')
        .prefetch_related('source_mappings')
    )
    third_party_provider_rows = []
    for provider in PHASE_ONE_THIRD_PARTY_PROVIDERS:
        matched = [ci for ci in third_party_items if _phase_one_text_matches(_phase_one_ci_text(ci), provider['keywords'])]
        third_party_provider_rows.append({
            'key': provider['key'],
            'label': provider['label'],
            'count': len(matched),
            'ready': bool(matched),
        })
    third_party_ready_count = sum(1 for item in third_party_provider_rows if item['ready'])
    third_party = {
        'count': len(third_party_items),
        'present': third_party_ready_count,
        'total': len(third_party_provider_rows),
        'providers': third_party_provider_rows,
        'ready': third_party_ready_count == len(third_party_provider_rows),
        'partial': third_party_ready_count > 0,
    }

    waterline = _build_phase_one_waterline(metric_items)
    sections = [waterline, sync, idc, cloud, aliyun_middleware, third_party]
    return {
        'ready': all(item.get('ready') for item in sections),
        'waterline': waterline,
        'sync': sync,
        'idc': idc,
        'cloud': cloud,
        'aliyun_middleware': aliyun_middleware,
        'third_party': third_party,
    }


def _user_cmdb_group_codes(user):
    if not getattr(user, 'is_authenticated', False):
        return []
    try:
        return list(user.rbac_groups.values_list('code', flat=True))
    except Exception:
        return []


def _ci_authorization_bypassed(user):
    return getattr(user, 'is_superuser', False) or user_has_permissions(user, ['cmdb.authorization.manage'])


def _user_can_view_platform_change_logs(user):
    return getattr(user, 'is_superuser', False) or any(
        user_has_permissions(user, [code])
        for code in ['cmdb.model.manage', 'cmdb.sync.manage', 'cmdb.ci.manage', 'cmdb.authorization.manage']
    )


def _ci_authorization_principal_q(user):
    principals = Q(principal_type='user', principal=getattr(user, 'username', ''))
    group_codes = _user_cmdb_group_codes(user)
    if group_codes:
        principals |= Q(principal_type='group', principal__in=group_codes)
    return principals


def _ci_authorization_policies_for_user(user, permission='view'):
    if not getattr(user, 'is_authenticated', False):
        return []
    if _ci_authorization_bypassed(user):
        return []

    permission_values = ['manage'] if permission == 'manage' else ['view', 'manage']
    return list(
        CIResourceAuthorization.objects.filter(
            _ci_authorization_principal_q(user),
            permission__in=permission_values,
            is_active=True,
        ).select_related('ci_type')
    )

def _user_has_any_ci_authorization_policy(user):
    if not getattr(user, 'is_authenticated', False) or _ci_authorization_bypassed(user):
        return False
    return CIResourceAuthorization.objects.filter(
        _ci_authorization_principal_q(user),
        is_active=True,
    ).exists()


def _ci_scope_q_for_user(user, permission='view'):
    if not getattr(user, 'is_authenticated', False):
        return Q(pk__in=[])
    if _ci_authorization_bypassed(user):
        return None

    policies = _ci_authorization_policies_for_user(user, permission=permission)
    if not policies:
        return Q(pk__in=[]) if _user_has_any_ci_authorization_policy(user) else None

    scope_q = Q(pk__in=[])
    for policy in policies:
        item_q = Q()
        if policy.business_line:
            item_q &= Q(business_line=policy.business_line)
        if policy.environment:
            item_q &= Q(environment=policy.environment)
        if policy.ci_type_id:
            item_q &= Q(ci_type_id=policy.ci_type_id)
        scope_q |= item_q
    return scope_q


def _resource_matches_authorization_policy(policy, *, ci_type_id=None, business_line='', environment=''):
    if policy.business_line and (business_line or '') != policy.business_line:
        return False
    if policy.environment and (environment or '') != policy.environment:
        return False
    if policy.ci_type_id and ci_type_id and int(ci_type_id) != policy.ci_type_id:
        return False
    if policy.ci_type_id and not ci_type_id:
        return False
    return True


def _user_can_manage_ci_resource(user, *, ci_type_id=None, business_line='', environment=''):
    if not getattr(user, 'is_authenticated', False):
        return False
    if _ci_authorization_bypassed(user):
        return True
    policies = _ci_authorization_policies_for_user(user, permission='manage')
    if not policies:
        return not _user_has_any_ci_authorization_policy(user)
    return any(
        _resource_matches_authorization_policy(
            policy,
            ci_type_id=ci_type_id,
            business_line=business_line,
            environment=environment,
        )
        for policy in policies
    )


def _ensure_user_can_manage_ci_resource(user, *, ci_type_id=None, business_line='', environment=''):
    if not _user_can_manage_ci_resource(
        user,
        ci_type_id=ci_type_id,
        business_line=business_line,
        environment=environment,
    ):
        raise PermissionDenied('无权管理该资源范围')


def _ensure_user_can_manage_config_item(user, config_item):
    _ensure_user_can_manage_ci_resource(
        user,
        ci_type_id=config_item.ci_type_id,
        business_line=config_item.business_line,
        environment=config_item.environment,
    )


def _apply_ci_authorization_scope(qs, user, permission='view'):
    scope_q = _ci_scope_q_for_user(user, permission=permission)
    if scope_q is None:
        return qs
    return qs.filter(scope_q)


def _sync_record_queryset_for_user(user, *, status=None, permission='view', include_global=None):
    qs = CISyncRecord.objects.select_related('job', 'ci', 'ci__ci_type').all()
    if status:
        qs = qs.filter(status=status)

    scoped_ci_ids = _apply_ci_authorization_scope(
        ConfigItem.objects.all(),
        user,
        permission=permission,
    ).values('id')
    scope_q = Q(ci_id__in=scoped_ci_ids)
    if include_global is None:
        include_global = user_has_permissions(user, ['cmdb.sync.view'])
    if include_global:
        scope_q |= Q(ci__isnull=True)
    return qs.filter(scope_q)


def _sync_governance_record_queryset_for_user(user, *, include_global=False):
    if user is None:
        qs = CISyncRecord.objects.select_related('job', 'ci', 'ci__ci_type').all()
    else:
        qs = _sync_record_queryset_for_user(user, include_global=include_global)
    return qs.filter(Q(status='failed') | Q(after___sync_relations__failed__gt=0)).exclude(retry_status__in=['success', 'ignored'])


def _normalize_business_line(value):
    return value or '未归类'


def _normalize_provider(value):
    normalized = str(value or '').strip()
    if normalized in {'\u672a\u6807\u8bb0', '\u672a\u6807\u6ce8'}:
        return 'manual'
    return normalized or 'manual'


def _provider_for_attributes(attributes):
    return (
        (attributes or {}).get('billing_provider')
        or (attributes or {}).get('cloud_provider')
        or (attributes or {}).get('provider')
        or ''
    )[:50]


def _cost_rows_for_month(month, ci_queryset=None):
    scoped_ci_qs = ci_queryset if ci_queryset is not None else ConfigItem.objects.all()
    scoped_ci_ids = scoped_ci_qs.values('id')
    if month == _current_month():
        existing_rows = list(
            CostRecord.objects.filter(month=month, ci_id__in=scoped_ci_ids)
            .select_related('ci__ci_type')
            .prefetch_related('ci__source_mappings')
            .order_by('-computed_at', '-id')
        )
        row_map = {}
        for row in existing_rows:
            if row.ci_id not in row_map:
                row_map[row.ci_id] = {
                    'ci': row.ci,
                    'amount': row.amount or Decimal('0'),
                    'provider': row.provider or _provider_for_attributes(row.ci.attributes or {}),
                }
            else:
                row_map[row.ci_id]['amount'] += row.amount or Decimal('0')
                if not row_map[row.ci_id]['provider'] and row.provider:
                    row_map[row.ci_id]['provider'] = row.provider

        for ci in scoped_ci_qs.select_related('ci_type').prefetch_related('source_mappings'):
            if ci.id in row_map:
                continue
            amount = _to_decimal((ci.attributes or {}).get('monthly_cost')) or Decimal('0')
            if amount <= 0:
                continue
            row_map[ci.id] = {
                'ci': ci,
                'amount': amount,
                'provider': _provider_for_attributes(ci.attributes or {}),
            }

        return list(row_map.values())

    row_map = {}
    for record in CostRecord.objects.filter(month=month, ci_id__in=scoped_ci_ids).select_related('ci__ci_type').prefetch_related('ci__source_mappings'):
        if record.ci_id not in row_map:
            row_map[record.ci_id] = {
                'ci': record.ci,
                'amount': record.amount or Decimal('0'),
                'provider': record.provider or _provider_for_attributes(record.ci.attributes or {}),
            }
        else:
            row_map[record.ci_id]['amount'] += record.amount or Decimal('0')
    return sorted(row_map.values(), key=lambda item: (-item['amount'], item['ci'].name))


def _month_cost_map(month, ci_queryset=None):
    return {
        row['ci'].id: row['amount']
        for row in _cost_rows_for_month(month, ci_queryset=ci_queryset)
    }


def _cost_source_account(ci):
    attributes = ci.attributes or {}
    mappings = sorted(
        (
            mapping for mapping in ci.source_mappings.all()
            if mapping.source_account
        ),
        key=lambda mapping: (
            str(mapping.source_type or '').lower().startswith(('aliyun_', 'tencent_', 'aws_', 'azure_', 'huaweicloud_')),
            mapping.last_seen_at.timestamp() if mapping.last_seen_at else float('-inf'),
            mapping.updated_at.timestamp() if mapping.updated_at else float('-inf'),
            mapping.id,
        ),
        reverse=True,
    )
    # A cloud synchronization mapping is the authoritative account assignment.
    if mappings:
        return mappings[0].source_account

    account = (
        attributes.get('source_account')
        or attributes.get('cloud_account')
        or attributes.get('account_name')
        or attributes.get('account')
        or attributes.get('account_id')
    )
    if account:
        return str(account)
    return '未标注账号'


def _cost_source_region(ci):
    attributes = ci.attributes or {}
    region = attributes.get('source_region') or attributes.get('region') or attributes.get('region_id')
    if region:
        return str(region)

    for mapping in ci.source_mappings.all():
        if mapping.source_region:
            return mapping.source_region
    return ''


def _cost_amount_for_ci(ci, month_costs):
    amount = month_costs.get(ci.id)
    if amount is not None:
        return amount
    return Decimal('0')


def _average_resource_usage_by_ci(ci_ids):
    """Return recent CPU and memory averages from collected waterline snapshots."""
    if not ci_ids:
        return {}

    cutoff = timezone.now() - timedelta(days=14)
    snapshots = CIResourceMetricSnapshot.objects.filter(
        ci_id__in=ci_ids,
        metric__in=['cpu_usage', 'memory_usage'],
        usage_percent__isnull=False,
        collected_at__gte=cutoff,
    ).order_by().values('ci_id', 'metric').annotate(average_usage=Avg('usage_percent'))
    averages = defaultdict(dict)
    for snapshot in snapshots:
        key = 'cpu' if snapshot['metric'] == 'cpu_usage' else 'memory'
        averages[snapshot['ci_id']][key] = _to_decimal(snapshot['average_usage']).quantize(Decimal('0.01'))
    return dict(averages)


def _format_usage_percent(value):
    if value is None:
        return '暂无采集数据'
    return f'{_to_float(value):.1f}%'


def _add_candidate(candidates, *, candidate_type, severity, ratio, monthly_cost, title, detail, action, evidence):
    if ratio <= 0:
        return
    potential_saving = (monthly_cost * ratio).quantize(Decimal('0.01'))
    optimized_cost = max(monthly_cost - potential_saving, Decimal('0'))
    candidates.append({
        'type': candidate_type,
        'type_label': TYPE_LABELS[candidate_type],
        'severity': severity,
        'severity_label': SEVERITY_LABELS[severity],
        'title': title,
        'detail': detail,
        'action': action,
        'evidence': evidence,
        'potential_saving': potential_saving,
        'optimized_monthly_cost': optimized_cost,
        'saving_rate': round(_to_float(ratio * Decimal('100')), 1),
    })


def _best_suggestion_for_ci(ci, monthly_cost, resource_usage=None):
    attributes = ci.attributes or {}
    cpu = _to_decimal(attributes.get('cpu')) or Decimal('0')
    memory_gb = _to_decimal(attributes.get('memory_gb')) or Decimal('0')
    resource_usage = resource_usage or {}
    avg_cpu_usage = resource_usage.get('cpu')
    avg_memory_usage = resource_usage.get('memory')
    usage_source = '近 14 天采集均值'
    if avg_cpu_usage is None:
        avg_cpu_usage = _to_decimal(attributes.get('avg_cpu_usage'))
    if avg_memory_usage is None:
        avg_memory_usage = _to_decimal(attributes.get('avg_memory_usage'))
    if not resource_usage:
        usage_source = '资产维护值'
    storage_gb = _to_decimal(attributes.get('storage_gb') or attributes.get('disk_gb')) or Decimal('0')
    storage_utilization = _to_decimal(attributes.get('storage_utilization') or attributes.get('storage_usage_pct') or attributes.get('disk_usage_pct'))
    always_on = _to_bool(attributes.get('always_on'))
    schedule_exempt = _to_bool(attributes.get('schedule_exempt'))
    offline_days = int(_to_decimal(attributes.get('offline_days')) or 0)
    candidates = []

    if ci.status in {'offline', 'decommissioned'}:
        _add_candidate(
            candidates,
            candidate_type='reclaim',
            severity='danger',
            ratio=Decimal('1.00'),
            monthly_cost=monthly_cost,
            title=f'回收下线资源：{ci.name}',
            detail='资源已经离线或下线，但仍在持续计费，适合优先释放实例、磁盘和公网能力。',
            action='确认业务已迁移后直接回收实例及其挂载资源，避免继续产生整月账单。',
            evidence=f'当前状态为 {ci.status}，已离线 {offline_days or 0} 天。',
        )

    if ci.status == 'idle' or (ci.environment in {'dev', 'test'} and monthly_cost >= Decimal('200') and (avg_cpu_usage or Decimal('0')) <= Decimal('10')):
        ratio = Decimal('0.70') if ci.status == 'idle' else Decimal('0.60')
        _add_candidate(
            candidates,
            candidate_type='reclaim',
            severity='warning',
            ratio=ratio,
            monthly_cost=monthly_cost,
            title=f'回收空闲资源：{ci.name}',
            detail='资源长时间处于空闲状态，继续保留完整规格会持续吞噬预算。',
            action='如仍需保留镜像或数据，先做快照后释放主机；否则直接回收。',
            evidence=f'环境 {ci.environment}，{usage_source} CPU {_format_usage_percent(avg_cpu_usage)}。',
        )

    if ci.environment in {'dev', 'test'} and monthly_cost >= Decimal('300') and not schedule_exempt and (always_on or (avg_cpu_usage or Decimal('0')) <= Decimal('25')):
        ratio = Decimal('0.55') if always_on else Decimal('0.40')
        severity = 'danger' if monthly_cost >= Decimal('800') else 'warning'
        _add_candidate(
            candidates,
            candidate_type='schedule',
            severity=severity,
            ratio=ratio,
            monthly_cost=monthly_cost,
            title=f'为非生产资源启用定时启停：{ci.name}',
            detail='测试与开发资源夜间和周末通常负载很低，适合通过自动关停快速降本。',
            action='建议设置工作日 08:00-20:00 运行窗口，夜间与周末自动关机。',
            evidence=f'环境 {ci.environment}，{usage_source} CPU {_format_usage_percent(avg_cpu_usage)}，当前保持 24x7 运行。',
        )

    if monthly_cost >= Decimal('1000') and (cpu >= Decimal('8') or memory_gb >= Decimal('16')) and (avg_cpu_usage is None or avg_cpu_usage <= Decimal('35')) and (avg_memory_usage is None or avg_memory_usage <= Decimal('55')):
        ratio = Decimal('0.25') if ci.environment == 'prod' else Decimal('0.35')
        severity = 'danger' if monthly_cost >= Decimal('1800') else 'warning'
        _add_candidate(
            candidates,
            candidate_type='downsize',
            severity=severity,
            ratio=ratio,
            monthly_cost=monthly_cost,
            title=f'缩容高成本资源：{ci.name}',
            detail='实例规格明显高于日常负载，适合降配或切换到更低成本的实例族。',
            action='根据近两周峰值使用率回收 25%~35% 资源规格，并保留弹性扩容余量。',
            evidence=(
                f'当前规格 {cpu}C/{memory_gb}G，{usage_source} CPU '
                f'{_format_usage_percent(avg_cpu_usage)}，内存 {_format_usage_percent(avg_memory_usage)}。'
            ),
        )

    if storage_gb >= Decimal('500') and monthly_cost >= Decimal('400') and storage_utilization is not None and storage_utilization <= Decimal('55'):
        ratio = Decimal('0.25') if storage_utilization <= Decimal('35') else Decimal('0.18')
        _add_candidate(
            candidates,
            candidate_type='storage',
            severity='warning',
            ratio=ratio,
            monthly_cost=monthly_cost,
            title=f'优化存储分层：{ci.name}',
            detail='数据量大但利用率偏低，适合冷热分层、压缩或归档到低频存储。',
            action='将低频访问数据迁移到低频或归档层，只保留最近 30 天热数据。',
            evidence=f'存储容量 {storage_gb}GB，当前利用率 {storage_utilization}% 。',
        )

    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            item['potential_saving'],
            SEVERITY_ORDER.get(item['severity'], 0),
        ),
    )


def _serialize_suggestion(item):
    payload = dict(item)
    payload['monthly_cost'] = _to_float(item['monthly_cost'])
    payload['potential_saving'] = _to_float(item['potential_saving'])
    payload['optimized_monthly_cost'] = _to_float(item['optimized_monthly_cost'])
    return payload


def _build_optimization(month, ci_queryset=None):
    scoped_ci_qs = ci_queryset if ci_queryset is not None else ConfigItem.objects.all()
    month_costs = _month_cost_map(month, ci_queryset=scoped_ci_qs)
    ci_rows = list(scoped_ci_qs.select_related('ci_type').prefetch_related('source_mappings'))
    usage_by_ci = _average_resource_usage_by_ci([ci.id for ci in ci_rows])

    suggestions = []
    total_monthly_cost = Decimal('0')
    for ci in ci_rows:
        monthly_cost = _cost_amount_for_ci(ci, month_costs)
        if monthly_cost <= 0:
            continue
        total_monthly_cost += monthly_cost
        suggestion = _best_suggestion_for_ci(ci, monthly_cost, usage_by_ci.get(ci.id))
        if not suggestion:
            continue
        suggestions.append({
            'ci_id': ci.id,
            'ci_name': ci.name,
            'ci_type_id': ci.ci_type_id,
            'ci_type': ci.ci_type.name,
            'source_account': _cost_source_account(ci),
            'environment': ci.environment,
            'business_line': _normalize_business_line(ci.business_line),
            'admin_user': ci.admin_user or '待认领',
            'monthly_cost': monthly_cost,
            **suggestion,
        })

    suggestions.sort(
        key=lambda item: (
            item['potential_saving'],
            SEVERITY_ORDER.get(item['severity'], 0),
            item['monthly_cost'],
        ),
        reverse=True,
    )

    total_potential_saving = sum((item['potential_saving'] for item in suggestions), Decimal('0'))
    optimized_monthly_cost = max(total_monthly_cost - total_potential_saving, Decimal('0'))
    annualized_saving = total_potential_saving * Decimal('12')

    by_type_map = defaultdict(lambda: {'count': 0, 'total_saving': Decimal('0')})
    by_severity_map = defaultdict(lambda: {'count': 0, 'total_saving': Decimal('0')})
    by_business_map = defaultdict(lambda: {'count': 0, 'total_saving': Decimal('0')})
    for item in suggestions:
        by_type_map[item['type']]['count'] += 1
        by_type_map[item['type']]['total_saving'] += item['potential_saving']

        by_severity_map[item['severity']]['count'] += 1
        by_severity_map[item['severity']]['total_saving'] += item['potential_saving']

        by_business_map[item['business_line']]['count'] += 1
        by_business_map[item['business_line']]['total_saving'] += item['potential_saving']

    by_type = [
        {
            'type': key,
            'label': TYPE_LABELS.get(key, key),
            'count': value['count'],
            'total_saving': _to_float(value['total_saving']),
        }
        for key, value in by_type_map.items()
    ]
    by_type.sort(key=lambda item: item['total_saving'], reverse=True)

    by_severity = [
        {
            'severity': key,
            'label': SEVERITY_LABELS.get(key, key),
            'count': value['count'],
            'total_saving': _to_float(value['total_saving']),
        }
        for key, value in by_severity_map.items()
    ]
    by_severity.sort(key=lambda item: SEVERITY_ORDER.get(item['severity'], 0), reverse=True)

    by_business = [
        {
            'business_line': key,
            'count': value['count'],
            'total_saving': _to_float(value['total_saving']),
        }
        for key, value in by_business_map.items()
    ]
    by_business.sort(key=lambda item: item['total_saving'], reverse=True)

    serialized_suggestions = [_serialize_suggestion(item) for item in suggestions[:12]]
    suggestion_tasks = {
        (task.ci_id, task.suggestion_type): task
        for task in CostOptimizationTask.objects.filter(
            ci_id__in=[item['ci_id'] for item in serialized_suggestions],
            month=month,
        ).only('id', 'ci_id', 'suggestion_type', 'status', 'owner', 'claimed_at', 'updated_at')
    }
    for item in serialized_suggestions:
        task = suggestion_tasks.get((item['ci_id'], item['type']))
        item['handling'] = {
            'task_id': task.id if task else None,
            'status': task.status if task else 'unclaimed',
            'owner': task.owner if task else '',
            'claimed_at': task.claimed_at if task else None,
            'updated_at': task.updated_at if task else None,
        }
    by_cloud_account_map = defaultdict(
        lambda: {
            'count': 0,
            'by_type': defaultdict(lambda: {'count': 0}),
        }
    )
    for item in serialized_suggestions:
        account_row = by_cloud_account_map[item['source_account']]
        account_row['count'] += 1
        account_row['by_type'][item['ci_type_id']]['count'] += 1

    by_cloud_account = [
        {
            'source_account': source_account,
            'count': value['count'],
            'by_type': [
                {'type_id': type_id, 'count': type_value['count']}
                for type_id, type_value in value['by_type'].items()
            ],
        }
        for source_account, value in by_cloud_account_map.items()
    ]
    for account in by_cloud_account:
        account['by_type'].sort(key=lambda item: item['type_id'])
    by_cloud_account.sort(key=lambda item: (-item['count'], item['source_account']))

    quick_wins = serialized_suggestions[:5]

    return {
        'month': month,
        'total_monthly_cost': _to_float(total_monthly_cost),
        'suggestions': serialized_suggestions,
        'quick_wins': quick_wins,
        'total_potential_saving': _to_float(total_potential_saving),
        'optimized_monthly_cost': _to_float(optimized_monthly_cost),
        'annualized_saving': _to_float(annualized_saving),
        'saving_rate': _safe_percent(total_potential_saving, total_monthly_cost),
        'suggestion_count': len(suggestions),
        'affected_resource_count': len(suggestions),
        'by_type': by_type,
        'by_severity': by_severity,
        'by_business': by_business,
        'by_cloud_account': by_cloud_account,
    }


def _build_cost_report(month, ci_queryset=None, source_account='', business_line='', environment=''):
    scoped_ci_qs = ci_queryset if ci_queryset is not None else ConfigItem.objects.all()
    source_account = str(source_account or '').strip()
    business_line = str(business_line or '').strip()
    environment = str(environment or '').strip()
    if business_line:
        scoped_ci_qs = scoped_ci_qs.filter(
            business_line='' if business_line == '__unassigned__' else business_line,
        )
    if environment:
        scoped_ci_qs = scoped_ci_qs.filter(
            environment='' if environment == '__unassigned__' else environment,
        )
    if source_account:
        matching_ci_ids = [
            ci.id
            for ci in scoped_ci_qs.prefetch_related('source_mappings')
            if _cost_source_account(ci) == source_account
        ]
        scoped_ci_qs = scoped_ci_qs.filter(id__in=matching_ci_ids)
    rows = _cost_rows_for_month(month, ci_queryset=scoped_ci_qs)
    total = sum((row['amount'] for row in rows), Decimal('0'))

    by_business_map = defaultdict(lambda: {'total_cost': Decimal('0'), 'ci_ids': set()})
    by_environment_map = defaultdict(lambda: {'total_cost': Decimal('0'), 'ci_ids': set()})
    by_type_map = defaultdict(lambda: {'total_cost': Decimal('0'), 'ci_ids': set()})
    by_provider_map = defaultdict(lambda: {'total_cost': Decimal('0'), 'ci_ids': set()})
    by_cloud_account_map = defaultdict(lambda: {
        'total_cost': Decimal('0'),
        'ci_ids': set(),
        'by_type': defaultdict(lambda: {'total_cost': Decimal('0'), 'ci_ids': set()}),
    })

    for row in rows:
        ci = row['ci']
        amount = row['amount']
        business_line = _normalize_business_line(ci.business_line)
        environment = ci.environment
        type_name = ci.ci_type.name
        provider = _normalize_provider(row['provider'])
        source_account = _cost_source_account(ci)

        by_business_map[business_line]['total_cost'] += amount
        by_business_map[business_line]['ci_ids'].add(ci.id)

        by_environment_map[environment]['total_cost'] += amount
        by_environment_map[environment]['ci_ids'].add(ci.id)

        by_type_map[type_name]['total_cost'] += amount
        by_type_map[type_name]['ci_ids'].add(ci.id)

        by_provider_map[provider]['total_cost'] += amount
        by_provider_map[provider]['ci_ids'].add(ci.id)

        account_row = by_cloud_account_map[source_account]
        account_row['total_cost'] += amount
        account_row['ci_ids'].add(ci.id)
        account_type_row = account_row['by_type'][(ci.ci_type_id, type_name)]
        account_type_row['total_cost'] += amount
        account_type_row['ci_ids'].add(ci.id)

    by_business = [
        {
            'business_line': key,
            'total_cost': _to_float(value['total_cost']),
            'count': len(value['ci_ids']),
        }
        for key, value in by_business_map.items()
    ]
    by_business.sort(key=lambda item: (-item['total_cost'], item['business_line']))

    by_environment = [
        {
            'environment': key,
            'total_cost': _to_float(value['total_cost']),
            'count': len(value['ci_ids']),
        }
        for key, value in by_environment_map.items()
    ]
    by_environment.sort(key=lambda item: (-item['total_cost'], item['environment']))

    by_type = [
        {
            'type_name': key,
            'total_cost': _to_float(value['total_cost']),
            'count': len(value['ci_ids']),
        }
        for key, value in by_type_map.items()
    ]
    by_type.sort(key=lambda item: (-item['total_cost'], item['type_name']))

    by_provider = [
        {
            'provider': key,
            'total_cost': _to_float(value['total_cost']),
            'count': len(value['ci_ids']),
        }
        for key, value in by_provider_map.items()
    ]
    by_provider.sort(key=lambda item: (-item['total_cost'], item['provider']))

    by_cloud_account = []
    for source_account, value in by_cloud_account_map.items():
        types = [
            {
                'type_id': type_id,
                'type_name': type_name,
                'total_cost': _to_float(type_value['total_cost']),
                'count': len(type_value['ci_ids']),
            }
            for (type_id, type_name), type_value in value['by_type'].items()
        ]
        types.sort(key=lambda item: (-item['total_cost'], item['type_name']))
        by_cloud_account.append({
            'source_account': source_account,
            'total_cost': _to_float(value['total_cost']),
            'count': len(value['ci_ids']),
            'by_type': types,
        })
    by_cloud_account.sort(key=lambda item: (-item['total_cost'], item['source_account']))

    top_cost_items = [
        {
            'ci_id': row['ci'].id,
            'name': row['ci'].name,
            'business_line': _normalize_business_line(row['ci'].business_line),
            'environment': row['ci'].environment,
            'type_name': row['ci'].ci_type.name,
            'monthly_cost': _to_float(row['amount']),
            'provider': _normalize_provider(row['provider']),
        }
        for row in sorted(rows, key=lambda item: (-item['amount'], item['ci'].name))[:10]
    ]

    optimization = _build_optimization(month, ci_queryset=scoped_ci_qs)
    cost_trend = []
    for period in _previous_months(6, month):
        period_total = sum((row['amount'] for row in _cost_rows_for_month(period, ci_queryset=scoped_ci_qs)), Decimal('0'))
        item = {'period': period, 'total': _to_float(period_total)}
        if period == month:
            item['projected_total'] = max(item['total'] - optimization['total_potential_saving'], 0)
            item['projected_saving'] = optimization['total_potential_saving']
        cost_trend.append(item)

    non_prod_cost_total = sum(
        (Decimal(str(item['total_cost'])) for item in by_environment if item['environment'] in {'dev', 'test'}),
        Decimal('0'),
    )
    avg_cost_per_resource = (total / len(rows)) if rows else Decimal('0')
    top_business = by_business[0] if by_business else {'business_line': '-', 'total_cost': 0}
    top_provider = by_provider[0] if by_provider else {'provider': '-', 'total_cost': 0}

    return {
        'month': month,
        'total_monthly_cost': _to_float(total),
        'optimized_monthly_cost': optimization['optimized_monthly_cost'],
        'total_potential_saving': optimization['total_potential_saving'],
        'annualized_saving': optimization['annualized_saving'],
        'saving_rate': optimization['saving_rate'],
        'by_business': by_business,
        'by_environment': by_environment,
        'by_type': by_type,
        'by_provider': by_provider,
        'by_cloud_account': by_cloud_account,
        'top_cost_items': top_cost_items,
        'cost_trend': cost_trend,
        'non_prod_cost_total': _to_float(non_prod_cost_total),
        'non_prod_cost_ratio': _safe_percent(non_prod_cost_total, total),
        'avg_cost_per_resource': _to_float(avg_cost_per_resource),
        'top_business_line': top_business['business_line'],
        'top_business_cost': top_business['total_cost'],
        'top_provider': top_provider['provider'],
        'top_provider_cost': top_provider['total_cost'],
        'optimization_preview': {
            'suggestion_count': optimization['suggestion_count'],
            'affected_resource_count': optimization['affected_resource_count'],
            'total_potential_saving': optimization['total_potential_saving'],
            'optimized_monthly_cost': optimization['optimized_monthly_cost'],
            'annualized_saving': optimization['annualized_saving'],
            'saving_rate': optimization['saving_rate'],
            'by_type': optimization['by_type'],
        },
        'recommendations_preview': optimization['quick_wins'],
    }


def _cost_item_payload(row):
    ci = row['ci']
    return {
        'ci_id': ci.id,
        'name': ci.name,
        'business_line': _normalize_business_line(ci.business_line),
        'environment': ci.environment,
        'type_id': ci.ci_type_id,
        'type_name': ci.ci_type.name,
        'source_account': _cost_source_account(ci),
        'monthly_cost': _to_float(row['amount']),
        'provider': _normalize_provider(row['provider']),
    }


def _positive_int(value, default, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, maximum))


def _config_item_snapshot(ci):
    if not ci:
        return {}
    return {
        'id': ci.id,
        'name': ci.name,
        'ci_type': ci.ci_type_id,
        'ci_type_name': ci.ci_type.name if ci.ci_type_id else '',
        'business_line': ci.business_line,
        'environment': ci.environment,
        'admin_user': ci.admin_user,
        'status': ci.status,
        'tags': [{'id': tag.id, 'name': tag.name, 'category': tag.category} for tag in ci.tags.all()],
        'attributes': normalize_ci_attributes(_strip_resource_waterline_attributes(ci.attributes or {})),
    }


def _config_item_merge_summary(target, sources):
    return {
        'target': {
            'id': target.id,
            'name': target.name,
            'ci_type': target.ci_type_id,
            'ci_type_name': normalize_ci_type_name(target.ci_type.name if target.ci_type_id else ''),
        },
        'sources': [
            {
                'id': source.id,
                'name': source.name,
                'ci_type': source.ci_type_id,
                'ci_type_name': normalize_ci_type_name(source.ci_type.name if source.ci_type_id else ''),
            }
            for source in sources
        ],
    }


def _move_relation_to_merge_target(relation, target, source_ids):
    old_source_id = relation.source_id
    old_target_id = relation.target_id
    new_source_id = target.id if old_source_id in source_ids else old_source_id
    new_target_id = target.id if old_target_id in source_ids else old_target_id
    if new_source_id == new_target_id:
        relation.delete()
        return 'deleted'
    duplicate = CIRelation.objects.filter(
        source_id=new_source_id,
        target_id=new_target_id,
        relation_type=relation.relation_type,
    ).exclude(pk=relation.pk).first()
    if duplicate:
        relation.delete()
        return 'deduplicated'
    relation.source_id = new_source_id
    relation.target_id = new_target_id
    relation.save(update_fields=['source', 'target'])
    return 'updated'


def _merge_config_item_attributes(target, sources):
    target_attributes = dict(target.attributes or {})
    for source in sources:
        for key, value in (source.attributes or {}).items():
            if key not in target_attributes or target_attributes.get(key) in (None, '', [], {}):
                target_attributes[key] = value
    return normalize_ci_attributes(target_attributes)


def _mark_source_config_item_merged(source, target, reason, operator):
    source_attributes = dict(source.attributes or {})
    unique_fields = list(source.ci_type.fields.filter(unique=True, is_active=True))
    original_attributes = dict(source_attributes)
    target_attributes = target.attributes or {}
    for field in unique_fields:
        if field.code in source_attributes and field.code in target_attributes:
            if _normalize_unique_field_duplicate_value(source_attributes.get(field.code)) == _normalize_unique_field_duplicate_value(target_attributes.get(field.code)):
                source_attributes.pop(field.code, None)
    source_attributes['merged_into_ci_id'] = target.id
    source_attributes['merged_into_ci_name'] = target.name
    source_attributes['merged_at'] = timezone.now().isoformat()
    if operator:
        source_attributes['merged_by'] = operator
    if reason:
        source_attributes['merge_reason'] = reason
    source_attributes['merged_original_attributes'] = original_attributes
    source.status = 'offline'
    source.attributes = normalize_ci_attributes(source_attributes)
    source.save(update_fields=['status', 'attributes', 'updated_at'])


def _dict_diff(before, after):
    diff = {}
    keys = set((before or {}).keys()) | set((after or {}).keys())
    for key in keys:
        old = (before or {}).get(key)
        new = (after or {}).get(key)
        if old != new:
            diff[key] = {'before': old, 'after': new}
    return diff


CMDB_LEDGER_CACHE_VERSION_KEY = 'cmdb:ledger:cache-version'
CMDB_DASHBOARD_CACHE_TTL = 20
CMDB_ISLAND_ANALYSIS_CACHE_TTL = 30
CMDB_LEDGER_LIST_CACHE_TTL = 20
CMDB_LEDGER_TREE_CACHE_TTL = 60
CMDB_MODEL_REPOSITORY_CACHE_TTL = 60
CMDB_VIEWS_SUMMARY_CACHE_TTL = 60
CMDB_COLLECTION_SUMMARY_CACHE_TTL = 20


def _cmdb_ledger_cache_version():
    version = cache.get(CMDB_LEDGER_CACHE_VERSION_KEY)
    if version is None:
        version = 1
        cache.set(CMDB_LEDGER_CACHE_VERSION_KEY, version, None)
    return version


def _bump_cmdb_ledger_cache_version():
    try:
        cache.incr(CMDB_LEDGER_CACHE_VERSION_KEY)
    except ValueError:
        cache.set(CMDB_LEDGER_CACHE_VERSION_KEY, int(timezone.now().timestamp()), None)


def _cmdb_ledger_request_cache_key(request, action):
    query = {
        key: request.query_params.getlist(key)
        for key in sorted(request.query_params.keys())
    }
    payload = {
        'action': action,
        'user_id': getattr(request.user, 'id', None),
        'version': _cmdb_ledger_cache_version(),
        'query': query,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')
    ).hexdigest()
    return f'cmdb:ledger:{action}:{digest}'


def _record_ci_change(ci, action, before, after, *, operator='', source='manual'):
    diff = _dict_diff(before, after)
    if action == 'update' and not diff:
        return None
    change = CIChangeLog.objects.create(
        ci=ci,
        action=action,
        before=before or {},
        after=after or {},
        diff=diff,
        operator=operator or '',
        source=source or 'manual',
    )
    _bump_cmdb_ledger_cache_version()
    return change


def _resource_request_snapshot(obj):
    if not obj:
        return {}
    return {
        'id': obj.id,
        'name': obj.title,
        'ci_type_name': '资源申请',
        'title': obj.title,
        'applicant': obj.applicant,
        'approver': obj.approver,
        'resource_type': obj.resource_type,
        'specification': obj.specification,
        'business_line': obj.business_line,
        'environment': obj.environment,
        'priority': obj.priority,
        'quantity': obj.quantity,
        'specs': obj.specs or {},
        'status': obj.status,
        'reason': obj.reason,
        'approval_comment': obj.approval_comment,
        'fulfillment_note': obj.fulfillment_note,
        'approved_at': obj.approved_at.isoformat() if obj.approved_at else None,
        'completed_at': obj.completed_at.isoformat() if obj.completed_at else None,
    }


def _record_request_change(obj, action, before, after, *, operator=''):
    return _record_ci_change(
        None,
        action,
        before,
        after,
        operator=operator,
        source='resource_request',
    )


def _relation_snapshot(relation):
    if not relation:
        return {}
    source = relation.source
    target = relation.target
    return {
        'id': relation.id,
        'source_id': relation.source_id,
        'source_name': source.name if source else '',
        'source_type': source.ci_type_id if source else None,
        'source_type_name': source.ci_type.name if source and source.ci_type_id else '',
        'target_id': relation.target_id,
        'target_name': target.name if target else '',
        'target_type': target.ci_type_id if target else None,
        'target_type_name': target.ci_type.name if target and target.ci_type_id else '',
        'relation_type': relation.relation_type,
        'description': relation.description,
        'evidence_source': relation.evidence_source,
        'evidence_source_display': relation.get_evidence_source_display(),
        'confidence': relation.confidence,
        'evidence': relation.evidence or {},
    }


def _resource_authorization_snapshot(authorization):
    if not authorization:
        return {}
    ci_type = authorization.ci_type
    return {
        'id': authorization.id,
        'name': authorization.name,
        'principal_type': authorization.principal_type,
        'principal': authorization.principal,
        'permission': authorization.permission,
        'business_line': authorization.business_line,
        'environment': authorization.environment,
        'ci_type': authorization.ci_type_id,
        'ci_type_name': ci_type.name if ci_type else '',
        'is_active': authorization.is_active,
        'description': authorization.description,
        'created_by': authorization.created_by,
    }


def _source_mapping_snapshot(mapping):
    if not mapping:
        return {}
    ci = mapping.ci
    return {
        'id': mapping.id,
        'ci': mapping.ci_id,
        'ci_name': ci.name if ci else '',
        'ci_type': ci.ci_type_id if ci else None,
        'ci_type_name': ci.ci_type.name if ci and ci.ci_type_id else '',
        'source_type': mapping.source_type,
        'source_account': mapping.source_account,
        'source_region': mapping.source_region,
        'source_unique_id': mapping.source_unique_id,
        'last_seen_at': mapping.last_seen_at.isoformat() if mapping.last_seen_at else None,
        'sync_status': mapping.sync_status,
        'raw_payload': mapping.raw_payload or {},
    }


def _model_group_snapshot(group):
    if not group:
        return {}
    return {
        'id': group.id,
        'name': group.name,
        'code': group.code,
        'description': group.description,
        'sort_order': group.sort_order,
        'is_builtin': group.is_builtin,
        'is_active': group.is_active,
    }


def _ci_type_snapshot(ci_type):
    if not ci_type:
        return {}
    group = ci_type.group
    return {
        'id': ci_type.id,
        'name': ci_type.name,
        'code': ci_type.code,
        'group': ci_type.group_id,
        'group_name': group.name if group else '',
        'icon': ci_type.icon,
        'color': ci_type.color,
        'description': ci_type.description,
        'is_builtin': ci_type.is_builtin,
        'is_active': ci_type.is_active,
    }


def _ci_field_snapshot(field):
    if not field:
        return {}
    ci_type = field.ci_type
    return {
        'id': field.id,
        'ci_type': field.ci_type_id,
        'ci_type_name': ci_type.name if ci_type else '',
        'name': field.name,
        'code': field.code,
        'field_type': field.field_type,
        'field_group': field.field_group,
        'required': field.required,
        'unique': field.unique,
        'default': field.default,
        'options': field.options,
        'validation': field.validation,
        'sync_mode': field.sync_mode,
        'is_builtin': field.is_builtin,
        'is_display': field.is_display,
        'is_searchable': field.is_searchable,
        'is_sensitive': field.is_sensitive,
        'is_active': field.is_active,
        'sort_order': field.sort_order,
    }


def _relation_rule_snapshot(rule):
    if not rule:
        return {}
    source_type = rule.source_type
    target_type = rule.target_type
    return {
        'id': rule.id,
        'source_type': rule.source_type_id,
        'source_type_name': source_type.name if source_type else '',
        'target_type': rule.target_type_id,
        'target_type_name': target_type.name if target_type else '',
        'relation_type': rule.relation_type,
        'direction': rule.direction,
        'required': rule.required,
        'multiple': rule.multiple,
        'description': rule.description,
        'is_active': rule.is_active,
    }


def _threshold_policy_snapshot(policy):
    if not policy:
        return {}
    resource_type = policy.resource_type
    return {
        'id': policy.id,
        'resource_type': policy.resource_type_id,
        'resource_type_name': resource_type.name if resource_type else '',
        'metric': policy.metric,
        'normal_threshold': str(policy.normal_threshold),
        'warning_threshold': str(policy.warning_threshold),
        'critical_threshold': str(policy.critical_threshold),
        'exceeded_threshold': str(policy.exceeded_threshold),
        'enabled': policy.enabled,
    }


def _resource_metric_snapshot(metric):
    if not metric:
        return {}
    ci = metric.ci
    return {
        'id': metric.id,
        'ci': metric.ci_id,
        'ci_name': ci.name if ci else '',
        'ci_type': ci.ci_type_id if ci else None,
        'ci_type_name': ci.ci_type.name if ci and ci.ci_type_id else '',
        'metric': metric.metric,
        'value': str(metric.value),
        'unit': metric.unit,
        'usage_percent': str(metric.usage_percent) if metric.usage_percent is not None else None,
        'collected_at': metric.collected_at.isoformat() if metric.collected_at else None,
        'source': metric.source,
    }


DEFAULT_WATERLINE_THRESHOLDS = {
    'warning_threshold': 70,
    'critical_threshold': 85,
    'exceeded_threshold': 95,
}


def _capacity_policy_lookup():
    policies = CIThresholdPolicy.objects.filter(enabled=True).select_related('resource_type')
    return {
        (policy.resource_type_id, policy.metric): policy
        for policy in policies
    }


def _capacity_thresholds_for_metric(policy_lookup, ci_type_id, metric):
    policy = policy_lookup.get((ci_type_id, metric)) or policy_lookup.get((None, metric))
    if not policy:
        return {
            'policy_id': None,
            'policy_scope': 'default',
            **DEFAULT_WATERLINE_THRESHOLDS,
        }
    return {
        'policy_id': policy.id,
        'policy_scope': 'model' if policy.resource_type_id else 'global',
        'warning_threshold': _to_float(policy.warning_threshold),
        'critical_threshold': _to_float(policy.critical_threshold),
        'exceeded_threshold': _to_float(policy.exceeded_threshold),
    }


def _capacity_waterline_status(usage_percent, thresholds):
    if usage_percent >= thresholds['exceeded_threshold']:
        return 'exceeded'
    if usage_percent >= thresholds['critical_threshold']:
        return 'critical'
    if usage_percent >= thresholds['warning_threshold']:
        return 'warning'
    return 'normal'


def _capacity_request_snapshot(request_obj):
    if not request_obj:
        return None
    return {
        'id': request_obj.id,
        'title': request_obj.title,
        'status': request_obj.status,
        'status_display': request_obj.get_status_display(),
        'priority': request_obj.priority,
        'applicant': request_obj.applicant,
        'created_at': request_obj.created_at,
        'updated_at': request_obj.updated_at,
        'completed_at': request_obj.completed_at,
    }


def _capacity_request_lookup(scoped_ci_ids):
    scoped_id_set = {int(item) for item in scoped_ci_ids}
    if not scoped_id_set:
        return {}
    status_rank = {
        'pending': 3,
        'approved': 3,
        'completed': 1,
    }
    lookup = {}
    requests = (
        ResourceRequest.objects
        .exclude(status='rejected')
        .only('id', 'title', 'status', 'priority', 'applicant', 'created_at', 'updated_at', 'completed_at', 'specs')
        .order_by('-created_at', '-id')
    )
    for request_obj in requests:
        capacity_source = (request_obj.specs or {}).get('capacity_source') or {}
        if not isinstance(capacity_source, dict):
            continue
        try:
            ci_id = int(capacity_source.get('ci_id') or 0)
        except (TypeError, ValueError):
            continue
        metric = (capacity_source.get('metric') or '').strip()
        if not ci_id or ci_id not in scoped_id_set or not metric:
            continue
        key = (ci_id, metric)
        current = lookup.get(key)
        candidate = {
            'rank': status_rank.get(request_obj.status, 0),
            'created_at': request_obj.created_at,
            'request': _capacity_request_snapshot(request_obj),
        }
        if (
            not current
            or (candidate['rank'], candidate['created_at']) > (current['rank'], current['created_at'])
        ):
            lookup[key] = candidate
    return {key: value['request'] for key, value in lookup.items()}


def _sync_job_snapshot(job):
    if not job:
        return {}
    return {
        'id': job.id,
        'name': job.name,
        'source_type': job.source_type,
        'status': job.status,
        'mode': job.mode,
        'dry_run': job.dry_run,
        'config': job.config or {},
        'created_by': job.created_by,
    }


def _resolve_ci_type_from_payload(payload):
    type_code = (payload.get('ci_type_code') or payload.get('model_code') or payload.get('type_code') or '').strip()
    type_name = normalize_ci_type_name(
        payload.get('ci_type_name')
        or payload.get('type_name')
        or payload.get('resource_type')
        or payload.get('ci_type')
        or '未分类资源'
    )
    if type_code.upper() == 'IDC_SERVER':
        return ensure_host_ci_type()
    if type_code:
        ci_type = CIType.objects.filter(code=type_code).first()
        if ci_type:
            return ci_type
    ci_type, _ = CIType.objects.get_or_create(
        name=type_name,
        defaults={
            'code': type_code,
            'icon': payload.get('icon') or 'Box',
            'color': payload.get('color') or '#64748b',
            'description': payload.get('description') or '',
        },
    )
    if type_code and not ci_type.code:
        ci_type.code = type_code
        ci_type.save(update_fields=['code', 'updated_at'])
    return ci_type


def _source_values(payload, default_source_type='manual'):
    attributes = payload.get('attributes') or {}
    source_type = (
        payload.get('source_type')
        or attributes.get('source_type')
        or attributes.get('source')
        or default_source_type
        or 'manual'
    )
    source_account = payload.get('source_account') or attributes.get('source_account') or attributes.get('account') or ''
    source_region = payload.get('source_region') or attributes.get('source_region') or attributes.get('region') or ''
    source_unique_id = (
        payload.get('source_unique_id')
        or payload.get('external_id')
        or payload.get('instance_id')
        or attributes.get('source_unique_id')
        or attributes.get('external_id')
        or attributes.get('instance_id')
        or payload.get('name')
    )
    return {
        'source_type': str(source_type or 'manual')[:50],
        'source_account': str(source_account or '')[:100],
        'source_region': str(source_region or '')[:100],
        'source_unique_id': str(source_unique_id or '')[:200],
    }


def _find_config_item_for_source(source):
    if not source['source_unique_id']:
        return None
    mapping = CISourceMapping.objects.select_related('ci').filter(**source).first()
    return mapping.ci if mapping else None


def _find_missing_source_mapping_for_rekey(ci_type, source, name):
    """Find the single missing mapping that can safely adopt a changed source ID."""
    if not name or not source['source_type']:
        return None
    mappings = list(
        CISourceMapping.objects.select_related('ci').filter(
            ci__ci_type=ci_type,
            ci__name=name,
            source_type=source['source_type'],
            source_account=source['source_account'],
            source_region=source['source_region'],
            sync_status='missing',
        ).order_by('-last_seen_at', '-id')[:2]
    )
    return mappings[0] if len(mappings) == 1 else None


def _restore_source_archive_candidates(config_item, source_type, note):
    for candidate in config_item.archive_candidates.filter(
        source_type=source_type,
        status__in=['pending', 'confirmed', 'archived'],
    ):
        candidate.status = 'restored'
        candidate.confirmed_at = timezone.now()
        candidate.reason = f'{candidate.reason}；{note}'[:200] if candidate.reason else note[:200]
        candidate.save(update_fields=['status', 'confirmed_at', 'reason', 'updated_at'])


def _sync_name_with_suffix(base_name, suffix_number, max_length=100):
    suffix = f'-{suffix_number}'
    base = str(base_name or '').strip() or 'resource'
    return f'{base[:max_length - len(suffix)]}{suffix}'[:max_length]


def _sync_source_allows_duplicate_display_name(source):
    source_type = str((source or {}).get('source_type') or '').lower()
    return source_type.startswith(('aliyun_', 'huaweicloud_'))


def _sync_name_matches_base(candidate, base_name):
    candidate = str(candidate or '')
    base_name = str(base_name or '')
    if not candidate or not base_name:
        return False
    if candidate == base_name:
        return True
    if not candidate.startswith(f'{base_name}-'):
        return False
    suffix = candidate[len(base_name) + 1:]
    return suffix.isdigit() and int(suffix or 0) >= 2


def _sync_name_taken_by_other_ci(ci_type, candidate, config_item=None):
    qs = ConfigItem.objects.filter(ci_type=ci_type, name=candidate)
    if config_item is not None:
        qs = qs.exclude(pk=config_item.pk)
    return qs.exists()


def _sync_name_reserved_by_other_source(context, ci_type, candidate, source):
    if context is None:
        return False
    source_key = _sync_source_identity_key(source)
    reserved_names = context.setdefault('reserved_names', {})
    reserved_source = reserved_names.get((ci_type.id, candidate))
    if reserved_source and reserved_source != source_key:
        return True
    seen_names = context.setdefault('names', {})
    seen_source = (seen_names.get((ci_type.id, candidate)) or {}).get('source') or {}
    return bool(seen_source and _sync_source_identity_key(seen_source) != source_key)


def _reserve_sync_display_name(ci_type, source, data, context=None, config_item=None):
    base_name = str(data.get('name') or source.get('source_unique_id') or 'resource').strip()[:100]
    if not base_name:
        return
    source_key = _sync_source_identity_key(source)
    candidates = []
    if config_item is not None and _sync_name_matches_base(config_item.name, base_name):
        candidates.append(config_item.name)
    candidates.append(base_name)

    for candidate in candidates:
        if not candidate:
            continue
        candidate = candidate[:100]
        if _sync_name_taken_by_other_ci(ci_type, candidate, config_item=config_item):
            continue
        if _sync_name_reserved_by_other_source(context, ci_type, candidate, source):
            continue
        data['name'] = candidate
        if context is not None:
            context.setdefault('reserved_names', {})[(ci_type.id, candidate)] = source_key
        return

    for suffix_number in range(2, 10000):
        candidate = _sync_name_with_suffix(base_name, suffix_number)
        if _sync_name_taken_by_other_ci(ci_type, candidate, config_item=config_item):
            continue
        if _sync_name_reserved_by_other_source(context, ci_type, candidate, source):
            continue
        data['name'] = candidate
        if context is not None:
            context.setdefault('reserved_names', {})[(ci_type.id, candidate)] = source_key
        return


def _name_peer_has_different_source_scope_mapping(name_peer, source):
    if name_peer is None:
        return False
    return bool(_source_mapping_scope_conflicts(name_peer, source))


def _sync_display_name_needs_disambiguation(ci_type, source, data, context=None, config_item=None):
    base_name = data.get('name') or ''
    if not base_name:
        return False
    if config_item is not None and _sync_name_matches_base(config_item.name, base_name) and config_item.name != base_name:
        return True
    source_key = _sync_source_identity_key(source)
    if context is not None:
        previous = context.setdefault('names', {}).get((ci_type.id, base_name))
        previous_source = (previous or {}).get('source') or {}
        if previous_source and _sync_source_identity_key(previous_source) != source_key:
            return True
    peers = (
        ConfigItem.objects
        .filter(ci_type=ci_type, name=base_name)
        .prefetch_related('source_mappings')
        .order_by('id')[:10]
    )
    for peer in peers:
        if config_item is not None and peer.id == config_item.id:
            continue
        if _name_peer_has_different_source_scope_mapping(peer, source):
            return True
    return False


SYNC_RELATION_HINT_KEYS = ('relations', 'relationships', 'relation_hints')
SYNC_RELATION_IP_KEYS = ('private_ip', 'ip_address', 'ip', 'public_ip')
SYNC_RELATION_ENDPOINT_KEYS = ('endpoint', 'domain', 'vip', 'host', 'hostname')


def _sync_relation_hint_rows(payload):
    rows = []
    if not isinstance(payload, dict):
        return rows
    containers = [payload]
    attributes = payload.get('attributes')
    if isinstance(attributes, dict):
        containers.append(attributes)
    for container in containers:
        for key in SYNC_RELATION_HINT_KEYS:
            value = container.get(key)
            if value in (None, '', [], {}):
                continue
            if isinstance(value, list):
                rows.extend(item for item in value if isinstance(item, dict))
            elif isinstance(value, dict):
                rows.append(value)
    return rows


def _sync_relation_peer_payload(hint, role):
    keys = [role]
    if role == 'target':
        keys.extend(['peer', 'to', 'dst', 'destination'])
    else:
        keys.extend(['peer', 'from', 'src'])
    for key in keys:
        value = hint.get(key)
        if isinstance(value, dict):
            return value
        if value not in (None, ''):
            text = str(value)
            return {'ci_id': value} if text.isdigit() else {'source_unique_id': value}
    return {}


def _sync_relation_peer_source(hint, role, current_source):
    peer = _sync_relation_peer_payload(hint, role)
    source_unique_id = (
        hint.get(f'{role}_source_unique_id')
        or hint.get(f'{role}_external_id')
        or hint.get(f'{role}_instance_id')
        or peer.get('source_unique_id')
        or peer.get('external_id')
        or peer.get('instance_id')
        or peer.get('id')
        or (peer.get('ci_id') if not str(peer.get('ci_id') or '').isdigit() else '')
    )
    source_type = (
        hint.get(f'{role}_source_type')
        or peer.get('source_type')
        or peer.get('source')
        or current_source.get('source_type')
        or ''
    )
    return {
        'source_type': str(source_type or '')[:50],
        'source_account': str(hint.get(f'{role}_source_account') or peer.get('source_account') or current_source.get('source_account') or '')[:100],
        'source_region': str(hint.get(f'{role}_source_region') or peer.get('source_region') or current_source.get('source_region') or '')[:100],
        'source_unique_id': str(source_unique_id or '')[:200],
    }


def _sync_relation_peer_type(hint, peer, role):
    type_code = (hint.get(f'{role}_ci_type_code') or peer.get('ci_type_code') or peer.get('model_code') or '').strip()
    type_name = normalize_ci_type_name(
        hint.get(f'{role}_ci_type_name')
        or hint.get(f'{role}_type_name')
        or peer.get('ci_type_name')
        or peer.get('type_name')
        or peer.get('resource_type')
        or ''
    )
    if type_code:
        ci_type = CIType.objects.filter(code=type_code).first()
        if ci_type:
            return ci_type
    if type_name:
        return CIType.objects.filter(name=type_name).first()
    return None


def _sync_relation_peer_value(hint, peer, role, *keys):
    attributes = peer.get('attributes') if isinstance(peer.get('attributes'), dict) else {}
    for key in keys:
        candidates = [
            hint.get(f'{role}_{key}'),
            hint.get(f'peer_{key}'),
            hint.get(key),
            peer.get(key),
            attributes.get(key),
        ]
        for value in candidates:
            if value not in (None, '', [], {}):
                return str(value).strip()
    return ''


def _sync_relation_scoped_queryset(hint, peer, role):
    qs = ConfigItem.objects.select_related('ci_type').prefetch_related('tags').all()
    ci_type = _sync_relation_peer_type(hint, peer, role)
    if ci_type:
        qs = qs.filter(ci_type=ci_type)
    business_line = _sync_relation_peer_value(hint, peer, role, 'business_line', 'biz')
    if business_line:
        qs = qs.filter(business_line=business_line)
    environment = _sync_relation_peer_value(hint, peer, role, 'environment', 'env')
    if environment:
        qs = qs.filter(environment=environment)
    status_value = _sync_relation_peer_value(hint, peer, role, 'status')
    if status_value:
        qs = qs.filter(status=status_value)
    return qs


def _single_relation_peer(qs):
    rows = list(qs.order_by('id')[:2])
    return rows[0] if len(rows) == 1 else None


def _sync_relation_find_peer_by_attribute(hint, peer, role):
    scoped = _sync_relation_scoped_queryset(hint, peer, role)
    attr_groups = [
        ('ip', SYNC_RELATION_IP_KEYS),
        ('endpoint', SYNC_RELATION_ENDPOINT_KEYS),
        ('instance_id', ('instance_id', 'external_id', 'resource_id')),
    ]
    for match_name, keys in attr_groups:
        value = _sync_relation_peer_value(hint, peer, role, *keys)
        if not value:
            continue
        attr_filter = Q()
        for key in keys:
            attr_filter |= Q(**{f'attributes__{key}': value})
        ci = _single_relation_peer(scoped.filter(attr_filter).distinct())
        if ci:
            return ci, match_name
    return None, ''


def _sync_relation_peer_tag_payload(hint, peer, role):
    for key in (f'{role}_tags', f'{role}_tag_items', f'{role}_cloud_tags', 'peer_tags', 'tags', 'tag_items', 'cloud_tags'):
        value = hint.get(key)
        if value not in (None, '', [], {}):
            return value
    for key in ('tags', 'tag_items', 'cloud_tags'):
        value = peer.get(key)
        if value not in (None, '', [], {}):
            return value
    attributes = peer.get('attributes') if isinstance(peer.get('attributes'), dict) else {}
    for key in ('tags', 'tag_items', 'cloud_tags'):
        value = attributes.get(key)
        if value not in (None, '', [], {}):
            return value
    return []


def _sync_relation_find_peer_by_tags(hint, peer, role):
    tag_value = _sync_relation_peer_tag_payload(hint, peer, role)
    tag_ids, tag_specs = _normalize_payload_tag_specs({'tags': tag_value})
    if not tag_ids and not tag_specs:
        return None, ''
    qs = _sync_relation_scoped_queryset(hint, peer, role)
    for tag_id in tag_ids:
        qs = qs.filter(tags__id=tag_id)
    for spec in tag_specs:
        tag_filter = Q(tags__name=spec['name'])
        if spec.get('category'):
            tag_filter &= Q(tags__category=spec['category'])
        qs = qs.filter(tag_filter)
    ci = _single_relation_peer(qs.distinct())
    return (ci, 'tags') if ci else (None, '')


def _sync_relation_find_peer(hint, role, current_source):
    peer = _sync_relation_peer_payload(hint, role)
    ci_id = hint.get(f'{role}_ci_id') or peer.get('ci_id')
    if ci_id not in (None, '') and str(ci_id).isdigit():
        ci = ConfigItem.objects.select_related('ci_type').filter(id=ci_id).first()
        if ci:
            return ci, 'ci_id'

    source = _sync_relation_peer_source(hint, role, current_source)
    if source['source_unique_id'] and source['source_type']:
        ci = _find_config_item_for_source(source)
        if ci:
            return ci, 'source_mapping'

    ci, matched_by = _sync_relation_find_peer_by_attribute(hint, peer, role)
    if ci:
        return ci, matched_by

    ci, matched_by = _sync_relation_find_peer_by_tags(hint, peer, role)
    if ci:
        return ci, matched_by

    name = (
        hint.get(f'{role}_name')
        or hint.get(f'{role}_ci_name')
        or peer.get('name')
        or peer.get('ci_name')
        or peer.get('resource_name')
    )
    if name:
        qs = ConfigItem.objects.select_related('ci_type').filter(name=name)
        ci_type = _sync_relation_peer_type(hint, peer, role)
        if ci_type:
            qs = qs.filter(ci_type=ci_type)
        ci = qs.order_by('id').first()
        if ci:
            return ci, 'name'
    return None, ''


def _sync_relations_from_payload(config_item, payload, *, job=None, source=None, operator='', dry_run=False):
    hints = _sync_relation_hint_rows(payload)
    if not hints:
        return {'total': 0, 'created': 0, 'skipped': 0, 'failed': 0, 'relations': [], 'errors': []}
    source = source or _source_values(payload, default_source_type=(job.source_type if job else 'manual'))
    summary = {'total': len(hints), 'created': 0, 'skipped': 0, 'failed': 0, 'relations': [], 'errors': []}
    for index, hint in enumerate(hints, start=1):
        relation_type = str(hint.get('relation_type') or hint.get('type') or hint.get('relation') or 'depends_on').strip()
        direction = str(hint.get('direction') or 'outgoing').strip().lower()
        peer_role = 'source' if direction == 'incoming' else 'target'
        peer, matched_by = _sync_relation_find_peer(hint, peer_role, source)
        if peer is None:
            summary['failed'] += 1
            summary['errors'].append({
                'index': index,
                'relation_type': relation_type,
                'direction': direction,
                'peer_role': peer_role,
                'reason': 'peer_not_found',
                'hint': hint,
            })
            continue
        relation_source = peer if direction == 'incoming' else config_item
        relation_target = config_item if direction == 'incoming' else peer
        if CIRelation.objects.filter(source=relation_source, target=relation_target, relation_type=relation_type).exists():
            summary['skipped'] += 1
            summary['relations'].append({
                'index': index,
                'source': relation_source.id,
                'target': relation_target.id,
                'relation_type': relation_type,
                'action': 'skip',
                'reason': 'duplicate',
            })
            continue
        payload_data = {
            'source': relation_source.id,
            'target': relation_target.id,
            'relation_type': relation_type,
            'description': hint.get('description') or f"由同步任务 {job.name if job else source.get('source_type')} 自动发现",
            'evidence_source': 'sync',
            'confidence': hint.get('confidence', 80),
            'evidence': {
                'sync_job_id': job.id if job else None,
                'source_type': source.get('source_type'),
                'source_unique_id': source.get('source_unique_id'),
                'matched_by': matched_by,
                'hint': hint,
            },
        }
        serializer = CIRelationSerializer(data=payload_data)
        if not serializer.is_valid():
            summary['failed'] += 1
            summary['errors'].append({
                'index': index,
                'relation_type': relation_type,
                'direction': direction,
                'peer_role': peer_role,
                'reason': 'validation_failed',
                'errors': serializer.errors,
                'hint': hint,
            })
            continue
        if dry_run:
            summary['skipped'] += 1
            summary['relations'].append({**payload_data, 'action': 'preview'})
            continue
        relation = serializer.save()
        snapshot = _relation_snapshot(relation)
        _record_ci_change(
            relation.source,
            'relation_create',
            {},
            snapshot,
            operator=operator,
            source='relation',
        )
        summary['created'] += 1
        summary['relations'].append({**snapshot, 'action': 'create'})
    return summary


def _sync_relation_failed_hint_payload(payload, relation_summary):
    failed_indexes = {
        item.get('index')
        for item in relation_summary.get('errors', [])
        if item.get('reason') == 'peer_not_found' and item.get('index')
    }
    if not failed_indexes:
        return None
    hints = [
        hint
        for index, hint in enumerate(_sync_relation_hint_rows(payload), start=1)
        if index in failed_indexes
    ]
    if not hints:
        hints = [
            item.get('hint')
            for item in relation_summary.get('errors', [])
            if item.get('reason') == 'peer_not_found'
            and item.get('index') in failed_indexes
            and isinstance(item.get('hint'), dict)
        ]
    if not hints:
        return None
    return {'relation_hints': hints}


def _sync_relation_merge_retry_summary(initial, retry):
    merged = {
        'total': initial.get('total', 0),
        'created': initial.get('created', 0) + retry.get('created', 0),
        'skipped': initial.get('skipped', 0) + retry.get('skipped', 0),
        'failed': initial.get('failed', 0),
        'relations': list(initial.get('relations') or []),
        'errors': list(initial.get('errors') or []),
    }
    resolved_count = retry.get('created', 0) + retry.get('skipped', 0)
    if resolved_count:
        remaining_peer_errors = [
            item for item in merged['errors']
            if item.get('reason') != 'peer_not_found'
        ]
        retry_errors = list(retry.get('errors') or [])
        merged['errors'] = [*remaining_peer_errors, *retry_errors]
        merged['failed'] = max(0, merged['failed'] - resolved_count)
    merged['relations'].extend(retry.get('relations') or [])
    return merged


def _preview_relation_type_key(row):
    return (
        row.get('ci_type')
        or row.get('ci_type_id')
        or row.get('ci_type_name')
        or row.get('ci_model_name')
        or ''
    )


def _preview_batch_relation_indexes(preview_items):
    by_source = {}
    by_name = {}
    by_attribute = {}

    def add_unique(index, key, item):
        if not key[-1]:
            return
        existing = index.get(key)
        if existing is None:
            index[key] = item
        elif existing is not item:
            index[key] = False

    for item in preview_items:
        result = item.get('result') or {}
        source = result.get('source') or {}
        after = result.get('after') or {}
        if result.get('action') == 'conflict':
            continue
        source_key = _sync_source_identity_key(source)
        if source_key[-1]:
            by_source[source_key] = item
        name = after.get('name') or ''
        if name:
            by_name[(str(_preview_relation_type_key(after)), name)] = item
            by_name[('', name)] = item
        attributes = after.get('attributes') or {}
        type_keys = {str(_preview_relation_type_key(after)), str(after.get('ci_type') or ''), after.get('ci_type_name') or '', ''}
        for match_name, keys in (
            ('ip', SYNC_RELATION_IP_KEYS),
            ('endpoint', SYNC_RELATION_ENDPOINT_KEYS),
            ('instance_id', ('instance_id', 'external_id', 'resource_id')),
        ):
            for key in keys:
                value = attributes.get(key)
                if value in (None, ''):
                    continue
                for type_key in type_keys:
                    add_unique(by_attribute, (str(type_key), match_name, str(value)), item)
    return by_source, by_name, by_attribute


def _preview_relation_find_peer_item(hint, role, current_source, by_source, by_name, by_attribute):
    peer_source = _sync_relation_peer_source(hint, role, current_source)
    source_key = _sync_source_identity_key(peer_source)
    if source_key[-1] and source_key in by_source:
        return by_source[source_key], 'batch_source'
    peer = _sync_relation_peer_payload(hint, role)
    name = (
        hint.get(f'{role}_name')
        or hint.get(f'{role}_ci_name')
        or peer.get('name')
        or peer.get('ci_name')
        or peer.get('resource_name')
    )
    if name:
        ci_type = _sync_relation_peer_type(hint, peer, role)
        type_key = str(ci_type.id if ci_type else (hint.get(f'{role}_ci_type_name') or peer.get('ci_type_name') or ''))
        return by_name.get((type_key, name)) or by_name.get(('', name)), 'batch_name'
    for match_name, keys in (
        ('ip', SYNC_RELATION_IP_KEYS),
        ('endpoint', SYNC_RELATION_ENDPOINT_KEYS),
        ('instance_id', ('instance_id', 'external_id', 'resource_id')),
    ):
        value = _sync_relation_peer_value(hint, peer, role, *keys)
        if not value:
            continue
        ci_type = _sync_relation_peer_type(hint, peer, role)
        type_keys = [str(ci_type.id if ci_type else ''), hint.get(f'{role}_ci_type_name') or peer.get('ci_type_name') or '', '']
        for type_key in type_keys:
            item = by_attribute.get((str(type_key), match_name, str(value)))
            if item:
                return item, f'batch_{match_name}'
    return None, ''


def _preview_batch_sync_relations(preview_items, job=None):
    by_source, by_name, by_attribute = _preview_batch_relation_indexes(preview_items)
    summary = defaultdict(int)
    for item in preview_items:
        result = item.get('result') or {}
        if result.get('action') == 'conflict':
            continue
        if result.get('ci') is not None:
            continue
        payload = item.get('payload') or {}
        hints = _sync_relation_hint_rows(payload)
        if not hints:
            continue
        current_source = result.get('source') or {}
        current_after = result.get('after') or {}
        relation_summary = result.get('relation_summary') or {
            'total': len(hints),
            'created': 0,
            'skipped': 0,
            'failed': 0,
            'preview': 0,
            'relations': [],
            'errors': [],
        }
        for index, hint in enumerate(hints, start=1):
            relation_type = str(hint.get('relation_type') or hint.get('type') or hint.get('relation') or 'depends_on').strip()
            direction = str(hint.get('direction') or 'outgoing').strip().lower()
            peer_role = 'source' if direction == 'incoming' else 'target'
            peer_ci, matched_by = _sync_relation_find_peer(hint, peer_role, current_source)
            peer_item = None
            if peer_ci is None:
                peer_item, matched_by = _preview_relation_find_peer_item(hint, peer_role, current_source, by_source, by_name, by_attribute)
            if peer_ci is None and peer_item is None:
                relation_summary['failed'] = relation_summary.get('failed', 0) + 1
                relation_summary.setdefault('errors', []).append({
                    'index': index,
                    'relation_type': relation_type,
                    'direction': direction,
                    'peer_role': peer_role,
                    'reason': 'peer_not_found',
                    'hint': hint,
                })
                summary['relation_failed'] += 1
                continue
            peer_after = (peer_item.get('result') or {}).get('after') if peer_item else {}
            relation_source = peer_after if direction == 'incoming' else current_after
            relation_target = current_after if direction == 'incoming' else peer_after
            if peer_ci is not None:
                relation_source = _config_item_snapshot(peer_ci) if direction == 'incoming' else current_after
                relation_target = current_after if direction == 'incoming' else _config_item_snapshot(peer_ci)
            relation_summary['preview'] = relation_summary.get('preview', 0) + 1
            relation_summary.setdefault('relations', []).append({
                'index': index,
                'source_name': relation_source.get('name') or '',
                'target_name': relation_target.get('name') or '',
                'source_unique_id': (relation_source.get('attributes') or {}).get('source_unique_id') or '',
                'target_unique_id': (relation_target.get('attributes') or {}).get('source_unique_id') or '',
                'relation_type': relation_type,
                'action': 'preview',
                'matched_by': matched_by,
            })
            summary['relation_preview'] += 1
        if relation_summary.get('total'):
            result['relation_summary'] = relation_summary
            after = dict(result.get('after') or {})
            after['_sync_relations'] = relation_summary
            result['after'] = after
            item['row']['after'] = after
    return dict(summary)


def _third_party_service_type_ids():
    return list(CIType.objects.filter(code='THIRD_PARTY_SERVICE').values_list('id', flat=True))


def _is_third_party_service_ci(ci):
    return bool(ci.ci_type_id and (ci.ci_type.code or '').upper() == 'THIRD_PARTY_SERVICE')


def _idc_server_type_ids():
    return list(CIType.objects.filter(code__in=['IDC_SERVER', 'PHYSICAL_SERVER']).values_list('id', flat=True))


def _is_idc_server_ci(ci):
    code = (ci.ci_type.code or '').upper() if ci.ci_type_id else ''
    name = normalize_ci_type_name(ci.ci_type.name) if ci.ci_type_id else ''
    return code in {'IDC_SERVER', 'PHYSICAL_SERVER'} or name in {'机房服务器', '物理机'}


def _date_from_ci_attribute(value):
    if not value:
        return None
    if hasattr(value, 'date'):
        return value.date()
    if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day'):
        return value
    parsed = parse_date(str(value)[:10])
    if parsed:
        return parsed
    parsed_dt = parse_datetime(str(value))
    return parsed_dt.date() if parsed_dt else None


def _int_attribute(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _ci_governance_entry(ci, category, metric=''):
    """Read the persisted governance state for an asset risk row."""
    governance = (ci.attributes or {}).get('governance') or {}
    if not isinstance(governance, dict):
        return {}
    key = f'{category}:{metric}' if metric else category
    entry = governance.get(key) or governance.get(category) or {}
    return dict(entry) if isinstance(entry, dict) else {}


def _governance_status_is_closed(entry, fingerprint=''):
    if not isinstance(entry, dict) or entry.get('status') not in {'resolved', 'ignored'}:
        return False
    saved_fingerprint = str(entry.get('fingerprint') or '').strip()
    return not saved_fingerprint or not fingerprint or saved_fingerprint == fingerprint


def _third_party_service_expiry_state_for_ci(ci, today=None):
    if not _is_third_party_service_ci(ci):
        return None
    attributes = ci.attributes or {}
    expire_date = _date_from_ci_attribute(attributes.get('service_expiry_date'))
    if not expire_date:
        return {'status': 'missing', 'expire_date': None, 'days_left': None}
    today = today or timezone.localdate()
    days_left = (expire_date - today).days
    warning_days = max(_int_attribute(attributes.get('service_expire_warning_days'), 30), 0)
    if days_left < 0:
        status_name = 'expired'
    elif days_left <= 7:
        status_name = 'urgent'
    elif days_left <= warning_days:
        status_name = 'warning'
    else:
        status_name = 'normal'
    return {
        'status': status_name,
        'expire_date': expire_date,
        'days_left': days_left,
        'warning_days': warning_days,
    }


def _third_party_expiry_risks_for_ci(ci, today=None):
    expiry = _third_party_service_expiry_state_for_ci(ci, today=today)
    if not expiry or expiry['status'] in {'missing', 'normal'}:
        return []
    days_left = expiry['days_left']
    if days_left < 0:
        title = f'{ci.name} 服务已过期 {abs(days_left)} 天'
    else:
        title = f'{ci.name} 服务将在 {days_left} 天后到期'
    risk_fingerprint = f'service_expiry:{expiry["expire_date"].isoformat()}'
    governance = _ci_governance_entry(ci, 'service_expiry')
    if _governance_status_is_closed(governance, risk_fingerprint):
        return []
    return [{
        'type': 'third_party_service_expiry',
        'severity': 'danger' if expiry['status'] in {'expired', 'urgent'} else 'warning',
        'title': title,
        'action': '建议完成服务续期并复核账号、密钥轮换和备份方案，避免外部服务中断。',
        'ci_id': ci.id,
        'ci_name': ci.name,
        'ci_type': ci.ci_type.code,
        'ci_type_name': ci.ci_type.name,
        'expire_date': expiry['expire_date'].isoformat(),
        'days_left': days_left,
        'governance_status': governance.get('status', 'open'),
        'governance_note': governance.get('note', ''),
        'risk_fingerprint': risk_fingerprint,
    }]


def _asset_service_expiry_risks_for_ci(ci, today=None):
    today = today or timezone.localdate()
    attributes = ci.attributes or {}
    expire_date = _date_from_ci_attribute(
        attributes.get('service_expiry_date')
        or attributes.get('warranty_end_date')
        or attributes.get('warranty_expire_date')
    )
    if not expire_date:
        return []
    warning_days = _int_attribute(
        attributes.get('service_expire_warning_days') or attributes.get('warranty_warning_days'),
        30,
    )
    days_left = (expire_date - today).days
    if days_left < 0:
        severity = 'danger'
        title = f'{ci.name} 服务已过期 {abs(days_left)} 天'
    elif days_left <= max(warning_days, 0):
        severity = 'warning'
        title = f'{ci.name} 服务将在 {days_left} 天后到期'
    else:
        return []
    risk_fingerprint = f'service_expiry:{expire_date.isoformat()}'
    governance = _ci_governance_entry(ci, 'service_expiry')
    if _governance_status_is_closed(governance, risk_fingerprint):
        return []
    return [{
        'type': 'asset_service_expiry',
        'severity': severity,
        'title': title,
        'action': '建议核对续期、替换或下线计划，避免资产服务周期中断。',
        'ci_id': ci.id,
        'ci_name': ci.name,
        'ci_type': ci.ci_type.code,
        'ci_type_name': ci.ci_type.name,
        'expire_date': expire_date.isoformat(),
        'days_left': days_left,
        'governance_status': governance.get('status', 'open'),
        'governance_note': governance.get('note', ''),
        'risk_fingerprint': risk_fingerprint,
    }]


def _resource_node_subtree_ids(resource_node_id):
    """Return a resource node and every descendant for tree-based filtering."""
    node_ids = {resource_node_id}
    parent_ids = {resource_node_id}
    while parent_ids:
        child_ids = set(
            ResourceNode.objects.filter(parent_id__in=parent_ids)
            .exclude(id__in=node_ids)
            .values_list('id', flat=True)
        )
        if not child_ids:
            break
        node_ids.update(child_ids)
        parent_ids = child_ids
    return node_ids


def _apply_config_item_attribute_filters(qs, params):
    business_node = (params.get('business_node') or '').strip()
    environment_node = (params.get('environment_node') or '').strip()
    resource_node = (params.get('resource_node') or '').strip()
    status = (params.get('status') or '').strip()
    asset_search = (params.get('asset_search') or params.get('name_search') or '').strip()
    attribute_search = (params.get('attribute_search') or params.get('attr_search') or '').strip()
    department = (params.get('department') or params.get('dept') or '').strip()
    system = (params.get('system') or params.get('business_system') or params.get('application') or '').strip()
    admin_user = (params.get('admin_user') or params.get('owner') or params.get('responsible') or '').strip()
    ownership = (params.get('ownership') or '').strip()
    source_type = (params.get('source_type') or params.get('source') or '').strip()
    source_account = (params.get('source_account') or params.get('cloud_account') or params.get('account') or '').strip()
    source_account_missing = str(params.get('source_account_missing') or '').strip().lower() in ('1', 'true', 'yes')
    source_region = (params.get('source_region') or params.get('cloud_region') or params.get('region') or '').strip()
    source_unique_id = (params.get('source_unique_id') or params.get('instance_id') or '').strip()
    vsphere_cluster = (params.get('vsphere_cluster') or params.get('cluster') or '').strip()
    vsphere_host = (params.get('vsphere_host') or params.get('host') or params.get('esxi_host') or '').strip()
    availability_zone = (params.get('availability_zone') or params.get('zone_id') or params.get('zone') or params.get('az') or '').strip()
    sync_status = (params.get('sync_status') or params.get('source_sync_status') or '').strip()
    engine = (params.get('engine') or params.get('db_engine') or params.get('middleware_engine') or '').strip()
    vpc_id = (params.get('vpc_id') or params.get('vpc') or '').strip()
    network_type = (params.get('network_type') or params.get('network') or '').strip()
    storage_class = (params.get('storage_class') or params.get('storage_type') or '').strip()
    acl = (params.get('acl') or params.get('access_control') or '').strip()
    idc = (params.get('idc') or params.get('machine_room') or params.get('room') or params.get('datacenter') or '').strip()
    rack = (params.get('rack') or params.get('cabinet') or '').strip()
    lifecycle_status = (params.get('lifecycle_status') or params.get('lifecycle') or '').strip()
    service_expiry_risk = (
        params.get('service_expiry_risk')
        or params.get('warranty_risk')
        or params.get('warranty_expiry_risk')
        or ''
    ).strip()
    provider = (params.get('provider') or params.get('external_provider') or '').strip()
    service_type = (params.get('service_type') or params.get('external_service_type') or '').strip()
    expiry_risk = (params.get('expiry_risk') or params.get('external_expiry_risk') or '').strip()
    if business_node:
        qs = qs.filter(business_node_id=business_node)
    if environment_node:
        qs = qs.filter(environment_node_id=environment_node)
    if resource_node:
        try:
            resource_node_id = int(resource_node)
        except (TypeError, ValueError):
            return qs.none()
        resource_node_ids = _resource_node_subtree_ids(resource_node_id)
        qs = qs.filter(
            Q(resource_node_id__in=resource_node_ids)
            | Q(resource_node__isnull=True, attributes__resource_node_id__in=resource_node_ids)
        )
    if status == 'stopped':
        qs = qs.filter(
            Q(status='stopped')
            | Q(status='idle')
            | Q(attributes__instance_status__iexact='stopped')
            | Q(attributes__power_state__iexact='poweredoff')
            | Q(attributes__runtime_status__iexact='stopped')
        )
    elif status:
        qs = qs.filter(status=status)
    if asset_search:
        qs = qs.filter(name__icontains=asset_search)
    if attribute_search:
        source_ci_ids = CISourceMapping.objects.filter(
            Q(source_unique_id__icontains=attribute_search)
            | Q(source_account__icontains=attribute_search)
            | Q(source_region__icontains=attribute_search)
        ).values_list('ci_id', flat=True)
        qs = qs.annotate(_attribute_search_text=Cast('attributes', output_field=CharField())).filter(
            Q(id__in=source_ci_ids)
            | Q(_attribute_search_text__icontains=attribute_search)
            | Q(attributes__ip_address__icontains=attribute_search)
            | Q(attributes__ip__icontains=attribute_search)
            | Q(attributes__private_ip__icontains=attribute_search)
            | Q(attributes__public_ip__icontains=attribute_search)
            | Q(attributes__host_ip__icontains=attribute_search)
            | Q(attributes__docker_environment_ip__icontains=attribute_search)
            | Q(attributes__source_unique_id__icontains=attribute_search)
            | Q(attributes__instance_id__icontains=attribute_search)
            | Q(attributes__resource_id__icontains=attribute_search)
            | Q(attributes__asset_id__icontains=attribute_search)
        )
    if admin_user:
        qs = qs.filter(admin_user=admin_user)
    if ownership:
        qs = qs.filter(
            Q(admin_user__icontains=ownership)
            | Q(attributes__department__icontains=ownership)
        )
    if source_type:
        source_ci_ids = CISourceMapping.objects.filter(source_type=source_type).values_list('ci_id', flat=True)
        qs = qs.filter(Q(id__in=source_ci_ids) | Q(attributes__source_type=source_type) | Q(attributes__source=source_type))
    if source_account:
        source_ci_ids = CISourceMapping.objects.filter(source_account=source_account).values_list('ci_id', flat=True)
        qs = qs.filter(
            Q(id__in=source_ci_ids)
            | Q(attributes__source_account=source_account)
            | Q(attributes__cloud_account=source_account)
            | Q(attributes__account=source_account)
            | Q(attributes__account_id=source_account)
            | Q(attributes__account_name=source_account)
        )
    if source_account_missing:
        mapped_ci_ids = CISourceMapping.objects.exclude(source_account='').values_list('ci_id', flat=True)
        qs = qs.exclude(id__in=mapped_ci_ids)
        for key in ['source_account', 'cloud_account', 'account', 'account_id', 'account_name']:
            qs = qs.filter(
                Q(**{f'attributes__{key}__isnull': True})
                | Q(**{f'attributes__{key}': ''})
                | Q(**{f'attributes__{key}': '-'})
            )
    if source_region:
        source_ci_ids = CISourceMapping.objects.filter(source_region=source_region).values_list('ci_id', flat=True)
        qs = qs.filter(
            Q(id__in=source_ci_ids)
            | Q(attributes__source_region=source_region)
            | Q(attributes__cloud_region=source_region)
            | Q(attributes__region=source_region)
            | Q(attributes__region_id=source_region)
        )
    if source_unique_id:
        source_ci_ids = CISourceMapping.objects.filter(source_unique_id=source_unique_id).values_list('ci_id', flat=True)
        qs = qs.filter(
            Q(id__in=source_ci_ids)
            | Q(attributes__source_unique_id=source_unique_id)
            | Q(attributes__instance_id=source_unique_id)
        )
    if vsphere_cluster:
        qs = qs.filter(Q(attributes__cluster=vsphere_cluster) | Q(attributes__vsphere_cluster=vsphere_cluster))
    if vsphere_host:
        qs = qs.filter(
            Q(attributes__host=vsphere_host)
            | Q(attributes__host_name=vsphere_host)
            | Q(attributes__esxi_host=vsphere_host)
        )
    if availability_zone:
        qs = qs.filter(
            Q(attributes__availability_zone=availability_zone)
            | Q(attributes__zone_id=availability_zone)
            | Q(attributes__zone=availability_zone)
            | Q(attributes__az=availability_zone)
        )
    if sync_status:
        source_ci_ids = CISourceMapping.objects.filter(sync_status=sync_status).values_list('ci_id', flat=True)
        qs = qs.filter(Q(id__in=source_ci_ids) | Q(attributes__sync_status=sync_status))
    if engine:
        qs = qs.filter(Q(attributes__engine=engine) | Q(attributes__db_engine=engine) | Q(attributes__middleware_engine=engine))
    if vpc_id:
        qs = qs.filter(Q(attributes__vpc_id=vpc_id) | Q(attributes__vpc=vpc_id))
    if network_type:
        qs = qs.filter(Q(attributes__network_type=network_type) | Q(attributes__network=network_type))
    if storage_class:
        qs = qs.filter(Q(attributes__storage_class=storage_class) | Q(attributes__storage_type=storage_class))
    if acl:
        qs = qs.filter(Q(attributes__acl=acl) | Q(attributes__access_control=acl))
    if department:
        qs = qs.filter(attributes__department=department)
    if system:
        qs = qs.filter(
            Q(business_line=system)
            | Q(attributes__system=system)
            | Q(attributes__business_system=system)
            | Q(attributes__app_name=system)
            | Q(attributes__application=system)
            | Q(attributes__service_name=system)
        )
    if idc:
        qs = qs.filter(
            Q(attributes__idc=idc)
            | Q(attributes__machine_room=idc)
            | Q(attributes__room=idc)
            | Q(attributes__datacenter=idc)
        )
    if rack:
        qs = qs.filter(Q(attributes__rack=rack) | Q(attributes__cabinet=rack))
    if lifecycle_status:
        qs = qs.filter(attributes__lifecycle_status=lifecycle_status)
    if provider:
        qs = qs.filter(attributes__provider=provider)
    if service_type:
        qs = qs.filter(attributes__service_type=service_type)
    if expiry_risk:
        today = timezone.localdate()
        matched_ids = []
        third_party_ids = _third_party_service_type_ids()
        candidate_qs = qs.select_related(None).select_related('ci_type')
        if third_party_ids:
            candidate_qs = candidate_qs.filter(ci_type_id__in=third_party_ids)
        for ci in candidate_qs.only('id', 'ci_type_id', 'ci_type__code', 'attributes'):
            expiry = _third_party_service_expiry_state_for_ci(ci, today=today)
            if not expiry:
                continue
            expiry_status = expiry['status']
            if expiry_risk in {'expired', 'urgent', 'warning', 'normal', 'missing'} and expiry_status == expiry_risk:
                matched_ids.append(ci.id)
            elif expiry_risk == 'expiring' and expiry_status in {'warning', 'urgent'}:
                matched_ids.append(ci.id)
            elif expiry_risk in {'risk', 'all'} and expiry_status in {'expired', 'urgent', 'warning'}:
                matched_ids.append(ci.id)
        qs = qs.filter(id__in=matched_ids)
    if service_expiry_risk:
        today = timezone.localdate()
        matched_ids = []
        candidate_qs = qs.select_related(None).select_related('ci_type')
        for ci in candidate_qs.only('id', 'ci_type_id', 'ci_type__code', 'ci_type__name', 'attributes'):
            risks = _asset_service_expiry_risks_for_ci(ci, today=today)
            if service_expiry_risk == 'expired' and any(item['days_left'] < 0 for item in risks):
                matched_ids.append(ci.id)
            elif service_expiry_risk in {'expiring', 'warning'} and any(item['days_left'] >= 0 for item in risks):
                matched_ids.append(ci.id)
            elif service_expiry_risk in {'risk', 'all'} and risks:
                matched_ids.append(ci.id)
        qs = qs.filter(id__in=matched_ids)
    return qs


def _missing_fields_for_ci(ci):
    missing = []
    attributes = ci.attributes or {}
    if not (ci.business_line or '').strip():
        missing.append({'code': 'business_line', 'name': '业务线'})
    if not (ci.admin_user or '').strip():
        missing.append({'code': 'admin_user', 'name': '负责人'})
    if not (ci.environment or '').strip():
        missing.append({'code': 'environment', 'name': '环境'})
    if not str(attributes.get('department') or '').strip():
        missing.append({'code': 'department', 'name': '部门'})
    for field in ci.ci_type.fields.filter(is_active=True, required=True):
        if attributes.get(field.code) in (None, '', []):
            missing.append({'code': field.code, 'name': field.name})
    return missing


def _missing_field_code_set(missing_fields):
    return {
        str(item.get('code') or item.get('name') or '').strip()
        for item in (missing_fields or [])
        if str(item.get('code') or item.get('name') or '').strip()
    }


def _sync_completion_issue(ci, missing_fields=None, assigned_to=''):
    missing_fields = missing_fields if missing_fields is not None else _missing_fields_for_ci(ci)
    open_qs = CICompletionIssue.objects.filter(ci=ci).exclude(status__in=['resolved', 'ignored'])
    if not missing_fields:
        for issue in open_qs:
            issue.status = 'resolved'
            issue.resolved_at = timezone.now()
            issue.resolution_note = issue.resolution_note or '关键字段已补齐'
            issue.save(update_fields=['status', 'resolved_at', 'resolution_note', 'updated_at'])
        return None
    missing_codes = _missing_field_code_set(missing_fields)
    ignored_issue = CICompletionIssue.objects.filter(ci=ci, status='ignored').order_by('-updated_at', '-id').first()
    if ignored_issue and _missing_field_code_set(ignored_issue.missing_fields) == missing_codes:
        ignored_issue.missing_fields = missing_fields
        ignored_issue.save(update_fields=['missing_fields', 'updated_at'])
        return ignored_issue
    severity = 'high' if any(item['code'] in {'business_line', 'admin_user'} for item in missing_fields) else 'medium'
    issue = open_qs.order_by('-created_at').first()
    if issue is None:
        issue = CICompletionIssue.objects.create(
            ci=ci,
            missing_fields=missing_fields,
            severity=severity,
            assigned_to=assigned_to or '',
        )
    else:
        issue.missing_fields = missing_fields
        issue.severity = severity
        if assigned_to:
            issue.assigned_to = assigned_to
            issue.status = 'assigned'
        issue.save(update_fields=['missing_fields', 'severity', 'assigned_to', 'status', 'updated_at'])
    return issue


TAG_INPUT_KEYS = ('tags', 'tag_items', 'cloud_tags')
TAG_NAME_KEYS = ('name', 'label', 'value', 'Value', 'TagValue', 'tag_value')
TAG_CATEGORY_KEYS = ('category', 'key', 'Key', 'TagKey', 'tag_key', 'group', 'type')


def _payload_has_tag_input(payload):
    if any(key in payload for key in TAG_INPUT_KEYS):
        return True
    attributes = payload.get('attributes') if isinstance(payload, dict) else {}
    return isinstance(attributes, dict) and any(key in attributes for key in TAG_INPUT_KEYS)


def _tag_input_values(value):
    if value in (None, ''):
        return []
    if isinstance(value, (list, tuple, set)):
        items = []
        for item in value:
            items.extend(_tag_input_values(item))
        return items
    if isinstance(value, dict):
        nested = value.get('Tag') or value.get('tag') or value.get('Tags') or value.get('tags')
        if nested is not None:
            return _tag_input_values(nested)
        if any(key in value for key in ('id', *TAG_NAME_KEYS, *TAG_CATEGORY_KEYS)):
            return [value]
        return [
            {'key': key, 'value': item}
            for key, item in value.items()
            if item not in (None, '', [], {})
        ]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if ',' in text or ';' in text:
            parts = re.split(r'[;,]+', text)
            if len(parts) > 1:
                return [part.strip() for part in parts if part.strip()]
        return [text]
    return [value]


def _payload_tag_values(payload):
    values = []
    for key in TAG_INPUT_KEYS:
        if key in payload:
            values.extend(_tag_input_values(payload.get(key)))
    attributes = payload.get('attributes') if isinstance(payload, dict) else {}
    if isinstance(attributes, dict):
        for key in TAG_INPUT_KEYS:
            if key in attributes:
                values.extend(_tag_input_values(attributes.get(key)))
    return values


def _normalize_payload_tag_specs(payload):
    tag_ids = []
    tag_specs = []
    seen_ids = set()
    seen_names = set()
    for item in _payload_tag_values(payload):
        if isinstance(item, int):
            if item not in seen_ids:
                tag_ids.append(item)
                seen_ids.add(item)
            continue
        if isinstance(item, dict):
            tag_id = item.get('id')
            if tag_id not in (None, ''):
                try:
                    tag_id = int(tag_id)
                except (TypeError, ValueError):
                    tag_id = None
                if tag_id and tag_id not in seen_ids:
                    tag_ids.append(tag_id)
                    seen_ids.add(tag_id)
                    continue
            name = next((item.get(key) for key in TAG_NAME_KEYS if item.get(key) not in (None, '')), '')
            category = next((item.get(key) for key in TAG_CATEGORY_KEYS if item.get(key) not in (None, '')), '')
        else:
            text = str(item or '').strip()
            if ':' in text:
                category, name = [part.strip() for part in text.split(':', 1)]
            else:
                name, category = text, ''
        name = str(name or '').strip()
        category = str(category or '').strip()
        if not name:
            continue
        key = name.lower()
        if key in seen_names:
            continue
        tag_specs.append({'name': name[:50], 'category': category[:50]})
        seen_names.add(key)
    return tag_ids, tag_specs


def _payload_tags_for_snapshot(payload):
    tag_ids, tag_specs = _normalize_payload_tag_specs(payload)
    previews = []
    seen = set()
    for tag in CITag.objects.filter(id__in=tag_ids, is_active=True):
        previews.append({'id': tag.id, 'name': tag.name, 'category': tag.category})
        seen.add(tag.name.lower())
    for spec in tag_specs:
        existing = CITag.objects.filter(name=spec['name']).first()
        name_key = spec['name'].lower()
        if name_key in seen:
            continue
        previews.append({
            'id': existing.id if existing else None,
            'name': spec['name'],
            'category': existing.category if existing and existing.category else spec['category'],
        })
        seen.add(name_key)
    return previews


def _payload_tag_objects(payload):
    tag_ids, tag_specs = _normalize_payload_tag_specs(payload)
    tags = []
    seen_ids = set()
    seen_names = set()
    for tag in CITag.objects.filter(id__in=tag_ids, is_active=True):
        tags.append(tag)
        seen_ids.add(tag.id)
        seen_names.add(tag.name.lower())
    missing_ids = set(tag_ids) - seen_ids
    if missing_ids:
        raise ValueError(f'Unknown tag id: {sorted(missing_ids)[0]}')
    for spec in tag_specs:
        name = spec['name']
        if name.lower() in seen_names:
            continue
        tag, _ = CITag.objects.get_or_create(name=name, defaults={'category': spec['category']})
        update_fields = []
        if not tag.is_active:
            tag.is_active = True
            update_fields.append('is_active')
        if spec['category'] and not tag.category:
            tag.category = spec['category']
            update_fields.append('category')
        if update_fields:
            tag.save(update_fields=[*update_fields, 'updated_at'])
        tags.append(tag)
        seen_names.add(name.lower())
    return tags


def _payload_to_config_item_data(payload, ci_type, source):
    validate_no_sensitive_plaintext(payload, context='同步资源数据')
    attributes = _strip_resource_waterline_attributes(normalize_ci_attributes(payload.get('attributes') or {}))
    for field_code in ci_type.fields.filter(is_active=True).values_list('code', flat=True):
        if field_code in payload and attributes.get(field_code) in (None, ''):
            attributes[field_code] = payload[field_code]
    department = payload.get('department') or payload.get('dept') or attributes.get('department') or attributes.get('dept') or ''
    if department:
        attributes['department'] = str(department)[:80]
    attributes.update({
        'source_type': source['source_type'],
        'source_account': source['source_account'],
        'source_region': source['source_region'],
        'source_unique_id': source['source_unique_id'],
    })
    attributes = _strip_resource_waterline_attributes({key: value for key, value in attributes.items() if value not in (None, '')})
    return {
        'name': (payload.get('name') or payload.get('resource_name') or source['source_unique_id'] or '未命名资源')[:100],
        'ci_type': ci_type,
        'business_line': (payload.get('business_line') or attributes.get('business_line') or '')[:50],
        'environment': payload.get('environment') or attributes.get('environment') or '',
        'admin_user': (payload.get('admin_user') or payload.get('owner') or attributes.get('admin_user') or attributes.get('owner') or '')[:50],
        'status': payload.get('status') or attributes.get('status') or 'active',
        'attributes': attributes,
    }


SYNC_IP_ATTRIBUTE_CODES = {'private_ip', 'public_ip', 'ip_address', 'ip'}


def _valid_ipv4_address(value):
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        return ''


def _clean_sync_ip_attributes(attributes, existing_attributes=None):
    cleaned = dict(attributes or {})
    existing_attributes = existing_attributes or {}
    for key in SYNC_IP_ATTRIBUTE_CODES:
        value = _valid_ipv4_address(cleaned.get(key))
        if value:
            cleaned[key] = value
            continue
        previous_value = _valid_ipv4_address(existing_attributes.get(key))
        if previous_value:
            cleaned[key] = previous_value
        else:
            cleaned.pop(key, None)
    return cleaned


SYNC_METADATA_FIELD_CODES = {
    'source_type',
    'source_account',
    'source_region',
    'source_unique_id',
}

RESOURCE_WATERLINE_ATTRIBUTE_CODES = {
    'cpu_used_mhz', 'cpu_usage', 'cpu_usage_percent', 'cpu_utilization', 'cpu_utilization_percent', 'cpu_used_percent',
    'memory_total_gb', 'memory_used_gb', 'memory_free_gb', 'memory_available_gb', 'memory_usage', 'memory_usage_percent',
    'memory_utilization', 'memory_utilization_percent', 'memory_used_percent',
    'disk_used_gb', 'disk_usage', 'disk_usage_percent', 'disk_utilization', 'disk_utilization_percent', 'disk_used_percent',
    'storage_used_gb', 'storage_usage', 'storage_usage_percent', 'storage_utilization', 'storage_utilization_percent', 'storage_used_percent',
    'root_disk_total_gb', 'root_disk_free_gb', 'root_disk_available_gb', 'root_mountpoint',
    'metric_collection_source', 'metric_collection_status', 'metric_collection_error', 'metrics_collection_status',
    'metric_datasource', 'metric_collected_at', 'prometheus_target',
}


def _strip_resource_waterline_attributes(attributes):
    return {
        key: value
        for key, value in (attributes or {}).items()
        if key not in RESOURCE_WATERLINE_ATTRIBUTE_CODES
    }


def _is_present_sync_value(value):
    return value not in (None, '', [], {})


def _merge_attributes_by_sync_mode(ci_type, existing_attributes, incoming_attributes):
    merged = dict(existing_attributes or {})
    field_modes = {
        field.code: field.sync_mode
        for field in ci_type.fields.filter(is_active=True).only('code', 'sync_mode')
    }
    for key, value in (incoming_attributes or {}).items():
        if key in SYNC_METADATA_FIELD_CODES:
            merged[key] = value
            continue
        if field_modes.get(key, 'source') == 'manual' and _is_present_sync_value(merged.get(key)):
            continue
        merged[key] = value
    return merged


SYNC_NUMERIC_CHANGE_TOLERANCE = Decimal('0.5')


def _preserve_insignificant_numeric_values(existing, incoming):
    """Keep the stored value when a collector only reports decimal noise."""
    if isinstance(existing, dict) and isinstance(incoming, dict):
        return {
            key: _preserve_insignificant_numeric_values(existing.get(key), value)
            for key, value in incoming.items()
        }
    if isinstance(existing, list) and isinstance(incoming, list):
        return incoming
    if existing in (None, '') or incoming in (None, ''):
        return incoming
    try:
        difference = abs(Decimal(str(existing)) - Decimal(str(incoming)))
    except (InvalidOperation, TypeError, ValueError):
        return incoming
    return existing if difference < SYNC_NUMERIC_CHANGE_TOLERANCE else incoming


def _resolve_cloud_resource_node_for_source(source):
    """Resolve a synchronized resource to the stable cloud tree node IDs."""
    account = str((source or {}).get('source_account') or '').strip()
    if not account:
        return None
    account_nodes = list(
        ResourceNode.objects.filter(
            node_type='cloud_account',
            parent__isnull=True,
            name=account,
        ).order_by('id')[:2]
    )
    if len(account_nodes) != 1:
        return None
    account_node = account_nodes[0]
    region = str((source or {}).get('source_region') or '').strip()
    if not region:
        return account_node
    region_nodes = list(
        ResourceNode.objects.filter(
            node_type='cloud_region',
            parent=account_node,
            name=region,
        ).order_by('id')[:2]
    )
    if len(region_nodes) == 1:
        return region_nodes[0]
    if len(region_nodes) > 1:
        return account_node
    return ResourceNode.objects.create(
        name=region,
        node_type='cloud_region',
        parent=account_node,
        is_synced=account_node.is_synced,
    )


def _upsert_config_item_from_payload(payload, *, job=None, dry_run=False, operator='', actor=None, sync_context=None):
    if not isinstance(payload, dict):
        raise ValueError('同步数据必须是对象')
    ci_type = _resolve_ci_type_from_payload(payload)
    source = _source_values(payload, default_source_type=(job.source_type if job else 'manual'))
    if not source['source_unique_id']:
        raise ValueError('缺少来源唯一标识')
    config_item = _find_config_item_for_source(source)
    matched_by_source = config_item is not None
    data = _payload_to_config_item_data(payload, ci_type, source)
    rekey_mapping = None
    if config_item is None:
        rekey_mapping = _find_missing_source_mapping_for_rekey(ci_type, source, data['name'])
        if rekey_mapping is not None:
            config_item = rekey_mapping.ci
            matched_by_source = True
    allow_duplicate_name = _sync_source_allows_duplicate_display_name(source)
    if not allow_duplicate_name and _sync_display_name_needs_disambiguation(ci_type, source, data, sync_context, config_item=config_item):
        _reserve_sync_display_name(ci_type, source, data, sync_context, config_item=config_item)
    if config_item is None:
        name = data.get('name')
        if name and not allow_duplicate_name:
            config_item = ConfigItem.objects.filter(name=name, ci_type=ci_type).order_by('id').first()
    if config_item is not None:
        for field in ['business_line', 'environment', 'admin_user']:
            existing_value = getattr(config_item, field)
            if existing_value not in (None, ''):
                data[field] = existing_value
        data['attributes'] = _merge_attributes_by_sync_mode(
            ci_type,
            config_item.attributes or {},
            data['attributes'],
        )
        data['attributes'] = _preserve_insignificant_numeric_values(
            config_item.attributes or {},
            data['attributes'],
        )
        data['attributes'] = _strip_resource_waterline_attributes(data['attributes'])
    resource_node = _resolve_cloud_resource_node_for_source(source)
    if resource_node:
        data['resource_node'] = resource_node
        data['attributes']['resource_node_id'] = resource_node.id
    elif config_item is not None:
        data['resource_node'] = config_item.resource_node
    data['attributes'] = _clean_sync_ip_attributes(
        data['attributes'],
        existing_attributes=config_item.attributes if config_item is not None else None,
    )
    data['attributes'] = validate_config_item_attributes_by_metadata(
        ci_type,
        data['attributes'],
        instance=config_item,
        merge_existing=config_item is not None,
    )
    tag_input_present = _payload_has_tag_input(payload)
    tag_preview = _payload_tags_for_snapshot(payload) if tag_input_present else None
    if actor is not None:
        if config_item is not None and not _user_can_manage_ci_resource(
            actor,
            ci_type_id=config_item.ci_type_id,
            business_line=config_item.business_line,
            environment=config_item.environment,
        ):
            raise ValueError('无权管理该资源范围')
        if not _user_can_manage_ci_resource(
            actor,
            ci_type_id=ci_type.id,
            business_line=data['business_line'],
            environment=data['environment'],
        ):
            raise ValueError('无权管理该资源范围')
    conflict = _detect_batch_sync_conflict(payload, ci_type, source, data, sync_context)
    if conflict is None:
        conflict = _detect_existing_sync_conflict(payload, ci_type, source, config_item, data, matched_by_source=matched_by_source)
    if conflict is not None:
        return conflict
    before = _config_item_snapshot(config_item)
    action_name = 'update' if config_item else 'create'
    after_preview = dict(before)
    after_preview.update({
        'name': data['name'],
        'ci_type': ci_type.id,
        'ci_type_name': ci_type.name,
        'business_line': data['business_line'],
        'environment': data['environment'],
        'admin_user': data['admin_user'],
        'status': data['status'],
        'resource_node': data['resource_node'].id if data.get('resource_node') else None,
        'attributes': data['attributes'],
    })
    if tag_input_present:
        after_preview['tags'] = tag_preview
    diff = _dict_diff(before, after_preview)
    if dry_run:
        relation_summary = (
            _sync_relations_from_payload(config_item, payload, job=job, source=source, operator=operator, dry_run=True)
            if config_item is not None
            else {'total': len(_sync_relation_hint_rows(payload)), 'created': 0, 'skipped': 0, 'failed': 0, 'relations': [], 'errors': []}
        )
        if relation_summary.get('total'):
            after_preview = dict(after_preview)
            after_preview['_sync_relations'] = relation_summary
        return {
            'action': action_name if diff else 'skip',
            'ci': config_item,
            'source': source,
            'before': before,
            'after': after_preview,
            'diff': diff,
            'relation_summary': relation_summary,
        }
    with transaction.atomic():
        if config_item is None:
            config_item = ConfigItem.objects.create(**data)
        elif diff:
            for field in ['name', 'ci_type', 'business_line', 'environment', 'admin_user', 'status', 'resource_node', 'attributes']:
                setattr(config_item, field, data[field])
            config_item.save()
        if tag_input_present:
            config_item.tags.set(_payload_tag_objects(payload))
        after = _config_item_snapshot(config_item)
        action_name = action_name if _dict_diff(before, after) else 'skip'
        if action_name != 'skip':
            _record_ci_change(config_item, action_name, before, after, operator=operator, source=source['source_type'])
        mapping_defaults = {
            'ci': config_item,
            'last_seen_at': timezone.now(),
            'sync_status': 'success',
            'raw_payload': payload,
        }
        if rekey_mapping is not None:
            rekey_mapping.source_unique_id = source['source_unique_id']
            rekey_mapping.ci = config_item
            rekey_mapping.last_seen_at = mapping_defaults['last_seen_at']
            rekey_mapping.sync_status = 'success'
            rekey_mapping.raw_payload = payload
            rekey_mapping.save(update_fields=[
                'source_unique_id', 'ci', 'last_seen_at', 'sync_status', 'raw_payload', 'updated_at',
            ])
            _restore_source_archive_candidates(config_item, source['source_type'], '同步来源重新发现，已恢复资源')
        else:
            CISourceMapping.objects.update_or_create(**source, defaults=mapping_defaults)
            _restore_source_archive_candidates(config_item, source['source_type'], '同步来源重新发现，已恢复资源')
        _sync_completion_issue(config_item, assigned_to=data['admin_user'])
        relation_summary = _sync_relations_from_payload(
            config_item,
            payload,
            job=job,
            source=source,
            operator=operator,
        )
    after = _config_item_snapshot(config_item)
    diff = _dict_diff(before, after)
    if relation_summary.get('total'):
        after = dict(after)
        after['_sync_relations'] = relation_summary
    return {
        'action': action_name,
        'ci': config_item,
        'source': source,
        'before': before,
        'after': after,
        'diff': diff,
        'relation_summary': relation_summary,
    }


def _items_for_sync_job(job, request_data=None):
    validate_no_sensitive_plaintext(getattr(job, 'config', {}) or {}, context='同步任务配置')
    items = collect_items_for_sync_job(job, request_data or {})
    for item in items:
        validate_no_sensitive_plaintext(item, context='同步资源数据')
    return items


def _decimal_metric_value(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


def _sync_metric_snapshots_from_payload(ci, payload, *, default_source='sync'):
    if not ci or not isinstance(payload, dict):
        return 0
    metric_rows = payload.get('_metric_snapshots')
    if not isinstance(metric_rows, list):
        return 0
    created_count = 0
    default_collected_at = timezone.now()
    for row in metric_rows:
        if not isinstance(row, dict):
            continue
        metric = str(row.get('metric') or '').strip()[:50]
        if not metric:
            continue
        usage_percent = row.get('usage_percent')
        usage_value = None
        if usage_percent not in (None, ''):
            usage_value = _decimal_metric_value(usage_percent)
        collected_at = default_collected_at
        raw_collected_at = row.get('collected_at')
        if raw_collected_at not in (None, ''):
            if isinstance(raw_collected_at, (int, float)):
                try:
                    collected_at = datetime.fromtimestamp(float(raw_collected_at), tz=timezone.get_current_timezone())
                except (OSError, OverflowError, TypeError, ValueError):
                    collected_at = default_collected_at
            else:
                parsed_collected_at = parse_datetime(str(raw_collected_at))
                if parsed_collected_at:
                    collected_at = timezone.make_aware(parsed_collected_at) if timezone.is_naive(parsed_collected_at) else parsed_collected_at
        CIResourceMetricSnapshot.objects.create(
            ci=ci,
            metric=metric,
            value=_decimal_metric_value(row.get('value')),
            unit=str(row.get('unit') or '')[:20],
            usage_percent=usage_value,
            collected_at=collected_at,
            source=str(row.get('source') or default_source or 'sync')[:50],
        )
        created_count += 1
    if created_count:
        _bump_cmdb_ledger_cache_version()
    return created_count


def _int_config(config, *keys, default=0):
    for key in keys:
        value = (config or {}).get(key)
        if value in (None, ''):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return default


def _collection_enabled(job):
    config = job.config or {}
    if 'collection_enabled' in config:
        return bool(config.get('collection_enabled'))
    if 'enabled' in config:
        return bool(config.get('enabled'))
    return job.mode == 'scheduled'


def _collection_interval_minutes(job):
    return _int_config(job.config or {}, 'interval_minutes', 'schedule_interval_minutes', 'interval', default=0)


def _collection_schedule_text(job):
    config = job.config or {}
    if config.get('schedule_label'):
        return str(config['schedule_label'])
    if config.get('cron'):
        return str(config['cron'])
    interval = _collection_interval_minutes(job)
    if interval:
        return f'每 {interval} 分钟'
    return '手动触发'


def _collection_next_run_at(job):
    if not _collection_enabled(job):
        return None
    interval = _collection_interval_minutes(job)
    if not interval:
        return None
    base_time = job.finished_at or job.started_at or job.updated_at or job.created_at
    if not base_time:
        return None
    return base_time + timezone.timedelta(minutes=interval)


def _field_mapping_count(config):
    mapping = (config or {}).get('field_mappings') or (config or {}).get('field_mapping') or []
    if isinstance(mapping, dict):
        return len(mapping)
    if isinstance(mapping, list):
        return len(mapping)
    return 0


def _build_collection_summary(user=None):
    jobs = list(CISyncJob.objects.annotate(record_count=Count('records')).order_by('-updated_at', '-id'))
    source_mapping_qs = CISourceMapping.objects.all()
    record_qs = CISyncRecord.objects.all()
    governance_record_qs = _sync_governance_record_queryset_for_user(None)
    visible_job_ids = None
    if user is not None:
        scoped_ci_ids = _apply_ci_authorization_scope(ConfigItem.objects.all(), user).values('id')
        source_mapping_qs = source_mapping_qs.filter(ci_id__in=scoped_ci_ids)
        record_qs = _sync_record_queryset_for_user(user)
        governance_record_qs = _sync_governance_record_queryset_for_user(user, include_global=True)
        visible_job_ids = set(record_qs.values_list('job_id', flat=True))
        jobs = [job for job in jobs if job.id in visible_job_ids]
    source_resource_counts = {
        row['source_type']: row['count']
        for row in source_mapping_qs.values('source_type').annotate(count=Count('ci', distinct=True))
    }
    failed_record_counts = {
        row['job_id']: row['count']
        for row in governance_record_qs.values('job_id').annotate(count=Count('id'))
    }
    success_record_counts = {
        row['job_id']: row['count']
        for row in record_qs.filter(status='success').values('job_id').annotate(count=Count('id'))
    }
    latest_failed_records = {}
    for record in governance_record_qs.select_related('job').order_by('-created_at', '-id')[:200]:
        rows = latest_failed_records.setdefault(record.job_id, [])
        if len(rows) >= 3:
            continue
        relation_summary = record.after.get('_sync_relations') if isinstance(record.after, dict) else {}
        relation_failed = int((relation_summary or {}).get('failed') or 0) if isinstance(relation_summary, dict) else 0
        relation_errors = relation_summary.get('errors') if isinstance(relation_summary, dict) and isinstance(relation_summary.get('errors'), list) else []
        first_relation_error = relation_errors[0] if relation_errors and isinstance(relation_errors[0], dict) else {}
        relation_message = ''
        if relation_failed:
            relation_message = f"自动关系失败 {relation_failed} 项"
            if first_relation_error.get('reason') == 'peer_not_found':
                relation_message += '：未找到对端资源'
        rows.append({
            'id': record.id,
            'source_unique_id': record.source_unique_id,
            'error_message': record.error_message or relation_message,
            'relation_issue': bool(relation_failed),
            'relation_issue_count': relation_failed,
            'retry_status': record.retry_status,
            'created_at': record.created_at,
        })
    total_record_counts = {
        row['job_id']: row['count']
        for row in record_qs.values('job_id').annotate(count=Count('id'))
    }

    now = timezone.now()
    job_rows = []
    source_rows = {}
    for job in jobs:
        config = job.config or {}
        item_count = configured_collection_item_count(job)
        enabled = _collection_enabled(job)
        next_run_at = _collection_next_run_at(job)
        is_due = bool(enabled and job.mode == 'scheduled' and (next_run_at is None or next_run_at <= now))
        source_type = job.source_type or 'manual'
        resource_count = source_resource_counts.get(source_type, 0)
        failed_count = failed_record_counts.get(job.id, 0)
        success_count = success_record_counts.get(job.id, 0)
        failed_samples = latest_failed_records.get(job.id, [])
        if not enabled:
            health_status = 'disabled'
        elif failed_count:
            health_status = 'failed'
        elif is_due:
            health_status = 'due'
        elif job.status in {'success', 'partial'}:
            health_status = 'healthy'
        else:
            health_status = 'pending'
        row = {
            'id': job.id,
            'name': job.name,
            'source_type': source_type,
            'mode': job.mode,
            'status': job.status,
            'dry_run': job.dry_run,
            'enabled': enabled,
            'connector': config.get('connector') or source_type,
            'resource_type': config.get('resource_type') or config.get('target_ci_type_code') or '',
            'target_ci_type_code': config.get('target_ci_type_code') or '',
            'full_sync': bool(config.get('full_sync')),
            'field_mapping_count': _field_mapping_count(config),
            'schedule_text': _collection_schedule_text(job),
            'interval_minutes': _collection_interval_minutes(job),
            'last_run_at': job.finished_at or job.started_at,
            'next_run_at': next_run_at,
            'is_due': is_due,
            'item_count': item_count,
            'record_count': total_record_counts.get(job.id, getattr(job, 'record_count', 0)),
            'success_count': success_count,
            'failed_count': failed_count,
            'failed_samples': failed_samples,
            'last_error_message': failed_samples[0]['error_message'] if failed_samples else job.error_message,
            'health_status': health_status,
            'resource_count': resource_count,
            'created_by': job.created_by,
            'updated_at': job.updated_at,
        }
        job_rows.append(row)

        source = source_rows.setdefault(source_type, {
            'source_type': source_type,
            'job_count': 0,
            'enabled_count': 0,
            'resource_count': resource_count,
            'failed_count': 0,
            'due_count': 0,
            'health_status': 'pending',
            'failed_samples': [],
            'last_run_at': None,
            'next_run_at': None,
            'status': 'pending',
        })
        source['job_count'] += 1
        source['enabled_count'] += 1 if enabled else 0
        source['failed_count'] += failed_count
        source['due_count'] += 1 if is_due else 0
        for failed_sample in failed_samples:
            if len(source['failed_samples']) < 3:
                source['failed_samples'].append({**failed_sample, 'job_id': job.id, 'job_name': job.name})
        if row['last_run_at'] and (not source['last_run_at'] or row['last_run_at'] > source['last_run_at']):
            source['last_run_at'] = row['last_run_at']
            source['status'] = row['status']
        if row['next_run_at'] and (not source['next_run_at'] or row['next_run_at'] < source['next_run_at']):
            source['next_run_at'] = row['next_run_at']
        if source['failed_count']:
            source['health_status'] = 'failed'
        elif source['due_count']:
            source['health_status'] = 'due'
        elif source['enabled_count']:
            source['health_status'] = 'healthy'
        else:
            source['health_status'] = 'disabled'

    sources = sorted(source_rows.values(), key=lambda item: (-item['resource_count'], item['source_type']))
    unhealthy_count = sum(1 for item in job_rows if item['health_status'] in {'failed', 'due'})
    return {
        'summary': {
            'job_count': len(job_rows),
            'source_count': len(sources),
            'scheduled_count': sum(1 for item in job_rows if item['mode'] == 'scheduled'),
            'enabled_count': sum(1 for item in job_rows if item['enabled']),
            'due_count': sum(1 for item in job_rows if item['is_due']),
            'failed_count': sum(item['failed_count'] for item in job_rows),
            'unhealthy_count': unhealthy_count,
            'collected_resource_count': sum(item['resource_count'] for item in sources),
        },
        'sources': sources,
        'jobs': job_rows,
    }


def _due_collection_jobs():
    now = timezone.now()
    due_jobs = []
    seen_job_keys = set()
    for job in CISyncJob.objects.filter(mode='scheduled').order_by('-updated_at', '-id'):
        config = job.config or {}
        account_key = str(
            config.get('cloud_account_id')
            or config.get('multicloud_account_id')
            or config.get('source_account')
            or config.get('account_name')
            or config.get('account_id')
            or ''
        ).strip()
        if config.get('account_ref_field') in {'cloud_account_id', 'multicloud_account_id'} and not account_key:
            continue
        if not _collection_enabled(job):
            continue
        job_key = (job.source_type, account_key) if account_key else (job.source_type, job.id)
        if job_key in seen_job_keys:
            continue
        seen_job_keys.add(job_key)
        next_run_at = _collection_next_run_at(job)
        if next_run_at is not None and next_run_at > now:
            continue
        due_jobs.append(job)
    return due_jobs


def run_due_collection_jobs(*, limit=50, operator='system-scheduler', user=None):
    due_jobs = _due_collection_jobs()[:max(1, min(int(limit), 50))]
    executed = []
    total_summary = defaultdict(int)
    for job in due_jobs:
        batch_id = uuid.uuid4().hex
        try:
            _mark_sync_job_collection_running(job)
            items = _items_for_sync_job(job, {})
            result = _run_sync_items(job, items, operator=operator, user=user, batch_id=batch_id)
            summary = result['summary']
            status_text = job.status
            error_message = ''
        except Exception as exc:
            result = _mark_sync_job_collection_failed(job, exc, batch_id=batch_id)
            summary = result['summary']
            status_text = 'failed'
            error_message = result['error_message']
        for key, value in summary.items():
            total_summary[key] += int(value or 0)
        executed.append({
            'id': job.id,
            'name': job.name,
            'source_type': job.source_type,
            'status': status_text,
            'summary': summary,
            'error_message': error_message,
        })
    return {
        'executed_count': len(executed),
        'summary': dict(total_summary),
        'jobs': executed,
    }


IMPORT_TOP_LEVEL_FIELDS = {
    'name',
    'resource_name',
    'ci_type',
    'ci_type_name',
    'ci_type_code',
    'type_name',
    'resource_type',
    'business_line',
    'department',
    'dept',
    'environment',
    'admin_user',
    'owner',
    'status',
    'source_type',
    'source_account',
    'source_region',
    'source_unique_id',
    'external_id',
    'instance_id',
    'icon',
    'color',
    'description',
}

IMPORT_COLUMN_ALIASES = {
    '资产名称': 'name',
    '名称': 'name',
    '模型': 'ci_type_name',
    '资产类型': 'ci_type_name',
    '模型编码': 'ci_type_code',
    '资产类型编码': 'ci_type_code',
    '唯一标识': 'source_unique_id',
    '来源唯一 ID': 'source_unique_id',
    '业务线': 'business_line',
    '部门': 'department',
    '环境': 'environment',
    '负责人': 'admin_user',
    '状态': 'status',
    '来源': 'source_type',
    '来源账号': 'source_account',
    '来源区域': 'source_region',
    '私网 IP': 'private_ip',
    '公网 IP': 'public_ip',
    'IP地址': 'ip_address',
    '规格': 'specification',
}


def _import_field_name_map():
    field_rows = CIField.objects.filter(is_active=True).exclude(name='').values_list('name', 'code')
    field_map = {}
    duplicate_names = set()
    for name, code in field_rows:
        if name in field_map and field_map[name] != code:
            duplicate_names.add(name)
            continue
        field_map[name] = code
    return {name: code for name, code in field_map.items() if name not in duplicate_names}


def _normalize_import_row(row, field_name_map=None):
    validate_no_sensitive_plaintext(row or {}, context='导入资源数据')
    payload = {}
    attributes = {}
    for raw_key, raw_value in (row or {}).items():
        key = str(raw_key or '').strip()
        if not key:
            continue
        if key.startswith('__') or key.startswith('#'):
            continue
        key = IMPORT_COLUMN_ALIASES.get(key, field_name_map.get(key, key) if field_name_map else key)
        value = raw_value
        if isinstance(value, str):
            value = value.strip()
        if value in (None, ''):
            continue
        if key == 'attributes':
            if isinstance(value, dict):
                attributes.update(value)
            else:
                try:
                    parsed = json.loads(value)
                except (TypeError, ValueError):
                    attributes[key] = value
                else:
                    if isinstance(parsed, dict):
                        attributes.update(parsed)
                    else:
                        attributes[key] = value
            continue
        if key in IMPORT_TOP_LEVEL_FIELDS:
            payload[key] = value
        else:
            attributes[key] = value
    payload['attributes'] = normalize_ci_attributes({**attributes, **normalize_ci_attributes(payload.get('attributes') or {})})
    return payload


def _parse_csv_import_items(text):
    if not text or not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff').strip()))
    if not reader.fieldnames:
        raise ValueError('CSV 第一行必须包含表头')
    field_name_map = _import_field_name_map()
    return [_normalize_import_row(row, field_name_map) for row in reader]


def _items_for_bulk_import(request_data=None):
    request_data = request_data or {}
    items = request_data.get('items')
    if items is None:
        text = request_data.get('text') or request_data.get('csv_text') or ''
        import_format = (request_data.get('format') or '').strip().lower()
        if import_format == 'csv' or text.lstrip().splitlines()[:1] and ',' in text.lstrip().splitlines()[0]:
            items = _parse_csv_import_items(text)
        elif text.strip():
            try:
                parsed = json.loads(text)
            except ValueError as exc:
                raise ValueError('导入内容需要是 JSON 数组或带表头的 CSV 文本') from exc
            items = parsed
        else:
            items = []
    if not isinstance(items, list):
        raise ValueError('导入数据必须是数组')
    if len(items) > 500:
        raise ValueError('单次最多导入 500 条资源')
    field_name_map = _import_field_name_map()
    normalized_items = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f'第 {index} 条导入数据必须是对象')
        normalized_items.append(_normalize_import_row(item, field_name_map))
    return normalized_items


def _attribute_value_for_export(value):
    if value in (None, ''):
        return ''
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _config_items_export_csv(items):
    items = list(items or ())
    field_rows = []
    ci_type_ids = {item.ci_type_id for item in items if item.ci_type_id}
    if ci_type_ids:
        field_rows = list(
            CIField.objects.filter(ci_type_id__in=ci_type_ids, is_active=True, is_display=True)
            .select_related('ci_type')
            .order_by('ci_type__name', 'sort_order', 'id')
        )
    seen_field_codes = set()
    export_fields = []
    for field in field_rows:
        if field.code in seen_field_codes:
            continue
        seen_field_codes.add(field.code)
        export_fields.append(field)

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    headers = [
        'ID',
        '模型',
        '名称',
        '业务线',
        '环境',
        '状态',
        '负责人',
        '部门',
        '来源',
        '来源账号',
        '来源区域',
        '来源唯一ID',
        'IP地址',
        '更新时间',
    ]
    headers.extend([field.name for field in export_fields])
    headers.append('扩展属性JSON')
    writer.writerow(headers)

    environment_labels = dict(ConfigItem._meta.get_field('environment').choices or ())
    status_labels = dict(ConfigItem._meta.get_field('status').choices or ())
    for item in items:
        attributes = normalize_ci_attributes(item.attributes or {})
        source_rows = _source_rows_for_ci(item)
        primary_source = source_rows[0] if source_rows else {}
        source_type = primary_source.get('source_type') or attributes.get('source_type') or attributes.get('source') or 'manual'
        source_account = primary_source.get('source_account') or attributes.get('source_account') or attributes.get('account') or ''
        source_region = primary_source.get('source_region') or attributes.get('source_region') or attributes.get('region') or ''
        source_unique_id = (
            primary_source.get('source_unique_id')
            or attributes.get('source_unique_id')
            or attributes.get('external_id')
            or attributes.get('instance_id')
            or ''
        )
        ip_address = attributes.get('ip_address') or attributes.get('private_ip') or attributes.get('public_ip') or attributes.get('ip') or ''
        department = attributes.get('department') or attributes.get('dept') or ''
        row = [
            item.id,
            resolve_config_item_type_meta(item)['name'],
            item.name,
            item.business_line,
            environment_labels.get(item.environment, item.environment),
            status_labels.get(item.status, item.status),
            item.admin_user,
            department,
            source_type,
            source_account,
            source_region,
            source_unique_id,
            ip_address,
            item.updated_at.strftime('%Y-%m-%d %H:%M:%S') if item.updated_at else '',
        ]
        row.extend(_attribute_value_for_export(attributes.get(field.code)) for field in export_fields)
        row.append(json.dumps(attributes, ensure_ascii=False))
        writer.writerow(row)

    return output.getvalue()


def _config_items_export_response(items):
    response = HttpResponse(_config_items_export_csv(items), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="cmdb-config-items.csv"'
    return response


def _safe_export_filename(value, fallback):
    normalized = re.sub(r'[^0-9A-Za-z._-]+', '-', str(value or '')).strip('.-')
    return normalized or fallback


def _config_items_export_by_type_response(items):
    grouped_items = defaultdict(list)
    for item in items:
        grouped_items[item.ci_type_id].append(item)
    if len(grouped_items) <= 1:
        return _config_items_export_response(next(iter(grouped_items.values()), []))

    output = io.BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr(
            '使用说明.txt',
            '资产按模型拆分为独立 CSV，避免不同模型字段混在同一张表中。\n'.encode('utf-8'),
        )
        for ci_type_id, type_items in grouped_items.items():
            ci_type = type_items[0].ci_type if type_items else None
            filename = _safe_export_filename(getattr(ci_type, 'code', ''), f'ci-type-{ci_type_id or "unknown"}')
            archive.writestr(f'{filename}.csv', _config_items_export_csv(type_items).encode('utf-8'))
    response = HttpResponse(output.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="cmdb-config-items-by-type.zip"'
    return response


def _sample_value_for_import_field(field):
    if field.code in {'private_ip', 'ip_address', 'public_ip', 'ip'} or field.field_type == 'ip':
        return '10.0.0.8'
    if field.field_type == 'integer':
        return '4'
    if field.field_type in {'float', 'decimal'}:
        return '4.0'
    if field.field_type == 'boolean':
        return 'true'
    if field.field_type == 'date':
        return timezone.now().date().isoformat()
    if field.field_type == 'datetime':
        return timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    if field.field_type == 'json':
        return '{}'
    if field.options:
        first_option = field.options[0] if isinstance(field.options, list) and field.options else ''
        if isinstance(first_option, dict):
            return first_option.get('value') or first_option.get('label') or ''
        return first_option
    return f'{field.code}_value'


def _config_item_import_template_response(ci_type=None):
    base_fields = [
        ('资产名称', 'name'),
        ('模型', 'ci_type_name'),
        ('唯一标识', 'source_unique_id'),
        ('业务线', 'business_line'),
        ('环境', 'environment'),
        ('负责人', 'admin_user'),
        ('部门', 'department'),
        ('状态', 'status'),
        ('来源', 'source_type'),
        ('来源账号', 'source_account'),
        ('来源区域', 'source_region'),
        ('私网 IP', 'private_ip'),
        ('公网 IP', 'public_ip'),
        ('规格', 'specification'),
    ]
    if ci_type:
        field_qs = ci_type.fields.filter(is_active=True).filter(Q(required=True) | Q(is_display=True)).order_by('sort_order', 'id')
    else:
        field_qs = CIField.objects.none()
    dynamic_fields = []
    seen_codes = {field_code for _, field_code in base_fields}
    for field in field_qs:
        if field.code in seen_codes:
            continue
        seen_codes.add(field.code)
        dynamic_fields.append(field)

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    headers = [*[label for label, _ in base_fields], *[field.name for field in dynamic_fields]]
    writer.writerow(headers)

    sample_type = ci_type or CIType.objects.order_by('id').first()
    sample_row = {
        'ci_type_name': sample_type.name if sample_type else '云主机(ECS)',
        'name': 'ecs-prod-01',
        'source_unique_id': 'i-example-001',
        'business_line': 'core',
        'department': '基础架构部',
        'environment': 'prod',
        'admin_user': 'ops',
        'status': 'active',
        'source_type': 'manual_import',
        'source_account': 'default',
        'source_region': 'cn-shanghai',
        'private_ip': '10.0.0.8',
        'public_ip': '',
        'specification': '',
    }
    for field in dynamic_fields:
        sample_row[field.code] = _sample_value_for_import_field(field)
    header_to_code = {label: field_code for label, field_code in base_fields}
    header_to_code.update({field.name: field.code for field in dynamic_fields})
    writer.writerow([sample_row.get(header_to_code[header], '') for header in headers])

    filename = f"cmdb-import-template-{ci_type.code}.csv" if ci_type and ci_type.code else 'cmdb-import-template.csv'
    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _config_item_import_template_archive_response(ci_types):
    output = io.BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr(
            '使用说明.txt',
            '每个 CSV 对应一个资产模型。请填写对应模型的文件后分别导入，避免不同模型字段混填。\n'.encode('utf-8'),
        )
        for ci_type in ci_types:
            response = _config_item_import_template_response(ci_type)
            filename = _safe_export_filename(ci_type.code, f'ci-type-{ci_type.id}')
            archive.writestr(f'{filename}.csv', response.content)
    response = HttpResponse(output.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="cmdb-import-templates-by-type.zip"'
    return response


def _impact_node_payload(ci, relation, direction, depth):
    return {
        'id': ci.id,
        'name': ci.name,
        'ci_type': ci.ci_type_id,
        'ci_type_name': normalize_ci_type_name(ci.ci_type.name if ci.ci_type_id else ''),
        'business_line': ci.business_line,
        'environment': ci.environment,
        'environment_display': ci.get_environment_display() if ci.environment else '',
        'admin_user': ci.admin_user,
        'status': ci.status,
        'status_display': ci.get_status_display(),
        'depth': depth,
        'relation_id': relation.id,
        'relation_type': relation.relation_type,
        'relation_label': relation.get_relation_type_display(),
        'direction': direction,
        'source_id': relation.source_id,
        'source_name': relation.source.name,
        'target_id': relation.target_id,
        'target_name': relation.target.name,
    }


def _walk_relation_impact(ci, direction, max_depth=2, visible_ci_ids=None):
    visited = {ci.id}
    frontier = {ci.id}
    nodes = []
    relation_type_counts = defaultdict(int)
    depth_counts = defaultdict(int)

    for depth in range(1, max_depth + 1):
        if not frontier:
            break
        if direction == 'downstream':
            relation_qs = CIRelation.objects.filter(source_id__in=frontier)
            related_attr = 'target'
        else:
            relation_qs = CIRelation.objects.filter(target_id__in=frontier)
            related_attr = 'source'
        next_frontier = set()
        for relation in relation_qs.select_related('source', 'source__ci_type', 'target', 'target__ci_type').order_by('id'):
            related = getattr(relation, related_attr)
            if visible_ci_ids is not None and related.id not in visible_ci_ids:
                continue
            if related.id in visited:
                continue
            visited.add(related.id)
            next_frontier.add(related.id)
            relation_type_counts[relation.relation_type] += 1
            depth_counts[str(depth)] += 1
            nodes.append(_impact_node_payload(related, relation, direction, depth))
        frontier = next_frontier

    return {
        'nodes': nodes,
        'count': len(nodes),
        'relation_type_counts': dict(relation_type_counts),
        'depth_counts': dict(depth_counts),
    }


def _config_item_delete_impact(ci, max_depth=2, user=None):
    relations = (
        CIRelation.objects.filter(Q(source=ci) | Q(target=ci))
        .select_related('source', 'source__ci_type', 'target', 'target__ci_type')
        .order_by('id')
    )
    relation_samples = []
    for relation in relations[:10]:
        related = relation.target if relation.source_id == ci.id else relation.source
        relation_samples.append({
            'id': relation.id,
            'direction': 'outgoing' if relation.source_id == ci.id else 'incoming',
            'relation_type': relation.relation_type,
            'relation_label': relation.get_relation_type_display(),
            'related_ci_id': related.id,
            'related_ci_name': related.name,
            'related_ci_type': related.ci_type.name if related.ci_type_id else '',
        })

    blocking_counts = {
        'relations': relations.count(),
        'source_mappings': ci.source_mappings.count(),
        'open_completion_issues': ci.completion_issues.exclude(status__in=['resolved', 'ignored']).count(),
        'pending_archive_candidates': ci.archive_candidates.filter(status='pending').count(),
        'cost_records': ci.costs.count(),
    }
    warning_counts = {
        'sync_records': ci.sync_records.count(),
        'change_logs': ci.change_logs.count(),
    }
    blocking_total = sum(blocking_counts.values())
    warning_total = sum(warning_counts.values())
    visible_ci_ids = None
    if user is not None:
        visible_ci_ids = set(_apply_ci_authorization_scope(ConfigItem.objects.all(), user).values_list('id', flat=True))
        visible_ci_ids.add(ci.id)
    max_depth = min(max(int(max_depth or 2), 1), 5)
    upstream = _walk_relation_impact(ci, 'upstream', max_depth=max_depth, visible_ci_ids=visible_ci_ids)
    downstream = _walk_relation_impact(ci, 'downstream', max_depth=max_depth, visible_ci_ids=visible_ci_ids)
    relation_type_counts = defaultdict(int)
    depth_counts = defaultdict(int)
    for bucket in [upstream, downstream]:
        for key, value in bucket['relation_type_counts'].items():
            relation_type_counts[key] += value
        for key, value in bucket['depth_counts'].items():
            depth_counts[key] += value
    return {
        'ci_id': ci.id,
        'ci_name': ci.name,
        'blocking_counts': blocking_counts,
        'warning_counts': warning_counts,
        'relation_samples': relation_samples,
        'blocking_total': blocking_total,
        'warning_total': warning_total,
        'can_delete_without_force': blocking_total == 0,
        'max_depth': max_depth,
        'upstream': upstream['nodes'],
        'downstream': downstream['nodes'],
        'impact_summary': {
            'upstream_count': upstream['count'],
            'downstream_count': downstream['count'],
            'total_related_count': upstream['count'] + downstream['count'],
            'relation_type_counts': dict(relation_type_counts),
            'depth_counts': dict(depth_counts),
        },
    }


def _sync_source_scope_key(source):
    return (
        source.get('source_type') or '',
        source.get('source_account') or '',
        source.get('source_region') or '',
    )


def _sync_source_identity_key(source):
    return (*_sync_source_scope_key(source), source.get('source_unique_id') or '')


def _sync_conflict_payload(reason, *, ci=None, source=None, payload=None, before=None, after=None):
    source = source or {}
    return {
        'action': 'conflict',
        'ci': ci,
        'source': source,
        'before': before or (_config_item_snapshot(ci) if ci is not None else {}),
        'after': after or (payload if isinstance(payload, dict) else {'payload': payload}),
        'diff': {},
        'error_message': reason,
    }


def _source_mapping_scope_conflicts(ci, source):
    if ci is None:
        return []
    return [
        mapping
        for mapping in ci.source_mappings.all()
        if (
            (mapping.source_type or '') == (source.get('source_type') or '')
            and (mapping.source_account or '') == (source.get('source_account') or '')
            and (mapping.source_region or '') == (source.get('source_region') or '')
            and (mapping.source_unique_id or '') != (source.get('source_unique_id') or '')
        )
    ]


def _detect_existing_sync_conflict(payload, ci_type, source, config_item, data, *, matched_by_source=False):
    name = data.get('name') or payload.get('name') or payload.get('resource_name') or ''
    if not name:
        return None
    if _sync_source_allows_duplicate_display_name(source):
        return None
    same_name_qs = ConfigItem.objects.filter(name=name, ci_type=ci_type).prefetch_related('source_mappings').order_by('id')
    if config_item is not None and matched_by_source:
        name_peer = same_name_qs.exclude(id=config_item.id).first()
        if name_peer is not None:
            return _sync_conflict_payload(
                f"来源 {source['source_unique_id']} 已绑定 {config_item.name}，但本次数据名称命中另一个资源 {name_peer.name}，需要人工确认来源映射。",
                ci=config_item,
                source=source,
                payload=payload,
                before=_config_item_snapshot(config_item),
                after={**data, 'ci_type': ci_type.id, 'ci_type_name': ci_type.name},
            )
        return None

    same_name_items = list(same_name_qs[:2])
    if len(same_name_items) > 1:
        return _sync_conflict_payload(
            f"资源名称 {name} 在模型 {ci_type.name} 下匹配多个配置项，无法自动确定来源 {source['source_unique_id']} 应绑定哪一个。",
            source=source,
            payload=payload,
        )
    matched_ci = config_item or (same_name_items[0] if same_name_items else None)
    if matched_ci is not None:
        conflicts = _source_mapping_scope_conflicts(matched_ci, source)
        if conflicts:
            mapping = conflicts[0]
            return _sync_conflict_payload(
                f"资源 {matched_ci.name} 已绑定同来源范围的唯一标识 {mapping.source_unique_id}，本次来源唯一标识为 {source['source_unique_id']}，需要人工合并或拆分。",
                ci=matched_ci,
                source=source,
                payload=payload,
                before=_config_item_snapshot(matched_ci),
                after={**data, 'ci_type': ci_type.id, 'ci_type_name': ci_type.name},
            )
    return None


def _detect_batch_sync_conflict(payload, ci_type, source, data, context):
    if context is None:
        return None
    source_key = _sync_source_identity_key(source)
    name_key = (ci_type.id, data.get('name') or '')
    seen_sources = context.setdefault('sources', {})
    seen_names = context.setdefault('names', {})
    if source_key in seen_sources:
        previous = seen_sources[source_key]
        return _sync_conflict_payload(
            f"同一批次重复出现来源唯一标识 {source['source_unique_id']}，已先匹配资源 {previous.get('name') or '-'}，请拆分或去重后再同步。",
            source=source,
            payload=payload,
        )
    allow_duplicate_name = _sync_source_allows_duplicate_display_name(source)
    if not allow_duplicate_name and name_key[1] and name_key in seen_names:
        previous = seen_names[name_key]
        previous_source = previous.get('source') or {}
        if _sync_source_identity_key(previous_source) != source_key:
            return _sync_conflict_payload(
                f"同一批次中资源名称 {name_key[1]} 对应多个来源唯一标识：{previous_source.get('source_unique_id') or '-'} 与 {source['source_unique_id']}。",
                source=source,
                payload=payload,
            )
    seen_sources[source_key] = {'name': data.get('name'), 'payload': payload, 'source': source}
    if not allow_duplicate_name and name_key[1]:
        seen_names[name_key] = {'name': data.get('name'), 'payload': payload, 'source': source}
    return None


def _sync_job_full_sync_enabled(job):
    config = job.config or {}
    for key in ['full_sync', 'detect_missing', 'missing_means_archive_candidate']:
        if key in config:
            return _to_bool(config.get(key))
    return job.source_type in {'vsphere_vm'}


def _sync_job_missing_marks_ci_offline(job):
    config = job.config or {}
    if 'missing_marks_offline' in config:
        return _to_bool(config.get('missing_marks_offline'))
    return job.source_type in {'vsphere_vm'}


def _sync_job_stale_missing_days(job):
    config = job.config or {}
    for key in ['stale_missing_after_days', 'stale_after_days', 'missing_after_days']:
        value = config.get(key)
        if value in (None, ''):
            continue
        try:
            days = int(value)
        except (TypeError, ValueError):
            continue
        if days > 0:
            return days
    return 0


def _source_mapping_in_seen_scope(mapping, seen_scopes, job=None):
    if getattr(job, 'source_type', '') == 'vsphere_vm' and mapping.source_type == 'vsphere_vm':
        seen_accounts = {(scope[0], scope[1]) for scope in seen_scopes if scope[0] == 'vsphere_vm' and scope[1]}
        return (mapping.source_type or '', mapping.source_account or '') in seen_accounts
    return (mapping.source_type or '', mapping.source_account or '', mapping.source_region or '') in seen_scopes


def _source_mapping_seen_in_full_sync(job, mapping, seen_sources, seen_identities):
    if getattr(job, 'source_type', '') == 'vsphere_vm' and mapping.source_type == 'vsphere_vm':
        mapping_key = (mapping.source_type or '', mapping.source_account or '', mapping.source_unique_id or '')
        return any(
            (
                source.get('source_type') or '',
                source.get('source_account') or '',
                source.get('source_unique_id') or '',
            ) == mapping_key
            for source in seen_sources
        )
    source = {
        'source_type': mapping.source_type,
        'source_account': mapping.source_account,
        'source_region': mapping.source_region,
        'source_unique_id': mapping.source_unique_id,
    }
    return _sync_source_identity_key(source) in seen_identities


def _archive_candidate_payload_for_mapping(mapping, reason=''):
    reason = reason or f'全量同步未发现来源资源 {mapping.source_unique_id}'
    return {
        'ci_id': mapping.ci_id,
        'ci_name': mapping.ci.name if mapping.ci_id else '',
        'ci_type_name': mapping.ci.ci_type.name if mapping.ci_id and mapping.ci.ci_type_id else '',
        'source_type': mapping.source_type,
        'source_account': mapping.source_account,
        'source_region': mapping.source_region,
        'source_unique_id': mapping.source_unique_id,
        'reason': reason,
        'last_seen_at': mapping.last_seen_at.isoformat() if mapping.last_seen_at else '',
    }


def _source_identity_for_mapping(mapping):
    return (mapping.source_type or '', mapping.source_account or '', mapping.source_region or '', mapping.source_unique_id or '')


def _missing_source_mappings_for_full_sync(job, seen_sources, include_existing_candidates=False):
    if not _sync_job_full_sync_enabled(job) or not seen_sources:
        return []
    seen_scopes = {_sync_source_scope_key(source) for source in seen_sources}
    seen_identities = {_sync_source_identity_key(source) for source in seen_sources}
    source_types = {scope[0] for scope in seen_scopes if scope[0]}
    mappings = CISourceMapping.objects.select_related('ci', 'ci__ci_type').filter(source_type__in=source_types)
    missing = []
    for mapping in mappings:
        if not _source_mapping_in_seen_scope(mapping, seen_scopes, job=job):
            continue
        if _source_mapping_seen_in_full_sync(job, mapping, seen_sources, seen_identities):
            continue
        if not include_existing_candidates and CIArchiveCandidate.objects.filter(ci=mapping.ci, source_type=mapping.source_type, status__in=['pending', 'ignored', 'confirmed', 'archived']).exists():
            continue
        missing.append(mapping)
    return missing


def _stale_source_mappings_for_job(job, exclude_identities=None):
    stale_days = _sync_job_stale_missing_days(job)
    if not stale_days:
        return []

    cutoff = timezone.now() - timezone.timedelta(days=stale_days)
    config = job.config or {}
    source_account = (config.get('source_account') or '').strip()
    source_region = (config.get('source_region') or '').strip()
    queryset = CISourceMapping.objects.select_related('ci', 'ci__ci_type').filter(
        source_type=job.source_type,
        last_seen_at__lt=cutoff,
    )
    if source_account:
        queryset = queryset.filter(source_account=source_account)
    if source_region:
        queryset = queryset.filter(source_region=source_region)

    exclude_identities = set(exclude_identities or [])
    stale = []
    for mapping in queryset:
        if _source_identity_for_mapping(mapping) in exclude_identities:
            continue
        if CIArchiveCandidate.objects.filter(ci=mapping.ci, source_type=mapping.source_type, status__in=['pending', 'ignored', 'confirmed', 'archived']).exists():
            continue
        stale.append(mapping)
    return stale


def _preview_archive_candidates_for_full_sync(job, seen_sources):
    records = []
    for mapping in _missing_source_mappings_for_full_sync(job, seen_sources):
        records.append({
            'action': 'archive_candidate',
            'source_unique_id': mapping.source_unique_id,
            'before': _config_item_snapshot(mapping.ci),
            'after': _archive_candidate_payload_for_mapping(mapping),
            'diff': {},
        })
    return records


def _preview_archive_candidates_for_stale_mappings(job, exclude_identities=None):
    records = []
    stale_days = _sync_job_stale_missing_days(job)
    for mapping in _stale_source_mappings_for_job(job, exclude_identities=exclude_identities):
        records.append({
            'action': 'archive_candidate',
            'source_unique_id': mapping.source_unique_id,
            'before': _config_item_snapshot(mapping.ci),
            'after': _archive_candidate_payload_for_mapping(
                mapping,
                reason=f'来源资源 {mapping.source_unique_id} 已超过 {stale_days} 天未同步',
            ),
            'diff': {},
        })
    return records


def _create_archive_candidates_for_full_sync(job, seen_sources, batch_id=''):
    records = []
    for mapping in _missing_source_mappings_for_full_sync(job, seen_sources, include_existing_candidates=True):
        payload = _archive_candidate_payload_for_mapping(mapping)
        before_snapshot = _config_item_snapshot(mapping.ci)
        candidate = CIArchiveCandidate.objects.filter(
            ci=mapping.ci,
            source_type=mapping.source_type,
            status__in=['pending', 'ignored', 'confirmed', 'archived'],
        ).order_by('-updated_at', '-id').first()
        if not candidate:
            candidate = CIArchiveCandidate.objects.create(
                ci=mapping.ci,
                source_type=mapping.source_type,
                reason=payload['reason'],
                last_seen_at=mapping.last_seen_at,
                status='pending',
            )
        if mapping.sync_status != 'missing':
            mapping.sync_status = 'missing'
            mapping.save(update_fields=['sync_status', 'updated_at'])
        if _sync_job_missing_marks_ci_offline(job) and mapping.ci_id and mapping.ci.status != 'offline':
            mapping.ci.status = 'offline'
            attrs = dict(mapping.ci.attributes or {})
            attrs['sync_status'] = 'missing'
            attrs['missing_source_unique_id'] = mapping.source_unique_id
            attrs['missing_detected_at'] = timezone.now().isoformat()
            mapping.ci.attributes = attrs
            mapping.ci.save(update_fields=['status', 'attributes', 'updated_at'])
        records.append(CISyncRecord.objects.create(
            job=job,
            ci=mapping.ci,
            batch_id=batch_id,
            action='archive_candidate',
            source_unique_id=mapping.source_unique_id,
            before=before_snapshot,
            after={**payload, 'candidate_id': candidate.id},
            diff={},
            status='success',
        ))
    return records


def _create_archive_candidates_for_stale_mappings(job, exclude_identities=None, batch_id=''):
    records = []
    stale_days = _sync_job_stale_missing_days(job)
    for mapping in _stale_source_mappings_for_job(job, exclude_identities=exclude_identities):
        payload = _archive_candidate_payload_for_mapping(
            mapping,
            reason=f'来源资源 {mapping.source_unique_id} 已超过 {stale_days} 天未同步',
        )
        candidate = CIArchiveCandidate.objects.create(
            ci=mapping.ci,
            source_type=mapping.source_type,
            reason=payload['reason'],
            last_seen_at=mapping.last_seen_at,
            status='pending',
        )
        mapping.sync_status = 'missing'
        mapping.save(update_fields=['sync_status', 'updated_at'])
        records.append(CISyncRecord.objects.create(
            job=job,
            ci=mapping.ci,
            batch_id=batch_id,
            action='archive_candidate',
            source_unique_id=mapping.source_unique_id,
            before=_config_item_snapshot(mapping.ci),
            after={**payload, 'candidate_id': candidate.id},
            diff={},
            status='success',
        ))
    return records


def _preview_sync_items(job, items, user=None):
    results = []
    preview_items = []
    summary = defaultdict(int)
    seen_sources = []
    sync_context = {'sources': {}, 'names': {}}
    for payload in items:
        try:
            validate_no_sensitive_plaintext(payload, context='同步资源数据')
            result = _upsert_config_item_from_payload(payload, job=job, dry_run=True, actor=user, sync_context=sync_context)
            if result['action'] != 'conflict':
                seen_sources.append(result['source'])
            summary[result['action']] += 1
            relation_summary = result.get('relation_summary') or {}
            for key in ('created', 'skipped', 'failed'):
                if relation_summary.get(key):
                    summary[f'relation_{key}'] += relation_summary[key]
            row = {
                'action': result['action'],
                'source_unique_id': result['source']['source_unique_id'],
                'before': result['before'],
                'after': result['after'],
                'diff': result['diff'],
                'error_message': result.get('error_message', ''),
            }
            results.append(row)
            preview_items.append({'payload': payload, 'result': result, 'row': row})
        except (ValueError, ValidationError) as exc:
            summary['fail'] += 1
            results.append({
                'action': 'fail',
                'error_message': str(exc),
                'after': {'blocked_sensitive_payload': True} if isinstance(exc, ValidationError) else payload,
            })
    batch_relation_summary = _preview_batch_sync_relations(preview_items, job=job)
    for key, value in batch_relation_summary.items():
        summary[key] += value
    archive_records = _preview_archive_candidates_for_full_sync(job, seen_sources)
    if archive_records:
        summary['archive_candidate'] += len(archive_records)
        results.extend(archive_records)
    full_sync_archive_identities = {
        (
            (record.get('after') or {}).get('source_type') or '',
            (record.get('after') or {}).get('source_account') or '',
            (record.get('after') or {}).get('source_region') or '',
            record.get('source_unique_id') or '',
        )
        for record in archive_records
    }
    stale_records = _preview_archive_candidates_for_stale_mappings(job, exclude_identities=full_sync_archive_identities)
    if stale_records:
        summary['archive_candidate'] += len(stale_records)
        results.extend(stale_records)
    return {'summary': dict(summary), 'records': results}


def _sync_collection_error_message(exc):
    message = str(exc) or exc.__class__.__name__
    lower_message = message.lower()
    if 'invalidaccesskeyid.notfound' in lower_message:
        prefix = '云账号 AccessKey 不存在或已被禁用'
    elif 'apigw.0301' in lower_message or 'incorrect iam authentication information' in lower_message or 'get token error' in lower_message:
        prefix = '华为云账号认证信息不匹配，请核对当前地域的 Project ID、AK/SK 以及 IAM 用户项目授权'
    elif 'http status: 403' in lower_message or 'forbidden' in lower_message or 'not authorized' in lower_message:
        prefix = '云账号缺少该同步任务所需的云产品/API 权限'
    elif 'getaddrinfo failed' in lower_message or 'name or service not known' in lower_message:
        prefix = '同步源地址解析失败，请检查账号地域、私有云地址或本机 DNS'
    elif 'timeout' in lower_message or 'timed out' in lower_message or '请求超时' in lower_message:
        prefix = '同步源请求超时，请检查网络连通性或稍后重试'
    else:
        prefix = '同步源采集失败'
    return f'{prefix}：{message}'[:1200]


def _mark_sync_job_collection_failed(job, exc, batch_id=None):
    message = _sync_collection_error_message(exc)
    summary = {'fail': 1}
    now = timezone.now()
    config = job.config if isinstance(job.config, dict) else {}
    job.status = 'failed'
    job.started_at = job.started_at or now
    job.finished_at = now
    job.summary = summary
    job.error_message = message
    job.save(update_fields=['status', 'started_at', 'finished_at', 'summary', 'error_message', 'updated_at'])
    record = CISyncRecord.objects.create(
        job=job,
        batch_id=batch_id or uuid.uuid4().hex,
        action='fail',
        source_unique_id='collection',
        after={
            'collection_failed': True,
            'source_type': job.source_type,
            'source_account': config.get('source_account') or config.get('account_name') or '',
            'source_region': config.get('source_region') or config.get('region_id') or config.get('region') or '',
        },
        status='failed',
        error_message=message,
    )
    return {'summary': summary, 'records': [record], 'error_message': message}


def _mark_sync_job_collection_running(job):
    job.status = 'running'
    job.started_at = timezone.now()
    job.finished_at = None
    job.error_message = ''
    job.save(update_fields=['status', 'started_at', 'finished_at', 'error_message', 'updated_at'])


def _mark_collection_failures_recovered(job, operator=''):
    failures = CISyncRecord.objects.filter(
        job=job,
        status='failed',
        source_unique_id='collection',
    ).exclude(retry_status='success')
    recovered_count = failures.update(
        retry_status='success',
        retry_count=F('retry_count') + 1,
        last_retried_at=timezone.now(),
        retried_by=operator or 'system-scheduler',
        retry_result='collection_resync',
    )
    if recovered_count:
        _bump_cmdb_ledger_cache_version()
    return recovered_count


def _run_sync_items(job, items, operator='', user=None, create_missing_archive_candidates=True, batch_id=None):
    summary = defaultdict(int)
    records = []
    batch_id = batch_id or uuid.uuid4().hex
    seen_sources = []
    relation_retry_candidates = []
    sync_context = {'sources': {}, 'names': {}}
    _mark_sync_job_collection_running(job)
    for payload in items:
        try:
            validate_no_sensitive_plaintext(payload, context='同步资源数据')
            result = _upsert_config_item_from_payload(payload, job=job, operator=operator, actor=user, sync_context=sync_context)
            if result['action'] != 'conflict':
                seen_sources.append(result['source'])
                metric_count = _sync_metric_snapshots_from_payload(
                    result.get('ci'),
                    payload,
                    default_source=result['source'].get('source_type') or job.source_type,
                )
                if metric_count:
                    summary['metric_snapshot'] += metric_count
            summary[result['action']] += 1
            relation_summary = result.get('relation_summary') or {}
            for key in ('created', 'skipped', 'failed'):
                if relation_summary.get(key):
                    summary[f'relation_{key}'] += relation_summary[key]
            record = CISyncRecord.objects.create(
                job=job,
                ci=result['ci'],
                batch_id=batch_id,
                action=result['action'],
                source_unique_id=result['source']['source_unique_id'],
                before=result['before'],
                after=result['after'],
                diff=result['diff'],
                status='failed' if result['action'] == 'conflict' else 'success',
                error_message=result.get('error_message', ''),
            )
            if result.get('ci') is not None and relation_summary.get('failed'):
                relation_retry_candidates.append({
                    'record': record,
                    'result': result,
                    'payload': payload,
                    'relation_summary': relation_summary,
                })
        except Exception as exc:
            summary['fail'] += 1
            after_payload = {'blocked_sensitive_payload': True} if isinstance(exc, ValidationError) else (
                payload if isinstance(payload, dict) else {'payload': payload}
            )
            record = CISyncRecord.objects.create(
                job=job,
                batch_id=batch_id,
                action='fail',
                source_unique_id=str((payload or {}).get('source_unique_id') or (payload or {}).get('instance_id') or ''),
                after=after_payload,
                status='failed',
                error_message=str(exc),
            )
        records.append(record)
    for candidate in relation_retry_candidates:
        retry_payload = _sync_relation_failed_hint_payload(candidate['payload'], candidate['relation_summary'])
        if not retry_payload:
            continue
        result = candidate['result']
        retry_summary = _sync_relations_from_payload(
            result['ci'],
            retry_payload,
            job=job,
            source=result['source'],
            operator=operator,
        )
        resolved_count = retry_summary.get('created', 0) + retry_summary.get('skipped', 0)
        if retry_summary.get('created'):
            summary['relation_created'] += retry_summary['created']
        if retry_summary.get('skipped'):
            summary['relation_skipped'] += retry_summary['skipped']
        if resolved_count:
            summary['relation_failed'] = max(0, summary.get('relation_failed', 0) - resolved_count)
        merged_summary = _sync_relation_merge_retry_summary(candidate['relation_summary'], retry_summary)
        record = candidate['record']
        after = dict(record.after or {})
        after['_sync_relations'] = merged_summary
        record.after = after
        record.save(update_fields=['after'])
    if create_missing_archive_candidates:
        archive_records = _create_archive_candidates_for_full_sync(job, seen_sources, batch_id=batch_id)
        if archive_records:
            summary['archive_candidate'] += len(archive_records)
            records.extend(archive_records)
        full_sync_archive_identities = {
            (
                (record.after or {}).get('source_type') or '',
                (record.after or {}).get('source_account') or '',
                (record.after or {}).get('source_region') or '',
                record.source_unique_id or '',
            )
            for record in archive_records
        }
        stale_records = _create_archive_candidates_for_stale_mappings(job, exclude_identities=full_sync_archive_identities, batch_id=batch_id)
        if stale_records:
            summary['archive_candidate'] += len(stale_records)
            records.extend(stale_records)
    job.finished_at = timezone.now()
    job.summary = dict(summary)
    error_count = summary.get('fail', 0) + summary.get('conflict', 0)
    job.status = 'success' if error_count == 0 else ('failed' if error_count == len(items) else 'partial')
    job.error_message = next((record.error_message for record in records if getattr(record, 'error_message', '')), '')
    job.save(update_fields=['finished_at', 'summary', 'status', 'error_message', 'updated_at'])
    if job.status == 'success':
        _mark_collection_failures_recovered(job, operator=operator)
    if records:
        _bump_cmdb_ledger_cache_version()
    return {'summary': dict(summary), 'records': records}


def _mark_sync_record_retry(record, retry_record, operator=''):
    retry_success = bool(retry_record and retry_record.status == 'success')
    record.retry_status = 'success' if retry_success else 'failed'
    record.retry_count = (record.retry_count or 0) + 1
    record.last_retried_at = timezone.now()
    record.retried_by = operator or ''
    record.retry_record = retry_record
    record.retry_result = retry_record.action if retry_record else 'fail'
    record.retry_error_message = '' if retry_success else (retry_record.error_message if retry_record else 'retry did not produce a record')
    record.save(update_fields=[
        'retry_status',
        'retry_count',
        'last_retried_at',
        'retried_by',
        'retry_record',
        'retry_result',
        'retry_error_message',
    ])


def _sync_retry_identity_from_payload(payload):
    if not isinstance(payload, dict):
        return ''
    attributes = payload.get('attributes') if isinstance(payload.get('attributes'), dict) else {}
    return str(
        payload.get('source_unique_id')
        or payload.get('instance_id')
        or payload.get('id')
        or attributes.get('source_unique_id')
        or attributes.get('instance_id')
        or ''
    )


def _sync_retry_identity_from_record(record):
    return str(record.source_unique_id or _sync_retry_identity_from_payload(record.after) or '')


def _mark_failed_records_from_retry_result(failed_records, retry_records, operator=''):
    retry_by_identity = defaultdict(list)
    unmatched_retry_records = []
    for retry_record in retry_records:
        identity = _sync_retry_identity_from_record(retry_record)
        if identity:
            retry_by_identity[identity].append(retry_record)
        else:
            unmatched_retry_records.append(retry_record)

    matched_retry_ids = set()
    for original_record in failed_records:
        identity = _sync_retry_identity_from_record(original_record)
        retry_record = None
        if identity and retry_by_identity.get(identity):
            retry_record = retry_by_identity[identity].pop(0)
        elif unmatched_retry_records:
            retry_record = unmatched_retry_records.pop(0)
        if retry_record:
            matched_retry_ids.add(retry_record.id)
        _mark_sync_record_retry(original_record, retry_record, operator=operator)
    return matched_retry_ids


def _mark_sync_record_relation_retry(record, relation_summary, retry_summary, operator=''):
    retry_success = int(relation_summary.get('failed') or 0) == 0
    retry_created = int(retry_summary.get('created') or 0)
    retry_skipped = int(retry_summary.get('skipped') or 0)
    retry_failed = int(retry_summary.get('failed') or 0)
    retry_errors = retry_summary.get('errors') if isinstance(retry_summary.get('errors'), list) else []
    after = dict(record.after or {})
    after['_sync_relations'] = relation_summary

    if retry_created:
        retry_result = 'relation_create'
    elif retry_skipped:
        retry_result = 'relation_skip'
    elif retry_failed:
        retry_result = 'relation_fail'
    else:
        retry_result = 'relation_retry'

    record.after = after
    record.retry_status = 'success' if retry_success else 'failed'
    record.retry_count = (record.retry_count or 0) + 1
    record.last_retried_at = timezone.now()
    record.retried_by = operator or ''
    record.retry_record = None
    record.retry_result = retry_result
    record.retry_error_message = '' if retry_success else '; '.join(
        str(item.get('reason') or item.get('error') or item) for item in retry_errors[:3]
    )
    record.save(update_fields=[
        'after',
        'retry_status',
        'retry_count',
        'last_retried_at',
        'retried_by',
        'retry_record',
        'retry_result',
        'retry_error_message',
    ])


def _retry_sync_record_relations(record, *, job, operator=''):
    initial_summary = _sync_record_relation_summary(record)
    payload = record.after if isinstance(record.after, dict) else {}
    retry_payload = _sync_relation_failed_hint_payload(payload, initial_summary)
    if not record.ci or not retry_payload:
        return {'skipped': 1, 'record': record}

    retry_summary = _sync_relations_from_payload(
        record.ci,
        retry_payload,
        job=job,
        source=_source_values(payload, default_source_type=job.source_type),
        operator=operator,
    )
    merged_summary = _sync_relation_merge_retry_summary(initial_summary, retry_summary)
    _mark_sync_record_relation_retry(record, merged_summary, retry_summary, operator=operator)
    summary = defaultdict(int)
    for key in ('created', 'skipped', 'failed'):
        value = int(retry_summary.get(key) or 0)
        if value:
            summary[f'relation_{key}'] += value
    resolved_count = int(retry_summary.get('created') or 0) + int(retry_summary.get('skipped') or 0)
    if resolved_count:
        summary['relation_resolved'] += resolved_count
    return {'summary': dict(summary), 'record': record}


class CIModelGroupViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = CIModelGroup.objects.all()
    serializer_class = CIModelGroupSerializer
    search_fields = ['name', 'code', 'description']
    filterset_fields = ['is_builtin', 'is_active']
    pagination_class = None
    rbac_permissions = {
        'list': ['cmdb.model.view'],
        'retrieve': ['cmdb.model.view'],
        'create': ['cmdb.model.manage'],
        'update': ['cmdb.model.manage'],
        'partial_update': ['cmdb.model.manage'],
        'destroy': ['cmdb.model.manage'],
        'ensure_builtins': ['cmdb.model.manage'],
    }

    @action(detail=False, methods=['post'], url_path='ensure-builtins')
    def ensure_builtins(self, request):
        before = {
            'groups': CIModelGroup.objects.filter(is_builtin=True).count(),
            'types': CIType.objects.filter(is_builtin=True).count(),
            'fields': CIField.objects.filter(is_builtin=True).count(),
            'relation_rules': CIRelationRule.objects.filter(
                source_type__is_builtin=True,
                target_type__is_builtin=True,
            ).count(),
            'threshold_policies': CIThresholdPolicy.objects.filter(resource_type__is_builtin=True).count(),
            'sync_jobs': CISyncJob.objects.filter(created_by='builtin').count(),
        }
        summary = ensure_builtin_cmdb()
        _record_ci_change(
            None,
            'cmdb_builtin_refresh',
            before,
            summary,
            operator=getattr(request.user, 'username', ''),
            source='model',
        )
        return Response({
            'summary': summary,
            'message': 'CMDB 内置模型、字段、关系规则、阈值策略和同步模板已刷新。',
        })

    def perform_create(self, serializer):
        group = serializer.save()
        _record_ci_change(
            None,
            'model_group_create',
            {},
            _model_group_snapshot(group),
            operator=getattr(self.request.user, 'username', ''),
            source='model',
        )

    def perform_update(self, serializer):
        before = _model_group_snapshot(serializer.instance)
        group = serializer.save()
        after = _model_group_snapshot(group)
        if _dict_diff(before, after):
            _record_ci_change(
                None,
                'model_group_update',
                before,
                after,
                operator=getattr(self.request.user, 'username', ''),
                source='model',
            )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_builtin:
            return Response({'detail': '内置模型分组不允许删除，可通过停用控制展示。'}, status=status.HTTP_400_BAD_REQUEST)
        if instance.ci_types.exists():
            return Response({'detail': '该分组下仍存在模型，请先迁移模型后再删除。'}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance):
        before = _model_group_snapshot(instance)
        _record_ci_change(
            None,
            'model_group_delete',
            before,
            {},
            operator=getattr(self.request.user, 'username', ''),
            source='model',
        )
        instance.delete()


class CITypeViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    """CI 类型管理"""
    queryset = CIType.objects.annotate(ci_count=Count('instances'))
    serializer_class = CITypeSerializer
    search_fields = ['name']
    pagination_class = None
    rbac_permissions = {
        'list': ['cmdb.ci.view'],
        'retrieve': ['cmdb.ci.view'],
        'create': ['cmdb.model.manage'],
        'update': ['cmdb.model.manage'],
        'partial_update': ['cmdb.model.manage'],
        'destroy': ['cmdb.model.manage'],
    }

    def get_required_permissions(self):
        if getattr(self, 'action', None) in {'list', 'retrieve'} and (
            user_has_permissions(self.request.user, ['cmdb.ci.view'])
            or user_has_permissions(self.request.user, ['cmdb.ci.manage'])
            or user_has_permissions(self.request.user, ['cmdb.model.view'])
            or user_has_permissions(self.request.user, ['cmdb.topology.view'])
        ):
            return []
        return super().get_required_permissions()

    def list(self, request, *args, **kwargs):
        search = (request.query_params.get('search') or '').strip().lower()
        grouped = {}
        for ci_type in self.get_queryset().select_related('group'):
            canonical_name = normalize_ci_type_name(ci_type.name)
            if is_placeholder_ci_type_name(canonical_name):
                continue
            row = grouped.get(canonical_name)
            if row is None:
                row = {
                    'id': ci_type.id,
                    'name': canonical_name,
                    'code': ci_type.code,
                    'group': ci_type.group_id,
                    'group_name': ci_type.group.name if ci_type.group else '',
                    'icon': ci_type.icon,
                    'color': ci_type.color,
                    'description': ci_type.description,
                    'is_builtin': ci_type.is_builtin,
                    'is_active': ci_type.is_active,
                    'created_at': ci_type.created_at,
                    'updated_at': ci_type.updated_at,
                    'ci_count': 0,
                }
                grouped[canonical_name] = row
            if canonical_name == ci_type.name:
                row['id'] = ci_type.id
                row['code'] = ci_type.code or row['code']
                row['group'] = ci_type.group_id or row['group']
                row['group_name'] = (ci_type.group.name if ci_type.group else '') or row['group_name']
                row['icon'] = ci_type.icon or row['icon']
                row['color'] = ci_type.color or row['color']
                row['description'] = ci_type.description or row['description']
                row['is_builtin'] = ci_type.is_builtin
                row['is_active'] = ci_type.is_active
                row['created_at'] = ci_type.created_at
                row['updated_at'] = ci_type.updated_at
            row['ci_count'] += getattr(ci_type, 'ci_count', 0)

        rows = list(grouped.values())
        if search:
            rows = [
                row for row in rows
                if search in (row['name'] or '').lower() or search in (row.get('code') or '').lower()
            ]
        rows.sort(key=lambda item: (-item['ci_count'], item['name']))
        return Response(rows)

    def perform_create(self, serializer):
        ci_type = serializer.save()
        _record_ci_change(
            None,
            'model_create',
            {},
            _ci_type_snapshot(ci_type),
            operator=getattr(self.request.user, 'username', ''),
            source='model',
        )

    def perform_update(self, serializer):
        before = _ci_type_snapshot(serializer.instance)
        ci_type = serializer.save()
        after = _ci_type_snapshot(ci_type)
        if _dict_diff(before, after):
            _record_ci_change(
                None,
                'model_update',
                before,
                after,
                operator=getattr(self.request.user, 'username', ''),
                source='model',
            )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_builtin:
            return Response({'detail': '内置模型不允许删除，可通过停用控制使用范围。'}, status=status.HTTP_400_BAD_REQUEST)
        if instance.instances.exists():
            return Response({'detail': '该模型下仍存在配置项，请先迁移或清理配置项后再删除。'}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance):
        before = _ci_type_snapshot(instance)
        _record_ci_change(
            None,
            'model_delete',
            before,
            {},
            operator=getattr(self.request.user, 'username', ''),
            source='model',
        )
        instance.delete()


class CIFieldViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = CIField.objects.select_related('ci_type').all()
    serializer_class = CIFieldSerializer
    search_fields = ['name', 'code', 'field_group', 'ci_type__name']
    filterset_fields = ['ci_type', 'field_type', 'required', 'unique', 'is_display', 'is_searchable', 'is_active']
    pagination_class = None
    rbac_permissions = {
        'list': ['cmdb.model.view'],
        'retrieve': ['cmdb.model.view'],
        'create': ['cmdb.model.manage'],
        'update': ['cmdb.model.manage'],
        'partial_update': ['cmdb.model.manage'],
        'destroy': ['cmdb.model.manage'],
    }

    def get_required_permissions(self):
        if getattr(self, 'action', None) in {'list', 'retrieve'} and (
            user_has_permissions(self.request.user, ['cmdb.ci.view'])
            or user_has_permissions(self.request.user, ['cmdb.ci.manage'])
            or user_has_permissions(self.request.user, ['cmdb.model.view'])
            or user_has_permissions(self.request.user, ['cmdb.topology.view'])
        ):
            return []
        return super().get_required_permissions()

    def perform_create(self, serializer):
        field = serializer.save()
        _record_ci_change(
            None,
            'model_field_create',
            {},
            _ci_field_snapshot(field),
            operator=getattr(self.request.user, 'username', ''),
            source='model',
        )

    def perform_update(self, serializer):
        before = _ci_field_snapshot(serializer.instance)
        field = serializer.save()
        after = _ci_field_snapshot(field)
        if _dict_diff(before, after):
            _record_ci_change(
                None,
                'model_field_update',
                before,
                after,
                operator=getattr(self.request.user, 'username', ''),
                source='model',
            )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_builtin:
            return Response({'detail': '内置字段不允许删除，可通过停用控制校验和展示。'}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance):
        before = _ci_field_snapshot(instance)
        _record_ci_change(
            None,
            'model_field_delete',
            before,
            {},
            operator=getattr(self.request.user, 'username', ''),
            source='model',
        )
        instance.delete()


class CITagViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = CITag.objects.annotate(ci_count=Count('config_items')).order_by('category', 'name', 'id')
    serializer_class = CITagSerializer
    search_fields = ['name', 'category', 'description']
    filterset_fields = ['category', 'is_active']
    pagination_class = None
    rbac_permissions = {
        'list': ['cmdb.ci.view'],
        'retrieve': ['cmdb.ci.view'],
        'create': ['cmdb.ci.manage'],
        'update': ['cmdb.ci.manage'],
        'partial_update': ['cmdb.ci.manage'],
        'destroy': ['cmdb.ci.manage'],
        'available_rules': ['cmdb.ci.view'],
    }

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if ConfigItem.objects.filter(tags=instance).exists():
            return Response({'detail': '该标签已关联资源，请先移除关联或停用标签。'}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)


class IPSubnetViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = IPSubnet.objects.all()
    serializer_class = IPSubnetSerializer
    search_fields = ['name', 'cidr', 'vlan_name', 'description']
    rbac_permissions = {
        'list': ['cmdb.ipam.view'],
        'retrieve': ['cmdb.ipam.view'],
        'addresses': ['cmdb.ipam.view'],
        'create': ['cmdb.ipam.manage'],
        'update': ['cmdb.ipam.manage'],
        'partial_update': ['cmdb.ipam.manage'],
        'destroy': ['cmdb.ipam.manage'],
        'scan': ['cmdb.ipam.manage'],
    }

    def get_queryset(self):
        return IPSubnet.objects.all().order_by('cidr', 'id')

    def perform_create(self, serializer):
        subnet = serializer.save(created_by=getattr(self.request.user, 'username', ''))
        _record_ci_change(None, 'ip_subnet_create', {}, {'id': subnet.id, 'cidr': subnet.cidr, 'name': subnet.name}, operator=getattr(self.request.user, 'username', ''), source='ipam')

    def perform_update(self, serializer):
        before = {'cidr': serializer.instance.cidr, 'name': serializer.instance.name, 'vlan_name': serializer.instance.vlan_name}
        subnet = serializer.save()
        _record_ci_change(None, 'ip_subnet_update', before, {'cidr': subnet.cidr, 'name': subnet.name, 'vlan_name': subnet.vlan_name}, operator=getattr(self.request.user, 'username', ''), source='ipam')

    def perform_destroy(self, instance):
        _record_ci_change(None, 'ip_subnet_delete', {'id': instance.id, 'cidr': instance.cidr, 'name': instance.name}, {}, operator=getattr(self.request.user, 'username', ''), source='ipam')
        instance.delete()

    @action(detail=True, methods=['get'])
    def addresses(self, request, pk=None):
        subnet = self.get_object()
        rows, summary = _subnet_address_snapshot(subnet)
        status_filter = str(request.query_params.get('status', '') or '').strip()
        search = str(request.query_params.get('search', '') or '').strip().lower()
        if status_filter:
            rows = [row for row in rows if row['status'] == status_filter]
        if search:
            rows = [row for row in rows if search in row['address'] or search in row['ci_name'].lower()]
        return Response({'subnet': IPSubnetSerializer(subnet).data, 'summary': summary, 'items': rows})

    @action(detail=True, methods=['post'])
    def scan(self, request, pk=None):
        subnet = self.get_object()
        try:
            timeout_ms = int(request.data.get('timeout_ms', 700))
        except (TypeError, ValueError):
            timeout_ms = 700
        summary = _scan_subnet(subnet, timeout_ms=max(200, min(timeout_ms, 3000)))
        audit_summary = {
            **summary,
            'scanned_at': summary['scanned_at'].isoformat() if summary.get('scanned_at') else '',
        }
        _record_ci_change(None, 'ip_subnet_scan', {}, {'id': subnet.id, 'cidr': subnet.cidr, **audit_summary}, operator=getattr(request.user, 'username', ''), source='ipam')
        return Response(summary)


class IPAddressViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = IPAddress.objects.select_related('subnet', 'ci').all()
    serializer_class = IPAddressSerializer
    search_fields = ['address', 'note', 'ci__name', 'subnet__name', 'subnet__cidr']
    filterset_fields = ['subnet', 'status', 'reachability']
    rbac_permissions = {
        'list': ['cmdb.ipam.view'],
        'retrieve': ['cmdb.ipam.view'],
        'create': ['cmdb.ipam.manage'],
        'update': ['cmdb.ipam.manage'],
        'partial_update': ['cmdb.ipam.manage'],
        'destroy': ['cmdb.ipam.manage'],
        'reserve': ['cmdb.ipam.manage'],
    }

    def perform_create(self, serializer):
        serializer.save(created_by=getattr(self.request.user, 'username', ''))

    @action(detail=True, methods=['post'])
    def reserve(self, request, pk=None):
        item = self.get_object()
        if item.ci_id:
            return Response({'detail': '已关联 CMDB 资产的地址不能手工保留。'}, status=status.HTTP_400_BAD_REQUEST)
        should_reserve = _to_bool(request.data.get('reserved', True))
        item.status = 'reserved' if should_reserve else 'available'
        item.note = str(request.data.get('note', item.note) or '').strip()
        item.save(update_fields=['status', 'note', 'updated_at'])
        _record_ci_change(None, 'ip_address_reserve', {}, {'id': item.id, 'address': item.address, 'status': item.status}, operator=getattr(request.user, 'username', ''), source='ipam')
        return Response(self.get_serializer(item).data)


class ConfigItemPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 500


CONFIG_ITEM_WATERLINE_METRICS = ['cpu_usage', 'memory_usage', 'disk_usage', 'storage_usage']
RESOURCE_WATERLINE_REFRESH_SOURCE_TYPES = {'aliyun_ecs', 'huaweicloud_ecs', 'vsphere_vm'}
LEDGER_TREE_ATTRIBUTE_KEYS = {
    'account',
    'account_id',
    'account_name',
    'app_group',
    'app_name',
    'application',
    'biz',
    'biz_line',
    'business_line',
    'business_line_name',
    'business_system',
    'cloud_account',
    'cloud_provider',
    'cloud_region',
    'cluster',
    'cores',
    'cpu',
    'cpu_count',
    'cpu_cores',
    'cpu_used',
    'cpu_used_cores',
    'cpu_used_mhz',
    'cpu_usage',
    'cpu_usage_percent',
    'cpu_utilization',
    'cpu_utilization_percent',
    'department',
    'disk_gb',
    'disk_size_gb',
    'disk_tb',
    'disk_used_gb',
    'disk_usage',
    'disk_usage_gb',
    'disk_usage_percent',
    'disk_utilization',
    'disk_utilization_percent',
    'env',
    'environment',
    'esxi_host',
    'host',
    'host_name',
    'instance_id',
    'instance_status',
    'lifecycle_status',
    'mem_gb',
    'memory',
    'memory_gb',
    'memory_mb',
    'memory_size_gb',
    'memory_used_gb',
    'memory_usage',
    'memory_usage_gb',
    'memory_usage_percent',
    'memory_utilization',
    'memory_utilization_percent',
    'metric_collection_error',
    'metric_collection_status',
    'metrics_collection_status',
    'name',
    'num_cpu',
    'num_cpus',
    'os_type',
    'private_ip',
    'provider',
    'provider_name',
    'provisioned_gb',
    'region',
    'region_id',
    'ram_gb',
    'ram_mb',
    'service_name',
    'service_expiry_date',
    'service_expire_warning_days',
    'source',
    'source_account',
    'source_region',
    'source_type',
    'source_unique_id',
    'state',
    'status',
    'storage_capacity_gb',
    'storage_gb',
    'storage_tb',
    'storage_used_gb',
    'storage_usage',
    'storage_usage_gb',
    'storage_usage_percent',
    'storage_utilization',
    'storage_utilization_percent',
    'system',
    'used_cpu',
    'used_cpu_cores',
    'used_disk_gb',
    'used_memory_gb',
    'used_memory_mb',
    'used_storage_gb',
    'vcpu',
    'vcpus',
    'vm_name',
    'vsphere_cluster',
}
LEDGER_TREE_PROVIDER_SUMMARY_ATTRIBUTE_KEYS = {
    'resource_kind',
    'endpoint',
    'host_count',
    'cluster_count',
    'datastore_count',
    'vm_count',
    'cpu_total_mhz',
    'cpu_used_mhz',
    'cpu_allocated_vcpu',
    'cpu_usage',
    'memory_total_gb',
    'memory_used_gb',
    'memory_allocated_gb',
    'memory_usage',
    'storage_total_gb',
    'storage_used_gb',
    'storage_allocated_gb',
    'storage_usage',
    'disk_total_gb',
    'disk_used_gb',
    'disk_allocated_gb',
    'disk_usage',
}


def _ledger_tree_attributes(attributes):
    if not isinstance(attributes, dict):
        return {}
    allowed_keys = set(LEDGER_TREE_ATTRIBUTE_KEYS)
    if attributes.get('resource_kind') == 'vsphere_capacity_summary':
        allowed_keys.update(LEDGER_TREE_PROVIDER_SUMMARY_ATTRIBUTE_KEYS)
    return {
        key: value
        for key, value in attributes.items()
        if key in allowed_keys and value not in (None, '')
    }


def _request_int_list(data, *keys, limit=100):
    raw_values = []
    for key in keys:
        if hasattr(data, 'getlist'):
            raw_values.extend(data.getlist(key))
        value = data.get(key) if hasattr(data, 'get') else None
        if value is not None:
            raw_values.append(value)
    values = []
    for raw in raw_values:
        if isinstance(raw, (list, tuple, set)):
            candidates = raw
        else:
            candidates = str(raw or '').replace(';', ',').split(',')
        for item in candidates:
            try:
                parsed = int(str(item).strip())
            except (TypeError, ValueError):
                continue
            if parsed and parsed not in values:
                values.append(parsed)
            if len(values) >= limit:
                return values
    return values


def _source_mapping_rows_for_waterline_refresh(ci):
    mappings = [
        mapping
        for mapping in ci.source_mappings.all()
        if (mapping.source_type or '').strip() in RESOURCE_WATERLINE_REFRESH_SOURCE_TYPES
        and (mapping.source_unique_id or '').strip()
    ]
    if mappings:
        return mappings
    attrs = ci.attributes or {}
    source_type = str(attrs.get('source_type') or attrs.get('source') or '').strip()
    source_unique_id = str(attrs.get('source_unique_id') or attrs.get('instance_id') or '').strip()
    if source_type in RESOURCE_WATERLINE_REFRESH_SOURCE_TYPES and source_unique_id:
        return [{
            'source_type': source_type,
            'source_account': str(attrs.get('source_account') or attrs.get('account') or attrs.get('account_name') or '').strip(),
            'source_region': str(attrs.get('source_region') or attrs.get('region') or '').strip(),
            'source_unique_id': source_unique_id,
        }]
    return []


def _mapping_value(mapping, key):
    if isinstance(mapping, dict):
        return str(mapping.get(key) or '').strip()
    return str(getattr(mapping, key, '') or '').strip()


def _sync_job_account_candidates(job):
    config = job.config or {}
    candidates = {
        str(config.get(key) or '').strip()
        for key in ('source_account', 'account_name', 'account_id', 'cloud_account_name')
        if str(config.get(key) or '').strip()
    }
    cloud_account_id = config.get('cloud_account_id') or config.get('multicloud_account_id')
    if cloud_account_id:
        try:
            from multicloud.models import CloudCredential
            credential = CloudCredential.objects.filter(id=cloud_account_id).first()
        except Exception:
            credential = None
        if credential:
            for value in (credential.account_name, credential.name, credential.account_id, credential.default_region):
                text = str(value or '').strip()
                if text:
                    candidates.add(text)
                    candidates.add(text.rstrip('/'))
    return {item for item in candidates if item}


def _sync_job_matches_source_mapping(job, mapping):
    source_account = _mapping_value(mapping, 'source_account')
    candidates = _sync_job_account_candidates(job)
    if source_account and candidates and source_account not in candidates:
        return False
    return True


def _sync_job_for_waterline_mapping(mapping):
    source_type = _mapping_value(mapping, 'source_type')
    source_account = _mapping_value(mapping, 'source_account')
    jobs = CISyncJob.objects.filter(source_type=source_type).order_by('-updated_at', '-id')
    fallback = None
    for job in jobs:
        if not _sync_job_matches_source_mapping(job, mapping):
            continue
        candidates = _sync_job_account_candidates(job)
        if source_account and source_account in candidates:
            return job
        if fallback is None:
            fallback = job
    return fallback


def _filter_sync_items_for_source_unique_ids(job, items, source_unique_ids):
    wanted = {str(item or '').strip() for item in source_unique_ids if str(item or '').strip()}
    filtered = []
    seen = set()
    for payload in items:
        if not isinstance(payload, dict):
            continue
        source = _source_values(payload, default_source_type=job.source_type)
        source_unique_id = source.get('source_unique_id') or ''
        if source_unique_id not in wanted or source_unique_id in seen:
            continue
        filtered.append(payload)
        seen.add(source_unique_id)
    return filtered


def _latest_metric_snapshot_rows_for_ci_ids(ci_ids):
    return list(latest_metric_snapshots(ci_ids, CONFIG_ITEM_WATERLINE_METRICS))


class ConfigItemViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    """配置项管理"""
    queryset = ConfigItem.objects.select_related('ci_type', 'business_node', 'environment_node', 'resource_node').all().order_by('-updated_at', '-id')
    serializer_class = ConfigItemSerializer
    pagination_class = ConfigItemPagination
    search_fields = [
        'name',
        'admin_user',
        'business_line',
        'ci_type__name',
        'tags__name',
        'tags__category',
        'attributes__ip_address',
        'attributes__ip',
        'attributes__private_ip',
        'attributes__public_ip',
        'attributes__host_ip',
        'attributes__docker_environment_ip',
        'attributes__description',
        'attributes__specification',
        'attributes__instance_type',
        'attributes__department',
        'attributes__provider',
        'attributes__service_type',
        'attributes__account_subject',
        'attributes__contract_no',
    ]
    filterset_fields = ['ci_type', 'business_line', 'environment', 'tags']
    rbac_permissions = {
        'list': ['cmdb.ci.view'],
        'retrieve': ['cmdb.ci.view'],
        'create': ['cmdb.ci.manage'],
        'update': ['cmdb.ci.manage'],
        'partial_update': ['cmdb.ci.manage'],
        'destroy': ['cmdb.ci.manage'],
        'stats': ['cmdb.ci.view'],
        'impact': ['cmdb.ci.view'],
        'bulk_import': ['cmdb.ci.manage'],
        'bulk_update': ['cmdb.ci.manage'],
        'export': ['cmdb.ci.view'],
        'import_template': ['cmdb.ci.view'],
        'ledger_tree': ['cmdb.ci.view'],
        'mark_archive_candidate': ['cmdb.ci.manage'],
        'restore_lifecycle': ['cmdb.ci.manage'],
        'governance_action': ['cmdb.ci.manage'],
        'merge_duplicates': ['cmdb.ci.manage'],
        'third_party_expiry_summary': ['cmdb.ci.view'],
    }

    def get_queryset(self):
        permission = 'manage' if getattr(self, 'action', '') in {
            'update',
            'partial_update',
            'destroy',
            'bulk_update',
            'mark_archive_candidate',
            'restore_lifecycle',
            'governance_action',
            'merge_duplicates',
        } else 'view'
        action = getattr(self, 'action', '')
        qs = ConfigItem.objects.select_related('ci_type', 'business_node', 'environment_node', 'resource_node').all().order_by('-updated_at', '-id')
        if action == 'ledger_tree':
            qs = qs.select_related('ci_type__group').prefetch_related(Prefetch(
                'source_mappings',
                queryset=CISourceMapping.objects.only(
                    'id',
                    'ci_id',
                    'source_type',
                    'source_account',
                    'source_region',
                    'source_unique_id',
                    'sync_status',
                    'last_seen_at',
                    'updated_at',
                ).order_by('id'),
            ))
        elif action in {'list', 'retrieve', 'export'}:
            qs = qs.prefetch_related(
                'tags',
                Prefetch(
                    'source_mappings',
                    queryset=CISourceMapping.objects.only(
                        'id',
                        'ci_id',
                        'source_type',
                        'source_account',
                        'source_region',
                        'source_unique_id',
                        'sync_status',
                        'last_seen_at',
                        'updated_at',
                    ).order_by('id'),
                ),
            )
        qs = _apply_ci_authorization_scope(qs, self.request.user, permission=permission)
        qs = _apply_config_item_attribute_filters(qs, self.request.query_params)
        if action in {'list', 'stats', 'export', 'ledger_tree'} and not _include_internal_provider_summaries(self.request.query_params):
            qs = _exclude_internal_provider_summary_items(qs)
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if getattr(self, 'action', '') == 'list':
            include_fields = _to_bool(self.request.query_params.get('include_fields', False))
            context['include_field_definitions'] = include_fields
        return context

    def _hydrate_config_item_list_page(self, items):
        item_list = list(items or [])
        if not item_list:
            return item_list
        ci_ids = [item.id for item in item_list]
        ci_type_ids = {item.ci_type_id for item in item_list if item.ci_type_id}

        relation_counts = defaultdict(int)
        for row in CIRelation.objects.filter(source_id__in=ci_ids).values('source_id').annotate(total=Count('id')):
            relation_counts[row['source_id']] += row['total']
        for row in CIRelation.objects.filter(target_id__in=ci_ids).values('target_id').annotate(total=Count('id')):
            relation_counts[row['target_id']] += row['total']

        field_rows_by_type = defaultdict(list)
        for field in CIField.objects.filter(ci_type_id__in=ci_type_ids, is_active=True).order_by('sort_order', 'id'):
            field_rows_by_type[field.ci_type_id].append(field)

        metric_rows_by_ci = defaultdict(list)
        for snapshot in _latest_metric_snapshot_rows_for_ci_ids(ci_ids):
            metric_rows_by_ci[snapshot.ci_id].append(snapshot)

        for item in item_list:
            item.relation_count_cached = relation_counts.get(item.id, 0)
            if item.ci_type_id and getattr(item, 'ci_type', None):
                item.ci_type.active_field_definitions = field_rows_by_type.get(item.ci_type_id, [])
            item.latest_waterline_metrics = metric_rows_by_ci.get(item.id, [])
        return item_list

    def list(self, request, *args, **kwargs):
        cache_key = _cmdb_ledger_request_cache_key(request, 'list')
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            page = self._hydrate_config_item_list_page(page)
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            cache.set(cache_key, response.data, CMDB_LEDGER_LIST_CACHE_TTL)
            return response
        items = self._hydrate_config_item_list_page(queryset[:200])
        serializer = self.get_serializer(items, many=True)
        data = serializer.data
        cache.set(cache_key, data, CMDB_LEDGER_LIST_CACHE_TTL)
        return Response(data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.filter_queryset(self.get_queryset())
        by_type_map = {}
        for item in qs:
            type_meta = resolve_config_item_type_meta(item)
            normalized_name = normalize_ci_type_name(type_meta['name'])
            bucket = by_type_map.setdefault(
                normalized_name,
                {
                    'ci_type': item.ci_type_id,
                    'ci_type__name': normalized_name,
                    'ci_type__color': type_meta['color'] or '#9c27b0',
                    'count': 0,
                },
            )
            bucket['count'] += 1
        by_type = sorted(by_type_map.values(), key=lambda entry: entry['count'], reverse=True)
        by_status = dict(qs.values_list('status').annotate(count=Count('id')))
        by_env = dict(qs.values_list('environment').annotate(count=Count('id')))
        return Response({
            'total': qs.count(),
            'by_type': by_type,
            'by_status': by_status,
            'by_env': by_env,
        })

    @action(detail=False, methods=['get'], url_path='third-party-expiry-summary')
    def third_party_expiry_summary(self, request):
        summary = {'total': 0, 'normal': 0, 'warning': 0, 'urgent': 0, 'expired': 0, 'missing': 0}
        today = timezone.localdate()
        for item in self.filter_queryset(self.get_queryset()).filter(ci_type__code='THIRD_PARTY_SERVICE'):
            expiry = _third_party_service_expiry_state_for_ci(item, today=today)
            if not expiry:
                continue
            summary['total'] += 1
            summary[expiry['status']] += 1
        return Response(summary)

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        try:
            items = _items_for_bulk_import(request.data)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        source_type = (request.data.get('source_type') or 'manual_import').strip()[:50] or 'manual_import'
        job_name = (request.data.get('name') or '资源台账批量导入').strip()[:100] or '资源台账批量导入'
        dry_run = _to_bool(request.data.get('dry_run', False))
        if dry_run:
            preview_job = CISyncJob(name=job_name, source_type=source_type, mode='import', dry_run=True)
            preview = _preview_sync_items(preview_job, items, user=request.user)
            return Response({
                'summary': preview['summary'],
                'records': preview['records'],
                'dry_run': True,
            })

        job = CISyncJob.objects.create(
            name=job_name,
            source_type=source_type,
            mode='import',
            dry_run=False,
            config={'items': items, 'format': request.data.get('format') or 'json'},
            created_by=getattr(request.user, 'username', ''),
        )
        result = _run_sync_items(job, items, operator=getattr(request.user, 'username', ''), user=request.user)
        return Response({
            'job': CISyncJobSerializer(job).data,
            'summary': result['summary'],
            'records': CISyncRecordSerializer(result['records'], many=True).data,
            'dry_run': False,
        })

    @action(detail=False, methods=['get'])
    def export(self, request):
        items = self.get_queryset()
        raw_ids = (request.query_params.get('ids') or '').strip()
        ci_type = (request.query_params.get('ci_type') or '').strip()
        business_line = (request.query_params.get('business_line') or '').strip()
        environment = (request.query_params.get('environment') or '').strip()
        tags = request.query_params.getlist('tags') or request.query_params.getlist('tags[]')
        if ci_type:
            items = items.filter(ci_type_id=ci_type)
        if business_line:
            items = items.filter(business_line=business_line)
        if environment:
            items = items.filter(environment=environment)
        if tags:
            items = items.filter(tags__in=[tag for tag in tags if tag]).distinct()
        if raw_ids:
            try:
                selected_ids = [int(value) for value in raw_ids.split(',') if value.strip()]
            except ValueError:
                return Response({'ids': ['资产 ID 必须为逗号分隔的整数。']}, status=status.HTTP_400_BAD_REQUEST)
            if not selected_ids:
                return Response({'ids': ['请至少选择一个资产。']}, status=status.HTTP_400_BAD_REQUEST)
            items = items.filter(id__in=selected_ids)
        items = items.select_related('ci_type', 'ci_type__group').prefetch_related('source_mappings')
        return _config_items_export_by_type_response(items)

    @action(detail=False, methods=['get'], url_path='ledger-tree')
    def ledger_tree(self, request):
        cache_key = _cmdb_ledger_request_cache_key(request, 'tree')
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        items = self.filter_queryset(self.get_queryset())
        rows = []
        for item in items:
            attributes = item.attributes or {}
            tree_attributes = _ledger_tree_attributes(attributes)
            source_rows = [
                {
                    'id': mapping.id,
                    'source_type': mapping.source_type,
                    'source_account': mapping.source_account,
                    'source_region': mapping.source_region,
                    'source_unique_id': mapping.source_unique_id,
                    'sync_status': mapping.sync_status,
                    'last_seen_at': mapping.last_seen_at,
                    'updated_at': mapping.updated_at,
                }
                for mapping in item.source_mappings.all()
            ]
            primary_source = source_rows[0] if source_rows else {}
            type_meta = resolve_config_item_type_meta(item)
            rows.append({
                'id': item.id,
                'name': item.name,
                'ci_type': item.ci_type_id,
                'ci_type_name': type_meta['name'],
                'ci_type_code': item.ci_type.code if item.ci_type_id else '',
                'ci_type_group': item.ci_type.group_id if item.ci_type_id else None,
                'ci_type_group_name': item.ci_type.group.name if item.ci_type_id and item.ci_type.group_id else '',
                'ci_type_group_code': item.ci_type.group.code if item.ci_type_id and item.ci_type.group_id else '',
                'business_node': item.business_node_id,
                'business_node_name': item.business_node.name if item.business_node_id else '',
                'business_line': item.business_line,
                'environment_node': item.environment_node_id,
                'environment_node_name': item.environment_node.name if item.environment_node_id else '',
                'environment': item.environment,
                'resource_node': item.resource_node_id,
                'resource_node_name': item.resource_node.name if item.resource_node_id else '',
                'resource_node_type': item.resource_node.node_type if item.resource_node_id else '',
                'resource_node_parent': item.resource_node.parent_id if item.resource_node_id else None,
                'status': item.status,
                'admin_user': item.admin_user,
                'attributes': tree_attributes,
                'source_mappings': source_rows,
                'source_label': primary_source.get('source_type') or attributes.get('source_type') or 'manual',
                'source_type': primary_source.get('source_type') or attributes.get('source_type') or 'manual',
                'source_sync_status': primary_source.get('sync_status') or '',
                'source_unique_id': primary_source.get('source_unique_id') or '',
            })
        cache.set(cache_key, rows, CMDB_LEDGER_TREE_CACHE_TTL)
        return Response(rows)

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        raw_ci_type_ids = (request.query_params.get('ci_types') or request.query_params.get('ci_type') or '').strip()
        if not raw_ci_type_ids:
            return _config_item_import_template_response()
        try:
            ci_type_ids = [int(value) for value in raw_ci_type_ids.split(',') if value.strip()]
        except ValueError:
            return Response({'ci_types': ['模型 ID 必须为逗号分隔的整数。']}, status=status.HTTP_400_BAD_REQUEST)
        ci_types = list(CIType.objects.filter(id__in=ci_type_ids).order_by('name', 'id'))
        if len(ci_types) != len(set(ci_type_ids)):
            return Response({'detail': '包含不存在的模型'}, status=status.HTTP_400_BAD_REQUEST)
        if len(ci_types) == 1:
            return _config_item_import_template_response(ci_types[0])
        return _config_item_import_template_archive_response(ci_types)

    @action(detail=False, methods=['post'], url_path='bulk-update')
    def bulk_update(self, request):
        raw_ids = request.data.get('ids') or request.data.get('ci_ids') or []
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response({'ids': ['Please provide a non-empty CI id list.']}, status=status.HTTP_400_BAD_REQUEST)
        try:
            ci_ids = [int(item) for item in raw_ids]
        except (TypeError, ValueError):
            return Response({'ids': ['CI ids must be integers.']}, status=status.HTTP_400_BAD_REQUEST)
        ci_ids = list(dict.fromkeys(ci_ids))

        updates = request.data.get('updates') or {}
        if not isinstance(updates, dict):
            return Response({'updates': ['Updates must be an object.']}, status=status.HTTP_400_BAD_REQUEST)

        allowed_update_fields = {'business_node', 'environment_node', 'business_line', 'environment', 'admin_user', 'status', 'attributes'}
        serializer_updates = {
            key: value
            for key, value in updates.items()
            if key in allowed_update_fields
        }
        if 'attributes' in serializer_updates and not isinstance(serializer_updates.get('attributes'), dict):
            return Response({'attributes': ['Attributes must be an object.']}, status=status.HTTP_400_BAD_REQUEST)

        tag_ids = request.data.get('tag_ids', updates.get('tag_ids', None))
        tag_action = (request.data.get('tag_action') or updates.get('tag_action') or 'append').strip().lower()
        if tag_action not in {'append', 'replace', 'remove'}:
            return Response({'tag_action': ['tag_action must be append, replace, or remove.']}, status=status.HTTP_400_BAD_REQUEST)
        if tag_ids is not None:
            if not isinstance(tag_ids, list):
                return Response({'tag_ids': ['tag_ids must be a list.']}, status=status.HTTP_400_BAD_REQUEST)
            try:
                tag_ids = [int(item) for item in tag_ids]
            except (TypeError, ValueError):
                return Response({'tag_ids': ['Tag ids must be integers.']}, status=status.HTTP_400_BAD_REQUEST)
            tag_ids = list(dict.fromkeys(tag_ids))
        else:
            tag_ids = []

        if not serializer_updates and not tag_ids:
            return Response({'updates': ['Please provide fields or tags to update.']}, status=status.HTTP_400_BAD_REQUEST)

        items = list(
            self.get_queryset()
            .filter(id__in=ci_ids)
            .select_related('ci_type')
            .prefetch_related('tags')
            .order_by('id')
        )
        if len(items) != len(ci_ids):
            found_ids = {item.id for item in items}
            missing_ids = [item for item in ci_ids if item not in found_ids]
            return Response({'ids': [f'CI ids not found or out of scope: {missing_ids}']}, status=status.HTTP_404_NOT_FOUND)

        tags = []
        if tag_ids:
            tags = list(CITag.objects.filter(id__in=tag_ids))
            if len(tags) != len(tag_ids):
                found_tag_ids = {item.id for item in tags}
                missing_tag_ids = [item for item in tag_ids if item not in found_tag_ids]
                return Response({'tag_ids': [f'Tag ids not found: {missing_tag_ids}']}, status=status.HTTP_404_NOT_FOUND)

        operator = getattr(request.user, 'username', '')
        note = (request.data.get('note') or updates.get('note') or '').strip()[:200]
        updated_items = []
        audit_rows = []

        with transaction.atomic():
            for item in items:
                _ensure_user_can_manage_config_item(request.user, item)
                before = _config_item_snapshot(item)
                if serializer_updates:
                    serializer = self.get_serializer(item, data=serializer_updates, partial=True)
                    serializer.is_valid(raise_exception=True)
                    validated = serializer.validated_data
                    ci_type = validated.get('ci_type') or item.ci_type
                    _ensure_user_can_manage_ci_resource(
                        request.user,
                        ci_type_id=ci_type.id if ci_type else None,
                        business_line=validated.get('business_line', item.business_line),
                        environment=validated.get('environment', item.environment),
                    )
                    item = serializer.save(attributes=normalize_ci_attributes(validated.get('attributes', item.attributes or {})))
                else:
                    _ensure_user_can_manage_ci_resource(
                        request.user,
                        ci_type_id=item.ci_type_id,
                        business_line=item.business_line,
                        environment=item.environment,
                    )

                if tags:
                    if tag_action == 'replace':
                        item.tags.set(tags)
                    elif tag_action == 'remove':
                        item.tags.remove(*tags)
                    else:
                        item.tags.add(*tags)

                _sync_completion_issue(item)
                item.refresh_from_db()
                after = _config_item_snapshot(item)
                audit_after = dict(after)
                if note:
                    audit_after['note'] = note
                _record_ci_change(
                    item,
                    'bulk_update',
                    before,
                    audit_after,
                    operator=operator,
                    source='manual',
                )
                updated_items.append(item)
                audit_rows.append({
                    'id': item.id,
                    'name': item.name,
                    'before': before,
                    'after': after,
                })

        return Response({
            'updated_count': len(updated_items),
            'tag_action': tag_action if tags else '',
            'updated_ids': [item.id for item in updated_items],
            'items': ConfigItemSerializer(updated_items, many=True).data,
            'changes': audit_rows,
        })

    @action(detail=True, methods=['get'])
    def impact(self, request, pk=None):
        try:
            max_depth = int(request.query_params.get('max_depth', 2))
        except (TypeError, ValueError):
            max_depth = 2
        return Response(_config_item_delete_impact(self.get_object(), max_depth=max_depth, user=request.user))

    @action(detail=True, methods=['post'], url_path='mark-archive-candidate')
    def mark_archive_candidate(self, request, pk=None):
        config_item = self.get_object()
        _ensure_user_can_manage_config_item(request.user, config_item)
        source_type = (request.data.get('source_type') or 'manual').strip()[:50] or 'manual'
        reason = (request.data.get('reason') or '人工标记待下线').strip()[:200] or '人工标记待下线'
        candidate = CIArchiveCandidate.objects.filter(
            ci=config_item,
            source_type=source_type,
            status__in=['pending', 'ignored', 'confirmed', 'archived'],
        ).order_by('-updated_at', '-id').first()
        before = _config_item_snapshot(config_item)
        if candidate:
            candidate.status = 'pending'
            candidate.reason = reason
            candidate.confirmed_by = ''
            candidate.confirmed_at = None
            candidate.save(update_fields=['status', 'reason', 'confirmed_by', 'confirmed_at', 'updated_at'])
        else:
            candidate = CIArchiveCandidate.objects.create(
                ci=config_item,
                source_type=source_type,
                reason=reason,
            )
        _record_ci_change(
            config_item,
            'archive_mark',
            before,
            _config_item_snapshot(config_item),
            operator=getattr(request.user, 'username', ''),
            source='governance',
        )
        return Response(CIArchiveCandidateSerializer(candidate).data)

    @action(detail=True, methods=['post'], url_path='restore-lifecycle')
    def restore_lifecycle(self, request, pk=None):
        config_item = self.get_object()
        _ensure_user_can_manage_config_item(request.user, config_item)
        before = _config_item_snapshot(config_item)
        target_status = request.data.get('status') or 'active'
        if target_status not in {'active', 'stopped'}:
            return Response({'status': ['恢复状态只能是 active 或 stopped']}, status=status.HTTP_400_BAD_REQUEST)
        note = (request.data.get('note') or '人工恢复资源生命周期').strip()[:200]
        config_item.status = target_status
        config_item.save(update_fields=['status', 'updated_at'])
        for candidate in config_item.archive_candidates.filter(status__in=['pending', 'confirmed', 'archived']):
            candidate.status = 'restored'
            candidate.confirmed_by = getattr(request.user, 'username', '')
            candidate.confirmed_at = timezone.now()
            if note:
                candidate.reason = f"{candidate.reason}；{note}"[:200] if candidate.reason else note
            candidate.save(update_fields=['status', 'confirmed_by', 'confirmed_at', 'reason', 'updated_at'])
        _record_ci_change(
            config_item,
            'archive_restore',
            before,
            _config_item_snapshot(config_item),
            operator=getattr(request.user, 'username', ''),
            source='governance',
        )
        return Response(ConfigItemSerializer(config_item).data)

    @action(detail=True, methods=['post'], url_path='governance-action')
    def governance_action(self, request, pk=None):
        """Persist an operator decision for a service-expiry or capacity risk."""
        config_item = self.get_object()
        _ensure_user_can_manage_config_item(request.user, config_item)
        category = str(request.data.get('category') or '').strip().lower()
        metric = str(request.data.get('metric') or '').strip().lower()
        action_name = str(request.data.get('status') or request.data.get('action') or '').strip().lower()
        if category not in {'service_expiry', 'capacity'}:
            return Response({'category': ['仅支持 service_expiry 或 capacity']}, status=status.HTTP_400_BAD_REQUEST)
        if category == 'capacity' and not metric:
            return Response({'metric': ['容量治理必须提供指标']}, status=status.HTTP_400_BAD_REQUEST)
        if action_name not in {'resolved', 'ignored', 'open'}:
            return Response({'status': ['治理状态只能是 resolved、ignored 或 open']}, status=status.HTTP_400_BAD_REQUEST)
        note = str(request.data.get('note') or '').strip()[:200]
        before = _config_item_snapshot(config_item)
        attributes = dict(config_item.attributes or {})
        raw_governance = attributes.get('governance')
        governance = dict(raw_governance) if isinstance(raw_governance, dict) else {}
        key = f'{category}:{metric}' if metric else category
        if action_name == 'open':
            governance.pop(key, None)
        else:
            governance[key] = {
                'status': action_name,
                'note': note,
                'fingerprint': str(request.data.get('risk_fingerprint') or '').strip()[:200],
                'updated_at': timezone.now().isoformat(),
                'updated_by': getattr(request.user, 'username', ''),
            }
        if governance:
            attributes['governance'] = governance
        else:
            attributes.pop('governance', None)
        config_item.attributes = normalize_ci_attributes(attributes)
        config_item.save(update_fields=['attributes', 'updated_at'])
        _record_ci_change(
            config_item,
            'governance_status',
            before,
            _config_item_snapshot(config_item),
            operator=getattr(request.user, 'username', ''),
            source='governance',
        )
        return Response({
            'id': config_item.id,
            'category': category,
            'metric': metric,
            'status': action_name,
            'note': note,
            'item': ConfigItemSerializer(config_item).data,
        })

    @action(detail=True, methods=['post'], url_path='merge-duplicates')
    def merge_duplicates(self, request, pk=None):
        target = self.get_object()
        _ensure_user_can_manage_config_item(request.user, target)
        source_ids = request.data.get('source_ids') or request.data.get('duplicate_ids') or []
        if not isinstance(source_ids, list) or not source_ids:
            return Response({'source_ids': ['请提供要合并的重复资源 ID 列表']}, status=status.HTTP_400_BAD_REQUEST)
        try:
            source_ids = [int(item) for item in source_ids]
        except (TypeError, ValueError):
            return Response({'source_ids': ['资源 ID 必须是整数']}, status=status.HTTP_400_BAD_REQUEST)
        source_ids = [item for item in dict.fromkeys(source_ids) if item != target.id]
        if not source_ids:
            return Response({'source_ids': ['不能把主资源自身作为合并来源']}, status=status.HTTP_400_BAD_REQUEST)

        sources = list(
            ConfigItem.objects.select_related('ci_type')
            .prefetch_related('tags', 'source_mappings')
            .filter(id__in=source_ids)
            .order_by('id')
        )
        if len(sources) != len(source_ids):
            found_ids = {item.id for item in sources}
            missing_ids = [item for item in source_ids if item not in found_ids]
            return Response({'source_ids': [f'资源不存在: {missing_ids}']}, status=status.HTTP_404_NOT_FOUND)
        for source in sources:
            _ensure_user_can_manage_config_item(request.user, source)
            if source.ci_type_id != target.ci_type_id:
                return Response({'source_ids': [f'资源 {source.name} 与主资源模型不同，不能直接合并']}, status=status.HTTP_400_BAD_REQUEST)

        reason = (request.data.get('reason') or '重复资源人工合并').strip()[:200] or '重复资源人工合并'
        operator = getattr(request.user, 'username', '')
        before = {
            'target': _config_item_snapshot(target),
            'sources': [_config_item_snapshot(source) for source in sources],
        }
        source_id_set = {source.id for source in sources}
        moved_counts = defaultdict(int)

        with transaction.atomic():
            target.attributes = _merge_config_item_attributes(target, sources)
            target.save(update_fields=['attributes', 'updated_at'])
            for source in sources:
                target.tags.add(*list(source.tags.all()))

            for mapping in CISourceMapping.objects.filter(ci_id__in=source_id_set):
                mapping.ci = target
                mapping.save(update_fields=['ci', 'updated_at'])
                moved_counts['source_mappings'] += 1
            for cost in CostRecord.objects.filter(ci_id__in=source_id_set):
                cost.ci = target
                cost.save(update_fields=['ci'])
                moved_counts['cost_records'] += 1
            moved_counts['resource_metrics'] = CIResourceMetricSnapshot.objects.filter(ci_id__in=source_id_set).update(ci=target)
            for sync_record in CISyncRecord.objects.filter(ci_id__in=source_id_set):
                sync_record.ci = target
                sync_record.save(update_fields=['ci'])
                moved_counts['sync_records'] += 1
            for issue in CICompletionIssue.objects.filter(ci_id__in=source_id_set).exclude(status__in=['resolved', 'ignored']):
                issue.ci = target
                issue.resolution_note = (issue.resolution_note or f'由重复资源合并至 {target.name}')[:200]
                issue.save(update_fields=['ci', 'resolution_note', 'updated_at'])
                moved_counts['completion_issues'] += 1
            for candidate in CIArchiveCandidate.objects.filter(ci_id__in=source_id_set).exclude(status__in=['restored', 'ignored']):
                candidate.ci = target
                candidate.reason = (candidate.reason or f'由重复资源合并至 {target.name}')[:200]
                candidate.save(update_fields=['ci', 'reason', 'updated_at'])
                moved_counts['archive_candidates'] += 1

            relation_qs = CIRelation.objects.filter(Q(source_id__in=source_id_set) | Q(target_id__in=source_id_set)).order_by('id')
            for relation in list(relation_qs):
                result = _move_relation_to_merge_target(relation, target, source_id_set)
                moved_counts[f'relations_{result}'] += 1

            for source in sources:
                _mark_source_config_item_merged(source, target, reason, operator)

            target.refresh_from_db()
            _sync_completion_issue(target)
            after = {
                'target': _config_item_snapshot(target),
                'sources': [_config_item_snapshot(source) for source in ConfigItem.objects.filter(id__in=source_ids).select_related('ci_type')],
                'moved_counts': dict(moved_counts),
                'reason': reason,
            }
            _record_ci_change(
                target,
                'merge_duplicates',
                before,
                after,
                operator=operator,
                source='governance',
            )

        return Response({
            'detail': '重复资源已合并',
            'summary': _config_item_merge_summary(target, sources),
            'moved_counts': dict(moved_counts),
            'target': ConfigItemSerializer(target).data,
        })

    def perform_create(self, serializer):
        ci_type = serializer.validated_data.get('ci_type')
        _ensure_user_can_manage_ci_resource(
            self.request.user,
            ci_type_id=ci_type.id if ci_type else None,
            business_line=serializer.validated_data.get('business_line', ''),
            environment=serializer.validated_data.get('environment', ''),
        )
        config_item = serializer.save(attributes=normalize_ci_attributes(serializer.validated_data.get('attributes')))
        after = _config_item_snapshot(config_item)
        _record_ci_change(
            config_item,
            'create',
            {},
            after,
            operator=getattr(self.request.user, 'username', ''),
            source='manual',
        )
        _sync_completion_issue(config_item)

    def perform_update(self, serializer):
        before = _config_item_snapshot(serializer.instance)
        attributes = serializer.validated_data.get('attributes', serializer.instance.attributes if serializer.instance else {})
        ci_type = serializer.validated_data.get('ci_type') or serializer.instance.ci_type
        _ensure_user_can_manage_ci_resource(
            self.request.user,
            ci_type_id=ci_type.id if ci_type else None,
            business_line=serializer.validated_data.get('business_line', serializer.instance.business_line),
            environment=serializer.validated_data.get('environment', serializer.instance.environment),
        )
        config_item = serializer.save(attributes=normalize_ci_attributes(attributes))
        after = _config_item_snapshot(config_item)
        _record_ci_change(
            config_item,
            'update',
            before,
            after,
            operator=getattr(self.request.user, 'username', ''),
            source='manual',
        )
        _sync_completion_issue(config_item)

    def destroy(self, request, *args, **kwargs):
        config_item = self.get_object()
        impact = _config_item_delete_impact(config_item, user=request.user)
        force = _to_bool(request.query_params.get('force'))
        if impact['blocking_total'] and not force:
            return Response({
                'detail': '配置项存在关联影响，请确认影响面后再强制删除',
                'impact': impact,
            }, status=status.HTTP_400_BAD_REQUEST)
        before = _config_item_snapshot(config_item)
        _record_ci_change(
            None,
            'delete',
            before,
            {},
            operator=getattr(request.user, 'username', ''),
            source='manual',
        )
        config_item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class ConfigItemPasswordViewSet(EventWallModelViewSetMixin, RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = ConfigItemPassword.objects.select_related('config_item', 'config_item__ci_type').all()
    serializer_class = ConfigItemPasswordSerializer
    pagination_class = None
    filterset_fields = ['config_item']
    search_fields = ['config_item__name', 'username', 'remark']
    event_module = 'cmdb'
    event_category = 'security'
    event_resource_type = 'config_item_password'
    event_resource_label = '资产登录凭据'
    event_resource_name_fields = ('config_item',)
    event_exclude_fields = ('password_ciphertext',)
    rbac_permissions = {
        'list': ['cmdb.password.reveal'],
        'retrieve': ['cmdb.password.reveal'],
        'create': ['cmdb.password.manage'],
        'update': ['cmdb.password.manage'],
        'partial_update': ['cmdb.password.manage'],
        'destroy': ['cmdb.password.manage'],
        'reveal': ['cmdb.password.reveal'],
    }

    def get_required_permissions(self):
        if getattr(self, 'action', None) in {'list', 'retrieve'} and (
            user_has_permissions(self.request.user, ['cmdb.password.manage'])
            or user_has_permissions(self.request.user, ['cmdb.password.reveal'])
        ):
            return []
        return super().get_required_permissions()

    def get_queryset(self):
        queryset = super().get_queryset()
        scoped_items = _apply_ci_authorization_scope(
            ConfigItem.objects.all(),
            self.request.user,
            permission='view',
        )
        return queryset.filter(config_item_id__in=scoped_items.values('id'))

    def perform_create(self, serializer):
        config_item = serializer.validated_data['config_item']
        _ensure_user_can_manage_config_item(self.request.user, config_item)
        username = getattr(self.request.user, 'username', '')
        serializer.save(created_by=username, updated_by=username)

    def perform_update(self, serializer):
        _ensure_user_can_manage_config_item(self.request.user, serializer.instance.config_item)
        serializer.save(updated_by=getattr(self.request.user, 'username', ''))

    def perform_destroy(self, instance):
        _ensure_user_can_manage_config_item(self.request.user, instance.config_item)
        instance.delete()

    def eventwall_related_resources(self, instance):
        return [build_resource('cmdb', 'config_item', instance.config_item_id, instance.config_item.name)]

    def eventwall_metadata(self, instance, action, before=None, after=None):
        return {'config_item_id': instance.config_item_id, 'has_password': bool(instance.password_ciphertext)}

    @action(detail=True, methods=['post'])
    def reveal(self, request, pk=None):
        item = self.get_object()
        verification = ConfigItemPasswordRevealSerializer(data=request.data)
        verification.is_valid(raise_exception=True)
        if not request.user.check_password(verification.validated_data['current_password']):
            raise ValidationError({'current_password': '当前登录密码不正确。'})

        try:
            password = decrypt_config_item_password(item.password_ciphertext)
        except ImproperlyConfigured as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ConfigItemPasswordDecryptionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        record_event(
            request=request,
            module='cmdb',
            category='security',
            action='reveal_password',
            title='查看资产登录密码',
            summary=f'查看资产 {item.config_item.name} 的登录密码',
            result=EventRecord.RESULT_SUCCESS,
            severity=EventRecord.SEVERITY_WARNING,
            resource_type='config_item_password',
            resource_id=item.id,
            resource_name=item.config_item.name,
            business_line=item.config_item.business_line,
            environment=item.config_item.environment,
            related_resources=[build_resource('cmdb', 'config_item', item.config_item_id, item.config_item.name)],
            metadata={'config_item_id': item.config_item_id},
            correlation_id=f'config-item-password:{item.id}',
        )
        response = Response({'username': item.username, 'password': password})
        response['Cache-Control'] = 'no-store, no-cache, max-age=0, must-revalidate'
        response['Pragma'] = 'no-cache'
        return response


class ResourceNodeViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    """资源节点(业务线/环境)树管理"""
    queryset = ResourceNode.objects.all().order_by('sort_order', 'id')
    serializer_class = ResourceNodeSerializer
    filterset_fields = ['node_type', 'parent']
    pagination_class = None
    rbac_permissions = {
        'list': ['cmdb.ci.view'],
        'retrieve': ['cmdb.ci.view'],
        'create': ['cmdb.ci.manage'],
        'update': ['cmdb.ci.manage'],
        'partial_update': ['cmdb.ci.manage'],
        'destroy': ['cmdb.ci.manage'],
        'tree': ['cmdb.ci.view'],
    }

    def get_required_permissions(self):
        if getattr(self, 'action', None) in {'list', 'retrieve', 'tree'} and (
            user_has_permissions(self.request.user, ['cmdb.ci.view'])
            or user_has_permissions(self.request.user, ['cmdb.request.submit'])
            or user_has_permissions(self.request.user, ['cmdb.request.approve'])
        ):
            return []
        return super().get_required_permissions()

    @action(detail=False, methods=['get'])
    def tree(self, request):
        nodes = list(ResourceNode.objects.all().order_by('sort_order', 'id').values())
        node_map = {node['id']: node for node in nodes}
        biz_resource_counts = {
            row['business_node_id']: row['count']
            for row in ConfigItem.objects.filter(business_node__isnull=False).values('business_node_id').annotate(count=Count('id'))
        }
        legacy_biz_resource_counts = {
            row['business_line']: row['count']
            for row in ConfigItem.objects.filter(business_node__isnull=True).exclude(business_line='').values('business_line').annotate(count=Count('id'))
        }
        biz_request_counts = {
            row['business_line']: row['count']
            for row in ResourceRequest.objects.exclude(business_line='').values('business_line').annotate(count=Count('id'))
        }
        env_resource_counts = {
            row['environment_node_id']: row['count']
            for row in ConfigItem.objects.filter(environment_node__isnull=False).values('environment_node_id').annotate(count=Count('id'))
        }
        legacy_env_resource_counts = {
            (row['business_line'], row['environment']): row['count']
            for row in ConfigItem.objects.filter(environment_node__isnull=True).exclude(business_line='').exclude(environment='').values('business_line', 'environment').annotate(count=Count('id'))
        }
        env_request_counts = {
            (row['business_line'], row['environment']): row['count']
            for row in ResourceRequest.objects.exclude(business_line='').exclude(environment='').values('business_line', 'environment').annotate(count=Count('id'))
        }
        business_tree = self._build_tree(
            nodes,
            None,
            node_map,
            biz_resource_counts,
            legacy_biz_resource_counts,
            biz_request_counts,
            env_resource_counts,
            legacy_env_resource_counts,
            env_request_counts,
            root_types={'biz'},
        )
        cloud_tree = self._build_tree(
            nodes,
            None,
            node_map,
            biz_resource_counts,
            legacy_biz_resource_counts,
            biz_request_counts,
            env_resource_counts,
            legacy_env_resource_counts,
            env_request_counts,
            root_types={'cloud_account'},
        )
        if (request.query_params.get('scope') or '').lower() == 'all':
            return Response({'business': business_tree, 'cloud': cloud_tree})
        return Response(business_tree)

    def perform_destroy(self, instance):
        if instance.is_synced:
            raise ValidationError({'detail': '同步来源节点不能删除'})
        if instance.node_type not in {'biz', 'env'} and instance.children.exists():
            raise ValidationError({'detail': '节点下还有子节点，不能直接删除'})
        if instance.node_type == 'biz':
            if instance.children.exists():
                raise ValidationError({'detail': '业务线下还有环境节点，不能直接删除'})
            if ConfigItem.objects.filter(Q(business_node=instance) | Q(business_node__isnull=True, business_line=instance.name)).exists():
                raise ValidationError({'detail': '业务线已关联配置项，不能直接删除'})
            if ResourceRequest.objects.filter(business_line=instance.name).exists():
                raise ValidationError({'detail': '业务线已关联资源申请，不能直接删除'})
        elif instance.node_type == 'env':
            business_line = instance.parent.name if instance.parent else ''
            if ConfigItem.objects.filter(Q(environment_node=instance) | Q(environment_node__isnull=True, business_line=business_line, environment=instance.name)).exists():
                raise ValidationError({'detail': '环境已关联配置项，不能直接删除'})
            if ResourceRequest.objects.filter(business_line=business_line, environment=instance.name).exists():
                raise ValidationError({'detail': '环境已关联资源申请，不能直接删除'})
        elif ConfigItem.objects.filter(resource_node=instance).exists():
            raise ValidationError({'detail': '节点已关联资产，不能直接删除'})
        instance.delete()

    def _build_tree(self, nodes, parent_id, node_map, biz_resource_counts, legacy_biz_resource_counts, biz_request_counts, env_resource_counts, legacy_env_resource_counts, env_request_counts, root_types=None):
        tree = []
        for node in nodes:
            if node['parent_id'] == parent_id:
                if parent_id is None and root_types and node.get('node_type') not in root_types:
                    continue
                children = self._build_tree(nodes, node['id'], node_map, biz_resource_counts, legacy_biz_resource_counts, biz_request_counts, env_resource_counts, legacy_env_resource_counts, env_request_counts)
                if children:
                    node['children'] = children
                node['children_count'] = len(children)
                if node['node_type'] == 'biz':
                    node['resource_count'] = biz_resource_counts.get(node['id'], 0) + legacy_biz_resource_counts.get(node['name'], 0)
                    node['request_count'] = biz_request_counts.get(node['name'], 0)
                else:
                    parent_node = node_map.get(node['parent_id'])
                    biz_name = parent_node['name'] if parent_node else ''
                    node['resource_count'] = env_resource_counts.get(node['id'], 0) + legacy_env_resource_counts.get((biz_name, node['name']), 0)
                    node['request_count'] = env_request_counts.get((biz_name, node['name']), 0)
                tree.append(node)
        return tree

class CIRelationViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    """CI 关系管理"""
    queryset = CIRelation.objects.select_related('source', 'target').all()
    serializer_class = CIRelationSerializer
    filterset_fields = ['source', 'target', 'relation_type']
    rbac_permissions = {
        'list': ['cmdb.ci.view'],
        'retrieve': ['cmdb.ci.view'],
        'create': ['cmdb.ci.manage'],
        'update': ['cmdb.ci.manage'],
        'partial_update': ['cmdb.ci.manage'],
        'destroy': ['cmdb.ci.manage'],
        'bulk_create': ['cmdb.ci.manage'],
        'available_rules': ['cmdb.ci.view'],
    }

    def get_queryset(self):
        permission = 'manage' if getattr(self, 'action', '') in {'update', 'partial_update', 'destroy', 'bulk_create'} else 'view'
        scoped_ci_ids = _apply_ci_authorization_scope(ConfigItem.objects.all(), self.request.user, permission=permission).values('id')
        return super().get_queryset().filter(source_id__in=scoped_ci_ids, target_id__in=scoped_ci_ids)

    def perform_create(self, serializer):
        source = serializer.validated_data.get('source')
        target = serializer.validated_data.get('target')
        if source:
            _ensure_user_can_manage_config_item(self.request.user, source)
        if target:
            _ensure_user_can_manage_config_item(self.request.user, target)
        relation = serializer.save()
        _record_ci_change(
            relation.source,
            'relation_create',
            {},
            _relation_snapshot(relation),
            operator=getattr(self.request.user, 'username', ''),
            source='relation',
        )

    def perform_update(self, serializer):
        source = serializer.validated_data.get('source') or serializer.instance.source
        target = serializer.validated_data.get('target') or serializer.instance.target
        if source:
            _ensure_user_can_manage_config_item(self.request.user, source)
        if target:
            _ensure_user_can_manage_config_item(self.request.user, target)
        serializer.save()

    def perform_destroy(self, instance):
        before = _relation_snapshot(instance)
        source_ci = instance.source
        _record_ci_change(
            source_ci,
            'relation_delete',
            before,
            {},
            operator=getattr(self.request.user, 'username', ''),
            source='relation',
        )
        instance.delete()

    @action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request):
        relation_rows = request.data.get('relations') or request.data.get('items') or []
        if not isinstance(relation_rows, list) or not relation_rows:
            return Response({'relations': ['Please provide a non-empty relation list.']}, status=status.HTTP_400_BAD_REQUEST)
        if len(relation_rows) > 200:
            return Response({'relations': ['A single bulk request supports at most 200 relations.']}, status=status.HTTP_400_BAD_REQUEST)

        created = []
        skipped = []
        errors = []
        operator = getattr(request.user, 'username', '')
        for index, row in enumerate(relation_rows, start=1):
            if not isinstance(row, dict):
                errors.append({'index': index, 'errors': {'detail': 'Relation item must be an object.'}})
                continue
            source_id = row.get('source') or row.get('source_id')
            target_id = row.get('target') or row.get('target_id')
            relation_type = row.get('relation_type')
            if not source_id or not target_id or not relation_type:
                errors.append({'index': index, 'errors': {'detail': 'source, target and relation_type are required.'}})
                continue
            if CIRelation.objects.filter(source_id=source_id, target_id=target_id, relation_type=relation_type).exists():
                skipped.append({
                    'index': index,
                    'source': source_id,
                    'target': target_id,
                    'relation_type': relation_type,
                    'reason': 'duplicate',
                })
                continue

            serializer = self.get_serializer(data={
                'source': source_id,
                'target': target_id,
                'relation_type': relation_type,
                'description': row.get('description') or request.data.get('description') or '',
                'evidence_source': row.get('evidence_source') or request.data.get('evidence_source') or 'manual',
                'confidence': row.get('confidence') if row.get('confidence') is not None else request.data.get('confidence', 100),
                'evidence': row.get('evidence') or request.data.get('evidence') or {},
            })
            if not serializer.is_valid():
                errors.append({'index': index, 'errors': serializer.errors})
                continue
            source = serializer.validated_data.get('source')
            target = serializer.validated_data.get('target')
            try:
                _ensure_user_can_manage_config_item(request.user, source)
                _ensure_user_can_manage_config_item(request.user, target)
            except PermissionDenied:
                errors.append({'index': index, 'errors': {'detail': 'Permission denied for relation scope.'}})
                continue

            relation = serializer.save()
            snapshot = _relation_snapshot(relation)
            _record_ci_change(
                relation.source,
                'relation_create',
                {},
                snapshot,
                operator=operator,
                source='relation',
            )
            created.append(snapshot)

        return Response({
            'summary': {
                'total': len(relation_rows),
                'created': len(created),
                'skipped': len(skipped),
                'errors': len(errors),
            },
            'created': created,
            'skipped': skipped,
            'errors': errors,
        })

    @action(detail=False, methods=['get'], url_path='available-rules')
    def available_rules(self, request):
        ci_id = request.query_params.get('ci') or request.query_params.get('source')
        direction = request.query_params.get('direction') or 'outgoing'
        ci = _apply_ci_authorization_scope(
            ConfigItem.objects.select_related('ci_type').all(),
            request.user,
            permission='view',
        ).filter(id=ci_id).first()
        if not ci:
            return Response({'detail': '配置项不存在或无权查看'}, status=status.HTTP_404_NOT_FOUND)

        if direction == 'incoming':
            rules = CIRelationRule.objects.filter(target_type=ci.ci_type, is_active=True).select_related('source_type', 'target_type')
        else:
            rules = CIRelationRule.objects.filter(source_type=ci.ci_type, is_active=True).select_related('source_type', 'target_type')
        rows = []
        for rule in rules.order_by('relation_type', 'target_type__name', 'source_type__name'):
            rows.append({
                'id': rule.id,
                'direction': direction,
                'relation_type': rule.relation_type,
                'source_type': rule.source_type_id,
                'source_type_name': rule.source_type.name,
                'target_type': rule.target_type_id,
                'target_type_name': rule.target_type.name,
                'peer_type': rule.source_type_id if direction == 'incoming' else rule.target_type_id,
                'peer_type_name': rule.source_type.name if direction == 'incoming' else rule.target_type.name,
                'required': rule.required,
                'multiple': rule.multiple,
                'description': rule.description,
            })
        return Response(rows)


class CIRelationRuleViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = CIRelationRule.objects.select_related('source_type', 'target_type').all()
    serializer_class = CIRelationRuleSerializer
    pagination_class = None
    filterset_fields = ['source_type', 'target_type', 'relation_type', 'is_active']
    rbac_permissions = {
        'list': ['cmdb.model.view'],
        'retrieve': ['cmdb.model.view'],
        'create': ['cmdb.model.manage'],
        'update': ['cmdb.model.manage'],
        'partial_update': ['cmdb.model.manage'],
        'destroy': ['cmdb.model.manage'],
    }

    def perform_create(self, serializer):
        rule = serializer.save()
        _record_ci_change(
            None,
            'relation_rule_create',
            {},
            _relation_rule_snapshot(rule),
            operator=getattr(self.request.user, 'username', ''),
            source='model',
        )

    def perform_update(self, serializer):
        before = _relation_rule_snapshot(serializer.instance)
        rule = serializer.save()
        after = _relation_rule_snapshot(rule)
        if _dict_diff(before, after):
            _record_ci_change(
                None,
                'relation_rule_update',
                before,
                after,
                operator=getattr(self.request.user, 'username', ''),
                source='model',
            )

    def perform_destroy(self, instance):
        before = _relation_rule_snapshot(instance)
        _record_ci_change(
            None,
            'relation_rule_delete',
            before,
            {},
            operator=getattr(self.request.user, 'username', ''),
            source='model',
        )
        instance.delete()


class CISourceMappingViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = CISourceMapping.objects.select_related('ci', 'ci__ci_type').all().order_by('-updated_at', '-id')
    serializer_class = CISourceMappingSerializer
    search_fields = ['source_type', 'source_account', 'source_region', 'source_unique_id', 'ci__name']
    filterset_fields = ['source_type', 'source_account', 'source_region', 'sync_status', 'ci']
    rbac_permissions = {
        'list': ['cmdb.sync.view'],
        'account_region_options': ['cmdb.ci.view'],
        'retrieve': ['cmdb.sync.view'],
        'create': ['cmdb.sync.manage'],
        'update': ['cmdb.sync.manage'],
        'partial_update': ['cmdb.sync.manage'],
        'destroy': ['cmdb.sync.manage'],
    }

    def get_queryset(self):
        permission = 'manage' if getattr(self, 'action', '') in {'update', 'partial_update', 'destroy'} else 'view'
        scoped_ci_ids = _apply_ci_authorization_scope(ConfigItem.objects.all(), self.request.user, permission=permission).values('id')
        return super().get_queryset().filter(ci_id__in=scoped_ci_ids)

    @action(detail=False, methods=['get'], url_path='account-region-options')
    def account_region_options(self, request):
        pairs = self.get_queryset().exclude(source_account='').values(
            'source_account',
            'source_region',
        ).distinct().order_by('source_account', 'source_region')
        return Response(list(pairs))

    def perform_create(self, serializer):
        ci = serializer.validated_data.get('ci')
        if ci:
            _ensure_user_can_manage_config_item(self.request.user, ci)
        mapping = serializer.save()
        _record_ci_change(
            mapping.ci,
            'source_mapping_create',
            {},
            _source_mapping_snapshot(mapping),
            operator=getattr(self.request.user, 'username', ''),
            source='source_mapping',
        )

    def perform_update(self, serializer):
        ci = serializer.validated_data.get('ci') or serializer.instance.ci
        if ci:
            _ensure_user_can_manage_config_item(self.request.user, ci)
        before = _source_mapping_snapshot(serializer.instance)
        mapping = serializer.save()
        after = _source_mapping_snapshot(mapping)
        if _dict_diff(before, after):
            _record_ci_change(
                mapping.ci,
                'source_mapping_update',
                before,
                after,
                operator=getattr(self.request.user, 'username', ''),
                source='source_mapping',
            )

    def perform_destroy(self, instance):
        before = _source_mapping_snapshot(instance)
        _record_ci_change(
            instance.ci,
            'source_mapping_delete',
            before,
            {},
            operator=getattr(self.request.user, 'username', ''),
            source='source_mapping',
        )
        instance.delete()


class CIThresholdPolicyViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = CIThresholdPolicy.objects.select_related('resource_type').all().order_by('resource_type_id', 'metric')
    serializer_class = CIThresholdPolicySerializer
    filterset_fields = ['resource_type', 'metric', 'enabled']
    rbac_permissions = {
        'list': ['cmdb.ci.view'],
        'retrieve': ['cmdb.ci.view'],
        'create': ['cmdb.ci.manage'],
        'update': ['cmdb.ci.manage'],
        'partial_update': ['cmdb.ci.manage'],
        'destroy': ['cmdb.ci.manage'],
    }

    def perform_create(self, serializer):
        policy = serializer.save()
        _record_ci_change(
            None,
            'threshold_policy_create',
            {},
            _threshold_policy_snapshot(policy),
            operator=getattr(self.request.user, 'username', ''),
            source='threshold_policy',
        )

    def perform_update(self, serializer):
        before = _threshold_policy_snapshot(serializer.instance)
        policy = serializer.save()
        after = _threshold_policy_snapshot(policy)
        if _dict_diff(before, after):
            _record_ci_change(
                None,
                'threshold_policy_update',
                before,
                after,
                operator=getattr(self.request.user, 'username', ''),
                source='threshold_policy',
            )

    def perform_destroy(self, instance):
        before = _threshold_policy_snapshot(instance)
        _record_ci_change(
            None,
            'threshold_policy_delete',
            before,
            {},
            operator=getattr(self.request.user, 'username', ''),
            source='threshold_policy',
        )
        instance.delete()


class CIResourceMetricSnapshotPagination(PageNumberPagination):
    page_size_query_param = 'page_size'
    max_page_size = 1000


class CIResourceMetricSnapshotViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = CIResourceMetricSnapshot.objects.select_related('ci', 'ci__ci_type').all()
    serializer_class = CIResourceMetricSnapshotSerializer
    pagination_class = CIResourceMetricSnapshotPagination
    search_fields = ['ci__name', 'metric', 'source']
    filterset_fields = ['ci', 'metric', 'source']
    rbac_permissions = {
        'list': ['cmdb.ci.view'],
        'retrieve': ['cmdb.ci.view'],
        'create': ['cmdb.ci.manage'],
        'update': ['cmdb.ci.manage'],
        'partial_update': ['cmdb.ci.manage'],
        'destroy': ['cmdb.ci.manage'],
        'latest': ['cmdb.ci.view'],
        'refresh_current_page': ['cmdb.sync.manage'],
    }

    def _csv_query_values(self, *names):
        values = []
        for name in names:
            for raw in self.request.query_params.getlist(name):
                values.extend(str(raw or '').replace(';', ',').split(','))
        return [item.strip() for item in values if item and item.strip()]

    def get_queryset(self):
        permission = 'manage' if getattr(self, 'action', '') in {'update', 'partial_update', 'destroy'} else 'view'
        scoped_ci_ids = _apply_ci_authorization_scope(ConfigItem.objects.all(), self.request.user, permission=permission).values('id')
        qs = super().get_queryset().filter(ci_id__in=scoped_ci_ids)
        collected_after = str(self.request.query_params.get('collected_after') or '').strip()
        if collected_after:
            parsed_collected_after = parse_datetime(collected_after)
            if parsed_collected_after:
                if timezone.is_naive(parsed_collected_after):
                    parsed_collected_after = timezone.make_aware(parsed_collected_after)
                qs = qs.filter(collected_at__gte=parsed_collected_after)
        collected_before = str(self.request.query_params.get('collected_before') or '').strip()
        if collected_before:
            parsed_collected_before = parse_datetime(collected_before)
            if parsed_collected_before:
                if timezone.is_naive(parsed_collected_before):
                    parsed_collected_before = timezone.make_aware(parsed_collected_before)
                qs = qs.filter(collected_at__lte=parsed_collected_before)
        raw_ci_ids = self._csv_query_values('ci_ids', 'ids')
        if raw_ci_ids:
            ci_ids = []
            for item in raw_ci_ids:
                try:
                    ci_ids.append(int(item))
                except (TypeError, ValueError):
                    continue
            if ci_ids:
                qs = qs.filter(ci_id__in=list(dict.fromkeys(ci_ids)))
        metric_names = self._csv_query_values('metrics', 'metric_in')
        if metric_names:
            qs = qs.filter(metric__in=list(dict.fromkeys(metric_names)))
        return qs

    @action(detail=False, methods=['get'], url_path='latest')
    def latest(self, request):
        qs = self.filter_queryset(self.get_queryset())
        metric_names = self._csv_query_values('metrics', 'metric_in') or CONFIG_ITEM_WATERLINE_METRICS
        ci_ids = qs.order_by().values('ci_id').distinct()
        rows = latest_metric_snapshots(ci_ids, metric_names, queryset=qs)
        serializer = self.get_serializer(rows, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='refresh-current-page')
    def refresh_current_page(self, request):
        ci_ids = _request_int_list(request.data, 'ci_ids', 'ids', limit=100)
        if not ci_ids:
            return Response({'detail': '请选择需要刷新资源水位的资产'}, status=400)

        scoped_ci_qs = _apply_ci_authorization_scope(
            ConfigItem.objects.select_related('ci_type').prefetch_related('source_mappings'),
            request.user,
            permission='manage',
        ).filter(id__in=ci_ids)
        ci_rows = list(scoped_ci_qs)
        if not ci_rows:
            return Response({'detail': '未找到可刷新的资产'}, status=404)

        job_targets = {}
        skipped = []
        for ci in ci_rows:
            mappings = _source_mapping_rows_for_waterline_refresh(ci)
            if not mappings:
                skipped.append({'ci_id': ci.id, 'name': ci.name, 'reason': '未找到支持实时水位采集的来源映射'})
                continue
            matched = False
            for mapping in mappings:
                job = _sync_job_for_waterline_mapping(mapping)
                if not job:
                    continue
                target = job_targets.setdefault(job.id, {'job': job, 'source_unique_ids': set(), 'ci_ids': set()})
                target['source_unique_ids'].add(_mapping_value(mapping, 'source_unique_id'))
                target['ci_ids'].add(ci.id)
                matched = True
            if not matched:
                skipped.append({'ci_id': ci.id, 'name': ci.name, 'reason': '未找到对应的同步任务'})

        total_summary = defaultdict(int)
        records = []
        executed_jobs = []
        operator = getattr(request.user, 'username', '')
        for target in job_targets.values():
            job = target['job']
            try:
                items = _items_for_sync_job(job, request.data)
            except ValueError as exc:
                return Response({'detail': str(exc)}, status=400)
            except Exception as exc:
                message = _sync_collection_error_message(exc)
                result = _mark_sync_job_collection_failed(job, exc)
                return Response({
                    'detail': message,
                    'summary': result['summary'],
                    'records': CISyncRecordSerializer(result['records'], many=True).data,
                    'error_message': result['error_message'],
                }, status=400)

            filtered_items = _filter_sync_items_for_source_unique_ids(job, items, target['source_unique_ids'])
            if not filtered_items:
                skipped.extend([
                    {'ci_id': ci_id, 'name': '', 'reason': '本次采集未返回当前页资源'}
                    for ci_id in sorted(target['ci_ids'])
                ])
                continue
            result = _run_sync_items(
                job,
                filtered_items,
                operator=operator,
                user=request.user,
                create_missing_archive_candidates=False,
            )
            for key, value in result['summary'].items():
                total_summary[key] += int(value or 0)
            records.extend(result['records'])
            executed_jobs.append({
                'id': job.id,
                'name': job.name,
                'source_type': job.source_type,
                'requested_count': len(target['ci_ids']),
                'matched_count': len(filtered_items),
                'summary': result['summary'],
            })

        latest_rows = _latest_metric_snapshot_rows_for_ci_ids([ci.id for ci in ci_rows])
        return Response({
            'requested_count': len(ci_rows),
            'executed_job_count': len(executed_jobs),
            'refreshed_count': sum(item['matched_count'] for item in executed_jobs),
            'skipped_count': len(skipped),
            'summary': dict(total_summary),
            'jobs': executed_jobs,
            'skipped': skipped,
            'records': CISyncRecordSerializer(records, many=True).data,
            'latest_metrics': self.get_serializer(latest_rows, many=True).data,
        })

    def perform_create(self, serializer):
        ci = serializer.validated_data.get('ci')
        if ci:
            _ensure_user_can_manage_config_item(self.request.user, ci)
        metric = serializer.save()
        _record_ci_change(
            metric.ci,
            'resource_metric_create',
            {},
            _resource_metric_snapshot(metric),
            operator=getattr(self.request.user, 'username', ''),
            source='resource_metric',
        )

    def perform_update(self, serializer):
        ci = serializer.validated_data.get('ci') or serializer.instance.ci
        if ci:
            _ensure_user_can_manage_config_item(self.request.user, ci)
        before = _resource_metric_snapshot(serializer.instance)
        metric = serializer.save()
        after = _resource_metric_snapshot(metric)
        if _dict_diff(before, after):
            _record_ci_change(
                metric.ci,
                'resource_metric_update',
                before,
                after,
                operator=getattr(self.request.user, 'username', ''),
                source='resource_metric',
            )

    def perform_destroy(self, instance):
        before = _resource_metric_snapshot(instance)
        _record_ci_change(
            instance.ci,
            'resource_metric_delete',
            before,
            {},
            operator=getattr(self.request.user, 'username', ''),
            source='resource_metric',
        )
        instance.delete()


class CIChangeLogViewSet(RBACPermissionMixin, viewsets.ReadOnlyModelViewSet):
    queryset = CIChangeLog.objects.select_related('ci').all()
    serializer_class = CIChangeLogSerializer
    search_fields = [
        'ci__name',
        'action',
        'operator',
        'source',
        'before__name',
        'before__title',
        'after__name',
        'after__title',
    ]
    filterset_fields = ['ci', 'action', 'operator', 'source']
    rbac_permissions = {
        'list': ['cmdb.audit.view'],
        'retrieve': ['cmdb.audit.view'],
        'summary': ['cmdb.audit.view'],
    }

    def get_queryset(self):
        qs = super().get_queryset()
        scope_q = _ci_scope_q_for_user(self.request.user, permission='view')
        if scope_q is not None:
            scoped_ids = ConfigItem.objects.filter(scope_q).values('id')
            audit_scope_q = Q(ci_id__in=scoped_ids)
            if _user_can_view_platform_change_logs(self.request.user):
                audit_scope_q |= Q(ci__isnull=True)
            qs = qs.filter(audit_scope_q)
        start = self.request.query_params.get('start') or self.request.query_params.get('created_after')
        end = self.request.query_params.get('end') or self.request.query_params.get('created_before')
        if start:
            start_dt = parse_datetime(start)
            if not start_dt:
                start_date = parse_date(start)
                if start_date:
                    start_dt = datetime.combine(start_date, datetime.min.time())
            if start_dt:
                if timezone.is_naive(start_dt):
                    start_dt = timezone.make_aware(start_dt)
                qs = qs.filter(created_at__gte=start_dt)
        if end:
            end_dt = parse_datetime(end)
            if not end_dt:
                end_date = parse_date(end)
                if end_date:
                    end_dt = datetime.combine(end_date, datetime.max.time())
            if end_dt:
                if timezone.is_naive(end_dt):
                    end_dt = timezone.make_aware(end_dt)
                qs = qs.filter(created_at__lte=end_dt)
        request_id = (self.request.query_params.get('request_id') or '').strip()
        if request_id:
            request_id_values = [request_id]
            if request_id.isdigit():
                request_id_values.append(int(request_id))
            request_scope_q = Q()
            for value in request_id_values:
                request_scope_q |= Q(before__id=value) | Q(after__id=value)
            qs = qs.filter(Q(ci__isnull=True) & request_scope_q)
        return qs

    @action(detail=False, methods=['get'])
    def summary(self, request):
        qs = self.filter_queryset(self.get_queryset())
        action_counts = list(qs.values('action').annotate(count=Count('id')).order_by('-count', 'action'))
        operator_counts = list(qs.values('operator').annotate(count=Count('id')).order_by('-count', 'operator')[:8])
        source_counts = list(qs.values('source').annotate(count=Count('id')).order_by('-count', 'source'))
        latest = qs.order_by('-created_at').values_list('created_at', flat=True).first()
        return Response({
            'total': qs.count(),
            'action_counts': action_counts,
            'operator_counts': operator_counts,
            'source_counts': source_counts,
            'latest_at': latest,
        })


class CISyncJobPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 500


class CISyncJobViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = CISyncJob.objects.annotate(record_count=Count('records')).all()
    serializer_class = CISyncJobSerializer
    pagination_class = CISyncJobPagination
    search_fields = ['name', 'source_type', 'created_by']
    filterset_fields = ['source_type', 'status', 'mode', 'dry_run']
    rbac_permissions = {
        'list': ['cmdb.sync.view'],
        'retrieve': ['cmdb.sync.view'],
        'create': ['cmdb.sync.manage'],
        'update': ['cmdb.sync.manage'],
        'partial_update': ['cmdb.sync.manage'],
        'destroy': ['cmdb.sync.manage'],
        'dry_run': ['cmdb.sync.manage'],
        'run': ['cmdb.sync.manage'],
        'run_due': ['cmdb.sync.manage'],
        'retry_failed': ['cmdb.sync.manage'],
        'records': ['cmdb.sync.view'],
        'collection_toggle': ['cmdb.sync.manage'],
    }

    def get_queryset(self):
        action_name = getattr(self, 'action', '')
        can_manage_sync = user_has_permissions(self.request.user, ['cmdb.sync.manage'])
        permission = 'manage' if action_name in {
            'update',
            'partial_update',
            'destroy',
            'dry_run',
            'run',
            'run_due',
            'retry_failed',
            'collection_toggle',
        } else 'view'
        visible_record_ids = _sync_record_queryset_for_user(
            self.request.user,
            permission=permission,
            include_global=(
                user_has_permissions(self.request.user, ['cmdb.sync.view'])
                or can_manage_sync
            ),
        ).values('id')
        queryset = CISyncJob.objects.annotate(
            record_count=Count('records', filter=Q(records__id__in=visible_record_ids), distinct=True)
        ).order_by('-updated_at', '-id')
        if can_manage_sync:
            return queryset
        return queryset.filter(records__id__in=visible_record_ids).distinct()

    def perform_create(self, serializer):
        job = serializer.save(created_by=getattr(self.request.user, 'username', ''))
        _record_ci_change(
            None,
            'sync_job_create',
            {},
            _sync_job_snapshot(job),
            operator=getattr(self.request.user, 'username', ''),
            source='sync_job',
        )

    def perform_update(self, serializer):
        before = _sync_job_snapshot(serializer.instance)
        job = serializer.save()
        after = _sync_job_snapshot(job)
        if _dict_diff(before, after):
            _record_ci_change(
                None,
                'sync_job_update',
                before,
                after,
                operator=getattr(self.request.user, 'username', ''),
                source='sync_job',
            )

    def perform_destroy(self, instance):
        before = _sync_job_snapshot(instance)
        _record_ci_change(
            None,
            'sync_job_delete',
            before,
            {},
            operator=getattr(self.request.user, 'username', ''),
            source='sync_job',
        )
        instance.delete()

    @action(detail=True, methods=['post'], url_path='dry-run')
    def dry_run(self, request, pk=None):
        job = self.get_object()
        try:
            items = _items_for_sync_job(job, request.data)
            preview = _preview_sync_items(job, items, user=request.user)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        except Exception as exc:
            return Response({'detail': _sync_collection_error_message(exc)}, status=400)
        return Response(preview)

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        job = self.get_object()
        batch_id = uuid.uuid4().hex
        _mark_sync_job_collection_running(job)
        try:
            items = _items_for_sync_job(job, request.data)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        except Exception as exc:
            result = _mark_sync_job_collection_failed(job, exc, batch_id=batch_id)
            return Response({
                'summary': result['summary'],
                'records': CISyncRecordSerializer(result['records'], many=True).data,
                'error_message': result['error_message'],
            })
        result = _run_sync_items(job, items, operator=getattr(request.user, 'username', ''), user=request.user, batch_id=batch_id)
        return Response({
            'summary': result['summary'],
            'records': CISyncRecordSerializer(result['records'], many=True).data,
        })

    @action(detail=False, methods=['post'], url_path='run-due')
    def run_due(self, request):
        due_jobs = _due_collection_jobs()
        limit = request.data.get('limit')
        if limit not in (None, ''):
            try:
                limit = max(1, min(int(limit), 50))
                due_jobs = due_jobs[:limit]
            except (TypeError, ValueError):
                return Response({'detail': 'limit 必须是正整数'}, status=400)

        executed = []
        total_summary = defaultdict(int)
        for job in due_jobs:
            batch_id = uuid.uuid4().hex
            try:
                _mark_sync_job_collection_running(job)
                items = _items_for_sync_job(job, {})
                result = _run_sync_items(job, items, operator=getattr(request.user, 'username', ''), user=request.user, batch_id=batch_id)
                summary = result['summary']
                status_text = job.status
                error_message = ''
            except Exception as exc:
                result = _mark_sync_job_collection_failed(job, exc, batch_id=batch_id)
                summary = result['summary']
                status_text = 'failed'
                error_message = result['error_message']
            for key, value in summary.items():
                total_summary[key] += int(value or 0)
            executed.append({
                'id': job.id,
                'name': job.name,
                'source_type': job.source_type,
                'status': status_text,
                'summary': summary,
                'error_message': error_message,
            })

        return Response({
            'executed_count': len(executed),
            'summary': dict(total_summary),
            'jobs': executed,
            'collection': _build_collection_summary(user=request.user),
        })

    @action(detail=True, methods=['get'])
    def records(self, request, pk=None):
        job = self.get_object()
        records = _sync_record_queryset_for_user(request.user).filter(job=job)
        serializer = CISyncRecordSerializer(records, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='collection-toggle')
    def collection_toggle(self, request, pk=None):
        job = self.get_object()
        before = _sync_job_snapshot(job)
        config = dict(job.config or {})
        config['collection_enabled'] = _to_bool(request.data.get('enabled'))
        job.config = config
        job.save(update_fields=['config', 'updated_at'])
        after = _sync_job_snapshot(job)
        if _dict_diff(before, after):
            _record_ci_change(
                None,
                'sync_job_update',
                before,
                after,
                operator=getattr(request.user, 'username', ''),
                source='sync_job',
            )
        return Response(CISyncJobSerializer(job).data)

    @action(detail=True, methods=['post'], url_path='retry-failed')
    def retry_failed(self, request, pk=None):
        job = self.get_object()
        failed_records = []
        relation_records = []
        skipped_count = 0
        retryable_qs = _sync_record_queryset_for_user(
            request.user,
            permission='manage',
            include_global=user_has_permissions(request.user, ['cmdb.sync.manage']),
        ).filter(
            Q(status='failed') | Q(after___sync_relations__failed__gt=0),
            job=job,
        ).order_by('created_at', 'id')
        for record in retryable_qs:
            if record.retry_status == 'success':
                skipped_count += 1
                continue
            if record.status == 'failed':
                if isinstance(record.after, dict) and record.after:
                    failed_records.append(record)
                else:
                    skipped_count += 1
                continue
            if int(_sync_record_relation_summary(record).get('failed') or 0) > 0 and record.ci_id:
                relation_records.append(record)
                continue
            skipped_count += 1

        if not failed_records and not relation_records:
            return Response({'summary': {'skipped': skipped_count} if skipped_count else {}, 'records': []})

        operator = getattr(request.user, 'username', '')
        summary = defaultdict(int)
        records = []
        if failed_records:
            failed_payloads = [record.after for record in failed_records]
            result = _run_sync_items(job, failed_payloads, operator=operator, user=request.user)
            _mark_failed_records_from_retry_result(failed_records, result['records'][:len(failed_records)], operator=operator)
            for key, value in result['summary'].items():
                summary[key] += value
            records.extend(result['records'])

        for record in relation_records:
            result = _retry_sync_record_relations(record, job=job, operator=operator)
            if result.get('skipped'):
                skipped_count += 1
                continue
            for key, value in (result.get('summary') or {}).items():
                summary[key] += value
            records.append(result['record'])

        if skipped_count:
            summary['skipped'] = skipped_count
        return Response({
            'summary': dict(summary),
            'records': CISyncRecordSerializer(records, many=True).data,
        })


def _sync_record_relation_summary(record):
    after = record.after if isinstance(record.after, dict) else {}
    summary = after.get('_sync_relations') if isinstance(after, dict) else {}
    return summary if isinstance(summary, dict) else {}


def _sync_record_relation_errors(record):
    summary = _sync_record_relation_summary(record)
    errors = summary.get('errors') if isinstance(summary.get('errors'), list) else []
    return [item for item in errors if isinstance(item, dict)]


def _sync_relation_error_rules(record, error):
    ci = record.ci
    if not ci:
        return []
    relation_type = error.get('relation_type') or 'depends_on'
    direction = (error.get('direction') or '').lower()
    hint = error.get('hint') if isinstance(error.get('hint'), dict) else {}
    peer_role = error.get('peer_role') or ('source' if direction == 'incoming' else 'target')
    peer = _sync_relation_peer_payload(hint, peer_role) if hint else {}
    peer_type = _sync_relation_peer_type(hint, peer, peer_role) if hint else None

    rules = CIRelationRule.objects.select_related('source_type', 'target_type').filter(
        relation_type=relation_type,
        is_active=True,
    )
    if direction == 'incoming':
        rules = rules.filter(target_type=ci.ci_type)
        if peer_type:
            rules = rules.filter(source_type=peer_type)
    elif direction == 'outgoing':
        rules = rules.filter(source_type=ci.ci_type)
        if peer_type:
            rules = rules.filter(target_type=peer_type)
    else:
        rules = rules.filter(Q(source_type=ci.ci_type) | Q(target_type=ci.ci_type))
        if peer_type:
            rules = rules.filter(Q(source_type=peer_type) | Q(target_type=peer_type))
    return list(rules.order_by('id')[:5])


def _sync_relation_issue_direction(record, rule, error):
    direction = (error.get('direction') or '').lower()
    if direction in {'incoming', 'outgoing'}:
        return direction
    return 'outgoing' if rule.source_type_id == record.ci.ci_type_id else 'incoming'


def _relation_candidate_row(candidate, *, score=0, reasons=None):
    return {
        'id': candidate.id,
        'name': candidate.name,
        'ci_type': candidate.ci_type_id,
        'ci_type_name': normalize_ci_type_name(candidate.ci_type.name),
        'business_line': candidate.business_line,
        'environment': candidate.environment,
        'environment_display': candidate.get_environment_display() if candidate.environment else '',
        'admin_user': candidate.admin_user,
        'status': candidate.status,
        'status_display': candidate.get_status_display(),
        'score': min(score, 100),
        'reasons': (reasons or [])[:4],
    }


def _sync_relation_existing_issue_relation(record, rule, direction):
    if direction == 'incoming':
        return CIRelation.objects.select_related('source', 'source__ci_type', 'target', 'target__ci_type').filter(
            source__ci_type=rule.source_type,
            target=record.ci,
            relation_type=rule.relation_type,
        ).order_by('id').first()
    return CIRelation.objects.select_related('source', 'source__ci_type', 'target', 'target__ci_type').filter(
        source=record.ci,
        target__ci_type=rule.target_type,
        relation_type=rule.relation_type,
    ).order_by('id').first()


def _sync_record_relation_candidate_issues(record, user=None, limit=5):
    if not record.ci_id:
        return []
    issues = []
    for error in _sync_record_relation_errors(record):
        if error.get('reason') != 'peer_not_found':
            continue
        hint = error.get('hint') if isinstance(error.get('hint'), dict) else {}
        peer_role = error.get('peer_role') or ('source' if (error.get('direction') or '').lower() == 'incoming' else 'target')
        current_source = _source_values(
            record.after if isinstance(record.after, dict) else {},
            default_source_type=(record.job.source_type if record.job_id else 'manual'),
        )
        for rule in _sync_relation_error_rules(record, error):
            direction = _sync_relation_issue_direction(record, rule, error)
            existing_relation = _sync_relation_existing_issue_relation(record, rule, direction)
            if existing_relation:
                peer_ci = existing_relation.source if direction == 'incoming' else existing_relation.target
                candidates = [_relation_candidate_row(peer_ci, score=100, reasons=['已有关系'])]
            else:
                candidates = _relation_candidate_suggestions(
                    record.ci,
                    rule,
                    direction,
                    user=user,
                    limit=limit,
                    hint=hint,
                    peer_role=peer_role,
                    current_source=current_source,
                )
            issues.append({
                'index': error.get('index'),
                'reason': error.get('reason'),
                'relation_type': error.get('relation_type') or rule.relation_type,
                'direction': direction,
                'peer_type': rule.source_type_id if direction == 'incoming' else rule.target_type_id,
                'peer_type_name': normalize_ci_type_name(rule.source_type.name if direction == 'incoming' else rule.target_type.name),
                'relation_rule_id': rule.id,
                'hint': hint,
                'existing_relation_id': existing_relation.id if existing_relation else None,
                'candidates': candidates,
                'candidate_count': len(candidates),
                'best_candidate': candidates[0] if candidates else None,
            })
    return issues


def _sync_record_mark_relation_resolved(record, *, error_index, relation, action='manual_resolve', created_delta=1, skipped_delta=0):
    after = dict(record.after or {})
    summary = dict(after.get('_sync_relations') or {})
    errors = [
        item for item in (summary.get('errors') or [])
        if not (isinstance(item, dict) and str(item.get('index')) == str(error_index))
    ]
    summary['errors'] = errors
    summary['failed'] = max(0, int(summary.get('failed') or 0) - 1)
    summary['created'] = int(summary.get('created') or 0) + created_delta
    if skipped_delta:
        summary['skipped'] = int(summary.get('skipped') or 0) + skipped_delta
    relation_rows = list(summary.get('relations') or [])
    relation_rows.append({**_relation_snapshot(relation), 'action': action})
    summary['relations'] = relation_rows
    resolved_rows = list(summary.get('resolved') or [])
    resolved_rows.append({
        'index': error_index,
        'relation_id': relation.id,
        'action': action,
        'resolved_at': timezone.now().isoformat(),
    })
    summary['resolved'] = resolved_rows
    after['_sync_relations'] = summary
    record.after = after
    record.save(update_fields=['after'])
    return summary


def _sync_record_create_relation_from_candidate(record, issue, candidate, request):
    try:
        peer_ci = ConfigItem.objects.select_related('ci_type').get(pk=candidate['id'])
    except ConfigItem.DoesNotExist:
        raise ValidationError({'candidate_id': ['候选资源不存在。']})
    _ensure_user_can_manage_config_item(request.user, record.ci)
    _ensure_user_can_manage_config_item(request.user, peer_ci)
    direction = issue['direction']
    relation_source = peer_ci if direction == 'incoming' else record.ci
    relation_target = record.ci if direction == 'incoming' else peer_ci
    existing_relation = CIRelation.objects.filter(
        source=relation_source,
        target=relation_target,
        relation_type=issue['relation_type'],
    ).first()
    if existing_relation:
        summary = _sync_record_mark_relation_resolved(
            record,
            error_index=issue.get('index'),
            relation=existing_relation,
            action='already_exists',
            created_delta=0,
            skipped_delta=1,
        )
        return existing_relation, summary
    confidence = max(0, min(int(request.data.get('confidence') or candidate.get('score') or 85), 100))
    payload = {
        'source': relation_source.id,
        'target': relation_target.id,
        'relation_type': issue['relation_type'],
        'description': request.data.get('description') or f"由同步关系失败治理创建：{record.job.name if record.job_id else record.id}",
        'evidence_source': 'governance',
        'confidence': confidence,
        'evidence': {
            'source': 'sync_relation_issue',
            'sync_record_id': record.id,
            'sync_job_id': record.job_id,
            'error_index': issue.get('index'),
            'candidate_id': peer_ci.id,
            'candidate_reasons': candidate.get('reasons') or [],
            'hint': issue.get('hint') or {},
        },
    }
    serializer = CIRelationSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    relation = serializer.save()
    snapshot = _relation_snapshot(relation)
    _record_ci_change(
        relation.source,
        'relation_create',
        {},
        snapshot,
        operator=getattr(request.user, 'username', ''),
        source='governance',
    )
    summary = _sync_record_mark_relation_resolved(record, error_index=issue.get('index'), relation=relation)
    return relation, summary


class CISyncRecordViewSet(RBACPermissionMixin, viewsets.ReadOnlyModelViewSet):
    queryset = CISyncRecord.objects.select_related('job', 'ci').all()
    serializer_class = CISyncRecordSerializer
    search_fields = ['source_unique_id', 'error_message', 'ci__name']
    filterset_fields = ['job', 'batch_id', 'action', 'status', 'ci']
    rbac_permissions = {
        'list': ['cmdb.sync.view'],
        'retrieve': ['cmdb.sync.view'],
        'retry': ['cmdb.sync.manage'],
        'ignore': ['cmdb.sync.manage'],
        'resolve_to_ci': ['cmdb.sync.manage'],
        'relation_candidates': ['cmdb.sync.view'],
        'resolve_relation': ['cmdb.sync.manage'],
        'bulk_resolve_relations': ['cmdb.sync.manage'],
    }

    def get_queryset(self):
        if getattr(self, 'action', '') in {'retry', 'ignore', 'resolve_to_ci', 'resolve_relation', 'bulk_resolve_relations'}:
            qs = _sync_record_queryset_for_user(
                self.request.user,
                permission='manage',
                include_global=user_has_permissions(self.request.user, ['cmdb.sync.manage']),
            )
        else:
            qs = _sync_record_queryset_for_user(self.request.user)
        if str(self.request.query_params.get('relation_issue') or '').lower() in {'1', 'true', 'yes'}:
            qs = qs.filter(after___sync_relations__failed__gt=0)
        return qs

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        record = self.get_object()
        if record.status != 'failed':
            return Response({'detail': '只能重试失败的同步记录'}, status=400)
        if not isinstance(record.after, dict) or not record.after:
            return Response({'detail': '同步记录缺少可重试的原始数据'}, status=400)
        operator = getattr(request.user, 'username', '')
        result = _run_sync_items(record.job, [record.after], operator=operator, user=request.user)
        _mark_sync_record_retry(record, result['records'][0] if result['records'] else None, operator=operator)
        return Response({
            'summary': result['summary'],
            'records': CISyncRecordSerializer(result['records'], many=True).data,
        })

    @action(detail=True, methods=['post'])
    def ignore(self, request, pk=None):
        record = self.get_object()
        if record.status not in {'failed', 'conflict'}:
            return Response({'detail': '只能忽略失败或冲突的同步记录'}, status=status.HTTP_400_BAD_REQUEST)
        note = str(request.data.get('note') or '人工忽略同步治理项').strip()[:200]
        before = {
            'sync_record_id': record.id,
            'status': record.status,
            'error_message': record.error_message,
        }
        record.status = 'ignored'
        record.retry_status = 'ignored'
        record.last_retried_at = timezone.now()
        record.retried_by = getattr(request.user, 'username', '')
        record.retry_result = 'ignored'
        record.retry_error_message = ''
        record.save(update_fields=[
            'status', 'retry_status', 'last_retried_at', 'retried_by',
            'retry_result', 'retry_error_message',
        ])
        _record_ci_change(
            record.ci,
            'sync_ignore',
            before,
            {'sync_record_id': record.id, 'status': record.status, 'note': note},
            operator=getattr(request.user, 'username', ''),
            source='governance',
        )
        return Response(CISyncRecordSerializer(record).data)

    @action(detail=True, methods=['get'], url_path='relation-candidates')
    def relation_candidates(self, request, pk=None):
        record = self.get_object()
        return Response({
            'record': CISyncRecordSerializer(record).data,
            'issues': _sync_record_relation_candidate_issues(record, user=request.user),
        })

    @action(detail=True, methods=['post'], url_path='resolve-relation')
    def resolve_relation(self, request, pk=None):
        record = self.get_object()
        if not record.ci_id:
            return Response({'detail': '同步记录未关联配置项，无法创建资源关系。'}, status=status.HTTP_400_BAD_REQUEST)
        error_index = request.data.get('error_index') or request.data.get('index')
        candidate_id = request.data.get('candidate') or request.data.get('candidate_id') or request.data.get('peer_ci')
        if error_index in (None, ''):
            return Response({'error_index': ['请选择要处理的关系失败项。']}, status=status.HTTP_400_BAD_REQUEST)
        if not candidate_id:
            return Response({'candidate_id': ['请选择要关联的候选资源。']}, status=status.HTTP_400_BAD_REQUEST)
        issues = _sync_record_relation_candidate_issues(record, user=request.user, limit=20)
        issue = next((item for item in issues if str(item.get('index')) == str(error_index)), None)
        if not issue:
            return Response({'detail': '未找到可处理的关系失败项，可能已被处理或缺少候选规则。'}, status=status.HTTP_404_NOT_FOUND)
        candidate = next((item for item in issue.get('candidates') or [] if str(item.get('id')) == str(candidate_id)), None)
        if not candidate:
            return Response({'candidate_id': ['候选资源不存在或不在当前授权范围内。']}, status=status.HTTP_400_BAD_REQUEST)
        relation, summary = _sync_record_create_relation_from_candidate(record, issue, candidate, request)
        return Response({
            'relation': CIRelationSerializer(relation).data,
            'record': CISyncRecordSerializer(record).data,
            'summary': summary,
        })

    @action(detail=False, methods=['post'], url_path='bulk-resolve-relations')
    def bulk_resolve_relations(self, request):
        raw_ids = request.data.get('record_ids') or request.data.get('ids') or []
        if raw_ids and not isinstance(raw_ids, list):
            return Response({'record_ids': ['请提供同步记录 ID 列表。']}, status=status.HTTP_400_BAD_REQUEST)
        try:
            limit = int(request.data.get('limit') or 100)
        except (TypeError, ValueError):
            limit = 100
        limit = min(max(limit, 1), 200)
        qs = self.get_queryset().filter(after___sync_relations__failed__gt=0).order_by('-created_at', '-id')
        if raw_ids:
            qs = qs.filter(id__in=raw_ids)
        records = list(qs[:limit])
        summary = {
            'total': len(records),
            'resolved': 0,
            'skipped': 0,
            'failed': 0,
        }
        errors = []
        resolved_records = []
        for record in records:
            issues = _sync_record_relation_candidate_issues(record, user=request.user, limit=1)
            if not issues:
                summary['skipped'] += 1
                continue
            record_resolved = 0
            for issue in issues:
                candidate = issue.get('best_candidate')
                if not candidate:
                    summary['skipped'] += 1
                    continue
                try:
                    _sync_record_create_relation_from_candidate(record, issue, candidate, request)
                    summary['resolved'] += 1
                    record_resolved += 1
                except Exception as exc:
                    summary['failed'] += 1
                    errors.append({
                        'record_id': record.id,
                        'error_index': issue.get('index'),
                        'detail': str(exc),
                    })
            if record_resolved:
                record.refresh_from_db()
                resolved_records.append(record)
        payload = {
            'summary': summary,
            'records': CISyncRecordSerializer(resolved_records, many=True).data,
        }
        if errors:
            payload['errors'] = errors[:20]
        return Response(payload)

    @action(detail=True, methods=['post'], url_path='resolve-to-ci')
    def resolve_to_ci(self, request, pk=None):
        record = self.get_object()
        if record.status != 'failed' or record.action not in {'conflict', 'fail'}:
            return Response({'detail': '只能处理失败或冲突的同步记录'}, status=status.HTTP_400_BAD_REQUEST)
        payload = record.after if isinstance(record.after, dict) else {}
        if not payload:
            return Response({'detail': '同步记录缺少可绑定的来源数据'}, status=status.HTTP_400_BAD_REQUEST)

        ci_id = request.data.get('ci') or request.data.get('ci_id') or request.data.get('target_ci')
        if not ci_id:
            return Response({'detail': '请提供要绑定的目标配置项'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            target_ci = ConfigItem.objects.select_related('ci_type').get(pk=ci_id)
        except ConfigItem.DoesNotExist:
            return Response({'detail': '目标配置项不存在'}, status=status.HTTP_404_NOT_FOUND)
        _ensure_user_can_manage_config_item(request.user, target_ci)

        source = _source_values(payload, default_source_type=record.job.source_type if record.job_id else 'manual')
        if not source['source_unique_id']:
            return Response({'detail': '同步记录缺少来源唯一标识'}, status=status.HTTP_400_BAD_REQUEST)
        replace_existing = bool(request.data.get('replace_existing'))
        rebind = bool(request.data.get('rebind'))
        note = (request.data.get('note') or request.data.get('resolution_note') or '').strip()
        operator = getattr(request.user, 'username', '')

        with transaction.atomic():
            exact_mapping = CISourceMapping.objects.select_related('ci', 'ci__ci_type').filter(**source).first()
            if exact_mapping and exact_mapping.ci_id != target_ci.id and not rebind:
                return Response(
                    {
                        'detail': (
                            f"来源 {source['source_unique_id']} 已绑定到 {exact_mapping.ci.name if exact_mapping.ci else exact_mapping.ci_id}，"
                            "如需改绑请显式传入 rebind=true。"
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            scope_conflicts = _source_mapping_scope_conflicts(target_ci, source)
            if scope_conflicts and not replace_existing:
                return Response(
                    {
                        'detail': (
                            f"目标资源 {target_ci.name} 已绑定同来源范围的其他唯一标识，"
                            "如需替换请显式传入 replace_existing=true。"
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            for mapping in scope_conflicts:
                before = _source_mapping_snapshot(mapping)
                mapping.delete()
                _record_ci_change(
                    target_ci,
                    'source_mapping_delete',
                    before,
                    {},
                    operator=operator,
                    source='source_mapping',
                )

            if exact_mapping:
                before = _source_mapping_snapshot(exact_mapping)
                exact_mapping.ci = target_ci
                exact_mapping.sync_status = 'success'
                exact_mapping.last_seen_at = timezone.now()
                exact_mapping.raw_payload = {
                    **payload,
                    'manual_resolution_note': note,
                    'resolved_from_sync_record': record.id,
                }
                exact_mapping.save(update_fields=['ci', 'sync_status', 'last_seen_at', 'raw_payload', 'updated_at'])
                after = _source_mapping_snapshot(exact_mapping)
                if _dict_diff(before, after):
                    _record_ci_change(
                        target_ci,
                        'source_mapping_update',
                        before,
                        after,
                        operator=operator,
                        source='source_mapping',
                    )
                mapping = exact_mapping
            else:
                mapping = CISourceMapping.objects.create(
                    ci=target_ci,
                    **source,
                    sync_status='success',
                    last_seen_at=timezone.now(),
                    raw_payload={
                        **payload,
                        'manual_resolution_note': note,
                        'resolved_from_sync_record': record.id,
                    },
                )
                _record_ci_change(
                    target_ci,
                    'source_mapping_create',
                    {},
                    _source_mapping_snapshot(mapping),
                    operator=operator,
                    source='source_mapping',
                )

            record.status = 'resolved'
            record.retry_status = 'success'
            record.retry_count = (record.retry_count or 0) + 1
            record.last_retried_at = timezone.now()
            record.retried_by = operator
            record.retry_result = 'resolve_to_ci'
            record.retry_error_message = ''
            record.error_message = note or record.error_message
            record.ci = target_ci
            record.save(update_fields=[
                'status',
                'retry_status',
                'retry_count',
                'last_retried_at',
                'retried_by',
                'retry_result',
                'retry_error_message',
                'error_message',
                'ci',
            ])

        return Response({
            'record': CISyncRecordSerializer(record).data,
            'source_mapping': CISourceMappingSerializer(mapping).data,
        })


class CICompletionIssueViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = CICompletionIssue.objects.select_related('ci', 'ci__ci_type').all()
    serializer_class = CICompletionIssueSerializer
    search_fields = ['ci__name', 'assigned_to', 'resolution_note']
    filterset_fields = ['status', 'severity', 'assigned_to', 'ci']
    rbac_permissions = {
        'list': ['cmdb.ci.view'],
        'retrieve': ['cmdb.ci.view'],
        'create': ['cmdb.ci.manage'],
        'update': ['cmdb.ci.manage'],
        'partial_update': ['cmdb.ci.manage'],
        'destroy': ['cmdb.ci.manage'],
        'resolve': ['cmdb.ci.manage'],
        'bulk_resolve': ['cmdb.ci.manage'],
        'assign': ['cmdb.ci.manage'],
        'ignore': ['cmdb.ci.manage'],
    }

    def get_queryset(self):
        permission = 'manage' if getattr(self, 'action', '') in {'update', 'partial_update', 'destroy', 'resolve', 'bulk_resolve', 'assign', 'ignore'} else 'view'
        scoped_ci_ids = _apply_ci_authorization_scope(ConfigItem.objects.all(), self.request.user, permission=permission).values('id')
        return super().get_queryset().filter(ci_id__in=scoped_ci_ids)

    def _apply_completion_updates(self, ci, updates):
        if updates and not isinstance(updates, dict):
            raise ValidationError({'detail': 'ci_updates 必须是对象'})
        before = _config_item_snapshot(ci)
        update_fields = []
        for field in ['name', 'business_line', 'environment', 'admin_user', 'status']:
            if field in updates:
                value = updates.get(field)
                if isinstance(value, str):
                    value = value.strip()
                if field == 'name' and not value:
                    raise ValidationError({'name': ['配置项名称不能为空']})
                setattr(ci, field, value)
                update_fields.append(field)
        if 'department' in updates:
            attributes = dict(ci.attributes or {})
            department = updates.get('department')
            if isinstance(department, str):
                department = department.strip()
            if department:
                attributes['department'] = str(department)[:80]
            else:
                attributes.pop('department', None)
            ci.attributes = normalize_ci_attributes(attributes)
            update_fields.append('attributes')
        if isinstance(updates.get('attributes'), dict):
            attributes = dict(ci.attributes or {})
            attributes.update(normalize_ci_attributes(updates['attributes']))
            ci.attributes = attributes
            update_fields.append('attributes')
        if update_fields:
            ci.save(update_fields=[*set(update_fields), 'updated_at'])
        return before, _config_item_snapshot(ci)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        issue = self.get_object()
        requested_status = request.data.get('status') or 'resolved'
        note = (request.data.get('note') or request.data.get('resolution_note') or '').strip()
        updates = request.data.get('ci_updates') or {}

        if updates:
            ci = issue.ci
            before, after = self._apply_completion_updates(ci, updates)
            if _dict_diff(before, after):
                _record_ci_change(
                    ci,
                    'completion_resolve',
                    before,
                    after,
                    operator=getattr(request.user, 'username', ''),
                    source='governance',
                )
            _sync_completion_issue(ci)
            issue.refresh_from_db()

        missing_fields = _missing_fields_for_ci(issue.ci)
        if requested_status == 'resolved' and missing_fields:
            issue.missing_fields = missing_fields
            issue.status = 'open'
            if note:
                issue.resolution_note = note
            issue.save(update_fields=['missing_fields', 'status', 'resolution_note', 'updated_at'])
            return Response({
                'detail': '仍有关键字段未补全，不能标记为已解决',
                'missing_fields': missing_fields,
                'issue': CICompletionIssueSerializer(issue).data,
            }, status=400)

        issue.status = requested_status
        issue.resolution_note = note
        issue.resolved_at = timezone.now() if issue.status == 'resolved' else issue.resolved_at
        issue.save(update_fields=['status', 'resolution_note', 'resolved_at', 'updated_at'])
        return Response(CICompletionIssueSerializer(issue).data)

    @action(detail=False, methods=['post'], url_path='bulk-resolve')
    def bulk_resolve(self, request):
        issue_ids = request.data.get('issue_ids') or request.data.get('ids') or []
        if not isinstance(issue_ids, list) or not issue_ids:
            return Response({'issue_ids': ['请选择需要批量补全的治理项']}, status=400)
        issue_ids = [item for item in issue_ids[:200] if item]
        note = (request.data.get('note') or request.data.get('resolution_note') or '批量补全关键字段').strip()
        updates = request.data.get('ci_updates') or {}
        if updates and not isinstance(updates, dict):
            return Response({'detail': 'ci_updates 必须是对象'}, status=400)

        summary = {'total': 0, 'resolved': 0, 'remaining': 0}
        records = []
        issues = list(self.get_queryset().filter(id__in=issue_ids).select_related('ci', 'ci__ci_type').order_by('id'))
        for issue in issues:
            summary['total'] += 1
            ci = issue.ci
            before, after = self._apply_completion_updates(ci, updates) if updates else (_config_item_snapshot(ci), _config_item_snapshot(ci))
            if _dict_diff(before, after):
                _record_ci_change(
                    ci,
                    'completion_resolve',
                    before,
                    after,
                    operator=getattr(request.user, 'username', ''),
                    source='governance',
                )
            _sync_completion_issue(ci)
            issue.refresh_from_db()
            missing_fields = _missing_fields_for_ci(ci)
            if missing_fields:
                issue.missing_fields = missing_fields
                issue.status = 'open'
                if note:
                    issue.resolution_note = note
                issue.save(update_fields=['missing_fields', 'status', 'resolution_note', 'updated_at'])
                summary['remaining'] += 1
            else:
                issue.status = 'resolved'
                issue.resolution_note = note
                issue.resolved_at = timezone.now()
                issue.save(update_fields=['status', 'resolution_note', 'resolved_at', 'updated_at'])
                summary['resolved'] += 1
            records.append(CICompletionIssueSerializer(issue).data)
        return Response({'summary': summary, 'records': records})

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        issue = self.get_object()
        assigned_to = (request.data.get('assigned_to') or '').strip()[:80]
        note = (request.data.get('note') or request.data.get('resolution_note') or '').strip()[:200]
        if not assigned_to:
            return Response({'assigned_to': ['处理人不能为空']}, status=400)

        before = _config_item_snapshot(issue.ci)
        issue.assigned_to = assigned_to
        issue.status = 'assigned'
        if note:
            issue.resolution_note = note
        issue.save(update_fields=['assigned_to', 'status', 'resolution_note', 'updated_at'])
        _record_ci_change(
            issue.ci,
            'completion_assign',
            before,
            _config_item_snapshot(issue.ci),
            operator=getattr(request.user, 'username', ''),
            source='governance',
        )
        return Response(CICompletionIssueSerializer(issue).data)

    @action(detail=True, methods=['post'])
    def ignore(self, request, pk=None):
        issue = self.get_object()
        note = (request.data.get('note') or request.data.get('resolution_note') or '').strip()
        before = _config_item_snapshot(issue.ci)
        issue.status = 'ignored'
        issue.resolution_note = note or issue.resolution_note or '已确认忽略该待补全项'
        issue.resolved_at = timezone.now()
        issue.save(update_fields=['status', 'resolution_note', 'resolved_at', 'updated_at'])
        _record_ci_change(
            issue.ci,
            'completion_ignore',
            before,
            _config_item_snapshot(issue.ci),
            operator=getattr(request.user, 'username', ''),
            source='governance',
        )
        return Response(CICompletionIssueSerializer(issue).data)


class CIArchiveCandidateViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = CIArchiveCandidate.objects.select_related('ci', 'ci__ci_type').all()
    serializer_class = CIArchiveCandidateSerializer
    search_fields = ['ci__name', 'source_type', 'reason', 'confirmed_by']
    filterset_fields = ['status', 'source_type', 'ci']
    rbac_permissions = {
        'list': ['cmdb.ci.view'],
        'retrieve': ['cmdb.ci.view'],
        'create': ['cmdb.ci.manage'],
        'update': ['cmdb.ci.manage'],
        'partial_update': ['cmdb.ci.manage'],
        'destroy': ['cmdb.ci.manage'],
        'confirm': ['cmdb.ci.manage'],
        'archive': ['cmdb.ci.manage'],
        'restore': ['cmdb.ci.manage'],
        'ignore': ['cmdb.ci.manage'],
        'bulk_action': ['cmdb.ci.manage'],
    }

    def get_queryset(self):
        permission = 'manage' if getattr(self, 'action', '') in {'update', 'partial_update', 'destroy', 'confirm', 'archive', 'restore', 'ignore', 'bulk_action'} else 'view'
        scoped_ci_ids = _apply_ci_authorization_scope(ConfigItem.objects.all(), self.request.user, permission=permission).values('id')
        return super().get_queryset().filter(ci_id__in=scoped_ci_ids)

    def _apply_bulk_candidate_action(self, candidate, action_name, *, user, note='', restore_status='active'):
        before = _config_item_snapshot(candidate.ci)
        operator = getattr(user, 'username', '')
        candidate.confirmed_by = operator
        candidate.confirmed_at = timezone.now()
        update_fields = ['status', 'confirmed_by', 'confirmed_at', 'updated_at']

        if action_name == 'confirm':
            candidate.status = 'confirmed'
            candidate.ci.status = 'offline'
            candidate.ci.save(update_fields=['status', 'updated_at'])
            change_action = 'archive_confirm'
        elif action_name == 'archive':
            candidate.status = 'archived'
            if note:
                candidate.reason = f"{candidate.reason}；归档说明：{note}" if candidate.reason else f"归档说明：{note}"
                update_fields.append('reason')
            candidate.ci.status = 'offline'
            candidate.ci.save(update_fields=['status', 'updated_at'])
            change_action = 'archive_archive'
        elif action_name == 'restore':
            candidate.status = 'restored'
            candidate.ci.status = restore_status or 'active'
            candidate.ci.save(update_fields=['status', 'updated_at'])
            change_action = 'archive_restore'
        elif action_name == 'ignore':
            candidate.status = 'ignored'
            if note:
                candidate.reason = f"{candidate.reason}；忽略说明：{note}" if candidate.reason else f"忽略说明：{note}"
                update_fields.append('reason')
            change_action = 'archive_ignore'
        else:
            raise ValidationError({'action': '不支持的待下线治理动作'})

        candidate.save(update_fields=update_fields)
        _record_ci_change(
            candidate.ci,
            change_action,
            before,
            _config_item_snapshot(candidate.ci),
            operator=operator,
            source='governance',
        )
        return candidate

    @action(detail=False, methods=['post'], url_path='bulk-action')
    def bulk_action(self, request):
        candidate_ids = request.data.get('candidate_ids') or request.data.get('ids') or []
        if not isinstance(candidate_ids, list) or not candidate_ids:
            return Response({'candidate_ids': ['请选择待处理的下线候选。']}, status=status.HTTP_400_BAD_REQUEST)
        action_name = (request.data.get('action') or '').strip()
        if action_name not in {'confirm', 'archive', 'restore', 'ignore'}:
            return Response({'action': ['动作只能是 confirm、archive、restore 或 ignore。']}, status=status.HTTP_400_BAD_REQUEST)

        normalized_ids = list(dict.fromkeys(candidate_ids))
        candidates = list(self.get_queryset().filter(id__in=normalized_ids).order_by('id'))
        if len(candidates) != len(normalized_ids):
            return Response({'candidate_ids': ['存在无权限或不存在的下线候选。']}, status=status.HTTP_404_NOT_FOUND)

        note = (request.data.get('note') or request.data.get('reason') or '').strip()
        restore_status = request.data.get('status') or 'active'
        updated = [
            self._apply_bulk_candidate_action(
                candidate,
                action_name,
                user=request.user,
                note=note,
                restore_status=restore_status,
            )
            for candidate in candidates
        ]
        return Response({
            'action': action_name,
            'updated_count': len(updated),
            'candidates': CIArchiveCandidateSerializer(updated, many=True).data,
        })

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        candidate = self.get_object()
        before = _config_item_snapshot(candidate.ci)
        candidate.status = 'confirmed'
        candidate.confirmed_by = getattr(request.user, 'username', '')
        candidate.confirmed_at = timezone.now()
        candidate.ci.status = 'offline'
        candidate.ci.save(update_fields=['status', 'updated_at'])
        candidate.save(update_fields=['status', 'confirmed_by', 'confirmed_at', 'updated_at'])
        _record_ci_change(candidate.ci, 'archive_confirm', before, _config_item_snapshot(candidate.ci), operator=candidate.confirmed_by, source='governance')
        return Response(CIArchiveCandidateSerializer(candidate).data)

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        candidate = self.get_object()
        before = _config_item_snapshot(candidate.ci)
        candidate.status = 'archived'
        candidate.confirmed_by = getattr(request.user, 'username', '')
        candidate.confirmed_at = timezone.now()
        note = (request.data.get('note') or request.data.get('reason') or '').strip()
        if note:
            candidate.reason = f"{candidate.reason}；归档说明：{note}" if candidate.reason else f"归档说明：{note}"
        candidate.ci.status = 'offline'
        candidate.ci.save(update_fields=['status', 'updated_at'])
        candidate.save(update_fields=['status', 'confirmed_by', 'confirmed_at', 'reason', 'updated_at'])
        _record_ci_change(candidate.ci, 'archive_archive', before, _config_item_snapshot(candidate.ci), operator=candidate.confirmed_by, source='governance')
        return Response(CIArchiveCandidateSerializer(candidate).data)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        candidate = self.get_object()
        before = _config_item_snapshot(candidate.ci)
        candidate.status = 'restored'
        candidate.confirmed_by = getattr(request.user, 'username', '')
        candidate.confirmed_at = timezone.now()
        candidate.ci.status = request.data.get('status') or 'active'
        candidate.ci.save(update_fields=['status', 'updated_at'])
        candidate.save(update_fields=['status', 'confirmed_by', 'confirmed_at', 'updated_at'])
        _record_ci_change(candidate.ci, 'archive_restore', before, _config_item_snapshot(candidate.ci), operator=candidate.confirmed_by, source='governance')
        return Response(CIArchiveCandidateSerializer(candidate).data)

    @action(detail=True, methods=['post'])
    def ignore(self, request, pk=None):
        candidate = self.get_object()
        before = _config_item_snapshot(candidate.ci)
        candidate.status = 'ignored'
        candidate.confirmed_by = getattr(request.user, 'username', '')
        candidate.confirmed_at = timezone.now()
        note = (request.data.get('note') or request.data.get('reason') or '').strip()
        if note:
            candidate.reason = f"{candidate.reason}；忽略说明：{note}" if candidate.reason else f"忽略说明：{note}"
        candidate.save(update_fields=['status', 'confirmed_by', 'confirmed_at', 'reason', 'updated_at'])
        _record_ci_change(
            candidate.ci,
            'archive_ignore',
            before,
            _config_item_snapshot(candidate.ci),
            operator=candidate.confirmed_by,
            source='governance',
        )
        return Response(CIArchiveCandidateSerializer(candidate).data)


class CIResourceAuthorizationViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = CIResourceAuthorization.objects.select_related('ci_type').all()
    serializer_class = CIResourceAuthorizationSerializer
    search_fields = ['name', 'principal', 'business_line', 'environment', 'description', 'ci_type__name']
    filterset_fields = ['principal_type', 'principal', 'permission', 'business_line', 'environment', 'ci_type', 'is_active']
    rbac_permissions = {
        'list': ['cmdb.authorization.view'],
        'retrieve': ['cmdb.authorization.view'],
        'create': ['cmdb.authorization.manage'],
        'update': ['cmdb.authorization.manage'],
        'partial_update': ['cmdb.authorization.manage'],
        'destroy': ['cmdb.authorization.manage'],
    }

    def perform_create(self, serializer):
        authorization = serializer.save(created_by=getattr(self.request.user, 'username', ''))
        _record_ci_change(
            None,
            'authorization_create',
            {},
            _resource_authorization_snapshot(authorization),
            operator=getattr(self.request.user, 'username', ''),
            source='authorization',
        )

    def perform_update(self, serializer):
        before = _resource_authorization_snapshot(serializer.instance)
        authorization = serializer.save()
        _record_ci_change(
            None,
            'authorization_update',
            before,
            _resource_authorization_snapshot(authorization),
            operator=getattr(self.request.user, 'username', ''),
            source='authorization',
        )

    def perform_destroy(self, instance):
        before = _resource_authorization_snapshot(instance)
        _record_ci_change(
            None,
            'authorization_delete',
            before,
            {},
            operator=getattr(self.request.user, 'username', ''),
            source='authorization',
        )
        instance.delete()


class CostRecordViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    """成本记录管理"""
    queryset = CostRecord.objects.select_related('ci').order_by('-month', '-computed_at', '-id')
    serializer_class = CostRecordSerializer
    filterset_fields = ['ci', 'month']
    rbac_permissions = {
        'list': ['cmdb.cost.view'],
        'retrieve': ['cmdb.cost.view'],
        'create': ['cmdb.ci.manage'],
        'update': ['cmdb.ci.manage'],
        'partial_update': ['cmdb.ci.manage'],
        'destroy': ['cmdb.ci.manage'],
    }

    def get_queryset(self):
        permission = 'manage' if getattr(self, 'action', '') in {'update', 'partial_update', 'destroy'} else 'view'
        scoped_ci_ids = _apply_ci_authorization_scope(ConfigItem.objects.all(), self.request.user, permission=permission).values('id')
        return super().get_queryset().filter(ci_id__in=scoped_ci_ids)

    def perform_create(self, serializer):
        ci = serializer.validated_data.get('ci')
        if ci:
            _ensure_user_can_manage_config_item(self.request.user, ci)
        serializer.save()

    def perform_update(self, serializer):
        ci = serializer.validated_data.get('ci') or serializer.instance.ci
        if ci:
            _ensure_user_can_manage_config_item(self.request.user, ci)
        serializer.save()


class CostOptimizationTaskViewSet(RBACPermissionMixin, viewsets.ReadOnlyModelViewSet):
    queryset = CostOptimizationTask.objects.select_related('ci__ci_type').prefetch_related('progress_entries')
    serializer_class = CostOptimizationTaskSerializer
    filterset_fields = ['month', 'status', 'owner', 'suggestion_type', 'ci']
    rbac_permissions = {
        'list': ['cmdb.cost.view'],
        'retrieve': ['cmdb.cost.view'],
        'claim': ['cmdb.cost.manage'],
        'progress': ['cmdb.cost.manage'],
    }

    def get_queryset(self):
        permission = 'manage' if getattr(self, 'action', '') in {'claim', 'progress'} else 'view'
        scoped_ci_ids = _apply_ci_authorization_scope(
            ConfigItem.objects.all(),
            self.request.user,
            permission=permission,
        ).values('id')
        return super().get_queryset().filter(ci_id__in=scoped_ci_ids)

    @action(detail=False, methods=['post'])
    def claim(self, request):
        month = _normalize_month(request.data.get('month'))
        suggestion_type = str(request.data.get('suggestion_type') or '').strip()
        ci_id = request.data.get('ci_id')
        if not ci_id or not suggestion_type:
            raise ValidationError({'detail': '请提供需要认领的优化建议。'})

        ci_queryset = _apply_ci_authorization_scope(
            ConfigItem.objects.filter(pk=ci_id),
            request.user,
            permission='manage',
        )
        ci = ci_queryset.select_related('ci_type').first()
        if not ci:
            raise PermissionDenied('无权认领该资源的成本优化事项。')
        suggestion = next(
            (
                item for item in _build_optimization(month, ci_queryset=ci_queryset)['suggestions']
                if item['type'] == suggestion_type
            ),
            None,
        )
        if not suggestion:
            raise ValidationError({'detail': '该建议已不再满足当前的优化条件，请刷新后重试。'})

        username = getattr(request.user, 'username', '')
        defaults = {
            'suggestion_title': suggestion['title'],
            'suggestion_snapshot': suggestion,
            'expected_monthly_saving': suggestion['potential_saving'],
            'status': 'claimed',
            'owner': username,
            'claimed_at': timezone.now(),
        }
        with transaction.atomic():
            task, created = CostOptimizationTask.objects.select_for_update().get_or_create(
                ci=ci,
                month=month,
                suggestion_type=suggestion_type,
                defaults=defaults,
            )
            if not created and task.owner != username:
                return Response(
                    {'detail': f'该建议已由 {task.owner or "其他成员"} 认领。'},
                    status=status.HTTP_409_CONFLICT,
                )
            if created:
                CostOptimizationProgress.objects.create(
                    task=task,
                    status='claimed',
                    progress_percent=0,
                    note=(request.data.get('note') or '').strip(),
                    created_by=username,
                )

        record_event(
            request=request,
            module='cmdb',
            category='governance',
            action='cost_optimization_claim',
            title='认领成本优化事项',
            summary=f'{username} 认领了 {ci.name} 的优化建议：{suggestion["title"]}',
            resource_type='cmdb_cost_optimization',
            resource_id=str(task.id),
            resource_name=ci.name,
            metadata={'task_id': task.id, 'ci_id': ci.id, 'month': month, 'suggestion_type': suggestion_type},
        )
        task = self.get_queryset().get(pk=task.pk)
        return Response(self.get_serializer(task).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def progress(self, request, pk=None):
        task = self.get_object()
        status_value = str(request.data.get('status') or task.status).strip()
        valid_statuses = {choice[0] for choice in CostOptimizationTask.STATUS_CHOICES}
        if status_value not in valid_statuses:
            raise ValidationError({'status': '不支持的处理状态。'})
        try:
            progress_percent = int(request.data.get('progress_percent', 0))
        except (TypeError, ValueError):
            raise ValidationError({'progress_percent': '完成度必须是 0 到 100 的整数。'})
        if not 0 <= progress_percent <= 100:
            raise ValidationError({'progress_percent': '完成度必须在 0 到 100 之间。'})

        actual_saving = request.data.get('actual_monthly_saving')
        if actual_saving in (None, ''):
            actual_saving = None
        else:
            try:
                actual_saving = Decimal(str(actual_saving)).quantize(Decimal('0.01'))
            except (InvalidOperation, ValueError):
                raise ValidationError({'actual_monthly_saving': '实际月节省必须是有效金额。'})
            if actual_saving < 0:
                raise ValidationError({'actual_monthly_saving': '实际月节省不能小于 0。'})

        username = getattr(request.user, 'username', '')
        task.status = status_value
        if actual_saving is not None:
            task.actual_monthly_saving = actual_saving
        if status_value in {'completed', 'deferred', 'rejected'}:
            task.resolved_by = username
            task.resolved_at = timezone.now()
        else:
            task.resolved_by = ''
            task.resolved_at = None
        task.save(update_fields=['status', 'actual_monthly_saving', 'resolved_by', 'resolved_at', 'updated_at'])
        CostOptimizationProgress.objects.create(
            task=task,
            status=status_value,
            progress_percent=progress_percent,
            note=(request.data.get('note') or '').strip(),
            actual_monthly_saving=actual_saving,
            created_by=username,
        )
        record_event(
            request=request,
            module='cmdb',
            category='governance',
            action='cost_optimization_progress',
            title='更新成本优化进展',
            summary=f'{username} 将 {task.ci.name} 的成本优化事项更新为 {task.get_status_display()}。',
            resource_type='cmdb_cost_optimization',
            resource_id=str(task.id),
            resource_name=task.ci.name,
            metadata={'task_id': task.id, 'status': status_value, 'progress_percent': progress_percent},
        )
        task = self.get_queryset().get(pk=task.pk)
        return Response(self.get_serializer(task).data)

class ResourceRequestViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    """资源申请管理"""
    queryset = ResourceRequest.objects.all().order_by('-created_at', '-id')
    serializer_class = ResourceRequestSerializer
    search_fields = ['title', 'applicant', 'resource_type', 'business_line', 'specification', 'reason']
    filterset_fields = ['status', 'resource_type', 'business_line', 'environment', 'priority']
    rbac_permissions = {
        'list': [],
        'retrieve': [],
        'create': ['cmdb.request.submit'],
        'update': ['cmdb.request.approve'],
        'partial_update': ['cmdb.request.approve'],
        'destroy': ['cmdb.request.approve'],
        'approve': ['cmdb.request.approve'],
        'reject': ['cmdb.request.approve'],
        'complete': ['cmdb.request.approve'],
        'provision': ['cmdb.request.execute'],
        'provisioning_options': [],
    }

    def _can_view_requests(self, user):
        return (
            user_has_permissions(user, ['cmdb.ci.view'])
            or user_has_permissions(user, ['cmdb.request.submit'])
            or user_has_permissions(user, ['cmdb.request.approve'])
            or user_has_permissions(user, ['cmdb.request.execute'])
        )

    def get_queryset(self):
        qs = super().get_queryset()
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return qs.none()
        if (
            user_has_permissions(user, ['cmdb.ci.view'])
            or user_has_permissions(user, ['cmdb.request.approve'])
            or user_has_permissions(user, ['cmdb.request.execute'])
        ):
            return qs
        if user_has_permissions(user, ['cmdb.request.submit']):
            return qs.filter(applicant=user.username)
        return qs.none()

    def list(self, request, *args, **kwargs):
        if not self._can_view_requests(request.user):
            return Response({'detail': '缺少资源申请查看权限'}, status=403)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        if not self._can_view_requests(request.user):
            return Response({'detail': '缺少资源申请查看权限'}, status=403)
        return super().retrieve(request, *args, **kwargs)

    def perform_create(self, serializer):
        obj = serializer.save(applicant=self.request.user.username)
        _record_request_change(
            obj,
            'request_submit',
            {},
            _resource_request_snapshot(obj),
            operator=getattr(self.request.user, 'username', ''),
        )

    @action(detail=False, methods=['get'], url_path='provisioning-options')
    def provisioning_options(self, request):
        if not self._can_view_requests(request.user):
            return Response({'detail': '缺少资源申请查看权限'}, status=403)
        return Response(build_provisioning_options())

    def _build_host_sync_payloads(self, obj, fulfillment_note=''):
        specs = obj.specs or {}
        cloud_delivery = specs.get('provisioning_mode') == 'cloud'
        raw_hosts = specs.get('hosts') or specs.get('items') or specs.get('resources')
        if raw_hosts:
            if not isinstance(raw_hosts, list):
                raise ValueError('多主机交付清单必须是数组')
            if obj.quantity and len(raw_hosts) != obj.quantity:
                raise ValueError('申请数量与主机交付清单数量不一致')
            host_specs = raw_hosts
        elif obj.quantity and obj.quantity > 1:
            raise ValueError('数量大于 1 时，请在规格要求中填写 hosts 主机清单')
        else:
            host_specs = [specs]

        description_parts = [obj.title, obj.reason, fulfillment_note]
        description = '；'.join([part.strip() for part in description_parts if part and part.strip()])[:200]
        payloads = []
        seen_hostnames = set()
        seen_ips = set()
        for index, host_spec in enumerate(host_specs, start=1):
            if not isinstance(host_spec, dict):
                raise ValueError('主机交付清单中的每一项必须是对象')
            hostname = (host_spec.get('hostname') or host_spec.get('name') or '').strip()
            ip_address = (
                host_spec.get('ip_address')
                or host_spec.get('private_ip')
                or host_spec.get('ip')
                or ''
            ).strip()
            if not hostname:
                raise ValueError('完成交付前请为每台主机填写主机名')
            if not ip_address and not cloud_delivery:
                raise ValueError('人工交付前请为每台主机填写 IP 地址')
            if ip_address:
                try:
                    ipaddress.ip_address(ip_address)
                except ValueError:
                    raise ValueError(f'主机 {hostname} 的 IP 地址不合法：{ip_address}')
            if hostname in seen_hostnames:
                raise ValueError(f'主机交付清单存在重复主机名：{hostname}')
            if ip_address and ip_address in seen_ips:
                raise ValueError(f'主机交付清单存在重复 IP 地址：{ip_address}')
            seen_hostnames.add(hostname)
            if ip_address:
                seen_ips.add(ip_address)
            payloads.append({
                'index': index,
                'hostname': hostname,
                'ip_address': ip_address,
                'business_line': (obj.business_line or '').strip(),
                'environment': (obj.environment or '').strip(),
                'admin_user': (host_spec.get('admin_user') or specs.get('admin_user') or obj.applicant or '').strip(),
                'os_type': (host_spec.get('os_type') or specs.get('os_type') or 'Linux').strip() or 'Linux',
                'instance_type': (host_spec.get('instance_type') or specs.get('instance_type') or '').strip(),
                'specification': (
                    host_spec.get('specification')
                    or obj.specification
                    or specs.get('specification')
                    or ''
                ).strip(),
                'description': description,
                'raw_spec': host_spec,
                'provider': host_spec.get('provider') or specs.get('provider') or '',
                'instance_id': host_spec.get('instance_id') or '',
                'public_ip': host_spec.get('public_ip') or '',
                'region': host_spec.get('region') or specs.get('region') or '',
                'zone': host_spec.get('zone') or specs.get('zone') or '',
                'instance_status': host_spec.get('status') or '',
            })
        return payloads

    def _request_delivery_source_unique_id(self, obj, payload, payload_count):
        return str(obj.id) if payload_count == 1 else f"{obj.id}:{payload['index']}"

    def _validate_host_delivery_conflicts(self, obj, payloads):
        source_unique_ids = [
            self._request_delivery_source_unique_id(obj, payload, len(payloads))
            for payload in payloads
        ]
        existing_source_mapping = (
            CISourceMapping.objects
            .select_related('ci')
            .filter(source_type='resource_request', source_unique_id__in=source_unique_ids)
            .first()
        )
        if existing_source_mapping:
            raise ValueError(
                f'资源申请交付映射 {existing_source_mapping.source_unique_id} 已存在，'
                '请刷新申请状态或检查是否已交付。'
            )
        for payload in payloads:
            hostname = payload['hostname']
            ip_address = payload['ip_address']
            same_host = Host.objects.filter(hostname=hostname).first()
            if same_host and same_host.ip_address and same_host.ip_address != ip_address:
                raise ValueError(f'主机 {hostname} 已存在且 IP 为 {same_host.ip_address}，不能改写为 {ip_address}')
            if ip_address:
                host_conflict = Host.objects.filter(ip_address=ip_address).exclude(hostname=hostname).first()
                if host_conflict:
                    raise ValueError(f'IP 地址 {ip_address} 已被主机 {host_conflict.hostname} 使用')
            same_name_ci = ConfigItem.objects.filter(name=hostname).first()
            if same_name_ci:
                ci_attributes = same_name_ci.attributes or {}
                existing_ip = ci_attributes.get('ip_address') or ci_attributes.get('private_ip') or ci_attributes.get('ip')
                if existing_ip and existing_ip != ip_address:
                    raise ValueError(f'配置项 {hostname} 已存在且 IP 为 {existing_ip}，不能改写为 {ip_address}')
                other_request_mapping = (
                    CISourceMapping.objects
                    .filter(source_type='resource_request', ci=same_name_ci)
                    .exclude(source_unique_id__in=source_unique_ids)
                    .first()
                )
                if other_request_mapping:
                    raise ValueError(
                        f'配置项 {hostname} 已由资源申请 {other_request_mapping.source_unique_id} 交付，'
                        '不能重复绑定到当前申请。'
                    )
            if ip_address:
                ci_conflict = (
                    ConfigItem.objects
                    .filter(Q(attributes__ip_address=ip_address) | Q(attributes__private_ip=ip_address))
                    .exclude(name=hostname)
                    .first()
                )
                if ci_conflict:
                    raise ValueError(f'IP 地址 {ip_address} 已被配置项 {ci_conflict.name} 使用')

    def _sync_request_to_host_assets(self, obj, fulfillment_note='', operator=''):
        payloads = self._build_host_sync_payloads(obj, fulfillment_note=fulfillment_note)
        self._validate_host_delivery_conflicts(obj, payloads)
        provider = (obj.specs or {}).get('provider') or ''
        ci_type_code = 'VIRTUAL_MACHINE' if provider == 'vsphere' else 'CLOUD_SERVER'
        ci_type_name = '虚拟机' if provider == 'vsphere' else '云主机(ECS)'
        ci_type = CIType.objects.filter(Q(code=ci_type_code) | Q(name=ci_type_name)).first()
        if not ci_type:
            ci_type = CIType.objects.create(
                code=ci_type_code,
                name=ci_type_name,
                icon='Monitor',
                color='#64748b',
                description='承载应用与数据服务的云主机',
            )
        delivered = []
        for payload in payloads:
            host = None
            if payload['ip_address']:
                host, _ = Host.objects.update_or_create(
                    hostname=payload['hostname'],
                    defaults={
                        'ip_address': payload['ip_address'],
                        'business_line': payload['business_line'],
                        'environment': payload['environment'],
                        'admin_user': payload['admin_user'],
                        'os_type': payload['os_type'],
                        'description': payload['description'],
                        'status': 'online',
                    },
                )
            config_item = ConfigItem.objects.filter(name=payload['hostname']).first()
            before = _config_item_snapshot(config_item) if config_item else {}
            attributes = dict((config_item.attributes or {}) if config_item else {})
            attributes.update({
                'ip_address': payload['ip_address'],
                'os_type': payload['os_type'],
                'instance_type': payload['instance_type'],
                'specification': payload['specification'],
                'description': payload['description'],
                'source': 'host_request',
                'request_id': obj.id,
                'request_title': obj.title,
                'request_item_index': payload['index'],
                'cloud_provider': provider_label(payload['provider']) if payload['provider'] else '',
                'provider': payload['provider'],
                'instance_id': payload['instance_id'],
                'private_ip': payload['ip_address'],
                'public_ip': payload['public_ip'],
                'region': payload['region'],
                'zone': payload['zone'],
                'instance_status': payload['instance_status'],
            })
            attributes = {
                key: value for key, value in attributes.items()
                if value not in (None, '')
            }
            is_create = config_item is None
            if is_create:
                config_item = ConfigItem.objects.create(
                    name=payload['hostname'],
                    ci_type=ci_type,
                    business_line=payload['business_line'],
                    environment=payload['environment'] or '',
                    admin_user=payload['admin_user'],
                    status='active',
                    attributes=attributes,
                )
            else:
                config_item.ci_type = ci_type
                config_item.business_line = payload['business_line']
                config_item.environment = payload['environment'] or config_item.environment or ''
                config_item.admin_user = payload['admin_user']
                config_item.status = 'active'
                config_item.attributes = attributes
                config_item.save()

            source_unique_id = self._request_delivery_source_unique_id(obj, payload, len(payloads))
            CISourceMapping.objects.update_or_create(
                source_type='resource_request',
                source_account=str((obj.specs or {}).get('cloud_credential_id') or obj.applicant or ''),
                source_region=payload['region'] or obj.environment or '',
                source_unique_id=source_unique_id,
                defaults={
                    'ci': config_item,
                    'sync_status': 'success',
                    'last_seen_at': timezone.now(),
                    'raw_payload': {
                        'request_id': obj.id,
                        'request_item_index': payload['index'],
                        'title': obj.title,
                        'resource_type': obj.resource_type,
                        'quantity': obj.quantity,
                        'specs': obj.specs or {},
                        'host_spec': payload['raw_spec'],
                        'fulfillment_note': fulfillment_note,
                    },
                },
            )
            _record_ci_change(
                config_item,
                'create' if is_create else 'update',
                before,
                _config_item_snapshot(config_item),
                operator=operator,
                source='resource_request',
            )
            delivered.append((host, config_item))
        return delivered

    def _sync_request_to_cloud_asset(self, obj, fulfillment_note='', operator=''):
        resource_type = str(obj.resource_type or '').strip().lower()
        if resource_type in {'主机', 'host', 'ecs'}:
            return self._sync_request_to_host_assets(obj, fulfillment_note=fulfillment_note, operator=operator)
        meta = ALIYUN_RESOURCE_TYPE_MAP.get(resource_type)
        if not meta:
            raise ValueError('当前资产类型暂不支持交付入库')
        specs = obj.specs or {}
        raw_items = specs.get('items') or specs.get('resources') or []
        if raw_items and not isinstance(raw_items, list):
            raise ValueError('资产交付清单必须是数组')
        if not raw_items:
            raw_items = [dict(specs) for _ in range(max(obj.quantity or 1, 1))]
        if obj.quantity and len(raw_items) != obj.quantity:
            raise ValueError('申请数量与资产交付清单数量不一致')
        ci_type = CIType.objects.filter(code=meta['ci_type_code']).first()
        if not ci_type:
            ci_type = CIType.objects.filter(name=meta['label']).first()
        if not ci_type:
            ci_type = CIType.objects.create(code=meta['ci_type_code'], name=meta['label'], icon='Box', color='#245bdb')
        delivered = []
        for index, item in enumerate(raw_items, start=1):
            if not isinstance(item, dict):
                raise ValueError('资产交付清单中的每一项必须是对象')
            base_name = str(item.get('name') or item.get('resource_name') or specs.get('resource_name') or f'{meta["value"]}-{obj.id}').strip()
            name = f'{base_name}-{index:02d}' if len(raw_items) > 1 else base_name
            if not name:
                raise ValueError('完成交付前请填写资产名称')
            attributes = {key: value for key, value in {**specs, **item}.items() if key not in {'items', 'resources'} and value not in (None, '')}
            attributes.update({
                'source': 'resource_request',
                'request_id': obj.id,
                'request_title': obj.title,
                'request_item_index': index,
                'resource_type': resource_type,
                'cloud_provider': '阿里云' if specs.get('provider') == 'aliyun' else (provider_label(specs.get('provider')) if specs.get('provider') else '阿里云'),
                'provider': specs.get('provider') or 'aliyun',
                'resource_id': item.get('resource_id') or item.get('instance_id') or '',
                'region': item.get('region') or specs.get('region') or '',
                'description': item.get('description') or fulfillment_note or obj.reason,
            })
            config_item = ConfigItem.objects.filter(name=name).first()
            before = _config_item_snapshot(config_item) if config_item else {}
            if config_item:
                config_item.ci_type = ci_type
                config_item.business_line = obj.business_line
                config_item.environment = obj.environment or config_item.environment or ''
                config_item.admin_user = item.get('admin_user') or specs.get('admin_user') or obj.applicant
                config_item.status = 'active'
                config_item.attributes = attributes
                config_item.save()
                is_create = False
            else:
                config_item = ConfigItem.objects.create(
                    name=name,
                    ci_type=ci_type,
                    business_line=obj.business_line,
                    environment=obj.environment or '',
                    admin_user=item.get('admin_user') or specs.get('admin_user') or obj.applicant,
                    status='active',
                    attributes=attributes,
                )
                is_create = True
            source_unique_id = str(obj.id) if len(raw_items) == 1 else f'{obj.id}:{index}'
            CISourceMapping.objects.update_or_create(
                source_type='resource_request',
                source_account=str(specs.get('cloud_credential_id') or obj.applicant),
                source_region=attributes.get('region') or obj.environment or '',
                source_unique_id=source_unique_id,
                defaults={'ci': config_item, 'sync_status': 'success', 'last_seen_at': timezone.now(), 'raw_payload': {'request_id': obj.id, 'resource_type': resource_type, 'item': item, 'fulfillment_note': fulfillment_note}},
            )
            _record_ci_change(config_item, 'create' if is_create else 'update', before, _config_item_snapshot(config_item), operator=operator, source='resource_request')
            delivered.append((None, config_item))
        return delivered

    def _merge_delivery_specs_from_request(self, obj, request):
        incoming_specs = request.data.get('specs')
        incoming_hosts = request.data.get('hosts') or request.data.get('items') or request.data.get('resources')
        if incoming_specs is None and incoming_hosts is None:
            return False
        if incoming_specs is not None and not isinstance(incoming_specs, dict):
            raise ValueError('交付规格必须是对象')
        if incoming_hosts is not None and not isinstance(incoming_hosts, list):
            raise ValueError('交付主机清单必须是数组')

        specs = dict(obj.specs or {})
        if incoming_specs:
            for key, value in incoming_specs.items():
                if value in (None, ''):
                    specs.pop(key, None)
                else:
                    specs[key] = value
        if incoming_hosts is not None:
            if str(obj.resource_type or '').strip().lower() not in {'主机', 'host', 'ecs'}:
                specs['items'] = incoming_hosts
            else:
                specs['hosts'] = incoming_hosts
                specs.pop('hostname', None)
                specs.pop('ip_address', None)
        obj.specs = specs
        return True

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        obj = self.get_object()
        if obj.status != 'pending':
            return Response({'detail': '只能审批待审批资源'}, status=400)
        before = _resource_request_snapshot(obj)
        obj.status = 'approved'
        obj.approver = request.user.username
        obj.approval_comment = (request.data.get('comment') or request.data.get('approval_comment') or '').strip()
        obj.approved_at = timezone.now()
        obj.save(update_fields=['status', 'approver', 'approval_comment', 'approved_at', 'updated_at'])
        _record_request_change(
            obj,
            'request_approve',
            before,
            _resource_request_snapshot(obj),
            operator=getattr(request.user, 'username', ''),
        )
        return Response(ResourceRequestSerializer(obj).data)
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        obj = self.get_object()
        if obj.status != 'pending':
            return Response({'detail': '只能审批待审批资源'}, status=400)
        before = _resource_request_snapshot(obj)
        obj.status = 'rejected'
        obj.approver = request.user.username
        obj.approval_comment = (request.data.get('comment') or request.data.get('approval_comment') or '').strip()
        obj.save(update_fields=['status', 'approver', 'approval_comment', 'updated_at'])
        _record_request_change(
            obj,
            'request_reject',
            before,
            _resource_request_snapshot(obj),
            operator=getattr(request.user, 'username', ''),
        )
        return Response(ResourceRequestSerializer(obj).data)

    @action(detail=True, methods=['post'])
    def provision(self, request, pk=None):
        obj = self.get_object()
        if obj.status not in {'approved', 'failed'}:
            return Response({'detail': '只能交付已批准或交付失败的资源申请'}, status=400)
        if (obj.specs or {}).get('provisioning_mode') != 'cloud':
            return Response({'detail': '当前申请为人工交付，请使用人工交付操作'}, status=400)

        operator = getattr(request.user, 'username', '')
        before = _resource_request_snapshot(obj)
        specs = dict(obj.specs or {})
        previous = specs.get('provisioning') if isinstance(specs.get('provisioning'), dict) else {}
        specs['provisioning'] = {
            **previous,
            'status': 'running',
            'operator': operator,
            'started_at': timezone.now().isoformat(),
            'attempts': int(previous.get('attempts') or 0) + 1,
            'error': '',
        }
        obj.status = 'provisioning'
        obj.specs = specs
        obj.save(update_fields=['status', 'specs', 'updated_at'])
        _record_request_change(
            obj,
            'request_provision_start',
            before,
            _resource_request_snapshot(obj),
            operator=operator,
        )

        resources = []
        try:
            credential, resources = provision_resource_request(obj)
            with transaction.atomic():
                obj.refresh_from_db()
                specs = dict(obj.specs or {})
                specs['hosts'] = [
                    {
                        'hostname': item.get('hostname') or '',
                        'ip_address': item.get('private_ip') or '',
                        'public_ip': item.get('public_ip') or '',
                        'instance_id': item.get('instance_id') or '',
                        'instance_type': item.get('instance_type') or obj.specification,
                        'os_type': specs.get('os_type') or 'Linux',
                        'admin_user': specs.get('admin_user') or obj.applicant,
                        'provider': item.get('provider') or specs.get('provider') or '',
                        'region': item.get('region') or specs.get('region') or '',
                        'zone': item.get('zone') or specs.get('zone') or '',
                        'status': item.get('status') or '',
                    }
                    for item in resources
                ]
                specs['provisioning'] = {
                    **(specs.get('provisioning') or {}),
                    'status': 'success',
                    'completed_at': timezone.now().isoformat(),
                    'credential_id': credential.id,
                    'credential_name': credential.name,
                    'provider': credential.provider,
                    'resources': resources,
                    'error': '',
                }
                obj.specs = specs
                self._sync_request_to_host_assets(
                    obj,
                    fulfillment_note=(request.data.get('note') or '云平台自动交付完成').strip(),
                    operator=operator,
                )
                obj.status = 'completed'
                obj.fulfillment_note = (request.data.get('note') or '云平台自动交付完成').strip()
                obj.completed_at = timezone.now()
                obj.save(update_fields=['status', 'specs', 'fulfillment_note', 'completed_at', 'updated_at'])
                _record_request_change(
                    obj,
                    'request_provision_complete',
                    before,
                    _resource_request_snapshot(obj),
                    operator=operator,
                )
        except Exception as exc:
            obj.refresh_from_db()
            specs = dict(obj.specs or {})
            current = specs.get('provisioning') if isinstance(specs.get('provisioning'), dict) else {}
            specs['provisioning'] = {
                **current,
                'status': 'failed',
                'failed_at': timezone.now().isoformat(),
                'resources': resources or current.get('resources') or [],
                'error': str(exc)[:1000],
            }
            obj.status = 'failed'
            obj.specs = specs
            obj.save(update_fields=['status', 'specs', 'updated_at'])
            _record_request_change(
                obj,
                'request_provision_failed',
                before,
                _resource_request_snapshot(obj),
                operator=operator,
            )
            record_event(
                request=request,
                module='cmdb',
                category='execution',
                action='resource_request_provision',
                title='资源申请自动交付失败',
                summary=f'资源申请 #{obj.id} 自动交付失败：{str(exc)[:240]}',
                result=EventRecord.RESULT_FAILED,
                severity=EventRecord.SEVERITY_WARNING,
                resource_type='resource_request',
                resource_id=str(obj.id),
                resource_name=obj.title,
                metadata={'provider': (obj.specs or {}).get('provider'), 'request_id': obj.id},
            )
            return Response({'detail': str(exc)}, status=400)

        record_event(
            request=request,
            module='cmdb',
            category='execution',
            action='resource_request_provision',
            title='资源申请自动交付完成',
            summary=f'资源申请 #{obj.id} 已在 {provider_label((obj.specs or {}).get("provider"))} 创建 {len(resources)} 台机器并写入 CMDB。',
            result=EventRecord.RESULT_SUCCESS,
            severity=EventRecord.SEVERITY_INFO,
            resource_type='resource_request',
            resource_id=str(obj.id),
            resource_name=obj.title,
            metadata={'provider': (obj.specs or {}).get('provider'), 'request_id': obj.id, 'resource_count': len(resources)},
        )
        return Response(ResourceRequestSerializer(obj).data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        obj = self.get_object()
        if obj.status != 'approved':
            return Response({'detail': '只能完成已批准资源'}, status=400)
        if (obj.specs or {}).get('provisioning_mode') == 'cloud':
            return Response({'detail': '当前申请为云平台自动交付，请使用自动交付操作'}, status=400)
        fulfillment_note = (request.data.get('note') or request.data.get('fulfillment_note') or '').strip()
        try:
            with transaction.atomic():
                before = _resource_request_snapshot(obj)
                specs_changed = self._merge_delivery_specs_from_request(obj, request)
                self._sync_request_to_cloud_asset(obj, fulfillment_note=fulfillment_note, operator=request.user.username)
                obj.status = 'completed'
                obj.fulfillment_note = fulfillment_note
                obj.completed_at = timezone.now()
                update_fields = ['status', 'fulfillment_note', 'completed_at', 'updated_at']
                if specs_changed:
                    update_fields.append('specs')
                obj.save(update_fields=update_fields)
                _record_request_change(
                    obj,
                    'request_complete',
                    before,
                    _resource_request_snapshot(obj),
                    operator=getattr(request.user, 'username', ''),
                )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(ResourceRequestSerializer(obj).data)


def _search_match_fields(ci, keyword):
    if not keyword:
        return []
    matched = []
    checks = [
        ('name', '名称', ci.name),
        ('ci_type', '模型', ci.ci_type.name if ci.ci_type_id else ''),
        ('business_line', '业务线', ci.business_line),
        ('environment', '环境', ci.get_environment_display() if ci.environment else ''),
        ('admin_user', '负责人', ci.admin_user),
        ('status', '状态', ci.get_status_display() if ci.status else ''),
    ]
    for code, label, value in checks:
        if keyword in _normalize_search_text(value):
            matched.append({'field': code, 'label': label, 'value': value})

    for tag in ci.tags.all():
        tag_text = f'{tag.category} {tag.name}'.strip()
        if keyword in _normalize_search_text(tag_text):
            matched.append({'field': 'tags', 'label': '标签', 'value': tag.name})
            if len(matched) >= 8:
                return matched

    for key, value in _flatten_attribute_pairs(ci.attributes or {}):
        if keyword in _normalize_search_text(key) or keyword in _normalize_search_text(value):
            matched.append({'field': f'attributes.{key}', 'label': key, 'value': value})
            if len(matched) >= 8:
                return matched

    for source in _source_rows_for_ci(ci):
        for code in ['source_type', 'source_account', 'source_region', 'source_unique_id', 'sync_status']:
            value = source.get(code)
            if keyword in _normalize_search_text(value):
                matched.append({'field': code, 'label': code, 'value': value})
                if len(matched) >= 8:
                    return matched
    return matched


def _search_result_for_ci(ci, matched_fields=None):
    attributes = ci.attributes or {}
    key_attributes = {}
    for key in [
        'ip_address',
        'ip',
        'private_ip',
        'public_ip',
        'host_ip',
        'instance_id',
        'source_unique_id',
        'asset_no',
        'serial_number',
        'domain',
        'service_name',
        'region',
        'cloud_provider',
        'department',
    ]:
        if attributes.get(key) not in (None, ''):
            key_attributes[key] = attributes.get(key)
    return {
        'id': ci.id,
        'name': ci.name,
        'ci_type': ci.ci_type_id,
        'ci_type_name': normalize_ci_type_name(ci.ci_type.name),
        'ci_type_color': ci.ci_type.color or '#9c27b0',
        'ci_type_icon': ci.ci_type.icon,
        'group_name': ci.ci_type.group.name if ci.ci_type.group_id else '未分组',
        'business_line': ci.business_line,
        'environment': ci.environment,
        'environment_display': ci.get_environment_display() if ci.environment else '',
        'admin_user': ci.admin_user,
        'status': ci.status,
        'status_display': ci.get_status_display(),
        'source_type': _source_label_for_ci(ci),
        'sources': _source_rows_for_ci(ci),
        'tag_items': CITagSerializer(ci.tags.all(), many=True).data,
        'key_attributes': key_attributes,
        'matched_fields': matched_fields or [],
        'updated_at': ci.updated_at,
    }


def _ci_type_identity(ci):
    name = normalize_ci_type_name(ci.ci_type.name if ci.ci_type_id else '')
    code = (ci.ci_type.code if ci.ci_type_id else '') or ''
    return f'{name} {code}'.lower()


def _relation_count_for_ci(ci):
    return getattr(ci, 'outgoing_count', 0) + getattr(ci, 'incoming_count', 0)


def _is_cloud_binding_model(ci):
    identity = _ci_type_identity(ci)
    keywords = [
        'eip',
        '弹性 ip',
        '云盘',
        'disk',
        'volume',
        '负载均衡',
        'load balancer',
        'slb',
        'alb',
    ]
    return any(keyword in identity for keyword in keywords)


def _is_data_service_model(ci):
    identity = _ci_type_identity(ci)
    keywords = ['mysql', 'redis', 'rds', 'mongodb', 'kafka', 'rocketmq', 'postgresql', '数据库', '中间件']
    return any(keyword in identity for keyword in keywords)


def _has_binding_attribute(attributes):
    binding_keys = [
        'attached_instance_id',
        'instance_id',
        'host_id',
        'server_id',
        'backend_servers',
        'backend_server_ids',
        'listener_count',
        'mount_instance_id',
        'bound_resource_id',
        'target_group_id',
        'application_id',
        'app_code',
        'service_id',
        'service_name',
    ]
    return any(attributes.get(key) not in (None, '', [], {}) for key in binding_keys)


def _island_issue_payload(ci, issue_type, severity, reason, suggestion):
    attributes = ci.attributes or {}
    return {
        'ci_id': ci.id,
        'ci_name': ci.name,
        'ci_type': ci.ci_type_id,
        'ci_type_name': normalize_ci_type_name(ci.ci_type.name if ci.ci_type_id else ''),
        'business_line': ci.business_line,
        'environment': ci.environment,
        'environment_display': ci.get_environment_display() if ci.environment else '',
        'admin_user': ci.admin_user,
        'status': ci.status,
        'issue_type': issue_type,
        'severity': severity,
        'reason': reason,
        'suggestion': suggestion,
        'relation_count': _relation_count_for_ci(ci),
        'source_type': _source_label_for_ci(ci),
        'key_attributes': {
            key: attributes.get(key)
            for key in ['private_ip', 'public_ip', 'ip_address', 'instance_id', 'domain', 'endpoint', 'region']
            if attributes.get(key) not in (None, '')
        },
        'updated_at': ci.updated_at,
    }


def _relation_candidate_hint_context(hint=None, peer_role='target', current_source=None):
    hint = hint if isinstance(hint, dict) else {}
    current_source = current_source or {}
    peer = _sync_relation_peer_payload(hint, peer_role) if hint else {}
    source = _sync_relation_peer_source(hint, peer_role, current_source) if hint else {
        'source_type': '',
        'source_account': '',
        'source_region': '',
        'source_unique_id': '',
    }
    name = (
        hint.get(f'{peer_role}_name')
        or hint.get(f'{peer_role}_ci_name')
        or hint.get('peer_name')
        or hint.get('ci_name')
        or peer.get('name')
        or peer.get('ci_name')
        or peer.get('resource_name')
        or ''
    )
    attr_groups = {
        'ip': (SYNC_RELATION_IP_KEYS, _sync_relation_peer_value(hint, peer, peer_role, *SYNC_RELATION_IP_KEYS)),
        'endpoint': (SYNC_RELATION_ENDPOINT_KEYS, _sync_relation_peer_value(hint, peer, peer_role, *SYNC_RELATION_ENDPOINT_KEYS)),
        'instance_id': (('instance_id', 'external_id', 'resource_id'), _sync_relation_peer_value(hint, peer, peer_role, 'instance_id', 'external_id', 'resource_id')),
    }
    tag_ids, tag_specs = _normalize_payload_tag_specs({'tags': _sync_relation_peer_tag_payload(hint, peer, peer_role)})
    return {
        'name': str(name or '').strip(),
        'source': source,
        'business_line': _sync_relation_peer_value(hint, peer, peer_role, 'business_line', 'biz'),
        'environment': _sync_relation_peer_value(hint, peer, peer_role, 'environment', 'env'),
        'attr_groups': attr_groups,
        'tag_ids': set(tag_ids),
        'tag_specs': tag_specs,
    }


def _candidate_attr_matches(attributes, value, keys):
    if not value:
        return False
    expected = str(value).strip()
    return any(str(attributes.get(key) or '').strip() == expected for key in keys)


def _candidate_tag_match_count(candidate, tag_ids, tag_specs):
    if not tag_ids and not tag_specs:
        return 0
    tags = list(candidate.tags.all())
    matched = 0
    if tag_ids:
        matched += len({tag.id for tag in tags if tag.id in tag_ids})
    for spec in tag_specs:
        for tag in tags:
            if tag.name == spec.get('name') and (not spec.get('category') or tag.category == spec.get('category')):
                matched += 1
                break
    return matched


def _relation_candidate_suggestions(ci, rule, direction, user=None, limit=5, hint=None, peer_role=None, current_source=None):
    peer_type = rule.source_type if direction == 'incoming' else rule.target_type
    existing_relation_filter = {
        'target': ci,
        'relation_type': rule.relation_type,
    } if direction == 'incoming' else {
        'source': ci,
        'relation_type': rule.relation_type,
    }
    existing_peer_field = 'source_id' if direction == 'incoming' else 'target_id'
    existing_peer_ids = set(CIRelation.objects.filter(**existing_relation_filter).values_list(existing_peer_field, flat=True))

    qs = ConfigItem.objects.select_related('ci_type').filter(ci_type=peer_type).exclude(id=ci.id)
    if existing_peer_ids:
        qs = qs.exclude(id__in=existing_peer_ids)
    if user is not None:
        qs = _apply_ci_authorization_scope(qs, user)

    ci_attrs = ci.attributes or {}
    ci_department = str(ci_attrs.get('department') or '').strip()
    hint_context = _relation_candidate_hint_context(hint, peer_role or ('source' if direction == 'incoming' else 'target'), current_source)
    candidates = []
    for candidate in qs.order_by('-updated_at', 'name')[:200]:
        candidate_attrs = candidate.attributes or {}
        candidate_department = str(candidate_attrs.get('department') or '').strip()
        score = 0
        reasons = []
        source = hint_context['source']
        source_unique_id = source.get('source_unique_id') or ''
        source_keys = ('source_unique_id', 'instance_id', 'external_id', 'resource_id')
        if source_unique_id:
            source_mapping_q = {
                key: value
                for key, value in source.items()
                if value not in (None, '')
            }
            if source_mapping_q and CISourceMapping.objects.filter(ci=candidate, **source_mapping_q).exists():
                score += 120
                reasons.append('来源身份命中')
            elif _candidate_attr_matches(candidate_attrs, source_unique_id, source_keys):
                score += 90
                reasons.append('来源ID命中')
        hint_name = hint_context['name']
        if hint_name:
            candidate_name = str(candidate.name or '').strip()
            if candidate_name == hint_name:
                score += 100
                reasons.append('名称命中')
            elif hint_name.lower() in candidate_name.lower() or candidate_name.lower() in hint_name.lower():
                score += 50
                reasons.append('名称相似')
        attr_score_map = {'ip': 90, 'endpoint': 80, 'instance_id': 90}
        attr_reason_map = {'ip': 'IP命中', 'endpoint': '端点命中', 'instance_id': '实例ID命中'}
        for match_name, (keys, value) in hint_context['attr_groups'].items():
            if _candidate_attr_matches(candidate_attrs, value, keys):
                score += attr_score_map[match_name]
                reasons.append(attr_reason_map[match_name])
        matched_tags = _candidate_tag_match_count(candidate, hint_context['tag_ids'], hint_context['tag_specs'])
        if matched_tags:
            score += min(60, matched_tags * 30)
            reasons.append('标签命中')
        if hint_context['business_line'] and candidate.business_line == hint_context['business_line']:
            score += 35
            reasons.append('线索业务线')
        if hint_context['environment'] and candidate.environment == hint_context['environment']:
            score += 25
            reasons.append('线索环境')
        if ci.business_line and candidate.business_line == ci.business_line:
            score += 40
            reasons.append('同业务线')
        if ci.environment and candidate.environment == ci.environment:
            score += 30
            reasons.append('同环境')
        if ci_department and candidate_department and ci_department == candidate_department:
            score += 15
            reasons.append('同部门')
        if ci.admin_user and candidate.admin_user and ci.admin_user == candidate.admin_user:
            score += 8
            reasons.append('同负责人')
        if candidate.status == 'active':
            score += 10
            reasons.append('使用中')
        if not reasons:
            reasons.append('匹配模型规则')
        row = _relation_candidate_row(candidate, score=score, reasons=reasons)
        row['_rank_score'] = score
        candidates.append(row)
    candidates.sort(key=lambda item: (-item['_rank_score'], item['status'] != 'active', item['name']))
    rows = candidates[:limit]
    for item in rows:
        item.pop('_rank_score', None)
    return rows


def _missing_required_relation_rules(ci, required_rules):
    missing = []
    for rule in required_rules:
        direction = (rule.direction or 'outgoing').lower()
        if direction == 'incoming':
            if rule.target_type_id != ci.ci_type_id:
                continue
            exists = CIRelation.objects.filter(
                source__ci_type_id=rule.source_type_id,
                target=ci,
                relation_type=rule.relation_type,
            ).exists()
            peer_type_name = normalize_ci_type_name(rule.source_type.name)
        else:
            if rule.source_type_id != ci.ci_type_id:
                continue
            exists = CIRelation.objects.filter(
                source=ci,
                target__ci_type_id=rule.target_type_id,
                relation_type=rule.relation_type,
            ).exists()
            peer_type_name = normalize_ci_type_name(rule.target_type.name)
        if not exists:
            missing.append({
                'rule_id': rule.id,
                'relation_type': rule.relation_type,
                'peer_type': rule.source_type_id if direction == 'incoming' else rule.target_type_id,
                'peer_type_name': peer_type_name,
                'direction': direction,
                'rule': rule,
            })
    return missing


def _missing_required_relation_extra(ci, missing_rule, user=None):
    candidates = _relation_candidate_suggestions(
        ci,
        missing_rule['rule'],
        missing_rule['direction'],
        user=user,
    )
    best_candidate = candidates[0] if candidates else None
    governance_status = 'auto_candidate' if best_candidate else 'manual_required'
    return {
        'relation_rule_id': missing_rule['rule_id'],
        'relation_type': missing_rule['relation_type'],
        'relation_direction': missing_rule['direction'],
        'peer_type': missing_rule['peer_type'],
        'peer_type_name': missing_rule['peer_type_name'],
        'relation_candidates': candidates,
        'candidate_count': len(candidates),
        'best_candidate': best_candidate,
        'governance_status': governance_status,
        'can_auto_create': bool(best_candidate),
    }


def _normalize_unique_field_duplicate_value(value):
    if value in (None, '', [], {}):
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _duplicate_unique_field_issue_map(config_items):
    unique_fields = (
        CIField.objects.filter(unique=True, is_active=True)
        .select_related('ci_type')
        .order_by('ci_type_id', 'sort_order', 'id')
    )
    fields_by_type = defaultdict(list)
    for field in unique_fields:
        fields_by_type[field.ci_type_id].append(field)
    if not fields_by_type:
        return {}

    buckets = defaultdict(list)
    for ci in config_items:
        attributes = ci.attributes or {}
        for field in fields_by_type.get(ci.ci_type_id, []):
            value = _normalize_unique_field_duplicate_value(attributes.get(field.code))
            if value is None:
                continue
            buckets[(ci.ci_type_id, field.code, value)].append((ci, field))

    issue_map = defaultdict(list)
    for (_ci_type_id, _field_code, value), entries in buckets.items():
        if len(entries) < 2:
            continue
        field = entries[0][1]
        duplicate_ci_ids = [ci.id for ci, _field in entries]
        duplicate_ci_names = [ci.name for ci, _field in entries]
        for ci, _field in entries:
            issue_map[ci.id].append({
                'field_code': field.code,
                'field_name': field.name,
                'value': value,
                'ci_ids': duplicate_ci_ids,
                'ci_names': duplicate_ci_names,
                'count': len(entries),
            })
    return issue_map


def _build_island_analysis(limit=100, user=None):
    qs = (
        ConfigItem.objects.select_related('ci_type')
        .prefetch_related('source_mappings')
        .annotate(outgoing_count=Count('outgoing_relations', distinct=True), incoming_count=Count('incoming_relations', distinct=True))
        .order_by('-updated_at', '-id')
    )
    if user is not None:
        qs = _apply_ci_authorization_scope(qs, user)
    config_items = list(qs)
    duplicate_unique_field_issues = _duplicate_unique_field_issue_map(config_items)
    issues = []
    summary = defaultdict(int)
    severity_order = {'high': 3, 'medium': 2, 'low': 1}
    required_rules = list(
        CIRelationRule.objects.filter(required=True, is_active=True)
        .select_related('source_type', 'target_type')
        .order_by('source_type__name', 'target_type__name', 'relation_type')
    )

    def add_issue(ci, issue_type, severity, reason, suggestion, extra=None):
        summary[issue_type] += 1
        summary[f'severity_{severity}'] += 1
        if len(issues) >= limit:
            return
        payload = _island_issue_payload(ci, issue_type, severity, reason, suggestion)
        if extra:
            payload.update(extra() if callable(extra) else extra)
        issues.append(payload)

    for ci in config_items:
        attributes = ci.attributes or {}
        relation_count = _relation_count_for_ci(ci)
        source_rows = _source_rows_for_ci(ci)
        has_source = bool(source_rows) or any(attributes.get(key) for key in ['source_type', 'source', 'source_unique_id', 'external_id'])

        for duplicate_issue in duplicate_unique_field_issues.get(ci.id, []):
            add_issue(
                ci,
                'duplicate_unique_field',
                'high',
                f"唯一字段 {duplicate_issue['field_name']} 存在重复值 {duplicate_issue['value']}，涉及 {duplicate_issue['count']} 个资源。",
                '合并重复资源、修正唯一字段值，或通过来源映射确认真实资源身份后再同步。',
                extra={
                    'duplicate_field_code': duplicate_issue['field_code'],
                    'duplicate_field_name': duplicate_issue['field_name'],
                    'duplicate_value': duplicate_issue['value'],
                    'duplicate_ci_ids': duplicate_issue['ci_ids'],
                    'duplicate_ci_names': duplicate_issue['ci_names'],
                    'duplicate_count': duplicate_issue['count'],
                },
            )
        if not ci.business_line or not ci.admin_user or not str(attributes.get('department') or '').strip():
            add_issue(
                ci,
                'missing_ownership',
                'high' if ci.status == 'active' else 'medium',
                '缺少业务线、部门或负责人，无法确认资源归属。',
                '补齐业务线、部门、环境和负责人，必要时从云标签或资源树批量回填。',
            )
        if relation_count == 0:
            add_issue(
                ci,
                'no_relation',
                'medium',
                '当前资源没有任何上游或下游关系。',
                '为资源补充应用、服务、主机、数据库或网络入口关系。',
            )
        for missing_rule in _missing_required_relation_rules(ci, required_rules):
            relation_extra = _missing_required_relation_extra(ci, missing_rule, user=user)
            if relation_extra['can_auto_create']:
                summary['relation_auto_candidate_count'] += 1
            else:
                summary['relation_manual_required_count'] += 1
            add_issue(
                ci,
                'missing_required_relation',
                'high' if ci.status == 'active' else 'medium',
                f"缺少必填关系：需要通过 {missing_rule['relation_type']} 关联 {missing_rule['peer_type_name']}。",
                '在资源拓扑或关系管理中补齐必填关系，确保应用、主机、数据服务和云资源链路完整。',
                extra=relation_extra,
            )
        if not has_source:
            add_issue(
                ci,
                'no_source',
                'medium',
                '资源没有采集来源或外部唯一标识，后续无法做自动对账。',
                '补充 source_type、source_unique_id 或通过同步中心重新入库。',
            )
        if _is_cloud_binding_model(ci) and relation_count == 0 and not _has_binding_attribute(attributes):
            add_issue(
                ci,
                'unbound_cloud_resource',
                'high',
                '疑似云资源未绑定到主机、应用或后端服务。',
                '核对云侧绑定关系，未使用资源进入回收或下线确认流程。',
            )
        if _is_data_service_model(ci) and not ci.business_line and relation_count == 0:
            add_issue(
                ci,
                'unlinked_data_service',
                'high',
                '数据库或中间件没有业务归属，也没有应用关系。',
                '补充应用依赖关系和负责人，避免故障、成本和权限无人负责。',
            )

    issues.sort(
        key=lambda item: (
            severity_order.get(item['severity'], 0),
            item['updated_at'] or timezone.now(),
        ),
        reverse=True,
    )
    issue_summary_keys = (
        'missing_ownership',
        'no_relation',
        'missing_required_relation',
        'duplicate_unique_field',
        'no_source',
        'unbound_cloud_resource',
        'unlinked_data_service',
    )
    missing_required_count = summary['missing_required_relation']
    auto_candidate_count = summary['relation_auto_candidate_count']
    return {
        'summary': {
            'total': sum(summary[key] for key in issue_summary_keys),
            'missing_ownership': summary['missing_ownership'],
            'no_relation': summary['no_relation'],
            'missing_required_relation': summary['missing_required_relation'],
            'duplicate_unique_field': summary['duplicate_unique_field'],
            'no_source': summary['no_source'],
            'unbound_cloud_resource': summary['unbound_cloud_resource'],
            'unlinked_data_service': summary['unlinked_data_service'],
            'relation_auto_candidate_count': auto_candidate_count,
            'relation_manual_required_count': summary['relation_manual_required_count'],
            'candidate_coverage_rate': round(auto_candidate_count * 100 / missing_required_count) if missing_required_count else 0,
            'severity_high': summary['severity_high'],
            'severity_medium': summary['severity_medium'],
            'severity_low': summary['severity_low'],
        },
        'results': issues[:limit],
    }


def _ci_type_text(ci_type):
    if not ci_type:
        return ''
    parts = [
        normalize_ci_type_name(ci_type.name),
        ci_type.code or '',
        ci_type.group.name if ci_type.group_id else '',
    ]
    return ' '.join(parts).lower()


def _is_application_type(ci_type):
    text = _ci_type_text(ci_type)
    return any(keyword in text for keyword in ['app', 'application', '应用', '系统', '业务系统'])


def _is_host_type(ci_type):
    text = _ci_type_text(ci_type)
    return any(keyword in text for keyword in ['host', 'server', 'ecs', '主机', '服务器', '虚拟机', '物理机', 'cloud_server'])


def _is_physical_host(ci):
    attributes = ci.attributes or {}
    text = _ci_type_text(ci.ci_type)
    physical_keys = ['idc', 'datacenter', 'machine_room', 'room', 'rack', 'cabinet', 'u_position', 'asset_sn', 'serial_number']
    if any(attributes.get(key) not in (None, '') for key in physical_keys):
        return True
    return any(keyword in text for keyword in ['physical', 'baremetal', '物理机', '机房'])


def _host_ip(attributes):
    return (
        attributes.get('ip_address')
        or attributes.get('private_ip')
        or attributes.get('public_ip')
        or attributes.get('host_ip')
        or attributes.get('ip')
        or ''
    )


def _host_kind(ci):
    attributes = ci.attributes or {}
    text = _ci_type_text(ci.ci_type)
    source = _source_label_for_ci(ci).lower()
    if _is_physical_host(ci):
        return 'physical'
    if any(keyword in text for keyword in ['ecs', 'cloud', '云主机']) or any(keyword in source for keyword in ['aliyun', 'tencent', 'huawei', 'aws']):
        return 'cloud'
    return 'virtual'


def _related_items_for_ci(ci, relations):
    related = []
    for relation in relations:
        if relation.source_id == ci.id:
            related.append((relation.target, relation))
        elif relation.target_id == ci.id:
            related.append((relation.source, relation))
    return related


def _view_filters(request):
    return {
        'business_line': (request.query_params.get('business_line') or '').strip(),
        'environment': (request.query_params.get('environment') or '').strip(),
    }


def _apply_ci_filters(qs, filters):
    if filters.get('business_line'):
        qs = qs.filter(business_line=filters['business_line'])
    if filters.get('environment'):
        qs = qs.filter(environment=filters['environment'])
    return qs


def _build_cmdb_views(request):
    filters = _view_filters(request)
    qs = (
        _apply_ci_authorization_scope(
            _apply_ci_filters(ConfigItem.objects.select_related('ci_type', 'ci_type__group').prefetch_related('source_mappings'), filters),
            request.user,
        )
        .annotate(outgoing_count=Count('outgoing_relations', distinct=True), incoming_count=Count('incoming_relations', distinct=True))
        .order_by('business_line', 'environment', 'ci_type__name', 'name')
    )
    ci_items = list(qs)
    ci_by_id = {ci.id: ci for ci in ci_items}
    ci_ids = set(ci_by_id)
    relations = list(
        CIRelation.objects.filter(source_id__in=ci_ids, target_id__in=ci_ids)
        .select_related('source', 'source__ci_type', 'target', 'target__ci_type')
        .order_by('id')
    )

    applications = []
    hosts = []
    physical_groups = {}
    relation_count = len(relations)
    for ci in ci_items:
        attributes = ci.attributes or {}
        relation_count_for_ci = _relation_count_for_ci(ci)
        if _is_application_type(ci.ci_type):
            related = _related_items_for_ci(ci, relations)
            service_code = attributes.get('service_code') or attributes.get('app_code') or attributes.get('code') or ''
            owner_team = attributes.get('owner_team') or attributes.get('team') or attributes.get('department') or ''
            host_count = sum(1 for item, _ in related if _is_host_type(item.ci_type))
            data_count = sum(1 for item, _ in related if _is_data_service_model(item))
            service_count = sum(1 for item, _ in related if _is_application_type(item.ci_type))
            app_risk = 0
            risk_items = []
            if not ci.business_line or not ci.admin_user or not owner_team or not service_code:
                app_risk += 1
                risk_items.append('应用编码、归属或负责团队缺失')
            if host_count == 0:
                app_risk += 1
                risk_items.append('未关联主机')
            if data_count == 0:
                app_risk += 1
                risk_items.append('未关联数据服务')
            source_rows = list(ci.source_mappings.all())
            sync_dates = [item.last_seen_at for item in source_rows if item.last_seen_at]
            resource_count = host_count + data_count + service_count
            coverage_rate = min(round(resource_count * 100 / 3), 100)
            applications.append({
                'id': ci.id,
                'name': ci.name,
                'code': service_code,
                'service_code': service_code,
                'business_line': ci.business_line,
                'environment': ci.environment,
                'environment_display': ci.get_environment_display() if ci.environment else '',
                'admin_user': ci.admin_user,
                'department': attributes.get('department') or '',
                'owner_team': owner_team,
                'language': attributes.get('language') or attributes.get('tech_stack') or attributes.get('technology') or '',
                'repo': attributes.get('repo') or attributes.get('repository') or attributes.get('git_url') or '',
                'tier': attributes.get('tier') or attributes.get('service_level') or '',
                'tier_display': {'core': '核心', 'important': '重要', 'normal': '普通'}.get(str(attributes.get('tier') or attributes.get('service_level') or '').lower(), attributes.get('tier') or attributes.get('service_level') or '未分级'),
                'endpoint': attributes.get('endpoint') or attributes.get('url') or attributes.get('web_url') or '',
                'description': attributes.get('description') or attributes.get('summary') or '',
                'status': ci.status,
                'status_display': ci.get_status_display(),
                'service_count': service_count,
                'host_count': host_count,
                'data_service_count': data_count,
                'resource_count': resource_count,
                'coverage_rate': coverage_rate,
                'relation_count': relation_count_for_ci,
                'risk_count': app_risk,
                'risk_items': risk_items,
                'health_status': 'danger' if app_risk >= 2 else ('warning' if app_risk else 'success'),
                'health_text': '高风险' if app_risk >= 2 else ('需关注' if app_risk else '运行良好'),
                'source_count': len(source_rows),
                'last_sync_at': max(sync_dates).isoformat() if sync_dates else None,
                'updated_at': ci.updated_at,
            })

        if _is_host_type(ci.ci_type):
            hosts.append({
                'id': ci.id,
                'name': ci.name,
                'ci_type_name': normalize_ci_type_name(ci.ci_type.name),
                'kind': _host_kind(ci),
                'ip': _host_ip(attributes),
                'business_line': ci.business_line,
                'environment': ci.environment,
                'environment_display': ci.get_environment_display() if ci.environment else '',
                'admin_user': ci.admin_user,
                'department': attributes.get('department') or '',
                'status': ci.status,
                'status_display': ci.get_status_display(),
                'os': attributes.get('os') or attributes.get('os_type') or attributes.get('os_name') or '',
                'cpu': attributes.get('cpu') or attributes.get('cpu_cores') or '',
                'memory_gb': attributes.get('memory_gb') or attributes.get('memory') or '',
                'agent_status': attributes.get('agent_status') or attributes.get('agent') or '',
                'source_type': _source_label_for_ci(ci),
                'relation_count': relation_count_for_ci,
                'updated_at': ci.updated_at,
            })

        if _is_physical_host(ci):
            room = attributes.get('machine_room') or attributes.get('room') or attributes.get('idc') or attributes.get('datacenter') or '未分配机房'
            rack = attributes.get('rack') or attributes.get('cabinet') or '未分配机柜'
            zone = attributes.get('zone') or attributes.get('area') or attributes.get('region') or ''
            key = (room, rack, zone)
            row = physical_groups.setdefault(key, {
                'room': room,
                'rack': rack,
                'zone': zone,
                'host_count': 0,
                'active_count': 0,
                'occupied_u': 0,
                'business_lines': set(),
                'hosts': [],
            })
            row['host_count'] += 1
            if ci.status == 'active':
                row['active_count'] += 1
            if attributes.get('u_position') or attributes.get('u'):
                row['occupied_u'] += 1
            if ci.business_line:
                row['business_lines'].add(ci.business_line)
            row['hosts'].append({
                'id': ci.id,
                'name': ci.name,
                'ip': _host_ip(attributes),
                'u_position': attributes.get('u_position') or attributes.get('u') or '',
                'status': ci.status,
                'status_display': ci.get_status_display(),
                'admin_user': ci.admin_user,
            })

    physical = []
    for row in physical_groups.values():
        physical.append({
            **row,
            'business_lines': sorted(row['business_lines']),
            'hosts': sorted(row['hosts'], key=lambda item: (str(item.get('u_position') or ''), item['name']))[:8],
        })
    physical.sort(key=lambda item: (-item['host_count'], item['room'], item['rack']))
    applications.sort(key=lambda item: (-item['host_count'], -item['relation_count'], item['name']))
    hosts.sort(key=lambda item: (item['business_line'] or '', item['environment'] or '', item['name']))

    return {
        'summary': {
            'application_count': len(applications),
            'host_count': len(hosts),
            'physical_location_count': len(physical),
            'relation_count': relation_count,
            'unowned_host_count': sum(
                1
                for item in hosts
                if not item['business_line'] or not item['admin_user'] or not str(item.get('department') or '').strip()
            ),
        },
        'applications': applications[:100],
        'hosts': hosts[:150],
        'physical': physical[:80],
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('cmdb.ci.view')])
def cmdb_resource_search(request):
    query = (request.query_params.get('q') or request.query_params.get('search') or '').strip()
    keyword = _normalize_search_text(query)
    try:
        limit = min(max(int(request.query_params.get('limit', 30)), 1), 100)
    except (TypeError, ValueError):
        limit = 30

    qs = _apply_ci_authorization_scope(
        ConfigItem.objects.select_related('ci_type', 'ci_type__group').prefetch_related('source_mappings', 'tags'),
        request.user,
    ).order_by('-updated_at', '-id')
    ci_type = request.query_params.get('ci_type')
    group = request.query_params.get('group')
    business_line = request.query_params.get('business_line')
    environment = request.query_params.get('environment')
    status_value = request.query_params.get('status')
    source_type = request.query_params.get('source_type')
    tag = request.query_params.get('tag') or request.query_params.get('tags')

    if ci_type:
        qs = qs.filter(ci_type_id=ci_type)
    if group:
        qs = qs.filter(ci_type__group_id=group)
    if business_line:
        qs = qs.filter(business_line=business_line)
    if environment:
        qs = qs.filter(environment=environment)
    if status_value:
        qs = qs.filter(status=status_value)
    if source_type:
        source_ci_ids = CISourceMapping.objects.filter(source_type=source_type).values_list('ci_id', flat=True)
        qs = qs.filter(Q(id__in=source_ci_ids) | Q(attributes__source_type=source_type) | Q(attributes__source=source_type))
    if tag:
        tag_filter = Q(tags__name=tag)
        if str(tag).isdigit():
            tag_filter |= Q(tags__id=int(tag))
        qs = qs.filter(tag_filter).distinct()

    total = 0
    results = []
    for ci in qs:
        matched_fields = _search_match_fields(ci, keyword) if keyword else []
        if keyword and not matched_fields:
            continue
        total += 1
        if len(results) < limit:
            results.append(_search_result_for_ci(ci, matched_fields))

    return Response({
        'query': query,
        'total': total,
        'limit': limit,
        'results': results,
    })


def _build_model_repository_payload(request, *, include_fields=False, include_tree=False):
    scoped_items = _apply_ci_authorization_scope(ConfigItem.objects.all(), request.user)
    scoped_ci_ids = scoped_items.values('id')
    data_quality = _build_data_quality_summary(scoped_items, scoped_ci_ids, user=request.user)
    data_quality_map = data_quality['model_quality_map']
    ci_counts = {
        row['ci_type_id']: row['count']
        for row in scoped_items.values('ci_type_id').annotate(count=Count('id'))
    }
    active_counts = {
        row['ci_type_id']: row['count']
        for row in scoped_items.filter(status='active').values('ci_type_id').annotate(count=Count('id'))
    }
    completion_counts = {
        row['ci__ci_type_id']: row['count']
        for row in CICompletionIssue.objects.exclude(status__in=['resolved', 'ignored'])
        .filter(ci_id__in=scoped_ci_ids)
        .values('ci__ci_type_id')
        .annotate(count=Count('id'))
    }
    archive_counts = {
        row['ci__ci_type_id']: row['count']
        for row in CIArchiveCandidate.objects.filter(status='pending')
        .filter(ci_id__in=scoped_ci_ids)
        .values('ci__ci_type_id')
        .annotate(count=Count('id'))
    }
    sync_failure_counts = {
        row['ci__ci_type_id']: row['count']
        for row in _sync_governance_record_queryset_for_user(request.user).filter(ci__isnull=False)
        .filter(ci_id__in=scoped_ci_ids)
        .values('ci__ci_type_id')
        .annotate(count=Count('id'))
    }
    field_rows = {}
    if include_fields:
        for field in CIField.objects.filter(is_active=True).order_by('sort_order', 'id'):
            rows = field_rows.setdefault(field.ci_type_id, [])
            rows.append({
                'id': field.id,
                'code': field.code,
                'name': field.name,
                'field_type': field.field_type,
                'field_group': field.field_group,
                'required': field.required,
                'unique': field.unique,
                'is_display': field.is_display,
                'is_searchable': field.is_searchable,
                'sync_mode': field.sync_mode,
                'sort_order': field.sort_order,
            })

    def model_payload(ci_type):
        total = ci_counts.get(ci_type.id, 0)
        completion = completion_counts.get(ci_type.id, 0)
        archive = archive_counts.get(ci_type.id, 0)
        sync_failures = sync_failure_counts.get(ci_type.id, 0)
        quality = data_quality_map.get(ci_type.id, {})
        return {
            'id': ci_type.id,
            'name': normalize_ci_type_name(ci_type.name),
            'code': ci_type.code,
            'icon': ci_type.icon,
            'color': ci_type.color or '#9c27b0',
            'description': ci_type.description,
            'is_builtin': ci_type.is_builtin,
            'is_active': ci_type.is_active,
            'ci_count': total,
            'active_count': active_counts.get(ci_type.id, 0),
            'risk_count': completion + archive + sync_failures,
            'completion_issue_count': completion,
            'archive_candidate_count': archive,
            'sync_failure_count': sync_failures,
            'quality_score': quality.get('score', 100),
            'quality_risk_count': quality.get('risk_count', 0),
            'quality_issue_counts': quality.get('issue_counts', {}),
            'field_count': len(field_rows.get(ci_type.id, [])) if include_fields else ci_type.fields.filter(is_active=True).count(),
            'required_field_count': sum(1 for field in field_rows.get(ci_type.id, []) if field['required']) if include_fields else ci_type.fields.filter(is_active=True, required=True).count(),
            'unique_field_count': sum(1 for field in field_rows.get(ci_type.id, []) if field['unique']) if include_fields else ci_type.fields.filter(is_active=True, unique=True).count(),
            **({'fields': field_rows.get(ci_type.id, [])} if include_fields else {}),
        }

    groups = []
    total_models = 0
    total_resources = 0
    total_risks = 0
    grouped_type_ids = set()
    for group_obj in CIModelGroup.objects.prefetch_related('ci_types').filter(is_active=True).order_by('sort_order', 'id'):
        models = [
            model_payload(ci_type)
            for ci_type in group_obj.ci_types.filter(is_active=True).order_by('name', 'id')
            if not is_placeholder_ci_type_name(ci_type.name)
        ]
        for item in models:
            grouped_type_ids.add(item['id'])
        group_resource_count = sum(item['ci_count'] for item in models)
        group_risk_count = sum(item['risk_count'] for item in models)
        group_quality_score = round(
            sum((item.get('quality_score') or 100) * max(int(item.get('ci_count') or 0), 0) for item in models) / group_resource_count
        ) if group_resource_count else 100
        total_models += len(models)
        total_resources += group_resource_count
        total_risks += group_risk_count
        groups.append({
            'id': group_obj.id,
            'name': group_obj.name,
            'code': group_obj.code,
            'description': group_obj.description,
            'sort_order': group_obj.sort_order,
            'is_builtin': group_obj.is_builtin,
            'model_count': len(models),
            'resource_count': group_resource_count,
            'risk_count': group_risk_count,
            'quality_score': group_quality_score,
            'models': models,
        })

    ungrouped_models = [
        model_payload(ci_type)
        for ci_type in CIType.objects.filter(is_active=True, group__isnull=True).order_by('name', 'id')
        if ci_type.id not in grouped_type_ids and not is_placeholder_ci_type_name(ci_type.name)
    ]
    if ungrouped_models:
        group_resource_count = sum(item['ci_count'] for item in ungrouped_models)
        group_risk_count = sum(item['risk_count'] for item in ungrouped_models)
        group_quality_score = round(
            sum((item.get('quality_score') or 100) * max(int(item.get('ci_count') or 0), 0) for item in ungrouped_models) / group_resource_count
        ) if group_resource_count else 100
        total_models += len(ungrouped_models)
        total_resources += group_resource_count
        total_risks += group_risk_count
        groups.append({
            'id': None,
            'name': '未分组',
            'code': 'ungrouped',
            'description': '尚未归入模型分组的资源模型',
            'sort_order': 9999,
            'is_builtin': False,
            'model_count': len(ungrouped_models),
            'resource_count': group_resource_count,
            'risk_count': group_risk_count,
            'quality_score': group_quality_score,
            'models': ungrouped_models,
        })

    top_models = sorted(
        [model for group_obj in groups for model in group_obj['models']],
        key=lambda item: (-item['ci_count'], item['name']),
    )[:10]

    payload = {
        'summary': {
            'group_count': len(groups),
            'model_count': total_models,
            'resource_count': total_resources,
            'risk_count': total_risks,
            'active_count': sum(active_counts.values()),
        },
        'groups': groups,
        'top_models': top_models,
    }
    if include_tree:
        payload['tree'] = [
            {
                'id': f"group:{group_obj['code']}",
                'node_type': 'group',
                'group_id': group_obj['id'],
                'name': group_obj['name'],
                'code': group_obj['code'],
                'description': group_obj['description'],
                'model_count': group_obj['model_count'],
                'resource_count': group_obj['resource_count'],
                'risk_count': group_obj['risk_count'],
                'quality_score': group_obj['quality_score'],
                'children': [
                    {
                        'id': f"model:{model['id']}",
                        'node_type': 'model',
                        'model_id': model['id'],
                        'name': model['name'],
                        'code': model['code'],
                        'icon': model['icon'],
                        'color': model['color'],
                        'ci_count': model['ci_count'],
                        'active_count': model['active_count'],
                        'risk_count': model['risk_count'],
                        'quality_score': model['quality_score'],
                        'field_count': model['field_count'],
                        'required_field_count': model['required_field_count'],
                        'unique_field_count': model['unique_field_count'],
                    }
                    for model in group_obj['models']
                ],
            }
            for group_obj in groups
        ]
    return payload


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('cmdb.ci.view')])
def cmdb_repository_summary(request):
    cache_key = _cmdb_ledger_request_cache_key(request, 'repository-summary')
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)
    payload = _build_model_repository_payload(request)
    cache.set(cache_key, payload, CMDB_MODEL_REPOSITORY_CACHE_TTL)
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('cmdb.ci.view')])
def cmdb_model_tree(request):
    include_fields = _to_bool(request.query_params.get('include_fields', False))
    cache_key = _cmdb_ledger_request_cache_key(request, 'model-tree')
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)
    payload = _build_model_repository_payload(request, include_fields=include_fields, include_tree=True)
    payload['source'] = 'model_tree'
    cache.set(cache_key, payload, CMDB_MODEL_REPOSITORY_CACHE_TTL)
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('cmdb.ci.view')])
def cmdb_island_analysis(request):
    cache_key = _cmdb_ledger_request_cache_key(request, 'island-analysis')
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)
    try:
        limit = min(max(int(request.query_params.get('limit', 100)), 1), 300)
    except (TypeError, ValueError):
        limit = 100
    payload = _build_island_analysis(limit=limit, user=request.user)
    issue_type = request.query_params.get('issue_type')
    severity = request.query_params.get('severity')
    if issue_type:
        payload['results'] = [item for item in payload['results'] if item['issue_type'] == issue_type]
    if severity:
        payload['results'] = [item for item in payload['results'] if item['severity'] == severity]
    cache.set(cache_key, payload, CMDB_ISLAND_ANALYSIS_CACHE_TTL)
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('cmdb.ci.view')])
def cmdb_views_summary(request):
    cache_key = _cmdb_ledger_request_cache_key(request, 'views-summary')
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)
    payload = _build_cmdb_views(request)
    cache.set(cache_key, payload, CMDB_VIEWS_SUMMARY_CACHE_TTL)
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('cmdb.sync.view')])
def cmdb_collection_summary(request):
    cache_key = _cmdb_ledger_request_cache_key(request, 'collection-summary')
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)
    payload = _build_collection_summary(user=request.user)
    cache.set(cache_key, payload, CMDB_COLLECTION_SUMMARY_CACHE_TTL)
    return Response(payload)


DATA_QUALITY_WEIGHTS = {
    'missing_ownership': 25,
    'no_relation': 15,
    'no_source': 15,
    'completion_issues': 30,
    'archive_candidates': 35,
    'sync_failures': 25,
}

DATA_QUALITY_LABELS = {
    'missing_ownership': '归属缺失',
    'no_relation': '关系断点',
    'no_source': '来源缺失',
    'completion_issues': '待补全',
    'archive_candidates': '待下线确认',
    'sync_failures': '同步失败',
}


def _governance_age_days(created_at):
    if not created_at:
        return 0
    return max((timezone.now() - created_at).days, 0)


def _governance_due_days(kind, severity=''):
    if kind == 'completion':
        if severity == 'high':
            return 1
        if severity == 'low':
            return 7
        return 3
    if kind == 'archive':
        return 7
    if kind == 'sync':
        return 1
    return 3


def _governance_due_at(created_at, due_days):
    return created_at + timedelta(days=due_days) if created_at else None


def _governance_is_overdue(created_at, due_days):
    due_at = _governance_due_at(created_at, due_days)
    return bool(due_at and timezone.now() > due_at)


def _governance_workload_summary(scoped_ci_ids, user=None):
    assignee_map = defaultdict(lambda: {
        'assignee': '',
        'total': 0,
        'overdue': 0,
        'completion': 0,
        'archive': 0,
        'sync': 0,
    })
    totals = defaultdict(int)
    overdue_tasks = []

    def normalize_assignee(value):
        value = (value or '').strip()
        return value or '未分派'

    def add_task(kind, *, task_id, title, ci_id=None, ci_name='', ci_type_name='', assignee='', severity='', status='', created_at=None):
        due_days = _governance_due_days(kind, severity)
        age_days = _governance_age_days(created_at)
        due_at = _governance_due_at(created_at, due_days)
        overdue = _governance_is_overdue(created_at, due_days)
        assignee_name = normalize_assignee(assignee)
        totals[f'{kind}_total'] += 1
        totals['total'] += 1
        if overdue:
            totals[f'{kind}_overdue'] += 1
            totals['overdue_total'] += 1
        bucket = assignee_map[assignee_name]
        bucket['assignee'] = assignee_name
        bucket['total'] += 1
        bucket[kind] += 1
        if overdue:
            bucket['overdue'] += 1
            overdue_tasks.append({
                'kind': kind,
                'id': task_id,
                'title': title,
                'ci_id': ci_id,
                'ci_name': ci_name,
                'ci_type_name': ci_type_name,
                'assignee': assignee_name,
                'severity': severity,
                'status': status,
                'age_days': age_days,
                'due_days': due_days,
                'due_at': due_at,
            })

    completion_issues = (
        CICompletionIssue.objects.exclude(status__in=['resolved', 'ignored'])
        .filter(ci_id__in=scoped_ci_ids)
        .select_related('ci', 'ci__ci_type')
    )
    for issue in completion_issues:
        add_task(
            'completion',
            task_id=issue.id,
            title='待补全资源',
            ci_id=issue.ci_id,
            ci_name=issue.ci.name if issue.ci_id else '',
            ci_type_name=normalize_ci_type_name(issue.ci.ci_type.name) if issue.ci_id else '',
            assignee=issue.assigned_to or (issue.ci.admin_user if issue.ci_id else ''),
            severity=issue.severity,
            status=issue.status,
            created_at=issue.created_at,
        )

    archive_candidates = (
        CIArchiveCandidate.objects.filter(status='pending', ci_id__in=scoped_ci_ids)
        .select_related('ci', 'ci__ci_type')
    )
    for candidate in archive_candidates:
        add_task(
            'archive',
            task_id=candidate.id,
            title='待下线确认',
            ci_id=candidate.ci_id,
            ci_name=candidate.ci.name if candidate.ci_id else '',
            ci_type_name=normalize_ci_type_name(candidate.ci.ci_type.name) if candidate.ci_id else '',
            assignee=candidate.confirmed_by or (candidate.ci.admin_user if candidate.ci_id else ''),
            severity='medium',
            status=candidate.status,
            created_at=candidate.created_at,
        )

    failed_sync_records = _sync_governance_record_queryset_for_user(user, include_global=False) if user is not None else CISyncRecord.objects.none()
    failed_sync_records = failed_sync_records.filter(ci_id__in=scoped_ci_ids).select_related('ci', 'ci__ci_type', 'job')
    for record in failed_sync_records:
        is_relation_issue = isinstance(record.after, dict) and int((record.after.get('_sync_relations') or {}).get('failed') or 0) > 0
        add_task(
            'sync',
            task_id=record.id,
            title='自动关系失败' if is_relation_issue and record.status != 'failed' else '同步失败',
            ci_id=record.ci_id,
            ci_name=record.ci.name if record.ci_id else record.source_unique_id,
            ci_type_name=normalize_ci_type_name(record.ci.ci_type.name) if record.ci_id else '',
            assignee=record.retried_by or (record.ci.admin_user if record.ci_id else ''),
            severity='high',
            status=record.status,
            created_at=record.created_at,
        )

    assignee_workload = sorted(
        assignee_map.values(),
        key=lambda item: (-item['overdue'], -item['total'], item['assignee']),
    )[:8]
    overdue_tasks.sort(key=lambda item: (-item['age_days'], item['due_days'], item['kind'], item['ci_name']))
    return {
        'total': totals['total'],
        'overdue_total': totals['overdue_total'],
        'completion_total': totals['completion_total'],
        'completion_overdue': totals['completion_overdue'],
        'archive_total': totals['archive_total'],
        'archive_overdue': totals['archive_overdue'],
        'sync_total': totals['sync_total'],
        'sync_overdue': totals['sync_overdue'],
        'assignee_workload': assignee_workload,
        'top_overdue_tasks': overdue_tasks[:8],
    }


def _build_data_quality_summary(scoped_items, scoped_ci_ids, user=None):
    items = list(
        scoped_items.select_related('ci_type')
        .prefetch_related('source_mappings')
        .annotate(outgoing_count=Count('outgoing_relations', distinct=True), incoming_count=Count('incoming_relations', distinct=True))
        .order_by('-updated_at', '-id')
    )
    if not items:
        return {
            'score': 100,
            'total': 0,
            'healthy': 0,
            'warning': 0,
            'critical': 0,
            'issue_counts': {key: 0 for key in DATA_QUALITY_WEIGHTS},
            'top_risks': [],
            'model_quality': [],
            'model_quality_map': {},
            'governance_workload': _governance_workload_summary(scoped_ci_ids, user=user),
        }

    open_completion_ci_ids = set(
        CICompletionIssue.objects.exclude(status__in=['resolved', 'ignored'])
        .filter(ci_id__in=scoped_ci_ids)
        .values_list('ci_id', flat=True)
    )
    pending_archive_ci_ids = set(
        CIArchiveCandidate.objects.filter(status='pending', ci_id__in=scoped_ci_ids)
        .values_list('ci_id', flat=True)
    )
    failed_sync_ci_ids = set(
        _sync_governance_record_queryset_for_user(user)
        .filter(ci_id__isnull=False)
        .values_list('ci_id', flat=True)
    ) if user is not None else set()

    issue_counts = defaultdict(int)
    status_counts = defaultdict(int)
    model_quality = defaultdict(lambda: {'score_total': 0, 'resource_count': 0, 'risk_count': 0, 'issue_counts': defaultdict(int)})
    model_quality_map = {}
    top_risks = []
    score_total = 0

    for ci in items:
        attributes = ci.attributes or {}
        ci_issues = []
        if not ci.business_line or not ci.admin_user or not str(attributes.get('department') or '').strip():
            ci_issues.append('missing_ownership')
        if _relation_count_for_ci(ci) == 0:
            ci_issues.append('no_relation')
        if not (_source_rows_for_ci(ci) or any(attributes.get(key) for key in ['source_type', 'source', 'source_unique_id', 'external_id'])):
            ci_issues.append('no_source')
        if ci.id in open_completion_ci_ids:
            ci_issues.append('completion_issues')
        if ci.id in pending_archive_ci_ids:
            ci_issues.append('archive_candidates')
        if ci.id in failed_sync_ci_ids:
            ci_issues.append('sync_failures')

        deduction = sum(DATA_QUALITY_WEIGHTS.get(issue, 0) for issue in ci_issues)
        score = max(0, 100 - deduction)
        score_total += score
        if score < 60:
            status_counts['critical'] += 1
        elif score < 90:
            status_counts['warning'] += 1
        else:
            status_counts['healthy'] += 1

        type_name = normalize_ci_type_name(ci.ci_type.name if ci.ci_type_id else '')
        model_bucket = model_quality[(ci.ci_type_id, type_name)]
        model_bucket['ci_type'] = ci.ci_type_id
        model_bucket['ci_type_name'] = type_name
        model_bucket['score_total'] += score
        model_bucket['resource_count'] += 1
        if ci_issues:
            model_bucket['risk_count'] += 1
        for issue in ci_issues:
            issue_counts[issue] += 1
            model_bucket['issue_counts'][issue] += 1
        if ci_issues:
            top_risks.append({
                'ci_id': ci.id,
                'ci_name': ci.name,
                'ci_type': ci.ci_type_id,
                'ci_type_name': type_name,
                'score': score,
                'issues': [
                    {'key': issue, 'label': DATA_QUALITY_LABELS.get(issue, issue), 'weight': DATA_QUALITY_WEIGHTS.get(issue, 0)}
                    for issue in ci_issues[:4]
                ],
                'business_line': ci.business_line,
                'environment': ci.environment,
                'admin_user': ci.admin_user,
            })

    model_rows = []
    for bucket in model_quality.values():
        resource_count = bucket['resource_count'] or 1
        model_rows.append({
            'ci_type': bucket['ci_type'],
            'ci_type_name': bucket['ci_type_name'],
            'resource_count': bucket['resource_count'],
            'risk_count': bucket['risk_count'],
            'score': round(bucket['score_total'] / resource_count),
            'issue_counts': dict(bucket['issue_counts']),
        })
        model_quality_map[bucket['ci_type']] = model_rows[-1]

    return {
        'score': round(score_total / len(items)),
        'total': len(items),
        'healthy': status_counts['healthy'],
        'warning': status_counts['warning'],
        'critical': status_counts['critical'],
        'issue_counts': {key: issue_counts[key] for key in DATA_QUALITY_WEIGHTS},
        'top_risks': sorted(top_risks, key=lambda item: (item['score'], -len(item['issues']), item['ci_name']))[:8],
        'model_quality': sorted(model_rows, key=lambda item: (-item['risk_count'], item['score'], item['ci_type_name']))[:8],
        'model_quality_map': model_quality_map,
        'governance_workload': _governance_workload_summary(scoped_ci_ids, user=user),
    }


def _latest_capacity_metric_snapshots(scoped_ci_ids):
    metric_names = (
        CIResourceMetricSnapshot.objects.order_by().values_list('metric', flat=True).distinct()
    )
    return latest_metric_snapshots(
        scoped_ci_ids,
        metric_names,
        queryset=CIResourceMetricSnapshot.objects.filter(usage_percent__isnull=False).select_related('ci', 'ci__ci_type'),
    )


def _build_governance_risk_payload(scoped_items):
    """Build only the risk queues needed by the governance workbench."""
    scoped_ci_ids = scoped_items.values('id')
    scoped_id_set = set(scoped_items.values_list('id', flat=True))
    policy_lookup = _capacity_policy_lookup()
    capacity_request_lookup = _capacity_request_lookup(scoped_id_set)
    metric_status_counts = defaultdict(int)
    metric_items = []
    snapshots = _latest_capacity_metric_snapshots(scoped_ci_ids)
    for snapshot in snapshots.iterator(chunk_size=1000):
        key = (snapshot.ci_id, snapshot.metric)
        usage_percent = _to_float(snapshot.usage_percent)
        thresholds = _capacity_thresholds_for_metric(policy_lookup, snapshot.ci.ci_type_id, snapshot.metric)
        waterline_status = _capacity_waterline_status(usage_percent, thresholds)
        metric_status_counts[waterline_status] += 1
        ci = snapshot.ci
        attributes = ci.attributes or {}
        governance = _ci_governance_entry(ci, 'capacity', snapshot.metric)
        risk_fingerprint = f'capacity:{snapshot.metric}:{snapshot.collected_at.isoformat() if snapshot.collected_at else ""}:{usage_percent}'
        linked_request = capacity_request_lookup.get(key)
        if _governance_status_is_closed(governance, risk_fingerprint):
            governance_status = governance['status']
        elif linked_request and linked_request['status'] in {'pending', 'approved'}:
            governance_status = 'requesting'
        elif linked_request and linked_request['status'] == 'completed':
            completed_at = linked_request.get('completed_at')
            governance_status = 'recheck_failed' if completed_at and snapshot.collected_at and snapshot.collected_at > completed_at else 'completed'
        else:
            governance_status = 'open'
        metric_items.append({
            'ci_id': snapshot.ci_id,
            'ci_name': ci.name,
            'ci_type': ci.ci_type.name,
            'ci_type_name': ci.ci_type.name,
            'ci_type_id': ci.ci_type_id,
            'business_line': ci.business_line,
            'environment': ci.environment,
            'admin_user': ci.admin_user,
            'department': attributes.get('department') or '',
            'source_type': attributes.get('source_type') or attributes.get('source') or '',
            'instance_type': attributes.get('instance_type') or attributes.get('flavor') or '',
            'specification': attributes.get('specification') or attributes.get('instance_type') or '',
            'metric': snapshot.metric,
            'value': _to_float(snapshot.value),
            'unit': snapshot.unit,
            'usage_percent': usage_percent,
            'status': waterline_status,
            'source': snapshot.source,
            'thresholds': thresholds,
            'policy_id': thresholds.get('policy_id'),
            'policy_scope': thresholds.get('policy_scope'),
            'warning_threshold': thresholds.get('warning_threshold'),
            'critical_threshold': thresholds.get('critical_threshold'),
            'exceeded_threshold': thresholds.get('exceeded_threshold'),
            'linked_request': linked_request,
            'governance_status': governance_status,
            'governance_note': governance.get('note', ''),
            'risk_fingerprint': risk_fingerprint,
            'collected_at': snapshot.collected_at,
        })
    top_capacity_risks = sorted(
        [item for item in metric_items if item['status'] in {'warning', 'critical', 'exceeded'} and item['governance_status'] not in {'resolved', 'ignored'}],
        key=lambda item: item['usage_percent'],
        reverse=True,
    )[:100]
    third_party_type_ids = _third_party_service_type_ids()
    service_expiry_risks = []
    for ci in scoped_items.select_related('ci_type').only('id', 'name', 'ci_type__code', 'ci_type__name', 'attributes'):
        if ci.ci_type_id in third_party_type_ids:
            service_expiry_risks.extend(_third_party_expiry_risks_for_ci(ci))
        else:
            service_expiry_risks.extend(_asset_service_expiry_risks_for_ci(ci))
    service_expiry_risks.sort(key=lambda item: (item['days_left'], item['ci_id']))
    return {
        'capacity_waterline': {
            'normal': metric_status_counts['normal'],
            'warning': metric_status_counts['warning'],
            'critical': metric_status_counts['critical'],
            'exceeded': metric_status_counts['exceeded'],
            'requesting': len({item['linked_request']['id'] for item in top_capacity_risks if item.get('linked_request') and item['linked_request']['status'] in {'pending', 'approved'}}),
            'completed_requests': len({item['linked_request']['id'] for item in top_capacity_risks if item.get('linked_request') and item['governance_status'] == 'completed'}),
            'recheck_failed': len({item['linked_request']['id'] for item in top_capacity_risks if item.get('linked_request') and item['governance_status'] == 'recheck_failed'}),
            'top_risks': top_capacity_risks,
        },
        'service_expiry_risks': service_expiry_risks[:100],
        'risk_summary': {
            'service_expiry': len(service_expiry_risks),
            'capacity_risks': len(top_capacity_risks),
        },
        'generated_at': timezone.now(),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('cmdb.dashboard.view')])
def cmdb_governance_risks(request):
    cache_key = _cmdb_ledger_request_cache_key(request, 'governance-risks')
    force_refresh = _to_bool(request.query_params.get('refresh'))
    cached = cache.get(cache_key)
    if cached is not None and not force_refresh:
        return Response(cached)
    scoped_items = _exclude_internal_provider_summary_items(
        _apply_ci_authorization_scope(ConfigItem.objects.all(), request.user)
    )
    payload = _build_governance_risk_payload(scoped_items)
    if not force_refresh:
        cache.set(cache_key, payload, CMDB_DASHBOARD_CACHE_TTL)
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('cmdb.dashboard.view')])
def cmdb_dashboard(request):
    cache_key = _cmdb_ledger_request_cache_key(request, 'dashboard')
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)
    month = _current_month()
    scoped_items = _exclude_internal_provider_summary_items(
        _apply_ci_authorization_scope(ConfigItem.objects.all(), request.user)
    )
    scoped_ci_ids = scoped_items.values('id')
    ci_total = scoped_items.count()
    ci_active = scoped_items.filter(status='active').count()
    ci_by_type = list(scoped_items.values(type_name=F('ci_type__name'), color=F('ci_type__color')).annotate(count=Count('id')).order_by('-count'))
    for item in ci_by_type:
        item['color'] = item.get('color') or '#9c27b0'
    ci_by_env = list(scoped_items.values('environment').annotate(count=Count('id')).order_by('-count'))
    scoped_id_set = set(scoped_items.values_list('id', flat=True))
    cost_rows = [row for row in _cost_rows_for_month(month) if row['ci'].id in scoped_id_set]
    business_totals = defaultdict(lambda: {'count': 0, 'total_cost': Decimal('0')})
    for row in cost_rows:
        ci = row['ci']
        if not ci.business_line:
            continue
        business_totals[ci.business_line]['total_cost'] += row['amount']
    for business_line, count in (
        scoped_items.exclude(business_line='').values_list('business_line').annotate(count=Count('id'))
    ):
        business_totals[business_line]['count'] = count
    ci_by_biz = [
        {
            'business_line': business_line,
            'count': value['count'],
            'total_cost': _to_float(value['total_cost']),
        }
        for business_line, value in business_totals.items()
    ]
    ci_by_biz.sort(key=lambda item: (-item['total_cost'], item['business_line']))
    for item in ci_by_biz:
        item['total_cost'] = _to_float(item['total_cost'])
    total_monthly_cost = sum((row['amount'] for row in cost_rows), Decimal('0'))
    relation_count = CIRelation.objects.filter(Q(source_id__in=scoped_ci_ids) | Q(target_id__in=scoped_ci_ids)).count()
    pending_requests = ResourceRequest.objects.filter(status='pending').count()
    ci_by_status = list(scoped_items.values('status').annotate(count=Count('id')).order_by('-count'))

    source_distribution = defaultdict(int)
    for row in CISourceMapping.objects.filter(ci_id__in=scoped_ci_ids).values('source_type').annotate(count=Count('ci', distinct=True)):
        source_distribution[row['source_type'] or 'manual'] += row['count']
    mapped_ci_ids = set(CISourceMapping.objects.filter(ci_id__in=scoped_ci_ids).values_list('ci_id', flat=True))
    for ci in scoped_items.exclude(id__in=mapped_ci_ids).only('id', 'attributes'):
        source_distribution[(ci.attributes or {}).get('source_type') or (ci.attributes or {}).get('source') or 'manual'] += 1
    ci_by_source = [
        {'source_type': key, 'count': value}
        for key, value in sorted(source_distribution.items(), key=lambda item: (-item[1], item[0]))
    ]
    ci_by_tag = list(
        CITag.objects.filter(config_items__id__in=scoped_ci_ids)
        .values('id', 'name', 'category', 'color')
        .annotate(count=Count('config_items', distinct=True))
        .order_by('-count', 'category', 'name')[:12]
    )

    metric_status_counts = defaultdict(int)
    metric_items = []
    capacity_policy_lookup = _capacity_policy_lookup()
    capacity_request_lookup = _capacity_request_lookup(scoped_id_set)
    for snapshot in _latest_capacity_metric_snapshots(scoped_ci_ids):
        key = (snapshot.ci_id, snapshot.metric)
        usage_percent = _to_float(snapshot.usage_percent)
        thresholds = _capacity_thresholds_for_metric(
            capacity_policy_lookup,
            snapshot.ci.ci_type_id,
            snapshot.metric,
        )
        waterline_status = _capacity_waterline_status(usage_percent, thresholds)
        metric_status_counts[waterline_status] += 1
        ci = snapshot.ci
        ci_attributes = ci.attributes or {}
        governance = _ci_governance_entry(ci, 'capacity', snapshot.metric)
        risk_fingerprint = f'capacity:{snapshot.metric}:{snapshot.collected_at.isoformat() if snapshot.collected_at else ""}:{usage_percent}'
        linked_request = capacity_request_lookup.get((snapshot.ci_id, snapshot.metric))
        if _governance_status_is_closed(governance, risk_fingerprint):
            governance_status = governance['status']
        elif linked_request and linked_request['status'] in {'pending', 'approved'}:
            governance_status = 'requesting'
        elif linked_request and linked_request['status'] == 'completed':
            completed_at = linked_request.get('completed_at')
            governance_status = (
                'recheck_failed'
                if completed_at and snapshot.collected_at and snapshot.collected_at > completed_at
                else 'completed'
            )
        else:
            governance_status = 'open'
        metric_items.append({
            'ci_id': snapshot.ci_id,
            'ci_name': ci.name,
            'ci_type': ci.ci_type.name,
            'ci_type_name': ci.ci_type.name,
            'ci_type_id': ci.ci_type_id,
            'business_line': ci.business_line,
            'environment': ci.environment,
            'admin_user': ci.admin_user,
            'department': ci_attributes.get('department') or '',
            'source_type': ci_attributes.get('source_type') or ci_attributes.get('source') or '',
            'instance_type': ci_attributes.get('instance_type') or ci_attributes.get('flavor') or '',
            'specification': ci_attributes.get('specification') or ci_attributes.get('instance_type') or '',
            'metric': snapshot.metric,
            'value': _to_float(snapshot.value),
            'unit': snapshot.unit,
            'usage_percent': usage_percent,
            'status': waterline_status,
            'source': snapshot.source,
            'thresholds': thresholds,
            'policy_id': thresholds.get('policy_id'),
            'policy_scope': thresholds.get('policy_scope'),
            'warning_threshold': thresholds.get('warning_threshold'),
            'critical_threshold': thresholds.get('critical_threshold'),
            'exceeded_threshold': thresholds.get('exceeded_threshold'),
            'linked_request': linked_request,
            'governance_status': governance_status,
            'governance_note': governance.get('note', ''),
            'risk_fingerprint': risk_fingerprint,
            'collected_at': snapshot.collected_at,
        })
    top_capacity_risks = sorted(
        [item for item in metric_items if item['status'] in {'warning', 'critical', 'exceeded'} and item.get('governance_status') not in {'resolved', 'ignored'}],
        key=lambda item: item['usage_percent'],
        reverse=True,
    )[:8]
    open_capacity_request_ids = {
        item['linked_request']['id']
        for item in top_capacity_risks
        if item.get('linked_request') and item['linked_request']['status'] in {'pending', 'approved'}
    }
    completed_capacity_request_ids = {
        item['linked_request']['id']
        for item in top_capacity_risks
        if item.get('linked_request') and item['governance_status'] == 'completed'
    }
    recheck_failed_capacity_request_ids = {
        item['linked_request']['id']
        for item in top_capacity_risks
        if item.get('linked_request') and item['governance_status'] == 'recheck_failed'
    }
    capacity_waterline = {
        'normal': metric_status_counts['normal'],
        'warning': metric_status_counts['warning'],
        'critical': metric_status_counts['critical'],
        'exceeded': metric_status_counts['exceeded'],
        'requesting': len(open_capacity_request_ids),
        'completed_requests': len(completed_capacity_request_ids),
        'recheck_failed': len(recheck_failed_capacity_request_ids),
        'top_risks': top_capacity_risks,
    }

    missing_owner_count = sum(
        1
        for ci in scoped_items.only('id', 'business_line', 'admin_user', 'attributes')
        if not (ci.business_line or '').strip()
        or not (ci.admin_user or '').strip()
        or not str((ci.attributes or {}).get('department') or '').strip()
    )
    open_completion_count = CICompletionIssue.objects.exclude(status__in=['resolved', 'ignored']).filter(ci_id__in=scoped_ci_ids).count()
    pending_archive_count = CIArchiveCandidate.objects.filter(status='pending', ci_id__in=scoped_ci_ids).count()
    failed_sync_count = _sync_governance_record_queryset_for_user(request.user, include_global=False).count()
    data_quality = _build_data_quality_summary(scoped_items, scoped_ci_ids, user=request.user)
    third_party_expiry_suggestions = []
    third_party_type_ids = _third_party_service_type_ids()
    if third_party_type_ids:
        for ci in scoped_items.filter(ci_type_id__in=third_party_type_ids).select_related('ci_type'):
            third_party_expiry_suggestions.extend(_third_party_expiry_risks_for_ci(ci))
    asset_service_expiry_suggestions = []
    for ci in scoped_items.exclude(ci_type_id__in=third_party_type_ids).select_related('ci_type'):
        asset_service_expiry_suggestions.extend(_asset_service_expiry_risks_for_ci(ci))
    service_expiry_suggestions = third_party_expiry_suggestions + asset_service_expiry_suggestions
    risk_summary = {
        'missing_owner': missing_owner_count,
        'completion_issues': open_completion_count,
        'archive_candidates': pending_archive_count,
        'sync_failures': failed_sync_count,
        'pending_requests': pending_requests,
        'service_expiry': len(service_expiry_suggestions),
        'capacity_requests': capacity_waterline['requesting'],
        'capacity_recheck_failed': capacity_waterline['recheck_failed'],
    }
    application_suggestions = []
    for item in capacity_waterline['top_risks'][:5]:
        application_suggestions.append({
            'type': 'capacity',
            'severity': item['status'],
            'title': f"{item['ci_name']} {item['metric']} 水位 {item['usage_percent']}%",
            'action': '建议评估扩容、清理或发起资源申请。',
            'ci_id': item['ci_id'],
            'ci_name': item['ci_name'],
            'ci_type': item['ci_type'],
            'ci_type_name': item['ci_type_name'],
            'ci_type_id': item['ci_type_id'],
            'business_line': item['business_line'],
            'environment': item['environment'],
            'admin_user': item['admin_user'],
            'metric': item['metric'],
            'usage_percent': item['usage_percent'],
            'thresholds': item['thresholds'],
            'policy_id': item['policy_id'],
            'policy_scope': item['policy_scope'],
            'warning_threshold': item['warning_threshold'],
            'critical_threshold': item['critical_threshold'],
            'exceeded_threshold': item['exceeded_threshold'],
            'source': item['source'],
            'linked_request': item['linked_request'],
            'governance_status': item['governance_status'],
            'collected_at': item['collected_at'],
        })
    if missing_owner_count:
        application_suggestions.append({
            'type': 'governance',
            'severity': 'warning',
            'title': f'{missing_owner_count} 个资源缺少业务线、部门或负责人',
            'action': '建议进入待补全资源列表批量补齐归属信息。',
        })
    if data_quality['score'] < 90:
        application_suggestions.append({
            'type': 'data_quality',
            'severity': 'critical' if data_quality['score'] < 60 else 'warning',
            'title': f"CMDB 数据质量评分 {data_quality['score']}，{data_quality['critical']} 个资源高风险",
            'action': '建议优先处理归属、来源、关系断点和同步失败问题。',
        })
    if pending_archive_count:
        application_suggestions.append({
            'type': 'archive',
            'severity': 'info',
            'title': f'{pending_archive_count} 个资源待下线确认',
            'action': '建议确认来源端状态后归档或恢复资源。',
        })
    application_suggestions.extend(sorted(
        service_expiry_suggestions,
        key=lambda item: (item['days_left'], item['ci_id']),
    )[:5])
    phase_one_coverage = _build_phase_one_coverage(scoped_items, scoped_ci_ids, metric_items)

    payload = {
        'ci_total': ci_total,
        'ci_active': ci_active,
        'ci_by_type': ci_by_type,
        'ci_by_env': ci_by_env,
        'ci_by_status': ci_by_status,
        'ci_by_source': ci_by_source,
        'ci_by_tag': ci_by_tag,
        'ci_by_business': ci_by_biz,
        'total_monthly_cost': _to_float(total_monthly_cost),
        'relation_count': relation_count,
        'pending_requests': pending_requests,
        'capacity_waterline': capacity_waterline,
        'phase_one_coverage': phase_one_coverage,
        'data_quality': data_quality,
        'risk_summary': risk_summary,
        'service_expiry_risks': sorted(
            service_expiry_suggestions,
            key=lambda item: (item['days_left'], item['ci_id']),
        )[:100],
        'application_suggestions': application_suggestions[:8],
    }
    cache.set(cache_key, payload, CMDB_DASHBOARD_CACHE_TTL)
    return Response(payload)

@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('cmdb.topology.view')])
def cmdb_topology(request):
    ci_type_id = request.query_params.get('ci_type')
    ci_id = request.query_params.get('ci_id')
    business_line = request.query_params.get('business_line')
    environment = request.query_params.get('environment')
    scope = request.query_params.get('scope', 'neighbors')
    include_neighbors = scope != 'exact'
    neighbor_hops = _positive_int(request.query_params.get('neighbor_hops'), 1, 3)
    if not include_neighbors:
        neighbor_hops = 0

    filtered_qs = _apply_ci_authorization_scope(ConfigItem.objects.select_related('ci_type').all(), request.user)
    if ci_type_id:
        filtered_qs = filtered_qs.filter(ci_type_id=ci_type_id)
    if business_line:
        filtered_qs = filtered_qs.filter(business_line=business_line)
    if environment:
        filtered_qs = filtered_qs.filter(environment=environment)
    if ci_id:
        filtered_qs = filtered_qs.filter(id=ci_id)

    matched_ids = set(filtered_qs.values_list('id', flat=True))
    node_ids = set(matched_ids)
    authorized_ids = set(
        _apply_ci_authorization_scope(ConfigItem.objects.all(), request.user).values_list('id', flat=True)
    )
    relations = CIRelation.objects.none()
    if matched_ids and include_neighbors:
        frontier_ids = set(matched_ids)
        for _ in range(neighbor_hops):
            if not frontier_ids:
                break
            frontier_relations = CIRelation.objects.filter(
                Q(source_id__in=frontier_ids) | Q(target_id__in=frontier_ids)
            ).values_list('source_id', 'target_id')
            next_frontier_ids = set()
            for source_id, target_id in frontier_relations:
                if source_id in authorized_ids and source_id not in node_ids:
                    next_frontier_ids.add(source_id)
                if target_id in authorized_ids and target_id not in node_ids:
                    next_frontier_ids.add(target_id)
            node_ids.update(next_frontier_ids)
            frontier_ids = next_frontier_ids

    node_qs = ConfigItem.objects.select_related('ci_type').filter(id__in=node_ids).order_by(
        'business_line',
        'environment',
        'ci_type__name',
        'name',
    )
    nodes = []
    for ci in node_qs:
        attributes = ci.attributes or {}
        nodes.append({
            'id': ci.id,
            'name': ci.name,
            'type': ci.ci_type.name,
            'icon': ci.ci_type.icon,
            'color': ci.ci_type.color or '#9c27b0',
            'status': ci.status,
            'ip': attributes.get('ip_address') or attributes.get('ip', ''),
            'env': ci.environment,
            'business_line': ci.business_line,
            'admin_user': ci.admin_user,
            'monthly_cost': _to_float(attributes.get('monthly_cost')),
            'instance_type': attributes.get('instance_type', ''),
            'cloud_provider': attributes.get('cloud_provider', ''),
            'region': attributes.get('region', ''),
            'cpu': attributes.get('cpu'),
            'memory_gb': attributes.get('memory_gb'),
            'disk_gb': attributes.get('disk_gb'),
            'description': attributes.get('description', ''),
            'is_match': ci.id in matched_ids,
        })

    filtered_edges = []
    if node_ids:
        if not matched_ids:
            relations = CIRelation.objects.none()
        elif not include_neighbors:
            relations = CIRelation.objects.filter(
                source_id__in=node_ids,
                target_id__in=node_ids,
            ).select_related('source', 'target')
        else:
            relations = CIRelation.objects.filter(
                source_id__in=node_ids,
                target_id__in=node_ids,
            ).select_related('source', 'target')
        for relation in relations:
            if relation.source_id in node_ids and relation.target_id in node_ids:
                filtered_edges.append({
                    'id': relation.id,
                    'source': relation.source_id,
                    'target': relation.target_id,
                    'source_name': relation.source.name,
                    'target_name': relation.target.name,
                    'type': relation.relation_type,
                    'label': relation.get_relation_type_display(),
                    'description': relation.description,
                    'evidence_source': relation.evidence_source,
                    'evidence_source_display': relation.get_evidence_source_display(),
                    'confidence': relation.confidence,
                    'evidence': relation.evidence or {},
                    'is_match': relation.source_id in matched_ids and relation.target_id in matched_ids,
                })

    return Response({
        'nodes': nodes,
        'edges': filtered_edges,
        'meta': {
            'scope': 'neighbors' if include_neighbors else 'exact',
            'neighbor_hops': neighbor_hops,
            'matched_node_ids': sorted(matched_ids),
            'node_count': len(nodes),
            'edge_count': len(filtered_edges),
        },
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('cmdb.cost.view')])
def cmdb_cost_report(request):
    month = _normalize_month(request.query_params.get('month'))
    scoped_ci_qs = _apply_ci_authorization_scope(ConfigItem.objects.all(), request.user)
    return Response(_build_cost_report(
        month,
        ci_queryset=scoped_ci_qs,
        source_account=request.query_params.get('source_account'),
        business_line=request.query_params.get('business_line'),
        environment=request.query_params.get('environment'),
    ))


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('cmdb.cost.view')])
def cmdb_cost_items(request):
    """Return one aggregated monthly cost row per authorized CMDB asset."""
    month = _normalize_month(request.query_params.get('month'))
    scoped_ci_qs = _apply_ci_authorization_scope(ConfigItem.objects.all(), request.user)
    ci_type = request.query_params.get('ci_type')
    if ci_type:
        scoped_ci_qs = scoped_ci_qs.filter(ci_type_id=ci_type)

    search = (request.query_params.get('search') or '').strip().lower()
    business_line = (request.query_params.get('business_line') or '').strip()
    environment = (request.query_params.get('environment') or '').strip()
    provider = (request.query_params.get('provider') or '').strip()
    source_account = (request.query_params.get('source_account') or '').strip()
    source_region = (request.query_params.get('source_region') or '').strip()
    rows = []
    for row in _cost_rows_for_month(month, ci_queryset=scoped_ci_qs):
        ci = row['ci']
        row_provider = _normalize_provider(row['provider'])
        if business_line and ci.business_line != business_line:
            continue
        if environment and ci.environment != environment:
            continue
        if provider and row_provider != provider:
            continue
        if source_account and _cost_source_account(ci) != source_account:
            continue
        if source_region and _cost_source_region(ci) != source_region:
            continue
        if search and search not in ci.name.lower():
            continue
        rows.append(row)

    rows.sort(key=lambda item: (-item['amount'], item['ci'].name))
    page = _positive_int(request.query_params.get('page'), 1, 100000)
    page_size = _positive_int(request.query_params.get('page_size'), 20, 100)
    start = (page - 1) * page_size
    return Response({
        'month': month,
        'count': len(rows),
        'page': page,
        'page_size': page_size,
        'results': [_cost_item_payload(row) for row in rows[start:start + page_size]],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, build_rbac_permission('cmdb.cost.manage')])
def cmdb_sync_aliyun_cost(request):
    month = request.data.get('month') or _current_month()
    scoped_ci_qs = _apply_ci_authorization_scope(
        ConfigItem.objects.all(),
        request.user,
        permission='manage',
    )
    try:
        result = sync_aliyun_monthly_costs(
            month=month,
            credential_id=request.data.get('credential_id'),
            ci_queryset=scoped_ci_qs,
            history_months=request.data.get('history_months', 12),
        )
    except AliyunCostSyncError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    failed = result['failed_count'] > 0
    record_event(
        request=request,
        module='cmdb',
        category='sync',
        action='sync_aliyun_cost',
        title='同步阿里云账单成本',
        summary=(
            f"已更新 {result['updated_count']} 项按量成本、"
            f"均摊 {result['subscription_updated_count']} 项订阅成本"
            f"，未匹配 {result['unmatched_bill_count']} 条账单"
        ),
        result=EventRecord.RESULT_FAILED if failed and not result['updated_count'] else EventRecord.RESULT_SUCCESS,
        severity=EventRecord.SEVERITY_WARNING if failed else EventRecord.SEVERITY_INFO,
        resource_type='cmdb_cost_sync',
        resource_id=f"aliyun:{result['month']}",
        resource_name='阿里云成本同步',
        correlation_id=f"cmdb-cost-sync:aliyun:{result['month']}",
        metadata={
            'provider': 'aliyun',
            'month': result['month'],
            'account_count': result['account_count'],
            'updated_count': result['updated_count'],
            'subscription_updated_count': result['subscription_updated_count'],
            'unmatched_bill_count': result['unmatched_bill_count'],
            'failed_count': result['failed_count'],
        },
    )
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('cmdb.cost.view')])
def cmdb_optimization(request):
    month = _normalize_month(request.query_params.get('month'))
    scoped_ci_qs = _apply_ci_authorization_scope(ConfigItem.objects.all(), request.user)
    return Response(_build_optimization(month, ci_queryset=scoped_ci_qs))
