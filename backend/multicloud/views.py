from rest_framework import filters, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from eventwall.mixins import EventWallModelViewSetMixin
from eventwall.models import EventRecord
from eventwall.services import build_resource, record_event
from rbac.permissions import RBACPermissionMixin, build_rbac_permission
from rbac.services import user_has_permissions

from .models import CloudAsset, CloudCredential, CloudEnvironment, CloudSyncTask
from .serializers import CloudAssetSerializer, CloudCredentialSerializer, CloudEnvironmentSerializer, CloudSyncTaskSerializer
from .services import (
    batch_sync_targets,
    build_cost_trend,
    build_overview,
    build_provider_catalog,
    build_topology,
    execute_batch_action,
    sync_credential_environments,
    sync_environment_inventory,
    sync_environment_to_cmdb,
    test_credential_connection,
)


class CloudCredentialViewSet(EventWallModelViewSetMixin, RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = CloudCredential.objects.all().prefetch_related('environments')
    serializer_class = CloudCredentialSerializer
    pagination_class = None
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'account_id', 'account_name', 'owner', 'description']
    event_module = 'multicloud'
    event_resource_type = 'cloud_credential'
    event_resource_label = '云账号'
    event_resource_name_fields = ('name', 'account_name')
    event_exclude_fields = ('access_key_id', 'access_key_secret', 'external_id', 'role_arn')
    rbac_permissions = {
        'list': ['ops.multicloud.view'],
        'retrieve': ['ops.multicloud.view'],
        'create': ['ops.multicloud.manage'],
        'update': ['ops.multicloud.manage'],
        'partial_update': ['ops.multicloud.manage'],
        'destroy': ['ops.multicloud.manage'],
        'test_connection': ['ops.multicloud.manage'],
        'sync_all': ['ops.multicloud.sync'],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        for key in ('provider',):
            if self.request.query_params.get(key):
                queryset = queryset.filter(**{key: self.request.query_params.get(key)})
        if self.request.query_params.get('is_enabled') in {'true', 'false'}:
            queryset = queryset.filter(is_enabled=self.request.query_params.get('is_enabled') == 'true')
        if self.request.query_params.get('demo_mode') in {'true', 'false'}:
            queryset = queryset.filter(demo_mode=self.request.query_params.get('demo_mode') == 'true')
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user.username, updated_by=self.request.user.username)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user.username)

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        credential = self.get_object()
        result = test_credential_connection(credential)
        record_event(
            request=request,
            module='multicloud',
            category='execution',
            action='test_connection',
            title='测试云账号连通性',
            summary=f'云账号 {credential.name} 连通性测试{"成功" if result.get("success") else "失败"}',
            result=EventRecord.RESULT_SUCCESS if result.get('success') else EventRecord.RESULT_FAILED,
            severity=EventRecord.SEVERITY_INFO if result.get('success') else EventRecord.SEVERITY_WARNING,
            resource_type='cloud_credential',
            resource_id=credential.id,
            resource_name=credential.name,
            correlation_id=f'cloud-credential:{credential.id}',
            metadata={'provider': credential.provider},
        )
        return Response(result)

    @action(detail=True, methods=['post'])
    def sync_all(self, request, pk=None):
        credential = self.get_object()
        result = sync_credential_environments(credential, operator=request.user.username)
        credential.refresh_from_db()
        record_event(
            request=request,
            module='multicloud',
            category='sync',
            action='sync_all',
            title='同步云账号环境',
            summary=result['message'],
            result=EventRecord.RESULT_SUCCESS if result.get('success', True) else EventRecord.RESULT_FAILED,
            severity=EventRecord.SEVERITY_INFO,
            resource_type='cloud_credential',
            resource_id=credential.id,
            resource_name=credential.name,
            correlation_id=f'cloud-credential:{credential.id}',
            metadata={'provider': credential.provider},
        )
        return Response(
            {'message': result['message'], 'result': result, 'credential': CloudCredentialSerializer(credential).data},
            status=status.HTTP_200_OK,
        )


