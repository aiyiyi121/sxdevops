<template>
  <div class="task-resource-base">
    <section class="resource-content-card">
      <div class="section-toolbar resource-section-head">
        <div class="toolbar-head">
          <h3 class="toolbar-title">资源底座</h3>
          <span class="toolbar-desc">按业务线和环境组织主机、K8s 集群及手工资源。</span>
        </div>
      </div>
    <div class="cmdb-items-layout task-resource-cmdb-layout">
    <TaskResourceScopeTree :data="managedScopeTree" :loading="loading.scopeTree" :selection="selectedScope" @select="selectResourceScope">
      <template #actions>
        <button v-if="canManage" type="button" :aria-label="canManageCmdbTree ? '新增业务线' : '新增手工环境'" :title="canManageCmdbTree ? '新增业务线' : '新增手工环境'" @click="canManageCmdbTree ? openCmdbNodeDialog() : openNodeDialog()">
          <el-icon><Plus /></el-icon>
        </button>
      </template>
      <template #node-actions="{ node }">
        <button v-for="action in nodeActions(node)" :key="action.key" type="button" :title="action.label" :aria-label="action.label" @click.stop="runNodeAction(action.key, node)">
          <el-icon><component :is="action.icon" /></el-icon>
        </button>
      </template>
    </TaskResourceScopeTree>

    <div class="cmdb-items-main resource-list-card">
      <div class="section-toolbar resource-list-head">
        <div class="toolbar-head">
          <h3 class="toolbar-title">执行资源</h3>
          <span class="toolbar-desc resource-inline-summary">{{ selectedScopeName }} · 主机 {{ stats.host || 0 }} · K8s {{ stats.k8s || 0 }} · 可用 {{ stats.active || 0 }} · 异常 {{ stats.warning || 0 }}</span>
        </div>
        <div class="resource-head-actions">
          <el-tag size="small" type="info">共 {{ pagination.total }} 个资源</el-tag>
          <el-button size="small" :loading="loading.resources" @click="reloadAll"><el-icon><RefreshRight /></el-icon>刷新</el-button>
          <el-button v-if="canManage" size="small" @click="openResourceDialog()"><el-icon><Plus /></el-icon>手工添加</el-button>
          <el-button v-if="canImportCmdb" type="primary" size="small" @click="openCmdbPicker"><el-icon><Connection /></el-icon>从 CMDB 接入</el-button>
        </div>
      </div>
      <div class="workbench-toolbar workbench-toolbar--history resource-toolbar">
        <div class="workbench-toolbar-left resource-toolbar-left">
          <el-select v-model="filters.resource_type" placeholder="资源类型" clearable style="width:120px" @change="refreshResourceView">
            <el-option label="主机" value="host" />
            <el-option label="K8s" value="k8s" />
          </el-select>
          <el-select v-model="filters.source_type" placeholder="资源来源" clearable style="width:132px" @change="refreshResourceView">
            <el-option label="CMDB 接入" value="cmdb" />
            <el-option label="手工添加" value="manual" />
          </el-select>
          <el-select v-model="filters.status" placeholder="状态" clearable style="width:110px" @change="refreshResourceView">
            <el-option label="可用" value="active" />
            <el-option label="异常" value="warning" />
            <el-option label="停用" value="inactive" />
          </el-select>
          <el-input
            v-model="filters.search"
            placeholder="搜索名称 / IP / 集群"
            clearable
            style="width:200px"
            @clear="refreshResourceView"
            @keyup.enter="refreshResourceView"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
        </div>
        <div class="workbench-toolbar-right resource-toolbar-right">
          <el-button @click="resetFilters">重置</el-button>
        </div>
      </div>

      <div class="resource-table-wrap">
        <el-table
          stripe
          :data="resources"
          v-loading="loading.resources"
          row-key="id"
          class="resource-table cmdb-table"
          :max-height="560"
          :empty-text="emptyText"
        >
          <el-table-column prop="name" label="资源" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="resource-name-cell">
                <button v-if="canManage" type="button" class="resource-name-link" @click="openResourceDialog(row)">{{ row.name }}</button>
                <strong v-else>{{ row.name }}</strong>
                <div class="resource-cell-meta">
                  <span>{{ row.resource_type_display || resourceTypeLabel(row.resource_type) }}</span>
                  <code class="resource-id-badge">资源 ID #{{ row.id }}</code>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="执行入口" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="resource-endpoint">{{ resourceEndpoint(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="126">
            <template #default="{ row }">
              <el-tooltip v-if="row.source_type === 'cmdb'" :content="row.cmdb_ci ? `关联资产：${row.cmdb_ci_name}（#${row.cmdb_ci}）` : '关联 CMDB 资产已删除'">
                <el-tag size="small" :type="row.cmdb_ci ? 'primary' : 'warning'" effect="plain">CMDB 接入</el-tag>
              </el-tooltip>
              <el-tag v-else size="small" type="info" effect="plain">手工添加</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="environment_name" label="环境" width="120" show-overflow-tooltip />
          <el-table-column prop="system_name" label="系统" width="108" show-overflow-tooltip>
            <template #default="{ row }">{{ row.system_name || '-' }}</template>
          </el-table-column>
          <el-table-column label="执行状态" width="110">
            <template #default="{ row }">
              <el-tooltip v-if="row.execution_blocked_reason" :content="row.execution_blocked_reason">
                <el-tag size="small" effect="plain" type="warning">暂停执行</el-tag>
              </el-tooltip>
              <el-tag v-else size="small" effect="plain" :type="statusType(row.status)">
                {{ row.status_display || statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="说明" min-width="160" show-overflow-tooltip />
          <el-table-column v-if="canManage" label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button link size="small" @click="openResourceDialog(row)">编辑</el-button>
              <el-button link size="small" type="danger" @click="removeResource(row)">{{ row.source_type === 'cmdb' ? '移除' : '删除' }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="resource-pagination">
        <el-pagination v-model:current-page="pagination.page" :page-size="20" :total="pagination.total" layout="total, prev, pager, next" small @current-change="fetchResources" />
      </div>
    </div>
    </div>
    </section>

    <el-dialog v-model="cmdbPickerVisible" title="从 CMDB 接入资产" width="1120px" top="8vh" append-to-body destroy-on-close class="cmdb-picker-dialog">
      <div class="cmdb-picker-layout">
      <TaskResourceScopeTree :data="cmdbTree" :loading="loading.cmdbTree" :selection="selectedCmdbScope" all-label="全部 CMDB 资产" @select="selectCmdbScope" />
      <div class="cmdb-picker-main">
      <div class="cmdb-picker-scope">{{ selectedCmdbScopeName }}<span>共 {{ cmdbTotal }} 个资产</span></div>
      <div class="cmdb-picker-toolbar">
        <el-input v-model="cmdbQuery.search" placeholder="搜索资产名称 / IP / 系统" clearable @keyup.enter="searchCmdbAssets" @clear="searchCmdbAssets">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="cmdbQuery.resource_type" clearable placeholder="执行资源类型" @change="changeCmdbResourceType">
          <el-option label="主机" value="host" /><el-option label="K8s 集群" value="k8s" />
        </el-select>
        <el-button @click="searchCmdbAssets">查询</el-button>
      </div>
      <el-table v-loading="loading.cmdb" :data="cmdbAssets" max-height="420" size="small" empty-text="暂无可接入的主机或 K8s 集群资产">
        <el-table-column prop="name" label="资产名称" min-width="170" show-overflow-tooltip />
        <el-table-column prop="ci_type_name" label="资产类型" min-width="110" show-overflow-tooltip />
        <el-table-column prop="ip_address" label="IP 地址" min-width="130">
          <template #default="{ row }">{{ row.ip_address || '待补充' }}</template>
        </el-table-column>
        <el-table-column prop="environment_name" label="环境" min-width="100" show-overflow-tooltip />
        <el-table-column prop="system_name" label="系统" min-width="110" show-overflow-tooltip />
        <el-table-column label="接入" width="100" fixed="right">
          <template #default="{ row }">
            <el-tag v-if="row.connected" size="small" type="info" effect="plain">已接入</el-tag>
            <el-button v-else link type="primary" size="small" @click="selectCmdbAsset(row)">选择接入</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="resource-pagination">
        <el-pagination v-model:current-page="cmdbQuery.page" :page-size="20" :total="cmdbTotal" layout="total, prev, pager, next" small @current-change="fetchCmdbAssets" />
      </div>
      </div>
      </div>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="cmdbNodeDialogVisible" :title="`${editingCmdbTreeNode ? '编辑' : '新增'}${cmdbNodeForm.node_type === 'biz' ? '业务线' : '环境'}`" width="460px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="cmdbNodeForm" label-width="86px" class="resource-compact-form">
        <el-form-item label="节点名称" required>
          <el-input v-model="cmdbNodeForm.name" :disabled="editingCmdbTreeNode?.is_synced" maxlength="100" placeholder="请输入节点名称" />
        </el-form-item>
        <el-form-item v-if="cmdbNodeForm.node_type === 'env'" label="所属业务线">
          <el-input :model-value="cmdbNodeForm.parent_name" disabled />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="cmdbNodeForm.sort_order" :min="0" :max="9999" style="width:100%" />
        </el-form-item>
        <div class="field-hint">与 CMDB 共用业务环境节点，修改后两处同步生效。</div>
      </el-form>
      <template #footer>
        <el-button @click="cmdbNodeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading.submit" @click="submitCmdbNode">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog :close-on-click-modal="false"
      v-model="nodeDialogVisible"
      :title="nodeDialogTitle"
      class="workbench-edit-dialog resource-dialog"
      width="520px"
      top="5vh"
      append-to-body
      destroy-on-close
    >
      <el-form label-position="top" :model="nodeForm" label-width="96px" class="resource-compact-form">
        <el-form-item v-if="!editingNodeId" label="节点类型">
          <el-radio-group v-model="nodeForm.group_type">
            <el-radio label="environment">环境</el-radio>
            <el-radio label="system">系统</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-else label="节点类型">
          <el-tag size="small" :type="nodeForm.group_type === 'environment' ? 'success' : 'info'" effect="plain">
            {{ nodeForm.group_type === 'environment' ? '环境' : '系统' }}
          </el-tag>
        </el-form-item>
        <el-form-item v-if="nodeForm.group_type === 'system'" label="所属环境" required>
          <el-select v-model="nodeForm.parent" style="width:100%" placeholder="选择环境">
            <el-option v-for="env in environments" :key="env.id" :label="env.name" :value="env.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="nodeForm.name" :disabled="!!editingCmdbNode" placeholder="请输入节点名称" />
        </el-form-item>
        <el-form-item label="编码">
          <el-input v-model="nodeForm.code" placeholder="可选，例如 prod / payment" />
        </el-form-item>
        <el-form-item v-if="nodeForm.group_type === 'environment'" label="事件中心环境">
          <el-select
            v-model="nodeForm.event_environment"
            clearable
            filterable
            style="width:100%"
            placeholder="可选，关联后任务事件按该环境归集"
          >
            <el-option
              v-for="env in eventEnvironmentSelectOptions"
              :key="env.id"
              :label="env.label"
              :value="env.id"
            />
          </el-select>
          <div class="field-hint">未关联时仍按任务环境名称尝试匹配事件中心环境。</div>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="nodeForm.sort_order" :min="1" :max="9999" style="width:100%" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="nodeForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="nodeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading.submit" @click="submitNode">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog :close-on-click-modal="false"
      v-model="resourceDialogVisible"
      :title="resourceDialogTitle"
      class="workbench-edit-dialog resource-dialog"
      width="620px"
      top="5vh"
      append-to-body
      destroy-on-close
    >
      <el-form label-position="top" :model="resourceForm" label-width="86px" class="workbench-editor-form--sectioned resource-compact-form">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>资源信息</h3></div>
          <div>
            <div v-if="resourceForm.cmdb_ci || cmdbContext.deleted" class="cmdb-asset-context">
              <el-tag size="small" effect="plain">CMDB 接入</el-tag>
              <strong>{{ cmdbContext.name || resourceForm.name }}</strong>
              <span>{{ cmdbContext.deleted ? '原资产已删除，请移除后重新接入' : '已有信息沿用资产台账，缺失信息可在此补充。' }}</span>
            </div>
            <div class="form-row">
              <el-form-item label="资源类型" required class="form-col">
                <el-radio-group v-model="resourceForm.resource_type" :disabled="editingResourceId !== null || !!resourceForm.cmdb_ci">
                  <el-radio label="host">主机</el-radio>
                  <el-radio label="k8s">K8s</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="状态" required class="form-col">
                <el-select v-model="resourceForm.status" style="width:100%">
                  <el-option label="可用" value="active" />
                  <el-option label="异常" value="warning" />
                  <el-option label="停用" value="inactive" />
                </el-select>
              </el-form-item>
            </div>
            <div class="form-row">
              <el-form-item label="环境" required class="form-col">
                <el-input v-if="isCmdbField('environment')" :model-value="cmdbContext.environment_name" disabled />
                <el-select v-else v-model="resourceForm.environment" filterable style="width:100%" @change="resourceForm.system = ''">
                  <el-option v-for="env in environments" :key="env.id" :label="env.name" :value="env.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="系统" class="form-col">
                <el-input v-if="isCmdbField('system')" :model-value="cmdbContext.system_name" disabled />
                <el-select v-else v-model="resourceForm.system" clearable filterable style="width:100%" :disabled="!resourceForm.environment">
                  <el-option v-for="system in systemsForResource" :key="system.id" :label="system.name" :value="system.id" />
                </el-select>
              </el-form-item>
            </div>
            <el-form-item v-if="resourceForm.resource_type === 'host'" label="资源名称" required>
              <el-input v-model="resourceForm.name" :disabled="isCmdbField('name')" placeholder="请输入资源名称" />
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>连接与归属</h3></div>
          <div>
            <template v-if="resourceForm.resource_type === 'host'">
              <div class="form-row">
                <el-form-item label="IP 地址" required class="form-col">
                  <el-input v-model="resourceForm.ip_address" :disabled="isCmdbField('ip_address')" placeholder="补充主机 IP 地址" />
                </el-form-item>
                <el-form-item label="SSH 端口" class="form-col">
                  <el-input-number v-model="resourceForm.ssh_port" :disabled="isCmdbField('ssh_port')" :min="1" :max="65535" style="width:100%" />
                </el-form-item>
              </div>
              <div class="form-row">
                <el-form-item label="SSH 用户" class="form-col">
                  <el-input v-model="resourceForm.ssh_user" :disabled="isCmdbField('ssh_user')" />
                </el-form-item>
                <el-form-item label="SSH 密码" class="form-col">
                  <el-input v-model="resourceForm.ssh_password" type="password" show-password :placeholder="editingResourceId ? '留空保留已保存密码' : '补充任务执行密码'" />
                </el-form-item>
              </div>
            </template>
            <template v-else>
              <div class="form-row">
                <el-form-item label="K8s 集群" required class="form-col">
                  <el-select v-model="resourceForm.cluster" filterable style="width:100%" @change="syncK8sResourceName">
                    <el-option v-for="cluster in k8sClusters" :key="cluster.id" :label="cluster.name" :value="cluster.id" />
                  </el-select>
                  <div class="field-hint">请先在容器环境中添加好集群</div>
                </el-form-item>
                <el-form-item label="资源名称" class="form-col">
                  <el-input :model-value="resourceForm.cmdb_ci ? resourceForm.name : (selectedK8sClusterName || '选择集群后自动生成')" disabled />
                </el-form-item>
              </div>
            </template>
            <div class="form-row">
              <el-form-item v-if="resourceForm.resource_type === 'host'" label="负责人" class="form-col">
                <el-input v-model="resourceForm.owner" :disabled="isCmdbField('owner')" placeholder="可选" />
              </el-form-item>
              <el-form-item label="说明" class="workbench-editor-full form-col wide">
                <el-input v-model="resourceForm.description" :disabled="isCmdbField('description')" />
              </el-form-item>
            </div>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="resourceDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading.submit" :disabled="cmdbContext.deleted" @click="submitResource">{{ !editingResourceId && resourceForm.cmdb_ci ? '保存并接入' : '保存' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Connection, Delete, Edit, Plus, RefreshRight, Search } from '@element-plus/icons-vue'
import { createResourceNode, deleteResourceNode, updateResourceNode } from '@/api/modules/cmdb'
import { getK8sClusters } from '@/api/modules/container'
import { getEventEnvironments } from '@/api/modules/eventwall'
import {
  createTaskResource,
  createTaskResourceGroup,
  deleteTaskResource,
  deleteTaskResourceGroup,
  getTaskResourceStats,
  getTaskResourceCmdbOptions,
  getTaskResourceCmdbTree,
  getTaskResourceScopeTree,
  getTaskResourceTree,
  getTaskResources,
  updateTaskResource,
  updateTaskResourceGroup,
} from '@/api/modules/ops'
import { useAuthStore } from '@/stores/auth'
import TaskResourceScopeTree from './TaskResourceScopeTree.vue'

const emit = defineEmits(['tree-updated', 'stats-updated'])
const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('ops.task.resource.manage'))
const canImportCmdb = computed(() => canManage.value && auth.hasPermission('cmdb.ci.view'))
const canManageCmdbTree = computed(() => canManage.value && auth.hasPermission('cmdb.ci.manage'))

const treeData = ref([])
const scopeTree = ref([])
const selectedScope = ref(null)
const resources = ref([])
const stats = ref({})
const k8sClusters = ref([])
const eventEnvironmentOptions = ref([])
const loading = reactive({ tree: false, scopeTree: false, resources: false, submit: false, cmdb: false, cmdbTree: false })
const filters = reactive({ search: '', resource_type: '', source_type: '', status: '', environment: '', system: '', scope_business: '', scope_environment: '', scope_system: '' })
const pagination = reactive({ page: 1, total: 0 })
const cmdbPickerVisible = ref(false)
const cmdbAssets = ref([])
const cmdbTotal = ref(0)
const cmdbTree = ref([])
const selectedCmdbScope = ref(null)
const cmdbQuery = reactive({ search: '', resource_type: '', scope_business: '', scope_environment: '', scope_system: '', page: 1 })
const cmdbContext = reactive({ name: '', environment_name: '', system_name: '', fields: [], deleted: false })

const nodeDialogVisible = ref(false)
const editingNodeId = ref(null)
const editingCmdbNode = ref(null)
const nodeForm = reactive(defaultNodeForm())
const cmdbNodeDialogVisible = ref(false)
const editingCmdbTreeNode = ref(null)
const cmdbNodeForm = reactive({ name: '', node_type: 'biz', parent: null, parent_name: '', sort_order: 0 })

const resourceDialogVisible = ref(false)
const editingResourceId = ref(null)
const resourceForm = reactive(defaultResourceForm())

const environments = computed(() => treeData.value)
const systemsForResource = computed(() => environments.value.find(item => item.id === resourceForm.environment)?.children || [])
const selectedScopeName = computed(() => scopeName(selectedScope.value, managedScopeTree.value))
const selectedCmdbScopeName = computed(() => scopeName(selectedCmdbScope.value, cmdbTree.value))
const selectedK8sClusterName = computed(() => k8sClusters.value.find(item => item.id === resourceForm.cluster)?.name || '')
const eventEnvironmentSelectOptions = computed(() => eventEnvironmentOptions.value.map(item => ({
  ...item,
  label: `${item.name || item.code}（${item.code}）`,
})))
const nodeDialogTitle = computed(() => `${editingNodeId.value ? '编辑' : '新增'}节点`)
const resourceDialogTitle = computed(() => `${editingResourceId.value ? '编辑' : '新增'}执行资源`)
const emptyText = computed(() => (selectedScope.value || filters.search || filters.resource_type || filters.source_type || filters.status
  ? '暂无匹配资源' : '暂无执行资源，可从 CMDB 接入或手工添加'))

const managedScopeTree = computed(() => {
  const tree = scopeTree.value.map(business => ({ ...business, children: business.children.map(environment => ({ ...environment })) }))
  if (!canManage.value) return tree

  function ensureBusiness(system = null) {
    const token = system ? groupScopeToken(system) : 'unassigned'
    let business = tree.find(node => node.scope_business === token)
    if (!business) {
      business = { key: `business:${token}`, name: system?.name || '未归属业务线', node_type: 'biz', scope_business: token, scope_environment: '', resource_count: 0, children: [] }
      tree.push(business)
    }
    return business
  }

  function ensureEnvironment(business, group, system = null) {
    const token = groupScopeToken(group)
    let environment = business.children.find(node => node.scope_environment === token)
    if (!environment) {
      const source = tree.flatMap(node => node.children).find(node => node.scope_environment === token)
      environment = { ...source, key: `${business.key}/environment:${token}`, name: group.name, node_type: 'env', scope_business: business.scope_business, scope_environment: token, resource_count: 0, children: [] }
      business.children.push(environment)
    }
    environment.taskGroup = group
    if (system) environment.taskSystem = system
  }

  ensureBusiness()
  for (const environment of treeData.value) {
    if (!environment.cmdb_node) ensureEnvironment(ensureBusiness(), environment)
    for (const system of environment.children || []) {
      if (!system.cmdb_node) ensureEnvironment(ensureBusiness(system), environment, system)
    }
  }
  const systems = treeData.value.flatMap(environment => environment.children || [])
  for (const business of tree) {
    const groups = systems.filter(system => groupScopeToken(system) === business.scope_business)
    if (groups.length === 1) business.taskGroup = groups[0]
    for (const environment of business.children) {
      environment.taskGroup ||= treeData.value.find(group => groupScopeToken(group) === environment.scope_environment)
    }
  }
  return tree
})

function groupScopeToken(group) {
  return group.cmdb_node ? `node:${group.cmdb_node}` : `name:${group.name}`
}

function nodeActions(node) {
  if (!canManage.value || node.node_type === 'system') return []
  if (node.cmdb_node && !node.taskSystem) {
    if (!canManageCmdbTree.value) return []
    return [
      ...(node.node_type === 'biz' ? [{ key: 'create_cmdb_environment', label: '新增环境', icon: Plus }] : []),
      { key: 'edit_cmdb', label: node.is_synced ? '调整排序' : '编辑节点', icon: Edit },
      ...(!node.is_synced ? [{ key: 'delete_cmdb', label: '删除节点', icon: Delete }] : []),
    ]
  }
  if (node.node_type === 'biz' && node.scope_business === 'unassigned') {
    return [{ key: 'create_manual_environment', label: '新增手工环境', icon: Plus }]
  }
  const group = node.taskSystem || node.taskGroup
  if (!group || group.cmdb_node) return []
  return [
    ...(node.node_type === 'env' && !node.taskSystem ? [{ key: 'create_manual_system', label: '新增系统', icon: Plus }] : []),
    { key: 'edit_manual', label: node.taskSystem ? '编辑系统分组' : '编辑分组', icon: Edit },
    { key: 'delete_manual', label: node.taskSystem ? '删除系统分组' : '删除分组', icon: Delete },
  ]
}

async function runNodeAction(action, node) {
  if (!nodeActions(node).some(item => item.key === action)) return
  if (action === 'create_cmdb_environment') return openCmdbNodeDialog(null, node)
  if (action === 'edit_cmdb') return openCmdbNodeDialog(node)
  if (action === 'create_manual_environment') return openNodeDialog()
  if (action === 'create_manual_system') return openNodeDialog(null, node.taskGroup)
  if (action === 'edit_manual') return openNodeDialog(node.taskSystem || node.taskGroup)
  try {
    const message = action === 'delete_cmdb' ? `确认删除 CMDB 节点「${node.name}」？资产台账中的对应节点也会同步删除。` : `确认删除分组「${node.name}」？`
    await ElMessageBox.confirm(message, '删除节点', { type: 'warning' })
  } catch {
    return
  }
  if (action === 'delete_cmdb') {
    await deleteResourceNode(node.cmdb_node)
    ElMessage.success('节点已删除')
    await refreshTreeAfterChange()
  } else {
    await delNode(node.taskSystem || node.taskGroup)
  }
}

function openCmdbNodeDialog(node = null, parent = null) {
  if (!canManageCmdbTree.value) return
  editingCmdbTreeNode.value = node
  const parentId = node?.cmdb_parent || parent?.cmdb_node || null
  Object.assign(cmdbNodeForm, {
    name: node?.name || '', node_type: node?.node_type || (parent ? 'env' : 'biz'),
    parent: parentId, parent_name: scopeTree.value.find(business => business.cmdb_node === parentId)?.name || '',
    sort_order: node?.sort_order || 0,
  })
  cmdbNodeDialogVisible.value = true
}

async function submitCmdbNode() {
  if (!canManageCmdbTree.value) return
  if (!cmdbNodeForm.name.trim()) return ElMessage.warning('请填写节点名称')
  loading.submit = true
  try {
    const payload = { name: cmdbNodeForm.name.trim(), node_type: cmdbNodeForm.node_type, parent: cmdbNodeForm.parent, sort_order: cmdbNodeForm.sort_order }
    if (editingCmdbTreeNode.value) await updateResourceNode(editingCmdbTreeNode.value.cmdb_node, payload)
    else await createResourceNode(payload)
    cmdbNodeDialogVisible.value = false
    ElMessage.success('业务环境节点已保存')
    await refreshTreeAfterChange()
  } finally {
    loading.submit = false
  }
}

async function refreshTreeAfterChange() {
  selectedScope.value = null
  Object.assign(filters, { scope_business: '', scope_environment: '', scope_system: '' })
  pagination.page = 1
  await reloadAll()
}

function scopeName(selection, tree) {
  if (!selection) return '全部资源'
  const business = tree.find(node => node.scope_business === selection.scope_business)
  if (selection.node_type === 'system') {
    const environment = business?.children?.find(node => node.scope_environment === selection.scope_environment)
    return [business?.name, environment?.name, selection.name].filter(Boolean).join(' / ')
  }
  return selection.node_type === 'env' ? `${business?.name || '未归属业务线'} / ${selection.name}` : selection.name
}

function defaultNodeForm() {
  return { group_type: 'environment', parent: '', name: '', code: '', event_environment: '', sort_order: 100, description: '' }
}

function defaultResourceForm() {
  return {
    cmdb_ci: null,
    resource_type: 'host',
    name: '',
    environment: '',
    system: '',
    status: 'active',
    ip_address: '',
    ssh_port: 22,
    ssh_user: 'root',
    ssh_password: '',
    cluster: '',
    namespace: '',
    owner: '',
    description: '',
    metadata: {},
  }
}

function normalizeList(res) {
  if (Array.isArray(res)) return res
  if (Array.isArray(res?.results)) return res.results
  return []
}

function normalizeTree(list = []) {
  return list.map(env => ({
    ...env,
    children: (env.children || []).map(system => ({ ...system, children: [] })),
  }))
}

function resourceTypeLabel(type) {
  return type === 'k8s' ? 'K8s' : '主机'
}

function resourceEndpoint(row) {
  if (row.resource_type === 'k8s') return row.cluster_name || row.name || '-'
  return row.endpoint || row.ip_address || '-'
}

function statusLabel(status) {
  if (status === 'active') return '可用'
  if (status === 'warning') return '异常'
  if (status === 'inactive') return '停用'
  return status || '-'
}

function statusType(status) {
  if (status === 'active') return 'success'
  if (status === 'warning') return 'warning'
  return 'info'
}

function isCmdbField(field) {
  return !!resourceForm.cmdb_ci && cmdbContext.fields.includes(field)
}

async function openCmdbPicker() {
  if (!canImportCmdb.value) return
  Object.assign(cmdbQuery, { search: '', resource_type: '', scope_business: '', scope_environment: '', scope_system: '', page: 1 })
  selectedCmdbScope.value = null
  cmdbAssets.value = []
  cmdbTotal.value = 0
  cmdbPickerVisible.value = true
  await Promise.all([fetchCmdbAssets(), fetchCmdbTree()])
}

async function fetchCmdbTree() {
  loading.cmdbTree = true
  try {
    cmdbTree.value = normalizeList(await getTaskResourceCmdbTree({ resource_type: cmdbQuery.resource_type }))
  } finally {
    loading.cmdbTree = false
  }
}

function selectCmdbScope(node) {
  selectedCmdbScope.value = node
  cmdbQuery.scope_business = node?.scope_business || ''
  cmdbQuery.scope_environment = node?.scope_environment || ''
  cmdbQuery.scope_system = node?.scope_system || ''
  return searchCmdbAssets()
}

function changeCmdbResourceType() {
  return Promise.all([searchCmdbAssets(), fetchCmdbTree()])
}

async function fetchCmdbAssets() {
  loading.cmdb = true
  try {
    const response = await getTaskResourceCmdbOptions({ ...cmdbQuery })
    cmdbAssets.value = normalizeList(response)
    cmdbTotal.value = response.count ?? cmdbAssets.value.length
  } finally {
    loading.cmdb = false
  }
}

function searchCmdbAssets() {
  cmdbQuery.page = 1
  return fetchCmdbAssets()
}

function selectCmdbAsset(asset) {
  cmdbPickerVisible.value = false
  openResourceDialog(null, asset)
}

function selectResourceScope(node) {
  selectedScope.value = node
  filters.environment = ''
  filters.system = ''
  filters.scope_business = node?.scope_business || ''
  filters.scope_environment = node?.scope_environment || ''
  filters.scope_system = node?.scope_system || ''
  return refreshResourceView()
}

function resetFilters() {
  Object.assign(filters, { search: '', resource_type: '', source_type: '', status: '', environment: '', system: '', scope_business: '', scope_environment: '', scope_system: '' })
  selectedScope.value = null
  return refreshResourceView()
}

function syncK8sResourceName() {
  if (resourceForm.resource_type === 'k8s') {
    if (!resourceForm.cmdb_ci) resourceForm.name = selectedK8sClusterName.value
    resourceForm.namespace = ''
    resourceForm.owner = ''
  }
}

function openNodeDialog(row = null, parent = null) {
  if (!canManage.value) return
  editingNodeId.value = row?.id || null
  editingCmdbNode.value = row?.cmdb_node || null
  Object.assign(nodeForm, defaultNodeForm())
  if (row) {
    Object.assign(nodeForm, {
      group_type: row.group_type,
      parent: row.parent || '',
      name: row.name || '',
      code: row.code || '',
      event_environment: row.event_environment || '',
      sort_order: row.sort_order || 100,
      description: row.description || '',
    })
  } else {
    Object.assign(nodeForm, {
      group_type: parent ? 'system' : 'environment',
      parent: parent?.id || '',
    })
  }
  nodeDialogVisible.value = true
}

function openResourceDialog(row = null, asset = null) {
  if (!canManage.value) return
  editingResourceId.value = row?.id || null
  Object.assign(resourceForm, defaultResourceForm())
  Object.assign(cmdbContext, { name: '', environment_name: '', system_name: '', fields: [], deleted: false })
  if (row) {
    Object.assign(resourceForm, {
      cmdb_ci: row.cmdb_ci || null,
      resource_type: row.resource_type,
      name: row.name || '',
      environment: row.environment || '',
      system: row.system || '',
      status: row.status || 'active',
      ip_address: row.ip_address || '',
      ssh_port: row.ssh_port || 22,
      ssh_user: row.ssh_user || 'root',
      ssh_password: '',
      cluster: row.cluster || '',
      namespace: row.namespace || '',
      owner: row.owner || '',
      description: row.description || '',
      metadata: row.metadata || {},
    })
    Object.assign(cmdbContext, {
      name: row.cmdb_ci_name || row.name,
      environment_name: row.environment_name || '',
      system_name: row.system_name || '',
      fields: row.cmdb_fields || [],
      deleted: row.source_type === 'cmdb' && !row.cmdb_ci,
    })
  } else {
    Object.assign(resourceForm, {
      environment: filters.environment || '',
      system: filters.system || '',
    })
  }
  if (asset) {
    Object.assign(resourceForm, {
      cmdb_ci: asset.id,
      resource_type: asset.resource_type,
      name: asset.name,
      ip_address: asset.ip_address || '',
      ssh_port: asset.ssh_port || 22,
      ssh_user: asset.ssh_user || 'root',
      owner: asset.owner || '',
      description: asset.description || '',
    })
    Object.assign(cmdbContext, {
      name: asset.name,
      environment_name: asset.environment_name || '',
      system_name: asset.system_name || '',
      fields: asset.cmdb_fields || [],
    })
  }
  resourceDialogVisible.value = true
}

async function fetchTree() {
  loading.tree = true
  try {
    const res = await getTaskResourceTree()
    treeData.value = normalizeTree(normalizeList(res))
    emit('tree-updated', treeData.value)
  } finally {
    loading.tree = false
  }
}

async function fetchScopeTree() {
  loading.scopeTree = true
  try {
    scopeTree.value = normalizeList(await getTaskResourceScopeTree())
  } finally {
    loading.scopeTree = false
  }
}

async function fetchResources() {
  loading.resources = true
  try {
    const res = await getTaskResources({ ...filters, page: pagination.page })
    resources.value = normalizeList(res)
    pagination.total = res.count ?? resources.value.length
  } finally {
    loading.resources = false
  }
}

function statFilterParams() {
  return {
    environment: filters.environment || undefined,
    system: filters.system || undefined,
    status: filters.status || undefined,
    search: filters.search || undefined,
    source_type: filters.source_type || undefined,
    scope_business: filters.scope_business || undefined,
    scope_environment: filters.scope_environment || undefined,
    scope_system: filters.scope_system || undefined,
  }
}

async function fetchStats() {
  const res = await getTaskResourceStats(statFilterParams())
  stats.value = res || {}
  emit('stats-updated', stats.value)
}

async function refreshResourceView() {
  pagination.page = 1
  await Promise.all([fetchResources(), fetchStats()])
}

async function fetchK8sClusters() {
  try {
    k8sClusters.value = normalizeList(await getK8sClusters())
  } catch {
    k8sClusters.value = []
  }
}

async function fetchEventEnvironments() {
  try {
    eventEnvironmentOptions.value = normalizeList(await getEventEnvironments({ enabled: 'true' }))
  } catch {
    eventEnvironmentOptions.value = []
  }
}

async function reloadAll() {
  await Promise.all([fetchTree(), fetchScopeTree(), fetchResources(), fetchStats(), fetchK8sClusters(), fetchEventEnvironments()])
}

async function submitNode() {
  if (!nodeForm.name.trim()) return ElMessage.warning('请填写节点名称')
  if (nodeForm.group_type === 'system' && !nodeForm.parent) return ElMessage.warning('请选择所属环境')
  loading.submit = true
  try {
    const payload = {
      ...nodeForm,
      name: nodeForm.name.trim(),
      parent: nodeForm.group_type === 'system' ? nodeForm.parent : null,
      event_environment: nodeForm.group_type === 'environment' ? (nodeForm.event_environment || null) : null,
    }
    if (editingNodeId.value) {
      await updateTaskResourceGroup(editingNodeId.value, payload)
    } else {
      await createTaskResourceGroup(payload)
    }
    nodeDialogVisible.value = false
    ElMessage.success('资源树已保存')
    await refreshTreeAfterChange()
  } finally {
    loading.submit = false
  }
}

async function submitResource() {
  if (!resourceForm.environment && !isCmdbField('environment')) return ElMessage.warning('请选择环境')
  if (resourceForm.resource_type === 'host') {
    if (!resourceForm.name.trim()) return ElMessage.warning('请填写资源名称')
    if (!resourceForm.ip_address) return ElMessage.warning('请填写主机 IP')
  }
  if (resourceForm.resource_type === 'k8s') {
    if (!resourceForm.cluster) return ElMessage.warning('请选择 K8s 集群')
    syncK8sResourceName()
    if (!resourceForm.name.trim()) return ElMessage.warning('所选 K8s 集群缺少名称')
  }
  loading.submit = true
  try {
    const payload = {
      ...resourceForm,
      name: resourceForm.name.trim(),
      system: resourceForm.system || null,
      cluster: resourceForm.cluster || null,
      namespace: '',
    }
    if (isCmdbField('environment')) delete payload.environment
    if (isCmdbField('system')) delete payload.system
    if (payload.resource_type === 'k8s') {
      payload.ip_address = null
      payload.ssh_password = ''
      payload.ssh_user = ''
    }
    if (editingResourceId.value && !payload.ssh_password) delete payload.ssh_password
    if (editingResourceId.value) {
      await updateTaskResource(editingResourceId.value, payload)
    } else {
      await createTaskResource(payload)
    }
    resourceDialogVisible.value = false
    ElMessage.success('执行资源已保存')
    await reloadAll()
  } finally {
    loading.submit = false
  }
}

async function delNode(row) {
  await deleteTaskResourceGroup(row.id)
  ElMessage.success('节点已删除')
  await refreshTreeAfterChange()
}

async function removeResource(row) {
  try {
    const message = row.source_type === 'cmdb'
      ? `确认移除「${row.name}」的任务接入？CMDB 资产会保留。`
      : `确认删除执行资源「${row.name}」？`
    await ElMessageBox.confirm(message, '移除执行资源', { type: 'warning' })
  } catch {
    return
  }
  await deleteTaskResource(row.id)
  ElMessage.success('资源已删除')
  if (resources.value.length === 1 && pagination.page > 1) pagination.page -= 1
  await reloadAll()
}

onMounted(reloadAll)
</script>

<style scoped>
.task-resource-base {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.resource-content-card {
  flex: 1;
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  background: var(--el-bg-color);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.03);
}

.resource-section-head {
  margin: 0 0 10px;
  padding: 0;
  border: 0;
}

.resource-section-head .toolbar-head {
  display: inline-flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px 8px;
}

.resource-section-head .toolbar-title {
  margin: 0;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 800;
}

.resource-section-head .toolbar-desc {
  color: var(--text-secondary);
  font-size: 12px;
}

.resource-list-head,
.resource-head-actions,
.resource-list-head .toolbar-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.resource-list-head {
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.resource-list-head .toolbar-title {
  margin: 0 0 3px;
  font-size: 13px;
  font-weight: 800;
  color: var(--text-primary);
}

.resource-list-head .toolbar-desc {
  color: var(--text-secondary);
  font-size: 12px;
}

.resource-list-head .toolbar-head {
  display: block;
  min-width: 0;
}

.resource-inline-summary {
  line-height: 1.4;
}

.resource-head-actions :deep(.el-button) {
  margin: 0;
  border-radius: 8px;
}

.resource-head-actions :deep(.el-icon) {
  margin-right: 4px;
}

.tree-search {
  margin-bottom: 8px;
}

.tree-node-count {
  flex: none;
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  background: #f1f5f9;
  padding: 1px 6px;
  border-radius: 5px;
}

.tree-node-count {
  margin-left: auto;
}

.resource-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 12px 2px 0;
  margin-top: 10px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
}

.resource-name-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.resource-name-cell strong,
.resource-cell-meta > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-name-cell strong {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
}

.resource-name-link {
  width: fit-content;
  max-width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: #245bdb;
  font: inherit;
  font-weight: 700;
  line-height: 1.4;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.resource-name-link:hover {
  color: #1d4ed8;
  text-decoration: underline;
}

.resource-cell-meta {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  color: #64748b;
  font-size: 12px;
}

.resource-id-badge {
  flex: none;
  padding: 1px 5px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #64748b;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 10px;
  line-height: 1.4;
}

.resource-endpoint {
  color: #64748b;
  font-size: 12px;
}

.cmdb-picker-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.cmdb-picker-toolbar > .el-input {
  flex: 1;
}

.cmdb-picker-toolbar > .el-select {
  width: 160px;
}

:global(.cmdb-picker-dialog) {
  max-width: calc(100vw - 32px);
}

.cmdb-picker-layout {
  display: grid;
  grid-template-columns: 212px minmax(0, 1fr);
  gap: 18px;
}

.cmdb-picker-main {
  min-width: 0;
}

.cmdb-picker-scope {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 28px;
  margin-bottom: 12px;
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}

.cmdb-picker-scope > span {
  color: #64748b;
  font-size: 12px;
  font-weight: 400;
}

.cmdb-asset-context {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 12px;
  margin-bottom: 16px;
  border: 1px solid rgba(51, 112, 255, 0.14);
  border-radius: 10px;
  background: #f7faff;
  font-size: 12px;
  color: #475569;
}

.cmdb-asset-context > span:last-child {
  color: #64748b;
}

.custom-tree-node {
  transition: background 0.2s;
  border-radius: 6px;
}

.tree-node-content {
  flex: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  min-height: 26px;
  font-size: 12px;
  padding-right: 2px;
}

.custom-tree-node:hover {
  background: rgba(51, 112, 255, 0.05);
}

.tree-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.2s;
  white-space: nowrap;
  position: absolute;
  right: 32px;
  background: #fff;
  border-radius: 6px;
}

.tree-action-btn {
  min-height: 18px;
  height: 18px;
  min-width: 18px;
  padding: 0;
  margin-left: 0 !important;
  font-size: 11px;
}

.el-tree-node__content:hover .tree-actions {
  opacity: 1;
}

.tree-node-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-env-tag {
  height: 18px;
  padding: 0 5px;
  border-radius: 6px;
  color: #245bdb;
  border-color: rgba(51, 112, 255, 0.18);
  background: rgba(51, 112, 255, 0.08);
}

.tree-panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 4px 0;
}

.tree-panel-title {
  font-weight: 600;
  color: #0f172a;
  font-size: 13px;
  cursor: pointer;
}

.tree-head-btn {
  min-height: 24px;
  padding: 0 4px;
}

.cmdb-items-layout {
  display: flex;
  gap: 8px;
  min-height: 0;
}

.task-resource-cmdb-layout {
  display: grid;
  grid-template-columns: 236px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
  min-height: 0;
}

.cmdb-resource-tree-panel {
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 14px;
  background: #fff;
  padding: 14px 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.cmdb-items-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.resource-list-card {
  gap: 0;
  background: light-dark(#fbfdff, var(--el-bg-color));
  border: 1px solid color-mix(in srgb, var(--el-border-color) 48%, transparent);
  border-radius: 12px;
  padding: 12px;
  box-shadow: none;
}

.section-gap {
  margin-bottom: 10px;
}

.resource-tree {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background: transparent;
}

.resource-tree :deep(.el-tree-node__content) {
  position: relative;
  min-height: 34px;
  border-radius: 8px;
}

.resource-tree :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: #e8f0ff;
  color: #245bdb;
}

.tree-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px 0;
}

.toolbar,
.resource-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: nowrap;
  gap: 10px;
  margin: 0 0 10px;
  padding: 8px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.92) 0%, rgba(255, 255, 255, 0.96) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.toolbar-left,
.toolbar-right,
.resource-toolbar-left,
.resource-toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
}

