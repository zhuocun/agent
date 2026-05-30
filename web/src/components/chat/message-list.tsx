"use client";

import {
  Children,
  isValidElement,
  useEffect,
  useRef,
  useState,
} from "react";
import { ArrowDown } from "lucide-react";

import { Button } from "@/components/ui/button";

// Pull the stable message id off a rendered child. UserMessage/AssistantMessage
// both take a `message` prop (see chat-thread.tsx) — that id is what we track
// for entrance animation. We can't read React `key`s here, and MessageList is
// only ever fed those two element types, so `props.message.id` is the contract.
function messageIdOf(child: React.ReactNode): string | null {
  if (!isValidElement(child)) return null;
  const props = child.props as { message?: { id?: unknown } };
  const id = props.message?.id;
  return typeof id === "string" ? id : null;
}

export function MessageList({
  children,
  isTemporary = false,
}: {
  children: React.ReactNode;
  isTemporary?: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLOListElement>(null);
  const atBottomRef = useRef(true);
  const [atBottom, setAtBottom] = useState(true);

  // Per-message entrance: only messages *appended while the list is already
  // showing* animate. Existing history (initial mount, conversation open, and
  // conversation switch) renders statically — a sibling slice owns the switch
  // cross-fade.
  //
  // `entered` is an ADDITIVE, STICKY set of ids that have earned the entrance
  // class. It lives in state (reading state during render is fine) and only
  // grows within a conversation, so once a render applies `animate-message-in`
  // to a node, no later render strips it. That stickiness is the whole point:
  // a keyframe animation fires when `animation-name` goes none→named on an
  // element, so we apply the class on the render *after* the append is detected
  // and then leave it there — the animation starts cleanly and is never aborted
  // mid-flight. (The prior attempt removed the class on the very next commit,
  // which cancelled the keyframe before paint.) The set is reset to empty on a
  // conversation switch so it can't leak the old thread's ids or grow unbounded.
  const [entered, setEntered] = useState<Set<string>>(() => new Set());

  // Ids present this render. Use Children.map (not toArray) so the traversal
  // matches the render loop and the post-commit effect exactly.
  const ids: string[] = [];
  Children.map(children, (child) => {
    const id = messageIdOf(child);
    if (id !== null) ids.push(id);
  });
  // A stable primitive view of `ids` for the effect's dependency array. `ids`
  // is rebuilt every render so it can't be a dep directly (referentially new
  // each time → behaves like no deps while falsely implying stability). The
  // joined string changes iff the id sequence changes, which is exactly when
  // the reconcile below must run — so depending on it is both correct AND
  // satisfies react-hooks/exhaustive-deps without a disable. "\n" can't appear
  // in a uuid or `local-…` id, so the join is unambiguous.
  const idsKey = ids.join("\n");

  // The id list committed by the *previous* paint. A ref, not state: we only
  // read/write it INSIDE the post-paint effect below, never during render, so
  // React 19's refs-during-render rule is satisfied. `null` means we haven't
  // committed yet (first commit) — its history must render static.
  const prevIdsRef = useRef<string[] | null>(null);

  // A message animates iff its id is in the sticky `entered` set. Everything
  // else (initial history, switched-in history, streaming token re-renders, and
  // the terminal placeholder→server-id same-length swap) renders static because
  // the effect below never adds those ids to the set.
  const isNew = (id: string | null): boolean => id !== null && entered.has(id);

  // Detect genuine appends AFTER paint (useEffect, not useLayoutEffect, so the
  // just-applied entrance class is allowed to paint before any bookkeeping).
  // Writing AND reading `prevIdsRef` here is allowed — the lint rule only
  // forbids ref access during render. We compare this commit's id list to the
  // previous one and decide whether each transition is an append or a bulk swap.
  //
  // First commit (prevIdsRef null/empty): the initial history is marked seen
  // WITHOUT animating. Disjoint id set (conversation switch): reset `entered`
  // and mark the new ids seen without animating. List did NOT grow (deletion,
  // regenerate trim, or the streaming terminal same-length id-swap): static.
  // Only a true append — same conversation AND the list grew — adds the
  // newly-present ids to `entered` so the next render animates them once.
  //
  // The dep is `idsKey` (a primitive faithfully tracking `ids`), so the effect
  // re-runs exactly when the id sequence changes — every commit that matters
  // for entrance bookkeeping — and the lint rule is satisfied honestly (no
  // disable). Under StrictMode's double-invoked effects the second run sees
  // prevIdsRef already advanced to the current ids, so the id-set compares
  // equal (not disjoint) and the diff (current minus previous) is empty —
  // nothing is double-marked or skipped.
  useEffect(() => {
    // Reconstruct this commit's id list from the primitive dep so the effect
    // body depends only on `idsKey` (an empty key = an empty list, not [""]).
    const current = idsKey === "" ? [] : idsKey.split("\n");
    const prev = prevIdsRef.current;
    const prevSet = new Set(prev ?? []);
    // "First commit" = no prior commit (prev === null) OR the prior commit was
    // empty: in both cases this is an initial/bulk load, not an append into an
    // already-populated list, so the whole list must render static. (In this
    // app MessageList unmounts whenever the thread is empty — chat-thread shows
    // the welcome surface instead — so it normally remounts fresh with the full
    // history; this empty-prev guard is the belt-and-braces that keeps a
    // bulk-populate from animating every row even if that ever changes.)
    const firstCommit = prev === null || prev.length === 0;
    // Disjoint = a switch/fresh-load swapped in an entirely new id set.
    const disjoint =
      !firstCommit && !current.some((id) => prevSet.has(id));
    const grew = current.length > (prev?.length ?? 0);

    if (firstCommit || disjoint) {
      // Bulk: render the whole list static. Reset the set on a switch so the
      // departed conversation's ids don't linger (and the set stays bounded).
      setEntered((cur) => (cur.size === 0 ? cur : new Set()));
    } else if (grew) {
      // Genuine append in the same conversation — flag only the new ids.
      const added = current.filter((id) => !prevSet.has(id));
      if (added.length > 0) {
        setEntered((cur) => {
          const next = new Set(cur);
          for (const id of added) next.add(id);
          return next;
        });
      }
    }
    // else: same length, overlapping ids (token re-render, terminal id-swap,
    // deletion) — leave `entered` untouched so nothing (re-)animates.

    prevIdsRef.current = current;
  }, [idsKey]);

  const recompute = () => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    const next = distance < 80;
    atBottomRef.current = next;
    setAtBottom(next);
  };

  const scrollToBottom = (smooth: boolean) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  };

  useEffect(() => {
    scrollToBottom(false);
    const content = contentRef.current;
    if (!content) return;
    // Auto-follow growth only while user is pinned at bottom.
    const ro = new ResizeObserver(() => {
      if (atBottomRef.current) scrollToBottom(false);
    });
    ro.observe(content);
    return () => ro.disconnect();
  }, []);

  return (
    <div className="relative min-h-0 min-w-0 flex-1 overflow-x-hidden">
      <div
        ref={scrollRef}
        onScroll={recompute}
        role="region"
        aria-label="Messages"
        tabIndex={0}
        // overflow-anchor:auto lets the browser keep the viewport visually
        // pinned when content *above* the current scroll position reflows
        // (e.g. an expanding reasoning panel earlier in the thread), so the
        // reader doesn't get shoved. The JS ResizeObserver below still owns
        // the "follow new tokens at the bottom" behavior; these are
        // complementary — anchoring handles above-fold reflow, the observer
        // handles below-fold growth.
        style={{ overflowAnchor: "auto" }}
        className="chat-scroll h-full overflow-y-auto overscroll-contain"
      >
        <ol
          ref={contentRef}
          // pt/pb clear the chat-thread chrome strips (header + safe-area-top
          // above; composer + safe-area-bottom below) so message content scrolls
          // *under* the gradient strips rather than colliding with them. The top
          // padding bumps +1.5rem in a temporary chat, where the chrome strip is
          // taller (it carries the "Temporary chat" banner above the header) —
          // mirroring the welcome surface's delta so the first message clears it.
          className={
            isTemporary
              ? "mx-auto flex w-full max-w-3xl list-none flex-col gap-6 px-4 pt-[calc(env(safe-area-inset-top)+5.5rem)] pb-[calc(var(--bottom-inset)+9rem)] md:pt-[calc(env(safe-area-inset-top)+7rem)]"
              : "mx-auto flex w-full max-w-3xl list-none flex-col gap-6 px-4 pt-[calc(env(safe-area-inset-top)+4rem)] pb-[calc(var(--bottom-inset)+9rem)] md:pt-[calc(env(safe-area-inset-top)+5.5rem)]"
          }
        >
          {Children.map(children, (child) => (
            // animate-message-in carries its own reduced-motion alternate
            // (globals.css), so the class alone is the complete contract — no
            // inline transform that would fight it or overflow-anchor.
            <li
              className={
                isNew(messageIdOf(child))
                  ? "min-w-0 list-none animate-message-in"
                  : "min-w-0 list-none"
              }
            >
              {child}
            </li>
          ))}
        </ol>
      </div>

      {!atBottom ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-[calc(var(--bottom-inset)+6.5rem)] z-40 flex justify-center">
          <Button
            type="button"
            variant="secondary"
            onClick={() => scrollToBottom(true)}
            aria-label="Jump to latest"
            className="glass-regular pointer-events-auto h-11 gap-1.5 rounded-full px-3"
          >
            <ArrowDown className="size-4" />
            Jump to latest
          </Button>
        </div>
      ) : null}
    </div>
  );
}
