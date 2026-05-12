# Nacos 配置中心 + 服务注册接入说明

> 创建日期：2026-05-12
> 最后更新：2026-05-12
>
> 用途：说清楚 thvote-be-re 如何从 Nacos 加载配置、如何注册到 Nacos naming service，以及运维同学需要在 Nacos 控制台做哪些事。
> 关联代码：`src/common/nacos.py`（812 行）、`src/common/config.py`（顶层 `_load_nacos_sync()`）、`src/main.py`（lifespan 内的注册流程）

---

## 一、为什么是 Nacos

2026-05-12 之前用 Apollo，由于以下原因切换到 Nacos：

- 团队部署侧已有 Nacos 集群（共用其他服务的）
- Apollo 自带的 Java config / portal DB 维护成本高（仓库内曾保留 521 行 `apolloconfigdb.sql` + 464 行 `apolloportaldb.sql`，一并清除）
- Nacos 同时提供**配置中心 + 服务注册发现**，比 Apollo + 自建 service discovery 简单

> 切换 commit：`5414a0f feat: 添加Nacos配置中心支持` 及后续修复，合入 feat 分支在 2026-05-12。

---

## 二、配置加载链路

```
模块加载（import src.common.config）
  ↓
src/common/config.py:46  →  _load_nacos_sync()
  ↓
src/common/nacos.py:292  →  load_nacos_config()
  ↓
按顺序：
  1. 检查 NACOS_ENABLED=true（否则直接返回）
  2. 用 v2.nacos SDK 连接 NACOS_SERVER_ADDRS
  3. get_config(dataId=NACOS_DATA_ID, group=NACOS_GROUP)
  4. _parse_config_content(content) 解析 JSON / Properties / JS 风格 JSON
  5. _apply_config_to_env(config_dict) 写入 os.environ
     ⚠ 仅当 key 不在 os.environ 时才写（已设置的环境变量赢）
  6. 失败时回退：尝试读 <repo_root>/<NACOS_DATA_ID> 同名本地文件
  ↓
Settings()  →  Pydantic BaseSettings 从 os.environ 读取
```

### 2.1 关键设计点

- **环境变量优先于 Nacos**：CI 在 `.env` 写死的会赢 Nacos 配置项。这让本地 / CI 不依赖 Nacos 也能跑。
- **import-time 阻塞**：`_load_nacos_sync` 在模块加载期同步等待 Nacos 响应。Nacos 不可达时 import 链全挂 → 见 BACKLOG **B-030**。
- **本地文件 fallback**：Nacos 拿不到时尝试读 `<repo_root>/<NACOS_DATA_ID>` 文件（即同名于 dataId 的文本文件）。便于本地开发与 Nacos 故障应急。

---

## 三、环境变量清单

| 变量 | 默认 | 说明 |
|---|---|---|
| `NACOS_ENABLED` | `false` | 主开关；`true`/`1`/`yes`/`on` 才生效 |
| `NACOS_SERVER_ADDRS` | `http://localhost:8848` | Nacos 集群地址，多个用逗号分隔 |
| `NACOS_NAMESPACE` | `""` | Nacos 命名空间 ID（不是名字）。空字符串表示 public |
| `NACOS_GROUP` | `DEFAULT_GROUP` | 配置 group |
| `NACOS_DATA_ID` | `thvote-be` | 配置 dataId |
| `NACOS_ACCESS_KEY` / `NACOS_SECRET_KEY` | `None` | 阿里云 MSE Nacos 鉴权用 |
| `NACOS_USERNAME` / `NACOS_PASSWORD` | `None` | 自建 Nacos 鉴权用 |
| `NACOS_SERVICE_NAME` | `thvote-be` | 注册到 naming service 的服务名 |
| `NACOS_SERVICE_IP` | `0.0.0.0` | 注册时上报的 IP（一般用部署机内网 IP） |
| `NACOS_SERVICE_PORT` | `8000` | 服务端口 |
| `NACOS_SERVICE_CLUSTER` | `DEFAULT` | 集群名 |
| `NACOS_SERVICE_WEIGHT` | `1.0` | 负载权重 |

> ⚠️ `NACOS_USERNAME` / `NACOS_PASSWORD` 在 Settings 类里**没有定义**——只在 `load_nacos_config()` 内直接读 env。这是历史不一致，未来可以补到 Settings 里。

---

## 四、控制台上要做什么

### 4.1 创建命名空间

Nacos 控制台 → 命名空间 → 新建：
- 命名空间名：`thvote-test` / `thvote-prod`
- 命名空间 ID：**记下来**，要填到 `NACOS_NAMESPACE`（不是名字）

