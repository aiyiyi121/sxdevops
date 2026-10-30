<template>
  <div class="knowledge-page workbench-page-shell">
    <section class="hero panel">
      <div class="hero-copy">
        <div class="hero-title-row">
          <span class="hero-icon"><el-icon><Share /></el-icon></span>
          <h2>知识图谱</h2>
          <p class="subtitle inline-subtitle">按知识环境聚合可观测性、事件中心与容器基础设施线索，形成服务视角的关系地图。</p>
        </div>
      </div>
    </section>

    <section class="tabs-card">
      <el-tabs v-model="activeTab" class="event-like-tabs" @tab-change="handleTabChange">
        <el-tab-pane name="graph">
          <template #label>
            <span class="tab-label"><el-icon><Share /></el-icon>图谱视图</span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="config">
          <template #label>
            <span class="tab-label"><el-icon><Setting /></el-icon>图谱配置</span>
          </template>
        </el-tab-pane>
      </el-tabs>
    </section>

    <section class="panel tabs-panel workbench-fill-panel">
      <template v-if="activeTab === 'graph'">
            <section class="topology-toolbar">
              <div class="toolbar-main">
                <span class="toolbar-label">
                  <span class="toolbar-label-dot"></span>
                  图谱范围
                </span>
                <el-select v-model="filters.environment" filterable placeholder="环境（必选）" style="width: 160px" @change="handleEnvironmentChange">
                  <el-option v-for="item in graph.filters?.environments || []" :key="item" :label="envLabel(item)" :value="item" />
                </el-select>
                <el-select v-model="filters.system" clearable filterable placeholder="系统" style="width: 180px" @change="loadGraph">
                  <el-option v-for="item in graph.filters?.systems || graph.filters?.business_lines || []" :key="item" :label="item" :value="item" />
                </el-select>
                <el-select v-model="filters.service" clearable filterable placeholder="服务" style="width: 220px" @change="loadGraph">
                  <el-option v-for="item in graph.filters?.services || []" :key="item" :label="item" :value="item" />
                </el-select>
              </div>
              <div class="toolbar-actions">
                <el-button @click="resetFilters">重置筛选</el-button>
                <el-button @click="resetCanvas">重置画布</el-button>
                <el-button type="primary" :loading="loading" @click="loadGraph">
                  <el-icon><RefreshRight /></el-icon>
                  刷新图谱
                </el-button>
              </div>
            </section>

            <div class="topology-summary-row">
              <div class="topology-kpis">
                <div class="topology-kpi">
                  <span class="kpi-label">节点数</span>
                  <span class="kpi-value">{{ visibleSummary.node_count }}</span>
                </div>
                <div class="topology-kpi">
                  <span class="kpi-label">关系数</span>
                  <span class="kpi-value">{{ visibleSummary.edge_count }}</span>
                </div>
                <div class="topology-kpi">
                  <span class="kpi-label">服务对象</span>
                  <span class="kpi-value">{{ visibleSummary.service_count }}</span>
                </div>
                <div class="topology-kpi">
                  <span class="kpi-label">基础设施</span>
                  <span class="kpi-value">{{ visibleSummary.infrastructure_count }}</span>
                </div>
                <div class="topology-kpi">
                  <span class="kpi-label">中间件 / DB</span>
                  <span class="kpi-value">{{ visibleSummary.runtime_component_count }}</span>
                </div>
                <el-button class="trace-topology-button" :disabled="!traceTopologyDatasourceId" @click="openTraceTopology">
                  <el-icon><Connection /></el-icon>
                  查看服务链路拓扑
                </el-button>
              </div>
              <div class="topology-summary-actions">
                <el-button class="summary-action-button" @click="adoptionDocVisible = true">
                  <el-icon><InfoFilled /></el-icon>
                  图谱自建说明
                </el-button>
              </div>
            </div>

            <section class="graph-layout">
              <div ref="graphPanelShellRef" class="graph-panel-shell">
                <div class="graph-source-note">
                  <el-icon><InfoFilled /></el-icon>
                  <span>当前图谱环境：{{ envLabel(filters.environment) || '未选择' }}</span>
                </div>
                <div
                  ref="graphLegendRef"
                  class="graph-legend-card"
                  :class="{ dragging: legendDrag.active }"
                  :style="graphLegendStyle"
                  @mousedown.stop.prevent="startLegendDrag"
                >
                  <div class="legend-title">节点类型</div>
                  <div v-for="item in nodeCategoryStats" :key="item.kind" class="legend-row">
                    <span class="legend-dot" :style="{ background: item.color }"></span>
                    <span>{{ item.label }}</span>
                    <em>{{ item.count }}</em>
                  </div>
                  <div class="legend-divider"></div>
                  <div class="legend-title">关系类型</div>
                  <div v-for="item in visibleRelationLegend" :key="item.key" class="legend-row">
                    <span class="legend-line" :class="`is-${item.key}`"></span>
                    <span>{{ item.label }}</span>
                  </div>
                </div>
                <div
                  ref="graphPanelRef"
                  class="graph-panel"
                  :class="{ dragging: graphDrag.active }"
                  v-loading="loading"
                  element-loading-text="正在加载知识图谱关系，可能会并行获取链路追踪、K8s / Docker 线索，请稍候..."
                  @wheel.prevent="handleGraphWheel"
                  @mousedown="startGraphDrag"
                  @mousemove="handleGraphDrag"
                  @mouseup="stopGraphDrag"
                  @mouseleave="stopGraphDrag"
                  @click="handleGraphPanelClick"
                >
                  <el-empty
                    v-if="!filters.environment"
                    class="graph-empty"
                    description="请先选择环境，知识图谱会按该环境关联的可观测性、事件中心与容器基础设施线索生成。"
                  />
                <div class="graph-board-viewport" :style="{ width: `${scaledGraphWidth}px`, height: `${scaledGraphHeight}px` }">
                  <div
                    class="graph-board"
                    :style="{
                      width: `${graphChartWidth}px`,
                      height: `${graphChartHeight}px`,
                      transform: `scale(${graphZoom})`,
                    }"
                  >
                    <svg class="graph-board-edges" :width="graphChartWidth" :height="graphChartHeight">
                      <path
                        v-for="edge in boardEdges"
                        :key="edge.id"
                        :d="edge.path"
                        class="board-edge"
                        :class="[`is-${edge.relation}`, { focused: edge.focused, dimmed: edge.dimmed }]"
                      />
                    </svg>
                    <section
                      v-for="lane in swimlaneLayout.lanes"
                      :key="lane.kind"
                      class="board-lane"
                      :style="laneStyle(lane)"
                    >
                      <div class="board-lane-title" :style="laneTitleStyle(lane)">
                        <span>{{ lane.label }}</span>
                      </div>
                      <div class="board-lane-body" :style="laneBodyStyle(lane)">
                        <div class="board-lane-count">{{ lane.totalNodeCount || lane.nodes.length }} 个节点</div>
                        <button
                          v-for="node in lane.nodes"
                          :key="node.id"
                          type="button"
                          class="board-node"
                          :class="{
                            active: selectedNodeId === node.id,
                            summary: node.isSummary,
                            related: isFocusedNeighbor(node.id),
                            dimmed: isDimmedNode(node.id),
                          }"
                          :style="nodeCardStyle(node)"
                          @click="node.isSummary ? null : selectNode(node)"
                        >
                          <span class="board-node-dot" :style="{ background: palette[node.kind] || '#64748b' }"></span>
                          <span v-if="nodeTypeBadge(node)" class="board-node-type">{{ nodeTypeBadge(node) }}</span>
                          <span class="board-node-label">{{ node.label }}</span>
                        </button>
                      </div>
                    </section>
                  </div>
                </div>
                </div>
              </div>

              <aside class="side-panel">
                <template v-if="selectedNode">
                  <div class="sidebar-header">
                    <div>
                      <div class="side-title">{{ selectedNode.label }}</div>
                      <div class="side-subtitle">{{ selectedNode.category || nodeKindLabel(selectedNode.kind) }}</div>
                    </div>
                    <el-tag>{{ nodeKindLabel(selectedNode.kind) }}</el-tag>
                  </div>
                  <div class="detail-grid">
                    <div class="detail-item">
                      <span>环境</span>
                      <strong>{{ envLabel(selectedNode.environment) }}</strong>
                    </div>
                    <div class="detail-item">
                      <span>系统</span>
                      <strong>{{ selectedNode.system_name || selectedNode.business_line || '-' }}</strong>
                    </div>
                    <div class="detail-item">
                      <span>服务</span>
                      <strong>{{ selectedNode.service || '-' }}</strong>
                    </div>
                    <div class="detail-item">
                      <span>权重</span>
                      <strong>{{ selectedNode.metric || 0 }}</strong>
                    </div>
                  </div>
                  <p v-if="selectedNode.description" class="node-desc">{{ selectedNode.description }}</p>
                  <div v-if="selectedNode.details?.length" class="node-details">
                    <div class="section-title">节点信息</div>
                    <div v-for="item in selectedNode.details" :key="`${item.label}-${item.value}`" class="capability-row">
                      <span>{{ item.label }}</span>
                      <strong>{{ item.value || '-' }}</strong>
                    </div>
                  </div>
                  <div v-if="selectedRelationStats.length || selectedNeighborKindStats.length || selectedNode.capabilities?.length" class="capability-list">
                    <div class="section-title">关联能力</div>
                    <div v-for="item in selectedRelationStats" :key="`relation-${item.key}`" class="capability-row">
                      <span>{{ item.label }}</span>
                      <strong>{{ item.count }}</strong>
                    </div>
                    <div v-for="item in selectedNeighborKindStats" :key="`kind-${item.kind}`" class="capability-row is-soft">
                      <span>{{ item.label }}</span>
                      <strong>{{ item.count }}</strong>
                    </div>
                    <div v-for="item in selectedNode.capabilities || []" :key="item.name" class="capability-row">
                      <span>{{ capabilityLabel(item.name) }}</span>
                      <strong>{{ item.count }}</strong>
                    </div>
                  </div>
                  <el-button v-if="selectedNode.route" type="primary" plain @click="openNode(selectedNode)">打开关联页面</el-button>
                </template>

                <template v-else>
                  <div class="sidebar-placeholder">
                    <div class="side-title">选择节点查看详情</div>
                    <div class="side-subtitle">点击画布节点查看环境、系统、服务、数据源和跳转入口；拖动画布或滚轮缩放可查看完整拓扑。</div>
                  </div>
                  <div class="section-title">高关联服务</div>
                  <button
                    v-for="node in topServices"
                    :key="node.id"
                    type="button"
                    class="service-row"
                    @click="selectNode(node)"
                  >
                    <span>{{ node.label }}</span>
                    <em>{{ node.metric }}</em>
                  </button>
                </template>
              </aside>
            </section>
      </template>
      <AIOpsKnowledgeConfig v-else embedded />
    </section>

    <el-dialog v-model="adoptionDocVisible" title="知识图谱服务识别流程" width="720px">
      <div class="adoption-doc">
        <section>
          <h3>服务识别优先级</h3>
          <ol>
            <li><strong>链路追踪优先：</strong>如果当前图谱环境配置的 Tracing 数据源能返回服务清单，图谱以 Tracing 服务作为主服务列表。</li>
            <li><strong>容器基础设施补充：</strong>K8s / Docker 不再抢占服务来源，主要用于补充服务运行在哪个集群、命名空间、主机或容器环境，并可通过工作负载标签补充系统归属。</li>
            <li><strong>Tracing 无数据时回退：</strong>当 Tracing 没有服务清单时，才从 K8s Deployment / StatefulSet / DaemonSet 和 Docker 容器中识别服务。</li>
            <li><strong>中间件 / DB 自动识别：</strong>图谱会从 Tracing Span 的组件与 Peer、K8s / Docker 运行对象、系统态势依赖中识别 Redis、MySQL、PostgreSQL、Kafka 等运行组件，并统一放入“中间件 / DB”泳道；“服务依赖”连线只使用 Tracing Span 和 K8s ConfigMap 中的显式线索。</li>
            <li><strong>事件与可观测性补证据：</strong>事件中心、告警、日志、系统态势用于补充关联能力、业务系统归属和证据，不作为有 Tracing 时的主服务来源。</li>
          </ol>
        </section>
        <section>
          <h3>为什么这样做</h3>
          <p>Tracing 里的 service 通常代表真实发生调用的应用服务，最接近“服务视角”。K8s / Docker 看到的是运行时资源，容易包含基础组件、批处理任务、Job Pod 或工具镜像，因此更适合作为部署位置证据；但对 Redis、MySQL、PostgreSQL、Kafka 这类可判定运行组件，会单独沉淀为“中间件 / DB”节点。</p>
        </section>
        <section>
          <h3>服务所属系统</h3>
          <p>当前系统归属只从可观测性、事件中心和容器基础设施推断，不再依赖 CMDB。可用证据包括系统态势服务清单、事件中心系统、告警系统、Tracing service 标签、平台发布记录和 K8s / Docker 工作负载标签；如果同名服务已有明确系统归属，就不会再挂到“未归属系统”。</p>
          <p>如果同一个服务确实属于多个系统，图谱会保留多个明确系统下的服务节点；只有完全没有系统证据时才归入“未归属系统”。后续建议优先补充 Tracing/告警标签、事件中心系统、发布记录系统或容器基础设施 label（如 <code>app.kubernetes.io/part-of</code>、<code>business_line</code>、<code>system</code>、<code>service.namespace</code>）。</p>
        </section>
      </div>
    </el-dialog>

    <el-dialog
      v-model="traceTopologyDialogVisible"
      width="76vw"
      class="trace-topology-dialog"
      append-to-body
      destroy-on-close
      :show-close="false"
      @opened="traceTopologyDialogReady = true"
      @closed="traceTopologyDialogReady = false"
    >
      <TraceObservability
        v-if="traceTopologyDialogReady"
        embedded
        topology
        :datasource-id="traceTopologyDatasourceId"
        :service="traceTopologyService"
      />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Connection, InfoFilled, RefreshRight, Setting, Share } from '@element-plus/icons-vue'
