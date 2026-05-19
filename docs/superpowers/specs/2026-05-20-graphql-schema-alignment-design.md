# GraphQL Schema 对齐设计（前后端 GQL 查漏补缺）

> 创建日期：2026-05-20
> 最后更新：2026-05-20
> 作者：Claude（brainstorming 流程产物）
> 关联文档：`docs/BACKLOG.md`

---

## 一、背景

后端 GraphQL schema（Strawberry）与前端实际发出的 GQL 请求存在三类不匹配：

1. **scalar 缺失**：前端使用 `DateTimeUtc` scalar，后端未注册，导致所有带 `voteStart` 参数的 result 查询直接报错
2. **字段名不对齐**：result 查询字段名（`queryCharacterRanking` 等）、submit query/mutation 名称（`getSubmitCharacterVote`、`submitCharacterVote` 等）与后端现有字段名完全不同
3. **用户认证 mutations 缺失**：前端投票页通过 GraphQL 发 `loginEmail`、`loginPhone`、`requestEmailCode` 等，后端 GraphQL 完全没有这些字段

目标：**后端适配前端**，不改前端代码。

---

## 二、涉及文件

| 文件 | 操作 |
|---|---|
| `src/api/graphql/types.py` | 新增 `DateTimeUtc` scalar + 全部强类型 result/user 类型 |
| `src/api/graphql/resolvers/result.py` | 完整重写，字段名/参数/返回类型全部对齐前端 |
| `src/api/graphql/resolvers/submit.py` | 重命名字段、修改 input 类型名、对齐 `voteToken` 参数 |
| `src/api/graphql/resolvers/user.py` | 新建，实现所有 user mutations + userTokenStatus query |
| `src/api/graphql/schema.py` | 注册 UserMutation |

---

## 三、scalar 对齐

注册自定义 `DateTimeUtc` scalar，映射到 Python `datetime`：

```python
from datetime import datetime
import strawberry

DateTimeUtc = strawberry.scalar(
    datetime,
    name="DateTimeUtc",
    description="UTC datetime in ISO 8601 format",
    serialize=lambda v: v.isoformat(),
    parse_value=lambda v: datetime.fromisoformat(v),
)
```

在 `strawberry.Schema` 里通过 `scalar_overrides` 注册。

---

## 四、Result GraphQL 字段对齐

### 4.1 新字段命名表

| 前端调用 | 参数（前端） | 返回类型 |
|---|---|---|
| `queryCharacterRanking(query, voteStart, voteYear)` | `query: String, voteStart: DateTimeUtc!, voteYear: Int!` | `CharacterOrMusicRanking` |
| `queryMusicRanking(query, voteStart, voteYear)` | 同上 | `CharacterOrMusicRanking` |
| `queryCPRanking(query, voteStart, voteYear)` | 同上 | `CPRanking` |
| `queryCharacterSingle(voteStart, voteYear, rank, query)` | `voteStart: DateTimeUtc!, voteYear: Int!, rank: Int!, query: String` | `RankingEntry` |
| `queryMusicSingle(...)` | 同上 | `RankingEntry` |
| `queryCPSingle(...)` | 同上 | `CPRankingEntry` |
| `queryCharacterTrend(voteStart, voteYear, names)` | `voteStart: DateTimeUtc!, voteYear: Int!, names: [String!]!` | `[Trends!]!` |
| `queryMusicTrend(...)` | 同上 | `[Trends!]!` |
| `queryCPTrend(voteStart, voteYear, ranks)` | `voteStart: DateTimeUtc!, voteYear: Int!, ranks: [Int!]!` | `[Trends!]!` |
| `queryGlobalStats(voteStart, voteYear, query)` | `voteStart: DateTimeUtc!, voteYear: Int!, query: String` | `GlobalStats` |
| `queryCompletionRates(voteStart, voteYear, query)` | 同上 | `CompletionRate` |
| `queryQuestionnaire(voteStart, voteYear, query, questionsOfInterest)` | `voteStart: DateTimeUtc!, voteYear: Int!, query: String, questionsOfInterest: [String!]!` | `QueryQuestionnaireResponse` |
| `queryQuestionnaireTrend(voteStart, voteYear, questionIds, query)` | `voteStart: DateTimeUtc!, voteYear: Int!, questionIds: [String!]!, query: String` | `[Trends!]!` |
| `queryCharsCovote(voteStart, voteYear, query, topK)` | `voteStart: DateTimeUtc!, voteYear: Int!, query: String, topK: Int!` | `CovoteResponse` |
| `queryMusicsCovote(...)` | 同上 | `CovoteResponse` |

**注意**：`voteStart: DateTimeUtc!` 参数由前端传入但后端 DAO 按 `vote_year: Int!` 查询 Redis key，`voteStart` 用于筛选/验证（保留兼容性，实际查询以 `vote_year` 为主键）。

### 4.2 新强类型

对齐 Rust `result_query.rs` 里的结构体：

