import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import timedelta

import requests
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    Alert,
    AlertAction,
    AlertAggregationRule,
    AlertClaim,
    AlertEscalationPolicy,
    AlertInhibitionRule,
    AlertIntegration,
    AlertInteractionToken,
    AlertMuteRule,
    AlertNotificationChannel,
    AlertNotificationLog,
    AlertNotificationRule,
    AlertRecipient,
    Host,
)


LEVEL_RANK = {'info': 1, 'warning': 2, 'critical': 3}
DEFAULT_GROUP_BY = ['source_type', 'environment', 'service', 'cluster', 'namespace', 'resource']
CARD_ACTIONS = ['claim', 'mute']


class SafeFormatDict(dict):
    def __missing__(self, key):
        return ''


def normalize_provider(provider):
    value = str(provider or '').strip().lower().replace('_', '-')
    aliases = {
        'alertmanager': Alert.SOURCE_PROMETHEUS,
        'prom': Alert.SOURCE_PROMETHEUS,
        'prometheus-alertmanager': Alert.SOURCE_PROMETHEUS,
        'prometheus': Alert.SOURCE_PROMETHEUS,
        'n9e': Alert.SOURCE_NIGHTINGALE,
        'nightingale': Alert.SOURCE_NIGHTINGALE,
        'aliyun': Alert.SOURCE_ALIYUN,
        'ali-cloud': Alert.SOURCE_ALIYUN,
        'cloudmonitor': Alert.SOURCE_ALIYUN,
        'zabbix': Alert.SOURCE_ZABBIX,
    }
    return aliases.get(value, value or Alert.SOURCE_GENERIC)


def resolve_integration(provider, token=''):
    provider = normalize_provider(provider)
    if not token:
        return None
    return AlertIntegration.objects.filter(provider=provider, token=token, is_enabled=True).first()


def _text(value, default=''):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _claim_records(alert):
    records = getattr(alert, '_prefetched_objects_cache', {}).get('claim_records')
    if records is not None:
        return list(records)
    return list(alert.claim_records.all())


def _claimant_names(alert):
    return [item.claimant for item in _claim_records(alert)]


def _has_claimants(alert):
    return bool(_claim_records(alert))


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    if value is None or value == '':
        return []
    if isinstance(value, list):
        return value
    return [value]


def _first(*values):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return ''


def _service_from_labels(labels, *fallbacks):
    labels = labels or {}
    return _text(_first(
        labels.get('app'),
        labels.get('job_name'),
        labels.get('service'),
        *fallbacks,
    ))


