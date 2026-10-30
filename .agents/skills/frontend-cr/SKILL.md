---
name: frontend-cr
description: >-
  Use when reviewing or auditing frontend code or a frontend diff/PR (React,
  TypeScript, JavaScript, Vue, Svelte, Solid, and other component frameworks).
  Check runtime errors, boundary data, XSS or injection, unsafe HTML and URLs,
  lost input, wrong or stale data, async errors, hook and effect bugs, type
  honesty, code smell, and frontend architecture or folder layering. Read
  source and report findings. Do not use for judging visual design or page
  layout, backend services, infrastructure, or non-UI logic.
---

# Frontend Code Review

Find user-visible frontend defects with few false alarms. Report only proven reachable violations after searching for defenses.

Priority: **runtime safety, security and data integrity → failure handling → state and effect correctness → type honesty → maintainability and layering → style**. Follow explicit user and project requirements first.

## Review rules

- Review without editing code. Propose repairs separately. Remediate only with explicit permission.
- Record the revision and initial workspace changes. Preserve unrelated work. Check command side effects; run only authorized, isolated checks without changing reviewed files, shared data, or services. Do not read credentials.
- On a diff review, report only defects introduced or worsened by the diff; put other verified defects you notice on the Pre-existing line. Read unchanged dependencies to understand the changed behavior.
- Prefer the narrowest fix within the existing design. Do not turn a repair into a component rewrite or architecture change.
- Treat every sign below as a candidate, not a finding. Syntax, a lint warning, a missing test, or a preferred pattern alone proves no defect.

## Step 1: Map the change

1. Read the PR description, requirements, project rules, and whole diff. Read any given QA story set (user stories with acceptance criteria) as requirements; never invent stories. On a later review round, review only changes since the last reviewed revision and verify earlier fixes. Identify the framework version, rendering mode, router, and state/cache libraries.
2. Read unchanged callers, consumers, types, schemas, shared hooks, API adapters, and wrappers the change relies on. Follow imports until you can see validation, error ownership, and state ownership. Respect an explicit review boundary. List unavailable code as a coverage gap.
3. Make a short inventory before hunting. For each changed component, hook, helper, or action, record:
   - Each boundary value: network response, input, route/query parameter, storage, browser API, SDK, or external prop. Note its contract, guard, and downstream uses.
   - Each state or cache write: owner, record identity, prior value, and readers.
   - Each effect: dependencies, captured values, resources, and cleanup.
   - Each async action: initiator, pending state, success, failure, cancellation, and completion writes.
   - Each rendered untrusted string: source, transformations, and final text, HTML, URL, or attribute context.
4. Connect the entries across files. Trace response → adapter → hook/cache → component → user action → write. Include covering tests. Map each in-scope story to its code path and covering test.

## Step 2: Hunt each entry

Apply every relevant section to each inventory entry. Derive expected behavior from the rule, not the implementation; contrast legal inputs, states, or completion orders differing in one relevant dimension. Trace across files and compare usually-correct look-alikes. Continue across independent decisions and effects without proving each candidate first. Explain skipped sections.

### 2.1 Boundary values and transformations

- Trace each value past its first use. Check null, missing fields, empty arrays, absent indices, and wrong shapes where the contract permits them. Check destructuring, array methods, nested access, and renderable types.
- Follow `?.` results downstream. Does `undefined` later reach `.length`, a calculation, or a required child prop? Use a fallback only if its meaning is valid. An empty list must not disguise a failed load.
- Retain original values through transformations. Try legal inputs whose type-valid outputs change required meaning or collapse distinct identities/values. Check `||` replacing valid falsy values, blank/null becoming zero, partial `parseInt`, `NaN`, infinities, invalid dates, seconds/milliseconds confusion, and precision/rounding.
- Check storage reads and `JSON.parse` failures separately. A parsed value still needs the shape its consumer assumes.
- Trace `any`, assertions, and non-null `!` back to their proof. Type declarations alone do not validate external data. Check that schema validation runs and handles failure. Follow the validated value onward.

