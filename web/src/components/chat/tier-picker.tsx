"use client";

import type { ComponentType, JSX } from "react";
import {
  Check,
  ChevronDown,
  Gauge,
  Sparkles,
  Wand2,
  Zap,
  type LucideProps,
} from "lucide-react";

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

const TIER_ICON: Record<ModelTierId, ComponentType<LucideProps>> = {
  auto: Wand2,
  fast: Zap,
  smart: Gauge,
  pro: Sparkles,
};

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
            className="inline-flex h-8 items-center gap-1.5 rounded-full bg-muted/60 px-2.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground [&_svg:not([class*='size-'])]:size-3.5"
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
        className="w-72 max-w-[min(20rem,calc(100vw-1.5rem))] rounded-2xl"
      >
        {tiers.map((tier) => {
          const Icon = TIER_ICON[tier.id];
          const isSelected = tier.id === selectedId;
          const isAuto = tier.id === "auto";

          return (
            <DropdownMenuItem
              key={tier.id}
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
              </div>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
