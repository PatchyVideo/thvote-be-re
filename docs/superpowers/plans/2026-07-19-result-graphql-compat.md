# Result 契约层 + 问卷 code + 分段统计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `Touhou-Vote/packages/result` 前端能真正打通本后端 —— 补上 legacy 契约的 12 个 `query*` GraphQL 字段(typed、camelCase),并把问卷统计从死表切到 `paper_answer`、把"性别"泛化成"按问卷回答分段"。

**Architecture:** 三层。**域层**(`src/apps/result/compute*.py`)算通用的 segment 统计;**契约层**(新 `src/api/graphql/resolvers/result_compat.py`)把 compute 的 dict **投影**成 `src/api/graphql/types.py` 里那套**已存在但零引用**的 typed 类型(它们的字段名正是前端契约);**问卷地基**给 `question_def`/`option_def` 加语义 `code` 列,让配置与前端都按 7 位码寻址。

**Tech Stack:** Python 3 (typed) · FastAPI · strawberry-graphql · SQLAlchemy async · Alembic · Redis · pytest(sqlite)。

设计稿:`docs/superpowers/specs/2026-07-19-result-graphql-compat-design.md`(先读它的 §三~§七)。

## Global Constraints

- **契约层只做投影,不改域层语义**。compute 内部按 segment 通用计数;契约层把 `segments["male"]` 投影成扁平的 `maleVoteCount` 等字段。
- **`types.py` 的结果类型每个字段都必填、无默认值**(`RankingEntry` 34 个;`album`/`CPItem.c` 虽 `Optional` 但无默认)→ **适配器必须逐字段显式构造**。
- **`voteYear`**:该年 Redis 有数据就用;否则回落 `settings.vote_year` 并 `logger.info` 一条。
- **`query`(高级搜索 DSL)**:接受参数;空/`None`/`"NONE"` → 全量榜;**非空 → 抛可辨识错误「高级搜索暂未实现」**(经 `map_app_errors`,不得变成 `INTERNAL_ERROR`)。
- **单条查询按唯一序号**:用 `entry["rank"][0]["rank"]`(排序后 1-based 序位),**不用会并列的 `display_rank`**。
- **历史字段本轮一律填 0**:`rank_last_1/2`、`vote_count_last_1/2`、`first_vote_count_last_1/2`、`first_vote_percentage_last_1/2`、`vote_percentage_last_1/2`(C2 未做)。
- **加法式,不破坏现有**:保留现有 `ResultQuery` 的 JSON 版查询;compute 输出**新增** `segments` 字段的同时**继续产出** `male_vote_count`/`female_vote_count` 嵌套对象(现有 pydantic `RankingEntity` 与 Redis 消费方不受影响)。
- **测试跑 sqlite**:禁用 PG-only SQL。**测试命令 `python3 -m pytest`**(裸 `pytest` 是系统 Python 3.10,`datetime.UTC` 会炸)。
- **CI 只 lint `src/`**:提交前必须 `python3 -m flake8 src/` 干净(max-line-length=88)。
- **alembic 当前 head = `0014`** → 新迁移编号 `0015`。

---

## File Structure

| 文件 | 责任 | 动作 |
|---|---|---|
| `alembic/versions/0015_questionnaire_semantic_code.py` | 给 `question_def`/`option_def` 加 `code` 列 + 索引 | Create |
| `src/db_model/questionnaire_def.py` | `QuestionDef.code` / `OptionDef.code` | Modify |
| `src/apps/questionnaire/importer.py` | 解析树时读 `code` | Modify |
| `src/apps/questionnaire/dao.py` | 写入 `code`;新增按 code 取映射的方法 | Modify |
| `src/apps/questionnaire/admin_service.py` | CRUD 接受 `code` | Modify |
| `src/apps/questionnaire/assembler.py` | 结构输出带 `code` | Modify |
| `src/apps/result/compute_dao.py` | `load_questionnaire_votes(vote_year)` 改读 `paper_answer` | Modify |
| `src/apps/result/compute.py` | `build_segment_map`;ranking/CP 加 segment 计数;paper 加性别交叉;completion 补分子分母;covote 过白名单+出名 | Modify |
| `src/apps/result/compute_service.py` | 传 vote_year / segment 配置 | Modify |
| `src/api/graphql/resolvers/result_compat.py` | **新**:12 个 `query*` + 适配器 | Create |
| `src/api/graphql/schema.py` | 把 `ResultCompatQuery` 挂进 `Query` 基类 | Modify |
| `src/common/config.py` | 性别题/选项改按 code 配 | Modify |
| `tests/…`(见各任务) | 单测 + 集成 + schema 契约测 | Create/Modify |

