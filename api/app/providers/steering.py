"""Lightweight language-steering for real-provider requests.

The provider protocol has NO system prompt by design: the OpenAI(-compatible)
adapter deliberately sends only user/assistant roles (no system role) to keep
the o-series models happy (see `app/providers/openai.py`). A side effect is that
DeepSeek — a Chinese-trained model and our default real provider — defaults to
Chinese on short/ambiguous input (e.g. a bare English "Hello" comes back as a
Chinese greeting).

The fix is intentionally minimal: prefix one short instruction onto the CURRENT
user turn's content in the OUTGOING request to a real provider, steering it to
reply in the language of the message. Constraints this design upholds:

- NOT a system-prompt / protocol seam. The `Provider` protocol signatures are
  unchanged; this is a pure transformation of the outgoing request body.
- Applied to the current user turn ONLY — history messages (loaded from the DB)
  are forwarded verbatim, never steered.
- Never persisted. Conversation history in the DB is untouched; the steer lives
  only for the duration of the outgoing HTTP request.
- Deliberately NOT applied in the streaming handler. The `FakeProvider` test
  double keys its deterministic behavior off `user_text` (template selection by
  hash, and `FORCE_FALLBACK:` / `FORCE_ERROR:` / `FORCE_RATE_LIMIT:` magic-marker
  prefixes detected with `startswith`). Steering at the handler would shift those
  markers off the start of `user_text` and corrupt the fake's protocol, so the
  steer is applied INSIDE the real providers' `stream()` only.
- NOT applied to `complete()` (title autogen) — titles must stay clean.

The steer adds a handful of input tokens per real call. That cost is negligible
and is captured by the provider-reported usage, so no pricing adjustment is
needed.
"""

from __future__ import annotations

# One short line. Terse, robust, and worded so the model treats it as an
# instruction about the *following* message rather than content to echo back.
STEER_PREFIX = "[Reply in the same language as the message below.]\n\n"


def steer_user_text(user_text: str) -> str:
    """Return `user_text` with the language-steer instruction prefixed.

    Applied to the CURRENT user turn only, in the outgoing request to a real
    provider. The result is never persisted to conversation history.
    """
    return f"{STEER_PREFIX}{user_text}"
