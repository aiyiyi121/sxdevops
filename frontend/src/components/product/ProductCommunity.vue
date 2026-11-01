<template>
  <section id="community" class="community-section" aria-labelledby="community-title">
    <div class="community-card">
      <div class="community-copy">
        <h2 id="community-title">关于项目与致谢</h2>
        <p>SxDevOps 是一个由个人独立维护的开源项目。从 UI 与架构设计，到功能开发、测试验证，主要依靠我的业余时间推进；模型调用所需的 Token 费用也由我个人承担。</p>
        <p>受限于个人时间与精力，当前版本仍有不少需要打磨的地方。欢迎通过 <a :href="`${repository}/issues`" target="_blank" rel="noopener noreferrer">Issue</a> 反馈问题、提出建议，也欢迎提交 <a :href="`${repository}/pulls`" target="_blank" rel="noopener noreferrer">PR</a> 参与共建。我会在能力范围内持续维护、迭代新版本。</p>
      </div>
      <figure class="community-follow">
        <img src="/promo/wechat-qrcode.png" alt="作者微信公众号二维码" width="430" height="430" loading="lazy" decoding="async" />
        <figcaption><strong>欢迎关注我的公众号</strong></figcaption>
      </figure>
      <div class="community-thanks">
        <h3>最后感谢支持与传播</h3>
        <p>感谢阿铭老师对本项目的启发与宣传。如有大模型或 AIOps 学习需求，可通过 <a href="https://www.amingedu.com/" target="_blank" rel="noopener noreferrer">铭科智联 · 跟阿铭学大模型/AIOps <el-icon><TopRight /></el-icon></a> 的公开渠道添加微信咨询。</p>
        <p>感谢 <a href="https://agent2048.com/zh/projects/2cmcyhvxsk4q" target="_blank" rel="noopener noreferrer">Agent2048 <el-icon><TopRight /></el-icon></a> 对本项目的推广与展示。</p>
      </div>
    </div>
  </section>
</template>

<script setup>
import { TopRight } from '@element-plus/icons-vue'

const repository = 'https://github.com/aiyiyi121/sxdevops'
</script>

<style scoped>
.community-section { width: min(1240px, calc(100% - 96px)); margin: 0 auto 64px; scroll-margin-top: 100px; }
.community-card { display: grid; grid-template-columns: minmax(0, 1fr) 180px; gap: 32px 52px; padding: 40px; background: var(--p-surface); border: 1px solid var(--p-line); border-radius: 12px; }
.community-copy h2 { color: var(--p-ink); font-size: 26px; font-weight: 600; line-height: 1.5; letter-spacing: -.6px; margin: 0 0 20px; }
.community-copy > p, .community-thanks p { color: var(--p-muted); font-size: 13px; line-height: 1.95; }
.community-copy > p + p { margin-top: 12px; }
a { color: var(--p-accent); text-decoration: none; overflow-wrap: anywhere; }
a:hover { text-decoration: underline; text-underline-offset: 3px; }
a:focus-visible { outline: 2px solid var(--p-accent); outline-offset: 4px; border-radius: 2px; }
a .el-icon { font-size: 11px; vertical-align: middle; }
.community-follow { margin: 0; align-self: center; text-align: center; }
.community-follow img { display: block; width: 100%; max-width: 180px; height: auto; border-radius: 8px; background: #fff; }
.community-follow figcaption { display: flex; flex-direction: column; gap: 7px; margin-top: 16px; }
.community-follow strong { color: var(--p-ink); font-size: 13px; font-weight: 600; }
.community-thanks { grid-column: 1 / -1; border-top: 1px solid var(--p-line); padding-top: 24px; }
.community-thanks h3 { color: var(--p-ink); font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.community-thanks p + p { margin-top: 8px; }
@media (max-width: 1150px) { .community-section { width: calc(100% - 64px); } .community-card { gap: 28px; padding: 30px; } }
@media (max-width: 700px) { .community-section { width: calc(100% - 40px); margin-bottom: 40px; } .community-card { grid-template-columns: minmax(0, 1fr); padding: 24px; gap: 26px; } .community-copy h2 { font-size: 23px; } .community-follow { width: 180px; justify-self: center; } .community-thanks { padding-top: 22px; } }
</style>
