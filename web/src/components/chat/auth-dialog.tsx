"use client";

import { useId, useState, type FormEvent, type JSX } from "react";

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
  postAuthLogin,
  postAuthUpgrade,
} from "@/lib/apiClient";
import type { AccountInfo } from "@/lib/types";

type AuthMode = "signin" | "signup";

export interface AuthDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Fired after a successful sign-in / account creation. The parent re-resolves
  // identity (re-runs bootstrap) so the whole shell reflects the new session.
  onSuccess: (account: AccountInfo) => void;
}

// Map the frozen backend error contract to short, non-enumerating copy. Anything
// we don't recognize falls through to a generic message so a surprise status
// (or a network blip) never leaves the form silent.
function messageForError(cause: unknown, mode: AuthMode): string {
  if (cause instanceof ApiError) {
    if (cause.status === 429) {
      return "Too many attempts. Try again in a minute.";
    }
    if (cause.code === "INVALID_CREDENTIALS") {
      return "Incorrect email or password.";
    }
    if (cause.code === "EMAIL_TAKEN") {
      return "An account with that email already exists.";
    }
    if (cause.code === "ALREADY_UPGRADED") {
      return "This session is already linked to an account. Sign in instead.";
    }
    // Surface the server's own copy for validation (400) and anything else.
    return cause.body || cause.title;
  }
  if (cause instanceof ApiNetworkError) {
    return "Couldn't reach the server. Check your connection and try again.";
  }
  return mode === "signin"
    ? "Couldn't sign you in. Please try again."
    : "Couldn't create your account. Please try again.";
}

// Sign-in / create-account modal. A single dialog hosts both flows with an
// in-place toggle so a guest can switch intent without losing the surface.
// Styling, focus management, escape-to-close and swipe-to-dismiss all ride on
// the shared <DialogContent> shell (matches settings-dialog.tsx).
export function AuthDialog({
  open,
  onOpenChange,
  onSuccess,
}: AuthDialogProps): JSX.Element {
  const emailId = useId();
  const passwordId = useId();
  const errorId = useId();

  const [mode, setMode] = useState<AuthMode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Reset transient form state on close so a re-open starts clean (no stale
  // error, no leftover password in memory). Driven from the close path rather
  // than an effect to avoid an open→render→reset cascade.
  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setMode("signin");
      setEmail("");
      setPassword("");
      setError(null);
      setPending(false);
    }
    onOpenChange(next);
  };

  const switchMode = () => {
    setMode((m) => (m === "signin" ? "signup" : "signin"));
    setError(null);
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (pending) return;

    const trimmedEmail = email.trim();
    if (trimmedEmail.length === 0 || password.length === 0) {
      setError("Enter your email and password.");
      return;
    }

    setPending(true);
    setError(null);
    try {
      const account =
        mode === "signin"
          ? await postAuthLogin(trimmedEmail, password)
          : await postAuthUpgrade({ email: trimmedEmail, password });
      onSuccess(account);
    } catch (cause) {
      setError(messageForError(cause, mode));
    } finally {
      setPending(false);
    }
  };

  const isSignIn = mode === "signin";
  const title = isSignIn ? "Sign in" : "Create account";
  const description = isSignIn
    ? "Sign in to sync your chats and bring your own API key."
    : "Create an account to keep your chats and bring your own API key.";
  const submitLabel = pending
    ? isSignIn
      ? "Signing in..."
      : "Creating account..."
    : isSignIn
      ? "Sign in"
      : "Create account";

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <label htmlFor={emailId} className="text-sm font-medium">
              Email
            </label>
            <input
              id={emailId}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              required
              disabled={pending}
              aria-invalid={error !== null}
              aria-describedby={error ? errorId : undefined}
              placeholder="you@example.com"
              className="block h-11 w-full rounded-2xl bg-muted/50 px-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:shadow-[var(--focus-ring)] disabled:opacity-50"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor={passwordId} className="text-sm font-medium">
              Password
            </label>
            <input
              id={passwordId}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={isSignIn ? "current-password" : "new-password"}
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              required
              disabled={pending}
              aria-invalid={error !== null}
              aria-describedby={error ? errorId : undefined}
              placeholder="••••••••"
              className="block h-11 w-full rounded-2xl bg-muted/50 px-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:shadow-[var(--focus-ring)] disabled:opacity-50"
            />
          </div>

          {error ? (
            <p id={errorId} role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}

          <Button
            type="submit"
            disabled={pending}
            className="h-11 w-full rounded-full"
          >
            {submitLabel}
          </Button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          {isSignIn ? "New here?" : "Already have an account?"}{" "}
          <button
            type="button"
            onClick={switchMode}
            disabled={pending}
            className="font-medium text-foreground underline-offset-2 hover:underline focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none disabled:opacity-50"
          >
            {isSignIn ? "Create an account" : "Sign in"}
          </button>
        </p>
      </DialogContent>
    </Dialog>
  );
}
