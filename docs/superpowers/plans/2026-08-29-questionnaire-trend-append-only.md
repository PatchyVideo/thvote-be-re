# 问卷趋势 + append-only 提交历史 实施计划(B-050-后补2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分两步交付问卷趋势——Step 1 用现有存储实现 legacy 平价的近似问卷趋势(点亮前端空图);Step 2 把提交存储改为 append-only 并将全类别 trend 升级为真实净增量曲线。

**Architecture:** Step 1(Task 1-3)只动 compute 纯函数、数据加载和契约层恒空桩,不动存储。Step 2(Task 4-9)迁移 0017 放开 `paper_answer` 约束、写路径改纯插入、新增历史加载器与净增量纯函数,替换近似 trend。两步各自独立可部署。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / Strawberry GraphQL / Alembic / Redis / pytest + fakeredis[lua]。

**Spec:** `docs/superpowers/specs/2026-08-29-questionnaire-trend-append-only-design.md`

## Global Constraints

- 仓库根 = `thvote-be-re`;所有命令在该目录执行。
- lint:`flake8 src/ --max-line-length=88` 必须干净;新代码带类型标注。
- 测试基线:当前全量 573 passed;每个 task 结束时全量 `pytest -q` 不允许出现新失败。
- 迁移编号:**0017**,`down_revision = "0016"`(0016 = `0016_candidate_sort_order`)。
- trend 输出契约(前端已锁定):稀疏 `[{"hrs": int, "cnt": int}]`,`hrs` = 相对 vote_start 的小时偏移(0-based),`cnt` = 该桶净增量(Step 2 起允许负数);前端自己补零、自己累计,**后端不得预累计**。
- 百分比/命名等沿用 compute.py 现行口径;禁止改动既有 GraphQL 字段语义。
- 提交信息用 `feat:`/`fix:`/`test:`/`docs:` 前缀,每 task 至少一次提交。

---

## Step 1:近似问卷趋势(legacy 平价)

### Task 1: 问卷数据加载增补时间戳

**Files:**
- Modify: `src/apps/result/compute_dao.py`(`load_questionnaire_votes`,~L67-110)
- Test: `tests/integration/test_compute_dao_raw.py`(追加)

**Interfaces:**
- Produces: `load_questionnaire_votes(vote_year)` 返回形状不变(`list[tuple[str, list[dict]]]`),但每个 item dict 增加键 `"ts": datetime`(该行 `paper_answer.created_at`)。既有消费方(`build_segment_map`/`compute_global_stats`/`compute_completion_rates`/`subset.build_facts`)按键取值,不受影响。

- [ ] **Step 1: 写失败测试**(追加到 `tests/integration/test_compute_dao_raw.py`;沿用该文件既有的 session/引擎 fixture 与 PaperAnswer 造数辅助——先读文件头看现有模式)

```python
async def test_questionnaire_votes_carry_row_timestamp(db_session):
    # 造:有 code 的题/选项 + 一行 paper_answer(复用本文件既有造数方式)
    ...
    votes = await ComputeDAO(db_session).load_questionnaire_votes(vote_year=12)
    [(vote_id, items)] = votes
    assert all(isinstance(i["ts"], datetime) for i in items)
```

- [ ] **Step 2: 跑测试确认失败**:`pytest tests/integration/test_compute_dao_raw.py -q -k timestamp`,预期 KeyError `'ts'`。
- [ ] **Step 3: 实现**——`load_questionnaire_votes` 组装 item dict 处(现为 `{"id": qcode, "answer": answers, "answer_str": r.input_text}`)加 `"ts": r.created_at`。
- [ ] **Step 4: 跑测试确认通过**;全量 `pytest -q` 无新失败(重点:`test_result_compute.py`/`test_advanced_search_service.py` 消费该返回值)。
- [ ] **Step 5: Commit**:`feat(result): load_questionnaire_votes 携带行时间戳 ts(问卷趋势数据前置)`

