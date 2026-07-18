# B-050 记票/结果重写 v1（核心排名闭环）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让离线批量计票（管理台 `POST /admin/compute-results` 已存在）改为**读真实提交表 `raw_*`、按角色 id 归票、白名单丢未知 id、CP 无序 multiset**，并把名次/加权口径对齐官方结果页需求文档。

**Architecture:** 计票仍是三层：`compute.py`（纯函数算法）/ `compute_dao.py`（DB 边界）/ `compute_service.py`（编排 + 写 Redis）。改动高度局部化——`compute_dao.load_*_votes` 从死表 `character/music/cp` 换成真表 `raw_character/raw_music/raw_cp`（返回元组形状 `(vote_id, created_at, items)` **不变**）；新增一个 id 白名单/注册表（从前端 `character.ts`/`music.ts` 提取的 JSON 快照 + Python 加载器），compute 函数把分组键从"把 id 当名字"改成"按 id 归票 + 白名单过滤 + id→名 展示"，并修正排序（票数→本命数→系统ID）、本命加权（票数+本命数）、CP key（有序 multiset）。对外发榜契约保持 **name-facing**（新增可选 `id` 字段，不删 `name`）。

**Tech Stack:** Python 3 (typed) · FastAPI · SQLAlchemy async · Redis · pytest（测试跑在 sqlite 上，禁用 PG-only SQL）· Node（一次性提取脚本）。

## Global Constraints

以下为项目级硬约束，每个任务都隐含适用（值来自权威结果页需求文档 `docs/VoileLabs-...-投票结果页面.md` 与 B-050 设计稿 `docs/superpowers/specs/2026-07-18-result-recount-id-based-design.md` §八）：

- **按 id 归票**：角色/音乐票的对象身份是前端 8-hex `id`（存在 `raw_*.payload` 每个元素的 `"id"` 字段）。以 id 归票，不再"把 id 当名字"。
- **白名单丢未知**：计票时，角色/音乐票中 id 不在白名单的**单个对象丢弃**；CP 票中**任一成员 id 不在白名单则整条 CP 丢弃**。
- **CP key = 无序 multiset**：`tuple(sorted([id_a, id_b, id_c?去None]))`（保留重复，支持自 CP 如 (A,A)）；`active`（主动方）、`first`、顺序**都不进 key**。
- **名次口径**：默认按**票数**降序定名次；**同票数=同名次**；同名次内展示顺序按 **本命数** 降序、再按 **系统ID** 升序（CP 用角色A的系统ID）；**并列占虚位**（下一个不同票数的名次 = 其列表下标+1）。
- **系统ID** = 该对象在前端 `characterList`/`musicList` 冻结列表中的**位置序号**（0 起），随白名单快照一起提取。
- **指标口径**：票数=含该对象的有效票数；本命数=本命位为该对象的有效票数；本命率=本命数÷票数；**本命加权=票数+本命数**；票数占比=票数÷有效票数（有效票数=该部门投票账号数）；本命占比=本命数÷本命票数（本命票数=该部门填了本命位的账号数=`sum(first_count)`）。
- **CP 额外**：`组合票数==1 不计入`（保留 vote_count≥2）；A/B/C主动率+无主动率之和=100%（按排序后位置算）；展示名 = `名A×名B[×名C]`。
- **有效票取最新**：同一 `vote_id` 在同一类别只取**最新一次提交**（实时路径 delete-then-insert 已只留一行；legacy-sync 可能多行，需 dedup）。排除 `invalidated == True` 的行。**dedup 用 Python 侧完成，禁用 PG-only 的 `DISTINCT ON`（测试跑 sqlite）**。
- **对外契约**：发榜/最终榜/结果页保持 name-facing。可**新增** `id` 字段，**不得删除或改语义** `name`。
- **v1 后补（本计划不做，喂空/退化值即可）**：性别男女票（gender_map 传空 → male/female=0）、trend 演进（raw_* 改票已删历史，无法复刻，degenerate 可接受）、上届对比（historical 传空）、问卷结果、高级搜索。这些代码路径**保留但喂空**，不在本计划验证。

---

## File Structure

| 文件 | 责任 | 动作 |
|---|---|---|
| `scripts/extract_whitelist.mjs` | 一次性：从前端 `character.ts`/`music.ts` 提取 id/name/名_jp/work/kind/date/album/系统ID → JSON 快照 | Create |
| `src/apps/result/data/whitelist_character.json` | 角色白名单快照（提交入库，运行时只读它，不依赖前端仓库） | Create（脚本产出） |
| `src/apps/result/data/whitelist_music.json` | 音乐白名单快照 | Create（脚本产出） |
| `src/apps/result/whitelist.py` | 运行时白名单/注册表：`WhitelistEntry`/`Whitelist`/`load_whitelist(category)` | Create |
| `src/apps/result/compute_dao.py` | DB 边界：`load_*_votes` 改读 `raw_*` | Modify |
| `src/apps/result/compute.py` | 纯算法：`compute_ranking`/`compute_cp_ranking` 改 id 归票 + 白名单 + 排序/加权口径 + CP multiset | Modify |
| `src/apps/result/compute_service.py` | 编排：加载白名单、传参、gender/historical 喂空 | Modify |
| `src/apps/result/schemas.py` | `RankingEntity` 新增可选 `id` | Modify |
| `tests/unit/test_whitelist.py` | 白名单加载器单测 | Create |
| `tests/unit/test_compute_ranking_id.py` | 角色/音乐 id 归票排序单测 | Create |
| `tests/unit/test_compute_cp_ranking_id.py` | CP multiset/主动率单测 | Create |
| `tests/integration/test_compute_dao_raw.py` | `load_*_votes` 读 raw_* 集成测 | Create |
| `tests/integration/test_compute_pipeline_v1.py` | 端到端 compute_all → Redis 集成测 | Create |

---

## Task 1: id 白名单快照 + 加载器

**Files:**
- Create: `scripts/extract_whitelist.mjs`
- Create（脚本产出并提交）: `src/apps/result/data/whitelist_character.json`, `src/apps/result/data/whitelist_music.json`
- Create: `src/apps/result/whitelist.py`
- Test: `tests/unit/test_whitelist.py`

