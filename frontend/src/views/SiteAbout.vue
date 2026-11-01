<template>
  <main class="site-about workbench-page-shell">
    <section class="hero panel">
      <h1>网站说明与隐私</h1>
    </section>
    <article class="panel about-content">
      <section>
        <h2>网站用途与项目身份</h2>
        <p>{{ siteStore.siteName }} 是基于 SXDevOps 开源项目的运维工作台，用于展示和使用资产管理、可观测性、任务协作与智能运维功能。</p>
        <p>项目维护者为 GitHub 用户 aiyiyi121。本站是独立的项目站点，不是 Google、云厂商或 Grafana 的官方登录入口；对接工具的名称用于说明兼容功能。</p>
        <a :href="repository" target="_blank" rel="noopener noreferrer">查看开源项目与维护者信息 ↗</a>
      </section>
      <section>
        <h2>账号与访客体验</h2>
        <p>登录表单仅用于本站平台账号。请勿填写邮箱、云平台或其他第三方账号的密码。登录不要求安装浏览器扩展、下载软件或提供银行卡信息。</p>
        <p>如登录页提供访客账号，其用途为只读体验。正式账号的可访问资源和操作由平台权限控制。</p>
      </section>
      <section>
        <h2>数据使用与本机存储</h2>
        <p>登录时，用户名和密码提交至本站认证接口，用于验证平台账号。浏览器会在本地存储登录令牌、用户资料及主题偏好；退出登录会清除本机的登录令牌和用户资料。</p>
        <p>平台会处理你主动提交的查询、配置与任务数据，并记录相关操作和访问日志，用于提供运维功能、权限审计和故障排查。请勿在公共演示环境提交真实生产凭据或个人敏感信息。</p>
        <p>使用 Grafana 等已配置的外部服务时，浏览器可能连接对应服务，其运营方会收到必要的网络请求。请仅使用管理员确认可信的接入地址。</p>
      </section>
      <section>
        <h2>联系与问题反馈</h2>
        <p>功能问题及账号、数据处理相关请求，可通过项目 Issues 联系维护者。涉及漏洞、密码或其他敏感信息时，请先阅读安全反馈说明，不要在公开 Issue 中提交这些内容。</p>
        <div class="about-links">
          <a :href="`${repository}/issues`" target="_blank" rel="noopener noreferrer">联系项目维护者 ↗</a>
          <a :href="`${repository}/blob/main/SECURITY.md`" target="_blank" rel="noopener noreferrer">安全反馈说明 ↗</a>
        </div>
      </section>
      <nav class="about-links about-navigation" aria-label="返回网站">
        <router-link to="/product">产品介绍</router-link>
        <router-link to="/login">登录工作台</router-link>
      </nav>
    </article>
  </main>
</template>

<script setup>
import { useSiteStore } from '@/stores/site'

const siteStore = useSiteStore()
const repository = 'https://github.com/aiyiyi121/sxdevops'
</script>

<style scoped>
.site-about {
  width: min(920px, 100%);
  min-height: 100vh;
  margin: 0 auto;
  padding: 24px 16px;
  color: var(--el-text-color-primary);
  gap: 6px;
}
.panel { background: var(--el-bg-color); border: 1px solid var(--el-border-color-light); }
.hero.panel { padding: 18px 24px; border-radius: 20px; }
h1 { margin: 0; font-size: 22px; }
.about-content { padding: 24px; border-radius: 16px; }
section + section { margin-top: 26px; }
h2 { margin: 0 0 10px; font-size: 16px; }
p { margin: 8px 0; color: var(--el-text-color-regular); font-size: 14px; line-height: 1.9; }
a { color: var(--el-color-primary); font-size: 13px; text-decoration: none; }
a:hover { text-decoration: underline; }
.about-links { display: flex; flex-wrap: wrap; gap: 12px 24px; }
.about-navigation { margin-top: 26px; padding-top: 20px; border-top: 1px solid var(--el-border-color-light); }
@media (max-width: 640px) {
  .site-about { padding: 12px; }
  .about-content, .hero.panel { padding: 18px; }
}
</style>
