import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    // Stable app identity so reinstalls/updates map to the same installed app.
    id: "/",
    name: "Olune — multi-model AI chat",
    short_name: "Olune",
    description: "Chat that respects your time.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    // Explicit fallback chain (no UA-specific upgrade today; pins standalone).
    display_override: ["standalone"],
    orientation: "any",
    background_color: "#f9fafc",
    // theme_color can only express one value; iOS dark is handled by the paired
    // `<meta name="theme-color" media=...>` tags emitted from the viewport
    // export in layout.tsx. Keep this the light surface.
    theme_color: "#f9fafc",
    categories: ["productivity", "utilities"],
    // Long-press / jump-list shortcuts (Android/Chromium installs). Each target
    // is an in-scope deep link the client resolves on mount (see chat-thread's
    // `?action=` handler) — no new icon assets required.
    shortcuts: [
      {
        name: "New chat",
        short_name: "New chat",
        description: "Start a fresh conversation",
        url: "/?action=new-chat",
      },
      {
        name: "Search chats",
        short_name: "Search",
        description: "Search your conversations",
        url: "/?action=search",
      },
      {
        name: "Settings",
        short_name: "Settings",
        description: "Open settings",
        url: "/?action=settings",
      },
    ],
    icons: [
      {
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-512-maskable.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