---

## Task 1: 问卷语义 `code` 列 + 导入/编辑器携带

**Files:** Create `alembic/versions/0015_questionnaire_semantic_code.py`;Modify `src/db_model/questionnaire_def.py`、`src/apps/questionnaire/importer.py`、`src/apps/questionnaire/dao.py`、`src/apps/questionnaire/admin_service.py`、`src/apps/questionnaire/assembler.py`;Test `tests/integration/test_questionnaire_code.py`

**Interfaces produced:** `QuestionDef.code: str | None`、`OptionDef.code: str | None`(`String(16)`,可空,建索引);导入树节点新增可选 `code` 键;结构输出新增 `code`。

**为什么必须独立成列**(勿改成复用主键):线上实测 `question_def.id` 是 **1,2,3 自增**,不是语义码;且运营将来用 admin 编辑器录题只会拿到自增主键。

- [ ] **Step 1: 写迁移 `0015`**

```python
"""questionnaire semantic code columns

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("question_def", sa.Column("code", sa.String(16), nullable=True))
    op.create_index("ix_question_def_code", "question_def", ["code"])
    op.add_column("option_def", sa.Column("code", sa.String(16), nullable=True))
    op.create_index("ix_option_def_code", "option_def", ["code"])


def downgrade() -> None:
    op.drop_index("ix_option_def_code", table_name="option_def")
    op.drop_column("option_def", "code")
    op.drop_index("ix_question_def_code", table_name="question_def")
    op.drop_column("question_def", "code")
```
> 参照同目录既有迁移的幂等写法(本仓迁移为 Postgres-only 但需能在 sqlite 建表路径下工作)。若既有迁移使用了 `if not exists` 风格的守卫,照抄该风格。

- [ ] **Step 2: 模型加字段**

`src/db_model/questionnaire_def.py`,`QuestionDef` 与 `OptionDef` 各加:
```python
    code: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
```
(放在各自 `order` 附近;注释一行说明:7 位语义码,题 5 位/选项 7 位,见需求文档。)

- [ ] **Step 3: 导入与 CRUD 携带 `code`**

- `importer.py`:在解析 question 的 dict 里加 `"code": q.get("code")`;option 同理加 `"code": o.get("code")`。
- `dao.py` `replace_structure_tree`:构造 `QuestionDef(...)` / `OptionDef(...)` 时把 `code` 传进去(与现有 `if X.get("id") is not None` 的显式 id 处理并列)。
- `admin_service.py`:create/update question 与 option 的可写字段集合里加入 `code`。
- `assembler.py`:输出 question/option 节点时带上 `"code": row.code`。

- [ ] **Step 4: 写集成测 `tests/integration/test_questionnaire_code.py`**

用本仓集成测既有的 `session` fixture(见 `tests/integration/conftest.py`)。三个用例:
1. **导入带 code 的树 → 落库**:`replace_structure_tree` 传入含 `code` 的树,查库断言 `QuestionDef.code == "11011"`、`OptionDef.code == "1101101"`。
2. **导入不带 code → 为 None**(不报错,向后兼容)。
3. **assembler 输出带 code**:调用结构组装,断言返回的 question/option 节点里有 `code`。

- [ ] **Step 5: 跑测试 + 迁移正反向**

```bash
python3 -m pytest tests/integration/test_questionnaire_code.py -v
python3 -m flake8 src/
```
Expected: PASS + flake8 干净。

- [ ] **Step 6: 提交**

```bash
git add alembic/versions/0015_questionnaire_semantic_code.py src/db_model/questionnaire_def.py src/apps/questionnaire/ tests/integration/test_questionnaire_code.py
git commit -m "feat(result): 问卷 question/option 加语义 code 列 + 导入与编辑器携带"
```

---

## Task 2: 问卷 feed 改读 `paper_answer`

