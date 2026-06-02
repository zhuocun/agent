"use client";

import { useState } from "react";
import { ChevronDown, Globe } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { SourceItem } from "@/lib/types";

export interface SourcesPanelProps {
  items: SourceItem[];
  // Open by default once the answer has settled so the grounding is visible
  // without a tap; the user can still collapse it. Mirrors ReasoningPanel's
  // `defaultOpen` knob.
  defaultOpen?: boolean;
}

// Grounded-answer source cards. Modeled on ReasoningPanel: a collapsible
// disclosure whose trigger states the count and whose body is a keyboard-
// navigable list of source cards (favicon + linked title + domain + snippet).
export function SourcesPanel({ items, defaultOpen = true }: SourcesPanelProps) {
  const [open, setOpen] = useState(defaultOpen);

  if (items.length === 0) return null;

  const label = items.length === 1 ? "1 source" : `${items.length} sources`;

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      // E2E target: avoids depending on the "N sources" label text.
      data-testid="sources-panel"
      className="text-muted-foreground"
    >
      <CollapsibleTrigger
        className={cn(
          "group/sources-trigger inline-flex items-center gap-1 text-left text-xs text-muted-foreground",
          // Tap target: grow the hit area vertically to clear the iOS 44pt floor
          // without disturbing the surrounding gap stack (same trick as
          // ReasoningPanel).
          "bg-transparent py-1.5 -my-1.5 underline-offset-2",
          "outline-none focus-visible:underline",
        )}
        aria-label={open ? `Hide ${label}` : `Show ${label}`}
      >
        <Globe aria-hidden className="size-3.5" />
        <span>{label}</span>
        <ChevronDown
          aria-hidden
          className="size-3.5 transition-transform duration-300 ease-[var(--ease-ios-spring)] group-data-[panel-open]/sources-trigger:rotate-180"
        />
      </CollapsibleTrigger>

      <CollapsibleContent
        keepMounted
        className={cn(
          "overflow-hidden",
          "transition-[height,opacity] duration-200 ease-[var(--ease-ios-smooth)]",
          "h-[var(--collapsible-panel-height)] opacity-100",
          "data-[starting-style]:h-0 data-[starting-style]:opacity-0",
          "data-[ending-style]:h-0 data-[ending-style]:opacity-0",
        )}
      >
        <ul className="mt-2 flex flex-col gap-2">
          {items.map((item) => (
            <li key={item.id}>
              <SourceCard item={item} />
            </li>
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}

function SourceCard({ item }: { item: SourceItem }) {
  // Prefer the explicit domain; fall back to parsing the URL host so the
  // favicon + label still render when the BE omits `domain`.
  const domain = item.domain ?? hostFromUrl(item.url);
  const faviconUrl = domain
    ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32`
    : null;

  // Belt-and-suspenders: the BE already drops non-http(s) URLs, but result URLs
  // are attacker-influenceable and this card also renders on the unauthenticated
  // public share view. Only emit a clickable href for a plain web URL; anything
  // else renders as non-clickable text so a bad scheme (javascript:, data:, …)
  // can never become a live link.
  const clickable = isHttpUrl(item.url);

  const cardClassName = cn(
    "flex items-start gap-3 rounded-xl border border-foreground/[0.06] bg-foreground/[0.02] p-3",
    "transition-colors",
    clickable && "hover:bg-foreground/[0.04]",
    "outline-none focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
  );

  const body = (
    <>
      <span
        aria-hidden
        className="mt-0.5 flex size-5 shrink-0 items-center justify-center overflow-hidden rounded text-muted-foreground"
      >
        {faviconUrl ? (
          // A bare <img> (not next/image) is deliberate: the favicon comes from
          // an arbitrary open-web domain, which `next/image` remotePatterns
          // can't enumerate, and it's a throwaway 20px glyph with a Globe
          // fallback — nothing to optimize.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={faviconUrl}
            alt=""
            width={20}
            height={20}
            loading="lazy"
            className="size-5 rounded"
            onError={(e) => {
              // Hide a broken favicon so the lucide Globe behind it (sibling)
              // shows through cleanly rather than a broken-image glyph.
              e.currentTarget.style.display = "none";
            }}
          />
        ) : (
          <Globe className="size-4" />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline gap-2">
          <span className="truncate text-sm font-medium text-foreground">
            {item.title}
          </span>
          {domain ? (
            <span className="shrink-0 truncate text-2xs text-muted-foreground">
              {domain}
            </span>
          ) : null}
        </span>
        {item.snippet ? (
          <span className="mt-0.5 line-clamp-2 block text-xs leading-snug text-muted-foreground">
            {item.snippet}
          </span>
        ) : null}
      </span>
    </>
  );

  if (!clickable) {
    // Unsafe / non-web URL: render the card as static, non-clickable text so an
    // attacker-supplied scheme can never become a live link.
    return (
      <div data-testid="source-card" className={cardClassName}>
        {body}
      </div>
    );
  }

  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      data-testid="source-card"
      className={cardClassName}
    >
      {body}
    </a>
  );
}

// True only for a plain http(s) URL. Mirrors the BE scheme allow-list so a
// non-web URL (javascript:, data:, …) is never rendered as a clickable href —
// belt-and-suspenders for the unauthenticated public share view.
function isHttpUrl(url: string): boolean {
  return /^https?:\/\//i.test(url.trim());
}

// Best-effort host extraction for the favicon + label when the BE omits the
// `domain` field. Strips a leading `www.`; returns "" on an unparseable URL so
// the caller falls back to the Globe glyph.
function hostFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}
