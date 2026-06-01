"use client";

import {
  CheckCircle2,
  CircleDashed,
  Loader2,
  ShieldCheck,
  ShieldQuestion,
  Wrench,
  XCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type {
  MessagePart,
  ToolApprovalState,
  ToolRunStatus,
} from "@/lib/types";

type ToolPart = Extract<MessagePart, { type: "tool_call" | "tool_result" }>;

interface ToolPartViewProps {
  part: ToolPart;
}

export function ToolPartView({ part }: ToolPartViewProps) {
  const isResult = part.type === "tool_result";
  const status = part.status ?? (isResult ? "succeeded" : "pending");
  const approvalState = part.approvalState ?? "not_required";
  const label = part.label ?? humanizeName(part.name);
  const detail =
    part.type === "tool_call"
      ? previewJson(part.input)
      : part.error ?? part.summary ?? previewJson(part.output);
  const destructive = status === "failed" || approvalState === "rejected";

  return (
    <div
      data-testid={isResult ? "tool-result-part" : "tool-call-part"}
      className={cn(
        "flex max-w-full items-start gap-2 rounded-md border px-3 py-2 text-sm",
        destructive
          ? "border-destructive/20 bg-destructive/5 text-destructive"
          : "border-foreground/[0.06] bg-foreground/[0.02] text-muted-foreground",
      )}
    >
      <StatusIcon status={status} destructive={destructive} />
      <div className="min-w-0 flex-1">
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
        {detail ? (
          <p className="mt-1 line-clamp-2 break-words text-xs leading-snug text-muted-foreground">
            {detail}
          </p>
        ) : null}
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
    <span className="inline-flex h-5 items-center rounded-full bg-foreground/[0.06] px-2 text-[11px] text-muted-foreground">
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
        "inline-flex h-5 items-center gap-1 rounded-full px-2 text-[11px]",
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
