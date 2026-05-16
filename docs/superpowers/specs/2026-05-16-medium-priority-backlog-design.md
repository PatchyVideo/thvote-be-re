# 中优先级 BACKLOG 实现设计（B-007/008/017/018/025/027/029/030）

> 创建日期：2026-05-16
> 最后更新：2026-05-16
> 作者：Claude（brainstorming 流程产物）
> 适用范围：`thvote-be-re`，8 个中优先级 BACKLOG 条目

---

## 一、概览

本文档覆盖以下 8 项，按实施顺序排列：

| 编号 | 主题 | 类型 |
|---|---|---|
| B-017 | Nacos + `lru_cache` 热更新限制文档化 | 文档 |
| B-029 | 部署机 docker-compose.yml 归属文档化 | 文档 |
| B-025 | 移除 `init_db()` / `DEBUG` 后门 | 代码删除 |
| B-018 | `_safe_log` 失败可见性 | 代码改进 |
| B-030 | Nacos import-time 阻塞改为懒加载 | 代码改进 |
| B-027 | `deploy-test.yml` flake8 改硬失败 | CI 配置 |
| B-007 | THBWiki + QQ SSO 登录 | 新功能 |
| B-008 | MongoDB → PostgreSQL 历史数据迁移脚本 | 新脚本 |

**实施原则**：所有新增配置字段统一通过 `Settings`（`src/common/config.py`）接入，经 Nacos → env var → `Settings()` 路径读取，不单独建配置加载机制。

---

## 二、B-017：Nacos + lru_cache 热更新限制

### 问题

`src/common/aliyun/pnvs_client.py`、`dm_smtp_client.py` 及后续 SSO 客户端工厂函数均使用 `@lru_cache(maxsize=1)`。Nacos 配置变更回调（`_on_nacos_config_change`）只更新环境变量和 `_settings_instance`，无法使已缓存的客户端实例失效。

### 设计

新建 `docs/architecture/nacos-hot-reload-limits.md`，内容涵盖：

1. 受影响的函数列表（`get_pnvs_client`、`get_dm_smtp_client`、未来的 `get_qq_oauth_client`、`get_thbwiki_oauth_client`）
2. 结论：**更改阿里云凭据或 SSO 凭据后，必须重启容器**，热更新对这些配置无效
3. 如需免重启热更新，需将这些函数改为每次从 `get_settings()` 读取凭据并重建客户端（放弃 `lru_cache`）——当前规模下不做，保留文档说明

---

## 三、B-029：部署机 docker-compose.yml 归属

### 问题

`docker/` 目录已从仓库删除，部署机上的 `docker-compose.yml` 由 CI workflow inline 写入（`deploy-test` job 中的 heredoc），但这一事实没有文档记录，导致维护者不清楚"谁负责这个文件"。

### 设计

新建 `docs/operations/deploy-server-setup.md`，记录：

1. 部署机上 `docker-compose.yml` 的路径：`${TEST_SERVER_DIR:-/opt/thvote/test}/docker-compose.yml`
2. 该文件**由 CI workflow 自动生成**（`deploy-test.yml` job 的 heredoc），仓库内没有对应源文件
3. 触发重写的条件：文件不存在，或文件中不含 `NACOS_ENABLED` 字段
4. 手动更新规程：若需修改 compose 内容，应修改 `deploy-test.yml` 的 heredoc，而非直接编辑部署机上的文件
5. 外部依赖说明：Postgres 使用阿里云 RDS（不在 compose 中），Redis 容器（`thvote-redis`）由 compose 管理

---

## 四、B-025：移除 init_db / DEBUG 后门

### 问题

`src/main.py` 通过 `DEBUG=true` 环境变量触发 `Base.metadata.create_all()`，这与 Alembic 迁移并存时会造成表结构脱离版本控制。

### 设计

**删除内容**：
- `_is_debug_mode()` 函数
- `lifespan` 中的整个 `if _is_debug_mode(): ... else: ...` 块
- `from .common.database import init_db` 导入

**新增内容**：在 lifespan 启动时执行 DB 连通性检查：

