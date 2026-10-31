<template>
  <div class="system-posture-page" :class="{ 'system-posture-page--embedded': embedded, 'workbench-page-shell': !embedded }">
    <section v-if="!embedded" class="hero panel">
      <div class="release-hero-copy">
        <div class="release-hero-title-row release-hero-title-inline">
          <span class="hero-icon"><el-icon><Aim /></el-icon></span>
          <h2>系统SLO</h2>
          <p class="page-inline-desc">按环境与系统聚合健康态势，结果导向定义系统 SLO，划清故障边界，快速定位异常节点、关键依赖与风险范围。</p>
        </div>
      </div>
    </section>

    <ObservabilityRouteTabs v-if="!embedded" group="posture" />

    <div
      class="overview-shell workbench-fill-panel"
      :class="{ 'is-root': !showFocusPanel }"
      :aria-busy="loading"
      v-loading="loading"
      element-loading-text="系统SLO加载数据较多，请稍等..."
      element-loading-background="var(--posture-loading-mask)"
    >
      <div class="overview-toolbar">
        <div>
          <div class="drill-breadcrumb">
            <button type="button" :class="{ active: !drillPath.length }" @click="resetDrill">系统视角</button>
            <template v-for="item in drillPath" :key="item.id">
              <span>/</span>
              <button type="button" :class="{ active: currentDrillParent?.id === item.id }" @click="jumpDrill(item)">
                {{ item.name }}
              </button>
            </template>
          </div>
          <span>{{ drillToolbarText }}</span>
        </div>
        <div class="overview-toolbar__actions">
          <el-button size="small" :loading="loading" @click="loadSystemPosture()"><el-icon><RefreshRight /></el-icon>刷新</el-button>
          <el-date-picker
            v-model="timeRange"
            type="datetimerange"
            size="small"
            unlink-panels
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            :shortcuts="timeRangeShortcuts"
            class="system-posture-time-picker"
            @change="handleTimeRangeChange"
          />
          <el-button v-if="drillPath.length" size="small" @click="drillUp">返回上层</el-button>
          <el-button v-if="canManageSystemPosture && !drillPath.length" size="small" @click="openCreateEnvironment">
            新增环境
          </el-button>
        </div>
      </div>

      <div class="overview-layout" :class="{ 'is-root': !showFocusPanel }">
        <section
          class="panel overview-systems-panel"
        >
          <div v-if="drillPath.length" class="system-grid">
            <article
              v-for="item in drillCards"
              :key="item.id"
              role="button"
              tabindex="0"
              class="system-card"
              :class="[`is-${cardStatus(item)}`, { active: isDrillCardActive(item), 'is-leaf': !hasChildren(item), 'is-slo-breached': isSloBreached(item) }]"
              @click="selectOverviewCard(item)"
              @keydown.enter.prevent="selectOverviewCard(item)"
            >
              <div class="system-card__head">
                <div class="system-card__title">
                  <strong>{{ item.name }}</strong>
                </div>
              </div>
              <div v-if="cardMeta(item)" class="system-card__meta">
                <span>{{ cardMeta(item) }}</span>
              </div>
              <div class="core-metric">
                <span>{{ cardSlo(item).label || 'SLI' }}</span>
                <strong>{{ formatMetric(cardSlo(item)) }}</strong>
                <em>{{ cardSlo(item).target !== undefined ? `SLO${targetText(cardSlo(item))}` : kindLabel(item.kind) }}</em>
              </div>
              <div class="system-card__signals">
                <span>故障节点 {{ abnormalCount(item) }}</span>
                <span>{{ hasChildren(item) ? `下级 ${item.children.length}` : '叶子节点' }}</span>
              </div>
              <div class="score-row">
                <span>健康分</span>
                <strong>{{ item.health_score ?? '--' }}</strong>
                <button
                  v-if="hasChildren(item)"
                  type="button"
                  class="drill-action"
                  :class="`is-${cardStatus(item)}`"
                  @click.stop="drillIntoCard(item)"
                >
                  下钻
                </button>
                <em v-else :class="`is-${cardStatus(item)}`">{{ statusLabel(cardStatus(item)) }}</em>
              </div>
            </article>
            <el-empty v-if="!drillCards.length && !loading" description="当前层级暂无节点" :image-size="72" />
          </div>
          <div v-else class="environment-groups">
            <section
              v-for="(group, groupIndex) in environmentGroups"
              :key="group.key"
              class="environment-group"
              :class="`is-${group.status}`"
            >
              <div class="environment-group__head">
                <div class="environment-title">
                  <span class="environment-dot" :class="`is-${group.status}`"></span>
                  <strong>{{ group.label }}</strong>
                  <em>{{ group.items.length }} 个系统</em>
                </div>
                <div class="environment-summary">
                  <span v-if="group.counts.critical">故障 {{ group.counts.critical }}</span>
                  <span v-if="group.counts.unknown">未知 {{ group.counts.unknown }}</span>
                  <span>健康 {{ group.counts.healthy }}</span>
                </div>
                <div v-if="canManageSystemPosture" class="environment-actions">
                  <el-button size="small" text :disabled="groupIndex === 0 || environmentSorting" @click="moveEnvironment(group, -1)">上移</el-button>
                  <el-button size="small" text :disabled="groupIndex === environmentGroups.length - 1 || environmentSorting" @click="moveEnvironment(group, 1)">下移</el-button>
                  <el-button size="small" text @click="renameEnvironment(group)">重命名</el-button>
                  <el-button size="small" type="primary" plain @click="openCreateSystem(group.key)">
                    <el-icon><Plus /></el-icon>
                    新增卡片
                  </el-button>
                </div>
              </div>
              <div class="system-grid">
                <article
                  v-for="item in group.items"
                  :key="item.id"
                  role="button"
                  tabindex="0"
                  class="system-card"
                  :class="[`is-${cardStatus(item)}`, { active: isDrillCardActive(item), 'is-leaf': !hasChildren(item), 'is-slo-breached': isSloBreached(item) }]"
                  @click="selectOverviewCard(item)"
                  @keydown.enter.prevent="selectOverviewCard(item)"
                >
                  <div class="system-card__head">
                    <div class="system-card__title">
                      <strong>{{ item.name }}</strong>
                    </div>
                    <div class="system-card__ops">
                      <template v-if="canManageSystemPosture && item.editable">
                        <el-button size="small" text :icon="Edit" @click.stop="openEditSystem(item)" />
                        <el-button size="small" text :icon="Delete" @click.stop="removeSystem(item)" />
                      </template>
                    </div>
                  </div>
                  <div v-if="cardMeta(item)" class="system-card__meta">
                    <span>{{ cardMeta(item) }}</span>
                  </div>
                  <div class="core-metric">
                    <span>{{ cardSlo(item).label || 'SLI' }}</span>
                    <strong>{{ formatMetric(cardSlo(item)) }}</strong>
                    <em>{{ cardSlo(item).target !== undefined ? `SLO${targetText(cardSlo(item))}` : kindLabel(item.kind) }}</em>
                  </div>
                  <div class="system-card__signals">
                    <span>故障节点 {{ abnormalCount(item) }}</span>
                    <span>{{ hasChildren(item) ? `下级 ${item.children.length}` : '叶子节点' }}</span>
                  </div>
                  <div class="score-row">
                    <span>健康分</span>
                    <strong>{{ item.health_score ?? '--' }}</strong>
                    <button
                      v-if="hasChildren(item)"
                      type="button"
                      class="drill-action"
                      :class="`is-${cardStatus(item)}`"
                      @click.stop="drillIntoCard(item)"
                    >
                      下钻
                    </button>
                    <em v-else :class="`is-${cardStatus(item)}`">{{ statusLabel(cardStatus(item)) }}</em>
                  </div>
                </article>
              </div>
            </section>
            <el-empty v-if="!environmentGroups.length && !loading" description="当前层级暂无节点" :image-size="72" />
          </div>
        </section>

        <section v-if="showFocusPanel" class="panel focus-panel">
          <div class="section-head">
            <div class="focus-heading">
              <h3>{{ focusTarget.name || '节点详情' }}</h3>
              <span>所在环境 · {{ focusEnvironmentLabel }}</span>
            </div>
            <el-tag size="small" :type="tagType(cardStatus(focusTarget))">{{ statusLabel(cardStatus(focusTarget)) }}</el-tag>
          </div>
          <div class="focus-kpis">
            <div class="focus-kpi">
              <span>{{ cardSlo(focusTarget).label || 'SLI' }}</span>
              <strong>{{ formatMetric(cardSlo(focusTarget)) }}</strong>
              <em>{{ cardSlo(focusTarget).target !== undefined ? `SLO${targetText(cardSlo(focusTarget))}` : kindLabel(focusTarget.kind) }}</em>
            </div>
            <div class="focus-kpi">
              <span>健康分</span>
              <strong>{{ focusTarget.health_score ?? '--' }}</strong>
              <em>{{ focusTarget.children?.length ? `下级 ${focusTarget.children.length}` : '叶子节点' }}</em>
            </div>
          </div>
          <div class="focus-entry-grid">
            <el-tooltip
              effect="light"
              placement="top"
              :show-after="180"
              popper-class="system-posture-entry-tip"
              :content="drilldownEntryText"
            >
              <button type="button" class="focus-entry" @click="openDrilldownDialog">
                <span>进入</span>
                <strong>层级下钻</strong>
                <em>{{ drilldownEntryText }}</em>
              </button>
            </el-tooltip>
            <el-tooltip
              effect="light"
              placement="top"
              :show-after="180"
              popper-class="system-posture-entry-tip"
              :content="topologyEntryText"
            >
              <button type="button" class="focus-entry" @click="openTopologyDialog">
                <span>进入</span>
                <strong>依赖拓扑</strong>
                <em>{{ topologyEntryText }}</em>
              </button>
            </el-tooltip>
          </div>
          <div v-if="focusMetrics.length" class="focus-block">
            <div class="focus-block__title">关键指标</div>
            <div class="compact-metric-list">
              <div v-for="metric in focusMetrics" :key="metric.label" class="compact-metric" :class="`is-${metric.status}`">
                <span>{{ metric.label }}</span>
                <strong>{{ formatMetric(metric) }}</strong>
                <em>{{ targetText(metric) }}</em>
              </div>
            </div>
          </div>
          <div v-if="focusActions.length" class="action-row compact-actions">
            <el-button
              v-for="action in focusActions"
              :key="action.key"
              size="small"
              plain
              @click="goAction(action)"
            >
              {{ action.title }}
            </el-button>
          </div>
        </section>
      </div>
    </div>

    <el-dialog
      v-model="drillDialogVisible"
      :title="`${selectedSystem.name || '系统视角'} · 层级下钻`"
      width="1040px"
      destroy-on-close
      class="system-posture-detail-dialog"
    >
      <div class="drill-layout">
        <section class="panel drill-tree-panel">
          <div class="section-head">
            <h3>层级下钻</h3>
            <el-tag size="small" type="info">节点 {{ drilldownRows.length }}</el-tag>
          </div>
          <div class="drill-tree">
            <button
              v-for="node in drilldownRows"
              :key="node.id"
              type="button"
              class="drill-row"
              :class="[`is-${node.status}`, { active: selectedNode?.id === node.id }]"
              :style="{ '--node-indent': `${node.level * 20}px` }"
              @click="selectNode(node)"
            >
              <span class="status-dot" :class="`is-${node.status}`"></span>
              <span class="node-kind">{{ kindLabel(node.kind) }}</span>
              <strong>{{ node.name }}</strong>
              <em v-if="node.role">{{ node.role }}</em>
            </button>
          </div>
        </section>

        <section class="panel node-detail-panel">
          <div class="section-head">
            <h3>{{ selectedNode?.name || '节点详情' }}</h3>
            <el-tag size="small" :type="tagType(selectedNode?.status)">{{ statusLabel(selectedNode?.status) }}</el-tag>
          </div>
          <div v-if="selectedNode" class="node-detail">
            <div v-if="selectedNode.hint" class="node-hint">{{ selectedNode.hint }}</div>
            <div class="metric-grid">
              <div v-for="metric in selectedNode.metrics || []" :key="metric.label" class="metric-cell" :class="`is-${metric.status}`">
                <span>{{ metric.label }}</span>
                <strong>{{ formatMetric(metric) }}</strong>
                <em>阈值 {{ targetText(metric) }}</em>
              </div>
            </div>
            <div v-if="selectedNode.children?.length" class="child-node-grid">
              <button
                v-for="child in selectedNode.children"
                :key="child.id"
                type="button"
                class="child-node"
                :class="`is-${child.status}`"
                @click="selectNode(child)"
              >
                <span class="status-dot" :class="`is-${child.status}`"></span>
                <strong>{{ child.name }}</strong>
                <em>{{ child.hint }}</em>
              </button>
            </div>
            <el-empty v-else description="当前节点已定位到叶子接口" :image-size="72" />
          </div>
          <el-empty v-else description="请选择一个系统、模块或接口" :image-size="72" />
        </section>
      </div>
    </el-dialog>

    <el-dialog
      v-model="topologyDialogVisible"
      :title="`${selectedSystem.name || '系统视角'} · 依赖拓扑`"
      width="1080px"
      destroy-on-close
      class="system-posture-detail-dialog"
      @opened="renderTopology"
      @closed="disposeTopology"
    >
      <section class="panel topology-panel">
        <div class="section-head">
          <h3>依赖健康度与影响面拓扑</h3>
          <div class="section-tags">
            <el-tag size="small" type="info">节点 {{ topology.node_count || 0 }}</el-tag>
            <el-tag size="small" type="warning">关系 {{ topology.call_count || 0 }}</el-tag>
          </div>
        </div>
        <div ref="topologyChartRef" class="topology-chart" />
      </section>

      <div class="dependency-grid">
        <article
          v-for="dep in selectedSystem.dependencies || []"
          :key="dep.id"
          class="dependency-card"
          :class="`is-${dep.status}`"
        >
          <div class="dependency-card__head">
            <div>
              <strong>{{ dep.name }}</strong>
              <span>{{ dep.kind }} · {{ dep.role === 'upstream' ? '上游' : '下游' }}</span>
            </div>
            <el-tag size="small" :type="tagType(dep.status)">{{ statusLabel(dep.status) }}</el-tag>
          </div>
          <p>{{ dep.impact }}</p>
          <div class="dependency-metrics">
            <span v-for="metric in dep.metrics || []" :key="metric.label" :class="`is-${metric.status}`">
              {{ metric.label }} {{ formatMetric(metric) }}
            </span>
          </div>
        </article>
      </div>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" append-to-body
      v-model="systemDialogVisible"
      :title="editingSystem ? '编辑系统卡片' : '新增系统卡片'"
      width="880px"
      destroy-on-close
      class="workbench-edit-dialog system-posture-dialog"
    >
      <el-form label-position="top" class="system-posture-form">
        <div class="form-section">
          <div class="form-section__head">
            <strong>基础信息</strong>
            <span>卡片归属环境由当前环境分组决定</span>
          </div>
          <div class="readonly-row readonly-row--top">
            <span>所属环境</span>
            <strong>{{ environmentLabel(systemForm.environment) }}</strong>
          </div>
          <div class="form-grid form-grid--basic">
            <el-form-item label="系统名称">
              <el-input v-model="systemForm.name" maxlength="128" show-word-limit placeholder="例如：交易系统核心" />
            </el-form-item>
            <el-form-item label="系统域">
              <el-select v-model="systemForm.domain" placeholder="请选择系统域">
                <el-option
                  v-for="item in systemDomainOptions"
                  :key="item"
                  :label="item"
                  :value="item"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="展示顺序">
              <el-input-number v-model="systemForm.sort_order" :min="0" :step="10" controls-position="right" />
              <div class="form-item-hint">同一环境下数值越小越靠前</div>
            </el-form-item>
          </div>
        </div>

        <div class="form-section">
          <div class="form-section__head">
            <strong>核心指标目标</strong>
            <span>当前值和健康分由实时数据计算，不在这里手工配置</span>
          </div>
          <div class="form-grid form-grid--slo">
            <el-form-item label="核心指标">
              <el-input v-model="systemForm.metric_label" placeholder="例如：下单成功率" />
            </el-form-item>
            <el-form-item label="目标值">
              <el-input-number v-model="systemForm.metric_target" :precision="2" controls-position="right" />
            </el-form-item>
            <el-form-item label="单位">
              <el-input v-model="systemForm.metric_unit" placeholder="%" />
            </el-form-item>
            <el-form-item label="方向">
              <el-select v-model="systemForm.metric_direction">
                <el-option label="越高越好" value="higher" />
                <el-option label="越低越好" value="lower" />
              </el-select>
            </el-form-item>
          </div>
        </div>

        <div class="form-section">
          <div class="form-section__head">
            <strong>高级配置</strong>
            <el-button size="small" text @click="jsonHelpVisible = true">JSON 填写帮助</el-button>
          </div>
          <el-form-item label="规则配置 JSON">
            <el-input
              v-model="systemForm.rule_config_text"
              type="textarea"
              :rows="14"
              spellcheck="false"
              class="json-editor"
              placeholder='例如：{"core_metric":{"metric":"checkout_success_rate","target":90},"root_cause_rules":[{"id":"inventory-conflict","count_as_fault":true}],"drilldown":{"services":[{"id":"api-gateway","paths":[{"id":"gateway-checkout","path":"/api/checkout"}]}],"dependencies":[{"id":"postgres","role":"downstream"}]}}'
            />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="systemDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="systemSubmitting" @click="saveSystem">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="jsonHelpVisible"
      title="系统态势规则 JSON 填写帮助"
      width="760px"
      append-to-body
      class="system-posture-help-dialog"
    >
      <div class="json-help">
        <p>常用配置包含核心指标、层级下钻结构、依赖拓扑。查询窗口由页面时间选择器控制，PromQL 中保留 {window} 占位即可。</p>
        <ul>
          <li><strong>core_metric</strong>：卡片核心指标定义；metric 对应 prometheus.scalars 中的指标 key，label/target/unit/direction 控制展示名称、目标值、单位和阈值方向。</li>
          <li><strong>core_metric.metric</strong>：指定系统核心指标使用哪个单值查询结果；当配置了下钻层级时，页面会优先按下钻层级汇总展示，缺少下钻数据时再使用该指标兜底。</li>
          <li><strong>prometheus.scalars</strong>：单值指标查询；query 返回 Prometheus scalar/vector 单值，scale 可把秒转换成毫秒。</li>
          <li><strong>checkout_success_rate</strong>：示例中的业务成功率指标 key，定义在 prometheus.scalars 下；可被 core_metric.metric、健康分公式和概览指标引用，实际系统可按自己的指标命名替换。</li>
          <li><strong>prometheus.series</strong>：服务、接口维度查询；labels 决定返回结果用哪些标签拼成 key。</li>
          <li><strong>root_cause_rules.count_as_fault</strong>：是否把该根因指标计入故障；true 表示命中 min_rate/critical_rate 后影响服务、接口、总状态和健康分，false 表示只展示指标不判故障。</li>
          <li><strong>drilldown.services</strong>：下钻服务拓扑；现在不会用内置拓扑兜底，服务和接口要在这里写完整。</li>
          <li><strong>drilldown.dependencies</strong>：外部依赖拓扑；role 可用 upstream 或 downstream。</li>
        </ul>
        <pre><code>{
  "version": 1,
  "enabled": true,
  "engine": "prometheus-tempo",
  "namespace": "trade",
  "service_pattern": "api-gateway|cart|order|inventory|catalog",
  "core_metric": {
    "metric": "checkout_success_rate",
    "label": "下单成功率",
    "target": 99,
    "unit": "%",
    "direction": "higher"
  },
  "prometheus": {
    "scalars": {
      "checkout_success_rate": {
        "label": "下单成功率",
        "target": 99,
        "unit": "%",
        "direction": "higher",
        "query": "100 * sum(rate(ecommerce_checkout_outcomes_total{namespace=\"{namespace}\",service=\"api-gateway\",outcome=\"success\"}[{window}])) / clamp_min(sum(rate(ecommerce_checkout_outcomes_total{namespace=\"{namespace}\",service=\"api-gateway\",outcome=~\"success|conflict\"}[{window}])), 0.000001)",
        "fallback_query": "100 * sum(rate(ecommerce_http_requests_total{namespace=\"{namespace}\",service=\"api-gateway\",path=\"/api/checkout\",status=~\"2..\"}[{window}])) / clamp_min(sum(rate(ecommerce_http_requests_total{namespace=\"{namespace}\",service=\"api-gateway\",path=\"/api/checkout\"}[{window}])), 0.000001)"
      },
      "checkout_p95_ms": {
        "label": "Checkout P95",
        "target": 500,
        "unit": "ms",
        "direction": "lower",
        "scale": 1000,
        "query": "histogram_quantile(0.95, sum by (le) (rate(ecommerce_http_request_duration_seconds_bucket{namespace=\"{namespace}\",service=\"api-gateway\",path=\"/api/checkout\"}[{window}])))"
      },
      "checkout_rps": {
        "label": "Checkout RPS",
        "target": 0.01,
        "unit": "",
        "direction": "higher",
        "query": "sum(rate(ecommerce_http_requests_total{namespace=\"{namespace}\",service=\"api-gateway\",path=\"/api/checkout\"}[{window}]))"
      }
    },
    "series": {
      "service_success_rate": {
        "labels": ["service"],
        "query": "100 * sum by (service) (rate(ecommerce_http_requests_total{namespace=\"{namespace}\",service=~\"{services}\",status!~\"5..\"}[{window}])) / clamp_min(sum by (service) (rate(ecommerce_http_requests_total{namespace=\"{namespace}\",service=~\"{services}\"}[{window}])), 0.000001)"
      },
      "path_p95_ms": {
        "labels": ["service", "path"],
        "scale": 1000,
        "query": "histogram_quantile(0.95, sum by (service,path,le) (rate(ecommerce_http_request_duration_seconds_bucket{namespace=\"{namespace}\",service=~\"{services}\"}[{window}])))"
      }
    }
  },
  "root_cause_rules": [
    {
      "id": "inventory-conflict",
      "label": "库存冲突",
      "metric": "checkout_conflict_rate",
      "min_rate": 1,
      "critical_rate": 50,
      "min_rps": 0.001,
      "count_as_fault": true,
      "target_service_id": "inventory",
      "target_interface_id": "inventory-availability"
    }
  ],
  "drilldown": {
    "services": [
      {
        "id": "api-gateway",
        "name": "API 网关",
        "role": "入口层",
        "target_ms": 500,
        "paths": [
          { "id": "gateway-checkout", "name": "POST /api/checkout", "path": "/api/checkout", "target_ms": 500 },
          { "id": "gateway-products", "name": "GET /api/products", "path": "/api/products", "target_ms": 350 }
        ]
      },
      {
        "id": "cart",
        "name": "购物车服务",
        "role": "交易前置",
        "target_ms": 250,
        "paths": [
          { "id": "cart-add", "name": "POST /cart/&lt;user_id&gt;/items", "path": "/cart/&lt;user_id&gt;/items", "target_ms": 180 },
          { "id": "cart-query", "name": "GET /cart/&lt;user_id&gt;", "path": "/cart/&lt;user_id&gt;", "target_ms": 120 }
        ]
      },
      {
        "id": "order",
        "name": "订单服务",
        "role": "交易核心",
        "target_ms": 450,
        "paths": [
          { "id": "order-create", "name": "POST /orders", "path": "/orders", "target_ms": 350 }
        ]
      },
      {
        "id": "inventory",
        "name": "库存服务",
        "role": "履约校验",
        "target_ms": 250,
        "paths": [
          { "id": "inventory-availability", "name": "POST /availability", "path": "/availability", "target_ms": 160 }
        ]
      },
      {
        "id": "catalog",
        "name": "商品服务",
        "role": "商品读取",
        "target_ms": 250,
        "paths": [
          { "id": "catalog-list", "name": "GET /products", "path": "/products", "target_ms": 180 },
          { "id": "catalog-detail", "name": "GET /products/&lt;product_id&gt;", "path": "/products/&lt;product_id&gt;", "target_ms": 180 }
        ]
      }
    ],
    "dependencies": [
      { "id": "postgres", "name": "PostgreSQL", "role": "downstream", "kind": "数据库" },
      { "id": "redis", "name": "Redis", "role": "downstream", "kind": "缓存" },
      { "id": "kafka", "name": "Kafka", "role": "downstream", "kind": "消息队列" }
    ]
  },
  "keywords": ["checkout", "order-service"],
  "focus_service_id": "checkout-service",
  "focus_interface_id": "checkout-api"
}</code></pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Aim,
  Delete,
  Edit,
  Plus,
  RefreshRight,
} from '@element-plus/icons-vue'
import echarts from '@/lib/echarts'
import ObservabilityRouteTabs from '@/components/observability/ObservabilityRouteTabs.vue'
import {
  createSystemPostureEnvironment,
  createSystemPostureSystem,
  deleteSystemPostureSystem,
  getObservabilitySystemPosture,
  updateSystemPostureEnvironment,
  updateSystemPostureSystem,
} from '@/api/modules/ops'
import { useAuthStore } from '@/stores/auth'
import { openRouteInNewTab } from '@/utils/router'

