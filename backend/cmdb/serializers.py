import ipaddress
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from rest_framework import serializers
from .metrics import latest_metric_snapshots
from .models import (
    CIArchiveCandidate,
    CIChangeLog,
    CICompletionIssue,
    CIField,
    CIModelGroup,
    CIResourceMetricSnapshot,
    CIResourceAuthorization,
    IPAddress,
    IPSubnet,
    CIRelation,
    CIRelationRule,
    CISourceMapping,
    CISyncJob,
    CISyncRecord,
    CITag,
    CIThresholdPolicy,
    CIType,
    ConfigItem,
    ConfigItemPassword,
    CostOptimizationProgress,
    CostOptimizationTask,
    CostRecord,
    ResourceNode,
    ResourceRequest,
)
from django.db.models import Count, Q, Sum
from django.core.exceptions import ImproperlyConfigured
from .passwords import encrypt_config_item_password
from .provisioning import ALIYUN_RESOURCE_TYPES, ALIYUN_RESOURCE_TYPE_MAP, provider_label, validate_provisioning_specs
from .sync import normalize_ci_attributes, normalize_ci_type_name, resolve_config_item_type_meta


RESOURCE_WATERLINE_ATTRIBUTE_CODES = {
    'cpu_used_mhz', 'cpu_usage', 'cpu_usage_percent', 'cpu_utilization', 'cpu_utilization_percent', 'cpu_used_percent',
    'memory_total_gb', 'memory_used_gb', 'memory_free_gb', 'memory_available_gb', 'memory_usage', 'memory_usage_percent',
    'memory_utilization', 'memory_utilization_percent', 'memory_used_percent',
    'disk_used_gb', 'disk_usage', 'disk_usage_percent', 'disk_utilization', 'disk_utilization_percent', 'disk_used_percent',
    'storage_used_gb', 'storage_usage', 'storage_usage_percent', 'storage_utilization', 'storage_utilization_percent', 'storage_used_percent',
    'root_disk_total_gb', 'root_disk_free_gb', 'root_disk_available_gb', 'root_mountpoint',
    'metric_collection_source', 'metric_collection_status', 'metric_collection_error', 'metrics_collection_status',
    'metric_datasource', 'metric_collected_at', 'prometheus_target',
}


def _normalize_field_options(options):
    normalized = []
    for item in options or []:
        if isinstance(item, dict):
            value = item.get('value', item.get('id', item.get('name')))
            label = item.get('label', item.get('name', value))
        else:
            value = item
            label = item
        if value not in (None, ''):
            normalized.append({'value': value, 'label': label})
    return normalized


def _field_option_values(field):
    return {str(item['value']) for item in _normalize_field_options(field.options)}


def _normalize_resource_environment(value):
    return str(value or '').strip()


SENSITIVE_KEY_EXACT = {
    'api_key',
    'apikey',
    'access_key_secret',
    'accesskeysecret',
    'secret_key',
    'client_secret',
    'private_key',
    'security_token',
}
SENSITIVE_KEY_PARTS = {'password', 'passwd', 'pwd', 'secret', 'token', 'credential'}
CMDB_SOURCE_METADATA_FIELD_CODES = {
    'source_type',
    'source_account',
    'source_region',
    'source_unique_id',
}


def _normalize_sensitive_key(key):
    return re.sub(r'[^a-z0-9]+', '_', str(key or '').strip().lower()).strip('_')


def _is_non_empty_secret_value(value):
    return value not in (None, '', [], {})


def _sensitive_plaintext_paths(value, prefix=''):
    paths = []
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = _normalize_sensitive_key(raw_key)
            path = f'{prefix}.{raw_key}' if prefix else str(raw_key)
            parts = {part for part in key.split('_') if part}
            if _is_non_empty_secret_value(item) and (key in SENSITIVE_KEY_EXACT or parts & SENSITIVE_KEY_PARTS):
                paths.append(path)
            if isinstance(item, (dict, list)):
                paths.extend(_sensitive_plaintext_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, (dict, list)):
                paths.extend(_sensitive_plaintext_paths(item, f'{prefix}[{index}]' if prefix else f'[{index}]'))
    return paths


def validate_no_sensitive_plaintext(value, *, context='数据'):
    paths = _sensitive_plaintext_paths(value)
    if paths:
        preview = '、'.join(paths[:5])
        suffix = ' 等' if len(paths) > 5 else ''
        raise serializers.ValidationError(f'{context}不能保存密钥、密码、Token 等明文字段：{preview}{suffix}。请改为记录负责人、到期日或凭据引用。')


