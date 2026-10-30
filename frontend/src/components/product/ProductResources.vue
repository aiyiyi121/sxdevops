<template>
  <div class="product-resources">
  <section id="start" class="resource-section">
    <div class="resource-heading"><div><p class="resource-eyebrow">{{ sectionLabel('start') }}</p><h2>从体验开始，<br />在自己的环境落地。</h2></div><p>选择部署方式，了解运行条件。<br />获取源码、准备配置，逐步接入你的资源与数据。</p></div>
    <slot />
    <div class="deployment-options">
      <article><div class="deployment-title"><el-icon><Box /></el-icon><h3>Docker Compose</h3><span>源码构建</span></div><p>仓库编排包含应用、MySQL、Redis、CMDB 同步调度器和 AIOps worker，适合先在独立环境建立完整工作链路。</p><ol><li><strong>准备配置</strong><span>获取源码，设置独立的 SECRET_KEY、数据库密码与 CMDB 凭据加密密钥。</span></li><li><strong>启动服务</strong><span>通过 Compose 构建和启动，应用与 worker 使用一致的镜像、配置和共享 checkpoint。</span></li><li><strong>接入场景</strong><span>按需纳管资产、配置数据源与模型，先验证一条明确的查询或巡检流程。</span></li></ol><a :href="`${repository}#快速启动`" target="_blank" rel="noopener noreferrer">查看 Compose 启动步骤 <el-icon><TopRight /></el-icon></a></article>
      <article><div class="deployment-title"><el-icon><Connection /></el-icon><h3>Kubernetes</h3><span>清单部署</span></div><p>使用仓库中的 Kubernetes 清单部署应用、MySQL 和 Redis，结合镜像仓库、持久化存储及实际环境维护配置。</p><ol><li><strong>准备镜像与存储</strong><span>构建并推送 OCI 镜像，设置集群可访问的镜像地址、凭据和 PVC。</span></li><li><strong>补齐异步运行组件</strong><span>当前基础清单需按 v2 发布指南补充 AIOps worker，并配置应用与 worker 共用的 MySQL checkpoint。</span></li><li><strong>验证与升级</strong><span>检查服务、日志和任务队列，按发布指南执行数据库迁移、备份与回退。</span></li></ol><a :href="doc('Kubernetes部署指南.md')" target="_blank" rel="noopener noreferrer">查看 Kubernetes 部署指南 <el-icon><TopRight /></el-icon></a></article>
    </div>

    <div class="faq-section"><div class="resources-subheading"><p class="resource-eyebrow">常见问题 / 使用前你可能想了解</p><h3>把关键问题，先说清楚。</h3></div><div class="faq-list"><details v-for="(faq, index) in faqs" :key="faq.question"><summary><span>0{{ index + 1 }}</span>{{ faq.question }}<el-icon class="faq-chevron"><ArrowDown /></el-icon></summary><p>{{ faq.answer }}</p></details></div></div>
  </section>

  <section id="resources" class="resource-section documentation-section">
    <div class="resource-heading"><div><p class="resource-eyebrow">{{ sectionLabel('resources') }}</p><h2>继续深入，<br />找到对应的文档。</h2></div><p>从首次使用到日常运维，按当前目标阅读。<br />操作手册、接入指南与实现说明，持续沉淀在仓库中。</p></div>
    <div class="document-groups"><div v-for="group in documentGroups" :key="group.title" class="document-group"><h3><el-icon><component :is="group.icon" /></el-icon>{{ group.title }}</h3><div class="documentation-grid"><a v-for="resource in group.documents" :key="resource.title" :href="doc(resource.path)" target="_blank" rel="noopener noreferrer"><div><h4>{{ resource.title }}</h4><p>{{ resource.description }}</p></div><el-icon><TopRight /></el-icon></a></div></div></div>
    <div class="community-note"><span><el-icon><ChatDotRound /></el-icon></span><div><h3>欢迎把真实问题带进来，一起把平台做得更好。</h3><p>贡献数据源、MCP 工具、Skill、评测案例或文档，也可以从一个 Issue 开始交流。</p></div><a :href="`${repository}/issues`" target="_blank" rel="noopener noreferrer">反馈与共建 <el-icon><TopRight /></el-icon></a></div>
  </section>
  </div>
