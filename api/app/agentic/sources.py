"""One run-scoped citation namespace for an agentic turn (AC-08).

Each worker numbers its own sources from 1, so a fan-out produces several
worker-local `[1]`s that must become distinct globals before anything reaches
the user, the aggregator, or the persisted catalog. `SourceNamespace` is the ONLY
implementation of that allocation: a second, list-ordered remapper in
`aggregate.py` renumbered by worker-plan position, diverging from the
arrival-ordered globals the live stream had already emitted.

Four properties the allocator has to hold, each learned from a live defect:

- **Arrival order.** Ids are handed out in the order events actually arrive, not
  plan order, because the wire has already shown earlier ids to the user.
- **Citation before source.** `[1]` can be written before the worker's own
  `Sources` event lands, so every surface allocates through `_global_id` and no
  marker falls through to its raw local ordinal — which resolved against
  whichever worker happened to own that global id (FL-16-a / FE-1).
- **Chunk safety.** A marker splits across answer deltas (`"See ["` + `"1]."`),
  so an unfinished trailing fragment is held per subagent until it completes.
- **Resume without reissue.** A citation-only global has no catalog row and can
  sit ABOVE the catalog's largest id, so `restored()` reads the allocator's own
  state — or, for checkpoints predating it, the citations left in answer text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from app.providers.protocol import Sources
from app.search.protocol import SourceItem

# Inline citation markers like ``[1]`` / ``[12]`` in worker answer text.
_CITATION_MARKER_RE = re.compile(r"\[(\d+)\]")

# Trailing incomplete citation opener: `[` or `[` + digits without a closing `]`.
_INCOMPLETE_CITATION_TAIL_RE = re.compile(r"\[\d*$")


def max_source_id(ids: Iterable[str]) -> int:
    """Largest citation ordinal in ``ids``, ignoring every entry `int` cannot read.

    Guarded rather than predicated, because no predicate stands in for `int`: a stored
    id is whatever an older build wrote, `"²"` passes `str.isdigit()`, an over-long
    digit string passes `str.isdecimal()`, and `int` rejects both. A resume reads these
    rows, so an unreadable id lowers the floor instead of raising out of that read.
    """
    floor = 0
    for sid in ids:
        try:
            floor = max(floor, int(sid))
        except (TypeError, ValueError):
            continue
    return floor


@dataclass(frozen=True, slots=True)
class CitationAllocation:
    """One worker-local to run-global citation id this run already published."""

    subagent_id: str
    local_id: int
    global_id: int


class SourceNamespace:
    """The run's global citation space: worker-local ordinals in, globals out."""

    def __init__(self, *, start: int = 1) -> None:
        self._next = max(1, start)
        self._map: dict[tuple[str, int], int] = {}
        # Global-id → remapped SourceItem (merged catalog for the aggregator).
        self._catalog: dict[int, SourceItem] = {}
        # Per-subagent unfinished citation fragment from the prior AnswerDelta.
        self._answer_carry: dict[str, str] = {}

    @classmethod
    def restored(
        cls,
        *,
        catalog: Sequence[SourceItem] = (),
        allocations: Sequence[CitationAllocation] = (),
        next_id: int = 0,
        prior_id_groups: Iterable[Iterable[str]] = (),
        prior_texts: Iterable[str] = (),
    ) -> SourceNamespace:
        """Reopen a paused run's namespace so nothing it published is reissued.

        No single record holds every published id: the catalog holds only the ones
        that reached a `Sources` event, so a citation-only `[n]` has no row there and
        can sit above the catalog's maximum. `allocations` and `next_id` are the
        allocator's own state and carry exactly those — without them a resumed
        worker's first new source took an id the pause turn had already rendered as a
        citation, silently pointing it at unrelated content. Checkpoints predating
        both still decode; for them every `[n]` in `prior_texts` (the paused draft and
        the finished siblings' answers) was rendered to the user, so the floor clears
        all of them. Those mappings are gone either way, so a re-citation allocates
        afresh — an unresolved marker rather than one silently pointing elsewhere.
        """
        namespace = cls(start=next_id)
        namespace.seed_catalog(catalog)
        for published in allocations:
            namespace._map[(published.subagent_id, published.local_id)] = published.global_id
            namespace._next = max(namespace._next, published.global_id + 1)
        marked = (_CITATION_MARKER_RE.findall(text) for text in prior_texts)
        cited = max((max_source_id(ids) for ids in (*prior_id_groups, *marked)), default=0)
        namespace._next = max(namespace._next, cited + 1)
        return namespace

    @property
    def next_id(self) -> int:
        """High-water mark: the next global id this namespace will hand out."""
        return self._next

    def allocations(self) -> tuple[CitationAllocation, ...]:
        """Every local→global mapping handed out, in allocation order."""
        return tuple(
            CitationAllocation(subagent_id=sid, local_id=local, global_id=gid)
            for (sid, local), gid in self._map.items()
        )

    def seed_catalog(self, items: Sequence[SourceItem]) -> None:
        """Pre-load a persisted catalog (resume) and advance the next id."""
        for item in items:
            gid = int(item.id)
            self._catalog[gid] = item
            self._next = max(self._next, gid + 1)

    def merged_items(self) -> list[SourceItem]:
        """Return the merged global catalog in ascending citation id order."""
        return [self._catalog[i] for i in sorted(self._catalog)]

    def remap_sources(self, event: Sources, subagent_id: str) -> Sources:
        """Renumber a worker's `Sources` event into the global space."""
        new_items: list[SourceItem] = []
        for item in event.items:
            gid = self._global_id(subagent_id, int(item.id))
            remapped = item.model_copy(update={"id": gid})
            self._catalog[gid] = remapped
            new_items.append(remapped)
        return replace(event, items=new_items)

    def rewrite_answer_text(self, text: str, subagent_id: str) -> str:
        """Rewrite ``[n]`` markers using this subagent's local→global map.

        Incomplete trailing ``[`` / ``[12`` fragments are held until the next
        chunk (or ``flush_answer_carry``) so split markers remap correctly.
        """
        combined = self._answer_carry.get(subagent_id, "") + text
        hold = ""
        process = combined
        incomplete = _INCOMPLETE_CITATION_TAIL_RE.search(combined)
        if incomplete is not None:
            hold = combined[incomplete.start() :]
            process = combined[: incomplete.start()]
        self._answer_carry[subagent_id] = hold

        if not process:
            return ""
        return self._rewrite_markers(process, subagent_id)

    def flush_answer_carry(self, subagent_id: str) -> str:
        """Emit any held fragment at worker end, rewriting complete markers."""
        hold = self._answer_carry.pop(subagent_id, "")
        if not hold:
            return ""
        return self._rewrite_markers(hold, subagent_id)

    def _global_id(self, subagent_id: str, local: int) -> int:
        """Global id for a worker-local ordinal, allocating on first sight.

        Every citation surface routes through here, so a marker cited BEFORE its
        own ``Sources`` event can never fall through to the raw local ordinal.
        """
        key = (subagent_id, local)
        gid = self._map.get(key)
        if gid is None:
            gid = self._next
            self._map[key] = gid
            self._next += 1
        return gid

    def _rewrite_markers(self, text: str, subagent_id: str) -> str:
        def _sub(match: re.Match[str]) -> str:
            return f"[{self._global_id(subagent_id, int(match.group(1)))}]"

        return _CITATION_MARKER_RE.sub(_sub, text)
