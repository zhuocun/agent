# Illustrations

Apply this file when a report has or adds any illustration other than the Blocked line. Omit an optional illustration that merely duplicates an easy scan or makes the report harder to read.

## Licensed illustrations

- **Conditional, at 8 or more tasks:** `<N> tasks: <counts in the attention order>`. Below 8 it is a defect — a status tally is by definition the result of scanning one column, and at four tasks the line is longer than the column it summarizes.
- **Conditional, dependency graph:** include only when a chain has at least two blocking edges across three subtasks and the graph makes its indirect effects easier to see. One edge and shared blockers are already expressed by the Dependency cells and Blocked line. Use ASCII art in a fenced block if legible, otherwise one blocker per line with dependents comma-separated, or rely on the Blocked line. Keep the Blocked line in every case.
- **Conditional, progress bars:** use only for a small enumerable denominator of at most 12, when the symbols are distinguishable at the destination and help the reader scan comparable units. Explain the symbols once, for example `█ done, · remaining`; retain the numeric count and unit. A bar has exactly as many cells as the denominator and filled cells as the numerator: `3/5` is `███··`. It measures unit count, never effort. The count and unit remain the claim; omit the bar when it adds width without helping the reader. If two outcome axes need bars, label each axis; neither may hide the other. Omit bars for unknown totals, unlike-unit comparisons or crowded cells. Do not add another rendering beside a value unless this exact-unit rule makes it mechanically checkable.
- **Conditional, milestone track:** only when named milestones already exist outside the report.

## Rejected illustrations

**Rejected outright:** progress bars whose cell count differs from the denominator; sparklines; burn or trend indicators.

## Chain topology

Topology beyond the answer to "what is blocked and by what" — chain order, indirect dependents — may live only in the graph; deleting every illustration may leave the reader not knowing how deep the chain runs.
