"use client";

/**
 * Lightweight haptic feedback shim. iOS Safari and most desktop browsers don't
 * implement `navigator.vibrate`, so on those platforms this is a no-op — call
 * it freely from any gesture commit / submit handler without environment
 * guards. Android Chrome (and a few others) honor the vibrate intent for
 * subtle touch confirmation.
 *
 * Intent map (durations are short on purpose; longer buzzes feel cheap):
 *   - selection: 10ms — confirm a discrete commit (submit a message, toggle).
 *   - impact:    20ms — punctuate a destructive gesture (swipe-to-delete).
 *   - light:      5ms — soft acknowledgement (dismiss a sheet, settle).
 */
export type HapticType = "selection" | "impact" | "light";

const DURATIONS: Record<HapticType, number> = {
  selection: 10,
  impact: 20,
  light: 5,
};

export function haptic(type: HapticType): void {
  if (typeof navigator === "undefined") return;
  if (typeof navigator.vibrate !== "function") return;
  try {
    navigator.vibrate(DURATIONS[type]);
  } catch {
    // Some platforms reject vibrate from non-user-gesture contexts; ignore.
  }
}
