"""Tariff calendar coordinator for the Rabot day-ahead price feed.

Polls ``rabot/day/price`` for today and tomorrow once per hour and caches the
parsed hourly prices in memory. The calendar entity uses the cache for its
``event`` property and calls :meth:`async_ensure_day` from
``async_get_events`` to lazily fetch any past day the dashboard scrolls to.

Verified behaviour of the upstream endpoint (see ``scripts/probe-rabot.sh``):

- The data is **not** gated on ``rabotHasContract``.
- Forward horizon: today + tomorrow once EPEX publishes (~13:00 CET).
- Backward horizon: roughly the last 12 months (fixed start, grows daily).
- Out-of-window days return ``code=0`` with ``prices=[]`` — no error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from ..api_client import SunlitApiClient, SunlitApiError

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(hours=1)

# The endpoint's verified horizon (see module docstring). Used to clamp the
# range the calendar will ever try to fetch from rabot/day/price.
MAX_FUTURE_DAYS = 1
MAX_PAST_DAYS = 365


@dataclass(frozen=True)
class HourlyPrice:
    """One hour of Rabot day-ahead pricing."""

    hour: int  # 0..23 (local)
    price_ct_per_kwh: float
    avg_ct_per_kwh: float
    tag: str  # VERY_CHEAP | CHEAP | NORMAL | EXPENSIVE | VERY_EXPENSIVE


class SunlitTariffCalendarCoordinator(
    DataUpdateCoordinator[dict[date, list[HourlyPrice]]]
):
    """Fetch + cache Rabot day-ahead prices for the tariff calendars."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: SunlitApiClient,
        family_id: str,
        family_name: str,
        space_id: int | str,
    ) -> None:
        """Initialize the coordinator (one per family)."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"Sunlit Tariff Calendar {family_name}",
            update_interval=UPDATE_INTERVAL,
        )
        self.api_client = api_client
        self.family_id = family_id
        self.family_name = family_name
        self.space_id = space_id
        self.daily_prices: dict[date, list[HourlyPrice]] = {}

    async def _async_update_data(self) -> dict[date, list[HourlyPrice]]:
        """Refresh today and tomorrow on every hourly tick.

        Tomorrow returns an empty list until EPEX publishes day-ahead prices
        around 13:00 local time; that's expected and not an error.
        """
        today = dt_util.now().date()
        for day in (today, today + timedelta(days=1)):
            try:
                await self._fetch_day(day)
            except SunlitApiError as err:
                _LOGGER.warning(
                    "Could not fetch Rabot prices for %s (%s): %s",
                    day,
                    self.family_name,
                    err,
                )
        return self.daily_prices

    async def async_ensure_day(self, day: date) -> list[HourlyPrice]:
        """Return prices for ``day`` from cache, fetching once if missing.

        Days outside the verified rabot/day/price horizon are not fetched
        (the API would respond with an empty list anyway).
        """
        if day in self.daily_prices:
            return self.daily_prices[day]
        today = dt_util.now().date()
        if day < today - timedelta(days=MAX_PAST_DAYS):
            return []
        if day > today + timedelta(days=MAX_FUTURE_DAYS):
            return []
        try:
            await self._fetch_day(day)
        except SunlitApiError as err:
            _LOGGER.warning(
                "Could not fetch Rabot prices for %s (%s): %s",
                day,
                self.family_name,
                err,
            )
        return self.daily_prices.get(day, [])

    async def _fetch_day(self, day: date) -> None:
        """Fetch one day and parse it into the cache (no-op on empty)."""
        day_str = day.isoformat()
        content = await self.api_client.fetch_rabot_day_price(
            self.space_id, day_str, show_tax=True, show_strategy=False
        )
        prices = self._parse_prices(content)
        # An empty list means "no data published yet" (future) or "outside
        # archive" (past). Don't cache empties — let the next poll retry
        # tomorrow (the most useful case) without sticking to a false miss.
        if prices:
            self.daily_prices[day] = prices

    @staticmethod
    def _parse_prices(content: dict[str, Any]) -> list[HourlyPrice]:
        """Parse the rabot/day/price ``content`` envelope into HourlyPrice list."""
        raw = content.get("prices") or []
        parsed: list[HourlyPrice] = []
        for entry in raw:
            try:
                hour = int(entry["hour"])
            except (KeyError, TypeError, ValueError):
                continue
            if not 0 <= hour <= 23:
                continue
            tag = entry.get("priceTag")
            if not isinstance(tag, str) or not tag:
                continue
            try:
                price = float(entry["priceInCentPerKwh"])
            except (KeyError, TypeError, ValueError):
                continue
            try:
                avg = float(entry.get("avgPriceInCentPerKwh") or 0.0)
            except (TypeError, ValueError):
                avg = 0.0
            parsed.append(
                HourlyPrice(
                    hour=hour,
                    price_ct_per_kwh=price,
                    avg_ct_per_kwh=avg,
                    tag=tag,
                )
            )
        parsed.sort(key=lambda p: p.hour)
        return parsed
