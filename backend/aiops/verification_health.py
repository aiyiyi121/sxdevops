"""Bounded, reproducible health evidence; correlation never implies causal proof."""
import hashlib
import json
import math
import operator
from datetime import timedelta

from django.core.exceptions import PermissionDenied

from ops.models import Alert, MetricDataSource
from ops.observability_views import execute_promql_query
from rbac.services import user_has_permissions

COMPARATORS = {'lt': operator.lt, 'lte': operator.le, 'gt': operator.gt, 'gte': operator.ge, 'eq': operator.eq}


def source_fingerprint(source):
    value = json.dumps({'provider': source.provider, 'config': source.config}, sort_keys=True, default=str)
    return hashlib.sha256(value.encode()).hexdigest()


def require_health_access(baseline, environment, user):
    health = baseline.get('health_policy') or {}
    signals = health.get('signals') or []
    if signals and not user_has_permissions(user, ['ops.metric.query']):
        raise PermissionDenied('当前账号无权查询验证指标。')
    for signal in signals:
        source = MetricDataSource.objects.filter(pk=signal['datasource_id'], is_enabled=True).first()
        if (not source or source.pk not in environment.metric_datasource_ids
                or source_fingerprint(source) != signal['source_fingerprint']):
            raise PermissionDenied('验证指标数据源或环境关联已变化，请重新核对证据范围。')


def collect_signal(signal, start, end):
    """Require every evaluation step of every returned series; missing data is unknown."""
    step = signal['step_seconds']
    payload = execute_promql_query(
        signal['query'], range_query=True, start_time=start, end_time=end, step=step,
        metric_datasource_id=signal['datasource_id'], prefer_metric_datasource=True,
    )
    rows = payload.get('result') or []
    expected = math.floor((end - start).total_seconds() / step) + 1
    evidence = {'name': signal['name'], 'datasource_id': signal['datasource_id'],
                'start': start.isoformat(), 'end': end.isoformat(), 'step_seconds': step,
                'expected_samples_per_series': expected, 'series': [], 'status': 'inconclusive'}
    if payload.get('resultType') != 'matrix' or not rows or len(rows) > 20:
        return evidence
    complete, healthy = True, True
    for row in rows:
        samples = []
        indexes = set()
        for sample in row.get('values') or []:
            try:
                timestamp, value = float(sample[0]), float(sample[1])
            except (TypeError, ValueError, IndexError):
                complete = False
                continue
            offset = (timestamp - start.timestamp()) / step
            if (not math.isfinite(timestamp) or not math.isfinite(value)
                    or abs(offset - round(offset)) > 0.001
                    or not 0 <= round(offset) < expected or round(offset) in indexes):
                complete = False
                continue
            indexes.add(round(offset))
            samples.append([timestamp, value])
            healthy = healthy and COMPARATORS[signal['comparison']](value, signal['threshold'])
        if len(indexes) != expected:
            complete = False
        labels = json.dumps(row.get('metric') or {}, sort_keys=True)
        evidence['series'].append({'series_id': hashlib.sha256(labels.encode()).hexdigest(), 'samples': samples})
    evidence['status'] = ('healthy' if healthy else 'unhealthy') if complete else 'inconclusive'
    return evidence


def prepare_health_policy(policy, environment, user, observation_seconds, captured_at, snapshot, primary_alert):
    if not policy:
        return {}
    if not isinstance(policy, dict) or set(policy) - {'signals', 'related_alert_ids'}:
        raise ValueError('健康策略仅支持 signals 和 related_alert_ids。')
    signals = policy.get('signals') or []
    related_ids = policy.get('related_alert_ids') or []
    if (not isinstance(signals, list) or len(signals) > 4 or not isinstance(related_ids, list)
            or len(related_ids) > 10 or any(type(value) is not int for value in related_ids)):
        raise ValueError('最多配置 4 项指标和 10 个关联告警。')
    if signals and (observation_seconds < 30 or not user_has_permissions(user, ['ops.metric.query'])):
        raise PermissionDenied('指标验证需要指标查询权限及至少 30 秒观察窗口。')
    normalized = []
    for signal in signals:
        if not isinstance(signal, dict) or set(signal) - {'name', 'datasource_id', 'query', 'comparison', 'threshold', 'step_seconds'}:
            raise ValueError('指标策略字段无效。')
        name, query = str(signal.get('name') or '').strip(), str(signal.get('query') or '').strip()
        comparison = signal.get('comparison')
        step, source_id = signal.get('step_seconds', 15), signal.get('datasource_id')
        try:
            threshold = float(signal['threshold'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('指标阈值必须为有限数值。') from None
        if (not name or len(name) > 80 or not query or len(query) > 2000 or comparison not in COMPARATORS
                or not math.isfinite(threshold) or type(step) is not int or not 15 <= step <= 60
                or observation_seconds < step * 2 or type(source_id) is not int):
            raise ValueError('指标名称、PromQL、阈值或采样间隔无效；窗口至少覆盖 3 个采样点。')
        source = MetricDataSource.objects.filter(pk=source_id, is_enabled=True).first()
        if not source or source.pk not in environment.metric_datasource_ids:
            raise PermissionDenied('指标数据源必须属于所选知识环境。')
        item = {'name': name, 'query': query, 'comparison': comparison, 'threshold': threshold,
                'step_seconds': step, 'datasource_id': source.pk, 'source_fingerprint': source_fingerprint(source)}
        normalized.append(item)
    related_ids = sorted(set(related_ids) - {primary_alert.pk})
    alerts = list(Alert.objects.filter(pk__in=related_ids, environment__in=environment.alert_environments))
    if len(alerts) != len(related_ids):
        raise ValueError('关联告警必须属于所选知识环境。')
    baseline_signals = []
    for signal in normalized:
        # Fail configuration if the baseline source cannot be queried. No empty success.
        try:
            baseline_signals.append(collect_signal(signal, captured_at - timedelta(seconds=observation_seconds), captured_at))
        except Exception:
            raise ValueError('无法读取处置前指标基线，请检查数据源后重试。') from None
    return {'signals': normalized, 'related_alerts': [snapshot(alert) for alert in alerts],
            'baseline_signals': baseline_signals}


def observation_end(verification, snapshot):
    task = verification.task
    anchor = task.finished_at
    policy = verification.baseline.get('health_policy') or {}
    if policy:
        ids = [verification.baseline['alert']['id'], *[alert['id'] for alert in policy.get('related_alerts') or []]]
        for alert in Alert.objects.filter(pk__in=ids, status=Alert.STATUS_RESOLVED):
            if alert.ends_at and task.finished_at <= alert.ends_at <= snapshot:
                anchor = max(anchor, alert.ends_at)
    return anchor + timedelta(seconds=verification.observation_seconds)
