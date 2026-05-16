"""User HTTP routes.

Mirrors thvote-be (Rust user-manager) endpoints under ``/api/v1/user/``.
Each endpoint is intentionally thin: parse the request, optionally
enforce a rate limit, delegate to ``UserService``, translate the
service-layer ``AppException`` into an ``HTTPException`` with a stable
error string body.

Auth model:
- Mutation endpoints carry ``user_token`` in the request body
  (Rust-aligned).
- ``GET /me`` carries the session token in ``Authorization: Bearer …``
  (only non-Rust endpoint; only place we use the header form).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.user.deps import (
    get_client_ip,
    get_current_user,
    get_user_service,
)
from src.apps.user.schemas import (
    EmptyResponse,
    LoginEmailPasswordRequest,
    LoginEmailRequest,
    LoginPhoneRequest,
    LoginResponse,
    RemoveVoterRequest,
    SendEmailCodeRequest,
    SendSmsCodeRequest,
    SsoBindRequest,
    SsoCallbackResponse,
    TokenStatusRequest,
    UpdateEmailRequest,
    UpdateNicknameRequest,
    UpdatePasswordRequest,
    UpdatePhoneRequest,
    VoterFE,
    voter_fe_from_user,
)
from src.apps.user.service import UserService
from src.common.config import get_settings
from src.common.database import get_db_session
from src.common.exceptions import AppException
from src.common.middleware.rate_limit import rate_limit
from src.common.redis import get_redis
from src.common.security import decode_session_token
from src.db_model.user import User

router = APIRouter(prefix="/user", tags=["user"])


# ── error mapping ────────────────────────────────────────────────────


def _raise_http(exc: AppException) -> None:
    """Translate an AppException into an HTTPException for FastAPI."""
    status = int(exc.details) if isinstance(exc.details, int) else 400
    raise HTTPException(status_code=status, detail=exc.message)


# ── helpers ──────────────────────────────────────────────────────────


def _override_meta_ip(request_obj, client_ip: str) -> None:
    """Trust the connecting peer over any user-supplied user_ip in Meta."""
    if hasattr(request_obj, "meta") and client_ip:
        request_obj.meta.user_ip = client_ip


# ── verification-code endpoints ──────────────────────────────────────


@router.post("/send-email-code", response_model=EmptyResponse)
async def send_email_code(
    body: SendEmailCodeRequest,
    client_ip: str = Depends(get_client_ip),
    service: UserService = Depends(get_user_service),
) -> EmptyResponse:
    _override_meta_ip(body, client_ip)
    try:
        await service.send_email_code(body)
    except AppException as exc:
        _raise_http(exc)
    return EmptyResponse()


@router.post("/send-sms-code", response_model=EmptyResponse)
async def send_sms_code(
    body: SendSmsCodeRequest,
    client_ip: str = Depends(get_client_ip),
    service: UserService = Depends(get_user_service),
) -> EmptyResponse:
    _override_meta_ip(body, client_ip)
    try:
        await service.send_sms_code(body)
    except AppException as exc:
        _raise_http(exc)
    return EmptyResponse()


# ── login endpoints (5 req/60s per IP) ───────────────────────────────


@router.post("/login-email-password", response_model=LoginResponse)
async def login_email_password(
    body: LoginEmailPasswordRequest,
    client_ip: str = Depends(get_client_ip),
    service: UserService = Depends(get_user_service),
) -> LoginResponse:
    await rate_limit(f"login-{client_ip or 'unknown'}", window=60, max_requests=5)
    _override_meta_ip(body, client_ip)
    try:
        return await service.login_with_email_password(body)
    except AppException as exc:
        _raise_http(exc)
        raise  # unreachable


@router.post("/login-email", response_model=LoginResponse)
async def login_email(
    body: LoginEmailRequest,
    client_ip: str = Depends(get_client_ip),
    service: UserService = Depends(get_user_service),
) -> LoginResponse:
    await rate_limit(f"login-{client_ip or 'unknown'}", window=60, max_requests=5)
    _override_meta_ip(body, client_ip)
    try:
        return await service.login_with_email_code(body)
    except AppException as exc:
        _raise_http(exc)
        raise


@router.post("/login-phone", response_model=LoginResponse)
async def login_phone(
    body: LoginPhoneRequest,
    client_ip: str = Depends(get_client_ip),
    service: UserService = Depends(get_user_service),
) -> LoginResponse:
    await rate_limit(f"login-{client_ip or 'unknown'}", window=60, max_requests=5)
    _override_meta_ip(body, client_ip)
    try:
        return await service.login_with_phone_code(body)
    except AppException as exc:
        _raise_http(exc)
        raise


# ── update endpoints (5 req/60s per user_id) ─────────────────────────


def _user_id_from_body_token(token: str) -> str:
    try:
        return decode_session_token(token).user_id
    except AppException as exc:
        raise HTTPException(status_code=401, detail="INVALID_TOKEN") from exc


async def _rate_limit_by_token(token: str, client_ip: str) -> None:
    """Enforce a coarse per-IP limit *before* token decode, then a tight
    per-user limit *after* decode.

    Skipping the pre-decode IP limit lets an attacker spam the endpoint
    with garbage tokens — each request takes the fast 401 path
    (no DB / no Redis user-bucket touch) and would otherwise bypass
    rate limiting entirely.  30 req/60s per IP is loose enough to never
    hit a real user but tight enough to make brute-forcing tokens cost
    something.
    """
    await rate_limit(
        f"user-mut-ip-{client_ip or 'unknown'}", window=60, max_requests=30
    )
    user_id = _user_id_from_body_token(token)
    await rate_limit(f"user-mut-{user_id}", window=60, max_requests=5)


@router.post("/update-email", response_model=EmptyResponse)
async def update_email(
    body: UpdateEmailRequest,
    client_ip: str = Depends(get_client_ip),
    service: UserService = Depends(get_user_service),
) -> EmptyResponse:
    await _rate_limit_by_token(body.user_token, client_ip)
    _override_meta_ip(body, client_ip)
    try:
        await service.update_email(body)
    except AppException as exc:
        _raise_http(exc)
    return EmptyResponse()


@router.post("/update-phone", response_model=EmptyResponse)
async def update_phone(
    body: UpdatePhoneRequest,
    client_ip: str = Depends(get_client_ip),
    service: UserService = Depends(get_user_service),
) -> EmptyResponse:
    await _rate_limit_by_token(body.user_token, client_ip)
    _override_meta_ip(body, client_ip)
    try:
        await service.update_phone(body)
    except AppException as exc:
        _raise_http(exc)
    return EmptyResponse()


@router.post("/update-nickname", response_model=EmptyResponse)
async def update_nickname(
    body: UpdateNicknameRequest,
    client_ip: str = Depends(get_client_ip),
    service: UserService = Depends(get_user_service),
) -> EmptyResponse:
    await _rate_limit_by_token(body.user_token, client_ip)
    _override_meta_ip(body, client_ip)
    try:
        await service.update_nickname(body)
    except AppException as exc:
        _raise_http(exc)
    return EmptyResponse()


@router.post("/update-password", response_model=EmptyResponse)
async def update_password(
    body: UpdatePasswordRequest,
    client_ip: str = Depends(get_client_ip),
    service: UserService = Depends(get_user_service),
) -> EmptyResponse:
    # Tighter limit: 5 req/300s per user_id (vs 5 req/60s for other mutations)
    # Prevents ~7200 brute-force attempts/day against weak passwords (B-012)
    await rate_limit(
        f"user-mut-ip-{client_ip or 'unknown'}", window=60, max_requests=30
    )
    user_id = _user_id_from_body_token(body.user_token)
    await rate_limit(f"update-password-{user_id}", window=300, max_requests=5)
    _override_meta_ip(body, client_ip)
    try:
        await service.update_password(body)
    except AppException as exc:
        _raise_http(exc)
    return EmptyResponse()


@router.post("/remove-voter", response_model=EmptyResponse)
async def remove_voter(
    body: RemoveVoterRequest,
    client_ip: str = Depends(get_client_ip),
    service: UserService = Depends(get_user_service),
) -> EmptyResponse:
    await _rate_limit_by_token(body.user_token, client_ip)
    _override_meta_ip(body, client_ip)
    try:
        await service.remove_voter(body)
    except AppException as exc:
        _raise_http(exc)
    return EmptyResponse()


# ── token + identity ─────────────────────────────────────────────────


@router.post("/token-status", response_model=EmptyResponse)
async def token_status(
    body: TokenStatusRequest,
    service: UserService = Depends(get_user_service),
) -> EmptyResponse:
    try:
        await service.token_status(body)
    except AppException as exc:
        _raise_http(exc)
    return EmptyResponse()


@router.get("/me", response_model=VoterFE)
async def get_me(current_user: User = Depends(get_current_user)) -> VoterFE:
    """Return the authenticated user's VoterFE.  No tokens, no rate limit."""
    return voter_fe_from_user(current_user)