```python
@strawberry.type
class VotingTrendItem:
    hrs: int
    cnt: int

@strawberry.type
class RankingGlobal:
    total_unique_items: int
    total_first: int
    total_votes: int
    average_votes_per_item: float
    median_votes_per_item: float

@strawberry.type
class RankingEntry:
    rank: int
    rank_last_1: int
    rank_last_2: int
    display_rank: int
    name: str
    vote_count: int
    vote_count_last_1: int
    vote_count_last_2: int
    first_vote_count: int
    first_vote_count_last_1: int
    first_vote_count_last_2: int
    first_vote_percentage: float
    first_vote_percentage_last_1: float
    first_vote_percentage_last_2: float
    first_vote_count_weighted: int
    character_type: str
    character_origin: str
    first_appearance: str
    album: Optional[str]
    name_jpn: str
    vote_percentage: float
    vote_percentage_last_1: float
    vote_percentage_last_2: float
    first_percentage: float
    male_vote_count: int
    male_percentage_per_char: float
    male_percentage_per_total: float
    female_vote_count: int
    female_percentage_per_char: float
    female_percentage_per_total: float
    trend: list[VotingTrendItem]
    trend_first: list[VotingTrendItem]
    reasons: list[str]
    num_reasons: int

@strawberry.type
class CPItem:
    a: str
    b: str
    c: Optional[str]

@strawberry.type
class CPRankingEntry:
    rank: int
    display_rank: int
    cp: CPItem
    a_active: float
    b_active: float
    c_active: float
    none_active: float
    vote_count: int
    first_vote_count: int
    first_vote_percentage: float
    first_vote_count_weighted: int
    vote_percentage: float
    first_percentage: float
    male_vote_count: int
    male_percentage_per_char: float
    male_percentage_per_total: float
    female_vote_count: int
    female_percentage_per_char: float
    female_percentage_per_total: float
    trend: list[VotingTrendItem]
    trend_first: list[VotingTrendItem]
    reasons: list[str]
    num_reasons: int

@strawberry.type
class CharacterOrMusicRanking:
    entries: list[RankingEntry]
    global_: RankingGlobal  # strawberry field name = "global"

@strawberry.type
class CPRanking:
    entries: list[CPRankingEntry]
    global_: RankingGlobal  # strawberry field name = "global"

@strawberry.type
class Trends:
    trend: list[VotingTrendItem]
    trend_first: list[VotingTrendItem]

@strawberry.type
class GlobalStats:
    vote_year: int
    num_vote: int
    num_char: int
    num_music: int
    num_cp: int
    num_doujin: int
    num_male: int
    num_female: int

@strawberry.type
class CompletionRateItem:
    name: str
    rate: float
    num_complete: int
    total: int

@strawberry.type
class CompletionRate:
    vote_year: int
    items: list[CompletionRateItem]

@strawberry.type
class CachedQuestionAnswerItem:
    aid: str
    total_votes: int
    male_votes: int
    female_votes: int

@strawberry.type
class CachedQuestionItem:
    question_id: str
    answers_cat: list[CachedQuestionAnswerItem]
    answers_str: list[str]
    total_answers: int
    total_male: int
    total_female: int

@strawberry.type
class QueryQuestionnaireResponse:
    entries: list[CachedQuestionItem]

@strawberry.type
class CovoteItem:
    a: str
    b: str
    cs: float  # chi_square
    mi: float  # mutual_info
    cv: float  # co-vote rate
    m00: int
    m01: int
    m10: int
    m11: int

@strawberry.type
class CovoteResponse:
    items: list[CovoteItem]
```

### 4.3 DAO 适配

现有 `ResultDAO` 返回 `dict`，需要在 resolver 里将 dict 转为上述强类型对象。转换逻辑写在 `resolvers/result.py` 里（`_dict_to_ranking_entry(d) -> RankingEntry` 等辅助函数），不改 DAO。

**缺失字段的默认值策略**：Redis 里存的计算结果可能缺少某些字段（如历史届次 `rank_last_1`），用 `d.get("rank_last_1", 0)` 取默认值，不崩溃。

---

## 五、Submit GraphQL 字段对齐

### 5.1 Query 字段重命名

| 前端调用 | 当前后端字段 | 参数变化 |
|---|---|---|
| `getSubmitCharacterVote(voteToken)` | `getCharacterSubmit(voteId)` | 参数 `voteToken: String!` |
| `getSubmitMusicVote(voteToken)` | `getMusicSubmit(voteId)` | 同上 |
| `getSubmitCPVote(voteToken)` | `getCpSubmit(voteId)` | 同上 |
| `getSubmitPaperVote(voteToken)` | `getPaperSubmit(voteId)` | 同上 |
| `getSubmitDojinVote(voteToken)` | `getDojinSubmit(voteId)` | 同上 |

参数改为 `vote_token: str`，resolver 内部用 `AuthProvider.decode_vote_token(vote_token)` 取出 `user_id`，再传给 service。

### 5.2 Mutation 字段重命名 + input 类型重命名

