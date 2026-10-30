"""Checkpointed task target selection, draft generation and answer synthesis."""

import copy

from ops.models import TaskResource

from . import services
from .langgraph_runtime import _checkpoint_value, _provider, _runtime
from .models import AIOpsChatMessage


def build_task_context(
    *, question, scoped_question, knowledge_environment, analysis_scope, provider, active_skills,
    action, action_route,
):
    return _checkpoint_value({
        'question': question, 'scoped_question': scoped_question,
        'environment': knowledge_environment, 'scope': analysis_scope,
        'provider_id': provider.id if provider else None, 'model': provider.default_model if provider else '',
        'skill_ids': [skill.id for skill in active_skills],
        'mcp_ids': [server.id for server in services._get_selected_mcp_servers(services.get_agent_config())],
        'action': action, 'action_route': action_route,
        'resource_arguments': services._task_generation_resource_arguments(question, scoped_question, knowledge_environment),
        'resource_ids': [], 'targets': [], 'evidence': {}, 'draft': None,
    })


def _blocked(state, node, detail, code='task_generation_blocked'):
    from .langgraph_pilot import _append_trace

    context = state['task_context']
    evidence = context['evidence']
    sections = [section for result in evidence.values() for section in result.get('sections') or []]
    sections.append({'title': '任务生成限制', 'items': [detail]})
    result = services._build_evidence_bundle_result(
        question=context['question'], scoped_question=context['scoped_question'],
        knowledge_environment=context['environment'], analysis_scope=context['scope'],
        provider=None, active_skills=[], sections=sections,
        citations=[{'title': '任务中心', 'path': '/tasks'}],
        tool_names=list(evidence), collected_tool_outputs=[
            {'tool_name': name, 'tool_output': value.get('tool_output') or {}} for name, value in evidence.items()
        ], execution_mode='deterministic_task_generation', message_type=AIOpsChatMessage.TYPE_ANALYSIS,
        extra_metadata={'task_generation_blocked': True, 'block_reason': code, 'materialized_in_task_center': False},
    )
    if context['action']:
        result = services._attach_selected_action_metadata(
            result, context['action'], extra_metadata={'action_route': context['action_route']},
        )
    return {'result': result, 'runtime_status': 'completed',
            'trace': _append_trace(state, node, status='blocked', reason=code)}


def _guard(state, tool_name):
    session, message, user = _runtime(state)
    if state.get('analysis_only') or (message.metadata or {}).get('analysis_only'):
        raise PermissionError('本轮为只分析模式，不生成任务草稿。')
    agent_config = services.get_agent_config()
    if not agent_config.allow_action_execution:
        raise PermissionError('服务端动作开关已关闭，请启用后重新发起任务生成。')
    servers = [server for server in services._get_selected_mcp_servers(agent_config)
               if server.id in state['task_context']['mcp_ids']]
    if not services._runtime_tool_is_available(servers, user, tool_name):
        raise PermissionError('任务工具已停用或当前账号权限不足，停止生成任务草稿。')
    if (tool_name == 'generate_host_task'
            and state['task_context']['resource_arguments']['resource_type'] == TaskResource.RESOURCE_K8S
            and not services.user_has_permissions(user, ['ops.k8s.view'])):
        raise PermissionError('当前账号已无权生成 K8s 任务草稿。')
    return session, message, user


def _failed_audit(state, tool_name, arguments, detail):
    import time
    from .langgraph_pilot import _runtime as load_runtime

    session, message, user = load_runtime(state)
    started_at = time.time()
    invocation = services._create_tool_invocation(session, message, tool_name, arguments)
    services._finish_tool_invocation(invocation, {'error': detail}, started_at, success=False)


def _targets(resource_ids):
    return list(TaskResource.objects.filter(id__in=resource_ids).order_by('id').values(
        'id', 'name', 'resource_type', 'status', 'environment_id', 'system_id', 'cluster_id', 'namespace', 'ip_address', 'ssh_port',
    ))


def _validate_targets(context):
    current = _checkpoint_value(_targets(context['resource_ids']))
    if not current or len(current) != len(context['resource_ids']) or current != context['targets']:
        raise PermissionError('本轮目标资源已变更或删除，请重新查询后生成任务草稿。')


def _collect(state, config, context, tool_name, arguments):
    from .langgraph_pilot import _callback_from_config

    session, message, user = _guard(state, tool_name)
    sections, citations, names, outputs = [], [], [], []
    result = services._run_scoped_tool(
        session, message, user, outputs, sections, citations, names, tool_name, arguments,
        emit=_callback_from_config(config),
    )
    context['evidence'][tool_name] = _checkpoint_value(result)
    return result


def task_scope_node(state, config=None):
    from .langgraph_pilot import _append_trace, _callback_from_config

    try:
        _guard(state, 'query_task_resources')
        _guard(state, 'generate_host_task')
    except services.ChatJobLeaseLost:
        raise
    except PermissionError as exc:
        detail = str(exc)
        _failed_audit(state, 'generate_host_task', {}, detail)
        return _blocked(state, 'task_scope', detail)
    emit = _callback_from_config(config)
    emit(step={'title': '任务生成证据收集', 'detail': '先查询资源底座，再生成待确认任务草稿。', 'status': 'completed'},
         text='正在查询任务资源并生成任务草稿')
    return {'trace': _append_trace(state, 'task_scope', environment=state['task_context']['environment'].get('name'))}


