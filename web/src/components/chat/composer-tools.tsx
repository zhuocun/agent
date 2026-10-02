"use client";

import { useId, useState, type JSX, type ReactNode } from "react";
import { Braces, Check, ChevronDown, Globe, SlidersHorizontal, Telescope } from "lucide-react";

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
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { haptic } from "@/lib/use-haptic";
import { cn } from "@/lib/utils";
import type {
  ModelTier,
  ModelTierId,
  ProviderDataPolicy,
  ProviderTierOption,
  ReasoningEffort,
  ReasoningEffortId,
} from "@/lib/types";

export interface ComposerToolsProps {
  tiers: ModelTier[];
  selectedTierId: ModelTierId;
  providerOptions: ProviderTierOption[];
  selectedProviderId?: string;
  onSelectProvider: (id: string) => void;
  efforts: ReasoningEffort[];
  selectedEffortId: ReasoningEffortId;
  onSelectEffort: (id: ReasoningEffortId) => void;
  // False when the served provider ignores reasoning effort (e.g. Anthropic).
  // The whole Reasoning-effort section is then omitted.
  effortSupported?: boolean;
  searchEnabled: boolean;
  onToggleSearch: (next: boolean) => void;
  jsonModeEnabled: boolean;
  onToggleJsonMode: (next: boolean) => void;
  showDeepResearch?: boolean;
  deepResearchEnabled?: boolean;
  onToggleDeepResearch?: (next: boolean) => void;
  disabled?: boolean;
}

// Quiet toolbar pill. Icon-only until a provider or a non-default effort is
// selected, then those labels sit on the button so the choice stays visible
// without opening the menu. Height stays on the 44px touch floor.
const TRIGGER_CLASS =
  "relative inline-flex h-11 min-h-11 shrink-0 items-center justify-center gap-1 rounded-full text-muted-foreground outline-none transition-colors hover:bg-foreground/[0.06] hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring aria-expanded:bg-foreground/[0.08] aria-expanded:text-foreground";

export function ComposerTools({
  tiers,
  selectedTierId,
  providerOptions,
  selectedProviderId,
  onSelectProvider,
  efforts,
  selectedEffortId,
  onSelectEffort,
  effortSupported = true,
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
  const provider =
    providerOptions.find((p) => p.providerId === selectedProviderId) ??
    providerOptions.find((p) => p.status === "available") ??
    providerOptions[0];
  const effort = efforts.find((e) => e.id === selectedEffortId) ?? efforts[0];
  const [sheetOpen, setSheetOpen] = useState(false);
  const showWebSearch = tier?.supportsWebSearch === true;
  const availableProviderCount = providerOptions.filter(
    (p) => p.status === "available",
  ).length;
  const showProviderPicker = availableProviderCount > 1;
  const providerLabel =
    showProviderPicker && provider?.providerId ? provider.label : undefined;
  const dataPolicy = provider?.dataPolicy ?? tier?.dataPolicy ?? null;
  const showEffort = Boolean(effort?.label && effort.label !== tier?.label);
  const anyToolOn =
    (showWebSearch && searchEnabled) ||
    (showDeepResearch && deepResearchEnabled) ||
    jsonModeEnabled;
  const hasStatus = Boolean(providerLabel || showEffort);

  const ariaLabel = toolsAriaLabel({
    showWebSearch,
    searchEnabled,
    showDeepResearch,
    deepResearchEnabled,
    jsonModeEnabled,
    providerLabel,
    effortLabel: effort?.label,
  });

  const handleSelectProvider = (id: string): void => {
    haptic("selection");
    onSelectProvider(id);
    setSheetOpen(false);
  };

  const handleSelectEffort = (id: ReasoningEffortId): void => {
    haptic("selection");
    onSelectEffort(id);
    setSheetOpen(false);
  };

  const triggerFace = (showStatus: boolean): JSX.Element => (
    <>
      <SlidersHorizontal aria-hidden className="size-4 shrink-0" />
      {showStatus && providerLabel ? (
        <span className="max-w-24 truncate">{providerLabel}</span>
      ) : null}
      {showStatus && showEffort && effort ? (
        <span className="truncate">{effort.label}</span>
      ) : null}
      {showStatus ? (
        <ChevronDown aria-hidden className="size-4 shrink-0" />
      ) : null}
      {anyToolOn ? (
        <span
          aria-hidden
          className="absolute top-1 right-1 size-1.5 rounded-full bg-brand"
        />
      ) : null}
    </>
  );

  const menuBody = (
    <>
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
      {showProviderPicker || effortSupported || dataPolicy ? (
        <DropdownMenuSeparator />
      ) : null}
      {showProviderPicker ? (
        <DropdownMenuGroup>
          <GroupHeading>Provider</GroupHeading>
          {providerOptions.map((p) => {
            const available = p.status === "available";
            return (
              <CompactRow
                key={p.providerId}
                label={p.label}
                meta={providerDescription(p)}
                selected={p.providerId === provider?.providerId}
                disabled={!available}
                onSelect={() => handleSelectProvider(p.providerId)}
              />
            );
          })}
        </DropdownMenuGroup>
      ) : null}
      {effortSupported ? (
        <DropdownMenuGroup className={showProviderPicker ? "mt-1" : undefined}>
          <GroupHeading>Reasoning effort</GroupHeading>
          {efforts.map((e) => (
            <CompactRow
              key={e.id}
              label={e.label}
              meta={effortMeta(e)}
              selected={e.id === selectedEffortId}
              onSelect={() => handleSelectEffort(e.id)}
            />
          ))}
        </DropdownMenuGroup>
      ) : null}
      {dataPolicy ? (
        <DropdownMenuGroup>
          <DataPolicyRow policy={dataPolicy} />
        </DropdownMenuGroup>
      ) : null}
    </>
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
                      hasStatus ? "max-w-40 px-3" : "w-11",
                      anyToolOn && "text-foreground",
                    )}
                  >
                    {triggerFace(hasStatus)}
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
                      "w-11",
                      anyToolOn && "text-foreground",
                    )}
                  >
                    {triggerFace(false)}
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
              Turn tools on or off, and choose the provider, reasoning effort,
              and data policy for the next message.
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
            {showProviderPicker ? (
              <SheetSection title="Provider">
                {providerOptions.map((p) => {
                  const available = p.status === "available";
                  return (
                    <SheetRow
                      key={p.providerId}
                      label={p.label}
                      description={providerDescription(p)}
                      selected={p.providerId === provider?.providerId}
                      disabled={!available}
                      onSelect={() => handleSelectProvider(p.providerId)}
                    />
                  );
                })}
              </SheetSection>
            ) : null}
            {effortSupported ? (
              <SheetSection title="Reasoning effort">
                {efforts.map((e) => (
                  <SheetRow
                    key={e.id}
                    label={e.label}
                    description={effortMeta(e) ?? ""}
                    selected={e.id === selectedEffortId}
                    onSelect={() => handleSelectEffort(e.id)}
                  />
                ))}
              </SheetSection>
            ) : null}
            {dataPolicy ? (
              <SheetSection title="Data policy">
                <li>
                  <p className="px-4 py-2 ui-caption leading-snug text-muted-foreground">
                    {dataPolicy.policyLabel}
                  </p>
                </li>
              </SheetSection>
            ) : null}
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
  providerLabel?: string;
  effortLabel?: string;
}): string {
  const parts = ["Tools"];
  if (state.showWebSearch) {
    parts.push(`Web search ${state.searchEnabled ? "on" : "off"}`);
  }
  if (state.showDeepResearch) {
    parts.push(`Deep Research ${state.deepResearchEnabled ? "on" : "off"}`);
  }
  parts.push(`JSON output ${state.jsonModeEnabled ? "on" : "off"}`);
  if (state.providerLabel) parts.push(`Provider ${state.providerLabel}`);
  if (state.effortLabel) parts.push(`Reasoning ${state.effortLabel}`);
  return `${parts.join(". ")}.`;
}

