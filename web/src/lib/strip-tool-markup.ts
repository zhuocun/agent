// Display-side guard against leaked tool-call markup in assistant/task text.
//
// Mirror of the backend sanitizer in `api/app/providers/_tool_markup.py`. The BE
// scrubs leaks out of the answer stream, but already-persisted transcripts (from
// before that fix) or edge cases can still carry raw tool-call special tokens.
// This is the final render-time net so users never see garbage like:
//
//     <｜｜DSML｜｜tool_calls>\n<｜｜DSML｜｜invoke name="web_search">...
//
// Purely display-side: it never touches streaming or persistence. Legitimate
// answers never contain these markers, so truncating from the first marker
// onward is safe.

// Fullwidth vertical bar U+FF5C and the DeepSeek "▁" U+2581 used in native
// special tokens. Spelled out as escapes so the exact code points are
// unambiguous and stay in sync with the backend constants.
const FW_BAR = "\uFF5C"; // ｜
const USCORE = "\u2581"; // ▁

// Exact tool-call START markers — mirror of the backend `_START_MARKERS`. Order
// does not matter; we scan for the earliest occurrence of any of them.
export const TOOL_MARKUP_START_MARKERS: readonly string[] = [
  `<${FW_BAR}${FW_BAR}DSML${FW_BAR}${FW_BAR}`, // <｜｜DSML｜｜
  `<${FW_BAR}tool${USCORE}calls${USCORE}begin${FW_BAR}>`, // <｜tool▁calls▁begin｜>
  `<${FW_BAR}tool${USCORE}call${USCORE}begin${FW_BAR}>`, // <｜tool▁call▁begin｜>
];

function earliestMarkerIndex(text: string): number | null {
  let best: number | null = null;
  for (const marker of TOOL_MARKUP_START_MARKERS) {
    const idx = text.indexOf(marker);
    if (idx !== -1 && (best === null || idx < best)) best = idx;
  }
  return best;
}

/** True when `text` contains any tool-call START marker (a leak). */
export function containsToolMarkup(text: string): boolean {
  return earliestMarkerIndex(text) !== null;
}

/**
 * Return `text` truncated at the first tool-call START marker.
 *
 * Everything from the first marker onward (the leaked tool-call block) is
 * dropped. Returns `text` unchanged when no marker is present.
 */
export function stripToolMarkup(text: string): string {
  const hit = earliestMarkerIndex(text);
  return hit === null ? text : text.slice(0, hit);
}