def _parse_time(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        if value > 100000000000:
            value = value / 1000
        return timezone.datetime.fromtimestamp(value, tz=timezone.get_current_timezone())
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if re.fullmatch(r'\d{10,13}', stripped):
            return _parse_time(int(stripped))
        parsed = parse_datetime(stripped)
        if parsed:
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            return parsed
    return None


def _parse_labels(value):
    if isinstance(value, dict):
        return {str(key): _text(val) for key, val in value.items() if key is not None}
    labels = {}
    if isinstance(value, list):
        parts = value
    elif isinstance(value, str):
        parts = re.split(r',,|,|\s+', value)
    else:
        parts = []
    for item in parts:
        text = _text(item)
        if not text or '=' not in text:
            continue
        key, val = text.split('=', 1)
        if key.strip():
            labels[key.strip()] = val.strip()
    return labels


def _severity_to_level(value, provider=''):
    text = _text(value).lower()
    if text in {'1'} and provider == Alert.SOURCE_NIGHTINGALE:
        return 'critical'
    if text in {'2'} and provider == Alert.SOURCE_NIGHTINGALE:
        return 'warning'
    if text in {'3'} and provider == Alert.SOURCE_NIGHTINGALE:
        return 'info'
    if text in {'5', '4'} and provider == Alert.SOURCE_ZABBIX:
        return 'critical'
    if text in {'3', '2'} and provider == Alert.SOURCE_ZABBIX:
        return 'warning'
    if text in {'critical', 'crit', 'fatal', 'emergency', 'disaster', 'high', 'p0', 'p1', 'sev0', 'sev1', '严重'}:
        return 'critical'
    if text in {'warning', 'warn', 'average', 'medium', 'minor', 'p2', 'p3', 'sev2', 'sev3', '告警', '警告'}:
        return 'warning'
    return 'info'


def _status_to_alert_status(value, payload=None):
    text = _text(value).lower()
    payload = payload or {}
    if text in {'resolved', 'resolve', 'ok', 'recovered', 'recovery', 'closed', '0'}:
        return Alert.STATUS_RESOLVED
    if text in {'problem', 'firing', 'alert', 'alerting', 'alarm', 'active', '1'}:
        return Alert.STATUS_ACTIVE
    for key in ['event_value', 'event.status', 'alertState', 'alert_state']:
        candidate = payload.get(key)
        if candidate is not None:
            resolved = _status_to_alert_status(candidate)
            if resolved:
                return resolved
    return Alert.STATUS_ACTIVE


def _host_for(resource, labels):
    candidates = [
        resource,
        labels.get('instance'),
        labels.get('host'),
        labels.get('hostname'),
        labels.get('node'),
        labels.get('ident'),
        labels.get('ip'),
    ]
    for candidate in candidates:
        text = _text(candidate)
        if not text:
            continue
        host = Host.objects.filter(Q(hostname=text) | Q(ip_address=text)).first()
        if host:
            return host
        if ':' in text:
            short = text.split(':', 1)[0]
            host = Host.objects.filter(Q(hostname=short) | Q(ip_address=short)).first()
            if host:
                return host
    return None


def _fingerprint(provider, fields):
    base = _first(fields.get('fingerprint'), fields.get('external_id'))
    if base:
        return hashlib.sha256(f'{provider}:{base}'.encode('utf-8')).hexdigest()
    stable = {
        'provider': provider,
        'title': fields.get('title'),
        'resource': fields.get('resource'),
        'metric_name': fields.get('metric_name'),
        'labels': fields.get('labels') or {},
    }
    payload = json.dumps(stable, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def alert_dimension_value(alert, key):
    key = str(key or '').strip()
    if not key:
        return ''
    if hasattr(alert, key):
        return _text(getattr(alert, key))
    labels = alert.labels or {}
    annotations = alert.annotations or {}
    if key.startswith('label.'):
        return _text(labels.get(key.split('.', 1)[1]))
    if key.startswith('annotation.'):
        return _text(annotations.get(key.split('.', 1)[1]))
    return _text(labels.get(key) or annotations.get(key))


def compute_group_key(alert, group_by=None):
    dims = group_by or DEFAULT_GROUP_BY
    values = [f'{key}={alert_dimension_value(alert, key) or "-"}' for key in dims]
    return ' | '.join(values)


def _normalize_prometheus(payload, integration=None):
    common_labels = _dict(payload.get('commonLabels'))
    common_annotations = _dict(payload.get('commonAnnotations'))
    group_key = _text(payload.get('groupKey'))
    alerts = payload.get('alerts') if isinstance(payload.get('alerts'), list) else [payload]
    normalized = []
    for item in alerts:
        labels = {**common_labels, **_dict(item.get('labels'))}
        annotations = {**common_annotations, **_dict(item.get('annotations'))}
        title = _first(annotations.get('summary'), labels.get('alertname'), item.get('title'), payload.get('title'), 'Prometheus 告警')
        resource = _first(labels.get('instance'), labels.get('pod'), labels.get('node'), labels.get('host'), labels.get('job'))
        message = _first(annotations.get('description'), annotations.get('message'), item.get('message'), title)
        normalized.append({
            'title': _text(title),
            'level': _severity_to_level(labels.get('severity'), Alert.SOURCE_PROMETHEUS),
            'status': _status_to_alert_status(item.get('status') or payload.get('status')),
            'source': _text(_first(labels.get('job'), labels.get('alertname'), 'Alertmanager')),
            'source_type': Alert.SOURCE_PROMETHEUS,
            'external_id': _text(_first(item.get('fingerprint'), item.get('generatorURL'))),
            'fingerprint': _text(item.get('fingerprint')),
            'group_key': group_key,
            'message': _text(message),
            'service': _service_from_labels(labels, labels.get('job')),
            'environment': _text(_first(labels.get('env'), labels.get('environment'))),
            'cluster': _text(labels.get('cluster')),
            'namespace': _text(labels.get('namespace')),
            'region': _text(_first(labels.get('region'), labels.get('az'))),
            'business_line': _text(_first(labels.get('business_line'), labels.get('team'), labels.get('busi_group'))),
            'resource_type': _text(_first(labels.get('resource_type'), labels.get('kind'), 'target')),
            'resource': _text(resource),
            'metric_name': _text(labels.get('__name__')),
            'runbook_url': _text(_first(annotations.get('runbook_url'), annotations.get('runbook'), item.get('generatorURL'))),
            'labels': labels,
            'annotations': annotations,
            'starts_at': _parse_time(item.get('startsAt') or payload.get('startsAt')),
            'ends_at': _parse_time(item.get('endsAt') or payload.get('endsAt')),
            'raw_payload': item,
        })
    return normalized


def _normalize_nightingale(payload, integration=None):
    events = payload.get('events') or payload.get('alerts') or payload.get('data') or payload
    if isinstance(events, dict):
        events = [events]
    normalized = []
    for item in _list(events):
        item = _dict(item)
        labels = _parse_labels(_first(item.get('tags_map'), item.get('tags'), item.get('tags_json')))
        annotations = _dict(item.get('annotations')) or _parse_labels(item.get('annotations'))
        title = _first(item.get('rule_name'), item.get('title'), annotations.get('summary'), '夜莺告警')
        resource = _first(item.get('target_ident'), item.get('target'), labels.get('ident'), labels.get('instance'), labels.get('host'))
        is_recovered = item.get('is_recovered')
        status_value = 'resolved' if is_recovered is True else _first(item.get('status'), item.get('event_status'), 'active')
        trigger_time = _first(item.get('trigger_time'), item.get('first_trigger_time'), item.get('created_at'))
        normalized.append({
            'title': _text(title),
            'level': _severity_to_level(_first(item.get('severity'), item.get('level')), Alert.SOURCE_NIGHTINGALE),
            'status': _status_to_alert_status(status_value),
            'source': _text(_first(item.get('cluster'), item.get('datasource_name'), item.get('cate'), 'Nightingale')),
            'source_type': Alert.SOURCE_NIGHTINGALE,
            'external_id': _text(_first(item.get('id'), item.get('event_id'), item.get('hash'))),
            'fingerprint': _text(item.get('hash')),
            'group_key': _text(_first(item.get('group_name'), item.get('group_id'))),
            'message': _text(_first(item.get('rule_note'), item.get('trigger_value'), annotations.get('description'), title)),
            'service': _service_from_labels(labels, item.get('rule_prod')),
            'environment': _text(_first(labels.get('env'), labels.get('environment'))),
            'cluster': _text(_first(item.get('cluster'), labels.get('cluster'))),
            'namespace': _text(labels.get('namespace')),
            'region': _text(labels.get('region')),
            'business_line': _text(_first(item.get('group_name'), labels.get('busi_group'), labels.get('team'))),
            'resource_type': _text(_first(labels.get('resource_type'), 'target')),
            'resource': _text(resource),
            'metric_name': _text(_first(item.get('prom_ql'), labels.get('__name__'))),
            'runbook_url': _text(item.get('runbook_url')),
            'labels': labels,
            'annotations': annotations,
            'starts_at': _parse_time(trigger_time),
            'ends_at': _parse_time(item.get('recover_time')),
            'raw_payload': item,
        })
    return normalized


def _normalize_zabbix(payload, integration=None):
    events = payload.get('alerts') or payload.get('events') or payload.get('data') or payload
    if isinstance(events, dict):
        events = [events]
    normalized = []
    for item in _list(events):
        item = _dict(item)
        tags = item.get('tags')
        labels = _parse_labels(tags)
        host_value = _first(item.get('host'), item.get('hostname'), item.get('host_name'), item.get('host.name'))
        if isinstance(item.get('hosts'), list) and item.get('hosts'):
            host_value = _first(host_value, item['hosts'][0].get('host'), item['hosts'][0].get('name'))
        title = _first(item.get('trigger_name'), item.get('event_name'), item.get('subject'), item.get('name'), 'Zabbix 告警')
        message = _first(item.get('message'), item.get('body'), item.get('trigger_description'), title)
        status_value = _first(item.get('status'), item.get('event_status'), item.get('event_value'), item.get('value'))
        normalized.append({
            'title': _text(title),
            'level': _severity_to_level(_first(item.get('severity'), item.get('trigger_severity'), item.get('priority')), Alert.SOURCE_ZABBIX),
            'status': _status_to_alert_status(status_value, item),
            'source': _text(_first(item.get('source'), 'Zabbix')),
            'source_type': Alert.SOURCE_ZABBIX,
            'external_id': _text(_first(item.get('eventid'), item.get('event_id'), item.get('triggerid'), item.get('trigger_id'))),
            'fingerprint': _text(_first(item.get('triggerid'), item.get('trigger_id'), item.get('eventid'))),
            'group_key': _text(_first(item.get('hostgroup'), item.get('host_group'), labels.get('group'))),
            'message': _text(message),
            'service': _service_from_labels(labels, item.get('application')),
            'environment': _text(_first(labels.get('env'), labels.get('environment'))),
            'cluster': _text(labels.get('cluster')),
            'namespace': _text(labels.get('namespace')),
            'region': _text(labels.get('region')),
            'business_line': _text(_first(labels.get('business_line'), labels.get('team'), item.get('hostgroup'))),
            'resource_type': 'host',
            'resource': _text(host_value),
            'metric_name': _text(_first(item.get('metric'), item.get('item_name'), item.get('key'))),
            'runbook_url': _text(item.get('url')),
            'labels': labels,
            'annotations': {'opdata': _text(item.get('opdata')), 'recovery_message': _text(item.get('recovery_message'))},
            'starts_at': _parse_time(_first(item.get('event_time'), item.get('clock'), item.get('time'))),
            'ends_at': _parse_time(_first(item.get('recovery_time'), item.get('r_clock'))),
            'raw_payload': item,
        })
    return normalized


def _normalize_aliyun(payload, integration=None):
    events = payload.get('alerts') or payload.get('data') or payload.get('events') or payload
    if isinstance(events, dict):
        events = [events]
    normalized = []
    for item in _list(events):
        item = _dict(item)
        dimensions = _dict(item.get('dimensions'))
        labels = {**dimensions}
        for key in ['namespace', 'metricName', 'instanceId', 'ruleId', 'regionId', 'product']:
            if item.get(key) is not None:
                labels[key] = _text(item.get(key))
        title = _first(item.get('alertName'), item.get('ruleName'), item.get('name'), '阿里云监控告警')
        resource = _first(item.get('instanceName'), item.get('instanceId'), dimensions.get('instanceId'), dimensions.get('userId'))
        status_value = _first(item.get('alertState'), item.get('state'), item.get('status'))
        normalized.append({
            'title': _text(title),
            'level': _severity_to_level(_first(item.get('level'), item.get('severity'), item.get('warnLevel')), Alert.SOURCE_ALIYUN),
            'status': _status_to_alert_status(status_value),
            'source': _text(_first(item.get('namespace'), item.get('product'), 'Aliyun CloudMonitor')),
            'source_type': Alert.SOURCE_ALIYUN,
            'external_id': _text(_first(item.get('alertId'), item.get('ruleId'), item.get('eventId'))),
            'fingerprint': _text(':'.join(filter(None, [_text(item.get('ruleId')), _text(resource), _text(item.get('metricName'))]))),
            'group_key': _text(_first(item.get('groupId'), item.get('contactGroups'))),
            'message': _text(_first(item.get('message'), item.get('content'), item.get('curValue'), title)),
            'service': _service_from_labels(labels, item.get('product'), item.get('namespace')),
            'environment': _text(_first(item.get('env'), dimensions.get('env'))),
            'cluster': _text(dimensions.get('cluster')),
            'namespace': _text(_first(item.get('namespace'), dimensions.get('namespace'))),
            'region': _text(_first(item.get('regionId'), item.get('region'), dimensions.get('regionId'))),
            'business_line': _text(_first(item.get('groupName'), dimensions.get('team'))),
            'resource_type': _text(_first(item.get('product'), item.get('namespace'), 'cloud_resource')),
            'resource': _text(resource),
            'metric_name': _text(item.get('metricName')),
            'runbook_url': _text(item.get('url')),
            'labels': labels,
            'annotations': {'curValue': _text(item.get('curValue')), 'expression': _text(item.get('expression'))},
            'starts_at': _parse_time(_first(item.get('timestamp'), item.get('lastTime'), item.get('startTime'))),
            'ends_at': _parse_time(item.get('endTime')),
            'raw_payload': item,
        })
    return normalized


def _normalize_generic(payload, integration=None, provider=Alert.SOURCE_GENERIC):
    labels = _parse_labels(payload.get('labels') or payload.get('tags'))
    annotations = _dict(payload.get('annotations'))
    title = _first(payload.get('title'), payload.get('name'), payload.get('alertname'), labels.get('alertname'), 'Webhook 告警')
    normalized = [{
        'title': _text(title),
        'level': _severity_to_level(_first(payload.get('level'), payload.get('severity'), labels.get('severity')), provider),
        'status': _status_to_alert_status(_first(payload.get('status'), payload.get('state'))),
        'source': _text(_first(payload.get('source'), provider)),
        'source_type': provider,
        'external_id': _text(_first(payload.get('id'), payload.get('event_id'), payload.get('external_id'))),
        'fingerprint': _text(payload.get('fingerprint')),
        'group_key': _text(payload.get('group_key')),
        'message': _text(_first(payload.get('message'), payload.get('description'), annotations.get('description'), title)),
        'service': _service_from_labels(labels, payload.get('service')),
        'environment': _text(_first(payload.get('environment'), payload.get('env'), labels.get('environment'), labels.get('env'))),
        'cluster': _text(_first(payload.get('cluster'), labels.get('cluster'))),
        'namespace': _text(_first(payload.get('namespace'), labels.get('namespace'))),
        'region': _text(_first(payload.get('region'), labels.get('region'))),
        'business_line': _text(_first(payload.get('business_line'), labels.get('business_line'), labels.get('team'))),
        'resource_type': _text(_first(payload.get('resource_type'), labels.get('resource_type'))),
        'resource': _text(_first(payload.get('resource'), payload.get('instance'), labels.get('instance'), labels.get('host'))),
        'metric_name': _text(_first(payload.get('metric_name'), labels.get('__name__'))),
        'runbook_url': _text(_first(payload.get('runbook_url'), annotations.get('runbook_url'))),
        'labels': labels,
        'annotations': annotations,
        'starts_at': _parse_time(_first(payload.get('starts_at'), payload.get('startsAt'), payload.get('time'))),
        'ends_at': _parse_time(_first(payload.get('ends_at'), payload.get('endsAt'))),
        'raw_payload': payload,
    }]
    return normalized


def normalize_alert_payload(provider, payload, integration=None):
    provider = normalize_provider(provider)
    payload = _dict(payload)
    default_labels = _dict(getattr(integration, 'default_labels', None))
    if provider == Alert.SOURCE_PROMETHEUS:
        alerts = _normalize_prometheus(payload, integration)
    elif provider == Alert.SOURCE_ZABBIX:
        alerts = _normalize_zabbix(payload, integration)
    elif provider == Alert.SOURCE_NIGHTINGALE:
        alerts = _normalize_nightingale(payload, integration)
    elif provider == Alert.SOURCE_ALIYUN:
        alerts = _normalize_aliyun(payload, integration)
    else:
        alerts = _normalize_generic(payload, integration, provider)
    for alert in alerts:
        alert['source_type'] = provider
        alert['labels'] = {**default_labels, **_dict(alert.get('labels'))}
        labels = alert['labels']
        for field, aliases in {
            'environment': ('env', 'environment'), 'cluster': ('cluster',),
            'namespace': ('namespace',), 'region': ('region', 'az'),
            'business_line': ('business_line', 'team', 'busi_group'),
        }.items():
            if not alert.get(field):
                alert[field] = _text(_first(*(labels.get(key) for key in aliases)))
        if not alert.get('service'):
            alert['service'] = _service_from_labels(labels)
        alert['fingerprint'] = _fingerprint(provider, alert)
        if not alert.get('starts_at'):
            alert['starts_at'] = timezone.now()
        if not alert.get('last_received_at'):
            alert['last_received_at'] = timezone.now()
    return alerts


def _save_action(alert, action, actor='', note='', metadata=None):
    return AlertAction.objects.create(
        alert=alert,
        action=action,
        actor=actor or '',
        note=note or '',
        metadata=metadata or {},
    )


def upsert_alert(normalized, integration=None, actor='webhook'):
    now = timezone.now()
    status_value = normalized.get('status') or Alert.STATUS_ACTIVE
    fingerprint = normalized.get('fingerprint') or _fingerprint(normalized.get('source_type'), normalized)
    existing = Alert.objects.filter(fingerprint=fingerprint).exclude(status=Alert.STATUS_CLOSED).order_by('-created_at').first()

    defaults = {
        'integration': integration,
        'title': normalized.get('title') or '告警事件',
        'level': normalized.get('level') or 'info',
        'status': status_value,
        'source': normalized.get('source') or normalized.get('source_type') or 'webhook',
        'source_type': normalized.get('source_type') or Alert.SOURCE_GENERIC,
        'external_id': normalized.get('external_id') or '',
        'fingerprint': fingerprint,
        'group_key': normalized.get('group_key') or '',
        'message': normalized.get('message') or '',
        'service': normalized.get('service') or '',
        'environment': normalized.get('environment') or '',
        'cluster': normalized.get('cluster') or '',
        'namespace': normalized.get('namespace') or '',
        'region': normalized.get('region') or '',
        'business_line': normalized.get('business_line') or '',
        'resource_type': normalized.get('resource_type') or '',
        'resource': normalized.get('resource') or '',
        'metric_name': normalized.get('metric_name') or '',
        'runbook_url': normalized.get('runbook_url') or '',
        'labels': normalized.get('labels') or {},
        'annotations': normalized.get('annotations') or {},
        'raw_payload': normalized.get('raw_payload') or {},
        'starts_at': normalized.get('starts_at'),
        'ends_at': normalized.get('ends_at') if status_value == Alert.STATUS_RESOLVED else None,
        'last_received_at': now,
    }
    defaults['host'] = _host_for(defaults['resource'], defaults['labels'])

    created = existing is None
    if created:
        alert = Alert.objects.create(**defaults)
    else:
        alert = existing
        was_resolved = alert.status == Alert.STATUS_RESOLVED
        for field, value in defaults.items():
            if field == 'starts_at' and alert.starts_at:
                continue
            setattr(alert, field, value)
        alert.occurrence_count = alert.occurrence_count + 1
        if status_value == Alert.STATUS_ACTIVE and was_resolved:
            alert.is_acknowledged = False
            alert.acknowledged_by = ''
            alert.acknowledged_at = None
            alert.ends_at = None
        alert.save()

    if not alert.group_key:
        alert.group_key = compute_group_key(alert)
        alert.save(update_fields=['group_key'])

    _save_action(
        alert,
        AlertAction.ACTION_WEBHOOK,
        actor=actor,
        note='Webhook 告警接入' if created else 'Webhook 告警更新',
        metadata={'created': created, 'source_type': alert.source_type},
    )
    return alert, created


def _alert_value_map(alert):
    values = {
        'title': alert.title,
        'level': alert.level,
        'status': alert.status,
        'source': alert.source,
        'source_type': alert.source_type,
        'service': alert.service,
        'environment': alert.environment,
        'cluster': alert.cluster,
        'namespace': alert.namespace,
        'region': alert.region,
        'business_line': alert.business_line,
        'resource_type': alert.resource_type,
        'resource': alert.resource,
        'metric_name': alert.metric_name,
        'claimed_by': alert.claimed_by,
    }
    values.update({f'label.{key}': value for key, value in (alert.labels or {}).items()})
    values.update({f'annotation.{key}': value for key, value in (alert.annotations or {}).items()})
    for key, value in (alert.labels or {}).items():
        values.setdefault(key, value)
    return {key: _text(value) for key, value in values.items()}


def match_matchers(alert, matchers):
    if not matchers:
        return True
    values = _alert_value_map(alert)
    if isinstance(matchers, dict):
        matchers = [{'key': key, 'op': '==', 'value': value} for key, value in matchers.items()]
    for matcher in _list(matchers):
        if not isinstance(matcher, dict):
            continue
        key = _text(matcher.get('key') or matcher.get('label'))
        op = _text(matcher.get('op') or matcher.get('func') or '==')
        expected = matcher.get('value')
        actual = values.get(key, '')
        if op in {'==', '='} and actual != _text(expected):
            return False
        if op == '!=' and actual == _text(expected):
            return False
        if op in {'=~', 'regex'} and not re.search(_text(expected), actual):
            return False
        if op == '!~' and re.search(_text(expected), actual):
            return False
        if op == 'contains' and _text(expected) not in actual:
            return False
        if op in {'in', 'not in'}:
            expected_values = [_text(item) for item in _list(expected)]
            hit = actual in expected_values
            if op == 'in' and not hit:
                return False
            if op == 'not in' and hit:
                return False
    return True


def apply_alert_suppression(alert):
    now = timezone.now()
    changed = False
    mute = AlertMuteRule.objects.filter(is_enabled=True).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now),
        Q(ends_at__isnull=True) | Q(ends_at__gte=now),
    ).order_by('-created_at').first()
    matched_mute = None
    for rule in AlertMuteRule.objects.filter(is_enabled=True).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now),
        Q(ends_at__isnull=True) | Q(ends_at__gte=now),
    ):
        if match_matchers(alert, rule.matchers):
            matched_mute = rule
            break
    if matched_mute:
        alert.status = Alert.STATUS_MUTED
        alert.is_suppressed = True
        alert.suppressed_by = f'mute:{matched_mute.name}'
        alert.suppressed_until = matched_mute.ends_at
        alert.mute_until = matched_mute.ends_at
        alert.muted_reason = matched_mute.reason
        changed = True
    elif alert.mute_until and alert.mute_until > now:
        alert.status = Alert.STATUS_MUTED
        alert.is_suppressed = True
        alert.suppressed_by = 'manual_mute'
        alert.suppressed_until = alert.mute_until
        changed = True
    else:
        inhibited_by = None
        inhibit_until = None
        for rule in AlertInhibitionRule.objects.filter(is_enabled=True):
            if not match_matchers(alert, rule.target_matchers):
                continue
            source_qs = Alert.objects.filter(status=Alert.STATUS_ACTIVE).exclude(pk=alert.pk)
            for source_alert in source_qs[:300]:
                if not match_matchers(source_alert, rule.source_matchers):
                    continue
                equal_labels = rule.equal_labels or []
                if all(alert_dimension_value(alert, key) == alert_dimension_value(source_alert, key) for key in equal_labels):
                    inhibited_by = rule
                    inhibit_until = now + timedelta(minutes=rule.duration_minutes)
                    break
            if inhibited_by:
                break
        alert.is_suppressed = bool(inhibited_by)
        alert.suppressed_by = f'inhibit:{inhibited_by.name}' if inhibited_by else ''
        alert.suppressed_until = inhibit_until
        changed = True
    if changed:
        alert.save(update_fields=['status', 'is_suppressed', 'suppressed_by', 'suppressed_until', 'mute_until', 'muted_reason', 'updated_at'])
    return alert


