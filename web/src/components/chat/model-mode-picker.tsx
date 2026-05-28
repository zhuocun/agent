"use client";

import type { JSX } from "react";
import { Check, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ModelTier, ModelTierId } from "@/lib/types";

export interface ModelModePickerProps {
  tiers: ModelTier[];
  selectedTierId: ModelTierId;
  onSelectTier: (id: ModelTierId) => void;
  disabled?: boolean;
}

export function ModelModePicker({
  tiers,
  selectedTierId,
  onSelectTier,
  disabled,
}: ModelModePickerProps): JSX.Element {
  const tier = tiers.find((t) => t.id === selectedTierId) ?? tiers[0];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={disabled}
        render={
          <Button
            type="button"
            variant="ghost"
            aria-label={`Model: ${tier?.label}. Open picker.`}
            className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-muted/60 p-0 text-muted-foreground hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground"
          >
            <Sparkles aria-hidden className="size-4" />
          </Button>
        }
      />
      <DropdownMenuContent
        align="start"
        sideOffset={8}
        className="w-72 max-w-[min(20rem,calc(100vw-1.5rem))] rounded-2xl"
      >
        {tiers.map((t) => (
          <Row
            key={t.id}
            label={t.label}
            description={t.description}
            selected={t.id === selectedTierId}
            onSelect={() => onSelectTier(t.id)}
          />
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Row({
  label,
  description,
  selected,
  onSelect,
}: {
  label: string;
  description: string;
  selected: boolean;
  onSelect: () => void;
}): JSX.Element {
  return (
    <DropdownMenuItem label={label} onClick={onSelect} className="py-2">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">{label}</span>
          {selected ? (
            <Check aria-hidden className="ml-auto size-4 text-foreground" />
          ) : null}
        </div>
        <p className="mt-0.5 text-xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
          {description}
        </p>
      </div>
    </DropdownMenuItem>
  );
}