.toolbar :deep(.el-input__wrapper),
.toolbar :deep(.el-select__wrapper),
.resource-toolbar :deep(.el-input__wrapper),
.resource-toolbar :deep(.el-select__wrapper) {
  min-height: 32px;
  border-radius: 8px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.12) inset;
  background: rgba(255, 255, 255, 0.94);
}

.toolbar :deep(.el-input__wrapper:hover),
.toolbar :deep(.el-select__wrapper:hover),
.resource-toolbar :deep(.el-input__wrapper:hover),
.resource-toolbar :deep(.el-select__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.16) inset;
}

.toolbar-right :deep(.el-button),
.resource-toolbar-right :deep(.el-button) {
  min-height: 26px;
  padding: 0 9px;
  border-radius: 8px;
  font-weight: 500;
}

.toolbar-right :deep(.el-button:not(.el-button--primary)),
.resource-toolbar-right :deep(.el-button:not(.el-button--primary)) {
  border-color: rgba(148, 163, 184, 0.12);
  background: rgba(255, 255, 255, 0.9);
  color: #475569;
  box-shadow: none;
}

.toolbar-right :deep(.el-button:not(.is-link):hover),
.resource-toolbar-right :deep(.el-button:not(.is-link):hover) {
  border-color: rgba(59, 130, 246, 0.18);
  color: #1d4ed8;
  background: #f8fbff;
}