**Interfaces:**
- Produces:
  - JSON 快照条目：`{"id": str, "name": str, "name_jp": str, "work": list[str], "kind": list[str], "date": int|None, "album": str|None, "system_id": int}`
  - `WhitelistEntry`（dataclass, frozen）字段：`id, name, name_jp, origin, type, first_appearance, album, system_id`
  - `class Whitelist`：`ids: set[str]`（property），`__contains__(oid) -> bool`，`get(oid) -> WhitelistEntry | None`，`name_of(oid) -> str`（未知返回 oid 原样），`system_id_of(oid) -> int`（未知返回一个大常量 `10**9`，保证未知排最后）
  - `load_whitelist(category: Literal["character","music"]) -> Whitelist`（读同目录 `data/whitelist_{category}.json`，可 `@lru_cache`）

- [ ] **Step 1: 写提取脚本 `scripts/extract_whitelist.mjs`**

前端 `characterList`/`musicList` 是纯对象字面量数组（无函数调用/`new`），用 `new Function` 安全求值数组字面量。字段直接透传，`system_id` = 数组下标；**不在这里做 kind→type 映射**（留给 Python 加载器统一处理）。

```js
// scripts/extract_whitelist.mjs
// 用法: node scripts/extract_whitelist.mjs <前端仓库根> <后端仓库根>
// 例:   node scripts/extract_whitelist.mjs /data/sunyunbo/www/Touhou-Vote /data/sunyunbo/www/Thvote-be/thvote-be-re
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const [frontRoot, backRoot] = process.argv.slice(2);
if (!frontRoot || !backRoot) {
  console.error('usage: node extract_whitelist.mjs <frontRoot> <backRoot>');
  process.exit(1);
}

function extractArray(tsText, varName) {
  // 取 "<varName>...= [" 后到匹配 "]" 的数组字面量文本
  const start = tsText.indexOf('[', tsText.indexOf(varName));
  if (start < 0) throw new Error(`array for ${varName} not found`);
  let depth = 0, i = start;
  for (; i < tsText.length; i++) {
    const ch = tsText[i];
    if (ch === '[') depth++;
    else if (ch === ']') { depth--; if (depth === 0) { i++; break; } }
  }
  const literal = tsText.slice(start, i);
  // 纯对象字面量数组，安全求值
  return new Function(`return (${literal});`)();
}

function build(list, kind /* 'character'|'music' */) {
  return list.map((e, idx) => ({
    id: String(e.id),
    name: String(e.name ?? ''),
    name_jp: String(e.origname ?? ''),
    work: kind === 'character' ? (e.work ?? []) : [],
    kind: e.kind ?? [],
    date: typeof e.date === 'number' ? e.date : null,
    album: kind === 'music' ? (e.album ?? null) : null,
    system_id: idx,
  }));
}

const charTs = readFileSync(join(frontRoot, 'packages/shared/data/character.ts'), 'utf8');
const musicTs = readFileSync(join(frontRoot, 'packages/shared/data/music.ts'), 'utf8');

const chars = build(extractArray(charTs, 'characterList'), 'character');
const musics = build(extractArray(musicTs, 'musicList'), 'music');

const outDir = join(backRoot, 'src/apps/result/data');
mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, 'whitelist_character.json'), JSON.stringify(chars, null, 2) + '\n');
writeFileSync(join(outDir, 'whitelist_music.json'), JSON.stringify(musics, null, 2) + '\n');
console.log(`characters=${chars.length} musics=${musics.length}`);
```

- [ ] **Step 2: 运行提取脚本并核对数量**

Run:
```bash
node scripts/extract_whitelist.mjs /data/sunyunbo/www/Touhou-Vote /data/sunyunbo/www/Thvote-be/thvote-be-re
```
Expected: 打印 `characters=244 musics=<N>`（角色**必须**=244，与已知 candidate_character 一致；音乐 N 记录下来，写进 changelog）。若 `characters` 不是 244，停下排查（前端 array 结构变了，脚本 `extractArray` 需调整），不要继续。

- [ ] **Step 3: 写加载器 `src/apps/result/whitelist.py`**

```python
"""id 白名单 / 展示注册表（B-050）。

数据来源：从前端 characterList/musicList 提取的冻结快照 JSON
（scripts/extract_whitelist.mjs 产出）。运行时只读快照，不依赖前端仓库。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

_DATA_DIR = Path(__file__).parent / "data"
_UNKNOWN_SYSTEM_ID = 10**9  # 未知 id 排最后（正常不该走到，白名单已先过滤）

# 前端 kind → 展示用 type（与 compute.KIND_MAPPING 一致，避免循环 import 这里内联）
_KIND_MAPPING: dict[str, str] = {
    "old": "旧作", "new": "新作", "CD": "专辑", "book": "出版物",
    "others": "其他", "other": "其他", "game": "游戏",
}


@dataclass(frozen=True)
class WhitelistEntry:
    id: str
    name: str
    name_jp: str
    origin: str
    type: str
    first_appearance: str | None
    album: str | None
    system_id: int


def _to_entry(raw: dict) -> WhitelistEntry:
    kinds = raw.get("kind") or []
    work = raw.get("work") or []
    date = raw.get("date")
    return WhitelistEntry(
        id=str(raw["id"]),
        name=raw.get("name", ""),
        name_jp=raw.get("name_jp", ""),
        origin="、".join(work) if work else "",
        type=_KIND_MAPPING.get(kinds[0], "其他") if kinds else "未知",
        first_appearance=str(date) if date else None,
        album=raw.get("album"),
        system_id=int(raw.get("system_id", _UNKNOWN_SYSTEM_ID)),
    )


class Whitelist:
    def __init__(self, entries: list[WhitelistEntry]):
        self._by_id: dict[str, WhitelistEntry] = {e.id: e for e in entries}

    @property
    def ids(self) -> set[str]:
        return set(self._by_id.keys())

    def __contains__(self, oid: str) -> bool:
        return oid in self._by_id

    def get(self, oid: str) -> WhitelistEntry | None:
        return self._by_id.get(oid)

    def name_of(self, oid: str) -> str:
        e = self._by_id.get(oid)
        return e.name if e else oid

    def system_id_of(self, oid: str) -> int:
        e = self._by_id.get(oid)
        return e.system_id if e else _UNKNOWN_SYSTEM_ID


@lru_cache(maxsize=4)
def load_whitelist(category: Literal["character", "music"]) -> Whitelist:
    path = _DATA_DIR / f"whitelist_{category}.json"
    raw_list = json.loads(path.read_text(encoding="utf-8"))
    return Whitelist([_to_entry(r) for r in raw_list])
```

- [ ] **Step 4: 写单测 `tests/unit/test_whitelist.py`**

