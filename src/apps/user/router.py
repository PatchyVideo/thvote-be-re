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

from fastapi import APIRouter, Depends, HTTPException

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
    TokenStatusRequest,
    UpdateEmailRequest,
    UpdateNicknameRequest,
    UpdatePasswordRequest,
    UpdatePhoneRequest,
    VoterFE,
    voter_fe_from_user,
)
from src.apps.user.service import UserService
from src.common.exceptions import AppException
from src.common.middleware.rate_limit import rate_limit
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


async def _rate_limit_by_token(token: str) -> None:
    user_id = _user_id_from_body_token(token)
    await rate_limit(f"user-mut-{user_id}", window=60, max_requests=5)


@router.post("/update-email", response_model=EmptyResponse)
async def update_email(
    body: UpdateEmailRequest,
    client_ip: str = Depends(get_client_ip),
    service: UserService = Depends(get_user_service),
) -> EmptyResponse:
    await _rate_limit_by_token(body.user_token)
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
    await _rate_limit_by_token(body.user_token)
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
    await _rate_limit_by_token(body.user_token)
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
    await _rate_limit_by_token(body.user_token)
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
    await _rate_limit_by_token(body.user_token)
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
