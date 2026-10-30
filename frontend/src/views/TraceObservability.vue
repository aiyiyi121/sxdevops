<template>
  <div class="observability-page workbench-page-shell" :class="{ 'is-embedded': embeddedMode }">
    <section v-if="!embeddedMode" class="hero panel">
      <div class="hero-copy">
        <div class="hero-title-row">
          <span class="hero-icon">
            <el-icon><Connection /></el-icon>
          </span>
          <h2>{{ tracePageTitle }}</h2>
          <p class="page-inline-desc">{{ tracePageDescription }}</p>
        </div>
      </div>
      <div class="hero-actions">
        <template v-if="activeTraceTab === 'datasources' && !topologyOnly">
          <el-button size="small" @click="refreshTracingDataSourcePage" :loading="loading.datasources">
            <el-icon><RefreshRight /></el-icon>
            刷新数据源
          </el-button>
        </template>
        <template v-else>
          <el-button size="small" @click="loadTracingDataSources" :loading="loading.datasources">
            <el-icon><RefreshRight /></el-icon>
            刷新数据源
          </el-button>
          <el-button size="small" v-if="hasNativeTracingUi" type="primary" @click="openTracingUi">
            外部打开
          </el-button>
        </template>
      </div>
    </section>

    <ObservabilityRouteTabs v-if="!topologyOnly && activeTraceTab === 'datasources'" group="datasources" />

    <template v-if="activeTraceTab === 'traces' && canViewTrace">
    <div v-if="!topologyOnly" class="trace-query-layout">
      <section class="panel trace-query-unified-card">
        <div class="trace-query-unified-head">
          <div class="trace-query-title-block">
            <div class="trace-query-title-row">
              <h3>Trace 查询</h3>
            </div>
          </div>
          <div class="trace-query-actions">
            <el-button size="small" type="primary" class="search-action-primary" @click="runSearch()" :loading="loading.search">查询 Trace</el-button>
            <el-button size="small" plain class="search-action-secondary" @click="resetFilters">重置</el-button>
          </div>
        </div>

        <div class="trace-query-unified-body">
          <div class="trace-query-provider-strip">
            <div class="trace-filter-datasource-row">
              <span class="trace-query-provider-label">数据源</span>
              <el-select
                v-model="filters.datasourceId"
                class="search-control trace-datasource-control"
                size="small"
                clearable
                filterable
                placeholder="选择当前 Provider 下的数据源"
                :disabled="!canViewTraceDataSources || !filteredTracingDataSources.length"
                @change="changeDataSource"
              >
                <el-option
                  v-for="item in filteredTracingDataSources"
                  :key="item.id"
                  :label="`${item.name}${item.is_default ? '（默认）' : ''}（${providerNameByKey(item.provider)}）`"
                  :value="String(item.id)"
                />
              </el-select>
            </div>
          </div>

          <div class="search-panel search-panel--merged">
            <div class="trace-filter-service-row">
              <div class="trace-filter-grid trace-filter-grid--primary">
                <div class="trace-inline-filter">
                  <span class="trace-inline-filter__label">服务</span>
                  <el-select v-model="filters.serviceId" class="search-control" size="small" clearable filterable placeholder="选择服务">
                    <el-option v-for="item in services" :key="item.id" :label="item.name" :value="item.id" />
                  </el-select>
                </div>
                <div class="trace-inline-filter">
                  <span class="trace-inline-filter__label">Trace</span>
                  <el-input class="search-control" size="small" v-model.trim="filters.traceId" placeholder="输入 Trace ID 直达" clearable />
                </div>
                <div class="trace-inline-filter">
                  <span class="trace-inline-filter__label">关键字</span>
                  <el-input class="search-control" size="small" v-model.trim="filters.keyword" placeholder="接口 / 服务名 / 关键字" clearable />
                </div>
                <div class="trace-inline-filter trace-inline-filter--compact">
                  <span class="trace-inline-filter__label">数量</span>
                  <el-input-number class="search-number advanced-filter-control advanced-filter-number" size="small" v-model="filters.limit" :min="5" :max="50" :step="5" />
                </div>
              </div>
            </div>

            <div class="trace-filter-grid trace-filter-grid--advanced trace-filter-grid--toolbar">
              <div class="trace-inline-filter trace-inline-filter--compact">
                <span class="trace-inline-filter__label">状态</span>
                <el-select v-model="filters.traceState" class="search-control advanced-filter-control" size="small" placeholder="全部状态">
                  <el-option label="全部状态" value="ALL" />
                  <el-option label="正常链路" value="SUCCESS" />
                  <el-option label="错误链路" value="ERROR" />
                </el-select>
              </div>
              <div class="trace-inline-filter trace-inline-filter--compact">
                <span class="trace-inline-filter__label">排序</span>
                <el-select v-model="filters.sortBy" class="search-control advanced-filter-control" size="small" placeholder="最近开始">
                  <el-option label="最近开始" value="latest" />
                  <el-option label="最慢优先" value="slowest" />
                  <el-option label="错误优先" value="errors" />
                </el-select>
              </div>
              <div class="trace-inline-filter trace-inline-filter--time">
                <span class="trace-inline-filter__label">时间</span>
                <el-date-picker
                  v-model="filters.timeRange"
                  class="search-control time-range-picker advanced-filter-time"
                  size="small"
                  type="datetimerange"
                  range-separator="至"
                  start-placeholder="开始"
                  end-placeholder="结束"
                  format="YYYY-MM-DD HH:mm"
                  unlink-panels
                  :shortcuts="timeRangeShortcuts"
                />
              </div>
            </div>

            <div class="search-summary-bar trace-query-summary-bar">
              <span v-for="item in searchPanelSummary" :key="item.label" class="query-pill">
                {{ item.label }}：{{ item.value }}
              </span>
            </div>
          </div>
        </div>
      </section>

      <section class="panel trace-info-panel compact-info-panel">
        <div class="section-head trace-info-head">
          <h3>当前数据源</h3>
          <el-tag v-if="selectedTracingDataSource" size="small" :type="traceProviderTagType(selectedTracingDataSource.provider)">
            {{ providerNameByKey(selectedTracingDataSource.provider) }}
          </el-tag>
        </div>

        <div v-if="selectedTracingDataSource" class="trace-source-card">
          <div class="trace-source-title-row">
            <strong class="trace-source-title">{{ selectedTracingDataSource.name }}</strong>
            <div class="trace-source-tags">
              <el-tag size="small" :type="selectedTracingDataSource.is_enabled ? 'success' : 'info'">
                {{ selectedTracingDataSource.is_enabled ? '启用' : '停用' }}
              </el-tag>
              <el-tag v-if="selectedTracingDataSource.is_default" size="small" type="warning">默认</el-tag>
            </div>
          </div>
          <div v-if="selectedTracingDataSource.description" class="trace-source-desc">
            {{ selectedTracingDataSource.description }}
          </div>
          <div class="trace-summary-list">
            <div v-for="item in traceDatasourceSummary" :key="item.label" class="trace-summary-item">
              <span>{{ item.label }}</span>
              <strong :class="{ 'is-multiline': item.multiline }" :title="item.multiline ? undefined : item.value">{{ item.value }}</strong>
            </div>
          </div>
        </div>
        <el-empty v-else description="当前还未选择链路数据源" :image-size="72" />
      </section>
    </div>

    <section class="panel">
      <div class="section-head">
        <div class="section-title-inline">
          <h3>{{ embeddedMode ? '服务调用拓扑' : '调用拓扑' }}</h3>
          <span v-if="embeddedMode" class="section-title-desc">服务调用链路从链路追踪获取，请关联好链路追踪</span>
        </div>
        <div class="section-head-tags">
          <el-tag size="small" type="success">节点 {{ focusedTopology.node_count || 0 }}</el-tag>
          <el-tag size="small" type="warning">调用 {{ focusedTopology.call_count || 0 }}</el-tag>
          <el-button size="small" text @click="topologyExpanded = !topologyExpanded">
            {{ topologyExpanded ? '收起' : '展开' }}
          </el-button>
        </div>
      </div>
      <button
        v-if="!topologyExpanded"
        type="button"
        class="compact-summary-bar compact-summary-bar--action"
        @click="topologyExpanded = true"
      >
        <span>节点 {{ focusedTopology.node_count || 0 }}</span>
        <span>调用 {{ focusedTopology.call_count || 0 }}</span>
        <span v-if="topologyHighlights.length">重点 {{ topologyHighlights[0].name }}</span>
        <strong class="compact-summary-bar__hint">点击展开</strong>
      </button>
      <div v-else class="topology-layout">
        <div ref="topologyChartRef" class="topology-chart" />
        <div class="topology-side">
          <div class="topology-list">
            <article
              v-for="item in pagedTopologyHighlights"
              :key="item.id"
              class="topology-item"
              :class="[`is-${item.role}`]"
            >
              <div class="topology-item-main">
                <strong :title="item.name">{{ item.shortName }}</strong>
                <span class="topology-item-role">{{ item.roleLabel }}</span>
              </div>
              <span class="topology-item-meta" :title="item.layer">{{ item.layer }}</span>
            </article>
          </div>
          <div v-if="topologyHighlights.length > TOPOLOGY_LIST_PAGE_SIZE" class="topology-pagination">
            <button
              type="button"
              class="trace-page-btn topology-page-btn"
              :disabled="topologyListPage <= 1"
              @click="topologyListPage -= 1"
            >
              上一页
            </button>
            <span class="trace-page-indicator">{{ topologyListPage }} / {{ topologyListPageCount }}</span>
            <button
              type="button"
              class="trace-page-btn topology-page-btn"
              :disabled="topologyListPage >= topologyListPageCount"
              @click="topologyListPage += 1"
            >
              下一页
            </button>
          </div>
        </div>
      </div>
    </section>

    <div v-if="!topologyOnly" class="content-grid">
      <section class="panel traces-panel">
        <div class="section-head">
          <h3>链路列表</h3>
          <div class="section-head-tags">
            <el-tag size="small" type="info">命中 {{ searchSummary.match_count || displayTraces.length }} 条</el-tag>
            <el-tag size="small" effect="plain">排序 {{ sortLabel }}</el-tag>
          </div>
        </div>

        <el-empty v-if="!displayTraces.length && !loading.search" description="当前条件下未找到 Trace。" />

        <template v-else>
          <div class="trace-results" v-loading="loading.search">
            <article
              v-for="row in pagedDisplayTraces"
              :key="row.trace_id"
              class="trace-result-card"
              :class="{
                'is-active': row.trace_id === selectedTraceId,
                'is-error': row.is_error,
                'is-slow': Number(row.duration_ms || 0) >= slowThreshold,
              }"
            >
              <button type="button" class="trace-result-main" @click="selectTrace(row)">
                <div class="trace-result-line two-line-layout">
                  <div class="trace-title-row">
                    <span class="trace-accent-bar" :class="{ 'is-error': row.is_error, 'is-slow': Number(row.duration_ms || 0) >= slowThreshold }"></span>
                    <strong class="trace-result-operation" :title="tracePrimaryEndpoint(row)">{{ tracePrimaryEndpoint(row) }}</strong>
                  </div>
                  <div class="trace-meta-row">
                    <span class="trace-status-pill" :class="{ 'is-error': row.is_error }">
                      {{ row.is_error ? '失败' : '成功' }}
                    </span>
                    <span class="trace-duration-pill" :class="{ 'is-slow': Number(row.duration_ms || 0) >= slowThreshold }">
                      {{ formatDuration(row.duration_ms) }}
                    </span>
                    <span class="trace-result-time">{{ formatListTime(row.start) }}</span>
                  </div>
                </div>
              </button>
            </article>
          </div>

          <div v-if="displayTraces.length > TRACE_LIST_PAGE_SIZE" class="trace-pagination">
            <button
              type="button"
              class="trace-page-btn"
              :disabled="traceListPage <= 1"
              @click="traceListPage -= 1"
            >
              上一页
            </button>
            <span class="trace-page-indicator">{{ traceListPage }} / {{ traceListPageCount }}</span>
            <button
              type="button"
              class="trace-page-btn"
              :disabled="traceListPage >= traceListPageCount"
              @click="traceListPage += 1"
            >
              下一页
            </button>
          </div>
        </template>
      </section>

      <section class="panel detail-panel">
        <div class="section-head">
          <h3>Trace 详情</h3>
          <div class="section-head-tags">
            <el-tag v-if="selectedTraceId" size="small" type="warning">{{ selectedTraceId }}</el-tag>
          </div>
        </div>

        <el-empty v-if="!traceDetail && !loading.detail" description="选择一条 Trace 后查看 Span 详情。" />

        <template v-else>
          <div class="trace-workbench" v-loading="loading.detail">
            <div class="trace-header-card">
              <div class="trace-title-block">
                <div class="trace-title-row-main">
                  <span class="trace-provider-pill">{{ selectedProviderMeta?.provider_name || tracing.provider_name || 'Tracing' }}</span>
                  <h3>{{ traceTitle }}</h3>
                </div>
                <div class="trace-header-meta">
                  <div class="trace-id-row">
                    <span>Trace ID</span>
                    <code>{{ selectedTraceId || '--' }}</code>
                  </div>
                </div>
              </div>
              <div class="trace-kpi-grid">
                <div class="trace-kpi">
                  <span>Duration</span>
                  <strong>{{ formatDuration(traceDetail?.duration_ms) }}</strong>
                </div>
                <div class="trace-kpi">
                  <span>Services</span>
                  <strong>{{ traceDetail?.services?.length || 0 }}</strong>
                </div>
                <div class="trace-kpi">
                  <span>Spans</span>
                  <strong>{{ traceDetail?.span_count || 0 }}</strong>
                </div>
                <div class="trace-kpi danger-kpi">
                  <span>Errors</span>
                  <strong>{{ traceDetail?.error_count || 0 }}</strong>
                </div>
              </div>
              <div v-if="waterfallRows.length" class="trace-minimap trace-header-minimap">
                <div class="trace-minimap-head">
                  <strong>Trace Timeline</strong>
                </div>
                <div class="minimap-track">
                  <button
                    v-for="row in minimapRows"
                    :key="`minimap-${row.span_id}`"
                    type="button"
                    class="minimap-segment"
                    :class="{ 'is-error': row.is_error, 'is-selected': String(row.span_id) === selectedSpanId }"
                    :style="row.barStyle"
                    :title="`${row.endpoint_name || row.service_code} · ${formatDuration(row.duration_ms)}`"
                    @click="focusSpan(row.span_id)"
                  />
                </div>
              </div>
            </div>

            <div v-if="selectedTraceId" class="trace-context-actions">
              <div class="context-copy">
                <strong>排障联动</strong>
                <span>用 Trace ID、服务和时间窗口串起日志、看板、告警和发布。</span>
              </div>
              <div class="context-actions">
                <button v-if="canQueryLogs" type="button" class="context-action-btn primary" @click="openLogsForCurrentTrace">查日志</button>
                <button v-if="canViewGrafana" type="button" class="context-action-btn" @click="openGrafanaForTrace">查看板</button>
                <button v-if="canViewAlerts" type="button" class="context-action-btn" @click="openAlertsForTrace">查告警</button>
                <button v-if="canViewDeployments" type="button" class="context-action-btn" @click="openDeploymentsForTrace">看发布</button>
              </div>
            </div>

            <div v-if="traceDetail?.spans?.length" class="trace-insights">
              <button
                v-for="span in errorSpanHighlights"
                :key="`error-${span.span_id}`"
                type="button"
                class="insight-pill error-pill"
                @click="focusSpan(span.span_id)"
              >
                异常：{{ span.endpoint_name || span.service_code }} · {{ formatDuration(span.duration_ms) }}
              </button>
              <button
                v-for="span in slowSpanHighlights"
                :key="`slow-${span.span_id}`"
                type="button"
                class="insight-pill slow-pill"
                @click="focusSpan(span.span_id)"
              >
                慢调用：{{ span.endpoint_name || span.service_code }} · {{ formatDuration(span.duration_ms) }}
              </button>
              <span v-for="item in serviceHighlights" :key="item.service" class="insight-pill service-pill">
                {{ item.service }} · {{ item.count }} spans
              </span>
            </div>

            <div class="span-toolbar">
              <el-input v-model.trim="spanUi.keyword" size="small" clearable placeholder="过滤 Span / Service / Tag" />
              <el-select v-model="spanUi.service" size="small" clearable filterable placeholder="全部服务">
                <el-option v-for="item in traceDetail?.services || []" :key="item" :label="item" :value="item" />
              </el-select>
              <div class="span-filter-toggle">
                <span class="span-filter-label">状态</span>
                <div class="span-filter-segment">
                  <button
                    type="button"
                    class="span-filter-option"
                    :class="{ 'is-active': !spanUi.errorsOnly }"
                    @click="spanUi.errorsOnly = false"
                  >
                    全部
                  </button>
                  <button
                    type="button"
                    class="span-filter-option"
                    :class="{ 'is-active': spanUi.errorsOnly }"
                    @click="spanUi.errorsOnly = true"
                  >
                    仅错误
                  </button>
                </div>
              </div>
              <div class="span-filter-toggle">
                <span class="span-filter-label">耗时</span>
                <div class="span-filter-segment">
                  <button
                    type="button"
                    class="span-filter-option"
                    :class="{ 'is-active': !spanUi.slowOnly }"
                    @click="spanUi.slowOnly = false"
                  >
                    全部耗时
                  </button>
                  <button
                    type="button"
                    class="span-filter-option"
                    :class="{ 'is-active': spanUi.slowOnly }"
                    @click="spanUi.slowOnly = true"
                  >
                    仅慢调用
                  </button>
                </div>
              </div>
            </div>

            <div v-if="waterfallRows.length" class="trace-timeline-card">
              <div class="timeline-axis-row">
                <span>Service & Operation</span>
                <div class="timeline-axis">
                  <span>0 ms</span>
                  <span class="timeline-axis-total">{{ formatDuration(traceDetail?.duration_ms) }}</span>
                </div>
                <span class="timeline-axis-duration-label">Duration</span>
                <span class="timeline-axis-action-placeholder"></span>
              </div>

              <div class="timeline-body">
                <template v-for="row in filteredTimelineRows" :key="`timeline-${row.span_id}`">
                  <div
                    class="timeline-row-shell"
                    :class="{
                      'is-error': row.is_error,
                      'is-slow': row.duration_ms >= slowThreshold,
                      'is-selected': String(row.span_id) === selectedSpanId,
                      'is-critical': criticalSpanIds.has(String(row.span_id)),
                    }"
                  >
                    <button
                      :id="`span-${selectedTraceId}-${row.span_id}`"
                      type="button"
                      class="timeline-row"
                      @click="toggleSpanDetails(row)"
                    >
                      <div class="timeline-label" :style="{ paddingLeft: `${row.depth * 16}px` }">
                        <span class="expand-mark">{{ isSpanExpanded(row.span_id) ? '▾' : '▸' }}</span>
                        <span class="service-dot" :style="{ background: row.serviceColor }"></span>
                        <div class="operation-cell">
                          <strong>{{ row.endpoint_name || row.service_code || 'Span' }}</strong>
                          <span>{{ row.service_code || '--' }} · {{ formatSpanKind(row.type) }} · {{ row.layer || 'UNSET' }}</span>
                        </div>
                      </div>
                      <div class="timeline-track">
                        <div class="timeline-bar" :style="row.barStyle"></div>
                      </div>
                      <span class="timeline-duration">{{ formatDuration(row.duration_ms) }}</span>
                    </button>
                    <el-tooltip v-if="canQueryLogs && selectedTraceId" content="查看当前 span 日志" placement="top">
                      <button type="button" class="timeline-log-action" @click.stop="openLogsForSpan(row)">
                        <svg viewBox="0 0 24 24" aria-hidden="true" class="timeline-log-icon">
                          <path d="M7.25 3.75h7.3l4.2 4.2v9.8a2 2 0 0 1-2 2h-9.5a2 2 0 0 1-2-2v-12a2 2 0 0 1 2-2Z" />
                          <path d="M14.55 3.75v4.2h4.2" />
                          <text x="6.45" y="16.15">LOG</text>
                        </svg>
                      </button>
                    </el-tooltip>
                  </div>

                  <div v-if="isSpanExpanded(row.span_id)" class="timeline-detail">
                    <div class="span-attribute-summary">
                      <span class="service-line" :style="{ background: row.serviceColor }"></span>
                      <span>Service: <strong>{{ row.service_code || '--' }}</strong></span>
                      <span>Duration: <strong>{{ formatDuration(row.duration_ms) }}</strong></span>
                      <span>Start: <strong>{{ formatTime(row.start_time) }}</strong></span>
                      <span>Child Count: <strong>{{ spanChildCount(row) }}</strong></span>
                      <span>Kind: <strong>{{ formatSpanKind(row.type) }}</strong></span>
                      <span>Status: <strong>{{ row.is_error ? 'error' : 'unset' }}</strong></span>
                      <span v-if="row.component">Library: <strong>{{ row.component }}</strong></span>
                      <span class="span-id-inline">SpanID: <strong>{{ row.span_id }}</strong></span>
                    </div>
                    <details class="attribute-section">
                      <summary>
                        <span class="attribute-chevron">⌄</span>
                        <strong>Span attributes</strong>
                        <span>{{ spanAttributes(row).length }} items</span>
                      </summary>
                      <div class="attribute-table">
                        <div v-for="attr in spanAttributes(row)" :key="`${row.span_id}-span-${attr.key}`" class="attribute-row">
                          <span>{{ attr.key }}</span>
                          <code>{{ formatAttributeValue(attr.value) }}</code>
                        </div>
                        <div v-if="!spanAttributes(row).length" class="attribute-empty">暂无 Span attributes</div>
                      </div>
                    </details>
                    <details class="attribute-section">
                      <summary>
                        <span class="attribute-chevron">⌄</span>
                        <strong>Resource attributes</strong>
                        <span>{{ resourceAttributes(row).length }} items</span>
                      </summary>
                      <div class="attribute-table">
                        <div v-for="attr in resourceAttributes(row)" :key="`${row.span_id}-resource-${attr.key}`" class="attribute-row">
                          <span>{{ attr.key }}</span>
                          <code>{{ formatAttributeValue(attr.value) }}</code>
                        </div>
                        <div v-if="!resourceAttributes(row).length" class="attribute-empty">暂无 Resource attributes</div>
                      </div>
                    </details>
                    <div v-if="row.logs?.length" class="span-log-list">
                      <div v-for="log in row.logs" :key="`${row.span_id}-${log.time}`" class="span-log-item">
                        <strong>{{ formatTime(log.time) }}</strong>
                        <span>{{ formatLog(log.data) }}</span>
                      </div>
                    </div>
                  </div>
                </template>
              </div>
            </div>

            <el-empty v-else description="当前 Trace 未返回 Span Timeline。" />
          </div>
        </template>
      </section>
    </div>

    <section v-if="!embeddedMode" class="panel embed-panel">
      <div class="section-head">
        <h3>外部链路平台</h3>
        <div class="section-head-tags">
          <el-button size="small" text @click="embedExpanded = !embedExpanded">
            {{ embedExpanded ? '收起' : '展开' }}
          </el-button>
          <el-button size="small" v-if="hasNativeTracingUi" link type="primary" @click="openTracingUi">外部打开</el-button>
        </div>
      </div>

      <div v-if="!embedExpanded" class="compact-summary-bar">
        <span>{{ selectedProviderMeta?.provider_name || '--' }}</span>
        <span>{{ selectedProviderMeta?.embed_url ? '已配置嵌入地址' : '未配置嵌入地址' }}</span>
      </div>
      <template v-else>
        <iframe v-if="selectedProviderMeta?.embed_url" class="embed-frame" :src="selectedProviderMeta.embed_url" title="Tracing" />
        <el-alert
          v-else
          title="当前 Provider 未配置可嵌入 UI，仍可使用平台内标准化链路查询。"
          type="info"
          show-icon
          :closable="false"
        />
      </template>
    </section>
    </template>

    <template v-else-if="activeTraceTab === 'datasources' && canViewTraceDataSources">
      <TracingDataSources ref="tracingDataSourcesPanelRef" class="workbench-fill-panel" embedded />
    </template>

  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Connection, RefreshRight } from '@element-plus/icons-vue'
