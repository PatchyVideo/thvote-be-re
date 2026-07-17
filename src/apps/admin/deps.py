"""管理端鉴权依赖(B-049):X-Admin-Secret 强制必填 + IP 白名单,fail-closed。

放独立模块(不放 router.py)以便 admin/router 与 monitor/router 共用,避免循环导入。
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

from src.apps.user.deps import get_client_ip
from src.common.config import Settings, get_settings

_logger = logging.getLogger(__name__)


def _ip_allowed(client_ip: str, allowlist: list[str]) -> bool:
    """空白名单=放行(逃生舱);否则精确 IP 或 CIDR 命中才放行。"""
    if not allowlist:
        return True
    try:
        ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in allowlist:
        try:
            if "/" in entry:
                if ip in ipaddress.ip_network(entry, strict=False):
                    return True
            elif ip == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue  # 白名单里写错的条目跳过,不影响其余
    return False


async def require_admin(
    request: Request,
    x_admin_secret: Optional[str] = Header(None),
    settings: Settings = Depends(get_settings),
) -> None:
    # fail-closed:未配 secret 一律拒(不留"未配=放行"的开放后门)
    if not settings.admin_secret or x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    client_ip = get_client_ip(request)
    if not _ip_allowed(client_ip, settings.admin_allowed_ips):
        # 不记完整 IP,避免噪声;仅计一次拒绝
        _logger.warning("admin request rejected: IP not in allowlist")
        raise HTTPException(status_code=403, detail="FORBIDDEN_IP")
