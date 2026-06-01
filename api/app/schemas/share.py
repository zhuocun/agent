"""Public-by-link share wire shapes (cost-stripped).

PRD 01 §4.10 / PRD 05 §4.3 / PRD 07 §6.4: a public-by-link conversation view
shows the messages and the MODEL ATTRIBUTION but HIDES per-message cost. This
is the explicit exception to the normal cost-transparency surface — anyone with
the link can read the conversation, so the per-turn cost ledger must never
leak.

These schemas are NOT a filtered view over `ChatMessage` / `ModelAttribution`
— they are a separate, deliberately narrow shape that simply has nowhere to put
a cost field. That makes the strip a structural guarantee (the field can't be
serialized because it doesn't exist on the model) rather than a runtime filter
that a future refactor could silently undo.

KEEP (model identity / attribution):
- `requestedTierId`, `servedTierId`  — what the user asked for vs what ran
- `servedModelLabel`                 — the concrete model name
- `isByok`                           — whether the owner used their own key
- `substitution` (reasonCode/reasonText) — why a different tier/model served

STRIP (everything cost / usage / pricing):
- `costUsd`, `costConfidence`
- the entire `breakdown` block: `listPrice*`, `subtotalUsd`,
  `sessionSurchargeUsd`, `inputTokens`, `outputTokens`, `reasoningTokens`,
  `cachedInputTokens`, `longContext`, `promoApplied`, `currency`

Token COUNTS without prices are a judgment call; PRD says "no per-message cost",
so we strip the whole usage/cost breakdown to be safe and keep only model
identity.
"""

from __future__ import annotations

from app.schemas.common import CamelModel, MessageRole, ModelTierId
from app.schemas.message import MessagePart, Substitution


class PublicAttribution(CamelModel):
    """Cost-stripped model attribution. Model identity only, never cost."""

    requested_tier_id: ModelTierId
    served_tier_id: ModelTierId
    served_model_label: str
    provider_id: str | None = None
    provider_label: str | None = None
    is_byok: bool
    substitution: Substitution | None = None


class PublicMessage(CamelModel):
    """A single message in the public share view. No `feedback`, no cost."""

    id: str
    role: MessageRole
    parts: list[MessagePart]
    created_at: str
    attribution: PublicAttribution | None = None


class PublicConversation(CamelModel):
    """The public-by-link conversation snapshot. No `selectedTierId` (it's an
    owner-side affordance) and no per-message cost anywhere."""

    id: str
    title: str
    messages: list[PublicMessage]


class ShareLinkResponse(CamelModel):
    """Owner-side response from minting a share link.

    Carries the raw `shareToken` plus a relative `sharePath` the FE can join to
    its own origin (`/share/{token}`). The BE deliberately does NOT emit an
    absolute URL — it doesn't know the public FE origin (it sits behind the
    Next.js `/api/*` rewrite), so the FE owns URL assembly.
    """

    share_token: str
    share_path: str
