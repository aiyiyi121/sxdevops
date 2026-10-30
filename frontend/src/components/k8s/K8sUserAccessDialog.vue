<template>
  <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="visible" :title="`K8s 授权 · ${user?.username || ''}`" width="min(980px, 94vw)" append-to-body destroy-on-close>
    <div v-loading="loading" class="k8s-access-form">
      <el-alert type="info" :closable="false" show-icon title="集群授权用于收紧平台角色权限；用户仍需在角色中获得对应的 K8s 查看、管理或终端权限。" />
      <el-form label-position="top" label-width="120px">
        <el-form-item label="访问范围">
          <el-radio-group v-model="form.unrestricted" :disabled="saving">
            <el-radio :value="true">沿用平台角色范围</el-radio>
            <el-radio :value="false">仅允许指定集群</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template v-if="!form.unrestricted">
        <div class="access-toolbar">
          <span>命名空间留空表示全部；不添加集群表示禁止访问所有集群。</span>
          <el-button :disabled="saving || form.grants.length >= clusters.length" @click="addGrant">添加集群</el-button>
        </div>
        <el-table :data="form.grants" empty-text="尚未授权集群">
          <el-table-column label="集群" width="205">
            <template #default="{ row }">
              <el-select v-model="row.cluster" :disabled="saving" filterable placeholder="选择集群">
                <el-option v-for="cluster in clusters" :key="cluster.id" :label="cluster.name" :value="cluster.id" :disabled="form.grants.some(item => item !== row && item.cluster === cluster.id)" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="集群角色" width="140">
            <template #default="{ row }">
              <el-select v-model="row.role" :disabled="saving" @change="row.role === 'viewer' && (row.allow_exec = false)">
                <el-option label="只读" value="viewer" /><el-option label="运维" value="operator" /><el-option label="管理员" value="admin" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="命名空间" min-width="260">
            <template #default="{ row }">
              <el-select v-model="row.namespaces" :disabled="saving" multiple filterable allow-create default-first-option placeholder="输入命名空间后按回车；留空为全部" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column label="Pod 终端" width="100">
            <template #default="{ row }"><el-switch v-model="row.allow_exec" :disabled="saving || row.role === 'viewer'" /></template>
          </el-table-column>
          <el-table-column width="65"><template #default="{ $index }"><el-button link type="danger" :disabled="saving" @click="form.grants.splice($index, 1)">移除</el-button></template></el-table-column>
        </el-table>
        <p class="access-note">只读角色仅查询资源；运维角色可在授权命名空间内管理资源；完整集群管理员可维护集群连接、节点调度及使用集群终端。</p>
      </template>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="loading" @click="save">保存授权</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getUserK8sAccess, updateUserK8sAccess } from '@/api/modules/rbac'
const visible = ref(false)
const loading = ref(false)
const saving = ref(false)
const user = ref(null)
const clusters = ref([])
const form = ref({ unrestricted: true, grants: [] })
async function open(row) {
  user.value = row
  visible.value = true
  loading.value = true
  form.value = { unrestricted: true, grants: [] }
  clusters.value = []
  try {
    const data = await getUserK8sAccess(row.id)
    form.value = { unrestricted: data.unrestricted, grants: data.grants }
    clusters.value = data.clusters
  } catch {
    visible.value = false
  } finally {
    loading.value = false
  }
}
function addGrant() {
  const cluster = clusters.value.find(item => !form.value.grants.some(grant => grant.cluster === item.id))
  if (cluster) form.value.grants.push({ cluster: cluster.id, role: 'viewer', namespaces: [], allow_exec: false })
}
async function save() {
  if (saving.value || loading.value) return
  saving.value = true
  try {
    await updateUserK8sAccess(user.value.id, form.value)
    ElMessage.success('K8s 授权已保存')
    visible.value = false
  } finally {
    saving.value = false
  }
}
defineExpose({ open })
</script>

<style scoped>
.k8s-access-form { display: flex; flex-direction: column; gap: 14px; }
.access-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--text-secondary); font-size: 13px; }
.access-note { margin: 0; color: var(--text-secondary); font-size: 12px; line-height: 1.7; }
</style>
