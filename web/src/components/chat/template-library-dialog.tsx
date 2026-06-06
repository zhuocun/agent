"use client";

import { useEffect, useState, type JSX } from "react";
import { FileText, Pencil, Plus, Trash2, X } from "lucide-react";

import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  createPromptTemplate,
  deletePromptTemplate,
  fetchPromptTemplates,
  updatePromptTemplate,
} from "@/lib/apiClient";
import type { PromptTemplate } from "@/lib/types";

const TITLE_MAX = 200;
const BODY_MAX = 10000;
const DESCRIPTION_MAX = 500;

export interface TemplateLibraryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export interface TemplateLibraryBodyProps {
  // Drives the load lifecycle. When hosted in the Settings hub this is the "is
  // the Templates tab active" flag; standalone it mirrors dialog open.
  active: boolean;
}

// The prompt library (D23): user-authored, reusable templates. Lists / creates
// / edits / deletes the caller's templates. All endpoints are caller-scoped +
// anonymous-allowed. Selecting a template (from the composer picker) prefills
// the composer — this dialog is the editable store behind that affordance.
export function TemplateLibraryBody({
  active,
}: TemplateLibraryBodyProps): JSX.Element {
  const open = active;
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  // `loaded` flips true after the first fetch settles (success OR error) so the
  // loading state is derived without a synchronous setState in the effect body
  // (mirrors MemoryDialog; the repo lints react-hooks/set-state-in-effect).
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Working draft for the "add" form.
  const [draftTitle, setDraftTitle] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [adding, setAdding] = useState(false);
  // The template currently being edited inline, plus its working fields.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [editingBody, setEditingBody] = useState("");
  const [editingDescription, setEditingDescription] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let cancelled = false;
    void (async () => {
      try {
        const rows = await fetchPromptTemplates(controller.signal);
        if (cancelled) return;
        setTemplates(rows);
        setLoaded(true);
      } catch {
        if (cancelled) return;
        setError("Couldn't load your templates. Please try again.");
        setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [open]);

  const loading = open && !loaded && error === null;

  const handleAdd = async (): Promise<void> => {
    const title = draftTitle.trim();
    const body = draftBody.trim();
    if (!title || !body || adding) return;
    setAdding(true);
    setError(null);
    try {
      const created = await createPromptTemplate({
        title,
        body,
        description: draftDescription.trim() || null,
      });
      // Newest-first, matching the BE list order.
      setTemplates((prev) => [created, ...prev]);
      setDraftTitle("");
      setDraftBody("");
      setDraftDescription("");
    } catch {
      setError("Couldn't save that template. Please try again.");
    } finally {
      setAdding(false);
    }
  };

  const startEdit = (template: PromptTemplate): void => {
    setEditingId(template.id);
    setEditingTitle(template.title);
    setEditingBody(template.body);
    setEditingDescription(template.description ?? "");
  };

  const cancelEdit = (): void => {
    setEditingId(null);
    setEditingTitle("");
    setEditingBody("");
    setEditingDescription("");
  };

  const handleSaveEdit = async (id: string): Promise<void> => {
    const title = editingTitle.trim();
    const body = editingBody.trim();
    if (!title || !body || busyId) return;
    setBusyId(id);
    setError(null);
    try {
      const updated = await updatePromptTemplate(id, {
        title,
        body,
        description: editingDescription.trim() || null,
      });
      setTemplates((prev) => prev.map((t) => (t.id === id ? updated : t)));
      cancelEdit();
    } catch {
      setError("Couldn't update that template. Please try again.");
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (id: string): Promise<void> => {
    if (busyId) return;
    setBusyId(id);
    setError(null);
    try {
      await deletePromptTemplate(id);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
    } catch {
      setError("Couldn't delete that template. Please try again.");
    } finally {
      setBusyId(null);
    }
  };

  const showEmpty = !loading && !error && templates.length === 0;
  const canAdd =
    draftTitle.trim().length > 0 && draftBody.trim().length > 0 && !adding;

  return (
    <div data-testid="template-dialog">
      <div className="flex flex-col gap-1.5 text-center sm:text-left">
        <h2 className="text-lg leading-none font-semibold">Prompt templates</h2>
        <p className="text-sm text-muted-foreground">
          Reusable prompts you can drop into the composer. Use{" "}
          <code className="font-mono text-xs">{"{{placeholders}}"}</code> for the
          parts you fill in each time.
        </p>
      </div>

      <div className="-mr-2 mt-4 max-h-[60dvh] space-y-5 overflow-y-auto pr-2 sm:max-h-[70dvh]">
          {/* Add a template */}
          <div className="space-y-2">
            <label
              htmlFor="template-add-title"
              className="text-sm font-medium"
            >
              Add a template
            </label>
            <input
              id="template-add-title"
              value={draftTitle}
              maxLength={TITLE_MAX}
              onChange={(event) => setDraftTitle(event.currentTarget.value)}
              className="w-full rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-sm leading-5 text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25"
              placeholder="Title — e.g. Blog post outline"
              data-testid="template-add-title"
            />
            <textarea
              id="template-add-body"
              value={draftBody}
              maxLength={BODY_MAX}
              rows={3}
              onChange={(event) => setDraftBody(event.currentTarget.value)}
              className="min-h-20 w-full resize-y rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-sm leading-5 text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25"
              placeholder="Body — e.g. Write a blog post about {{topic}} for {{audience}}."
              data-testid="template-add-body"
            />
            <input
              id="template-add-description"
              value={draftDescription}
              maxLength={DESCRIPTION_MAX}
              onChange={(event) =>
                setDraftDescription(event.currentTarget.value)
              }
              className="w-full rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-sm leading-5 text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25"
              placeholder="Description (optional)"
              data-testid="template-add-description"
            />
            <div className="flex justify-end">
              <Button
                type="button"
                size="sm"
                onClick={() => void handleAdd()}
                disabled={!canAdd}
                data-testid="template-add-button"
              >
                <Plus aria-hidden className="size-3.5" />
                <span>Add template</span>
              </Button>
            </div>
          </div>

          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}

          {/* The library */}
          <section className="space-y-2">
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : showEmpty ? (
              <p className="text-sm text-muted-foreground">
                No templates yet. Add one above, and it&apos;ll appear here.
              </p>
            ) : (
              <ul className="space-y-2" data-testid="template-list">
                {templates.map((template) => (
                  <li
                    key={template.id}
                    className="glass-clear space-y-2 rounded-2xl px-3.5 py-3"
                    data-testid="template-item"
                  >
                    {editingId === template.id ? (
                      <>
                        <input
                          value={editingTitle}
                          maxLength={TITLE_MAX}
                          onChange={(event) =>
                            setEditingTitle(event.currentTarget.value)
                          }
                          className="w-full rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-sm leading-5 text-foreground outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/25"
                          data-testid="template-edit-title"
                        />
                        <textarea
                          value={editingBody}
                          maxLength={BODY_MAX}
                          rows={3}
                          onChange={(event) =>
                            setEditingBody(event.currentTarget.value)
                          }
                          className="min-h-20 w-full resize-y rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-sm leading-5 text-foreground outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/25"
                          data-testid="template-edit-body"
                        />
                        <input
                          value={editingDescription}
                          maxLength={DESCRIPTION_MAX}
                          onChange={(event) =>
                            setEditingDescription(event.currentTarget.value)
                          }
                          className="w-full rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-sm leading-5 text-foreground outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/25"
                          placeholder="Description (optional)"
                          data-testid="template-edit-description"
                        />
                        <div className="flex justify-end gap-2">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={cancelEdit}
                            data-testid="template-edit-cancel"
                          >
                            <X aria-hidden className="size-3.5" />
                            <span>Cancel</span>
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            onClick={() => void handleSaveEdit(template.id)}
                            disabled={
                              busyId === template.id ||
                              editingTitle.trim().length === 0 ||
                              editingBody.trim().length === 0
                            }
                            data-testid="template-edit-save"
                          >
                            Save
                          </Button>
                        </div>
                      </>
                    ) : (
                      <div className="flex items-start gap-3">
                        <FileText
                          aria-hidden
                          className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                        />
                        <div className="min-w-0 flex-1 space-y-0.5">
                          <p className="text-sm font-medium break-words">
                            {template.title}
                          </p>
                          {template.description ? (
                            <p className="text-xs text-muted-foreground break-words">
                              {template.description}
                            </p>
                          ) : null}
                          <p className="text-sm break-words whitespace-pre-wrap text-muted-foreground">
                            {template.body}
                          </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            aria-label="Edit template"
                            onClick={() => startEdit(template)}
                            disabled={busyId === template.id}
                            data-testid="template-edit-button"
                          >
                            <Pencil aria-hidden className="size-3.5" />
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            aria-label="Delete template"
                            onClick={() => void handleDelete(template.id)}
                            disabled={busyId === template.id}
                            data-testid="template-delete-button"
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
    </div>
  );
}

// Standalone dialog wrapper — preserved for any standalone caller. The body is
// the same one the Settings hub hosts as a tab.
export function TemplateLibraryDialog({
  open,
  onOpenChange,
}: TemplateLibraryDialogProps): JSX.Element {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[80dvh] sm:max-h-none">
        {open ? <TemplateLibraryBody active={open} /> : null}
      </DialogContent>
    </Dialog>
  );
}
