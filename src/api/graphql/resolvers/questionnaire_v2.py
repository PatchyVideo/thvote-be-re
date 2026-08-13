"""GraphQL bridge for structured questionnaire (v2) submit + read-back.

voteToken → user_id(vote_id);answer state 用 JSON 标量承载
QuestionnaireAnswerStateV2(结构复杂且逐年变,标量最省事,与 result 查询同风格)。
"""
from __future__ import annotations

import uuid

import strawberry

from src.api.graphql.errors import map_app_errors
from src.api.graphql.types import JSON
from src.apps.questionnaire.dao import QuestionnaireDAO
from src.apps.questionnaire.service import QuestionnaireService
from src.common.config import get_settings
from src.common.database import get_db_session
from src.common.exceptions import UnauthorizedError
from src.common.middleware.rate_limit import get_redis_client, rate_limit
from src.common.security import JWTValidationError, decode_vote_token

_SERVICE = "submit-handler"


def _vote_user_id(vote_token: str) -> str:
    if not vote_token:
        raise UnauthorizedError("INVALID_TOKEN", details=401)
    try:
        return decode_vote_token(vote_token).user_id
    except JWTValidationError as exc:
        raise UnauthorizedError("INVALID_TOKEN", details=401) from exc


@strawberry.type
class PaperV2Mutation:
    @strawberry.mutation
    async def submit_paper_v2(
        self, info: strawberry.Info, vote_token: str, answers: JSON
    ) -> bool:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(vote_token)
            await rate_limit(user_id, await get_redis_client())
            redis_client = await get_redis_client()
            lock_key = f"lock-submit-{user_id}"
            lock_value = str(uuid.uuid4())
            acquired = await redis_client.set(lock_key, lock_value, nx=True, px=10_000)
            if not acquired:
                from src.common.exceptions import RateLimitError
                raise RateLimitError("SUBMIT_LOCKED", details=429)
            try:
                year = get_settings().vote_year
                async for db in get_db_session():
                    svc = QuestionnaireService(QuestionnaireDAO(db))
                    await svc.submit_answers(user_id, year, answers)
                    return True
            finally:
                current = await redis_client.get(lock_key)
                if current == lock_value:
                    await redis_client.delete(lock_key)
        raise RuntimeError("unreachable")  # pragma: no cover


@strawberry.type
class PaperV2Query:
    @strawberry.field
    async def get_paper_v2(
        self, info: strawberry.Info, vote_token: str
    ) -> JSON:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(vote_token)
            year = get_settings().vote_year
            async for db in get_db_session():
                svc = QuestionnaireService(QuestionnaireDAO(db))
                return await svc.get_answers(user_id, year)
        raise RuntimeError("unreachable")  # pragma: no cover
