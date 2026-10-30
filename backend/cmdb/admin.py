from django.contrib import admin

from .models import (
    CIArchiveCandidate,
    CIChangeLog,
    CICompletionIssue,
    CIField,
    CIModelGroup,
    CIResourceMetricSnapshot,
    CIResourceAuthorization,
    CIRelation,
    CIRelationRule,
    CISourceMapping,
    CISyncJob,
    CISyncRecord,
    CITag,
    CIThresholdPolicy,
    CIType,
    ConfigItem,
    CostRecord,
    ResourceNode,
    ResourceRequest,
)


@admin.register(CIModelGroup)
class CIModelGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'sort_order', 'is_builtin', 'is_active', 'updated_at')
    list_filter = ('is_builtin', 'is_active')
    search_fields = ('name', 'code', 'description')


@admin.register(CIType)
class CITypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'group', 'is_builtin', 'is_active', 'created_at', 'updated_at')
    list_filter = ('group', 'is_builtin', 'is_active')
    search_fields = ('name', 'code', 'description')


@admin.register(CIField)
class CIFieldAdmin(admin.ModelAdmin):
    list_display = ('ci_type', 'name', 'code', 'field_type', 'required', 'unique', 'is_builtin', 'is_active', 'sort_order')
    list_filter = ('ci_type', 'field_type', 'required', 'unique', 'is_builtin', 'is_active')
    search_fields = ('ci_type__name', 'name', 'code', 'field_group')


@admin.register(CITag)
class CITagAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'color', 'is_active', 'updated_at')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'category', 'description')


@admin.register(ConfigItem)
class ConfigItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'ci_type', 'business_line', 'environment', 'admin_user', 'status', 'updated_at')
    list_filter = ('ci_type', 'environment', 'status')
    search_fields = ('name', 'business_line', 'admin_user')


@admin.register(CISourceMapping)
class CISourceMappingAdmin(admin.ModelAdmin):
    list_display = ('ci', 'source_type', 'source_account', 'source_region', 'source_unique_id', 'sync_status', 'last_seen_at')
    list_filter = ('source_type', 'source_account', 'source_region', 'sync_status')
    search_fields = ('ci__name', 'source_unique_id', 'source_account')


@admin.register(CIRelation)
class CIRelationAdmin(admin.ModelAdmin):
    list_display = ('source', 'relation_type', 'target', 'description')
    list_filter = ('relation_type',)
    search_fields = ('source__name', 'target__name', 'description')


@admin.register(CIRelationRule)
class CIRelationRuleAdmin(admin.ModelAdmin):
    list_display = ('source_type', 'relation_type', 'target_type', 'required', 'multiple', 'is_active')
    list_filter = ('relation_type', 'required', 'multiple', 'is_active')
    search_fields = ('source_type__name', 'target_type__name', 'description')


@admin.register(CIThresholdPolicy)
class CIThresholdPolicyAdmin(admin.ModelAdmin):
    list_display = ('resource_type', 'metric', 'warning_threshold', 'critical_threshold', 'exceeded_threshold', 'enabled')
    list_filter = ('resource_type', 'metric', 'enabled')
    search_fields = ('resource_type__name', 'metric')


@admin.register(CIResourceMetricSnapshot)
class CIResourceMetricSnapshotAdmin(admin.ModelAdmin):
    list_display = ('ci', 'metric', 'value', 'unit', 'usage_percent', 'collected_at', 'source')
    list_filter = ('metric', 'source')
    search_fields = ('ci__name', 'metric', 'source')


@admin.register(CIChangeLog)
class CIChangeLogAdmin(admin.ModelAdmin):
    list_display = ('ci', 'action', 'operator', 'source', 'created_at')
    list_filter = ('action', 'operator', 'source')
    search_fields = ('ci__name', 'action', 'operator', 'source')


@admin.register(CISyncJob)
class CISyncJobAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_type', 'status', 'mode', 'dry_run', 'created_by', 'updated_at')
    list_filter = ('source_type', 'status', 'mode', 'dry_run', 'created_by')
    search_fields = ('name', 'source_type', 'created_by')


@admin.register(CISyncRecord)
class CISyncRecordAdmin(admin.ModelAdmin):
    list_display = ('job', 'ci', 'action', 'source_unique_id', 'status', 'created_at')
    list_filter = ('action', 'status')
    search_fields = ('job__name', 'ci__name', 'source_unique_id', 'error_message')


@admin.register(CICompletionIssue)
class CICompletionIssueAdmin(admin.ModelAdmin):
    list_display = ('ci', 'severity', 'status', 'assigned_to', 'resolved_at', 'updated_at')
    list_filter = ('severity', 'status', 'assigned_to')
    search_fields = ('ci__name', 'assigned_to', 'resolution_note')


@admin.register(CIArchiveCandidate)
class CIArchiveCandidateAdmin(admin.ModelAdmin):
    list_display = ('ci', 'source_type', 'status', 'confirmed_by', 'confirmed_at', 'updated_at')
    list_filter = ('source_type', 'status', 'confirmed_by')
    search_fields = ('ci__name', 'source_type', 'reason', 'confirmed_by')


@admin.register(CIResourceAuthorization)
class CIResourceAuthorizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'principal_type', 'principal', 'permission', 'business_line', 'environment', 'ci_type', 'is_active', 'updated_at')
    list_filter = ('principal_type', 'permission', 'business_line', 'environment', 'ci_type', 'is_active')
    search_fields = ('name', 'principal', 'business_line', 'environment', 'description')


@admin.register(CostRecord)
class CostRecordAdmin(admin.ModelAdmin):
    list_display = ('ci', 'month', 'amount', 'provider', 'computed_at')
    list_filter = ('month', 'provider')
    search_fields = ('ci__name', 'provider')


@admin.register(ResourceRequest)
class ResourceRequestAdmin(admin.ModelAdmin):
    list_display = ('title', 'resource_type', 'business_line', 'environment', 'applicant', 'status', 'created_at')
    list_filter = ('resource_type', 'business_line', 'environment', 'status')
    search_fields = ('title', 'applicant', 'approver', 'resource_type', 'business_line')


@admin.register(ResourceNode)
class ResourceNodeAdmin(admin.ModelAdmin):
    list_display = ('name', 'node_type', 'parent', 'sort_order')
    list_filter = ('node_type',)
    search_fields = ('name',)
