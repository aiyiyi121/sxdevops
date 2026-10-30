<template>
  <div class="fade-in workbench-page-shell">
    <div class="workbench-card">
      <div class="workbench-card-head">
        <div class="workbench-card-title">
          <strong>只读查询台</strong>
          <span>沿用任务历史的卡片和结果区结构，便于和工单页统一浏览体验。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button v-if="canExecuteQueries" type="primary" @click="handleQuery" :loading="querying"
            :disabled="!selectedDs || !selectedDb || !sqlContent.trim()">
            <el-icon><CaretRight /></el-icon> 执行查询
          </el-button>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history">
        <div class="workbench-toolbar-left">
          <el-select v-model="selectedDs" placeholder="选择数据源" style="width: 220px"
            @change="onDsChange" filterable>
            <el-option v-for="ds in datasources" :key="ds.id" :label="ds.name" :value="ds.id">
              <span>{{ ds.name }}</span>
              <span style="color:var(--text-secondary); margin-left:8px; font-size:12px;">
                {{ getDatasourceTypeLabel(ds.db_type) }} / {{ ds.host }}:{{ ds.port }}
              </span>
            </el-option>
          </el-select>
          <el-select v-model="selectedDb" placeholder="选择数据库" style="width: 200px"
            :loading="dbLoading" filterable>
            <el-option v-for="db in databases" :key="db" :label="db" :value="db" />
          </el-select>
          <el-input v-model="submitter" placeholder="操作人" style="width: 130px" disabled />
        </div>
      </div>

      <div class="sql-editor-wrapper">
        <textarea v-model="sqlContent" class="sql-editor"
          :placeholder="queryPlaceholder" rows="6"
          @keydown.ctrl.enter="handleQuery"></textarea>
      </div>
      <div class="query-hint">{{ queryHint }}</div>
    </div>

    <div class="workbench-card" v-if="queryResult || queryError">
      <div class="workbench-card-head">
        <div class="workbench-card-title">
          <strong>查询结果</strong>
        </div>
        <div class="workbench-card-actions result-meta" v-if="queryResult">
          <el-tag type="info" size="small">{{ queryResult.count }} 行</el-tag>
          <el-tag type="success" size="small">{{ queryResult.duration_ms }}ms</el-tag>
        </div>
      </div>

      <div v-if="queryError">
        <el-alert :title="queryError" type="error" show-icon :closable="false" />
      </div>

      <el-table v-else :data="queryResult.rows" stripe style="width: 100%;"
        max-height="400" size="small">
        <el-table-column v-for="col in queryResult.columns" :key="col"
          :prop="col" :label="col" min-width="120" show-overflow-tooltip />
      </el-table>
    </div>

    <div v-if="canViewQueries" class="workbench-card">
      <div class="workbench-card-head">
        <div class="workbench-card-title">
          <strong>查询历史</strong>
          <span>最近执行记录会沉淀在这里，方便回看语句与结果规模。</span>
        </div>
      </div>

      <el-table :data="history" stripe v-loading="historyLoading" style="width: 100%;" size="small">
        <el-table-column prop="datasource_name" label="数据源" width="130" />
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag size="small">{{ getDatasourceTypeLabel(row.datasource_db_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="database" label="数据库" width="120" />
        <el-table-column prop="sql_content" label="查询内容" min-width="250" show-overflow-tooltip />
        <el-table-column prop="submitter" label="操作人" width="90" />
        <el-table-column prop="result_count" label="结果行数" width="100" />
        <el-table-column prop="duration_ms" label="耗时" width="90">
          <template #default="{ row }">{{ row.duration_ms }}ms</template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>

      <div class="workbench-pagination">
        <el-pagination v-model:current-page="historyPage" :page-size="20" :total="historyTotal"
          layout="total, prev, pager, next" @current-change="fetchHistory" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getDataSources, getDataSourceDatabases, submitQuery, getQueryOrders } from '@/api/modules/sqlaudit'
import { useAuthStore } from '@/stores/auth'
import { getDatasourceTypeLabel, getQueryPlaceholder } from '@/utils/sqlaudit'

defineProps({
  embedded: {
    type: Boolean,
    default: false,
  },
})

const authStore = useAuthStore()
const datasources = ref([])
const databases = ref([])
const dbLoading = ref(false)

const selectedDs = ref(null)
const selectedDb = ref('')
const sqlContent = ref('')
const submitter = ref(authStore.currentUser?.username || 'admin')
const querying = ref(false)
const queryResult = ref(null)
const queryError = ref('')

const history = ref([])
const historyLoading = ref(false)
const historyPage = ref(1)
const historyTotal = ref(0)
const canViewQueries = computed(() => authStore.hasPermission('sqlaudit.query.view'))
const canExecuteQueries = computed(() => authStore.hasPermission('sqlaudit.query.execute'))
const currentDatasource = computed(() => datasources.value.find(ds => ds.id === selectedDs.value) || null)
const currentDatasourceType = computed(() => currentDatasource.value?.db_type || 'mysql')
const queryPlaceholder = computed(() => getQueryPlaceholder(currentDatasourceType.value))
const queryHint = computed(() => currentDatasourceType.value === 'mongodb'
  ? 'MongoDB 查询支持 find / aggregate / count / distinct 四种命令格式'
  : currentDatasourceType.value === 'postgresql'
    ? 'PostgreSQL 查询仅允许单条 SELECT / WITH / SHOW，使用只读事务'
    : 'MySQL 查询仅允许 SELECT / SHOW / DESC 语句')

const formatTime = (t) => t ? new Date(t).toLocaleString('zh-CN') : ''

const loadDatasources = async () => {
  try {
    const res = await getDataSources({ page_size: 100 })
    datasources.value = (res.results || res).filter(ds => ds.is_active)
  } catch (e) { console.error(e) }
}

const onDsChange = async (dsId) => {
  selectedDb.value = ''
  if (!dsId) { databases.value = []; return }
  dbLoading.value = true
  try {
    const res = await getDataSourceDatabases(dsId)
    databases.value = res.databases || []
  } catch (e) {
    databases.value = []
    ElMessage.warning('获取数据库列表失败')
  } finally { dbLoading.value = false }
}

const handleQuery = async () => {
  if (!sqlContent.value.trim()) return
  querying.value = true
  queryError.value = ''
  queryResult.value = null
  try {
    const res = await submitQuery({
      datasource: selectedDs.value,
      database: selectedDb.value,
      sql_content: sqlContent.value,
      submitter: submitter.value,
    })
    queryResult.value = {
      columns: res.columns,
      rows: res.rows,
      count: res.count,
      duration_ms: res.duration_ms,
    }
    if (canViewQueries.value) fetchHistory()
  } catch (e) {
    queryError.value = e.response?.data?.error || '查询失败'
    if (canViewQueries.value) fetchHistory()
  } finally { querying.value = false }
}

const fetchHistory = async () => {
  if (!canViewQueries.value) return
  historyLoading.value = true
  try {
    const res = await getQueryOrders({ page: historyPage.value })
    history.value = res.results || res
    historyTotal.value = res.count || history.value.length
  } catch (e) { console.error(e) }
  finally { historyLoading.value = false }
}

onMounted(() => {
  loadDatasources()
  if (canViewQueries.value) fetchHistory()
})
</script>

<style scoped>
.query-hint {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.sql-editor-wrapper {
  margin-top: 2px;
}
</style>
