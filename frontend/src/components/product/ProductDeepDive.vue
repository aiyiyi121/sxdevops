<template>
  <div class="product-deep-dive">
    <section id="modules" class="detail-section detail-width">
      <div class="detail-heading"><div><p class="detail-eyebrow">{{ sectionLabel('modules') }}</p><h2>把日常工作，<br />连成可复用的流程。</h2></div><p>资产是底座，观测是事实，任务承接行动。<br />深入每个模块，看看它们如何协同工作。</p></div>
      <div class="module-selector" role="group" aria-label="了解模块详细能力"><button v-for="(module, index) in modules" :key="module.id" type="button" :aria-pressed="moduleIndex === index" @click="moduleIndex = index"><el-icon><component :is="module.icon" /></el-icon>{{ module.label }}</button></div>
      <article class="module-detail" aria-live="polite">
        <div class="module-intro"><span class="detail-eyebrow">{{ currentModule.eyebrow }}</span><h3>{{ currentModule.title }}</h3><p>{{ currentModule.description }}</p><div class="module-chain"><span v-for="(step, index) in currentModule.chain" :key="step"><span v-if="index" aria-hidden="true">→</span>{{ step }}</span></div><a :href="doc(currentModule.document)" target="_blank" rel="noopener noreferrer">{{ currentModule.linkLabel }} <el-icon><TopRight /></el-icon></a></div>
        <ul class="module-points"><li v-for="point in currentModule.points" :key="point.title"><el-icon><Check /></el-icon><div><h4>{{ point.title }}</h4><p>{{ point.description }}</p></div></li></ul>
      </article>
      <div class="scenario-cards"><article v-for="scenario in useCases" :key="scenario.title"><span>{{ scenario.number }} / {{ scenario.label }}</span><h3>{{ scenario.title }}</h3><p>{{ scenario.description }}</p><div><el-icon><ArrowRight /></el-icon>{{ scenario.outcome }}</div></article></div>
    </section>

    <section id="architecture" class="detail-section detail-width">
      <div class="detail-heading"><div><p class="detail-eyebrow">{{ sectionLabel('architecture') }}</p><h2>统一控制面，<br /><span>连接真实的基础设施。</span></h2></div><p>前端工作台、后端业务控制与智能体编排各司其职。<br />把已有数据源和执行环境接进来，保留清晰的权限边界。</p></div>
      <ProductFigure src="/promo/v2/platform-architecture.svg" title="SxDevOps 平台架构" alt="SxDevOps 架构图：Vue 工作台连接 Django API 与 Channels，AIOps 通过 LangGraph、任务队列、worker 和 checkpoint 编排受控工具，访问可观测数据及资源环境" label="平台架构 / 当前实现" caption="工作台负责交互，Django 承接业务控制，LangGraph 编排分析与证据；操作继续经过平台 API，数据源和资源访问沿用账号权限。" />
      <div class="architecture-notes"><article><span>业务控制</span><h3>业务能力统一承接</h3><p>CMDB、任务、事件、工单与容器管理通过 Django API 提供服务。前端菜单和按钮镜像权限，实际执行仍由后端校验。</p></article><article><span>运行与状态</span><h3>异步任务有状态可恢复</h3><p>数据库队列与独立 worker 处理聊天和验证，checkpoint 保存阶段状态。本地默认 SQLite，Compose 使用共享 MySQL checkpoint。</p></article><article><span>开放集成</span><h3>复用已有数据与工具</h3><p>接入指标、日志、链路与 Grafana，结合 Kubernetes、Docker、SSH 和外部 MCP，把原有工具组织成受控的工作链路。</p></article></div>
      <div class="tech-stack"><span>技术栈</span><span v-for="technology in technologies" :key="technology">{{ technology }}</span></div>
    </section>

    <section id="aiops" class="detail-section agent-section">
      <div class="detail-width">
        <div class="detail-heading"><div><p class="detail-eyebrow">{{ sectionLabel('aiops') }}</p><h2>AI 负责理解，<br />平台让每一步<span>有章可循。</span></h2></div><p>问题进入受控编排，工具返回事实，Skill 组织专业输出。<br />从查询到动作，每一层都有自己的职责。</p></div>
        <div class="agent-facts"><div><strong>6<span> 类问答入口</span></strong><p>从故障排查到资产查询，按问题选择工作方式</p></div><div><strong>13<span> 个内置 Skill</span></strong><p>复用证据方法、查询规范、输出结构与安全边界</p></div><div><strong>3<span> 条流程主线</span></strong><p>聊天分析、动作确认与处置效果验证分别管理</p></div></div>
        <ProductFigure src="/promo/v2/aiops-execution-flow.svg" title="AIOps 实现原理与执行链路" alt="AIOps 原理图：问题与范围、Action 路由、LangGraph 专业取证或模型工具循环、MCP 事实、Skill 整形、只读回复或待确认动作、平台执行与验证" label="AIOps 原理 / 从输入到执行" :height="960" caption="按当前聊天、确认与验证流程梳理。图中展示主要职责和路径，完整节点、恢复条件与运行配置见 LangGraph 文档。" />
        <div class="mechanism-grid"><article v-for="mechanism in mechanisms" :key="mechanism.title"><span>{{ mechanism.label }}</span><h3>{{ mechanism.title }}</h3><p>{{ mechanism.description }}</p></article></div>
        <div class="question-types"><div class="subsection-heading"><h3>六类问题入口，背后复用专业方法</h3><p>自动识别任务，也可按问答类型进入；权限与环境范围始终生效。</p></div><div class="question-grid"><article v-for="question in questionTypes" :key="question.title"><el-icon><component :is="question.icon" /></el-icon><div><h4>{{ question.title }}</h4><p>{{ question.description }}</p></div></article></div></div>
        <div class="runtime-note"><el-icon><Connection /></el-icon><p><strong>中断后，继续已保存的工作。</strong>已完成并保存 checkpoint 的阶段可在恢复时复用；恢复仍检查当前权限、MCP 状态与原始范围。节点内部中断可能重试当前请求，外部工具需要幂等。</p><a :href="doc('AIOps-LangGraph-试点说明.md')" target="_blank" rel="noopener noreferrer">实现文档 <el-icon><TopRight /></el-icon></a></div>
      </div>
    </section>

    <section id="verification" class="detail-section detail-width">
      <div class="detail-heading"><div><p class="detail-eyebrow">{{ sectionLabel('verification') }}</p><h2>执行完成之后，<br />继续看<span>恢复的证据。</span></h2></div><p>把任务结果与告警恢复分开检查。<br />保存处置前基线，等待观察窗口，再给出有边界的结论。</p></div>
      <div class="verification-flow" aria-label="处置效果验证流程"><div v-for="(step, index) in verificationSteps" :key="step.title"><span>0{{ index + 1 }}</span><h3>{{ step.title }}</h3><p>{{ step.description }}</p></div></div>
      <div class="verification-results"><article v-for="result in verificationResults" :key="result.title" :class="result.className"><span class="result-indicator"></span><h3>{{ result.title }}</h3><p>{{ result.description }}</p></article></div>
      <div class="verification-boundary"><p>当前验证以平台接收的同一告警恢复事件为依据。观察到恢复，可以说明告警状态变化；操作因果、业务整体健康与指标持续达标，需要进一步的证据支持。</p><a :href="doc('AIOps-处置效果验证.md')" target="_blank" rel="noopener noreferrer">查看验证口径 <el-icon><TopRight /></el-icon></a></div>
    </section>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ArrowRight, Box, Check, Connection, DataAnalysis, Document, Lock, Search, Tickets, TopRight } from '@element-plus/icons-vue'
