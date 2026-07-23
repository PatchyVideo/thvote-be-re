# 计票真相源迁 DB + voteable 导入/管理通道 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 计票白名单从前端快照 JSON 迁到 DB（voteable/candidate），入口双键（8-hex 旧 id / candidateId 新 id）聚合到同一实体；建统一的 voteable 导入通道与 admin 查看/编辑能力。

**Architecture:** 见设计稿 `docs/superpowers/specs/2026-07-23-tally-db-truth-source-design.md`（§三~§七）。迁移 0016 纯 schema；数据全走 admin 导入端点（upsert + dry-run）；compute 内部 canonical key = `str(candidate_id)`；`RankingEntity` 加法式新增 `candidate_id`。

**Tech Stack:** FastAPI + SQLAlchemy(async) + Alembic + strawberry-graphql + pytest（sqlite aiosqlite 测试库经 `create_all`）。

## Global Constraints

- 分支：`renko_dev`。每个 Task 一个 commit，msg 前缀按仓库约定（feat:/fix:/test:/docs:）。
- 提交前必须过：`python3 -m pytest tests/ -q`（全绿）与 `python3 -m flake8 src/`（exit 0，max-line-length=88；**CI 只 lint src/，但 flake8 挂了 CI 必挂**）。
- 迁移写法对齐 0015：Postgres-only 幂等（sqlite 测试库走 `create_all`，跳过迁移）。
- GraphQL/REST 契约只做加法，不改既有字段语义（CLAUDE.md §8）。
- 快照 JSON `src/apps/result/data/whitelist_{character,music}.json` 是只读 fixture，任何任务不得修改其内容。
- admin 路由已有 `require_admin` 全局闸门；新端点照 `list_works`/`create_work`（`src/apps/admin/router.py:624-648`）的依赖注入模式写，不必手动查 secret。

---

### Task 1: 迁移 0016 + candidate 模型加 sort_order

**Files:**
- Create: `alembic/versions/0016_candidate_sort_order.py`
- Modify: `src/db_model/candidate.py`（两个类各加一列）
- Test: 复用 CI 空库迁移烟雾（无新测试文件；模型列由后续任务的测试覆盖）

**Interfaces:**
- Produces: `CandidateCharacter.sort_order: Optional[int]`、`CandidateMusic.sort_order: Optional[int]`（后续所有任务依赖）

- [ ] **Step 1: 写迁移**（照抄 0015 的幂等风格，`down_revision = "0015"`）

```python
"""0016 add sort_order to candidate_character/candidate_music.

年度官方候选列表序号（0 起），名次第三级 tie-break 的数据来源
（设计稿 2026-07-23-tally-db-truth-source-design.md §三）。
Postgres-only 幂等；sqlite 测试库经 create_all 跳过本迁移。
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_TABLES = ("candidate_character", "candidate_music")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS sort_order INTEGER")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS sort_order")
```

- [ ] **Step 2: 模型加列** —— `src/db_model/candidate.py` 的 `CandidateCharacter` 与 `CandidateMusic` 各加：

```python
    sort_order = Column(Integer, nullable=True)
```

（加在 `voteable_id` 行之后；两个类都加。）

- [ ] **Step 3: 跑全量测试确认无回归**

Run: `python3 -m pytest tests/ -q`  Expected: 465 passed（数量与现状一致）

- [ ] **Step 4: flake8 + Commit**

```bash
python3 -m flake8 src/
git add alembic/versions/0016_candidate_sort_order.py src/db_model/candidate.py
git commit -m "feat(tally): 迁移0016 candidate 加 sort_order 列(纯 schema,年度官方列表序号)"
```

---

### Task 2: whitelist.py 重写 — 双键 Whitelist + 异步 DB 加载

**Files:**
- Modify: `src/apps/result/whitelist.py`（重写；**暂时保留**旧的 JSON `load_whitelist`，Task 6 删）
- Create: `tests/unit/test_whitelist_db.py`
- Modify（机械更新构造参数）: `tests/unit/test_compute.py`、`tests/unit/test_compute_ranking_id.py`、`tests/unit/test_compute_cp_ranking_id.py`、`tests/unit/test_compute_gaps.py`、`tests/unit/test_segment_stats.py`、`tests/unit/test_result_compat_historical_sentinel.py`

