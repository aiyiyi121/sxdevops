from django.contrib.auth import get_user_model
import os

from django.db import transaction

from sxdevops.features import filter_feature_permissions, permission_feature_enabled

from .models import PermissionDefinition, Role, SystemModuleSetting, UserGroup
from .registry import BUILTIN_ROLES, PERMISSION_DEFINITIONS
from .preview import is_preview_read_permission, is_preview_user


User = get_user_model()
DEFAULT_ADMIN_USERNAME = 'admin'
DEFAULT_ADMIN_PASSWORD_ENV = 'SXDEVOPS_ADMIN_INITIAL_PASSWORD'
DEFAULT_ADMIN_EMAIL = 'admin@example.com'
SYSTEM_MODULE_CATALOG = [
    {'code': 'dashboard', 'title': '系统态势', 'required': False, 'description': '平台首页与核心概览入口。', 'sort_order': 10, 'level': 1},
    {'code': 'cmdb', 'title': 'CMDB', 'required': False, 'description': '统一资源台账、模型、同步与治理入口。', 'sort_order': 20, 'level': 1},
    {'code': 'cmdb.overview', 'title': '概览', 'required': False, 'description': 'CMDB 资源概览。', 'sort_order': 21, 'parent_code': 'cmdb', 'level': 2},
    {'code': 'cmdb.ledger', 'title': '资产台账', 'required': False, 'description': '资产统一台账。', 'sort_order': 22, 'parent_code': 'cmdb', 'level': 2},
    {'code': 'cmdb.model', 'title': '分类视图', 'required': False, 'description': '资产模型分类视图。', 'sort_order': 23, 'parent_code': 'cmdb', 'level': 2},
    {'code': 'cmdb.topology', 'title': '资产拓扑', 'required': False, 'description': '按资产树筛选分类关系拓扑。', 'sort_order': 24, 'parent_code': 'cmdb', 'level': 2},
    {'code': 'cmdb.governance', 'title': '资产治理', 'required': False, 'description': '资产质量与治理入口。', 'sort_order': 25, 'parent_code': 'cmdb', 'level': 2},
    {'code': 'cmdb.cost', 'title': '成本管理', 'required': False, 'description': '资源成本管理入口。', 'sort_order': 26, 'parent_code': 'cmdb', 'level': 2},
    {'code': 'cmdb.platform-config', 'title': '平台配置', 'required': False, 'description': '资产采集、分类配置与 IP 管理。', 'sort_order': 27, 'parent_code': 'cmdb', 'level': 2},
    {'code': 'cmdb.requests', 'title': '资源运营', 'required': False, 'incomplete': True, 'description': '资源申请、成本与授权入口。', 'sort_order': 28, 'parent_code': 'cmdb', 'level': 2},
    {'code': 'cmdb.thresholds', 'title': '平台设置', 'required': False, 'incomplete': True, 'description': 'CMDB 平台设置与审计入口。', 'sort_order': 29, 'parent_code': 'cmdb', 'level': 2},
    {'code': 'cmdb.views', 'title': '视图展示', 'required': False, 'incomplete': True, 'description': '资产视图展示。', 'sort_order': 30, 'parent_code': 'cmdb', 'level': 2},
    {'code': 'aiops', 'title': 'AIOps', 'required': False, 'description': '智能助手、知识图谱与配置入口。', 'sort_order': 40, 'level': 1},
    {'code': 'aiops.chat', 'title': '智能助手', 'required': False, 'description': '智能助手入口。', 'sort_order': 41, 'parent_code': 'aiops', 'level': 2},
    {'code': 'aiops.knowledge', 'title': '知识图谱', 'required': False, 'description': '知识图谱入口。', 'sort_order': 42, 'parent_code': 'aiops', 'level': 2},
    {'code': 'aiops.config', 'title': '智能体配置', 'required': False, 'description': '智能体配置入口。', 'sort_order': 43, 'parent_code': 'aiops', 'level': 2},
    {'code': 'aiops.audit', 'title': '智能体审计', 'required': False, 'description': '智能体审计入口。', 'sort_order': 44, 'parent_code': 'aiops', 'level': 2},
    {'code': 'aiops.widget', 'title': '右下角智能助手', 'required': False, 'description': '控制页面右下角智能助手悬浮入口的显示与隐藏。', 'sort_order': 45, 'parent_code': 'aiops', 'level': 2, 'config_type': 'floating_entry'},
    {'code': 'containers', 'title': '容器管理', 'required': False, 'description': 'K8s 与 Docker 管理入口。', 'sort_order': 46, 'level': 1},
    {'code': 'containers.k8s', 'title': 'K8s 集群', 'required': False, 'description': 'K8s 集群入口。', 'sort_order': 47, 'parent_code': 'containers', 'level': 2},
    {'code': 'containers.docker', 'title': 'Docker 环境', 'required': False, 'description': 'Docker 环境入口。', 'sort_order': 48, 'parent_code': 'containers', 'level': 2},
    {'code': 'observability', 'title': '可观测性', 'required': False, 'description': '监控、日志、链路与告警入口。', 'sort_order': 50, 'level': 1},
    {'code': 'observability.system-posture', 'title': '系统态势', 'required': False, 'description': '系统 SLO 与态势历史入口。', 'sort_order': 51, 'parent_code': 'observability', 'level': 2},
    {'code': 'observability.boards', 'title': '仪表盘', 'required': False, 'description': 'Grafana 仪表盘入口。', 'sort_order': 52, 'parent_code': 'observability', 'level': 2},
    {'code': 'observability.metrics', 'title': '指标查询', 'required': False, 'description': '指标查询入口。', 'sort_order': 52, 'parent_code': 'observability', 'level': 2},
    {'code': 'observability.rum', 'title': 'RUM', 'required': False, 'incomplete': True, 'description': '真实用户监控入口。', 'sort_order': 53, 'parent_code': 'observability', 'level': 2},
    {'code': 'observability.logs', 'title': '日志中心', 'required': False, 'description': '日志查询入口。', 'sort_order': 54, 'parent_code': 'observability', 'level': 2},
    {'code': 'observability.tracing', 'title': '链路追踪', 'required': False, 'description': '链路追踪入口。', 'sort_order': 55, 'parent_code': 'observability', 'level': 2},
    {'code': 'observability.datasources', 'title': '数据源', 'required': False, 'description': '可观测性数据源入口。', 'sort_order': 56, 'parent_code': 'observability', 'level': 2},
    {'code': 'observability.alerts', 'title': '告警中心', 'required': False, 'description': '告警管理入口。', 'sort_order': 57, 'parent_code': 'observability', 'level': 2},
    {'code': 'events', 'title': '事件中心', 'required': False, 'description': '事件流、事件源与分析入口。', 'sort_order': 60, 'level': 1},
    {'code': 'events.wall', 'title': '事件中心', 'required': False, 'description': '事件中心入口。', 'sort_order': 61, 'parent_code': 'events', 'level': 2},
    {'code': 'events.environments', 'title': '事件环境', 'required': False, 'description': '事件环境配置。', 'sort_order': 62, 'parent_code': 'events', 'level': 2},
    {'code': 'events.sources', 'title': '事件源', 'required': False, 'description': '事件源配置。', 'sort_order': 63, 'parent_code': 'events', 'level': 2},
    {'code': 'tasks', 'title': '任务中心', 'required': False, 'description': '资源、工作台与定时任务入口。', 'sort_order': 70, 'level': 1},
    {'code': 'tasks.workbench', 'title': '任务工作台', 'required': False, 'description': '任务工作台入口。', 'sort_order': 71, 'parent_code': 'tasks', 'level': 2},
    {'code': 'tasks.resources', 'title': '资源底座', 'required': False, 'description': '任务资源底座入口。', 'sort_order': 72, 'parent_code': 'tasks', 'level': 2},
    {'code': 'workorders', 'title': '工单系统', 'required': False, 'description': '发布、SQL 审计与事务工单入口。', 'sort_order': 80, 'level': 1},
    {'code': 'workorders.releases', 'title': '应用发布', 'required': False, 'description': '应用发布入口。', 'sort_order': 81, 'parent_code': 'workorders', 'level': 2},
    {'code': 'workorders.sql', 'title': 'SQL 审计', 'required': False, 'description': 'SQL 审计入口。', 'sort_order': 82, 'parent_code': 'workorders', 'level': 2},
    {'code': 'workorders.transactions', 'title': '事务工单', 'required': False, 'description': '事务工单入口。', 'sort_order': 83, 'parent_code': 'workorders', 'level': 2},
    {'code': 'workorders.approval-flows', 'title': '审批流', 'required': False, 'description': '审批流入口。', 'sort_order': 84, 'parent_code': 'workorders', 'level': 2},
    {'code': 'cloudsecurity', 'title': '安全中心', 'required': False, 'description': '统一查看边界防护与内部平台安全态势。', 'sort_order': 90, 'level': 1},
    {'code': 'cloudsecurity.waf', 'title': 'WAF 防火墙', 'required': False, 'description': '阿里云 WAF 3.0 防护态势入口。', 'sort_order': 91, 'parent_code': 'cloudsecurity', 'level': 2},
    {'code': 'cloudsecurity.internal-platform', 'title': '内部平台安全', 'required': False, 'description': '内部平台账号、权限、审计与变更安全态势入口。', 'sort_order': 92, 'parent_code': 'cloudsecurity', 'level': 2},
    {'code': 'system', 'title': '系统管理', 'required': True, 'description': '系统管理保持固定显示。', 'sort_order': 100, 'level': 1},
    {'code': 'system.users', 'title': '用户管理', 'required': True, 'description': '用户与权限管理入口。', 'sort_order': 101, 'parent_code': 'system', 'level': 2},
    {'code': 'system.audit', 'title': '操作审计', 'required': True, 'description': '操作审计入口。', 'sort_order': 102, 'parent_code': 'system', 'level': 2},
    {'code': 'system.modules', 'title': '系统设置', 'required': True, 'description': '网站基础信息与菜单配置入口。', 'sort_order': 103, 'parent_code': 'system', 'level': 2},
]

