import ipaddress

from django.db.models import Count, Q

from cmdb.models import ConfigItem, ResourceNode
from cmdb.sync import HOST_LIKE_CI_TYPE_CODES, HOST_LIKE_CI_TYPE_NAMES, is_host_like_ci

from .models import TaskResource, TaskResourceGroup


def cmdb_resource_kind(config_item):
    if config_item.ci_type.code == 'K8S_CLUSTER':
        return TaskResource.RESOURCE_K8S
    if is_host_like_ci(config_item) or config_item.ci_type.code == 'VIRTUAL_MACHINE':
        return TaskResource.RESOURCE_HOST
    return ''


def cmdb_resource_defaults(config_item):
    attributes = config_item.attributes or {}
    defaults = {'name': config_item.name}
    if cmdb_resource_kind(config_item) == TaskResource.RESOURCE_HOST:
        for key in ('ip_address', 'private_ip', 'public_ip', 'host_ip', 'ip'):
            try:
                defaults['ip_address'] = str(ipaddress.ip_address(str(attributes.get(key) or '').strip()))
                break
            except ValueError:
                continue
        ssh_user = str(attributes.get('ssh_user') or attributes.get('login_user') or '').strip()
        if ssh_user:
            defaults['ssh_user'] = ssh_user[:64]
        try:
            ssh_port = int(attributes.get('ssh_port'))
            if 1 <= ssh_port <= 65535:
                defaults['ssh_port'] = ssh_port
        except (TypeError, ValueError):
            pass
    owner = str(config_item.admin_user or attributes.get('ops_owner') or '').strip()
    description = str(attributes.get('description') or attributes.get('specification') or '').strip()
    if owner:
        defaults['owner'] = owner[:64]
    if description:
        defaults['description'] = description[:255]
    return defaults


def cmdb_resource_group_names(config_item):
    return (
        config_item.environment_node.name if config_item.environment_node_id else config_item.environment,
        config_item.business_node.name if config_item.business_node_id else config_item.business_line,
    )


def visible_cmdb_resources(user):
    from cmdb.views import _apply_ci_authorization_scope

    queryset = ConfigItem.objects.select_related('ci_type', 'environment_node', 'business_node')
    return _apply_ci_authorization_scope(queryset, user, permission='view')


def scope_task_resources(queryset, user):
    return queryset.filter(
        Q(cmdb_ci__isnull=True) | Q(cmdb_ci_id__in=visible_cmdb_resources(user).values('pk')),
    )


def cmdb_resource_options(user, resource_type=''):
    host_types = Q(ci_type__code__in=[*HOST_LIKE_CI_TYPE_CODES, 'VIRTUAL_MACHINE']) | Q(ci_type__name__in=HOST_LIKE_CI_TYPE_NAMES)
    cluster_types = Q(ci_type__code='K8S_CLUSTER')
    type_filter = host_types | cluster_types
    if resource_type == TaskResource.RESOURCE_HOST:
        type_filter = host_types
    elif resource_type == TaskResource.RESOURCE_K8S:
        type_filter = cluster_types
    return visible_cmdb_resources(user).filter(type_filter).select_related('task_resource').order_by('name', 'id')


def filter_resource_business_scope(queryset, params, *, cmdb=False):
    for parameter, node_field, name_field in (
        ('scope_business', 'business_node_id' if cmdb else 'system__cmdb_node_id', 'business_line' if cmdb else 'system__name'),
        ('scope_environment', 'environment_node_id' if cmdb else 'environment__cmdb_node_id', 'environment' if cmdb else 'environment__name'),
    ):
        value = str(params.get(parameter) or '')
        if not value:
            continue
        if value == 'unassigned':
            queryset = queryset.filter(**{f'{node_field}__isnull': True}).filter(
                Q(**{f'{name_field}__isnull': True}) | Q(**{name_field: ''}),
            )
        elif value.startswith('node:') and value[5:].isdigit():
            queryset = queryset.filter(**{node_field: int(value[5:])})
        elif value.startswith('name:'):
            queryset = queryset.filter(**{f'{node_field}__isnull': True, name_field: value[5:]})
        else:
            return queryset.none()
    return queryset


