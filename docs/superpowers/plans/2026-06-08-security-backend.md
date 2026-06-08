# Block 1 安全 — 后端(含管理端)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给后端加三道安全闸:① 提名时间窗 + 二创提名自动校验(域名/发布时间/udid 去重)+ 人工审核队列;② 投票前"问卷已提交"弱门禁;③ 管理端提名审核界面。

**Architecture:** 提名校验纯逻辑放 `nomination_service.py`(域名/时间/去重,mock 友好);提交编排调 scraper 取 udid+发布时间,逐条入 `dojin_nomination` 表(status=pending);submit 服务的角色/音乐/CP 入口加问卷门禁;管理端加审核端点 + Tab。

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, 现有 scraper 服务, Alembic

**Design Spec:** `docs/superpowers/specs/2026-06-08-security-backend-design.md`

---

## File Map

| 文件 | 操作 |
|---|---|
| `src/common/config.py` | Modify — 加 5 配置字段 |
| `src/db_model/dojin_nomination.py` | Create — DojinNomination 模型 |
| `src/db_model/__init__.py` | Modify — 导出 |
| `alembic/versions/0007_dojin_nomination.py` | Create — migration |
| `src/apps/submit/nomination_service.py` | Create — 纯校验逻辑(域名/时间/去重) |
| `src/apps/submit/dao.py` | Modify — dojin_nomination 读写 + 问卷存在性查询 |
| `src/apps/submit/service.py` | Modify — dojin 走 nomination 流程;角色/音乐/CP 加门禁 |
| `src/apps/submit/schemas.py` | Modify — 提名逐条结果模型 |
| `src/apps/admin/{router,service,schemas}.py` | Modify — nominations 审核端点 |
| `src/apps/result/router.py`(或新路由) | Modify — `/nominations/approved` |
| `src/admin_ui/index.html` | Modify — 提名审核 Tab |
| `tests/{unit,integration,contract}/...` | Create |

---

## Task 1: 配置项

**Files:** Modify `src/common/config.py`

- [ ] **Step 1:** 在 `Settings` 类中,`vote_end_iso` 字段附近追加:

```python
    # 提名(二创)配置
    nomination_start_iso: Optional[str] = Field(None, validation_alias="NOMINATION_START_ISO")
    nomination_end_iso: Optional[str] = Field(None, validation_alias="NOMINATION_END_ISO")
    work_eligible_start_iso: Optional[str] = Field(None, validation_alias="WORK_ELIGIBLE_START_ISO")
    work_eligible_end_iso: Optional[str] = Field(None, validation_alias="WORK_ELIGIBLE_END_ISO")
    dojin_domain_allowlist: list[str] = Field(default_factory=list, validation_alias="DOJIN_DOMAIN_ALLOWLIST")
```

注意 `dojin_domain_allowlist` 若 Nacos 以逗号字符串下发,pydantic-settings 对 `list[str]` 默认按 JSON 解析,可能不兼容逗号串。**为稳妥,改用 str 字段 + property 拆分**:

```python
    dojin_domain_allowlist_raw: Optional[str] = Field(None, validation_alias="DOJIN_DOMAIN_ALLOWLIST")

    @property
    def dojin_domain_allowlist(self) -> list[str]:
        if not self.dojin_domain_allowlist_raw:
            return []
        return [d.strip() for d in self.dojin_domain_allowlist_raw.split(",") if d.strip()]
```

- [ ] **Step 2:** 验证 `python -c "from src.common.config import get_settings; s=get_settings(); print(s.nomination_start_iso, s.dojin_domain_allowlist)"` → 打印 `None []`
- [ ] **Step 3:** flake8 `src/common/config.py --max-line-length=88`,commit `feat(security): nomination/dojin config fields (B-037)`

---

## Task 2: DojinNomination 模型 + migration

**Files:** Create `src/db_model/dojin_nomination.py`; Modify `__init__.py`; Create migration

