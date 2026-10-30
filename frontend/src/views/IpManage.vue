<template>
  <div class="fade-in ipam-page workbench-page-shell">
    <CmdbPlatformHeader />

    <div class="neo-tabs theme-blue ipam-tabs">
      <button type="button" class="neo-tab-btn" :class="{ active: activeTab === 'pool' }" @click="openPoolTab">
        <el-icon><DataBoard /></el-icon>地址池详情
      </button>
      <button type="button" class="neo-tab-btn" :class="{ active: activeTab === 'subnets' }" @click="activeTab = 'subnets'">
        <el-icon><Grid /></el-icon>子网管理
      </button>
    </div>

    <section v-if="activeTab === 'subnets'" class="workbench-card">
      <div class="section-toolbar">
        <div class="toolbar-head"><span class="toolbar-title">子网管理</span><span class="toolbar-desc">添加需要管理的网段，扫描会保留 CMDB 已登记的停机虚拟机地址。</span></div>
        <el-button v-if="canManage" type="primary" @click="openSubnetDialog()"><el-icon><Plus /></el-icon>添加 IPv4 子网</el-button>
      </div>
      <div class="workbench-toolbar workbench-toolbar--history">
        <div class="workbench-toolbar-left"><el-input v-model="subnetSearch" clearable placeholder="搜索子网名称、CIDR、VLAN" style="width: 280px" /></div>
        <div class="workbench-toolbar-right"><el-button class="filter-refresh-btn" :loading="loading" @click="fetchSubnets"><el-icon><RefreshRight /></el-icon>刷新</el-button></div>
      </div>
      <el-table v-loading="loading" :data="filteredSubnets" stripe style="width: 100%">
        <el-table-column label="子网" min-width="220">
          <template #default="{ row }"><div class="subnet-cell"><strong>{{ row.cidr }}</strong><span>{{ row.name }}</span></div></template>
        </el-table-column>
        <el-table-column label="网络信息" min-width="190"><template #default="{ row }"><div>{{ row.vlan_name || '未设置 VLAN / Port Group' }}</div><span class="sub-text">网关：{{ row.gateway || '-' }}</span></template></el-table-column>
        <el-table-column label="地址池" min-width="230"><template #default="{ row }"><div class="usage-line"><el-progress :percentage="usagePercent(row)" :stroke-width="8" :show-text="false" /><span>{{ row.in_use_count + row.offline_count }}/{{ row.address_total }}</span></div><span class="sub-text">空闲 {{ row.available_count }} · 停机 {{ row.offline_count }} · 保留 {{ row.reserved_count }}</span></template></el-table-column>
        <el-table-column label="最近扫描" width="176"><template #default="{ row }"><el-tag v-if="row.last_scanned_at" size="small" type="success">已扫描</el-tag><el-tag v-else size="small" type="info">未扫描</el-tag><div class="sub-text scan-time">{{ formatTime(row.last_scanned_at) }}</div></template></el-table-column>
        <el-table-column label="操作" width="250" fixed="right"><template #default="{ row }"><el-button link type="primary" size="small" @click="openAddressPool(row)">查看详情</el-button><el-button v-if="canManage" link type="success" size="small" :loading="scanningId === row.id" @click="scanSubnet(row)">扫描</el-button><el-button v-if="canManage" link type="primary" size="small" @click="openSubnetDialog(row)">编辑</el-button><el-button v-if="canManage" link type="danger" size="small" @click="removeSubnet(row)">删除</el-button></template></el-table-column>
      </el-table>
    </section>

    <section v-else class="workbench-card pool-card">
      <div class="section-toolbar">
        <div class="toolbar-head"><span class="toolbar-title">地址池详情</span><span class="toolbar-desc">{{ activeSubnet ? `${activeSubnet.name} · ${activeSubnet.cidr} · ${activeSubnet.vlan_name || '未设置 VLAN / Port Group'}` : '请选择需要查看的子网' }}</span></div>
        <div class="pool-actions"><el-button v-if="canManage" type="primary" :disabled="!activeSubnet" :loading="scanningId === activeSubnet?.id" @click="scanSubnet(activeSubnet)"><el-icon><RefreshRight /></el-icon>重新扫描当前地址池</el-button></div>
      </div>
      <div class="workbench-toolbar workbench-toolbar--history">
        <div class="workbench-toolbar-left"><el-select :model-value="activeSubnet?.id" placeholder="筛选子网" style="width: 250px" @update:model-value="selectPoolSubnet"><el-option v-for="subnet in subnets" :key="subnet.id" :label="`${subnet.cidr} · ${subnet.name}`" :value="subnet.id" /></el-select><el-select v-model="poolStatusFilter" clearable placeholder="全部地址" style="width: 116px"><el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select><el-input v-model="poolSearch" clearable placeholder="搜索 IP 或关联资产" style="width: 230px" /></div>
        <div class="workbench-toolbar-right"><span class="scan-note">CMDB 中状态为停机且保留了历史 IP 记录的地址，会标记为停机。</span></div>
      </div>
      <div class="pool-summary"><span><i class="dot dot--available" />空闲 {{ poolSummary.available || 0 }}</span><span><i class="dot dot--in-use" />使用中 {{ poolSummary.in_use || 0 }}</span><span><i class="dot dot--offline" />停机 {{ poolSummary.offline || 0 }}</span><span><i class="dot dot--reserved" />保留 {{ poolSummary.reserved || 0 }}</span></div>
      <div v-loading="poolLoading" class="address-grid">
        <button v-for="address in filteredAddresses" :key="address.address" type="button" class="address-cell" :class="[`address-cell--${address.status}`, { active: selectedAddress?.address === address.address }]" @click="selectedAddress = address">
          <span>{{ address.address.split('.').pop() }}</span>
        </button>
      </div>
      <div v-if="selectedAddress" class="address-detail">
        <div><span class="detail-label">IP 地址</span><strong>{{ selectedAddress.address }}</strong></div>
        <div><span class="detail-label">状态</span><el-tag size="small" :type="statusTagType(selectedAddress.status)">{{ statusLabel(selectedAddress.status) }}</el-tag></div>
        <div><span class="detail-label">扫描</span><span>{{ reachabilityLabel(selectedAddress.reachability) }}</span></div>
        <div><span class="detail-label">关联资产</span><span>{{ selectedAddress.linked_ci_names?.join('、') || selectedAddress.ci_name || '未关联 CMDB 资产' }}</span></div>
      </div>
    </section>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="subnetDialogVisible" :title="editingSubnet ? '编辑子网' : '添加 IPv4 子网'" width="620px" append-to-body>
      <el-form label-position="top" :model="subnetForm" class="subnet-form" label-width="132px">
        <el-form-item label="子网名称" required><el-input v-model="subnetForm.name" placeholder="例如 production-app-net" /></el-form-item>
        <el-form-item label="CIDR 网段" required><el-input v-model="subnetForm.cidr" placeholder="例如 10.20.1.0/24" /></el-form-item>
        <el-form-item label="VLAN / Port Group"><el-input v-model="subnetForm.vlan_name" placeholder="例如 PG-业务网-VLAN120" /></el-form-item>
        <el-form-item label="网关"><el-input v-model="subnetForm.gateway" placeholder="例如 10.20.1.1" /></el-form-item>
        <el-form-item label="保留地址"><el-input v-model="subnetForm.excluded_text" placeholder="以逗号分隔，例如 10.20.1.2, 10.20.1.3" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="subnetForm.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="subnetDialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveSubnet">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { DataBoard, Grid, Plus, RefreshRight } from '@element-plus/icons-vue'
