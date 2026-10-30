<template>
  <div class="app-layout">
    <aside class="sidebar" :class="{ collapsed: appStore.sidebarCollapsed }">
      <div class="sidebar-logo">
        <div class="logo-icon">
          <img :src="siteStore.siteIcon" :alt="siteStore.siteName" class="brand-mark" />
        </div>
        <div class="logo-copy">
          <span class="logo-text" :title="siteStore.siteName">{{ siteStore.siteName }}</span>
          <span class="logo-subtext">AI Agent</span>
        </div>
      </div>

      <el-menu
        :default-active="activeMenuPath"
        class="sidebar-nav el-menu-vertical"
        :collapse="appStore.sidebarCollapsed"
        router
        :collapse-transition="false"
        :default-openeds="defaultOpenMenuKeys"
      >
        <template v-for="item in visibleMenuItems" :key="item.title">
          <el-sub-menu v-if="item.children?.length" :index="item.menuKey || item.moduleKey || item.title">
            <template #title>
              <el-icon><component :is="item.icon" /></el-icon>
              <span class="menu-title-row">
                <span>{{ item.title }}</span>
                <span v-if="item.badge" class="menu-status-badge">{{ item.badge }}</span>
              </span>
            </template>
            <el-menu-item
              v-for="child in item.children"
              :key="child.menuKey || child.path"
              :index="child.menuKey || child.path"
              :route="child.route || child.path"
            >
              <template #title>
                <el-icon v-if="child.icon"><component :is="child.icon" /></el-icon>
                <span class="menu-title-row">
                  <span>{{ child.title }}</span>
                  <span v-if="child.badge" class="menu-status-badge">{{ child.badge }}</span>
                </span>
              </template>
            </el-menu-item>
          </el-sub-menu>

          <el-menu-item
            v-else
            class="sidebar-direct-item"
            :index="item.menuKey || item.moduleKey || item.path"
            :route="item.route || item.path"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span class="menu-title-row">
              <span>{{ item.title }}</span>
              <span v-if="item.badge" class="menu-status-badge">{{ item.badge }}</span>
            </span>
            <template v-if="appStore.sidebarCollapsed" #title>{{ item.title }}</template>
          </el-menu-item>
        </template>
      </el-menu>

      <div class="sidebar-footer">
        <div class="sidebar-shortcuts" role="group" aria-label="快捷操作">
          <el-tooltip content="产品介绍" placement="right">
            <button class="sidebar-tool promo-trigger" type="button" aria-label="产品介绍" @click="openProductIntro">
              <el-icon :size="17"><Promotion /></el-icon>
            </button>
          </el-tooltip>

          <el-popover placement="right-end" width="min(360px, calc(100vw - 100px))" trigger="click" popper-class="sidebar-notice-popover">
            <template #reference>
              <button class="sidebar-tool notice-trigger" type="button" :aria-label="notificationCount ? `平台提醒，${notificationCount} 条待关注动态` : '平台提醒'" @click="handleNoticeOpen">
                <el-badge :value="notificationCount" :max="99" :hidden="!notificationCount">
                  <el-icon :size="18"><Bell /></el-icon>
                </el-badge>
              </button>
            </template>

            <div class="notice-panel">
              <div class="notice-panel__header">
                <div>
                  <div class="notice-panel__title">平台提醒</div>
                  <div class="notice-panel__subtitle">
                    {{ notificationCount ? `当前有 ${notificationCount} 条待关注动态` : '当前暂无待关注动态' }}
                  </div>
                </div>
                <el-button link type="primary" :loading="notificationsLoading" @click="loadNotifications">刷新</el-button>
              </div>

              <div v-if="notificationSections.length" class="notice-groups">
                <section
                  v-for="section in notificationSections"
                  :key="section.key"
                  class="notice-group"
                >
                  <div class="notice-group__header">
                    <div class="notice-group__meta">
                      <span class="notice-group__title">{{ section.title }}</span>
                      <span class="notice-group__count">{{ section.items.length }}</span>
                    </div>
                    <el-button
                      v-if="section.route"
                      link
                      type="primary"
                      class="notice-group__more"
                      @click="goSection(section)"
                    >
                      查看更多
                    </el-button>
                  </div>
                  <div class="notice-list">
                    <button
                      v-for="item in section.items"
                      :key="item.key"
                      type="button"
                      class="notice-item"
                      @click="goNotification(item)"
                    >
                      <div class="notice-item__dot" :class="`is-${item.dotTone}`"></div>
                      <div class="notice-item__body">
                        <div class="notice-item__top">
                          <div class="notice-item__title-wrap">
                            <span class="notice-item__title">{{ item.title }}</span>
                            <el-tag size="small" effect="light" :type="item.tagType">{{ item.tag }}</el-tag>
                          </div>
                          <span class="notice-item__time">{{ formatDateTime(item.time) }}</span>
                        </div>
                        <div class="notice-item__desc">{{ item.description }}</div>
                      </div>
                    </button>
                  </div>
                </section>
              </div>
              <div v-else class="notice-empty">
                <el-icon><Bell /></el-icon>
                <span>告警、事件与高风险动态会在这里实时汇总</span>
              </div>
            </div>
          </el-popover>

          <el-dropdown trigger="click" placement="top-start" @command="setTheme">
            <button class="sidebar-tool theme-trigger" type="button" :aria-label="`主题选择，当前${themeLabel}`" :title="`当前主题：${themeLabel}，点击切换`">
              <el-icon :size="18"><Sunny v-if="theme === 'light'" /><Moon v-else /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="option in themeOptions" :key="option.value" :command="option.value" :class="{ 'theme-option--active': theme === option.value }" :aria-current="theme === option.value ? 'true' : undefined">
                  <span class="theme-option">
                    <span class="theme-option__swatch" :class="`theme-option__swatch--${option.value}`" aria-hidden="true"></span>
                    <span>{{ option.label }}</span>
                    <span v-if="option.recommended" class="theme-option__hint">推荐</span>
                    <el-icon v-if="theme === option.value" class="theme-option__check"><Check /></el-icon>
                  </span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <el-tooltip :content="appStore.sidebarCollapsed ? '展开侧栏' : '收起侧栏'" placement="right">
            <button class="sidebar-tool collapse-btn" type="button" :aria-label="appStore.sidebarCollapsed ? '展开侧栏' : '收起侧栏'" :aria-expanded="!appStore.sidebarCollapsed" @click="appStore.toggleSidebar">
              <el-icon :size="18"><Fold v-if="!appStore.sidebarCollapsed" /><Expand v-else /></el-icon>
            </button>
          </el-tooltip>
        </div>

        <el-dropdown class="sidebar-account" placement="top-start" trigger="click" @command="handleUserCommand">
          <button class="user-trigger" type="button" :aria-label="`${authStore.displayName || '未登录'}，账号菜单`">
            <el-avatar :size="28" class="user-avatar">
              <span>{{ userInitials }}</span>
            </el-avatar>
            <span class="user-meta">
              <span class="user-name">{{ authStore.displayName || '未登录' }}</span>
              <span class="user-role">{{ primaryRoleLabel }}</span>
            </span>
            <el-icon class="user-menu-arrow"><ArrowUp /></el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="refresh">刷新权限</el-dropdown-item>
              <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </aside>

    <div class="main-area">
      <main class="content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
      <AIOpsChatWidget v-if="!isAIOpsChatRoute" :show-launcher="showAIOpsChatLauncher" />
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useSiteStore } from '@/stores/site'
import { setTheme, theme, themeLabel, themeOptions } from '@/theme'
import { SYSTEM_POSTURE_ENABLED } from '@/config/features'
import AIOpsChatWidget from '@/components/aiops/AIOpsChatWidget.vue'
import { getDashboardStats, getDeployments, getTransactionTickets } from '@/api/modules/ops'
import { getEventWallAnalysis } from '@/api/modules/eventwall'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()
const siteStore = useSiteStore()
const notificationsLoading = ref(false)
const notificationItems = ref([])
const notificationCount = ref(0)
const moduleVisibility = computed(() => (authStore.moduleSettings || []).reduce((result, item) => ({
  ...result,
  [item.code]: item.required ? true : item.enabled !== false,
}), {}))
const moduleSettingsLoaded = computed(() => authStore.moduleSettingsLoaded)
const moduleOrder = computed(() => new Map((authStore.moduleSettings || []).map((item, index) => [item.code, index])))
const MODULE_SETTINGS_EVENT = 'sxdevops-module-settings-updated'
const TASK_SCHEDULES_VISIBLE = false
const observabilityBoardPermissions = SYSTEM_POSTURE_ENABLED
  ? ['ops.grafana.view', 'ops.observability.system_posture.view']
  : ['ops.grafana.view']