import echarts from '@/lib/echarts'
import { getObservabilityOverview, getTraceDetail, getTracingCatalog, getTracingDataSources, resolveTraceToGrafana, resolveTraceToLogs, searchTracing } from '@/api/modules/ops'
import { useAuthStore } from '@/stores/auth'
import { openRouteInNewTab } from '@/utils/router'
import ObservabilityRouteTabs from '@/components/observability/ObservabilityRouteTabs.vue'
import TracingDataSources from './TracingDataSources.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const props = defineProps({
  embedded: {
    type: Boolean,
    default: false,
  },
  topology: {
    type: Boolean,
    default: false,
  },
  provider: {
    type: String,
    default: '',
  },
  datasourceId: {
    type: String,
    default: '',
  },
  service: {
    type: String,
    default: '',
  },
})
const loading = reactive({
  catalog: false,
  datasources: false,
  search: false,
  detail: false,
})

const overview = ref({ modules: {}, summary: {}, tips: [] })
const tracing = ref({})
const providers = ref([])
const tracingDataSources = ref([])
const tracingDataSourcesPanelRef = ref(null)
const services = ref([])
const traces = ref([])
const traceDetail = ref(null)
const selectedTraceId = ref('')
const selectedSpanId = ref('')
const topology = ref({})
const searchSummary = ref({})
const topologyChartRef = ref(null)
const expandedSpanIds = ref(new Set())
const topologyExpanded = ref(false)
const embedExpanded = ref(false)
const activeTraceTab = ref(route.query.tab === 'datasources' ? 'datasources' : 'traces')
const traceListPage = ref(1)
const topologyListPage = ref(1)

let topologyChart = null

const DEFAULT_DURATION_MINUTES = 30
const TRACE_LIST_PAGE_SIZE = 15
const TOPOLOGY_LIST_PAGE_SIZE = 6
const embeddedMode = computed(() => Boolean(props.embedded))
const topologyOnly = computed(() => Boolean(props.topology) || route.query.topology === '1')
const routeParams = computed(() => ({
  provider: props.provider || (typeof route.query.provider === 'string' ? route.query.provider : ''),
  datasourceId: props.datasourceId || (typeof route.query.datasourceId === 'string' ? route.query.datasourceId : ''),
  service: props.service || (typeof route.query.service === 'string' ? route.query.service : ''),
  traceId: typeof route.query.traceId === 'string' ? route.query.traceId : '',
  keyword: typeof route.query.keyword === 'string' ? route.query.keyword : '',
  window: route.query.window || '',
  from: route.query.from || '',
  to: route.query.to || '',
  topology: topologyOnly.value ? '1' : '',
}))
const tracePageTitle = computed(() => {
  if (topologyOnly.value) return 'Trace 调用拓扑'
  if (activeTraceTab.value === 'datasources') return '链路追踪数据源'
  return '链路追踪'
})
const tracePageDescription = computed(() => {
  if (topologyOnly.value) return '基于链路 Span 采样聚合服务间与服务到中间件 / DB 的调用关系'
  if (activeTraceTab.value === 'datasources') return '统一维护 SkyWalking、Tempo、Jaeger、Zipkin 等链路数据源配置'
  return '支持接入 SkyWalking 与 OpenTelemetry 生态下的 Zipkin、Jaeger、Tempo 等链路数据'
})

function buildRelativeTimeRange(minutes = DEFAULT_DURATION_MINUTES) {
  const safeMinutes = Math.max(5, Number(minutes || DEFAULT_DURATION_MINUTES))
  const end = new Date()
  const start = new Date(end.getTime() - safeMinutes * 60 * 1000)
  return [start, end]
}

const filters = reactive({
  provider: '',
  datasourceId: '',
  serviceId: '',
  traceState: 'ALL',
  durationMinutes: DEFAULT_DURATION_MINUTES,
  timeRange: buildRelativeTimeRange(DEFAULT_DURATION_MINUTES),
  keyword: '',
  traceId: '',
  limit: 20,
  sortBy: 'latest',
})

const spanUi = reactive({
  keyword: '',
  service: '',
  errorsOnly: false,
  slowOnly: false,
})

