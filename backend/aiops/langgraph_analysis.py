"""Checkpointed service anomaly and environment alert evidence."""

import copy
import time

from . import services
from .langgraph_runtime import _checkpoint_value, _provider, _runtime


PHASES = ('scope', 'alerts', 'metrics', 'posture', 'logs', 'traces', 'events', 'workloads', 'synthesis')


def build_analysis_context(*, kind, question, scoped_question, environment, scope, provider, skills, action):
    service = services._detect_observability_service(scoped_question, analysis_scope=scope, knowledge_environment=environment)
    duration = services._detect_log_duration_minutes(question)
    query = ' '.join(item for item in [environment.get('name'), service] if item) or scoped_question
    return _checkpoint_value({
        'kind': kind, 'question': question, 'scoped_question': scoped_question, 'environment': environment, 'scope': scope,
        'provider_id': provider.id if provider else None, 'model': provider.default_model if provider else '',
        'skill_ids': [skill.id for skill in skills], 'action': action,
        'mcp_ids': [server.id for server in services._get_selected_mcp_servers(services.get_agent_config())],
        'service': service, 'duration': duration, 'query': query, 'levels': services._detect_log_levels_filter(question) or ['error', 'warning'],
        'alert_arguments': {'query': query, 'status': '', 'date_filter': 'last_hour' if duration <= 60 else '',
                            'system_name': services._extract_system_name(scoped_question), 'limit': 8},
        'evidence': {}, 'next': 'analysis_scope', 'metric_alert_id': None,
    })


def _tool(context, phase):
    query, duration, service = context['query'], context['duration'], context['service']
    if phase == 'alerts':
        return 'query_alerts', context['alert_arguments']
    if phase == 'metrics' and context['kind'] == 'alerts':
        alert = services._select_alert_for_metric_evidence((context['evidence'].get('query_alerts') or {}).get('tool_output') or {})
        if alert:
            context['metric_alert_id'] = alert['id']
            return 'query_alert_metrics', {'query': query, 'alert_id': alert['id'], 'fingerprint': alert.get('fingerprint') or '',
                                           'duration_minutes': max(60, duration), 'step': services.ALERT_METRIC_DEFAULT_STEP_SECONDS,
                                           'budget': services.ALERT_METRIC_QUERY_BUDGET}
    if phase == 'posture' and services.is_system_posture_enabled():
        return 'query_system_posture', {'query': context['scoped_question'], 'limit': 6, 'analysis_scope': context['scope']}
    if phase == 'logs' and service:
        return 'query_logs', {'query': query, 'service': service, 'levels': context['levels'], 'duration_minutes': duration, 'limit': 8}
    if phase == 'traces' and service:
        return 'query_traces', {'query': service, 'errors_only': True, 'duration_minutes': duration, 'limit': 8}
    if phase == 'events':
        return 'query_events', {'query': query, 'date_filter': 'last_hour' if duration <= 60 else '', 'limit': 8}
    if phase == 'workloads' and context['scope'].get('k8s_cluster_ids'):
        return 'query_k8s_resources', {'query': context['scoped_question'], 'resource_type': 'workloads', 'limit': 8}
    return None, {}


def analysis_node(phase):
    def execute(state, config=None):
        from .langgraph_pilot import _append_trace, _callback_from_config

        session, message, user = _runtime(state)
        context = copy.deepcopy(state['analysis_context'])
        node = 'analysis_' + phase
        if phase == 'synthesis':
            return _synthesize(state, config, user, context)
        tool_name, arguments = _tool(context, phase)
        status, reason = 'completed', ''
        if tool_name:
            servers = [server for server in services._get_selected_mcp_servers(services.get_agent_config())
                       if server.id in context['mcp_ids']]
            if services._runtime_tool_is_available(servers, user, tool_name):
                result = services._run_scoped_tool(session, message, user, [], [], [], [], tool_name, arguments,
                                                   emit=_callback_from_config(config))
                output = result.get('tool_output') or {}
                if isinstance(output, dict) and output.get('error'):
                    status, reason = 'failed', str(output['error'])
            else:
                status, reason = 'blocked', 'tool_unavailable_or_permission_denied'
                invocation = services._create_tool_invocation(session, message, tool_name, arguments)
                services._finish_tool_invocation(invocation, {'error': reason}, time.time(), success=False)
                result = {'tool_output': {'error': reason}, 'sections': [{'title': '取证限制', 'items': [f'{tool_name} 已停用或无权访问。']}], 'citations': []}
            context['evidence'][tool_name] = _checkpoint_value(result)
        elif phase != 'scope':
            status, reason = 'skipped', 'evidence_context_unavailable'
        context['next'] = 'analysis_' + PHASES[PHASES.index(phase) + 1]
        return {'analysis_context': _checkpoint_value(context),
                'trace': _append_trace(state, node, status=status, tool_name=tool_name or '', reason=reason)}
    return execute


def _synthesize(state, config, user, context):
    from .langgraph_pilot import _append_trace, _callback_from_config

    evidence = context['evidence']
    collected = [{'tool_name': name, 'tool_output': value.get('tool_output') or {}} for name, value in evidence.items()]
    sections = [section for value in evidence.values() for section in value.get('sections') or []]
    if not context['service']:
        sections.append({'title': '日志与链路跳过', 'items': ['未识别到明确服务名，已跳过日志与链路查询，避免用环境名或系统名误查。']})
    if context['kind'] == 'alerts' and not context['metric_alert_id']:
        sections.append({'title': '指标查询结果', 'items': ['未查询到可用于指标分析的告警。']})
    provider = None
    if context['provider_id']:
        try:
            provider = _provider(context)
        except ValueError:
            pass
    skills = [skill for skill in services._get_selected_skills(services.get_agent_config(), user=user)
              if skill.id in context['skill_ids']]
    extra = {'service': context['service'], 'duration_minutes': context['duration'], 'langgraph_analysis_checkpointed': True}
    if context['kind'] == 'alerts':
        metrics = services._collect_metric_context(collected)
        extra.update({'alert_filters': context['alert_arguments'], 'metric_alert_id': context['metric_alert_id'],
                      'metric_query': {key: metrics.get(key) for key in ('called', 'planned_count', 'executed_count', 'abnormal_count', 'missing_count', 'failed_count')},
                      'skipped_observability_service_lookup': not bool(context['service'])})
    else:
        extra['log_levels'] = context['levels']
    result = services._build_evidence_bundle_result(
        question=context['question'], scoped_question=context['scoped_question'], knowledge_environment=context['environment'],
        analysis_scope=context['scope'], provider=provider, active_skills=skills, sections=sections,
        citations=[citation for value in evidence.values() for citation in value.get('citations') or []],
        tool_names=list(evidence), collected_tool_outputs=collected,
        execution_mode='deterministic_alert_environment_analysis' if context['kind'] == 'alerts' else 'deterministic_service_rca',
        extra_metadata=extra,
    )
    if context['action']:
        result = services._attach_selected_action_metadata(result, context['action'], extra_metadata={
            'action_route': 'alert_environment_analysis' if context['kind'] == 'alerts' else 'service_anomaly_evidence',
        })
    _callback_from_config(config)(step={'title': '分析证据汇总完成', 'status': 'completed', 'detail': '已保存各阶段证据'}, text='分析证据汇总完成')
    return {'result': _checkpoint_value(result), 'runtime_status': 'completed',
            'trace': _append_trace(state, 'analysis_synthesis', evidence=list(evidence))}


def analysis_next(state):
    from .langgraph_formatter import after_synthesis

    return after_synthesis(state) if state.get('result') else state['analysis_context']['next']
