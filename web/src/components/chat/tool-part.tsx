"use client";

import {
  Check,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  Loader2,
  ShieldCheck,
  ShieldQuestion,
  Wrench,
  X,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type {
  MessagePart,
  ToolApprovalState,
  ToolRunStatus,
} from "@/lib/types";

type ToolPart = Extract<MessagePart, { type: "tool_call" | "tool_result" }>;

interface ToolPartViewProps {
  part: ToolPart;
  // HITL: invoked when the user approves/denies a tool call awaiting their
  // decision. Only wired (and the buttons only shown) for the LAST assistant
  // message whose turn is paused on this call — the parent gates it.
  onDecision?: (d: { toolCallId: string; decision: "approve" | "deny" }) => void;
}

export function ToolPartView({ part, onDecision }: ToolPartViewProps) {
  const isResult = part.type === "tool_result";
  const status = part.status ?? (isResult ? "succeeded" : "pending");
  const approvalState = part.approvalState ?? "not_required";
  const label = part.label ?? humanizeName(part.name);
  const detail =
    part.type === "tool_call"
      ? previewJson(part.input)
      : part.error ?? part.summary ?? previewJson(part.output);
  const destructive = status === "failed" || approvalState === "rejected";
  // Show the approve/deny controls only on a tool_call still pending the user's
  // decision, and only when the parent supplied a handler (it gates this to the
  // trailing paused turn). Mirrors the BE pause shape: status
  // "awaiting_approval" + approvalState "pending".
  const showApprovalControls =
    part.type === "tool_call" &&
    status === "awaiting_approval" &&
    approvalState === "pending" &&
    onDecision !== undefined;
  const toolCallId = part.type === "tool_call" ? part.id : undefined;
  // Settled tool runs carry no live info, so collapse their detail + pills
  // behind a one-line summary (progressive disclosure) and let the user expand
  // on a tap. `running` and `awaiting_approval` stay always-expanded: they
  // carry live state and (for awaiting_approval) the approve/deny controls that
  // must stay reachable, so collapsing them would regress the HITL flow.
  const isTerminal =
    status === "succeeded" || status === "failed" || status === "cancelled";

  const outerClassName = cn(
    "flex max-w-full items-start gap-2 rounded-xl border px-3 py-2.5 text-sm",
    destructive
      ? "border-destructive/20 bg-destructive/5 text-destructive"
      : "border-foreground/[0.06] bg-foreground/[0.02] text-muted-foreground",
  );

  // The summary line (icon + label + role + status word) is shared between the
  // always-expanded layout and the collapsible trigger so the resting row reads
  // identically in both modes.
  const summaryRow = (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      <span className="truncate font-medium text-foreground">{label}</span>
      <span className="text-xs text-muted-foreground">
        {isResult ? "result" : "tool call"}
      </span>
      <StatusPill status={status} />
      {approvalState !== "not_required" ? (
        <ApprovalPill state={approvalState} />
      ) : null}
    </div>
  );

  const detailBody = (
    <>
      {detail ? (
        <p className="mt-1 line-clamp-2 break-words text-xs leading-snug text-muted-foreground">
          {detail}
        </p>
      ) : null}
      {showApprovalControls && toolCallId ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            onClick={() => onDecision({ toolCallId, decision: "approve" })}
            data-testid="tool-approve"
            className="rounded-full"
          >
            <Check aria-hidden />
            <span>Approve</span>
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onDecision({ toolCallId, decision: "deny" })}
            data-testid="tool-deny"
            className="rounded-full"
          >
            <X aria-hidden />
            <span>Deny</span>
          </Button>
        </div>
      ) : null}
    </>
  );

  // Live (running / awaiting_approval) states render fully expanded so their
  // detail and approve/deny controls are always reachable.
  if (!isTerminal) {
    return (
      <div data-testid={isResult ? "tool-result-part" : "tool-call-part"} className={outerClassName}>
        <StatusIcon status={status} destructive={destructive} />
        <div className="min-w-0 flex-1">
          {summaryRow}
          {detailBody}
        </div>
      </div>
    );
  }

  // Settled states collapse the detail behind the summary. The trigger reuses
  // the summary row and adds a chevron; clicking it expands the detail. The
  // panel height/opacity tween on the iOS "smooth" curve; reduced-motion users
  // get the instant collapse — globals.css zeroes the transition on
  // `[data-slot="collapsible-content"]` (the panel primitive carries that slot)
  // under `prefers-reduced-motion`, and the chevron rotation degrades via
  // `motion-reduce:transition-none`.
  return (
    <Collapsible
      data-testid={isResult ? "tool-result-part" : "tool-call-part"}
      className={outerClassName}
    >
      <StatusIcon status={status} destructive={destructive} />
      <div className="min-w-0 flex-1">
        <CollapsibleTrigger
          className={cn(
            "group/tool-trigger flex w-full min-w-0 items-center gap-1.5 text-left",
            "bg-transparent outline-none",
            "focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
          )}
          aria-label={`${label}, ${statusLabel(status)} — show details`}
        >
          {summaryRow}
          <ChevronDown
            aria-hidden
            className="ml-auto size-3.5 shrink-0 transition-transform duration-300 ease-[var(--ease-ios-spring)] motion-reduce:transition-none group-data-[panel-open]/tool-trigger:rotate-180"
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
          {detailBody}
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

function StatusIcon({
  status,
  destructive,
}: {
  status: ToolRunStatus;
  destructive: boolean;
}) {
  if (status === "running") {
    return (
      <Loader2
        className="mt-0.5 size-4 shrink-0 motion-safe:animate-spin"
        aria-hidden
      />
    );
  }
  if (status === "succeeded") {
    return (
      <CheckCircle2
        className="mt-0.5 size-4 shrink-0 text-success"
        aria-hidden
      />
    );
  }
  if (destructive) {
    return <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden />;
  }
  if (status === "awaiting_approval") {
    return (
      <ShieldQuestion
        className="mt-0.5 size-4 shrink-0 text-warning-foreground"
        aria-hidden
      />
    );
  }
  if (status === "cancelled") {
    return <CircleDashed className="mt-0.5 size-4 shrink-0" aria-hidden />;
  }
  return <Wrench className="mt-0.5 size-4 shrink-0" aria-hidden />;
}

function StatusPill({ status }: { status: ToolRunStatus }) {
  return (
    <span className="inline-flex h-5 items-center rounded-full bg-foreground/[0.06] px-2 text-2xs text-muted-foreground">
      {statusLabel(status)}
    </span>
  );
}

function ApprovalPill({ state }: { state: ToolApprovalState }) {
  const approved = state === "approved";
  const rejected = state === "rejected";
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-full px-2 text-2xs",
        approved && "bg-success/10 text-success",
        rejected && "bg-destructive/10 text-destructive",
        !approved && !rejected && "bg-warning text-warning-foreground",
      )}
    >
      {approved ? <ShieldCheck className="size-3" aria-hidden /> : null}
      {approvalLabel(state)}
    </span>
  );
}

function statusLabel(status: ToolRunStatus): string {
  switch (status) {
    case "awaiting_approval":
      return "Needs approval";
    case "running":
      return "Running";
    case "succeeded":
      return "Complete";
    case "failed":
      return "Failed";
    case "cancelled":
      return "Cancelled";
    case "pending":
      return "Pending";
  }
}

function approvalLabel(state: ToolApprovalState): string {
  switch (state) {
    case "pending":
      return "Approval pending";
    case "approved":
      return "Approved";
    case "rejected":
      return "Rejected";
    case "not_required":
      return "No approval";
  }
}

function humanizeName(name: string): string {
  return name
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function previewJson(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  const rendered =
    typeof value === "string" ? value : JSON.stringify(value, null, 0);
  if (!rendered) return null;
  return rendered.length > 180 ? `${rendered.slice(0, 177)}...` : rendered;
}
