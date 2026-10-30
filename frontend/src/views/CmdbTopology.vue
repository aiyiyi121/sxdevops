<template>
  <div class="fade-in cmdb-model-topology-page workbench-page-shell">
    <section class="hero panel">
      <div class="hero-title-row">
        <span class="hero-icon"><el-icon><Share /></el-icon></span>
        <h2>资产拓扑</h2>
        <p class="page-inline-desc">按业务环境或云账号筛选资产分类，查看分类之间的关系规则。</p>
      </div>
    </section>

    <div class="workbench-card cmdb-model-topology-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">资产拓扑关系</span>
          <span class="toolbar-desc">按业务环境或云账号筛选资产分类，查看分类间的关系规则。</span>
        </div>
        <div class="workbench-card-actions">
          <el-tag size="small" type="info" :title="selectedScope?.path || '全部资产'">{{ selectedScope?.label || '全部资产' }} · {{ visibleModels.length }} 个分类</el-tag>
          <el-tag size="small" type="info">{{ visibleRules.length }} 条规则</el-tag>
          <el-button :loading="loading" @click="loadModelTopology">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <div class="asset-topology-workspace">
        <aside class="asset-scope-panel ledger-resource-tree-panel" aria-label="资产树">
          <div class="neo-tabs theme-blue ledger-perspective-tabs" role="group" aria-label="资产树维度">
            <button v-for="mode in scopeModes" :key="mode.key" type="button" class="neo-tab-btn" :class="{ active: scopeMode === mode.key }" :aria-pressed="scopeMode === mode.key" @click="changeScopeMode(mode.key)">
              <el-icon><component :is="mode.icon" /></el-icon><span>{{ mode.label }}</span>
            </button>
          </div>
          <div class="asset-scope-heading">{{ scopeMode === 'business' ? '业务环境维度' : '云账号维度' }}</div>
          <template v-if="canViewCi">
            <el-input v-model="scopeKeyword" clearable :prefix-icon="Search" :placeholder="scopeMode === 'business' ? '搜索业务线 / 资产名' : '搜索云账号 / 资产名'" aria-label="搜索资产树" />
            <div v-if="scopeLoadError" class="asset-scope-message" role="alert">资产树加载失败，请点击刷新重试。</div>
            <div v-else v-loading="loading" class="asset-scope-body">
              <button type="button" class="asset-scope-all" :class="{ active: !selectedScopeKey }" @click="clearScope">
                <span><el-icon><FolderOpened /></el-icon>全部资产</span><em>{{ scopeRows.length }}</em>
              </button>
              <el-tree ref="scopeTreeRef" :data="scopeTreeNodes" node-key="key" :default-expanded-keys="scopeTreeNodes.map(node => node.key)" :expand-on-click-node="false" :filter-node-method="filterScopeNode" highlight-current @node-click="selectScope">
                <template #default="{ data }">
                  <span class="asset-scope-node" :title="data.path"><span>{{ data.label }}</span><em>{{ data.count }}</em></span>
                </template>
              </el-tree>
              <el-empty v-if="!loading && !scopeTreeNodes.length" description="暂无资产树节点" :image-size="52" />
            </div>
          </template>
          <el-empty v-else description="当前账号无资产查看权限" :image-size="52" />
        </aside>

        <div class="asset-topology-main">
          <div class="workbench-toolbar workbench-toolbar--history cmdb-model-topology-toolbar">
            <div class="topology-filter-main">
              <span class="topology-filter-label">
                <span class="topology-filter-dot"></span>
                筛选条件
              </span>
              <el-select v-model="filters.group" clearable filterable placeholder="资产分类分组" style="width: 168px" @change="renderGraph">
                <el-option v-for="item in groupOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-select v-model="filters.relation_type" clearable filterable placeholder="关系类型" style="width: 140px" @change="renderGraph">
                <el-option v-for="item in relationTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-select v-model="filters.status" placeholder="规则状态" style="width: 128px" @change="renderGraph">
                <el-option label="启用规则" value="active" />
                <el-option label="全部规则" value="all" />
                <el-option label="停用规则" value="inactive" />
              </el-select>
              <el-input
                v-model="filters.keyword"
                clearable
                placeholder="搜索分类 / 编码 / 关系"
                style="width: 240px"
                @input="renderGraph"
              />
            </div>
            <div class="topology-filter-actions">
              <el-button @click="resetFilters">重置</el-button>
            </div>
          </div>

          <div class="cmdb-model-topology-layout">
            <section class="model-graph-panel">
              <div class="model-graph-board-shell">
                <div class="graph-legend-card">
                  <div class="legend-title">关系图例</div>
                  <div v-for="item in relationTypeStats" :key="item.key" class="legend-row">
                    <span class="legend-line" :style="relationLegendStyle(item.key)"></span>
                    <span>{{ item.label }}</span>
                    <em>{{ item.count }}</em>
                  </div>
                  <span v-if="!relationTypeStats.length" class="model-muted">暂无关系规则</span>
                </div>

                <div
                  ref="graphPanelRef"
                  v-loading="loading"
                  class="model-graph-canvas"
                  :class="{ dragging: graphDrag.active }"
                  @wheel.prevent="handleGraphWheel"
                  @mousedown="startGraphDrag"
                  @mousemove="handleGraphDrag"
                  @mouseup="stopGraphDrag"
                  @mouseleave="stopGraphDrag"
                  @click="handleGraphPanelClick"
                >
                  <el-empty
                    v-if="!loading && !visibleModels.length"
                    class="model-graph-empty"
                    :description="scopeLoadError ? '资产树加载失败，请刷新重试' : selectedScope ? '当前范围暂无匹配的资产分类' : '暂无匹配的资产分类'"
                    :image-size="88"
                  />
                  <div
                    v-else
                    class="topology-board-viewport"
                    :style="{ width: `${scaledTopologyBoardSize.width}px`, height: `${scaledTopologyBoardSize.height}px` }"
                  >
                  <div
                    class="topology-board"
                    :style="{ width: `${topologyBoardSize.width}px`, height: `${topologyBoardSize.height}px`, transform: `scale(${graphZoom})` }"
                  >
                    <svg class="model-board-edges" :width="topologyBoardSize.width" :height="topologyBoardSize.height">
                      <defs>
                        <marker id="asset-topology-arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
                          <path d="M0,0 L0,6 L8,3 z" fill="context-stroke" />
                        </marker>
                      </defs>
                      <path
                        v-for="edge in topologyBoardEdges"
                        :key="edge.id"
                        :d="edge.path"
                        class="model-board-edge"
                        :class="{ focused: edge.focused, dimmed: edge.dimmed, required: edge.required, inactive: edge.inactive }"
                        :style="{ stroke: edge.color, strokeDasharray: edge.dash }"
                        marker-end="url(#asset-topology-arrow)"
                      />
                    </svg>

                    <section
                      v-for="lane in topologyBoardLanes"
                      :key="lane.key"
                      class="model-board-lane"
                      :style="topologyLaneStyle(lane)"
                    >
                      <button
                        type="button"
                        class="board-lane-title"
                        :class="{ active: filters.group === lane.key }"
                        :style="{ '--lane-color': lane.color }"
                        @click="applyGroupFilter(lane.key)"
                      >
                        <span>{{ lane.label }}</span>
                      </button>
                      <div class="board-lane-body" :style="{ '--lane-color': lane.color }">
                        <div class="board-lane-count">{{ lane.models.length }} 个分类</div>
                      </div>
                      <button
                        v-for="node in lane.nodes"
                        :key="node.id"
                        type="button"
                        class="board-node"
                        :class="{ active: selectedModelId === node.id, related: isRelatedModel(node.id), dimmed: isDimmedModel(node.id) }"
                        :style="topologyNodeStyle(node)"
                        @click.stop="selectModel(node.id)"
                      >
                        <span class="board-node-dot" :style="{ background: node.color }"></span>
                        <span class="board-node-type">{{ nodeResourceCountText(node) }}</span>
                        <span class="board-node-label">{{ node.name }}</span>
                      </button>
                    </section>
                  </div>
                  </div>
                </div>
              </div>
            </section>

            <aside class="model-side-panel side-panel">
              <template v-if="selectedModel">
                <div class="model-side-header">
                  <div>
                    <div class="model-side-title">{{ selectedModel.name }}</div>
                    <div class="model-side-subtitle">{{ selectedModel.code || '-' }} / {{ selectedModel.group_name || '未分组' }}</div>
                  </div>
                  <el-tag size="small" :type="selectedModel.is_active === false ? 'warning' : 'success'">
                    {{ selectedModel.is_active === false ? '停用' : '启用' }}
                  </el-tag>
                </div>

                <div class="model-detail-grid">
                  <div v-for="item in selectedModelStats" :key="item.label" class="model-detail-item">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                  </div>
                </div>

                <div class="model-section">
                  <div class="model-section-head">
                    <strong>关联规则</strong>
                    <el-tag size="small" type="info">{{ selectedRules.length }}</el-tag>
                  </div>
                  <div class="model-rule-list">
                    <button
                      v-for="rule in selectedRules"
                      :key="rule.id"
                      type="button"
                      class="model-rule-row"
                      @click="selectModel(rule.otherModelId)"
                    >
                      <span class="model-rule-main">
                        <strong>{{ rule.otherModelName }}</strong>
                        <small>{{ relationTypeLabel(rule.relation_type) }} / {{ rule.directionLabel }}</small>
                      </span>
                      <el-tag size="small" :type="rule.required ? 'danger' : 'info'">{{ rule.required ? '必填' : '可选' }}</el-tag>
                    </button>
                    <el-empty v-if="!selectedRules.length" description="暂无关联规则" :image-size="56" />
                  </div>
                </div>

                <div class="model-section">
                  <div class="model-section-head">
                    <strong>说明</strong>
                  </div>
                  <p class="model-description">{{ selectedModel.description || '暂无说明' }}</p>
                </div>
              </template>

              <template v-else>
                <div class="sidebar-placeholder model-side-empty">
                  <div class="model-side-title">关系概览</div>
                  <div class="model-side-subtitle">点击分类节点查看上下游规则。连线表示分类关系规则，资源数量随左侧资产范围更新。</div>
                </div>
                <div class="model-section high-connected-section">
                  <div class="section-title">高关联分类</div>
                  <div class="high-connected-grid">
                    <button
                      v-for="model in topConnectedModels"
                      :key="model.id"
                      type="button"
                      class="service-row"
                      :title="model.name || model.code || '未命名分类'"
                      @click="selectModel(model.id)"
                    >
                      <span>{{ model.name || model.code || '未命名分类' }}</span>
                      <em>{{ modelDegree(model.id) }}</em>
                    </button>
                  </div>
                  <el-empty v-if="!topConnectedModels.length" description="暂无高关联分类" :image-size="56" />
                </div>
              </template>

              <div class="model-section">
                <div class="model-section-head">
                  <strong>关系类型</strong>
                </div>
                <div class="model-tag-row">
                  <el-tag v-for="item in relationTypeStats" :key="item.key" size="small" :type="item.tone">
                    {{ item.label }} {{ item.count }}
                  </el-tag>
                  <span v-if="!relationTypeStats.length" class="model-muted">暂无关系规则</span>
                </div>
              </div>

              <div class="model-section">
                <div class="model-section-head">
                  <strong>资产分组</strong>
                </div>
                <div class="model-tag-row">
                  <el-tag v-for="item in groupStats" :key="item.key" size="small" type="info">
                    {{ item.label }} {{ item.count }}
                  </el-tag>
                </div>
              </div>
            </aside>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { FolderOpened, MostlyCloudy, RefreshRight, Search, Share } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { getCIModelGroups, getCIRelationRules, getCITypes, getConfigItemLedgerTree, getResourceNodeTree } from '@/api/modules/cmdb'
