"use client";

import { useId, useState, type JSX } from "react";
import { Key, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { showToast } from "@/components/ui/toast";
import { deleteByok, putByok } from "@/lib/apiClient";
import { ApiError, ApiNetworkError } from "@/lib/apiClient";
import { isAnonymousAccount, type AccountInfo } from "@/lib/types";

// PRD 04 §5.2 — surface providers as user-facing labels; the canonical id list
// is not yet exported from `lib/`, so the form hardcodes the two MVP providers
// (Anthropic, OpenAI) with the same ids the gateway accepts. Replace with a
// registry import once one lands.
const PROVIDERS: ReadonlyArray<{ id: string; label: string; placeholder: string }> = [
  { id: "anthropic", label: "Anthropic", placeholder: "sk-ant-..." },
  { id: "openai", label: "OpenAI", placeholder: "sk-..." },
];

export interface ByokFormProps {
  account: AccountInfo;
  onAccountChange: (next: AccountInfo) => void;
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
  const currentProvider = PROVIDERS.find((p) => p.id === provider) ?? PROVIDERS[0]!;
  const hasKeyForProvider = account.byokEnabled;

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
      onAccountChange(next);
      reset();
      showToast({
        severity: "success",
        title: "Key saved",
        body: `${currentProvider.label} requests will bill to your key.`,
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
      onAccountChange(next);
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

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
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
          className="block h-9 w-full rounded-2xl bg-muted/50 px-3 text-sm text-foreground outline-none focus-visible:shadow-[var(--focus-ring)]"
        >
          {PROVIDERS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </div>

      {hasKeyForProvider && !editing ? (
        <div className="space-y-2">
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

      {!hasKeyForProvider || editing ? (
        <div className="space-y-2">
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
              className="block h-9 w-full rounded-2xl bg-muted/50 pl-3 pr-9 font-mono text-sm text-foreground outline-none placeholder:font-sans placeholder:text-muted-foreground focus-visible:shadow-[var(--focus-ring)]"
            />
            {apiKey.length > 0 ? (
              <button
                type="button"
                onClick={() => setApiKey("")}
                aria-label="Clear API key"
                className="absolute right-1.5 top-1/2 inline-flex size-6 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
              >
                <X aria-hidden className="size-3.5" />
              </button>
            ) : null}
          </div>
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
