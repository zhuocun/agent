"use client";

import { useId, useState, type JSX, type ReactNode } from "react";
import { CreditCard, Gauge, Key, LogOut, Receipt } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { ByokForm } from "@/components/chat/byok-form";
import { TierPicker } from "@/components/chat/tier-picker";
import { ThemeToggle } from "@/components/chat/theme-toggle";
import {
  getUsagePresentation,
  UsageMeter,
} from "@/components/chat/usage-meter";
import { SpendDialog } from "@/components/chat/spend-dialog";
import { MODEL_TIERS } from "@/lib/model-tiers";
import {
  createBillingCheckout,
  createBillingPortal,
  type BillingCheckoutKind,
} from "@/lib/apiClient";
import {
  isAnonymousAccount,
  type AccountInfo,
  type ModelTierId,
  type Project,
  type UserPreferences,
  type UsageBudget,
} from "@/lib/types";
import type { ProjectUpdateInput } from "@/lib/apiClient";
import { cn } from "@/lib/utils";

export interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preferences: UserPreferences;
  onPreferencesChange: (next: UserPreferences) => void;
  account: AccountInfo;
  onAccountChange: (next: AccountInfo) => void;
  usage: UsageBudget;
  // Persist a new monthly spend cap (or `null` to clear it). Wired through the
  // existing preferences flow in the parent.
  onSaveBudget: (value: number | null) => void;
  onSignOut: () => void;
  // Open the auth dialog (closing settings first). Anonymous-only affordances —
  // upgrade/credits/BYOK — route here instead of dead-ending on disabled chrome.
  onRequestSignIn: () => void;
  onExportData: () => void;
  onDeleteAccount: () => void;
  // Open the read-only "Activity & data access" surface (closing settings
  // first). Lists the data-access log + the processing-provenance rollup.
  onOpenActivity: () => void;
  // Open the "Memory" manager (closing settings first): the opt-in toggle +
  // the editable, attributed fact ledger (D19).
  onOpenMemory: () => void;
  // Open the "Prompt templates" manager (closing settings first): the editable
  // library of user-authored, reusable prompt templates (D23).
  onOpenTemplates: () => void;
  // Open the read-only "Models & data policies" directory (closing settings
  // first). Browsable catalog of provider routes, policies, and prices.
  onOpenModelDirectory: () => void;
  // Projects/Spaces (D20). The caller's projects + an updater that PATCHes a
  // project's settings (default tier, retention, budget sub-cap, shared
  // instructions). Optional so embeddings that predate D20 still type-check.
  projects?: Project[];
  onUpdateProject?: (id: string, patch: ProjectUpdateInput) => void;
}

// Derive avatar initials from a display name (first + last token), capped at
// two letters. Falls back gracefully for single-word or empty names.
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}

// A labeled settings row: left label + helper text, right-aligned control.
// `htmlFor` ties the optional <label> to a control's id (used for switches so
// they are reachable and named); when absent the label renders as plain text
// (used for rows whose control carries its own accessible name, e.g. menus).
function SettingRow({
  label,
  helper,
  htmlFor,
  control,
}: {
  label: string;
  helper?: ReactNode;
  htmlFor?: string;
  control: ReactNode;
}): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        {htmlFor ? (
          <label htmlFor={htmlFor} className="text-sm font-medium">
            {label}
          </label>
        ) : (
          <p className="text-sm font-medium">{label}</p>
        )}
        {helper ? (
          <p className="mt-0.5 text-xs text-muted-foreground">{helper}</p>
        ) : null}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  );
}

function SectionHeading({ children }: { children: ReactNode }): JSX.Element {
  return (
    <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
      {children}
    </h3>
  );
}

type RetentionDays = UserPreferences["retentionDays"];

const RETENTION_OPTIONS: Array<{
  value: RetentionDays;
  label: string;
  description: string;
}> = [
  { value: 30, label: "30 days", description: "Delete saved chats after 30 days." },
  { value: 90, label: "90 days", description: "Delete saved chats after 90 days." },
  { value: null, label: "Forever", description: "Keep saved chats until you delete them." },
];

const CUSTOM_INSTRUCTIONS_LIMIT = 4000;

