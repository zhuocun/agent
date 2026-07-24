// Shared calm copy for the FE last-resort empty-reply fallback (Layer 5). A
// turn can settle `done` after tool/subagent activity with no written main
// answer — most often a pre-fix persisted transcript the backend can't
// retroactively repair. The private thread pairs this line with a Regenerate
// CTA; the read-only share view shows the line alone. Kept in one place so both
// surfaces read identically.
export const EMPTY_REPLY_FALLBACK_COPY =
  "This turn finished without a written reply.";
