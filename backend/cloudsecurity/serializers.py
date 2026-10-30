from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import (
    InternalSecurityAsset,
    InternalSecurityThreat,
    InternalSecurityThreatActivity,
    InternalPlatformSecurityActivity,
    InternalPlatformSecurityControl,
    InternalPlatformSecurityFinding,
    SoftwareSecurityItem,
)


class InternalPlatformSecurityActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = InternalPlatformSecurityActivity
        fields = ('id', 'action', 'message', 'actor', 'created_at')


class InternalPlatformSecurityControlSerializer(serializers.ModelSerializer):
    platform_display = serializers.CharField(source='get_platform_display', read_only=True)
    open_findings = serializers.IntegerField(read_only=True)

    class Meta:
        model = InternalPlatformSecurityControl
        fields = (
            'id', 'platform', 'platform_display', 'scope', 'title', 'requirement',
            'evidence_requirement', 'sort_order', 'enabled', 'open_findings',
        )


class InternalPlatformSecurityFindingSerializer(serializers.ModelSerializer):
    platform_display = serializers.CharField(source='get_platform_display', read_only=True)
    finding_type_display = serializers.CharField(source='get_finding_type_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    control_title = serializers.CharField(source='control.title', read_only=True, default='')
    activities = InternalPlatformSecurityActivitySerializer(many=True, read_only=True)
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = InternalPlatformSecurityFinding
        fields = (
            'id', 'control', 'control_title', 'finding_type', 'finding_type_display',
            'platform', 'platform_display', 'scope', 'title', 'description', 'severity',
            'severity_display', 'status', 'status_display', 'owner', 'due_date',
            'ticket_ref', 'evidence', 'created_by', 'closed_by', 'closed_at',
            'created_at', 'updated_at', 'is_overdue', 'activities',
        )
        read_only_fields = ('created_by', 'closed_by', 'closed_at')

    def get_is_overdue(self, obj):
        from django.utils import timezone

        return bool(
            obj.due_date
            and obj.due_date < timezone.localdate()
            and obj.status not in {obj.STATUS_CLOSED, obj.STATUS_IGNORED}
        )


class InternalSecurityAssetSerializer(serializers.ModelSerializer):
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    agent_status_display = serializers.CharField(source='get_agent_status_display', read_only=True)
    risk_level_display = serializers.CharField(source='get_risk_level_display', read_only=True)
    open_threat_count = serializers.IntegerField(read_only=True)
    threat_count = serializers.IntegerField(read_only=True)
    resolved_threat_count = serializers.IntegerField(read_only=True)
    protection_status = serializers.SerializerMethodField()
    protection_status_display = serializers.SerializerMethodField()

    class Meta:
        model = InternalSecurityAsset
        fields = (
            'id', 'source', 'source_display', 'source_id', 'name', 'ip_address',
            'os_name', 'environment', 'business_line', 'agent_status',
            'agent_status_display', 'risk_level', 'risk_level_display',
            'last_seen_at', 'last_scan_at', 'tags', 'open_threat_count',
            'threat_count', 'resolved_threat_count', 'protection_status',
            'protection_status_display',
        )

    def get_protection_status(self, obj):
        if obj.agent_status == obj.AGENT_PENDING:
            return 'pending'
        if obj.agent_status == obj.AGENT_OFFLINE:
            return 'offline'
        if not obj.last_seen_at or obj.last_seen_at < timezone.now() - timedelta(minutes=30):
            return 'stale'
        return 'healthy'

    def get_protection_status_display(self, obj):
        return {
            'pending': '待接入',
            'offline': 'Agent 离线',
            'stale': '心跳异常',
            'healthy': '防护正常',
        }[self.get_protection_status(obj)]


class InternalSecurityThreatActivitySerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    from_status_display = serializers.CharField(source='get_from_status_display', read_only=True)
    to_status_display = serializers.CharField(source='get_to_status_display', read_only=True)

    class Meta:
        model = InternalSecurityThreatActivity
        fields = (
            'id', 'action', 'action_display', 'from_status', 'from_status_display',
            'to_status', 'to_status_display', 'message', 'actor', 'created_at',
        )


class InternalSecurityThreatSerializer(serializers.ModelSerializer):
    asset_name = serializers.CharField(source='asset.name', read_only=True, default='')
    asset_ip = serializers.IPAddressField(source='asset.ip_address', read_only=True, default=None)
    asset_source = serializers.CharField(source='asset.source', read_only=True, default='')
    asset_source_display = serializers.CharField(source='asset.get_source_display', read_only=True, default='')
    threat_type_display = serializers.CharField(source='get_threat_type_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    activities = InternalSecurityThreatActivitySerializer(many=True, read_only=True)

    class Meta:
        model = InternalSecurityThreat
        fields = (
            'id', 'asset', 'asset_name', 'asset_ip', 'asset_source',
            'asset_source_display', 'source', 'threat_type', 'threat_type_display',
            'title', 'severity', 'severity_display', 'status', 'status_display',
            'description', 'process_path', 'command_line', 'file_hash', 'remote_ip',
            'suggestion', 'owner', 'ticket_ref', 'detected_at', 'resolved_at',
            'created_at', 'updated_at', 'activities',
        )
        read_only_fields = ('resolved_at',)


class SoftwareSecurityItemSerializer(serializers.ModelSerializer):
    deployment_type_display = serializers.CharField(source='get_deployment_type_display', read_only=True)
    upgrade_necessity_display = serializers.CharField(source='get_upgrade_necessity_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = SoftwareSecurityItem
        fields = (
            'id', 'row_number', 'deployment_type', 'deployment_type_display',
            'software_name', 'latest_version', 'current_version', 'other_versions',
            'risk_summary', 'upgrade_advice', 'upgrade_necessity',
            'upgrade_necessity_display', 'priority', 'bug_advice',
            'owner_feedback', 'plan_time', 'status', 'status_display',
            'last_reviewed_at', 'updated_at',
        )
