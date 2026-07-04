"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown, CircleDashed, Globe, Loader2, Search, ShieldQuestion } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { ToolRun, WebSearchGroup } from "@/lib/tool-groups";

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

function extractRunQuery(run: ToolRun): string | null {
  const callInput = run.call?.input;
  if (callInput && typeof callInput === "object" && !Array.isArray(callInput)) {
    const query = (callInput as Record<string, unknown>).query;
    if (typeof query === "string" && query.trim()) return query.trim();
  }
  const resultOutput = run.result?.output;
  if (
    resultOutput &&
    typeof resultOutput === "object" &&
    !Array.isArray(resultOutput)
  ) {
    const query = (resultOutput as Record<string, unknown>).query;
    if (typeof query === "string" && query.trim()) return query.trim();
  }
  return null;
}

function extractRunSourceCount(run: ToolRun): number | null {
  const output = run.result?.output;
  if (output && typeof output === "object" && !Array.isArray(output)) {
    const results = (output as Record<string, unknown>).results;
    if (Array.isArray(results)) return results.length;
  }
  const summary = run.result?.summary;
  if (summary) {
    const match = /^(\d+)\s+sources?$/.exec(summary);
    if (match) return Number(match[1]);
  }
  return null;
}

function WebSearchRunRow({ run }: { run: ToolRun }) {
  const query =
    extractRunQuery(run) ??
    run.call?.label ??
    run.result?.label ??
    "Web search";
  const sourceCount = extractRunSourceCount(run);
  const status = run.status;

  let icon: ReactNode;
  let statusSuffix: ReactNode = null;
  let errorLine: ReactNode = null;
  let showSourceCount = false;

  switch (status) {
    case "pending":
    case "running":
      icon = (
        <Loader2
          aria-hidden
          className="mt-0.5 size-3.5 shrink-0 motion-safe:animate-spin"
        />
      );
      statusSuffix = <span> · searching…</span>;
      break;
    case "awaiting_approval":
      icon = (
        <ShieldQuestion
          aria-hidden
          className="mt-0.5 size-3.5 shrink-0 text-warning"
        />
      );
      statusSuffix = <span> · awaiting approval</span>;
      break;
    case "succeeded":
      icon = <Search aria-hidden className="mt-0.5 size-3.5 shrink-0" />;
      showSourceCount = true;
      break;
    case "failed":
      icon = <Search aria-hidden className="mt-0.5 size-3.5 shrink-0" />;
      errorLine = (
        <p className="mt-0.5 text-destructive/80">
          {run.result?.error ?? "Search failed"}
        </p>
      );
      break;
    case "cancelled":
      icon = <CircleDashed aria-hidden className="mt-0.5 size-3.5 shrink-0" />;
      statusSuffix = (
        <span className="text-muted-foreground/70"> · cancelled</span>
      );
      break;
    default: {
      const _exhaustive: never = status;
      return _exhaustive;
    }
  }

  return (
    <li data-testid="web-search-run" className="list-none">
      <div className="flex min-w-0 items-start gap-1.5 ui-caption leading-snug text-muted-foreground">
        {icon}
        <div className="min-w-0 flex-1">
          <span className="text-foreground/90">{query}</span>
          {showSourceCount && sourceCount !== null ? (
            <span>
              {" "}
              · {sourceCount} source{sourceCount === 1 ? "" : "s"}
            </span>
          ) : null}
          {statusSuffix}
          {errorLine}
        </div>
      </div>
    </li>
  );
}

export function WebSearchPanel({ group, embedded = false }: WebSearchPanelProps) {
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
  const triggerDetail = statusLabel ?? summary;
  // Live turns default open; settled turns default closed unless the user toggled.
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const open = userOpen ?? isLive;

  return (
    <div
      data-testid="web-search-panel"
      className={cn(
        "max-w-full ui-body text-muted-foreground",
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
            <span className="ui-caption text-muted-foreground">{triggerDetail}</span>
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
          <ul className="mt-1 flex flex-col gap-0.5">
            {group.runs.map((run, idx) => (
              <WebSearchRunRow key={`${run.id}-${idx}`} run={run} />
            ))}
          </ul>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