DEFAULT_SYSTEM_MODULE_CODE = 'dashboard'
SYSTEM_MODULE_PATHS = {
    'dashboard': '/dashboard',
    'cmdb.overview': '/cmdb/overview',
    'cmdb.ledger': '/cmdb/ledger',
    'cmdb.model': '/cmdb/model',
    'cmdb.topology': '/cmdb/topology',
    'cmdb.governance': '/cmdb/governance',
    'cmdb.cost': '/cmdb/cost',
    'cmdb.platform-config': '/cmdb/platform-config',
    'cmdb.requests': '/cmdb/requests',
    'cmdb.thresholds': '/cmdb/thresholds',
    'cmdb.views': '/cmdb/views',
    'aiops.chat': '/aiops/chat',
    'aiops.knowledge': '/aiops/knowledge',
    'aiops.config': '/aiops/config',
    'aiops.audit': '/aiops/audit',
    'observability.system-posture': '/observability/system-posture',
    'observability.boards': '/observability/grafana',
    'observability.metrics': '/observability/metrics',
    'observability.rum': '/observability/rum',
    'observability.logs': '/logs/query',
    'observability.tracing': '/observability/tracing',
    'observability.datasources': '/observability/datasources',
    'observability.alerts': '/alerts',
    'events.wall': '/events/wall',
    'events.environments': '/events/environments',
    'events.sources': '/events/sources',
    'cloudsecurity.waf': '/cloud-security/waf',
    'cloudsecurity.internal-platform': '/security-center/internal-platform',
    'tasks.workbench': '/tasks/workbench',
    'tasks.resources': '/tasks/resources',
    'workorders.releases': '/workorders/releases',
    'workorders.sql': '/workorders/sql',
    'workorders.transactions': '/workorders/transactions',
    'workorders.approval-flows': '/workorders/approval-flows',
    'containers.k8s': '/containers/k8s',
    'containers.docker': '/containers/docker',
    'system.users': '/users',
    'system.audit': '/users/audit',
    'system.modules': '/users/modules',
}


