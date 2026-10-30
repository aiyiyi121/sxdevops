import importlib
import importlib.util
import json
import socket
import ssl
import time
from datetime import date
from decimal import Decimal
from urllib.parse import urlparse


class CloudAdapterError(RuntimeError):
    pass


def _normalize_endpoint(value, default_port=443):
    text = str(value or '').strip()
    if not text:
        return '', default_port
    if '://' in text:
        parsed = urlparse(text)
    else:
        parsed = urlparse(f'//{text.split("/", 1)[0]}')
    host = (parsed.hostname or text.split('/', 1)[0]).strip().strip('[]')
    return host, parsed.port or default_port


def _pyvmomi_fault_message(exc):
    return (getattr(exc, 'msg', '') or str(exc) or exc.__class__.__name__).strip()


def _has_module(module_name):
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_decimal(value, default='0'):
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _object_value(obj, *names, default=''):
    if obj is None:
        return default
    for name in names:
        if isinstance(obj, dict):
            value = obj.get(name)
        else:
            value = getattr(obj, name, None)
        if value not in (None, ''):
            return value
    return default


def _tag_map(pairs):
    rows = {}
    for item in pairs or []:
        key = item.get('Key') or item.get('key')
        value = item.get('Value') or item.get('value')
        if key:
            rows[key] = value
    return rows


class BaseCloudAdapter:
    provider = ''
    provider_label = ''
    required_modules = ()
    supports_inventory = False
    supports_costs = False
    supports_provisioning = False

    def __init__(self, credential):
        self.credential = credential

    @classmethod
    def dependency_status(cls):
        modules = {module: _has_module(module) for module in cls.required_modules}
        installed = all(modules.values()) if modules else False
        return {
            'provider': cls.provider,
            'provider_label': cls.provider_label or cls.provider,
            'installed': installed,
            'required_modules': list(cls.required_modules),
            'modules': modules,
            'supports_inventory': cls.supports_inventory,
            'supports_costs': cls.supports_costs,
            'supports_provisioning': cls.supports_provisioning,
        }

    def capability(self):
        return self.dependency_status()

    def default_region(self, fallback=''):
        return self.credential.default_region or fallback

    def unavailable_error(self):
        required = ', '.join(self.required_modules) or 'provider sdk'
        raise CloudAdapterError(f'{self.provider_label} SDK is unavailable. Install: {required}')

    def asset(self, environment, name, resource_type, resource_id, **kwargs):
        return {
            'name': name,
            'provider': environment.credential.provider,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'region': kwargs.get('region') or environment.region or self.default_region(),
            'zone': kwargs.get('zone') or environment.zone or '',
            'status': kwargs.get('status', 'running'),
            'charge_type': kwargs.get('charge_type', 'on_demand'),
            'private_ip': kwargs.get('private_ip', ''),
            'public_ip': kwargs.get('public_ip', ''),
            'vpc_name': kwargs.get('vpc_name') or environment.vpc_name or '',
            'spec': kwargs.get('spec', ''),
            'cpu': _safe_int(kwargs.get('cpu', 0)),
            'memory_gb': _safe_decimal(kwargs.get('memory_gb', '0')),
            'disk_gb': _safe_decimal(kwargs.get('disk_gb', '0')),
            'monthly_cost': _safe_decimal(kwargs.get('monthly_cost', '0')),
            'risk_level': kwargs.get('risk_level', 'normal'),
            'sync_state': kwargs.get('sync_state', 'synced'),
            'tags': kwargs.get('tags') or {},
            'metadata': kwargs.get('metadata') or {},
        }

    def test_connection(self):
        self.unavailable_error()

    def fetch_inventory(self, environment):
        self.unavailable_error()

    def fetch_cost_series(self, months=6):
        return None

    def provision_instances(self, request_id, specs, names):
        raise CloudAdapterError(f'{self.provider_label} does not support instance provisioning.')