</template>

<script setup>
import { ArrowDown, Box, ChatDotRound, Connection, Document, Finished, MagicStick, TopRight } from '@element-plus/icons-vue'
import { sectionLabel } from './sections'

const repository = 'https://github.com/aiyiyi121/sxdevops'
const doc = path => `${repository}/blob/main/docs/${path}`
const faqs = [
  { question: '可以先接入已有监控和日志系统吗？', answer: '可以。平台通过数据源和工具配置衔接已有 Prometheus / Grafana、日志与链路系统，不要求先搬迁所有数据。建议先选择一个环境，配置资源关联和数据源，再验证告警、日志、Trace 与事件能否形成连续的证据链。' },
  { question: 'AI 会直接执行重启、修改配置或批量命令吗？', answer: '查询与分析按当前账号权限取证；写入和执行类动作先经过预检，形成待确认动作或任务草稿。用户核对目标与参数后，由后端再次检查身份、权限和范围，再通过平台 API 执行。自愈建议也沿用这条确认链路。' },
  { question: 'Action、Skill 和 MCP 分别负责什么？', answer: 'Action 定义本次任务的入口、上下文和流程边界；Skill 提供证据方法、查询规范和输出要求；MCP 提供实际可调用的工具。能力挂载、工具启用与权限共同决定本轮行为，一个 Skill 可以被多个问答类型复用。' },
  { question: '分析过程被中断后，能否继续？', answer: '异步分析由数据库队列和独立 worker 承接。已完成并保存 checkpoint 的节点可以恢复后复用，恢复会重新校验权限、MCP 与原始范围。节点内部中断仍可能重试当前请求，因此外部工具需要具备幂等性；图版本变化时按发布指南处理未完成任务。' },
  { question: '任务执行成功，就代表故障已经解决了吗？', answer: '需要继续检查。提前配置基线的任务可在观察窗口后核对同一告警恢复事件，返回“告警已恢复”“验证未通过”或“证据不足”。告警恢复说明观察到状态变化，操作因果与业务整体健康还需要更多证据。' },
  { question: 'CMDB 中有了资产，就可以直接执行任务吗？', answer: '需要显式接入。在任务中心选择 CMDB 资产，补充执行信息并保存后，它才成为执行资源。资产名称、IP、负责人等基础信息沿用 CMDB，执行凭据单独维护；源资产停机、下线或删除时会限制新的关联任务执行。' },
]
const documentGroups = [
  { title: '使用入门', icon: Document, documents: [
    { title: '平台使用文档', description: '模块入口、操作说明与推荐流程', path: '用户使用文档.md' },
    { title: '知识图谱与环境配置', description: '准备环境、服务关系与资源绑定', path: '用户使用文档.md#关键前提必须配置知识图谱环境' },
    { title: '可观测性使用指南', description: '指标、日志、链路与数据源配置', path: '用户使用文档.md#可观测性' },
    { title: '事件中心使用指南', description: '筛选时间线，关联环境与事件源', path: '用户使用文档.md#事件中心' },
  ] },
  { title: '资产与容器', icon: Connection, documents: [
    { title: 'CMDB 使用手册', description: '资产纳管、资源树、容量与治理', path: 'CMDB使用手册.md' },
    { title: 'CMDB 接入任务资源', description: '执行信息、凭据与资产生命周期', path: 'task-resource-cmdb.md' },
    { title: 'K8s 工作台与授权', description: '集群、命名空间、终端与日志', path: 'K8s工作台与用户授权.md' },
    { title: 'Docker 工作台', description: '环境、容器、镜像与操作边界', path: 'Docker工作台.md' },
  ] },
  { title: '智能体与任务', icon: MagicStick, documents: [
    { title: '问答能力与 Skills', description: '六类入口、方法复用与工具关联', path: 'AIOps-问答能力与Skills.md' },
    { title: '任务中心使用指南', description: '执行资源、任务工作台与结果查询', path: '用户使用文档.md#任务中心' },
    { title: 'LangGraph 运行机制', description: '图节点、checkpoint 与中断恢复', path: 'AIOps-LangGraph-试点说明.md' },
    { title: '处置效果验证', description: '告警基线、观察窗口与判定口径', path: 'AIOps-处置效果验证.md' },
  ] },
  { title: '部署与维护', icon: Finished, documents: [
    { title: 'Kubernetes 部署指南', description: '镜像、存储、配置与部署清单', path: 'Kubernetes部署指南.md' },
    { title: 'v2 升级与发布指南', description: '升级顺序、worker、备份与回退', path: 'releases/v2.0.0-release-guide.md' },
    { title: 'vSphere 指标接入', description: '接入 Prometheus 与真实运行指标', path: 'vsphere-vm-prometheus-metrics.md' },
    { title: '工作台主题说明', description: '三套主题、使用方式与配色适配', path: 'frontend-theme.md' },
  ] },
]
</script>

