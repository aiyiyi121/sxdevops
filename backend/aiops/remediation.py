import os
import uuid
from datetime import timedelta
from typing import TypedDict

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from eventwall.models import EventRecord
from eventwall.services import record_event
from ops.models import Alert, HostTask
from rbac.services import user_has_permissions

from .models import AIOpsGraphNodeRun, AIOpsKnowledgeEnvironment, AIOpsPendingAction, AIOpsRemediationVerification
from .verification_health import collect_signal, observation_end, prepare_health_policy, require_health_access


VERIFICATION_GRAPH_VERSION = 2
VERIFICATION_PERMISSIONS = ('aiops.chat.analyze', 'ops.alert.view')
TERMINAL_TASK_STATUSES = ('success', 'partial', 'failed', 'canceled')


class VerificationState(TypedDict, total=False):
    verification_id: int
    graph_version: int
    session_id: int
    message_id: int
    user_id: int
    thread_id: str
    task_evidence: dict
    alert_evidence: dict
    health_evidence: dict
    result: dict
    trace: list


def _snapshot(alert):
    return {
        'id': alert.id, 'title': alert.title, 'status': alert.status,
        'fingerprint': alert.fingerprint, 'environment': alert.environment,
        'service': alert.service,
        **{field: getattr(alert, field).isoformat() if getattr(alert, field) else None
           for field in ('starts_at', 'ends_at', 'last_received_at')},
    }


def _require_access(verification, user=None):
    user = user or verification.action.session.user
    if not user.is_active or not user_has_permissions(user, VERIFICATION_PERMISSIONS):
        raise PermissionDenied('当前账号无权读取验证证据。')
    environment = verification.environment
    baseline = verification.baseline
    if (not environment or not environment.is_enabled
            or sorted(environment.alert_environments) != sorted(baseline.get('alert_environments') or [])):
        raise PermissionDenied('知识环境或告警关联已变化，请重新核对验证范围。')
    require_health_access(baseline, environment, user)
    return user


@transaction.atomic
def configure_verification(action, user, environment_id, alert_id, observation_seconds=60, health_policy=None):
    if not user.is_active or not user_has_permissions(user, VERIFICATION_PERMISSIONS):
        raise PermissionDenied('当前账号无权配置效果验证。')
    if not isinstance(observation_seconds, int) or not 0 <= observation_seconds <= 600:
        raise ValueError('观察窗口必须为 0 到 600 秒。')
    action = AIOpsPendingAction.objects.select_for_update().select_related('session').get(pk=action.pk)
    if action.session.user_id != user.id or action.mirror_source_id:
        raise PermissionDenied('只能配置本人原始会话的效果验证。')
    if action.action_type != AIOpsPendingAction.ACTION_EXECUTE_HOST_TASK or not action.message_id:
        raise ValueError('只有任务处置支持效果验证。')
    if action.status not in (AIOpsPendingAction.STATUS_PENDING, AIOpsPendingAction.STATUS_EXECUTED):
        raise ValueError('当前动作不可配置验证。')
    if (action.result_payload or {}).get('materialized_in_task_center'):
        raise ValueError('请在任务创建执行前配置验证，以保存处置前证据。')
    existing = AIOpsRemediationVerification.objects.filter(action=action).first()
    if existing:
        if (existing.environment_id == environment_id and existing.baseline.get('alert', {}).get('id') == alert_id
                and existing.observation_seconds == observation_seconds
                and existing.baseline.get('health_request', {}) == (health_policy or {})):
            return existing
        raise ValueError('本次动作已有验证基线，请保留原始证据。')
    environment = AIOpsKnowledgeEnvironment.objects.filter(pk=environment_id, is_enabled=True).first()
    if not environment or not environment.alert_environments:
        raise ValueError('请选择已关联告警环境的知识环境。')
    alert = Alert.objects.filter(pk=alert_id, environment__in=environment.alert_environments).first()
    if not alert or alert.status != Alert.STATUS_ACTIVE:
        raise ValueError('请选择该环境内当前活跃的告警。')
    captured_at = timezone.now()
    health = prepare_health_policy(health_policy, environment, user, observation_seconds, captured_at, _snapshot, alert)
    verification = AIOpsRemediationVerification.objects.create(
        action=action, environment=environment,
        thread_id=f'aiops-verification-{action.id}-{uuid.uuid4().hex}',
        observation_seconds=observation_seconds,
        baseline={
            'environment_name': environment.name, 'alert_environments': list(environment.alert_environments),
            'captured_at': captured_at.isoformat(), 'alert': _snapshot(alert),
            'health_request': health_policy or {}, 'health_policy': health,
        },
        summary='已保存处置前告警证据，等待在任务中心创建并执行任务。',
    )
    record_event(
        module='aiops', category='execution', action='configure_verification',
        title='配置处置效果验证', summary=f'动作 #{action.id} 已保存告警 #{alert.id} 的验证基线',
        resource_type='aiops_verification', resource_id=verification.id,
        actor_username=user.username, correlation_id=verification.thread_id,
        is_demo=bool((alert.labels or {}).get('remediation_demo')),
    )
    return verification


