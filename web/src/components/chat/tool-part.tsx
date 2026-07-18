"use client";

import { useEffect, useRef, useState } from "react";
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
import { formatUsdMeter } from "@/lib/money";
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
// input carries the research plan (plus cost fields on the wire that the main
// UI does not render), which deserve a structured rendering instead of the
// generic one-line JSON preview.
const PLAN_APPROVAL_TOOL_NAME = "agentic_plan_approval";
const PLAN_CLARIFY_TOOL_NAME = "agentic_plan_clarify";

// Narrowed view of the plan-approval tool input:
// `{ plan: string[], estimatedCostUsd?: number, capUsd?: number }`. Null when
// the plan shape doesn't match (the renderer then falls back to the generic
// preview).
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

interface PlanClarifyInput {
  questions: string[];
}

function parsePlanClarifyInput(
  input: Record<string, JsonValue> | undefined,
): PlanClarifyInput | null {
  if (!input || !Array.isArray(input.questions)) return null;
  const questions = input.questions.filter(
    (q): q is string => typeof q === "string" && q.trim().length > 0,
  );
  if (questions.length === 0) return null;
  return { questions };
}

interface ToolPartViewProps {
  part: ToolPart;
  // HITL: invoked when the user approves/denies a tool call awaiting their
  // decision. Only wired (and the buttons only shown) for the LAST assistant
  // message whose turn is paused on this call — the parent gates it.
  onDecision?: (d: {
    toolCallId: string;
    decision: "approve" | "deny";
    editedInput?: Record<string, unknown>;
  }) => void;
  /** When nested inside a search/tool list, drop per-result card chrome. */
  embedded?: boolean;
}

