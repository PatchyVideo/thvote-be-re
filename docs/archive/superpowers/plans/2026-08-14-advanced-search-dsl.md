# 高级搜索/筛选 DSL 实施计划(B-050-后补5)

> **归档状态**：已实施 —— B-050-后补5，2026-08-14（`src/apps/result/advanced_search/`）
> 本文件是**历史过程记录，不代表当前实现**。现状请查 [BACKLOG.md](../../../BACKLOG.md) 与 [CHANGELOG.md](../../../CHANGELOG.md)。
> 归档于 2026-08-31。
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现结果查询高级搜索——服务端解析 DSL `query` 参数,按 `vote_id` 子集重算全套结果并缓存,点亮契约层 10 个带 `query` 参数的 GraphQL 查询。

**Architecture:** 新子包 `src/apps/result/advanced_search/`(dsl 解析 / subset 子集圈选 / service 缓存与整包重算),子集圈选后**原样复用** `compute.py` 纯函数;缓存 key 镜像现有 `result:{year}:...` 布局、多一段 `adv:{快照版本}:{指纹}` infix;契约层把 `_reject_query_dsl` 替换为 `_apply_advanced_search`。设计稿:`docs/superpowers/specs/2026-08-14-advanced-search-dsl-design.md`。

**Tech Stack:** Python 3.12 / lark(新依赖,纯 Python)/ SQLAlchemy async / redis.asyncio / strawberry GraphQL / pytest + fakeredis + aiosqlite。

## Global Constraints

- 新代码全部带类型标注(CLAUDE.md §6);flake8 通过。
- 错误一律 `ValidationError(kind, human_readable_message=...)`(`src.common.exceptions`),kind 取 `ADVANCED_SEARCH_SYNTAX_ERROR` / `ADVANCED_SEARCH_TOO_COMPLEX` / `ADVANCED_SEARCH_UNKNOWN_NAME` 三种(设计稿 §八)。
- 限制常量:`MAX_QUERY_LENGTH = 1024`、`MAX_ATOMS = 20`、`MAX_DEPTH = 5`;缓存 `ADV_TTL_SECONDS = 24 * 3600`。
- **无 DB schema 变更**——不需要 alembic migration。
- 日志不得输出投票人 vote_id 明细(可输出子集规模、指纹)。
- 每个 Task 单独 commit,message 前缀按仓库约定(`feat:`/`test:`/`docs:`)。
- 测试从 `thvote-be-re/` 根目录跑:`python -m pytest <file> -v`;整套回归:`python -m pytest tests/ -q`。

---

### Task 1: 依赖 + AST 数据类 + lark 解析器(`dsl.py` 之一)

**Files:**
- Modify: `pyproject.toml`(dependencies 列表,`"aiohttp>=3.9",` 之后加一行)
- Create: `src/apps/result/advanced_search/__init__.py`(空文件)
- Create: `src/apps/result/advanced_search/dsl.py`
- Test: `tests/unit/test_advanced_search_dsl.py`

**Interfaces:**
- Produces(后续 Task 依赖的精确签名):
  - AST 节点(全部 `@dataclass(frozen=True)`,可哈希):`QCond(qcode: str, ocode: str)`、`CharAny(names: tuple[str, ...])`、`CharFirst(name: str)`、`MusicAny(names: tuple[str, ...])`、`MusicFirst(name: str)`、`And(children: tuple[Node, ...])`、`Or(children: tuple[Node, ...])`;`Node` 为七者 Union 类型别名。
  - `parse_query(query: str) -> Node`:解析 + 长度限制;语法错抛 `ValidationError("ADVANCED_SEARCH_SYNTAX_ERROR")`(消息带行列号)。(Task 2 会给它追加归一化与 AST 限制。)

- [ ] **Step 1: 加依赖**

在 `pyproject.toml` 的 `dependencies` 列表 `"aiohttp>=3.9",` 之后加:

```toml
    "lark>=1.1.0",
```

然后安装(在项目现用的虚拟环境里):`pip install "lark>=1.1.0"`,验证:`python -c "import lark; print(lark.__version__)"`。

- [ ] **Step 2: 写失败测试**

`tests/unit/test_advanced_search_dsl.py`:

```python
"""高级搜索 DSL 解析单测(设计稿 §四/§五)。"""

from __future__ import annotations

import pytest

from src.apps.result.advanced_search.dsl import (
    And,
    CharAny,
    CharFirst,
    MusicAny,
    MusicFirst,
    Or,
    QCond,
    parse_query,
)
from src.common.exceptions import ValidationError


class TestAtoms:
    def test_q_cond(self):
        assert parse_query("q11011 = 1101101") == QCond(qcode="11011", ocode="1101101")

    def test_chars_any(self):
        node = parse_query('chars: ["东风谷早苗", "博丽灵梦"]')
        assert isinstance(node, CharAny)
        assert set(node.names) == {"东风谷早苗", "博丽灵梦"}

    def test_chars_first(self):
        assert parse_query('chars_first="东风谷早苗"') == CharFirst(name="东风谷早苗")

    def test_musics_any(self):
        node = parse_query('musics: ["信仰是为了虚幻之人", "Native Faith"]')
        assert isinstance(node, MusicAny)
        assert set(node.names) == {"信仰是为了虚幻之人", "Native Faith"}

    def test_musics_first(self):
        assert parse_query('musics_first="信仰是为了虚幻之人"') == MusicFirst(
            name="信仰是为了虚幻之人"
        )


class TestCombinators:
    def test_and_of_three(self):
        node = parse_query(
            'q11011 = 1101101 AND chars: ["东风谷早苗"] AND chars: ["博丽灵梦"]'
        )
        assert isinstance(node, And)
        assert len(node.children) == 3

    def test_or(self):
        node = parse_query('q11011 = 1101101 OR chars: ["东风谷早苗"]')
        assert isinstance(node, Or)
        assert len(node.children) == 2

    def test_and_binds_tighter_than_or(self):
        node = parse_query('q1 = 2 OR q3 = 4 AND q5 = 6')
        assert isinstance(node, Or)
        assert node.children[0] == QCond(qcode="1", ocode="2")
        assert isinstance(node.children[1], And)

    def test_parens_requirement_example(self):
        node = parse_query(
            '(q11011 = 1101101 AND chars: ["东风谷早苗"])'
            ' OR musics_first="信仰是为了虚幻之人"'
        )
        assert isinstance(node, Or)
        kinds = {type(c) for c in node.children}
        assert And in kinds and MusicFirst in kinds


class TestErrors:
    @pytest.mark.parametrize("bad", [
        "chars:[",                       # 括号不闭合
        'chars ["a"]',                   # 缺冒号
        "q11011 == 1101101",             # 双等号
        'chars: ["a"] and chars: ["b"]', # 小写 and 不是关键字
        "",                              # 空串不该走到解析(调用方保证),真走到也报语法错
    ])
    def test_syntax_error(self, bad: str):
        with pytest.raises(ValidationError) as exc_info:
            parse_query(bad)
        assert exc_info.value.message == "ADVANCED_SEARCH_SYNTAX_ERROR"

    def test_query_too_long(self):
        with pytest.raises(ValidationError) as exc_info:
            parse_query("q1 = 1 " + "OR q1 = 1 " * 200)  # > 1024 字符
        assert exc_info.value.message == "ADVANCED_SEARCH_TOO_COMPLEX"
```

注意:`ValidationError` 的 kind 存放字段以 `src/common/exceptions.py` 实际实现为准(现有代码用 `exc.message` 承载 kind,见 `result_compat.py` 的用法);若属性名不同,以读到的真实字段调整断言,**不要**改异常类本身。

- [ ] **Step 3: 跑测试确认失败**

`python -m pytest tests/unit/test_advanced_search_dsl.py -v`
预期:`ModuleNotFoundError: No module named 'src.apps.result.advanced_search'`。

