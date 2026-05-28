import type { ModelTier, ModelTierId } from "@/lib/types";

// Capability tiers shown in the picker (PRD 06 §5.6) — never raw model IDs.
// Hints are sourced from the registry (PRD 02); values here are mock.
export const MODEL_TIERS: ModelTier[] = [
  {
    id: "fast",
    label: "Fast",
    description: "Quick, low-cost answers for everyday questions.",
    speedHint: "fastest",
    costHint: "lowest",
    contextHint: "128K",
  },
  {
    id: "smart",
    label: "Smart",
    description: "Balanced reasoning and speed for most work.",
    speedHint: "balanced",
    costHint: "medium",
    contextHint: "200K",
  },
  {
    id: "pro",
    label: "Pro",
    description: "Maximum capability for hard, high-stakes tasks.",
    speedHint: "slow",
    costHint: "high",
    contextHint: "1M",
  },
];

export const MODEL_TIERS_BY_ID: Record<ModelTierId, ModelTier> = Object.fromEntries(
  MODEL_TIERS.map((t) => [t.id, t]),
) as Record<ModelTierId, ModelTier>;
