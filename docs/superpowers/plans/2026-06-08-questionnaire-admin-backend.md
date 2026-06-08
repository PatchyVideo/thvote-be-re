# 问卷管理增强（自由列表 + 全层级 CRUD）— 后端(含管理端)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development / executing-plans. Steps use `- [ ]`.

**Goal:** 把问卷结构从「固定 8 槽 + 年份」改为「自由问卷列表 + 自增 id」,提供问卷/题组/题/选项四层 CRUD 端点与自研管理端编辑器,公开结构端点改返回问卷数组。

**Architecture:** 重塑 `questionnaire_def`(去 vote_year/slot,加 key/required;四层 PK 自增)→ migration 0010 drop&recreate(表空,无数据损失)。assembler/importer/completion 改数组契约。新增 `QuestionnaireAdminService/DAO` 做四层 CRUD + 级联删除。管理端单文件内做列表页 + 单问卷编辑页。

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, 原生 HTML/CSS/JS

**Design Spec:** `docs/superpowers/specs/2026-06-08-questionnaire-admin-backend-design.md`

**前置:** B-039 后端已在 zfq_dev(8 槽 + 年份)。本计划取代其 admin/契约部分;复用 paper_answer / submitPaperV2 / 投票门禁挂载点。基于 zfq_dev 拉新分支实施。

---

## File Map

| 文件 | 操作 |
|---|---|
| `src/db_model/questionnaire_def.py` | 重塑 4 模型 |
| `alembic/versions/0010_questionnaire_freeform.py` | 新建(drop&recreate 4 表) |
| `src/apps/questionnaire/assembler.py` | 输出改问卷数组 |
| `src/apps/questionnaire/importer.py` | 解析改问卷数组 |
| `src/apps/questionnaire/completion.py` | required 字段判定 |
| `src/apps/questionnaire/service.py` | get_structure 去年份;答案 flatten 改数组 |
| `src/apps/questionnaire/dao.py` | load_structure_rows 去年份;replace_answers 不变 |
| `src/apps/questionnaire/router.py` | structure 去 vote_year |
| `src/apps/questionnaire/admin_dao.py` | 新建:四层 CRUD + 级联 |
| `src/apps/questionnaire/admin_service.py` | 新建 |
| `src/apps/questionnaire/admin_router.py` | 新建:13 CRUD 端点 + 改造 import |
| `src/api/rest/v1/__init__.py` | 注册 admin_router |
| `src/admin_ui/index.html` | 问卷配置 Tab:列表 + 编辑页 |
| 既有 B-039 测试 | 随契约更新 |
| `tests/...` | 新建 |

---

## Task 1: 重塑模型 + migration 0010

**Files:** `src/db_model/questionnaire_def.py`; `alembic/versions/0010_questionnaire_freeform.py`

- [ ] **Step 1:** 将 `src/db_model/questionnaire_def.py` 的 4 个结构模型替换为(PaperAnswer 不动):

```python
class QuestionnaireDef(Base):
    __tablename__ = "questionnaire_def"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    introduction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(8), nullable=False, default="main")
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class QuestionGroupDef(Base):
    __tablename__ = "question_group_def"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    questionnaire_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hidden_by_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class QuestionDef(Base):
    __tablename__ = "question_def"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(8), nullable=False, default="Single")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    introduction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_input_len: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)


class OptionDef(Base):
    __tablename__ = "option_def"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    related_question_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    mutex_option_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    option_group: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```
确保文件顶部 import 含 `Boolean`(`from sqlalchemy import Boolean, JSON, DateTime, Integer, String, Text, UniqueConstraint, func`)。PaperAnswer 保持原样。

- [ ] **Step 2:** 创建 `alembic/versions/0010_questionnaire_freeform.py`(`revision="0010"`, `down_revision="0009"`)。`upgrade()`:先 `op.drop_table` 顺序 `option_def → question_def → question_group_def → questionnaire_def`,再按新 shape `op.create_table` 这 4 表(列同 Step 1;PK autoincrement;questionnaire_def 的 `key` 加 UNIQUE;group/question/option 的 FK 列建 index)。`downgrade()` 反向(可只 drop 新表)。参照 `0008_questionnaire_structure.py` 的写法,注意 `order` 是保留字需加引号(沿用 0008 做法)。

