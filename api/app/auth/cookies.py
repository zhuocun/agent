"""itsdangerous signer wrapper + cookie kwargs.

`COOKIE_KW` is built per-call from settings so test overrides take effect.
"""

from __future__ import annotations

from typing import Any, Literal

from itsdangerous import BadSignature, URLSafeSerializer

from app.config import Settings

COOKIE_NAME_DEFAULT = "sid"


def build_signer(secret: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret, salt="session")


def cookie_kwargs(settings: Settings) -> dict[str, Any]:
    samesite: Literal["lax", "strict", "none"] = settings.cookie_samesite
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": samesite,
        "path": "/",
        "max_age": settings.session_max_age_seconds,
    }


def load_session_id(signer: URLSafeSerializer, raw: str) -> str | None:
    """Return the signed session id or None if the cookie is malformed."""
    try:
        loaded = signer.loads(raw)
    except BadSignature:
        return None
    if not isinstance(loaded, str):
        return None
    return loaded


def dump_session_id(signer: URLSafeSerializer, session_id: str) -> str:
    dumped = signer.dumps(session_id)
    # URLSafeSerializer returns str in modern itsdangerous; coerce defensively.
    return dumped if isinstance(dumped, str) else dumped.decode("utf-8")
