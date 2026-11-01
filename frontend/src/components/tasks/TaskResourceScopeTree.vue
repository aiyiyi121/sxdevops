<template>
  <aside v-loading="loading" class="resource-scope-tree">
    <div class="scope-tree-head">
      <strong>业务环境维度</strong>
      <div v-if="$slots.actions" class="scope-tree-actions scope-tree-root-actions"><slot name="actions" /></div>
    </div>
    <el-input v-model="keyword" clearable placeholder="搜索业务线 / 资源名等" class="scope-tree-search" />
    <div class="scope-tree-list" role="tree" aria-label="业务环境资源树">
      <button type="button" class="scope-all-node" :class="{ active: !selection }" @click="emit('select', null)">
        <span>{{ allLabel }}</span><strong>{{ total }}</strong>
      </button>
      <div
        v-for="entry in visibleNodes"
        :key="entry.node.key"
        class="scope-tree-row"
        :class="{ active: selection?.key === entry.node.key }"
        :style="{ '--scope-node-depth': entry.depth }"
        role="treeitem"
        tabindex="0"
        :aria-label="nodeLabel(entry.node) + ' ' + (entry.node.resource_count || 0)"
        :aria-level="entry.depth + 1"
        :aria-selected="selection?.key === entry.node.key"
        :aria-expanded="entry.hasChildren ? entry.expanded : undefined"
        @click="emit('select', entry.node)"
        @keydown.enter.self.prevent="emit('select', entry.node)"
        @keydown.space.self.prevent="emit('select', entry.node)"
        @keydown.right.self.prevent="setExpanded(entry.node, true)"
        @keydown.left.self.prevent="setExpanded(entry.node, false)"
      >
        <span class="scope-tree-label">
          <button
            v-if="entry.hasChildren" type="button" class="scope-tree-toggle"
            :aria-label="(entry.expanded ? '收起' : '展开') + nodeLabel(entry.node)"
            :aria-expanded="entry.expanded" @click.stop="setExpanded(entry.node, !entry.expanded)"
          ><el-icon><component :is="entry.expanded ? ArrowDown : ArrowRight" /></el-icon></button>
          <span v-else class="scope-tree-toggle scope-tree-toggle--leaf" />
          <el-icon class="scope-tree-node-icon"><component :is="nodeIcon(entry.node)" /></el-icon>
          <span :title="nodeLabel(entry.node)">{{ nodeLabel(entry.node) }}</span>
        </span>
        <span class="scope-tree-node-right">
          <strong>{{ entry.node.resource_count || 0 }}</strong>
          <span v-if="$slots['node-actions']" class="scope-tree-actions scope-tree-node-actions" @click.stop>
            <slot name="node-actions" :node="entry.node" />
          </span>
        </span>
      </div>
    </div>
    <el-empty v-if="!loading && !visibleNodes.length" :description="keyword ? '暂无匹配资源' : '暂无业务环境资源'" :image-size="56" />
  </aside>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ArrowDown, ArrowRight, Collection, Folder, FolderChecked } from '@element-plus/icons-vue'

const props = defineProps({
  data: { type: Array, default: () => [] },
  loading: Boolean,
  selection: { type: Object, default: null },
  allLabel: { type: String, default: '全部执行资源' },
})
const emit = defineEmits(['select'])
const keyword = ref('')
const expansion = ref(new Map())
const total = computed(() => props.data.reduce((count, node) => count + (node.resource_count || 0), 0))

function nodeLabel(node) {
  if (node.node_type !== 'env') return node.name
  return ({ prod: '生产', production: '生产', test: '测试', testing: '测试', dev: '开发', development: '开发', uat: '联调', integration: '集成' })[String(node.name).trim().toLowerCase()] || node.name
}

function nodeIcon(node) {
  return ({ biz: Folder, env: FolderChecked, system: Collection })[node.node_type] || Folder
}

function setExpanded(node, expanded) {
  expansion.value.set(node.key, expanded)
}

const visibleNodes = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  function flatten(nodes, depth = 0) {
    return [...nodes].sort((left, right) => {
      const explicit = node => node.cmdb_node ? 0 : 1
      return explicit(left) - explicit(right) || (left.sort_order || 0) - (right.sort_order || 0)
        || (right.asset_count ?? right.resource_count ?? 0) - (left.asset_count ?? left.resource_count ?? 0) || left.name.localeCompare(right.name, 'zh-Hans-CN')
    }).flatMap(node => {
      const hasChildren = Boolean(node.children?.length)
      const expanded = hasChildren && (Boolean(query) || (expansion.value.get(node.key) ?? node.node_type === 'biz'))
      const children = expanded ? flatten(node.children, depth + 1) : []
      const text = [node.name, nodeLabel(node), ...(node.search_names || [])].join(' ').toLowerCase()
      if (query && !text.includes(query) && !children.length) return []
      return [{ node, depth, hasChildren, expanded }, ...children]
    })
  }
  return flatten(props.data)
})
</script>