class AwsCloudAdapter(BaseCloudAdapter):
    provider = 'aws'
    provider_label = 'AWS'
    required_modules = ('boto3',)
    supports_inventory = True
    supports_costs = True

    def _session(self):
        if not self.capability()['installed']:
            self.unavailable_error()
        boto3 = importlib.import_module('boto3')
        session_kwargs = {}
        if self.credential.access_key_id:
            session_kwargs['aws_access_key_id'] = self.credential.access_key_id
        if self.credential.access_key_secret:
            session_kwargs['aws_secret_access_key'] = self.credential.access_key_secret
        region_name = self.default_region('ap-southeast-1')
        base_session = boto3.session.Session(region_name=region_name, **session_kwargs)
        if not self.credential.role_arn:
            return base_session
        params = {'RoleArn': self.credential.role_arn, 'RoleSessionName': f'sxdevops-{self.credential.id}'}
        if self.credential.external_id:
            params['ExternalId'] = self.credential.external_id
        creds = base_session.client('sts', region_name=region_name).assume_role(**params)['Credentials']
        return boto3.session.Session(
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
            region_name=region_name,
        )

    def test_connection(self):
        session = self._session()
        region = self.default_region('ap-southeast-1')
        identity = session.client('sts', region_name=region).get_caller_identity()
        return {
            'success': True,
            'status': 'healthy',
            'message': f'AWS STS connectivity verified for account {identity.get("Account", "-")}.',
            'region': region,
            'demo_mode': False,
            'sdk_mode': 'aws-boto3',
            'account': identity.get('Account', ''),
            'arn': identity.get('Arn', ''),
        }

    def fetch_inventory(self, environment):
        session = self._session()
        region = environment.region or self.default_region('ap-southeast-1')
        assets = []
        ec2 = session.client('ec2', region_name=region)
        for reservation in ec2.describe_instances().get('Reservations', []):
            for instance in reservation.get('Instances', []):
                tags = _tag_map(instance.get('Tags'))
                name = tags.get('Name') or instance.get('InstanceId')
                assets.append(self.asset(environment, name, 'ecs', instance.get('InstanceId'), region=region, zone=instance.get('Placement', {}).get('AvailabilityZone', ''), status='running' if instance.get('State', {}).get('Name') == 'running' else 'stopped', charge_type=instance.get('InstanceLifecycle') or 'on_demand', private_ip=instance.get('PrivateIpAddress', ''), public_ip=instance.get('PublicIpAddress', ''), vpc_name=instance.get('VpcId', ''), spec=instance.get('InstanceType', ''), tags=tags))
        return assets

    def fetch_cost_series(self, months=6):
        session = self._session()
        client = session.client('ce', region_name='us-east-1')
        end = date.today().replace(day=1)
        start_year = end.year
        start_month = end.month - (months - 1)
        while start_month <= 0:
            start_year -= 1
            start_month += 12
        start = date(start_year, start_month, 1)
        response = client.get_cost_and_usage(TimePeriod={'Start': start.isoformat(), 'End': end.isoformat()}, Granularity='MONTHLY', Metrics=['UnblendedCost'])
        labels, values = [], []
        for row in response.get('ResultsByTime', []):
            labels.append(row.get('TimePeriod', {}).get('Start', '')[:7])
            values.append(float(row.get('Total', {}).get('UnblendedCost', {}).get('Amount', '0')))
        return {'labels': labels, 'values': values, 'unit': 'USD'}


