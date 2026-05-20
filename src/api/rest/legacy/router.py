"""Legacy flat REST routes mirroring the old Rust gateway contract.

See ``src/api/rest/legacy/__init__.py`` for why this layer exists and when to
remove it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.apps.submit.router import get_submit_service
from src.apps.submit.schemas import VotingStatus
from src.apps.submit.service import SubmitService
from src.common.security import (
    JWTValidationError,
    decode_session_token,
    decode_vote_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["legacy-compat"])


class TokenStatusInputs(BaseModel):
    """Request body for the legacy ``/user-token-status`` endpoint.

    ``vote_token`` may be an empty string (the frontend sends whatever it has in
    localStorage); treated the same as absent.
    """

    user_token: str
    vote_token: str | None = None


class TokenStatusOutput(BaseModel):
    """Response shape of the old Rust ``user_token_status`` handler.

    ``status`` is the string ``"valid"`` / ``"invalid"`` the frontend checks —
    it logs the user out on anything other than ``"valid"``.  HTTP is always
    200: invalidity is carried in the body, not the status code.
    """

    status: str
    voting_status: VotingStatus | None = None
    papers_json: str | None = None


@router.post("/user-token-status", response_model=TokenStatusOutput)
async def user_token_status(
    body: TokenStatusInputs,
    service: SubmitService = Depends(get_submit_service),
) -> TokenStatusOutput:
    """Validate the session token; if valid, attach voting status + papers.

    Mirrors ``thvote-be/gateway/src/main.rs::user_token_status``:
      - invalid / expired ``user_token`` -> ``{"status": "invalid"}`` (HTTP 200)
      - valid -> ``{"status": "valid", ...}``; when a usable ``vote_token`` is
        supplied, include per-category ``voting_status`` and, if the paper vote
        is done, the stored ``papers_json``.

    A misconfigured JWT key raises ``JWTConfigurationError`` (a server fault) and
    is deliberately NOT swallowed here — it must surface as 500, not masquerade
    as an invalid token that silently logs everyone out.
    """
    try:
        decode_session_token(body.user_token)
    except JWTValidationError:
        return TokenStatusOutput(status="invalid")

    out = TokenStatusOutput(status="valid")

    if not body.vote_token:
        return out
    try:
        vote = decode_vote_token(body.vote_token)
    except JWTValidationError:
        # Logged in, but no usable vote token (e.g. outside the vote window).
        # Still "valid" — there is simply nothing to pre-fill.
        return out

    voting_status = await service.get_voting_status(vote.user_id)
    out.voting_status = voting_status
    if voting_status.papers:
        paper = await service.get_paper_submit(vote.user_id)
        out.papers_json = paper.papers_json
    return out
