"use client";

import type { JSX } from "react";
import { Check, ChevronDown } from "lucide-react";

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
          <button
            type="button"
            aria-label={`Model: ${tier?.label}, reasoning effort ${effort?.label}. Open picker.`}
            className="inline-flex h-9 items-center gap-1.5 rounded-full px-2.5 text-sm outline-none transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring aria-expanded:bg-muted/60"
          >
            <span className="font-medium text-foreground">{tier?.label}</span>
            <span className="text-muted-foreground">{effort?.label}</span>
            <ChevronDown aria-hidden className="size-3.5 text-muted-foreground" />
          </button>
        }
      />
      <DropdownMenuContent
        align="start"
        sideOffset={8}
        className="w-72 max-w-[min(20rem,calc(100vw-1.5rem))] rounded-2xl"
      >
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-[10px] tracking-wider uppercase">
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
          <DropdownMenuLabel className="text-[10px] tracking-wider uppercase">
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