import { buildCmdbAssetScopeTrees, indexAssetsByModel } from '@/utils/cmdb-asset-scope'
import { resolveThemeColor } from '@/theme'

const authStore = useAuthStore()
const loading = ref(false)
const ciTypes = ref([])
const modelGroups = ref([])
const relationRules = ref([])
const assetRows = ref([])
const resourceTrees = ref({ business: [], cloud: [] })
const scopeMode = ref('business')
const scopeModes = [{ key: 'business', label: '业务环境维度', icon: FolderOpened }, { key: 'cloud', label: '云账号维度', icon: MostlyCloudy }]
const scopeKeyword = ref('')
const selectedScopeKey = ref('')
const scopeTreeRef = ref(null)
const scopeReady = ref(false)
const scopeLoadError = ref(false)
const selectedModelId = ref('')
const graphPanelRef = ref(null)
const graphZoom = ref(0.68)
const graphDrag = reactive({ active: false, moved: false, x: 0, y: 0, scrollLeft: 0, scrollTop: 0 })
const filters = reactive({
  group: '',
  relation_type: '',
  status: 'active',
  keyword: '',
})
const LANE_WIDTH = 206
const LANE_GAP = 16
const LANE_LEFT = 20
const LANE_TOP = 18
const LANE_TITLE_HEIGHT = 34
const LANE_BODY_TOP = 54
const LANE_NODE_TOP = 86
const LANE_NODE_STEP = 88
const LANE_MIN_HEIGHT = 560
const NODE_DOT_CENTER_OFFSET = 32
const MIN_GRAPH_ZOOM = 0.56
const MAX_GRAPH_ZOOM = 1.18

