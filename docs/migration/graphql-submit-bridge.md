# GraphQL Submit 桥接(投票提交路径适配)— Spec 草稿

> 状态:**草稿,待讨论定稿**(2026-06-07 起草,基于前端 dev 分支与 thvote-be Rust gateway 的双向契约勘探)。
> 模式与已完成的 user 模块桥接(登录 PR #3 / 账号管理 PR #4)相同:**业务逻辑不动(`SubmitService`),只加 GraphQL 桥**。

## 1. 背景 / 差距

前端(`Touhou-Vote/packages/vote`)的投票提交与回读**全走 GraphQL**,契约是按旧 Rust gateway 写的;
Python 侧现有 GraphQL submit 字段是自创命名(`submitCharacter(input:)` / `getCharacterSubmit(voteId)`),
**名字、入参、返回都不匹配**,前端一调即 `Cannot query field`。

## 2. 目标契约(以前端 gql 文档为准,大小写已逐一核实)

### 2.1 Mutations(5 个,均返回 `Boolean`)

| 字段 | 入参类型(精确名) | content 结构 |
|---|---|---|
| `submitCharacterVote` | `CharacterSubmitGQL!` | `{voteToken, characters: [{id, first?, reason?}]}` |
| `submitMusicVote` | `MusicSubmitGQL!` | `{voteToken, musics: [{id, first?, reason?}]}` |
| `submitCPVote` | `CPSubmitGQL!` | `{voteToken, cps: [{idA, idB, idC?, active?, first?, reason?}]}` |
| `submitDojin` | `DojinSubmitGQL!` | `{voteToken, dojins: [{title, author, url, dojinType, reason, imageUrl?}]}`(前端两处使用:VoteDoujin + EditDoujin) |
| `submitPaperVote` | `PaperSubmitGQL!` | `{voteToken, paperJson: String}` |

- `DojinType` 为 GraphQL 枚举:`ARTICLE / CRAFT / DRAWING / MUSIC / OTHER / SOFTWARE / VIDEO`(Python 现为 str,需加枚举类型并映射)。
- 注意 music 提交字段名是 **`musics`**(复数),而回读结果字段是 **`music`**(单数)——是旧契约的怪癖,照抄。

### 2.2 Queries(5 个,凭 voteToken 回读已投内容)

| 字段 | 返回选择集 |
|---|---|
| `getSubmitCharacterVote(voteToken!)` | `{characters {id first reason}}` |
| `getSubmitMusicVote(voteToken!)` | `{music {id first reason}}` |
| `getSubmitCPVote(voteToken!)` | `{cps {idA idB idC active first reason}}` |
| `getSubmitDojinVote(voteToken!)` | `{dojins {dojinType url title author reason imageUrl}}` |
| `getSubmitPaperVote(voteToken!)` | `{papersJson}` |

### 2.3 错误契约

前端 onError:`error_kind === 'REQUEST_TOO_FREQUENT'` → 「请求过于频繁」;
其余一律弹 `'投票失败，原因：' + extensions.human_readable_message`。
→ 直接复用 user 桥的 `map_app_errors` + `_HUMAN_READABLE_MESSAGES`(需为 submit 侧错误补文案,见 §5)。

## 3. 关键语义(复刻 Rust gateway)

1. resolver 收 `voteToken` → `decode_vote_token()` → `user_id`(即 vote_id);**客户端不再传 vote_id,服务端生成 meta**(created_at=now、user_ip 取自请求上下文)。比现状(信任客户端 `meta.vote_id`)更安全。
2. 限流 + 提交锁沿用现有 resolver 的 `rate_limit` / `_acquire_vote_lock`,但 key 改为 token 解出的 `user_id`(现状用客户端给的 `input.meta.vote_id`,同样属于信任客户端,顺带修正)。
3. 校验、入库全部走现有 `SubmitService.submit_*` / `get_*_submit`,不改 service。

## 4. 已定决策

- **改后端适配前端**(A 方案哲学,同 user 模块):前端零改动。
- **旧字段保留**(用户拍板,以防万一):`submitCharacter(input:)` ×5、`getCharacterSubmit(voteId)` ×7 暂不删除,双轨并存。
  - ⚠️ 遗留风险记录:`get*(voteId)` 系列**无鉴权可凭裸 voteId 查任意人提交**;保留期间此暴露面继续存在。移除条件:新契约上线且前端验证通过后,单独 PR 清理(届时记 changelog)。

## 5. 待讨论(下次细聊的议题清单)

1. **submit 侧错误文案表**:`SUBMIT_LOCKED`、`VOTE_TOKEN_REQUIRED`/`INVALID_TOKEN`(投票 token 失效≈"请重新登录")、各 `ValueError` 校验消息(service 抛的是现成中文,如"数量N不在范围内[1,8]"——直接透传到 human_readable_message?还是收敛成固定文案?)
2. **`ValueError` → GraphQL 错误的映射**:现有 submit resolver 对 ValueError 的处理方式 vs user 桥的 `map_app_errors`(AppException 体系)——桥接层是否把 ValueError 包成 ValidationError,error_kind 用什么(Rust 是 `INVALID_CONTENT`)。
3. **paper 校验差异**:Python 比 Rust 严(非空列表 + 整数 id + answer_str≤4096);前端的 paperJson 结构是嵌套对象(`{mainQuestionnaire:..., extraQuestionnaire:...}`)而非列表——**现有 validate_paper 可能直接拒掉前端的真实载荷,需核实并对齐**。⚠️ 高风险点。
4. **Dojin 回读的 EditDoujin 流程**:前端有编辑已提交同人作品的页面,确认其 mutation/query 用法是否在上表覆盖内。
5. 测试策略:SDL 契约回归(10 个签名钉死,同 `test_user_account_mutations.py`)+ resolver 单测(token→user_id、meta 服务端生成)+ paper 真实载荷用例。

## 6. 旧↔新实现对照(迁移规范 §9 要求)

| 旧实现(Rust) | 新实现(Python,本桥) |
|---|---|
| `gateway/src/schema.rs:264-286` 5 个 mutation | `src/api/graphql/resolvers/submit.py` 新增 5 个前端名 resolver |
| `gateway/src/submit_handler.rs` JWT 验证+meta 生成(331-347 等) | resolver 内 `decode_vote_token` + 服务端造 `SubmitMetadata` |
| `gateway/src/schema.rs:95-117` 5 个 getter | 同文件新增 5 个 `getSubmit*Vote(voteToken)` resolver |
| submit-handler 校验/入库 | `SubmitService`(已等价,不动) |