const durationOptions = [
  { label: '最近 15 分钟', value: 15 },
  { label: '最近 30 分钟', value: DEFAULT_DURATION_MINUTES },
  { label: '最近 1 小时', value: 60 },
  { label: '最近 6 小时', value: 360 },
]

const timeRangeShortcuts = durationOptions.map((item) => ({
  text: item.label,
  value: () => buildRelativeTimeRange(item.value),
}))

const slowThreshold = 800

const selectedProviderMeta = computed(() =>
  providers.value.find((item) => item.provider === filters.provider)
  || providers.value.find((item) => item.active)
  || tracing.value
)

const filteredTracingDataSources = computed(() =>
  tracingDataSources.value.filter((item) => item.is_enabled)
)

const selectedTracingDataSource = computed(() =>
  tracingDataSources.value.find((item) => String(item.id) === String(filters.datasourceId))
)

function preferredTracingDataSource(provider = '') {
  const enabled = tracingDataSources.value.filter((item) => item.is_enabled)
  const scoped = provider ? enabled.filter((item) => item.provider === provider) : enabled
  return scoped.find((item) => item.is_default) || scoped[0] || enabled.find((item) => item.is_default) || enabled[0] || null
}

const sortLabel = computed(() => ({
  latest: '最近开始',
  slowest: '最慢优先',
  errors: '错误优先',
}[filters.sortBy] || '最近开始'))

const searchPanelSummary = computed(() => {
  const items = [
    { label: 'Provider', value: selectedProviderMeta.value?.provider_name || '--' },
  ]
  if (selectedTracingDataSource.value?.name) {
    items.push({ label: '数据源', value: selectedTracingDataSource.value.name })
  }
  if (filters.serviceId) {
    items.push({ label: '服务', value: serviceNameById(filters.serviceId) || filters.serviceId })
  }
  items.push(
    { label: '时间', value: timeRangeSummary.value },
    { label: '状态', value: filters.traceState === 'ALL' ? '全部' : filters.traceState === 'ERROR' ? '错误' : '正常' },
    { label: '数量', value: `${filters.limit} 条` },
  )
  return items
})

const traceDatasourceSummary = computed(() => {
  const datasource = selectedTracingDataSource.value
  if (!datasource) return []
  const config = datasource.config || {}
  const items = [
    { label: '连接地址', value: formatDatasourceSummaryLines(datasource), multiline: true },
  ]
  if (datasource.provider === 'skywalking' && config.default_layer) {
    items.push({ label: '默认 Layer', value: config.default_layer })
  }
  return items
})

const canQueryLogs = computed(() => authStore.hasPermission('ops.log.query'))
const canViewTrace = computed(() => authStore.hasPermission('ops.trace.view'))
const canViewAlerts = computed(() => authStore.hasPermission('ops.alert.view'))
const canViewGrafana = computed(() => authStore.hasPermission('ops.grafana.view'))
const canViewDeployments = computed(() => authStore.hasAnyPermission(['ops.deployment.view', 'ops.deployment.manage', 'ops.deployment.approve']))
const canViewTraceDataSources = computed(() => authStore.hasPermission('ops.trace.datasource.view'))
const hasNativeTracingUi = computed(() => Boolean(selectedProviderMeta.value?.ui_url || selectedProviderMeta.value?.query_url || selectedProviderMeta.value?.oap_url))

const displayTraces = computed(() => {
  const items = [...traces.value]
  if (filters.sortBy === 'slowest') {
    return items.sort((a, b) => Number(b.duration_ms || 0) - Number(a.duration_ms || 0))
  }
  if (filters.sortBy === 'errors') {
    return items.sort((a, b) => Number(Boolean(b.is_error)) - Number(Boolean(a.is_error)) || Number(b.duration_ms || 0) - Number(a.duration_ms || 0))
  }
  return items.sort((a, b) => parseTimeValue(b.start) - parseTimeValue(a.start))
})

const pagedDisplayTraces = computed(() => {
  const startIndex = (traceListPage.value - 1) * TRACE_LIST_PAGE_SIZE
  return displayTraces.value.slice(startIndex, startIndex + TRACE_LIST_PAGE_SIZE)
})

const traceListPageCount = computed(() => Math.max(1, Math.ceil(displayTraces.value.length / TRACE_LIST_PAGE_SIZE)))

const traceListMaxDuration = computed(() =>
  Math.max(...displayTraces.value.map((item) => Number(item.duration_ms || 0)), slowThreshold, 1)
)

const topologyHighlights = computed(() =>
  (() => {
    const topologyData = focusedTopology.value || {}
    const nodes = topologyData.nodes || []
    const calls = topologyData.calls || []
    const selectedNodeId = String(topologyData.selected_node_id || '')
    const levels = new Map()
    if (selectedNodeId) {
      const outgoing = new Map()
      const incoming = new Map()
      calls.forEach((call) => {
        const sourceId = String(call.source || '')
        const targetId = String(call.target || '')
        if (!sourceId || !targetId) return
        if (!outgoing.has(sourceId)) outgoing.set(sourceId, new Set())
        if (!incoming.has(targetId)) incoming.set(targetId, new Set())
        outgoing.get(sourceId).add(targetId)
        incoming.get(targetId).add(sourceId)
      })
      const walk = (direction, step) => {
        const queue = [{ id: selectedNodeId, level: 0 }]
        const visited = new Set([selectedNodeId])
        while (queue.length) {
          const current = queue.shift()
          ;[...(direction.get(current.id) || [])].forEach((nextId) => {
            if (visited.has(nextId)) return
            visited.add(nextId)
            const nextLevel = current.level + step
            levels.set(nextId, nextLevel)
            queue.push({ id: nextId, level: nextLevel })
          })
        }
      }
      levels.set(selectedNodeId, 0)
      walk(outgoing, 1)
      walk(incoming, -1)
    }
    return nodes.map((item) => {
      const nodeId = String(item.id || '')
      const level = levels.get(nodeId)
      const hasIncoming = calls.some((call) => call.target === nodeId && call.source !== nodeId)
      const hasOutgoing = calls.some((call) => call.source === nodeId && call.target !== nodeId)
      const role = nodeId === selectedNodeId
        ? 'selected'
        : level < 0
          ? 'upstream'
          : level > 0
            ? 'downstream'
            : hasIncoming && !hasOutgoing
              ? 'downstream'
              : hasOutgoing && !hasIncoming
                ? 'upstream'
                : 'peer'
      return {
        id: item.id,
        name: item.name,
        shortName: ellipsisText(item.name, 20),
        layer: Array.isArray(item.layers) && item.layers.length ? item.layers.join(', ') : item.type || 'SERVICE',
        role,
        roleLabel: role === 'selected' ? '当前服务' : role === 'upstream' ? '上游' : role === 'downstream' ? '下游' : '关联',
      }
    })
  })()
    .sort((a, b) => {
      const order = { selected: 0, upstream: 1, downstream: 2, peer: 3 }
      return (order[a.role] ?? 9) - (order[b.role] ?? 9) || a.name.localeCompare(b.name)
    })
)

const pagedTopologyHighlights = computed(() => {
  const startIndex = (topologyListPage.value - 1) * TOPOLOGY_LIST_PAGE_SIZE
  return topologyHighlights.value.slice(startIndex, startIndex + TOPOLOGY_LIST_PAGE_SIZE)
})

const topologyListPageCount = computed(() => Math.max(1, Math.ceil(topologyHighlights.value.length / TOPOLOGY_LIST_PAGE_SIZE)))

const focusedTopology = computed(() => {
  const source = topology.value || {}
  const nodes = Array.isArray(source.nodes) ? source.nodes : []
  const calls = Array.isArray(source.calls) ? source.calls : []
  if (!filters.serviceId || !nodes.length) {
    return {
      node_count: source.node_count || nodes.length,
      call_count: source.call_count || calls.length,
      nodes,
      calls,
    }
  }

  const selectedService = services.value.find((item) => item.id === filters.serviceId)
  const candidateNames = new Set(
    [filters.serviceId, selectedService?.id, selectedService?.name, selectedService?.short_name]
      .map((item) => String(item || '').trim())
      .filter(Boolean)
  )

  const matchedNode = nodes.find((item) => candidateNames.has(String(item.id || '').trim()) || candidateNames.has(String(item.name || '').trim()))
  if (!matchedNode) {
    return {
      node_count: source.node_count || nodes.length,
      call_count: source.call_count || calls.length,
      nodes,
      calls,
    }
  }

  const selectedNodeId = matchedNode.id
  const selectedNodeKey = String(selectedNodeId)
  const adjacency = new Map()
  calls.forEach((item) => {
    const sourceId = String(item.source || '')
    const targetId = String(item.target || '')
    if (!sourceId || !targetId) return
    if (!adjacency.has(sourceId)) adjacency.set(sourceId, new Set())
    if (!adjacency.has(targetId)) adjacency.set(targetId, new Set())
    adjacency.get(sourceId).add(targetId)
    adjacency.get(targetId).add(sourceId)
  })

  const relatedNodeKeys = new Set([selectedNodeKey])
  const queue = [selectedNodeKey]
  while (queue.length) {
    const currentId = queue.shift()
    ;[...(adjacency.get(currentId) || [])].forEach((nextId) => {
      if (relatedNodeKeys.has(nextId)) return
      relatedNodeKeys.add(nextId)
      queue.push(nextId)
    })
  }

  const relatedCalls = calls.filter((item) => relatedNodeKeys.has(String(item.source || '')) && relatedNodeKeys.has(String(item.target || '')))
  const relatedNodeIds = new Set()
  relatedCalls.forEach((item) => {
    relatedNodeIds.add(String(item.source || ''))
    relatedNodeIds.add(String(item.target || ''))
  })
  relatedNodeIds.add(selectedNodeKey)

  const relatedNodes = nodes.filter((item) => relatedNodeIds.has(String(item.id || '')))
  return {
    node_count: relatedNodes.length,
    call_count: relatedCalls.length,
    selected_node_id: selectedNodeId,
    nodes: relatedNodes,
    calls: relatedCalls,
  }
})

const traceSpans = computed(() => traceDetail.value?.spans || [])

const errorSpanHighlights = computed(() =>
  [...traceSpans.value]
    .filter((item) => item.is_error)
    .sort((a, b) => Number(b.duration_ms || 0) - Number(a.duration_ms || 0))
    .slice(0, 3)
)

const slowSpanHighlights = computed(() =>
  [...traceSpans.value]
    .filter((item) => Number(item.duration_ms || 0) >= slowThreshold)
    .sort((a, b) => Number(b.duration_ms || 0) - Number(a.duration_ms || 0))
    .slice(0, 3)
)

const serviceHighlights = computed(() => {
  const summary = new Map()
  traceSpans.value.forEach((item) => {
    const service = item.service_code || 'unknown'
    const current = summary.get(service) || { service, count: 0, errorCount: 0, maxDuration: 0 }
    current.count += 1
    if (item.is_error) current.errorCount += 1
    current.maxDuration = Math.max(current.maxDuration, Number(item.duration_ms || 0))
    summary.set(service, current)
  })
  return [...summary.values()]
    .sort((a, b) => b.count - a.count || b.maxDuration - a.maxDuration)
    .slice(0, 6)
})

const rootSpan = computed(() =>
  traceSpans.value.find((item) => item.parent_span_id === -1 || item.parent_span_id === '-1' || item.parent_span_id === '' || item.parent_span_id === null)
  || traceSpans.value[0]
  || null
)

const traceTitle = computed(() =>
  rootSpan.value?.endpoint_name
  || rootSpan.value?.service_code
  || traceDetail.value?.service_name
  || 'Trace Timeline'
)

const traceContextService = computed(() =>
  traceDetail.value?.service_name
  || rootSpan.value?.service_code
  || serviceNameById(filters.serviceId)
  || filters.serviceId
  || ''
)

const timeRangeSummary = computed(() => {
  const [start, end] = normalizeTimeRange(filters.timeRange)
  if (!start || !end) return `${filters.durationMinutes} 分钟`
  return `${formatMinuteTime(start)} ~ ${formatMinuteTime(end)}`
})

const waterfallRows = computed(() => {
  const spans = traceSpans.value
  if (!spans.length) return []
  const spanMap = new Map(spans.map((item) => [String(item.span_id), item]))
  const depthCache = new Map()
  const spanColors = ['#2563eb', '#0f766e', '#ea580c', '#7c3aed', '#db2777', '#0891b2', '#65a30d', '#9333ea', '#d97706', '#0284c7']
  const spanAccentColors = ['#38bdf8', '#2dd4bf', '#fb923c', '#a78bfa', '#f472b6', '#22d3ee', '#a3e635', '#c084fc', '#fbbf24', '#67e8f9']
  const startValues = spans.map((item) => parseTimeValue(item.start_time)).filter(Boolean)
  const minStart = startValues.length ? Math.min(...startValues) : 0
  const total = Math.max(Number(traceDetail.value?.duration_ms || 0), 1)

  const calcDepth = (span) => {
    const key = String(span.span_id)
    if (depthCache.has(key)) return depthCache.get(key)
    const parent = spanMap.get(String(span.parent_span_id))
    const depth = parent ? calcDepth(parent) + 1 : 0
    depthCache.set(key, depth)
    return depth
  }

  return [...spans]
    .sort((a, b) => parseTimeValue(a.start_time) - parseTimeValue(b.start_time))
    .map((span, index) => {
      const start = parseTimeValue(span.start_time)
      const offset = Math.max(0, start - minStart)
      const left = (offset / total) * 100
      const width = Math.max((Number(span.duration_ms || 0) / total) * 100, 2)
      const spanColor = span.is_error ? '#ef4444' : spanColors[index % spanColors.length]
      const spanAccentColor = span.is_error ? '#f97316' : spanAccentColors[index % spanAccentColors.length]
      const safeLeft = Math.min(left, 98)
      const safeWidth = Math.min(width, 100 - safeLeft)
      return {
        ...span,
        depth: calcDepth(span),
        offset_ms: offset,
        left_pct: safeLeft,
        width_pct: safeWidth,
        serviceColor: spanColor,
        spanColor,
        barStyle: {
          left: `${safeLeft}%`,
          width: `${safeWidth}%`,
          background: `linear-gradient(90deg, ${spanColor}, ${spanAccentColor})`,
        },
      }
    })
})

