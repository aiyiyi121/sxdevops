from datetime import datetime, timedelta, timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from rbac.permissions import build_rbac_permission


RANGE_OPTIONS = {
    '24h': {'buckets': 12, 'step': timedelta(hours=2), 'multiplier': 1},
    '7d': {'buckets': 7, 'step': timedelta(days=1), 'multiplier': 7},
    '30d': {'buckets': 10, 'step': timedelta(days=3), 'multiplier': 30},
}


def _range_config(value):
    return RANGE_OPTIONS.get(value, RANGE_OPTIONS['24h'])


def _build_trend(now, range_key, platform):
    config = _range_config(range_key)
    platform_factor = {'all': 1, 'web': 0.78, 'mobile': 0.22}.get(platform, 1)
    trend = []
    for index in range(config['buckets']):
        point = now - config['step'] * (config['buckets'] - 1 - index)
        sessions = round((980 + index * 73) * platform_factor * max(1, config['multiplier'] / config['buckets']))
        trend.append({
            'label': point.strftime('%H:%M') if range_key == '24h' else point.strftime('%m-%d'),
            'sessions': sessions,
            'errors': max(1, round((4 + index % 4) * platform_factor)),
            'lcp': round(1.55 + (index % 5) * 0.09, 2),
        })
    return trend


def _vital_status(value, good, warning):
    if value <= good:
        return {'status': '良好', 'type': 'success', 'score': 88}
    if value <= warning:
        return {'status': '需改进', 'type': 'warning', 'score': 66}
    return {'status': '较差', 'type': 'danger', 'score': 38}


def _build_vitals(apps):
    count = max(len(apps), 1)
    lcp = round(sum(item['lcp'] for item in apps) / count, 2) if apps else 0
    inp = round(sum(item['inp'] for item in apps) / count) if apps else 0
    cls = round(sum(item['cls'] for item in apps) / count, 2) if apps else 0
    fcp = round(max(lcp * 0.55, 0.1), 2) if lcp else 0
    definitions = [
        ('lcp', 'LCP 最大内容绘制', lcp, 2.5, 4, 's', '目标低于 2.5s'),
        ('inp', 'INP 交互响应', inp, 200, 500, 'ms', '目标低于 200ms'),
        ('cls', 'CLS 累积布局偏移', cls, 0.1, 0.25, '', '目标低于 0.1'),
        ('fcp', 'FCP 首次内容绘制', fcp, 1.8, 3, 's', '目标低于 1.8s'),
    ]
    return [
        {'key': key, 'label': label, 'value': f'{value}{unit}', 'raw_value': value, 'hint': hint, **_vital_status(value, good, warning)}
        for key, label, value, good, warning, unit, hint in definitions
    ]


