from datetime import datetime, timezone

from src.api.graphql.types import LoginResult, VoterFEType, login_result_from_pydantic
from src.apps.user.schemas import LoginResponse, VoterFE


def test_login_result_from_pydantic_maps_all_fields():
    created = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    resp = LoginResponse(
        user=VoterFE(
            username="alice", pfp=None, password=True,
            phone=None, email="a@b.com", thbwiki=False,
            patchyvideo=False, created_at=created,
        ),
        session_token="sess-123",
        vote_token="vote-456",
    )
    out = login_result_from_pydantic(resp)
    assert isinstance(out, LoginResult)
    assert isinstance(out.user, VoterFEType)
    assert out.user.username == "alice"
    assert out.user.email == "a@b.com"
    assert out.user.password is True
    assert out.user.created_at == created
    assert out.session_token == "sess-123"
    assert out.vote_token == "vote-456"