**Interfaces:**
- Produces:
  - `WhitelistEntry(candidate_id: int, voteable_id: int, old_id: str | None, name: str, name_jp: str, origin: str, type: str, first_appearance: str | None, album: str | None, system_id: int)`（frozen dataclass，字段顺序即位置参数顺序）
  - `Whitelist(entries)`：`__contains__(token: str)` / `get(token) -> WhitelistEntry | None` / `name_of(token) -> str` / `system_id_of(token) -> int` / `canonical(token) -> str | None`（返回 `str(candidate_id)`）/ `ids -> set[str]`（**canonical token 集合**）/ `entries -> list[WhitelistEntry]`
  - `async def load_whitelist_db(session, category: Literal["character","music"], vote_year: int) -> Whitelist`
  - 常量 `SORT_ORDER_TAIL_BASE = 10**8`
- Consumes: Task 1 的 `sort_order` 列。

- [ ] **Step 1: 写失败测试** `tests/unit/test_whitelist_db.py`：

```python
"""双键 Whitelist 单元测试（设计稿 §4.2/§4.4）。"""
import pytest

from src.apps.result.whitelist import (
    SORT_ORDER_TAIL_BASE, Whitelist, WhitelistEntry,
)


def _entry(cid, old_id, name, sort=0):
    return WhitelistEntry(cid, cid, old_id, name, "", "", "旧作", None, None, sort)


def test_dual_token_hits_same_entry():
    wl = Whitelist([_entry(22, "4068b1c2", "博丽灵梦")])
    assert "22" in wl and "4068b1c2" in wl
    assert wl.get("22") is wl.get("4068b1c2")
    assert wl.canonical("4068b1c2") == "22"
    assert wl.canonical("22") == "22"
    assert wl.canonical("deadbeef") is None
    assert wl.name_of("4068b1c2") == "博丽灵梦"


def test_old_id_absent_only_candidate_token():
    wl = Whitelist([_entry(7, None, "无旧id角色")])
    assert "7" in wl
    assert wl.canonical("7") == "7"
    assert wl.ids == {"7"}


def test_token_collision_raises():
    # old_id 与另一条的 candidate_id 字符串同形 → 构造期必须炸
    with pytest.raises(ValueError):
        Whitelist([_entry(22, None, "甲"), _entry(9, "22", "乙")])


def test_sort_order_null_falls_to_tail_by_candidate_id():
    wl = Whitelist([
        WhitelistEntry(5, 5, None, "有序", "", "", "旧作", None, None, 3),
        WhitelistEntry(2, 2, None, "无序", "", "", "旧作", None, None,
                       SORT_ORDER_TAIL_BASE + 2),
    ])
    assert wl.system_id_of("5") == 3
    assert wl.system_id_of("2") == SORT_ORDER_TAIL_BASE + 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/unit/test_whitelist_db.py -q`
Expected: FAIL（`WhitelistEntry` 参数不匹配 / 无 `canonical`）

- [ ] **Step 3: 重写 `src/apps/result/whitelist.py`**（保留旧 `load_whitelist` JSON 函数与 `_to_entry` 在文件尾部并加注释 `# DEPRECATED: Task 6 移除`；`_KIND_MAPPING` 保留）：

```python
SORT_ORDER_TAIL_BASE = 10**8  # sort_order 缺失时排到尾部,彼此按 candidate_id 顺延


@dataclass(frozen=True)
class WhitelistEntry:
    candidate_id: int
    voteable_id: int
    old_id: str | None
    name: str
    name_jp: str
    origin: str
    type: str
    first_appearance: str | None
    album: str | None
    system_id: int


class Whitelist:
    def __init__(self, entries: list[WhitelistEntry]):
        self._entries = list(entries)
        self._by_token: dict[str, WhitelistEntry] = {}
        for e in entries:
            for token in filter(None, (str(e.candidate_id), e.old_id)):
                if token in self._by_token:
                    raise ValueError(f"whitelist token collision: {token!r}")
                self._by_token[token] = e

    @property
    def entries(self) -> list[WhitelistEntry]:
        return self._entries

    @property
    def ids(self) -> set[str]:
        return {str(e.candidate_id) for e in self._entries}

    def __contains__(self, token: str) -> bool:
        return token in self._by_token

    def get(self, token: str) -> WhitelistEntry | None:
        return self._by_token.get(token)

    def canonical(self, token: str) -> str | None:
        e = self._by_token.get(token)
        return str(e.candidate_id) if e else None

    def name_of(self, token: str) -> str:
        e = self._by_token.get(token)
        return e.name if e else token

    def system_id_of(self, token: str) -> int:
        e = self._by_token.get(token)
        return e.system_id if e else _UNKNOWN_SYSTEM_ID


async def load_whitelist_db(session, category, vote_year: int) -> Whitelist:
    """voteable JOIN candidate(vote_year) LEFT JOIN work → Whitelist。"""
    from sqlalchemy import select
    from src.db_model.candidate import CandidateCharacter, CandidateMusic
    from src.db_model.voteable import VoteableCharacter, VoteableMusic
    from src.db_model.work import Work

    C = CandidateCharacter if category == "character" else CandidateMusic
    V = VoteableCharacter if category == "character" else VoteableMusic
    rows = (await session.execute(
        select(C.id, C.sort_order, V.id, V.name, V.name_jp, V.type,
               V.first_appearance, V.old_id, Work.name)
        .join(V, C.voteable_id == V.id)
        .outerjoin(Work, V.work_id == Work.id)
        .where(C.vote_year == vote_year)
    )).all()
    entries = []
    for cid, sort, vid, name, name_jp, vtype, first_app, old_id, wname in rows:
        entries.append(WhitelistEntry(
            candidate_id=cid, voteable_id=vid, old_id=old_id,
            name=name, name_jp=name_jp or "",
            origin=wname or "",
            type=_KIND_MAPPING.get(vtype or "", vtype or "未知"),
            first_appearance=str(first_app) if first_app else None,
            album=(wname or None) if category == "music" else None,
            system_id=(sort if sort is not None
                       else SORT_ORDER_TAIL_BASE + cid),
        ))
    return Whitelist(entries)
```