@api_view(['GET'])
@permission_classes([IsAuthenticated, build_rbac_permission('ops.rum.view')])
def rum_overview(request):
    platform = request.query_params.get('platform', 'all')
    range_key = request.query_params.get('range', '24h')
    if platform not in {'all', 'web', 'mobile'}:
        platform = 'all'
    if range_key not in RANGE_OPTIONS:
        range_key = '24h'

    apps = [
        {'name': '商户门户', 'service': 'merchant-portal', 'platform': 'web', 'sessions': 18642, 'users': 9240, 'error_rate': 0.42, 'lcp': 1.72, 'cls': 0.04, 'inp': 148},
        {'name': '运营工作台', 'service': 'ops-workbench', 'platform': 'web', 'sessions': 12480, 'users': 6380, 'error_rate': 0.68, 'lcp': 2.14, 'cls': 0.08, 'inp': 182},
        {'name': '移动巡检', 'service': 'mobile-inspection', 'platform': 'mobile', 'sessions': 8320, 'users': 4180, 'error_rate': 0.31, 'lcp': 1.48, 'cls': 0.03, 'inp': 126},
    ]
    if platform != 'all':
        apps = [item for item in apps if item['platform'] == platform]

    sessions = [
        {'id': 's_9fd2a1', 'app': '商户门户', 'service': 'merchant-portal', 'platform': 'web', 'path': '/orders/123', 'country': '中国·上海', 'device': 'Chrome / Windows', 'duration': '08:42', 'events': 38, 'network_requests': 24, 'status': '正常', 'time': '刚刚', 'trace_id': '9fd2a1c840e54a61a31ed54f7620ac88'},
        {'id': 's_2a0c44', 'app': '运营工作台', 'service': 'ops-workbench', 'platform': 'web', 'path': '/risk/rules', 'country': '中国·杭州', 'device': 'Safari / macOS', 'duration': '04:18', 'events': 21, 'network_requests': 17, 'status': '有错误', 'time': '3 分钟前', 'trace_id': '2a0c448fae5c4e2fb1f8cba9dfeee524'},
        {'id': 's_18be72', 'app': '移动巡检', 'service': 'mobile-inspection', 'platform': 'mobile', 'path': '/inspection/today', 'country': '中国·深圳', 'device': 'iOS 17', 'duration': '12:06', 'events': 64, 'network_requests': 42, 'status': '正常', 'time': '6 分钟前', 'trace_id': '18be72ec48054d0db6be5960f817851c'},
        {'id': 's_71c8e9', 'app': '商户门户', 'service': 'merchant-portal', 'platform': 'web', 'path': '/checkout', 'country': '中国·北京', 'device': 'Chrome / Android', 'duration': '01:12', 'events': 7, 'network_requests': 9, 'status': '受挫', 'time': '9 分钟前', 'trace_id': '71c8e969cf0143408c23782b89ea6083'},
    ]
    errors = [
        {'id': 'err-checkout-total', 'app': '商户门户', 'service': 'merchant-portal', 'platform': 'web', 'message': "Cannot read properties of undefined (reading 'total')", 'source': 'checkout.js:218', 'count': 42, 'users': 31, 'last_seen': '2 分钟前', 'level': 'error', 'session_id': 's_71c8e9', 'trace_id': '71c8e969cf0143408c23782b89ea6083'},
        {'id': 'err-order-timeout', 'app': '运营工作台', 'service': 'ops-workbench', 'platform': 'web', 'message': '请求 /api/orders 超时（504）', 'source': 'orders.vue:94', 'count': 27, 'users': 19, 'last_seen': '8 分钟前', 'level': 'warning', 'session_id': 's_2a0c44', 'trace_id': '2a0c448fae5c4e2fb1f8cba9dfeee524'},
        {'id': 'err-network-lost', 'app': '移动巡检', 'service': 'mobile-inspection', 'platform': 'mobile', 'message': 'Failed to fetch: network connection lost', 'source': 'runtime', 'count': 13, 'users': 11, 'last_seen': '14 分钟前', 'level': 'error', 'session_id': 's_18be72', 'trace_id': '18be72ec48054d0db6be5960f817851c'},
    ]
    if platform != 'all':
        sessions = [item for item in sessions if item['platform'] == platform]
        errors = [item for item in errors if item['platform'] == platform]

    multiplier = _range_config(range_key)['multiplier']
    totals = {
        'sessions': sum(item['sessions'] for item in apps) * multiplier,
        'users': round(sum(item['users'] for item in apps) * (1 + (multiplier - 1) * 0.48)),
        'errors': sum(item['count'] for item in errors) * multiplier,
        'error_rate': round(sum(item['error_rate'] for item in apps) / max(len(apps), 1), 2),
    }
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return Response({
        'query': {'platform': platform, 'range': range_key},
        'totals': totals,
        'deltas': {'sessions': 12.6, 'users': 8.2, 'errors': -4.1, 'error_rate': -0.08},
        'vitals': _build_vitals(apps),
        'apps': apps,
        'trend': _build_trend(now, range_key, platform),
        'sessions': sessions,
        'errors': errors,
        'generated_at': now.isoformat(),
    })
