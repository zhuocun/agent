"use client";

import { useState, type JSX, type ReactNode } from "react";
import { Check, ChevronDown, ChevronRight, Globe, Braces } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

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
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type {
  ModelTier,
  ModelTierId,
  ProviderDataPolicy,
  ProviderTierOption,
  ReasoningEffort,
  ReasoningEffortId,
} from "@/lib/types";

export interface ModelModePickerProps {
  tiers: ModelTier[];
  selectedTierId: ModelTierId;
  onSelectTier: (id: ModelTierId) => void;
  providerOptions: ProviderTierOption[];
  selectedProviderId?: string;
  onSelectProvider: (id: string) => void;
  efforts: ReasoningEffort[];
  selectedEffortId: ReasoningEffortId;
  onSelectEffort: (id: ReasoningEffortId) => void;
  // False when the served provider ignores reasoning effort (e.g. Anthropic).
  // The whole Reasoning-effort section is then OMITTED (progressive disclosure,
  // 00-principles §20) rather than shown as disabled rows — never an error.
  // Defaults to true (supported) when omitted.
  effortSupported?: boolean;
  // Web-search toggle. The "Web search" section is shown ONLY when the
  // currently-selected tier reports `supportsWebSearch`; on a tier that can't
  // search, the toggle is hidden entirely (the BE would ignore the flag).
  searchEnabled: boolean;
  onToggleSearch: (next: boolean) => void;
  // JSON-mode (structured-output) toggle. Unlike web search this is NOT
  // tier-gated — every tier accepts it (the BE handles provider-specific
  // best-effort), so the "JSON output" section always renders.
  jsonModeEnabled: boolean;
  onToggleJsonMode: (next: boolean) => void;
  disabled?: boolean;
}

// Shared trigger styling — identical between the desktop dropdown and the
// mobile bottom-sheet variants per PRD 06 §5.6 / PRD 01 §5.3 (the trigger's
// appearance is stable; only the disclosure surface changes by modality).
// Restyled for the trigger's home in the composer TOOLBAR (Lovable-style
// model dropdown): a compact text-sm ghost pill that sits flush with the
// surrounding muted icon buttons while keeping the 44px touch floor
// (PRD 06 §3.3). The mobile max-width budgets for the toolbar's siblings
// (+ / mic / send circles) so the trigger can never push them off-card.
// Lovable's "Fable 5" model selector reads as a subtle pill, not a bare text
// run: a faint resting fill + hairline rim sets it apart from the muted icon
// circles flanking it, while staying quiet enough not to compete with the send
// button. Hover/expanded deepen the fill; focus shows the ring.
const TRIGGER_CLASS =
  "inline-flex h-11 min-w-0 max-w-[min(12rem,calc(100vw-16rem))] items-center gap-1 rounded-full px-3 text-sm outline-none transition-colors bg-foreground/[0.04] shadow-[inset_0_0_0_1px_var(--glass-border)] hover:bg-foreground/[0.08] focus-visible:ring-2 focus-visible:ring-ring aria-expanded:bg-foreground/[0.08] md:max-w-80";

