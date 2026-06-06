"use client";

import {
  forwardRef,
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
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
  // Collapsed at rest so the thread stays quiet (progressive disclosure):
  // the always-visible "N sources" + Globe trigger is the summary, and the
  // per-source cards expand on a tap. Brings sources into parity with the
  // reasoning panel, which also defaults collapsed post-stream. An inline
  // `[n]` citation still reveals its card — `revealSource` opens the panel
  // and `keepMounted` keeps the card refs populated while collapsed. Mirrors
  // ReasoningPanel's `defaultOpen` knob.
  defaultOpen?: boolean;
}

// Imperative handle so an inline `[n]` citation marker can reveal the matching
// source card: open the panel (if collapsed), scroll the card into view, and
// briefly highlight it.
export interface SourcesPanelHandle {
  revealSource: (id: number) => void;
}

// How long the highlight pulse stays on a revealed source card (ms).
const HIGHLIGHT_MS = 1600;

// "From the web" today; the other origins are reserved (PRD 07 §4.3) and not
// yet produced by the backend, but the label is ready for them.
function provenanceLabel(p: SourceItem["provenance"]): string {
  switch (p) {
    case "knowledge":
      return "From your documents";
    case "connector":
      return "From a connector";
    default:
      return "From the web";
  }
}

// Grounded-answer source cards. Modeled on ReasoningPanel: a collapsible
// disclosure whose trigger states the count and whose body is a keyboard-
// navigable list of source cards (favicon + linked title + domain + snippet).
export const SourcesPanel = forwardRef<SourcesPanelHandle, SourcesPanelProps>(
  function SourcesPanel({ items, defaultOpen = false }, ref) {
    const [open, setOpen] = useState(defaultOpen);
    const [highlightId, setHighlightId] = useState<number | null>(null);
    const cardRefs = useRef(new Map<number, HTMLElement | null>());
    const highlightTimer = useRef<number | null>(null);
    const baseId = useId();

    useImperativeHandle(
      ref,
      () => ({
        revealSource(id: number) {
          // Open first so the card is laid out, then scroll + pulse-highlight.
          // `keepMounted` on the content means the refs are populated even when
          // the panel was collapsed, so the scroll target always exists.
          setOpen(true);
          setHighlightId(id);
          requestAnimationFrame(() => {
            cardRefs.current
              .get(id)
              ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
          });
          if (highlightTimer.current !== null) {
            window.clearTimeout(highlightTimer.current);
          }
          highlightTimer.current = window.setTimeout(() => {
            setHighlightId(null);
            highlightTimer.current = null;
          }, HIGHLIGHT_MS);
        },
      }),
      [],
    );

    useEffect(
      () => () => {
        if (highlightTimer.current !== null) {
          window.clearTimeout(highlightTimer.current);
        }
      },
      [],
    );

    if (items.length === 0) return null;

    const label = items.length === 1 ? "1 source" : `${items.length} sources`;
    // Provenance is uniform per turn today (web). Derive from the first tagged
    // item, defaulting to web when the BE omits it.
    const provenance = items.find((it) => it.provenance)?.provenance ?? "web";

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
          <p
            className="mt-2 text-2xs text-muted-foreground"
            data-testid="sources-provenance"
          >
            {provenanceLabel(provenance)}
          </p>
          <ul className="mt-1.5 flex flex-col gap-2">
            {items.map((item) => (
              <li key={item.id}>
                <SourceCard
                  item={item}
                  cardId={`${baseId}-source-${item.id}`}
                  highlighted={highlightId === item.id}
                  registerRef={(el) => {
                    if (el) cardRefs.current.set(item.id, el);
                    else cardRefs.current.delete(item.id);
                  }}
                />
              </li>
            ))}
          </ul>
        </CollapsibleContent>
      </Collapsible>
    );
  },
);

function SourceCard({
  item,
  cardId,
  highlighted,
  registerRef,
}: {
  item: SourceItem;
  cardId: string;
  highlighted: boolean;
  registerRef: (el: HTMLElement | null) => void;
}) {
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
    "transition-[background-color,box-shadow] duration-300",
    clickable && "hover:bg-foreground/[0.04]",
    "outline-none focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
    // Transient pulse when an inline `[n]` marker reveals this card. Kept
    // prominent (clear ring + tint) so the jump-to-source is unmistakable even
    // when the card is already on screen.
    highlighted &&
      "bg-primary/10 shadow-[0_0_0_2.5px_var(--color-primary)] scroll-mt-4",
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
      <div
        ref={registerRef}
        id={cardId}
        data-testid="source-card"
        data-source-id={item.id}
        className={cardClassName}
      >
        {body}
      </div>
    );
  }

  return (
    <a
      ref={registerRef}
      id={cardId}
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      data-testid="source-card"
      data-source-id={item.id}
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
