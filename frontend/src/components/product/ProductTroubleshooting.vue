<template>
  <section id="troubleshooting" class="troubleshooting-section">
    <div class="path-heading">
      <div><p class="path-eyebrow">{{ sectionLabel('troubleshooting') }}</p><h2>沿着排障路径，<br />把线索连成<span>判断。</span></h2></div>
      <p>先从全局发现异常，再收敛到环境、系统与服务。<br />让告警、日志、Trace、事件与任务接得上。</p>
    </div>

    <ol class="investigation-journey" aria-label="从发现异常到处置的排障路径">
      <li v-for="(stage, index) in journey" :key="stage.title">
        <div class="journey-top"><span>0{{ index + 1 }}</span><span>{{ stage.value }}</span></div>
        <el-icon class="journey-icon"><component :is="stage.icon" /></el-icon>
        <h3>{{ stage.title }}</h3><p>{{ stage.description }}</p><span class="journey-context">{{ stage.context }}</span>
      </li>
    </ol>

    <div class="case-heading"><div><p class="path-eyebrow">同一问题 / 两条处理路径</p><h3>从一个具体问题，看清两条处理路径。</h3></div><div class="case-selector" role="group" aria-label="选择排障对照场景"><button v-for="(scenario, index) in scenarios" :key="scenario.id" type="button" :aria-pressed="scenarioIndex === index" @click="scenarioIndex = index">{{ scenario.label }}</button></div></div>
    <div class="case-body" aria-live="polite">
      <div class="case-question"><span><el-icon><ChatDotRound /></el-icon> 现场提问</span><p>{{ currentScenario.question }}</p><div><span>{{ currentScenario.scope }}</span><span>场景示意</span></div></div>
      <div class="path-comparison">
        <article class="manual-path"><div class="comparison-title"><span>MANUAL / 人工排查</span><h4>逐项查询，人工串起上下文</h4></div><ol><li v-for="(step, index) in currentScenario.manual" :key="step.title"><span>0{{ index + 1 }}</span><div><h5>{{ step.title }}</h5><p>{{ step.description }}</p></div></li></ol><p class="path-result">{{ currentScenario.manualResult }}</p></article>
        <article class="agent-path"><div class="comparison-title"><span>WITH AGENT / 智能体协同</span><h4>围绕同一范围，组织证据与建议</h4></div><ol><li v-for="(step, index) in currentScenario.agent" :key="step.title"><span><el-icon><Check /></el-icon></span><div><h5>{{ step.title }}</h5><p>{{ step.description }}</p></div></li></ol><p class="path-result">{{ currentScenario.agentResult }}</p></article>
      </div>
      <div class="answer-preview"><div class="answer-heading"><span>交付给你的，不止一句结论</span><span>输出结构示意</span></div><dl><div v-for="part in currentScenario.output" :key="part.title"><dt>{{ part.title }}</dt><dd>{{ part.description }}</dd></div></dl></div>
      <p class="case-note">以上展示处理方式与输出结构，不代表实际查询结果。取证以已配置的数据源、资源关联和当前权限为准；时间接近的变更仍需交叉验证。</p>
    </div>

    <div class="review-panel">
      <div class="review-story"><span class="path-eyebrow">EVENT CENTER / 从处理到复盘</span><h3>把一次处理，<br />留成下一次能查的现场。</h3><p>事件中心围绕最终执行结果、关键写操作和失败线索组织记录，按系统、环境、应用与时间收敛范围。结合任务历史和智能体审计，回看谁做了什么、结果如何。</p><a href="#screenshots" @click="$emit('show-events')">查看事件中心界面 <el-icon><ArrowRight /></el-icon></a></div>
      <div class="review-details"><div class="review-questions"><span>复盘时，可以从这些问题开始</span><p v-for="question in reviewQuestions" :key="question"><el-icon><Search /></el-icon>{{ question }}</p></div><div class="review-boundaries"><div><h4>保留结果与责任</h4><p>关注最终执行和关键写入，默认排除未执行的驳回审批记录，避免把审批过程误当成实际变更。</p></div><div><h4>回到具体记录核对</h4><p>时间线提供关联线索，任务返回内容和工具调用审计补充细节；关联仍需结合现场证据判断。</p></div></div></div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ArrowRight, ChatDotRound, Check, Connection, DataAnalysis, Monitor, Search, Tickets } from '@element-plus/icons-vue'
