"""Neutral runtime foundations shared by streaming, tools, and agentic code.

Modules here own cross-cutting request-scoped facts (database context today)
without importing the provider, streaming, or route layers, so any consumer can
depend on them without creating a cycle.
"""

from __future__ import annotations

from app.runtime.context import RuntimeContext, derive_session_factory

__all__ = ["RuntimeContext", "derive_session_factory"]