def resource_business_tree(queryset, *, cmdb=False, include_cmdb_nodes=True):
    nodes = list(ResourceNode.objects.filter(node_type__in=['biz', 'env']).order_by('sort_order', 'id'))
    node_map = {node.pk: node for node in nodes}
    businesses = {}

    def ensure_business(node_id, name):
        node = node_map.get(node_id)
        token = f'node:{node_id}' if node_id else f'name:{name}' if name else 'unassigned'
        if token not in businesses:
            businesses[token] = {
                'key': f'business:{token}', 'name': node.name if node else name or '未归属业务线',
                'node_type': 'biz', 'scope_business': token, 'scope_environment': '',
                'cmdb_node': node_id, 'cmdb_parent': node.parent_id if node else None,
                'is_synced': node.is_synced if node else False, 'sort_order': node.sort_order if node else 0,
                'resource_count': 0, 'children': [],
            }
        return businesses[token]

    def ensure_environment(business, node_id, name):
        node = node_map.get(node_id)
        token = f'node:{node_id}' if node_id else f'name:{name}' if name else 'unassigned'
        existing = next((child for child in business['children'] if child['scope_environment'] == token), None)
        if existing:
            return existing
        environment = {
            'key': f"{business['key']}/environment:{token}", 'name': node.name if node else name or '未归属环境',
            'node_type': 'env', 'scope_business': business['scope_business'], 'scope_environment': token,
            'cmdb_node': node_id, 'cmdb_parent': node.parent_id if node else None,
            'is_synced': node.is_synced if node else False, 'sort_order': node.sort_order if node else 0,
            'resource_count': 0, 'children': [],
        }
        business['children'].append(environment)
        return environment

    if include_cmdb_nodes:
        for node in nodes:
            if node.node_type == 'biz':
                ensure_business(node.pk, node.name)
        for node in nodes:
            if node.node_type == 'env' and node.parent_id in node_map and node_map[node.parent_id].node_type == 'biz':
                business = ensure_business(node.parent_id, node_map[node.parent_id].name)
                ensure_environment(business, node.pk, node.name)

    fields = (
        ('business_node_id', 'business_line', 'environment_node_id', 'environment') if cmdb else
        ('system__cmdb_node_id', 'system__name', 'environment__cmdb_node_id', 'environment__name')
    )
    for row in queryset.order_by().values(*fields).annotate(total=Count('id')):
        business = ensure_business(row[fields[0]], row[fields[1]] or '')
        environment = ensure_environment(business, row[fields[2]], row[fields[3]] or '')
        business['resource_count'] += row['total']
        environment['resource_count'] += row['total']
    return list(businesses.values())


def _cmdb_group(group_type, name, node=None, parent=None):
    queryset = TaskResourceGroup.objects.filter(group_type=group_type, parent=parent)
    group = queryset.filter(cmdb_node=node).first() if node else None
    if not group:
        group = queryset.filter(name=name[:80], cmdb_node__isnull=True).first()
    if not group:
        group = TaskResourceGroup.objects.create(
            group_type=group_type, name=name[:80], parent=parent, cmdb_node=node,
        )
    elif node and not group.cmdb_node_id:
        group.cmdb_node = node
        group.save(update_fields=['cmdb_node'])
    return group


def apply_cmdb_resource_groups(values, config_item):
    environment_name, system_name = cmdb_resource_group_names(config_item)
    if environment_name:
        values['environment'] = _cmdb_group(
            TaskResourceGroup.GROUP_ENVIRONMENT, environment_name, config_item.environment_node,
        )
    environment = values.get('environment')
    if system_name and environment:
        values['system'] = _cmdb_group(
            TaskResourceGroup.GROUP_SYSTEM, system_name, config_item.business_node, environment,
        )
    elif environment_name and values.get('system') and values['system'].parent_id != environment.id:
        values['system'] = None
    return values


def sync_cmdb_task_resource(config_item):
    resource = TaskResource.objects.filter(cmdb_ci=config_item).select_related('environment', 'system').first()
    if not resource:
        return
    values = cmdb_resource_defaults(config_item)
    values.setdefault('environment', resource.environment)
    values.setdefault('system', resource.system)
    apply_cmdb_resource_groups(values, config_item)
    TaskResource.objects.filter(pk=resource.pk).update(**values)
