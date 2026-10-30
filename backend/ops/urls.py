from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import loki_views
from . import log_views
from . import docker_views
from . import docker_logs
from . import k8s_views
from . import observability_views
from . import rum_views
from sxdevops.features import is_system_posture_enabled

router = DefaultRouter()
router.register(r'hosts', views.HostViewSet)
router.register(r'task-resource-groups', views.TaskResourceGroupViewSet, basename='task-resource-group')
router.register(r'task-resources', views.TaskResourceViewSet, basename='task-resource')
router.register(r'host-tasks', views.HostTaskViewSet, basename='host-task')
router.register(r'host-task-templates', views.HostTaskTemplateViewSet, basename='host-task-template')
router.register(r'host-task-schedules', views.HostTaskScheduleViewSet, basename='host-task-schedule')
router.register(r'host-task-schedule-executions', views.HostTaskScheduleExecutionViewSet, basename='host-task-schedule-execution')
router.register(r'deployment-approval-flows', views.DeploymentApprovalFlowViewSet, basename='deployment-approval-flow')
router.register(r'deployments', views.DeploymentViewSet)
router.register(r'transaction-tickets', views.TransactionTicketViewSet, basename='transaction-ticket')
router.register(r'alerts', views.AlertViewSet)
router.register(r'alert-integrations', views.AlertIntegrationViewSet, basename='alert-integration')
router.register(r'alert-recipients', views.AlertRecipientViewSet, basename='alert-recipient')
router.register(r'alert-recipient-groups', views.AlertRecipientGroupViewSet, basename='alert-recipient-group')
router.register(r'alert-notification-channels', views.AlertNotificationChannelViewSet, basename='alert-notification-channel')
router.register(r'alert-notification-rules', views.AlertNotificationRuleViewSet, basename='alert-notification-rule')
router.register(r'alert-aggregation-rules', views.AlertAggregationRuleViewSet, basename='alert-aggregation-rule')
router.register(r'alert-inhibition-rules', views.AlertInhibitionRuleViewSet, basename='alert-inhibition-rule')
router.register(r'alert-mute-rules', views.AlertMuteRuleViewSet, basename='alert-mute-rule')
router.register(r'alert-escalation-policies', views.AlertEscalationPolicyViewSet, basename='alert-escalation-policy')
router.register(r'alert-notification-logs', views.AlertNotificationLogViewSet, basename='alert-notification-log')
router.register(r'alert-actions', views.AlertActionViewSet, basename='alert-action')
router.register(r'logs', views.LogEntryViewSet)
router.register(r'log/datasources', log_views.LogDataSourceViewSet, basename='log-datasource')
router.register(r'observability/datasource-links', observability_views.ObservabilityDataSourceLinkViewSet, basename='observability-datasource-link')
if is_system_posture_enabled():
    router.register(r'observability/system-posture/environments', observability_views.SystemPostureEnvironmentViewSet, basename='system-posture-environment')
    router.register(r'observability/system-posture/systems', observability_views.SystemPostureSystemViewSet, basename='system-posture-system')
router.register(r'observability/tracing/datasources', observability_views.TracingDataSourceViewSet, basename='tracing-datasource')
router.register(r'observability/metric/datasources', observability_views.MetricDataSourceViewSet, basename='metric-datasource')
router.register(r'k8s/clusters', k8s_views.K8sClusterViewSet)
router.register(r'docker/hosts', docker_views.DockerHostViewSet)
urlpatterns = [
    path('dashboard/stats/', views.dashboard_stats, name='dashboard-stats'),
    path('alerts/webhooks/<str:provider>/', views.alert_webhook, name='alert-webhook'),
    path('alerts/webhooks/<str:provider>/<str:token>/', views.alert_webhook, name='alert-webhook-token'),
    path('alerts/card-actions/<uuid:token>/', views.alert_card_action, name='alert-card-action'),
    path('log/providers/', log_views.log_providers, name='log-providers'),
    path('log/providers/<str:provider>/catalog/', log_views.log_provider_catalog, name='log-provider-catalog'),
    path('log/query/', log_views.log_query, name='log-query'),
    # Loki 代理
    path('loki/labels/', loki_views.loki_labels, name='loki-labels'),
    path('loki/label/<str:label_name>/values/', loki_views.loki_label_values, name='loki-label-values'),
    path('loki/query_range/', loki_views.loki_query_range, name='loki-query-range'),
    path('loki/series/', loki_views.loki_series, name='loki-series'),
    # Docker 容器管理
    path('docker/containers/', docker_views.list_containers, name='docker-containers'),
    path('docker/images/', docker_views.list_images, name='docker-images'),
    path('docker/images/remove/', docker_views.remove_images, name='docker-images-remove'),
    path('docker/images/prune/', docker_views.prune_dangling_images, name='docker-images-prune'),
    path('docker/images/<str:image_id>/inspect/', docker_views.image_inspect, name='docker-image-inspect'),
    path('docker/containers/<str:container_id>/action/', docker_views.container_action, name='docker-container-action'),
    path('docker/containers/<str:container_id>/remove/', docker_views.container_remove, name='docker-container-remove'),
    path('docker/containers/<str:container_id>/logs/', docker_views.container_logs, name='docker-container-logs'),
    path('docker/containers/<str:container_id>/log_page/', docker_logs.container_log_page, name='docker-container-log-page'),
    path('docker/containers/<str:container_id>/inspect/', docker_views.container_inspect, name='docker-container-inspect'),
    path('observability/overview/', observability_views.observability_overview, name='observability-overview'),
    path('observability/rum/overview/', rum_views.rum_overview, name='observability-rum-overview'),
    path('observability/grafana/config/', observability_views.grafana_setting_view, name='observability-grafana-config'),
    path('observability/metrics/query/', observability_views.metrics_promql_query, name='observability-metrics-query'),
    path('observability/metrics/series-names/', observability_views.metrics_series_names, name='observability-metrics-series-names'),
    path('observability/grafana/promql/query/', observability_views.grafana_promql_query, name='observability-grafana-promql-query'),
    path('observability/grafana/panel/query/', observability_views.grafana_panel_query, name='observability-grafana-panel-query'),
    path('observability/tracing/providers/', observability_views.tracing_providers, name='observability-tracing-providers'),
    path('observability/tracing/catalog/', observability_views.observability_tracing_catalog, name='observability-tracing-catalog'),
    path('observability/tracing/search/', observability_views.observability_tracing_search, name='observability-tracing-search'),
    path('observability/tracing/traces/<str:trace_id>/', observability_views.observability_trace_detail, name='observability-trace-detail'),

    path('', include(router.urls)),
]

if is_system_posture_enabled():
    urlpatterns = [
        path('observability/system-posture/history/', observability_views.observability_system_posture_history, name='observability-system-posture-history'),
        path('observability/system-posture/', observability_views.observability_system_posture, name='observability-system-posture'),
        *urlpatterns,
    ]

