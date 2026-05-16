# Nacos 热更新限制

> 创建日期：2026-05-16
> 最后更新：2026-05-16

## 问题

以下工厂函数使用 `@lru_cache(maxsize=1)` 缓存客户端实例：

- `src/common/aliyun/pnvs_client.py` — `get_pnvs_client()`
- `src/common/aliyun/dm_smtp_client.py` — `get_dm_smtp_client()`
- `src/apps/user/sso_clients.py`（计划中；追踪于 B-007）— `get_qq_oauth_client()` / `get_thbwiki_oauth_client()`

Nacos 配置变更回调 `_on_nacos_config_change`（`src/common/config.py`）在收到变更通知时只更新
环境变量和 `_settings_instance`，**无法使已缓存的 lru_cache 客户端实例失效**。

## 影响

通过 Nacos 热更新以下配置 **不会生效**，必须重启容器：

- 阿里云 PNVS 凭据（`ALIYUN_PNVS_*`）
- 阿里云 DirectMail 凭据（`ALIYUN_DM_*`）
- QQ OAuth 凭据（`QQ_APP_ID` / `QQ_APP_SECRET`）
- THBWiki OAuth 凭据（`THBWIKI_CLIENT_ID` / `THBWIKI_CLIENT_SECRET`）

数据库地址、Redis 地址、JWT 密钥等**不使用 lru_cache 的配置**可以通过
`POST /admin/reload-config` 热更新。

## 操作规程

更改上述凭据后，在部署环境执行：

```bash
docker-compose restart backend
```

## 技术背景

若需支持免重启热更新，需将工厂函数改为每次调用时从 `get_settings()` 重新读取凭据，
放弃 `lru_cache`。当前规模下不做，此改动记录在 BACKLOG B-017。