Usually correct: contract-guaranteed fields; props guaranteed by every caller; guarded access or successful schema parsing; deliberate `||` for all falsy values; optional rendering of absent content; proven assertions; contract-defined normalization or loss. Raw differences or round-trip failures alone do not prove defects. Do not invent violations or demand repeated validation.

### 2.2 State, forms, identity and navigation

- For each write, ask which record and render it belongs to. Trace two queued updates from the same captured value. Check direct mutation, shared object aliases, and old snapshots overwriting newer edits.
- Follow typed input through loading, validation, rerender, refetch, save failure, and retry. Check controlled/uncontrolled transitions, default values, and effects that copy props over dirty fields.
- Check list keys and component keys through reorder, insertion, deletion, and selection changes. Can state move to another record or a remount erase input?
- Trace form submit, Enter, button click, and repeated activation. Check unintended submit buttons and whether pending guards cover every path. Does a second invocation create a second effect before the first completes?
- Follow route/query changes, back/forward, and record switches. Check parser/serializer agreement, filter/page synchronization, and updates that drop other parameters. Does navigation discard edits the flow promises to preserve or submit them to the wrong record?

Usually correct: functional updates; deliberate reset on record change; immutable state; index keys on a static list with no identity changes; an actually disabled submit path; server deduplication preventing duplicate effects; navigation with an explicit discard decision. Do not require persistence for every form.

### 2.3 Async actions and failure handling

- Start A, change selection or start B, then trace both completion orders. Trace every success, catch, and finally write. Can A replace B's data, clear B's pending state, or show an error for the wrong record?
- Check optimistic writes on rejection and partial success. Does rollback or reconciliation restore truth without erasing a later edit? Can an old refetch replace an optimistic value?
- Trace rejection ownership through callers and shared wrappers. `try { workAsync() }` does not catch its later rejection unless awaited. A returned promise can transfer ownership to a caller. Inspect event handlers, timers, subscriptions, and detached work too.
- Check HTTP status handling: `fetch` resolves on HTTP errors. Check response parsing and domain-error handling before success UI, navigation, or clearing input.
- Check pending release on every exit. A failure must leave a usable retry path and retain input where required. Logging alone does not repair a stuck form or false success.
- `Promise.all` rejects early but cancels nothing. Check partial side effects and recovery; do not prescribe `allSettled` unless partial success is allowed.
- Find the render error boundary and its fallback. Check loading and rejection handling for suspending reads. Ordinary error boundaries do not catch event-handler or detached async failures. Check the framework's route, loader, and server-render error handling separately.

Usually correct: cancellation intentionally ignored; best-effort telemetry failure; a caller or query library handling rejection; a generation check rejecting stale completions; deliberate stale data labeled during refresh. Abort alone is not proof if later processing still writes state.

### 2.4 Hooks, effects and resource lifetime

- For each effect, memoized value, and callback, list reactive reads. Change each prop, state, or context value in turn. Does the computation or callback use the current value when needed?
- Trace unstable dependencies to a consequence. A new object causes reruns, but a loop needs a state write that causes another changed dependency. Check the write and its bailout.
- Match setup with cleanup on dependency change and unmount. Check timers, listeners, observers, subscriptions, sockets, and async completions. Cleanup must remove the same resource and handler. Check setup → cleanup → setup for duplicate active work.
- Check derived-state effects for stale intermediate renders or overwritten input. Recommend render-time derivation only when it preserves the behavior. Do not flag an effect solely because it sets state.
- Check hook order across early returns, branches, and loops. Apply the installed React version's exceptions: `use` may be conditional, but not inside `try/catch`. An async effect callback returns a promise instead of cleanup.
- Check render-time mutations and ref reads for a concrete purity or stale-display failure. Server Components cannot use client state/effect hooks.

Usually correct: omitted stable `useState` setters and `useRef` objects; functional updates avoiding captured state; dependencies stabilized by a shared hook's contract; harmless `useMemo`/`useCallback`; library-owned cleanup; a completed one-shot operation. A missing dependency or cleanup matters only when it changes behavior or leaks an active resource.