```python
from src.apps.result.whitelist import Whitelist, WhitelistEntry, load_whitelist


def _wl() -> Whitelist:
    return Whitelist([
        WhitelistEntry("aaaa1111", "博丽灵梦", "博麗霊夢", "东方红魔乡", "旧作", "19961103", None, 0),
        WhitelistEntry("bbbb2222", "雾雨魔理沙", "霧雨魔理沙", "东方封魔录", "旧作", "19970815", None, 1),
    ])


def test_contains_and_ids():
    wl = _wl()
    assert "aaaa1111" in wl
    assert "zzzz9999" not in wl
    assert wl.ids == {"aaaa1111", "bbbb2222"}


def test_name_and_system_id_lookup():
    wl = _wl()
    assert wl.name_of("aaaa1111") == "博丽灵梦"
    assert wl.system_id_of("bbbb2222") == 1
    # 未知 id：name 原样返回、system_id 巨大（排最后）
    assert wl.name_of("zzzz9999") == "zzzz9999"
    assert wl.system_id_of("zzzz9999") == 10**9


def test_load_real_snapshot_character_count():
    wl = load_whitelist("character")
    assert len(wl.ids) == 244  # 与 candidate_character 一致
    # 系统ID 覆盖 0..243 连续
    sids = sorted(wl.system_id_of(i) for i in wl.ids)
    assert sids[0] == 0 and sids[-1] == 243


def test_load_real_snapshot_music_nonempty():
    wl = load_whitelist("music")
    assert len(wl.ids) > 0
```

- [ ] **Step 5: 跑测试**

Run: `pytest tests/unit/test_whitelist.py -v`
Expected: PASS（含真实快照的 244 计数）。

- [ ] **Step 6: 提交**

```bash
git add scripts/extract_whitelist.mjs src/apps/result/data/ src/apps/result/whitelist.py tests/unit/test_whitelist.py
git commit -m "feat(b050): id 白名单快照(前端提取) + 运行时加载器"
```

---

## Task 2: `compute_dao.load_*_votes` 改读 `raw_*`

**Files:**
- Modify: `src/apps/result/compute_dao.py`（`load_char_votes`/`load_music_votes`/`load_cp_votes` + imports）
- Test: `tests/integration/test_compute_dao_raw.py`

**Interfaces:**
- Consumes: `RawCharacterSubmit`/`RawMusicSubmit`/`RawCPSubmit`（`src/db_model/raw_submit.py`，列：`vote_id, attempt, created_at, invalidated, payload`）。
- Produces（**形状不变**）：`load_char_votes()/load_music_votes()/load_cp_votes() -> list[tuple[str, datetime, list[dict]]]` = `(vote_id, created_at, payload_items)`；已排除 `invalidated`，每个 `vote_id` 仅保留最新一次提交。

- [ ] **Step 1: 写失败集成测 `tests/integration/test_compute_dao_raw.py`**

用现有测试的 DB fixture（sqlite）。插入：一个正常提交、一个同 `vote_id` 的更新（模拟 legacy 多行，`created_at` 更晚应取它）、一个 `invalidated=True`（应排除）、一个 legacy `list[str]` payload（应被 `_normalize_items` 转成 dict）。

```python
import pytest
from datetime import datetime, timezone, timedelta

from src.apps.result.compute_dao import ComputeDAO
from src.db_model.raw_submit import RawCharacterSubmit


@pytest.mark.asyncio
async def test_load_char_votes_latest_only_and_excludes_invalidated(db_session):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add_all([
        # voteA 旧提交
        RawCharacterSubmit(vote_id="voteA", attempt=1, created_at=base,
                           user_ip="x", payload=[{"id": "aaaa1111", "first": False}]),
        # voteA 新提交（同 vote_id，更晚）→ 应只取这条
        RawCharacterSubmit(vote_id="voteA", attempt=2, created_at=base + timedelta(hours=1),
                           user_ip="x", payload=[{"id": "bbbb2222", "first": True}]),
        # voteB 被作废 → 应排除
        RawCharacterSubmit(vote_id="voteB", attempt=1, created_at=base,
                           user_ip="x", invalidated=True,
                           payload=[{"id": "aaaa1111", "first": False}]),
        # voteC legacy list[str] payload → 归一化
        RawCharacterSubmit(vote_id="voteC", attempt=1, created_at=base,
                           user_ip="x", payload=["aaaa1111"]),
    ])
    await db_session.commit()

    dao = ComputeDAO(db_session)
    votes = await dao.load_char_votes()
    by_vote = {vid: items for vid, _, items in votes}

    assert "voteB" not in by_vote  # invalidated 排除
    assert by_vote["voteA"] == [{"id": "bbbb2222", "first": True}]  # 只取最新
    assert by_vote["voteC"] == [{"id": "aaaa1111", "first": False, "reason": None}]  # 归一化
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/integration/test_compute_dao_raw.py -v`
Expected: FAIL（当前 `load_char_votes` 读死表 `Character`，返回空/报错）。

- [ ] **Step 3: 改 `compute_dao.py`**

改 imports（去掉死表 `Character/Music/Cp`，加 raw 模型）：

```python
from src.db_model.raw_submit import (
    RawCharacterSubmit,
    RawCPSubmit,
    RawMusicSubmit,
)
from src.db_model.candidate import CandidateCharacter, CandidateMusic, FinalRanking
from src.db_model.questionnaire import Questionnaire
```
（保留 `_normalize_items`、`CandidateMeta` import 不变。删除 `from src.db_model.character import Character` 等三行死表 import。）

加一个可复用的私有归并方法，然后三个 `load_*_votes` 改用它：

```python
    @staticmethod
    def _latest_per_vote(rows) -> list[tuple[str, datetime, list[dict]]]:
        """按 vote_id 取最新一行（created_at desc, attempt desc 兜底），排除 invalidated。
        Python 侧 dedup（sqlite/PG 通吃，不用 DISTINCT ON）。
        """
        # created_at desc, coalesce(attempt,0) desc → 先出现的即最新
        ordered = sorted(
            rows,
            key=lambda r: (r.created_at, r.attempt or 0),
            reverse=True,
        )
        seen: dict[str, tuple[str, datetime, list[dict]]] = {}
        for r in ordered:
            if r.invalidated:
                continue
            if r.vote_id in seen:
                continue
            seen[r.vote_id] = (r.vote_id, r.created_at, _normalize_items(r.payload))
        return list(seen.values())

    async def load_char_votes(self) -> list[tuple[str, datetime, list[dict]]]:
        rows = (await self.session.execute(select(RawCharacterSubmit))).scalars().all()
        return self._latest_per_vote(rows)

    async def load_music_votes(self) -> list[tuple[str, datetime, list[dict]]]:
        rows = (await self.session.execute(select(RawMusicSubmit))).scalars().all()
        return self._latest_per_vote(rows)

    async def load_cp_votes(self) -> list[tuple[str, datetime, list[dict]]]:
        rows = (await self.session.execute(select(RawCPSubmit))).scalars().all()
        return self._latest_per_vote(rows)
```