- [ ] **Step 1:** 创建 `src/db_model/dojin_nomination.py`:

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DojinNomination(Base):
    __tablename__ = "dojin_nomination"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    udid: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    author: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    dojin_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    publish_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    reject_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("vote_id", "udid", name="uq_dojin_nom_voter_udid"),
    )
```

- [ ] **Step 2:** `__init__.py` 加 `from .dojin_nomination import DojinNomination` + 加进 `__all__`。
- [ ] **Step 3:** 验证 `python -c "from src.db_model import DojinNomination; print(DojinNomination.__tablename__)"` → `dojin_nomination`
- [ ] **Step 4:** 手写 migration `alembic/versions/0007_dojin_nomination.py`(`revision="0007"`, `down_revision="0006"`),`create_table("dojin_nomination", ...)` 镜像上面所有列 + UniqueConstraint + index(vote_id, udid)。`downgrade` 为 `drop_table`。参照 `0006_sync_run_log_and_raw_work.py` 的写法。
- [ ] **Step 5:** flake8 + commit `feat(security): DojinNomination model + migration 0007 (B-037)`

> migration 不在本地跑(无 Postgres);CI 的 `alembic upgrade head` 会验证。集成测试用 sqlite `create_all`,自动包含新表。

---

## Task 3: nomination_service 纯校验逻辑(TDD)

**Files:** Create `src/apps/submit/nomination_service.py`; Create `tests/unit/test_nomination_validate.py`

- [ ] **Step 1:** 写失败测试 `tests/unit/test_nomination_validate.py`:

```python
"""Unit tests for nomination pure validation helpers."""
from datetime import datetime, timezone


def test_extract_domain():
    from src.apps.submit.nomination_service import extract_domain
    assert extract_domain("https://www.bilibili.com/video/BV1?x=1") == "bilibili.com"
    assert extract_domain("http://youtube.com/watch") == "youtube.com"
    assert extract_domain("not a url") is None


def test_domain_allowed():
    from src.apps.submit.nomination_service import domain_allowed
    allow = ["bilibili.com", "youtube.com"]
    assert domain_allowed("https://www.bilibili.com/x", allow) is True
    assert domain_allowed("https://evil.com/x", allow) is False
    # empty allowlist → everything allowed
    assert domain_allowed("https://anything.com", []) is True


def test_within_window():
    from src.apps.submit.nomination_service import within_window
    s = "2026-01-01T00:00:00+00:00"
    e = "2026-12-31T23:59:59+00:00"
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert within_window(now, s, e) is True
    before = datetime(2025, 6, 1, tzinfo=timezone.utc)
    assert within_window(before, s, e) is False
    # missing bounds → treated as open (None means unbounded)
    assert within_window(now, None, None) is True


def test_publish_date_eligible():
    from src.apps.submit.nomination_service import publish_date_eligible
    pub = datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert publish_date_eligible(pub, "2026-01-01T00:00:00+00:00", "2026-12-31T00:00:00+00:00") is True
    assert publish_date_eligible(pub, "2027-01-01T00:00:00+00:00", None) is False
    # unknown publish date → eligible (defer to manual review)
    assert publish_date_eligible(None, "2026-01-01T00:00:00+00:00", None) is True