| 前端 mutation | 前端 input 类型 | 当前后端 | 前端 content 结构 |
|---|---|---|---|
| `submitCharacterVote(content)` | `CharacterSubmitGQL` | `submitCharacter(input)` / `CharacterSubmitMutationInput` | `{voteToken, characters: [{id, first, reason}]}` |
| `submitMusicVote(content)` | `MusicSubmitGQL` | `submitMusic(input)` / `MusicSubmitMutationInput` | `{voteToken, musics: [{id, first, reason}]}` |
| `submitCPVote(content)` | `CPSubmitGQL` | `submitCp(input)` / `CPSubmitMutationInput` | `{voteToken, cps: [{idA, idB, idC, active, first, reason}]}` |
| `submitPaperVote(content)` | `PaperSubmitGQL` | `submitPaper(input)` / `PaperSubmitMutationInput` | `{voteToken, paperJson}` |
| `submitDojin(content)` | `DojinSubmitGQL` | `submitDojin(input)` / `DojinSubmitMutationInput` | `{voteToken, dojins: [...]}` |

**Input 类型变化**：
- `voteToken: str` 替代原来的 `meta.vote_id`
- `characters`/`musics`/`cps`/`dojins` 字段名不变
- `PaperSubmitGQL` 里前端用 `paperJson`（不是 `papersJson`）

Submit mutation resolver 内部通过 `voteToken` 解码取 `user_id` 作为 `vote_id`，其余逻辑不变。

---

## 六、User GraphQL mutations + query

新建 `src/api/graphql/resolvers/user.py`，内部调用已有的 `UserService`。

### 6.1 UserType（对应 Rust `Voter`）

```python
@strawberry.type
class UserType:
    username: Optional[str]
    pfp: Optional[str]
    password: bool
    phone: Optional[str]
    email: Optional[str]
    thbwiki: bool
    patchyvideo: bool
    created_at: datetime  # maps to DateTimeUtc in schema
```

### 6.2 LoginResult

```python
@strawberry.type
class LoginResult:
    user: UserType
    session_token: str
    vote_token: str
```

### 6.3 UserQuery

```python
@strawberry.type
class UserQuery:
    @strawberry.field
    async def user_token_status(self, user_token: str, vote_token: Optional[str] = None) -> bool:
        # 调用 UserService.token_status
```

### 6.4 UserMutation

```python
@strawberry.type
class UserMutation:
    @strawberry.mutation
    async def login_email(self, email: str, nickname: Optional[str], verify_code: str) -> LoginResult: ...

    @strawberry.mutation
    async def login_phone(self, phone: str, nickname: Optional[str], verify_code: str) -> LoginResult: ...

    @strawberry.mutation
    async def login_email_password(self, email: str, password: str) -> LoginResult: ...

    @strawberry.mutation
    async def request_email_code(self, email: str) -> bool: ...

    @strawberry.mutation
    async def request_phone_code(self, phone: str) -> bool: ...

    @strawberry.mutation
    async def update_email(self, user_token: str, email: str, verify_code: str) -> bool: ...

    @strawberry.mutation
    async def update_phone(self, user_token: str, phone: str, verify_code: str) -> bool: ...

    @strawberry.mutation
    async def update_nickname(self, user_token: str, new_nickname: str) -> bool: ...

    @strawberry.mutation
    async def update_password(
        self, user_token: str, old_password: Optional[str], new_password: str
    ) -> bool: ...
```

**实现方式**：每个 mutation 构造对应的 `*Request` Pydantic schema，调用 `UserService` 方法，捕获 `AppException` 转为 GraphQL error（保持 `error_kind`/`human_readable_message` 在 extensions 里，与前端的 `error.graphQLErrors[0].extensions.error_kind` 兼容）。

`Meta` 的 `user_ip` 从 Strawberry `info.context["request"].client.host` 取，`vote_id` 对 user mutations 不适用（设为空字符串）。

### 6.5 schema.py 更新

```python
@strawberry.type
class Query(SubmitQuery, ResultQuery, UserQuery):
    pass

@strawberry.type
class Mutation(SubmitMutation, UserMutation):
    pass

schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    scalar_overrides={datetime: DateTimeUtc},
)
```

---

## 七、错误处理

- result 查询：`ResultNotComputedError` → Strawberry `StrawberryException`，HTTP 200 body `errors: [{message: "..."}]`
- user mutations：`AppException` → `raise strawberry.exceptions.StrawberryException(message=exc.message)`，并在 `extensions` 里附加 `error_kind` 和 `human_readable_message`（前端依赖这两个字段做错误提示）
- DAO 缺字段时 `.get("field", default)` 取默认值，不 crash

---

## 八、不做的事（YAGNI）

- 不补 `listVotableCharacters`/`listVotableWorks`/`listVotableMusics`（旧 Rust vote_data，Python 侧有 REST 替代）
- 不补 `serverDate` query（前端 result 包不调用）
- 不改 DAO 层（只在 resolver 里做 dict → type 转换）
- 不写迁移脚本（纯 GraphQL schema 变更，无 DB 改动）