const standardTopologyGroups = [
  { key: 'business', code: 'business', label: '业务模型', color: '#245bdb', sort: 10, keywords: ['APP_SERVICE', 'APPLICATION', '应用', '业务', '系统', '服务'] },
  { key: 'compute', code: 'compute', label: '计算资源', color: '#0ea5e9', sort: 20, keywords: ['CLOUD_SERVER', 'ECS', 'VIRTUAL_MACHINE', 'IDC_SERVER', 'PHYSICAL', 'K8S', 'KUBERNETES', 'DOCKER', 'VSPHERE', 'ESXI', '云主机', '虚拟机', '机房', '物理机', '宿主机', '容器', '集群'] },
  { key: 'database', code: 'database', label: '数据库', color: '#f97316', sort: 30, keywords: ['MYSQL', 'POSTGRESQL', 'POSTGRES', 'MONGODB', 'MONGO', 'DATABASE', 'DB', 'RDS', '数据库', '文档数据库'] },
  { key: 'middleware', code: 'middleware', label: '中间件', color: '#8b5cf6', sort: 40, keywords: ['REDIS', 'TAIR', 'KAFKA', 'ROCKETMQ', 'RABBITMQ', 'EMQX', 'ELASTICSEARCH', 'NACOS', 'ZOOKEEPER', 'MQ', 'QUEUE', 'CACHE', '缓存', '消息', '搜索', '注册', '配置中心', '中间件'] },
  { key: 'storage', code: 'storage', label: '存储', color: '#14b8a6', sort: 50, keywords: ['OBJECT_STORAGE', 'BLOCK_STORAGE', 'FILE_STORAGE', 'OSS', 'COS', 'S3', 'NAS', 'VOLUME', 'DISK', '对象存储', '块存储', '文件存储', '存储桶', '云盘'] },
  { key: 'bigdata', code: 'bigdata', label: '大数据', color: '#eab308', sort: 60, keywords: ['HADOOP', 'FLINK', 'CLICKHOUSE', 'HOLOGRES', 'MAXCOMPUTE', 'DATAWORKS', 'STARROCKS', '大数据', '数仓', 'OLAP'] },
  { key: 'network', code: 'network', label: '网络与入口', color: '#10b981', sort: 70, keywords: ['LOAD_BALANCER', 'SLB', 'CLB', 'NAT', 'EIP', 'SECURITY', 'FIREWALL', 'NGINX', 'DOMAIN', 'CERTIFICATE', '网关', '负载均衡', '弹性 IP', '安全组', '防火墙', '域名', '证书', '网络', '入口'] },
  { key: 'external', code: 'external', label: '第三方服务', color: '#64748b', sort: 80, keywords: ['THIRD_PARTY', 'EXTERNAL', 'SAAS', 'API', '第三方', '外部服务', '服务商'] },
]
const standardTopologyGroupCodes = new Set(standardTopologyGroups.map(group => group.code))
const hiddenModelCodes = new Set(['MIDDLEWARE', 'CLOUD_DATABASE', 'VSPHERE_CAPACITY', 'SPARK', 'HIVE', 'HBASE', 'DORIS'])

const canViewCi = computed(() => authStore.hasPermission('cmdb.ci.view'))

const listOf = (payload) => {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.results)) return payload.results
  if (Array.isArray(payload?.data)) return payload.data
  if (Array.isArray(payload?.data?.results)) return payload.data.results
  return []
}

const visibleBaseModels = computed(() => ciTypes.value.filter((model) => {
  if (hiddenModelCodes.has(String(model.code || '').toUpperCase())) return false
  const name = String(model.name || '').trim()
  return !['机房服务器', '物理机', '云数据库', 'Docker环境', 'vSphere资源统计', '数据仓库', 'Spark', 'Hive', 'HBase', 'Doris'].includes(name)
}))
const assetModelIndex = computed(() => indexAssetsByModel(assetRows.value, visibleBaseModels.value))
const scopeRows = computed(() => assetRows.value.filter(row => assetModelIndex.value.has(String(row.id))))
const scopeTrees = computed(() => buildCmdbAssetScopeTrees(scopeRows.value, resourceTrees.value))
const scopeTreeNodes = computed(() => scopeTrees.value[scopeMode.value])
const scopeNodeIndex = computed(() => {
  const result = new Map()
  const visit = nodes => nodes.forEach(node => { result.set(node.key, node); visit(node.children) })
  visit(scopeTreeNodes.value)
  return result
})
const selectedScope = computed(() => scopeNodeIndex.value.get(selectedScopeKey.value))
const scopedModelCounts = computed(() => {
  const result = new Map()
  for (const row of scopeRows.value) {
    if (selectedScopeKey.value && !selectedScope.value?.rowIds.has(String(row.id))) continue
    const modelId = assetModelIndex.value.get(String(row.id))
    result.set(modelId, (result.get(modelId) || 0) + 1)
  }
  return result
})
const scopeModels = computed(() => {
  if (!canViewCi.value) return visibleBaseModels.value
  if (!scopeReady.value) return []
  return visibleBaseModels.value
    .map(model => ({ ...model, ci_count: scopedModelCounts.value.get(String(model.id)) || 0 }))
    .filter(model => !selectedScopeKey.value || model.ci_count > 0)
})
const modelMap = computed(() => new Map(scopeModels.value.map(model => [String(model.id), model])))
const visibleRules = computed(() => {
  const keyword = normalizedKeyword.value
  return relationRules.value.filter((rule) => {
    const sourceId = String(rule.source_type)
    const targetId = String(rule.target_type)
    const source = modelMap.value.get(sourceId)
    const target = modelMap.value.get(targetId)
    if (!source || !target) return false
    if (filters.status === 'active' && rule.is_active === false) return false
    if (filters.status === 'inactive' && rule.is_active !== false) return false
    if (filters.group) {
      const inGroup = modelGroupKey(source) === filters.group || modelGroupKey(target) === filters.group
      if (!inGroup) return false
    }
    if (filters.relation_type && normalizedRelationType(rule.relation_type) !== filters.relation_type) return false
    if (!keyword) return true
    return [
      source.name,
      source.code,
      source.group_name,
      target.name,
      target.code,
      target.group_name,
      relationTypeLabel(rule.relation_type),
      rule.description,
    ].some(value => String(value || '').toLowerCase().includes(keyword))
  })
})
const visibleModelIds = computed(() => {
  const ids = new Set()
  visibleRules.value.forEach((rule) => {
    ids.add(String(rule.source_type))
    ids.add(String(rule.target_type))
  })
  if (filters.relation_type) return ids
  scopeModels.value.forEach(model => {
    if (filters.group && modelGroupKey(model) !== filters.group) return
    if (normalizedKeyword.value && ![model.name, model.code, model.group_name].some(value => String(value || '').toLowerCase().includes(normalizedKeyword.value))) return
    ids.add(String(model.id))
  })
  return ids
})
const visibleModels = computed(() => scopeModels.value.filter(model => visibleModelIds.value.has(String(model.id))))
const visibleModelMap = computed(() => new Map(visibleModels.value.map(model => [String(model.id), model])))
const normalizedKeyword = computed(() => filters.keyword.trim().toLowerCase())
const selectedModel = computed(() => visibleModelMap.value.get(String(selectedModelId.value)) || null)
const topConnectedModels = computed(() => visibleModels.value
  .slice()
  .sort((left, right) => (
    modelDegree(right.id) - modelDegree(left.id)
    || Number(right.ci_count || 0) - Number(left.ci_count || 0)
    || String(left.name || left.code || '').localeCompare(String(right.name || right.code || ''), 'zh-Hans-CN')
  ))
  .slice(0, 8))