- [ ] **Step 3:** 验证 `python -c "from src.db_model import QuestionnaireDef; print(QuestionnaireDef.__table__.columns.keys())"` → 含 `key, title, category, required, order`,不含 `vote_year, slot`。
- [ ] **Step 4:** flake8 + commit `feat(questionnaire): remodel structure tables (free-form, autoincrement) + migration 0010 (B-041)`

---

## Task 2: assembler → 问卷数组(TDD)

**Files:** `src/apps/questionnaire/assembler.py`; `tests/unit/test_questionnaire_assembler.py`(改写)

- [ ] **Step 1:** 改写 `tests/unit/test_questionnaire_assembler.py` 为新契约:

```python
"""Tests: assemble DB rows -> {"questionnaires":[...]} array."""


def _q(id, key, category="main", required=False, title="t", introduction="i", order=0):
    return {"id": id, "key": key, "category": category, "required": required,
            "title": title, "introduction": introduction, "order": order}


def _g(id, questionnaire_id, order=0, hidden_by_default=False):
    return {"id": id, "questionnaire_id": questionnaire_id, "order": order,
            "hidden_by_default": hidden_by_default}


def _qn(id, group_id, type="Single", content="c", introduction="i", order=0,
        max_input_len=1000):
    return {"id": id, "group_id": group_id, "type": type, "content": content,
            "introduction": introduction, "order": order, "max_input_len": max_input_len}


def _o(id, question_id, content="o", related=None, mutex=None, group=0, order=0):
    return {"id": id, "question_id": question_id, "content": content,
            "related_question_ids": related or [], "mutex_option_ids": mutex or [],
            "option_group": group, "order": order}


def test_assemble_array_shape_and_order():
    from src.apps.questionnaire.assembler import assemble_structure

    questionnaires = [_q(2, "b", order=2, required=False),
                      _q(1, "a", order=1, required=True, title="必填")]
    groups = [_g(10, 1, order=1, hidden_by_default=True)]
    questions = [_qn(100, 10, type="Single")]
    options = [_o(1000, 100, related=[101], mutex=[1001])]

    out = assemble_structure(questionnaires, groups, questions, options)
    qs = out["questionnaires"]
    assert [q["id"] for q in qs] == [1, 2]  # sorted by order
    q1 = qs[0]
    assert q1["key"] == "a" and q1["required"] is True and q1["category"] == "main"
    g = q1["questionGroups"][0]
    assert g["hiddenByDefault"] is True
    opt = g["questions"][0]["options"][0]
    assert opt["relatedQuestionIds"] == [101]
    assert opt["mutexOptionIds"] == [1001]
    assert opt["optionGroup"] == 0
    # questionnaire with no groups still appears
    assert qs[1]["questionGroups"] == []
```

- [ ] **Step 2:** 运行确认失败。
- [ ] **Step 3:** 改写 `assemble_structure`:删除 `_SLOT_TO_KEY` 映射;输出 `{"questionnaires": [...]}`,按 `order` 排序;问卷项含 `id/key/title/introduction/category/required/order/questionGroups`;组项的 `initialQuestionId` 改 `hiddenByDefault`(读 `hidden_by_default`)。question/option 输出字段不变(`relatedQuestionIds/mutexOptionIds/optionGroup/maxInputLen`)。

```python
def _question_out(q, options_by_question):
    opts = sorted(options_by_question.get(q["id"], []), key=lambda o: o.get("order", 0))
    return {"id": q["id"], "type": q.get("type", "Single"),
            "content": q.get("content", ""), "introduction": q.get("introduction", ""),
            "maxInputLen": q.get("max_input_len", 1000),
            "options": [_option_out(o) for o in opts]}


def _group_out(g, questions_by_group, options_by_question):
    qs = sorted(questions_by_group.get(g["id"], []), key=lambda q: q.get("order", 0))
    return {"id": g["id"], "order": g.get("order", 0),
            "hiddenByDefault": g.get("hidden_by_default", False),
            "questions": [_question_out(q, options_by_question) for q in qs]}


def _questionnaire_out(qn, groups_by_q, questions_by_group, options_by_question):
    grps = sorted(groups_by_q.get(qn["id"], []), key=lambda g: g.get("order", 0))
    return {"id": qn["id"], "key": qn.get("key", ""), "title": qn.get("title", ""),
            "introduction": qn.get("introduction", ""),
            "category": qn.get("category", "main"),
            "required": bool(qn.get("required", False)), "order": qn.get("order", 0),
            "questionGroups": [_group_out(g, questions_by_group, options_by_question)
                               for g in grps]}


def assemble_structure(questionnaires, groups, questions, options):
    groups_by_q = {}
    for g in groups:
        groups_by_q.setdefault(g["questionnaire_id"], []).append(g)
    questions_by_group = {}
    for q in questions:
        questions_by_group.setdefault(q["group_id"], []).append(q)
    options_by_question = {}
    for o in options:
        options_by_question.setdefault(o["question_id"], []).append(o)
    ordered = sorted(questionnaires, key=lambda q: q.get("order", 0))
    return {"questionnaires": [
        _questionnaire_out(qn, groups_by_q, questions_by_group, options_by_question)
        for qn in ordered
    ]}
```
(保留 `_option_out` 不变。)

