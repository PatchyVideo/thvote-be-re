"""GraphQL submit 桥 — 前端(旧 Rust gateway)契约的投票提交/回读。

业务逻辑全在 SubmitService;本模块只做:
  voteToken → user_id(即 vote_id)→ 服务端造 meta → service。
契约与决策见 docs/superpowers/specs/2026-06-07-graphql-submit-bridge-design.md。
旧自创字段(resolvers/submit.py)按用户决策原样保留,与本模块并存。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncIterator, Optional

import strawberry

from src.api.graphql.errors import _client_ip_from_info, map_app_errors

# Tasks 5-6(其余 mutation 与回读 query)会扩展这里的 import:
# 其余 *SubmitRest / *SubmitPydantic 与 pydantic_to_graphql_* 转换器。
from src.api.graphql.types import (
    CharacterSubmit,
    CharacterSubmitInput,
    CPSubmit,
    CPSubmitInput,
    DojinSubmit,
    MusicSubmit,
    MusicSubmitInput,
)
from src.apps.submit.dao import SubmitDAO
from src.apps.submit.schemas import CharacterSubmit as CharacterSubmitPydantic
from src.apps.submit.schemas import CPSubmit as CPSubmitPydantic
from src.apps.submit.schemas import DojinSubmit as DojinSubmitPydantic
from src.apps.submit.schemas import MusicSubmit as MusicSubmitPydantic
from src.apps.submit.schemas import (
    CharacterSubmitRest,
    CPSubmitRest,
    DojinSubmitRest,
    MusicSubmitRest,
    PaperSubmitRest,
    SubmitMetadata,
)
from src.apps.submit.service import SubmitService
from src.common.database import get_db_session
from src.common.exceptions import RateLimitError, UnauthorizedError, ValidationError
from src.common.middleware.rate_limit import get_redis_client, rate_limit
from src.common.security import JWTValidationError, decode_vote_token

_SERVICE = "submit-handler"  # extensions.service,对齐旧 Rust 服务名


# ── GraphQL 类型(名字以前端 gql 文档为准,大小写精确) ────────────────


@strawberry.enum
class DojinType(Enum):
    MUSIC = "MUSIC"
    VIDEO = "VIDEO"
    DRAWING = "DRAWING"
    SOFTWARE = "SOFTWARE"
    ARTICLE = "ARTICLE"
    CRAFT = "CRAFT"
    OTHER = "OTHER"


@strawberry.input(name="DojinSubmitItemGQL")
class DojinSubmitItemGQL:
    title: str
    author: str
    url: str
    dojin_type: DojinType
    reason: str
    image_url: Optional[str] = None


@strawberry.input(name="CharacterSubmitGQL")
class CharacterSubmitGQL:
    vote_token: str
    characters: list[CharacterSubmitInput]


@strawberry.input(name="MusicSubmitGQL")
class MusicSubmitGQL:
    vote_token: str
    musics: list[MusicSubmitInput]  # 提交字段是复数;回读结果字段是单数 music(旧契约怪癖)


@strawberry.input(name="CPSubmitGQL")
class CPSubmitGQL:
    vote_token: str
    cps: list[CPSubmitInput]


@strawberry.input(name="PaperSubmitGQL")
class PaperSubmitGQL:
    vote_token: str
    paper_json: str


@strawberry.input(name="DojinSubmitGQL")
class DojinSubmitGQL:
    vote_token: str
    dojins: list[DojinSubmitItemGQL]


@strawberry.type
class CharacterSubmitRestQuery:
    characters: list[CharacterSubmit]


@strawberry.type
class MusicSubmitRestQuery:
    music: list[MusicSubmit]


@strawberry.type
class CPSubmitRestQuery:
    cps: list[CPSubmit]


@strawberry.type
class DojinSubmitRestQuery:
    dojins: list[DojinSubmit]


@strawberry.type
class PaperSubmitRestQuery:
    papers_json: str


# ── 共享 helpers ──────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _vote_user_id(vote_token: str) -> str:
    """voteToken → user_id(即 vote_id)。缺失/伪造/过期(含窗口外)统一 INVALID_TOKEN。"""
    if not vote_token:
        raise UnauthorizedError("INVALID_TOKEN", details=401)
    try:
        return decode_vote_token(vote_token).user_id
    except JWTValidationError as exc:
        raise UnauthorizedError("INVALID_TOKEN", details=401) from exc


def _server_meta(user_id: str, info: "strawberry.Info") -> SubmitMetadata:
    """meta 由服务端生成:vote_id 取自 token,时间与 IP 不信任客户端。"""
    return SubmitMetadata(
        vote_id=user_id,
        created_at=_utcnow(),
        user_ip=_client_ip_from_info(info) or "<unknown>",
    )


@asynccontextmanager
async def _submit_lock(user_id: str) -> AsyncIterator[None]:
    """同一用户的并发提交互斥。冲突抛 AppException(SUBMIT_LOCKED),
    走 map_app_errors 出正确 extensions(旧 resolver 抛裸 Exception 会被全局
    格式化器脱敏,这里刻意不复用)。"""
    redis_client = await get_redis_client()
    lock_key = f"lock-submit-{user_id}"
    lock_value = str(uuid.uuid4())
    acquired = await redis_client.set(lock_key, lock_value, nx=True, px=10_000)
    if not acquired:
        raise RateLimitError("SUBMIT_LOCKED", details=429)
    try:
        yield
    finally:
        current = await redis_client.get(lock_key)
        if current == lock_value:
            await redis_client.delete(lock_key)


async def _run_submit(body, service_method_name: str) -> bool:
    """统一的 service 调用:ValueError → INVALID_CONTENT(中文原文透传)。"""
    async for db in get_db_session():
        service = SubmitService(SubmitDAO(db))
        try:
            await getattr(service, service_method_name)(body)
        except ValueError as exc:
            raise ValidationError(
                "INVALID_CONTENT", details=422, human_readable_message=str(exc)
            ) from exc
        return True
    raise RuntimeError("unreachable")  # pragma: no cover


# ── Mutations ─────────────────────────────────────────────────────────


@strawberry.type
class SubmitBridgeMutation:
    @strawberry.mutation
    async def submit_character_vote(
        self, info: strawberry.Info, content: CharacterSubmitGQL
    ) -> bool:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(content.vote_token)
            await rate_limit(user_id, await get_redis_client())
            async with _submit_lock(user_id):
                body = CharacterSubmitRest(
                    characters=[
                        CharacterSubmitPydantic(id=c.id, reason=c.reason, first=c.first)
                        for c in content.characters
                    ],
                    meta=_server_meta(user_id, info),
                )
                return await _run_submit(body, "submit_character")
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation
    async def submit_music_vote(
        self, info: strawberry.Info, content: MusicSubmitGQL
    ) -> bool:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(content.vote_token)
            await rate_limit(user_id, await get_redis_client())
            async with _submit_lock(user_id):
                body = MusicSubmitRest(
                    music=[  # REST 模型字段是单数 music(入参是复数 musics)
                        MusicSubmitPydantic(id=m.id, reason=m.reason, first=m.first)
                        for m in content.musics
                    ],
                    meta=_server_meta(user_id, info),
                )
                return await _run_submit(body, "submit_music")
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation(name="submitCPVote")
    async def submit_cp_vote(
        self, info: strawberry.Info, content: CPSubmitGQL
    ) -> bool:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(content.vote_token)
            await rate_limit(user_id, await get_redis_client())
            async with _submit_lock(user_id):
                body = CPSubmitRest(
                    cps=[
                        CPSubmitPydantic(
                            id_a=c.id_a, id_b=c.id_b, id_c=c.id_c,
                            active=c.active, first=c.first, reason=c.reason,
                        )
                        for c in content.cps
                    ],
                    meta=_server_meta(user_id, info),
                )
                return await _run_submit(body, "submit_cp")
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation
    async def submit_paper_vote(
        self, info: strawberry.Info, content: PaperSubmitGQL
    ) -> bool:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(content.vote_token)
            await rate_limit(user_id, await get_redis_client())
            async with _submit_lock(user_id):
                body = PaperSubmitRest(
                    papers_json=content.paper_json,
                    meta=_server_meta(user_id, info),
                )
                return await _run_submit(body, "submit_paper")
        raise RuntimeError("unreachable")  # pragma: no cover

    @strawberry.mutation
    async def submit_dojin(
        self, info: strawberry.Info, content: DojinSubmitGQL
    ) -> bool:
        async with map_app_errors(service=_SERVICE):
            user_id = _vote_user_id(content.vote_token)
            await rate_limit(user_id, await get_redis_client())
            async with _submit_lock(user_id):
                body = DojinSubmitRest(
                    dojins=[
                        DojinSubmitPydantic(
                            dojin_type=d.dojin_type.value,  # 入库存枚举名("MUSIC")
                            url=d.url, title=d.title, author=d.author,
                            reason=d.reason, image_url=d.image_url,
                        )
                        for d in content.dojins
                    ],
                    meta=_server_meta(user_id, info),
                )
                return await _run_submit(body, "submit_dojin")
        raise RuntimeError("unreachable")  # pragma: no cover