import CmdbPlatformHeader from '@/components/cmdb/CmdbPlatformHeader.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { can } from '@/utils/permission'
import { createIPSubnet, deleteIPSubnet, getIPSubnetAddresses, getIPSubnets, scanIPSubnet, updateIPSubnet } from '@/api/modules/cmdb'

const loading = ref(false)
const poolLoading = ref(false)
const saving = ref(false)
const scanningId = ref(null)
const subnets = ref([])
const activeTab = ref('pool')
const activeSubnet = ref(null)
const pendingPoolSubnetId = ref(null)
const addresses = ref([])
const poolSummary = ref({})
const selectedAddress = ref(null)
const subnetSearch = ref('')
const poolSearch = ref('')
const poolStatusFilter = ref('')
const subnetDialogVisible = ref(false)
const editingSubnet = ref(null)
const subnetForm = ref(emptyForm())
const canManage = computed(() => can('cmdb.ipam.manage'))
const statusOptions = [
  { value: 'available', label: '空闲' }, { value: 'in_use', label: '使用中' }, { value: 'offline', label: '停机' }, { value: 'reserved', label: '已保留' },
]
const viewStateKey = 'sxdevops:ipam-view-state'

function emptyForm() { return { name: '', cidr: '', vlan_name: '', gateway: '', excluded_text: '', description: '' } }
function asList(data) { return Array.isArray(data) ? data : (data?.results || []) }
function formatTime(value) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '尚未扫描' }
function usagePercent(row) { return row.address_total ? Math.round(((row.in_use_count + row.offline_count + row.reserved_count) / row.address_total) * 100) : 0 }
function statusLabel(value) { return statusOptions.find(item => item.value === value)?.label || value }
function reachabilityLabel(value) { return ({ reachable: '可达', unreachable: '不通', unknown: '未扫描' })[value] || '未扫描' }
function statusTagType(value) { return ({ available: 'success', in_use: '', offline: 'warning', reserved: 'info' })[value] || 'info' }