defineProps({
  embedded: {
    type: Boolean,
    default: false,
  },
})

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const lastSystemStorageKey = 'sxdevops:observability:system-posture:last-system'
const loading = ref(false)
const systemSubmitting = ref(false)
const environmentSorting = ref(false)
const systemDialogVisible = ref(false)
const jsonHelpVisible = ref(false)
const drillDialogVisible = ref(false)
const topologyDialogVisible = ref(false)
const editingSystem = ref(null)
const systemPosture = ref({ summary: {}, systems: [], data_sources: [], selected_system: {}, topology: {}, timeline: [], quick_actions: [] })
const selectedSystemId = ref(typeof route.query.system === 'string' ? route.query.system : readLastSelectedSystemId())
const timeRange = ref(initialTimeRange())
const selectedNodeId = ref('')
const topologyChartRef = ref(null)
let topologyChart = null
let postureRequestSeq = 0

function defaultSystemForm() {
  return {
    name: '',
    environment: 'prod',
    domain: '业务域',
    metric_label: '成功率',
    metric_target: 99,
    metric_unit: '%',
    metric_direction: 'higher',
    rule_config_text: '{}',
    sort_order: 100,
  }
}

const systemForm = ref(defaultSystemForm())
const systemDomainOptions = ['业务域', '平台域', '基础设施域']
const timeRangeShortcuts = [
  {
    text: '最近 30 分钟',
    value: () => [new Date(Date.now() - 30 * 60 * 1000), new Date()],
  },
  {
    text: '最近 5 分钟',
    value: () => [new Date(Date.now() - 5 * 60 * 1000), new Date()],
  },
  {
    text: '最近 15 分钟',
    value: () => [new Date(Date.now() - 15 * 60 * 1000), new Date()],
  },
  {
    text: '最近 1 小时',
    value: () => [new Date(Date.now() - 60 * 60 * 1000), new Date()],
  },
  {
    text: '最近 6 小时',
    value: () => [new Date(Date.now() - 6 * 60 * 60 * 1000), new Date()],
  },
  {
    text: '最近 24 小时',
    value: () => [new Date(Date.now() - 24 * 60 * 60 * 1000), new Date()],
  },
]

