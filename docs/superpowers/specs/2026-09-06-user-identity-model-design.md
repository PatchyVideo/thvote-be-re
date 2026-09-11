# 用户身份模型归一化(user + user_identity)设计

> **状态**:已实施(2026-09-06,migration 0018;见 CHANGELOG 同日条目)。本文件是设计稿,记录设计意图与取舍。
> 日期:2026-09-06
> 范围:`thvote-be-re` 的 `user` 表、`src/apps/user/*`、管理端用户列表、旧 Mongo 同步、迁移 `0018`。
> 前提:系统尚未公开上线,用户库允许破坏性重建,**无兼容期**。

---

## 一、背景与问题

现状(`src/db_model/user.py`)把四种认证来源平铺成列:`phone_number`/`phone_verified`、`email`/`email_verified`、`thbwiki_uid`、`qq_openid`,各配一个 partial unique index,外加 CHECK 约束 `at_least_one_identifier`(活跃账号必须有手机或邮箱)。

这个形状带来的具体问题(2026-09-06 核查代码确认):

1. **每加一个 provider 要改七处**:迁移加列加索引、DAO 加 `find_by_x`、`_merge_sso_session` 加分支、`bind_sso` 复制一段、`remove_voter` 加清理、`VoterFE` 加字段、admin 映射加字段。`bind_sso` 已经是两段几乎相同的代码,设计稿 F3 还排着第三个来源 patchyvideo。
2. **软删除漏掉 SSO 列**:`remove_voter` 清邮箱、手机、密码,但不清两个 SSO id;`find_by_thbwiki_uid`/`find_by_qq_openid` 也不过滤 `removed`。注销过的账号永久占住该 QQ/THBWiki 身份,他人再绑报 `SSO_ID_ALREADY_BOUND`。
3. **登录时合并 SSO 会话不查重**:`_merge_sso_session` 直接赋值,撞 unique index 抛 `IntegrityError` → 500;sid 已被 `GETDEL` 消费,重试无效。
4. **验证状态只属于手机和邮箱**:SSO 身份没有 verified、绑定时间、绑定 IP/设备等元数据;"哪个身份可信"本是身份的属性,却固化成账号上两个布尔列。

同时确认的现状:SSO 今天只是"绑定"而非"注册来源"——OAuth 回调只换一个 sid,用户仍须走手机/邮箱验证码登录;前端登录只走 GraphQL,GraphQL 桥接构造 `UserService` 时不传 redis、不收 sid,所以"登录时顺手绑 SSO"在生产链路上实际不通,能用的只有已登录后的 `/sso/*/bind`。

## 二、目标与非目标

**目标**

- 账号与认证来源分离:`user` 只表达账号,`user_identity` 一行一个认证来源。
- 登录、绑定、改绑、注销收敛为一套按 `(provider, subject)` 查身份的代码路径;加 provider 只加枚举值。
- 每条身份自带绑定时间、绑定 IP、绑定设备指纹,供反刷聚类使用。
- 修掉上面第 2、3 两个 bug。
- 对外契约(REST `VoterFE`、GraphQL `LoginResult`、admin 用户列表字段)**形状不变**。

**非目标(本轮不做)**

- SSO 独立登录/注册入口(用 QQ/THBWiki 直接登录、无账号则创建)。表结构已为此留位,但不加端点、不改前端登录框、不加 GraphQL mutation。
- GraphQL 登录链路传 sid。维持现状,记为已知缺口。
- 按设备/IP 硬拦截多账号注册(见第十一节)。
- 旧 Mongo 用户导入。上线即空库,导入链路一并移除。

## 三、数据模型

### 3.1 `user`(账号)

| 列 | 说明 |
| --- | --- |
| `id` | 不变,UUID4 字符串主键(`generate_user_id`) |
| `nickname`, `pfp` | 不变 |
| `password_hash` | 不变,可空;只存 Argon2 |
| `removed` | 不变 |
| `register_date`, `register_ip_address`, `register_device_id` | 不变 |

**删除**:`phone_number`、`phone_verified`、`email`、`email_verified`、`legacy_salt`、`thbwiki_uid`、`qq_openid`;CHECK `at_least_one_identifier`;索引 `ix_user_email_unique`、`ix_user_phone_unique`、`uq_user_thbwiki_uid`、`uq_user_qq_openid`。保留 `idx_user_register_date`。

`register_*` 与首条身份的 `created_*` 内容重复,**刻意保留**:现有反刷聚类(B-044/B-049)和管理端按账号级注册信息查询,保持稳定。

