import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/toast";
import { InstallCoachmark } from "@/components/chat/install-coachmark";

const geistSans = Geist({
  variable: "--font-sans",
  subsets: ["latin"],
});

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
    statusBarStyle: "default",
  },
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon.ico", sizes: "any" },
    ],
    shortcut: ["/favicon.ico"],
    apple: [{ url: "/apple-touch-icon.svg", type: "image/svg+xml" }],
  },
};

// Route-segment viewport export (Next.js 16). `viewportFit: "cover"` lets
// content draw under notches/home indicators so `env(safe-area-inset-*)`
// resolves to real values; `interactiveWidget: "resizes-content"` makes the
// Android soft keyboard shrink the layout viewport (content resizes).
// `themeColor` is paired (light/dark) to the canon's `--background` token so
// the OS chrome (Android status bar, iOS standalone tint) matches the app
// surface in both schemes.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  interactiveWidget: "resizes-content",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f9fafc" },
    { media: "(prefers-color-scheme: dark)", color: "#101216" },
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
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
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
