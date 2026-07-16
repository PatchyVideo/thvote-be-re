"""Shared GraphQL resolver plumbing: error mapping + client-IP extraction.

map_app_errors / _extensions 原住在 resolvers/user.py;submit 桥也需要同一套
错误契约,故下沉到此(单一出处,user.py 改为从这里 import)。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import strawberry
from fastapi import HTTPException
from graphql import GraphQLError

from src.apps.user.deps import get_client_ip
from src.common.exceptions import AppException

logger = logging.getLogger(__name__)

# error_kind → 面向用户的中文文案。前端部分错误处理直接展示
# extensions.human_readable_message。未列出的 kind 回退 None(前端走自己的兜底)。
# 只放安全、可直接展示给终端用户的措辞,不含任何敏感信息。
_HUMAN_READABLE_MESSAGES: dict[str, str] = {
    "INCORRECT_VERIFY_CODE": "验证码错误或已失效，请重新获取",
    "SMS_VERIFY_FAILED": "验证码校验失败，请重试",
    "INCORRECT_PASSWORD": "密码错误",
    "OLD_PASSWORD_REQUIRED": "请输入原密码",
    "EMAIL_IN_USE": "该邮箱已被使用",
    "PHONE_IN_USE": "该手机号已被使用",
    "USER_ALREADY_EXIST": "该账号已存在",
    "REQUEST_TOO_FREQUENT": "请求过于频繁，请稍后再试",
    "INVALID_PHONE": "手机号格式不正确",
    "INVALID_EMAIL": "邮箱格式不正确",
    "INVALID_TOKEN": "登录已失效，请重新登录",
    "USER_NOT_FOUND": "用户不存在",
    "SMS_SEND_FAILED": "短信发送失败，请稍后重试",
    "ALIYUN_NOT_CONFIGURED": "服务暂未配置，请联系管理员",
    "CAPTCHA_REQUIRED": "请完成人机验证",
    "CAPTCHA_FAILED": "人机验证未通过，请重试",
    "CAPTCHA_UNAVAILABLE": "人机验证服务暂不可用，请稍后再试",
    "INTERNAL_ERROR": "服务器开小差了，请稍后重试",
    "SUBMIT_LOCKED": "提交处理中，请稍后再试",
}


def _client_ip_from_info(info: "strawberry.Info") -> str:
    """Extract the real client IP from the Strawberry request context."""
    ctx = info.context
    request = ctx["request"] if isinstance(ctx, dict) else getattr(ctx, "request", None)
    if request is None:
        return ""
    return get_client_ip(request)


def _extensions(
    service: str,
    error_kind: str,
    *,
    error_message: Optional[str] = None,
    upstream: Optional[str] = None,
    human_readable: Optional[str] = None,
) -> dict[str, object]:
    return {
        "service": service,
        "url": None,
        "error_kind": error_kind,
        "error_message": error_message,
        "human_readable_message": (
            human_readable
            if human_readable is not None
            else _HUMAN_READABLE_MESSAGES.get(error_kind)
        ),
        "upstream_response_string": upstream,
    }


@asynccontextmanager
async def map_app_errors(
    service: str, *, remap: Optional[dict[str, str]] = None
) -> AsyncIterator[None]:
    """Translate service-layer errors into a Rust-aligned GraphQLError.

    *remap* lets a resolver rename a service error_kind to the one the
    frontend expects (e.g. the service's generic ``USER_ALREADY_EXIST`` →
    ``EMAIL_IN_USE`` / ``PHONE_IN_USE`` for the update mutations).
    """
    try:
        yield
    except AppException as exc:
        kind = (remap or {}).get(exc.message, exc.message)
        raise GraphQLError(
            "Error",
            extensions=_extensions(
                service,
                kind,
                error_message=getattr(exc, "error_message", None),
                upstream=getattr(exc, "upstream_response_string", None),
                human_readable=getattr(exc, "human_readable_message", None),
            ),
        ) from exc
    except HTTPException as exc:
        raise GraphQLError(
            "Error", extensions=_extensions(service, str(exc.detail))
        ) from exc
    except GraphQLError:
        raise  # already-mapped error — pass through unchanged
    except Exception as exc:
        # 真实异常进日志(含堆栈),响应只暴露稳定的 INTERNAL_ERROR,
        # 不向调用方透出内部细节(SDK/SQL/类名等)。
        logger.exception("Unhandled error in GraphQL resolver (service=%s)", service)
        raise GraphQLError(
            "Error",
            extensions=_extensions(service, "INTERNAL_ERROR", error_message=None),
        ) from exc
