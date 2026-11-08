# Values and Load

Apply these sections as Step 2 sections of SKILL.md: answer each question for every inventory entry whose subject the section has, and pass every candidate through SKILL.md's Step 3.

## 2.7 Money, numbers, time and text

- **Money.** Binary floating point (`float`, `double`, a JavaScript `number` with fractions) for amounts stored, charged, compared or summed is a defect; use decimals or integer minor units. Check currency minor units (JPY 0 decimals, KWD 3), the rounding mode and where it applies (per line or on the total, per the contract), split parts adding up to the total (allocate the remainder), truncating integer division, and the order of conversion and rounding.
- **Numbers.** Units (milliseconds versus seconds), percentages as 0.15 versus 15, division by zero, parse failures, overflow and values out of the column's range.
- **Time.** Candidate: an instant stored in local time or with no offset; confirm it when the schema, a contract or another reader expects UTC. Apply date-only rules (due today, end of month) in the contract's time zone. Check daylight-saving changes, month ends, leap days, and inclusive versus exclusive end times.
- **Text.** Normalize case and whitespace alike on write and lookup; check collation and whether length limits count bytes or characters.

Usually correct: floats for non-money ratios and metrics; rounding only for display when stored values are exact.

## 2.8 Boundaries, lists and batches

- Test each comparison at its edge: `<` versus `<=`, an inclusive end date, a count at the limit, zero or one item, the last page.
- Pagination: the sort order must be total (a unique tiebreaker such as the ID), and a cursor must encode every sort key and compare in the sort's direction. Offset paging under concurrent inserts can skip or repeat rows; a defect only when the contract promises a stable listing. "Has more" must be right when exactly `limit` rows remain: fetch `limit + 1`. Candidate: a page size the client can raise with no server cap.
- Batches: handle an empty `IN ()` list and duplicate input IDs; report errors at the input's original positions when the contract asks. Candidate: a batch with no maximum size.

Usually correct: offset paging on an internal list with no stability promise.

## 2.9 Queries and load

- **Per-item queries (N+1).** A query or remote call inside a loop over a result whose size grows with data or user input is a candidate. Confirm it only when the list size is user- or data-driven on a request path and a contract or sourced latency limit applies; otherwise it is a suggestion. Rate it by measured or sourced impact. Usually correct: a loop bounded by a small constant, a batched `IN` fetch, eager loading configured in the ORM, a per-request cache.
- **Unbounded work and timeouts.** Candidates: a user-driven query with no limit; a whole table loaded into memory; a new filter on a large table with no index (cite the schema); an external call with no timeout; retries multiplying across layers (3 × 3 × 3 = 27).
