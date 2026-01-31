"""Custom exception types for Tinman.

This module defines a hierarchy of exceptions for better error handling
and classification throughout the Tinman system.
"""

from typing import Any


class TinmanError(Exception):
    """Base exception for all Tinman errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


# LLM-related exceptions
class LLMError(TinmanError):
    """Base exception for LLM-related errors."""

    pass


class LLMTimeoutError(LLMError):
    """Raised when an LLM call times out."""

    def __init__(
        self, message: str = "LLM call timed out", timeout_seconds: float | None = None
    ):
        details = {"timeout_seconds": timeout_seconds} if timeout_seconds else {}
        super().__init__(message, details)
        self.timeout_seconds = timeout_seconds


class LLMResponseError(LLMError):
    """Raised when LLM returns an invalid or unparseable response."""

    def __init__(self, message: str, raw_response: str | None = None):
        details = {"raw_response": raw_response[:500] if raw_response else None}
        super().__init__(message, details)
        self.raw_response = raw_response


class LLMRateLimitError(LLMError):
    """Raised when LLM API rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: float | None = None):
        details = {"retry_after_seconds": retry_after} if retry_after else {}
        super().__init__(message, details)
        self.retry_after = retry_after


# Validation exceptions
class ValidationError(TinmanError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: str | None = None, value: Any = None):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)[:100]  # Truncate long values
        super().__init__(message, details)
        self.field = field
        self.value = value


# Approval exceptions
class ApprovalError(TinmanError):
    """Base exception for approval-related errors."""

    pass


class ApprovalTimeoutError(ApprovalError):
    """Raised when an approval request times out."""

    def __init__(
        self, message: str = "Approval request timed out", request_id: str | None = None
    ):
        details = {"request_id": request_id} if request_id else {}
        super().__init__(message, details)
        self.request_id = request_id


class ApprovalDeniedError(ApprovalError):
    """Raised when an approval request is denied."""

    def __init__(self, message: str = "Approval denied", reason: str | None = None):
        details = {"reason": reason} if reason else {}
        super().__init__(message, details)
        self.reason = reason


# Agent exceptions
class AgentError(TinmanError):
    """Base exception for agent-related errors."""

    pass


class AgentTimeoutError(AgentError):
    """Raised when an agent execution times out."""

    def __init__(
        self,
        message: str,
        agent_type: str | None = None,
        timeout_seconds: float | None = None,
    ):
        details = {}
        if agent_type:
            details["agent_type"] = agent_type
        if timeout_seconds:
            details["timeout_seconds"] = timeout_seconds
        super().__init__(message, details)
        self.agent_type = agent_type
        self.timeout_seconds = timeout_seconds


class AgentExecutionError(AgentError):
    """Raised when an agent fails during execution."""

    def __init__(
        self, message: str, agent_type: str | None = None, cause: Exception | None = None
    ):
        details = {"agent_type": agent_type} if agent_type else {}
        super().__init__(message, details)
        self.agent_type = agent_type
        self.__cause__ = cause


# Mode exceptions
class ModeError(TinmanError):
    """Base exception for mode-related errors."""

    pass


class ModeTransitionError(ModeError):
    """Raised when an invalid mode transition is attempted."""

    def __init__(
        self, message: str, from_mode: str | None = None, to_mode: str | None = None
    ):
        details = {}
        if from_mode:
            details["from_mode"] = from_mode
        if to_mode:
            details["to_mode"] = to_mode
        super().__init__(message, details)
        self.from_mode = from_mode
        self.to_mode = to_mode


class ModeRestrictionError(ModeError):
    """Raised when an action is not allowed in the current mode."""

    def __init__(
        self, message: str, current_mode: str | None = None, action: str | None = None
    ):
        details = {}
        if current_mode:
            details["current_mode"] = current_mode
        if action:
            details["action"] = action
        super().__init__(message, details)
        self.current_mode = current_mode
        self.action = action


# Database exceptions
class DatabaseError(TinmanError):
    """Base exception for database-related errors."""

    pass


class TransactionError(DatabaseError):
    """Raised when a database transaction fails."""

    pass


# Tool exceptions
class ToolError(TinmanError):
    """Base exception for tool-related errors."""

    pass


class ToolBlockedError(ToolError):
    """Raised when a tool execution is blocked by risk policy."""

    def __init__(
        self, message: str, tool_name: str | None = None, risk_tier: str | None = None
    ):
        details = {}
        if tool_name:
            details["tool_name"] = tool_name
        if risk_tier:
            details["risk_tier"] = risk_tier
        super().__init__(message, details)
        self.tool_name = tool_name
        self.risk_tier = risk_tier
