# 第三方组件许可

SXDevOps 自有代码使用 [MIT License](LICENSE)。依赖和容器中的系统组件保留各自许可，不能用项目 MIT 许可覆盖。

前端每次 `npm run build` 前从已安装的生产依赖生成完整许可和版权声明，随发行文件保存在 `/assets/third-party-notices.txt`。缺少许可元数据或声明文件会阻止构建。分发前端文件时应同时保留该文件。

`@vue/devtools-api 6.6.4` 的 npm 包未附许可文件，已从上游同版本标签补齐；`lodash-unified 1.0.3` 未提供独立许可文件或源码地址，已保留发布者声明的 MIT 许可、作者元数据及标准 MIT 全文。补充记录按精确版本维护在 `frontend/licenses/`，升级后重新核对。

Python 包附带的许可文件由 pip 安装在对应 `.dist-info` 目录，发行容器保留这些文件。缺失文件的包补充声明、来源和核对版本保存在 `licenses/python/`，随镜像复制到 `/app/licenses/python/`。其中四个 Alibaba Python 包未提供许可文件，补充材料明确区分发布者声明、标准 Apache-2.0 全文和未能恢复的上游 NOTICE。发行镜像还保留 `/usr/share/doc/` 等系统包版权声明，以及 `/app/LICENSE` 和本文件。重新打包、裁剪依赖时也必须保留相应声明。

当前依赖包含 Paramiko（LGPL-2.1）、Certifi（MPL-2.0）、orjson（MPL-2.0 AND (Apache-2.0 OR MIT)）和其他具有独立许可的组件。项目没有修改这些库；下游应保留动态替换能力、许可文本及上游源码获取方式。若修改或重新分发相关库，应按对应 LGPL / MPL 条款提供所需源码和修改说明。

- [Paramiko 源码和发行版](https://github.com/paramiko/paramiko)
- [Certifi 源码和发行版](https://github.com/certifi/python-certifi)
- [orjson 源码和发行版](https://github.com/ijl/orjson)
- [本轮依赖版本与许可清单](docs/releases/v2.0.0-dependency-licenses.json)

清单记录本地验证环境的依赖闭包，不代表未来 `>=` 约束解析出的全部版本。每次构建镜像须重新核对实际安装版本、发行文本、可选依赖和系统包；本轮清单不能替代新发行物的检查。
