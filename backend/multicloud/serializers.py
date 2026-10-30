from decimal import Decimal

from django.db.models import Q
from rest_framework import serializers

from .models import CloudAsset, CloudCredential, CloudEnvironment, CloudSyncTask
from .services import PROVIDER_CATALOG


PROVIDER_SOURCE_PREFIXES = {
    'aliyun': ['aliyun_'],
    'huawei': ['huaweicloud_'],
    'huaweicloud': ['huaweicloud_'],
    'vsphere': ['vsphere_'],
}
INTERNAL_PROVIDER_SUMMARY_CI_TYPE_CODES = {'VSPHERE_CAPACITY'}
INTERNAL_PROVIDER_SUMMARY_CI_TYPE_NAMES = {'vSphere资源统计'}
INTERNAL_PROVIDER_SUMMARY_SOURCE_PREFIXES = ('vsphere-summary:',)


class CloudCredentialSerializer(serializers.ModelSerializer):
    provider_label = serializers.CharField(source='get_provider_display', read_only=True)
    auth_mode_label = serializers.CharField(source='get_auth_mode_display', read_only=True)
    environment_count = serializers.SerializerMethodField()
    asset_count = serializers.SerializerMethodField()
    masked_secret = serializers.SerializerMethodField()

    class Meta:
        model = CloudCredential
        fields = [
            'id', 'provider', 'provider_label', 'name', 'account_id', 'account_name', 'auth_mode', 'auth_mode_label',
            'access_key_id', 'access_key_secret', 'masked_secret', 'project_id', 'role_arn', 'external_id',
            'default_region', 'owner', 'description', 'tags', 'is_enabled', 'demo_mode', 'last_test_status',
            'last_test_message', 'last_sync_at', 'environment_count', 'asset_count', 'created_by', 'updated_by',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['last_test_status', 'last_test_message', 'last_sync_at', 'environment_count', 'asset_count', 'created_by', 'updated_by', 'created_at', 'updated_at']
        extra_kwargs = {'access_key_secret': {'write_only': True, 'required': False, 'allow_blank': True}}

    def validate_provider(self, value):
        if value not in PROVIDER_CATALOG:
            raise serializers.ValidationError('暂不支持该云厂商。')
        return value

    def validate(self, attrs):
        if self.instance and attrs.get('access_key_secret', None) == '':
            attrs.pop('access_key_secret')
        provider = attrs.get('provider') or getattr(self.instance, 'provider', None)
        demo_mode = attrs.get('demo_mode', getattr(self.instance, 'demo_mode', False))
        auth_mode = str(attrs.get('auth_mode', getattr(self.instance, 'auth_mode', 'aksk')) or '').strip().lower()
        if demo_mode or auth_mode == 'demo':
            raise serializers.ValidationError({'demo_mode': 'Demo 模式已下线，请配置真实账号凭据。'})
        if provider == 'huawei' and not demo_mode and auth_mode != 'demo':
            access_key_id = attrs.get('access_key_id', getattr(self.instance, 'access_key_id', ''))
            access_key_secret = attrs.get('access_key_secret', getattr(self.instance, 'access_key_secret', ''))
            project_id = attrs.get('project_id', getattr(self.instance, 'project_id', ''))
            errors = {}
            if not str(access_key_id or '').strip():
                errors['access_key_id'] = '华为云账号必须填写 AccessKey ID。'
            if not str(access_key_secret or '').strip():
                errors['access_key_secret'] = '华为云账号必须填写 Secret Key。'
            if not str(project_id or '').strip():
                errors['project_id'] = '华为云账号必须填写 Project ID。'
            if errors:
                raise serializers.ValidationError(errors)
        return attrs

    def get_environment_count(self, obj):
        return obj.environments.count()

    def get_asset_count(self, obj):
        inventory_count = CloudAsset.objects.filter(environment__credential=obj).count()
        try:
            from cmdb.models import CISourceMapping, ConfigItem
        except Exception:
            return inventory_count

        account_candidates = {
            str(value or '').strip()
            for value in [obj.id, obj.account_name, obj.name, obj.account_id]
            if str(value or '').strip()
        }
        if not account_candidates:
            return inventory_count

        source_q = Q()
        for prefix in PROVIDER_SOURCE_PREFIXES.get(obj.provider, []):
            source_q |= Q(source_type__startswith=prefix)

        mapping_q = Q(source_account__in=account_candidates)
        if source_q:
            mapping_q &= source_q
        mapping_qs = CISourceMapping.objects.filter(mapping_q)
        for prefix in INTERNAL_PROVIDER_SUMMARY_SOURCE_PREFIXES:
            mapping_qs = mapping_qs.exclude(source_unique_id__startswith=prefix)
        mapping_qs = mapping_qs.exclude(
            Q(ci__ci_type__code__in=INTERNAL_PROVIDER_SUMMARY_CI_TYPE_CODES)
            | Q(ci__ci_type__name__in=INTERNAL_PROVIDER_SUMMARY_CI_TYPE_NAMES)
        )
        ci_ids = set(mapping_qs.values_list('ci_id', flat=True))

        attribute_q = Q()
        for value in account_candidates:
            attribute_q |= Q(attributes__source_account=value)
            attribute_q |= Q(attributes__cloud_account=value)
            attribute_q |= Q(attributes__account=value)
            attribute_q |= Q(attributes__account_id=value)
            attribute_q |= Q(attributes__account_name=value)
        if attribute_q:
            ci_q = attribute_q
            attribute_source_q = Q()
            for prefix in PROVIDER_SOURCE_PREFIXES.get(obj.provider, []):
                attribute_source_q |= Q(attributes__source_type__startswith=prefix)
            if attribute_source_q:
                ci_q &= attribute_source_q
            ci_qs = ConfigItem.objects.filter(ci_q).exclude(
                Q(ci_type__code__in=INTERNAL_PROVIDER_SUMMARY_CI_TYPE_CODES)
                | Q(ci_type__name__in=INTERNAL_PROVIDER_SUMMARY_CI_TYPE_NAMES)
            )
            for prefix in INTERNAL_PROVIDER_SUMMARY_SOURCE_PREFIXES:
                ci_qs = ci_qs.exclude(attributes__source_unique_id__startswith=prefix)
            ci_ids.update(ci_qs.values_list('id', flat=True))
        return len(ci_ids) if ci_ids else inventory_count

    def get_masked_secret(self, obj):
        if not obj.access_key_secret:
            return ''
        return f'{obj.access_key_secret[:2]}******{obj.access_key_secret[-2:]}'


class CloudEnvironmentSerializer(serializers.ModelSerializer):
    credential_name = serializers.CharField(source='credential.name', read_only=True)
    provider = serializers.CharField(source='credential.provider', read_only=True)
    provider_label = serializers.CharField(source='credential.get_provider_display', read_only=True)
    environment_type_label = serializers.CharField(source='get_environment_type_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    sync_status_label = serializers.CharField(source='get_sync_status_display', read_only=True)
    asset_count = serializers.SerializerMethodField()
    monthly_cost = serializers.SerializerMethodField()
    risk_count = serializers.SerializerMethodField()

    class Meta:
        model = CloudEnvironment
        fields = [
            'id', 'credential', 'credential_name', 'provider', 'provider_label', 'name', 'code', 'business_line',
            'environment_type', 'environment_type_label', 'region', 'zone', 'vpc_name', 'network_cidr', 'owner',
            'status', 'status_label', 'sync_status', 'sync_status_label', 'description', 'tags', 'summary',
            'asset_count', 'monthly_cost', 'risk_count', 'last_sync_at', 'last_cmdb_sync_at', 'created_by',
            'updated_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['credential_name', 'provider', 'provider_label', 'summary', 'asset_count', 'monthly_cost', 'risk_count', 'last_sync_at', 'last_cmdb_sync_at', 'created_by', 'updated_by', 'created_at', 'updated_at']

    def get_asset_count(self, obj):
        return obj.assets.count()

    def get_monthly_cost(self, obj):
        return float(sum((asset.monthly_cost or Decimal('0')) for asset in obj.assets.all()))

    def get_risk_count(self, obj):
        return obj.assets.filter(risk_level__in=['warning', 'critical']).count()


class CloudAssetSerializer(serializers.ModelSerializer):
    provider_label = serializers.CharField(source='get_provider_display', read_only=True)
    resource_type_label = serializers.CharField(source='get_resource_type_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    risk_level_label = serializers.CharField(source='get_risk_level_display', read_only=True)
    sync_state_label = serializers.CharField(source='get_sync_state_display', read_only=True)
    environment_name = serializers.CharField(source='environment.name', read_only=True)
    credential_name = serializers.CharField(source='environment.credential.name', read_only=True)

    class Meta:
        model = CloudAsset
        fields = [
            'id', 'environment', 'environment_name', 'credential_name', 'provider', 'provider_label', 'resource_type',
            'resource_type_label', 'resource_id', 'name', 'region', 'zone', 'status', 'status_label', 'charge_type',
            'private_ip', 'public_ip', 'vpc_name', 'spec', 'cpu', 'memory_gb', 'disk_gb', 'monthly_cost',
            'cost_currency', 'risk_level', 'risk_level_label', 'sync_state', 'sync_state_label', 'tags',
            'metadata', 'synced_at', 'created_at', 'updated_at',
        ]


class CloudSyncTaskSerializer(serializers.ModelSerializer):
    task_type_label = serializers.CharField(source='get_task_type_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    credential_name = serializers.CharField(source='credential.name', read_only=True)
    environment_name = serializers.CharField(source='environment.name', read_only=True)
    target_display = serializers.CharField(read_only=True)

    class Meta:
        model = CloudSyncTask
        fields = [
            'id', 'credential', 'credential_name', 'environment', 'environment_name', 'target_display', 'task_type',
            'task_type_label', 'status', 'status_label', 'operator', 'summary', 'result', 'started_at', 'finished_at',
            'created_at',
        ]