- [ ] **Step 4: 机械更新 6 个单测文件的构造调用**。旧位置参数
  `WhitelistEntry("id_a", "角色甲", "", "", "旧作", None, None, 0)` 改为在前面
  补三个参数（candidate_id 取一个稳定小整数、voteable_id 同值、old_id=原第一参）：
  `WhitelistEntry(1, 1, "id_a", "角色甲", "", "", "旧作", None, None, 0)`。
  同一文件内 candidate_id 依次 1、2、3…（**不同 entry 不得重复**）。涉及文件见
  上方 Files 列表；逐文件 grep `WhitelistEntry(` 全部改完。

- [ ] **Step 5: 全量测试 + flake8 + Commit**

Run: `python3 -m pytest tests/ -q`  Expected: 全绿（465 + 新增 4）
```bash
python3 -m flake8 src/
git add -A && git commit -m "feat(tally): Whitelist 双键重写(canonical=candidateId)+异步 DB 加载"
```

---

### Task 3: compute 入口 canonical 归一 + 丢弃分类计数 + CP member_names

**Files:**
- Modify: `src/apps/result/compute.py`（`compute_ranking` / `compute_cp_ranking` / `compute_covote` 的 id 入口；新增 `classify_dropped_token`）
- Test: `tests/unit/test_canonical_aggregation.py`（新建）

**Interfaces:**
- Consumes: Task 2 的 `Whitelist.canonical`。
- Produces:
  - `compute_ranking`/`compute_cp_ranking` 返回的 `global_stats` dict 新增键
    `"dropped": {"legacy_8hex_unmatched": int, "candidate_id_unknown": int, "malformed": int}`
  - `compute_cp_ranking` 每个条目 dict 新增 `"member_names": list[str]`（与成员 canonical 顺序一致，`wl.name_of` 结果）
  - `def classify_dropped_token(raw: str) -> str`（返回上述三个键之一）

- [ ] **Step 1: 失败测试** `tests/unit/test_canonical_aggregation.py`：

```python
"""混合 id 格式聚合 + 丢弃分类（设计稿 §4.3）。"""
from datetime import datetime, timezone

from src.apps.result.compute import (
    classify_dropped_token, compute_cp_ranking, compute_ranking,
)
from src.apps.result.whitelist import Whitelist, WhitelistEntry

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _wl():
    return Whitelist([
        WhitelistEntry(22, 22, "4068b1c2", "灵梦", "", "", "旧作", None, None, 0),
        WhitelistEntry(31, 31, "aabbccdd", "魔理沙", "", "", "旧作", None, None, 1),
    ])


def test_mixed_formats_aggregate_to_one_entity():
    votes = [
        ("u1", T0, [{"id": "4068b1c2", "first": True}]),   # 旧格式
        ("u2", T0, [{"id": "22", "first": False}]),          # 新格式,同一实体
        ("u3", T0, [{"id": "undefined"}]),                   # 前端漂移期垃圾
        ("u4", T0, [{"id": "deadbeef"}]),                    # 8hex 未匹配
        ("u5", T0, [{"id": "999"}]),                         # 未知 candidateId
    ]
    ranking, gstats = compute_ranking(votes, _wl(), {}, {}, T0, 1)
    reimu = next(e for e in ranking if e["name"] == "灵梦")
    assert reimu["vote_count"] == 2          # 两种格式聚合
    assert gstats["dropped"] == {
        "legacy_8hex_unmatched": 1, "candidate_id_unknown": 1, "malformed": 1,
    }


def test_cp_multiset_not_split_by_format():
    votes = [
        ("u1", T0, [{"id_a": "4068b1c2", "id_b": "aabbccdd", "active": "a"}]),
        ("u2", T0, [{"id_a": "31", "id_b": "22", "active": "b"}]),
    ]
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, T0, 1)
    assert len(ranking) == 1                 # 同一无序组合,一个条目
    assert ranking[0]["vote_count"] == 2
    assert sorted(ranking[0]["member_names"]) == ["灵梦", "魔理沙"]


def test_classify():
    assert classify_dropped_token("deadbeef") == "legacy_8hex_unmatched"
    assert classify_dropped_token("999") == "candidate_id_unknown"
    assert classify_dropped_token("undefined") == "malformed"
    assert classify_dropped_token("") == "malformed"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/unit/test_canonical_aggregation.py -q`  Expected: FAIL

