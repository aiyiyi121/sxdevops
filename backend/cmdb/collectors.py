import json
import ipaddress
import math
import os
import socket
import ssl
from datetime import datetime, timedelta, timezone
from importlib import import_module
from urllib.parse import urlparse

from .prometheus_metrics import enrich_cloud_vm_metrics, enrich_vsphere_vm_metrics


def _optional_import(module_name, install_hint):
    try:
        return import_module(module_name)
    except ImportError as exc:
        raise ValueError(f'{module_name} 未安装，无法执行自动采集；请先安装 {install_hint}') from exc


def _optional_import_or_none(module_name):
    try:
        return import_module(module_name)
    except ImportError:
        return None


DEMO_MODE_DISABLED_MESSAGE = 'Demo 模式已下线，请使用真实账号或凭据引用。'


def _pyvmomi_fault_message(exc):
    return (getattr(exc, 'msg', '') or str(exc) or exc.__class__.__name__).strip()


def _first_non_empty(*values):
    for value in values:
        if value not in (None, '', []):
            return value
    return ''


def _as_list(value):
    if value in (None, ''):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _config_value(config, *keys):
    for key in keys:
        value = (config or {}).get(key)
        if value not in (None, '', []):
            return value
    return ''


def _normalize_endpoint(value, default_port=None):
    text = str(value or '').strip()
    if not text:
        return '', default_port
    if '://' in text:
        parsed = urlparse(text)
    else:
        parsed = urlparse(f'//{text.split("/", 1)[0]}')
    host = (parsed.hostname or text.split('/', 1)[0]).strip().strip('[]')
    port = parsed.port or default_port
    return host, port


def _has_any_config(config, *keys):
    return any(_config_value(config, key) not in (None, '', []) for key in keys)


def _runtime_secret_from_ref(config, name):
    ref = str((config or {}).get('auth_ref') or '').strip()
    if not ref:
        return ''
    env_name = f'{ref}_{name}'.upper()
    return os.environ.get(env_name, '')


def _with_cloud_account(config):
    account_id = _config_value(config, 'cloud_account_id', 'multicloud_account_id')
    if not account_id:
        return dict(config or {})
    try:
        from multicloud.models import CloudCredential
    except ImportError:
        return dict(config or {})
    try:
        credential = CloudCredential.objects.get(id=account_id)
    except (CloudCredential.DoesNotExist, TypeError, ValueError):
        raise ValueError(f'云账号不存在或不可用：{account_id}')
    if not credential.is_enabled:
        raise ValueError(f'云账号已停用：{credential.name}')
    if credential.demo_mode or str(credential.auth_mode or '').strip().lower() == 'demo':
        raise ValueError(DEMO_MODE_DISABLED_MESSAGE)
    merged = dict(config or {})
    metric_config = credential.tags if isinstance(credential.tags, dict) else {}
    for key in ('prometheus_metrics_enabled', 'metric_datasource_id'):
        if key in metric_config:
            merged[key] = metric_config[key]
    preferred_source_account = credential.account_name or credential.name
    current_source_account = str(merged.get('source_account') or '').strip()
    endpoint_values = set()
    for value in (
        credential.account_id,
        merged.get('account_id'),
        merged.get('host'),
        merged.get('server'),
        merged.get('vcenter_host'),
        merged.get('endpoint'),
    ):
        text = str(value or '').strip()
        if not text:
            continue
        endpoint_values.add(text)
        endpoint_values.add(text.rstrip('/'))
        parsed = urlparse(text)
        if parsed.netloc:
            endpoint_values.add(parsed.netloc)
            endpoint_values.add(parsed.netloc.rstrip('/'))
    if preferred_source_account and (not current_source_account or current_source_account.rstrip('/') in endpoint_values):
        merged['source_account'] = preferred_source_account
    else:
        merged.setdefault('source_account', preferred_source_account)
    merged.setdefault('account_id', credential.account_id)
    merged.setdefault('region_id', credential.default_region)
    merged.setdefault('source_region', credential.default_region)
    merged.setdefault('access_key_id', credential.access_key_id)
    merged.setdefault('access_key_secret', credential.access_key_secret)
    merged.setdefault('secret_key', credential.access_key_secret)
    merged.setdefault('project_id', credential.project_id)
    merged.setdefault('provider', credential.provider)
    merged.setdefault('auth_mode', credential.auth_mode)
    merged.setdefault('demo_mode', credential.demo_mode)
    if credential.provider == 'vsphere':
        endpoint = credential.account_id or credential.default_region
        host, port = _normalize_endpoint(endpoint, 443)
        if not merged.get('host'):
            merged['host'] = host
        if not merged.get('vcenter_host'):
            merged['vcenter_host'] = host
        if not merged.get('endpoint'):
            merged['endpoint'] = host
        if port and not merged.get('port'):
            merged['port'] = port
        if not merged.get('username'):
            merged['username'] = credential.access_key_id
        if not merged.get('user'):
            merged['user'] = credential.access_key_id
        if not merged.get('password'):
            merged['password'] = credential.access_key_secret
        if not merged.get('source_region'):
            merged['source_region'] = credential.default_region or credential.account_id or 'private-cloud'
        if not merged.get('provider'):
            merged['provider'] = 'vsphere'
    return merged


def _runtime_collection_config(config, request_data=None):
    merged = _with_cloud_account(config or {})
    runtime_credentials = (request_data or {}).get('runtime_credentials') or {}
    if isinstance(runtime_credentials, dict):
        merged.update({key: value for key, value in runtime_credentials.items() if value not in (None, '')})
    for key, env_name in {
        'username': 'USERNAME',
        'password': 'PASSWORD',
        'access_key_id': 'ACCESS_KEY_ID',
        'access_key_secret': 'ACCESS_KEY_SECRET',
        'secret_key': 'SECRET_KEY',
        'project_id': 'PROJECT_ID',
    }.items():
        if not merged.get(key):
            value = _runtime_secret_from_ref(merged, env_name)
            if value:
                merged[key] = value
    return merged


def _extract_path(data, path):
    current = data or {}
    for key in str(path or '').split('.'):
        key = key.strip()
        if not key:
            continue
        if isinstance(current, dict):
            current = current.get(key)
            continue
        return None
    return current


def _first_list_by_paths(data, paths):
    for path in paths:
        value = _extract_path(data, path)
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
    return []


def _first_ip(*values):
    for value in values:
        for item in _as_list(value):
            if isinstance(item, dict):
                item = _first_non_empty(
                    item.get('IpAddress'),
                    item.get('ip'),
                    item.get('addr'),
                    item.get('Address'),
                    item.get('address'),
                )
            item = str(item or '').strip()
            if item:
                return item
    return ''


def _first_valid_ip(*values):
    for value in values:
        for item in _as_list(value):
            if isinstance(item, dict):
                item = _first_non_empty(
                    item.get('IpAddress'),
                    item.get('ip'),
                    item.get('addr'),
                    item.get('Address'),
                    item.get('address'),
                )
            item = str(item or '').strip()
            if not item:
                continue
            try:
                ipaddress.ip_address(item)
            except ValueError:
                continue
            return item
    return ''


def _nested(data, *keys):
    current = data or {}
    for key in keys:
        if not isinstance(current, dict):
            return ''
        current = current.get(key)
    return current


def _path_value(data, path):
    current = data or {}
    for key in str(path or '').replace('[', '.').replace(']', '').split('.'):
        key = key.strip()
        if not key:
            continue
        if isinstance(current, dict):
            current = current.get(key)
            continue
        if isinstance(current, list):
            try:
                current = current[int(key)]
            except (TypeError, ValueError, IndexError):
                return ''
            continue
        return ''
    return current


def _set_payload_value(payload, target, value):
    if value in (None, ''):
        return
    target = str(target or '').strip()
    if not target:
        return
    top_level_fields = {
        'name',
        'resource_name',
        'ci_type',
        'ci_type_name',
        'ci_type_code',
        'business_line',
        'environment',
        'admin_user',
        'status',
        'source_type',
        'source_account',
        'source_region',
        'source_unique_id',
        'tags',
    }
    if target in top_level_fields:
        payload[target] = value
        return
    attributes = payload.setdefault('attributes', {})
    if not isinstance(attributes, dict):
        attributes = {}
        payload['attributes'] = attributes
    if target.startswith('attributes.'):
        attributes[target.split('.', 1)[1]] = value
    else:
        attributes[target] = value


def _field_mapping_entries(config):
    mapping = (config or {}).get('field_mapping') or (config or {}).get('field_mappings') or []
    if isinstance(mapping, dict):
        return [
            {'target': target, 'source': source}
            for target, source in mapping.items()
            if target and source
        ]
    if isinstance(mapping, list):
        entries = []
        for item in mapping:
            if not isinstance(item, dict):
                continue
            target = item.get('target') or item.get('target_field') or item.get('cmdb_field') or item.get('field')
            source = item.get('source') or item.get('source_field') or item.get('path')
            if target and source:
                entries.append({
                    'target': target,
                    'source': source,
                    'default': item.get('default'),
                    'required': bool(item.get('required')),
                })
        return entries
    return []


def _apply_field_mapping(payload, raw, config):
    entries = _field_mapping_entries(config)
    if not entries:
        return payload
    mapped = dict(payload or {})
    if isinstance((payload or {}).get('attributes'), dict):
        mapped['attributes'] = dict(payload.get('attributes') or {})
    for entry in entries:
        value = _path_value(raw, entry['source'])
        if value in (None, '') and entry.get('default') not in (None, ''):
            value = entry.get('default')
        if value in (None, '') and entry.get('required'):
            raise ValueError(f"Field mapping source missing: {entry['source']}")
        _set_payload_value(mapped, entry['target'], value)
    return mapped


def _tag_value(raw, *names):
    tags = _nested(raw, 'Tags', 'Tag') or raw.get('tags') or raw.get('Tags') or []
    normalized_names = {str(name).lower() for name in names}
    if isinstance(tags, dict):
        tags = tags.get('Tag') or tags.get('tag') or []
    for tag in _as_list(tags):
        if not isinstance(tag, dict):
            continue
        key = str(_first_non_empty(tag.get('Key'), tag.get('key'), tag.get('TagKey'), tag.get('tag_key'))).lower()
        if key in normalized_names:
            return _first_non_empty(tag.get('Value'), tag.get('value'), tag.get('TagValue'), tag.get('tag_value'))
    return ''


def _cloud_tag_entries(raw):
    tags = _nested(raw, 'Tags', 'Tag') or raw.get('tags') or raw.get('Tags') or []
    if isinstance(tags, dict):
        tags = tags.get('Tag') or tags.get('tag') or []
    entries = []
    for tag in _as_list(tags):
        if isinstance(tag, str):
            name = tag.strip()
            if name:
                entries.append({'name': name})
            continue
        if not isinstance(tag, dict):
            continue
        key = _first_non_empty(tag.get('Key'), tag.get('key'), tag.get('TagKey'), tag.get('tag_key'), tag.get('category'))
        value = _first_non_empty(tag.get('Value'), tag.get('value'), tag.get('TagValue'), tag.get('tag_value'), tag.get('name'))
        if value:
            entries.append({'key': str(key or '').strip(), 'value': str(value).strip()})
    return entries


def _memory_gb_from_mb(value):
    try:
        return round(float(value) / 1024, 2)
    except (TypeError, ValueError):
        return ''


def _status_from_cloud(value):
    normalized = str(value or '').strip().lower()
    if normalized in {'running', 'available', 'normal', 'active', 'poweredon', 'power_on', 'on'}:
        return 'active'
    if normalized in {'stopped', 'inactive', 'shutoff', 'poweredoff', 'power_off', 'off'}:
        return 'stopped'
    if normalized in {'deleted', 'deleting', 'released', 'disabled'}:
        return 'offline'
    return 'active'


def _cloud_instance_status(value):
    normalized = str(value or '').strip().lower()
    if normalized in {'running', 'available', 'normal', 'active', 'poweredon', 'power_on', 'on'}:
        return 'Running'
    if normalized in {'stopped', 'inactive', 'shutoff', 'poweredoff', 'power_off', 'off'}:
        return 'Stopped'
    if normalized in {'deleted', 'deleting', 'released', 'disabled'}:
        return 'Deleted'
    return 'Running'


def _url_with_scheme(value):
    value = str(value or '').strip()
    if not value:
        return ''
    if '://' in value:
        return value
    return f'https://{value}'


def _json_object(value):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    text = value.strip()
    if not text.startswith('{'):
        return {}
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _valid_url_or_empty(value):
    text = _url_with_scheme(value)
    if not text:
        return ''
    parsed = urlparse(text)
    if parsed.scheme in {'http', 'https'} and parsed.netloc:
        return text
    return ''


def _aliyun_ack_api_server(value):
    endpoint_payload = _json_object(value)
    endpoint = _first_non_empty(
        endpoint_payload.get('api_server_endpoint'),
        endpoint_payload.get('intranet_api_server_endpoint'),
        endpoint_payload.get('ApiServerEndpoint'),
        endpoint_payload.get('IntranetApiServerEndpoint'),
    ) if endpoint_payload else value
    return _valid_url_or_empty(endpoint)


def _normalized_engine_code(value):
    normalized = str(value or '').strip().lower().replace('-', '').replace('_', '')
    if normalized in {'postgresql', 'postgres', 'pgsql'}:
        return 'postgresql'
    if normalized in {'mysql', 'mariadb'}:
        return 'mysql'
    return normalized


def _first_count(*values):
    for value in values:
        if isinstance(value, dict):
            for child in value.values():
                count = _first_count(child)
                if count != '':
                    return count
            continue
        if isinstance(value, (list, tuple)):
            return len(value)
        if value not in (None, ''):
            return value
    return ''


def _join_non_empty(values, separator=','):
    items = []
    for value in _as_list(values):
        if isinstance(value, dict):
            value = _first_non_empty(
                value.get('VSwitchId'),
                value.get('vSwitchId'),
                value.get('IpAddress'),
                value.get('AllocationId'),
                value.get('InstanceId'),
                value.get('SecurityGroupId'),
                value.get('MountTargetDomain'),
                value.get('domain'),
                value.get('Name'),
            )
        text = str(value or '').strip()
        if text:
            items.append(text)
    return separator.join(items)


def _base_payload(raw, config, *, source_type, unique_id, name, region):
    account = _first_non_empty(config.get('source_account'), config.get('account_name'), config.get('account_id'))
    return {
        'name': name or unique_id,
        'source_type': source_type,
        'source_account': account,
        'source_region': region or config.get('source_region') or config.get('region_id') or '',
        'source_unique_id': unique_id,
        'business_line': _first_non_empty(raw.get('business_line'), _tag_value(raw, 'business_line', 'business', 'biz')),
        'department': _first_non_empty(raw.get('department'), raw.get('dept'), _tag_value(raw, 'department', 'dept', 'org', 'organization')),
        'environment': _first_non_empty(raw.get('environment'), _tag_value(raw, 'environment', 'env')),
        'admin_user': _first_non_empty(raw.get('admin_user'), raw.get('owner'), _tag_value(raw, 'admin_user', 'owner', 'ops_owner')),
        'status': _status_from_cloud(_first_non_empty(
            raw.get('Status'),
            raw.get('status'),
            raw.get('InstanceStatus'),
            raw.get('DBInstanceStatus'),
            raw.get('power_state'),
            raw.get('PowerState'),
        )),
    }