**Files:** Modify `src/apps/result/compute_dao.py`、`src/apps/result/compute_service.py`;Test `tests/integration/test_questionnaire_feed.py`

**Interfaces:**
- Consumes: `PaperAnswer`(`vote_id`, `vote_year`, `active_question_id`, `selected_option_ids`, `input_text`)、`QuestionDef.code`、`OptionDef.code`。
- Produces: `ComputeDAO.load_questionnaire_votes(vote_year: int) -> list[tuple[str, list[dict]]]`,每个 dict = `{"id": 题code, "answer": [选项code…], "answer_str": input_text}`。**签名新增 `vote_year` 参数**(其余 `load_*_votes` 不带参)。

**规则:**
- 只取该 `vote_year` 的行。
- `active_question_id` 为空 → 跳过该行。
- 题/选项**没有 `code`** → 跳过(无法按语义码寻址;记一次 `logger.debug` 汇总计数即可,勿逐行刷日志)。
- 同一 `vote_id` 的多行合并成一个 list。
- `paper_answer` **无 `invalidated`**,不做作废过滤(与 raw_* 不同,写进注释)。

- [ ] **Step 1: 写失败集成测 `tests/integration/test_questionnaire_feed.py`**

seed:`QuestionDef(code="11011")` + 两个 `OptionDef(code="1101101"/"1101102")` + 一个 `Input` 题 `code="11021"`;再 seed `PaperAnswer` 行(vote-1 选了 1101101;vote-2 选了 1101102;vote-1 另一行 input_text="喜欢")。另加一行 `active_question_id=None`(应被跳过)和一行 `vote_year` 不同(应被过滤)。

```python
@pytest.mark.asyncio
async def test_load_questionnaire_votes_from_paper_answer(session):
    await _seed(session)              # 见上
    dao = ComputeDAO(session)
    votes = await dao.load_questionnaire_votes(2026)
    by_vote = {vid: items for vid, items in votes}

    assert set(by_vote) == {"vote-1", "vote-2"}          # 空 active/别年被排除
    assert {"id": "11011", "answer": ["1101101"], "answer_str": None} in by_vote["vote-1"]
    assert {"id": "11021", "answer": [], "answer_str": "喜欢"} in by_vote["vote-1"]
    assert by_vote["vote-2"][0]["answer"] == ["1101102"]
```

- [ ] **Step 2: 跑测试确认失败** — `python3 -m pytest tests/integration/test_questionnaire_feed.py -v`(当前读死表,返回空)。

- [ ] **Step 3: 实现**

在 `compute_dao.py`:去掉 `from src.db_model.questionnaire import Questionnaire`,改 import `PaperAnswer` / `QuestionDef` / `OptionDef`。重写:

```python
    async def load_questionnaire_votes(
        self, vote_year: int
    ) -> list[tuple[str, list[dict]]]:
        """从 paper_answer(B-039 结构化表)读问卷回答,按语义 code 输出。

        注意:paper_answer 没有 invalidated 标志,admin 作废动作触达不到问卷答案。
        题/选项缺 code 的行会被跳过(无法按语义码寻址)。
        """
        q_codes = dict(
            (await self.session.execute(select(QuestionDef.id, QuestionDef.code))).all()
        )
        o_codes = dict(
            (await self.session.execute(select(OptionDef.id, OptionDef.code))).all()
        )
        rows = (
            await self.session.execute(
                select(PaperAnswer).where(PaperAnswer.vote_year == vote_year)
            )
        ).scalars().all()

        grouped: dict[str, list[dict]] = {}
        skipped = 0
        for r in rows:
            if r.active_question_id is None:
                continue
            qcode = q_codes.get(r.active_question_id)
            if not qcode:
                skipped += 1
                continue
            answers = [
                o_codes[oid]
                for oid in (r.selected_option_ids or [])
                if o_codes.get(oid)
            ]
            grouped.setdefault(r.vote_id, []).append(
                {"id": qcode, "answer": answers, "answer_str": r.input_text}
            )
        if skipped:
            logger.debug("questionnaire feed: skipped %d rows without code", skipped)
        return list(grouped.items())
```
(文件顶部若无 `logger`,加 `logger = logging.getLogger(__name__)`。)

`compute_service.py`:`q_votes = await self.dao.load_questionnaire_votes(vote_year)`。

