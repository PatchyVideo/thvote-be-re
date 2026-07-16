# 阿里云验证码 2.0 接入手册（人机验证 / B-043）

> 创建日期：2026-07-17
> 用途：从零到上线接入"发验证码前人机验证"的**傻瓜式操作清单**——照着点、照着填即可。
> 姊妹篇：短信/邮件接入见 `aliyun-onboarding.md`；配置下发机制见 `nacos-config-center.md`；设计依据见 `../superpowers/specs/2026-07-16-captcha-anti-abuse-design.md`。
> ⚠️ 本手册假设**先用个人阿里云账户接入、上线前切换公家账户**——切换步骤见 §六，接入时请把 §六 要求"记录在案"的东西都记下来。

---

## 总览

```
你要在阿里云控制台做的事:  开通服务 → 建场景(拿 SceneId + prefix) → RAM 子账号发 AK
你要在 Nacos 填的东西:     ALIYUN_CAPTCHA_* 六个键 → 重启后端容器
前端要拿到的东西:          prefix + SceneId(前端初始化 AliyunCaptcha.js 用)
后端代码:                  已就绪(ALIYUN_CAPTCHA_ENABLED=false 时零行为变化)
```

计费提醒：按量 0.005 元/次、场景 3 个内免费，我们的量级下**成本可忽略**，不用买资源包。

## 一、开通服务

1. 登录阿里云控制台 → 搜索"**验证码 2.0**"（或直达 `https://yundun.console.aliyun.com/?p=captcha`）。
2. 点"立即开通/立即购买"，选**按量付费**。开通免费，不用预付。
3. ⚠️ 别开成旧版"人机验证(1.0)"——它已于 2026-06-10 停服，控制台如果还有入口也不要碰。

## 二、创建验证场景（拿 SceneId 和 prefix）

1. 验证码 2.0 控制台 → **场景管理** → 新建场景。
   - 场景名：`thvote_send_code`（发验证码专用）
   - 验证方式：建议选**无痕验证**（低风险用户无感通过，高风险自动升级滑块/拼图；体验最好）
   - 端类型：Web/H5
2. 保存后记下 **SceneId**（形如 `1cxxxxxx`）。
3. 到控制台"**概览**"页记下 **prefix**（"身份标"，账户级别，形如 `1cabcd`）。
4. 场景先保持 **test（测试）模式**——test 模式跳过风控只测链路，联调通了再切 **formal（正式）**。

> SceneId 给前端初始化和后端校验共用；prefix 只有前端用。**这两个值 + 下一步的 AK 都和账户绑定**，换账户全部要重新生成（见 §六）。

## 三、RAM 子账号发 AK（别用主账号 AK）

1. RAM 控制台 → 用户 → 创建用户 `thvote-captcha`（仅"OpenAPI 调用访问"）。
2. 授权：搜索 CAPTCHA 相关系统策略（形如 `AliyunYundunCAPTCHAFullAccess`；若控制台策略名不同，以能调用 `VerifyIntelligentCaptcha` 为准，最小化可自建自定义策略只含该 Action）。
3. 创建 AccessKey，记下 **AccessKey ID / Secret**（Secret 只显示一次）。

## 四、把配置注入 Nacos

测试环境：R-NACOS 控制台 `http://154.37.215.62:10848/rnacos/`，命名空间 ID `dfacd6e1-b442-476c-bffe-ff5504651c39`，**dataId `thvote_be`（下划线！）**，Group `DEFAULT_GROUP`。在现有 JSON 里追加（值全部是字符串，外层带引号）：

```json
"ALIYUN_CAPTCHA_ENABLED": "true",
"ALIYUN_CAPTCHA_ACCESS_KEY_ID": "LTAI...",
"ALIYUN_CAPTCHA_ACCESS_KEY_SECRET": "...",
"ALIYUN_CAPTCHA_ENDPOINT": "captcha.cn-shanghai.aliyuncs.com",
"ALIYUN_CAPTCHA_SCENE_ID_SEND_CODE": "1cxxxxxx",
"ALIYUN_CAPTCHA_FAIL_MODE": "closed"
```

说明：
- `ENABLED` 是总闸：`false`（默认）＝完全不启用，行为与接入前一致——**可以先把其他五个键填好、最后再拨 true**。
- `FAIL_MODE`：`closed`（默认）＝阿里云验证服务异常时**拒绝发码**；`open`＝异常时放行。**只在确认阿里云大面积故障时才临时切 open**，切记事后改回。
- ⚠️ 改完 Nacos **必须重启后端容器**才生效（配置是启动时拉进环境变量的，B-017）：GitHub Actions 手动触发一次 `Test & Deploy Backend`（workflow_dispatch 会 `--force-recreate`），或在服务器 `docker restart thvote-backend`。

## 五、验证链路（smoke）

