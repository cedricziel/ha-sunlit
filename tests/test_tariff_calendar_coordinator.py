"""Tests for SunlitTariffCalendarCoordinator."""

from datetime import date, timedelta
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest

from custom_components.sunlit.api_client import SunlitApiError
from custom_components.sunlit.coordinators.tariff_calendar import (
    HourlyPrice,
    SunlitTariffCalendarCoordinator,
)


def _content(num_prices: int) -> dict:
    """Build a valid /rabot/day/price response content envelope."""
    return {
        "prices": [
            {
                "hour": h,
                "priceInCentPerKwh": 10.0 + h,
                "avgPriceInCentPerKwh": 12.34,
                "priceTag": "CHEAP" if h % 2 == 0 else "EXPENSIVE",
                "timestamp": f"2026-06-02 {h:02d}:00:00",
            }
            for h in range(num_prices)
        ],
        "utcOffset": "UTC+2",
        "rabotHasContractPrice": None,
    }


@pytest.mark.asyncio
async def test_update_caches_today_and_tomorrow(hass: HomeAssistant):
    """Hourly poll fetches today + tomorrow and caches non-empty responses."""
    api = AsyncMock()
    api.fetch_rabot_day_price = AsyncMock(return_value=_content(24))
    coord = SunlitTariffCalendarCoordinator(
        hass, api_client=api, family_id="34038", family_name="Garage", space_id=34038
    )

    await coord._async_update_data()

    today = dt_util.now().date()
    assert today in coord.daily_prices
    assert today + timedelta(days=1) in coord.daily_prices
    assert len(coord.daily_prices[today]) == 24
    assert api.fetch_rabot_day_price.call_count == 2


@pytest.mark.asyncio
async def test_empty_response_is_not_cached(hass: HomeAssistant):
    """Future days return prices=[] until publication; don't pin a false miss."""
    api = AsyncMock()
    api.fetch_rabot_day_price = AsyncMock(
        side_effect=[_content(24), {"prices": [], "utcOffset": "UTC+2"}]
    )
    coord = SunlitTariffCalendarCoordinator(
        hass, api_client=api, family_id="34038", family_name="Garage", space_id=34038
    )

    await coord._async_update_data()

    today = dt_util.now().date()
    assert today in coord.daily_prices
    assert (today + timedelta(days=1)) not in coord.daily_prices


@pytest.mark.asyncio
async def test_api_error_is_swallowed(hass: HomeAssistant):
    """An API error on one day doesn't abort the whole refresh."""
    api = AsyncMock()
    api.fetch_rabot_day_price = AsyncMock(
        side_effect=[_content(24), SunlitApiError("boom")]
    )
    coord = SunlitTariffCalendarCoordinator(
        hass, api_client=api, family_id="34038", family_name="Garage", space_id=34038
    )

    await coord._async_update_data()  # must not raise

    today = dt_util.now().date()
    assert today in coord.daily_prices


@pytest.mark.asyncio
async def test_async_ensure_day_hits_cache(hass: HomeAssistant):
    """Cached days are returned without re-hitting the API."""
    api = AsyncMock()
    api.fetch_rabot_day_price = AsyncMock(return_value=_content(24))
    coord = SunlitTariffCalendarCoordinator(
        hass, api_client=api, family_id="34038", family_name="Garage", space_id=34038
    )
    target = dt_util.now().date() - timedelta(days=3)
    coord.daily_prices[target] = [HourlyPrice(0, 5.0, 5.0, "CHEAP")]

    result = await coord.async_ensure_day(target)

    assert result and result[0].tag == "CHEAP"
    api.fetch_rabot_day_price.assert_not_called()


@pytest.mark.asyncio
async def test_async_ensure_day_fetches_when_missing(hass: HomeAssistant):
    """Uncached days inside the horizon trigger one fetch."""
    api = AsyncMock()
    api.fetch_rabot_day_price = AsyncMock(return_value=_content(24))
    coord = SunlitTariffCalendarCoordinator(
        hass, api_client=api, family_id="34038", family_name="Garage", space_id=34038
    )
    target = dt_util.now().date() - timedelta(days=30)

    result = await coord.async_ensure_day(target)

    assert len(result) == 24
    api.fetch_rabot_day_price.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_ensure_day_clamps_outside_horizon(hass: HomeAssistant):
    """Beyond ±the verified window we don't waste an API call."""
    api = AsyncMock()
    api.fetch_rabot_day_price = AsyncMock(return_value=_content(24))
    coord = SunlitTariffCalendarCoordinator(
        hass, api_client=api, family_id="34038", family_name="Garage", space_id=34038
    )
    too_old = dt_util.now().date() - timedelta(days=400)
    too_future = dt_util.now().date() + timedelta(days=3)

    assert await coord.async_ensure_day(too_old) == []
    assert await coord.async_ensure_day(too_future) == []
    api.fetch_rabot_day_price.assert_not_called()


def test_parse_prices_skips_invalid_entries():
    """Bad rows are dropped silently; valid ones survive and sort by hour."""
    content = {
        "prices": [
            {"hour": "bad", "priceInCentPerKwh": 1.0, "priceTag": "CHEAP"},  # bad hour
            {"hour": 5, "priceInCentPerKwh": "nope", "priceTag": "CHEAP"},  # bad price
            {"hour": 24, "priceInCentPerKwh": 1.0, "priceTag": "CHEAP"},  # out of range
            {"hour": 3, "priceInCentPerKwh": 2.0, "priceTag": ""},  # empty tag
            {"hour": 7, "priceInCentPerKwh": 3.5, "priceTag": "CHEAP"},
            {"hour": 1, "priceInCentPerKwh": 1.5, "priceTag": "EXPENSIVE"},
        ]
    }
    parsed = SunlitTariffCalendarCoordinator._parse_prices(content)
    assert [p.hour for p in parsed] == [1, 7]
    assert parsed[0].tag == "EXPENSIVE"
    assert parsed[1].price_ct_per_kwh == 3.5


def test_parse_prices_handles_missing_prices_key():
    assert SunlitTariffCalendarCoordinator._parse_prices({}) == []
    assert SunlitTariffCalendarCoordinator._parse_prices({"prices": None}) == []