- [ ] **Step 4: 跑测试确认通过** + `python3 -m pytest tests/ -k "compute or questionnaire" -v`(记录因此转红的旧测,若有则在本任务内修)。

- [ ] **Step 5: 提交** — `feat(result): 问卷 feed 改读 paper_answer(按语义 code 映射)`

---

## Task 3: 分段统计泛化(性别 = 被指定的那道题)

**Files:** Modify `src/apps/result/compute.py`、`src/apps/result/compute_service.py`、`src/common/config.py`;Test `tests/unit/test_segment_stats.py`

**Interfaces:**
- **新增** `build_segment_map(questionnaire_votes, question_code: str, label_by_option: dict[str, str]) -> dict[str, str]` —— 返回 `vote_id → label`,无匹配为 `"unknown"`。**取代** `compute_gender_map`(删除旧函数;它的调用方只有 compute_service 与旧测)。
- `compute_ranking` / `compute_cp_ranking` 的第 3 个参数 `gender_map` **改名为 `segment_map`**(类型不变 `dict[str, str]`)。
- 每个 ranking entry **新增** `"segments": {label: {"vote_count": int, "percentage_per_item": float, "percentage_per_total": float}}`;**同时保留**原有 `male_vote_count` / `female_vote_count` 嵌套对象,其值由 `segments.get("male"/"female")` 投影(缺失则全 0)。**CP entry 同样要有这两组字段**(现在完全没有,而契约层 `CPRankingEntry` 必填)。
- `compute_paper_results(questionnaire_votes, segment_map)` —— **签名改为接收 segment_map**(去掉未使用的 `vote_start`/`total_hours`)。每题输出新增 `total_male` / `total_female`,每个 `answers_cat` 项新增 `male_votes` / `female_votes`。

**配置**(`src/common/config.py`):
```python
    gender_question_code: str = Field("11011")   # 题语义码(不带 q 前缀)
    gender_male_option_code: str = Field("1101101")
    gender_female_option_code: str = Field("1101102")
```
保留旧的三个 `gender_*` 字段一个发布周期(标注 deprecated)以免部署侧炸;`compute_service` 只读新字段,并据此构造 `label_by_option = {male_code: "male", female_code: "female"}`。

- [ ] **Step 1: 写失败单测 `tests/unit/test_segment_stats.py`**

```python
def test_build_segment_map():
    q_votes = [
        ("u1", [{"id": "11011", "answer": ["1101101"], "answer_str": None}]),
        ("u2", [{"id": "11011", "answer": ["1101102"], "answer_str": None}]),
        ("u3", [{"id": "11021", "answer": ["1102101"], "answer_str": None}]),  # 别的题
    ]
    m = build_segment_map(q_votes, "11011", {"1101101": "male", "1101102": "female"})
    assert m == {"u1": "male", "u2": "female", "u3": "unknown"}


def test_ranking_segments_and_legacy_projection():
    # u1=male 投 id_a;u2=female 投 id_a → id_a segments male1/female1
    votes = [_vote("u1", [{"id": "id_a"}]), _vote("u2", [{"id": "id_a"}])]
    seg = {"u1": "male", "u2": "female"}
    ranking, _ = compute_ranking(votes, _wl(), seg, {}, VS, 1)
    e = ranking[0]
    assert e["segments"]["male"]["vote_count"] == 1
    assert e["segments"]["female"]["vote_count"] == 1
    # legacy 投影仍在
    assert e["male_vote_count"]["vote_count"] == 1
    assert e["female_vote_count"]["vote_count"] == 1


def test_cp_ranking_has_gender_fields():
    votes = [_v("u1", [{"id_a": "A", "id_b": "B"}]), _v("u2", [{"id_a": "A", "id_b": "B"}])]
    ranking, _ = compute_cp_ranking(votes, _wl(), {"u1": "male"}, {}, VS, 1)
    e = ranking[0]
    assert e["male_vote_count"]["vote_count"] == 1
    assert e["female_vote_count"]["vote_count"] == 0


def test_paper_results_gender_crosstab():
    q_votes = [
        ("u1", [{"id": "11011", "answer": ["1101101"], "answer_str": None}]),
        ("u2", [{"id": "11011", "answer": ["1101102"], "answer_str": None}]),
    ]
    seg = {"u1": "male", "u2": "female"}
    res = compute_paper_results(q_votes, seg)
    q = res["11011"]
    assert q["total_male"] == 1 and q["total_female"] == 1
    cat = {c["aid"]: c for c in q["answers_cat"]}
    assert cat["1101101"]["male_votes"] == 1 and cat["1101101"]["female_votes"] == 0
```

