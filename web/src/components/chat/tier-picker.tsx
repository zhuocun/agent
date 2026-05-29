"use client";

import { useState, type JSX } from "react";
import { Check, ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
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
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { ModelTier, ModelTierId } from "@/lib/types";

export interface TierPickerProps {
  tiers: ModelTier[];
  selectedId: ModelTierId;
  onSelect: (id: ModelTierId) => void;
  disabled?: boolean;
}

// Shared trigger styling — identical between the desktop dropdown and the
// mobile bottom-sheet variants per PRD 06 §5.6 / PRD 01 §5.3 (the trigger's
// appearance is stable; only the disclosure surface changes by modality).
const TRIGGER_CLASS =
  "inline-flex h-11 items-center gap-1 rounded-full bg-muted/60 px-3 text-xs text-muted-foreground hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground data-[popup-open]:bg-muted data-[popup-open]:text-foreground [&_svg:not([class*='size-'])]:size-3.5";

export function TierPicker({ tiers, selectedId, onSelect, disabled }: TierPickerProps): JSX.Element {
  const selected = tiers.find((t) => t.id === selectedId) ?? tiers[0];
  const [sheetOpen, setSheetOpen] = useState(false);

  const triggerLabel = selected
    ? `Model: ${selected.label}. Change model tier.`
    : "Change model tier.";

  const handleSelect = (id: ModelTierId): void => {
    onSelect(id);
    setSheetOpen(false);
  };

  const triggerInner = (
    <>
      <span className="font-medium text-foreground">{selected?.label}</span>
      <ChevronDown aria-hidden className="text-muted-foreground" />
    </>
  );

  return (
    <>
      {/* Desktop: hover/click dropdown anchored to the trigger. Density-splits-
          by-input-modality (02-patterns §D) — hover does not exist on touch so
          the mobile branch below renders a bottom sheet instead. */}
      <DropdownMenu>
        <DropdownMenuTrigger
          disabled={disabled}
          render={
            <Button
              type="button"
              variant="ghost"
              className={cn(TRIGGER_CLASS, "hidden md:inline-flex")}
              aria-label={triggerLabel}
            >
              {triggerInner}
            </Button>
          }
        />
        <DropdownMenuContent
          align="start"
          sideOffset={8}
          className="w-64 max-w-[min(18rem,calc(100vw-1.5rem))] rounded-2xl"
        >
          {tiers.map((tier) => {
            const isSelected = tier.id === selectedId;
            return (
              <DropdownMenuItem
                key={tier.id}
                label={tier.label}
                onClick={() => onSelect(tier.id)}
                className="py-2"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{tier.label}</span>
                    {isSelected ? (
                      <Check
                        aria-hidden
                        className="ml-auto size-4 text-foreground"
                      />
                    ) : null}
                  </div>
                  <p className="mt-0.5 text-xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
                    {tier.description}
                  </p>
                </div>
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Mobile: bottom sheet. Decision 10 + Pattern: Thumb zone primacy. The
          sheet rises from the bottom, honours safe-area-inset-bottom via the
          --bottom-inset token, and each row meets the PRD 06 §3.3 44px touch
          target floor. */}
      <Dialog open={sheetOpen} onOpenChange={setSheetOpen}>
        <DialogTrigger
          disabled={disabled}
          render={
            <Button
              type="button"
              variant="ghost"
              className={cn(TRIGGER_CLASS, "md:hidden")}
              aria-label={triggerLabel}
            >
              {triggerInner}
            </Button>
          }
        />
        <DialogContent className="top-auto bottom-0 left-0 max-h-[80dvh] max-w-full translate-x-0 translate-y-0 gap-3 rounded-t-3xl rounded-b-none p-4 pb-[calc(var(--bottom-inset)+0.5rem)]">
          <div
            aria-hidden
            className="mx-auto -mt-1 h-1.5 w-9 rounded-full bg-foreground/15"
          />
          <DialogHeader>
            <DialogTitle className="text-base">Model</DialogTitle>
            <DialogDescription className="sr-only">
              Choose which capability tier answers your next message.
            </DialogDescription>
          </DialogHeader>
          <ul className="-mx-1 flex flex-col overflow-y-auto">
            {tiers.map((tier) => {
              const isSelected = tier.id === selectedId;
              return (
                <li key={tier.id}>
                  <button
                    type="button"
                    onClick={() => handleSelect(tier.id)}
                    aria-label={tier.label}
                    aria-pressed={isSelected}
                    className={cn(
                      "flex min-h-11 w-full items-start gap-3 rounded-xl px-4 py-3 text-left transition-colors hover:bg-foreground/[0.04] focus-visible:bg-foreground/[0.04] focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
                      isSelected && "bg-foreground/[0.06]",
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-foreground">
                          {tier.label}
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
                        {tier.description}
                      </p>
                    </div>
                    {isSelected ? (
                      <Check
                        aria-hidden
                        className="mt-0.5 size-4 shrink-0 text-foreground"
                      />
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </DialogContent>
      </Dialog>
    </>
  );
}
