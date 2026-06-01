from __future__ import annotations

from app.schemas.message import ChatMessage, ToolCallPart, ToolResultPart


def test_tool_parts_round_trip_with_approval_state() -> None:
    message = ChatMessage.model_validate(
        {
            "id": "assistant-1",
            "role": "assistant",
            "createdAt": "2026-06-01T00:00:00Z",
            "status": "done",
            "parts": [
                {
                    "type": "tool_call",
                    "id": "call-1",
                    "name": "calendar_create_event",
                    "label": "Create calendar event",
                    "status": "awaiting_approval",
                    "approvalState": "pending",
                    "input": {"title": "Planning review"},
                },
                {
                    "type": "tool_result",
                    "toolCallId": "call-1",
                    "name": "calendar_create_event",
                    "status": "cancelled",
                    "approvalState": "rejected",
                    "error": "User rejected the tool call.",
                },
            ],
        }
    )

    assert isinstance(message.parts[0], ToolCallPart)
    assert message.parts[0].approval_state == "pending"
    assert isinstance(message.parts[1], ToolResultPart)
    assert message.parts[1].tool_call_id == "call-1"

    dumped = message.model_dump(by_alias=True, exclude_none=True)
    assert dumped["parts"][0]["approvalState"] == "pending"
    assert dumped["parts"][1]["toolCallId"] == "call-1"


def test_tool_parts_default_to_no_approval_required() -> None:
    message = ChatMessage.model_validate(
        {
            "id": "assistant-1",
            "role": "assistant",
            "createdAt": "2026-06-01T00:00:00Z",
            "parts": [
                {
                    "type": "tool_call",
                    "id": "call-1",
                    "name": "web_search",
                }
            ],
        }
    )

    part = message.parts[0]
    assert isinstance(part, ToolCallPart)
    assert part.status == "pending"
    assert part.approval_state == "not_required"
