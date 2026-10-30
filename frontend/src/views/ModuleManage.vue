<template>
  <div class="fade-in module-manage-page workbench-page-shell">
    <section class="hero panel">
      <div class="release-hero-copy">
        <div class="release-hero-title-row">
          <span class="release-header-icon"><el-icon><Menu /></el-icon></span>
          <h2>系统设置</h2>
          <p class="page-inline-desc">配置网站名称、图标，以及菜单顺序、显示状态与登录默认页。</p>
        </div>
      </div>
    </section>

    <section v-loading="siteLoading" class="workbench-card site-settings-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">基础配置</span>
          <span class="toolbar-desc">统一设置侧栏、登录页与浏览器标签页的网站标识。</span>
        </div>
        <div v-if="canManageModules" class="workbench-card-actions">
          <el-button :disabled="siteLoading || siteSaving || !siteLoaded" @click="restoreSiteDefaults">恢复默认</el-button>
          <el-button type="primary" :loading="siteSaving" :disabled="siteLoading || !siteLoaded" @click="saveSiteSettings">
            <el-icon><Check /></el-icon>
            保存配置
          </el-button>
        </div>
      </div>
      <el-form :model="siteForm" class="site-settings-form" label-position="left" label-width="76px" :disabled="!canManageModules || siteLoading || siteSaving || !siteLoaded" @submit.prevent="saveSiteSettings">
        <el-form-item label="网站名称" class="site-name-field">
          <el-input v-model="siteForm.site_name" maxlength="10" show-word-limit placeholder="请输入网站名称" aria-label="网站名称" />
        </el-form-item>
        <el-form-item label="网站图标" class="site-icon-field">
          <div class="site-icon-controls">
            <span class="site-icon-preview"><img :src="iconPreview" alt="网站图标预览" /></span>
            <div class="site-icon-actions">
              <el-button :icon="Upload" @click="siteIconInput?.click()">上传图标</el-button>
              <el-button :disabled="!selectedIcon && !siteStore.customIconUrl" @click="restoreDefaultIcon">恢复默认图标</el-button>
            </div>
            <span class="site-icon-hint">PNG、JPG、WebP 或 ICO，最大 1 MB，建议使用正方形透明图标。</span>
          </div>
        </el-form-item>
      </el-form>
      <input ref="siteIconInput" type="file" accept=".png,.jpg,.jpeg,.webp,.ico" class="site-icon-file" aria-label="选择网站图标文件" @change="handleIconSelected" />
    </section>

    <div class="workbench-card module-content-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">菜单配置</span>
          <span class="toolbar-desc">上移、下移调整同级菜单顺序，保存后生效；一级菜单连同子菜单一起移动。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button :disabled="loading || saving" @click="resetMenuOrder">恢复默认顺序</el-button>
          <el-button class="filter-refresh-btn" :loading="loading" @click="fetchSettings">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
          <el-button type="primary" :loading="saving" @click="handleSave">
            <el-icon><Check /></el-icon>
            保存配置
          </el-button>
        </div>
      </div>

      <el-table
        v-loading="loading"
        :data="modules"
        :row-class-name="getModuleRowClass"
        style="width: 100%"
        class="module-table"
      >
        <el-table-column label="菜单模块" min-width="220">
          <template #default="{ row }">
            <div class="module-name-cell" :class="{ 'module-name-cell--child': row.level === 2 }">
              <span class="module-name">{{ row.title }}{{ row.incomplete ? '（待完善）' : '' }}</span>
              <span class="module-code">{{ row.code }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="280" show-overflow-tooltip />
        <el-table-column label="配置类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="getConfigTypeTag(row)">
              {{ getConfigTypeLabel(row) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="显示状态" width="120">
          <template #default="{ row }">
            <el-switch
              v-model="row.enabled"
              inline-prompt
              active-text="显示"
              inactive-text="隐藏"
              :disabled="row.required"
            />
          </template>
        </el-table-column>
        <el-table-column label="菜单顺序" width="140" align="center">
          <template #default="{ row }">
            <span v-if="row.config_type === 'floating_entry'" class="default-page-empty">-</span>
            <div v-else class="module-order-actions">
              <el-button text size="small" :icon="ArrowUp" :disabled="saving || !canMoveModule(row, -1)" :aria-label="`上移${row.title}`" @click="moveModule(row, -1)" />
              <el-button text size="small" :icon="ArrowDown" :disabled="saving || !canMoveModule(row, 1)" :aria-label="`下移${row.title}`" @click="moveModule(row, 1)" />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="登录默认页" width="140" align="center">
          <template #default="{ row }">
            <span v-if="!row.path" class="default-page-empty">-</span>
            <el-button
              v-else-if="row.is_default"
              class="default-page-button is-current"
              type="primary"
              plain
              size="small"
              disabled
            >
              当前默认
            </el-button>
            <el-button
              v-else
              class="default-page-button"
              size="small"
              :disabled="!canSetDefault(row)"
              @click="handleSetDefault(row)"
            >
              设为默认
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="最近更新" width="180">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="更新人" width="120">
          <template #default="{ row }">{{ row.updated_by || '-' }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, ArrowUp, Check, Menu, RefreshRight, Upload } from '@element-plus/icons-vue'
import { getModuleSettings, updateModuleSettings } from '@/api/modules/rbac'
import { useAuthStore } from '@/stores/auth'
import { DEFAULT_SITE_NAME, defaultSiteIcon, useSiteStore } from '@/stores/site'

const authStore = useAuthStore()
const siteStore = useSiteStore()
const canManageModules = computed(() => authStore.hasPermission('rbac.module.manage'))
const loading = ref(false)
const saving = ref(false)
const modules = ref([])
const siteLoading = ref(false)
const siteLoaded = ref(false)
const siteSaving = ref(false)
const siteIconInput = ref(null)
const siteForm = reactive({ site_name: siteStore.siteName })
const selectedIcon = ref(null)
const previewUrl = ref('')
const resetIcon = ref(false)
const iconPreview = computed(() => previewUrl.value || (resetIcon.value ? defaultSiteIcon : siteStore.siteIcon))

function clearSelectedIcon() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  selectedIcon.value = null
  if (siteIconInput.value) siteIconInput.value.value = ''
}

function handleIconSelected(event) {
  if (!canManageModules.value || siteSaving.value || !siteLoaded.value) return
  const file = event.target.files?.[0]
  if (!file) return
  event.target.value = ''
  if (!/\.(png|jpe?g|webp|ico)$/i.test(file.name)) {
    ElMessage.warning('请选择 PNG、JPG、WebP 或 ICO 图标')
    return
  }
  if (file.size > 1024 * 1024) {
    ElMessage.warning('图标大小不能超过 1 MB')
    return
  }
  clearSelectedIcon()
  selectedIcon.value = file
  previewUrl.value = URL.createObjectURL(file)
  resetIcon.value = false
}

function restoreDefaultIcon() {
  clearSelectedIcon()
  resetIcon.value = true
}

function restoreSiteDefaults() {
  siteForm.site_name = DEFAULT_SITE_NAME
  restoreDefaultIcon()
}

async function fetchSiteSettings() {
  siteLoading.value = true
  try {
    const settings = await siteStore.load({ silent: false })
    siteForm.site_name = settings.site_name
    siteLoaded.value = true
  } finally {
    siteLoading.value = false
  }
}

async function saveSiteSettings() {
  if (!canManageModules.value || siteLoading.value || siteSaving.value || !siteLoaded.value) return
  const siteName = siteForm.site_name.trim()
  if (!siteName) {
    ElMessage.warning('请输入网站名称')
    return
  }
  if (siteName.length > 10) {
    ElMessage.warning('网站名称最多 10 个字符')
    return
  }
  const data = new FormData()
  data.append('site_name', siteName)
  data.append('reset_icon', String(resetIcon.value))
  if (selectedIcon.value) data.append('icon', selectedIcon.value)
  siteSaving.value = true
  try {
    const settings = await siteStore.save(data)
    siteForm.site_name = settings.site_name
    clearSelectedIcon()
    resetIcon.value = false
    ElMessage.success('网站基础配置已保存')
  } finally {
    siteSaving.value = false
  }
}

function normalizeModules(list = []) {
  const normalized = list.map(item => ({
    ...item,
    enabled: item.required ? true : item.enabled !== false,
  }))
  if (!normalized.some(item => item.is_default)) {
    const dashboard = normalized.find(item => item.code === 'dashboard')
    if (dashboard) dashboard.is_default = true
  }
  return orderModules(normalized)
}

function orderModules(list) {
  const sorted = list.slice().sort((first, second) => first.sort_order - second.sort_order || first.default_sort_order - second.default_sort_order)
  return sorted.filter(item => !item.parent_code).flatMap(parent => [parent, ...sorted.filter(item => item.parent_code === parent.code)])
}

function moduleSiblings(row) {
  return modules.value.filter(item => (item.parent_code || '') === (row.parent_code || '') && item.config_type !== 'floating_entry')
}

function canMoveModule(row, direction) {
  const siblings = moduleSiblings(row)
  const nextIndex = siblings.findIndex(item => item.code === row.code) + direction
  return nextIndex >= 0 && nextIndex < siblings.length
}

function moveModule(row, direction) {
  if (!canMoveModule(row, direction)) return
  const siblings = moduleSiblings(row)
  const index = siblings.findIndex(item => item.code === row.code)
  const targetIndex = index + direction
  const target = siblings[targetIndex]
  siblings[targetIndex] = siblings[index]
  siblings[index] = target
  siblings.forEach((item, position) => { item.sort_order = (position + 1) * 10 })
  modules.value = orderModules(modules.value)
}

function resetMenuOrder() {
  modules.value.forEach(item => { item.sort_order = item.default_sort_order })
  modules.value = orderModules(modules.value)
}

async function fetchSettings() {
  loading.value = true
  try {
    modules.value = normalizeModules(await getModuleSettings())
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    const modulePayload = modules.value.map(item => ({
      code: item.code,
      enabled: item.required ? true : item.enabled,
      sort_order: item.sort_order,
    }))
    const selectedDefault = modules.value.find(item => item.is_default && canSetDefault(item))
    const response = await updateModuleSettings({
      modules: modulePayload,
      default_code: selectedDefault?.code || 'dashboard',
    })
    modules.value = normalizeModules(response.data || response || [])
    authStore.setModuleSettings(modules.value)
    window.dispatchEvent(new Event('sxdevops-module-settings-updated'))
    ElMessage.success('菜单顺序、显示状态与登录默认页已保存')
  } finally {
    saving.value = false
  }
}

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN', { hour12: false })
}

function canSetDefault(row) {
  if (!row?.path || row.enabled === false) return false
  if (!row.parent_code) return true
  const parent = modules.value.find(item => item.code === row.parent_code)
  return parent?.enabled !== false
}

function handleSetDefault(row) {
  if (!canSetDefault(row)) return
  modules.value.forEach((item) => {
    item.is_default = item.code === row.code
  })
}

function getConfigTypeLabel(row) {
  if (row.required) return '固定显示'
  if (row.config_type === 'floating_entry') return '悬浮入口'
  return row.level === 1 ? '一级菜单' : '二级菜单'
}

function getConfigTypeTag(row) {
  if (row.required) return 'info'
  return row.config_type === 'floating_entry' ? 'warning' : 'success'
}

function getModuleRowClass({ row }) {
  return row.level === 1 ? 'module-table__row--parent' : 'module-table__row--child'
}

onMounted(fetchSettings)
onMounted(fetchSiteSettings)
onBeforeUnmount(clearSelectedIcon)
</script>

<style scoped>
.module-manage-page {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.panel {
  background: linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(250,252,255,.96) 100%);
  border: 1px solid rgba(15,23,42,.08);
  border-radius: 18px;
  box-shadow: 0 8px 24px rgba(15,23,42,.04);
  padding: 14px 16px;
}

.hero {
  margin-bottom: 0;
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36,91,219,.09);
}

