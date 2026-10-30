<template>
  <div class="observability-page">
    <section class="hero panel">
      <div class="hero-copy">
        <div class="hero-title-row">
          <span class="hero-icon">
            <el-icon><component :is="overviewHero.icon" /></el-icon>
          </span>
          <h2>{{ overviewHero.title }}</h2>
          <span class="hero-tagline">{{ overviewHero.description }}</span>
        </div>
      </div>
      <div class="hero-actions">
        <el-button size="small" @click="loadOverview" :loading="loading">
          <el-icon><RefreshRight /></el-icon>
          刷新
        </el-button>
      </div>
    </section>

    <div class="neo-tabs theme-blue log-center-tabs trace-center-tabs overview-center-tabs">
      <button
        v-if="canViewSystemPosture"
        class="neo-tab-btn"
        :class="{ active: activeOverviewTab === 'system-posture' }"
        @click="activeOverviewTab = 'system-posture'"
      >
        <el-icon><Aim /></el-icon>
        系统态势
      </button>
      <button
        v-if="canViewSystemPosture"
        class="neo-tab-btn"
        :class="{ active: activeOverviewTab === 'posture-history' }"
        @click="activeOverviewTab = 'posture-history'"
      >
        <el-icon><Calendar /></el-icon>
        态势历史
      </button>
      <button
        class="neo-tab-btn"
        :class="{ active: activeOverviewTab === 'capabilities' }"
        @click="activeOverviewTab = 'capabilities'"
      >
        <el-icon><Share /></el-icon>
        关联配置
      </button>
    </div>

    <section v-if="activeOverviewTab === 'capabilities'" class="capability-section">
      <div class="stats-grid release-stats dashboard-stats capability-card-grid">
        <div v-for="card in capabilityCards" :key="card.label" class="stat-card release-stat-card" :class="card.tone">
          <div class="stat-inline">
            <span class="stat-label">{{ card.label }}</span>
            <span class="stat-value">{{ card.value }}</span>
          </div>
        </div>
      </div>
    </section>

    <ObservabilitySystemPosture v-if="activeOverviewTab === 'system-posture' && canViewSystemPosture" embedded />
    <ObservabilityPostureHistory v-if="activeOverviewTab === 'posture-history' && canViewSystemPosture" embedded />
    <section v-if="activeOverviewTab === 'capabilities' && canViewLinks" class="panel">
      <div class="section-head">
        <h3>关联配置</h3>
        <el-tag size="small" type="success">日志 / 链路 / 看板</el-tag>
      </div>
      <ObservabilityDataSourceLinks embedded />
    </section>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Aim, Calendar, RefreshRight, Share } from '@element-plus/icons-vue'
import { getObservabilityOverview } from '@/api/modules/ops'
import { useAuthStore } from '@/stores/auth'
import { SYSTEM_POSTURE_ENABLED } from '@/config/features'
import ObservabilityDataSourceLinks from './ObservabilityDataSourceLinks.vue'
const ObservabilityPostureHistory = SYSTEM_POSTURE_ENABLED
  ? defineAsyncComponent(() => import('./ObservabilityPostureHistory.vue'))
  : null
const ObservabilitySystemPosture = SYSTEM_POSTURE_ENABLED
  ? defineAsyncComponent(() => import('./ObservabilitySystemPosture.vue'))
  : null

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const loading = ref(false)
const overview = ref({ modules: {}, summary: {} })
const canViewLinks = computed(() => authStore.hasPermission('ops.observability.link.view'))
const canViewSystemPosture = computed(() => SYSTEM_POSTURE_ENABLED && authStore.hasPermission('ops.observability.system_posture.view'))
const activeOverviewTab = ref(resolveOverviewTab(route.query.tab))

const overviewHero = computed(() => {
  if (activeOverviewTab.value === 'system-posture') {
    return {
      title: '系统态势',
      description: '按环境与系统聚合健康态势，结果导向定义系统 SLO，划清故障边界，快速定位异常节点、关键依赖与风险范围。',
      icon: Aim,
    }
  }
  if (activeOverviewTab.value === 'posture-history') {
    return {
      title: '态势历史',
      description: '以系统态势数据生成 Statuspage 风格历史视图，集中查看近期运行状态、组件可用性和影响事件。',
      icon: Calendar,
    }
  }
  return {
    title: '关联配置',
    description: '统一维护日志、链路、看板与告警的关联关系，为故障排查关联跳转和 AIOps 分析提供上下文。',
    icon: Share,
  }
})

