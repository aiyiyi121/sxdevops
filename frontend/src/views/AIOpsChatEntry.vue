<template>
  <div class="aiops-entry-page fade-in">
    <section class="aiops-chat-shell">
      <AIOpsChatWidget embedded />
    </section>
  </div>
</template>

<script setup>
import AIOpsChatWidget from '@/components/aiops/AIOpsChatWidget.vue'
</script>

<style scoped>
.aiops-entry-page{display:flex;flex-direction:column;height:var(--page-content-height);min-height:0}
.aiops-chat-shell{flex:1;min-height:0}
</style>
