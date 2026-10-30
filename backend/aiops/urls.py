from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from . import views
from .remediation_views import action_verification


router = DefaultRouter()
router.register('sessions', views.AIOpsChatSessionViewSet, basename='aiops-session')
router.register('admin/providers', views.AIOpsModelProviderViewSet, basename='aiops-provider')
router.register('admin/mcp-servers', views.AIOpsMCPServerViewSet, basename='aiops-mcp-server')
router.register('admin/skills', views.AIOpsSkillViewSet, basename='aiops-skill')
router.register('knowledge-environments', views.AIOpsKnowledgeEnvironmentViewSet, basename='aiops-knowledge-environment')
router.register('admin/audit/sessions', views.AIOpsAuditSessionViewSet, basename='aiops-audit-session')
router.register('admin/audit/executions', views.AIOpsAuditExecutionViewSet, basename='aiops-audit-execution')
router.register('admin/audit/tool-invocations', views.AIOpsToolInvocationViewSet, basename='aiops-audit-tool')
router.register('admin/audit/model-invocations', views.AIOpsModelInvocationViewSet, basename='aiops-audit-model')
router.register('admin/audit/actions', views.AIOpsPendingActionViewSet, basename='aiops-audit-action')
router.register('a2a/tasks', views.AIOpsExternalTaskViewSet, basename='aiops-a2a-task')
router.register('runbooks', views.AIOpsRunbookViewSet, basename='aiops-runbook')
router.register('review-knowledge', views.AIOpsReviewKnowledgeViewSet, basename='aiops-review-knowledge')

urlpatterns = [
    path('bootstrap/', views.bootstrap, name='aiops-bootstrap'),
    path('capabilities/', views.capabilities, name='aiops-capabilities'),
    path('admin/capabilities/', views.admin_capabilities, name='aiops-admin-capabilities'),
    path('admin/capabilities/<str:code>/', views.capability_skills, name='aiops-capability-skills'),
    path('knowledge-graph/', views.knowledge_graph, name='aiops-knowledge-graph'),
    path('admin/actions/', views.action_registry, name='aiops-action-registry'),
    path('admin/actions/preflight/', views.action_preflight, name='aiops-action-preflight'),
    path('admin/config/', views.agent_config_view, name='aiops-agent-config'),
    path('mcp/manifest/', views.platform_mcp_manifest, name='aiops-platform-mcp-manifest'),
    path('mcp/tools/', views.platform_mcp_tools, name='aiops-platform-mcp-tools'),
    path('mcp/call/', views.platform_mcp_call, name='aiops-platform-mcp-call'),
    path('mcp/rpc/', views.platform_mcp_rpc, name='aiops-platform-mcp-rpc'),
    path('admin/providers/presets/', views.model_provider_presets, name='aiops-provider-presets-explicit'),
    path('admin/audit/overview/', views.audit_overview, name='aiops-audit-overview'),
    path('admin/audit/costs/', views.audit_cost_overview, name='aiops-audit-cost-overview'),
    path('admin/audit/skill-traces/', views.audit_skill_traces, name='aiops-audit-skill-traces'),
    path('admin/audit/skill-traces/bulk-delete/', views.audit_skill_traces_bulk_delete, name='aiops-audit-skill-traces-bulk-delete'),
    path('admin/audit/action-traces/', views.audit_action_traces, name='aiops-audit-action-traces'),
    path('admin/audit/action-traces/bulk-delete/', views.audit_action_traces_bulk_delete, name='aiops-audit-action-traces-bulk-delete'),
    re_path(r'^admin/audit/costs/?$', views.audit_cost_overview, name='aiops-audit-cost-overview-compat'),
    re_path(
        r'^sessions/(?P<pk>\d+)/delete_session/?$',
        views.AIOpsChatSessionViewSet.as_view({'post': 'delete_session'}),
        name='aiops-session-delete-session',
    ),
    path('actions/<int:pk>/confirm/', views.confirm_pending_action, name='aiops-confirm-action'),
    path('actions/<int:pk>/cancel/', views.cancel_pending_action, name='aiops-cancel-action'),
    path('actions/<int:pk>/verification/', action_verification, name='aiops-action-verification'),
    path('', include(router.urls)),
]
