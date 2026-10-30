from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'model-groups', views.CIModelGroupViewSet)
router.register(r'ci-types', views.CITypeViewSet)
router.register(r'ci-fields', views.CIFieldViewSet)
router.register(r'tags', views.CITagViewSet)
router.register(r'config-items', views.ConfigItemViewSet)
router.register(r'config-item-passwords', views.ConfigItemPasswordViewSet)
router.register(r'ci-relations', views.CIRelationViewSet)
router.register(r'relation-rules', views.CIRelationRuleViewSet)
router.register(r'source-mappings', views.CISourceMappingViewSet)
router.register(r'threshold-policies', views.CIThresholdPolicyViewSet)
router.register(r'resource-metrics', views.CIResourceMetricSnapshotViewSet)
router.register(r'change-logs', views.CIChangeLogViewSet)
router.register(r'sync-jobs', views.CISyncJobViewSet)
router.register(r'sync-records', views.CISyncRecordViewSet)
router.register(r'completion-issues', views.CICompletionIssueViewSet)
router.register(r'archive-candidates', views.CIArchiveCandidateViewSet)
router.register(r'resource-authorizations', views.CIResourceAuthorizationViewSet)
router.register(r'cost-records', views.CostRecordViewSet)
router.register(r'optimization-tasks', views.CostOptimizationTaskViewSet, basename='cost-optimization-task')
router.register(r'resource-requests', views.ResourceRequestViewSet)
router.register(r'resource-nodes', views.ResourceNodeViewSet)
router.register(r'ip-subnets', views.IPSubnetViewSet)
router.register(r'ip-addresses', views.IPAddressViewSet)

urlpatterns = [
    path(
        'resource-metrics/refresh-current-page/',
        views.CIResourceMetricSnapshotViewSet.as_view({'post': 'refresh_current_page'}),
        name='cmdb-resource-metrics-refresh-current-page',
    ),
    path('', include(router.urls)),
    path('dashboard/stats/', views.cmdb_dashboard, name='cmdb-dashboard'),
    path('governance/risks/', views.cmdb_governance_risks, name='cmdb-governance-risks'),
    path('ledger-tree/', views.ConfigItemViewSet.as_view({'get': 'ledger_tree'}), name='cmdb-ledger-tree-compat'),
    path('search/', views.cmdb_resource_search, name='cmdb-resource-search'),
    path('repository/summary/', views.cmdb_repository_summary, name='cmdb-repository-summary'),
    path('model-tree/', views.cmdb_model_tree, name='cmdb-model-tree'),
    path('island-analysis/', views.cmdb_island_analysis, name='cmdb-island-analysis'),
    path('views/summary/', views.cmdb_views_summary, name='cmdb-views-summary'),
    path('collection/summary/', views.cmdb_collection_summary, name='cmdb-collection-summary'),
    path('topology/data/', views.cmdb_topology, name='cmdb-topology'),
    path('cost/report/', views.cmdb_cost_report, name='cmdb-cost-report'),
    path('cost/items/', views.cmdb_cost_items, name='cmdb-cost-items'),
    path('cost/sync-aliyun/', views.cmdb_sync_aliyun_cost, name='cmdb-sync-aliyun-cost'),
    path('optimization/suggestions/', views.cmdb_optimization, name='cmdb-optimization'),
]