const systems = computed(() => systemPosture.value.systems || [])
const topology = computed(() => selectedSystem.value.topology || systemPosture.value.topology || {})
const selectedSystem = computed(() => {
  const selected = systemPosture.value.selected_system || {}
  if (selectedSystemId.value) {
    const matched = systems.value.find(item => item.id === selectedSystemId.value)
    if (matched) {
      return selected.id === selectedSystemId.value ? selected : matched
    }
  }
  return selected.id ? selected : systems.value[0] || {}
})

const drillPath = ref([])
const detailPanelOpen = ref(false)
const postureEnvironments = computed(() => systemPosture.value.environments || [])
const environmentNameByKey = computed(() => postureEnvironments.value.reduce((acc, item) => {
  const key = normalizeEnvironmentKey(item.key || item.name)
  acc[key] = item.name || item.label || key
  return acc
}, {}))
const currentDrillParent = computed(() => drillPath.value[drillPath.value.length - 1] || null)
const drillCards = computed(() => (currentDrillParent.value ? currentDrillParent.value.children || [] : systems.value))
const environmentGroups = computed(() => groupSystemsByEnvironment(systems.value, postureEnvironments.value))
const showFocusPanel = computed(() => Boolean(focusTarget.value?.id))
const focusTarget = computed(() => {
  if (drillPath.value.length) {
    return selectedNode.value || currentDrillParent.value || selectedSystem.value || {}
  }
  return selectedSystem.value || {}
})
const focusEnvironmentLabel = computed(() => {
  const target = focusTarget.value || {}
  const source = target.environment || target.env || target.rule_config?.environment ? target : selectedSystem.value
  return environmentLabel(environmentKey(source || {}))
})
const focusMetrics = computed(() => {
  const target = focusTarget.value || {}
  const sloLabel = cardSlo(target).label
  const sourceMetrics = target.metrics || []
  const metrics = sourceMetrics.filter(metric => metric.label && metric.label !== sloLabel)
  return (metrics.length ? metrics : sourceMetrics).slice(0, 4)
})
const focusActions = computed(() => allowedQuickActions.value.slice(0, 3))
const drilldownEntryText = computed(() => `系统、子系统、模块与接口 · ${drilldownRows.value.length} 个节点`)
const topologyEntryText = computed(() => `上下游依赖健康度 · ${topology.value.node_count || 0} 个节点 · ${topology.value.call_count || 0} 条关系`)
const drillToolbarText = computed(() => {
  if (!drillPath.value.length) {
    return `系统 ${systems.value.length} 个 · 点击卡片查看详情，点下钻进入子系统、模块和接口`
  }
  const parent = currentDrillParent.value
  const childCount = parent?.children?.length || 0
  return `${parent?.name || '当前层级'} · 下级 ${childCount} 个 · 点击卡片查看详情，点下钻进入下一层`
})
const drilldownRows = computed(() => {
  if (!selectedSystem.value.id) return []
  return [
    {
      id: selectedSystem.value.id,
      name: selectedSystem.value.name,
      kind: 'system',
      status: selectedSystem.value.status,
      role: selectedSystem.value.domain,
      metrics: selectedSystem.value.metrics || [],
      children: selectedSystem.value.children || [],
      level: 0,
    },
    ...flattenNodes(selectedSystem.value.children || [], 1),
  ]
})

const selectedNode = computed(() => {
  if (!drilldownRows.value.length) return null
  return drilldownRows.value.find(item => item.id === selectedNodeId.value)
    || drilldownRows.value.find(item => item.status === 'critical')
    || drilldownRows.value[0]
})

const allowedQuickActions = computed(() => {
  const responseSelectedId = systemPosture.value.selected_system?.id || ''
  const source = responseSelectedId === selectedSystem.value.id
    ? (systemPosture.value.quick_actions || selectedSystem.value.actions || [])
    : (selectedSystem.value.actions || [])
  return source.filter(actionAllowed)
})

const canViewAlerts = computed(() => authStore.hasPermission('ops.alert.view'))
const canViewTrace = computed(() => authStore.hasPermission('ops.trace.view'))
const canQueryLogs = computed(() => authStore.hasPermission('ops.log.query'))
const canViewGrafana = computed(() => authStore.hasPermission('ops.grafana.view'))
const canViewEvents = computed(() => authStore.hasPermission('eventwall.view'))
const canManageSystemPosture = computed(() => authStore.hasPermission('ops.observability.system_posture.manage') || Boolean(systemPosture.value.context?.can_manage))

function readLastSelectedSystemId() {
  try {
    return window.localStorage.getItem(lastSystemStorageKey) || ''
  } catch {
    return ''
  }
}

function rememberSelectedSystemId(systemId = '') {
  if (!systemId) return
  try {
    window.localStorage.setItem(lastSystemStorageKey, systemId)
  } catch {
    // localStorage may be unavailable in restricted browser contexts.
  }
}

function parseRouteDate(value) {
  const date = new Date(String(value || ''))
  return Number.isNaN(date.getTime()) ? null : date
}

function initialTimeRange() {
  const start = typeof route.query.start === 'string' ? parseRouteDate(route.query.start) : null
  const end = typeof route.query.end === 'string' ? parseRouteDate(route.query.end) : null
  if (start && end && start < end) {
    return [start, end]
  }
  return [new Date(Date.now() - 30 * 60 * 1000), new Date()]
}

function systemPostureTimeParams() {
  const [start, end] = Array.isArray(timeRange.value) ? timeRange.value : []
  const startDate = start instanceof Date ? start : parseRouteDate(start)
  const endDate = end instanceof Date ? end : parseRouteDate(end)
  if (!startDate || !endDate || startDate >= endDate) return {}
  return {
    start: startDate.toISOString(),
    end: endDate.toISOString(),
  }
}

async function handleTimeRangeChange() {
  const timeQuery = systemPostureTimeParams()
  const nextQuery = { ...route.query, ...timeQuery }
  if (!timeQuery.start || !timeQuery.end) {
    delete nextQuery.start
    delete nextQuery.end
  }
  await router.replace({ query: nextQuery })
  await loadSystemPosture(selectedSystemId.value)
}

function flattenNodes(nodes = [], level = 0) {
  return nodes.flatMap((node) => [
    { ...node, level },
    ...flattenNodes(node.children || [], level + 1),
  ])
}

function abnormalChildren(system) {
  return flattenNodes(system.children || [], 1).filter(item => item.status === 'critical')
}

function hasChildren(item = {}) {
  return Array.isArray(item.children) && item.children.length > 0
}

function cardStatus(item = {}) {
  const status = item.status || item.base_status
  return ['critical', 'healthy', 'unknown'].includes(status) ? status : 'unknown'
}

function cardSlo(item = {}) {
  if (item?.core_metric && Object.keys(item.core_metric || {}).length) {
    return item.core_metric
  }
  const metrics = Array.isArray(item.metrics) ? item.metrics : []
  return (
    metrics.find(metric => /slo|成功率|可用率|通过率/i.test(String(metric.label || '')))
    || metrics[0]
    || {}
  )
}

function metricNumber(value) {
  if (value === undefined || value === null || value === '') return null
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  const normalized = String(value).replace(/,/g, '').replace('%', '').trim()
  if (!normalized) return null
  const numberValue = Number(normalized)
  return Number.isFinite(numberValue) ? numberValue : null
}

