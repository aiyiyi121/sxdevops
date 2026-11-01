from django.db.models import Case, CharField, Count, Max, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Cast, Coalesce
from django.db.models.fields.json import KeyTextTransform
from django.utils import timezone
from rest_framework import serializers

from .models import AIOpsChatJob, AIOpsChatMessage, AIOpsGraphNodeRun, AIOpsModelInvocation, AIOpsPendingAction, AIOpsToolInvocation


def execution_queryset():
    jobs = AIOpsChatJob.objects.filter(user_message_id=OuterRef('pk')).order_by('-id')
    graphs = AIOpsGraphNodeRun.objects.filter(message_id=OuterRef('pk'), node='__graph__').order_by('-id')
    assistants = AIOpsChatMessage.objects.filter(
        session_id=OuterRef('session_id'), role='assistant', mirror_source__isnull=True,
    ).annotate(
        orchestration_user_message_id_text=KeyTextTransform('orchestration_user_message_id', 'metadata'),
        resume_status=KeyTextTransform('langgraph_resume_status', 'metadata'),
    ).filter(
        Q(metadata__langgraph_thread_id=OuterRef('metadata__langgraph_thread_id'))
        | Q(orchestration_user_message_id_text=Cast(OuterRef('pk'), output_field=CharField())),
    ).order_by('-id')
    nodes = Q(graph_node_runs__node='__graph__')
    return AIOpsChatMessage.objects.filter(
        role='user', mirror_source__isnull=True, session__mirror_source__isnull=True,
    ).filter(
        (Q(metadata__langgraph_thread_id__isnull=False) & ~Q(metadata__langgraph_thread_id=''))
        | Q(metadata__orchestration_degraded=True),
    ).select_related('session__user').annotate(
        execution_status=Coalesce(
            Subquery(jobs.values('status')[:1]), KeyTextTransform('orchestration_status', 'metadata'),
            Subquery(graphs.values('status')[:1]),
            Subquery(assistants.values('resume_status')[:1]),
            Case(When(metadata__langgraph_checkpoint_expired=True, then=Value('completed')), default=Value('unknown')),
            output_field=CharField(),
        ),
        assistant_message_id=Subquery(assistants.values('id')[:1]),
        node_count=Count('graph_node_runs', filter=~nodes),
        failed_node_count=Count('graph_node_runs', filter=~nodes & Q(graph_node_runs__status='failed')),
        node_duration_ms=Coalesce(Sum('graph_node_runs__duration_ms', filter=~nodes), 0),
        graph_duration_ms=Coalesce(Sum('graph_node_runs__duration_ms', filter=nodes), 0),
        node_retry_count=Coalesce(Sum('graph_node_runs__retry_count', filter=~nodes), 0),
        last_node_at=Max('graph_node_runs__started_at'),
        last_finished_at=Max('graph_node_runs__finished_at'),
        last_job_at=Subquery(jobs.values('updated_at')[:1]),
    ).order_by('-created_at', '-id')


def safe_error(value):
    if not value:
        return ''
    from .services import _sanitize_mcp_error_text
    return _sanitize_mcp_error_text(value)[:500]


class AIOpsAuditExecutionSerializer(serializers.BaseSerializer):
    def to_representation(self, message):
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        return {
            'id': message.id,
            'message_id': message.id,
            'assistant_message_id': message.assistant_message_id,
            'session_id': message.session_id,
            'session_title': message.session.title,
            'username': message.session.user.username,
            'question': message.content[:240],
            'thread_id': str(metadata.get('langgraph_thread_id') or ''),
            'orchestration_engine': metadata.get('orchestration_engine') or 'langgraph',
            'orchestration_degraded': bool(metadata.get('orchestration_degraded')),
            'status': message.execution_status,
            'created_at': message.created_at,
            'updated_at': max(item for item in [message.created_at, message.last_node_at, message.last_finished_at, message.last_job_at] if item),
            'node_count': message.node_count,
            'failed_node_count': message.failed_node_count,
            'node_duration_ms': message.node_duration_ms,
            'graph_duration_ms': message.graph_duration_ms,
            'retry_count': message.node_retry_count,
            'resume_count': metadata.get('langgraph_resume_count', 0),
            'checkpoint_expired': bool(metadata.get('langgraph_checkpoint_expired')),
            'checkpoint_cleanup_pending': bool(metadata.get('langgraph_checkpoint_cleanup_pending')),
        }


