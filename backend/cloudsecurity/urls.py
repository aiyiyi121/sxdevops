from django.urls import path

from . import views


internal_platform_findings = views.InternalPlatformSecurityFindingViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
internal_platform_finding_detail = views.InternalPlatformSecurityFindingViewSet.as_view({
    'get': 'retrieve',
    'patch': 'partial_update',
})
internal_platform_finding_progress = views.InternalPlatformSecurityFindingViewSet.as_view({'post': 'progress'})
internal_platform_finding_close = views.InternalPlatformSecurityFindingViewSet.as_view({'post': 'close'})
internal_platform_finding_reopen = views.InternalPlatformSecurityFindingViewSet.as_view({'post': 'reopen'})


urlpatterns = [
    path('waf/accounts/', views.waf_accounts, name='cloudsecurity-waf-accounts'),
    path('waf/overview/', views.waf_overview, name='cloudsecurity-waf-overview'),
    path('waf/resources/', views.waf_resources, name='cloudsecurity-waf-resources'),
    path('waf/events/', views.waf_events, name='cloudsecurity-waf-events'),
    path('internal-platform/overview/', views.internal_platform_overview, name='internal-platform-overview'),
    path('internal-platform/posture/', views.internal_platform_posture, name='internal-platform-posture'),
    path('internal-platform/assets/', views.internal_platform_assets, name='internal-platform-assets'),
    path('internal-platform/threats/', views.internal_platform_threats, name='internal-platform-threats'),
    path('internal-platform/threats/<int:pk>/action/', views.internal_platform_threat_action, name='internal-platform-threat-action'),
    path('internal-platform/software/', views.internal_platform_software, name='internal-platform-software'),
    path('internal-platform/software/<int:pk>/status/', views.internal_platform_software_status, name='internal-platform-software-status'),
    path('internal-platform/findings/', internal_platform_findings, name='internal-platform-findings'),
    path('internal-platform/findings/<int:pk>/', internal_platform_finding_detail, name='internal-platform-finding-detail'),
    path('internal-platform/findings/<int:pk>/progress/', internal_platform_finding_progress, name='internal-platform-finding-progress'),
    path('internal-platform/findings/<int:pk>/close/', internal_platform_finding_close, name='internal-platform-finding-close'),
    path('internal-platform/findings/<int:pk>/reopen/', internal_platform_finding_reopen, name='internal-platform-finding-reopen'),
]
