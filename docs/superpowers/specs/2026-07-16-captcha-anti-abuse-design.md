# 注册防刷：人机验证（阿里云验证码 2.0）构思与调研

> 状态：**调研+构思完成，待拍板后实施**（2026-07-16）。
> 威胁模型：临时手机号批量收码注册刷票；纯 API 脚本注册（不走前端）；短信通道费用攻击。
> 结论先行：闸门设在**发验证码**动作上（GraphQL + REST 双入口，service 层强制），采用阿里云验证码 2.0，后端强制二次校验，默认 fail-closed，顺手补齐发码端点缺失的限流。

## 一、现状与缺口（代码勘探结论）

发码链路（手机为例）：`LoginBox.vue:209 getPhoneCode()` → GraphQL `requestPhoneCode(phone)`（resolvers/user.py:78）→ `UserService.send_sms_code()`（service.py:92）→ PNVS 客户端发短信。REST `POST /api/v1/user/send-sms-code` 走同一 service。改绑手机/邮箱（UserSettings.vue:332）复用同一对 mutation。

**"注册"发生在首次验证码登录时**：`login_with_phone_code`/`login_with_email_code` 对不存在用户自动 `_register_via_phone/email`（service.py:159-182/134-157）。因此锁住"发码"＝同时锁住批量注册与短信费用两个攻击面（登录必须消费验证码→验证码必须先过人机验证，保护是传递的）。

**缺口（本次勘探发现）**：
- ⚠️ 发码端点**当前无任何后端限流**——GraphQL `requestPhoneCode/requestEmailCode` 与 REST `send-sms-code/send-email-code` 都没挂 `rate_limit`。邮件仅有 per-邮箱 120s guard（email_code.py:67）；短信全靠阿里云 PNVS 侧频控兜底。脚本可直接烧短信费。
- 登录有 per-IP 5/60s（resolvers/user.py:107 等），账号变更有双层限流——只有发码是裸的。
- 无任何人机验证/风控集成。

## 二、产品调研摘要（阿里云验证码 2.0，2026-07-16 联网核实）

