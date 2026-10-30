# 安全问题反馈

请针对当前主线代码报告问题，并注明所用版本或提交 SHA。历史版本修复应升级到当前维护版本；项目暂未承诺独立的旧版本安全维护周期。

## 私密反馈

仓库的 [GitHub 私密漏洞报告](https://github.com/aiyiyi121/sxdevops/security/advisories/new)需要维护者先启用 Private vulnerability reporting。2026-10-30 通过 GitHub API 核实，该设置为关闭状态，目前不能将此链接视为已可用的报告渠道。

维护者可在 [仓库安全设置](https://github.com/aiyiyi121/sxdevops/settings/security_analysis)启用 Private vulnerability reporting，随后核对报告入口，并用 `GET /repos/aiyiyi121/sxdevops/private-vulnerability-reporting` 确认 `enabled: true`。未配置专用安全邮箱前，必须先完成此项再对外承诺私密报告服务。

若入口不可用，请通过 [维护者 GitHub 主页](https://github.com/aiyiyi121)已有的私密联系方式联系。项目目前未公布专用安全邮箱；没有可用私密渠道时，只在 Issue 留下“需要私密安全联系渠道”的请求，不公开漏洞细节、载荷或凭据。维护者应在正式对外运营前确认至少一条渠道可用。

报告建议包含版本、受影响模块、最小复现步骤、必要权限、预期与实际行为及脱敏证据。不要附带真实 Token、密码、云密钥、客户数据或可直接访问的生产连接信息。

## 处理与披露

维护者确认问题和影响范围后，与报告者协商修复及披露时间；公开说明应包含修复版本、受影响范围及必要的轮换或升级步骤。目前不承诺固定响应时限。

已发现凭据泄露时，应先撤销会话、关闭相关连接并轮换外部凭据。删除仓库文件或修复权限代码不会自动消除已泄露信息。

部署、RBAC 和公开演示的安全边界见[账号、RBAC 与安全](docs/user-permission-security.md)。