- [ ] **Step 4: 实现**

`src/apps/result/advanced_search/__init__.py` 为空文件。`src/apps/result/advanced_search/dsl.py`:

```python
"""高级搜索 DSL:文法、AST、解析(设计稿 §四/§五)。

语法(需求文档 §846-923):6 种原子条件 + AND/OR/括号,AND 结合紧于 OR。
解析产物是与 lark 解耦的 frozen dataclass AST,B-053 直接消费。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Union

from lark import Lark, Token, Transformer
from lark import exceptions as lark_exceptions

from src.common.exceptions import ValidationError

MAX_QUERY_LENGTH = 1024
MAX_ATOMS = 20
MAX_DEPTH = 5


@dataclass(frozen=True)
class QCond:
    qcode: str
    ocode: str


@dataclass(frozen=True)
class CharAny:
    names: tuple[str, ...]


@dataclass(frozen=True)
class CharFirst:
    name: str


@dataclass(frozen=True)
class MusicAny:
    names: tuple[str, ...]


@dataclass(frozen=True)
class MusicFirst:
    name: str


@dataclass(frozen=True)
class And:
    children: tuple["Node", ...]


@dataclass(frozen=True)
class Or:
    children: tuple["Node", ...]


Node = Union[QCond, CharAny, CharFirst, MusicAny, MusicFirst, And, Or]

_GRAMMAR = r"""
?expr: or_expr
?or_expr: and_expr ("OR" and_expr)*
?and_expr: atom ("AND" atom)*
?atom: "(" expr ")"
     | q_cond
     | chars_any
     | chars_first
     | musics_any
     | musics_first

q_cond: QNAME "=" INT
chars_any: "chars" ":" "[" string ("," string)* "]"
chars_first: "chars_first" "=" string
musics_any: "musics" ":" "[" string ("," string)* "]"
musics_first: "musics_first" "=" string

string: ESCAPED_STRING
QNAME: /q\d+/

%import common.ESCAPED_STRING
%import common.INT
%import common.WS
%ignore WS
"""

_PARSER = Lark(_GRAMMAR, start="expr")


class _ToAst(Transformer):
    """lark 树 → frozen dataclass AST。

    `?or_expr`/`?and_expr` 单子节点时被 lark 内联,只有真正出现
    OR/AND 时才会调用对应方法——不会产生单儿子的 And/Or 包装。
    """

    def string(self, items: list[Token]) -> str:
        return json.loads(str(items[0]))  # ESCAPED_STRING 与 JSON 字符串同格式

    def q_cond(self, items: list[Token]) -> QCond:
        return QCond(qcode=str(items[0])[1:], ocode=str(items[1]))

    def chars_any(self, items: list[str]) -> CharAny:
        return CharAny(names=tuple(items))

    def chars_first(self, items: list[str]) -> CharFirst:
        return CharFirst(name=items[0])

    def musics_any(self, items: list[str]) -> MusicAny:
        return MusicAny(names=tuple(items))

    def musics_first(self, items: list[str]) -> MusicFirst:
        return MusicFirst(name=items[0])

    def or_expr(self, items: list[Node]) -> Or:
        return Or(children=tuple(items))

    def and_expr(self, items: list[Node]) -> And:
        return And(children=tuple(items))


def parse_query(query: str) -> Node:
    """query 字符串 → AST。语法错/超长 → 可辨识 ValidationError。"""
    if len(query) > MAX_QUERY_LENGTH:
        raise ValidationError(
            "ADVANCED_SEARCH_TOO_COMPLEX",
            human_readable_message=f"高级搜索指令过长(超过 {MAX_QUERY_LENGTH} 字符)",
        )
    try:
        tree = _PARSER.parse(query)
        return _ToAst().transform(tree)
    except lark_exceptions.UnexpectedInput as exc:
        line = getattr(exc, "line", "?")
        column = getattr(exc, "column", "?")
        raise ValidationError(
            "ADVANCED_SEARCH_SYNTAX_ERROR",
            human_readable_message=f"高级搜索语法错误(第 {line} 行第 {column} 列附近)",
        ) from exc
    except lark_exceptions.VisitError as exc:
        raise ValidationError(
            "ADVANCED_SEARCH_SYNTAX_ERROR",
            human_readable_message="高级搜索语法错误",
        ) from exc
```

- [ ] **Step 5: 跑测试确认通过**

`python -m pytest tests/unit/test_advanced_search_dsl.py -v` → 全 PASS。若 lark 对空串抛的不是 `UnexpectedInput` 子类导致空串用例失败,在 `parse_query` 开头对 `not query.strip()` 显式抛同款 `ADVANCED_SEARCH_SYNTAX_ERROR`。

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/apps/result/advanced_search/ tests/unit/test_advanced_search_dsl.py
git commit -m "feat(result): 高级搜索 DSL 解析器(lark 文法+AST,B-050-后补5 Task 1)"
```

---

### Task 2: 归一化 / 指纹 / AST 限制(`dsl.py` 之二)

**Files:**
- Modify: `src/apps/result/advanced_search/dsl.py`
- Test: `tests/unit/test_advanced_search_dsl.py`(追加)

**Interfaces:**
- Consumes: Task 1 的 AST 节点与 `parse_query`。
- Produces:
  - `normalize(node: Node) -> Node`:组内排序去重、And/Or 拍平+规范排序+单儿子解包。
  - `canonical(node: Node) -> str`:确定性规范串。
  - `fingerprint(node: Node) -> str`:`sha1(canonical)[:16]`。
  - `parse_query` 行为升级:返回**归一化后**的 AST,并做原子数/深度限制(超限抛 `ADVANCED_SEARCH_TOO_COMPLEX`)。

- [ ] **Step 1: 追加失败测试**

在 `tests/unit/test_advanced_search_dsl.py` 末尾追加:

```python
from src.apps.result.advanced_search.dsl import canonical, fingerprint, normalize  # noqa: E402


class TestNormalization:
    def test_commutative_and_same_fingerprint(self):
        a = parse_query('chars: ["a"] AND q1 = 2')
        b = parse_query('q1 = 2 AND chars: ["a"]')
        assert a == b
        assert fingerprint(a) == fingerprint(b)

    def test_list_order_and_dup_same_fingerprint(self):
        a = parse_query('chars: ["a", "b"]')
        b = parse_query('chars: ["b", "a", "a"]')
        assert fingerprint(a) == fingerprint(b)

    def test_nested_same_op_flattened(self):
        node = parse_query('(q1 = 1 AND q2 = 2) AND q3 = 3')
        assert isinstance(node, And)
        assert len(node.children) == 3  # 拍平,不是 And(And(..), ..)

    def test_duplicate_atoms_deduped_to_single(self):
        node = parse_query('q1 = 1 AND q1 = 1')
        assert node == QCond(qcode="1", ocode="1")  # 去重后单儿子解包

    def test_canonical_is_deterministic(self):
        node = parse_query('musics: ["x"] OR chars_first="y"')
        assert canonical(node) == canonical(parse_query('chars_first="y" OR musics: ["x"]'))


class TestLimits:
    def test_too_many_atoms(self):
        query = " OR ".join(f"q{i} = 1" for i in range(21))  # 21 原子 > 20
        with pytest.raises(ValidationError) as exc_info:
            parse_query(query)
        assert exc_info.value.message == "ADVANCED_SEARCH_TOO_COMPLEX"

    def test_too_deep(self):
        query = 'q1 = 1 AND (q2 = 2 OR (q3 = 3 AND (q4 = 4 OR (q5 = 5 AND (q6 = 6 OR q7 = 7)))))'
        with pytest.raises(ValidationError) as exc_info:
            parse_query(query)
        assert exc_info.value.message == "ADVANCED_SEARCH_TOO_COMPLEX"

    def test_depth_five_ok(self):
        node = parse_query('q1 = 1 AND (q2 = 2 OR (q3 = 3 AND (q4 = 4 OR q5 = 5)))')
        assert node is not None