@transaction.atomic
def ensure_builtin_rbac():
    permission_by_code = {}
    for index, (code, name, category, description) in enumerate(PERMISSION_DEFINITIONS, start=1):
        if not permission_feature_enabled(code):
            continue
        permission, _ = PermissionDefinition.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'category': category,
                'description': description,
                'sort_order': index,
                'is_builtin': True,
            },
        )
        permission_by_code[code] = permission

    for role_data in BUILTIN_ROLES:
        role, _ = Role.objects.update_or_create(
            code=role_data['code'],
            defaults={
                'name': role_data['name'],
                'description': role_data['description'],
                'is_builtin': True,
            },
        )
        codes = role_data['permissions']
        if '*' in codes:
            role.permissions.set(PermissionDefinition.objects.filter(code__in=permission_by_code))
        else:
            role.permissions.set([permission_by_code[code] for code in filter_feature_permissions(codes) if code in permission_by_code])


@transaction.atomic
def ensure_default_superuser():
    if User.objects.filter(is_superuser=True).exists():
        return

    initial_password = os.getenv(DEFAULT_ADMIN_PASSWORD_ENV, '').strip()
    if not initial_password:
        return

    user = User.objects.create_superuser(
        username=DEFAULT_ADMIN_USERNAME,
        email=DEFAULT_ADMIN_EMAIL,
        password=initial_password,
    )
    role = Role.objects.filter(code='platform-admin').first()
    if role:
        role.users.add(user)


def get_user_direct_roles(user):
    if not getattr(user, 'is_authenticated', False):
        return Role.objects.none()
    return user.rbac_roles.prefetch_related('permissions').all()


