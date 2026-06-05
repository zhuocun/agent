"use client";

import { useEffect, useId, useState, type JSX } from "react";
import { Brain, Pencil, Plus, Trash2, X } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import {
  createMemoryFact,
  deleteMemoryFact,
  fetchMemoryFacts,
  updateMemoryFact,
} from "@/lib/apiClient";
import type { MemoryFact } from "@/lib/types";

const FACT_MAX = 2000;

export interface MemoryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // The current opt-in state + a persister wired by the parent through the
  // existing preferences flow (so the toggle round-trips to the BE).
  memoryEnabled: boolean;
  onMemoryEnabledChange: (next: boolean) => void;
}

// The editable, attributed fact ledger (D19) — the glass-box differentiator
// made operable. Lists/adds/edits/deletes the caller's saved facts and exposes
// the opt-in toggle. All endpoints are caller-scoped + anonymous-allowed.
export function MemoryDialog({
  open,
  onOpenChange,
  memoryEnabled,
  onMemoryEnabledChange,
}: MemoryDialogProps): JSX.Element {
  const toggleId = useId();
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  // `loaded` flips true after the first fetch settles (success OR error) so the
  // loading state is derived without a synchronous setState in the effect body
  // (mirrors ActivityDialog; the repo lints react-hooks/set-state-in-effect).
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [adding, setAdding] = useState(false);
  // The fact currently being edited inline, plus its working text.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let cancelled = false;
    void (async () => {
      try {
        const rows = await fetchMemoryFacts(controller.signal);
        if (cancelled) return;
        setFacts(rows);
        setLoaded(true);
      } catch {
        if (cancelled) return;
        setError("Couldn't load your memory. Please try again.");
        setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [open]);

  const loading = open && !loaded && error === null;

  const handleOpenChange = (next: boolean): void => {
    if (!next) {
      // Reset transient state so a re-open refetches from a clean slate.
      setFacts([]);
      setLoaded(false);
      setError(null);
      setDraft("");
      setAdding(false);
      setEditingId(null);
      setEditingText("");
      setBusyId(null);
    }
    onOpenChange(next);
  };

  const handleAdd = async (): Promise<void> => {
    const content = draft.trim();
    if (!content || adding) return;
    setAdding(true);
    setError(null);
    try {
      const created = await createMemoryFact(content);
      // Newest-first, matching the BE list order.
      setFacts((prev) => [created, ...prev]);
      setDraft("");
    } catch {
      setError("Couldn't save that fact. Please try again.");
    } finally {
      setAdding(false);
    }
  };

  const startEdit = (fact: MemoryFact): void => {
    setEditingId(fact.id);
    setEditingText(fact.content);
  };

  const cancelEdit = (): void => {
    setEditingId(null);
    setEditingText("");
  };

  const handleSaveEdit = async (id: string): Promise<void> => {
    const content = editingText.trim();
    if (!content || busyId) return;
    setBusyId(id);
    setError(null);
    try {
      const updated = await updateMemoryFact(id, content);
      setFacts((prev) => prev.map((f) => (f.id === id ? updated : f)));
      cancelEdit();
    } catch {
      setError("Couldn't update that fact. Please try again.");
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (id: string): Promise<void> => {
    if (busyId) return;
    setBusyId(id);
    setError(null);
    try {
      await deleteMemoryFact(id);
      setFacts((prev) => prev.filter((f) => f.id !== id));
    } catch {
      setError("Couldn't delete that fact. Please try again.");
    } finally {
      setBusyId(null);
    }
  };

  const showEmpty = !loading && !error && facts.length === 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-h-[80dvh] sm:max-h-none"
        data-testid="memory-dialog"
      >
        <DialogHeader>
          <DialogTitle>Memory</DialogTitle>
          <DialogDescription>
            The facts the assistant can remember about you. Add, edit, or remove
            them anytime — they&apos;re only used when memory is on, and never in
            temporary chats.
          </DialogDescription>
        </DialogHeader>

        <div className="-mr-2 max-h-[60dvh] space-y-5 overflow-y-auto pr-2 sm:max-h-[70dvh]">
          {/* Opt-in toggle */}
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <label htmlFor={toggleId} className="text-sm font-medium">
                Use memory in chats
              </label>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Off by default. When on, your saved facts are added to new,
                non-temporary chats.
              </p>
            </div>
            <div className="shrink-0">
              <Switch
                id={toggleId}
                checked={memoryEnabled}
                onCheckedChange={onMemoryEnabledChange}
                data-testid="memory-enabled-switch"
              />
            </div>
          </div>

          {/* Add a fact */}
          <div className="space-y-2">
            <label htmlFor="memory-add-input" className="text-sm font-medium">
              Add a fact
            </label>
            <textarea
              id="memory-add-input"
              value={draft}
              maxLength={FACT_MAX}
              rows={2}
              onChange={(event) => setDraft(event.currentTarget.value)}
              className="min-h-16 w-full resize-y rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-sm leading-5 text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25"
              placeholder="e.g. I prefer concise answers and metric units."
              data-testid="memory-add-input"
            />
            <div className="flex justify-end">
              <Button
                type="button"
                size="sm"
                onClick={() => void handleAdd()}
                disabled={adding || draft.trim().length === 0}
                data-testid="memory-add-button"
              >
                <Plus aria-hidden className="size-3.5" />
                <span>Add fact</span>
              </Button>
            </div>
          </div>

          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}

          {/* The ledger */}
          <section className="space-y-2">
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : showEmpty ? (
              <p className="text-sm text-muted-foreground">
                No saved facts yet. Add one above, and it&apos;ll appear here.
              </p>
            ) : (
              <ul className="space-y-2" data-testid="memory-list">
                {facts.map((fact) => (
                  <li
                    key={fact.id}
                    className="glass-clear space-y-2 rounded-2xl px-3.5 py-3"
                    data-testid="memory-fact"
                  >
                    {editingId === fact.id ? (
                      <>
                        <textarea
                          value={editingText}
                          maxLength={FACT_MAX}
                          rows={2}
                          onChange={(event) =>
                            setEditingText(event.currentTarget.value)
                          }
                          className="min-h-16 w-full resize-y rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-sm leading-5 text-foreground outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/25"
                          data-testid="memory-edit-input"
                        />
                        <div className="flex justify-end gap-2">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={cancelEdit}
                            data-testid="memory-edit-cancel"
                          >
                            <X aria-hidden className="size-3.5" />
                            <span>Cancel</span>
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            onClick={() => void handleSaveEdit(fact.id)}
                            disabled={
                              busyId === fact.id ||
                              editingText.trim().length === 0
                            }
                            data-testid="memory-edit-save"
                          >
                            Save
                          </Button>
                        </div>
                      </>
                    ) : (
                      <div className="flex items-start gap-3">
                        <Brain
                          aria-hidden
                          className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                        />
                        <p className="min-w-0 flex-1 text-sm break-words whitespace-pre-wrap">
                          {fact.content}
                        </p>
                        <div className="flex shrink-0 items-center gap-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            aria-label="Edit fact"
                            onClick={() => startEdit(fact)}
                            disabled={busyId === fact.id}
                            data-testid="memory-edit-button"
                          >
                            <Pencil aria-hidden className="size-3.5" />
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            aria-label="Delete fact"
                            onClick={() => void handleDelete(fact.id)}
                            disabled={busyId === fact.id}
                            data-testid="memory-delete-button"
                          >
                            <Trash2 aria-hidden className="size-3.5" />
                          </Button>
                        </div>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