import echarts from '@/lib/echarts'
import { themedColor } from '@/theme/palette'
import { getAIOpsKnowledgeGraph } from '@/api/modules/aiops'
import AIOpsKnowledgeConfig from './AIOpsKnowledgeConfig.vue'
import TraceObservability from './TraceObservability.vue'

const route = useRoute()
const router = useRouter()
const chartRef = ref(null)
const graphPanelRef = ref(null)
const graphPanelShellRef = ref(null)
const graphLegendRef = ref(null)
const loading = ref(false)
const graph = ref({ nodes: [], edges: [], summary: {}, filters: {}, relation_legend: [] })
const selectedNodeId = ref('')
const adoptionDocVisible = ref(false)
const traceTopologyDialogVisible = ref(false)
const traceTopologyDialogReady = ref(false)
const activeTab = ref(route.query.tab === 'config' ? 'config' : 'graph')
const filters = reactive({ environment: '', system: '', service: '' })
const DEFAULT_GRAPH_ZOOM = 0.84
const MIN_GRAPH_ZOOM = 0.5
const MAX_GRAPH_ZOOM = 1.35
const NODE_DOT_RADIUS = 24
const NODE_DOT_CENTER_OFFSET = 32
const LANE_MAX_VISIBLE_NODES = 36
const LANE_MAX_ROWS = 12
const LANE_BASE_WIDTH = 206
const LANE_COLUMN_GAP = 14
const LANE_GAP = 18
const LANE_NODE_TOP = 68
const LANE_NODE_STEP = 82
const LANE_BODY_TOP = 76
const LANE_LEFT_PADDING = 18
const hiddenNodeKinds = new Set(['environment', 'external_event'])
const graphZoom = ref(DEFAULT_GRAPH_ZOOM)
const graphDrag = reactive({ active: false, moved: false, x: 0, y: 0, scrollLeft: 0, scrollTop: 0 })
const legendPosition = reactive({ x: null, y: null })
const legendDrag = reactive({ active: false, offsetX: 0, offsetY: 0 })
let chart = null