def _base_url(request=None):
    if request:
        return request.build_absolute_uri('/').rstrip('/')
    return str(
        getattr(settings, 'SXDEVOPS_PUBLIC_BASE_URL', '')
        or getattr(settings, 'AGDEVOPS_PUBLIC_BASE_URL', '')
        or ''
    ).rstrip('/')


def _interaction_url(alert, action, provider='', request=None):
    token = AlertInteractionToken.objects.create(
        alert=alert,
        action=action,
        provider=provider or '',
        expires_at=timezone.now() + timedelta(days=7),
    )
    base = _base_url(request)
    if not base:
        return ''
    return f'{base}/api/alerts/card-actions/{token.token}/'


def _alert_context(alert, action='fire'):
    return {
        'id': alert.id,
        'title': alert.title,
        'level': alert.level,
        'status': alert.status,
        'source': alert.source,
        'source_type': alert.source_type,
        'service': alert.service,
        'environment': alert.environment,
        'cluster': alert.cluster,
        'namespace': alert.namespace,
        'resource': alert.resource,
        'metric_name': alert.metric_name,
        'message': alert.message,
        'claimants': '、'.join(_claimant_names(alert)),
        'runbook_url': alert.runbook_url,
        'starts_at': alert.starts_at.isoformat() if alert.starts_at else '',
        'last_received_at': alert.last_received_at.isoformat() if alert.last_received_at else '',
        'action': action,
        'group_key': alert.group_key,
        'occurrence_count': alert.occurrence_count,
    }


