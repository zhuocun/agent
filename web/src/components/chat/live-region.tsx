"use client";

// The single, separate polite status region (PRD 06 §3.5 / PRD 01 §5.7).
// The streamed answer body is NOT a live region; discrete generation-status
// transitions ("Generating", "Response ready", "Stopped") are announced here.
export function LiveRegion({ message }: { message: string }) {
  return (
    <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
      {message}
    </div>
  );
}