const selectedRules = computed(() => {
  if (!selectedModel.value) return []
  return visibleRules.value
    .filter(rule => String(rule.source_type) === String(selectedModel.value.id) || String(rule.target_type) === String(selectedModel.value.id))
    .map((rule) => {
      const outgoing = String(rule.source_type) === String(selectedModel.value.id)
      const otherModelId = outgoing ? String(rule.target_type) : String(rule.source_type)
      const other = modelMap.value.get(otherModelId)
      return {
        ...rule,
        otherModelId,
        otherModelName: other?.name || otherModelId,
        directionLabel: outgoing ? '向外' : '向内',
      }
    })
})
const selectedModelStats = computed(() => {
  if (!selectedModel.value) return []
  const incoming = visibleRules.value.filter(rule => String(rule.target_type) === String(selectedModel.value.id)).length
  const outgoing = visibleRules.value.filter(rule => String(rule.source_type) === String(selectedModel.value.id)).length
  return [
    { label: '资源数量', value: selectedModel.value.ci_count || 0 },
    { label: '出向关系', value: outgoing },
    { label: '入向关系', value: incoming },
    { label: '字段数量', value: selectedModel.value.field_count ?? selectedModel.value.fields_count ?? '-' },
  ]
})
const topologyGroupRows = computed(() => {
  const activeApiGroups = modelGroups.value.filter(group => group.is_active !== false && String(group.code || '').toLowerCase() !== 'data')
  const apiByCode = new Map(activeApiGroups.map(group => [String(group.code || '').toLowerCase(), group]))
  const standardRows = standardTopologyGroups.map((group) => {
    const apiGroup = apiByCode.get(group.code)
    return {
      ...(apiGroup || {}),
      key: group.key,
      code: group.code,
      label: apiGroup?.name || group.label,
      name: apiGroup?.name || group.label,
      color: resolveThemeColor(group.color, 'text'),
      sort: apiGroup?.sort_order ?? group.sort,
      is_standard: true,
    }
  })
  const customRows = activeApiGroups
    .filter(group => !standardTopologyGroupCodes.has(String(group.code || '').toLowerCase()))
    .map(group => ({
      ...group,
      key: String(group.code || group.id || group.name),
      code: String(group.code || '').toLowerCase(),
      label: group.name || group.code || '未分组',
      color: resolveThemeColor('#64748b', 'text'),
      sort: Number(group.sort_order || 999),
      is_standard: false,
    }))
  return [...standardRows, ...customRows].sort((left, right) => Number(left.sort || 0) - Number(right.sort || 0))
})
const topologyGroupByCode = computed(() => new Map(topologyGroupRows.value.map(group => [String(group.code || group.key).toLowerCase(), group])))
const groupOptions = computed(() => topologyGroupRows.value.map(group => ({ value: group.code || group.key, label: group.label || group.name })))
const relationTypeOptions = computed(() => {
  const map = new Map()
  relationRules.value.forEach(rule => {
    const key = normalizedRelationType(rule.relation_type)
    map.set(key, relationTypeLabel(key))
  })
  return [...map.entries()].map(([value, label]) => ({ value, label }))
})
const relationTypeStats = computed(() => {
  const counter = new Map()
  visibleRules.value.forEach((rule) => {
    const key = normalizedRelationType(rule.relation_type || 'related')
    counter.set(key, (counter.get(key) || 0) + 1)
  })
  return [...counter.entries()]
    .map(([key, count], index) => ({
      key,
      label: relationTypeLabel(key),
      count,
      tone: ['info', 'success', 'warning', 'danger'][index % 4],
    }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, 'zh-Hans-CN'))
})
const groupStats = computed(() => {
  const counter = new Map()
  visibleModels.value.forEach((model) => {
    const group = topologyGroupByCode.value.get(modelGroupKey(model)) || { key: 'ungrouped', label: '未分组' }
    counter.set(group.key, {
      key: group.key,
      label: group.label,
      count: (counter.get(group.key)?.count || 0) + 1,
      sort: group.sort ?? 9999,
    })
  })
  return [...counter.values()]
    .sort((left, right) => Number(left.sort || 0) - Number(right.sort || 0) || left.label.localeCompare(right.label, 'zh-Hans-CN'))
})
const topologyHierarchyGroups = computed(() => {
  const knownGroups = topologyGroupRows.value.map(group => ({
    key: group.code || group.key,
    label: group.label || group.name || '未分组',
    sort: Number(group.sort || 0),
    color: group.color || '#64748b',
    is_standard: group.is_standard,
    models: [],
  }))
  const groups = new Map(knownGroups.map(group => [group.key, group]))
  visibleModels.value.forEach((model) => {
    const key = modelGroupKey(model) || 'ungrouped'
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        label: model.group_name || '未分组',
        sort: 9999,
        color: resolveThemeColor('#64748b', 'text'),
        is_standard: false,
        models: [],
      })
    }
    groups.get(key).models.push(model)
  })
  return [...groups.values()]
    .filter(group => group.models.length || (group.is_standard && !selectedScopeKey.value && !filters.group && !filters.relation_type && !normalizedKeyword.value))
    .map(group => ({
      ...group,
      models: group.models.slice().sort((left, right) => modelDegree(right.id) - modelDegree(left.id) || String(left.name).localeCompare(String(right.name), 'zh-Hans-CN')),
    }))
    .sort((left, right) => left.sort - right.sort || left.label.localeCompare(right.label, 'zh-Hans-CN'))
})
const topologyRelationLanes = computed(() => visibleRules.value.map((rule) => {
  const source = modelMap.value.get(String(rule.source_type))
  const target = modelMap.value.get(String(rule.target_type))
  const sourceGroup = source ? topologyGroupByCode.value.get(modelGroupKey(source)) : null
  const targetGroup = target ? topologyGroupByCode.value.get(modelGroupKey(target)) : null
  return {
    key: String(rule.id),
    sourceId: String(rule.source_type),
    targetId: String(rule.target_type),
    sourceName: source?.name || rule.source_type,
    targetName: target?.name || rule.target_type,
    sourceGroupName: sourceGroup?.label || source?.group_name || '未分组',
    targetGroupName: targetGroup?.label || target?.group_name || '未分组',
    relationLabel: relationTypeLabel(rule.relation_type),
    required: !!rule.required,
    color: relationColor(rule),
    dash: relationDash(rule),
  }
}))
const topologyBoardLanes = computed(() => topologyHierarchyGroups.value.map((group, groupIndex) => {
  const nodes = group.models.map((model, rowIndex) => ({
    id: String(model.id),
    model,
    name: model.name || model.code || '未命名分类',
    code: model.code || '',
    count: Number(model.ci_count || 0),
    color: modelColor(model),
    groupKey: group.key,
    groupLabel: group.label,
    x: LANE_LEFT + groupIndex * (LANE_WIDTH + LANE_GAP) + LANE_WIDTH / 2,
    y: LANE_TOP + LANE_NODE_TOP + rowIndex * LANE_NODE_STEP + NODE_DOT_CENTER_OFFSET,
    top: LANE_NODE_TOP + rowIndex * LANE_NODE_STEP,
  }))
  const laneHeight = Math.max(LANE_MIN_HEIGHT, LANE_NODE_TOP + Math.max(nodes.length, 1) * LANE_NODE_STEP + 42)
  return {
    ...group,
    x: LANE_LEFT + groupIndex * (LANE_WIDTH + LANE_GAP),
    y: LANE_TOP,
    width: LANE_WIDTH,
    height: laneHeight,
    nodes,
  }
}))
const topologyNodeMap = computed(() => {
  const map = new Map()
  topologyBoardLanes.value.forEach(lane => lane.nodes.forEach(node => map.set(node.id, node)))
  return map
})
const selectedNeighborIds = computed(() => {
  const ids = new Set()
  const selectedId = String(selectedModelId.value || '')
  if (!selectedId) return ids
  visibleRules.value.forEach((rule) => {
    const sourceId = String(rule.source_type)
    const targetId = String(rule.target_type)
    if (sourceId === selectedId) ids.add(targetId)
    if (targetId === selectedId) ids.add(sourceId)
  })
  return ids
})
const topologyBoardEdges = computed(() => visibleRules.value.map((rule) => {
  const source = topologyNodeMap.value.get(String(rule.source_type))
  const target = topologyNodeMap.value.get(String(rule.target_type))
  if (!source || !target) return null
  const selectedId = String(selectedModelId.value || '')
  const focused = !!selectedId && (source.id === selectedId || target.id === selectedId)
  const dimmed = !!selectedId && !focused
  const curve = Math.max(72, Math.abs(target.x - source.x) * 0.45)
  const sign = source.x <= target.x ? 1 : -1
  return {
    id: String(rule.id),
    sourceId: source.id,
    targetId: target.id,
    color: relationColor(rule),
    dash: relationDash(rule),
    required: !!rule.required,
    inactive: rule.is_active === false,
    focused,
    dimmed,
    path: `M ${source.x} ${source.y} C ${source.x + curve * sign} ${source.y}, ${target.x - curve * sign} ${target.y}, ${target.x} ${target.y}`,
  }
}).filter(Boolean))
const topologyBoardSize = computed(() => {
  const laneCount = Math.max(topologyBoardLanes.value.length, 1)
  const height = Math.max(...topologyBoardLanes.value.map(lane => lane.height), LANE_MIN_HEIGHT) + LANE_TOP + 22
  return {
    width: LANE_LEFT * 2 + laneCount * LANE_WIDTH + Math.max(0, laneCount - 1) * LANE_GAP,
    height,
  }
})
const scaledTopologyBoardSize = computed(() => ({
  width: Math.ceil(topologyBoardSize.value.width * graphZoom.value),
  height: Math.ceil(topologyBoardSize.value.height * graphZoom.value),
}))

