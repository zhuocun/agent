"use client";

import { useEffect, useRef, useState } from "react";
import { RotateCw, SearchX } from "lucide-react";
import Link from "next/link";
import { Loader2, MessageSquareText } from "lucide-react";

import { MarkdownRenderer } from "@/components/chat/markdown-renderer";
import { ReasoningPanel } from "@/components/chat/reasoning-panel";
import {
  SourcesPanel,
  type SourcesPanelHandle,
} from "@/components/chat/sources-panel";
import { ToolPartView } from "@/components/chat/tool-part";
import { ThemeToggle } from "@/components/chat/theme-toggle";
import { PublicAttributionRow } from "@/components/share/public-attribution-row";
import { Button } from "@/components/ui/button";
import { ApiError, fetchPublicConversation } from "@/lib/apiClient";
import type { PublicConversation, PublicMessage } from "@/lib/types";

// Read-only public-by-link snapshot. NO composer, NO sidebar, NO message
// actions (copy/regenerate/feedback), NO edit — anyone with the link reads a
// static conversation. It reuses the SAME rendering primitives as the private
// thread (MarkdownRenderer for text/answers, ReasoningPanel for reasoning) so
// shared markdown/code/reasoning behaviour stays identical; the only divergence
// is attribution, which is rendered cost-free via PublicAttributionRow because
// the public contract structurally carries no cost (web/src/lib/types.ts).
//
// Fetch is CLIENT-side via the same apiClient the rest of the app uses, which
// routes through the FE `/api/*` rewrite. That keeps one wire path and one
// error envelope, and avoids resolving the BE origin server-side (the apiClient
// reads NEXT_PUBLIC_API_BASE_URL, a browser-inlined value). A 404 (unknown or
// revoked token) maps to a friendly "no longer available" empty state.

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; conversation: PublicConversation }
  | { kind: "unavailable" }
  | { kind: "error" };

export function PublicConversationView({ token }: { token: string }) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  // Bumped by the error-state "Try again" button to re-run the fetch effect.
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    // Re-running via the retry button resets the view to the loading spinner;
    // the initial mount is already in `loading`, so only retries need this.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (attempt > 0) setState({ kind: "loading" });
    // No synchronous setState here: `loading` is the initial state, and the
    // page never swaps tokens in place (each /share/{token} is its own mount),
    // so resetting to loading on token change isn't needed. State only moves
    // forward from inside the async callback below.
    void (async () => {
      try {
        const conversation = await fetchPublicConversation(
          token,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        setState({ kind: "ready", conversation });
      } catch (cause) {
        if (controller.signal.aborted) return;
        // 404 == unknown/revoked token — the expected "gone" path, not a crash.
        if (cause instanceof ApiError && cause.status === 404) {
          setState({ kind: "unavailable" });
          return;
        }
        setState({ kind: "error" });
      }
    })();
    return () => controller.abort();
  }, [token, attempt]);

  // Reflect the conversation title in the tab once it loads. The server page
  // ships sensible static metadata; this is a low-churn enhancement that avoids
  // a server-side BE fetch for a title.
  useEffect(() => {
    if (state.kind === "ready" && state.conversation.title) {
      document.title = `${state.conversation.title} · Olune`;
    }
  }, [state]);

  return (
    <div className="relative flex min-h-dvh flex-col bg-background text-foreground">
      <PublicHeader />
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 pt-[calc(env(safe-area-inset-top)+4rem)] pb-16 md:pt-[calc(env(safe-area-inset-top)+5.5rem)]">
        {state.kind === "loading" ? <LoadingState /> : null}
        {state.kind === "unavailable" ? <UnavailableState /> : null}
        {state.kind === "error" ? (
          <ErrorState onRetry={() => setAttempt((n) => n + 1)} />
        ) : null}
        {state.kind === "ready" ? (
          <ConversationBody conversation={state.conversation} />
        ) : null}
      </main>
    </div>
  );
}

function PublicHeader() {
  return (
    // Mirrors the private top chrome (chat-thread.tsx): a light from-background
    // color gradient carries status-bar-text legibility AND is the fallback
    // separation when blur is gated, while a masked `chrome-frost` layer does
    // the refractive blur over scrolling messages. The frost drops to nothing
    // under prefers-reduced-transparency / no-backdrop-filter (see globals.css),
    // leaving the opaque-enough gradient so the title + buttons never render
    // over bare scrolling text.
    <header className="fixed inset-x-0 top-0 z-40 flex h-[46px] items-center gap-2 bg-gradient-to-b from-background/70 via-background/30 to-background/0 px-[max(env(safe-area-inset-left),1.25rem)] pr-[max(env(safe-area-inset-right),1.25rem)] pt-[env(safe-area-inset-top)] md:h-16">
      <div
        aria-hidden
        className="chrome-frost pointer-events-none absolute inset-0 -z-10"
        style={{
          maskImage: "linear-gradient(to bottom, black, transparent)",
          WebkitMaskImage: "linear-gradient(to bottom, black, transparent)",
        }}
      />
      <Link
        href="/"
        className="flex items-center gap-2 rounded-sm font-medium text-foreground outline-none focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
        aria-label="Olune home"
      >
        <span className="text-base font-semibold tracking-tight">Olune</span>
        <span className="hidden text-sm text-muted-foreground sm:inline">
          · shared chat
        </span>
      </Link>
      <div className="ml-auto flex items-center gap-1">
        <ThemeToggle />
        <Button
          nativeButton={false}
          render={<Link href="/" />}
          variant="secondary"
          className="h-11 rounded-full px-3.5 text-sm sm:h-9"
        >
          Start your own chat
        </Button>
      </div>
    </header>
  );
}

