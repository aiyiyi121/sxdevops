from datetime import timedelta

from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from eventwall.services import record_event
from rbac.permissions import RBACPermissionMixin, build_rbac_permission

from .services import (
    WAF_REGIONS,
    WafConfigurationError,
    WafServiceError,
    get_waf_events,
    get_waf_overview,
    get_waf_resources,
    list_waf_accounts,
)
from .models import (
    InternalSecurityAsset,
    InternalSecurityThreat,
    InternalSecurityThreatActivity,
    InternalPlatformSecurityActivity,
    InternalPlatformSecurityControl,
    InternalPlatformSecurityFinding,
    SoftwareSecurityItem,
)
from .serializers import (
    InternalSecurityAssetSerializer,
    InternalSecurityThreatSerializer,
    InternalPlatformSecurityControlSerializer,
    InternalPlatformSecurityFindingSerializer,
    SoftwareSecurityItemSerializer,
)


WAF_VIEW_PERMISSIONS = [IsAuthenticated, build_rbac_permission('cloudsecurity.waf.view')]
INTERNAL_PLATFORM_VIEW_PERMISSIONS = [
    IsAuthenticated,
    build_rbac_permission('cloudsecurity.internal_platform.view'),
]
INTERNAL_PLATFORM_MANAGE_PERMISSIONS = [
    IsAuthenticated,
    build_rbac_permission('cloudsecurity.internal_platform.manage'),
]


def _positive_int(value, default, maximum):
    try:
        return min(max(1, int(value)), maximum)
    except (TypeError, ValueError):
        return default


def _service_response(callback):
    try:
        return Response(callback())
    except WafConfigurationError as exc:
        return Response({'detail': str(exc), 'code': 'waf_not_configured'}, status=400)
    except WafServiceError as exc:
        return Response({'detail': str(exc), 'code': 'waf_provider_error'}, status=502)


@api_view(['GET'])
@permission_classes(WAF_VIEW_PERMISSIONS)
def waf_accounts(request):
    return Response({
        'accounts': list_waf_accounts(),
        'regions': [{'value': key, 'label': label} for key, label in WAF_REGIONS.items()],
    })


@api_view(['GET'])
@permission_classes(WAF_VIEW_PERMISSIONS)
def waf_overview(request):
    return _service_response(lambda: get_waf_overview(
        credential_id=request.query_params.get('credential_id'),
        region_id=request.query_params.get('region_id'),
        hours=request.query_params.get('hours', 24),
        start_time=request.query_params.get('start_time'),
        end_time=request.query_params.get('end_time'),
    ))


@api_view(['GET'])
@permission_classes(WAF_VIEW_PERMISSIONS)
def waf_resources(request):
    return _service_response(lambda: get_waf_resources(
        credential_id=request.query_params.get('credential_id'),
        region_id=request.query_params.get('region_id'),
        page=_positive_int(request.query_params.get('page'), 1, 100000),
        page_size=_positive_int(request.query_params.get('page_size'), 20, 100),
        query=str(request.query_params.get('query') or '').strip()[:128],
    ))


@api_view(['GET'])
@permission_classes(WAF_VIEW_PERMISSIONS)
def waf_events(request):
    return _service_response(lambda: get_waf_events(
        credential_id=request.query_params.get('credential_id'),
        region_id=request.query_params.get('region_id'),
        hours=request.query_params.get('hours', 24),
        start_time=request.query_params.get('start_time'),
        end_time=request.query_params.get('end_time'),
        page=_positive_int(request.query_params.get('page'), 1, 100000),
        page_size=_positive_int(request.query_params.get('page_size'), 20, 100),
        resource=str(request.query_params.get('resource') or '').strip()[:128],
        client_ip=str(request.query_params.get('client_ip') or '').strip()[:128],
        rule_type=str(request.query_params.get('rule_type') or '').strip()[:128],
        action=str(request.query_params.get('action') or '').strip()[:128],
        request_url=str(request.query_params.get('request_url') or '').strip()[:256],
        rule_id=str(request.query_params.get('rule_id') or '').strip()[:128],
    ))


