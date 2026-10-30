<template>
  <div class="fade-in workbench-page-shell">
    <div class="workbench-card">
      <div class="workbench-card-head">
        <div class="workbench-card-title">
          <strong>数据源清单</strong>
          <span>维护连接、账号与启停状态，供工单与查询页复用。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button v-if="canManageSqlDatasources" type="primary" @click="openDialog()">
            <el-icon><Plus /></el-icon> 新增数据源
          </el-button>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history">
        <div class="workbench-toolbar-left">
          <el-input v-model="search" placeholder="搜索名称 / 地址" clearable style="width: 280px"
            :prefix-icon="Search" @input="fetchData" />
        </div>
      </div>

      <el-table :data="items" stripe v-loading="loading" style="width: 100%">
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ getDatasourceTypeLabel(row.db_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="连接地址" min-width="200">
          <template #default="{ row }">
            <span>{{ row.host }}:{{ row.port }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="user" label="用户名" width="120" />
        <el-table-column label="字符集" width="100">
          <template #default="{ row }">{{ row.db_type === 'mongodb' ? '-' : row.charset }}</template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
        <el-table-column v-if="canManageSqlDatasources" label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="success" size="small" @click="handleTest(row)" :loading="testingId === row.id">
              测试连接
            </el-button>
            <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
            <el-popconfirm title="确定删除此数据源？" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button link type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div class="workbench-pagination">
        <el-pagination v-model:current-page="page" :page-size="20" :total="total"
          layout="total, prev, pager, next" @current-change="fetchData" />
      </div>
    </div>

    <el-dialog :close-on-click-modal="false" class="workbench-edit-dialog" v-model="dialogVisible" :title="editingId ? '编辑数据源' : '新增数据源'" width="90%" style="max-width:560px;" top="5vh" append-to-body destroy-on-close>
      <el-form class="workbench-editor-form--sectioned" label-position="top" :model="form" label-width="90px">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>数据源信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="数据库类型">
              <el-select v-model="form.db_type" style="width:100%" @change="handleTypeChange">
                <el-option v-for="option in DATASOURCE_TYPE_OPTIONS" :key="option.value" :label="option.label" :value="option.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="名称">
              <el-input v-model="form.name" placeholder="例如 prod-db-master" />
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>连接与认证</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="主机地址">
              <el-input v-model="form.host" placeholder="例如 192.168.1.100" />
            </el-form-item>
            <el-form-item label="端口">
              <el-input-number v-model="form.port" :min="1" :max="65535" style="width:100%" />
            </el-form-item>
            <el-form-item label="用户名">
              <el-input v-model="form.user" :placeholder="form.db_type === 'mongodb' ? '例如 admin' : '例如 root'" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="form.password" type="password" show-password
            :placeholder="editingId ? '留空则不修改' : '请输入密码'" />
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">03</span><h3>其他设置</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="字符集">
              <el-select v-model="form.charset" style="width:100%" :disabled="form.db_type === 'mongodb'">
                <el-option label="utf8mb4" value="utf8mb4" />
                <el-option label="utf8" value="utf8" />
                <el-option label="latin1" value="latin1" />
                <el-option label="gbk" value="gbk" />
              </el-select>
            </el-form-item>
            <el-form-item label="状态">
              <el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" />
            </el-form-item>
            <el-form-item class="workbench-editor-full" label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  getDataSources, createDataSource, updateDataSource,
  deleteDataSource, testDataSourceConnection,
} from '@/api/modules/sqlaudit'
import { useAuthStore } from '@/stores/auth'
import {
  DATASOURCE_TYPE_OPTIONS,
  getDatasourceDefaultPort,
  getDatasourceTypeLabel,
} from '@/utils/sqlaudit'

defineProps({
  embedded: {
    type: Boolean,
    default: false,
  },
})

const authStore = useAuthStore()
const items = ref([])
const loading = ref(false)
const search = ref('')
const page = ref(1)
const total = ref(0)
const testingId = ref(null)

const dialogVisible = ref(false)
const editingId = ref(null)
const saving = ref(false)
const defaultForm = {
  db_type: 'mysql', name: '', host: '', port: 3306, user: 'root',
  password: '', charset: 'utf8mb4', is_active: true, remark: '',
}
const form = ref({ ...defaultForm })
const canManageSqlDatasources = computed(() => authStore.hasPermission('sqlaudit.datasource.manage'))

const fetchData = async () => {
  loading.value = true
  try {
    const params = { page: page.value }
    if (search.value) params.search = search.value
    const res = await getDataSources(params)
    items.value = res.results || res
    total.value = res.count || items.value.length
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

const openDialog = (row) => {
  if (row) {
    editingId.value = row.id
    form.value = {
      db_type: row.db_type || 'mysql',
      name: row.name, host: row.host, port: row.port,
      user: row.user, password: '', charset: row.charset,
      is_active: row.is_active, remark: row.remark,
    }
  } else {
    editingId.value = null
    form.value = { ...defaultForm }
  }
  dialogVisible.value = true
}

const handleTypeChange = (nextType) => {
  const currentPort = form.value.port
  const useDefaultPort = !editingId.value || currentPort === 3306 || currentPort === 27017
  form.value.db_type = nextType
  if (useDefaultPort) {
    form.value.port = getDatasourceDefaultPort(nextType)
  }
  if (nextType === 'mongodb') {
    form.value.charset = 'utf8mb4'
  }
}

const handleSave = async () => {
  saving.value = true
  try {
    const data = { ...form.value }
    if (editingId.value && !data.password) {
      delete data.password
    }
    if (editingId.value) {
      await updateDataSource(editingId.value, data)
      ElMessage.success('更新成功')
    } else {
      await createDataSource(data)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    fetchData()
  } catch (e) { console.error(e) }
  finally { saving.value = false }
}

const handleDelete = async (id) => {
  try {
    await deleteDataSource(id)
    ElMessage.success('删除成功')
    fetchData()
  } catch (e) { console.error(e) }
}

const handleTest = async (row) => {
  testingId.value = row.id
  try {
    const res = await testDataSourceConnection(row.id)
    if (res.success) {
      ElMessage.success(res.message)
    } else {
      ElMessage.error(res.message)
    }
  } catch (e) {
    ElMessage.error('测试请求失败')
  } finally {
    testingId.value = null
  }
}

onMounted(fetchData)
</script>

<style scoped>
</style>


