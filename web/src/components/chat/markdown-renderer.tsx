"use client";

import { useEffect, useMemo, useRef, type ReactNode, type RefObject } from "react";
import type { MermaidConfig } from "mermaid";
import {
  type Components,
  type DiagramPlugin,
  type MermaidErrorComponentProps,
  type PluginConfig,
  type StreamdownProps,
  Streamdown,
  defaultRehypePlugins,
} from "streamdown";
import { useTheme } from "next-themes";

import { cn } from "@/lib/utils";
import type { SourceItem } from "@/lib/types";
import { stripToolMarkup } from "@/lib/strip-tool-markup";
import { CITATION_TAG, createCitationRehypePlugin } from "./citation-rehype";

// Mirror of Streamdown's internal `MermaidInstance` interface (not exported
// from the package). Matches `getMermaid`'s return contract in
// streamdown@2.5.0's index.d.ts.
type MermaidInstance = {
  initialize: (config: MermaidConfig) => void;
  render: (id: string, source: string) => Promise<{ svg: string }>;
};

// Streamdown does NOT ship a default Mermaid plugin: its `plugins` context
// defaults to `null`, so a ```mermaid fence renders the in-library "Mermaid
// plugin not available" notice unless we supply a `DiagramPlugin` ourselves
// (verified in streamdown@2.5.0 compiled source — `dist/chunk-BO2N2NFS.js`:
// `Ve.Provider value={g ?? null}` + the `de()=>ct().mermaid` lookup). The
// top-level `mermaid` prop only carries `{ config, errorComponent }`; it does
// not activate rendering on its own. So we register a `plugins.mermaid` whose
// `getMermaid` lazily `import("mermaid")`s — keeping the ~500KB mermaid bundle
// out of the initial chunk and off the SSR path. Streamdown itself defers the
// diagram render until the code fence closes (its incomplete-fence gate plus an
// IntersectionObserver), so streaming half-diagrams never render.
let mermaidModule: Promise<MermaidInstance> | null = null;

function loadMermaid(config?: MermaidConfig): Promise<MermaidInstance> {
  if (!mermaidModule) {
    mermaidModule = import("mermaid").then(
      (mod) => mod.default as unknown as MermaidInstance,
    );
  }
  return mermaidModule.then((instance) => {
    // Re-initialize on every call so a theme change (config.theme) actually
    // re-themes diagrams: mermaid.render() reads theme from the global state set
    // by the last initialize(), so caching initialize() to the first config
    // would freeze the theme. startOnLoad:false — we drive render() via
    // Streamdown and never let mermaid scan the DOM on import. securityLevel is
    // pinned AFTER the spread: diagram source is untrusted model output, so
    // "strict" (DOMPurify-sanitized labels, no click handlers / arbitrary HTML)
    // must stay authoritative and un-overridable by config. Never "loose".
    instance.initialize({ startOnLoad: false, ...config, securityLevel: "strict" });
    return instance;
  });
}

// `getMermaid` is sync in Streamdown's contract (DiagramPlugin) but returns an
// object whose `render` resolves async; we return a thin wrapper that kicks off
// (and caches) the dynamic import and proxies `initialize`/`render` to it.
const mermaidPlugin: DiagramPlugin = {
  name: "mermaid",
  type: "diagram",
  language: "mermaid",
  getMermaid: (config?: MermaidConfig): MermaidInstance => ({
    initialize: () => {
      // Warm the dynamic import. The actual mermaid.initialize() runs inside
      // loadMermaid() and is re-applied with the current config on every
      // render() call below, so theme changes take effect.
      void loadMermaid(config);
    },
    render: async (id: string, source: string) => {
      const instance = await loadMermaid(config);
      return instance.render(id, source);
    },
  }),
};

// On parse failure, show the raw mermaid source instead of blanking the message.
function MermaidError({ chart }: MermaidErrorComponentProps) {
  return (
    <pre className="chat-md-mermaid-error overflow-x-auto whitespace-pre-wrap rounded-md border bg-muted p-3 font-mono text-sm">
      <code>{chart}</code>
    </pre>
  );
}