const graphNodes = computed(() => (graph.value.nodes || []).filter(node => {
  if (hiddenNodeKinds.has(node.kind)) return false
  if (node.infra_type === 'task_resource_environment') return false
  if (String(node.id || '').startsWith('infrastructure:task_resource_env:')) return false
  return !String(node.id || '').startsWith('capability:')
}))
const graphNodeById = computed(() => new Map((graph.value.nodes || []).map(node => [node.id, node])))
const traceTopologyDatasourceId = computed(() => {
  const traceNode = (graph.value.nodes || []).find(node => String(node.id || '').startsWith('trace_ds:'))
  return traceNode ? String(traceNode.id).replace('trace_ds:', '') : ''
})
const traceTopologyService = computed(() => {
  if (filters.service) return filters.service
  if (selectedNode.value?.service) return selectedNode.value.service
  if (selectedNode.value?.kind === 'service') return selectedNode.value.label || selectedNode.value.name || ''
  return ''
})
const graphEdges = computed(() => (graph.value.edges || []).filter(edge => {
  const source = graphNodeById.value.get(edge.source)
  const target = graphNodeById.value.get(edge.target)
  if (!source || !target) return false
  const kinds = new Set([source.kind, target.kind])
  return (
    (edge.relation === 'system_service' && kinds.has('system') && kinds.has('service'))
    || edge.relation === 'service_deployment'
    || edge.relation === 'infrastructure_member'
    || edge.relation === 'service_runtime'
    || edge.relation === 'system_runtime'
  )
}))
const visibleSummary = computed(() => {
  const kindCounts = graphNodes.value.reduce((acc, node) => {
    acc[node.kind] = (acc[node.kind] || 0) + 1
    return acc
  }, {})
  return {
    node_count: graphNodes.value.length,
    edge_count: graphEdges.value.length,
    service_count: kindCounts.service || 0,
    datasource_count: kindCounts.datasource || 0,
    infrastructure_count: kindCounts.infrastructure || 0,
    runtime_component_count: kindCounts.runtime_component || 0,
  }
})
const selectedNode = computed(() => graphNodes.value.find(item => item.id === selectedNodeId.value) || null)
const graphLegendStyle = computed(() => {
  if (legendPosition.x === null || legendPosition.y === null) {
    return { top: '14px', right: '14px' }
  }
  return {
    left: `${legendPosition.x}px`,
    top: `${legendPosition.y}px`,
  }
})
const relationLegendMap = computed(() => new Map((graph.value.relation_legend || []).map(item => [item.key, item.label])))
const selectedFocus = computed(() => {
  const selectedId = selectedNodeId.value
  const nodeIds = new Set()
  const edgeIds = new Set()
  if (!selectedId) return { nodeIds, edgeIds }
  nodeIds.add(selectedId)
  graphEdges.value.forEach((edge) => {
    if (edge.source !== selectedId && edge.target !== selectedId) return
    edgeIds.add(edge.id)
    nodeIds.add(edge.source)
    nodeIds.add(edge.target)
  })
  return { nodeIds, edgeIds }
})
const selectedRelationStats = computed(() => {
  const selectedId = selectedNodeId.value
  if (!selectedId) return []
  const counter = new Map()
  graphEdges.value.forEach((edge) => {
    if (edge.source !== selectedId && edge.target !== selectedId) return
    const key = edge.relation || 'related'
    counter.set(key, (counter.get(key) || 0) + 1)
  })
  return [...counter.entries()]
    .map(([key, count]) => ({
      key,
      label: relationLegendMap.value.get(key) || edgeRelationLabel(key),
      count,
    }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, 'zh-Hans-CN'))
})
const selectedNeighborKindStats = computed(() => {
  const selectedId = selectedNodeId.value
  if (!selectedId) return []
  const neighborIds = new Set()
  graphEdges.value.forEach((edge) => {
    if (edge.source === selectedId) neighborIds.add(edge.target)
    if (edge.target === selectedId) neighborIds.add(edge.source)
  })
  const counter = new Map()
  neighborIds.forEach((nodeId) => {
    const node = graphNodeById.value.get(nodeId)
    if (!node) return
    counter.set(node.kind, (counter.get(node.kind) || 0) + 1)
  })
  return [...counter.entries()]
    .map(([kind, count]) => ({
      kind,
      label: `${nodeKindLabel(kind)}节点`,
      count,
    }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, 'zh-Hans-CN'))
})
const topServices = computed(() => graphNodes.value
  .filter(item => item.kind === 'service')
  .slice()
  .sort((left, right) => Number(right.metric || 0) - Number(left.metric || 0))
  .slice(0, 8))
const activeLaneDefinitions = computed(() => {
  const presentKinds = new Set(graphNodes.value.map(node => node.kind))
  return laneDefinitions.filter(lane => laneKinds(lane).some(kind => presentKinds.has(kind)))
})

function laneDisplayMetrics(count) {
  const visibleCount = Math.min(count, LANE_MAX_VISIBLE_NODES)
  const itemCount = Math.max(1, visibleCount + (count > visibleCount ? 1 : 0))
  const columns = Math.max(1, Math.min(3, Math.ceil(itemCount / LANE_MAX_ROWS)))
  const rows = Math.max(1, Math.ceil(itemCount / columns))
  return {
    visibleCount,
    hiddenCount: Math.max(0, count - visibleCount),
    itemCount,
    columns,
    rows,
    width: columns * LANE_BASE_WIDTH + (columns - 1) * LANE_COLUMN_GAP,
  }
}

const graphChartHeight = computed(() => {
  const nodes = graphNodes.value
  const maxLaneRows = Math.max(1, ...activeLaneDefinitions.value.map(lane => {
    const kinds = new Set(laneKinds(lane))
    const count = nodes.filter(node => kinds.has(node.kind)).length
    return laneDisplayMetrics(count).rows
  }))
  return Math.max(640, LANE_BODY_TOP + LANE_NODE_TOP + maxLaneRows * LANE_NODE_STEP + 112)
})
const graphChartWidth = computed(() => {
  const nodes = graphNodes.value
  const widths = activeLaneDefinitions.value.map((lane) => {
    const kinds = new Set(laneKinds(lane))
    const count = nodes.filter(node => kinds.has(node.kind)).length
    return laneDisplayMetrics(count).width
  })
  const laneCount = Math.max(widths.length, 1)
  const totalLaneWidth = widths.reduce((sum, width) => sum + width, 0)
  return Math.max(980, LANE_LEFT_PADDING * 2 + totalLaneWidth + Math.max(0, laneCount - 1) * LANE_GAP)
})
const scaledGraphWidth = computed(() => Math.ceil(graphChartWidth.value * graphZoom.value))
const scaledGraphHeight = computed(() => Math.ceil(graphChartHeight.value * graphZoom.value))
const swimlaneLayout = computed(() => buildSwimlaneLayout())
const boardNodeMap = computed(() => new Map(swimlaneLayout.value.nodes.map(node => [node.id, node])))
const boardEdges = computed(() => graphEdges.value
  .map((edge, index) => {
    const source = boardNodeMap.value.get(edge.source)
    const target = boardNodeMap.value.get(edge.target)
    if (!source || !target) return null
    const leftNode = source.x <= target.x ? source : target
    const rightNode = source.x <= target.x ? target : source
    const sourceX = leftNode.centerX + NODE_DOT_RADIUS
    const targetX = rightNode.centerX - NODE_DOT_RADIUS
    const sourceY = leftNode.centerY
    const targetY = rightNode.centerY
    const midX = (sourceX + targetX) / 2
    return {
      id: `${edge.source}-${edge.target}-${edge.relation || index}`,
      relation: edge.relation || 'default',
      path: `M ${sourceX} ${sourceY} C ${midX} ${sourceY}, ${midX} ${targetY}, ${targetX} ${targetY}`,
      focused: isFocusedEdge(edge.id),
      dimmed: isDimmedEdge(edge.id),
    }
  })
  .filter(Boolean))
const nodeCategoryStats = computed(() => {
  const counts = graphNodes.value.reduce((acc, node) => {
    acc[node.kind] = (acc[node.kind] || 0) + 1
    return acc
  }, {})
  return laneDefinitions
    .map((lane) => ({
      kind: lane.kind,
      label: lane.label,
      color: palette[lane.kind] || '#64748b',
      count: laneKinds(lane).reduce((sum, kind) => sum + (counts[kind] || 0), 0),
    }))
    .filter(item => item.count > 0)
})
const visibleRelationLegend = computed(() => {
  const visibleRelationKeys = new Set(boardEdges.value.map(edge => edge.relation))
  return (graph.value.relation_legend || []).filter(item => visibleRelationKeys.has(item.key))
})

const categories = [
  { name: '可观测性' },
  { name: '环境' },
  { name: '系统' },
  { name: '服务' },
  { name: '基础设施' },
  { name: '运行组件' },
  { name: '事件源' },
]