```

注意 `test_too_deep` 的深度按"归一化前"的 AST 计算(见 Step 3 实现顺序:先限制后归一化——限制是护栏,要拦原始输入的复杂度,不能被归一化"洗浅")。

- [ ] **Step 2: 跑测试确认失败**

`python -m pytest tests/unit/test_advanced_search_dsl.py -v`
预期:`ImportError: cannot import name 'canonical'`。

- [ ] **Step 3: 实现**

在 `dsl.py` 追加(并把 `parse_query` 末尾的 `return _ToAst().transform(tree)` 改为先赋值 `ast`,依次 `_check_limits(ast)`、`return normalize(ast)`;两个 except 子句不动):

```python
import hashlib  # 放到文件顶部 import 区


def canonical(node: Node) -> str:
    """确定性规范串——归一化等价的 AST 得到同一个串。"""
    if isinstance(node, QCond):
        return f"q{node.qcode}={node.ocode}"
    if isinstance(node, CharAny):
        inner = ",".join(json.dumps(n, ensure_ascii=False) for n in node.names)
        return f"chars:[{inner}]"
    if isinstance(node, CharFirst):
        return f"chars_first={json.dumps(node.name, ensure_ascii=False)}"
    if isinstance(node, MusicAny):
        inner = ",".join(json.dumps(n, ensure_ascii=False) for n in node.names)
        return f"musics:[{inner}]"
    if isinstance(node, MusicFirst):
        return f"musics_first={json.dumps(node.name, ensure_ascii=False)}"
    op = " AND " if isinstance(node, And) else " OR "
    return "(" + op.join(canonical(c) for c in node.children) + ")"


def fingerprint(node: Node) -> str:
    """归一化 AST 的缓存指纹(16 位 hex 足够,碰撞域是单届的约束空间)。"""
    return hashlib.sha1(canonical(node).encode("utf-8")).hexdigest()[:16]


def normalize(node: Node) -> Node:
    """组内排序去重;And/Or 按结合律拍平、操作数规范排序、单儿子解包。"""
    if isinstance(node, (And, Or)):
        cls = type(node)
        flat: list[Node] = []
        for child in node.children:
            nc = normalize(child)
            if isinstance(nc, cls):
                flat.extend(nc.children)
            else:
                flat.append(nc)
        uniq = sorted(set(flat), key=canonical)
        if len(uniq) == 1:
            return uniq[0]
        return cls(children=tuple(uniq))
    if isinstance(node, CharAny):
        return CharAny(names=tuple(sorted(set(node.names))))
    if isinstance(node, MusicAny):
        return MusicAny(names=tuple(sorted(set(node.names))))
    return node


def _stats(node: Node) -> tuple[int, int]:
    """(原子条件数, 嵌套深度)。原子深度记 1,And/Or 记 1+max(子深度)。"""
    if isinstance(node, (And, Or)):
        pairs = [_stats(c) for c in node.children]
        return sum(p[0] for p in pairs), 1 + max(p[1] for p in pairs)
    return 1, 1


def _check_limits(node: Node) -> None:
    atoms, depth = _stats(node)
    if atoms > MAX_ATOMS:
        raise ValidationError(
            "ADVANCED_SEARCH_TOO_COMPLEX",
            human_readable_message=f"约束条件过多({atoms} 个,上限 {MAX_ATOMS})",
        )
    if depth > MAX_DEPTH:
        raise ValidationError(
            "ADVANCED_SEARCH_TOO_COMPLEX",
            human_readable_message=f"嵌套过深({depth} 层,上限 {MAX_DEPTH})",
        )
```

- [ ] **Step 4: 跑测试确认通过**

`python -m pytest tests/unit/test_advanced_search_dsl.py -v` → 全 PASS(含 Task 1 用例回归)。

- [ ] **Step 5: Commit**

```bash
git add src/apps/result/advanced_search/dsl.py tests/unit/test_advanced_search_dsl.py
git commit -m "feat(result): DSL 归一化/指纹/复杂度限制(B-050-后补5 Task 2)"
```

---

### Task 3: 子集圈选(`subset.py`)

**Files:**
- Create: `src/apps/result/advanced_search/subset.py`
- Test: `tests/unit/test_advanced_search_subset.py`

**Interfaces:**
- Consumes: Task 1/2 的 AST 节点;`src.apps.result.whitelist.Whitelist`/`WhitelistEntry`(现有,`entries` 属性、`canonical(token) -> str | None`)。
- Produces:
  - `VoteFacts` dataclass:`char_ids: dict[str, set[str]]`、`char_first: dict[str, set[str]]`、`music_ids: dict[str, set[str]]`、`music_first: dict[str, set[str]]`、`q_answers: dict[str, dict[str, set[str]]]`、`all_vote_ids: set[str]`(key 均为 vote_id;id 均为 canonical `str(candidate_id)`)。
  - `build_facts(char_votes, music_votes, cp_votes, q_votes, char_wl, music_wl) -> VoteFacts`(votes 形参类型与 `ComputeDAO.load_*_votes` 返回一致:char/music/cp 为 `list[tuple[str, datetime, list[dict]]]`,q 为 `list[tuple[str, list[dict]]]`)。
  - `resolve_names(node: Node, char_wl: Whitelist, music_wl: Whitelist) -> dict[tuple[str, str], set[str]]`:`("character"|"music", 名字) → canonical id 集合`;未知名字聚合后抛 `ValidationError("ADVANCED_SEARCH_UNKNOWN_NAME")`。
  - `evaluate_subset(node: Node, facts: VoteFacts, resolved: dict[tuple[str, str], set[str]]) -> set[str]`。

- [ ] **Step 1: 写失败测试**

`tests/unit/test_advanced_search_subset.py`:

```python
"""子集圈选单测:事实索引 / 名字解析 / AST 求值(设计稿 §五/§六)。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.apps.result.advanced_search.dsl import parse_query
from src.apps.result.advanced_search.subset import (
    build_facts,
    evaluate_subset,
    resolve_names,
)
from src.apps.result.whitelist import Whitelist, WhitelistEntry
from src.common.exceptions import ValidationError

_DT = datetime(2026, 1, 2, tzinfo=timezone.utc)


def _entry(cid: int, name: str, name_jp: str = "") -> WhitelistEntry:
    return WhitelistEntry(
        candidate_id=cid, voteable_id=cid, old_id=None, name=name,
        name_jp=name_jp, origin="", type="", first_appearance=None,
        album=None, system_id=cid,
    )


@pytest.fixture
def char_wl() -> Whitelist:
    return Whitelist([_entry(1, "东风谷早苗", "東風谷早苗"), _entry(2, "博丽灵梦")])


@pytest.fixture
def music_wl() -> Whitelist:
    return Whitelist([_entry(10, "信仰是为了虚幻之人", "Native Faith")])


def _votes(*rows):
    """rows: (vote_id, [(id, first)])。"""
    return [
        (vid, _DT, [{"id": str(i), "first": f, "reason": None} for i, f in items])
        for vid, items in rows
    ]


@pytest.fixture
def facts(char_wl, music_wl):
    char_votes = _votes(
        ("u1", [(1, True), (2, False)]),   # 投早苗(本命)+灵梦
        ("u2", [(2, True)]),               # 只投灵梦(本命)
    )
    music_votes = _votes(("u1", [(10, False)]))
    q_votes = [
        ("u1", [{"id": "11011", "answer": ["1101101"], "answer_str": None}]),
        ("u3", [{"id": "11011", "answer": ["1101102"], "answer_str": None}]),
    ]
    return build_facts(char_votes, music_votes, [], q_votes, char_wl, music_wl)


class TestResolveNames:
    def test_resolves_name_and_name_jp(self, char_wl, music_wl):
        node = parse_query('chars: ["東風谷早苗"] AND musics: ["Native Faith"]')
        resolved = resolve_names(node, char_wl, music_wl)
        assert resolved[("character", "東風谷早苗")] == {"1"}
        assert resolved[("music", "Native Faith")] == {"10"}

    def test_unknown_name_raises_with_names_listed(self, char_wl, music_wl):
        node = parse_query('chars: ["雾雨魔理沙"] AND musics: ["不存在的曲子"]')
        with pytest.raises(ValidationError) as exc_info:
            resolve_names(node, char_wl, music_wl)
        assert exc_info.value.message == "ADVANCED_SEARCH_UNKNOWN_NAME"
        assert "雾雨魔理沙" in (exc_info.value.human_readable_message or "")


def _eval(query: str, facts, char_wl, music_wl) -> set[str]:
    node = parse_query(query)
    resolved = resolve_names(node, char_wl, music_wl)
    return evaluate_subset(node, facts, resolved)


class TestEvaluate:
    def test_chars_any_is_or_within_group(self, facts, char_wl, music_wl):
        assert _eval('chars: ["东风谷早苗", "博丽灵梦"]', facts, char_wl, music_wl) == {"u1", "u2"}

    def test_two_chars_atoms_anded_means_voted_both(self, facts, char_wl, music_wl):
        assert _eval('chars: ["东风谷早苗"] AND chars: ["博丽灵梦"]', facts, char_wl, music_wl) == {"u1"}

    def test_chars_first(self, facts, char_wl, music_wl):
        assert _eval('chars_first="博丽灵梦"', facts, char_wl, music_wl) == {"u2"}

    def test_cross_section_and_missing_section_is_false(self, facts, char_wl, music_wl):
        # u2 没投音乐 → musics 原子判 False
        assert _eval('chars: ["博丽灵梦"] AND musics: ["Native Faith"]', facts, char_wl, music_wl) == set()
        assert _eval('chars: ["东风谷早苗"] AND musics: ["Native Faith"]', facts, char_wl, music_wl) == {"u1"}

    def test_q_cond_and_or(self, facts, char_wl, music_wl):
        assert _eval("q11011 = 1101101", facts, char_wl, music_wl) == {"u1"}
        # u3 只答了问卷没投票,也在全集里
        assert _eval('q11011 = 1101102 OR chars_first="博丽灵梦"', facts, char_wl, music_wl) == {"u2", "u3"}

    def test_empty_subset(self, facts, char_wl, music_wl):
        assert _eval('chars_first="东风谷早苗" AND chars_first="博丽灵梦"', facts, char_wl, music_wl) == set()
```

- [ ] **Step 2: 跑测试确认失败**

`python -m pytest tests/unit/test_advanced_search_subset.py -v`
预期:`ModuleNotFoundError`(subset 不存在)。

- [ ] **Step 3: 实现**

`src/apps/result/advanced_search/subset.py`:

```python
"""子集圈选:事实索引 + 名字解析 + AST 求值(设计稿 §五/§六)。

