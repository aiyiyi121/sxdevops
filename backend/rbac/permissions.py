from rest_framework.permissions import BasePermission, IsAuthenticated

from rest_framework.exceptions import PermissionDenied

from .services import user_has_permissions


class RBACPermission(BasePermission):
    message = '当前用户没有执行此操作的权限。'
    required_permissions = ()

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated or not request.user.is_active:
            return False

        codes = getattr(self, 'required_permissions', ())
        if not codes and hasattr(view, 'get_required_permissions'):
            codes = view.get_required_permissions()
        if isinstance(codes, str):
            codes = [codes]
        if not codes:
            return True
        if user_has_permissions(request.user, codes):
            return True
        self.message = f'缺少权限: {", ".join(codes)}'
        return False


class RBACPermissionMixin:
    permission_classes = [IsAuthenticated, RBACPermission]
    rbac_permissions = {}

    def get_required_permissions(self):
        request = getattr(self, 'request', None)
        allowed_methods = getattr(self, 'allowed_methods', None)
        if request is not None and allowed_methods is not None and request.method not in allowed_methods:
            # Unsupported methods have no handler; preserve DRF's 405 response.
            return []
        mapping = getattr(self, 'rbac_permissions', {}) or {}
        action = getattr(self, 'action', None)
        if action == 'metadata':
            action = 'list'
        if action not in mapping and '*' not in mapping:
            raise PermissionDenied('该操作尚未配置权限，已拒绝访问。')
        codes = mapping.get(action, mapping.get('*'))
        if isinstance(codes, str):
            return [codes]
        return list(codes or [])


def build_rbac_permission(*codes):
    class ViewRBACPermission(RBACPermission):
        required_permissions = codes

    return ViewRBACPermission
