<template>
  <div class="fade-in waf-page workbench-page-shell">
    <section class="hero panel">
      <div class="waf-hero-title-row">
        <span class="release-header-icon"><el-icon><Lock /></el-icon></span>
        <h2>WAF 防火墙</h2>
        <p class="page-inline-desc">聚合阿里云 Web 应用防火墙 3.0 防护对象、流量趋势与安全事件</p>
      </div>
    </section>

    <div class="neo-tabs theme-blue" role="tablist" aria-label="WAF 数据视图">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="neo-tab-btn"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        <el-icon><component :is="tab.icon" /></el-icon>
        <span>{{ tab.label }}</span>
      </button>
    </div>

    <div class="workbench-card waf-content-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">{{ activeTabMeta.title }}</span>
          <span class="toolbar-desc">{{ activeTabMeta.description }}</span>
        </div>
        <div v-if="activeTab !== 'sources'" class="workbench-card-actions">
          <el-tag v-if="overview.instance?.edition" size="small" effect="plain">
            {{ editionLabel(overview.instance.edition) }}
          </el-tag>
          <el-tag v-if="overview.instance?.instance_id" size="small" type="success" effect="plain">实例已连接</el-tag>
        </div>
      </div>

      <div v-if="activeTab !== 'sources'" class="workbench-toolbar workbench-toolbar--history waf-filter-bar">
        <div class="workbench-toolbar-left">
          <div class="current-data-source" :title="selectedAccount?.account_name || selectedAccount?.name || '暂未选择数据源'">
            <el-icon><Connection /></el-icon>
            <span>当前数据源</span>
            <strong>{{ selectedAccount?.account_name || selectedAccount?.name || '暂未选择' }}</strong>
          </div>
          <el-date-picker
            v-if="activeTab !== 'resources'"
            v-model="customTimeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            aria-label="时间范围"
            :clearable="false"
            :disabled-date="disableFutureDate"
            :shortcuts="timeShortcuts"
            style="width: 390px"
            @change="handleCustomTimeChange"
          />
          <el-input
            v-if="activeTab === 'resources'"
            v-model="resourceQuery"
            clearable
            placeholder="搜索域名 / 防护对象"
            style="width: 220px"
            @keyup.enter="loadResources(1)"
            @clear="loadResources(1)"
          />
        </div>
        <div class="workbench-toolbar-right">
          <span v-if="lastFetchedAt" class="freshness">更新于 {{ formatDateTime(lastFetchedAt) }}</span>
          <el-button :loading="activeLoading" :disabled="!selectedCredentialId" @click="refreshActiveTab">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <div v-if="activeTab === 'events'" class="event-filter-panel">
        <div class="event-filter-heading">
          <span>事件条件</span>
          <small>按防护对象、攻击来源和规则信息精确定位事件</small>
        </div>
        <div class="event-filter-controls">
          <el-select
            v-model="eventFilters.resource"
            clearable
            placeholder="防护对象"
            style="width: 180px"
            @change="loadEvents(1)"
          >
            <el-option v-for="resource in eventResourceOptions" :key="resource" :label="resource" :value="resource" />
          </el-select>
          <el-input
            v-model="eventFilters.clientIp"
            clearable
            placeholder="来源 IP"
            style="width: 140px"
            @keyup.enter="loadEvents(1)"
            @clear="loadEvents(1)"
          />
          <el-select v-model="eventFilters.ruleType" clearable placeholder="规则类型" style="width: 140px" @change="loadEvents(1)">
            <el-option v-for="item in eventRuleTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="eventFilters.action" clearable placeholder="处置结果" style="width: 124px" @change="loadEvents(1)">
            <el-option label="已拦截" value="block" />
            <el-option label="人机验证" value="challenge" />
            <el-option label="已放行" value="allow" />
          </el-select>
          <el-input
            v-model="eventFilters.requestUrl"
            clearable
            placeholder="请求 URL"
            style="width: 210px"
            @keyup.enter="loadEvents(1)"
            @clear="loadEvents(1)"
          />
          <el-input
            v-model="eventFilters.ruleId"
            clearable
            placeholder="规则 ID"
            style="width: 140px"
            @keyup.enter="loadEvents(1)"
            @clear="loadEvents(1)"
          />
          <el-button link type="primary" class="event-filter-reset" @click="resetEventFilters">清空筛选</el-button>
        </div>
      </div>

      <el-alert
        v-if="connectionError"
        class="runtime-alert"
        type="warning"
        :title="connectionError"
        :closable="false"
        show-icon
      />
      <el-alert
        v-else-if="overview.warnings?.length"
        class="runtime-alert"
        type="warning"
        :title="warningText"
        :closable="false"
        show-icon
      />

      <el-empty
        v-if="!catalogLoading && !accounts.length"
        description="暂无已启用的阿里云账号，请先在多云管理中配置 AK/SK"
      />

      <div v-else-if="activeTab === 'sources'" class="source-pane">
        <div class="source-notice">
          <el-icon><InfoFilled /></el-icon>
          <div>
            <strong>通过 CMDB 资产采集中心统一管理 WAF 查询源</strong>
            <p>仅展示已启用且已配置 AK/SK 的阿里云采集源。选择后，防护态势、防护对象和攻击事件会使用该账号查询；使用前请确认账号已开通阿里云 WAF 3.0，并具备 WAF 只读查询权限。</p>
          </div>
        </div>

        <div class="source-list-heading">
          <strong>阿里云采集源</strong>
          <span>{{ accounts.length }} 个已启用来源</span>
        </div>
        <div class="source-grid">
          <article
            v-for="account in accounts"
            :key="account.id"
            class="source-card"
            :class="{ 'source-card--selected': account.id === selectedCredentialId, 'source-card--unavailable': !account.configured }"
          >
            <div class="source-card-topline">
              <div class="source-provider-mark">Aliyun</div>
              <el-tag size="small" :type="account.configured ? 'success' : 'info'" effect="plain">
                {{ account.configured ? '可用于 WAF 查询' : '凭据待补全' }}
              </el-tag>
            </div>
            <strong class="source-account-name">{{ account.account_name || account.name }}</strong>
            <span class="source-account-id">{{ account.account_id || '未设置账号 ID' }}</span>
            <dl class="source-meta-list">
              <div><dt>默认地域</dt><dd>{{ account.default_region || '--' }}</dd></div>
              <div><dt>负责人</dt><dd>{{ account.owner || '--' }}</dd></div>
            </dl>
            <div class="source-card-footer">
              <span v-if="account.id === selectedCredentialId" class="source-current"><el-icon><CircleCheckFilled /></el-icon>当前查询源</span>
              <span v-else></span>
              <el-button
                size="small"
                :type="account.id === selectedCredentialId ? 'default' : 'primary'"
                :disabled="!account.configured || account.id === selectedCredentialId"
                @click="selectDataSource(account)"
              >{{ account.id === selectedCredentialId ? '已选择' : '选择此数据源' }}</el-button>
            </div>
          </article>
        </div>
      </div>

      <div v-else-if="activeTab === 'overview'" v-loading="overviewLoading" class="overview-pane">
        <div v-if="!connectionError || overview.trend?.length" class="trend-section">
          <div class="subsection-head">
            <div>
              <strong>请求与规则命中趋势</strong>
              <span>统计范围：{{ selectedTimeRangeLabel }}，统计粒度会随时间范围自动调整</span>
            </div>
            <div class="legend-row">
              <span><i class="legend-dot legend-dot--blue"></i>请求 QPS</span>
              <span><i class="legend-dot legend-dot--red"></i>规则命中</span>
            </div>
          </div>
          <div ref="trendChartRef" class="trend-chart"></div>
        </div>

        <div v-if="!connectionError" class="security-health-strip">
          <div class="security-health-item" :class="{ 'security-health-item--danger': overview.alarm?.active }">
            <span>实例告警</span>
            <strong>{{ alarmStatusLabel }}</strong>
            <small>{{ alarmDescription }}</small>
          </div>
          <div class="security-health-item">
            <span>访问日志</span>
            <strong>{{ logStatusLabel }}</strong>
            <small>已统计当前页防护对象的日志开通状态</small>
          </div>
          <div class="security-health-item" :class="{ 'security-health-item--danger': upstream5xxCount > 0 }">
            <span>源站 5xx</span>
            <strong>{{ formatNumber(upstream5xxCount) }}</strong>
            <small>所选时间内源站返回给 WAF 的异常响应</small>
          </div>
        </div>

        <div v-if="!connectionError" class="ranking-grid">
          <section class="ranking-section">
            <div class="subsection-head">
              <div><strong>受攻击对象</strong><span>按规则命中次数排序</span></div>
            </div>
            <div v-if="overview.top_resources?.length" class="ranking-list">
              <button
                v-for="(item, index) in overview.top_resources"
                :key="`${item.resource}-${index}`"
                type="button"
                class="ranking-row ranking-row--action"
                :aria-label="`查看防护对象 ${item.resource || '--'} 的攻击事件`"
                @click="drillIntoEvents({ resource: item.resource })"
              >
                <span class="rank-index">{{ index + 1 }}</span>
                <span class="rank-name" :title="item.resource">{{ item.resource || '--' }}</span>
                <strong>{{ formatNumber(item.count) }}</strong>
              </button>
            </div>
            <el-empty v-else :image-size="46" description="暂无攻击对象排行" />
          </section>
          <section class="ranking-section ranking-section--split">
            <div class="subsection-head">
              <div><strong>攻击来源 IP</strong><span>定位高频访问来源</span></div>
            </div>
            <div v-if="overview.top_client_ips?.length" class="ranking-list">
              <button
                v-for="(item, index) in overview.top_client_ips"
                :key="`${item.client_ip}-${index}`"
                type="button"
                class="ranking-row ranking-row--action"
                :aria-label="`查看来源 IP ${item.client_ip || '--'} 的攻击事件`"
                @click="drillIntoEvents({ clientIp: item.client_ip })"
              >
                <span class="rank-index">{{ index + 1 }}</span>
                <span class="rank-name rank-name--mono">{{ item.client_ip || '--' }}</span>
                <strong>{{ formatNumber(item.count) }}</strong>
              </button>
            </div>
            <el-empty v-else :image-size="46" description="暂无攻击来源排行" />
          </section>
        </div>

        <div v-if="!connectionError" class="insight-ranking-grid">
          <section class="ranking-section">
            <div class="subsection-head">
              <div><strong>命中规则类型</strong><span>识别主要防护场景</span></div>
            </div>
            <div v-if="overview.top_rule_types?.length" class="ranking-list">
              <button
                v-for="(item, index) in overview.top_rule_types"
                :key="`${item.rule_type}-${index}`"
                type="button"
                class="ranking-row ranking-row--action"
                :aria-label="`查看${ruleTypeLabel(item.rule_type)}攻击事件`"
                @click="drillIntoEvents({ ruleType: item.rule_type })"
              >
                <span class="rank-index">{{ index + 1 }}</span>
                <span class="rank-name">{{ ruleTypeLabel(item.rule_type) }}</span>
                <strong>{{ formatNumber(item.count) }}</strong>
              </button>
            </div>
            <el-empty v-else :image-size="42" description="暂无规则类型排行" />
          </section>
          <section class="ranking-section ranking-section--split">
            <div class="subsection-head">
              <div><strong>高频规则 ID</strong><span>关联攻击事件进一步排查</span></div>
            </div>
            <div v-if="overview.top_rule_ids?.length" class="ranking-list">
              <button
                v-for="(item, index) in overview.top_rule_ids"
                :key="`${item.rule_id}-${index}`"
                type="button"
                class="ranking-row ranking-row--action"
                :aria-label="`查看规则 ID ${item.rule_id || '--'} 的攻击事件`"
                @click="drillIntoEvents({ ruleId: item.rule_id })"
              >
                <span class="rank-index">{{ index + 1 }}</span>
                <span class="rank-name" :title="item.rule_name || item.rule_id">
                  <span class="rank-name--mono">{{ item.rule_id || '--' }}</span><span v-if="item.rule_name">（{{ item.rule_name }}）</span>
                </span>
                <strong>{{ formatNumber(item.count) }}</strong>
              </button>
            </div>
            <el-empty v-else :image-size="42" description="暂无规则 ID 排行" />
          </section>
          <section class="ranking-section ranking-section--split insight-ranking-section--last">
            <div class="subsection-head">
              <div><strong>攻击事件请求 URL</strong><span>按攻击事件请求次数排序</span></div>
            </div>
            <div v-if="overview.top_urls?.length" class="ranking-list">
              <button
                v-for="(item, index) in overview.top_urls"
                :key="`${item.url}-${index}`"
                type="button"
                class="ranking-row ranking-row--action"
                :aria-label="`查看 URL ${item.url || '--'} 的攻击事件`"
                @click="drillIntoEvents({ requestUrl: eventRequestUrl(item.url) })"
              >
                <span class="rank-index">{{ index + 1 }}</span>
                <span class="rank-name rank-name--mono" :title="item.url">{{ item.url || '--' }}</span>
                <strong>{{ formatNumber(item.count) }}</strong>
              </button>
            </div>
            <el-empty v-else :image-size="42" description="暂无攻击事件请求 URL" />
          </section>
        </div>
      </div>

      <div v-else-if="activeTab === 'resources'" class="table-pane">
        <el-table v-loading="resourcesLoading" :data="resources.items" stripe style="width: 100%">
          <el-table-column label="防护对象" min-width="220">
            <template #default="{ row }">
              <div class="primary-cell">
                <strong>{{ row.resource || '--' }}</strong>
                <span>{{ row.description || row.origin || '阿里云 WAF 3.0' }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="接入产品" min-width="140">
            <template #default="{ row }">{{ productLabel(row.product) }}</template>
          </el-table-column>
          <el-table-column label="资源组" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.group || '默认资源组' }}</template>
          </el-table-column>
          <el-table-column label="防护状态" width="118">
            <template #default="{ row }">
              <el-tag size="small" :type="resourceStatusType(row.status)" effect="light">
                {{ resourceStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="客户端识别" min-width="170">
            <template #default="{ row }">
              <div class="feature-tags">
                <el-tag size="small" :type="row.xff_enabled ? 'success' : 'info'">XFF</el-tag>
                <el-tag size="small" :type="row.acw_cookie_enabled ? 'success' : 'info'">Cookie</el-tag>
                <el-tag size="small" :type="row.acw_secure_enabled ? 'success' : 'info'">安全校验</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
          </el-table-column>
        </el-table>
        <div class="pagination-row">
          <el-pagination
            v-model:current-page="resources.page"
            v-model:page-size="resources.page_size"
            layout="total, sizes, prev, pager, next"
            :total="resources.total"
            :page-sizes="[20, 50, 100]"
            @current-change="loadResources"
            @size-change="loadResources(1)"
          />
        </div>
      </div>

      <div v-else class="table-pane">
        <el-table v-loading="eventsLoading" :data="events.items" stripe style="width: 100%">
          <el-table-column label="发生时间" width="174">
            <template #default="{ row }">{{ formatDateTime(row.time) }}</template>
          </el-table-column>
          <el-table-column label="防护对象" min-width="190" show-overflow-tooltip>
            <template #default="{ row }"><strong>{{ row.resource || '--' }}</strong></template>
          </el-table-column>
          <el-table-column label="攻击来源" min-width="170">
            <template #default="{ row }">
              <div class="primary-cell">
                <span class="mono-text">{{ row.client_ip || '--' }}</span>
                <small>{{ row.country || '未知地区' }}</small>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="规则类型" min-width="140">
            <template #default="{ row }">{{ ruleTypeLabel(row.rule_type) }}</template>
          </el-table-column>
          <el-table-column label="命中规则" min-width="170" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="primary-cell">
                <strong class="mono-text">{{ row.rule_id || '--' }}</strong>
                <span>{{ row.rule_name || '规则名称暂未返回' }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="请求" min-width="230" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="request-method">{{ row.request_method || 'HTTP' }}</span>
              <span class="request-path">{{ row.request_path || '--' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="处置" width="104">
            <template #default="{ row }">
              <el-tag size="small" :type="actionTagType(row.action)">{{ actionLabel(row.action) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="76" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEventDetail(row)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination-row">
          <el-pagination
            v-model:current-page="events.page"
            v-model:page-size="events.page_size"
            layout="total, sizes, prev, pager, next"
            :total="events.total"
            :page-sizes="[20, 50, 100]"
            @current-change="loadEvents"
            @size-change="loadEvents(1)"
          />
        </div>
      </div>
    </div>

    <el-dialog
      v-model="eventDetailVisible"
      title="攻击事件详情"
      width="min(820px, 94vw)"
      append-to-body
      destroy-on-close
      class="waf-event-dialog"
    >
      <template v-if="selectedEvent">
        <el-descriptions :column="2" border size="small" class="event-detail-summary">
          <el-descriptions-item label="发生时间">{{ formatDateTime(selectedEvent.time) }}</el-descriptions-item>
          <el-descriptions-item label="处置结果">
            <el-tag size="small" :type="actionTagType(selectedEvent.action)">{{ actionLabel(selectedEvent.action) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="防护对象">{{ selectedEvent.resource || '--' }}</el-descriptions-item>
          <el-descriptions-item label="源站 Host">{{ selectedEvent.host || '--' }}</el-descriptions-item>
          <el-descriptions-item label="攻击来源"><span class="mono-text">{{ selectedEvent.client_ip || '--' }}</span></el-descriptions-item>
          <el-descriptions-item label="来源区域">{{ eventLocation(selectedEvent) }}</el-descriptions-item>
          <el-descriptions-item label="请求地址" :span="2">
            <span class="request-method">{{ selectedEvent.request_method || 'HTTP' }}</span>
            <code class="event-detail-code">{{ fullRequestPath(selectedEvent) }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="请求 Trace ID" :span="2">
            <code class="event-detail-code">{{ selectedEvent.trace_id || '--' }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="User-Agent" :span="2">{{ selectedEvent.user_agent || '--' }}</el-descriptions-item>
          <el-descriptions-item label="Referer" :span="2">{{ selectedEvent.referer || '--' }}</el-descriptions-item>
        </el-descriptions>

        <section class="event-rule-section">
          <div class="event-rule-heading">
            <strong>命中规则</strong>
            <span>共 {{ selectedEvent.rules?.length || 0 }} 条终止规则</span>
          </div>
          <div v-if="selectedEvent.rules?.length" class="event-rule-list">
            <div v-for="(rule, index) in selectedEvent.rules" :key="`${rule.id}-${index}`" class="event-rule-row">
              <div class="event-rule-meta">
                <el-tag size="small" type="danger" effect="light">{{ ruleTypeLabel(rule.type) }}</el-tag>
                <span>规则 ID <span class="mono-text">{{ rule.id || '--' }}</span><template v-if="rule.name">（{{ rule.name }}）</template></span>
                <span>{{ defenseSceneLabel(rule.defense_scene) }}</span>
                <el-tag size="small" :type="actionTagType(rule.action)">{{ actionLabel(rule.action) }}</el-tag>
              </div>
              <pre v-if="rule.hit" class="event-hit-detail">{{ formatEventDetail(rule.hit) }}</pre>
            </div>
          </div>
          <el-empty v-else :image-size="44" description="该事件未返回终止规则详情" />
        </section>

        <section v-if="hasMatchedDetail(selectedEvent)" class="event-rule-section">
          <div class="event-rule-heading"><strong>命中位置</strong></div>
          <pre class="event-hit-detail">{{ formatEventDetail(selectedEvent.matched_detail) }}</pre>
        </section>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import echarts from '@/lib/echarts'
import { getWafAccounts, getWafEvents, getWafOverview, getWafResources } from '@/api/modules/cloudsecurity'


const tabs = [
  { key: 'overview', label: '防护态势', icon: 'DataLine', title: '防护态势', description: '查看请求峰值、规则命中趋势与高频攻击来源。' },
  { key: 'events', label: '攻击事件', icon: 'Warning', title: '攻击事件', description: '查看近期安全事件、来源 IP、命中规则与处置结果。' },
  { key: 'resources', label: '防护对象', icon: 'Monitor', title: '防护对象', description: '查看接入 WAF 3.0 的域名、云产品与防护状态。' },
  { key: 'sources', label: '数据源', icon: 'Connection', title: '数据源', description: '选择 CMDB 资产采集中心已配置的阿里云账号作为 WAF 查询源。' },
]
const timeShortcuts = [
  { text: '最近 1 小时', value: () => recentTimeRange(1) },
  { text: '最近 6 小时', value: () => recentTimeRange(6) },
  { text: '最近 24 小时', value: () => recentTimeRange(24) },
  { text: '最近 3 天', value: () => recentTimeRange(72) },
  { text: '最近 7 天', value: () => recentTimeRange(168) },
  { text: '最近 30 天', value: () => recentTimeRange(720) },
]
const eventRuleTypeOptions = [
  { label: '跨站脚本攻击', value: 'xss' },
  { label: 'SQL 注入', value: 'sqli' },
  { label: '代码执行', value: 'code_exec' },
  { label: '命令注入', value: 'cmdi' },
  { label: '任意文件上传', value: 'arbitrary_file_uploading' },
  { label: '任意文件读取', value: 'arbitrary_file_reading' },
  { label: '扫描器行为', value: 'scanner_behavior' },
  { label: '逻辑漏洞', value: 'logic_flaw' },
]

const catalogLoading = ref(false)
const overviewLoading = ref(false)
const resourcesLoading = ref(false)
const eventsLoading = ref(false)
const accounts = ref([])
const selectedCredentialId = ref(null)
const regionId = ref('cn-hangzhou')
const customTimeRange = ref(recentTimeRange(24))
const activeTab = ref('overview')
const resourceQuery = ref('')
const eventFilters = reactive({
  resource: '',
  clientIp: '',
  ruleType: '',
  action: '',
  requestUrl: '',
  ruleId: '',
})
const eventResourceOptions = ref([])
const connectionError = ref('')
const trendChartRef = ref(null)
const eventDetailVisible = ref(false)
const selectedEvent = ref(null)
let trendChart = null
let overviewRequestId = 0

const overview = reactive({
  summary: {},
  instance: null,
  trend: [],
  top_resources: [],
  top_client_ips: [],
  top_rule_ids: [],
  top_rule_types: [],
  top_urls: [],
  alarm: {},
  log_status: {},
  upstream_response_codes: [],
  warnings: [],
  fetched_at: '',
})
const resources = reactive({ items: [], total: 0, page: 1, page_size: 20, fetched_at: '' })
const events = reactive({ items: [], total: 0, page: 1, page_size: 20, fetched_at: '' })

const summary = computed(() => overview.summary || {})
const selectedTimeRangeLabel = computed(() => {
  if (customTimeRange.value?.length !== 2) return '--'
  const [start, end] = customTimeRange.value
  return `${formatDateTime(start)} 至 ${formatDateTime(end)}`
})
const activeTabMeta = computed(() => tabs.find(item => item.key === activeTab.value) || tabs[0])
const activeLoading = computed(() => ({
  overview: overviewLoading.value,
  resources: resourcesLoading.value,
  events: eventsLoading.value,
})[activeTab.value])
const lastFetchedAt = computed(() => ({
  overview: overview.fetched_at,
  resources: resources.fetched_at,
  events: events.fetched_at,
})[activeTab.value])
const selectedAccount = computed(() => accounts.value.find(item => item.id === selectedCredentialId.value) || null)
const warningText = computed(() => `部分数据暂不可用：${(overview.warnings || []).map(item => item.source).join('、')}`)
const upstream5xxCount = computed(() => (overview.upstream_response_codes || []).reduce(
  (total, item) => total + Number(item['5xx'] || 0),
  0,
))
const alarmStatusLabel = computed(() => {
  if (!Object.keys(overview.alarm || {}).length) return '--'
  return overview.alarm.active ? '告警触发' : '运行正常'
})
const alarmDescription = computed(() => {
  if (!Object.keys(overview.alarm || {}).length) return '暂无实例告警状态数据'
  if (!overview.alarm.active) return '未检测到实例沙箱或容量告警'
  return alarmCauseLabel(overview.alarm.cause, overview.alarm.count)
})
const logStatusLabel = computed(() => {
  const status = overview.log_status || {}
  if (!status.total) return '--'
  return `${status.enabled || 0} / ${status.total} 已开通`
})

function requestParams() {
  const params = {
    credential_id: selectedCredentialId.value,
    region_id: regionId.value,
  }
  if (customTimeRange.value?.length === 2) {
    params.start_time = new Date(customTimeRange.value[0]).getTime()
    params.end_time = new Date(customTimeRange.value[1]).getTime()
  } else {
    params.hours = rangeHours.value
  }
  return params
}

function extractError(error, fallback) {
  return error?.response?.data?.detail || error?.message || fallback
}

async function loadCatalog() {
  catalogLoading.value = true
  connectionError.value = ''
  try {
    const response = await getWafAccounts()
    accounts.value = response.accounts || []
    const firstAvailable = accounts.value.find(item => item.configured)
    if (firstAvailable) {
      selectedCredentialId.value = firstAvailable.id
      regionId.value = firstAvailable.default_region || 'cn-hangzhou'
      await loadOverview()
    }
  } catch (error) {
    connectionError.value = extractError(error, '读取阿里云账号失败。')
  } finally {
    catalogLoading.value = false
  }
}

async function loadOverview() {
  if (!selectedCredentialId.value) return
  const requestId = ++overviewRequestId
  const params = requestParams()
  overviewLoading.value = true
  connectionError.value = ''
  try {
    const response = await getWafOverview(params)
    if (requestId !== overviewRequestId) return
    Object.assign(overview, {
      summary: response.summary || {},
      instance: response.instance || null,
      trend: response.trend || [],
      top_resources: response.top_resources || [],
      top_client_ips: response.top_client_ips || [],
      top_rule_ids: response.top_rule_ids || [],
      top_rule_types: response.top_rule_types || [],
      top_urls: response.top_urls || [],
      alarm: response.alarm || {},
      log_status: response.log_status || {},
      upstream_response_codes: response.upstream_response_codes || [],
      warnings: response.warnings || [],
      fetched_at: response.fetched_at || '',
    })
    await nextTick()
    renderTrendChart()
  } catch (error) {
    if (requestId !== overviewRequestId) return
    connectionError.value = extractError(error, '读取 WAF 防护态势失败。')
  } finally {
    if (requestId === overviewRequestId) overviewLoading.value = false
  }
}

async function loadResources(page = resources.page) {
  if (!selectedCredentialId.value) return
  resourcesLoading.value = true
  connectionError.value = ''
  try {
    const response = await getWafResources({
      ...requestParams(),
      page,
      page_size: resources.page_size,
      query: resourceQuery.value.trim(),
    })
    Object.assign(resources, {
      items: response.items || [],
      total: response.total || 0,
      page: response.page || page,
      page_size: response.page_size || resources.page_size,
      fetched_at: response.fetched_at || '',
    })
  } catch (error) {
    connectionError.value = extractError(error, '读取 WAF 防护对象失败。')
  } finally {
    resourcesLoading.value = false
  }
}

async function loadEvents(page = events.page) {
  if (!selectedCredentialId.value) return
  eventsLoading.value = true
  connectionError.value = ''
  try {
    const response = await getWafEvents({
      ...requestParams(),
      page,
      page_size: events.page_size,
      resource: eventFilters.resource.trim(),
      client_ip: eventFilters.clientIp.trim(),
      rule_type: eventFilters.ruleType,
      action: eventFilters.action,
      request_url: eventFilters.requestUrl.trim(),
      rule_id: eventFilters.ruleId.trim(),
    })
    Object.assign(events, {
      items: response.items || [],
      total: response.total || 0,
      page: response.page || page,
      page_size: response.page_size || events.page_size,
      fetched_at: response.fetched_at || '',
    })
  } catch (error) {
    connectionError.value = extractError(error, '读取 WAF 攻击事件失败。')
  } finally {
    eventsLoading.value = false
  }
}

async function switchTab(key) {
  activeTab.value = key
  connectionError.value = ''
  if (key === 'events') await loadEventResourceOptions()
  if (key !== 'sources') await refreshActiveTab()
}

async function drillIntoEvents(filters) {
  Object.assign(eventFilters, {
    resource: '',
    clientIp: '',
    ruleType: '',
    action: '',
    requestUrl: '',
    ruleId: '',
  }, filters)
  activeTab.value = 'events'
  connectionError.value = ''
  await loadEventResourceOptions()
  await loadEvents(1)
}

function eventRequestUrl(value) {
  const rawValue = String(value || '').trim()
  if (!rawValue) return ''
  const isHostAndPath = /^[a-z0-9.-]+\/.+/i.test(rawValue)
  const target = rawValue.includes('://') ? rawValue : (isHostAndPath ? `https://${rawValue}` : '')
  if (!target) return rawValue
  try {
    const parsed = new URL(target)
    return `${parsed.pathname || '/'}${parsed.search || ''}`
  } catch {
    return rawValue
  }
}

async function refreshActiveTab() {
  if (activeTab.value === 'resources') return loadResources(1)
  if (activeTab.value === 'events') return loadEvents(1)
  return loadOverview()
}

async function selectDataSource(account) {
  if (!account?.configured) return
  selectedCredentialId.value = account.id
  regionId.value = account.default_region || 'cn-hangzhou'
}

function handleCustomTimeChange(value) {
  if (value?.length === 2) void refreshActiveTab()
}

function disableFutureDate(date) {
  return date.getTime() > Date.now()
}

function resetEventFilters() {
  Object.assign(eventFilters, {
    resource: '',
    clientIp: '',
    ruleType: '',
    action: '',
    requestUrl: '',
    ruleId: '',
  })
  void loadEvents(1)
}

function recentTimeRange(hours) {
  const end = new Date()
  return [new Date(end.getTime() - hours * 60 * 60 * 1000), end]
}

async function loadEventResourceOptions() {
  if (!selectedCredentialId.value) return
  try {
    const response = await getWafResources({ ...requestParams(), page: 1, page_size: 100, query: '' })
    eventResourceOptions.value = (response.items || []).map(item => item.resource).filter(Boolean)
  } catch {
    eventResourceOptions.value = []
  }
}

function renderTrendChart() {
  if (!trendChartRef.value || activeTab.value !== 'overview') return
  if (trendChart && trendChart.getDom?.() !== trendChartRef.value) {
    trendChart.dispose()
    trendChart = null
  }
  if (!trendChart) trendChart = echarts.init(trendChartRef.value, null, { renderer: 'canvas' })
  const points = overview.trend || []
  trendChart.setOption({
    animationDuration: 350,
    grid: { left: 48, right: 28, top: 28, bottom: 34 },
    tooltip: { trigger: 'axis' },
    legend: { show: false },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: points.map(item => formatChartTime(item.timestamp)),
      axisLabel: { color: '#64748b', fontSize: 11 },
      axisLine: { lineStyle: { color: '#dbe3ee' } },
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: 'value',
        name: 'QPS',
        nameTextStyle: { color: '#94a3b8', fontSize: 11 },
        axisLabel: { color: '#64748b', fontSize: 11 },
        splitLine: { lineStyle: { color: '#eef2f7' } },
      },
      {
        type: 'value',
        name: '命中',
        nameTextStyle: { color: '#94a3b8', fontSize: 11 },
        axisLabel: { color: '#64748b', fontSize: 11 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '请求 QPS',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: points.map(item => item.qps || 0),
        lineStyle: { width: 2, color: '#3370ff' },
        itemStyle: { color: '#3370ff' },
        areaStyle: { color: 'rgba(51, 112, 255, 0.08)' },
      },
      {
        name: '规则命中',
        type: 'bar',
        yAxisIndex: 1,
        barMaxWidth: 8,
        data: points.map(item => item.attacks || 0),
        itemStyle: { color: '#ef6b73', borderRadius: [3, 3, 0, 0] },
      },
    ],
  }, true)
}

function timestampValue(value) {
  const numeric = Number(value)
  if (Number.isFinite(numeric) && numeric > 0) return numeric < 100000000000 ? numeric * 1000 : numeric
  return value
}

function formatChartTime(value) {
  const date = new Date(timestampValue(value))
  if (Number.isNaN(date.getTime())) return String(value || '--')
  const selectedRangeHours = customTimeRange.value?.length === 2
    ? (new Date(customTimeRange.value[1]).getTime() - new Date(customTimeRange.value[0]).getTime()) / 3600000
    : rangeHours.value
  if (selectedRangeHours <= 24) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  }
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

function formatDateTime(value) {
  if (!value) return '--'
  const date = new Date(timestampValue(value))
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-CN')
}

function editionLabel(value) {
  const labels = { basic: '基础版', pro: '高级版', enterprise: '企业版', ultimate: '旗舰版' }
  return labels[String(value || '').toLowerCase()] || value
}

function productLabel(value) {
  const labels = { waf: 'CNAME 接入', alb: '应用负载均衡', clb: '传统负载均衡', ecs: '云服务器', msea: 'MSE 网关', fc: '函数计算' }
  return labels[String(value || '').toLowerCase()] || value || '--'
}

function resourceStatusType(value) {
  return ['online', 'normal', '1'].includes(String(value || '').toLowerCase()) ? 'success' : 'warning'
}

function resourceStatusLabel(value) {
  const normalized = String(value || '').toLowerCase()
  if (['online', 'normal', '1'].includes(normalized)) return '防护中'
  if (['offline', '0'].includes(normalized)) return '未接入'
  return value || '状态未知'
}

function ruleTypeLabel(value) {
  const labels = {
    waf: 'Web 核心防护',
    waf_base: 'Web 核心防护',
    xss: '跨站脚本攻击',
    sqli: 'SQL 注入',
    sql_injection: 'SQL 注入',
    code_exec: '代码执行',
    cmdi: '命令注入',
    command_injection: '命令注入',
    arbitrary_file_uploading: '任意文件上传',
    arbitrary_file_reading: '任意文件读取',
    logic_flaw: '逻辑漏洞',
    scanner_behavior: '扫描器行为',
    cc: 'CC 防护',
    acl: '访问控制',
    antiscan: '扫描防护',
    ip_blacklist: 'IP 黑名单',
    blacklist: 'IP 黑名单',
    custom: '自定义规则',
    cc_system: 'CC 防护',
    region_block: '区域封禁',
    scene: 'Bot 管理',
    dlp: '数据泄露防护',
  }
  return labels[String(value || '').toLowerCase()] || value || '安全规则'
}

function alarmCauseLabel(cause, count) {
  const labels = {
    fivefold: '请求 QPS 超出套餐上限 5 倍',
    '4count': '请求 QPS 已连续多日超出套餐上限',
    exceed10w: '请求峰值 QPS 超过 100,000',
    costProtection: '已触发费用保护',
  }
  const description = labels[cause] || cause || '请前往阿里云 WAF 控制台核查实例状态'
  return count ? `${description}（${count}）` : description
}

function defenseSceneLabel(value) {
  const labels = { waf_base: 'Web 核心防护', cc: 'CC 防护', antiscan: '扫描防护', acl: '访问控制' }
  return labels[String(value || '').toLowerCase()] || value || '默认防护场景'
}

function actionTagType(value) {
  const text = String(value || '').toLowerCase()
  if (['block', 'blocked', 'deny', '2'].some(item => text.includes(item))) return 'danger'
  if (['challenge', 'captcha', '3'].some(item => text.includes(item))) return 'warning'
  return 'info'
}

function actionLabel(value) {
  const text = String(value || '').toLowerCase()
  if (['block', 'blocked', 'deny', '2'].some(item => text.includes(item))) return '已拦截'
  if (['challenge', 'captcha', '3'].some(item => text.includes(item))) return '人机验证'
  if (['pass', 'allow', '0'].some(item => text.includes(item))) return '已放行'
  return value || '已记录'
}

function openEventDetail(row) {
  selectedEvent.value = row
  eventDetailVisible.value = true
}

function eventLocation(event) {
  return [event.country, event.region].filter(Boolean).join(' / ') || '未知地区'
}

function fullRequestPath(event) {
  const path = event.request_path || '--'
  const query = event.querystring
  if (!query || query === '-') return path
  return query.startsWith('?') ? `${path}${query}` : `${path}?${query}`
}

function formatEventDetail(value) {
  if (!value) return '--'
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

function hasMatchedDetail(event) {
  return event?.matched_detail && Object.keys(event.matched_detail).length > 0
}

function handleResize() {
  trendChart?.resize()
}

onMounted(() => {
  void loadCatalog()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  trendChart = null
})
</script>

<style scoped>
.waf-page {
  gap: 6px;
}

.waf-page > .neo-tabs,
.waf-page > .waf-content-card {
  margin-top: 0;
  margin-bottom: 0;
}

.panel {
  padding: 14px 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(250, 252, 255, 0.96) 100%);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.hero {
  display: flex;
  align-items: center;
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36, 91, 219, 0.09);
}

.hero.panel {
  border-radius: 20px;
}

.waf-hero-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.hero h2 {
  margin: 0;
  color: #0f172a;
  font-size: 23px;
}

.page-inline-desc {
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.45;
}

.release-header-icon {
  width: 42px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(36, 91, 219, 0.12);
  border-radius: 14px;
  background: linear-gradient(180deg, #f3f7ff 0%, #ebf2ff 100%);
  color: #245bdb;
  font-size: 20px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.audit-grid {
  gap: 10px;
}

.audit-card {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(252, 253, 255, 0.94) 100%);
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.03);
}

.audit-card--inline {
  min-height: 68px;
  padding: 14px 16px;
}

.audit-card .stat-label {
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}

.audit-card .stat-value {
  color: #1f2329;
  font-size: 24px;
}

.audit-card--success {
  background: linear-gradient(180deg, #fbfffd 0%, #ffffff 100%);
}

.audit-card--warning {
  background: linear-gradient(180deg, #fffdfa 0%, #ffffff 100%);
}

.audit-card--danger {
  background: linear-gradient(180deg, #fffafb 0%, #ffffff 100%);
}

.neo-tabs {
  display: flex;
  width: 100%;
  gap: 8px;
  padding: 3px;
  overflow-x: auto;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 4px 10px rgba(15, 23, 42, 0.025);
}

.neo-tab-btn {
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 18px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #64748b;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.2;
  cursor: pointer;
  white-space: nowrap;
}

.neo-tab-btn .el-icon {
  font-size: 15px;
}

.neo-tab-btn.active {
  background: #e8f0ff;
  color: #245bdb;
  box-shadow: inset 0 0 0 1px rgba(36, 91, 219, 0.08);
}

.waf-content-card {
  padding: 14px 16px;
  border-radius: 14px;
  background: #ffffff;
}

.waf-filter-bar {
  margin-bottom: 8px;
}

.current-data-source {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 190px;
  max-width: 260px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid rgba(51, 112, 255, 0.16);
  border-radius: 8px;
  background: #f7faff;
}

.current-data-source .el-icon {
  flex: 0 0 auto;
  color: #3370ff;
  font-size: 14px;
}

.current-data-source span {
  flex: 0 0 auto;
  color: #64748b;
  font-size: 11px;
}

.current-data-source strong {
  overflow: hidden;
  color: #245bdb;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-filter-panel {
  margin-bottom: 8px;
  padding: 9px 10px 10px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  background: #fbfcfe;
}

.event-filter-heading {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  min-height: 22px;
  margin: 0 2px 7px;
}

.event-filter-heading span {
  color: #334155;
  font-size: 12px;
  font-weight: 700;
}

.event-filter-heading small {
  color: #94a3b8;
  font-size: 11px;
}

.event-filter-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  overflow-x: auto;
  padding-bottom: 1px;
}

.event-filter-reset {
  flex: 0 0 auto;
  margin-left: 2px;
}

.waf-filter-bar :deep(.el-date-editor .el-range__icon) {
  margin-right: 4px;
}

.freshness {
  color: #94a3b8;
  font-size: 11px;
  white-space: nowrap;
}

.runtime-alert {
  margin: 8px 0;
}

.runtime-alert :deep(.el-alert__title) {
  font-size: 12px;
}

.overview-pane,
.table-pane,
.source-pane {
  min-height: 260px;
}

.source-pane {
  padding-top: 2px;
}

.source-notice {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid rgba(36, 91, 219, 0.12);
  border-radius: 12px;
  background: linear-gradient(135deg, #f6f9ff 0%, #fbfdff 100%);
}

.source-notice > .el-icon {
  flex: 0 0 auto;
  margin-top: 2px;
  color: #3370ff;
  font-size: 16px;
}

.source-notice strong {
  display: block;
  color: #172033;
  font-size: 13px;
}

.source-notice p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.source-list-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin: 14px 0 8px;
}

.source-list-heading strong {
  color: #172033;
  font-size: 13px;
}

.source-list-heading span {
  color: #94a3b8;
  font-size: 11px;
}

.source-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
}

.source-card {
  min-width: 0;
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.025);
}

.source-card--selected {
  border-color: rgba(51, 112, 255, 0.42);
  background: linear-gradient(180deg, #f7faff 0%, #ffffff 100%);
  box-shadow: 0 6px 16px rgba(51, 112, 255, 0.08);
}

.source-card--unavailable {
  background: #fbfcfe;
}

.source-card-topline,
.source-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.source-provider-mark {
  color: #eb6a24;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.02em;
}

.source-account-name {
  display: block;
  overflow: hidden;
  margin-top: 12px;
  color: #172033;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-account-id {
  display: block;
  overflow: hidden;
  margin-top: 4px;
  color: #94a3b8;
  font-family: Consolas, "Courier New", monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-meta-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 12px 0;
}

.source-meta-list div {
  min-width: 0;
}

.source-meta-list dt {
  color: #94a3b8;
  font-size: 11px;
}

.source-meta-list dd {
  overflow: hidden;
  margin: 3px 0 0;
  color: #475569;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-card-footer {
  min-height: 28px;
  padding-top: 10px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
}

.source-current {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #245bdb;
  font-size: 11px;
  font-weight: 600;
}

.trend-section {
  padding: 10px 0 4px;
}

.subsection-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 32px;
}

.subsection-head > div:first-child {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.subsection-head strong {
  color: #172033;
  font-size: 13px;
}

.subsection-head span {
  color: #94a3b8;
  font-size: 11px;
}

.legend-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.legend-row span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.legend-dot--blue {
  background: #3370ff;
}

.legend-dot--red {
  background: #ef6b73;
}

.trend-chart {
  width: 100%;
  height: 286px;
}

.security-health-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 4px;
  border-top: 1px solid rgba(148, 163, 184, 0.14);
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
}

.security-health-item {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 11px 16px;
}

.security-health-item + .security-health-item {
  border-left: 1px solid rgba(148, 163, 184, 0.14);
}

.security-health-item span {
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
}

.security-health-item strong {
  color: #172033;
  font-size: 14px;
}

.security-health-item small {
  overflow: hidden;
  color: #94a3b8;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.security-health-item--danger strong {
  color: #d8394c;
}

.ranking-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 4px;
  border-top: 1px solid rgba(148, 163, 184, 0.14);
}

.insight-ranking-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 4px;
  border-top: 1px solid rgba(148, 163, 184, 0.14);
}

.ranking-section {
  min-width: 0;
  padding: 14px 16px 4px 0;
}

.ranking-section--split {
  padding-right: 0;
  padding-left: 16px;
  border-left: 1px solid rgba(148, 163, 184, 0.14);
}

.insight-ranking-section--last {
  padding-right: 0;
}

.ranking-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 6px;
}

.ranking-row {
  min-height: 34px;
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 0 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  font: inherit;
  text-align: left;
}

.ranking-row--action {
  width: 100%;
  cursor: pointer;
}

.ranking-row--action:hover {
  background: #f7f9fc;
}

.ranking-row--action:focus-visible {
  outline: 2px solid rgba(36, 91, 219, 0.35);
  outline-offset: 1px;
}

.rank-index {
  color: #94a3b8;
  font-size: 11px;
  text-align: center;
}

.ranking-row:nth-child(-n+3) .rank-index {
  color: #245bdb;
  font-weight: 700;
}

.rank-name {
  overflow: hidden;
  color: #334155;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rank-name--mono,
.mono-text {
  font-family: Consolas, "Courier New", monospace;
}

.ranking-row strong {
  color: #0f172a;
  font-size: 12px;
}

.primary-cell {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.primary-cell strong {
  overflow: hidden;
  color: #1e293b;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.primary-cell span,
.primary-cell small {
  overflow: hidden;
  color: #94a3b8;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.feature-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.request-method {
  display: inline-block;
  min-width: 42px;
  margin-right: 6px;
  color: #245bdb;
  font-size: 11px;
  font-weight: 700;
}

.request-path {
  color: #475569;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 10px;
}

.event-detail-summary :deep(.el-descriptions__label) {
  width: 112px;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.event-detail-summary :deep(.el-descriptions__content) {
  color: #1e293b;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.event-detail-code {
  color: #334155;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.event-rule-section {
  margin-top: 14px;
}

.event-rule-heading {
  min-height: 30px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.event-rule-heading strong {
  color: #172033;
  font-size: 13px;
}

.event-rule-heading span {
  color: #94a3b8;
  font-size: 11px;
}

.event-rule-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.event-rule-row {
  padding: 10px 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  background: #fbfcfe;
}

.event-rule-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  color: #64748b;
  font-size: 11px;
}

.event-hit-detail {
  max-height: 220px;
  margin: 8px 0 0;
  padding: 10px 12px;
  overflow: auto;
  border-radius: 8px;
  background: #f3f6fa;
  color: #334155;
  font-family: Consolas, "Courier New", monospace;
  font-size: 11px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

:global(.waf-event-dialog .el-dialog__header) {
  margin-right: 0;
  padding: 16px 18px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
}

:global(.waf-event-dialog .el-dialog__title) {
  color: #172033;
  font-size: 15px;
  font-weight: 700;
}

:global(.waf-event-dialog .el-dialog__body) {
  max-height: min(72vh, 720px);
  padding: 14px 18px 18px;
  overflow-y: auto;
}

@media (max-width: 900px) {
  .ranking-grid,
  .insight-ranking-grid {
    grid-template-columns: 1fr;
  }

  .ranking-section,
  .ranking-section--split {
    padding: 12px 0;
    border-left: 0;
  }

  .ranking-section--split {
    border-top: 1px solid rgba(148, 163, 184, 0.14);
  }

  .insight-ranking-section--last {
    padding-right: 0;
  }

  .waf-filter-bar,
  .waf-filter-bar .workbench-toolbar-left,
  .waf-filter-bar .workbench-toolbar-right,
  .event-filter-controls {
    width: 100%;
  }

}

@media (max-width: 640px) {
  .audit-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .page-inline-desc {
    display: none;
  }

  .neo-tab-btn {
    flex: 1;
    min-width: 0;
    padding: 0 8px;
  }

  .subsection-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .trend-chart {
    height: 240px;
  }

  .security-health-strip {
    grid-template-columns: 1fr;
  }

  .security-health-item + .security-health-item {
    border-top: 1px solid rgba(148, 163, 184, 0.14);
    border-left: 0;
  }

  .security-health-item small {
    white-space: normal;
  }

  .pagination-row {
    overflow-x: auto;
    justify-content: flex-start;
  }

  .event-detail-summary :deep(.el-descriptions__label) {
    width: 88px;
  }

  :global(.waf-event-dialog .el-dialog__body) {
    padding: 12px;
  }
}
</style>
