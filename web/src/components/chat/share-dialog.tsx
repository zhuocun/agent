"use client";

import { useId, useRef, useState, type JSX } from "react";
import { Check, Copy, Link2 } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  ApiNetworkError,
  createShareLink,
  deleteShareLink,
} from "@/lib/apiClient";

export interface ShareDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // The conversation this dialog mints / revokes a link for. `null` while no
  // conversation is targeted (the parent only opens the dialog with a real id).
  conversationId: string | null;
  conversationTitle: string | null;
}

// Map the frozen backend error contract to short copy. A 404 on the share
// routes means the conversation isn't shareable (temporary chat) or isn't
// owned — collapse both into one non-enumerating line. Anything else falls
// through to the server's own copy, then a generic fallback.
function messageForError(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 404) {
      return "This conversation can't be shared.";
    }
    if (cause.status === 429) {
      return "Too many attempts. Try again in a minute.";
    }
    return cause.body || cause.title;
  }
  if (cause instanceof ApiNetworkError) {
    return "Couldn't reach the server. Check your connection and try again.";
  }
  return "Something went wrong. Please try again.";
}

// Assemble the absolute share URL from the BE's relative path and our own
// origin (the BE deliberately never knows the public origin). SSR-safe: the
// dialog is client-only and only computes this after a successful mint, so
// `window` is always defined at call time.
function absoluteShareUrl(sharePath: string): string {
  if (typeof window === "undefined") return sharePath;
  return new URL(sharePath, window.location.origin).toString();
}

// Share-management dialog (PRD 07 §6.4). Two states inside one surface:
//   - "create": a single button mints the link (idempotent on the BE).
//   - "ready": the absolute URL in a read-only field + Copy, with Remove link
//     to revoke and fall back to "create".
// Styling, focus trap, escape-to-close and swipe-to-dismiss all ride on the
// shared <DialogContent> shell (matches settings-dialog.tsx / auth-dialog.tsx).
export function ShareDialog({
  open,
  onOpenChange,
  conversationId,
  conversationTitle,
}: ShareDialogProps): JSX.Element {
  const urlFieldId = useId();
  const errorId = useId();

  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  // Transient "Copied" / revoke confirmation timers; cleared on close so a
  // stale timeout can't flip state after the dialog is gone.
  const copiedTimerRef = useRef<number | null>(null);

  // Reset transient state on close so a re-open starts clean. Driven from the
  // close path rather than an effect to avoid an open→render→reset cascade
  // (the repo lints react-hooks/set-state-in-effect).
  const handleOpenChange = (next: boolean) => {
    if (!next) {
      if (copiedTimerRef.current !== null) {
        window.clearTimeout(copiedTimerRef.current);
        copiedTimerRef.current = null;
      }
      setShareUrl(null);
      setPending(false);
      setError(null);
      setCopied(false);
      setStatus(null);
    }
    onOpenChange(next);
  };

  const handleCreate = async () => {
    if (pending || !conversationId) return;
    setPending(true);
    setError(null);
    setStatus(null);
    try {
      const result = await createShareLink(conversationId);
      setShareUrl(absoluteShareUrl(result.sharePath));
      setStatus("Share link created");
    } catch (cause) {
      setError(messageForError(cause));
    } finally {
      setPending(false);
    }
  };

  const handleRevoke = async () => {
    if (pending || !conversationId) return;
    setPending(true);
    setError(null);
    setStatus(null);
    try {
      // Any 2xx (the BE returns 204) means the conversation is now unshared.
      await deleteShareLink(conversationId);
      if (copiedTimerRef.current !== null) {
        window.clearTimeout(copiedTimerRef.current);
        copiedTimerRef.current = null;
      }
      setShareUrl(null);
      setCopied(false);
      setStatus("Link removed");
    } catch (cause) {
      setError(messageForError(cause));
    } finally {
      setPending(false);
    }
  };

  const handleCopy = async () => {
    if (!shareUrl) return;
    const confirmCopied = () => {
      setCopied(true);
      setStatus("Link copied");
      if (copiedTimerRef.current !== null) {
        window.clearTimeout(copiedTimerRef.current);
      }
      copiedTimerRef.current = window.setTimeout(() => {
        copiedTimerRef.current = null;
        setCopied(false);
      }, 2000);
    };

    // Clipboard API is the happy path; fall back to selecting the field so the
    // user can copy manually where the API is unavailable (insecure origin,
    // older browser, denied permission).
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareUrl);
        confirmCopied();
        return;
      }
      throw new Error("clipboard unavailable");
    } catch {
      const field = document.getElementById(
        urlFieldId,
      ) as HTMLInputElement | null;
      if (field) {
        field.focus();
        field.select();
      }
      setStatus("Press Ctrl/Cmd+C to copy the link.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Share chat</DialogTitle>
          <DialogDescription>
            {conversationTitle
              ? `Create a public link to "${conversationTitle}".`
              : "Create a public link to this conversation."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Anyone with the link can view this conversation read-only. Costs and
            usage are hidden on the shared view.
          </p>

          {shareUrl ? (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <label htmlFor={urlFieldId} className="text-sm font-medium">
                  Public link
                </label>
                <div className="flex items-center gap-2">
                  <input
                    id={urlFieldId}
                    type="text"
                    value={shareUrl}
                    readOnly
                    onFocus={(e) => e.currentTarget.select()}
                    aria-label="Public share link"
                    className="block h-11 w-full min-w-0 flex-1 rounded-2xl bg-muted/50 px-3 text-sm text-foreground outline-none focus-visible:shadow-[var(--focus-ring)] sm:h-9"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={handleCopy}
                    className="h-11 shrink-0 rounded-full px-3 sm:h-9"
                  >
                    {copied ? (
                      <>
                        <Check aria-hidden className="size-4" />
                        <span>Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy aria-hidden className="size-4" />
                        <span>Copy</span>
                      </>
                    )}
                  </Button>
                </div>
              </div>

              <Button
                type="button"
                variant="ghost"
                onClick={handleRevoke}
                disabled={pending}
                className="-ml-2 rounded-full text-muted-foreground hover:text-foreground"
              >
                {pending ? "Removing link..." : "Remove link"}
              </Button>
            </div>
          ) : (
            <Button
              type="button"
              onClick={handleCreate}
              disabled={pending}
              className="h-11 w-full rounded-full"
            >
              <Link2 aria-hidden className="size-4" />
              <span>{pending ? "Creating link..." : "Create share link"}</span>
            </Button>
          )}

          {error ? (
            <p id={errorId} role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}

          {/* Status line for AT: announces copy / create / revoke without
              stealing focus. role="status" is an implicit aria-live=polite. */}
          <p role="status" className="sr-only">
            {status}
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