const categoryIndex = {
  environment: 1,
  logs: 0,
  tracing: 0,
  dashboard: 0,
  alert: 0,
  posture: 0,
  internal_event: 0,
  system: 2,
  service: 3,
  infrastructure: 4,
  runtime_component: 5,
  datasource: 0,
  event_source: 6,
}

const palette = {
  observability: '#0ea5e9',
  logs: '#0ea5e9',
  tracing: '#8b5cf6',
  dashboard: '#10b981',
  alert: '#ef4444',
  posture: '#14b8a6',
  internal_event: '#64748b',
  summary: '#94a3b8',
  environment: '#2563eb',
  system: '#334155',
  service: '#0f766e',
  infrastructure: '#f97316',
  runtime_component: '#0891b2',
  datasource: '#7c3aed',
  event_source: '#db2777',
}

const LANE_TINTS = [
  { fill: 'rgba(59, 130, 246, 0.13)', border: 'rgba(59, 130, 246, 0.28)' },
  { fill: 'rgba(16, 185, 129, 0.13)', border: 'rgba(16, 185, 129, 0.28)' },
  { fill: 'rgba(245, 158, 11, 0.13)', border: 'rgba(245, 158, 11, 0.28)' },
  { fill: 'rgba(236, 72, 153, 0.11)', border: 'rgba(236, 72, 153, 0.26)' },
  { fill: 'rgba(14, 165, 233, 0.13)', border: 'rgba(14, 165, 233, 0.28)' },
]
const LANE_TINT_BY_KIND = {
  service: { fill: 'rgba(245, 158, 11, 0.13)', border: 'rgba(245, 158, 11, 0.28)' },
  observability: { fill: 'rgba(16, 185, 129, 0.08)', border: 'rgba(16, 185, 129, 0.18)' },
  event_source: { fill: 'rgba(16, 185, 129, 0.08)', border: 'rgba(16, 185, 129, 0.18)' },
}

const laneDefinitions = [
  { kind: 'infrastructure', label: '基础设施' },
  { kind: 'system', label: '系统' },
  { kind: 'service', label: '服务' },
  { kind: 'runtime_component', label: '中间件 / DB' },
  { kind: 'observability', label: '可观测性', kinds: ['datasource', 'dashboard', 'logs', 'tracing', 'posture'] },
  { kind: 'alert', label: '告警' },
  { kind: 'event_source', label: '事件源' },
  { kind: 'internal_event', label: '内部事件' },
]

function envLabel(value) {
  return {
    prod: '生产',
    test: '测试',
    dev: '开发',
    staging: '预发',
    production: '生产',
    testing: '测试',
    development: '开发',
  }[value] || value || '-'
}

function capabilityLabel(value) {
  return {
    logs: '日志',
    tracing: '链路',
    dashboards: '看板',
    alerts: '告警',
    posture: '系统态势',
    internal_events: '内部事件',
    external_events: '外部事件',
  }[value] || value
}

function nodeKindLabel(value) {
  return {
    observability: '可观测性',
    logs: '日志',
    tracing: '链路',
    dashboard: '看板',
    alert: '告警',
    posture: '系统态势',
    internal_event: '内部事件',
    external_event: '外部事件',
    environment: '环境',
    system: '系统',
    service: '服务',
    infrastructure: '基础设施',
    runtime_component: '中间件 / DB',
    datasource: '数据源',
    event_source: '事件源',
  }[value] || value || '-'
}

function edgeRelationLabel(value) {
  return {
    system_service: '系统承载服务',
    service_deployment: '部署在',
    infrastructure_member: '集群包含主机',
    service_runtime: '服务依赖',
    system_runtime: '系统依赖组件',
    environment_system: '环境包含系统',
    environment_observability: '环境关联可观测性',
    environment_infrastructure: '环境运行于基础设施',
  }[value] || value || '关联'
}

function isFocusedNeighbor(nodeId) {
  return Boolean(selectedNodeId.value && nodeId !== selectedNodeId.value && selectedFocus.value.nodeIds.has(nodeId))
}

function isDimmedNode(nodeId) {
  return Boolean(selectedNodeId.value && !selectedFocus.value.nodeIds.has(nodeId))
}

function isFocusedEdge(edgeId) {
  return Boolean(selectedNodeId.value && selectedFocus.value.edgeIds.has(edgeId))
}

function isDimmedEdge(edgeId) {
  return Boolean(selectedNodeId.value && !selectedFocus.value.edgeIds.has(edgeId))
}

function laneKinds(lane) {
  return lane.kinds || [lane.kind]
}

function nodeLaneKind(node) {
  const lane = laneDefinitions.find(item => laneKinds(item).includes(node.kind))
  return lane?.kind || node.kind
}

function datasourceBadgeType(node) {
  const id = String(node.id || '')
  const category = String(node.category || '')
  if (id.startsWith('metric_ds:') || category.includes('指标')) return 'metrics'
  if (id.startsWith('log_ds:') || category.includes('日志')) return 'logs'
  if (id.startsWith('trace_ds:') || category.includes('链路')) return 'tracing'
  return ''
}

function nodeTypeBadge(node) {
  if (!['datasource', 'dashboard', 'logs', 'tracing', 'posture', 'infrastructure', 'runtime_component'].includes(node.kind)) return ''
  const category = String(node.category || '')
  if (node.kind === 'posture') return '系统态势'
  if (node.kind === 'infrastructure') {
    if (node.infra_type === 'k8s') return 'K8s'
    if (node.infra_type === 'k8s_host') return '主机'
    if (node.infra_type === 'docker') return 'Docker'
    if (node.infra_type === 'task_resource_host') return '主机'
    if (node.infra_type === 'task_resource_k8s') return 'K8s'
    if (node.infra_type === 'task_resource_environment') return ''
    return '主机'
  }
  if (node.kind === 'runtime_component') return node.runtime_type || '组件'
  if (node.kind === 'dashboard') return '看板'
  if (node.kind === 'logs' || category.includes('日志')) return '日志'
  if (node.kind === 'tracing' || category.includes('链路')) return '链路'
  const datasourceType = datasourceBadgeType(node)
  if (datasourceType === 'metrics') return '指标'
  if (datasourceType === 'logs') return '日志'
  if (datasourceType === 'tracing') return '链路'
  return '数据源'
}

function laneNodeSortWeight(node) {
  if (node.kind === 'datasource') {
    const datasourceType = datasourceBadgeType(node)
    if (datasourceType === 'metrics') return 10
    if (datasourceType === 'logs') return 20
    if (datasourceType === 'tracing') return 30
    return 40
  }
  if (node.kind === 'dashboard') return 50
  if (node.kind === 'posture') return 60
  if (node.kind === 'logs') return 70
  if (node.kind === 'tracing') return 80
  if (node.kind !== 'infrastructure') return 100
  if (node.infra_type === 'k8s') return 1
  if (node.infra_type === 'k8s_host') return 2
  if (node.infra_type === 'docker') return 3
  if (node.infra_type === 'task_resource_k8s') return 4
  if (node.infra_type === 'task_resource_host') return 5
  return 9
}

function nodeSize(node) {
  const base = node.kind === 'system' ? 50 : node.kind === 'service' ? 42 : node.kind === 'environment' ? 44 : 32
  return Math.min(base + Math.sqrt(Number(node.metric || 0)) * 3, 68)
}

function hexToRgba(hex, alpha = 1) {
  const normalized = String(hex || '#64748b').replace('#', '')
  const value = normalized.length === 3
    ? normalized.split('').map(char => char + char).join('')
    : normalized.padEnd(6, '0').slice(0, 6)
  const number = Number.parseInt(value, 16)
  const red = (number >> 16) & 255
  const green = (number >> 8) & 255
  const blue = number & 255
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
}

function getLaneTint(lane) {
  if (LANE_TINT_BY_KIND[lane.kind]) return LANE_TINT_BY_KIND[lane.kind]
  const name = lane.label || lane.kind || ''
  let hash = 0
  for (let index = 0; index < name.length; index += 1) {
    hash = (hash * 31 + name.charCodeAt(index)) >>> 0
  }
  return LANE_TINTS[hash % LANE_TINTS.length]
}

