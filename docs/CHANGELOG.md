# thvote-be-re CHANGELOG

> 仓库级变更记录，按 CLAUDE.md §4 维护。日期格式 `YYYY-MM-DD`。
>
> 创建日期：2026-04-27

> 最后更新：2026-07-17（管理端 UI↔API 对齐:修 5 处子页面/按钮/字段/结果显示错位）

## [2026-07-17] 管理端面板 UI↔API 对齐修复

> 全量审计现有 admin panel(`src/admin_ui/index.html`)各子页面/按钮 vs 后端端点契约,修复实测发现的 3 个真 bug + 2 个显示/健壮性缺陷。为 Vue 重写(Plan 2)前先把现有面板的功能/字段/结果显示对齐。

### Fixed
- **候选项编辑不再破坏合并状态**:`candidate_field_specs` 排除内部列 `merged_into`(合并链,只应由 merge/unmerge 端点改)。此前它被当可编辑文本字段渲染,`saveEdit` 每次保存都回发 `merged_into=""` → 空串写入 Integer 列 500,或悄悄清掉候选的合并链;且 `saveEdit` 只处理 409/404,其他状态(含 500)仍提示"已保存"。同时给 `saveEdit` 加 `!r.ok` 判错。
- **问卷题/选项编辑不再把 `order` 重置为 0**:`assembler.py` 的 `_question_out`/`_option_out` 现在输出 `order`(此前只有 `_group_out` 带)。编辑弹窗读 `qu.order||0`/`o.order||0` 恒为 0,保存又回发 → 静默打乱展示顺序。
- **"Reload Config" 按钮不再 404**:该端点挂在裸 `/admin/reload-config`(非 `/api/v1`),前端 `quickAction` 经 `api()` 误加 `/api/v1` 前缀 → 404。改为直连裸路径并带 `X-Admin-Secret`;三个 quick action 一并加 `!r.ok` 判错。
- **问卷列表卡片"问题"数不再恒为 0**:`list_questionnaires` 现返回 `question_count`(题→组→问卷计数),卡片改读它。
- **审计日志 `since` 传非法格式返回 400** `INVALID_SINCE_FORMAT`(此前 `datetime.fromisoformat` 无 try/except → 500)。

### 兼容性
- assembler 结构输出**新增 `order` 键**(问题/选项层):附加字段,向后兼容(结构本就按 order 排序);问卷列表项新增 `question_count`。二者均只增不改。
- 纯后端 + 管理端静态页,无 schema/迁移/GraphQL SDL 变更。测试 +4,全量 411 passed。

## [2026-07-17] B-042 收口 admin ops 端点鉴权

> B-049 的 `require_admin` 只覆盖到 `/api/v1/admin/*` 两个路由;`main.py` 上还有三个裸 `/admin/*` ops 端点未纳入闸门。本次补齐。

### Security
- `main.py` 的 `POST /admin/reload-config`、`GET /admin/discover/{service_name}`、`GET /admin/discover-self` 三个 ops 端点加 `dependencies=[Depends(require_admin)]`——此前**零鉴权**,`reload-config` 还会回显 DB host/port/name(信息泄露)。勘察确认这三个端点无内部/自动调用方(CI、健康检查、服务注册均不调),唯一调用方是携带 `X-Admin-Secret` 的 admin UI,故加闸门不影响运维。
- 测试 +6(`tests/integration/test_admin_auth.py`:三端点 × 无 secret/错 secret 各 403;require_admin 在 handler 前短路,不触发真实 reload/Nacos 调用)。全量 407 passed。

### 兼容性 / 部署
- 需 `ADMIN_SECRET` 已配(B-049 已在 Nacos 配好)。调这三个端点现在必须带 `X-Admin-Secret` 头。
- 纯后端,无 schema/迁移变更。B-042 的 admin 鉴权项就此关闭;仅剩 scraper Pixiv 凭据待配。

## [2026-07-17] B-049 安全监控管理端 API + 处置动作（record-only）

> 承接 B-044~B-048 各反刷票取证信号(IP/设备指纹、`fill_duration_ms`、`client_env`、作弊评分)，本次落地一套只读监控视图 + 可逆的人工处置端点，挂在既有 fail-closed 的 `require_admin` 闸门下(见上一条目)。只读 `raw_*`(路径 A)，`raw_work`(废弃路径 B)不纳入。

### Added
- migration `0014`：`raw_character/music/cp/paper/dojin` 各表加 `invalidated`(bool，默认 `false`，管理端软作废标记)+ 若干监控查询索引；新表 `voter_review`(`user_id` 主键，`status`/`note`/`updated_at`，人工复核记录)。
- `src/apps/admin/monitor/`：新的监控子模块，挂在 `/api/v1/admin/monitor`，与 `router.py` 一样受 `require_admin` 统一闸门保护。
  - `GET /overview`：各类别投票总数、去重 IP/设备数、按日提交量。
  - `GET /groups`、`GET /groups/{kind}/{key}/members`：IP/设备聚类(同一 IP 或设备关联的多账号)及成员列表。
  - `GET /suspects`：固定权重可疑打分(首投过快、无 `client_env`、UA 疑似脚本、注册到首投间隔过短、所在 IP/设备组过大)，分页返回、候选集封顶避免全量算分。
  - `GET /votes`：单类别投票浏览器，支持按 `vote_id`/`user_ip`/`device`/`invalidated` 过滤 + 分页。
  - `GET /account/{vote_id}`：单账号钻取，聚合其在 5 个类别下的全部提交 + 已有复核记录 + 关联的 IP/设备组。
  - `PATCH /vote/{category}/{row_id}/invalidate`、`.../restore`：切换单条投票记录的 `invalidated` 标记，行不存在返回 404。
  - `PATCH /account/{vote_id}/review`：人工复核状态 upsert(`status`/`note`，每账号一行，覆盖式更新)。
- `tests/integration/test_admin_monitor.py`：15 个用例，覆盖聚类/分页/评分/HTTP 鉴权 + 本次新增的处置动作(作废→列表可见→恢复；作废不存在的行 404；复核 upsert 覆盖并反映到账号详情)。

### Record-only 边界（重要）
- `invalidate`/`restore`/`review` **只写标记或行数据，不做任何排名重算**——排名仍完全由现有(未改动的)计票逻辑产出。响应 `detail` 明确写"已记录；影响排名需 B-050 计票重写落地后生效"，前端据此提示管理员"已记录，暂不影响当前排名"。
- 这是刻意的阶段边界：B-050(计票重写)落地前，本控制台只做"取证 + 记录"，不接入排名计算，避免在旧计票逻辑上叠加新的隐式规则。

### 兼容性 / 部署
- 新增数据库表/列需要 `alembic upgrade head`(migration `0014`)才能使用；未跑迁移时相关端点会因列/表缺失报错。
- 无破坏性变更：新增端点均为新路径，不影响既有 `/api/v1/admin/*` 端点语义。

## [2026-07-17] B-049 管理端鉴权 fail-closed + IP 白名单

> Review 发现 `src/apps/questionnaire/admin_router.py` 有独立 `/admin` 路由,仍用旧的 fail-open `_check_admin_secret`(未配 `admin_secret` 时直接放行)——与 `src/apps/admin/router.py` 已切换的 fail-closed `require_admin` 不是同一套闸门,形成一个未闭合的开放口子。本次把它补齐。

### Changed
- `_check_admin_secret` 由 fail-open 改 fail-closed(未配 `admin_secret` 一律 403);`require_admin` 统一闸门(secret + IP 白名单)应用于 `src/apps/admin/router.py` 与 `src/apps/questionnaire/admin_router.py` 两个 `/admin` 路由。
- `require_admin`(以及两处 `_check_admin_secret`)的 secret 比较改用 `secrets.compare_digest` 常量时间比较,避免逐字节比较的响应耗时差被用于旁路猜测 secret。

