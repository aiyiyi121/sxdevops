from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ops.models import Alert, HostTask, HostTaskExecution

from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsKnowledgeEnvironment, AIOpsPendingAction, AIOpsRemediationVerification
from .remediation import bind_verification_task, configure_verification, process_verification


DEMO_ENVIRONMENT = '处置验证演示环境'
DEMO_CASES = [
    {'code': 'recovered', 'title': '任务成功且收到恢复事件', 'task_status': 'success', 'alert_status': 'resolved', 'expected': 'passed'},
    {'code': 'still_active', 'title': '任务成功但告警仍活跃', 'task_status': 'success', 'alert_status': 'active', 'expected': 'failed'},
    {'code': 'task_failed', 'title': '任务失败且告警仍活跃', 'task_status': 'failed', 'alert_status': 'active', 'expected': 'failed'},
    {'code': 'manually_closed', 'title': '告警被关闭但没有恢复事件', 'task_status': 'success', 'alert_status': 'closed', 'expected': 'inconclusive'},
    {'code': 'stale_recovery', 'title': '恢复事件早于本次任务', 'task_status': 'success', 'alert_status': 'resolved', 'expected': 'inconclusive'},
    {'code': 'missing_evidence', 'title': '原告警证据缺失', 'task_status': 'success', 'alert_status': 'missing', 'expected': 'inconclusive'},
]


@transaction.atomic
def seed_remediation_demo(user):
    if not user.is_active or not user.is_superuser:
        raise ValueError('请选择已有的有效管理员作为演示记录所有者。')
    environment, created = AIOpsKnowledgeEnvironment.objects.get_or_create(
        name=DEMO_ENVIRONMENT,
        defaults={'description': '仅用于处置验证评测；告警和任务均为演示记录，不连接真实资源。',
                  'alert_environments': ['aiops-remediation-demo'], 'created_by': user.username},
    )
    if not created and environment.alert_environments != ['aiops-remediation-demo']:
        raise ValueError('同名演示环境已被修改，请先核对环境用途。')
    records = []
    for case in DEMO_CASES:
        existing = AIOpsRemediationVerification.objects.filter(
            is_demo=True, action__session__user=user,
            action__session__context__remediation_demo_case=case['code'],
        ).first()
        if existing:
            records.append(existing)
            continue
        base = timezone.now() - timedelta(minutes=10)
        session = AIOpsChatSession.objects.create(
            user=user, title=f"[演示] {case['title']}",
            context={'remediation_demo_case': case['code'], 'knowledge_environment': environment.name},
        )
        question = AIOpsChatMessage.objects.create(
            session=session, role='user', content=f"[演示] 验证 order-service 处置效果：{case['title']}",
            metadata={'orchestration_engine': 'langgraph', 'orchestration_status': 'completed', 'is_demo': True},
        )
        thread_id = f'aiops-remediation-demo-chat-{question.id}'
        question.metadata['langgraph_thread_id'] = thread_id
        question.save(update_fields=['metadata'])
        assistant = AIOpsChatMessage.objects.create(
            session=session, role='assistant', content='演示任务与告警事件均为构造数据；下方验证由实际验证图执行，未运行远程命令。',
            metadata={'langgraph_thread_id': thread_id, 'is_demo': True},
        )
        action = AIOpsPendingAction.objects.create(
            session=session, message=assistant, action_type='execute_host_task',
            title=f"[演示] order-service 处置 · {case['title']}",
            action_payload={'name': '[演示] 服务恢复记录', 'request_summary': '演示记录，不执行真实命令'},
        )
        alert = Alert.objects.create(
            title=f"[演示] order-service 错误率 · {case['title']}", message='处置效果验证评测样本',
            source='aiops-remediation-demo', environment='aiops-remediation-demo', service='order-service',
            fingerprint=f'aiops-remediation-demo-{question.id}', starts_at=base - timedelta(minutes=5),
            last_received_at=base, status='active', labels={'remediation_demo': True},
        )
        verification = configure_verification(action, user, environment.id, alert.id, 0)
        verification.is_demo = True
        verification.baseline['captured_at'] = base.isoformat()
        verification.save(update_fields=['is_demo', 'baseline'])
        action.status = 'executed'
        action.confirmed_by = user.username
        action.confirmed_at = base + timedelta(seconds=5)
        action.save(update_fields=['status', 'confirmed_by', 'confirmed_at'])
        task = HostTask.objects.create(
            name=action.title, task_type='run_command', trigger_source='aiops', created_by=user.username,
            status=case['task_status'], lifecycle_status=case['task_status'], target_count=1,
            success_count=int(case['task_status'] == 'success'), failed_count=int(case['task_status'] == 'failed'),
            started_at=base + timedelta(seconds=10), finished_at=base + timedelta(seconds=20),
            source_context={'source': 'aiops', 'pending_action_id': action.id, 'session_id': session.id,
                            'remediation_demo': True, 'expected_verification': case['expected']},
            summary='演示执行记录；未连接主机或集群。',
        )
        HostTaskExecution.objects.create(
            task=task, host_name='demo-order-service', status=case['task_status'],
            output='演示执行记录；没有发出远程调用。', started_at=task.started_at, finished_at=task.finished_at,
        )
        bind_verification_task(action, task, user)
        action.result_payload = {'task_id': task.id, 'materialized_in_task_center': True, 'is_demo': True}
        action.save(update_fields=['result_payload'])
        if case['alert_status'] == 'missing':
            alert.delete()
        else:
            alert.status = case['alert_status']
            alert.ends_at = (base - timedelta(seconds=10) if case['code'] == 'stale_recovery'
                             else base + timedelta(seconds=30)) if alert.status == 'resolved' else None
            alert.last_received_at = base + timedelta(seconds=30)
            alert.save(update_fields=['status', 'ends_at', 'last_received_at'])
        records.append(verification)
    return records


def evaluate_remediation_demo(user):
    results = []
    for case in DEMO_CASES:
        verification = AIOpsRemediationVerification.objects.filter(
            is_demo=True, action__session__user=user,
            action__session__context__remediation_demo_case=case['code'],
        ).select_related('task').first()
        if verification and verification.status == 'waiting':
            from uuid import uuid4
            token = uuid4()
            claimed = AIOpsRemediationVerification.objects.filter(pk=verification.pk, status='waiting').update(
                status='running', claim_token=token, lease_until=timezone.now() + timedelta(seconds=120),
                attempt_count=1,
            )
            if claimed:
                verification.refresh_from_db()
                process_verification(verification)
                verification.refresh_from_db()
        actual = verification.status if verification else 'missing'
        results.append({'case': case['code'], 'title': case['title'], 'expected': case['expected'],
                        'actual': actual, 'matched': actual == case['expected'],
                        'session_id': verification.action.session_id if verification else None})
    return {'total': len(results), 'matched': sum(item['matched'] for item in results), 'cases': results}
