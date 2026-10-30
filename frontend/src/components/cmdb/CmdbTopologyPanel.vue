<template>
  <div class="topology-panel">
    <div class="topology-toolbar">
      <div class="toolbar-main">
        <span class="toolbar-label">
          <span class="toolbar-label-dot"></span>
          {{ labels.filterConditions }}
        </span>
        <el-select v-model="topoFilterBiz" clearable filterable :placeholder="labels.businessLine" style="width: 160px">
          <el-option v-for="businessLine in businessOptions" :key="businessLine" :label="businessLine" :value="businessLine" />
        </el-select>
        <el-select v-model="topoFilterEnv" clearable :placeholder="labels.environment" style="width: 140px">
          <el-option v-for="environment in environmentOptions" :key="environment" :label="envLabel(environment)" :value="environment" />
        </el-select>
        <el-select v-model="topoFilterType" clearable :placeholder="labels.ciType" style="width: 160px">
          <el-option v-for="type in ciTypes" :key="type.id" :label="type.name" :value="type.id" />
        </el-select>
        <el-select v-model="topologyScope" :placeholder="labels.scope" style="width: 190px">
          <el-option :label="labels.neighborScope" value="neighbors" />
          <el-option :label="labels.neighborScope2" value="neighbors_2" />
          <el-option :label="labels.neighborScope3" value="neighbors_3" />
          <el-option :label="labels.exactScope" value="exact" />
        </el-select>
      </div>
      <div class="toolbar-actions">
        <el-button @click="resetFilters">{{ labels.resetFilters }}</el-button>
        <el-button @click="fitCanvas">{{ labels.resetCanvas }}</el-button>
        <el-button v-if="canManage" type="primary" @click="openRelationDialog()">
          <el-icon><Link /></el-icon>
          {{ editingRelationId ? labels.editRelation : labels.addRelation }}
        </el-button>
      </div>
    </div>

    <div class="topology-kpis">
      <div class="topology-kpi">
        <span class="kpi-label">{{ labels.nodeCount }}</span>
        <span class="kpi-value">{{ topology.nodes.length }}</span>
      </div>
      <div class="topology-kpi">
        <span class="kpi-label">{{ labels.edgeCount }}</span>
        <span class="kpi-value">{{ topology.edges.length }}</span>
      </div>
      <div class="topology-kpi">
        <span class="kpi-label">{{ labels.matchedNodeCount }}</span>
        <span class="kpi-value">{{ matchedNodeCount }}</span>
      </div>
      <div class="topology-kpi">
        <span class="kpi-label">{{ labels.externalNodeCount }}</span>
        <span class="kpi-value">{{ externalNodeCount }}</span>
      </div>
    </div>

    <div class="topology-layout">
      <div class="topology-canvas-card" v-loading="topoLoading">
        <div v-if="!topology.nodes.length && !topoLoading" class="topology-empty">
          <el-empty :description="labels.emptyTopology" />
        </div>
        <CmdbTopologyCanvas
          ref="topologyCanvasRef"
          :nodes="topology.nodes"
          :edges="topology.edges"
          :ci-types="ciTypes"
          :resource-tree="resourceTree"
          :matched-node-ids="topology.meta?.matched_node_ids || []"
          :selected-node-id="selectedNodeId"
          :selected-edge-id="selectedEdgeId"
          :reset-token="resetToken"
          :labels="labels"
          :editable="canManage"
          @select-node="handleSelectNode"
          @select-edge="handleSelectEdge"
          @clear-selection="clearSelection"
          @edit-node="openItemEditorById"
        />
      </div>

      <div class="topology-sidebar">
        <div v-if="selectedNode" class="sidebar-section">
          <div class="sidebar-header">
            <div>
              <div class="sidebar-title">{{ selectedNode.name }}</div>
              <div class="sidebar-subtitle">{{ selectedNode.type }} / {{ selectedNode.business_line || labels.unassigned }}</div>
            </div>
            <el-tag :type="selectedNode.status === 'active' ? 'success' : selectedNode.status === 'idle' ? 'warning' : 'info'">
              {{ statusLabel(selectedNode.status) }}
            </el-tag>
          </div>

          <div class="detail-grid">
            <div class="detail-card">
              <div class="detail-label">{{ labels.environment }}</div>
              <div class="detail-value">{{ envLabel(selectedNode.env) }}</div>
            </div>
            <div class="detail-card">
              <div class="detail-label">IP</div>
              <div class="detail-value">{{ selectedNode.ip || '-' }}</div>
            </div>
            <div class="detail-card">
              <div class="detail-label">{{ labels.owner }}</div>
              <div class="detail-value">{{ selectedNode.admin_user || '-' }}</div>
            </div>
            <div class="detail-card">
              <div class="detail-label">{{ labels.monthlyCost }}</div>
              <div class="detail-value">{{ formatCurrency(selectedNode.monthly_cost) }}</div>
            </div>
            <div class="detail-card">
              <div class="detail-label">{{ labels.spec }}</div>
              <div class="detail-value">{{ selectedNode.instance_type || formatSpec(selectedNode) }}</div>
            </div>
            <div class="detail-card">
              <div class="detail-label">{{ labels.provider }}</div>
              <div class="detail-value">{{ selectedNode.cloud_provider || '-' }}</div>
            </div>
          </div>

          <div v-if="selectedNode.description" class="detail-block">
            <div class="detail-block-title">{{ labels.description }}</div>
            <div class="detail-block-body">{{ selectedNode.description }}</div>
          </div>

          <div v-if="canManage" class="sidebar-actions">
            <el-button type="primary" @click="editSelectedCi">
              <el-icon><Edit /></el-icon>
              {{ labels.editCi }}
            </el-button>
            <el-button @click="openRelationDialog()">
              <el-icon><Link /></el-icon>
              {{ labels.newRelation }}
            </el-button>
          </div>

          <div class="detail-block">
            <div class="detail-block-title">{{ labels.relatedResources }}</div>
            <div v-if="selectedNodeRelations.length" class="relation-list">
              <button
                v-for="relation in selectedNodeRelations"
                :key="relation.id"
                type="button"
                class="relation-row"
                @click="handleSelectEdge(relation.id)"
              >
                <div class="relation-main">
                  <span class="relation-tag">{{ relation.label }}</span>
                  <span class="relation-target">{{ relation.partnerName }}</span>
                </div>
                <span class="relation-meta">{{ relation.direction }}</span>
              </button>
            </div>
            <div v-else class="detail-empty">{{ labels.emptyRelations }}</div>
          </div>
        </div>

        <div v-else-if="selectedEdge" class="sidebar-section">
          <div class="sidebar-header">
            <div>
              <div class="sidebar-title">{{ selectedEdge.label }}</div>
              <div class="sidebar-subtitle">{{ selectedEdge.source_name }} -> {{ selectedEdge.target_name }}</div>
            </div>
            <el-tag type="info">{{ labels.relation }}</el-tag>
          </div>

          <div class="detail-grid single-column">
            <div class="detail-card full-width">
              <div class="detail-label">{{ labels.sourceNode }}</div>
              <div class="detail-value">{{ selectedEdge.source_name }}</div>
            </div>
            <div class="detail-card full-width">
              <div class="detail-label">{{ labels.targetNode }}</div>
              <div class="detail-value">{{ selectedEdge.target_name }}</div>
            </div>
            <div class="detail-card full-width">
              <div class="detail-label">{{ labels.description }}</div>
              <div class="detail-value">{{ selectedEdge.description || '-' }}</div>
            </div>
          </div>

          <div v-if="canManage" class="sidebar-actions">
            <el-button type="primary" @click="openRelationDialog(selectedEdge)">
              <el-icon><Edit /></el-icon>
              {{ labels.editRelation }}
            </el-button>
            <el-popconfirm :title="labels.confirmDeleteRelation" @confirm="removeSelectedRelation">
              <template #reference>
                <el-button type="danger" plain>
                  <el-icon><Delete /></el-icon>
                  {{ labels.deleteRelation }}
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>

        <div v-else class="sidebar-placeholder">
          <div class="placeholder-title">{{ labels.selectHintTitle }}</div>
          <div class="placeholder-text">{{ labels.selectHintText }}</div>
        </div>
      </div>
    </div>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-if="canManage" v-model="relationDialogVisible" :title="editingRelationId ? labels.editCiRelation : labels.addCiRelation" width="90%" style="max-width: 560px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="relationForm" label-width="90px">
        <el-form-item :label="labels.sourceCi">
          <el-select v-model="relationForm.source" filterable :placeholder="labels.selectSource" style="width: 100%">
            <el-option v-for="ci in allCiList" :key="ci.id" :label="ci.name" :value="ci.id">
              <span style="float: left">{{ ci.name }}</span>
              <span style="float: right; color: var(--text-secondary); font-size: 12px">{{ ci.ci_type_name }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item :label="labels.relationType">
          <el-select v-model="relationForm.relation_type" style="width: 100%">
            <el-option :label="labels.dependsOn" value="depends_on" />
            <el-option :label="labels.runsOn" value="runs_on" />
            <el-option :label="labels.connectsTo" value="connects_to" />
          </el-select>
        </el-form-item>
        <el-form-item :label="labels.targetCi">
          <el-select v-model="relationForm.target" filterable :placeholder="labels.selectTarget" style="width: 100%">
            <el-option v-for="ci in allCiList" :key="ci.id" :label="ci.name" :value="ci.id">
              <span style="float: left">{{ ci.name }}</span>
              <span style="float: right; color: var(--text-secondary); font-size: 12px">{{ ci.ci_type_name }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item :label="labels.relationDescription">
          <el-input v-model="relationForm.description" type="textarea" :rows="3" :placeholder="labels.relationDescriptionPlaceholder" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="relationDialogVisible = false">{{ labels.cancel }}</el-button>
        <el-button type="primary" :loading="relationSaving" @click="saveRelation">{{ labels.save }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Edit, Link } from '@element-plus/icons-vue'
import CmdbTopologyCanvas from './CmdbTopologyCanvas.vue'
import { deleteCIRelation, createCIRelation, getCmdbTopology, getConfigItems, updateCIRelation } from '@/api/modules/cmdb'
import { buildBusinessOptions, buildEnvironmentOptions, envLabel } from './useTopologyGraph'

const labels = {
  businessLine: '\u4e1a\u52a1\u7ebf',
  environment: '\u73af\u5883',
  ciType: 'CI \u7c7b\u578b',
  scope: '\u62d3\u6251\u8303\u56f4',
  filterConditions: '\u6761\u4ef6\u7b5b\u9009',
  neighborScope: '\u5e26\u4e00\u8df3\u90bb\u5c45',
  neighborScope2: '\u5e26\u4e24\u8df3\u90bb\u5c45',
  neighborScope3: '\u5e26\u4e09\u8df3\u90bb\u5c45\uff08\u4e0a\u9650\uff09',
  exactScope: '\u53ea\u770b\u547d\u4e2d\u8282\u70b9',
  resetFilters: '\u91cd\u7f6e\u7b5b\u9009',
  resetCanvas: '\u91cd\u7f6e\u753b\u5e03',
  addRelation: '\u6dfb\u52a0\u5173\u7cfb',
  editRelation: '\u7f16\u8f91\u5173\u7cfb',
  nodeCount: '\u8282\u70b9\u6570',
  edgeCount: '\u5173\u7cfb\u6570',
  matchedNodeCount: '\u547d\u4e2d\u8282\u70b9',
  externalNodeCount: '\u6269\u5c55\u8282\u70b9',
  emptyTopology: '\u5f53\u524d\u7b5b\u9009\u4e0b\u6ca1\u6709\u8d44\u6e90\u8282\u70b9\uff0c\u8bf7\u8c03\u6574\u4e1a\u52a1\u7ebf\u3001\u73af\u5883\u6216\u8303\u56f4\u3002',
  unassigned: '\u672a\u5206\u914d',
  owner: '\u8d1f\u8d23\u4eba',
  monthlyCost: '\u6708\u6210\u672c',
  spec: '\u89c4\u683c',
  provider: '\u4e91\u5382\u5546',
  description: '\u8bf4\u660e',
  editCi: '\u7f16\u8f91 CI',
  newRelation: '\u65b0\u5efa\u5173\u7cfb',
  relatedResources: '\u5173\u8054\u8d44\u6e90',
  emptyRelations: '\u5f53\u524d\u8282\u70b9\u8fd8\u6ca1\u6709\u5173\u8054\u5173\u7cfb\u3002',
  relation: '\u5173\u7cfb',
  sourceNode: '\u6e90\u8282\u70b9',
  targetNode: '\u76ee\u6807\u8282\u70b9',
  confirmDeleteRelation: '\u786e\u8ba4\u5220\u9664\u8fd9\u6761\u5173\u7cfb\u5417\uff1f',
  deleteRelation: '\u5220\u9664\u5173\u7cfb',
  selectHintTitle: '\u8bf7\u9009\u62e9\u8282\u70b9\u6216\u5173\u7cfb',
  selectHintText: '\u70b9\u51fb\u8282\u70b9\u67e5\u770b\u8be6\u60c5\uff0c\u70b9\u51fb\u8fde\u7ebf\u67e5\u770b\u5173\u7cfb\uff0c\u4e5f\u53ef\u4ee5\u62d6\u52a8\u753b\u5e03\u3001\u7f29\u653e\u89c6\u56fe\u6765\u67e5\u770b\u8fc7\u6ee4\u540e\u7684\u62d3\u6251\u3002',
  editCiRelation: '\u7f16\u8f91 CI \u5173\u7cfb',
  addCiRelation: '\u6dfb\u52a0 CI \u5173\u7cfb',
  sourceCi: '\u6e90 CI',
  selectSource: '\u9009\u62e9\u6e90\u8d44\u6e90',
  relationType: '\u5173\u7cfb\u7c7b\u578b',
  dependsOn: '\u4e1a\u52a1\u4f9d\u8d56',
  runsOn: '\u90e8\u7f72\u5728',
  connectsTo: '\u8fde\u63a5\u5230',
  targetCi: '\u76ee\u6807 CI',
  selectTarget: '\u9009\u62e9\u76ee\u6807\u8d44\u6e90',
  relationDescription: '\u5173\u7cfb\u63cf\u8ff0',
  relationDescriptionPlaceholder: '\u8865\u5145\u8bf4\u660e\u4e1a\u52a1\u4f9d\u8d56\u3001\u7f51\u7edc\u8c03\u7528\u6216\u90e8\u7f72\u627f\u8f7d\u5173\u7cfb',
  cancel: '\u53d6\u6d88',
  save: '\u4fdd\u5b58',
  outgoing: '\u51fa\u5411',
  incoming: '\u5165\u5411',
  active: '\u8fd0\u884c\u4e2d',
  idle: '\u7a7a\u95f2',
  offline: '\u79bb\u7ebf',
  maintenance: '\u7ef4\u62a4\u4e2d',
  decommissioned: '\u5df2\u4e0b\u7ebf',
}

const props = defineProps({
  ciTypes: {
    type: Array,
    default: () => [],
  },
  resourceTree: {
    type: Array,
    default: () => [],
  },
  canManage: {
    type: Boolean,
    default: false,
  },
  focusCiId: {
    type: [String, Number],
    default: null,
  },
})

const emit = defineEmits(['edit-ci'])

const topologyCanvasRef = ref(null)
const topoLoading = ref(false)
const relationSaving = ref(false)
const relationDialogVisible = ref(false)
const editingRelationId = ref(null)
const topoFilterBiz = ref(null)
const topoFilterEnv = ref(null)
const topoFilterType = ref(null)
const topologyScope = ref('neighbors')
const topology = ref({ nodes: [], edges: [], meta: { matched_node_ids: [] } })
const allCiList = ref([])
const selectedNodeId = ref(null)
const selectedEdgeId = ref(null)
const relationForm = ref({ source: null, target: null, relation_type: 'depends_on', description: '' })

let fetchTimer = null

const businessOptions = computed(() => buildBusinessOptions(props.resourceTree, topology.value.nodes, { includeEmpty: true }))
const environmentOptions = computed(() => buildEnvironmentOptions(props.resourceTree, topoFilterBiz.value, topology.value.nodes, { includeEmpty: true }))
const allCiMap = computed(() => new Map(allCiList.value.map(item => [item.id, item])))
const selectedNode = computed(() => topology.value.nodes.find(node => node.id === selectedNodeId.value) || null)
const selectedEdge = computed(() => topology.value.edges.find(edge => edge.id === selectedEdgeId.value) || null)
const matchedNodeCount = computed(() => topology.value.meta?.matched_node_ids?.length || topology.value.nodes.filter(node => node.is_match).length)
const externalNodeCount = computed(() => Math.max(topology.value.nodes.length - matchedNodeCount.value, 0))
const resetToken = computed(() => [topoFilterBiz.value || '', topoFilterEnv.value || '', topoFilterType.value || '', topologyScope.value, topology.value.meta?.node_count || 0, topology.value.meta?.edge_count || 0].join('|'))
const selectedNodeRelations = computed(() => {
  if (!selectedNode.value) return []
  return topology.value.edges
    .filter(edge => edge.source === selectedNode.value.id || edge.target === selectedNode.value.id)
    .map(edge => ({
      ...edge,
      partnerId: edge.source === selectedNode.value.id ? edge.target : edge.source,
      partnerName: edge.source === selectedNode.value.id ? edge.target_name : edge.source_name,
      direction: edge.source === selectedNode.value.id ? labels.outgoing : labels.incoming,
    }))
})

function formatCurrency(value) {
  return `\u00A5${Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
}
function formatSpec(node) {
  const cpu = node.cpu ? `${node.cpu}C` : null
  const memory = node.memory_gb ? `${node.memory_gb}G` : null
  const disk = node.disk_gb ? `${node.disk_gb}G ${'\u78c1\u76d8'}` : null
  return [cpu, memory, disk].filter(Boolean).join(' / ') || '-'
}

function statusLabel(status) {
  return {
    active: labels.active,
    idle: labels.idle,
    offline: labels.offline,
    maintenance: labels.maintenance,
    decommissioned: labels.decommissioned,
  }[status] || status || '-'
}

function getErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (detail) return detail
  const data = error?.response?.data
  if (Array.isArray(data?.non_field_errors) && data.non_field_errors.length) return data.non_field_errors[0]
  if (typeof data === 'string') return data
  if (data && typeof data === 'object') {
    const firstValue = Object.values(data)[0]
    if (Array.isArray(firstValue) && firstValue.length) return firstValue[0]
  }
  return fallback
}

async function ensureAllCiList(force = false) {
  if (allCiList.value.length && !force) return
  const response = await getConfigItems({ page_size: 999 })
  allCiList.value = (response.results || response).slice().sort((left, right) => left.name.localeCompare(right.name))
}

async function fetchTopology() {
  topoLoading.value = true
  try {
    const neighborHops = { neighbors: 1, neighbors_2: 2, neighbors_3: 3 }[topologyScope.value]
    const params = {
      scope: topologyScope.value === 'exact' ? 'exact' : 'neighbors',
      ...(neighborHops ? { neighbor_hops: neighborHops } : {}),
    }
    if (props.focusCiId) params.ci_id = props.focusCiId
    if (topoFilterBiz.value) params.business_line = topoFilterBiz.value
    if (topoFilterEnv.value) params.environment = topoFilterEnv.value
    if (topoFilterType.value) params.ci_type = topoFilterType.value
    const response = await getCmdbTopology(params)
    topology.value = {
      nodes: response.nodes || [],
      edges: response.edges || [],
      meta: response.meta || { matched_node_ids: [] },
    }
    if (selectedNodeId.value && !topology.value.nodes.some(node => node.id === selectedNodeId.value)) {
      clearSelection()
    }
    if (selectedEdgeId.value && !topology.value.edges.some(edge => edge.id === selectedEdgeId.value)) {
      clearSelection()
    }
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '\u52a0\u8f7d\u8d44\u6e90\u5730\u56fe\u5931\u8d25'))
  } finally {
    topoLoading.value = false
  }
}

function scheduleFetch() {
  clearTimeout(fetchTimer)
  fetchTimer = setTimeout(() => {
    fetchTopology()
  }, 160)
}

function clearSelection() {
  selectedNodeId.value = null
  selectedEdgeId.value = null
}

function handleSelectNode(nodeId) {
  selectedNodeId.value = nodeId
  selectedEdgeId.value = null
}

function handleSelectEdge(edgeId) {
  selectedEdgeId.value = edgeId
  selectedNodeId.value = null
}

function resetFilters() {
  topoFilterBiz.value = null
  topoFilterEnv.value = null
  topoFilterType.value = null
  topologyScope.value = 'neighbors'
  clearSelection()
}

function fitCanvas() {
  topologyCanvasRef.value?.fitView()
}

function openRelationDialog(edge = null) {
  if (!props.canManage) return
  editingRelationId.value = edge?.id || null
  relationForm.value = edge
    ? {
        source: edge.source,
        target: edge.target,
        relation_type: edge.type,
        description: edge.description || '',
      }
    : {
        source: selectedNode.value?.id || null,
        target: null,
        relation_type: 'depends_on',
        description: '',
      }
  relationDialogVisible.value = true
  ensureAllCiList().catch(() => {
    ElMessage.error('\u52a0\u8f7d CI \u5217\u8868\u5931\u8d25')
  })
}

async function saveRelation() {
  if (!props.canManage) return
  if (!relationForm.value.source || !relationForm.value.target) {
    ElMessage.warning('\u8bf7\u9009\u62e9\u6e90 CI \u548c\u76ee\u6807 CI')
    return
  }

  relationSaving.value = true
  try {
    if (editingRelationId.value) {
      await updateCIRelation(editingRelationId.value, relationForm.value)
      ElMessage.success('\u5173\u7cfb\u5df2\u66f4\u65b0')
    } else {
      await createCIRelation(relationForm.value)
      ElMessage.success('\u5173\u7cfb\u5df2\u521b\u5efa')
    }
    relationDialogVisible.value = false
    editingRelationId.value = null
    await ensureAllCiList(true)
    await fetchTopology()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '\u4fdd\u5b58\u5173\u7cfb\u5931\u8d25'))
  } finally {
    relationSaving.value = false
  }
}

async function removeSelectedRelation() {
  if (!props.canManage) return
  if (!selectedEdge.value) return
  try {
    await deleteCIRelation(selectedEdge.value.id)
    ElMessage.success('\u5173\u7cfb\u5df2\u5220\u9664')
    clearSelection()
    await fetchTopology()
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '\u5220\u9664\u5173\u7cfb\u5931\u8d25'))
  }
}

async function editSelectedCi() {
  if (!props.canManage) return
  if (!selectedNode.value) return
  await ensureAllCiList()
  emit('edit-ci', allCiMap.value.get(selectedNode.value.id) || selectedNode.value)
}

async function openItemEditorById(nodeId) {
  if (!props.canManage) return
  await ensureAllCiList()
  const ci = allCiMap.value.get(nodeId)
  if (ci) emit('edit-ci', ci)
}

watch(
  () => [topoFilterBiz.value, topoFilterEnv.value, topoFilterType.value, topologyScope.value],
  () => {
    clearSelection()
    scheduleFetch()
  },
  { immediate: true },
)

watch(
  () => props.focusCiId,
  () => {
    clearSelection()
    scheduleFetch()
  },
)

watch(
  () => topoFilterBiz.value,
  value => {
    if (value && topoFilterEnv.value && !environmentOptions.value.includes(topoFilterEnv.value)) {
      topoFilterEnv.value = null
    }
  },
)

watch(
  () => [topoFilterBiz.value, topoFilterEnv.value],
  ([businessLine, environment]) => {
    if ((businessLine || environment) && topologyScope.value === 'neighbors') {
      topologyScope.value = 'exact'
    }
  },
)

watch(
  () => props.resourceTree,
  () => {
    if (topoFilterBiz.value && !businessOptions.value.includes(topoFilterBiz.value)) {
      topoFilterBiz.value = null
      topoFilterEnv.value = null
    }
    scheduleFetch()
  },
  { deep: true },
)

watch(
  () => relationDialogVisible.value,
  visible => {
    if (!visible) {
      editingRelationId.value = null
      relationForm.value = { source: null, target: null, relation_type: 'depends_on', description: '' }
    }
  },
)

onMounted(() => {
  if (props.canManage) {
    ensureAllCiList().catch(() => {})
  }
})

onBeforeUnmount(() => {
  if (fetchTimer) clearTimeout(fetchTimer)
})
</script>

<style scoped>
.topology-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.topology-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.toolbar-main,
.toolbar-actions,
.sidebar-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
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

.topology-kpis {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.topology-kpi {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 7px 12px;
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
  font-size: 18px;
  font-weight: 700;
  line-height: 1;
}

.topology-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 14px;
  min-height: 640px;
}

.topology-canvas-card,
.topology-sidebar {
  position: relative;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 20px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  overflow: hidden;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
}

.topology-canvas-card {
  min-height: 640px;
}

.topology-empty {
  position: absolute;
  inset: 0;
  z-index: 7;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(248, 250, 252, 0.72);
}

.topology-sidebar {
  padding: 18px;
  color: #0f172a;
}

.sidebar-section,
.sidebar-placeholder {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.sidebar-title,
.placeholder-title {
  font-size: 18px;
  font-weight: 700;
}

.sidebar-subtitle,
.placeholder-text,
.detail-empty {
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.single-column {
  grid-template-columns: 1fr;
}

.detail-card {
  padding: 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.full-width {
  width: 100%;
}

.detail-label,
.detail-block-title {
  margin-bottom: 6px;
  color: #64748b;
  font-size: 12px;
}

.detail-value,
.detail-block-body {
  color: #0f172a;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}

.detail-block {
  padding-top: 4px;
}

.relation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.relation-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.96);
  color: inherit;
  cursor: pointer;
}

.relation-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
}

.relation-tag {
  color: #7c3aed;
  font-size: 12px;
  font-weight: 600;
}

.relation-target,
.relation-meta {
  font-size: 12px;
  color: #64748b;
}

@media (max-width: 1100px) {
  .topology-layout {
    grid-template-columns: 1fr;
  }
}
</style>