> 说明：`_normalize_items` 对 CP 也适用——CP payload 元素本就是 dict（`{id_a,id_b,...}`），不是 str，`_normalize_items` 原样保留 dict。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/integration/test_compute_dao_raw.py -v`
Expected: PASS。

- [ ] **Step 5: 跑既有 compute 相关测试确保没炸**

Run: `pytest tests/ -k "compute" -v`
Expected: 现存 compute 测试若断言了旧死表行为会失败——这些属于本迁移的预期变化，记录下来交给 Task 5 一并修（此处只需确认没有 import 错误等硬崩）。

- [ ] **Step 6: 提交**

```bash
git add src/apps/result/compute_dao.py tests/integration/test_compute_dao_raw.py
git commit -m "feat(b050): compute_dao 改读 raw_* 真表(取最新/排除作废/归一化)"
```

---

## Task 3: `compute_ranking` 改 id 归票 + 白名单 + 口径修正（角色/音乐）

**Files:**
- Modify: `src/apps/result/compute.py`（`compute_ranking` + 保留 `CandidateMeta`）
- Test: `tests/unit/test_compute_ranking_id.py`

**Interfaces:**
- Consumes: `Whitelist`（Task 1）；votes 形状 `(vote_id, created_at, items)`，item = `{"id": str, "first": bool, "reason": str|None}`。
- Produces（签名变化）：
  `compute_ranking(votes, whitelist: Whitelist, gender_map: dict, historical: dict, vote_start, total_hours) -> tuple[list[dict], dict]`
  —— 删去旧的 `candidates`（改 `whitelist`）与 `name_remap`（id 归票不需要名字归并）。输出 entry 新增 `"id"` 字段；`name` = `whitelist.name_of(id)`。

**关键口径（Global Constraints 落地）：**
- 分组键 = `oid = item["id"]`；`if oid not in whitelist: continue`（丢未知）。
- 排序：`sorted(all_ids, key=lambda o: (-vote_count[o], -first_count[o], whitelist.system_id_of(o)))`。
- display_rank：**按 vote_count 变化**判定（同票数同名次、虚位）。
- `favorite_vote_count_weighted = vote_count + first_count`。
- 新增 `favorite_percentage_of_all = first_count / total_first`（本命占比），`total_first = sum(first_count.values())`。

- [ ] **Step 1: 写失败单测 `tests/unit/test_compute_ranking_id.py`**

```python
from datetime import datetime, timezone

from src.apps.result.compute import compute_ranking
from src.apps.result.whitelist import Whitelist, WhitelistEntry

VS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _wl():
    return Whitelist([
        WhitelistEntry("id_a", "角色甲", "", "", "旧作", None, None, 0),
        WhitelistEntry("id_b", "角色乙", "", "", "旧作", None, None, 1),
        WhitelistEntry("id_c", "角色丙", "", "", "旧作", None, None, 2),
    ])


def _vote(vid, items):
    return (vid, VS, items)


def test_drops_unknown_ids():
    votes = [_vote("u1", [{"id": "id_a"}, {"id": "UNKNOWN"}])]
    ranking, _ = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    names = {e["name"] for e in ranking}
    assert names == {"角色甲"}  # UNKNOWN 被丢


def test_sort_by_votes_then_first_then_system_id():
    # 甲: 2票0本命; 乙: 2票1本命; 丙: 2票1本命 → 乙丙同票同本命，按系统ID(乙1<丙2)乙在前
    votes = [
        _vote("u1", [{"id": "id_a"}, {"id": "id_b", "first": True}, {"id": "id_c", "first": True}]),
        _vote("u2", [{"id": "id_a"}, {"id": "id_b"}, {"id": "id_c"}]),
    ]
    ranking, _ = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    order = [e["name"] for e in ranking]
    # 乙(2票1本命) / 丙(2票1本命) 在 甲(2票0本命) 之前；乙丙同名次按系统ID
    assert order == ["角色乙", "角色丙", "角色甲"]
    # 乙丙票数相同(2) → display_rank 相同(第1)，甲虚位到第3
    dr = {e["name"]: e["display_rank"] for e in ranking}
    assert dr["角色乙"] == 1 and dr["角色丙"] == 1 and dr["角色甲"] == 3


def test_metrics_weighted_and_ratios():
    # 甲: 3票2本命
    votes = [
        _vote("u1", [{"id": "id_a", "first": True}]),
        _vote("u2", [{"id": "id_a", "first": True}]),
        _vote("u3", [{"id": "id_a"}]),
    ]
    ranking, gstats = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    e = ranking[0]
    assert e["id"] == "id_a" and e["name"] == "角色甲"
    assert e["favorite_vote_count_weighted"] == 3 + 2  # 票数+本命数
    assert e["favorite_percentage"] == 66.67  # 本命率 2/3
    assert e["rank"][0]["vote_count"] == 3
    # 票数占比 = 3/3 账号 = 100%
    assert e["rank"][0]["vote_percentage"] == 100.0