> ℹ️ 如果只有一个环境，可以直接用 public 命名空间，`NACOS_NAMESPACE` 留空。

### 4.2 创建配置项

Nacos 控制台 → 配置管理 → 配置列表 → "+"：
- Data ID：`thvote-be`（与 `NACOS_DATA_ID` 默认一致）
- Group：`DEFAULT_GROUP`
- 配置格式：**JSON**（推荐）或 Properties
- 配置内容样例：

```json
{
  "ALIYUN_PNVS_ACCESS_KEY_ID": "LTAI...",
  "ALIYUN_PNVS_ACCESS_KEY_SECRET": "...",
  "ALIYUN_PNVS_ENDPOINT": "dypnsapi.aliyuncs.com",
  "ALIYUN_PNVS_REGION_ID": "cn-hangzhou",
  "ALIYUN_PNVS_SCHEME_NAME": "thvote-sms-verify",
  "ALIYUN_PNVS_SMS_SIGN_NAME": "...",
  "ALIYUN_PNVS_SMS_TEMPLATE_CODE": "SMS_xxxxxxxx",
  "ALIYUN_PNVS_CODE_LENGTH": "6",
  "ALIYUN_PNVS_VALID_TIME": "300",
  "ALIYUN_PNVS_INTERVAL": "120",
  "ALIYUN_DM_ACCOUNT_NAME": "noreply@thvote.example.com",
  "ALIYUN_DM_FROM_ALIAS": "THVote",
  "ALIYUN_DM_SMTP_HOST": "smtpdm.aliyun.com",
  "ALIYUN_DM_SMTP_PORT": "465",
  "ALIYUN_DM_SMTP_USERNAME": "noreply@thvote.example.com",
  "ALIYUN_DM_SMTP_PASSWORD": "..."
}
```

> ⚠️ 所有 value 都用字符串（外层带引号）。Pydantic Settings 后续会按字段类型转换。

### 4.3 鉴权

阿里云 MSE Nacos：在 RAM 控制台开 AccessKey 然后填 `NACOS_ACCESS_KEY` / `NACOS_SECRET_KEY`。
自建 Nacos：用 `NACOS_USERNAME` / `NACOS_PASSWORD`（注：这两个变量未进 Settings 类，见 §三脚注）。

---

## 五、服务注册

`src/main.py` lifespan 里 `NACOS_ENABLED=true` 时会：

1. `start_nacos_watcher(on_change=...)` 启动配置 long-poll 监听器
2. `register_service_to_nacos(...)` 把自身注册到 naming service
3. 关停时（lifespan exit）应调 `deregister_service_from_nacos` 注销（**当前未在 lifespan 里调用**，是 follow-up）

`/admin/discover/{service_name}` 与 `/admin/discover-self` 两个 admin 端点可用于排障，看 Nacos 里有哪些活实例。

---

## 六、热更新限制

`start_nacos_watcher` 注册了配置变更回调，能把新值写回 `os.environ`。**但**：

- `Settings()` 是 `lru_cache` 单例，已实例化的字段不会重新读 env
- `get_pnvs_client` / `get_dm_smtp_client` / `get_email_code_service` / `get_sms_code_service` 也都是 `lru_cache(maxsize=1)`，已构造的客户端不会重建

含义：**改 Nacos 配置后必须重启容器**才能生效；热更新当前只对**没有被缓存的代码路径**有效。

→ 这是 BACKLOG **B-017** 的 root cause（继承自 Apollo 时代，切到 Nacos 没解决）。

---

## 七、本地开发不接 Nacos

```bash
export NACOS_ENABLED=false   # 默认就是 false
uvicorn src.main:app --reload
```

或者放本地配置文件：在 `<repo_root>/thvote-be` 写一个 properties 或 JSON 文件，`NACOS_ENABLED=true` 但 server 不通时会自动回退到这个文件。

---

## 八、Follow-up

- **B-017** Nacos + `lru_cache` 热更新不生效 → 文档化或给客户端加 `reload()`
- **B-030** import-time 阻塞加载 → 改 lazy + 超时熔断
- **B-031** `_parse_config_content` 的 JS 风格 JSON 容错解析是隐式技术债 → 约束上游配置写标准 JSON 后删除容错分支
- lifespan exit 时没调 `deregister_service_from_nacos`，K8s 滚动更新期会有短暂的"已下线但仍在 naming list"
- `NACOS_USERNAME` / `NACOS_PASSWORD` 没进 Settings 类
