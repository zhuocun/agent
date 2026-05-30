"""OpenAI(-compatible) Chat Completions adapter.

Maps `client.chat.completions.create(..., stream=True)` chunks to our internal
`ProviderEvent`s. Mirrors `anthropic.py` in shape, streaming contract, usage
accounting, and error mapping so the rest of the system stays provider-agnostic.

Notable differences from the Anthropic adapter:

- Reasoning-text streaming is path-dependent. Stock OpenAI Chat Completions does
  NOT stream the model's reasoning content; it only reports `reasoning_tokens` in
  usage. DeepSeek's OpenAI-compatible endpoint, however, DOES surface the
  chain-of-thought as a separate `delta.reasoning_content` field, which we now
  forward as `ReasoningDelta`/`ReasoningDone`. The field is absent/None on stock
  OpenAI (and o-series) responses, so reading it is a safe no-op there (zero
  reasoning events is a legal stream per the Provider Protocol). Either way,
  reasoning is billed at the output rate via the usage buckets below.

- Disjoint usage buckets (THE correctness detail). `pricing.compute_cost_breakdown`
  sums FOUR buckets independently:
      input*in + output*out + reasoning*out + cached_input*cache
  so the buckets MUST be disjoint or we double-bill. OpenAI's usage is NOT
  disjoint: `prompt_tokens` INCLUDES `prompt_tokens_details.cached_tokens`, and
  `completion_tokens` INCLUDES `completion_tokens_details.reasoning_tokens`.
  We therefore subtract the overlaps:
      cached_input_tokens = cached_tokens
      input_tokens        = max(prompt_tokens - cached_tokens, 0)
      reasoning_tokens     = reasoning_tokens
      output_tokens        = max(completion_tokens - reasoning_tokens, 0)

- `stream_options={"include_usage": True}` is REQUIRED to get a usage object on
  a streaming call — it arrives in the final chunk (which carries empty
  `choices`). Some OpenAI-compatible endpoints ignore it; we then leave all
  buckets at 0.

- `max_completion_tokens` (NOT `max_tokens`). The o-series models (the `pro`
  default `o1`) reject the legacy `max_tokens` parameter.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

import openai
from openai import AsyncOpenAI

from app.errors import AppError, ErrorEnvelope
from app.providers.protocol import (
    AnswerDelta,
    ChatMessage,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    ReasoningDone,
    UsageUpdate,
)
from app.providers.steering import steer_user_text


def _safe_int(value: Any) -> int:
    """Coerce SDK usage fields (often `int | None`) to int."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _retry_after_ms(exc: openai.RateLimitError) -> int | None:
    """Best-effort `retryAfterMs` from a rate-limit response's headers.

    Mirrors the SDK's own precedence: the non-standard millisecond header
    `retry-after-ms` wins, else integer/float `retry-after` seconds. Returns
    None when neither header is present or parseable.
    """
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None:
        return None
    ms_header = headers.get("retry-after-ms")
    if ms_header is not None:
        try:
            return int(float(ms_header))
        except (TypeError, ValueError):
            pass
    sec_header = headers.get("retry-after")
    if sec_header is not None:
        try:
            return int(float(sec_header) * 1000)
        except (TypeError, ValueError):
            pass
    return None


def _map_sdk_error(exc: openai.APIError) -> AppError:
    """Translate an OpenAI SDK error into a typed `AppError`.

    Rate limits become `RATE_LIMITED` (429) with `retryAfterMs` when the
    upstream response carries a retry-after header; everything else becomes
    `PROVIDER_UPSTREAM` (502, or 503 for explicit unavailability/overload). The
    raw SDK message is never placed in the user-facing `body` — only a clean
    generic string. The original exception is left for the caller to log.

    Note: `openai.APIConnectionError` is an `APIError` but NOT an
    `APIStatusError` (it has no `.status_code`); the isinstance guard below
    keeps it at 502.
    """
    if isinstance(exc, openai.RateLimitError):
        return AppError(
            ErrorEnvelope(
                code="RATE_LIMITED",
                severity="error",
                title="Rate limited",
                body="The model provider is rate-limiting requests. Please retry shortly.",
                retry_after_ms=_retry_after_ms(exc),
            ),
            status_code=429,
        )
    # 503/529 mean the upstream is unavailable/overloaded; surface as 503 so the
    # client can treat it as transient. All other upstream failures are 502.
    status_code = 502
    if isinstance(exc, openai.APIStatusError) and exc.status_code in (503, 529):
        status_code = 503
    return AppError(
        ErrorEnvelope(
            code="PROVIDER_UPSTREAM",
            severity="error",
            title="Provider error",
            body="The model provider returned an error. Please try again.",
        ),
        status_code=status_code,
    )


