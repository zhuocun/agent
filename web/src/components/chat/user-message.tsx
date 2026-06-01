"use client";

import { useEffect, useRef, useState } from "react";
import {
  Check,
  Copy,
  FileText,
  GitBranch,
  Image as ImageIcon,
  Loader2,
  Pencil,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { ChatMessage, MessagePart } from "@/lib/types";

interface UserMessageProps {
  message: ChatMessage;
  onEdit?: (newText: string) => void;
  onBranch?: () => void;
  canEdit?: boolean;
  canBranch?: boolean;
  isBranching?: boolean;
}

const MAX_EDIT_HEIGHT = 320;

function formatAttachmentSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UserMessage({
  message,
  onEdit,
  onBranch,
  canEdit,
  canBranch,
  isBranching,
}: UserMessageProps) {
  const text = message.parts
    .filter((p): p is Extract<MessagePart, { type: "text" }> => p.type === "text")
    .map((p) => p.text)
    .join("\n\n");
  const attachments = message.parts.filter(
    (p): p is Extract<MessagePart, { type: "attachment" }> =>
      p.type === "attachment",
  );

  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(text);
  const [copied, setCopied] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const editable = !!onEdit && !!canEdit;
  const trimmed = draft.trim();
  const canSave = trimmed.length > 0 && draft !== text;

  const autoGrow = () => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, MAX_EDIT_HEIGHT)}px`;
  };

  useEffect(() => {
    if (!isEditing) return;
    const ta = textareaRef.current;
    if (!ta) return;
    ta.focus();
    const end = ta.value.length;
    ta.setSelectionRange(end, end);
    autoGrow();
  }, [isEditing]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable in insecure contexts.
    }
  };

  const enterEdit = () => {
    setDraft(text);
    setIsEditing(true);
  };

  const cancelEdit = () => {
    setIsEditing(false);
    setDraft(text);
  };

  const saveEdit = () => {
    if (submitting || !canSave || !onEdit) return;
    setSubmitting(true);
    onEdit(trimmed);
    setIsEditing(false);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (e.key === "Escape") {
      e.preventDefault();
      cancelEdit();
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (editable) saveEdit();
    }
  };

  if (isEditing) {
    return (
      <div className="flex justify-end" role="article" aria-label="You">
        <div className="w-full max-w-[85%] space-y-2">
          {/* Edit reuses the SAME tinted-glass material as the display bubble
              (see below) so entering edit doesn't change the bubble's surface —
              only its contents. brand-muted wash + inset top highlight + 1px
              hairline read it as the user's raised glass object. */}
          <div className="rounded-3xl bg-brand-muted px-5 py-3 shadow-[var(--glass-highlight),inset_0_0_0_1px_var(--glass-border)]">
            <label className="block">
              <span className="sr-only">Edit message</span>
              <textarea
                ref={textareaRef}
                rows={1}
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value);
                  autoGrow();
                }}
                onKeyDown={onKeyDown}
                className="block min-h-[44px] max-h-[320px] w-full resize-none bg-transparent text-[1.0625rem] leading-7 text-foreground outline-none md:text-[0.9375rem]"
              />
            </label>
          </div>
          <div className="flex items-center justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={cancelEdit}
              className="h-11 rounded-full px-4 text-sm text-muted-foreground hover:text-foreground"
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={saveEdit}
              disabled={!canSave || submitting}
              aria-label="Save and resubmit"
              // Brand fill (matching the composer's primary send) so "submit a
              // turn" has one consistent primary color across the surface.
              className="h-11 rounded-full bg-brand px-4 text-sm text-brand-foreground hover:bg-brand/90 disabled:opacity-40"
            >
              Save
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="group/msg flex flex-col items-end gap-1"
      role="article"
      aria-label="You"
    >
      {/* The user's bubble reads as a faint brand-tinted glass object, not a
          flat gray fill: `bg-brand-muted` (themed light/dark) is the user's
          single-accent "voice," and the inset top highlight + 1px hairline
          give it raised glass dimensionality. Tail-less + continuous
          rounded-3xl is the modern iOS-26 direction. `text-foreground` stays
          legible over the wash in both themes (pale-blue/near-black in light,
          mid-blue/near-white in dark). Kept deliberately subtle — a wash, not
          a saturated blue bubble. */}
      <div
        data-testid="user-message-text"
        className="max-w-[85%] space-y-3 rounded-3xl bg-brand-muted px-5 py-3 text-[1.0625rem] leading-7 text-foreground shadow-[var(--glass-highlight),inset_0_0_0_1px_var(--glass-border)] md:text-[0.9375rem]"
      >
        {text ? <div className="whitespace-pre-wrap break-words">{text}</div> : null}
        {attachments.length > 0 ? (
          <div className="flex flex-wrap justify-end gap-2">
            {attachments.map((attachment) => (
              <span
                key={attachment.id}
                className="inline-flex h-8 max-w-full items-center gap-2 rounded-full bg-background/45 px-3 text-xs leading-none text-foreground shadow-[inset_0_0_0_1px_var(--glass-border)]"
              >
                {attachment.mediaType === "pdf" ? (
                  <FileText aria-hidden className="size-3.5 shrink-0" />
                ) : (
                  <ImageIcon aria-hidden className="size-3.5 shrink-0" />
                )}
                <span className="min-w-0 max-w-[12rem] truncate">
                  {attachment.name}
                </span>
                <span className="shrink-0 text-muted-foreground">
                  {formatAttachmentSize(attachment.sizeBytes)}
                </span>
              </span>
            ))}
          </div>
        ) : null}
      </div>
      <div className="opacity-100 transition-opacity focus-within:opacity-100 md:opacity-0 md:group-hover/msg:opacity-100 [@media(hover:none)]:opacity-100">
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                type="button"
                variant="ghost"
                onClick={handleCopy}
                aria-label={copied ? "Copied" : "Copy"}
                className="size-11 rounded-full p-0 text-muted-foreground hover:text-foreground md:size-9"
              >
                {copied ? (
                  <Check className="size-4 text-success" />
                ) : (
                  <Copy className="size-4" />
                )}
              </Button>
            }
          />
          <TooltipContent>{copied ? "Copied" : "Copy"}</TooltipContent>
        </Tooltip>

        {editable ? (
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  type="button"
                  variant="ghost"
                  onClick={enterEdit}
                  aria-label="Edit"
                  className="size-11 rounded-full p-0 text-muted-foreground hover:text-foreground md:size-9"
                >
                  <Pencil className="size-4" />
                </Button>
              }
            />
            <TooltipContent>Edit</TooltipContent>
          </Tooltip>
        ) : null}

        {onBranch ? (
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  type="button"
                  variant="ghost"
                  onClick={onBranch}
                  disabled={!canBranch || isBranching}
                  aria-label={isBranching ? "Branching" : "Branch in new chat"}
                  className="size-11 rounded-full p-0 text-muted-foreground hover:text-foreground md:size-9"
                >
                  {isBranching ? (
                    <Loader2 className="size-4 motion-safe:animate-spin" />
                  ) : (
                    <GitBranch className="size-4" />
                  )}
                </Button>
              }
            />
            <TooltipContent>
              {isBranching ? "Branching" : "Branch in new chat"}
            </TooltipContent>
          </Tooltip>
        ) : null}
      </div>
    </div>
  );
}
