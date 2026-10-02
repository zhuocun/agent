"use client";

import { useId, useState, type JSX, type ReactNode } from "react";
import { Braces, Globe, SlidersHorizontal, Telescope } from "lucide-react";

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
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { haptic } from "@/lib/use-haptic";
import { cn } from "@/lib/utils";
import type { ModelTier, ModelTierId } from "@/lib/types";

export interface ComposerToolsProps {
  tiers: ModelTier[];
  selectedTierId: ModelTierId;
  searchEnabled: boolean;
  onToggleSearch: (next: boolean) => void;
  jsonModeEnabled: boolean;
  onToggleJsonMode: (next: boolean) => void;
  showDeepResearch?: boolean;
  deepResearchEnabled?: boolean;
  onToggleDeepResearch?: (next: boolean) => void;
  disabled?: boolean;
}

// Quiet 44px toolbar button. A brand dot appears when any tool is on, so the
// choice stays visible without a second label on the pill.
const TRIGGER_CLASS =
  "relative inline-flex h-11 min-h-11 w-11 shrink-0 items-center justify-center rounded-full text-muted-foreground outline-none transition-colors hover:bg-foreground/[0.06] hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring aria-expanded:bg-foreground/[0.08] aria-expanded:text-foreground";

export function ComposerTools({
  tiers,
  selectedTierId,
  searchEnabled,
  onToggleSearch,
  jsonModeEnabled,
  onToggleJsonMode,
  showDeepResearch = false,
  deepResearchEnabled = false,
  onToggleDeepResearch,
  disabled,
}: ComposerToolsProps): JSX.Element {
  const tier = tiers.find((t) => t.id === selectedTierId) ?? tiers[0];
  const [sheetOpen, setSheetOpen] = useState(false);
  const showWebSearch = tier?.supportsWebSearch === true;
  const anyToolOn =
    (showWebSearch && searchEnabled) ||
    (showDeepResearch && deepResearchEnabled) ||
    jsonModeEnabled;

  const ariaLabel = toolsAriaLabel({
    showWebSearch,
    searchEnabled,
    showDeepResearch,
    deepResearchEnabled,
    jsonModeEnabled,
  });

  const triggerFace = (
    <>
      <SlidersHorizontal aria-hidden className="size-4 shrink-0" />
      {anyToolOn ? (
        <span
          aria-hidden
          className="absolute top-1 right-1 size-1.5 rounded-full bg-brand"
        />
      ) : null}
    </>
  );

  const menuBody = (
    <DropdownMenuGroup>
      <GroupHeading>Tools</GroupHeading>
      {showWebSearch ? (
        <ToggleRow
          icon={Globe}
          label="Web search"
          description="Ground answers with a live web search."
          checked={searchEnabled}
          onToggle={onToggleSearch}
          testId="web-search-toggle"
        />
      ) : null}
      {showDeepResearch && onToggleDeepResearch ? (
        <ToggleRow
          icon={Telescope}
          label="Deep Research"
          description="Fan out parallel research agents and synthesize their findings."
          checked={deepResearchEnabled}
          onToggle={onToggleDeepResearch}
          testId="deep-research-toggle"
        />
      ) : null}
      <ToggleRow
        icon={Braces}
        label="JSON output"
        description="Ask the model to reply with a JSON object."
        checked={jsonModeEnabled}
        onToggle={onToggleJsonMode}
        testId="json-mode-toggle"
      />
    </DropdownMenuGroup>
  );

  return (
    <>
      <DropdownMenu>
        <Tooltip>
          <TooltipTrigger
            render={
              <DropdownMenuTrigger
                disabled={disabled}
                render={
                  <button
                    type="button"
                    aria-label={ariaLabel}
                    data-testid="composer-tools"
                    className={cn(
                      TRIGGER_CLASS,
                      "hidden md:inline-flex",
                      anyToolOn && "text-foreground",
                    )}
                  >
                    {triggerFace}
                  </button>
                }
              />
            }
          />
          <TooltipContent>Tools</TooltipContent>
        </Tooltip>
        <DropdownMenuContent
          align="start"
          side="top"
          sideOffset={8}
          data-testid="tools-menu"
          className="w-80 max-w-[min(22rem,calc(100vw-1.5rem))] rounded-2xl p-1.5"
        >
          {menuBody}
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={sheetOpen} onOpenChange={setSheetOpen}>
        <Tooltip>
          <TooltipTrigger
            render={
              <DialogTrigger
                disabled={disabled}
                render={
                  <button
                    type="button"
                    aria-label={ariaLabel}
                    data-testid="composer-tools"
                    className={cn(
                      TRIGGER_CLASS,
                      "md:hidden",
                      anyToolOn && "text-foreground",
                    )}
                  >
                    {triggerFace}
                  </button>
                }
              />
            }
          />
          <TooltipContent>Tools</TooltipContent>
        </Tooltip>
        <DialogContent
          data-testid="tools-sheet"
          className="flex [--dialog-max-h:80dvh] max-h-[80dvh] min-h-0 flex-col gap-3 overflow-hidden px-4 pt-4 pb-[max(env(safe-area-inset-bottom),1rem)] sm:max-h-none sm:p-6"
        >
          <DialogHeader className="shrink-0">
            <DialogTitle>Tools</DialogTitle>
            <DialogDescription className="sr-only">
              Turn Web search, Deep Research, and JSON output on or off.
            </DialogDescription>
          </DialogHeader>
          <div className="-mx-1 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain pb-8">
            <SheetSection title="Tools">
              {showWebSearch ? (
                <SheetToggleRow
                  label="Web search"
                  description="Ground answers with a live web search."
                  checked={searchEnabled}
                  onCheckedChange={onToggleSearch}
                  testId="web-search-toggle"
                />
              ) : null}
              {showDeepResearch && onToggleDeepResearch ? (
                <SheetToggleRow
                  label="Deep Research"
                  description="Fan out parallel research agents and synthesize their findings."
                  checked={deepResearchEnabled}
                  onCheckedChange={onToggleDeepResearch}
                  testId="deep-research-toggle"
                />
              ) : null}
              <SheetToggleRow
                label="JSON output"
                description="Ask the model to reply with a JSON object."
                checked={jsonModeEnabled}
                onCheckedChange={onToggleJsonMode}
                testId="json-mode-toggle"
              />
            </SheetSection>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function toolsAriaLabel(state: {
  showWebSearch: boolean;
  searchEnabled: boolean;
  showDeepResearch: boolean;
  deepResearchEnabled: boolean;
  jsonModeEnabled: boolean;
}): string {
  const parts = ["Tools"];
  if (state.showWebSearch) {
    parts.push(`Web search ${state.searchEnabled ? "on" : "off"}`);
  }
  if (state.showDeepResearch) {
    parts.push(`Deep Research ${state.deepResearchEnabled ? "on" : "off"}`);
  }
  parts.push(`JSON output ${state.jsonModeEnabled ? "on" : "off"}`);
  return `${parts.join(". ")}.`;
}

function GroupHeading({ children }: { children: ReactNode }): JSX.Element {
  return (
    <DropdownMenuLabel className="px-2 pt-1 pb-0.5 ui-eyebrow font-semibold tracking-wide text-muted-foreground uppercase">
      {children}
    </DropdownMenuLabel>
  );
}

function ToggleRow({
  icon: Icon,
  label,
  description,
  checked,
  onToggle,
  testId,
}: {
  icon: typeof Globe;
  label: string;
  description: string;
  checked: boolean;
  onToggle: (next: boolean) => void;
  testId: string;
}): JSX.Element {
  return (
    <DropdownMenuCheckboxItem
      checked={checked}
      closeOnClick={false}
      onCheckedChange={(next) => onToggle(next)}
      className="items-center py-1.5"
      data-testid={testId}
      aria-label={`${label}: ${checked ? "on" : "off"}`}
    >
      <Icon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">{label}</span>
          <span className="ui-caption text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/70">
            {checked ? "On" : "Off"}
          </span>
        </div>
        <p className="sr-only">{description}</p>
      </div>
    </DropdownMenuCheckboxItem>
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
      <p className="px-4 pb-1 ui-eyebrow font-semibold tracking-wide text-muted-foreground uppercase">
        {title}
      </p>
      <ul className="flex flex-col">{children}</ul>
    </div>
  );
}

function SheetToggleRow({
  label,
  description,
  checked,
  onCheckedChange,
  testId,
}: {
  label: string;
  description: string;
  checked: boolean;
  onCheckedChange: (next: boolean) => void;
  testId: string;
}): JSX.Element {
  const labelId = useId();
  const descriptionId = useId();
  return (
    <li>
      <button
        type="button"
        role="switch"
        data-testid={testId}
        aria-checked={checked}
        aria-labelledby={labelId}
        aria-describedby={descriptionId}
        onClick={() => {
          haptic("selection");
          onCheckedChange(!checked);
        }}
        className={cn(
          "flex min-h-11 w-full items-center gap-3 rounded-xl px-4 py-2.5 text-left transition-colors",
          "hover:bg-foreground/[0.04] focus-visible:bg-foreground/[0.04] focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
          checked && "bg-foreground/[0.06]",
        )}
      >
        <span className="min-w-0 flex-1">
          <span id={labelId} className="block ui-list-row font-medium text-foreground">
            {label}
          </span>
          <span id={descriptionId} className="sr-only">
            {description}
          </span>
        </span>
        <span
          aria-hidden
          data-checked={checked ? "" : undefined}
          className="inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-border bg-muted/60 transition-colors data-[checked]:border-transparent data-[checked]:bg-brand"
        >
          <span
            data-checked={checked ? "" : undefined}
            className="block size-4 translate-x-0.5 rounded-full bg-card shadow-glass-ambient transition-transform duration-[250ms] ease-ios-spring motion-reduce:duration-150 motion-reduce:ease-out data-[checked]:translate-x-4"
          />
        </span>
      </button>
    </li>
  );
}
