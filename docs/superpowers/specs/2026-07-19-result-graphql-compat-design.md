# Result 前端契约层 + 问卷语义 code + 分段统计 —— 设计稿

> 状态：**设计已定稿,可进入 writing-plans**
> 日期：2026-07-19 · 分支 `feat/result-graphql-compat` · 承接 B-050 v1（记票重写已合入 main）

---

## 一、背景：问题比"缺几个后补功能"大得多

对 result 前端（`Touhou-Vote/packages/result`）与本后端做了双向审计，结论是**两者根本不是同一套 API**：

- 前端调用 12 个 `query*` 名（`queryCharacterRanking` / `queryCPSingle` / …），后端只有 `ranking` / `trends` / `globalStats` / … 9 个不同名字。
- 后端所有 result 字段返回**不可子选的 `JSON` 标量**，而前端查询全是 `{ global { … } entries { … } }` —— **即使改名也过不了 schema 校验**。
- 字段名/结构不同：`firstVoteCount`↔`favorite_vote_count`、`nameJpn`↔`name_jp`、`characterType`↔`type`；male 三个扁平字段 ↔ 后端嵌套对象；`voteCountLast1/2` ↔ 后端 `rank[]` 数组。
- 参数不同：前端按 **rank** 取单条（后端只按 name）、传 `voteStart` / `query`（后端无此参数）、问卷传**列表**（后端收单个）。

**实测坐实**（测试机 `154.37.215.62:18000`）：
```
queryCharacterRanking → "Cannot query field 'queryCharacterRanking' on type 'Query'."
```
测试机 nginx 的 `/res-be/` 已指向本后端 → **结果页目前一个都跑不起来**。

### 关键有利条件

`src/api/graphql/types.py:25-198` 已存在一整套 typed strawberry 结果类型（`RankingEntry` / `CPRankingEntry` / `CharacterOrMusicRanking`（含 `global_ = strawberry.field(name="global")`）/ `Trends` / `ResultGlobalStats` / `CompletionRate` / `CachedQuestionItem` / `CovoteItem` …），注释写着 "align with Rust gateway result_query.rs"，**全仓零引用**。其字段名正是前端要的那套。

> **等于契约层的类型早已写好，只差一个 resolver 去适配 compute 的 dict 输出。**

---

## 二、本轮范围

**做**：A 契约层 · B 问卷语义 code · C1 问卷 feed + 分段统计 · C4 covote 修正
**不做（记 BACKLOG）**：C2 上届对比 · C3 trend 存储改造 · 高级搜索 DSL

---

## 三、A. GraphQL 结果契约层

新增 `src/api/graphql/resolvers/result_compat.py`，类 `ResultCompatQuery`，挂进根 `Query` 的基类列表（`schema.py` 是多继承拼装）。

**12 个字段**：`queryCharacterRanking` / `queryMusicRanking` / `queryCPRanking` / `queryCharacterTrend` / `queryMusicTrend` / `queryCharacterSingle` / `queryMusicSingle` / `queryCPSingle` / `queryGlobalStats` / `queryQuestionnaire` / `queryQuestionnaireTrend` / `queryCompletionRates`。

**返回类型**：直接复用 `types.py` 里那套现成类型。适配器（dict → type）照 `types.py` 既有的 `pydantic_to_graphql_*` 手写转换函数风格。
⚠️ 这些类型**每个字段都必填、无默认值**（`RankingEntry` 34 个字段；`album` / `CPItem.c` 虽 Optional 但无默认，仍须显式传 `None`），适配器必须逐字段构造。

**行为约定**（已与用户确认）：
- **`voteYear`**：前端写死 `11`，后端数据在 `settings.vote_year`。策略 = **该年有数据就用，没有则回落 `settings.vote_year` 并记一条日志**。前端不用改。
- **`query`（高级搜索 DSL）**：必须**接受**此参数（否则 schema 校验即挂）。空 / `None` / `"NONE"` → 返回全量榜（正确）；**非空 → 明确报错「高级搜索暂未实现」**。
  > 决策理由：静默忽略会返回**未筛选**的数字，用户以为是筛选结果 —— 宁可可见地失败，也不给看似合理实则错误的数据。
- **`rank` 取单条**：用**唯一序号**（`rank[0].rank`，即排序后的 1-based 序位），**不用会并列的 `display_rank`**。
- **错误处理**：走 `map_app_errors`。现有 `ResultQuery` 是唯一没用它的 resolver，导致它那句 "run compute-results first" 被全局兜底吞成 `INTERNAL_ERROR` —— 新层不要重蹈。
- **旧的 JSON 版查询保留**（加法式，不破坏任何现有调用方）。

