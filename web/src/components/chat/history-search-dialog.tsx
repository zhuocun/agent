"use client";

import { useEffect, useMemo, useState, type JSX } from "react";
import { LoaderCircle, MessageSquare, Search } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { searchHistory } from "@/lib/apiClient";
import type {
  ConversationSummary,
  ModelTierId,
  Project,
  SearchFilters,
} from "@/lib/types";

// A tag the dialog can filter by. Kept structural (not the parallel workstream's
// ORM-backed type) so this branch type-checks while `tags` is empty; integration
// passes the real tag list, which only needs `{ id, name }` here.
export interface SearchTag {
  id: string;
  name: string;
}

export interface HistorySearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projects: Project[];
  // Empty in this branch (the tag workstream ships separately); the control
  // hides itself when there are no tags so it's inert until then.
  tags?: SearchTag[];
  onSelectConversation: (id: string) => void;
}

// Served-model options mirror the `ModelTierId` union (the BE matches the
// matched message's `attribution.servedTierId`). Friendly labels only — never a
// raw model id (PRD 06 §5.6).
const SERVED_MODEL_OPTIONS: { value: ModelTierId; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "fast", label: "Fast" },
  { value: "smart", label: "Smart" },
  { value: "pro", label: "Pro" },
];

// Shared input styling — copied from the sidebar/template inputs so the controls
// read as part of the same surface family.
const INPUT_CLASS =
  "w-full min-w-0 rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-sm leading-5 text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25";
const DATE_INPUT_CLASS =
  "w-full min-w-[7.5rem] rounded-xl border border-border/70 bg-background/70 px-2 py-2 text-sm leading-5 text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25";
const SELECT_CLASS =
  "h-9 w-full truncate rounded-xl border border-border/70 bg-background/70 px-3 text-sm text-foreground outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/25";

// Date input <-> ISO. The native date input gives a `YYYY-MM-DD` string; the BE
// parses ISO-8601. `dateTo` is widened to end-of-day so an inclusive "to"
// matches conversations updated any time on that calendar day.
function toIsoStart(date: string): string | undefined {
  return date ? new Date(`${date}T00:00:00`).toISOString() : undefined;
}
function toIsoEnd(date: string): string | undefined {
  return date ? new Date(`${date}T23:59:59.999`).toISOString() : undefined;
}