数据源与 compute_all 完全同源(ComputeDAO.load_*_votes 已做"每 vote_id
取最新、排除 invalidated"),本模块只做纯内存集合运算。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.apps.result.advanced_search.dsl import (
    And,
    CharAny,
    CharFirst,
    MusicAny,
    MusicFirst,
    Node,
    Or,
    QCond,
)
from src.apps.result.whitelist import Whitelist
from src.common.exceptions import ValidationError

CharMusicVotes = list[tuple[str, datetime, list[dict]]]
QVotes = list[tuple[str, list[dict]]]


@dataclass
class VoteFacts:
    """per-vote 事实索引;id 均为 canonical str(candidate_id)。"""

    char_ids: dict[str, set[str]]
    char_first: dict[str, set[str]]
    music_ids: dict[str, set[str]]
    music_first: dict[str, set[str]]
    q_answers: dict[str, dict[str, set[str]]]
    all_vote_ids: set[str]


def _canon(wl: Whitelist, raw: object) -> str:
    token = str(raw)
    return wl.canonical(token) or token


def build_facts(
    char_votes: CharMusicVotes,
    music_votes: CharMusicVotes,
    cp_votes: CharMusicVotes,
    q_votes: QVotes,
    char_wl: Whitelist,
    music_wl: Whitelist,
) -> VoteFacts:
    char_ids: dict[str, set[str]] = {}
    char_first: dict[str, set[str]] = {}
    for vid, _dt, items in char_votes:
        char_ids[vid] = {_canon(char_wl, it.get("id", "")) for it in items}
        char_first[vid] = {
            _canon(char_wl, it.get("id", "")) for it in items if it.get("first")
        }
    music_ids: dict[str, set[str]] = {}
    music_first: dict[str, set[str]] = {}
    for vid, _dt, items in music_votes:
        music_ids[vid] = {_canon(music_wl, it.get("id", "")) for it in items}
        music_first[vid] = {
            _canon(music_wl, it.get("id", "")) for it in items if it.get("first")
        }
    q_answers: dict[str, dict[str, set[str]]] = {}
    for vid, entries in q_votes:
        per_question: dict[str, set[str]] = {}
        for entry in entries:
            per_question.setdefault(str(entry.get("id", "")), set()).update(
                str(a) for a in (entry.get("answer") or [])
            )
        q_answers[vid] = per_question
    all_vote_ids = (
        set(char_ids) | set(music_ids)
        | {vid for vid, _dt, _items in cp_votes} | set(q_answers)
    )
    return VoteFacts(
        char_ids=char_ids, char_first=char_first,
        music_ids=music_ids, music_first=music_first,
        q_answers=q_answers, all_vote_ids=all_vote_ids,
    )


def _name_index(wl: Whitelist) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for e in wl.entries:
        index.setdefault(e.name, set()).add(str(e.candidate_id))
        if e.name_jp:
            index.setdefault(e.name_jp, set()).add(str(e.candidate_id))
    return index


def resolve_names(
    node: Node, char_wl: Whitelist, music_wl: Whitelist
) -> dict[tuple[str, str], set[str]]:
    """AST 里所有名字 → canonical id 集合;未知名字聚合后一次性报错。

    name 与 name_jp 精确匹配任一即命中;同名撞多条时取并集(投任一即
    满足,与组内 OR 语义一致,设计稿 §十二风险2)。
    """
    char_idx = _name_index(char_wl)
    music_idx = _name_index(music_wl)
    resolved: dict[tuple[str, str], set[str]] = {}
    unknown: list[str] = []

    def visit(n: Node) -> None:
        if isinstance(n, (And, Or)):
            for child in n.children:
                visit(child)
            return
        if isinstance(n, (CharAny, CharFirst)):
            names = n.names if isinstance(n, CharAny) else (n.name,)
            for name in names:
                ids = char_idx.get(name)
                if ids:
                    resolved[("character", name)] = ids
                else:
                    unknown.append(name)
        elif isinstance(n, (MusicAny, MusicFirst)):
            names = n.names if isinstance(n, MusicAny) else (n.name,)
            for name in names:
                ids = music_idx.get(name)
                if ids:
                    resolved[("music", name)] = ids
                else:
                    unknown.append(name)

    visit(node)
    if unknown:
        uniq = list(dict.fromkeys(unknown))
        raise ValidationError(
            "ADVANCED_SEARCH_UNKNOWN_NAME",
            human_readable_message="未知的角色/曲目名: " + "、".join(uniq),
        )
    return resolved