def bind_verification_task(action, task, user):
    if (task.created_by != user.username or action.session.user_id != user.id
            or not action.confirmed_at or action.confirmed_by != user.username
            or action.status != AIOpsPendingAction.STATUS_EXECUTED
            or task.trigger_source != HostTask.TRIGGER_SOURCE_AIOPS
            or str((task.source_context or {}).get('pending_action_id')) != str(action.id)):
        return
    AIOpsRemediationVerification.objects.filter(
        action=action, task__isnull=True, status=AIOpsRemediationVerification.STATUS_WAITING,
    ).update(task=task, summary='等待任务完成及观察窗口结束后自动验证。', updated_at=timezone.now())


def _verification(state):
    verification = AIOpsRemediationVerification.objects.select_related(
        'action__session__user', 'environment', 'task',
    ).get(pk=state['verification_id'])
    _require_access(verification)
    return verification


def _scope_node(state, config=None):
    verification = _verification(state)
    if verification.is_demo != bool((verification.task.source_context or {}).get('remediation_demo')):
        raise ValueError('演示验证与真实任务不能混用。')
    return {'trace': [*state.get('trace', []), {'node': 'verification_scope', 'status': 'completed'}]}


def _task_node(state, config=None):
    task = _verification(state).task
    if not task or task.status not in TERMINAL_TASK_STATUSES or not task.finished_at:
        raise ValueError('任务尚未结束，不能验证恢复效果。')
    return {'task_evidence': {
        'id': task.id, 'status': task.status, 'success_count': task.success_count,
        'failed_count': task.failed_count, 'skipped_count': task.skipped_count,
        'target_count': task.target_count, 'execution_count': task.executions.count(),
        'successful_executions': task.executions.filter(status='success').count(),
        'started_at': task.started_at.isoformat() if task.started_at else None,
        'finished_at': task.finished_at.isoformat(),
    }}


def _alert_node(state, config=None):
    verification = _verification(state)
    baseline = verification.baseline
    alert = Alert.objects.filter(
        pk=(baseline.get('alert') or {}).get('id'), environment__in=baseline['alert_environments'],
    ).first()
    policy = baseline.get('health_policy') or {}
    related = list(Alert.objects.filter(
        pk__in=[row['id'] for row in policy.get('related_alerts') or []],
        environment__in=baseline['alert_environments'],
    ).order_by('id'))
    end = observation_end(verification, timezone.now())
    start = end - timedelta(seconds=verification.observation_seconds)
    health = {'related_alerts': [_snapshot(row) for row in related], 'signals': [],
              'window_start': start.isoformat(), 'window_end': end.isoformat()}
    if policy and timezone.now() < end:
        raise ValueError('告警恢复后的完整观察窗口尚未结束，不能提前判定健康。')
    for signal in policy.get('signals') or []:
        try:
            health['signals'].append(collect_signal(signal, start, end))
        except Exception:
            health['signals'].append({'name': signal['name'], 'status': 'inconclusive', 'error': '指标查询失败'})
    return {'alert_evidence': _snapshot(alert) if alert else {}, 'health_evidence': health}