function ConversationBody({
  conversation,
}: {
  conversation: PublicConversation;
}) {
  return (
    <div className="flex flex-1 flex-col">
      <div className="mb-6 space-y-1">
        <h1
          className="text-balance text-2xl font-semibold tracking-tight"
          data-testid="public-conversation-title"
        >
          {conversation.title}
        </h1>
        <p className="text-sm text-muted-foreground">
          A read-only shared conversation.
        </p>
      </div>

      {conversation.messages.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          This conversation has no messages yet.
        </p>
      ) : (
        <ol className="flex list-none flex-col gap-6">
          {conversation.messages.map((message) => (
            <li key={message.id} className="min-w-0 list-none">
              <PublicMessageItem message={message} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function PublicMessageItem({ message }: { message: PublicMessage }) {
  // Hooks must run unconditionally, so they sit above the user-message early
  // return (harmless for user turns, which have no sources).
  const sourcesPanelRef = useRef<SourcesPanelHandle>(null);
  const sourceItems =
    message.parts.find((p) => p.type === "sources")?.items ?? [];

  if (message.role === "user") {
    const text = message.parts
      .filter((p) => p.type === "text")
      .map((p) => p.text)
      .join("\n\n");
    return (
      <div
        className="flex flex-col items-end"
        role="article"
        aria-label="User message"
      >
        <div
          data-testid="public-user-message"
          className="max-w-[85%] whitespace-pre-wrap break-words rounded-3xl bg-brand-muted px-5 py-3 text-[1.0625rem] leading-7 text-foreground shadow-[var(--glass-highlight),inset_0_0_0_1px_var(--glass-border)] md:text-[0.9375rem]"
        >
          {text}
        </div>
      </div>
    );
  }

  // Assistant (and any system) turns: render reasoning + text parts with the
  // same primitives as the private thread, then a cost-free attribution byline.
  return (
    <div
      className="space-y-3 break-words text-foreground"
      role="article"
      aria-label="Assistant message"
      data-testid="public-assistant-message"
    >
      {message.parts.map((part, idx) => {
        if (part.type === "reasoning") {
          return (
            <ReasoningPanel
              key={idx}
              text={part.text}
              durationSec={part.durationSec}
              isStreaming={false}
            />
          );
        }
        if (part.type === "text") {
          return part.text ? (
            <div key={idx} data-testid="public-assistant-answer">
              <MarkdownRenderer
                sources={sourceItems}
                onCitationClick={(id) =>
                  sourcesPanelRef.current?.revealSource(id)
                }
              >
                {part.text}
              </MarkdownRenderer>
            </div>
          ) : null;
        }
        if (part.type === "sources") {
          // Citations are not cost-bearing, so they survive the share strip and
          // render with the same primitive as the private thread — a shared
          // grounded answer keeps its sources, and an ungrounded turn keeps its
          // honesty marker.
          if (part.items.length === 0) {
            return part.requested ? <PublicUngroundedMarker key={idx} /> : null;
          }
          return (
            <SourcesPanel key={idx} ref={sourcesPanelRef} items={part.items} />
          );
        }
        if (part.type === "tool_call" || part.type === "tool_result") {
          return <ToolPartView key={idx} part={part} />;
        }
        // `status` parts are an in-flight streaming affordance; a static
        // snapshot has no live status, so they're intentionally omitted.
        return null;
      })}

      {message.attribution ? (
        <div className="pt-1">
          <PublicAttributionRow attribution={message.attribution} />
        </div>
      ) : null}
    </div>
  );
}

// Mirror of the private thread's ungrounded honesty marker (PRD 07 §4.3) so a
// shared ungrounded turn reads "Answered without live sources" too.
function PublicUngroundedMarker() {
  return (
    <div
      className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
      data-testid="ungrounded-marker"
    >
      <SearchX aria-hidden className="size-3.5" />
      <span>Answered without live sources</span>
    </div>
  );
}

function LoadingState() {
  return (
    <div
      className="flex flex-1 items-center justify-center py-24 text-muted-foreground"
      role="status"
    >
      <Loader2 className="size-5 motion-safe:animate-spin" aria-hidden />
      <span className="sr-only">Loading shared conversation…</span>
    </div>
  );
}

function UnavailableState() {
  return (
    <EmptyState
      title="This shared conversation is no longer available"
      body="The link may have been revoked, or it never existed. Ask whoever shared it for an up-to-date link."
    />
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <EmptyState
      title="Couldn't load this conversation"
      body="Something went wrong reaching the server. Check your connection and try again."
      onRetry={onRetry}
    />
  );
}

function EmptyState({
  title,
  body,
  onRetry,
}: {
  title: string;
  body: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="flex flex-1 flex-col items-center justify-center gap-4 py-24 text-center"
      data-testid="public-unavailable"
    >
      <div className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <MessageSquareText className="size-6" aria-hidden />
      </div>
      <div className="space-y-1.5">
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        <p className="mx-auto max-w-sm text-sm text-muted-foreground">{body}</p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        {onRetry ? (
          <Button
            type="button"
            variant="secondary"
            onClick={onRetry}
            className="h-10 rounded-full px-4 text-sm"
          >
            <RotateCw aria-hidden className="size-4" />
            <span>Try again</span>
          </Button>
        ) : null}
        <Button
          nativeButton={false}
          render={<Link href="/" />}
          className="h-10 rounded-full px-4 text-sm"
        >
          Start your own chat
        </Button>
      </div>
    </div>
  );
}
