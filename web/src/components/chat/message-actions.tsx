"use client";

import { useState } from "react";
import {
  Check,
  Copy,
  GitBranch,
  Loader2,
  RotateCcw,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Feedback } from "@/lib/types";

interface MessageActionsProps {
  text: string;
  feedback: Feedback;
  canBranch?: boolean;
  isBranching?: boolean;
  canRegenerate?: boolean;
  onBranch?: () => void;
  onRegenerate?: () => void;
  onFeedback?: (next: Feedback) => void;
}

// Legacy clipboard fallback for insecure origins / denied permission, where
// `navigator.clipboard` is unavailable. Selects an off-screen textarea and
// runs `document.execCommand("copy")`. Returns whether the copy succeeded.
function legacyCopy(value: string): boolean {
  if (typeof document === "undefined") return false;
  const ta = document.createElement("textarea");
  ta.value = value;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.top = "-9999px";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  try {
    ta.focus();
    ta.select();
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    document.body.removeChild(ta);
  }
}

export function MessageActions({
  text,
  feedback,
  canBranch,
  isBranching,
  canRegenerate,
  onBranch,
  onRegenerate,
  onFeedback,
}: MessageActionsProps) {
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);

  const handleCopy = async () => {
    const markCopied = () => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    };
    // Clipboard API is the happy path; fall back to a legacy off-screen
    // textarea + execCommand so copy still works on insecure origins / when
    // permission is denied (mirrors share-dialog.tsx). Prefer copying over
    // erroring; only surface "Copy failed" if both paths fail.
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        markCopied();
        return;
      }
      throw new Error("clipboard unavailable");
    } catch {
      if (legacyCopy(text)) {
        markCopied();
      } else {
        setCopyFailed(true);
        setTimeout(() => setCopyFailed(false), 1500);
      }
    }
  };

  return (
    <div role="toolbar" aria-label="Message actions" className="group/actions inline-flex items-center gap-0.5 rounded-full p-0.5">
      <IconAction
        label={copied ? "Copied" : copyFailed ? "Copy failed" : "Copy"}
        onClick={handleCopy}
      >
        {copied ? (
          <Check className="size-4 text-success" />
        ) : (
          <Copy className="size-4" />
        )}
      </IconAction>

      {canRegenerate ? (
        <IconAction label="Regenerate" onClick={onRegenerate}>
          <RotateCcw className="size-4" />
        </IconAction>
      ) : null}

      {onBranch ? (
        <IconAction
          label={isBranching ? "Branching" : "Branch in new chat"}
          disabled={!canBranch || isBranching}
          onClick={onBranch}
        >
          {isBranching ? (
            <Loader2 className="size-4 motion-safe:animate-spin" />
          ) : (
            <GitBranch className="size-4" />
          )}
        </IconAction>
      ) : null}

      <IconAction
        label="Helpful"
        pressed={feedback === "up"}
        onClick={() => onFeedback?.(feedback === "up" ? null : "up")}
      >
        <ThumbsUp className="size-4" />
      </IconAction>

      <IconAction
        label="Not helpful"
        pressed={feedback === "down"}
        onClick={() => onFeedback?.(feedback === "down" ? null : "down")}
      >
        <ThumbsDown className="size-4" />
      </IconAction>
    </div>
  );
}

function IconAction({
  label,
  pressed,
  disabled,
  onClick,
  children,
}: {
  label: string;
  pressed?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            onClick={onClick}
            disabled={disabled}
            aria-label={label}
            aria-pressed={typeof pressed === "boolean" ? pressed : undefined}
            className={cn(
              "size-11 rounded-full p-0 text-muted-foreground hover:text-foreground md:size-9",
              pressed && "bg-foreground/[0.06] text-foreground",
            )}
          >
            {children}
          </Button>
        }
      />
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