- [ ] **Step 3: 实现**。`compute.py` 顶部加：

```python
_HEX8_RE = re.compile(r"^[0-9a-f]{8}$")


def classify_dropped_token(raw: str) -> str:
    if raw and _HEX8_RE.fullmatch(raw):
        return "legacy_8hex_unmatched"
    if raw and raw.isdigit():
        return "candidate_id_unknown"
    return "malformed"
```

`compute_ranking` 内替换（原 `oid = item.get("id", ""); if not oid or oid not in whitelist: continue`）：

```python
            raw_id = item.get("id", "")
            oid = whitelist.canonical(raw_id)
            if oid is None:
                dropped[classify_dropped_token(raw_id)] += 1
                continue
```

函数开头加 `dropped: Counter = Counter()`；`global_stats` 返回 dict 加
`"dropped": {k: dropped.get(k, 0) for k in ("legacy_8hex_unmatched", "candidate_id_unknown", "malformed")}`。
`compute_cp_ranking` 同法：每个成员 `canonical`，任一成员 None → 整条丢弃并按**第一个未命中成员**分类计数；
组合 key 用 canonical 后的成员构造；`members_of[key]` 存 canonical 成员；产出条目 dict 加
`"member_names": [whitelist.name_of(m) for m in key]`。`compute_covote` 的白名单过滤同样改走 `canonical`（聚合 key 用 canonical）。
条目 dict 的 `"id"` 字段一律取 `whitelist.get(oid).old_id`（旧语义：8-hex，可 None）。

- [ ] **Step 4: 全量测试 + flake8 + Commit**

Run: `python3 -m pytest tests/ -q`  Expected: 全绿
```bash
python3 -m flake8 src/
git add -A && git commit -m "feat(tally): compute 入口 canonical 归一+丢弃分类计数+CP member_names"
```

---

### Task 4: 统一导入通道 — VoteableImportService + POST /admin/voteables/import

**Files:**
- Create: `src/apps/admin/voteable_import_service.py`
- Modify: `src/apps/admin/router.py`（新端点，放在 works 端点之后）
- Test: `tests/integration/test_voteable_import.py`（新建）

**Interfaces:**
- Produces:
  - `class VoteableImportService:` `def __init__(self, session)`；
    `async def run(self, category: str, vote_year: int | None, format: str, content: str, dry_run: bool) -> dict`
    返回 `{create, update, work_created, candidate_upserts, conflicts, totals}`（设计稿 §5.1 形状）；
    `content` 解析失败时返回 `{"parse_error": "..."}`
  - 端点 `POST /api/v1/admin/voteables/import`，body
    `{category, vote_year?, format: "json"|"csv", content, dry_run=true}`
- Consumes: Task 1 的 `sort_order` 列。

- [ ] **Step 1: 失败测试** `tests/integration/test_voteable_import.py`（照仓库既有 admin 集成测试的 client/session fixture 写法——参考 `tests/integration/test_candidate_admin.py` 顶部 fixture，复用同款 `app`/`client`）。核心用例（每个都是独立 test 函数）：

```python
import json

ROWS = [
    {"name": "博丽灵梦", "name_jp": "博麗　霊夢", "type": "old",
     "old_id": "4068b1c2", "work": "东方红魔乡", "sort_order": 0},
    {"name": "新角色", "type": "new", "work": "新作品X", "work_type": "new",
     "sort_order": 1},
]


def _body(rows, dry_run=True, vote_year=12):
    return {"category": "character", "vote_year": vote_year,
            "format": "json", "content": json.dumps(rows), "dry_run": dry_run}
```

1. `test_dry_run_reports_create_without_writing`：空库 dry-run → `create` 长度 2、
   `work_created` 含两个 work 名；再 GET（或直查 session）确认**没有**任何行落库。