### Task 2: compute_paper_results 产出近似 trend

**Files:**
- Modify: `src/apps/result/compute.py`(`compute_paper_results`,L525-592)
- Test: `tests/unit/` 新建 `test_paper_trend.py`(若已有 compute_paper_results 单测文件则追加)

**Interfaces:**
- Consumes: Task 1 的 item `"ts"` 键。
- Produces: 新签名 `compute_paper_results(questionnaire_votes, segment_map, vote_start: datetime | None = None, total_hours: int = 0) -> dict[str, dict]`;每题结果 dict 增加 `"trend": list[dict]`(稀疏 `[{"hrs","cnt"}]`;`vote_start` 为 None 或 item 无 `"ts"` 时为 `[]`)。

- [ ] **Step 1: 写失败测试**

```python
from datetime import datetime, timezone
from src.apps.result.compute import compute_paper_results

VS = datetime(2026, 1, 1, tzinfo=timezone.utc)

def _item(qid, ts_hours):
    return {"id": qid, "answer": ["1101101"], "answer_str": None,
            "ts": VS.replace(hour=0) + timedelta(hours=ts_hours)}

def test_paper_trend_buckets_by_row_hour():
    votes = [("v1", [_item("11011", 0)]), ("v2", [_item("11011", 2)]),
             ("v3", [_item("11011", 2)])]
    res = compute_paper_results(votes, {}, vote_start=VS, total_hours=720)
    assert res["11011"]["trend"] == [{"hrs": 0, "cnt": 1}, {"hrs": 2, "cnt": 2}]

def test_paper_trend_clamps_out_of_window():
    votes = [("v1", [_item("11011", -5)]), ("v2", [_item("11011", 9999)])]
    res = compute_paper_results(votes, {}, vote_start=VS, total_hours=10)
    assert res["11011"]["trend"] == [{"hrs": 0, "cnt": 1}, {"hrs": 9, "cnt": 1}]

def test_paper_trend_sum_equals_total():
    votes = [("v%d" % i, [_item("11011", i % 7)]) for i in range(20)]
    res = compute_paper_results(votes, {}, vote_start=VS, total_hours=720)
    assert sum(t["cnt"] for t in res["11011"]["trend"]) == res["11011"]["total"]

def test_paper_trend_empty_without_vote_start():
    votes = [("v1", [_item("11011", 0)])]
    assert compute_paper_results(votes, {})["11011"]["trend"] == []
```

- [ ] **Step 2: 跑测试确认失败**(KeyError `'trend'`)。
- [ ] **Step 3: 实现**——聚合循环里增加(镜像 `compute_ranking` L164-167 的钳制与 naive-tz 处理):

```python
question_trend: dict[str, list[int]] = defaultdict(
    lambda: [0] * max(total_hours, 1))
# for 循环内、question_total[qid] += 1 之后:
ts = item.get("ts")
if vote_start is not None and ts is not None:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    bucket = max(0, min(int((ts - vote_start).total_seconds() / 3600),
                        total_hours - 1))
    question_trend[qid][bucket] += 1
# 结果组装处:
"trend": [{"hrs": h, "cnt": c}
          for h, c in enumerate(question_trend[qid]) if c > 0],
```

- [ ] **Step 4: 跑测试确认通过**;全量回归。
- [ ] **Step 5: Commit**:`feat(result): compute_paper_results 产出近似问卷趋势(按行时刻分桶,legacy 平价)`

### Task 3: 接线两个调用点 + 契约层恒空桩换真数据

**Files:**
- Modify: `src/apps/result/compute_service.py`(L126 调用点)
- Modify: `src/apps/result/advanced_search/service.py`(`_compute_filtered` 内 L245 调用点;该函数上文已有 `vote_start`/`total_hours` 局部量,直接传)
- Modify: `src/api/graphql/resolvers/result_compat.py`(`_query_questionnaire_trend_entries` L479-496 + `query_questionnaire_trend` 字段 docstring L657-690)
- Test: `tests/integration/test_result_compat_graphql.py` 或既有问卷契约测试文件(先 `grep -rn "questionnaire_trend\|questionnaireTrend" tests/` 找到现有恒空断言并改写)