### 3.2 `user_identity`(认证来源)

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | Integer 自增主键 | |
| `user_id` | String(64),FK → `user.id` ON DELETE CASCADE,有索引 | |
| `provider` | String(16) + CHECK IN ('email','phone','qq','thbwiki') | 用 VARCHAR 加约束而不用 PG 原生 enum:sqlite 单测可跑;加值只改代码和 CHECK,不改类型 |
| `subject` | String(255),非空 | 归一化后的标识,见 3.3 |
| `verified` | Boolean,非空 | 见 3.4 |
| `verified_at` | DateTime(tz),可空 | |
| `created_at` | DateTime(tz),非空,server_default now() | 绑定时间 |
| `created_ip` | String(64),非空,默认 '' | 绑定时的可信客户端 IP(`meta.user_ip`) |
| `created_device_id` | String(128),非空,默认 '' | 绑定时的设备指纹(`meta.additional_fingureprint`) |
| `last_login_at` | DateTime(tz),可空 | 用该身份登录时更新 |

约束(均为**完整**唯一约束,不再是 partial):

- `uq_user_identity_provider_subject (provider, subject)`:一个邮箱/手机号/openid 只属于一个账号。
- `uq_user_identity_user_provider (user_id, provider)`:一个账号每种来源最多一个身份;改手机号是替换不是追加,与现有语义一致。

不再需要 partial 条件的原因:注销时直接删身份行(见 5.5),同一邮箱注销后重新注册自然不冲突。

### 3.3 subject 归一化

集中在 `normalize_subject(provider, raw)`,规则:

| provider | 规则 |
| --- | --- |
| email | `strip()` 后转小写(旧 Rust 网关在 `login_email_password` 也做小写) |
| phone | `strip()`,其余原样(格式校验仍在 Pydantic 层) |
| qq | 原样(openid) |
| thbwiki | 原样(MediaWiki user id 字符串) |

### 3.4 `verified` 的语义

当前所有创建身份的路径(验证码登录、改绑、OAuth 绑定)都在验证通过后才建行,因此本轮**不存在** `verified=false` 的行;创建时一律 `verified=true` 并写 `verified_at`。这一列是为未来"先录入后验证"的场景预留,**没有隐含逻辑**。投票资格判断(5.6)仍显式检查 `verified`,以便未来引入未验证身份时规则不变。

### 3.5 关系加载

`User.identities` 关系用 `lazy="selectin"`:取账号时多一条 `IN` 查询带出全部身份,async 会话下不触发懒加载报错。用户量为千级,每账号身份 ≤4 行,开销可忽略。

## 四、代码结构

| 单元 | 职责 |
| --- | --- |
| `src/db_model/user.py` | `User` 去掉身份列;加 `identities` 关系 |
| `src/db_model/user_identity.py` | `UserIdentity` 模型与约束 |
| `src/apps/user/identity.py` | `IdentityProvider`(StrEnum:EMAIL/PHONE/QQ/THBWIKI)、`normalize_subject`、`VOTE_ELIGIBLE_PROVIDERS` |
| `src/apps/user/dao.py` | `UserDAO` 删 `get_by_email`/`get_by_phone`/`find_by_thbwiki_uid`/`find_by_qq_openid`;`search_users` 改 join 身份表。新增 `UserIdentityDAO`:`find_user(provider, subject) -> User \| None`(只返回 `removed=False` 的账号)、`get(user_id, provider)`、`add`、`delete`、`delete_all_for_user`、`touch_last_login` |
| `src/apps/user/service.py` | `UserService` 保持为入口。身份操作抽到 `src/apps/user/identity_service.py`(实现时若抽出后 service.py 仍超 400 行,继续按"验证码 / 登录 / 账号维护"拆) |
| `src/apps/user/schemas.py` | `voter_fe_from_user(user)` 从 `user.identities` 算 `phone`/`email`/`thbwiki`;`VoterFE` 形状不变 |
| `src/apps/user/utils/security.py`、`src/common/security/password.py` | 删 `verify_legacy_password`/`verify_any_password` 及 bcrypt+salt 路径;只留 Argon2 `hash_password`/`verify_password` |
| `src/apps/admin/router.py`、`schemas.py` | `UserAdminItem` 字段不变;`email`/`phone`/`email_verified`/`phone_verified` 从身份算出 |
| `src/apps/admin/sync/runner.py` | 删 `map_voter` 与 `("mongodb_db_users","voters","user",...)` 同步项;其余集合不动 |
| `src/api/graphql/types.py` | 无形状变化;`LoginResult.user` 仍由 `VoterFE` 转换 |

