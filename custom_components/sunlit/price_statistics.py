"""Backfill historical Rabot price statistics onto the electricity_price sensor.

Companion to ``calendar.py`` — the calendar serves past events on demand from
``rabot/day/price``, but recorder long-term statistics for the
``electricity_price`` sensor only start accumulating when the integration
records them. This module walks the verified backward horizon (~365 days) and
imports per-hour MEASUREMENT statistics (``mean = min = max = hourly price``)
onto the entity's own statistic_id via :func:`async_import_statistics`.

The import is idempotent: per-hour buckets are keyed by ``start``, so re-running
just overwrites the same rows. The service is opt-in (user-invoked) — startup
stays minimal.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.components.recorder import DOMAIN as RECORDER_DOMAIN
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinators.tariff_calendar import (
    MAX_PAST_DAYS,
    HourlyPrice,
    SunlitTariffCalendarCoordinator,
)

_LOGGER = logging.getLogger(__name__)

# Backfill ceiling (matches the verified horizon of rabot/day/price).
DEFAULT_DAYS = MAX_PAST_DAYS
MIN_DAYS = 1
MAX_DAYS = MAX_PAST_DAYS

# ``mean_type`` (HA 2025.5+) replaced ``has_mean``; stay compatible with the
# minimum HA version the integration supports.
try:
    from homeassistant.components.recorder.models import StatisticMeanType

    _MEAN_META: dict[str, Any] = {"mean_type": StatisticMeanType.ARITHMETIC}
except ImportError:  # pragma: no cover - HA < 2025.5
    _MEAN_META = {"has_mean": True}


def _clamp_days(value: Any) -> int:
    """Coerce ``days`` to int and clamp to the supported range."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return max(MIN_DAYS, min(MAX_DAYS, n))


def resolve_price_statistic_id(
    hass: HomeAssistant, family_name: str, family_id: str | int
) -> str | None:
    """Resolve the live entity_id for the family's electricity_price sensor.

    Mirrors the user-renameable-entity_id approach already used in #191:
    look up the entity by stable unique_id rather than constructing a slug.
    """
    unique_id = (
        f"sunlit_{family_name.lower().replace(' ', '_')}_{family_id}_electricity_price"
    )
    return er.async_get(hass).async_get_entity_id(SENSOR_DOMAIN, DOMAIN, unique_id)


def build_price_statistics(
    statistic_id: str,
    daily_prices: dict[date, list[HourlyPrice]],
) -> tuple[StatisticMetaData, list[StatisticData]]:
    """Build (metadata, hourly statistic rows) for the price sensor."""
    metadata = StatisticMetaData(
        **_MEAN_META,
        has_sum=False,
        name=None,  # HA uses the entity's friendly name
        source=RECORDER_DOMAIN,
        statistic_id=statistic_id,
        unit_class=None,
        unit_of_measurement="ct/kWh",
    )
    statistics: list[StatisticData] = []
    for day in sorted(daily_prices):
        midnight = dt_util.start_of_local_day(day)
        for entry in sorted(daily_prices[day], key=lambda p: p.hour):
            start = midnight + timedelta(hours=entry.hour)
            price = entry.price_ct_per_kwh
            statistics.append(
                StatisticData(start=start, mean=price, min=price, max=price)
            )
    return metadata, statistics


async def async_collect_price_history(
    coordinator: SunlitTariffCalendarCoordinator,
    days: int,
    *,
    now: datetime | None = None,
) -> dict[date, list[HourlyPrice]]:
    """Walk ``days`` days back, fetching missing days via the coordinator.

    Already-cached days are reused (the calendar's on-demand fetches double as
    cache warming). Days outside the verified horizon are skipped silently.
    """
    if now is None:
        now = dt_util.now()
    today = now.date()
    collected: dict[date, list[HourlyPrice]] = {}
    # Walk oldest -> newest so the cumulative cache builds naturally.
    for offset in range(days, 0, -1):
        day = today - timedelta(days=offset)
        prices = await coordinator.async_ensure_day(day)
        if prices:
            collected[day] = prices
    return collected


async def async_import_family_price_history(
    hass: HomeAssistant,
    coordinator: SunlitTariffCalendarCoordinator,
    days: int = DEFAULT_DAYS,
) -> int:
    """Backfill ``electricity_price`` MEASUREMENT statistics for one family.

    Returns the number of hourly statistic rows imported.
    """
    statistic_id = resolve_price_statistic_id(
        hass, coordinator.family_name, coordinator.family_id
    )
    if not statistic_id:
        _LOGGER.warning(
            "electricity_price entity not registered for %s — skipping backfill",
            coordinator.family_name,
        )
        return 0

    collected = await async_collect_price_history(coordinator, _clamp_days(days))
    if not collected:
        _LOGGER.info(
            "No historical Rabot prices available for %s in the last %s day(s)",
            coordinator.family_name,
            days,
        )
        return 0

    metadata, statistics = build_price_statistics(statistic_id, collected)
    async_import_statistics(hass, metadata, statistics)
    _LOGGER.info(
        "Imported %s hourly price statistics rows for %s (%s -> %s)",
        len(statistics),
        coordinator.family_name,
        min(collected),
        max(collected),
    )
    return len(statistics)


async def async_import_all_price_history(
    hass: HomeAssistant,
    coordinators: Iterable[SunlitTariffCalendarCoordinator],
    days: int = DEFAULT_DAYS,
) -> int:
    """Backfill prices for every family that has a tariff coordinator."""
    total = 0
    for coordinator in coordinators:
        try:
            total += await async_import_family_price_history(hass, coordinator, days)
        except Exception:
            _LOGGER.exception(
                "Failed to import historical price statistics for %s",
                coordinator.family_name,
            )
    return total
