"""R-04 / D-09: submitted ids must be candidates of the current vote year.

Before this fix an unknown id was stored anyway and then dropped by the tally,
so the user saw "vote submitted" while nothing counted.  The candidate check
lives in ``SubmitService`` and accepts exactly the same tokens as the tally
(canonical ``candidate_id`` or the legacy 8-hex ``old_id``).
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from src.apps.submit.dao import SubmitDAO
from src.apps.submit.schemas import (
    CPSubmit,
    CPSubmitRest,
    CharacterSubmit,
    CharacterSubmitRest,
    MusicSubmit,
    MusicSubmitRest,
    PaperSubmitRest,
    SubmitMetadata,
)
from src.apps.submit.service import InvalidCandidateError, SubmitService
from src.common.security.jwt import create_vote_token
from src.db_model.candidate import CandidateCharacter, CandidateMusic
from src.db_model.voteable import VoteableCharacter, VoteableMusic

VOTE_YEAR = 2026
CHAR_CANDIDATE = 22
CHAR_OLD_ID = "4068b1c2"
MUSIC_CANDIDATE = 165


@pytest.fixture(autouse=True)
def fixed_vote_year(monkeypatch):
    from src.common.config import get_settings

    monkeypatch.setattr(get_settings(), "vote_year", VOTE_YEAR)


async def seed_candidates(session, vote_year=VOTE_YEAR):
    """``candidate_*`` junction rows carry the id the frontend submits.

    ``vote-objects`` returns ``CandidateCharacter.id`` as ``candidateId`` and the
    tally whitelist keys on it too, so the seeded candidate id is 22 while the
    voteable row keeps its own id.
    """
    session.add(VoteableCharacter(id=1, name="博丽灵梦", old_id=CHAR_OLD_ID))
    session.add(CandidateCharacter(
        id=CHAR_CANDIDATE, vote_year=vote_year, voteable_id=1, sort_order=1,
    ))
    session.add(VoteableMusic(id=1, name="曲目"))
    session.add(CandidateMusic(
        id=MUSIC_CANDIDATE, vote_year=vote_year, voteable_id=1, sort_order=1,
    ))
    await session.commit()


async def unlock_gate(svc: SubmitService, vote_id: str) -> None:
    """Legacy paper with real content satisfies the gate (R-03)."""
    await svc.submit_paper(PaperSubmitRest(
        papers_json='{"q1": "a"}', meta=SubmitMetadata(vote_id=vote_id),
    ))


def _chars(vote_id: str, ids) -> CharacterSubmitRest:
    return CharacterSubmitRest(
        characters=[CharacterSubmit(id=i) for i in ids],
        meta=SubmitMetadata(vote_id=vote_id),
    )


@pytest.mark.asyncio
async def test_known_character_id_accepted(session):
    await seed_candidates(session)
    svc = SubmitService(SubmitDAO(session))
    await unlock_gate(svc, "u-ok")
    assert await svc.submit_character(_chars("u-ok", [str(CHAR_CANDIDATE)])) > 0


@pytest.mark.asyncio
async def test_legacy_old_id_accepted(session):
    """The tally still resolves legacy 8-hex ids; submit must not reject them."""
    await seed_candidates(session)
    svc = SubmitService(SubmitDAO(session))
    await unlock_gate(svc, "u-old")
    assert await svc.submit_character(_chars("u-old", [CHAR_OLD_ID])) > 0


@pytest.mark.asyncio
async def test_unknown_character_id_rejected_and_not_stored(session):
    await seed_candidates(session)
    svc = SubmitService(SubmitDAO(session))
    await unlock_gate(svc, "u-bad")
    with pytest.raises(InvalidCandidateError) as ei:
        await svc.submit_character(_chars("u-bad", ["999999"]))
    assert "999999" in str(ei.value)
    # nothing was written: the ballot never reaches the tally's dropped counter
    assert (await svc.get_character_submit("u-bad")).characters == []


@pytest.mark.asyncio
async def test_unknown_music_id_rejected(session):
    await seed_candidates(session)
    svc = SubmitService(SubmitDAO(session))
    await unlock_gate(svc, "u-music")
    with pytest.raises(InvalidCandidateError):
        await svc.submit_music(MusicSubmitRest(
            music=[MusicSubmit(id="999999")], meta=SubmitMetadata(vote_id="u-music"),
        ))


@pytest.mark.asyncio
async def test_cp_member_must_be_character_candidate(session):
    await seed_candidates(session)
    svc = SubmitService(SubmitDAO(session))
    await unlock_gate(svc, "u-cp")
    with pytest.raises(InvalidCandidateError):
        await svc.submit_cp(CPSubmitRest(
            cps=[CPSubmit(id_a=str(CHAR_CANDIDATE), id_b="999999")],
            meta=SubmitMetadata(vote_id="u-cp"),
        ))
    assert (await svc.get_cp_submit("u-cp")).cps == []


@pytest.mark.asyncio
async def test_cp_with_known_members_accepted(session):
    await seed_candidates(session)
    svc = SubmitService(SubmitDAO(session))
    await unlock_gate(svc, "u-cp-ok")
    assert await svc.submit_cp(CPSubmitRest(
        cps=[CPSubmit(id_a=str(CHAR_CANDIDATE), id_b=CHAR_OLD_ID)],
        meta=SubmitMetadata(vote_id="u-cp-ok"),
    )) > 0


@pytest.mark.asyncio
async def test_year_without_candidates_skips_check(session):
    """No candidates imported for the year → nothing to check against.

    Fail-open is deliberate: such a deployment cannot tally anything, and
    blocking every submission would be a worse failure mode.
    """
    svc = SubmitService(SubmitDAO(session))
    await unlock_gate(svc, "u-nocand")
    assert await svc.submit_character(_chars("u-nocand", ["999999"])) > 0


@pytest.mark.asyncio
async def test_other_year_candidates_do_not_validate(session):
    """A candidate of last year is not a candidate of this year."""
    await seed_candidates(session, vote_year=VOTE_YEAR - 1)
    svc = SubmitService(SubmitDAO(session))
    await unlock_gate(svc, "u-lastyear")
    assert await svc.submit_character(_chars("u-lastyear", ["999999"])) > 0


# ── GraphQL error mapping ────────────────────────────────────────────────

SUBMIT_CHARACTER = """
mutation($voteToken: String!, $characters: [CharacterSubmitInput!]!) {
  submitCharacterVote(content: {voteToken: $voteToken, characters: $characters})
}
"""


def _vote_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    return create_vote_token(user_id, now - timedelta(hours=1), now + timedelta(days=1))


@pytest_asyncio.fixture
async def gql(monkeypatch, session, patch_redis):
    import src.api.graphql.resolvers.submit_bridge as bridge

    async def _fake_db():
        yield session

    async def _fake_redis():
        return patch_redis

    monkeypatch.setattr(bridge, "get_db_session", _fake_db)
    monkeypatch.setattr(bridge, "get_redis_client", _fake_redis)

    from src.api.graphql.schema import schema

    return schema


@pytest.mark.asyncio
async def test_graphql_unknown_candidate_error_kind(gql, session):
    await seed_candidates(session)
    svc = SubmitService(SubmitDAO(session))
    await unlock_gate(svc, "gql-bad")
    result = await gql.execute(
        SUBMIT_CHARACTER,
        variable_values={
            "voteToken": _vote_token("gql-bad"),
            "characters": [{"id": "999999"}],
        },
        context_value={"request": None},
    )
    assert result.errors, "unknown candidate must not be accepted"
    ext = result.errors[0].extensions
    assert ext["error_kind"] == "INVALID_CANDIDATE"
    assert ext["human_readable_message"]
