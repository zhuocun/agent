// Pre-send cost & token estimate (Feature 2). Pure, FE-only — pricing now ships
// in bootstrap on each `ModelTier` (listPriceInPerM / listPriceOutPerM), so the
// composer can show the user roughly what the next turn will cost BEFORE they
// send it (the transparency wedge: "higher reasoning / bigger context ⇒ more").
//
// This is deliberately APPROXIMATE: token counts are a chars/4 heuristic, not a
// real tokenizer (we don't ship a BPE model to the client). The composer labels
// the line as an estimate; the exact charge lands in the post-turn attribution.

import type { AttachmentPart, ModelTier } from "@/lib/types";

// Rough chars-per-token ratio for English-ish text. The real tokenizer varies
// by model, but chars/4 is the standard back-of-envelope figure and is good
// enough for an order-of-magnitude pre-send hint.
const CHARS_PER_TOKEN = 4;

// Flat token cost we attribute to each image attachment. Real vision token
// accounting is tile-based and model-specific; a single conservative constant
// keeps the estimate honest-but-simple (images push the number up without
// pretending to be exact).
const TOKENS_PER_IMAGE = 1_000;

// Assumed output length (in tokens) for the estimate. The real answer length is
// unknown pre-send, so we assume a modest, typical reply. Documented so the
// number is reproducible rather than magic.
const ASSUMED_OUTPUT_TOKENS = 400;

export interface CostEstimateInput {
  text: string;
  attachments?: AttachmentPart[];
  // Tokens already in the conversation history that ride along as input on this
  // turn. Optional — callers that don't track it pass 0 (the composer does).
  historyTokens?: number;
  tier: Pick<ModelTier, "listPriceInPerM" | "listPriceOutPerM">;
}

export interface CostEstimate {
  // Estimated INPUT tokens for this turn (prompt + attachments + history). The
  // composer can surface this as the "~N tokens" half of the hint.
  tokens: number;
  // Estimated USD for the turn, or `null` when the tier has no usable price
  // (Auto, or a binding missing pricing) — the caller shows "estimate
  // unavailable" rather than a misleading "$0.00".
  usd: number | null;
}

// Approximate the input-token count for a turn. chars/4 for the prompt text and
// any text/PDF attachments (their bytes stand in for transcript length), plus a
// flat per-image constant. Plus any passed-in history tokens.
function estimateInputTokens(input: CostEstimateInput): number {
  const textTokens = Math.ceil(input.text.length / CHARS_PER_TOKEN);
  let attachmentTokens = 0;
  for (const attachment of input.attachments ?? []) {
    if (attachment.mediaType === "image") {
      attachmentTokens += TOKENS_PER_IMAGE;
    } else {
      // text / pdf: bytes are a reasonable proxy for transcript length.
      attachmentTokens += Math.ceil(attachment.sizeBytes / CHARS_PER_TOKEN);
    }
  }
  const historyTokens = Math.max(0, Math.floor(input.historyTokens ?? 0));
  return textTokens + attachmentTokens + historyTokens;
}

/**
 * Estimate the token + USD cost of the next turn for a given tier.
 *
 * Token counts are APPROXIMATE (chars/4). `usd` is `null` when the tier carries
 * no usable input price (Auto resolves its model per turn, so it has price 0;
 * an unpriced binding is treated the same) — callers must render "estimate
 * unavailable for Auto" in that case, never "$0.00".
 */
export function estimateTurnCost(input: CostEstimateInput): CostEstimate {
  const tokens = estimateInputTokens(input);
  const { listPriceInPerM, listPriceOutPerM } = input.tier;

  // Auto / missing binding: no single price, so no honest dollar figure.
  if (!listPriceInPerM) {
    return { tokens, usd: null };
  }

  const inputUsd = (tokens * listPriceInPerM) / 1e6;
  const outputUsd = (ASSUMED_OUTPUT_TOKENS * listPriceOutPerM) / 1e6;
  return { tokens, usd: inputUsd + outputUsd };
}
