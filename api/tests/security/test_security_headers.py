"""Verify the SecurityHeadersMiddleware injects defensive headers."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.parametrize(
    "path",
    ["/healthz", "/api/bootstrap", "/api/status"],
)
async def test_security_headers_present(client: AsyncClient, path: str) -> None:
    resp = await client.get(path)
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in resp.headers["Permissions-Policy"]
    assert "microphone=()" in resp.headers["Permissions-Policy"]
    assert "geolocation=()" in resp.headers["Permissions-Policy"]
    assert "payment=()" in resp.headers["Permissions-Policy"]