def _render(value, alert, action='fire'):
    template = _text(value)
    context = SafeFormatDict(_alert_context(alert, action))
    if not template:
        return ''
    try:
        return template.format_map(context)
    except Exception:
        return template


def _default_title(alert, action='fire'):
    prefix = {
        'fire': '告警触发',
        'resolved': '告警恢复',
        'escalation': '告警升级',
        'test': '告警测试',
    }.get(action, '告警通知')
    return f'[{prefix}] {alert.title}'


def _default_body(alert, action='fire'):
    lines = [
        f'级别: {alert.get_level_display()}',
        f'状态: {alert.get_status_display()}',
        f'来源: {alert.source_type} / {alert.source}',
        f'对象: {alert.resource or alert.host.hostname if alert.host else alert.resource or "-"}',
        f'服务: {alert.service or "-"}',
        f'环境: {alert.environment or "-"}',
        f'时间: {alert.starts_at.strftime("%Y-%m-%d %H:%M:%S") if alert.starts_at else "-"}',
        '',
        alert.message or alert.title,
    ]
    if alert.runbook_url:
        lines.append(f'Runbook: {alert.runbook_url}')
    return '\n'.join(lines)


def _recipient_contacts(rule):
    result = defaultdict(set)
    names = set()
    recipients = set(rule.recipients.filter(is_enabled=True))
    for group in rule.recipient_groups.filter(is_enabled=True).prefetch_related('recipients', 'users'):
        recipients.update(group.recipients.filter(is_enabled=True))
        for user in group.users.filter(is_active=True):
            names.add(user.get_full_name() or user.username)
            if user.email:
                result['emails'].add(user.email)
    for recipient in recipients:
        names.add(recipient.name)
        if recipient.email:
            result['emails'].add(recipient.email)
        if recipient.phone:
            result['phones'].add(recipient.phone)
        if recipient.dingtalk_user_id:
            result['dingtalk_user_ids'].add(recipient.dingtalk_user_id)
        if recipient.feishu_user_id:
            result['feishu_user_ids'].add(recipient.feishu_user_id)
        if recipient.wecom_user_id:
            result['wecom_user_ids'].add(recipient.wecom_user_id)
        if recipient.user and recipient.user.email:
            result['emails'].add(recipient.user.email)
    result['names'] = names
    return {key: sorted(value) for key, value in result.items()}


