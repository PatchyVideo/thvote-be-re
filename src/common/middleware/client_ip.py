"""Client IP contextvar 中间件(B-060)。

把经 B-044 可信代理规则(`get_client_ip`,读 X-Real-IP + CIDR 信任)解析出的
客户端 IP 放进 ContextVar,供不在 FastAPI 依赖注入链路里的深层代码读取——
典型消费方是 GraphQL resolver 之下的高级搜索服务层(per-IP miss 限频),
免去把 Request 对象穿透 10 个 GraphQL 字段签名。

非 HTTP 上下文(测试直调、脚本)里 ContextVar 保持默认 None,消费方须把
None 当"无 IP 信息"降级处理(只走全局限频),不得报错。
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

client_ip_var: ContextVar[str | None] = ContextVar("client_ip", default=None)


class ClientIPMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # 延迟导入:user.deps 会拉起 config 链,模块顶层导入有环风险
        from src.apps.user.deps import get_client_ip

        token = client_ip_var.set(get_client_ip(request))
        try:
            return await call_next(request)
        finally:
            client_ip_var.reset(token)