function buildSwimlaneLayout() {
  const nodes = graphNodes.value
  const lanes = activeLaneDefinitions.value
  const headerY = 22
  const bodyY = LANE_BODY_TOP
  const laneNodes = []
  let cursorX = LANE_LEFT_PADDING

  const positionedLanes = lanes.map((lane, laneIndex) => {
    const color = palette[lane.kind] || '#64748b'
    const tint = getLaneTint(lane)
    const kinds = new Set(laneKinds(lane))
    const fullLaneItems = nodes
      .filter(node => kinds.has(node.kind))
      .sort((left, right) => {
        const weightDiff = laneNodeSortWeight(left) - laneNodeSortWeight(right)
        if (weightDiff !== 0) return weightDiff
        return String(left.label || '').localeCompare(String(right.label || ''), 'zh-Hans-CN')
      })
    const metrics = laneDisplayMetrics(fullLaneItems.length)
    const hiddenCount = metrics.hiddenCount
    const visibleItems = hiddenCount
      ? fullLaneItems.slice(0, metrics.visibleCount).concat([{
        id: `lane-summary:${lane.kind}`,
        label: `还有 ${hiddenCount} 个节点`,
        kind: 'summary',
        category: lane.label,
        metric: hiddenCount,
        isSummary: true,
      }])
      : fullLaneItems
    const laneItems = visibleItems
      .map((node, index) => {
        const columnIndex = Math.floor(index / metrics.rows)
        const rowIndex = index % metrics.rows
        const cardLeft = columnIndex * (LANE_BASE_WIDTH + LANE_COLUMN_GAP) + LANE_BASE_WIDTH / 2
        const centerX = cursorX + cardLeft
        const cardY = LANE_NODE_TOP + rowIndex * LANE_NODE_STEP
        const positioned = {
          ...node,
          x: centerX,
          centerX,
          centerY: bodyY + cardY + NODE_DOT_CENTER_OFFSET,
          cardY,
          cardLeft,
          color: palette[node.kind] || color,
        }
        laneNodes.push(positioned)
        return positioned
      })
    const positionedLane = {
      ...lane,
      x: cursorX,
      y: bodyY,
      titleY: headerY,
      width: metrics.width,
      height: graphChartHeight.value - bodyY - 28,
      color,
      tint,
      index: laneIndex,
      nodes: laneItems,
      totalNodeCount: fullLaneItems.length,
      hiddenNodeCount: hiddenCount,
      columns: metrics.columns,
    }
    cursorX += metrics.width + LANE_GAP
    return positionedLane
  })

  return { lanes: positionedLanes, nodes: laneNodes }
}

function laneStyle(lane) {
  return {
    left: `${lane.x}px`,
    top: '0px',
    width: `${lane.width}px`,
    height: `${graphChartHeight.value}px`,
    '--lane-color': lane.color,
  }
}

function laneTitleStyle(lane) {
  return {
    top: `${lane.titleY}px`,
    borderColor: themedColor('rgba(59, 130, 246, 0.28)', 'border'),
    boxShadow: 'none',
  }
}

function laneBodyStyle(lane) {
  const topColor = lane.index % 2 === 0 ? 'rgba(255, 255, 255, 0.90)' : 'rgba(248, 250, 252, 0.92)'
  return {
    top: `${lane.y}px`,
    height: `${lane.height}px`,
    background: `linear-gradient(180deg, ${themedColor(topColor, 'surface')} 0%, ${themedColor(lane.tint.fill, 'surface')} 100%)`,
    borderColor: themedColor(lane.tint.border, 'border'),
    boxShadow: 'none',
  }
}

function nodeCardStyle(node) {
  return {
    top: `${node.cardY}px`,
    left: `${node.cardLeft}px`,
    '--node-color': node.color,
  }
}

function buildLaneLayout() {
  const nodes = graphNodes.value
  const lanes = activeLaneDefinitions.value
  const width = Math.max(graphChartWidth.value, chartRef.value?.clientWidth || 980)
  const height = graphChartHeight.value
  const leftPadding = 18
  const headerY = 18
  const headerHeight = 44
  const bodyY = 86
  const laneGap = 16
  const laneWidth = 206
  const nodeStep = 82
  const laneMap = new Map()
  let cursorX = leftPadding

  lanes.forEach((lane, index) => {
    const kinds = new Set(laneKinds(lane))
    const laneNodes = nodes.filter(node => kinds.has(node.kind))
    laneMap.set(lane.kind, { ...lane, index, x: cursorX, width: laneWidth, nodes: laneNodes })
    cursorX += laneWidth + laneGap
  })

  const positionedNodes = nodes.map((node) => {
    const lane = laneMap.get(nodeLaneKind(node)) || laneMap.values().next().value || { x: leftPadding, width: laneWidth, nodes: [] }
    const index = Math.max(lane.nodes.findIndex(item => item.id === node.id), 0)
    const x = lane.x + lane.width / 2
    const y = bodyY + 86 + index * nodeStep
    return { ...node, x, y }
  })

  const laneGraphics = lanes.map((lane) => {
    const item = laneMap.get(lane.kind)
    const color = palette[lane.kind] || '#64748b'
    return {
      type: 'group',
      silent: true,
      z: -10,
      children: [
        {
          type: 'rect',
          shape: { x: item.x, y: headerY, width: item.width, height: headerHeight, r: 22 },
          style: {
            fill: 'rgba(255,255,255,0.94)',
            stroke: hexToRgba(color, 0.32),
            lineWidth: 1.5,
            shadowBlur: 16,
            shadowColor: 'rgba(15,23,42,0.08)',
          },
        },
        {
          type: 'text',
          style: {
            x: item.x + item.width / 2,
            y: headerY + 28,
            text: lane.label,
            fill: '#0f172a',
            font: '800 17px sans-serif',
            align: 'center',
          },
        },
        {
          type: 'rect',
          shape: { x: item.x, y: bodyY, width: item.width, height: height - bodyY - 28, r: 20 },
          style: {
            fill: hexToRgba(color, 0.12),
            stroke: hexToRgba(color, 0.22),
            lineWidth: 1.2,
            shadowBlur: 18,
            shadowColor: hexToRgba(color, 0.12),
          },
        },
        {
          type: 'text',
          style: {
            x: item.x + item.width / 2,
            y: bodyY + (height - bodyY - 28) / 2,
            text: lane.label,
            fill: hexToRgba(color, 0.08),
            font: '900 28px sans-serif',
            align: 'center',
          },
        },
        {
          type: 'rect',
          shape: { x: item.x + 14, y: bodyY + 12, width: 72, height: 24, r: 12 },
          style: {
            fill: 'rgba(255,255,255,0.78)',
            stroke: 'rgba(255,255,255,0.68)',
          },
        },
        {
          type: 'text',
          style: {
            x: item.x + 28,
            y: bodyY + 29,
            text: `${item.nodes.length} 个节点`,
            fill: '#475569',
            font: '700 12px sans-serif',
          },
        },
      ],
    }
  })

  return { nodes: positionedNodes, graphics: laneGraphics }
}

function buildOption() {
  const { nodes, graphics } = buildLaneLayout()
  const data = nodes.map(node => ({
    id: node.id,
    name: node.label,
    value: node.metric || 0,
    category: categoryIndex[node.kind] ?? 0,
    x: node.x,
    y: node.y,
    fixed: true,
    symbolSize: nodeSize(node),
    itemStyle: {
      color: palette[node.kind] || '#64748b',
      borderColor: '#ffffff',
      borderWidth: 3,
      shadowBlur: 16,
      shadowColor: hexToRgba(palette[node.kind] || '#64748b', 0.24),
    },
    label: {
      show: true,
      formatter: '{b}',
      position: 'bottom',
      distance: 8,
      color: '#0f172a',
      backgroundColor: 'rgba(255,255,255,0.94)',
      borderColor: 'rgba(148,163,184,0.18)',
      borderWidth: 1,
      borderRadius: 10,
      padding: [5, 10],
      shadowBlur: 8,
      shadowColor: 'rgba(15,23,42,0.08)',
    },
    emphasis: {
      label: { show: true },
      itemStyle: {
        shadowBlur: 18,
        shadowColor: 'rgba(15, 23, 42, 0.22)',
      },
    },
    node,
  }))
  const links = (graph.value.edges || []).map(edge => ({
    source: edge.source,
    target: edge.target,
    value: edge.weight || 1,
    label: { show: false, formatter: edge.label },
    lineStyle: {
      width: Math.min(1 + Number(edge.weight || 1) * 0.4, 4),
      opacity: edge.relation === 'observability_link' ? 0.78 : 0.38,
      curveness: edge.relation === 'observability_link' ? 0.18 : 0.08,
      color: edge.relation === 'observability_link' ? '#0ea5e9' : '#94a3b8',
    },
    edge,
  }))

  return {
    backgroundColor: 'transparent',
    graphic: graphics,
    tooltip: {
      trigger: 'item',
      borderWidth: 0,
      backgroundColor: 'rgba(255, 255, 255, 0.98)',
      textStyle: { color: '#0f172a' },
      extraCssText: 'box-shadow:0 18px 30px rgba(15,23,42,.12);border-radius:12px;padding:10px 12px;',
      formatter: params => {
        if (params.dataType === 'edge') return `${params.data.edge.label}<br/>${params.data.source} -> ${params.data.target}`
        const node = params.data.node || {}
        return `${node.label}<br/>${node.category || node.kind}<br/>${node.description || ''}`
      },
    },
    series: [{
      type: 'graph',
      layout: 'none',
      roam: false,
      draggable: false,
      categories,
      data,
      links,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 8,
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 4 },
      },
      label: {
        color: '#0f172a',
        fontWeight: 600,
        fontSize: 12,
      },
      labelLayout: {
        hideOverlap: false,
      },
    }],
  }
}

