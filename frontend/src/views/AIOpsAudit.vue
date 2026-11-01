<template>
  <div class="fade-in aiops-audit-page workbench-page-shell">
    <section class="hero panel">
      <div class="release-hero-copy">
        <div class="release-hero-title-row">
          <span class="audit-header-icon"><el-icon><Tickets /></el-icon></span>
          <h2>智能体审计</h2>
          <p class="page-inline-desc">集中查看会话、执行追踪、工具调用、模型成本与待执行动作记录。</p>
        </div>
      </div>
    </section>

    <div class="neo-tabs theme-blue log-center-tabs trace-center-tabs event-tabs-shell audit-tabs">
      <button
        v-for="tab in auditTabs"
        :key="tab.name"
        type="button"
        class="neo-tab-btn audit-tab-btn"
        :class="{ active: activeTab === tab.name }"
        @click="switchTab(tab.name)"
      >
        <el-icon><component :is="tab.icon" /></el-icon>
        <span class="tab-label">{{ tab.label }}</span>
      </button>
    </div>

    <section v-if="activeTab === 'overview'" class="workbench-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">运行概览</span>
          <span class="toolbar-desc">聚焦所选时间范围内的调用命中明细与模型成本。</span>
        </div>
        <div class="overview-time-controls">
          <el-date-picker
            v-model="overviewTimeRange"
            class="overview-time-picker"
            size="small"
            type="datetimerange"
            format="YYYY-MM-DD HH:mm"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            :clearable="false"
            :shortcuts="overviewTimeShortcuts"
            @change="handleOverviewRangeChange"
          />
          <el-button
            size="small"
            :type="overviewAllTime ? 'primary' : 'default'"
            plain
            @click="selectAllOverviewTime"
          >
            全部时间
          </el-button>
          <el-button class="filter-refresh-btn audit-flat-action-btn" size="small" plain :loading="loading.overview" @click="loadOverview">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <div class="overview-dashboard-grid">
        <div class="overview-invocation-section">
          <div class="invocation-chart-grid">
            <div v-for="chart in overviewInvocationCharts" :key="chart.key" class="invocation-chart-card">
              <div class="invocation-chart-head">
                <strong>{{ chart.title }}</strong>
                <el-tag size="small" effect="plain">{{ formatNumber(chart.total) }} 次</el-tag>
              </div>
              <div class="invocation-pie-layout">
                <div
                  class="invocation-pie"
                  :style="chart.pieStyle"
                  @mousemove="handleInvocationPieMove($event, chart)"
                  @mouseleave="clearInvocationPieHover"
                >
                  <div class="invocation-pie-core">
                    <strong>{{ formatNumber(chart.total) }}</strong>
                    <span>总计</span>
                  </div>
                  <div
                    v-if="invocationPieHover.chartKey === chart.key && invocationPieHover.item"
                    class="invocation-pie-tooltip"
                    :style="{ left: `${invocationPieHover.x}px`, top: `${invocationPieHover.y}px` }"
                  >
                    <strong>{{ invocationPieHover.item.label }}</strong>
                    <span>{{ formatNumber(invocationPieHover.item.value) }} 次</span>
                  </div>
                </div>
                <div v-if="chart.total" class="invocation-pie-legend">
                  <div v-for="item in chart.rows" :key="item.key" class="invocation-pie-row">
                    <div class="invocation-pie-row-head">
                      <span class="invocation-dot" :style="{ background: item.color }"></span>
                      <span>{{ item.label }}</span>
                      <em>{{ formatPercent(item.value, chart.total) }}</em>
                      <strong>{{ formatNumber(item.value) }}</strong>
                    </div>
                  </div>
                </div>
                <div v-else class="overview-empty">{{ chart.emptyText }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="overview-panel overview-panel--model">
          <div class="overview-panel-head">
            <div>
              <span class="section-title">模型成本</span>
            </div>
          </div>
          <div class="overview-mini-grid">
            <div class="overview-mini-stat">
              <span>模型调用</span>
              <strong>{{ formatNumber(modelCostSummary.total_calls) }}</strong>
            </div>
            <div class="overview-mini-stat">
              <span>Token</span>
              <strong>{{ formatTokenCount(modelCostSummary.total_tokens) }}</strong>
            </div>
            <div class="overview-mini-stat">
              <span>费用</span>
              <strong>{{ formatModelCostSummary(modelCostSummary) }}</strong>
            </div>
            <div class="overview-mini-stat">
              <span>平均耗时</span>
              <strong>{{ formatLatency(modelCostSummary.avg_latency_ms) }}</strong>
            </div>
          </div>
          <div class="overview-rank-list">
            <div v-for="item in modelProviderRows" :key="`${item.provider}-${item.cost_currency || 'USD'}`" class="overview-rank-row">
              <div class="overview-rank-main">
                <div class="overview-rank-title">
                  <span>{{ item.provider }}</span>
                  <strong>{{ formatNumber(item.calls) }} 次</strong>
                </div>
                <div class="overview-rank-meta">
                  <span>{{ formatTokenCount(item.tokens) }} Token</span>
                  <span>{{ formatCost(item.estimated_cost_usd, item.cost_currency) }}</span>
                  <span>平均 {{ formatLatency(item.avg_latency_ms) }}</span>
                </div>
                <div class="overview-rank-bar"><span :style="{ width: `${item.percent}%` }"></span></div>
              </div>
            </div>
            <div v-if="!modelProviderRows.length" class="overview-empty">暂无模型调用数据</div>
          </div>
        </div>
      </div>
    </section>

    <section v-else class="workbench-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">{{ activeTabMeta.title }}</span>
          <span class="toolbar-desc">{{ activeTabMeta.desc }}</span>
        </div>
        <div class="workbench-card-actions">
          <el-button class="filter-refresh-btn audit-flat-action-btn" size="small" plain :loading="activeLoading" @click="refreshActiveTab">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
          <el-button
            v-if="activeTab === 'sessions' && canManageAudit"
            class="audit-flat-action-btn"
            type="danger"
            size="small"
            plain
            :disabled="!selectedAuditSessionIds.length"
            @click="handleBatchDeleteAuditSessions"
          >
            <el-icon><Delete /></el-icon>
            批量删除
          </el-button>
          <el-button
            v-if="activeTab === 'tools' && invocationAuditTab === 'mcp' && canManageAudit"
            class="audit-flat-action-btn"
            type="danger"
            size="small"
            plain
            :disabled="!selectedAuditToolIds.length"
            @click="handleBatchDeleteAuditTools"
          >
            <el-icon><Delete /></el-icon>
            批量删除
          </el-button>
          <el-button
            v-if="activeTab === 'tools' && invocationAuditTab === 'skills' && canManageAudit"
            class="audit-flat-action-btn"
            type="danger"
            size="small"
            plain
            :disabled="!selectedAuditSkillTraceIds.length"
            @click="handleBatchDeleteAuditSkillTraces"
          >
            <el-icon><Delete /></el-icon>
            批量删除
          </el-button>
          <el-button
            v-if="activeTab === 'tools' && invocationAuditTab === 'actionHits' && canManageAudit"
            class="audit-flat-action-btn"
            type="danger"
            size="small"
            plain
            :disabled="!selectedAuditActionTraceIds.length"
            @click="handleBatchDeleteAuditActionTraces"
          >
            <el-icon><Delete /></el-icon>
            批量删除
          </el-button>
          <el-button
            v-if="activeTab === 'actions' && canManageAudit"
            class="audit-flat-action-btn"
            type="danger"
            size="small"
            plain
            :disabled="!selectedAuditActionIds.length"
            @click="handleBatchDeleteAuditActions"
          >
            <el-icon><Delete /></el-icon>
            批量删除
          </el-button>
        </div>
      </div>

      <div v-if="activeTab === 'tools'" class="audit-subtabs">
        <button
          v-for="tab in invocationAuditTabs"
          :key="tab.name"
          type="button"
          class="audit-subtab-btn"
          :class="{ active: invocationAuditTab === tab.name }"
          @click="switchInvocationAuditTab(tab.name)"
        >
          <span>{{ tab.label }}</span>
        </button>
      </div>

      <div v-if="correlationScope && ['sessions', 'executions', 'tools', 'models', 'actions'].includes(activeTab)" class="audit-correlation-scope">
        <el-tag size="small" closable @close="clearCorrelationScope">{{ correlationScope }}</el-tag>
        <span>仅展示关联范围内的记录，切换页签可查看相关审计；关闭标签返回全部会话</span>
      </div>
      <div class="workbench-toolbar workbench-toolbar--history audit-list-toolbar">
        <div class="workbench-toolbar-left">
          <template v-if="activeTab === 'sessions'">
            <el-input v-model="auditFilters.sessions.q" class="audit-filter-search" size="small" clearable placeholder="搜索会话标题" @keyup.enter="applyAuditFilters" />
            <el-input v-model="auditFilters.sessions.username" class="audit-filter-user" size="small" clearable placeholder="用户" @keyup.enter="applyAuditFilters" />
            <el-select v-model="auditFilters.sessions.status" size="small" clearable placeholder="状态" @change="applyAuditFilters">
              <el-option v-for="item in sessionStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-date-picker v-model="auditFilters.sessions.timeRange" class="audit-filter-time" size="small" type="datetimerange" format="YYYY-MM-DD HH:mm" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" clearable @change="applyAuditFilters" />
          </template>
          <template v-else-if="activeTab === 'executions'">
            <el-input v-model="auditFilters.executions.q" class="audit-filter-search" size="small" clearable placeholder="搜索问题 / 会话 / Thread" @keyup.enter="applyAuditFilters" />
            <el-input v-model="auditFilters.executions.username" class="audit-filter-user" size="small" clearable placeholder="用户" @keyup.enter="applyAuditFilters" />
            <el-select v-model="auditFilters.executions.status" size="small" clearable placeholder="状态" @change="applyAuditFilters">
              <el-option v-for="item in executionStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-date-picker v-model="auditFilters.executions.timeRange" class="audit-filter-time" size="small" type="datetimerange" format="YYYY-MM-DD HH:mm" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" clearable @change="applyAuditFilters" />
          </template>
          <template v-else-if="activeTab === 'tools'">
            <el-input v-model="auditFilters.tools.q" class="audit-filter-search" size="small" clearable :placeholder="invocationSearchPlaceholder" @keyup.enter="applyAuditFilters" />
            <el-input v-model="auditFilters.tools.username" class="audit-filter-user" size="small" clearable placeholder="用户" @keyup.enter="applyAuditFilters" />
            <el-select v-if="invocationAuditTab === 'mcp'" v-model="auditFilters.tools.status" size="small" clearable placeholder="状态" @change="applyAuditFilters">
              <el-option v-for="item in toolStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-select v-if="invocationAuditTab === 'actionHits'" v-model="auditFilters.tools.risk_level" size="small" clearable placeholder="风险" @change="applyAuditFilters">
              <el-option v-for="item in actionRiskOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-date-picker v-model="auditFilters.tools.timeRange" class="audit-filter-time" size="small" type="datetimerange" format="YYYY-MM-DD HH:mm" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" clearable @change="applyAuditFilters" />
          </template>
          <template v-else-if="activeTab === 'models'">
            <el-input v-model="auditFilters.models.q" class="audit-filter-search" size="small" clearable placeholder="搜索会话 / 供应商 / 模型" @keyup.enter="applyAuditFilters" />
            <el-select v-model="auditFilters.models.status" size="small" clearable placeholder="状态" @change="applyAuditFilters">
              <el-option v-for="item in modelStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-select v-model="auditFilters.models.purpose" size="small" clearable placeholder="用途" @change="applyAuditFilters">
              <el-option v-for="item in modelPurposeOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-date-picker v-model="auditFilters.models.timeRange" class="audit-filter-time" size="small" type="datetimerange" format="YYYY-MM-DD HH:mm" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" clearable @change="applyAuditFilters" />
          </template>
          <template v-else-if="activeTab === 'actions'">
            <el-input v-model="auditFilters.actions.q" class="audit-filter-search" size="small" clearable placeholder="搜索动作 / 会话" @keyup.enter="applyAuditFilters" />
            <el-input v-model="auditFilters.actions.username" class="audit-filter-user" size="small" clearable placeholder="用户" @keyup.enter="applyAuditFilters" />
            <el-select v-model="auditFilters.actions.status" size="small" clearable placeholder="状态" @change="applyAuditFilters">
              <el-option v-for="item in actionFilterStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-select v-model="auditFilters.actions.risk_level" size="small" clearable placeholder="风险" @change="applyAuditFilters">
              <el-option v-for="item in actionRiskOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-date-picker v-model="auditFilters.actions.timeRange" class="audit-filter-time" size="small" type="datetimerange" format="YYYY-MM-DD HH:mm" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" clearable @change="applyAuditFilters" />
          </template>
        </div>
        <div class="workbench-toolbar-right">
          <el-button size="small" type="primary" plain @click="applyAuditFilters">筛选</el-button>
          <el-button size="small" @click="resetAuditFilters">重置</el-button>
        </div>
      </div>

      <el-table
        v-if="activeTab === 'sessions'"
        v-loading="loading.sessions"
        :data="auditSessions"
        stripe
        size="small"
        class="console-table audit-session-table"
        @selection-change="handleAuditSessionSelectionChange"
      >
        <el-table-column v-if="canManageAudit" type="selection" width="34" />
        <el-table-column type="expand" width="34">
          <template #default="{ row }">
            <div class="agent-trace-expand">
              <div class="trace-panel">
                <div class="trace-panel-head">
                  <span>Skill 命中</span>
                  <small>{{ formatSkillTraceSummary(row) }}</small>
                </div>
                <div v-if="skillTraceItems(row).length" class="trace-pill-list">
                  <span
                    v-for="skill in skillTraceItems(row)"
                    :key="skill.slug || skill.id || skill.name"
                    class="trace-pill"
                    :class="`is-${skill.status || 'available'}`"
                  >
                    <strong>{{ skill.name || skill.slug || '-' }}</strong>
                    <em>{{ skillStatusLabel(skill.status) }}</em>
                    <small v-if="skill.used_tools?.length">{{ skill.used_tools.join(' / ') }}</small>
                  </span>
                </div>
                <div v-else class="trace-empty">暂无 Skill 命中记录</div>
              </div>
              <div class="trace-panel">
                <div class="trace-panel-head">
                  <span>问答类型命中</span>
                  <small>{{ actionTraceTitle(row) }}</small>
                </div>
                <div v-if="hasActionTrace(row)" class="trace-action-main">
                  <el-tag size="small" :type="actionTraceStatusTone(capabilityTrace(row).status)" effect="plain">
                    {{ actionTraceStatusLabel(capabilityTrace(row).status) }}
                  </el-tag>
                  <strong>{{ actionTraceTitle(row) }}</strong>
                  <span>{{ actionTraceDetail(row) }}</span>
                </div>
                <div v-else class="trace-empty">暂无问答类型命中记录</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="会话标题" min-width="220" show-overflow-tooltip />
        <el-table-column prop="username" label="用户" width="88" show-overflow-tooltip />
        <el-table-column prop="message_count" label="消息数" width="72" />
        <el-table-column label="工具" width="68">
          <template #default="{ row }">
            {{ formatNumber(row.tool_invocation_count) }}
          </template>
        </el-table-column>
        <el-table-column label="Skill" width="96">
          <template #default="{ row }">
            <el-tag size="small" :type="skillTraceTone(row)" effect="plain">{{ formatSkillTraceSummary(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="问答类型" width="112" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="hasActionTrace(row)" class="audit-action-hit">{{ actionTraceTitle(row) }}</span>
            <span v-else class="muted-text">-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="66">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.status || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最后消息" width="156">
          <template #default="{ row }">
            {{ formatDateTimeDisplay(row.last_message_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <div class="audit-session-actions">
              <el-button link type="primary" @click="navigateAuditScope({ tab: 'executions', sessionId: row.id })">执行追踪</el-button>
              <el-button v-if="canManageAudit" link type="danger" @click="handleDeleteAuditSession(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-table v-else-if="activeTab === 'executions'" v-loading="loading.executions" :data="auditExecutions" stripe size="small" class="console-table" empty-text="暂无 LangGraph 执行记录">
        <el-table-column prop="session_title" label="会话" min-width="190" show-overflow-tooltip>
          <template #default="{ row }"><el-button class="audit-session-link" link type="primary" @click="filterAuditSession(row)">{{ row.session_title || `会话 #${row.session_id}` }}</el-button></template>
        </el-table-column>
        <el-table-column prop="question" label="本轮问题" min-width="240" show-overflow-tooltip />
        <el-table-column prop="username" label="用户" width="90" show-overflow-tooltip />
        <el-table-column label="运行方式" width="100">
          <template #default="{ row }"><el-tag size="small" effect="plain" :type="row.orchestration_degraded ? 'warning' : 'info'">{{ row.orchestration_degraded ? '兼容降级' : 'LangGraph' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><el-tag size="small" effect="plain" :type="executionStatusTone(row.status)">{{ executionStatusLabel(row.status) }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="node_count" label="节点" width="60" />
        <el-table-column label="图累计耗时" width="110"><template #default="{ row }">{{ formatLatency(row.graph_duration_ms) }}</template></el-table-column>
        <el-table-column label="恢复 / 重试" width="100"><template #default="{ row }">{{ row.resume_count }} / {{ row.retry_count }}</template></el-table-column>
        <el-table-column label="Checkpoint" width="114"><template #default="{ row }"><span :class="{ 'muted-text': row.checkpoint_expired }">{{ row.orchestration_degraded ? '降级不可用' : row.checkpoint_expired ? '已清理' : row.checkpoint_cleanup_pending ? '清理中' : '查看详情' }}</span></template></el-table-column>
        <el-table-column label="创建时间" width="156"><template #default="{ row }">{{ formatDateTimeDisplay(row.created_at) }}</template></el-table-column>
        <el-table-column label="操作" width="80" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openExecutionDetail(row)">详情</el-button></template></el-table-column>
      </el-table>

      <el-table
        v-else-if="activeTab === 'tools' && invocationAuditTab === 'mcp'"
        v-loading="loading.tools"
        :data="auditTools"
        stripe
        size="small"
        class="console-table audit-invocation-table"
        @selection-change="handleAuditToolSelectionChange"
      >
        <el-table-column v-if="canManageAudit" type="selection" width="34" />
        <el-table-column type="expand" width="34">
          <template #default="{ row }">
            <div class="json-preview">{{ formatJsonCompact({ request_payload: row.request_payload, response_summary: row.response_summary }) }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="session_title" label="会话" min-width="190" show-overflow-tooltip>
          <template #default="{ row }"><el-button class="audit-session-link" link type="primary" @click="filterAuditSession(row)">{{ row.session_title || `会话 #${row.session}` }}</el-button></template>
        </el-table-column>
        <el-table-column prop="tool_name" label="MCP 工具" min-width="112" show-overflow-tooltip />
        <el-table-column prop="username" label="用户" width="82" show-overflow-tooltip />
        <el-table-column label="状态" width="82">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTone(row.status)" effect="plain">{{ row.status || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="86">
          <template #default="{ row }">
            {{ formatLatency(row.latency_ms) }}
          </template>
        </el-table-column>
        <el-table-column label="时间" width="128">
          <template #default="{ row }">
            {{ formatDateTimeCompact(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="138" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :disabled="!row.message" @click="navigateAuditScope({ tab: 'executions', sessionId: row.session, messageId: row.message })">执行追踪</el-button>
            <el-button v-if="canManageAudit" link type="danger" @click="handleDeleteAuditTool(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-table
        v-else-if="activeTab === 'tools' && invocationAuditTab === 'skills'"
        v-loading="loading.skillTraces"
        :data="auditSkillTraces"
        stripe
        size="small"
        class="console-table audit-invocation-table"
        @selection-change="handleAuditSkillTraceSelectionChange"
      >
        <el-table-column v-if="canManageAudit" type="selection" width="34" />
        <el-table-column type="expand" width="34">
          <template #default="{ row }">
            <div class="trace-detail-grid">
              <div class="trace-panel">
                <div class="trace-panel-head">
                  <span>Skill 详情</span>
                  <small>{{ traceHitReasonLabel(row.hit_reason) }}</small>
                </div>
                <div class="trace-detail-list">
                  <div class="trace-detail-row"><span>名称</span><strong>{{ row.name || row.slug || '-' }}</strong></div>
                  <div class="trace-detail-row"><span>分类</span><strong>{{ row.category || '-' }}</strong></div>
                  <div class="trace-detail-row"><span>风险</span><strong>{{ row.risk_level || '-' }}</strong></div>
                  <div class="trace-detail-row"><span>来源</span><strong>{{ row.inferred ? '历史推断' : '运行记录' }}</strong></div>
                </div>
              </div>
              <div class="trace-panel">
                <div class="trace-panel-head">
                  <span>工具详情</span>
                  <small>{{ formatTraceCount(row.used_tools, '工具') }}</small>
                </div>
                <div class="trace-detail-list">
                  <div class="trace-detail-row trace-detail-row--stack">
                    <span>本次使用</span>
                    <div v-if="traceListItems(row.used_tools).length" class="trace-detail-tags">
                      <el-tag v-for="tool in traceListItems(row.used_tools)" :key="tool" size="small" effect="plain">{{ tool }}</el-tag>
                    </div>
                    <strong v-else>-</strong>
                  </div>
                </div>
              </div>
              <div class="trace-panel">
                <div class="trace-panel-head">
                  <span>能力关联</span>
                  <small>{{ row.action_display_name || row.action_code || '-' }}</small>
                </div>
                <div v-if="traceDisplayItems(row.applicable_action_names, row.applicable_actions).length" class="trace-detail-tags">
                  <el-tag v-for="action in traceDisplayItems(row.applicable_action_names, row.applicable_actions)" :key="action" size="small" effect="plain">{{ action }}</el-tag>
                </div>
                <div v-else class="trace-empty">暂无关联问答类型</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="session_title" label="会话" min-width="190" show-overflow-tooltip>
          <template #default="{ row }"><el-button class="audit-session-link" link type="primary" @click="filterAuditSession(row)">{{ row.session_title || `会话 #${row.session}` }}</el-button></template>
        </el-table-column>
        <el-table-column prop="name" label="Skill" min-width="102" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="trace-name-cell">
              <strong>{{ row.name || row.slug || '-' }}</strong>
              <small v-if="row.slug">{{ row.slug }}</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="命中来源" width="118" show-overflow-tooltip>
          <template #default="{ row }">
            {{ traceHitReasonLabel(row.hit_reason) }}
          </template>
        </el-table-column>
        <el-table-column label="问答类型" width="104" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.action_display_name || row.action_code" class="audit-action-hit">{{ row.action_display_name || row.action_code }}</span>
            <span v-else class="muted-text">-</span>
          </template>
        </el-table-column>
        <el-table-column label="工具" width="68">
          <template #default="{ row }">
            <el-tag v-if="traceListCount(row.used_tools)" size="small" type="success" effect="plain">{{ formatTraceCount(row.used_tools, '工具') }}</el-tag>
            <span v-else class="muted-text">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="用户" width="68" show-overflow-tooltip />
        <el-table-column label="时间" width="118">
          <template #default="{ row }">
            {{ formatDateTimeCompact(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column v-if="canManageAudit" label="操作" width="56" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="handleDeleteAuditSkillTrace(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-table
        v-else-if="activeTab === 'tools' && invocationAuditTab === 'actionHits'"
        v-loading="loading.actionTraces"
        :data="auditActionTraces"
        stripe
        size="small"
        class="console-table audit-invocation-table"
        @selection-change="handleAuditActionTraceSelectionChange"
      >
        <el-table-column v-if="canManageAudit" type="selection" width="34" />
        <el-table-column type="expand" width="34">
          <template #default="{ row }">
            <div class="trace-detail-grid">
              <div class="trace-panel">
                <div class="trace-panel-head">
                  <span>问答类型详情</span>
                  <small>{{ row.code || '-' }}</small>
                </div>
                <div class="trace-detail-list">
                  <div class="trace-detail-row"><span>路由</span><strong>{{ row.route || '-' }}</strong></div>
                  <div class="trace-detail-row"><span>草稿</span><strong>{{ row.draft_generated ? '已生成' : '-' }}</strong></div>
                  <div class="trace-detail-row"><span>说明</span><strong>{{ actionTraceRecordDetail(row) }}</strong></div>
                </div>
              </div>
              <div class="trace-panel">
                <div class="trace-panel-head">
                  <span>Skill 详情</span>
                  <small>{{ formatTraceCount(traceDisplayItems(row.skill_names, row.skills), 'Skill') }}</small>
                </div>
                <div v-if="traceDisplayItems(row.skill_names, row.skills).length" class="trace-detail-tags">
                  <el-tag v-for="skill in traceDisplayItems(row.skill_names, row.skills)" :key="skill" size="small" effect="plain">{{ skill }}</el-tag>
                </div>
                <div v-else class="trace-empty">暂无 Skill 记录</div>
              </div>
              <div class="trace-panel">
                <div class="trace-panel-head">
                  <span>工具详情</span>
                  <small>{{ formatTraceCount(row.allowed_tools, '工具') }}</small>
                </div>
                <div v-if="traceListItems(row.allowed_tools).length" class="trace-detail-tags">
                  <el-tag v-for="tool in traceListItems(row.allowed_tools)" :key="tool" size="small" effect="plain">{{ tool }}</el-tag>
                </div>
                <div v-else class="trace-empty">暂无工具记录</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="session_title" label="会话" min-width="190" show-overflow-tooltip>
          <template #default="{ row }"><el-button class="audit-session-link" link type="primary" @click="filterAuditSession(row)">{{ row.session_title || `会话 #${row.session}` }}</el-button></template>
        </el-table-column>
        <el-table-column label="问答类型" min-width="112" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="trace-name-cell">
              <strong>{{ row.display_name || row.code || '-' }}</strong>
              <small v-if="row.code">{{ row.code }}</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="风险" width="64">
          <template #default="{ row }">
            <el-tag v-if="row.risk_level || row.risk_level_display" size="small" :type="riskTone(row.risk_level)" effect="plain">{{ row.risk_level_display || row.risk_level }}</el-tag>
            <span v-else class="muted-text">-</span>
          </template>
        </el-table-column>
        <el-table-column label="Skill" width="76">
          <template #default="{ row }">
            <el-tag v-if="traceListCount(row.skills)" size="small" type="success" effect="plain">{{ formatTraceCount(row.skills, 'Skill') }}</el-tag>
            <span v-else class="muted-text">-</span>
          </template>
        </el-table-column>
        <el-table-column label="工具" width="76">
          <template #default="{ row }">
            <el-tag v-if="traceListCount(row.allowed_tools)" size="small" type="success" effect="plain">{{ formatTraceCount(row.allowed_tools, '工具') }}</el-tag>
            <span v-else class="muted-text">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="用户" width="82" show-overflow-tooltip />
        <el-table-column label="时间" width="128">
          <template #default="{ row }">
            {{ formatDateTimeCompact(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column v-if="canManageAudit" label="操作" width="62" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="handleDeleteAuditActionTrace(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-table
        v-else-if="activeTab === 'models'"
        v-loading="loading.models"
        :data="auditModels"
        stripe
        size="small"
        class="console-table"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="json-preview">{{ formatJsonCompact({ request_summary: row.request_summary, response_summary: row.response_summary }) }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="session_title" label="会话" min-width="190" show-overflow-tooltip>
          <template #default="{ row }">
            <el-button v-if="row.session" class="audit-session-link" link type="primary" @click="filterAuditSession(row)">{{ row.session_title || `会话 #${row.session}` }}</el-button>
            <span v-else class="muted-text">无关联会话</span>
          </template>
        </el-table-column>
        <el-table-column prop="provider_name" label="提供商" min-width="150" show-overflow-tooltip />
        <el-table-column prop="purpose_display" label="用途" width="110" />
        <el-table-column prop="resolved_model" label="模型" min-width="160" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTone(row.status)" effect="plain">{{ row.status_display || row.status || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Token" width="110">
          <template #default="{ row }">
            {{ formatTokenCount(row.total_tokens) }}
          </template>
        </el-table-column>
        <el-table-column label="费用" width="110">
          <template #default="{ row }">
            {{ formatCost(row.estimated_cost_usd, row.estimated_cost_currency) }}
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="110">
          <template #default="{ row }">
            {{ formatLatency(row.latency_ms) }}
          </template>
        </el-table-column>
        <el-table-column label="时间" min-width="170">
          <template #default="{ row }">
            {{ formatDateTimeDisplay(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="138" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :disabled="!row.message" @click="navigateAuditScope({ tab: 'executions', sessionId: row.session, messageId: row.message })">执行追踪</el-button>
            <el-button v-if="canManageAudit" link type="danger" @click="handleDeleteAuditModel(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-table
        v-else-if="activeTab === 'actions'"
        v-loading="loading.actions"
        :data="auditActions"
        stripe
        size="small"
        class="console-table"
        @selection-change="handleAuditActionSelectionChange"
      >
        <el-table-column v-if="canManageAudit" type="selection" width="34" />
        <el-table-column prop="session_title" label="会话" min-width="190" show-overflow-tooltip>
          <template #default="{ row }"><el-button class="audit-session-link" link type="primary" @click="filterAuditSession(row)">{{ row.session_title || `会话 #${row.session}` }}</el-button></template>
        </el-table-column>
        <el-table-column prop="title" label="动作标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="environment_display" label="环境" width="112" show-overflow-tooltip />
        <el-table-column label="风险" width="84">
          <template #default="{ row }">
            <el-tag size="small" :type="riskTone(row.risk_level)" effect="plain">{{ row.risk_level_display || row.risk_level || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="104">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTone(row.status)" effect="plain">{{ row.status_display || row.status || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="confirmed_by" label="确认人" width="90" show-overflow-tooltip />
        <el-table-column label="更新时间" width="150">
          <template #default="{ row }">
            {{ formatDateTimeDisplay(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="关联任务" width="96">
          <template #default="{ row }">
            <el-button v-if="getActionTaskId(row)" link type="primary" @click="goTaskWorkbenchTask(row)">查看任务</el-button>
            <span v-else class="muted-text">-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="canManageAudit" label="操作" width="64" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="handleDeleteAuditAction(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-row">
        <el-pagination class="pagination-total" :total="activePagination.total" layout="total" />
        <div class="pagination-size-control">
          <span class="audit-page-size-label">每页</span>
          <el-select v-model="activePageSize" class="audit-page-size-select" size="small" @change="handleAuditPageSizeChange">
            <el-option v-for="size in auditPageSizeOptions" :key="size" :label="`${size} 条`" :value="size" />
          </el-select>
        </div>
        <el-pagination class="pagination-pager" :current-page="activePagination.page" :page-size="activePagination.pageSize" :total="activePagination.total" layout="prev, pager, next" @current-change="loadActiveTabPage" />
      </div>
    </section>
    <AIOpsExecutionDetail v-model="executionDetailVisible" :execution-id="executionDetailId" @navigate="navigateAuditScope" />
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChatDotSquare, Connection, Cpu, Delete, Promotion, RefreshRight, Tickets } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import AIOpsExecutionDetail from '@/components/aiops/AIOpsExecutionDetail.vue'
import { executionStatusLabel, executionStatusOptions, executionStatusTone } from '@/utils/aiopsExecution'
import { normalizePendingActionTitle } from '@/utils/taskDraftTitle'
import {
  bulkDeleteAIOpsAuditActionTraces,
  bulkDeleteAIOpsAuditActions,
  bulkDeleteAIOpsAuditSessions,
  bulkDeleteAIOpsAuditSkillTraces,
  bulkDeleteAIOpsAuditToolInvocations,
  deleteAIOpsAuditAction,
  deleteAIOpsAuditModelInvocation,
  deleteAIOpsAuditSession,
  deleteAIOpsAuditToolInvocation,
  getAIOpsAuditActionTraces,
  getAIOpsAuditActions,
  getAIOpsAuditCosts,
  getAIOpsAuditExecutions,
  getAIOpsAuditModelInvocations,
  getAIOpsAuditOverview,
  getAIOpsAuditSessions,
  getAIOpsAuditSkillTraces,
  getAIOpsAuditToolInvocations,
} from '@/api/modules/aiops'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const activeTab = ref('overview')
const invocationAuditTab = ref('actionHits')
const auditOverview = ref({})
const auditCosts = ref({})
const auditSessions = ref([])
const auditExecutions = ref([])
const executionDetailVisible = ref(false)
const executionDetailId = ref(null)
const correlationScope = computed(() => {
  const title = route.query.session_title || `会话 #${route.query.session_id || '-'}`
  if (route.query.message_id) return `${title} · 消息 #${route.query.message_id}`
  return route.query.session_id ? title : ''
})
const auditTools = ref([])
const auditSkillTraces = ref([])
const auditActionTraces = ref([])
const auditModels = ref([])
const auditActions = ref([])
const selectedAuditSessionIds = ref([])
const selectedAuditToolIds = ref([])
const selectedAuditSkillTraceIds = ref([])
const selectedAuditActionTraceIds = ref([])
const selectedAuditActionIds = ref([])
const invocationPieHover = reactive({ chartKey: '', item: null, x: 0, y: 0 })
const loading = reactive({
  overview: false,
  sessions: false,
  executions: false,
  tools: false,
  skillTraces: false,
  actionTraces: false,
  models: false,
  actions: false,
})
const AUDIT_DEFAULT_PAGE_SIZE = 20
const AUDIT_MIN_PAGE_SIZE = 10
const AUDIT_MAX_PAGE_SIZE = 100
const auditPageSizeOptions = [10, 20, 50, 100]
const auditSessionPagination = reactive({ page: 1, pageSize: AUDIT_DEFAULT_PAGE_SIZE, total: 0 })
const auditExecutionPagination = reactive({ page: 1, pageSize: AUDIT_DEFAULT_PAGE_SIZE, total: 0 })
const auditToolPagination = reactive({ page: 1, pageSize: AUDIT_DEFAULT_PAGE_SIZE, total: 0 })
const auditSkillTracePagination = reactive({ page: 1, pageSize: AUDIT_DEFAULT_PAGE_SIZE, total: 0 })
const auditActionTracePagination = reactive({ page: 1, pageSize: AUDIT_DEFAULT_PAGE_SIZE, total: 0 })
const auditModelPagination = reactive({ page: 1, pageSize: AUDIT_DEFAULT_PAGE_SIZE, total: 0 })
const auditActionPagination = reactive({ page: 1, pageSize: AUDIT_DEFAULT_PAGE_SIZE, total: 0 })
const auditFilters = reactive({
  sessions: { q: '', username: '', status: '', timeRange: [] },
  executions: { q: '', username: '', status: '', timeRange: [] },
  tools: { q: '', username: '', status: '', risk_level: '', timeRange: [] },
  models: { q: '', status: '', purpose: '', timeRange: [] },
  actions: { q: '', username: '', status: '', risk_level: '', timeRange: [] },
})
const sessionStatusOptions = [
  { label: '进行中', value: 'active' },
  { label: '已归档', value: 'archived' },
]
const toolStatusOptions = [
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failed' },
  { label: '待处理', value: 'pending' },
]
const modelStatusOptions = [
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failed' },
]
const modelPurposeOptions = [
  { label: '聊天规划', value: 'chat_planning' },
  { label: '回答整形', value: 'answer_formatting' },
  { label: '参数抽取', value: 'parameter_extraction' },
  { label: '模型探测', value: 'model_probe' },
  { label: '连接测试', value: 'connection_test' },
]
const actionFilterStatusOptions = [
  { label: '待确认', value: 'pending' },
  { label: '已确认', value: 'confirmed' },
  { label: '已执行', value: 'executed' },
  { label: '执行失败', value: 'failed' },
  { label: '已取消', value: 'canceled' },
]
const actionRiskOptions = [
  { label: '低', value: 'low' },
  { label: '中', value: 'medium' },
  { label: '高', value: 'high' },
  { label: '极高', value: 'critical' },
]
const OVERVIEW_DEFAULT_DAYS = 7
const overviewAllTime = ref(false)
const overviewRecentDays = ref(OVERVIEW_DEFAULT_DAYS)
const overviewTimeRange = ref(buildRecentTimeRange(OVERVIEW_DEFAULT_DAYS))
const overviewTimeShortcuts = [
  { text: '最近 1 天', value: () => buildRecentTimeRange(1) },
  { text: '最近 7 天', value: () => buildRecentTimeRange(7) },
  { text: '最近 14 天', value: () => buildRecentTimeRange(14) },
  { text: '最近 30 天', value: () => buildRecentTimeRange(30) },
  { text: '最近 90 天', value: () => buildRecentTimeRange(90) },
]

const auditTabs = [
  { name: 'overview', label: '运行概览', icon: Tickets, title: '运行概览', desc: '汇总今日使用与所选时间范围成本。' },
  { name: 'sessions', label: '会话历史', icon: ChatDotSquare, title: '会话历史', desc: '查看智能助手会话、用户与消息数量。' },
  { name: 'executions', label: '执行追踪', icon: Connection, title: '执行追踪', desc: '查看每轮 LangGraph 节点、耗时、恢复与 checkpoint 状态。' },
  { name: 'tools', label: '调用审计', icon: Connection, title: '调用审计', desc: '分层查看问答类型命中、Skill 命中与 MCP 工具调用。' },
  { name: 'models', label: '模型调用', icon: Cpu, title: '模型调用', desc: '查看模型用途、Token、耗时与预估费用。' },
  { name: 'actions', label: '待执行动作', icon: Promotion, title: '待执行动作', desc: '审计待确认、已执行、失败和被策略拦截的动作。' },
]
const validTabs = auditTabs.map(item => item.name)
const invocationAuditTabs = [
  { name: 'actionHits', label: '问答类型命中' },
  { name: 'skills', label: 'Skill 命中' },
  { name: 'mcp', label: 'MCP 工具' },
]
const validInvocationAuditTabs = invocationAuditTabs.map(item => item.name)
const invocationPiePalettes = {
  mcp: ['#245bdb', '#3b82f6', '#60a5fa', '#93c5fd', '#1d4ed8', '#2563eb', '#38bdf8', '#0ea5e9'],
  skills: ['#16a34a', '#22c55e', '#4ade80', '#86efac', '#15803d', '#059669', '#34d399', '#10b981'],
  actions: ['#f59e0b', '#fbbf24', '#f97316', '#fb923c', '#d97706', '#ea580c', '#facc15', '#eab308'],
}
const canManageAudit = computed(() => authStore.hasPermission('aiops.audit.manage'))
const modelCostSummary = computed(() => auditCosts.value?.model || {})
const toolCostSummary = computed(() => auditCosts.value?.tools || {})
const modelProviderRows = computed(() => {
  const rows = Array.isArray(modelCostSummary.value.by_provider) ? modelCostSummary.value.by_provider : []
  const maxCalls = Math.max(...rows.map(item => toNumber(item.calls)), 1)
  return rows.slice(0, 6).map(item => ({
    ...item,
    percent: Math.max(6, Math.round((toNumber(item.calls) / maxCalls) * 100)),
  }))
})
const overviewInvocationCharts = computed(() => {
  const distribution = auditOverview.value?.invocation_distribution || {}
  const fallbackMcpItems = Array.isArray(toolCostSummary.value.by_tool)
    ? toolCostSummary.value.by_tool.map(item => ({
      key: item.tool_name || 'unknown',
      label: item.tool_name || '未命名工具',
      count: item.calls,
    }))
    : []
  return [
    buildInvocationPieChart({
      key: 'mcp',
      title: 'MCP 工具调用',
      items: Array.isArray(distribution.mcp_tools) ? distribution.mcp_tools : fallbackMcpItems,
      palette: invocationPiePalettes.mcp,
      emptyText: '暂无 MCP 工具调用',
    }),
    buildInvocationPieChart({
      key: 'skills',
      title: 'Skill 命中',
      items: Array.isArray(distribution.skills) ? distribution.skills : [],
      palette: invocationPiePalettes.skills,
      emptyText: '暂无 Skill 命中记录',
    }),
    buildInvocationPieChart({
      key: 'actions',
      title: '问答类型命中',
      items: Array.isArray(distribution.actions) ? distribution.actions : [],
      palette: invocationPiePalettes.actions,
      emptyText: '暂无问答类型命中记录',
    }),
  ]
})
const activeTabMeta = computed(() => auditTabs.find(item => item.name === activeTab.value) || auditTabs[0])
const invocationSearchPlaceholder = computed(() => {
  if (invocationAuditTab.value === 'skills') return '搜索 Skill / 问答类型 / 会话'
  if (invocationAuditTab.value === 'actionHits') return '搜索问答类型 / Skill / 会话'
  return '搜索 MCP 工具 / 会话'
})
const activeLoading = computed(() => {
  if (activeTab.value === 'tools') {
    if (invocationAuditTab.value === 'skills') return loading.skillTraces
    if (invocationAuditTab.value === 'actionHits') return loading.actionTraces
    return loading.tools
  }
  return Boolean(loading[activeTab.value])
})
const activePagination = computed(() => {
  if (activeTab.value === 'executions') return auditExecutionPagination
  if (activeTab.value === 'tools') {
    if (invocationAuditTab.value === 'skills') return auditSkillTracePagination
    if (invocationAuditTab.value === 'actionHits') return auditActionTracePagination
    return auditToolPagination
  }
  if (activeTab.value === 'models') return auditModelPagination
  if (activeTab.value === 'actions') return auditActionPagination
  return auditSessionPagination
})
const activePageSize = computed({
  get: () => activePagination.value.pageSize,
  set: size => setAuditPageSize(size),
})

function toNumber(value) {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : 0
}

function normalizeInvocationPieRows(items, palette) {
  const rowMap = new Map()
  ;(Array.isArray(items) ? items : []).forEach((item, index) => {
    const value = toNumber(item?.count ?? item?.value ?? item?.calls)
    if (!value) return
    const label = String(item?.label || item?.name || item?.tool_name || item?.code || item?.key || '未命名').trim()
    const key = String(item?.key || item?.slug || item?.code || item?.tool_name || label || index).trim()
    const current = rowMap.get(key) || { key, label, value: 0 }
    current.value += value
    rowMap.set(key, current)
  })
  return Array.from(rowMap.values())
    .sort((left, right) => right.value - left.value || left.label.localeCompare(right.label, 'zh-CN'))
    .map((item, index) => ({
      ...item,
      color: palette[index % palette.length],
    }))
}

function buildInvocationPieStyle(rows, total) {
  if (!total) return { background: 'conic-gradient(#e2e8f0 0deg 360deg)' }
  let cursor = 0
  const segments = rows.map((item) => {
    const start = cursor
    cursor += (item.value / total) * 360
    return `${item.color} ${start.toFixed(2)}deg ${cursor.toFixed(2)}deg`
  })
  return { background: `conic-gradient(${segments.join(', ')})` }
}

function buildInvocationPieChart({ key, title, desc, items, palette, emptyText }) {
  const rows = normalizeInvocationPieRows(items, palette)
  const total = rows.reduce((sum, item) => sum + item.value, 0)
  return {
    key,
    title,
    desc,
    rows,
    total,
    emptyText,
    pieStyle: buildInvocationPieStyle(rows, total),
  }
}

function handleInvocationPieMove(event, chart) {
  if (!chart?.total || !Array.isArray(chart.rows) || !chart.rows.length) {
    clearInvocationPieHover()
    return
  }
  const rect = event.currentTarget.getBoundingClientRect()
  const centerX = rect.width / 2
  const centerY = rect.height / 2
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top
  const angle = (Math.atan2(y - centerY, x - centerX) * 180 / Math.PI + 90 + 360) % 360
  let cursor = 0
  const hovered = chart.rows.find((item, index) => {
    cursor += (item.value / chart.total) * 360
    return angle <= cursor || index === chart.rows.length - 1
  })
  invocationPieHover.chartKey = chart.key
  invocationPieHover.item = hovered || null
  invocationPieHover.x = Math.min(Math.max(x, 40), rect.width - 40)
  invocationPieHover.y = Math.min(Math.max(y, 26), rect.height - 26)
}

function clearInvocationPieHover() {
  invocationPieHover.chartKey = ''
  invocationPieHover.item = null
}

function buildRecentTimeRange(days) {
  const end = new Date()
  const start = new Date(end.getTime() - days * 24 * 60 * 60 * 1000)
  return [start, end]
}

function formatDateTimeParam(value) {
  if (!value) return ''
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toISOString()
}

function formatDateTimeDisplay(value) {
  if (!value) return '-'
  const date = value instanceof Date ? value : new Date(value)
  if (!Number.isNaN(date.getTime())) {
    const pad = number => String(number).padStart(2, '0')
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  }
  const text = String(value).trim()
  return text ? text.replace('T', ' ').replace(/\.\d+.*$/, '').replace(/(?:Z|[+-]\d{2}:?\d{2})$/, '') : '-'
}

function formatDateTimeCompact(value) {
  const text = formatDateTimeDisplay(value)
  return text.length > 16 ? text.slice(0, 16) : text
}

function buildOverviewCostParams() {
  if (overviewAllTime.value) return { range: 'all' }
  if (overviewRecentDays.value) return { days: overviewRecentDays.value }
  const [start, end] = Array.isArray(overviewTimeRange.value) ? overviewTimeRange.value : []
  const startParam = formatDateTimeParam(start)
  const endParam = formatDateTimeParam(end)
  if (startParam && endParam) {
    return { start: startParam, end: endParam }
  }
  return { days: OVERVIEW_DEFAULT_DAYS }
}

function appendTimeRangeParams(params, range) {
  const [start, end] = Array.isArray(range) ? range : []
  const startParam = formatDateTimeParam(start)
  const endParam = formatDateTimeParam(end)
  if (startParam) params.start = startParam
  if (endParam) params.end = endParam
}

function compactParams(params) {
  return Object.fromEntries(Object.entries(params).reduce((entries, [key, value]) => {
    const normalized = typeof value === 'string' ? value.trim() : value
    if (normalized === '' || normalized === null || normalized === undefined) return entries
    if (Array.isArray(normalized) && !normalized.length) return entries
    entries.push([key, normalized])
    return entries
  }, []))
}

function auditPageSize(tab, subTab = invocationAuditTab.value) {
  if (tab === 'executions') return auditExecutionPagination.pageSize
  if (tab === 'tools') {
    if (subTab === 'skills') return auditSkillTracePagination.pageSize
    if (subTab === 'actionHits') return auditActionTracePagination.pageSize
    return auditToolPagination.pageSize
  }
  if (tab === 'models') return auditModelPagination.pageSize
  if (tab === 'actions') return auditActionPagination.pageSize
  return auditSessionPagination.pageSize
}

function buildAuditListParams(tab, page = 1, subTab = invocationAuditTab.value) {
  const base = { page, page_size: auditPageSize(tab, subTab) }
  if (['sessions', 'executions', 'tools', 'models', 'actions'].includes(tab)) {
    base.session_id = route.query.session_id
    base.message_id = route.query.message_id
  }
  if (tab === 'executions') {
    const filters = auditFilters.executions
    appendTimeRangeParams(base, filters.timeRange)
    return compactParams({ ...base, q: filters.q, username: filters.username, status: filters.status })
  }
  if (tab === 'sessions') {
    const filters = auditFilters.sessions
    appendTimeRangeParams(base, filters.timeRange)
    return compactParams({ ...base, q: filters.q, username: filters.username, status: filters.status })
  }
  if (tab === 'tools') {
    const filters = auditFilters.tools
    appendTimeRangeParams(base, filters.timeRange)
    return compactParams({ ...base, q: filters.q, username: filters.username, status: filters.status, risk_level: filters.risk_level })
  }
  if (tab === 'models') {
    const filters = auditFilters.models
    appendTimeRangeParams(base, filters.timeRange)
    return compactParams({ ...base, q: filters.q, status: filters.status, purpose: filters.purpose })
  }
  const filters = auditFilters.actions
  appendTimeRangeParams(base, filters.timeRange)
  return compactParams({ ...base, q: filters.q, username: filters.username, status: filters.status, risk_level: filters.risk_level })
}

function clearAuditFilterGroup(group) {
  Object.keys(group).forEach((key) => {
    group[key] = Array.isArray(group[key]) ? [] : ''
  })
}

function applyAuditFilters() {
  return loadActiveTabPage(1)
}

function resetAuditFilters() {
  if (!auditFilters[activeTab.value]) return
  clearAuditFilterGroup(auditFilters[activeTab.value])
  return loadActiveTabPage(1)
}

function setAuditPageSize(size) {
  activePagination.value.pageSize = Math.min(Math.max(Number(size) || AUDIT_DEFAULT_PAGE_SIZE, AUDIT_MIN_PAGE_SIZE), AUDIT_MAX_PAGE_SIZE)
}

function handleAuditPageSizeChange(size) {
  setAuditPageSize(size)
  return loadActiveTabPage(1)
}

async function handleOverviewRangeChange() {
  overviewAllTime.value = false
  overviewRecentDays.value = inferRecentDaysFromRange(overviewTimeRange.value)
  await loadOverview()
}

async function selectAllOverviewTime() {
  overviewAllTime.value = true
  overviewRecentDays.value = null
  overviewTimeRange.value = []
  await loadOverview()
}

function inferRecentDaysFromRange(range) {
  if (!Array.isArray(range) || range.length !== 2) return null
  const [start, end] = range
  const startDate = start instanceof Date ? start : new Date(start)
  const endDate = end instanceof Date ? end : new Date(end)
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return null
  const now = Date.now()
  const endDelta = Math.abs(now - endDate.getTime())
  const diffDays = (endDate.getTime() - startDate.getTime()) / (24 * 60 * 60 * 1000)
  if (endDelta > 10 * 60 * 1000) return null
  return [1, 7, 14, 30, 90].find(days => Math.abs(diffDays - days) < 0.02) || null
}

function formatNumber(value) {
  return toNumber(value).toLocaleString('zh-CN')
}

function formatPercent(value, total) {
  const totalValue = toNumber(total)
  if (!totalValue) return '0%'
  const percent = (toNumber(value) / totalValue) * 100
  return `${percent >= 10 ? Math.round(percent) : percent.toFixed(1)}%`
}

function formatTokenCount(value) {
  const numberValue = Math.round(toNumber(value))
  if (Math.abs(numberValue) < 1000000) return formatNumber(numberValue)
  const millionValue = numberValue / 1000000
  const digits = Math.abs(millionValue) < 10 ? 2 : 1
  return `${millionValue.toFixed(digits).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1')}M`
}

function normalizeCostCurrency(currency) {
  return String(currency || '').toUpperCase() === 'CNY' ? 'CNY' : 'USD'
}

function currencySymbol(currency) {
  return normalizeCostCurrency(currency) === 'CNY' ? '¥' : '$'
}

function formatCost(value, currency = 'USD') {
  const numberValue = toNumber(value)
  const symbol = currencySymbol(currency)
  if (!numberValue) return `${symbol}0`
  return `${symbol}${numberValue.toFixed(numberValue < 1 ? 4 : 2)}`
}

function formatModelCostSummary(summary = {}) {
  const byCurrency = Array.isArray(summary.by_currency) ? summary.by_currency.filter(item => toNumber(item.estimated_cost_usd)) : []
  if (byCurrency.length > 1) {
    return byCurrency
      .map(item => formatCost(item.estimated_cost_usd, item.currency))
      .join(' / ')
  }
  const currency = byCurrency[0]?.currency || summary.cost_currency || 'USD'
  return formatCost(summary.estimated_cost_usd, currency)
}

function formatLatency(value) {
  const numberValue = Math.round(toNumber(value))
  return numberValue ? `${formatNumber(numberValue)} ms` : '-'
}

function normalizeTab(tab) {
  const value = Array.isArray(tab) ? tab[0] : tab
  return validTabs.includes(value) ? value : 'overview'
}

function normalizeInvocationAuditTab(tab) {
  const value = Array.isArray(tab) ? tab[0] : tab
  return validInvocationAuditTabs.includes(value) ? value : 'actionHits'
}

function syncRouteTab(tab) {
  const nextTab = normalizeTab(tab)
  if (route.query.tab !== nextTab) {
    return router.replace({ path: route.path, query: { ...route.query, tab: nextTab } })
  }
  return Promise.resolve()
}

function switchTab(tab) {
  const nextTab = normalizeTab(tab)
  activeTab.value = nextTab
  syncRouteTab(nextTab)
}

async function navigateAuditScope({ tab, sessionId, messageId }) {
  clearAuditFilterGroup(auditFilters[tab])
  if (tab === 'tools') invocationAuditTab.value = 'mcp'
  const session = auditSessions.value.find(item => String(item.id) === String(sessionId))
  const row = [...auditExecutions.value, ...auditTools.value, ...auditSkillTraces.value, ...auditActionTraces.value, ...auditModels.value, ...auditActions.value]
    .find(item => String(item.session_id || item.session) === String(sessionId))
  const sessionTitle = session?.title || row?.session_title || (String(route.query.session_id) === String(sessionId) ? route.query.session_title : undefined)
  await router.replace({ path: route.path, query: compactParams({
    ...route.query, tab, session_id: sessionId, session_title: sessionTitle, message_id: messageId,
  }) })
}

async function filterAuditSession(row) {
  const sessionId = row.session_id || row.session
  if (!sessionId) return
  clearAuditFilterGroup(auditFilters[activeTab.value])
  await router.replace({ path: route.path, query: compactParams({
    ...route.query, session_id: sessionId, session_title: row.session_title, message_id: undefined,
  }) })
}

async function clearCorrelationScope() {
  const query = { ...route.query }
  delete query.session_id
  delete query.session_title
  delete query.message_id
  await router.replace({ path: route.path, query })
}

function openExecutionDetail(row) {
  executionDetailId.value = row.message_id
  executionDetailVisible.value = true
}

async function switchInvocationAuditTab(tab) {
  const nextTab = normalizeInvocationAuditTab(tab)
  if (invocationAuditTab.value === nextTab) return
  invocationAuditTab.value = nextTab
  auditFilters.tools.status = ''
  auditFilters.tools.risk_level = ''
  selectedAuditToolIds.value = []
  await loadActiveInvocationTabPage(1)
}

function getActionTaskId(action) {
  const value = action?.result_payload?.task_id || action?.result_payload?.created_task_id || action?.result_payload?.host_task_id
  return value ? String(value) : ''
}

function appendEnvironmentValue(list, value) {
  const text = String(value || '').trim()
  if (text && !list.includes(text)) list.push(text)
}

function appendEnvironmentItems(list, items) {
  if (!Array.isArray(items)) return
  items.forEach(item => {
    appendEnvironmentValue(list, item?.environment_name)
    appendEnvironmentValue(list, item?.environment)
    appendEnvironmentValue(list, item?.env)
    appendEnvironmentValue(list, item?.namespace)
  })
}

function formatEnvironmentValues(values) {
  const items = values.filter(Boolean)
  if (!items.length) return '-'
  if (items.length === 1) return items[0]
  return `${items[0]} 等 ${items.length} 个`
}

function pendingActionEnvironmentDisplay(row = {}) {
  const payload = row.action_payload || {}
  const resultPayload = row.result_payload || {}
  const sourceContext = payload.source_context || resultPayload.source_context || {}
  const selectionFilters = payload.selection_filters || resultPayload.selection_filters || {}
  const values = []
  appendEnvironmentValue(values, payload.environment_name)
  appendEnvironmentValue(values, payload.environment)
  appendEnvironmentValue(values, sourceContext.environment_name)
  appendEnvironmentValue(values, sourceContext.environment)
  appendEnvironmentValue(values, sourceContext.resource_environment)
  appendEnvironmentValue(values, selectionFilters.environment_name)
  appendEnvironmentValue(values, selectionFilters.environment)
  appendEnvironmentItems(values, payload.target_hosts)
  appendEnvironmentItems(values, payload.target_snapshot)
  appendEnvironmentItems(values, payload.k8s_targets)
  appendEnvironmentItems(values, resultPayload.target_hosts)
  appendEnvironmentItems(values, resultPayload.target_snapshot)
  return formatEnvironmentValues(values)
}

function goTaskWorkbenchTask(action) {
  const taskId = getActionTaskId(action)
  if (!taskId) return
  router.push({
    path: '/tasks/workbench',
    query: {
      taskTab: 'history',
      taskId,
      source: 'aiopsAudit',
    },
  })
}

function skillTraceItems(row) {
  const items = Array.isArray(row?.skill_trace?.items) ? row.skill_trace.items : []
  return [...items].sort((left, right) => {
    const leftHit = left?.status && left.status !== 'available'
    const rightHit = right?.status && right.status !== 'available'
    if (leftHit !== rightHit) return leftHit ? -1 : 1
    return String(left?.name || '').localeCompare(String(right?.name || ''), 'zh-CN')
  })
}

function formatSkillTraceSummary(row) {
  const trace = row?.skill_trace || {}
  const matched = toNumber(trace.matched_count)
  if (!matched) return '暂无'
  return `${matched} 命中`
}

function skillTraceTone(row) {
  const matched = toNumber(row?.skill_trace?.matched_count)
  if (matched > 0) return 'success'
  if (toNumber(row?.skill_trace?.enabled_count) > 0) return 'info'
  return 'info'
}

function skillStatusLabel(status) {
  const labels = {
    available: '已加载',
    matched: '命中',
    called: '已调用',
    fallback: '已回退',
  }
  return labels[status] || status || '已加载'
}

function capabilityTrace(row) {
  return row?.capability_trace || row?.action_trace || {}
}

function hasActionTrace(row) {
  const trace = capabilityTrace(row)
  return Boolean(trace && typeof trace === 'object' && Object.keys(trace).length)
}

function actionTraceTitle(row) {
  const trace = capabilityTrace(row)
  return trace.display_name || trace.code || '-'
}

function actionTraceStatusLabel(status) {
  const labels = {
    matched: '已命中',
    needs_info: '待补充',
    pending_confirmation: '待确认',
    materialized: '已落库',
    blocked: '已拦截',
    failed: '失败',
  }
  return labels[status] || status || '已命中'
}

function actionTraceStatusTone(status) {
  if (status === 'failed' || status === 'blocked') return 'danger'
  if (status === 'needs_info' || status === 'pending_confirmation') return 'warning'
  if (status === 'materialized') return 'success'
  return 'info'
}

function actionTraceDetail(row) {
  const trace = capabilityTrace(row)
  const decision = trace.decision || {}
  if (decision.task_name) return `任务中心：${decision.task_name}`
  if (decision.pending_action_id) return `待执行动作 #${decision.pending_action_id}`
  if (decision.reason === 'analysis_only') return '仅分析模式已拦截执行动作'
  if (decision.reason === 'policy') return '策略已拦截执行动作'
  if (decision.reason === 'missing_context') return '缺少必要上下文'
  if (trace.route) return `路由：${trace.route}`
  if (Array.isArray(trace.allowed_tools) && trace.allowed_tools.length) return `允许工具 ${trace.allowed_tools.length} 个`
  return trace.code || '-'
}

function traceHitReasonLabel(reason) {
  const labels = {
    runtime_enabled: '运行时启用',
    action_matched: '问答类型命中',
    action_called: '问答类型调用',
    capability_matched: '问答类型命中',
    capability_called: '问答类型调用',
    legacy_action_router: '历史能力路由推断',
    legacy_tool_dependency: '历史工具推断',
  }
  return labels[reason] || reason || '-'
}

function traceListItems(values) {
  const items = Array.isArray(values) ? values : []
  return items.reduce((list, item) => {
    const value = String(item || '').trim()
    if (value && !list.includes(value)) list.push(value)
    return list
  }, [])
}

function traceDisplayItems(values, fallbackValues = []) {
  const displayValues = traceListItems(values)
  return displayValues.length ? displayValues : traceListItems(fallbackValues)
}

function traceListCount(values) {
  return traceListItems(values).length
}

function formatTraceCount(values, label) {
  const count = traceListCount(values)
  return count ? `${count} ${label}` : '-'
}

function actionTraceRecordDetail(row) {
  const decision = row?.decision || {}
  if (decision.task_name) return `任务中心：${decision.task_name}`
  if (decision.pending_action_id) return `待执行动作 #${decision.pending_action_id}`
  if (decision.reason === 'analysis_only') return '仅分析模式已拦截执行动作'
  if (decision.reason === 'policy') return '策略已拦截执行动作'
  if (decision.reason === 'missing_context') return '缺少必要上下文'
  if (row?.route) return `路由：${row.route}`
  if (Array.isArray(row?.allowed_tools) && row.allowed_tools.length) return `允许工具 ${row.allowed_tools.length} 个`
  return row?.code || '-'
}

function formatJsonCompact(value) {
  try {
    return JSON.stringify(value || {}, null, 2)
  } catch (error) {
    return String(value || '')
  }
}

function statusTone(status) {
  if (['success', 'completed', 'confirmed', 'executed', 'matched', 'called', 'materialized'].includes(status)) return 'success'
  if (['failed', 'error', 'canceled', 'rejected', 'blocked'].includes(status)) return 'danger'
  if (['pending', 'draft', 'running', 'fallback', 'needs_info', 'pending_confirmation'].includes(status)) return 'warning'
  return 'info'
}

function riskTone(risk) {
  if (['high', 'critical'].includes(risk)) return 'danger'
  if (risk === 'medium') return 'warning'
  return 'info'
}

async function loadOverview() {
  loading.overview = true
  try {
    const overviewParams = buildOverviewCostParams()
    const [overviewData, costData] = await Promise.all([
      getAIOpsAuditOverview(overviewParams, { skipErrorMessage: true }),
      getAIOpsAuditCosts(overviewParams, { skipErrorMessage: true }),
    ])
    auditOverview.value = overviewData || {}
    auditCosts.value = costData || {}
  } finally {
    loading.overview = false
  }
}

async function loadAuditSessions(page = 1, config = {}) {
  loading.sessions = true
  try {
    const data = await getAIOpsAuditSessions(buildAuditListParams('sessions', page), config)
    auditSessionPagination.page = page
    auditSessionPagination.total = data.count || 0
    auditSessions.value = data.results || data || []
    selectedAuditSessionIds.value = []
  } catch (error) {
    const message = String(error?.response?.data?.detail || '')
    if (page > 1 && message.includes('无效页面')) return loadAuditSessions(page - 1, config)
    throw error
  } finally {
    loading.sessions = false
  }
}

async function loadAuditTools(page = 1, config = {}) {
  loading.tools = true
  try {
    const data = await getAIOpsAuditToolInvocations(buildAuditListParams('tools', page, 'mcp'), config)
    auditToolPagination.page = page
    auditToolPagination.total = data.count || 0
    auditTools.value = data.results || data || []
    selectedAuditToolIds.value = []
  } catch (error) {
    const message = String(error?.response?.data?.detail || '')
    if (page > 1 && message.includes('无效页面')) return loadAuditTools(page - 1, config)
    throw error
  } finally {
    loading.tools = false
  }
}

async function loadAuditSkillTraces(page = 1, config = {}) {
  loading.skillTraces = true
  try {
    const data = await getAIOpsAuditSkillTraces(buildAuditListParams('tools', page, 'skills'), config)
    auditSkillTracePagination.page = page
    auditSkillTracePagination.total = data.count || 0
    auditSkillTraces.value = data.results || data || []
    selectedAuditSkillTraceIds.value = []
  } catch (error) {
    const message = String(error?.response?.data?.detail || '')
    if (page > 1 && message.includes('无效页面')) return loadAuditSkillTraces(page - 1, config)
    throw error
  } finally {
    loading.skillTraces = false
  }
}

async function loadAuditActionTraces(page = 1, config = {}) {
  loading.actionTraces = true
  try {
    const data = await getAIOpsAuditActionTraces(buildAuditListParams('tools', page, 'actionHits'), config)
    auditActionTracePagination.page = page
    auditActionTracePagination.total = data.count || 0
    auditActionTraces.value = data.results || data || []
    selectedAuditActionTraceIds.value = []
  } catch (error) {
    const message = String(error?.response?.data?.detail || '')
    if (page > 1 && message.includes('无效页面')) return loadAuditActionTraces(page - 1, config)
    throw error
  } finally {
    loading.actionTraces = false
  }
}

async function loadAuditModels(page = 1, config = {}) {
  loading.models = true
  try {
    const data = await getAIOpsAuditModelInvocations(buildAuditListParams('models', page), config)
    auditModelPagination.page = page
    auditModelPagination.total = data.count || 0
    auditModels.value = data.results || data || []
  } catch (error) {
    const message = String(error?.response?.data?.detail || '')
    if (page > 1 && message.includes('无效页面')) return loadAuditModels(page - 1, config)
    throw error
  } finally {
    loading.models = false
  }
}

async function loadAuditActions(page = 1, config = {}) {
  loading.actions = true
  try {
    const data = await getAIOpsAuditActions(buildAuditListParams('actions', page), config)
    auditActionPagination.page = page
    auditActionPagination.total = data.count || 0
    const rows = data.results || data || []
    auditActions.value = rows.map(row => ({
      ...row,
      title: normalizePendingActionTitle(row),
      environment_display: pendingActionEnvironmentDisplay(row),
    }))
    selectedAuditActionIds.value = []
  } catch (error) {
    const message = String(error?.response?.data?.detail || '')
    if (page > 1 && message.includes('无效页面')) return loadAuditActions(page - 1, config)
    throw error
  } finally {
    loading.actions = false
  }
}

function loadActiveInvocationTabPage(page = 1) {
  if (invocationAuditTab.value === 'skills') return loadAuditSkillTraces(page)
  if (invocationAuditTab.value === 'actionHits') return loadAuditActionTraces(page)
  return loadAuditTools(page)
}

async function loadAuditExecutions(page = 1) {
  loading.executions = true
  try {
    const data = await getAIOpsAuditExecutions(buildAuditListParams('executions', page), { skipErrorMessage: true })
    auditExecutions.value = data.results || []
    auditExecutionPagination.page = page
    auditExecutionPagination.total = data.count || 0
  } catch (error) {
    if (error?.response?.status === 404 && page > 1) return loadAuditExecutions(page - 1)
    auditExecutions.value = []
    auditExecutionPagination.total = 0
    ElMessage.error(error?.response?.data?.detail || '执行追踪加载失败')
  } finally {
    loading.executions = false
  }
}

function loadActiveTabPage(page = 1) {
  if (activeTab.value === 'executions') return loadAuditExecutions(page)
  if (activeTab.value === 'tools') return loadActiveInvocationTabPage(page)
  if (activeTab.value === 'models') return loadAuditModels(page)
  if (activeTab.value === 'actions') return loadAuditActions(page)
  return loadAuditSessions(page)
}

async function refreshActiveTab() {
  if (activeTab.value === 'overview') return loadOverview()
  await Promise.all([loadOverview(), loadActiveTabPage(activePagination.value.page)])
}

function handleAuditSessionSelectionChange(rows) {
  selectedAuditSessionIds.value = rows.map(item => item.id)
}

function handleAuditToolSelectionChange(rows) {
  selectedAuditToolIds.value = rows.map(item => item.id)
}

function handleAuditSkillTraceSelectionChange(rows) {
  selectedAuditSkillTraceIds.value = rows.map(item => item.id)
}

function handleAuditActionTraceSelectionChange(rows) {
  selectedAuditActionTraceIds.value = rows.map(item => item.id)
}

function handleAuditActionSelectionChange(rows) {
  selectedAuditActionIds.value = rows.map(item => item.id)
}

async function handleDeleteAuditSession(row) {
  await ElMessageBox.confirm(`确认删除会话《${row.title}》吗？该操作不可恢复。`, '删除确认', { type: 'warning' })
  const shouldFallbackPage = auditSessions.value.length === 1 && auditSessionPagination.page > 1
  await deleteAIOpsAuditSession(row.id)
  ElMessage.success('会话已删除')
  await Promise.all([loadOverview(), loadAuditSessions(shouldFallbackPage ? auditSessionPagination.page - 1 : auditSessionPagination.page)])
}

async function handleBatchDeleteAuditSessions() {
  if (!selectedAuditSessionIds.value.length) return
  await ElMessageBox.confirm(`确认批量删除已选中的 ${selectedAuditSessionIds.value.length} 个会话吗？该操作不可恢复。`, '批量删除确认', { type: 'warning' })
  const shouldFallbackPage = selectedAuditSessionIds.value.length === auditSessions.value.length && auditSessionPagination.page > 1
  const deletedCount = selectedAuditSessionIds.value.length
  await bulkDeleteAIOpsAuditSessions(selectedAuditSessionIds.value)
  ElMessage.success(`已删除 ${deletedCount} 个会话`)
  await Promise.all([loadOverview(), loadAuditSessions(shouldFallbackPage ? auditSessionPagination.page - 1 : auditSessionPagination.page)])
}

async function handleDeleteAuditTool(row) {
  await ElMessageBox.confirm(`确认删除工具调用《${row.tool_name}》吗？该操作不可恢复。`, '删除确认', { type: 'warning' })
  const shouldFallbackPage = auditTools.value.length === 1 && auditToolPagination.page > 1
  await deleteAIOpsAuditToolInvocation(row.id)
  ElMessage.success('工具调用已删除')
  await Promise.all([loadOverview(), loadAuditTools(shouldFallbackPage ? auditToolPagination.page - 1 : auditToolPagination.page)])
}

async function handleBatchDeleteAuditTools() {
  if (!selectedAuditToolIds.value.length) return
  const shouldFallbackPage = selectedAuditToolIds.value.length === auditTools.value.length && auditToolPagination.page > 1
  const deletedCount = selectedAuditToolIds.value.length
  await ElMessageBox.confirm(`确认批量删除已选中的 ${deletedCount} 个工具调用吗？该操作不可恢复。`, '批量删除确认', { type: 'warning' })
  await bulkDeleteAIOpsAuditToolInvocations(selectedAuditToolIds.value)
  ElMessage.success(`已删除 ${deletedCount} 个工具调用`)
  await Promise.all([loadOverview(), loadAuditTools(shouldFallbackPage ? auditToolPagination.page - 1 : auditToolPagination.page)])
}

async function handleDeleteAuditSkillTrace(row) {
  await ElMessageBox.confirm(`确认删除 Skill 命中《${row.name || row.slug || '-'}》吗？该操作不可恢复。`, '删除确认', { type: 'warning' })
  const shouldFallbackPage = auditSkillTraces.value.length === 1 && auditSkillTracePagination.page > 1
  await bulkDeleteAIOpsAuditSkillTraces([row.id])
  ElMessage.success('Skill 命中记录已删除')
  await loadAuditSkillTraces(shouldFallbackPage ? auditSkillTracePagination.page - 1 : auditSkillTracePagination.page)
}

async function handleBatchDeleteAuditSkillTraces() {
  if (!selectedAuditSkillTraceIds.value.length) return
  const shouldFallbackPage = selectedAuditSkillTraceIds.value.length === auditSkillTraces.value.length && auditSkillTracePagination.page > 1
  const deletedCount = selectedAuditSkillTraceIds.value.length
  await ElMessageBox.confirm(`确认批量删除已选中的 ${deletedCount} 个 Skill 命中记录吗？该操作不可恢复。`, '批量删除确认', { type: 'warning' })
  await bulkDeleteAIOpsAuditSkillTraces(selectedAuditSkillTraceIds.value)
  ElMessage.success(`已删除 ${deletedCount} 个 Skill 命中记录`)
  await loadAuditSkillTraces(shouldFallbackPage ? auditSkillTracePagination.page - 1 : auditSkillTracePagination.page)
}

async function handleDeleteAuditActionTrace(row) {
  await ElMessageBox.confirm(`确认删除问答类型命中《${row.display_name || row.code || '-'}》吗？该操作不可恢复。`, '删除确认', { type: 'warning' })
  const shouldFallbackPage = auditActionTraces.value.length === 1 && auditActionTracePagination.page > 1
  await bulkDeleteAIOpsAuditActionTraces([row.id])
  ElMessage.success('问答类型命中记录已删除')
  await loadAuditActionTraces(shouldFallbackPage ? auditActionTracePagination.page - 1 : auditActionTracePagination.page)
}

async function handleBatchDeleteAuditActionTraces() {
  if (!selectedAuditActionTraceIds.value.length) return
  const shouldFallbackPage = selectedAuditActionTraceIds.value.length === auditActionTraces.value.length && auditActionTracePagination.page > 1
  const deletedCount = selectedAuditActionTraceIds.value.length
  await ElMessageBox.confirm(`确认批量删除已选中的 ${deletedCount} 个问答类型命中记录吗？该操作不可恢复。`, '批量删除确认', { type: 'warning' })
  await bulkDeleteAIOpsAuditActionTraces(selectedAuditActionTraceIds.value)
  ElMessage.success(`已删除 ${deletedCount} 个问答类型命中记录`)
  await loadAuditActionTraces(shouldFallbackPage ? auditActionTracePagination.page - 1 : auditActionTracePagination.page)
}

async function handleDeleteAuditModel(row) {
  await ElMessageBox.confirm(`确认删除模型调用《${row.resolved_model || row.requested_model || '-'}》吗？该操作不可恢复。`, '删除确认', { type: 'warning' })
  const shouldFallbackPage = auditModels.value.length === 1 && auditModelPagination.page > 1
  await deleteAIOpsAuditModelInvocation(row.id)
  ElMessage.success('模型调用已删除')
  await Promise.all([loadOverview(), loadAuditModels(shouldFallbackPage ? auditModelPagination.page - 1 : auditModelPagination.page)])
}

async function handleDeleteAuditAction(row) {
  await ElMessageBox.confirm(`确认删除动作《${row.title}》吗？该操作不可恢复。`, '删除确认', { type: 'warning' })
  const shouldFallbackPage = auditActions.value.length === 1 && auditActionPagination.page > 1
  await deleteAIOpsAuditAction(row.id)
  ElMessage.success('动作已删除')
  await Promise.all([loadOverview(), loadAuditActions(shouldFallbackPage ? auditActionPagination.page - 1 : auditActionPagination.page)])
}

async function handleBatchDeleteAuditActions() {
  if (!selectedAuditActionIds.value.length) return
  const shouldFallbackPage = selectedAuditActionIds.value.length === auditActions.value.length && auditActionPagination.page > 1
  const deletedCount = selectedAuditActionIds.value.length
  await ElMessageBox.confirm(`确认批量删除已选中的 ${deletedCount} 个动作吗？该操作不可恢复。`, '批量删除确认', { type: 'warning' })
  await bulkDeleteAIOpsAuditActions(selectedAuditActionIds.value)
  ElMessage.success(`已删除 ${deletedCount} 个动作`)
  await Promise.all([loadOverview(), loadAuditActions(shouldFallbackPage ? auditActionPagination.page - 1 : auditActionPagination.page)])
}

watch(
  () => [route.query.tab, route.query.session_id, route.query.message_id],
  async ([tab]) => {
    const nextTab = normalizeTab(tab)
    if (activeTab.value !== nextTab) activeTab.value = nextTab
    if (route.query.tab !== nextTab) {
      await syncRouteTab(nextTab)
      return
    }
    if (nextTab === 'overview') {
      await loadOverview()
    } else {
      await loadActiveTabPage(1)
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.audit-session-link { max-width: 100%; vertical-align: middle; }
.audit-session-link :deep(span) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.audit-session-actions { display: inline-flex; align-items: center; flex-wrap: nowrap; gap: 12px; white-space: nowrap; }
.audit-session-actions :deep(.el-button) { margin-left: 0; flex-shrink: 0; }
.aiops-audit-page {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.panel,
.workbench-card {
  background: linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(250,252,255,.96) 100%);
  border: 1px solid rgba(15,23,42,.08);
  border-radius: 18px;
  box-shadow: 0 8px 24px rgba(15,23,42,.04);
  padding: 14px 16px;
}

.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 0;
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36,91,219,.09);
}

.release-hero-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.release-hero-copy {
  min-width: 0;
}

.hero h2 {
  color: #0f172a;
  font-size: 23px;
  margin: 0;
}

.page-inline-desc {
  color: #475569;
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
  transform: translateY(1px);
}

.audit-header-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #245bdb;
  background: linear-gradient(180deg,#f3f7ff 0%,#ebf2ff 100%);
  border: 1px solid rgba(36,91,219,.12);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.8);
}

.hero.panel {
  border-radius: 20px;
}

.audit-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}

.audit-card {
  border-radius: 14px;
  border: 1px solid rgba(15,23,42,.08);
  background: linear-gradient(180deg,rgba(255,255,255,.98) 0%,rgba(252,253,255,.94) 100%);
  box-shadow: 0 4px 14px rgba(15,23,42,.03);
}

.audit-card--inline {
  min-height: 68px;
  padding: 14px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.audit-card .stat-label {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.audit-card .stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #1f2329;
}

.audit-card--warning {
  background: linear-gradient(180deg,#fffdfa 0%,#ffffff 100%);
}

.audit-card--success {
  background: linear-gradient(180deg,#fbfffd 0%,#ffffff 100%);
}

.audit-card--danger {
  background: linear-gradient(180deg,#fffafb 0%,#ffffff 100%);
}

.audit-card--action {
  cursor: pointer;
  text-align: left;
}

.audit-card--action:hover {
  border-color: rgba(36,91,219,.16);
  box-shadow: 0 10px 20px rgba(36,91,219,.06);
}

.audit-card--action.is-active {
  border-color: rgba(36,91,219,.24);
  background: linear-gradient(180deg,#f4f7ff 0%,#ffffff 100%);
  box-shadow: 0 0 0 1px rgba(36,91,219,.05),0 12px 22px rgba(36,91,219,.08);
}

.audit-tabs {
  display: flex;
  width: 100%;
  margin: 0;
  padding: 3px;
  gap: 8px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.9));
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.025);
}

.audit-correlation-scope { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; color: var(--text-secondary); font-size: 12px; }

.audit-tab-btn {
  min-height: 38px;
  padding: 0 18px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #4e5969;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.2;
  gap: 6px;
}

.audit-tab-btn:hover {
  background: rgba(51,112,255,.06);
}

.audit-tabs.theme-blue .audit-tab-btn.active {
  color: #245bdb;
  background: #e8f0ff;
  box-shadow: inset 0 0 0 1px rgba(51, 112, 255, 0.08);
}

.audit-tab-btn .el-icon {
  margin: 0;
  font-size: 15px;
}

.audit-tab-btn .tab-label {
  font-size: 13px;
  font-weight: 700;
  line-height: 1.1;
}

.audit-subtabs {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  margin-bottom: 8px;
  padding: 3px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.82);
}

.audit-subtab-btn {
  min-height: 32px;
  padding: 0 14px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #4e5969;
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
}

.audit-subtab-btn:hover {
  background: rgba(51, 112, 255, 0.06);
}

.audit-subtab-btn.active {
  color: #245bdb;
  background: #e8f0ff;
  box-shadow: inset 0 0 0 1px rgba(51, 112, 255, 0.08);
}

.section-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.toolbar-head {
  display: inline-flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
}

.toolbar-title,
.section-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
}

.toolbar-desc {
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

.workbench-card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.overview-time-controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.overview-time-picker {
  width: 330px;
}

.overview-time-picker :deep(.el-range-separator) {
  color: #94a3b8;
  font-size: 12px;
}

.filter-refresh-btn {
  min-height: 28px;
}

.audit-flat-action-btn {
  height: 28px;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  box-shadow: none;
}

.audit-flat-action-btn :deep(.el-icon),
.audit-flat-action-btn .el-icon {
  margin-right: 4px;
  font-size: 14px;
}

.audit-flat-action-btn.el-button--danger.is-plain {
  color: #dc2626;
  border-color: rgba(220, 38, 38, 0.18);
  background: rgba(254, 242, 242, 0.72);
}

.audit-flat-action-btn.el-button--danger.is-plain:hover {
  color: #b91c1c;
  border-color: rgba(220, 38, 38, 0.28);
  background: rgba(254, 226, 226, 0.86);
}

.audit-flat-action-btn.is-disabled,
.audit-flat-action-btn.is-disabled:hover {
  color: #94a3b8;
  border-color: rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.8);
}

.audit-list-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  margin-bottom: 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.88));
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.03);
}

.audit-list-toolbar .workbench-toolbar-left,
.audit-list-toolbar .workbench-toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}

.audit-list-toolbar .workbench-toolbar-left {
  flex: 1 1 auto;
}

.audit-list-toolbar .workbench-toolbar-right {
  flex: 0 0 auto;
  justify-content: flex-end;
}

.audit-list-toolbar :deep(.el-input),
.audit-list-toolbar :deep(.el-select) {
  width: 112px;
}

.audit-filter-search {
  width: 220px !important;
}

.audit-filter-user {
  width: 112px !important;
}

.audit-filter-time {
  width: 310px !important;
}

.audit-page-size-label {
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.audit-page-size-select {
  width: 94px !important;
}

.overview-dashboard-grid {
  display: grid;
  grid-template-columns: 1fr;
  align-items: start;
  gap: 10px;
}

.overview-invocation-section {
  min-width: 0;
}

.overview-panel {
  min-width: 0;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(15,23,42,.08);
  background: linear-gradient(180deg, rgba(255,255,255,.99) 0%, rgba(249,251,253,.96) 100%);
  box-shadow: 0 4px 14px rgba(15,23,42,.03);
}

.overview-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.overview-panel-head p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.overview-panel--model .section-title {
  font-size: 13px;
  line-height: 1.2;
}

.overview-mini-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.overview-mini-stat {
  min-height: 58px;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(148,163,184,.18);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.9), rgba(255, 255, 255, 0.72));
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
}

.overview-mini-stat span {
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
}

.overview-mini-stat strong {
  color: #111827;
  font-size: 16px;
  font-weight: 760;
  line-height: 1.15;
}

.invocation-chart-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.invocation-chart-card {
  min-width: 0;
  padding: 9px 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.78);
}

.invocation-chart-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.invocation-chart-head strong {
  min-width: 0;
  overflow: hidden;
  color: #0f172a;
  font-size: 13px;
  font-weight: 760;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.invocation-pie-layout {
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr;
  justify-items: center;
  gap: 10px;
}

.invocation-pie {
  position: relative;
  width: 152px;
  aspect-ratio: 1;
  justify-self: center;
  display: grid;
  place-items: center;
  border-radius: 50%;
  box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.06), 0 10px 24px rgba(15, 23, 42, 0.06);
}

.invocation-pie-core {
  width: 86px;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 3px;
  border-radius: 50%;
  background: linear-gradient(180deg, #fff 0%, #f8fafc 100%);
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.14);
}

.invocation-pie-core strong {
  color: #0f172a;
  font-size: 20px;
  font-weight: 780;
  line-height: 1;
}

.invocation-pie-core span {
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
}

.invocation-pie-tooltip {
  position: absolute;
  z-index: 2;
  max-width: 132px;
  padding: 5px 7px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.9);
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.16);
  color: #fff;
  pointer-events: none;
  text-align: left;
  transform: translate(-50%, calc(-100% - 8px));
}

.invocation-pie-tooltip strong,
.invocation-pie-tooltip span {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.invocation-pie-tooltip strong {
  font-size: 11px;
  font-weight: 760;
  line-height: 1.25;
}

.invocation-pie-tooltip span {
  margin-top: 2px;
  color: rgba(255, 255, 255, 0.78);
  font-size: 10px;
  font-weight: 700;
  line-height: 1.2;
}

.invocation-pie-legend {
  width: 100%;
  min-width: 0;
  height: calc(24px * 3 + 4px * 2);
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.invocation-pie-row {
  box-sizing: border-box;
  min-width: 0;
  height: 24px;
  flex: 0 0 24px;
  padding: 0 6px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 8px;
  background: rgba(248, 250, 252, 0.62);
  display: flex;
  align-items: center;
}

.invocation-pie-row-head {
  width: 100%;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 5px;
}

.invocation-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  box-shadow: 0 0 0 2px rgba(148, 163, 184, 0.08);
}

.invocation-pie-row-head span:not(.invocation-dot) {
  min-width: 0;
  overflow: hidden;
  color: #334155;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.invocation-pie-row-head em {
  color: #94a3b8;
  font-size: 11px;
  font-style: normal;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
}

.invocation-pie-row-head strong {
  color: #0f172a;
  font-size: 12px;
  font-weight: 760;
  line-height: 1.2;
  white-space: nowrap;
}

.overview-rank-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.overview-rank-row {
  min-height: 54px;
  padding: 8px 10px;
  border-radius: 12px;
  border: 1px solid rgba(148,163,184,.16);
  background: rgba(255,255,255,.78);
}

.overview-rank-main {
  min-width: 0;
}

.overview-rank-title,
.overview-rank-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.overview-rank-title span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #1f2937;
  font-size: 13px;
  font-weight: 700;
}

.overview-rank-title strong {
  color: #0f172a;
  font-size: 13px;
  font-weight: 760;
  white-space: nowrap;
}

.overview-rank-meta {
  justify-content: flex-start;
  margin-top: 4px;
  color: #64748b;
  font-size: 11px;
  flex-wrap: wrap;
}

.overview-rank-bar {
  height: 5px;
  margin-top: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(226,232,240,.78);
}

.overview-rank-bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #60a5fa 0%, #2563eb 100%);
}

.overview-empty {
  min-height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed rgba(148,163,184,.32);
  border-radius: 12px;
  color: #94a3b8;
  font-size: 12px;
  background: rgba(248,250,252,.6);
}

.muted-text {
  color: #94a3b8;
  font-size: 12px;
}

.console-table {
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid #e2e8f0;
}

.console-table :deep(th.el-table__cell) {
  background: #f8fafc;
  color: #475569;
  font-weight: 700;
}

.audit-invocation-table :deep(.cell) {
  padding: 0 6px;
}

.audit-invocation-table :deep(.el-table__expand-icon) {
  width: 22px;
}

.audit-invocation-table :deep(.el-tag--small) {
  padding: 0 6px;
}

.audit-session-table :deep(.cell) {
  padding: 0 6px;
}

.audit-session-table {
  width: 100%;
  max-width: 100%;
}

.audit-session-table :deep(.el-table__expand-icon) {
  width: 22px;
}

.json-preview {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow: auto;
  margin: 0;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #334155;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.55;
}

.agent-trace-expand {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  padding: 10px 4px 4px;
}

.trace-panel {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.86));
}

.trace-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.trace-panel-head span {
  color: #0f172a;
  font-size: 13px;
  font-weight: 700;
}

.trace-panel-head small {
  min-width: 0;
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-pill-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.trace-pill {
  min-height: 28px;
  max-width: 100%;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.76);
}

.trace-pill strong {
  min-width: 0;
  overflow: hidden;
  color: #1f2937;
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-pill em {
  flex: 0 0 auto;
  color: #64748b;
  font-size: 11px;
  font-style: normal;
  font-weight: 700;
}

.trace-pill small {
  min-width: 0;
  overflow: hidden;
  color: #64748b;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-pill.is-matched,
.trace-pill.is-called {
  border-color: rgba(22, 163, 74, 0.2);
  background: rgba(240, 253, 244, 0.82);
}

.trace-pill.is-fallback {
  border-color: rgba(245, 158, 11, 0.22);
  background: rgba(255, 251, 235, 0.82);
}

.trace-empty {
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed rgba(148, 163, 184, 0.26);
  border-radius: 10px;
  color: #94a3b8;
  font-size: 12px;
  background: rgba(248, 250, 252, 0.58);
}

.trace-action-main {
  min-height: 44px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 4px 8px;
  align-items: center;
}

.trace-action-main strong {
  min-width: 0;
  overflow: hidden;
  color: #1f2937;
  font-size: 13px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-action-main span:last-child {
  grid-column: 1 / -1;
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.audit-action-hit {
  color: #245bdb;
  font-size: 12px;
  font-weight: 700;
}

.trace-name-cell {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.trace-name-cell strong {
  min-width: 0;
  overflow: hidden;
  color: #1f2937;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-name-cell small {
  min-width: 0;
  overflow: hidden;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-detail-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 10px 4px 4px;
}

.trace-detail-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.trace-detail-row {
  display: grid;
  grid-template-columns: 62px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.trace-detail-row span {
  color: #94a3b8;
  font-size: 12px;
  font-weight: 600;
}

.trace-detail-row strong {
  min-width: 0;
  overflow: hidden;
  color: #334155;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-detail-row--stack {
  grid-template-columns: 1fr;
  gap: 6px;
}

.trace-detail-tags {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
}

.pagination-row {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 10px;
}

.pagination-size-control {
  display: flex;
  align-items: center;
  gap: 6px;
}

.pagination-total :deep(.el-pagination__total) {
  margin-right: 0;
}

.pagination-pager {
  margin-left: 0;
}

@media (max-width: 860px) {
  .overview-dashboard-grid {
    grid-template-columns: 1fr;
  }

  .section-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .overview-time-controls {
    justify-content: flex-start;
    width: 100%;
  }

  .overview-time-picker {
    width: 100%;
  }

  .invocation-pie-layout {
    grid-template-columns: 1fr;
  }

  .invocation-pie {
    width: 128px;
  }

  .audit-list-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .audit-subtabs {
    overflow-x: auto;
  }

  .audit-subtab-btn {
    flex: 0 0 auto;
  }

  .audit-list-toolbar .workbench-toolbar-left,
  .audit-list-toolbar .workbench-toolbar-right {
    justify-content: flex-start;
    width: 100%;
  }

  .audit-list-toolbar :deep(.el-input),
  .audit-list-toolbar :deep(.el-select),
  .audit-filter-search,
  .audit-filter-user,
  .audit-filter-time {
    width: 100% !important;
  }

  .pagination-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .agent-trace-expand {
    grid-template-columns: 1fr;
  }

  .trace-detail-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .overview-mini-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .invocation-chart-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .hero {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
