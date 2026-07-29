from __future__ import annotations

from http import HTTPStatus
from typing import Any

from app.core.agent.contracts import AgentError, AgentErrorEnvelope, ErrorCode


class AgentException(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR,
        retryable: bool = False,
        stage: str = "agent",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = int(status_code)
        self.retryable = retryable
        self.stage = stage
        self.details = details or {}

    def to_error(self, request_id: str) -> AgentError:
        return AgentError(
            request_id=request_id,
            code=self.code,
            message=str(self),
            retryable=self.retryable,
            stage=self.stage,
            details=self.details,
        )

    def to_envelope(self, request_id: str) -> AgentErrorEnvelope:
        error = self.to_error(request_id)
        return AgentErrorEnvelope(detail=error.message, error=error)


def invalid_input(
    message: str,
    *,
    status_code: int = HTTPStatus.BAD_REQUEST,
    stage: str = "validate_input",
    details: dict[str, Any] | None = None,
) -> AgentException:
    return AgentException(
        ErrorCode.INVALID_INPUT,
        message,
        status_code=status_code,
        stage=stage,
        details=details,
    )


def classify_exception(error: Exception, *, stage: str = "agent") -> AgentException:
    if isinstance(error, AgentException):
        return error
    if isinstance(error, FileNotFoundError):
        return AgentException(
            ErrorCode.INDEX_NOT_READY,
            str(error),
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            retryable=True,
            stage=stage,
        )
    if isinstance(error, RuntimeError):
        return AgentException(
            ErrorCode.RETRIEVAL_UNAVAILABLE,
            str(error),
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            retryable=True,
            stage=stage,
        )
    if isinstance(error, TimeoutError):
        return AgentException(
            ErrorCode.TOOL_EXECUTION_FAILED,
            "Agent dependency timed out.",
            status_code=HTTPStatus.GATEWAY_TIMEOUT,
            retryable=True,
            stage=stage,
            details={"error_type": type(error).__name__},
        )
    if isinstance(error, ValueError):
        return invalid_input(str(error), stage=stage)
    return AgentException(
        ErrorCode.INTERNAL_ERROR,
        "Agent request failed unexpectedly.",
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        stage=stage,
        details={"error_type": type(error).__name__},
    )
