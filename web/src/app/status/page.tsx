import type { Metadata } from "next";

import { PlatformStatusView } from "@/components/status/platform-status-view";

// Public platform-status route: `/status`. A server-component shell that owns
// metadata; the live `/api/status` fetch + rendering happen client-side in
// PlatformStatusView via the same apiClient (FE `/api/*` rewrite) the rest of
// the app uses, so we don't resolve the BE origin server-side. The page is
// public and unauthenticated — anyone can check platform health — and we keep
// it out of search indexes since it's an operational surface, not content.

export const metadata: Metadata = {
  title: "Platform status · Olune",
  description: "Live operational status for Olune.",
  robots: { index: false, follow: false },
};

export default function StatusPage() {
  return <PlatformStatusView />;
}