```

- [ ] **Step 2:** 运行确认失败(ModuleNotFoundError)。
- [ ] **Step 3:** 创建 `src/apps/submit/nomination_service.py`:

```python
"""Nomination (dojin) pure validation helpers — no DB, no I/O."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse


def extract_domain(url: str) -> str | None:
    try:
        host = urlparse(url).hostname
    except Exception:
        return None
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def domain_allowed(url: str, allowlist: list[str]) -> bool:
    if not allowlist:
        return True
    dom = extract_domain(url)
    if dom is None:
        return False
    return any(dom == a or dom.endswith("." + a) for a in allowlist)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def within_window(now: datetime, start_iso: str | None, end_iso: str | None) -> bool:
    start = _parse_iso(start_iso)
    end = _parse_iso(end_iso)
    if start and now < start:
        return False
    if end and now > end:
        return False
    return True


def publish_date_eligible(
    publish_date: datetime | None, start_iso: str | None, end_iso: str | None
) -> bool:
    if publish_date is None:
        return True  # unknown → defer to manual review
    return within_window(publish_date, start_iso, end_iso)
```

- [ ] **Step 4:** 运行确认通过(4 tests)。
- [ ] **Step 5:** flake8 + commit `feat(security): nomination pure validation helpers + tests (B-037)`

---

## Task 4: DAO — dojin_nomination 读写 + 问卷存在性

**Files:** Modify `src/apps/submit/dao.py`

- [ ] **Step 1:** 读 `src/apps/submit/dao.py` 了解现有 SubmitDAO 模式(session 用法)。
- [ ] **Step 2:** 在 SubmitDAO 追加方法:

```python
    async def has_paper(self, vote_id: str) -> bool:
        from sqlalchemy import select, func as sqlfunc
        from src.db_model.raw_submit import RawPaperSubmit
        n = (await self.session.execute(
            select(sqlfunc.count()).select_from(RawPaperSubmit)
            .where(RawPaperSubmit.vote_id == vote_id)
        )).scalar_one()
        return n > 0

    async def nomination_exists(self, vote_id: str, udid: str) -> bool:
        from sqlalchemy import select
        from src.db_model.dojin_nomination import DojinNomination
        row = (await self.session.execute(
            select(DojinNomination).where(
                DojinNomination.vote_id == vote_id,
                DojinNomination.udid == udid,
            )
        )).scalar_one_or_none()
        return row is not None

    async def create_nomination(self, row: dict) -> int:
        from src.db_model.dojin_nomination import DojinNomination
        obj = DojinNomination(**row)
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj.id

    async def list_nominations(self, status: str | None, page: int, page_size: int):
        from sqlalchemy import select, desc, func as sqlfunc
        from src.db_model.dojin_nomination import DojinNomination
        q = select(DojinNomination)
        if status and status != "all":
            q = q.where(DojinNomination.status == status)
        total = (await self.session.execute(
            select(sqlfunc.count()).select_from(q.subquery())
        )).scalar_one()
        rows = (await self.session.execute(
            q.order_by(desc(DojinNomination.created_at))
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return rows, total

    async def set_nomination_status(
        self, nom_id: int, status: str, reviewed_by: str, reject_reason: str | None
    ) -> bool:
        from datetime import datetime, timezone
        from sqlalchemy import select
        from src.db_model.dojin_nomination import DojinNomination
        row = (await self.session.execute(
            select(DojinNomination).where(DojinNomination.id == nom_id)
        )).scalar_one_or_none()
        if row is None:
            return False
        row.status = status
        row.reviewed_by = reviewed_by
        row.reject_reason = reject_reason
        row.reviewed_at = datetime.now(timezone.utc)
        await self.session.commit()
        return True

    async def list_approved_nominations(self, page: int, page_size: int):
        """Approved nominations deduped by udid with nomination_count."""
        from sqlalchemy import select, func as sqlfunc
        from src.db_model.dojin_nomination import DojinNomination
        # group by udid; pick max(title/url) as representative, count distinct voters
        base = select(
            DojinNomination.udid,
            sqlfunc.min(DojinNomination.title).label("title"),
            sqlfunc.min(DojinNomination.url).label("url"),
            sqlfunc.min(DojinNomination.author).label("author"),
            sqlfunc.count(sqlfunc.distinct(DojinNomination.vote_id)).label("cnt"),
        ).where(DojinNomination.status == "approved").group_by(DojinNomination.udid)
        rows = (await self.session.execute(
            base.offset((page - 1) * page_size).limit(page_size)
        )).all()
        return rows
```

- [ ] **Step 3:** flake8 + commit `feat(security): SubmitDAO nomination + has_paper methods (B-037)`

---

## Task 5: submit_service — 提名编排 + 投票门禁(TDD)

**Files:** Modify `src/apps/submit/service.py`, `schemas.py`; Create `tests/integration/test_security_submit.py`

- [ ] **Step 1:** 在 `schemas.py` 加提名结果模型:

```python
class NominationItemResult(BaseModel):
    index: int
    reason: str

class NominationSubmitResult(BaseModel):
    accepted: int = 0
    rejected: list[NominationItemResult] = []
    skipped: list[NominationItemResult] = []
```

- [ ] **Step 2:** 写失败集成测试 `tests/integration/test_security_submit.py`(mock scraper + sqlite)。覆盖:
  - `submit_character` 在无 paper 时抛门禁错误;有 paper 时通过。
  - `submit_dojin_nominations`:全通过 / 含不允许域名(rejected)/ scraper 返回重复 udid(skipped)。

  (用 `tests/integration/conftest.py` 的 `session` fixture;mock 一个 scraper 对象,其 `scrape_url` 返回带 udid+ptime 的对象或抛错。)

  关键断言示例:
```python
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_character_gate_blocks_without_paper(session):
    from src.apps.submit.dao import SubmitDAO
    from src.apps.submit.service import SubmitService, QuestionnaireNotCompletedError
    from src.apps.submit.schemas import CharacterSubmitRest, SubmitMetadata, CharacterSubmit
    svc = SubmitService(SubmitDAO(session))
    data = CharacterSubmitRest(
        characters=[CharacterSubmit(id="c1")],
        meta=SubmitMetadata(vote_id="u1"),
    )
    with pytest.raises(QuestionnaireNotCompletedError):
        await svc.submit_character(data)


@pytest.mark.asyncio
async def test_character_gate_passes_with_paper(session):
    from src.apps.submit.dao import SubmitDAO
    from src.apps.submit.service import SubmitService
    from src.apps.submit.schemas import (
        CharacterSubmitRest, PaperSubmitRest, SubmitMetadata, CharacterSubmit,
    )
    dao = SubmitDAO(session)
    svc = SubmitService(dao)
    await svc.submit_paper(PaperSubmitRest(papers_json="{}", meta=SubmitMetadata(vote_id="u2")))
    data = CharacterSubmitRest(
        characters=[CharacterSubmit(id="c1")], meta=SubmitMetadata(vote_id="u2"),
    )
    assert await svc.submit_character(data) > 0
```

- [ ] **Step 3:** 在 `service.py` 实现:
  - 定义异常 `class QuestionnaireNotCompletedError(Exception): pass`。
  - 在 `submit_character/music/cp` 开头加 `await self._require_questionnaire(data.meta.vote_id)`:
```python
    async def _require_questionnaire(self, vote_id: str) -> None:
        if not await self.submit_dao.has_paper(vote_id):
            raise QuestionnaireNotCompletedError(vote_id)
```
  - 新增 `submit_dojin_nominations(data, settings, scraper)` 方法:逐条按 §五流程处理,调 `nomination_service` 的纯函数 + `scraper.scrape_url`(try/except + 超时由 scraper 内部或 asyncio.wait_for 包),写 `dao.create_nomination`,返回 `NominationSubmitResult`。保留写一份 raw_dojin(调现有 `submit_dojin`)。
  - 提名窗校验:`within_window(now, settings.nomination_start_iso, settings.nomination_end_iso)`,不在窗内抛 `NominationClosedError`;未配置(两者皆 None)抛 `NominationNotConfiguredError`。
- [ ] **Step 4:** 运行集成测试确认通过。
- [ ] **Step 5:** flake8 + commit `feat(security): questionnaire gate + dojin nomination orchestration (B-037)`

---

## Task 6: GraphQL/REST 提交端点接线

**Files:** Modify `src/api/graphql/resolvers/submit_bridge.py`(submitDojin 返回逐条结果 + 错误映射);提交角色/音乐/CP 的 resolver/router 把 `QuestionnaireNotCompletedError` 映射为 422/对应 GraphQL 错误。

- [ ] **Step 1:** 读现有 submit_bridge.py,了解错误映射与返回类型模式。
- [ ] **Step 2:** submitDojin resolver 改为调 `submit_dojin_nominations`,返回新 GraphQL 类型 `DojinSubmitResult { accepted, rejected[], skipped[] }`;注入 ScraperService + Settings 依赖。
- [ ] **Step 3:** 角色/音乐/CP 的 submit resolver 捕获 `QuestionnaireNotCompletedError` → GraphQL 错误 `QUESTIONNAIRE_NOT_COMPLETED`;捕获 `NominationClosedError`/`NominationNotConfiguredError` → 对应错误码。
- [ ] **Step 4:** 跑 `pytest tests/ -q` 确认无回归 + flake8 `src/`。commit `feat(security): wire nomination result + gate errors into graphql (B-037)`

---

## Task 7: 管理端审核端点(含 UI)

**Files:** Modify `src/apps/admin/{schemas,service,router}.py`, `src/admin_ui/index.html`; Create `tests/contract/test_nomination_endpoints.py`

- [ ] **Step 1:** schemas 加 `NominationItem`, `NominationListResponse`, `NominationRejectRequest`。
- [ ] **Step 2:** AdminService 加 `list_nominations`, `review_nomination(id, approve/reject, reason)` → 调 `SubmitDAO`(在 admin service 内构造 SubmitDAO(self._session))。
- [ ] **Step 3:** router 加(`X-Admin-Secret`):
  - `GET /admin/nominations?status=&page=&page_size=`
  - `PATCH /admin/nominations/{id}/approve`
  - `PATCH /admin/nominations/{id}/reject`(body reason)
  返回/404 同候选项模式。
- [ ] **Step 4:** `src/admin_ui/index.html` 加「提名审核」Tab:nav 加按钮 + `nominations()` 函数(筛选 status + 列表 + 行内 通过/驳回);复用白色主题 + modal(驳回填 reason)。
- [ ] **Step 5:** contract 测试 `tests/contract/test_nomination_endpoints.py`:无 secret→403;列表 shape;approve/reject 404。
- [ ] **Step 6:** `pytest tests/ -q` + flake8 `src/`。commit `feat(admin): nomination review endpoints + UI (B-037)`

---

## Task 8: 公开已通过提名查询

**Files:** Modify result 路由(或新建 `src/apps/submit/router.py` 的公开端点);Create contract 测试

- [ ] **Step 1:** 加 `GET /nominations/approved?page=&page_size=` → 调 `SubmitDAO.list_approved_nominations`,返回 `{items:[{udid,title,url,author,nomination_count}], page}`。无需 admin secret(公开),但建议加 vote_token 或保持公开按产品定;**本期公开只读**。
- [ ] **Step 2:** contract 测试:返回 200 + shape。
- [ ] **Step 3:** `pytest tests/ -q` + flake8。commit `feat(security): public approved-nominations query (B-037)`

---

## Task 9: 全量回归 + BACKLOG

- [ ] **Step 1:** `pytest tests/ -q --tb=short`(仅既有 pnvs 本地失败可接受)。
- [ ] **Step 2:** `flake8 src/ --max-line-length=88` 干净。
- [ ] **Step 3:** `docs/BACKLOG.md` 加 B-037 行(后端安全块,标完成 + commit)。
- [ ] **Step 4:** commit `docs: mark B-037 backend security done`;`git push`。

---

## Self-Review 注意
- scraper 同步调用要包 `asyncio.wait_for(..., timeout=5)`,失败降级 udid=None,绝不让提名提交因 scraper 挂掉而整体失败。
- 门禁只加在角色/音乐/CP,**不加在 paper/dojin**(否则没法先填问卷)。
- `dojin_domain_allowlist` 配置解析按 Task 1 的 property 方式,避免 pydantic list 解析坑。