**Interfaces:**
- Consumes: Task 2 的 `compute_paper_results(..., vote_start=, total_hours=)` 与结果里的 `"trend"`。
- Produces: GraphQL `queryQuestionnaireTrend(questionIds, voteYear, query)` 返回真实 `Trends(trend=[VotingTrendItem...], trend_first=[])`,DSL `query` 参数经 `_apply_advanced_search` 走子集缓存。

- [ ] **Step 1: 写失败测试**——在现有 GraphQL 集成测试文件中(沿用其 app/redis/compute fixture):造 paper_answer 数据(不同小时的 created_at)→ 跑 compute → 执行

```graphql
query { queryQuestionnaireTrend(voteYear: 12, questionIds: ["q11011"]) {
  trend { hrs cnt } trendFirst { hrs cnt } } }
```

断言 `trend` 非空且与造数分桶一致、`trendFirst == []`;另写一个带 `query: "q11011=1101101"` 的用例断言子集路径同样返回非空 trend(counts ≤ 全集)。同时把 `grep` 找到的既有"恒空"断言改为非空断言。
- [ ] **Step 2: 跑测试确认失败**(trend 为空)。
- [ ] **Step 3: 实现**:
  - `compute_service.py` L126 → `compute_paper_results(q_votes, segment_map, vote_start=vote_start, total_hours=total_hours)`;`advanced_search/service.py` L245 同样。
  - `_query_questionnaire_trend_entries` 改为(镜像 L449-476 的 entries 循环模式):

```python
svc = await _get_result_service()
year = await _resolve_vote_year(svc.result_dao, vote_year, svc.result_dao.settings)
svc = await _apply_advanced_search(svc, query, year)
await _map_not_computed_error(svc.get_global_stats(GlobalStatsQuery(vote_year=year)))
entries: list[Trends] = []
for question_id in question_ids:
    code = _strip_question_prefix(question_id)
    try:
        raw = await svc.get_questionnaire(
            QuestionnaireQuery(question_id=code, vote_year=year))
    except ResultNotComputedError:
        entries.append(Trends(trend=[], trend_first=[]))
        continue
    entries.append(Trends(
        trend=[VotingTrendItem(hrs=t["hrs"], cnt=t["cnt"])
               for t in raw.get("trend", [])],
        trend_first=[],
    ))
return entries
```

  - 更新两处 docstring:删除"恒为空/移除条件"表述,写明"近似口径(最新提交分桶,与 legacy 一致);trend_first 恒空(问卷无本命概念);真实净增量见 Step 2"。`VotingTrendItem` 若未在本文件 import,从 `src.api.graphql.types` 导入。
- [ ] **Step 4: 跑测试确认通过**;全量回归;`flake8 src/ --max-line-length=88`。
- [ ] **Step 5: 文档**——`docs/CHANGELOG.md` 加条目(Added:问卷趋势近似版;兼容性:无 schema 变化、需重跑 compute);`docs/BACKLOG.md` B-050-后补2 标"Step 1 ✅(近似)/ Step 2 进行中"。
- [ ] **Step 6: Commit**:`feat(result): queryQuestionnaireTrend 接通近似趋势(含 DSL 子集路径);docs 同步`

---

## Step 2:append-only 存储 + 真实净增量 trend

### Task 4: migration 0017(paper_answer 放开约束 + attempt 列)

**Files:**
- Create: `alembic/versions/0017_paper_answer_append_only.py`
- Test: 现有 alembic 升降级测试模式(`grep -rn "upgrade\|downgrade" tests/ | grep -i alembic` 找现有迁移测试;若无专用测试,以 Step 4 的升降级实跑为准)