import ProductFigure from './ProductFigure.vue'
import { sectionLabel } from './sections'

const repository = 'https://github.com/aiyiyi121/sxdevops'
const doc = path => `${repository}/blob/main/docs/${path}`
const moduleIndex = ref(0)
const modules = [
  { id: 'cmdb', label: 'CMDB 资产底座', icon: Connection, eyebrow: '资产 → 上下文 → 执行', title: '知道资源是什么，也知道它与谁有关。', description: '资产台账、业务线与环境树、同步中心、容量水位和拓扑使用统一资源口径。将云账号、vSphere、机房及第三方服务逐步纳入同一个资产底座。', chain: ['同步纳管', '资源归属', '容量与拓扑', '接入任务'], document: 'CMDB使用手册.md', linkLabel: '阅读 CMDB 使用手册', points: [
    { title: '统一资产与归属', description: '通过台账、搜索、资源树和模板管理资产，结合业务线、环境与负责人理解资源上下文。' },
    { title: '容量、治理与拓扑', description: '按最新指标查看水位；拓扑可选择精确命中或带 1–3 跳邻居，画布始终限定在授权资产内。' },
    { title: '显式衔接执行资源', description: '选择 CMDB 资产，补充执行信息并保存后接入任务中心。基础信息随源资产更新，执行凭据单独维护。' },
    { title: '资产生命周期约束', description: '关联源资产停机、下线或删除时阻止新的任务执行；移除执行资源保留源资产与既有历史引用。' },
  ] },
  { id: 'observability', label: '可观测性与图谱', icon: DataAnalysis, eyebrow: '指标 · 日志 · 链路 · 上下文', title: '从告警信号，追到服务与证据。', description: '把系统态势、指标查询、日志检索、链路追踪、告警与 Grafana 看板组织到一个工作台，结合环境和服务关系缩小排查范围。', chain: ['观察态势', '明确环境', '查询证据', '形成判断'], document: '用户使用文档.md', linkLabel: '了解可观测性工作台', points: [
    { title: '接入已有数据源', description: '支持 Prometheus / Grafana、Loki / ELK / SLS，以及 SkyWalking、Tempo、Jaeger、Zipkin 等来源。' },
    { title: '结合资源上下文', description: '知识环境、服务依赖与主机关系为分析提供上下文，查询沿用环境、时间窗口与账号权限。' },
    { title: '多个信号相互印证', description: '日志、Trace、告警、指标和近期变更可共同参与分析，时间接近的变更保留为候选诱因，继续交叉验证。' },
    { title: '明确展示查询限制', description: '无数据、数据源未配置、查询失败与权限不足分别记录，证据缺口不会被直接解释为系统正常。' },
  ] },
  { id: 'containers', label: '容器管理', icon: Box, eyebrow: 'Kubernetes / Docker 工作台', title: '查看资源，也照顾到操作的每个细节。', description: '统一 Kubernetes 与 Docker 工作台，从集群或环境概要进入资源、容器、镜像、终端和日志，持续保留当前操作上下文。', chain: ['选择范围', '查看资源', '预检确认', '检查结果'], document: 'K8s工作台与用户授权.md', linkLabel: '阅读容器工作台说明', points: [
    { title: 'K8s 资源与 YAML', description: '管理工作负载、Service、Ingress、网络策略、HPA 与配额；YAML 创建或编辑先 dry-run 预检、查看差异，再确认应用。' },
    { title: '容量与范围授权', description: '汇总实际用量、Requests、Limits 与可分配容量；在 RBAC 上叠加集群、命名空间和终端授权，缺少 metrics 时明确提示。' },
    { title: 'Docker 环境工作台', description: '容器与镜像支持分页搜索，环境卡片与概要联动；操作前明确目标，自动刷新在后台页面或弹窗期间暂停。' },
    { title: '交互终端与历史日志', description: '支持 Shell 选择、全屏、重连、会话下载与复制粘贴；日志按游标翻阅历史，展示原始内容并控制浏览器保留量。' },
  ] },
  { id: 'tasks', label: '任务与事件', icon: Tickets, eyebrow: '草稿 → 执行 → 复盘', title: '把建议接到任务，把结果带回复盘。', description: '通过主机巡检、批量命令、脚本模板和执行历史统一承接运维操作。事件中心沉淀关键写入、失败线索和变更上下文。', chain: ['准备草稿', '核对目标', '确认执行', '追踪复盘'], document: 'task-resource-cmdb.md', linkLabel: '了解任务资源与 CMDB 接入', points: [
    { title: '复用任务模板', description: '巡检、命令、脚本与 Playbook 围绕明确的执行资源组织，AIOps 可按本轮查询到的资源生成任务草稿。' },
    { title: '确认后进入执行', description: '核对资源、参数和风险，再载入任务中心编辑或执行；分析建议、动作确认和实际任务分别留痕。' },
    { title: '结果按资源追踪', description: '查看任务执行记录与逐项返回内容，区分成功、失败和跳过目标，为处置验证提供真实结果。' },
    { title: '事件时间线与复盘', description: '结合发布、工单、操作事件和失败记录，按系统、环境、应用与时间过滤，回看异常前后发生了什么。' },
  ] },
  { id: 'governance', label: '工单与权限', icon: Lock, eyebrow: '协作 / 权限 / 审计', title: '把团队流程与执行边界放在一起。', description: '发布、事务审批与 SQL 审计承接协作流程。权限控制覆盖后端接口、路由、菜单、页面动作和 WebSocket 等入口。', chain: ['身份认证', '权限校验', '审批确认', '操作审计'], document: '用户使用文档.md', linkLabel: '阅读平台使用文档', points: [
    { title: '工单连接协作', description: '应用发布、事务工单、审批流与 SQL 审计组织变更过程，减少上下文在团队间传递时的遗漏。' },
    { title: '后端执行权限校验', description: '页面隐藏只是交互呈现；实际请求、工具调用与终端连接都要通过后端的权限和资源范围检查。' },
    { title: '动作确认重新检查', description: '人工确认时复核身份、动作开关、当前权限与目标范围；模型不能绕过平台 API 直接操作资源。' },
    { title: '工作台按习惯调整', description: '提供浅色、炭灰、深蓝灰三套主题；系统设置集中管理网站名称、图标、菜单排序与显示。' },
  ] },
]
const currentModule = computed(() => modules[moduleIndex.value])
const useCases = [
  { number: '01', label: '故障排查', title: '服务错误率突然升高', description: '围绕生产服务查询告警、日志、错误 Trace 和最近变更，整理异常时间线与可能原因。', outcome: '输出依据、风险和下一步建议' },
  { number: '02', label: '资源运维', title: '集群工作负载反复重启', description: '结合 Pod 状态、事件、资源用量与配置定位线索；需要调整时先检查范围与 YAML 差异。', outcome: '取证与变更确认形成衔接' },
  { number: '03', label: '日常治理', title: '资产盘点与主机巡检', description: '从 CMDB 看归属与容量，将选定资产接入执行资源，通过模板生成和执行巡检任务。', outcome: '保留资源、任务与返回结果' },
]
const technologies = ['Vue 3', 'Django / DRF', 'Channels / Daphne', 'LangGraph', 'MySQL / SQLite', 'Redis', 'MCP']
const mechanisms = [
  { label: 'ACTION / 任务合同', title: '先明确要解决什么问题', description: '路由任务类型，声明所需上下文、风险边界和确认策略。进入生成或执行前，预检权限、依赖、参数和目标。' },
  { label: 'SKILL / 专业方法', title: '让经验变成可复用规范', description: '组织证据清单、查询方法、判断规则和输出格式。告警、日志、链路、容器安全与回滚评估等方法可以跨能力复用。' },
  { label: 'MCP / 工具连接', title: '用受控工具获取真实事实', description: '工具在 MCP Server 中统一配置。运行时结合启用状态、白名单、用户权限和 Action 策略，决定本轮可调用的能力。' },
  { label: 'OUTPUT / 结果校验', title: '给出结论，也交代证据限制', description: '专业路线分阶段保存证据，通用路线由模型规划并逐个调用工具。回答经 Skill 整形和校验，必要时有界修复与兜底。' },
]
const questionTypes = [
  { title: '故障排查', icon: Search, description: '告警根因、K8s 诊断、异常取证与恢复建议' },
  { title: '日志查询', icon: Document, description: '查询生成、日志检索与异常模式分析' },
  { title: 'SLO 评估', icon: DataAnalysis, description: '可用性、延迟、错误率与目标风险' },
  { title: '事件分析', icon: Connection, description: '发布、变更、工单与告警时间线关联' },
  { title: '任务生成', icon: Tickets, description: '主机、Playbook 与 K8s 任务草稿' },
  { title: 'CMDB', icon: Box, description: '资产查询、成本、依赖拓扑与数据质量' },
]
const verificationSteps = [
  { title: '保存基线', description: '任务创建前选定活跃告警、环境与观察窗口。' },
  { title: '执行任务', description: '沿用人工确认和任务中心的实际执行流程。' },
  { title: '等待观察', description: '任务结束后经过设定窗口，再读取恢复证据。' },
  { title: '形成结论', description: '结合执行结果、告警指纹和恢复事件判定。' },
]
const verificationResults = [
  { title: '告警已恢复', className: 'result-success', description: '任务与目标执行成功，同一告警的恢复事件满足本次任务后的时间条件。' },
  { title: '验证未通过', className: 'result-warning', description: '任务失败、部分成功或跳过目标，或观察窗口结束后告警仍处于活跃状态。' },
  { title: '证据不足', className: 'result-neutral', description: '基线、恢复时间、指纹或权限等证据不满足要求，保留原因供进一步核查。' },
]
</script>

