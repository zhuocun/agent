"use client";

import type { JSX } from "react";
import { Check, ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ModelTier, ModelTierId } from "@/lib/types";

export interface TierPickerProps {
  tiers: ModelTier[];
  selectedId: ModelTierId;
  onSelect: (id: ModelTierId) => void;
  disabled?: boolean;
}

export function TierPicker({ tiers, selectedId, onSelect, disabled }: TierPickerProps): JSX.Element {
  const selected = tiers.find((t) => t.id === selectedId) ?? tiers[0];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={disabled}
        render={
          <Button
            type="button"
            variant="ghost"
            className="inline-flex h-11 items-center gap-1 rounded-full bg-muted/60 px-3 text-xs text-muted-foreground hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground [&_svg:not([class*='size-'])]:size-3.5"
            aria-label={
              selected
                ? `Model: ${selected.label}. Change model tier.`
                : "Change model tier."
            }
          >
            <span className="font-medium text-foreground">{selected?.label}</span>
            <ChevronDown aria-hidden className="text-muted-foreground" />
          </Button>
        }
      />
      <DropdownMenuContent
        align="start"
        sideOffset={8}
        className="w-64 max-w-[min(18rem,calc(100vw-1.5rem))] rounded-2xl"
      >
        {tiers.map((tier) => {
          const isSelected = tier.id === selectedId;
          return (
            <DropdownMenuItem
              key={tier.id}
              label={tier.label}
              onClick={() => onSelect(tier.id)}
              className="py-2"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{tier.label}</span>
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