| 项 | 结论 |
|---|---|
| 产品现状 | 主推**验证码 2.0**；1.0（AFS/`awsc.js` 一脉）已于 **2026-06-10 彻底停服**，只能接 2.0 |
| 验证形态 | 无痕验证/一点即过/滑块/拼图/图像复原/**空间推理**（点选类，最接近"点红绿灯"）；难度由风险模型自适应，低风险无感通过 |
| 计费 | 按量：内地 **0.005 元/次**（海外节点 0.007）；**场景 3 个内免费**；无按次免费额度 |
| 前端接入 | 无 npm 包，**必须动态加载** `AliyunCaptcha.js`（CDN）；`initAliyunCaptcha({prefix, SceneId, region, mode})`；**popup 模式可绑定"发送验证码"按钮**；过验后回调给 **`captchaVerifyParam`**（不透明串）；JS 加载到发起验证建议 ≥2s（指纹采集） |
| 服务端校验 | `VerifyIntelligentCaptcha`；endpoint 二选一：`captcha.cn-shanghai.aliyuncs.com`（cn）/ `captcha.ap-southeast-1.aliyuncs.com`（sgp）；PyPI **`alibabacloud-captcha20230305`**（v1.1.4, 2025-10）；入参 `CaptchaVerifyParam`(+`SceneId`)；返回 `VerifyResult` bool + `VerifyCode`（T001 成功，F001-F025 失败，**F008=重放**） |
| 防绕过语义 | `captchaVerifyParam` **一次性+防重放**；但二次校验是**业务方自觉的架构约定**——我们后端必须无条件真调 `VerifyIntelligentCaptcha` 且只信 `VerifyResult`，否则形同虚设 |
| 降级建议 | **官方文档空白**（无 fail-open/closed 指引），需自定策略（见 §四） |
| 海外可用性 | JS 资源域名 `g.alicdn.com`/`ynuf.aliapp.org` 等，**海外加载体验无官方数据**——东方众有海外用户，需实测（行动项） |
| 备选 | Cloudflare Turnstile（免费/全球节点/无感）> GeeTest / 腾讯云验证码 / hCaptcha |

（详细来源链接见本次调研代理记录；关键条目均出自 help.aliyun.com 官方文档。）

## 三、方案构思

### 3.1 闸门位置与契约

- **service 层强制**：`UserService.send_sms_code / send_email_code` 增加 `captcha_verify_param: Optional[str]` 入参，进门先 `captcha_service.verify_or_raise(param, scene_id)`——GraphQL 与 REST 双入口自然同时收口，杜绝"REST 后门"。
- GraphQL：`requestPhoneCode(phone, captchaVerifyParam: String)` / `requestEmailCode(email, captchaVerifyParam: String)`——**新增可选参数**（SDL 向后兼容，加字段不破坏现有调用）；REST 请求体同样加可选字段。
- 开关 `ALIYUN_CAPTCHA_ENABLED`（Nacos）：off＝现行为（兼容期/应急降级）；on＝缺参→`CAPTCHA_REQUIRED`、校验失败→`CAPTCHA_FAILED`（新 error_kind + 中文 `human_readable_message`："请完成人机验证" / "人机验证未通过，请重试"），复用全局错误 extensions 兜底体系。
- **不必闸 login**：登录必须消费验证码（传递保护）；`loginEmailPassword` 爆破已有 5/60s per-IP + B-012 改密限流。改绑手机/邮箱走同一对 mutation，自动被覆盖。

### 3.2 后端组件（照 PNVS 模式）

- `src/common/aliyun/captcha_client.py`：`AliyunCaptchaClient(settings)`，lazy-init SDK、`_async_call` 线程池包同步 SDK、`@lru_cache(maxsize=1)` 工厂 `get_captcha_client()`。错误包装：校验不通过→`ValidationError("CAPTCHA_FAILED")`；SDK/网络异常→按 §3.4 降级策略处理。
- 配置（`Settings` 新增，Nacos dataId `thvote_be` 下发；**改配置需重启容器**，B-017）：
  `ALIYUN_CAPTCHA_ENABLED` / `ACCESS_KEY_ID` / `ACCESS_KEY_SECRET`（建议独立 RAM 用户）/ `ENDPOINT`（默认 cn-shanghai）/ `SCENE_ID_SEND_CODE` / `FAIL_MODE`（closed|open，默认 closed）。
- 供应商抽象**从轻**：不做 Provider 接口层，但 service 只依赖 `verify_or_raise(param)` 一个函数签名——将来若换 Turnstile，只换 client 实现与前端 widget，契约（一个不透明 param 字段）不变。

### 3.3 前端接入（Touhou-Vote，vote 包）

- `index.html`（或入口）按官方方式动态加载 `AliyunCaptcha.js` + 全局 `AliyunCaptchaConfig={region:'cn', prefix:'<身份标>'}`。
- `LoginBox.vue` / `UserSettings.vue`：popup 模式绑定"获取验证码"按钮，`captchaVerifyParam` 回调里携带该参数调用 `requestPhoneCode/requestEmailCode`。注意 ≥2s 指纹采集约束（页面加载即初始化，而非点击时才注入 JS）。

### 3.4 降级策略（官方空白，我方自定）

- **默认 fail-closed**：阿里云验证服务异常（超时/5xx）→ 拒绝发码，报"人机验证服务暂不可用，请稍后再试"。理由：投票公正性优先；且短信通道与验证码同属阿里云生态，大范围故障时发码多半也不可用。
- **人工降级通道**：Nacos 把 `ALIYUN_CAPTCHA_ENABLED=false`（或 `FAIL_MODE=open`）+ 重启容器。写入排障手册。
- 不做代码级自动 fail-open（自动放行＝给攻击者一个"打挂验证码就能刷"的激励）。

### 3.5 顺手补齐（与人机验证互补，独立小 PR 可先行）

- 发码端点 per-IP 限流：建议 10/60s（比登录宽，容忍公用出口 IP）。
- 短信 per-号码守卫：`sms-verify-guard-{phone}` 60s，对齐 email 的 120s guard 模式（不再单赖阿里云侧频控）。

## 四、成本估算（公式，按量付费）

`成本 ≈ 验证次数 × 0.005 元`。验证次数 ≈ 发码次数（每次发码一次验证）。即使按 10 万用户 × 平均 3 次发码 = 30 万次，也只有 **约 1500 元/届**；场景只需 1 个（`thvote_send_code`），免费额度内。结论：成本可忽略，无需包年包月。

## 五、实施排期草案（拍板后执行）

| 阶段 | 内容 | 估时 |
|---|---|---|
| M0（**需要你操作**） | 开通验证码 2.0 → 建场景（test 模式）拿 `SceneId`+`prefix` → 建 RAM 用户发 AK → 三样进 Nacos | 0.5h 人工 |
| M1 后端 | captcha client + service 闸门 + 配置 + 错误文案 + 单测/契约测试（SDL 加参）+ 发码限流补齐 | 0.5-1 天 |
| M2 前端 | LoginBox/UserSettings 接 widget（popup 绑按钮） | 0.5 天 |
| M3 联调 | 测试机全链路（test 场景）→ 境外网络实测 JS 加载 → 场景切 formal | 0.5 天 |

## 六、风险与待拍板

1. **海外用户体验未知**（文档空白）：M3 实测 `g.alicdn.com` 境外加载；若不可接受→ 备选 Cloudflare Turnstile（免费、全球、无感，架构上仅换 client+widget）。
2. **fail-closed 默认**是否认可（§3.4）。
3. **邮箱验证码是否同样强制**人机验证：建议是（临时邮箱比临时手机号更廉价），本设计默认双闸。
4. 场景数：先建 1 个 `send_code` 场景；若后续想对"登录"与"注册"区分风控（官方建议分场景），再加（3 个内免费）。
5. 验证码 2.0 无法自定义"点红绿灯"这类主题化点选；形态由风险模型自适应（低风险用户可能无感直过——这是特性不是缺陷，真人体验更好）。
