"""Security-response-headers middleware.

Injects a minimal set of defensive headers on every response to mitigate
MIME-sniffing, clickjacking, and information-leakage risks:

- ``X-Content-Type-Options: nosniff`` — prevents browsers from MIME-sniffing
  a response away from the declared Content-Type.
- ``X-Frame-Options: DENY`` — blocks the page from being rendered in a frame,
  iframe, or object on any origin (clickjacking defense).
- ``Referrer-Policy: strict-origin-when-cross-origin`` — limits the Referer
  header to origin-only on cross-origin requests and full URL same-origin.
- ``Permissions-Policy`` — disables sensitive browser APIs (camera, microphone,
  geolocation, payment) that this application never uses.

``Strict-Transport-Security`` is deliberately NOT set here: the Fly.io and
Vercel reverse proxies each inject their own HSTS headers, and setting a
competing value in the app could create confusing precedence issues or
prevent local HTTP dev. Let the edge handle HSTS.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject hardened response headers on every HTTP response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        return response
