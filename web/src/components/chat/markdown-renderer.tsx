"use client";

import { Streamdown } from "streamdown";
import { cn } from "@/lib/utils";

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
