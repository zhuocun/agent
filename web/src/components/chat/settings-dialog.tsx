"use client";

import { useId, type JSX, type ReactNode } from "react";
import { LogOut } from "lucide-react";

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
import { UsageMeter } from "@/components/chat/usage-meter";
import { MODEL_TIERS } from "@/lib/model-tiers";
import type { AccountInfo, UsageBudget, UserPreferences } from "@/lib/types";

export interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preferences: UserPreferences;
  onPreferencesChange: (next: UserPreferences) => void;
  account: AccountInfo;
  onAccountChange: (next: AccountInfo) => void;
  usage: UsageBudget;
  onSignOut: () => void;
}

// Worker C audit gap: same anonymous discriminator the BYOK form uses; kept
// local so the dialog can gate the sign-out row without leaking a typed field
// that the wire schema hasn't shipped yet.
function isAnonymousAccount(account: AccountInfo): boolean {
  const flagged = (account as { isAnonymous?: unknown }).isAnonymous;
  if (typeof flagged === "boolean") return flagged;
  return account.email.trim().length === 0;
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
  onSignOut,
}: SettingsDialogProps): JSX.Element {
  const sendOnEnterId = useId();
  const autoExpandId = useId();
  const temporaryId = useId();
  const trainingId = useId();
  const anonymous = isAnonymousAccount(account);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
                    {account.planLabel}
                  </span>
                </div>
                <p className="truncate text-xs text-muted-foreground">
                  {account.email}
                </p>
              </div>
            </div>

            <UsageMeter usage={usage} />

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
            <ByokForm account={account} onAccountChange={onAccountChange} />
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
                    onPreferencesChange({ ...preferences, defaultTierId: id })
                  }
                />
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
                    onPreferencesChange({ ...preferences, sendOnEnter: checked })
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
                    onPreferencesChange({
                      ...preferences,
                      autoExpandReasoning: checked,
                    })
                  }
                />
              }
            />
          </section>

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
                    onPreferencesChange({
                      ...preferences,
                      temporaryByDefault: checked,
                    })
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
                    onPreferencesChange({ ...preferences, trainingOptIn: checked })
                  }
                />
              }
            />
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