<style scoped>
.detail-width { width: min(1240px, calc(100% - 96px)); margin-inline: auto; }
.detail-section { padding-top: 100px; scroll-margin-top: 90px; }
.detail-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 36px; margin-bottom: 35px; }
.detail-eyebrow { color: var(--p-accent); font-size: 10px; letter-spacing: 1.8px; font-weight: 600; }
.detail-heading h2 { font-size: 37px; font-weight: 650; line-height: 1.4; letter-spacing: -1.4px; margin-top: 14px; }
.detail-heading h2 span { color: var(--p-accent); }
.detail-heading > p { max-width: 410px; font-size: 13px; line-height: 1.95; color: var(--p-muted); padding-bottom: 4px; }
a { color: inherit; text-decoration: none; }
button { color: inherit; font: inherit; cursor: pointer; }
:is(a, button):focus-visible { outline: 2px solid var(--p-accent); outline-offset: 4px; }
.module-selector { display: flex; flex-wrap: wrap; gap: 9px; margin-bottom: 16px; }
.module-selector button { display: inline-flex; align-items: center; gap: 8px; padding: 11px 16px; font-size: 12px; border: 1px solid var(--p-line); background: var(--p-surface); border-radius: 8px; color: var(--p-muted); }
.module-selector button:hover { border-color: var(--p-subtle); color: var(--p-ink); }
.module-selector button[aria-pressed="true"] { border-color: var(--p-accent); color: var(--p-accent); background: var(--p-accent-wash); }
.module-detail { display: grid; grid-template-columns: .85fr 1.15fr; border: 1px solid var(--p-line); border-radius: 12px; overflow: hidden; background: var(--p-surface); }
.module-intro { display: flex; align-items: flex-start; flex-direction: column; padding: 35px; background: radial-gradient(ellipse at top left, var(--p-accent-wash), transparent 90%); border-right: 1px solid var(--p-line); }
.module-intro .detail-eyebrow { font-size: 9px; letter-spacing: 1px; }
.module-intro h3 { font-size: 24px; line-height: 1.65; font-weight: 600; letter-spacing: -.5px; margin: 19px 0 16px; }
.module-intro > p { font-size: 13px; color: var(--p-muted); line-height: 2; }
.module-chain { display: flex; flex-wrap: wrap; gap: 10px; margin: 25px 0; color: var(--p-muted); font-size: 11px; }
.module-chain > span { display: inline-flex; gap: 10px; align-items: center; }
.module-chain > span > span { color: var(--p-subtle); }
.module-intro a { display: inline-flex; align-items: center; gap: 7px; margin-top: auto; padding-top: 18px; font-size: 11px; color: var(--p-accent); }
.module-points { list-style: none; padding: 30px; display: grid; gap: 21px; }
.module-points li { display: flex; align-items: flex-start; gap: 12px; }
.module-points .el-icon { color: var(--p-accent); margin-top: 4px; font-size: 13px; flex-shrink: 0; }
.module-points h4 { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.module-points p { color: var(--p-muted); font-size: 12px; line-height: 1.9; }
.scenario-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 18px; }
.scenario-cards article { padding: 25px; border: 1px solid var(--p-line); border-radius: 10px; }
.scenario-cards article > span { font-size: 10px; letter-spacing: 1px; color: var(--p-subtle); }
.scenario-cards h3 { font-size: 16px; font-weight: 600; margin: 12px 0; }
.scenario-cards p { font-size: 12px; color: var(--p-muted); line-height: 1.95; }
.scenario-cards article > div { display: flex; align-items: center; gap: 7px; margin-top: 20px; font-size: 10px; color: var(--p-accent); }
.architecture-notes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 28px; padding: 29px 0; }
.architecture-notes article > span { color: var(--p-subtle); font-size: 9px; letter-spacing: 1.4px; }
.architecture-notes h3 { font-size: 15px; font-weight: 600; margin: 9px 0; }
.architecture-notes p { font-size: 12px; line-height: 1.95; color: var(--p-muted); }
.tech-stack { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; border-block: 1px solid var(--p-line); padding: 19px 0; }
.tech-stack span { font-size: 10px; padding: 4px 9px; color: var(--p-muted); border: 1px solid var(--p-line); background: var(--p-surface); border-radius: 5px; }
.tech-stack span:first-child { border: 0; background: none; color: var(--p-subtle); padding-left: 0; padding-right: 12px; }
.agent-section { margin-top: 100px; padding-block: 80px; background: var(--p-surface); border-block: 1px solid var(--p-line); }
.agent-facts { display: grid; grid-template-columns: repeat(3, 1fr); border-block: 1px solid var(--p-line); padding-block: 22px; margin-bottom: 28px; gap: 28px; }
.agent-facts strong { font-size: 32px; font-weight: 600; line-height: 1.2; color: var(--p-accent); }
.agent-facts strong span { font-size: 13px; color: var(--p-ink); margin-left: 9px; font-weight: 500; }
.agent-facts p { font-size: 11px; margin-top: 8px; color: var(--p-muted); line-height: 1.8; }
.mechanism-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-top: 25px; }
.mechanism-grid article { padding: 27px; border: 1px solid var(--p-line); border-radius: 10px; background: var(--p-bg); }
.mechanism-grid article > span { font-size: 10px; color: var(--p-accent); letter-spacing: .8px; }
.mechanism-grid h3 { font-size: 17px; font-weight: 600; margin: 12px 0; }
.mechanism-grid p { font-size: 12px; color: var(--p-muted); line-height: 1.95; }
.question-types { margin-top: 40px; }
.subsection-heading h3 { font-size: 19px; font-weight: 600; }
.subsection-heading p { font-size: 12px; margin-top: 7px; color: var(--p-muted); }
.question-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px 28px; margin-top: 27px; }
.question-grid article { display: flex; gap: 12px; align-items: flex-start; }
.question-grid .el-icon { display: grid; place-items: center; width: 32px; height: 32px; border: 1px solid var(--p-line); border-radius: 7px; color: var(--p-accent); background: var(--p-bg); flex-shrink: 0; font-size: 15px; }
.question-grid h4 { font-size: 13px; font-weight: 600; }
.question-grid p { font-size: 11px; line-height: 1.8; margin-top: 4px; color: var(--p-muted); }
.runtime-note { display: flex; align-items: center; gap: 15px; padding: 22px; border: 1px solid var(--p-line); border-radius: 9px; margin-top: 32px; }
.runtime-note > .el-icon { color: var(--p-accent); font-size: 24px; flex-shrink: 0; }
.runtime-note p { color: var(--p-muted); font-size: 12px; line-height: 1.95; }
.runtime-note strong { color: var(--p-ink); font-weight: 600; }
.runtime-note > a { display: inline-flex; align-items: center; gap: 7px; margin-left: auto; color: var(--p-accent); font-size: 11px; white-space: nowrap; }
.verification-flow { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--p-line); border-radius: 12px; background: var(--p-surface); overflow: hidden; }
.verification-flow > div { padding: 26px; }
.verification-flow > div + div { border-left: 1px solid var(--p-line); }
.verification-flow > div > span { color: var(--p-accent); font-size: 12px; font-family: ui-monospace, monospace; }
.verification-flow h3 { font-size: 15px; font-weight: 600; margin: 13px 0 9px; }
.verification-flow p { color: var(--p-muted); font-size: 12px; line-height: 1.9; }
.verification-results { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 18px; }
.verification-results article { position: relative; padding: 24px; border: 1px solid var(--p-line); border-radius: 10px; }
.result-indicator { display: block; width: 6px; height: 6px; border-radius: 50%; background: var(--p-subtle); margin-bottom: 13px; }
.result-success .result-indicator { background: var(--p-accent); }
.result-warning .result-indicator { background: light-dark(#ebcb8b, #ebcb8b); }
.verification-results h3 { font-size: 14px; font-weight: 600; }
.verification-results p { margin-top: 10px; color: var(--p-muted); font-size: 12px; line-height: 1.95; }
.verification-boundary { display: flex; gap: 28px; align-items: center; padding-top: 20px; }
.verification-boundary p { color: var(--p-muted); font-size: 11px; line-height: 1.9; }
.verification-boundary a { color: var(--p-accent); display: inline-flex; align-items: center; gap: 7px; font-size: 11px; white-space: nowrap; }
@media (max-width: 1150px) { .detail-width { width: calc(100% - 64px); } .module-intro { padding: 28px; } .module-intro h3 { font-size: 22px; } .module-points { padding: 26px; } .scenario-cards article { padding: 22px; } .detail-heading > p { font-size: 12px; } .verification-flow > div { padding: 23px; } }
@media (max-width: 900px) { .detail-section { padding-top: 74px; } .detail-heading h2 { font-size: 30px; } .detail-heading > p { font-size: 11px; max-width: 300px; } .module-detail { grid-template-columns: 1fr; } .module-intro { border-right: 0; border-bottom: 1px solid var(--p-line); } .module-chain { margin-block: 18px 0; } .module-intro h3 { margin-block: 14px 10px; } .module-points { grid-template-columns: repeat(2, 1fr); gap: 22px; } .scenario-cards { gap: 10px; } .scenario-cards article { padding: 20px; } .scenario-cards h3 { font-size: 14px; } .scenario-cards p { font-size: 11px; } .scenario-cards article > div { align-items: flex-start; font-size: 9px; } .scenario-cards article > div .el-icon { flex-shrink: 0; margin-top: 3px; } .architecture-notes { gap: 20px; } .architecture-notes h3 { font-size: 13px; } .architecture-notes p { font-size: 11px; } .agent-section { margin-top: 74px; padding-block: 65px; } .agent-facts { gap: 20px; } .agent-facts strong span { display: block; margin: 8px 0 0; font-size: 12px; } .agent-facts p { font-size: 10px; } .mechanism-grid article { padding: 23px; } .mechanism-grid h3 { font-size: 15px; } .question-grid { grid-template-columns: repeat(2, 1fr); } .verification-flow { grid-template-columns: repeat(2, 1fr); } .verification-flow > div:nth-child(3) { border-left: 0; } .verification-flow > div:nth-child(n+3) { border-top: 1px solid var(--p-line); } .verification-results article { padding: 21px; } .verification-results p { font-size: 11px; } }
@media (max-width: 640px) {
  .detail-width { width: calc(100% - 40px); } .detail-section { padding-top: 60px; scroll-margin-top: 80px; } .detail-heading { display: block; margin-bottom: 25px; } .detail-eyebrow { font-size: 10px; letter-spacing: 1.3px; } .detail-heading h2 { font-size: 27px; margin-top: 12px; letter-spacing: -1px; } .detail-heading > p { margin-top: 17px; max-width: none; font-size: 11px; }
  .module-selector { gap: 7px; } .module-selector button { font-size: 10px; gap: 5px; padding: 9px 11px; } .module-intro { padding: 24px; } .module-intro .detail-eyebrow { font-size: 10px; } .module-intro h3 { font-size: 21px; } .module-intro > p { font-size: 12px; } .module-chain { font-size: 10px; gap: 8px; } .module-chain > span { gap: 8px; } .module-points { padding: 24px; grid-template-columns: 1fr; gap: 22px; } .module-points h4 { font-size: 12px; } .module-points p { font-size: 11px; }
  .scenario-cards { grid-template-columns: 1fr; } .scenario-cards article { padding: 23px; } .scenario-cards h3 { font-size: 16px; } .scenario-cards p { font-size: 12px; } .scenario-cards article > div { font-size: 10px; margin-top: 15px; }
  .architecture-notes { grid-template-columns: 1fr; gap: 24px; padding-block: 25px; } .architecture-notes h3 { font-size: 14px; } .architecture-notes p { font-size: 12px; } .tech-stack { gap: 8px; padding-block: 16px; } .tech-stack span { font-size: 9px; } .tech-stack span:first-child { width: 100%; }
  .agent-section { margin-top: 60px; padding-block: 50px; } .agent-facts { gap: 15px; padding-block: 20px; } .agent-facts strong { font-size: 28px; } .agent-facts strong span { font-size: 10px; line-height: 1.7; } .agent-facts p { font-size: 9px; line-height: 1.9; } .mechanism-grid { grid-template-columns: 1fr; gap: 10px; margin-top: 18px; } .mechanism-grid article { padding: 24px; } .mechanism-grid article > span { font-size: 9px; } .mechanism-grid h3 { font-size: 16px; } .mechanism-grid p { font-size: 12px; }
  .question-types { margin-top: 30px; } .subsection-heading h3 { font-size: 16px; line-height: 1.7; } .subsection-heading p { font-size: 11px; line-height: 1.9; } .question-grid { grid-template-columns: 1fr; margin-top: 24px; gap: 20px; } .question-grid h4 { font-size: 13px; } .question-grid p { font-size: 11px; } .runtime-note { align-items: flex-start; flex-wrap: wrap; padding: 18px; gap: 12px; margin-top: 27px; } .runtime-note > .el-icon { font-size: 18px; margin-top: 4px; } .runtime-note p { flex: 1; font-size: 11px; } .runtime-note > a { margin-left: 30px; width: calc(100% - 30px); font-size: 10px; }
  .verification-flow > div { padding: 21px; } .verification-flow h3 { font-size: 14px; } .verification-flow p { font-size: 11px; } .verification-results { grid-template-columns: 1fr; gap: 10px; margin-top: 14px; } .verification-results article { padding: 22px; } .verification-results h3 { font-size: 14px; } .verification-results p { font-size: 12px; } .verification-boundary { flex-direction: column; align-items: flex-start; gap: 14px; } .verification-boundary p { font-size: 10px; }

}
</style>