const capabilityCards = computed(() => [
  {
    label: '监控看板',
    value: `看板数 ${overview.value.modules?.grafana?.dashboard_count || 0}`,
    tone: '',
  },
  {
    label: '日志中心',
    value: `数据源 ${overview.value.modules?.logs?.datasource_count || 0}`,
    tone: 'success-card',
  },
  {
    label: '链路追踪',
    value: `数据源 ${overview.value.modules?.tracing?.datasource_count || 0}`,
    tone: 'warning-card',
  },
  {
    label: '告警中心',
    value: `活跃告警 ${overview.value.modules?.alerts?.unacknowledged || 0}`,
    tone: 'danger-card',
  },
])

function resolveOverviewTab(tab) {
  if (tab === 'system-posture' && canViewSystemPosture.value) return 'system-posture'
  if (tab === 'posture-history' && canViewSystemPosture.value) return 'posture-history'
  if (tab === 'capabilities') return 'capabilities'
  return canViewSystemPosture.value ? 'system-posture' : 'capabilities'
}

watch(() => route.query.tab, (tab) => {
  activeOverviewTab.value = resolveOverviewTab(tab)
})

watch(activeOverviewTab, (tab) => {
  if (!tab || route.query.tab === tab) return
  router.replace({
    query: {
      ...route.query,
      tab,
    },
  })
})

watch(canViewSystemPosture, (canView) => {
  if (!canView && ['system-posture', 'posture-history'].includes(activeOverviewTab.value)) {
    activeOverviewTab.value = 'capabilities'
  }
})

async function loadOverview() {
  loading.value = true
  try {
    overview.value = await getObservabilityOverview()
  } finally {
    loading.value = false
  }
}

onMounted(loadOverview)
</script>

<style scoped>
.observability-page {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.panel {
  background: linear-gradient(180deg, #ffffff 0%, #fffdf8 100%);
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.04);
  padding: 12px 14px;
}

.hero,
.hero-copy,
.hero-title-row,
.hero-actions,
.section-head {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.hero-copy {
  gap: 4px;
}

.hero {
  align-items: center;
  justify-content: space-between;
}

.hero-actions {
  align-items: center;
}

.hero-actions :deep(.el-button) {
  border-radius: 10px;
  font-weight: 500;
  min-height: 32px;
  padding: 0 14px;
}

.hero-title-row {
  align-items: center;
  gap: 12px;
}

.hero-title-row h2 {
  font-size: 23px;
  line-height: 1.1;
  margin: 0;
}

.hero-tagline {
  color: #64748b;
  font-size: 13px;
  line-height: 1.45;
}

.hero-icon {
  align-items: center;
  background: linear-gradient(135deg, #0f766e, #2563eb);
  border-radius: 16px;
  color: #fff;
  display: inline-flex;
  height: 42px;
  justify-content: center;
  width: 42px;
}

.capability-section {
  display: block;
}

.overview-center-tabs {
  margin-bottom: 0;
  padding: 4px;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255,255,255,.96), rgba(248,250,252,.9));
  border: 1px solid rgba(148,163,184,.16);
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.04);
}

.overview-center-tabs .neo-tab-btn {
  min-height: 38px;
  padding: 0 20px;
  border-radius: 8px;
}

.overview-center-tabs.theme-blue .neo-tab-btn.active {
  color: #245bdb !important;
  background: rgba(51, 112, 255, 0.1) !important;
  box-shadow: inset 0 0 0 1px rgba(51, 112, 255, 0.08) !important;
}

.section-head {
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.section-head h3 {
  font-size: 14px;
  line-height: 1.3;
  margin: 0;
}

.capability-card-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 0;
}

.release-stat-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-shadow: 0 6px 18px rgba(31, 35, 41, 0.04);
  min-height: 68px;
  padding: 9px 11px;
  display: flex;
  align-items: center;
}

.success-card {
  background: linear-gradient(135deg, #dcfce7, #86efac);
}

.info-card {
  background: linear-gradient(135deg, #dbeafe, #93c5fd);
}

.warning-card {
  background: linear-gradient(135deg, #fef3c7, #fdba74);
}

.danger-card {
  background: linear-gradient(135deg, #fee2e2, #fca5a5);
}

.stat-inline {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.stat-label {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
}

.stat-value {
  color: #475569;
  font-size: 13px;
  font-weight: 500;
}

@media (max-width: 1200px) {
  .capability-card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .hero,
  .section-head {
    align-items: stretch;
    flex-direction: column;
  }

  .capability-card-grid {
    grid-template-columns: 1fr;
  }
}

.hero.panel {
  border-radius: 20px;
}
</style>
