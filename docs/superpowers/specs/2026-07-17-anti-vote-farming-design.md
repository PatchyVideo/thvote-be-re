# 反刷票（一人多小号）：证据采集设计

> 状态：**Phase 0 已实现**（2026-07-17，B-044）。
> 威胁模型：一个人用大量小号（真手机号/接码平台 + 手动过 captcha）刷票。
> 核心思路：注册关抬高单号成本（captcha + 手机/邮件 + 限流），**投票关留可信证据**供事后聚类——数据要**现在就开始记**，投票期一开永远补不回来。

## 一、分层防御全景

| 关卡 | 手段 | 状态 |
|---|---|---|
| 注册/发码 | 人机验证（阿里云验证码 2.0，B-043） | ✅ 已上线 |
| 注册/发码 | 手机/邮件验证码 | ✅ 已有 |
| 注册/发码 | 发码端点 per-IP + per-号码限流 | ⏳ 待做（B-043 剩余项，依赖本文的 IP 可信修复） |
| 投票取证 | 可信 IP（注册 + 每票） | ✅ 本 PR 修复 |
| 投票取证 | 设备指纹（注册 + 每票） | ✅ 本 PR Phase 0 |
| 事后分析 | 管理端按 IP/设备聚类多账号 | ⏳ Phase 2（数据已在记录，随时可建） |

指纹与 IP 都**只作取证记录、绝不作实时拦截门**（客户端可控；且会误伤共用电脑/校园网/一家人）。判定刷票＝人工复核聚类结果。

## 二、本 PR（B-044）改了什么

### 2.1 设备指纹（Phase 0：localStorage UUID）
- 前端 `packages/vote/src/common/lib/deviceId.ts`：`crypto.randomUUID()` 存 localStorage，稳定持久；随**投票提交**和**登录（=注册）**上报。清缓存/无痕会重置——Phase 1 可升级 FingerprintJS（只换这个文件 + 值来源，契约不变）。
- 后端-投票：5 个 `*SubmitGQL` 加可选 `deviceId` → `_server_meta` 写进**已存在的** `raw_*.additional_fingreprint` 列（投票表无需迁移，字段是移植时就建好的）。
- 后端-注册：`loginPhone/loginEmail` 加可选 `deviceId` → `Meta.additional_fingureprint` → `_register_via_*` 存入 `user.register_device_id` 新列（migration 0011）。让"账号→设备"持久化在 user 表，而非只进会滚动、且和投票记录不同表的 `activity_log`。

### 2.2 可信客户端 IP（同一"证据可信"目标；也是限流的前置）
**修复前的三个洞**（勘探 2026-07-17）：① REST 提交口 IP 是 body 自报、可伪造；② `get_client_ip` 读 `X-Forwarded-For[0]`（最左＝客户端可塞假值）；③ `TRUSTED_PROXY_IPS` 未配 → 回退到"直接对端"＝**nginx 内网 IP**，所有请求记成同一个，IP 限流与聚类同时报废。

**修复**：
- `get_client_ip`：对端在 `trusted_proxy_ips`（**支持 CIDR**）内时，读 nginx 用 `$remote_addr` 覆盖写的 `X-Real-IP`（客户端改不了）；无该头则取 XFF **最右**一跳（nginx 追加的真实对端），绝不取最左。
- REST 提交 5 端点：`body.meta.user_ip = client_ip` 服务端强制覆盖。
- 需 Nacos 配 `TRUSTED_PROXY_IPS`（见 §四）。

### 2.3 现在能追溯到什么
一条投票记录：`vote_id`(=user.id) + `user_ip`(可信) + `created_at` + `additional_fingreprint`(设备 UUID)。
一个账号：`register_ip_address` + `register_device_id` + 注册时间 + 手机/邮箱 + SSO 绑定。
→ 具备了"按 IP 段 / 按设备 UUID 聚类多账号"的原始数据。

## 三、刻意的边界与局限（诚实记录）

- **设备 UUID 只挡懒人**：清 cookie / 无痕 / 换设备即重置。它抓的是"同一浏览器批量换号"，不是决定性证据。Phase 1 上 FingerprintJS 才跨无痕稳定。
- **IP 是弱信号**：运营商 NAT 让真实用户共享 IP（误伤），攻击者切 IP 零成本（漏抓）。IP 只作聚类提示。
- **只留最新一票**：`raw_*` 是 delete-then-insert，看不到改票轨迹/次数（时序也是刷票信号）。改 append-only 是更大的改动，本期不做，记为 follow-up。
- **不拦截**：本 PR 不基于指纹/IP 做任何拒绝，避免误伤真实用户 + 给攻击者"打挂某信号就放行"的激励。

## 四、部署：Nacos 配置

新增 dataId `thvote_be`：

```json
"TRUSTED_PROXY_IPS": "[\"172.16.0.0/12\"]"
```

- 值是 JSON 字符串数组，元素可为**具体 IP 或 CIDR 网段**。填 nginx 所在 docker 网段即可（`thvote-net` 是 `external:true`，子网由创建时定；私有网段整段信任最省事且抗容器 IP 变化——后端只被 nginx 私网访问或公网直连 :18000，私网来源必是 nginx，公网直连对端本就是真实客户端）。
- ⚠️ 改后需重启容器（B-017）。配好后 per-IP 证据与限流才有意义。

## 五、Follow-up

- **Phase 1**：deviceId.ts 升级 FingerprintJS `visitorId`（跨无痕更稳）。
- **Phase 2**：管理端"多账号聚类视图"（按 IP 段 / register_device_id 分组列可疑账号）。
- 发码端点 per-IP + per-号码限流（B-043 剩余项，依赖本 PR 的 IP 可信）。
- 评估投票记录改 append-only 以保留改票时序。
- 隐私：若正式上线，考虑在隐私说明披露"为防刷票记录设备特征/IP"。