def evaluate_subset(
    node: Node,
    facts: VoteFacts,
    resolved: dict[tuple[str, str], set[str]],
) -> set[str]:
    """对全集逐 vote_id 求 AST 真值,返回满足约束的 vote_id 集合。"""

    def ok(n: Node, vid: str) -> bool:
        if isinstance(n, And):
            return all(ok(c, vid) for c in n.children)
        if isinstance(n, Or):
            return any(ok(c, vid) for c in n.children)
        if isinstance(n, QCond):
            return n.ocode in facts.q_answers.get(vid, {}).get(n.qcode, set())
        if isinstance(n, CharAny):
            voted = facts.char_ids.get(vid, set())
            return any(resolved[("character", nm)] & voted for nm in n.names)
        if isinstance(n, CharFirst):
            return bool(
                resolved[("character", n.name)] & facts.char_first.get(vid, set())
            )
        if isinstance(n, MusicAny):
            voted = facts.music_ids.get(vid, set())
            return any(resolved[("music", nm)] & voted for nm in n.names)
        if isinstance(n, MusicFirst):
            return bool(
                resolved[("music", n.name)] & facts.music_first.get(vid, set())
            )
        raise TypeError(f"unknown AST node: {n!r}")

    return {vid for vid in facts.all_vote_ids if ok(node, vid)}
```

- [ ] **Step 4: 跑测试确认通过**

`python -m pytest tests/unit/test_advanced_search_subset.py -v` → 全 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/apps/result/advanced_search/subset.py tests/unit/test_advanced_search_subset.py
git commit -m "feat(result): 子集圈选——事实索引/名字解析/AST 求值(B-050-后补5 Task 3)"
```

---

### Task 4: 缓存整包重算服务(`service.py`)+ 快照版本

**Files:**
- Create: `src/apps/result/advanced_search/service.py`
- Modify: `src/apps/result/compute_service.py`(compute_all 的 Redis pipeline 加一行快照版本)
- Test: `tests/integration/test_advanced_search_service.py`

**Interfaces:**
- Consumes: Task 1-3 全部;`ComputeDAO`(`load_char_votes()`/`load_music_votes()`/`load_cp_votes()`/`load_questionnaire_votes(vote_year)`);`load_whitelist_db(session, category, vote_year)`;compute 纯函数(签名同 `compute_service.py` 现有调用);`src.common.database.get_session_maker`。
- Produces:
  - `ensure_filtered_results(redis: aioredis.Redis, settings: Settings, vote_year: int, query_str: str) -> str`——确保筛选结果在缓存,返回 ResultDAO 用的 key infix(`adv:{版本}:{指纹}`)。Task 5 的契约层只调用这一个函数。
  - `snapshot_version_key(vote_year: int) -> str` = `result:{year}:snapshot_version`。
  - `ComputeService.compute_all` 在 pipeline 里写入快照版本(unix 秒时间戳字符串)。

- [ ] **Step 1: 写失败测试**

`tests/integration/test_advanced_search_service.py`:

```python
"""高级搜索服务集成测:整包重算/缓存命中/版本/未知名/空子集(设计稿 §三/§六/§七)。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio

try:
    import fakeredis.aioredis as fakeredis_aioredis
    FakeRedis = fakeredis_aioredis.FakeRedis
except ImportError:
    import fakeredis
    FakeRedis = fakeredis.aioredis.FakeRedis

from tests.integration.conftest import seed_voteables_from_snapshot

import src.apps.result.advanced_search.service as adv_service_module
from src.apps.result.advanced_search.service import (
    ensure_filtered_results,
    snapshot_version_key,
)
from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.compute_service import ComputeService
from src.apps.result.whitelist import load_whitelist_db
from src.common.config import Settings
from src.common.exceptions import ValidationError
from src.db_model.raw_submit import RawCharacterSubmit


@pytest_asyncio.fixture
def fake_redis():
    return FakeRedis(decode_responses=True)


@pytest_asyncio.fixture
def settings():
    s = Settings()
    s.__dict__["vote_year"] = 2026
    s.__dict__["vote_start_iso"] = "2026-01-01T00:00:00Z"
    s.__dict__["vote_end_iso"] = "2026-12-31T23:59:59Z"
    s.__dict__["gender_question_code"] = "11011"
    s.__dict__["gender_male_option_code"] = "1101101"
    s.__dict__["gender_female_option_code"] = "1101102"
    return s


@pytest_asyncio.fixture
async def seeded(session, session_maker, fake_redis, settings, monkeypatch):
    """种子:白名单 + 3 条角色票(u1/u2 投 id1,u3 投 id2)→ compute_all。
    并把 advanced_search.service 的 get_session_maker 指到测试库。
    返回 (name1, name2):id1/id2 的展示名,供 DSL 用。"""
    await seed_voteables_from_snapshot(session, "character", 2026)
    await seed_voteables_from_snapshot(session, "music", 2026)
    wl = await load_whitelist_db(session, "character", 2026)
    id1, id2 = sorted(wl.ids)[:2]
    for vid, cid, first in [("u1", id1, True), ("u2", id1, False), ("u3", id2, True)]:
        session.add(RawCharacterSubmit(
            vote_id=vid, attempt=1,
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc), user_ip="",
            payload=[{"id": cid, "first": first, "reason": None}],
        ))
    await session.commit()
    result = await ComputeService(ComputeDAO(session), fake_redis, settings).compute_all(2026)
    assert result["ok"] is True
    monkeypatch.setattr(adv_service_module, "get_session_maker", lambda: session_maker)
    return wl.name_of(id1), wl.name_of(id2)


@pytest.mark.asyncio
async def test_compute_all_writes_snapshot_version(seeded, fake_redis):
    assert await fake_redis.get(snapshot_version_key(2026)) is not None


@pytest.mark.asyncio
async def test_filtered_ranking_uses_subset_denominator(seeded, fake_redis, settings):
    name1, _ = seeded
    infix = await ensure_filtered_results(
        fake_redis, settings, 2026, f'chars: ["{name1}"]'
    )
    ranking = json.loads(await fake_redis.get(f"result:2026:{infix}:chars:ranking"))
    # 子集 = {u1, u2}(都投了 id1);榜上只有 name1,票数 2,占比分母是子集的 2
    assert [e["name"] for e in ranking] == [name1]
    assert ranking[0]["rank"][0]["vote_count"] == 2
    assert ranking[0]["rank"][0]["vote_percentage"] == 1.0
    stats = json.loads(await fake_redis.get(f"result:2026:{infix}:global_stats"))
    assert stats["num_vote"] == 2


@pytest.mark.asyncio
async def test_cache_hit_skips_recompute(seeded, fake_redis, settings, monkeypatch):
    name1, _ = seeded
    calls = {"n": 0}
    real = adv_service_module._compute_filtered

    async def counting(*args, **kwargs):
        calls["n"] += 1
        return await real(*args, **kwargs)

    monkeypatch.setattr(adv_service_module, "_compute_filtered", counting)
    q = f'chars: ["{name1}"]'
    infix1 = await ensure_filtered_results(fake_redis, settings, 2026, q)
    infix2 = await ensure_filtered_results(fake_redis, settings, 2026, q)
    assert infix1 == infix2
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_unknown_name_raises(seeded, fake_redis, settings):
    with pytest.raises(ValidationError) as exc_info:
        await ensure_filtered_results(
            fake_redis, settings, 2026, 'chars: ["绝对不存在的角色名XYZ"]'
        )
    assert exc_info.value.message == "ADVANCED_SEARCH_UNKNOWN_NAME"


@pytest.mark.asyncio
async def test_empty_subset_is_valid_result(seeded, fake_redis, settings):
    name1, name2 = seeded
    infix = await ensure_filtered_results(
        fake_redis, settings, 2026,
        f'chars_first="{name1}" AND chars_first="{name2}"',
    )
    ranking = json.loads(await fake_redis.get(f"result:2026:{infix}:chars:ranking"))
    stats = json.loads(await fake_redis.get(f"result:2026:{infix}:global_stats"))
    assert ranking == []
    assert stats["num_vote"] == 0
```

- [ ] **Step 2: 跑测试确认失败**

`python -m pytest tests/integration/test_advanced_search_service.py -v`
预期:`ModuleNotFoundError`(service 不存在)。

- [ ] **Step 3: 实现 service.py**

`src/apps/result/advanced_search/service.py`:

