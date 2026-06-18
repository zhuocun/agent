"use client";

import { ChevronDown, Wrench } from "lucide-react";

import { ToolPartView } from "@/components/chat/tool-part";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { ToolGroup } from "@/lib/tool-groups";

interface ToolGroupPanelProps {
  group: ToolGroup;
  // HITL passthrough, threaded to each run's `ToolPartView`. A group only ever
  // holds settled runs, so the approve/deny controls never actually render —
  // but the prop is forwarded to keep the renderer uniform with the flat path.
  onDecision?: (d: { toolCallId: string; decision: "approve" | "deny" }) => void;
}

// Aggregated, collapsed-by-default panel for a contiguous run of >=2 settled
// tool calls. Mirrors SubagentPanel's grammar — a quiet bordered card with a
// lucide header icon, a one-line summary, and progressive disclosure — but the
// WHOLE card collapses behind its summary (the runs carry no live state), with
// one `ToolPartView` per run inside. Reuses the collapsible primitive, the iOS
// easing tokens, the motion-reduce degrade, and the min-h-11 touch target from
// tool-part.tsx so the toggle reads identically.
export function ToolGroupPanel({ group, onDecision }: ToolGroupPanelProps) {
  const total = group.runs.length;
  const noun = total === 1 ? "call" : "calls";
  const summary =
    group.failedCount > 0
      ? `${total} ${noun} · ${group.failedCount} failed`
      : `${total} ${noun}`;

  return (
    <div
      data-testid="tool-group-panel"
      className="max-w-full rounded-xl border border-foreground/[0.06] bg-foreground/[0.02] px-3 py-2.5 text-sm text-muted-foreground"
    >
      <Collapsible>
        <CollapsibleTrigger
          data-testid="tool-group-trigger"
          className={cn(
            "group/tool-group-trigger flex w-full min-w-0 items-center gap-1.5 text-left",
            "min-h-11 bg-transparent py-2 -my-2 outline-none md:min-h-0 md:py-0 md:my-0",
            "focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
          )}
          aria-label={`Tools, ${summary} — toggle details`}
        >
          <Wrench aria-hidden className="size-4 shrink-0" />
          <span className="font-medium text-foreground">Tools</span>
          <span className="text-xs text-muted-foreground">{summary}</span>
          <ChevronDown
            aria-hidden
            className="ml-auto size-3.5 shrink-0 transition-transform duration-300 ease-[var(--ease-ios-spring)] motion-reduce:transition-none group-data-[panel-open]/tool-group-trigger:rotate-180"
          />
        </CollapsibleTrigger>
        <CollapsibleContent
          keepMounted
          className={cn(
            "overflow-hidden",
            "transition-[height,opacity] duration-200 ease-[var(--ease-ios-smooth)]",
            "h-[var(--collapsible-panel-height)] opacity-100",
            "data-[starting-style]:h-0 data-[starting-style]:opacity-0",
            "data-[ending-style]:h-0 data-[ending-style]:opacity-0",
          )}
        >
          <ul className="mt-2 flex flex-col gap-1.5">
            {group.runs.map((run, idx) => {
              // Prefer the result part (it carries the terminal outcome +
              // summary); fall back to the call when a run has no result.
              const part = run.result ?? run.call;
              if (!part) return null;
              return (
                <li key={`${run.id}-${idx}`} className="list-none">
                  <ToolPartView part={part} onDecision={onDecision} />
                </li>
              );
            })}
          </ul>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
