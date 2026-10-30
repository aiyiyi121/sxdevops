<template>
  <div class="fade-in task-page-shell workbench-page-shell">
    <section class="hero panel task-hero-panel">
      <div class="hero-copy">
        <div class="hero-title-row">
          <span class="hero-icon hero-icon-monitor"><el-icon><Monitor /></el-icon></span>
          <h2>资源底座</h2>
          <p class="page-inline-desc">统一接入 CMDB 资产与手工资源，维护任务执行连接与资源归属。</p>
        </div>
      </div>
    </section>

    <TaskResourceBase class="workbench-fill-panel" />
  </div>
</template>

<script setup>
import { Monitor } from '@element-plus/icons-vue'
import TaskResourceBase from '@/components/tasks/TaskResourceBase.vue'
</script>

<style scoped>
.task-page-shell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.hero.panel.task-hero-panel {
  align-items: center;
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border: 1px solid rgba(36, 91, 219, 0.09);
  border-radius: 20px;
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.04);
  display: flex;
  justify-content: space-between;
  padding: 14px 16px;
}

.hero-copy {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.hero-title-row {
  align-items: center;
  display: flex;
  gap: 10px;
}

.hero-title-row h2 {
  color: #0f172a;
  font-size: 23px;
  font-weight: 700;
  line-height: 1.1;
  margin: 0;
}

.page-inline-desc {
  color: #475569;
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
  flex: 0 1 auto;
}

.hero-icon {
  align-items: center;
  border-radius: 14px;
  color: #245bdb;
  display: inline-flex;
  font-size: 20px;
  height: 42px;
  justify-content: center;
  width: 42px;
}

.hero-icon-monitor {
  background: rgba(51, 112, 255, 0.09);
}

.panel {
  background: #fff;
  border: 1px solid #eff0f2;
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(31, 35, 41, 0.06);
  padding: 12px 14px;
}

@media (max-width: 760px) {
  .hero.panel.task-hero-panel {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