const defaultOpenMenuKeys = []
let notificationTimer = null
const menuItems = [
  { moduleKey: 'dashboard', path: '/dashboard', title: '系统态势', icon: 'Odometer', permission: 'ops.dashboard.view' },
  {
    moduleKey: 'cmdb',
    title: 'CMDB',
    icon: 'Monitor',
    children: [
      { path: '/cmdb/overview', visibilityKey: 'cmdb.overview', title: '概览', icon: 'Monitor', permission: 'cmdb.dashboard.view' },
      { path: '/cmdb/ledger', visibilityKey: 'cmdb.ledger', title: '资产台账', icon: 'Collection', permission: 'cmdb.ci.view' },
      { path: '/cmdb/model', visibilityKey: 'cmdb.model', title: '分类视图', icon: 'SetUp', permission: 'cmdb.model.view' },
      { path: '/cmdb/topology', visibilityKey: 'cmdb.topology', title: '资产拓扑', icon: 'Share', permission: 'cmdb.model.view' },
      { path: '/cmdb/governance', visibilityKey: 'cmdb.governance', title: '资产治理', icon: 'Warning', permission: 'cmdb.ci.view' },
      { path: '/cmdb/cost', visibilityKey: 'cmdb.cost', title: '成本管理', icon: 'Coin', permission: 'cmdb.cost.view' },
      { path: '/cmdb/platform-config', visibilityKey: 'cmdb.platform-config', title: '平台配置', icon: 'SetUp', anyPermissions: ['cmdb.sync.view', 'cmdb.model.manage', 'cmdb.ipam.view'] },
      { path: '/cmdb/requests', visibilityKey: 'cmdb.requests', title: '资源运营', icon: 'Tickets', anyPermissions: ['cmdb.request.submit', 'cmdb.request.approve', 'cmdb.request.execute', 'cmdb.ci.view'] },
      { path: '/cmdb/thresholds', visibilityKey: 'cmdb.thresholds', title: '平台设置', icon: 'DocumentChecked', permission: 'cmdb.ci.view' },
      { path: '/cmdb/views', visibilityKey: 'cmdb.views', title: '视图展示', icon: 'DataBoard', permission: 'cmdb.ci.view' },
    ],
  },
  {
    moduleKey: 'aiops',
    title: 'AIOps',
    icon: 'ChatDotSquare',
    children: [
      { path: '/aiops/chat', visibilityKey: 'aiops.chat', title: '智能助手', icon: 'Service', permission: 'aiops.chat.view' },
      { path: '/aiops/knowledge', visibilityKey: 'aiops.knowledge', title: '知识图谱', icon: 'Share', permission: 'aiops.knowledge.view' },
      { path: '/aiops/config', visibilityKey: 'aiops.config', title: '智能体配置', icon: 'Tools', permission: 'aiops.config.view' },
      { path: '/aiops/audit', visibilityKey: 'aiops.audit', title: '智能体审计', icon: 'Tickets', permission: 'aiops.audit.view' },
    ],
  },
  {
    moduleKey: 'containers',
    title: '容器管理',
    icon: 'Box',
    children: [
      { path: '/containers/k8s', visibilityKey: 'containers.k8s', title: 'K8s 集群', icon: 'Connection', permission: 'ops.k8s.view' },
      { path: '/containers/docker', visibilityKey: 'containers.docker', title: 'Docker 环境', icon: 'Platform', permission: 'ops.docker.view' },
    ],
  },
  {
    moduleKey: 'observability',
    title: '可观测性',
    icon: 'DataLine',
    children: [
      { path: '/observability/boards', visibilityKey: 'observability.boards', title: '可视化', icon: 'DataLine', anyPermissions: observabilityBoardPermissions },
      { path: '/observability/metrics', visibilityKey: 'observability.metrics', title: '指标查询', icon: 'DataAnalysis', permission: 'ops.metric.query' },
      { path: '/observability/rum', visibilityKey: 'observability.rum', title: 'RUM', icon: 'Monitor', permission: 'ops.rum.view' },
      { path: '/logs/query', visibilityKey: 'observability.logs', title: '日志中心', icon: 'Search', permission: 'ops.log.query' },
      { path: '/observability/tracing', visibilityKey: 'observability.tracing', title: '链路追踪', icon: 'Connection', permission: 'ops.trace.view' },
      { path: '/observability/datasources', visibilityKey: 'observability.datasources', title: '数据源', icon: 'DataBoard', anyPermissions: ['ops.metric.datasource.view', 'ops.log.datasource.view', 'ops.trace.datasource.view', 'ops.observability.link.view'] },
      { path: '/alerts', visibilityKey: 'observability.alerts', title: '告警中心', icon: 'Bell', anyPermissions: ['ops.alert.view', 'ops.alert.config.view'] },
    ],
  },
  {
    moduleKey: 'events',
    title: '事件中心',
    icon: 'Tickets',
    children: [
      { path: '/events/wall', visibilityKey: 'events.wall', title: '事件中心', icon: 'Aim', permission: 'eventwall.view' },
      { path: '/events/environments', visibilityKey: 'events.environments', title: '事件环境', icon: 'CollectionTag', permission: 'eventwall.environment.view' },
      { path: '/events/sources', visibilityKey: 'events.sources', title: '事件源', icon: 'Share', permission: 'eventwall.source.view' },
    ],
  },
  {
    moduleKey: 'tasks',
    title: '任务中心',
    icon: 'Operation',
    children: [
      { path: '/tasks/workbench', visibilityKey: 'tasks.workbench', title: '任务工作台', icon: 'Operation', anyPermissions: ['ops.task.execute', 'ops.host.execute'] },
      { path: '/tasks/schedules', title: '计划任务', icon: 'Timer', hidden: !TASK_SCHEDULES_VISIBLE, anyPermissions: ['ops.host.schedule.view', 'ops.host.schedule.manage', 'ops.host.schedule.execute'] },
      { path: '/tasks/resources', visibilityKey: 'tasks.resources', title: '资源底座', icon: 'Monitor', anyPermissions: ['ops.task.resource.view', 'ops.task.resource.manage'] },
    ],
  },
  {
    moduleKey: 'workorders',
    title: '工单系统',
    icon: 'Tickets',
    children: [
      { path: '/workorders/releases', visibilityKey: 'workorders.releases', title: '应用发布', icon: 'Promotion', anyPermissions: ['ops.deployment.view', 'ops.deployment.manage', 'ops.deployment.approve'] },
      { path: '/workorders/sql', visibilityKey: 'workorders.sql', title: 'SQL 审计', icon: 'DataAnalysis', anyPermissions: ['sqlaudit.datasource.view', 'sqlaudit.order.view', 'sqlaudit.order.submit', 'sqlaudit.order.review', 'sqlaudit.order.execute', 'sqlaudit.query.view', 'sqlaudit.query.execute'] },
      { path: '/workorders/transactions', visibilityKey: 'workorders.transactions', title: '事务工单', icon: 'Tickets', anyPermissions: ['ops.ticket.view', 'ops.ticket.manage', 'ops.ticket.approve'] },
      { path: '/workorders/approval-flows', visibilityKey: 'workorders.approval-flows', title: '审批流', icon: 'Checked', anyPermissions: ['ops.deployment.view', 'ops.deployment.manage', 'ops.deployment.approve'] },
    ],
  },
  {
    moduleKey: 'cloudsecurity',
    title: '安全中心',
    icon: 'Lock',
    children: [
      { path: '/cloud-security/waf', visibilityKey: 'cloudsecurity.waf', title: 'WAF 防火墙', icon: 'Lock', permission: 'cloudsecurity.waf.view' },
      { path: '/security-center/internal-platform', visibilityKey: 'cloudsecurity.internal-platform', title: '内部平台安全', icon: 'DocumentChecked', permission: 'cloudsecurity.internal_platform.view' },
    ],
  },
  {
    moduleKey: 'system',
    title: '系统管理',
    icon: 'User',
    children: [
      { path: '/users', visibilityKey: 'system.users', title: '用户管理', icon: 'User', anyPermissions: ['rbac.user.view', 'rbac.role.view', 'rbac.group.view', 'rbac.permission.view'] },
      { path: '/users/audit', visibilityKey: 'system.audit', title: '操作审计', icon: 'DocumentChecked', permission: 'rbac.audit.view' },
      { path: '/users/modules', visibilityKey: 'system.modules', title: '系统设置', icon: 'Menu', permission: 'rbac.module.manage' },
    ],
  },
]