function isSloBreached(item = {}) {
  const metric = cardSlo(item)
  const value = metricNumber(metric.value)
  const target = metricNumber(metric.target)
  if (value === null || target === null) return false
  return metric.direction === 'lower' ? value > target : value < target
}

function cardLevel(item = {}) {
  if (Number.isFinite(Number(item.level))) {
    return `L${Number(item.level) + 1}`
  }
  return drillPath.value.length ? `L${drillPath.value.length + 1}` : 'L1'
}

function abnormalCount(item = {}) {
  return abnormalChildren(item).length
}

function cardMeta(system = {}) {
  if (system.kind && system.kind !== 'system') {
    return [cardLevel(system), kindLabel(system.kind), system.role].map(item => String(item || '').trim()).filter(Boolean).join(' · ')
  }
  return [cardLevel(system), system.domain]
    .map(item => String(item || '').trim())
    .filter(Boolean)
    .join(' · ')
}

function drillPathToIndex(id) {
  return drillPath.value.findIndex(item => item.id === id)
}

function resetDrill() {
  drillPath.value = []
  detailPanelOpen.value = true
  selectedNodeId.value = selectedSystem.value.id || ''
}

function drillUp() {
  if (!drillPath.value.length) return
  drillPath.value = drillPath.value.slice(0, -1)
  const last = drillPath.value[drillPath.value.length - 1]
  selectedNodeId.value = last?.id || selectedSystem.value.id || ''
  detailPanelOpen.value = true
}

function jumpDrill(item = {}) {
  const index = drillPathToIndex(item.id)
  if (index < 0) return
  drillPath.value = drillPath.value.slice(0, index + 1)
  selectedNodeId.value = item.id
  detailPanelOpen.value = true
}

function selectOverviewCard(item = {}) {
  if (!item?.id) return
  if (!drillPath.value.length) {
    void selectSystem(item, { silent: true, resetNode: false })
    selectedNodeId.value = item.id
  } else {
    selectedNodeId.value = item.id
  }
  detailPanelOpen.value = true
}

function drillIntoCard(item = {}) {
  if (!item?.id) return
  if (!drillPath.value.length) {
    void selectSystem(item, { silent: true, resetNode: false })
    drillPath.value = [{
      ...item,
      kind: 'system',
    }]
    selectedNodeId.value = item.id
    detailPanelOpen.value = true
    return
  }
  selectedNodeId.value = item.id
  if (hasChildren(item)) {
    const index = drillPathToIndex(item.id)
    if (index >= 0) {
      drillPath.value = drillPath.value.slice(0, index + 1)
    } else {
      drillPath.value = [...drillPath.value, item]
    }
  }
  detailPanelOpen.value = true
}

function isDrillCardActive(item = {}) {
  return (drillPath.value.length ? selectedNodeId.value === item.id : selectedSystem.value.id === item.id)
}

function tagType(status) {
  return {
    critical: 'danger',
    healthy: 'success',
  }[status] || 'info'
}

function statusLabel(status) {
  return {
    critical: '故障',
    healthy: '健康',
  }[status] || '未知'
}

function kindLabel(kind) {
  return {
    system: '系统',
    service: '服务',
    interface: '接口',
    dependency: '依赖',
  }[kind] || '节点'
}

function formatMetric(metric = {}) {
  if (metric.value === undefined || metric.value === null || metric.value === '') return '--'
  return `${metric.value}${metric.unit || ''}`
}

function targetText(metric = {}) {
  if (metric.target === undefined || metric.target === null || metric.target === '') return '--'
  return `${metric.target}${metric.unit || ''}`
}

function stringifyConfig(value = {}) {
  try {
    const normalized = value && typeof value === 'object' && !Array.isArray(value) ? { ...value } : {}
    return JSON.stringify(normalized, null, 2)
  } catch {
    return '{}'
  }
}

function parseRuleConfig(text) {
  const raw = String(text || '').trim()
  if (!raw) return {}
  const parsed = JSON.parse(raw)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('规则配置必须是 JSON 对象')
  }
  return parsed
}

function splitText(value) {
  return String(value || '')
    .split(/[\n,，]/)
    .map(item => item.trim())
    .filter(Boolean)
}

function normalizeEnvironmentKey(value = '') {
  const raw = String(value || '').trim()
  return raw || 'prod'
}

function environmentKey(system = {}) {
  return normalizeEnvironmentKey(system.environment || system.env || system.form?.environment || system.rule_config?.environment || 'prod')
}

function environmentLabel(key = '') {
  const normalized = normalizeEnvironmentKey(key)
  if (environmentNameByKey.value[normalized]) return environmentNameByKey.value[normalized]
  return {
    prod: '生产环境',
    production: '生产环境',
    staging: '预发环境',
    stage: '预发环境',
    pre: '预发环境',
    test: '测试环境',
    testing: '测试环境',
    dev: '开发环境',
    development: '开发环境',
    default: '默认环境',
  }[String(normalized).toLowerCase()] || normalized
}

function environmentOrder(key = '') {
  const order = { prod: 1, production: 1, staging: 2, stage: 2, pre: 2, test: 3, testing: 3, dev: 4, development: 4, default: 9 }
  return order[String(key).toLowerCase()] || 8
}

function effectiveCardStatus(item = {}) {
  const ownStatus = cardStatus(item)
  if (ownStatus === 'critical') return 'critical'
  const childStatuses = flattenNodes(item.children || [], 1).map((node) => {
    const nodeStatus = cardStatus(node)
    if (nodeStatus === 'critical') return 'critical'
    if (isSloBreached(node)) return 'critical'
    return nodeStatus
  })
  if (childStatuses.includes('critical')) return 'critical'
  if (isSloBreached(item)) return 'critical'
  if (ownStatus === 'unknown') return 'unknown'
  return ownStatus
}

function environmentCounts(items = []) {
  return items.reduce((acc, item) => {
    const status = cardStatus(item)
    acc[status] = (acc[status] || 0) + 1
    return acc
  }, { critical: 0, healthy: 0, unknown: 0 })
}

function environmentStatusFromCounts(counts = {}, total = 0) {
  if (counts.critical) return 'critical'
  if (total && counts.unknown === total) return 'unknown'
  return total ? 'healthy' : 'unknown'
}

function environmentStatus(items = []) {
  return environmentStatusFromCounts(environmentCounts(items), items.length)
}

function systemSortOrderValue(item = {}) {
  return Number(item.sort_order ?? item.form?.sort_order ?? 100)
}

function groupSystemsByEnvironment(items = [], environmentDefs = []) {
  const groups = new Map()
  environmentDefs.forEach((environment) => {
    const key = normalizeEnvironmentKey(environment.key || environment.name)
    if (!key) return
    groups.set(key, {
      id: environment.id,
      key,
      label: environment.name || environment.label || environmentLabel(key),
      sort_order: Number(environment.sort_order ?? environmentOrder(key)),
      source: environment.source || (environment.id ? 'configured' : 'derived'),
      items: [],
    })
  })
  items.forEach((item) => {
    const key = environmentKey(item)
    if (!groups.has(key)) {
      groups.set(key, { id: null, key, label: environmentLabel(key), sort_order: environmentOrder(key), source: 'derived', items: [] })
    }
    groups.get(key).items.push(item)
  })
  return Array.from(groups.values())
    .map((group) => {
      const sortedItems = [...group.items].sort((a, b) => (
        systemSortOrderValue(a) - systemSortOrderValue(b)
        || String(a.name || '').localeCompare(String(b.name || ''), 'zh-Hans-CN')
        || String(a.id || '').localeCompare(String(b.id || ''), 'en')
      ))
      const counts = environmentCounts(group.items)
      return {
        ...group,
        items: sortedItems,
        counts,
        status: environmentStatusFromCounts(counts, sortedItems.length),
      }
    })
    .sort((a, b) => (a.sort_order ?? environmentOrder(a.key)) - (b.sort_order ?? environmentOrder(b.key)) || a.label.localeCompare(b.label, 'zh-Hans-CN'))
}

function firstSystemInFirstEnvironment() {
  return environmentGroups.value.find(group => group.items.length > 0)?.items?.[0] || systems.value[0] || null
}

function systemExists(systemId = '') {
  return Boolean(systemId && systems.value.some(item => item.id === systemId))
}

function buildRuleConfigStructureFromSystem(system = {}, ruleConfig = {}) {
  const nextConfig = {
    ...(ruleConfig && typeof ruleConfig === 'object' && !Array.isArray(ruleConfig) ? ruleConfig : {}),
  }
  const services = Array.isArray(system.children) ? system.children : []
  const dependencies = Array.isArray(system.dependencies) ? system.dependencies : []

  if (!nextConfig.drilldown || typeof nextConfig.drilldown !== 'object' || Array.isArray(nextConfig.drilldown)) {
    nextConfig.drilldown = {}
  }
  if (!Array.isArray(nextConfig.drilldown.levels) || !nextConfig.drilldown.levels.length) {
    nextConfig.drilldown.levels = [
      { level: 'L1', kind: 'system', label: system.name || '业务系统', source: 'system' },
      { level: 'L2', kind: 'service', label: '子系统 / 服务', source: 'children' },
      { level: 'L3', kind: 'interface', label: '模块 / 接口', source: 'children.interfaces' },
      { level: 'L2', kind: 'dependency', label: '依赖项', source: 'dependencies' },
    ]
  }
  if (!Array.isArray(nextConfig.drilldown.services) || !nextConfig.drilldown.services.length) {
    nextConfig.drilldown.services = services.map(service => ({
      id: service.id,
      name: service.name,
      role: service.role || service.hint || '',
      interfaces: (service.children || []).map(item => item.id).filter(Boolean),
    })).filter(item => item.id)
  }
  if (!Array.isArray(nextConfig.drilldown.dependencies) || !nextConfig.drilldown.dependencies.length) {
    nextConfig.drilldown.dependencies = dependencies.map(dep => ({
      id: dep.id,
      role: dep.role || 'dependency',
      reason: dep.impact || dep.hint || dep.kind || '',
    })).filter(item => item.id)
  }

  if (!nextConfig.topology || typeof nextConfig.topology !== 'object' || Array.isArray(nextConfig.topology)) {
    nextConfig.topology = {}
  }
  if (!nextConfig.topology.root) {
    nextConfig.topology.root = system.id || ''
  }
  if (!Array.isArray(nextConfig.topology.nodes) || !nextConfig.topology.nodes.length) {
    const nodes = [
      { id: system.id, kind: 'system', label: system.name },
    ]
    services.forEach((service) => {
      if (service.id) nodes.push({ id: service.id, kind: service.kind || 'service', label: service.name, role: service.role || '' })
      ;(service.children || []).forEach((item) => {
        if (item.id) nodes.push({ id: item.id, kind: item.kind || 'interface', label: item.name })
      })
    })
    dependencies.forEach((dep) => {
      if (dep.id) nodes.push({ id: dep.id, kind: dep.kind || 'dependency', label: dep.name, role: dep.role || 'dependency' })
    })
    nextConfig.topology.nodes = nodes.filter(item => item.id)
  }
  if (!Array.isArray(nextConfig.topology.links) || !nextConfig.topology.links.length) {
    const links = []
    services.forEach((service) => {
      if (system.id && service.id) links.push({ source: system.id, target: service.id, type: 'drilldown' })
      ;(service.children || []).forEach((item) => {
        if (service.id && item.id) links.push({ source: service.id, target: item.id, type: 'interface' })
      })
    })
    dependencies.forEach((dep) => {
      if (!system.id || !dep.id) return
      if (dep.role === 'upstream') {
        links.push({ source: dep.id, target: system.id, type: 'upstream' })
      } else {
        links.push({ source: system.id, target: dep.id, type: dep.role || 'dependency' })
      }
    })
    nextConfig.topology.links = links
  }
  return nextConfig
}