.release-hero-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.release-hero-title-row h2 {
  color: #0f172a;
  font-size: 23px;
  margin: 0;
}

.release-header-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #245bdb;
  background: linear-gradient(180deg,#f3f7ff 0%,#ebf2ff 100%);
  border: 1px solid rgba(36,91,219,.12);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.8);
}

.page-inline-desc {
  color: #475569;
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
  flex: 0 1 auto;
}

.module-content-card {
  display: flex;
  flex-direction: column;
}

.module-manage-page > .site-settings-card {
  flex: 0 0 auto;
}

.site-settings-form {
  display: grid;
  grid-template-columns: minmax(0, 300px) minmax(0, 560px);
  justify-content: start;
  align-items: center;
  gap: 16px 72px;
  margin-top: 12px;
}

.site-settings-form .el-form-item {
  align-items: center;
  margin-bottom: 0;
}

.site-settings-form :deep(.el-form-item__content) {
  min-width: 0;
}

.site-name-field .el-input {
  max-width: 224px;
}

.site-icon-controls {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  align-items: start;
  gap: 6px 12px;
  width: 100%;
  min-width: 0;
}

.site-icon-preview {
  display: grid;
  place-items: center;
  grid-row: 1 / span 2;
  width: 56px;
  height: 56px;
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  background: var(--content-bg);
}

