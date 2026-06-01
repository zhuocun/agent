"""Protocol types for future backend-side tool execution.

This does not implement an agent loop. It gives tool callers one bounded shape
for inputs, outputs, and human approval state so future tools can be additive
instead of inventing a new transcript contract per tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

ToolApprovalState = Literal[
    "not_required",
    "pending",
    "approved",
    "rejected",
]

ToolRunStatus = Literal[
    "pending",
    "awaiting_approval",
    "running",
    "succeeded",
    "failed",
    "cancelled",
]


@dataclass(frozen=True)
class ToolCallRequest:
    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)
    approval_state: ToolApprovalState = "not_required"


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_call_id: str
    name: str
    status: ToolRunStatus
    output: dict[str, Any] = field(default_factory=dict)
    summary: str | None = None
    error: str | None = None
    approval_state: ToolApprovalState = "not_required"


class ToolExecutor(Protocol):
    """Executes one approved tool call.

    Implementations should return `awaiting_approval` instead of performing
    side effects when `approval_state` is `pending`.
    """

    async def execute(self, call: ToolCallRequest) -> ToolExecutionResult: ...
