"""Shared node diagnostics and bounded, read-only tool retries."""

import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

import requests
from django.utils import timezone

from .models import AIOpsGraphNodeRun, AIOpsPendingAction


_NODE_CONTEXT = ContextVar('aiops_graph_node', default=None)
_MODEL_AUDIT_CONTEXT = ContextVar('aiops_model_audit', default=None)
READ_ONLY_TOOLS = frozenset({
    'query_alerts', 'query_alert_metrics', 'query_alert_root_cause', 'query_logs', 'query_traces',
    'query_events', 'query_event_wall', 'query_system_posture', 'query_dashboard_metadata',
    'query_dashboard_panel_data', 'query_grafana_promql', 'query_knowledge_graph', 'query_workorders',
    'query_k8s_resources', 'query_k8s_cluster_summary', 'query_task_resources', 'query_hosts',
    'query_cmdb_items', 'query_cmdb_insights', 'query_cmdb_topology', 'query_cost_report',
})


class GraphNodeTimeout(TimeoutError):
    pass


def model_audit_scope():
    context = _NODE_CONTEXT.get()
    return dict(context.get('audit_scope') or {}) if context else dict(_MODEL_AUDIT_CONTEXT.get() or {})


@contextmanager
def compatibility_audit_scope(session, message, user):
    token = _MODEL_AUDIT_CONTEXT.set({'session_id': session.id, 'message_id': message.id, 'user_id': user.id})
    try:
        yield
    finally:
        _MODEL_AUDIT_CONTEXT.reset(token)


def bounded_timeout(seconds):
    context = _NODE_CONTEXT.get()
    if context is None:
        return seconds
    remaining = context['deadline'] - time.monotonic()
    if remaining <= 0:
        raise GraphNodeTimeout('LangGraph 节点时间预算已耗尽。')
    return min(float(seconds), remaining)


def transient_error(exc):
    return isinstance(exc, (requests.Timeout, requests.ConnectionError, ConnectionError)) and not isinstance(exc, GraphNodeTimeout)


def query_get(client, url, **kwargs):
    context = _NODE_CONTEXT.get()
    if context is None:
        return client.get(url, **kwargs)
    limit = min(max(int(os.getenv('AIOPS_LANGGRAPH_QUERY_RETRIES', '1')), 0), 3)
    while True:
        kwargs['timeout'] = bounded_timeout(kwargs.get('timeout') or 6)
        try:
            return client.get(url, **kwargs)
        except (requests.Timeout, requests.ConnectionError):
            if context['retries'] >= limit:
                raise
            context['retries'] += 1
            context['emit'](step={'title': '只读查询重试', 'status': 'running', 'detail': '数据源连接暂时失败'}, text='正在重试只读查询')


def run_tool(tool_name, invoke, *, external=False):
    context = _NODE_CONTEXT.get()
    if context is None:
        return invoke()
    retry_limit = min(max(int(os.getenv('AIOPS_LANGGRAPH_QUERY_RETRIES', '1')), 0), 3)
    safe = tool_name in READ_ONLY_TOOLS and not external
    for attempt in range(retry_limit + 1):
        bounded_timeout(1)
        try:
            result = invoke()
        except Exception as exc:
            if not safe or not transient_error(exc) or attempt >= retry_limit or context['retries'] >= retry_limit:
                raise
        else:
            output = result.get('tool_output') or {}
            if not (safe and isinstance(output, dict) and output.get('error')
                    and output.get('retryable') is True and attempt < retry_limit and context['retries'] < retry_limit):
                bounded_timeout(1)
                return result
        context['retries'] += 1
        context['emit'](tool_event={'name': tool_name, 'status': 'running', 'detail': '只读查询暂时失败，正在重试'},
                        text=f'重试 {tool_name}')


def finish_run(run, started, status, error='', retries=0):
    from .services import _sanitize_mcp_error_text

    run.status = status
    run.finished_at = timezone.now()
    run.duration_ms = max(int((time.monotonic() - started) * 1000), 0)
    run.retry_count = retries
    run.error = _sanitize_mcp_error_text(error)[:500] if error else ''
    run.save(update_fields=['status', 'finished_at', 'duration_ms', 'retry_count', 'error'])


def instrument_node(node, function):
    @wraps(function)
    def execute(state, config=None):
        from .langgraph_pilot import _callback_from_config
        from .services import ChatJobLeaseLost

        thread_id = str(((config or {}).get('configurable') or {}).get('thread_id') or state.get('thread_id') or '')
        run = AIOpsGraphNodeRun.objects.create(message_id=state['message_id'], thread_id=thread_id, node=node)
        started = time.monotonic()
        emit = _callback_from_config(config)
        context = {'deadline': started + max(float(os.getenv('AIOPS_LANGGRAPH_NODE_TIMEOUT_SECONDS', '180')), 1),
                   'retries': 0, 'emit': emit,
                   'audit_scope': {name: state.get(name) for name in ('session_id', 'message_id', 'user_id')}}
        token = _NODE_CONTEXT.set(context)
        try:
            emit(metadata_updates={'langgraph_current_node': {'node': node, 'status': 'running', 'run_id': run.id}})
            from .langgraph_formatter import attach_formatter, capture_formatter

            with capture_formatter(state) as capture:
                update = function(state, config)
                update = attach_formatter(update, capture)
            bounded_timeout(1)
            trace = update.get('trace') or []
            last = trace[-1] if trace and trace[-1].get('node') == node else {}
            status = last.get('status') or 'completed'
            detail = str(last.get('error') or last.get('reason') or '')
            finish_run(run, started, status, detail, context['retries'])
            emit(metadata_updates={'langgraph_current_node': {'node': node, 'status': status, 'run_id': run.id,
                                                              'duration_ms': run.duration_ms, 'retry_count': run.retry_count}})
            if last:
                update = {**update, 'trace': [*trace[:-1], {**last, 'duration_ms': run.duration_ms,
                                                          'retry_count': run.retry_count, 'run_id': run.id}]}
            return update
        except ChatJobLeaseLost:
            finish_run(run, started, 'interrupted', 'worker_lease_lost', context['retries'])
            raise
        except Exception as exc:
            finish_run(run, started, 'failed', str(exc), context['retries'])
            emit(metadata_updates={'langgraph_current_node': {'node': node, 'status': 'failed', 'run_id': run.id}})
            raise
        finally:
            _NODE_CONTEXT.reset(token)
    return execute


def instrument_action_node(node, function):
    @wraps(function)
    def execute(state, config=None):
        from langgraph.errors import GraphInterrupt

        action = AIOpsPendingAction.objects.get(pk=state['action_id'])
        if action.message_id is None:
            return function(state, config)
        thread_id = str(((config or {}).get('configurable') or {}).get('thread_id') or '')
        run = None
        if node == 'confirmation':
            run = AIOpsGraphNodeRun.objects.filter(
                message_id=action.message_id, thread_id=thread_id, node='action_confirmation', status='waiting',
            ).order_by('-id').first()
        if run is None:
            run = AIOpsGraphNodeRun.objects.create(
                message_id=action.message_id, thread_id=thread_id, node='action_' + node,
            )
        started = time.monotonic()
        try:
            result = function(state, config)
        except GraphInterrupt:
            run.status = 'waiting'
            run.save(update_fields=['status'])
            raise
        except Exception as exc:
            finish_run(run, started, 'failed', str(exc))
            raise
        else:
            finish_run(run, started, 'completed')
            return result
    return execute