```python
async with get_session_maker()() as session:
    await session.execute(text("SELECT 1"))
logger.info("Database connection verified. Schema managed by Alembic.")
```

若 `SELECT 1` 失败则异常向上传播，容器启动失败，立即可见（而非静默带错运行）。

**不在范围内**：检查 `alembic_version` 表（过重，留 B-026 处理）。

---

## 五、B-018：_safe_log 失败可见性

### 问题

`UserService._safe_log` 捕获所有异常后仅写日志，无指标暴露，运维无法在不翻日志的情况下感知审计链路是否健康。

### 设计

**`src/apps/user/service.py`**：

```python
_audit_log_failures: int = 0

def get_audit_log_failures() -> int:
    return _audit_log_failures

# _safe_log 的 except 块：
global _audit_log_failures
_audit_log_failures += 1
logger.exception("ActivityLog write failed ...")
```

**`src/main.py` GET /health**：

```python
from .apps.user.service import get_audit_log_failures

failures = get_audit_log_failures()
return {
    "status": "degraded" if failures > 0 else "ok",
    "db_status": db_status,
    "vote_year": settings.vote_year,
    **({"audit_failures": failures} if failures > 0 else {}),
}
```

`status: "degraded"` 不影响服务正常运行，仅作可见性信号。计数器为进程级内存，重启归零（足够用于告警触发，不需持久化）。

---

## 六、B-030：Nacos import-time 阻塞改为懒加载

### 问题

`src/common/config.py` 第 46 行在模块 import 时同步调用 `_load_nacos_sync()`，若 Nacos 不可达，`import src.common.config` 会阻塞最长 30s，导致所有依赖 config 的模块 import 挂起。

### 设计（方案 A：懒加载）

```python
_nacos_loaded: bool = False

def get_settings() -> Settings:
    global _settings_instance, _nacos_loaded
    if _settings_instance is None:
        if not _nacos_loaded:
            _load_nacos_sync()
            _nacos_loaded = True
        _settings_instance = Settings()
    return _settings_instance
```

**删除**：模块顶层的 `_load_nacos_sync()`（当前第 46 行）。

**效果**：
- `import src.common.config` 不再触发任何网络请求
- 首次调用 `get_settings()` 时才加载 Nacos（通常在 `create_app()` 内）
- 测试 fixtures 中若未调用 `get_settings()`，Nacos 完全不被触发

`reload_settings()` 保持现有行为（已直接创建 `Settings()`，不受此变更影响）。

---

## 七、B-027：flake8 CI 改硬失败

### 设计

两步：

1. 本地跑 `flake8 src/ --max-line-length=88`，修复所有违规（不引入新逻辑，仅格式修正）
2. 将 `deploy-test.yml` 第 64 行改为：
   ```yaml
   - name: 代码风格检查
     run: flake8 src/ --max-line-length=88
   ```
   去掉 `|| true`，使 lint job 在有违规时真正失败、阻断后续 test + deploy。

**依赖**：步骤 1 必须先完成，否则 CI 立即红。

---

## 八、B-007：THBWiki + QQ SSO 登录

### 8.1 数据库（migration 0004）

```sql
ALTER TABLE "user" ADD COLUMN thbwiki_uid VARCHAR(128);
ALTER TABLE "user" ADD COLUMN qq_openid  VARCHAR(128);
CREATE UNIQUE INDEX uq_user_thbwiki_uid ON "user"(thbwiki_uid) WHERE thbwiki_uid IS NOT NULL;
CREATE UNIQUE INDEX uq_user_qq_openid   ON "user"(qq_openid)   WHERE qq_openid   IS NOT NULL;
```

ORM（`src/db_model/user.py`）新增对应 `mapped_column`。

### 8.2 新配置字段（Settings）

```python
qq_app_id:             Optional[str] = Field(None, validation_alias="QQ_APP_ID")
qq_app_secret:         Optional[str] = Field(None, validation_alias="QQ_APP_SECRET")
thbwiki_client_id:     Optional[str] = Field(None, validation_alias="THBWIKI_CLIENT_ID")
thbwiki_client_secret: Optional[str] = Field(None, validation_alias="THBWIKI_CLIENT_SECRET")
sso_callback_base_url: Optional[str] = Field(None, validation_alias="SSO_CALLBACK_BASE_URL")
```