### A.1 适配器需要、但 compute 目前不产出的小缺口

| 缺口 | 现状 | 处理 |
|---|---|---|
| `CovoteItem.cs` / `.mi` | `compute_covote` 只产 `m00/m01/m10/m11/cv` | **本轮置 0.0 并加注释说明未实现**（前端 connect 页仍是占位，无消费方；补算留待前端页面落地时一并做） |
| `CompletionRateItem.num_complete` / `.total` | `compute_completion_rates` 只返回 rate 分数 | compute 侧改为同时返回分子/分母 |
| `CachedQuestionItem` 的性别交叉（`total_male` / `total_female`，及 `CachedQuestionAnswerItem.male_votes` / `female_votes`） | `compute_paper_results` 完全不算性别 | 由 C1 的分段能力提供 |
| `ResultGlobalStats.vote_year` | compute 不产 | 适配器补上 |
| `RankingEntry.*_last_1` / `*_last_2`（8 个历史字段） | 历史被 `historical={}` 关掉（C2 未做） | **本轮一律填 0**，C2 落地后才有真值 |

---

## 四、B. 问卷语义 code（地基）

### 为什么必须独立成列

实测线上问卷结构：**问卷 id=1,2,3 / 组 id=1,2 / 题 id=1,2,3 / 选项 id=1,2 —— 纯自增，非语义**；且内容全是占位文案（真实题目待运营录入）。
导入接口虽"尊重显式 id"，但当初导入的树没带 id；而**将来运营用 admin 嵌套编辑器录真题时，建行只会拿到自增主键**。

> 结论：语义码**不能寄生在主键上**，必须独立成列。（主键本也不该承载业务语义。）

### 设计

- **只给 `question_def` 与 `option_def` 增加 `code` 列**（`String(16)`，可空、建索引）。
  - `questionnaire_def` 已有语义 `key`（`main_required` / `extra_1` …），不再加。
  - `question_group_def` **不加** —— 前端契约只按题码（`q11011`）和选项码（`1101101`）寻址，组码无消费方。
- **码制**（权威需求文档定义，前端 legacy `questionnaire.ts:6-13` 有完整说明）：
  `[1位 问卷类型][1位 子分类][2位 问题组][1位 题序][2位 选项序]`
  → 题码 5 位（如 `11011`），选项码 7 位（如 `1101101`）。
- **写入路径**：导入接口与 admin 编辑器都要能携带/设置 `code`。
- **配置改按 code**：`gender_question_id` / `gender_male_value` / `gender_female_value` 从"字符串 `q11011` / `male` / `female`"改为**按 code 匹配**（题码 + 选项码）。
- **`q` 前缀约定**：前端线上格式是 `q11011`（问卷题）与裸数字选项码。契约层**接受两种写法**（可选 `q` 前缀），对外**输出前端格式**（`questionId` 带 `q`）。

### 现成的真实数据源（供运营录真题时用）

前端 legacy `Touhou-Vote/packages/shared/data/questionnaire.ts` 含**真实问卷内容 + 真实 7 位 id**，是导入真题的现成源，不必手敲。（本轮不做导入，仅记录。）

---

## 五、C1. 问卷 feed + 分段统计（把"性别"泛化成"按问卷回答切分"）

### C1.1 换数据源

`ComputeDAO.load_questionnaire_votes` 现在读**死表** `Questionnaire`（全仓无写入方）。真源二选一：

| 源 | 判断 |
|---|---|
| `raw_paper.papers_json` | ❌ 不透明 `Text`、内容异构（嵌套对象/扁平列表/`"{}"`/任意 JSON 都合法）；且 B-039 规范明确写着"统计侧也不读这张原始表"，正因如此 `validate_paper` 才不校验结构 —— 去解析它等于把那条契约反悔 |
| **`paper_answer`（B-039 结构化表）** | ✅ 结构化、`vote_id` + `vote_year` 有索引、是规范指定的继任者（`PaperAnswer` docstring：*"replaces the opaque papers_json blob"*） |

**采用 `paper_answer`。** 映射：
```
{"id": 题code, "answer": [选项code…], "answer_str": input_text}
```
（由 `active_question_id` / `selected_option_ids` 经 `code` 列翻译而来。）

**注意事项**：
- `paper_answer` 按 `vote_year` 分区 → 新的 DAO 方法要接 `vote_year` 参数（其余 `load_*_votes` 都不接参数）。
- 粒度是 **(vote_id, year, questionnaire_id, group_id)** 一行、答的题记在 `active_question_id`；**不是一题一行**。多题组会塌缩，实现时需确认前端 `activeQuestionId` 是否确为一组一题。
- `active_question_id` 可空 → 跳过空行。
- `paper_answer` **没有 `invalidated` 标志** → admin 的作废动作（B-049）触达不到问卷答案。记录此差异。
- 与 `raw_paper` 并存期：统计 `num_finished_paper` / 完成率时按 `vote_id` **去重**，避免双计。