**Interfaces:**
- Produces: `paper_answer` 无 `uq_paper_answer_voter_group` 约束;新列 `attempt Integer NULL`;新索引 `ix_paper_answer_vote (vote_id, vote_year)`。ORM 模型 `PaperAnswer`(`src/db_model/questionnaire_def.py:86`)同步:删 `UniqueConstraint`、加 `attempt: Mapped[int | None]`。

- [ ] **Step 1: 写迁移**

```python
"""paper_answer append-only: drop voter-group unique, add attempt batch marker

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_paper_answer_voter_group", "paper_answer", type_="unique")
    op.add_column(
        "paper_answer", sa.Column("attempt", sa.Integer(), nullable=True))
    op.create_index(
        "ix_paper_answer_vote", "paper_answer", ["vote_id", "vote_year"])


def downgrade() -> None:
    # 回滚前先清历史批次,只留每 (vote_id, vote_year, questionnaire_id,
    # group_id) 的最大 attempt 行,否则唯一约束加不回去。
    op.execute(
        """
        DELETE FROM paper_answer p USING paper_answer q
        WHERE p.vote_id = q.vote_id AND p.vote_year = q.vote_year
          AND p.questionnaire_id = q.questionnaire_id
          AND p.group_id = q.group_id
          AND COALESCE(p.attempt, 0) < COALESCE(q.attempt, 0)
        """
    )
    op.drop_index("ix_paper_answer_vote", table_name="paper_answer")
    op.drop_column("paper_answer", "attempt")
    op.create_unique_constraint(
        "uq_paper_answer_voter_group", "paper_answer",
        ["vote_id", "vote_year", "questionnaire_id", "group_id"])
```

同步 ORM:`PaperAnswer` 删 `__table_args__` 的 UniqueConstraint、加 `attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)`。注意 downgrade 的 `DELETE ... USING` 是 PostgreSQL 语法——测试库(SQLite/PG?)先看现有迁移怎么写方言分支(`grep -l "sqlite" alembic/versions/ | head`),照仓库现行做法处理;若测试全程 `Base.metadata.create_all`(不跑迁移)则只需保证 PG 语法正确。
- [ ] **Step 2: 升降级实跑**(照 `docs/architecture/database-schema-management.md` 的本地流程,或 CI 等价物):`alembic upgrade head` → `alembic downgrade 0016` → `alembic upgrade head` 三连通过。
- [ ] **Step 3: 全量回归**(ORM 变化会波及 create_all 的测试库)。
- [ ] **Step 4: Commit**:`feat(db): 0017 paper_answer append-only(删组唯一约束+attempt 批次标记+索引)`

### Task 5: SubmitDAO 写路径改纯插入

**Files:**
- Modify: `src/apps/submit/dao.py`(`_upsert` L21-62)
- Test: `tests/integration/test_submit_attempt_and_duration.py`(改写单行断言)

**Interfaces:**
- Produces: `_upsert` 不再删除旧行——每次提交插入新行,`attempt` 递增、首提 `fill_duration_ms` 冻结逻辑不变。读方 `ComputeDAO._latest_per_vote` 无需改动(本就取最新)。

- [ ] **Step 1: 改写测试**——该文件现有断言 `assert len(rows) == 1  # delete-then-insert keeps a single row`(L52 附近)改为:

```python
rows = (await session.execute(
    select(RawCharacterSubmit).where(RawCharacterSubmit.vote_id == vid)
    .order_by(RawCharacterSubmit.attempt))).scalars().all()
assert [r.attempt for r in rows] == [1, 2]          # 历史保留
assert rows[0].payload != rows[1].payload            # 两次内容都在
assert rows[1].fill_duration_ms == rows[0].fill_duration_ms  # 首提冻结
```

