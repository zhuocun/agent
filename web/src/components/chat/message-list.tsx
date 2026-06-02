"use client";

import {
  Children,
  isValidElement,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ArrowDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  useVirtualMessageWindow,
  type VirtualMessageItem,
} from "@/lib/use-virtual-message-window";
import { cn } from "@/lib/utils";

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

function messageRoleOf(child: React.ReactNode): "assistant" | "user" | null {
  if (!isValidElement(child)) return null;
  const props = child.props as { message?: { role?: unknown } };
  const role = props.message?.role;
  return role === "assistant" || role === "user" ? role : null;
}

const VIRTUALIZE_AFTER = 80;
const MESSAGE_ROW_GAP_PX = 24;
const VIRTUAL_OVERSCAN_PX = 1100;
const USER_MESSAGE_ESTIMATE_PX = 96;
const ASSISTANT_MESSAGE_ESTIMATE_PX = 220;

interface RenderedMessageItem {
  key: string;
  id: string | null;
  role: "assistant" | "user" | null;
  child: React.ReactNode;
  estimateSize: number;
}

function estimateSizeForRole(role: "assistant" | "user" | null): number {
  return role === "user" ? USER_MESSAGE_ESTIMATE_PX : ASSISTANT_MESSAGE_ESTIMATE_PX;
}

function useMeasuredRow(
  key: string,
  onMeasure: (key: string, size: number) => void,
) {
  const rowRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    const row = rowRef.current;
    if (!row) return;

    const measure = () => onMeasure(key, row.getBoundingClientRect().height);
    measure();

    const ro = new ResizeObserver(measure);
    ro.observe(row);
    return () => ro.disconnect();
  }, [key, onMeasure]);

  return rowRef;
}

function MessageRow({
  item,
  index,
  total,
  isNew,
  onMeasure,
}: {
  item: RenderedMessageItem;
  index: number;
  total: number;
  isNew: boolean;
  onMeasure: (key: string, size: number) => void;
}) {
  const rowRef = useMeasuredRow(item.key, onMeasure);
  return (
    // animate-message-in carries its own reduced-motion alternate
    // (globals.css), so the class alone is the complete contract — no
    // inline transform that would fight it or overflow-anchor.
    <li
      ref={rowRef}
      data-message-role={item.role ?? undefined}
      data-testid="message-list-row"
      aria-posinset={index + 1}
      aria-setsize={total}
      className={cn(
        "chat-message-row min-w-0 list-none",
        index < total - 1 && "mb-6",
        isNew && "animate-message-in",
      )}
    >
      {item.child}
    </li>
  );
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

  // Flatten once so the id traversal, virtual-window metadata, and render loop
  // all agree on ordering.
  const items = useMemo<RenderedMessageItem[]>(() => {
    return Children.toArray(children).map((child, index) => {
      const id = messageIdOf(child);
      const role = messageRoleOf(child);
      return {
        key: id ?? `message-${index}`,
        id,
        role,
        child,
        estimateSize: estimateSizeForRole(role),
      };
    });
  }, [children]);
  const ids = items.flatMap((item) => (item.id === null ? [] : [item.id]));
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
  const virtualItems = useMemo<VirtualMessageItem[]>(
    () =>
      items.map((item) => ({
        key: item.key,
        estimateSize: item.estimateSize,
      })),
    [items],
  );
  const virtualWindow = useVirtualMessageWindow({
    enabled: items.length > VIRTUALIZE_AFTER,
    items: virtualItems,
    scrollRef,
    gapPx: MESSAGE_ROW_GAP_PX,
    overscanPx: VIRTUAL_OVERSCAN_PX,
  });
  const refreshVirtualViewport = virtualWindow.refreshViewport;
  const visibleItems = items.slice(
    virtualWindow.startIndex,
    virtualWindow.endIndex,
  );

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

  const recompute = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    const next = distance < 80;
    atBottomRef.current = next;
    setAtBottom(next);
    refreshVirtualViewport();
  }, [refreshVirtualViewport]);

  const scrollToBottom = useCallback((smooth: boolean) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    refreshVirtualViewport();
  }, [refreshVirtualViewport]);

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
  }, [scrollToBottom]);

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
              // Temporary mode adds the ~3rem TemporaryChatBanner to the top
              // chrome strip, so clear it by the banner's full height (+3rem
              // over the non-temporary offset) — a +1.5rem bump still left the
              // first message tucked under the banner.
              ? "mx-auto w-full max-w-3xl list-none px-4 pt-[calc(env(safe-area-inset-top)+7rem)] pb-[calc(var(--bottom-inset)+9rem)] md:pt-[calc(env(safe-area-inset-top)+8.5rem)]"
              : "mx-auto w-full max-w-3xl list-none px-4 pt-[calc(env(safe-area-inset-top)+4rem)] pb-[calc(var(--bottom-inset)+9rem)] md:pt-[calc(env(safe-area-inset-top)+5.5rem)]"
          }
        >
          {virtualWindow.paddingTop > 0 ? (
            <li
              aria-hidden
              className="list-none"
              style={{ height: virtualWindow.paddingTop }}
            />
          ) : null}
          {visibleItems.map((item, visibleIndex) => {
            const index = virtualWindow.startIndex + visibleIndex;
            return (
              <MessageRow
                key={item.key}
                item={item}
                index={index}
                total={items.length}
                isNew={isNew(item.id)}
                onMeasure={virtualWindow.measureItem}
              />
            );
          })}
          {virtualWindow.paddingBottom > 0 ? (
            <li
              aria-hidden
              className="list-none"
              style={{ height: virtualWindow.paddingBottom }}
            />
          ) : null}
        </ol>
      </div>

      {/* Jump-to-latest. Kept MOUNTED at all times and animated on `atBottom`
          so it springs in/out (opacity + scale + a small upward translate)
          rather than hard-mounting. Under motion-reduce it collapses to a
          plain opacity fade (no scale/translate). When hidden it's fully
          non-interactive: pointer-events-none + aria-hidden + tabIndex -1 keep
          it out of the tab order and from intercepting taps. 44pt (size-11)
          meets the iOS touch-target floor; icon-only by design. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-[calc(var(--bottom-inset)+6.5rem)] z-30 flex justify-center">
        <Button
          type="button"
          variant="secondary"
          onClick={() => scrollToBottom(true)}
          aria-label="Jump to latest"
          aria-hidden={atBottom}
          tabIndex={atBottom ? -1 : 0}
          className={cn(
            "glass-regular size-11 rounded-full p-0 transition-[opacity,transform,scale] duration-300 ease-[var(--ease-ios-spring)] motion-reduce:transition-[opacity] motion-reduce:duration-150",
            atBottom
              ? "pointer-events-none translate-y-1 scale-90 opacity-0 motion-reduce:translate-y-0 motion-reduce:scale-100"
              : "pointer-events-auto translate-y-0 scale-100 opacity-100",
          )}
        >
          <ArrowDown className="size-4" />
        </Button>
      </div>
    </div>
  );
}
