"use client";

import { Streamdown } from "streamdown";
import { cn } from "@/lib/utils";

// Streaming-safe markdown (PRD 01 §4.4, §5.4). Streamdown handles incomplete
// markdown mid-stream, Shiki code highlighting + copy, GFM tables, KaTeX, and
// rehype-harden-class sanitization (PRD 01 §4.4 [P0 security]). Element spacing
// and inline styling are themed via the `.chat-md` layer in globals.css.
export function MarkdownRenderer({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  return (
    <Streamdown
      parseIncompleteMarkdown
      className={cn("chat-md", className)}
    >
      {children}
    </Streamdown>
  );
}