def _finding_activity(finding, action, request, message=''):
    actor = getattr(request.user, 'username', '') or 'system'
    InternalPlatformSecurityActivity.objects.create(
        finding=finding,
        action=action,
        message=message,
        actor=actor,
    )
    record_event(
        module='cloudsecurity',
        category='security_rectification',
        action=action,
        title=f'内部平台安全：{finding.title}',
        summary=message or finding.get_status_display(),
        request=request,
        severity='danger' if finding.severity in {'critical', 'high'} else 'warning',
        resource_module='cloudsecurity',
        resource_type='internal_platform_finding',
        resource_id=finding.id,
        resource_name=finding.title,
        metadata={
            'platform': finding.platform,
            'severity': finding.severity,
            'status': finding.status,
            'ticket_ref': finding.ticket_ref,
        },
        correlation_id=f'internal-platform-security:{finding.id}',
    )


def _finding_queryset(request):
    queryset = (
        InternalPlatformSecurityFinding.objects
        .select_related('control')
        .prefetch_related('activities')
    )
    params = request.query_params
    finding_type = str(params.get('finding_type') or '').strip()
    platform = str(params.get('platform') or '').strip()
    severity = str(params.get('severity') or '').strip()
    finding_status = str(params.get('status') or '').strip()
    overdue = str(params.get('overdue') or '').strip().lower()
    keyword = str(params.get('keyword') or '').strip()
    if finding_type:
        queryset = queryset.filter(finding_type=finding_type)
    if platform:
        queryset = queryset.filter(platform=platform)
    if severity:
        queryset = queryset.filter(severity__in=['critical', 'high']) if severity == 'high_risk' else queryset.filter(severity=severity)
    if finding_status:
        queryset = queryset.filter(status=finding_status)
    if overdue in {'1', 'true'}:
        queryset = queryset.filter(due_date__lt=timezone.localdate()).exclude(
            status__in=[
                InternalPlatformSecurityFinding.STATUS_CLOSED,
                InternalPlatformSecurityFinding.STATUS_IGNORED,
            ]
        )
    if keyword:
        queryset = queryset.filter(
            Q(title__icontains=keyword)
            | Q(owner__icontains=keyword)
            | Q(ticket_ref__icontains=keyword)
            | Q(scope__icontains=keyword)
        )
    return queryset.order_by('status', 'due_date', '-updated_at', '-id')


@api_view(['GET'])
@permission_classes(INTERNAL_PLATFORM_VIEW_PERMISSIONS)
def internal_platform_overview(request):
    base_queryset = InternalPlatformSecurityFinding.objects.all()
    open_statuses = [
        InternalPlatformSecurityFinding.STATUS_PENDING,
        InternalPlatformSecurityFinding.STATUS_IN_PROGRESS,
        InternalPlatformSecurityFinding.STATUS_PENDING_REVIEW,
    ]
    today = timezone.localdate()
    open_queryset = base_queryset.filter(status__in=open_statuses)
    monthly_queryset = base_queryset.filter(finding_type=InternalPlatformSecurityFinding.TYPE_MONTHLY_REVIEW)
    open_by_control = Count(
        'findings',
        filter=Q(
            findings__status__in=open_statuses,
            findings__finding_type=InternalPlatformSecurityFinding.TYPE_RECTIFICATION,
        ),
    )
    controls = (
        InternalPlatformSecurityControl.objects
        .filter(enabled=True)
        .annotate(open_findings=open_by_control)
        .order_by('sort_order', 'id')
    )
    return Response({
        'summary': {
            'open_count': open_queryset.count(),
            'critical_count': open_queryset.filter(severity='critical').count(),
            'overdue_count': open_queryset.filter(due_date__lt=today).count(),
            'pending_review_count': open_queryset.filter(status='pending_review').count(),
            'monthly_total': monthly_queryset.count(),
            'monthly_closed': monthly_queryset.filter(status=InternalPlatformSecurityFinding.STATUS_CLOSED).count(),
        },
        'platforms': [
            {'value': value, 'label': label}
            for value, label in InternalPlatformSecurityControl.PLATFORM_CHOICES
        ],
        'controls': InternalPlatformSecurityControlSerializer(controls, many=True).data,
    })


