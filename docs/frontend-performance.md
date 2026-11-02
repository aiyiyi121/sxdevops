# 产品页首次加载与静态压缩

产品介绍页只注册实际使用的图标容器。完整 Element Plus 插件及全局图标在导航到其他页面前加载，工作台、登录页及权限校验继续沿用原流程。构建器按实际共享依赖拆包，避免将产品页的小组件与整套组件库强制放进同一个文件。

产品截图保留原 WebP 文件、尺寸、内容指纹、延迟加载及大图交互，不降低清晰度。优化加载时序时应核对全部标题、链接、图片与交互，而不仅核对首屏。

## 构建

`cd frontend && npm run build` 在 Vite 构建完成后生成 `.gz` 和 `.br` 静态副本。处理 HTML，以及至少 1 KiB 的 JS、CSS、SVG、JSON 和文本，且只保留比原文件小的副本。压缩在构建时完成，访问时不会增加服务器的实时 Brotli 压缩负担；原文件始终保留。

## Nginx 接入

以下配置适用于独立静态目录和已有反向代理，要求 Nginx 启用 `http_gzip_static_module`，可用 `nginx -V` 核实。Brotli 使用预压缩文件，不依赖额外动态模块。

1. 将 `docker/nginx/static-compression.conf` 放到 HTTP 级别的 include 目录，例如 `/etc/nginx/conf.d/sxdevops-static-encoding.conf`。
2. 将另外两份 `docker/nginx/static-compression-*.conf` 放入 `/etc/nginx/snippets/`，文件名分别为 `sxdevops-static-compression-response.conf` 和 `sxdevops-static-compression-locations.conf`。
3. 在现有站点的 `server` 内包含 `include /etc/nginx/snippets/sxdevops-static-compression-locations.conf;`。保留原静态根目录、API、WebSocket、Grafana、TLS 和路由回退。
4. 在现有 `location = /index.html` 内使用下面的内容协商，同时保留站点原来的所有安全头和 `Cache-Control: no-store`：

```nginx
types { text/html html br; }
try_files $uri$sxdevops_brotli_suffix $uri =404;
gzip off;
gzip_vary off;
gzip_static on;
add_header Content-Encoding $sxdevops_content_encoding always;
add_header Vary Accept-Encoding always;
```

默认优先选择客户端支持的 Brotli；缺少 `.br` 或客户端不支持时，由 `gzip_static` 选择 Gzip，最后回退原文件。显式 `q=0` 会拒绝对应编码。响应保留正确的原始 MIME 类型、`Content-Encoding`、`Vary: Accept-Encoding` 与安全头。新增 `add_header` 会影响 Nginx 的头部继承，集成时必须检查站点额外安全头。

仅在静态资源位置启用这些规则，不缓存或压缩认证接口、业务 API、WebSocket 或 Grafana 流式响应。HTML 保持不缓存，带构建指纹的 JS/CSS 保持长期缓存，截图保持原缓存策略。

发布必须包含全部原文件与压缩副本，先运行 `nginx -t`，再平滑重载。验证两域名的 HTML、JS、CSS、SVG 在 `br`、`gzip`、`identity` 和 `q=0` 下的内容、MIME、安全头及缓存策略，并在真实浏览器中检查导航到登录页和工作台。