class CloudEnvironmentViewSet(EventWallModelViewSetMixin, RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = CloudEnvironment.objects.select_related('credential').prefetch_related('assets')
    serializer_class = CloudEnvironmentSerializer
    pagination_class = None
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'code', 'business_line', 'region', 'owner', 'description']
    event_module = 'multicloud'
    event_resource_type = 'cloud_environment'
    event_resource_label = '云环境'
    event_resource_name_fields = ('name', 'code')
    rbac_permissions = {
        'list': ['ops.multicloud.view'],
        'retrieve': ['ops.multicloud.view'],
        'create': ['ops.multicloud.manage'],
        'update': ['ops.multicloud.manage'],
        'partial_update': ['ops.multicloud.manage'],
        'destroy': ['ops.multicloud.manage'],
        'sync': ['ops.multicloud.sync'],
        'sync_cmdb': ['ops.multicloud.sync', 'cmdb.ci.manage'],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        system_name = (self.request.query_params.get('system_name') or self.request.query_params.get('system') or '').strip()
        if system_name:
            queryset = queryset.filter(business_line=system_name)
        mapping = {
            'provider': 'credential__provider',
            'environment_type': 'environment_type',
            'status': 'status',
            'credential': 'credential_id',
        }
        for key, field in mapping.items():
            if self.request.query_params.get(key):
                queryset = queryset.filter(**{field: self.request.query_params.get(key)})
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user.username, updated_by=self.request.user.username)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user.username)

    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        environment = self.get_object()
        task = sync_environment_inventory(environment, operator=request.user.username)
        environment.refresh_from_db()
        record_event(
            request=request,
            module='multicloud',
            category='sync',
            action='sync_inventory',
            title='同步云环境资源',
            summary=task.summary,
            result=EventRecord.RESULT_SUCCESS if task.status == 'success' else EventRecord.RESULT_FAILED,
            severity=EventRecord.SEVERITY_INFO if task.status == 'success' else EventRecord.SEVERITY_WARNING,
            resource_type='cloud_environment',
            resource_id=environment.id,
            resource_name=environment.name,
            business_line=environment.business_line,
            environment=environment.environment_type,
            correlation_id=f'cloud-sync:{task.id}',
            related_resources=[
                build_resource('multicloud', 'cloud_credential', environment.credential_id, environment.credential.name),
                build_resource('multicloud', 'cloud_sync_task', task.id, task.summary),
            ],
            metadata={'task_type': task.task_type, 'status': task.status},
        )
        return Response(
            {'message': task.summary, 'task': CloudSyncTaskSerializer(task).data, 'environment': CloudEnvironmentSerializer(environment).data},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'])
    def sync_cmdb(self, request, pk=None):
        environment = self.get_object()
        task = sync_environment_to_cmdb(environment, operator=request.user.username)
        environment.refresh_from_db()
        record_event(
            request=request,
            module='multicloud',
            category='sync',
            action='sync_cmdb',
            title='同步云环境到 CMDB',
            summary=task.summary,
            result=EventRecord.RESULT_SUCCESS if task.status == 'success' else EventRecord.RESULT_FAILED,
            severity=EventRecord.SEVERITY_WARNING,
            resource_type='cloud_environment',
            resource_id=environment.id,
            resource_name=environment.name,
            business_line=environment.business_line,
            environment=environment.environment_type,
            correlation_id=f'cloud-sync:{task.id}',
            related_resources=[
                build_resource('multicloud', 'cloud_credential', environment.credential_id, environment.credential.name),
                build_resource('multicloud', 'cloud_sync_task', task.id, task.summary),
                build_resource('cmdb', 'config_scope', environment.code, environment.name),
            ],
            metadata={'task_type': task.task_type, 'status': task.status},
        )
        return Response(
            {'message': task.summary, 'task': CloudSyncTaskSerializer(task).data, 'environment': CloudEnvironmentSerializer(environment).data},
            status=status.HTTP_200_OK,
        )


class CloudAssetViewSet(RBACPermissionMixin, viewsets.ReadOnlyModelViewSet):
    queryset = CloudAsset.objects.select_related('environment', 'environment__credential')
    serializer_class = CloudAssetSerializer
    pagination_class = None
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'resource_id', 'private_ip', 'public_ip', 'spec', 'environment__name']
    rbac_permissions = {'list': ['ops.multicloud.view'], 'retrieve': ['ops.multicloud.view']}

    def get_queryset(self):
        queryset = super().get_queryset()
        for key in ('provider', 'resource_type', 'risk_level', 'sync_state'):
            if self.request.query_params.get(key):
                queryset = queryset.filter(**{key: self.request.query_params.get(key)})
        if self.request.query_params.get('environment'):
            queryset = queryset.filter(environment_id=self.request.query_params.get('environment'))
        return queryset


