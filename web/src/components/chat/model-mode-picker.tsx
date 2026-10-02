"use client";

import { useState, type JSX, type ReactNode } from "react";
import { Check, ChevronDown } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { haptic } from "@/lib/use-haptic";
import { cn } from "@/lib/utils";
import type { ModelTier, ModelTierId } from "@/lib/types";

export interface ModelModePickerProps {
  tiers: ModelTier[];
  selectedTierId: ModelTierId;
  onSelectTier: (id: ModelTierId) => void;
  disabled?: boolean;
}

// Shared trigger styling — identical between the desktop dropdown and the
// mobile bottom-sheet variants. A compact ghost pill in the composer toolbar
// that keeps the 44px touch floor. The label is the model only; tools,
// provider, reasoning effort, and data policy live on the Tools control.
const TRIGGER_CLASS =
  "inline-flex h-11 min-w-0 max-w-[min(12rem,max(6rem,calc(100vw-11rem)))] sm:max-w-[min(12rem,max(6rem,calc(100vw-16rem)))] items-center gap-1 rounded-full px-3 ui-list-row outline-none transition-colors bg-foreground/[0.04] shadow-[inset_0_0_0_1px_var(--glass-border)] hover:bg-foreground/[0.08] focus-visible:ring-2 focus-visible:ring-ring aria-expanded:bg-foreground/[0.08] md:max-w-80";

