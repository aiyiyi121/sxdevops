<template>
  <div ref="pageRoot" class="product-intro" @click="onPageAnchorClick">
    <a class="skip-link" href="#product-main">跳到主要内容</a>
    <header class="site-header">
      <div class="page-width header-inner">
        <a class="brand" href="#top" aria-label="SxDevOps 首页" @click="mobileMenu = false">
          <span class="brand-symbol"><img :src="brandMark" alt="" width="46" height="46" /></span>
          <span>SxDevOps<span class="brand-version">v2</span></span>
        </a>
        <button class="menu-toggle" type="button" :aria-expanded="mobileMenu" aria-controls="product-nav" :aria-label="mobileMenu ? '关闭导航' : '打开导航'" @click="mobileMenu = !mobileMenu">
          <el-icon><Close v-if="mobileMenu" /><Menu v-else /></el-icon>
        </button>
        <nav id="product-nav" class="main-nav" :class="{ 'is-open': mobileMenu }" aria-label="产品导航">
          <a v-for="item in navigation" :key="item.id" :href="`#${item.id}`" :aria-current="activeSection === item.id ? 'location' : undefined">{{ item.label }}</a>
        </nav>
        <a class="header-github" :href="repository" target="_blank" rel="noopener noreferrer" aria-label="在 GitHub 查看 SxDevOps 源码">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 .9a11.1 11.1 0 0 0-3.51 21.63c.56.1.76-.24.76-.54v-2.07c-3.1.67-3.75-1.32-3.75-1.32-.5-1.29-1.24-1.64-1.24-1.64-1.01-.69.08-.68.08-.68 1.12.08 1.71 1.15 1.71 1.15.99 1.7 2.6 1.21 3.23.92.1-.72.39-1.21.71-1.49-2.47-.28-5.07-1.24-5.07-5.49 0-1.21.43-2.2 1.14-2.98-.11-.28-.5-1.41.11-2.94 0 0 .93-.3 3.05 1.14a10.6 10.6 0 0 1 5.55 0c2.12-1.44 3.05-1.14 3.05-1.14.61 1.53.22 2.66.11 2.94.71.78 1.14 1.77 1.14 2.98 0 4.26-2.6 5.21-5.08 5.49.4.35.75 1.02.75 2.06v3.07c0 .3.2.65.77.54A11.1 11.1 0 0 0 12 .9Z" /></svg>
          <span class="github-label">GitHub</span>
          <span class="repository-stars" :aria-label="`GitHub Star 数：${starsLabel}`"><span aria-hidden="true">☆</span>{{ starsLabel }}</span>
          <el-icon><TopRight /></el-icon>
        </a>
      </div>
    </header>

    <main id="product-main">
      <section id="top" class="hero-section">
        <div class="hero-grid" aria-hidden="true"></div>
        <div class="page-width hero-layout">
          <div class="hero-copy">
            <a class="release-pill" :href="`${repository}/blob/main/docs/releases/v2.0.0.md`" target="_blank" rel="noopener noreferrer">
              <span>v2.0.0</span> 从资产底座，到智能运维 <el-icon><ArrowRight /></el-icon>
            </a>
            <p class="eyebrow hero-eyebrow"><span></span> 开源 · 智能运维平台</p>
            <h1>看清每个异常，<br />让<span class="hero-accent">行动有据可依。</span></h1>
            <p class="hero-description">把资产、可观测数据与运维任务连成一条线。<br class="desktop-break" />让 AI 帮你找证据、理思路，把关键决策留给你。</p>
            <div class="hero-actions">
              <router-link class="button button-primary" to="/dashboard">进入工作台 <el-icon><ArrowRight /></el-icon></router-link>
              <a class="button button-secondary" href="#screenshots"><el-icon><Monitor /></el-icon> 看看真实界面</a>
            </div>
            <div class="hero-footnote"><span><el-icon><CircleCheck /></el-icon> MIT 开源</span><span><el-icon><CircleCheck /></el-icon> 支持私有部署</span><span><el-icon><CircleCheck /></el-icon> 关键动作人工确认</span></div>
          </div>

          <div class="scenario-wrap">
            <div class="scenario-orbit" aria-hidden="true"></div>
            <div class="scenario-window">
              <div class="window-topline">
                <div class="window-identity"><span class="agent-mark"><el-icon><MagicStick /></el-icon></span><strong>SxDevOps Agent</strong></div>
                <span class="demo-badge">交互示意</span>
              </div>
              <div class="scenario-switch" role="group" aria-label="切换运维场景">
                <button v-for="(scenario, index) in scenarios" :key="scenario.title" type="button" :aria-pressed="scenarioIndex === index" @click="selectScenario(index)">{{ scenario.title }}</button>
              </div>
              <div class="scenario-content" aria-live="polite">
                <div class="context-line"><span class="status-dot"></span>{{ currentScenario.context }}<span class="context-label">范围已明确</span></div>
                <div class="user-question"><span class="user-avatar">你</span><p>{{ currentScenario.question }}</p></div>
                <div class="evidence-heading"><span><el-icon><Connection /></el-icon> 汇集证据</span><span>{{ currentScenario.sources.length }} 类来源</span></div>
                <div class="evidence-list">
                  <div v-for="source in currentScenario.sources" :key="source.name" class="evidence-row"><span class="evidence-check"><el-icon><Check /></el-icon></span><span>{{ source.name }}</span><span>{{ source.result }}</span></div>
                </div>
                <div class="agent-insight"><span class="insight-label">分析与建议</span><p>{{ currentScenario.insight }}</p><div class="source-tags"><span v-for="tag in currentScenario.tags" :key="tag">{{ tag }}</span></div></div>
                <div class="confirmation-card" :class="{ 'is-previewed': confirmationPreview }">
                  <span class="confirmation-icon"><el-icon><CircleCheck v-if="confirmationPreview" /><Lock v-else /></el-icon></span>
                  <div><strong>{{ confirmationPreview ? '确认后，交由任务中心执行' : '下一步：生成任务草稿' }}</strong><span>{{ confirmationPreview ? '执行记录与结果回到审计链路' : '检查目标与参数，由你决定是否执行' }}</span></div>
                  <button type="button" :aria-pressed="confirmationPreview" @click="confirmationPreview = !confirmationPreview">{{ confirmationPreview ? '返回' : '预览流程' }}<el-icon><ArrowRight /></el-icon></button>
                </div>
              </div>
              <div class="window-footer"><span class="status-dot"></span> 先有证据，再有行动 <span>场景 / {{ String(scenarioIndex + 1).padStart(2, '0') }}</span></div>
            </div>
            <p class="scenario-caption">交互流程示意；实际查询与执行在登录后的工作台发起。</p>
          </div>
        </div>
        <div class="page-width value-strip">
          <div><span class="strip-number">01</span><p><strong>统一上下文</strong><span>知道资源在哪，也知道归谁管</span></p></div>
          <div><span class="strip-number">02</span><p><strong>让证据说话</strong><span>指标、日志、链路与事件一起看</span></p></div>
          <div><span class="strip-number">03</span><p><strong>把动作管住</strong><span>权限、人工确认与审计贯穿执行</span></p></div>
        </div>
      </section>

      <section class="integration-section page-width" aria-label="可对接的工具与数据源">
        <p>连接已有工具，让数据发挥更大价值</p>
        <div class="integration-list"><span>Prometheus</span><span>Grafana</span><span>Loki / ELK</span><span>SkyWalking</span><span>Kubernetes</span><span>Docker</span><span>Jenkins</span><span class="integration-more">+ MCP</span></div>
      </section>

      <section id="capabilities" class="section-block page-width">
        <div class="section-heading"><div><p class="eyebrow">{{ sectionLabel('capabilities') }}</p><h2>一个工作台，<br />连接你的运维现场。</h2></div><p class="section-description">从资源归属到异常取证，从日常巡检到变更留痕。<br />把分散的能力组织起来，为每次判断提供上下文。</p></div>
        <div class="capability-grid">
          <article class="capability-card capability-featured">
            <span class="feature-icon"><el-icon><MagicStick /></el-icon></span><span class="card-kicker">智能运维助手</span><h3>让 AI 带着证据工作</h3><p>用自然语言发起分析，联合可观测数据与资源上下文，输出依据、风险和建议，进一步生成可确认的任务草稿。</p>
            <div class="agent-pipeline" aria-label="智能体工作链路"><span>理解问题</span><el-icon><ArrowRight /></el-icon><span>工具取证</span><el-icon><ArrowRight /></el-icon><span>结构化结论</span></div>
            <div class="feature-bottom"><span>LangGraph</span><span>MCP 工具</span><span>可复用 Skills</span></div>
          </article>
          <article v-for="feature in features" :key="feature.title" class="capability-card" :class="feature.className">
            <span class="feature-icon"><el-icon><component :is="feature.icon" /></el-icon></span><span class="card-kicker">{{ feature.eyebrow }}</span><h3>{{ feature.title }}</h3><p>{{ feature.description }}</p><div class="feature-bottom"><span v-for="tag in feature.tags" :key="tag">{{ tag }}</span></div>
          </article>
        </div>
      </section>

      <ProductPrinciples />

      <section id="workflow" class="workflow-section">
        <div class="page-width">
          <div class="section-heading"><div><p class="eyebrow">{{ sectionLabel('workflow') }}</p><h2>思而后行，<span class="accent-text">行必有证。</span></h2></div><p class="section-description">模型负责理解与规划，平台负责权限与执行。<br />从发现异常到复盘，让每一步都能被追溯。</p></div>
          <ol class="workflow-steps">
            <li v-for="(step, index) in workflow" :key="step.title"><span class="step-number">0{{ index + 1 }}</span><span class="step-node"><el-icon><component :is="step.icon" /></el-icon></span><h3>{{ step.title }}</h3><p>{{ step.description }}</p></li>
          </ol>
          <div class="boundary-strip"><span class="boundary-icon"><el-icon><Lock /></el-icon></span><p><strong>执行有边界，结论有依据。</strong><span>操作沿用平台 RBAC 与确认机制；查询失败、权限不足和证据缺失会明确展示。</span></p><a :href="`${repository}/blob/main/docs/AIOps-LangGraph-试点说明.md`" target="_blank" rel="noopener noreferrer">了解运行机制 <el-icon><TopRight /></el-icon></a></div>
        </div>
      </section>

      <ProductTroubleshooting @show-events="screenshotIndex = screenshots.findIndex(shot => shot.id === 'events')" />
      <ProductDeepDive />

      <section id="screenshots" class="section-block page-width screenshots-section">
        <div class="section-heading"><div><p class="eyebrow">{{ sectionLabel('screenshots') }}</p><h2>能力不止于介绍，<br />打开就能看见。</h2></div><p class="section-description">真实产品截图，呈现各模块的工作方式。<br />切换查看，点击图片可放大浏览。</p></div>
        <div class="gallery-selectors" role="group" aria-label="选择产品界面"><button v-for="(shot, index) in screenshots" :key="shot.id" type="button" :aria-pressed="screenshotIndex === index" @click="screenshotIndex = index"><el-icon><component :is="shot.icon" /></el-icon>{{ shot.label }}</button></div>
        <div class="gallery-frame">
          <div class="gallery-topline"><div class="window-dots" aria-hidden="true"><i></i><i></i><i></i></div><span>{{ currentScreenshot.path }}</span><span class="gallery-counter">{{ String(screenshotIndex + 1).padStart(2, '0') }} / {{ String(screenshots.length).padStart(2, '0') }}</span></div>
          <button class="screenshot-button" :class="{ 'is-archived': currentScreenshot.archived }" type="button" :aria-label="`放大查看${currentScreenshot.label}截图`" @click="openLightbox(screenshotIndex)"><img :src="currentScreenshot.src" :alt="currentScreenshot.alt" width="1600" :height="currentScreenshot.archived ? 1000 : 803" loading="lazy" decoding="async" /><span class="zoom-hint"><el-icon><FullScreen /></el-icon> 点击查看大图</span></button>
          <div class="gallery-caption" aria-live="polite"><div><h3>{{ currentScreenshot.title }}</h3><p>{{ currentScreenshot.description }}</p></div><span class="real-capture"><span class="status-dot"></span> 真实界面</span></div>
        </div>
        <p class="gallery-note">{{ currentScreenshot.archived ? '功能截图展示模块工作方式，当前界面样式以工作台为准。' : '截图展示已实现功能，界面细节随版本持续迭代。' }}</p>
      </section>

      <ProductResources>
        <div class="start-grid">
          <div class="start-main"><span class="card-kicker">从这里开始</span><h3>你的基础设施，<br />你的运维工作台。</h3><p>支持 Docker Compose 与 Kubernetes 部署。<br />按部署指南配置环境，再逐步连接 CMDB、可观测数据与 AI 模型。</p><div class="start-actions"><a class="button button-primary" href="/login" target="_blank" rel="noopener noreferrer">在线体验 <el-icon><TopRight /></el-icon></a><a class="text-link" :href="repository" target="_blank" rel="noopener noreferrer">查看源码 <el-icon><ArrowRight /></el-icon></a></div><span class="license-note">MIT 开源许可 · 自由使用，欢迎共建</span></div>
          <div class="start-resources">
            <div class="clone-block"><div><span><el-icon><FolderOpened /></el-icon> 获取源码</span><button type="button" @click="copyCloneCommand">{{ copyState === 'copied' ? '已复制' : copyState === 'failed' ? '请手动复制' : '复制命令' }}</button></div><pre><code>{{ cloneCommand }}</code></pre><span class="sr-only" role="status">{{ copyState === 'copied' ? '源码命令已复制到剪贴板' : copyState === 'failed' ? '无法访问剪贴板，请选中命令手动复制' : '' }}</span></div>
            <a v-for="resource in resources" :key="resource.title" class="resource-link" :href="resource.href" target="_blank" rel="noopener noreferrer"><span class="resource-icon"><el-icon><component :is="resource.icon" /></el-icon></span><div><h3>{{ resource.title }}</h3><p>{{ resource.description }}</p></div><el-icon><TopRight /></el-icon></a>
          </div>
        </div>
      </ProductResources>

      <section class="closing-section page-width"><span class="closing-label">为真实运维现场而建</span><h2>少一些来回切换，<br /><span>多一些有据可依。</span></h2><router-link class="button button-primary" to="/dashboard">开始探索 SxDevOps <el-icon><ArrowRight /></el-icon></router-link><div class="closing-orbit" aria-hidden="true"></div></section>
    </main>

    <footer class="site-footer page-width"><a class="brand footer-brand" href="#top"><img :src="brandMark" alt="" width="36" height="36" />SxDevOps</a><p>开源智能运维 Agent 平台</p><nav aria-label="页脚导航"><a :href="`${repository}/blob/main/LICENSE`" target="_blank" rel="noopener noreferrer">MIT License</a><a :href="`${repository}/issues`" target="_blank" rel="noopener noreferrer">反馈与共建 <el-icon><TopRight /></el-icon></a><a href="#top">回到顶部 ↑</a></nav></footer>

    <dialog ref="lightbox" class="screenshot-dialog" aria-label="产品截图大图预览" @click="onBackdropClick" @close="lightboxIndex = null" @keydown.left.prevent="moveLightbox(-1)" @keydown.right.prevent="moveLightbox(1)">
      <template v-if="lightboxScreenshot"><div class="lightbox-toolbar"><strong>{{ lightboxScreenshot.label }}</strong><span>{{ (lightboxIndex ?? 0) + 1 }} / {{ screenshots.length }}</span><button type="button" aria-label="关闭大图" @click="lightbox.close()"><el-icon><Close /></el-icon></button></div><img :src="lightboxScreenshot.src" :alt="lightboxScreenshot.alt" /><div class="lightbox-bottom"><button type="button" aria-label="上一张截图" @click="moveLightbox(-1)"><el-icon><ArrowLeft /></el-icon> 上一张</button><p>{{ lightboxScreenshot.title }}</p><button type="button" aria-label="下一张截图" @click="moveLightbox(1)">下一张 <el-icon><ArrowRight /></el-icon></button></div></template>
    </dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, Box, Check, CircleCheck, Close, Connection, Cpu, DataAnalysis, Document, Finished, FolderOpened, FullScreen, Lock, MagicStick, Menu, Monitor, Search, Tickets, TopRight } from '@element-plus/icons-vue'
