"""Checkpointed planning, individual tool execution and answer synthesis."""

import copy
import hashlib
import json
import time

from django.db.models import Model

from . import services
from .models import AIOpsChatMessage, AIOpsModelInvocation, AIOpsModelProvider


MAX_AGENT_ROUNDS = 6
MAX_TOOLS_PER_ROUND = 8


def _checkpoint_value(value):
    if isinstance(value, Model):
        fields = ('id', 'title', 'name', 'hostname', 'ip_address', 'environment', 'service',
                  'namespace', 'cluster', 'level', 'status', 'source', 'message', 'fingerprint',
                  'created_at', 'starts_at', 'last_received_at', 'business_line', 'system_name')
        result = {field: _checkpoint_value(getattr(value, field)) for field in fields if hasattr(value, field)}
        if hasattr(value, 'host_id'):
            result['host'] = value.host.hostname if value.host_id else ''
        return result
    if isinstance(value, dict):
        return {key: _checkpoint_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_checkpoint_value(item) for item in value]
    return json.loads(json.dumps(value, ensure_ascii=False, default=services._json_default))


def _schema_fingerprint(parameters):
    payload = json.dumps(parameters, sort_keys=True, ensure_ascii=False, default=services._json_default)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def build_agent_context(
    *, provider, active_mcp_servers, active_skills, knowledge_environment, analysis_scope,
    selected_action, messages, tools, registry, mcp_diagnostics,
):
    specs = {tool['function']['name']: tool['function'] for tool in tools}
    descriptors = {}
    for tool_name, entry in registry.items():
        descriptor = {
            'kind': entry['kind'],
            'schema_fingerprint': _schema_fingerprint(specs[tool_name]['parameters']),
        }
        if entry['kind'] == 'external':
            descriptor.update({
                'server_id': entry['server'].id,
                'raw_tool_name': entry['raw_tool_name'],
                'config_fingerprint': entry['schema_fingerprint'],
            })
        else:
            descriptor['tool_name'] = tool_name
        descriptors[tool_name] = descriptor
    context = {
        'provider_id': provider.id, 'model': provider.default_model,
        'mcp_ids': [server.id for server in active_mcp_servers],
        'skill_ids': [skill.id for skill in active_skills],
        'environment': knowledge_environment, 'scope': analysis_scope, 'action': selected_action,
        'messages': messages, 'tools': tools, 'registry': descriptors, 'diagnostics': mcp_diagnostics,
        'rounds': 0, 'calls': [], 'call_index': 0, 'tool_names': [], 'outputs': [],
        'sections': [], 'citations': [], 'draft': None, 'message_type': AIOpsChatMessage.TYPE_TEXT,
        'content': '', 'next': 'agent_plan',
    }
    return json.loads(json.dumps(context, ensure_ascii=False, default=services._json_default))


def _runtime(state):
    from .langgraph_pilot import _runtime as load_runtime

    session, message, user = load_runtime(state)
    if not user.is_active or session.user_id != user.id or message.session_id != session.id:
        raise PermissionError('聊天身份或会话状态已变化，停止恢复。')
    if not services.user_has_permissions(user, ['aiops.chat.view']):
        raise PermissionError('当前用户已失去聊天分析权限。')
    context = state.get('agent_context') or state.get('task_context') or state.get('analysis_context')
    if context:
        session = copy.copy(session)
        session.context = {**(session.context or {}), 'current_environment': context['environment'],
                           'analysis_scope': context['scope']}
    return session, message, user


def _provider(context):
    provider = AIOpsModelProvider.objects.filter(pk=context['provider_id'], is_enabled=True).first()
    if not services._provider_is_ready(provider):
        raise ValueError('本轮模型提供商已停用或不可用。')
    if context['model'] not in {provider.default_model, provider.backup_model}:
        raise ValueError('本轮模型已不在提供商的可用模型中。')
    provider = copy.copy(provider)
    provider.default_model = context['model']
    return provider