```python
"""高级搜索服务:缓存查找/单飞锁/子集整包重算(设计稿 §三/§六/§七)。

缓存 key 镜像预计算布局,多一段 infix:
    result:{year}:adv:{快照版本}:{指纹}:chars:ranking  (TTL 24h)
快照版本由 compute_all 写入(定时重算后翻转,旧缓存自然失效)。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

from src.apps.result.advanced_search.dsl import Node, fingerprint, parse_query
from src.apps.result.advanced_search.subset import (
    build_facts,
    evaluate_subset,
    resolve_names,
)
from src.apps.result.compute import (
    build_segment_map,
    compute_completion_rates,
    compute_cp_ranking,
    compute_global_stats,
    compute_paper_results,
    compute_ranking,
)
from src.apps.result.compute_dao import ComputeDAO
from src.apps.result.whitelist import load_whitelist_db
from src.common.config import Settings
from src.common.database import get_session_maker

logger = logging.getLogger(__name__)

ADV_TTL_SECONDS = 24 * 3600
_LOCK_TTL_MS = 30_000
_WAIT_PROBES = 25
_WAIT_INTERVAL_SECONDS = 0.2


def snapshot_version_key(vote_year: int) -> str:
    return f"result:{vote_year}:snapshot_version"


async def ensure_filtered_results(
    redis: aioredis.Redis, settings: Settings, vote_year: int, query_str: str
) -> str:
    """确保该约束的筛选结果在缓存;返回 ResultDAO 的 key infix。

    解析/限制/未知名字错误直接向上抛(可辨识 ValidationError,契约层经
    map_app_errors 出口)。单飞锁防击穿:等锁超时兜底自己算——重复计算
    只浪费几百毫秒,不出错。
    """
    ast = parse_query(query_str)
    fp = fingerprint(ast)
    version = await redis.get(snapshot_version_key(vote_year)) or "0"
    if isinstance(version, bytes):
        version = version.decode()
    infix = f"adv:{version}:{fp}"
    marker = f"result:{vote_year}:{infix}:global_stats"
    if await redis.exists(marker):
        return infix

    lock_key = f"adv_lock:{vote_year}:{fp}"
    got_lock = await redis.set(lock_key, "1", nx=True, px=_LOCK_TTL_MS)
    if not got_lock:
        for _ in range(_WAIT_PROBES):
            await asyncio.sleep(_WAIT_INTERVAL_SECONDS)
            if await redis.exists(marker):
                return infix
        logger.warning(
            "advanced search: lock wait timed out, computing anyway "
            "(year=%d fp=%s)", vote_year, fp,
        )
    try:
        await _compute_filtered(redis, settings, vote_year, ast, infix)
    finally:
        if got_lock:
            await redis.delete(lock_key)
    return infix


async def _compute_filtered(
    redis: aioredis.Redis,
    settings: Settings,
    vote_year: int,
    ast: Node,
    infix: str,
) -> None:
    """载票 → 圈子集 → 过滤后复用 compute 纯函数整包重算 → 写缓存。

    与 ComputeService.compute_all 的差异只有:输入按子集过滤、不算
    covote(需求无消费方)、写 key 带 infix 和 TTL。窗口参数与
    compute_all 同源(settings),子集 trend 分桶口径一致。
    """
    s = settings
    vote_start = datetime.fromisoformat(s.vote_start_iso.replace("Z", "+00:00"))
    vote_end = datetime.fromisoformat(s.vote_end_iso.replace("Z", "+00:00"))
    if vote_start.tzinfo is None:
        vote_start = vote_start.replace(tzinfo=timezone.utc)
    if vote_end.tzinfo is None:
        vote_end = vote_end.replace(tzinfo=timezone.utc)
    total_hours = max(1, int((vote_end - vote_start).total_seconds() / 3600))

    session_maker = get_session_maker()
    async with session_maker() as session:
        dao = ComputeDAO(session)
        char_votes = await dao.load_char_votes()
        music_votes = await dao.load_music_votes()
        cp_votes = await dao.load_cp_votes()
        q_votes = await dao.load_questionnaire_votes(vote_year)
        char_wl = await load_whitelist_db(session, "character", vote_year)
        music_wl = await load_whitelist_db(session, "music", vote_year)

    resolved = resolve_names(ast, char_wl, music_wl)
    facts = build_facts(char_votes, music_votes, cp_votes, q_votes, char_wl, music_wl)
    subset = evaluate_subset(ast, facts, resolved)
    logger.info(
        "advanced search compute: year=%d fp=%s subset=%d/%d",
        vote_year, infix.rsplit(":", 1)[-1], len(subset), len(facts.all_vote_ids),
    )

    # segment_map 用全量问卷构建(查表只发生在子集内,设计稿 §六);
    # 其余输入全部过滤到子集。
    label_by_option = {
        s.gender_male_option_code: "male",
        s.gender_female_option_code: "female",
    }
    segment_map = build_segment_map(q_votes, s.gender_question_code, label_by_option)
    char_votes = [v for v in char_votes if v[0] in subset]
    music_votes = [v for v in music_votes if v[0] in subset]
    cp_votes = [v for v in cp_votes if v[0] in subset]
    q_votes = [v for v in q_votes if v[0] in subset]

    char_ranking, char_global = compute_ranking(
        char_votes, char_wl, segment_map, {}, vote_start, total_hours)
    music_ranking, music_global = compute_ranking(
        music_votes, music_wl, segment_map, {}, vote_start, total_hours)
    cp_ranking, cp_global = compute_cp_ranking(
        cp_votes, char_wl, segment_map, {}, vote_start, total_hours)
    all_voters = (
        {v[0] for v in char_votes} | {v[0] for v in music_votes}
        | {v[0] for v in cp_votes} | {v[0] for v in q_votes}
    )
    global_stats = compute_global_stats(
        char_votes, music_votes, cp_votes, q_votes, segment_map)
    completion_rates = compute_completion_rates(
        char_votes, music_votes, cp_votes, q_votes, all_voters)
    paper_results = compute_paper_results(q_votes, segment_map)

    def key(*parts: str) -> str:
        return f"result:{vote_year}:{infix}:" + ":".join(parts)

    pipe = redis.pipeline()
    pipe.set(key("chars", "ranking"), json.dumps(char_ranking), ex=ADV_TTL_SECONDS)
    pipe.set(key("chars", "global"), json.dumps(char_global), ex=ADV_TTL_SECONDS)
    pipe.set(key("musics", "ranking"), json.dumps(music_ranking), ex=ADV_TTL_SECONDS)
    pipe.set(key("musics", "global"), json.dumps(music_global), ex=ADV_TTL_SECONDS)
    pipe.set(key("cps", "ranking"), json.dumps(cp_ranking), ex=ADV_TTL_SECONDS)
    pipe.set(key("cps", "global"), json.dumps(cp_global), ex=ADV_TTL_SECONDS)
    pipe.set(
        key("completion_rates"), json.dumps(completion_rates), ex=ADV_TTL_SECONDS)
    for qid, data in paper_results.items():
        pipe.set(key("paper", qid), json.dumps(data), ex=ADV_TTL_SECONDS)
    # global_stats 最后写:它是 ensure 的存在性探针(marker),
    # 必须等其余 section 全部就位后才可见。
    pipe.set(key("global_stats"), json.dumps(global_stats), ex=ADV_TTL_SECONDS)
    await pipe.execute()
```

- [ ] **Step 4: 修改 `compute_service.py` 写快照版本**

在 `ComputeService.compute_all` 的 Redis pipeline 段(`await pipe.execute()` 之前、`for qid, data in paper_results.items():` 循环之后)插入:

```python
            # 快照版本:高级搜索缓存 key 的组成部分(advanced_search/service.py),
            # 定时重算后版本翻转 → 旧筛选缓存自然失效。
            pipe.set(
                self._key(vote_year, "snapshot_version"),
                str(int(time.time())),
            )
```