import brandMark from '@/assets/brand-mark.png'
import ProductDeepDive from '@/components/product/ProductDeepDive.vue'
import ProductResources from '@/components/product/ProductResources.vue'
import ProductTroubleshooting from '@/components/product/ProductTroubleshooting.vue'
import ProductPrinciples from '@/components/product/ProductPrinciples.vue'
import { productSections, sectionLabel } from '@/components/product/sections'
import { useRepositoryStars } from '@/composables/useRepositoryStars'

const repository = 'https://github.com/aiyiyi121/sxdevops'
const { starsLabel } = useRepositoryStars()
const navigation = productSections.filter(section => section.navigation)
const mobileMenu = ref(false)
const pageRoot = ref(null)
const activeSection = ref('')
const router = useRouter()
const route = useRoute()
let scrollFrame = 0

function onPageAnchorClick(event) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  const anchor = event.target.closest('a[href^="#"]')
  if (!anchor || !pageRoot.value?.contains(anchor)) return
  const hash = anchor.getAttribute('href')
  if (!hash || hash === '#' || !document.getElementById(hash.slice(1))) return
  event.preventDefault()
  mobileMenu.value = false
  router.push({ path: route.path, query: route.query, hash })
}

function updateActiveSection() {
  scrollFrame = 0
  const threshold = (pageRoot.value?.querySelector('.site-header')?.offsetHeight || 82) + window.innerHeight * 0.25
  activeSection.value = navigation.reduce((current, item) => {
    const section = document.getElementById(item.id)
    return section && section.getBoundingClientRect().top <= threshold ? item.id : current
  }, '')
}
function scheduleActiveSection() {
  if (!scrollFrame) scrollFrame = window.requestAnimationFrame(updateActiveSection)
}
onMounted(() => {
  updateActiveSection()
  window.addEventListener('scroll', scheduleActiveSection, { passive: true })
  window.addEventListener('resize', scheduleActiveSection)
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', scheduleActiveSection)
  window.removeEventListener('resize', scheduleActiveSection)
  if (scrollFrame) window.cancelAnimationFrame(scrollFrame)
})
const scenarioIndex = ref(0)
const confirmationPreview = ref(false)
const scenarios = [
  { title: '服务排障', context: '生产环境 / order-center', question: '订单服务的错误率升高了，帮我结合日志和最近变更分析原因。', sources: [{ name: '指标与告警', result: '错误率出现上升' }, { name: '应用日志', result: '发现连接池超时' }, { name: '事件与变更', result: '关联近期发布记录' }], insight: '异常时间与近期变更重合，日志中出现连接池超时。建议先检查连接与配置，再决定下一步处置。', tags: ['时间线关联', '保留证据', '待确认建议'] },
  { title: 'K8s 诊断', context: '生产集群 / production / order-api', question: '这个 Pod 最近频繁重启，帮我看看事件、日志和资源情况。', sources: [{ name: 'Pod 状态', result: '最近发生多次重启' }, { name: '集群事件', result: '发现 OOMKilled 记录' }, { name: '资源用量', result: '内存接近配置上限' }], insight: '退出记录与内存用量提示资源压力。建议结合历史峰值检查配置，调整前先查看 YAML 差异与预检结果。', tags: ['集群范围约束', '资源证据', '变更预检'] },
  { title: '主机巡检', context: '生产资源组 / web-servers', question: '帮我给这组主机做一次只读巡检，重点看磁盘和核心服务状态。', sources: [{ name: 'CMDB 资产', result: '明确目标资源与归属' }, { name: '执行资源', result: '检查任务资源关联' }, { name: '巡检模板', result: '准备磁盘与服务检查' }], insight: '根据目标资源准备巡检草稿，展示检查项与执行范围。确认后在任务中心执行，再查看逐台主机的返回结果。', tags: ['目标可核对', '模板复用', '执行可追踪'] },
]
const currentScenario = computed(() => scenarios[scenarioIndex.value])
function selectScenario(index) { scenarioIndex.value = index; confirmationPreview.value = false }