function systemToForm(system = {}) {
  const form = system.form || {}
  const sourceRuleConfig = form.rule_config || system.rule_config || {}
  const ruleConfig = buildRuleConfigStructureFromSystem(system, sourceRuleConfig)
  const coreMetric = ruleConfig?.core_metric && typeof ruleConfig.core_metric === 'object'
    ? ruleConfig.core_metric
    : form.core_metric || system.core_metric || {}
  return {
    ...defaultSystemForm(),
    name: form.name || system.name || '',
    environment: form.environment || system.environment || 'prod',
    domain: systemDomainOptions.includes(form.domain || system.domain) ? form.domain || system.domain : '业务域',
    metric_label: coreMetric.label || form.core_metric?.label || system.core_metric?.label || '成功率',
    metric_target: Number(coreMetric.target ?? form.core_metric?.target ?? system.core_metric?.target ?? 99),
    metric_unit: coreMetric.unit || '%',
    metric_direction: coreMetric.direction || 'higher',
    rule_config_text: stringifyConfig(ruleConfig),
    sort_order: form.sort_order ?? system.sort_order ?? 100,
  }
}

function hasStructuredServiceSpecs(items = []) {
  return Array.isArray(items) && items.some((service) => (
    service
    && typeof service === 'object'
    && !Array.isArray(service)
    && Array.isArray(service.interfaces)
    && service.interfaces.some((item) => item && typeof item === 'object' && !Array.isArray(item))
  ))
}

function buildServiceSpecsFromChildren(system = {}) {
  return (Array.isArray(system.children) ? system.children : [])
    .filter((service) => service && typeof service === 'object' && !Array.isArray(service))
    .map((service) => ({
      id: service.id || '',
      name: service.name || '',
      role: service.role || '',
      base_status: service.base_status || service.status || 'unknown',
      metrics: Array.isArray(service.metrics) ? service.metrics : [],
      interfaces: (Array.isArray(service.children) ? service.children : [])
        .filter((item) => item && typeof item === 'object' && !Array.isArray(item))
        .map((item) => ({
          id: item.id || '',
          name: item.name || '',
          base_status: item.base_status || item.status || 'unknown',
          hint: item.hint || '',
          metrics: Array.isArray(item.metrics) ? item.metrics : [],
        })),
    }))
    .filter((service) => service.id)
}

function hasStructuredDependencies(items = []) {
  return Array.isArray(items) && items.some((item) => (
    item
    && typeof item === 'object'
    && !Array.isArray(item)
    && item.name
  ))
}

function buildDependenciesFromSource(system = {}) {
  return (Array.isArray(system.dependencies) ? system.dependencies : [])
    .filter((item) => item && typeof item === 'object' && !Array.isArray(item))
    .map((item) => ({
      id: item.id || '',
      name: item.name || '',
      role: item.role || 'dependency',
      kind: item.kind || '',
      base_status: item.base_status || item.status || 'unknown',
      metrics: Array.isArray(item.metrics) ? item.metrics : [],
      impact: item.impact || item.hint || '',
    }))
    .filter((item) => item.id)
}

function formToPayload(sourceForm = systemForm.value, sourceSystem = editingSystem.value) {
  const form = sourceForm
  const name = form.name.trim()
  const ruleConfig = parseRuleConfig(form.rule_config_text)
  const formSnapshot = sourceSystem?.form || {}
  const coreMetric = formSnapshot.core_metric || sourceSystem?.core_metric || {}
  const metric = {
    ...coreMetric,
    label: form.metric_label.trim() || 'SLO',
    target: Number(form.metric_target ?? coreMetric.target ?? 99.9),
    unit: form.metric_unit.trim() || '',
    direction: form.metric_direction || 'higher',
  }
  const drilldownConfig = ruleConfig.drilldown && typeof ruleConfig.drilldown === 'object' ? ruleConfig.drilldown : {}
  const sourceServiceSpecs = Array.isArray(formSnapshot.service_specs)
    ? formSnapshot.service_specs
    : Array.isArray(sourceSystem?.service_specs)
      ? sourceSystem.service_specs
      : []
  const fallbackServiceSpecs = hasStructuredServiceSpecs(sourceServiceSpecs)
    ? sourceServiceSpecs
    : buildServiceSpecsFromChildren(sourceSystem)
  const serviceSpecs = hasStructuredServiceSpecs(drilldownConfig.services)
    ? drilldownConfig.services
    : hasStructuredServiceSpecs(ruleConfig.service_specs)
      ? ruleConfig.service_specs
      : fallbackServiceSpecs
  const sourceDependencies = Array.isArray(formSnapshot.dependencies)
    ? formSnapshot.dependencies
    : Array.isArray(sourceSystem?.dependencies)
      ? sourceSystem.dependencies
      : []
  const fallbackDependencies = hasStructuredDependencies(sourceDependencies)
    ? sourceDependencies
    : buildDependenciesFromSource(sourceSystem)
  const dependencies = hasStructuredDependencies(drilldownConfig.dependencies)
    ? drilldownConfig.dependencies
    : hasStructuredDependencies(ruleConfig.dependencies)
      ? ruleConfig.dependencies
      : fallbackDependencies
  const playbook = Array.isArray(ruleConfig.playbook)
    ? ruleConfig.playbook
    : formSnapshot.playbook || sourceSystem?.playbook || []
  const keywords = Array.isArray(ruleConfig.keywords)
    ? ruleConfig.keywords
    : formSnapshot.keywords || sourceSystem?.keywords || splitText(`${name}，${form.domain}`)
  const effectiveRuleConfig = {
    ...ruleConfig,
    core_metric: {
      ...(ruleConfig.core_metric && typeof ruleConfig.core_metric === 'object' ? ruleConfig.core_metric : {}),
      label: metric.label,
      target: metric.target,
      unit: metric.unit,
      direction: metric.direction,
    },
  }
  return {
    name,
    environment: form.environment.trim() || 'prod',
    domain: form.domain.trim(),
    tier: formSnapshot.tier || sourceSystem?.tier || '',
    owner: formSnapshot.owner || sourceSystem?.owner || '',
    summary: formSnapshot.summary || sourceSystem?.summary || '',
    keywords,
    core_metric: metric,
    metrics: formSnapshot.metrics || sourceSystem?.metrics || [],
    service_specs: serviceSpecs,
    dependencies,
    rule_config: effectiveRuleConfig,
    playbook,
    focus_service_id: ruleConfig.focus_service_id || formSnapshot.focus_service_id || sourceSystem?.focus_service_id || '',
    focus_interface_id: ruleConfig.focus_interface_id || formSnapshot.focus_interface_id || sourceSystem?.focus_interface_id || '',
    focus_keyword: ruleConfig.focus_keyword || formSnapshot.focus_keyword || sourceSystem?.focus_keyword || name,
    sort_order: Number(form.sort_order ?? 100),
    is_enabled: true,
  }
}

function openCreateSystem(environment = 'prod') {
  editingSystem.value = null
  const targetEnvironment = normalizeEnvironmentKey(environment)
  systemForm.value = { ...defaultSystemForm(), environment: targetEnvironment }
  systemDialogVisible.value = true
}

function openEditSystem(system) {
  editingSystem.value = system
  systemForm.value = systemToForm(system)
  systemDialogVisible.value = true
}

async function openCreateEnvironment() {
  try {
    const { value } = await ElMessageBox.prompt('请输入环境名称', '新增环境', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：生产环境 / 华东生产 / 灰度环境',
      inputPattern: /\S+/,
      inputErrorMessage: '环境名称不能为空',
    })
    const saved = await createSystemPostureEnvironment({
      name: normalizeEnvironmentKey(value),
      sort_order: (postureEnvironments.value.length + 1) * 10,
    })
    const environment = saved?.key || normalizeEnvironmentKey(value)
    ElMessage.success('环境已添加，可在该环境下新增卡片')
    await loadSystemPosture(selectedSystemId.value)
    await nextTick()
    openCreateSystem(environment)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error('新增环境失败')
    }
  }
}

async function renameEnvironment(group = {}) {
  const oldKey = group.key
  if (!oldKey) return
  try {
    const { value } = await ElMessageBox.prompt('请输入新的环境名称', '重命名环境', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: group.label,
      inputPattern: /\S+/,
      inputErrorMessage: '环境名称不能为空',
    })
    const newLabel = normalizeEnvironmentKey(value)
    if (newLabel === group.label) return
    if (group.id) {
      await updateSystemPostureEnvironment(group.id, { name: newLabel })
    } else {
      await createSystemPostureEnvironment({
        key: oldKey,
        name: newLabel,
        sort_order: group.sort_order ?? environmentOrder(oldKey),
      })
    }
    ElMessage.success('环境名称已更新')
    await loadSystemPosture(selectedSystemId.value)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error('重命名环境失败')
    }
  }
}

async function ensureEnvironmentRecord(group = {}, sortOrder = 100) {
  if (group.id) {
    return group
  }
  const saved = await createSystemPostureEnvironment({
    key: group.key,
    name: group.label || environmentLabel(group.key),
    sort_order: sortOrder,
  })
  return {
    ...group,
    id: saved?.id,
    key: saved?.key || group.key,
    label: saved?.name || group.label,
  }
}

async function moveEnvironment(group = {}, direction = 0) {
  if (!group?.key || environmentSorting.value) return
  const currentGroups = environmentGroups.value
  const currentIndex = currentGroups.findIndex(item => item.key === group.key)
  const targetIndex = currentIndex + direction
  if (currentIndex < 0 || targetIndex < 0 || targetIndex >= currentGroups.length) return

  const reordered = [...currentGroups]
  const [moved] = reordered.splice(currentIndex, 1)
  reordered.splice(targetIndex, 0, moved)

  environmentSorting.value = true
  try {
    const persistedGroups = []
    for (let index = 0; index < reordered.length; index += 1) {
      persistedGroups.push(await ensureEnvironmentRecord(reordered[index], (index + 1) * 10))
    }
    await Promise.all(persistedGroups.map((item, index) => (
      item.id
        ? updateSystemPostureEnvironment(item.id, { sort_order: (index + 1) * 10 })
        : Promise.resolve()
    )))
    ElMessage.success('环境顺序已更新')
    await loadSystemPosture(selectedSystemId.value)
  } catch (error) {
    ElMessage.error('调整环境顺序失败')
  } finally {
    environmentSorting.value = false
  }
}

async function saveSystem() {
  let payload
  try {
    payload = formToPayload()
  } catch (error) {
    ElMessage.warning(error.message || '规则配置不是合法 JSON')
    return
  }
  if (!payload.name) {
    ElMessage.warning('请填写系统名称')
    return
  }
  systemSubmitting.value = true
  try {
    const saved = editingSystem.value?.source_id
      ? await updateSystemPostureSystem(editingSystem.value.source_id, payload)
      : await createSystemPostureSystem(payload)
    systemDialogVisible.value = false
    ElMessage.success(editingSystem.value ? '系统卡片已更新' : '系统卡片已新增')
    await loadSystemPosture(saved?.id ? `custom-${saved.id}` : selectedSystemId.value)
  } finally {
    systemSubmitting.value = false
  }
}

