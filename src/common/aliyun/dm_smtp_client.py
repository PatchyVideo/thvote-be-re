"""Aliyun DirectMail SMTP client.

Sends 6-digit verification codes via Aliyun DM's SMTP gateway.  The code
is generated locally by ``EmailCodeService`` and passed in here as a
plain string; this client only handles MIME assembly + SMTP transport.

References:
- https://help.aliyun.com/zh/direct-mail/use-cases/send-emails-using-smtp
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from functools import lru_cache

from src.common.config import Settings, get_settings
from src.common.exceptions import AppException, ExternalAPIError

logger = logging.getLogger(__name__)


class AliyunDmSmtpClient:
    """SMTP wrapper around Aliyun DirectMail.

    Construct via ``get_dm_smtp_client()``.  Tests should patch this
    class (or the ``send_verification_email`` method) rather than
    smtplib directly.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _ensure_configured(self) -> None:
        s = self._settings
        if not (
            s.aliyun_dm_smtp_host
            and s.aliyun_dm_smtp_username
            and s.aliyun_dm_smtp_password
            and s.aliyun_dm_account_name
        ):
            raise AppException("ALIYUN_NOT_CONFIGURED", details=500)

    async def send_verification_email(self, *, recipient: str, code: str) -> None:
        """Send a verification-code email; raises ExternalAPIError on failure.

        The body is intentionally minimal — production templates can be
        introduced later by passing an HTML body alongside the plain text.
        """
        self._ensure_configured()

        message = self._build_message(recipient=recipient, code=code)
        import asyncio

        try:
            await asyncio.to_thread(self._send_sync, recipient, message.as_string())
        except (smtplib.SMTPException, OSError) as exc:
            logger.exception("Aliyun DM SMTP send failed for %s", _mask_email(recipient))
            raise ExternalAPIError("EMAIL_SEND_FAILED", details=502) from exc

    def _build_message(self, *, recipient: str, code: str) -> MIMEMultipart:
        s = self._settings
        from_alias = s.aliyun_dm_from_alias or "THVote"
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "THVote 验证码"
        msg["From"] = formataddr((from_alias, str(s.aliyun_dm_account_name)))
        msg["To"] = recipient
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        if s.aliyun_dm_tag_name:
            msg["X-AliDM-Tag"] = s.aliyun_dm_tag_name

        text_body = (
            f"您的 THVote 验证码：{code}\n"
            f"验证码 1 小时内有效，请勿将其提供给他人。\n"
            f"如非本人操作，请忽略此邮件。\n"
        )
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        return msg

    def _send_sync(self, recipient: str, raw_message: str) -> None:
        s = self._settings
        host = str(s.aliyun_dm_smtp_host)
        port = int(s.aliyun_dm_smtp_port or 465)
        username = str(s.aliyun_dm_smtp_username)
        password = str(s.aliyun_dm_smtp_password)
        sender = str(s.aliyun_dm_account_name)

        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=10) as smtp:
                smtp.login(username, password)
                smtp.sendmail(sender, [recipient], raw_message)
        else:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                smtp.starttls(context=context)
                smtp.login(username, password)
                smtp.sendmail(sender, [recipient], raw_message)


def _mask_email(email: str) -> str:
    """u***r@example.com style masking for log output."""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{'*' * len(local)}@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


@lru_cache(maxsize=1)
def get_dm_smtp_client() -> AliyunDmSmtpClient:
    """Return the process-wide DM SMTP client singleton."""
    return AliyunDmSmtpClient(get_settings())