### C1.2 把"性别"泛化成"分段"

> 用户洞察：切分（segmentation）与高级搜索的 `q11011 = 1101101` **是同一个原语** —— 都是"用问卷回答约束投票集合"，共用同一份 `vote_id → {题code: [选项code]}` 索引。

**本轮落地（几乎零额外成本）**：
- 建 `vote_id → {题code: [选项code]}` 索引（性别票本来就需要）。
- 把 `gender_map: dict[uid, "male"|"female"|"unknown"]` 泛化为 **`segment_map: dict[uid, label]`**，ranking 按 label 分别计数。**性别只是"用配置指定的那道题构造出的 segment_map"**。
- 问卷聚合**按定义驱动**：依 `question_def.type`（`Single` / `Multi` / `Input`）分派 —— 单选/多选按选项计数（多选一人贡献多个），填空收集字符串（沿用现有"滤掉『无』"的规则）。**不给每道题写死逻辑。**

**本轮不做（记 BACKLOG，与 DSL 同组）**：
- 对外的"任意问卷题 × 投票结果"通用查询 API 与前端交互。
- 全题目预聚合（244 角色 × 32 题 × 40 选项 会撑爆 Redis 榜单）→ 将来应**按需算**，不塞进现成榜。

### C1.3 契约层做投影

**域层通用、契约层专用**：前端**没有任何一处**能展示通用切分（ranking 页读扁平 `maleVoteCount` / `malePercentagePerChar` / `malePercentagePerTotal`；问卷页读 `answersCat{maleVotes, femaleVotes}`）。
→ compute 内部按 segment 算，compat 层把 `segments["male"]` **投影**成 `maleVoteCount` 等扁平字段。今天前端照常工作，将来要通用分析时后端已具备能力，不用重写。

---

## 六、C4. covote 修正

`compute_covote` 目前把 `a` / `b` 输出为**裸 8-hex id**且**不过白名单**（直接用 `item.get("id")`）。
→ 改为：**先按白名单过滤**，再配对；输出 `a` / `b` 用 `Whitelist.name_of()` 转成人名。

⚠️ **诚实提示**：前端 `characterConnect` / `musicConnect` 两个页面在 `packages/result` 里是"维护中"占位页（`&lt;template&gt;角色部门同投页面还在维护中哦&lt;/template&gt;`），本轮修好 covote 只是让**接口正确**，**不会立刻多出一个能看的页面**，需另一个仓库补前端。

---

## 七、已知限制与诚实预期

1. **C1 本轮交付的是"能力"而非"数字"**：线上问卷是占位内容 + 非语义 id，真实题目待运营录入；在那之前，性别票与问卷结果**仍会是 0**。立刻变可见的是**契约层**（排名/详情/理由等有真实数据的页面会活过来）。
2. **历史字段本轮填"无数据"哨兵 `-1`/`-1.0`**（`*_last_1` / `*_last_2`；旧网关同款 `.unwrap_or(-1)`，前端按 `< 0` 判断"有没有上届数据"，2026-07-19 fix-wave 已从最初误填的 `0`/`0.0` 改正——填 0 会让前端渲染出编造的"上届 0 票"而不是正确的"-"），上届对比真值需 C2。
3. **trend 仍是退化值**：`raw_*` 是 delete-then-insert，历史已被删除，现有 trend 实为"最后一次提交时刻"的直方图，非真实演进曲线。需 C3 改 append-only 存储。
4. **高级搜索非空 query 会明确报错**（非静默返回全量）。
5. **covote 修好但前端页面仍是占位**（见 §六）。
6. `paper_answer` 无作废标志，admin 作废不影响问卷统计。

---

## 八、验收标准

- 前端真实查询打到新后端**能通过 schema 校验并返回数据**（至少 `queryCharacterRanking` / `queryCPRanking` / `queryCharacterSingle` / `queryGlobalStats`）。
- `voteYear=11` 时回落到 `settings.vote_year` 且有日志。
- 非空 `query` 返回可辨识的「高级搜索暂未实现」错误（不是 `INTERNAL_ERROR`）。
- covote 输出人名且全部在白名单内。
- `code` 列迁移可正反向执行；配置按 code 能定位性别题（用带 code 的测试数据验证）。
- 全量测试绿；`flake8 src/` 干净（CI 只 lint `src/`）。

