import type { CSSProperties } from "react";

/**
 * Top chrome padding for surfaces that scroll beneath the floating header
 * (and optional status banners). Keeps the magic rem offsets in one place so
 * header/banner height tweaks don't require hunting literals across files.
 *
 * Split into a static class + dynamic CSS variables because Tailwind v4's
 * scanner only extracts literal class strings — runtime-built
 * `pt-[...${x}rem]` names are invisible to it and silently produce no CSS.
 * `CHAT_CHROME_PAD_CLASS` is the literal (so the pt-/md:pt- utilities get
 * generated) and `topChromePaddingStyle` supplies the per-surface offsets via
 * the `--chat-chrome-pad-top(-md)` variables it references.
 */
export type ChatChromeSurface = "welcome" | "thread" | "compare";

const BASE_TOP_REM: Record<ChatChromeSurface, { mobile: number; desktop: number }> =
  {
    welcome: { mobile: 5.5, desktop: 7 },
    thread: { mobile: 4, desktop: 5.5 },
    compare: { mobile: 5.5, desktop: 7 },
  };

/** Each status pill (temporary or degraded) adds ~3rem to the top chrome. */
const BANNER_REM = 3;

function topChromeBannerRem(options: {
  isTemporary: boolean;
  statusBannerActive: boolean;
}): number {
  const { isTemporary, statusBannerActive } = options;
  return (
    (isTemporary && !statusBannerActive ? BANNER_REM : 0) +
    (statusBannerActive ? BANNER_REM : 0)
  );
}

/** Static class applied alongside `topChromePaddingStyle` on the same element. */
export const CHAT_CHROME_PAD_CLASS =
  "pt-[calc(env(safe-area-inset-top)+var(--chat-chrome-pad-top))] md:pt-[calc(env(safe-area-inset-top)+var(--chat-chrome-pad-top-md))]";

export function topChromePaddingStyle(
  surface: ChatChromeSurface,
  options: {
    isTemporary: boolean;
    statusBannerActive: boolean;
  },
): CSSProperties {
  const base = BASE_TOP_REM[surface];
  const bannerRem = topChromeBannerRem(options);
  return {
    "--chat-chrome-pad-top": `${base.mobile + bannerRem}rem`,
    "--chat-chrome-pad-top-md": `${base.desktop + bannerRem}rem`,
  } as CSSProperties;
}
