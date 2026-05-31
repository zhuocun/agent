import type { ModelTier, ModelTierId } from "@/lib/types";

// Capability tiers shown in the picker (PRD 06 §5.6) — never raw model IDs.
// Hints are sourced from the registry (PRD 02); values here are mock.
// Auto leads per PRD 02 FR-7 ("Auto" is the default for new users); its
// speed/cost/context hints are "auto" because the router resolves to a
// concrete tier per turn, and a single hint would mislead.
export const MODEL_TIERS: ModelTier[] = [
  {
    id: "auto",
    label: "Auto",
    description: "Match the right model to the question.",
    speedHint: "balanced",
    costHint: "medium",
    contextHint: "auto",
    modelLabel: "", // varies per message via the router
  },
  {
    id: "fast",
    label: "Fast",
    description: "Quick, low-cost answers for everyday questions.",
    speedHint: "fastest",
    costHint: "lowest",
    contextHint: "1M",
    modelLabel: "DeepSeek V4 Flash",
  },
  {
    id: "smart",
    label: "Smart",
    description: "Balanced reasoning and speed for most work.",
    speedHint: "balanced",
    costHint: "medium",
    contextHint: "1M",
    modelLabel: "DeepSeek V4 Flash",
  },
  {
    id: "pro",
    label: "Pro",
    description: "Maximum capability for hard, high-stakes tasks.",
    speedHint: "slow",
    costHint: "high",
    contextHint: "1M",
    modelLabel: "DeepSeek V4 Pro",
  },
];

export const MODEL_TIERS_BY_ID: Record<ModelTierId, ModelTier> = Object.fromEntries(
  MODEL_TIERS.map((t) => [t.id, t]),
) as Record<ModelTierId, ModelTier>;