---

## 九、BACKLOG 补记（本轮新增/更新）

- **新增**：result 前端 ↔ 后端 GraphQL **契约层断裂**（本设计稿处理）。
- **更新 B-050-后补5（高级搜索）**：补记关键发现 —— DSL **不是"过滤已算好的榜"，而是"换一个投票子集重算榜"**，需按需子集重算能力；且与分段共用 `vote_id → 回答` 索引。
- **新增**：通用"任意问卷题 × 投票结果"交叉分析 API + 前端（与 DSL 同组，共用索引）。
- **新增（运营）**：录入真实问卷内容（可从前端 legacy `questionnaire.ts` 导入，含真实 7 位 id）。

---

## 十、v1 实现落地（2026-07-19，Task 7 收尾）

> 状态：**七个任务全部完成，全量测试绿，`flake8 src/` 干净**。本节记录最终文件清单、`code` 写入路径、配置新名、以及与本设计稿的两处刻意偏差。

### 10.1 最终文件清单

**新增**：
- `alembic/versions/0015_questionnaire_semantic_code.py`：`question_def`/`option_def` 各加 `code VARCHAR(16)` + 索引，幂等 `ADD COLUMN/INDEX IF NOT EXISTS`（Postgres-only，sqlite 测试库走 `create_all` 不经过迁移）。
- `src/api/graphql/resolvers/result_compat.py`（677 行）：`ResultCompatQuery`，12 个 `query*` 字段 + dict→strawberry 类型的适配器函数 + 三个契约层公共助手（`_resolve_vote_year`/`_reject_query_dsl`/`_map_not_computed_error`）。
- 测试：`tests/integration/test_questionnaire_code.py`、`tests/integration/test_questionnaire_feed.py`、`tests/integration/test_result_compat_ranking.py`、`tests/integration/test_result_compat_rest.py`、`tests/unit/test_compute_gaps.py`、`tests/unit/test_result_compat_schema.py`、`tests/unit/test_segment_stats.py`。

**修改**：
- `src/api/graphql/schema.py`：`Query` 多继承基类列表追加 `ResultCompatQuery`。
- `src/db_model/questionnaire_def.py`：`QuestionDef`/`OptionDef` 各加 `code: Mapped[str | None]`（`String(16)`, `nullable=True`, `index=True`）。
- `src/apps/questionnaire/importer.py`、`src/apps/questionnaire/dao.py`：整树导入 / 单条编辑各自的行构造字典加 `"code": q.get("code")` / `o.get("code")`。
- `src/apps/questionnaire/assembler.py`：`_question_out`/`_option_out` 输出加 `"code"` 键（结构查询回显）。
- `src/apps/questionnaire/admin_service.py`：`create_question`/`update_question`/`create_option`/`update_option` 改为先经显式白名单 `_pick_writable(fields, _QUESTION_WRITABLE_FIELDS | _OPTION_WRITABLE_FIELDS)` 过滤请求体，`code` 加入两个白名单。
- `src/apps/result/compute_dao.py`：`load_questionnaire_votes` 从死表 `Questionnaire` 改读 `paper_answer`（新增 `vote_year` 参数），经 `question_def.id→code`/`option_def.id→code` 两张映射表翻译成语义码；缺 code 的问题行/选项分别计数，汇总成一条 debug 日志。
- `src/apps/result/compute.py`：`compute_gender_map`→`build_segment_map`；`compute_ranking`/`compute_cp_ranking` 新增 `segments` 输出（`_segment_breakdown`/`_legacy_gender_projection` 两个新 helper）；`compute_completion_rates` 返回 `{category: {rate, num_complete, total}}`；`compute_paper_results` 签名简化并新增性别交叉字段；`compute_covote` 新增 `whitelist` 参数、置零 `cs`/`mi`。
- `src/apps/result/compute_service.py`：接线以上签名变化（`build_segment_map` 用 `settings.gender_*_code` 构造 `label_by_option`；`load_questionnaire_votes(vote_year)`；`compute_paper_results(q_votes, segment_map)`；`compute_covote(votes, whitelist, top_k=100)`）。
- `src/common/config.py`：新增 `gender_question_code`/`gender_male_option_code`/`gender_female_option_code`；旧三项 `gender_question_id`/`gender_male_value`/`gender_female_value` 保留但标 deprecated，`compute_service` 不再读取。

### 10.2 `code` 的写入路径

