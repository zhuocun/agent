"use client";

import type { ComponentType, JSX } from "react";
import {
  Check,
  ChevronDown,
  CircleDollarSign,
  Gauge,
  Maximize2,
  Sparkles,
  Wand2,
  Zap,
  type LucideProps,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { ModelTier, ModelTierId } from "@/lib/types";

export interface TierPickerProps {
  tiers: ModelTier[];
  selectedId: ModelTierId;
  onSelect: (id: ModelTierId) => void;
  disabled?: boolean;
}

// Per-tier glyph (PRD 06 §5.6 — capability tiers, never raw model IDs).
const TIER_ICON: Record<ModelTierId, ComponentType<LucideProps>> = {
  auto: Wand2,
  fast: Zap,
  smart: Gauge,
  pro: Sparkles,
};

// Human-readable mappings for the registry hint enums (PRD 02 sources the values).
const SPEED_LABEL: Record<ModelTier["speedHint"], string> = {
  fastest: "Fastest",
  fast: "Fast",
  balanced: "Balanced",
  slow: "Deliberate",
};

const COST_LABEL: Record<ModelTier["costHint"], string> = {
  lowest: "Lowest cost",
  low: "Low cost",
  medium: "Medium cost",
  high: "Highest cost",
};

function HintChip({
  icon: Icon,
  label,
  title,
  mono,
}: {
  icon: ComponentType<LucideProps>;
  label: string;
  title: string;
  mono?: boolean;
}) {
  return (
    <Badge
      variant="secondary"
      title={title}
      aria-label={title}
      className="gap-1 px-1.5 text-muted-foreground"
    >
      <Icon aria-hidden className="text-muted-foreground" />
      <span className={cn(mono && "font-mono")}>{label}</span>
    </Badge>
  );
}

export function TierPicker({ tiers, selectedId, onSelect, disabled }: TierPickerProps): JSX.Element {
  const selected = tiers.find((t) => t.id === selectedId) ?? tiers[0];
  const SelectedIcon = selected ? TIER_ICON[selected.id] : Wand2;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={disabled}
        render={
          <Button
            type="button"
            variant="ghost"
            size="sm"
            // >=40px touch target (PRD 03 / PRD 06 §3.3) while staying compact in the composer.
            className="min-h-10 gap-1.5 px-2.5 text-muted-foreground hover:text-foreground aria-expanded:text-foreground"
            // Conveys the current selection + the action to screen readers (PRD 01 §5.7).
            aria-label={
              selected
                ? `Model: ${selected.label}. Change model tier.`
                : "Change model tier."
            }
          >
            {SelectedIcon ? (
              <SelectedIcon
                aria-hidden
                className={cn(selected?.id === "auto" && "text-brand")}
              />
            ) : null}
            <span className="font-medium text-foreground">{selected?.label}</span>
            <ChevronDown aria-hidden className="text-muted-foreground" />
          </Button>
        }
      />
      <DropdownMenuContent
        align="start"
        sideOffset={8}
        className="w-72 max-w-[min(20rem,calc(100vw-1.5rem))]"
      >
        {tiers.map((tier) => {
          const Icon = TIER_ICON[tier.id];
          const isSelected = tier.id === selectedId;
          const isAuto = tier.id === "auto";

          return (
            <DropdownMenuItem
              key={tier.id}
              // Native text-nav uses the label, not the rich body (PRD 06 §5.6).
              label={tier.label}
              onClick={() => onSelect(tier.id)}
              className="items-start gap-2.5 py-2"
            >
              <span
                aria-hidden
                className={cn(
                  "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md",
                  isAuto
                    ? "bg-brand-muted text-brand"
                    : "bg-secondary text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground",
                )}
              >
                <Icon className="size-4" />
              </span>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{tier.label}</span>
                  {isAuto ? (
                    <span className="text-xs font-medium text-brand">
                      Recommended
                    </span>
                  ) : null}
                  {isSelected ? (
                    <Check
                      aria-hidden
                      className="ml-auto size-4 text-foreground"
                    />
                  ) : null}
                </div>

                <p className="mt-0.5 text-xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
                  {tier.description}
                </p>

                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <HintChip
                    icon={Zap}
                    label={SPEED_LABEL[tier.speedHint]}
                    title={`Speed: ${SPEED_LABEL[tier.speedHint]}`}
                  />
                  <HintChip
                    icon={CircleDollarSign}
                    label={COST_LABEL[tier.costHint]}
                    title={`Relative cost: ${COST_LABEL[tier.costHint]}`}
                  />
                  <HintChip
                    icon={Maximize2}
                    label={tier.contextHint}
                    title={`Context window: ${tier.contextHint}`}
                    mono
                  />
                </div>

                {isAuto ? (
                  <p className="mt-1.5 text-xs font-medium text-brand">
                    Routes each message for you.
                  </p>
                ) : null}
              </div>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