全部通过 Nacos → env → `Settings()` 路径读取，无单独加载逻辑。

### 8.3 Redis LoginSession

Key：`sso-session:{uuid4}`，TTL 600s，JSON 格式：

```json
{"thbwiki_uid": "123", "qq_openid": null}
```

辅助函数放 `src/apps/user/sso_session.py`：`create_sso_session(redis, data) → sid`、`consume_sso_session(redis, sid) → dict | None`。

`consume_sso_session` 使用 `GETDEL`（Redis 6.2+ 原子命令）一次完成读取并删除，防止并发请求重复消费同一 sid。Redis < 6.2 时退化为 Lua 脚本（`GET` + `DEL` 原子执行）。

### 8.4 OAuth 流程

**QQ OAuth2**（三步）：
```
GET /user/sso/qq/authorize
  → 302 https://graph.qq.com/oauth2.0/authorize?...

GET /user/sso/qq/callback?code=&state=
  → POST graph.qq.com/oauth2.0/token → access_token
  → GET  graph.qq.com/oauth2.0/me?access_token=...  （JSONP，需解析）
  → 存 sso-session:{sid} = {"qq_openid": openid}
  → 返回 {"sid": "..."}
```

**THBWiki OAuth2**（MediaWiki OAuth2 扩展，两步）：
```
GET /user/sso/thbwiki/authorize
  → 302 https://thwiki.cc/wiki/Special:OAuth/authorize?...

GET /user/sso/thbwiki/callback?code=
  → POST thwiki.cc/wiki/Special:OAuth/access_token → {access_token, id_token}
  → 解码 id_token JWT（验签算法取决于 THBWiki OAuth2 扩展配置：
      若为 HMAC-SHA256，用 THBWIKI_CLIENT_SECRET；
      若为 RS256，需从 THBWiki JWKS 端点取公钥；
      实现时先尝试 HS256，失败则 fallback RS256）
    payload: {"sub": "用户ID", "username": "...", "email": "..."}
  → 存 sso-session:{sid} = {"thbwiki_uid": sub}
  → 返回 {"sid": "..."}
```

**PatchyVideo**：`patchyvideo: bool = False`，保持 stub，不新增端点。

### 8.5 新增端点（共 6 个）

| 端点 | 说明 |
|---|---|
| `GET /user/sso/qq/authorize` | 构造 QQ 授权 URL，302 跳转 |
| `GET /user/sso/qq/callback` | 换 token → openid → 存 session → 返回 `{"sid":"..."}` |
| `GET /user/sso/thbwiki/authorize` | 构造 THBWiki 授权 URL，302 跳转 |
| `GET /user/sso/thbwiki/callback` | 换 token → 解 JWT → 存 session → 返回 `{"sid":"..."}` |
| `POST /user/sso/qq/bind` | 已登录用户绑定 QQ（直接传 code，换 openid 后写入 user 行） |
| `POST /user/sso/thbwiki/bind` | 已登录用户绑定 THBWiki |

### 8.6 现有登录端点修改

`LoginEmailRequest`、`LoginPhoneRequest`、`LoginEmailPasswordRequest` 请求体加：

```python
sid: Optional[str] = None
```

`UserService` 登录/注册成功后，若 `sid` 不为 `None`：
1. `consume_sso_session(redis, sid)` 取出 SSO 数据（同时删除 session）
2. 对 `thbwiki_uid` / `qq_openid`：仅在 user 行对应列当前为 `NULL` 时写入（已绑定则跳过，不报错）
3. 调 `user_dao.save(user)`

### 8.7 VoterFE 更新

```python
thbwiki:     bool = Field(default=False)  # = bool(user.thbwiki_uid)
patchyvideo: bool = Field(default=False)  # 永远 False，stub
```

`from_user()` 工厂方法中：`thbwiki=bool(user.thbwiki_uid)`。