async function removeSystem(system) {
  try {
    await ElMessageBox.confirm(`确认删除「${system.name}」系统卡片？`, '删除系统卡片', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  if (system.source_id && system.builtin_backed) {
    await updateSystemPostureSystem(system.source_id, { ...formToPayload(systemToForm(system), system), is_enabled: false })
  } else if (system.source_id) {
    await deleteSystemPostureSystem(system.source_id)
  } else {
    await createSystemPostureSystem({ ...formToPayload(systemToForm(system), system), is_enabled: false })
  }
  ElMessage.success('系统卡片已删除')
  if (selectedSystemId.value === system.id) {
    selectedSystemId.value = ''
    selectedNodeId.value = ''
  }
  await loadSystemPosture(selectedSystemId.value)
}

function actionAllowed(action) {
  if (action.key === 'alert') return canViewAlerts.value
  if (action.key === 'trace') return canViewTrace.value
  if (action.key === 'log') return canQueryLogs.value
  if (action.key === 'events') return canViewEvents.value
  if (action.key === 'grafana') return canViewGrafana.value
  return true
}

function go(path, query = {}) {
  if (!path) return
  openRouteInNewTab(router, { path, query })
}

function goAction(action) {
  go(action.path, action.query || {})
}

async function selectSystem(system, options = {}) {
  if (!system?.id) return
  if (selectedSystemId.value === system.id) {
    detailPanelOpen.value = true
    selectedNodeId.value = selectedNodeId.value || system.focus?.interface_id || system.focus?.service_id || system.id
    rememberSelectedSystemId(system.id)
    return
  }
  selectedSystemId.value = system.id
  selectedNodeId.value = system.focus?.interface_id || system.focus?.service_id || system.id
  detailPanelOpen.value = true
  rememberSelectedSystemId(system.id)
  const nextQuery = { ...route.query, system: system.id }
  delete nextQuery.tab
  router.replace({ query: nextQuery })
  await loadSystemPosture(system.id, options)
}

function selectNode(node) {
  selectedNodeId.value = node?.id || ''
}

async function loadSystemPosture(systemId = selectedSystemId.value, options = {}) {
  const { silent = false, resetNode = true } = options
  const requestSeq = ++postureRequestSeq
  const requestedSystemId = systemId || ''
  if (!silent) loading.value = true
  try {
    const response = await getObservabilitySystemPosture({
      system: requestedSystemId || undefined,
      ...systemPostureTimeParams(),
    })
    if (requestSeq !== postureRequestSeq) return
    systemPosture.value = response
    const responseSelectedId = response.selected_system_id || response.selected_system?.id || ''
    const fallbackSystem = firstSystemInFirstEnvironment()
    const nextSystemId = systemExists(requestedSystemId)
      ? requestedSystemId
      : fallbackSystem?.id || responseSelectedId || ''
    if (nextSystemId && responseSelectedId !== nextSystemId && requestedSystemId !== nextSystemId) {
      selectedSystemId.value = nextSystemId
      rememberSelectedSystemId(nextSystemId)
      await loadSystemPosture(nextSystemId, options)
      return
    }
    selectedSystemId.value = nextSystemId || responseSelectedId || requestedSystemId || ''
    if (selectedSystemId.value) {
      detailPanelOpen.value = true
      rememberSelectedSystemId(selectedSystemId.value)
    }
    if (resetNode) {
      selectedNodeId.value = response.selected_system?.focus?.interface_id
        || response.selected_system?.focus?.service_id
        || response.selected_system?.id
        || selectedSystemId.value
        || ''
    }
    if (topologyDialogVisible.value) {
      await nextTick()
      renderTopology()
    }
  } finally {
    if (!silent) loading.value = false
  }
}

async function openDrilldownDialog() {
  if (!selectedSystem.value?.id) return
  selectedNodeId.value = selectedNode.value?.id || selectedSystem.value.focus?.interface_id || selectedSystem.value.focus?.service_id || selectedSystem.value.id
  drillDialogVisible.value = true
}

async function openTopologyDialog() {
  if (!selectedSystem.value?.id) return
  topologyDialogVisible.value = true
  await nextTick()
  renderTopology()
}

function nodeColor(status, kind) {
  if (status === 'critical') return '#f54a45'
  if (status === 'warning') return '#ff8800'
  if (kind === 'system') return '#3370ff'
  if (kind === 'service') return '#00a870'
  if (kind === 'interface') return '#8f959e'
  return '#646a73'
}

function renderTopology() {
  if (!topologyDialogVisible.value || !topologyChartRef.value) return
  if (topologyChart && topologyChart.getDom() !== topologyChartRef.value) {
    topologyChart.dispose()
    topologyChart = null
  }
  if (!topologyChart) {
    topologyChart = echarts.init(topologyChartRef.value)
    topologyChart.on('click', (params) => {
      if (params.dataType !== 'node') return
      const match = drilldownRows.value.find(item => item.id === params.data.id)
      if (match) {
        selectedNodeId.value = match.id
        topologyDialogVisible.value = false
        drillDialogVisible.value = true
      }
    })
  }

  const rawNodes = topology.value.nodes || []
  const rawLinks = topology.value.links || []
  const width = topologyChartRef.value.clientWidth || 900
  const height = topologyChartRef.value.clientHeight || 360
  const groups = rawNodes.reduce((acc, node) => {
    const key = node.category || node.kind || 'dependency'
    acc[key] = acc[key] || []
    acc[key].push(node)
    return acc
  }, {})
  const xMap = { upstream: 0.12, dependency: 0.12, system: 0.34, service: 0.54, interface: 0.78, downstream: 0.9 }

  const positionedNodes = rawNodes.map((node) => {
    const category = node.category || node.kind || 'dependency'
    const group = groups[category] || [node]
    const index = group.findIndex(item => item.id === node.id)
    const count = group.length || 1
    return {
      id: node.id,
      name: node.name,
      value: node.name,
      x: width * (xMap[category] || 0.5),
      y: ((index + 1) * height) / (count + 1),
      symbolSize: node.kind === 'system' ? 64 : node.kind === 'service' ? 48 : 38,
      itemStyle: {
        color: nodeColor(node.status, node.kind),
        borderColor: '#ffffff',
        borderWidth: 2,
        shadowBlur: node.status === 'critical' ? 10 : 4,
        shadowColor: node.status === 'critical' ? 'rgba(245, 74, 69, 0.18)' : 'rgba(31, 35, 41, 0.08)',
      },
      label: {
        show: true,
        formatter: node.name.length > 14 ? `${node.name.slice(0, 13)}...` : node.name,
      },
    }
  })

  topologyChart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        if (params.dataType === 'edge') return `${params.data.source} → ${params.data.target}`
        return params.data?.name || ''
      },
    },
    series: [
      {
        type: 'graph',
        layout: 'none',
        roam: true,
        draggable: true,
        label: { show: true, position: 'bottom', color: '#1f2329', fontSize: 11 },
        emphasis: { focus: 'adjacency', scale: true },
        data: positionedNodes,
        links: rawLinks.map(link => ({
          source: link.source,
          target: link.target,
          value: link.value || 1,
          symbol: ['none', 'arrow'],
          symbolSize: 8,
          lineStyle: {
            color: link.kind === 'upstream' ? '#3370ff' : link.kind === 'downstream' ? '#f54a45' : '#8f959e',
            width: 1 + Math.min(2, Number(link.value || 1) * 0.25),
            opacity: 0.72,
            curveness: 0.06,
          },
        })),
      },
    ],
  }, true)
  topologyChart.resize()
}

function disposeTopology() {
  topologyChart?.dispose()
  topologyChart = null
}

function handleResize() {
  topologyChart?.resize()
}

watch(
  () => [topologyDialogVisible.value, selectedSystem.value?.id, topology.value.node_count, topology.value.call_count].join('|'),
  async () => {
    await nextTick()
    if (topologyDialogVisible.value) {
      renderTopology()
    }
  }
)

watch(selectedNode, (node) => {
  if (node?.id && node.id !== selectedNodeId.value) selectedNodeId.value = node.id
})

onMounted(async () => {
  await loadSystemPosture()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  disposeTopology()
})
</script>

<style scoped>
.system-posture-page {
  --posture-loading-mask: color-mix(in srgb, var(--card-bg) 82%, transparent);
  --fm-bg: #f7f8fa;
  --fm-panel: #ffffff;
  --fm-text: #1f2329;
  --fm-muted: #646a73;
  --fm-subtle: #8f959e;
  --fm-border: #e5e7eb;
  --fm-border-soft: #eef0f4;
  --fm-blue: #3370ff;
  --fm-blue-soft: #eff4ff;
  --fm-red: #f54a45;
  --fm-red-soft: #fff2f0;
  --fm-amber: #ff8800;
  --fm-amber-soft: #fff7e6;
  --fm-green: #00a870;
  --fm-green-soft: #eefaf4;
  color: var(--fm-text);
  display: flex;
  flex-direction: column;
  gap: 6px;
  letter-spacing: 0;
}

.panel {
  background: linear-gradient(180deg, #ffffff 0%, #fbfcff 100%);
  border: 1px solid rgba(31, 35, 41, 0.08);
  border-radius: 8px;
  box-shadow: 0 6px 18px rgba(31, 35, 41, 0.04);
  padding: 14px;
}

.hero {
  align-items: center;
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36, 91, 219, 0.09);
  display: flex;
  justify-content: space-between;
  gap: 16px;
  min-height: 64px;
  padding: 14px 16px;
}

.release-hero-title-row {
  align-items: center;
  display: flex;
  gap: 12px;
}

.release-hero-title-inline {
  flex-wrap: wrap;
}

.page-inline-desc {
  color: #475569;
  flex: 0 1 auto;
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
  transform: translateY(1px);
}

.hero h2 {
  color: var(--fm-text);
  font-size: 23px;
  font-weight: 600;
  line-height: 1.12;
  margin: 0;
}

.hero-icon {
  align-items: center;
  background: linear-gradient(135deg, #edf4ff 0%, #f4fbff 100%);
  border: 1px solid #d9e6ff;
  border-radius: 14px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
  color: #245bdb;
  display: inline-flex;
  font-size: 20px;
  height: 42px;
  justify-content: center;
  width: 42px;
}

.hero.panel {
  border-radius: 20px;
}

.hero-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.hero-actions :deep(.el-button) {
  border-radius: 10px;
  font-weight: 500;
  min-height: 32px;
  padding: 0 14px;
}

.overview-shell {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 250, 252, 0.92) 100%);
  border: 1px solid rgba(31, 35, 41, 0.08);
  border-radius: 8px;
  box-shadow: 0 8px 22px rgba(31, 35, 41, 0.04);
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
  min-height: 0;
  align-content: start;
  padding: 8px;
}

.system-posture-page--embedded .overview-shell {
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
  min-height: auto;
  padding: 0;
}

.overview-layout,
.drill-layout {
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(0, 2.05fr) minmax(280px, 0.7fr);
}

.overview-layout.is-root {
  grid-template-columns: minmax(0, 1fr);
}

.system-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.environment-groups {
  display: grid;
  gap: 14px;
}

.environment-group {
  border-top: 1px solid rgba(226, 232, 240, 0.9);
  display: grid;
  gap: 10px;
  padding-top: 12px;
}

.environment-group:first-child {
  border-top: 0;
  padding-top: 0;
}

.environment-group__head {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  min-height: 28px;
}

.environment-title,
.environment-summary,
.environment-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  min-width: 0;
}

.environment-title {
  flex: 1 1 auto;
}

.environment-actions {
  flex: 0 0 auto;
  gap: 4px;
}

.environment-title strong {
  color: var(--fm-text);
  font-size: 14px;
  font-weight: 650;
  line-height: 1.25;
}

.environment-title em,
.environment-summary span {
  border-radius: 999px;
  color: var(--fm-muted);
  font-size: 12px;
  font-style: normal;
  line-height: 1.35;
}

.environment-title em {
  background: #f5f6f8;
  padding: 2px 8px;
}

.environment-summary span {
  background: rgba(247, 249, 252, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.86);
  padding: 2px 7px;
}