<style scoped>
.resource-scope-tree {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 520px;
  border-right: 4px solid light-dark(#e5e7eb, var(--el-border-color));
  padding-right: 12px;
}
.scope-tree-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}
.scope-tree-head > strong { color: var(--text-primary); font-size: 14px; line-height: 1.3; }
.scope-tree-search { margin-bottom: 12px; }
.scope-tree-list { display: flex; flex-direction: column; gap: 4px; }
.scope-all-node, .scope-tree-row {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  min-width: 0;
  min-height: 30px;
  padding: 0 8px;
  border: 0;
  border-radius: 2px;
  background: transparent;
  color: var(--el-text-color-regular);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}
.scope-tree-row { padding-left: calc(8px + var(--scope-node-depth, 0) * 16px); }
.scope-all-node:hover, .scope-all-node.active { background: light-dark(#eaf8f0, var(--el-fill-color-lighter)); color: var(--el-color-success); }
.scope-tree-row:hover, .scope-tree-row.active { background: light-dark(#e8f0ff, var(--el-fill-color-lighter)); color: var(--el-color-primary); }
.scope-all-node:focus-visible, .scope-tree-row:focus-visible, .scope-tree-toggle:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: -2px;
}
.scope-all-node strong, .scope-tree-node-right > strong {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  min-width: 28px;
  height: 20px;
  padding: 0 6px;
  border-radius: 2px;
  background: light-dark(#eef4ff, var(--el-fill-color-lighter));
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 500;
}
.scope-all-node strong { background: light-dark(#e8fff4, var(--el-fill-color-lighter)); color: var(--el-color-success); }
.scope-tree-label { display: inline-flex; align-items: center; gap: 5px; min-width: 0; }
.scope-tree-label > span:last-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scope-tree-node-icon { flex: none; color: var(--text-secondary); font-size: 14px; }
.scope-tree-row:hover .scope-tree-node-icon, .scope-tree-row.active .scope-tree-node-icon { color: var(--el-color-primary); }
.scope-tree-toggle {
  display: inline-flex; align-items: center; justify-content: center;
  flex: none; width: 16px; height: 16px; padding: 0;
  border: 0; border-radius: 4px; background: transparent; color: var(--el-text-color-placeholder); cursor: pointer;
}
.scope-tree-toggle .el-icon { font-size: 12px; }
.scope-tree-toggle:hover { background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.scope-tree-toggle--leaf { visibility: hidden; }
.scope-tree-node-right { display: inline-flex; align-items: center; flex: none; min-width: 34px; margin-left: auto; padding-left: 8px; }
.scope-tree-actions { display: inline-flex; align-items: center; gap: 2px; flex: none; }
.scope-tree-actions:empty { display: none; }
.scope-tree-actions :deep(button) {
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; padding: 0; border: 0; border-radius: 6px;
  background: transparent; color: var(--text-secondary); cursor: pointer;
}
.scope-tree-root-actions :deep(button) {
  width: 28px; height: 28px; border: 1px solid var(--el-border-color-light);
  border-radius: 8px; background: var(--el-bg-color);
}
.scope-tree-actions :deep(button:hover) { background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.scope-tree-node-actions {
  position: absolute; right: 40px; top: 50%; transform: translateY(-50%);
  padding: 1px 2px; border: 1px solid var(--el-border-color-light); border-radius: 8px;
  background: var(--el-bg-color-overlay); box-shadow: var(--el-box-shadow-light);
  opacity: 0; pointer-events: none; transition: opacity .16s ease;
}
.scope-tree-row:hover .scope-tree-node-actions, .scope-tree-row.active .scope-tree-node-actions,
.scope-tree-row:focus-within .scope-tree-node-actions { opacity: 1; pointer-events: auto; }
@media (max-width: 1100px) {
  .resource-scope-tree {
    min-height: 0; max-height: 280px; overflow: auto; padding-right: 0; padding-bottom: 12px;
    border-right: 0; border-bottom: 1px solid var(--el-border-color-lighter);
  }
}
</style>