def _aliyun_ecs_item(raw, config):
    instance_id = _first_non_empty(raw.get('InstanceId'), raw.get('instance_id'), raw.get('source_unique_id'))
    private_ip = _first_ip(
        _nested(raw, 'VpcAttributes', 'PrivateIpAddress', 'IpAddress'),
        _nested(raw, 'InnerIpAddress', 'IpAddress'),
        raw.get('PrivateIpAddress'),
        raw.get('private_ip'),
    )
    public_ip = _first_ip(
        _nested(raw, 'PublicIpAddress', 'IpAddress'),
        _nested(raw, 'EipAddress', 'IpAddress'),
        raw.get('PublicIpAddress'),
        raw.get('public_ip'),
    )
    memory_gb = _first_non_empty(raw.get('memory_gb'), _memory_gb_from_mb(raw.get('Memory')))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_ecs',
        unique_id=instance_id,
        name=_first_non_empty(raw.get('InstanceName'), raw.get('HostName'), raw.get('name')),
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': '云主机(ECS)',
        'ci_type_code': config.get('target_ci_type_code') or 'CLOUD_SERVER',
        'attributes': {
            'instance_id': instance_id,
            'private_ip': private_ip,
            'public_ip': public_ip,
            'instance_type': _first_non_empty(raw.get('InstanceType'), raw.get('instance_type')),
            'cpu': _first_non_empty(raw.get('Cpu'), raw.get('cpu')),
            'memory_gb': memory_gb,
            'zone_id': _first_non_empty(raw.get('ZoneId'), raw.get('zone_id')),
            'vpc_id': _nested(raw, 'VpcAttributes', 'VpcId') or raw.get('VpcId'),
            'vswitch_id': _nested(raw, 'VpcAttributes', 'VSwitchId') or raw.get('VSwitchId'),
            'instance_status': _cloud_instance_status(_first_non_empty(raw.get('Status'), raw.get('status'))),
            'os_type': _first_non_empty(raw.get('OSType'), raw.get('OSName'), raw.get('os_type')),
            'expired_time': _first_non_empty(raw.get('ExpiredTime'), raw.get('expired_time')),
            'metric_collection_status': raw.get('_metric_collection_status') or '',
            'metric_collection_source': raw.get('_metric_collection_source') or '',
            'metric_collection_error': raw.get('_metric_collection_error') or '',
            'metric_datasource': raw.get('_metric_datasource') or '',
            'metric_collected_at': raw.get('_metric_collected_at') or '',
            'prometheus_target': raw.get('_prometheus_target') or '',
        },
    })
    metrics = raw.get('_metric_snapshots') if isinstance(raw.get('_metric_snapshots'), list) else []
    if metrics:
        payload['_metric_snapshots'] = metrics
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_rds_item(raw, config):
    instance_id = _first_non_empty(raw.get('DBInstanceId'), raw.get('InstanceId'), raw.get('instance_id'), raw.get('source_unique_id'))
    engine = _first_non_empty(raw.get('Engine'), raw.get('engine')) or 'MySQL'
    engine_code = _normalized_engine_code(engine)
    ci_type_name = 'PostgreSQL' if engine_code == 'postgresql' else 'MySQL'
    ci_type_code = 'POSTGRESQL' if engine_code == 'postgresql' else (config.get('target_ci_type_code') or 'MYSQL')
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_rds',
        unique_id=instance_id,
        name=_first_non_empty(raw.get('DBInstanceDescription'), raw.get('DBInstanceId'), raw.get('name')),
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': ci_type_name,
        'ci_type_code': ci_type_code,
        'attributes': {
            'instance_id': instance_id,
            'endpoint': _first_non_empty(raw.get('ConnectionString'), raw.get('connection_string'), raw.get('endpoint')),
            'port': _first_non_empty(raw.get('Port'), raw.get('port')),
            'engine': engine,
            'version': _first_non_empty(raw.get('EngineVersion'), raw.get('engine_version')),
            'instance_class': _first_non_empty(raw.get('DBInstanceClass'), raw.get('instance_class')),
            'storage_gb': _first_non_empty(raw.get('DBInstanceStorage'), raw.get('storage_gb')),
            'zone_id': _first_non_empty(raw.get('ZoneId'), raw.get('zone_id')),
            'vpc_id': _first_non_empty(raw.get('VpcId'), raw.get('vpc_id'), _nested(raw, 'VpcAttributes', 'VpcId')),
            'vswitch_id': _first_non_empty(raw.get('VSwitchId'), raw.get('vswitch_id'), _nested(raw, 'VpcAttributes', 'VSwitchId')),
            'network_type': _first_non_empty(raw.get('DBInstanceNetType'), raw.get('InstanceNetworkType'), raw.get('network_type')),
            'instance_status': _first_non_empty(raw.get('DBInstanceStatus'), raw.get('Status'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_elasticsearch_item(raw, config):
    cluster_id = _first_non_empty(
        raw.get('instanceId'),
        raw.get('InstanceId'),
        raw.get('cluster_id'),
        raw.get('source_unique_id'),
    )
    datastore = raw.get('nodeSpec') if isinstance(raw.get('nodeSpec'), dict) else {}
    master_config = raw.get('masterConfiguration') if isinstance(raw.get('masterConfiguration'), dict) else {}
    client_config = raw.get('clientNodeConfiguration') if isinstance(raw.get('clientNodeConfiguration'), dict) else {}
    warm_config = raw.get('warmNodeConfiguration') if isinstance(raw.get('warmNodeConfiguration'), dict) else {}
    data_config = raw.get('elasticDataNodeConfiguration') if isinstance(raw.get('elasticDataNodeConfiguration'), dict) else {}

    def _config_storage_gb(node_config):
        if not isinstance(node_config, dict):
            return 0
        amount = _number_or_zero(_first_non_empty(node_config.get('amount'), node_config.get('nodeAmount'), 1))
        disk_size = _number_or_zero(_first_non_empty(node_config.get('disk'), node_config.get('size'), node_config.get('storage')))
        return amount * disk_size

    storage_gb = round(sum(
        _config_storage_gb(node_config)
        for node_config in (datastore, master_config, client_config, warm_config, data_config)
    ), 2)
    endpoint = _first_non_empty(
        raw.get('endpoint'),
        raw.get('domain'),
        raw.get('publicDomain'),
        raw.get('kibanaDomain'),
        raw.get('public_ip'),
        raw.get('publicIp'),
    )
    instance_status = _first_non_empty(raw.get('status'), raw.get('Status'), raw.get('instanceStatus'))
    instances = raw.get('instances') if isinstance(raw.get('instances'), list) else []
    node_count = _first_non_empty(raw.get('nodeAmount'), raw.get('node_count'), len(instances))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_elasticsearch',
        unique_id=cluster_id,
        name=_first_non_empty(raw.get('description'), raw.get('name'), raw.get('instanceName'), cluster_id),
        region=_first_non_empty(raw.get('regionId'), raw.get('RegionId'), raw.get('region')),
    )
    payload.update({
        'ci_type_name': 'Elasticsearch',
        'ci_type_code': config.get('target_ci_type_code') or 'ELASTICSEARCH',
        'attributes': {
            'cluster_id': cluster_id,
            'endpoint': endpoint,
            'version': _first_non_empty(
                raw.get('esVersion'),
                raw.get('version'),
                _nested(raw, 'datastore', 'version'),
            ),
            'node_count': node_count,
            'index_count': _first_non_empty(raw.get('index_count'), raw.get('indexCount')),
            'storage_gb': storage_gb or _first_non_empty(raw.get('storage_gb')),
            'public_ip': _first_non_empty(raw.get('public_ip'), raw.get('publicIp')),
            'vpc_id': _first_non_empty(raw.get('vpcId'), raw.get('VpcId')),
            'subnet_id': _first_non_empty(raw.get('subnetId'), raw.get('SubnetId')),
            'security_group_id': _first_non_empty(raw.get('securityGroupId'), raw.get('SecurityGroupId')),
            'instance_status': _first_non_empty(instance_status, 'Available'),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_ack_item(raw, config):
    cluster_id = _first_non_empty(raw.get('cluster_id'), raw.get('ClusterId'), raw.get('clusterId'), raw.get('Id'), raw.get('source_unique_id'))
    api_server = _first_non_empty(raw.get('api_server'), raw.get('ApiServer'), raw.get('MasterUrl'), raw.get('master_url'), raw.get('endpoint'))
    api_server_endpoints = _json_object(api_server)
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_ack',
        unique_id=cluster_id,
        name=_first_non_empty(raw.get('name'), raw.get('Name'), raw.get('cluster_name'), raw.get('ClusterName'), cluster_id),
        region=_first_non_empty(raw.get('region_id'), raw.get('RegionId'), raw.get('region')),
    )
    payload.update({
        'ci_type_name': 'K8s Cluster',
        'ci_type_code': config.get('target_ci_type_code') or 'K8S_CLUSTER',
        'attributes': {
            'cluster_id': cluster_id,
            'api_server': _aliyun_ack_api_server(api_server),
            'api_server_endpoints': api_server_endpoints,
            'version': _first_non_empty(raw.get('version'), raw.get('Version'), raw.get('current_version'), raw.get('CurrentVersion')),
            'node_count': _first_non_empty(raw.get('node_count'), raw.get('NodeCount'), raw.get('size'), raw.get('Size')),
            'cluster_type': _first_non_empty(raw.get('cluster_type'), raw.get('ClusterType'), raw.get('type'), raw.get('Profile')),
            'profile': _first_non_empty(raw.get('profile'), raw.get('Profile')),
            'network_mode': _first_non_empty(raw.get('network_mode'), raw.get('NetworkMode')),
            'vpc_id': _first_non_empty(raw.get('vpc_id'), raw.get('VpcId'), raw.get('vpcid')),
            'vswitch_ids': _join_non_empty(_first_non_empty(raw.get('vswitch_ids'), raw.get('VSwitchIds'), raw.get('VSwitches'))),
            'security_group_id': _first_non_empty(raw.get('security_group_id'), raw.get('SecurityGroupId')),
            'deletion_protection': _first_non_empty(raw.get('deletion_protection'), raw.get('DeletionProtection')),
            'created_at': _first_non_empty(raw.get('created'), raw.get('Created'), raw.get('created_at'), raw.get('CreationTime')),
            'instance_status': _first_non_empty(raw.get('state'), raw.get('State'), raw.get('status'), raw.get('Status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_redis_item(raw, config):
    instance_id = _first_non_empty(raw.get('InstanceId'), raw.get('KVStoreInstanceId'), raw.get('instance_id'), raw.get('source_unique_id'))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_redis',
        unique_id=instance_id,
        name=_first_non_empty(raw.get('InstanceName'), raw.get('instance_name'), raw.get('name'), instance_id),
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': 'Redis',
        'ci_type_code': config.get('target_ci_type_code') or 'REDIS',
        'attributes': {
            'instance_id': instance_id,
            'endpoint': _first_non_empty(raw.get('ConnectionDomain'), raw.get('connection_domain'), raw.get('endpoint')),
            'port': _first_non_empty(raw.get('Port'), raw.get('port')),
            'version': _first_non_empty(raw.get('EngineVersion'), raw.get('engine_version')),
            'memory_gb': _first_non_empty(raw.get('memory_gb'), raw.get('Capacity'), raw.get('capacity_gb')),
            'zone_id': _first_non_empty(raw.get('ZoneId'), raw.get('zone_id')),
            'vpc_id': _first_non_empty(raw.get('VpcId'), raw.get('vpc_id'), _nested(raw, 'VpcAttributes', 'VpcId')),
            'vswitch_id': _first_non_empty(raw.get('VSwitchId'), raw.get('vswitch_id'), _nested(raw, 'VpcAttributes', 'VSwitchId')),
            'private_ip': _first_non_empty(raw.get('PrivateIp'), raw.get('private_ip'), raw.get('PrivateIPAddress')),
            'network_type': _first_non_empty(raw.get('NetworkType'), raw.get('InstanceNetworkType'), raw.get('network_type')),
            'instance_status': _first_non_empty(raw.get('InstanceStatus'), raw.get('Status'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_mongodb_item(raw, config):
    instance_id = _first_non_empty(raw.get('DBInstanceId'), raw.get('InstanceId'), raw.get('instance_id'), raw.get('source_unique_id'))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_mongodb',
        unique_id=instance_id,
        name=_first_non_empty(raw.get('DBInstanceDescription'), raw.get('InstanceName'), raw.get('name'), instance_id),
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': 'MongoDB',
        'ci_type_code': config.get('target_ci_type_code') or 'MONGODB',
        'attributes': {
            'instance_id': instance_id,
            'endpoint': _first_non_empty(raw.get('ConnectionString'), raw.get('ConnectionDomain'), raw.get('endpoint')),
            'port': _first_non_empty(raw.get('Port'), raw.get('port')),
            'engine': _first_non_empty(raw.get('Engine'), raw.get('engine')) or 'MongoDB',
            'version': _first_non_empty(raw.get('EngineVersion'), raw.get('DBInstanceVersion'), raw.get('version')),
            'instance_class': _first_non_empty(raw.get('DBInstanceClass'), raw.get('instance_class')),
            'storage_gb': _first_non_empty(raw.get('DBInstanceStorage'), raw.get('Storage'), raw.get('storage_gb')),
            'replica_count': _first_non_empty(raw.get('ReplicaCount'), raw.get('replica_count'), raw.get('NodeCount')),
            'zone_id': _first_non_empty(raw.get('ZoneId'), raw.get('zone_id')),
            'vpc_id': _first_non_empty(raw.get('VpcId'), raw.get('vpc_id'), _nested(raw, 'VpcAttributes', 'VpcId')),
            'vswitch_id': _first_non_empty(raw.get('VSwitchId'), raw.get('vswitch_id'), _nested(raw, 'VpcAttributes', 'VSwitchId')),
            'network_type': _first_non_empty(raw.get('NetworkType'), raw.get('DBInstanceNetType'), raw.get('network_type')),
            'instance_status': _first_non_empty(raw.get('DBInstanceStatus'), raw.get('Status'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_kafka_item(raw, config):
    instance_id = _first_non_empty(raw.get('InstanceId'), raw.get('instance_id'), raw.get('source_unique_id'))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_kafka',
        unique_id=instance_id,
        name=_first_non_empty(raw.get('Name'), raw.get('InstanceName'), raw.get('name'), instance_id),
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': 'Kafka',
        'ci_type_code': config.get('target_ci_type_code') or 'KAFKA',
        'attributes': {
            'instance_id': instance_id,
            'endpoint': _first_non_empty(raw.get('Endpoint'), raw.get('BootstrapServers'), raw.get('connection_string'), raw.get('endpoint')),
            'port': _first_non_empty(raw.get('Port'), raw.get('port')),
            'version': _first_non_empty(raw.get('Version'), raw.get('KafkaVersion'), raw.get('version')),
            'instance_class': _first_non_empty(raw.get('SpecType'), raw.get('InstanceType'), raw.get('instance_class')),
            'topic_count': _first_non_empty(raw.get('TopicNum'), raw.get('TopicCount'), raw.get('topic_count')),
            'partition_count': _first_non_empty(raw.get('PartitionNum'), raw.get('PartitionCount'), raw.get('partition_count')),
            'storage_gb': _first_non_empty(raw.get('DiskSize'), raw.get('Storage'), raw.get('storage_gb')),
            'message_lag': _first_non_empty(raw.get('MessageLag'), raw.get('message_lag')),
            'zone_id': _first_non_empty(raw.get('ZoneId'), raw.get('zone_id')),
            'vpc_id': _first_non_empty(raw.get('VpcId'), raw.get('vpc_id')),
            'vswitch_id': _first_non_empty(raw.get('VSwitchId'), raw.get('vswitch_id')),
            'network_type': _first_non_empty(raw.get('NetworkType'), raw.get('network_type')),
            'instance_status': _first_non_empty(raw.get('Status'), raw.get('InstanceStatus'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_rocketmq_item(raw, config):
    instance_id = _first_non_empty(raw.get('InstanceId'), raw.get('instance_id'), raw.get('source_unique_id'))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_rocketmq',
        unique_id=instance_id,
        name=_first_non_empty(raw.get('InstanceName'), raw.get('Name'), raw.get('name'), instance_id),
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': 'RocketMQ',
        'ci_type_code': config.get('target_ci_type_code') or 'ROCKETMQ',
        'attributes': {
            'instance_id': instance_id,
            'endpoint': _first_non_empty(raw.get('NameSrvEndpoint'), raw.get('TcpEndpoint'), raw.get('Endpoint'), raw.get('endpoint')),
            'http_endpoint': _first_non_empty(raw.get('HttpEndpoint'), raw.get('http_endpoint')),
            'version': _first_non_empty(raw.get('Version'), raw.get('InstanceVersion'), raw.get('version')),
            'instance_class': _first_non_empty(raw.get('InstanceType'), raw.get('Spec'), raw.get('instance_class')),
            'topic_count': _first_non_empty(raw.get('TopicCount'), raw.get('topic_count')),
            'group_count': _first_non_empty(raw.get('GroupCount'), raw.get('group_count')),
            'message_lag': _first_non_empty(raw.get('MessageLag'), raw.get('message_lag')),
            'zone_id': _first_non_empty(raw.get('ZoneId'), raw.get('zone_id')),
            'vpc_id': _first_non_empty(raw.get('VpcId'), raw.get('vpc_id')),
            'vswitch_id': _first_non_empty(raw.get('VSwitchId'), raw.get('vswitch_id')),
            'network_type': _first_non_empty(raw.get('NetworkType'), raw.get('network_type')),
            'instance_status': _first_non_empty(raw.get('Status'), raw.get('InstanceStatus'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_oss_item(raw, config):
    bucket = _first_non_empty(raw.get('Name'), raw.get('BucketName'), raw.get('bucket'), raw.get('source_unique_id'))
    endpoint = _url_with_scheme(_first_non_empty(raw.get('ExtranetEndpoint'), raw.get('IntranetEndpoint'), raw.get('Endpoint'), raw.get('endpoint')))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_oss',
        unique_id=bucket,
        name=bucket,
        region=_first_non_empty(raw.get('Location'), raw.get('RegionId'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': '对象存储',
        'ci_type_code': config.get('target_ci_type_code') or 'OBJECT_STORAGE',
        'attributes': {
            'bucket': bucket,
            'endpoint': endpoint,
            'storage_gb': _first_non_empty(raw.get('StorageGB'), raw.get('Storage'), raw.get('storage_gb')),
            'storage_class': _first_non_empty(raw.get('StorageClass'), raw.get('storage_class')),
            'acl': _first_non_empty(raw.get('Acl'), raw.get('ACL'), raw.get('acl')),
            'region': _first_non_empty(raw.get('Location'), raw.get('RegionId'), raw.get('region_id')),
            'created_at': _first_non_empty(raw.get('CreationDate'), raw.get('created_at')),
            'instance_status': _first_non_empty(raw.get('Status'), raw.get('status')) or 'Available',
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_slb_item(raw, config):
    instance_id = _first_non_empty(raw.get('LoadBalancerId'), raw.get('InstanceId'), raw.get('instance_id'), raw.get('source_unique_id'))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_slb',
        unique_id=instance_id,
        name=_first_non_empty(raw.get('LoadBalancerName'), raw.get('InstanceName'), raw.get('name'), instance_id),
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': '负载均衡',
        'ci_type_code': config.get('target_ci_type_code') or 'LOAD_BALANCER',
        'attributes': {
            'instance_id': instance_id,
            'vip': _first_ip(raw.get('Address'), raw.get('LoadBalancerIpAddress'), raw.get('vip')),
            'domain': _first_non_empty(raw.get('Address'), raw.get('Domain'), raw.get('domain')),
            'bandwidth': _first_non_empty(raw.get('Bandwidth'), raw.get('bandwidth')),
            'instance_class': _first_non_empty(raw.get('LoadBalancerSpec'), raw.get('Spec'), raw.get('instance_class')),
            'network_type': _first_non_empty(raw.get('AddressType'), raw.get('NetworkType'), raw.get('network_type')),
            'zone_id': _first_non_empty(raw.get('MasterZoneId'), raw.get('ZoneId'), raw.get('zone_id')),
            'vpc_id': _first_non_empty(raw.get('VpcId'), raw.get('vpc_id')),
            'vswitch_id': _first_non_empty(raw.get('VSwitchId'), raw.get('vswitch_id')),
            'backend_count': _first_non_empty(raw.get('BackendServerCount'), raw.get('backend_count')),
            'instance_status': _first_non_empty(raw.get('LoadBalancerStatus'), raw.get('Status'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_disk_item(raw, config):
    disk_id = _first_non_empty(raw.get('DiskId'), raw.get('disk_id'), raw.get('VolumeId'), raw.get('volume_id'), raw.get('source_unique_id'))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_disk',
        unique_id=disk_id,
        name=_first_non_empty(raw.get('DiskName'), raw.get('Name'), raw.get('name'), disk_id),
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': 'Block Storage',
        'ci_type_code': config.get('target_ci_type_code') or 'BLOCK_STORAGE',
        'attributes': {
            'volume_id': disk_id,
            'volume_type': _first_non_empty(raw.get('Category'), raw.get('Type'), raw.get('DiskType'), raw.get('volume_type')),
            'capacity_gb': _first_non_empty(raw.get('Size'), raw.get('DiskSize'), raw.get('capacity_gb')),
            'iops': _first_non_empty(raw.get('IOPS'), raw.get('Iops'), raw.get('iops')),
            'attached_to': _first_non_empty(raw.get('InstanceId'), raw.get('AttachedInstanceId'), raw.get('attached_to')),
            'device': _first_non_empty(raw.get('Device'), raw.get('device')),
            'zone_id': _first_non_empty(raw.get('ZoneId'), raw.get('zone_id')),
            'encrypted': _first_non_empty(raw.get('Encrypted'), raw.get('encrypted')),
            'performance_level': _first_non_empty(raw.get('PerformanceLevel'), raw.get('performance_level')),
            'billing_method': _first_non_empty(raw.get('DiskChargeType'), raw.get('ChargeType'), raw.get('billing_method')),
            'created_at': _first_non_empty(raw.get('CreationTime'), raw.get('CreatedTime'), raw.get('created_at')),
            'instance_status': _first_non_empty(raw.get('Status'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_nas_item(raw, config):
    filesystem_id = _first_non_empty(raw.get('FileSystemId'), raw.get('filesystem_id'), raw.get('FileSystemName'), raw.get('source_unique_id'))
    mount_targets = _first_non_empty(
        _nested(raw, 'MountTargets', 'MountTarget'),
        raw.get('MountTargets'),
        raw.get('mount_targets'),
    )
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_nas',
        unique_id=filesystem_id,
        name=_first_non_empty(raw.get('Description'), raw.get('FileSystemName'), raw.get('Name'), raw.get('name'), filesystem_id),
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': 'File Storage',
        'ci_type_code': config.get('target_ci_type_code') or 'FILE_STORAGE',
        'attributes': {
            'filesystem_id': filesystem_id,
            'mount_target': _first_non_empty(raw.get('MountTargetDomain'), raw.get('mount_target'), _join_non_empty(mount_targets)),
            'protocol': str(_first_non_empty(raw.get('ProtocolType'), raw.get('Protocol'), raw.get('protocol'))).lower(),
            'capacity_gb': _first_non_empty(raw.get('Capacity'), raw.get('CapacityGB'), raw.get('capacity_gb')),
            'used_gb': _first_non_empty(raw.get('MeteredSize'), raw.get('UsedGB'), raw.get('used_gb')),
            'storage_type': _first_non_empty(raw.get('StorageType'), raw.get('storage_type')),
            'zone_id': _first_non_empty(raw.get('ZoneId'), raw.get('zone_id')),
            'vpc_id': _first_non_empty(raw.get('VpcId'), raw.get('vpc_id')),
            'created_at': _first_non_empty(raw.get('CreateTime'), raw.get('CreationTime'), raw.get('created_at')),
            'instance_status': _first_non_empty(raw.get('Status'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_clickhouse_item(raw, config):
    cluster_id = _first_non_empty(raw.get('DBClusterId'), raw.get('ClusterId'), raw.get('cluster_id'), raw.get('source_unique_id'))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_clickhouse',
        unique_id=cluster_id,
        name=_first_non_empty(raw.get('DBClusterDescription'), raw.get('DBClusterName'), raw.get('ClusterName'), raw.get('name'), cluster_id),
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': 'ClickHouse',
        'ci_type_code': config.get('target_ci_type_code') or 'CLICKHOUSE',
        'attributes': {
            'cluster_id': cluster_id,
            'endpoint': _first_non_empty(raw.get('ConnectionString'), raw.get('Endpoint'), raw.get('endpoint')),
            'version': _first_non_empty(raw.get('EngineVersion'), raw.get('Version'), raw.get('version')),
            'shard_count': _first_non_empty(raw.get('ShardCount'), raw.get('shard_count')),
            'replica_count': _first_non_empty(raw.get('ReplicaCount'), raw.get('replica_count')),
            'node_count': _first_non_empty(raw.get('NodeCount'), raw.get('node_count')),
            'storage_gb': _first_non_empty(raw.get('StorageSize'), raw.get('DBNodeStorage'), raw.get('storage_gb')),
            'instance_class': _first_non_empty(raw.get('DBNodeClass'), raw.get('Category'), raw.get('instance_class')),
            'vpc_id': _first_non_empty(raw.get('VpcId'), raw.get('vpc_id')),
            'vswitch_id': _first_non_empty(raw.get('VSwitchId'), raw.get('vswitch_id')),
            'instance_status': _first_non_empty(raw.get('DBClusterStatus'), raw.get('Status'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_hologres_item(raw, config):
    instance_id = _first_non_empty(raw.get('InstanceId'), raw.get('instance_id'), raw.get('Id'), raw.get('source_unique_id'))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_hologres',
        unique_id=instance_id,
        name=_first_non_empty(raw.get('InstanceName'), raw.get('Name'), raw.get('name'), instance_id),
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id'), raw.get('region')),
    )
    payload.update({
        'ci_type_name': 'Hologres',
        'ci_type_code': config.get('target_ci_type_code') or 'HOLOGRES',
        'attributes': {
            'instance_id': instance_id,
            'endpoint': _first_non_empty(raw.get('Endpoint'), raw.get('ConnectionString'), raw.get('endpoint')),
            'region': _first_non_empty(raw.get('RegionId'), raw.get('region_id'), raw.get('region')),
            'version': _first_non_empty(raw.get('Version'), raw.get('EngineVersion'), raw.get('version')),
            'cpu': _first_non_empty(raw.get('Cpu'), raw.get('CpuCore'), raw.get('Cores'), raw.get('cpu')),
            'storage_gb': _first_non_empty(raw.get('StorageGB'), raw.get('StorageSize'), raw.get('storage_gb')),
            'instance_class': _first_non_empty(raw.get('InstanceType'), raw.get('InstanceClass'), raw.get('instance_class')),
            'zone_id': _first_non_empty(raw.get('ZoneId'), raw.get('zone_id')),
            'vpc_id': _first_non_empty(raw.get('VpcId'), raw.get('vpc_id')),
            'vswitch_id': _first_non_empty(raw.get('VSwitchId'), raw.get('vswitch_id')),
            'instance_status': _first_non_empty(raw.get('Status'), raw.get('InstanceStatus'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_maxcompute_item(raw, config):
    project_name = _first_non_empty(raw.get('ProjectName'), raw.get('project_name'), raw.get('Name'), raw.get('source_unique_id'))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_maxcompute',
        unique_id=project_name,
        name=project_name,
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id'), raw.get('region')),
    )
    payload.update({
        'ci_type_name': 'MaxCompute',
        'ci_type_code': config.get('target_ci_type_code') or 'MAXCOMPUTE',
        'attributes': {
            'project_name': project_name,
            'region': _first_non_empty(raw.get('RegionId'), raw.get('region_id'), raw.get('region')),
            'quota_name': _first_non_empty(raw.get('QuotaName'), raw.get('DefaultQuota'), raw.get('quota_name')),
            'storage_gb': _first_non_empty(raw.get('StorageGB'), raw.get('StorageSize'), raw.get('storage_gb')),
            'table_count': _first_non_empty(raw.get('TableCount'), raw.get('table_count')),
            'job_count': _first_non_empty(raw.get('JobCount'), raw.get('job_count')),
            'owner': _first_non_empty(raw.get('Owner'), raw.get('owner')),
            'created_at': _first_non_empty(raw.get('CreateTime'), raw.get('created_at')),
            'instance_status': _first_non_empty(raw.get('Status'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_dataworks_item(raw, config):
    workspace_id = _first_non_empty(raw.get('ProjectId'), raw.get('WorkspaceId'), raw.get('workspace_id'), raw.get('Id'), raw.get('source_unique_id'))
    workspace_name = _first_non_empty(raw.get('ProjectName'), raw.get('WorkspaceName'), raw.get('workspace_name'), raw.get('Name'), workspace_id)
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_dataworks',
        unique_id=workspace_id,
        name=workspace_name,
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id'), raw.get('region')),
    )
    payload.update({
        'ci_type_name': 'DataWorks',
        'ci_type_code': config.get('target_ci_type_code') or 'DATAWORKS',
        'attributes': {
            'workspace_id': workspace_id,
            'workspace_name': workspace_name,
            'region': _first_non_empty(raw.get('RegionId'), raw.get('region_id'), raw.get('region')),
            'edition': _first_non_empty(raw.get('ProjectMode'), raw.get('Edition'), raw.get('edition')),
            'node_count': _first_non_empty(raw.get('NodeCount'), raw.get('node_count')),
            'workflow_count': _first_non_empty(raw.get('WorkflowCount'), raw.get('workflow_count')),
            'owner': _first_non_empty(raw.get('Owner'), raw.get('owner')),
            'created_at': _first_non_empty(raw.get('CreateTime'), raw.get('created_at')),
            'instance_status': _first_non_empty(raw.get('Status'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_nat_gateway_item(raw, config):
    instance_id = _first_non_empty(raw.get('NatGatewayId'), raw.get('InstanceId'), raw.get('nat_gateway_id'), raw.get('source_unique_id'))
    eip_addresses = _first_non_empty(_nested(raw, 'IpLists', 'IpList'), raw.get('EipAddresses'), raw.get('eip_addresses'))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_nat_gateway',
        unique_id=instance_id,
        name=_first_non_empty(raw.get('Name'), raw.get('NatGatewayName'), raw.get('name'), instance_id),
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': 'NAT Gateway',
        'ci_type_code': config.get('target_ci_type_code') or 'NAT_GATEWAY',
        'attributes': {
            'instance_id': instance_id,
            'gateway_type': _first_non_empty(raw.get('NatType'), raw.get('Type'), raw.get('gateway_type')),
            'spec': _first_non_empty(raw.get('Spec'), raw.get('InstanceType'), raw.get('spec')),
            'vpc_id': _first_non_empty(raw.get('VpcId'), raw.get('vpc_id')),
            'vswitch_id': _first_non_empty(raw.get('VSwitchId'), raw.get('vswitch_id')),
            'eip_addresses': _join_non_empty(eip_addresses),
            'snat_entry_count': _first_non_empty(raw.get('SnatEntryCount'), raw.get('snat_entry_count')),
            'forward_entry_count': _first_non_empty(raw.get('ForwardEntryCount'), raw.get('forward_entry_count')),
            'network_type': _first_non_empty(raw.get('NetworkType'), raw.get('network_type')),
            'created_at': _first_non_empty(raw.get('CreationTime'), raw.get('CreatedTime'), raw.get('created_at')),
            'instance_status': _first_non_empty(raw.get('Status'), raw.get('NatGatewayStatus'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


def _aliyun_eip_item(raw, config):
    allocation_id = _first_non_empty(raw.get('AllocationId'), raw.get('EipAddressId'), raw.get('allocation_id'), raw.get('source_unique_id'))
    ip_address = _first_non_empty(raw.get('IpAddress'), raw.get('EipAddress'), raw.get('PublicIpAddress'), raw.get('ip_address'))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'aliyun_eip',
        unique_id=allocation_id or ip_address,
        name=_first_non_empty(raw.get('Name'), raw.get('InstanceName'), raw.get('name'), ip_address, allocation_id),
        region=_first_non_empty(raw.get('RegionId'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': 'Elastic IP',
        'ci_type_code': config.get('target_ci_type_code') or 'ELASTIC_IP',
        'attributes': {
            'allocation_id': allocation_id,
            'ip_address': ip_address,
            'bandwidth': _first_non_empty(raw.get('Bandwidth'), raw.get('bandwidth')),
            'internet_charge_type': _first_non_empty(raw.get('InternetChargeType'), raw.get('ChargeType'), raw.get('internet_charge_type')),
            'attached_to': _first_non_empty(raw.get('InstanceId'), raw.get('AssociatedInstanceId'), raw.get('attached_to')),
            'instance_type': _first_non_empty(raw.get('InstanceType'), raw.get('AssociatedInstanceType'), raw.get('instance_type')),
            'isp': _first_non_empty(raw.get('ISP'), raw.get('Isp'), raw.get('isp')),
            'created_at': _first_non_empty(raw.get('AllocationTime'), raw.get('CreationTime'), raw.get('created_at')),
            'instance_status': _first_non_empty(raw.get('Status'), raw.get('status')),
        },
    })
    cloud_tags = _cloud_tag_entries(raw)
    if cloud_tags:
        payload['tags'] = cloud_tags
        payload['attributes']['cloud_tags'] = cloud_tags
    return payload


ALIYUN_NORMALIZERS = {
    'ecs': _aliyun_ecs_item,
    'cloud_server': _aliyun_ecs_item,
    'rds': _aliyun_rds_item,
    'mysql': _aliyun_rds_item,
    'postgresql': _aliyun_rds_item,
    'postgres': _aliyun_rds_item,
    'elasticsearch': _aliyun_elasticsearch_item,
    'es': _aliyun_elasticsearch_item,
    'ack': _aliyun_ack_item,
    'cs': _aliyun_ack_item,
    'k8s': _aliyun_ack_item,
    'k8s_cluster': _aliyun_ack_item,
    'redis': _aliyun_redis_item,
    'kvstore': _aliyun_redis_item,
    'mongodb': _aliyun_mongodb_item,
    'mongo': _aliyun_mongodb_item,
    'kafka': _aliyun_kafka_item,
    'rocketmq': _aliyun_rocketmq_item,
    'ons': _aliyun_rocketmq_item,
    'oss': _aliyun_oss_item,
    'object_storage': _aliyun_oss_item,
    'disk': _aliyun_disk_item,
    'disks': _aliyun_disk_item,
    'cloud_disk': _aliyun_disk_item,
    'block_storage': _aliyun_disk_item,
    'nfs': _aliyun_nas_item,
    'nas': _aliyun_nas_item,
    'file_storage': _aliyun_nas_item,
    'clickhouse': _aliyun_clickhouse_item,
    'hologres': _aliyun_hologres_item,
    'maxcompute': _aliyun_maxcompute_item,
    'odps': _aliyun_maxcompute_item,
    'dataworks': _aliyun_dataworks_item,
    'slb': _aliyun_slb_item,
    'load_balancer': _aliyun_slb_item,
    'nat': _aliyun_nat_gateway_item,
    'nat_gateway': _aliyun_nat_gateway_item,
    'eip': _aliyun_eip_item,
    'elastic_ip': _aliyun_eip_item,
}


def _vsphere_vm_item(raw, config):
    vm_id = _first_non_empty(raw.get('vm'), raw.get('vm_id'), raw.get('moid'), raw.get('source_unique_id'), raw.get('uuid'))
    target_ci_type_code = config.get('target_ci_type_code') or 'VIRTUAL_MACHINE'
    if str(target_ci_type_code).upper() == 'CLOUD_SERVER':
        target_ci_type_code = 'VIRTUAL_MACHINE'
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'vsphere_vm',
        unique_id=vm_id,
        name=_first_non_empty(raw.get('name'), raw.get('Name'), raw.get('guest_name'), vm_id),
        region=_first_non_empty(raw.get('datacenter'), raw.get('Datacenter'), raw.get('source_region')),
    )
    payload.update({
        'ci_type_name': '虚拟机',
        'ci_type_code': target_ci_type_code,
        'attributes': {
            'instance_id': vm_id,
            'private_ip': _first_ip(raw.get('ip_address'), raw.get('ip'), raw.get('guest_ip'), raw.get('GuestIpAddress')),
            'public_ip': _first_ip(raw.get('public_ip')),
            'instance_type': _first_non_empty(raw.get('template'), raw.get('hardware_version'), raw.get('instance_type')),
            'cpu': _first_non_empty(raw.get('cpu'), raw.get('num_cpu'), raw.get('NumCpu')),
            'memory_gb': _first_non_empty(raw.get('memory_gb'), _memory_gb_from_mb(raw.get('memory_mb') or raw.get('MemoryMB'))),
            'disk_gb': _first_non_empty(raw.get('disk_gb'), raw.get('provisioned_gb'), raw.get('ProvisionedGB')),
            'cpu_used_mhz': _first_non_empty(raw.get('cpu_used_mhz'), raw.get('CpuUsedMhz')),
            'cpu_usage_percent': _first_non_empty(raw.get('cpu_usage_percent'), raw.get('cpu_usage')),
            'memory_used_gb': _first_non_empty(raw.get('memory_used_gb'), raw.get('MemoryUsedGB')),
            'memory_usage_percent': _first_non_empty(raw.get('memory_usage_percent'), raw.get('memory_usage')),
            'memory_total_gb': raw.get('memory_total_gb'),
            'memory_free_gb': raw.get('memory_free_gb'),
            'memory_available_gb': raw.get('memory_available_gb'),
            'disk_used_gb': _first_non_empty(raw.get('disk_used_gb'), raw.get('storage_used_gb'), raw.get('committed_gb')),
            'disk_usage_percent': _first_non_empty(raw.get('disk_usage_percent'), raw.get('storage_usage'), raw.get('storage_usage_percent')),
            'root_disk_total_gb': raw.get('root_disk_total_gb'),
            'root_disk_free_gb': raw.get('root_disk_free_gb'),
            'root_disk_available_gb': raw.get('root_disk_available_gb'),
            'root_mountpoint': raw.get('root_mountpoint'),
            'datacenter': _first_non_empty(raw.get('datacenter'), raw.get('Datacenter')),
            'cluster': _first_non_empty(raw.get('cluster'), raw.get('Cluster')),
            'host': _first_non_empty(raw.get('host'), raw.get('Host')),
            'folder': _first_non_empty(raw.get('folder'), raw.get('Folder')),
            'os_type': _first_non_empty(raw.get('guest_os'), raw.get('GuestFullName'), raw.get('os_type')),
            'instance_status': _cloud_instance_status(_first_non_empty(raw.get('power_state'), raw.get('PowerState'), raw.get('status'))),
            'cloud_provider': 'vSphere',
            'metric_collection_status': raw.get('_metric_collection_status') or '',
            'metric_collection_source': raw.get('_metric_collection_source') or '',
            'metric_collection_error': raw.get('_metric_collection_error') or '',
            'metric_datasource': raw.get('_metric_datasource') or '',
            'metric_collected_at': raw.get('_metric_collected_at') or '',
            'prometheus_target': raw.get('_prometheus_target') or '',
        },
    })
    metrics = raw.get('_metric_snapshots') if isinstance(raw.get('_metric_snapshots'), list) else []
    if metrics:
        payload['_metric_snapshots'] = metrics
    return payload


def _vsphere_host_unique_id(raw):
    raw_id = _first_non_empty(raw.get('source_unique_id'), raw.get('host_id'), raw.get('moid'), raw.get('host'), raw.get('name'))
    raw_id = str(raw_id or '').strip()
    if raw_id.startswith('host:'):
        return raw_id
    return f'host:{raw_id}' if raw_id else ''


def _vsphere_host_lifecycle_status(raw):
    if raw.get('maintenance_mode') is True:
        return 'maintenance'
    state = str(_first_non_empty(raw.get('connection_state'), raw.get('power_state'), raw.get('status'))).lower()
    if 'disconnect' in state or 'notrespond' in state or 'standby' in state:
        return 'offline'
    if 'maintenance' in state:
        return 'maintenance'
    return 'running'


def _vsphere_host_metric_snapshots(raw):
    snapshots = []
    cpu_usage_percent = _first_non_empty(raw.get('cpu_usage_percent'), raw.get('cpu_usage'))
    if cpu_usage_percent not in (None, ''):
        snapshots.append({
            'metric': 'cpu_usage',
            'value': _number_or_zero(_first_non_empty(raw.get('cpu_used_mhz'), raw.get('CpuUsedMhz'))),
            'unit': 'MHz',
            'usage_percent': cpu_usage_percent,
            'source': 'vsphere_host',
        })
    memory_usage_percent = _first_non_empty(raw.get('memory_usage_percent'), raw.get('memory_usage'))
    if memory_usage_percent not in (None, ''):
        snapshots.append({
            'metric': 'memory_usage',
            'value': _number_or_zero(_first_non_empty(raw.get('memory_used_gb'), raw.get('MemoryUsedGB'))),
            'unit': 'GB',
            'usage_percent': memory_usage_percent,
            'source': 'vsphere_host',
        })
    return snapshots


def _vsphere_host_item(raw, config):
    host_unique_id = _vsphere_host_unique_id(raw)
    management_ip = _first_valid_ip(raw.get('management_ip'), raw.get('ip_address'), raw.get('private_ip'), raw.get('name'))
    datacenter = _first_non_empty(raw.get('datacenter'), raw.get('Datacenter'), raw.get('idc'))
    serial_number = _first_non_empty(raw.get('serial_number'), raw.get('asset_sn'), raw.get('service_tag'), host_unique_id)
    memory_gb = _first_non_empty(raw.get('memory_gb'), round(_bytes_to_gb(raw.get('memory_bytes')), 2) if raw.get('memory_bytes') else '')
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'vsphere_vm',
        unique_id=host_unique_id,
        name=_first_non_empty(raw.get('name'), raw.get('host_name'), raw.get('Host'), host_unique_id),
        region=_first_non_empty(datacenter, raw.get('source_region')),
    )
    payload.update({
        'ci_type_name': '物理机',
        'ci_type_code': config.get('host_ci_type_code') or 'IDC_SERVER',
        'status': 'active' if _vsphere_host_lifecycle_status(raw) in {'running', 'maintenance'} else 'offline',
        'attributes': {
            'asset_sn': serial_number,
            'private_ip': management_ip,
            'ip_address': management_ip,
            'idc': datacenter,
            'host_name': _first_non_empty(raw.get('host_name'), raw.get('name'), raw.get('Host')),
            'hostname': _first_non_empty(raw.get('host_name'), raw.get('name'), raw.get('Host')),
            'datacenter': datacenter,
            'cluster': _first_non_empty(raw.get('cluster'), raw.get('Cluster')),
            'vendor': _first_non_empty(raw.get('vendor'), raw.get('Vendor')),
            'model': _first_non_empty(raw.get('model'), raw.get('Model')),
            'serial_number': serial_number,
            'cpu': _first_non_empty(raw.get('cpu'), raw.get('cpu_cores'), raw.get('num_cpu_cores'), raw.get('NumCpuCores')),
            'memory_gb': memory_gb,
            'disk_gb': _first_non_empty(raw.get('disk_gb'), raw.get('storage_gb')),
            'cpu_mhz': _first_non_empty(raw.get('cpu_mhz'), raw.get('CpuMhz')),
            'cpu_total_mhz': _first_non_empty(raw.get('cpu_total_mhz'), raw.get('CpuTotalMhz')),
            'cpu_used_mhz': _first_non_empty(raw.get('cpu_used_mhz'), raw.get('CpuUsedMhz')),
            'cpu_usage_percent': _first_non_empty(raw.get('cpu_usage_percent'), raw.get('cpu_usage')),
            'memory_used_gb': _first_non_empty(raw.get('memory_used_gb'), raw.get('MemoryUsedGB')),
            'memory_usage_percent': _first_non_empty(raw.get('memory_usage_percent'), raw.get('memory_usage')),
            'cpu_thread_count': _first_non_empty(raw.get('cpu_thread_count'), raw.get('num_cpu_threads')),
            'cpu_package_count': _first_non_empty(raw.get('cpu_package_count'), raw.get('num_cpu_packages')),
            'connection_state': _first_non_empty(raw.get('connection_state'), raw.get('ConnectionState')),
            'power_state': _first_non_empty(raw.get('power_state'), raw.get('PowerState')),
            'maintenance_mode': raw.get('maintenance_mode'),
            'lifecycle_status': _vsphere_host_lifecycle_status(raw),
            'esxi_version': _first_non_empty(raw.get('esxi_version'), raw.get('version'), raw.get('Version')),
            'esxi_build': _first_non_empty(raw.get('esxi_build'), raw.get('build'), raw.get('Build')),
            'cloud_provider': 'vSphere',
            'source_kind': 'vsphere_host',
        },
    })
    metrics = _vsphere_host_metric_snapshots(raw)
    if metrics:
        payload['_metric_snapshots'] = metrics
    return payload


def _huaweicloud_ecs_flavor_id(raw):
    flavor = raw.get('flavor') if isinstance(raw.get('flavor'), dict) else {}
    return _first_non_empty(
        raw.get('flavor_id'),
        raw.get('flavor_ref'),
        raw.get('instance_type'),
        flavor.get('id'),
        flavor.get('name'),
        raw.get('flavor') if not isinstance(raw.get('flavor'), dict) else '',
    )


def _huaweicloud_sdk_request(request_cls, **kwargs):
    try:
        return request_cls(**kwargs)
    except TypeError:
        request = request_cls()
        for key, value in kwargs.items():
            setattr(request, key, value)
        return request


def _fetch_huaweicloud_ecs_flavors(client, ecs_module):
    candidates = [
        ('ListFlavorsRequest', 'list_flavors'),
        ('NovaListFlavorsDetailsRequest', 'nova_list_flavors_details'),
        ('NovaListFlavorsRequest', 'nova_list_flavors'),
    ]
    for request_name, method_name in candidates:
        request_cls = getattr(ecs_module, request_name, None)
        method = getattr(client, method_name, None)
        if not request_cls or not method:
            continue
        try:
            request = _huaweicloud_sdk_request(request_cls, limit=1000)
            payload = _sdk_response_dict(method(request))
        except TypeError:
            request = _huaweicloud_sdk_request(request_cls)
            payload = _sdk_response_dict(method(request))
        except Exception:
            continue
        rows = _first_list_by_paths(payload, ['flavors', 'body.flavors']) if payload else []
        flavors = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            flavor_id = _first_non_empty(row.get('id'), row.get('name'))
            if flavor_id:
                flavors[str(flavor_id)] = row
        if flavors:
            return flavors
    return {}


def _huaweicloud_ecs_volume_size_gb(value):
    if not isinstance(value, dict):
        return 0
    size = _first_non_empty(
        value.get('size'),
        value.get('Size'),
        value.get('volume_size'),
        value.get('volumeSize'),
        value.get('volume_size_gb'),
        value.get('disk_size'),
        value.get('disk_size_gb'),
    )
    return _number_or_zero(size)


def _huaweicloud_ecs_disk_gb(raw, flavor=None):
    flavor = flavor if isinstance(flavor, dict) else {}
    direct = _first_non_empty(raw.get('disk_gb'), raw.get('disk'), raw.get('disk_size_gb'), raw.get('root_disk_gb'))
    if direct:
        return direct
    total = 0
    volume_candidates = [
        raw.get('root_volume'),
        raw.get('RootVolume'),
        raw.get('data_volumes'),
        raw.get('dataVolumes'),
        raw.get('volumes_attached'),
        raw.get('os-extended-volumes:volumes_attached'),
        raw.get('_volume_attachments'),
    ]
    for candidate in volume_candidates:
        if isinstance(candidate, dict):
            total += _huaweicloud_ecs_volume_size_gb(candidate)
        else:
            for item in _as_list(candidate):
                total += _huaweicloud_ecs_volume_size_gb(item)
    if total:
        return round(total, 2)
    extra_specs = flavor.get('extra_specs') if isinstance(flavor.get('extra_specs'), dict) else {}
    return _first_non_empty(
        flavor.get('disk'),
        flavor.get('root_gb'),
        flavor.get('OS-FLV-EXT-DATA:ephemeral'),
        extra_specs.get('quota:local_disk'),
    )


def _attach_huaweicloud_ecs_volume_details(client, ecs_module, items):
    request_cls = getattr(ecs_module, 'ListServerBlockDevicesRequest', None)
    method = getattr(client, 'list_server_block_devices', None)
    if not request_cls or not method:
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        instance_id = str(_first_non_empty(item.get('id'), item.get('server_id'), item.get('InstanceId'), item.get('source_unique_id')) or '').strip()
        if not instance_id:
            continue
        try:
            request = _huaweicloud_sdk_request(request_cls, server_id=instance_id)
            payload = _sdk_response_dict(method(request))
            attachments = _first_list_by_paths(
                payload,
                ['volumeAttachments', 'volume_attachments', 'block_device_mapping', 'body.volumeAttachments'],
            ) if payload else []
            if attachments:
                item['_volume_attachments'] = attachments
        except Exception as exc:
            item['_spec_collection_error'] = str(exc)


def _attach_huaweicloud_ecs_specs(client, ecs_module, items):
    flavor_map = _fetch_huaweicloud_ecs_flavors(client, ecs_module)
    for item in items:
        if not isinstance(item, dict):
            continue
        flavor = item.get('flavor') if isinstance(item.get('flavor'), dict) else {}
        flavor_id = str(_huaweicloud_ecs_flavor_id(item) or '').strip()
        detail = flavor_map.get(flavor_id) or {}
        if detail:
            item['flavor'] = {**detail, **flavor}
    _attach_huaweicloud_ecs_volume_details(client, ecs_module, items)


def _huaweicloud_ecs_item(raw, config):
    instance_id = _first_non_empty(raw.get('id'), raw.get('server_id'), raw.get('InstanceId'), raw.get('source_unique_id'))
    addresses = raw.get('addresses') or raw.get('Addresses') or {}
    address_values = []
    if isinstance(addresses, dict):
        for items in addresses.values():
            address_values.extend(_as_list(items))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'huaweicloud_ecs',
        unique_id=instance_id,
        name=_first_non_empty(raw.get('name'), raw.get('server_name'), raw.get('InstanceName'), instance_id),
        region=_first_non_empty(raw.get('region'), raw.get('RegionId'), raw.get('availability_zone')),
    )
    flavor = raw.get('flavor') if isinstance(raw.get('flavor'), dict) else {}
    memory_gb = _first_non_empty(
        raw.get('memory_gb'),
        raw.get('memory'),
        _memory_gb_from_mb(_first_non_empty(flavor.get('ram'), flavor.get('memory_mb'), raw.get('memory_mb'))),
    )
    payload.update({
        'ci_type_name': '云主机(ECS)',
        'ci_type_code': config.get('target_ci_type_code') or 'CLOUD_SERVER',
        'attributes': {
            'instance_id': instance_id,
            'private_ip': _first_valid_ip(raw.get('private_ip'), address_values),
            'public_ip': _first_valid_ip(raw.get('public_ip'), raw.get('floating_ip')),
            'instance_type': _first_non_empty(flavor.get('id'), flavor.get('name'), raw.get('flavor')),
            'cpu': _first_non_empty(raw.get('cpu'), raw.get('vcpus'), flavor.get('vcpus'), flavor.get('cpu')),
            'memory_gb': memory_gb,
            'disk_gb': _huaweicloud_ecs_disk_gb(raw, flavor),
            'zone_id': _first_non_empty(raw.get('availability_zone'), raw.get('zone_id')),
            'vpc_id': _first_non_empty(raw.get('vpc_id'), raw.get('VpcId')),
            'subnet_id': _first_non_empty(raw.get('subnet_id'), raw.get('subnet')),
            'os_type': _first_non_empty(raw.get('os_type'), raw.get('OS-EXT-SRV-ATTR:os_type')),
            'instance_status': _cloud_instance_status(_first_non_empty(raw.get('status'), raw.get('InstanceStatus'))),
            'cloud_provider': 'Huawei Cloud',
            'metric_collection_status': raw.get('_metric_collection_status') or '',
            'metric_collection_source': raw.get('_metric_collection_source') or '',
            'metric_collection_error': raw.get('_metric_collection_error') or '',
            'metric_datasource': raw.get('_metric_datasource') or '',
            'metric_collected_at': raw.get('_metric_collected_at') or '',
            'prometheus_target': raw.get('_prometheus_target') or '',
            'spec_collection_error': raw.get('_spec_collection_error') or '',
        },
    })
    metrics = raw.get('_metric_snapshots') if isinstance(raw.get('_metric_snapshots'), list) else []
    if metrics:
        payload['_metric_snapshots'] = metrics
    return payload


def _huaweicloud_rds_item(raw, config):
    instance_id = _first_non_empty(raw.get('id'), raw.get('instance_id'), raw.get('DBInstanceId'), raw.get('source_unique_id'))
    datastore = raw.get('datastore') if isinstance(raw.get('datastore'), dict) else {}
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'huaweicloud_rds',
        unique_id=instance_id,
        name=_first_non_empty(raw.get('name'), raw.get('instance_name'), instance_id),
        region=_first_non_empty(raw.get('region'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': 'MySQL',
        'ci_type_code': config.get('target_ci_type_code') or 'MYSQL',
        'attributes': {
            'instance_id': instance_id,
            'endpoint': _first_non_empty(raw.get('private_dns_names'), raw.get('private_ip'), raw.get('endpoint')),
            'port': _first_non_empty(raw.get('port'), raw.get('Port')),
            'engine': _first_non_empty(datastore.get('type'), raw.get('engine')) or 'MySQL',
            'version': _first_non_empty(datastore.get('version'), raw.get('engine_version')),
            'instance_class': _first_non_empty(raw.get('flavor_ref'), raw.get('instance_class')),
            'storage_gb': _first_non_empty(raw.get('volume_size'), raw.get('storage_gb')),
            'vpc_id': _first_non_empty(raw.get('vpc_id'), raw.get('VpcId')),
            'subnet_id': _first_non_empty(raw.get('subnet_id'), raw.get('subnet')),
            'instance_status': _first_non_empty(raw.get('status'), raw.get('DBInstanceStatus')),
            'cloud_provider': 'Huawei Cloud',
        },
    })
    return payload


def _huaweicloud_redis_item(raw, config):
    instance_id = _first_non_empty(raw.get('id'), raw.get('instance_id'), raw.get('source_unique_id'))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'huaweicloud_redis',
        unique_id=instance_id,
        name=_first_non_empty(raw.get('name'), raw.get('instance_name'), instance_id),
        region=_first_non_empty(raw.get('region'), raw.get('region_id')),
    )
    payload.update({
        'ci_type_name': 'Redis',
        'ci_type_code': config.get('target_ci_type_code') or 'REDIS',
        'attributes': {
            'instance_id': instance_id,
            'endpoint': _first_non_empty(raw.get('domain_name'), raw.get('ip'), raw.get('endpoint')),
            'port': _first_non_empty(raw.get('port'), raw.get('Port')),
            'version': _first_non_empty(raw.get('engine_version'), raw.get('version')),
            'memory_gb': _first_non_empty(raw.get('capacity'), raw.get('memory_gb')),
            'vpc_id': _first_non_empty(raw.get('vpc_id'), raw.get('VpcId')),
            'subnet_id': _first_non_empty(raw.get('subnet_id'), raw.get('subnet')),
            'private_ip': _first_ip(raw.get('ip'), raw.get('private_ip')),
            'instance_status': _first_non_empty(raw.get('status'), raw.get('instance_status')),
            'cloud_provider': 'Huawei Cloud',
        },
    })
    return payload


def _huaweicloud_eip_item(raw, config):
    allocation_id = _first_non_empty(raw.get('id'), raw.get('publicip_id'), raw.get('public_ip_id'), raw.get('allocation_id'), raw.get('source_unique_id'))
    ip_address = _first_non_empty(
        raw.get('public_ip_address'),
        raw.get('publicip_address'),
        raw.get('public_ip'),
        raw.get('ip_address'),
        _nested(raw, 'publicip', 'publicip_address'),
        _nested(raw, 'publicip', 'ip_address'),
    )
    bandwidth = raw.get('bandwidth') if isinstance(raw.get('bandwidth'), dict) else {}
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'huaweicloud_eip',
        unique_id=allocation_id or ip_address,
        name=_first_non_empty(raw.get('alias'), raw.get('name'), raw.get('publicip_address'), ip_address, allocation_id),
        region=_first_non_empty(raw.get('region'), raw.get('region_id'), raw.get('public_border_group')),
    )
    payload.update({
        'ci_type_name': 'Elastic IP',
        'ci_type_code': config.get('target_ci_type_code') or 'ELASTIC_IP',
        'attributes': {
            'allocation_id': allocation_id,
            'ip_address': ip_address,
            'bandwidth': _first_non_empty(raw.get('bandwidth_size'), bandwidth.get('size'), raw.get('bandwidth')),
            'internet_charge_type': _first_non_empty(raw.get('type'), bandwidth.get('share_type'), raw.get('bandwidth_share_type'), raw.get('internet_charge_type'), raw.get('ip_version')),
            'attached_to': _first_non_empty(raw.get('port_id'), raw.get('private_ip_address'), raw.get('attached_to')),
            'instance_type': _first_non_empty(raw.get('resource_type'), raw.get('instance_type')),
            'created_at': _first_non_empty(raw.get('create_time'), raw.get('created_at')),
            'instance_status': _first_non_empty(raw.get('status'), raw.get('Status')),
            'public_border_group': _first_non_empty(raw.get('public_border_group'), raw.get('publicBorderGroup')),
        },
    })
    return payload


def _huaweicloud_obs_item(raw, config):
    bucket = _first_non_empty(raw.get('name'), raw.get('bucket'), raw.get('bucket_name'), raw.get('bucketName'), raw.get('Name'), raw.get('source_unique_id'))
    region = _first_non_empty(raw.get('location'), raw.get('region'), raw.get('region_id'), raw.get('Location'))
    endpoint = _url_with_scheme(_first_non_empty(raw.get('endpoint'), raw.get('Endpoint'), region and f'obs.{region}.myhuaweicloud.com'))
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'huaweicloud_obs',
        unique_id=bucket,
        name=bucket,
        region=region,
    )
    payload.update({
        'ci_type_name': '对象存储',
        'ci_type_code': config.get('target_ci_type_code') or 'OBJECT_STORAGE',
        'attributes': {
            'bucket': bucket,
            'endpoint': endpoint,
            'storage_gb': _first_non_empty(raw.get('storage_gb'), raw.get('size')),
            'storage_class': _first_non_empty(raw.get('storage_class'), raw.get('cluster_type')),
            'created_at': _first_non_empty(raw.get('creation_date'), raw.get('creationDate'), raw.get('created_at'), raw.get('CreationDate')),
            'region': region,
            'instance_status': _first_non_empty(raw.get('status'), raw.get('instance_status')) or 'Available',
        },
    })
    return payload


HUAWEICLOUD_ECS_USAGE_METRICS = [
    ('cpu_util', 'cpu_usage'),
    ('mem_util', 'memory_usage'),
    ('disk_util_inband', 'disk_usage'),
]


def _fetch_huaweicloud_ecs_usage_metrics(config, client, instance_ids):
    if not instance_ids:
        return {}, {}
    ces_module = _optional_import('huaweicloudsdkces.v1', 'huaweicloudsdkces')
    limit_minutes = int(_config_value(config, 'metric_window_minutes', 'ecs_metric_window_minutes') or 30)
    period = int(_config_value(config, 'metric_period', 'ecs_metric_period') or 300)
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=limit_minutes)
    from_timestamp = int(start.timestamp() * 1000)
    to_timestamp = int(now.timestamp() * 1000)
    metrics_by_instance = {str(instance_id): [] for instance_id in instance_ids if str(instance_id).strip()}
    errors_by_instance = {str(instance_id): [] for instance_id in instance_ids if str(instance_id).strip()}
    for instance_id in list(metrics_by_instance):
        for metric_name, local_metric in HUAWEICLOUD_ECS_USAGE_METRICS:
            request = ces_module.ShowMetricDataRequest(
                namespace='SYS.ECS',
                metric_name=metric_name,
                dim_0=f'instance_id,{instance_id}',
                filter='average',
                period=period,
                _from=from_timestamp,
                to=to_timestamp,
            )
            try:
                response = client.show_metric_data(request)
                payload = _sdk_response_dict(response)
                usage = None
                latest_timestamp = ''
                for point in _metric_datapoints(payload):
                    if not isinstance(point, dict):
                        continue
                    point_usage = _metric_point_usage(point)
                    if point_usage is None:
                        continue
                    timestamp = _metric_point_timestamp(point)
                    if usage is None or timestamp >= latest_timestamp:
                        usage = point_usage
                        latest_timestamp = timestamp
                if usage is not None:
                    metrics_by_instance[instance_id].append({
                        'metric': local_metric,
                        'value': round(usage, 2),
                        'unit': '%',
                        'usage_percent': round(usage, 2),
                        'source': 'huaweicloud_ces',
                    })
                else:
                    errors_by_instance[instance_id].append(f'{metric_name} no data')
            except Exception as exc:
                errors_by_instance[instance_id].append(f'{metric_name} {exc}')
    return metrics_by_instance, errors_by_instance


def _attach_huaweicloud_ecs_usage_metrics(config, client, items):
    instance_ids = [
        str(_first_non_empty(item.get('id'), item.get('server_id'), item.get('InstanceId'), item.get('source_unique_id')))
        for item in items
        if isinstance(item, dict)
    ]
    instance_ids = [item for item in instance_ids if item]
    if not instance_ids:
        return items
    try:
        metrics_by_instance, errors_by_instance = _fetch_huaweicloud_ecs_usage_metrics(config, client, instance_ids)
    except Exception as exc:
        for item in items:
            if not isinstance(item, dict):
                continue
            instance_id = str(_first_non_empty(item.get('id'), item.get('server_id'), item.get('InstanceId'), item.get('source_unique_id')))
            item['_metric_collection_status'] = 'failed'
            item['_metric_collection_error'] = str(exc)
        return items
    for item in items:
        if not isinstance(item, dict):
            continue
        instance_id = str(_first_non_empty(item.get('id'), item.get('server_id'), item.get('InstanceId'), item.get('source_unique_id')))
        snapshots = metrics_by_instance.get(instance_id) or []
        errors = errors_by_instance.get(instance_id) or []
        if snapshots:
            item['_metric_snapshots'] = snapshots
        if snapshots and errors:
            item['_metric_collection_status'] = 'partial'
        elif snapshots:
            item['_metric_collection_status'] = 'success'
        elif errors:
            item['_metric_collection_status'] = 'failed'
        else:
            item['_metric_collection_status'] = 'no_data'
        if errors:
            item['_metric_collection_error'] = '; '.join(errors)
    return items


def _vsphere_capacity_summary_item(raw, config):
    source_account = _first_non_empty(
        raw.get('source_account'),
        config.get('source_account'),
        config.get('account_name'),
        config.get('account'),
        config.get('host'),
    )
    endpoint = _first_non_empty(raw.get('endpoint'), config.get('host'), config.get('server'), config.get('vcenter_host'))
    source_unique_id = _first_non_empty(raw.get('source_unique_id'), f'vsphere-summary:{source_account or endpoint}')
    metrics = raw.get('metrics') if isinstance(raw.get('metrics'), list) else []
    attributes = {
        'resource_kind': 'vsphere_capacity_summary',
        'cloud_provider': 'vSphere',
        'endpoint': endpoint,
        'host_count': raw.get('host_count'),
        'cluster_count': raw.get('cluster_count'),
        'datastore_count': raw.get('datastore_count'),
        'vm_count': raw.get('vm_count'),
        'cpu_total_mhz': raw.get('cpu_total_mhz'),
        'cpu_used_mhz': raw.get('cpu_used_mhz'),
        'cpu_allocated_vcpu': raw.get('cpu_allocated_vcpu'),
        'cpu_usage': raw.get('cpu_usage'),
        'memory_total_gb': raw.get('memory_total_gb'),
        'memory_used_gb': raw.get('memory_used_gb'),
        'memory_allocated_gb': raw.get('memory_allocated_gb'),
        'memory_usage': raw.get('memory_usage'),
        'storage_total_gb': raw.get('storage_total_gb'),
        'storage_used_gb': raw.get('storage_used_gb'),
        'storage_allocated_gb': raw.get('storage_allocated_gb'),
        'storage_usage': raw.get('storage_usage'),
    }
    payload = _base_payload(
        raw,
        config,
        source_type=config.get('source_type') or 'vsphere_vm',
        unique_id=source_unique_id,
        name=_first_non_empty(raw.get('name'), f'{source_account or endpoint} 资源统计'),
        region='',
    )
    payload['source_region'] = ''
    payload.update({
        'ci_type_name': 'vSphere资源统计',
        'ci_type_code': config.get('summary_ci_type_code') or 'VSPHERE_CAPACITY',
        'attributes': {key: value for key, value in attributes.items() if value not in (None, '')},
        '_metric_snapshots': metrics,
    })
    return payload


VSPHERE_NORMALIZERS = {
    'vm': _vsphere_vm_item,
    'virtual_machine': _vsphere_vm_item,
    'cloud_server': _vsphere_vm_item,
}


HUAWEICLOUD_NORMALIZERS = {
    'ecs': _huaweicloud_ecs_item,
    'cloud_server': _huaweicloud_ecs_item,
    'rds': _huaweicloud_rds_item,
    'mysql': _huaweicloud_rds_item,
    'redis': _huaweicloud_redis_item,
    'eip': _huaweicloud_eip_item,
    'elastic_ip': _huaweicloud_eip_item,
    'obs': _huaweicloud_obs_item,
    'object_storage': _huaweicloud_obs_item,
}


ALIYUN_SDK_REQUESTS = {
    'ecs': {
        'module': 'aliyunsdkecs.request.v20140526.DescribeInstancesRequest',
        'class': 'DescribeInstancesRequest',
        'list_paths': ['Instances.Instance'],
    },
    'rds': {
        'module': 'aliyunsdkrds.request.v20140815.DescribeDBInstancesRequest',
        'class': 'DescribeDBInstancesRequest',
        'list_paths': ['Items.DBInstance'],
    },
    'mysql': {
        'module': 'aliyunsdkrds.request.v20140815.DescribeDBInstancesRequest',
        'class': 'DescribeDBInstancesRequest',
        'list_paths': ['Items.DBInstance'],
    },
    'postgresql': {
        'module': 'aliyunsdkrds.request.v20140815.DescribeDBInstancesRequest',
        'class': 'DescribeDBInstancesRequest',
        'list_paths': ['Items.DBInstance'],
    },
    'postgres': {
        'module': 'aliyunsdkrds.request.v20140815.DescribeDBInstancesRequest',
        'class': 'DescribeDBInstancesRequest',
        'list_paths': ['Items.DBInstance'],
    },
    'elasticsearch': {
        'module': 'aliyunsdkelasticsearch.request.v20170613.ListInstanceRequest',
        'class': 'ListInstanceRequest',
        'list_paths': ['Result'],
        'page_param': 'page',
        'size_param': 'size',
        'max_page_size': 100,
    },
    'es': {
        'module': 'aliyunsdkelasticsearch.request.v20170613.ListInstanceRequest',
        'class': 'ListInstanceRequest',
        'list_paths': ['Result'],
        'page_param': 'page',
        'size_param': 'size',
        'max_page_size': 100,
    },
    'ack': {
        'module': 'aliyunsdkcs.request.v20151215.DescribeClustersV1Request',
        'class': 'DescribeClustersV1Request',
        'list_paths': ['clusters', 'Clusters.Cluster', 'Clusters'],
    },
    'cs': {
        'module': 'aliyunsdkcs.request.v20151215.DescribeClustersV1Request',
        'class': 'DescribeClustersV1Request',
        'list_paths': ['clusters', 'Clusters.Cluster', 'Clusters'],
    },
    'k8s': {
        'module': 'aliyunsdkcs.request.v20151215.DescribeClustersV1Request',
        'class': 'DescribeClustersV1Request',
        'list_paths': ['clusters', 'Clusters.Cluster', 'Clusters'],
    },
    'k8s_cluster': {
        'module': 'aliyunsdkcs.request.v20151215.DescribeClustersV1Request',
        'class': 'DescribeClustersV1Request',
        'list_paths': ['clusters', 'Clusters.Cluster', 'Clusters'],
    },
    'redis': {
        'module': 'aliyunsdkr_kvstore.request.v20150101.DescribeInstancesRequest',
        'class': 'DescribeInstancesRequest',
        'list_paths': ['Instances.KVStoreInstance', 'Instances.Instance'],
    },
    'kvstore': {
        'module': 'aliyunsdkr_kvstore.request.v20150101.DescribeInstancesRequest',
        'class': 'DescribeInstancesRequest',
        'list_paths': ['Instances.KVStoreInstance', 'Instances.Instance'],
    },
    'mongodb': {
        'module': 'aliyunsdkdds.request.v20151201.DescribeDBInstancesRequest',
        'class': 'DescribeDBInstancesRequest',
        'list_paths': ['DBInstances.DBInstance'],
    },
    'mongo': {
        'module': 'aliyunsdkdds.request.v20151201.DescribeDBInstancesRequest',
        'class': 'DescribeDBInstancesRequest',
        'list_paths': ['DBInstances.DBInstance'],
    },
    'kafka': {
        'module': 'aliyunsdkalikafka.request.v20190916.GetInstanceListRequest',
        'class': 'GetInstanceListRequest',
        'list_paths': ['InstanceList.InstanceVO', 'InstanceList'],
    },
    'rocketmq': {
        'module': 'aliyunsdkons.request.v20190214.OnsInstanceInServiceListRequest',
        'class': 'OnsInstanceInServiceListRequest',
        'list_paths': ['Data.InstanceVO', 'Data.Instance', 'Data'],
    },
    'ons': {
        'module': 'aliyunsdkons.request.v20190214.OnsInstanceInServiceListRequest',
        'class': 'OnsInstanceInServiceListRequest',
        'list_paths': ['Data.InstanceVO', 'Data.Instance', 'Data'],
    },
    'slb': {
        'module': 'aliyunsdkslb.request.v20140515.DescribeLoadBalancersRequest',
        'class': 'DescribeLoadBalancersRequest',
        'list_paths': ['LoadBalancers.LoadBalancer'],
    },
    'load_balancer': {
        'module': 'aliyunsdkslb.request.v20140515.DescribeLoadBalancersRequest',
        'class': 'DescribeLoadBalancersRequest',
        'list_paths': ['LoadBalancers.LoadBalancer'],
    },
    'disk': {
        'module': 'aliyunsdkecs.request.v20140526.DescribeDisksRequest',
        'class': 'DescribeDisksRequest',
        'list_paths': ['Disks.Disk'],
        'domain': 'ecs.aliyuncs.com',
        'version': '2014-05-26',
        'action': 'DescribeDisks',
    },
    'disks': {
        'module': 'aliyunsdkecs.request.v20140526.DescribeDisksRequest',
        'class': 'DescribeDisksRequest',
        'list_paths': ['Disks.Disk'],
        'domain': 'ecs.aliyuncs.com',
        'version': '2014-05-26',
        'action': 'DescribeDisks',
    },
    'cloud_disk': {
        'module': 'aliyunsdkecs.request.v20140526.DescribeDisksRequest',
        'class': 'DescribeDisksRequest',
        'list_paths': ['Disks.Disk'],
        'domain': 'ecs.aliyuncs.com',
        'version': '2014-05-26',
        'action': 'DescribeDisks',
    },
    'block_storage': {
        'module': 'aliyunsdkecs.request.v20140526.DescribeDisksRequest',
        'class': 'DescribeDisksRequest',
        'list_paths': ['Disks.Disk'],
        'domain': 'ecs.aliyuncs.com',
        'version': '2014-05-26',
        'action': 'DescribeDisks',
    },
    'nas': {
        'module': 'aliyunsdknas.request.v20170626.DescribeFileSystemsRequest',
        'class': 'DescribeFileSystemsRequest',
        'list_paths': ['FileSystems.FileSystem'],
        'domain': 'nas.aliyuncs.com',
        'version': '2017-06-26',
        'action': 'DescribeFileSystems',
    },
    'nfs': {
        'module': 'aliyunsdknas.request.v20170626.DescribeFileSystemsRequest',
        'class': 'DescribeFileSystemsRequest',
        'list_paths': ['FileSystems.FileSystem'],
        'domain': 'nas.aliyuncs.com',
        'version': '2017-06-26',
        'action': 'DescribeFileSystems',
    },
    'file_storage': {
        'module': 'aliyunsdknas.request.v20170626.DescribeFileSystemsRequest',
        'class': 'DescribeFileSystemsRequest',
        'list_paths': ['FileSystems.FileSystem'],
        'domain': 'nas.aliyuncs.com',
        'version': '2017-06-26',
        'action': 'DescribeFileSystems',
    },
    'clickhouse': {
        'module': 'aliyunsdkclickhouse.request.v20191111.DescribeDBClustersRequest',
        'class': 'DescribeDBClustersRequest',
        'list_paths': ['DBClusters.DBCluster'],
        'domain': 'clickhouse.aliyuncs.com',
        'version': '2019-11-11',
        'action': 'DescribeDBClusters',
    },
    'hologres': {
        'module': 'aliyunsdkhologram.request.v20220601.ListInstancesRequest',
        'class': 'ListInstancesRequest',
        'list_paths': ['body.InstanceList', 'Body.InstanceList', 'InstanceList', 'Instances.Instance', 'Instances', 'Data.Items', 'Data'],
    },
    'maxcompute': {
        'module': 'aliyunsdkmaxcompute.request.v20220104.ListProjectsRequest',
        'class': 'ListProjectsRequest',
        'list_paths': ['data.projects', 'Projects.Project', 'Projects', 'Data.Items', 'Data'],
        'domain': 'maxcompute.aliyuncs.com',
        'version': '2022-01-04',
        'action': 'ListProjects',
    },
    'odps': {
        'module': 'aliyunsdkmaxcompute.request.v20220104.ListProjectsRequest',
        'class': 'ListProjectsRequest',
        'list_paths': ['data.projects', 'Projects.Project', 'Projects', 'Data.Items', 'Data'],
        'domain': 'maxcompute.aliyuncs.com',
        'version': '2022-01-04',
        'action': 'ListProjects',
    },
    'dataworks': {
        'module': 'aliyunsdkdataworks_public.request.v20200518.ListProjectsRequest',
        'class': 'ListProjectsRequest',
        'list_paths': ['PageResult.ProjectList', 'Projects.Project', 'ProjectList.Project', 'Data.Project', 'Data'],
        'domain': 'dataworks-public.aliyuncs.com',
        'version': '2020-05-18',
        'action': 'ListProjects',
    },
    'nat': {
        'module': 'aliyunsdkvpc.request.v20160428.DescribeNatGatewaysRequest',
        'class': 'DescribeNatGatewaysRequest',
        'list_paths': ['NatGateways.NatGateway'],
        'domain': 'vpc.aliyuncs.com',
        'version': '2016-04-28',
        'action': 'DescribeNatGateways',
        'max_page_size': 50,
    },
    'nat_gateway': {
        'module': 'aliyunsdkvpc.request.v20160428.DescribeNatGatewaysRequest',
        'class': 'DescribeNatGatewaysRequest',
        'list_paths': ['NatGateways.NatGateway'],
        'domain': 'vpc.aliyuncs.com',
        'version': '2016-04-28',
        'action': 'DescribeNatGateways',
        'max_page_size': 50,
    },
    'eip': {
        'module': 'aliyunsdkvpc.request.v20160428.DescribeEipAddressesRequest',
        'class': 'DescribeEipAddressesRequest',
        'list_paths': ['EipAddresses.EipAddress'],
        'domain': 'vpc.aliyuncs.com',
        'version': '2016-04-28',
        'action': 'DescribeEipAddresses',
    },
    'elastic_ip': {
        'module': 'aliyunsdkvpc.request.v20160428.DescribeEipAddressesRequest',
        'class': 'DescribeEipAddressesRequest',
        'list_paths': ['EipAddresses.EipAddress'],
        'domain': 'vpc.aliyuncs.com',
        'version': '2016-04-28',
        'action': 'DescribeEipAddresses',
    },
}


ALIYUN_ECS_USAGE_METRICS = [
    ('CPUUtilization', 'cpu_usage', '%'),
    ('memory_usedutilization', 'memory_usage', '%'),
    ('diskusage_utilization', 'disk_usage', '%'),
]


def _set_sdk_param(request, name, value):
    if value in (None, ''):
        return
    setter = getattr(request, f'set_{name}', None)
    if callable(setter):
        setter(value)
        return
    add_query_param = getattr(request, 'add_query_param', None)
    if callable(add_query_param):
        add_query_param(name, value)


def _decode_sdk_response(response):
    if isinstance(response, bytes):
        response = response.decode('utf-8')
    if isinstance(response, str):
        return json.loads(response or '{}')
    return response or {}


def _sdk_response_dict(response):
    if isinstance(response, dict):
        return response
    to_dict = getattr(response, 'to_dict', None)
    if callable(to_dict):
        try:
            payload = to_dict()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            return payload
    to_json_object = getattr(response, 'to_json_object', None)
    if callable(to_json_object):
        try:
            payload = to_json_object()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            return payload
    to_map = getattr(response, 'to_map', None)
    if callable(to_map):
        try:
            payload = to_map()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            return payload
    result = {}
    for key, value in vars(response).items() if hasattr(response, '__dict__') else []:
        if key.startswith('_') or value in (None, ''):
            continue
        result[key] = value
    if result:
        return result
    return {}


def _sdk_plain_item(item):
    if isinstance(item, dict):
        return item
    payload = _sdk_response_dict(item)
    if isinstance(payload, dict) and payload:
        return payload
    return item


def _aliyun_common_request(sdk):
    if not all(sdk.get(key) for key in ('domain', 'version', 'action')):
        return None
    request_module = _optional_import('aliyunsdkcore.request', 'aliyun-python-sdk-core')
    request = request_module.CommonRequest()
    if hasattr(request, 'set_accept_format'):
        request.set_accept_format('json')
    request.set_domain(sdk['domain'])
    request.set_version(sdk['version'])
    request.set_action_name(sdk['action'])
    if sdk.get('uri_pattern') and hasattr(request, 'set_uri_pattern'):
        request.set_uri_pattern(sdk['uri_pattern'])
    if sdk.get('method') and hasattr(request, 'set_method'):
        request.set_method(sdk['method'])
    return request


def _fetch_aliyun_hologres_raw_items(config):
    access_key_id = _config_value(config, 'access_key_id', 'aliyun_access_key_id', 'ak')
    access_key_secret = _config_value(config, 'access_key_secret', 'aliyun_access_key_secret', 'secret_access_key', 'sk')
    region_id = _config_value(config, 'region_id', 'source_region', 'region') or 'cn-hangzhou'
    if not access_key_id or not access_key_secret:
        raise ValueError('阿里云 Hologres 自动采集需要配置 access_key_id 和 access_key_secret')

    client_module = _optional_import('alibabacloud_hologram20220601.client', 'alibabacloud-hologram20220601')
    models_module = _optional_import('alibabacloud_hologram20220601.models', 'alibabacloud-hologram20220601')
    openapi_models = _optional_import('alibabacloud_tea_openapi.models', 'alibabacloud-tea-openapi')
    endpoint = _config_value(config, 'hologres_endpoint', 'endpoint') or f'hologram.{region_id}.aliyuncs.com'
    client = client_module.Client(openapi_models.Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        region_id=region_id,
        endpoint=endpoint,
    ))
    response = client.list_instances(models_module.ListInstancesRequest())
    payload = response.to_map() if hasattr(response, 'to_map') else response
    return [
        item for item in _first_list_by_paths(payload, ALIYUN_SDK_REQUESTS['hologres']['list_paths'])
        if isinstance(item, dict)
    ]


def _fetch_aliyun_elasticsearch_raw_items(config):
    access_key_id = _config_value(config, 'access_key_id', 'aliyun_access_key_id', 'ak')
    access_key_secret = _config_value(config, 'access_key_secret', 'aliyun_access_key_secret', 'secret_access_key', 'sk')
    region_id = _config_value(config, 'region_id', 'source_region', 'region') or 'cn-hangzhou'
    if not access_key_id or not access_key_secret:
        raise ValueError('阿里云 Elasticsearch 自动采集需要配置 access_key_id 和 access_key_secret')

    endpoint = _config_value(config, 'elasticsearch_endpoint', 'es_endpoint', 'endpoint')
    endpoint_host, _ = _normalize_endpoint(endpoint, None)
    if not endpoint_host or 'console.aliyun.com' in endpoint_host:
        endpoint_host = f'elasticsearch.{region_id}.aliyuncs.com'

    client_module = _optional_import('aliyunsdkcore.client', 'aliyun-python-sdk-core')
    client = client_module.AcsClient(access_key_id, access_key_secret, region_id)
    request_module = _optional_import_or_none('aliyunsdkelasticsearch.request.v20170613.ListInstanceRequest')
    request_class = getattr(request_module, 'ListInstanceRequest', None) if request_module else None
    sdk = {
        'domain': endpoint_host,
        'version': '2017-06-13',
        'action': 'ListInstance',
        'method': 'GET',
        'uri_pattern': '/openapi/instances',
    }
    page_size = min(int(_config_value(config, 'page_size', 'collection_page_size') or 100), 100)
    max_pages = int(_config_value(config, 'max_pages', 'collection_max_pages') or 20)
    list_paths = [
        'Result',
        'result',
        'Data.Result',
        'Data.Items',
        'data.result',
        'data.items',
        'PageResult.Result',
        'PageResult.Instance',
        'PageResult.Instances',
        'body.Result',
        'body.result',
        'Body.Result',
        'result.items',
    ]
    items = []
    for page_number in range(1, max_pages + 1):
        request = request_class() if request_class is not None else _aliyun_common_request(sdk)
        if hasattr(request, 'set_accept_format'):
            request.set_accept_format('json')
        if hasattr(request, 'set_endpoint'):
            request.set_endpoint(endpoint_host)
        elif hasattr(request, 'set_domain'):
            request.set_domain(endpoint_host)
        if hasattr(request, 'set_protocol_type'):
            request.set_protocol_type('https')
        if sdk.get('method') and hasattr(request, 'set_method'):
            request.set_method(sdk['method'])
        if sdk.get('uri_pattern') and hasattr(request, 'set_uri_pattern'):
            request.set_uri_pattern(sdk['uri_pattern'])
        _set_sdk_param(request, 'page', page_number)
        _set_sdk_param(request, 'size', page_size)
        for key, value in (config.get('extra_query_params') or {}).items():
            _set_sdk_param(request, key, value)
        payload = _decode_sdk_response(client.do_action_with_exception(request))
        code = str(_first_non_empty(payload.get('Code'), payload.get('code')) or '').strip()
        if code and code not in {'200', 'OK', 'Success'}:
            message = _first_non_empty(payload.get('Message'), payload.get('message'), payload.get('Recommend'))
            raise ValueError(f'阿里云 Elasticsearch 采集失败：{code} {message}'.strip())
        page_items = _first_list_by_paths(payload, list_paths)
        if not page_items:
            break
        items.extend([item for item in page_items if isinstance(item, dict)])
        total = (
            payload.get('TotalCount')
            or payload.get('totalCount')
            or payload.get('total')
            or _path_value(payload, 'PageResult.TotalCount')
            or _path_value(payload, 'PageResult.Total')
            or _path_value(payload, 'Data.TotalCount')
            or _path_value(payload, 'data.totalCount')
            or _path_value(payload, 'data.total')
        )
        if total and len(items) >= int(total):
            break
        if len(page_items) < page_size:
            break
    return items


def _chunks(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def _metric_datapoints(payload):
    data = payload.get('Datapoints') or payload.get('DataPoints') or payload.get('datapoints') or payload.get('data')
    if isinstance(data, str):
        try:
            data = json.loads(data or '[]')
        except (TypeError, ValueError):
            return []
    if isinstance(data, dict):
        for key in ('Datapoint', 'DataPoint', 'items', 'data'):
            if isinstance(data.get(key), list):
                return data.get(key)
        return [data]
    if isinstance(data, list):
        return data
    return []


def _metric_point_instance_id(point):
    dimensions = point.get('dimensions') or point.get('Dimensions') or point.get('dimension')
    if isinstance(dimensions, str):
        try:
            dimensions = json.loads(dimensions or '{}')
        except (TypeError, ValueError):
            dimensions = {}
    if isinstance(dimensions, dict):
        value = _first_non_empty(
            dimensions.get('instanceId'),
            dimensions.get('InstanceId'),
            dimensions.get('instance_id'),
        )
        if value:
            return str(value)
    return str(_first_non_empty(point.get('instanceId'), point.get('InstanceId'), point.get('instance_id')))


def _metric_point_usage(point):
    for key in ('Average', 'Value', 'value', 'Maximum', 'Minimum', 'average', 'maximum'):
        if key not in point or point.get(key) in (None, ''):
            continue
        try:
            usage = float(point.get(key))
        except (TypeError, ValueError):
            continue
        if math.isfinite(usage):
            return max(0, min(100, usage))
    return None


def _metric_point_timestamp(point):
    return str(_first_non_empty(
        point.get('TimeStamp'),
        point.get('Timestamp'),
        point.get('timeStamp'),
        point.get('timestamp'),
        point.get('collect_time'),
    ))


def _fetch_aliyun_ecs_usage_metrics(config, client, instance_ids):
    if not instance_ids:
        return {}
    request_module = _optional_import_or_none('aliyunsdkcms.request.v20190101.DescribeMetricLastRequest')
    if request_module is None:
        return {}
    request_class = getattr(request_module, 'DescribeMetricLastRequest', None)
    if request_class is None:
        return {}
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=int(_config_value(config, 'cms_window_minutes', 'metric_window_minutes') or 30))
    result = {instance_id: [] for instance_id in instance_ids}
    for aliyun_metric, local_metric, unit in ALIYUN_ECS_USAGE_METRICS:
        metric_values = {}
        for batch in _chunks(instance_ids, 50):
            request = request_class()
            if hasattr(request, 'set_accept_format'):
                request.set_accept_format('json')
            _set_sdk_param(request, 'Namespace', 'acs_ecs_dashboard')
            _set_sdk_param(request, 'MetricName', aliyun_metric)
            _set_sdk_param(request, 'Period', str(_config_value(config, 'cms_period', 'metric_period') or 60))
            _set_sdk_param(request, 'StartTime', start.strftime('%Y-%m-%dT%H:%M:%SZ'))
            _set_sdk_param(request, 'EndTime', now.strftime('%Y-%m-%dT%H:%M:%SZ'))
            _set_sdk_param(request, 'Dimensions', json.dumps([{'instanceId': instance_id} for instance_id in batch]))
            payload = _decode_sdk_response(client.do_action_with_exception(request))
            if payload.get('Success') is False or str(payload.get('Code') or '').strip() not in ('', '200', 'OK', 'Success'):
                code = _first_non_empty(payload.get('Code'), payload.get('code'), 'Unknown')
                message = _first_non_empty(payload.get('Message'), payload.get('message'), '未返回错误详情')
                raise ValueError(f'阿里云云监控指标采集失败：{code} {message}')
            for point in _metric_datapoints(payload):
                if not isinstance(point, dict):
                    continue
                instance_id = _metric_point_instance_id(point)
                usage = _metric_point_usage(point)
                if not instance_id or usage is None:
                    continue
                metric_values[instance_id] = max(metric_values.get(instance_id, 0), usage)
        for instance_id, usage in metric_values.items():
            result.setdefault(instance_id, []).append({
                'metric': local_metric,
                'value': round(usage, 2),
                'unit': unit,
                'usage_percent': round(usage, 2),
                'source': 'aliyun_cloudmonitor',
            })
    return {instance_id: rows for instance_id, rows in result.items() if rows}


def _aliyun_ecs_monitor_rows(payload):
    data = payload.get('MonitorData') or payload.get('monitorData') or payload.get('Data') or payload.get('data')
    if isinstance(data, str):
        try:
            data = json.loads(data or '{}')
        except (TypeError, ValueError):
            return []
    if isinstance(data, dict):
        for key in ('InstanceMonitorData', 'MonitorData', 'items', 'data'):
            value = data.get(key)
            if isinstance(value, str):
                try:
                    value = json.loads(value or '[]')
                except (TypeError, ValueError):
                    value = []
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return [value]
        return [data]
    if isinstance(data, list):
        return data
    return []


def _ecs_monitor_cpu_usage(point):
    for key in ('CPU', 'Cpu', 'cpu', 'CPUUtilization', 'cpu_usage'):
        if key not in point or point.get(key) in (None, ''):
            continue
        try:
            usage = float(point.get(key))
        except (TypeError, ValueError):
            continue
        if math.isfinite(usage):
            return max(0, min(100, usage))
    return None


def _fetch_aliyun_ecs_cpu_usage_from_ecs_monitor(config, client, instance_ids):
    if not instance_ids:
        return {}
    request_module = _optional_import_or_none('aliyunsdkecs.request.v20140526.DescribeInstanceMonitorDataRequest')
    if request_module is None:
        return {}
    request_class = getattr(request_module, 'DescribeInstanceMonitorDataRequest', None)
    if request_class is None:
        return {}
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=int(_config_value(config, 'ecs_monitor_window_minutes', 'metric_window_minutes') or 30))
    result = {}
    for instance_id in instance_ids:
        request = request_class()
        if hasattr(request, 'set_accept_format'):
            request.set_accept_format('json')
        _set_sdk_param(request, 'InstanceId', instance_id)
        _set_sdk_param(request, 'Period', int(_config_value(config, 'ecs_monitor_period', 'metric_period') or 60))
        _set_sdk_param(request, 'StartTime', start.strftime('%Y-%m-%dT%H:%M:%SZ'))
        _set_sdk_param(request, 'EndTime', now.strftime('%Y-%m-%dT%H:%M:%SZ'))
        payload = _decode_sdk_response(client.do_action_with_exception(request))
        if payload.get('Code') and str(payload.get('Code')).strip() not in ('200', 'OK', 'Success'):
            message = _first_non_empty(payload.get('Message'), payload.get('message'), '未返回错误详情')
            raise ValueError(f'阿里云 ECS 监控指标采集失败：{payload.get("Code")} {message}')
        selected = None
        for point in _aliyun_ecs_monitor_rows(payload):
            if not isinstance(point, dict):
                continue
            usage = _ecs_monitor_cpu_usage(point)
            if usage is None:
                continue
            timestamp = str(_first_non_empty(point.get('TimeStamp'), point.get('Timestamp'), point.get('timeStamp'), point.get('timestamp')))
            if selected is None or timestamp >= selected[0]:
                selected = (timestamp, usage)
        if selected:
            usage = round(selected[1], 2)
            result[instance_id] = [{
                'metric': 'cpu_usage',
                'value': usage,
                'unit': '%',
                'usage_percent': usage,
                'source': 'aliyun_ecs_monitor',
            }]
    return result


def _attach_aliyun_ecs_usage_metrics(config, client, items):
    instance_ids = [
        str(_first_non_empty(item.get('InstanceId'), item.get('instance_id'), item.get('source_unique_id')))
        for item in items
        if isinstance(item, dict)
    ]
    instance_ids = [item for item in instance_ids if item]
    try:
        metrics_by_instance = _fetch_aliyun_ecs_usage_metrics(config, client, instance_ids)
    except Exception as exc:
        try:
            fallback_metrics = _fetch_aliyun_ecs_cpu_usage_from_ecs_monitor(config, client, instance_ids)
        except Exception as fallback_exc:
            fallback_metrics = {}
            fallback_error = f'；ECS 监控兜底失败：{fallback_exc}'
        else:
            fallback_error = ''
        for item in items:
            if isinstance(item, dict):
                instance_id = str(_first_non_empty(item.get('InstanceId'), item.get('instance_id'), item.get('source_unique_id')))
                snapshots = fallback_metrics.get(instance_id)
                if snapshots:
                    item['_metric_snapshots'] = snapshots
                    item['_metric_collection_status'] = 'partial'
                    item['_metric_collection_error'] = f'{exc}；已通过 ECS 监控接口补采 CPU，内存/磁盘当前用量仍需要云监控权限。'
                else:
                    item['_metric_collection_status'] = 'failed'
                    item['_metric_collection_error'] = f'{exc}{fallback_error}'
        return items
    if not metrics_by_instance:
        try:
            metrics_by_instance = _fetch_aliyun_ecs_cpu_usage_from_ecs_monitor(config, client, instance_ids)
        except Exception:
            metrics_by_instance = {}
        if metrics_by_instance:
            for item in items:
                if not isinstance(item, dict):
                    continue
                instance_id = str(_first_non_empty(item.get('InstanceId'), item.get('instance_id'), item.get('source_unique_id')))
                snapshots = metrics_by_instance.get(instance_id)
                if snapshots:
                    item['_metric_snapshots'] = snapshots
                    item['_metric_collection_status'] = 'partial'
                    item['_metric_collection_error'] = '未从 CloudMonitor 获取到最近指标；已通过 ECS 监控接口补采 CPU，内存/磁盘当前用量仍需要云监控权限。'
                else:
                    item['_metric_collection_status'] = 'no_data'
            return items
    for item in items:
        if not isinstance(item, dict):
            continue
        instance_id = str(_first_non_empty(item.get('InstanceId'), item.get('instance_id'), item.get('source_unique_id')))
        snapshots = metrics_by_instance.get(instance_id)
        if snapshots:
            item['_metric_snapshots'] = snapshots
            item['_metric_collection_status'] = 'success'
        else:
            item['_metric_collection_status'] = 'no_data'
    return items


def _fetch_aliyun_raw_items(config, resource_type):
    if resource_type in {'oss', 'object_storage'}:
        return _fetch_aliyun_oss_raw_items(config)
    if resource_type == 'hologres':
        return _fetch_aliyun_hologres_raw_items(config)
    if resource_type in {'elasticsearch', 'es'}:
        return _fetch_aliyun_elasticsearch_raw_items(config)

    access_key_id = _config_value(config, 'access_key_id', 'aliyun_access_key_id', 'ak')
    access_key_secret = _config_value(config, 'access_key_secret', 'aliyun_access_key_secret', 'secret_access_key', 'sk')
    region_id = _config_value(config, 'region_id', 'source_region', 'region') or 'cn-hangzhou'
    if not access_key_id or not access_key_secret:
        raise ValueError('阿里云自动采集需要配置 access_key_id 和 access_key_secret')

    sdk = ALIYUN_SDK_REQUESTS.get(resource_type)
    if not sdk:
        raise ValueError(f'Unsupported Aliyun resource_type: {resource_type}')
    client_module = _optional_import('aliyunsdkcore.client', 'aliyun-python-sdk-core')
    request_module = _optional_import_or_none(sdk['module'])
    client = client_module.AcsClient(access_key_id, access_key_secret, region_id)
    request_class = getattr(request_module, sdk['class'], None) if request_module else None
    if request_class is None and not all(sdk.get(key) for key in ('domain', 'version', 'action')):
        raise ValueError(f"{sdk['module']} 未安装，无法采集阿里云 {resource_type}；请安装 {sdk['module'].split('.')[0]}")
    page_size = int(_config_value(config, 'page_size', 'collection_page_size') or 100)
    if sdk.get('max_page_size'):
        page_size = min(page_size, int(sdk['max_page_size']))
    max_pages = int(_config_value(config, 'max_pages', 'collection_max_pages') or 20)
    items = []
    for page_number in range(1, max_pages + 1):
        request = request_class() if request_class is not None else _aliyun_common_request(sdk)
        if hasattr(request, 'set_accept_format'):
            request.set_accept_format('json')
        _set_sdk_param(request, 'RegionId', region_id)
        _set_sdk_param(request, sdk.get('size_param') or 'PageSize', page_size)
        _set_sdk_param(request, sdk.get('page_param') or 'PageNumber', page_number)
        for key, value in (config.get('extra_query_params') or {}).items():
            _set_sdk_param(request, key, value)
        payload = _decode_sdk_response(client.do_action_with_exception(request))
        page_items = _first_list_by_paths(payload, sdk['list_paths'])
        if not page_items:
            break
        items.extend([item for item in page_items if isinstance(item, dict)])
        total = (
            payload.get('TotalCount')
            or payload.get('Total')
            or _path_value(payload, 'PageResult.TotalCount')
            or _path_value(payload, 'data.totalCount')
            or _path_value(payload, 'data.total')
        )
        if total and len(items) >= int(total):
            break
        if len(page_items) < page_size:
            break
    if resource_type in {'ecs', 'cloud_server'}:
        _attach_aliyun_ecs_usage_metrics(config, client, items)
    return items


def _fetch_aliyun_oss_raw_items(config):
    access_key_id = _config_value(config, 'access_key_id', 'aliyun_access_key_id', 'ak')
    access_key_secret = _config_value(config, 'access_key_secret', 'aliyun_access_key_secret', 'secret_access_key', 'sk')
    region_id = _config_value(config, 'region_id', 'source_region', 'region') or 'cn-hangzhou'
    if not access_key_id or not access_key_secret:
        raise ValueError('阿里云 OSS 自动采集需要配置 access_key_id 和 access_key_secret')
    oss2 = _optional_import('oss2', 'oss2')
    endpoint = _config_value(config, 'oss_endpoint', 'endpoint') or f'https://oss-{region_id}.aliyuncs.com'
    auth = oss2.Auth(access_key_id, access_key_secret)
    service = oss2.Service(auth, endpoint)
    return [
        {
            'Name': bucket.name,
            'Location': getattr(bucket, 'location', '') or region_id,
            'CreationDate': getattr(bucket, 'creation_date', ''),
            'ExtranetEndpoint': endpoint,
            'StorageClass': getattr(bucket, 'storage_class', ''),
        }
        for bucket in oss2.BucketIterator(service)
    ]


def _round_percent(used, total):
    try:
        used_value = float(used or 0)
        total_value = float(total or 0)
    except (TypeError, ValueError):
        return None
    if total_value <= 0:
        return None
    return round(max(0, min(100, used_value / total_value * 100)), 2)


def _bytes_to_gb(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0
    return number / 1024 / 1024 / 1024


def _number_or_zero(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _vsphere_capacity_summary_raw(
    config,
    *,
    endpoint='',
    hosts=None,
    datastores=None,
    cluster_count=0,
    vm_count=0,
    cpu_allocated_vcpu=0,
    memory_allocated_gb=0,
    storage_allocated_gb=0,
):
    hosts = hosts or []
    datastores = datastores or []
    cpu_total_mhz = 0
    cpu_used_mhz = 0
    memory_total_gb = 0
    memory_used_gb = 0
    connected_hosts = 0
    for host_obj in hosts:
        summary = getattr(host_obj, 'summary', None)
        hardware = getattr(summary, 'hardware', None)
        quick_stats = getattr(summary, 'quickStats', None)
        runtime = getattr(summary, 'runtime', None)
        connection_state = str(getattr(runtime, 'connectionState', '') or '').lower()
        if connection_state and 'disconnected' in connection_state:
            continue
        connected_hosts += 1
        cpu_mhz = float(getattr(hardware, 'cpuMhz', 0) or 0)
        cpu_cores = float(getattr(hardware, 'numCpuCores', 0) or 0)
        cpu_total_mhz += cpu_mhz * cpu_cores
        cpu_used_mhz += float(getattr(quick_stats, 'overallCpuUsage', 0) or 0)
        memory_total_gb += _bytes_to_gb(getattr(hardware, 'memorySize', 0))
        memory_used_gb += float(getattr(quick_stats, 'overallMemoryUsage', 0) or 0) / 1024

    storage_total_gb = 0
    storage_used_gb = 0
    datastore_count = 0
    for datastore in datastores:
        summary = getattr(datastore, 'summary', None)
        if not summary or getattr(summary, 'accessible', True) is False:
            continue
        capacity_gb = _bytes_to_gb(getattr(summary, 'capacity', 0))
        free_gb = _bytes_to_gb(getattr(summary, 'freeSpace', 0))
        if capacity_gb <= 0:
            continue
        datastore_count += 1
        storage_total_gb += capacity_gb
        storage_used_gb += max(0, capacity_gb - free_gb)

    cpu_usage = _round_percent(cpu_used_mhz, cpu_total_mhz)
    memory_usage = _round_percent(memory_used_gb, memory_total_gb)
    storage_usage = _round_percent(storage_used_gb, storage_total_gb)
    source_account = _first_non_empty(
        config.get('source_account'),
        config.get('account_name'),
        config.get('account'),
        config.get('host'),
        endpoint,
    )
    metrics = []
    if cpu_usage is not None:
        metrics.append({'metric': 'cpu_usage', 'value': round(cpu_used_mhz, 2), 'unit': 'MHz', 'usage_percent': cpu_usage, 'source': 'vsphere_summary'})
    if memory_usage is not None:
        metrics.append({'metric': 'memory_usage', 'value': round(memory_used_gb, 2), 'unit': 'GB', 'usage_percent': memory_usage, 'source': 'vsphere_summary'})
    if storage_usage is not None:
        metrics.append({'metric': 'disk_usage', 'value': round(storage_used_gb, 2), 'unit': 'GB', 'usage_percent': storage_usage, 'source': 'vsphere_summary'})
    if not metrics:
        return None
    return {
        '__sxdevops_kind': 'vsphere_capacity_summary',
        'name': f'{source_account} 资源统计',
        'source_account': source_account,
        'source_unique_id': f'vsphere-summary:{source_account}',
        'endpoint': endpoint,
        'host_count': connected_hosts,
        'cluster_count': cluster_count,
        'datastore_count': datastore_count,
        'vm_count': vm_count,
        'cpu_total_mhz': round(cpu_total_mhz, 2),
        'cpu_used_mhz': round(cpu_used_mhz, 2),
        'cpu_allocated_vcpu': round(_number_or_zero(cpu_allocated_vcpu), 2),
        'cpu_usage': cpu_usage,
        'memory_total_gb': round(memory_total_gb, 2),
        'memory_used_gb': round(memory_used_gb, 2),
        'memory_allocated_gb': round(_number_or_zero(memory_allocated_gb), 2),
        'memory_usage': memory_usage,
        'storage_total_gb': round(storage_total_gb, 2),
        'storage_used_gb': round(storage_used_gb, 2),
        'storage_allocated_gb': round(_number_or_zero(storage_allocated_gb), 2),
        'storage_usage': storage_usage,
        'metrics': metrics,
    }


def _vsphere_object_class_name(obj):
    return obj.__class__.__name__ if obj is not None else ''


def _vsphere_is_class(obj, expected_name):
    class_name = _vsphere_object_class_name(obj)
    return class_name == f'vim.{expected_name}' or class_name == expected_name or class_name.endswith(f'.{expected_name}')


def _vsphere_parent_name(obj, expected_name):
    cursor = getattr(obj, 'parent', None)
    while cursor:
        if _vsphere_is_class(cursor, expected_name):
            return getattr(cursor, 'name', '')
        cursor = getattr(cursor, 'parent', None)
    return ''


def _vsphere_host_management_ip(host_obj):
    config = getattr(host_obj, 'config', None)
    network = getattr(config, 'network', None)
    for vnic in getattr(network, 'vnic', []) or []:
        spec = getattr(vnic, 'spec', None)
        ip_config = getattr(spec, 'ip', None)
        ip_address = getattr(ip_config, 'ipAddress', '')
        if _first_valid_ip(ip_address):
            return ip_address
    return _first_valid_ip(getattr(host_obj, 'name', ''))


def _vsphere_host_serial_number(hardware):
    fallback = ''
    for item in getattr(hardware, 'otherIdentifyingInfo', []) or []:
        identifier_type = getattr(item, 'identifierType', None)
        label = ' '.join([
            str(getattr(identifier_type, 'key', '') or ''),
            str(getattr(identifier_type, 'label', '') or ''),
            str(getattr(identifier_type, 'summary', '') or ''),
        ]).lower()
        value = _first_non_empty(getattr(item, 'identifierValue', ''), getattr(item, 'value', ''))
        if value and not fallback:
            fallback = value
        if value and ('serial' in label or 'service' in label):
            return value
    return fallback


def _vsphere_host_raw_item(host_obj):
    summary = getattr(host_obj, 'summary', None)
    hardware = getattr(summary, 'hardware', None)
    quick_stats = getattr(summary, 'quickStats', None)
    runtime = getattr(summary, 'runtime', None)
    config_summary = getattr(summary, 'config', None)
    product = getattr(config_summary, 'product', None)
    cpu_mhz = _number_or_zero(getattr(hardware, 'cpuMhz', 0))
    cpu_cores = _number_or_zero(getattr(hardware, 'numCpuCores', 0))
    cpu_total_mhz = cpu_mhz * cpu_cores
    cpu_used_mhz = _number_or_zero(getattr(quick_stats, 'overallCpuUsage', 0))
    memory_gb = _bytes_to_gb(getattr(hardware, 'memorySize', 0))
    memory_used_gb = _number_or_zero(getattr(quick_stats, 'overallMemoryUsage', 0)) / 1024
    host_id = getattr(host_obj, '_moId', '') or getattr(host_obj, 'name', '')
    return {
        '__sxdevops_kind': 'vsphere_host',
        'host_id': host_id,
        'moid': host_id,
        'name': getattr(host_obj, 'name', ''),
        'host_name': getattr(host_obj, 'name', ''),
        'management_ip': _vsphere_host_management_ip(host_obj),
        'datacenter': _vsphere_parent_name(host_obj, 'Datacenter'),
        'cluster': _vsphere_parent_name(host_obj, 'ClusterComputeResource'),
        'vendor': getattr(hardware, 'vendor', ''),
        'model': getattr(hardware, 'model', ''),
        'serial_number': _vsphere_host_serial_number(hardware),
        'cpu_cores': getattr(hardware, 'numCpuCores', ''),
        'cpu_thread_count': getattr(hardware, 'numCpuThreads', ''),
        'cpu_package_count': getattr(hardware, 'numCpuPkgs', ''),
        'cpu_mhz': getattr(hardware, 'cpuMhz', ''),
        'cpu_total_mhz': round(cpu_total_mhz, 2) if cpu_total_mhz else '',
        'cpu_used_mhz': round(cpu_used_mhz, 2) if cpu_used_mhz else '',
        'cpu_usage_percent': _round_percent(cpu_used_mhz, cpu_total_mhz),
        'memory_bytes': getattr(hardware, 'memorySize', ''),
        'memory_gb': round(memory_gb, 2) if memory_gb else '',
        'memory_used_gb': round(memory_used_gb, 2) if memory_used_gb else '',
        'memory_usage_percent': _round_percent(memory_used_gb, memory_gb),
        'connection_state': str(getattr(runtime, 'connectionState', '') or ''),
        'power_state': str(getattr(runtime, 'powerState', '') or ''),
        'maintenance_mode': bool(getattr(runtime, 'inMaintenanceMode', False)),
        'esxi_version': getattr(product, 'version', ''),
        'esxi_build': getattr(product, 'build', ''),
    }


def _fetch_vsphere_raw_items(config, resource_type):
    if resource_type not in VSPHERE_NORMALIZERS:
        return []
    host, parsed_port = _normalize_endpoint(_config_value(config, 'host', 'server', 'vcenter_host', 'endpoint'), 443)
    username = _config_value(config, 'username', 'user')
    password = _config_value(config, 'password')
    if not host or not username or not password:
        raise ValueError('vSphere 自动采集需要配置 host、username 和 password')

    connect_module = _optional_import('pyVim.connect', 'pyvmomi')
    pyvmomi_module = _optional_import('pyVmomi', 'pyvmomi')
    vim_module = pyvmomi_module.vim
    invalid_login_error = getattr(getattr(vim_module, 'fault', None), 'InvalidLogin', None)
    method_fault_error = getattr(getattr(pyvmomi_module, 'vmodl', None), 'MethodFault', None)
    port = int(_config_value(config, 'port') or parsed_port or 443)
    disable_ssl = config.get('disable_ssl_verification', True) is not False
    ssl_context = ssl._create_unverified_context() if disable_ssl else None
    try:
        service_instance = connect_module.SmartConnect(
            host=host,
            user=username,
            pwd=password,
            port=port,
            sslContext=ssl_context,
        )
    except socket.gaierror as exc:
        raise ValueError(f'无法解析 vSphere 地址「{host}」，请确认后端服务器能访问该地址，或填写可解析的 IP/域名。') from exc
    except Exception as exc:
        if invalid_login_error and isinstance(exc, invalid_login_error):
            raise ValueError(f'vSphere 账号认证失败，请检查用户名、密码和登录域：{_pyvmomi_fault_message(exc)}') from exc
        if method_fault_error and isinstance(exc, method_fault_error):
            raise ValueError(f'vSphere 接口返回错误：{_pyvmomi_fault_message(exc)}') from exc
        if isinstance(exc, (TimeoutError, ConnectionRefusedError, OSError)):
            raise ValueError(f'无法连接 vSphere 地址「{host}:{port}」，请确认后端服务器网络可达且端口开放。') from exc
        raise
    try:
        content = service_instance.RetrieveContent()
        vm_view = content.viewManager.CreateContainerView(content.rootFolder, [vim_module.VirtualMachine], True)
        host_view = content.viewManager.CreateContainerView(content.rootFolder, [vim_module.HostSystem], True)
        datastore_view = content.viewManager.CreateContainerView(content.rootFolder, [vim_module.Datastore], True)
        try:
            items = []
            host_objects = list(host_view.view)
            datastore_objects = list(datastore_view.view)
            cluster_names = set()
            cpu_allocated_vcpu = 0
            memory_allocated_gb = 0
            storage_allocated_gb = 0
            for vm in vm_view.view:
                summary = getattr(vm, 'summary', None)
                config_summary = getattr(summary, 'config', None)
                runtime = getattr(summary, 'runtime', None)
                guest = getattr(summary, 'guest', None)
                storage = getattr(summary, 'storage', None)
                quick_stats = getattr(summary, 'quickStats', None)
                host_obj = getattr(runtime, 'host', None)
                parent = getattr(vm, 'parent', None)
                host_parent = getattr(host_obj, 'parent', None) if host_obj else None
                cluster = ''
                host_parent_class = host_parent.__class__.__name__ if host_parent else ''
                if host_parent_class in ('vim.ClusterComputeResource', 'ClusterComputeResource') or host_parent_class.endswith('.ClusterComputeResource'):
                    cluster = getattr(host_parent, 'name', '')
                    if cluster:
                        cluster_names.add(cluster)
                datacenter = ''
                cursor = parent
                while cursor:
                    if cursor.__class__.__name__ == 'vim.Datacenter':
                        datacenter = getattr(cursor, 'name', '')
                        break
                    cursor = getattr(cursor, 'parent', None)
                committed = getattr(storage, 'committed', 0) or 0
                uncommitted = getattr(storage, 'uncommitted', 0) or 0
                committed_gb = round(committed / 1024 / 1024 / 1024, 2) if committed else ''
                provisioned_gb = round((committed + uncommitted) / 1024 / 1024 / 1024, 2) if committed or uncommitted else ''
                num_cpu = getattr(config_summary, 'numCpu', '')
                memory_mb = getattr(config_summary, 'memorySizeMB', '')
                host_summary = getattr(host_obj, 'summary', None) if host_obj else None
                host_hardware = getattr(host_summary, 'hardware', None)
                cpu_used_mhz = _number_or_zero(getattr(quick_stats, 'overallCpuUsage', 0))
                host_cpu_mhz = _number_or_zero(getattr(host_hardware, 'cpuMhz', 0))
                cpu_total_mhz = _number_or_zero(num_cpu) * host_cpu_mhz
                memory_used_mb = _number_or_zero(
                    _first_non_empty(
                        getattr(quick_stats, 'guestMemoryUsage', None),
                        getattr(quick_stats, 'hostMemoryUsage', None),
                    )
                )
                memory_used_gb = memory_used_mb / 1024 if memory_used_mb else 0
                memory_gb = _number_or_zero(memory_mb) / 1024 if memory_mb else 0
                cpu_usage_percent = _round_percent(cpu_used_mhz, cpu_total_mhz)
                memory_usage_percent = _round_percent(memory_used_gb, memory_gb)
                disk_usage_percent = _round_percent(committed, committed + uncommitted)
                metric_snapshots = []
                if cpu_usage_percent is not None:
                    metric_snapshots.append({'metric': 'cpu_usage', 'value': round(cpu_used_mhz, 2), 'unit': 'MHz', 'usage_percent': cpu_usage_percent, 'source': 'vsphere_vm'})
                if memory_usage_percent is not None:
                    metric_snapshots.append({'metric': 'memory_usage', 'value': round(memory_used_gb, 2), 'unit': 'GB', 'usage_percent': memory_usage_percent, 'source': 'vsphere_vm'})
                if disk_usage_percent is not None:
                    metric_snapshots.append({'metric': 'disk_usage', 'value': committed_gb or 0, 'unit': 'GB', 'usage_percent': disk_usage_percent, 'source': 'vsphere_vm'})
                cpu_allocated_vcpu += _number_or_zero(num_cpu)
                memory_allocated_gb += _number_or_zero(memory_mb) / 1024
                storage_allocated_gb += _number_or_zero(provisioned_gb)
                vm_item = {
                    'vm': getattr(config_summary, 'vmPathName', '') or getattr(vm, '_moId', ''),
                    'name': getattr(config_summary, 'name', '') or getattr(vm, 'name', ''),
                    'power_state': str(getattr(runtime, 'powerState', '')),
                    'guest_ip': getattr(guest, 'ipAddress', ''),
                    'num_cpu': num_cpu,
                    'memory_mb': memory_mb,
                    'provisioned_gb': provisioned_gb,
                    'committed_gb': committed_gb,
                    'cpu_used_mhz': round(cpu_used_mhz, 2) if cpu_used_mhz else '',
                    'cpu_usage_percent': cpu_usage_percent,
                    'memory_used_gb': round(memory_used_gb, 2) if memory_used_gb else '',
                    'memory_usage_percent': memory_usage_percent,
                    'disk_used_gb': committed_gb,
                    'disk_usage_percent': disk_usage_percent,
                    '_metric_collection_status': 'partial' if len(metric_snapshots) and len(metric_snapshots) < 3 else ('ok' if metric_snapshots else 'no_data'),
                    'datacenter': datacenter,
                    'cluster': cluster,
                    'host': getattr(host_obj, 'name', ''),
                    'guest_os': getattr(config_summary, 'guestFullName', ''),
                }
                if metric_snapshots:
                    vm_item['_metric_snapshots'] = metric_snapshots
                items.append(vm_item)
            vm_count = len(items)
            for host_obj in host_objects:
                items.append(_vsphere_host_raw_item(host_obj))
            summary_item = _vsphere_capacity_summary_raw(
                config,
                endpoint=host,
                hosts=host_objects,
                datastores=datastore_objects,
                cluster_count=len(cluster_names),
                vm_count=vm_count,
                cpu_allocated_vcpu=cpu_allocated_vcpu,
                memory_allocated_gb=memory_allocated_gb,
                storage_allocated_gb=storage_allocated_gb,
            )
            if summary_item:
                items.append(summary_item)
            return items
        finally:
            vm_view.Destroy()
            host_view.Destroy()
            datastore_view.Destroy()
    finally:
        connect_module.Disconnect(service_instance)


def _fetch_huaweicloud_raw_items(config, resource_type):
    access_key_id = _config_value(config, 'access_key_id', 'huaweicloud_access_key_id', 'ak')
    secret_key = _config_value(config, 'secret_key', 'access_key_secret', 'huaweicloud_secret_key', 'sk')
    project_id = _config_value(config, 'project_id', 'huaweicloud_project_id')
    region_id = _config_value(config, 'region_id', 'source_region', 'region') or 'cn-north-4'
    if not access_key_id or not secret_key:
        raise ValueError('华为云自动采集需要配置 access_key_id 和 secret_key')
    project_scoped_resource = resource_type not in {'obs', 'object_storage'}
    if project_scoped_resource and not project_id:
        raise ValueError('华为云自动采集该资源需要配置 project_id')

    credentials = None
    if project_scoped_resource:
        credentials_module = _optional_import('huaweicloudsdkcore.auth.credentials', 'huaweicloudsdkcore')
        credentials = credentials_module.BasicCredentials(access_key_id, secret_key, project_id)
    limit = int(_config_value(config, 'page_size', 'collection_page_size') or 100)
    if resource_type in {'ecs', 'cloud_server'}:
        ecs_module = _optional_import('huaweicloudsdkecs.v2', 'huaweicloudsdkecs')
        region_module = _optional_import('huaweicloudsdkecs.v2.region.ecs_region', 'huaweicloudsdkecs')
        client = ecs_module.EcsClient.new_builder().with_credentials(credentials).with_region(
            region_module.EcsRegion.value_of(region_id)
        ).build()
        items = []
        offset = 0
        total = None
        while True:
            response = client.list_servers_details(ecs_module.ListServersDetailsRequest(limit=limit, offset=offset))
            payload = _sdk_response_dict(response)
            page_items = _first_list_by_paths(payload, ['servers']) if payload else []
            items.extend([item for item in page_items if isinstance(item, dict)])
            total = total if total is not None else _first_non_empty(payload.get('count'))
            if total and len(items) >= int(total):
                break
            if len(page_items) < limit:
                break
            offset += limit
        _attach_huaweicloud_ecs_specs(client, ecs_module, items)
        try:
            ces_module = _optional_import('huaweicloudsdkces.v1', 'huaweicloudsdkces')
            ces_region_module = _optional_import('huaweicloudsdkces.v1.region.ces_region', 'huaweicloudsdkces')
            ces_client = ces_module.CesClient.new_builder().with_credentials(credentials).with_region(
                ces_region_module.CesRegion.value_of(region_id)
            ).build()
            _attach_huaweicloud_ecs_usage_metrics(config, ces_client, items)
        except Exception as exc:
            for item in items:
                if not isinstance(item, dict):
                    continue
                item['_metric_collection_status'] = 'failed'
                item['_metric_collection_error'] = str(exc)
        return items
    if resource_type in {'rds', 'mysql'}:
        rds_module = _optional_import('huaweicloudsdkrds.v3', 'huaweicloudsdkrds')
        region_module = _optional_import('huaweicloudsdkrds.v3.region.rds_region', 'huaweicloudsdkrds')
        client = rds_module.RdsClient.new_builder().with_credentials(credentials).with_region(
            region_module.RdsRegion.value_of(region_id)
        ).build()
        response = client.list_instances(rds_module.ListInstancesRequest(limit=limit))
        return _sdk_response_dict(response).get('instances') or []
    if resource_type == 'redis':
        dcs_module = _optional_import('huaweicloudsdkdcs.v2', 'huaweicloudsdkdcs')
        region_module = _optional_import('huaweicloudsdkdcs.v2.region.dcs_region', 'huaweicloudsdkdcs')
        client = dcs_module.DcsClient.new_builder().with_credentials(credentials).with_region(
            region_module.DcsRegion.value_of(region_id)
        ).build()
        response = client.list_instances(dcs_module.ListInstancesRequest(limit=limit))
        return _sdk_response_dict(response).get('instances') or []
    if resource_type in {'eip', 'elastic_ip'}:
        eip_module = _optional_import('huaweicloudsdkeip.v2', 'huaweicloudsdkeip')
        region_module = _optional_import('huaweicloudsdkeip.v2.region.eip_region', 'huaweicloudsdkeip')
        client = eip_module.EipClient.new_builder().with_credentials(credentials).with_region(
            region_module.EipRegion.value_of(region_id)
        ).build()
        items = []
        marker = None
        seen_markers = set()
        while True:
            request = eip_module.ListPublicipsRequest(limit=limit, marker=marker)
            response = client.list_publicips(request)
            payload = _sdk_response_dict(response)
            page_items = _first_list_by_paths(payload, [
                'publicips',
                'public_ips',
                'body.publicips',
                'body.public_ips',
                'result.publicips',
                'Publicips',
            ]) if payload else []
            page_items = [_sdk_plain_item(item) for item in page_items]
            page_items = [item for item in page_items if isinstance(item, dict)]
            items.extend(page_items)
            if len(page_items) < limit:
                break
            marker = _first_non_empty(page_items[-1].get('id'), page_items[-1].get('public_ip_address'))
            if not marker or marker in seen_markers:
                break
            seen_markers.add(marker)
        return items
    if resource_type in {'obs', 'object_storage'}:
        obs_module = _optional_import('huaweicloudsdkobs.v1', 'huaweicloudsdkobs')
        obs_auth_module = _optional_import('huaweicloudsdkobs.v1.obs_credentials', 'huaweicloudsdkobs')
        obs_endpoint = _url_with_scheme(_config_value(config, 'obs_endpoint', 'endpoint') or f'obs.{region_id}.myhuaweicloud.com')
        obs_client = obs_module.ObsClient.new_builder().with_credentials(
            obs_auth_module.ObsCredentials(access_key_id, secret_key)
        ).with_endpoint(obs_endpoint).build()
        response = obs_client.list_buckets(obs_module.ListBucketsRequest())
        payload = _sdk_response_dict(response)
        buckets = _first_list_by_paths(payload, [
            'buckets.bucket',
            'buckets',
            'body.buckets.bucket',
            'body.buckets',
            'body.Buckets.Bucket',
            'Buckets.Bucket',
            'Buckets',
        ]) if payload else []
        buckets = [_sdk_plain_item(item) for item in buckets]
        return [item for item in buckets if isinstance(item, dict)]
    return []


def _should_fetch_provider_items(config, connector):
    if config.get('collection_enabled') is True:
        return True
    if connector == 'aliyun':
        return _has_any_config(config, 'access_key_id', 'aliyun_access_key_id', 'ak')
    if connector == 'vsphere':
        return _has_any_config(config, 'host', 'server', 'vcenter_host', 'endpoint')
    if connector in {'huaweicloud', 'huawei_cloud'}:
        return _has_any_config(config, 'access_key_id', 'huaweicloud_access_key_id', 'ak')
    return False


def _fetch_provider_raw_items(config, connector, resource_type):
    if _config_value(config, 'demo_mode') is True or str(_config_value(config, 'auth_mode')).lower() == 'demo':
        raise ValueError(DEMO_MODE_DISABLED_MESSAGE)
    if not _should_fetch_provider_items(config, connector):
        return []
    if connector == 'aliyun':
        return _fetch_aliyun_raw_items(config, resource_type)
    if connector == 'vsphere':
        return _fetch_vsphere_raw_items(config, resource_type)
    if connector in {'huaweicloud', 'huawei_cloud'}:
        return _fetch_huaweicloud_raw_items(config, resource_type)
    return []


def _demo_provider_raw_items(config, connector, resource_type):
    region = _config_value(config, 'region_id', 'source_region', 'region') or 'cn-hangzhou'
    account = _config_value(config, 'source_account', 'account_name', 'account_id') or 'demo-account'
    zone = f'{region}-a'
    if connector == 'aliyun':
        prefix = str(account).replace(' ', '-').lower()
        rows = {
            'ecs': [
                {
                    'InstanceId': f'i-{prefix}-app-01',
                    'InstanceName': f'{prefix}-app-01',
                    'RegionId': region,
                    'ZoneId': zone,
                    'Status': 'Running',
                    'InstanceType': 'ecs.g7.large',
                    'Cpu': 4,
                    'Memory': 8192,
                    'VpcAttributes': {'VpcId': 'vpc-demo', 'VSwitchId': 'vsw-demo', 'PrivateIpAddress': {'IpAddress': ['10.10.11.10']}},
                    'PublicIpAddress': {'IpAddress': ['47.96.10.10']},
                    'Tags': {'Tag': [{'TagKey': 'environment', 'TagValue': 'prod'}, {'TagKey': 'owner', 'TagValue': 'sre'}]},
                    '_metric_snapshots': [
                        {'metric': 'cpu_usage', 'value': 38, 'unit': '%', 'usage_percent': 38, 'source': 'aliyun_cloudmonitor'},
                        {'metric': 'memory_usage', 'value': 62, 'unit': '%', 'usage_percent': 62, 'source': 'aliyun_cloudmonitor'},
                        {'metric': 'disk_usage', 'value': 54, 'unit': '%', 'usage_percent': 54, 'source': 'aliyun_cloudmonitor'},
                    ],
                }
            ],
            'rds': [
                {
                    'DBInstanceId': f'rm-{prefix}-mysql',
                    'DBInstanceDescription': f'{prefix}-mysql',
                    'RegionId': region,
                    'ZoneId': zone,
                    'DBInstanceStatus': 'Running',
                    'Engine': 'MySQL',
                    'EngineVersion': '8.0',
                    'DBInstanceClass': 'mysql.n2.medium.2c',
                    'DBInstanceStorage': 500,
                    'ConnectionString': f'{prefix}-mysql.mysql.aliyuncs.com',
                    'Port': '3306',
                    'VpcId': 'vpc-demo',
                    'VSwitchId': 'vsw-demo',
                }
            ],
            'ack': [
                {
                    'cluster_id': f'c-{prefix}-ack',
                    'name': f'{prefix}-ack',
                    'region_id': region,
                    'state': 'running',
                    'cluster_type': 'ManagedKubernetes',
                    'current_version': '1.30.1-aliyun.1',
                    'node_count': 6,
                    'api_server': f'https://{prefix}-ack.{region}.cs.aliyuncs.com',
                    'vpc_id': 'vpc-demo',
                    'vswitch_ids': ['vsw-demo'],
                    'security_group_id': 'sg-demo',
                }
            ],
            'redis': [
                {
                    'InstanceId': f'r-{prefix}-redis',
                    'InstanceName': f'{prefix}-redis',
                    'RegionId': region,
                    'ZoneId': zone,
                    'InstanceStatus': 'Normal',
                    'EngineVersion': '7.0',
                    'Capacity': 8,
                    'ConnectionDomain': f'{prefix}-redis.redis.aliyuncs.com',
                    'Port': '6379',
                    'VpcId': 'vpc-demo',
                    'VSwitchId': 'vsw-demo',
                }
            ],
            'disk': [
                {
                    'DiskId': f'd-{prefix}-system',
                    'DiskName': f'{prefix}-system-disk',
                    'RegionId': region,
                    'ZoneId': zone,
                    'Status': 'In_use',
                    'Category': 'cloud_essd',
                    'Size': 120,
                    'PerformanceLevel': 'PL1',
                    'InstanceId': f'i-{prefix}-app-01',
                    'DiskChargeType': 'PostPaid',
                }
            ],
            'nas': [
                {
                    'FileSystemId': f'nas-{prefix}',
                    'Description': f'{prefix}-shared-nas',
                    'RegionId': region,
                    'Status': 'Running',
                    'ProtocolType': 'NFS',
                    'StorageType': 'Capacity',
                    'CapacityGB': 10240,
                    'MeteredSize': 3200,
                    'MountTargetDomain': f'{prefix}.nas.aliyuncs.com',
                    'VpcId': 'vpc-demo',
                }
            ],
            'clickhouse': [
                {
                    'DBClusterId': f'cc-{prefix}',
                    'DBClusterDescription': f'{prefix}-clickhouse',
                    'RegionId': region,
                    'DBClusterStatus': 'Running',
                    'EngineVersion': '23.8',
                    'ConnectionString': f'{prefix}-clickhouse.clickhouse.aliyuncs.com',
                    'ShardCount': 2,
                    'ReplicaCount': 2,
                    'StorageSize': 800,
                    'VpcId': 'vpc-demo',
                }
            ],
            'hologres': [
                {
                    'InstanceId': f'hg-{prefix}',
                    'InstanceName': f'{prefix}-hologres',
                    'RegionId': region,
                    'Status': 'Running',
                    'Endpoint': f'{prefix}-hologres.hologres.aliyuncs.com',
                    'Version': '3.0',
                    'Cpu': 32,
                    'StorageGB': 1024,
                    'VpcId': 'vpc-demo',
                }
            ],
            'maxcompute': [
                {
                    'ProjectName': f'{prefix}_maxcompute',
                    'RegionId': region,
                    'Status': 'Available',
                    'QuotaName': 'pay-as-you-go',
                    'StorageGB': 4096,
                    'TableCount': 240,
                    'JobCount': 32,
                }
            ],
            'dataworks': [
                {
                    'ProjectId': f'dw-{prefix}',
                    'ProjectName': f'{prefix}-dataworks',
                    'RegionId': region,
                    'Status': 'Available',
                    'ProjectMode': 'standard',
                    'NodeCount': 120,
                    'WorkflowCount': 18,
                }
            ],
            'mongodb': [
                {
                    'DBInstanceId': f'mg-{prefix}-mongodb',
                    'DBInstanceDescription': f'{prefix}-mongodb',
                    'RegionId': region,
                    'ZoneId': zone,
                    'DBInstanceStatus': 'Running',
                    'Engine': 'MongoDB',
                    'DBInstanceVersion': '6.0',
                    'DBInstanceClass': 'dds.mongo.mid',
                    'DBInstanceStorage': 200,
                    'ConnectionString': f'{prefix}-mongodb.mongodb.aliyuncs.com',
                    'Port': '3717',
                    'VpcId': 'vpc-demo',
                    'VSwitchId': 'vsw-demo',
                }
            ],
            'nat_gateway': [
                {
                    'NatGatewayId': f'ngw-{prefix}',
                    'Name': f'{prefix}-nat',
                    'RegionId': region,
                    'Status': 'Available',
                    'NatType': 'Enhanced',
                    'Spec': 'Small',
                    'VpcId': 'vpc-demo',
                    'VSwitchId': 'vsw-demo',
                    'IpLists': {'IpList': [{'IpAddress': '47.96.30.30'}]},
                }
            ],
            'eip': [
                {
                    'AllocationId': f'eip-{prefix}',
                    'IpAddress': '47.96.30.30',
                    'RegionId': region,
                    'Status': 'InUse',
                    'Bandwidth': 100,
                    'InternetChargeType': 'PayByTraffic',
                    'InstanceId': f'ngw-{prefix}',
                    'InstanceType': 'Nat',
                }
            ],
            'kafka': [
                {
                    'InstanceId': f'alikafka-{prefix}',
                    'Name': f'{prefix}-kafka',
                    'RegionId': region,
                    'ZoneId': zone,
                    'Status': 'Running',
                    'Version': '2.6',
                    'SpecType': 'professional',
                    'TopicNum': 12,
                    'PartitionNum': 36,
                    'DiskSize': 300,
                    'Endpoint': f'{prefix}-kafka:9092',
                    'VpcId': 'vpc-demo',
                    'VSwitchId': 'vsw-demo',
                }
            ],
            'rocketmq': [
                {
                    'InstanceId': f'rmq-{prefix}',
                    'InstanceName': f'{prefix}-rocketmq',
                    'RegionId': region,
                    'ZoneId': zone,
                    'Status': 'Running',
                    'Version': '5.0',
                    'InstanceType': 'professional',
                    'TopicCount': 10,
                    'GroupCount': 4,
                    'NameSrvEndpoint': f'{prefix}-rocketmq:9876',
                    'VpcId': 'vpc-demo',
                    'VSwitchId': 'vsw-demo',
                }
            ],
            'oss': [
                {
                    'Name': f'{prefix}-artifacts',
                    'Location': region,
                    'Status': 'Available',
                    'StorageClass': 'Standard',
                    'StorageGB': 800,
                    'ExtranetEndpoint': f'oss-{region}.aliyuncs.com',
                }
            ],
            'slb': [
                {
                    'LoadBalancerId': f'lb-{prefix}',
                    'LoadBalancerName': f'{prefix}-ingress',
                    'RegionId': region,
                    'MasterZoneId': zone,
                    'LoadBalancerStatus': 'active',
                    'Address': '47.96.20.20',
                    'AddressType': 'internet',
                    'LoadBalancerSpec': 'slb.s2.small',
                    'Bandwidth': 20,
                    'VpcId': 'vpc-demo',
                    'VSwitchId': 'vsw-demo',
                }
            ],
            'elasticsearch': [
                {
                    'instanceId': f'es-{prefix}',
                    'description': f'{prefix}-search',
                    'regionId': region,
                    'status': 'active',
                    'esVersion': '8.11',
                    'nodeAmount': 3,
                    'nodeSpec': {'amount': 3, 'disk': 120},
                    'endpoint': f'{prefix}-search.es.aliyuncs.com',
                    'vpcId': 'vpc-demo',
                    'index_count': 12,
                }
            ],
        }
        aliases = {
            'cs': 'ack',
            'k8s': 'ack',
            'k8s_cluster': 'ack',
            'disks': 'disk',
            'cloud_disk': 'disk',
            'block_storage': 'disk',
            'nfs': 'nas',
            'file_storage': 'nas',
            'odps': 'maxcompute',
            'nat': 'nat_gateway',
            'elastic_ip': 'eip',
            'es': 'elasticsearch',
        }
        resource_type = aliases.get(resource_type, resource_type)
        return rows.get(resource_type, [])
    if connector in {'huaweicloud', 'huawei_cloud'}:
        if resource_type in {'ecs', 'cloud_server'}:
            return [{'id': 'hw-demo-ecs-01', 'name': f'{account}-ecs-01', 'region': region, 'status': 'ACTIVE', 'flavor': {'id': 's6.large.2'}, 'addresses': {'private': [{'addr': '10.30.11.10'}]}, 'metadata': {}}]
        if resource_type in {'rds', 'mysql'}:
            return [{'id': 'hw-demo-rds-01', 'name': f'{account}-mysql', 'region': region, 'status': 'ACTIVE', 'datastore': {'type': 'MySQL', 'version': '8.0'}, 'volume_size': 300, 'port': '3306'}]
        if resource_type == 'redis':
            return [{'id': 'hw-demo-redis-01', 'name': f'{account}-redis', 'region': region, 'status': 'RUNNING', 'engine_version': '7.0', 'capacity': 8, 'port': '6379', 'ip': '10.30.2.30'}]
        if resource_type in {'eip', 'elastic_ip'}:
            return [{'id': 'hw-eip-demo-01', 'public_ip_address': '121.36.10.9', 'region': region, 'status': 'ACTIVE', 'bandwidth_size': 100, 'type': '5_bgp', 'port_id': 'hw-demo-port-01'}]
        if resource_type in {'obs', 'object_storage'}:
            return [{'name': f'{account}-obs', 'location': region, 'status': 'Available', 'creation_date': '2026-01-01T00:00:00Z', 'storage_gb': 512, 'endpoint': f'obs.{region}.myhuaweicloud.com'}]
    return []


def _configured_raw_items(config, request_data=None):
    request_data = request_data or {}
    for key in ('raw_items', 'fixture_items', 'provider_items'):
        value = request_data.get(key)
        if isinstance(value, list):
            return value
    for key in ('raw_items', 'fixture_items', 'provider_items'):
        value = (config or {}).get(key)
        if isinstance(value, list):
            return value
    return []


def collect_items_for_sync_job(job, request_data=None):
    request_data = request_data or {}
    request_items = request_data.get('items')
    if request_items is not None:
        if not isinstance(request_items, list):
            raise ValueError('items 必须是数组')
        return [_apply_field_mapping(item, item, job.config or {}) for item in request_items if isinstance(item, dict)]

    config = _runtime_collection_config(job.config or {}, request_data)
    configured_items = config.get('items')
    if isinstance(configured_items, list) and configured_items:
        return [_apply_field_mapping(item, item, config) for item in configured_items if isinstance(item, dict)]

    connector = str(config.get('connector') or '').strip().lower()
    resource_type = str(config.get('resource_type') or '').strip().lower()
    raw_items = _configured_raw_items(config, request_data)
    if not raw_items:
        raw_items = _fetch_provider_raw_items(config, connector, resource_type)
    if connector == 'aliyun' and resource_type in ALIYUN_NORMALIZERS and raw_items:
        if resource_type in {'ecs', 'cloud_server'}:
            raw_items = enrich_cloud_vm_metrics(raw_items, config, 'aliyun_cloudmonitor')
        normalizer = ALIYUN_NORMALIZERS[resource_type]
        return [
            _apply_field_mapping(normalizer(raw, {**config, 'source_type': job.source_type}), raw, config)
            for raw in raw_items
            if isinstance(raw, dict)
        ]
    if connector == 'vsphere' and resource_type in VSPHERE_NORMALIZERS and raw_items:
        if resource_type in {'vm', 'virtual_machine', 'cloud_server'}:
            raw_items = enrich_vsphere_vm_metrics(raw_items, config)
        normalizer = VSPHERE_NORMALIZERS[resource_type]
        items = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            if raw.get('__sxdevops_kind') == 'vsphere_capacity_summary':
                items.append(_vsphere_capacity_summary_item(raw, {**config, 'source_type': job.source_type}))
            elif raw.get('__sxdevops_kind') == 'vsphere_host':
                items.append(_apply_field_mapping(_vsphere_host_item(raw, {**config, 'source_type': job.source_type}), raw, config))
            else:
                items.append(_apply_field_mapping(normalizer(raw, {**config, 'source_type': job.source_type}), raw, config))
        return items
    if connector in {'huaweicloud', 'huawei_cloud'} and resource_type in HUAWEICLOUD_NORMALIZERS and raw_items:
        if resource_type in {'ecs', 'cloud_server'}:
            raw_items = enrich_cloud_vm_metrics(raw_items, config, 'huaweicloud_cloudmonitor')
        normalizer = HUAWEICLOUD_NORMALIZERS[resource_type]
        return [
            _apply_field_mapping(normalizer(raw, {**config, 'source_type': job.source_type}), raw, config)
            for raw in raw_items
            if isinstance(raw, dict)
        ]

    if raw_items and _field_mapping_entries(config):
        mapped_items = []
        base_config = {**config, 'source_type': job.source_type}
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            base_payload = _base_payload(
                raw,
                base_config,
                source_type=job.source_type or config.get('source_type') or 'manual',
                unique_id=_first_non_empty(raw.get('source_unique_id'), raw.get('id'), raw.get('ID'), raw.get('Id')),
                name=_first_non_empty(raw.get('name'), raw.get('Name'), raw.get('resource_name')),
                region=_first_non_empty(raw.get('source_region'), raw.get('region'), raw.get('RegionId')),
            )
            base_payload['ci_type_code'] = config.get('target_ci_type_code') or raw.get('ci_type_code') or raw.get('resource_type') or ''
            base_payload['ci_type_name'] = config.get('target_ci_type_name') or raw.get('ci_type_name') or ''
            base_payload['attributes'] = {}
            mapped_items.append(_apply_field_mapping(base_payload, raw, config))
        return mapped_items

    if configured_items is None:
        return []
    if not isinstance(configured_items, list):
        raise ValueError('items 必须是数组')
    return configured_items


def configured_collection_item_count(job):
    config = job.config or {}
    items = config.get('items') if isinstance(config.get('items'), list) else []
    if items:
        return len(items)
    return len(_configured_raw_items(config))
