"""Integration tests for Block 1 security: vote gate + nomination orchestration."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.apps.submit.schemas import (
    CharacterSubmit,
    CharacterSubmitRest,
    DojinSubmit,
    DojinSubmitRest,
    PaperSubmitRest,
    SubmitMetadata,
)


def _scraper_returning(udid, ptime):
    """A stub scraper whose scrape_url returns a RespBody-like object."""

    class _Stub:
        async def scrape_url(self, url):
            data = SimpleNamespace(udid=udid, ptime=ptime)
            return SimpleNamespace(status="ok", data=data)

    return _Stub()


def _scraper_failing():
    class _Stub:
        async def scrape_url(self, url):
            raise RuntimeError("scrape failed")

    return _Stub()


# ── vote gate ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_character_gate_blocks_without_paper(session):
    from src.apps.submit.dao import SubmitDAO
    from src.apps.submit.service import (
        QuestionnaireNotCompletedError,
        SubmitService,
    )

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

    dao = SubmitDAO(session)
    svc = SubmitService(dao)
    await svc.submit_paper(
        PaperSubmitRest(papers_json="{}", meta=SubmitMetadata(vote_id="u2"))
    )
    data = CharacterSubmitRest(
        characters=[CharacterSubmit(id="c1")],
        meta=SubmitMetadata(vote_id="u2"),
    )
    assert await svc.submit_character(data) > 0


# ── nomination orchestration ───────────────────────────────────────────────

def _settings(allowlist_raw=None):
    return SimpleNamespace(
        nomination_start_iso="2026-01-01T00:00:00+00:00",
        nomination_end_iso="2026-12-31T23:59:59+00:00",
        work_eligible_start_iso=None,
        work_eligible_end_iso=None,
        dojin_domain_allowlist=(
            [d.strip() for d in allowlist_raw.split(",")] if allowlist_raw else []
        ),
    )


def _dojin(url, title="t"):
    return DojinSubmit(
        dojin_type="VIDEO", url=url, title=title, author="a", reason="r"
    )


@pytest.mark.asyncio
async def test_nomination_all_accepted(session):
    from src.apps.submit.dao import SubmitDAO
    from src.apps.submit.service import SubmitService

    svc = SubmitService(SubmitDAO(session))
    data = DojinSubmitRest(
        dojins=[_dojin("https://bilibili.com/v/1")],
        meta=SubmitMetadata(vote_id="n1"),
    )
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    result = await svc.submit_dojin_nominations(
        data, _settings(), _scraper_returning("udid-1", "2026-03-01"), now=now
    )
    assert result.accepted == 1
    assert result.rejected == []


@pytest.mark.asyncio
async def test_nomination_domain_rejected(session):
    from src.apps.submit.dao import SubmitDAO
    from src.apps.submit.service import SubmitService

    svc = SubmitService(SubmitDAO(session))
    data = DojinSubmitRest(
        dojins=[_dojin("https://evil.com/v/1")],
        meta=SubmitMetadata(vote_id="n2"),
    )
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    result = await svc.submit_dojin_nominations(
        data, _settings("bilibili.com"),
        _scraper_returning("udid-2", "2026-03-01"), now=now,
    )
    assert result.accepted == 0
    assert len(result.rejected) == 1
    assert "域名" in result.rejected[0].reason


@pytest.mark.asyncio
async def test_nomination_duplicate_skipped(session):
    from src.apps.submit.dao import SubmitDAO
    from src.apps.submit.service import SubmitService

    svc = SubmitService(SubmitDAO(session))
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    data = DojinSubmitRest(
        dojins=[
            _dojin("https://bilibili.com/v/1", "first"),
            _dojin("https://bilibili.com/v/1", "dup"),
        ],
        meta=SubmitMetadata(vote_id="n3"),
    )
    result = await svc.submit_dojin_nominations(
        data, _settings(), _scraper_returning("same-udid", "2026-03-01"), now=now
    )
    assert result.accepted == 1
    assert len(result.skipped) == 1


@pytest.mark.asyncio
async def test_nomination_scraper_failure_still_pending(session):
    from src.apps.submit.dao import SubmitDAO
    from src.apps.submit.service import SubmitService

    svc = SubmitService(SubmitDAO(session))
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    data = DojinSubmitRest(
        dojins=[_dojin("https://bilibili.com/v/1")],
        meta=SubmitMetadata(vote_id="n4"),
    )
    result = await svc.submit_dojin_nominations(
        data, _settings(), _scraper_failing(), now=now
    )
    # scraper failed → udid None → still accepted (pending manual review)
    assert result.accepted == 1


@pytest.mark.asyncio
async def test_nomination_closed_window(session):
    from src.apps.submit.dao import SubmitDAO
    from src.apps.submit.service import NominationClosedError, SubmitService

    svc = SubmitService(SubmitDAO(session))
    data = DojinSubmitRest(
        dojins=[_dojin("https://bilibili.com/v/1")],
        meta=SubmitMetadata(vote_id="n5"),
    )
    after = datetime(2027, 6, 1, tzinfo=timezone.utc)
    with pytest.raises(NominationClosedError):
        await svc.submit_dojin_nominations(
            data, _settings(), _scraper_returning("u", "2026-01-01"), now=after
        )


@pytest.mark.asyncio
async def test_nomination_not_configured(session):
    from src.apps.submit.dao import SubmitDAO
    from src.apps.submit.service import (
        NominationNotConfiguredError,
        SubmitService,
    )

    svc = SubmitService(SubmitDAO(session))
    data = DojinSubmitRest(
        dojins=[_dojin("https://bilibili.com/v/1")],
        meta=SubmitMetadata(vote_id="n6"),
    )
    s = SimpleNamespace(
        nomination_start_iso=None, nomination_end_iso=None,
        work_eligible_start_iso=None, work_eligible_end_iso=None,
        dojin_domain_allowlist=[],
    )
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    with pytest.raises(NominationNotConfiguredError):
        await svc.submit_dojin_nominations(
            data, s, _scraper_returning("u", "2026-01-01"), now=now
        )