- [ ] **Step 2: 跑测试确认失败。**

- [ ] **Step 3: 实现**

- 删 `compute_gender_map`,加 `build_segment_map`(遍历 q_votes,找 `item["id"] == question_code`,取 `answer[0]`(或 `answer_str`)在 `label_by_option` 里查 label,查不到 `"unknown"`)。
- `compute_ranking`:把 `male_count`/`female_count` 两个 defaultdict 换成 `segment_count: dict[oid, dict[label, int]]`;循环里 `segment_count[oid][segment_map.get(user_id, "unknown")] += 1`。输出时:
  ```python
  segs = segment_count[oid]
  def _seg(label: str) -> dict:
      c = segs.get(label, 0)
      return {
          "vote_count": c,
          "percentage_per_item": round(c / vc, 4) if vc else 0.0,
          "percentage_per_total": round(c / total_voters, 4) if total_voters else 0.0,
      }
  entry["segments"] = {lb: _seg(lb) for lb in segs}
  entry["male_vote_count"] = {  # legacy 投影,契约层要扁平字段
      "vote_count": _seg("male")["vote_count"],
      "percentage_per_char": _seg("male")["percentage_per_item"],
      "percentage_per_total": _seg("male")["percentage_per_total"],
  }
  # female 同理
  ```
- `compute_cp_ranking`:**同样加**上述 `segments` + `male_vote_count`/`female_vote_count`(现在完全没有)。
- `compute_paper_results(questionnaire_votes, segment_map)`:计数时按 `segment_map.get(user_id)` 同时累加 `male_votes`/`female_votes` 与 `total_male`/`total_female`。
  > **简化说明(与设计稿的偏差,需在 CHANGELOG 注明)**:聚合仍**按答案形状**分派(`answer` 是 list → 按选项计数;`answer_str` 非空 → 收字符串),**不引入 `question_def.type` 映射** —— 形状已足以区分单选/多选/填空,引入类型表只会多一次 DB 往返而无收益。
- `compute_service`:构造 `label_by_option` 并调用 `build_segment_map`;把 `segment_map` 传给三个 ranking 与 paper。

- [ ] **Step 4: 跑测试** — 新测 PASS;`python3 -m pytest tests/ -q` 全绿(修因改名/签名转红的旧测)。

- [ ] **Step 5: 提交** — `feat(result): 性别泛化为分段统计(segment_map)+ 问卷性别交叉`

---

## Task 4: compute 小缺口 + covote 修正(C4)

**Files:** Modify `src/apps/result/compute.py`、`src/apps/result/compute_service.py`;Test `tests/unit/test_compute_gaps.py`

**Interfaces:**
- `compute_completion_rates(...) -> dict[str, dict]`,每项 `{"rate": float, "num_complete": int, "total": int}`(原来只返回 rate 分数)。
- `compute_covote(votes, whitelist, top_k=100)` —— **新增 `whitelist` 参数**:配对前**先按白名单过滤** id;输出 `a`/`b` 用 `whitelist.name_of()` 转**人名**;新增 `"cs": 0.0, "mi": 0.0` 两个字段(**本轮明确置 0 并注释未实现** —— 前端 connect 页仍是占位,无消费方)。

- [ ] **Step 1: 写失败单测 `tests/unit/test_compute_gaps.py`**

```python
def test_completion_rates_returns_counts():
    res = compute_completion_rates(CHAR_VOTES, [], [], [], {"u1", "u2", "u3"})
    assert res["character"]["num_complete"] == 3
    assert res["character"]["total"] == 3
    assert res["character"]["rate"] == pytest.approx(1.0)


def test_covote_uses_names_and_filters_whitelist():
    votes = [
        _vote("u1", [{"id": "id_a"}, {"id": "id_b"}, {"id": "UNKNOWN"}]),
        _vote("u2", [{"id": "id_a"}]),
    ]
    items = compute_covote(votes, _wl(), top_k=10)
    names = {n for i in items for n in (i["a"], i["b"])}
    assert names <= {"角色甲", "角色乙"}      # 出人名,且 UNKNOWN 被丢
    assert all(i["cs"] == 0.0 and i["mi"] == 0.0 for i in items)
```