const observabilityBoardPaths = new Set([
  '/observability/boards',
  '/observability/grafana',
  ...(SYSTEM_POSTURE_ENABLED ? ['/observability/system-posture', '/observability/posture-history'] : []),
])
const observabilityQueryPaths = new Set([
  '/observability/query',
  '/observability/metrics',
  '/observability/rum',
  '/logs/query',
  '/observability/tracing',
])
const observabilityDatasourcePaths = new Set([
  '/observability/datasources',
  '/observability/metrics/datasources',
  '/logs/datasources',
  '/observability/tracing/datasources',
  '/observability/datasource-links',
])

const cmdbMenuPathMap = {
  '/cmdb': '/cmdb/overview',
  '/cmdb/overview': '/cmdb/overview',
  '/cmdb/views': '/cmdb/views',
  '/cmdb/ledger': '/cmdb/ledger',
  '/cmdb/platform-config': '/cmdb/platform-config',
  '/cmdb/topology': '/cmdb/topology',
  '/cmdb/repository': '/cmdb/model',
  '/cmdb/model': '/cmdb/model',
  '/cmdb/model/config': '/cmdb/platform-config',
  '/cmdb/model/topology': '/cmdb/topology',
  '/cmdb/sync': '/cmdb/platform-config',
  '/cmdb/ipam': '/cmdb/platform-config',
  '/cmdb/source-mappings': '/cmdb/platform-config',
  '/cmdb/requests': '/cmdb/requests',
  '/cmdb/governance': '/cmdb/governance',
  '/cmdb/cost': '/cmdb/cost',
  '/cmdb/authorization': '/cmdb/requests',
  '/cmdb/thresholds': '/cmdb/thresholds',
  '/cmdb/audit': '/cmdb/thresholds',
}


