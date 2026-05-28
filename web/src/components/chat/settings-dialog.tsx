"use client";

import { useId, type JSX, type ReactNode } from "react";
import { Key } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
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
  usage: UsageBudget;
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
  usage,
}: SettingsDialogProps): JSX.Element {
  const sendOnEnterId = useId();
  const autoExpandId = useId();
  const temporaryId = useId();
  const trainingId = useId();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Mobile: bottom-anchored sheet (full width, pinned bottom, rounded top,
          capped at 80dvh to let the glass surface breathe). Reverts to the
          shared centered modal at sm: by restoring DialogContent's default
          top/left + translate + radius. */}
      <DialogContent className="top-auto bottom-0 left-0 max-h-[80dvh] max-w-full translate-x-0 translate-y-0 rounded-t-3xl rounded-b-none sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:max-h-none sm:max-w-lg sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-3xl">
        <div
          aria-hidden
          className="mx-auto -mt-2 h-1 w-10 rounded-full bg-foreground/15 sm:hidden"
        />
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>
            Manage your account, appearance, and privacy.
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

            {account.byokEnabled ? (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Key aria-hidden className="size-3.5 shrink-0" />
                <span>
                  Billed to your key
                  {account.byokMaskedKey ? (
                    <>
                      {" "}
                      <span className="font-mono text-foreground">
                        {account.byokMaskedKey}
                      </span>
                    </>
                  ) : null}
                </span>
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                Using platform credits — add your own API key to bill providers
                directly.
              </p>
            )}
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
              helper="Off uses ⌘/Ctrl+Enter to send"
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
              helper="Show the model's thinking by default"
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
              helper="New chats won't be saved to history"
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
              label="Improve the model for everyone"
              helper="Off by default. Your conversations are never used to train models unless you turn this on."
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