`VOTE_ELIGIBLE_PROVIDERS` 默认 `{email, phone}`,通过配置项 `VOTE_ELIGIBLE_PROVIDERS`(JSON 数组字符串,与 `ADMIN_ALLOWED_IPS` 同形,Nacos 可改;未知值忽略)覆盖。是否改为仅手机号,上线前另行决定(见第十一节)。

## 五、行为与流程

### 5.1 核心内部方法

**`_login_by_identity(provider, subject, nickname, meta, sid) -> LoginResponse`**

1. `find_user(provider, subject)`;命中但账号 `removed=TRUE`(管理端封禁,身份行保留)→ `USER_REMOVED` 403;
2. 无 → `_register(provider, subject, nickname, meta)`:建 `User`(`register_*` 取 meta)+ 一条身份(`created_*` 取同一份 meta,`verified=true`);写 `voter_creation` 日志;
3. 有 → `touch_last_login`;写 `voter_login` 日志;
4. `_merge_sso_session(user, sid, meta)`(5.3);
5. 签 session token 与(有资格时)vote token。

三个登录入口都是它的薄包装:`login_with_email_code`、`login_with_phone_code` 先 `consume` 验证码;`login_with_email_password` 先 `find_user(email, ...)` 再 `verify_password`,不建账号。

**`_bind_identity(user, provider, subject, meta, conflict_code) -> UserIdentity`**

1. `find_user(provider, subject)` 命中且 `id != user.id` → 抛 409,错误码由调用方传入:`update_email`/`update_phone` 传 `USER_ALREADY_EXIST`,SSO 路径传 `SSO_ID_ALREADY_BOUND`(两个现有契约都保住);
2. 命中且是本人且 subject 相同 → 幂等返回现有行;
3. `get(user.id, provider)` 已有其他 subject → 删旧行、插新行(替换语义,新行 `created_*` 取本次 meta);
4. 否则插新行。

### 5.2 改绑

`update_email`/`update_phone`:鉴权 → `consume` 验证码 → `_bind_identity(..., USER_ALREADY_EXIST)` → 日志(old_value 取被替换行的 subject)。

### 5.3 登录时合并 SSO 会话

`_merge_sso_session`:读 Redis sid → 对每个 key 调 `_bind_identity`;**捕获 409 记 warning 跳过,不阻断登录**(用户已通过验证码,绑定只是顺手)。其他异常照常抛。

### 5.4 已登录后绑定 SSO

`bind_sso` → `_bind_identity(..., SSO_ID_ALREADY_BOUND)`,meta 取 bind 请求。路由层 `_sso_bind` 的 provider if/else 保留(它做的是 OAuth 交换,不是身份存储)。

### 5.5 注销

`remove_voter`:校验旧密码(如有)→ `delete_all_for_user` → `password_hash=None`、`removed=True` → 日志。账号行保留,供投票记录关联与审计。

### 5.6 投票资格

`_maybe_sign_vote_token`:存在 `verified=true` 且 `provider ∈ VOTE_ELIGIBLE_PROVIDERS` 的身份才签 vote token。等价于旧 Rust `generate_vote_id` 的 `phone_verified || email_verified`。

### 5.7 `VoterFE` 映射

| 字段 | 来源 |
| --- | --- |
| `username` | `user.nickname` |
| `pfp` | `user.pfp` |
| `password` | `bool(user.password_hash)` |
| `phone` | phone 身份的 subject,无则 null |
| `email` | email 身份的 subject,无则 null |
| `thbwiki` | 是否存在 thbwiki 身份 |
| `patchyvideo` | 固定 false(遗留字段) |
| `created_at` | `user.register_date` |

### 5.8 "至少一个身份"

原 CHECK 跨表无法表达。当前没有解绑端点,改绑是替换,注销是整体删除,所以没有会让活跃账号身份为零的路径;**不加应用层检查**。未来加解绑端点时,在该端点拒绝删最后一个身份。

## 六、刻意的行为变化

