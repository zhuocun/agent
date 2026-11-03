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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

// Link plus the conversation it was minted for. `conversationId` stays in this
// object even when `url` is null so an in-flight create can tell a conversation
// change from "no link yet".
interface ShareSession {
  // `open` is mirrored so a response that lands after close cannot restore a
  // link the close path just cleared.
  open: boolean;
  conversationId: string | null;
  url: string | null;
  status: string | null;
  copied: boolean;
  error: string | null;
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

  // The minted URL is stored with the conversation id captured when Create
  // started. `conversationId` on this object is the id the link belongs to,
  // kept in state so a late response can see a newer id without reading a ref
  // during render. New chat can null the prop while this dialog stays open.
  const [session, setSession] = useState<ShareSession>(() => ({
    open,
    conversationId,
    url: null,
    status: null,
    copied: false,
    error: null,
  }));
  const [pending, setPending] = useState(false);
  // Transient "Copied" timer; cleared on close so a stale timeout can't flip
  // state after the dialog is gone.
  const copiedTimerRef = useRef<number | null>(null);

  // Drop a link (and its copy/error status) when the dialog closes or the
  // targeted conversation changes. Conditional setState during render is the
  // documented way to reset on a prop change; an effect would trip
  // react-hooks/set-state-in-effect.
  if (session.open !== open || session.conversationId !== conversationId) {
    setSession({
      open,
      conversationId,
      url: null,
      status: null,
      copied: false,
      error: null,
    });
  }

  // Hide Copy / Remove unless the stored link is still for this conversation.
  // The render-time reset above clears it on the next pass; this also covers
  // the pass that notices the prop change.
  const shareUrl =
    session.conversationId === conversationId ? session.url : null;

  // Reset transient state on close so a re-open starts clean. Driven from the
  // close path rather than an effect to avoid an open→render→reset cascade
  // (the repo lints react-hooks/set-state-in-effect).
  const handleOpenChange = (next: boolean) => {
    if (!next) {
      if (copiedTimerRef.current !== null) {
        window.clearTimeout(copiedTimerRef.current);
        copiedTimerRef.current = null;
      }
      setPending(false);
      setSession((current) => ({
        open: false,
        conversationId: current.conversationId,
        url: null,
        status: null,
        copied: false,
        error: null,
      }));
    }
    onOpenChange(next);
  };

  const handleCreate = async () => {
    if (pending || conversationId === null) return;
    const targetId = conversationId;
    setPending(true);
    setSession((current) =>
      current.open && current.conversationId === targetId
        ? { ...current, error: null, status: null }
        : current,
    );
    try {
      const result = await createShareLink(targetId);
      const url = absoluteShareUrl(result.sharePath);
      // A new chat (or any other selection) may have changed the prop while
      // this request was in flight. Apply the URL only if this id is still
      // the one the dialog is bound to; otherwise leave the reset in place.
      setSession((current) =>
        current.open && current.conversationId === targetId
          ? { ...current, url, status: "Share link created", error: null }
          : current,
      );
    } catch (cause) {
      const message = messageForError(cause);
      setSession((current) =>
        current.open && current.conversationId === targetId
          ? { ...current, error: message }
          : current,
      );
    } finally {
      setPending(false);
    }
  };

  const handleRevoke = async () => {
    if (pending || conversationId === null) return;
    const targetId = conversationId;
    setPending(true);
    setSession((current) =>
      current.open && current.conversationId === targetId
        ? { ...current, error: null, status: null }
        : current,
    );
    try {
      // Any 2xx (the BE returns 204) means the conversation is now unshared.
      await deleteShareLink(targetId);
      if (copiedTimerRef.current !== null) {
        window.clearTimeout(copiedTimerRef.current);
        copiedTimerRef.current = null;
      }
      setSession((current) =>
        current.open && current.conversationId === targetId
          ? {
              ...current,
              url: null,
              copied: false,
              status: "Link removed",
              error: null,
            }
          : current,
      );
    } catch (cause) {
      const message = messageForError(cause);
      setSession((current) =>
        current.open && current.conversationId === targetId
          ? { ...current, error: message }
          : current,
      );
    } finally {
      setPending(false);
    }
  };

  const handleCopy = async () => {
    if (!shareUrl) return;
    const confirmCopied = () => {
      setSession((current) =>
        current.url === null
          ? current
          : { ...current, copied: true, status: "Link copied" },
      );
      if (copiedTimerRef.current !== null) {
        window.clearTimeout(copiedTimerRef.current);
      }
      copiedTimerRef.current = window.setTimeout(() => {
        copiedTimerRef.current = null;
        setSession((current) => ({ ...current, copied: false }));
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
      setSession((current) =>
        current.url === null
          ? current
          : { ...current, status: "Press Ctrl/Cmd+C to copy the link." },
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="flex flex-col overflow-hidden sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Share chat</DialogTitle>
          <DialogDescription>
            {conversationTitle
              ? `Create a public link to "${conversationTitle}".`
              : "Create a public link to this conversation."}
          </DialogDescription>
        </DialogHeader>

        {/* Scroll body: landscape / short viewports can push the link field past
            the sheet cap under the keyboard, so the content scrolls within the
            overflow-hidden flex shell rather than clipping (ST5 §c ST-8, R6). */}
        <div className="-mr-2 min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain pr-2">
          <p className="ui-body text-muted-foreground">
            Anyone with the link can view this conversation read-only. Costs and
            usage are hidden on the shared view.
          </p>

          {shareUrl ? (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor={urlFieldId}>Public link</Label>
                <div className="flex items-center gap-2">
                  <Input
                    id={urlFieldId}
                    type="text"
                    value={shareUrl}
                    readOnly
                    onFocus={(e) => e.currentTarget.select()}
                    aria-label="Public share link"
                    className="rounded-2xl border-0 bg-muted/50 min-w-0 flex-1"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={handleCopy}
                    className="h-9 shrink-0 rounded-full px-3 [@media(hover:none)]:h-11"
                  >
                    {session.copied ? (
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
                disabled={pending || conversationId === null}
                className="-ml-2 rounded-full text-muted-foreground hover:text-foreground"
              >
                {pending ? "Removing link..." : "Remove link"}
              </Button>
            </div>
          ) : (
            <Button
              type="button"
              onClick={handleCreate}
              disabled={pending || conversationId === null}
              className="h-11 w-full rounded-full"
            >
              <Link2 aria-hidden className="size-4" />
              <span>{pending ? "Creating link..." : "Create share link"}</span>
            </Button>
          )}

          {session.error ? (
            <p id={errorId} role="alert" className="ui-body text-destructive-text">
              {session.error}
            </p>
          ) : null}

          {/* Status line for AT: announces copy / create / revoke without
              stealing focus. role="status" is an implicit aria-live=polite. */}
          <p role="status" className="sr-only">
            {session.status}
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