function RetentionPicker({
  value,
  onChange,
}: {
  value: RetentionDays;
  onChange: (value: RetentionDays) => void;
}): JSX.Element {
  return (
    <div
      className="grid grid-cols-3 overflow-hidden rounded-full border border-border/70 bg-secondary/40 p-0.5"
      role="group"
      aria-label="Chat retention"
    >
      {RETENTION_OPTIONS.map((option) => {
        const selected = value === option.value;
        return (
          <button
            key={option.label}
            type="button"
            aria-pressed={selected}
            title={option.description}
            onClick={() => onChange(option.value)}
            className={cn(
              "min-w-0 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
              selected
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "n/a";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  }).format(value);
}

function ledgerEntryLabel(entryType: string): string {
  if (entryType === "platform_debit") return "Usage debit";
  if (entryType === "grant") return "Grant";
  return "Adjustment";
}

// Monthly spend-cap editor (Feature 3). A small number input bound to the
// user's saved cap with an explicit Save. When the platform enforces a TIGHTER
// cap, `effectiveQuotaUsd` differs from the user cap and we surface the enforced
// figure so the user understands which limit actually binds.
function BudgetEditor({
  usage,
  onSaveBudget,
}: {
  usage: UsageBudget;
  onSaveBudget: (value: number | null) => void;
}): JSX.Element {
  const inputId = useId();
  // Bind to the saved user cap; empty string ⇒ no cap.
  const [draft, setDraft] = useState<string>(
    usage.userBudgetUsd != null ? String(usage.userBudgetUsd) : "",
  );

  // The enforced cap line only matters when the platform cap is tighter than
  // (and so overrides) the user's chosen cap.
  const userCap = usage.userBudgetUsd ?? null;
  const effectiveCap = usage.effectiveQuotaUsd ?? null;
  const showEnforced =
    effectiveCap != null && (userCap == null || effectiveCap < userCap);

  function save(): void {
    const trimmed = draft.trim();
    if (trimmed === "") {
      onSaveBudget(null);
      return;
    }
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed) || parsed < 0) return;
    onSaveBudget(parsed);
  }

  return (
    <div className="space-y-1.5 border-t border-border/50 pt-2">
      <label htmlFor={inputId} className="text-xs font-medium">
        Monthly budget cap
      </label>
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <span
            aria-hidden
            className="pointer-events-none absolute inset-y-0 left-2.5 flex items-center text-xs text-muted-foreground"
          >
            $
          </span>
          <input
            id={inputId}
            type="number"
            inputMode="decimal"
            min={0}
            step="0.01"
            value={draft}
            placeholder="No cap"
            onChange={(event) => setDraft(event.currentTarget.value)}
            data-testid="budget-cap-input"
            className="h-9 w-full rounded-xl border border-border/70 bg-background/70 pl-6 pr-3 text-sm tabular-nums text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25"
          />
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={save}
          data-testid="budget-cap-save"
        >
          Save
        </Button>
      </div>
      <p className="text-xs leading-snug text-muted-foreground">
        {showEnforced ? (
          <>
            Enforced cap:{" "}
            <span className="font-mono tabular-nums text-foreground">
              {formatUsd(effectiveCap)}
            </span>{" "}
            — the platform cap is tighter than your setting.
          </>
        ) : (
          "Pause platform-key usage once this month's spend reaches the cap. Leave empty for no cap."
        )}
      </p>
    </div>
  );
}

// Per-conversation spend-cap editor (PRD 05 §4.5 D27). Mirrors `BudgetEditor`
// but writes the `perConversationBudgetUsd` preference: the BE refuses the next
// platform-key turn once a single conversation's accumulated cost reaches it.
function PerConversationBudgetEditor({
  value,
  onSave,
}: {
  value: number | null;
  onSave: (value: number | null) => void;
}): JSX.Element {
  const inputId = useId();
  const [draft, setDraft] = useState<string>(
    value != null ? String(value) : "",
  );

  function save(): void {
    const trimmed = draft.trim();
    if (trimmed === "") {
      onSave(null);
      return;
    }
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed) || parsed < 0) return;
    onSave(parsed);
  }

  return (
    <div className="space-y-1.5 border-t border-border/50 pt-2">
      <label htmlFor={inputId} className="text-xs font-medium">
        Per-conversation cap
      </label>
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <span
            aria-hidden
            className="pointer-events-none absolute inset-y-0 left-2.5 flex items-center text-xs text-muted-foreground"
          >
            $
          </span>
          <input
            id={inputId}
            type="number"
            inputMode="decimal"
            min={0}
            step="0.01"
            value={draft}
            placeholder="No cap"
            onChange={(event) => setDraft(event.currentTarget.value)}
            data-testid="conversation-cap-input"
            className="h-9 w-full rounded-xl border border-border/70 bg-background/70 pl-6 pr-3 text-sm tabular-nums text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25"
          />
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={save}
          data-testid="conversation-cap-save"
        >
          Save
        </Button>
      </div>
      <p className="text-xs leading-snug text-muted-foreground">
        Pause platform-key turns in any single chat once its spend reaches this
        cap. Leave empty for no per-conversation cap.
      </p>
    </div>
  );
}

// Tier options for a Project's create-time default (D20), including the
// "Inherit" choice (`null` = use the user's global default tier). The concrete
// tiers mirror the global tier picker's `MODEL_TIERS`.
const PROJECT_TIER_OPTIONS: Array<{ value: ModelTierId | null; label: string }> = [
  { value: null, label: "Inherit" },
  ...MODEL_TIERS.map((tier) => ({ value: tier.id, label: tier.label })),
];

// Retention options for a Project (D20). `null` = inherit the user-global
// retention. Mirrors the per-conversation retention choices.
const PROJECT_RETENTION_OPTIONS: Array<{ value: number | null; label: string }> = [
  { value: null, label: "Inherit" },
  { value: 30, label: "30 days" },
  { value: 90, label: "90 days" },
];

// The per-project settings panel (D20). A project selector plus the four wedge
// controls — shared instructions, default tier, retention, and a
// per-conversation budget sub-cap — each writing to the project PATCH endpoint
// via `onUpdate`. Mirrors the global controls; every setting is OPTIONAL and
// `null` means "inherit the user-global value". Keyed editors reset their local
// draft when the selected project changes.
function ProjectSettingsPanel({
  projects,
  onUpdate,
}: {
  projects: Project[];
  onUpdate: (id: string, patch: ProjectUpdateInput) => void;
}): JSX.Element {
  const selectId = useId();
  const instructionsId = useId();
  const [selectedId, setSelectedId] = useState<string>(projects[0]?.id ?? "");
  // Keep a valid selection as the project list changes (create/delete).
  const selected =
    projects.find((p) => p.id === selectedId) ?? projects[0] ?? null;

  if (projects.length === 0) {
    return (
      <p className="text-xs leading-snug text-muted-foreground">
        No projects yet. Create one from the sidebar to scope a default model,
        retention, budget, and shared instructions for a group of chats.
      </p>
    );
  }

  if (!selected) return <></>;

  return (
    <div className="space-y-4" data-testid="project-settings-panel">
      <SettingRow
        label="Project"
        helper="Settings below apply to this project's chats."
        htmlFor={selectId}
        control={
          <select
            id={selectId}
            value={selected.id}
            onChange={(event) => setSelectedId(event.currentTarget.value)}
            data-testid="project-settings-select"
            className="h-9 max-w-[12rem] truncate rounded-xl border border-border/70 bg-background/70 px-3 text-sm text-foreground outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/25"
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        }
      />

      <SettingRow
        label="Default model"
        helper="Tier new chats in this project start with."
        control={
          <div
            className="flex flex-wrap gap-1 rounded-full border border-border/70 bg-secondary/40 p-0.5"
            role="group"
            aria-label="Project default model"
          >
            {PROJECT_TIER_OPTIONS.map((option) => {
              const active = (selected.defaultTierId ?? null) === option.value;
              return (
                <button
                  key={option.label}
                  type="button"
                  aria-pressed={active}
                  onClick={() =>
                    onUpdate(selected.id, { defaultTierId: option.value })
                  }
                  className={cn(
                    "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                    active
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        }
      />

      <SettingRow
        label="Retention"
        helper="Overrides your global retention for this project's chats."
        control={
          <div
            className="grid grid-cols-3 overflow-hidden rounded-full border border-border/70 bg-secondary/40 p-0.5"
            role="group"
            aria-label="Project retention"
          >
            {PROJECT_RETENTION_OPTIONS.map((option) => {
              const active = (selected.retentionDays ?? null) === option.value;
              return (
                <button
                  key={option.label}
                  type="button"
                  aria-pressed={active}
                  onClick={() =>
                    onUpdate(selected.id, { retentionDays: option.value })
                  }
                  className={cn(
                    "min-w-0 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                    active
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        }
      />

      <ProjectBudgetEditor
        key={`budget-${selected.id}`}
        value={selected.perConversationBudgetUsd ?? null}
        onSave={(value) =>
          onUpdate(selected.id, { perConversationBudgetUsd: value })
        }
      />

      <div className="space-y-2">
        <label htmlFor={instructionsId} className="text-sm font-medium">
          Shared instructions
        </label>
        <ProjectInstructionsEditor
          key={`instructions-${selected.id}`}
          id={instructionsId}
          value={selected.customInstructions ?? ""}
          onCommit={(value) =>
            onUpdate(selected.id, {
              customInstructions: value.trim().length > 0 ? value : null,
            })
          }
        />
        <p className="text-xs leading-snug text-muted-foreground">
          Appended to your global custom instructions for every chat in this
          project.
        </p>
      </div>
    </div>
  );
}

// A keyed textarea for a Project's shared instructions, committing on blur (the
// same draft/commit discipline as the global custom-instructions field).
function ProjectInstructionsEditor({
  id,
  value,
  onCommit,
}: {
  id: string;
  value: string;
  onCommit: (value: string) => void;
}): JSX.Element {
  const [draft, setDraft] = useState(value);
  return (
    <>
      <textarea
        id={id}
        value={draft}
        maxLength={CUSTOM_INSTRUCTIONS_LIMIT}
        rows={4}
        onChange={(event) => setDraft(event.currentTarget.value)}
        onBlur={() => {
          if (draft !== value) onCommit(draft);
        }}
        data-testid="project-instructions-input"
        className="min-h-24 w-full resize-y rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-sm leading-5 text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25"
        placeholder="Context, tone, or constraints shared across this project"
      />
      <div className="text-right font-mono text-[11px] tabular-nums text-muted-foreground">
        {draft.length}/{CUSTOM_INSTRUCTIONS_LIMIT}
      </div>
    </>
  );
}

// A keyed per-conversation budget sub-cap editor for a Project (D20). Mirrors
// `PerConversationBudgetEditor` but its empty value means "inherit the user
// preference" rather than "no cap".
function ProjectBudgetEditor({
  value,
  onSave,
}: {
  value: number | null;
  onSave: (value: number | null) => void;
}): JSX.Element {
  const inputId = useId();
  const [draft, setDraft] = useState<string>(
    value != null ? String(value) : "",
  );

  function save(): void {
    const trimmed = draft.trim();
    if (trimmed === "") {
      onSave(null);
      return;
    }
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed) || parsed < 0) return;
    onSave(parsed);
  }

  return (
    <div className="space-y-1.5">
      <label htmlFor={inputId} className="text-xs font-medium">
        Per-conversation cap
      </label>
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <span
            aria-hidden
            className="pointer-events-none absolute inset-y-0 left-2.5 flex items-center text-xs text-muted-foreground"
          >
            $
          </span>
          <input
            id={inputId}
            type="number"
            inputMode="decimal"
            min={0}
            step="0.01"
            value={draft}
            placeholder="Inherit"
            onChange={(event) => setDraft(event.currentTarget.value)}
            data-testid="project-cap-input"
            className="h-9 w-full rounded-xl border border-border/70 bg-background/70 pl-6 pr-3 text-sm tabular-nums text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25"
          />
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={save}
          data-testid="project-cap-save"
        >
          Save
        </Button>
      </div>
      <p className="text-xs leading-snug text-muted-foreground">
        Overrides your per-conversation cap for this project&apos;s chats. Empty
        inherits your preference.
      </p>
    </div>
  );
}

function UsageDetails({
  usage,
  anonymous,
  onSaveBudget,
  perConversationBudgetUsd,
  onSavePerConversationBudget,
}: {
  usage: UsageBudget;
  anonymous: boolean;
  onSaveBudget: (value: number | null) => void;
  perConversationBudgetUsd: number | null;
  onSavePerConversationBudget: (value: number | null) => void;
}): JSX.Element {
  if (usage.isByok) {
    return (
      <div className="glass-clear space-y-2 rounded-2xl px-3.5 py-3">
        <div className="flex items-start gap-3">
          <Key
            aria-hidden
            className="mt-0.5 size-4 shrink-0 text-byok-indicator-foreground"
          />
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-medium">Bring your own key</p>
              <UsageMeter usage={usage} />
            </div>
            <p className="text-xs leading-snug text-muted-foreground">
              Model token charges bill to your provider key. Platform credits
              remain available if you remove the key.
            </p>
            <p className="text-xs text-muted-foreground">
              Credit balance:{" "}
              <span className="font-mono tabular-nums text-foreground">
                {formatUsd(usage.creditBalanceUsd)}
              </span>
            </p>
            <div className="pt-1">
              <SpendDialog />
            </div>
          </div>
        </div>
      </div>
    );
  }

  const budget = getUsagePresentation(usage);
  const isExhausted = budget.tone === "exhausted";
  const isNearLimit = budget.tone === "warning" || budget.tone === "critical";
  const helper = isExhausted
    ? anonymous
      ? "Usage limit reached. Sign in and add a key below to keep using supported providers, or wait for the next period."
      : "Usage limit reached. Add a key below to keep using supported providers, or wait for the next period."
    : isNearLimit
      ? anonymous
        ? "You're close to the cap. Sign in to bring your own key and keep model charges off platform credits."
        : "You're close to the cap. Bring your own key below to keep model charges off platform credits."
      : "Platform-key requests count toward this monthly cap.";

  return (
    <div
      className={cn(
        "glass-clear space-y-3 rounded-2xl px-3.5 py-3",
        isExhausted && "border-destructive/30",
        isNearLimit && !isExhausted && "border-warning-foreground/25",
      )}
    >
      <div className="flex items-start gap-3">
        <Gauge
          aria-hidden
          className={cn(
            "mt-0.5 size-4 shrink-0",
            isExhausted
              ? "text-destructive"
              : isNearLimit
                ? "text-warning"
                : "text-muted-foreground",
          )}
        />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium">Platform credits</p>
            <UsageMeter usage={usage} />
          </div>
          <p className="text-xs leading-snug text-muted-foreground">
            {helper}
          </p>
        </div>
      </div>
      <dl className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <dt className="text-muted-foreground">Used</dt>
          <dd className="mt-0.5 font-mono tabular-nums">
            {budget.used.toLocaleString()}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Remaining</dt>
          <dd
            className={cn(
              "mt-0.5 font-mono tabular-nums",
              isExhausted
                ? "text-destructive"
                : isNearLimit
                  ? "text-warning"
                  : "text-foreground",
            )}
          >
            {budget.remaining.toLocaleString()}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Limit</dt>
          <dd className="mt-0.5 font-mono tabular-nums">
            {budget.limit.toLocaleString()}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Period</dt>
          <dd className="mt-0.5">{usage.periodLabel}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Spend</dt>
          <dd className="mt-0.5 font-mono tabular-nums">
            {formatUsd(usage.monthlySpendUsd)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Credits</dt>
          <dd className="mt-0.5 font-mono tabular-nums">
            {formatUsd(usage.creditBalanceUsd)}
          </dd>
        </div>
      </dl>
      {usage.recentLedgerEntries && usage.recentLedgerEntries.length > 0 ? (
        <div className="space-y-1 border-t border-border/50 pt-2 text-xs">
          {usage.recentLedgerEntries.slice(0, 3).map((entry) => (
            <div key={entry.id} className="flex items-center justify-between gap-3">
              <span className="min-w-0 truncate text-muted-foreground">
                {entry.description ?? ledgerEntryLabel(entry.entryType)}
              </span>
              <span
                className={cn(
                  "shrink-0 font-mono tabular-nums",
                  entry.amountUsd < 0 ? "text-muted-foreground" : "text-foreground",
                )}
              >
                {formatUsd(entry.amountUsd)}
              </span>
            </div>
          ))}
        </div>
      ) : null}
      <BudgetEditor usage={usage} onSaveBudget={onSaveBudget} />
      <PerConversationBudgetEditor
        value={perConversationBudgetUsd}
        onSave={onSavePerConversationBudget}
      />
      <div className="border-t border-border/50 pt-3">
        <SpendDialog />
      </div>
    </div>
  );
}

// Settings panel (PRD 06 §5.7 / PRD 05). Privacy-first copy + defaults:
// training opt-in is framed as off-by-default and never assumed.
export function SettingsDialog({
  open,
  onOpenChange,
  preferences,
  onPreferencesChange,
  account,
  onAccountChange,
  usage,
  onSaveBudget,
  onSignOut,
  onRequestSignIn,
  onExportData,
  onDeleteAccount,
  onOpenActivity,
  onOpenMemory,
  onOpenTemplates,
  onOpenModelDirectory,
  projects = [],
  onUpdateProject,
}: SettingsDialogProps): JSX.Element {
  const sendOnEnterId = useId();
  const autoExpandId = useId();
  const customInstructionsId = useId();
  const temporaryId = useId();
  const trainingId = useId();
  const telemetryId = useId();
  const anonymous = isAnonymousAccount(account);
  const billing = account.billing ?? {
    planId: account.planLabel === "Pro" ? "pro" : "free",
    planLabel: account.planLabel,
    proEnabled: account.planLabel === "Pro",
    billingProvider: null,
    checkoutAvailable: false,
    proCheckoutAvailable: false,
    creditCheckoutAvailable: false,
    portalAvailable: false,
    creditBalanceUsd: usage.creditBalanceUsd ?? 0,
  };
  const proCheckoutAvailable =
    billing.proCheckoutAvailable ?? billing.checkoutAvailable;
  const creditCheckoutAvailable =
    billing.creditCheckoutAvailable ?? billing.checkoutAvailable;
  const [billingBusy, setBillingBusy] = useState<
    "pro" | "credits" | "portal" | null
  >(null);
  const [billingError, setBillingError] = useState<string | null>(null);
  const [customInstructionsDraft, setCustomInstructionsDraft] = useState(
    preferences.customInstructions,
  );

  function mergePreferenceDraft(
    patch: Partial<UserPreferences> = {},
  ): UserPreferences {
    return {
      ...preferences,
      customInstructions: customInstructionsDraft,
      ...patch,
    };
  }

  function commitCustomInstructions(): void {
    if (customInstructionsDraft === preferences.customInstructions) return;
    onPreferencesChange(mergePreferenceDraft());
  }

  async function openCheckout(kind: BillingCheckoutKind): Promise<void> {
    const busy = kind === "pro_subscription" ? "pro" : "credits";
    setBillingBusy(busy);
    setBillingError(null);
    try {
      const session = await createBillingCheckout({ kind });
      window.location.assign(session.url);
    } catch {
      setBillingError("Billing could not be started.");
      setBillingBusy(null);
    }
  }

  async function openPortal(): Promise<void> {
    setBillingBusy("portal");
    setBillingError(null);
    try {
      const session = await createBillingPortal();
      window.location.assign(session.url);
    } catch {
      setBillingError("Billing management is not available yet.");
      setBillingBusy(null);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) commitCustomInstructions();
        onOpenChange(nextOpen);
      }}
    >
      {/* The base DialogContent now provides the mobile bottom-sheet shell
          (full-width, bottom-pinned, rounded top, grabber, home-indicator-safe
          bottom padding, swipe-to-dismiss) and reverts to the centered modal at
          sm:. We keep the 80dvh cap here so the glass surface breathes a touch
          more than the default 90dvh on the settings panel. */}
      <DialogContent className="max-h-[80dvh] sm:max-h-none">
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>
            Account, appearance, and privacy preferences.
          </DialogDescription>
        </DialogHeader>

        <div className="-mr-2 max-h-[60dvh] space-y-6 overflow-y-auto pr-2 sm:max-h-[70dvh]">
          {/* Account */}
          <section className="space-y-3">
            <SectionHeading>Account</SectionHeading>
            <div className="flex items-center gap-3">
              <span
                aria-hidden
                className="flex size-10 shrink-0 items-center justify-center rounded-full bg-secondary text-sm font-semibold text-secondary-foreground"
              >
                {initials(account.name)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-medium">{account.name}</p>
                  <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground">
                    {billing.planLabel}
                  </span>
                </div>
                <p className="truncate text-xs text-muted-foreground">
                  {account.email}
                </p>
              </div>
            </div>

            <UsageDetails
              usage={usage}
              anonymous={anonymous}
              onSaveBudget={onSaveBudget}
              perConversationBudgetUsd={preferences.perConversationBudgetUsd}
              onSavePerConversationBudget={(value) =>
                onPreferencesChange(
                  mergePreferenceDraft({ perConversationBudgetUsd: value }),
                )
              }
            />

            <div className="flex flex-wrap gap-2">
              {anonymous ? (
                // Guests can't check out; rather than a dead, disabled control
                // route them straight to the auth dialog (closes settings).
                <Button
                  type="button"
                  size="sm"
                  onClick={onRequestSignIn}
                >
                  <CreditCard aria-hidden className="size-3.5" />
                  <span>Sign in to upgrade</span>
                </Button>
              ) : (
                <>
                  {!billing.proEnabled ? (
                    <Button
                      type="button"
                      size="sm"
                      disabled={!proCheckoutAvailable || billingBusy !== null}
                      onClick={() => void openCheckout("pro_subscription")}
                    >
                      <CreditCard aria-hidden className="size-3.5" />
                      <span>
                        {billingBusy === "pro" ? "Opening..." : "Upgrade to Pro"}
                      </span>
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={!creditCheckoutAvailable || billingBusy !== null}
                    onClick={() => void openCheckout("credit_purchase")}
                  >
                    <Receipt aria-hidden className="size-3.5" />
                    <span>
                      {billingBusy === "credits" ? "Opening..." : "Buy credits"}
                    </span>
                  </Button>
                  {billing.portalAvailable ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={billingBusy !== null}
                      onClick={() => void openPortal()}
                    >
                      <CreditCard aria-hidden className="size-3.5" />
                      <span>
                        {billingBusy === "portal"
                          ? "Opening..."
                          : "Manage billing"}
                      </span>
                    </Button>
                  ) : null}
                </>
              )}
            </div>
            {billingError ? (
              <p className="text-xs text-destructive">{billingError}</p>
            ) : null}

            {!anonymous ? (
              <div className="pt-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={onSignOut}
                  className="-ml-2 rounded-full text-muted-foreground hover:text-foreground"
                >
                  <LogOut aria-hidden className="size-3.5" />
                  <span>Sign out</span>
                </Button>
              </div>
            ) : null}
          </section>

          <Separator />

          {/* Bring your own key — PRD 04 §5.2 / PRD 02 FR-6. Anonymous sessions
              are gated inside ByokForm with a sign-in CTA. */}
          <section className="space-y-3">
            <SectionHeading>Bring your own key</SectionHeading>
            <ByokForm
              account={account}
              preferences={preferences}
              onAccountChange={onAccountChange}
              onRequestSignIn={onRequestSignIn}
            />
          </section>

          <Separator />

          {/* Appearance */}
          <section className="space-y-3">
            <SectionHeading>Appearance</SectionHeading>
            <SettingRow
              label="Theme"
              helper="Match your system, or pick light or dark."
              control={<ThemeToggle />}
            />
          </section>

          <Separator />

          {/* Chat */}
          <section className="space-y-4">
            <SectionHeading>Chat</SectionHeading>
            <SettingRow
              label="Default model"
              helper="The tier new chats start with."
              control={
                <TierPicker
                  tiers={MODEL_TIERS}
                  selectedId={preferences.defaultTierId}
                  onSelect={(id) =>
                    onPreferencesChange(mergePreferenceDraft({ defaultTierId: id }))
                  }
                />
              }
            />
            <SettingRow
              label="Models & data policies"
              helper="Compare each provider's data handling, capabilities, and prices."
              control={
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  data-testid="open-model-directory-button"
                  onClick={onOpenModelDirectory}
                >
                  Browse
                </Button>
              }
            />
            <SettingRow
              label="Send on Enter"
              helper="When off, press ⌘/Ctrl+Enter to send."
              htmlFor={sendOnEnterId}
              control={
                <Switch
                  id={sendOnEnterId}
                  checked={preferences.sendOnEnter}
                  onCheckedChange={(checked) =>
                    onPreferencesChange(mergePreferenceDraft({ sendOnEnter: checked }))
                  }
                />
              }
            />
            <SettingRow
              label="Auto-expand reasoning"
              helper="Show the model's thinking by default."
              htmlFor={autoExpandId}
              control={
                <Switch
                  id={autoExpandId}
                  checked={preferences.autoExpandReasoning}
                  onCheckedChange={(checked) =>
                    onPreferencesChange(
                      mergePreferenceDraft({ autoExpandReasoning: checked }),
                    )
                  }
                />
              }
            />
            <div className="space-y-2">
              <label
                htmlFor={customInstructionsId}
                className="text-sm font-medium"
              >
                Custom instructions
              </label>
              <textarea
                id={customInstructionsId}
                value={customInstructionsDraft}
                maxLength={CUSTOM_INSTRUCTIONS_LIMIT}
                rows={5}
                onChange={(event) =>
                  setCustomInstructionsDraft(event.currentTarget.value)
                }
                onBlur={commitCustomInstructions}
                className="min-h-28 w-full resize-y rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-sm leading-5 text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25"
                placeholder="Preferred tone, formatting, and context for future chats"
              />
              <div className="text-right font-mono text-[11px] tabular-nums text-muted-foreground">
                {customInstructionsDraft.length}/{CUSTOM_INSTRUCTIONS_LIMIT}
              </div>
            </div>
          </section>

          {/* Projects/Spaces (D20). Per-project scoping of the wedge controls.
              Only rendered when an updater is wired (the parent owns the PATCH);
              the panel itself handles the empty-project case with a hint. */}
          {onUpdateProject ? (
            <>
              <Separator />
              <section className="space-y-4" data-testid="settings-projects-section">
                <SectionHeading>Projects</SectionHeading>
                <ProjectSettingsPanel
                  projects={projects}
                  onUpdate={onUpdateProject}
                />
              </section>
            </>
          ) : null}

          <Separator />

          {/* Privacy & data */}
          <section className="space-y-4">
            <SectionHeading>Privacy &amp; data</SectionHeading>
            <SettingRow
              label="Temporary chats by default"
              helper="New chats won't be saved to history."
              htmlFor={temporaryId}
              control={
                <Switch
                  id={temporaryId}
                  checked={preferences.temporaryByDefault}
                  onCheckedChange={(checked) =>
                    onPreferencesChange(
                      mergePreferenceDraft({ temporaryByDefault: checked }),
                    )
                  }
                />
              }
            />
            <SettingRow
              label="Saved chat retention"
              helper="Temporary chats are still never saved."
              control={
                <RetentionPicker
                  value={preferences.retentionDays}
                  onChange={(retentionDays) =>
                    onPreferencesChange(mergePreferenceDraft({ retentionDays }))
                  }
                />
              }
            />
            <SettingRow
              label="Help improve Olune"
              helper="Your conversations are never used to train models unless this is on."
              htmlFor={trainingId}
              control={
                <Switch
                  id={trainingId}
                  checked={preferences.trainingOptIn}
                  onCheckedChange={(checked) =>
                    onPreferencesChange(mergePreferenceDraft({ trainingOptIn: checked }))
                  }
                />
              }
            />
            <SettingRow
              label="Product telemetry"
              helper="Share content-free usage events that help improve launch reliability."
              htmlFor={telemetryId}
              control={
                <Switch
                  id={telemetryId}
                  checked={preferences.telemetryEnabled}
                  onCheckedChange={(checked) =>
                    onPreferencesChange(mergePreferenceDraft({ telemetryEnabled: checked }))
                  }
                />
              }
            />
          </section>

          <Separator />

          {/* Your data — portability + erasure. Both endpoints accept anonymous
              callers (guests accrue data too), so these rows are ungated. The
              parent owns the download / confirm-dialog / reset side effects. */}
          <section className="space-y-4">
            <SectionHeading>Your data</SectionHeading>
            <SettingRow
              label="Memory"
              helper={
                preferences.memoryEnabled
                  ? "On — review and edit the facts the assistant remembers about you."
                  : "Off — opt in and manage the facts the assistant can remember."
              }
              control={
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  data-testid="open-memory-button"
                  onClick={onOpenMemory}
                >
                  Manage
                </Button>
              }
            />
            <SettingRow
              label="Prompt templates"
              helper="Create and edit reusable prompts you can drop into the composer."
              control={
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  data-testid="open-templates-button"
                  onClick={onOpenTemplates}
                >
                  Manage
                </Button>
              }
            />
            <SettingRow
              label="Activity & data access"
              helper="See sensitive account actions and where your messages were processed."
              control={
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  data-testid="open-activity-button"
                  onClick={onOpenActivity}
                >
                  View
                </Button>
              }
            />
            <SettingRow
              label="Export your data"
              helper="Download your account, preferences, and conversations as JSON."
              control={
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  data-testid="export-data-button"
                  onClick={onExportData}
                >
                  Export
                </Button>
              }
            />
            <SettingRow
              label="Delete account"
              helper="Permanently delete your account and all conversations. This can't be undone."
              control={
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  data-testid="delete-account-button"
                  onClick={onDeleteAccount}
                >
                  Delete account
                </Button>
              }
            />
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