function parseCost(value: string): number | undefined {
  if (value.trim() === "") return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

// The advanced history-search dialog. A separate surface from the Cmd+K palette
// (too tight for filters): a query input plus transparency-native filters
// (served-model, cost range, date range, project, tag) over the same
// `/api/conversations/search` wire path, extended via `searchHistory`. Results
// surface the matched message's served-model / cost / date inline; clicking a
// result navigates to that conversation.
export function HistorySearchDialog({
  open,
  onOpenChange,
  projects,
  tags = [],
  onSelectConversation,
}: HistorySearchDialogProps): JSX.Element {
  const [query, setQuery] = useState("");
  const [servedModel, setServedModel] = useState<ModelTierId | "">("");
  const [costMin, setCostMin] = useState("");
  const [costMax, setCostMax] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [projectId, setProjectId] = useState("");
  const [tagId, setTagId] = useState("");

  const [results, setResults] = useState<ConversationSummary[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Flips true once the first query has settled, so the empty state reads as
  // "no matches" only after a search ran (not before the user typed anything).
  const [searched, setSearched] = useState(false);

  // Build the filter payload from the controls. Memoized on the raw control
  // values so the search effect re-runs only when something actually changed.
  const filters: SearchFilters = useMemo(
    () => ({
      servedModel: servedModel || undefined,
      costMin: parseCost(costMin),
      costMax: parseCost(costMax),
      dateFrom: toIsoStart(dateFrom),
      dateTo: toIsoEnd(dateTo),
      projectId: projectId || undefined,
      tagId: tagId || undefined,
    }),
    [servedModel, costMin, costMax, dateFrom, dateTo, projectId, tagId],
  );

  // Debounced search: runs whenever the (open) dialog has a non-empty query or
  // its filters change. Empty query clears results without hitting the BE (the
  // `q` param is required server-side).
  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    if (q.length === 0) {
      // Clearing transient state on an empty query is a deliberate effect-time
      // reset, not a cascading render — the rule's caveat case.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setResults([]);
      setPending(false);
      setSearched(false);
      return;
    }
    setPending(true);
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void searchHistory(q, filters, controller.signal)
        .then((rows) => {
          if (controller.signal.aborted) return;
          setResults(rows);
          setError(null);
          setPending(false);
          setSearched(true);
        })
        .catch(() => {
          if (controller.signal.aborted) return;
          setError("Couldn't run that search. Please try again.");
          setPending(false);
          setSearched(true);
        });
    }, 200);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [open, query, filters]);

  const handleOpenChange = (next: boolean): void => {
    if (!next) {
      // Reset everything so a re-open starts from a clean slate.
      setQuery("");
      setServedModel("");
      setCostMin("");
      setCostMax("");
      setDateFrom("");
      setDateTo("");
      setProjectId("");
      setTagId("");
      setResults([]);
      setPending(false);
      setError(null);
      setSearched(false);
    }
    onOpenChange(next);
  };

  const handleSelect = (id: string): void => {
    handleOpenChange(false);
    // Defer so the dialog's close animation doesn't race the navigation /
    // focus move (mirrors the command palette).
    requestAnimationFrame(() => onSelectConversation(id));
  };

  const showEmpty =
    searched && !pending && error === null && results.length === 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-h-[85dvh] sm:max-h-none sm:max-w-2xl"
        data-testid="search-dialog"
      >
        <DialogHeader>
          <DialogTitle>Search history</DialogTitle>
          <DialogDescription>
            Search your conversations and filter by model, cost, date, or
            project.
          </DialogDescription>
        </DialogHeader>

        <div className="-mr-2 max-h-[68dvh] space-y-4 overflow-y-auto pr-2 sm:max-h-[70dvh]">
          {/* Query */}
          <div className="relative">
            <Search
              aria-hidden
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <input
              autoFocus
              type="search"
              value={query}
              onChange={(event) => setQuery(event.currentTarget.value)}
              placeholder="Search conversations…"
              aria-label="Search query"
              className={`${INPUT_CLASS} pl-9`}
              data-testid="search-query-input"
            />
          </div>

          {/* Filters */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-muted-foreground">
                Model
              </span>
              <select
                value={servedModel}
                onChange={(event) =>
                  setServedModel(event.currentTarget.value as ModelTierId | "")
                }
                className={SELECT_CLASS}
                data-testid="search-filter-model"
              >
                <option value="">Any model</option>
                {SERVED_MODEL_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-xs font-medium text-muted-foreground">
                Project
              </span>
              <select
                value={projectId}
                onChange={(event) => setProjectId(event.currentTarget.value)}
                className={SELECT_CLASS}
                data-testid="search-filter-project"
              >
                <option value="">Any project</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>

            <div className="space-y-1 text-sm">
              <span className="text-xs font-medium text-muted-foreground">
                Cost (USD)
              </span>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  inputMode="decimal"
                  value={costMin}
                  onChange={(event) => setCostMin(event.currentTarget.value)}
                  placeholder="Min"
                  aria-label="Minimum cost"
                  className={INPUT_CLASS}
                  data-testid="search-filter-cost-min"
                />
                <span aria-hidden className="text-muted-foreground">
                  –
                </span>
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  inputMode="decimal"
                  value={costMax}
                  onChange={(event) => setCostMax(event.currentTarget.value)}
                  placeholder="Max"
                  aria-label="Maximum cost"
                  className={INPUT_CLASS}
                  data-testid="search-filter-cost-max"
                />
              </div>
            </div>

            <div className="space-y-1 text-sm sm:col-span-2">
              <span className="text-xs font-medium text-muted-foreground">
                Date
              </span>
              <div className="flex items-center gap-2">
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(event) => setDateFrom(event.currentTarget.value)}
                  aria-label="From date"
                  className={DATE_INPUT_CLASS}
                  data-testid="search-filter-date-from"
                />
                <span aria-hidden className="text-muted-foreground">
                  –
                </span>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(event) => setDateTo(event.currentTarget.value)}
                  aria-label="To date"
                  className={DATE_INPUT_CLASS}
                  data-testid="search-filter-date-to"
                />
              </div>
            </div>

            {/* Tag filter — hidden until the tags workstream lands (the prop is
                empty in this branch). Rendered structurally so integration only
                has to pass `tags`. */}
            {tags.length > 0 ? (
              <label className="space-y-1 text-sm">
                <span className="text-xs font-medium text-muted-foreground">
                  Tag
                </span>
                <select
                  value={tagId}
                  onChange={(event) => setTagId(event.currentTarget.value)}
                  className={SELECT_CLASS}
                  data-testid="search-filter-tag"
                >
                  <option value="">Any tag</option>
                  {tags.map((tag) => (
                    <option key={tag.id} value={tag.id}>
                      {tag.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>

          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}

          {/* Results */}
          <section className="space-y-2" aria-busy={pending || undefined}>
            {pending ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <LoaderCircle
                  aria-hidden
                  className="size-4 motion-safe:animate-spin"
                />
                Searching…
              </p>
            ) : showEmpty ? (
              <p className="text-sm text-muted-foreground">
                No matches — try a different term or loosen the filters.
              </p>
            ) : results.length > 0 ? (
              <ul className="space-y-2" data-testid="search-results">
                {results.map((result) => {
                  const snippet = result.matchSnippet?.trim();
                  return (
                    <li key={result.id}>
                      <button
                        type="button"
                        onClick={() => handleSelect(result.id)}
                        className="glass-clear flex w-full items-start gap-3 rounded-2xl px-3.5 py-3 text-left outline-none transition-colors hover:bg-foreground/[0.04] focus-visible:shadow-[var(--focus-ring)]"
                        data-testid="search-result"
                        data-conversation-id={result.id}
                      >
                        <MessageSquare
                          aria-hidden
                          className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                        />
                        <span className="min-w-0 flex-1 space-y-1">
                          <span className="block truncate text-sm font-medium">
                            {result.title}
                          </span>
                          {snippet ? (
                            <span className="block truncate text-xs text-muted-foreground">
                              {snippet}
                            </span>
                          ) : null}
                          {result.servedModelLabel ||
                          result.costUsd != null ||
                          result.matchedAt ? (
                            <span className="flex flex-wrap items-center gap-1.5 pt-0.5">
                              {result.servedModelLabel ? (
                                <Badge variant="secondary">
                                  {result.servedModelLabel}
                                </Badge>
                              ) : null}
                              {result.costUsd != null ? (
                                <Badge variant="outline">
                                  ${result.costUsd.toFixed(4)}
                                </Badge>
                              ) : null}
                              {result.matchedAt ? (
                                <span className="text-2xs text-muted-foreground">
                                  {new Date(
                                    result.matchedAt,
                                  ).toLocaleDateString()}
                                </span>
                              ) : null}
                            </span>
                          ) : null}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
