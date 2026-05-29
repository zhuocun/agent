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
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type {
  ModelTier,
  ModelTierId,
  ReasoningEffort,
  ReasoningEffortId,
} from "@/lib/types";

export interface ModelModePickerProps {
  tiers: ModelTier[];
  selectedTierId: ModelTierId;
  onSelectTier: (id: ModelTierId) => void;
  efforts: ReasoningEffort[];
  selectedEffortId: ReasoningEffortId;
  onSelectEffort: (id: ReasoningEffortId) => void;
  disabled?: boolean;
}

// Shared trigger styling — identical between the desktop dropdown and the
// mobile bottom-sheet variants per PRD 06 §5.6 / PRD 01 §5.3 (the trigger's
// appearance is stable; only the disclosure surface changes by modality).
const TRIGGER_CLASS =
  "inline-flex h-11 min-w-0 items-center gap-1.5 rounded-full px-3 text-base outline-none transition-colors hover:bg-foreground/5 focus-visible:ring-2 focus-visible:ring-ring aria-expanded:bg-foreground/5";

export function ModelModePicker({
  tiers,
  selectedTierId,
  onSelectTier,
  efforts,
  selectedEffortId,
  onSelectEffort,
  disabled,
}: ModelModePickerProps): JSX.Element {
  const tier = tiers.find((t) => t.id === selectedTierId) ?? tiers[0];
  const effort = efforts.find((e) => e.id === selectedEffortId) ?? efforts[0];
  const [sheetOpen, setSheetOpen] = useState(false);

  const triggerLabel = `Model ${tier?.label}, reasoning ${effort?.label}. Change.`;

  const triggerInner = (
    <>
      <span className="truncate font-medium text-foreground">{tier?.label}</span>
      <span className="text-muted-foreground">{effort?.label}</span>
      <ChevronDown aria-hidden className="size-4 text-muted-foreground" />
    </>
  );

  const handleSelectTier = (id: ModelTierId): void => {
    onSelectTier(id);
    setSheetOpen(false);
  };

  const handleSelectEffort = (id: ReasoningEffortId): void => {
    onSelectEffort(id);
    setSheetOpen(false);
  };

  return (
    <>
      {/* Desktop: hover/click dropdown anchored to the trigger. Density-splits-
          by-input-modality (02-patterns §D) — hover does not exist on touch so
          the mobile branch below renders a bottom sheet instead. */}
      <DropdownMenu>
        <DropdownMenuTrigger
          disabled={disabled}
          render={
            <button
              type="button"
              aria-label={triggerLabel}
              className={cn(TRIGGER_CLASS, "hidden md:inline-flex")}
            >
              {triggerInner}
            </button>
          }
        />
        <DropdownMenuContent
          align="start"
          sideOffset={8}
          className="w-72 max-w-[min(20rem,calc(100vw-1.5rem))] rounded-2xl"
        >
          <DropdownMenuGroup>
            <DropdownMenuLabel className="text-[11px] font-semibold">
              Model
            </DropdownMenuLabel>
            {tiers.map((t) => (
              <DropdownRow
                key={t.id}
                label={t.label}
                description={t.description}
                selected={t.id === selectedTierId}
                onSelect={() => onSelectTier(t.id)}
              />
            ))}
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuLabel className="text-[11px] font-semibold">
              Reasoning effort
            </DropdownMenuLabel>
            {efforts.map((e) => (
              <DropdownRow
                key={e.id}
                label={e.label}
                description={e.description}
                selected={e.id === selectedEffortId}
                onSelect={() => onSelectEffort(e.id)}
              />
            ))}
          </DropdownMenuGroup>
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
            <button
              type="button"
              aria-label={triggerLabel}
              className={cn(TRIGGER_CLASS, "md:hidden")}
            >
              {triggerInner}
            </button>
          }
        />
        <DialogContent className="top-auto bottom-0 left-0 max-h-[80dvh] max-w-full translate-x-0 translate-y-0 gap-3 rounded-t-3xl rounded-b-none p-4 pb-[calc(var(--bottom-inset)+0.5rem)]">
          <div
            aria-hidden
            className="mx-auto -mt-1 h-1.5 w-9 rounded-full bg-foreground/15"
          />
          <DialogHeader>
            <DialogTitle className="text-base">Model and reasoning</DialogTitle>
            <DialogDescription className="sr-only">
              Choose which capability tier and reasoning effort answer your next
              message.
            </DialogDescription>
          </DialogHeader>
          <div className="-mx-1 flex flex-col gap-4 overflow-y-auto">
            <SheetSection title="Model">
              {tiers.map((t) => (
                <SheetRow
                  key={t.id}
                  label={t.label}
                  description={t.description}
                  selected={t.id === selectedTierId}
                  onSelect={() => handleSelectTier(t.id)}
                />
              ))}
            </SheetSection>
            <SheetSection title="Reasoning effort">
              {efforts.map((e) => (
                <SheetRow
                  key={e.id}
                  label={e.label}
                  description={e.description}
                  selected={e.id === selectedEffortId}
                  onSelect={() => handleSelectEffort(e.id)}
                />
              ))}
            </SheetSection>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function DropdownRow({
  label,
  description,
  selected,
  onSelect,
}: {
  label: string;
  description: string;
  selected: boolean;
  onSelect: () => void;
}): JSX.Element {
  return (
    <DropdownMenuItem label={label} onClick={onSelect} className="py-2">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">{label}</span>
          {selected ? (
            <Check aria-hidden className="ml-auto size-4 text-foreground" />
          ) : null}
        </div>
        <p className="mt-0.5 text-xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
          {description}
        </p>
      </div>
    </DropdownMenuItem>
  );
}

function SheetSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <div className="flex flex-col">
      <p className="px-4 pb-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
        {title}
      </p>
      <ul className="flex flex-col">{children}</ul>
    </div>
  );
}

function SheetRow({
  label,
  description,
  selected,
  onSelect,
}: {
  label: string;
  description: string;
  selected: boolean;
  onSelect: () => void;
}): JSX.Element {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-label={label}
        aria-pressed={selected}
        className={cn(
          "flex min-h-11 w-full items-start gap-3 rounded-xl px-4 py-3 text-left transition-colors hover:bg-foreground/[0.04] focus-visible:bg-foreground/[0.04] focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
          selected && "bg-foreground/[0.06]",
        )}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground">{label}</span>
          </div>
          <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
            {description}
          </p>
        </div>
        {selected ? (
          <Check
            aria-hidden
            className="mt-0.5 size-4 shrink-0 text-foreground"
          />
        ) : null}
      </button>
    </li>
  );
}
