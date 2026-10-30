import calendar
import importlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from .models import ConfigItem, CostRecord


ALIYUN_SOURCE_PREFIX = 'aliyun_'
ALIYUN_COST_PROVIDER = 'aliyun'
ALIYUN_SUBSCRIPTION_COST_PROVIDER = 'aliyun_subscription'
RESOURCE_ID_ATTRIBUTE_KEYS = (
    'resource_id',
    'instance_id',
    'source_unique_id',
    'allocation_id',
    'volume_id',
    'bucket',
    'cluster_id',
    'filesystem_id',
    'project_name',
    'workspace_id',
)
ACCOUNT_ATTRIBUTE_KEYS = (
    'source_account',
    'cloud_account',
    'account',
    'account_id',
    'account_name',
)


class AliyunCostSyncError(ValueError):
    pass


def _decimal(value):
    try:
        return Decimal(str(value if value not in (None, '') else '0'))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


def _normalize_month(month, today=None):
    value = str(month or '').strip()
    if len(value) != 7 or value[4] != '-':
        raise AliyunCostSyncError('month must use YYYY-MM format')
    try:
        year, month_number = (int(part) for part in value.split('-', 1))
        date(year, month_number, 1)
    except (TypeError, ValueError):
        raise AliyunCostSyncError('month must use YYYY-MM format') from None
    return value


def _credential_account_candidates(credential):
    return {
        str(value).strip()
        for value in (
            credential.id,
            credential.account_id,
            credential.account_name,
            credential.name,
        )
        if str(value or '').strip()
    }


def _ci_is_aliyun(ci):
    attributes = ci.attributes or {}
    values = (
        attributes.get('provider'),
        attributes.get('cloud_provider'),
        attributes.get('billing_provider'),
        attributes.get('source_type'),
        attributes.get('source'),
    )
    if any(str(value or '').strip().lower().startswith('aliyun') for value in values):
        return True
    return any(
        str(mapping.source_type or '').strip().lower().startswith(ALIYUN_SOURCE_PREFIX)
        for mapping in ci.source_mappings.all()
    )


def _ci_belongs_to_credential(ci, account_candidates):
    attributes = ci.attributes or {}
    values = {str(attributes.get(key) or '').strip() for key in ACCOUNT_ATTRIBUTE_KEYS}
    values.update(str(mapping.source_account or '').strip() for mapping in ci.source_mappings.all())
    values.discard('')
    return bool(values & account_candidates)


def _ci_resource_ids(ci):
    attributes = ci.attributes or {}
    values = {str(attributes.get(key) or '').strip() for key in RESOURCE_ID_ATTRIBUTE_KEYS}
    values.update(str(mapping.source_unique_id or '').strip() for mapping in ci.source_mappings.all())
    return {value for value in values if value}


def _aliyun_cis_for_credential(credential, ci_queryset=None):
    queryset = ci_queryset if ci_queryset is not None else ConfigItem.objects.all()
    candidates = _credential_account_candidates(credential)
    ci_by_resource_id = {}
    for ci in queryset.prefetch_related('source_mappings'):
        if not _ci_is_aliyun(ci) or not _ci_belongs_to_credential(ci, candidates):
            continue
        for resource_id in _ci_resource_ids(ci):
            ci_by_resource_id.setdefault(resource_id, []).append(ci)
    return ci_by_resource_id


def _bill_items(payload):
    data = payload.get('Data') or {}
    items = (data.get('Items') or {}).get('Item') or []
    return items if isinstance(items, list) else [items]


def _fetch_aliyun_instance_bill_items(credential, month):
    try:
        client_module = importlib.import_module('aliyunsdkcore.client')
        request_module = importlib.import_module(
            'aliyunsdkbssopenapi.request.v20171214.QueryInstanceBillRequest'
        )
    except ImportError as exc:
        raise AliyunCostSyncError(
            'Aliyun billing SDK is unavailable. Install aliyun-python-sdk-bssopenapi.'
        ) from exc

    client = client_module.AcsClient(
        credential.access_key_id,
        credential.access_key_secret,
        credential.default_region or 'cn-hangzhou',
    )
    page_number = 1
    page_size = 300
    rows = []
    while True:
        request = request_module.QueryInstanceBillRequest()
        request.set_accept_format('json')
        request.set_BillingCycle(month)
        request.set_Granularity('MONTHLY')
        request.set_PageNum(page_number)
        request.set_PageSize(page_size)
        try:
            payload = json.loads(client.do_action_with_exception(request))
        except Exception as exc:
            raise AliyunCostSyncError(f'Aliyun billing request failed: {exc}') from exc
        page_rows = _bill_items(payload)
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        page_number += 1
    return rows