class OpenAIProvider:
    """Adapter over `openai.AsyncOpenAI.chat.completions.create(...)`.

    Holds a default client built from the platform key + configured base URL.
    Per-request BYOK overrides build a fresh `AsyncOpenAI(api_key=...)` on the
    same base URL (the SDK is cheap to construct -- HTTP session is lazy). This
    keeps the default fast path identical while making BYOK opt-in per call.
    """

    def __init__(self, api_key: str, base_url: str | None = None, max_tokens: int = 16000):
        self._default_api_key = api_key
        self._base_url = base_url
        self._max_tokens = max_tokens
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def _client_for(self, api_key: str | None) -> AsyncOpenAI:
        """Return the default client, or a fresh one bound to `api_key`.

        The default client is reused across requests for connection pooling;
        BYOK clients are throwaway and rely on the SDK's own connection
        management for that single call. BYOK keeps the same base URL.
        """
        if api_key is None or api_key == self._default_api_key:
            return self._client
        return AsyncOpenAI(api_key=api_key, base_url=self._base_url)

    async def stream(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
        thinking: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        # Build messages: history + the current user turn. Only user/assistant
        # roles (no system role), which keeps o-series models happy.
        messages: list[dict[str, Any]] = [{"role": m.role, "content": m.text} for m in history]
        # Steer ONLY the current user turn (real-provider, outgoing request,
        # never persisted). History stays verbatim. See app/providers/steering.py.
        messages.append({"role": "user", "content": steer_user_text(user_text)})

        # Optional provider hints, built CONDITIONALLY so we never send a
        # `reasoning_effort=None` or an empty `extra_body` to stock OpenAI.
        # `thinking` maps to DeepSeek V4's dual-mode toggle via `extra_body`;
        # `reasoning_effort` is the DeepSeek effort level ("high"/"max").
        kwargs: dict[str, Any] = {}
        if reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort
        if thinking is not None:
            kwargs["extra_body"] = {
                "thinking": {"type": "enabled" if thinking else "disabled"}
            }

        client = self._client_for(api_key)
        usage_obj: Any = None
        # Reasoning-event invariant (DeepSeek's `delta.reasoning_content`): emit
        # at most one ReasoningDone, only after >=1 ReasoningDelta, and before any
        # AnswerDelta. Stock OpenAI never sends `reasoning_content`, so these stay
        # False and no reasoning events are emitted.
        reasoning_seen = False
        reasoning_done_sent = False
        try:
            stream = await client.chat.completions.create(
                model=model_id,
                messages=cast(Any, messages),
                # o-series models reject `max_tokens`; use `max_completion_tokens`.
                max_completion_tokens=self._max_tokens,
                stream=True,
                # REQUIRED to get usage on a streaming call -- it rides the final
                # chunk (which has empty `choices`).
                stream_options={"include_usage": True},
                **kwargs,
            )
            async for chunk in stream:
                # Usage arrives on the final chunk; capture from any chunk that
                # carries it (some compat endpoints place it differently).
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    usage_obj = chunk_usage
                for choice in getattr(chunk, "choices", None) or []:
                    delta = getattr(choice, "delta", None)
                    # DeepSeek streams chain-of-thought separately on
                    # `delta.reasoning_content` (absent/None on stock OpenAI).
                    rc = getattr(delta, "reasoning_content", None)
                    if rc:
                        yield ReasoningDelta(text=rc)
                        reasoning_seen = True
                    content = getattr(delta, "content", None)
                    if content:
                        # Close the reasoning block exactly once, just before the
                        # first answer text follows it.
                        if reasoning_seen and not reasoning_done_sent:
                            yield ReasoningDone()
                            reasoning_done_sent = True
                        yield AnswerDelta(text=content)
        except openai.APIError as exc:
            raise _map_sdk_error(exc) from exc

        # Compute the four DISJOINT buckets. OpenAI usage overlaps:
        #   prompt_tokens     includes prompt_tokens_details.cached_tokens
        #   completion_tokens includes completion_tokens_details.reasoning_tokens
        # so we subtract the overlaps to avoid double-billing (pricing sums the
        # four buckets independently). `usage_obj is None` (compat endpoint that
        # ignored stream_options) leaves everything at 0.
        prompt_tokens = _safe_int(getattr(usage_obj, "prompt_tokens", None))
        completion_tokens = _safe_int(getattr(usage_obj, "completion_tokens", None))
        prompt_details = getattr(usage_obj, "prompt_tokens_details", None)
        completion_details = getattr(usage_obj, "completion_tokens_details", None)
        # Clamp at read: cached/reasoning flow straight into UsageUpdate, so a
        # non-conformant endpoint reporting a negative must not produce a
        # negative cost. (input/output are already clamped via the subtraction.)
        cached_input_tokens = max(_safe_int(getattr(prompt_details, "cached_tokens", None)), 0)
        # DeepSeek reports cache hits at the TOP LEVEL as `prompt_cache_hit_tokens`
        # (not under `prompt_tokens_details.cached_tokens`), so fall back to it
        # when the standard nested field is absent/zero — otherwise DeepSeek cache
        # discounts would never apply.
        if cached_input_tokens == 0:
            cached_input_tokens = max(
                _safe_int(getattr(usage_obj, "prompt_cache_hit_tokens", None)), 0
            )
        reasoning_tokens = max(_safe_int(getattr(completion_details, "reasoning_tokens", None)), 0)
        input_tokens = max(prompt_tokens - cached_input_tokens, 0)
        output_tokens = max(completion_tokens - reasoning_tokens, 0)

        usage_update = UsageUpdate(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens,
        )
        yield usage_update
        yield Complete(usage=usage_update)

    async def complete(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
    ) -> str:
        """Non-streaming variant. One `chat.completions.create` call, text out.

        Used by title autogen — small/fast tier, short max tokens. Returns the
        first choice's message content stripped. Returns empty string on a
        response without a choice / text (defensive — the caller swallows empty
        titles).
        """
        messages: list[dict[str, Any]] = [{"role": m.role, "content": m.text} for m in history]
        messages.append({"role": "user", "content": user_text})

        client = self._client_for(api_key)
        try:
            response = await client.chat.completions.create(
                model=model_id,
                messages=cast(Any, messages),
                # Title-autogen calls are short; cap output tokens tightly at 64.
                max_completion_tokens=64,
            )
        except openai.APIError as exc:
            raise _map_sdk_error(exc) from exc
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        content = getattr(choices[0].message, "content", None)
        return content.strip() if isinstance(content, str) else ""