- [ ] **Step 4:** 运行通过。flake8 + commit `feat(questionnaire): assembler outputs questionnaire array (B-041)`

---

## Task 3: importer → 问卷数组(TDD)

**Files:** `src/apps/questionnaire/importer.py`; `tests/unit/test_questionnaire_importer.py`(改写)

- [ ] **Step 1:** 改写测试为数组输入:

```python
"""Tests: parse {"questionnaires":[...]} tree -> rows."""


def _tree():
    return {"questionnaires": [
        {"id": 1, "key": "a", "title": "必填", "category": "main", "required": True,
         "order": 1, "questionGroups": [
            {"id": 10, "order": 1, "hiddenByDefault": False, "questions": [
                {"id": 100, "type": "Single", "content": "q1", "introduction": "",
                 "maxInputLen": 1000, "options": [
                    {"id": 1000, "content": "o1", "relatedQuestionIds": [101],
                     "mutexOptionIds": [1001], "optionGroup": 0}]}]}]},
        {"id": 2, "key": "b", "title": "额外", "category": "extra", "required": False,
         "order": 2, "questionGroups": []},
    ]}


def test_parse_array():
    from src.apps.questionnaire.importer import parse_structure_tree
    qns, groups, questions, options = parse_structure_tree(_tree())
    by_id = {q["id"]: q for q in qns}
    assert by_id[1]["key"] == "a" and by_id[1]["required"] is True
    assert by_id[1]["category"] == "main"
    assert by_id[2]["category"] == "extra"
    assert groups[0]["questionnaire_id"] == 1
    assert groups[0]["hidden_by_default"] is False
    assert questions[0]["group_id"] == 10
    assert options[0]["question_id"] == 100
    assert options[0]["related_question_ids"] == [101]


def test_roundtrip_through_assembler():
    from src.apps.questionnaire.assembler import assemble_structure
    from src.apps.questionnaire.importer import parse_structure_tree
    rows = parse_structure_tree(_tree())
    out = assemble_structure(*rows)
    assert out["questionnaires"][0]["key"] == "a"
    assert out["questionnaires"][0]["questionGroups"][0]["questions"][0]["id"] == 100
```

- [ ] **Step 2:** 运行确认失败。
- [ ] **Step 3:** 改写 `parse_structure_tree`:遍历 `tree["questionnaires"]`,每份产出 questionnaire row(`id?/key/title/introduction/category/required/order`),其 `questionGroups` → group rows(`id?/questionnaire_id/order/hidden_by_default`),`questions` → question rows(`id?/group_id/type/content/introduction/order/max_input_len`),`options` → option rows(`id?/question_id/content/related_question_ids/mutex_option_ids/option_group/order`)。`id` 字段:若传入则带上(导入保留 id),否则不带(由 DB 自增)——本任务先**总是带 id**(导入题库通常自带稳定 id);DAO 层 replace 时按是否带 id 决定。
- [ ] **Step 4:** 运行通过。flake8 + commit `feat(questionnaire): importer parses questionnaire array (B-041)`

---

## Task 4: completion → required 字段(TDD)

**Files:** `src/apps/questionnaire/completion.py`; `tests/unit/test_questionnaire_completion.py`(改写)

- [ ] **Step 1:** 改写测试:structure 为数组,required 由问卷 `required` 字段决定:

```python
def _structure(required_groups, required=True):
    return {"questionnaires": [
        {"id": 1, "key": "a", "category": "main", "required": required, "order": 1,
         "questionGroups": [{"id": gid, "order": i, "hiddenByDefault": False,
                             "questions": []}
                            for i, gid in enumerate(required_groups)]},
        {"id": 2, "key": "b", "category": "extra", "required": False, "order": 2,
         "questionGroups": [{"id": 99, "order": 1, "hiddenByDefault": False,
                             "questions": []}]},
    ]}


def test_complete_when_required_groups_answered():
    from src.apps.questionnaire.completion import is_complete
    s = _structure([10, 11])
    answers = [{"questionnaire_id": 1, "group_id": 10},
               {"questionnaire_id": 1, "group_id": 11}]
    assert is_complete(s, answers) is True


def test_incomplete_when_required_group_missing():
    from src.apps.questionnaire.completion import is_complete
    s = _structure([10, 11])
    assert is_complete(s, [{"questionnaire_id": 1, "group_id": 10}]) is False


def test_non_required_questionnaire_ignored():
    from src.apps.questionnaire.completion import is_complete
    s = _structure([10])
    # answering required q1.g10 is enough; q2 (not required) ignored
    assert is_complete(s, [{"questionnaire_id": 1, "group_id": 10}]) is True


def test_no_required_questionnaires_complete():
    from src.apps.questionnaire.completion import is_complete
    s = _structure([10], required=False)
    assert is_complete(s, []) is True
```

- [ ] **Step 2:** 运行确认失败。
- [ ] **Step 3:** 改写 `completion.py`:

```python
def _required_groups(structure):
    out = []
    for qn in structure.get("questionnaires", []):
        if qn.get("required"):
            for g in qn.get("questionGroups", []):
                out.append((qn["id"], g["id"]))
    return out


def is_complete(structure, answers):
    required = _required_groups(structure)
    if not required:
        return True
    answered = {(a["questionnaire_id"], a["group_id"]) for a in answers}
    return all(p in answered for p in required)
```

- [ ] **Step 4:** 运行通过。flake8 + commit `feat(questionnaire): completion uses required field over array (B-041)`

---

## Task 5: 结构端点去年份 + service 适配

**Files:** `src/apps/questionnaire/dao.py`, `service.py`, `router.py`; `tests/integration/test_questionnaire_domain.py`(改写)

- [ ] **Step 1:** `dao.py` `load_structure_rows(vote_year)` → `load_structure_rows()`(去 vote_year 过滤,读全部结构行)。`replace_answers`/`get_answers` 保留 vote_year(答案仍分年)。
- [ ] **Step 2:** `service.py`:`get_structure()` 去 vote_year 参数;`is_complete(vote_id, vote_year)` 内部 `get_structure()` + `get_answers(vote_id, vote_year)`。`submit_answers` 的 `_flatten_answer_state` 改为接受**扁平数组** `answers=[{questionnaireId, groupId, activeQuestionId, selectedOptionIds, input}]`:

```python
def _flatten_answer_state(answers: list[dict]) -> list[dict]:
    rows = []
    for a in answers:
        rows.append({
            "questionnaire_id": a.get("questionnaireId"),
            "group_id": a.get("groupId"),
            "active_question_id": a.get("activeQuestionId"),
            "selected_option_ids": a.get("selectedOptionIds") or [],
            "input_text": a.get("input"),
        })
    return rows
```
`submit_answers(vote_id, vote_year, answers)` 调它。

- [ ] **Step 3:** `router.py`:`GET /questionnaire/structure` 去掉 `vote_year` 参数,直接 `await service.get_structure()`。
- [ ] **Step 4:** 改写 `tests/integration/test_questionnaire_domain.py`:seed 用新模型字段(key/required/hidden_by_default,自增 id 用 seed 指定);structure 断言数组;submit/get 用扁平 answers 数组;is_complete 用 required 问卷。
- [ ] **Step 5:** 同步改 GraphQL `submitPaperV2`:其 `answers` JSON 现按扁平数组传入 `service.submit_answers`(resolver 已透传 JSON,无需改签名,确认 service 调用参数名)。
- [ ] **Step 6:** 运行 `pytest tests/integration/test_questionnaire_domain.py tests/contract/test_paper_v2_schema.py -q`;flake8。commit `feat(questionnaire): structure endpoint year-less + flat answer array (B-041)`