function modelGroupKey(model) {
  const explicitCode = String(model.group_code || '').toLowerCase()
  if (standardTopologyGroupCodes.has(explicitCode)) return explicitCode
  const groupName = String(model.group_name || '').trim()
  const groupByName = topologyGroupRows.value.find(group => group.label === groupName || group.name === groupName)
  if (groupByName) return String(groupByName.code || groupByName.key).toLowerCase()
  const identity = `${model.code || ''} ${model.name || ''} ${model.group_name || ''}`.toUpperCase()
  if (/(THIRD_PARTY|EXTERNAL|SAAS|API|第三方|外部服务|服务商)/.test(identity)) return 'external'
  const inferred = standardTopologyGroups.find(group => group.keywords.some(keyword => identity.includes(String(keyword).toUpperCase())))
  if (inferred) return inferred.code
  return String(model.group ?? model.group_id ?? model.group_name ?? '').toLowerCase()
}

function relationTypeLabel(type) {
  const key = normalizedRelationType(type)
  const labels = {
    depends_on: '依赖',
    runs_on: '运行于',
    connects_to: '连接到',
    related: '关联',
  }
  return labels[key] || key || '关联'
}

function normalizedRelationType(type) {
  const key = String(type || '').trim()
  return {
    contains: 'connects_to',
    hosted_on: 'connects_to',
  }[key] || key
}

function modelColor(model) {
  const group = topologyGroupByCode.value.get(modelGroupKey(model))
  return resolveThemeColor(model.color || group?.color || ['#245bdb', '#0ea5e9', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444'][Math.abs(hashCode(model.group_name || model.name || 'model')) % 6], 'text')
}

function hashCode(text) {
  let hash = 0
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) - hash) + text.charCodeAt(index)
    hash |= 0
  }
  return hash
}

function relationColor(rule) {
  const colors = {
    depends_on: '#8d9db2',
    connects_to: '#b7a58d',
    runs_on: '#78a5a8',
    related: '#a5afbd',
  }
  return resolveThemeColor(colors[normalizedRelationType(rule?.relation_type)] || colors.related, 'text')
}

function relationDash(rule) {
  const dashes = {
    depends_on: '4 5',
    connects_to: '2 5',
    runs_on: '15 5',
    related: '5 4',
  }
  return dashes[normalizedRelationType(rule?.relation_type)] ?? dashes.related
}

function modelDegree(id) {
  return visibleRules.value.reduce((count, rule) => count + ((String(rule.source_type) === String(id) || String(rule.target_type) === String(id)) ? 1 : 0), 0)
}

function renderGraph() {
  if (selectedModelId.value && !visibleModelMap.value.has(String(selectedModelId.value))) {
    selectedModelId.value = ''
  }
}

function selectModel(id) {
  selectedModelId.value = String(id || '')
}

function topologyLaneStyle(lane) {
  return {
    left: `${lane.x}px`,
    top: `${lane.y}px`,
    width: `${lane.width}px`,
    height: `${lane.height}px`,
    '--lane-color': lane.color || '#64748b',
  }
}

function topologyNodeStyle(node) {
  return {
    top: `${node.top}px`,
    '--node-color': node.color || '#64748b',
  }
}