def task_resources_node(state, config=None):
    from .langgraph_pilot import _append_trace

    context = copy.deepcopy(state['task_context'])
    arguments = context['resource_arguments']
    try:
        result = _collect(state, config, context, 'query_task_resources', arguments)
    except services.ChatJobLeaseLost:
        raise
    except PermissionError as exc:
        _failed_audit(state, 'query_task_resources', arguments, str(exc))
        return _blocked(state, 'task_resources', str(exc))
    output = result.get('tool_output') or {}
    ids = services._dedupe_int_list(output.get('resource_ids') or (output.get('summary') or {}).get('resource_ids') or [])
    context['resource_ids'] = ids
    context['targets'] = _checkpoint_value(_targets(ids))
    update = {'task_context': _checkpoint_value(context),
              'trace': _append_trace(state, 'task_resources', resource_count=len(ids))}
    if not ids:
        return {**update, **_blocked({**state, **update}, 'task_resources',
                                    '当前环境未匹配到可用任务资源，请检查资源底座或补充明确目标。', 'task_resources_empty')}
    return update


def task_draft_node(state, config=None):
    from .langgraph_pilot import _append_trace

    context = copy.deepcopy(state['task_context'])
    arguments = services._task_generation_draft_arguments(
        context['question'], context['scoped_question'], context['environment'], context['resource_ids'],
    )
    try:
        _guard(state, 'query_task_resources')
        _guard(state, 'generate_host_task')
        _validate_targets(context)
        result = _collect(state, config, context, 'generate_host_task', arguments)
        draft = result.get('pending_action_draft') or {}
        if draft and (draft.get('host_ids') or not draft.get('resource_ids')
                      or not set(draft['resource_ids']).issubset(context['resource_ids'])):
            raise PermissionError('任务草稿目标超出本轮已查询资源范围，请重新指定目标。')
    except services.ChatJobLeaseLost:
        raise
    except PermissionError as exc:
        _failed_audit(state, 'generate_host_task', arguments, str(exc))
        return _blocked(state, 'task_draft', str(exc))
    context['draft'] = _checkpoint_value(result.get('pending_action_draft'))
    return {'task_context': _checkpoint_value(context),
            'trace': _append_trace(state, 'task_draft', draft_ready=bool(context['draft']))}


def task_synthesis_node(state, config=None):
    from .langgraph_pilot import _append_trace, _callback_from_config

    context = state['task_context']
    try:
        session, message, user = _guard(state, 'generate_host_task')
        _guard(state, 'query_task_resources')
        _validate_targets(context)
    except services.ChatJobLeaseLost:
        raise
    except PermissionError as exc:
        return _blocked(state, 'task_synthesis', str(exc))
    evidence = context['evidence']
    agent_config = services.get_agent_config()
    skills = [skill for skill in services._get_selected_skills(agent_config, user=user)
              if skill.id in context['skill_ids']]
    provider = None
    if context['provider_id']:
        try:
            provider = _provider(context)
        except ValueError:
            pass
    result = services._build_evidence_bundle_result(
        question=context['question'], scoped_question=context['scoped_question'],
        knowledge_environment=context['environment'], analysis_scope=context['scope'],
        provider=provider, active_skills=skills,
        sections=[section for value in evidence.values() for section in value.get('sections') or []],
        citations=[citation for value in evidence.values() for citation in value.get('citations') or []],
        tool_names=list(evidence), collected_tool_outputs=[
            {'tool_name': name, 'tool_output': value.get('tool_output') or {}} for name, value in evidence.items()
        ], execution_mode='deterministic_task_generation', message_type=AIOpsChatMessage.TYPE_ACTION,
        pending_action_draft=context['draft'],
        extra_metadata={'resource_ids': context['resource_ids'], 'materialized_in_task_center': False,
                        'langgraph_task_checkpointed': True},
    )
    if context['action']:
        result = services._attach_selected_action_metadata(
            result, context['action'], extra_metadata={'action_route': context['action_route']},
        )
    result['metadata'].update({'langgraph_route': state.get('route') or 'action',
                              'langgraph_action_gate': (state.get('policy') or {}).get('action_gate') or 'disabled'})
    _callback_from_config(config)(
        step={'title': '任务草稿汇总完成', 'detail': '草稿交由 Django 确认层处理。', 'status': 'completed'},
        text='任务草稿汇总完成',
    )
    return {'result': _checkpoint_value(result), 'runtime_status': 'completed',
            'trace': _append_trace(state, 'task_synthesis', draft_ready=bool(context['draft']))}


def task_next(state):
    if state.get('result'):
        return 'validate'
    return {'task_scope': 'task_resources', 'task_resources': 'task_draft', 'task_draft': 'task_synthesis'}[
        state['trace'][-1]['node']
    ]