### Security
- 新配置 `ADMIN_ALLOWED_IPS`(Nacos JSON 数组字符串,空 = 不限 IP;非空时客户端 IP 须精确匹配或落入某个 CIDR 才放行,否则 403)。
- 新增 `tests/integration/test_admin_auth.py`:对 `require_admin` 的 fail-closed 行为做 HTTP 级回归覆盖(未配 secret 403、错 secret 403、IP 不在白名单 403、空白名单 + 正确 secret 放行)。
- `tests/contract/test_result_endpoints.py` 删除了一个本地 `admin_secret` fixture——它不还原 `ADMIN_SECRET` 环境变量,会污染同进程内后续测试;改用 `tests/contract/conftest.py` 里已有的、会正确还原环境的同名 fixture。

### 兼容性 / 部署
- **部署警告(重要)**:上线前必须在 Nacos 配好 `ADMIN_SECRET`,否则**所有 `/api/v1/admin/*` 端点将 403**(测试机此前 `ADMIN_SECRET` 未配 = 裸奔,部署本改动前务必先配)。
- 遗留:`main.py` 的 `/admin/reload-config`、`/admin/discover*` 三个 ops 端点仍未纳入闸门(需先分析内部调用方),B-042 部分保留。

## [2026-07-17] 删除死代码：vote_data 模块（路径 B 空壳）

> 勘探(2026-07-17)发现投票有两套并行存储:**路径 A** `raw_*`(前端 GraphQL 提交的真实落库,提交/回读/CSV/统计全走这)与**路径 B** `character/music/cp/questionnaire`(由 `vote_data` 模块写,但**无任何调用方**、测试库 0 行、旧 Rust 侧本就是空壳 `fn main(){}`、项目文档 2026-05-12 已标"遗留不再写入")。二者**从未接线**。

### Removed
- 删除整个 `src/apps/vote_data/`(service/dao/router/models/schemas)——路径 B 的唯一写入方,其 REST `/api/v1/vote-data/*` 端点无任何调用者。
- `src/api/rest/v1/__init__.py`:注销 `vote_data_router`。
- `tests/integration/test_vote_data.py` 删除。

### Fixed
- `AdminService.get_user_detail` 的"投票状态"改读**真实提交表 raw_***(`SubmitDAO.has_submit`),此前读死表 Path B 永远显示"未投",不准。

### 遗留（转 B-050 大重写）
- `db_model/character.py`/`music.py`/`cp.py`/`questionnaire.py` 四个模型现只剩 `compute_dao` 在读——它们是 B-050 计票重写的对象,本次不动。
> 最后更新：2026-07-17（B-048 拦脚本:Origin/Referer 校验）

## [2026-07-17] B-048 拦脚本：服务端 Origin/Referer 校验（默认关）

> 让变更请求尽量来自真人浏览器,拦掉裸脚本(curl/python 直连)。设计见 `docs/superpowers/specs/2026-07-17-block-scripts-design.md`。

### Added / Security
- `BrowserOriginGuardMiddleware`(`src/common/middleware/origin_guard.py`):对**变更类请求**要求带浏览器自动附加的 `Origin`/`Referer`,不带→403(`FORBIDDEN_ORIGIN`)。范围:`POST /graphql` 且 body 含 `mutation`(正则 `\bmutation\b`,**不匹配 introspection 的 `mutationType`**→前端 codegen 不受影响)、REST 提交/发码/登录端点。`CORS_ALLOWED_ORIGINS` 配了具体域名时还需 host 匹配。
- 开关 `REQUIRE_BROWSER_ORIGIN`(Nacos,默认 **false**),安全灰度;改后重启容器(B-017)。
- 测试 +6,含钉死 BaseHTTPMiddleware 读 body 后能回放给下游 GraphQL(带 Origin 的 mutation 真的执行)。

### 兼容性 / 局限
- **默认关,零行为变化**。CORS 拦不住脚本(浏览器端执行),故本项在服务端主动校验。
- 少数隐私插件剥离 Referer/Origin 的用户,开启后投票会被拦——故可随时关。伪造头能过(刻意接受,成本已抬高)。
- **端口收口(`:18000` 直连)列为后续项**:前端 codegen 直连 :18000 拉 schema,直接关端口会断前端 CI,收口前须先把 codegen 改走 nginx 代理。

## [2026-07-17] B-046 UA + 浏览器环境指纹（每票取证）

## [2026-07-17] B-046 User-Agent + 浏览器环境指纹（每票取证）

> 每票记录客户端环境指纹作反刷票特征。只取证不拦截。前端在 Touhou-Vote `4b89a23`。

### Added
- `raw_*.client_env`(新列 **migration 0013**,6 张表,单个 JSON 列):`{ua, tz, screen, lang}`。
  - `ua` 服务端在 `_server_meta` 从请求头取(连纯 API 机器人也跑不掉:headless/`python-requests`/缺 UA 皆信号)。
  - `tz/screen/lang` 前端 `clientEnv.ts` 采集、以 JSON 字符串上报;服务端**只白名单取这三键、值截断、限总长**(不做 PII grab-bag)。浏览器时区 vs IP 地理不符=经典代理信号。
  - 单个 JSON 列,以后加环境信号无需改表。
- 5 个 `*SubmitGQL` 加可选 `clientEnv`(SDL 向后兼容);sync mapper 透传(历史 NULL)。测试 +7。