def _verdict_node(state, config=None):
    verification = _verification(state)
    baseline = verification.baseline
    task = state.get('task_evidence') or {}
    alert = state.get('alert_evidence') or {}
    status = AIOpsRemediationVerification.STATUS_INCONCLUSIVE
    summary = '未取得同一告警的有效恢复证据，不能确认恢复。'
    started = parse_datetime(task.get('started_at') or '')
    captured = parse_datetime(baseline.get('captured_at') or '')
    ended = parse_datetime(alert.get('ends_at') or '')
    received = parse_datetime(alert.get('last_received_at') or '')
    if (task.get('status') != HostTask.STATUS_SUCCESS or task.get('failed_count') or task.get('skipped_count')
            or not task.get('target_count') or task.get('success_count') != task.get('target_count')
            or task.get('successful_executions') != task.get('target_count')
            or task.get('execution_count') != task.get('target_count')):
        status, summary = AIOpsRemediationVerification.STATUS_FAILED, '任务未全部成功，处置验证未通过；请检查任务执行记录。'
    elif not started or not captured or started < captured:
        summary = '缺少有效的处置前基线或任务开始时间，不能确认恢复。'
    elif alert and alert.get('fingerprint') != baseline['alert'].get('fingerprint'):
        summary = '告警指纹发生变化，不能使用其他告警事件证明本次恢复。'
    elif alert and alert.get('status') == Alert.STATUS_ACTIVE:
        status, summary = AIOpsRemediationVerification.STATUS_FAILED, '观察窗口结束后告警仍活跃，尚未观察到恢复。'
    elif (alert.get('status') == Alert.STATUS_RESOLVED and ended and received
          and started <= ended <= timezone.now() and started <= received <= timezone.now()):
        status = AIOpsRemediationVerification.STATUS_PASSED
        summary = '平台已收到该告警在任务开始后的恢复事件；此结果不证明处置因果或业务整体健康。'
    elif alert.get('status') in (Alert.STATUS_CLOSED, Alert.STATUS_MUTED):
        summary = '告警被关闭或屏蔽，不能据此判定故障恢复。'
    health = state.get('health_evidence') or {}
    policy = baseline.get('health_policy') or {}
    if status == AIOpsRemediationVerification.STATUS_PASSED and policy:
        related = {row['id']: row for row in health.get('related_alerts') or []}
        for before in policy.get('related_alerts') or []:
            after = related.get(before['id'], {})
            if after.get('status') == Alert.STATUS_ACTIVE:
                status, summary = 'failed', '关联告警仍活跃，多信号验证未通过。'
                break
            if after.get('fingerprint') != before['fingerprint'] or after.get('status') != Alert.STATUS_RESOLVED:
                status, summary = 'inconclusive', '关联告警缺失、已变更或被人工关闭，健康证据不足。'
                break
            related_ended = parse_datetime(after.get('ends_at') or '')
            related_received = parse_datetime(after.get('last_received_at') or '')
            if (not related_ended or not related_received or related_ended > timezone.now()
                    or related_received > timezone.now()
                    or (before.get('status') == Alert.STATUS_ACTIVE
                        and (related_ended < started or related_received < started))):
                status, summary = 'inconclusive', '关联告警缺少有效恢复时间，健康证据不足。'
                break
        if status == 'passed':
            results = health.get('signals') or []
            if len(results) != len(policy.get('signals') or []) or any(row['status'] == 'inconclusive' for row in results):
                status, summary = 'inconclusive', '观察窗口存在缺失、非有限值或查询失败，不能判定持续达标。'
            elif any(row['status'] == 'unhealthy' for row in results):
                status, summary = 'failed', '观察窗口内至少一个指标采样未达阈值，多信号验证未通过。'
            elif health.get('signals'):
                summary = '告警已恢复，配置的指标在完整观察窗口的每个采样点均达标；结果不证明处置因果或未观测业务健康。'
            else:
                summary = '主告警及配置的关联告警均已恢复；结果不证明持续指标达标、处置因果或未观测业务健康。'
    causality = {'assessment': 'temporal_association_only', 'causal_proof': False,
                 'action_id': verification.action_id, 'task_id': verification.task_id,
                 'baseline_captured_at': baseline.get('captured_at'), 'task_started_at': task.get('started_at'),
                 'alert_recovered_at': alert.get('ends_at'),
                 'review_required': '需结合任务目标、同期变更及独立业务证据复核归因；不能排除自发恢复或其他干预。'}
    return {'result': {'status': status, 'summary': summary, 'task': task, 'alert': alert,
                       'health': health, 'causality': causality}}