function renderGraph() {
  if (activeTab.value !== 'graph' || !chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
    chart.on('click', params => {
      if (params.dataType === 'node') {
        selectNode(params.data.node)
      }
    })
  }
  chart.setOption(buildOption(), true)
  chart.resize()
}

async function loadGraph() {
  if (activeTab.value !== 'graph') return
  loading.value = true
  try {
    const params = {}
    if (filters.environment) params.environment = filters.environment
    if (filters.system) params.system = filters.system
    if (filters.service) params.service = filters.service
    graph.value = await getAIOpsKnowledgeGraph(params)
    if (!filters.environment && graph.value.filters?.environments?.length) {
      const defaultEnvironment = graph.value.filters.default_environment
      filters.environment = graph.value.filters.environments.includes(defaultEnvironment)
        ? defaultEnvironment
        : graph.value.filters.environments[0]
      await loadGraph()
      return
    }
    if (selectedNodeId.value && !graphNodes.value.some(item => item.id === selectedNodeId.value)) {
      selectedNodeId.value = ''
    }
    await nextTick()
    renderGraph()
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.system = ''
  filters.service = ''
  selectedNodeId.value = ''
  loadGraph()
}

function resetCanvas() {
  selectedNodeId.value = ''
  graphZoom.value = DEFAULT_GRAPH_ZOOM
  graphPanelRef.value?.scrollTo({ left: 0, top: 0, behavior: 'smooth' })
}

function setGraphZoom(nextZoom, event) {
  const panel = graphPanelRef.value
  const currentZoom = graphZoom.value
  const zoom = Math.min(MAX_GRAPH_ZOOM, Math.max(MIN_GRAPH_ZOOM, Number(nextZoom.toFixed(2))))
  if (zoom === currentZoom) return

  if (!event || !panel) {
    graphZoom.value = zoom
    return
  }

  const rect = panel.getBoundingClientRect()
  const cursorX = event.clientX - rect.left
  const cursorY = event.clientY - rect.top
  const logicalX = (panel.scrollLeft + cursorX) / currentZoom
  const logicalY = (panel.scrollTop + cursorY) / currentZoom
  graphZoom.value = zoom
  nextTick(() => {
    panel.scrollLeft = logicalX * zoom - cursorX
    panel.scrollTop = logicalY * zoom - cursorY
  })
}

function handleGraphWheel(event) {
  const delta = event.deltaY > 0 ? -0.08 : 0.08
  setGraphZoom(graphZoom.value + delta, event)
}

function startGraphDrag(event) {
  if (event.button !== 0) return
  if (event.target?.closest?.('button, a, input, textarea, .graph-legend-card, .graph-source-note')) return
  const panel = graphPanelRef.value
  if (!panel) return
  graphDrag.active = true
  graphDrag.moved = false
  graphDrag.x = event.clientX
  graphDrag.y = event.clientY
  graphDrag.scrollLeft = panel.scrollLeft
  graphDrag.scrollTop = panel.scrollTop
  event.preventDefault()
}

function handleGraphDrag(event) {
  if (!graphDrag.active) return
  const panel = graphPanelRef.value
  if (!panel) return
  const deltaX = event.clientX - graphDrag.x
  const deltaY = event.clientY - graphDrag.y
  if (Math.abs(deltaX) > 3 || Math.abs(deltaY) > 3) {
    graphDrag.moved = true
  }
  panel.scrollLeft = graphDrag.scrollLeft - deltaX
  panel.scrollTop = graphDrag.scrollTop - deltaY
}

function stopGraphDrag() {
  graphDrag.active = false
}

function clampLegendPosition(x, y) {
  const shell = graphPanelShellRef.value
  const card = graphLegendRef.value
  if (!shell || !card) return { x, y }
  const padding = 8
  const maxX = Math.max(padding, shell.clientWidth - card.offsetWidth - padding)
  const maxY = Math.max(padding, shell.clientHeight - card.offsetHeight - padding)
  return {
    x: Math.min(Math.max(padding, x), maxX),
    y: Math.min(Math.max(padding, y), maxY),
  }
}

function startLegendDrag(event) {
  if (event.button !== 0) return
  const shell = graphPanelShellRef.value
  const card = graphLegendRef.value
  if (!shell || !card) return
  const shellRect = shell.getBoundingClientRect()
  const cardRect = card.getBoundingClientRect()
  const currentX = cardRect.left - shellRect.left
  const currentY = cardRect.top - shellRect.top
  const startPosition = clampLegendPosition(currentX, currentY)
  legendPosition.x = startPosition.x
  legendPosition.y = startPosition.y
  legendDrag.active = true
  legendDrag.offsetX = event.clientX - cardRect.left
  legendDrag.offsetY = event.clientY - cardRect.top
  window.addEventListener('mousemove', handleLegendDrag)
  window.addEventListener('mouseup', stopLegendDrag)
}

function handleLegendDrag(event) {
  if (!legendDrag.active) return
  const shell = graphPanelShellRef.value
  if (!shell) return
  const shellRect = shell.getBoundingClientRect()
  const next = clampLegendPosition(
    event.clientX - shellRect.left - legendDrag.offsetX,
    event.clientY - shellRect.top - legendDrag.offsetY,
  )
  legendPosition.x = next.x
  legendPosition.y = next.y
}

function stopLegendDrag() {
  legendDrag.active = false
  window.removeEventListener('mousemove', handleLegendDrag)
  window.removeEventListener('mouseup', stopLegendDrag)
}

function handleGraphPanelClick(event) {
  if (graphDrag.moved) {
    graphDrag.moved = false
    return
  }
  if (event.target?.closest?.('.board-node, .graph-legend-card, .graph-source-note')) return
  selectedNodeId.value = ''
}

function handleEnvironmentChange() {
  filters.system = ''
  filters.service = ''
  selectedNodeId.value = ''
  loadGraph()
}

function selectNode(node) {
  selectedNodeId.value = node?.id || ''
}

function openNode(node) {
  if (!node?.route) return
  router.push(node.route)
}

function resizeGraph() {
  chart?.resize()
}

function disposeGraph() {
  chart?.dispose()
  chart = null
}

function handleTabChange(tabName) {
  const nextQuery = { ...route.query }
  if (tabName === 'config') {
    nextQuery.tab = 'config'
  } else {
    delete nextQuery.tab
  }
  router.replace({ path: '/aiops/knowledge', query: nextQuery })
  if (tabName === 'config') {
    disposeGraph()
  } else if (tabName === 'graph') {
    nextTick(() => {
      if (graph.value.nodes.length || filters.environment) {
        renderGraph()
      } else {
        loadGraph()
      }
    })
  }
}

function openTraceTopology() {
  if (!traceTopologyDatasourceId.value) return
  traceTopologyDialogReady.value = false
  traceTopologyDialogVisible.value = true
}

watch(() => graph.value.nodes.length, () => nextTick(renderGraph))

watch(
  () => route.query.tab,
  (value) => {
    const nextTab = value === 'config' ? 'config' : 'graph'
    if (activeTab.value !== nextTab) {
      activeTab.value = nextTab
      if (nextTab === 'config') {
        disposeGraph()
      } else {
        nextTick(renderGraph)
      }
    }
  },
)

onMounted(() => {
  window.addEventListener('resize', resizeGraph)
  if (activeTab.value === 'graph') loadGraph()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeGraph)
  stopLegendDrag()
  disposeGraph()
})
</script>

