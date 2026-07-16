# 前后端 API 契约对账（2026-07-14）

> 方法：后端全量路由/GraphQL 字段盘点（thvote-be-re main `9f39a81`）× 前端全量调用盘点（Touhou-Vote dev `cfba9cc`），关键结论均经测试机（:18000 / :8082 / :8084）curl 实测复核。
> 本文是"现状对账"，处置决策见文末"待拍板"。

## 一、无漂移（已收口，联调可直接用）

| 前端调用 | 后端对应 | 状态 |
|---|---|---|
| vote 包全部 GraphQL 操作（登录 5 + 账号 4 + 提交 5 + 回读 5,见 voteDataSource.ts / LoginBox / UserSettings / Vote*.vue） | 桥接字段（`loginPhone`/`submitCharacterVote(content:)`/`getSubmit*Vote(voteToken)` 等） | ✅ 全部命中桥接层,零旧字段调用 |
| `POST /v11-be/user-token-status`（user.ts:159） | legacy-compat 根路径 `/user-token-status` | ✅ v11/v12 兜底块都能到达 |
| `POST /v12-be/doujin/api`（EditDoujin.vue:294,待前端切 v12） | `/api/v1/scraper/scrape`,契约实测吻合 | ✅ v12 已修;**v11 路径仍 404**,切 v12 前该功能坏着 |

## 二、重大漂移：result 包全量在老 Rust 契约上 ⚠️

- result 前端（18 个文件、21+ 个 query）全部使用**老 Rust result-query 字段名**：`queryCharacterRanking` / `queryMusicRanking` / `queryCPRanking` / `query*Single` / `query*Trend` / `queryGlobalStats` / `queryQuestionnaire(Trend)`,入参 `(voteStart: DateTimeUtc!, voteYear: Int!, ...)`。
- Python GraphQL 实测**没有这些字段**（Query 只有 `ranking(category,...)`/`trends`/`singleEntity`/`globalStats`/... 返回 JSON blob,签名、命名、返回 shape 三者全不同）。
- 测试机 :8084 的 nginx `location /res-be/` **已指向 Python 后端**（Dockerfile.result.template:36）→ **result 页在测试机上全部 schema 校验失败**。生产 result 仍靠 touhou.ai 老 Rust 活着。
- 附带硬编码：各页面散落 `voteYear: 11`、`voteStart: Date.UTC(2023,11,29)`（上届参数）。

## 三、后端死代码：旧 GraphQL submit 字段确认全坏

`resolvers/submit.py` 全部 12 个旧字段（`submitCharacter(input:)` ×5、`getCharacterSubmit(voteId)` ×7,含 `getVotingStatus/Statistics`）都有同一 bug：`SubmitService(db)` 直接传 session,运行时必炸（service.py:131 期望 `SubmitDAO`）。前端**零调用**（本次盘点确认）→ 属可安全删除的死代码,删除后 SDL 更干净（此前仅知 submitDojin 一例,本次确认是全员）。

## 四、本地静态数据 →后端化 对照表（前端待切清单）

| 前端本地数据 | 后端已就绪的替代 | 备注 |
|---|---|---|
| `shared/data/character.ts`(244 角色)、`music.ts`(612 曲)、`work.ts` | `GET /api/v1/vote-objects/characters|music|{id}`（B-040） | 前端 plan 已写(vote-objects-frontend) |
| `shared/data/questionnaire.ts`（V1,**仍是生产提交链路**）、`questionnaireV2.ts`(占位) | `GET /api/v1/questionnaire/structure` + `submitPaperV2`（B-039/041,测试机已导入 8 问卷骨架） | 前端 plan 已写(questionnaire-frontend/admin-frontend) |
| `shared/data/time.ts`（`deadline` 临时改成 **2099 年**,注释称"投票开始前需改回"） | `POST /api/v1/voting-status/`（或补 server-time 类端点） | ⚠️ 高危遗忘点:不改回=永不截止 |
| `shared/data/voteYear.ts`（=12 硬编码） | 后端 `/health` 已报 vote_year,或随 voting-status 下发 | 低 |
| `vote/.../doujin.ts` doujinTypes、`getNickName.ts` NickNameData | 后端 DojinType 枚举 / autocomplete | 低,可长期保留前端 |

## 五、修正此前判断的两条

1. **`/server-time` 并非联调必撞**：现前端只有 2 处 fetch（见一/三行表）,没有任何 `/server-time` 调用,时间逻辑全走本地 time.ts。除非决定做"服务器时间对齐",否则无需补该端点。
2. **`search_cps()` 恒空暂不影响前端**：前端搜索（角色/CP 选择）全部在本地 character.ts + NickNameData 上做,不调 `/api/v1/autocomplete/search`。修复优先级降低（后端自身功能正确性问题仍在）。

## 六、次要隐患

- **codegen**：vote/result 两包 codegen 默认 schema URL 都指向**生产 Rust**（`https://touhou.ai/vote-be/graphql`,CI 里才覆盖成测试后端）;且无 `documents:` 校验,组件内联 gql 写错字段**编译期不报错**,只能运行时炸。本地跑 codegen 时务必带 `GRAPHQL_SCHEMA_URL=http://154.37.215.62:18000/graphql`。
- navigator 包零后端调用（vite 里的 `/nav-be` 代理是死配置）。
- B-019 错误 shape 统一：当前前端实际消费面均已兜住（legacy 路由复刻 Rust shape、scraper shape 天然吻合、GraphQL 有全局 extensions 兜底）,维持低优先级。

## 待拍板（影响下一步排期）

1. **result 契约怎么收口**（本审计最大项）：
   - 路线 a（沿用既定打法）：后端加 result 桥接层,复刻老 Rust 字段名/签名/返回 shape,result 前端零改动。工作量大（11 个字段,entries/trend 等复杂 shape）。
   - 路线 b：result 前端改写到 Python 新契约（`ranking(category:...)` JSON）。前端 18 文件全动,且 result 是给公众看的,回归成本高。
   - 无论 a/b,`voteYear=11`/`voteStart=2023` 硬编码都要一并处理。
2. ~~旧 GraphQL submit 死字段是否删除~~ → 已删（同日 PR `refactor/remove-dead-submit-graphql`,详见 CHANGELOG）。
3. `time.ts` deadline=2099 的改回机制（建议至少加 BACKLOG 提醒项,或直接切后端 voting-status）。