1. **闸门生效**（后端视角，ENABLED=true 后）：

```bash
# 不带 captchaVerifyParam,应报 CAPTCHA_REQUIRED("请完成人机验证")
curl -s -X POST http://154.37.215.62:18000/graphql -H 'content-type: application/json' \
  -d '{"query":"mutation{requestEmailCode(email:\"smoke@example.com\")}"}'
# 带假参数,应报 CAPTCHA_UNAVAILABLE 或 CAPTCHA_FAILED(说明后端真的去问了阿里云)
curl -s -X POST http://154.37.215.62:18000/graphql -H 'content-type: application/json' \
  -d '{"query":"mutation{requestEmailCode(email:\"smoke@example.com\",captchaVerifyParam:\"fake\")}"}'
```

2. **真人链路**（前端接好 widget 后）：测试页点"获取验证码" → 弹出/无感通过验证 → 收到验证码。控制台"数据统计"里应能看到验证请求。
3. **反向验证（必须）**：把 Nacos 里 `ENABLED` 改回 `false` + 重启，确认旧行为恢复（不带参数也能发码）——这是应急降级通道，要演练过才算数。

## 六、⚠️ 个人账户 → 公家账户切换清单（上线前必做）

**和账户绑定、切换时全部作废重来的东西**（接入时就记录在案）：

| 项 | 在哪 | 切换动作 |
|---|---|---|
| 服务开通 | 公家账户控制台 | 重新开通验证码 2.0（§一） |
| 场景 + SceneId | 场景管理 | 重建场景，**SceneId 会变** |
| prefix（身份标） | 概览页 | **prefix 会变**（账户级） |
| RAM 用户 + AK | RAM 控制台 | 重建 `thvote-captcha` + 新 AK（§三） |

**切换执行顺序**（缺一步就是全站发不出验证码）：

1. 公家账户走一遍 §一~§三，拿到新 SceneId / prefix / AK（新场景先 test 模式）。
2. **前端**：替换初始化里的 `prefix` 和 `SceneId`（位置见前端接入 plan；两个值都在前端代码/配置里），发版。
3. **后端**：Nacos 更新 `ACCESS_KEY_ID/SECRET/SCENE_ID_SEND_CODE` 三个键 → 重启容器。
4. 跑一遍 §五 smoke（1、2、3 全做）。
5. 新场景切 formal；个人账户的场景删除、RAM AK **禁用并删除**（避免个人账户继续计费/泄露风险）。

> 前后端的 SceneId 必须是**同一个场景**;前端 prefix 与后端 AK 必须是**同一个账户**——混用新旧账户的任意组合都会校验失败（阿里云侧对不上）。

## 七、常见坑速查

| 症状 | 原因 | 处理 |
|---|---|---|
| 前端 widget 一直"加载中" | `g.alicdn.com`/`ynuf.aliapp.org` 等域名被网络环境拦 | 检查网络/白名单；海外用户报告集中出现时评估备选（Turnstile，见设计稿 §六） |
| 后端报 `ALIYUN_NOT_CONFIGURED` | ENABLED=true 但 AK/endpoint 没填全 | 补齐 §四 六个键并重启 |
| 后端报 `CAPTCHA_UNAVAILABLE`（持续） | AK 无权限 / SceneId 不存在 / endpoint 写错 | 查 RAM 授权与 SceneId;确认 endpoint 为 `captcha.cn-shanghai.aliyuncs.com` |
| 校验总失败 `F008` | `captchaVerifyParam` 被重复提交（一次性参数） | 前端每次发码都要重新完成验证,不能缓存参数 |
| 真人频繁被要求滑块 | 场景还在 test 模式或风控判定风险高 | 确认已切 formal;必要时开自定义策略（30 元/天,慎用） |
| 改了 Nacos 没生效 | 配置只在启动时加载（B-017） | 重启容器 |

## 八、相关代码位置

| 层 | 位置 |
|---|---|
| 配置声明 | `src/common/config.py` `aliyun_captcha_*` 字段 |
| 阿里云客户端 | `src/common/aliyun/captcha_client.py`（`VerifyIntelligentCaptcha` 封装） |
| 闸门逻辑 | `src/common/verification/captcha.py`（`CaptchaService.verify_or_raise`,行为矩阵见其 docstring） |
| 接入点 | `src/apps/user/service.py` `send_sms_code`/`send_email_code` 首行（GraphQL/REST 双入口共用） |
| GraphQL 契约 | `requestPhoneCode/requestEmailCode` 可选参数 `captchaVerifyParam`（契约测试 `tests/contract/test_captcha_contract.py`） |
| 错误文案 | `src/api/graphql/errors.py`（CAPTCHA_REQUIRED / CAPTCHA_FAILED / CAPTCHA_UNAVAILABLE） |