function canAccess(item) {
  if (item.permission) return authStore.hasPermission(item.permission)
  if (item.anyPermissions) return authStore.hasAnyPermission(item.anyPermissions)
  return true
}

function isModuleVisible(item) {
  const visibilityKey = item.visibilityKey || item.moduleKey
  if (!visibilityKey) return true
  return moduleVisibility.value[visibilityKey] !== false
}

function visibleChildren(items = []) {
  return items
    .filter(child => !child.hidden && isModuleVisible(child))
    .map((child) => {
      if (!child.children) return child
      const children = visibleChildren(child.children)
      return { ...child, children }
    })
    .filter((child) => child.children ? child.children.length > 0 : canAccess(child))
    .sort(compareMenuOrder)
}

function compareMenuOrder(first, second) {
  const firstOrder = moduleOrder.value.get(first.visibilityKey || first.moduleKey) ?? Number.MAX_SAFE_INTEGER
  const secondOrder = moduleOrder.value.get(second.visibilityKey || second.moduleKey) ?? Number.MAX_SAFE_INTEGER
  return firstOrder - secondOrder
}

const visibleMenuItems = computed(() => {
  if (!moduleSettingsLoaded.value) return []
  return menuItems
    .filter(isModuleVisible)
    .map((item) => {
      if (!item.children) return item
      const children = visibleChildren(item.children)
      return { ...item, children }
    })
    .filter((item) => item.children ? item.children.length > 0 : !item.hidden && canAccess(item))
    .sort(compareMenuOrder)
})

