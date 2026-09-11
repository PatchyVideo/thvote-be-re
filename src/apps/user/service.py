"""User service layer — business orchestration for the auth flows.

Responsibilities:
- Decode session tokens for mutation endpoints.
- Drive verification-code services (email Redis-backed; SMS via PNVS).
- Read/write accounts through ``UserDAO`` and identities through
  ``IdentityService`` (the only place that touches ``user_identity``).
- Audit every mutation through ``ActivityLogDAO`` on a best-effort
  basis (audit failures never abort the primary request).
- Sign session and (when eligible) vote tokens at login time.

Routers should call this layer; they should not import DAOs directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.apps.user.dao import ActivityLogDAO, UserDAO, UserIdentityDAO
from src.apps.user.identity import IdentityProvider, vote_eligible_providers
from src.apps.user.identity_service import IdentityService
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
    VoterFE,
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
from src.common.middleware.rate_limit import rate_limit
from src.common.verification import (
    CaptchaService,
    EmailCodeService,
    SmsCodeService,
    get_captcha_service,
    get_email_code_service,
    get_sms_code_service,
)
from src.db_model.user import User

logger = logging.getLogger(__name__)

_audit_log_failures: int = 0

# Redis LoginSession keys (sso_session.py) → provider.  The key names are
# the wire format the OAuth callbacks write; keep them stable.
_SSO_SESSION_KEYS: dict[str, IdentityProvider] = {
    "thbwiki_uid": IdentityProvider.THBWIKI,
    "qq_openid": IdentityProvider.QQ,
}


def get_audit_log_failures() -> int:
    """Return the count of ActivityLog write failures since process start."""
    return _audit_log_failures


@dataclass
class UserService:
    """Business orchestration for the user/auth module.

    Inject DAOs and verification services for testability.  Defaults are
    process-wide singletons so the FastAPI dependency wiring stays small.
    """

    user_dao: UserDAO
    activity_dao: ActivityLogDAO
    email_code_service: EmailCodeService = field(default_factory=get_email_code_service)
    sms_code_service: SmsCodeService = field(default_factory=get_sms_code_service)
    captcha_service: CaptchaService = field(default_factory=get_captcha_service)
    auth: AuthProvider = field(default_factory=AuthProvider)
    redis: object = field(default=None)
    settings: object = field(default=None)
    identities: IdentityService | None = None

    def __post_init__(self) -> None:
        if self.identities is None:
            self.identities = IdentityService(
                user_dao=self.user_dao,
                identity_dao=UserIdentityDAO(self.user_dao.session),
            )

    # ─── verification-code endpoints ──────────────────────────────────
    #
    # 限流分两层(B-043 补齐:此前发码端点无任何后端限流):
    # 1. per-IP 洪泛限流放在 captcha **之前**——挡洪泛,并保护每次验证码校验
    #    对阿里云的付费调用(0.005 元/次)不被刷爆。依赖 X-Real-IP 可信(B-044)。
    #    额度取 30/60s(宽松):captcha 已逐次拦每一次发码,per-IP 只是洪泛/成本
    #    兜底,可放宽;而共用出口 IP(校园/小区 NAT)一分钟内可能有几十真实用户同时
    #    注册,30/60s 给足余量避免误伤(30×0.005=0.15 元/分钟/IP 成本可忽略)。
    #    撞线仅"请求过于频繁"软提示,60s 后可重试。
    # 2. per-目标(手机号/邮箱)重发间隔放在 captcha **之后**——只对真正发出的
    #    码计数,避免"过验证码前失败也占额度"误伤真实用户。邮箱已有 120s guard。

    _SEND_CODE_IP_WINDOW = 60
    _SEND_CODE_IP_MAX = 30
    _SEND_CODE_PHONE_WINDOW = 60
    _SEND_CODE_PHONE_MAX = 1

    async def send_email_code(self, request: SendEmailCodeRequest) -> None:
        await rate_limit(
            f"sendcode-ip-{request.meta.user_ip or 'unknown'}",
            window=self._SEND_CODE_IP_WINDOW,
            max_requests=self._SEND_CODE_IP_MAX,
        )
        await self.captcha_service.verify_or_raise(request.captcha_verify_param)
        # 邮箱 per-地址重发间隔由 EmailCodeService 的 120s guard 承担(在 captcha 之后)
        await self.email_code_service.send(request.email)
        await self._safe_log(
            event_type="send_email",
            target_email=request.email,
            requester_ip=request.meta.user_ip,
            additional_fingerprint=request.meta.additional_fingureprint,
        )

    async def send_sms_code(self, request: SendSmsCodeRequest) -> None:
        await rate_limit(
            f"sendcode-ip-{request.meta.user_ip or 'unknown'}",
            window=self._SEND_CODE_IP_WINDOW,
            max_requests=self._SEND_CODE_IP_MAX,
        )
        await self.captcha_service.verify_or_raise(request.captcha_verify_param)
        await rate_limit(
            f"sendcode-phone-{request.phone}",
            window=self._SEND_CODE_PHONE_WINDOW,
            max_requests=self._SEND_CODE_PHONE_MAX,
        )
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
        # find_owner 而非 resolve：resolve 对封禁账号直接抛 USER_REMOVED，
        # 而它跑在验口令之前——未认证的调用方就能区分"这个邮箱属于封禁
        # 账号"和"查无此邮箱"。先验口令，口令对了才谈封禁。
        user = await self.identities.find_owner(IdentityProvider.EMAIL, request.email)
        if user is None or not user.password_hash:
            raise ValidationError("INCORRECT_PASSWORD", details=400)

        result = self.auth.verify_password(request.password, user.password_hash)
        if not result.valid:
            raise ValidationError("INCORRECT_PASSWORD", details=400)
        if user.removed:
            raise UnauthorizedError("USER_REMOVED", details=403)
        if result.needs_rehash and result.upgraded_hash:
            # 显式落库：不要指望下面的 touch_login 顺手 save——它在
            # identity 缺失时会提前 return，那条写入就无声丢了。
            user.password_hash = result.upgraded_hash
            await self.user_dao.save(user)

        await self.identities.touch_login(user, IdentityProvider.EMAIL)
        await self._safe_log(
            event_type="voter_login",
            user_id=user.id,
            target_email=request.email,
            requester_ip=request.meta.user_ip,
            additional_fingerprint=request.meta.additional_fingureprint,
        )
        await self._merge_sso_session(user, request.sid, request.meta)
        return self._build_login_response(user)

    async def login_with_email_code(self, request: LoginEmailRequest) -> LoginResponse:
        await self.email_code_service.consume(request.email, request.verify_code)
        return await self._login_by_identity(
            IdentityProvider.EMAIL,
            request.email,
            nickname=request.nickname,
            meta=request.meta,
            sid=request.sid,
        )

    async def login_with_phone_code(self, request: LoginPhoneRequest) -> LoginResponse:
        await self.sms_code_service.consume(request.phone, request.verify_code)
        return await self._login_by_identity(
            IdentityProvider.PHONE,
            request.phone,
            nickname=request.nickname,
            meta=request.meta,
            sid=request.sid,
        )

    async def _login_by_identity(
        self,
        provider: IdentityProvider,
        subject: str,
        *,
        nickname: str | None,
        meta: Meta,
        sid: str | None,
    ) -> LoginResponse:
        """Shared tail of every verified-identity login: find-or-register,
        audit, merge a pending SSO session, sign tokens."""
        user = await self.identities.resolve(provider, subject)
        if user is None:
            user = await self.identities.register(provider, subject, nickname, meta)
            await self._safe_log(
                event_type="voter_creation",
                user_id=user.id,
                new_value=nickname,
                requester_ip=meta.user_ip,
                additional_fingerprint=meta.additional_fingureprint,
                **_target_fields(provider, subject),
            )
        else:
            await self.identities.touch_login(user, provider, proven=True)
            await self._safe_log(
                event_type="voter_login",
                user_id=user.id,
                requester_ip=meta.user_ip,
                additional_fingerprint=meta.additional_fingureprint,
                **_target_fields(provider, subject),
            )

        await self._merge_sso_session(user, sid, meta)
        return self._build_login_response(user)

    # ─── update endpoints ────────────────────────────────────────────

    async def update_email(self, request: UpdateEmailRequest) -> None:
        user = await self._authenticate(request.user_token)
        await self.email_code_service.consume(request.email, request.verify_code)
        await self._rebind_contact(
            user, IdentityProvider.EMAIL, request.email, request.meta, "update_email"
        )

    async def update_phone(self, request: UpdatePhoneRequest) -> None:
        user = await self._authenticate(request.user_token)
        await self.sms_code_service.consume(request.phone, request.verify_code)
        await self._rebind_contact(
            user, IdentityProvider.PHONE, request.phone, request.meta, "update_phone"
        )

    async def _rebind_contact(
        self,
        user: User,
        provider: IdentityProvider,
        subject: str,
        meta: Meta,
        event_type: str,
    ) -> None:
        bound = await self.identities.bind(
            user, provider, subject, meta, conflict_code="USER_ALREADY_EXIST"
        )
        await self._safe_log(
            event_type=event_type,
            user_id=user.id,
            old_value=bound.replaced_subject,
            new_value=bound.identity.subject,
            requester_ip=meta.user_ip,
            additional_fingerprint=meta.additional_fingureprint,
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
            verification = self.auth.verify_password(
                request.old_password, user.password_hash
            )
            if not verification.valid:
                raise ValidationError("INCORRECT_PASSWORD", details=400)

        user.password_hash = self.auth.hash_password(request.new_password)
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

        if user.password_hash and request.old_password:
            verification = self.auth.verify_password(
                request.old_password, user.password_hash
            )
            if not verification.valid:
                raise ValidationError("INCORRECT_PASSWORD", details=400)

        # Soft delete: drop every identity row and the credential so nothing
        # can re-identify or re-authenticate this account (GDPR / 个保法 §47).
        # The account row stays as a tombstone for vote-record linkage.
        user.removed = True
        user.password_hash = None
        await self.identities.unbind_all(user)
        await self._safe_log(
            event_type="remove_voter",
            user_id=user.id,
            requester_ip=request.meta.user_ip,
            additional_fingerprint=request.meta.additional_fingureprint,
        )

    # ─── SSO binding ─────────────────────────────────────────────────

    async def _merge_sso_session(self, user: User, sid, meta: Meta) -> None:
        """Attach identities from a pending Redis LoginSession (if any).

        A conflict (openid already owned by someone else) is logged and
        skipped rather than raised: the user has already passed
        verification, the SSO attach is a courtesy (spec §5.3).
        """
        if not sid or not self.redis:
            return
        from .sso_session import consume_sso_session

        data = await consume_sso_session(self.redis, sid)
        if not data:
            return
        for key, provider in _SSO_SESSION_KEYS.items():
            subject = data.get(key)
            if not subject:
                continue
            # 这条路径是"补绑"，不是"改绑"：账号已有该 provider 的绑定时
            # 不得顶掉。bind() 的语义是替换——被顶掉的 openid 会随之释放，
            # 任何人都能再去认领；而这里只是登录顺带的 courtesy，用户并未
            # 表达换绑意图。换绑走 update_* / bind_sso 的显式入口。
            current = user.identity(provider.value)
            if current is not None and current.subject != subject:
                logger.warning(
                    "SSO merge skipped for user_id=%s provider=%s: "
                    "already bound to a different subject",
                    user.id,
                    provider.value,
                )
                continue
            try:
                bound = await self.identities.bind(
                    user, provider, subject, meta, conflict_code="SSO_ID_ALREADY_BOUND"
                )
            except ValidationError as exc:
                logger.warning(
                    "SSO merge skipped for user_id=%s provider=%s: %s",
                    user.id,
                    provider.value,
                    exc.message,
                )
                continue
            if bound.changed:
                await self._safe_log(
                    event_type="bind_sso",
                    user_id=user.id,
                    new_value=bound.identity.subject,
                    requester_ip=meta.user_ip,
                    additional_fingerprint=meta.additional_fingureprint,
                )

    async def bind_sso(
        self, user_token: str, sso_data: dict, meta: Meta | None = None
    ) -> VoterFE:
        """Bind an SSO identifier to an already-authenticated user.

        Raises:
            UnauthorizedError: if user_token is invalid
            ValidationError(SSO_ID_ALREADY_BOUND, 409): if the SSO ID
                belongs to another account
        """
        user = await self._require_session_token(user_token)
        meta = meta or Meta()
        for key, provider in _SSO_SESSION_KEYS.items():
            subject = sso_data.get(key)
            if not subject:
                continue
            await self.identities.bind(
                user, provider, subject, meta, conflict_code="SSO_ID_ALREADY_BOUND"
            )
        return voter_fe_from_user(user)

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
        eligible = vote_eligible_providers()
        if not any(
            identity.verified and identity.provider in eligible
            for identity in user.identities
        ):
            return ""

        settings = get_settings()
        try:
            start = datetime.fromisoformat(
                settings.vote_start_iso.replace("Z", "+00:00")
            )
            end = datetime.fromisoformat(settings.vote_end_iso.replace("Z", "+00:00"))
        except ValueError:
            # Misconfigured vote window must be loud, not silent — otherwise
            # every login succeeds with vote_token="" and submit silently
            # fails for every user with no operator-visible signal.
            logger.error(
                "Invalid VOTE_START_ISO=%r or VOTE_END_ISO=%r — every login "
                "will return an empty vote_token until config is fixed",
                settings.vote_start_iso,
                settings.vote_end_iso,
            )
            return ""

        now = datetime.now(UTC)
        if now < start or now > end:
            return ""
        return self.auth.create_vote_token(user.id, start, end)

    async def _safe_log(self, **fields) -> None:
        """Write an ActivityLog row best-effort; swallow any failure."""
        global _audit_log_failures
        cleaned = {k: v for k, v in fields.items() if v is not None}
        try:
            await self.activity_dao.write(**cleaned)
        except Exception:  # noqa: BLE001 -- audit must never break primary flow
            _audit_log_failures += 1
            logger.exception(
                "ActivityLog write failed (event_type=%s); continuing",
                cleaned.get("event_type"),
            )

    async def _require_session_token(self, user_token: str) -> User:
        """Decode a session token and return the User.

        Raises UnauthorizedError if the token is missing, invalid, or the user
        is removed.
        """
        if not user_token:
            raise UnauthorizedError("INVALID_SESSION_TOKEN", "Missing session token")
        try:
            payload = self.auth.decode_session_token(user_token)
        except AppException as exc:
            raise UnauthorizedError(
                "INVALID_SESSION_TOKEN", "Invalid session token"
            ) from exc
        user = await self.user_dao.get_by_id(payload.user_id)
        if user is None or user.removed:
            raise UnauthorizedError("INVALID_SESSION_TOKEN", "User not found")
        return user


def _target_fields(provider: IdentityProvider, subject: str) -> dict[str, str]:
    """ActivityLog target column for a contact identity (none for SSO)."""
    if provider is IdentityProvider.EMAIL:
        return {"target_email": subject}
    if provider is IdentityProvider.PHONE:
        return {"target_phone": subject}
    return {}