<style scoped>
.resource-section { width: min(1240px, calc(100% - 96px)); margin-inline: auto; padding-top: 100px; scroll-margin-top: 90px; }
.resource-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 36px; margin-bottom: 35px; }
.resource-eyebrow { color: var(--p-accent); font-size: 10px; letter-spacing: 1.8px; font-weight: 600; }
.resource-heading h2 { font-size: 37px; font-weight: 650; line-height: 1.4; letter-spacing: -1.4px; margin-top: 14px; }
.resource-heading > p { color: var(--p-muted); font-size: 13px; line-height: 1.95; padding-bottom: 4px; }
a { color: inherit; text-decoration: none; }
:is(a, summary):focus-visible { outline: 2px solid var(--p-accent); outline-offset: 4px; }
.deployment-options { display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px; }
.deployment-options article { display: flex; flex-direction: column; align-items: flex-start; padding: 30px; background: var(--p-surface); border: 1px solid var(--p-line); border-radius: 12px; }
.deployment-title { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; width: 100%; }
.deployment-title > .el-icon { color: var(--p-accent); font-size: 22px; }
.deployment-title h3 { font-size: 18px; font-weight: 600; }
.deployment-title > span { color: var(--p-subtle); border: 1px solid var(--p-line); border-radius: 4px; padding: 2px 6px; font-size: 9px; margin-left: auto; }
.deployment-options article > p { color: var(--p-muted); font-size: 12px; line-height: 1.95; margin-top: 18px; }
.deployment-options ol { list-style: none; counter-reset: steps; margin-block: 25px; display: grid; gap: 20px; }
.deployment-options li { padding-left: 31px; position: relative; counter-increment: steps; }
.deployment-options li::before { content: counter(steps, decimal-leading-zero); position: absolute; left: 0; top: 2px; color: var(--p-accent); font-size: 10px; font-family: ui-monospace, monospace; }
.deployment-options li strong { display: block; font-size: 12px; font-weight: 600; }
.deployment-options li span { display: block; color: var(--p-muted); font-size: 11px; line-height: 1.95; margin-top: 5px; }
.deployment-options article > a { display: inline-flex; align-items: center; gap: 8px; font-size: 11px; margin-top: auto; color: var(--p-accent); }
.faq-section { margin-top: 60px; }
.resources-subheading h3 { font-size: 23px; font-weight: 600; letter-spacing: -.5px; margin-top: 12px; }
.faq-list { margin-top: 25px; border-top: 1px solid var(--p-line); }
.faq-list details { border-bottom: 1px solid var(--p-line); }
.faq-list summary { display: flex; align-items: center; gap: 18px; padding: 22px 5px; font-size: 14px; list-style: none; cursor: pointer; }
.faq-list summary::-webkit-details-marker { display: none; }
.faq-list summary > span { color: var(--p-subtle); font-size: 10px; font-family: ui-monospace, monospace; }
.faq-chevron { margin-left: auto; color: var(--p-subtle); font-size: 12px; flex-shrink: 0; }
.faq-list details[open] .faq-chevron { transform: rotate(180deg); color: var(--p-accent); }
.faq-list details[open] summary { color: var(--p-accent); }
.faq-list details > p { color: var(--p-muted); font-size: 13px; line-height: 2.05; padding: 0 36px 24px; max-width: 980px; }
.document-groups { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 32px 24px; }
.document-group > h3 { display: flex; align-items: center; gap: 9px; font-size: 14px; font-weight: 600; margin-bottom: 15px; }
.document-group > h3 > .el-icon { color: var(--p-accent); font-size: 17px; }
.documentation-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.documentation-grid a { display: flex; align-items: center; gap: 13px; padding: 20px; border: 1px solid var(--p-line); border-radius: 9px; background: var(--p-surface); min-width: 0; transition: border-color .2s, background .2s, transform .2s; }
.documentation-grid a > .el-icon:last-child { color: var(--p-subtle); font-size: 12px; margin-left: auto; flex-shrink: 0; }
.documentation-grid a:hover { border-color: var(--p-accent); background: var(--p-raised); transform: translateY(-2px); }
.documentation-grid h4 { font-size: 13px; font-weight: 600; }
.documentation-grid p { color: var(--p-muted); font-size: 10px; margin-top: 4px; line-height: 1.8; }
.community-note { display: flex; align-items: center; gap: 18px; margin-top: 30px; padding: 25px; border: 1px solid var(--p-line); border-radius: 10px; }
.community-note > span { width: 40px; height: 40px; display: grid; place-items: center; border: 1px solid var(--p-line); background: var(--p-accent-wash); border-radius: 10px; color: var(--p-accent); font-size: 22px; flex-shrink: 0; }
.community-note h3 { font-size: 14px; font-weight: 600; }
.community-note p { margin-top: 7px; color: var(--p-muted); font-size: 11px; line-height: 1.8; }
.community-note > a { display: flex; align-items: center; gap: 7px; margin-left: auto; color: var(--p-accent); font-size: 11px; white-space: nowrap; }
@media (max-width: 1150px) { .resource-section { width: calc(100% - 64px); } .resource-heading > p { font-size: 12px; } .deployment-options article { padding: 25px; } .documentation-grid a { padding: 20px; gap: 10px; } }
@media (max-width: 900px) { .resource-section { padding-top: 74px; } .resource-heading h2 { font-size: 30px; } .resource-heading > p { font-size: 11px; max-width: 300px; } .document-groups { grid-template-columns: 1fr; } .deployment-title h3 { font-size: 16px; } .deployment-title > span { margin-left: 32px; } .community-note h3 { font-size: 13px; } }
@media (max-width: 640px) { .resource-section { width: calc(100% - 40px); padding-top: 60px; scroll-margin-top: 80px; } .resource-heading { display: block; margin-bottom: 25px; } .resource-eyebrow { font-size: 10px; letter-spacing: 1.3px; } .resource-heading h2 { font-size: 27px; letter-spacing: -1px; margin-top: 12px; } .resource-heading > p { font-size: 11px; max-width: none; margin-top: 17px; } .deployment-options { grid-template-columns: 1fr; gap: 12px; } .deployment-options article { padding: 24px; } .deployment-title h3 { font-size: 17px; } .deployment-title > span { margin-left: auto; } .deployment-options article > p { font-size: 12px; } .deployment-options li span { font-size: 11px; } .faq-section { margin-top: 44px; } .resources-subheading h3 { font-size: 19px; } .faq-list summary { gap: 11px; padding-block: 20px; font-size: 12px; } .faq-list details > p { padding: 0 5px 23px 29px; font-size: 11px; } .documentation-grid { grid-template-columns: 1fr; gap: 10px; } .documentation-grid h4 { font-size: 13px; } .documentation-grid p { font-size: 11px; } .community-note { align-items: flex-start; flex-wrap: wrap; padding: 21px; gap: 12px; } .community-note > span { width: 34px; height: 34px; font-size: 18px; } .community-note > div { flex: 1; } .community-note h3 { font-size: 13px; line-height: 1.8; } .community-note p { font-size: 11px; } .community-note > a { margin-left: 46px; width: calc(100% - 46px); font-size: 10px; } }
</style>