const normalizedMenuPath = computed(() => {
  if (route.path.startsWith('/sql')) {
    return '/sql'
  }
  if (route.path === '/cmdb' || route.path.startsWith('/cmdb/')) {
    if (route.path === '/cmdb/model/topology') return '/cmdb/topology'
    if (route.path === '/cmdb/model/config') return '/cmdb/platform-config'
    if (route.path.startsWith('/cmdb/model/')) return '/cmdb/model'
    return cmdbMenuPathMap[route.path] || '/cmdb/overview'
  }
  if (route.path.startsWith('/events/')) {
    return route.path
  }
  if (observabilityBoardPaths.has(route.path)) {
    return '/observability/boards'
  }
  if (observabilityQueryPaths.has(route.path) && route.query.tab !== 'datasources') {
    if (route.path === '/observability/query') return '/observability/metrics'
    return route.path
  }
  if (observabilityDatasourcePaths.has(route.path) || (route.path === '/observability/metrics' && route.query.tab === 'datasources') || (route.path === '/observability/tracing' && route.query.tab === 'datasources')) {
    return '/observability/datasources'
  }
  return route.path
})

const activeMenuPath = computed(() => {
  return normalizedMenuPath.value
})

const currentRoleLabel = computed(() => {
  const roles = authStore.currentUser?.roles || []
  if (!roles.length) return '无角色'
  return roles.map(role => role.name).join(' / ')
})

const primaryRoleLabel = computed(() => {
  const roles = authStore.currentUser?.roles || []
  if (!roles.length) return '访客'
  if (roles.length === 1) return roles[0].name
  return `${roles[0].name} +${roles.length - 1}`
})

const userInitials = computed(() => {
  const source = authStore.displayName || authStore.currentUser?.username || 'S'
  return source.slice(0, 1).toUpperCase()
})

const isAIOpsChatRoute = computed(() => route.name === 'AIOpsChat' || route.path === '/aiops/chat')
const showAIOpsChatLauncher = computed(() => (
  moduleSettingsLoaded.value && moduleVisibility.value['aiops.widget'] !== false
))

const notificationSections = computed(() => {
  const sectionOrder = ['approval', 'alert', 'event']
  const sectionTitleMap = {
    approval: '待审批清单',
    alert: '告警提醒',
    event: '关键事件',
  }
  const sectionRouteMap = {
    approval: '/workorders/releases',
    alert: '/alerts',
    event: '/events/wall',
  }
  return sectionOrder
    .map((key) => ({
      key,
      title: sectionTitleMap[key],
      route: sectionRouteMap[key],
      items: notificationItems.value.filter(item => item.section === key),
    }))
    .filter(section => section.items.length)
})