def _post_json(url, payload, timeout=8, headers=None):
    response = requests.post(url, json=payload, timeout=timeout, headers=headers or {})
    text = response.text[:1000]
    if response.status_code >= 400:
        raise RuntimeError(f'HTTP {response.status_code}: {text}')
    return text


def _channel_url(channel):
    config = channel.config or {}
    url = _text(config.get('webhook_url') or config.get('url'))
    if url:
        return url
    token = _text(config.get('access_token') or config.get('token'))
    if channel.channel_type == AlertNotificationChannel.CHANNEL_DINGTALK and token:
        return f'https://oapi.dingtalk.com/robot/send?access_token={token}'
    if channel.channel_type == AlertNotificationChannel.CHANNEL_WECOM and token:
        return f'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={token}'
    return ''


def _card_buttons(alert, provider, request=None):
    labels = {
        'acknowledge': '确认',
        'claim': '认领',
        'mute': '屏蔽 1 小时',
        'escalate': '升级',
    }
    buttons = []
    for action in CARD_ACTIONS:
        url = _interaction_url(alert, action, provider=provider, request=request)
        if url:
            buttons.append({'action': action, 'title': labels[action], 'url': url})
    return buttons


def send_alert_notification(channel, alert, recipients, action='fire', rule=None, request=None):
    config = channel.config or {}
    title = _render(channel.template_title, alert, action) or _default_title(alert, action)
    body = _render(channel.template_body, alert, action) or _default_body(alert, action)
    status = AlertNotificationLog.STATUS_SUCCESS
    response_body = ''
    error_message = ''
    request_summary = {'channel_type': channel.channel_type, 'title': title, 'action': action, 'group_key': alert.group_key}

    try:
        if channel.channel_type == AlertNotificationChannel.CHANNEL_EMAIL:
            emails = sorted(set(_list(config.get('to')) + recipients.get('emails', [])))
            if not emails:
                status = AlertNotificationLog.STATUS_SKIPPED
                response_body = '没有可用邮箱接收人'
            else:
                EmailMessage(title, body, getattr(settings, 'DEFAULT_FROM_EMAIL', None), emails).send(fail_silently=False)
                response_body = f'sent email to {len(emails)} recipients'
                request_summary['recipient_count'] = len(emails)
        elif channel.channel_type in {AlertNotificationChannel.CHANNEL_SMS, AlertNotificationChannel.CHANNEL_VOICE}:
            phones = sorted(set(_list(config.get('phones')) + recipients.get('phones', [])))
            url = _channel_url(channel)
            if not phones or not url:
                status = AlertNotificationLog.STATUS_SKIPPED
                response_body = '没有手机号或渠道 webhook_url'
            else:
                payload = {'phones': phones, 'title': title, 'content': body, 'alert': _alert_context(alert, action), 'config': {k: v for k, v in config.items() if k not in {'token', 'access_token', 'secret'}}}
                request_summary['recipient_count'] = len(phones)
                response_body = _post_json(url, payload, timeout=channel.timeout_seconds)
        elif channel.channel_type == AlertNotificationChannel.CHANNEL_DINGTALK:
            url = _channel_url(channel)
            if not url:
                status = AlertNotificationLog.STATUS_SKIPPED
                response_body = '未配置钉钉 webhook_url 或 access_token'
            else:
                buttons = _card_buttons(alert, 'dingtalk', request=request)
                payload = {
                    'msgtype': 'actionCard',
                    'actionCard': {
                        'title': title,
                        'text': body.replace('\n', '\n\n'),
                        'btnOrientation': '0',
                        'btns': [{'title': item['title'], 'actionURL': item['url']} for item in buttons],
                    },
                }
                if not buttons:
                    payload = {'msgtype': 'markdown', 'markdown': {'title': title, 'text': body}}
                request_summary['buttons'] = [item['action'] for item in buttons]
                response_body = _post_json(url, payload, timeout=channel.timeout_seconds)
        elif channel.channel_type == AlertNotificationChannel.CHANNEL_FEISHU:
            url = _channel_url(channel)
            if not url:
                status = AlertNotificationLog.STATUS_SKIPPED
                response_body = '未配置飞书 webhook_url'
            else:
                buttons = _card_buttons(alert, 'feishu', request=request)
                payload = {
                    'msg_type': 'interactive',
                    'card': {
                        'config': {'wide_screen_mode': True, 'enable_forward': True},
                        'header': {'template': 'red' if alert.level == 'critical' else 'orange', 'title': {'tag': 'plain_text', 'content': title}},
                        'elements': [
                            {'tag': 'markdown', 'content': body},
                            {'tag': 'action', 'actions': [
                                {'tag': 'button', 'text': {'tag': 'plain_text', 'content': item['title']}, 'url': item['url'], 'type': 'primary' if item['action'] == 'acknowledge' else 'default'}
                                for item in buttons
                            ]},
                        ],
                    },
                }
                request_summary['buttons'] = [item['action'] for item in buttons]
                response_body = _post_json(url, payload, timeout=channel.timeout_seconds)
        elif channel.channel_type == AlertNotificationChannel.CHANNEL_WECOM:
            url = _channel_url(channel)
            if not url:
                status = AlertNotificationLog.STATUS_SKIPPED
                response_body = '未配置企微 webhook_url 或 key'
            else:
                button_text = '\n'.join([f'[{item["title"]}]({item["url"]})' for item in _card_buttons(alert, 'wecom', request=request)])
                payload = {'msgtype': 'markdown', 'markdown': {'content': f'**{title}**\n\n{body}\n\n{button_text}'}}
                response_body = _post_json(url, payload, timeout=channel.timeout_seconds)
        else:
            status = AlertNotificationLog.STATUS_SKIPPED
            response_body = '未知通知渠道'
    except Exception as exc:
        status = AlertNotificationLog.STATUS_ERROR
        error_message = str(exc)

    log = AlertNotificationLog.objects.create(
        alert=alert,
        rule=rule,
        channel=channel,
        action=action,
        status=status,
        recipient_summary=', '.join(recipients.get('names', [])[:20]),
        request_payload=request_summary,
        response_body=response_body,
        error_message=error_message,
        sent_at=timezone.now() if status == AlertNotificationLog.STATUS_SUCCESS else None,
    )
    _save_action(alert, AlertAction.ACTION_NOTIFY, actor='system', note=f'{channel.name}: {log.get_status_display()}', metadata={'channel_type': channel.channel_type, 'log_id': log.id})
    return log