export function ModelModePicker({
  tiers,
  selectedTierId,
  onSelectTier,
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
  disabled,
}: ModelModePickerProps): JSX.Element {
  const tier = tiers.find((t) => t.id === selectedTierId) ?? tiers[0];
  // Value-aware hint (PRD 05 §4.5 D27 / PRD 07 §6.3): flag the cheapest capable
  // route. A LABEL ONLY — it never changes the selection automatically.
  const cheapestTierId = cheapestAvailableTierId(tiers);
  const provider =
    providerOptions.find((p) => p.providerId === selectedProviderId) ??
    providerOptions.find((p) => p.status === "available") ??
    providerOptions[0];
  const effort = efforts.find((e) => e.id === selectedEffortId) ?? efforts[0];
  const [sheetOpen, setSheetOpen] = useState(false);
  // The web-search section only exists for tiers that support it; the parent
  // also clears `searchEnabled` when switching to a non-supporting tier, so
  // this is a pure display gate.
  const showWebSearch = tier?.supportsWebSearch === true;
  const availableProviderCount = providerOptions.filter(
    (p) => p.status === "available",
  ).length;
  const showProviderPicker = availableProviderCount > 1;
  const providerLabel =
    showProviderPicker && provider?.providerId ? provider.label : undefined;
  const dataPolicy = provider?.dataPolicy ?? tier?.dataPolicy ?? null;

  const triggerLabel = `Model ${tier?.label}${
    providerLabel ? ` on ${providerLabel}` : ""
  }, reasoning ${effort?.label}. Change.`;

  // Hide the reasoning-effort label when it duplicates the tier label (the
  // default "Auto"/"Auto" case, and any future collision) so the header states
  // the model state once rather than stuttering. The accessible triggerLabel
  // above still announces both values for screen-reader users.
  const showEffort = effort?.label && effort.label !== tier?.label;
  // Mobile minimalism: under md the trigger collapses to just the tier label so
  // the bar reads as one tap-target word; the provider + effort meta only return
  // at md+ where there's room for the full state line. The accessible
  // `triggerLabel` (above) still announces every value to AT regardless.
  const triggerInner = (
    <>
      <span className="min-w-0 truncate font-medium text-foreground">
        {tier?.label}
      </span>
      {providerLabel ? (
        <span className="hidden max-w-24 truncate text-muted-foreground md:inline">
          {providerLabel}
        </span>
      ) : null}
      {showEffort ? (
        <span className="hidden text-muted-foreground md:inline">
          {effort.label}
        </span>
      ) : null}
      <ChevronDown aria-hidden className="size-4 shrink-0 text-muted-foreground" />
    </>
  );

  const handleSelectTier = (id: ModelTierId): void => {
    onSelectTier(id);
    setSheetOpen(false);
  };

  const handleSelectProvider = (id: string): void => {
    onSelectProvider(id);
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
          the mobile branch below renders a bottom sheet instead.

          Progressive disclosure (00-principles §20, 02-patterns §75-86): the
          surface opens as a one-decision QUICK SWITCH. Only the Model tier group
          is shown at the first level; Provider, Reasoning effort, Data policy,
          Web search, and JSON output all live behind the "Advanced" collapsible
          so secondary controls never compete with the primary tier choice. This
          matches the mobile sheet's disclosure, just rendered as a dropdown. */}
      <DropdownMenu>
        <DropdownMenuTrigger
          disabled={disabled}
          render={
            <button
              type="button"
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
          // The trigger now anchors at the BOTTOM of the viewport (composer
          // toolbar), so the menu opens upward by default.
          side="top"
          sideOffset={8}
          className="w-80 max-w-[min(22rem,calc(100vw-1.5rem))] rounded-2xl p-1.5"
        >
          {/* Model tier — the only first-level decision, so it leads. Each row
              is one tight line (label · model · price); the longer description
              renders ONLY under the selected tier, in a quieter treatment. */}
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

          {/* First-level toggles — Web search + JSON output are tap-and-go
              switches users reach for mid-prompt, so they sit OUT of Advanced.
              Web search is tier-gated; JSON output always renders.
              `closeOnClick={false}` keeps the menu open across a flip so the
              state change is seen. */}
          <DropdownMenuGroup className="mt-1.5">
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
            <ToggleRow
              icon={Braces}
              label="JSON output"
              description="Ask the model to reply with a JSON object."
              checked={jsonModeEnabled}
              onToggle={onToggleJsonMode}
              testId="json-mode-toggle"
            />
          </DropdownMenuGroup>

          {/* Advanced — progressive disclosure (00-principles §20). Provider,
              reasoning effort, and data policy collapse here so the picker
              opens minimal; power users expand to reach them. Mirrors the
              mobile sheet's Advanced section for cross-modality parity. */}
          <Collapsible className="mt-1">
            <CollapsibleTrigger
              data-testid="picker-advanced"
              className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-2xs font-semibold tracking-wide text-muted-foreground uppercase outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:text-accent-foreground"
            >
              <ChevronRight
                aria-hidden
                className="size-3.5 shrink-0 transition-transform [[data-panel-open]_&]:rotate-90"
              />
              Advanced
            </CollapsibleTrigger>
            <CollapsibleContent>
              {showProviderPicker ? (
                <DropdownMenuGroup className="mt-1">
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

              {dataPolicy ? <DataPolicyRow policy={dataPolicy} /> : null}

              {/* Reasoning effort — omitted ENTIRELY when the served provider
                  ignores it (effortSupported=false): per progressive disclosure
                  (00-principles §20) we hide the whole section rather than show
                  disabled rows plus a note. */}
              {effortSupported ? (
                <DropdownMenuGroup className="mt-1">
                  <GroupHeading>Reasoning effort</GroupHeading>
                  {efforts.map((e) => (
                    <CompactRow
                      key={e.id}
                      label={e.label}
                      meta={effortMeta(e)}
                      selected={e.id === selectedEffortId}
                      onSelect={() => onSelectEffort(e.id)}
                    />
                  ))}
                </DropdownMenuGroup>
              ) : null}
            </CollapsibleContent>
          </Collapsible>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Mobile: bottom sheet. Decision 10 + Pattern: Thumb zone primacy. We
          ride the shared <DialogContent> shell, which already supplies the
          bottom-sheet geometry (fixed inset-x-0 bottom-0, rounded top, spring
          slide, grabber, swipe-to-dismiss, home-indicator-safe bottom padding)
          and reverts to the centered modal at sm:. So we pass ONLY intent here:
          a slightly tighter `gap-3 px-4 pt-4` density for the dense option rows
          and a 80dvh cap (vs the shell's 90dvh) so the sheet sits a touch lower.
          We re-state the shell's safe-area `pb` explicitly because a bare `p-4`
          shorthand would twMerge-clobber it and drop the last row under the home
          indicator; `sm:p-6` then restores even padding on the desktop modal.
          Each row still meets the PRD 06 §3.3 44px touch floor. */}
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
        <DialogContent className="max-h-[80dvh] gap-3 px-4 pt-4 pb-[max(env(safe-area-inset-bottom),1rem)] sm:max-h-none sm:p-6">
          <DialogHeader>
            <DialogTitle>Model and reasoning</DialogTitle>
            <DialogDescription className="sr-only">
              Choose which capability tier and reasoning effort answer your next
              message.
            </DialogDescription>
          </DialogHeader>
          <div className="-mx-1 flex flex-col gap-4 overflow-y-auto">
            {/* Tier leads on mobile too, and is the ONLY section shown by
                default. The full description rides only on the selected row; the
                rest carry the compact model · price meta. */}
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
            {/* First-level toggles — Web search + JSON output are tap-and-go
                switches users reach for mid-prompt, so they sit OUT of Advanced
                in the mobile sheet too. Mirrors the desktop dropdown order. */}
            {showWebSearch ? (
              <SheetSection title="Web search">
                <SheetRow
                  label={searchEnabled ? "On" : "Off"}
                  description="Ground answers with a live web search."
                  selected={searchEnabled}
                  onSelect={() => onToggleSearch(!searchEnabled)}
                  testId="web-search-toggle"
                />
              </SheetSection>
            ) : null}
            <SheetSection title="JSON output">
              <SheetRow
                label={jsonModeEnabled ? "On" : "Off"}
                description="Ask the model to reply with a JSON object."
                selected={jsonModeEnabled}
                onSelect={() => onToggleJsonMode(!jsonModeEnabled)}
                testId="json-mode-toggle"
              />
            </SheetSection>
            {/* Advanced — progressive disclosure (00-principles §20). Provider,
                reasoning effort, and data policy collapse here for iOS-native
                simplicity: the sheet opens showing only the Model tier and the
                two switches, and power users expand to reach the rest. Parity
                with the desktop dropdown's Advanced section. */}
            <Collapsible>
              <CollapsibleTrigger
                data-testid="picker-advanced"
                className="flex min-h-11 w-full items-center gap-2 rounded-xl px-4 py-2.5 text-left text-2xs font-semibold tracking-wide text-muted-foreground uppercase transition-colors hover:bg-foreground/[0.04]"
              >
                <ChevronRight
                  aria-hidden
                  className="size-3.5 shrink-0 transition-transform [[data-panel-open]_&]:rotate-90"
                />
                Advanced
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="flex flex-col gap-4 pt-2">
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
                  {/* Reasoning effort — omitted ENTIRELY when the served provider
                      ignores it (effortSupported=false), rather than rendering
                      disabled rows plus a note (00-principles §20). */}
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
                        <p className="px-4 py-2 text-xs leading-snug text-muted-foreground">
                          {dataPolicy.policyLabel}
                        </p>
                      </li>
                    </SheetSection>
                  ) : null}
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

// Group heading for the dropdown. A tight, quiet caption that delineates groups
// via typographic hierarchy + spacing rather than full-bleed rules
// (00-principles §20). Reuses the menu label primitive for role/semantics.
function GroupHeading({ children }: { children: ReactNode }): JSX.Element {
  return (
    <DropdownMenuLabel className="px-2 pt-1 pb-0.5 text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
      {children}
    </DropdownMenuLabel>
  );
}

// The primary tier row: a single scannable line (label · model · price) with a
// trailing check. The longer marketing `description` is revealed ONLY for the
// selected tier, in a lighter caption — matching visual weight to the user's
// current intent (02-patterns §75-86) instead of repeating prose on every row.
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
    <DropdownMenuItem
      label={tier.label}
      onClick={onSelect}
      className="py-1.5"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="shrink-0 font-medium">{tier.label}</span>
          {meta ? (
            <span className="min-w-0 text-2xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/70">
              {meta}
            </span>
          ) : null}
          {badge ? <ValueBadge label={badge} /> : null}
          {selected ? (
            <Check aria-hidden className="ml-auto size-4 shrink-0 text-foreground" />
          ) : null}
        </div>
        {selected && tier.description ? (
          <p className="mt-0.5 text-2xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
            {tier.description}
          </p>
        ) : null}
      </div>
    </DropdownMenuItem>
  );
}

// A secondary single-line row (Provider / Reasoning effort): label on the left,
// a compact muted meta clause, trailing check. No wrapped description block.
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
        <span className="min-w-0 text-2xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/70">
          {meta}
        </span>
      ) : null}
      {selected ? (
        <Check aria-hidden className="ml-auto size-4 shrink-0 text-foreground" />
      ) : null}
    </DropdownMenuItem>
  );
}