# ── SSO: QQ Connect ──────────────────────────────────────────────────


@router.get("/sso/qq/authorize", tags=["sso"])
async def qq_authorize() -> RedirectResponse:
    settings = get_settings()
    if not settings.qq_app_id or not settings.sso_callback_base_url:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SSO_NOT_CONFIGURED",
                "message": "QQ SSO is not configured",
            },
        )
    from .sso_clients import qq_authorize_url

    redirect_uri = (
        f"{settings.sso_callback_base_url}/api/v1/user/sso/qq/callback"
    )
    state = secrets.token_urlsafe(16)
    url = qq_authorize_url(settings.qq_app_id, redirect_uri, state)
    return RedirectResponse(url=url, status_code=302)


@router.get("/sso/qq/callback", tags=["sso"])
async def qq_callback(
    code: str,
    state: str = "",
    redis=Depends(get_redis),
) -> SsoCallbackResponse:
    settings = get_settings()
    if (
        not settings.qq_app_id
        or not settings.qq_app_secret
        or not settings.sso_callback_base_url
    ):
        raise HTTPException(
            status_code=503, detail={"code": "SSO_NOT_CONFIGURED"}
        )
    from .sso_clients import qq_exchange_code
    from .sso_session import create_sso_session

    redirect_uri = (
        f"{settings.sso_callback_base_url}/api/v1/user/sso/qq/callback"
    )
    try:
        openid = await qq_exchange_code(
            code, settings.qq_app_id, settings.qq_app_secret, redirect_uri
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_SSO_CODE", "message": str(exc)},
        )
    sid = await create_sso_session(redis, {"qq_openid": openid})
    return SsoCallbackResponse(sid=sid)