.site-icon-preview img {
  width: 40px;
  height: 40px;
  object-fit: contain;
}

.site-icon-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.site-icon-actions .el-button + .el-button {
  margin-left: 0;
}

.site-icon-hint {
  grid-column: 2;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.site-icon-file {
  display: none;
}

.module-name-cell {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.module-name-cell--child {
  padding-left: 30px;
  position: relative;
}

:deep(.module-table .module-table__row--parent > td.el-table__cell) {
  background: linear-gradient(90deg, rgba(237,244,255,.74), rgba(255,255,255,.78));
  border-top: 1px solid rgba(36,91,219,.12);
  border-bottom-color: rgba(36,91,219,.08);
}

:deep(.module-table .module-table__row--parent .module-name) {
  color: #173f9c;
  font-size: 14px;
}

:deep(.module-table .module-table__row--parent .module-code) {
  color: #7193d9;
}

:deep(.module-table .module-table__row--child > td.el-table__cell) {
  background: #fff;
}

:deep(.module-table .module-table__row--child .el-table__cell:first-child) {
  position: relative;
}

:deep(.module-table .module-table__row--child .el-table__cell:first-child::before) {
  position: absolute;
  left: 20px;
  top: 50%;
  width: 16px;
  height: 1px;
  background: #cbd5e1;
  content: '';
}

.module-name {
  color: #0f172a;
  font-weight: 700;
}

.module-code {
  color: #94a3b8;
  font-size: 12px;
}

:deep(.module-table .el-switch.is-disabled) {
  opacity: 0.72;
}

.default-page-button {
  min-width: 78px;
}

.module-order-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.module-order-actions .el-button + .el-button {
  margin-left: 0;
}

.default-page-button.is-current.is-disabled {
  color: #245bdb;
  background: #edf4ff;
  border-color: #c9d9ff;
  opacity: 1;
}

.default-page-empty {
  color: #cbd5e1;
}

@media (max-width: 1024px) {
  .site-settings-form {
    grid-template-columns: minmax(0, 560px);
  }
}

@media (max-width: 760px) {
  .section-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
}

.hero.panel { border-radius: 20px; }
</style>