export function ToolPartView({ part, onDecision, embedded = false }: ToolPartViewProps) {
  // A-14: synchronous double-submit guard — disable after the first click even
  // before the parent flips isStreaming / approvalState.
  const [decisionBusy, setDecisionBusy] = useState(false);
  const isResult = part.type === "tool_result";
  const status = part.status ?? (isResult ? "succeeded" : "pending");
  const approvalState = part.approvalState ?? "not_required";
  const label = part.label ?? humanizeName(part.name);
  // Plan-approval / clarify pseudo tools (agentic): render structurally instead
  // of the generic JSON preview.
  const planApproval =
    part.type === "tool_call" && part.name === PLAN_APPROVAL_TOOL_NAME
      ? parsePlanApprovalInput(part.input)
      : null;
  const planClarify =
    part.type === "tool_call" && part.name === PLAN_CLARIFY_TOOL_NAME
      ? parsePlanClarifyInput(part.input)
      : null;
  const detail =
    planApproval || planClarify
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
  // Nested inside a search/tool list: borderless rows for settled successes —
  // the green checkmark carries status; keep full chrome for failures/HITL.
  const compactEmbedded =
    embedded &&
    isTerminal &&
    status === "succeeded" &&
    planApproval == null &&
    planClarify == null &&
    !showApprovalControls;

  const outerClassName = cn(
    "flex max-w-full items-start gap-2 ui-body",
    compactEmbedded
      ? "py-1 text-muted-foreground"
      : cn(
          "rounded-xl border px-3 py-2.5",
          destructive
            ? "border-destructive/20 bg-destructive/5 text-destructive"
            : "border-foreground/[0.06] bg-foreground/[0.02] text-muted-foreground",
        ),
  );

  // The summary line (icon + label + role + status word) is shared between the
  // always-expanded layout and the collapsible trigger so the resting row reads
  // identically in both modes.
  // Plan-approval / clarify are user-facing gates, not generic tools — drop the
  // "tool call" suffix. When paused on approval, StatusPill ("Needs approval")
  // and ApprovalPill ("Approval pending") say the same thing; keep one.
  const showApprovalPill =
    approvalState !== "not_required" &&
    !(status === "awaiting_approval" && approvalState === "pending");

  const showStatusPill = !(compactEmbedded && status === "succeeded");

  const summaryRow = (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      <span className="truncate font-medium text-foreground">{label}</span>
      {planApproval || planClarify || compactEmbedded ? null : (
        <span className="ui-caption text-muted-foreground">
          {isResult ? "result" : "tool call"}
        </span>
      )}
      {showStatusPill ? <StatusPill status={status} /> : null}
      {showApprovalPill ? <ApprovalPill state={approvalState} /> : null}
    </div>
  );

  const detailBody = (
    <>
      {planApproval ? <PlanApprovalDetail input={planApproval} /> : null}
      {planClarify && showApprovalControls && toolCallId ? (
        <PlanClarifyForm
          questions={planClarify.questions}
          toolCallId={toolCallId}
          onDecision={onDecision!}
        />
      ) : null}
      {planClarify && !(showApprovalControls && toolCallId) ? (
        <PlanClarifyDetail input={planClarify} />
      ) : null}
      {detail ? (
        <p className="mt-1 line-clamp-2 break-words ui-caption leading-snug text-muted-foreground">
          {detail}
        </p>
      ) : null}
      {showApprovalControls && toolCallId && !planClarify ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            disabled={decisionBusy}
            onClick={() => {
              setDecisionBusy(true);
              onDecision({
                toolCallId,
                decision: "approve",
              });
            }}
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
            disabled={decisionBusy}
            onClick={() => {
              setDecisionBusy(true);
              onDecision({ toolCallId, decision: "deny" });
            }}
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
// decomposition as a numbered list so the user approves a legible plan — not a
// JSON blob.
function PlanApprovalDetail({ input }: { input: PlanApprovalInput }) {
  const showEstimate = input.estimatedCostUsd !== null;
  const showCap = input.capUsd !== null;
  return (
    <div className="mt-2 space-y-2" data-testid="plan-approval-detail">
      {showEstimate || showCap ? (
        <p className="ui-caption text-muted-foreground" data-testid="plan-approval-cost">
          {showEstimate ? (
            <span>
              Estimated run cost: {formatUsdMeter(input.estimatedCostUsd!)}
              <span className="text-muted-foreground/70"> (estimate)</span>
            </span>
          ) : null}
          {showCap ? (
            <span>
              {showEstimate ? " · " : null}
              Per-run cap: {formatUsdMeter(input.capUsd!)}
            </span>
          ) : null}
        </p>
      ) : null}
      <ol className="list-decimal space-y-1 pl-5 ui-caption leading-snug text-muted-foreground">
        {input.plan.map((step, idx) => (
          <li key={idx} className="break-words">
            {step}
          </li>
        ))}
      </ol>
    </div>
  );
}

function PlanClarifyDetail({ input }: { input: PlanClarifyInput }) {
  return (
    <div className="mt-2 space-y-2" data-testid="plan-clarify-detail">
      <p className="ui-caption text-muted-foreground">
        A few questions before starting the research run:
      </p>
      <ol className="list-decimal space-y-1 pl-5 ui-caption leading-snug text-muted-foreground">
        {input.questions.map((question, idx) => (
          <li key={idx} className="break-words">
            {question}
          </li>
        ))}
      </ol>
    </div>
  );
}

function PlanClarifyForm({
  questions,
  toolCallId,
  onDecision,
}: {
  questions: string[];
  toolCallId: string;
  onDecision: (d: {
    toolCallId: string;
    decision: "approve" | "deny";
    editedInput?: Record<string, unknown>;
  }) => void;
}) {
  const [answers, setAnswers] = useState<string[]>(() => questions.map(() => ""));
  const [decisionBusy, setDecisionBusy] = useState(false);
  const maxAnswerChars = 2000;
  const firstAnswerRef = useRef<HTMLTextAreaElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  // C-007: move focus to the first clarify field when the form appears, and
  // restore the prior focus target after the user decides.
  useEffect(() => {
    const active = document.activeElement;
    previousFocusRef.current =
      active instanceof HTMLElement ? active : null;
    const frame = requestAnimationFrame(() => {
      firstAnswerRef.current?.focus();
    });
    return () => {
      cancelAnimationFrame(frame);
      const prior = previousFocusRef.current;
      if (prior && typeof prior.focus === "function") {
        prior.focus();
      }
    };
  }, []);

  return (
    <div
      className="mt-2 space-y-3"
      data-testid="plan-clarify-detail"
      role="group"
      aria-labelledby="plan-clarify-heading"
    >
      <p
        id="plan-clarify-heading"
        className="ui-caption text-muted-foreground"
        tabIndex={-1}
      >
        A few questions before starting the research run:
      </p>
      <ol className="list-none space-y-3 p-0">
        {questions.map((question, idx) => (
          <li key={idx} className="space-y-1.5">
            <label
              htmlFor={`plan-clarify-answer-${idx}`}
              className="block ui-caption leading-snug text-foreground"
            >
              <span className="text-muted-foreground">{idx + 1}. </span>
              {question}
            </label>
            <textarea
              ref={idx === 0 ? firstAnswerRef : undefined}
              id={`plan-clarify-answer-${idx}`}
              data-testid={`plan-clarify-answer-${idx}`}
              value={answers[idx] ?? ""}
              onChange={(e) => {
                const next = [...answers];
                next[idx] = e.target.value.slice(0, maxAnswerChars);
                setAnswers(next);
              }}
              rows={2}
              maxLength={maxAnswerChars}
              className={cn(
                "w-full resize-y rounded-lg border border-foreground/10 bg-background px-2.5 py-2",
                "ui-caption leading-snug text-foreground placeholder:text-muted-foreground/70",
                "outline-none focus-visible:shadow-[var(--focus-ring)]",
              )}
              placeholder="Your answer (optional)"
            />
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          disabled={decisionBusy}
          onClick={() => {
            setDecisionBusy(true);
            onDecision({
              toolCallId,
              decision: "approve",
              editedInput: {
                answers: questions.map((question, idx) => ({
                  questionId: String(idx),
                  question,
                  answer: answers[idx] ?? "",
                })),
              },
            });
          }}
          data-testid="tool-approve"
          className="min-h-11 rounded-full bg-brand px-4 text-brand-foreground hover:bg-brand/90 md:min-h-0"
        >
          <Check aria-hidden />
          <span>Continue</span>
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={decisionBusy}
          onClick={() => {
            setDecisionBusy(true);
            onDecision({ toolCallId, decision: "deny" });
          }}
          data-testid="tool-deny"
          className="min-h-11 rounded-full px-4 md:min-h-0"
        >
          <X aria-hidden />
          <span>Skip research</span>
        </Button>
      </div>
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
    <span className="inline-flex h-5 items-center rounded-full bg-foreground/[0.06] px-2 ui-caption text-muted-foreground">
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
        "inline-flex h-5 items-center gap-1 rounded-full px-2 ui-caption",
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
  const cleaned = stripReservedToolKeys(value);
  const rendered =
    typeof cleaned === "string" ? cleaned : JSON.stringify(cleaned, null, 0);
  if (!rendered) return null;
  return rendered.length > 180 ? `${rendered.slice(0, 177)}...` : rendered;
}

/** H-012: never render server control / ledger keys as tool input. */
const RESERVED_TOOL_KEYS = new Set([
  "_agenticContinuation",
  "_approvalClaimId",
  "plannerCostUsd",
  "planner_cost_usd",
  "actualCostUsd",
  "actual_cost_usd",
  "pausedWorkerCostUsd",
  "paused_worker_cost_usd",
]);

function stripReservedToolKeys(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(stripReservedToolKeys);
  }
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      if (RESERVED_TOOL_KEYS.has(key)) continue;
      out[key] = stripReservedToolKeys(child);
    }
    return out;
  }
  return value;
}