def test_favorite_percentage_of_all():
    # 甲2本命, 乙1本命 → 总本命票=3；甲本命占比=2/3
    votes = [
        _vote("u1", [{"id": "id_a", "first": True}]),
        _vote("u2", [{"id": "id_a", "first": True}]),
        _vote("u3", [{"id": "id_b", "first": True}]),
    ]
    ranking, _ = compute_ranking(votes, _wl(), {}, {}, VS, 1)
    by = {e["name"]: e for e in ranking}
    assert round(by["角色甲"]["favorite_percentage_of_all"], 4) == round(2 / 3, 4)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/test_compute_ranking_id.py -v`
Expected: FAIL（签名不符 / 无 `id` 字段 / 加权口径旧）。

- [ ] **Step 3: 改 `compute_ranking`（`src/apps/result/compute.py`）**

替换 `compute_ranking` 整个函数为下面版本（保留文件顶部 `CandidateMeta`、`_median`、`KIND_MAPPING` 不动；`compute_gender_map` 不动）：

```python
def compute_ranking(
    votes: list[tuple[str, datetime, list[dict]]],
    whitelist: "Whitelist",
    gender_map: dict[str, str],
    historical: dict[str, dict],
    vote_start: datetime,
    total_hours: int,
) -> tuple[list[dict], dict]:
    """按 id 归票的角色/音乐排名（B-050）。

    votes: (vote_id, submit_datetime, items)，item = {"id", "first", "reason"}
    whitelist: id 白名单/展示注册表；不在白名单的 id 直接丢弃。
    历史键仍按 name（final_ranking 是 name-keyed）；v1 传空 dict。
    返回 (ranking_list, global_stats_dict)
    """
    vote_count: dict[str, int] = defaultdict(int)      # 按 oid
    first_count: dict[str, int] = defaultdict(int)
    reasons: dict[str, list[str]] = defaultdict(list)
    male_count: dict[str, int] = defaultdict(int)
    female_count: dict[str, int] = defaultdict(int)
    trend: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    trend_first: dict[str, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    total_voters = len(votes)

    for user_id, submit_dt, items in votes:
        gender = gender_map.get(user_id, "unknown")
        if submit_dt.tzinfo is None:
            submit_dt = submit_dt.replace(tzinfo=timezone.utc)
        hour_bucket = max(0, min(
            int((submit_dt - vote_start).total_seconds() / 3600), total_hours - 1))
        seen_in_vote: set[str] = set()
        for item in items:
            oid = item.get("id", "")
            if not oid or oid not in whitelist:
                continue
            if oid in seen_in_vote:  # 同一账号同一 id 只计一次
                continue
            seen_in_vote.add(oid)
            is_first = bool(item.get("first", False))
            reason = item.get("reason")
            vote_count[oid] += 1
            if is_first:
                first_count[oid] += 1
            if reason:
                reasons[oid].append(reason)
            if gender == "male":
                male_count[oid] += 1
            elif gender == "female":
                female_count[oid] += 1
            trend[oid][hour_bucket] += 1
            if is_first:
                trend_first[oid][hour_bucket] += 1

    all_ids = set(vote_count.keys())
    total_votes = sum(vote_count.values())
    total_first = sum(first_count.values())

    # 名次：票数→本命数→系统ID
    sorted_ids = sorted(
        all_ids,
        key=lambda o: (-vote_count[o], -first_count[o], whitelist.system_id_of(o)),
    )

    ranking = []
    prev_vc = None
    prev_display_rank = 0
    for i, oid in enumerate(sorted_ids):
        vc = vote_count[oid]
        fc = first_count[oid]
        if vc != prev_vc:            # 同票数同名次；不同则虚位递推
            prev_display_rank = i + 1
            prev_vc = vc
        vp = vc / total_voters if total_voters else 0.0
        fp = fc / vc if vc else 0.0
        fpa = fc / total_first if total_first else 0.0

        rank_snapshots = [{
            "rank": i + 1,
            "vote_count": vc,
            "favorite_vote_count": fc,
            "favorite_percentage": int(fp * 100),
            "vote_percentage": round(vp * 100, 2),
        }]
        hist = historical.get(whitelist.name_of(oid), {})
        for suffix in ("1", "2"):
            if hist.get(f"rank_{suffix}"):
                hvc = hist[f"votes_{suffix}"]
                hfc = hist[f"first_{suffix}"]
                rank_snapshots.append({
                    "rank": hist[f"rank_{suffix}"],
                    "vote_count": hvc,
                    "favorite_vote_count": hfc,
                    "favorite_percentage": int(hfc / hvc * 100) if hvc else 0,
                    "vote_percentage": 0.0,
                })

        mc = male_count[oid]
        fc_gender = female_count[oid]
        meta = whitelist.get(oid)
        name = meta.name if meta else oid

        ranking.append({
            "rank": rank_snapshots,
            "display_rank": prev_display_rank,
            "id": oid,
            "name": name,
            "favorite_vote_count_weighted": vc + fc,
            "type": (meta.type if meta else "") or "未知",
            "origin": (meta.origin if meta else "") or "未知",
            "first_appearance": (meta.first_appearance if meta else "") or "",
            "album": (meta.album if meta else "") or "",
            "name_jp": (meta.name_jp if meta else "") or "",
            "favorite_percentage": round(fp * 100, 2),
            "favorite_percentage_of_all": round(fpa * 100, 2),
            "male_vote_count": {
                "vote_count": mc,
                "percentage_per_char": round(mc / vc, 4) if vc else 0.0,
                "percentage_per_total": round(mc / total_voters, 4) if total_voters else 0.0,
            },
            "female_vote_count": {
                "vote_count": fc_gender,
                "percentage_per_char": round(fc_gender / vc, 4) if vc else 0.0,
                "percentage_per_total": round(fc_gender / total_voters, 4) if total_voters else 0.0,
            },
            "reasons": reasons[oid],
            "reasons_count": len(reasons[oid]),
            "trend": [{"hrs": h, "cnt": c} for h, c in enumerate(trend[oid]) if c > 0],
            "trend_first": [{"hrs": h, "cnt": c} for h, c in enumerate(trend_first[oid]) if c > 0],
        })

    global_stats = {
        "total_unique_items": len(all_ids),
        "total_first": total_first,
        "total_votes": total_votes,
        "average_votes_per_item": total_votes / len(all_ids) if all_ids else 0.0,
        "median_votes_per_item": _median(list(vote_count.values())),
    }
    return ranking, global_stats
```

在文件顶部 imports 后加类型引用（避免运行时循环 import，用 `TYPE_CHECKING`）：

```python
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from src.apps.result.whitelist import Whitelist
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/test_compute_ranking_id.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/apps/result/compute.py tests/unit/test_compute_ranking_id.py
git commit -m "feat(b050): compute_ranking 改 id 归票+白名单+名次/加权口径(票数→本命→系统ID)"
```

---

## Task 4: `compute_cp_ranking` 改 id 归票 + 无序 multiset + 主动率按位置

**Files:**
- Modify: `src/apps/result/compute.py`（`compute_cp_ranking`）
- Test: `tests/unit/test_compute_cp_ranking_id.py`

**Interfaces:**
- Consumes: `Whitelist`；cp item = `{"id_a","id_b","id_c","active","first","reason"}`。
- Produces（签名变化）：
  `compute_cp_ranking(cp_votes, whitelist: "Whitelist", gender_map, historical, vote_start, total_hours) -> tuple[list[dict], dict]`
  —— 新增 `whitelist` 参数（其余保持）。

**关键口径：**
- 成员 `members = [id_a, id_b] + ([id_c] if id_c)`；**任一 member 不在白名单 → 整条 CP 丢弃**。
- key = `tuple(sorted(members))`（multiset，保留重复）；`active`/`first`/顺序不进 key。
- 排序后位置 A/B/C = `sorted(members)[0/1/2]`；主动率按成员 id 计数后映射到位置；无主动率 = active 为空的占比。
- **丢弃 `vote_count == 1` 的组合**。
- 排序：`(-vote_count, -first_count, whitelist.system_id_of(A))`，A = sorted members[0]；display_rank 按 vote_count 虚位。
- `favorite_vote_count_weighted = vote_count + first_count`；展示 `name = "×".join(名A,名B[,名C])`；`id_a/id_b/id_c` = 排序后成员。

- [ ] **Step 1: 写失败单测 `tests/unit/test_compute_cp_ranking_id.py`**

```python
from datetime import datetime, timezone

from src.apps.result.compute import compute_cp_ranking
from src.apps.result.whitelist import Whitelist, WhitelistEntry

VS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _wl():
    return Whitelist([
        WhitelistEntry("A", "甲", "", "", "旧作", None, None, 0),
        WhitelistEntry("B", "乙", "", "", "旧作", None, None, 1),
        WhitelistEntry("C", "丙", "", "", "旧作", None, None, 2),
    ])


def _v(vid, items):
    return (vid, VS, items)


def test_unordered_key_merges_and_drops_singletons():
    # (A,B) 与 (B,A) 应合并为同一组合；共 2 票（≥2 保留）
    votes = [
        _v("u1", [{"id_a": "A", "id_b": "B"}]),
        _v("u2", [{"id_a": "B", "id_b": "A"}]),
    ]
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, VS, 1)
    assert len(ranking) == 1
    e = ranking[0]
    assert e["id_a"] == "A" and e["id_b"] == "B"  # 排序后
    assert e["name"] == "甲×乙"
    assert e["rank"][0]["vote_count"] == 2


