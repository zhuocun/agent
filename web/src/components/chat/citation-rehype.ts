// Inline `[n]` citation markers (PRD 07 §4.3 / D24).
//
// A rehype (HAST) transform that turns bare `[n]` tokens in the rendered answer
// into a custom `<citationmarker>` element keyed on the source id, which the
// MarkdownRenderer maps to an interactive citation chip. This is render-only
// over the shipped source-card list:
//
//   - ONLY `[n]` where `n` is a known source id is transformed; every other
//     `[...]` (footnotes, array indices, unknown ids) stays literal text.
//   - Text inside `code` / `pre` is never touched, so code samples that contain
//     `[1]` are left verbatim.
//   - The plugin runs AFTER Streamdown's default sanitize + harden plugins (see
//     markdown-renderer.tsx), so the custom element survives sanitization while
//     the model's own raw HTML is still scrubbed first.
//
// Streaming safety: a half-streamed `[` (or `[1` with no closing bracket) does
// not match the marker regex, so it renders as plain text until the token
// completes — `parseIncompleteMarkdown` and the existing renderer behavior are
// untouched.

// Custom (lowercase) tag name the chip component is mapped onto.
export const CITATION_TAG = "citationmarker";

// Minimal HAST node shape — we only touch the fields we need rather than
// pulling the full `@types/hast` surface.
interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

// `[n]` where n is 1–4 digits. Bounded so a pathological `[999999999…]` can't
// blow up Number parsing; real source ids are tiny ordinals.
const MARKER = /\[(\d{1,4})\]/g;

function splitCitations(text: string, ids: ReadonlySet<number>): HastNode[] {
  const out: HastNode[] = [];
  let lastIndex = 0;
  MARKER.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = MARKER.exec(text)) !== null) {
    const n = Number(match[1]);
    if (!ids.has(n)) continue; // unknown id -> leave literal
    if (match.index > lastIndex) {
      out.push({ type: "text", value: text.slice(lastIndex, match.index) });
    }
    out.push({
      type: "element",
      tagName: CITATION_TAG,
      properties: { dataCitationId: n },
      children: [{ type: "text", value: match[0] }],
    });
    lastIndex = match.index + match[0].length;
  }
  if (out.length === 0) return [{ type: "text", value: text }];
  if (lastIndex < text.length) {
    out.push({ type: "text", value: text.slice(lastIndex) });
  }
  return out;
}

// Build a rehype plugin bound to the active source ids. Returns a unified
// plugin: `() => (tree) => void`.
export function createCitationRehypePlugin(
  sourceIds: readonly number[],
): () => (tree: HastNode) => void {
  const ids = new Set(sourceIds);
  return function rehypeInlineCitations() {
    return (tree: HastNode): void => {
      walk(tree, false);
    };

    function walk(node: HastNode, insideCode: boolean): void {
      const children = node.children;
      if (!children || children.length === 0) return;
      const isCodeContainer =
        node.type === "element" &&
        (node.tagName === "code" || node.tagName === "pre");
      const skip = insideCode || isCodeContainer;

      const next: HastNode[] = [];
      for (const child of children) {
        if (
          !skip &&
          child.type === "text" &&
          typeof child.value === "string" &&
          child.value.includes("[")
        ) {
          next.push(...splitCitations(child.value, ids));
        } else {
          if (child.type === "element") walk(child, skip);
          next.push(child);
        }
      }
      node.children = next;
    }
  };
}