def execution_detail(message):
    data = AIOpsAuditExecutionSerializer(message).data
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    thread_id = data['thread_id']
    checkpoint = {'status': 'missing', 'graph_version': None, 'next': [], 'created_at': None}
    if data['orchestration_degraded']:
        checkpoint['status'] = 'degraded'
    elif metadata.get('langgraph_checkpoint_cleanup_pending'):
        checkpoint['status'] = 'cleanup_pending'
    elif metadata.get('langgraph_checkpoint_expired'):
        checkpoint['status'] = 'expired'
    else:
        try:
            from .langgraph_pilot import get_langgraph_chat_graph
            snapshot = get_langgraph_chat_graph().get_state({'configurable': {'thread_id': thread_id}})
            if snapshot and snapshot.values:
                checkpoint.update({
                    'status': 'available',
                    'graph_version': snapshot.values.get('graph_version'),
                    'next': [str(node)[:64] for node in snapshot.next or ()],
                    'created_at': snapshot.created_at,
                })
        except Exception:
            checkpoint['status'] = 'unavailable'
    checkpoint['expired_at'] = metadata.get('langgraph_checkpoint_expired_at')
    job = AIOpsChatJob.objects.filter(user_message=message, thread_id=thread_id).order_by('-id').first()
    data['job'] = None if job is None else {
        'id': job.id, 'status': job.status, 'attempt_count': job.attempt_count,
        'analysis_only': job.analysis_only, 'lease_until': job.lease_until,
        'lease_expired': bool(job.status == 'running' and job.lease_until and job.lease_until <= timezone.now()),
        'error': safe_error(job.error_message), 'updated_at': job.updated_at,
    }
    runs = list(AIOpsGraphNodeRun.objects.filter(message=message, thread_id=thread_id).order_by('-id')[:501])
    data['nodes_truncated'] = len(runs) > 500
    data['nodes'] = [{
        'id': run.id, 'node': run.node, 'status': run.status,
        'started_at': run.started_at, 'finished_at': run.finished_at,
        'duration_ms': run.duration_ms, 'retry_count': run.retry_count,
        'error': safe_error(run.error) if run.status in ['failed', 'interrupted', 'blocked'] else '',
    } for run in reversed(runs[:500])]
    data['checkpoint'] = checkpoint
    data['tool_count'] = AIOpsToolInvocation.objects.filter(session_id=message.session_id, message=message).count()
    data['model_count'] = AIOpsModelInvocation.objects.filter(session_id=message.session_id, message=message).count()
    data['actions'] = action_execution_details(message, thread_id)
    return data


def action_execution_details(message, thread_id):
    from .langgraph_pilot import _action_graph_config

    related = Q(message_id=message.id) | Q(message__metadata__orchestration_user_message_id=message.id)
    if thread_id:
        related |= Q(message__metadata__langgraph_thread_id=thread_id)
    actions = AIOpsPendingAction.objects.filter(
        related, session_id=message.session_id, mirror_source__isnull=True,
    ).order_by('-id')[:50]
    result = []
    for action in actions:
        action_thread = _action_graph_config(action)['configurable']['thread_id']
        runs = list(AIOpsGraphNodeRun.objects.filter(
            message_id=action.message_id, thread_id=action_thread,
        ).order_by('-id')[:101])
        nodes = []
        for run in reversed(runs[:100]):
            finish = run.finished_at
            status = run.status
            if status == 'waiting' and action.status == AIOpsPendingAction.STATUS_CANCELED:
                finish, status = action.updated_at, 'canceled'
            elapsed = max(int(((finish or timezone.now()) - run.started_at).total_seconds() * 1000), 0)
            nodes.append({
                'id': run.id, 'node': run.node, 'status': status,
                'started_at': run.started_at, 'finished_at': finish, 'duration_ms': run.duration_ms,
                'waiting_ms': max(elapsed - run.duration_ms, 0) if run.node == 'action_confirmation' else 0,
                'error': safe_error(run.error) if status == 'failed' else '',
            })
        result.append({
            'id': action.id, 'title': action.title, 'status': action.status, 'action_type': action.action_type,
            'status_label': action.get_status_display(), 'thread_id': action_thread,
            'nodes': nodes, 'nodes_truncated': len(runs) > 100,
        })
    return result