import { sectionLabel } from './sections'

defineEmits(['show-events'])
const journey = [
  { title: '系统态势，先看全局', value: '可见', icon: Monitor, description: '从首页 SLA 历史、当前状态和环境分组识别异常系统，区分故障、未知和数据缺口。', context: '首页 → 系统态势 → 明确影响范围' },
  { title: '可观测性，找到证据', value: '有据', icon: DataAnalysis, description: '沿同一服务和时间窗口查看告警、指标、日志与 Trace，核对慢调用、异常 Span 和错误上下文。', context: '告警 → 日志 / Trace → 指标交叉验证' },
  { title: '事件中心，回看变化', value: '可追', icon: Connection, description: '关联最近发布、任务、工单和关键写入，确认异常前后发生了什么，保留待验证的候选原因。', context: '环境 / 系统 / 应用 → 事件时间线' },
  { title: '任务中心，承接行动', value: '可执行', icon: Tickets, description: '需要巡检或处置时生成草稿，核对目标、参数与风险，确认后执行，再查看结果和恢复证据。', context: '任务草稿 → 人工确认 → 执行与复盘' },
]
const scenarioIndex = ref(0)
const scenarios = [
  {
    id: 'service', label: '服务异常', question: '分析生产 order-center 最近 30 分钟的异常，结合告警、日志、Trace 和最近变更给出排查建议。', scope: '生产环境 / order-center / 最近 30 分钟',
    manual: [
      { title: '先读懂告警', description: '查看 PromQL、标签、触发时间，确认环境、服务和影响范围。' },
      { title: '分别查询日志与链路', description: '搜索错误关键字，定位慢调用和异常 Span，手工对齐时间窗口。' },
      { title: '翻看变更与任务记录', description: '核对最近发布、审批、任务和事件，拼出异常前后的时间线。' },
      { title: '整理结论与后续动作', description: '汇总证据和疑点，再准备巡检或处置任务，记录执行结果。' },
    ],
    agent: [
      { title: '先固定问题范围', description: '明确知识环境、服务与时间窗口，按当前账号权限组织查询。' },
      { title: '分阶段取证', description: '采集告警、日志、错误 Trace、指标和相关事件，保留每一步结果与缺口。' },
      { title: '输出可核对的判断', description: '用 Skill 整理结论、依据、风险与建议，将变更关联保留为待验证线索。' },
      { title: '衔接待确认任务', description: '需要巡检时生成草稿，用户核对后由任务中心承接，结果进入追踪与审计。' },
    ],
    manualResult: '排查人员负责发现、切换、对齐和汇总每一类信息。', agentResult: '把精力放到看证据、做判断和确认动作上。',
    output: [
      { title: '初步结论', description: '概括异常范围与候选原因，区分事实和推断。' },
      { title: '证据清单', description: '保留告警、日志、Trace 与变更的来源和查询窗口。' },
      { title: '缺口与风险', description: '交代查询失败、缺少数据和需要补查的部分。' },
      { title: '建议动作', description: '列出核查顺序；需要执行时先核对任务草稿。' },
    ],
  },
  {
    id: 'k8s', label: 'K8s 异常', question: '分析测试环境中反复重启的工作负载，结合 Pod、集群、告警和事件，给出下一步核查建议。', scope: '指定知识环境 / 绑定集群 / 授权命名空间',
    manual: [
      { title: '找到正确集群与资源', description: '确认环境绑定和命名空间，筛选异常工作负载与 Pod。' },
      { title: '逐项检查资源状态', description: '查看重启、调度、资源用量与集群摘要，识别异常线索。' },
      { title: '补查告警和事件', description: '对齐告警、近期变更和系统态势，排除无关环境的信息。' },
      { title: '决定核查或变更', description: '整理问题和影响范围；如需改 YAML，先预检并检查差异。' },
    ],
    agent: [
      { title: '固定环境与关联集群', description: '沿用环境绑定、用户指定命名空间和资源授权范围。' },
      { title: '采集资源与集群事实', description: '工作负载、Pod 与集群摘要分阶段保存，缺少绑定或权限时明确说明。' },
      { title: '补齐关联上下文', description: '查询该范围内的告警、事件与态势，结合状态整理候选原因。' },
      { title: '给出检查顺序', description: '建议先核查探针、依赖、容量或配置，写入与执行继续经过预检和确认。' },
    ],
    manualResult: '需要人工保持集群、资源、告警和事件的范围一致。', agentResult: '围绕原环境和原集群组织取证，缺失信息可见。',
    output: [
      { title: '资源范围', description: '明确环境、集群、命名空间与异常工作负载。' },
      { title: '现场事实', description: '整理 Pod、集群摘要、告警与事件返回的状态。' },
      { title: '证据限制', description: '标出未绑定集群、未配置指标或查询失败的来源。' },
      { title: '核查建议', description: '按依据给出下一步；涉及配置变更先预检确认。' },
    ],
  },
  {
    id: 'change', label: '变更关联', question: '检查指定环境最近的发布和配置变更，看看它们与当前服务告警有哪些关联，并列出需要验证的地方。', scope: '指定环境 / 服务关系 / 最近变更与活动告警',
    manual: [
      { title: '先确认服务关系', description: '查看知识环境与依赖，厘清相关系统、服务和资源。' },
      { title: '收集变更与审批', description: '分别翻查最近发布、配置变化、工单和审批状态。' },
      { title: '对齐事件与告警', description: '手工比较执行结果、发生时间和告警范围，筛出候选线索。' },
      { title: '补证据后再定性', description: '检查日志、指标和依赖影响，再决定继续观察、检查或评估回退。' },
    ],
    agent: [
      { title: '先建立环境上下文', description: '结合知识图谱与服务关系明确本轮分析范围。' },
      { title: '逐类读取变更证据', description: '分阶段查询最近变更、工单、事件和活动告警，记录来源与状态。' },
      { title: '整理关联与不确定性', description: '指出时间、服务或依赖上的重合，明确关联仍需交叉验证。' },
      { title: '提供后续验证建议', description: '给出补查项目、影响核对与风险提示，具体执行仍由用户决定。' },
    ],
    manualResult: '需要人工区分审批过程、实际变更与异常的先后关系。', agentResult: '把分散记录放回同一上下文，让候选原因更便于核对。',
    output: [
      { title: '关联范围', description: '交代涉及哪些环境、系统、服务与依赖。' },
      { title: '关键时间线', description: '列出实际变更、执行结果与告警的先后关系。' },
      { title: '待验证线索', description: '保留候选诱因，避免将时间接近直接判断为因果。' },
      { title: '下一步', description: '补查日志、Trace 与指标，再评估核查或回退方案。' },
    ],
  },
]
const currentScenario = computed(() => scenarios[scenarioIndex.value])
const reviewQuestions = ['最近生产环境失败了什么？', '谁触发了这次关键变更？', '哪个应用的失败事件最集中？']
</script>