class AliyunCloudAdapter(BaseCloudAdapter):
    provider = 'aliyun'
    provider_label = 'Aliyun'
    required_modules = ('aliyunsdkcore', 'aliyunsdkecs')
    supports_inventory = True
    supports_provisioning = True

    def _client(self, region=''):
        if not self.capability()['installed']:
            self.unavailable_error()
        client_module = importlib.import_module('aliyunsdkcore.client')
        return client_module.AcsClient(self.credential.access_key_id, self.credential.access_key_secret, region or self.default_region('cn-hangzhou'))

    def test_connection(self):
        request_module = importlib.import_module('aliyunsdkecs.request.v20140526.DescribeRegionsRequest')
        request = request_module.DescribeRegionsRequest()
        request.set_accept_format('json')
        response = json.loads(self._client().do_action_with_exception(request))
        count = len((response.get('Regions') or {}).get('Region', []))
        return {
            'success': True,
            'status': 'healthy',
            'message': f'Aliyun ECS connectivity verified, {count} regions visible.',
            'region': self.default_region('cn-hangzhou'),
            'demo_mode': False,
            'sdk_mode': 'aliyun-python-sdk',
            'count': count,
        }

    def fetch_inventory(self, environment):
        request_module = importlib.import_module('aliyunsdkecs.request.v20140526.DescribeInstancesRequest')
        request = request_module.DescribeInstancesRequest()
        request.set_accept_format('json')
        response = json.loads(self._client(environment.region or self.default_region('cn-hangzhou')).do_action_with_exception(request))
        assets = []
        for row in ((response.get('Instances') or {}).get('Instance') or []):
            tags = {}
            for tag in (((row.get('Tags') or {}).get('Tag') or [])):
                if tag.get('TagKey'):
                    tags[tag['TagKey']] = tag.get('TagValue', '')
            private_ips = ((row.get('VpcAttributes') or {}).get('PrivateIpAddress') or {}).get('IpAddress') or []
            public_ips = ((row.get('PublicIpAddress') or {}).get('IpAddress') or [])
            assets.append(self.asset(environment, row.get('InstanceName') or row.get('InstanceId'), 'ecs', row.get('InstanceId'), region=row.get('RegionId') or environment.region, zone=row.get('ZoneId', ''), status='running' if row.get('Status') == 'Running' else 'stopped', charge_type=row.get('InstanceChargeType', ''), private_ip=private_ips[0] if private_ips else '', public_ip=public_ips[0] if public_ips else '', vpc_name=(row.get('VpcAttributes') or {}).get('VpcId', ''), spec=row.get('InstanceType', ''), cpu=row.get('Cpu', 0), memory_gb=row.get('Memory', 0), tags=tags))
        return assets

    def provision_instances(self, request_id, specs, names):
        request_module = importlib.import_module('aliyunsdkecs.request.v20140526.RunInstancesRequest')
        describe_module = importlib.import_module('aliyunsdkecs.request.v20140526.DescribeInstancesRequest')
        region = specs.get('region') or self.default_region('cn-hangzhou')
        client = self._client(region)
        instance_ids = []
        for index, name in enumerate(names, start=1):
            request = request_module.RunInstancesRequest()
            request.set_accept_format('json')
            request.set_ImageId(specs['image_id'])
            request.set_InstanceType(specs['instance_type'])
            request.set_SecurityGroupId(specs['security_group_id'])
            request.set_VSwitchId(specs['vswitch_id'])
            request.set_InstanceName(name)
            request.set_HostName(name)
            request.set_Amount(1)
            request.set_InstanceChargeType(specs.get('instance_charge_type') or 'PostPaid')
            request.set_SystemDiskCategory(specs.get('system_disk_category') or 'cloud_essd')
            request.set_SystemDiskSize(int(specs.get('system_disk_size') or 40))
            request.set_ClientToken(f'sxdevops-request-{request_id}-{index}')
            if specs.get('zone'):
                request.set_ZoneId(specs['zone'])
            if specs.get('key_pair_name'):
                request.set_KeyPairName(specs['key_pair_name'])
            request.add_query_param('Tag.1.Key', 'sxdevops-request-id')
            request.add_query_param('Tag.1.Value', str(request_id))
            response = json.loads(client.do_action_with_exception(request))
            created_ids = ((response.get('InstanceIdSets') or {}).get('InstanceIdSet') or [])
            if not created_ids:
                raise CloudAdapterError(f'阿里云未返回实例 ID，主机 {name} 创建结果无法确认。')
            instance_ids.extend(created_ids)

        describe_request = describe_module.DescribeInstancesRequest()
        describe_request.set_accept_format('json')
        describe_request.set_InstanceIds(json.dumps(instance_ids))
        response = json.loads(client.do_action_with_exception(describe_request))
        rows = ((response.get('Instances') or {}).get('Instance') or [])
        row_by_id = {row.get('InstanceId'): row for row in rows}
        resources = []
        for name, instance_id in zip(names, instance_ids):
            row = row_by_id.get(instance_id) or {}
            private_ips = ((row.get('VpcAttributes') or {}).get('PrivateIpAddress') or {}).get('IpAddress') or []
            public_ips = ((row.get('PublicIpAddress') or {}).get('IpAddress') or [])
            resources.append({
                'provider': self.provider,
                'instance_id': instance_id,
                'hostname': row.get('InstanceName') or name,
                'private_ip': private_ips[0] if private_ips else '',
                'public_ip': public_ips[0] if public_ips else '',
                'region': row.get('RegionId') or region,
                'zone': row.get('ZoneId') or specs.get('zone') or '',
                'instance_type': row.get('InstanceType') or specs['instance_type'],
                'status': row.get('Status') or 'Pending',
            })
        return resources


