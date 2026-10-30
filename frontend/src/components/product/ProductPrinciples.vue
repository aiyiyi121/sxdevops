<template>
  <section id="principles" class="principles-section">
    <div class="principles-heading"><div><p class="principles-eyebrow">{{ sectionLabel('principles') }}</p><h2>让智能体可用、可信，<br />也能<span>持续运转。</span></h2></div><p>真实数据、受控工具、可靠流程与持续评估，<br />一起决定智能体能否在运维现场发挥价值。</p></div>
    <ProductFigure src="/promo/v2/sre-agent-principles.webp" title="SRE 角度对 AI 的思考：谈谈如何做好运维智能体" alt="SRE 运维智能体方法论图：拆解故障处理、用证据支持结论、明确执行责任、合理组织工具与技能、计算新增成本，并持续评估与保障运行" label="SRE / 工程方法论" :width="1672" :height="941" light caption="从信息收集、分析判断、任务执行到结果验证，梳理运维智能体的职责、证据、边界与投入。这张图表达工程方法和建设方向，具体能力以当前产品实现为准。" />
    <div class="principle-notes"><article><span>01</span><div><h3>证据要能回到来源</h3><p>区分事实、推断与尚未验证的假设，保留查询范围、时间窗口和证据缺口，让结论可以复核。</p></div></article><article><span>02</span><div><h3>价值要放在真实工作里衡量</h3><p>把模型调用、查询、维护和复核成本一起考虑，用具体场景评估排障效率、处理成本与风险变化。</p></div></article><article><span>03</span><div><h3>先建立可检查的工作链路</h3><p>保留权限不足、数据缺失、工具失败与执行异常等案例，围绕流程的真实表现持续补充评测与改进。</p></div></article></div>
  </section>
</template>

<script setup>
import ProductFigure from './ProductFigure.vue'
import { sectionLabel } from './sections'
</script>

<style scoped>
.principles-section { width: min(1240px, calc(100% - 96px)); margin-inline: auto; padding-top: 100px; scroll-margin-top: 90px; }
.principles-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 36px; margin-bottom: 35px; }
.principles-eyebrow { color: var(--p-accent); font-size: 11px; letter-spacing: 1.4px; font-weight: 600; }
.principles-heading h2 { font-size: 37px; font-weight: 650; line-height: 1.4; letter-spacing: -1.4px; margin-top: 14px; }
.principles-heading h2 span { color: var(--p-accent); }
.principles-heading > p { max-width: 410px; font-size: 13px; line-height: 1.95; color: var(--p-muted); padding-bottom: 4px; }
.principle-notes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 25px; margin-top: 28px; }
.principle-notes article { display: flex; align-items: flex-start; gap: 13px; }
.principle-notes article > span { color: var(--p-accent); font-size: 11px; margin-top: 3px; font-family: ui-monospace, monospace; }
.principle-notes h3 { font-size: 14px; font-weight: 600; }
.principle-notes p { font-size: 12px; color: var(--p-muted); line-height: 1.95; margin-top: 9px; }
@media (max-width: 1150px) { .principles-section { width: calc(100% - 64px); } .principles-heading > p { font-size: 12px; } }
@media (max-width: 900px) { .principles-section { padding-top: 74px; } .principles-heading h2 { font-size: 30px; } .principles-heading > p { font-size: 11px; max-width: 300px; } .principle-notes { gap: 19px; } .principle-notes h3 { font-size: 12px; } .principle-notes p { font-size: 11px; } }
@media (max-width: 640px) { .principles-section { width: calc(100% - 40px); padding-top: 60px; scroll-margin-top: 80px; } .principles-heading { display: block; margin-bottom: 25px; } .principles-eyebrow { font-size: 10px; } .principles-heading h2 { font-size: 27px; margin-top: 12px; letter-spacing: -1px; } .principles-heading > p { margin-top: 17px; max-width: none; font-size: 11px; } .principle-notes { grid-template-columns: 1fr; gap: 24px; margin-top: 25px; } .principle-notes h3 { font-size: 14px; } .principle-notes p { font-size: 12px; } }
</style>