`time` 已在该文件顶部 import(现用 `time.monotonic()`),无需新增 import。

- [ ] **Step 5: 跑测试确认通过**

`python -m pytest tests/integration/test_advanced_search_service.py -v` → 全 PASS。
回归:`python -m pytest tests/integration/test_result_compute.py -v` → 全 PASS(compute_all 只多写一个 key,不影响现有断言)。

- [ ] **Step 6: Commit**

```bash
git add src/apps/result/advanced_search/service.py src/apps/result/compute_service.py tests/integration/test_advanced_search_service.py
git commit -m "feat(result): 高级搜索整包重算服务+快照版本缓存失效(B-050-后补5 Task 4)"
```

---

### Task 5: `ResultDAO` infix + 契约层接线(替换 `_reject_query_dsl`)

**Files:**
- Modify: `src/apps/result/dao.py`(构造参数 + `_key`)
- Modify: `src/api/graphql/resolvers/result_compat.py`(删 `_reject_query_dsl`,加 `_apply_advanced_search`,改 8 个 helper)
- Modify: `tests/integration/test_result_compat_ranking.py`(原"query DSL 拒绝"用例改为断言筛选生效)
- Test: `tests/integration/test_result_compat_advanced_search.py`

**Interfaces:**
- Consumes: Task 4 的 `ensure_filtered_results(redis, settings, vote_year, query_str) -> str`。
- Produces:
  - `ResultDAO.__init__(self, redis, settings, key_infix: str | None = None)`;`_key` 在 year 段后插入 infix。
  - `result_compat._apply_advanced_search(svc: ResultService, query: Optional[str], year: int) -> ResultService`。

- [ ] **Step 1: 写失败测试**

`tests/integration/test_result_compat_advanced_search.py`(种子/patch 直接复用现有模块的 helper,避免第二份拷贝漂移):

```python
"""契约层高级搜索集成测:GraphQL query 参数端到端(设计稿 §三/§八)。"""

from __future__ import annotations

import pytest
import pytest_asyncio

import src.apps.result.advanced_search.service as adv_service_module
from src.apps.result.whitelist import load_whitelist_db
from tests.integration.test_result_compat_ranking import (
    QUERY_CHARACTER_RANKING,
    _patch_result_service,
    _seed_and_compute,
    fake_redis,
    settings,
)
from src.api.graphql.schema import schema

__all__ = ["fake_redis", "settings"]  # re-export fixtures for pytest


@pytest_asyncio.fixture
async def gql(monkeypatch, session, session_maker, fake_redis, settings):
    """种子+compute(复用 ranking 测试的 helper)+ 双 monkeypatch:
    resolver 的 redis/settings + advanced_search 的 session_maker。
    返回 (schema, name1, name2):name1=两票角色,name2=一票角色。"""
    await _seed_and_compute(session, fake_redis, settings)
    _patch_result_service(monkeypatch, fake_redis, settings)
    monkeypatch.setattr(adv_service_module, "get_session_maker", lambda: session_maker)
    wl = await load_whitelist_db(session, "character", 2026)
    id1, id2 = sorted(wl.ids)[:2]
    return schema, wl.name_of(id1), wl.name_of(id2)


@pytest.mark.asyncio
async def test_filtered_ranking_recounts_on_subset(gql) -> None:
    schema_, name1, _ = gql
    result = await schema_.execute(
        QUERY_CHARACTER_RANKING,
        variable_values={"voteYear": 2026, "query": f'chars: ["{name1}"]'},
    )
    assert result.errors is None
    data = result.data["queryCharacterRanking"]
    # _seed_and_compute:user-1/user-2 投 id1,user-3 投 id2。
    # 筛选"投了 name1"→ 子集 {user-1, user-2} → 榜上只剩 name1,基数=2
    assert [e["name"] for e in data["entries"]] == [name1]
    assert data["entries"][0]["voteCount"] == 2
    assert data["global"]["totalVotes"] == 2


@pytest.mark.asyncio
async def test_empty_and_none_query_hit_precomputed_path(gql) -> None:
    schema_, _, _ = gql
    baseline = await schema_.execute(
        QUERY_CHARACTER_RANKING, variable_values={"voteYear": 2026, "query": None}
    )
    for q in ("", "NONE"):
        result = await schema_.execute(
            QUERY_CHARACTER_RANKING, variable_values={"voteYear": 2026, "query": q}
        )
        assert result.errors is None
        assert result.data == baseline.data


@pytest.mark.asyncio
async def test_syntax_error_is_identifiable(gql) -> None:
    schema_, _, _ = gql
    result = await schema_.execute(
        QUERY_CHARACTER_RANKING,
        variable_values={"voteYear": 2026, "query": "chars:["},
    )
    assert result.errors is not None
    assert "ADVANCED_SEARCH_SYNTAX_ERROR" in str(result.errors[0])


@pytest.mark.asyncio
async def test_unknown_name_is_identifiable(gql) -> None:
    schema_, _, _ = gql
    result = await schema_.execute(
        QUERY_CHARACTER_RANKING,
        variable_values={"voteYear": 2026, "query": 'chars: ["绝对不存在的角色名XYZ"]'},
    )
    assert result.errors is not None
    assert "ADVANCED_SEARCH_UNKNOWN_NAME" in str(result.errors[0])
```

注:若从测试模块 import fixture 的 re-export 方式(`__all__`)在本仓库 pytest 版本下不生效,把 `fake_redis`/`settings` 两个 fixture 直接复制进本文件(与 `test_result_compat_ranking.py` 顶部逐字一致)并留一行注释指向来源。

- [ ] **Step 2: 跑测试确认失败**

`python -m pytest tests/integration/test_result_compat_advanced_search.py -v`
预期:`test_filtered_ranking_recounts_on_subset` FAIL——错误里出现 `ADVANCED_SEARCH_NOT_IMPLEMENTED`(旧拒绝逻辑还在)。

- [ ] **Step 3: 实现 `ResultDAO` infix**

`src/apps/result/dao.py` 修改两处:

```python
class ResultDAO:
    def __init__(
        self,
        redis: aioredis.Redis,
        settings: Settings,
        key_infix: str | None = None,
    ):
        self.redis = redis
        self.settings = settings
        # 高级搜索筛选结果的 key 中缀(adv:{版本}:{指纹});None = 预计算主榜。
        self.key_infix = key_infix

    def _key(self, vote_year: int, *parts: str) -> str:
        base = f"result:{vote_year}:"
        if self.key_infix:
            base += f"{self.key_infix}:"
        return base + ":".join(parts)
```

- [ ] **Step 4: 实现契约层接线**

`src/api/graphql/resolvers/result_compat.py`:

1. 顶部 import 增加:

```python
from src.apps.result.advanced_search.service import ensure_filtered_results
```

2. **删除** `_reject_query_dsl` 整个函数,原位替换为:

```python
async def _apply_advanced_search(
    svc: ResultService, query: Optional[str], year: int
) -> ResultService:
    """query 为空/"NONE" → 原样返回(预计算主榜路径,零改动);否则确保
    筛选缓存就绪(miss 时载票→圈子集→整包重算,advanced_search/service.py),
    返回读 result:{year}:adv:{版本}:{指纹}:* 的 ResultService。

    解析/未知名字错误(可辨识 ValidationError)从这里向上穿透,经
    map_app_errors 出口——不再有 ADVANCED_SEARCH_NOT_IMPLEMENTED。
    """
    if not query or query == "NONE":
        return svc
    infix = await ensure_filtered_results(
        svc.result_dao.redis, svc.result_dao.settings, year, query
    )
    dao = ResultDAO(
        svc.result_dao.redis, svc.result_dao.settings, key_infix=infix
    )
    return ResultService(dao)
```

