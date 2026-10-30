<template>
  <div class="fade-in cost-manage-page workbench-page-shell">
    <section class="hero panel">
      <div class="cost-hero-title-row">
        <span class="cost-header-icon"><el-icon><Coin /></el-icon></span>
        <h2>成本管理</h2>
        <p class="page-inline-desc">按业务线和环境核对月度成本，跟进费用明细与优化动作。</p>
      </div>
    </section>

    <div class="neo-tabs theme-blue cost-tabs">
      <button
        v-for="item in tabs"
        :key="item.key"
        type="button"
        :class="{ active: activeTab === item.key }"
        @click="activeTab = item.key"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        {{ item.label }}
      </button>
    </div>

    <section class="workbench-card cost-content-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">{{ activeTabMeta.label }}</span>
          <span class="toolbar-desc">{{ activeTabMeta.desc }}</span>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history cost-filter-bar">
        <div class="workbench-toolbar-left">
          <el-date-picker
            v-model="filters.month"
            type="month"
            value-format="YYYY-MM"
            format="YYYY-MM"
            placeholder="选择月份"
            style="width: 150px"
            @change="refreshActiveTab"
          />
          <el-select
            v-if="activeTab === 'overview'"
            v-model="overviewAccount"
            clearable
            placeholder="全部云账号"
            style="width: 180px"
          >
            <el-option label="全部云账号" value="" />
            <el-option v-for="account in cloudAccountRows" :key="account.source_account" :label="account.source_account" :value="account.source_account" />
          </el-select>
          <el-select v-if="activeTab === 'tracking'" v-model="taskStatusFilter" clearable placeholder="全部处理状态" style="width: 150px">
            <el-option v-for="item in handlingStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>
        <div class="workbench-toolbar-right">
          <el-button v-if="canManageCost && activeTab !== 'tracking'" :loading="syncLoading" @click="syncAliyunCosts">同步云账号成本</el-button>
          <el-button :loading="activeTab === 'tracking' ? tasksLoading : loading" @click="refreshActiveTab">
            <el-icon><RefreshRight /></el-icon>
            {{ activeTab === 'tracking' ? '刷新跟进' : '刷新' }}
          </el-button>
        </div>
      </div>

      <template v-if="activeTab === 'overview'">
        <div v-loading="loading" class="cost-account-overview">
          <div class="cost-overview-head">
            <div>
              <strong>云账号费用分布</strong>
              <span>按云账号汇总，并拆分到每个资产类型。</span>
            </div>
            <el-tag size="small" type="info">{{ overviewCloudAccountRows.length }} 个账号</el-tag>
          </div>
          <el-empty v-if="!overviewCloudAccountRows.length && !loading" description="所选范围暂无成本记录" :image-size="64" />
          <template v-else>
            <div ref="costOverviewChartRef" class="cost-overview-chart" />
            <div class="cost-overview-details">
              <div class="cost-overview-details-head">
                <strong>费用构成明细</strong>
                <span>按云账号及资产类型汇总</span>
              </div>
              <el-table :data="costOverviewDetails" stripe size="small" class="cost-table" max-height="300">
                <el-table-column prop="source_account" label="云账号" min-width="180" show-overflow-tooltip />
                <el-table-column prop="type_name" label="资产类型" min-width="170" show-overflow-tooltip />
                <el-table-column prop="count" label="资产数" width="90" align="right" />
                <el-table-column label="月成本" width="150" align="right">
                  <template #default="{ row }"><strong>{{ formatMoney(row.total_cost) }}</strong></template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </div>
      </template>

      <template v-else-if="activeTab === 'details'">
        <div class="cost-detail-layout">
          <aside class="cost-rank-tree">
            <div class="cost-rank-tree-head">
              <strong>费用排行范围</strong>
              <span>按云账号与资产类型筛选</span>
            </div>
            <div class="cost-rank-tree-list">
              <button type="button" class="cost-rank-tree-node cost-rank-tree-node--root" :class="{ active: !costRankScope.key }" @click="selectCostRankScope()">
                <span>全部费用</span>
                <strong>{{ formatMoney(report.total_monthly_cost) }}</strong>
              </button>
              <div v-for="account in costRankTreeRows" :key="account.key" class="cost-rank-tree-group" :class="{ 'is-expanded': isCostAccountExpanded(account.key) }">
                <div class="cost-rank-tree-account-head">
                  <button type="button" class="cost-rank-tree-toggle" :aria-label="`${isCostAccountExpanded(account.key) ? '收起' : '展开'} ${account.label}`" @click="toggleCostAccount(account.key)">
                    <el-icon><ArrowDown v-if="isCostAccountExpanded(account.key)" /><ArrowRight v-else /></el-icon>
                  </button>
                  <button type="button" class="cost-rank-tree-node" :class="{ active: costRankScope.key === account.key }" @click="selectCostRankScope(account)">
                    <span>{{ account.label }}</span>
                    <strong>{{ formatMoney(account.total_cost) }}</strong>
                  </button>
                </div>
                <div v-if="isCostAccountExpanded(account.key)" class="cost-rank-tree-children">
                  <button v-for="type in account.children" :key="type.key" type="button" class="cost-rank-tree-node cost-rank-tree-node--child" :class="{ active: costRankScope.key === type.key }" @click="selectCostRankScope(type)">
                    <span>{{ type.label }}</span>
                    <strong>{{ formatMoney(type.total_cost) }}</strong>
                  </button>
                </div>
              </div>
            </div>
          </aside>
          <div class="cost-detail-main">
            <div class="cost-rank-result-head">
              <strong>{{ costRankScope.label || '全部费用' }}</strong>
              <span>按月成本从高到低排列</span>
            </div>
            <div class="workbench-toolbar workbench-toolbar--history cost-list-filter-bar">
              <div class="workbench-toolbar-left">
                <el-select v-model="filters.ciType" clearable filterable placeholder="资产模型" style="width: 150px" @change="fetchCostItems(true)">
                  <el-option v-for="item in ciTypes" :key="item.id" :label="item.name" :value="item.id" />
                </el-select>
                <el-input v-model="filters.search" clearable placeholder="搜索资产" style="width: 190px" @keyup.enter="fetchCostItems(true)" />
                <el-select v-model="filters.businessLine" clearable filterable placeholder="业务线" style="width: 130px" @change="fetchCostItems(true)">
                  <el-option v-for="item in businessLines" :key="item" :label="item" :value="item" />
                </el-select>
                <el-select v-model="filters.environment" clearable placeholder="环境" style="width: 110px" @change="fetchCostItems(true)">
                  <el-option v-for="item in environments" :key="item" :label="environmentText(item)" :value="item" />
                </el-select>
                <el-select v-model="filters.provider" clearable placeholder="成本来源" style="width: 145px" @change="fetchCostItems(true)">
                  <el-option v-for="item in providers" :key="item" :label="providerLabel(item)" :value="item" />
                </el-select>
              </div>
              <div class="workbench-toolbar-right"><el-button @click="resetDetailFilters">重置筛选</el-button></div>
            </div>
            <el-table v-loading="itemsLoading" :data="costItems" stripe class="cost-table" empty-text="所选条件下暂无成本记录">
              <el-table-column prop="name" label="资源" min-width="220" show-overflow-tooltip />
              <el-table-column prop="type_name" label="资产模型" min-width="140" show-overflow-tooltip />
              <el-table-column prop="business_line" label="业务线" min-width="130" show-overflow-tooltip />
              <el-table-column label="环境" width="88"><template #default="{ row }">{{ environmentText(row.environment) }}</template></el-table-column>
              <el-table-column label="成本来源" min-width="160" show-overflow-tooltip><template #default="{ row }">{{ providerLabel(row.provider) }}</template></el-table-column>
              <el-table-column label="月成本" width="150" align="right"><template #default="{ row }"><strong>{{ formatMoney(row.monthly_cost) }}</strong></template></el-table-column>
              <el-table-column label="操作" width="100" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openAsset(row)">资产详情</el-button></template></el-table-column>
            </el-table>
            <div class="cost-pagination">
              <el-pagination
                v-model:current-page="pagination.page"
                v-model:page-size="pagination.pageSize"
                :page-sizes="[20, 50, 100]"
                :total="pagination.total"
                layout="total, sizes, prev, pager, next"
                @size-change="fetchCostItems(true)"
                @current-change="fetchCostItems"
              />
            </div>
          </div>
        </div>
      </template>

      <template v-else-if="activeTab === 'optimization'">
        <div class="cost-detail-layout cost-detail-layout--suggestions">
          <aside class="cost-rank-tree">
            <div class="cost-rank-tree-head">
              <strong>建议范围</strong>
              <span>按云账号与资产类型筛选</span>
            </div>
            <div class="cost-rank-tree-list">
              <button type="button" class="cost-rank-tree-node cost-rank-tree-node--root" :class="{ active: !optimizationScope.key }" @click="selectOptimizationScope()">
                <span>全部建议</span>
                <strong>{{ suggestions.length }} 项</strong>
              </button>
              <div v-for="account in costRankTreeRows" :key="`optimization-${account.key}`" class="cost-rank-tree-group" :class="{ 'is-expanded': isOptimizationAccountExpanded(account.key) }">
                <div class="cost-rank-tree-account-head">
                  <button type="button" class="cost-rank-tree-toggle" :aria-label="`${isOptimizationAccountExpanded(account.key) ? '收起' : '展开'} ${account.label}`" @click="toggleOptimizationAccount(account.key)">
                    <el-icon><ArrowDown v-if="isOptimizationAccountExpanded(account.key)" /><ArrowRight v-else /></el-icon>
                  </button>
                  <button type="button" class="cost-rank-tree-node" :class="{ active: optimizationScope.key === account.key }" @click="selectOptimizationScope(account)">
                    <span>{{ account.label }}</span>
                    <strong>{{ optimizationSuggestionCount(account) }} 项</strong>
                  </button>
                </div>
                <div v-if="isOptimizationAccountExpanded(account.key)" class="cost-rank-tree-children">
                  <button v-for="type in account.children" :key="`optimization-${type.key}`" type="button" class="cost-rank-tree-node cost-rank-tree-node--child" :class="{ active: optimizationScope.key === type.key }" @click="selectOptimizationScope(type)">
                    <span>{{ type.label }}</span>
                    <strong>{{ optimizationSuggestionCount(type) }} 项</strong>
                  </button>
                </div>
              </div>
            </div>
          </aside>
          <div class="cost-detail-main">
            <div class="cost-rank-result-head">
              <strong>{{ optimizationScope.label || '全部建议' }}</strong>
              <span>预计节省 {{ formatMoney(filteredSuggestionsSaving) }}</span>
            </div>
            <div class="cost-panel cost-panel--suggestions">
          <div class="cost-panel-head"><strong>降本建议</strong><span>预计节省 {{ formatMoney(report.total_potential_saving) }}</span></div>
          <el-table v-loading="loading" :data="filteredSuggestions" stripe class="cost-table" empty-text="当前范围暂无降本建议">
              <el-table-column label="建议" min-width="250">
                <template #default="{ row }">
                  <div class="suggestion-cell">
                    <div><el-tag size="small" :type="suggestionTagType(row.severity)">{{ suggestionTypeLabel(row.type) }}</el-tag><strong>{{ row.title }}</strong></div>
                    <span>{{ row.detail }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="判断依据" min-width="220">
                <template #default="{ row }">
                  <div class="suggestion-cell suggestion-cell--reason">
                    <strong>{{ row.evidence || '暂无采集依据' }}</strong>
                    <span>{{ row.action }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="成本影响" width="135" align="right">
                <template #default="{ row }">
                  <strong>{{ formatMoney(row.potential_saving) }}</strong>
                  <span class="suggestion-saving-label">可节省</span>
                </template>
              </el-table-column>
              <el-table-column label="处理状态" min-width="150">
                <template #default="{ row }">
                  <div class="handling-cell">
                    <el-tag size="small" :type="handlingStatusTagType(row.handling?.status)">{{ handlingStatusLabel(row.handling?.status) }}</el-tag>
                    <span v-if="row.handling?.owner">{{ row.handling.owner }} 认领</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column v-if="canManageCost" label="操作" width="88" fixed="right">
                <template #default="{ row }">
                  <el-button v-if="row.handling?.status === 'unclaimed'" link type="primary" @click="claimSuggestion(row)">认领</el-button>
                  <el-button v-else link type="primary" @click="activeTab = 'tracking'">跟进</el-button>
                </template>
              </el-table-column>
          </el-table>
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="cost-tracking-shell">
          <el-table v-loading="tasksLoading" :data="filteredOptimizationTasks" stripe class="cost-table" empty-text="当前月份暂未认领成本优化事项">
            <el-table-column label="优化事项" min-width="260" show-overflow-tooltip>
              <template #default="{ row }">
                <div class="suggestion-cell">
                  <div><el-tag size="small" type="info">{{ suggestionTypeLabel(row.suggestion_type) }}</el-tag><strong>{{ row.suggestion_title }}</strong></div>
                  <span>{{ row.ci_name }} · {{ row.ci_type || '未标注模型' }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="owner" label="认领人" width="115" show-overflow-tooltip />
            <el-table-column label="处理状态" width="120">
              <template #default="{ row }"><el-tag size="small" :type="handlingStatusTagType(row.status)">{{ row.status_display || handlingStatusLabel(row.status) }}</el-tag></template>
            </el-table-column>
            <el-table-column label="进展" width="115">
              <template #default="{ row }">
                <span>{{ row.latest_progress?.progress_percent ?? 0 }}%</span>
                <span class="task-progress-note">{{ row.latest_progress?.note || '暂无进展说明' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="月度节省" width="145" align="right">
              <template #default="{ row }">
                <strong>{{ formatMoney(row.actual_monthly_saving ?? row.expected_monthly_saving) }}</strong>
                <span class="suggestion-saving-label">{{ row.actual_monthly_saving === null ? '预估' : '已确认' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="更新时间" width="165">
              <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
            </el-table-column>
            <el-table-column v-if="canManageCost" label="操作" width="78" fixed="right">
              <template #default="{ row }"><el-button link type="primary" @click="openProgressDialog(row)">更新</el-button></template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </section>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="progressDialogVisible" title="更新处理进展" width="540px" append-to-body destroy-on-close>
      <el-form label-position="top" label-width="82px" class="cost-progress-form">
        <el-form-item label="处理状态">
          <el-select v-model="progressForm.status" style="width:100%">
            <el-option v-for="item in handlingStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="完成度">
          <el-input-number v-model="progressForm.progress_percent" :min="0" :max="100" controls-position="right" style="width:160px" />
          <span class="form-suffix">%</span>
        </el-form-item>
        <el-form-item label="实际月节省">
          <el-input-number v-model="progressForm.actual_monthly_saving" :min="0" :precision="2" controls-position="right" style="width:190px" />
          <span class="form-suffix">元</span>
        </el-form-item>
        <el-form-item label="进展说明">
          <el-input v-model="progressForm.note" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="记录当前处理动作、阻塞项或结论" />
        </el-form-item>
      </el-form>
      <div v-if="selectedTask?.progress_entries?.length" class="progress-history">
        <strong>处理记录</strong>
        <div v-for="entry in selectedTask.progress_entries" :key="entry.id" class="progress-history-row">
          <div><el-tag size="small" :type="handlingStatusTagType(entry.status)">{{ entry.status_display || handlingStatusLabel(entry.status) }}</el-tag><span>{{ entry.progress_percent }}%</span><span>{{ entry.created_by || '-' }}</span></div>
          <p>{{ entry.note || '未填写说明' }}</p>
          <time>{{ formatTime(entry.created_at) }}</time>
        </div>
      </div>
      <template #footer>
        <el-button @click="progressDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="progressSaving" @click="saveTaskProgress">保存进展</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="assetDetailVisible" :title="assetDetail?.name || '配置项详情'" size="760px" append-to-body destroy-on-close>
      <div v-loading="assetDetailLoading" class="ci-detail-shell">
        <template v-if="assetDetail">
          <div class="detail-heading">
            <div class="detail-heading-main">
              <div class="detail-title-row">
                <strong class="detail-main-title" :title="assetDetail.name">{{ assetDetail.name }}</strong>
                <el-tag size="small" :type="statusTagType(assetDetail.status)">{{ assetDetail.status_display || assetDetail.status || '-' }}</el-tag>
                <el-tag size="small" type="info" effect="plain">{{ assetDetail.ci_type_name || selectedCostItem?.type_name || '未标注资产类型' }}</el-tag>
              </div>
            </div>
          </div>
          <div class="detail-grid">
            <section class="detail-section">
              <div class="detail-section-title">基础信息</div>
              <div class="compact-stack">
                <div class="detail-kv">资产 ID：{{ assetDetail.id }}</div>
                <div class="detail-kv">状态：{{ assetDetail.status_display || assetDetail.status || '-' }}</div>
                <div class="detail-kv">业务线：{{ assetDetail.business_line || '-' }}</div>
                <div class="detail-kv">环境：{{ assetDetail.environment_display || environmentText(assetDetail.environment) }}</div>
                <div class="detail-kv">部门：{{ assetDetail.attributes?.department || '-' }}</div>
                <div class="detail-kv">负责人：{{ assetDetail.admin_user || '-' }}</div>
                <div class="detail-kv">关系数：{{ assetDetail.relation_count || 0 }}</div>
                <div class="detail-kv">当月成本：<strong>{{ costDetailMonthlyCostText }}</strong></div>
                <div class="detail-kv detail-kv--full">更新时间：{{ formatTime(assetDetail.updated_at) }}</div>
                <div class="detail-kv">采集来源：{{ assetDetailSourceText }}</div>
                <div class="detail-kv detail-kv--full">描述：{{ assetDetail.attributes?.description || '-' }}</div>
              </div>
              <div class="detail-tag-list">
                <span v-for="tag in assetDetail.tag_items || []" :key="tag.id" class="tag-chip" :style="{ borderColor: tag.color || '#dbe4f0', color: tag.color || '#245bdb' }">{{ tag.name }}</span>
                <span v-if="!(assetDetail.tag_items || []).length" class="sub-text">暂无标签</span>
              </div>
            </section>
            <section class="detail-section">
              <div class="detail-section-title">模型字段</div>
              <div v-if="assetDetailDisplayFields.length" class="field-value-list">
                <div v-for="field in assetDetailDisplayFields" :key="field.id || field.code" class="field-value-row">
                  <span>{{ field.name }}</span>
                  <strong>{{ formatValue(assetDetail.attributes?.[field.code]) }}</strong>
                </div>
              </div>
              <el-empty v-else description="暂无字段定义" :image-size="58" />
            </section>
          </div>
          <section class="detail-section detail-section--cost">
            <div class="detail-section-head">
              <div class="detail-section-title">成本</div>
            </div>
            <div class="cost-detail-summary">
              <el-tag size="small" :type="providerTagType(selectedCostItem?.provider)">{{ providerLabel(selectedCostItem?.provider) }}</el-tag>
              <div class="cost-detail-value cost-detail-value--primary">
                <span>{{ filters.month }} 月成本</span>
                <strong>{{ formatMoney(selectedCostItem?.monthly_cost) }}</strong>
              </div>
            </div>
          </section>
          <section v-if="assetWaterlineRows.length" class="detail-section">
            <div class="detail-section-head"><div class="detail-section-title">资产水位</div><el-tag size="small" type="info">最新采集</el-tag></div>
            <el-table :data="assetWaterlineRows" stripe class="cost-table detail-table">
              <el-table-column label="指标" width="100"><template #default="{ row }">{{ metricLabel(row.metric) }}</template></el-table-column>
              <el-table-column label="当前值" width="142"><template #default="{ row }">{{ formatMetricValue(row) }}</template></el-table-column>
              <el-table-column label="使用率" width="100" align="right"><template #default="{ row }">{{ row.usage_percent === null || row.usage_percent === undefined ? '-' : formatPercent(row.usage_percent) }}</template></el-table-column>
              <el-table-column label="采集来源" width="130" prop="source" show-overflow-tooltip />
              <el-table-column label="采集时间" width="150" align="right"><template #default="{ row }">{{ formatTime(row.collected_at) }}</template></el-table-column>
            </el-table>
          </section>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ArrowDown, ArrowRight, Coin, DataAnalysis, Finished, List, RefreshRight } from '@element-plus/icons-vue'
import echarts from '@/lib/echarts'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import {
  getCITypes,
  getConfigItem,
  getCmdbCostItems,
  getCmdbCostReport,
  getCmdbOptimization,
  getCmdbOptimizationTasks,
  claimCmdbOptimizationTask,
  syncCmdbAliyunCosts,
  updateCmdbOptimizationTaskProgress,
} from '@/api/modules/cmdb'

const authStore = useAuthStore()
const loading = ref(false)
const itemsLoading = ref(false)
const syncLoading = ref(false)
const tasksLoading = ref(false)
const progressSaving = ref(false)
const report = ref({})
const optimization = ref({})
const optimizationTasks = ref([])
const costItems = ref([])
const ciTypes = ref([])
const assetDetailVisible = ref(false)
const assetDetailLoading = ref(false)
const assetDetail = ref(null)
const selectedCostItem = ref(null)
const selectedTask = ref(null)
const progressDialogVisible = ref(false)
const activeTab = ref('overview')
const costRankScope = ref({})
const expandedCostAccounts = ref({})
const optimizationScope = ref({})
const expandedOptimizationAccounts = ref({})
const overviewAccount = ref('')
const taskStatusFilter = ref('')
const progressForm = reactive({ status: 'in_progress', progress_percent: 0, actual_monthly_saving: undefined, note: '' })
const costOverviewChartRef = ref(null)
let costOverviewChart = null
const costDataCache = new Map()
const COST_CACHE_TTL = 5 * 60 * 1000
const COST_CACHE_PREFIX = 'cmdb-cost-summary:v4:'
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
const filters = reactive({
  month: currentMonth(),
  search: '',
  ciType: '',
  businessLine: '',
  environment: '',
  provider: '',
  sourceAccount: '',
})

const tabs = [
  { key: 'overview', label: '成本概览', desc: '汇总当前业务范围的成本，并核对各资产类型的费用构成。', icon: DataAnalysis },
  { key: 'details', label: '费用明细', desc: '查看当前业务范围内的月成本 Top 排行，可按业务线、环境和资产类型筛选。', icon: List },
  { key: 'optimization', label: '优化建议', desc: '保留可执行的降本建议，并展示对应的资源水位依据。', icon: Coin },
  { key: 'tracking', label: '处理跟进', desc: '集中查看已认领事项、处理进展和已确认的节省效果。', icon: Finished },
]
const activeTabMeta = computed(() => tabs.find(item => item.key === activeTab.value) || tabs[0])
const canManageCost = computed(() => authStore.hasPermission('cmdb.cost.manage'))
const environmentRows = computed(() => listOf(report.value.by_environment))
const providerRows = computed(() => listOf(report.value.by_provider))
const cloudAccountRows = computed(() => listOf(report.value.by_cloud_account))
const overviewCloudAccountRows = computed(() => overviewAccount.value
  ? cloudAccountRows.value.filter(item => item.source_account === overviewAccount.value)
  : cloudAccountRows.value)
const businessLines = computed(() => listOf(report.value.by_business).map(item => item.business_line).filter(item => item && item !== '未归类'))
const environments = computed(() => environmentRows.value.map(item => item.environment).filter(Boolean))
const providers = computed(() => providerRows.value.map(item => item.provider).filter(Boolean))
const suggestions = computed(() => listOf(optimization.value.suggestions || report.value.recommendations_preview))
const handlingStatusOptions = [
  { value: 'claimed', label: '已认领' },
  { value: 'in_progress', label: '处理中' },
  { value: 'completed', label: '已完成' },
  { value: 'deferred', label: '暂缓处理' },
  { value: 'rejected', label: '不采纳' },
]
const filteredOptimizationTasks = computed(() => optimizationTasks.value.filter(item => !taskStatusFilter.value || item.status === taskStatusFilter.value))
const filteredSuggestions = computed(() => suggestions.value.filter((item) => {
  if (optimizationScope.value.sourceAccount && item.source_account !== optimizationScope.value.sourceAccount) return false
  if (optimizationScope.value.ciType && Number(item.ci_type_id) !== Number(optimizationScope.value.ciType)) return false
  return true
}))
const filteredSuggestionsSaving = computed(() => filteredSuggestions.value.reduce((total, item) => total + Number(item.potential_saving || 0), 0))
const costOverviewDetails = computed(() => overviewCloudAccountRows.value.flatMap(account => listOf(account.by_type).map(type => ({
  source_account: account.source_account,
  ...type,
}))))
const costRankTreeRows = computed(() => cloudAccountRows.value.map((account) => ({
  key: `account:${account.source_account}`,
  label: account.source_account,
  sourceAccount: account.source_account,
  total_cost: account.total_cost,
  children: listOf(account.by_type).map(type => ({
    key: `account:${account.source_account}:type:${type.type_id}`,
    label: type.type_name,
    sourceAccount: account.source_account,
    ciType: type.type_id,
    total_cost: type.total_cost,
  })),
})))
const optimizationCountByScope = computed(() => {
  const counts = new Map()
  listOf(optimization.value.by_cloud_account).forEach((account) => {
    const accountKey = String(account.source_account || '').trim()
    if (!accountKey) return
    counts.set(`account:${accountKey}`, Number(account.count || 0))
    listOf(account.by_type).forEach((type) => {
      counts.set(`account:${accountKey}:type:${Number(type.type_id)}`, Number(type.count || 0))
    })
  })
  return counts
})
const assetDetailDisplayFields = computed(() => {
  const fields = assetDetail.value?.field_definitions || []
  return fields.filter(field => !['department', 'monthly_cost', 'cost_center'].includes(field.code))
})
const assetWaterlineRows = computed(() => Array.isArray(assetDetail.value?.latest_metric_snapshots) ? assetDetail.value.latest_metric_snapshots : [])
const assetDetailSourceText = computed(() => {
  const sourceAccount = selectedCostItem.value?.source_account || assetDetail.value?.attributes?.source_account
  const sourceRegion = selectedCostItem.value?.source_region || assetDetail.value?.attributes?.source_region
  return [sourceAccount, sourceRegion].filter(Boolean).join(' / ') || '未标注'
})
const costDetailMonthlyCostText = computed(() => {
  if (selectedCostItem.value?.monthly_cost === null || selectedCostItem.value?.monthly_cost === undefined) return '-'
  const amount = formatMoney(selectedCostItem.value.monthly_cost)
  return selectedCostItem.value?.provider === 'aliyun' ? `预估 ${amount}` : amount
})

function currentMonth() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function listOf(value) {
  return Array.isArray(value) ? value : value?.results || []
}

function readCostCache(month) {
  const memoryEntry = costDataCache.get(month)
  if (memoryEntry && Date.now() - memoryEntry.cachedAt < COST_CACHE_TTL) return memoryEntry
  try {
    const entry = JSON.parse(sessionStorage.getItem(`${COST_CACHE_PREFIX}${month}`) || 'null')
    if (entry && Date.now() - entry.cachedAt < COST_CACHE_TTL) {
      costDataCache.set(month, entry)
      return entry
    }
  } catch {}
  return null
}

function writeCostCache(month, entry) {
  costDataCache.set(month, entry)
  try {
    sessionStorage.setItem(`${COST_CACHE_PREFIX}${month}`, JSON.stringify(entry))
  } catch {}
}

function formatMoney(value) {
  return `¥${Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`
}

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function formatValue(value) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.join('、') || '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function metricLabel(metric) {
  return { cpu_usage: 'CPU', memory_usage: '内存', disk_usage: '磁盘', storage_usage: '存储' }[metric] || metric || '-'
}

function formatMetricValue(row) {
  if (row?.value === null || row?.value === undefined || row?.value === '') return '-'
  return `${row.value}${row.unit ? ` ${row.unit}` : ''}`
}

function statusTagType(value) {
  if (value === 'active' || value === 'online') return 'success'
  if (value === 'idle') return 'warning'
  if (value === 'offline' || value === 'decommissioned') return 'info'
  return 'info'
}

function environmentText(value) {
  return { prod: '生产', pre: '预发', test: '测试', dev: '开发' }[value] || value || '未标注'
}

function providerLabel(value) {
  const provider = String(value || '').trim()
  const normalizedProvider = ['\\u672a\\u6807\\u8bb0', '\\u672a\\u6807\\u6ce8'].includes(provider) ? 'manual' : (provider || 'manual')
  return {
    aliyun: '阿里云按量付费',
    aliyun_subscription: '阿里云包年包月均摊',
    manual: '手工维护',
  }[normalizedProvider] || normalizedProvider
}

function suggestionTypeLabel(value) {
  return {
    reclaim: '资源回收',
    schedule: '定时启停',
    downsize: '规格缩容',
    storage: '存储优化',
  }[value] || value || '优化建议'
}

function suggestionTagType(value) {
  if (value === 'danger') return 'danger'
  if (value === 'warning') return 'warning'
  if (value === 'success') return 'success'
  return 'info'
}

function handlingStatusLabel(value) {
  if (value === 'unclaimed') return '待认领'
  return handlingStatusOptions.find(item => item.value === value)?.label || value || '待认领'
}

function handlingStatusTagType(value) {
  if (value === 'completed') return 'success'
  if (value === 'in_progress') return 'primary'
  if (value === 'claimed' || value === 'deferred') return 'warning'
  if (value === 'rejected') return 'info'
  return 'info'
}

function providerTagType(value) {
  if (value === 'aliyun') return 'success'
  if (value === 'aliyun_subscription') return 'primary'
  return 'info'
}

async function fetchCostItems(resetPage = false) {
  if (resetPage === true) pagination.page = 1
  itemsLoading.value = true
  try {
    const response = await getCmdbCostItems({
      month: filters.month,
      search: filters.search || undefined,
      ci_type: filters.ciType || undefined,
      business_line: filters.businessLine || undefined,
      environment: filters.environment || undefined,
      provider: filters.provider || undefined,
      source_account: filters.sourceAccount || undefined,
      page: pagination.page,
      page_size: pagination.pageSize,
    })
    costItems.value = listOf(response)
    pagination.total = Number(response?.count || 0)
  } finally {
    itemsLoading.value = false
  }
}

async function fetchOptimizationTasks() {
  tasksLoading.value = true
  try {
    optimizationTasks.value = listOf(await getCmdbOptimizationTasks({ month: filters.month }))
  } finally {
    tasksLoading.value = false
  }
}

async function claimSuggestion(row) {
  try {
    await claimCmdbOptimizationTask({
      month: filters.month,
      ci_id: row.ci_id,
      suggestion_type: row.type,
    })
    ElMessage.success('已认领，后续请在处理跟进中更新进展')
    await Promise.all([refreshCosts(true), fetchOptimizationTasks()])
  } catch (error) {
    if (error?.response?.status === 409) ElMessage.warning(error.response.data?.detail || '该建议已被其他成员认领')
    else throw error
  }
}

function openProgressDialog(row) {
  selectedTask.value = row
  Object.assign(progressForm, {
    status: row.status || 'in_progress',
    progress_percent: row.latest_progress?.progress_percent ?? 0,
    actual_monthly_saving: row.actual_monthly_saving ?? undefined,
    note: '',
  })
  progressDialogVisible.value = true
}

async function saveTaskProgress() {
  if (!selectedTask.value?.id) return
  progressSaving.value = true
  try {
    const task = await updateCmdbOptimizationTaskProgress(selectedTask.value.id, {
      status: progressForm.status,
      progress_percent: progressForm.progress_percent,
      actual_monthly_saving: progressForm.actual_monthly_saving,
      note: progressForm.note,
    })
    selectedTask.value = task
    ElMessage.success('处理进展已更新')
    await Promise.all([fetchOptimizationTasks(), refreshCosts(true)])
  } finally {
    progressSaving.value = false
  }
}

async function refreshCosts(force = false) {
  loading.value = true
  try {
    const params = { month: filters.month }
    const cacheEntry = force ? null : readCostCache(filters.month)
    if (cacheEntry) {
      report.value = cacheEntry.report
      optimization.value = cacheEntry.optimization
    } else {
      const [reportResult, optimizationResult] = await Promise.all([
        getCmdbCostReport(params),
        getCmdbOptimization(params),
      ])
      report.value = reportResult || {}
      optimization.value = optimizationResult || {}
      writeCostCache(filters.month, {
        report: report.value,
        optimization: optimization.value,
        cachedAt: Date.now(),
      })
    }
    if (activeTab.value === 'details') await fetchCostItems()
    if (activeTab.value === 'tracking') await fetchOptimizationTasks()
    await nextTick()
    renderCostOverviewChart()
  } finally {
    loading.value = false
  }
}

async function refreshActiveTab() {
  if (activeTab.value === 'tracking') {
    await fetchOptimizationTasks()
    return
  }
  await refreshCosts(true)
}

function resetDetailFilters() {
  Object.assign(filters, { search: '', ciType: '', businessLine: '', environment: '', provider: '', sourceAccount: '' })
  costRankScope.value = {}
  fetchCostItems(true)
}

function selectCostRankScope(scope = null) {
  costRankScope.value = scope || {}
  filters.sourceAccount = scope?.sourceAccount || ''
  filters.ciType = scope?.ciType || ''
  fetchCostItems(true)
}

function isCostAccountExpanded(key) {
  return expandedCostAccounts.value[key] !== false
}

function toggleCostAccount(key) {
  expandedCostAccounts.value = {
    ...expandedCostAccounts.value,
    [key]: !isCostAccountExpanded(key),
  }
}

function selectOptimizationScope(scope = null) {
  optimizationScope.value = scope || {}
}

function optimizationSuggestionCount(scope) {
  if (scope?.key && optimizationCountByScope.value.has(scope.key)) {
    return optimizationCountByScope.value.get(scope.key)
  }
  return suggestions.value.filter((item) => {
    if (scope?.sourceAccount && String(item.source_account || '').trim() !== String(scope.sourceAccount).trim()) return false
    if (scope?.ciType && Number(item.ci_type_id) !== Number(scope.ciType)) return false
    return true
  }).length
}

function isOptimizationAccountExpanded(key) {
  return expandedOptimizationAccounts.value[key] !== false
}

function toggleOptimizationAccount(key) {
  expandedOptimizationAccounts.value = {
    ...expandedOptimizationAccounts.value,
    [key]: !isOptimizationAccountExpanded(key),
  }
}

function renderCostOverviewChart() {
  if (!costOverviewChartRef.value) return
  if (costOverviewChart && costOverviewChart.getDom() !== costOverviewChartRef.value) {
    costOverviewChart.dispose()
    costOverviewChart = null
  }
  if (!costOverviewChart) costOverviewChart = echarts.init(costOverviewChartRef.value)
  const accountData = overviewCloudAccountRows.value.map(item => ({ name: item.source_account || '未标注账号', value: Number(item.total_cost || 0) }))
  const typeTotals = new Map()
  costOverviewDetails.value.forEach((item) => {
    typeTotals.set(item.type_name, (typeTotals.get(item.type_name) || 0) + Number(item.total_cost || 0))
  })
  const typeData = Array.from(typeTotals, ([name, value]) => ({ name: name || '未标注类型', value }))
  const overviewTotal = accountData.reduce((total, item) => total + item.value, 0)
  const tooltip = {
    trigger: 'item',
    valueFormatter: value => formatMoney(value),
  }
  const pie = (name, data, center) => ({
    name,
    type: 'pie',
    radius: ['44%', '70%'],
    center,
    avoidLabelOverlap: true,
    itemStyle: { borderColor: '#fff', borderWidth: 3, borderRadius: 5 },
    label: { color: '#475569', fontSize: 12, formatter: '{b}\n{d}%' },
    labelLine: { length: 10, length2: 8 },
    data,
  })
  costOverviewChart.setOption({
    color: ['#245bdb', '#4f8cff', '#36a9a1', '#f59e0b', '#8b5cf6', '#ef6b73', '#64748b'],
    tooltip,
    title: [
      { text: '云账号', subtext: formatMoney(overviewTotal), left: '25%', top: '43%', textAlign: 'center', textStyle: { color: '#0f172a', fontSize: 14, fontWeight: 700 }, subtextStyle: { color: '#64748b', fontSize: 12 } },
      { text: '资产类型', subtext: `${typeData.length} 类`, left: '75%', top: '43%', textAlign: 'center', textStyle: { color: '#0f172a', fontSize: 14, fontWeight: 700 }, subtextStyle: { color: '#64748b', fontSize: 12 } },
    ],
    series: [pie('云账号成本', accountData, ['25%', '52%']), pie('资产类型成本', typeData, ['75%', '52%'])],
  }, true)
  costOverviewChart.resize()
}

function resizeCostOverviewChart() {
  costOverviewChart?.resize()
}

async function syncAliyunCosts() {
  syncLoading.value = true
  try {
    const result = await syncCmdbAliyunCosts({ month: filters.month, history_months: 12 })
    const failedCount = Number(result?.failed_count || 0)
    const message = `按量 ${Number(result?.updated_count || 0)} 项，包年包月均摊 ${Number(result?.subscription_updated_count || 0)} 项。`
    if (failedCount) ElMessage.warning(`阿里云成本同步完成：${message}${failedCount} 个账号未完成。`)
    else ElMessage.success(`阿里云成本已同步：${message}`)
    await refreshCosts(true)
  } finally {
    syncLoading.value = false
  }
}

async function openAsset(row) {
  const ciId = row?.ci_id || row?.id
  if (!ciId) return
  selectedCostItem.value = { ...row, ci_id: ciId }
  assetDetail.value = { id: ciId, name: row.name, ci_type_name: row.type_name || row.ci_type_name }
  assetDetailVisible.value = true
  assetDetailLoading.value = true
  try {
    assetDetail.value = await getConfigItem(ciId)
  } catch {
    ElMessage.warning('资产详情加载失败，请稍后重试')
  } finally {
    assetDetailLoading.value = false
  }
}

onMounted(async () => {
  const [typesResult] = await Promise.all([getCITypes(), refreshCosts()])
  ciTypes.value = listOf(typesResult)
  window.addEventListener('resize', resizeCostOverviewChart)
})

watch(activeTab, async (tab) => {
  if (tab === 'details' && !costItems.value.length) await fetchCostItems()
  if (tab === 'tracking') await fetchOptimizationTasks()
  if (tab === 'overview') {
    await nextTick()
    renderCostOverviewChart()
  }
})

watch(overviewAccount, async () => {
  await nextTick()
  renderCostOverviewChart()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCostOverviewChart)
  costOverviewChart?.dispose()
  costOverviewChart = null
})
</script>

<style scoped>
.cost-manage-page{display:flex;flex-direction:column;gap:6px}
.hero.panel{padding:14px 16px;border:1px solid rgba(36,91,219,.09);border-radius:20px;background:linear-gradient(135deg,#fbfdff 0%,#f7faff 52%,#f9fbfd 100%)}
.cost-hero-title-row{display:flex;align-items:center;gap:10px;min-width:0}.cost-hero-title-row h2{margin:0;color:#0f172a;font-size:20px;line-height:1.3}.page-inline-desc{margin:0;color:#64748b;font-size:13px;line-height:1.45}.cost-header-icon{width:42px;height:42px;border-radius:12px;background:#eaf2ff;color:#245bdb;display:inline-flex;align-items:center;justify-content:center;font-size:20px;flex:none}
.cost-tabs{display:flex;width:100%;margin:0;gap:8px;padding:3px;border:1px solid rgba(148,163,184,.18);border-radius:12px;background:#fff;box-shadow:0 12px 26px rgba(15,23,42,.04)}.cost-tabs button{min-height:38px;padding:0 18px;border:0;border-radius:8px;background:transparent;color:#64748b;display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:700;line-height:1.2;cursor:pointer}.cost-tabs button.active{background:#e8f0ff;color:#245bdb;box-shadow:inset 0 0 0 1px rgba(51,112,255,.13)}
.cost-content-card{margin:0;padding:14px 16px;border:1px solid rgba(148,163,184,.18);border-radius:12px;background:#fff;box-shadow:0 10px 24px rgba(15,23,42,.035)}.section-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px}.toolbar-head{display:inline-flex;align-items:baseline;gap:8px;min-width:0;flex-wrap:wrap}.toolbar-title{color:#0f172a;font-size:14px;font-weight:800}.toolbar-desc{color:#64748b;font-size:12px}.workbench-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:12px 0;padding:10px;border:1px solid rgba(148,163,184,.14);border-radius:10px;background:#f8fafc}.workbench-toolbar-left,.workbench-toolbar-right{display:flex;align-items:center;gap:8px;min-width:0}.workbench-toolbar-left{flex:1;overflow:auto}.workbench-toolbar-right{flex:none}
.cost-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.cost-panel{min-width:0;border:1px solid rgba(148,163,184,.16);border-radius:10px;overflow:hidden}.cost-provider-panel{margin-top:10px}.cost-panel-head{min-height:44px;padding:0 12px;border-bottom:1px solid rgba(148,163,184,.14);background:#fbfdff;display:flex;align-items:center;justify-content:space-between;gap:8px}.cost-panel-head strong{color:#0f172a;font-size:13px}.cost-panel-head span{color:#64748b;font-size:12px}.cost-table{width:100%}.cost-pagination{display:flex;justify-content:flex-end;margin-top:12px}
.cost-account-overview{min-width:0}.cost-overview-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;padding:2px 1px}.cost-overview-head>div{display:flex;align-items:baseline;gap:8px;min-width:0;flex-wrap:wrap}.cost-overview-head strong{color:#0f172a;font-size:14px;font-weight:800}.cost-overview-head span{color:#64748b;font-size:12px}.cost-overview-chart{width:100%;height:410px;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff}.cost-overview-details{margin-top:10px;border:1px solid rgba(148,163,184,.16);border-radius:10px;overflow:hidden}.cost-overview-details-head{min-height:42px;padding:0 12px;border-bottom:1px solid rgba(148,163,184,.14);background:#fbfdff;display:flex;align-items:center;gap:8px}.cost-overview-details-head strong{color:#0f172a;font-size:13px}.cost-overview-details-head span{color:#64748b;font-size:12px}
.cost-detail-layout{display:grid;grid-template-columns:244px minmax(0,1fr);gap:14px;min-height:440px}.cost-rank-tree{min-width:0;padding-right:12px;border-right:1px solid rgba(148,163,184,.18)}.cost-rank-tree-head{display:flex;flex-direction:column;gap:3px;padding:3px 4px 10px}.cost-rank-tree-head strong{color:#0f172a;font-size:13px}.cost-rank-tree-head span{color:#64748b;font-size:12px}.cost-rank-tree-list{display:flex;flex-direction:column;gap:6px;padding-right:0}.cost-rank-tree-group{display:flex;flex-direction:column;gap:4px;padding:4px;border:1px solid rgba(148,163,184,.13);border-radius:9px;background:#fbfdff}.cost-rank-tree-group.is-expanded{background:#f8fbff}.cost-rank-tree-account-head{display:flex;align-items:center;gap:2px;min-width:0}.cost-rank-tree-node{box-sizing:border-box;width:100%;min-height:34px;padding:7px 8px;border:1px solid transparent;border-radius:7px;background:transparent;color:#475569;display:grid;grid-template-columns:minmax(0,1fr) 44px;align-items:center;gap:8px;font:inherit;font-size:12px;text-align:left;cursor:pointer}.cost-rank-tree-node span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.cost-rank-tree-toggle{width:24px;min-width:24px;height:28px;padding:0;border:0;border-radius:6px;background:transparent;color:#64748b;display:inline-flex;align-items:center;justify-content:center;cursor:pointer}.cost-rank-tree-toggle:hover{background:#e8f0ff;color:#245bdb}.cost-rank-tree-toggle .el-icon{font-size:13px}.cost-rank-tree-node strong{display:flex;align-items:center;justify-content:flex-end;width:44px;min-width:44px;line-height:1.2;color:#64748b;font-size:11px;font-weight:700;text-align:right;font-variant-numeric:tabular-nums}.cost-rank-tree-node:hover{background:#f5f8fe;color:#245bdb}.cost-rank-tree-node.active{border-color:rgba(51,112,255,.14);background:#e8f0ff;color:#245bdb}.cost-rank-tree-node.active strong{color:#245bdb}.cost-rank-tree-node--root{margin:0 5px 3px 0;background:#f8fafc}.cost-rank-tree-children{display:flex;flex-direction:column;gap:2px;margin:0 0 1px 34px;padding:0}.cost-rank-tree-node--child{min-height:31px;padding-left:10px;font-size:12px}.cost-detail-main{min-width:0}.cost-rank-result-head{display:flex;align-items:baseline;gap:8px;margin-bottom:8px}.cost-rank-result-head strong{color:#0f172a;font-size:13px}.cost-rank-result-head span{color:#64748b;font-size:12px}.cost-list-filter-bar{margin:0 0 10px}.cost-panel--suggestions{width:100%}
.ci-detail-shell{display:flex;flex-direction:column;gap:6px}.detail-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.detail-heading-main{min-width:0;display:flex;flex-direction:column;gap:2px}.detail-heading-actions{display:inline-flex;align-items:center;gap:6px;flex-shrink:0}.detail-title-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.detail-main-title{font-size:16px;line-height:1.35;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.detail-section{display:flex;flex-direction:column;gap:5px;padding:8px 10px;border:1px solid rgba(148,163,184,.14);border-radius:9px;background:#f8fafc;min-width:0}.detail-section--cost{gap:10px}.detail-section-title{color:#0f172a;font-size:13px;font-weight:800}.detail-section-head{display:flex;align-items:center;justify-content:space-between;gap:10px}.compact-stack{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px 8px}.detail-kv{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#475569;font-size:12px}.detail-kv strong{color:#0f172a;font-weight:700}.detail-kv--full{grid-column:span 2;white-space:normal;overflow:visible;text-overflow:clip;overflow-wrap:anywhere}.field-value-list{display:flex;flex-direction:column;gap:2px}.field-value-row{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0;padding:3px 0;color:#64748b;font-size:12px}.field-value-row span,.field-value-row strong{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.field-value-row strong{color:#0f172a;font-weight:600;text-align:right}.cost-detail-summary{display:flex;align-items:center;gap:12px;min-height:42px;padding:8px 10px;border:1px solid rgba(148,163,184,.16);border-radius:8px;background:#fbfdff}.cost-detail-value{display:inline-flex;align-items:baseline;gap:6px;min-width:0;color:#64748b;font-size:12px}.cost-detail-value--primary{margin-left:auto}.cost-detail-value strong{color:#0f172a;font-size:17px}.impact-summary-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.impact-summary-item{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 10px;border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#fff;color:#64748b;font-size:12px}.impact-summary-item strong{font-size:18px;color:#0f172a}.detail-tag-list{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}.tag-chip{display:inline-flex;align-items:center;min-height:22px;padding:0 7px;border:1px solid;border-radius:6px;background:#fff;font-size:11px;line-height:1.2}.sub-text,.muted-text{color:#94a3b8;font-size:12px}.impact-column-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:8px}.impact-list-panel{display:flex;flex-direction:column;gap:5px;min-width:0;padding:8px;border:1px solid rgba(148,163,184,.16);border-radius:8px;background:#fff}.impact-list-panel>strong{color:#334155;font-size:12px}.impact-node-row{display:flex;flex-direction:column;align-items:flex-start;gap:2px;min-width:0;padding:4px 0;border:0;background:transparent;text-align:left;cursor:pointer}.impact-node-row span,.impact-node-row small{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.impact-node-row span{color:#245bdb;font-size:12px}.impact-node-row small{color:#94a3b8;font-size:11px}.audit-diff-cell{display:flex;align-items:center;gap:6px;min-width:0}.audit-diff-cell span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.suggestion-cell{display:flex;flex-direction:column;gap:5px;min-width:0;padding:3px 0}.suggestion-cell>div{display:flex;align-items:center;gap:7px;min-width:0}.suggestion-cell strong{color:#0f172a;font-size:12px;line-height:1.45}.suggestion-cell>div strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.suggestion-cell span{color:#64748b;font-size:12px;line-height:1.45}.suggestion-cell--reason{gap:3px}.suggestion-saving-label{display:block;margin-top:3px;color:#64748b;font-size:11px}.handling-cell{display:flex;flex-direction:column;align-items:flex-start;gap:5px;min-width:0}.handling-cell span{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#64748b;font-size:12px}.cost-tracking-shell{min-width:0}.task-progress-note{display:block;max-width:96px;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#64748b;font-size:11px}.cost-progress-form{padding-right:10px}.form-suffix{margin-left:8px;color:#64748b;font-size:12px}.progress-history{max-height:220px;margin-top:8px;padding-top:12px;border-top:1px solid rgba(148,163,184,.18);overflow:auto}.progress-history>strong{display:block;margin-bottom:8px;color:#0f172a;font-size:13px}.progress-history-row{padding:8px 0;border-top:1px dashed rgba(148,163,184,.2)}.progress-history-row:first-of-type{border-top:0}.progress-history-row>div{display:flex;align-items:center;gap:8px;color:#64748b;font-size:12px}.progress-history-row p{margin:5px 0 3px;color:#475569;font-size:12px;line-height:1.5;white-space:pre-wrap}.progress-history-row time{color:#94a3b8;font-size:11px}
@media (max-width:900px){.cost-grid,.cost-account-grid,.cost-detail-layout,.detail-grid{grid-template-columns:1fr}.cost-rank-tree{padding:0 0 10px;border-right:0;border-bottom:1px solid rgba(148,163,184,.18)}.workbench-toolbar{align-items:flex-start;flex-direction:column}.workbench-toolbar-left{width:100%;flex-wrap:wrap}.workbench-toolbar-right{width:100%;justify-content:flex-end}}
@media (max-width:640px){.cost-hero-title-row{align-items:flex-start;flex-wrap:wrap}.page-inline-desc{width:100%}.cost-tabs{overflow:auto}.cost-tabs button{flex:none}.workbench-toolbar-right{justify-content:flex-start}.cost-content-card{padding:12px}.cost-overview-head{align-items:flex-start;flex-direction:column}.compact-stack,.impact-summary-grid{grid-template-columns:1fr}.detail-kv--full{grid-column:span 1}.cost-detail-summary{align-items:flex-start;flex-wrap:wrap}.cost-detail-value--primary{margin-left:0}}
</style>