const filteredSubnets = computed(() => {
  const keyword = subnetSearch.value.trim().toLowerCase()
  return subnets.value.filter((row) => {
    const matchesKeyword = !keyword || [row.name, row.cidr, row.vlan_name].some(value => String(value || '').toLowerCase().includes(keyword))
    return matchesKeyword
  })
})
const filteredAddresses = computed(() => addresses.value.filter((row) => {
  const keyword = poolSearch.value.trim().toLowerCase()
  return (!poolStatusFilter.value || row.status === poolStatusFilter.value) && (!keyword || row.address.includes(keyword) || (row.linked_ci_names || []).join(' ').toLowerCase().includes(keyword) || String(row.ci_name || '').toLowerCase().includes(keyword))
}))

async function fetchSubnets() { loading.value = true; try { subnets.value = asList(await getIPSubnets()); if (activeTab.value === 'pool' && !activeSubnet.value && subnets.value.length) { const target = subnets.value.find(item => String(item.id) === String(pendingPoolSubnetId.value)) || subnets.value[0]; pendingPoolSubnetId.value = null; await selectPoolSubnet(target.id) } } catch (error) { ElMessage.error(error?.response?.data?.detail || '加载子网失败') } finally { loading.value = false } }
async function loadAddresses() { if (!activeSubnet.value) return; poolLoading.value = true; try { const data = await getIPSubnetAddresses(activeSubnet.value.id); activeSubnet.value = data.subnet; poolSummary.value = data.summary || {}; addresses.value = data.items || []; selectedAddress.value = addresses.value.find(item => item.address === selectedAddress.value?.address) || addresses.value[0] || null } catch (error) { ElMessage.error(error?.response?.data?.detail || '加载地址池失败') } finally { poolLoading.value = false } }
async function openAddressPool(row) { activeSubnet.value = row; activeTab.value = 'pool'; selectedAddress.value = null; await loadAddresses() }
async function selectPoolSubnet(subnetId) { const subnet = subnets.value.find(item => item.id === subnetId); if (!subnet || subnet.id === activeSubnet.value?.id) return; activeSubnet.value = subnet; selectedAddress.value = null; poolSearch.value = ''; poolStatusFilter.value = ''; await loadAddresses() }
async function openPoolTab() { activeTab.value = 'pool'; if (!activeSubnet.value && subnets.value.length) await selectPoolSubnet(subnets.value[0].id) }
async function scanSubnet(row) { if (!row) return; scanningId.value = row.id; try { await scanIPSubnet(row.id); ElMessage.success(`${row.cidr} 扫描完成`); await Promise.all([fetchSubnets(), activeSubnet.value?.id === row.id ? loadAddresses() : Promise.resolve()]) } catch (error) { ElMessage.error(error?.response?.data?.detail || '扫描失败') } finally { scanningId.value = null } }
function openSubnetDialog(row = null) { editingSubnet.value = row; subnetForm.value = row ? { ...row, excluded_text: (row.excluded_addresses || []).join(', ') } : emptyForm(); subnetDialogVisible.value = true }
async function saveSubnet() { if (!subnetForm.value.name || !subnetForm.value.cidr) { ElMessage.warning('请填写子网名称和 CIDR 网段'); return } saving.value = true; const payload = { name: subnetForm.value.name, cidr: subnetForm.value.cidr, vlan_name: subnetForm.value.vlan_name, gateway: subnetForm.value.gateway, description: subnetForm.value.description, excluded_addresses: subnetForm.value.excluded_text.split(/[,\n]/).map(value => value.trim()).filter(Boolean) }; try { if (editingSubnet.value) await updateIPSubnet(editingSubnet.value.id, payload); else await createIPSubnet(payload); subnetDialogVisible.value = false; ElMessage.success('子网已保存'); await fetchSubnets() } catch (error) { const detail = error?.response?.data; ElMessage.error(typeof detail === 'string' ? detail : Object.values(detail || {})[0]?.[0] || '保存失败') } finally { saving.value = false } }
async function removeSubnet(row) { try { await ElMessageBox.confirm(`删除 ${row.cidr} 后会一并移除扫描结果，确定继续吗？`, '删除子网', { type: 'warning' }); await deleteIPSubnet(row.id); ElMessage.success('子网已删除'); if (activeSubnet.value?.id === row.id) activeTab.value = 'subnets'; await fetchSubnets() } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(error?.response?.data?.detail || '删除失败') } }