// Interactive inline citation chip rendered for a `<citationmarker>` element
// produced by the citation rehype plugin. Keyboard-focusable; activating it
// reveals the matching source card. The literal `[n]` text is preserved as the
// chip's label so copy/paste of the answer still reads naturally.
function CitationChip({
  children,
  onActivate,
  adjacent = false,
}: {
  children?: ReactNode;
  onActivate: (id: number) => void;
  /** Directly follows another marker (`[1][2]`), per the rehype plugin. */
  adjacent?: boolean;
}) {
  const label =
    typeof children === "string"
      ? children
      : Array.isArray(children)
        ? children.join("")
        : String(children ?? "");
  const match = /\[(\d{1,4})\]/.exec(label);
  if (!match) return <>{children}</>;
  const id = Number(match[1]);

  return (
    <button
      type="button"
      data-testid="citation-marker"
      data-citation-id={id}
      onClick={(e) => {
        e.preventDefault();
        onActivate(id);
      }}
      aria-label={`Jump to source ${id}`}
      className={cn(
        "inline-flex items-baseline align-baseline rounded px-0.5 text-[0.85em] font-medium leading-none",
        // Hit-slop: the painted chip is ~22x13 px. An invisible ::before grows
        // the clickable region to the 24 px pointer floor (UI-TOUCH-2) and, on
        // touch, to 44 px wide without changing the type size or the line box.
        // On touch its height stops at the 28 px prose line box, so it never
        // takes taps from the line above or below (UI-TOUCH-3, §15 C50).
        "relative before:absolute before:-inset-x-0.5 before:-inset-y-1.5 before:content-['']",
        // A marker that follows another starts its slop at its own edge, so
        // two pointer slops never overlap.
        adjacent && "before:left-0",
        "[@media(hover:none)]:before:-inset-x-[11px] [@media(hover:none)]:before:top-[calc((100%-1.75rem)/2)] [@media(hover:none)]:before:bottom-[calc((100%-1.75rem)/2)]",
        // Two touch hit-slops of 11 px would overlap across a run like
        // `[1][2]`, so a tap on the right of [1] opened source 2
        // (UI-TOUCH-3). On touch, a marker that follows another is pushed
        // clear of its neighbour's slop.
        adjacent && "[@media(hover:none)]:ml-[22px]",
        "text-primary bg-primary/[0.08] hover:bg-primary/15",
        "cursor-pointer transition-colors",
        "outline-none focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
      )}
    >
      {label}
    </button>
  );
}

// Horizontal scrollers inside rendered markdown (a long code line, a wide
// table) are unreachable by keyboard unless the scroller itself can take focus
// (WCAG 2.1.1; axe scrollable-region-focusable). Streamdown owns that markup
// and gives no hook for it, so the scrollers are marked after render: any
// code-block or table box whose content overflows gets tabIndex=0 and a name,
// plus role=region unless it is the <table> itself, which keeps its table
// role. The marking tracks overflow, so a block that fits stays out of the
// Tab order.
const SCROLL_CANDIDATES =
  'pre, table, [data-streamdown="code-block-body"], div:has(> table)';
const SCROLL_MARK = "data-scroll-region";
const SYNC_DEBOUNCE_MS = 150;

function syncScrollRegions(root: HTMLElement): void {
  for (const el of root.querySelectorAll<HTMLElement>(SCROLL_CANDIDATES)) {
    const ox = getComputedStyle(el).overflowX;
    const overflows =
      (ox === "auto" || ox === "scroll") && el.scrollWidth > el.clientWidth + 1;
    if (overflows === el.hasAttribute(SCROLL_MARK)) continue;
    if (!overflows) {
      // Dropping tabindex from the focused region would throw focus to
      // <body>; leave it marked until focus moves on.
      const active = document.activeElement;
      if (active && (el === active || el.contains(active))) continue;
      el.removeAttribute(SCROLL_MARK);
      el.removeAttribute("tabindex");
      el.removeAttribute("aria-label");
      if (el.getAttribute("role") === "region") el.removeAttribute("role");
      continue;
    }
    const isTable = el.tagName === "TABLE" || !!el.querySelector(":scope > table");
    const lang = el.closest("[data-language]")?.getAttribute("data-language");
    el.setAttribute(SCROLL_MARK, "");
    el.setAttribute("tabindex", "0");
    if (el.tagName !== "TABLE") el.setAttribute("role", "region");
    el.setAttribute(
      "aria-label",
      isTable ? "Scrollable table" : lang ? `Scrollable ${lang} code` : "Scrollable code",
    );
  }
}

function useScrollRegions(ref: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    // Trailing debounce: a sync reads layout (getComputedStyle, scrollWidth)
    // for every candidate, and streaming mutates the DOM every frame, so a
    // per-frame sync would force a layout per frame (UI-PERF-4). Syncing
    // once the DOM has been quiet for SYNC_DEBOUNCE_MS costs one layout per
    // burst; a finished message settles one debounce after its last delta.
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      if (timer !== undefined) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = undefined;
        syncScrollRegions(root);
      }, SYNC_DEBOUNCE_MS);
    };
    syncScrollRegions(root);
    // Streaming appends content and highlighting swaps the code body in
    // later, so re-check on DOM changes as well as on width changes.
    const mo = new MutationObserver(schedule);
    mo.observe(root, { childList: true, subtree: true, characterData: true });
    const ro = new ResizeObserver(schedule);
    // The ref host is `display: contents` and has no box to resize; watch
    // the Streamdown root it wraps instead.
    ro.observe(root.firstElementChild ?? root);
    // A region kept marked only because it held focus is released here.
    root.addEventListener("focusout", schedule);
    return () => {
      root.removeEventListener("focusout", schedule);
      mo.disconnect();
      ro.disconnect();
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [ref]);
}