.environment-actions :deep(.el-button) {
  border-radius: 6px;
  font-weight: 500;
  margin-left: 0;
  min-height: 28px;
  padding: 0 5px;
}

.environment-actions :deep(.el-button--primary) {
  margin-left: 2px;
  padding: 0 9px;
}

.environment-dot {
  background: var(--fm-subtle);
  border-radius: 999px;
  height: 8px;
  width: 8px;
}

.environment-dot.is-critical {
  background: #d83931;
  box-shadow: 0 0 0 3px rgba(245, 74, 69, 0.08);
}

.environment-dot.is-warning {
  background: #c26300;
  box-shadow: 0 0 0 3px rgba(255, 136, 0, 0.08);
}

.environment-dot.is-healthy {
  background: #087a55;
  box-shadow: 0 0 0 3px rgba(0, 168, 112, 0.08);
}

.overview-systems-panel {
  border-color: rgba(203, 213, 225, 0.82);
  box-shadow: 0 0 0 1px rgba(226, 232, 240, 0.74), 0 4px 14px rgba(31, 35, 41, 0.025);
  min-height: 0;
  min-width: 0;
}

.overview-shell :deep(.el-loading-mask) {
  border-radius: inherit;
}

.overview-shell :deep(.el-loading-spinner) {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  margin-top: 0;
  transform: translateY(-50%);
}

.overview-shell :deep(.el-loading-spinner .circular) {
  width: 32px;
  height: 32px;
}

.overview-shell :deep(.el-loading-spinner .path) {
  stroke: var(--el-color-primary);
}

.overview-shell :deep(.el-loading-spinner .el-loading-text) {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  margin: 0;
}

.overview-toolbar {
  align-items: center;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid rgba(226, 232, 240, 0.86);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(31, 35, 41, 0.02);
  display: flex;
  justify-content: space-between;
  margin: 0;
  padding: 8px 10px;
}

.overview-toolbar h3 {
  color: var(--fm-text);
  font-size: 15px;
  font-weight: 600;
  line-height: 1.2;
  margin: 0;
}

.overview-toolbar span {
  color: var(--fm-muted);
  display: inline-block;
  font-size: 12px;
  margin-top: 4px;
}

.overview-toolbar__actions {
  align-items: center;
  display: flex;
  gap: 8px;
}

.system-posture-time-picker {
  width: 330px;
}

.system-posture-time-picker :deep(.el-range__icon),
.system-posture-time-picker :deep(.el-range-separator) {
  color: var(--fm-muted);
}