### 兼容性 / 部署
- 需 `alembic upgrade head`(**0013**,依赖 0012;`ADD COLUMN IF NOT EXISTS`,幂等)。**本 PR 叠在 B-045(#11)之上,须先合 #11**。
- 只取证、不拦截。

## [2026-07-17] B-045 提交耗时 + 服务端改票计数（反机器人时序特征）

## [2026-07-17] B-045 提交耗时 + 服务端改票计数（反机器人时序特征）

> 记录投票/问卷填写耗时作为反机器人特征(瞎点耗时≈0),**不误伤改票的人**。只取证不拦截。设计见 `docs/superpowers/specs/2026-07-17-submit-timing-signal-design.md`;前端在 Touhou-Vote `f59585a`。

### Added
- `raw_*.fill_duration_ms`(新列,**migration 0012** 覆盖 6 张 raw_* 表):客户端上报的"页面挂载→提交"墙钟毫秒数。5 个 `*SubmitGQL` 加可选 `fillDurationMs` → `_server_meta` → `SubmitMetadata` → 落库。前端 `fillTimer.ts` + 5 类投票/问卷埋点。机器人直接打 GraphQL 不跑前端 → 值为 null(本身即信号)。
  - **落库语义 = 首次提交耗时,改票时服务端保留不覆盖**(`_upsert` 逻辑)。防机器人"投一次快、再重提一次"洗掉首投证据(覆盖式提交会物理删掉 attempt=1 那行)。判据直接看这个保留值(快/为空=可疑),重提多少次改不了它;不再按 attempt 豁免。
- `attempt` 计数**改由服务端计算**(复用此前恒 NULL 的死列,无需迁移):`SubmitDAO._upsert`(5 个 create_* 收敛到它)覆盖写前 `MAX(attempt)+1`,首次=1、改票=2/3…,作辅助信息(改了几次)。
- 测试 +2(attempt 1→2→3、只留一行、fill_duration 落库)。

### 兼容性 / 部署
- SDL:5 个 submit input 各加**可选** `fillDurationMs`(向后兼容);契约测试同步更新。
- 需 `alembic upgrade head`(0012,`ADD COLUMN IF NOT EXISTS`,幂等)。
- 二者均**只取证、不拦截**。

## [2026-07-17] B-043 发码端点限流补齐

## [2026-07-17] B-043 发码端点限流（此前完全无限流）

### Added / Security
- `UserService.send_email_code/send_sms_code` 加两层限流（service 层单一收口,GraphQL `request*Code` + REST `send-*-code` 双入口一并覆盖）：
  - **per-IP 洪泛限流 30/60s**,放在 captcha **之前**——挡洪泛并保护每次验证码校验对阿里云的付费调用(0.005 元/次)。额度取宽松值:captcha 已逐次拦每次发码,per-IP 只作洪泛/成本兜底;共用出口 IP(校园/小区 NAT)一分钟内可能几十真实用户同时注册,30/60s 给足余量避免误伤。依赖 X-Real-IP 可信(B-044)才有意义。
  - **per-号码重发间隔 1/60s(短信)**,放在 captcha **之后**——只对真正发出的码计数,避免过验证码前失败也占额度。邮箱沿用 EmailCodeService 既有 120s guard。
- `rate_limit` 的 `HTTPException(429)` 经 `map_app_errors`(GraphQL)/FastAPI(REST) 出 `REQUEST_TOO_FREQUENT`。测试 +4(限流顺序:IP 在 captcha 前、洪泛在 captcha/发送前被拦)。

### 兼容性
- 纯后端,无 schema/契约变更。撞线为 `REQUEST_TOO_FREQUENT` 软提示,60s 后可重试。

## [2026-07-17] B-044 反刷票证据采集:设备 UUID + 可信 IP

## [2026-07-17] B-044 反刷票证据采集：设备 UUID + 可信客户端 IP

> 目标:为"一人多小号"刷票留可事后聚类的可信证据(现在就记,投票期一开补不回来)。指纹与 IP **只取证不拦截**。设计见 `docs/superpowers/specs/2026-07-17-anti-vote-farming-design.md`。前端改动在 Touhou-Vote `4b9f4c5`。

### Added
- 设备指纹(Phase 0,localStorage UUID):5 个 `*SubmitGQL` 加可选 `deviceId` → `_server_meta` 写入已有的 `raw_*.additional_fingreprint` 列(投票表无需迁移);`loginPhone/loginEmail` 加可选 `deviceId` → `Meta` → 新列 `user.register_device_id`(**migration 0011**)。前端 `deviceId.ts` 生成/持久化 UUID,随投票与登录上报。
- 单测 +12(X-Real-IP/CIDR 解析)。

### Fixed / Security
- `get_client_ip`:对端为可信代理(`trusted_proxy_ips`,**支持 CIDR**)时读 nginx 覆盖写的、不可伪造的 `X-Real-IP`(旧实现读可伪造的 `X-Forwarded-For[0]`);无该头则取 XFF 最右一跳。修复"未配 `TRUSTED_PROXY_IPS` 时所有请求记成 nginx 内网 IP"→ 之前 IP 限流与聚类均失效。
- REST 提交 5 端点服务端强制覆盖 `meta.user_ip`(旧实现信客户端 body 自报,可伪造)。

### 兼容性 / 部署
- SDL:5 个 submit input 各加**可选** `deviceId`(向后兼容,老客户端不传);契约测试同步更新。
- 需 `alembic upgrade head`(0011,`ADD COLUMN IF NOT EXISTS`,幂等)。
- 需 Nacos 配 `TRUSTED_PROXY_IPS`(nginx 网段/私有网段,JSON 字符串数组,改后重启)——否则 IP 仍不可信。

## [2026-07-17] B-043 人机验证全链路上线:后端壳+前端 widget+配置

## [2026-07-17] B-043 人机验证前端接入 + 测试机全链路生效（Touhou-Vote 仓库改动,此处记录以便追溯）

### Added
- 前端（Touhou-Vote dev `30efc96`）:`packages/vote/src/common/lib/aliyunCaptcha.ts`（脚本预载+隐藏代理按钮弹出 popup 验证,`CAPTCHA_PREFIX`/`CAPTCHA_SCENE_ID` 常量集中于此,换账户改这里）;LoginBox/UserSettings 的"获取验证码"改为先过验证再发码,`captchaVerifyParam` 随 `request*Code` 提交;新增 CAPTCHA_* 错误的用户提示分支。
- 降级语义:用户关闭弹窗=静默中止;`AliyunCaptcha.js` 加载失败(如海外网络)=无参直发,由后端闸门裁决。

### 部署/验证（2026-07-17 实测）
- Nacos 六键已配（ENABLED=true,FAIL_MODE=closed,SceneId `8yhz5jet`）;后端(:18000)与前端(:8082)均已部署。
- smoke:无参发码→`CAPTCHA_REQUIRED`;伪造参数→`CAPTCHA_FAILED`（阿里云真实判定回包,证明 AK/SceneId/endpoint 全通）;部署产物 chunk 内确认集成存在。
- 真人浏览器验收通过（2026-07-17，Touhou-Vote `11a7630`）：点"获取"→弹出阿里云验证→过验→倒计时启动→收到短信,全链路正常。
- 修复（`11a7630`）：`verifyHuman` 的弹窗触发从 `setTimeout(0)` 改到 `getInstance` 回调后（+300ms 兜底）——原写法在 widget 异步绑定按钮监听前就程序化点击,点击落空导致 Promise 永久悬住（无弹窗/无报错/无倒计时）。
- 待办:发码端点限流（独立小 PR）、海外网络加载实测（B-043 剩余项）。

## [2026-07-17] B-043 人机验证后端壳（配置/客户端/闸门,默认关闭）

### Added
- `Settings` 新增 `ALIYUN_CAPTCHA_*` 六键（ENABLED/AK 对/ENDPOINT/SCENE_ID_SEND_CODE/FAIL_MODE,均 Nacos 下发,改后需重启,B-017）。
- `src/common/aliyun/captcha_client.py`:验证码 2.0 `VerifyIntelligentCaptcha` 封装（照 pnvs_client 模式:lazy SDK import、线程池异步、lru_cache 单例;API 级错误→`CAPTCHA_UNAVAILABLE`）。依赖新增 `alibabacloud-captcha20230305>=1.1.0`。
- `src/common/verification/captcha.py`:`CaptchaService.verify_or_raise` 闸门（行为矩阵:关闭=放行;缺参=`CAPTCHA_REQUIRED`;未过=`CAPTCHA_FAILED`+VerifyCode;服务异常按 `FAIL_MODE` closed(默认拒)/open(放行)）。
- 接入点:`UserService.send_sms_code/send_email_code` 首行调闸门——GraphQL 与 REST 双入口同时收口。
- GraphQL `requestPhoneCode/requestEmailCode` 新增**可选**参数 `captchaVerifyParam`(SDL 向后兼容,契约测试钉死可选性);REST `Send*CodeRequest` 加同名可选字段;错误文案表 +3(中文)。
- 测试 +12(闸门行为矩阵/响应解析/service 接线顺序/SDL 契约),全量 355 passed。
- `docs/operations/captcha-onboarding.md`:傻瓜式接入手册（开通→建场景→RAM AK→Nacos→smoke→**个人→公家账户切换清单**→坑速查）。

### 兼容性
- **`ALIYUN_CAPTCHA_ENABLED` 默认 false,零行为变化**;拨 true 前需按手册配齐 Nacos 六键并重启。
- SDL 变更(§8 报备):仅两个 mutation 各加一个可空参数,旧调用不受影响。

## [2026-07-16] B-043 注册防刷人机验证：调研与构思（docs）

### Added
- `docs/superpowers/specs/2026-07-16-captcha-anti-abuse-design.md`：阿里云验证码 2.0 联网调研（1.0 已于 2026-06-10 停服;计费 0.005 元/次;前端动态加载 `AliyunCaptcha.js` popup 绑定发码按钮;服务端 `VerifyIntelligentCaptcha` + PyPI `alibabacloud-captcha20230305`;`captchaVerifyParam` 一次性防重放）+ 方案构思（闸门设在发验证码,service 层双入口收口;`requestPhoneCode/EmailCode` 加可选参数,SDL 向后兼容;默认 fail-closed,Nacos 开关人工降级;成本约 0.005 元/次可忽略）。
- ⚠️ 勘探发现并记录：发码端点（GraphQL `request*Code` + REST `send-*-code`）**当前无任何后端限流**——列入 B-043 一并修复。

### 兼容性
- 纯文档,无代码变更。实施将新增 GraphQL 可选参数与 `ALIYUN_CAPTCHA_*` 配置组（届时另记）。

## [2026-07-14] 删除 GraphQL 旧 submit 死字段（refactor PR）

### Removed
- `resolvers/submit.py` 整文件:旧 `SubmitQuery`(7 字段:`getCharacterSubmit`/`getMusicSubmit`/`getCpSubmit`/`getPaperSubmit`/`getDojinSubmit`/`getVotingStatus`/`getVotingStatistics`,均 `voteId` 入参)与旧 `SubmitMutation`(5 字段:`submitCharacter`/`submitMusic`/`submitCp`/`submitPaper`(input:)及被 MRO 遮蔽的旧 `submitDojin`)。全部 resolver 因 `SubmitService(db)` 传参错误**运行时本就不可用**,且契约对账确认前端零调用(见 api-contract-audit-2026-07-14.md)。
- `types.py` 13 个随之成为孤儿的类型/转换器:`SubmitMetadata(Input)`、`*SubmitResult`×4、`VotingStatus`、`VotingStatistics`、`SubmitSuccess`、`*SubmitMutationInput`×5→其中 Dojin 系早已被 SDL 剪除、`DojinSubmitInput`、`pydantic_to_graphql_meta/voting_status/voting_statistics`。
- `tests/contract/test_graphql_login_contract.py` 中"旧 submit 字段仍在"的断言改为守护桥接字段 `submitCharacterVote`。

### 兼容性
- **SDL 变更**(§8 报备):11 个字段、13 个类型从 schema 消失;**桥接字段与其余契约零变化**(删除前后 SDL diff 验证:只减不增)。前端 codegen 下次运行后 `__generated__` 类型同步瘦身,因无 documents 校验且前端零调用,无破坏。
- 附带收益:关闭 `get*(voteId)` 无鉴权查任意人提交的历史暴露面(migration 文档 §4 遗留风险项)。
- REST 的 `/api/v1/voting-status/`、`/voting-statistics/`(pydantic 同名模型)不受影响。

## [2026-07-14] 前后端 API 契约对账（docs）

### Added
- `docs/migration/api-contract-audit-2026-07-14.md`：后端全量 API × 前端全量调用交叉对账。要点：vote 包 GraphQL 已全量在桥接层（零漂移）;**result 包 18 文件 21+ query 全在老 Rust 契约上**（Python 无 `query*Ranking` 等字段,测试机 :8084 已指向 Python → result 页全挂,为当前最大缺口）;旧 GraphQL submit 12 字段确认全坏但前端零调用（死代码,建议删）;本地静态数据→后端化对照表;修正两条旧判断（`/server-time` 前端并不调用、`search_cps` 恒空暂不影响前端）。

## [2026-07-14] nginx v12 路由部署（Touhou-Vote 仓库改动，此处记录以便追溯）

### Changed
- 测试机 :8082 vote 容器 nginx（`Touhou-Vote/Dockerfile.vote.template`,`c5c508f`+`cfba9cc`）：新增 `/v12-be/` 精确 location（vote-objects/questionnaire → `/api/v1/*`;`/v12-be/doujin/api` 精确匹配 → `/api/v1/scraper/scrape`;兜底 → 根路径），**保留 `/v11-be/` 过渡块**（移除条件：前端全量切 v12）。与原 plan 的两处刻意偏离及验收记录见 [nginx-routing-fix plan 实施记录](./superpowers/plans/2026-06-09-nginx-routing-fix.md)。

### 兼容性
- v11 前端不受影响（过渡块在）；前端可开始按 v12 API_PREFIX 切换。
- 发现项：测试环境 scraper 的 Pixiv 凭据未配（`Pixiv authentication failed`），二创提名联调前需补。

## [2026-07-14] B-032：删除 alembic auto-baseline shim

### Removed
- `alembic/env.py` 的 `_maybe_baseline_existing_schema` 与 `_SENTINELS`:该 shim 按"表是否存在"闷头 stamp、不校验列,会掩盖 schema 漂移(2026-05-31 测试库登录全挂的根因)。B-025 移除 init_db 后门后它已无存在必要,`alembic upgrade head` 现在对空库老实从 0001 跑全链。
- 连带移除 zfq 为 shim 打的"清残留事务"补丁(`connection.in_transaction()` 时 rollback):shim 没了,inspect() 不再先于 begin_transaction 执行,补丁失去存在理由,`do_run_migrations` 恢复标准 alembic 写法。

### 兼容性
- 已被 alembic 管理的库(测试机已 stamp 至 0010)不受影响,upgrade head 为 no-op。
- 若存在**从未被 alembic 管理**的祖传库(有 `user` 表但无 `alembic_version`),upgrade 将因 CREATE TABLE 冲突显式报错而非静默 stamp——这是刻意行为,此类库应清空重建。
- 空库全链路由 CI 每次 push 的迁移烟雾测试(空 PG 跑 `alembic upgrade head`)持续验证。5-31 事件的残留漂移核查(空库重建测试机)暂缓:待 B-026 CI `alembic check` 门禁或联调中发现异常时再做。

## [2026-07-14] 合并 zfq_dev：问卷结构化(B-039) + 投票对象后端(B-040) + 自由问卷管理(B-041) + BSON 离线导入

> 合并记录:代码作者 zfqxuz(分支 `zfq_dev`,2026-06-08..06-28,31 commits),`main` 快进合并至 `e516321`。合并前在隔离 worktree 全量 pytest:343 passed / 1 skipped(跳过项依赖可选 `pymongo`,预期行为)。本条目按 CLAUDE.md §4 补记(原分支未随代码更新 CHANGELOG)。

### Added
- **B-039 问卷结构化(Block 3A)**:4 张问卷结构表 + `PaperAnswer`(migration `0008`);DB→questionnaireV2 assembler;完成度纯校验;questionnaire domain dao/service/router + `GET /api/v1/questionnaire/structure`;GraphQL `submitPaperV2`/`getPaperV2`(SDL 契约测试钉死);投票门禁升级为结构化完成校验(过渡安全:无结构数据时回退旧行为)。
- **B-040 投票对象迁后端(Block 3B)**:候选表加 `merged_into`(migration `0009`);`detect_merges` 纯逻辑 + 导入时自动合并 + admin merge/unmerge 端点;统计 compute 尊重 `merged_into`(仅 canonical 项 + 票数归并);`GET /api/v1/vote-objects/characters|music|{id}` 分组查询;管理端候选项合并视图。
- **B-041 自由问卷管理**(取代 B-039 的 admin/契约部分):问卷结构表重塑为自由列表(去年份、自增 id,migration `0010`,**drop & recreate 4 表**);`GET /questionnaire/structure` 改返回**问卷数组**(原固定 8 槽对象作废)且去年份参数;答案改扁平数组;completion 改按 `required` 字段;13 个 admin CRUD 端点(问卷/题组/题/选项,均 `X-Admin-Secret`)+ 整树导入(支持无 id JSON);管理端自研嵌套编辑器 UI(卡片式问卷列表 + 逐层编辑)。
- `scripts/import_mongo_dump.py`:离线 BSON dump 导入 CLI(复用 sync mappers,`ON CONFLICT DO NOTHING`;需可选依赖 `pymongo`)。
- 设计文档:v11→v12 API 版本升级 + nginx 路由修复 spec/plans(`docs/superpowers/{specs,plans}/2026-06-09-*`)——**nginx 与前端侧均未实施**,是前后端联调前置项。

### Fixed
- alembic:`inspect()` 残留事务导致迁移不落库(clear transaction 后再 `begin_transaction`)。
- submit:raw submit 改 upsert,防重复落库。
- questionnaire:`_row_to_dict` 的 datetime 转 ISO 字符串;层级树导入兼容无 id JSON。

### 兼容性 / 部署
- 需 `alembic upgrade head`(0008→0010)。**0010 对 4 张问卷结构表 drop & recreate**,已导入的问卷结构需重新导入(设计时测试库为空,无损;若目标库已有结构数据需先导出)。
- `GET /questionnaire/structure` 为破坏性契约变更(数组形态);投票前端 questionnaireV2 加载**待适配**(plan 已写)。
- v12 路由契约(`/v12-be/` + nginx location 拆分)未部署;部署顺序约束:nginx 升版 ≤ 前端升版,后端结构端点先于前端切换。

## [2026-06-07] GraphQL Submit 桥接(投票提交/回读适配前端契约)

### Added
- `src/api/graphql/resolvers/submit_bridge.py`:按前端(旧 Rust gateway)契约新增 5 个 mutation(`submitCharacterVote/submitMusicVote/submitCPVote/submitPaperVote/submitDojin`,入参 `content: …GQL!`,返回 `Boolean`)与 5 个回读 query(`getSubmit*Vote(voteToken)`)。resolver 内 `voteToken`→`user_id`(即 vote_id),meta(时间/IP)服务端生成,不信任客户端;限流与提交锁按 token 身份。`DojinType` GraphQL 枚举(入库存枚举名)。SDL 契约由 `tests/unit/test_submit_bridge_schema.py` 钉死(21 例)。
- `src/api/graphql/errors.py`:错误映射工具从 resolvers/user.py 下沉共享;`_extensions` 支持异常自带 `human_readable_message` 优先于文案表;文案表新增 `SUBMIT_LOCKED`。
- `AppException` 增可选 `human_readable_message`(向后兼容)。

### Fixed
- `validate_paper` 重写为「合法 JSON + UTF-8 ≤256KB」:旧实现要求"非空列表+整数 id",是按想象格式写的,会拒掉前端真实载荷(嵌套对象);统计侧不读原始 papers_json,无下游结构依赖。REST 路径同步受益。错误文案改为面向用户("问卷数据不是合法 JSON，请重试"/"问卷数据过大")。
- 修复 `test_legacy_token_status` 两例日期依赖(session token 在 freeze 块外签发)。

### Changed / ⚠️ 唯一旧字段例外
- **`submitDojin` 新旧同名**:GraphQL 不允许同名字段并存,桥版本(`content: DojinSubmitGQL!`→`Boolean!`)经 MRO 取代旧版本(`input:`→`SubmitSuccess!`)。旧版本本就因 `SubmitService(db)` 传参错误不可用,无实际调用方。连带效应:旧版本独占的输入类型 `DojinSubmitInput`/`DojinSubmitMutationInput` 因无字段引用而从 SDL 剪除(strawberry 只输出可达类型)。其余旧字段(`submitCharacter(input:)` ×4、`getCharacterSubmit(voteId)` ×7)按决策原样保留。

### 兼容性 / 刻意差异(记录)
- service 校验错误(`ValueError`)以 `error_kind=INVALID_CONTENT` + 中文原文(`human_readable_message`)返回;锁冲突=`SUBMIT_LOCKED`(429)。
- 提交锁 key 为全局 `lock-submit-{user_id}`(对齐 Python REST 现状),与 Rust 的按类别 `lock-submit_character_v1-{vote_id}` 不同——刻意沿用 Python 约定。
- 回读 query 不限流(与 REST get-* 端点一致的刻意不对称;读是幂等的)。
- 桥未做 user 桥那种 per-IP 预解码限流:伪造 token 仅消耗 JWT 验签 CPU,提交频率天然受限,刻意从简。

## [2026-05-31] GraphQL 全局错误格式化器（保证 errors 必带 extensions）

### Added
- 新增 `src/api/graphql/http.py::AppGraphQLRouter`,override `process_result` 给**每一个**出站 GraphQL 错误兜底补 `extensions`(`{service,url,error_kind,error_message,human_readable_message,upstream_response_string}`)。`src/main.py` 改用它挂载 `/graphql`。

### Fixed
- 此前 `map_app_errors` 只覆盖被它包住的 resolver 内部错误;**schema 校验错误**(如 `Cannot query field 'X'`)、parse 错误、漏套 wrapper 的 resolver 异常会**无 `extensions`** 到达前端,导致前端 `extensions.error_kind` 直接崩(`Uncaught TypeError: extensions is undefined`)。现统一兜底:校验/parse 错误 → `error_kind="BAD_REQUEST"`;漏网运行时异常 → `error_kind="INTERNAL_ERROR"` 且 message 脱敏为 `Internal server error`(不泄露 SQL/SDK 细节,与 `map_app_errors` 的 INTERNAL_ERROR 处理一致)。

### 兼容性
- 已被 `map_app_errors` 赋了 `error_kind` 的错误**原样保留**,不覆盖。
- 纯增强,不改任何 query/mutation 行为;前端可选链兜底(Touhou-Vote `4df20d4`)与此构成防御纵深。
- 与 B-019(错误响应 shape 统一)同向。

## [2026-05-31] 补齐账号管理 GraphQL mutation + 错误中文文案

### Added
- 新增 4 个 GraphQL mutation,适配前端 `UserSettings.vue`:`updateNickname` / `updatePassword`(`oldPassword` 可选) / `updatePhone` / `updateEmail`。此前后端只在 service/REST(`/api/v1/user/update-*`)实现,GraphQL 未适配,前端调用直接报 `Cannot query field 'updatePassword'`(并触发前端 `extensions is undefined` 崩溃)。逻辑仍在 `UserService`,本次只做 GraphQL→service 的桥接(与登录 mutation 同模式),并复用 REST 同款限流(per-IP 30/60s + per-user 5/60s;改密码 5/300s,B-012)。
- `_extensions` 现按 `error_kind` 填充 `human_readable_message`(中文文案表)。此前恒为 `None`,导致前端改密码/改昵称兜底分支显示"原因:null"。

### Changed
- `map_app_errors` 新增可选 `remap` 参数:把 service 的通用 `USER_ALREADY_EXIST` 翻译成前端期望的 `PHONE_IN_USE` / `EMAIL_IN_USE`(`human_readable_message` 跟随 remap 后的 kind)。

### 兼容性
- 纯新增/增强,不改既有 mutation 与 REST。`removeVoter`(注销)前端未调用,未桥接。
- 已知未覆盖(非阻塞):投票提交(submit)路径前端用 `submitCharacterVote(content:...)` 等,与后端 `submitCharacter(input:...)` 名称+入参不一致,属同类 GraphQL 适配缺口,另行处理。


## [2026-05-31] session_token 有效期可配置，默认 7 → 30 天

### Changed
- `session_token` 有效期从写死的 **7 天**改为可配置:env/Nacos `SESSION_EXPIRE_DAYS`，默认 **30**。语义=用户多久不活跃就要重新发验证码登录;调长以**减少短信发送**与重复登录,权衡是会话被盗用窗口更长。`src/common/security/jwt.py:create_session_token` 改为读 `Settings.session_expire_days`。

### 兼容性 / 注意
- 已签发的旧 token 不受影响(各自带自己的 `exp`);仅新登录按新值签发。
- 改值需**重启容器**生效(`Settings` 是 `lru_cache` 单例,见 BACKLOG B-017)。
- `voteToken` 仍到投票季结束(`VOTE_END_ISO`),不受此项影响。

## [2026-05-31] 修复登录成功后又被弹回登录页（REST 契约漂移）

### Added
- 新增 legacy-compat 路由层 `src/api/rest/legacy/`，挂在后端**根路径**（无 `/api/v1` 前缀），首个端点 `POST /user-token-status`，复刻旧 Rust gateway 契约 `{status:"valid"|"invalid", voting_status, papers_json}`（HTTP 恒 200）。

### Fixed
- **登录后闪现投票页又被弹回登录页**:登录走 GraphQL 成功,但前端 bootstrap 的 `checkLoginStatus()` 会 `POST /v11-be/user-token-status`,而该扁平路径在 Python 后端是 404(真实路由在 `/api/v1/user/token-status`,且原实现返回空体而非 `{status:"valid"}`)。前端拿不到 `status:"valid"` 就 `deleteUserData()` 登出 → bounce。新增的 legacy-compat 端点同时修好**路径**和**响应 shape**,前端无需改动。

### 兼容性 / 迁移
- 纯新增,不影响 `/api/v1` 与 GraphQL 现有路由;旧 `POST /api/v1/user/token-status`（空体）保留。
- 这是迁移期兼容垫片,**移除条件**已记入 BACKLOG **B-033** 与 `docs/migration/legacy-rest-compat.md`:Rust gateway 下线 + 前端 REST 迁移到 `/api/v1`。
- 已知未覆盖:`/v11-be/doujin/api` 同类 404 本次未处理。

## [2026-05-31] 修复部署用旧镜像导致迁移不生效

### Fixed
- 部署脚本 `docker pull "${BACKEND_IMAGE}" || true` 在拉取失败时**静默使用本地旧镜像**,加上浮动 `:prod`/`:test` tag,导致 `alembic upgrade head` 可能跑旧镜像里的迁移(只到 0004),deploy 却报成功——迁移/代码悄悄没更新(0005 因此没生效,`alembic_version` 卡在 0004)。
- 改为:**用本次构建产出的不可变 digest**(`...-backend@<digest>`)部署;`docker pull` **去掉 `|| true`**(重试一次后仍失败则硬红终止),不再静默用旧镜像。移除已无用的 `BACKEND_TAG`。

### 注意
- 排查期间已直接对 RDS 补齐 `user` 表缺失列解锁登录;本修复保证后续迁移/镜像可靠交付。`alembic/**` 也已纳入 push 触发路径(迁移改动会触发部署)。

---

## [2026-05-31] 修复 user 表 schema 漂移(migration 0005)

### Fixed
- 测试库 `user` 表缺 `phone_verified` 等 0001 列(根因:`env.py` 的 `_maybe_baseline_existing_schema` 把一张残缺旧表自动 stamp 成 0001,0001 的建表从未真正执行),导致 `loginPhone` 报 `UndefinedColumnError` → `INTERNAL_ERROR`。
- 新增 migration `0005_reconcile_user_columns`:幂等 `ALTER TABLE "user" ADD COLUMN IF NOT EXISTS ...` 补齐所有 user 列(Postgres-only,非 PG 方言 no-op;干净库上全部 no-op)。

### 注意
- 这是针对 `user` 表的定向补丁以解锁登录;其他表可能有同源漂移,根治仍是在有权限时空库重建(BACKLOG B-025/B-026)。

---

## [2026-05-31] PNVS 短信模板参数可配置

### Fixed
- PNVS 之前写死 `template_param='{"code":"##code##"}'`,对含额外变量(如有效期 `min`)的短信模板会被阿里云判「模板内容与模板参数不匹配」(SMS_SEND_FAILED)。改为可配置 `ALIYUN_PNVS_TEMPLATE_PARAM`(默认仍为 `{"code":"##code##"}`,行为不变)。
- PNVS 频控码 `biz.FREQUENCY`(同号码发送过频)之前落到 `SMS_SEND_FAILED` 兜底,前端只显示"网络错误"。现归类为 `REQUEST_TOO_FREQUENT`,前端正确显示"请求过于频繁"。同时兜住 `*_LIMIT_CONTROL` / 含 `FREQUENCY` 的频控变体。
- 校验路径 `_parse_check_response` / `check_sms_verify_code` 抛 `SMS_VERIFY_FAILED` 时现在也带上游 `upstream_response_string`/`error_message`(此前缺,code review M3 遗留),便于排查"验证码失效/过期"类校验失败的真实阿里云返回码。

### Added
- `Settings.aliyun_pnvs_template_param`(env `ALIYUN_PNVS_TEMPLATE_PARAM`)。模板有 `min` 等变量时填 `{"code":"##code##","min":"5"}`。

### 兼容性
- 向后兼容:未设置时维持原默认值。

---

## [2026-05-31] CI 手动触发部署 + 登录配置清单文档

### Changed
- `deploy-test.yml`:`build-backend` / `deploy-test` 现在也响应 `workflow_dispatch`（之前 deploy 仅限 push）。job `if` 改为显式校验依赖结果，`skip_tests=true` 时仍可构建/部署。
- 部署步骤改 `docker-compose up -d --force-recreate backend`：即使镜像未变也重建容器，使**改完 Nacos 配置后手动触发即可让配置生效**，无需 SSH 上服务器 `docker restart`。

### Added
- `docs/operations/login-config-checklist.md`:登录模块所需 Nacos 配置项**待填清单**（按登录方式分组、必填/可选、JSON 骨架、R-NACOS `:10848` 访问入口、阿里云参数获取指引）。

### Changed（文档）
- `docs/operations/nacos-config-center.md` §四:补 R-NACOS 双控制台（协议口 `:8848` vs 鉴权控制台 `:10848`）访问方式;注明测试环境 dataId 为 `thvote_be`（下划线）。
- `docs/operations/cicd-pipeline.md` §6.2:更新手动触发行为说明。

### 兼容性
- 无破坏:push 触发行为不变;新增的是手动触发可部署的能力。

---

## [2026-05-30] GraphQL 登录 mutation 桥接

### Added
- GraphQL `UserMutation`：`requestPhoneCode` / `requestEmailCode` / `loginPhone` / `loginEmail` / `loginEmailPassword`，包装现有 `UserService`，对齐前端 `LoginBox.vue` 既定契约。
- `LoginResult { user: VoterFE, sessionToken, voteToken }` GraphQL 类型。

### Changed
- `AppException` 增加可选 `error_message` / `upstream_response_string`（向后兼容）。
- PNVS 发送失败时透传阿里云上游 code/message（复刻 Rust `ServiceError` 诊断信息）。
- GraphQL 错误 `extensions` 复刻 Rust shape：`{service,url,error_kind,error_message,human_readable_message,upstream_response_string}`。

### 兼容性
- 纯增量：REST `/user/*` 与 submit/result GraphQL 行为不变。
- GraphQL schema 新增 5 个 mutation 字段，无破坏。

### 已知差异
- `login_email_password` 对"用户不存在"返回 `INCORRECT_PASSWORD`（防枚举），前端 `NOT_FOUND` 分支不触发——刻意保留。
- 老用户密码登录仍依赖 B-008 历史数据回填（未做）。

---

## [2026-05-30] 文档对账：BACKLOG / REFACTOR_TODO 与 main 同步

> 不涉及代码变更，仅修正两份"进度仪表盘"与 `main`（HEAD `d4a3247`，2026-05-19）的偏差。
> 背景：`BACKLOG.md` 停在 2026-05-12、`REFACTOR_TODO.md` 停在 2026-05-13，而 `feat/user-and-verify` 期间（05-13..05-17）完成的一批 backlog 已合入 main 但未回标。

### Changed
- **`docs/BACKLOG.md`**：状态表标记以下为 ✅ 已完成（附 commit）：B-003(`8724e39`)、B-004/009/012(`9684643`)、B-007 SSO(`19d659f`..`e19d941`)、B-014/015/016(`581102f`)、B-017(`ab7a642`)、B-018(`fe993e4`)、B-025(`76facaa`)、B-027(`6d73de6`)、B-029(`0e340e9`)、B-030(`fce832a`)。B-011/B-026 阻塞已解除（依赖项 B-007/B-025 完成）→ 移入「可立即做」。重写「🟢/🟡/🔴」分组（去掉已失效的"等 PR merge"维度）。
- **`REFACTOR_TODO.md`**：用户模块补 SSO 已落地；autocomplete 由 ❌ 修正为 ⚠️（角色/音乐已实现 ILIKE，仅 `search_cps()` 仍空）；scraper 头部 ⚠️→✅；migration 表补 0004（SSO 列）；重排「建议实施顺序」并修复一处 markdown 残缺块。

### Fixed（文档准确性）
- 修正 B-008 描述：此前列为"可立即做"，实为**仅设计稿完成、实现未做**（`scripts/` 仍空）。
- 修正 B-028：2026-05-19 的 3 个 `fix(ci)` 提交只是修 `deploy-test.yml` 的 YAML/包发现 bug，**未补 prod 部署通道**，此项仍开放且为当前最高优先级。

### 兼容性
- 无（纯文档）。

---

## [2026-05-12] 合入 zfq_dev 基础设施：Apollo→Nacos、移除 docker/、workflow 精简

> 合并提交：`c8a04d5 merge: bring zfq_dev infrastructure (Nacos + new deploy) into feat`
> 包含 zfq_dev 18 个 commit：`5414a0f` … `2ced1fd`

### Changed
- **配置中心 Apollo → Nacos**：
  - 删除 `src/common/apollo.py`
  - 新增 `src/common/nacos.py`（812 行，含配置中心 + naming service 双功能）
  - 重写 `src/common/config.py`：模块加载期 `_load_nacos_sync()` 同步拉取 Nacos 配置写入 `os.environ`（仅当 key 不存在时），再交给 Pydantic Settings 实例化
  - `Settings` 类新增 13 个 `NACOS_*` 字段（含服务注册的 IP/port/cluster/weight）
- **服务注册接入**：`src/main.py` lifespan 现在会 `start_nacos_watcher` + `register_service_to_nacos`；新增 `/admin/discover/{service_name}` 与 `/admin/discover-self` 两个排障端点
- **依赖管理收敛**：删除 `requirements.txt`，所有依赖统一进 `pyproject.toml`；新增 `nacos-sdk-python>=2.0.0`
- **健康检查降级**：`/health` 现在在 DB 不可用时返回 `db_status=unavailable`（HTTP 200），而非整体 500
- **Nacos 加载本地文件回退**：Nacos 拿不到配置时尝试读 `<repo_root>/<NACOS_DATA_ID>` 同名文件作为应急

### Removed
- `.github/workflows/deploy-prod.yml`（与 Apollo / 仓库内 docker-compose 强耦合的旧 prod workflow）
- `.github/workflows/deploy.yml`（备用 prod workflow，功能与 deploy-test.yml 重叠）
- `.github/workflows/pylint.yml`（软门禁 `--exit-zero` 永不失败，与 deploy-test.yml lint job 重复）
- 整个 `docker/` 目录（compose 文件、apollo SQL 521+464 行、bootstrap 脚本、测试环境脚本）
- 整个 `frontend/` 目录（Dockerfile.prod、nginx 配置）
- `QUICKSTART.md`（内容过时）
- `docs/REFACTOR_TODO.md`（与本次合并冲突，删除态胜出）
- `local_db/dev.db`（不该进 git 的本地 sqlite 文件）
- `requirements.txt`

### Added
- `docs/operations/nacos-config-center.md`：Nacos 接入说明（配置 + 服务注册，含 dataId 写法样例与 lifespan 行为）
- 部署机不再编排本地 postgres 容器，改用阿里云 RDS（仍保留 redis container 在 deploy 流程里）
- `__pycache__/` 加入 `.gitignore`（zfq_dev 误提交了一些 `.pyc`，本次合并时清理）

### 兼容性
- **破坏性**：`APOLLO_*` 环境变量不再被读取，必须改用 `NACOS_*`
- **破坏性**：仓库内 `docker/docker-compose*.yml` 不再存在；部署机需自维护 compose 文件（详见 `cicd-pipeline.md` §三）
- **破坏性**：没有独立 prod workflow——main 分支 push 走的也是 `deploy-test.yml`，部署目标仍是 TEST_SERVER_HOST（镜像 tag 区分为 prod vs test）。**这是 follow-up B-028**
- **配置迁移路径**：原 Apollo `application` namespace 里的 `ALIYUN_PNVS_*` / `ALIYUN_DM_*` 17 个字段需要全量复制到 Nacos（`DATA_ID=thvote-be`，`GROUP=DEFAULT_GROUP`），格式建议标准 JSON
- **运行时风险**：`src/common/config.py` 顶层 `_load_nacos_sync()` 是 import-time 阻塞调用——Nacos 故障会让所有 import 链挂掉（B-030）

### CI/CD
- 唯一保留的 workflow `deploy-test.yml` 仍有 `alembic upgrade head` 步骤（test 阶段烟测 + deploy 阶段应用迁移），未受影响
- 部署阶段写入 `.env` 的内容从 `APOLLO_*` 改为 `NACOS_*`

### Docs
- `docs/README.md`：删除 `REFACTOR_TODO.md` 入口；新增 `nacos-config-center.md` 入口
- `docs/CHANGELOG.md`：本节
- `docs/BACKLOG.md`：B-017 重写为 Nacos 视角；新增 B-028（prod workflow 缺失）/ B-029（部署机 compose 归属）/ B-030（Nacos import 阻塞）/ B-031（_parse_config_content 容错），状态总览范围改为 B-001..B-031
- `docs/operations/cicd-pipeline.md`：整篇重写（Workflow 总览从 4 → 1；新增 §三"与部署机的耦合"；§四配置交付从 Apollo 改 Nacos；§七记录本次改动）
- `docs/operations/aliyun-onboarding.md`：§四改写为 Nacos 投递路径；引用 `nacos-config-center.md`
- `docs/architecture/database-schema-management.md`：阶段 2 标 ✅ 已完成；§四操作手册改用 `pip install -e .`（不再 `requirements.txt`）；备注 QUICKSTART.md 已删

### Follow-up
- **B-028**（高）：补 prod 部署通道或确认现状
- **B-029**（中）：部署机 compose 文件归属文档化
- **B-030**（中）：Nacos import-time 阻塞改 lazy
- **B-031**（低）：约束 Nacos 配置写标准 JSON 后删 `_parse_config_content` 容错分支

### Fixed（追加）
- **alembic 首次部署到已有 DB**：`env.py` 加 `_maybe_baseline_existing_schema`，跑迁移前自动检测"已有 managed 表但无 alembic_version"的状态，自动 stamp 到合适的 revision（user 在 → 0001；raw_character 在 → 0002）。`alembic upgrade head` 现在对**任意状态的 DB 都是幂等**的——空 DB、祖传 schema、已托管的 DB 都能直接跑。Sentinel 表与对应 revision 维护在 `_SENTINELS` 元组里，未来加迁移时同步追加

---

## [2026-05-12] 重构进度整理 + 四项 BACKLOG bug 修复

### docs
- 新建 `REFACTOR_TODO.md`：全项目重构进度总览，含各模块移植状态（✅/⚠️/❌）、测试空白、建议实施顺序及与 BACKLOG 的交叉引用

---

## [2026-05-12] 四项 BACKLOG bug 修复 + 文档同步

### Fixed
- **B-006**：删除 `src/main.py` 中重复的 `logging.basicConfig` 块（第 24-30 行是第 14-20 行的完整拷贝）
- **B-002**：`src/apps/submit/router.py` `prefix="/v1"` 改为 `prefix=""`，消除与 `api_router`(`prefix="/api/v1"`) 叠加产生的 `/api/v1/v1/...` 异常路径；submit 端点现在正确挂载在 `/api/v1/character/` 等路径下

### Changed
- **B-005**：`src/common/middleware/rate_limit.py` 替换非原子限流实现（旧：`GET last_reset → GET tokens → 判断 → DECR`，存在 TOCTOU 竞态）为原子 `INCR + EXPIRE` 固定窗口计数器；Redis key 格式从 `rate-limit-{uid}-tokens` / `rate-limit-{uid}-last-reset` 统一为 `rate-limit-{uid}`

### Added
- **B-001**：`alembic/versions/0002_voting_tables.py`，把投票相关表纳入 Alembic 版本管理：
  - 活跃表：`raw_character`、`raw_music`、`raw_cp`、`raw_paper`、`raw_dojin`（含复合索引）
  - 遗留表：`character`、`music`、`cp`、`questionnaire`（仍在 db_model/ 但已不写入）

### 兼容性
- **B-002**：submit REST 端点路径变更（`/api/v1/v1/...` → `/api/v1/...`），若有直接调用旧路径的客户端需更新；GraphQL 调用不受影响（resolver 直接调用 service 层）
- **B-005**：Redis key 格式变更，旧限流状态自然失效；已有部署升级后当前窗口内的限流计数重置（无安全风险）
- **B-001**：已有部署（表已存在）首版本要求 `alembic stamp 0002`，**已在 2026-05-12 后续修复中自动化**（`alembic/env.py:_maybe_baseline_existing_schema` 自动检测并 stamp，无需手工 stamp）

### docs
- `docs/CHANGELOG.md`：`[Unreleased]` → `[2026-04-27]`，更新日期
- `docs/BACKLOG.md`：更新日期，各条目经代码核查均保持原状（B-001~B-027 均未完成）
- `docs/migration/user-manager.md`：更新日期，checkbox 经代码核查属实
- `docs/REFACTOR_TODO.md`：顶部加醒目过时警告，指向 BACKLOG、CHANGELOG、migration 文档

---

## [2026-04-27] feat/user-and-verify 分支（已合入主干）

> 工作期间：2026-04-27
> 包含 commits：`45d75b7` … `c75f552`（共 16 个）
> 判断依据（2026-05-12 核查）：`src/apps/user/` 目录已有完整源文件（router/service/dao/deps/schemas/models/utils），表明该分支内容已合入主干。

### Added
- 用户与认证模块（feat/user-and-verify 分支）
  - 接入阿里云号码认证服务（PNVS）作为短信验证码全托管方案
  - 接入阿里云邮件推送 DirectMail（SMTP）作为邮件验证码投递通道
  - `EmailCodeService`：本地 6 位码生成 + Redis 存取 + guard 防刷（120s）
  - `SmsCodeService`：薄封装 PNVS 的 `SendSmsVerifyCode` / `CheckSmsVerifyCode`
  - 11 个对齐 Rust 的认证端点 + 1 个 `GET /me` 替代旧 `GET /{user_id}`
  - `ActivityLog` 9 类事件落库（best-effort，不阻断主请求）
  - 登录成功签发 `vote_token`（投票期内 + 已验证 phone 或 email）
  - Alembic 数据库迁移工具引入，baseline migration 把 User + ActivityLog 纳入版本管理
  - 设计文档 `docs/superpowers/specs/2026-04-27-user-auth-design.md`

### Changed
- `vote_token` JWT 主体由 `vote_id` 改为 `user_id`，对齐 Rust 行为；`audience` 保持 `vote`
- 用户敏感端点接入既有速率限制中间件（5 req/60s 按 IP 或 user_id 配比，详见设计文档 §7.4）

### Removed
- 半成品旧端点：`POST /api/v1/user/login`、`POST /api/v1/user/login/email`、`POST /api/v1/user/register`、`GET /api/v1/user/{user_id}`、`DELETE /api/v1/user/{user_id}`
- 历史遗留目录 `src/app/`（仅有 .pyc，无源文件）
- 历史遗留空壳 `src/models/__init__.py`（实际模型在 `src/db_model/`）

### 兼容性
- **破坏性**：上述移除的旧端点如有外部调用方需切换到新端点
- **数据库**：首次部署需运行 `alembic upgrade head`；已有部署字段已对齐，无需回填
- **配置**：要求 `ALIYUN_PNVS_*` 与 `ALIYUN_DM_*` 环境变量就位（Apollo / .env），未配置时调用对应端点会得到 `ALIYUN_NOT_CONFIGURED`
- **依赖新增**：`alembic`、`alibabacloud_dypnsapi20170525`、`alibabacloud_tea_openapi`、`alibabacloud_tea_util`；测试依赖 `freezegun`、`fakeredis`
- **DB 约束变更**：`user.at_least_one_identifier` CHECK 约束放宽为 `removed = TRUE OR phone_number IS NOT NULL OR email IS NOT NULL`，以支持 `remove-voter` 软删除时清空 email/phone（Rust 行为对齐）。已有部署执行 `alembic upgrade head` 即可。

### Operations
- 新增 `docs/operations/aliyun-onboarding.md`：从零到上线的阿里云 PNVS + DirectMail 接入手册（账号/RAM/认证方案/域名验证/SMTP/smoke 验证 + 常见坑）
- 新增 `docs/operations/cicd-pipeline.md`：CI/CD 流水线说明（4 个 workflow 拓扑、Aliyun/Apollo 配置交付路径、follow-up）
- 新增 `docs/superpowers/specs/2026-04-27-user-auth-open-issues.md`：用户与认证模块已知问题与待办（U-1..U-15），按 PR 前已修复 / PR 前待修 / PR 后再做分组
- 新增 `docs/architecture/database-schema-management.md`：数据库 schema 管理现状诊断 + 4 阶段演进路线图（阶段 1 已完成 ✅；阶段 2 把投票相关表纳入 Alembic；阶段 3 移除 init_db 后门；阶段 4 持续纪律）

### Fixed
- **U-1**：`init_db()` 与 Alembic 并存导致 schema 漂移 — 默认部署不再调用 `Base.metadata.create_all`，仅 `DEBUG=true` 时为本地开发保留。生产/测试环境必须靠 `alembic upgrade head`（CI 已就位）
- **U-4**：`remove-voter` 软删除现在同步清除 `password_hash` 与 `legacy_salt`，避免被删用户的密码哈希残留在 DB 里成为撞库素材
- **U-V1**：`_maybe_sign_vote_token` 配置错误从 `logger.warning` 升到 `logger.error`，避免 `VOTE_*_ISO` 打错时所有用户静默拿空 vote_token、submit 全挂但运维无信号
- **U-16**：`EmailCodeService.send` 用 `SET NX EX` 原子化 guard，并发同邮箱不再发两封邮件
- **U-17**：mutation 端点（`update-*` / `remove-voter`）在 token 解码前先做 IP 级限流（30 req/60s），堵住"刷 garbage token 拿快速 401"绕过 per-user 限流的路径
- **U-19**：`pnvs_client` check 失败的错误码从 `SMS_SEND_FAILED` 改为 `SMS_VERIFY_FAILED`，语义对齐

### CI/CD
- `deploy-test.yml` test job 在 `pytest` 之前新增 `alembic upgrade head` 步骤，把 0001 baseline 用真 Postgres service 烟测
- `deploy-test.yml` / `deploy-prod.yml` / `deploy.yml` 三处部署步骤都加 `docker-compose run --rm backend alembic upgrade head`，并在执行前等待 Postgres 健康
- `Dockerfile` 的 development + production stage 都 `COPY alembic/` 与 `alembic.ini`，使容器内可执行迁移
- `deploy-test.yml` 测试依赖加 `fakeredis`（与 requirements.txt 保持一致）

### 兼容性补充
- 首次部署到已有数据库的实例：`alembic upgrade head` 会在 `alembic_version` 表不存在时尝试 `CREATE TABLE user`，**与既有 `user` 表冲突**。需要先 `alembic stamp head` 把现有 schema 标记为最新，再走后续 migration。详见 `docs/operations/cicd-pipeline.md` §五 F-cicd-3。

### Follow-up
见 `docs/superpowers/specs/2026-04-27-user-auth-design.md` §九 F1-F9。