function nodeResourceCountText(node = {}) {
  const count = Number(node.count ?? node.resource_count ?? 0)
  return `${Number.isFinite(count) ? count : 0} 项资源`
}

function isRelatedModel(id) {
  return selectedNeighborIds.value.has(String(id))
}

function isDimmedModel(id) {
  const selectedId = String(selectedModelId.value || '')
  if (!selectedId) return false
  const nodeId = String(id)
  return nodeId !== selectedId && !selectedNeighborIds.value.has(nodeId)
}

function relationLegendStyle(type) {
  const key = normalizedRelationType(type)
  const rule = { relation_type: key }
  const legendStyles = {
    connects_to: 'dotted',
    runs_on: 'dashed',
    related: 'dashed',
  }
  return {
    borderColor: relationColor(rule),
    borderTopStyle: legendStyles[key] || 'dashed',
  }
}

function handleGraphWheel(event) {
  const delta = event.deltaY > 0 ? -0.08 : 0.08
  setGraphZoom(graphZoom.value + delta, event)
}

function applyGroupFilter(groupKey) {
  filters.group = filters.group === groupKey ? '' : groupKey
  renderGraph()
}

function resetFilters() {
  clearScope()
  filters.group = ''
  filters.relation_type = ''
  filters.status = 'active'
  filters.keyword = ''
  selectedModelId.value = ''
  renderGraph()
}

function filterScopeNode(value, data) {
  return !value || data.searchText.includes(value.trim().toLowerCase())
}

function selectScope(node) {
  selectedScopeKey.value = node.key
  selectedModelId.value = ''
  nextTick(() => { if (graphPanelRef.value) graphPanelRef.value.scrollLeft = 0 })
}

function clearScope() {
  selectedScopeKey.value = ''
  scopeTreeRef.value?.setCurrentKey(null)
}

function changeScopeMode(mode) {
  if (scopeMode.value === mode) return
  scopeMode.value = mode
  clearScope()
  nextTick(() => scopeTreeRef.value?.filter(scopeKeyword.value))
}

watch(scopeKeyword, value => scopeTreeRef.value?.filter(value))
watch(visibleModelMap, renderGraph)

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

function handleGraphPanelClick(event) {
  if (graphDrag.moved) {
    graphDrag.moved = false
    return
  }
  if (event.target?.closest?.('.board-node, .board-lane-title, .graph-legend-card, .graph-source-note')) return
  selectedModelId.value = ''
}

async function loadModelTopology() {
  loading.value = true
  scopeLoadError.value = false
  scopeReady.value = false
  try {
    const [typesRes, groupsRes, rulesRes, scopeRes] = await Promise.all([
      getCITypes({ page_size: 500 }),
      getCIModelGroups({ page_size: 200 }),
      getCIRelationRules({ page_size: 500 }),
      canViewCi.value ? Promise.all([getConfigItemLedgerTree(), getResourceNodeTree({ scope: 'all' })])
        .then(data => ({ data })).catch(error => ({ error })) : null,
    ])
    ciTypes.value = listOf(typesRes)
    modelGroups.value = listOf(groupsRes)
    relationRules.value = listOf(rulesRes)
    if (scopeRes?.error) {
      scopeLoadError.value = true
      assetRows.value = []
      resourceTrees.value = { business: [], cloud: [] }
    } else if (scopeRes) {
      assetRows.value = listOf(scopeRes.data[0])
      const nodes = scopeRes.data[1]
      resourceTrees.value = Array.isArray(nodes) ? { business: nodes, cloud: [] } : { business: listOf(nodes?.business), cloud: listOf(nodes?.cloud) }
      scopeReady.value = true
      if (selectedScopeKey.value && !scopeNodeIndex.value.has(selectedScopeKey.value)) clearScope()
    }
    selectedModelId.value = ''
    await nextTick()
    scopeTreeRef.value?.setCurrentKey(selectedScopeKey.value || null)
    scopeTreeRef.value?.filter(scopeKeyword.value)
    renderGraph()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '分类拓扑加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadModelTopology()
})
</script>

