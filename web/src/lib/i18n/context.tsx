"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  type ReactNode,
} from "react";

import {
  catalogs,
  en,
  RTL_LOCALES,
  type MessageKey,
} from "@/lib/i18n/messages";

export type Dir = "ltr" | "rtl";

export interface TranslateVars {
  [key: string]: string | number;
}

// `t(key, vars?)` resolves a catalog string for the active locale, falls back to
// the English baseline, then to the raw key, and interpolates `{name}` tokens.
export type TranslateFn = (key: MessageKey, vars?: TranslateVars) => string;

interface I18nContextValue {
  locale: string;
  dir: Dir;
  t: TranslateFn;
}

function interpolate(template: string, vars?: TranslateVars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = vars[name];
    return value === undefined ? match : String(value);
  });
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({
  locale = "en",
  dir,
  children,
}: {
  locale?: string;
  // Optional explicit direction override (the `?rtl=1` test hook). When absent,
  // direction is derived from the locale.
  dir?: Dir;
  children: ReactNode;
}) {
  const resolvedDir: Dir = dir ?? (RTL_LOCALES.has(locale) ? "rtl" : "ltr");

  const t = useCallback<TranslateFn>(
    (key, vars) => {
      const catalog = catalogs[locale];
      const template = catalog?.[key] ?? en[key] ?? key;
      return interpolate(template, vars);
    },
    [locale],
  );

  const value = useMemo<I18nContextValue>(
    () => ({ locale, dir: resolvedDir, t }),
    [locale, resolvedDir, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (ctx) return ctx;
  // Provider-less fallback (e.g. an isolated unit render): English, LTR. Keeps
  // `useT()` safe to call from any client component without a hard crash.
  return {
    locale: "en",
    dir: "ltr",
    t: (key, vars) => interpolate(en[key] ?? key, vars),
  };
}

export function useT(): TranslateFn {
  return useI18n().t;
}

// Client-side direction hook for the `?rtl=1` test affordance. Reads the URL
// query first (`?rtl=1` → RTL, `?rtl=0` → LTR), persisting the choice to the
// `rtl` cookie so the server can render the correct `dir` on the next load;
// absent a query param it honours the existing cookie. Only mutates the DOM
// (`document.documentElement.dir`) — no React state — so it stays clear of the
// repo's set-state-in-effect lint while still flipping direction live without a
// reload. Mount once near the root.
export function DirController() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const query = params.get("rtl");
    let dir: Dir | null = null;
    if (query === "1") dir = "rtl";
    else if (query === "0") dir = "ltr";

    if (dir) {
      document.cookie = `rtl=${dir === "rtl" ? "1" : "0"}; path=/; max-age=31536000; samesite=lax`;
    } else {
      const cookieMatch = document.cookie.match(/(?:^|;\s*)rtl=([01])/);
      if (cookieMatch) dir = cookieMatch[1] === "1" ? "rtl" : "ltr";
    }

    if (dir) document.documentElement.dir = dir;
  }, []);

  return null;
}

export function useDir(): Dir {
  return useI18n().dir;
}

export function useLocale(): string {
  return useI18n().locale;
}
