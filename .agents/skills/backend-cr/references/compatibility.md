# Compatibility

Apply these sections as Step 2 sections of SKILL.md: answer each question for every inventory entry whose subject the section has, and pass every candidate through SKILL.md's Step 3.

## 2.10 Compatibility, deploys and migrations

When the project deploys by rolling update or can roll back, assume old and new versions run together and a rollback runs old code on data new code wrote.

- **Migrations.** A NOT NULL column with no default on a table old code inserts into; renaming or dropping a column or table old code reads; a column type change; a new enum value old readers reject; a long-locking change on a large table; a backfill overwriting rows written after it started; a migration that fails on re-run. Safe pattern: add the nullable or defaulted shape, deploy code handling both, backfill, remove the old shape later.
- **APIs and messages.** Removing or renaming a field; changing its meaning, unit or default; making an optional request field required; a decoder rejecting unknown fields, so an added field breaks old readers. The new version must process messages the old one queued, and old consumers still running must read new messages.
- **Configuration and flags.** Check the default for a missing setting and both branches of a switch; turning a flag off must stop the effect, not just hide the entry point.
- **Removal.** Before removing a field, method or endpoint, search every caller, including reflection, configuration, scheduled jobs and other services, and report unknown external consumers.
- **Released behavior.** "Released behavior preserved" needs a comparison of inputs, outputs, defaults, failures, ordering and side effects with the released artifact or an approved equivalent, not a development branch; if unavailable, it is a pending gate with an owner.
- **Documentation.** When behavior changes, check that the API schema, interface comments and error catalog describe the new nullability, units, failures and effects; a stale description callers rely on is a finding.

Usually correct: an added nullable column or optional response field that clients ignore.