class CloudSyncTaskViewSet(RBACPermissionMixin, viewsets.ReadOnlyModelViewSet):
    queryset = CloudSyncTask.objects.select_related('credential', 'environment', 'environment__credential')
    serializer_class = CloudSyncTaskSerializer
    pagination_class = None
    filter_backends = [filters.SearchFilter]
    search_fields = ['operator', 'summary', 'credential__name', 'environment__name']
    rbac_permissions = {'list': ['ops.multicloud.view'], 'retrieve': ['ops.multicloud.view']}

    def get_queryset(self):
        queryset = super().get_queryset()
        for key in ('status', 'task_type'):
            if self.request.query_params.get(key):
                queryset = queryset.filter(**{key: self.request.query_params.get(key)})
        return queryset


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('ops.multicloud.view')])
def overview_view(request):
    return Response(build_overview())


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('ops.multicloud.view')])
def catalog_view(request):
    return Response({'providers': build_provider_catalog()})


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('ops.multicloud.view')])
def topology_view(request):
    environment_id = request.query_params.get('environment')
    provider = request.query_params.get('provider', '')
    return Response(build_topology(environment_id=environment_id, provider=provider))


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('ops.multicloud.view')])
def cost_trend_view(request):
    return Response(
        build_cost_trend(
            provider=request.query_params.get('provider', ''),
            environment_id=request.query_params.get('environment') or None,
            resource_type=request.query_params.get('resource_type', ''),
            group_by=request.query_params.get('group_by', 'provider') or 'provider',
        )
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated, build_rbac_permission('ops.multicloud.sync')])
def batch_sync_view(request):
    environment_ids = request.data.get('environment_ids') or []
    credential_ids = request.data.get('credential_ids') or []
    sync_cmdb = bool(request.data.get('sync_cmdb'))
    if sync_cmdb and not user_has_permissions(request.user, ['cmdb.ci.manage']):
        return Response({'detail': '同步到 CMDB 需要 CMDB 资源管理权限。'}, status=status.HTTP_403_FORBIDDEN)
    results = batch_sync_targets(
        environment_ids=environment_ids,
        credential_ids=credential_ids,
        operator=request.user.username,
        sync_cmdb=sync_cmdb,
    )
    record_event(
        request=request,
        module='multicloud',
        category='sync',
        action='batch_sync',
        title='批量同步多云目标',
        summary=f'已提交 {len(results)} 个多云同步任务',
        result=EventRecord.RESULT_SUCCESS,
        severity=EventRecord.SEVERITY_INFO,
        resource_type='cloud_batch_sync',
        resource_id=f'batch-{len(results)}',
        resource_name='批量同步',
        correlation_id=f'multicloud-batch-sync:{len(results)}:{timezone.now().strftime("%Y%m%d%H%M%S")}',
        metadata={
            'environment_ids': environment_ids,
            'credential_ids': credential_ids,
            'sync_cmdb': sync_cmdb,
            'count': len(results),
        },
    )
    return Response(
        {
            'message': f'Submitted {len(results)} batch sync tasks.',
            'count': len(results),
            'results': results,
        },
        status=status.HTTP_200_OK,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def batch_action_view(request):
    scope = request.data.get('scope')
    action = request.data.get('action')
    ids = request.data.get('ids') or []
    payload = request.data.get('payload') or {}

    permission_codes = {
        'credentials': ['ops.multicloud.manage'],
        'environments': ['ops.multicloud.sync'] if action in {'sync_inventory', 'sync_cmdb'} else ['ops.multicloud.manage'],
        'assets': ['ops.multicloud.manage'],
    }.get(scope, [])
    if not permission_codes:
        return Response({'detail': '请选择有效的批量操作范围。'}, status=status.HTTP_400_BAD_REQUEST)
    if action == 'sync_cmdb':
        permission_codes = ['ops.multicloud.sync', 'cmdb.ci.manage']

    if not user_has_permissions(request.user, permission_codes):
        return Response({'detail': f'Missing permissions: {", ".join(permission_codes)}'}, status=status.HTTP_403_FORBIDDEN)

    try:
        result = execute_batch_action(scope=scope, action=action, ids=ids, operator=request.user.username, payload=payload)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    record_event(
        request=request,
        module='multicloud',
        category='execution',
        action=action,
        title='执行多云批量动作',
        summary=f'对 {scope} 执行批量动作 {action}，目标 {len(ids)} 个',
        result=EventRecord.RESULT_SUCCESS,
        severity=EventRecord.SEVERITY_WARNING if action in {'delete', 'sync_cmdb'} else EventRecord.SEVERITY_INFO,
        resource_type=f'multicloud_{scope}',
        resource_id='batch',
        resource_name=scope,
        correlation_id=f'multicloud-batch-action:{scope}:{action}',
        metadata={'ids': ids, 'payload': payload},
    )
    return Response(result, status=status.HTTP_200_OK)