`test_null_first_fill_stays_null_across_resubmits` 同理改为多行断言。再补一个:三连提交后 `ComputeDAO._latest_per_vote` 只吐最新 payload。
- [ ] **Step 2: 跑测试确认失败**(当前只剩 1 行)。
- [ ] **Step 3: 实现**——`_upsert` 删除 L57 的 `await self.session.execute(delete(model)...)` 一行;docstring 重写:append-only 语义 + attempt/fill 冻结保留 + "读方取最新行,历史行服务于真实 trend 与反刷票取证(B-050-后补2)";`delete` import 若再无使用则移除。
- [ ] **Step 4: 跑测试确认通过**;全量回归(重点:`test_result_compute.py` 走 `_latest_per_vote`、admin monitor 列表测试)。
- [ ] **Step 5: Commit**:`feat(submit): 提交存储改 append-only——历史行保留,读方取最新(B-050-后补2)`

### Task 6: 问卷写路径批次化 + 读方取最新批次

**Files:**
- Modify: `src/apps/questionnaire/dao.py`(`replace_answers` L70-83、`get_answers` L85-92)
- Modify: `src/apps/result/compute_dao.py`(`load_questionnaire_votes` 行过滤)
- Test: `tests/` 中问卷提交/读取的既有测试文件(`grep -rn "replace_answers\|submitPaperV2\|get_answers" tests/ -l`)追加批次用例

**Interfaces:**
- Produces: `QuestionnaireDAO.replace_answers(vote_id, vote_year, rows)` 语义改为**追加一个新批次**(函数名保留——对调用方语义仍是"整卷替换";docstring 说明底层为 append):批内所有行 `attempt = prev_max + 1`(首批 1)。新增模块级辅助 `latest_batch(rows: list[PaperAnswer]) -> list[PaperAnswer]`:取最大 `attempt` 批;全 NULL(0017 前存量)则整组返回。`get_answers`/`load_questionnaire_votes` 经 `latest_batch` 过滤。

- [ ] **Step 1: 写失败测试**

```python
async def test_resubmit_appends_batch_and_reads_latest(db_session):
    dao = QuestionnaireDAO(db_session)
    await dao.replace_answers("v1", 12, [_row(group_id=1, opts=[11]),
                                         _row(group_id=2, opts=[21])])
    await dao.replace_answers("v1", 12, [_row(group_id=1, opts=[12])])  # 撤掉组2
    all_rows = (await db_session.execute(select(PaperAnswer))).scalars().all()
    assert len(all_rows) == 3                      # 历史批次保留
    current = await dao.get_answers("v1", 12)
    assert len(current) == 1                       # 只见最新批
    assert current[0]["selected_option_ids"] == [12]

async def test_null_attempt_legacy_rows_still_readable(db_session):
    # 直插两行 attempt=None(模拟 0017 前存量),get_answers 应整组返回
    ...
    assert len(await dao.get_answers("v-legacy", 12)) == 2
```

`load_questionnaire_votes` 侧同样加一个"改票后只计最新批"的用例(测撤答的组不再出现在 items 里)。
- [ ] **Step 2: 跑测试确认失败**。
- [ ] **Step 3: 实现**:

```python
def latest_batch(rows):
    """append-only 批次选择:取最大 attempt 批;全 NULL(0017 前存量)整组返回。"""
    attempts = [r.attempt for r in rows if r.attempt is not None]
    if not attempts:
        return list(rows)
    top = max(attempts)
    return [r for r in rows if r.attempt == top]
```

`replace_answers`:删掉 delete 语句;先 `select(func.max(PaperAnswer.attempt)).where(vote_id==, vote_year==)` 得 `prev`(None→0),插入行带 `attempt=prev + 1`。`get_answers` 与 `compute_dao.load_questionnaire_votes` 在按 vote_id 分组后套 `latest_batch`(compute_dao 从 `src.apps.questionnaire.dao import latest_batch` 复用,不复制实现)。
- [ ] **Step 4: 跑测试确认通过**;全量回归(completion/service 经 `get_answers`,自动继承)。
- [ ] **Step 5: Commit**:`feat(questionnaire): paper_answer 批次化 append-only,读方取最新批(B-050-后补2)`