Map these checks to other frameworks. Vue `watch` tracks declared sources, not callback reads. Vue `watchEffect`, Svelte `$effect`, and Solid `createEffect` track synchronous reads, not reads after `await` or in a timer. Svelte legacy `$:` tracks directly referenced variables. Check framework-specific cleanup and derived/computed values; do not demand React dependency arrays elsewhere.

### 2.5 Server-state caches

- Compare query keys with all inputs that change the result: record, user/tenant, filter, sort, page, and locale when relevant. Trace each consumer of a shared key.
- After a mutation, trace detail, list, count, and derived queries that display its result. Check actual invalidation matching and library defaults. Can old data persist beyond the promised freshness?
- Check identity changes and logout. Can one account see another account's cached result? Trace overlapping fetches and mutations through cache writes.

Usually correct: key factories including the inputs; scoped providers clearing identity; intentional stale-time or pagination placeholders; automatic invalidation or normalized-cache updates. A missing manual invalidation call alone is not a defect.

### 2.6 Untrusted HTML, URLs and attributes

- Trace boundary strings to `dangerouslySetInnerHTML`, `innerHTML`, document-writing APIs, and markup renderers. Does sanitization cover the final markup and permitted features? Check transformations after sanitization.
- For URLs, identify the actual sink and browser/framework behavior. Check executable schemes such as `javascript:` in links or navigation. Check URL parsing, case, and leading whitespace against the scheme policy. Check origin restrictions only when required, including relative and protocol-relative URLs.
- Check dynamic attributes and spread props for dangerous capabilities. Prove which value reaches which operation. A string in `src` does not automatically execute like a navigation URL.

Usually correct: React text interpolation and ordinary escaped attributes; trusted constant markup; a maintained sanitizer configured for the context; a validated URL allowlist; a blocked scheme under the installed framework. Do not demand HTML sanitization of plain text or treat every `data:` URL as executable.

### 2.7 Server rendering, dates and locale

- When SSR applies, compare server HTML with the first client render. Check browser-only APIs, random IDs, current time, local storage, and differing data or locale. Trace a mismatch to broken hydration or incorrect UI.
- Trace date-only values versus instants, local-time and timezone conversion, locale parsing, currency/units, and rounding against the contract.

Usually correct: client-only rendering; browser reads after hydration; stable serialized data and framework IDs; an intentional isolated hydration exception; user-local formatting when the contract asks for it. Do not demand UTC display or identical locale output without a requirement.

### 2.8 Tests

For each changed behavior, ask: would reverting the change or deleting its guard fail a meaningful assertion? Check that tests exercise the real changed component/hook and user path. Inspect mocks that bypass the adapter or effect. Check unawaited interactions and assertions before completion. Check snapshots without behavior assertions and mocked return values asserted against themselves. Race tests need distinguishable responses and controlled completion order, not fixed sleeps.

A missing test is a coverage gap, not proof of a production defect. Separate ineffective tests from production findings. State what ran and what was only read.

### 2.9 Code smell and layering

Judge against the repo's documented or existing convention. On a diff, flag only structure introduced or worsened. Keep structural findings separate from behavior defects. Cite the violated rule or concrete maintenance consequence; otherwise make an optional suggestion.

Without a convention, use feature ownership and one-way dependencies as guidance. Let routing/providers compose features. Keep components, hooks, data access, and types with their feature. Let shared code serve multiple features without importing them. Prefer public feature interfaces over internal imports. Separate presentation from state/data logic when responsibilities require it. Add a layer only for a real concern. Do not enforce file counts or line thresholds.

Usually correct: small colocated components; intentional composition or prop passing; library conventions combining fetching and rendering; local duplication cheaper than an abstraction; an inline context value without demonstrated impact. Size, memoization, nesting, or several booleans alone is not a defect.

## Step 3: Verify before reporting

For each candidate, try to disprove it:

1. Locate the contract: PR description, given stories and acceptance criteria, and product rules; types, schemas, and API docs; callers, tests, and established behavior; project standards. Distinguish compile-time promises from runtime enforcement. A story silent on the case confirms nothing; the absence of a story is never itself a defect.
2. Check baseline UI obligations too. Supported inputs must not crash. Untrusted content must not execute. Edits must not silently move to another record or disappear during the promised flow. Failed work must not appear successful. Displayed results must match their stated identity and freshness.
3. Trace the exact trigger's branch conditions and intermediate values across files; confirm branch reachability and rule violation. Exclude boundary-rejected data. Static trace and arithmetic can suffice; use permitted isolated probes only for decisive uncertainty.
4. Search callers, schemas, adapters, shared hooks, framework behavior, and cache configuration for defenses. Trace each against this trigger; drop blocked candidates.
5. Name the user-visible consequence and narrowest fix. Keep valid guards and recovery behavior.
6. Classify: **Confirmed** requires the reachable trigger, violated contract, and evidence. **Uncertain** means a decisive fact or contract is silent or ambiguous; state the exact question and decision owner. **Suggestion** means an optional improvement without a demonstrated violation. Keep the three separate. Drop disproved candidates.

## Step 4: Rate and report

Use the project's severity scheme, else rate confirmed impact and reachability:

- **Blocker:** routine use causes severe loss/corruption, cross-user exposure, executable untrusted content, or an unusable core flow.
- **Major:** a reachable crash, wrong/stale result, lost input, stuck action, race, or active leak with limited scope or recovery.
- **Minor:** a demonstrated small behavior defect or a concrete maintainability violation.

Do not rate by syntax. An unguarded access is not automatically a Blocker.

Use this compact form. Omit empty sections. Order findings by severity. Combine repeated instances of one cause, not distinct defects; list every instance. Do not repeat a fixed earlier finding; carry an unfixed, failed-fix or worsened one under its original ID. Give each given story one status: violated (a finding), uncertain (an Uncertain item), not covered by a test (no violation, no effective test: a test gap), met (satisfied and tested), or outside scope. Keep the Stories line even with no set. Expand only for multiple independent flows or a requested full report.

```text
Scope: <revision/diff and flows reviewed; later round: base revision, fixes verified>
Findings: <count, or no confirmed defects in reviewed scope>
F1 [severity] <title> — <file:line; related locations>
  Trigger: <action/value/timing and cross-file path>
  Contract: <required behavior and source>
  Consequence: <what the user sees or loses>
  Evidence: <decisive code facts; reproduction/test result if run>
  Fix: <narrowest repair; exact replacement when useful>
  Verify: <regression assertion that fails before and passes after>
Uncertain: <question; missing fact/source; owner>
Stories: <S1 met, S2 violated F1, …; or none given>
Pre-existing: <file:line — defect the diff did not introduce or worsen>
Test gaps / suggestions: <separate from defects>
Skipped / unavailable: <sections or code — reason, in one line>
Checks: <commands, revision, results; or reading only>
Workspace: <unchanged, or explain changes>; pending checks: <what remains>
```

Propose the verification; do not implement it during review without permission. Never claim an unrun test passed or a clean review proves production safety.

## Self-check

- [ ] Every changed flow has an inventory. Read unchanged callers, types, shared hooks, and consumers needed for its contract. Each given story has a path, test, and status, or Stories says none given.
- [ ] Trace each applicable hunt section across files, including stale completions and failure paths. List skipped or unavailable coverage.
- [ ] Each finding has a reachable trigger, contract, location, consequence, evidence, searched defense, and narrow fix.
- [ ] Reject usually-correct look-alikes. Separate uncertain cases, test gaps, structural concerns, and optional suggestions from confirmed behavior defects.
- [ ] Scale severity and report length to proven impact. One finding per cause, with every instance; pre-existing defects on their own line; fixed earlier findings not repeated; a later round reviews newer changes and earlier fixes. Record checks honestly. Keep review separate from remediation and preserve unrelated work.
