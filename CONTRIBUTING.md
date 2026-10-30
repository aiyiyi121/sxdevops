# 贡献指南

欢迎通过 Issue、Pull Request 或文档修正参与。开发环境见[快速开始](docs/getting-started.md)，完整规范见 [AGENTS.md](AGENTS.md)。

## 开发与提交

- 后端业务放在对应 Django app；前端页面、API、路由和状态分别放在既有目录中。
- Python 使用 4 空格缩进；Vue 页面使用 PascalCase 文件名，API 和 store 延续现有命名。
- 涉及权限时先落实后端 RBAC，再同步路由、菜单、按钮及 WebSocket 校验；遵循项目 [RBAC 集成规范](.codex/skills/sxdevops-rbac-feature-integration/SKILL.md)。
- 界面遵循项目[工作台 UI 规范](.codex/skills/sxdevops-feishu-ui/SKILL.md)，适配浅色、炭灰和深蓝灰。
- 提交使用 `feat:`、`fix(scope):`、`docs:` 等既有风格，一次提交围绕同一目的。

PR 说明用户可见变化、涉及模块、迁移与配置影响、验证结果；界面改动附真实截图。安全漏洞按 [SECURITY.md](SECURITY.md) 私密反馈。

## 验证

```bash
cd backend
python manage.py check
python manage.py test --noinput
cd ../frontend
npm ci
npm run build
```

后端测试使用隔离测试数据库，数据库账号须有对应建库权限。针对行为变化在邻近 `tests.py` 或 `test_*.py` 增加有意义的回归；Windows 不能覆盖的 PTY / Shell 场景在 Linux 镜像中补验。

前端当前没有统一自动化测试套件。界面修改至少通过生产构建，并在浏览器检查权限、三套主题和窄屏。后端无热更新，修改后重启 Daphne 及受影响 worker。

全量测试仍有已知失败，最近结果见 [v2.0.0 验证记录](docs/releases/v2.0.0-validation.md)。记录实际失败、环境和基线对比，不把专项通过写成全量通过。

## 文档维护

- 正式文档统一从 [docs/README.md](docs/README.md) 导航，按功能维护单一说明。
- 使用指南只写当前行为；运行边界和未实现能力明确标注，方案不能当作交付结果。
- 发布记录集中于 `docs/releases/`，写明提交、日期、环境和验证限制。临时逐轮日志留在忽略的运行目录。
- 中文文件保存为 UTF-8，提交前检查替换字符、常见乱码、本地链接和 `git diff --check`。
- 修改 README 产品展示内容时同步检查[截图](docs/screenshots/README.md)，不使用占位图或生产敏感信息。

## 发布检查

1. 验证候选提交的测试、前端构建、迁移、关键权限与全新环境启动；明确未通过项。
2. 核对版本元数据、更新说明和升级要求，记录源码 SHA 及镜像摘要。
3. 执行敏感信息和第三方依赖许可检查；保留 MIT `LICENSE` 与依赖要求的许可声明。
4. 确认配置、密钥、数据库、日志和构建产物未被跟踪；历史泄露须轮换凭据，删除文件不等于清理 Git 历史。
5. 备份、排空并升级应用和两个后台服务，按[运维指南](docs/deployment.md)验证和准备回退。
6. 新版本使用新的 SemVer 标签；正式发布后的标签保持稳定，不用移动标签代替后续补丁版本。

本清单是每次发布的检查要求，不代表历史版本全部通过。安全联系方式的可用性、依赖许可和凭据历史应逐次复核。
