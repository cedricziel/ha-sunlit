"""Tests for the tariff-strategy push path on the strategy coordinator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.sunlit.api_client import SunlitApiError
from custom_components.sunlit.coordinators.strategy import (
    SunlitStrategyHistoryCoordinator,
)


FIXTURES = Path(__file__).parent / "fixtures" / "api"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _make_coordinator(
    hass: HomeAssistant, api_client: AsyncMock
) -> SunlitStrategyHistoryCoordinator:
    return SunlitStrategyHistoryCoordinator(
        hass=hass,
        api_client=api_client,
        family_id="34038",
        family_name="Test Family",
    )


# ---------- update_tariff_setup_field validation ----------


async def test_update_tariff_setup_field_unknown_band_raises(
    hass: HomeAssistant, enable_custom_integrations
):
    """Unknown bands must be rejected so typos don't silently grow the cache."""
    coord = _make_coordinator(hass, AsyncMock())

    with pytest.raises(ValueError, match="Unknown tariff band"):
        coord.update_tariff_setup_field("medium", "strategy", "SmartStrategy")


async def test_update_tariff_setup_field_unknown_field_raises(
    hass: HomeAssistant, enable_custom_integrations
):
    """Unknown fields must be rejected, not stored as a stray dict key."""
    coord = _make_coordinator(hass, AsyncMock())

    with pytest.raises(ValueError, match="Unknown field"):
        coord.update_tariff_setup_field("low", "bogusField", 42)


async def test_update_tariff_setup_field_writes_value(
    hass: HomeAssistant, enable_custom_integrations
):
    """Happy path: valid (band, field) writes through to the cache."""
    coord = _make_coordinator(hass, AsyncMock())

    coord.update_tariff_setup_field("low", "socMin", 5)

    assert coord.tariff_setup["low"]["socMin"] == 5


# ---------- async_push_tariff_setup behaviour ----------


async def test_async_push_sends_full_low_and_high_blocks(
    hass: HomeAssistant, enable_custom_integrations
):
    """Push must always carry both blocks — endpoint is all-or-nothing."""
    api = AsyncMock()
    api.set_tariff_strategy.return_value = _load("tariff_strategy_add_accepted.json")
    api.fetch_space_strategy_history.return_value = {"content": []}
    coord = _make_coordinator(hass, api)
    # Don't schedule the periodic timer in the test.
    coord.async_request_refresh = AsyncMock()

    coord.update_tariff_setup_field("low", "socMin", 5)
    coord.update_tariff_setup_field("high", "socMax", 95)

    await coord.async_push_tariff_setup()

    api.set_tariff_strategy.assert_called_once()
    kwargs = api.set_tariff_strategy.call_args.kwargs or {}
    args = api.set_tariff_strategy.call_args.args
    # Either positional or kwargs — pull out the two blocks robustly.
    low = kwargs.get("low_price_strategy")
    high = kwargs.get("high_price_strategy")
    if low is None and len(args) >= 3:
        low, high = args[1], args[2]
    assert low is not None and high is not None, "both blocks must be sent"
    assert low["socMin"] == 5
    assert high["socMax"] == 95
    # The block must contain *all* fields, not only the changed one.
    assert {"strategy", "socMin", "socMax"}.issubset(low.keys())
    assert {"strategy", "socMin", "socMax"}.issubset(high.keys())


async def test_tariff_setup_property_returns_defensive_copy(
    hass: HomeAssistant, enable_custom_integrations
):
    """Mutating the returned dict must not change the internal cache."""
    coord = _make_coordinator(hass, AsyncMock())
    snapshot = coord.tariff_setup

    snapshot["low"]["socMin"] = 99
    snapshot["high"] = {"hijacked": True}

    # Internal cache stayed untouched
    assert coord.tariff_setup["low"]["socMin"] != 99
    assert "hijacked" not in coord.tariff_setup["high"]


# ---------- 500003 reject case ----------


async def test_async_push_does_not_swallow_api_error(
    hass: HomeAssistant, enable_custom_integrations
):
    """A 500003 (or any other API error) must propagate so callers can roll back."""
    api = AsyncMock()
    api.set_tariff_strategy.side_effect = SunlitApiError(
        "API error: Service temporarily unavailable"
    )
    coord = _make_coordinator(hass, api)

    coord.update_tariff_setup_field("high", "strategy", "EnergyStorageOnly")

    with pytest.raises(SunlitApiError):
        await coord.async_push_tariff_setup()