def _rule_can_send(rule, alert, action):
    if not rule.is_enabled:
        return False
    if action == 'resolved' and not rule.notify_on_resolved:
        return False
    if action == 'escalation' and not rule.notify_on_escalation:
        return False
    if action == 'fire' and not rule.notify_on_fire:
        return False
    if rule.min_level and LEVEL_RANK.get(alert.level, 0) < LEVEL_RANK.get(rule.min_level, 0):
        return False
    return match_matchers(alert, rule.matchers)


def dispatch_alert_notifications(alert, action='fire', request=None, force=False):
    if not force and (alert.is_suppressed or alert.status == Alert.STATUS_MUTED):
        return []
    if action == 'resolved' and alert.status != Alert.STATUS_RESOLVED:
        return []
    logs = []
    rules = AlertNotificationRule.objects.filter(is_enabled=True).prefetch_related('channels', 'recipients', 'recipient_groups__recipients', 'recipient_groups__users')
    for rule in rules:
        if not _rule_can_send(rule, alert, action):
            continue
        recipients = _recipient_contacts(rule)
        channels = [channel for channel in rule.channels.all() if channel.is_enabled]
        if action == 'resolved':
            channels = [channel for channel in channels if channel.send_resolved]
        if not channels:
            continue
        aggregation = rule.aggregation_rule
        if aggregation and aggregation.is_enabled:
            group_key = compute_group_key(alert, aggregation.group_by or DEFAULT_GROUP_BY)
            alert.group_key = group_key
            alert.save(update_fields=['group_key', 'updated_at'])
            since = timezone.now() - timedelta(minutes=aggregation.repeat_interval_minutes)
            if not force and AlertNotificationLog.objects.filter(alert=alert, rule=rule, action=action, created_at__gte=since, status=AlertNotificationLog.STATUS_SUCCESS).exists():
                continue
        for channel in channels:
            logs.append(send_alert_notification(channel, alert, recipients, action=action, rule=rule, request=request))
    return logs


