from datetime import datetime, timezone

from src.api.graphql.types import (
    LoginResult,
    VoterFEType,
    pydantic_to_graphql_login_result,
)
from src.apps.user.schemas import LoginResponse, VoterFE


def test_pydantic_to_graphql_login_result_maps_all_fields():
    created = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    resp = LoginResponse(
        user=VoterFE(
            username="alice", pfp="http://pfp", password=True,
            phone="13800000000", email="a@b.com", thbwiki=True,
            patchyvideo=False, created_at=created,
        ),
        session_token="sess-123",
        vote_token="vote-456",
    )
    out = pydantic_to_graphql_login_result(resp)
    assert isinstance(out, LoginResult)
    assert isinstance(out.user, VoterFEType)
    assert out.user.username == "alice"
    assert out.user.pfp == "http://pfp"
    assert out.user.password is True
    assert out.user.phone == "13800000000"
    assert out.user.email == "a@b.com"
    assert out.user.thbwiki is True
    assert out.user.patchyvideo is False
    assert out.user.created_at == created
    assert out.session_token == "sess-123"
    assert out.vote_token == "vote-456"
