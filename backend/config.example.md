# 本地 JSON 配置

数据库与缓存需要本地配置时，把同目录的 [config.example.json](config.example.json) 复制为 `config.json` 并修改。该文件可能包含密码，已被 Git 忽略。

**有效 JSON 字段优先于对应环境变量。** 不要直接复制示例后以为环境变量还能覆盖其中数据库密码或连接地址；完整变量、默认值和容器传参方式见[配置参考](../docs/configuration.md)。

| 部分 | 字段 | 用途 |
| --- | --- | --- |
| `database` | `type` | 默认 `postgresql`（推荐）；备选 `mysql`，本地开发可显式选 `sqlite` |
| `database` | `database_name`、`user`、`password`、`host`、`port` | PostgreSQL / MySQL 库名及连接参数 |
| `database` | `charset`、`conn_max_age`、`options` | 字符集、连接复用及数据库选项 |
| `cache` | `type` | `redis` 或 `local` |
| `cache` | `redis_url`、`key_prefix`、`default_timeout_seconds` | Redis 地址、键前缀和缓存时长 |
| `cache` | `ignore_redis_errors` | Redis 异常容错；应评估对限流的影响 |

主示例使用 PostgreSQL；MySQL 示例见 [config.example.mysql.json](config.example.mysql.json)。本地开发可将 [config.example.sqlite.json](config.example.sqlite.json) 复制为 `config.json`，继续使用 `backend/db.sqlite3`，无需转换现有 SQLite 数据。未配置 Redis 时使用进程内缓存。多实例应使用共享缓存与共享 checkpoint，不能仅复制本地配置文件实现共享状态。

[文档目录](../docs/README.md)
