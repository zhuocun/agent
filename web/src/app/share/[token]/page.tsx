import type { Metadata } from "next";

import { PublicConversationView } from "@/components/share/public-conversation-view";

// Public-by-link share route: `/share/{token}`. This is a server component
// shell that owns route params + metadata; the actual conversation fetch and
// rendering happen client-side in PublicConversationView via the same apiClient
// (FE `/api/*` rewrite) the rest of the app uses. We keep metadata STATIC here
// rather than fetching the conversation title server-side: the title isn't
// secret, but a server fetch would need to resolve the BE origin (the apiClient
// reads the browser-inlined NEXT_PUBLIC_API_BASE_URL), and the view already
// reflects the live title into `document.title` once loaded. `noindex` keeps
// shared links out of search results — they're capability links, not content
// meant to be crawled.

// `params` is async in this Next version (App Router) — await it.
export const metadata: Metadata = {
  title: "Shared conversation · Olune",
  description: "A read-only shared conversation on Olune.",
  robots: { index: false, follow: false },
};

export default async function SharePage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <PublicConversationView token={token} />;
}
