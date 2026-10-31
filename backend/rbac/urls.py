from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from .site_settings import public_site_settings, site_icon, update_site_settings
from .repository import public_repository_stats


router = DefaultRouter()
router.register('users', views.UserViewSet, basename='rbac-user')
router.register('roles', views.RoleViewSet, basename='rbac-role')
router.register('groups', views.UserGroupViewSet, basename='rbac-group')
router.register('permissions', views.PermissionDefinitionViewSet, basename='rbac-permission')

urlpatterns = [
    path('auth/login/', views.login_view, name='rbac-login'),
    path('auth/logout/', views.logout_view, name='rbac-logout'),
    path('auth/me/', views.current_user_view, name='rbac-me'),
    path('auth/sync/', views.sync_permissions_view, name='rbac-sync'),
    path('auth/assignment-options/', views.assignment_options_view, name='rbac-assignment-options'),
    path('module-settings/', views.system_module_settings_view, name='rbac-module-settings'),
    path('site-settings/', public_site_settings, name='rbac-site-settings'),
    path('site-settings/icon/', site_icon, name='rbac-site-icon'),
    path('site-settings/repository/', public_repository_stats, name='rbac-repository-stats'),
    path('site-settings/manage/', update_site_settings, name='rbac-site-settings-manage'),
    path('', include(router.urls)),
]