---

## Task 6: admin CRUD service/dao + 级联删除(TDD)

**Files:** `src/apps/questionnaire/admin_dao.py`, `admin_service.py`(新建);`tests/integration/test_questionnaire_crud.py`(新建)

- [ ] **Step 1:** 写失败集成测试 `tests/integration/test_questionnaire_crud.py`(用 conftest `session`):覆盖
  - 建问卷→建题组→建题→建选项,各返回 id;
  - `get_one(qid)` 返回完整树;
  - 改问卷元数据、改题、改选项;
  - 删问卷级联清空其 group/question/option;
  - key 重复建问卷 → 抛 `KeyConflictError`;
  - 建子节点父不存在 → 抛 `ParentNotFoundError`。

```python
import pytest
from src.apps.questionnaire.admin_dao import QuestionnaireAdminDAO
from src.apps.questionnaire.admin_service import (
    KeyConflictError, ParentNotFoundError, QuestionnaireAdminService,
)


def _svc(session):
    return QuestionnaireAdminService(QuestionnaireAdminDAO(session))


@pytest.mark.asyncio
async def test_full_crud_and_cascade(session):
    svc = _svc(session)
    qid = await svc.create_questionnaire(
        {"key": "a", "title": "必填", "category": "main", "required": True, "order": 1}
    )
    gid = await svc.create_group({"questionnaire_id": qid, "order": 1})
    quid = await svc.create_question({"group_id": gid, "type": "Single", "content": "q"})
    oid = await svc.create_option({"question_id": quid, "content": "o"})

    tree = await svc.get_questionnaire(qid)
    assert tree["key"] == "a"
    assert tree["questionGroups"][0]["questions"][0]["options"][0]["id"] == oid

    assert await svc.update_question(quid, {"content": "q2"}) is True
    assert await svc.delete_questionnaire(qid) is True
    assert await svc.get_questionnaire(qid) is None
    # cascade: option/question/group gone
    assert await svc.get_question(quid) is None


@pytest.mark.asyncio
async def test_key_conflict(session):
    svc = _svc(session)
    await svc.create_questionnaire({"key": "dup", "title": "x"})
    with pytest.raises(KeyConflictError):
        await svc.create_questionnaire({"key": "dup", "title": "y"})


@pytest.mark.asyncio
async def test_parent_not_found(session):
    svc = _svc(session)
    with pytest.raises(ParentNotFoundError):
        await svc.create_group({"questionnaire_id": 999999, "order": 1})
```

- [ ] **Step 2:** 运行确认失败。
- [ ] **Step 3:** 实现 `admin_dao.py`:对 4 模型的 create/get/get_one(树)/update/delete;`delete_questionnaire` 收集其 group ids→question ids→option ids 批量删(共用 `_collect_descendants`);`create_*` 子节点前校验父存在;`create_questionnaire` 前查 key 唯一。`get_questionnaire(id)` 组装单份树(复用 assembler 的单问卷输出或直接拼)。返回新建行的 `id`。
- [ ] **Step 4:** 实现 `admin_service.py`:薄封装 DAO;定义 `KeyConflictError`/`ParentNotFoundError`;create/update/delete/get 各方法。
- [ ] **Step 5:** 运行通过。flake8 + commit `feat(questionnaire): admin CRUD service/dao + cascade delete + tests (B-041)`

---

## Task 7: admin CRUD 路由 + 改造 import + contract

**Files:** `src/apps/questionnaire/admin_router.py`(新建);`src/api/rest/v1/__init__.py`;`tests/contract/test_questionnaire_admin_crud.py`(新建)