def get_verification_graph():
    from langgraph.graph import END, START, StateGraph
    from .langgraph_execution import instrument_node
    from .langgraph_pilot import _get_checkpointer

    builder = StateGraph(VerificationState)
    nodes = [
        ('verification_scope', _scope_node), ('verification_task', _task_node),
        ('verification_alert', _alert_node), ('verification_verdict', _verdict_node),
    ]
    previous = START
    for name, handler in nodes:
        builder.add_node(name, instrument_node(name, handler))
        builder.add_edge(previous, name)
        previous = name
    builder.add_edge(previous, END)
    return builder.compile(checkpointer=_get_checkpointer())


def claim_verification(lease_seconds=120):
    now = timezone.now()
    AIOpsRemediationVerification.objects.filter(
        Q(status='waiting') | Q(status='running', lease_until__lt=now),
        task__isnull=True, action__result_payload__materialized_in_task_center=True,
    ).update(status='inconclusive', summary='关联任务已不存在，无法验证处置效果。',
             finished_at=now, updated_at=now, claim_token=None, lease_until=None)
    candidates = AIOpsRemediationVerification.objects.filter(
        Q(status='waiting', task__status__in=TERMINAL_TASK_STATUSES)
        | Q(status='running', lease_until__lt=now),
    ).select_related('task').order_by('created_at', 'id')[:100]
    for candidate in candidates:
        if (not candidate.task or not candidate.task.finished_at
                or observation_end(candidate, now) > now):
            continue
        token = uuid.uuid4()
        claimed = AIOpsRemediationVerification.objects.filter(pk=candidate.pk).filter(
            Q(status='waiting') | Q(status='running', lease_until__lt=now),
        ).update(status='running', claim_token=token, lease_until=now + timedelta(seconds=lease_seconds),
                 attempt_count=F('attempt_count') + 1, updated_at=now)
        if claimed:
            return AIOpsRemediationVerification.objects.get(pk=candidate.pk)
    return None