def _decimal_for_compare(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _validate_min_max(field, value, *, compare_value=None):
    validation = field.validation or {}
    if compare_value is None:
        compare_value = value
    for rule_name, message_label in (('min', '不能小于'), ('max', '不能大于')):
        expected = validation.get(rule_name)
        if expected in (None, ''):
            continue
        expected_value = _decimal_for_compare(expected)
        actual_value = _decimal_for_compare(compare_value)
        if expected_value is None or actual_value is None:
            continue
        if rule_name == 'min' and actual_value < expected_value:
            raise serializers.ValidationError(f'{field.name} {message_label} {expected}')
        if rule_name == 'max' and actual_value > expected_value:
            raise serializers.ValidationError(f'{field.name} {message_label} {expected}')


def _parse_date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return parse_date(str(value))
    except (TypeError, ValueError):
        return None


def _parse_datetime_value(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return None
    try:
        return parse_datetime(str(value))
    except (TypeError, ValueError):
        return None


def _validate_date_range(field, parsed_value):
    validation = field.validation or {}
    for rule_name, message_label in (('min', '不能早于'), ('max', '不能晚于')):
        expected = validation.get(rule_name)
        if expected in (None, ''):
            continue
        expected_value = _parse_date_value(expected)
        if expected_value is None:
            continue
        if rule_name == 'min' and parsed_value < expected_value:
            raise serializers.ValidationError(f'{field.name} {message_label} {expected}')
        if rule_name == 'max' and parsed_value > expected_value:
            raise serializers.ValidationError(f'{field.name} {message_label} {expected}')


def _validate_datetime_range(field, parsed_value):
    validation = field.validation or {}
    for rule_name, message_label in (('min', '不能早于'), ('max', '不能晚于')):
        expected = validation.get(rule_name)
        if expected in (None, ''):
            continue
        expected_value = _parse_datetime_value(expected)
        if expected_value is None:
            continue
        if rule_name == 'min' and parsed_value < expected_value:
            raise serializers.ValidationError(f'{field.name} {message_label} {expected}')
        if rule_name == 'max' and parsed_value > expected_value:
            raise serializers.ValidationError(f'{field.name} {message_label} {expected}')


def _field_values_equal(field, current, incoming):
    try:
        current = _validate_field_value(field, current)
    except serializers.ValidationError:
        pass
    return current == incoming or str(current) == str(incoming)


def _validate_field_value(field, value):
    if value in (None, ''):
        if field.required:
            raise serializers.ValidationError(f'{field.name} 为必填字段')
        return value

    field_type = field.field_type
    if field_type == 'integer':
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError(f'{field.name} 必须是整数')
        _validate_min_max(field, normalized)
        return normalized
    if field_type == 'decimal':
        try:
            normalized = float(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError(f'{field.name} 必须是数字')
        _validate_min_max(field, normalized)
        return normalized
    if field_type == 'boolean':
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {'true', 'false', '1', '0', 'yes', 'no'}:
            return value.lower() in {'true', '1', 'yes'}
        raise serializers.ValidationError(f'{field.name} 必须是布尔值')
    if field_type == 'date':
        parsed = _parse_date_value(value)
        if parsed is None:
            raise serializers.ValidationError(f'{field.name} 必须是合法日期')
        _validate_date_range(field, parsed)
        return parsed.isoformat()
    if field_type == 'datetime':
        parsed = _parse_datetime_value(value)
        if parsed is None:
            raise serializers.ValidationError(f'{field.name} 必须是合法日期时间')
        _validate_datetime_range(field, parsed)
        return parsed.isoformat()
    if field_type == 'enum':
        allowed = _field_option_values(field)
        if allowed and str(value) not in allowed:
            raise serializers.ValidationError(f'{field.name} 不在允许选项中')
        return value
    if field_type == 'multi_enum':
        if not isinstance(value, list):
            raise serializers.ValidationError(f'{field.name} 必须是数组')
        allowed = _field_option_values(field)
        if allowed:
            invalid = [item for item in value if str(item) not in allowed]
            if invalid:
                raise serializers.ValidationError(f'{field.name} 包含非法选项: {", ".join(map(str, invalid))}')
        return value
    if field_type == 'ip':
        try:
            ipaddress.ip_address(str(value))
        except ValueError:
            raise serializers.ValidationError(f'{field.name} 必须是合法 IP 地址')
        return str(value)
    if field_type == 'url':
        parsed = urlparse(str(value))
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise serializers.ValidationError(f'{field.name} 必须是合法 URL')
        return str(value)
    if field_type == 'json':
        if not isinstance(value, (dict, list)):
            raise serializers.ValidationError(f'{field.name} 必须是 JSON 对象或数组')
        return value

    min_length = (field.validation or {}).get('min_length')
    if min_length and len(str(value)) < int(min_length):
        raise serializers.ValidationError(f'{field.name} 长度不能小于 {min_length}')
    max_length = (field.validation or {}).get('max_length')
    if max_length and len(str(value)) > int(max_length):
        raise serializers.ValidationError(f'{field.name} 长度不能超过 {max_length}')
    pattern = (field.validation or {}).get('regex')
    if pattern and not re.fullmatch(pattern, str(value)):
        raise serializers.ValidationError(f'{field.name} 格式不符合要求')
    return value


def validate_config_item_attributes_by_metadata(ci_type, attributes, *, instance=None, merge_existing=False):
    if not ci_type:
        return normalize_ci_attributes(attributes or {})

    incoming_attributes = normalize_ci_attributes(attributes or {})
    validate_no_sensitive_plaintext(incoming_attributes, context='配置项属性')
    if instance is not None and merge_existing:
        merged_attributes = dict(instance.attributes or {})
        merged_attributes.update(incoming_attributes)
    else:
        merged_attributes = dict(incoming_attributes)

    errors = {}
    normalized = dict(merged_attributes)
    fields = list(ci_type.fields.filter(is_active=True))
    for field in fields:
        value = normalized.get(field.code)
        if value in (None, '') and field.default not in (None, ''):
            value = field.default
            normalized[field.code] = value
        if field.is_sensitive and value not in (None, '', [], {}):
            errors[field.code] = [f'{field.name} 是敏感字段，当前版本不保存明文，请记录负责人、到期日或凭据引用。']
            continue
        try:
            normalized[field.code] = _validate_field_value(field, value)
        except serializers.ValidationError as exc:
            errors[field.code] = exc.detail

        normalized_value = normalized.get(field.code)
        if field.unique and normalized_value not in (None, ''):
            duplicate_qs = ConfigItem.objects.filter(ci_type=ci_type)
            if instance is not None:
                duplicate_qs = duplicate_qs.exclude(pk=instance.pk)
            if any(
                _field_values_equal(field, (item.attributes or {}).get(field.code), normalized_value)
                for item in duplicate_qs.only('id', 'attributes')
            ):
                errors[field.code] = [f'{field.name} 必须唯一']

    if errors:
        raise serializers.ValidationError({'attributes': errors})
    return normalize_ci_attributes(normalized)


class CIModelGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = CIModelGroup
        fields = '__all__'


class IPSubnetSerializer(serializers.ModelSerializer):
    address_total = serializers.SerializerMethodField()
    available_count = serializers.SerializerMethodField()
    in_use_count = serializers.SerializerMethodField()
    offline_count = serializers.SerializerMethodField()
    reserved_count = serializers.SerializerMethodField()

    class Meta:
        model = IPSubnet
        fields = '__all__'
        read_only_fields = ['created_by', 'last_scanned_at']

    def validate(self, attrs):
        cidr = attrs.get('cidr', getattr(self.instance, 'cidr', ''))
        try:
            network = ipaddress.ip_network(str(cidr).strip(), strict=False)
        except ValueError as exc:
            raise serializers.ValidationError({'cidr': '请输入有效的 IPv4 CIDR，例如 10.20.1.0/24。'}) from exc
        if network.version != 4:
            raise serializers.ValidationError({'cidr': '当前仅支持 IPv4 子网。'})
        if network.num_addresses > 4096:
            raise serializers.ValidationError({'cidr': '单个子网最多支持 4096 个地址，请拆分为更小的网段。'})
        attrs['cidr'] = network.with_prefixlen
        gateway = str(attrs.get('gateway', getattr(self.instance, 'gateway', '')) or '').strip()
        if gateway:
            try:
                if ipaddress.ip_address(gateway) not in network:
                    raise serializers.ValidationError({'gateway': '网关必须位于该子网内。'})
            except ValueError as exc:
                raise serializers.ValidationError({'gateway': '请输入有效的 IPv4 地址。'}) from exc
        excluded = attrs.get('excluded_addresses', getattr(self.instance, 'excluded_addresses', [])) or []
        if not isinstance(excluded, list):
            raise serializers.ValidationError({'excluded_addresses': '保留地址必须是 IP 地址列表。'})
        invalid = []
        for address in excluded:
            try:
                if ipaddress.ip_address(str(address)) not in network:
                    invalid.append(str(address))
            except ValueError:
                invalid.append(str(address))
        if invalid:
            raise serializers.ValidationError({'excluded_addresses': f'以下地址无效或不属于子网：{", ".join(invalid[:5])}'})
        return attrs

    def _status_counts(self, obj):
        if hasattr(obj, '_ip_status_counts'):
            return obj._ip_status_counts
        counts = {'available': 0, 'in_use': 0, 'offline': 0, 'reserved': 0}
        for row in obj.addresses.values('status').annotate(total=Count('id')):
            counts[row['status']] = row['total']
        return counts

    def get_address_total(self, obj):
        return max(ipaddress.ip_network(obj.cidr).num_addresses - 2, 0)

    def get_available_count(self, obj):
        return self._status_counts(obj)['available']

    def get_in_use_count(self, obj):
        return self._status_counts(obj)['in_use']

    def get_offline_count(self, obj):
        return self._status_counts(obj)['offline']

    def get_reserved_count(self, obj):
        return self._status_counts(obj)['reserved']


class IPAddressSerializer(serializers.ModelSerializer):
    ci_name = serializers.CharField(source='ci.name', read_only=True)

    class Meta:
        model = IPAddress
        fields = '__all__'
        read_only_fields = ['linked_ci_names', 'last_scanned_at', 'created_by']

    def validate(self, attrs):
        subnet = attrs.get('subnet', getattr(self.instance, 'subnet', None))
        address = str(attrs.get('address', getattr(self.instance, 'address', '')) or '').strip()
        if not subnet:
            return attrs
        try:
            network = ipaddress.ip_network(subnet.cidr)
            ip_value = ipaddress.ip_address(address)
        except ValueError as exc:
            raise serializers.ValidationError({'address': '请输入有效的 IPv4 地址。'}) from exc
        if ip_value.version != 4 or ip_value not in network or ip_value in {network.network_address, network.broadcast_address}:
            raise serializers.ValidationError({'address': 'IP 必须是子网内的可用 IPv4 地址。'})
        attrs['address'] = str(ip_value)
        return attrs


class CITypeSerializer(serializers.ModelSerializer):
    ci_count = serializers.IntegerField(read_only=True)
    group_name = serializers.CharField(source='group.name', read_only=True)
    group_code = serializers.CharField(source='group.code', read_only=True)

    class Meta:
        model = CIType
        fields = '__all__'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['name'] = normalize_ci_type_name(data.get('name'))
        return data

    def validate_name(self, value):
        return normalize_ci_type_name(value)

    def validate(self, attrs):
        if self.instance is not None and self.instance.is_builtin:
            protected_fields = ['code', 'name']
            changed = [
                field
                for field in protected_fields
                if field in attrs and attrs[field] != getattr(self.instance, field)
            ]
            if changed:
                raise serializers.ValidationError({
                    field: '内置模型的名称和编码不允许修改，可通过停用控制使用范围。'
                    for field in changed
                })
        return attrs


class CIFieldSerializer(serializers.ModelSerializer):
    ci_type_name = serializers.CharField(source='ci_type.name', read_only=True)

    class Meta:
        model = CIField
        fields = '__all__'

    def validate_code(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('字段编码不能为空')
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*', value):
            raise serializers.ValidationError('字段编码必须以字母开头，仅包含字母、数字和下划线')
        if value in CMDB_SOURCE_METADATA_FIELD_CODES:
            raise serializers.ValidationError('来源元数据由来源映射统一维护，不能作为资产分类字段配置。')
        return value

    def validate(self, attrs):
        if self.instance is not None and self.instance.is_builtin:
            protected_fields = [
                'ci_type',
                'code',
                'field_type',
                'required',
                'unique',
                'default',
                'options',
                'validation',
                'is_sensitive',
            ]
            changed = [
                field
                for field in protected_fields
                if field in attrs and attrs[field] != getattr(self.instance, field)
            ]
            if changed:
                raise serializers.ValidationError({
                    field: '内置字段的关键约束不允许修改，可调整展示、排序或停用。'
                    for field in changed
                })
        return attrs


class CITagSerializer(serializers.ModelSerializer):
    ci_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = CITag
        fields = '__all__'

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('标签名称不能为空')
        return value


class ConfigItemSerializer(serializers.ModelSerializer):
    ci_type_name = serializers.SerializerMethodField()
    ci_type_code = serializers.SerializerMethodField()
    ci_type_group_code = serializers.SerializerMethodField()
    ci_type_icon = serializers.SerializerMethodField()
    ci_type_color = serializers.SerializerMethodField()
    relation_count = serializers.SerializerMethodField()
    field_definitions = serializers.SerializerMethodField()
    latest_metric_snapshots = serializers.SerializerMethodField()
    source_mappings = serializers.SerializerMethodField()
    source_label = serializers.SerializerMethodField()
    source_type = serializers.SerializerMethodField()
    source_sync_status = serializers.SerializerMethodField()
    source_unique_id = serializers.SerializerMethodField()
    last_seen_at = serializers.SerializerMethodField()
    tag_items = CITagSerializer(source='tags', many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    environment_display = serializers.CharField(source='get_environment_display', read_only=True)
    business_node_name = serializers.SerializerMethodField()
    environment_node_name = serializers.SerializerMethodField()

    class Meta:
        model = ConfigItem
        fields = '__all__'

    def get_ci_type_name(self, obj):
        return resolve_config_item_type_meta(obj)['name']

    def get_ci_type_code(self, obj):
        return obj.ci_type.code if obj.ci_type_id else ''

    def get_ci_type_group_code(self, obj):
        if not obj.ci_type_id or not obj.ci_type.group_id:
            return ''
        return obj.ci_type.group.code

    def get_ci_type_icon(self, obj):
        return resolve_config_item_type_meta(obj)['icon']

    def get_ci_type_color(self, obj):
        return resolve_config_item_type_meta(obj)['color']

    def get_business_node_name(self, obj):
        return obj.business_node.name if obj.business_node_id else ''

    def get_environment_node_name(self, obj):
        return obj.environment_node.name if obj.environment_node_id else ''

    def validate_resource_node(self, value):
        if value is None:
            return value
        if value.node_type not in {'cloud_account', 'cloud_region', 'cloud_cluster', 'cloud_host'}:
            raise serializers.ValidationError('请选择云资源树中的节点')
        return value

    def _validate_resource_scope(self, attrs):
        instance = getattr(self, 'instance', None)
        if 'business_node' not in attrs and 'business_line' in attrs:
            business_name = (attrs.get('business_line') or '').strip()
            candidates = list(ResourceNode.objects.filter(node_type='biz', parent__isnull=True, name=business_name)[:2])
            attrs['business_node'] = candidates[0] if len(candidates) == 1 else None

        business_node = attrs.get('business_node', getattr(instance, 'business_node', None))
        if 'environment_node' not in attrs and 'environment' in attrs and business_node:
            expected_environment = _normalize_resource_environment(attrs.get('environment'))
            candidates = [
                node
                for node in ResourceNode.objects.filter(node_type='env', parent=business_node)
                if _normalize_resource_environment(node.name) == expected_environment
            ]
            if len(candidates) == 1:
                attrs['environment_node'] = candidates[0]
        environment_node = attrs.get('environment_node', getattr(instance, 'environment_node', None))

        if 'business_node' in attrs and not business_node and 'environment_node' not in attrs:
            environment_node = None
            attrs['environment_node'] = None

        if business_node and business_node.node_type != 'biz':
            raise serializers.ValidationError({'business_node': '请选择业务线节点'})
        if environment_node:
            if environment_node.node_type != 'env':
                raise serializers.ValidationError({'environment_node': '请选择环境节点'})
            if not business_node:
                raise serializers.ValidationError({'environment_node': '请先选择业务线节点'})
            if environment_node.parent_id != business_node.id:
                raise serializers.ValidationError({'environment_node': '所选环境不属于当前业务线'})

        if 'business_node' in attrs:
            attrs['business_line'] = business_node.name if business_node else attrs.get('business_line', '')
        if 'environment_node' in attrs:
            attrs['environment'] = _normalize_resource_environment(environment_node.name) if environment_node else attrs.get('environment', '')

        if 'resource_node' in attrs:
            attributes = dict(attrs.get('attributes', getattr(instance, 'attributes', {}) or {}))
            if attrs['resource_node']:
                attributes['resource_node_id'] = attrs['resource_node'].id
            else:
                attributes.pop('resource_node_id', None)
            attrs['attributes'] = attributes
        if 'attributes' in attrs:
            attrs['attributes'] = {
                key: value
                for key, value in (attrs['attributes'] or {}).items()
                if key not in RESOURCE_WATERLINE_ATTRIBUTE_CODES
            }
        return attrs

    def _sync_scope_fields(self, validated_data):
        if 'business_node' in validated_data:
            business_node = validated_data['business_node']
            validated_data['business_line'] = business_node.name if business_node else validated_data.get('business_line', '')
        if 'environment_node' in validated_data:
            environment_node = validated_data['environment_node']
            validated_data['environment'] = _normalize_resource_environment(environment_node.name) if environment_node else validated_data.get('environment', '')
        return validated_data

    def create(self, validated_data):
        return super().create(self._sync_scope_fields(validated_data))

    def update(self, instance, validated_data):
        return super().update(instance, self._sync_scope_fields(validated_data))

    def get_relation_count(self, obj):
        cached = getattr(obj, 'relation_count_cached', None)
        if cached is not None:
            return cached
        return obj.outgoing_relations.count() + obj.incoming_relations.count()

    def get_field_definitions(self, obj):
        if not self.context.get('include_field_definitions', True):
            return []
        ci_type = getattr(obj, 'ci_type', None)
        cached = getattr(ci_type, 'active_field_definitions', None)
        if cached is not None:
            return CIFieldSerializer(cached, many=True).data
        return CIFieldSerializer(obj.ci_type.fields.filter(is_active=True), many=True).data

    def get_latest_metric_snapshots(self, obj):
        wanted_metrics = {'cpu_usage', 'memory_usage', 'disk_usage', 'storage_usage'}
        snapshots = getattr(obj, 'latest_waterline_metrics', None)
        if snapshots is None:
            snapshots = latest_metric_snapshots([obj.pk], wanted_metrics)
        rows = []
        seen = set()
        for snapshot in snapshots:
            if snapshot.metric not in wanted_metrics or snapshot.metric in seen:
                continue
            seen.add(snapshot.metric)
            rows.append({
                'id': snapshot.id,
                'ci': snapshot.ci_id,
                'metric': snapshot.metric,
                'value': str(snapshot.value),
                'unit': snapshot.unit,
                'usage_percent': str(snapshot.usage_percent) if snapshot.usage_percent is not None else None,
                'collected_at': snapshot.collected_at.isoformat() if snapshot.collected_at else None,
                'source': snapshot.source,
            })
        return rows

    def _source_rows(self, obj):
        cached = getattr(obj, '_cmdb_serialized_source_rows', None)
        if cached is not None:
            return cached
        mappings = getattr(obj, '_prefetched_objects_cache', {}).get('source_mappings')
        if mappings is None:
            mappings = obj.source_mappings.all()
        rows = [
            {
                'id': mapping.id,
                'source_type': mapping.source_type,
                'source_account': mapping.source_account,
                'source_region': mapping.source_region,
                'source_unique_id': mapping.source_unique_id,
                'sync_status': mapping.sync_status,
                'last_seen_at': mapping.last_seen_at,
                'updated_at': mapping.updated_at,
            }
            for mapping in mappings
        ]
        setattr(obj, '_cmdb_serialized_source_rows', rows)
        return rows

    def _primary_source_row(self, obj):
        rows = self._source_rows(obj)
        return rows[0] if rows else {}

    def get_source_mappings(self, obj):
        return self._source_rows(obj)

    def get_source_label(self, obj):
        source = self._primary_source_row(obj)
        attributes = obj.attributes or {}
        return source.get('source_type') or attributes.get('source_type') or attributes.get('source') or 'manual'

    def get_source_type(self, obj):
        return self.get_source_label(obj)

    def get_source_sync_status(self, obj):
        source = self._primary_source_row(obj)
        return source.get('sync_status') or ''

    def get_source_unique_id(self, obj):
        source = self._primary_source_row(obj)
        attributes = obj.attributes or {}
        return (
            source.get('source_unique_id')
            or attributes.get('source_unique_id')
            or attributes.get('external_id')
            or attributes.get('instance_id')
            or ''
        )

    def get_last_seen_at(self, obj):
        source = self._primary_source_row(obj)
        return source.get('last_seen_at')

    def _validate_attributes_by_metadata(self, attrs):
        ci_type = attrs.get('ci_type') or getattr(self.instance, 'ci_type', None)
        if not ci_type:
            return attrs
        attrs['attributes'] = validate_config_item_attributes_by_metadata(
            ci_type,
            attrs.get('attributes', {}),
            instance=self.instance,
            merge_existing=self.instance is not None,
        )
        return attrs

    def validate(self, attrs):
        attrs = self._validate_resource_scope(attrs)
        return self._validate_attributes_by_metadata(attrs)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['attributes'] = normalize_ci_attributes(data.get('attributes'))
        return data


class ConfigItemPasswordSerializer(serializers.ModelSerializer):
    config_item_name = serializers.CharField(source='config_item.name', read_only=True)
    config_item_type = serializers.CharField(source='config_item.ci_type.name', read_only=True)
    has_password = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=False, trim_whitespace=False)

    class Meta:
        model = ConfigItemPassword
        fields = [
            'id',
            'config_item',
            'config_item_name',
            'config_item_type',
            'username',
            'password',
            'has_password',
            'remark',
            'created_by',
            'updated_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'config_item_name',
            'config_item_type',
            'has_password',
            'created_by',
            'updated_by',
            'created_at',
            'updated_at',
        ]

    def get_has_password(self, obj):
        return bool(obj.password_ciphertext)

    def validate_config_item(self, value):
        if self.instance and value.pk != self.instance.config_item_id:
            raise serializers.ValidationError('不能变更登录凭据关联的资产。')
        if not self.instance and ConfigItemPassword.objects.filter(config_item=value).exists():
            raise serializers.ValidationError('该资产已经配置登录凭据。')
        return value

    def validate(self, attrs):
        if self.instance is None and 'password' not in attrs:
            raise serializers.ValidationError({'password': '请填写登录密码。'})
        return attrs

    def _encrypted_password(self, password):
        try:
            return encrypt_config_item_password(password)
        except (ImproperlyConfigured, ValueError) as exc:
            raise serializers.ValidationError({'password': str(exc)}) from exc

    def create(self, validated_data):
        password = validated_data.pop('password')
        validated_data['password_ciphertext'] = self._encrypted_password(password)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password is not None:
            validated_data['password_ciphertext'] = self._encrypted_password(password)
        return super().update(instance, validated_data)


class ConfigItemPasswordRevealSerializer(serializers.Serializer):
    current_password = serializers.CharField(
        write_only=True,
        allow_blank=False,
        trim_whitespace=False,
        error_messages={
            'required': '请输入当前平台登录密码。',
            'blank': '请输入当前平台登录密码。',
        },
    )


class CISourceMappingSerializer(serializers.ModelSerializer):
    ci_name = serializers.CharField(source='ci.name', read_only=True)
    ci_type_name = serializers.CharField(source='ci.ci_type.name', read_only=True)

    class Meta:
        model = CISourceMapping
        fields = '__all__'
        validators = []

    def validate(self, attrs):
        instance = self.instance
        source_type = (attrs.get('source_type', getattr(instance, 'source_type', '')) or '').strip()
        source_account = (attrs.get('source_account', getattr(instance, 'source_account', '')) or '').strip()
        source_region = (attrs.get('source_region', getattr(instance, 'source_region', '')) or '').strip()
        source_unique_id = (attrs.get('source_unique_id', getattr(instance, 'source_unique_id', '')) or '').strip()
        if not source_type:
            raise serializers.ValidationError({'source_type': '请填写来源类型。'})
        if not source_unique_id:
            raise serializers.ValidationError({'source_unique_id': '请填写来源唯一标识。'})
        duplicate_qs = CISourceMapping.objects.filter(
            source_type=source_type,
            source_account=source_account,
            source_region=source_region,
            source_unique_id=source_unique_id,
        )
        if instance:
            duplicate_qs = duplicate_qs.exclude(pk=instance.pk)
        if duplicate_qs.exists():
            raise serializers.ValidationError({'source_unique_id': '同一来源范围下的唯一标识已绑定其他资源。'})
        attrs['source_type'] = source_type
        attrs['source_account'] = source_account
        attrs['source_region'] = source_region
        attrs['source_unique_id'] = source_unique_id
        return attrs

class CIRelationSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source='source.name', read_only=True)
    target_name = serializers.CharField(source='target.name', read_only=True)
    source_type = serializers.CharField(source='source.ci_type.name', read_only=True)
    target_type = serializers.CharField(source='target.ci_type.name', read_only=True)
    evidence_source_display = serializers.CharField(source='get_evidence_source_display', read_only=True)

    class Meta:
        model = CIRelation
        fields = '__all__'

    def _matching_relation_rule(self, source, target, relation_type):
        if not source or not target or not relation_type:
            return None
        source_rules = CIRelationRule.objects.filter(source_type=source.ci_type, is_active=True)
        if not source_rules.exists():
            return None
        rule = source_rules.filter(
            target_type=target.ci_type,
            relation_type=relation_type,
        ).first()
        if not rule:
            raise serializers.ValidationError('关系不符合模型关系规则，请先在模型设计中维护允许的关系。')
        return rule

    def validate(self, attrs):
        source = attrs.get('source') or getattr(self.instance, 'source', None)
        target = attrs.get('target') or getattr(self.instance, 'target', None)
        relation_type = attrs.get('relation_type') or getattr(self.instance, 'relation_type', None)
        confidence = attrs.get('confidence', getattr(self.instance, 'confidence', 100))
        evidence = attrs.get('evidence', getattr(self.instance, 'evidence', {}))

        if confidence is None:
            attrs['confidence'] = 100
        else:
            try:
                confidence_value = int(confidence)
            except (TypeError, ValueError):
                raise serializers.ValidationError({'confidence': '置信度必须是 0 到 100 之间的整数。'})
            if not 0 <= confidence_value <= 100:
                raise serializers.ValidationError({'confidence': '置信度必须在 0 到 100 之间。'})
            attrs['confidence'] = confidence_value

        if evidence in (None, ''):
            attrs['evidence'] = {}
        elif not isinstance(evidence, dict):
            raise serializers.ValidationError({'evidence': '关系证据必须是 JSON 对象。'})

        if source and target and source.id == target.id:
            raise serializers.ValidationError('Source and target must be different CIs.')

        if source and target and relation_type:
            duplicate_qs = CIRelation.objects.filter(
                source=source,
                target=target,
                relation_type=relation_type,
            )
            if self.instance is not None:
                duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)
            if duplicate_qs.exists():
                raise serializers.ValidationError('This CI relation already exists.')

            rule = self._matching_relation_rule(source, target, relation_type)
            if rule and not rule.multiple:
                same_type_qs = CIRelation.objects.filter(
                    source=source,
                    target__ci_type=target.ci_type,
                    relation_type=relation_type,
                )
                if self.instance is not None:
                    same_type_qs = same_type_qs.exclude(pk=self.instance.pk)
                if same_type_qs.exists():
                    raise serializers.ValidationError('该模型关系规则不允许同一资源关联多个同类目标。')

        return attrs


class CIRelationRuleSerializer(serializers.ModelSerializer):
    source_type_name = serializers.CharField(source='source_type.name', read_only=True)
    target_type_name = serializers.CharField(source='target_type.name', read_only=True)

    class Meta:
        model = CIRelationRule
        fields = '__all__'


class CIThresholdPolicySerializer(serializers.ModelSerializer):
    resource_type_name = serializers.CharField(source='resource_type.name', read_only=True)

    class Meta:
        model = CIThresholdPolicy
        fields = '__all__'

    def validate(self, attrs):
        instance = self.instance
        normal = attrs.get(
            'normal_threshold',
            getattr(instance, 'normal_threshold', CIThresholdPolicy._meta.get_field('normal_threshold').get_default()),
        )
        warning = attrs.get(
            'warning_threshold',
            getattr(instance, 'warning_threshold', CIThresholdPolicy._meta.get_field('warning_threshold').get_default()),
        )
        critical = attrs.get(
            'critical_threshold',
            getattr(instance, 'critical_threshold', CIThresholdPolicy._meta.get_field('critical_threshold').get_default()),
        )
        exceeded = attrs.get(
            'exceeded_threshold',
            getattr(instance, 'exceeded_threshold', CIThresholdPolicy._meta.get_field('exceeded_threshold').get_default()),
        )
        if not (normal <= warning <= critical <= exceeded):
            raise serializers.ValidationError({
                'thresholds': '阈值必须满足：正常 <= 预警 <= 紧张 <= 超限。'
            })
        return attrs


class CIResourceMetricSnapshotSerializer(serializers.ModelSerializer):
    ci_name = serializers.CharField(source='ci.name', read_only=True)
    ci_type_name = serializers.CharField(source='ci.ci_type.name', read_only=True)
    source_type = serializers.SerializerMethodField()
    source_account = serializers.SerializerMethodField()
    source_region = serializers.SerializerMethodField()
    source_unique_id = serializers.SerializerMethodField()

    class Meta:
        model = CIResourceMetricSnapshot
        fields = '__all__'

    def _ci_attributes(self, obj):
        if not obj.ci_id:
            return {}
        return obj.ci.attributes or {}

    def get_source_type(self, obj):
        attrs = self._ci_attributes(obj)
        return attrs.get('source_type') or attrs.get('source') or ''

    def get_source_account(self, obj):
        attrs = self._ci_attributes(obj)
        return attrs.get('source_account') or attrs.get('cloud_account') or attrs.get('account') or attrs.get('account_name') or ''

    def get_source_region(self, obj):
        attrs = self._ci_attributes(obj)
        return attrs.get('source_region') or attrs.get('region') or attrs.get('endpoint') or ''

    def get_source_unique_id(self, obj):
        attrs = self._ci_attributes(obj)
        return attrs.get('source_unique_id') or attrs.get('instance_id') or ''


class CIChangeLogSerializer(serializers.ModelSerializer):
    ci_name = serializers.CharField(source='ci.name', read_only=True)
    diff_fields = serializers.SerializerMethodField()
    diff_preview = serializers.SerializerMethodField()
    diff_count = serializers.SerializerMethodField()

    class Meta:
        model = CIChangeLog
        fields = '__all__'

    def _field_label(self, key):
        mapping = {
            'name': '名称',
            'ci_type': '模型',
            'ci_type_name': '模型',
            'business_line': '业务线',
            'environment': '环境',
            'admin_user': '负责人',
            'status': '状态',
            'tags': '标签',
            'attributes': '扩展属性',
            'id': '关系ID',
            'source_id': '源资源ID',
            'source_name': '源资源',
            'source_type': '源模型ID',
            'source_type_name': '源模型',
            'target_id': '目标资源ID',
            'target_name': '目标资源',
            'target_type': '目标模型ID',
            'target_type_name': '目标模型',
            'relation_type': '关系类型',
            'description': '描述',
        }
        if key.startswith('attributes.'):
            return key.replace('attributes.', '扩展属性.')
        return mapping.get(key, key)

    def _stringify_value(self, value):
        if value in (None, ''):
            return '-'
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            text = str(value)
        return text if len(text) <= 60 else f'{text[:57]}...'

    def _flatten_diff(self, diff):
        rows = []
        for key, payload in (diff or {}).items():
            if key in RESOURCE_WATERLINE_ATTRIBUTE_CODES:
                continue
            if key.startswith('attributes.') and key.split('.', 1)[1] in RESOURCE_WATERLINE_ATTRIBUTE_CODES:
                continue
            before = payload.get('before') if isinstance(payload, dict) else None
            after = payload.get('after') if isinstance(payload, dict) else None
            if key == 'attributes' and isinstance(before, dict) and isinstance(after, dict):
                attr_keys = sorted(set(before.keys()) | set(after.keys()))
                for attr_key in attr_keys:
                    if attr_key in RESOURCE_WATERLINE_ATTRIBUTE_CODES:
                        continue
                    old = before.get(attr_key)
                    new = after.get(attr_key)
                    if old != new:
                        rows.append({
                            'field': f'attributes.{attr_key}',
                            'label': self._field_label(f'attributes.{attr_key}'),
                            'before': old,
                            'after': new,
                            'before_text': self._stringify_value(old),
                            'after_text': self._stringify_value(new),
                        })
                continue
            rows.append({
                'field': key,
                'label': self._field_label(key),
                'before': before,
                'after': after,
                'before_text': self._stringify_value(before),
                'after_text': self._stringify_value(after),
            })
        return rows

    def get_diff_fields(self, obj):
        if obj.diff:
            return self._flatten_diff(obj.diff)
        if obj.action == 'create':
            return [{'field': 'resource', 'label': '资源', 'before': None, 'after': obj.after, 'before_text': '-', 'after_text': '创建配置项'}]
        if obj.action == 'delete':
            return [{'field': 'resource', 'label': '资源', 'before': obj.before, 'after': None, 'before_text': '删除配置项', 'after_text': '-'}]
        return []

    def get_diff_preview(self, obj):
        rows = self.get_diff_fields(obj)
        if rows:
            preview = [f"{row['label']}：{row['before_text']} -> {row['after_text']}" for row in rows[:3]]
            suffix = f" 等 {len(rows)} 项" if len(rows) > 3 else ''
            return '；'.join(preview) + suffix
        mapping = {
            'completion_resolve': '补全资源信息',
            'completion_assign': '转派待补全',
            'completion_ignore': '忽略待补全',
            'archive_mark': '标记待下线',
            'archive_confirm': '确认资源下线',
            'archive_archive': '归档下线候选',
            'archive_restore': '恢复资源',
            'archive_ignore': '忽略下线候选',
            'relation_create': '创建资源关系',
            'relation_delete': '删除资源关系',
            'request_submit': '提交资源申请',
            'request_approve': '批准资源申请',
            'request_reject': '驳回资源申请',
            'request_complete': '完成资源交付',
        }
        return mapping.get(obj.action, '-')

    def get_diff_count(self, obj):
        return len(self.get_diff_fields(obj))


def _age_days(started_at):
    if not started_at:
        return 0
    return max((timezone.now() - started_at).days, 0)


def _due_at(started_at, due_days):
    if not started_at:
        return None
    return started_at + timedelta(days=due_days)


def _is_overdue(started_at, due_days):
    due_at = _due_at(started_at, due_days)
    return bool(due_at and timezone.now() > due_at)


class CISyncRecordSerializer(serializers.ModelSerializer):
    ci_name = serializers.CharField(source='ci.name', read_only=True)
    job_name = serializers.CharField(source='job.name', read_only=True)
    job_source_type = serializers.CharField(source='job.source_type', read_only=True)
    job_source_accounts = serializers.SerializerMethodField()
    job_source_context = serializers.SerializerMethodField()
    age_days = serializers.SerializerMethodField()
    due_days = serializers.SerializerMethodField()
    due_at = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    relation_issue = serializers.SerializerMethodField()
    relation_issue_count = serializers.SerializerMethodField()
    relation_issue_summary = serializers.SerializerMethodField()

    class Meta:
        model = CISyncRecord
        fields = '__all__'

    def _relation_summary(self, obj):
        after = obj.after if isinstance(obj.after, dict) else {}
        summary = after.get('_sync_relations') if isinstance(after, dict) else {}
        return summary if isinstance(summary, dict) else {}

    def _job_source_context(self, obj):
        cached = getattr(obj, '_serializer_job_source_context', None)
        if cached is not None:
            return cached
        config = obj.job.config if isinstance(obj.job.config, dict) else {}
        accounts = []
        for key in ('source_account', 'account_name', 'account_id', 'cloud_account_name'):
            value = str(config.get(key) or '').strip()
            if value:
                accounts.append(value)

        credential = None
        credential_id = config.get('cloud_account_id') or config.get('multicloud_account_id')
        if credential_id:
            try:
                from multicloud.models import CloudCredential
                credential = CloudCredential.objects.filter(id=credential_id).first()
            except Exception:
                credential = None
            if credential:
                accounts.extend(
                    str(value or '').strip()
                    for value in (credential.account_name, credential.name, credential.account_id, credential.default_region)
                    if str(value or '').strip()
                )
        context = {
            'source_account': str(
                config.get('source_account')
                or config.get('account_name')
                or (credential.account_name if credential else '')
                or (credential.name if credential else '')
                or (credential.account_id if credential else '')
                or ''
            ).strip(),
            'source_region': str(
                config.get('source_region')
                or config.get('region_id')
                or config.get('region')
                or (credential.default_region if credential else '')
                or ''
            ).strip(),
            'provider': str(config.get('provider') or config.get('connector') or '').strip(),
            'accounts': list(dict.fromkeys(accounts)),
        }
        obj._serializer_job_source_context = context
        return context

    def get_job_source_accounts(self, obj):
        return self._job_source_context(obj)['accounts']

    def get_job_source_context(self, obj):
        context = self._job_source_context(obj)
        return {
            'source_account': context['source_account'],
            'source_region': context['source_region'],
            'provider': context['provider'],
        }

    def get_relation_issue_count(self, obj):
        return int(self._relation_summary(obj).get('failed') or 0)

    def get_relation_issue(self, obj):
        return self.get_relation_issue_count(obj) > 0

    def get_relation_issue_summary(self, obj):
        summary = self._relation_summary(obj)
        if not summary:
            return {}
        errors = summary.get('errors') if isinstance(summary.get('errors'), list) else []
        peer_not_found = sum(1 for item in errors if isinstance(item, dict) and item.get('reason') == 'peer_not_found')
        validation_failed = sum(1 for item in errors if isinstance(item, dict) and item.get('reason') == 'validation_failed')
        return {
            'total': int(summary.get('total') or 0),
            'created': int(summary.get('created') or 0),
            'skipped': int(summary.get('skipped') or 0),
            'failed': int(summary.get('failed') or 0),
            'peer_not_found': peer_not_found,
            'validation_failed': validation_failed,
            'errors': errors[:5],
        }

    def get_age_days(self, obj):
        return _age_days(obj.created_at)

    def get_due_days(self, obj):
        if self.get_relation_issue(obj):
            return 1
        return 1 if obj.status == 'failed' else 3

    def get_due_at(self, obj):
        return _due_at(obj.created_at, self.get_due_days(obj))

    def get_is_overdue(self, obj):
        return _is_overdue(obj.created_at, self.get_due_days(obj))


def validate_sync_field_mapping_config(config):
    mapping = (config or {}).get('field_mapping')
    if mapping in (None, '', [], {}):
        mapping = (config or {}).get('field_mappings')
    if mapping in (None, '', [], {}):
        return

    errors = []
    targets = set()

    def validate_entry(target, source, label):
        target = str(target or '').strip() if target is not None else ''
        source = str(source or '').strip() if source is not None else ''
        if not target:
            errors.append(f'{label} 缺少目标字段')
        if not source:
            errors.append(f'{label} 缺少来源字段')
        if target:
            if target in targets:
                errors.append(f'{label} 目标字段 {target} 重复')
            targets.add(target)

    if isinstance(mapping, dict):
        for target, source in mapping.items():
            validate_entry(target, source, f'字段映射 {target or "-"}')
    elif isinstance(mapping, list):
        for index, item in enumerate(mapping, start=1):
            label = f'字段映射第 {index} 行'
            if not isinstance(item, dict):
                errors.append(f'{label} 必须是对象')
                continue
            target = item.get('target') or item.get('target_field') or item.get('cmdb_field') or item.get('field')
            source = item.get('source') or item.get('source_field') or item.get('path')
            validate_entry(target, source, label)
            if 'required' in item and not isinstance(item.get('required'), bool):
                errors.append(f'{label} required 必须是布尔值')
    else:
        errors.append('字段映射必须是对象或数组')

    if errors:
        raise serializers.ValidationError({'field_mapping': errors})


def _contains_demo_sync_mode(value):
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key or '').strip().lower()
            if normalized_key == 'demo_mode' and item is True:
                return True
            if normalized_key == 'auth_mode' and str(item or '').strip().lower() == 'demo':
                return True
            if _contains_demo_sync_mode(item):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_demo_sync_mode(item) for item in value)
    return False