def apply_escalation_policy(alert, request=None):
    if alert.status not in {Alert.STATUS_ACTIVE, Alert.STATUS_MUTED}:
        return False
    policy = matching_escalation_policy(alert)
    if not policy or not policy.levels:
        return False
    now = timezone.now()
    started_at = alert.starts_at or alert.created_at or now
    duration_minutes = max(int((now - started_at).total_seconds() // 60), 0)
    target_level = alert.escalation_level
    matched_level = None
    for index, item in enumerate(policy.levels):
        try:
            after_minutes = int(item.get('after_minutes') or item.get('minutes') or 0)
        except (TypeError, ValueError):
            after_minutes = 0
        if duration_minutes >= after_minutes and index + 1 > target_level:
            target_level = index + 1
            matched_level = item
    if target_level <= alert.escalation_level:
        return False
    alert.escalation_level = target_level
    alert.escalated_at = now
    alert.save(update_fields=['escalation_level', 'escalated_at', 'updated_at'])
    _save_action(
        alert,
        AlertAction.ACTION_ESCALATE,
        actor='system',
        note=f'命中升级策略 {policy.name}',
        metadata={'policy_id': policy.id, 'level': matched_level or {}, 'duration_minutes': duration_minutes},
    )
    dispatch_alert_notifications(alert, action='escalation', request=request, force=True)
    return True


def ingest_webhook(provider, payload, integration=None, request=None):
    provider = normalize_provider(provider)
    normalized_alerts = normalize_alert_payload(provider, payload, integration=integration)
    created_count = 0
    updated_count = 0
    alerts = []
    notification_actions = []
    with transaction.atomic():
        if integration:
            integration.last_received_at = timezone.now()
            integration.save(update_fields=['last_received_at', 'updated_at'])
        for item in normalized_alerts:
            alert, created = upsert_alert(item, integration=integration, actor=provider)
            apply_alert_suppression(alert)
            apply_escalation_policy(alert, request=request)
            action = 'resolved' if alert.status == Alert.STATUS_RESOLVED else 'fire'
            notification_actions.append((alert, action))
            created_count += 1 if created else 0
            updated_count += 0 if created else 1
            alerts.append(alert)
    for alert, action in notification_actions:
        dispatch_alert_notifications(alert, action=action, request=request)
    return {'created': created_count, 'updated': updated_count, 'alerts': alerts}


def apply_alert_action(alert, action, actor='', note='', metadata=None, request=None, mute_minutes=60):
    now = timezone.now()
    metadata = metadata or {}
    if action == AlertAction.ACTION_ACKNOWLEDGE:
        alert.is_acknowledged = True
        alert.acknowledged_by = actor
        alert.acknowledged_at = now
        update_fields = ['is_acknowledged', 'acknowledged_by', 'acknowledged_at', 'updated_at']
    elif action == AlertAction.ACTION_CLAIM:
        if actor:
            AlertClaim.objects.get_or_create(alert=alert, claimant=actor)
        getattr(alert, '_prefetched_objects_cache', {}).pop('claim_records', None)
        claim_records = _claim_records(alert)
        alert.claimed_by = claim_records[0].claimant if claim_records else (actor or '')
        alert.claimed_at = claim_records[0].claimed_at if claim_records else now
        update_fields = ['claimed_by', 'claimed_at', 'updated_at']
    elif action == AlertAction.ACTION_UNCLAIM:
        if actor:
            AlertClaim.objects.filter(alert=alert, claimant=actor).delete()
        getattr(alert, '_prefetched_objects_cache', {}).pop('claim_records', None)
        claim_records = _claim_records(alert)
        alert.claimed_by = claim_records[0].claimant if claim_records else ''
        alert.claimed_at = claim_records[0].claimed_at if claim_records else None
        update_fields = ['claimed_by', 'claimed_at', 'updated_at']
    elif action == AlertAction.ACTION_MUTE:
        alert.status = Alert.STATUS_MUTED
        alert.is_suppressed = True
        alert.suppressed_by = 'manual_mute'
        alert.suppressed_until = now + timedelta(minutes=mute_minutes)
        alert.mute_until = alert.suppressed_until
        alert.muted_by = actor
        alert.muted_reason = note or f'屏蔽 {mute_minutes} 分钟'
        update_fields = ['status', 'is_suppressed', 'suppressed_by', 'suppressed_until', 'mute_until', 'muted_by', 'muted_reason', 'updated_at']
    elif action == AlertAction.ACTION_ESCALATE:
        alert.escalation_level = alert.escalation_level + 1
        alert.escalated_at = now
        update_fields = ['escalation_level', 'escalated_at', 'updated_at']
    elif action == AlertAction.ACTION_RESOLVE:
        alert.status = Alert.STATUS_RESOLVED
        alert.ends_at = now
        update_fields = ['status', 'ends_at', 'updated_at']
    elif action == AlertAction.ACTION_CLOSE:
        alert.status = Alert.STATUS_CLOSED
        alert.closed_at = now
        update_fields = ['status', 'closed_at', 'updated_at']
    elif action == AlertAction.ACTION_REOPEN:
        alert.status = Alert.STATUS_ACTIVE
        alert.closed_at = None
        alert.ends_at = None
        alert.is_acknowledged = False
        alert.is_suppressed = False
        update_fields = ['status', 'closed_at', 'ends_at', 'is_acknowledged', 'is_suppressed', 'updated_at']
    else:
        update_fields = ['updated_at']
    alert.save(update_fields=update_fields)
    action_record = _save_action(alert, action, actor=actor, note=note, metadata=metadata)
    if action == AlertAction.ACTION_ESCALATE:
        dispatch_alert_notifications(alert, action='escalation', request=request, force=True)
    return action_record


def handle_interaction_token(token_value, request=None):
    token = AlertInteractionToken.objects.select_related('alert').filter(token=token_value).first()
    if not token:
        return False, '交互令牌不存在', None
    if not token.is_available:
        return False, '交互令牌已过期或已使用', token.alert
    actor = f'card:{token.provider or "unknown"}'
    note = '卡片按钮操作'
    apply_alert_action(token.alert, token.action, actor=actor, note=note, metadata={'token': str(token.token)}, request=request)
    token.used_at = timezone.now()
    token.save(update_fields=['used_at'])
    return True, '告警操作已处理', token.alert


def alert_group_summary(queryset, group_by=None, limit=5000):
    group_by = [item for item in (group_by or DEFAULT_GROUP_BY) if item]
    groups = {}
    for alert in queryset.order_by('-created_at')[:limit]:
        values = {key: alert_dimension_value(alert, key) or '-' for key in group_by}
        key = ' | '.join([f'{name}={value}' for name, value in values.items()])
        if key not in groups:
            groups[key] = {
                'key': key,
                'dimensions': values,
                'total': 0,
                'critical': 0,
                'warning': 0,
                'info': 0,
                'unacknowledged': 0,
                'suppressed': 0,
                'latest_at': None,
                'sample_alert_id': None,
                'sample_title': '',
            }
        item = groups[key]
        item['total'] += 1
        item[alert.level] = item.get(alert.level, 0) + 1
        if not _has_claimants(alert):
            item['unacknowledged'] += 1
        if alert.is_suppressed or alert.status == Alert.STATUS_MUTED:
            item['suppressed'] += 1
        if not item['latest_at'] or alert.created_at > item['latest_at']:
            item['latest_at'] = alert.created_at
            item['sample_alert_id'] = alert.id
            item['sample_title'] = alert.title
    data = list(groups.values())
    for item in data:
        item['latest_at'] = item['latest_at'].isoformat() if item['latest_at'] else ''
    data.sort(key=lambda item: (item['critical'], item['warning'], item['total']), reverse=True)
    return data


def alert_summary(queryset):
    alerts = list(queryset)
    level_counter = Counter(alert.level for alert in alerts)
    status_counter = Counter(alert.status for alert in alerts)
    return {
        'total': len(alerts),
        'critical': level_counter.get('critical', 0),
        'warning': level_counter.get('warning', 0),
        'info': level_counter.get('info', 0),
        'active': status_counter.get(Alert.STATUS_ACTIVE, 0),
        'resolved': status_counter.get(Alert.STATUS_RESOLVED, 0),
        'muted': status_counter.get(Alert.STATUS_MUTED, 0),
        'closed': status_counter.get(Alert.STATUS_CLOSED, 0),
        'unacknowledged': sum(1 for alert in alerts if not _has_claimants(alert)),
        'claimed': sum(1 for alert in alerts if _has_claimants(alert)),
        'suppressed': sum(1 for alert in alerts if alert.is_suppressed or alert.status == Alert.STATUS_MUTED),
    }


def matching_escalation_policy(alert):
    for policy in AlertEscalationPolicy.objects.filter(is_enabled=True):
        if match_matchers(alert, policy.matchers):
            return policy
    return None
