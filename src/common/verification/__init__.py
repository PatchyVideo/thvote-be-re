"""Verification-code services.

EmailCodeService: locally generated 6-digit codes stored in Redis with
guard keys for anti-spam (mirrors Rust user-manager behavior).

SmsCodeService: thin orchestration over Aliyun PNVS — Aliyun owns the
code lifecycle, this service just translates send/check calls.

CaptchaService: human-verification gate (Aliyun CAPTCHA 2.0) enforced
before any code is sent (B-043); no-op while ALIYUN_CAPTCHA_ENABLED=false.
"""

from .captcha import CaptchaService, get_captcha_service
from .email_code import EmailCodeService, get_email_code_service
from .sms_code import SmsCodeService, get_sms_code_service

__all__ = [
    "CaptchaService",
    "EmailCodeService",
    "SmsCodeService",
    "get_captcha_service",
    "get_email_code_service",
    "get_sms_code_service",
]