<style scoped>
.knowledge-page {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: #0f172a;
}

.panel {
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
  padding: 12px 14px;
}

.tabs-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tabs-card {
  display: flex;
  align-items: flex-start;
  width: 100%;
  padding: 4px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.9));
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.04);
}

.tabs-panel :deep(.el-tabs__header) {
  margin-bottom: 10px;
}

.event-like-tabs :deep(.el-tabs__header) {
  margin: 0;
}

.event-like-tabs {
  width: 100%;
}

.event-like-tabs :deep(.el-tabs__nav-wrap) {
  display: block;
  max-width: 100%;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.event-like-tabs :deep(.el-tabs__nav-wrap::after),
.event-like-tabs :deep(.el-tabs__active-bar) {
  display: none;
}

.event-like-tabs :deep(.el-tabs__content) {
  display: none;
}

.event-like-tabs :deep(.el-tabs__nav-scroll) {
  overflow: visible;
}

.event-like-tabs :deep(.el-tabs__nav) {
  display: flex;
  gap: 8px;
  border: 0;
}

.event-like-tabs :deep(.el-tabs__item) {
  min-height: 38px;
  height: 38px;
  padding: 0 20px !important;
  border-radius: 8px;
  color: #4e5969;
  font-size: 13px;
  font-weight: 700;
  line-height: 38px;
}

.event-like-tabs :deep(.el-tabs__item:hover) {
  background: rgba(51, 112, 255, 0.06);
  color: #245bdb;
}

.event-like-tabs :deep(.el-tabs__item.is-active) {
  background: #e8f0ff;
  color: #245bdb;
  box-shadow: inset 0 0 0 1px rgba(51, 112, 255, 0.08);
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.tab-label :deep(.el-icon) {
  font-size: 15px;
}

.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.hero-title-row,
.toolbar-main {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.toolbar-main {
  flex: 1 1 auto;
  min-width: 0;
}

.hero-title-row h2 {
  margin: 0;
  font-size: 23px;
  color: #0f172a;
}

.subtitle {
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.45;
}

.inline-subtitle {
  padding-left: 2px;
}

.hero-icon {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: linear-gradient(135deg, #0f766e, #2563eb);
}

.topology-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  margin-bottom: 4px;
}

.toolbar-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.toolbar-actions :deep(.el-button) {
  margin-left: 0;
}

.summary-action-button,
.trace-topology-button {
  height: 32px;
  min-width: 0;
  padding: 0 10px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  box-shadow: none;
}

.summary-action-button {
  border-color: rgba(148, 163, 184, 0.28);
  color: #475569;
  background: rgba(255, 255, 255, 0.72);
}

.summary-action-button:not(.is-disabled):hover {
  border-color: rgba(100, 116, 139, 0.36);
  color: #334155;
  background: rgba(248, 250, 252, 0.92);
}

.trace-topology-button {
  margin-left: 8px;
  border-color: rgba(51, 112, 255, 0.16);
  color: #3370ff;
  background: rgba(232, 240, 255, 0.42);
  box-shadow: 0 6px 14px rgba(36, 91, 219, 0.05);
}

.trace-topology-button:not(.is-disabled):hover {
  border-color: rgba(51, 112, 255, 0.26);
  color: #245bdb;
  background: rgba(219, 234, 254, 0.64);
  box-shadow: 0 8px 18px rgba(36, 91, 219, 0.08);
}

.trace-topology-button.is-disabled,
.trace-topology-button.is-disabled:hover {
  border-color: rgba(148, 163, 184, 0.18);
  color: #cbd5e1;
  background: rgba(248, 250, 252, 0.62);
  box-shadow: none;
}

:global(.trace-topology-dialog.el-dialog) {
  max-width: 1120px;
  border-radius: 18px;
  overflow: hidden;
}

:global(.trace-topology-dialog .el-dialog__header) {
  display: none;
}

:global(.trace-topology-dialog .el-dialog__body) {
  margin: 0;
  max-height: calc(100vh - 48px);
  overflow: hidden;
  padding: 0;
  background: #ffffff;
}

.toolbar-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 999px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(241, 245, 249, 0.96) 100%);
  color: #334155;
  font-size: 13px;
  font-weight: 600;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
}

.toolbar-label-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(180deg, #0ea5e9 0%, #14b8a6 100%);
  box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.12);
}

.topology-summary-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.topology-kpis {
  display: flex;
  gap: 8px;
  flex: 1 1 auto;
  flex-wrap: wrap;
  min-width: 0;
}

.topology-summary-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: flex-start;
  gap: 8px;
  white-space: nowrap;
}

.topology-kpi {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 5px 11px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}

.kpi-label {
  color: #64748b;
  font-size: 12px;
  line-height: 1;
  white-space: nowrap;
}

.kpi-value {
  color: #0f172a;
  font-size: 17px;
  font-weight: 700;
  line-height: 1;
}

.graph-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 248px;
  gap: 10px;
  flex: 1;
  min-height: 360px;
}

.graph-panel-shell {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.graph-panel,
.side-panel {
  position: relative;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 22px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  overflow: hidden;
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.10);
}

.graph-panel {
  flex: 1;
  min-height: 360px;
  contain: size;
  overflow: auto;
  cursor: grab;
  background:
    linear-gradient(rgba(148, 163, 184, 0.07) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.07) 1px, transparent 1px),
    linear-gradient(rgba(59, 130, 246, 0.10) 1px, transparent 1px),
    linear-gradient(90deg, rgba(59, 130, 246, 0.10) 1px, transparent 1px),
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.08), transparent 28%),
    radial-gradient(circle at bottom right, rgba(16, 185, 129, 0.08), transparent 30%),
    linear-gradient(180deg, #f8fbff 0%, #f1f7fd 100%);
  background-size: 22px 22px, 22px 22px, 88px 88px, 88px 88px, auto, auto, auto;
  scrollbar-width: thin;
}

.graph-panel.dragging {
  cursor: grabbing;
  user-select: none;
}

.graph-panel::before {
  display: none;
}

.graph-panel :deep(.el-loading-mask) {
  border-radius: 20px;
  background: rgba(248, 250, 252, 0.72);
}

.graph-chart {
  min-width: 100%;
  height: 640px;
}

.graph-board-viewport {
  position: relative;
  min-width: 100%;
  overflow: hidden;
}

.graph-board {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
}

.graph-board-edges {
  position: absolute;
  inset: 0;
  z-index: 3;
  pointer-events: none;
}

.board-edge {
  fill: none;
  stroke: rgba(139, 92, 246, 0.34);
  stroke-width: 1.5;
  stroke-linecap: round;
  transition: opacity 0.16s ease, stroke-width 0.16s ease, stroke 0.16s ease;
}

.board-edge.focused {
  opacity: 0.96;
  stroke-width: 2.8;
}

.board-edge.dimmed {
  opacity: 0.08;
  stroke-width: 1;
}

.board-edge.is-system_service {
  stroke: rgba(139, 92, 246, 0.36);
}

.board-edge.is-environment_system {
  stroke: rgba(37, 99, 235, 0.42);
}

.board-edge.is-observability_link {
  stroke: rgba(14, 165, 233, 0.86);
  stroke-dasharray: none;
  stroke-width: 2.8;
}

.board-edge.is-environment_infrastructure {
  stroke: rgba(249, 115, 22, 0.72);
  stroke-width: 2.4;
}

.board-edge.is-service_runtime,
.board-edge.is-system_runtime {
  stroke: rgba(8, 145, 178, 0.42);
  stroke-width: 1.45;
}

.board-edge.is-service_deployment {
  stroke: rgba(34, 197, 94, 0.34);
  stroke-width: 1.35;
}

.board-edge.is-infrastructure_member {
  stroke: rgba(245, 158, 11, 0.58);
  stroke-width: 1.8;
  stroke-dasharray: 8 6;
}

.board-edge.is-event_context {
  stroke: rgba(249, 115, 22, 0.68);
  stroke-dasharray: 11 8;
}

.board-edge.focused {
  opacity: 0.96;
  stroke-width: 2.8;
}

