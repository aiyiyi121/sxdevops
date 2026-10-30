from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone

from eventwall.mixins import EventWallModelViewSetMixin
from eventwall.models import EventRecord
from eventwall.services import build_resource, record_event

from .models import DataSource, SqlOrder, QueryOrder, SqlCheckResult
from .serializers import (
    DataSourceSerializer, SqlOrderSerializer,
    QueryOrderSerializer,
)
from . import sql_checker
from . import db_executor
from rbac.permissions import RBACPermissionMixin, build_rbac_permission


class DataSourceViewSet(EventWallModelViewSetMixin, RBACPermissionMixin, viewsets.ModelViewSet):
    """数据源管理"""
    queryset = DataSource.objects.all()
    serializer_class = DataSourceSerializer
    search_fields = ['name', 'host']
    event_module = 'sqlaudit'
    event_resource_type = 'sql_datasource'
    event_resource_label = 'SQL 数据源'
    event_resource_name_fields = ('name',)
    event_exclude_fields = ('password',)
    rbac_permissions = {
        'list': ['sqlaudit.datasource.view'],
        'retrieve': ['sqlaudit.datasource.view'],
        'create': ['sqlaudit.datasource.view', 'sqlaudit.datasource.manage'],
        'update': ['sqlaudit.datasource.view', 'sqlaudit.datasource.manage'],
        'partial_update': ['sqlaudit.datasource.view', 'sqlaudit.datasource.manage'],
        'destroy': ['sqlaudit.datasource.view', 'sqlaudit.datasource.manage'],
        'test_connection': ['sqlaudit.datasource.view', 'sqlaudit.datasource.manage'],
        'databases': ['sqlaudit.datasource.view'],
    }

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        ds = self.get_object()
        success, message = db_executor.test_connection(ds)
        record_event(
            request=request,
            module='sqlaudit',
            category='execution',
            action='test_connection',
            title='测试 SQL 数据源连通性',
            summary=f'数据源 {ds.name} 连通性测试{"成功" if success else "失败"}',
            result=EventRecord.RESULT_SUCCESS if success else EventRecord.RESULT_FAILED,
            severity=EventRecord.SEVERITY_INFO if success else EventRecord.SEVERITY_WARNING,
            resource_type='sql_datasource',
            resource_id=ds.id,
            resource_name=ds.name,
            correlation_id=f'sql-datasource:{ds.id}',
            metadata={'db_type': ds.db_type, 'host': ds.host},
        )
        return Response({
            'success': success,
            'message': message,
        })

    @action(detail=True, methods=['get'])
    def databases(self, request, pk=None):
        ds = self.get_object()
        databases = db_executor.get_databases(ds)
        return Response({'databases': databases})


class SqlOrderViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    """SQL 工单管理"""
    queryset = SqlOrder.objects.select_related('datasource').prefetch_related('check_results').all()
    serializer_class = SqlOrderSerializer
    search_fields = ['title', 'submitter', 'sql_content']
    http_method_names = ['get', 'post', 'head', 'options']
    rbac_permissions = {
        'list': ['sqlaudit.order.view'],
        'retrieve': ['sqlaudit.order.view'],
        'create': ['sqlaudit.datasource.view', 'sqlaudit.order.submit'],
        'approve': ['sqlaudit.order.view', 'sqlaudit.order.review'],
        'reject': ['sqlaudit.order.view', 'sqlaudit.order.review'],
        'execute': ['sqlaudit.order.view', 'sqlaudit.order.execute'],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        status_value = self.request.query_params.get('status')
        if status_value in dict(SqlOrder.STATUS_CHOICES):
            queryset = queryset.filter(status=status_value)

        search = (self.request.query_params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(submitter__icontains=search)
                | Q(sql_content__icontains=search)
            )
        return queryset

    def perform_create(self, serializer):
        order = serializer.save(
            submitter=self.request.user.username,
            status='pending',
            reviewer='',
            review_comment='',
            reviewed_at=None,
            execute_log='',
            affected_rows=None,
            duration_ms=None,
            executed_at=None,
        )
        results = sql_checker.check_sql(
            order.sql_content,
            order.sql_type,
            getattr(order.datasource, 'db_type', 'mysql'),
        )
        for item in results:
            SqlCheckResult.objects.create(
                order=order,
                level=item.level,
                rule_name=item.rule_name,
                message=item.message,
                line_no=item.line_no,
            )

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        order = self.get_object()
        if order.status != 'pending':
            return Response(
                {'error': f'当前状态为"{order.get_status_display()}"，不可审核'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = 'approved'
        order.reviewer = request.user.username
        order.review_comment = request.data.get('comment', '')
        order.reviewed_at = timezone.now()
        order.save()
        return Response(SqlOrderSerializer(order).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        order = self.get_object()
        if order.status != 'pending':
            return Response(
                {'error': f'当前状态为"{order.get_status_display()}"，不可驳回'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = 'rejected'
        order.reviewer = request.user.username
        order.review_comment = request.data.get('comment', '')
        order.reviewed_at = timezone.now()
        order.save()
        record_event(
            request=request,
            module='sqlaudit',
            category='workflow',
            action='reject',
            title='驳回 SQL 工单',
            summary=f'SQL 工单 {order.title} 已被驳回',
            result=EventRecord.RESULT_REJECTED,
            severity=EventRecord.SEVERITY_WARNING,
            resource_type='sql_order',
            resource_id=order.id,
            resource_name=order.title,
            application=order.database,
            correlation_id=f'sql-order:{order.id}',
            related_resources=[build_resource('sqlaudit', 'sql_datasource', order.datasource_id, order.datasource.name)],
            metadata={'database': order.database},
        )
        return Response(SqlOrderSerializer(order).data)

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        order = self.get_object()
        if order.status != 'approved':
            return Response(
                {'error': f'当前状态为"{order.get_status_display()}"，不可执行'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.status = 'executing'
        order.save()

        success, affected, duration, log = db_executor.execute_sql(
            order.datasource, order.database, order.sql_content,
        )

        order.status = 'executed' if success else 'failed'
        order.affected_rows = affected
        order.duration_ms = duration
        order.execute_log = log
        order.executed_at = timezone.now()
        order.save()
        record_event(
            request=request,
            module='sqlaudit',
            category='execution',
            action='execute',
            title='执行 SQL 工单',
            summary=f'SQL 工单 {order.title} 执行{"成功" if success else "失败"}',
            result=EventRecord.RESULT_SUCCESS if success else EventRecord.RESULT_FAILED,
            severity=EventRecord.SEVERITY_WARNING,
            resource_type='sql_order',
            resource_id=order.id,
            resource_name=order.title,
            application=order.database,
            correlation_id=f'sql-order:{order.id}',
            related_resources=[build_resource('sqlaudit', 'sql_datasource', order.datasource_id, order.datasource.name)],
            metadata={
                'database': order.database,
                'affected_rows': affected,
                'duration_ms': duration,
            },
        )

        return Response(SqlOrderSerializer(order).data)


class QueryOrderViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    """查询工单"""
    queryset = QueryOrder.objects.select_related('datasource').all()
    serializer_class = QueryOrderSerializer
    search_fields = ['submitter', 'sql_content']
    http_method_names = ['get', 'post', 'head', 'options']
    rbac_permissions = {
        'list': ['sqlaudit.query.view'],
        'retrieve': ['sqlaudit.query.view'],
        'create': ['sqlaudit.datasource.view', 'sqlaudit.query.execute'],
    }

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        datasource_id = request.data.get('datasource')
        database = request.data.get('database', '')
        sql_content = request.data.get('sql_content', '')

        try:
            ds = DataSource.objects.get(id=datasource_id)
        except DataSource.DoesNotExist:
            return Response(
                {'error': '数据源不存在'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        validation_error = db_executor.validate_query_content(ds, sql_content)
        if validation_error:
            return Response(
                {'error': validation_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        success, columns, rows, count, duration, error = db_executor.execute_query(
            ds, database, sql_content,
        )

        query_order = serializer.save(
            submitter=request.user.username,
            result_count=count if success else 0,
            duration_ms=duration,
        )
        if not success:
            return Response(
                {'error': error, 'order': QueryOrderSerializer(query_order).data},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'order': QueryOrderSerializer(query_order).data,
            'columns': columns,
            'rows': rows,
            'count': count,
            'duration_ms': duration,
        }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, build_rbac_permission('sqlaudit.order.submit')])
def sql_check_api(request):
    sql_content = request.data.get('sql_content', '')
    sql_type = request.data.get('sql_type', 'DML')
    db_type = request.data.get('db_type', 'mysql')

    if not sql_content.strip():
        return Response(
            {'error': 'SQL 内容不能为空'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    results = sql_checker.check_sql(sql_content, sql_type, db_type)
    return Response({
        'results': [item.to_dict() for item in results],
    })
