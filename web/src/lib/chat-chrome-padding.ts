/**
 * Top chrome padding for surfaces that scroll beneath the floating header
 * (and optional status banners). Keeps the magic rem offsets in one place so
 * header/banner height tweaks don't require hunting literals across files.
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

export function topChromeBannerRem(options: {
  isTemporary: boolean;
  statusBannerActive: boolean;
}): number {
  const { isTemporary, statusBannerActive } = options;
  return (
    (isTemporary && !statusBannerActive ? BANNER_REM : 0) +
    (statusBannerActive ? BANNER_REM : 0)
  );
}

export function topChromePaddingClass(
  surface: ChatChromeSurface,
  options: {
    isTemporary: boolean;
    statusBannerActive: boolean;
  },
): string {
  const base = BASE_TOP_REM[surface];
  const bannerRem = topChromeBannerRem(options);
  const mobile = base.mobile + bannerRem;
  const desktop = base.desktop + bannerRem;
  return `pt-[calc(env(safe-area-inset-top)+${mobile}rem)] md:pt-[calc(env(safe-area-inset-top)+${desktop}rem)]`;
}