.resource-table-wrap {
  min-height: 0;
  min-width: 0;
  display: block;
}

.resource-table {
  width: 100%;
}

.resource-list-card :deep(.el-table) {
  --el-table-border-color: #eef0f2;
  --el-table-header-bg-color: #eaf8f0;
  --el-table-row-hover-bg-color: #f6fffb;
  border: 0;
  border-radius: 0;
  overflow: hidden;
}

.resource-list-card :deep(.el-table th.el-table__cell) {
  color: #1f2937;
  font-weight: 500;
  background: #eaf8f0;
}

.resource-list-card :deep(.el-table td.el-table__cell) {
  border-bottom-color: #eef0f2;
}

.resource-list-card :deep(.el-table .el-table__row:hover > td.el-table__cell) {
  background: #f6fffb;
}

.form-row {
  display: flex;
  gap: 10px;
}

.form-col {
  flex: 1;
}

.field-hint {
  margin-top: 4px;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.4;
}

.resource-compact-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.resource-compact-form :deep(.el-input__wrapper),
.resource-compact-form :deep(.el-textarea__inner),
.resource-compact-form :deep(.el-select__wrapper) {
  min-height: 32px;
  border-radius: 10px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.16) inset;
  background: rgba(255, 255, 255, 0.94);
}

.resource-compact-form :deep(.el-input__wrapper:hover),
.resource-compact-form :deep(.el-textarea__inner:hover),
.resource-compact-form :deep(.el-select__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.18) inset;
}




.resource-dialog :deep(.el-button) {
  min-height: 30px;
  border-radius: 9px;
}

@media (max-width: 1200px) {
  .task-resource-cmdb-layout {
    grid-template-columns: 220px minmax(0, 1fr);
  }

  .resource-toolbar {
    overflow-x: auto;
  }
}

@media (max-width: 1100px) {
  .task-resource-cmdb-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 900px) {
  .cmdb-items-layout {
    flex-direction: column;
  }

  .task-resource-cmdb-layout {
    grid-template-columns: minmax(0, 1fr);
    min-height: auto;
  }

  .cmdb-picker-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .cmdb-resource-tree-panel {
    max-height: 280px;
  }

  .form-row {
    flex-direction: column;
    gap: 0;
  }
}
</style>
