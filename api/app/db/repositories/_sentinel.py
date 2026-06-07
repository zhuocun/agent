"""Shared PATCH-update sentinel.

Nullable columns need a three-valued default: ``None`` is meaningful (clear the
column), so it cannot also mean "leave unchanged."  The ``_Unset`` class and
the singleton ``UNSET`` fill that role.

Before this module, identical ``class _Unset`` / ``_UNSET = _Unset()`` blocks
were copy-pasted into ``conversations``, ``projects``, and ``tags``.  Importing
from one place keeps the pattern DRY and the ``isinstance`` checks consistent.
"""

from __future__ import annotations

from typing import Final


class _Unset:
    """Sentinel distinguishing "don't touch" from an explicit ``None``.

    Used as the default for nullable PATCH parameters where ``None`` means
    "clear the column" rather than "leave unchanged."
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "UNSET"


UNSET: Final[_Unset] = _Unset()

__all__ = ["UNSET", "_Unset"]