def _servers(context):
    return [server for server in services._get_selected_mcp_servers(services.get_agent_config())
            if server.id in context['mcp_ids']]


def _available_specs(state, context, user):
    servers = _servers(context)
    by_id = {server.id: server for server in servers}
    specs = []
    for spec in context['tools']:
        tool_name = spec['function']['name']
        descriptor = context['registry'][tool_name]
        if descriptor['kind'] == 'platform_mcp':
            allowed = services._runtime_tool_is_available(servers, user, tool_name)
            if state.get('analysis_only') and tool_name == 'generate_host_task':
                allowed = False
        else:
            server = by_id.get(descriptor['server_id'])
            allowed = bool(server and services._fingerprint_mcp_config(server) == descriptor['config_fingerprint'])
            if state.get('analysis_only') and services.MCP_READ_ONLY_DENY_PATTERN.search(descriptor['raw_tool_name']):
                allowed = False
        if allowed:
            specs.append(spec)
    return specs


def _update(state, context, node, **extra):
    from .langgraph_pilot import _append_trace

    return {'agent_context': _checkpoint_value(context), 'trace': _append_trace(state, node, **extra)}


def _failure(state, context, node, exc):
    from .langgraph_pilot import _append_trace

    if isinstance(exc, services.ChatJobLeaseLost):
        raise exc
    error = services._sanitize_mcp_error_text(str(exc))
    if isinstance(exc, services.AIOpsModelCallError):
        result = services._build_llm_api_error_result(error)
    elif context['outputs']:
        citations = services._dedupe_citations(context['citations'])
        content = services._build_fallback_answer(
            context['sections'], citations, pending_action_draft=context['draft'],
            question=state['question'], collected_tool_outputs=context['outputs'],
        )
        result = {
            'content': services._ensure_followup_line(services._normalize_formatter_output(content), citations),
            'citations': citations, 'tool_calls': context['tool_names'],
            'message_type': context['message_type'], 'pending_action_draft': context['draft'],
            'metadata': {'execution_mode': 'mcp_skills', 'formatter_mode': 'fallback',
                         'formatter_attempts': 0, 'fallback_reason': error,
                         'mcp_diagnostics': context['diagnostics']},
        }
    else:
        result = services._build_dispatch_error_result(error, code='runtime_error', message='模型或工具调用失败。')
    return {'result': result, 'runtime_status': 'failed',
            'trace': _append_trace(state, node, status='failed', error=error)}


def agent_plan_node(state, config=None):
    from .langgraph_pilot import _callback_from_config

    context = copy.deepcopy(state['agent_context'])
    emit = _callback_from_config(config)
    try:
        session, message, user = _runtime(state)
        if context['rounds'] >= MAX_AGENT_ROUNDS:
            context['next'] = 'agent_synthesis'
            return _update(state, context, 'agent_plan', reason='round_budget')
        provider = _provider(context)
        specs = _available_specs(state, context, user)
        if not specs:
            raise PermissionError('本轮工具均已停用、权限撤销或配置变化。')
        emit(step={'title': '模型规划', 'detail': f"第 {context['rounds'] + 1} 轮决策", 'status': 'running'},
             text='正在请求大模型规划')
        completion = services._request_model_completion(
            provider, {'model': provider.default_model, 'temperature': provider.temperature,
                       'max_tokens': provider.max_tokens, 'messages': context['messages'],
                       'tools': specs, 'tool_choice': 'auto'},
            session=session, message=message, user=user, purpose=AIOpsModelInvocation.PURPOSE_CHAT_PLANNING,
        )
        response = ((completion or {}).get('choices') or [{}])[0].get('message') or {}
        content = (response.get('content') or '').strip()
        calls = response.get('tool_calls') or []
        context['rounds'] += 1
        if calls:
            call_ids = [call.get('id') for call in calls]
            if len(calls) > MAX_TOOLS_PER_ROUND or not all(call_ids) or len(set(call_ids)) != len(call_ids):
                raise ValueError('模型工具计划超过预算，或调用 ID 缺失/重复。')
            context['messages'].append({'role': 'assistant', 'content': content, 'tool_calls': calls})
            context.update({'calls': calls, 'call_index': 0, 'next': 'agent_tool'})
        elif not context['tool_names']:
            if context['rounds'] == 1:
                context['messages'].append({
                    'role': 'user', 'content': '你上一轮没有调用任何工具。请重新决策，并且这一次必须至少调用 1 个最相关的工具后再回答；不要直接自由作答。',
                })
                context['next'] = 'agent_plan'
            else:
                return {'result': services._build_dispatch_error_result(
                    '模型未调用任何工具，请检查模型与 MCP/Skill 配置。', code='no_tool_called',
                    message='模型未调用任何工具，无法完成问答。'), 'runtime_status': 'failed',
                    **_update(state, context, 'agent_plan', status='failed', reason='no_tool_called')}
        else:
            context.update({'content': content, 'next': 'agent_synthesis'})
        emit(step={'title': '生成工具计划' if calls else '生成回复',
                   'detail': f'本轮工具 {len(calls)} 个。', 'status': 'completed'},
             text='模型规划完成')
        return _update(state, context, 'agent_plan', round=context['rounds'], tool_count=len(calls))
    except services.ChatJobLeaseLost:
        raise
    except Exception as exc:
        return _failure(state, context, 'agent_plan', exc)