function formatDateTime(value) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function buildAlertNotificationItem(item) {
  const levelMap = {
    critical: { tag: '严重告警', tagType: 'danger' },
    warning: { tag: '告警提醒', tagType: 'warning' },
    info: { tag: '信息提醒', tagType: 'info' },
  }
  const meta = levelMap[item.level] || { tag: '平台提醒', tagType: 'info' }
  return {
    key: `alert-${item.id}`,
    section: 'alert',
    title: item.title || '告警中心通知',
    description: item.message || item.source || '请进入告警中心查看详情',
    time: item.created_at,
    route: '/alerts',
    tag: meta.tag,
    tagType: meta.tagType,
    dotTone: item.level === 'critical' ? 'danger' : item.level === 'warning' ? 'warning' : 'info',
    priority: item.level === 'critical' ? 3 : item.level === 'warning' ? 2 : 1,
  }
}

function buildDeploymentApprovalItem(item) {
  const nodeName = item.current_approval_step?.node_name || '默认审批'
  const scopeText = formatScopeText(item)
  return {
    key: `deploy-approval-${item.id}`,
    section: 'approval',
    title: `${item.app_name} / ${item.version}`,
    description: `${scopeText} · 发布审批待处理 · ${nodeName}`,
    time: item.deployed_at,
    route: '/workorders/releases',
    tag: '发布审批',
    tagType: 'warning',
    dotTone: 'warning',
    priority: 4,
  }
}

function buildTransactionApprovalItem(item) {
  const scopeText = formatScopeText(item)
  return {
    key: `transaction-approval-${item.id}`,
    section: 'approval',
    title: item.title || '事务工单待审批',
    description: `${scopeText} · 事务工单待处理 · ${item.type_display || '运维事务'}`,
    time: item.updated_at || item.created_at,
    route: '/workorders/transactions',
    tag: '事务审批',
    tagType: 'warning',
    dotTone: 'warning',
    priority: 4,
  }
}

function buildEventNotificationItem(item) {
  const resultToneMap = {
    failed: { tag: '高风险事件', tagType: 'danger', priority: 3 },
    partial: { tag: '待关注事件', tagType: 'warning', priority: 2 },
    pending: { tag: '待处理事件', tagType: 'warning', priority: 2 },
  }
  const meta = resultToneMap[item.result] || { tag: '平台动态', tagType: 'info', priority: 1 }
  return {
    key: `event-${item.id}`,
    section: 'event',
    title: item.title || '事件中心动态',
    description: item.summary || item.detail || item.resource_name || '请进入事件中心查看详情',
    time: item.occurred_at,
    route: '/events/wall',
    tag: meta.tag,
    tagType: meta.tagType,
    dotTone: item.result === 'failed' ? 'danger' : item.result === 'partial' || item.result === 'pending' ? 'warning' : 'info',
    priority: meta.priority,
  }
}

function formatScopeText(item) {
  const parts = []
  if (item?.system_name || item?.business_line) parts.push(item.system_name || item.business_line)
  if (item?.environment_display) {
    parts.push(item.environment_display)
  } else if (item?.environment) {
    parts.push(item.environment)
  }
  return parts.join(' / ') || '未指定系统 / 环境'
}

