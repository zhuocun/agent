"use client";

import { useMemo } from "react";
import type { MermaidConfig } from "mermaid";
import {
  type DiagramPlugin,
  type MermaidErrorComponentProps,
  type PluginConfig,
  Streamdown,
} from "streamdown";
import { useTheme } from "next-themes";

import { cn } from "@/lib/utils";

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

export function MarkdownRenderer({
  children,
  className,
}: {
  children: string;
  className?: string;
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

  return (
    <Streamdown
      parseIncompleteMarkdown
      controls={{ code: { download: false } }}
      mermaid={mermaid}
      plugins={plugins}
      className={cn("chat-md", className)}
    >
      {children}
    </Streamdown>
  );
}
