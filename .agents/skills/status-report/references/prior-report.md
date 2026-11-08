# Prior report

Apply this file when a prior report exists, before marking movement in the table or writing `Changes since`.

## Changes since

Bullets, cap five. On overflow, fold changes of the same kind into one bullet, then keep the most consequential; the table's delta markers still show every status and count change. A change qualifies only if it altered a task's or a subtask's status, altered a progress count, or opened or closed an `Action required` item. Each bullet states the change, what it means, and a reference. Never restate a current count on its own; a count may appear only as the endpoint of a stated transition. **Effort is not a change.**

## Delta markers

- Mark movement in the cell: `(unchanged)` only where the row's status moved but its count did not, `(new)` for a row absent then, `(+n)` for a changed count, `(was <status>)` for a changed status. `(was <status>)` follows the Status value in the Status cell, and every other marker goes in Progress; the status vocabularies apply to the value before the marker. Mark only rows that changed; a delta on every row is noise. A task row, and any row carrying a folded count, marks movement on Status only.
- If the unit or denominator changed, write `(rebaselined from <old count>)` and make the rebaseline a `Changes since` bullet.