// Switch-like toggle row for Web search / JSON output. `closeOnClick={false}`
// keeps the menu open so the on/off flip is visible mid-decision; the checkbox
// item exposes role="menuitemcheckbox"/aria-checked and renders its own check
// indicator on the right. A leading Lucide icon (currentColor) anchors the row;
// the compact On/Off state sits inline so the row stays a single line.
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
      className="py-1.5"
      data-testid={testId}
      aria-label={`${label}: ${checked ? "on" : "off"}`}
    >
      <Icon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">{label}</span>
          <span className="text-2xs text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/70">
            {checked ? "On" : "Off"}
          </span>
        </div>
        <p className="text-2xs leading-snug text-muted-foreground">
          {description}
        </p>
      </div>
    </DropdownMenuCheckboxItem>
  );
}

// Data policy line for the dropdown — display only. Sits inline (label + value)
// rather than as its own boxed section so it reads as a quiet footnote.
function DataPolicyRow({ policy }: { policy: ProviderDataPolicy }): JSX.Element {
  return (
    <div className="mt-1 px-2 py-1">
      <p className="text-2xs leading-snug text-muted-foreground">
        <span className="font-semibold">Data policy:</span> {policy.policyLabel}
      </p>
    </div>
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
      <p className="px-4 pb-1 text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
        {title}
      </p>
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
  testId,
}: {
  label: string;
  description: string;
  badge?: string;
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
  testId?: string;
}): JSX.Element {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        disabled={disabled}
        aria-label={label}
        aria-pressed={selected}
        data-testid={testId}
        className={cn(
          "flex min-h-11 w-full items-start gap-3 rounded-xl px-4 py-2.5 text-left transition-colors hover:bg-foreground/[0.04] focus-visible:bg-foreground/[0.04] focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
          selected && "bg-foreground/[0.06]",
          disabled && "cursor-not-allowed opacity-50",
        )}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="min-w-0 truncate text-sm font-medium text-foreground">
              {label}
            </span>
            {badge ? <ValueBadge label={badge} /> : null}
          </div>
          {description ? (
            <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
              {description}
            </p>
          ) : null}
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

function providerDescription(provider: ProviderTierOption): string {
  if (provider.status === "pending") return "Coming soon.";
  if (provider.status === "unavailable") return "Unavailable.";
  return provider.dataPolicy?.policyLabel ?? "Available for this turn.";
}

// A subtle "Cheapest" (or similar) pill rendered next to a model row's label.
// Purely informational — selection never changes on its own. STATIC chip (never
// animated/pulsing, per 02-patterns §73).
function ValueBadge({ label }: { label: string }): JSX.Element {
  return (
    <span className="shrink-0 rounded-full bg-foreground/[0.06] px-1.5 py-0.5 text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
      {label}
    </span>
  );
}

function tierMeta(tier: ModelTier): string {
  const parts = [
    tier.modelLabel,
    tierPriceMeta(tier),
    tier.supportsAttachments ? "Attachments" : "",
  ];
  return parts.filter(Boolean).join(" · ");
}

// Per-million-token list price hint, e.g. "$0.14/M in · $0.28/M out". Empty for
// unpriced tiers ("auto", or any tier whose binding is missing a price) so the
// row simply omits it rather than showing "$0/M".
function tierPriceMeta(tier: ModelTier): string {
  if (tier.listPriceInPerM <= 0 && tier.listPriceOutPerM <= 0) return "";
  return `$${tier.listPriceInPerM}/M in · $${tier.listPriceOutPerM}/M out`;
}

// The cheapest tier with an AVAILABLE route and a real price, by combined
// in+out list price. Returns null when no priced+available tier exists (e.g.
// only "auto" is priced at 0, or all routes are pending/unavailable).
function cheapestAvailableTierId(tiers: ModelTier[]): ModelTierId | null {
  let best: { id: ModelTierId; price: number } | null = null;
  for (const t of tiers) {
    // "auto" is a per-turn router, not a single route — its price varies by
    // message, so it's never the thing we flag as "cheapest".
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

// Relative cost/latency hint for an effort row, surfacing the trade-off so a
// "max reasoning" pick can't be made without seeing it (PRD 01 §4.2). Skipped
// for "Auto" (its hints are "auto", which carry no signal worth showing).
function effortMeta(effort: ReasoningEffort): string | undefined {
  if (effort.costHint === "auto") return undefined;
  return `Cost ${effort.costHint} · Latency ${effort.latencyHint}`;
}
