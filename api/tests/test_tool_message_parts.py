from __future__ import annotations

from app.schemas.message import ChatMessage, TextPart, ToolCallPart, ToolResultPart


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


def test_resumed_approve_message_parts_round_trip() -> None:
    """The NEW assistant row a resume→approve produces: [tool_result, text].

    Mirrors what the handler persists after a HITL approval — the seeded
    `tool_result` (approved / succeeded) followed by the post-tool answer text.
    """
    message = ChatMessage.model_validate(
        {
            "id": "assistant-2",
            "role": "assistant",
            "createdAt": "2026-06-01T00:00:05Z",
            "status": "done",
            "parts": [
                {
                    "type": "tool_result",
                    "toolCallId": "fake_cal_1",
                    "name": "calendar_create_event",
                    "label": "Create calendar event",
                    "status": "succeeded",
                    "approvalState": "approved",
                    "summary": "Created event: Planning review",
                    "output": {
                        "eventId": "evt_fake_cal_1",
                        "title": "Planning review",
                        "startsAt": "2026-06-02T09:00:00Z",
                    },
                },
                {"type": "text", "text": "…tool approved: the calendar event was created."},
            ],
        }
    )

    assert isinstance(message.parts[0], ToolResultPart)
    assert message.parts[0].status == "succeeded"
    assert message.parts[0].approval_state == "approved"
    assert isinstance(message.parts[1], TextPart)

    dumped = message.model_dump(by_alias=True, exclude_none=True)
    assert dumped["parts"][0]["approvalState"] == "approved"
    assert dumped["parts"][0]["output"]["eventId"] == "evt_fake_cal_1"


def test_resumed_deny_message_parts_round_trip() -> None:
    """The NEW assistant row a resume→deny produces: [tool_result(cancelled), text]."""
    message = ChatMessage.model_validate(
        {
            "id": "assistant-3",
            "role": "assistant",
            "createdAt": "2026-06-01T00:00:06Z",
            "status": "done",
            "parts": [
                {
                    "type": "tool_result",
                    "toolCallId": "fake_cal_1",
                    "name": "calendar_create_event",
                    "status": "cancelled",
                    "approvalState": "rejected",
                    "error": "User denied the tool call.",
                },
                {"type": "text", "text": "…tool denied: I did not create the calendar event."},
            ],
        }
    )

    assert isinstance(message.parts[0], ToolResultPart)
    assert message.parts[0].status == "cancelled"
    assert message.parts[0].approval_state == "rejected"
    dumped = message.model_dump(by_alias=True, exclude_none=True)
    assert dumped["parts"][0]["status"] == "cancelled"
    assert dumped["parts"][0]["approvalState"] == "rejected"


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
