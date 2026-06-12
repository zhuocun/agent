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
  JsonValue,
  MessagePart,
  ToolApprovalState,
  ToolRunStatus,
} from "@/lib/types";

type ToolPart = Extract<MessagePart, { type: "tool_call" | "tool_result" }>;

// The agentic orchestrator's plan-approval pause rides a PSEUDO tool call with
// this name (api/app/agentic/orchestrator.py PLAN_APPROVAL_TOOL_NAME). Its
// input carries the research plan + cost estimate, which deserve a structured
// rendering instead of the generic one-line JSON preview.
const PLAN_APPROVAL_TOOL_NAME = "agentic_plan_approval";

// Narrowed view of the plan-approval tool input:
// `{ plan: string[], estimatedCostUsd: number, capUsd: number }`. Null when the
// shape doesn't match (the renderer then falls back to the generic preview).
interface PlanApprovalInput {
  plan: string[];
  estimatedCostUsd: number | null;
  capUsd: number | null;
}

function parsePlanApprovalInput(
  input: Record<string, JsonValue> | undefined,
): PlanApprovalInput | null {
  if (!input || !Array.isArray(input.plan)) return null;
  const plan = input.plan.filter((step): step is string => typeof step === "string");
  if (plan.length === 0) return null;
  return {
    plan,
    estimatedCostUsd:
      typeof input.estimatedCostUsd === "number" ? input.estimatedCostUsd : null,
    capUsd: typeof input.capUsd === "number" ? input.capUsd : null,
  };
}

// Mirrors attribution-row's cost summary grammar.
function formatUsd(n: number): string {
  if (n === 0) return "$0.00";
  if (n < 0.0001) return "<$0.0001";
  const decimals = n < 0.01 ? 4 : n < 1 ? 3 : 2;
  return `$${n.toFixed(decimals)}`;
}

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
  // Plan-approval pseudo tool (agentic): render the research plan + cost
  // estimate structurally instead of the generic JSON preview. Falls back to
  // the preview when the input doesn't match the expected shape.
  const planApproval =
    part.type === "tool_call" && part.name === PLAN_APPROVAL_TOOL_NAME
      ? parsePlanApprovalInput(part.input)
      : null;
  const detail = planApproval
    ? null
    : part.type === "tool_call"
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
  // Plan-approval is a user-facing gate, not a generic tool — drop the "tool
  // call" suffix. When paused on approval, StatusPill ("Needs approval") and
  // ApprovalPill ("Approval pending") say the same thing; keep one.
  const showApprovalPill =
    approvalState !== "not_required" &&
    !(status === "awaiting_approval" && approvalState === "pending");

  const summaryRow = (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      <span className="truncate font-medium text-foreground">{label}</span>
      {planApproval ? null : (
        <span className="text-xs text-muted-foreground">
          {isResult ? "result" : "tool call"}
        </span>
      )}
      <StatusPill status={status} />
      {showApprovalPill ? <ApprovalPill state={approvalState} /> : null}
    </div>
  );

  const detailBody = (
    <>
      {planApproval ? <PlanApprovalDetail input={planApproval} /> : null}
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
            className="min-h-11 rounded-full bg-brand px-4 text-brand-foreground hover:bg-brand/90 md:min-h-0"
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
            className="min-h-11 rounded-full px-4 md:min-h-0"
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
            "min-h-11 bg-transparent py-2 -my-2 outline-none md:min-h-0 md:py-0 md:my-0",
            "focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
          )}
          aria-label={`${label}, ${statusLabel(status)} — toggle details`}
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

// Structured body for the plan-approval pause: the planner's sub-question
// decomposition as a numbered list plus the pre-spawn cost estimate against
// the per-run cap, so the user approves a legible plan — not a JSON blob.
function PlanApprovalDetail({ input }: { input: PlanApprovalInput }) {
  return (
    <div className="mt-2 space-y-2" data-testid="plan-approval-detail">
      <ol className="list-decimal space-y-1 pl-5 text-xs leading-snug text-muted-foreground">
        {input.plan.map((step, idx) => (
          <li key={idx} className="break-words">
            {step}
          </li>
        ))}
      </ol>
      {input.estimatedCostUsd !== null ? (
        <p className="text-xs text-muted-foreground">
          Estimated cost{" "}
          <span className="font-mono tabular-nums text-foreground">
            {formatUsd(input.estimatedCostUsd)}
          </span>
          {input.capUsd !== null ? (
            <> of {formatUsd(input.capUsd)} run cap</>
          ) : null}
        </p>
      ) : null}
    </div>
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
        className="mt-0.5 size-4 shrink-0 text-warning"
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
