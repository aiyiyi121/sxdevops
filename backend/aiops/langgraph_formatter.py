"""Durable answer formatting, fact checks, repair and fallback."""

import copy
import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar

from django.contrib.auth import get_user_model

from . import services
from .langgraph_runtime import _checkpoint_value, _provider, _runtime
from .models import AIOpsPendingAction


_CAPTURE = ContextVar('aiops_formatter_capture', default=None)
NATIVE_EVIDENCE_PERMISSIONS = {
    'query_recent_changes': ('ops.deployment.view',),
    'query_workorders': ('ops.ticket.view', 'ops.deployment.view'),
}


@contextmanager
def capture_formatter(state):
    capture = {'state': state, 'request': None}
    token = _CAPTURE.set(capture)
    try:
        yield capture
    finally:
        _CAPTURE.reset(token)


def _skill_fingerprint(skill):
    fields = ('slug', 'name', 'category', 'description', 'content', 'applicable_actions',
              'recommended_tools', 'builtin_tools', 'output_contract')
    content = json.dumps({field: getattr(skill, field) for field in fields}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _provider_fingerprint(provider):
    endpoint = json.dumps([provider.provider_type, provider.base_url], ensure_ascii=False)
    return hashlib.sha256(endpoint.encode('utf-8')).hexdigest()


def defer_formatter(provider, request, skills):
    capture = _CAPTURE.get()
    if capture is None:
        return False
    state = capture['state']
    if capture['request'] is not None:
        raise ValueError('同一图节点不能准备多个回复整形请求。')
    config = services.get_agent_config()
    servers = services._get_selected_mcp_servers(config)
    saved = state.get('agent_context') or state.get('task_context') or state.get('analysis_context') or {}
    server_ids = saved.get('mcp_ids')
    if server_ids is None:
        server_ids = state.get(f"{state.get('route')}_mcp_ids")
    if server_ids is not None:
        servers = [server for server in servers if server.id in server_ids]
    outputs = {item['tool_name']: item.get('tool_output') or {} for item in request['collected_tool_outputs']}
    guard_tools = [name for name in request['tool_calls']
                   if not outputs.get(name, {}).get('error')
                   and not (outputs.get(name, {}).get('summary') or {}).get('evidence_unavailable')
                   and (saved.get('registry', {}).get(name) or {}).get('kind') != 'external']
    native_tools = [name for name in guard_tools if name in NATIVE_EVIDENCE_PERMISSIONS
                    and not any(name in (server.tool_whitelist or []) for server in servers)]
    user = get_user_model().objects.get(pk=state['user_id'])
    native_permissions = {name: [permission for permission in NATIVE_EVIDENCE_PERMISSIONS[name]
                                if services.user_has_permissions(user, [permission])] for name in native_tools}
    capture['request'] = _checkpoint_value({
        **request, 'provider_id': provider.id, 'model': provider.default_model,
        'provider_fingerprint': _provider_fingerprint(provider),
        'skill_ids': [skill.id for skill in skills],
        'skill_fingerprints': {str(skill.id): _skill_fingerprint(skill) for skill in skills},
        'formatter_skill_id': getattr(services._find_skill_by_slug(skills, services.ANSWER_FORMATTER_SKILL_SLUG), 'id', None),
        'mcp_ids': [server.id for server in servers], 'guard_tools': guard_tools,
        'native_permissions': native_permissions,
        'attempts': 0, 'previous_issue': '', 'content': '', 'checks': [],
        'next': 'formatter_prepare', 'reason': '', 'error': '',
    })
    return True


def attach_formatter(update, capture):
    context = capture['request']
    if context is not None and update.get('result'):
        context['base_content'] = update['result'].get('content') or context['fallback_content']
        return {**update, 'formatter_context': context, 'runtime_status': 'answer_formatting'}
    return update


def after_synthesis(state):
    return 'formatter_prepare' if state.get('formatter_context') else 'validate'


def _guard(state, context):
    session, message, user = _runtime(state)
    config = services.get_agent_config()
    if not config.is_enabled:
        raise PermissionError('智能助手已停用，停止恢复回复。')
    servers = [server for server in services._get_selected_mcp_servers(config) if server.id in context['mcp_ids']]
    for name in context['guard_tools']:
        if name in context.get('native_permissions', {}):
            if not services._tool_allowed(user, name) or any(
                not services.user_has_permissions(user, [permission])
                for permission in context['native_permissions'][name]
            ):
                raise PermissionError(f'{name} 查询权限已变化，停止返回保存的证据。')
            continue
        available_name = 'query_event_wall' if name == 'query_events' else name
        if not services._runtime_tool_is_available(servers, user, available_name):
            raise PermissionError(f'{name} 已停用或当前账号已无权查看保存的证据。')
    agent = state.get('agent_context') or {}
    for name in context['tool_calls']:
        descriptor = (agent.get('registry') or {}).get(name) or {}
        if descriptor.get('kind') == 'external':
            server = next((item for item in servers if item.id == descriptor['server_id']), None)
            if not server or services._fingerprint_mcp_config(server) != descriptor['config_fingerprint']:
                raise PermissionError('外部取证工具配置已变化，停止恢复回复。')
    if context['pending_action_draft']:
        if state.get('analysis_only') or not config.allow_action_execution:
            raise PermissionError('当前策略不允许返回待确认任务草稿。')
        draft_tool = ('create_cmdb_asset_draft'
                      if context['pending_action_draft'].get('action_type') == AIOpsPendingAction.ACTION_CREATE_CMDB_ASSET
                      else 'generate_host_task')
        if not services._tool_allowed(user, draft_tool):
            raise PermissionError('当前账号已无权生成该动作草稿。')
        if state.get('task_context'):
            from .langgraph_tasks import _guard as task_guard, _validate_targets

            task_guard(state, 'generate_host_task')
            task_guard(state, 'query_task_resources')
            _validate_targets(state['task_context'])
    return user, config


def _skills(context, user, config):
    current = {skill.id: skill for skill in services._get_selected_skills(config, user=user)}
    selected = [current[identifier] for identifier in context['skill_ids'] if identifier in current]
    formatter = services._find_skill_by_slug(selected, services.ANSWER_FORMATTER_SKILL_SLUG)
    if formatter is None or formatter.id != context['formatter_skill_id']:
        return [], None, 'formatter_skill_disabled'
    if len(selected) != len(context['skill_ids']) or any(
        _skill_fingerprint(skill) != context['skill_fingerprints'][str(skill.id)] for skill in selected
    ):
        return [], None, 'formatter_skill_changed'
    return selected, formatter, ''


def _update(state, context, node, *, status='completed', result=None, **details):
    from .langgraph_pilot import _append_trace

    update = {'formatter_context': _checkpoint_value(context),
              'trace': _append_trace(state, node, status=status, attempt=context['attempts'], **details)}
    if result is not None:
        update.update(result=result, runtime_status='completed')
    return update


def _blocked(state, context, node, exc):
    result = services._build_dispatch_error_result(str(exc), code='formatter_permission_denied')
    context = dict(context)
    context['next'] = 'validate'
    return _update(state, context, node, status='blocked', result=result, reason=str(exc))


def formatter_node(phase):
    node = 'formatter_' + phase

    def execute(state, config=None):
        context = copy.deepcopy(state['formatter_context'])
        try:
            user, agent_config = _guard(state, context)
        except services.ChatJobLeaseLost:
            raise
        except PermissionError as exc:
            return _blocked(state, context, node, exc)
        skills, formatter, issue = _skills(context, user, agent_config)
        if phase not in ('fallback', 'finish') and issue:
            context.update(reason=issue, next='formatter_fallback')
            return _update(state, context, node, status='skipped', reason=issue)
        if phase == 'prepare':
            context['next'] = 'formatter_model'
        elif phase == 'model':
            try:
                provider = _provider(context)
                if _provider_fingerprint(provider) != context['provider_fingerprint']:
                    raise ValueError('本轮模型提供商地址已变化，请重新发起问答。')
                context['attempts'] += 1
                context['content'] = services._request_answer_formatter_once(
                    provider, context, formatter_skill=formatter, active_skills=skills,
                    attempt=context['attempts'], previous_issue=context['previous_issue'],
                )
            except services.ChatJobLeaseLost:
                raise
            except Exception as exc:
                context.update(error=services._sanitize_mcp_error_text(str(exc))[:300],
                               reason='model_api_error' if isinstance(exc, services.AIOpsModelCallError) else 'formatter_error',
                               next='formatter_fallback')
                return _update(state, context, node, status='failed', error=context['error'])
            context['next'] = 'formatter_check'
        elif phase == 'check':
            issue = services._formatter_repair_issue(
                context['content'], **{key: context[key] for key in (
                    'fallback_content', 'collected_tool_outputs', 'pending_action_draft', 'message_type', 'profile',
                )},
            )
            context['previous_issue'] = issue
            context['checks'].append({'attempt': context['attempts'], 'issue': issue})
            context['next'] = 'formatter_repair' if issue else 'formatter_finish'
            return _update(state, context, node, status='failed' if issue else 'completed', reason=issue)
        elif phase == 'repair':
            context['content'] = ''
            context['next'] = 'formatter_model' if context['attempts'] < context['max_attempts'] else 'formatter_fallback'
            if context['next'] == 'formatter_fallback':
                context['reason'] = 'invalid_formatter_output'
        elif phase == 'fallback':
            context['content'] = context['fallback_content'] if context['model_error_policy'] == 'error' else context['base_content']
            context['next'] = 'formatter_finish'
            return _update(state, context, node, reason=context['reason'])
        elif phase == 'finish':
            if issue:
                context.update(content=context['base_content'], reason=issue)
            result = copy.deepcopy(state['result'])
            if context['reason'] == 'model_api_error' and context['model_error_policy'] == 'error':
                result = services._build_llm_api_error_result(context['error'])
            else:
                result['content'] = services._ensure_followup_line(
                    services._normalize_formatter_output(context['content']), result.get('citations') or [],
                )
                metadata = dict(result.get('metadata') or {})
                metadata.update(formatter_mode='fallback' if context['reason'] else 'skill',
                                formatter_attempts=context['attempts'])
                if context['error']:
                    metadata['formatter_error'] = context['error']
                metadata['skill_trace'] = services._mark_skill_trace_action_hit(
                    services._build_skill_trace(skills, formatter_result={
                        'used': bool(context['attempts']), 'fell_back': bool(context['reason']),
                    }, tool_calls=context['tool_calls']), metadata.get('selected_action'),
                )
                result['metadata'] = metadata
            result.setdefault('metadata', {}).update({
                'langgraph_formatter_checkpointed': True, 'formatter_reason': context['reason'] or 'formatted',
                'formatter_checks': context['checks'], 'formatter_attempts': context['attempts'],
            })
            context['next'] = 'validate'
            return _update(state, context, node, result=result, reason=context['reason'])
        return _update(state, context, node)
    return execute


def formatter_next(state):
    return state['formatter_context']['next']
