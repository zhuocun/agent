"use client";

import type { ComponentType, JSX } from "react";
import {
  Brain,
  Check,
  ChevronDown,
  Gauge,
  Sparkles,
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
import type {
  ReasoningEffort,
  ReasoningEffortId,
} from "@/lib/types";

export interface ReasoningEffortToggleProps {
  efforts: ReasoningEffort[];
  selectedId: ReasoningEffortId;
  onSelect: (id: ReasoningEffortId) => void;
  disabled?: boolean;
}

const EFFORT_ICON: Record<ReasoningEffortId, ComponentType<LucideProps>> = {
  auto: Sparkles,
  minimal: Zap,
  standard: Gauge,
  extended: Brain,
};

// 0 = auto (rendered as a dash chip — no level), 1..3 = filled dot count.
// Keeps the visualisation honest: "auto" doesn't claim a position on the
// cost/latency scale, it defers to the app.
const COST_LEVEL: Record<ReasoningEffort["costHint"], number> = {
  auto: 0,
  lowest: 1,
  low: 1,
  medium: 2,
  high: 3,
};

const LATENCY_LEVEL: Record<ReasoningEffort["latencyHint"], number> = {
  auto: 0,
  fastest: 1,
  fast: 1,
  balanced: 2,
  slow: 3,
};

// Cost rises with the level; latency *worsens* with the level (more dots = slower).
// We share the dot bar but colour the filled dots brand-accented so the user reads
// the row as "this many dots' worth of cost / slowness" — not a green-good gauge.
function HintBar({
  label,
  level,
}: {
  label: string;
  level: number;
}): JSX.Element {
  if (level === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
        <span className="font-medium">{label}:</span>
        <span aria-hidden>—</span>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
      <span className="font-medium">{label}:</span>
      <span aria-hidden className="inline-flex items-center gap-0.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={cn(
              "size-1.5 rounded-full",
              i < level ? "bg-foreground/70" : "bg-foreground/15",
            )}
          />
        ))}
      </span>
    </span>
  );
}

function describeHint(hint: ReasoningEffort["costHint"] | ReasoningEffort["latencyHint"]): string {
  // Used only for the trigger's aria-label / SR text — the visual is the dot bar.
  switch (hint) {
    case "auto":
      return "auto";
    case "lowest":
      return "lowest";
    case "low":
      return "low";
    case "medium":
      return "medium";
    case "high":
      return "high";
    case "fastest":
      return "fastest";
    case "fast":
      return "fast";
    case "balanced":
      return "balanced";
    case "slow":
      return "slow";
  }
}

export function ReasoningEffortToggle({
  efforts,
  selectedId,
  onSelect,
  disabled,
}: ReasoningEffortToggleProps): JSX.Element {
  const selected = efforts.find((e) => e.id === selectedId) ?? efforts[0];
  const SelectedIcon = selected ? EFFORT_ICON[selected.id] : Sparkles;

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
                ? `Change reasoning effort. Currently: ${selected.label}.`
                : "Change reasoning effort."
            }
            title={
              selected
                ? `Change reasoning effort. Currently: ${selected.label}.`
                : "Change reasoning effort."
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
        className="w-80 max-w-[min(22rem,calc(100vw-1.5rem))] rounded-2xl"
      >
        {efforts.map((effort) => {
          const Icon = EFFORT_ICON[effort.id];
          const isSelected = effort.id === selectedId;
          const isAuto = effort.id === "auto";

          return (
            <DropdownMenuItem
              key={effort.id}
              label={effort.label}
              onClick={() => onSelect(effort.id)}
              className="items-start gap-2.5 py-2"
              aria-label={
                isAuto
                  ? `${effort.label}. ${effort.description}.`
                  : `${effort.label}. ${effort.description}. Cost ${describeHint(effort.costHint)}, latency ${describeHint(effort.latencyHint)}.`
              }
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
                  <span className="font-medium">{effort.label}</span>
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
                  {effort.description}
                </p>

                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <HintBar label="Cost" level={COST_LEVEL[effort.costHint]} />
                  <HintBar label="Latency" level={LATENCY_LEVEL[effort.latencyHint]} />
                </div>
              </div>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