watch([activeTab, () => activeSubnet.value?.id], () => {
  window.sessionStorage.setItem(viewStateKey, JSON.stringify({ tab: activeTab.value, subnetId: activeSubnet.value?.id || null }))
})

onMounted(async () => {
  try {
    const viewState = JSON.parse(window.sessionStorage.getItem(viewStateKey) || 'null')
    if (viewState?.tab === 'pool') {
      activeTab.value = 'pool'
      pendingPoolSubnetId.value = viewState.subnetId
    }
  } catch (_) {
    window.sessionStorage.removeItem(viewStateKey)
  }
  await fetchSubnets()
})
</script>

<style scoped>
.ipam-page { display: flex; flex-direction: column; gap: 6px; }
.panel, .workbench-card { background: linear-gradient(180deg, rgba(255,255,255,.98), rgba(250,252,255,.96)); border: 1px solid rgba(15,23,42,.08); box-shadow: 0 8px 24px rgba(15,23,42,.04); }
.panel { padding: 14px 16px; border-radius: 18px; }
.hero.panel { border-radius: 20px; background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%); border-color: rgba(36,91,219,.09); }
.release-hero-title-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.release-hero-title-row h2 { margin: 0; color: #0f172a; font-size: 23px; }
.release-header-icon { width: 42px; height: 42px; border-radius: 14px; display: inline-flex; align-items: center; justify-content: center; font-size: 20px; color: #245bdb; background: linear-gradient(180deg,#f3f7ff,#ebf2ff); border: 1px solid rgba(36,91,219,.12); }
.page-inline-desc, .toolbar-desc, .sub-text, .scan-note { color: #64748b; font-size: 13px; }
.page-inline-desc { margin: 0; }
.ipam-tabs { display: flex; width: 100%; margin: 0; padding: 3px; gap: 8px; border: 1px solid rgba(148,163,184,.16); border-radius: 12px; background: #fff; box-shadow: 0 12px 26px rgba(15,23,42,.04); overflow: auto; }.neo-tab-btn { min-height: 38px; padding: 0 18px; display: inline-flex; align-items: center; gap: 6px; border: 0; border-radius: 8px; background: transparent; color: #475569; font-size: 13px; font-weight: 700; line-height: 1.2; white-space: nowrap; cursor: pointer; }.neo-tab-btn .el-icon { font-size: 15px; }.neo-tab-btn:hover { background: rgba(51,112,255,.06); color: #245bdb; }.neo-tab-btn.active { color: #245bdb; background: #e8f0ff; box-shadow: inset 0 0 0 1px rgba(51,112,255,.1); }.neo-tab-btn:disabled { cursor: not-allowed; opacity: .45; }
.workbench-card { border-radius: 14px; padding: 14px 16px; overflow: hidden; }.section-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }.toolbar-head { display: inline-flex; align-items: baseline; flex-wrap: wrap; gap: 8px; }.toolbar-title { font-size: 15px; font-weight: 800; color: #0f172a; }.workbench-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 10px; padding: 8px; border: 1px solid rgba(148,163,184,.16); border-radius: 10px; background: #f8fafc; }.workbench-toolbar-left, .workbench-toolbar-right, .pool-actions { display: flex; align-items: center; gap: 8px; }.subnet-cell { display: grid; gap: 4px; }.subnet-cell strong { color: #245bdb; }.usage-line { display: flex; gap: 10px; align-items: center; }.usage-line .el-progress { width: 118px; }.scan-time { margin-top: 5px; }
.pool-card { min-height: 500px; }.pool-summary { display: flex; flex-wrap: wrap; gap: 18px; padding: 12px 16px; font-size: 13px; color: #475569; }.dot { width: 9px; height: 9px; display: inline-block; border-radius: 3px; margin-right: 5px; }.dot--available { background: #4fd18b; }.dot--in-use { background: #3b82f6; }.dot--offline { background: #f5a524; }.dot--reserved { background: #94a3b8; }
.address-grid { padding: 16px; display: grid; grid-template-columns: repeat(auto-fill, minmax(46px, 1fr)); gap: 8px; border-top: 1px solid rgba(15,23,42,.06); }.address-cell { min-height: 32px; border: 0; border-radius: 6px; font-weight: 700; color: #fff; cursor: pointer; box-shadow: 0 2px 5px rgba(15,23,42,.09); }.address-cell--available { background: #4fd18b; }.address-cell--in_use { background: #3b82f6; }.address-cell--offline { background: #f5a524; }.address-cell--reserved { background: #94a3b8; }.address-cell.active { outline: 3px solid rgba(36,91,219,.2); outline-offset: 2px; }
.address-detail { margin: 0 16px 16px; padding: 13px 16px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; border: 1px solid rgba(36,91,219,.12); border-radius: 12px; background: #f8fbff; font-size: 13px; color: #334155; }.address-detail > div { min-width: 0; display: grid; gap: 5px; }.detail-label { color: #94a3b8; font-size: 12px; }.address-detail strong { color: #245bdb; }
.subnet-form :deep(.el-form-item__label) { white-space: nowrap; }
@media (max-width: 840px) { .section-toolbar, .workbench-toolbar { align-items: flex-start; flex-direction: column; }.address-detail { grid-template-columns: repeat(2, minmax(0, 1fr)); }.address-grid { grid-template-columns: repeat(auto-fill, minmax(38px, 1fr)); } }
</style>
