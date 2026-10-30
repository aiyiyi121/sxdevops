"""Runtime diagnostics and conservative checkpoint retention."""

import os
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from .models import AIOpsChatJob, AIOpsChatMessage, AIOpsGraphNodeRun, AIOpsPendingAction, AIOpsRemediationVerification


def runtime_summary(thread_id):
    runs = AIOpsGraphNodeRun.objects.filter(thread_id=thread_id).exclude(node='__graph__')
    totals = runs.aggregate(node_runs=Count('id'), duration_ms=Sum('duration_ms'), retries=Sum('retry_count'))
    totals['failed_nodes'] = runs.filter(status='failed').count()
    totals['interrupted_nodes'] = runs.filter(status='interrupted').count()
    message = AIOpsChatMessage.objects.filter(metadata__langgraph_thread_id=thread_id).first()
    totals['resume_count'] = (message.metadata or {}).get('langgraph_resume_count', 0) if message else 0
    totals['checkpoint_expired'] = bool(message and (message.metadata or {}).get('langgraph_checkpoint_expired'))
    return totals


def cleanup_checkpoints(*, retention_days=None, limit=100, apply=False):
    from .langgraph_pilot import _action_graph_config, _get_checkpointer, get_langgraph_chat_graph

    days = int(retention_days if retention_days is not None else os.getenv('AIOPS_LANGGRAPH_RETENTION_DAYS', '30'))
    if days < 1 or limit < 1:
        raise ValueError('保留天数和清理数量必须大于零。')
    cutoff = timezone.now() - timedelta(days=days)
    candidates = AIOpsChatMessage.objects.filter(role='user', created_at__lt=cutoff,
                                                metadata__has_key='langgraph_thread_id').order_by('id')
    result = {'eligible': [], 'deleted': [], 'skipped': 0}
    scanned = 0
    for candidate in candidates.iterator(chunk_size=100):
        if len(result['eligible']) >= limit or scanned >= limit * 10:
            break
        scanned += 1
        with transaction.atomic():
            message = AIOpsChatMessage.objects.select_for_update().get(pk=candidate.pk)
            metadata = dict(message.metadata or {})
            thread_id = metadata.get('langgraph_thread_id')
            if not thread_id or (metadata.get('langgraph_checkpoint_expired') and not metadata.get('langgraph_checkpoint_cleanup_pending')):
                continue
            jobs = list(AIOpsChatJob.objects.select_for_update().filter(user_message=message))
            recent_run = message.graph_node_runs.aggregate(latest=Max('started_at'))['latest']
            recent_action = AIOpsGraphNodeRun.objects.filter(
                message__session_id=message.session_id, node__in=['action_review', 'action_confirmation', 'action_execute'],
            ).filter(Q(started_at__gte=cutoff) | Q(finished_at__gte=cutoff) | Q(status='running')).exists()
            busy = any(job.status in ['queued', 'running'] or job.updated_at >= cutoff for job in jobs)
            verification_busy = AIOpsRemediationVerification.objects.filter(
                action__session_id=message.session_id, status__in=['waiting', 'running'],
            ).exists()
            if (busy or verification_busy or recent_action or (recent_run and recent_run >= cutoff)
                    or AIOpsPendingAction.objects.filter(session_id=message.session_id, status__in=['pending', 'confirmed']).exists()):
                result['skipped'] += 1
                continue
            snapshot = get_langgraph_chat_graph().get_state({'configurable': {'thread_id': thread_id}})
            if not metadata.get('langgraph_checkpoint_cleanup_pending') and (
                    not snapshot.values or snapshot.next or snapshot.values.get('status') != 'completed'):
                result['skipped'] += 1
                continue
            result['eligible'].append(thread_id)
            if not apply:
                continue
            metadata['langgraph_checkpoint_expired'] = True
            metadata['langgraph_checkpoint_cleanup_pending'] = True
            metadata['langgraph_checkpoint_expired_at'] = timezone.now().isoformat()
            message.metadata = metadata
            message.save(update_fields=['metadata'])
        _get_checkpointer().delete_thread(thread_id)
        actions = AIOpsPendingAction.objects.filter(session_id=message.session_id, status__in=['executed', 'canceled', 'failed']).filter(
            Q(message__metadata__langgraph_thread_id=thread_id) | Q(message_id__in=[job.assistant_message_id for job in jobs]),
        )
        for action in actions:
            action_thread = _action_graph_config(action)['configurable']['thread_id']
            _get_checkpointer().delete_thread(action_thread)
            AIOpsGraphNodeRun.objects.filter(message_id=action.message_id, thread_id=action_thread).delete()
        message.graph_node_runs.all().delete()
        message.refresh_from_db()
        message.metadata = {**message.metadata, 'langgraph_checkpoint_cleanup_pending': False}
        message.save(update_fields=['metadata'])
        result['deleted'].append(thread_id)
    return result