const features = [
  { eyebrow: '资产底座', title: 'CMDB，让资源有上下文', icon: Connection, description: '统一资产台账、业务与环境资源树，连接同步、容量和拓扑。把资产信息衔接到任务执行资源。', tags: ['统一资产', '资源拓扑', '容量治理'], className: 'capability-cmdb' },
  { eyebrow: '可观测性', title: '从信号中找到线索', icon: DataAnalysis, description: '汇集指标、日志、链路、告警与 Grafana 看板，结合事件时间线，为排障提供多维证据。', tags: ['Metrics', 'Logs', 'Traces'], className: 'capability-observe' },
  { eyebrow: '容器管理', title: 'Kubernetes 与 Docker，一处管理', icon: Box, description: '资源管理、容量概览、交互终端与历史日志集中呈现；K8s YAML 变更先预检，再确认。', tags: ['范围授权', 'YAML 差异', '终端与日志'] },
  { eyebrow: '任务与事件', title: '任务有去向，事件可复盘', icon: Tickets, description: '用巡检、批量命令与脚本模板承接操作，让执行历史、关键写入和失败线索回到事件与审计链路。', tags: ['任务草稿', '执行历史', '事件中心'] },
  { eyebrow: '协作与治理', title: '协作与权限，一起落地', icon: Lock, description: '工单审批、发布与 SQL 审计连接团队流程。后端 API、页面操作和 WebSocket 统一接入 RBAC。', tags: ['工单审批', 'RBAC', '操作审计'] },
]
const workflow = [
  { title: '发现异常', icon: Monitor, description: '从态势、告警或具体问题进入现场。' },
  { title: '汇集证据', icon: Search, description: '查询日志、指标、链路与变更记录。' },
  { title: '形成建议', icon: MagicStick, description: '整理依据、风险与可核对的任务草稿。' },
  { title: '确认执行', icon: Check, description: '检查权限与目标，确认后交给平台执行。' },
  { title: '留痕复盘', icon: Finished, description: '查看执行与审计，按配置验证告警恢复。' },
]
const screenshots = [
  { id: 'assistant', label: '智能助手', icon: MagicStick, path: 'workspace / aiops / chat', src: '/promo/v2/assistant.webp', title: '用一个问题，打开有上下文的运维分析', description: '围绕资源与证据展开对话，查看分析依据、建议与后续操作入口。', alt: '智能助手真实产品截图：历史会话、分析结论、证据明细和对话输入区' },
  { id: 'posture', label: '系统态势', icon: Monitor, path: 'workspace / dashboard / sla', src: '/promo/v2/posture.webp', title: '先看全局态势，再收敛故障边界', description: '按环境与系统查看 SLA 历史和当前状态，区分故障、未知与数据缺口。', alt: '系统态势功能截图：环境分组、系统 SLA 历史条带与当前状态', archived: true },
  { id: 'observability', label: '可观测总览', icon: DataAnalysis, path: 'workspace / observability / overview', src: '/promo/v2/observability.webp', title: '告警、日志、Trace 与看板，从同一入口展开', description: '汇集可观测性摘要、工具入口与最近活动，为排查提供连续的事实来源。', alt: '可观测性总览功能截图：日志、告警、链路追踪与 Grafana 摘要', archived: true },
  { id: 'events', label: '事件中心', icon: Connection, path: 'workspace / events / timeline', src: '/promo/v2/events.webp', title: '异常前后发生了什么，回到时间线里找', description: '按环境、系统、服务、事件源与时间查看变更和执行记录，追踪最终结果与失败线索。', alt: '事件中心功能截图：环境筛选、事件时间线、应用发布与运维任务记录', archived: true },
  { id: 'cmdb', label: 'CMDB', icon: Connection, path: 'workspace / cmdb', src: '/promo/v2/cmdb.webp', title: '先把资产看清，再把上下文连起来', description: '资产总览、业务归属、容量水位与治理入口，统一理解你的基础设施。', alt: 'CMDB 真实产品截图：资源树、资产总览、业务归属、容量与资源治理面板' },
  { id: 'logs', label: '日志检索', icon: DataAnalysis, path: 'workspace / observability / logs', src: '/promo/v2/logs.webp', title: '从异常趋势，追到具体日志', description: '组合数据源与查询条件，查看趋势、日志内容与关联上下文。', alt: '日志中心真实产品截图：数据源筛选、查询条件、日志趋势柱状图与结果列表' },
  { id: 'kubernetes', label: 'Kubernetes', icon: Box, path: 'workspace / containers / kubernetes', src: '/promo/v2/kubernetes.webp', title: '多集群资源，集中放进一个工作台', description: '从集群概况进入工作负载、资源与终端，结合授权范围开展操作。', alt: 'Kubernetes 工作台真实产品截图：集群卡片、资源入口、集群概要和容量统计' },
  { id: 'docker', label: 'Docker', icon: Cpu, path: 'workspace / containers / docker', src: '/promo/v2/docker.webp', title: '容器、镜像与环境，切换更顺手', description: '按环境查看容器与镜像，支持分页搜索、交互终端及历史日志。', alt: 'Docker 工作台真实产品截图：环境信息、容器列表、运行状态、镜像和操作入口' },
  { id: 'audit', label: '智能体审计', icon: Search, path: 'workspace / aiops / audit', src: '/promo/v2/audit.webp', title: '让智能体的工作过程可以被检查', description: '查看会话、工具调用与执行记录，把分析过程与最终动作串起来。', alt: '智能体审计真实产品截图：会话查询、执行记录、状态、工具调用和明细入口' },
  { id: 'execution', label: '任务执行', icon: Tickets, path: 'workspace / tasks / execution', src: '/promo/v2/execution.webp', title: '每一次执行，都有结果可查', description: '查看执行明细与逐项返回内容，为后续验证与复盘保留依据。', alt: '任务执行真实产品截图：执行详情弹窗、目标资源、状态和执行结果' },
  { id: 'settings', label: '工作台主题', icon: Monitor, path: 'workspace / settings', src: '/promo/v2/settings.webp', title: '按你的习惯，调整工作台', description: '浅色、炭灰和深蓝灰三套主题，支持网站名称、图标与菜单显示配置。', alt: '炭灰主题系统设置真实产品截图：网站名称、图标配置、菜单列表和显示开关' },
]
const screenshotIndex = ref(0)
const currentScreenshot = computed(() => screenshots[screenshotIndex.value])
const lightbox = ref(null)
const lightboxIndex = ref(null)
const lightboxScreenshot = computed(() => lightboxIndex.value === null ? null : screenshots[lightboxIndex.value])
async function openLightbox(index) { lightboxIndex.value = index; await nextTick(); lightbox.value.showModal() }
function moveLightbox(direction) { if (lightboxIndex.value !== null) lightboxIndex.value = (lightboxIndex.value + direction + screenshots.length) % screenshots.length }
function onBackdropClick(event) { if (event.target === lightbox.value) lightbox.value.close() }
onBeforeUnmount(() => { if (lightbox.value?.open) lightbox.value.close() })