def _aliyun_client(credential):
    try:
        client_module = importlib.import_module('aliyunsdkcore.client')
    except ImportError as exc:
        raise AliyunCostSyncError(
            'Aliyun billing SDK is unavailable. Install aliyun-python-sdk-bssopenapi.'
        ) from exc
    return client_module.AcsClient(
        credential.access_key_id,
        credential.access_key_secret,
        credential.default_region or 'cn-hangzhou',
    )


def _fetch_aliyun_subscription_orders(credential, start_date, end_date):
    """Return subscription orders for all Aliyun products in the supplied time window."""
    try:
        request_module = importlib.import_module(
            'aliyunsdkbssopenapi.request.v20171214.QueryOrdersRequest'
        )
    except ImportError as exc:
        raise AliyunCostSyncError(
            'Aliyun billing SDK is unavailable. Install aliyun-python-sdk-bssopenapi.'
        ) from exc

    client = _aliyun_client(credential)
    page_number = 1
    page_size = 100
    orders = []
    while True:
        request = request_module.QueryOrdersRequest()
        request.set_accept_format('json')
        request.set_SubscriptionType('Subscription')
        request.set_PaymentStatus('PaymentCompleted')
        request.set_CreateTimeStart(f'{start_date.isoformat()}T00:00:00Z')
        request.set_CreateTimeEnd(f'{end_date.isoformat()}T00:00:00Z')
        request.set_PageNum(page_number)
        request.set_PageSize(page_size)
        try:
            payload = json.loads(client.do_action_with_exception(request))
        except Exception as exc:
            raise AliyunCostSyncError(f'Aliyun subscription order request failed: {exc}') from exc
        data = payload.get('Data') or {}
        page_orders = ((data.get('OrderList') or {}).get('Order') or [])
        if not isinstance(page_orders, list):
            page_orders = [page_orders]
        orders.extend(page_orders)
        if len(page_orders) < page_size:
            break
        page_number += 1
    return orders


def _fetch_aliyun_order_details(credential, order_id):
    try:
        request_module = importlib.import_module(
            'aliyunsdkbssopenapi.request.v20171214.GetOrderDetailRequest'
        )
    except ImportError as exc:
        raise AliyunCostSyncError(
            'Aliyun billing SDK is unavailable. Install aliyun-python-sdk-bssopenapi.'
        ) from exc

    request = request_module.GetOrderDetailRequest()
    request.set_accept_format('json')
    request.set_OrderId(str(order_id))
    try:
        payload = json.loads(_aliyun_client(credential).do_action_with_exception(request))
    except Exception as exc:
        raise AliyunCostSyncError(f'Aliyun order detail request failed: {exc}') from exc
    orders = (((payload.get('Data') or {}).get('OrderList') or {}).get('Order') or [])
    return orders if isinstance(orders, list) else [orders]


def _bill_resource_id(row):
    return str(
        row.get('InstanceID')
        or row.get('InstanceId')
        or row.get('ResourceId')
        or row.get('ResourceID')
        or ''
    ).strip()


def _bill_amount(row):
    for field in ('PretaxAmount', 'PretaxGrossAmount', 'PayableAmount', 'CashAmount'):
        if row.get(field) not in (None, ''):
            return _decimal(row.get(field))
    return Decimal('0')


def _is_subscription_item(row):
    return str(row.get('SubscriptionType') or '').strip().lower() == 'subscription'


def _is_paid_product_sub_order(order):
    if str(order.get('OrderSubType') or '').strip() != 'ProductSubOrder':
        return False
    payment_status = str(order.get('PaymentStatus') or '').strip().lower()
    return payment_status in {'paid', 'paymentcompleted'} or bool(order.get('PaymentTime'))


def _month_shift(month, offset):
    year, month_number = (int(part) for part in month.split('-', 1))
    absolute_month = year * 12 + month_number - 1 + offset
    return f'{absolute_month // 12:04d}-{absolute_month % 12 + 1:02d}'