class TencentCloudAdapter(BaseCloudAdapter):
    provider = 'tencent'
    provider_label = 'Tencent Cloud'
    required_modules = ('tencentcloud',)
    supports_inventory = True

    def test_connection(self):
        if not self.capability()['installed']:
            self.unavailable_error()
        credential_module = importlib.import_module('tencentcloud.common.credential')
        profile_module = importlib.import_module('tencentcloud.common.profile.client_profile')
        http_module = importlib.import_module('tencentcloud.common.profile.http_profile')
        client_module = importlib.import_module('tencentcloud.sts.v20180813.sts_client')
        models_module = importlib.import_module('tencentcloud.sts.v20180813.models')
        cred = credential_module.Credential(self.credential.access_key_id, self.credential.access_key_secret)
        http_profile = http_module.HttpProfile()
        http_profile.endpoint = 'sts.tencentcloudapi.com'
        client_profile = profile_module.ClientProfile()
        client_profile.httpProfile = http_profile
        client = client_module.StsClient(cred, self.default_region('ap-guangzhou'), client_profile)
        payload = json.loads(client.GetCallerIdentity(models_module.GetCallerIdentityRequest()).to_json_string())
        return {
            'success': True,
            'status': 'healthy',
            'message': f'TencentCloud STS connectivity verified for UIN {payload.get("UserId", "-")}.',
            'region': self.default_region('ap-guangzhou'),
            'demo_mode': False,
            'sdk_mode': 'tencentcloud-sdk-python',
            'account': payload.get('AccountId', ''),
        }

    def fetch_inventory(self, environment):
        if not self.capability()['installed']:
            self.unavailable_error()
        credential_module = importlib.import_module('tencentcloud.common.credential')
        profile_module = importlib.import_module('tencentcloud.common.profile.client_profile')
        http_module = importlib.import_module('tencentcloud.common.profile.http_profile')
        client_module = importlib.import_module('tencentcloud.cvm.v20170312.cvm_client')
        models_module = importlib.import_module('tencentcloud.cvm.v20170312.models')
        cred = credential_module.Credential(self.credential.access_key_id, self.credential.access_key_secret)
        http_profile = http_module.HttpProfile()
        http_profile.endpoint = 'cvm.tencentcloudapi.com'
        client_profile = profile_module.ClientProfile()
        client_profile.httpProfile = http_profile
        client = client_module.CvmClient(cred, environment.region or self.default_region('ap-guangzhou'), client_profile)
        payload = json.loads(client.DescribeInstances(models_module.DescribeInstancesRequest()).to_json_string())
        assets = []
        for row in payload.get('InstanceSet', []):
            private_ips = row.get('PrivateIpAddresses') or []
            public_ips = row.get('PublicIpAddresses') or []
            assets.append(self.asset(environment, row.get('InstanceName') or row.get('InstanceId'), 'ecs', row.get('InstanceId'), region=environment.region or self.default_region('ap-guangzhou'), zone=row.get('Placement', {}).get('Zone', ''), status='running' if row.get('InstanceState') == 'RUNNING' else 'stopped', charge_type=row.get('InstanceChargeType', ''), private_ip=private_ips[0] if private_ips else '', public_ip=public_ips[0] if public_ips else '', vpc_name=row.get('VirtualPrivateCloud', {}).get('VpcId', ''), spec=row.get('InstanceType', '')))
        return assets