### 8.8 错误处理

| 场景 | 响应 |
|---|---|
| SSO 凭据未配置（`QQ_APP_ID` 为 None） | `503 SERVICE_UNAVAILABLE: SSO not configured` |
| OAuth code 无效 / 过期 | `400 INVALID_SSO_CODE` |
| sid 不存在 / 已消费 | `400 INVALID_OR_EXPIRED_SID` |
| 该 openid 已绑定其他账户 | `409 SSO_ID_ALREADY_BOUND` |
| 该 openid 已绑定当前账户（重复 bind） | `200`，幂等成功，不报错 |

### 8.9 测试

- 单元测试：`sso_session.py` 的 create / consume 逻辑（mock Redis）
- 集成测试：使用 mock HTTP 响应模拟 QQ / THBWiki API，覆盖 callback → session → login 全流程
- 契约测试：6 个端点可达性（无真实 OAuth 凭据时返回 503）

---

## 九、B-008：MongoDB → PostgreSQL 迁移脚本

### 文件位置

```
scripts/
  migrate_users_from_mongodb.py
```

### 依赖

`pyproject.toml` 新增 optional extra：

```toml
[project.optional-dependencies]
scripts = ["pymongo>=4.0"]
```

安装：`pip install -e ".[scripts]"`

### 字段映射

| MongoDB 字段 | PostgreSQL 字段 | 转换说明 |
|---|---|---|
| `_id`（ObjectId） | `id` | `str(objectid)`（24 位 hex） |
| `phone` | `phone_number` | 直接 |
| `phone_verified` | `phone_verified` | 直接 |
| `email` | `email` | 直接 |
| `email_verified` | `email_verified` | 直接 |
| `password_hashed` | `password_hash` | 直接（bcrypt 格式兼容） |
| `salt` | `legacy_salt` | 直接 |
| `created_at`（bson.DateTime） | `register_date` | `.as_datetime()` |
| `nickname` | `nickname` | 直接 |
| `signup_ip` | `register_ip_address` | `None → ""` |
| `qq_openid` | `qq_openid` | 直接（需 migration 0004 已执行） |
| `thbwiki_uid` | `thbwiki_uid` | 直接（需 migration 0004 已执行） |
| `pfp` | `pfp` | 直接 |
| `removed` | `removed` | `None → False` |

### 运行方式

```bash
MONGODB_URI=mongodb://... MONGODB_DB=thvote DATABASE_URL=postgresql+asyncpg://... \
  python scripts/migrate_users_from_mongodb.py [--batch-size 500] [--dry-run]
```

`--dry-run`：只读取 MongoDB，打印映射结果，不写 PostgreSQL。

### 幂等性

使用 `INSERT ... ON CONFLICT (id) DO NOTHING`。可多次执行，已存在的行不会被覆盖。

### 输出示例

```
[migrate] 读取 MongoDB thvote.voters ...
[migrate] 共 12483 条文档
[migrate] 批次 1/25 ... inserted=500 skipped=0 errors=0
...
[migrate] 完成：inserted=12341, skipped=140, errors=2
[migrate] 错误详情见 migrate_errors.jsonl
```

错误行写入 `migrate_errors.jsonl`（每行一个 JSON）供人工复查。

### 前置条件

1. `alembic upgrade head`（含 migration 0004）已执行
2. `pip install -e ".[scripts]"` 已安装 pymongo

---

## 十、实施顺序

```
1. B-017  文档（30 分钟）
2. B-029  文档（30 分钟）
3. B-025  删除 init_db（30 分钟）
4. B-018  _safe_log 计数器（1 小时）
5. B-030  Nacos 懒加载（1 小时）
6. B-027  flake8 先清违规，再改 CI（1-2 小时）
7. B-007  SSO（含 migration 0004，2-3 天）
8. B-008  迁移脚本（半天，依赖 B-007 的 migration 0004）
```

B-007 是唯一需要数据库 schema 变更的项目，其余均不改表结构。B-008 依赖 B-007 的 migration 0004 先执行完毕。