def _execute_tool(state, context, session, message, user, tool_name, arguments):
    descriptor = context['registry'].get(tool_name)
    specs = _available_specs(state, context, user)
    if not descriptor or not any(spec['function']['name'] == tool_name for spec in specs):
        raise PermissionError('工具未授权、已停用或配置已变化，禁止执行。')
    if descriptor['kind'] == 'platform_mcp':
        current_specs = services._tool_specs_for_runtime(
            [server for server in _servers(context) if server.server_type == services.AIOpsMCPServer.SERVER_PLATFORM_BUILTIN], user,
        )
        current = next((spec for spec in current_specs if spec['function']['name'] == tool_name), None)
        if not current or _schema_fingerprint(current['function']['parameters']) != descriptor['schema_fingerprint']:
            raise PermissionError('平台工具参数定义已变化，请重新发起问答。')
        return services._run_tool_call(session, message, user, tool_name, arguments,
                                       registry_entry=services._platform_tool_registry_entry(tool_name))
    server = next(server for server in _servers(context) if server.id == descriptor['server_id'])
    client = services._create_mcp_client_session(server)
    try:
        client.initialize()
        discovered = services._discover_external_mcp_tools(server, client)
        tool = next((tool for tool in discovered if tool.get('name') == descriptor['raw_tool_name']), None)
        if not tool or _schema_fingerprint(tool.get('inputSchema') or {'type': 'object', 'properties': {}}) != descriptor['schema_fingerprint']:
            raise PermissionError('外部 MCP 工具已移除或参数定义已变化。')
        return services._run_tool_call(session, message, user, tool_name, arguments, registry_entry={
            'kind': 'external', 'server': server, 'client_session': client,
            'raw_tool_name': descriptor['raw_tool_name'], 'raw_description': tool.get('description') or '',
            'schema_fingerprint': descriptor['config_fingerprint'],
            'description_warnings': (tool.get('_meta') or {}).get('description_warnings') or [],
        })
    finally:
        try:
            client.close()
        except services.ChatJobLeaseLost:
            raise
        except Exception:
            pass


