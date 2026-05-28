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
import type { ReasoningEffort, ReasoningEffortId } from "@/lib/types";

export interface ReasoningEffortToggleProps {
  efforts: ReasoningEffort[];
  selectedId: ReasoningEffortId;
  onSelect: (id: ReasoningEffortId) => void;
  disabled?: boolean;
}

export function ReasoningEffortToggle({
  efforts,
  selectedId,
  onSelect,
  disabled,
}: ReasoningEffortToggleProps): JSX.Element {
  const selected = efforts.find((e) => e.id === selectedId) ?? efforts[0];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={disabled}
        render={
          <Button
            type="button"
            variant="ghost"
            className="inline-flex h-8 items-center gap-1 rounded-full bg-muted/60 px-2.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground [&_svg:not([class*='size-'])]:size-3.5"
            aria-label={
              selected
                ? `Reasoning effort: ${selected.label}. Change reasoning effort.`
                : "Change reasoning effort."
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
        {efforts.map((effort) => {
          const isSelected = effort.id === selectedId;
          return (
            <DropdownMenuItem
              key={effort.id}
              label={effort.label}
              onClick={() => onSelect(effort.id)}
              className="py-2"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{effort.label}</span>
                  {isSelected ? (
                    <Check
                      aria-hidden
                      className="ml-auto size-4 text-foreground"
                    />
                  ) : null}
                </div>
                <p className="mt-0.5 text-xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
                  {effort.description}
                </p>
              </div>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
