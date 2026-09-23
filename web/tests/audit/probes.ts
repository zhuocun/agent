// In-page probes for the UI audit harness (see ui.audit.ts).
//
// Every function exported here is passed to `page.evaluate`, so it is
// serialized with `Function.prototype.toString` and must be fully
// self-contained: no imports, no closures over module scope, helpers declared
// inside the function body.
//
// Probe → UI_STANDARDS.md clause map:
//   overflow     → UI-LAYOUT-1 (page scrollWidth) + per-element right-edge offenders
//   targets      → UI-TOUCH-1 (44 px on touch) / UI-TOUCH-2 (24 px on pointer)
//   smallText    → UI-TYPE-4 (mobile floors) — the brief's floor is a flat 12 px
//   spacing      → craft: margin/padding/gap values off the Tailwind 4 px scale
//   animations   → UI-MOTION-1 / UI-MOTION-2 (running animations snapshot)
//   focus        → UI-FOCUS-2 (visible indicator) / UI-FOCUS-3 (not obscured)
//   cls          → UI-PERF-3 lab approximation (layout-shift entries)

export interface ProbeOptions {
  touch: boolean;
  targetFloor: number;
}

/** Layout / target / text / spacing / animation probe. Runs in the page. */
export function pageProbe(opts: ProbeOptions) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  function describe(el: Element): string {
    const tag = el.tagName.toLowerCase();
    const id = el.id && !/^(base-ui|radix|:r)/.test(el.id) ? `#${el.id}` : "";
    const testid = el.getAttribute("data-testid");
    const aria = el.getAttribute("aria-label");
    const role = el.getAttribute("role");
    const cls =
      typeof (el as HTMLElement).className === "string"
        ? (el as HTMLElement).className
            .split(/\s+/)
            .filter(Boolean)
            .slice(0, 4)
            .join(".")
        : "";
    let s = tag + id;
    if (testid) s += `[data-testid="${testid}"]`;
    if (role) s += `[role="${role}"]`;
    if (aria) s += `[aria-label="${aria.slice(0, 40)}"]`;
    if (!testid && !aria && cls) s += `.${cls}`;
    return s;
  }

  function text(el: Element): string {
    return ((el as HTMLElement).innerText || el.textContent || "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 50);
  }

  function isVisible(el: Element): boolean {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none") return false;
    if (parseFloat(cs.opacity) === 0) return false;
    // aria-hidden / inert subtrees are not user-reachable (closed drawers,
    // the pre-bootstrap placeholder).
    if (el.closest("[aria-hidden='true'], [inert]")) return false;
    // Fully outside the viewport vertically = not on screen for this shot.
    if (r.bottom <= 0 || r.top >= vh) return false;
    return true;
  }

  function clippedHorizontally(el: Element): boolean {
    // True if some ancestor clips/scrolls horizontally, which makes the
    // element's overhang an in-container scroll rather than page overflow.
    let p = el.parentElement;
    while (p && p !== document.body && p !== document.documentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === "auto" || ox === "scroll" || ox === "hidden" || ox === "clip") {
        return true;
      }
      p = p.parentElement;
    }
    return false;
  }

  // ── Overflow (UI-LAYOUT-1) ────────────────────────────────────────────
  const se = document.scrollingElement as HTMLElement;
  const overflow = {
    scrollWidth: se.scrollWidth,
    clientWidth: se.clientWidth,
    pageOverflows: se.scrollWidth > se.clientWidth + 1,
    offenders: [] as Array<{ sel: string; left: number; right: number; text: string; clipped: boolean }>,
  };
  const all = Array.from(document.body.querySelectorAll("*"));
  for (const el of all) {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    if (r.right <= vw + 1 && r.left >= -1) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none") continue;
    if (el.closest("[aria-hidden='true'], [inert]")) continue;
    // Off-canvas fixed chrome (closed drawers, toasts parked off-screen)
    // entirely outside the viewport is not a reflow defect.
    if (r.left >= vw || r.right <= 0) continue;
    const clipped = clippedHorizontally(el);
    if (clipped) continue;
    overflow.offenders.push({
      sel: describe(el),
      left: Math.round(r.left),
      right: Math.round(r.right),
      text: text(el),
      clipped,
    });
  }
  // Keep only the outermost offenders (children of an offender add noise).
  overflow.offenders = overflow.offenders.slice(0, 25);

  // ── Targets (UI-TOUCH-1 / UI-TOUCH-2) ──────────────────────────────────
  const targetSel =
    'button, a[href], [role="button"], [role="tab"], [role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"], [role="option"], [role="switch"], [role="checkbox"], [role="radio"], input:not([type="hidden"]), select, textarea, summary';
  const targets = Array.from(document.querySelectorAll(targetSel)).filter(
    (el) =>
      isVisible(el) &&
      !(el as HTMLButtonElement).disabled &&
      !el.closest("[data-nextjs-toast], nextjs-portal"),
  );
  const rects = targets.map((el) => el.getBoundingClientRect());

  function hitSlop(el: Element, r: DOMRect) {
    // Expand by an absolutely positioned ::before / ::after with negative
    // insets (the repo's hit-slop idiom), measured, not assumed.
    let { left, top, right, bottom } = r;
    for (const pseudo of ["::before", "::after"]) {
      const ps = getComputedStyle(el, pseudo);
      if (!ps.content || ps.content === "none" || ps.position !== "absolute") continue;
      const px = (v: string) => (v.endsWith("px") ? parseFloat(v) : 0);
      left = Math.min(left, r.left + px(ps.left));
      top = Math.min(top, r.top + px(ps.top));
      right = Math.max(right, r.right - px(ps.right));
      bottom = Math.max(bottom, r.bottom - px(ps.bottom));
    }
    return { w: right - left, h: bottom - top };
  }

  const smallTargets: Array<{
    sel: string;
    text: string;
    w: number;
    h: number;
    inline: boolean;
    spacingOk: boolean;
  }> = [];
  targets.forEach((el, i) => {
    const r = rects[i]!;
    const eff = hitSlop(el, r);
    if (eff.w >= opts.targetFloor && eff.h >= opts.targetFloor) return;
    // WCAG 2.5.8 inline exception: a link inside a sentence.
    const inline =
      el.tagName === "A" &&
      !!el.parentElement &&
      /^(P|LI|TD|TH|SPAN|BLOCKQUOTE|DD)$/.test(el.parentElement.tagName) &&
      (el.parentElement.textContent || "").trim().length >
        (el.textContent || "").trim().length + 10;
    // WCAG 2.5.8 spacing exception (pointer only): a floor-diameter circle
    // centred on the target intersects no other target.
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const rad = opts.targetFloor / 2;
    let spacingOk = true;
    rects.forEach((o, j) => {
      if (j === i || !spacingOk) return;
      if (targets[j]!.contains(el) || el.contains(targets[j]!)) return;
      const dx = Math.max(o.left - cx, 0, cx - o.right);
      const dy = Math.max(o.top - cy, 0, cy - o.bottom);
      if (Math.hypot(dx, dy) < rad) spacingOk = false;
    });
    smallTargets.push({
      sel: describe(el),
      text: text(el) || el.getAttribute("aria-label") || "",
      w: Math.round(eff.w * 10) / 10,
      h: Math.round(eff.h * 10) / 10,
      inline,
      spacingOk: opts.touch ? false : spacingOk,
    });
  });

  // ── Text-size floor (flat 12 px) ───────────────────────────────────────
  const smallText = new Map<string, { sel: string; fontSize: number; sample: string; count: number }>();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node: Node | null;
  const fontSizes = new Map<number, number>();
  while ((node = walker.nextNode())) {
    const t = (node.nodeValue || "").trim();
    if (!t) continue;
    const el = node.parentElement;
    if (!el || !isVisible(el)) continue;
    if (el.closest("script, style, noscript")) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    fontSizes.set(fs, (fontSizes.get(fs) || 0) + 1);
    if (fs >= 12) continue;
    const key = `${describe(el)}|${fs}`;
    const prev = smallText.get(key);
    if (prev) prev.count += 1;
    else smallText.set(key, { sel: describe(el), fontSize: fs, sample: t.slice(0, 40), count: 1 });
  }

  // ── Off-scale spacing (craft) ──────────────────────────────────────────
  const props = [
    "marginTop", "marginRight", "marginBottom", "marginLeft",
    "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "rowGap", "columnGap",
  ] as const;
  const offScale = new Map<string, { value: number; prop: string; count: number; examples: string[]; inProse: number }>();
  function onScale(v: number): boolean {
    if (v === 0 || v === 1) return true; // hairline offsets
    const a = Math.abs(v);
    if (a <= 16) return Math.abs(a / 2 - Math.round(a / 2)) < 0.01; // 0.5-step region: 2,4,6..16
    return Math.abs(a / 4 - Math.round(a / 4)) < 0.01;
  }
  for (const el of all) {
    if (!isVisible(el)) continue;
    const cs = getComputedStyle(el);
    for (const p of props) {
      const raw = cs[p];
      if (!raw || raw === "normal" || !raw.endsWith("px")) continue;
      const v = parseFloat(raw);
      if (Number.isNaN(v) || onScale(v)) continue;
      const vr = Math.round(v * 100) / 100;
      const key = `${vr}|${p}`;
      const inProse = el.closest(".chat-md") ? 1 : 0;
      const e = offScale.get(key);
      if (e) {
        e.count += 1;
        e.inProse += inProse;
        if (e.examples.length < 3) e.examples.push(describe(el));
      } else {
        offScale.set(key, { value: vr, prop: p, count: 1, examples: [describe(el)], inProse });
      }
    }
  }

  // ── Animations (UI-MOTION-1 / -2) ──────────────────────────────────────
  // No `message-list` testid ships; `.chat-scroll` is the thread scroller.
  const list = document.querySelector(".chat-scroll");
  const animations = document
    .getAnimations()
    .filter((a) => a.playState === "running")
    .map((a) => {
      const target = (a.effect as KeyframeEffect | null)?.target as Element | null;
      const timing = a.effect?.getComputedTiming();
      return {
        name: (a as CSSAnimation).animationName || (a as CSSTransition).transitionProperty || a.constructor.name,
        target: target ? describe(target) : null,
        infinite: timing?.iterations === Infinity,
        insideMessageList: !!(target && list && list.contains(target)),
      };
    });

  // ── Misc facts reviewers want next to the shot ─────────────────────────
  const facts = {
    hoverNone: matchMedia("(hover: none)").matches,
    pointerCoarse: matchMedia("(pointer: coarse)").matches,
    theme: document.documentElement.className,
    dir: document.documentElement.dir || "ltr",
    title: document.title,
    bodyTextSample: (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 160),
    busyIndicators: document.querySelectorAll('[aria-busy="true"]').length,
  };

  return {
    viewport: { w: vw, h: vh },
    facts,
    overflow,
    targets: { floor: opts.targetFloor, total: targets.length, small: smallTargets },
    smallText: Array.from(smallText.values()).sort((a, b) => a.fontSize - b.fontSize),
    fontSizes: Array.from(fontSizes.entries()).sort((a, b) => a[0] - b[0]),
    spacing: Array.from(offScale.values()).sort((a, b) => b.count - a.count).slice(0, 15),
    animations,
  };
}

