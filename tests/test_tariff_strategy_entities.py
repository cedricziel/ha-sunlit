"""Tests for the tariff-strategy entities (select + number).

These exercise:
- update flow: entity → coordinator cache → push
- rollback when the push fails (cache reverts to the previous value)
- socMin < socMax sanity guard on the SOC number entities
- RestoreEntity populates the coordinator cache from the last seen state
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.sunlit.api_client import SunlitApiError
from custom_components.sunlit.coordinators.strategy import (
    SunlitStrategyHistoryCoordinator,
)
from custom_components.sunlit.number import SunlitTariffSocNumber
from custom_components.sunlit.select import SunlitTariffStrategySelect


def _make_coord(hass: HomeAssistant) -> SunlitStrategyHistoryCoordinator:
    api = AsyncMock()
    api.set_tariff_strategy.return_value = {
        "code": 0,
        "responseTime": 1716800000000,
        "message": {"DE": "Ok"},
        "content": None,
    }
    api.fetch_space_strategy_history.return_value = {"content": []}
    coord = SunlitStrategyHistoryCoordinator(
        hass=hass,
        api_client=api,
        family_id="34038",
        family_name="Garage",
    )
    # Don't schedule the periodic refresh timer during entity tests.
    coord.async_request_refresh = AsyncMock()
    return coord


def _make_select(coord, band: str = "low") -> SunlitTariffStrategySelect:
    entity = SunlitTariffStrategySelect(
        coordinator=coord,
        entry_id="test_entry_id",
        family_id="34038",
        family_name="Garage",
        band=band,
    )
    entity.hass = coord.hass
    entity.async_write_ha_state = MagicMock()
    return entity


def _make_number(coord, band: str, field: str) -> SunlitTariffSocNumber:
    entity = SunlitTariffSocNumber(
        coordinator=coord,
        entry_id="test_entry_id",
        family_id="34038",
        family_name="Garage",
        band=band,
        field=field,
        name_suffix=f"{band} {field}",
    )
    entity.hass = coord.hass
    entity.async_write_ha_state = MagicMock()
    return entity


# ---------- select rollback ----------


async def test_select_rolls_back_on_push_failure(
    hass: HomeAssistant, enable_custom_integrations
):
    coord = _make_coord(hass)
    coord.api_client.set_tariff_strategy.side_effect = SunlitApiError(
        "API error: Service temporarily unavailable"
    )
    entity = _make_select(coord, band="high")

    previous = coord.tariff_setup["high"]["strategy"]

    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("EnergyStorageOnly")

    # Cache must have been reverted, not stuck on the rejected value.
    assert coord.tariff_setup["high"]["strategy"] == previous


async def test_select_invalid_option_raises_without_pushing(
    hass: HomeAssistant, enable_custom_integrations
):
    coord = _make_coord(hass)
    entity = _make_select(coord)

    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("not-a-real-strategy")

    coord.api_client.set_tariff_strategy.assert_not_called()


# ---------- number rollback + socMin < socMax ----------


async def test_number_socmin_must_be_below_socmax(
    hass: HomeAssistant, enable_custom_integrations
):
    coord = _make_coord(hass)
    # Force a known socMax so the assertion is deterministic.
    coord.update_tariff_setup_field("low", "socMax", 80)
    entity = _make_number(coord, band="low", field="socMin")

    with pytest.raises(HomeAssistantError, match="must be < socMax"):
        await entity.async_set_native_value(80)

    # Nothing was pushed.
    coord.api_client.set_tariff_strategy.assert_not_called()


async def test_number_socmax_must_be_above_socmin(
    hass: HomeAssistant, enable_custom_integrations
):
    coord = _make_coord(hass)
    coord.update_tariff_setup_field("low", "socMin", 20)
    entity = _make_number(coord, band="low", field="socMax")

    with pytest.raises(HomeAssistantError, match="must be > socMin"):
        await entity.async_set_native_value(20)

    # Fail-fast: must abort before any API call, same as the socMin test.
    coord.api_client.set_tariff_strategy.assert_not_called()


async def test_number_rolls_back_on_push_failure(
    hass: HomeAssistant, enable_custom_integrations
):
    coord = _make_coord(hass)
    coord.update_tariff_setup_field("low", "socMin", 1)
    coord.update_tariff_setup_field("low", "socMax", 90)
    coord.api_client.set_tariff_strategy.side_effect = SunlitApiError(
        "API error: Service temporarily unavailable"
    )
    entity = _make_number(coord, band="low", field="socMin")

    previous = coord.tariff_setup["low"]["socMin"]

    with pytest.raises(HomeAssistantError):
        await entity.async_set_native_value(15)

    assert coord.tariff_setup["low"]["socMin"] == previous


async def test_number_happy_path_writes_cache(
    hass: HomeAssistant, enable_custom_integrations
):
    coord = _make_coord(hass)
    coord.update_tariff_setup_field("low", "socMin", 1)
    coord.update_tariff_setup_field("low", "socMax", 90)
    entity = _make_number(coord, band="low", field="socMin")

    await entity.async_set_native_value(20)

    assert coord.tariff_setup["low"]["socMin"] == 20
    coord.api_client.set_tariff_strategy.assert_called_once()


# ---------- RestoreEntity populates cache ----------


async def test_select_restore_writes_cache_on_added_to_hass(
    hass: HomeAssistant, enable_custom_integrations
):
    coord = _make_coord(hass)
    entity = _make_select(coord, band="low")
    last_state = MagicMock()
    last_state.state = "EnergyStorageOnly"

    # Skip CoordinatorEntity.async_added_to_hass() — it would attach a refresh
    # listener and leave a lingering 5-min timer in the test loop. We only
    # care about the restore branch here.
    with patch.object(
        SunlitTariffStrategySelect.__bases__[0],
        "async_added_to_hass",
        new=AsyncMock(),
    ), patch.object(
        SunlitTariffStrategySelect,
        "async_get_last_state",
        new=AsyncMock(return_value=last_state),
    ):
        await entity.async_added_to_hass()

    assert coord.tariff_setup["low"]["strategy"] == "EnergyStorageOnly"


async def test_number_restore_writes_cache_on_added_to_hass(
    hass: HomeAssistant, enable_custom_integrations
):
    coord = _make_coord(hass)
    entity = _make_number(coord, band="high", field="socMin")
    last_state = MagicMock()
    last_state.state = "25"

    with patch.object(
        SunlitTariffSocNumber.__bases__[0],
        "async_added_to_hass",
        new=AsyncMock(),
    ), patch.object(
        SunlitTariffSocNumber,
        "async_get_last_state",
        new=AsyncMock(return_value=last_state),
    ):
        await entity.async_added_to_hass()

    assert coord.tariff_setup["high"]["socMin"] == 25


async def test_number_restore_ignores_unparseable_state(
    hass: HomeAssistant, enable_custom_integrations
):
    coord = _make_coord(hass)
    original = coord.tariff_setup["high"]["socMin"]
    entity = _make_number(coord, band="high", field="socMin")
    last_state = MagicMock()
    last_state.state = "not-a-number"

    with patch.object(
        SunlitTariffSocNumber.__bases__[0],
        "async_added_to_hass",
        new=AsyncMock(),
    ), patch.object(
        SunlitTariffSocNumber,
        "async_get_last_state",
        new=AsyncMock(return_value=last_state),
    ):
        await entity.async_added_to_hass()

    # Stays on the default — bad state didn't poison the cache.
    assert coord.tariff_setup["high"]["socMin"] == original