const resources = [
  { title: 'Docker Compose 部署', description: '从源码构建，启动应用与配套服务', icon: Box, href: `${repository}#快速启动` },
  { title: 'Kubernetes 部署指南', description: '镜像、存储、配置与 worker 补充说明', icon: Connection, href: `${repository}/blob/main/docs/Kubernetes部署指南.md` },
  { title: '平台使用文档', description: '了解模块能力、使用方法与典型场景', icon: Document, href: `${repository}/blob/main/docs/用户使用文档.md` },
]
const cloneCommand = 'git clone https://github.com/aiyiyi121/sxdevops.git\ncd sxdevops'
const copyState = ref('idle')
async function copyCloneCommand() { try { await navigator.clipboard.writeText(cloneCommand); copyState.value = 'copied' } catch { copyState.value = 'failed' } }
</script>

<style scoped>
.product-intro {
  --p-bg: light-dark(#0c0f12, #0c0f12);
  --p-surface: light-dark(#13181d, #13181d);
  --p-raised: light-dark(#192126, #192126);
  --p-ink: light-dark(#f1f5f3, #f1f5f3);
  --p-muted: light-dark(#a4afaf, #a4afaf);
  --p-subtle: light-dark(#82918f, #82918f);
  --p-line: light-dark(#283237, #283237);
  --p-accent: light-dark(#a6efd0, #a6efd0);
  --p-on-accent: light-dark(#102c24, #102c24);
  --p-accent-wash: light-dark(#163029, #163029);
  --p-cyan: light-dark(#9bcddd, #9bcddd);
  --p-shade: light-dark(#070a0c, #070a0c);
  --p-translucent: light-dark(#0c0f12ed, #0c0f12ed);
  color-scheme: dark;
  min-height: 100vh;
  background: var(--p-bg);
  color: var(--p-ink);
  font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  line-height: 1.6;
  overflow: clip;
}
.product-intro *, .product-intro *::before, .product-intro *::after { box-sizing: border-box; }
.product-intro a { color: inherit; text-decoration: none; }
.product-intro button { font: inherit; color: inherit; cursor: pointer; }
.product-intro button, .product-intro a { -webkit-tap-highlight-color: transparent; }
.product-intro :is(button, a):focus-visible { outline: 2px solid var(--p-accent); outline-offset: 5px; }
.product-intro ::selection { color: var(--p-on-accent); background: var(--p-accent); }
.product-intro .el-icon { flex-shrink: 0; }
.page-width { width: min(1240px, calc(100% - 96px)); margin-inline: auto; }
.product-intro section[id] { scroll-margin-top: 95px; }
.skip-link { position: fixed; top: -90px; left: 20px; z-index: 30; padding: 10px 20px; background: var(--p-accent); color: var(--p-on-accent) !important; border-radius: 8px; }
.skip-link:focus { top: 12px; }
.site-header { position: sticky; top: 0; z-index: 20; border-bottom: 1px solid var(--p-line); background: var(--p-translucent); backdrop-filter: blur(18px); }
.header-inner { display: flex; align-items: center; justify-content: space-between; gap: 32px; height: 82px; }
.brand { display: inline-flex; align-items: center; gap: 9px; font-size: 21px; font-weight: 750; letter-spacing: -.6px; white-space: nowrap; }
.brand-symbol { width: 43px; height: 43px; display: grid; place-items: center; flex-shrink: 0; background: var(--p-raised); border: 1px solid var(--p-line); border-radius: 12px; }
.brand-symbol img { width: 100%; height: 100%; object-fit: contain; }
.brand-version { font-size: 11px; color: var(--p-accent); margin-left: 8px; letter-spacing: 0; font-weight: 500; vertical-align: super; }
.main-nav { display: flex; align-items: center; gap: 17px; margin-left: auto; }
.main-nav a { position: relative; font-size: 13px; color: var(--p-muted); transition: color .2s; white-space: nowrap; }
.main-nav a::after { content: ''; position: absolute; inset-inline: 0; bottom: -10px; height: 2px; border-radius: 2px; background: var(--p-accent); transform: scaleX(0); transition: transform .25s ease; }
.main-nav a[aria-current="location"] { color: var(--p-accent); }
.main-nav a[aria-current="location"]::after { transform: scaleX(1); }
.main-nav a:hover, .text-link:hover, .site-footer a:hover { color: var(--p-accent); }
.header-github { display: inline-flex; align-items: center; gap: 9px; border: 1px solid var(--p-line); border-radius: 8px; padding: 9px 14px; font-size: 12px; background: var(--p-surface); }
.header-github svg { width: 17px; height: 17px; }
.header-github > .el-icon { color: var(--p-subtle); }
.repository-stars { display: inline-flex; align-items: center; gap: 5px; padding-left: 9px; border-left: 1px solid var(--p-line); color: var(--p-ink); font-variant-numeric: tabular-nums; white-space: nowrap; }
.repository-stars > span { color: var(--p-accent); font-size: 16px; }
.menu-toggle { display: none; background: none; border: 1px solid var(--p-line); width: 38px; height: 38px; border-radius: 8px; }
.hero-section { position: relative; isolation: isolate; padding-top: 78px; }
.hero-grid { pointer-events: none; position: absolute; z-index: -1; inset: 0; opacity: .22; background-image: linear-gradient(var(--p-line) 1px, transparent 1px), linear-gradient(90deg, var(--p-line) 1px, transparent 1px); background-size: 64px 64px; mask-image: radial-gradient(ellipse at 78% 28%, black, transparent 66%); }
.hero-layout { display: grid; grid-template-columns: 1fr 1fr; align-items: start; gap: 54px; }
.release-pill { display: inline-flex; gap: 10px; align-items: center; border: 1px solid var(--p-line); background: var(--p-surface); border-radius: 100px; padding: 6px 12px 6px 6px; font-size: 11px; color: var(--p-muted) !important; }
.release-pill > span { border-radius: 100px; padding: 2px 8px; background: var(--p-accent-wash); color: var(--p-accent); font-family: ui-monospace, monospace; font-size: 11px; }
.release-pill .el-icon { margin-left: 5px; color: var(--p-accent); }
.eyebrow { font-size: 11px; font-weight: 600; letter-spacing: 2px; color: var(--p-accent); font-family: 'Inter', ui-monospace, monospace; }
.hero-eyebrow { margin: 36px 0 18px; display: flex; align-items: center; gap: 9px; letter-spacing: 1.7px; color: var(--p-muted); }
.hero-eyebrow > span, .status-dot { display: inline-block; width: 5px; height: 5px; border-radius: 50%; background: var(--p-accent); flex-shrink: 0; }
.hero-copy h1 { font-size: clamp(38px, 4.2vw, 59px); font-weight: 760; line-height: 1.3; letter-spacing: -2.4px; white-space: nowrap; }
.hero-accent { color: var(--p-accent); }
.hero-description { color: var(--p-muted); font-size: 15px; line-height: 1.95; margin-top: 26px; }
.hero-actions { display: flex; flex-wrap: wrap; gap: 13px; margin-top: 33px; }
.button { display: inline-flex; align-items: center; justify-content: center; gap: 16px; border: 1px solid transparent; border-radius: 8px; min-height: 47px; padding: 10px 20px; font-size: 13px; font-weight: 650; transition: transform .2s, border-color .2s, background .2s; }
.button:hover { transform: translateY(-2px); }
.button-primary { background: var(--p-accent); color: var(--p-on-accent) !important; }
.button-primary:hover { background: var(--p-ink); }
.button-secondary { background: var(--p-surface); border-color: var(--p-line); }
.button-secondary:hover { border-color: var(--p-accent); }
.hero-footnote { display: flex; flex-wrap: wrap; gap: 18px; margin-top: 24px; color: var(--p-subtle); font-size: 10px; }
.hero-footnote > span { display: inline-flex; align-items: center; gap: 5px; }
.hero-footnote .el-icon { color: var(--p-accent); }
.scenario-wrap { position: relative; min-width: 0; }
.scenario-orbit { position: absolute; inset: -60px; background: radial-gradient(ellipse, var(--p-accent-wash), transparent 68%); pointer-events: none; z-index: -1; opacity: .6; }
.scenario-window { border: 1px solid var(--p-line); border-radius: 14px; overflow: hidden; background: var(--p-surface); box-shadow: 0 28px 75px -35px var(--p-shade); transform: rotate(-1deg); }
.window-topline { display: flex; justify-content: space-between; align-items: center; padding: 15px 19px; gap: 12px; border-bottom: 1px solid var(--p-line); }
.window-identity { display: inline-flex; align-items: center; gap: 9px; font-size: 12px; }
.agent-mark { width: 25px; height: 25px; display: grid; place-items: center; border-radius: 7px; background: var(--p-accent-wash); color: var(--p-accent); font-size: 14px; }
.demo-badge { color: var(--p-subtle); font-size: 10px; }
.scenario-switch { display: flex; align-items: center; gap: 6px; padding: 12px 18px 0; }
.scenario-switch button { border: 1px solid transparent; background: none; border-radius: 6px; padding: 5px 11px; color: var(--p-muted); font-size: 10px; }
.scenario-switch button[aria-pressed="true"] { color: var(--p-accent); border-color: var(--p-line); background: var(--p-raised); }
.scenario-switch button:hover { color: var(--p-accent); }
.scenario-content { padding: 14px 19px 16px; }
.context-line { display: flex; gap: 7px; align-items: center; font-size: 10px; color: var(--p-muted); }
.context-label { margin-left: auto; font-size: 9px; color: var(--p-subtle); }
.user-question { display: flex; align-items: flex-start; gap: 9px; margin: 17px 0 19px; }
.user-avatar { width: 24px; height: 24px; flex-shrink: 0; display: grid; place-items: center; font-size: 10px; border-radius: 7px; background: var(--p-raised); color: var(--p-muted); border: 1px solid var(--p-line); }
.user-question p { font-size: 12px; line-height: 1.8; padding: 8px 11px; border-radius: 0 9px 9px; background: var(--p-raised); margin-top: 2px; }
.evidence-heading { display: flex; align-items: center; justify-content: space-between; font-size: 10px; color: var(--p-subtle); margin-bottom: 9px; }
.evidence-heading > span:first-child { display: inline-flex; align-items: center; gap: 6px; color: var(--p-muted); }
.evidence-heading .el-icon { color: var(--p-accent); }
.evidence-list { border: 1px solid var(--p-line); border-radius: 8px; overflow: hidden; }
.evidence-row { display: flex; align-items: center; gap: 8px; min-height: 33px; padding: 5px 11px; font-size: 10px; }
.evidence-row + .evidence-row { border-top: 1px solid var(--p-line); }
.evidence-check { color: var(--p-accent); display: flex; }
.evidence-row > span:last-child { margin-left: auto; color: var(--p-muted); }
.agent-insight { margin: 16px 0; }
.insight-label { font-size: 10px; color: var(--p-accent); font-weight: 600; }
.agent-insight p { font-size: 11px; line-height: 1.9; margin: 5px 0 10px; min-height: 42px; color: var(--p-muted); }
.source-tags { display: flex; flex-wrap: wrap; gap: 5px; }
.source-tags span { border: 1px solid var(--p-line); border-radius: 4px; padding: 1px 6px; color: var(--p-subtle); font-size: 9px; }
.confirmation-card { display: flex; gap: 9px; align-items: center; padding: 12px 10px; background: var(--p-accent-wash); border: 1px solid var(--p-line); border-radius: 8px; }
.confirmation-icon { color: var(--p-accent); font-size: 16px; display: flex; }
.confirmation-card > div { flex: 1; min-width: 0; }
.confirmation-card strong { display: block; font-size: 10px; font-weight: 600; }
.confirmation-card > div > span { display: block; margin-top: 2px; color: var(--p-muted); font-size: 9px; }
.confirmation-card button { display: inline-flex; gap: 5px; align-items: center; background: none; border: 0; white-space: nowrap; color: var(--p-accent); font-size: 10px; }
.is-previewed { border-color: var(--p-accent); }
.window-footer { display: flex; gap: 6px; align-items: center; border-top: 1px solid var(--p-line); padding: 9px 19px; font-size: 9px; color: var(--p-subtle); }
.window-footer > span:last-child { margin-left: auto; letter-spacing: 1px; font-family: ui-monospace, monospace; }
.scenario-caption { text-align: center; color: var(--p-subtle); font-size: 9px; margin-top: 15px; }
.value-strip { margin-top: 66px; display: grid; grid-template-columns: repeat(3, 1fr); border-top: 1px solid var(--p-line); border-bottom: 1px solid var(--p-line); }
.value-strip > div { display: flex; align-items: center; gap: 17px; padding: 27px 0; }
.value-strip > div + div { padding-left: 40px; border-left: 1px solid var(--p-line); }
.strip-number { color: var(--p-subtle); font-size: 13px; font-family: ui-monospace, monospace; }
.value-strip p strong { display: block; font-size: 13px; font-weight: 600; }
.value-strip p span { color: var(--p-subtle); font-size: 11px; display: block; margin-top: 4px; }
.integration-section { text-align: center; padding-block: 40px 8px; }
.integration-section > p { font-size: 10px; color: var(--p-subtle); letter-spacing: 1px; }
.integration-list { display: flex; justify-content: center; flex-wrap: wrap; gap: 35px; margin-top: 21px; color: var(--p-muted); font-size: 15px; font-weight: 600; letter-spacing: -.2px; }
.integration-list .integration-more { color: var(--p-accent); font-size: 12px; align-self: center; font-family: ui-monospace, monospace; }
.section-block { padding-block: 100px 0; }
.section-heading { display: flex; justify-content: space-between; align-items: end; gap: 35px; margin-bottom: 37px; }
.section-heading h2 { font-size: 37px; letter-spacing: -1.4px; line-height: 1.4; font-weight: 650; margin-top: 15px; }
.section-description { color: var(--p-muted); font-size: 13px; line-height: 1.95; padding-bottom: 4px; max-width: 405px; }
.capability-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.capability-card { position: relative; display: flex; flex-direction: column; min-height: 277px; padding: 29px; border: 1px solid var(--p-line); border-radius: 12px; background: var(--p-surface); transition: border-color .2s, transform .2s; }
.capability-card:hover { border-color: var(--p-subtle); transform: translateY(-3px); }
.feature-icon { display: grid; place-items: center; color: var(--p-accent); width: 34px; height: 34px; border: 1px solid var(--p-line); background: var(--p-raised); border-radius: 8px; font-size: 17px; margin-bottom: 22px; }
.card-kicker { font-size: 10px; letter-spacing: 1.5px; color: var(--p-subtle); font-family: ui-monospace, monospace; }
.capability-card h3 { font-size: 17px; font-weight: 600; margin: 8px 0 12px; letter-spacing: -.3px; }
.capability-card > p { color: var(--p-muted); font-size: 13px; line-height: 1.95; margin-bottom: 22px; }
.feature-bottom { display: flex; flex-wrap: wrap; gap: 6px 13px; margin-top: auto; font-size: 10px; color: var(--p-subtle); }
.feature-bottom span + span::before { content: '·'; margin-right: 12px; color: var(--p-subtle); }
.capability-featured { background: radial-gradient(ellipse at top right, var(--p-accent-wash), transparent 80%), var(--p-surface); }
.capability-featured .card-kicker { color: var(--p-accent); }
.agent-pipeline { display: flex; align-items: center; gap: 6px; font-size: 9px; color: var(--p-accent); margin: 0 0 25px; }
.agent-pipeline span { padding: 5px 7px; border: 1px solid var(--p-line); background: var(--p-bg); border-radius: 5px; }
.capability-observe .feature-icon { color: var(--p-cyan); }
.workflow-section { padding: 90px 0 72px; margin-top: 100px; border-block: 1px solid var(--p-line); background: var(--p-surface); }
.accent-text { color: var(--p-accent); }
.workflow-steps { display: grid; grid-template-columns: repeat(5, 1fr); list-style: none; margin-top: 50px; }
.workflow-steps li { position: relative; padding-right: 28px; }
.workflow-steps li:not(:last-child)::after { content: ''; position: absolute; left: 50px; top: 40px; width: calc(100% - 50px); height: 1px; background: var(--p-line); }
.step-number { display: block; font-size: 9px; color: var(--p-subtle); font-family: ui-monospace, monospace; margin-bottom: 12px; }
.step-node { display: grid; place-items: center; width: 38px; height: 38px; border: 1px solid var(--p-line); border-radius: 50%; background: var(--p-bg); color: var(--p-accent); font-size: 17px; }
.workflow-steps h3 { font-size: 14px; font-weight: 600; margin: 17px 0 9px; }
.workflow-steps p { font-size: 12px; color: var(--p-muted); line-height: 1.9; max-width: 170px; }
.boundary-strip { display: flex; align-items: center; gap: 15px; border: 1px solid var(--p-line); border-radius: 9px; margin-top: 35px; padding: 19px 22px; }
.boundary-icon { color: var(--p-accent); display: flex; font-size: 22px; }
.boundary-strip p strong { font-size: 12px; font-weight: 600; }
.boundary-strip p span { color: var(--p-muted); font-size: 11px; margin-left: 14px; }
.boundary-strip > a { display: flex; align-items: center; gap: 7px; color: var(--p-accent); font-size: 10px; white-space: nowrap; margin-left: auto; }
.gallery-selectors { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 19px; }
.gallery-selectors button { display: inline-flex; align-items: center; gap: 8px; border: 1px solid var(--p-line); border-radius: 7px; padding: 9px 14px; font-size: 11px; background: none; color: var(--p-muted); transition: color .2s, background .2s; }
.gallery-selectors button:hover { color: var(--p-ink); background: var(--p-surface); }
.gallery-selectors button[aria-pressed="true"] { background: var(--p-accent); color: var(--p-on-accent); border-color: var(--p-accent); }
.gallery-frame { border: 1px solid var(--p-line); border-radius: 12px; overflow: hidden; background: var(--p-surface); box-shadow: 0 25px 70px -40px var(--p-shade); }
.gallery-topline { display: flex; align-items: center; gap: 18px; padding: 12px 20px; font-family: ui-monospace, monospace; color: var(--p-subtle); font-size: 10px; border-bottom: 1px solid var(--p-line); }
.window-dots { display: flex; gap: 5px; }
.window-dots i { height: 6px; width: 6px; border-radius: 50%; background: var(--p-line); }
.window-dots i:first-child { background: var(--p-subtle); }
.gallery-counter { margin-left: auto; }
.screenshot-button { display: block; position: relative; width: 100%; border: 0; padding: 0; overflow: hidden; background: var(--p-raised); }
.screenshot-button img { width: 100%; height: auto; aspect-ratio: 1600 / 803; object-fit: contain; object-position: top; display: block; transition: transform .4s; }
.screenshot-button.is-archived img { aspect-ratio: 1600 / 1000; }
.screenshot-button:hover img { transform: scale(1.006); }
.zoom-hint { position: absolute; bottom: 16px; right: 16px; display: flex; align-items: center; gap: 7px; color: var(--p-ink); background: var(--p-translucent); border: 1px solid var(--p-line); border-radius: 5px; padding: 6px 10px; font-size: 10px; }
.gallery-caption { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 23px 25px; border-top: 1px solid var(--p-line); }
.gallery-caption h3 { font-size: 15px; font-weight: 600; }
.gallery-caption p { color: var(--p-muted); font-size: 11px; margin-top: 5px; }
.real-capture { display: inline-flex; gap: 6px; align-items: center; color: var(--p-subtle); font-size: 10px; white-space: nowrap; }
.gallery-note { color: var(--p-subtle); font-size: 10px; text-align: right; margin-top: 12px; }
.start-grid { display: grid; grid-template-columns: 1fr 1fr; border: 1px solid var(--p-line); border-radius: 12px; overflow: hidden; margin-bottom: 24px; }
.start-main { padding: 45px; background: radial-gradient(ellipse at bottom left, var(--p-accent-wash), transparent 80%), var(--p-surface); display: flex; align-items: flex-start; flex-direction: column; }
.start-main .card-kicker { color: var(--p-accent); }
.start-main h3 { font-size: 28px; line-height: 1.6; letter-spacing: -.8px; font-weight: 600; margin: 20px 0 17px; }
.start-main p { font-size: 12px; color: var(--p-muted); line-height: 1.95; }
.start-actions { display: flex; align-items: center; gap: 24px; margin-top: 30px; }
.text-link { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; }
.license-note { color: var(--p-subtle); font-size: 9px; margin-top: auto; padding-top: 30px; letter-spacing: 1px; }
.start-resources { padding: 28px 30px; min-width: 0; border-left: 1px solid var(--p-line); }
.clone-block { border: 1px solid var(--p-line); border-radius: 8px; padding: 15px; margin-bottom: 13px; background: var(--p-surface); }
.clone-block > div { display: flex; align-items: center; gap: 10px; justify-content: space-between; }
.clone-block > div > span { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: var(--p-muted); }
.clone-block button { background: var(--p-raised); border: 1px solid var(--p-line); border-radius: 5px; font-size: 9px; padding: 4px 8px; }
.clone-block pre { font-size: 10px; color: var(--p-accent); line-height: 2; padding-top: 12px; white-space: pre-wrap; overflow-wrap: anywhere; }
.clone-block code { font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace; }
.resource-link { display: flex; align-items: center; gap: 13px; padding: 17px 4px; border-bottom: 1px solid var(--p-line); }
.resource-link:last-child { border-bottom: 0; padding-bottom: 4px; }
.resource-icon { display: grid; place-items: center; width: 34px; height: 34px; border: 1px solid var(--p-line); border-radius: 7px; color: var(--p-muted); }
.resource-link h3 { font-size: 12px; font-weight: 600; }
.resource-link p { font-size: 10px; color: var(--p-subtle); margin-top: 3px; }
.resource-link > .el-icon { margin-left: auto; color: var(--p-subtle); font-size: 12px; }
.resource-link:hover h3, .resource-link:hover > .el-icon { color: var(--p-accent); }
.closing-section { position: relative; isolation: isolate; margin-top: 90px; text-align: center; padding-block: 65px 75px; border-top: 1px solid var(--p-line); overflow: hidden; }
.closing-label { font-size: 9px; letter-spacing: 2px; color: var(--p-subtle); }
.closing-section h2 { font-size: 42px; font-weight: 650; letter-spacing: -1px; line-height: 1.5; margin: 20px 0 27px; }
.closing-section h2 span { color: var(--p-accent); }
.closing-orbit { pointer-events: none; z-index: -1; position: absolute; width: 600px; height: 500px; border-radius: 50%; bottom: -450px; left: calc(50% - 300px); box-shadow: 0 -10px 140px -50px var(--p-accent); border: 1px solid var(--p-line); }
.site-footer { display: flex; align-items: center; gap: 25px; padding-block: 26px 30px; border-top: 1px solid var(--p-line); }
.footer-brand { font-size: 16px; gap: 5px; }
.site-footer > p { font-size: 10px; color: var(--p-subtle); }
.site-footer nav { margin-left: auto; display: flex; gap: 22px; color: var(--p-muted); font-size: 10px; }
.site-footer nav a { display: inline-flex; align-items: center; gap: 4px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.screenshot-dialog { margin: auto; width: min(1500px, calc(100vw - 48px)); max-width: none; max-height: calc(100dvh - 48px); padding: 0; color: var(--p-ink); background: var(--p-surface); border: 1px solid var(--p-line); border-radius: 12px; overflow: auto; }
.screenshot-dialog::backdrop { background: light-dark(#000c, #000c); backdrop-filter: blur(8px); }
.lightbox-toolbar, .lightbox-bottom { display: flex; align-items: center; gap: 16px; padding: 13px 18px; }
.lightbox-toolbar strong { font-size: 13px; font-weight: 600; }
.lightbox-toolbar > span { margin-left: auto; color: var(--p-subtle); font-size: 11px; }
.lightbox-toolbar button { display: grid; place-items: center; background: var(--p-raised); border: 1px solid var(--p-line); border-radius: 6px; width: 30px; height: 30px; }
.screenshot-dialog > img { width: 100%; height: auto; display: block; max-height: calc(100dvh - 180px); object-fit: contain; background: var(--p-bg); }
.lightbox-bottom { justify-content: space-between; }
.lightbox-bottom button { display: inline-flex; align-items: center; gap: 8px; font-size: 11px; padding: 8px 12px; border: 1px solid var(--p-line); border-radius: 6px; background: var(--p-raised); white-space: nowrap; }
.lightbox-bottom p { color: var(--p-muted); font-size: 11px; text-align: center; }
@media (min-width: 1600px) { .hero-section { padding-top: 100px; } .hero-layout { gap: 70px; } .hero-copy h1 { font-size: 61px; } .value-strip { margin-top: 82px; } }
@media (max-width: 1150px) {
  .page-width { width: calc(100% - 64px); }
  .header-inner { gap: 22px; } .main-nav { gap: 19px; } .header-github { padding: 8px 11px; }
  .hero-layout { gap: 30px; } .hero-copy h1 { font-size: 43px; letter-spacing: -1.8px; } .hero-description { font-size: 13px; }
  .hero-footnote { gap: 11px; font-size: 9px; } .button { padding-inline: 16px; font-size: 12px; }
  .value-strip > div + div { padding-left: 24px; } .value-strip p span { font-size: 10px; }
  .capability-card { padding: 23px; } .capability-card h3 { font-size: 15px; } .agent-pipeline { gap: 4px; font-size: 8px; }
  .boundary-strip p span { display: block; margin: 3px 0 0; } .integration-list { gap: 25px; font-size: 13px; }
  .start-main { padding: 35px; } .start-resources { padding: 25px; } .site-footer { gap: 15px; } .site-footer nav { gap: 17px; }
}
@media (max-width: 1100px) {
  .header-inner { height: 70px; } .brand { font-size: 19px; } .brand-symbol { width: 36px; height: 36px; }
  .main-nav { display: none; position: absolute; left: 0; right: 0; top: 70px; padding: 16px 32px; border-bottom: 1px solid var(--p-line); background: var(--p-bg); } .main-nav.is-open { display: flex; flex-direction: column; align-items: stretch; gap: 0; } .main-nav a { padding: 12px 8px; font-size: 13px; } .main-nav a::after { inset-inline: 8px; bottom: 5px; transform-origin: left; } .header-github { font-size: 11px; margin-left: auto; } .menu-toggle { display: grid; place-items: center; order: 3; }
}
@media (max-width: 900px) {
  .header-inner { height: 70px; } .brand { font-size: 19px; } .brand-symbol { width: 36px; height: 36px; }
  .main-nav { display: none; position: absolute; left: 0; right: 0; top: 70px; padding: 16px 32px; border-bottom: 1px solid var(--p-line); background: var(--p-bg); } .main-nav.is-open { display: flex; flex-direction: column; align-items: stretch; gap: 0; } .main-nav a { padding: 12px 8px; font-size: 13px; } .main-nav a::after { inset-inline: 8px; bottom: 5px; transform-origin: left; } .header-github { font-size: 11px; margin-left: auto; } .menu-toggle { display: grid; place-items: center; order: 3; }
  .hero-section { padding-top: 55px; } .hero-layout { grid-template-columns: 1fr; gap: 48px; } .hero-copy { text-align: center; } .hero-copy h1 { font-size: 55px; letter-spacing: -2px; }
  .hero-eyebrow, .hero-actions, .hero-footnote { justify-content: center; } .hero-eyebrow { margin-top: 27px; } .hero-description { font-size: 14px; } .hero-footnote { font-size: 10px; gap: 20px; }
  .scenario-wrap { max-width: 560px; width: 100%; margin-inline: auto; } .scenario-window { transform: none; } .user-question p { font-size: 13px; } .agent-insight p { font-size: 12px; }
  .value-strip { margin-top: 40px; } .value-strip > div { gap: 12px; padding-block: 22px; } .value-strip > div + div { padding-left: 17px; } .value-strip p span { max-width: 145px; line-height: 1.8; }
  .section-block { padding-top: 74px; } .section-heading h2 { font-size: 30px; } .section-heading { gap: 25px; } .section-description { font-size: 11px; max-width: 300px; }
  .capability-grid { grid-template-columns: repeat(2, 1fr); } .capability-card { min-height: 270px; } .capability-card h3 { font-size: 16px; } .agent-pipeline { font-size: 9px; }
  .workflow-section { margin-top: 74px; padding-block: 65px 55px; } .workflow-steps li { padding-right: 20px; } .workflow-steps p { font-size: 10px; } .workflow-steps h3 { font-size: 12px; }
  .start-main { padding: 30px; } .start-main h3 { font-size: 24px; } .start-main p { font-size: 11px; } .start-resources { padding: 22px; } .resource-link p { font-size: 9px; }
  .site-footer { flex-wrap: wrap; gap: 10px 18px; } .site-footer nav { margin-left: auto; } .site-footer > p { display: none; }
}
@media (max-width: 640px) {
  .page-width { width: calc(100% - 40px); }
  .header-inner { height: 66px; gap: 12px; } .brand { font-size: 18px; } .header-github { padding: 7px 10px; margin-left: auto; } .header-github > .el-icon { display: none; }
  .menu-toggle { display: grid; place-items: center; order: 3; }
  .main-nav { display: none; position: absolute; left: 0; right: 0; top: 66px; padding: 16px 20px; border-bottom: 1px solid var(--p-line); background: var(--p-bg); }
  .main-nav.is-open { display: flex; flex-direction: column; align-items: stretch; gap: 0; } .main-nav a { padding: 12px 8px; font-size: 13px; }
  .product-intro section[id] { scroll-margin-top: 84px; }
  .hero-section { padding-top: 36px; } .release-pill { font-size: 10px; } .release-pill > span { font-size: 10px; }
  .hero-eyebrow { font-size: 8px; letter-spacing: 1.3px; margin: 28px 0 16px; } .hero-copy h1 { font-size: clamp(29px, 7.5vw, 46px); letter-spacing: -1.4px; line-height: 1.45; }
  .hero-description { font-size: 12px; line-height: 1.95; margin-top: 20px; } .desktop-break { display: none; } .hero-actions { gap: 10px; margin-top: 25px; } .button { font-size: 11px; gap: 10px; min-height: 44px; padding-inline: 15px; }
  .hero-footnote { gap: 12px; font-size: 8px; margin-top: 19px; } .hero-layout { gap: 33px; }
  .window-topline { padding: 13px 14px; } .scenario-switch { padding-inline: 12px; } .scenario-switch button { padding: 5px 9px; } .scenario-content { padding: 12px 14px 14px; }
  .user-question { margin-block: 15px; gap: 7px; } .user-question p { font-size: 11px; } .context-label { display: none; } .agent-insight p { font-size: 11px; } .evidence-row { font-size: 9px; padding-inline: 9px; }
  .confirmation-card { gap: 7px; padding: 11px 9px; } .confirmation-icon { display: none; } .confirmation-card strong { font-size: 10px; } .confirmation-card > div > span { font-size: 8px; } .confirmation-card button { font-size: 9px; gap: 3px; }
  .scenario-caption { font-size: 8px; } .value-strip { grid-template-columns: 1fr; margin-top: 30px; } .value-strip > div { padding: 17px 5px; gap: 16px; } .value-strip > div + div { border-left: 0; border-top: 1px solid var(--p-line); padding-left: 5px; }
  .value-strip p { display: flex; align-items: center; flex-wrap: wrap; gap: 7px 15px; } .value-strip p strong { font-size: 12px; } .value-strip p span { margin-top: 0; max-width: none; font-size: 10px; }
  .integration-section { padding-top: 28px; } .integration-section > p { font-size: 9px; } .integration-list { gap: 15px 22px; font-size: 12px; margin-top: 17px; }
  .section-block { padding-top: 60px; } .section-heading { display: block; margin-bottom: 25px; } .eyebrow { font-size: 10px; letter-spacing: 1.4px; } .section-heading h2 { font-size: 27px; letter-spacing: -1px; margin-top: 12px; } .section-description { margin-top: 18px; font-size: 11px; max-width: none; }
  .capability-grid { grid-template-columns: 1fr; gap: 10px; } .capability-card { min-height: 0; padding: 23px; } .feature-icon { margin-bottom: 18px; } .capability-card h3 { font-size: 17px; } .capability-card > p { font-size: 12px; } .agent-pipeline { font-size: 9px; margin-bottom: 20px; }
  .workflow-section { margin-top: 60px; padding-block: 52px 42px; } .workflow-steps { grid-template-columns: 1fr; margin-top: 28px; gap: 0; }
  .workflow-steps li { display: grid; grid-template-columns: 24px 38px 1fr; column-gap: 13px; padding: 0 0 25px; } .workflow-steps li:last-child { padding-bottom: 0; } .step-number { grid-column: 1; grid-row: 1 / span 2; align-self: start; padding-top: 10px; margin: 0; }
  .step-node { grid-column: 2; grid-row: 1 / span 2; } .workflow-steps h3 { grid-column: 3; font-size: 13px; margin: 0 0 3px; } .workflow-steps p { grid-column: 3; font-size: 11px; max-width: none; }
  .workflow-steps li:not(:last-child)::after { left: 55px; top: 43px; height: calc(100% - 48px); width: 1px; } .boundary-strip { flex-wrap: wrap; padding: 17px; gap: 10px; margin-top: 28px; } .boundary-icon { font-size: 17px; } .boundary-strip p { flex: 1; min-width: 0; } .boundary-strip p strong { font-size: 11px; } .boundary-strip p span { font-size: 10px; } .boundary-strip > a { margin-left: 27px; }
  .gallery-selectors { gap: 7px; margin-bottom: 14px; } .gallery-selectors button { font-size: 10px; gap: 5px; padding: 8px 10px; } .gallery-topline { padding: 10px 12px; font-size: 8px; gap: 10px; }
  .gallery-caption { padding: 18px; gap: 12px; } .gallery-caption h3 { font-size: 13px; } .gallery-caption p { font-size: 10px; } .real-capture { display: none; } .zoom-hint { font-size: 8px; bottom: 8px; right: 8px; padding: 4px 7px; } .gallery-note { font-size: 9px; text-align: left; }
  .start-grid { grid-template-columns: 1fr; } .start-main { padding: 28px; } .start-main h3 { font-size: 25px; margin-top: 17px; } .start-main p { font-size: 11px; } .start-actions { margin-top: 23px; } .license-note { padding-top: 24px; font-size: 8px; } .start-resources { border-left: 0; border-top: 1px solid var(--p-line); padding: 22px; } .clone-block pre { font-size: 9px; }
  .resource-link p { font-size: 10px; } .closing-section { margin-top: 60px; padding-block: 45px 50px; } .closing-label { font-size: 8px; letter-spacing: 1.4px; } .closing-section h2 { font-size: 30px; margin-block: 17px 23px; }
  .site-footer { padding-block: 22px; } .footer-brand { font-size: 15px; } .site-footer nav { width: 100%; justify-content: space-between; gap: 10px; font-size: 9px; margin: 5px 0 0; }
  .screenshot-dialog { width: calc(100vw - 20px); max-height: calc(100dvh - 30px); border-radius: 8px; } .lightbox-toolbar, .lightbox-bottom { padding: 12px; gap: 8px; } .lightbox-bottom p { display: none; } .lightbox-bottom button { font-size: 10px; } .screenshot-dialog > img { max-height: calc(100dvh - 170px); }
}
@media (max-width: 360px) {
  .header-github { height: 36px; padding: 0 8px; gap: 6px; justify-content: center; flex-shrink: 0; }
  .header-github > .github-label { display: none; }
  .repository-stars { padding-left: 6px; }
  .menu-toggle { flex-shrink: 0; }
}
@media (prefers-reduced-motion: reduce) { .product-intro *, .product-intro *::before, .product-intro *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; } }
</style>
