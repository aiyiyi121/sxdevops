"""Public product previews expose forms without granting execution privileges."""
from django.conf import settings
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.exceptions import PermissionDenied


PREVIEW_MESSAGE = '访客体验模式：可浏览页面和表单，暂不支持提交或执行操作。'
SENSITIVE_READ_PERMISSIONS = {'ops.k8s.secret.view', 'cmdb.password.reveal'}
# These POST handlers only retrieve observations or resolve navigation links.
PREVIEW_POST_VIEWS = {
    'rbac-logout', 'log-query', 'log-provider-catalog',
    'observability-metrics-query', 'observability-grafana-promql-query',
    'observability-grafana-panel-query', 'observability-tracing-search',
    *{
        f'observability-datasource-link-resolve-{source}-to-{target}'
        for source, target in (
            ('trace', 'logs'), ('log', 'trace'), ('trace', 'grafana'),
            ('log', 'grafana'), ('grafana', 'logs'), ('grafana', 'trace'),
        )
    },
}
# Legacy read endpoints share their permission code with execution actions.
PREVIEW_LEGACY_READ_VIEWS = {
    'host-task-list', 'host-task-detail', 'host-task-stats',
    'host-task-host-options', 'host-task-resource-options',
    'host-task-template-list', 'host-task-template-detail',
    'rbac-user-options', 'rbac-user-k8s-access',
}


def is_preview_user(user):
    return bool(
        getattr(user, 'is_authenticated', False)
        and getattr(user, 'is_active', False)
        and user.username in getattr(settings, 'PUBLIC_PREVIEW_USERNAMES', ())
    )


def is_preview_read_permission(code):
    return code.endswith(('.view', '.query')) and code not in SENSITIVE_READ_PERMISSIONS


def enforce_preview_request(request, user):
    if not is_preview_user(user):
        return
    match = getattr(request, 'resolver_match', None)
    if request.method in {'GET', 'HEAD', 'OPTIONS'}:
        if match and match.url_name == 'observability-system-posture-history' and any(
            str(request.query_params.get(key, '')).lower() in {'1', 'true', 'yes'}
            for key in ('refresh', 'backfill')
        ):
            raise PermissionDenied(PREVIEW_MESSAGE, code='preview_read_only')
        return
    if request.method == 'POST' and match and match.url_name in PREVIEW_POST_VIEWS:
        return
    raise PermissionDenied(PREVIEW_MESSAGE, code='preview_read_only')


class PreviewTokenAuthentication(TokenAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result:
            enforce_preview_request(request, result[0])
        return result


class PreviewSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result:
            enforce_preview_request(request, result[0])
        return result