export function ModelModePicker({
  tiers,
  selectedTierId,
  onSelectTier,
  disabled,
}: ModelModePickerProps): JSX.Element {
  const tier = tiers.find((t) => t.id === selectedTierId) ?? tiers[0];
  const cheapestTierId = cheapestAvailableTierId(tiers);
  const [sheetOpen, setSheetOpen] = useState(false);
  const triggerLabel = `Model ${tier?.label}. Change.`;

  const triggerInner = (
    <>
      <span className="min-w-0 truncate font-medium text-foreground">
        {tier?.label}
      </span>
      <ChevronDown aria-hidden className="size-4 shrink-0 text-muted-foreground" />
    </>
  );

  const handleSelectTier = (id: ModelTierId): void => {
    haptic("selection");
    onSelectTier(id);
    setSheetOpen(false);
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          disabled={disabled}
          render={
            <button
              type="button"
              dir="ltr"
              aria-label={triggerLabel}
              data-testid="model-mode-trigger"
              className={cn(TRIGGER_CLASS, "hidden md:inline-flex")}
            >
              {triggerInner}
            </button>
          }
        />
        <DropdownMenuContent
          align="start"
          side="top"
          sideOffset={8}
          data-testid="model-menu"
          className="w-80 max-w-[min(22rem,calc(100vw-1.5rem))] rounded-2xl p-1.5"
        >
          <DropdownMenuGroup>
            <GroupHeading>Model</GroupHeading>
            {tiers.map((t) => (
              <TierRow
                key={t.id}
                tier={t}
                badge={t.id === cheapestTierId ? "Cheapest" : undefined}
                selected={t.id === selectedTierId}
                onSelect={() => handleSelectTier(t.id)}
              />
            ))}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={sheetOpen} onOpenChange={setSheetOpen}>
        <DialogTrigger
          disabled={disabled}
          render={
            <button
              type="button"
              dir="ltr"
              aria-label={triggerLabel}
              data-testid="model-mode-trigger"
              className={cn(TRIGGER_CLASS, "md:hidden")}
            >
              {triggerInner}
            </button>
          }
        />
        <DialogContent
          data-testid="model-sheet"
          className="flex [--dialog-max-h:80dvh] max-h-[80dvh] min-h-0 flex-col gap-3 overflow-hidden px-4 pt-4 pb-[max(env(safe-area-inset-bottom),1rem)] sm:max-h-none sm:p-6"
        >
          <DialogHeader className="shrink-0">
            <DialogTitle>Model</DialogTitle>
            <DialogDescription className="sr-only">
              Choose which model answers your next message.
            </DialogDescription>
          </DialogHeader>
          <div className="-mx-1 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain pb-8">
            <SheetSection title="Model">
              {tiers.map((t) => {
                const selected = t.id === selectedTierId;
                return (
                  <SheetRow
                    key={t.id}
                    label={t.label}
                    description={
                      selected
                        ? [t.description, tierMeta(t)].filter(Boolean).join(" · ")
                        : tierMeta(t)
                    }
                    badge={t.id === cheapestTierId ? "Cheapest" : undefined}
                    selected={selected}
                    onSelect={() => handleSelectTier(t.id)}
                  />
                );
              })}
            </SheetSection>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function GroupHeading({ children }: { children: ReactNode }): JSX.Element {
  return (
    <DropdownMenuLabel className="px-2 pt-1 pb-0.5 ui-eyebrow font-semibold tracking-wide text-muted-foreground uppercase">
      {children}
    </DropdownMenuLabel>
  );
}

function TierRow({
  tier,
  badge,
  selected,
  onSelect,
}: {
  tier: ModelTier;
  badge?: string;
  selected: boolean;
  onSelect: () => void;
}): JSX.Element {
  const meta = tierMeta(tier);
  return (
    <DropdownMenuItem label={tier.label} onClick={onSelect} className="py-1.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="shrink-0 font-medium">{tier.label}</span>
          {meta ? (
            <span className="min-w-0 truncate ui-caption leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/70">
              {meta}
            </span>
          ) : null}
          {badge ? <ValueBadge label={badge} /> : null}
          {selected ? (
            <Check aria-hidden className="ml-auto size-4 shrink-0 text-foreground" />
          ) : null}
        </div>
        {selected && tier.description ? (
          <p className="mt-0.5 ui-secondary leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
            {tier.description}
          </p>
        ) : null}
      </div>
    </DropdownMenuItem>
  );
}

function SheetSection({
  title,
  children,
}: {
  title?: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <div className="flex flex-col">
      {title ? (
        <p className="px-4 pb-1 ui-eyebrow font-semibold tracking-wide text-muted-foreground uppercase">
          {title}
        </p>
      ) : null}
      <ul className="flex flex-col">{children}</ul>
    </div>
  );
}

function SheetRow({
  label,
  description,
  badge,
  selected,
  disabled,
  onSelect,
}: {
  label: string;
  description: string;
  badge?: string;
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
}): JSX.Element {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        disabled={disabled}
        aria-label={label}
        aria-pressed={selected}
        className={cn(
          "flex min-h-11 w-full items-start gap-3 rounded-xl px-4 py-2.5 text-left transition-colors hover:bg-foreground/[0.04] focus-visible:bg-foreground/[0.04] focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
          selected && "bg-foreground/[0.06]",
          disabled && "cursor-not-allowed opacity-50",
        )}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="min-w-0 truncate ui-list-row font-medium text-foreground">
              {label}
            </span>
            {badge ? <ValueBadge label={badge} /> : null}
          </div>
          {description ? (
            <p className="mt-0.5 ui-secondary leading-snug text-muted-foreground">
              {description}
            </p>
          ) : null}
        </div>
        {selected ? (
          <Check aria-hidden className="mt-0.5 size-4 shrink-0 text-foreground" />
        ) : null}
      </button>
    </li>
  );
}

function ValueBadge({ label }: { label: string }): JSX.Element {
  return (
    <span className="shrink-0 rounded-full bg-foreground/[0.06] px-1.5 py-0.5 ui-eyebrow font-semibold tracking-wide text-muted-foreground uppercase">
      {label}
    </span>
  );
}

function tierMeta(tier: ModelTier): string {
  const parts = [tier.modelLabel, tier.supportsAttachments ? "Attachments" : ""];
  return parts.filter(Boolean).join(" · ");
}

function cheapestAvailableTierId(tiers: ModelTier[]): ModelTierId | null {
  let best: { id: ModelTierId; price: number } | null = null;
  for (const t of tiers) {
    if (t.id === "auto") continue;
    if (t.providerRouteStatus !== "available") continue;
    const price = t.listPriceInPerM + t.listPriceOutPerM;
    if (price <= 0) continue;
    if (best === null || price < best.price) {
      best = { id: t.id, price };
    }
  }
  return best?.id ?? null;
}
