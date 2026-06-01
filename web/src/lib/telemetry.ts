"use client";

import { postTelemetryEvent, type TelemetryEventType } from "@/lib/apiClient";
import type { UserPreferences } from "@/lib/types";

export type TelemetryProperties = Record<string, string | number | boolean | null>;

export function reportTelemetry(
  preferences: Pick<UserPreferences, "telemetryEnabled"> | null | undefined,
  eventType: TelemetryEventType,
  properties?: TelemetryProperties,
): void {
  if (preferences?.telemetryEnabled === false) return;
  void postTelemetryEvent(eventType, properties).catch(() => {
    // Best-effort product telemetry must never affect the UI path.
  });
}