function GroupHeading({ children }: { children: ReactNode }): JSX.Element {
  return (
    <DropdownMenuLabel className="px-2 pt-1 pb-0.5 ui-eyebrow font-semibold tracking-wide text-muted-foreground uppercase">
      {children}
    </DropdownMenuLabel>
  );
}

function CompactRow({
  label,
  meta,
  selected,
  disabled,
  onSelect,
}: {
  label: string;
  meta?: string;
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
}): JSX.Element {
  return (
    <DropdownMenuItem
      label={label}
      onClick={onSelect}
      disabled={disabled}
      className="py-1.5"
    >
      <span className="shrink-0 font-medium">{label}</span>
      {meta ? (
        <span className="min-w-0 ui-caption leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/70">
          {meta}
        </span>
      ) : null}
      {selected ? (
        <Check aria-hidden className="ml-auto size-4 shrink-0 text-foreground" />
      ) : null}
    </DropdownMenuItem>
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

function DataPolicyRow({ policy }: { policy: ProviderDataPolicy }): JSX.Element {
  return (
    <DropdownMenuLabel className="px-2 py-1.5 ui-caption font-normal tracking-normal text-muted-foreground normal-case">
      <span className="font-semibold">Data policy:</span> {policy.policyLabel}
    </DropdownMenuLabel>
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

function SheetRow({
  label,
  description,
  selected,
  disabled,
  onSelect,
}: {
  label: string;
  description: string;
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
          <span className="block truncate ui-list-row font-medium text-foreground">
            {label}
          </span>
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

function providerDescription(provider: ProviderTierOption): string {
  if (provider.status === "pending") return "Coming soon.";
  if (provider.status === "unavailable") return "Unavailable.";
  return provider.dataPolicy?.policyLabel ?? "Available for this turn.";
}

function effortMeta(effort: ReasoningEffort): string | undefined {
  if (effort.costHint === "auto") return undefined;
  return `Cost ${effort.costHint} · Latency ${effort.latencyHint}`;
}