| 变化 | 原因 |
| --- | --- |
| 登录时 SSO 合并冲突:500 → 跳过并 warning | 见 5.3 |
| 注销后同一 QQ/THBWiki 可被他人或本人重新绑定 | 修 bug 2 |
| 邮箱密码登录只认 Argon2,bcrypt+salt 路径删除 | 无旧用户导入,`legacy_salt` 无来源 |
| 管理端搜索 email/phone 改为 join 身份表 | 列已迁移;结果集不变 |
| admin `UserAdminItem.email_verified/phone_verified` 来自身份行的 `verified` | 形状不变 |
| 旧 Mongo `voters` 集合同步删除 | 上线即空库 |
| 被管理端封禁(`removed=TRUE` 但身份行保留)的邮箱/手机再登录:旧实现撞 partial unique index → 500,新实现返回 `USER_REMOVED`(403),且该标识不能被新账号注册 | 封禁要可解封,身份行必须保留;实施时发现 |

## 七、迁移 `0018`(down = `0017`)

upgrade:

1. 建 `user_identity` 及两条唯一约束、`user_id` 索引;
2. 回填(近似值,文档注明):
   ```sql
   INSERT INTO user_identity (user_id, provider, subject, verified, verified_at,
                              created_at, created_ip, created_device_id)
   SELECT id, 'email', lower(trim(email)), email_verified,
          CASE WHEN email_verified THEN register_date END,
          register_date, register_ip_address, register_device_id
     FROM "user" WHERE email IS NOT NULL AND removed = FALSE;
   -- phone / qq / thbwiki 同形;qq、thbwiki 的 verified 取 TRUE
   ```
   `removed=TRUE` 的行不回填身份(与 5.5 一致)。
3. 删 `user` 的七个列、CHECK、四个 partial index。

> **2026-09-12 复核补记(两条隐患,均已修;只影响"带 0018 之前存量数据的库")**
>
> 1. **归一化会撞新唯一约束**(已加前置检查拦住)。旧的 partial unique index 建在**原始列**上且**大小写敏感**,所以 `Foo@Example.com` 与 `foo@example.com` 可以合法共存;回填用 `lower(trim(...))` 归一化后两者塌成同一个 subject,撞 `uq_user_identity_provider_subject`。`trim(phone_number)` 同理(`' 138…'` vs `'138…'`)。真 PG 16 上已复现:迁移跑到一半抛 `UniqueViolation` 整体回滚。**现已在 `upgrade()` 开头加 `_assert_no_backfill_collisions`**,建表前就拒绝并点名冲突账号,而不是中途炸一个裸 Postgres 错误。
> 2. **回填曾把"管理员封禁"当成"用户自助注销"**(2026-09-12 已修)。`removed=TRUE` 在旧表里有两种来源:`remove_voter` 自助注销(§5.5)与 `ban_user` 管理员封禁(`admin/service.py` 只翻 `removed`)。原回填用 `removed = FALSE` 一刀切,把封禁账号也排除了 —— 而 `IdentityService.resolve` 正是靠身份行对封禁 subject 抛 `USER_REMOVED` 来防止改头换面重新注册,于是封禁账号的邮箱/手机被释放、解封后又没有任何身份可登录(真 PG 已复现:封禁账号回填得 0 条 identity)。
>
>    **两者其实可以区分**(复核时查实,此前误以为不可区分):旧 `remove_voter` 在同一次提交里把 `email`/`phone_number`/`password_hash` **全部置空**,而 `ban_user` 一个都不动;旧 CHECK `at_least_one_identifier` 又保证活跃账号必有 email 或 phone,封禁前是活跃的,所以必有其一。判别式即 `_BACKFILL_SCOPE`:
>
>    ```sql
>    removed = FALSE OR email IS NOT NULL OR phone_number IS NOT NULL
>    ```
>
>    于是两个目标不必取舍:封禁账号的身份行完整回填(封禁可执行、解封可登录),自助注销的账号一条都不回填 —— **包括旧 `remove_voter` 漏清的 `qq_openid`/`thbwiki_uid`**(§一.2 记的缺陷),不借回填把用户要求抹除的标识搬进新表。真 PG 上四种形态逐一验证通过。
>
> 两条对现有环境都**不影响**:测试机的 0018 已在近乎空库上跑完,新环境是空 `user` 表上跑 0018(回填是空操作),且 §9 已定"旧 Mongo `voters` 同步删除、上线即空库",不存在 legacy 用户导入通道(`COLLECTION_CONFIG` 里没有 user 映射)。隐患只在"拿 0018 之前的存量库重放迁移"时成立。

downgrade:重建七列与约束,反向回填(每账号每 provider 取唯一一行),删 `user_identity`。

sqlite 测试库走 `create_all`,不跑迁移;迁移只在 PG 上验证(测试机 + CI 的 PG job)。

## 八、测试

