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
    icons: [
      // Scalable source first, raster PNGs for installers that require them.
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        src: "/icon-maskable.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "maskable",
      },
      {
        src: "/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
    categories: ["productivity", "utilities"],
  };
}
