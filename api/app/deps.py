"""Re-export common dependency providers in one place.

Keeps route imports short and creates a single seam to swap dependency
implementations in tests.
"""

from __future__ import annotations

from app.auth.dependency import current_user
from app.db.session import get_db

__all__ = ["current_user", "get_db"]