async function loadNotifications() {
  notificationsLoading.value = true
  try {
    const tasks = []
    if (authStore.hasPermission('ops.deployment.approve')) {
      tasks.push(getDeployments({ approval_status: 'pending' }))
    } else {
      tasks.push(Promise.resolve(null))
    }

    if (authStore.hasPermission('ops.ticket.approve')) {
      tasks.push(getTransactionTickets({ status: 'pending' }))
    } else {
      tasks.push(Promise.resolve(null))
    }

    if (authStore.hasPermission('ops.dashboard.view')) {
      tasks.push(getDashboardStats())
    } else {
      tasks.push(Promise.resolve(null))
    }

    if (authStore.hasPermission('eventwall.view')) {
      tasks.push(getEventWallAnalysis({ limit: 80 }))
    } else {
      tasks.push(Promise.resolve(null))
    }

    const [deploymentsResult, transactionTicketsResult, dashboardStatsResult, eventOverviewResult] = await Promise.allSettled(tasks)
    const deploymentsResponse = deploymentsResult.status === 'fulfilled' ? deploymentsResult.value : null
    const transactionTicketsResponse = transactionTicketsResult.status === 'fulfilled' ? transactionTicketsResult.value : null
    const dashboardStats = dashboardStatsResult.status === 'fulfilled' ? dashboardStatsResult.value : null
    const eventOverview = eventOverviewResult.status === 'fulfilled' ? eventOverviewResult.value : null

    const items = []
    let total = 0

    if (deploymentsResponse) {
      const deploymentItems = Array.isArray(deploymentsResponse.results) ? deploymentsResponse.results : (deploymentsResponse || [])
      const pendingDeploymentApprovals = deploymentItems.filter(canHandleDeploymentApproval)
      items.push(...pendingDeploymentApprovals.slice(0, 3).map(buildDeploymentApprovalItem))
      total += pendingDeploymentApprovals.length
    }

    if (transactionTicketsResponse) {
      const ticketItems = Array.isArray(transactionTicketsResponse.results) ? transactionTicketsResponse.results : (transactionTicketsResponse || [])
      items.push(...ticketItems.slice(0, 3).map(buildTransactionApprovalItem))
      total += ticketItems.length
    }

    if (dashboardStats) {
      const recentAlerts = Array.isArray(dashboardStats.recent_alerts) ? dashboardStats.recent_alerts : []
      items.push(...recentAlerts.slice(0, 4).map(buildAlertNotificationItem))
      total += Number(dashboardStats.alerts?.unacknowledged || 0)
    }

    if (eventOverview) {
      const priorityEvents = Array.isArray(eventOverview.suspects) ? eventOverview.suspects : []
      items.push(...priorityEvents.slice(0, 4).map(buildEventNotificationItem))
      total += priorityEvents.length
    }

    notificationItems.value = items
      .sort((left, right) => {
        if (right.priority !== left.priority) return right.priority - left.priority
        return new Date(right.time || 0).getTime() - new Date(left.time || 0).getTime()
      })
      .slice(0, 6)
    notificationCount.value = total
  } catch {
    notificationItems.value = []
    notificationCount.value = 0
  } finally {
    notificationsLoading.value = false
  }
}

function handleNoticeOpen() {
  if (!notificationItems.value.length && !notificationsLoading.value) {
    void loadNotifications()
  }
}

async function loadModuleSettings() {
  if (!authStore.isAuthenticated) return
  await authStore.reloadModuleSettings({ silent: true })
}

function openProductIntro() {
  router.push('/product')
}

function canHandleDeploymentApproval(item) {
  const step = item?.current_approval_step
  if (!step?.approver_type || !step?.approver_value) return authStore.hasPermission('ops.deployment.approve')
  if (step.approver_type === 'user') return authStore.currentUser?.username === step.approver_value
  if (step.approver_type === 'role') {
    return (authStore.currentUser?.roles || []).some(role => role.code === step.approver_value)
  }
  if (step.approver_type === 'group') {
    return (authStore.currentUser?.user_groups || []).some(group => group.code === step.approver_value)
  }
  return false
}

function goNotification(item) {
  if (!item?.route) return
  router.push(item.route)
}

function goSection(section) {
  if (!section?.route) return
  router.push(section.route)
}

async function handleUserCommand(command) {
  if (command === 'refresh') {
    await authStore.reloadProfile()
    ElMessage.success('权限已刷新')
    return
  }
  if (command === 'logout') {
    await authStore.logout()
    router.replace('/login')
  }
}

onMounted(() => {
  window.addEventListener(MODULE_SETTINGS_EVENT, loadModuleSettings)
  if (!authStore.moduleSettingsLoaded) {
    void loadModuleSettings()
  }
  void loadNotifications()
  notificationTimer = window.setInterval(() => {
    void loadNotifications()
  }, 60000)
})

onBeforeUnmount(() => {
  window.removeEventListener(MODULE_SETTINGS_EVENT, loadModuleSettings)
  if (notificationTimer) {
    window.clearInterval(notificationTimer)
    notificationTimer = null
  }
})
</script>

<style scoped>
.brand-mark {
  width: 24px;
  height: 24px;
  display: block;
  object-fit: contain;
}

