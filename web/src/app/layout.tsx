import type { Metadata, Viewport } from "next";
import { Geist_Mono } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/toast";
import { InstallCoachmark } from "@/components/chat/install-coachmark";

// UI sans is the Apple system stack (defined as `--font-sans` in globals.css) —
// no web-font load, so the standalone PWA renders in SF Pro like a native app.
// Only the monospace code face is web-loaded (Geist Mono).
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Olune — multi-model AI chat",
  description:
    "A transparent, multi-model, privacy-first AI chat. See which model answered and what it cost.",
  manifest: "/manifest.webmanifest",
  applicationName: "Olune",
  appleWebApp: {
    capable: true,
    title: "Olune",
    // Edge-to-edge: content draws under the status bar. Safe because the app
    // header already pads `env(safe-area-inset-top)` (chat-thread.tsx chrome
    // strip) and a fixed status-bar blur strip is rendered below.
    // `default` (not the deprecated `black-translucent`) so the status-bar
    // glyphs follow the paired light/dark `theme-color` metas below — under
    // iOS 26 `black-translucent` can force white glyphs even in light mode.
    statusBarStyle: "default",
    startupImage: [
      {
        url: "/splash-1170x2532-light.png",
        media:
          "(prefers-color-scheme: light) and (device-width: 390px) and (device-height: 844px) and (-webkit-device-pixel-ratio: 3)",
      },
      {
        url: "/splash-1170x2532-dark.png",
        media:
          "(prefers-color-scheme: dark) and (device-width: 390px) and (device-height: 844px) and (-webkit-device-pixel-ratio: 3)",
      },
    ],
  },
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/icon-192.png", type: "image/png", sizes: "192x192" },
      { url: "/icon-512.png", type: "image/png", sizes: "512x512" },
    ],
    apple: [
      { url: "/apple-touch-icon.png", type: "image/png", sizes: "180x180" },
    ],
  },
};

// Route-segment viewport export (Next.js 16). `viewportFit: "cover"` lets
// content draw under notches/home indicators so `env(safe-area-inset-*)`
// resolves to real values; `interactiveWidget: "resizes-content"` makes the
// Android soft keyboard shrink the layout viewport (content resizes).
// `themeColor` tints the OS/browser chrome (Android status bar, iOS Safari
// web-tinting of the toolbar + status-bar area, iOS standalone tint) to the
// canon's `--background` token. The light value is emitted UNCONDITIONALLY
// (no `media`) as the baseline, with dark layered on as a `media` override —
// rather than two `media`-scoped entries. iOS Safari skips web-tinting when
// every theme-color is media-scoped (it wants a plain, unconditional one to
// honor); the baseline makes the tint reliably engage. Resolution still lands
// correctly: light/no-preference falls through to the baseline, and dark wins
// via its media query (a no-media meta always matches, so the later dark meta
// overrides it only under prefers-color-scheme: dark). Both values match
// `--background` exactly — light oklch(0.985 0.003 250) → #f9fafc, dark
// oklch(0.165 0.008 250) → #0c0f12.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  interactiveWidget: "resizes-content",
  themeColor: [
    { color: "#f9fafc" },
    { media: "(prefers-color-scheme: dark)", color: "#0c0f12" },
  ],
};

const SW_REGISTER_SNIPPET = `if ('serviceWorker' in navigator) {
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/sw.js').catch(function () {});
  });
}`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* Status-bar safety strip (iOS `black-translucent`). Content draws
            edge-to-edge under the status bar; this fixed, blurred strip keeps
            the clock/battery legible over scrolling content. The mask fades
            the strip's bottom edge so there's no hard seam against the chrome.
            Zero height when `env(safe-area-inset-top)` is 0 (non-notch / web). */}
        <div
          aria-hidden
          className="pointer-events-none fixed inset-x-0 top-0 z-[100]"
          style={{
            height: "env(safe-area-inset-top)",
            // Track the glass system's blur + saturation, but deliberately omit
            // the `brightness(--glass-brightness)` lift the `glass-*` utilities
            // carry. That lift (1.03) is sub-perceptual over colored content but
            // pushes the near-white app surface (#f9fafc) PAST the top of the
            // gamut — every channel clips to 255 — so over the page this strip
            // rendered a pure-white band that read brighter than the body. The
            // brightness lift only earns its keep over rich content (bubbles,
            // dialogs); over the flat top surface it just manufactures a seam.
            backdropFilter:
              "blur(var(--glass-blur)) saturate(var(--glass-saturate))",
            WebkitBackdropFilter:
              "blur(var(--glass-blur)) saturate(var(--glass-saturate))",
            maskImage: "linear-gradient(to bottom, black, transparent)",
            WebkitMaskImage: "linear-gradient(to bottom, black, transparent)",
          }}
        />
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <TooltipProvider delay={200}>
            {children}
            <InstallCoachmark />
            <Toaster />
          </TooltipProvider>
        </ThemeProvider>
        {process.env.NODE_ENV === "production" ? (
          <Script id="sw-register" strategy="afterInteractive">
            {SW_REGISTER_SNIPPET}
          </Script>
        ) : null}
      </body>
    </html>
  );
}