def get_user_group_roles(user):
    if not getattr(user, 'is_authenticated', False):
        return Role.objects.none()
    return Role.objects.filter(user_groups__users=user).prefetch_related('permissions').distinct()


def get_user_effective_permissions(user):
    if not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False):
        return set()
    if is_preview_user(user):
        return set(filter_feature_permissions([
            code for code, *_ in PERMISSION_DEFINITIONS if is_preview_read_permission(code)
        ]))
    if getattr(user, 'is_superuser', False):
        return set(filter_feature_permissions(PermissionDefinition.objects.values_list('code', flat=True)))

    permission_codes = set(
        PermissionDefinition.objects.filter(roles__users=user).values_list('code', flat=True)
    )
    permission_codes.update(
        PermissionDefinition.objects.filter(roles__user_groups__users=user).values_list('code', flat=True)
    )
    return set(filter_feature_permissions(permission_codes))


def user_has_permissions(user, codes):
    if not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False):
        return False
    codes = [code for code in (codes or []) if code]
    if any(not permission_feature_enabled(code) for code in codes):
        return False
    if not codes:
        return True
    if getattr(user, 'is_superuser', False) and not is_preview_user(user):
        return True
    granted = get_user_effective_permissions(user)
    return all(code in granted for code in codes)


def get_permission_catalog():
    disabled_codes = [
        code
        for code in PermissionDefinition.objects.values_list('code', flat=True)
        if not permission_feature_enabled(code)
    ]
    return PermissionDefinition.objects.exclude(code__in=disabled_codes).order_by('sort_order', 'code')


def get_builtin_role_catalog():
    return Role.objects.filter(is_builtin=True).order_by('name')


@transaction.atomic
def ensure_system_module_settings():
    existing = {item.code: item for item in SystemModuleSetting.objects.all()}
    for module in SYSTEM_MODULE_CATALOG:
        setting = existing.get(module['code'])
        if setting is None:
            legacy_boards = existing.get('observability.boards') if module['code'] == 'observability.system-posture' else None
            SystemModuleSetting.objects.create(
                code=module['code'],
                enabled=legacy_boards.enabled if legacy_boards else not module.get('incomplete', False),
                sort_order=legacy_boards.sort_order if legacy_boards else None,
            )


def get_default_system_module_code():
    ensure_system_module_settings()
    configured_code = SystemModuleSetting.objects.filter(
        is_default=True,
        code__in=SYSTEM_MODULE_PATHS,
    ).values_list('code', flat=True).first()
    return configured_code or DEFAULT_SYSTEM_MODULE_CODE


def get_default_system_page():
    code = get_default_system_module_code()
    return SYSTEM_MODULE_PATHS.get(code, SYSTEM_MODULE_PATHS[DEFAULT_SYSTEM_MODULE_CODE])


def get_system_module_settings():
    ensure_system_module_settings()
    setting_map = {item.code: item for item in SystemModuleSetting.objects.all()}
    default_code = next((
        item.code
        for item in setting_map.values()
        if item.is_default and item.code in SYSTEM_MODULE_PATHS
    ), DEFAULT_SYSTEM_MODULE_CODE)
    items = []
    for module in SYSTEM_MODULE_CATALOG:
        setting = setting_map.get(module['code'])
        items.append({
            'code': module['code'],
            'title': module['title'],
            'description': module['description'],
            'required': module['required'],
            'incomplete': module.get('incomplete', False),
            'sort_order': setting.sort_order if setting is not None and setting.sort_order is not None else module['sort_order'],
            'default_sort_order': module['sort_order'],
            'parent_code': module.get('parent_code', ''),
            'level': module.get('level', 1),
            'config_type': module.get('config_type', 'menu'),
            'path': SYSTEM_MODULE_PATHS.get(module['code'], ''),
            'enabled': module['required'] or (setting.enabled if setting is not None else not module.get('incomplete', False)),
            'is_default': module['code'] == default_code,
            'updated_by': '' if setting is None else setting.updated_by,
            'updated_at': None if setting is None else setting.updated_at,
        })
    ordered = sorted(items, key=lambda item: (item['sort_order'], item['default_sort_order'], item['code']))
    children = {}
    for item in ordered:
        children.setdefault(item['parent_code'], []).append(item)
    return [item for parent in children.get('', []) for item in [parent, *children.get(parent['code'], [])]]


def get_user_summary(user):
    roles = list(Role.objects.filter(users=user).values('id', 'code', 'name'))
    groups = list(UserGroup.objects.filter(users=user).values('id', 'code', 'name'))
    return {
        'roles': roles,
        'groups': groups,
        'effective_permissions': sorted(get_user_effective_permissions(user)),
    }
