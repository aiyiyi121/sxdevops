<template>
  <el-dropdown
    v-if="actions.length"
    class="k8s-resource-actions"
    trigger="click"
    placement="bottom-end"
    :persistent="false"
    popper-class="k8s-resource-action-popper"
    @command="emit('select', $event)"
  >
    <button class="k8s-resource-more-button" type="button" aria-label="更多操作" @click.stop>
      <el-icon><MoreFilled /></el-icon>
    </button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="action in actions"
          :key="action.key"
          :command="action"
          :disabled="action.disabled"
          :class="{ 'is-danger': action.danger }"
        >
          <el-icon><component :is="iconMap[action.icon] || MoreFilled" /></el-icon>
          <span>{{ action.label }}</span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup>
import {
  Bell,
  Document,
  EditPen,
  Delete,
  Monitor,
  MoreFilled,
  RefreshRight,
  Tickets,
} from '@element-plus/icons-vue'

defineProps({
  actions: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['select'])

const iconMap = {
  delete: Delete,
  events: Bell,
  logs: Tickets,
  pods: Tickets,
  restart: RefreshRight,
  scale: RefreshRight,
  shell: Monitor,
  yaml: Document,
  edit: EditPen,
}
</script>

<style scoped>
.k8s-resource-more-button {
  display: inline-flex;
  width: 30px;
  height: 30px;
  align-items: center;
  justify-content: center;
  border: 1px solid #d8e1ef;
  border-radius: 50%;
  background: #fff;
  color: #4773bd;
  cursor: pointer;
  transition: .16s ease;
}

.k8s-resource-more-button:hover,
.k8s-resource-more-button:focus-visible {
  border-color: #82a7e8;
  background: #edf4ff;
  box-shadow: 0 0 0 3px rgba(51, 112, 255, .1);
  color: #245bdb;
  outline: none;
}
</style>

<style>
.k8s-resource-action-popper.el-popper {
  min-width: 148px;
  padding: 5px;
  border-color: #d9e1ec;
  box-shadow: 0 12px 28px rgba(15, 23, 42, .14);
}

.k8s-resource-action-popper .el-dropdown-menu {
  padding: 0;
}

.k8s-resource-action-popper .el-dropdown-menu__item {
  gap: 8px;
  min-height: 32px;
  padding: 0 10px;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}

.k8s-resource-action-popper .el-dropdown-menu__item .el-icon {
  color: #4475bf;
  font-size: 14px;
}

.k8s-resource-action-popper .el-dropdown-menu__item:hover {
  background: #eff5ff;
  color: #245bdb;
}

.k8s-resource-action-popper .el-dropdown-menu__item.is-danger,
.k8s-resource-action-popper .el-dropdown-menu__item.is-danger .el-icon {
  color: #dc2626;
}
</style>
