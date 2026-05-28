"use client";

import type { JSX } from "react";
import { Check, ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type {
  ModelTier,
  ModelTierId,
  ReasoningEffort,
  ReasoningEffortId,
} from "@/lib/types";

export interface ModelModePickerProps {
  tiers: ModelTier[];
  selectedTierId: ModelTierId;
  onSelectTier: (id: ModelTierId) => void;
  efforts: ReasoningEffort[];
  selectedEffortId: ReasoningEffortId;
  onSelectEffort: (id: ReasoningEffortId) => void;
  disabled?: boolean;
}

export function ModelModePicker({
  tiers,
  selectedTierId,
  onSelectTier,
  efforts,
  selectedEffortId,
  onSelectEffort,
  disabled,
}: ModelModePickerProps): JSX.Element {
  const tier = tiers.find((t) => t.id === selectedTierId) ?? tiers[0];
  const effort = efforts.find((e) => e.id === selectedEffortId) ?? efforts[0];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={disabled}
        render={
          <Button
            type="button"
            variant="ghost"
            className="inline-flex h-8 items-center gap-1.5 rounded-full bg-muted/60 px-2.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground [&_svg:not([class*='size-'])]:size-3.5"
            aria-label={`Model and reasoning effort. Currently ${tier?.label} model, ${effort?.label} effort. Open picker.`}
          >
            <span className="font-medium text-foreground">{tier?.label}</span>
            <span aria-hidden className="text-muted-foreground/70">·</span>
            <span className="font-medium text-foreground">{effort?.label}</span>
            <ChevronDown aria-hidden className="text-muted-foreground" />
          </Button>
        }
      />
      <DropdownMenuContent
        align="start"
        sideOffset={8}
        className="w-72 max-w-[min(20rem,calc(100vw-1.5rem))] rounded-2xl"
      >
        <DropdownMenuGroup>
          <DropdownMenuLabel className="px-2 pt-1 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Model
          </DropdownMenuLabel>
          {tiers.map((t) => (
            <Row
              key={t.id}
              label={t.label}
              description={t.description}
              selected={t.id === selectedTierId}
              onSelect={() => onSelectTier(t.id)}
            />
          ))}
        </DropdownMenuGroup>

        <DropdownMenuSeparator />

        <DropdownMenuGroup>
          <DropdownMenuLabel className="px-2 pt-1 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Reasoning effort
          </DropdownMenuLabel>
          {efforts.map((e) => (
            <Row
              key={e.id}
              label={e.label}
              description={e.description}
              selected={e.id === selectedEffortId}
              onSelect={() => onSelectEffort(e.id)}
            />
          ))}
        </DropdownMenuGroup>
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