### Task 7: ComputeDAO 历史加载器

**Files:**
- Modify: `src/apps/result/compute_dao.py`
- Test: `tests/integration/test_compute_dao_raw.py`(追加)

**Interfaces:**
- Consumes: Task 5/6 的多行存储。
- Produces:
  - `load_char_history() / load_music_history() / load_cp_history() -> list[tuple[str, datetime, int, list[dict]]]`——`(vote_id, created_at, attempt_coalesced, items)`,**全历史行**、未排序保证(消费方自行排序);选民排除口径与 `_latest_per_vote` 完全一致:**最新行 invalidated → 该 vote_id 全部行不返回**。
  - `load_questionnaire_history(vote_year) -> list[tuple[str, datetime, int, list[dict]]]`——每个批次一个元组,items 形状同 `load_questionnaire_votes`(含 code 映射与缺 code 跳过逻辑,提取共用私有辅助 `_answers_to_items` 避免复制)。

- [ ] **Step 1: 写失败测试**

```python
async def test_char_history_returns_all_rows_excluding_invalidated_voter(db_session):
    # v1: 两次提交;v2: 一次提交后最新行 invalidated=True
    ...
    hist = await ComputeDAO(db_session).load_char_history()
    ids = {(vid, att) for vid, _, att, _ in hist}
    assert ids == {("v1", 1), ("v1", 2)}     # v2 整体出局(与 _latest_per_vote 同口径)

async def test_questionnaire_history_one_tuple_per_batch(db_session):
    # v1 两个批次(Task 6 的 replace_answers 连提两次)
    ...
    hist = await ComputeDAO(db_session).load_questionnaire_history(12)
    assert [att for vid, _, att, _ in hist if vid == "v1"] == [1, 2]
```

- [ ] **Step 2: 跑测试确认失败**。
- [ ] **Step 3: 实现**——`_history_per_vote(rows)` 私有辅助:按 vote_id 分组、组内按 `(created_at, coalesce(attempt,0))` 升序;沿用 `_latest_per_vote` 的最新行判定,若最新行 `invalidated` 则丢整组;否则输出组内全部行(含被单独标 invalidated 的历史行——作废历史行不影响计票,与设计稿 §四一致)。三个 `load_*_history` 套用;问卷版按 (vote_id, attempt) 分批组装。
- [ ] **Step 4: 跑测试确认通过**;全量回归。
- [ ] **Step 5: Commit**:`feat(result): ComputeDAO 历史加载器(全提交序列,选民排除与 _latest_per_vote 同口径)`

### Task 8: 真实净增量 trend 纯函数 + 全链路接线

**Files:**
- Create: `src/apps/result/trend.py`
- Modify: `src/apps/result/compute.py`(`compute_ranking`/`compute_cp_ranking`/`compute_paper_results` 增加 `history` 参数)
- Modify: `src/apps/result/compute_service.py`(加载历史、传参)
- Modify: `src/apps/result/advanced_search/service.py`(`_compute_filtered` 同步:历史按子集 vote_ids 过滤后传入)
- Test: Create `tests/unit/test_net_delta_trend.py`;Modify `tests/integration/test_result_compute.py`(不变量)

**Interfaces:**
- Consumes: Task 7 的 `load_*_history` 输出。
- Produces:
  - `trend.net_delta_trends(history: list[tuple[str, datetime, int, list[dict]]], item_keys: Callable[[dict], Iterable[str]], first_flag: Callable[[dict], bool], vote_start: datetime, total_hours: int) -> dict[str, dict[str, list[dict]]]`——返回 `{key: {"trend": [...稀疏...], "trend_first": [...]}}`。`item_keys(item)` 返回该 item 的 0..n 个 canonical key(白名单外返回空;CP 用其 multiset key 函数);`first_flag(item)` 判本命。
  - `compute_ranking(..., history: list | None = None)` / `compute_cp_ranking(..., history=None)` / `compute_paper_results(..., history=None)`:`history` 非 None 时,输出条目的 `trend`/`trend_first` 用净增量结果替换近似值(近似逻辑保留为 `history is None` 的回退,便于逐步迁移与旧测试);问卷的 `trend_first` 恒空不变。

