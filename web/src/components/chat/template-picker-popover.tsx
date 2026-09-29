"use client";

import { useId, useMemo, type JSX, type RefObject } from "react";
import { FileText } from "lucide-react";

import { Popover, PopoverContent } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import type { PromptTemplate } from "@/lib/types";

export interface TemplatePickerPopoverProps {
  open: boolean;
  items: PromptTemplate[];
  query: string;
  selectedIndex: number;
  onSelectedIndexChange: (next: number) => void;
  onPick: (template: PromptTemplate) => void;
  onClose: () => void;
  // Whether the user's templates are still being fetched (first open). When
  // true and nothing has loaded yet, the popover shows a loading hint instead
  // of the empty-state.
  loading?: boolean;
  // Optional ids so the composer can wire combobox ↔ listbox/activedescendant
  // pairs across the two components.
  listboxId?: string;
  optionIdPrefix?: string;
  // Optional anchor element (the composer container) used for positioning
  // and to keep interactions inside the composer from dismissing the popover.
  anchorRef?: RefObject<HTMLElement | null>;
}

// Case-insensitive title/description/body filter. Pure so the composer can
// compute the same filtered set when handling Enter/Tab without re-renders.
export function filterTemplates(
  templates: PromptTemplate[],
  query: string,
): PromptTemplate[] {
  const q = query.trim().toLowerCase();
  if (!q) return templates;
  return templates.filter(
    (t) =>
      t.title.toLowerCase().includes(q) ||
      (t.description ?? "").toLowerCase().includes(q) ||
      t.body.toLowerCase().includes(q),
  );
}

export function TemplatePickerPopover({
  open,
  items,
  query,
  selectedIndex,
  onSelectedIndexChange,
  onPick,
  onClose,
  loading = false,
  listboxId,
  optionIdPrefix,
  anchorRef,
}: TemplatePickerPopoverProps): JSX.Element | null {
  const fallbackListboxId = useId();
  const fallbackOptionPrefix = useId();
  const resolvedListboxId = listboxId ?? fallbackListboxId;
  const resolvedOptionPrefix = optionIdPrefix ?? fallbackOptionPrefix;

  const filtered = useMemo(
    () => filterTemplates(items, query),
    [items, query],
  );

  if (!open) return null;

  const clamped =
    filtered.length === 0
      ? -1
      : Math.min(Math.max(selectedIndex, 0), filtered.length - 1);

  return (
    <Popover
      open={open}
      modal={false}
      onOpenChange={(nextOpen, details) => {
        if (nextOpen) return;
        const target = details.event.target;
        if (
          details.reason === "outside-press" &&
          target instanceof Node &&
          anchorRef?.current?.contains(target)
        ) {
          return;
        }
        onClose();
      }}
    >
      <PopoverContent
        anchor={anchorRef}
        collisionPadding={0}
        side="top"
        align="start"
        sideOffset={8}
        initialFocus={false}
        finalFocus={false}
        role="presentation"
        data-testid="template-picker"
        className={cn(
          "w-(--anchor-width) gap-0 overflow-hidden rounded-2xl p-0 text-base text-foreground",
          // Mirrors the slash popover's iOS entrance: a spring pop from a
          // slightly-shrunk, faded state; reduced motion falls back to a plain
          // cross-fade with no scale/translate.
          "origin-bottom transition-[opacity,transform,scale] duration-200 ease-[var(--ease-ios-spring)]",
          "starting:scale-95 starting:opacity-0 starting:translate-y-1",
          "motion-reduce:transition-opacity motion-reduce:duration-150 motion-reduce:scale-100 motion-reduce:translate-y-0",
        )}
      >
        <div id={`${resolvedListboxId}-label`} className="sr-only">
          Prompt templates
        </div>
        {/* Always render the listbox so `aria-controls` on the textarea points
            at a real element — even when no templates match. An empty listbox is
            valid ARIA; the hint sits alongside it inside the popup. */}
        <ul
          role="listbox"
          id={resolvedListboxId}
          aria-labelledby={`${resolvedListboxId}-label`}
          className={cn(
            "max-h-72 overflow-y-auto overscroll-contain py-1",
            filtered.length === 0 && "sr-only",
          )}
        >
          {filtered.map((template, index) => {
            const isSelected = index === clamped;
            const id = `${resolvedOptionPrefix}-${index}`;
            return (
              <li
                key={template.id}
                id={id}
                role="option"
                aria-selected={isSelected}
                onMouseEnter={() => onSelectedIndexChange(index)}
                onPointerDown={(e) => {
                  // pointerdown beats the textarea's blur, which would unmount the
                  // popover before the click resolved.
                  e.preventDefault();
                  onPick(template);
                }}
                data-testid="template-picker-option"
                className={cn(
                  // min-h-11: 44pt touch floor on the touch sheet (harmless on
                  // desktop). Quiet translucent selection tint to match the
                  // slash popover.
                  "mx-1 flex min-h-11 cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 ui-list-row text-foreground",
                  isSelected && "bg-foreground/[0.06]",
                )}
              >
                <span
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-lg",
                    isSelected
                      ? "bg-brand/10 text-foreground"
                      : "bg-secondary text-muted-foreground",
                  )}
                >
                  <FileText aria-hidden className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block ui-list-row font-medium truncate">
                    {template.title}
                  </span>
                  <span className="block truncate ui-caption text-muted-foreground">
                    {template.description?.trim() || template.body}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
        {filtered.length === 0 ? (
          <div className="px-4 py-3 ui-body text-muted-foreground">
            {loading
              ? "Loading your templates…"
              : items.length === 0
                ? "No templates yet. Add some in Settings → Prompt templates."
                : "No templates match."}
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
