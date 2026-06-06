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
  DropdownMenuCheckboxItem,
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
  // The effort rows are then rendered DISABLED with a one-line note — never an
  // error. Defaults to true (supported) when omitted.
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
const TRIGGER_CLASS =
  "inline-flex h-11 min-w-0 items-center gap-1.5 rounded-full px-3 text-base outline-none transition-colors hover:bg-foreground/5 focus-visible:ring-2 focus-visible:ring-ring aria-expanded:bg-foreground/5";

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
  const triggerInner = (
    <>
      <span className="truncate font-medium text-foreground">{tier?.label}</span>
      {providerLabel ? (
        <span className="hidden max-w-24 truncate text-muted-foreground sm:inline">
          {providerLabel}
        </span>
      ) : null}
      {showEffort ? (
        <span className="text-muted-foreground">{effort.label}</span>
      ) : null}
      <ChevronDown aria-hidden className="size-4 text-muted-foreground" />
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
          the mobile branch below renders a bottom sheet instead. */}
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
          sideOffset={8}
          className="w-72 max-w-[min(20rem,calc(100vw-1.5rem))] rounded-2xl"
        >
          {showProviderPicker ? (
            <>
              <DropdownMenuGroup>
                <DropdownMenuLabel className="text-2xs font-semibold">
                  Provider
                </DropdownMenuLabel>
                {providerOptions.map((p) => {
                  const available = p.status === "available";
                  return (
                    <DropdownRow
                      key={p.providerId}
                      label={p.label}
                      description={providerDescription(p)}
                      selected={p.providerId === provider?.providerId}
                      disabled={!available}
                      onSelect={() => handleSelectProvider(p.providerId)}
                    />
                  );
                })}
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
            </>
          ) : null}
          <DropdownMenuGroup>
            <DropdownMenuLabel className="text-2xs font-semibold">
              Model
            </DropdownMenuLabel>
            {tiers.map((t) => (
              <DropdownRow
                key={t.id}
                label={t.label}
                description={t.description}
                meta={tierMeta(t)}
                badge={t.id === cheapestTierId ? "Cheapest" : undefined}
                selected={t.id === selectedTierId}
                onSelect={() => handleSelectTier(t.id)}
              />
            ))}
          </DropdownMenuGroup>
          {dataPolicy ? (
            <>
              <DropdownMenuSeparator />
              <DataPolicyRow policy={dataPolicy} />
            </>
          ) : null}
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuLabel className="text-2xs font-semibold">
              Reasoning effort
            </DropdownMenuLabel>
            {efforts.map((e) => (
              <DropdownRow
                key={e.id}
                label={e.label}
                description={e.description}
                meta={effortMeta(e)}
                selected={e.id === selectedEffortId}
                disabled={!effortSupported}
                onSelect={() => onSelectEffort(e.id)}
              />
            ))}
            {!effortSupported ? (
              <p className="px-3 py-1.5 text-xs leading-snug text-muted-foreground">
                This model ignores reasoning effort.
              </p>
            ) : null}
          </DropdownMenuGroup>
          {showWebSearch ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuLabel className="text-2xs font-semibold">
                  Web search
                </DropdownMenuLabel>
                {/* `closeOnClick={false}` keeps the menu open so toggling
                    search on/off doesn't dismiss the picker mid-decision. The
                    checkbox item exposes role="menuitemcheckbox"/aria-checked
                    and renders its own check indicator on the right (so no
                    inline glyph here — that would double the check). */}
                <DropdownMenuCheckboxItem
                  checked={searchEnabled}
                  closeOnClick={false}
                  onCheckedChange={(next) => onToggleSearch(next)}
                  className="py-2"
                  data-testid="web-search-toggle"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">
                        {searchEnabled ? "On" : "Off"}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
                      Ground answers with a live web search.
                    </p>
                  </div>
                </DropdownMenuCheckboxItem>
              </DropdownMenuGroup>
            </>
          ) : null}
          {/* JSON output is NOT tier-gated (unlike web search above) — every
              tier accepts it, so this section always renders. */}
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuLabel className="text-2xs font-semibold">
              JSON output
            </DropdownMenuLabel>
            {/* Mirrors the web-search toggle: `closeOnClick={false}` keeps the
                menu open across the flip, and the checkbox item exposes
                role="menuitemcheckbox"/aria-checked with its own check
                indicator (no inline glyph). */}
            <DropdownMenuCheckboxItem
              checked={jsonModeEnabled}
              closeOnClick={false}
              onCheckedChange={(next) => onToggleJsonMode(next)}
              className="py-2"
              data-testid="json-mode-toggle"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">
                    {jsonModeEnabled ? "On" : "Off"}
                  </span>
                </div>
                <p className="mt-0.5 text-xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
                  Ask the model to reply with a JSON object.
                </p>
              </div>
            </DropdownMenuCheckboxItem>
          </DropdownMenuGroup>
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
          indicator; `sm:p-6` then restores even padding on the desktop modal. The
          old `top-auto bottom-0 translate-*-0 rounded-t-3xl rounded-b-none`
          overrides just re-stated the shell's own geometry — dropping them lets
          the picker inherit the shell's clean grabber + swipe path. Each row
          still meets the PRD 06 §3.3 44px touch floor. */}
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
            <SheetSection title="Model">
              {tiers.map((t) => (
                <SheetRow
                  key={t.id}
                  label={t.label}
                  description={[t.description, tierMeta(t)]
                    .filter(Boolean)
                    .join(" · ")}
                  badge={t.id === cheapestTierId ? "Cheapest" : undefined}
                  selected={t.id === selectedTierId}
                  onSelect={() => handleSelectTier(t.id)}
                />
              ))}
            </SheetSection>
            {dataPolicy ? (
              <SheetSection title="Data policy">
                <li>
                  <p className="px-4 py-2 text-xs leading-snug text-muted-foreground">
                    {dataPolicy.policyLabel}
                  </p>
                </li>
              </SheetSection>
            ) : null}
            <SheetSection title="Reasoning effort">
              {efforts.map((e) => (
                <SheetRow
                  key={e.id}
                  label={e.label}
                  description={[e.description, effortMeta(e)]
                    .filter(Boolean)
                    .join(" · ")}
                  selected={e.id === selectedEffortId}
                  disabled={!effortSupported}
                  onSelect={() => handleSelectEffort(e.id)}
                />
              ))}
              {!effortSupported ? (
                <li>
                  <p className="px-4 py-2 text-xs leading-snug text-muted-foreground">
                    This model ignores reasoning effort.
                  </p>
                </li>
              ) : null}
            </SheetSection>
            {showWebSearch ? (
              <SheetSection title="Web search">
                {/* Toggle stays in-sheet (no auto-dismiss) so the user can see
                    the On/Off state flip before closing. */}
                <SheetRow
                  label={searchEnabled ? "On" : "Off"}
                  description="Ground answers with a live web search."
                  selected={searchEnabled}
                  onSelect={() => onToggleSearch(!searchEnabled)}
                  testId="web-search-toggle"
                />
              </SheetSection>
            ) : null}
            {/* JSON output isn't tier-gated, so this section always renders. */}
            <SheetSection title="JSON output">
              <SheetRow
                label={jsonModeEnabled ? "On" : "Off"}
                description="Ask the model to reply with a JSON object."
                selected={jsonModeEnabled}
                onSelect={() => onToggleJsonMode(!jsonModeEnabled)}
                testId="json-mode-toggle"
              />
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
  meta,
  badge,
  selected,
  disabled,
  onSelect,
}: {
  label: string;
  description: string;
  meta?: string;
  badge?: string;
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
}): JSX.Element {
  return (
    <DropdownMenuItem
      label={label}
      onClick={onSelect}
      disabled={disabled}
      className="py-2"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium">{label}</span>
          {badge ? <ValueBadge label={badge} /> : null}
          {selected ? (
            <Check aria-hidden className="ml-auto size-4 text-foreground" />
          ) : null}
        </div>
        <p className="mt-0.5 text-xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
          {description}
        </p>
        {meta ? (
          <p className="mt-0.5 truncate text-2xs leading-snug text-muted-foreground/80 group-focus/dropdown-menu-item:text-accent-foreground/70">
            {meta}
          </p>
        ) : null}
      </div>
    </DropdownMenuItem>
  );
}

function DataPolicyRow({ policy }: { policy: ProviderDataPolicy }): JSX.Element {
  return (
    <div className="px-3 py-2">
      <p className="text-2xs font-semibold text-muted-foreground">
        Data policy
      </p>
      <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
        {policy.policyLabel}
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
          "flex min-h-11 w-full items-start gap-3 rounded-xl px-4 py-3 text-left transition-colors hover:bg-foreground/[0.04] focus-visible:bg-foreground/[0.04] focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
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

function providerDescription(provider: ProviderTierOption): string {
  if (provider.status === "pending") return "Coming soon.";
  if (provider.status === "unavailable") return "Unavailable.";
  return provider.dataPolicy?.policyLabel ?? "Available for this turn.";
}

// A subtle "Cheapest" (or similar) pill rendered next to a model row's label.
// Purely informational — selection never changes on its own.
function ValueBadge({ label }: { label: string }): JSX.Element {
  return (
    <span className="shrink-0 rounded-full bg-brand/10 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-brand uppercase">
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