class CISyncJobSerializer(serializers.ModelSerializer):
    record_count = serializers.IntegerField(read_only=True)
    failed_samples = serializers.SerializerMethodField()
    last_error_message = serializers.SerializerMethodField()

    class Meta:
        model = CISyncJob
        fields = '__all__'
        read_only_fields = ['created_by', 'started_at', 'finished_at', 'summary', 'error_message', 'created_at', 'updated_at']

    def validate_config(self, value):
        validate_no_sensitive_plaintext(value or {}, context='同步任务配置')
        if _contains_demo_sync_mode(value or {}):
            raise serializers.ValidationError('Demo 模式已下线，请使用真实账号或凭据引用。')
        validate_sync_field_mapping_config(value or {})
        return value or {}

    def _failed_samples(self, obj):
        cached = getattr(obj, '_serializer_failed_samples', None)
        if cached is not None:
            return cached
        records = obj.records.filter(status='failed').exclude(error_message='').order_by('-created_at', '-id')[:3]
        samples = [
            {
                'id': record.id,
                'source_unique_id': record.source_unique_id,
                'error_message': record.error_message,
                'created_at': record.created_at,
            }
            for record in records
        ]
        obj._serializer_failed_samples = samples
        return samples

    def get_failed_samples(self, obj):
        return self._failed_samples(obj)

    def get_last_error_message(self, obj):
        if obj.error_message:
            return obj.error_message
        samples = self._failed_samples(obj)
        return samples[0]['error_message'] if samples else ''


