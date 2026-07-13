import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Page not found · Olune",
  description: "The page you are looking for does not exist.",
  robots: { index: false, follow: false },
};

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center px-4 py-16 text-center">
        <Link
          href="/"
          className="mb-8 rounded-sm font-medium text-foreground outline-none focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
          aria-label="Olune home"
        >
          <span className="font-heading text-2xl tracking-tight text-foreground/90">
            Olune
          </span>
        </Link>
        <p className="text-sm font-medium tracking-wide text-muted-foreground">
          404
        </p>
        <h1 className="mt-2 font-heading text-3xl tracking-tight text-balance md:text-4xl">
          Page not found
        </h1>
        <p className="mt-3 max-w-sm text-sm leading-relaxed text-muted-foreground">
          This page doesn&apos;t exist or may have moved.
        </p>
        <Link
          href="/"
          className="mt-8 inline-flex h-11 items-center rounded-full bg-brand px-5 text-sm font-medium text-brand-foreground transition-colors hover:bg-brand/90 focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
        >
          Back to chat
        </Link>
      </main>
    </div>
  );
}
