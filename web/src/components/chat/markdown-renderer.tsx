"use client";

import { useMemo, type ReactNode } from "react";
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
}: {
  children?: ReactNode;
  onActivate: (id: number) => void;
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
        "mx-px inline-flex items-baseline align-baseline rounded px-1 text-[0.85em] font-medium leading-none",
        "text-primary bg-primary/[0.08] hover:bg-primary/15",
        "cursor-pointer transition-colors",
        "outline-none focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
      )}
    >
      {label}
    </button>
  );
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
    if (!citationsEnabled || !onCitationClick) return undefined;
    const Cite = (props: { children?: ReactNode }) => (
      <CitationChip onActivate={onCitationClick}>{props.children}</CitationChip>
    );
    // The `Components` map's index signature widens child props to `unknown`;
    // our chip only reads `children`, so cast through `unknown` rather than
    // contorting the signature.
    return { [CITATION_TAG]: Cite } as unknown as Components;
  }, [citationsEnabled, onCitationClick]);

  return (
    <Streamdown
      parseIncompleteMarkdown
      controls={{ code: { download: false } }}
      mermaid={mermaid}
      plugins={plugins}
      className={cn("chat-md", className)}
      {...(rehypePlugins ? { rehypePlugins } : {})}
      {...(components ? { components } : {})}
    >
      {children}
    </Streamdown>
  );
}