def agent_tool_node(state, config=None):
    from .langgraph_pilot import _callback_from_config

    context = copy.deepcopy(state['agent_context'])
    emit = _callback_from_config(config)
    try:
        session, message, user = _runtime(state)
        call = context['calls'][context['call_index']]
        function = call.get('function') or {}
        tool_name = function.get('name') or ''
        arguments = services._parse_tool_arguments(function.get('arguments'))
        emit(tool_event={'name': tool_name, 'detail': '开始调用', 'status': 'running'}, text=f'正在调用 {tool_name}')
        try:
            tool_result = _execute_tool(state, context, session, message, user, tool_name, arguments)
        except services.ChatJobLeaseLost:
            raise
        except Exception as exc:
            error = services._sanitize_mcp_error_text(str(exc))
            invocation = services._create_tool_invocation(session, message, tool_name, arguments)
            services._finish_tool_invocation(invocation, {'error': error}, time.time(), success=False)
            tool_result = {'tool_output': {'error': error}, 'sections': [{'title': '工具调用状态', 'items': [error]}]}
        tool_result = _checkpoint_value(tool_result)
        output = tool_result.get('tool_output') or {}
        context['tool_names'].append(tool_name)
        context['outputs'].append({'tool_name': tool_name, 'tool_output': output})
        context['sections'].extend(tool_result.get('sections') or [])
        context['citations'].extend(tool_result.get('citations') or [])
        if tool_result.get('pending_action_draft'):
            context['draft'] = tool_result['pending_action_draft']
        if tool_result.get('message_type') == AIOpsChatMessage.TYPE_ACTION:
            context['message_type'] = AIOpsChatMessage.TYPE_ACTION
        elif tool_result.get('message_type') == AIOpsChatMessage.TYPE_ANALYSIS and context['message_type'] != AIOpsChatMessage.TYPE_ACTION:
            context['message_type'] = AIOpsChatMessage.TYPE_ANALYSIS
        context['messages'].append({'role': 'tool', 'tool_call_id': call['id'],
                                    'content': json.dumps(output, ensure_ascii=False, default=services._json_default)})
        context['call_index'] += 1
        context['next'] = ('agent_tool' if context['call_index'] < len(context['calls']) else
                           'agent_plan' if context['rounds'] < MAX_AGENT_ROUNDS else 'agent_synthesis')
        status = 'failed' if isinstance(output, dict) and output.get('error') else 'completed'
        emit(tool_event={'name': tool_name, 'detail': services._summarize_tool_result(tool_result), 'status': status},
             text=f'{tool_name} 调用完成')
        return _update(state, context, 'agent_tool', tool_name=tool_name, tool_call_id=call['id'], status=status)
    except services.ChatJobLeaseLost:
        raise
    except Exception as exc:
        return _failure(state, context, 'agent_tool', exc)


def agent_synthesis_node(state, config=None):
    from .langgraph_pilot import _callback_from_config, _append_trace

    context = state['agent_context']
    emit = _callback_from_config(config)
    try:
        session, message, user = _runtime(state)
        agent_config = services.get_agent_config()
        skills = [skill for skill in services._get_selected_skills(agent_config, user=user)
                  if skill.id in context['skill_ids']]
        result = services._finalize_tool_runtime_answer(
            provider=_provider(context), question=state['question'],
            knowledge_environment=context['environment'], analysis_scope=context['scope'],
            active_skills=skills, selected_action=context['action'], mcp_diagnostics=context['diagnostics'],
            sections=context['sections'], citations=context['citations'], executed_tool_names=context['tool_names'],
            collected_tool_outputs=context['outputs'], pending_action_draft=context['draft'],
            message_type=context['message_type'], final_content=context['content'], emit=emit,
        )
        emit(step={'title': '工具链回复完成', 'detail': '已完成证据与 Skill 回复整理。', 'status': 'completed'},
             text='工具链回复完成')
        result['metadata'].update({'langgraph_route': state.get('route') or 'general',
                                   'langgraph_agent_rounds': context['rounds'],
                                   'langgraph_action_gate': (state.get('policy') or {}).get('action_gate') or 'disabled'})
        return {'result': result, 'runtime_status': 'completed',
                'trace': _append_trace(state, 'agent_synthesis', rounds=context['rounds'], tools=len(context['tool_names']))}
    except services.ChatJobLeaseLost:
        raise
    except Exception as exc:
        return _failure(state, context, 'agent_synthesis', exc)


def agent_next(state):
    from .langgraph_formatter import after_synthesis

    return after_synthesis(state) if state.get('result') else state['agent_context']['next']