.board-edge.dimmed {
  opacity: 0.08;
  stroke-width: 1;
}

.board-lane {
  position: absolute;
  z-index: 2;
}

.board-lane-title {
  position: absolute;
  left: 0;
  right: 0;
  z-index: 7;
  height: 34px;
  border: 1px solid rgba(59, 130, 246, 0.28);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.98);
  color: #0f172a;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 600;
}

.board-lane-title::before {
  display: none;
}

.board-lane-body {
  position: absolute;
  left: 0;
  right: 0;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 18px;
  overflow: hidden;
}

.board-lane-body::after {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.28) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.28) 1px, transparent 1px);
  background-size: 28px 28px;
  pointer-events: none;
}

.board-lane-body::before {
  display: none;
}

.board-lane-count {
  position: absolute;
  top: 14px;
  left: 16px;
  z-index: 5;
  padding: 3px 9px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.90);
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.board-node {
  position: absolute;
  left: 50%;
  z-index: 6;
  width: 156px;
  min-height: 78px;
  padding: 8px 10px 9px;
  border: 0;
  background: transparent;
  color: #0f172a;
  transform: translateX(-50%);
  cursor: pointer;
  font: inherit;
  transition: filter 0.16s ease, opacity 0.16s ease, transform 0.16s ease;
}

.board-node-dot {
  width: 48px;
  height: 48px;
  margin: 0 auto 10px;
  border: 2px solid rgba(255, 255, 255, 0.98);
  border-radius: 50%;
  display: block;
  position: relative;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.12);
}

.board-node-dot::before {
  content: "";
  position: absolute;
  inset: -22px;
  z-index: -1;
  border-radius: 50%;
  background: radial-gradient(
    circle,
    color-mix(in srgb, var(--node-color) 18%, transparent) 0%,
    color-mix(in srgb, var(--node-color) 10%, transparent) 36%,
    transparent 70%
  );
  pointer-events: none;
}

.board-node-type {
  position: absolute;
  top: 46px;
  left: 50%;
  z-index: 2;
  padding: 1px 6px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.96);
  color: #475569;
  font-size: 10px;
  font-weight: 600;
  line-height: 1.35;
  transform: translateX(-50%);
  pointer-events: none;
}

.board-node-label {
  max-width: 148px;
  margin: 0 auto;
  padding: 5px 10px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.98);
  display: block;
  overflow: hidden;
  color: #0f172a;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
  box-shadow: none;
}

.board-node:hover,
.board-node.active {
  z-index: 12;
  filter: saturate(1.08);
}

.board-node.related {
  z-index: 9;
}

.board-node.dimmed {
  opacity: 0.22;
  filter: grayscale(0.75) saturate(0.68);
}

.board-node.summary {
  cursor: default;
  pointer-events: none;
}

.board-node.summary .board-node-dot {
  width: 38px;
  height: 38px;
  opacity: 0.7;
}

.board-node.summary .board-node-label {
  border-style: dashed;
  color: #64748b;
  font-weight: 700;
}

.board-node:hover .board-node-dot,
.board-node.active .board-node-dot {
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.98), 0 0 0 5px color-mix(in srgb, var(--node-color) 18%, transparent);
}

.board-node:hover .board-node-dot::before,
.board-node.active .board-node-dot::before {
  background: radial-gradient(
    circle,
    color-mix(in srgb, var(--node-color) 24%, transparent) 0%,
    color-mix(in srgb, var(--node-color) 13%, transparent) 38%,
    transparent 72%
  );
}

.board-node.active .board-node-label {
  border-color: color-mix(in srgb, var(--node-color) 38%, rgba(148, 163, 184, 0.24));
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.15);
}

.board-node.related .board-node-label {
  border-color: color-mix(in srgb, var(--node-color) 26%, rgba(148, 163, 184, 0.24));
}

.graph-empty {
  position: absolute;
  inset: 0;
  z-index: 8;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(248, 250, 252, 0.76);
}

.graph-source-note {
  position: absolute;
  bottom: 14px;
  left: 14px;
  z-index: 9;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.96);
  color: #0f172a;
  font-size: 11px;
  box-shadow: 0 14px 30px rgba(15, 23, 42, 0.10);
}

.graph-legend-card {
  position: absolute;
  top: 14px;
  right: 14px;
  z-index: 9;
  min-width: 118px;
  max-width: 138px;
  padding: 9px 10px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.97);
  color: #334155;
  box-shadow: 0 16px 34px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(8px);
  cursor: grab;
  user-select: none;
  touch-action: none;
}

.graph-legend-card.dragging {
  cursor: grabbing;
  box-shadow: 0 20px 42px rgba(15, 23, 42, 0.18);
}

.side-panel {
  min-width: 0;
  padding: 15px;
  color: #0f172a;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.sidebar-placeholder {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.side-title {
  color: #0f172a;
  font-size: 16px;
  font-weight: 700;
}

.side-subtitle,
.node-desc {
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.detail-item,
.capability-row,
.service-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 11px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.95);
}

.detail-item {
  flex-direction: column;
  align-items: flex-start;
}

.detail-item span,
.section-title {
  color: #64748b;
  font-size: 11px;
}

.detail-item strong,
.capability-row strong {
  color: #0f172a;
  font-size: 12px;
}

.capability-row.is-soft {
  background: rgba(248, 250, 252, 0.92);
}

.section-title {
  margin: 12px 0 7px;
  font-weight: 700;
}

.legend-title {
  margin-bottom: 6px;
  color: #0f172a;
  font-size: 11px;
  font-weight: 700;
}

.legend-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
  margin-bottom: 5px;
  color: #475569;
  font-size: 11px;
}

.adoption-doc {
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: #334155;
  font-size: 13px;
  line-height: 1.7;
}

.adoption-doc h3 {
  margin: 0 0 8px;
  color: #0f172a;
  font-size: 15px;
}

.adoption-doc p,
.adoption-doc ol {
  margin: 0;
}

.adoption-doc ol {
  padding-left: 20px;
}

.adoption-doc li + li {
  margin-top: 6px;
}

.adoption-doc code {
  padding: 1px 5px;
  border-radius: 6px;
  background: #f1f5f9;
  color: #0f766e;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.legend-line {
  display: inline-block;
  width: 22px;
  border-top: 2px solid #94a3b8;
}

.legend-line.is-system_service {
  border-color: #8b5cf6;
}

.legend-line.is-environment_system {
  border-color: #2563eb;
}

.legend-line.is-observability_link {
  border-color: #0ea5e9;
}

.legend-line.is-environment_infrastructure {
  border-color: #f97316;
}

.legend-line.is-service_runtime,
.legend-line.is-system_runtime {
  border-color: rgba(8, 145, 178, 0.58);
}

.legend-line.is-service_deployment {
  border-color: rgba(34, 197, 94, 0.46);
}

.legend-line.is-infrastructure_member {
  border-color: #f59e0b;
  border-top-style: dashed;
}

.legend-line.is-event_context {
  border-color: #f97316;
  border-top-style: dashed;
}

.legend-divider {
  height: 1px;
  margin: 8px 0;
  background: rgba(148, 163, 184, 0.2);
}

.legend-row em {
  color: #64748b;
  font-size: 10px;
  font-style: normal;
}

.service-row {
  width: 100%;
  margin-bottom: 8px;
  color: #0f172a;
  cursor: pointer;
  text-align: left;
  font: inherit;
  transition: border-color 0.16s ease, transform 0.16s ease, box-shadow 0.16s ease;
}

.service-row:hover {
  transform: translateY(-1px);
  border-color: rgba(14, 165, 233, 0.28);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}

.service-row span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.service-row em {
  color: #64748b;
  font-size: 11px;
  font-style: normal;
}

@media (max-width: 1100px) {
  .topology-toolbar {
    grid-template-columns: 1fr;
  }

  .toolbar-actions {
    flex-wrap: wrap;
  }

  .topology-summary-row {
    flex-direction: column;
  }

  .topology-summary-actions {
    flex-wrap: wrap;
  }

  .graph-layout {
    grid-template-columns: 1fr;
  }

  .graph-chart {
    height: 520px;
  }

  .graph-panel {
    min-height: 520px;
  }
}

@media (max-width: 720px) {
  .graph-legend-card,
  .graph-source-note {
    position: static;
    margin: 10px 10px 0;
    transform: none;
  }

  .graph-chart {
    height: 480px;
  }
}
</style>
