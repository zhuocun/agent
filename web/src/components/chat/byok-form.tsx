"use client";

import { useId, useMemo, useState, type JSX } from "react";
import { Key, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { showToast } from "@/components/ui/toast";
import { deleteByok, putByok } from "@/lib/apiClient";
import { ApiError, ApiNetworkError } from "@/lib/apiClient";
import {
  isAnonymousAccount,
  type AccountInfo,
  type ByokKeyStatus,
} from "@/lib/types";

// PRD 04 §5.2 — surface providers as user-facing labels; the canonical id list
// is not yet exported from `lib/`, so the form hardcodes the MVP providers with
// the same ids the gateway accepts. Replace with a registry import once one
// lands.
type ProviderChoice = { id: string; label: string; placeholder: string };

const PROVIDERS: ReadonlyArray<ProviderChoice> = [
  { id: "deepseek", label: "DeepSeek", placeholder: "sk-deepseek-..." },
  { id: "anthropic", label: "Anthropic", placeholder: "sk-ant-..." },
  { id: "openai", label: "OpenAI", placeholder: "sk-..." },
];

function providerChoicesForAccount(account: AccountInfo): ProviderChoice[] {
  const choices = new Map<string, ProviderChoice>();
  for (const provider of PROVIDERS) choices.set(provider.id, provider);
  for (const key of account.byokKeys ?? []) {
    if (!choices.has(key.providerId)) {
      choices.set(key.providerId, {
        id: key.providerId,
        label: key.providerLabel,
        placeholder: "API key",
      });
    }
  }
  return Array.from(choices.values());
}

function keyStatusForProvider(
  account: AccountInfo,
  providerId: string,
  providerLabel: string,
): ByokKeyStatus | undefined {
  if (account.byokKeys) {
    return account.byokKeys.find((key) => key.providerId === providerId);
  }
  if (!account.byokEnabled) return undefined;
  return {
    providerId,
    providerLabel,
    maskedKey: account.byokMaskedKey ?? "",
    usable: true,
  };
}

export interface ByokFormProps {
  account: AccountInfo;
  onAccountChange: (next: AccountInfo) => void | Promise<void>;
}

export function ByokForm({ account, onAccountChange }: ByokFormProps): JSX.Element {
  const providerId = useId();
  const keyId = useId();
  const [provider, setProvider] = useState<string>(PROVIDERS[0]!.id);
  const [apiKey, setApiKey] = useState("");
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);

  const anonymous = isAnonymousAccount(account);
  const providerChoices = useMemo(
    () => providerChoicesForAccount(account),
    [account],
  );
  const currentProvider =
    providerChoices.find((p) => p.id === provider) ??
    providerChoices[0] ??
    PROVIDERS[0]!;
  const currentKey = keyStatusForProvider(
    account,
    currentProvider.id,
    currentProvider.label,
  );
  const hasKeyForProvider = currentKey !== undefined;
  const keyUsable = currentKey?.usable !== false;

  const reset = () => {
    setApiKey("");
    setEditing(false);
    setConfirmingDelete(false);
  };

  const handleReportError = (cause: unknown, fallbackTitle: string) => {
    const title =
      cause instanceof ApiError ? cause.title : fallbackTitle;
    const body =
      cause instanceof ApiError
        ? cause.body
        : cause instanceof ApiNetworkError
          ? cause.message
          : undefined;
    showToast({ severity: "error", title, body });
  };

  const handleSave = async () => {
    const trimmed = apiKey.trim();
    if (trimmed.length === 0) return;
    setSaving(true);
    try {
      const next = await putByok({ provider, apiKey: trimmed });
      await onAccountChange(next);
      reset();
      showToast({
        severity: "success",
        title: "Key saved",
        body: `${currentProvider.label} requests can bill to your key when that provider is selected.`,
      });
    } catch (cause) {
      handleReportError(cause, "Couldn't save key");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setRemoving(true);
    try {
      const next = await deleteByok(provider);
      await onAccountChange(next);
      reset();
      showToast({
        severity: "success",
        title: "Key removed",
        body: `${currentProvider.label} requests revert to platform credits.`,
      });
    } catch (cause) {
      handleReportError(cause, "Couldn't remove key");
    } finally {
      setRemoving(false);
    }
  };

  if (anonymous) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-muted-foreground">
          Sign in to bring your own API key. Guest sessions can&apos;t store
          provider credentials.
        </p>
      </div>
    );
  }

  // The key-entry row shares the inset-grouped card with the provider row
  // (mirrors the welcome-list pattern), so compute its visibility once: shown
  // when there's no stored key, or when the user is explicitly replacing one.
  const showKeyRow = !hasKeyForProvider || editing;

  return (
    <div className="space-y-3">
      {/* iOS inset-grouped card: Provider + API-key as two rows inside one
          `glass-clear` surface with a hairline `border-t` separator between
          them (none above the first row). `overflow-hidden rounded-2xl` clips
          the field corners to the card. Labels sit above each field within the
          row; the controls themselves are bare (no per-field surface) so the
          card is the only material — same grouping language as the welcome
          list. */}
      <div className="glass-clear overflow-hidden rounded-2xl">
        <div className="space-y-1.5 px-3.5 py-3">
          <label htmlFor={providerId} className="text-sm font-medium">
            Provider
          </label>
          <select
            id={providerId}
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value);
              reset();
            }}
            // h-11 = 44pt, the iOS minimum touch target (was h-9/36px). The
            // field is transparent (`bg-transparent`) because the card behind
            // it is the surface now.
            className="block h-11 w-full rounded-xl bg-transparent px-2.5 text-sm text-foreground outline-none focus-visible:shadow-[var(--focus-ring)]"
          >
            {providerChoices.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>

        {showKeyRow ? (
          <div className="space-y-1.5 border-t border-border/60 px-3.5 py-3">
            <label htmlFor={keyId} className="text-sm font-medium">
              API key
            </label>
            <div className="relative">
              <input
                id={keyId}
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                autoComplete="off"
                autoCorrect="off"
                spellCheck={false}
                placeholder={currentProvider.placeholder}
                // h-11 = 44pt (was h-9). Transparent against the card surface;
                // right padding leaves room for the clear button. The password
                // hardening (autoComplete/autoCorrect/spellCheck off) is kept.
                className="block h-11 w-full rounded-xl bg-transparent pl-2.5 pr-10 font-mono text-sm text-foreground outline-none placeholder:font-sans placeholder:text-muted-foreground focus-visible:shadow-[var(--focus-ring)]"
              />
              {apiKey.length > 0 ? (
                <button
                  type="button"
                  onClick={() => setApiKey("")}
                  aria-label="Clear API key"
                  // Centered in the 44px row; the size-9 hit area keeps a
                  // comfortable target while the icon stays small.
                  className="absolute right-1 top-1/2 inline-flex size-9 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
                >
                  <X aria-hidden className="size-3.5" />
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>

      {hasKeyForProvider && !editing ? (
        <div className="space-y-2">
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Key aria-hidden className="size-3.5 shrink-0" />
            <span>
              {keyUsable
                ? `Billed to your ${currentProvider.label} key`
                : `${currentProvider.label} key saved but not currently usable`}
              {currentKey?.maskedKey ? (
                <>
                  {" "}
                  <span className="font-mono text-foreground">
                    {currentKey.maskedKey}
                  </span>
                </>
              ) : null}
            </span>
          </p>
          {confirmingDelete ? (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs text-muted-foreground">
                Remove this key? Future requests revert to platform credits.
              </p>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setConfirmingDelete(false)}
                disabled={removing}
                className="rounded-full"
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={handleDelete}
                disabled={removing}
                className="rounded-full"
              >
                {removing ? "Removing..." : "Remove key"}
              </Button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => setEditing(true)}
                className="rounded-full"
              >
                Replace key
              </Button>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={() => setConfirmingDelete(true)}
                className="rounded-full"
              >
                Remove key
              </Button>
            </div>
          )}
        </div>
      ) : null}

      {/* The key field itself now lives in the inset-grouped card above; what
          remains here is the help text and the Save/Cancel actions, gated on
          the same `showKeyRow` so they appear together with the field. */}
      {showKeyRow ? (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            Stored encrypted server-side; never sent to other providers.
          </p>
          <div className="flex flex-wrap gap-2">
            {editing ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={reset}
                disabled={saving}
                className="rounded-full"
              >
                Cancel
              </Button>
            ) : null}
            <Button
              type="button"
              size="sm"
              onClick={handleSave}
              disabled={saving || apiKey.trim().length === 0}
              className="rounded-full"
            >
              {saving ? "Saving..." : hasKeyForProvider ? "Save new key" : "Add key"}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