class CICompletionIssueSerializer(serializers.ModelSerializer):
    ci_name = serializers.CharField(source='ci.name', read_only=True)
    ci_type_name = serializers.CharField(source='ci.ci_type.name', read_only=True)
    ci_business_line = serializers.CharField(source='ci.business_line', read_only=True)
    ci_environment = serializers.CharField(source='ci.environment', read_only=True)
    ci_admin_user = serializers.CharField(source='ci.admin_user', read_only=True)
    ci_department = serializers.SerializerMethodField()
    ci_attributes = serializers.JSONField(source='ci.attributes', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    age_days = serializers.SerializerMethodField()
    due_days = serializers.SerializerMethodField()
    due_at = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = CICompletionIssue
        fields = '__all__'

    def get_ci_department(self, obj):
        return (obj.ci.attributes or {}).get('department', '') if obj.ci_id else ''

    def get_age_days(self, obj):
        return _age_days(obj.created_at)

    def get_due_days(self, obj):
        if obj.severity == 'high':
            return 1
        if obj.severity == 'low':
            return 7
        return 3

    def get_due_at(self, obj):
        return _due_at(obj.created_at, self.get_due_days(obj))

    def get_is_overdue(self, obj):
        return obj.status not in {'resolved', 'ignored'} and _is_overdue(obj.created_at, self.get_due_days(obj))


class CIArchiveCandidateSerializer(serializers.ModelSerializer):
    ci_name = serializers.CharField(source='ci.name', read_only=True)
    ci_type_name = serializers.CharField(source='ci.ci_type.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    age_days = serializers.SerializerMethodField()
    due_days = serializers.SerializerMethodField()
    due_at = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = CIArchiveCandidate
        fields = '__all__'

    def get_age_days(self, obj):
        return _age_days(obj.created_at)

    def get_due_days(self, obj):
        return 7

    def get_due_at(self, obj):
        return _due_at(obj.created_at, self.get_due_days(obj))

    def get_is_overdue(self, obj):
        return obj.status == 'pending' and _is_overdue(obj.created_at, self.get_due_days(obj))


class CIResourceAuthorizationSerializer(serializers.ModelSerializer):
    ci_type_name = serializers.CharField(source='ci_type.name', read_only=True)
    principal_type_display = serializers.CharField(source='get_principal_type_display', read_only=True)
    permission_display = serializers.CharField(source='get_permission_display', read_only=True)
    scope_display = serializers.SerializerMethodField()

    class Meta:
        model = CIResourceAuthorization
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_scope_display(self, obj):
        parts = [
            obj.business_line or '全部业务线',
            obj.environment or '全部环境',
            obj.ci_type.name if obj.ci_type_id else '全部模型',
        ]
        return ' / '.join(parts)

    def validate_principal(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('授权主体不能为空')
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get('permission') == 'manage' and not attrs.get('business_line') and not attrs.get('ci_type'):
            raise serializers.ValidationError('管理授权至少需要限定业务线或资源模型')
        return attrs


class CostRecordSerializer(serializers.ModelSerializer):
    ci_name = serializers.CharField(source='ci.name', read_only=True)
    business_line = serializers.CharField(source='ci.business_line', read_only=True)

    class Meta:
        model = CostRecord
        fields = '__all__'


class CostOptimizationProgressSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = CostOptimizationProgress
        fields = ['id', 'status', 'status_display', 'progress_percent', 'note', 'actual_monthly_saving', 'created_by', 'created_at']


class CostOptimizationTaskSerializer(serializers.ModelSerializer):
    ci_name = serializers.CharField(source='ci.name', read_only=True)
    ci_type = serializers.CharField(source='ci.ci_type.name', read_only=True)
    business_line = serializers.CharField(source='ci.business_line', read_only=True)
    environment = serializers.CharField(source='ci.environment', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    progress_entries = CostOptimizationProgressSerializer(many=True, read_only=True)
    latest_progress = serializers.SerializerMethodField()

    class Meta:
        model = CostOptimizationTask
        fields = [
            'id', 'ci', 'ci_name', 'ci_type', 'business_line', 'environment', 'month',
            'suggestion_type', 'suggestion_title', 'suggestion_snapshot',
            'expected_monthly_saving', 'actual_monthly_saving', 'status', 'status_display',
            'owner', 'claimed_at', 'resolved_by', 'resolved_at', 'latest_progress',
            'progress_entries', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_latest_progress(self, obj):
        entries = list(obj.progress_entries.all())
        if not entries:
            return None
        return CostOptimizationProgressSerializer(entries[0]).data

class ResourceRequestSerializer(serializers.ModelSerializer):
    requester = serializers.CharField(source='applicant', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    environment_display = serializers.SerializerMethodField()
    delivered_ci = serializers.SerializerMethodField()
    delivered_items = serializers.SerializerMethodField()
    delivery_mode = serializers.SerializerMethodField()
    provider = serializers.SerializerMethodField()
    provider_label = serializers.SerializerMethodField()
    provisioning = serializers.SerializerMethodField()
    resource_type_label = serializers.SerializerMethodField()

    class Meta:
        model = ResourceRequest
        fields = '__all__'
        read_only_fields = [
            'applicant', 'approver', 'status', 'approval_comment', 'fulfillment_note',
            'approved_at', 'completed_at', 'created_at', 'updated_at',
        ]

    def get_delivery_mode(self, obj):
        return (obj.specs or {}).get('provisioning_mode') or 'manual'

    def get_provider(self, obj):
        return (obj.specs or {}).get('provider') or ''

    def get_provider_label(self, obj):
        return provider_label(self.get_provider(obj))

    def get_provisioning(self, obj):
        value = (obj.specs or {}).get('provisioning') or {}
        return value if isinstance(value, dict) else {}

    def get_resource_type_label(self, obj):
        value = str(obj.resource_type or '').strip().lower()
        if value in {'主机', 'host', 'ecs'}:
            return '云服务器 ECS'
        return next((item['label'] for item in ALIYUN_RESOURCE_TYPES if item['value'] == value), obj.resource_type or '')

    def get_environment_display(self, obj):
        return obj.get_environment_display() if obj.environment else ''

    def _delivered_mappings(self, obj):
        cached = getattr(obj, '_cmdb_delivered_mappings', None)
        if cached is not None:
            return cached
        request_id = str(obj.id)
        mappings = list(
            CISourceMapping.objects
            .select_related('ci', 'ci__ci_type')
            .filter(
                Q(source_unique_id=request_id) | Q(source_unique_id__startswith=f'{request_id}:'),
                source_type='resource_request',
                ci__isnull=False,
            )
            .order_by('id')
        )
        def sort_key(mapping):
            raw_payload = mapping.raw_payload or {}
            try:
                item_index = int(raw_payload.get('request_item_index') or 0)
            except (TypeError, ValueError):
                item_index = 0
            return (item_index, mapping.source_unique_id, mapping.id)

        mappings.sort(key=sort_key)
        setattr(obj, '_cmdb_delivered_mappings', mappings)
        return mappings

    def _delivered_item(self, mapping):
        if not mapping or not mapping.ci:
            return None
        ci = mapping.ci
        return {
            'id': ci.id,
            'name': ci.name,
            'ci_type_name': resolve_config_item_type_meta(ci)['name'],
            'business_line': ci.business_line,
            'environment': ci.environment,
            'environment_display': ci.get_environment_display() if ci.environment else '',
            'admin_user': ci.admin_user,
            'status': ci.status,
            'status_display': ci.get_status_display() if ci.status else '',
            'source_mapping_id': mapping.id,
            'request_item_index': (mapping.raw_payload or {}).get('request_item_index'),
            'sync_status': mapping.sync_status,
            'last_seen_at': mapping.last_seen_at,
        }

    def get_delivered_items(self, obj):
        return [
            item for item in (self._delivered_item(mapping) for mapping in self._delivered_mappings(obj))
            if item
        ]

    def get_delivered_ci(self, obj):
        items = self.get_delivered_items(obj)
        return items[0] if items else None

    def validate(self, attrs):
        business_line = (attrs.get('business_line') if 'business_line' in attrs else getattr(self.instance, 'business_line', '')) or ''
        environment = (attrs.get('environment') if 'environment' in attrs else getattr(self.instance, 'environment', '')) or ''
        title = (attrs.get('title') if 'title' in attrs else getattr(self.instance, 'title', '')) or ''
        resource_type = (attrs.get('resource_type') if 'resource_type' in attrs else getattr(self.instance, 'resource_type', '')) or ''
        quantity = attrs.get('quantity', getattr(self.instance, 'quantity', 1))

        business_line = business_line.strip()
        title = title.strip()
        resource_type = resource_type.strip()
        if not title:
            raise serializers.ValidationError({'title': '请填写申请标题'})
        aliases = {item['label'].lower(): item['value'] for item in ALIYUN_RESOURCE_TYPES}
        normalized_resource_type = '主机' if resource_type in ['主机', 'host', 'Host', 'HOST', 'ecs', 'ECS'] else aliases.get(resource_type.lower(), resource_type.lower())
        supported_types = {'主机', *ALIYUN_RESOURCE_TYPE_MAP.keys()}
        if normalized_resource_type not in supported_types:
            raise serializers.ValidationError({'resource_type': '请选择平台支持的阿里云资产类型'})
        if quantity < 1:
            raise serializers.ValidationError({'quantity': '数量必须大于 0'})
        if business_line and not ResourceNode.objects.filter(node_type='biz', name=business_line).exists():
            raise serializers.ValidationError({'business_line': '所选业务线未在资源树中配置'})
        if environment:
            if not business_line:
                raise serializers.ValidationError({'environment': '请先选择业务线'})
            if not ResourceNode.objects.filter(node_type='env', parent__name=business_line, name=environment).exists():
                raise serializers.ValidationError({'environment': '所选环境未在当前业务线下配置'})

        attrs['title'] = title
        attrs['resource_type'] = normalized_resource_type
        attrs['business_line'] = business_line
        try:
            raw_specs = attrs.get('specs', getattr(self.instance, 'specs', {})) or {}
            raw_specs = {**raw_specs, 'resource_type': normalized_resource_type}
            attrs['specs'] = validate_provisioning_specs(
                raw_specs,
                quantity,
            )
        except ValueError as exc:
            raise serializers.ValidationError({'specs': str(exc)})
        return attrs

class ResourceNodeSerializer(serializers.ModelSerializer):
    ROOT_NODE_TYPES = {'biz', 'cloud_account'}
    CHILD_NODE_PARENT_TYPES = {
        'env': {'biz'},
        'cloud_region': {'cloud_account'},
        'cloud_cluster': {'cloud_region'},
        'cloud_host': {'cloud_region', 'cloud_cluster'},
    }
    NODE_TYPE_LABELS = {
        'biz': '业务线',
        'env': '环境',
        'cloud_account': '云账号',
        'cloud_region': '云地域',
        'cloud_cluster': '云集群',
        'cloud_host': '云宿主机',
    }

    class Meta:
        model = ResourceNode
        fields = '__all__'

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        name = attrs.get('name', instance.name if instance else '')
        node_type = attrs.get('node_type', instance.node_type if instance else '')
        parent = attrs.get('parent', instance.parent if instance else None)

        if instance and instance.is_synced and instance.node_type in (set(self.CHILD_NODE_PARENT_TYPES) | self.ROOT_NODE_TYPES):
            changed_fields = []
            if 'name' in attrs and attrs['name'] != instance.name:
                changed_fields.append('name')
            if 'node_type' in attrs and attrs['node_type'] != instance.node_type:
                changed_fields.append('node_type')
            if 'parent' in attrs and attrs['parent'] != instance.parent:
                changed_fields.append('parent')
            if 'is_synced' in attrs and attrs['is_synced'] != instance.is_synced:
                changed_fields.append('is_synced')
            if changed_fields:
                raise serializers.ValidationError({'detail': '同步来源节点只能调整排序'})

        if isinstance(name, str):
            name = name.strip()
        if not name:
            raise serializers.ValidationError({'name': '请填写节点名称'})
        attrs['name'] = name

        if node_type in self.ROOT_NODE_TYPES:
            if parent is not None:
                raise serializers.ValidationError({'parent': f'{self.NODE_TYPE_LABELS.get(node_type, "根")}节点不能设置父节点'})
        elif node_type in self.CHILD_NODE_PARENT_TYPES:
            if parent is None:
                raise serializers.ValidationError({'parent': f'{self.NODE_TYPE_LABELS.get(node_type, "子")}节点必须设置父节点'})
            if instance and parent.pk == instance.pk:
                raise serializers.ValidationError({'parent': '节点不能挂在自身下'})
            allowed_parent_types = self.CHILD_NODE_PARENT_TYPES[node_type]
            if parent.node_type not in allowed_parent_types:
                allowed_labels = '或'.join(self.NODE_TYPE_LABELS.get(item, item) for item in allowed_parent_types)
                raise serializers.ValidationError({'parent': f'{self.NODE_TYPE_LABELS.get(node_type, "子")}节点只能挂在{allowed_labels}下'})
        else:
            raise serializers.ValidationError({'node_type': '节点类型不合法'})

        duplicate_qs = ResourceNode.objects.filter(name=name, node_type=node_type, parent=parent)
        if instance:
            duplicate_qs = duplicate_qs.exclude(pk=instance.pk)
        if duplicate_qs.exists():
            if parent is None:
                raise serializers.ValidationError({'name': f'{self.NODE_TYPE_LABELS.get(node_type, "节点")}名称已存在'})
            raise serializers.ValidationError({'name': f'同一父节点下{self.NODE_TYPE_LABELS.get(node_type, "节点")}名称已存在'})

        return attrs