@router.post("/sso/qq/bind", tags=["sso"])
async def qq_bind(
    req: SsoBindRequest,
    db: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
) -> VoterFE:
    return await _sso_bind(req, "qq", db, redis)


# ── SSO: THBWiki ─────────────────────────────────────────────────────


@router.get("/sso/thbwiki/authorize", tags=["sso"])
async def thbwiki_authorize() -> RedirectResponse:
    settings = get_settings()
    if not settings.thbwiki_client_id or not settings.sso_callback_base_url:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SSO_NOT_CONFIGURED",
                "message": "THBWiki SSO is not configured",
            },
        )
    from .sso_clients import thbwiki_authorize_url

    redirect_uri = (
        f"{settings.sso_callback_base_url}/api/v1/user/sso/thbwiki/callback"
    )
    state = secrets.token_urlsafe(16)
    url = thbwiki_authorize_url(settings.thbwiki_client_id, redirect_uri, state)
    return RedirectResponse(url=url, status_code=302)


@router.get("/sso/thbwiki/callback", tags=["sso"])
async def thbwiki_callback(
    code: str,
    state: str = "",
    redis=Depends(get_redis),
) -> SsoCallbackResponse:
    settings = get_settings()
    if (
        not settings.thbwiki_client_id
        or not settings.thbwiki_client_secret
        or not settings.sso_callback_base_url
    ):
        raise HTTPException(
            status_code=503, detail={"code": "SSO_NOT_CONFIGURED"}
        )
    from .sso_clients import thbwiki_exchange_code
    from .sso_session import create_sso_session

    redirect_uri = (
        f"{settings.sso_callback_base_url}/api/v1/user/sso/thbwiki/callback"
    )
    try:
        uid = await thbwiki_exchange_code(
            code,
            settings.thbwiki_client_id,
            settings.thbwiki_client_secret,
            redirect_uri,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_SSO_CODE", "message": str(exc)},
        )
    sid = await create_sso_session(redis, {"thbwiki_uid": uid})
    return SsoCallbackResponse(sid=sid)


@router.post("/sso/thbwiki/bind", tags=["sso"])
async def thbwiki_bind(
    req: SsoBindRequest,
    db: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
) -> VoterFE:
    return await _sso_bind(req, "thbwiki", db, redis)


# ── shared bind helper ───────────────────────────────────────────────


async def _sso_bind(
    req: SsoBindRequest,
    provider: str,
    db: AsyncSession,
    redis,
) -> VoterFE:
    # Validate the session token first — always returns 401 on bad token,
    # regardless of whether SSO is configured.
    _user_id_from_body_token(req.user_token)

    settings = get_settings()

    if provider == "qq":
        if (
            not settings.qq_app_id
            or not settings.qq_app_secret
            or not settings.sso_callback_base_url
        ):
            raise HTTPException(
                status_code=503, detail={"code": "SSO_NOT_CONFIGURED"}
            )
        from .sso_clients import qq_exchange_code

        redirect_uri = (
            f"{settings.sso_callback_base_url}/api/v1/user/sso/qq/callback"
        )
        try:
            openid = await qq_exchange_code(
                req.code,
                settings.qq_app_id,
                settings.qq_app_secret,
                redirect_uri,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_SSO_CODE", "message": str(exc)},
            )
        sso_data = {"qq_openid": openid}
    else:  # thbwiki
        if (
            not settings.thbwiki_client_id
            or not settings.thbwiki_client_secret
            or not settings.sso_callback_base_url
        ):
            raise HTTPException(
                status_code=503, detail={"code": "SSO_NOT_CONFIGURED"}
            )
        from .sso_clients import thbwiki_exchange_code

        redirect_uri = (
            f"{settings.sso_callback_base_url}"
            f"/api/v1/user/sso/thbwiki/callback"
        )
        try:
            uid = await thbwiki_exchange_code(
                req.code,
                settings.thbwiki_client_id,
                settings.thbwiki_client_secret,
                redirect_uri,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_SSO_CODE", "message": str(exc)},
            )
        sso_data = {"thbwiki_uid": uid}

    from src.apps.user.dao import ActivityLogDAO, UserDAO
    from src.common.database import get_session_maker

    user_dao = UserDAO(db)
    activity_dao = ActivityLogDAO(get_session_maker())
    svc = UserService(user_dao=user_dao, activity_dao=activity_dao)
    try:
        voter_fe = await svc.bind_sso(req.user_token, sso_data)
    except AppException as exc:
        _raise_http(exc)
    return voter_fe
