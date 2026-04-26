"""User service layer — business orchestration for the auth flows.

Responsibilities:
- Decode session tokens for mutation endpoints.
- Drive verification-code services (email Redis-backed; SMS via PNVS).
- Read/write the ``user`` table through ``UserDAO``.
- Audit every mutation through ``ActivityLogDAO`` on a best-effort
  basis (audit failures never abort the primary request).
- Sign session and (when eligible) vote tokens at login time.

Routers should call this layer; they should not import DAOs directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.apps.user.dao import ActivityLogDAO, UserDAO
from src.apps.user.schemas import (
    LoginEmailPasswordRequest,
    LoginEmailRequest,
    LoginPhoneRequest,
    LoginResponse,
    Meta,
    RemoveVoterRequest,
    SendEmailCodeRequest,
    SendSmsCodeRequest,
    TokenStatusRequest,
    UpdateEmailRequest,
    UpdateNicknameRequest,
    UpdatePasswordRequest,
    UpdatePhoneRequest,
    generate_user_id,
    voter_fe_from_user,
)
from src.apps.user.utils.security import AuthProvider
from src.common.config import get_settings
from src.common.exceptions import (
    AppException,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from src.common.verification import (
    EmailCodeService,
    SmsCodeService,
    get_email_code_service,
    get_sms_code_service,
)
from src.db_model.user import User

logger = logging.getLogger(__name__)


@dataclass
class UserService:
    """Business orchestration for the user/auth module.

    Inject DAOs and verification services for testability.  Defaults are
    process-wide singletons so the FastAPI dependency wiring stays small.
    """

    user_dao: UserDAO
    activity_dao: ActivityLogDAO
    email_code_service: EmailCodeService = field(
        default_factory=get_email_code_service
    )
    sms_code_service: SmsCodeService = field(default_factory=get_sms_code_service)
    auth: AuthProvider = field(default_factory=AuthProvider)

    # ─── verification-code endpoints ──────────────────────────────────

    async def send_email_code(self, request: SendEmailCodeRequest) -> None:
        await self.email_code_service.send(request.email)
        await self._safe_log(
            event_type="send_email",
            target_email=request.email,
            requester_ip=request.meta.user_ip,
            additional_fingerprint=request.meta.additional_fingureprint,
        )

    async def send_sms_code(self, request: SendSmsCodeRequest) -> None:
        result = await self.sms_code_service.send(request.phone)
        await self._safe_log(
            event_type="send_sms",
            target_phone=request.phone,
            detail=f"BizId={result.biz_id}" if result.biz_id else None,
            requester_ip=request.meta.user_ip,
            additional_fingerprint=request.meta.additional_fingureprint,
        )

    # ─── login endpoints ─────────────────────────────────────────────

    async def login_with_email_password(
        self, request: LoginEmailPasswordRequest
    ) -> LoginResponse:
        user = await self.user_dao.get_by_email(request.email)
        if user is None:
            raise ValidationError("INCORRECT_PASSWORD", details=400)

        result = self.auth.verify_any_password(
            password=request.password,
            password_hashed=user.password_hash or "",
            legacy_salt=user.legacy_salt,
        )
        if not result.valid:
            raise ValidationError("INCORRECT_PASSWORD", details=400)

        if result.needs_rehash and result.upgraded_hash:
            user.password_hash = result.upgraded_hash
            user.legacy_salt = None
            await self.user_dao.save(user)

        await self._safe_log(
            event_type="voter_login",
            user_id=user.id,
            target_email=user.email,
            requester_ip=request.meta.user_ip,
            additional_fingerprint=request.meta.additional_fingureprint,
        )
        return self._build_login_response(user)

    async def login_with_email_code(self, request: LoginEmailRequest) -> LoginResponse:
        await self.email_code_service.consume(request.email, request.verify_code)

        user = await self.user_dao.get_by_email(request.email)
        if user is None:
            user = await self._register_via_email(
                email=request.email,
                nickname=request.nickname,
                meta=request.meta,
            )
        else:
            if not user.email_verified:
                user.email_verified = True
                await self.user_dao.save(user)
            await self._safe_log(
                event_type="voter_login",
                user_id=user.id,
                target_email=user.email,
                requester_ip=request.meta.user_ip,
                additional_fingerprint=request.meta.additional_fingureprint,
            )

        return self._build_login_response(user)

    async def login_with_phone_code(self, request: LoginPhoneRequest) -> LoginResponse:
        await self.sms_code_service.consume(request.phone, request.verify_code)

        user = await self.user_dao.get_by_phone(request.phone)
        if user is None:
            user = await self._register_via_phone(
                phone=request.phone,
                nickname=request.nickname,
                meta=request.meta,
            )
        else:
            if not user.phone_verified:
                user.phone_verified = True
                await self.user_dao.save(user)
            await self._safe_log(
                event_type="voter_login",
                user_id=user.id,
                target_phone=user.phone_number,
                requester_ip=request.meta.user_ip,
                additional_fingerprint=request.meta.additional_fingureprint,
            )

        return self._build_login_response(user)

    # ─── update endpoints ────────────────────────────────────────────

    async def update_email(self, request: UpdateEmailRequest) -> None:
        user = await self._authenticate(request.user_token)
        await self.email_code_service.consume(request.email, request.verify_code)

        existing = await self.user_dao.get_by_email(request.email)
        if existing is not None and existing.id != user.id:
            raise ValidationError("USER_ALREADY_EXIST", details=409)

        old_value = user.email
        user.email = request.email
        user.email_verified = True
        await self.user_dao.save(user)
        await self._safe_log(
            event_type="update_email",
            user_id=user.id,
            old_value=old_value,
            new_value=request.email,
            requester_ip=request.meta.user_ip,
            additional_fingerprint=request.meta.additional_fingureprint,
        )

    async def update_phone(self, request: UpdatePhoneRequest) -> None:
        user = await self._authenticate(request.user_token)
        await self.sms_code_service.consume(request.phone, request.verify_code)

        existing = await self.user_dao.get_by_phone(request.phone)
        if existing is not None and existing.id != user.id:
            raise ValidationError("USER_ALREADY_EXIST", details=409)

        old_value = user.phone_number
        user.phone_number = request.phone
        user.phone_verified = True
        await self.user_dao.save(user)
        await self._safe_log(
            event_type="update_phone",
            user_id=user.id,
            old_value=old_value,
            new_value=request.phone,
            requester_ip=request.meta.user_ip,
            additional_fingerprint=request.meta.additional_fingureprint,
        )

    async def update_nickname(self, request: UpdateNicknameRequest) -> None:
        user = await self._authenticate(request.user_token)
        old_value = user.nickname
        user.nickname = request.nickname
        await self.user_dao.save(user)
        await self._safe_log(
            event_type="update_nickname",
            user_id=user.id,
            old_value=old_value,
            new_value=request.nickname,
            requester_ip=request.meta.user_ip,
            additional_fingerprint=request.meta.additional_fingureprint,
        )

    async def update_password(self, request: UpdatePasswordRequest) -> None:
        user = await self._authenticate(request.user_token)

        if user.password_hash:
            if not request.old_password:
                raise ValidationError("OLD_PASSWORD_REQUIRED", details=400)
            verification = self.auth.verify_any_password(
                password=request.old_password,
                password_hashed=user.password_hash,
                legacy_salt=user.legacy_salt,
            )
            if not verification.valid:
                raise ValidationError("INCORRECT_PASSWORD", details=400)

        user.password_hash = self.auth.hash_password(request.new_password)
        user.legacy_salt = None
        await self.user_dao.save(user)
        await self._safe_log(
            event_type="update_password",
            user_id=user.id,
            requester_ip=request.meta.user_ip,
            additional_fingerprint=request.meta.additional_fingureprint,
        )

    # ─── token + lifecycle ───────────────────────────────────────────

    async def token_status(self, request: TokenStatusRequest) -> None:
        """Validate the token; no DB read, no log entry."""
        try:
            self.auth.decode_session_token(request.user_token)
        except AppException as exc:
            raise UnauthorizedError("INVALID_TOKEN", details=401) from exc

    async def remove_voter(self, request: RemoveVoterRequest) -> None:
        user = await self._authenticate(request.user_token)

        if user.password_hash:
            if request.old_password:
                verification = self.auth.verify_any_password(
                    password=request.old_password,
                    password_hashed=user.password_hash,
                    legacy_salt=user.legacy_salt,
                )
                if not verification.valid:
                    raise ValidationError("INCORRECT_PASSWORD", details=400)

        user.removed = True
        user.email = None
        user.phone_number = None
        user.email_verified = False
        user.phone_verified = False
        await self.user_dao.save(user)
        await self._safe_log(
            event_type="remove_voter",
            user_id=user.id,
            requester_ip=request.meta.user_ip,
            additional_fingerprint=request.meta.additional_fingureprint,
        )

    # ─── registration helpers ────────────────────────────────────────

    async def _register_via_email(
        self, email: str, nickname: str | None, meta: Meta
    ) -> User:
        user = User(
            id=generate_user_id(),
            email=email,
            email_verified=True,
            nickname=nickname,
            register_ip_address=meta.user_ip or "",
        )
        created = await self.user_dao.create(user)
        await self._safe_log(
            event_type="voter_creation",
            user_id=created.id,
            target_email=email,
            new_value=nickname,
            requester_ip=meta.user_ip,
            additional_fingerprint=meta.additional_fingureprint,
        )
        return created

    async def _register_via_phone(
        self, phone: str, nickname: str | None, meta: Meta
    ) -> User:
        user = User(
            id=generate_user_id(),
            phone_number=phone,
            phone_verified=True,
            nickname=nickname,
            register_ip_address=meta.user_ip or "",
        )
        created = await self.user_dao.create(user)
        await self._safe_log(
            event_type="voter_creation",
            user_id=created.id,
            target_phone=phone,
            new_value=nickname,
            requester_ip=meta.user_ip,
            additional_fingerprint=meta.additional_fingureprint,
        )
        return created

    # ─── shared helpers ──────────────────────────────────────────────

    async def _authenticate(self, token: str) -> User:
        """Decode the session token and return the (active) User row."""
        try:
            payload = self.auth.decode_session_token(token)
        except AppException as exc:
            raise UnauthorizedError("INVALID_TOKEN", details=401) from exc
        user = await self.user_dao.get_by_id(payload.user_id)
        if user is None:
            raise NotFoundError("USER_NOT_FOUND", details=404)
        return user

    def _build_login_response(self, user: User) -> LoginResponse:
        session_token = self.auth.create_session_token(user.id)
        vote_token = self._maybe_sign_vote_token(user)
        return LoginResponse(
            user=voter_fe_from_user(user),
            session_token=session_token,
            vote_token=vote_token,
        )

    def _maybe_sign_vote_token(self, user: User) -> str:
        if not (user.email_verified or user.phone_verified):
            return ""

        settings = get_settings()
        try:
            start = datetime.fromisoformat(settings.vote_start_iso.replace("Z", "+00:00"))
            end = datetime.fromisoformat(settings.vote_end_iso.replace("Z", "+00:00"))
        except ValueError:
            logger.warning(
                "Invalid VOTE_START_ISO/VOTE_END_ISO; skipping vote_token issuance"
            )
            return ""

        now = datetime.now(UTC)
        if now < start or now > end:
            return ""
        return self.auth.create_vote_token(user.id, start, end)

    async def _safe_log(self, **fields) -> None:
        """Write an ActivityLog row best-effort; swallow any failure."""
        cleaned = {k: v for k, v in fields.items() if v is not None}
        try:
            await self.activity_dao.write(**cleaned)
        except Exception:  # noqa: BLE001 -- audit must never break primary flow
            logger.exception(
                "ActivityLog write failed (event_type=%s); continuing",
                cleaned.get("event_type"),
            )