- [ ] **Step 2: 跑测试确认失败。**
- [ ] **Step 3: 实现**(改 `compute_completion_rates` 返回结构;`compute_covote` 加 whitelist 过滤 + `name_of` + `cs`/`mi` 置 0 并写注释;`compute_service` 传 `char_wl`/`music_wl` 给 covote)。
- [ ] **Step 4: 跑测试**(新测 PASS;全量绿 —— 注意 `ResultDAO.get_completion_rates` 的消费方与旧断言可能要跟着改)。
- [ ] **Step 5: 提交** — `feat(result): completion 补分子分母 + covote 过白名单并输出人名`

---

## Task 5: 契约层骨架 + 三个排名查询

**Files:** Create `src/api/graphql/resolvers/result_compat.py`;Modify `src/api/graphql/schema.py`;Test `tests/unit/test_result_compat_schema.py`、`tests/integration/test_result_compat_ranking.py`

**Interfaces produced:** `ResultCompatQuery`,字段 `queryCharacterRanking` / `queryMusicRanking` / `queryCPRanking`,签名均为:
```python
(self, vote_start: Optional[DateTimeUtc] = None, vote_year: Optional[int] = None,
 query: Optional[str] = None) -> CharacterOrMusicRanking | CPRanking
```
> `vote_start` 前端必传但后端**不使用**(仅为 schema 兼容),写注释说明。

**公共助手(本任务建立,后续任务复用):**
```python
def _resolve_vote_year(dao, requested: Optional[int], settings) -> int:
    """该年有数据就用,否则回落 settings.vote_year 并记一条日志。"""

def _reject_query_dsl(query: Optional[str]) -> None:
    """非空(且非 'NONE')→ 抛「高级搜索暂未实现」;经 map_app_errors 成为可辨识错误。"""
```

**`RankingEntry` 字段映射表**(compute dict → strawberry;**34 个字段全部必填**):

| strawberry 字段 | 来源 |
|---|---|
| `rank` | `e["rank"][0]["rank"]` |
| `display_rank` | `e["display_rank"]` |
| `name` | `e["name"]` |
| `vote_count` | `e["rank"][0]["vote_count"]` |
| `first_vote_count` | `e["rank"][0]["favorite_vote_count"]` |
| `first_vote_percentage` | `e["favorite_percentage"]` |
| `first_vote_count_weighted` | `e["favorite_vote_count_weighted"]` |
| `first_percentage` | `e["favorite_percentage_of_all"]` |
| `vote_percentage` | `e["rank"][0]["vote_percentage"]` |
| `character_type` / `character_origin` / `first_appearance` | `e["type"]` / `e["origin"]` / `e["first_appearance"]` |
| `album` | `e["album"] or None` |
| `name_jpn` | `e["name_jp"]` |
| `male_vote_count` / `male_percentage_per_char` / `male_percentage_per_total` | `e["male_vote_count"]` 的 `vote_count` / `percentage_per_char` / `percentage_per_total` |
| `female_*`(同三项) | `e["female_vote_count"]` 同理 |
| `trend` / `trend_first` | `[VotingTrendItem(hrs=t["hrs"], cnt=t["cnt"]) for t in e["trend"…]]` |
| `reasons` / `num_reasons` | `e["reasons"]` / `e["reasons_count"]` |
| `rank_last_1` `rank_last_2` `vote_count_last_1` `vote_count_last_2` `first_vote_count_last_1` `first_vote_count_last_2` | **0** |
| `first_vote_percentage_last_1/2`、`vote_percentage_last_1/2` | **0.0** |

**`CPRankingEntry` 映射**:同上通用项;另外 `cp = CPItem(a=wl.name_of(e["id_a"]), b=wl.name_of(e["id_b"]), c=wl.name_of(e["id_c"]) if e["id_c"] else None)`(用 `load_whitelist("character")`);`a_active`/`b_active`/`c_active`/`none_active` ← `e["active_a"]`/`…_b`/`…_c`/`e["active_none"]`;male/female 来自 Task 3 给 CP 补的字段。