- [ ] **Step 1: 写失败测试**(核心语义全覆盖)

```python
VS = datetime(2026, 1, 1, tzinfo=timezone.utc)

def _h(vid, hours, att, ids, first=None):
    items = [{"id": i, "first": (i == first)} for i in ids]
    return (vid, VS + timedelta(hours=hours), att, items)

KEYS = lambda item: [item["id"]]
FIRST = lambda item: bool(item.get("first"))

def test_add_then_remove_produces_negative_bucket():
    hist = [_h("v1", 0, 1, ["A", "B"]), _h("v1", 3, 2, ["A"])]  # 第3小时撤掉B
    t = net_delta_trends(hist, KEYS, FIRST, VS, 720)
    assert t["B"]["trend"] == [{"hrs": 0, "cnt": 1}, {"hrs": 3, "cnt": -1}]
    assert t["A"]["trend"] == [{"hrs": 0, "cnt": 1}]            # 未变动不重复计

def test_first_flag_migration():
    hist = [_h("v1", 0, 1, ["A", "B"], first="A"),
            _h("v1", 2, 2, ["A", "B"], first="B")]              # 本命 A→B
    t = net_delta_trends(hist, KEYS, FIRST, VS, 720)
    assert t["A"]["trend_first"] == [{"hrs": 0, "cnt": 1}, {"hrs": 2, "cnt": -1}]
    assert t["B"]["trend_first"] == [{"hrs": 2, "cnt": 1}]
    assert t["A"]["trend"] == [{"hrs": 0, "cnt": 1}]            # 总票不受本命转移影响

def test_single_snapshot_degenerates_to_approximation():
    hist = [_h("v1", 5, 1, ["A"])]
    t = net_delta_trends(hist, KEYS, FIRST, VS, 720)
    assert t["A"]["trend"] == [{"hrs": 5, "cnt": 1}]

def test_invariant_net_sum_equals_final_count_random_edits():
    rng = random.Random(42)
    pool = ["A", "B", "C", "D"]
    hist, final = [], Counter()
    for v in range(30):
        att, picks = 0, []
        for _ in range(rng.randint(1, 4)):        # 每人 1-4 次改票
            att += 1
            picks = rng.sample(pool, rng.randint(1, 3))
            hist.append(_h(f"v{v}", rng.randint(0, 100), att, picks))
        final.update(picks)                        # 最后一次快照 = 终榜口径
    # 注意:_h 的时间是乱序随机——net_delta_trends 必须自己按 (ts, attempt) 排
    t = net_delta_trends(hist, KEYS, FIRST, VS, 720)
    for k in pool:
        assert sum(x["cnt"] for x in t.get(k, {"trend": []})["trend"]) == final[k]
```