| 层 | 用例 |
| --- | --- |
| 单测 | `normalize_subject` 各 provider;`_bind_identity` 的冲突 409 / 本人幂等 / 同 provider 替换;`_maybe_sign_vote_token` 只认资格集合与 `verified` |
| 契约 | `test_voter_fe_contract`、`test_router_endpoints`、`test_sso_endpoints`、`test_graphql_login_contract` 断言不改 |
| 集成 | 验证码首登建账号 + 身份(`created_*` 与 `register_*` 一致);同邮箱再登不重建且 `last_login_at` 更新;改绑到他人邮箱 409;注销后同邮箱重登得到新账号 id;SSO bind 冲突 409;登录 sid 合并冲突不阻断登录;注销后同 openid 可再绑 |
| PG 专属 | 两条唯一约束真抛 `IntegrityError`(顺带完成 B-022) |
| 迁移 | 在 PG 上 upgrade → 校验回填行数 = 各非空列计数 → downgrade → 校验列恢复 |

现有全量测试(约 400)须通过;直接构造 `User(email=...)` 的测试改为账号 + 身份,建议加一个测试 helper `make_user(email=..., phone=...)` 收敛改动。

## 九、文档与 changelog

- `docs/migration/user-manager.md` §一 重写为新结构;附旧 Rust 字段 → 新表映射(见附录)。
- `docs/CHANGELOG.md`:`Changed`(用户模型归一化,**需数据迁移 0018,无兼容期**,对外接口形状不变)+ `Removed`(legacy 密码路径、voters 同步)。
- `docs/BACKLOG.md`:关闭 B-011(CHECK 约束随本轮删除)、B-022(PG 唯一约束测试)、B-024(视 `save()` 是否仍存在)、B-008(Mongo→PG 用户回填脚本,随"上线即空库"决定作废)。
- 本设计稿状态改为"已实施"。

提交拆三个:`refactor:` 表 + 代码,`test:`,`docs:`。

## 十、风险与回滚

- **风险:漏改旧列消费方**。实现前 `grep -rn 'phone_number\|email_verified\|phone_verified\|thbwiki_uid\|qq_openid\|legacy_salt' src tests scripts` 列清单逐个清零;mypy 与全量测试兜底。核查时的已知消费方:`apps/admin/router.py`、`apps/admin/schemas.py`、`apps/admin/sync/runner.py`、`apps/admin/monitor/dao.py`(只用 `register_date`,不受影响)、`api/graphql/types.py`(经 `VoterFE`,不受影响)。
- **风险:selectin 让每次取账号多一条查询**。量级可忽略;若管理端列表分页出现 N+1,在 `search_users` 显式 `selectinload`。
- **回滚**:`alembic downgrade 0017` + 回退代码。测试机数据可由 mock 工具重灌(`docs/operations/mock-vote-data.md`)。

## 十一、反刷说明(多账号)

"手机注册一个、退出、邮箱再注册一个"在现有扁平表下已经可行,本轮既不使其更易也不更难;决定小号成本的是身份获取成本(邮箱几乎免费)。新模型的贡献是每条身份带 `created_ip`/`created_device_id`,同一设备指纹下分属两个账号的手机身份与邮箱身份可被 B-044/B-049 的聚类直接命中。

三档处置,均不需改表:

1. 只取证不拦截(**本轮默认**,与现有反刷方针一致);
2. 邮箱账号能登录不能投票:`VOTE_ELIGIBLE_PROVIDERS=phone`,上线前按用户构成决定;
3. 按设备限注册:不做。`device_id` 是 localStorage UUID,清除即失效,只防手动开号,且误伤共用电脑。

## 附录:旧字段 → 新表映射

| 旧(Rust Voter / 旧 `user` 列) | 新 |
| --- | --- |
| `phone` / `phone_number` | `user_identity(provider='phone').subject` |
| `phone_verified` | `user_identity(provider='phone').verified` |
| `email` | `user_identity(provider='email').subject` |
| `email_verified` | `user_identity(provider='email').verified` |
| `qq_openid` | `user_identity(provider='qq').subject` |
| `thbwiki_uid` | `user_identity(provider='thbwiki').subject` |
| `password_hashed` / `password_hash` | `user.password_hash`(不变) |
| `salt` / `legacy_salt` | 删除 |
| `signup_ip` / `register_ip_address` | `user.register_ip_address`(不变);另有每身份 `created_ip` |
| — | `user_identity.created_at/created_device_id/last_login_at`(新增) |
