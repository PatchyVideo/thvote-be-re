"""Aliyun service clients (PNVS for SMS, DirectMail for email).

Both clients are lazy singletons keyed on the cached settings; they are
constructed on first use and reused across requests.  Tests should mock
the public client classes (``AliyunPnvsClient`` / ``AliyunDmSmtpClient``)
rather than the underlying SDKs.
"""

from .dm_smtp_client import AliyunDmSmtpClient, get_dm_smtp_client
from .pnvs_client import (
    AliyunPnvsClient,
    PnvsResult,
    PnvsSendResult,
    get_pnvs_client,
)

__all__ = [
    "AliyunPnvsClient",
    "AliyunDmSmtpClient",
    "PnvsSendResult",
    "PnvsResult",
    "get_pnvs_client",
    "get_dm_smtp_client",
]