const filteredTimelineRows = computed(() => {
  const keyword = spanUi.keyword.trim().toLowerCase()
  return waterfallRows.value.filter((row) => {
    if (spanUi.service && row.service_code !== spanUi.service) return false
    if (spanUi.errorsOnly && !row.is_error) return false
    if (spanUi.slowOnly && Number(row.duration_ms || 0) < slowThreshold) return false
    if (!keyword) return true
    const haystack = [
      row.endpoint_name,
      row.service_code,
      row.service_instance_name,
      row.peer,
      row.layer,
      ...(row.tags || []).map((tag) => `${tag.key} ${tag.value}`),
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(keyword)
  })
})

const minimapRows = computed(() => waterfallRows.value.slice(0, 80))

const criticalSpanIds = computed(() => {
  const rows = [...waterfallRows.value]
    .sort((a, b) => Number(b.duration_ms || 0) - Number(a.duration_ms || 0))
    .slice(0, Math.min(4, waterfallRows.value.length))
  if (rootSpan.value) rows.push(rootSpan.value)
  return new Set(rows.map((item) => String(item.span_id)))
})

function parseTimeValue(value) {
  return parseDateValue(value)?.getTime() || 0
}

function serviceNameById(serviceId) {
  return services.value.find((item) => item.id === serviceId)?.name || ''
}

function formatDuration(value) {
  return `${Number(value || 0)} ms`
}

function formatTime(value) {
  if (!value) return '--'
  const date = parseDateValue(value)
  return !date || Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

function formatListTime(value) {
  if (!value) return '--'
  const date = parseDateValue(value)
  if (!date || Number.isNaN(date.getTime())) return String(value)
  const now = new Date()
  const sameDay = date.getFullYear() === now.getFullYear()
    && date.getMonth() === now.getMonth()
    && date.getDate() === now.getDate()
  return date.toLocaleString('zh-CN', sameDay
    ? { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }
    : { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function parseDateValue(value) {
  if (value === undefined || value === null || value === '') return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value

  const raw = String(value).trim()
  if (!raw) return null

  const compactMatch = raw.match(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})?$/)
  if (compactMatch) {
    const [, year, month, day, hour, minute, second = '00'] = compactMatch
    const date = new Date(`${year}-${month}-${day}T${hour}:${minute}:${second}`)
    return Number.isNaN(date.getTime()) ? null : date
  }

  const numeric = Number(raw)
  if (Number.isFinite(numeric) && /^-?\d+(\.\d+)?$/.test(raw)) {
    const absValue = Math.abs(numeric)
    let milliseconds = numeric
    if (absValue < 100000000000) {
      milliseconds = numeric * 1000
    } else if (absValue >= 100000000000000000) {
      milliseconds = numeric / 1000000
    } else if (absValue >= 100000000000000) {
      milliseconds = numeric / 1000
    }
    const date = new Date(milliseconds)
    return Number.isNaN(date.getTime()) ? null : date
  }

  const normalized = raw.includes(' ') && !raw.includes('T') ? raw.replace(' ', 'T') : raw
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatLog(items = []) {
  return items.map((item) => `${item.key}: ${item.value}`).join(' | ')
}

function normalizeAttributes(items = []) {
  const seen = new Set()
  return (items || [])
    .map((item) => ({
      key: String(item?.key || '').trim(),
      value: item?.value,
    }))
    .filter((item) => item.key && item.value !== undefined && item.value !== null && String(item.value).trim() !== '')
    .filter((item) => {
      if (seen.has(item.key)) return false
      seen.add(item.key)
      return true
    })
}

function spanAttributes(row) {
  return normalizeAttributes(row?.tags || [])
}

function isResourceLikeAttribute(key) {
  const normalized = String(key || '').trim()
  if (!normalized) return false
  const resourceLikePrefixes = [
    'service.',
    'telemetry.',
    'otel.',
    'k8s.',
    'container.',
    'host.',
    'cloud.',
    'process.',
    'os.',
    'deployment.',
    'resource.',
    'faas.',
    'aws.',
    'gcp.',
    'azure.',
    'heroku.',
  ]
  const resourceLikeKeys = new Set([
    'service',
    'job',
    'instance',
    'namespace',
    'pod',
    'pod_name',
    'container_name',
    'node',
    'node_name',
    'cluster',
    'cluster_name',
    'environment',
    'env',
    'version',
    'hostname',
    'host.name',
    'host.hostname',
  ])
  return resourceLikePrefixes.some((prefix) => normalized.startsWith(prefix)) || resourceLikeKeys.has(normalized)
}

function resourceAttributes(row) {
  const attrs = normalizeAttributes([
    ...(row?.resource_tags || []),
    ...(row?.resourceTags || []),
    ...(row?.resource_attributes || []),
    ...(row?.resourceAttributes || []),
  ])
  const existing = new Set(attrs.map((item) => item.key))
  normalizeAttributes([
    ...(row?.scope_tags || []),
    ...(row?.scopeTags || []),
    ...(row?.scope_attributes || []),
    ...(row?.scopeAttributes || []),
    ...(row?.tags || []),
  ]).forEach((item) => {
    if (existing.has(item.key)) return
    if (!isResourceLikeAttribute(item.key)) return
    attrs.push(item)
    existing.add(item.key)
  })
  const fallback = [
    ['service.name', row?.service_code],
    ['service.instance.id', row?.service_instance_name],
    ['service.namespace', traceDetail.value?.service_namespace],
  ]
  fallback.forEach(([key, value]) => {
    if (!existing.has(key) && value !== undefined && value !== null && String(value).trim()) {
      attrs.push({ key, value })
      existing.add(key)
    }
  })
  const priority = ['service.name', 'service.namespace', 'service.version', 'service.instance.id']
  return attrs.sort((left, right) => {
    const leftIndex = priority.indexOf(left.key)
    const rightIndex = priority.indexOf(right.key)
    if (leftIndex !== -1 || rightIndex !== -1) {
      return (leftIndex === -1 ? 999 : leftIndex) - (rightIndex === -1 ? 999 : rightIndex)
    }
    return left.key.localeCompare(right.key)
  })
}

function formatAttributeValue(value) {
  if (typeof value === 'string') return value
  if (value === undefined || value === null) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function formatSpanKind(value) {
  const raw = String(value || '').trim()
  if (!raw) return 'span'
  return raw
    .replace(/^SPAN_KIND_/i, '')
    .replace(/^kind_/i, '')
    .replace(/^span_/i, '')
    .toLowerCase()
}

function spanChildCount(row) {
  const spanId = String(row?.span_id ?? '')
  if (!spanId) return 0
  return traceSpans.value.filter((item) => String(item.parent_span_id ?? '') === spanId).length
}

function normalizeTimeRange(value) {
  if (!Array.isArray(value) || value.length !== 2) return [null, null]
  const start = value[0] instanceof Date ? value[0] : new Date(value[0])
  const end = value[1] instanceof Date ? value[1] : new Date(value[1])
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return [null, null]
  return start.getTime() <= end.getTime() ? [start, end] : [end, start]
}

function minutesBetweenDates(start, end) {
  return Math.max(5, Math.ceil((end.getTime() - start.getTime()) / 60000))
}

function matchesDurationPreset(value, minutes) {
  const [start, end] = normalizeTimeRange(value)
  if (!start || !end) return false
  return Math.abs((end.getTime() - start.getTime()) - (minutes * 60 * 1000)) <= 60 * 1000
}

function syncDurationMinutesFromTimeRange() {
  const [start, end] = normalizeTimeRange(filters.timeRange)
  if (!start || !end) return
  filters.durationMinutes = minutesBetweenDates(start, end)
}

function formatMinuteTime(value) {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return '--'
  return date.toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function traceTimeRangePayload() {
  const [start, end] = normalizeTimeRange(filters.timeRange)
  if (!start || !end) return { start_time: '', end_time: '' }
  return {
    start_time: start.toISOString(),
    end_time: end.toISOString(),
  }
}

function formatDatasourceSummary(row) {
  const config = row?.config || {}
  if (row?.provider === 'skywalking') return [config.oap_url, config.ui_url].filter(Boolean).join(' / ') || '未配置 SkyWalking 地址'
  return [config.query_url, config.ui_url].filter(Boolean).join(' / ') || '未配置查询地址'
}

function formatDatasourceSummaryLines(row) {
  const config = row?.config || {}
  if (row?.provider === 'skywalking') return [config.oap_url, config.ui_url].filter(Boolean).join('\n') || '未配置 SkyWalking 地址'
  return [config.query_url, config.ui_url].filter(Boolean).join('\n') || '未配置查询地址'
}

function providerNameByKey(provider) {
  return providers.value.find((item) => item.provider === provider)?.provider_name || provider || '--'
}

function traceProviderTagType(provider) {
  return {
    skywalking: 'success',
    tempo: 'warning',
    jaeger: 'primary',
    zipkin: 'info',
  }[provider] || 'info'
}

function traceServiceName(row) {
  return row?.service_name || serviceNameById(row?.service_id) || '--'
}

function tracePrimaryEndpoint(row) {
  return (row?.endpoint_names || []).find(Boolean) || traceServiceName(row)
}

function shortTraceId(traceId) {
  const value = String(traceId || '')
  if (value.length <= 14) return value || '--'
  return `${value.slice(0, 6)}…${value.slice(-6)}`
}

function ellipsisText(value, max = 18) {
  const text = String(value || '')
  if (text.length <= max) return text || '--'
  return `${text.slice(0, Math.max(1, max - 1))}…`
}

function traceHeatStyle(row) {
  const value = Number(row?.duration_ms || 0)
  const ratio = Math.min(100, Math.max(8, (value / traceListMaxDuration.value) * 100))
  return {
    width: `${ratio}%`,
    background: row?.is_error
      ? 'linear-gradient(90deg, #ef4444, #f97316)'
      : value >= slowThreshold
        ? 'linear-gradient(90deg, #f59e0b, #f97316)'
        : 'linear-gradient(90deg, #2563eb, #38bdf8)',
  }
}

function focusSpan(spanId) {
  if (spanId === undefined || spanId === null || !selectedTraceId.value) return
  const next = new Set(expandedSpanIds.value)
  next.add(String(spanId))
  expandedSpanIds.value = next
  selectedSpanId.value = String(spanId)
  nextTick(() => {
    document.getElementById(`span-${selectedTraceId.value}-${spanId}`)?.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
    })
  })
}

function isSpanExpanded(spanId) {
  return expandedSpanIds.value.has(String(spanId))
}

function toggleSpanDetails(row) {
  const spanId = String(row?.span_id ?? '')
  if (!spanId) return
  const next = new Set(expandedSpanIds.value)
  if (next.has(spanId)) {
    next.delete(spanId)
  } else {
    next.add(spanId)
  }
  expandedSpanIds.value = next
  selectedSpanId.value = spanId
}

function resetSpanWorkbench(spans = []) {
  spanUi.keyword = ''
  spanUi.service = ''
  spanUi.errorsOnly = false
  spanUi.slowOnly = false
  const root = spans.find((item) => item.parent_span_id === -1 || item.parent_span_id === '-1' || item.parent_span_id === '' || item.parent_span_id === null) || spans[0]
  selectedSpanId.value = root ? String(root.span_id) : ''
  expandedSpanIds.value = root ? new Set([String(root.span_id)]) : new Set()
}

function resetFilters() {
  filters.traceState = 'ALL'
  filters.durationMinutes = DEFAULT_DURATION_MINUTES
  filters.timeRange = buildRelativeTimeRange(DEFAULT_DURATION_MINUTES)
  filters.keyword = ''
  filters.traceId = ''
  filters.limit = 20
  filters.sortBy = 'latest'
  if (services.value.length) {
    filters.serviceId = services.value[0].id
  }
}

function serviceIdFromRouteValue(raw) {
  if (!raw) return ''
  return services.value.find((item) => item.id === raw || item.name === raw || item.short_name === raw)?.id || ''
}

function routeWindowMinutes() {
  const raw = Number(routeParams.value.window || 0)
  if (!Number.isFinite(raw) || raw <= 0) return DEFAULT_DURATION_MINUTES
  return raw
}

function routeTimeRange() {
  const from = Number(routeParams.value.from || 0)
  const to = Number(routeParams.value.to || 0)
  if (Number.isFinite(from) && Number.isFinite(to) && from > 0 && to > 0) {
    return normalizeTimeRange([from, to])
  }
  return buildRelativeTimeRange(routeWindowMinutes())
}

async function loadOverview() {
  overview.value = await getObservabilityOverview({ provider: filters.provider, datasource_id: filters.datasourceId })
}

async function loadTracingDataSources() {
  if (!canViewTraceDataSources.value) {
    tracingDataSources.value = []
    return
  }
  loading.datasources = true
  try {
    const response = await getTracingDataSources({ is_enabled: 'true' })
    tracingDataSources.value = Array.isArray(response) ? response : response.results || []
  } finally {
    loading.datasources = false
  }
}

async function refreshTracingDataSourcePage() {
  loading.datasources = true
  try {
    await tracingDataSourcesPanelRef.value?.fetchDataSources?.()
    await loadTracingDataSources()
  } finally {
    loading.datasources = false
  }
}

function applyDefaultTracingDataSource() {
  if (filters.datasourceId) return false
  const datasource = preferredTracingDataSource(filters.provider)
  if (!datasource) return false
  filters.datasourceId = String(datasource.id)
  if (datasource.provider) {
    filters.provider = datasource.provider
  }
  return true
}

async function loadCatalog() {
  loading.catalog = true
  try {
    const response = await getTracingCatalog({ provider: filters.provider, datasource_id: filters.datasourceId })
    tracing.value = response.tracing || {}
    providers.value = response.providers || []
    services.value = response.services || []
    topology.value = response.topology || {}
    searchSummary.value = response.summary || {}
    traces.value = response.recent_traces || []
    if (!filters.provider) {
      filters.provider = response.tracing?.provider || providers.value[0]?.provider || 'demo'
    }
    if (!filters.datasourceId && response.tracing?.datasource_id) {
      filters.datasourceId = String(response.tracing.datasource_id)
    }
    if (!filters.serviceId && services.value.length) {
      filters.serviceId = services.value[0].id
    }
    await nextTick()
    renderTopology()
    if (traces.value.length) {
      await selectTrace(traces.value[0])
    }
  } finally {
    loading.catalog = false
  }
}

async function runSearch(selectFirst = true) {
  loading.search = true
  try {
    const rangePayload = traceTimeRangePayload()
    const response = await searchTracing({
      provider: filters.provider,
      datasource_id: filters.datasourceId,
      service_id: filters.serviceId,
      trace_state: filters.traceState,
      duration_minutes: filters.durationMinutes,
      start_time: rangePayload.start_time,
      end_time: rangePayload.end_time,
      keyword: filters.keyword,
      trace_id: filters.traceId,
      limit: filters.limit,
    })
    tracing.value = response.tracing || tracing.value
    providers.value = response.providers || providers.value
    services.value = response.services || services.value
    traces.value = response.traces || []
    searchSummary.value = response.summary || {}
    if (selectFirst && traces.value.length) {
      await selectTrace(traces.value[0])
    } else if (!traces.value.length) {
      selectedTraceId.value = ''
      selectedSpanId.value = ''
      expandedSpanIds.value = new Set()
      traceDetail.value = null
    }
  } finally {
    loading.search = false
  }
}

async function applyRouteTracePreset(force = false) {
  const traceId = String(routeParams.value.traceId || '').trim()
  const provider = String(routeParams.value.provider || '').trim()
  const datasourceId = String(routeParams.value.datasourceId || '').trim()
  const routeService = String(routeParams.value.service || '').trim()
  const routeKeyword = String(routeParams.value.keyword || '').trim()
  let contextChanged = false
  if (provider && provider !== filters.provider) {
    filters.provider = provider
    contextChanged = true
  }
  if (datasourceId && datasourceId !== filters.datasourceId) {
    filters.datasourceId = datasourceId
    contextChanged = true
  }
  if (contextChanged) {
    filters.serviceId = ''
    selectedTraceId.value = ''
    selectedSpanId.value = ''
    expandedSpanIds.value = new Set()
    traceDetail.value = null
    await loadOverview()
    await loadTracingDataSources()
    await loadCatalog()
  }

  filters.timeRange = routeTimeRange()
  syncDurationMinutesFromTimeRange()

  if (!traceId) {
    const nextServiceId = serviceIdFromRouteValue(routeService)
    const nextKeyword = routeKeyword || routeService
    if (!nextServiceId && !nextKeyword) {
      return contextChanged
    }
    if (!force && filters.traceId === '' && filters.serviceId === nextServiceId && filters.keyword === nextKeyword) {
      return false
    }
    filters.traceId = ''
    filters.keyword = nextKeyword
    filters.serviceId = nextServiceId
    filters.traceState = 'ALL'
    await runSearch(true)
    return true
  }

  if (!force && filters.traceId === traceId) return false
  filters.traceId = traceId
  filters.keyword = routeKeyword
  filters.serviceId = serviceIdFromRouteValue(routeService)
  filters.traceState = 'ALL'
  await runSearch(true)
  return true
}

async function loadTrace(traceId) {
  if (!traceId) return
  loading.detail = true
  try {
    const response = await getTraceDetail(traceId, { provider: filters.provider, datasource_id: filters.datasourceId })
    tracing.value = response.tracing || tracing.value
    providers.value = response.providers || providers.value
    traceDetail.value = response.trace || null
    selectedTraceId.value = traceId
    resetSpanWorkbench(response.trace?.spans || [])
  } finally {
    loading.detail = false
  }
}

async function selectTrace(row) {
  if (!row?.trace_id) return
  await loadTrace(row.trace_id)
}

async function refreshAll() {
  await loadTracingDataSources()
  await loadOverview()
  await loadCatalog()
  if (services.value.length) {
    await runSearch(false)
  }
}

function openTracingUi() {
  const url = selectedProviderMeta.value?.ui_url || selectedProviderMeta.value?.query_url || selectedProviderMeta.value?.oap_url
  if (url) window.open(url, '_blank', 'noopener,noreferrer')
}

async function changeProvider(provider) {
  if (!provider) return
  filters.provider = provider
  filters.datasourceId = ''
  filters.serviceId = ''
  selectedTraceId.value = ''
  selectedSpanId.value = ''
  expandedSpanIds.value = new Set()
  traceDetail.value = null
  await router.replace({
    path: route.path,
    query: {
      ...route.query,
      provider,
      datasourceId: undefined,
      traceId: undefined,
      service: undefined,
      keyword: undefined,
    },
  })
  await loadTracingDataSources()
  applyDefaultTracingDataSource(provider)
  await loadOverview()
  await loadCatalog()
}

async function changeDataSource(datasourceId) {
  filters.datasourceId = datasourceId || ''
  const datasource = selectedTracingDataSource.value
  if (datasource?.provider && datasource.provider !== filters.provider) {
    filters.provider = datasource.provider
  }
  filters.serviceId = ''
  selectedTraceId.value = ''
  selectedSpanId.value = ''
  expandedSpanIds.value = new Set()
  traceDetail.value = null
  await router.replace({
    path: route.path,
    query: {
      ...route.query,
      provider: filters.provider || undefined,
      datasourceId: filters.datasourceId || undefined,
      traceId: undefined,
      service: undefined,
      keyword: undefined,
    },
  })
  await loadOverview()
  await loadCatalog()
}

function traceTagsForLogJump(row) {
  const service = spanTraceService(row)
  const namespace = spanTraceNamespace(row)
  return {
    'service.name': service || '',
    'service.namespace': namespace || '',
  }
}

function traceLogTimeRange(row) {
  const start = parseDateValue(row?.start_time || rootSpan.value?.start_time)
  const durationMs = Number(row?.duration_ms || traceDetail.value?.duration_ms || 0)
  if (start) {
    const startMs = start.getTime()
    const endMs = startMs + Math.max(durationMs, 60 * 1000)
    return [startMs - 5 * 60 * 1000, endMs + 5 * 60 * 1000]
  }
  const [from, to] = normalizeTimeRange(filters.timeRange)
  return [from?.getTime(), to?.getTime()]
}

function spanTraceContextValue(row, keys = []) {
  const directSources = [
    row || {},
    rootSpan.value || {},
  ]
  for (const source of directSources) {
    for (const key of keys) {
      const value = source?.[key] ?? source?.[key.replace('.', '_')]
      if (typeof value === 'string' && value.trim()) return value.trim()
    }
  }

  const attributeRows = normalizeAttributes([
    ...(row?.resource_tags || []),
    ...(row?.resourceTags || []),
    ...(row?.resource_attributes || []),
    ...(row?.resourceAttributes || []),
    ...(row?.scope_tags || []),
    ...(row?.scopeTags || []),
    ...(row?.scope_attributes || []),
    ...(row?.scopeAttributes || []),
    ...(row?.tags || []),
    ...(rootSpan.value?.resource_tags || []),
    ...(rootSpan.value?.resourceTags || []),
    ...(rootSpan.value?.resource_attributes || []),
    ...(rootSpan.value?.resourceAttributes || []),
  ])
  for (const key of keys) {
    const rowItem = attributeRows.find((item) => item.key === key || item.key === key.replace('.', '_'))
    if (rowItem && String(rowItem.value).trim()) return String(rowItem.value).trim()
  }
  for (const key of keys) {
    const value = traceDetail.value?.[key] ?? traceDetail.value?.[key.replace('.', '_')]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}

function spanTraceService(row) {
  return row?.service_code
    || spanTraceContextValue(row, [
    'service.name',
    'service',
    'service_name',
    'serviceName',
    'service_code',
    'workload',
    'app',
    'application',
    'container',
    'container_name',
    'k8s.container.name',
  ]) || traceContextService.value || ''
}

function spanTraceNamespace(row) {
  return spanTraceContextValue(row, [
    'service.namespace',
    'namespace',
    'service_namespace',
    'serviceNamespace',
    'k8s.namespace.name',
    'kubernetes_namespace_name',
  ])
}

function spanTraceLogTitle(row) {
  const service = spanTraceService(row)
  const endpoint = row?.endpoint_name || ''
  if (service && endpoint) return `${service} / ${endpoint}`
  return service || endpoint || `Span ${row?.span_id || ''}`
}

async function openLogsForTrace(row) {
  if (!canQueryLogs.value || !row?.trace_id) return
  const [from, to] = traceLogTimeRange(row)
  const service = row.service_name || row.service_id || row.service || spanTraceService(row) || ''
  const namespace = row.service_namespace || row.namespace || spanTraceNamespace(row) || ''
  const title = row.title || ''
  try {
    const resolved = await resolveTraceToLogs({
      trace_id: row.trace_id,
      tracing_datasource_id: filters.datasourceId,
      tags: traceTagsForLogJump(row),
    })
    openRouteInNewTab(router, {
      path: '/logs/query',
      query: {
        traceId: row.trace_id,
        service: service || undefined,
        namespace: namespace || undefined,
        title: title || undefined,
        logProvider: resolved.log_datasource?.provider,
        logDatasourceId: resolved.log_datasource?.id ? String(resolved.log_datasource.id) : undefined,
        lokiQuery: resolved.query || undefined,
        window: String(resolved.window_minutes || filters.durationMinutes || 60),
        from,
        to,
        autoRun: '1',
      },
    })
  } catch {
    openRouteInNewTab(router, {
      path: '/logs/query',
      query: {
        traceId: row.trace_id,
        service: service || undefined,
        namespace: namespace || undefined,
        title: title || undefined,
        window: String(filters.durationMinutes || 60),
        from,
        to,
        autoRun: '1',
      },
    })
  }
}

function openLogsForCurrentTrace() {
  openLogsForTrace({
    trace_id: selectedTraceId.value,
    service_name: traceContextService.value,
    service_namespace: firstTraceContextValue(['service.namespace', 'namespace', 'k8s.namespace.name', 'kubernetes_namespace_name']),
    start_time: rootSpan.value?.start_time,
    duration_ms: traceDetail.value?.duration_ms,
  })
}

function openLogsForSpan(row) {
  if (!row || !selectedTraceId.value) return
  openLogsForTrace({
    trace_id: selectedTraceId.value,
    service_name: spanTraceService(row),
    service_namespace: spanTraceNamespace(row),
    start_time: row.start_time,
    duration_ms: row.duration_ms,
    tags: traceTagsForLogJump(row),
    title: spanTraceLogTitle(row),
  })
}

function openAlertsForTrace() {
  if (!canViewAlerts.value || !selectedTraceId.value) return
  openRouteInNewTab(router, {
    path: '/alerts',
    query: {
      search: traceContextService.value || selectedTraceId.value,
      level: traceDetail.value?.error_count ? 'critical' : undefined,
      ack: traceDetail.value?.error_count ? '0' : undefined,
    },
  })
}

function openDeploymentsForTrace() {
  if (!canViewDeployments.value || !selectedTraceId.value) return
  openRouteInNewTab(router, {
    path: '/workorders/releases',
    query: {
      keyword: traceContextService.value || traceTitle.value,
      service: traceContextService.value || undefined,
      traceId: selectedTraceId.value,
      source: 'trace',
    },
  })
}

function firstTraceContextValue(keys = []) {
  const directSources = [
    traceDetail.value || {},
    rootSpan.value || {},
    route.query || {},
  ]
  for (const source of directSources) {
    for (const key of keys) {
      const value = source?.[key] ?? source?.[key.replace('.', '_')]
      if (typeof value === 'string' && value.trim()) return value.trim()
    }
  }

  const attributeRows = normalizeAttributes([
    ...(rootSpan.value?.resource_tags || []),
    ...(rootSpan.value?.resourceTags || []),
    ...(rootSpan.value?.resource_attributes || []),
    ...(rootSpan.value?.resourceAttributes || []),
    ...(rootSpan.value?.tags || []),
  ])
  for (const key of keys) {
    const row = attributeRows.find((item) => item.key === key || item.key === key.replace('.', '_'))
    if (row && String(row.value).trim()) return String(row.value).trim()
  }
  return ''
}

async function openGrafanaForTrace() {
  if (!canViewGrafana.value || !selectedTraceId.value) return
  const [start, end] = normalizeTimeRange(filters.timeRange)
  const service = traceContextService.value || firstTraceContextValue(['service.name', 'service', 'workload', 'app', 'container'])
  const namespace = firstTraceContextValue(['service.namespace', 'namespace', 'k8s.namespace.name', 'kubernetes_namespace_name'])
  const tags = {
    'service.name': service || '',
    'service.namespace': namespace || '',
    service: service || '',
    namespace: namespace || '',
  }
  try {
    const resolved = await resolveTraceToGrafana({
      trace_id: selectedTraceId.value,
      tracing_datasource_id: filters.datasourceId,
      dashboard_key: 'kubernetes-compute-resources-workload',
      tags,
      from: start ? start.getTime() : undefined,
      to: end ? end.getTime() : undefined,
    })
    openRouteInNewTab(router, {
      path: '/observability/grafana',
      query: {
        ...(resolved.query || {}),
        provider: filters.provider || undefined,
        'var-workload': resolved.query?.['var-workload'] || service || undefined,
        'var-namespace': resolved.query?.['var-namespace'] || namespace || undefined,
        fullscreen: '1',
      },
    })
  } catch {
    openRouteInNewTab(router, {
      path: '/observability/grafana',
      query: {
        dashboard: 'kubernetes-compute-resources-workload',
        service: service || undefined,
        'var-workload': service || undefined,
        'var-namespace': namespace || undefined,
        traceId: selectedTraceId.value,
        provider: filters.provider || undefined,
        from: start ? start.getTime() : undefined,
        to: end ? end.getTime() : undefined,
        fullscreen: '1',
      },
    })
  }
}

function renderTopology() {
  if (!topologyChartRef.value) return
  if (topologyChart && topologyChart.getDom() !== topologyChartRef.value) {
    topologyChart.dispose()
    topologyChart = null
  }
  if (!topologyChart) topologyChart = echarts.init(topologyChartRef.value)

  const topologyData = focusedTopology.value || {}
  const rawNodes = topologyData.nodes || []
  const rawLinks = topologyData.calls || []
  const selectedNodeId = String(topologyData.selected_node_id || '')
  const chartWidth = topologyChartRef.value.clientWidth || 780
  const chartHeight = topologyChartRef.value.clientHeight || 320
  const nodeIdSet = new Set(rawNodes.map((item) => String(item.id || '')).filter(Boolean))
  const outgoing = new Map()
  const incoming = new Map()
  rawLinks.forEach((item) => {
    const sourceId = String(item.source || '')
    const targetId = String(item.target || '')
    if (!sourceId || !targetId || !nodeIdSet.has(sourceId) || !nodeIdSet.has(targetId)) return
    if (!outgoing.has(sourceId)) outgoing.set(sourceId, new Set())
    if (!incoming.has(targetId)) incoming.set(targetId, new Set())
    outgoing.get(sourceId).add(targetId)
    incoming.get(targetId).add(sourceId)
  })

  const nodeLevels = new Map()
  const walkLevels = (startIds, direction, step) => {
    const queue = startIds
      .filter((id) => nodeIdSet.has(id))
      .map((id) => ({ id, level: nodeLevels.get(id) || 0 }))
    const visited = new Set(queue.map((item) => `${item.id}:${step}`))
    while (queue.length) {
      const current = queue.shift()
      const nextIds = direction.get(current.id) || new Set()
      nextIds.forEach((nextId) => {
        const nextLevel = current.level + step
        const currentLevel = nodeLevels.get(nextId)
        if (currentLevel === undefined || (step > 0 ? nextLevel > currentLevel : nextLevel < currentLevel)) {
          nodeLevels.set(nextId, nextLevel)
        }
        const visitKey = `${nextId}:${step}`
        if (visited.has(visitKey)) return
        visited.add(visitKey)
        queue.push({ id: nextId, level: nodeLevels.get(nextId) ?? nextLevel })
      })
    }
  }

  if (selectedNodeId && nodeIdSet.has(selectedNodeId)) {
    nodeLevels.set(selectedNodeId, 0)
    walkLevels([selectedNodeId], outgoing, 1)
    walkLevels([selectedNodeId], incoming, -1)
  } else {
    const rootIds = rawNodes
      .map((item) => String(item.id || ''))
      .filter((id) => id && !(incoming.get(id)?.size))
    const starts = rootIds.length ? rootIds : rawNodes.slice(0, 1).map((item) => String(item.id || '')).filter(Boolean)
    starts.forEach((id) => nodeLevels.set(id, 0))
    walkLevels(starts, outgoing, 1)
  }

  rawNodes.forEach((item) => {
    const nodeId = String(item.id || '')
    if (!nodeLevels.has(nodeId)) {
      const maxLevel = Math.max(...nodeLevels.values(), 0)
      nodeLevels.set(nodeId, maxLevel + 1)
    }
  })

  const levelGroups = new Map()
  rawNodes.forEach((item) => {
    const nodeId = String(item.id || '')
    const level = nodeLevels.get(nodeId) ?? 0
    if (!levelGroups.has(level)) levelGroups.set(level, [])
    levelGroups.get(level).push(nodeId)
  })

  const orderedLevels = [...levelGroups.keys()].sort((a, b) => a - b)
  const xPadding = Math.min(96, Math.max(58, chartWidth * 0.08))
  const yPadding = Math.min(72, Math.max(44, chartHeight * 0.16))
  const usableWidth = Math.max(chartWidth - xPadding * 2, 1)
  const usableHeight = Math.max(chartHeight - yPadding * 2, 1)
  const positions = new Map()
  orderedLevels.forEach((level, columnIndex) => {
    const ids = levelGroups.get(level) || []
    const sortedIds = [...ids].sort((a, b) => {
      const aWeight = Number(rawLinks.find((item) => String(item.source || '') === a || String(item.target || '') === a)?.count || 0)
      const bWeight = Number(rawLinks.find((item) => String(item.source || '') === b || String(item.target || '') === b)?.count || 0)
      return bWeight - aWeight || String(a).localeCompare(String(b))
    })
    const x = orderedLevels.length <= 1
      ? chartWidth * 0.5
      : xPadding + (columnIndex * usableWidth) / (orderedLevels.length - 1)
    sortedIds.forEach((id, rowIndex) => {
      positions.set(id, {
        x,
        y: sortedIds.length <= 1 ? chartHeight * 0.5 : yPadding + ((rowIndex + 0.5) * usableHeight) / sortedIds.length,
      })
    })
  })

  const selectedLevel = nodeLevels.get(selectedNodeId) ?? 0
  const nodeRole = (nodeId) => {
    const level = nodeLevels.get(nodeId) ?? 0
    if (nodeId === selectedNodeId) return 'selected'
    if (selectedNodeId && level < selectedLevel) return 'upstream'
    if (selectedNodeId && level > selectedLevel) return 'downstream'
    return 'peer'
  }

  const nodes = rawNodes.map((item, index) => {
    const nodeId = String(item.id || '')
    const isRuntimeNode = item.type === 'RUNTIME_COMPONENT' || String(item.id || '').startsWith('runtime:')
    const position = positions.get(nodeId) || { x: chartWidth * 0.5, y: chartHeight * 0.5 }
    const role = nodeRole(nodeId)
    const color = nodeId === selectedNodeId
      ? '#2563eb'
      : isRuntimeNode
        ? '#0891b2'
      : role === 'upstream'
        ? '#0f766e'
        : role === 'downstream'
          ? '#ea580c'
          : ['#7c3aed', '#0891b2', '#64748b'][index % 3]
    return {
      id: item.id,
      name: item.name,
      value: item.name,
      x: position.x,
      y: position.y,
      symbol: isRuntimeNode ? 'roundRect' : 'circle',
      symbolSize: nodeId === selectedNodeId ? 56 : isRuntimeNode ? [84, 38] : 42,
      itemStyle: {
        color,
        borderColor: nodeId === selectedNodeId ? 'rgba(191, 219, 254, 0.95)' : '#ffffff',
        borderWidth: nodeId === selectedNodeId ? 4 : 2,
        shadowBlur: nodeId === selectedNodeId ? 18 : 8,
        shadowColor: nodeId === selectedNodeId ? 'rgba(37, 99, 235, 0.28)' : 'rgba(15, 23, 42, 0.08)',
      },
      label: {
        position: 'bottom',
        formatter: () => ellipsisText(item.name, nodeId === selectedNodeId ? 18 : 16),
      },
    }
  })

  const links = rawLinks.map((item) => ({
    source: item.source,
    target: item.target,
    value: item.count || 0,
    lineStyle: {
      color: String(item.source || '') === selectedNodeId ? '#fdba74' : '#99f6e4',
      width: Math.min(4, 1.6 + Number(item.count || 0) * 0.2),
      opacity: 0.95,
      curveness: 0.03,
    },
    symbol: ['none', 'arrow'],
    symbolSize: 8,
  }))

  topologyChart.setOption(
    {
      tooltip: {
        trigger: 'item',
        formatter: (params) => {
          if (params.dataType === 'edge') {
            const count = params.data?.value ? ` · ${params.data.value} 次` : ''
            return `${params.data.source} → ${params.data.target}${count}`
          }
          return params.data?.name || ''
        },
      },
      series: [
        {
          type: 'graph',
          layout: 'none',
          roam: true,
          draggable: true,
          label: { show: true, color: '#0f172a', fontSize: 11, distance: 8 },
          emphasis: {
            focus: 'adjacency',
            scale: true,
            lineStyle: {
              width: 3,
            },
          },
          data: nodes,
          links,
          lineStyle: { opacity: 0.92 },
        },
      ],
    },
    true
  )
  topologyChart.resize()
}

function handleResize() {
  topologyChart?.resize()
}

watch(
  () => [topology.value, filters.serviceId],
  async () => {
    topologyListPage.value = 1
    await nextTick()
    renderTopology()
  },
  { deep: true }
)

watch(topologyExpanded, async (expanded) => {
  if (!expanded) {
    topologyChart?.dispose()
    topologyChart = null
    return
  }
  await nextTick()
  renderTopology()
  setTimeout(() => {
    if (topologyExpanded.value) renderTopology()
  }, 60)
})

watch(
  () => filters.timeRange,
  () => {
    syncDurationMinutesFromTimeRange()
  },
  { deep: true, immediate: true }
)

watch(
  () => displayTraces.value.length,
  () => {
    if (traceListPage.value > traceListPageCount.value) {
      traceListPage.value = traceListPageCount.value
    }
    if (!displayTraces.value.length) {
      traceListPage.value = 1
    }
  },
  { immediate: true }
)

watch(
  () => selectedTraceId.value,
  (traceId) => {
    if (!traceId) return
    const index = displayTraces.value.findIndex((item) => item.trace_id === traceId)
    if (index === -1) return
    traceListPage.value = Math.floor(index / TRACE_LIST_PAGE_SIZE) + 1
  },
  { immediate: true }
)

onMounted(async () => {
  if (!canViewTrace.value) {
    activeTraceTab.value = canViewTraceDataSources.value ? 'datasources' : 'traces'
    return
  }
  if (topologyOnly.value) {
    topologyExpanded.value = true
  }
  filters.provider = routeParams.value.provider
  filters.datasourceId = routeParams.value.datasourceId
  await loadTracingDataSources()
  if (!filters.datasourceId) {
    applyDefaultTracingDataSource(filters.provider)
  }
  await loadOverview()
  await loadCatalog()
  if (!(await applyRouteTracePreset(true)) && !traces.value.length && services.value.length) {
    await runSearch(true)
  }
  window.addEventListener('resize', handleResize)
})

watch(
  () => [
    routeParams.value.provider,
    routeParams.value.datasourceId,
    routeParams.value.traceId,
    routeParams.value.service,
    routeParams.value.keyword,
    routeParams.value.window,
    routeParams.value.from,
    routeParams.value.to,
    routeParams.value.topology,
  ].join('|'),
  async (value, previous) => {
    if (!value || value === previous) return
    filters.provider = routeParams.value.provider
    filters.datasourceId = routeParams.value.datasourceId
    if (topologyOnly.value) {
      topologyExpanded.value = true
    }
    await applyRouteTracePreset()
  }
)

watch(
  () => route.query.tab,
  (value) => {
    if (value === 'datasources' && canViewTraceDataSources.value) {
      activeTraceTab.value = 'datasources'
    } else {
      activeTraceTab.value = 'traces'
    }
  },
  { immediate: true }
)

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  topologyChart?.dispose()
})
</script>

<style scoped>
.observability-page {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.observability-page.is-embedded {
  background: #ffffff;
  gap: 0;
  height: 100%;
  padding: 0;
}

.observability-page.is-embedded .panel {
  background: #ffffff;
  border: 0;
  border-radius: 18px;
  box-shadow: none;
  overflow: hidden;
  padding: 16px 18px 18px;
}

.observability-page.is-embedded .topology-layout {
  grid-template-columns: minmax(0, 1fr) 260px;
}

.observability-page.is-embedded .topology-chart,
.observability-page.is-embedded .topology-side {
  height: clamp(420px, 72vh, 680px);
  min-height: 420px;
}

.observability-page.is-embedded .topology-chart {
  background: linear-gradient(180deg, #fbfdff 0%, #f7fbff 100%);
}

.observability-page.is-embedded .section-head h3 {
  font-size: 20px;
  font-weight: 800;
}

.section-title-inline {
  display: inline-flex;
  align-items: baseline;
  flex: 1 1 auto;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.section-title-desc {
  color: #64748b;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
}

.panel {
  background: linear-gradient(180deg, #ffffff 0%, #fffdf8 100%);
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.04);
  padding: 12px 14px;
}

.hero.panel {
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36, 91, 219, 0.09);
  border-radius: 20px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  padding: 14px 16px;
}

.hero,
.hero-copy,
.hero-title-row,
.hero-actions,
.section-head,
.section-head-tags,
.provider-card__title,
.toolbar-actions,
.waterfall-head,
.span-head,
.span-title,
.span-meta,
.span-tags,
.chips-wrap,
.detail-summary {
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

.page-inline-desc {
  color: #64748b;
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
  flex: 0 1 auto;
  transform: translateY(1px);
}

.hero-icon {
  align-items: center;
  background: linear-gradient(180deg, #f3f7ff 0%, #ebf2ff 100%);
  border: 1px solid rgba(36, 91, 219, 0.12);
  border-radius: 14px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
  color: #245bdb;
  display: inline-flex;
  flex: 0 0 42px;
  height: 42px;
  justify-content: center;
  width: 42px;
}

.trace-center-tabs {
  margin-bottom: 0;
  padding: 4px;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255,255,255,.96), rgba(248,250,252,.9));
  border: 1px solid rgba(148,163,184,.16);
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.04);
}

.trace-center-tabs .neo-tab-btn {
  min-height: 38px;
  padding: 0 20px;
  border-radius: 8px;
}

.trace-center-tabs.theme-blue .neo-tab-btn.active {
  color: #245bdb;
  background: rgba(51, 112, 255, 0.1);
  box-shadow: inset 0 0 0 1px rgba(51, 112, 255, 0.08);
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

.trace-query-layout {
  align-items: stretch;
  display: grid;
  gap: 6px;
  grid-template-columns: minmax(0, 1.76fr) minmax(282px, 0.75fr);
}

.trace-query-unified-card {
  background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 16px;
  box-shadow: 0 6px 20px rgba(15, 23, 42, 0.04);
  padding: 10px 12px;
}

.trace-query-unified-head {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  margin-bottom: 8px;
}

.trace-query-title-block {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.trace-query-title-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.trace-query-title-row h3 {
  color: #0f172a;
  font-size: 14px;
  letter-spacing: 0.01em;
  margin: 0;
}

.trace-query-actions {
  align-items: center;
  display: flex;
  flex-shrink: 0;
  gap: 4px;
  justify-content: flex-end;
}

.trace-info-panel {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(249, 250, 252, 0.94) 100%);
  border-color: rgba(226, 232, 240, 0.84);
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.03);
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 9px 10px;
}

.trace-info-head {
  margin-bottom: 6px;
}

.trace-source-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.trace-source-title-row {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
}

.trace-source-title {
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  min-width: 0;
}

.trace-source-tags {
  align-items: center;
  display: flex;
  flex-shrink: 0;
  gap: 4px;
}

.trace-source-desc {
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.trace-summary-list {
  display: grid;
  gap: 5px;
  grid-template-columns: 1fr;
}

.trace-summary-item {
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(226, 232, 240, 0.88);
  border-radius: 9px;
  min-height: 54px;
  padding: 6px 8px;
}

.trace-summary-item span {
  color: #64748b;
  display: block;
  font-size: 11px;
  margin-bottom: 3px;
}

.trace-summary-item strong {
  color: #0f172a;
  display: block;
  font-size: 12px;
  line-height: 1.45;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-summary-item strong.is-multiline {
  overflow: visible;
  text-overflow: initial;
  white-space: pre-line;
  word-break: break-all;
}

.trace-query-unified-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trace-query-provider-strip {
  display: flex;
  flex-direction: column;
  gap: 5px;
  width: 100%;
}

.trace-filter-datasource-row {
  align-items: center;
  display: flex;
  gap: 6px;
  min-height: 30px;
  width: 100%;
}

.trace-filter-service-row {
  align-items: center;
  display: flex;
  gap: 8px;
  min-height: 32px;
  padding-bottom: 6px;
  width: 100%;
}

.trace-inline-filter {
  align-items: center;
  column-gap: 8px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  min-width: 0;
}

.trace-inline-filter--compact {
  width: 100%;
}

.trace-inline-filter--time {
  min-width: 0;
  width: 100%;
}

.trace-inline-filter__label {
  color: #64748b;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  margin-right: 1px;
  white-space: nowrap;
}

.trace-query-provider-label {
  color: #64748b;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 500;
  margin-right: 4px;
  white-space: nowrap;
}

.trace-datasource-control {
  flex: 1 1 auto;
  max-width: none;
}

.compact-summary-bar {
  align-items: center;
  background: linear-gradient(180deg, #fafcff 0%, #ffffff 100%);
  border: 1px dashed rgba(148, 163, 184, 0.46);
  border-radius: 12px;
  color: #475569;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 10px;
}

.compact-summary-bar--action {
  cursor: pointer;
  text-align: left;
  transition: all 0.2s ease;
  width: 100%;
}

.compact-summary-bar--action:hover {
  background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
  border-color: rgba(100, 116, 139, 0.62);
}

.compact-summary-bar--action:focus-visible {
  outline: 2px solid rgba(59, 130, 246, 0.32);
  outline-offset: 2px;
}

.compact-summary-bar span {
  font-size: 11px;
}

.compact-summary-bar__hint {
  color: #334155;
  font-size: 11px;
  font-weight: 600;
  margin-left: auto;
}

.search-panel {
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 12px;
}

.search-panel--merged {
  background: transparent;
  border: 0;
  border-top: 1px solid rgba(226, 232, 240, 0.64);
  border-radius: 0;
  padding: 8px 0 0;
}

.search-control,
.search-number {
  width: 100%;
}

.trace-filter-grid {
  display: grid;
  gap: 6px;
  width: 100%;
}

.trace-filter-grid--primary {
  align-items: center;
  column-gap: 8px;
  grid-template-columns: minmax(0, 0.94fr) minmax(182px, 0.78fr) minmax(188px, 0.82fr) minmax(118px, 0.42fr);
}

.trace-filter-grid--advanced {
  align-items: center;
  column-gap: 8px;
  grid-template-columns: minmax(146px, 0.44fr) minmax(146px, 0.44fr) minmax(360px, 1fr);
  margin-top: 7px;
}

.trace-filter-grid--toolbar {
  align-items: center;
  padding: 0;
}

.advanced-filter-control {
  width: 100%;
}

.advanced-filter-number {
  width: 100%;
}

.advanced-filter-time {
  min-width: 0;
  width: 100%;
}

.search-control :deep(.el-select__wrapper),
.search-control :deep(.el-input__wrapper),
.search-control :deep(.el-range-editor.el-input__wrapper),
.search-number :deep(.el-input__wrapper) {
  background: rgba(248, 250, 252, 0.82);
  border-radius: 8px;
  box-shadow: 0 0 0 1px rgba(226, 232, 240, 0.92) inset;
  min-height: 30px;
}

.search-control :deep(.el-input__inner),
.search-control :deep(.el-select__selected-item),
.search-control :deep(.el-range-input),
.search-number :deep(.el-input__inner) {
  font-size: 12px;
}

.search-control :deep(.el-select__wrapper:hover),
.search-control :deep(.el-input__wrapper:hover),
.search-control :deep(.el-range-editor.el-input__wrapper:hover),
.search-number :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(191, 219, 254, 0.96) inset;
}

.search-action-primary {
  border-radius: 8px;
  box-shadow: none;
  font-size: 13px;
  font-weight: 600;
  min-width: 84px;
  min-height: 28px;
  padding-inline: 12px;
}

.search-action-secondary {
  background: transparent;
  border-color: transparent;
  color: #64748b;
  font-size: 12px;
  min-height: 28px;
  padding-inline: 10px;
}

.advanced-filter-time :deep(.el-range-input),
.advanced-filter-time :deep(.el-range-separator) {
  font-size: 11px;
}

.advanced-filter-time :deep(.el-range-editor.el-input__wrapper) {
  gap: 6px;
  justify-content: flex-start;
}

.advanced-filter-time :deep(.el-range-input) {
  flex: 1 1 0;
  min-width: 0;
  text-align: left;
}

.advanced-filter-time :deep(.el-range-separator) {
  color: #64748b;
  flex: 0 0 18px;
  text-align: center;
}

.advanced-filter-time :deep(.el-range__icon) {
  color: #94a3b8;
  margin-right: 2px;
}

.search-action-secondary:hover {
  background: #ffffff;
  border-color: rgba(203, 213, 225, 0.9);
  color: #1e3a8a;
}

.search-summary-bar {
  align-items: center;
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
  overflow-x: auto;
  scrollbar-width: none;
}

.time-range-picker {
  width: 100%;
}

.search-summary-bar {
  align-items: center;
  border-top: 1px solid rgba(241, 245, 249, 0.92);
  display: flex;
  flex-wrap: nowrap;
  margin-top: 6px;
  padding-top: 6px;
}

.trace-query-summary-bar {
  margin-top: 2px;
}

.trace-query-summary-bar::-webkit-scrollbar {
  display: none;
}

.topology-layout {
  align-items: stretch;
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(0, 1.7fr) 178px;
}

.topology-chart {
  background: linear-gradient(180deg, #fbfdff 0%, #f8fbff 100%);
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 12px;
  height: 300px;
}

.topology-side {
  display: flex;
  flex-direction: column;
  gap: 4px;
  height: 300px;
  justify-content: flex-start;
  min-height: 300px;
}

.topology-list {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 3px;
  min-height: 0;
  overflow: hidden;
}

.topology-item {
  background: #fbfdff;
  border: 1px solid rgba(226, 232, 240, 0.88);
  border-radius: 9px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 7px;
}

.topology-item-main {
  align-items: center;
  display: flex;
  gap: 6px;
  justify-content: space-between;
  min-width: 0;
}

.topology-item strong {
  color: #0f172a;
  flex: 1 1 auto;
  font-size: 11px;
  line-height: 1.2;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topology-item-role {
  border-radius: 999px;
  display: inline-flex;
  font-size: 9px;
  line-height: 1;
  padding: 1px 5px;
  white-space: nowrap;
}

.topology-item.is-selected .topology-item-role {
  background: rgba(219, 234, 254, 0.95);
  color: #1d4ed8;
}

.topology-item.is-upstream .topology-item-role {
  background: rgba(204, 251, 241, 0.95);
  color: #0f766e;
}

.topology-item.is-downstream .topology-item-role {
  background: rgba(255, 237, 213, 0.95);
  color: #c2410c;
}

.topology-item.is-peer .topology-item-role {
  background: rgba(241, 245, 249, 0.95);
  color: #475569;
}

.topology-item-meta,
.topology-item span,
.chips-title,
.span-log-item span {
  color: var(--text-secondary);
  font-size: 10px;
}

.topology-item-meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topology-pagination {
  align-items: center;
  display: flex;
  flex: 0 0 auto;
  gap: 5px;
  justify-content: center;
  padding-top: 0;
}

.topology-page-btn {
  padding: 4px 8px;
}

.content-grid {
  align-items: start;
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(280px, 0.52fr) minmax(0, 1.68fr);
}

.traces-panel {
  display: flex;
  flex-direction: column;
  max-height: none;
  min-height: 860px;
  overflow: hidden;
}

.query-pill {
  background: rgba(248, 250, 252, 0.82);
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 999px;
  color: #64748b;
  font-size: 10px;
  flex: 0 0 auto;
  padding: 3px 7px;
  white-space: nowrap;
}

.trace-results {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
}

.trace-pagination {
  align-items: center;
  display: flex;
  gap: 6px;
  justify-content: center;
  margin-top: 8px;
  padding-top: 4px;
}

.trace-page-btn {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  color: #334155;
  cursor: pointer;
  font-size: 11px;
  line-height: 1;
  padding: 5px 9px;
}

.trace-page-btn:disabled {
  color: #94a3b8;
  cursor: not-allowed;
  opacity: 0.7;
}

.trace-page-indicator {
  color: #64748b;
  font-size: 11px;
}

.trace-result-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 9px;
  overflow: hidden;
  transition: all 0.2s ease;
}

.trace-result-card.is-active {
  background: linear-gradient(180deg, rgba(239, 246, 255, 0.96) 0%, #ffffff 100%);
  border-color: rgba(37, 99, 235, 0.34);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.08);
}

.trace-result-card.is-error {
  border-color: rgba(239, 68, 68, 0.2);
}

.trace-result-card.is-slow:not(.is-error) {
  border-color: rgba(245, 158, 11, 0.24);
}

.trace-result-main {
  background: transparent;
  border: 0;
  cursor: pointer;
  display: block;
  padding: 6px 8px;
  text-align: left;
  width: 100%;
}

.trace-result-main:hover {
  background: rgba(248, 250, 252, 0.7);
}

.trace-result-line {
  min-width: 0;
}

.trace-result-line.two-line-layout {
  display: flex;
  flex-direction: column;
  gap: 4px;
  line-height: 1.15;
  min-width: 0;
  padding-left: 10px;
  position: relative;
}

.trace-title-row {
  align-items: center;
  display: flex;
  min-width: 0;
}

.trace-accent-bar {
  background: linear-gradient(180deg, #f59e0b 0%, #fb923c 100%);
  border-radius: 999px;
  bottom: 2px;
  left: 0;
  position: absolute;
  top: 2px;
  width: 3px;
}

.trace-result-card.is-active .trace-accent-bar {
  background: linear-gradient(180deg, #2563eb 0%, #0ea5e9 100%);
}

.trace-accent-bar.is-error {
  background: linear-gradient(180deg, #ef4444 0%, #f97316 100%);
}

.trace-accent-bar.is-slow:not(.is-error) {
  background: linear-gradient(180deg, #f59e0b 0%, #f97316 100%);
}

.trace-meta-row {
  align-items: center;
  display: flex;
  gap: 6px;
  min-width: 0;
}

.trace-result-operation {
  color: #0f172a;
  font-weight: 700;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.trace-duration-pill {
  background: rgba(37, 99, 235, 0.08);
  border-radius: 999px;
  color: #1d4ed8;
  flex: 0 0 auto;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  min-width: 42px;
  padding: 3px 7px;
  text-align: center;
}

.trace-duration-pill.is-slow {
  background: rgba(245, 158, 11, 0.14);
  color: #b45309;
}

.trace-status-pill {
  background: rgba(22, 163, 74, 0.1);
  border-radius: 999px;
  color: #15803d;
  flex: 0 0 auto;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  padding: 3px 7px;
}

.trace-status-pill.is-error {
  background: rgba(239, 68, 68, 0.12);
  color: #dc2626;
}

.trace-result-time {
  color: #64748b;
  font-size: 10px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-panel {
  max-height: none;
  min-height: 860px;
  overflow: hidden;
}

.trace-workbench {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
}

.trace-header-card {
  align-items: start;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border: 1px solid #dbeafe;
  border-radius: 12px;
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(0, 1.8fr) minmax(320px, 1fr);
  padding: 8px 10px;
}

.trace-title-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.trace-title-row-main {
  align-items: center;
  display: flex;
  gap: 8px;
  min-width: 0;
}

.trace-title-block h3 {
  flex: 1;
  font-size: 16px;
  line-height: 1.15;
  margin: 0;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-provider-pill {
  align-self: flex-start;
  background: rgba(37, 99, 235, 0.08);
  border: 1px solid rgba(37, 99, 235, 0.14);
  border-radius: 999px;
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 7px;
}

.trace-header-meta,
.trace-id-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.trace-header-meta {
  justify-content: space-between;
}

.trace-id-row span,
.trace-kpi span,
.detail-label,
.operation-cell span,
.timeline-detail strong,
.timeline-duration {
  color: var(--text-secondary);
  font-size: 11px;
}

.trace-id-row code {
  background: rgba(15, 23, 42, 0.05);
  border-radius: 8px;
  color: #0f172a;
  font-size: 11px;
  max-width: 260px;
  overflow: hidden;
  padding: 2px 6px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-kpi-grid {
  display: grid;
  gap: 4px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.trace-kpi {
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 1px;
  justify-content: center;
  min-height: 42px;
  padding: 5px 7px;
}

.trace-kpi strong {
  color: #0f172a;
  font-size: 14px;
}

.trace-context-actions {
  align-items: center;
  background: linear-gradient(90deg, rgba(37, 99, 235, 0.06), rgba(14, 165, 233, 0.03));
  border: 1px solid rgba(37, 99, 235, 0.12);
  border-radius: 10px;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  padding: 5px 8px;
}

.context-copy {
  align-items: baseline;
  display: flex;
  gap: 8px;
  min-width: 0;
}

.context-copy strong {
  color: #0f172a;
  flex: 0 0 auto;
  font-size: 12px;
  line-height: 1.2;
}

.context-copy span {
  color: #64748b;
  font-size: 11px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-actions {
  align-items: center;
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: flex-end;
}

.context-action-btn {
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 999px;
  color: #334155;
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  padding: 5px 8px;
}

.context-action-btn:hover {
  border-color: rgba(37, 99, 235, 0.28);
  color: #1d4ed8;
}

.context-action-btn.primary {
  background: rgba(37, 99, 235, 0.08);
  border-color: rgba(37, 99, 235, 0.18);
  color: #1d4ed8;
}

.danger-kpi {
  background: rgba(254, 242, 242, 0.92);
  border-color: rgba(239, 68, 68, 0.18);
}

.trace-minimap {
  background: transparent;
  border: 0;
  border-radius: 0;
  padding: 2px 0 0;
}

.trace-header-minimap {
  align-items: center;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 10px;
  display: grid;
  gap: 4px;
  grid-column: 1 / -1;
  margin-top: -2px;
  padding: 4px 6px;
  grid-template-columns: 132px minmax(0, 1fr);
}

.trace-minimap-head,
.span-toolbar {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: space-between;
}

.trace-header-minimap .trace-minimap-head {
  align-items: flex-start;
  flex-direction: column;
  gap: 1px;
  justify-content: center;
}

.trace-minimap-head span {
  color: var(--text-secondary);
  font-size: 11px;
}

.trace-minimap-head strong {
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.1;
}

.minimap-track {
  background: linear-gradient(180deg, #f8fafc 0%, #fff 100%);
  border: 0;
  border-radius: 12px;
  height: 28px;
  margin-top: 0;
  position: relative;
}

.minimap-segment {
  border: 0;
  border-radius: 999px;
  cursor: pointer;
  height: 8px;
  opacity: 0.9;
  position: absolute;
  top: 9px;
}

.minimap-segment.is-error {
  box-shadow: inset 0 0 0 1px rgba(127, 29, 29, 0.14);
}

.minimap-segment.is-selected {
  height: 12px;
  margin-top: -2px;
  box-shadow: 0 0 0 2px rgba(15, 23, 42, 0.12);
}

.trace-insights {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.insight-pill {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  color: #334155;
  cursor: pointer;
  font-size: 10px;
  padding: 3px 7px;
}

.error-pill {
  background: rgba(254, 242, 242, 0.92);
  border-color: rgba(239, 68, 68, 0.18);
  color: #b91c1c;
}

.slow-pill {
  background: rgba(255, 251, 235, 0.94);
  border-color: rgba(245, 158, 11, 0.2);
  color: #b45309;
}

.service-pill {
  background: rgba(37, 99, 235, 0.08);
  border-color: rgba(37, 99, 235, 0.14);
  color: #1d4ed8;
  cursor: default;
}

.span-toolbar {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 4px 8px;
}

.span-toolbar :deep(.el-input),
.span-toolbar :deep(.el-select) {
  width: 172px;
}

.span-toolbar :deep(.el-input__wrapper),
.span-toolbar :deep(.el-select__wrapper) {
  min-height: 26px;
}

.span-filter-toggle {
  align-items: center;
  display: flex;
  gap: 4px;
}

.span-filter-label {
  color: #94a3b8;
  font-size: 10px;
  font-weight: 500;
  line-height: 1;
}

.span-filter-segment {
  align-items: center;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  display: inline-flex;
  padding: 2px;
}

.span-filter-option {
  background: transparent;
  border: 0;
  border-radius: 999px;
  color: #94a3b8;
  cursor: pointer;
  font-size: 11px;
  line-height: 1;
  padding: 4px 7px;
  transition: all 0.2s ease;
}

.span-filter-option:hover {
  color: #64748b;
}

.span-filter-option.is-active {
  background: rgba(37, 99, 235, 0.08);
  color: #1d4ed8;
  font-weight: 600;
}

.trace-timeline-card {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: visible;
}

.timeline-axis-row {
  align-items: center;
  background: linear-gradient(180deg, #fff 0%, #f8fafc 100%);
  border-bottom: 1px solid #e2e8f0;
  color: #94a3b8;
  display: grid;
  font-size: 10px;
  gap: 8px;
  grid-template-columns: 236px minmax(0, 1fr) 64px 34px;
  padding: 5px 8px;
}

.timeline-axis-action-placeholder {
  display: block;
}

.timeline-axis {
  display: flex;
  justify-content: space-between;
  padding-left: 6px;
}

.timeline-axis-total {
  padding-right: 0;
  transform: translateX(6px);
}

.timeline-axis-duration-label {
  justify-self: end;
  padding-right: 0;
  text-align: right;
  transform: translateX(3px);
}

.timeline-body {
  display: flex;
  flex-direction: column;
  position: relative;
}

.timeline-row-shell {
  align-items: center;
  background: #fff;
  border-bottom: 1px solid #f1f5f9;
  display: grid;
  gap: 4px;
  grid-template-columns: minmax(0, 1fr) 34px;
  padding: 0 8px;
  position: relative;
}

.timeline-row {
  align-items: center;
  background: transparent;
  border: 0;
  cursor: default;
  display: grid;
  gap: 6px;
  grid-template-columns: 236px minmax(0, 1fr) 64px;
  padding: 5px 0;
  position: relative;
  text-align: left;
  width: 100%;
}

.timeline-row-shell:hover {
  background: #f8fafc;
}

.timeline-row-shell.is-error {
  background: rgba(254, 242, 242, 0.52);
}

.timeline-row-shell.is-slow .timeline-duration {
  color: #d97706;
}

.timeline-row-shell.is-selected {
  background: rgba(239, 246, 255, 0.95);
}

.timeline-row-shell.is-critical .operation-cell strong::after {
  color: #2563eb;
  content: '  critical';
  font-size: 10px;
  font-weight: 600;
}

.timeline-row-shell:hover,
.timeline-row-shell:focus-within {
  z-index: 8;
}

.timeline-log-action {
  align-items: center;
  background: rgba(255, 255, 255, 0.72);
  border: 0;
  border-radius: 8px;
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.18);
  color: #8b95a7;
  cursor: pointer;
  display: inline-flex;
  height: 26px;
  justify-content: center;
  padding: 0;
  justify-self: end;
  transition: all 0.2s ease;
  transform: translateX(4px);
  width: 30px;
}

.timeline-log-action:hover {
  background: rgba(37, 99, 235, 0.08);
  box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.18);
  color: #2563eb;
}

.timeline-log-action:focus-visible {
  outline: 2px solid rgba(37, 99, 235, 0.22);
  outline-offset: 1px;
}

.timeline-log-icon {
  fill: none;
  height: 20px;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.65;
  width: 20px;
}

.timeline-log-icon text {
  fill: currentColor;
  font-family: Inter, "Segoe UI", Arial, sans-serif;
  font-size: 6.8px;
  font-weight: 900;
  letter-spacing: 0;
  stroke: none;
}

.timeline-label {
  align-items: center;
  display: flex;
  gap: 5px;
  min-width: 0;
}

.expand-mark {
  color: #64748b;
  flex: 0 0 auto;
  font-size: 10px;
}

.service-dot {
  border-radius: 999px;
  flex: 0 0 auto;
  height: 7px;
  width: 7px;
}

.operation-cell {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-width: 0;
  position: relative;
}

.operation-cell strong {
  font-size: 11px;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.operation-cell span {
  color: #64748b;
  font-size: 10px;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timeline-track {
  background: repeating-linear-gradient(90deg, rgba(226, 232, 240, 0.72) 0, rgba(226, 232, 240, 0.72) 1px, transparent 1px, transparent 20%);
  border-radius: 999px;
  height: 8px;
  margin-left: 6px;
  position: relative;
}

.timeline-bar {
  border-radius: 999px;
  height: 8px;
  position: absolute;
  top: 0;
}

.timeline-duration {
  font-size: 10px;
  padding-left: 4px;
  text-align: right;
}

.timeline-detail {
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.56) 0%, #ffffff 100%);
  border-bottom: 1px solid #e2e8f0;
  padding: 9px 12px 12px 82px;
}

.span-attribute-summary {
  align-items: center;
  color: #64748b;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  font-size: 12px;
  line-height: 1.45;
  margin-bottom: 8px;
}

.span-attribute-summary strong {
  color: #0f172a;
  font-weight: 700;
}

.service-line {
  border-radius: 999px;
  display: inline-block;
  height: 6px;
  width: 22px;
}

.span-id-inline {
  margin-left: 0;
}

.attribute-section {
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(226, 232, 240, 0.82);
  border-radius: 9px;
  margin-top: 6px;
  overflow: hidden;
}

.attribute-section summary {
  align-items: center;
  cursor: pointer;
  display: flex;
  gap: 8px;
  list-style: none;
  min-height: 32px;
  padding: 6px 10px;
}

.attribute-section summary::-webkit-details-marker {
  display: none;
}

.attribute-section summary strong {
  color: #0f172a;
  font-size: 12px;
}

.attribute-section summary > span:last-child {
  color: #94a3b8;
  font-size: 11px;
  margin-left: auto;
}

.attribute-section[open] summary > span:last-child {
  display: none;
}

.attribute-chevron {
  color: #64748b;
  display: inline-flex;
  font-size: 15px;
  line-height: 1;
  transition: transform 0.16s ease;
}

.attribute-section:not([open]) .attribute-chevron {
  transform: rotate(-90deg);
}

.attribute-table {
  background: rgba(248, 250, 252, 0.52);
  border-top: 1px solid rgba(226, 232, 240, 0.78);
  padding: 0 8px 8px;
}

.attribute-row {
  align-items: center;
  background: transparent;
  border-bottom: 1px solid rgba(226, 232, 240, 0.56);
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(140px, 0.3fr) minmax(0, 1fr);
  min-height: 29px;
  padding: 5px 6px;
}

.attribute-row:nth-child(2n) {
  background: rgba(255, 255, 255, 0.46);
}

.attribute-row span {
  color: #64748b;
  font-size: 11px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attribute-row code {
  color: #0f766e;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  line-height: 1.45;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.attribute-empty {
  color: #94a3b8;
  font-size: 12px;
  padding: 10px 8px 0;
}

.attribute-section:not([open]) .attribute-table {
  display: none;
}

.span-log-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 4px;
}

.span-log-item {
  background: #fff7ed;
  border-radius: 7px;
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 4px 6px;
}

.span-log-item strong {
  font-size: 10px;
}

.span-log-item span {
  font-size: 10px;
}

.embed-frame {
  border: 0;
  border-radius: 10px;
  height: 500px;
  width: 100%;
}

:deep(.el-table td.el-table__cell),
:deep(.el-table th.el-table__cell) {
  padding: 7px 0;
}

:deep(.el-table .cell) {
  line-height: 1.35;
}

@media (max-width: 1460px) {
  .trace-query-layout {
    grid-template-columns: minmax(0, 1.65fr) minmax(260px, 0.69fr);
  }

  .trace-filter-grid--primary {
    grid-template-columns: minmax(0, 0.92fr) minmax(172px, 0.74fr) minmax(180px, 0.78fr) minmax(112px, 0.38fr);
  }

  .trace-filter-grid--advanced {
    grid-template-columns: minmax(132px, 0.42fr) minmax(132px, 0.42fr) minmax(300px, 1fr);
  }

  .search-action-primary {
    min-width: 78px;
    padding-inline: 10px;
  }

  .search-action-secondary {
    font-size: 12px;
  }
}

@media (max-width: 1280px) {
  .trace-kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trace-query-unified-head {
    align-items: stretch;
    flex-direction: column;
  }

  .trace-filter-grid--primary,
  .trace-filter-grid--advanced {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .advanced-filter-time {
    flex: 1 1 320px;
    width: auto;
  }

  .trace-header-card,
  .trace-query-layout,
  .content-grid,
  .topology-layout {
    grid-template-columns: 1fr;
  }

  .trace-header-meta {
    align-items: flex-start;
    flex-direction: column;
  }

  .timeline-axis-row,
  .timeline-row {
    grid-template-columns: 204px minmax(0, 1fr) 68px;
  }

  .traces-panel,
  .detail-panel {
    max-height: none;
    min-height: 0;
  }

  .trace-results,
  .trace-workbench {
    overflow: visible;
    padding-right: 0;
  }
}

@media (max-width: 760px) {
  .hero,
  .section-head,
  .trace-context-actions,
  .trace-query-unified-head {
    align-items: stretch;
    flex-direction: column;
  }

  .trace-filter-datasource-row,
  .trace-filter-service-row {
    align-items: flex-start;
    justify-content: flex-start;
  }

  .trace-inline-filter--time {
    min-width: 0;
  }

  .trace-filter-grid--primary,
  .trace-filter-grid--advanced {
    grid-template-columns: 1fr;
  }

  .trace-source-title-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .trace-filter-grid--toolbar {
    align-items: stretch;
  }

  .trace-inline-filter,
  .trace-inline-filter--compact,
  .trace-inline-filter--time {
    width: 100%;
  }

  .trace-inline-filter__label {
    margin-right: 2px;
  }

  .advanced-filter-control,
  .advanced-filter-number,
  .advanced-filter-time {
    width: 100%;
  }

  .trace-query-actions {
    justify-content: flex-start;
    width: 100%;
  }

  .context-copy {
    align-items: flex-start;
    flex-direction: column;
    gap: 2px;
  }

  .context-actions {
    justify-content: flex-start;
  }

  .trace-kpi-grid,
  .attribute-row {
    grid-template-columns: 1fr;
  }

  .timeline-detail {
    padding-left: 18px;
  }

  .trace-result-main {
    padding: 6px 7px;
  }

  .trace-title-row-main,
  .trace-header-meta {
    align-items: flex-start;
    flex-direction: column;
  }

  .trace-title-block h3 {
    white-space: normal;
  }

  .trace-header-minimap {
    grid-template-columns: 1fr;
  }

  .trace-header-minimap .trace-minimap-head {
    flex-direction: row;
    justify-content: space-between;
  }

  .trace-meta-row {
    gap: 5px;
  }

  .trace-duration-pill {
    min-width: 40px;
    padding: 3px 6px;
  }

  .span-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .span-toolbar :deep(.el-input),
  .span-toolbar :deep(.el-select) {
    width: 100%;
  }

  .timeline-axis-row,
  .timeline-row {
    display: flex;
    flex-direction: column;
  }

  .timeline-track {
    min-height: 14px;
    width: 100%;
  }
}
.hero.panel { border-radius: 20px; }
</style>



