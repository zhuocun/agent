"use client";

import { Children, useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";

import { Button } from "@/components/ui/button";

export function MessageList({ children }: { children: React.ReactNode }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLOListElement>(null);
  const atBottomRef = useRef(true);
  const [atBottom, setAtBottom] = useState(true);

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
    <div className="relative min-h-0 flex-1">
      <div
        ref={scrollRef}
        onScroll={recompute}
        className="chat-scroll h-full overflow-y-auto overscroll-contain"
      >
        <ol
          ref={contentRef}
          aria-label="Messages"
          // pt/pb clear the chat-thread chrome strips (header + safe-area-top
          // above; composer + safe-area-bottom below) so message content scrolls
          // *under* the gradient strips rather than colliding with them.
          className="mx-auto flex w-full max-w-3xl list-none flex-col gap-5 px-4 pt-[calc(env(safe-area-inset-top)+4.5rem)] pb-[calc(var(--bottom-inset)+9rem)] md:pt-[calc(env(safe-area-inset-top)+5.5rem)]"
        >
          {Children.map(children, (child) => (
            <li className="list-none">{child}</li>
          ))}
        </ol>
      </div>

      {!atBottom ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-[calc(var(--bottom-inset)+8rem)] z-40 flex justify-center">
          <Button
            type="button"
            variant="secondary"
            onClick={() => scrollToBottom(true)}
            aria-label="Jump to latest"
            className="pointer-events-auto h-9 gap-1.5 rounded-full border border-border px-3 shadow-sm"
          >
            <ArrowDown className="size-4" />
            Latest
          </Button>
        </div>
      ) : null}
    </div>
  );
}