def test_singleton_cp_excluded():
    votes = [_v("u1", [{"id_a": "A", "id_b": "B"}])]  # 只有1票
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, VS, 1)
    assert ranking == []  # 组合票数为1不计入


def test_drop_cp_if_any_member_unknown():
    votes = [
        _v("u1", [{"id_a": "A", "id_b": "UNKNOWN"}]),
        _v("u2", [{"id_a": "A", "id_b": "UNKNOWN"}]),
    ]
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, VS, 1)
    assert ranking == []


def test_active_rates_by_position_sum_100():
    # (A,B) 4票：2票A主动、1票B主动、1票无主动
    votes = [
        _v("u1", [{"id_a": "A", "id_b": "B", "active": "A"}]),
        _v("u2", [{"id_a": "A", "id_b": "B", "active": "A"}]),
        _v("u3", [{"id_a": "A", "id_b": "B", "active": "B"}]),
        _v("u4", [{"id_a": "A", "id_b": "B"}]),
    ]
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, VS, 1)
    e = ranking[0]
    assert e["active_a"] == 0.5    # 2/4
    assert e["active_b"] == 0.25   # 1/4
    assert e["active_c"] == 0.0    # 无C
    assert e["active_none"] == 0.25
    assert round(e["active_a"] + e["active_b"] + e["active_c"] + e["active_none"], 4) == 1.0