3. 改 8 个 helper:删除每处 `_reject_query_dsl(query)` 行;在 `year = await _resolve_vote_year(...)` 之后插入 `svc = await _apply_advanced_search(svc, query, year)`。以 `_query_character_or_music_ranking` 为例,改后:

```python
async def _query_character_or_music_ranking(
    category: str, vote_year: Optional[int], query: Optional[str]
) -> CharacterOrMusicRanking:
    svc = await _get_result_service()
    year = await _resolve_vote_year(svc.result_dao, vote_year, svc.result_dao.settings)
    svc = await _apply_advanced_search(svc, query, year)
    data = await _fetch_ranking(svc, category, year)
    return CharacterOrMusicRanking(
        entries=[_ranking_entry_from_dict(e) for e in data["rankings"]],
        global_=_ranking_global_from_dict(data["global"]),
    )
```

同样模式改其余 7 个:`_query_cp_ranking`、`_query_character_or_music_single`、`_query_cp_single`、`_query_global_stats`、`_query_completion_rates`、`_query_questionnaire_entries`、`_query_questionnaire_trend_entries`(后两个的 `_map_not_computed_error` 探测保持在 `_apply_advanced_search` **之后**、用筛选后的 svc——筛选路径的 global_stats 由 ensure 保证存在,探测语义不变)。`_query_character_or_music_trend` 无 query 参数,不动。

4. 更新模块 docstring 与 `query_character_ranking` 字段上的 `# 高级搜索 DSL:见 _reject_query_dsl。` 注释为 `# 高级搜索 DSL:见 _apply_advanced_search。`。

- [ ] **Step 5: 更新旧的拒绝用例**

`tests/integration/test_result_compat_ranking.py` 里断言 `ADVANCED_SEARCH_NOT_IMPLEMENTED` 的用例(grep 定位),改为断言新行为:非空合法 query 不再报错(该用例数据下筛选照常返回),或直接删除并在 commit message 说明由 `test_result_compat_advanced_search.py` 全面接管。同文件顶部 docstring 的"query DSL 拒绝"字样同步更新。改完跑:
`python -m pytest tests/integration/test_result_compat_ranking.py -v` → 全 PASS。

- [ ] **Step 6: 跑新测试确认通过**

`python -m pytest tests/integration/test_result_compat_advanced_search.py tests/integration/test_result_compat_ranking.py tests/integration/test_result_compat_rest.py -v` → 全 PASS。

- [ ] **Step 7: Commit**

```bash
git add src/apps/result/dao.py src/api/graphql/resolvers/result_compat.py tests/integration/test_result_compat_advanced_search.py tests/integration/test_result_compat_ranking.py
git commit -m "feat(result): 契约层接通高级搜索——query 参数子集重算取代 NOT_IMPLEMENTED(B-050-后补5 Task 5)"
```

---

### Task 6: 性能冒烟 + 全量回归 + 文档收尾

**Files:**
- Test: `tests/unit/test_advanced_search_perf.py`
- Modify: `docs/CHANGELOG.md`、`docs/BACKLOG.md`、`docs/migration/result-stats-audit-2026-08-14.md`、`docs/superpowers/specs/2026-08-14-advanced-search-dsl-design.md`(§十一状态)

**Interfaces:** Consumes Task 1-5 全部;无新接口。

- [ ] **Step 1: 写性能冒烟测试**

`tests/unit/test_advanced_search_perf.py`:

```python
"""性能冒烟:5 万合成票走 事实索引→求值→子集重排名 全程 < 2s(设计稿 §九-6)。

纯内存路径(不含 DB 载票——载票是既有 compute_all 同款 SELECT,不在此测)。
阈值给足余量:CI 机器慢也不该 flake;若仍偶发,放宽到 4s 并在此注明。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from src.apps.result.advanced_search.dsl import parse_query
from src.apps.result.advanced_search.subset import (
    build_facts,
    evaluate_subset,
    resolve_names,
)
from src.apps.result.compute import compute_ranking
from src.apps.result.whitelist import Whitelist, WhitelistEntry

N_VOTES = 50_000
N_CHARS = 50
_DT = datetime(2026, 1, 2, tzinfo=timezone.utc)


def test_perf_smoke_50k_votes() -> None:
    wl = Whitelist([
        WhitelistEntry(
            candidate_id=100 + j, voteable_id=j, old_id=None, name=f"角色{j}",
            name_jp="", origin="", type="", first_appearance=None,
            album=None, system_id=j,
        )
        for j in range(N_CHARS)
    ])
    votes = [
        (
            f"u{i}", _DT,
            [{"id": str(100 + (i % N_CHARS)), "first": i % 7 == 0, "reason": None},
             {"id": str(100 + ((i + 1) % N_CHARS)), "first": False, "reason": None}],
        )
        for i in range(N_VOTES)
    ]
    ast = parse_query('chars: ["角色1", "角色2"] OR chars_first="角色3"')

    t0 = time.monotonic()
    resolved = resolve_names(ast, wl, Whitelist([]))
    facts = build_facts(votes, [], [], [], wl, Whitelist([]))
    subset = evaluate_subset(ast, facts, resolved)
    filtered = [v for v in votes if v[0] in subset]
    ranking, _global = compute_ranking(filtered, wl, {}, {}, _DT, 24)
    elapsed = time.monotonic() - t0

    assert subset  # 约束确实圈到了票
    assert ranking
    assert elapsed < 2.0, f"advanced search pipeline took {elapsed:.2f}s"
```

- [ ] **Step 2: 跑冒烟 + 全量回归 + lint**

```
python -m pytest tests/unit/test_advanced_search_perf.py -v
python -m pytest tests/ -q
flake8 src/apps/result/advanced_search/ src/api/graphql/resolvers/result_compat.py src/apps/result/dao.py src/apps/result/compute_service.py
```

预期:全 PASS、flake8 无告警。任何失败先修复再进 Step 3。

- [ ] **Step 3: 文档收尾**

1. `docs/CHANGELOG.md` 顶部加条目(参照 2026-08-14 既有条目格式):日期、`### Added` 高级搜索功能说明(10 个 query 参数点亮、三种错误 kind、缓存布局、无 DB 变更、新依赖 lark)、`### 兼容性`(前端零改动;`ADVANCED_SEARCH_NOT_IMPLEMENTED` kind 移除,改为三种细分错误;问卷原子在 B-054 前匹配为空的已知限制)。
2. `docs/BACKLOG.md`:B-050-后补5 行标 ✅ 已完成 + 日期 + commit,整行按维护规则迁至 `BACKLOG-archive.md`;B-053 行的"共用索引"备注更新为指向 `advanced_search/subset.py`。
3. `docs/migration/result-stats-audit-2026-08-14.md` §四/§六:高级搜索状态 🔴→✅。
4. 设计稿 §十一补一行:已实施,commit 区间。

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_advanced_search_perf.py docs/
git commit -m "test(result): 高级搜索 5 万票性能冒烟;docs: B-050-后补5 完成收尾"
```

---

## Self-Review 记录(计划完成后自查)

- **Spec 覆盖**:设计稿 §四文法(Task 1)、§4.2 归一化/§4.3 限制(Task 2)、§五语义含两个拍板决策(Task 3)、§六重算/§七缓存与单飞/快照版本(Task 4)、§三接入点/§八错误(Task 5)、§九测试含性能冒烟(各 Task + Task 6)、§十一文档同步(Task 6)。§十非目标无需任务。
- **类型一致性**:`parse_query`/`fingerprint`/`ensure_filtered_results`/`VoteFacts`/`_apply_advanced_search` 的签名在 Interfaces 块与代码块一致;votes 元组形态与 `ComputeDAO` 实际返回核对过(含 q_votes 二元组)。
- **无占位符**:所有测试与实现均为完整代码;仅 Task 5 Step 5(旧用例改写)与 Task 6 Step 3(文档措辞)是"定位后按说明修改",因其内容依赖执行时的文件现状,已给出定位方式与修改要点。