class HuaweiCloudAdapter(BaseCloudAdapter):
    provider = 'huawei'
    provider_label = 'Huawei Cloud'
    required_modules = ('huaweicloudsdkcore', 'huaweicloudsdkecs')
    supports_inventory = True
    supports_provisioning = True

    def _client(self, region=''):
        if not self.capability()['installed']:
            self.unavailable_error()
        if not self.credential.project_id:
            raise CloudAdapterError('Huawei Cloud requires project_id for AK/SK API access.')
        credentials_module = importlib.import_module('huaweicloudsdkcore.auth.credentials')
        ecs_module = importlib.import_module('huaweicloudsdkecs.v2')
        region_module = importlib.import_module('huaweicloudsdkecs.v2.region.ecs_region')
        credentials = credentials_module.BasicCredentials(self.credential.access_key_id, self.credential.access_key_secret, self.credential.project_id)
        return ecs_module.EcsClient.new_builder().with_credentials(credentials).with_region(region_module.EcsRegion.value_of(region or self.default_region('cn-north-4'))).build()

    def test_connection(self):
        ecs_module = importlib.import_module('huaweicloudsdkecs.v2')
        response = self._client().list_servers_details(ecs_module.ListServersDetailsRequest())
        count = len(getattr(response, 'servers', []) or [])
        return {
            'success': True,
            'status': 'healthy',
            'message': f'Huawei Cloud ECS connectivity verified, {count} servers visible.',
            'region': self.default_region('cn-north-4'),
            'demo_mode': False,
            'sdk_mode': 'huaweicloud-python-sdk',
            'count': count,
        }

    @classmethod
    def server_specs(cls, row):
        flavor = _object_value(row, 'flavor', default={}) or {}
        cpu = _safe_int(_object_value(flavor, 'vcpus', 'cpu', 'cores', default=0))
        memory_gb = _safe_decimal(_object_value(flavor, 'memory_gb', 'ram_gb', default='0'))
        if not memory_gb:
            ram_mb = _safe_decimal(_object_value(flavor, 'ram', 'memory', 'memory_mb', default='0'))
            memory_gb = ram_mb / Decimal('1024') if ram_mb else Decimal('0')

        disk_gb = _safe_decimal(_object_value(flavor, 'disk_gb', 'disk', 'root_gb', 'root_disk_gb', default='0'))
        volumes = (
            _object_value(row, 'os_extended_volumes_volumes_attached', default=None)
            or _object_value(row, 'os-extended-volumes:volumes_attached', default=None)
            or _object_value(row, 'volumes_attached', default=[])
            or []
        )
        attached_disk_gb = Decimal('0')
        for volume in volumes:
            attached_disk_gb += _safe_decimal(_object_value(volume, 'size', 'volume_size', 'disk_size', default='0'))
        if attached_disk_gb:
            disk_gb = attached_disk_gb
        return {
            'spec': _object_value(flavor, 'id', 'name', default='') or '',
            'cpu': cpu,
            'memory_gb': memory_gb,
            'disk_gb': disk_gb,
        }

    def fetch_inventory(self, environment):
        ecs_module = importlib.import_module('huaweicloudsdkecs.v2')
        response = self._client(environment.region or self.default_region('cn-north-4')).list_servers_details(ecs_module.ListServersDetailsRequest())
        assets = []
        for row in getattr(response, 'servers', []) or []:
            private_ip = ''
            public_ip = ''
            for address_list in (_object_value(row, 'addresses', default={}) or {}).values():
                for address in address_list or []:
                    addr = _object_value(address, 'addr', default='') or ''
                    ip_type = _object_value(address, 'os_ext_ip_stype', 'OS-EXT-IPS:type', default='') or ''
                    if ip_type == 'floating' and not public_ip:
                        public_ip = addr
                    elif not private_ip:
                        private_ip = addr
            tags = {}
            row_tags = _object_value(row, 'tags', default=[]) or []
            if isinstance(row_tags, dict):
                tags.update(row_tags)
            for tag in row_tags if isinstance(row_tags, list) else []:
                if isinstance(tag, str) and '=' in tag:
                    key, value = tag.split('=', 1)
                    tags[key] = value
            specs = self.server_specs(row)
            assets.append(self.asset(environment, _object_value(row, 'name', default='') or _object_value(row, 'id', default=''), 'ecs', _object_value(row, 'id', default=''), region=environment.region or self.default_region('cn-north-4'), zone=_object_value(row, 'os_ext_a_zavailability_zone', 'OS-EXT-AZ:availability_zone', default='') or '', status='running' if _object_value(row, 'status', default='') == 'ACTIVE' else 'stopped', private_ip=private_ip, public_ip=public_ip, spec=specs['spec'], cpu=specs['cpu'], memory_gb=specs['memory_gb'], disk_gb=specs['disk_gb'], tags=tags, metadata={'host_status': _object_value(row, 'host_status', default=''), 'description': _object_value(row, 'description', default=''), 'enterprise_project_id': _object_value(row, 'enterprise_project_id', default='')}))
        return assets

    def provision_instances(self, request_id, specs, names):
        ecs_module = importlib.import_module('huaweicloudsdkecs.v2')
        region = specs.get('region') or self.default_region('cn-north-4')
        client = self._client(region)
        server = ecs_module.PostPaidServer(
            availability_zone=specs.get('zone') or None,
            count=len(names),
            flavor_ref=specs['flavor_ref'],
            image_ref=specs['image_id'],
            is_auto_rename=len(names) > 1,
            key_name=specs.get('key_name') or None,
            name=names[0] if len(names) == 1 else specs['instance_name_prefix'],
            nics=[ecs_module.PostPaidServerNic(subnet_id=specs['subnet_id'])],
            root_volume=ecs_module.PostPaidServerRootVolume(
                volumetype=specs.get('root_volume_type') or 'GPSSD',
                size=int(specs.get('root_volume_size') or 40),
            ),
            security_groups=[ecs_module.PostPaidServerSecurityGroup(id=specs['security_group_id'])],
            server_tags=[ecs_module.PostPaidServerTag(key='sxdevops-request-id', value=str(request_id))],
            vpcid=specs['vpc_id'],
            description=f'SXDevOps resource request #{request_id}',
        )
        response = client.create_servers(ecs_module.CreateServersRequest(
            x_client_token=f'sxdevops-request-{request_id}',
            body=ecs_module.CreateServersRequestBody(server=server),
        ))
        server_ids = list(getattr(response, 'server_ids', None) or [])
        if not server_ids:
            raise CloudAdapterError('华为云未返回云服务器 ID，创建结果无法确认。')
        resources = []
        for index, server_id in enumerate(server_ids):
            name = names[index] if index < len(names) else f"{specs['instance_name_prefix']}-{index + 1:02d}"
            private_ip = ''
            public_ip = ''
            status = 'BUILD'
            try:
                detail_response = client.list_servers_details(ecs_module.ListServersDetailsRequest(server_id=server_id))
                detail = (getattr(detail_response, 'servers', None) or [None])[0]
                if detail:
                    name = _object_value(detail, 'name', default=name) or name
                    status = _object_value(detail, 'status', default=status) or status
                    for address_list in (_object_value(detail, 'addresses', default={}) or {}).values():
                        for address in address_list or []:
                            address_value = _object_value(address, 'addr', default='') or ''
                            address_type = _object_value(address, 'os_ext_ip_stype', 'OS-EXT-IPS:type', default='') or ''
                            if address_type == 'floating' and not public_ip:
                                public_ip = address_value
                            elif not private_ip:
                                private_ip = address_value
            except Exception:
                pass
            resources.append({
                'provider': self.provider,
                'instance_id': server_id,
                'hostname': name,
                'private_ip': private_ip,
                'public_ip': public_ip,
                'region': region,
                'zone': specs.get('zone') or '',
                'instance_type': specs['flavor_ref'],
                'status': status,
                'job_id': getattr(response, 'job_id', '') or '',
            })
        return resources