.sidebar-logo .logo-text {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-footer {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 10px max(10px, env(safe-area-inset-bottom));
  border-top: 1px solid rgba(148, 163, 184, 0.1);
}

.sidebar-shortcuts {
  display: flex;
  align-items: center;
  justify-content: space-around;
  gap: 4px;
}

.sidebar-tool {
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.sidebar-tool:hover {
  color: #245bdb;
  border-color: rgba(96, 165, 250, 0.3);
  background: #ffffff;
}

.theme-option {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 154px;
  min-height: 34px;
  font-size: 13px;
}

.theme-option__swatch {
  width: 26px;
  height: 22px;
  flex: 0 0 auto;
  border: 1px solid light-dark(#94a3b8, #94a3b8);
  border-radius: 6px;
}

.theme-option__swatch--light {
  background: linear-gradient(90deg, light-dark(#e8eef7, #e8eef7) 30%, light-dark(#ffffff, #ffffff) 30%);
}

.theme-option__swatch--dark {
  background: linear-gradient(90deg, light-dark(#101722, #101722) 30%, light-dark(#26364b, #26364b) 30%);
}

.theme-option__swatch--charcoal {
  background: linear-gradient(90deg, light-dark(#181818, #181818) 30%, light-dark(#383838, #383838) 30%);
}

.theme-option__check {
  margin-left: auto;
  color: var(--primary);
}

.theme-option__hint {
  padding: 1px 4px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 10px;
  font-weight: 500;
  line-height: 16px;
}

.theme-option--active .theme-option {
  font-weight: 700;
}

.sidebar-tool:focus-visible,
.user-trigger:focus-visible {
  outline: 2px solid #6095ef;
  outline-offset: 2px;
}

.promo-trigger {
  color: #5b7fc7;
}

.notice-trigger :deep(.el-badge__content) {
  height: 16px;
  padding: 0 4px;
  font-size: 10px;
  line-height: 14px;
}

.sidebar.collapsed .sidebar-footer {
  align-items: center;
  padding-right: 8px;
  padding-left: 8px;
}

.sidebar.collapsed .sidebar-shortcuts {
  flex-direction: column;
}

.sidebar.collapsed .user-trigger {
  justify-content: center;
  padding: 6px;
}

.sidebar.collapsed .user-meta,
.sidebar.collapsed .user-menu-arrow {
  display: none;
}

.notice-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.notice-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.notice-panel__title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.notice-panel__subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}

.notice-groups {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 420px;
  overflow-y: auto;
  padding-right: 4px;
}

.notice-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.notice-group__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.notice-group__meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.notice-group__title {
  font-size: 12px;
  font-weight: 700;
  color: #475569;
}

.notice-group__count {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(226, 232, 240, 0.72);
  color: #64748b;
  font-size: 11px;
  line-height: 20px;
  text-align: center;
}

.notice-group__more {
  padding: 0;
  font-size: 12px;
}

.notice-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.notice-item {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 10px 10px 8px;
  border: 1px solid rgba(226, 232, 240, 0.72);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.92);
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
}

.notice-item:hover {
  border-color: rgba(148, 163, 184, 0.26);
  background: rgba(248, 250, 252, 0.96);
}

.notice-item__dot {
  width: 8px;
  height: 8px;
  margin-top: 6px;
  flex-shrink: 0;
  border-radius: 999px;
  background: #94a3b8;
}

.notice-item__dot.is-danger {
  background: #ef4444;
  box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.08);
}

.notice-item__dot.is-warning {
  background: #f59e0b;
  box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.08);
}

.notice-item__dot.is-info {
  background: #60a5fa;
  box-shadow: 0 0 0 4px rgba(96, 165, 250, 0.08);
}

.notice-item__body {
  min-width: 0;
  flex: 1;
}

.notice-item__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.notice-item__title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.notice-item__title {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
}

.notice-item__time {
  flex-shrink: 0;
  font-size: 11px;
  color: #94a3b8;
}

.notice-item__desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.55;
  color: #64748b;
}

.notice-empty {
  min-height: 120px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #94a3b8;
  font-size: 12px;
}

.menu-title-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.menu-title-row > span:first-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu-status-badge {
  flex: 0 0 auto;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.14);
  color: #64748b;
  font-size: 10px;
  line-height: 16px;
  font-weight: 700;
}

.sidebar.collapsed .menu-status-badge {
  display: none;
}

.sidebar-account {
  display: block;
  width: 100%;
}

.user-trigger {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 6px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.36);
  text-align: left;
  font: inherit;
  cursor: pointer;
  transition: background 0.2s ease;
}

.user-trigger:hover {
  background: #ffffff;
}

.user-menu-arrow {
  flex: 0 0 auto;
  margin-left: auto;
  color: #94a3b8;
  font-size: 12px;
}

.user-avatar {
  flex: 0 0 auto;
  background: linear-gradient(135deg, #72c1b5 0%, #5f90c1 58%, #506ba5 100%);
  color: #ffffff;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}

.fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.user-meta {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.user-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.user-role {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--text-secondary);
}

@media (max-width: 760px) {
  .sidebar-footer {
    align-items: center;
    padding-right: 8px;
    padding-left: 8px;
  }

  .sidebar-shortcuts {
    flex-direction: column;
  }

  .user-trigger {
    justify-content: center;
    padding: 6px;
  }

  .user-meta,
  .user-menu-arrow,
  .collapse-btn {
    display: none;
  }
}

</style>