def _months_in_service_period(start_value, end_value):
    try:
        start = date.fromisoformat(str(start_value)[:10])
        end = date.fromisoformat(str(end_value)[:10])
    except (TypeError, ValueError):
        return []
    count = max(1, (end.year - start.year) * 12 + end.month - start.month)
    return [_month_shift(start.strftime('%Y-%m'), index) for index in range(count)]


def _order_resource_ids(order):
    resource_id_keys = (
        'InstanceIDs', 'InstanceIds', 'InstanceID', 'InstanceId',
        'ResourceIDs', 'ResourceIds', 'ResourceID', 'ResourceId',
        'DBInstanceIDs', 'DBInstanceIds', 'DBInstanceID', 'DBInstanceId',
        'DiskIDs', 'DiskIds', 'DiskID', 'DiskId',
        'VolumeIDs', 'VolumeIds', 'VolumeID', 'VolumeId',
        'AllocationIDs', 'AllocationIds', 'AllocationID', 'AllocationId',
        'NatGatewayIDs', 'NatGatewayIds', 'NatGatewayID', 'NatGatewayId',
        'BucketNames', 'BucketName', 'Bucket',
        'ClusterIDs', 'ClusterIds', 'ClusterID', 'ClusterId',
        'LoadBalancerIDs', 'LoadBalancerIds', 'LoadBalancerID', 'LoadBalancerId',
        'FileSystemIDs', 'FileSystemIds', 'FileSystemID', 'FileSystemId',
        'ProjectNames', 'ProjectName', 'WorkspaceID', 'WorkspaceId',
    )
    values = []
    for key in resource_id_keys:
        value = order.get(key)
        if value in (None, ''):
            continue
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = [value]
        if isinstance(value, dict):
            value = value.values()
        if not isinstance(value, (list, tuple, set)):
            value = [value]
        values.extend(str(item).strip() for item in value if str(item or '').strip())
    return list(dict.fromkeys(values))


def _allocate_evenly(amount, count):
    if count <= 0:
        return []
    cents = (amount * Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    base = (cents / count).quantize(Decimal('1'), rounding=ROUND_DOWN)
    remainder = int(cents - base * count)
    return [
        (base + (Decimal('1') if index < remainder else Decimal('0'))) / Decimal('100')
        for index in range(count)
    ]


def _project_monthly_cost(amount, month, today):
    if month != today.strftime('%Y-%m'):
        return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), False
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    projected = amount * Decimal(days_in_month) / Decimal(today.day)
    return projected.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), True


def _replace_aliyun_cost_record(ci, month, amount):
    return _replace_cost_record(ci, month, amount, ALIYUN_COST_PROVIDER)


def _replace_cost_record(ci, month, amount, provider):
    records = list(
        CostRecord.objects.filter(ci=ci, month=month, provider=provider).order_by('id')
    )
    if records:
        record = records[0]
        record.amount = amount
        record.save(update_fields=['amount'])
        if len(records) > 1:
            CostRecord.objects.filter(id__in=[item.id for item in records[1:]]).delete()
        return record
    return CostRecord.objects.create(
        ci=ci,
        month=month,
        amount=amount,
        provider=provider,
    )