OPEN_THREAT_STATUSES = [
    InternalSecurityThreat.STATUS_OPEN,
    InternalSecurityThreat.STATUS_PROCESSING,
    InternalSecurityThreat.STATUS_ISOLATED,
]


def _security_asset_queryset(request):
    queryset = InternalSecurityAsset.objects.filter(is_enabled=True)
    params = request.query_params
    source = str(params.get('source') or '').strip()
    agent_status = str(params.get('agent_status') or '').strip()
    risk_level = str(params.get('risk_level') or '').strip()
    protection_status = str(params.get('protection_status') or '').strip()
    keyword = str(params.get('keyword') or '').strip()
    heartbeat_cutoff = timezone.now() - timedelta(minutes=30)
    if source:
        queryset = queryset.filter(source=source)
    if agent_status:
        queryset = queryset.filter(agent_status=agent_status)
    if risk_level:
        queryset = queryset.exclude(risk_level=InternalSecurityAsset.RISK_CLEAN) if risk_level == 'at_risk' else queryset.filter(risk_level=risk_level)
    if protection_status == 'gap':
        queryset = queryset.filter(
            Q(agent_status__in=[InternalSecurityAsset.AGENT_OFFLINE, InternalSecurityAsset.AGENT_PENDING])
            | Q(last_seen_at__lt=heartbeat_cutoff)
            | Q(last_seen_at__isnull=True)
        )
    elif protection_status == 'healthy':
        queryset = queryset.filter(agent_status=InternalSecurityAsset.AGENT_ONLINE, last_seen_at__gte=heartbeat_cutoff)
    if keyword:
        queryset = queryset.filter(
            Q(name__icontains=keyword)
            | Q(ip_address__icontains=keyword)
            | Q(business_line__icontains=keyword)
            | Q(os_name__icontains=keyword)
        )
    return queryset.annotate(
        open_threat_count=Count('threats', filter=Q(threats__status__in=OPEN_THREAT_STATUSES), distinct=True),
        threat_count=Count('threats', distinct=True),
        resolved_threat_count=Count('threats', filter=Q(threats__status=InternalSecurityThreat.STATUS_RESOLVED), distinct=True),
    ).order_by('-open_threat_count', '-risk_level', 'name', 'id')


def _security_threat_queryset(request):
    queryset = InternalSecurityThreat.objects.select_related('asset').prefetch_related('activities')
    params = request.query_params
    threat_type = str(params.get('threat_type') or '').strip()
    severity = str(params.get('severity') or '').strip()
    threat_status = str(params.get('status') or '').strip()
    source = str(params.get('source') or '').strip()
    owner_status = str(params.get('owner_status') or '').strip()
    asset_id = str(params.get('asset_id') or '').strip()
    keyword = str(params.get('keyword') or '').strip()
    if threat_type:
        queryset = queryset.filter(threat_type=threat_type)
    if severity:
        queryset = queryset.filter(severity__in=['critical', 'high']) if severity == 'high_risk' else queryset.filter(severity=severity)
    if threat_status:
        queryset = queryset.filter(status__in=OPEN_THREAT_STATUSES) if threat_status == 'open_all' else queryset.filter(status=threat_status)
    if source:
        queryset = queryset.filter(asset__source=source)
    if owner_status == 'unassigned':
        queryset = queryset.filter(owner='')
    elif owner_status == 'assigned':
        queryset = queryset.exclude(owner='')
    if asset_id:
        queryset = queryset.filter(asset_id=asset_id)
    if keyword:
        queryset = queryset.filter(
            Q(title__icontains=keyword)
            | Q(asset__name__icontains=keyword)
            | Q(asset__ip_address__icontains=keyword)
            | Q(process_path__icontains=keyword)
            | Q(command_line__icontains=keyword)
        )
    return _order_threats(queryset)