**`RankingGlobal`** ← global dict 的 `total_unique_items` / `total_first` / `total_votes` / `average_votes_per_item` / `median_votes_per_item`(同名)。

- [ ] **Step 1: 写 schema 契约测 `tests/unit/test_result_compat_schema.py`**

参照既有 `tests/unit/test_submit_bridge_schema.py` 的写法(对 `schema.as_str()` 断言),断言 SDL 中存在:
`queryCharacterRanking(`、`queryMusicRanking(`、`queryCPRanking(`,且 `CharacterOrMusicRanking` 有 `global:` 字段(而非 `global_`)。

- [ ] **Step 2: 写行为集成测 `tests/integration/test_result_compat_ranking.py`**

用 `session` + 本地 `fake_redis`/`settings` fixture(照 `tests/integration/test_result_compute.py` 顶部)。seed raw_character(真实白名单 id)→ `ComputeService.compute_all` → 用 `schema.execute` 跑:
```graphql
query { queryCharacterRanking(voteYear: 11) { global { totalVotes } entries { name displayRank voteCount firstVoteCount maleVoteCount } } }
```
断言:①无 `errors`;②`voteYear: 11` 无数据 → **回落**到 settings 年份且**有数据返回**;③非空 `query: "chars:[\"x\"]"` → 返回可辨识错误且 **不是** `INTERNAL_ERROR`。

- [ ] **Step 3: 跑测试确认失败。**
- [ ] **Step 4: 实现** `result_compat.py` + 在 `schema.py` 的 `class Query(...)` 基类列表**追加** `ResultCompatQuery`(放在 `ResultQuery` **之后**,避免同名遮蔽;当前无同名,仍按此顺序)。resolver 内用 `async with map_app_errors(service="result"):`。
- [ ] **Step 5: 跑测试 + `python3 -m flake8 src/`。**
- [ ] **Step 6: 提交** — `feat(result): GraphQL 契约层骨架 + 三个排名查询`

---

## Task 6: 契约层剩余九个查询

**Files:** Modify `src/api/graphql/resolvers/result_compat.py`;Test `tests/integration/test_result_compat_rest.py`

**新增字段与映射:**

| 字段 | 参数 | 返回 | 取数 |
|---|---|---|---|
| `queryCharacterSingle` / `queryMusicSingle` / `queryCPSingle` | `rank: int!`, `voteStart?`, `voteYear?`, `query?` | `RankingEntry` / `CPRankingEntry` | 取该 category 的 ranking,**按 `e["rank"][0]["rank"] == rank`** 匹配;找不到 → 可辨识 404 类错误 |
| `queryCharacterTrend` / `queryMusicTrend` | `names: [String!]!`, `voteStart?`, `voteYear?` | `list[Trends]` | 对每个 name 取 `ResultDAO.get_trend`,组装 `Trends(trend=…, trend_first=…)`;**顺序与入参 names 一致**;缺失的 name 返回空 trend(不报错) |
| `queryGlobalStats` | `voteStart?`, `voteYear?`, `query?` | `ResultGlobalStats` | `get_global_stats` + `vote_year=` 解析后的年份 |
| `queryCompletionRates` | `voteStart?`, `voteYear?`, `query?` | `CompletionRate` | Task 4 后的 dict → `items=[CompletionRateItem(name=cat, rate=…, num_complete=…, total=…)]` |
| `queryQuestionnaire` | `questionsOfInterest: [String!]!`, `voteStart?`, `voteYear?`, `query?` | `QueryQuestionnaireResponse` | 对每个 id **去掉可选 `q` 前缀**后取 `paper:{code}`;组装 `CachedQuestionItem(question_id="q"+code, answers_cat=[CachedQuestionAnswerItem(aid=…, total_votes=…, male_votes=…, female_votes=…)], answers_str=…, total_answers=…, total_male=…, total_female=…)`;**缺的题跳过**(不报错) |
| `queryQuestionnaireTrend` | `questionIds: [String!]!`, 同上 | `QueryQuestionnaireResponse` | **与 `queryQuestionnaire` 同实现**(现有后端本就是别名,无时间轴);在 docstring 写明"无时间维度,C3/问卷 trend 未实现" |

