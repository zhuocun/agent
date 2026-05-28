"use client";

import { useState } from "react";
import { Check, Copy, RotateCcw, ThumbsDown, ThumbsUp } from "lucide-react";

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
  canRegenerate?: boolean;
  onRegenerate?: () => void;
  onFeedback?: (next: Feedback) => void;
}

export function MessageActions({
  text,
  feedback,
  canRegenerate,
  onRegenerate,
  onFeedback,
}: MessageActionsProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable in insecure contexts.
    }
  };

  return (
    <div
      className={cn(
        "group/actions inline-flex items-center gap-0.5 rounded-full p-0.5",
        "transition-colors duration-200",
        "hover:[background-color:var(--glass-regular-bg)] hover:shadow-glass-ambient",
        "focus-within:[background-color:var(--glass-regular-bg)] focus-within:shadow-glass-ambient",
      )}
    >
      <IconAction label={copied ? "Copied" : "Copy"} onClick={handleCopy}>
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

      <IconAction
        label="Good response"
        pressed={feedback === "up"}
        onClick={() => onFeedback?.(feedback === "up" ? null : "up")}
      >
        <ThumbsUp className="size-4" />
      </IconAction>

      <IconAction
        label="Bad response"
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
  onClick,
  children,
}: {
  label: string;
  pressed?: boolean;
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
            aria-label={label}
            aria-pressed={pressed}
            className={cn(
              "size-11 rounded-full p-0 text-muted-foreground hover:text-foreground md:size-8",
              pressed && "text-brand",
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