class VSphereCloudAdapter(BaseCloudAdapter):
    provider = 'vsphere'
    provider_label = 'VMware vSphere / ESXi'
    required_modules = ('pyVim.connect', 'pyVmomi')
    supports_inventory = True
    supports_provisioning = True

    def _connection_params(self):
        host, port = _normalize_endpoint(self.credential.account_id or self.credential.default_region or '', 443)
        username = (self.credential.access_key_id or '').strip()
        password = self.credential.access_key_secret or ''
        if not host or not username or not password:
            raise CloudAdapterError('vSphere/ESXi 账号需要填写地址、用户名和密码。')
        return host, port, username, password

    def _connect(self):
        if not self.capability()['installed']:
            self.unavailable_error()
        connect_module = importlib.import_module('pyVim.connect')
        pyvmomi_module = importlib.import_module('pyVmomi')
        invalid_login_error = getattr(getattr(pyvmomi_module.vim, 'fault', None), 'InvalidLogin', None)
        method_fault_error = getattr(getattr(pyvmomi_module, 'vmodl', None), 'MethodFault', None)
        host, port, username, password = self._connection_params()
        try:
            service_instance = connect_module.SmartConnect(
                host=host,
                user=username,
                pwd=password,
                port=port,
                sslContext=ssl._create_unverified_context(),
            )
        except socket.gaierror as exc:
            raise CloudAdapterError(f'无法解析 vSphere 地址「{host}」，请确认后端服务器能访问该地址，或填写可解析的 IP/域名。') from exc
        except Exception as exc:
            if invalid_login_error and isinstance(exc, invalid_login_error):
                raise CloudAdapterError(f'vSphere 账号认证失败，请检查用户名、密码和登录域：{_pyvmomi_fault_message(exc)}') from exc
            if method_fault_error and isinstance(exc, method_fault_error):
                raise CloudAdapterError(f'vSphere 接口返回错误：{_pyvmomi_fault_message(exc)}') from exc
            if isinstance(exc, (TimeoutError, ConnectionRefusedError, OSError)):
                raise CloudAdapterError(f'无法连接 vSphere 地址「{host}:{port}」，请确认后端服务器网络可达且端口开放。') from exc
            raise
        return connect_module, service_instance

    def test_connection(self):
        connect_module, service_instance = self._connect()
        try:
            content = service_instance.RetrieveContent()
            about = getattr(content, 'about', None)
            version = getattr(about, 'version', '') or ''
            name = getattr(about, 'fullName', '') or 'VMware vSphere'
            return {
                'success': True,
                'status': 'healthy',
                'message': f'{name} connectivity verified, version {version or "-"}.',
                'region': self.credential.default_region or self.credential.account_id,
                'demo_mode': False,
                'sdk_mode': 'pyvmomi',
                'version': version,
            }
        finally:
            connect_module.Disconnect(service_instance)

    def fetch_inventory(self, environment):
        connect_module, service_instance = self._connect()
        pyvmomi_module = importlib.import_module('pyVmomi')
        vim_module = pyvmomi_module.vim
        region = environment.region or self.credential.default_region or self.credential.account_id
        assets = []
        try:
            content = service_instance.RetrieveContent()
            view = content.viewManager.CreateContainerView(content.rootFolder, [vim_module.VirtualMachine], True)
            try:
                for vm in view.view:
                    summary = getattr(vm, 'summary', None)
                    config = getattr(summary, 'config', None)
                    runtime = getattr(summary, 'runtime', None)
                    guest = getattr(summary, 'guest', None)
                    storage = getattr(summary, 'storage', None)
                    host_obj = getattr(runtime, 'host', None)
                    power_state = str(getattr(runtime, 'powerState', '') or '')
                    committed = getattr(storage, 'committed', 0) or 0
                    uncommitted = getattr(storage, 'uncommitted', 0) or 0
                    disk_gb = round((committed + uncommitted) / 1024 / 1024 / 1024, 1) if committed or uncommitted else 0
                    memory_mb = getattr(config, 'memorySizeMB', 0) or 0
                    vm_id = getattr(config, 'uuid', '') or getattr(config, 'instanceUuid', '') or getattr(vm, '_moId', '')
                    name = getattr(config, 'name', '') or getattr(vm, 'name', '') or vm_id
                    assets.append(self.asset(
                        environment,
                        name,
                        'ecs',
                        vm_id,
                        region=region,
                        zone=getattr(host_obj, 'name', '') or '',
                        status='running' if 'poweredOn' in power_state else 'stopped',
                        charge_type='private_cloud',
                        private_ip=getattr(guest, 'ipAddress', '') or '',
                        spec=f'VMware VM / {getattr(config, "numCpu", 0) or 0}C{round(memory_mb / 1024, 1) if memory_mb else 0}G',
                        cpu=getattr(config, 'numCpu', 0) or 0,
                        memory_gb=round(memory_mb / 1024, 1) if memory_mb else 0,
                        disk_gb=disk_gb,
                        tags={'platform': 'vsphere'},
                        metadata={
                            'vm_path': getattr(config, 'vmPathName', '') or '',
                            'guest_os': getattr(config, 'guestFullName', '') or '',
                            'power_state': power_state,
                            'host': getattr(host_obj, 'name', '') or '',
                            'supported_version': 'ESXi/vCenter 8.0.2',
                        },
                    ))
            finally:
                view.Destroy()
        finally:
            connect_module.Disconnect(service_instance)
        return assets

    def provision_instances(self, request_id, specs, names):
        connect_module, service_instance = self._connect()
        pyvmomi_module = importlib.import_module('pyVmomi')
        vim_module = pyvmomi_module.vim
        try:
            content = service_instance.RetrieveContent()

            def find_one(vim_type, name, required=True):
                view = content.viewManager.CreateContainerView(content.rootFolder, [vim_type], True)
                try:
                    result = next((item for item in view.view if getattr(item, 'name', '') == name), None)
                finally:
                    view.Destroy()
                if required and result is None:
                    raise CloudAdapterError(f'vSphere 中未找到 {name}。')
                return result

            template = find_one(vim_module.VirtualMachine, specs['template_name'])
            datastore = find_one(vim_module.Datastore, specs['datastore_name'])
            cluster_name = specs.get('cluster_name') or ''
            cluster = find_one(vim_module.ClusterComputeResource, cluster_name) if cluster_name else None
            resource_pool = cluster.resourcePool if cluster else getattr(template, 'resourcePool', None)
            folder_name = specs.get('folder_name') or ''
            folder = find_one(vim_module.Folder, folder_name) if folder_name else getattr(template, 'parent', None)
            if resource_pool is None or folder is None:
                raise CloudAdapterError('无法确定 vSphere 资源池或虚拟机目录。')

            resources = []
            for name in names:
                existing_vm = find_one(vim_module.VirtualMachine, name, required=False)
                if existing_vm:
                    annotation = getattr(getattr(existing_vm, 'config', None), 'annotation', '') or ''
                    if f'resource request #{request_id}' not in annotation:
                        raise CloudAdapterError(f'vSphere 虚拟机 {name} 已存在，请调整命名后重试。')
                    vm = existing_vm
                else:
                    relocate_spec = vim_module.vm.RelocateSpec(pool=resource_pool, datastore=datastore)
                    config_spec = vim_module.vm.ConfigSpec(
                        annotation=f'SXDevOps resource request #{request_id}',
                        numCPUs=int(specs.get('cpu') or 2),
                        memoryMB=int(float(specs.get('memory_gb') or 4) * 1024),
                    )
                    clone_spec = vim_module.vm.CloneSpec(
                        location=relocate_spec,
                        config=config_spec,
                        powerOn=bool(specs.get('power_on', True)),
                        template=False,
                    )
                    task = template.CloneVM_Task(folder=folder, name=name, spec=clone_spec)
                    deadline = time.monotonic() + 900
                    while str(getattr(task.info, 'state', '')) in {'queued', 'running'}:
                        if time.monotonic() >= deadline:
                            raise CloudAdapterError(f'vSphere 克隆虚拟机 {name} 超时。')
                        time.sleep(1)
                    if str(getattr(task.info, 'state', '')) != 'success':
                        error = getattr(task.info, 'error', None)
                        raise CloudAdapterError(f'vSphere 克隆虚拟机 {name} 失败：{_pyvmomi_fault_message(error)}')
                    vm = getattr(task.info, 'result', None) or find_one(vim_module.VirtualMachine, name)
                summary = getattr(vm, 'summary', None)
                config = getattr(summary, 'config', None)
                guest = getattr(summary, 'guest', None)
                resources.append({
                    'provider': self.provider,
                    'instance_id': getattr(config, 'uuid', '') or getattr(config, 'instanceUuid', '') or getattr(vm, '_moId', ''),
                    'hostname': name,
                    'private_ip': getattr(guest, 'ipAddress', '') or '',
                    'public_ip': '',
                    'region': self.credential.default_region or self.credential.account_id,
                    'zone': cluster_name,
                    'instance_type': f"{int(specs.get('cpu') or 2)}C{specs.get('memory_gb') or 4}G",
                    'status': 'poweredOn' if specs.get('power_on', True) else 'poweredOff',
                })
            return resources
        finally:
            connect_module.Disconnect(service_instance)


class PlaceholderCloudAdapter(BaseCloudAdapter):
    def unavailable_error(self):
        raise CloudAdapterError(f'{self.provider_label} live SDK integration is not installed in this environment.')


class BaiduCloudAdapter(PlaceholderCloudAdapter):
    provider = 'baidu'
    provider_label = 'Baidu AI Cloud'
    required_modules = ('baidubce',)


ADAPTERS = {
    'aliyun': AliyunCloudAdapter,
    'tencent': TencentCloudAdapter,
    'huawei': HuaweiCloudAdapter,
    'baidu': BaiduCloudAdapter,
    'aws': AwsCloudAdapter,
    'vsphere': VSphereCloudAdapter,
}


def get_cloud_adapter(credential):
    adapter_class = ADAPTERS.get(credential.provider)
    if not adapter_class:
        return None
    return adapter_class(credential)


def get_provider_sdk_capabilities():
    return {provider: adapter.dependency_status() for provider, adapter in ADAPTERS.items()}