- [ ] **Step 1: 写集成测**(每个查询至少一条:能跑通 + 关键字段对);`queryCharacterSingle` 要有"按唯一序号取到正确条目"的断言;`queryQuestionnaire` 要覆盖 `q11011` 与 `11011` 两种写法都能命中。
- [ ] **Step 2: 跑测试确认失败。**
- [ ] **Step 3: 实现。**
- [ ] **Step 4: 跑测试 + 全量 + `flake8 src/`。**
- [ ] **Step 5: 提交** — `feat(result): 契约层补齐单条/趋势/全局/问卷/完成率查询`

---

## Task 7: 文档 / CHANGELOG / BACKLOG + 端到端验收

**Files:** Modify 设计稿(补"实现落地"节)、`docs/CHANGELOG.md`、`docs/BACKLOG.md`

- [ ] **Step 1: 端到端验收**

```bash
python3 -m pytest tests/ -q          # 全绿
python3 -m flake8 src/               # exit 0
python3 -m alembic upgrade head      # 到 0015
```
再对**本地起的**服务(或部署后)用前端真实查询打一次 `queryCharacterRanking`,确认能过 schema 校验并返回数据。把实际输出片段贴进报告。

- [ ] **Step 2: 设计稿补 §十「v1 实现落地」**:最终文件清单、`code` 的写入路径、配置项新名、以及**与设计稿的偏差**(问卷聚合按答案形状而非 `question_def.type` 分派 —— 附理由)。

- [ ] **Step 3: CHANGELOG**:`[2026-07-19]` 条目,Added/Changed;写明**兼容性**:新增 12 个 GraphQL 查询(加法式,旧 JSON 查询保留);`compute_*` 三处签名变化(`gender_map`→`segment_map`、`compute_paper_results` 去掉未用参数、`compute_covote` 加 whitelist);`compute_completion_rates` 返回结构变化;新增 `0015` 迁移;配置新增 `gender_*_code` 三项(旧三项标 deprecated)。

- [ ] **Step 4: BACKLOG**:
  - 标记「result 契约层断裂」**已解决**(本轮)。
  - **更新 B-050-后补5(高级搜索)**:补记 DSL **不是过滤现成榜、而是换投票子集重算**,需按需子集重算能力;与分段共用 `vote_id → 回答` 索引。
  - **新增**:通用「任意问卷题 × 投票结果」交叉分析 API + 前端(与 DSL 同组,共用索引)。
  - **新增(运营)**:录入真实问卷内容并填 `code`(可从前端 legacy `questionnaire.ts` 导入,含真实 7 位 id);**在此之前性别票/问卷结果恒为 0**。
  - **新增(前端,另一仓库)**:`characterConnect`/`musicConnect` 占位页待补;`doujin` 页硬编码;CP 缺 compare/evolution 页;`/test` 调试路由在生产 router 里。

- [ ] **Step 5: 提交** — `docs(result): 契约层落地说明 + CHANGELOG + BACKLOG`

---

## Self-Review Checklist

- **Spec 覆盖**:A 契约层(T5/T6)✓;B code 列(T1)✓;C1 feed(T2)+ 分段(T3)✓;C4 covote(T4)✓;不做项在 T7 记 BACKLOG ✓。
- **类型必填**:映射表覆盖 `RankingEntry` 全部 34 字段(含 8 个历史字段填 0)与 `CPRankingEntry` 的 male/female(靠 T3 给 CP 补字段)✓。
- **无占位**:每个任务有确切文件、签名、映射表、测试用例 ✓。
- **可移植**:测试跑 sqlite,无 PG-only SQL ✓;测试命令统一 `python3 -m pytest` ✓;`flake8 src/` 进每个任务的验收 ✓。
- **加法式**:旧 JSON 查询保留、compute 同时产出 legacy male/female 字段 ✓。
- **一致性**:`segment_map` 命名在 T3/T5 一致;`code` 不带 `q` 前缀存库、契约层出/入都处理前缀 ✓。

## Execution Handoff

计划已存 `docs/superpowers/plans/2026-07-19-result-graphql-compat.md`。两种执行方式:
1. **Subagent-Driven(推荐)** — 每任务派新实现子代理 + 任务级评审 + 收尾整支评审。
2. **Inline Execution** — 本会话批量执行 + 检查点。
