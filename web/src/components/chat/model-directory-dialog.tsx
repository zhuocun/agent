"use client";

import { useEffect, useState, type JSX } from "react";
import { Check, Database, Minus, ShieldCheck, ShieldOff } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { fetchModelDirectory } from "@/lib/apiClient";
import type {
  ModelDirectoryEntry,
  ModelDirectoryTier,
  ProviderDataPolicy,
} from "@/lib/types";
import { cn } from "@/lib/utils";

export interface ModelDirectoryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// Per-million-token list price, shown so a user can compare routes. The BE
// emits 0 for tiers whose model varies per request (the `auto` router); we
// render those as "varies" rather than a misleading $0.
function formatPrice(perM: number): string {
  if (!Number.isFinite(perM) || perM <= 0) return "varies";
  return `$${perM.toFixed(2)}/M`;
}

const STATUS_COPY: Record<
  ModelDirectoryEntry["status"],
  { label: string; variant: "secondary" | "outline" | "ghost" }
> = {
  available: { label: "Available", variant: "secondary" },
  pending: { label: "Coming soon", variant: "outline" },
  unavailable: { label: "Unavailable", variant: "ghost" },
};

function retentionPhrase(policy: ProviderDataPolicy): string {
  if (policy.retentionDays === null || policy.retentionDays === undefined) {
    return "Retention not disclosed";
  }
  if (policy.retentionDays === 0) return "No retention";
  return `Retained up to ${policy.retentionDays} days`;
}

function SectionHeading({ children }: { children: string }): JSX.Element {
  return (
    <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
      {children}
    </h3>
  );
}

// A single capability pill — a check or a dash so the row reads as a quick
// yes/no comparison rather than a wall of text.
function Capability({
  on,
  label,
}: {
  on: boolean;
  label: string;
}): JSX.Element {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs",
        on ? "text-foreground" : "text-muted-foreground/60",
      )}
    >
      {on ? (
        <Check aria-hidden className="size-3" />
      ) : (
        <Minus aria-hidden className="size-3" />
      )}
      {label}
    </span>
  );
}

function PolicyBlock({
  policy,
}: {
  policy: ProviderDataPolicy | null;
}): JSX.Element {
  if (policy === null) {
    // A route with no published policy renders honestly as "unavailable" — we
    // never fabricate a guess (PRD 07 §5).
    return (
      <p
        className="text-xs text-muted-foreground"
        data-testid="policy-unavailable"
      >
        Data policy unavailable for this route.
      </p>
    );
  }
  return (
    <div className="space-y-1.5" data-testid="data-policy">
      <p className="flex items-center gap-1.5 text-xs font-medium">
        {policy.trainsOnData ? (
          <ShieldOff aria-hidden className="size-3.5 text-warning" />
        ) : (
          <ShieldCheck aria-hidden className="size-3.5 text-muted-foreground" />
        )}
        {policy.policyLabel}
      </p>
      <ul className="grid grid-cols-1 gap-1 text-xs text-muted-foreground sm:grid-cols-2">
        <li className="flex items-center gap-1.5">
          <Database aria-hidden className="size-3 shrink-0" />
          Data residency: {policy.dataResidency}
        </li>
        <li>
          Training:{" "}
          {policy.trainsOnData
            ? `may train (default ${policy.trainingDefault.replace("_", " ")})`
            : "never trains on your data"}
        </li>
        <li>{retentionPhrase(policy)}</li>
        <li>
          {policy.zeroDataRetentionAvailable
            ? "Zero-data-retention available"
            : "No zero-data-retention option"}
        </li>
      </ul>
    </div>
  );
}

function TierRow({ tier }: { tier: ModelDirectoryTier }): JSX.Element {
  return (
    <li
      className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-xl px-1 py-1.5"
      data-testid="directory-tier"
    >
      <div className="flex min-w-0 items-center gap-2">
        <span className="text-sm font-medium capitalize">{tier.tierId}</span>
        {tier.modelLabel ? (
          <span className="truncate text-xs text-muted-foreground">
            {tier.modelLabel}
          </span>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Capability on={tier.supportsWebSearch} label="Web" />
        <Capability on={tier.supportsAttachments} label="Files" />
        <Capability on={tier.supportsVision} label="Vision" />
        <span className="font-mono text-xs tabular-nums text-muted-foreground">
          in {formatPrice(tier.listPriceInPerM)} · out{" "}
          {formatPrice(tier.listPriceOutPerM)}
        </span>
      </div>
    </li>
  );
}

function ProviderCard({
  entry,
}: {
  entry: ModelDirectoryEntry;
}): JSX.Element {
  const status = STATUS_COPY[entry.status];
  return (
    <section
      className="glass-clear space-y-3 rounded-2xl px-3.5 py-3"
      data-testid="directory-provider"
      data-provider={entry.providerId}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{entry.label}</h3>
        <Badge variant={status.variant}>{status.label}</Badge>
        {entry.defaultRouteEligible ? (
          <Badge variant="outline">Default-eligible</Badge>
        ) : null}
      </div>

      <PolicyBlock policy={entry.dataPolicy} />

      {entry.tiers.length > 0 ? (
        <ul className="space-y-0.5 border-t border-border/50 pt-2">
          {entry.tiers.map((tier) => (
            <TierRow key={tier.tierId} tier={tier} />
          ))}
        </ul>
      ) : (
        <p className="border-t border-border/50 pt-2 text-xs text-muted-foreground">
          No tiers available on this route yet.
        </p>
      )}
    </section>
  );
}

// Model & data-policy directory (PRD 05 §4.5 / PRD 07 §5). A read-only,
// registry-derived catalog of every provider route with its data policy and
// per-tier capabilities + list prices, so a user can compare routes before
// choosing one. Anonymous-allowed; the catalog is identical for every caller.
export function ModelDirectoryDialog({
  open,
  onOpenChange,
}: ModelDirectoryDialogProps): JSX.Element {
  const [entries, setEntries] = useState<ModelDirectoryEntry[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let cancelled = false;
    void (async () => {
      try {
        const directory = await fetchModelDirectory(controller.signal);
        if (cancelled) return;
        setEntries(directory);
        setLoaded(true);
      } catch {
        if (cancelled) return;
        setError("Couldn't load the model directory. Please try again.");
        setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [open]);

  const loading = open && !loaded && error === null;

  const handleOpenChange = (next: boolean): void => {
    if (!next) {
      setEntries([]);
      setLoaded(false);
      setError(null);
    }
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-h-[80dvh] sm:max-h-none"
        data-testid="model-directory-dialog"
      >
        <DialogHeader>
          <DialogTitle>Models &amp; data policies</DialogTitle>
          <DialogDescription>
            Compare each provider route&apos;s data handling, capabilities, and
            list prices. Facts come straight from the live model registry.
          </DialogDescription>
        </DialogHeader>

        <div className="-mr-2 max-h-[60dvh] space-y-3 overflow-y-auto pr-2 sm:max-h-[70dvh]">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : (
            <SectionListing entries={entries} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function SectionListing({
  entries,
}: {
  entries: ModelDirectoryEntry[];
}): JSX.Element {
  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No provider routes are configured.
      </p>
    );
  }
  return (
    <div className="space-y-3" data-testid="directory-list">
      <SectionHeading>Provider routes</SectionHeading>
      {entries.map((entry) => (
        <ProviderCard key={entry.providerId} entry={entry} />
      ))}
    </div>
  );
}
