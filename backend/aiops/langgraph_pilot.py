"""LangGraph orchestration for default AIOps chat and read-only investigation.

The graphs own orchestration state and branching. The existing AIOps tool
runtime owns permissions, resource scoping and tool-call audit records.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, TypedDict

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from .models import AIOpsChatMessage, AIOpsChatSession, AIOpsPendingAction
from .services import (
    _build_analysis_scope,
    get_agent_config,
    _resolve_knowledge_environment_for_query,
    _run_tool_call,
    _platform_tool_registry_entry,
)

try:  # Keep the rest of AIOps usable before the optional pilot dependency is installed.
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt
except ImportError:  # pragma: no cover - exercised in environments without the extra.
    SqliteSaver = None
    END = START = StateGraph = None
    Command = interrupt = None

try:
    from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
except ImportError:  # pragma: no cover - local SQLite pilot installations.
    PyMySQLSaver = None


if PyMySQLSaver is not None:
    class _SxPyMySQLSaver(PyMySQLSaver):
        @staticmethod
        def _select_sql(where: str) -> str:
            query = PyMySQLSaver._select_sql(where)
            return query.replace(
                "VARCHAR(150) CHARACTER SET utf8mb4 PATH '$'",
                "VARCHAR(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci PATH '$'",
            )
else:  # pragma: no cover - local SQLite pilot installations.
    _SxPyMySQLSaver = None


LANGGRAPH_AVAILABLE = StateGraph is not None and SqliteSaver is not None
CHAT_GRAPH_VERSION = 12
ACTION_GRAPH_VERSION = 1
_GRAPH = None
_GRAPH_LOCK = threading.RLock()
_CHAT_GRAPH = None
_ACTION_GRAPH = None
_CHECKPOINTER = None
_CHECKPOINTER_CONNECTION = None


class LangGraphPilotUnavailable(RuntimeError):
    """Raised when the optional LangGraph dependency is not installed."""


class PilotState(TypedDict, total=False):
    session_id: int
    message_id: int
    user_id: int
    question: str
    environment: str
    service: str
    thread_id: str
    max_evidence_tools: int
    scope: Dict[str, Any]
    alerts: Dict[str, Any]
    evidence: List[Dict[str, Any]]
    trace: List[Dict[str, Any]]
    status: str
    error: str
    _result: Dict[str, Any]


class ChatState(TypedDict, total=False):
    graph_version: int
    session_id: int
    message_id: int
    user_id: int
    question: str
    analysis_only: bool
    thread_id: str
    result: Dict[str, Any]
    trace: List[Dict[str, Any]]
    status: str
    runtime_status: str
    route: str
    requested_action: str
    policy: Dict[str, Any]
    incident_environment: str
    incident_mcp_ids: List[int]
    incident_alert: Dict[str, Any]
    incident_alert_fact: Dict[str, Any]
    incident_query: str
    incident_evidence: Dict[str, Any]
    k8s_environment: Dict[str, Any]
    k8s_mcp_ids: List[int]
    k8s_cluster_id: int
    k8s_scope: Dict[str, Any]
    k8s_resource_type: str
    k8s_evidence: Dict[str, Any]
    correlation_environment: Dict[str, Any]
    correlation_scope: Dict[str, Any]
    correlation_query: str
    correlation_system: str
    correlation_service: str
    correlation_evidence: Dict[str, Any]
    self_heal_environment: Dict[str, Any]
    self_heal_scope: Dict[str, Any]
    self_heal_query: str
    self_heal_system: str
    self_heal_service: str
    self_heal_evidence: Dict[str, Any]
    slo_environment: Dict[str, Any]
    slo_scope: Dict[str, Any]
    slo_query: str
    slo_system: str
    slo_service: str
    slo_duration_minutes: int
    slo_action: Dict[str, Any]
    slo_evidence: Dict[str, Any]
    agent_context: Dict[str, Any]
    task_context: Dict[str, Any]
    analysis_context: Dict[str, Any]
    formatter_context: Dict[str, Any]
    error: str


class ActionState(TypedDict, total=False):
    graph_version: int
    action_id: int
    action_type: str
    risk_level: str
    status: str
    confirmed_by_id: int
    submitted_payload: Dict[str, Any]
    result: Dict[str, Any]


def _require_langgraph() -> None:
    if not LANGGRAPH_AVAILABLE:
        raise LangGraphPilotUnavailable(
            'LangGraph 试点依赖未安装，请执行 pip install -r requirements.txt。'
        )


def _checkpoint_path() -> str:
    configured = str(os.getenv('AIOPS_LANGGRAPH_CHECKPOINT_PATH') or '').strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = Path(settings.BASE_DIR) / path
    else:
        path = Path(settings.BASE_DIR) / 'runtime' / 'aiops-langgraph-checkpoints.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _get_checkpointer():
    global _CHECKPOINTER, _CHECKPOINTER_CONNECTION
    _require_langgraph()
    with _GRAPH_LOCK:
        if _CHECKPOINTER is None:
            backend = str(os.getenv('AIOPS_LANGGRAPH_CHECKPOINT_BACKEND') or 'sqlite').strip().lower()
            if backend == 'mysql':
                if PyMySQLSaver is None:
                    raise LangGraphPilotUnavailable('MySQL checkpoint 依赖未安装。')
                import pymysql

                database = settings.DATABASES['default']
                if database['ENGINE'] != 'django.db.backends.mysql':
                    raise ValueError('MySQL checkpoint 需要 Django MySQL 数据库配置。')
                connection_options = {
                    'host': database.get('HOST') or 'localhost',
                    'port': int(database.get('PORT') or 3306),
                    'user': database.get('USER') or '',
                    'password': database.get('PASSWORD') or '',
                    'database': database.get('NAME') or '',
                    'charset': 'utf8mb4',
                    'collation': str(
                        (database.get('OPTIONS') or {}).get('collation')
                        or os.getenv('AIOPS_LANGGRAPH_MYSQL_COLLATION')
                        or 'utf8mb4_unicode_ci'
                    ),
                    'autocommit': True,
                }

                def connect():
                    return pymysql.connect(**connection_options)

                checkpointer = _SxPyMySQLSaver(connect)
                setup_connection = connect()
                try:
                    with setup_connection.cursor() as cursor:
                        cursor.execute('SELECT GET_LOCK(%s, %s)', ('sxdevops_aiops_checkpoint_setup', 30))
                        if cursor.fetchone()[0] != 1:
                            raise RuntimeError('无法获取 checkpoint 初始化锁。')
                        try:
                            checkpointer.setup()
                        finally:
                            cursor.execute('SELECT RELEASE_LOCK(%s)', ('sxdevops_aiops_checkpoint_setup',))
                finally:
                    setup_connection.close()
                _CHECKPOINTER = checkpointer
            elif backend == 'sqlite':
                _CHECKPOINTER_CONNECTION = sqlite3.connect(
                    _checkpoint_path(),
                    check_same_thread=False,
                    timeout=30,
                )
                _CHECKPOINTER = SqliteSaver(_CHECKPOINTER_CONNECTION)
                _CHECKPOINTER.setup()
            else:
                raise ValueError(f'不支持的 LangGraph checkpoint 后端：{backend}')
        return _CHECKPOINTER


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return {'value': str(value)}


def _callback_from_config(config):
    callback = ((config or {}).get('configurable') or {}).get('progress_callback')
    return callback if callable(callback) else (lambda **kwargs: None)


def _runtime(state: PilotState):
    session = AIOpsChatSession.objects.get(pk=state['session_id'])
    message = AIOpsChatMessage.objects.get(pk=state['message_id'])
    user = get_user_model().objects.get(pk=state['user_id'])
    return session, message, user


def _append_trace(state: PilotState, node: str, status: str = 'completed', **extra: Any):
    return [
        *(state.get('trace') or []),
        {'node': node, 'status': status, **extra},
    ]


def _compact_tool_result(tool_name: str, tool_result: Dict[str, Any]) -> Dict[str, Any]:
    """Keep checkpoint state JSON-like and avoid storing Django model objects."""
    output = tool_result.get('tool_output') or {}
    compact: Dict[str, Any] = {
        'tool_name': tool_name,
        'summary': output.get('summary') if isinstance(output, dict) else {},
        'sections': tool_result.get('sections') or output.get('sections') or [],
        'citations': tool_result.get('citations') or output.get('citations') or [],
    }
    if isinstance(output, dict) and output.get('error'):
        compact['error'] = str(output['error'])[:300]
    if isinstance(output, dict) and isinstance(output.get('alert'), dict):
        compact['alert'] = _json_safe(output['alert'])
    if isinstance(output, dict) and isinstance(output.get('alerts'), list):
        compact['alerts'] = [
            {
                'id': item.id,
                'fingerprint': item.fingerprint or '',
                'service': item.service or '',
                'environment': item.environment or '',
                'title': item.title or '',
                'resource': item.resource or '',
                'resource_type': item.resource_type or '',
            }
            for item in output['alerts'][:8]
            if hasattr(item, 'id')
        ]
    if isinstance(output, dict):
        for key in ('changes', 'workorders', 'events', 'items', 'records', 'links'):
            value = output.get(key)
            if isinstance(value, list):
                compact[key] = _json_safe(value[:8])
    return compact


def _incident_compact_tool_result(tool_name: str, tool_result: Dict[str, Any]) -> Dict[str, Any]:
    """Store bounded, structured evidence for the incident checkpoint."""
    from .services import _log_to_sample_dict, _value_from_record

    compact = _compact_tool_result(tool_name, tool_result)
    output = tool_result.get('tool_output') or {}
    if not isinstance(output, dict):
        return compact
    if tool_name == 'query_logs' and isinstance(output.get('logs'), list):
        compact['logs'] = [_json_safe(_log_to_sample_dict(item)) for item in output['logs'][:8]]
    elif tool_name == 'query_events' and isinstance(output.get('events'), list):
        compact['events'] = [{
            'title': _value_from_record(item, 'title', ''),
            'result': _value_from_record(item, 'result', ''),
            'summary': _value_from_record(item, 'summary', ''),
            'resource_name': _value_from_record(item, 'resource_name', ''),
            'environment': _value_from_record(item, 'environment', ''),
            'created_at': _value_from_record(item, 'created_at', ''),
        } for item in output['events'][:8]]
    elif tool_name == 'query_system_posture' and isinstance(output.get('systems'), list):
        compact['systems'] = [{
            'name': _value_from_record(item, 'name', ''),
            'environment': _value_from_record(item, 'environment', ''),
            'health_score': _value_from_record(item, 'health_score', ''),
            'core_metric': _json_safe(_value_from_record(item, 'core_metric', {})),
        } for item in output['systems'][:6]]
    elif tool_name == 'query_traces' and isinstance(output.get('traces'), list):
        compact['traces'] = _json_safe(output['traces'][:8])
    elif tool_name in {'query_alert_metrics', 'query_k8s_resources', 'query_k8s_cluster_summary'}:
        for key in ('metrics', 'evidence', 'series', 'items', 'pods', 'workloads'):
            if isinstance(output.get(key), list):
                compact[key] = _json_safe(output[key][:8])
    return _json_safe(compact)


def _scope_node(state: PilotState) -> PilotState:
    question = str(state.get('question') or '').strip()
    environment = str(state.get('environment') or '').strip()
    resolved = _resolve_knowledge_environment_for_query(
        ' '.join(item for item in [environment, question] if item)
    )
    if resolved:
        knowledge_environment = resolved
        environment = knowledge_environment.get('name') or environment
        scope = _build_analysis_scope(knowledge_environment)
    else:
        scope = {'environment': environment, 'resolution_status': 'missing'}
    return {
        'environment': environment,
        'scope': scope,
        'trace': _append_trace(state, 'scope', environment=environment),
    }


def _alerts_node(state: PilotState) -> PilotState:
    session, message, user = _runtime(state)
    result = _run_tool_call(
        session,
        message,
        user,
        'query_alerts',
        {
            'query': state.get('question') or state.get('environment') or '',
            'limit': 8,
        },
        registry_entry=_platform_tool_registry_entry('query_alerts'),
    )
    compact = _compact_tool_result('query_alerts', result)
    return {
        'alerts': compact,
        'trace': _append_trace(
            state,
            'alerts',
            tool='query_alerts',
            count=(compact.get('summary') or {}).get('count', 0),
        ),
    }


def _has_alerts(state: PilotState) -> bool:
    alerts = state.get('alerts') or {}
    summary = alerts.get('summary') or {}
    return bool(summary.get('count') or alerts.get('alerts'))


def _evidence_node(state: PilotState) -> PilotState:
    session, message, user = _runtime(state)
    alerts = state.get('alerts') or {}
    alert_items = alerts.get('alerts') or []
    first_alert = alert_items[0] if alert_items else {}
    service = str(state.get('service') or first_alert.get('service') or '').strip()
    question = state.get('question') or state.get('environment') or ''
    tools = []
    if service:
        tools.extend([
            ('query_logs', {'query': question, 'service': service, 'limit': 6, 'duration_minutes': 60}),
            ('query_traces', {'query': service, 'errors_only': True, 'limit': 6, 'duration_minutes': 60}),
        ])
    tools.append(('query_recent_changes', {'limit': 5}))
    evidence = []
    max_tools = max(1, min(int(state.get('max_evidence_tools') or 3), 3))
    for tool_name, arguments in tools[:max_tools]:
        result = _run_tool_call(
            session,
            message,
            user,
            tool_name,
            arguments,
            registry_entry=_platform_tool_registry_entry(tool_name),
        )
        evidence.append(_compact_tool_result(tool_name, result))
    return {
        'service': service,
        'evidence': evidence,
        'trace': _append_trace(state, 'evidence', tools=[item['tool_name'] for item in evidence]),
    }


def _finalize_node(state: PilotState) -> PilotState:
    alerts = state.get('alerts') or {}
    evidence = state.get('evidence') or []
    sections = []
    citations = []
    for item in [alerts, *evidence]:
        sections.extend(item.get('sections') or [])
        citations.extend(item.get('citations') or [])
    deduped_citations = []
    seen_citations = set()
    for citation in citations:
        key = (citation.get('title'), citation.get('path')) if isinstance(citation, dict) else str(citation)
        if key in seen_citations:
            continue
        seen_citations.add(key)
        deduped_citations.append(citation)
    count = (alerts.get('summary') or {}).get('count', 0)
    return {
        'status': 'completed',
        'trace': _append_trace(state, 'finalize', alert_count=count, evidence_count=len(evidence)),
        'evidence': evidence,
        '_result': {
            'status': 'completed',
            'engine': 'langgraph',
            'environment': state.get('environment') or '',
            'service': state.get('service') or '',
            'alert_count': count,
            'sections': sections,
            'citations': deduped_citations,
            'scope': state.get('scope') or {},
        },
    }


def _build_graph():
    _require_langgraph()
    builder = StateGraph(PilotState)
    builder.add_node('scope', _scope_node)
    builder.add_node('alerts', _alerts_node)
    builder.add_node('evidence', _evidence_node)
    builder.add_node('finalize', _finalize_node)
    builder.add_edge(START, 'scope')
    builder.add_edge('scope', 'alerts')
    builder.add_conditional_edges('alerts', lambda state: 'evidence' if _has_alerts(state) else 'finalize')
    builder.add_edge('evidence', 'finalize')
    builder.add_edge('finalize', END)
    return builder.compile(checkpointer=_get_checkpointer())


def get_langgraph_pilot_graph():
    global _GRAPH
    _require_langgraph()
    with _GRAPH_LOCK:
        if _GRAPH is None:
            _GRAPH = _build_graph()
        return _GRAPH


def _chat_prepare_node(state: ChatState, config=None) -> ChatState:
    """Validate the graph input before entering the controlled AIOps runtime."""
    question = str(state.get('question') or '').strip()
    if not state.get('session_id') or not state.get('message_id') or not state.get('user_id'):
        raise ValueError('LangGraph chat state is missing its Django identity fields')
    if not question:
        raise ValueError('LangGraph chat question cannot be empty')
    emit = _callback_from_config(config)
    emit(
        step={
            'title': 'LangGraph 编排',
            'detail': '已通过状态校验，准备执行受控 AIOps runtime。',
            'status': 'running',
        },
        text='正在进入 LangGraph 编排',
    )
    return {
        'status': 'prepared',
        'runtime_status': 'ready',
        'trace': _append_trace(state, 'prepare', status='completed'),
    }


def _chat_route_node(state: ChatState, config=None) -> ChatState:
    """Choose a stable orchestration lane while keeping execution policy in Django."""
    from .services import _is_direct_alert_analysis_question, _resolve_question_category_action

    question = str(state.get('question') or '').lower()
    message = AIOpsChatMessage.objects.only('metadata').get(pk=state['message_id'])
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    page_context = metadata.get('page_context') if isinstance(metadata.get('page_context'), dict) else {}
    page_code = str(page_context.get('page') or '').lower()
    category = metadata.get('question_category') or 'auto'
    action_routes = {
        'alert.root_cause': 'incident' if _is_direct_alert_analysis_question(question) else 'general',
        'log.query_generate': 'general',
        'k8s.diagnose': 'k8s',
        'slo.analysis': 'slo',
        'change.correlation': 'correlation',
        'event.analysis': 'correlation',
        'self_heal.recommend': 'self_heal',
        'host_task.generate': 'action',
    }
    requested_action = None
    if category == 'troubleshoot' or category in action_routes:
        _, _, user = _runtime(state)
        requested_action = _resolve_question_category_action(category, question, user=user)
        route = action_routes[requested_action['code']] if requested_action and requested_action.get('available') else 'general'
    elif category in {'cmdb', 'cost'} or (category == 'auto' and (page_code == 'cmdb' or page_code.startswith('cmdb.'))):
        route = 'cmdb'
    elif any(keyword in question for keyword in ('生成任务', '创建任务', '安装', '巡检任务', '执行命令', '脚本')):
        route = 'action'
    elif '告警' in question and any(keyword in question for keyword in ('根因', '原因', '为什么', '怎么处理')):
        route = 'incident'
    elif _is_chat_self_heal_question(question):
        route = 'self_heal'
    elif _is_chat_change_correlation_question(question):
        route = 'correlation'
    elif any(keyword in question for keyword in ('k8s', 'kubernetes', 'pod', '集群', '工作负载')):
        route = 'k8s'
    elif any(keyword in question for keyword in ('cmdb', '资产', '配置项')):
        route = 'cmdb'
    elif _is_chat_slo_analysis_question(question):
        route = 'slo'
    else:
        route = 'general'
    return {
        'route': route,
        'requested_action': requested_action['code'] if requested_action else '',
        'trace': _append_trace(state, 'route', route=route),
    }


def _is_chat_change_correlation_question(question: str) -> bool:
    lowered = str(question or '').lower()
    has_change_scope = any(keyword in lowered for keyword in (
        '变更', '发布', '上线', '部署', '工单', '回滚', '事件',
        'release', 'change', 'rollout', 'event',
    ))
    has_correlation_intent = any(keyword in lowered for keyword in (
        '关联', '关系', '影响', '导致', '相关', '时间线',
        '异常', '错误率', '升高', '下降', '原因', '为什么', '排查',
        'correlat', 'impact', 'caused',
    ))
    return has_change_scope and has_correlation_intent


def _is_chat_self_heal_question(question: str) -> bool:
    lowered = str(question or '').lower()
    has_recommendation_intent = any(keyword in lowered for keyword in (
        '推荐', '方案', '建议', '适合', '能不能', '是否可以', 'dry-run', '自愈',
        'recommend', 'remediation', 'self-heal',
    ))
    has_recovery_scope = any(keyword in lowered for keyword in (
        '自愈', '自动恢复', '修复', '处置', '恢复', '脚本', '回滚',
        '告警', '故障', '异常', 'error', 'incident',
    ))
    return has_recommendation_intent and has_recovery_scope


def _is_chat_slo_analysis_question(question: str) -> bool:
    from .services import (
        _action_question_matches,
        _is_direct_posture_question,
        _is_direct_promql_question,
        is_system_posture_enabled,
    )

    return (
        _action_question_matches('slo.analysis', question)
        and not _is_direct_promql_question(question)
        and not (is_system_posture_enabled() and _is_direct_posture_question(question))
    )


def _chat_lane_node(lane: str):
    def node(state: ChatState, config=None) -> ChatState:
        return {
            'trace': _append_trace(state, f'lane_{lane}', route=lane, status='completed'),
        }

    return node


def _chat_route_next(state: ChatState) -> str:
    return f"lane_{state.get('route') or 'general'}"


def _chat_policy_node(state: ChatState, config=None) -> ChatState:
    """Capture the server-side action policy before any runtime tool is called."""
    from .services import _question_scope_disabled_reason, _build_dispatch_error_result
    agent_config = get_agent_config()
    message = AIOpsChatMessage.objects.only('metadata').get(pk=state['message_id'])
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    reason = _question_scope_disabled_reason(agent_config, state.get('question') or '',
        metadata.get('question_category') or 'auto', route=state.get('route') or '',
        page_context=metadata.get('page_context'))
    if reason:
        return {'result': _build_dispatch_error_result(reason), 'runtime_status': 'completed',
                'trace': _append_trace(state, 'policy', status='blocked', reason=reason)}
    policy = {
        'analysis_only': bool(state.get('analysis_only')),
        'allow_action_execution': bool(getattr(agent_config, 'allow_action_execution', False)),
        'action_gate': 'analysis_only' if state.get('analysis_only') else (
            'enabled' if getattr(agent_config, 'allow_action_execution', False) else 'disabled'
        ),
    }
    emit = _callback_from_config(config)
    emit(
        step={
            'title': '动作策略检查',
            'detail': '已读取服务端动作开关与只分析模式，后续动作仍需 Django 确认层处理。',
            'status': 'completed',
        },
        text='已完成动作策略检查',
    )
    return {
        'policy': policy,
        'trace': _append_trace(state, 'policy', action_gate=policy['action_gate']),
    }


def _chat_cmdb_node(state: ChatState, config=None) -> ChatState:
    """Run the authorized CMDB fastpath before the compatibility runtime."""
    from .services import _build_chat_result_legacy

    session = AIOpsChatSession.objects.get(pk=state['session_id'])
    message = AIOpsChatMessage.objects.get(pk=state['message_id'])
    user = get_user_model().objects.get(pk=state['user_id'])
    result = _build_chat_result_legacy(
        session,
        message,
        user,
        state.get('question') or message.content,
        progress_callback=_callback_from_config(config),
        analysis_only=bool(state.get('analysis_only')),
        cmdb_only=True,
    )
    if not result:
        return {'trace': _append_trace(state, 'cmdb_fastpath', status='skipped')}
    result = _json_safe(result)
    metadata = dict(result.get('metadata') or {})
    metadata.update({
        'langgraph_route': 'cmdb',
        'langgraph_action_gate': (state.get('policy') or {}).get('action_gate') or 'disabled',
    })
    result['metadata'] = metadata
    return {
        'result': result,
        'runtime_status': 'completed',
        'trace': _append_trace(state, 'cmdb_fastpath', execution_mode=metadata.get('execution_mode') or 'direct_cmdb_query'),
    }


def _chat_after_policy(state: ChatState) -> str:
    if state.get('result'):
        return 'validate'
    if state.get('route') == 'cmdb':
        return 'cmdb_fastpath'
    if state.get('route') == 'incident':
        return 'incident_scope'
    if state.get('route') == 'correlation':
        return 'correlation_scope'
    if state.get('route') == 'self_heal':
        return 'self_heal_scope'
    if state.get('route') == 'slo':
        return 'slo_scope'
    if state.get('route') == 'k8s':
        from .services import _is_k8s_analysis_question

        if state.get('requested_action') == 'k8s.diagnose' or _is_k8s_analysis_question(state.get('question') or ''):
            return 'k8s_scope'
    return 'chat_runtime'


def _chat_after_cmdb(state: ChatState) -> str:
    from .langgraph_formatter import after_synthesis

    return after_synthesis(state) if state.get('result') else 'chat_runtime'


def _incident_scope_node(state: ChatState, config=None) -> ChatState:
    from .services import _build_environment_required_result, _get_selected_mcp_servers, _resolve_chat_environment

    session = AIOpsChatSession.objects.get(pk=state['session_id'])
    resolution = _resolve_chat_environment(session, state['question'])
    if resolution.get('status') != 'resolved':
        return {
            'result': _json_safe(_build_environment_required_result(resolution)),
            'runtime_status': 'completed',
            'trace': _append_trace(state, 'incident_scope', status='blocked'),
        }
    environment = resolution['environment'].get('name') or ''
    return {
        'incident_environment': environment,
        'incident_mcp_ids': [server.id for server in _get_selected_mcp_servers(get_agent_config())],
        'trace': _append_trace(state, 'incident_scope', environment=environment),
    }


def _incident_after_scope(state: ChatState) -> str:
    return 'validate' if state.get('result') else 'incident_alert'


def _incident_after_alert(state: ChatState) -> str:
    return 'validate' if state.get('result') else 'incident_k8s'


def _incident_after_k8s(state: ChatState) -> str:
    return 'validate' if state.get('result') else 'incident_posture'


def _incident_after_posture(state: ChatState) -> str:
    return 'validate' if state.get('result') else 'incident_events'


def _incident_after_events(state: ChatState) -> str:
    return 'validate' if state.get('result') else 'incident_logs'


def _incident_after_logs(state: ChatState) -> str:
    return 'validate' if state.get('result') else 'incident_traces'


def _incident_after_traces(state: ChatState) -> str:
    return 'validate' if state.get('result') else 'incident_metrics'


def _incident_after_metrics(state: ChatState) -> str:
    return 'validate' if state.get('result') else 'incident_synthesis'


def _k8s_after_scope(state: ChatState) -> str:
    return 'validate' if state.get('result') else 'k8s_resources'


def _k8s_next(state: ChatState) -> str:
    if state.get('result'):
        return 'validate'
    phases = ['k8s_resources', 'k8s_cluster', 'k8s_alerts', 'k8s_events', 'k8s_posture', 'k8s_synthesis']
    return phases[phases.index(state['trace'][-1]['node']) + 1]


def _incident_runtime(state):
    session, message, user = _runtime(state)
    session.context = {**(session.context or {}), 'current_environment': {'name': state['incident_environment']}}
    session._incident_alert_snapshot = state.get('incident_alert_fact') or None
    return session, message, user


def _incident_tool_available(state, user, tool_name):
    from .services import _get_selected_mcp_servers, _runtime_tool_is_available

    servers = [server for server in _get_selected_mcp_servers(get_agent_config())
               if server.id in state.get('incident_mcp_ids', [])]
    return _runtime_tool_is_available(servers, user, 'query_event_wall' if tool_name == 'query_events' else tool_name)


def _incident_denied(state, node, tool_name='query_alert_root_cause', reason='tool_unavailable_or_permission_denied'):
    from .services import _build_dispatch_error_result, _create_tool_invocation, _finish_tool_invocation

    session, message, user = _incident_runtime(state)
    invocation = _create_tool_invocation(session, message, tool_name, {'phase': node})
    _finish_tool_invocation(invocation, {'error': reason}, time.time(), success=False)
    return {
        'result': _json_safe(_build_dispatch_error_result('告警取证工具已停用或当前账号无权查看告警。', code='incident_permission_denied')),
        'runtime_status': 'completed',
        'trace': _append_trace(state, node, status='blocked', reason=reason),
    }


def _incident_alert_node(state: ChatState, config=None) -> ChatState:
    from .services import _alert_scope_queryset, _alert_to_fact, _extract_alert_fingerprint, _extract_alert_id

    question = state['question']
    query = f"{state['incident_environment']} {question}".strip()
    alert_id = _extract_alert_id(question)
    fingerprint = _extract_alert_fingerprint(question)
    latest = any(keyword in question.lower() for keyword in ('最新一条', '最新告警', '最后一条', '最近一条', 'latest alert', 'last alert'))
    session, message, user = _incident_runtime(state)
    evidence = {}
    selected = None
    selection = 'explicit' if alert_id or fingerprint else 'latest' if latest else 'query'
    if not _incident_tool_available(state, user, 'query_alert_root_cause'):
        return _incident_denied(state, 'incident_alert')
    if alert_id or fingerprint or latest:
        knowledge_environment = _resolve_knowledge_environment_for_query(query)
        queryset = _alert_scope_queryset(knowledge_environment)
        if alert_id:
            selected = queryset.filter(id=alert_id).order_by('-last_received_at', '-created_at', '-id').first()
        elif fingerprint:
            selected = queryset.filter(fingerprint=fingerprint).order_by('-last_received_at', '-created_at', '-id').first()
        else:
            selected = queryset.order_by('-last_received_at', '-created_at', '-id').first()
    else:
        if not _incident_tool_available(state, user, 'query_alerts'):
            return _incident_denied(state, 'incident_alert')
        result = _run_tool_call(
            session,
            message,
            user,
            'query_alerts',
            {'query': query, 'limit': 8},
            registry_entry=_platform_tool_registry_entry('query_alerts'),
        )
        compact = _compact_tool_result('query_alerts', result)
        evidence['alerts'] = compact
        alert_items = (result.get('tool_output') or {}).get('alerts') if isinstance(result.get('tool_output'), dict) else []
        selected = alert_items[0] if alert_items else None
    if selected is None:
        return {
            'incident_alert': {},
            'incident_alert_fact': {},
            'incident_query': query,
            'incident_evidence': evidence,
            'trace': _append_trace(state, 'incident_alert', status='completed', selection=selection, count=0),
        }
    fact = _json_safe(selected if isinstance(selected, dict) else _alert_to_fact(selected))
    if not isinstance(selected, dict):
        fact.update({key: getattr(selected, key).isoformat() if getattr(selected, key) else None
                     for key in ('starts_at', 'last_received_at', 'created_at')})
    incident_query = ' '.join(item for item in [state['incident_environment'], fact.get('service'), fact.get('resource'), fact.get('title')] if item).strip()
    return {
        'incident_alert': {'id': fact.get('id'), 'fingerprint': fact.get('fingerprint') or ''},
        'incident_alert_fact': fact,
        'incident_query': incident_query or query,
        'incident_evidence': evidence,
        'trace': _append_trace(state, 'incident_alert', selection=selection, alert_id=fact.get('id')),
    }


def _incident_collect_node(state: ChatState, node, tool_name, arguments, evidence_key=None, config=None):
    from .services import _create_tool_invocation, _finish_tool_invocation

    alert = state.get('incident_alert_fact') or {}
    if not alert:
        return {'trace': _append_trace(state, node, status='skipped', reason='alert_missing')}
    session, message, user = _incident_runtime(state)
    if not _incident_tool_available(state, user, 'query_alert_root_cause'):
        return _incident_denied(state, node)
    if not _incident_tool_available(state, user, tool_name):
        reason = 'tool_unavailable_or_permission_denied'
        invocation = _create_tool_invocation(session, message, tool_name, {'phase': node, **arguments})
        _finish_tool_invocation(invocation, {'error': reason}, time.time(), success=False)
        evidence = dict(state.get('incident_evidence') or {})
        evidence[evidence_key or tool_name] = {
            'tool_name': tool_name, 'error': reason, 'summary': {'error': reason},
            'sections': [{'title': '取证限制', 'items': [f'{tool_name} 已停用或无权访问。']}], 'citations': [],
        }
        return {'incident_evidence': evidence, 'trace': _append_trace(state, node, status='blocked', tool=tool_name, reason=reason)}
    emit = _callback_from_config(config)
    emit(tool_event={'name': tool_name, 'status': 'running', 'node': node}, text=f'正在执行 {tool_name}')
    result = _run_tool_call(
        session,
        message,
        user,
        tool_name,
        arguments,
        registry_entry=_platform_tool_registry_entry(tool_name),
    )
    compact = _incident_compact_tool_result(tool_name, result)
    evidence = dict(state.get('incident_evidence') or {})
    evidence[evidence_key or tool_name] = compact
    summary = compact.get('summary') or {}
    if compact.get('error') and not summary.get('error'):
        compact['summary'] = {**summary, 'error': compact['error']}
    status = 'failed' if compact.get('error') or summary.get('error') else 'completed'
    reason = compact.get('error') or summary.get('error') or ''
    if tool_name == 'query_alert_metrics' and summary.get('failed_count'):
        status, reason = 'failed', 'metric_queries_incomplete'
    if summary.get('evidence_unavailable') and not reason:
        status, reason = 'skipped', 'evidence_unavailable'
    emit(tool_event={'name': tool_name, 'status': status, 'node': node, 'detail': reason}, text=f'{tool_name} {status}')
    return {
        'incident_evidence': evidence,
        'trace': _append_trace(state, node, status=status, tool=tool_name, evidence_key=evidence_key or tool_name, reason=reason),
    }


def _incident_k8s_node(state: ChatState, config=None) -> ChatState:
    from .services import _value_from_record

    alert = state.get('incident_alert_fact') or {}
    raw_type = str(_value_from_record(alert, 'resource_type') or '').lower()
    if not (_value_from_record(alert, 'cluster') or _value_from_record(alert, 'namespace') or raw_type in {'pod', 'pods', 'deployment', 'deployments', 'service', 'services', 'node', 'nodes'} or 'k8s' in str(_value_from_record(alert, 'source')).lower()):
        return {'trace': _append_trace(state, 'incident_k8s', status='skipped', reason='not_k8s_alert')}
    environment = _resolve_knowledge_environment_for_query(state['incident_environment']) or {}
    if not environment.get('k8s_cluster_ids'):
        evidence = dict(state.get('incident_evidence') or {})
        evidence['k8s'] = {'summary': {'error': '当前知识环境未绑定 K8s 集群，已跳过集群查询。'},
                           'sections': [{'title': 'K8s 取证缺口', 'items': ['当前知识环境未绑定 K8s 集群。']}], 'citations': []}
        return {'incident_evidence': evidence, 'trace': _append_trace(state, 'incident_k8s', status='skipped', reason='cluster_missing')}
    resource_type = {'deployment': 'deployments', 'deployments': 'deployments', 'service': 'services', 'services': 'services', 'node': 'nodes', 'nodes': 'nodes'}.get(raw_type, '')
    tool_name = 'query_k8s_resources' if resource_type and resource_type != 'pods' else 'query_k8s_cluster_summary'
    arguments = {'query': state.get('incident_query') or state['question'], 'cluster_name': _value_from_record(alert, 'cluster') or '', 'limit': 6}
    if tool_name == 'query_k8s_resources':
        arguments['resource_type'] = resource_type
    return _incident_collect_node(state, 'incident_k8s', tool_name, arguments, 'k8s', config)


def _incident_posture_node(state: ChatState, config=None) -> ChatState:
    from . import services

    if not services.is_system_posture_enabled():
        return {'trace': _append_trace(state, 'incident_posture', status='skipped', reason='posture_disabled')}
    return _incident_collect_node(state, 'incident_posture', 'query_system_posture', {'query': state.get('incident_query') or state['question'], 'limit': 3}, 'posture', config)


def _incident_events_node(state: ChatState, config=None) -> ChatState:
    return _incident_collect_node(state, 'incident_events', 'query_events', {'query': state.get('incident_query') or state['question'], 'date_filter': '', 'limit': 5}, 'events', config)


def _incident_logs_node(state: ChatState, config=None) -> ChatState:
    from .services import _value_from_record

    service = _value_from_record(state.get('incident_alert_fact') or {}, 'service')
    if not service:
        if not state.get('incident_alert_fact'):
            return {'trace': _append_trace(state, 'incident_logs', status='skipped', reason='alert_missing')}
        evidence = dict(state.get('incident_evidence') or {})
        evidence['logs'] = {'summary': {'skipped': True, 'reason': 'service_missing'}, 'logs': [],
                            'sections': [{'title': '日志与链路跳过', 'items': ['告警未携带明确服务名，已跳过日志与链路查询。']}], 'citations': []}
        return {'incident_evidence': evidence, 'trace': _append_trace(state, 'incident_logs', status='skipped', reason='service_missing')}
    return _incident_collect_node(state, 'incident_logs', 'query_logs', {'query': state.get('incident_query') or state['question'], 'service': service, 'limit': 5}, 'logs', config)


def _incident_traces_node(state: ChatState, config=None) -> ChatState:
    from .services import _value_from_record

    alert = state.get('incident_alert_fact') or {}
    service = _value_from_record(alert, 'service')
    if not service:
        return {'trace': _append_trace(state, 'incident_traces', status='skipped', reason='service_missing')}
    text = ' '.join(str(_value_from_record(alert, key) or '') for key in ('title', 'message', 'service', 'resource')).lower()
    return _incident_collect_node(state, 'incident_traces', 'query_traces', {'query': f"{state['incident_environment']} {service}", 'errors_only': any(keyword in text for keyword in ('5xx', 'error', 'timeout', '错误', '失败', '超时')), 'limit': 5, 'duration_minutes': 60}, 'traces', config)


def _incident_metrics_node(state: ChatState, config=None) -> ChatState:
    from .services import ALERT_METRIC_DEFAULT_STEP_SECONDS, ALERT_METRIC_QUERY_BUDGET

    alert = state.get('incident_alert') or {}
    return _incident_collect_node(
        state,
        'incident_metrics',
        'query_alert_metrics',
        {'query': state.get('incident_query') or state['question'], 'alert_id': alert.get('id'), 'fingerprint': alert.get('fingerprint') or '', 'duration_minutes': 60, 'step': ALERT_METRIC_DEFAULT_STEP_SECONDS, 'budget': ALERT_METRIC_QUERY_BUDGET},
        'metrics',
        config=config,
    )


def _incident_synthesis_node(state: ChatState, config=None) -> ChatState:
    from .services import (
        _action_registry_item_by_code,
        _assemble_alert_root_cause,
        _attach_selected_action_metadata,
        _build_evidence_bundle_result,
        _create_tool_invocation,
        _finish_tool_invocation,
        _get_selected_skills,
        _skills_for_action,
    )

    evidence = state.get('incident_evidence') or {}
    alert = state.get('incident_alert_fact') or {}
    session, message, user = _incident_runtime(state)
    active_skills = _skills_for_action(_get_selected_skills(get_agent_config(), user=user), {'code': 'alert.root_cause'})
    if not _incident_tool_available(state, user, 'query_alert_root_cause'):
        return _incident_denied(state, 'incident_synthesis')
    for key, compact in list(evidence.items()):
        tool_name = compact.get('tool_name')
        if tool_name and not _incident_tool_available(state, user, tool_name):
            evidence = {**evidence, key: {'tool_name': tool_name, 'summary': {'error': '取证工具已停用或无权访问，未使用已保存结果。'},
                                       'sections': [{'title': '取证限制', 'items': [f'{tool_name} 已停用或无权访问。']}], 'citations': []}}
    if not alert:
        result = _build_evidence_bundle_result(
            question=state['question'], scoped_question=f"{state['incident_environment']} {state['question']}",
            knowledge_environment={'name': state['incident_environment']}, analysis_scope={'environment': state['incident_environment']},
            provider=None, active_skills=active_skills,
            sections=[{'title': '告警根因分析', 'items': ['没有找到可分析的告警。请确认环境、指纹或告警中心数据是否存在。']}],
            citations=[{'title': '告警中心', 'path': '/alerts'}],
            tool_names=[compact.get('tool_name') for compact in evidence.values() if compact.get('tool_name')],
            collected_tool_outputs=[{'tool_name': compact.get('tool_name'), 'tool_output': compact} for compact in evidence.values()],
            execution_mode='direct_alert_root_cause_fastpath',
            extra_metadata={'incident_alert_not_found': True, 'incident_evidence': list(evidence), 'incident_evidence_nodes': list(evidence)},
        )
    else:
        analysis_inputs = {key: {item: value for item, value in compact.items() if item != 'tool_name'} for key, compact in evidence.items()}
        root_payload = _assemble_alert_root_cause(
            alert,
            environment=state['incident_environment'],
            k8s_result=analysis_inputs.get('k8s'), posture_result=analysis_inputs.get('posture'),
            event_result=analysis_inputs.get('events'), log_result=analysis_inputs.get('logs'),
            trace_result=analysis_inputs.get('traces'), metric_result=analysis_inputs.get('metrics'),
        )
        if not _incident_tool_available(state, user, 'query_alert_root_cause'):
            return _incident_denied(state, 'incident_synthesis')
        invocation = _create_tool_invocation(session, message, 'query_alert_root_cause', {
            'phase': 'synthesis', 'alert_id': alert.get('id'), 'fingerprint': alert.get('fingerprint') or '',
            'knowledge_environment': state['incident_environment'],
        })
        _finish_tool_invocation(invocation, root_payload.get('summary') or {}, time.time(), success=True)
        sections = root_payload.get('sections') or []
        citations = root_payload.get('citations') or []
        tool_names = ['query_alert_root_cause'] + [compact.get('tool_name') for compact in evidence.values() if compact.get('tool_name')]
        collected = [{'tool_name': 'query_alert_root_cause', 'tool_output': root_payload}]
        result = _build_evidence_bundle_result(
            question=state['question'], scoped_question=f"{state['incident_environment']} {state['question']}",
            knowledge_environment={'name': state['incident_environment']}, analysis_scope={'environment': state['incident_environment']},
            provider=None, active_skills=active_skills, sections=sections, citations=citations, tool_names=tool_names,
            collected_tool_outputs=collected, execution_mode='direct_alert_root_cause_fastpath',
            extra_metadata={'alert_id': alert.get('id'), 'alert_fingerprint': alert.get('fingerprint') or '', 'incident_evidence': list(evidence), 'incident_evidence_nodes': list(evidence)},
        )
    action = _action_registry_item_by_code('alert.root_cause', user=user)
    if action:
        result = _attach_selected_action_metadata(result, action, extra_metadata={'action_route': 'direct_alert_root_cause_fastpath'})
    result = _json_safe(result)
    result.setdefault('metadata', {}).update({
        'langgraph_route': 'incident',
        'langgraph_action_gate': (state.get('policy') or {}).get('action_gate') or 'disabled',
    })
    return {
        'result': result,
        'runtime_status': 'completed',
        'trace': _append_trace(state, 'incident_synthesis', evidence=list(evidence)),
    }


def _k8s_scope_node(state: ChatState, config=None) -> ChatState:
    from ops.models import K8sCluster
    from .services import _build_analysis_scope, _build_environment_required_result, _get_selected_mcp_servers, _resolve_chat_environment

    session = AIOpsChatSession.objects.get(pk=state['session_id'])
    question = state['question']
    resolution = _resolve_chat_environment(session, question)
    if resolution.get('status') != 'resolved':
        return {
            'result': _json_safe(_build_environment_required_result(resolution)),
            'runtime_status': 'completed',
            'trace': _append_trace(state, 'k8s_scope', status='blocked'),
        }
    environment = resolution['environment']
    scoped_state = {**state, 'k8s_environment': _json_safe(environment),
                    'k8s_mcp_ids': [server.id for server in _get_selected_mcp_servers(get_agent_config())]}
    if not _k8s_access_allowed(scoped_state, _runtime(state)[2]):
        return _k8s_denied(scoped_state, 'k8s_scope')
    cluster_id = K8sCluster.objects.filter(id__in=environment.get('k8s_cluster_ids') or []).order_by('-updated_at', '-id').values_list('id', flat=True).first()
    try:
        analysis_scope = _build_analysis_scope(environment)
    except Exception as exc:
        analysis_scope = {'environment': environment.get('name'), 'error': str(exc)[:200]}
    resource_type = _detect_k8s_resource_type_for_graph(question)
    return {
        'k8s_environment': _json_safe(environment),
        'k8s_mcp_ids': scoped_state['k8s_mcp_ids'],
        'k8s_cluster_id': cluster_id or 0,
        'k8s_scope': _json_safe(analysis_scope),
        'k8s_resource_type': resource_type,
        'trace': _append_trace(
            state,
            'k8s_scope',
            environment=environment.get('name') or '',
            cluster_id=cluster_id,
            resource_type=resource_type,
        ),
    }


def _detect_k8s_resource_type_for_graph(question: str) -> str:
    from .services import _detect_k8s_resource_type

    return _detect_k8s_resource_type(question) or 'workloads'


def _k8s_runtime(state):
    session, message, user = _runtime(state)
    session.context = {**(session.context or {}), 'current_environment': {'name': state['k8s_environment']['name']}}
    session._k8s_environment_snapshot = state['k8s_environment']
    session._k8s_cluster_id = state.get('k8s_cluster_id') or 0
    return session, message, user


def _k8s_tool_available(state, user, tool_name):
    from .services import _get_selected_mcp_servers, _runtime_tool_is_available

    servers = [server for server in _get_selected_mcp_servers(get_agent_config())
               if server.id in state.get('k8s_mcp_ids', [])]
    return _runtime_tool_is_available(servers, user, 'query_event_wall' if tool_name == 'query_events' else tool_name)


def _k8s_access_allowed(state, user):
    return all(_k8s_tool_available(state, user, name) for name in ['query_k8s_resources', 'query_k8s_cluster_summary'])


def _k8s_denied(state, node):
    from .services import _build_dispatch_error_result, _create_tool_invocation, _finish_tool_invocation

    session, message, user = _k8s_runtime(state)
    reason = 'tool_unavailable_or_permission_denied'
    invocation = _create_tool_invocation(session, message, 'query_k8s_resources', {'phase': node})
    _finish_tool_invocation(invocation, {'error': reason}, time.time(), success=False)
    return {
        'result': _json_safe(_build_dispatch_error_result('K8s 取证工具已停用或当前账号无权查看 K8s。', code='k8s_permission_denied')),
        'runtime_status': 'completed',
        'trace': _append_trace(state, node, status='blocked', reason=reason),
    }


def _k8s_gap(tool_name, reason, detail):
    return {'tool_name': tool_name, 'summary': {'evidence_unavailable': True, 'reason': reason},
            'sections': [{'title': '取证限制', 'items': [detail]}], 'citations': []}


def _k8s_collect_node(state: ChatState, node: str, tool_name: str, arguments: Dict[str, Any], config=None) -> ChatState:
    from .services import _create_tool_invocation, _finish_tool_invocation, _value_from_record, is_system_posture_enabled

    session, message, user = _k8s_runtime(state)
    if not _k8s_access_allowed(state, user):
        return _k8s_denied(state, node)
    evidence = dict(state.get('k8s_evidence') or {})
    reason = ''
    if tool_name in {'query_k8s_resources', 'query_k8s_cluster_summary'} and not state['k8s_environment'].get('k8s_cluster_ids'):
        reason, detail = 'cluster_binding_missing', '当前知识环境未绑定 K8s 集群，已跳过集群取证，无法判断工作负载是否健康。'
    elif tool_name in {'query_k8s_resources', 'query_k8s_cluster_summary'} and not state.get('k8s_cluster_id'):
        reason, detail = 'cluster_missing', '当前知识环境绑定的 K8s 集群不存在，已跳过集群取证，无法判断工作负载是否健康。'
    elif tool_name == 'query_system_posture' and not is_system_posture_enabled():
        reason, detail = 'feature_disabled', '系统态势功能未启用，已跳过态势取证。'
    if reason:
        evidence[tool_name] = _k8s_gap(tool_name, reason, detail)
        return {'k8s_evidence': evidence, 'trace': _append_trace(state, node, status='skipped', tool=tool_name, reason=reason)}
    if not _k8s_tool_available(state, user, tool_name):
        reason = 'tool_unavailable_or_permission_denied'
        invocation = _create_tool_invocation(session, message, tool_name, {'phase': node, **arguments})
        _finish_tool_invocation(invocation, {'error': reason}, time.time(), success=False)
        evidence[tool_name] = _k8s_gap(tool_name, reason, f'{tool_name} 已停用或无权访问。')
        evidence[tool_name]['error'] = reason
        return {'k8s_evidence': evidence, 'trace': _append_trace(state, node, status='blocked', tool=tool_name, reason=reason)}
    emit = _callback_from_config(config)
    emit(tool_event={'name': tool_name, 'status': 'running', 'node': node}, text=f'正在执行 {tool_name}')
    result = _run_tool_call(
        session,
        message,
        user,
        tool_name,
        arguments,
        registry_entry=_platform_tool_registry_entry(tool_name),
    )
    compact = _incident_compact_tool_result(tool_name, result)
    output = result.get('tool_output') or {}
    if isinstance(output, dict) and isinstance(output.get('alerts'), list) and tool_name == 'query_alerts':
        compact['alerts'] = [{key: _json_safe(_value_from_record(item, key, ''))
                              for key in ('id', 'fingerprint', 'service', 'environment', 'title', 'resource', 'resource_type', 'level', 'status')}
                             for item in output['alerts'][:8]]
    evidence[tool_name] = compact
    summary = compact.get('summary') or {}
    reason = compact.get('error') or summary.get('error') or ''
    status = 'failed' if reason else 'completed'
    if summary.get('evidence_unavailable') and not reason:
        status, reason = 'skipped', 'evidence_unavailable'
    emit(tool_event={'name': tool_name, 'status': status, 'node': node, 'detail': reason}, text=f'{tool_name} {status}')
    return {
        'k8s_evidence': evidence,
        'trace': _append_trace(
            state,
            node,
            tool=tool_name,
            status=status,
            reason=reason,
            count=summary.get('count', 0),
        ),
    }


def _k8s_resources_node(state: ChatState, config=None) -> ChatState:
    scoped_question = f"{state['k8s_environment'].get('name')} {state['question']}".strip()
    return _k8s_collect_node(
        state,
        'k8s_resources',
        'query_k8s_resources',
        {'query': scoped_question, 'resource_type': state.get('k8s_resource_type') or 'workloads', 'limit': 12},
        config=config,
    )


def _k8s_cluster_node(state: ChatState, config=None) -> ChatState:
    scoped_question = f"{state['k8s_environment'].get('name')} {state['question']}".strip()
    return _k8s_collect_node(
        state,
        'k8s_cluster',
        'query_k8s_cluster_summary',
        {'query': scoped_question, 'limit': 1},
        config=config,
    )


def _k8s_alerts_node(state: ChatState, config=None) -> ChatState:
    from ops.models import Alert

    environment_name = state['k8s_environment'].get('name') or ''
    return _k8s_collect_node(state, 'k8s_alerts', 'query_alerts',
                             {'query': environment_name, 'status': Alert.STATUS_ACTIVE, 'limit': 8}, config=config)


def _k8s_events_node(state: ChatState, config=None) -> ChatState:
    return _k8s_collect_node(state, 'k8s_events', 'query_events', {
        'query': state['k8s_environment'].get('name') or '',
        'date_filter': 'last_hour' if '一小时' in state['question'] else '', 'limit': 8,
    }, config=config)


def _k8s_posture_node(state: ChatState, config=None) -> ChatState:
    return _k8s_collect_node(state, 'k8s_posture', 'query_system_posture', {
        'query': f"{state['k8s_environment'].get('name')} {state['question']}".strip(),
        'limit': 4, 'analysis_scope': state['k8s_scope'],
    }, config=config)


def _k8s_synthesis_node(state: ChatState, config=None) -> ChatState:
    from .services import (
        _action_registry_item_by_code,
        _attach_selected_action_metadata,
        _build_evidence_bundle_result,
        _get_selected_skills,
        _skills_for_action,
        _provider_is_ready,
        get_active_provider,
    )

    session, message, user = _k8s_runtime(state)
    if not _k8s_access_allowed(state, user):
        return _k8s_denied(state, 'k8s_synthesis')
    evidence = state.get('k8s_evidence') or {}
    sections, citations, tool_names, collected = [], [], [], []
    for tool_name, compact in evidence.items():
        if not _k8s_tool_available(state, user, tool_name) and not (compact.get('summary') or {}).get('evidence_unavailable'):
            compact = _k8s_gap(tool_name, 'tool_unavailable_or_permission_denied', f'{tool_name} 已停用或无权访问，已移除缓存证据。')
        sections.extend(compact.get('sections') or [])
        citations.extend(compact.get('citations') or [])
        tool_names.append(tool_name)
        tool_output = {key: value for key, value in compact.items() if key != 'tool_name'}
        collected.append({'tool_name': tool_name, 'tool_output': tool_output})
    agent_config = get_agent_config()
    provider = get_active_provider(agent_config)
    formatter_provider = provider if _provider_is_ready(provider) else None
    result = _build_evidence_bundle_result(
        question=state['question'],
        scoped_question=f"{state['k8s_environment'].get('name')} {state['question']}".strip(),
        knowledge_environment=state['k8s_environment'],
        analysis_scope=state['k8s_scope'],
        provider=formatter_provider,
        active_skills=_skills_for_action(_get_selected_skills(agent_config, user=user), {'code': 'k8s.diagnose'}),
        sections=sections,
        citations=citations,
        tool_names=tool_names,
        collected_tool_outputs=collected,
        execution_mode='deterministic_k8s_rca',
        extra_metadata={'k8s_resource_type': state.get('k8s_resource_type') or 'workloads', 'k8s_evidence_checkpointed': True},
    )
    k8s_action = _action_registry_item_by_code('k8s.diagnose', user=user)
    if k8s_action:
        result = _attach_selected_action_metadata(result, k8s_action, extra_metadata={'action_route': 'deterministic_k8s_rca'})
    return {
        'result': _json_safe(result),
        'runtime_status': 'completed',
        'trace': _append_trace(state, 'k8s_synthesis', evidence=list(evidence)),
    }


def _correlation_scope_node(state: ChatState, config=None) -> ChatState:
    from .services import _build_analysis_scope, _build_environment_required_result, _detect_observability_service, _extract_system_name, _resolve_chat_environment

    session = AIOpsChatSession.objects.get(pk=state['session_id'])
    question = state['question']
    resolution = _resolve_chat_environment(session, question)
    if resolution.get('status') != 'resolved':
        return {
            'result': _json_safe(_build_environment_required_result(resolution)),
            'runtime_status': 'completed',
            'trace': _append_trace(state, 'correlation_scope', status='blocked'),
        }
    environment = resolution['environment']
    try:
        analysis_scope = _build_analysis_scope(environment)
    except Exception as exc:
        analysis_scope = {'environment': environment.get('name'), 'error': str(exc)[:200]}
    service = _detect_observability_service(
        question,
        analysis_scope=analysis_scope,
        knowledge_environment=environment,
    )
    system_name = _extract_system_name(question) or ((analysis_scope or {}).get('systems') or [''])[0]
    correlation_query = ' '.join(item for item in [
        environment.get('name'),
        system_name,
        service,
        question,
    ] if item).strip()
    return {
        'correlation_environment': _json_safe(environment),
        'correlation_scope': _json_safe(analysis_scope),
        'correlation_query': correlation_query,
        'correlation_system': system_name,
        'correlation_service': service,
        'trace': _append_trace(
            state,
            'correlation_scope',
            environment=environment.get('name') or '',
            system=system_name,
            service=service,
        ),
    }


def _correlation_after_scope(state: ChatState) -> str:
    return 'validate' if state.get('result') else 'correlation_knowledge'


def _correlation_collect_node(state: ChatState, node: str, tool_name: str, arguments: Dict[str, Any]) -> ChatState:
    session, message, user = _runtime(state)
    result = _run_tool_call(
        session,
        message,
        user,
        tool_name,
        arguments,
        registry_entry=_platform_tool_registry_entry(tool_name),
    )
    compact = _compact_tool_result(tool_name, result)
    evidence = dict(state.get('correlation_evidence') or {})
    evidence[tool_name] = compact
    return {
        'correlation_evidence': evidence,
        'trace': _append_trace(
            state,
            node,
            tool=tool_name,
            status='failed' if compact.get('error') else 'completed',
            count=(compact.get('summary') or {}).get('count', 0),
        ),
    }


def _correlation_knowledge_node(state: ChatState, config=None) -> ChatState:
    return _correlation_collect_node(
        state,
        'correlation_knowledge',
        'query_knowledge_graph',
        {
            'query': state['correlation_query'],
            'environment': state['correlation_environment'].get('name'),
            'system_name': state.get('correlation_system') or '',
            'service': state.get('correlation_service') or '',
            'limit': 8,
        },
    )


def _correlation_changes_node(state: ChatState, config=None) -> ChatState:
    return _correlation_collect_node(state, 'correlation_changes', 'query_recent_changes', {
        'query': state['correlation_query'], 'system_name': state.get('correlation_system') or '',
        'service': state.get('correlation_service') or '', 'limit': 6,
    })


def _correlation_workorders_node(state: ChatState, config=None) -> ChatState:
    return _correlation_collect_node(
        state,
        'correlation_workorders',
        'query_workorders',
        {'query': state['correlation_query'], 'status': 'all', 'limit': 6},
    )


def _correlation_events_node(state: ChatState, config=None) -> ChatState:
    question = state['question'].lower()
    return _correlation_collect_node(
        state,
        'correlation_events',
        'query_event_wall',
        {
            'query': state['correlation_query'],
            'date_filter': 'today' if any(keyword in question for keyword in ('今天', '今日', '当天', 'today')) else '',
            'limit': 6,
        },
    )


def _correlation_alerts_node(state: ChatState, config=None) -> ChatState:
    from ops.models import Alert

    return _correlation_collect_node(
        state,
        'correlation_alerts',
        'query_alerts',
        {'query': state['correlation_query'], 'status': Alert.STATUS_ACTIVE, 'limit': 6},
    )


def _correlation_synthesis_node(state: ChatState, config=None) -> ChatState:
    from .services import (
        _action_registry_item_by_code,
        _attach_selected_action_metadata,
        _build_evidence_bundle_result,
        _get_selected_skills,
        _skills_for_action,
        _provider_is_ready,
        get_active_provider,
    )

    session, message, user = _runtime(state)
    evidence = state.get('correlation_evidence') or {}
    sections = [{
        'title': '事件分析',
        'items': [
            f"环境：{state['correlation_environment'].get('name') or '-'}",
            f"系统：{state.get('correlation_system') or '-'}",
            f"服务：{state.get('correlation_service') or '-'}",
            f"分析范围：{state.get('correlation_query') or '-'}",
        ],
    }, {
        'title': '风险提示',
        'items': [
            '先核对最近发布、工单和事件时间线是否落在同一窗口。',
            '变更时间接近只能作为候选诱因，需要日志、链路或指标证据交叉验证。',
        ],
    }]
    citations, tool_names, collected = [], [], []
    for tool_name, compact in evidence.items():
        sections.extend(compact.get('sections') or [])
        citations.extend(compact.get('citations') or [])
        tool_names.append(tool_name)
        tool_output = {
            key: value
            for key, value in compact.items()
            if key != 'tool_name'
        }
        collected.append({'tool_name': tool_name, 'tool_output': tool_output})
    agent_config = get_agent_config()
    provider = get_active_provider(agent_config)
    formatter_provider = provider if _provider_is_ready(provider) else None
    result = _build_evidence_bundle_result(
        question=state['question'],
        scoped_question=state.get('correlation_query') or state['question'],
        knowledge_environment=state['correlation_environment'],
        analysis_scope=state['correlation_scope'],
        provider=formatter_provider,
        active_skills=_skills_for_action(_get_selected_skills(agent_config, user=user), {'code': 'change.correlation'}),
        sections=sections,
        citations=citations,
        tool_names=tool_names,
        collected_tool_outputs=collected,
        execution_mode='deterministic_change_correlation',
        extra_metadata={
            'system_name': state.get('correlation_system') or '',
            'service': state.get('correlation_service') or '',
            'correlation_query': state.get('correlation_query') or '',
        },
    )
    action = _action_registry_item_by_code('change.correlation', user=user)
    if action:
        result = _attach_selected_action_metadata(result, action)
    result = _json_safe(result)
    result.setdefault('metadata', {}).update({
        'langgraph_route': 'correlation',
        'langgraph_action_gate': (state.get('policy') or {}).get('action_gate') or 'disabled',
    })
    return {
        'result': result,
        'runtime_status': 'completed',
        'trace': _append_trace(state, 'correlation_synthesis', evidence=list(evidence)),
    }


def _self_heal_scope_node(state: ChatState, config=None) -> ChatState:
    from .services import _build_analysis_scope, _build_environment_required_result, _detect_observability_service, _extract_system_name, _resolve_chat_environment

    session = AIOpsChatSession.objects.get(pk=state['session_id'])
    question = state['question']
    resolution = _resolve_chat_environment(session, question)
    if resolution.get('status') != 'resolved':
        return {
            'result': _json_safe(_build_environment_required_result(resolution)),
            'runtime_status': 'completed',
            'trace': _append_trace(state, 'self_heal_scope', status='blocked'),
        }
    environment = resolution['environment']
    try:
        analysis_scope = _build_analysis_scope(environment)
    except Exception as exc:
        analysis_scope = {'environment': environment.get('name'), 'error': str(exc)[:200]}
    service = _detect_observability_service(
        question,
        analysis_scope=analysis_scope,
        knowledge_environment=environment,
    )
    system_name = _extract_system_name(question) or ((analysis_scope or {}).get('systems') or [''])[0]
    recommendation_scope = ' '.join(item for item in [
        environment.get('name'),
        system_name,
        service,
        question,
    ] if item).strip()
    return {
        'self_heal_environment': _json_safe(environment),
        'self_heal_scope': _json_safe(analysis_scope),
        'self_heal_query': recommendation_scope,
        'self_heal_system': system_name,
        'self_heal_service': service,
        'trace': _append_trace(
            state,
            'self_heal_scope',
            environment=environment.get('name') or '',
            system=system_name,
            service=service,
        ),
    }


def _self_heal_after_scope(state: ChatState) -> str:
    return 'validate' if state.get('result') else 'self_heal_alerts'


def _self_heal_collect_node(state: ChatState, node: str, tool_name: str, arguments: Dict[str, Any]) -> ChatState:
    session, message, user = _runtime(state)
    result = _run_tool_call(
        session,
        message,
        user,
        tool_name,
        arguments,
        registry_entry=_platform_tool_registry_entry(tool_name),
    )
    compact = _compact_tool_result(tool_name, result)
    evidence = dict(state.get('self_heal_evidence') or {})
    evidence[tool_name] = compact
    return {
        'self_heal_evidence': evidence,
        'trace': _append_trace(
            state,
            node,
            tool=tool_name,
            status='failed' if compact.get('error') else 'completed',
            count=(compact.get('summary') or {}).get('count', 0),
        ),
    }


def _self_heal_alerts_node(state: ChatState, config=None) -> ChatState:
    from ops.models import Alert

    return _self_heal_collect_node(
        state,
        'self_heal_alerts',
        'query_alerts',
        {'query': state['self_heal_query'] or state['question'], 'status': Alert.STATUS_ACTIVE, 'limit': 8},
    )


def _self_heal_knowledge_node(state: ChatState, config=None) -> ChatState:
    return _self_heal_collect_node(
        state,
        'self_heal_knowledge',
        'query_knowledge_graph',
        {
            'query': state['self_heal_query'],
            'environment': state['self_heal_environment'].get('name'),
            'system_name': state.get('self_heal_system') or '',
            'service': state.get('self_heal_service') or '',
            'limit': 8,
        },
    )


def _self_heal_changes_node(state: ChatState, config=None) -> ChatState:
    return _self_heal_collect_node(state, 'self_heal_changes', 'query_recent_changes', {
        'query': state['self_heal_query'], 'system_name': state.get('self_heal_system') or '',
        'service': state.get('self_heal_service') or '', 'limit': 6,
    })


def _self_heal_logs_node(state: ChatState, config=None) -> ChatState:
    service = state.get('self_heal_service') or ''
    if not service:
        return {'trace': _append_trace(state, 'self_heal_logs', status='skipped', reason='service_missing')}
    return _self_heal_collect_node(
        state,
        'self_heal_logs',
        'query_logs',
        {
            'query': state['self_heal_query'],
            'service': service,
            'levels': ['warning', 'error'],
            'duration_minutes': 60,
            'limit': 8,
        },
    )


def _self_heal_traces_node(state: ChatState, config=None) -> ChatState:
    service = state.get('self_heal_service') or ''
    if not service:
        return {'trace': _append_trace(state, 'self_heal_traces', status='skipped', reason='service_missing')}
    return _self_heal_collect_node(
        state,
        'self_heal_traces',
        'query_traces',
        {
            'query': f"{state['self_heal_environment'].get('name')} {service}",
            'errors_only': True,
            'duration_minutes': 60,
            'limit': 8,
        },
    )


def _self_heal_synthesis_node(state: ChatState, config=None) -> ChatState:
    from .services import (
        _action_registry_item_by_code,
        _attach_selected_action_metadata,
        _build_action_approval_block,
        _build_evidence_bundle_result,
        _get_selected_skills,
        _skills_for_action,
        _provider_is_ready,
        get_active_provider,
    )

    session, message, user = _runtime(state)
    evidence = state.get('self_heal_evidence') or {}
    environment_name = state['self_heal_environment'].get('name') or '-'
    service = state.get('self_heal_service') or ''
    system_name = state.get('self_heal_system') or ''
    sections = [{
        'title': '自愈推荐',
        'items': [
            f'环境：{environment_name}',
            f'优先围绕：{service or system_name or environment_name}',
            '先做只读验证和 dry-run，再决定是否进入执行草案。',
            '如果需要执行，请先确认影响范围、审批人和执行窗口。',
        ],
    }, {
        'title': '风险提示',
        'items': [
            '自愈只给推荐，不直接执行高风险动作。',
            '任何执行类动作都应先补充范围与审批信息。',
        ],
    }]
    if not service:
        sections.append({
            'title': '日志与链路跳过',
            'items': ['未识别到明确服务名，已跳过日志与链路查询，避免用环境名或系统名误查。'],
        })
    citations, tool_names, collected = [], [], []
    for tool_name, compact in evidence.items():
        sections.extend(compact.get('sections') or [])
        citations.extend(compact.get('citations') or [])
        tool_names.append(tool_name)
        collected.append({
            'tool_name': tool_name,
            'tool_output': {key: value for key, value in compact.items() if key != 'tool_name'},
        })
    agent_config = get_agent_config()
    provider = get_active_provider(agent_config)
    formatter_provider = provider if _provider_is_ready(provider) else None
    result = _build_evidence_bundle_result(
        question=state['question'],
        scoped_question=state.get('self_heal_query') or state['question'],
        knowledge_environment=state['self_heal_environment'],
        analysis_scope=state['self_heal_scope'],
        provider=formatter_provider,
        active_skills=_skills_for_action(_get_selected_skills(agent_config, user=user), {'code': 'self_heal.recommend'}),
        sections=sections,
        citations=citations,
        tool_names=tool_names,
        collected_tool_outputs=collected,
        execution_mode='deterministic_self_heal_recommendation',
        extra_metadata={
            'system_name': system_name,
            'service': service,
            'recommendation_scope': state.get('self_heal_query') or '',
        },
    )
    action = _action_registry_item_by_code('self_heal.recommend', user=user)
    approval_block = _build_action_approval_block(
        action or {},
        summary='当前已给出自愈推荐，请先确认影响范围、审批人和执行窗口，再继续推进。',
        items=[
            {
                'label': '影响范围',
                'value': service or system_name or environment_name,
                'detail': '请确认本次自愈建议覆盖的环境、系统或服务。',
                'text': f'影响范围：{service or system_name or environment_name}',
            },
            {
                'label': '确认信息',
                'value': '审批人 / 执行窗口',
                'detail': '如需进入执行草案，请补充审批人和允许执行的时间窗口。',
                'text': '确认信息：审批人 / 执行窗口',
            },
            {
                'label': '下一步',
                'value': '确认后继续生成执行草案',
                'detail': '当前阶段只推荐，不直接执行。',
                'text': '下一步：确认后继续生成执行草案',
            },
        ],
        metrics=[
            {'label': '推荐项', 'value': f'{len(sections[0].get("items") or [])} 条'},
            {'label': '动作模式', 'value': (action or {}).get('agent_mode_display') or (action or {}).get('agent_mode') or '--'},
            {'label': '风险等级', 'value': (action or {}).get('risk_level_display') or (action or {}).get('risk_level') or '--'},
        ],
        actions=[
            {'type': 'reuse', 'label': '补充影响范围', 'value': f'请补充{environment_name}环境的影响范围、审批人和执行窗口。'},
            {'type': 'reuse', 'label': '继续生成草案', 'value': f'在确认{environment_name}环境影响范围后，继续生成自愈执行草案。'},
        ],
        status='waiting_confirmation',
        status_display='待确认',
        block_id_suffix='confirmation',
    )
    if action:
        result = _attach_selected_action_metadata(result, action, extra_blocks=[approval_block])
    else:
        result.setdefault('metadata', {})['action_route'] = 'deterministic_self_heal_recommendation'
        result.setdefault('metadata', {}).setdefault('response_blocks', []).append(approval_block)
    result = _json_safe(result)
    result.setdefault('metadata', {}).update({
        'langgraph_route': 'self_heal',
        'langgraph_action_gate': (state.get('policy') or {}).get('action_gate') or 'disabled',
    })
    return {
        'result': result,
        'runtime_status': 'completed',
        'trace': _append_trace(state, 'self_heal_synthesis', evidence=list(evidence)),
    }


def _slo_scope_node(state: ChatState, config=None) -> ChatState:
    from .services import (
        _action_registry_item_by_code,
        _build_environment_required_result,
        _detect_log_duration_minutes,
        _detect_observability_service,
        _extract_system_name,
        _persist_session_context,
        _resolve_chat_environment,
        _select_action_for_question,
    )

    session, message, user = _runtime(state)
    question = state['question']
    resolution = _resolve_chat_environment(session, question)
    if resolution.get('status') != 'resolved':
        return {
            'result': _json_safe(_build_environment_required_result(resolution)),
            'runtime_status': 'completed',
            'trace': _append_trace(state, 'slo_scope', status='blocked'),
        }
    environment = resolution['environment']
    try:
        analysis_scope = _build_analysis_scope(environment)
    except Exception as exc:
        analysis_scope = {'environment': environment.get('name'), 'error': str(exc)[:200]}
    action = (
        _action_registry_item_by_code('slo.analysis', user=user)
        if state.get('requested_action') == 'slo.analysis'
        else _select_action_for_question(question, user=user, analysis_scope=analysis_scope)
    )
    if not action or action.get('code') != 'slo.analysis':
        return {'trace': _append_trace(state, 'slo_scope', status='skipped', reason='action_unavailable')}
    _persist_session_context(
        session,
        current_environment={'name': environment.get('name'), 'aliases': environment.get('aliases') or []},
        analysis_scope=analysis_scope,
    )
    scoped_question = f"{environment.get('name')} {question}".strip()
    service = _detect_observability_service(
        scoped_question,
        analysis_scope=analysis_scope,
        knowledge_environment=environment,
    )
    system_name = _extract_system_name(scoped_question) or (analysis_scope.get('systems') or [''])[0]
    duration_minutes = _detect_log_duration_minutes(question)
    return {
        'slo_environment': _json_safe(environment),
        'slo_scope': _json_safe(analysis_scope),
        'slo_query': ' '.join(item for item in [environment.get('name'), system_name, service, question] if item),
        'slo_system': system_name,
        'slo_service': service,
        'slo_duration_minutes': duration_minutes,
        'slo_action': _json_safe(action),
        'trace': _append_trace(state, 'slo_scope', environment=environment.get('name'), service=service, duration_minutes=duration_minutes),
    }


def _slo_after_scope(state: ChatState) -> str:
    if state.get('result'):
        return 'validate'
    return 'slo_posture' if state.get('slo_action') else 'chat_runtime'


def _slo_collect_node(state: ChatState, config, node: str, tool_name: str, arguments: Dict[str, Any]) -> ChatState:
    from .services import _run_scoped_tool, _value_from_record

    session, message, user = _runtime(state)
    tool_result = _run_scoped_tool(
        session, message, user, [], [], [], [], tool_name, arguments,
        emit=_callback_from_config(config),
    )
    compact = _compact_tool_result(tool_name, tool_result)
    output = tool_result.get('tool_output') or {}
    error = compact.get('error') or (compact.get('summary') or {}).get('error')
    if error:
        compact['error'] = str(error)[:300]
        if not compact.get('sections'):
            compact['sections'] = [{'title': 'SLO 查询状态', 'items': [f'{tool_name}：{compact["error"]}']}]
    if tool_name == 'query_alerts':
        compact['alerts'] = [
            {key: _json_safe(_value_from_record(alert, key)) for key in (
                'id', 'fingerprint', 'title', 'level', 'status', 'service', 'environment',
                'resource', 'resource_type', 'last_received_at', 'starts_at', 'created_at',
            )}
            for alert in (output.get('alerts') or [])[:8]
        ]
    if tool_name == 'query_alert_metrics':
        compact['evidence'] = _json_safe((output.get('evidence') or [])[:6])
    evidence = dict(state.get('slo_evidence') or {})
    evidence[tool_name] = _json_safe(compact)
    return {
        'slo_evidence': evidence,
        'trace': _append_trace(state, node, tool=tool_name, status='failed' if error else 'completed'),
    }


def _slo_posture_node(state: ChatState, config=None) -> ChatState:
    from .services import is_system_posture_enabled

    if not is_system_posture_enabled():
        return {'trace': _append_trace(state, 'slo_posture', status='skipped', reason='feature_disabled')}
    return _slo_collect_node(state, config, 'slo_posture', 'query_system_posture', {
        'query': f"{state['slo_environment'].get('name')} {state['question']}",
        'limit': 8, 'analysis_scope': state['slo_scope'],
    })


def _slo_alerts_node(state: ChatState, config=None) -> ChatState:
    return _slo_collect_node(state, config, 'slo_alerts', 'query_alerts', {
        'query': ' '.join(item for item in [state['slo_environment'].get('name'), state.get('slo_service')] if item),
        'status': '',
        'date_filter': 'last_hour' if state['slo_duration_minutes'] <= 60 else '', 'limit': 8,
    })


def _slo_metrics_node(state: ChatState, config=None) -> ChatState:
    from .services import ALERT_METRIC_QUERY_BUDGET, _select_alert_for_metric_evidence

    alerts = (state.get('slo_evidence') or {}).get('query_alerts') or {}
    alert = _select_alert_for_metric_evidence(alerts)
    if not alert or not alert.get('id'):
        return {'trace': _append_trace(state, 'slo_metrics', status='skipped', reason='alert_missing')}
    return _slo_collect_node(state, config, 'slo_metrics', 'query_alert_metrics', {
        'query': state['slo_query'], 'alert_id': alert['id'],
        'duration_minutes': state['slo_duration_minutes'], 'budget': ALERT_METRIC_QUERY_BUDGET,
    })


def _slo_panels_node(state: ChatState, config=None) -> ChatState:
    namespaces = {
        str(namespace) for values in (state['slo_environment'].get('k8s_namespaces') or {}).values()
        for namespace in values
    }
    return _slo_collect_node(state, config, 'slo_panels', 'query_dashboard_panel_data', {
        'query': state['slo_query'], 'duration_minutes': state['slo_duration_minutes'], 'limit': 3,
        'variables': {'namespace': next(iter(namespaces))} if len(namespaces) == 1 else {},
    })


def _slo_traces_node(state: ChatState, config=None) -> ChatState:
    if not state.get('slo_service'):
        return {'trace': _append_trace(state, 'slo_traces', status='skipped', reason='service_missing')}
    return _slo_collect_node(state, config, 'slo_traces', 'query_traces', {
        'query': f"{state['slo_environment'].get('name')} {state['slo_service']}",
        'errors_only': True, 'duration_minutes': state['slo_duration_minutes'], 'limit': 6,
    })


def _slo_knowledge_node(state: ChatState, config=None) -> ChatState:
    return _slo_collect_node(state, config, 'slo_knowledge', 'query_knowledge_graph', {
        'query': state['slo_query'], 'environment': state['slo_environment'].get('name'),
        'system_name': state.get('slo_system') or '', 'service': state.get('slo_service') or '', 'limit': 8,
    })


def _slo_workloads_node(state: ChatState, config=None) -> ChatState:
    if not state['slo_scope'].get('k8s_cluster_ids'):
        return {'trace': _append_trace(state, 'slo_workloads', status='skipped', reason='cluster_missing')}
    return _slo_collect_node(state, config, 'slo_workloads', 'query_k8s_resources', {
        'query': f"{state['slo_environment'].get('name')} {state['question']}",
        'resource_type': 'workloads', 'limit': 8,
    })


def _slo_synthesis_node(state: ChatState, config=None) -> ChatState:
    import copy
    from .services import (
        _attach_selected_action_metadata,
        _build_evidence_bundle_result,
        _get_selected_skills,
        _provider_is_ready,
        _skills_for_action,
        get_active_provider,
    )

    session, message, user = _runtime(state)
    evidence = state.get('slo_evidence') or {}
    sections, citations, collected = [], [], []
    for tool_name, compact in evidence.items():
        sections.extend(compact.get('sections') or [])
        citations.extend(compact.get('citations') or [])
        collected.append({'tool_name': tool_name, 'tool_output': {
            key: value for key, value in compact.items() if key != 'tool_name'
        }})
    if not state.get('slo_service'):
        sections.append({
            'title': '链路追踪跳过',
            'items': ['未识别到明确服务名，已跳过 Trace 查询，避免用环境名或系统名误查。'],
        })
    agent_config = get_agent_config()
    provider = get_active_provider(agent_config)
    requested_model = str((message.metadata or {}).get('model') or '').strip()
    if provider and requested_model in {provider.default_model, provider.backup_model} and requested_model:
        provider = copy.copy(provider)
        provider.default_model = requested_model
    action = state['slo_action']
    result = _build_evidence_bundle_result(
        question=state['question'],
        scoped_question=f"{state['slo_environment'].get('name')} {state['question']}".strip(),
        knowledge_environment=state['slo_environment'], analysis_scope=state['slo_scope'],
        provider=provider if _provider_is_ready(provider) else None,
        active_skills=_skills_for_action(_get_selected_skills(agent_config, user=user), action),
        sections=sections, citations=citations, tool_names=list(evidence), collected_tool_outputs=collected,
        execution_mode='deterministic_slo_analysis',
        extra_metadata={
            'system_name': state.get('slo_system') or '', 'service': state.get('slo_service') or '',
            'duration_minutes': state['slo_duration_minutes'], 'langgraph_route': 'slo',
            'langgraph_action_gate': (state.get('policy') or {}).get('action_gate') or 'disabled',
        },
    )
    result = _attach_selected_action_metadata(result, action, extra_metadata={'action_route': 'deterministic_slo_analysis'})
    return {
        'result': _json_safe(result), 'runtime_status': 'completed',
        'trace': _append_trace(state, 'slo_synthesis', evidence=list(evidence)),
    }


def _chat_runtime_node(state: ChatState, config=None) -> ChatState:
    """Run the existing deterministic and tool calling runtime as a graph node."""
    from .services import ChatJobLeaseLost, _build_chat_result_legacy

    session = AIOpsChatSession.objects.get(pk=state['session_id'])
    message = AIOpsChatMessage.objects.get(pk=state['message_id'])
    user = get_user_model().objects.get(pk=state['user_id'])
    emit = _callback_from_config(config)
    try:
        result = _build_chat_result_legacy(
            session,
            message,
            user,
            state.get('question') or message.content,
            progress_callback=emit,
            analysis_only=bool(state.get('analysis_only')),
            graph_runtime=True,
        )
    except ChatJobLeaseLost:
        raise
    except Exception as exc:
        return {
            'error': str(exc)[:500],
            'runtime_status': 'failed',
            'trace': _append_trace(state, 'chat_runtime', status='failed', error=str(exc)[:200]),
        }
    result = _json_safe(result)
    if result.get('_analysis_context'):
        return {
            'analysis_context': result['_analysis_context'], 'runtime_status': 'evidence_collection',
            'trace': _append_trace(state, 'chat_runtime', execution_mode='checkpointed_analysis'),
        }
    if result.get('_task_context'):
        return {
            'task_context': result['_task_context'], 'runtime_status': 'task_generation',
            'trace': _append_trace(state, 'chat_runtime', execution_mode='checkpointed_task_generation'),
        }
    if result.get('_agent_context'):
        return {
            'agent_context': result['_agent_context'], 'runtime_status': 'planning',
            'trace': _append_trace(state, 'chat_runtime', execution_mode='checkpointed_tool_runtime'),
        }
    metadata = dict(result.get('metadata') or {})
    metadata.update({
        'langgraph_route': state.get('route') or 'general',
        'langgraph_action_gate': (state.get('policy') or {}).get('action_gate') or 'disabled',
    })
    result['metadata'] = metadata
    return {
        'result': result,
        'runtime_status': 'completed',
        'trace': _append_trace(state, 'chat_runtime', execution_mode='controlled_runtime_adapter'),
    }


def _chat_action_guard_node(state: ChatState, config=None) -> ChatState:
    """Annotate action drafts without materializing or executing them in the graph."""
    if state.get('formatter_context'):
        from .langgraph_formatter import _guard, _blocked

        try:
            _guard(state, state['formatter_context'])
        except PermissionError as exc:
            return _blocked(state, state['formatter_context'], 'action_guard', exc)
    result = dict(state.get('result') or {})
    metadata = dict(result.get('metadata') or {})
    draft = result.get('pending_action_draft')
    if draft and not draft.get('error'):
        metadata['langgraph_action_decision'] = 'deferred_to_django_confirmation'
    else:
        metadata['langgraph_action_decision'] = 'none'
    result['metadata'] = metadata
    return {
        'result': result,
        'trace': _append_trace(
            state,
            'action_guard',
            decision=metadata['langgraph_action_decision'],
        ),
    }


def _chat_validate_node(state: ChatState, config=None) -> ChatState:
    """Keep the Django message layer from receiving a malformed graph result."""
    if state.get('formatter_context'):
        from .langgraph_formatter import _guard, _blocked
        from .services import ChatJobLeaseLost

        try:
            _guard(state, state['formatter_context'])
        except ChatJobLeaseLost:
            raise
        except PermissionError as exc:
            return _blocked(state, state['formatter_context'], 'validate', exc)
    result = state.get('result')
    if not isinstance(result, dict):
        raise ValueError('LangGraph chat runtime returned an invalid result')
    result.setdefault('content', '')
    result.setdefault('citations', [])
    result.setdefault('tool_calls', [])
    result.setdefault('message_type', AIOpsChatMessage.TYPE_TEXT)
    result.setdefault('metadata', {})
    if not isinstance(result['metadata'], dict):
        result['metadata'] = {}
    return {
        'result': result,
        'status': 'validated',
        'trace': _append_trace(state, 'validate', status='completed'),
    }


def _chat_finalize_node(state: ChatState, config=None) -> ChatState:
    if state.get('formatter_context'):
        from .langgraph_formatter import _guard, _blocked

        try:
            _guard(state, state['formatter_context'])
        except PermissionError as exc:
            return {**_blocked(state, state['formatter_context'], 'finalize', exc), 'status': 'completed'}
    emit = _callback_from_config(config)
    emit(
        step={
            'title': 'LangGraph 编排完成',
            'detail': '已完成状态图执行，返回 Django 动作确认与消息处理层。',
            'status': 'completed',
        },
        text='LangGraph 编排完成',
    )
    return {
        'status': 'completed',
        'trace': [*(state.get('trace') or []), {'node': 'finalize', 'status': 'completed'}],
    }


def _chat_error_node(state: ChatState, config=None) -> ChatState:
    """Persist a structured graph failure so async workers can diagnose it."""
    error = str(state.get('error') or 'LangGraph execution failed')[:500]
    result = {
        'content': f'问答失败：{error}',
        'citations': [],
        'tool_calls': [],
        'message_type': AIOpsChatMessage.TYPE_ERROR,
        'pending_action_draft': None,
        'metadata': {
            'execution_mode': 'langgraph_error',
            'error_code': 'langgraph_execution_error',
            'error_detail': error,
            'langgraph_route': state.get('route') or 'unknown',
        },
    }
    return {
        'status': 'failed',
        'result': result,
        'trace': _append_trace(state, 'error', status='failed', error=error),
    }


def _chat_failure_router(state: ChatState) -> str:
    if state.get('error'):
        return 'error'
    if state.get('task_context'):
        return 'task_scope'
    if state.get('analysis_context'):
        return 'analysis_scope'
    from .langgraph_formatter import after_synthesis

    return 'agent_plan' if state.get('agent_context') else after_synthesis(state)


def _build_chat_graph(checkpointer=None):
    _require_langgraph()
    from .langgraph_runtime import agent_plan_node, agent_tool_node, agent_synthesis_node, agent_next
    from .langgraph_tasks import task_scope_node, task_resources_node, task_draft_node, task_synthesis_node, task_next
    from .langgraph_analysis import PHASES, analysis_node, analysis_next
    from .langgraph_execution import instrument_node
    from .langgraph_formatter import after_synthesis, formatter_node, formatter_next

    class ChatGraph(StateGraph):
        def add_node(self, node, action, **kwargs):
            return super().add_node(node, instrument_node(node, action), **kwargs)

    builder = ChatGraph(ChatState)
    builder.add_node('route', _chat_route_node)
    for lane in ('action', 'k8s', 'incident', 'correlation', 'self_heal', 'slo', 'cmdb', 'general'):
        builder.add_node(f'lane_{lane}', _chat_lane_node(lane))
    builder.add_node('prepare', _chat_prepare_node)
    builder.add_node('policy', _chat_policy_node)
    builder.add_node('cmdb_fastpath', _chat_cmdb_node)
    builder.add_node('incident_scope', _incident_scope_node)
    builder.add_node('incident_alert', _incident_alert_node)
    builder.add_node('incident_k8s', _incident_k8s_node)
    builder.add_node('incident_posture', _incident_posture_node)
    builder.add_node('incident_events', _incident_events_node)
    builder.add_node('incident_logs', _incident_logs_node)
    builder.add_node('incident_traces', _incident_traces_node)
    builder.add_node('incident_metrics', _incident_metrics_node)
    builder.add_node('incident_synthesis', _incident_synthesis_node)
    builder.add_node('k8s_scope', _k8s_scope_node)
    builder.add_node('k8s_resources', _k8s_resources_node)
    builder.add_node('k8s_cluster', _k8s_cluster_node)
    builder.add_node('k8s_alerts', _k8s_alerts_node)
    builder.add_node('k8s_events', _k8s_events_node)
    builder.add_node('k8s_posture', _k8s_posture_node)
    builder.add_node('k8s_synthesis', _k8s_synthesis_node)
    builder.add_node('correlation_scope', _correlation_scope_node)
    builder.add_node('correlation_knowledge', _correlation_knowledge_node)
    builder.add_node('correlation_changes', _correlation_changes_node)
    builder.add_node('correlation_workorders', _correlation_workorders_node)
    builder.add_node('correlation_events', _correlation_events_node)
    builder.add_node('correlation_alerts', _correlation_alerts_node)
    builder.add_node('correlation_synthesis', _correlation_synthesis_node)
    builder.add_node('self_heal_scope', _self_heal_scope_node)
    builder.add_node('self_heal_alerts', _self_heal_alerts_node)
    builder.add_node('self_heal_knowledge', _self_heal_knowledge_node)
    builder.add_node('self_heal_changes', _self_heal_changes_node)
    builder.add_node('self_heal_logs', _self_heal_logs_node)
    builder.add_node('self_heal_traces', _self_heal_traces_node)
    builder.add_node('self_heal_synthesis', _self_heal_synthesis_node)
    builder.add_node('slo_scope', _slo_scope_node)
    builder.add_node('slo_posture', _slo_posture_node)
    builder.add_node('slo_alerts', _slo_alerts_node)
    builder.add_node('slo_metrics', _slo_metrics_node)
    builder.add_node('slo_panels', _slo_panels_node)
    builder.add_node('slo_traces', _slo_traces_node)
    builder.add_node('slo_knowledge', _slo_knowledge_node)
    builder.add_node('slo_workloads', _slo_workloads_node)
    builder.add_node('slo_synthesis', _slo_synthesis_node)
    builder.add_node('chat_runtime', _chat_runtime_node)
    builder.add_node('agent_plan', agent_plan_node)
    builder.add_node('agent_tool', agent_tool_node)
    builder.add_node('agent_synthesis', agent_synthesis_node)
    builder.add_node('task_scope', task_scope_node)
    builder.add_node('task_resources', task_resources_node)
    builder.add_node('task_draft', task_draft_node)
    builder.add_node('task_synthesis', task_synthesis_node)
    for phase in PHASES:
        builder.add_node('analysis_' + phase, analysis_node(phase))
    for phase in ('prepare', 'model', 'check', 'repair', 'fallback', 'finish'):
        builder.add_node('formatter_' + phase, formatter_node(phase))
        builder.add_conditional_edges('formatter_' + phase, formatter_next)
    builder.add_node('validate', _chat_validate_node)
    builder.add_node('error', _chat_error_node)
    builder.add_node('action_guard', _chat_action_guard_node)
    builder.add_node('finalize', _chat_finalize_node)
    builder.add_edge(START, 'route')
    builder.add_conditional_edges('route', _chat_route_next)
    for lane in ('action', 'k8s', 'incident', 'correlation', 'self_heal', 'slo', 'cmdb', 'general'):
        builder.add_edge(f'lane_{lane}', 'prepare')
    builder.add_edge('prepare', 'policy')
    builder.add_conditional_edges('policy', _chat_after_policy)
    builder.add_conditional_edges('cmdb_fastpath', _chat_after_cmdb)
    builder.add_conditional_edges('incident_scope', _incident_after_scope)
    builder.add_conditional_edges('incident_alert', _incident_after_alert)
    builder.add_conditional_edges('incident_k8s', _incident_after_k8s)
    builder.add_conditional_edges('incident_posture', _incident_after_posture)
    builder.add_conditional_edges('incident_events', _incident_after_events)
    builder.add_conditional_edges('incident_logs', _incident_after_logs)
    builder.add_conditional_edges('incident_traces', _incident_after_traces)
    builder.add_conditional_edges('incident_metrics', _incident_after_metrics)
    builder.add_conditional_edges('incident_synthesis', after_synthesis)
    builder.add_conditional_edges('k8s_scope', _k8s_after_scope)
    for node in ['k8s_resources', 'k8s_cluster', 'k8s_alerts', 'k8s_events', 'k8s_posture']:
        builder.add_conditional_edges(node, _k8s_next)
    builder.add_conditional_edges('k8s_synthesis', after_synthesis)
    builder.add_conditional_edges('correlation_scope', _correlation_after_scope)
    builder.add_edge('correlation_knowledge', 'correlation_changes')
    builder.add_edge('correlation_changes', 'correlation_workorders')
    builder.add_edge('correlation_workorders', 'correlation_events')
    builder.add_edge('correlation_events', 'correlation_alerts')
    builder.add_edge('correlation_alerts', 'correlation_synthesis')
    builder.add_conditional_edges('correlation_synthesis', after_synthesis)
    builder.add_conditional_edges('self_heal_scope', _self_heal_after_scope)
    builder.add_edge('self_heal_alerts', 'self_heal_knowledge')
    builder.add_edge('self_heal_knowledge', 'self_heal_changes')
    builder.add_edge('self_heal_changes', 'self_heal_logs')
    builder.add_edge('self_heal_logs', 'self_heal_traces')
    builder.add_edge('self_heal_traces', 'self_heal_synthesis')
    builder.add_conditional_edges('self_heal_synthesis', after_synthesis)
    builder.add_conditional_edges('slo_scope', _slo_after_scope)
    builder.add_edge('slo_posture', 'slo_alerts')
    builder.add_edge('slo_alerts', 'slo_metrics')
    builder.add_edge('slo_metrics', 'slo_panels')
    builder.add_edge('slo_panels', 'slo_traces')
    builder.add_edge('slo_traces', 'slo_knowledge')
    builder.add_edge('slo_knowledge', 'slo_workloads')
    builder.add_edge('slo_workloads', 'slo_synthesis')
    builder.add_conditional_edges('slo_synthesis', after_synthesis)
    builder.add_conditional_edges('chat_runtime', _chat_failure_router)
    builder.add_conditional_edges('agent_plan', agent_next)
    builder.add_conditional_edges('agent_tool', agent_next)
    builder.add_conditional_edges('agent_synthesis', after_synthesis)
    for node in ('task_scope', 'task_resources', 'task_draft'):
        builder.add_conditional_edges(node, task_next)
    builder.add_conditional_edges('task_synthesis', after_synthesis)
    for phase in PHASES:
        builder.add_conditional_edges('analysis_' + phase, analysis_next)
    builder.add_edge('validate', 'action_guard')
    builder.add_edge('action_guard', 'finalize')
    builder.add_edge('error', END)
    builder.add_edge('finalize', END)
    return builder.compile(checkpointer=checkpointer or _get_checkpointer())


def _action_review_node(state: ActionState, config=None) -> ActionState:
    action = AIOpsPendingAction.objects.get(pk=state['action_id'])
    if action.status != AIOpsPendingAction.STATUS_PENDING:
        raise ValueError('当前动作状态不可确认。')
    return {
        'action_type': action.action_type,
        'risk_level': action.risk_level,
        'status': 'awaiting_confirmation',
    }


def _action_confirmation_node(state: ActionState, config=None) -> ActionState:
    decision = interrupt({
        'action_id': state['action_id'],
        'action_type': state['action_type'],
        'risk_level': state['risk_level'],
        'confirmation_required': True,
    })
    return {
        'confirmed_by_id': int(decision['user_id']),
        'submitted_payload': _json_safe(decision.get('payload') or {}),
        'status': 'confirmed',
    }


def _action_execute_node(state: ActionState, config=None) -> ActionState:
    from .services import confirm_action

    user = get_user_model().objects.get(pk=state['confirmed_by_id'])
    request = ((config or {}).get('configurable') or {}).get('request')
    with transaction.atomic():
        action = AIOpsPendingAction.objects.select_for_update().select_related('session', 'message').get(pk=state['action_id'])
        result = confirm_action(action, user, request=request, payload=state.get('submitted_payload'))
    return {'result': _json_safe(result), 'status': 'completed'}


def _build_action_graph():
    _require_langgraph()
    from .langgraph_execution import instrument_action_node

    builder = StateGraph(ActionState)
    builder.add_node('review', instrument_action_node('review', _action_review_node))
    builder.add_node('confirmation', instrument_action_node('confirmation', _action_confirmation_node))
    builder.add_node('execute', instrument_action_node('execute', _action_execute_node))
    builder.add_edge(START, 'review')
    builder.add_edge('review', 'confirmation')
    builder.add_edge('confirmation', 'execute')
    builder.add_edge('execute', END)
    return builder.compile(checkpointer=_get_checkpointer())


def get_langgraph_action_graph():
    global _ACTION_GRAPH
    with _GRAPH_LOCK:
        if _ACTION_GRAPH is None:
            _ACTION_GRAPH = _build_action_graph()
        return _ACTION_GRAPH


def _action_graph_config(action, request=None):
    created = action.created_at.strftime('%Y%m%d%H%M%S%f')
    return {'configurable': {'thread_id': f'aiops-action-{action.id}-{created}', 'request': request}}


def start_action_confirmation(action_id):
    action = AIOpsPendingAction.objects.get(pk=action_id)
    if action.status != AIOpsPendingAction.STATUS_PENDING:
        return None
    graph = get_langgraph_action_graph()
    config = _action_graph_config(action)
    snapshot = graph.get_state(config)
    if not snapshot.values:
        graph.invoke({'action_id': action.id, 'graph_version': ACTION_GRAPH_VERSION}, config=config)
        snapshot = graph.get_state(config)
    return snapshot


def confirm_langgraph_action(action, user, request=None, payload=None):
    if action.session.user_id != user.id:
        raise ValueError('只能确认自己的动作。')
    if action.status == AIOpsPendingAction.STATUS_EXECUTED:
        from .services import confirm_action
        return confirm_action(action, user, request=request, payload=payload)
    if action.status != AIOpsPendingAction.STATUS_PENDING:
        raise ValueError('当前动作状态不可确认。')
    graph = get_langgraph_action_graph()
    config = _action_graph_config(action, request=request)
    snapshot = start_action_confirmation(action.id)
    if snapshot is None:
        raise ValueError('当前动作状态不可确认。')
    if snapshot.next and snapshot.values.get('graph_version') != ACTION_GRAPH_VERSION:
        raise RuntimeError('动作确认图版本已变化，无法安全恢复旧 checkpoint。')
    if snapshot.values.get('status') == 'completed':
        return snapshot.values['result']
    if snapshot.next == ('execute',):
        graph.invoke(None, config=config)
    elif snapshot.next == ('confirmation',):
        graph.invoke(Command(resume={'user_id': user.id, 'payload': dict(payload or {})}), config=config)
    else:
        raise RuntimeError('动作确认图未处于待确认状态。')
    final = graph.get_state(config)
    if final.values.get('status') != 'completed':
        raise RuntimeError('动作确认图未完成执行。')
    return final.values['result']


def get_langgraph_chat_graph():
    global _CHAT_GRAPH
    _require_langgraph()
    with _GRAPH_LOCK:
        if _CHAT_GRAPH is None:
            _CHAT_GRAPH = _build_chat_graph()
        return _CHAT_GRAPH


def get_langgraph_chat_checkpoint(thread_id: str) -> Dict[str, Any]:
    """Read the latest durable chat state for diagnostics or a worker resume."""
    graph = get_langgraph_chat_graph()
    snapshot = graph.get_state({'configurable': {'thread_id': str(thread_id)}})
    values = snapshot.values if snapshot else {}
    if not values and str(os.getenv('AIOPS_LANGGRAPH_CHECKPOINT_BACKEND') or 'sqlite').lower() == 'mysql':
        legacy_path = Path(_checkpoint_path())
        if legacy_path.is_file():
            connection = sqlite3.connect(str(legacy_path), check_same_thread=False)
            try:
                legacy_graph = _build_chat_graph(checkpointer=SqliteSaver(connection))
                legacy_snapshot = legacy_graph.get_state({'configurable': {'thread_id': str(thread_id)}})
                values = legacy_snapshot.values if legacy_snapshot else {}
            finally:
                connection.close()
    return _json_safe(values)


def ensure_langgraph_thread_id(user_message: AIOpsChatMessage) -> str:
    """Return and persist the stable checkpoint key for one chat message."""
    metadata = user_message.metadata if isinstance(user_message.metadata, dict) else {}
    thread_id = str(metadata.get('langgraph_thread_id') or '').strip()
    if thread_id:
        return thread_id
    thread_id = f'aiops-chat-{user_message.id}-{uuid.uuid4().hex}'
    user_message.metadata = {**metadata, 'langgraph_thread_id': thread_id}
    user_message.save(update_fields=['metadata'])
    return thread_id


def close_langgraph_resources() -> None:
    """Close the process-local SQLite saver before a worker reload or shutdown."""
    global _GRAPH, _CHAT_GRAPH, _ACTION_GRAPH, _CHECKPOINTER, _CHECKPOINTER_CONNECTION
    with _GRAPH_LOCK:
        _GRAPH = None
        _CHAT_GRAPH = None
        _ACTION_GRAPH = None
        checkpointer_connection = _CHECKPOINTER_CONNECTION
        _CHECKPOINTER = None
        _CHECKPOINTER_CONNECTION = None
        if checkpointer_connection is not None:
            checkpointer_connection.close()


def run_langgraph_chat(
    session: AIOpsChatSession,
    user_message: AIOpsChatMessage,
    user,
    question: str,
    *,
    progress_callback=None,
    analysis_only: bool = False,
    thread_id: str = '',
) -> Dict[str, Any]:
    """Run default AIOps chat through LangGraph with durable checkpoints."""
    graph = get_langgraph_chat_graph()
    thread_id = str(thread_id or ensure_langgraph_thread_id(user_message))
    from .langgraph_execution import finish_run
    from .langgraph_management import runtime_summary
    from .models import AIOpsGraphNodeRun
    from .services import ChatJobLeaseLost

    started = time.monotonic()
    with transaction.atomic():
        current_message = AIOpsChatMessage.objects.select_for_update().get(pk=user_message.pk)
        if (current_message.metadata or {}).get('langgraph_checkpoint_expired'):
            raise ValueError('本轮 checkpoint 已按保留策略清理，请发起新消息。')
        run = AIOpsGraphNodeRun.objects.create(message=current_message, thread_id=thread_id, node='__graph__')
    config = {
        'recursion_limit': 96,
        'configurable': {
            'thread_id': thread_id,
            'progress_callback': progress_callback,
        },
    }
    try:
        snapshot = graph.get_state(config)
        if snapshot and snapshot.values and snapshot.next and snapshot.values.get('graph_version', 1) != CHAT_GRAPH_VERSION:
            raise RuntimeError('聊天图版本已变化，无法安全恢复旧 checkpoint。')
        if snapshot and snapshot.values and snapshot.next:
            with transaction.atomic():
                current_message = AIOpsChatMessage.objects.select_for_update().get(pk=user_message.pk)
                current_metadata = dict(current_message.metadata or {})
                current_metadata['langgraph_resume_count'] = int(current_metadata.get('langgraph_resume_count') or 0) + 1
                current_message.metadata = current_metadata
                current_message.save(update_fields=['metadata'])
        initial_state = None if snapshot and snapshot.values else {
            'graph_version': CHAT_GRAPH_VERSION,
            'session_id': session.id,
            'message_id': user_message.id,
            'user_id': user.id,
            'question': str(question or user_message.content or '').strip(),
            'analysis_only': bool(analysis_only),
            'thread_id': thread_id,
            'trace': [],
            }
        final_state = snapshot.values if snapshot and snapshot.values and not snapshot.next else graph.invoke(initial_state, config=config)
        finish_run(run, started, 'failed' if final_state.get('error') else 'completed', str(final_state.get('error') or ''))
    except ChatJobLeaseLost:
        finish_run(run, started, 'interrupted', 'worker_lease_lost')
        raise
    except Exception as exc:
        finish_run(run, started, 'failed', str(exc))
        raise
    result = dict(final_state.get('result') or {})
    metadata = dict(result.get('metadata') or {})
    metadata.update({
        'orchestration_engine': 'langgraph',
        'langgraph_thread_id': thread_id,
        'langgraph_checkpointed': True,
        'langgraph_trace': final_state.get('trace') or [],
        'langgraph_runtime_summary': runtime_summary(thread_id),
    })
    result['metadata'] = metadata
    return result


def run_langgraph_readonly_pilot(
    session: AIOpsChatSession,
    user_message: AIOpsChatMessage,
    user,
    *,
    question: str = '',
    environment: str = '',
    service: str = '',
    thread_id: str = '',
    max_evidence_tools: int = 3,
) -> Dict[str, Any]:
    """Run the pilot and return a UI-friendly trace plus evidence bundle."""
    graph = get_langgraph_pilot_graph()
    thread_id = str(thread_id or f'aiops-langgraph-{uuid.uuid4()}')
    initial: PilotState = {
        'session_id': session.id,
        'message_id': user_message.id,
        'user_id': user.id,
        'question': str(question or user_message.content or '').strip(),
        'environment': str(environment or '').strip(),
        'service': str(service or '').strip(),
        'thread_id': thread_id,
        'max_evidence_tools': max_evidence_tools,
        'trace': [],
    }
    final_state = graph.invoke(
        initial,
        config={'configurable': {'thread_id': thread_id}},
    )
    result = final_state.get('_result') or {}
    return {
        **result,
        'thread_id': thread_id,
        'trace': final_state.get('trace') or [],
        'checkpointed': True,
    }
