"""Model & data-policy directory tests (PRD 05 §4.5 / PRD 07 §5).

The `/api/models/directory` catalog must mirror the live registry exactly: all
provider routes (including the pending, null-policy Gemini route), each route's
data policy, and per-tier prices/labels straight from `TIER_BINDINGS`. Nothing
is hardcoded — these assertions pin the registry-derived values.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_directory_lists_all_registry_providers_with_policies_and_prices(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/models/directory")
    assert resp.status_code == 200, resp.text
    entries = resp.json()
    by_id = {e["providerId"]: e for e in entries}
    # Every registry route is surfaced, including pending/unavailable ones.
    assert set(by_id) == {"deepseek", "anthropic", "openai", "gemini", "xai", "fake"}

    # CamelModel entry shape.
    assert set(by_id["deepseek"].keys()) == {
        "providerId",
        "label",
        "status",
        "defaultRouteEligible",
        "dataPolicy",
        "tiers",
    }

    # DeepSeek — policy fields straight from the registry (never hardcoded here:
    # these mirror PROVIDER_ROUTES[deepseek].data_policy).
    deepseek = by_id["deepseek"]
    assert deepseek["label"] == "DeepSeek"
    assert deepseek["status"] == "available"
    assert deepseek["defaultRouteEligible"] is True
    policy = deepseek["dataPolicy"]
    assert policy is not None
    assert policy["trainsOnData"] is True
    assert policy["dataResidency"] == "China"
    assert policy["policyLabel"] == "May train unless opted out; China data residency"

    # DeepSeek `fast` tier price/label come straight from TIER_BINDINGS.
    tiers_by_id = {t["tierId"]: t for t in deepseek["tiers"]}
    assert "fast" in tiers_by_id
    fast = tiers_by_id["fast"]
    assert fast["modelLabel"] == "DeepSeek V4 Flash"
    assert fast["listPriceInPerM"] == 0.14
    assert fast["listPriceOutPerM"] == 0.28
    assert fast["supportsWebSearch"] is True
    # `modalitiesOut` (D22 precondition) is surfaced per directory tier. Every
    # wired route is text-out today, so every tier reports exactly ["text"].
    for tier in deepseek["tiers"]:
        assert tier["modalitiesOut"] == ["text"]

    # Pro tier carries the frontier price.
    assert tiers_by_id["pro"]["listPriceInPerM"] == 0.435
    assert tiers_by_id["pro"]["modelLabel"] == "DeepSeek V4 Pro"


async def test_directory_pending_route_has_null_policy_and_no_tiers(
    client: AsyncClient,
) -> None:
    entries = (await client.get("/api/models/directory")).json()
    gemini = next(e for e in entries if e["providerId"] == "gemini")
    # Pending roadmap route: never a guessed policy, never fabricated tiers.
    assert gemini["status"] == "pending"
    assert gemini["dataPolicy"] is None
    assert gemini["defaultRouteEligible"] is False
    assert gemini["tiers"] == []

    # xAI Grok (T07) is the same shape: a pending roadmap route with no policy
    # and no fabricated tiers until an adapter + data-policy sign-off land.
    xai = next(e for e in entries if e["providerId"] == "xai")
    assert xai["label"] == "Grok (xAI)"
    assert xai["status"] == "pending"
    assert xai["dataPolicy"] is None
    assert xai["defaultRouteEligible"] is False
    assert xai["tiers"] == []


async def test_directory_anthropic_policy_from_registry(
    client: AsyncClient,
) -> None:
    entries = (await client.get("/api/models/directory")).json()
    anthropic = next(e for e in entries if e["providerId"] == "anthropic")
    policy = anthropic["dataPolicy"]
    assert policy is not None
    assert policy["trainsOnData"] is False
    assert policy["dataResidency"] == "US/EU"
    assert policy["retentionDays"] == 30
    assert policy["zeroDataRetentionAvailable"] is True