2. `test_execute_creates_and_is_idempotent`：`dry_run=False` 执行 → 再跑一次同
   内容 dry-run → `create==[]` 且 `update==[]`（幂等）；直查 voteable 行断言
   `old_id`、candidate 行断言 `sort_order`。
3. `test_match_priority_old_id_then_name`：先导入含 old_id 的行；再用「同 old_id
   但 name 改了」的行导入 → 命中 `matched_by_old_id`，update 的 diff 含 name。
4. `test_conflict_batch_rejected`：构造 name 命中但 old_id 与库内不同的行 →
   dry-run 的 `conflicts` 非空；`dry_run=False` 时整批 400/409、库内无变化。
5. `test_vote_year_none_skips_candidate`：`vote_year=None` → 只 upsert voteable，
   `candidate_upserts==0`。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/integration/test_voteable_import.py -q`  Expected: FAIL(404/ImportError)

- [ ] **Step 3: 实现 service**。要点（完整逻辑，无省略）：

```python
# voteable_import_service.py 结构
def _parse(format: str, content: str) -> list[dict] | str:
    # json: json.loads 必须是 list[dict]
    # csv: csv.DictReader(io.StringIO(content))，空列过滤
    # aliases 列: JSON 数组字符串或 ';' 分隔 → list[str]
    # sort_order/voteable_id: int()；失败 → 返回错误串（parse_error）

class VoteableImportService:
    async def run(self, category, vote_year, format, content, dry_run):
        rows = _parse(...)                      # str → {"parse_error": rows}
        V = VoteableCharacter if category == "character" else VoteableMusic
        C = CandidateCharacter if category == "character" else CandidateMusic
        # 预载全部 voteable 行到内存: by_id / by_old_id / by_name 三个索引
        # 预载全部 work: by_name
        # 逐行:
        #   1) voteable_id 提供 → by_id;找不到 → conflicts
        #   2) 否则 old_id 提供且 by_old_id 命中 → matched_by_old_id
        #   3) 否则 by_name 命中 → matched_by_name
        #      ⚠ 命中行已有非空 old_id 且与本行 old_id 都非空且不同 → conflicts
        #   4) 都未命中 → create
        #   同批内 name/old_id 重复 → conflicts
        #   work 字段: by_name 命中取 id;未命中 → 记入 work_created(执行时新建,
        #   type=work_type or "others")
        #   只更新本行**提供了**的字段(row 里没有的键不动)
        # dry_run: 只汇总报告,不写
        # 执行: conflicts 非空 → 抛 ValueError("IMPORT_CONFLICTS") (router 转 409)
        #        全部写入走当前 session(单事务,由调用方 commit 语义保证)
        #        vote_year 非空 → upsert C(vote_year, voteable_id) 行 + sort_order
        # totals: rows/matched_by_id/matched_by_old_id/matched_by_name/created
