"""Tests for the cloud→HA tariff readback path.

Cedric's PR #201 review (item 1) asked for:
  - find the GET-style endpoint the app uses to render the tariff setup
  - add it to the api client
  - have the coordinator's _async_update_data reconcile its cache from it
  - that makes the cache cloud-authoritative and the rollback path correct
    rather than best-effort

The endpoint turned out to be POST /v1.8/strategy/setting/detail with
strategyType=TariffStrategy. The fixture mirrors a real captured response.
"""

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
    coord = SunlitStrategyHistoryCoordinator(
        hass=hass,
        api_client=api_client,
        family_id="40566",
        family_name="Balkon",
    )
    coord.async_request_refresh = AsyncMock()
    return coord


def _api_with_tariff_active() -> AsyncMock:
    """Wire up an api client whose readback returns a known tariff setup."""
    api = AsyncMock()
    raw = _load("strategy_setting_detail_tariff_active.json")
    tariff = raw["content"]["tariffStrategy"]
    api.fetch_tariff_setup.return_value = {
        "low": tariff["lowPriceStrategy"],
        "high": tariff["highPriceStrategy"],
        "enableSwitchNotice": tariff["enableSwitchNotice"],
    }
    api.fetch_space_strategy_history.return_value = {"content": []}
    return api


# ---------- happy path: cache wins back from cloud ----------


async def test_readback_overwrites_divergent_cache(
    hass: HomeAssistant, enable_custom_integrations
):
    """If the cache says one thing and the cloud says another, cloud wins.

    This is the core scenario Cedric's review asked us to cover: the user
    just edited the strategy in the SunEnergyXT app, the cloud now reflects
    that, but our HA cache still holds the previous values. After the next
    coordinator refresh the cache must mirror the cloud.
    """
    api = _api_with_tariff_active()
    coord = _make_coordinator(hass, api)

    # Pre-populate the cache with values different from what the cloud has.
    coord.update_tariff_setup_field("low", "socMin", 50)
    coord.update_tariff_setup_field("low", "socMax", 60)
    coord.update_tariff_setup_field("high", "strategy", "Manual")
    coord.update_tariff_setup_field("high", "socMin", 80)

    await coord._async_update_data()

    # Cloud values (from the fixture) should now sit in the cache.
    assert coord.tariff_setup["low"]["strategy"] == "EnergyStorageOnly"
    assert coord.tariff_setup["low"]["socMin"] == 1
    assert coord.tariff_setup["low"]["socMax"] == 90
    assert coord.tariff_setup["high"]["strategy"] == "SmartStrategy"
    assert coord.tariff_setup["high"]["socMin"] == 10
    assert coord.tariff_setup["high"]["socMax"] == 100


async def test_readback_called_with_family_id(
    hass: HomeAssistant, enable_custom_integrations
):
    """The coordinator must read back its own family — verifies wiring."""
    api = _api_with_tariff_active()
    coord = _make_coordinator(hass, api)

    await coord._async_update_data()

    api.fetch_tariff_setup.assert_called_once_with("40566")


# ---------- defensive: missing / disabled / failing readback ----------


async def test_readback_returning_none_leaves_cache_untouched(
    hass: HomeAssistant, enable_custom_integrations
):
    """No tariff strategy configured on cloud side: cache must keep its values.

    This is the 'fresh install' case — the user has never configured a
    tariff strategy yet. We must not clobber the defaults with empty data.
    """
    api = AsyncMock()
    api.fetch_tariff_setup.return_value = None
    api.fetch_space_strategy_history.return_value = {"content": []}
    coord = _make_coordinator(hass, api)

    coord.update_tariff_setup_field("low", "socMin", 42)

    await coord._async_update_data()

    assert coord.tariff_setup["low"]["socMin"] == 42


async def test_readback_api_error_does_not_break_history_fetch(
    hass: HomeAssistant, enable_custom_integrations
):
    """A failing readback must not abort the regular history update.

    History data is what surfaces on the dashboard tile; the readback is
    only for cache sanity. A flaky readback shouldn't take down the tile.
    """
    api = AsyncMock()
    api.fetch_tariff_setup.side_effect = SunlitApiError("readback boom")
    api.fetch_space_strategy_history.return_value = {
        "content": [
            {
                "modifyDate": 1780000000000,
                "strategy": "TariffStrategy",
                "status": "ACTIVE",
            }
        ]
    }
    coord = _make_coordinator(hass, api)

    data = await coord._async_update_data()

    assert "strategy" in data
    assert data["strategy"]["last_strategy_type"] == "TariffStrategy"


async def test_readback_skips_none_fields(
    hass: HomeAssistant, enable_custom_integrations
):
    """Cloud sometimes reports a field as null — keep our cached value then.

    Captured responses regularly carry e.g. ``socMin: null`` in the
    high-price block depending on strategy type. Treating null as
    'overwrite' would zero out the cache; we instead treat null as
    'cloud has no opinion here'.
    """
    api = AsyncMock()
    # Construct a readback where socMin is null — must not overwrite cache.
    api.fetch_tariff_setup.return_value = {
        "low": {
            "strategy": "EnergyStorageOnly",
            "socMin": None,
            "socMax": 90,
            "defaultExpectInverterOutput": 300.0,
        },
        "high": {
            "strategy": "SmartStrategy",
            "socMin": None,
            "socMax": 100,
        },
        "enableSwitchNotice": True,
    }
    api.fetch_space_strategy_history.return_value = {"content": []}
    coord = _make_coordinator(hass, api)

    coord.update_tariff_setup_field("low", "socMin", 5)
    coord.update_tariff_setup_field("high", "socMin", 15)

    await coord._async_update_data()

    # socMin stayed because cloud sent null; socMax overwritten because cloud sent value.
    assert coord.tariff_setup["low"]["socMin"] == 5
    assert coord.tariff_setup["low"]["socMax"] == 90
    assert coord.tariff_setup["high"]["socMin"] == 15
    assert coord.tariff_setup["high"]["socMax"] == 100
