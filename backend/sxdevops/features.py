from django.conf import settings


SYSTEM_POSTURE_PERMISSION_CODES = {
    'ops.observability.system_posture.view',
    'ops.observability.system_posture.manage',
}

SYSTEM_POSTURE_TOOL_NAMES = {
    'query_system_posture',
}


def is_system_posture_enabled():
    return bool(getattr(settings, 'SYSTEM_POSTURE_ENABLED', True))


def permission_feature_enabled(code):
    if code in SYSTEM_POSTURE_PERMISSION_CODES:
        return is_system_posture_enabled()
    return True


def tool_feature_enabled(name):
    if name in SYSTEM_POSTURE_TOOL_NAMES:
        return is_system_posture_enabled()
    return True


def filter_feature_permissions(codes):
    return [code for code in (codes or []) if permission_feature_enabled(code)]


def filter_feature_tools(names):
    return [name for name in (names or []) if tool_feature_enabled(name)]
