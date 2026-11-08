# Blocking chains

Apply this file when a `Blocked` subtask's Dependency names another subtask as its blocker.

## Following the chain

Follow the chain to the subtask at its end: a `Blocked` or `Paused` end carries the item under its own rule; a `Done` end no longer blocks, so re-derive the Status of the subtask it blocked; a `Running` end needs none; a `Not started` end needs a **Decision** item to start it or name its executor; a `Dropped` end needs a **Decision** item to re-scope or drop the blocked subtask. An unknown end needs an `Unverified claims` entry, without an invented ask.

## Worked example

The shape, in four tasks — a subtask blocked by another subtask, an agent running now, a paused subtask with its matching `Action required` item, a done development subtask followed by a running review, and a done task shown once:

```
# Payments — 2026-10-15 08:30 UTC @ 4ab7de1
<verdict>
## Tasks
Blocked: Payout rails / Reconciliation is blocked by Currency service / Rollout.
```

| Work | Status | Progress | Executor | Dependency | Evidence |
| --- | --- | --- | --- | --- | --- |
| **Payout rails** | Blocked | 0/2 subtasks done | — | — | CR-118 task checklist |
| Payout rails / Reconciliation | Blocked | 2/7 rails reconciled | Session S-51 | Blocked by Currency service / Rollout | CR-118 reconciliation record |
| Payout rails / Review | Not started | — | Unassigned | After Payout rails / Reconciliation | CR-118 review assignment and sequence |
| **Currency service** | In progress | 0/2 subtasks done | — | — | CR-120 task checklist |
| Currency service / Implementation | Running | 8/9 handlers implemented | Session S-42 | None | CR-120 handler checklist; run 9913 linked to S-42, live at 08:30 UTC |
| Currency service / Rollout | Paused | 5/9 handlers exposed | Unassigned | None | CR-120 rollout record; commit e91f0c2 (2026-10-09) |
| **Refund flow** | In progress | 1/2 subtasks done | — | — | CR-131 task checklist |
| Refund flow / Development | Done | 4/4 endpoints implemented | Session S-37 | None | CR-131 assignment; commit 7c21e0a |
| Refund flow / Review | Running | 5/8 review comments resolved | Li Wei | None | CR-131 review checklist, comment at 08:10 UTC |
| **Fraud rules** | Done (was In progress) | 2/2 subtasks done | — | — | CR-127 closed checklist |

Its matching `Action required` item; Reconciliation needs no item of its own, because its chain ends at Rollout:

`- **Decision** — Currency service / Rollout has no executor and nothing blocks it: assign an executor or confirm the pause — unblocks when an executor is named, owner payments team lead — Payout rails / Reconciliation stays blocked — commit e91f0c2`
