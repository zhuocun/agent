"use client";

import { Children, useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";

import { Button } from "@/components/ui/button";

// Scroll region for the thread (PRD 01 §5.1): follows the stream only while the
// user is at/near the bottom; otherwise shows a "Jump to latest" pill.
// `overscroll-contain` prevents pull-to-refresh from killing in-flight streams
// (PRD 03 §4.4).
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
    // Auto-follow growth only when the user is already pinned to the bottom.
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
        className="h-full overflow-y-auto overscroll-contain"
      >
        <ol
          ref={contentRef}
          aria-label="Messages"
          className="mx-auto flex w-full max-w-3xl list-none flex-col gap-7 px-4 py-6"
        >
          {Children.map(children, (child) => (
            <li className="list-none">{child}</li>
          ))}
        </ol>
      </div>

      {!atBottom ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center">
          <Button
            type="button"
            variant="secondary"
            onClick={() => scrollToBottom(true)}
            aria-label="Jump to latest"
            className="pointer-events-auto h-9 gap-1.5 rounded-full border border-border px-3 shadow-md"
          >
            <ArrowDown className="size-4" />
            Latest
          </Button>
        </div>
      ) : null}
    </div>
  );
}