<style scoped>
.cmdb-model-topology-page{display:flex;flex-direction:column;gap:6px}
.asset-topology-workspace{display:grid;flex:1;grid-template-columns:260px minmax(0,1fr);gap:18px;align-items:stretch}
.asset-scope-panel{min-width:0;padding:0 12px 0 0;margin:0;min-height:520px;border-right:4px solid var(--el-border-color-lighter)}
.asset-scope-heading{margin-bottom:12px;font-size:14px;font-weight:700;line-height:1.3;color:var(--text-primary)}
.asset-scope-panel>.el-input{margin-bottom:12px}
.ledger-perspective-tabs{width:100%;margin-bottom:12px;padding:3px;gap:6px;border-radius:12px;box-shadow:none}
.neo-tab-btn{display:inline-flex;align-items:center;gap:6px;flex:1;min-width:0;min-height:34px;padding:0 8px;border:0;border-radius:8px;background:transparent;color:#475569;font-size:12px;font-weight:700;line-height:1.2;justify-content:center;white-space:nowrap;cursor:pointer}
.neo-tab-btn:hover{background:rgba(51,112,255,.06);color:#245bdb}
.neo-tab-btn.active{background:#e8f0ff;color:#245bdb;box-shadow:inset 0 0 0 1px rgba(51,112,255,.1)}
.neo-tab-btn .el-icon{font-size:14px}
.asset-scope-body{min-height:260px;max-height:640px;overflow:auto}
.asset-scope-all{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;min-height:34px;padding:0 8px;border:0;border-radius:8px;background:transparent;color:var(--text-primary);font:inherit;font-size:12px;cursor:pointer}
.asset-scope-all>span{display:inline-flex;align-items:center;gap:7px}
.asset-scope-all.active{background:var(--el-color-primary-light-9);color:var(--el-color-primary)}
.asset-scope-node{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0;flex:1;padding-right:8px;font-size:12px;color:var(--text-primary)}
.asset-scope-node>span{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.asset-scope-node em,.asset-scope-all em{flex:none;font-size:11px;font-style:normal;color:var(--text-secondary)}
.asset-scope-panel :deep(.el-tree){background:transparent;--el-tree-node-content-height:34px}
.asset-scope-panel :deep(.el-tree-node__content){border-radius:8px}
.asset-scope-panel :deep(.is-current>.el-tree-node__content){background:var(--el-color-primary-light-9)}
.asset-scope-message{font-size:12px;line-height:1.7;color:var(--el-color-danger)}
.asset-scope-panel button:focus-visible{outline:2px solid var(--el-color-primary);outline-offset:2px}
.hero.panel{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px;border:1px solid rgba(36,91,219,.09);border-radius:20px;background:linear-gradient(135deg,#fbfdff 0%,#f7faff 52%,#f9fbfd 100%);box-shadow:0 8px 20px rgba(15,23,42,.05)}
.hero-copy{min-width:0;flex:1}
.hero-title-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.hero-title-row h2{margin:0;color:#0f172a;font-size:23px;line-height:1.2}
.hero-icon{width:42px;height:42px;border-radius:13px;display:inline-flex;align-items:center;justify-content:center;color:#245bdb;background:rgba(51,112,255,.1)}
.page-inline-desc{margin:0;color:#64748b;font-size:13px;line-height:1.45}
.cmdb-model-topology-card{display:flex;flex-direction:column;min-width:0;margin:0;padding:14px 16px;overflow:hidden}
.asset-topology-main{display:flex;flex-direction:column;min-width:0;overflow:hidden}
.cmdb-model-topology-card .section-toolbar{align-items:center;margin:0 0 10px;padding:0;border:0}
.cmdb-model-topology-card .toolbar-head{display:inline-flex;align-items:baseline;gap:8px;min-width:0;flex:1 1 auto;flex-wrap:wrap}
.cmdb-model-topology-card .toolbar-title{font-size:15px;font-weight:800;color:#0f172a;line-height:1.35;white-space:nowrap}
.cmdb-model-topology-card .toolbar-desc{min-width:0;color:#64748b;font-size:12px;line-height:1.45;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cmdb-model-topology-card .workbench-card-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex:0 0 auto}
.cmdb-model-topology-card .workbench-card-actions :deep(.el-tag){height:24px;border-radius:7px;background:#f8fafc;color:#64748b;border-color:rgba(148,163,184,.16)}
.cmdb-model-topology-card .workbench-card-actions :deep(.el-button){height:30px;border-radius:8px;margin-left:0}
.cmdb-model-topology-toolbar{margin:0 0 12px;padding:8px;border:1px solid rgba(148,163,184,.14);border-radius:12px;background:linear-gradient(180deg,#fbfdff 0%,#f8fafc 100%);box-shadow:inset 0 1px 0 rgba(255,255,255,.9);display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:nowrap;overflow-x:auto}
.topology-filter-main,.topology-filter-actions{display:flex;align-items:center;gap:8px;min-width:0}
.topology-filter-main{flex:1 1 auto;flex-wrap:nowrap;overflow-x:auto;padding-bottom:2px;scrollbar-width:thin}
.topology-filter-label{flex:none}
.topology-filter-actions{flex:0 0 auto;justify-content:flex-end}
.topology-filter-label{height:28px;padding:0 10px;border:1px solid rgba(148,163,184,.16);border-radius:999px;background:#fff;color:#475569;font-size:12px;font-weight:700;display:inline-flex;align-items:center;gap:7px;white-space:nowrap;box-shadow:0 6px 14px rgba(15,23,42,.035)}
.topology-filter-dot{width:7px;height:7px;border-radius:999px;background:#245bdb;box-shadow:0 0 0 3px rgba(51,112,255,.1)}
.cmdb-model-topology-toolbar :deep(.el-input__wrapper),.cmdb-model-topology-toolbar :deep(.el-select__wrapper){min-height:32px;border-radius:10px;box-shadow:0 0 0 1px rgba(148,163,184,.16) inset;background:#fff}
.cmdb-model-topology-toolbar :deep(.el-button){height:32px;border-radius:10px;margin-left:0;font-weight:700}
.cmdb-model-topology-layout{display:grid;flex:1;grid-template-columns:minmax(0,1fr) 224px;gap:10px;min-height:480px}
.model-graph-panel{min-width:0;min-height:0;display:flex;flex-direction:column;gap:10px}
.model-side-panel{position:relative;min-width:0;border:1px solid rgba(148,163,184,.18);border-radius:22px;background:linear-gradient(180deg,#fff 0%,#f8fafc 100%);padding:15px;color:#0f172a;overflow:hidden;box-shadow:0 18px 42px rgba(15,23,42,.1)}
.model-side-header,.model-section-head{display:flex;align-items:center;justify-content:space-between;gap:10px}
.model-side-title{font-size:16px;font-weight:700;color:#0f172a}
.model-side-subtitle{font-size:12px;color:#64748b;line-height:1.45}
.model-side-subtitle{margin-top:4px}
.model-graph-board-shell{position:relative;display:flex;flex-direction:column;flex:1;min-width:0;min-height:0;gap:6px}
.model-graph-canvas{contain:size}
.model-graph-canvas{position:relative;flex:1;min-height:360px;width:100%;border:1px solid rgba(148,163,184,.18);border-radius:22px;background:linear-gradient(rgba(148,163,184,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(148,163,184,.07) 1px,transparent 1px),linear-gradient(rgba(59,130,246,.1) 1px,transparent 1px),linear-gradient(90deg,rgba(59,130,246,.1) 1px,transparent 1px),radial-gradient(circle at top left,rgba(59,130,246,.08),transparent 28%),radial-gradient(circle at bottom right,rgba(16,185,129,.08),transparent 30%),linear-gradient(180deg,#f8fbff 0%,#f1f7fd 100%);background-size:22px 22px,22px 22px,88px 88px,88px 88px,auto,auto,auto;box-shadow:0 18px 42px rgba(15,23,42,.1);overflow:auto;scrollbar-width:thin;cursor:grab}
.model-graph-canvas.dragging{cursor:grabbing;user-select:none}
.model-graph-canvas :deep(.el-loading-mask){border-radius:20px;background:rgba(248,250,252,.72)}
.topology-board-viewport{position:relative;min-width:100%;overflow:hidden}
.topology-board{position:absolute;top:0;left:0;min-width:100%;transform-origin:0 0}
.model-board-edges{position:absolute;inset:0;z-index:3;pointer-events:none}
.model-board-edge{fill:none;stroke-width:1.35;stroke-linecap:round;opacity:.52;transition:opacity .16s ease,stroke-width .16s ease}
.model-board-edge.required{stroke-width:1.75}
.model-board-edge.inactive{opacity:.28}
.model-board-edge.focused{opacity:.72;stroke-width:2.1}
.model-board-edge.dimmed{opacity:.045;stroke-width:1}
.model-board-lane{position:absolute;z-index:2}
.board-lane-title{position:absolute;top:0;left:0;right:0;z-index:7;height:34px;border:1px solid color-mix(in srgb,var(--lane-color) 28%,rgba(148,163,184,.18));border-radius:14px;background:rgba(255,255,255,.98);color:#0f172a;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:700;cursor:pointer;font-family:inherit;transition:all .16s ease}
.board-lane-title:hover,.board-lane-title.active{border-color:color-mix(in srgb,var(--lane-color) 46%,rgba(148,163,184,.18));color:var(--lane-color);box-shadow:0 10px 24px color-mix(in srgb,var(--lane-color) 12%,transparent)}
.board-lane-body{position:absolute;top:54px;left:0;right:0;bottom:0;border:1px solid color-mix(in srgb,var(--lane-color) 18%,rgba(148,163,184,.18));border-radius:18px;background:linear-gradient(180deg,color-mix(in srgb,var(--lane-color) 11%,#fff) 0%,rgba(255,255,255,.58) 100%);overflow:hidden}
.board-lane-body::after{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.3) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.3) 1px,transparent 1px);background-size:28px 28px;pointer-events:none}
.board-lane-count{position:absolute;top:14px;left:16px;z-index:5;padding:3px 9px;border-radius:8px;background:rgba(255,255,255,.9);color:#475569;font-size:12px;font-weight:700}
.board-node{position:absolute;left:50%;z-index:6;width:164px;min-height:82px;padding:8px 9px 9px;border:0;background:transparent;color:#0f172a;transform:translateX(-50%);cursor:pointer;font:inherit;transition:filter .16s ease,opacity .16s ease,transform .16s ease}
.board-node-dot{width:48px;height:48px;margin:0 auto 10px;border:2px solid rgba(255,255,255,.98);border-radius:50%;display:block;position:relative;box-shadow:0 0 0 1px rgba(148,163,184,.12)}
.board-node-dot::before{content:"";position:absolute;inset:-22px;z-index:-1;border-radius:50%;background:radial-gradient(circle,color-mix(in srgb,var(--node-color) 18%,transparent) 0%,color-mix(in srgb,var(--node-color) 10%,transparent) 36%,transparent 70%);pointer-events:none}
.board-node-type{position:absolute;top:46px;left:50%;z-index:2;padding:1px 6px;border:1px solid rgba(148,163,184,.18);border-radius:999px;background:rgba(255,255,255,.96);color:#475569;font-size:10px;font-weight:700;line-height:1.35;transform:translateX(-50%);pointer-events:none;max-width:112px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.board-node-label{max-width:150px;margin:0 auto;padding:5px 10px;border:1px solid rgba(148,163,184,.24);border-radius:10px;background:rgba(255,255,255,.98);display:block;overflow:hidden;color:#0f172a;font-size:12px;font-weight:700;line-height:1.25;text-overflow:ellipsis;white-space:nowrap}
.board-node-meta{max-width:150px;margin:5px auto 0;display:block;overflow:hidden;color:#64748b;font-size:10px;font-weight:600;line-height:1.2;text-align:center;text-overflow:ellipsis;white-space:nowrap}
.board-node:hover,.board-node.active{z-index:12;filter:saturate(1.08)}
.board-node.related{z-index:9}
.board-node.dimmed{opacity:.22;filter:grayscale(.75) saturate(.68)}
.board-node:hover .board-node-dot,.board-node.active .board-node-dot{box-shadow:0 0 0 2px rgba(255,255,255,.98),0 0 0 5px color-mix(in srgb,var(--node-color) 18%,transparent)}
.board-node.active .board-node-label{border-color:color-mix(in srgb,var(--node-color) 38%,rgba(148,163,184,.24));box-shadow:0 14px 28px rgba(15,23,42,.15)}
.board-node.related .board-node-label{border-color:color-mix(in srgb,var(--node-color) 26%,rgba(148,163,184,.24))}
.graph-legend-card{display:flex;align-items:center;flex-wrap:wrap;gap:12px;min-width:0;padding:7px 10px;border:1px solid var(--el-border-color-light);border-radius:10px;background:var(--el-fill-color-light);color:var(--text-secondary)}
.legend-title{color:var(--text-primary);font-size:11px;font-weight:700}
.legend-row{display:inline-flex;align-items:center;gap:6px;color:var(--text-secondary);font-size:11px}
.legend-row span:nth-child(2){overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.legend-line{display:inline-block;width:22px;border-top:1.5px dashed #a5afbd}
.legend-row em{color:#64748b;font-size:10px;font-style:normal}
.model-graph-empty{position:absolute;inset:0;z-index:8;display:flex;align-items:center;justify-content:center;background:rgba(248,250,252,.76)}
.model-side-panel{display:flex;flex-direction:column;gap:14px}
.sidebar-placeholder{display:flex;flex-direction:column;gap:6px}
.model-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.model-detail-item{border:1px solid rgba(148,163,184,.12);border-radius:10px;padding:10px;background:#fbfdff;display:flex;flex-direction:column;gap:4px}
.model-detail-item span{font-size:12px;color:#64748b}
.model-detail-item strong{font-size:13px;color:#0f172a;word-break:break-word}
.model-section{display:flex;flex-direction:column;gap:8px}
.model-rule-list{display:flex;flex-direction:column;gap:8px;max-height:240px;overflow:auto}
.model-rule-row,.service-row{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:rgba(255,255,255,.95);padding:10px 11px;cursor:pointer;text-align:left;font:inherit}
.model-rule-row:hover,.service-row:hover{border-color:rgba(36,91,219,.24);background:#f8fbff}
.model-rule-main{display:flex;flex-direction:column;gap:2px;min-width:0}
.model-rule-main strong{font-size:13px;color:#0f172a}
.model-rule-main small,.model-muted{font-size:12px;color:#64748b}
.high-connected-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.high-connected-grid .service-row{min-width:0;gap:4px;padding:8px 4px}
.service-row span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#0f172a;font-size:11px;font-weight:600}
.service-row em{flex:none;color:#245bdb;font-size:11px;font-style:normal;font-weight:700;font-variant-numeric:tabular-nums}
.section-title{margin:2px 0 -4px;color:#64748b;font-size:11px;font-weight:700}
.model-description{margin:0;font-size:13px;line-height:1.7;color:#475569}
.model-tag-row{display:flex;flex-wrap:wrap;gap:4px}
.model-tag-row :deep(.el-tag){flex:1 0 27%;min-width:fit-content;max-width:100%;height:auto;min-height:20px;padding:1px 2px;font-size:11px;line-height:1.4}
.model-tag-row :deep(.el-tag__content){white-space:normal;overflow-wrap:anywhere}
.model-side-empty{padding:8px 0 2px}
.cmdb-model-topology-toolbar :deep(.el-select),.cmdb-model-topology-toolbar :deep(.el-input){flex:0 0 auto}

@media (max-width: 1100px) {
  .asset-topology-workspace{grid-template-columns:1fr;gap:12px}
  .asset-scope-panel{min-height:0;padding:0 0 12px;border-right:0;border-bottom:1px solid var(--el-border-color-lighter)}
  .asset-scope-body{min-height:0;max-height:240px}
}

@media (max-width: 980px) {
  .cmdb-model-topology-layout{grid-template-columns:1fr}
  .model-graph-canvas{min-height:480px}
  .model-side-panel{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;border-radius:14px;box-shadow:none}
}

@media (max-width: 760px) {
  .cmdb-model-topology-card{padding:12px}
  .model-side-panel{display:flex}
  .model-graph-canvas{height:480px;min-height:480px}
}
</style>