注意最后一个用例里"最后一次快照"须按 `(ts, attempt)` 排序后取——测试代码里 final 的构造要与排序口径一致(用 att 最大者;写测试时先对每人的序列按同键排序再累计)。
- [ ] **Step 2: 跑测试确认失败**(模块不存在)。
- [ ] **Step 3: 实现 `trend.py`**(~60 行):按 vote_id 分组 → 组内按 `(created_at, attempt)` 升序 → 逐快照求 `set(keys)`/`set(first_keys)` 与前态的差集,增减落该快照小时桶(钳制同 compute_ranking 口径,naive tz 补 utc)→ 稀疏化输出(`cnt != 0` 保留,负值保留)。
- [ ] **Step 4: 单测通过后接 compute.py**——三个函数加 `history=None` 参数:非 None 时构造各自的 `item_keys`(角色/音乐:`whitelist.canonical(_as_token(item.get("id","")))`,None 丢弃;CP:复用 `compute_cp_ranking` 现有 multiset key 构造逻辑,提为局部闭包;问卷:`[qid]`,即 `item.get("id")` 非空时),调 `net_delta_trends`,在结果组装处用 `trends.get(oid, {"trend": [], "trend_first": []})` 替换近似数组。**近似分桶代码在 history 路径下不再执行**(用 `if history is None` 分支包住,勿删——问卷 Step 1 测试与既有 compute 测试仍走它)。
- [ ] **Step 5: 接 compute_service**——`compute_all` 里加载 `char_hist = await self.dao.load_char_history()` 等四份,传 `history=` 给三处 compute 调用(问卷传 `load_questionnaire_history(vote_year)`)。
- [ ] **Step 6: 接 advanced_search `_compute_filtered`**——镜像其现有"按 `vote_ids` 过滤 votes"的写法过滤四份 history(`[h for h in hist if h[0] in vote_ids]`),传参。**不变量集成测试**追加到 `test_result_compute.py`:造两个选民、其中一人改票两次,跑 compute_all,断言 ranking 里每实体 `sum(trend cnt) == vote_count` 且存在负桶。
- [ ] **Step 7: 全量回归 + flake8**。
- [ ] **Step 8: Commit**(可分两笔:`feat(result): 净增量 trend 纯函数` / `feat(result): compute 全链路接入真实 trend(主榜+DSL 子集)`)。

### Task 9: mock 生成器适配 + 文档收尾

**Files:**
- Modify: `scripts/generate_mock_votes.py`(paper_answer 行加 `attempt=1`;L233 附近关于 UNIQUE 约束的注释更新为批次语义)
- Modify: `docs/CHANGELOG.md` / `docs/BACKLOG.md` / `docs/migration/result-stats-audit-2026-08-14.md` / `docs/operations/mock-vote-data.md`
- Test: 既有 mock 生成器测试(`grep -rn "generate_mock" tests/ -l`)跑通即可

**Interfaces:** 无新接口;纯适配与文档。

- [ ] **Step 1: mock 生成器**——`paper_rows` 构造处加 `"attempt": 1`;跑其测试确认绿。
- [ ] **Step 2: 文档**:
  - CHANGELOG:Step 2 条目(Changed:提交存储 append-only;**兼容性:需跑 0017**;行为变化:trend 变真实净增量、admin 监控列表出现历史行、作废历史行不影响计票)。
  - BACKLOG:B-050-后补2 标 ✅(注明两步交付完成日期);新增小待办"admin 监控投票列表展示 attempt 列"(低)。
  - result-stats-audit:§一/§三 A-3 更新——legacy 近似值真相 + 本次两步结论(Step 1 平价、Step 2 超越 legacy);§二表格问卷趋势行 🔴→✅。
  - mock-vote-data.md:提一句 attempt 字段与 append-only 语义。
  - 设计稿状态行改"已实施"。
- [ ] **Step 3: 全量回归 + flake8**,确认基线净增(573 → 新数字)。
- [ ] **Step 4: Commit**:`docs+chore: B-050-后补2 收尾(mock 适配/CHANGELOG/BACKLOG/审计文档同步)`

---

## Self-Review 备忘(计划作者已核)

- 设计稿 §三→Task 1-3,§四→Task 4-6,§五→Task 7-8,§四 mock/§八 文档→Task 9,全覆盖。
- 类型一致性:`history` 元组 `(vote_id, created_at, attempt, items)` 在 Task 7 产出、Task 8 消费,签名一致;`latest_batch` 在 Task 6 定义、compute_dao 复用。
- 已知留白(刻意):Task 1/3/6 的测试代码依赖各测试文件现有 fixture,实现者先读文件再套用,不在计划里虚构 fixture 名。
