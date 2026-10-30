<template>
  <aside v-loading="loading" class="resource-scope-tree">
    <div class="scope-tree-head">
      <strong>业务环境维度</strong>
      <div v-if="$slots.actions" class="scope-tree-actions scope-tree-root-actions"><slot name="actions" /></div>
    </div>
    <el-input v-model="keyword" clearable size="small" placeholder="搜索业务线 / 环境" class="scope-tree-search">
      <template #prefix><el-icon><Search /></el-icon></template>
    </el-input>
    <button type="button" class="scope-all-node" :class="{ active: !selection }" @click="emit('select', null)">
      <span>{{ allLabel }}</span><strong>{{ total }}</strong>
    </button>
    <el-tree
      ref="treeRef"
      :data="data"
      :props="{ label: 'name', children: 'children' }"
      :current-node-key="selection?.key || null"
      :filter-node-method="filterNode"
      node-key="key"
      highlight-current
      default-expand-all
      :expand-on-click-node="false"
      :indent="16"
      class="scope-tree-list"
      @node-click="node => emit('select', node)"
    >
      <template #default="{ data: node }">
        <div class="scope-tree-node">
          <span class="scope-tree-label">
            <el-icon><component :is="node.node_type === 'biz' ? Connection : Monitor" /></el-icon>
            <span :title="node.name">{{ node.name }}</span>
          </span>
          <div v-if="$slots['node-actions']" class="scope-tree-actions scope-tree-node-actions" @click.stop>
            <slot name="node-actions" :node="node" />
          </div>
          <strong>{{ node.resource_count || 0 }}</strong>
        </div>
      </template>
    </el-tree>
    <el-empty v-if="!loading && !data.length" description="暂无业务环境资源" :image-size="56" />
  </aside>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { Connection, Monitor, Search } from '@element-plus/icons-vue'

const props = defineProps({
  data: { type: Array, default: () => [] },
  loading: Boolean,
  selection: { type: Object, default: null },
  allLabel: { type: String, default: '全部执行资源' },
})
const emit = defineEmits(['select'])
const treeRef = ref(null)
const keyword = ref('')
const total = computed(() => props.data.reduce((count, node) => count + (node.resource_count || 0), 0))

function filterNode(value, node) {
  return !value || node.name.toLowerCase().includes(value.toLowerCase())
}

watch(keyword, value => treeRef.value?.filter(value))
watch(() => props.data, async () => {
  await nextTick()
  treeRef.value?.filter(keyword.value)
})
watch(() => props.selection, value => treeRef.value?.setCurrentKey(value?.key || null))
</script>

<style scoped>
.resource-scope-tree {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 520px;
  border-right: 4px solid #e5e7eb;
  padding-right: 12px;
}

.scope-tree-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 28px;
  margin-bottom: 12px;
}

.scope-tree-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex: none;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.16s ease;
}

.scope-tree-actions:empty {
  display: none;
}

.scope-tree-head:hover .scope-tree-root-actions,
.scope-tree-head:focus-within .scope-tree-root-actions,
.scope-tree-list :deep(.el-tree-node__content:hover > .scope-tree-node > .scope-tree-node-actions),
.scope-tree-node:focus-within > .scope-tree-node-actions {
  opacity: 1;
  pointer-events: auto;
}

.scope-tree-actions :deep(button) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
}

.scope-tree-root-actions :deep(button) {
  width: 28px;
  height: 28px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 8px;
  background: #fff;
}

.scope-tree-actions :deep(button:hover) {
  background: rgba(51, 112, 255, 0.1);
  color: #245bdb;
}

.scope-tree-node-actions {
  position: absolute;
  right: 40px;
  top: 50%;
  transform: translateY(-50%);
  padding: 1px 2px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
}

.scope-tree-head > strong {
  color: #1f2937;
  font-size: 14px;
  line-height: 1.3;
}

.scope-tree-search {
  margin-bottom: 12px;
}

.scope-all-node,
.scope-tree-node {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  color: #374151;
  font-size: 13px;
}

.scope-all-node {
  width: 100%;
  min-height: 30px;
  padding: 0 8px;
  margin-bottom: 4px;
  border: 0;
  border-radius: 2px;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.scope-all-node:hover,
.scope-all-node.active {
  background: #e8f0ff;
  color: #245bdb;
}

.scope-all-node strong,
.scope-tree-node strong {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  min-width: 28px;
  height: 20px;
  padding: 0 6px;
  border-radius: 2px;
  background: #eef4ff;
  color: #245bdb;
  font-size: 12px;
  font-weight: 500;
}

.scope-tree-list {
  background: transparent;
}

.scope-tree-node {
  flex: 1;
  padding-right: 8px;
}

.scope-tree-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.scope-tree-label > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scope-tree-label .el-icon {
  flex: none;
  color: #64748b;
  font-size: 14px;
}

.scope-tree-list :deep(.el-tree-node__content) {
  min-height: 30px;
  margin-bottom: 4px;
  border-radius: 2px;
}

.scope-tree-list :deep(.el-tree-node.is-current > .el-tree-node__content),
.scope-tree-list :deep(.el-tree-node__content:hover) {
  background: #e8f0ff;
}

.scope-tree-list :deep(.el-tree-node.is-current > .el-tree-node__content .scope-tree-node) {
  color: #245bdb;
}

@media (max-width: 900px) {
  .resource-scope-tree {
    min-height: 0;
    max-height: 280px;
    overflow: auto;
    padding-right: 0;
    padding-bottom: 12px;
    border-right: 0;
    border-bottom: 1px solid #e5e7eb;
  }
}
</style>
