<template>
  <figure class="product-figure" :class="{ 'figure-light': light }">
    <div class="figure-header"><span>{{ label }}</span><span><el-icon><FullScreen /></el-icon> 点击放大查看</span></div>
    <button class="figure-image" type="button" :aria-label="`放大查看${title}`" @click="openFigure">
      <img :src="src" :alt="alt" :width="width" :height="height" loading="lazy" decoding="async" />
    </button>
    <figcaption><strong>{{ title }}</strong><p>{{ caption }}</p></figcaption>
    <dialog ref="dialog" class="figure-dialog" :aria-label="`${title}大图`" @click="closeBackdrop" @close="fullSize = false">
      <div class="figure-dialog-header"><strong>{{ title }}</strong><div><button type="button" :aria-pressed="fullSize" @click="fullSize = !fullSize">{{ fullSize ? '适应窗口' : '原尺寸查看' }}</button><a :href="src" target="_blank" rel="noopener noreferrer" aria-label="在新窗口打开原图"><el-icon><TopRight /></el-icon></a><button type="button" aria-label="关闭图片" @click="dialog.close()"><el-icon><Close /></el-icon></button></div></div>
      <div class="figure-dialog-content" :class="{ 'is-full-size': fullSize }" tabindex="0" aria-label="图片区域，可滚动查看"><img v-if="opened" :src="src" :alt="alt" /></div>
      <p class="figure-dialog-note">{{ fullSize ? '可横向和纵向滚动查看细节。' : '切换原尺寸查看细节，也可在新窗口打开。' }} 按 Esc 关闭。</p>
    </dialog>
  </figure>
</template>

<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { Close, FullScreen, TopRight } from '@element-plus/icons-vue'

defineProps({ src: { type: String, required: true }, title: { type: String, required: true }, alt: { type: String, required: true }, caption: { type: String, default: '' }, label: { type: String, default: 'PRODUCT / DIAGRAM' }, width: { type: Number, default: 1200 }, height: { type: Number, default: 820 }, light: Boolean })
const dialog = ref(null)
const fullSize = ref(false)
const opened = ref(false)
function openFigure() { opened.value = true; dialog.value.showModal() }
function closeBackdrop(event) { if (event.target === dialog.value) dialog.value.close() }
onBeforeUnmount(() => { if (dialog.value?.open) dialog.value.close() })
</script>

<style scoped>
.product-figure { margin: 0; overflow: hidden; border: 1px solid var(--p-line); border-radius: 12px; background: var(--p-surface); }
.figure-header { padding: 13px 20px; display: flex; align-items: center; justify-content: space-between; gap: 15px; color: var(--p-subtle); border-bottom: 1px solid var(--p-line); font-size: 10px; letter-spacing: 1px; }
.figure-header > span:last-child { display: inline-flex; align-items: center; gap: 7px; letter-spacing: 0; }
.figure-image { width: 100%; display: block; background: var(--p-bg); border: 0; padding: 0; cursor: zoom-in; }
.figure-image img { width: 100%; height: auto; display: block; }
.figure-light .figure-image { padding: 16px; background: light-dark(#effaff, #effaff); }
.figure-light .figure-image img { border-radius: 6px; }
figcaption { padding: 20px 24px; border-top: 1px solid var(--p-line); }
figcaption strong { font-size: 14px; font-weight: 600; }
figcaption p { margin-top: 6px; font-size: 12px; line-height: 1.9; color: var(--p-muted); }
.figure-dialog { margin: auto; width: min(1540px, calc(100vw - 40px)); max-width: none; padding: 0; max-height: calc(100dvh - 40px); overflow: auto; color: var(--p-ink); background: var(--p-surface); border: 1px solid var(--p-line); border-radius: 12px; }
.figure-dialog::backdrop { background: light-dark(#000c, #000c); backdrop-filter: blur(8px); }
.figure-dialog-header { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 14px 18px; border-bottom: 1px solid var(--p-line); }
.figure-dialog-header strong { font-size: 13px; font-weight: 600; }
.figure-dialog-header > div { display: flex; gap: 8px; align-items: center; }
.figure-dialog-header :is(a, button) { display: inline-flex; justify-content: center; align-items: center; min-width: 32px; height: 32px; padding: 4px 10px; border: 1px solid var(--p-line); background: var(--p-raised); border-radius: 6px; font-size: 11px; color: var(--p-ink); white-space: nowrap; cursor: pointer; }
.figure-dialog-content { max-height: calc(100dvh - 180px); overflow: auto; background: var(--p-bg); overscroll-behavior: contain; }
.figure-dialog-content img { width: 100%; height: auto; max-height: calc(100dvh - 180px); object-fit: contain; display: block; }
.figure-dialog-content.is-full-size img { width: auto; min-width: 100%; max-width: none; max-height: none; }
.figure-dialog-note { font-size: 11px; color: var(--p-muted); padding: 12px 18px; }
:is(a, button, [tabindex]):focus-visible { outline: 2px solid var(--p-accent); outline-offset: -3px; }
@media (max-width: 640px) { .figure-header { padding: 12px 14px; font-size: 8px; letter-spacing: .4px; } .figure-header > span:last-child { font-size: 9px; } .figure-light .figure-image { padding: 6px; } figcaption { padding: 17px; } figcaption strong { font-size: 12px; } figcaption p { font-size: 11px; } .figure-dialog { width: calc(100vw - 16px); max-height: calc(100dvh - 20px); } .figure-dialog-header { align-items: flex-start; padding: 12px; gap: 10px; } .figure-dialog-header strong { font-size: 11px; padding-top: 5px; } .figure-dialog-header > div { gap: 5px; } .figure-dialog-header :is(a, button) { font-size: 9px; padding-inline: 7px; min-width: 28px; height: 30px; } .figure-dialog-note { font-size: 10px; } }
</style>