def _order_threats(queryset):
    return queryset.annotate(
        _status_rank=Case(
            When(status=InternalSecurityThreat.STATUS_OPEN, then=Value(0)),
            When(status=InternalSecurityThreat.STATUS_PROCESSING, then=Value(1)),
            When(status=InternalSecurityThreat.STATUS_ISOLATED, then=Value(2)),
            When(status=InternalSecurityThreat.STATUS_RESOLVED, then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        ),
        _severity_rank=Case(
            When(severity='critical', then=Value(0)),
            When(severity='high', then=Value(1)),
            When(severity='medium', then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        ),
    ).order_by('_status_rank', '_severity_rank', '-detected_at', '-id')


def _software_security_queryset(request):
    queryset = SoftwareSecurityItem.objects.filter(is_active=True)
    params = request.query_params
    priority = str(params.get('priority') or '').strip().upper()
    deployment_type = str(params.get('deployment_type') or '').strip()
    necessity = str(params.get('upgrade_necessity') or '').strip()
    item_status = str(params.get('status') or '').strip()
    keyword = str(params.get('keyword') or '').strip()
    if priority:
        queryset = queryset.filter(priority__in=['P0', 'P1']) if priority == 'HIGH' else queryset.filter(priority=priority)
    if deployment_type:
        queryset = queryset.filter(deployment_type=deployment_type)
    if necessity:
        queryset = queryset.filter(upgrade_necessity=necessity)
    if item_status:
        queryset = queryset.filter(status=item_status)
    if keyword:
        queryset = queryset.filter(
            Q(software_name__icontains=keyword)
            | Q(current_version__icontains=keyword)
            | Q(latest_version__icontains=keyword)
            | Q(risk_summary__icontains=keyword)
        )
    return queryset.order_by('priority', 'row_number')


@api_view(['GET'])
@permission_classes(INTERNAL_PLATFORM_VIEW_PERMISSIONS)
def internal_platform_posture(request):
    assets = InternalSecurityAsset.objects.filter(is_enabled=True)
    threats = InternalSecurityThreat.objects.all()
    software = SoftwareSecurityItem.objects.filter(is_active=True)
    open_threats = threats.filter(status__in=OPEN_THREAT_STATUSES)
    heartbeat_cutoff = timezone.now() - timedelta(minutes=30)
    protection_gaps = assets.filter(
        Q(agent_status__in=[InternalSecurityAsset.AGENT_OFFLINE, InternalSecurityAsset.AGENT_PENDING])
        | Q(last_seen_at__lt=heartbeat_cutoff)
        | Q(last_seen_at__isnull=True)
    )
    high_risk_software = software.filter(priority__in=['P0', 'P1'])
    source_counts = dict(assets.values_list('source').annotate(total=Count('id')))
    last_scan_at = assets.order_by('-last_scan_at').values_list('last_scan_at', flat=True).first()
    connectors = []
    for value, label in InternalSecurityAsset.SOURCE_CHOICES:
        total = int(source_counts.get(value) or 0)
        connectors.append({
            'value': value,
            'label': label,
            'asset_count': total,
            'status': 'planned' if value == InternalSecurityAsset.SOURCE_VSPHERE and total == 0 else ('connected' if total else 'pending'),
        })
    return Response({
        'summary': {
            'asset_total': assets.count(),
            'agent_online_count': assets.filter(agent_status=InternalSecurityAsset.AGENT_ONLINE).count(),
            'asset_risk_count': assets.exclude(risk_level=InternalSecurityAsset.RISK_CLEAN).count(),
            'open_threat_count': open_threats.count(),
            'critical_threat_count': open_threats.filter(severity='critical').count(),
            'isolated_count': threats.filter(status=InternalSecurityThreat.STATUS_ISOLATED).count(),
            'protection_gap_count': protection_gaps.count(),
            'unassigned_threat_count': open_threats.filter(owner='').count(),
            'software_total': software.count(),
            'software_high_risk_count': high_risk_software.count(),
            'software_p0_count': software.filter(priority='P0').count(),
            'software_planned_count': software.filter(status=SoftwareSecurityItem.STATUS_PLANNED).count(),
            'last_scan_at': last_scan_at,
        },
        'connectors': connectors,
        'threat_types': [{'value': value, 'label': label} for value, label in InternalSecurityThreat.THREAT_TYPE_CHOICES],
        'asset_sources': [{'value': value, 'label': label} for value, label in InternalSecurityAsset.SOURCE_CHOICES],
        'top_threats': InternalSecurityThreatSerializer(_order_threats(open_threats.select_related('asset'))[:5], many=True).data,
        'top_software': SoftwareSecurityItemSerializer(high_risk_software.order_by('priority', 'row_number')[:6], many=True).data,
    })


@api_view(['GET'])
@permission_classes(INTERNAL_PLATFORM_VIEW_PERMISSIONS)
def internal_platform_assets(request):
    return Response(InternalSecurityAssetSerializer(_security_asset_queryset(request), many=True).data)


@api_view(['GET'])
@permission_classes(INTERNAL_PLATFORM_VIEW_PERMISSIONS)
def internal_platform_threats(request):
    return Response(InternalSecurityThreatSerializer(_security_threat_queryset(request), many=True).data)


@api_view(['GET'])
@permission_classes(INTERNAL_PLATFORM_VIEW_PERMISSIONS)
def internal_platform_software(request):
    return Response(SoftwareSecurityItemSerializer(_software_security_queryset(request), many=True).data)


def _refresh_asset_risk(asset):
    if asset is None:
        return
    severities = list(asset.threats.filter(status__in=OPEN_THREAT_STATUSES).values_list('severity', flat=True))
    risk_order = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
    asset.risk_level = max(severities, key=lambda value: risk_order.get(value, 0)) if severities else InternalSecurityAsset.RISK_CLEAN
    asset.save(update_fields=['risk_level', 'updated_at'])


@api_view(['POST'])
@permission_classes(INTERNAL_PLATFORM_MANAGE_PERMISSIONS)
def internal_platform_threat_action(request, pk):
    try:
        threat = InternalSecurityThreat.objects.select_related('asset').prefetch_related('activities').get(pk=pk)
    except InternalSecurityThreat.DoesNotExist:
        return Response({'detail': '威胁事件不存在。'}, status=status.HTTP_404_NOT_FOUND)
    action = str(request.data.get('action') or '').strip()
    status_map = {
        'progress': InternalSecurityThreat.STATUS_PROCESSING,
        'isolate': InternalSecurityThreat.STATUS_ISOLATED,
        'resolve': InternalSecurityThreat.STATUS_RESOLVED,
        'ignore': InternalSecurityThreat.STATUS_IGNORED,
        'reopen': InternalSecurityThreat.STATUS_OPEN,
    }
    if action not in status_map:
        return Response({'action': '无效的处置动作。'}, status=status.HTTP_400_BAD_REQUEST)
    allowed_actions = {
        InternalSecurityThreat.STATUS_OPEN: {'progress', 'isolate', 'resolve', 'ignore'},
        InternalSecurityThreat.STATUS_PROCESSING: {'isolate', 'resolve', 'ignore'},
        InternalSecurityThreat.STATUS_ISOLATED: {'progress', 'resolve', 'ignore'},
        InternalSecurityThreat.STATUS_RESOLVED: {'reopen'},
        InternalSecurityThreat.STATUS_IGNORED: {'reopen'},
    }
    if action not in allowed_actions.get(threat.status, set()):
        return Response({'action': f'当前状态“{threat.get_status_display()}”不支持该操作。'}, status=status.HTTP_400_BAD_REQUEST)
    message = str(request.data.get('message') or '').strip()
    if action in {'ignore', 'reopen'} and not message:
        return Response({'message': '忽略或重新打开威胁时必须填写原因。'}, status=status.HTTP_400_BAD_REQUEST)
    previous_status = threat.status
    threat.status = status_map[action]
    threat.owner = str(request.data.get('owner') or threat.owner or request.user.username).strip()
    threat.ticket_ref = str(request.data.get('ticket_ref') or threat.ticket_ref or '').strip()
    threat.resolved_at = timezone.now() if action in {'resolve', 'ignore'} else None
    threat.save(update_fields=['status', 'owner', 'ticket_ref', 'resolved_at', 'updated_at'])
    InternalSecurityThreatActivity.objects.create(
        threat=threat,
        action=action,
        from_status=previous_status,
        to_status=threat.status,
        message=message,
        actor=request.user.username,
    )
    _refresh_asset_risk(threat.asset)
    record_event(
        module='cloudsecurity',
        category='host_security',
        action=f'threat_{action}',
        title=f'主机安全：{threat.title}',
        summary=message or threat.get_status_display(),
        request=request,
        severity='danger' if threat.severity in {'critical', 'high'} else 'warning',
        resource_module='cloudsecurity',
        resource_type='internal_security_threat',
        resource_id=threat.id,
        resource_name=threat.title,
        metadata={'asset': threat.asset_name if hasattr(threat, 'asset_name') else (threat.asset.name if threat.asset else ''), 'status': threat.status},
        correlation_id=f'internal-security-threat:{threat.id}',
    )
    threat = InternalSecurityThreat.objects.select_related('asset').prefetch_related('activities').get(pk=threat.pk)
    return Response(InternalSecurityThreatSerializer(threat).data)


@api_view(['POST'])
@permission_classes(INTERNAL_PLATFORM_MANAGE_PERMISSIONS)
def internal_platform_software_status(request, pk):
    try:
        item = SoftwareSecurityItem.objects.get(pk=pk, is_active=True)
    except SoftwareSecurityItem.DoesNotExist:
        return Response({'detail': '软件版本项不存在。'}, status=status.HTTP_404_NOT_FOUND)
    item_status = str(request.data.get('status') or '').strip()
    if item_status not in dict(SoftwareSecurityItem.STATUS_CHOICES):
        return Response({'status': '无效的治理状态。'}, status=status.HTTP_400_BAD_REQUEST)
    item.status = item_status
    if 'plan_time' in request.data:
        item.plan_time = str(request.data.get('plan_time') or '').strip()[:80]
    if 'owner_feedback' in request.data:
        item.owner_feedback = str(request.data.get('owner_feedback') or '').strip()
    item.last_reviewed_at = timezone.now()
    item.save(update_fields=['status', 'plan_time', 'owner_feedback', 'last_reviewed_at', 'updated_at'])
    record_event(
        module='cloudsecurity',
        category='software_security',
        action='software_status_update',
        title=f'软件安全：{item.software_name}',
        summary=f'{item.get_status_display()} · {item.plan_time or "未填写计划"}',
        request=request,
        severity='danger' if item.priority in {'P0', 'P1'} else 'warning',
        resource_module='cloudsecurity',
        resource_type='software_security_item',
        resource_id=item.id,
        resource_name=item.software_name,
        metadata={'priority': item.priority, 'status': item.status, 'current_version': item.current_version},
        correlation_id=f'software-security:{item.id}',
    )
    return Response(SoftwareSecurityItemSerializer(item).data)


class InternalPlatformSecurityFindingViewSet(RBACPermissionMixin, viewsets.ViewSet):
    rbac_permissions = {
        'list': ['cloudsecurity.internal_platform.view'],
        'retrieve': ['cloudsecurity.internal_platform.view'],
        'create': ['cloudsecurity.internal_platform.manage'],
        'partial_update': ['cloudsecurity.internal_platform.manage'],
        'progress': ['cloudsecurity.internal_platform.manage'],
        'close': ['cloudsecurity.internal_platform.manage'],
        'reopen': ['cloudsecurity.internal_platform.manage'],
    }

    def _get_finding(self, pk):
        return (
            InternalPlatformSecurityFinding.objects
            .select_related('control')
            .prefetch_related('activities')
            .get(pk=pk)
        )

    def list(self, request):
        return Response(InternalPlatformSecurityFindingSerializer(_finding_queryset(request), many=True).data)

    def retrieve(self, request, pk=None):
        try:
            finding = self._get_finding(pk)
        except InternalPlatformSecurityFinding.DoesNotExist:
            return Response({'detail': '整改项不存在。'}, status=status.HTTP_404_NOT_FOUND)
        return Response(InternalPlatformSecurityFindingSerializer(finding).data)

    def create(self, request):
        serializer = InternalPlatformSecurityFindingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        finding = serializer.save(created_by=request.user.username)
        _finding_activity(finding, 'create', request, '创建整改项')
        return Response(InternalPlatformSecurityFindingSerializer(finding).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        try:
            finding = self._get_finding(pk)
        except InternalPlatformSecurityFinding.DoesNotExist:
            return Response({'detail': '整改项不存在。'}, status=status.HTTP_404_NOT_FOUND)
        serializer = InternalPlatformSecurityFindingSerializer(finding, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        finding = serializer.save()
        _finding_activity(finding, 'update', request, str(request.data.get('note') or '更新整改项信息'))
        return Response(InternalPlatformSecurityFindingSerializer(finding).data)

    def progress(self, request, pk=None):
        try:
            finding = self._get_finding(pk)
        except InternalPlatformSecurityFinding.DoesNotExist:
            return Response({'detail': '整改项不存在。'}, status=status.HTTP_404_NOT_FOUND)
        message = str(request.data.get('message') or '').strip()
        if not message:
            return Response({'message': '请填写进展说明。'}, status=status.HTTP_400_BAD_REQUEST)
        finding.status = request.data.get('status') or InternalPlatformSecurityFinding.STATUS_IN_PROGRESS
        if finding.status not in dict(InternalPlatformSecurityFinding.STATUS_CHOICES):
            return Response({'status': '无效状态。'}, status=status.HTTP_400_BAD_REQUEST)
        for field in ('owner', 'ticket_ref', 'evidence'):
            if field in request.data:
                setattr(finding, field, str(request.data.get(field) or '').strip())
        if 'due_date' in request.data:
            finding.due_date = request.data.get('due_date') or None
        finding.save()
        _finding_activity(finding, 'progress', request, message)
        return Response(InternalPlatformSecurityFindingSerializer(finding).data)

    def close(self, request, pk=None):
        try:
            finding = self._get_finding(pk)
        except InternalPlatformSecurityFinding.DoesNotExist:
            return Response({'detail': '整改项不存在。'}, status=status.HTTP_404_NOT_FOUND)
        message = str(request.data.get('message') or '').strip()
        if not message:
            return Response({'message': '关闭前请填写复核结论或证据。'}, status=status.HTTP_400_BAD_REQUEST)
        finding.status = InternalPlatformSecurityFinding.STATUS_CLOSED
        finding.evidence = str(request.data.get('evidence') or finding.evidence or '').strip()
        finding.closed_by = request.user.username
        finding.closed_at = timezone.now()
        finding.save(update_fields=['status', 'evidence', 'closed_by', 'closed_at', 'updated_at'])
        _finding_activity(finding, 'close', request, message)
        return Response(InternalPlatformSecurityFindingSerializer(finding).data)

    def reopen(self, request, pk=None):
        try:
            finding = self._get_finding(pk)
        except InternalPlatformSecurityFinding.DoesNotExist:
            return Response({'detail': '整改项不存在。'}, status=status.HTTP_404_NOT_FOUND)
        finding.status = InternalPlatformSecurityFinding.STATUS_PENDING
        finding.closed_by = ''
        finding.closed_at = None
        finding.save(update_fields=['status', 'closed_by', 'closed_at', 'updated_at'])
        _finding_activity(finding, 'reopen', request, str(request.data.get('message') or '复开整改项'))
        return Response(InternalPlatformSecurityFindingSerializer(finding).data)