def _refresh_current_monthly_cost(ci, month):
    components = {
        provider: Decimal('0')
        for provider in (ALIYUN_COST_PROVIDER, ALIYUN_SUBSCRIPTION_COST_PROVIDER)
    }
    for record in CostRecord.objects.filter(ci=ci, month=month, provider__in=components):
        components[record.provider] += record.amount or Decimal('0')
    total = sum(components.values(), Decimal('0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    attributes = dict(ci.attributes or {})
    attributes.update({
        'monthly_cost': float(total),
        'cost_provider': ALIYUN_COST_PROVIDER,
        'cost_subscription_amortized_amount': float(components[ALIYUN_SUBSCRIPTION_COST_PROVIDER]),
    })
    ci.attributes = attributes
    ci.save(update_fields=['attributes', 'updated_at'])


def _subscription_costs_for_orders(
    credential, orders, ci_by_resource_id, history_start_month, end_month
):
    costs = {}
    order_count = 0
    errors = []
    processed_sub_order_ids = set()
    for order in orders:
        order_id = order.get('OrderId') or order.get('OrderID')
        if not order_id:
            continue
        try:
            detail_orders = _fetch_aliyun_order_details(credential, order_id)
        except AliyunCostSyncError as exc:
            errors.append(str(exc))
            continue
        for detail in detail_orders:
            sub_order_id = str(detail.get('SubOrderId') or detail.get('OrderId') or '').strip()
            if (
                not _is_subscription_item(detail)
                or not _is_paid_product_sub_order(detail)
                or not sub_order_id
                or sub_order_id in processed_sub_order_ids
            ):
                continue
            processed_sub_order_ids.add(sub_order_id)
            resource_ids = _order_resource_ids(detail)
            service_months = [
                item for item in _months_in_service_period(
                    detail.get('UsageStartTime'),
                    detail.get('UsageEndTime'),
                ) if history_start_month <= item <= end_month
            ]
            if not resource_ids or not service_months:
                continue
            order_count += 1
            allocations = _allocate_evenly(
                _bill_amount(detail),
                len(resource_ids) * len(service_months),
            )
            allocation_index = 0
            for resource_id in resource_ids:
                for service_month in service_months:
                    for ci in ci_by_resource_id.get(resource_id, []):
                        key = (ci.id, service_month)
                        costs[key] = costs.get(key, Decimal('0')) + allocations[allocation_index]
                    allocation_index += 1
    return costs, order_count, errors


def sync_aliyun_monthly_costs(
    *, month, credential_id=None, ci_queryset=None, today=None, history_months=12
):
    """Fetch Aliyun usage bills and amortize paid subscription orders into CMDB costs."""
    from multicloud.models import CloudCredential

    month = _normalize_month(month)
    today = today or timezone.localdate()
    try:
        history_months = int(history_months)
    except (TypeError, ValueError):
        raise AliyunCostSyncError('history_months must be an integer') from None
    if not 1 <= history_months <= 36:
        raise AliyunCostSyncError('history_months must be between 1 and 36')
    history_start_month = _month_shift(month, -(history_months - 1))
    order_lookup_start = date(*map(int, _month_shift(history_start_month, -3).split('-')), 1)
    order_lookup_end = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    credentials = CloudCredential.objects.filter(provider='aliyun', is_enabled=True).order_by('id')
    if credential_id not in (None, ''):
        credentials = credentials.filter(id=credential_id)

    summary = {
        'month': month,
        'projection': month == today.strftime('%Y-%m'),
        'accounts': [],
        'account_count': 0,
        'updated_count': 0,
        'subscription_updated_count': 0,
        'subscription_order_count': 0,
        'unmatched_bill_count': 0,
        'failed_count': 0,
        'total_monthly_cost': Decimal('0'),
    }
    for credential in credentials:
        account_result = {
            'credential_id': credential.id,
            'credential_name': credential.name,
            'updated_count': 0,
            'subscription_updated_count': 0,
            'subscription_order_count': 0,
            'unmatched_bill_count': 0,
            'failed': False,
        }
        summary['account_count'] += 1
        if credential.demo_mode or str(credential.auth_mode or '').strip().lower() == 'demo':
            account_result.update({'failed': True, 'error': 'Demo credentials cannot retrieve billing data.'})
            summary['failed_count'] += 1
            summary['accounts'].append(account_result)
            continue
        if not credential.access_key_id or not credential.access_key_secret:
            account_result.update({'failed': True, 'error': 'Access Key ID and Secret are required.'})
            summary['failed_count'] += 1
            summary['accounts'].append(account_result)
            continue

        try:
            bill_rows = _fetch_aliyun_instance_bill_items(credential, month)
        except AliyunCostSyncError as exc:
            account_result.update({'failed': True, 'error': str(exc)})
            summary['failed_count'] += 1
            summary['accounts'].append(account_result)
            continue

        try:
            subscription_orders = _fetch_aliyun_subscription_orders(
                credential,
                order_lookup_start,
                order_lookup_end,
            )
        except AliyunCostSyncError as exc:
            subscription_orders = []
            account_result['subscription_error'] = str(exc)

        ci_by_resource_id = _aliyun_cis_for_credential(credential, ci_queryset=ci_queryset)
        ci_by_id = {
            ci.id: ci
            for matched_cis in ci_by_resource_id.values()
            for ci in matched_cis
        }
        billed_by_resource = {}
        currency_by_resource = {}
        subscription_bill_resource_ids = set()
        for row in bill_rows:
            # Prepaid subscription costs are calculated from the paid order below.
            if _is_subscription_item(row):
                subscription_bill_resource_ids.add(_bill_resource_id(row))
                continue
            resource_id = _bill_resource_id(row)
            if not resource_id:
                continue
            billed_by_resource[resource_id] = billed_by_resource.get(resource_id, Decimal('0')) + _bill_amount(row)
            currency_by_resource[resource_id] = str(row.get('Currency') or 'CNY').strip() or 'CNY'

        account_result['bill_item_count'] = len(bill_rows)
        account_result['matched_resource_count'] = 0
        subscription_costs, subscription_order_count, subscription_errors = _subscription_costs_for_orders(
            credential,
            subscription_orders,
            ci_by_resource_id,
            history_start_month,
            month,
        )
        account_result['subscription_order_count'] = subscription_order_count
        summary['subscription_order_count'] += subscription_order_count
        if subscription_errors:
            account_result['subscription_errors'] = subscription_errors
        with transaction.atomic():
            current_affected_ci_ids = set()
            for resource_id in subscription_bill_resource_ids - set(billed_by_resource):
                for ci in ci_by_resource_id.get(resource_id, []):
                    CostRecord.objects.filter(
                        ci=ci,
                        month=month,
                        provider=ALIYUN_COST_PROVIDER,
                    ).delete()
                    current_affected_ci_ids.add(ci.id)
            for resource_id, amount in billed_by_resource.items():
                matched_cis = ci_by_resource_id.get(resource_id, [])
                if not matched_cis:
                    account_result['unmatched_bill_count'] += 1
                    summary['unmatched_bill_count'] += 1
                    continue
                projected_amount, projected = _project_monthly_cost(amount, month, today)
                for ci in matched_cis:
                    if month == today.strftime('%Y-%m'):
                        attributes = dict(ci.attributes or {})
                        attributes.update({
                            'monthly_cost': float(projected_amount),
                            'cost_provider': ALIYUN_COST_PROVIDER,
                            'cost_currency': currency_by_resource.get(resource_id, 'CNY'),
                            'cost_actual_amount': float(amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
                            'cost_billing_cycle': month,
                            'cost_is_projected': projected,
                            'cost_projection_days': today.day if projected else calendar.monthrange(*map(int, month.split('-')))[1],
                            'cost_last_synced_at': timezone.now().isoformat(),
                        })
                        ci.attributes = attributes
                        ci.save(update_fields=['attributes', 'updated_at'])
                    _replace_aliyun_cost_record(ci, month, projected_amount)
                    current_affected_ci_ids.add(ci.id)
                    account_result['updated_count'] += 1
                    summary['updated_count'] += 1
                    summary['total_monthly_cost'] += projected_amount
                account_result['matched_resource_count'] += 1

            # This provider is fully derived from the fetched order detail set.
            # Replace its in-scope history so cancelled or unpaid draft orders cannot linger.
            current_affected_ci_ids.update(
                CostRecord.objects.filter(
                    ci_id__in=ci_by_id,
                    month=month,
                    provider=ALIYUN_SUBSCRIPTION_COST_PROVIDER,
                ).values_list('ci_id', flat=True)
            )
            CostRecord.objects.filter(
                ci_id__in=ci_by_id,
                month__gte=history_start_month,
                month__lte=month,
                provider=ALIYUN_SUBSCRIPTION_COST_PROVIDER,
            ).delete()
            for (ci_id, service_month), amount in subscription_costs.items():
                ci = ci_by_id[ci_id]
                amortized_amount = amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                _replace_cost_record(
                    ci,
                    service_month,
                    amortized_amount,
                    ALIYUN_SUBSCRIPTION_COST_PROVIDER,
                )
                account_result['subscription_updated_count'] += 1
                summary['subscription_updated_count'] += 1
                if service_month == month:
                    current_affected_ci_ids.add(ci.id)
                    summary['total_monthly_cost'] += amortized_amount

            if month == today.strftime('%Y-%m'):
                for ci_id in current_affected_ci_ids:
                    _refresh_current_monthly_cost(ci_by_id[ci_id], month)
        summary['accounts'].append(account_result)

    summary['total_monthly_cost'] = float(
        summary['total_monthly_cost'].quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    )
    return summary