export function MarkdownRenderer({
  children,
  className,
  sources,
  onCitationClick,
}: {
  children: string;
  className?: string;
  // Active source list for the message (optional). When present alongside
  // `onCitationClick`, bare `[n]` tokens whose `n` matches a source id become
  // interactive citation chips. Absent/empty leaves the renderer byte-for-byte
  // as before (default off) so every existing call site is unchanged.
  sources?: SourceItem[];
  onCitationClick?: (id: number) => void;
}) {
  const { resolvedTheme } = useTheme();
  const rootRef = useRef<HTMLDivElement>(null);
  useScrollRegions(rootRef);

  // Final render-time net: drop any leaked tool-call markup (mirrors the BE
  // sanitizer) so persisted/edge-case leaks never display raw. Display-only —
  // streaming and persistence are untouched.
  const safeChildren = stripToolMarkup(children);

  // Memoize so the config object identity only changes with the theme, avoiding
  // needless mermaid re-inits / re-renders on unrelated re-renders.
  const mermaid = useMemo(
    () => ({
      config: {
        theme: resolvedTheme === "dark" ? ("dark" as const) : ("default" as const),
      } satisfies MermaidConfig,
      errorComponent: MermaidError,
    }),
    [resolvedTheme],
  );

  const plugins = useMemo<PluginConfig>(() => ({ mermaid: mermaidPlugin }), []);

  // Citation wiring is opt-in: only active when the caller supplies both a
  // non-empty source list and a click handler. Keyed on the sorted id list so
  // the memo identity is stable across re-renders with the same sources.
  const idsKey = (sources ?? [])
    .map((s) => s.id)
    .sort((a, b) => a - b)
    .join(",");
  const citationsEnabled = idsKey.length > 0 && !!onCitationClick;

  const rehypePlugins = useMemo<StreamdownProps["rehypePlugins"]>(() => {
    if (!citationsEnabled) return undefined;
    const ids = idsKey.split(",").map(Number);
    // Append AFTER the default raw → sanitize → harden chain so the custom
    // citation element survives sanitization (the model's own HTML is still
    // scrubbed by the defaults that run first).
    return [
      ...Object.values(defaultRehypePlugins),
      createCitationRehypePlugin(ids),
    ];
  }, [citationsEnabled, idsKey]);

  const components = useMemo<Components | undefined>(() => {
    // An image in streamed markdown comes straight from the model, so neither
    // `loading` nor a usable `alt` is guaranteed. Supply both here rather than
    // trusting the content: lazy + async decode keep an off-screen image off
    // the first paint, and a generic label is what PRD 01 §5.4 asks for when
    // the model gives none. The width cap lives in `.chat-md :where(img)`.
    const Img = (props: { src?: string; alt?: string; title?: string }) => (
      // A remote, model-supplied URL has no known dimensions and no configured
      // loader, which is what `next/image` requires — a plain `img` is correct
      // here, and `.chat-md :where(img)` caps its width.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={props.src ?? ""}
        alt={props.alt?.trim() ? props.alt : "Image in assistant response"}
        {...(props.title ? { title: props.title } : {})}
        loading="lazy"
        decoding="async"
      />
    );
    // The `Components` map's index signature widens child props to `unknown`;
    // each override reads only the props it names, so cast through `unknown`
    // rather than contorting the signature.
    if (!citationsEnabled || !onCitationClick) {
      return { img: Img } as unknown as Components;
    }
    const Cite = (props: {
      children?: ReactNode;
      "data-citation-adjacent"?: string;
    }) => (
      <CitationChip
        onActivate={onCitationClick}
        adjacent={props["data-citation-adjacent"] === "true"}
      >
        {props.children}
      </CitationChip>
    );
    return { img: Img, [CITATION_TAG]: Cite } as unknown as Components;
  }, [citationsEnabled, onCitationClick]);

  return (
    // `contents`: a ref host for useScrollRegions that adds no box, so the
    // Streamdown root keeps its place in the parent's layout.
    <div ref={rootRef} className="contents">
      <Streamdown
        parseIncompleteMarkdown
        controls={{ code: { download: false } }}
        mermaid={mermaid}
        plugins={plugins}
        className={cn("chat-md", className)}
        {...(rehypePlugins ? { rehypePlugins } : {})}
        {...(components ? { components } : {})}
      >
        {safeChildren}
      </Streamdown>
    </div>
  );
}