def process_verification(verification):
    from .services import ChatJobLeaseLost
    verification_id, claim_token = verification.pk, verification.claim_token

    def owned():
        return AIOpsRemediationVerification.objects.filter(
            pk=verification_id, status='running', claim_token=claim_token,
            lease_until__gt=timezone.now(),
        )

    def check_lease(**kwargs):
        if not claim_token or not owned().exists():
            raise ChatJobLeaseLost('效果验证租约已失效。')

    try:
        check_lease()
        verification = _verification({'verification_id': verification.id})
        graph = get_verification_graph()
        config = {'configurable': {'thread_id': verification.thread_id, 'progress_callback': check_lease}}
        snapshot = graph.get_state(config)
        if snapshot.values and snapshot.values.get('graph_version') != VERIFICATION_GRAPH_VERSION:
            raise ValueError('验证图版本已变化，不能恢复旧验证。')
        initial = None if snapshot.values else {
            'verification_id': verification.id, 'graph_version': VERIFICATION_GRAPH_VERSION,
            'session_id': verification.action.session_id, 'message_id': verification.action.message_id,
            'user_id': verification.action.session.user_id, 'thread_id': verification.thread_id, 'trace': [],
        }
        final = snapshot.values if snapshot.values and not snapshot.next else graph.invoke(initial, config=config)
        _verification({'verification_id': verification.id})
        result = final['result']
        current_alert = Alert.objects.filter(pk=verification.baseline['alert']['id']).first()
        related_ids = [row['id'] for row in (verification.baseline.get('health_policy') or {}).get('related_alerts') or []]
        current_related = [_snapshot(row) for row in Alert.objects.filter(pk__in=related_ids).order_by('id')]
        if (_task_node(final)['task_evidence'] != result['task']
                or (_snapshot(current_alert) if current_alert else {}) != result['alert']
                or current_related != (result.get('health') or {}).get('related_alerts', [])):
            result = {'status': 'inconclusive', 'summary': '验证期间任务或告警发生变化，请重新核对当前证据。', 'task': {}, 'alert': {}}
    except ChatJobLeaseLost:
        return
    except Exception as exc:
        from .audit_executions import safe_error
        result = {'status': 'inconclusive', 'summary': safe_error(exc), 'task': {}, 'alert': {}}
    try:
        check_lease()
    except ChatJobLeaseLost:
        return
    with transaction.atomic():
        changed = owned().update(
            status=result['status'], summary=result['summary'], evidence={
                'task': result['task'], 'alert': result['alert'],
                'health': result.get('health', {}), 'causality': result.get('causality', {}),
            },
            finished_at=timezone.now(), claim_token=None, lease_until=None, updated_at=timezone.now(),
        )
        if changed:
            record_event(
                module='aiops', category='execution', action='verify_remediation', title='处置效果验证完成',
                summary=result['summary'], resource_type='aiops_verification', resource_id=verification.id,
                actor_username=verification.action.session.user.username, correlation_id=verification.thread_id,
                metadata={'status': result['status'], 'task_id': verification.task_id, 'is_demo': verification.is_demo},
                is_demo=verification.is_demo,
                result=EventRecord.RESULT_FAILED if result['status'] == 'failed' else EventRecord.RESULT_SUCCESS,
                severity=EventRecord.SEVERITY_INFO if result['status'] == 'passed' else EventRecord.SEVERITY_WARNING,
            )


def verification_details(verification, user):
    data = {
        'id': verification.id, 'status': verification.status, 'status_label': verification.get_status_display(),
        'task_id': verification.task_id, 'is_demo': verification.is_demo,
        'observation_seconds': verification.observation_seconds, 'attempt_count': verification.attempt_count,
        'finished_at': verification.finished_at, 'checkpoint_expired': verification.checkpoint_expired,
    }
    try:
        _require_access(verification, user)
    except PermissionDenied:
        return {**data, 'summary': '当前权限或环境关联不允许读取验证证据。', 'baseline': {}, 'evidence': {}, 'nodes': []}
    runs = AIOpsGraphNodeRun.objects.filter(thread_id=verification.thread_id).order_by('id')
    return {**data, 'summary': verification.summary, 'baseline': verification.baseline, 'evidence': verification.evidence,
            'nodes': list(runs.values('node', 'status', 'duration_ms', 'started_at', 'finished_at')[:100])}


def cleanup_verifications():
    from .langgraph_pilot import _get_checkpointer

    cutoff = timezone.now() - timedelta(days=max(int(os.getenv('AIOPS_LANGGRAPH_RETENTION_DAYS', '30')), 1))
    candidates = AIOpsRemediationVerification.objects.filter(
        finished_at__lt=cutoff, checkpoint_expired=False,
    ).exclude(status__in=['waiting', 'running']).order_by('id')[:100]
    for verification in candidates:
        _get_checkpointer().delete_thread(verification.thread_id)
        AIOpsGraphNodeRun.objects.filter(thread_id=verification.thread_id).delete()
        AIOpsRemediationVerification.objects.filter(pk=verification.pk).update(checkpoint_expired=True)