```
运营录题 / 导入 JSON 里的 "code" 字段
        │
        ├─ 整树导入  importer.parse_structure_tree()  → qn_row["code"] / o_row["code"]
        ├─ 单条编辑  QuestionnaireDAO.create_question/update_question/
        │            create_option/update_option()    → q_kwargs["code"] / o_kwargs["code"]
        └─ admin API  QuestionnaireAdminService.*      → _pick_writable() 白名单放行 "code"
                        │
                        ▼
              db_model.QuestionDef.code / OptionDef.code
              （String(16)，nullable，索引；migration 0015）
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
   assembler._question_out/    ComputeDAO.load_questionnaire_votes()：
   _option_out → 结构查询回显    QuestionDef.id→code / OptionDef.id→code
   （admin 编辑器读回）           两张映射表，把 paper_answer 的
                                 active_question_id/selected_option_ids
                                 翻译成语义 code，喂给 compute 层
```

关键约束：主键（自增 id）永远不承载语义；`code` 独立可空列，缺失时该题/选项在问卷统计里被跳过并计入调试日志（不是静默丢弃、也不报错），运营录入真题后自然补全。

### 10.3 新配置项

| 新字段 | 默认值 | 用途 |
|---|---|---|
| `gender_question_code` | `"11011"` | 性别题的语义码（裸码，无 `q` 前缀） |
| `gender_male_option_code` | `"1101101"` | "男"选项的语义码 |
| `gender_female_option_code` | `"1101102"` | "女"选项的语义码 |

旧三项 `gender_question_id`（`"q11011"`）/`gender_male_value`（`"male"`）/`gender_female_value`（`"female"`）**标记 deprecated、保留一个发布周期**，`compute_service.py` 不再读取；下个发布周期确认无遗留读取方后可删除。

### 10.4 与设计稿的两处偏差

**偏差一：问卷聚合按答案形状分派，不按 `question_def.type` 分派。**

设计稿 §五「C1.2」原文写"问卷聚合按定义驱动：依 `question_def.type`（`Single`/`Multi`/`Input`）分派"。实现改为按**答案形状**分派（`compute_paper_results`：`answer` 是非空 list → 按选项计数；`answer_str` 非空 → 收字符串）。理由：`paper_answer` 产出的 `answer`/`answer_str` 形状本身已经完全区分单选/多选（list）与填空（字符串）——单选多选在这一层的处理逻辑其实相同（都是"对 list 里每个选项计数"，多选自然贡献多个计数，无需额外分支）；引入 `question_def.type` 映射不会改变任何分支行为，只会多一次 DB 往返换取一个从未被用到的判断依据。保留至今没有反例：三种题型在 `paper_answer` 里的形状互斥且稳定。

**偏差二（计划纠错）：`queryQuestionnaireTrend` 返回 `[Trends!]!`，不是设计稿/计划写的 `QueryQuestionnaireResponse`。**

设计稿与其后的实施计划都称 `queryQuestionnaireTrend` 是 `queryQuestionnaire` 的"趋势版别名"，字面推导其返回类型也应是 `QueryQuestionnaireResponse`。Task 7 用真实前端源码核对（`Touhou-Vote/packages/result/src/pages/QuestionnaireDetail.vue`）发现前端实际读取 `result.value.queryQuestionnaireTrend[0].trend`/`[0].trendFirst`——按**数组下标**取值，形状是 `[Trends!]!`，与 `queryCharacterTrend`/`queryMusicTrend` 同构；旧 Rust 网关的 schema 定义与此一致。若按计划字面实现 `QueryQuestionnaireResponse`（`{entries: [...]}`），前端会因形状不匹配直接 schema 校验失败，整个"调查问卷"页面挂掉。已按真实前端契约实现为 `[Trends!]!`，长度与入参 `questionIds` 一致、内容全部为空序列（问卷没有真正的时间维度，见 §七「已知限制」第 3 条），并在 resolver docstring 里记录了这次纠错。详见 CHANGELOG。

### 10.5 端到端验收结果

- `python3 -m pytest tests/ -q` → **462 passed, 1 skipped**（skip 项依赖可选 `pymongo`，与本轮无关）。
- `python3 -m flake8 src/` → exit 0。
- Schema 里 12 个 `query*` 字段的 SDL 与前端 `.vue` 源码逐个字段/参数核对（14 个前端文件、12 个查询名），**零漂移**：字段名、参数、`queryCharacterTrend`/`queryMusicTrend`/`queryQuestionnaireTrend` 的数组下标消费模式全部对齐。
- 实际执行前端原文 `queryCharacterRanking` 查询（`characterCompare.vue` 版本）against 内存 sqlite + 真实 compute 管线种子数据，验证 `voteYear: 11`（前端硬编码）正确回落到 `settings.vote_year`（测试用 2026）并返回真实 `global`/`entries` 数据，schema 校验通过、无 error。