def test_self_cp_preserved():
    # (A,A) 自CP：multiset 保留重复，2票
    votes = [
        _v("u1", [{"id_a": "A", "id_b": "A"}]),
        _v("u2", [{"id_a": "A", "id_b": "A"}]),
    ]
    ranking, _ = compute_cp_ranking(votes, _wl(), {}, {}, VS, 1)
    assert len(ranking) == 1
    assert ranking[0]["id_a"] == "A" and ranking[0]["id_b"] == "A"
    assert ranking[0]["name"] == "甲×甲"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/test_compute_cp_ranking_id.py -v`
Expected: FAIL。

- [ ] **Step 3: 改 `compute_cp_ranking`**

替换整个函数：

```python
def compute_cp_ranking(
    cp_votes: list[tuple[str, datetime, list[dict]]],
    whitelist: "Whitelist",
    gender_map: dict[str, str],
    historical: dict[str, dict],
    vote_start: datetime,
    total_hours: int,
) -> tuple[list[dict], dict]:
    """按无序 multiset 归票的 CP 排名（B-050）。

    item: {"id_a","id_b","id_c","active","first","reason"}
    key = tuple(sorted([id_a,id_b,id_c?去None]))；顺序/主动方/first 不进 key。
    任一成员不在白名单 → 整条 CP 丢弃；组合票数==1 不计入。
    """
    vote_count: dict[tuple, int] = defaultdict(int)
    first_count: dict[tuple, int] = defaultdict(int)
    reasons: dict[tuple, list[str]] = defaultdict(list)
    active_count: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    members_of: dict[tuple, list[str]] = {}
    trend: dict[tuple, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    trend_first: dict[tuple, list[int]] = defaultdict(lambda: [0] * max(total_hours, 1))
    total_voters = len(cp_votes)

    for user_id, submit_dt, items in cp_votes:
        if submit_dt.tzinfo is None:
            submit_dt = submit_dt.replace(tzinfo=timezone.utc)
        hour_bucket = max(0, min(
            int((submit_dt - vote_start).total_seconds() / 3600), total_hours - 1))
        seen_in_vote: set[tuple] = set()
        for item in items:
            raw_members = [item.get("id_a", ""), item.get("id_b", "")]
            if item.get("id_c"):
                raw_members.append(item["id_c"])
            if any((not m) or (m not in whitelist) for m in raw_members):
                continue  # 未知成员 → 整条丢
            key = tuple(sorted(raw_members))  # multiset，保留重复
            if key in seen_in_vote:
                continue
            seen_in_vote.add(key)
            is_first = bool(item.get("first", False))
            reason = item.get("reason")
            active = item.get("active") or "none"

            vote_count[key] += 1
            if is_first:
                first_count[key] += 1
            if reason:
                reasons[key].append(reason)
            active_count[key][active] += 1
            trend[key][hour_bucket] += 1
            if is_first:
                trend_first[key][hour_bucket] += 1
            members_of.setdefault(key, list(key))

    # 组合票数==1 不计入
    all_keys = [k for k in vote_count if vote_count[k] >= 2]
    total_votes = sum(vote_count[k] for k in all_keys)

    def system_id_a(k: tuple) -> int:
        return whitelist.system_id_of(members_of[k][0])

    sorted_keys = sorted(
        all_keys,
        key=lambda k: (-vote_count[k], -first_count[k], system_id_a(k)),
    )

    ranking = []
    prev_vc = None
    prev_display_rank = 0
    for i, key in enumerate(sorted_keys):
        vc = vote_count[key]
        fc = first_count[key]
        if vc != prev_vc:
            prev_display_rank = i + 1
            prev_vc = vc
        members = members_of[key]
        a = members[0]
        b = members[1] if len(members) > 1 else ""
        c = members[2] if len(members) > 2 else None
        ac = active_count[key]

        def _rate(mid: str) -> float:
            return round(ac.get(mid, 0) / vc, 4) if vc else 0.0

        ranking.append({
            "rank": [{
                "rank": i + 1,
                "vote_count": vc,
                "favorite_vote_count": fc,
                "favorite_percentage": int(fc / vc * 100) if vc else 0,
                "vote_percentage": round(vc / total_voters * 100, 2) if total_voters else 0.0,
            }],
            "display_rank": prev_display_rank,
            "name": "×".join(whitelist.name_of(m) for m in members),
            "id_a": a,
            "id_b": b,
            "id_c": c,
            "favorite_vote_count_weighted": vc + fc,
            "favorite_percentage": round(fc / vc * 100, 2) if vc else 0.0,
            "favorite_percentage_of_all": (
                round(fc / sum(first_count[k] for k in all_keys) * 100, 2)
                if sum(first_count[k] for k in all_keys) else 0.0
            ),
            "active_a": _rate(a),
            "active_b": _rate(b) if b else 0.0,
            "active_c": _rate(c) if c else 0.0,
            "active_none": _rate("none"),
            "reasons": reasons[key],
            "reasons_count": len(reasons[key]),
            "trend": [{"hrs": h, "cnt": cc} for h, cc in enumerate(trend[key]) if cc > 0],
            "trend_first": [{"hrs": h, "cnt": cc} for h, cc in enumerate(trend_first[key]) if cc > 0],
        })

    global_stats = {
        "total_unique_items": len(all_keys),
        "total_first": sum(first_count[k] for k in all_keys),
        "total_votes": total_votes,
        "average_votes_per_item": total_votes / len(all_keys) if all_keys else 0.0,
        "median_votes_per_item": _median([vote_count[k] for k in all_keys]),
    }
    return ranking, global_stats
```

> 自 CP (A,A) 边界：`members=["A","A"]`，`active_a` 与 `active_b` 会相等（同一 id 的主动占比），属可接受的极小瑕疵（自 CP 的 A/B 本就是同一角色），记入 changelog 备注。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/test_compute_cp_ranking_id.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/apps/result/compute.py tests/unit/test_compute_cp_ranking_id.py
git commit -m "feat(b050): compute_cp_ranking 改无序 multiset+白名单+主动率按位置+票数1不计"
```

---

## Task 5: `compute_service` 接线到 v1 管线

**Files:**
- Modify: `src/apps/result/compute_service.py`
- Test: `tests/integration/test_compute_pipeline_v1.py`

**Interfaces:**
- Consumes: `load_whitelist`（Task 1）、改签名后的 `compute_ranking`/`compute_cp_ranking`（Task 3/4）、改表后的 `load_*_votes`（Task 2）。
- Produces: `compute_all(vote_year)` 端到端跑通，Redis 键**不变**（`result:{y}:chars:ranking` 等）。

**关键改动：**
- 加载 `char_wl = load_whitelist("character")`、`music_wl = load_whitelist("music")`。
- `compute_ranking(char_votes, char_wl, gender_map, {}, vote_start, total_hours)`（historical 传 `{}`，v1 不做上届）。
- `compute_cp_ranking(cp_votes, char_wl, gender_map, {}, vote_start, total_hours)`（CP 成员是角色 → 用 `char_wl`）。
- 删除 `char_candidates/music_candidates/char_remap/music_remap/*_hist` 的加载与传参（v1 不用）。
- `gender_map` 仍调用 `compute_gender_map`，但 `q_votes` 来自死表（空）→ gender_map 实际为空，male/female=0（v1 后补）。
- 其余（global_stats/completion/covote/paper）保持，天然对空/退化输入工作。

- [ ] **Step 1: 写失败集成测 `tests/integration/test_compute_pipeline_v1.py`**

用 fakeredis + sqlite DB fixture（参照现有 compute 集成测）。seed 两个角色投票 + 一个作废行，跑 `compute_all`，断言 Redis `chars:ranking` 含 id 字段、顺序、丢作废。

```python
import json
import pytest
from datetime import datetime, timezone

from src.apps.result.compute_service import ComputeService
from src.apps.result.compute_dao import ComputeDAO
from src.db_model.raw_submit import RawCharacterSubmit


@pytest.mark.asyncio
async def test_compute_all_char_ranking_id_based(db_session, fake_redis, settings):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # 用真实白名单里的两个 id（从快照取，测试里硬编码两个已知 id）
    from src.apps.result.whitelist import load_whitelist
    ids = sorted(load_whitelist("character").ids)
    id1, id2 = ids[0], ids[1]
    db_session.add_all([
        RawCharacterSubmit(vote_id="u1", attempt=1, created_at=base, user_ip="x",
                           payload=[{"id": id1, "first": True}, {"id": id2}]),
        RawCharacterSubmit(vote_id="u2", attempt=1, created_at=base, user_ip="x",
                           payload=[{"id": id1}]),
        RawCharacterSubmit(vote_id="u3", attempt=1, created_at=base, user_ip="x",
                           invalidated=True, payload=[{"id": id2}]),
    ])
    await db_session.commit()

    svc = ComputeService(ComputeDAO(db_session), fake_redis, settings)
    result = await svc.compute_all(vote_year=settings.vote_year)
    assert result["ok"] and result["counts"]["chars"] == 2

    raw = await fake_redis.get(f"result:{settings.vote_year}:chars:ranking")
    ranking = json.loads(raw)
    top = ranking[0]
    assert top["id"] == id1  # id1 2票 > id2 1票（且 u3 作废不计）
    assert top["rank"][0]["vote_count"] == 2
    assert top["favorite_vote_count_weighted"] == 2 + 1
```

> 若现有测试没有 `fake_redis`/`settings` fixture，参照 `tests/` 里既有 compute 集成测的 fixture 命名接入（实现者按仓库现状对齐 fixture 名）。

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/integration/test_compute_pipeline_v1.py -v`
Expected: FAIL。

- [ ] **Step 3: 改 `compute_service.compute_all`**

改 import：
```python
from src.apps.result.compute import (
    compute_completion_rates,
    compute_covote,
    compute_cp_ranking,
    compute_gender_map,
    compute_global_stats,
    compute_paper_results,
    compute_ranking,
)
from src.apps.result.whitelist import load_whitelist
```

改数据加载与计算段（替换原 75-112 行区间）：
```python
            # Load votes (raw_*)
            char_votes = await self.dao.load_char_votes()
            music_votes = await self.dao.load_music_votes()
            cp_votes = await self.dao.load_cp_votes()
            q_votes = await self.dao.load_questionnaire_votes()

            # 白名单（id→名/系统ID）；CP 成员是角色 → 用角色白名单
            char_wl = load_whitelist("character")
            music_wl = load_whitelist("music")

            gender_map = compute_gender_map(
                q_votes, s.gender_question_id, s.gender_male_value, s.gender_female_value,
            )
            char_ranking, char_global = compute_ranking(
                char_votes, char_wl, gender_map, {}, vote_start, total_hours,
            )
            music_ranking, music_global = compute_ranking(
                music_votes, music_wl, gender_map, {}, vote_start, total_hours,
            )
            cp_ranking, cp_global = compute_cp_ranking(
                cp_votes, char_wl, gender_map, {}, vote_start, total_hours,
            )
```
（删除 `load_char_candidates/load_music_candidates/load_merge_name_map/load_historical` 四组调用。其余 all_voters/global_stats/completion/covote/paper 段与 Redis 写入保持不变。）

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/integration/test_compute_pipeline_v1.py -v`
Expected: PASS。

- [ ] **Step 5: 修既有 compute 测试的口径漂移 + 全量跑**

Run: `pytest tests/ -k "compute or result" -v`
处理 Task 2 Step 5 记下的、因口径变化而失败的旧断言（把断言改成新 id-based 口径；若旧测试断言的是死表行为则删除并说明）。
Run: `pytest tests/ -q`
Expected: 全绿。

- [ ] **Step 6: 提交**

```bash
git add src/apps/result/compute_service.py tests/integration/test_compute_pipeline_v1.py
git commit -m "feat(b050): compute_service 接线 id 白名单管线(gender/上届 v1 喂空)"
```

---

## Task 6: 发榜 schema 补 `id` + 文档/CHANGELOG/BACKLOG

**Files:**
- Modify: `src/apps/result/schemas.py`（`RankingEntity` 加可选 `id`、`favorite_percentage_of_all`）
- Modify: `docs/superpowers/specs/2026-07-18-result-recount-id-based-design.md`（补"实现落地"小节）
- Modify: `docs/CHANGELOG.md`, `docs/BACKLOG.md`
- Modify: `docs/migration/python-rewrite.md`（若存在：登记旧 compute→新 compute 映射）

- [ ] **Step 1: schema 加字段**

`src/apps/result/schemas.py` 的 `RankingEntity` 加（放在 `name` 上方/下方均可，保持向后兼容用 `Optional` 默认）：
```python
    id: Optional[str] = None
    favorite_percentage_of_all: float = 0.0
```
（`RankingEntity` 顶部已 `from typing import ... Optional`。GraphQL/REST 返回的是无类型 JSON，不受影响；此改动仅让 Pydantic 契约也带上 id。）

- [ ] **Step 2: 跑受影响测试**

Run: `pytest tests/ -k "result or schema" -q`
Expected: PASS（新增字段有默认值，向后兼容）。

- [ ] **Step 3: 更新设计稿"实现落地"小节**

在 `docs/superpowers/specs/2026-07-18-result-recount-id-based-design.md` 末尾加"§九 v1 实现落地（2026-07-18）"：记录最终文件清单、白名单快照来源与**重新提取步骤**（前端列表变更时 `node scripts/extract_whitelist.mjs ...` 重跑并提交 JSON）、系统ID=列表位置序号、CP multiset、名次口径、以及 v1 明确后补项。

- [ ] **Step 4: 更新 CHANGELOG / BACKLOG**

`docs/CHANGELOG.md` 加一条 `[日期] Added/Changed: B-050 v1 记票重写（读 raw_*、id 白名单、CP 无序、名次口径对齐）`，注明兼容性（发榜新增 id 字段、名次口径变化）。
`docs/BACKLOG.md`：把 B-050 标记为"v1 完成"，并列出后补子项（性别票、trend 需改存储、上届对比、问卷结果、高级搜索、候选表迁 object_id）。

- [ ] **Step 5: 提交**

```bash
git add src/apps/result/schemas.py docs/
git commit -m "feat(b050): 发榜 schema 补 id/本命占比 + 文档/CHANGELOG/BACKLOG"
```

---

## Self-Review Checklist（写完计划自查）

- **Spec coverage**：票数/本命数/本命率/本命加权/票数占比/本命占比（Task 3/4）✓；名次票数→本命→系统ID+虚位（Task 3/4）✓；白名单丢未知（Task 3/4）✓；CP 无序 multiset+自CP+主动率+票数1不计（Task 4）✓；读 raw_*+取最新+排除作废（Task 2）✓；离线批量按钮（已存在，无需新建）✓；系统ID=列表序号（Task 1）✓。
- **后补项明确**：性别/trend/上届/问卷/搜索在 Global Constraints 标注为 v1 不做、喂空，不在验证范围。
- **可移植性**：dedup 用 Python 侧（禁 DISTINCT ON），测试跑 sqlite。
- **契约兼容**：name 保留、id 新增、Redis 键不变。
- **类型一致**：`Whitelist` 在 compute.py 用 `TYPE_CHECKING` 前向引用；`load_whitelist("character"|"music")` 字面量一致。

## Execution Handoff

计划已存 `docs/superpowers/plans/2026-07-18-b050-result-recount-v1.md`。两种执行方式：
1. **Subagent-Driven（推荐）** — 每个任务派新实现子代理 + 任务级评审 + 收尾整体评审。
2. **Inline Execution** — 本会话内批量执行 + 检查点。
