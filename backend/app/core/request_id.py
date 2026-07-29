from __future__ import annotations

import re
from contextvars import ContextVar
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


REQUEST_ID_HEADER = "X-Request-Id"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def create_request_id() -> str:
    return uuid4().hex


def normalize_request_id(value: str | None) -> str:
    candidate = (value or "").strip()
    return candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else create_request_id()


def current_request_id() -> str:
    return _request_id.get()


class RequestIdMiddleware:
    """Pure ASGI middleware so streaming responses are not buffered."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = normalize_request_id(headers.get(REQUEST_ID_HEADER))
        scope.setdefault("state", {})["request_id"] = request_id
        token = _request_id.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _request_id.reset(token)