- [ ] **Step 1:** 新建 `admin_router.py`:`router = APIRouter(prefix="/admin", tags=["questionnaire-admin"])`,全端点 `X-Admin-Secret`(复用 `_check_admin_secret` 模式 / 自带校验)。端点:
  - 问卷:`GET /questionnaires`(列表,元数据+group_count)、`GET /questionnaires/{id}`(树)、`POST /questionnaires`、`PUT /questionnaires/{id}`、`DELETE /questionnaires/{id}`
  - 题组:`POST /question-groups`、`PUT /question-groups/{id}`、`DELETE /question-groups/{id}`
  - 题:`POST /questions`、`PUT /questions/{id}`、`DELETE /questions/{id}`
  - 选项:`POST /options`、`PUT /options/{id}`、`DELETE /options/{id}`
  - 改造 `POST /questionnaire/import`:接受 `{"questionnaires":[...]}`,调 importer+replace。
  错误映射:`KeyConflictError`→409 `QUESTIONNAIRE_KEY_CONFLICT`;`ParentNotFoundError`→404 `PARENT_NOT_FOUND`;id 不存在→404 `NOT_FOUND`。
- [ ] **Step 2:** 注册进 `src/api/rest/v1/__init__.py`(`include_router(questionnaire_admin_router)`)。注意静态路径 `/questionnaires` 与 `/questionnaires/{id}` 顺序无冲突(方法不同 / FastAPI 处理)。
- [ ] **Step 3:** contract 测试 `tests/contract/test_questionnaire_admin_crud.py`(用 contract conftest 的 `app`/`admin_secret`):无 secret→403;建问卷→列表含它;建树→get tree;key 冲突→409;删→404。
- [ ] **Step 4:** `pytest tests/ -q`(更新后全绿,除既有 pnvs 本地失败)+ flake8 `src/`。commit `feat(questionnaire): admin CRUD endpoints + array import + contract (B-041)`

---

## Task 8: 管理端 UI(列表页 + 单问卷编辑页)

**Files:** `src/admin_ui/index.html`

- [ ] **Step 1:** 替换现有「问卷配置」Tab 的 `questionnaire()` 为**列表页**:调 `GET /admin/questionnaires` 渲染表格(key/title/category/required/group_count + 编辑/删除),顶部「+ 新建问卷」「整树导入」。新建/导入复用 modal。
- [ ] **Step 2:** 新增**单问卷编辑页** `editQuestionnaire(id)`:调 `GET /admin/questionnaires/{id}` 渲染树(题组→题→选项),每节点行内 改/删/加子节点按钮;`← 返回列表`。节点编辑用 modal:
  - 问卷元数据:key/title/category(下拉 main/extra)/required(勾选)/order
  - 题组:order / hidden_by_default(勾选)
  - 题:type(下拉 Single/Multiple/Input)/content/introduction/max_input_len/order
  - 选项:content/option_group/order + related(当前问卷所有题的多选)+ mutex(当前问卷所有选项的多选),显示标题、值存 id
- [ ] **Step 3:** 各增删改调对应 CRUD 端点,成功后局部刷新当前问卷树;删除带级联提示。视图切换用内存状态(`renderQuestionnaireList()` / `renderQuestionnaireEditor(id)`),不引入路由库。
- [ ] **Step 4:** `python -c "from src.main import create_app; create_app()"` 确认挂载;本地 `uvicorn` 目检列表/编辑/增删改全流程。
- [ ] **Step 5:** commit `feat(admin-ui): questionnaire list page + nested editor (B-041)`

手工验收清单:
- [ ] 列表页展示所有问卷 + 新建/删除
- [ ] 进编辑页:题组/题/选项树正确;各级增删改即时生效
- [ ] related/mutex 用下拉选当前问卷的题/选项(存 id)
- [ ] 整树导入(数组 JSON)→ 列表刷新
- [ ] 删问卷级联提示 + 生效

---

## Task 9: 全量回归 + BACKLOG

- [ ] **Step 1:** `pytest tests/ -q --tb=short`(仅既有 pnvs 本地失败可接受);`flake8 src/ --max-line-length=88` 干净。
- [ ] **Step 2:** `docs/BACKLOG.md` 标 B-041 后端完成。
- [ ] **Step 3:** commit;按需合并 zfq_dev 部署。

---

## Self-Review 注意
- migration 0010 drop&recreate 仅因表空(zfq_dev 测试);若届时表里已有数据,改为 ALTER 迁移并保数据。
- 既有 B-039 测试(assembler/importer/completion/domain/admin import)随契约更新,勿留旧 8 槽断言。
- `submitPaperV2` 答案契约由"嵌套 buckets"改为"扁平数组"——前端 plan 同步。
- related/mutex 引用自增 id:UI 必须在"该问卷已存在的题/选项"范围内选,避免悬空引用。