/** Installed with addInitScript: accumulates layout-shift entries. */
export function installClsObserver() {
  const w = window as unknown as {
    __auditCls: { value: number; entries: Array<{ v: number; t: number; recent: boolean; src: string[] }> };
  };
  w.__auditCls = { value: 0, entries: [] };
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries() as unknown as Array<{
        value: number;
        startTime: number;
        hadRecentInput: boolean;
        sources?: Array<{ node?: Node }>;
      }>) {
        if (!e.hadRecentInput) w.__auditCls.value += e.value;
        w.__auditCls.entries.push({
          v: Math.round(e.value * 10000) / 10000,
          t: Math.round(e.startTime),
          recent: e.hadRecentInput,
          src: (e.sources || [])
            .map((s) => {
              const n = s.node as Element | undefined;
              if (!n || !n.tagName) return "#text";
              const tid = n.getAttribute && n.getAttribute("data-testid");
              return n.tagName.toLowerCase() + (tid ? `[data-testid="${tid}"]` : "");
            })
            .slice(0, 3),
        });
      }
    }).observe({ type: "layout-shift", buffered: true });
  } catch {
    /* layout-shift unsupported */
  }
}

/** Snapshot of the currently focused element (focus-walk step). */
export function focusSnapshot() {
  const w = window as unknown as { __auditFocused: Element[] };
  w.__auditFocused = w.__auditFocused || [];
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  w.__auditFocused.push(el);
  function styleOf(e: Element) {
    const cs = getComputedStyle(e);
    return {
      outline: `${cs.outlineStyle} ${cs.outlineWidth} ${cs.outlineColor}`,
      boxShadow: cs.boxShadow,
      borderColor: cs.borderColor,
      background: cs.backgroundColor,
      textDecoration: cs.textDecorationLine,
    };
  }
  const chain: Array<ReturnType<typeof styleOf>> = [];
  let p: Element | null = el;
  for (let i = 0; i < 4 && p; i++) {
    chain.push(styleOf(p));
    p = p.parentElement;
  }
  const r = el.getBoundingClientRect();
  const header = document.querySelector("header");
  const hr = header?.getBoundingClientRect();
  const tag = el.tagName.toLowerCase();
  return {
    index: w.__auditFocused.length - 1,
    desc:
      tag +
      (el.getAttribute("data-testid") ? `[data-testid="${el.getAttribute("data-testid")}"]` : "") +
      (el.getAttribute("role") ? `[role="${el.getAttribute("role")}"]` : "") +
      (el.getAttribute("aria-label") ? `[aria-label="${el.getAttribute("aria-label")}"]` : ""),
    text: ((el as HTMLElement).innerText || "").replace(/\s+/g, " ").trim().slice(0, 40),
    focusVisible: el.matches(":focus-visible"),
    rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
    inViewport: r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth,
    underHeader: !!(hr && r.top < hr.bottom && r.bottom <= hr.bottom && r.top >= hr.top),
    focused: chain,
  };
}

/** After blurring, read the resting styles of every element the walk hit. */
export function focusBaselines() {
  const w = window as unknown as { __auditFocused: Element[] };
  function styleOf(e: Element) {
    const cs = getComputedStyle(e);
    return {
      outline: `${cs.outlineStyle} ${cs.outlineWidth} ${cs.outlineColor}`,
      boxShadow: cs.boxShadow,
      borderColor: cs.borderColor,
      background: cs.backgroundColor,
      textDecoration: cs.textDecorationLine,
    };
  }
  return (w.__auditFocused || []).map((el) => {
    const chain: Array<ReturnType<typeof styleOf>> = [];
    let p: Element | null = el;
    for (let i = 0; i < 4 && p; i++) {
      chain.push(styleOf(p));
      p = p.parentElement;
    }
    return chain;
  });
}
