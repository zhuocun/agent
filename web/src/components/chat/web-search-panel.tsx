"use client";

import { useState } from "react";
import { ChevronDown, Globe, Loader2 } from "lucide-react";

import { ToolPartView } from "@/components/chat/tool-part";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { WebSearchGroup } from "@/lib/tool-groups";

interface WebSearchPanelProps {
  group: WebSearchGroup;
  onDecision?: (d: { toolCallId: string; decision: "approve" | "deny" }) => void;
  /** When nested inside agent activity, drop the outer card chrome. */
  embedded?: boolean;
}

function formatSearchStatusLabel(
  label: string,
  state: "active" | "done",
): string {
  if (state !== "done") return label;
  if (label === "Searching the web…") return "Searched the web";
  return label;
}

function extractQueries(group: WebSearchGroup): string[] {
  return group.runs
    .map((run) => {
      const input = run.call?.input ?? run.result?.output;
      if (input && typeof input === "object" && !Array.isArray(input)) {
        const query = (input as Record<string, unknown>).query;
        if (typeof query === "string" && query.trim()) return query.trim();
      }
      return null;
    })
    .filter((query): query is string => query !== null);
}

function sourceCount(group: WebSearchGroup): number {
  let total = 0;
  for (const run of group.runs) {
    const output = run.result?.output;
    if (output && typeof output === "object" && !Array.isArray(output)) {
      const results = (output as Record<string, unknown>).results;
      if (Array.isArray(results)) total += results.length;
    }
  }
  return total;
}

function buildSummary(group: WebSearchGroup): string {
  const queryCount = group.runs.length;
  const queryNoun = queryCount === 1 ? "query" : "queries";
  const sources = sourceCount(group);
  const parts: string[] = [`${queryCount} ${queryNoun}`];
  if (sources > 0) {
    parts.push(`${sources} source${sources === 1 ? "" : "s"}`);
  }
  if (group.failedCount > 0) {
    parts.push(`${group.failedCount} failed`);
  }
  return parts.join(" · ");
}

export function WebSearchPanel({ group, onDecision, embedded = false }: WebSearchPanelProps) {
  const isLive =
    group.status === "running" ||
    group.status === "pending" ||
    group.statusPart?.state === "active";
  const statusLabel =
    isLive && group.statusPart
      ? formatSearchStatusLabel(
          group.statusPart.label,
          group.statusPart.state,
        )
      : null;
  const summary = buildSummary(group);
  const queries = extractQueries(group);
  const singleQueryLine =
    queries.length === 1 ? queries[0] : null;
  const triggerDetail = statusLabel ?? summary;
  // Live turns default open; settled turns default closed unless the user toggled.
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const open = userOpen ?? isLive;

  return (
    <div
      data-testid="web-search-panel"
      className={cn(
        "max-w-full text-sm text-muted-foreground",
        embedded
          ? "py-0.5"
          : "rounded-xl border border-foreground/[0.06] bg-foreground/[0.02] px-3 py-2.5",
      )}
    >
      <Collapsible open={open} onOpenChange={setUserOpen}>
        <CollapsibleTrigger
          data-testid="web-search-trigger"
          className={cn(
            "group/web-search-trigger flex w-full min-w-0 items-center gap-1.5 text-left",
            "min-h-11 bg-transparent py-2 -my-2 outline-none md:min-h-0 md:py-0 md:my-0",
            "focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
          )}
          aria-label={`Web search, ${summary} — toggle details`}
        >
          {isLive ? (
            <Loader2
              aria-hidden
              className="size-4 shrink-0 motion-safe:animate-spin"
            />
          ) : (
            <Globe aria-hidden className="size-4 shrink-0" />
          )}
          <span className="font-medium text-foreground">Web search</span>
          {triggerDetail ? (
            <span className="text-xs text-muted-foreground">{triggerDetail}</span>
          ) : null}
          <ChevronDown
            aria-hidden
            className="ml-auto size-3.5 shrink-0 transition-transform duration-300 ease-[var(--ease-ios-spring)] motion-reduce:transition-none group-data-[panel-open]/web-search-trigger:rotate-180"
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
          <div className="mt-1 space-y-1.5">
            {singleQueryLine && !isLive ? (
              <p className="text-xs leading-snug text-muted-foreground">
                <span className="font-medium text-foreground">Query:</span>{" "}
                {singleQueryLine}
              </p>
            ) : null}
            <ul className="flex flex-col gap-0.5">
              {group.runs.map((run, idx) => {
                const part = run.result ?? run.call;
                if (!part) return null;
                return (
                  <li key={`${run.id}-${idx}`} className="list-none">
                    <ToolPartView part={part} onDecision={onDecision} embedded={embedded} />
                  </li>
                );
              })}
            </ul>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
