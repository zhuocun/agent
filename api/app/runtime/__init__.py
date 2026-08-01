"""Neutral runtime foundations shared by streaming, tools, and agentic code.

Modules here own cross-cutting request-scoped facts — the per-turn database
context (`context`) and one run's accounting (`run_receipt`) — without importing
the provider, streaming, or route layers, so any consumer can depend on them
without creating a cycle.

The package root deliberately re-exports NOTHING. `providers.protocol` imports
`run_receipt` for the `RunCost.receipt` carrier, and importing a submodule runs
this file first: re-exporting `context` here would drag `app.db.session` into
every provider import for no caller's benefit. Import the submodule you need.
"""

from __future__ import annotations
