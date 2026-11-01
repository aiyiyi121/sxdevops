"""Bounded event fixtures for an explicitly opted-in showcase installation."""

import os
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from eventwall.models import EventEnvironment, EventRecord, EventSource
from eventwall.services import resolve_event_environment, touch_event_environment


GENERATOR = 'showcase-hourly-v1'
SCENARIOS = (
    ('application_release', 'jenkins', 'ops', 'deployment', 'order-service', '订单服务构建与发布', '构建、单元测试和制品校验已完成，发布批次已记录。'),
    ('db_change', 'builtin-workorder', 'sqlaudit', 'sql_order', 'order-mysql-prod', '订单库索引变更', '订单查询索引变更已完成预检，执行耗时与影响行数已归档。'),
    ('config_change', 'gitlab', 'ops', 'config_release', 'gateway-prod', '网关路由配置更新', '合并请求已通过检查，路由配置版本与差异已归档。'),
    ('ops_transaction', 'jira', 'ops', 'transaction_ticket', 'platform-access', '生产访问权限申请流转', '值班人员已核对访问范围和有效期，审批与处理记录已关联。'),
    ('task_center', 'builtin-task-center', 'ops', 'host_task', 'node-health-check', '节点健康巡检完成', '巡检覆盖节点负载、磁盘容量和服务状态，执行结果已归档。'),
    ('application_release', 'argocd', 'ops', 'deployment', 'member-center', '会员服务版本同步', '应用期望版本与运行版本已完成比对，发布健康检查结果已归档。'),
)
SOURCE_TYPES = {
    'jenkins': ('Jenkins', 'jenkins'), 'gitlab': ('GitLab', 'gitlab'),
    'jira': ('Jira', 'jira'), 'argocd': ('ArgoCD', 'argocd'),
    'builtin-workorder': ('工单系统', 'builtin_workorder'),
    'builtin-task-center': ('任务中心', 'builtin_task'),
}


def refresh_events(*, hours=1, now=None, retention_days=14, environment='prod'):
    now = now or timezone.now()
    target_environment = resolve_event_environment(environment, strict=EventEnvironment.objects.filter(enabled=True).exists())
    if not target_environment['ok'] or not target_environment['code']:
        raise CommandError(target_environment['detail'] or '环境不能为空。')
    current_hour = timezone.localtime(now).replace(minute=0, second=0, microsecond=0)
    created = 0
    with transaction.atomic():
        # Lock the same source rows in the same order so concurrent timer/manual runs
        # cannot both insert an hour. No new schema or long-running worker is needed.
        for code in sorted(SOURCE_TYPES):
            name, source_type = SOURCE_TYPES[code]
            source, _ = EventSource.objects.get_or_create(code=code, defaults={
                'name': name, 'source_type': source_type,
                'source_kind': 'builtin' if code.startswith('builtin-') else 'external',
                'auth_type': 'webhook' if not code.startswith('builtin-') else 'none',
            })
            EventSource.objects.select_for_update().get(pk=source.pk)
        sources = {item.code: item for item in EventSource.objects.filter(code__in=SOURCE_TYPES)}
        for offset in range(hours - 1, -1, -1):
            hour = current_hour - timedelta(hours=offset)
            for index, (category, code, module, resource_type, resource, title, summary) in enumerate(SCENARIOS):
                identity = f'{GENERATOR}:{hour.isoformat()}:{code}:{category}'
                if EventRecord.objects.filter(correlation_id=identity).exists():
                    continue
                failed = (hour.hour + index) % 11 == 0
                result = 'failed' if failed else ('partial' if (hour.hour + index) % 7 == 0 else 'success')
                occurred_at = min(hour + timedelta(minutes=5 + index * 8), now)
                metadata = {
                    'generated_by': GENERATOR, 'event_category': category,
                    'event_source_code': code, 'event_source_type': sources[code].source_type,
                    'event_id': identity, 'environment_name': target_environment['name'],
                    'version': f'v2.{hour.day}.{hour.hour}',
                }
                if code == 'jenkins':
                    metadata.update(job_name='order-service-release', build_number=int(hour.timestamp()) // 3600,
                                    stage='部署验证', duration_ms=86000, branch='main',
                                    build_result='FAILURE' if failed else 'SUCCESS')
                elif code == 'gitlab':
                    metadata.update(project='platform/gateway-config', merge_request=hour.day * 100 + hour.hour,
                                    config_key='gateway.routes', branch='main')
                elif code == 'jira':
                    metadata.update(issue_key=f'OPS-{hour.day * 100 + hour.hour}', ticket_type='访问权限', owner='平台运维组')
                elif code == 'argocd':
                    metadata.update(sync_status='OutOfSync' if failed else 'Synced', health='Degraded' if failed else 'Healthy')
                elif category == 'db_change':
                    metadata.update(database='order_db', sql_type='CREATE INDEX', affected_rows=0, duration_ms=1842)
                else:
                    metadata.update(task_type='节点巡检', target='生产节点组', duration_ms=12500)
                EventRecord.objects.create(
                    occurred_at=occurred_at, module=module,
                    category='external_event' if sources[code].source_kind == 'external' else 'execution',
                    action=category, result=result, severity='danger' if failed else ('warning' if result == 'partial' else 'info'),
                    title=title if result == 'success' else title.replace('完成', '结果待复核') + ' · 检查待复核',
                    summary=summary if result == 'success' else '本次检查发现偏差，已保留执行上下文并通知值班队列复核。',
                    detail=summary, actor_type='system', actor_username=code, actor_display=sources[code].name,
                    source_type='external' if sources[code].source_kind == 'external' else 'scheduler',
                    resource_module=module, resource_type=resource_type, resource_id=resource,
                    resource_name=resource, business_line='电商线', environment=target_environment['code'],
                    application=resource if category == 'application_release' else '',
                    correlation_id=identity, metadata=metadata, tags=[category, target_environment['name']], is_demo=True,
                )
                created += 1
        for code, source in sources.items():
            latest = EventRecord.objects.filter(metadata__generated_by=GENERATOR, metadata__event_source_code=code).order_by('-occurred_at').values_list('occurred_at', flat=True).first()
            source.last_event_at = latest
            source.last_sync_at = now
            source.enabled = True
            source.status = 'healthy'
            source.last_error = ''
            # Local fixtures do not enable unauthenticated inbound webhook access.
            source.save(update_fields=['last_event_at', 'last_sync_at', 'enabled', 'status', 'last_error'])
        removed, _ = EventRecord.objects.filter(
            metadata__generated_by=GENERATOR, occurred_at__lt=now - timedelta(days=retention_days),
        ).delete()
        touch_event_environment(target_environment['code'], now)
    return created, removed


class Command(BaseCommand):
    help = '为已明确启用的展示环境补充每小时事件，保留最近 14 天；不会调用外部系统。'

    def add_arguments(self, parser):
        parser.add_argument('--hours', type=int, default=1)
        parser.add_argument('--environment', default='prod', help='事件中心已配置的环境标识或别名。')

    def handle(self, *args, **options):
        if os.environ.get('SXDEVOPS_SHOWCASE_EVENTS') != '1':
            raise CommandError('此命令仅用于明确启用 SXDEVOPS_SHOWCASE_EVENTS=1 的展示环境。')
        if not 1 <= options['hours'] <= 24:
            raise CommandError('--hours 必须在 1 到 24 之间。')
        created, removed = refresh_events(hours=options['hours'], environment=options['environment'])
        self.stdout.write(f'事件补充完成：新增 {created} 条，清理过期记录 {removed} 条。')