.drill-breadcrumb {
  align-items: center;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.drill-breadcrumb button {
  background: transparent;
  border: 1px solid transparent;
  border-radius: 999px;
  color: var(--fm-muted);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  padding: 2px 8px;
}

.drill-breadcrumb button.active {
  background: #ffffff;
  border-color: rgba(226, 232, 240, 0.96);
  color: var(--fm-text);
  font-weight: 600;
}

.drill-breadcrumb span {
  color: var(--fm-subtle);
  font-size: 12px;
  margin-top: 0;
}

.overview-toolbar :deep(.el-button) {
  border-radius: 6px;
  font-weight: 500;
}

.system-card {
  background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
  border: 1px solid rgba(31, 35, 41, 0.08);
  border-radius: 8px;
  box-shadow: 0 3px 12px rgba(31, 35, 41, 0.025);
  color: inherit;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  min-height: 184px;
  padding: 12px;
  text-align: left;
  transition: background 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.system-card:hover,
.system-card.active {
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border-color: rgba(51, 112, 255, 0.28);
  box-shadow: 0 8px 18px rgba(51, 112, 255, 0.07);
  transform: translateY(-1px);
}

.system-card.is-slo-breached {
  background: linear-gradient(180deg, #fffafa 0%, #fff7f5 100%);
  border-color: rgba(216, 57, 49, 0.14);
}

.system-card.is-slo-breached:hover,
.system-card.is-slo-breached.active {
  background: linear-gradient(180deg, #ffffff 0%, #fff5f2 100%);
  border-color: rgba(216, 57, 49, 0.22);
  box-shadow: 0 8px 18px rgba(216, 57, 49, 0.055);
}

.system-card.is-critical:not(:hover):not(.active) {
  border-color: rgba(216, 57, 49, 0.16);
}

.system-card.is-warning:not(:hover):not(.active) {
  border-color: var(--fm-border);
}

.system-card__head,
.system-card__title,
.system-card__meta,
.system-card__signals,
.score-row,
.section-head,
.dependency-card__head,
.section-tags,
.action-row {
  align-items: center;
  display: flex;
  gap: 8px;
}

.system-card__head,
.section-head,
.dependency-card__head {
  justify-content: space-between;
}

.system-card__title {
  flex: 1;
  min-width: 0;
}

.system-card__title strong {
  color: var(--fm-text);
  font-size: 15px;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.system-card__ops {
  align-items: center;
  display: inline-flex;
  flex-shrink: 0;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.16s ease;
}

.system-card:hover .system-card__ops,
.system-card.active .system-card__ops,
.system-card:focus-within .system-card__ops {
  opacity: 1;
}

.system-card__ops :deep(.el-button) {
  border-radius: 6px;
  color: var(--fm-subtle);
  height: 24px;
  padding: 0 5px;
  width: 24px;
}

.system-card__ops :deep(.el-button:hover) {
  background: #f4f6f8;
  color: var(--fm-text);
}

.system-card__meta,
.system-card__signals,
.focus-meta {
  color: var(--fm-muted);
  flex-wrap: wrap;
  font-size: 12px;
  margin-top: 8px;
}

.system-card__meta {
  display: block;
  margin-top: 6px;
  min-height: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.score-row {
  align-items: center;
  color: var(--fm-muted);
  display: flex;
  font-size: 12px;
  gap: 8px;
  margin-top: auto;
  border-top: 1px solid var(--fm-border-soft);
  padding-top: 9px;
}

.score-row strong {
  color: var(--fm-text);
  font-size: 15px;
  font-weight: 650;
}

.score-row em,
.drill-action {
  border-radius: 7px;
  font-size: 12px;
  font-style: normal;
  font-weight: 500;
  margin-left: auto;
}

.drill-action {
  align-items: center;
  border: 1px solid rgba(51, 112, 255, 0.18);
  box-shadow: 0 2px 6px rgba(51, 112, 255, 0.06);
  cursor: pointer;
  display: inline-flex;
  gap: 4px;
  line-height: 1.4;
  min-height: 26px;
  padding: 0 10px;
  transition: background 0.16s ease, border-color 0.16s ease, color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.drill-action::after {
  content: '›';
  font-size: 15px;
  line-height: 1;
}

.drill-action:hover {
  border-color: rgba(51, 112, 255, 0.34);
  box-shadow: 0 4px 10px rgba(51, 112, 255, 0.1);
  transform: translateY(-1px);
}

.drill-action:active {
  box-shadow: 0 2px 6px rgba(31, 35, 41, 0.06);
  transform: translateY(0);
}

.score-row em {
  border: 0;
  padding: 2px 7px;
}

.score-row em.is-critical,
.drill-action.is-critical {
  background: #fff1f0;
  color: #d83931;
}

.score-row em.is-warning,
.drill-action.is-warning {
  background: #fff7e6;
  color: #c26300;
}

.score-row em.is-healthy,
.drill-action.is-healthy {
  background: #edf8f3;
  color: #087a55;
}

.score-row em.is-offline,
.drill-action.is-offline {
  background: #f2f3f5;
  color: var(--fm-muted);
}

.core-metric {
  align-items: center;
  background: rgba(247, 249, 252, 0.88);
  border: 1px solid rgba(226, 232, 240, 0.8);
  border-radius: 8px;
  display: grid;
  gap: 2px 8px;
  grid-template-columns: minmax(0, 1fr) auto;
  margin-top: 10px;
  min-height: 58px;
  padding: 8px 10px;
}

.system-card.is-slo-breached .core-metric {
  background: rgba(255, 247, 245, 0.72);
  border-color: rgba(216, 57, 49, 0.12);
}

.system-card.is-slo-breached .core-metric em {
  border-color: rgba(216, 57, 49, 0.16);
  color: #ad352f;
}

.core-metric span {
  grid-column: 1;
}

.core-metric strong {
  grid-column: 1;
}

.core-metric em {
  align-self: center;
  background: #ffffff;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 999px;
  grid-column: 2;
  grid-row: 1 / span 2;
  padding: 2px 8px;
}

.core-metric span,
.core-metric em,
.metric-cell span,
.metric-cell em,
.dependency-card span,
.dependency-card p {
  color: var(--fm-muted);
  font-size: 12px;
  font-style: normal;
  line-height: 1.45;
}

.core-metric strong {
  color: var(--fm-text);
  font-size: 18px;
  font-weight: 650;
}

.metric-cell strong {
  color: var(--fm-text);
  font-size: 16px;
  font-weight: 650;
}

.system-card__signals {
  gap: 6px;
  margin-top: 8px;
}

.system-card__signals span {
  background: #f6f7f9;
  border-radius: 999px;
  color: var(--fm-muted);
  font-size: 11px;
  line-height: 1.35;
  padding: 2px 7px;
}

.focus-panel {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(249, 251, 255, 0.96) 100%);
  border-color: rgba(203, 213, 225, 0.82);
  box-shadow: 0 0 0 1px rgba(226, 232, 240, 0.74), 0 4px 14px rgba(31, 35, 41, 0.025);
  min-width: 0;
  padding: 12px;
}

.section-head {
  margin-bottom: 10px;
}

.section-head h3 {
  color: var(--fm-text);
  font-size: 15px;
  font-weight: 600;
  margin: 0;
}

.focus-heading {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.focus-heading h3,
.focus-heading span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.focus-heading span {
  color: var(--fm-muted);
  font-size: 12px;
  line-height: 1.35;
}

.focus-kpis {
  display: grid;
  gap: 6px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.focus-kpi {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 8px;
  display: grid;
  gap: 2px;
  min-width: 0;
  min-height: 58px;
  padding: 6px 8px;
}

.focus-kpi span,
.focus-kpi em,
.focus-block__title,
.compact-metric span,
.compact-metric em {
  color: var(--fm-muted);
  font-size: 12px;
  font-style: normal;
  line-height: 1.45;
}

.focus-kpi strong {
  color: var(--fm-text);
  font-size: 18px;
  font-weight: 650;
  line-height: 1.15;
}

.focus-entry-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 8px;
}

.focus-entry {
  background: linear-gradient(180deg, #ffffff 0%, #fbfcff 100%);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 8px;
  box-shadow: 0 3px 10px rgba(31, 35, 41, 0.025);
  color: inherit;
  cursor: pointer;
  display: grid;
  gap: 4px;
  grid-template-columns: minmax(0, 1fr) 22px;
  min-height: 86px;
  overflow: hidden;
  padding: 11px 12px;
  position: relative;
  text-align: left;
  transition: background 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.focus-entry::after {
  align-items: center;
  align-self: center;
  background: #f4f7ff;
  border: 1px solid rgba(51, 112, 255, 0.12);
  border-radius: 999px;
  color: #3370ff;
  content: '›';
  display: inline-flex;
  font-size: 18px;
  font-weight: 500;
  grid-column: 2;
  grid-row: 1 / span 3;
  height: 22px;
  justify-content: center;
  line-height: 1;
  transition: background 0.16s ease, border-color 0.16s ease, transform 0.16s ease;
  width: 22px;
}

.focus-entry:hover {
  background: #f8fbff;
  border-color: rgba(51, 112, 255, 0.36);
  box-shadow: 0 8px 18px rgba(51, 112, 255, 0.08);
  transform: translateY(-1px);
}

.focus-entry:hover::after {
  background: #3370ff;
  border-color: #3370ff;
  color: #ffffff;
  transform: translateX(2px);
}

.focus-entry:active {
  box-shadow: 0 3px 10px rgba(31, 35, 41, 0.04);
  transform: translateY(0);
}

.focus-entry:focus-visible {
  border-color: rgba(51, 112, 255, 0.55);
  box-shadow: 0 0 0 3px rgba(51, 112, 255, 0.12);
  outline: none;
}

.focus-entry span,
.focus-entry em {
  color: var(--fm-muted);
  font-size: 12px;
  font-style: normal;
  line-height: 1.45;
}

.focus-entry strong {
  color: var(--fm-text);
  font-size: 14px;
  font-weight: 650;
  line-height: 1.35;
}

.focus-entry span,
.focus-entry strong,
.focus-entry em {
  grid-column: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.system-posture-entry-tip) {
  border: 1px solid rgba(226, 232, 240, 0.96) !important;
  border-radius: 8px !important;
  box-shadow: 0 10px 28px rgba(31, 35, 41, 0.1) !important;
  color: #1f2329 !important;
  font-size: 12px;
  line-height: 1.55;
  max-width: 320px;
  padding: 8px 10px !important;
  white-space: normal;
  word-break: break-word;
}

.focus-block {
  border-top: 1px solid var(--fm-border-soft);
  margin-top: 8px;
  padding-top: 8px;
}

.focus-block__title {
  font-weight: 600;
  margin-bottom: 8px;
}

.compact-metric-list {
  display: grid;
  gap: 5px;
}

.compact-metric {
  align-items: center;
  background: #ffffff;
  border: 1px solid rgba(226, 232, 240, 0.78);
  border-radius: 8px;
  display: grid;
  gap: 8px;
  min-height: 34px;
  padding: 6px 8px;
}

.compact-metric {
  grid-template-columns: minmax(0, 1fr) auto auto;
}

.compact-metric strong {
  color: var(--fm-text);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.45;
  min-width: 0;
  overflow-wrap: anywhere;
}

.compact-metric.is-critical strong {
  color: #d83931;
}

.compact-metric.is-warning strong {
  color: #c26300;
}

.metric-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 12px;
}

.metric-cell {
  background: #ffffff;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 8px;
  display: grid;
  gap: 4px;
  padding: 9px 10px;
}

.metric-cell.is-critical {
  background: #fffdfc;
  border-color: rgba(245, 74, 69, 0.26);
}

.metric-cell.is-critical strong {
  color: #d83931;
}

.metric-cell.is-warning {
  background: #fffdf9;
  border-color: rgba(255, 136, 0, 0.26);
}

.metric-cell.is-warning strong {
  color: #c26300;
}

.metric-cell.is-healthy {
  background: #fbfffd;
  border-color: rgba(0, 168, 112, 0.22);
}

.metric-cell.is-healthy strong {
  color: #087a55;
}

.action-row {
  flex-wrap: wrap;
  margin-top: 12px;
}

.compact-actions {
  border-top: 1px solid var(--fm-border-soft);
  margin-top: 8px;
  padding-top: 8px;
}

.action-row :deep(.el-button) {
  border-radius: 6px;
}

.compact-actions :deep(.el-button) {
  margin-left: 0;
  background: #ffffff;
  border-color: rgba(226, 232, 240, 0.95);
  color: var(--fm-muted);
  font-weight: 500;
}

.drill-tree {
  display: grid;
  gap: 5px;
}

.drill-row {
  align-items: center;
  background: #ffffff;
  border: 1px solid rgba(226, 232, 240, 0.88);
  border-radius: 8px;
  box-sizing: border-box;
  color: inherit;
  cursor: pointer;
  display: flex;
  gap: 8px;
  min-height: 40px;
  padding: 0 14px 0 calc(12px + var(--node-indent, 0px));
  text-align: left;
  transition: background 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
  width: 100%;
}

.drill-row:hover,
.drill-row.active {
  background: #f5f8ff;
  border-color: rgba(51, 112, 255, 0.28);
  box-shadow: 0 4px 12px rgba(51, 112, 255, 0.05);
}

.drill-row strong {
  color: var(--fm-text);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drill-row em,
.node-kind {
  color: var(--fm-muted);
  font-size: 12px;
  font-style: normal;
  line-height: 1.4;
}

.node-kind {
  background: #f4f6f8;
  border-radius: 6px;
  flex: 0 0 auto;
  padding: 2px 7px;
}

.drill-row em {
  background: #f8fafc;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 999px;
  flex: 0 1 auto;
  margin-left: auto;
  max-width: 116px;
  overflow: hidden;
  padding: 2px 8px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-dot {
  background: var(--fm-subtle);
  border-radius: 999px;
  height: 7px;
  width: 7px;
}

.status-dot.is-critical {
  background: #d83931;
  box-shadow: 0 0 0 3px rgba(245, 74, 69, 0.08);
}

.status-dot.is-warning {
  background: #c26300;
  box-shadow: 0 0 0 3px rgba(255, 136, 0, 0.08);
}

.status-dot.is-healthy {
  background: #087a55;
  box-shadow: 0 0 0 3px rgba(0, 168, 112, 0.08);
}

.node-hint {
  background: #fff6f5;
  border: 1px solid rgba(245, 74, 69, 0.22);
  border-radius: 8px;
  color: #d83931;
  font-size: 13px;
  line-height: 1.5;
  padding: 10px 12px;
}

.child-node-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 12px;
}

.child-node {
  background: #ffffff;
  border: 1px solid rgba(226, 232, 240, 0.88);
  border-radius: 8px;
  color: inherit;
  cursor: pointer;
  display: grid;
  gap: 5px;
  padding: 10px;
  text-align: left;
  transition: background 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
}

.child-node:hover {
  background: #f8fbff;
  border-color: rgba(51, 112, 255, 0.24);
  box-shadow: 0 4px 12px rgba(51, 112, 255, 0.05);
}

.child-node strong {
  color: var(--fm-text);
}

.child-node em {
  color: var(--fm-muted);
  font-size: 12px;
  font-style: normal;
  line-height: 1.4;
}

.topology-chart {
  background: linear-gradient(180deg, #ffffff 0%, #f7f9fc 100%);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 8px;
  height: 390px;
  width: 100%;
}

.dependency-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.dependency-card {
  background: #ffffff;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 8px;
  padding: 12px;
}

.dependency-card.is-critical {
  background: #fffdfc;
  border-color: rgba(245, 74, 69, 0.26);
}

.dependency-card.is-warning {
  background: #fffdf9;
  border-color: rgba(255, 136, 0, 0.26);
}

.dependency-card__head strong {
  color: var(--fm-text);
  display: block;
  margin-bottom: 4px;
}

.dependency-card p {
  margin: 10px 0;
}

.dependency-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.dependency-metrics span {
  background: #f4f6f8;
  border-radius: 6px;
  padding: 4px 8px;
}

.dependency-metrics span.is-critical {
  background: #fff1f0;
  color: #d83931;
}

.dependency-metrics span.is-warning {
  background: #fff0d6;
  color: #c26300;
}

.system-card :deep(.el-tag),
.dependency-card :deep(.el-tag),
.section-head :deep(.el-tag) {
  border-radius: 6px;
  font-weight: 500;
}


.system-posture-detail-dialog :deep(.el-dialog) {
  border-radius: 8px;
  overflow: hidden;
}

.system-posture-detail-dialog :deep(.el-dialog__header) {
  border-bottom: 1px solid var(--fm-border-soft);
  margin-right: 0;
  padding: 18px 20px 14px;
}

.system-posture-detail-dialog :deep(.el-dialog__title) {
  color: var(--fm-text);
  font-size: 16px;
  font-weight: 600;
}

.system-posture-detail-dialog :deep(.el-dialog__body) {
  background: #f7f8fa;
  padding: 14px;
}





.system-posture-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.system-posture-form :deep(.el-form-item__label) {
  color: var(--fm-muted);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.2;
  margin-bottom: 7px;
}

.form-section {
  background: #ffffff;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 8px;
  margin-bottom: 12px;
  padding: 12px;
}

.form-section__head {
  align-items: center;
  display: flex;
  gap: 10px;
  justify-content: space-between;
  margin-bottom: 12px;
}

.form-section__head :deep(.el-button) {
  border-radius: 6px;
  font-weight: 500;
  min-height: 26px;
}

.form-section__head strong {
  color: var(--fm-text);
  font-size: 14px;
  font-weight: 650;
  line-height: 1.35;
}

.form-section__head span,
.readonly-row span {
  color: var(--fm-muted);
  font-size: 12px;
  line-height: 1.45;
}

.readonly-row {
  align-items: center;
  background: #f7f9fc;
  border: 1px solid rgba(226, 232, 240, 0.82);
  border-radius: 8px;
  display: flex;
  justify-content: space-between;
  min-height: 34px;
  padding: 0 10px;
}

.readonly-row--top {
  margin-bottom: 12px;
}

.readonly-row strong {
  color: var(--fm-text);
  font-size: 13px;
  font-weight: 600;
}

.system-posture-form :deep(.el-input__wrapper),
.system-posture-form :deep(.el-textarea__inner),
.system-posture-form :deep(.el-select__wrapper),
.system-posture-form :deep(.el-input-number) {
  border-radius: 6px;
}

.system-posture-form :deep(.el-input-number) {
  width: 100%;
}

.json-editor :deep(.el-textarea__inner) {
  font-family: "JetBrains Mono", "Cascadia Code", Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
}

:deep(.system-posture-help-dialog) {
  border-radius: 8px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: min(760px, 82vh);
  margin-bottom: 0;
  margin-top: 8vh !important;
  overflow: hidden;
}

:deep(.system-posture-help-dialog .el-dialog__header) {
  border-bottom: 1px solid var(--fm-border-soft);
  flex: 0 0 auto;
  margin-right: 0;
  padding: 18px 20px 14px;
}

:deep(.system-posture-help-dialog .el-dialog__body) {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  padding: 16px 20px 20px;
}

.json-help {
  color: var(--fm-muted);
  flex: 1 1 auto;
  font-size: 13px;
  line-height: 1.6;
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
}

.json-help p {
  margin: 0 0 12px;
}

.json-help pre {
  background: #f7f9fc;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 8px;
  color: #1f2329;
  margin: 0;
  overflow: visible;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.json-help code {
  font-family: "JetBrains Mono", "Cascadia Code", Consolas, monospace;
  font-size: 12px;
  line-height: 1.55;
}

.form-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.form-grid--basic {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.form-grid--slo {
  grid-template-columns: minmax(160px, 1.35fr) minmax(120px, 1fr) minmax(88px, 0.7fr) minmax(120px, 1fr);
}

.form-item-hint {
  color: var(--fm-muted);
  font-size: 12px;
  line-height: 1.5;
  margin-top: 6px;
}

.dialog-footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.dialog-footer :deep(.el-button) {
  border-radius: 6px;
}

@media (max-width: 1280px) {
  .drill-layout,
  .dependency-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 1100px) {
  .overview-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 900px) {
  .system-grid,
  .metric-grid,
  .child-node-grid,
  .focus-entry-grid,
  .form-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .overview-toolbar {
    align-items: stretch;
    flex-direction: column;
    gap: 8px;
  }

  .overview-toolbar__actions,
  .environment-group__head {
    flex-wrap: wrap;
  }

  .overview-toolbar__actions .system-posture-time-picker {
    flex: 1 1 100%;
    order: 1;
    min-width: 0;
    width: 100%;
  }

  .environment-actions {
    flex: 1 1 100%;
  }

  .hero {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
