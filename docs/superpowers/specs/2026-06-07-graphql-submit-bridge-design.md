# GraphQL Submit 桥接设计(投票提交路径适配前端契约)

> 定稿:2026-06-07(brainstorming 全流程逐项确认)。分支 `feat/graphql-submit-bridge`。
> 迁移主题文档:`docs/migration/graphql-submit-bridge.md`(背景与契约勘探);本文件是实现依据。
> 模式同已上线的 user 模块桥接(登录 PR #3 / 账号管理 PR #4):**业务逻辑不动,只加 GraphQL 桥**。

## 1. 目标 / 非目标

**目标**
- 前端(`Touhou-Vote/packages/vote`)的 5 个投票提交 mutation 与 5 个回读 query 在 Python 后端可用,前端零改动。
- 修复 `validate_paper` 的错误假设(会拒掉前端真实载荷)。
- 错误按既有 extensions 契约返回,中文校验消息透传给用户。

**非目标**
- 不删除/不修改现有自创 GraphQL 字段(`submitCharacter(input:)` ×5、`getCharacterSubmit(voteId)` ×7)——用户决策"以防万一"保留。其无鉴权 getter 的暴露面与移除条件已记 `docs/migration/graphql-submit-bridge.md` §4。
- 不动 REST `/api/v1/{character,music,cp,paper,dojin}/` 行为(validate_paper 修复除外,它是 bug fix,使 REST 同步受益)。
- 不做前端改动。

## 2. 新增文件与改动面

```
src/api/graphql/
├── errors.py                      ← 新:从 resolvers/user.py 下沉 map_app_errors /
│                                       _extensions / _HUMAN_READABLE_MESSAGES(纯搬家)
├── resolvers/
│   ├── user.py                    ← 仅改 import 指向 errors.py,行为不变
│   ├── submit.py                  ← 一字不动
│   └── submit_bridge.py           ← 新:本设计全部新代码
└── schema.py                      ← Mutation 多继承 SubmitBridgeMutation,
                                        Query 多继承 SubmitBridgeQuery
src/common/exceptions.py           ← AppException 增可选 human_readable_message kwarg
src/apps/submit/service.py         ← 仅 validate_paper 一个函数体重写
```

## 3. GraphQL 契约(精确,以前端 gql 文档为准)

### 3.1 Mutations(5 个,均返回 `Boolean!`,成功 = `true`)

| 字段 | 入参 |
|---|---|
| `submitCharacterVote` | `content: CharacterSubmitGQL!` |
| `submitMusicVote` | `content: MusicSubmitGQL!` |
| `submitCPVote` | `content: CPSubmitGQL!` |
| `submitPaperVote` | `content: PaperSubmitGQL!` |
| `submitDojin` | `content: DojinSubmitGQL!` |

顶层输入类型(strawberry `@strawberry.input(name="…GQL")` 显式定名,保大小写):

```graphql
input CharacterSubmitGQL { voteToken: String!  characters: [CharacterSubmitInput!]! }
input MusicSubmitGQL     { voteToken: String!  musics: [MusicSubmitInput!]! }       # 注意 musics 复数
input CPSubmitGQL        { voteToken: String!  cps: [CPSubmitInput!]! }
input PaperSubmitGQL     { voteToken: String!  paperJson: String! }
input DojinSubmitGQL     { voteToken: String!  dojins: [DojinSubmitItemGQL!]! }

enum DojinType { MUSIC VIDEO DRAWING SOFTWARE ARTICLE CRAFT OTHER }
input DojinSubmitItemGQL {
  title: String!  author: String!  url: String!
  dojinType: DojinType!  reason: String!  imageUrl: String
}
```

- 条目级输入**复用现有** `CharacterSubmitInput` / `MusicSubmitInput` / `CPSubmitInput`(types.py,字段完全吻合:`id/first/reason`、`idA/idB/idC/active/first/reason`)。前端文档只点名顶层 `…GQL` 类型,条目类型名无契约约束。
- dojin 条目新建 `DojinSubmitItemGQL`(现有 `DojinSubmitInput.dojin_type` 是 str,前端发枚举)。**入库存枚举名字符串**(`"MUSIC"`),与回读 JSON 一致,round-trip 成立。

### 3.2 Queries(5 个,均以 voteToken 鉴权)

```graphql
getSubmitCharacterVote(voteToken: String!): CharacterSubmitRestQuery!
getSubmitMusicVote(voteToken: String!): MusicSubmitRestQuery!
getSubmitCPVote(voteToken: String!): CPSubmitRestQuery!
getSubmitDojinVote(voteToken: String!): DojinSubmitRestQuery!
getSubmitPaperVote(voteToken: String!): PaperSubmitRestQuery!

type CharacterSubmitRestQuery { characters: [CharacterSubmitType!]! }
type MusicSubmitRestQuery     { music: [MusicSubmitType!]! }        # 单数!提交 musics/回读 music 是旧契约怪癖,照抄
type CPSubmitRestQuery        { cps: [CPSubmitType!]! }
type DojinSubmitRestQuery     { dojins: [DojinSubmitType!]! }
type PaperSubmitRestQuery     { papersJson: String! }
```

- 条目级输出复用现有 `*SubmitType`(字段名已核对:`id/first/reason`、`idA/...`、`dojinType/url/title/author/reason/imageUrl`)。dojin 输出沿用现有 str 类型即可(JSON 序列化与枚举名一致,前端不校验响应类型)。
- **空结果语义**:未投过 → 空数组 / `papersJson: "{}"`(service 现行为);前端 `voteDataSource` 已兜底。不返回 null、不报错。

### 3.3 前端选择集(回归测试要覆盖)
`characters{id first reason}`、`music{id first reason}`、`cps{idA idB idC active first reason}`、`dojins{dojinType url title author reason imageUrl}`、`papersJson`。

## 4. resolver 数据流(5 个 mutation 共用骨架)

```
decode_vote_token(content.voteToken)        # 失败 → INVALID_TOKEN(见 §6)
        ↓ user_id(= vote_id,不信任客户端)
rate_limit(user_id) + 提交锁(user_id)        # 复用现有 rate_limit/_acquire_vote_lock,
        ↓                                    # key 改为 token 解出的 user_id
服务端造 SubmitMetadata(vote_id=user_id,
    created_at=now, user_ip=请求IP,          # user_ip 经 _client_ip_from_info(同 user 桥)
    vote_token 不落 meta)
        ↓
SubmitService.submit_*()                     # ValueError → INVALID_CONTENT(见 §6)
        ↓
return True
```

Query 同理:decode → user_id → `SubmitService.get_*_submit(user_id)` → 组装 RestQuery 类型(丢弃 meta,只回条目)。

## 5. validate_paper 修复(service 层,bug fix)

现状(`src/apps/submit/service.py`)要求"非空列表 + 每项整数 id + answer_str≤4096"——
是按想象的旧格式写的;前端真实载荷是嵌套对象 `{mainQuestionnaire:{...}, extraQuestionnaire:{...}}`,
现校验必拒。统计侧(`result/compute_dao.load_questionnaire_votes`)读的是独立的 `questionnaire` 表,
不消费 `raw_paper_submit.papers_json`,故原始提交无下游结构依赖。

**新实现**:只验两条 —— ① `json.loads` 合法;② UTF-8 编码后 ≤ 256KB(`len(papers_json.encode("utf-8")) <= 256 * 1024`,防滥用存储)。
不验内部结构(问卷题目年年变,后端不与之耦合)。旧 Rust 是零校验透传,本实现是其严格改进。
REST 路径同步受益;changelog 记录行为变化。

## 6. 错误处理

| 情形 | error_kind | HTTP 语义 | human_readable_message |
|---|---|---|---|
| voteToken 缺失/坏/过期(窗口外) | `INVALID_TOKEN` | 401 | 「登录已失效，请重新登录」(沿用文案表现有条目) |
| service 校验 `ValueError` | `INVALID_CONTENT` | 422 | **ValueError 中文原文透传** |
| 提交锁冲突 | `SUBMIT_LOCKED` | 429 | 「提交处理中，请稍后再试」(文案表新增) |
| 限流 | `REQUEST_TOO_FREQUENT` | 429 | 已有 |
| 其余漏网 | 全局格式化器兜底(PR #5) | — | — |

**实现细节**
- `AppException.__init__` 增可选 `human_readable_message` kwarg(与先前加 `error_message` 同手法,向后兼容)。
- `_extensions`(搬入 errors.py 后)取值优先级:异常携带的 `human_readable_message` > `_HUMAN_READABLE_MESSAGES[kind]` > None。
- 桥接 resolver 内:`except ValueError as e: raise ValidationError("INVALID_CONTENT", details=422, human_readable_message=str(e))`。
- 提交锁:现有 GraphQL 侧 `_acquire_vote_lock` 冲突时抛的是**裸 Exception**(会被全局格式化器脱敏成 INTERNAL_ERROR)——桥接不复用该抛错行为,锁冲突必须抛 `RateLimitError("SUBMIT_LOCKED", details=429)` 走 map_app_errors。
- 前端 onError 契约:`REQUEST_TOO_FREQUENT` 特判,其余显示 `human_readable_message`——以上每行都能被正确展示。

## 7. 测试

1. **SDL 契约回归**(`tests/unit/test_submit_bridge_schema.py`):10 个字段签名 + `DojinType` 7 个枚举值 + 5 个顶层输入类型字段逐一钉死(`test_user_account_mutations.py` 模式)。
2. **resolver 单测**(假 SubmitService):
   - token→user_id 注入 meta(断言 service 收到的 vote_id == token 的 user_id,且非客户端可控);
   - 坏/过期 token → `INVALID_TOKEN`;
   - service 抛 `ValueError("多个本命")` → `INVALID_CONTENT` 且 human_readable_message=="多个本命";
   - getter 空结果 → 空数组 / `"{}"`。
3. **paper 载荷用例**:前端真实嵌套对象通过新 `validate_paper`;非法 JSON、>256KB 被拒(中文消息)。
4. **搬家防回归**:errors.py 下沉后,**直接改测试 import 指向 errors.py**(errors.py 是单一出处,user.py 不做 re-export),8 例断言不改、必须仍绿。

## 8. 旧↔新对照(迁移规范 §9)

| 旧实现(Rust) | 新实现(Python) |
|---|---|
| `gateway/src/schema.rs:264-286` 5 mutation / `:95-117` 5 query | `resolvers/submit_bridge.py` |
| gateway JWT 验证 + `generate_submit_metadata` | resolver 内 `decode_vote_token` + 服务端造 meta |
| submit-handler 校验/入库 | `SubmitService`(除 validate_paper 修复外不动) |
| Rust `validate_paper` 零校验透传 | 合法 JSON + ≤256KB(刻意差异:严格改进) |
| Rust vote_id=`thvote-{年}-{id}` 自定义 claim | Python 直接用 user_id(既有刻意差异,沿用) |

## 9. 交付物清单

- `src/api/graphql/errors.py`(下沉)+ `resolvers/user.py` import 调整
- `src/api/graphql/resolvers/submit_bridge.py`(新)+ `schema.py` 接线
- `src/common/exceptions.py`(human_readable_message kwarg)
- `src/apps/submit/service.py::validate_paper` 重写
- 测试 ×4 组(§7)
- `docs/CHANGELOG.md` + `docs/migration/graphql-submit-bridge.md` 状态更新
- PR(分支 `feat/graphql-submit-bridge`),CI 绿后交用户 review