```

- [ ] **Step 4: 加端点**（`src/apps/admin/router.py`，works 端点之后；依赖注入照 `create_work`）：

```python
@router.post("/voteables/import")
async def import_voteables(
    body: dict,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    category = body.get("category")
    if category not in ("character", "music"):
        raise HTTPException(status_code=422, detail="category must be character|music")
    svc = VoteableImportService(session)
    try:
        result = await svc.run(
            category, body.get("vote_year"), body.get("format", "json"),
            body.get("content", ""), bool(body.get("dry_run", True)),
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if "parse_error" in result:
        raise HTTPException(status_code=400, detail=result["parse_error"])
    return result
```

- [ ] **Step 5: 全量测试 + flake8 + Commit**

```bash
python3 -m pytest tests/ -q && python3 -m flake8 src/
git add -A && git commit -m "feat(admin): voteable 统一导入通道(upsert+dry-run+conflicts 整批拒绝)"
```

---

### Task 5: 快照转换器 scripts/whitelist_to_import.py

**Files:**
- Create: `scripts/whitelist_to_import.py`
- Test: `tests/unit/test_whitelist_converter.py`（新建）

**Interfaces:**
- Produces: `def convert(category: str, raw_list: list[dict]) -> list[dict]`（纯函数，可 import）；
  CLI：`python3 scripts/whitelist_to_import.py character > /tmp/char_import.json`（读
  `src/apps/result/data/whitelist_{category}.json`，stdout 输出导入格式 JSON 数组）。
- Consumes: Task 4 的导入行字段约定（§5.2）。

- [ ] **Step 1: 失败测试**：

```python
import json
from pathlib import Path

from scripts.whitelist_to_import import convert

DATA = Path("src/apps/result/data")


def test_character_snapshot_converts_fully():
    raw = json.loads((DATA / "whitelist_character.json").read_text())
    rows = convert("character", raw)
    assert len(rows) == 244
    r0 = next(r for r in rows if r["name"] == "博丽灵梦")
    assert r0["old_id"] == "4068b1c2" and r0["sort_order"] == 0
    assert r0["work"] == "东方灵异传"        # work[0]
    assert all(set(r) <= {"name", "name_jp", "type", "old_id", "work",
                          "work_type", "sort_order", "first_appearance"}
               for r in rows)


def test_music_snapshot_converts_fully():
    raw = json.loads((DATA / "whitelist_music.json").read_text())
    rows = convert("music", raw)
    assert len(rows) == 612
    assert all(r.get("old_id") for r in rows)
    # 音乐 work ← album
    sample = next(r for r in rows if r["name"] == "A Sacred Lot")
    assert sample["work"] == "东方灵异传"
```

- [ ] **Step 2: 确认失败** → Run: `python3 -m pytest tests/unit/test_whitelist_converter.py -q`

- [ ] **Step 3: 实现**：`convert` 映射 —— `old_id←id`、`sort_order←system_id`、
  `name/name_jp` 直搬、`type←kind[0]`（缺省 "others"）、`work_type←kind[0] 若在
  {"old","new","CD","book","others"} 否则 "others"`、`first_appearance←str(date)`、
  角色 `work←work[0]`（空列表则省略该键）、音乐 `work←album`（None 则省略）。
  值为 None/空的键**不输出**（导入语义=未提供字段不动）。CLI 入口
  `if __name__ == "__main__":`，参数一个（category），stdout 打 JSON。

- [ ] **Step 4: 全量 + flake8（scripts/ 不在 CI lint 内但也顺手过）+ Commit**

```bash
python3 -m pytest tests/ -q && python3 -m flake8 src/ scripts/whitelist_to_import.py
git add -A && git commit -m "feat(tally): 快照→导入格式转换器(纯函数+CLI,244/612 全量断言)"
```

---

### Task 6: 接线切换 — compute_service/resolver 改 DB 白名单，JSON loader 退役

**Files:**
- Modify: `src/apps/result/compute_service.py`（DB 加载 + WHITELIST_EMPTY + dropped 日志）
- Modify: `src/api/graphql/resolvers/result_compat.py`（去掉 `load_whitelist` 依赖，CP 名字改读 `member_names`）
- Modify: `src/apps/result/whitelist.py`（删除 DEPRECATED 的 JSON `load_whitelist`/`_to_entry`）
- Create: `tests/integration/conftest_voteables.py` 种子 helper（或并入既有 `tests/integration/conftest.py`）
- Modify: `tests/integration/test_result_compat_rest.py`、`tests/integration/test_result_compat_ranking.py`、`tests/integration/test_result_compute.py`（种子 + 断言适配）

**Interfaces:**
- Consumes: Task 2 `load_whitelist_db`、Task 3 `member_names`/`dropped`、Task 4 导入服务、Task 5 `convert`。
- Produces: `async def seed_voteables_from_snapshot(session, category, vote_year)`（测试 helper：`convert()` 快照 → `VoteableImportService.run(dry_run=False)`，dogfooding 导入通道）。

- [ ] **Step 1: 写种子 helper**（放 `tests/integration/conftest.py`）：

```python
async def seed_voteables_from_snapshot(session, category: str, vote_year: int):
    import json as _json
    from pathlib import Path
    from scripts.whitelist_to_import import convert
    from src.apps.admin.voteable_import_service import VoteableImportService

    raw = _json.loads(
        (Path("src/apps/result/data") / f"whitelist_{category}.json").read_text()
    )
    svc = VoteableImportService(session)
    result = await svc.run(category, vote_year, "json",
                           _json.dumps(convert(category, raw)), dry_run=False)
    assert not result.get("conflicts")
    await session.commit()
```

- [ ] **Step 2: compute_service 切换**（`compute_service.py:77-78`）：

```python
            char_wl = await load_whitelist_db(
                self.dao.session, "character", vote_year)
            music_wl = await load_whitelist_db(
                self.dao.session, "music", vote_year)
            if not char_wl.entries and not music_wl.entries:
                raise AppException("WHITELIST_EMPTY", details=500)
```

（import 行同步改；`AppException` 从 `src.common.exceptions` import。）
compute 结束处把 `char_global["dropped"]`/`music_global["dropped"]`/`cp_global["dropped"]`
汇总为一条 `logger.info("compute dropped tokens: %s", ...)`。

- [ ] **Step 3: result_compat 摘除 whitelist**：`_cp_ranking_entry_from_dict(e, char_whitelist)`
  的两个调用点（`result_compat.py:271`、`:316` 附近）删掉 `load_whitelist` 调用，函数签名去掉
  whitelist 参数，内部原先 `whitelist.name_of(member)` 的地方改为
  `names = e.get("member_names") or list(e.get("members", []))`（按位置取）。顶部 import 行清理。

- [ ] **Step 4: 三个集成测试文件适配**：在各自 seed fixture（现在直接插 raw_* 票的那些）里先
  `await seed_voteables_from_snapshot(session, "character", <该测试用的 vote_year>)`（音乐用例同理）。
  原 `load_whitelist("character")` 的期望值推导改为读快照 JSON 自行构造（或改用
  `await load_whitelist_db(session, ...)`）。断言口径不变——**8-hex 票在 DB 白名单
  (old_id 已回填)下归票结果必须与改造前相同**；如个别断言涉及 `ids` 集合形态
  （canonical token 化），按新语义修正并在断言旁注释原因。

- [ ] **Step 5: 删除 whitelist.py 的 DEPRECATED JSON loader**，全仓 grep
  `load_whitelist(`（旧同步版）确认零残留。

- [ ] **Step 6: 全量测试 + flake8 + Commit**

```bash
python3 -m pytest tests/ -q && python3 -m flake8 src/
git add -A && git commit -m "feat(tally): compute/resolver 切 DB 白名单,JSON loader 退役,集成测试走导入通道种子"
```

---

### Task 7: candidate_id 加法式输出（REST schema + GraphQL 契约）

**Files:**
- Modify: `src/apps/result/schemas.py`（`RankingEntity` 加 `candidate_id: Optional[int] = None`）
- Modify: `src/apps/result/compute.py`（排名条目 dict 加 `"candidate_id": int`；CP 条目加 `"member_candidate_ids": list[int]`）
- Modify: `src/api/graphql/types.py`（`RankingEntry`/`CPRankingEntry` 加 `candidate_id: Optional[int]` 字段，strawberry 自动出 camelCase `candidateId`）
- Modify: `src/api/graphql/resolvers/result_compat.py`（`_ranking_entry_from_dict` 映射 `candidate_id=d.get("candidate_id")`；CP 同理）
- Test: `tests/contract/test_result_candidate_id.py`（新建）

**Interfaces:**
- Consumes: Task 3 canonical key（`int(oid)` 即 candidate_id）。
- Produces: GraphQL SDL `RankingEntry.candidateId: Int`（可空）；REST 排名 JSON 含 `candidate_id`。

- [ ] **Step 1: 失败测试**：

```python
def test_sdl_has_candidate_id(graphql_schema_sdl):  # 参考既有 contract 测试的 schema fixture
    assert "candidateId" in graphql_schema_sdl

def test_compute_output_carries_candidate_id():
    # 复用 test_canonical_aggregation 的 _wl/votes 构造,断言
    # ranking 条目 entry["candidate_id"] == 22 且 entry["id"] == "4068b1c2"
```

（contract fixture 名以 `tests/contract/test_captcha_contract.py` 现行写法为准，照抄其 schema 获取方式。）

- [ ] **Step 2: 确认失败 → 实现 → 全量绿**。compute 侧：条目构造处 `"candidate_id": int(oid)`；
  CP `"member_candidate_ids": [int(m) for m in key]`。GraphQL 类型字段一律 `Optional`、默认 None。

- [ ] **Step 3: flake8 + Commit**

```bash
git add -A && git commit -m "feat(result): 排名输出加法式新增 candidate_id/candidateId(id 语义不变)"
```

---

### Task 8: admin voteables 查看/编辑端点

**Files:**
- Create: `src/apps/admin/voteable_admin_service.py`
- Modify: `src/apps/admin/router.py`（三个端点）
- Test: `tests/integration/test_voteable_admin.py`（新建）

**Interfaces:**
- Produces:
  - `GET /api/v1/admin/voteables?category=&q=&vote_year=&page=1&page_size=50`
    → `{items: [{voteableId, name, nameJp, type, firstAppearance, aliases, workId,
    workName, oldId, years: [{voteYear, candidateId, sortOrder}]}], total}`
  - `POST /api/v1/admin/voteables/{category}/{voteable_id}` body 任意子集
    `{name, name_jp, type, first_appearance, aliases, work_id, old_id}` → `{ok: true}`；
    old_id 与他行冲突 → 409 `OLD_ID_CONFLICT`；行不存在 → 404
  - `POST /api/v1/admin/candidates/{category}/{candidate_id}/sort-order`
    body `{sort_order: int | null}` → `{ok: true}`
- Consumes: Task 1 列；Task 4 的测试 fixture 风格。

- [ ] **Step 1: 失败测试**（独立函数，种子用 Task 6 helper 或手插少量行）：
  ① 列表分页/`q` 按 name 模糊过滤/`vote_year` 过滤 years 命中；② 编辑 name+work_id
  后 GET 反映新值；③ old_id 撞他行 → 409；④ 不存在 id → 404；⑤ sort-order 端点
  改值后列表 years 里可见；⑥（鉴权由全局闸门覆盖，无需单测）。

- [ ] **Step 2: 确认失败 → 实现**。service 模式照 `work_service.py`（session 注入、
  select/count 分页）；编辑端点写操作后照 works 端点清 vote-objects 缓存
  （`await _clear_vote_objects_cache(redis)`，import 端点 Task 4 也补同款——列表数据
  改了缓存必须失效）。

- [ ] **Step 3: 全量 + flake8 + Commit**

```bash
git add -A && git commit -m "feat(admin): voteables 列表/编辑/sort-order 端点(B-057① 收口)"
```

---

### Task 9: 文档 + 收尾验证（Phase 1 完成线）

**Files:**
- Modify: `docs/CHANGELOG.md`（新条目）、`docs/BACKLOG.md`（B-050-后补6 置✅、B-057①②置✅）、
  `docs/superpowers/specs/2026-07-23-tally-db-truth-source-design.md`（状态行 → Phase 1 已实现）

- [ ] **Step 1: CHANGELOG 条目**（Added: 0016/导入端点/admin 端点/candidate_id 字段/转换器；
  Changed: 白名单数据源 JSON→DB、CP member_names 入缓存 dict；兼容性: 部署后需先
  快照导入再重跑 compute（§八时序）、`result:*` 缓存需重算、快照 JSON 退役为 fixture）。
- [ ] **Step 2: BACKLOG 更新**（对应行置✅+日期；「维护规则」不删行）。
- [ ] **Step 3: 终验**：

```bash
python3 -m pytest tests/ -q          # 全绿
python3 -m flake8 src/               # exit 0
git add -A && git commit -m "docs(tally): CHANGELOG/BACKLOG/设计稿状态收尾(Phase 1)"
```

---

### Task 10（Phase 2）: admin-ui VoteablesView

**Files:**
- Create: `admin-ui/src/api/voteables.ts`、`admin-ui/src/views/VoteablesView.vue`
- Modify: `admin-ui/src/router.ts`（加路由）、导航入口（照 WorksView 挂法，grep `WorksView` 找到 nav 位置同步加）
- Build 产物: `src/admin_ui/`（`cd admin-ui && pnpm install && pnpm build`，dist 提交）

**Interfaces:**
- Consumes: Task 8 端点 + Task 4 import 端点。
- Produces: `/admin-ui` 下「投票对象」页。

- [ ] **Step 1: api client**（照 `admin-ui/src/api/works.ts` 的 client 封装写）：
  `listVoteables(params)` / `updateVoteable(category, id, body)` /
  `setSortOrder(category, candidateId, sortOrder)` / `importVoteables(body)`。
- [ ] **Step 2: VoteablesView.vue**（照 `WorksView.vue` 的表格/弹窗模式）：
  category 切换 tab + 搜索框 + 年份筛选；表格列 name/name_jp/type/work/old_id
  （空值黄色高亮）/years+sortOrder；行内「编辑」弹窗（Task 8 字段全集，work 下拉
  数据来自既有 works api）；页顶「导入」按钮 → 弹窗（textarea 粘贴 JSON/CSV +
  format/vote_year 选择 → dry-run 报告表格分组展示 create/update/conflicts →
  「确认执行」二次提交 `dry_run=false`）。
- [ ] **Step 3: 路由+导航**：router.ts 加 `/voteables`；nav 与 WorksView 并列加「投票对象」。
- [ ] **Step 4: 构建 + 手验 + Commit**：

```bash
cd admin-ui && pnpm install && pnpm build && cd ..
git add admin-ui/ src/admin_ui/
git commit -m "feat(admin-ui): VoteablesView 投票对象查看/编辑/导入(Phase 2)"
```

（构建失败即修复后重跑；无前端测试框架，验收=build 通过 + 端点联通由 Task 8 集成测试背书。）

---

## Self-Review 记录

- 覆盖检查：设计稿 §三→Task1、§四→Task2/3/6、§五→Task4/5、§六→Task8/10、§七→Task7、§八→Task9 文档、§十→各任务测试步骤。无遗漏。
- 占位符：无 TBD/省略；Task 4 Step 3 为结构化伪码但逐分支写明行为。
- 类型一致性：`canonical() -> str|None`、`WhitelistEntry` 十字段位置序、`member_names`/`member_candidate_ids`/`dropped` 三键名在 Task 3/6/7 间一致。