<style scoped>
.troubleshooting-section { width: min(1240px, calc(100% - 96px)); margin-inline: auto; padding-top: 100px; scroll-margin-top: 90px; }
.path-heading { display: flex; justify-content: space-between; align-items: flex-end; gap: 36px; margin-bottom: 35px; }
.path-eyebrow { font-size: 11px; color: var(--p-accent); letter-spacing: 1.8px; font-weight: 600; }
.path-heading h2 { font-size: 37px; line-height: 1.4; font-weight: 650; letter-spacing: -1.4px; margin-top: 14px; }
.path-heading h2 span { color: var(--p-accent); }
.path-heading > p { color: var(--p-muted); font-size: 13px; line-height: 1.95; padding-bottom: 4px; }
.investigation-journey { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); list-style: none; border: 1px solid var(--p-line); border-radius: 12px; background: var(--p-surface); overflow: hidden; }
.investigation-journey li { padding: 27px; position: relative; display: flex; flex-direction: column; align-items: flex-start; }
.investigation-journey li + li { border-left: 1px solid var(--p-line); }
.journey-top { width: 100%; display: flex; justify-content: space-between; align-items: center; font-size: 10px; color: var(--p-subtle); }
.journey-top > span:last-child { color: var(--p-accent); border: 1px solid var(--p-line); border-radius: 4px; padding: 2px 6px; font-size: 9px; }
.journey-icon { font-size: 24px; color: var(--p-accent); margin-top: 22px; }
.investigation-journey h3 { font-size: 15px; font-weight: 600; margin-top: 13px; }
.investigation-journey p { font-size: 12px; line-height: 1.95; color: var(--p-muted); margin-block: 10px 21px; }
.journey-context { display: block; width: 100%; font-size: 10px; line-height: 1.9; color: var(--p-subtle); border-top: 1px solid var(--p-line); padding-top: 16px; margin-top: auto; }
.case-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 25px; margin-block: 48px 20px; }
.case-heading h3 { font-size: 23px; font-weight: 600; letter-spacing: -.5px; margin-top: 12px; }
.case-selector { display: flex; flex-wrap: wrap; gap: 7px; flex-shrink: 0; }
.case-selector button { font: inherit; color: var(--p-muted); background: var(--p-surface); border: 1px solid var(--p-line); border-radius: 7px; padding: 9px 13px; font-size: 11px; cursor: pointer; }
.case-selector button[aria-pressed="true"] { color: var(--p-on-accent); border-color: var(--p-accent); background: var(--p-accent); }
:is(a, button):focus-visible { outline: 2px solid var(--p-accent); outline-offset: 4px; }
.case-question { border: 1px solid var(--p-line); border-radius: 10px; padding: 22px 25px; background: var(--p-surface); }
.case-question > span { display: flex; align-items: center; gap: 7px; color: var(--p-accent); font-size: 10px; }
.case-question p { font-size: 15px; line-height: 1.85; margin-block: 11px; }
.case-question > div { display: flex; flex-wrap: wrap; gap: 8px 18px; color: var(--p-subtle); font-size: 10px; }
.path-comparison { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-top: 18px; }
.path-comparison article { border: 1px solid var(--p-line); border-radius: 10px; padding: 28px; display: flex; flex-direction: column; }
.path-comparison .agent-path { background: linear-gradient(130deg, var(--p-accent-wash), var(--p-surface) 75%); }
.comparison-title > span { color: var(--p-subtle); font-size: 9px; letter-spacing: 1.1px; }
.agent-path .comparison-title > span { color: var(--p-accent); }
.comparison-title h4 { font-size: 19px; font-weight: 600; margin-top: 9px; }
.path-comparison ol { list-style: none; display: grid; gap: 22px; margin-block: 26px; }
.path-comparison li { display: flex; align-items: flex-start; gap: 13px; }
.path-comparison li > span { width: 25px; height: 25px; flex-shrink: 0; display: grid; place-items: center; border: 1px solid var(--p-line); border-radius: 6px; color: var(--p-subtle); font-size: 9px; }
.agent-path li > span { color: var(--p-accent); background: var(--p-accent-wash); }
.path-comparison h5 { font-size: 13px; font-weight: 600; margin-top: 1px; }
.path-comparison li p { color: var(--p-muted); font-size: 12px; line-height: 1.95; margin-top: 5px; }
.path-result { font-size: 11px; line-height: 1.9; color: var(--p-subtle); padding-top: 17px; border-top: 1px solid var(--p-line); margin-top: auto; }
.agent-path .path-result { color: var(--p-accent); }
.answer-preview { border: 1px solid var(--p-line); border-radius: 10px; margin-top: 18px; padding: 22px 25px; }
.answer-heading { display: flex; align-items: center; justify-content: space-between; gap: 15px; }
.answer-heading > span:first-child { font-size: 13px; font-weight: 600; }
.answer-heading > span:last-child { font-size: 9px; color: var(--p-subtle); }
.answer-preview dl { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 25px; margin-top: 20px; }
.answer-preview dt { font-size: 11px; color: var(--p-accent); }
.answer-preview dd { color: var(--p-muted); font-size: 11px; line-height: 1.95; margin-top: 8px; }
.case-note { font-size: 10px; line-height: 1.95; color: var(--p-subtle); margin-top: 12px; }
.review-panel { display: grid; grid-template-columns: .85fr 1.15fr; border: 1px solid var(--p-line); border-radius: 12px; overflow: hidden; margin-top: 40px; }
.review-story { padding: 32px; background: var(--p-surface); border-right: 1px solid var(--p-line); }
.review-story .path-eyebrow { font-size: 9px; }
.review-story h3 { font-size: 24px; font-weight: 600; line-height: 1.6; margin-top: 15px; }
.review-story p { font-size: 12px; color: var(--p-muted); line-height: 1.95; margin-top: 13px; }
.review-story a { display: inline-flex; align-items: center; gap: 8px; color: var(--p-accent); font-size: 11px; margin-top: 22px; text-decoration: none; }
.review-details { padding: 30px; }
.review-questions > span { color: var(--p-subtle); font-size: 11px; }
.review-questions p { display: flex; align-items: center; gap: 10px; font-size: 13px; margin-top: 16px; }
.review-questions .el-icon { color: var(--p-accent); font-size: 14px; flex-shrink: 0; }
.review-boundaries { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 23px; border-top: 1px solid var(--p-line); padding-top: 23px; margin-top: 25px; }
.review-boundaries h4 { font-size: 12px; font-weight: 600; }
.review-boundaries p { font-size: 11px; line-height: 1.95; color: var(--p-muted); margin-top: 8px; }
@media (max-width: 1150px) { .troubleshooting-section { width: calc(100% - 64px); } .path-heading > p { font-size: 12px; } .investigation-journey li { padding: 23px; } .investigation-journey h3 { font-size: 13px; } .investigation-journey p { font-size: 11px; } .journey-context { font-size: 9px; } .case-heading h3 { font-size: 21px; } }
@media (max-width: 900px) { .troubleshooting-section { padding-top: 74px; } .path-heading h2 { font-size: 30px; } .path-heading > p { max-width: 300px; font-size: 11px; } .investigation-journey { grid-template-columns: repeat(2, minmax(0, 1fr)); } .investigation-journey li:nth-child(3) { border-left: 0; } .investigation-journey li:nth-child(n+3) { border-top: 1px solid var(--p-line); } .investigation-journey h3 { font-size: 15px; } .investigation-journey p { font-size: 12px; } .case-heading { align-items: flex-start; flex-direction: column; gap: 18px; } .comparison-title h4 { font-size: 16px; } .path-comparison article { padding: 23px; } .answer-preview dl { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px 25px; } .review-panel { grid-template-columns: 1fr; } .review-story { border-right: 0; border-bottom: 1px solid var(--p-line); } .review-story h3 br { display: none; } }
@media (max-width: 640px) { .troubleshooting-section { width: calc(100% - 40px); padding-top: 60px; scroll-margin-top: 80px; } .path-heading { display: block; margin-bottom: 25px; } .path-heading h2 { font-size: 27px; letter-spacing: -1px; margin-top: 12px; } .path-eyebrow { font-size: 10px; letter-spacing: 1.3px; } .path-heading > p { max-width: none; margin-top: 17px; font-size: 11px; } .investigation-journey { grid-template-columns: 1fr; } .investigation-journey li + li { border-left: 0; border-top: 1px solid var(--p-line); } .investigation-journey li { padding: 24px; } .journey-icon { margin-top: 15px; } .journey-context { font-size: 10px; margin-top: 16px; padding-top: 13px; } .case-heading { margin-top: 35px; } .case-heading h3 { font-size: 19px; line-height: 1.7; } .case-selector button { font-size: 10px; padding: 9px 12px; } .case-question { padding: 21px; } .case-question p { font-size: 13px; } .case-question > div { font-size: 9px; line-height: 1.9; } .path-comparison { grid-template-columns: 1fr; gap: 12px; margin-top: 12px; } .path-comparison article { padding: 23px; } .comparison-title h4 { font-size: 17px; } .path-comparison ol { gap: 20px; margin-block: 22px; } .path-comparison h5 { font-size: 12px; } .path-comparison li p { font-size: 11px; } .path-result { font-size: 10px; } .answer-preview { margin-top: 12px; padding: 22px; } .answer-heading { flex-wrap: wrap; gap: 7px; } .answer-heading > span:first-child { font-size: 12px; } .answer-preview dl { grid-template-columns: 1fr; gap: 17px; } .answer-preview dd { margin-top: 4px; } .case-note { font-size: 9px; } .review-panel { margin-top: 30px; } .review-story, .review-details { padding: 24px; } .review-story .path-eyebrow { font-size: 10px; } .review-story h3 { font-size: 21px; } .review-story h3 br { display: initial; } .review-questions p { font-size: 12px; } .review-boundaries { grid-template-columns: 1fr; gap: 20px; } }
</style>
