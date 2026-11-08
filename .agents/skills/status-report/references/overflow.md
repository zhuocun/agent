# Overflow

Apply this file when the Tasks table would exceed 10 tasks or 20 table rows or has a rolled or folded row, or when more than five items qualify for `Action required`.

## Tasks table cap

When over either cap, roll the terminal tasks into one row naming each of them, whose Status follows the derivation rule applied to them, and whose Progress counts them by status (`2 done · 1 dropped`); then fold all of a non-terminal task's subtask rows at once into a count in its task row's Progress, in the order `blocked · running · paused · not started · done · dropped · unknown`, for example `1 blocked · 2 not started · 3 done`. Retain unverified qualifiers on folded counts. Fold first the tasks whose subtasks are all `Not started`, `Done` or `Dropped`, then the others, until the table fits 20 rows or every task is folded; a folded `Blocked` or `Paused` subtask still appears on the Blocked line or in `Action required`, and a folded `Running` subtask's identity and as-of evidence move into its task row's Evidence cell. If more than 10 non-terminal tasks remain, print them all — complete picture outranks concision — and say so in the verdict.

## Action required overflow

If the items that match a `Blocked` or `Paused` subtask alone exceed five, merge the ones that share an owner and print the rest. On overflow of the other items, keep the most consequential and let the verdict name what was left out.
