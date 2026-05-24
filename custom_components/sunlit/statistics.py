"""Historical long-term statistics backfill for Sunlit.

Home Assistant only keeps statistics from the moment a sensor starts recording.
The cloud already holds years of generation & earnings history, exposed by the
``/v1.1/space/statistics/dynamic/earning`` endpoint at year/month/day
granularity. This module walks that history and injects it into HA's long-term
statistics as *external* statistics (``sunlit:<space>_…``) so it shows up in the
Energy Dashboard and Statistics cards without creating any entities.

The import is idempotent: external statistics are keyed by ``start`` time, so
re-running simply overwrites the same daily buckets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import logging
from typing import Any

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .api_client import SunlitApiClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ``mean_type`` (Home Assistant 2025.5+) replaced the deprecated ``has_mean``.
# Stay compatible with the integration's documented minimum HA version.
try:
    from homeassistant.components.recorder.models import StatisticMeanType

    _MEAN_META: dict[str, Any] = {"mean_type": StatisticMeanType.NONE}
except ImportError:  # pragma: no cover - HA < 2025.5
    _MEAN_META = {"has_mean": False}

_DEFAULT_CURRENCY = "EUR"


@dataclass(frozen=True)
class DailyEarning:
    """One day of historical generation and earnings for a space."""

    date: date
    generation_kwh: float
    earnings: float
    currency: str


def _as_float(value: Any) -> float:
    """Coerce an API value to float, defaulting to 0.0."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int | None:
    """Coerce a bucket key to int, or None when not parseable."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _has_data(bucket: dict[str, Any]) -> bool:
    """Return True if a year/month bucket carries any generation or earnings."""
    return (
        _as_float(bucket.get("totalPowerGeneration")) != 0.0
        or _as_float(bucket.get("totalEarnings")) != 0.0
    )


async def async_collect_earning_history(
    api: SunlitApiClient,
    space_id: str | int,
    today: date,
) -> list[DailyEarning]:
    """Walk the earning endpoint (year -> month -> day) into daily buckets.

    Years and months without any data are skipped to avoid pointless requests,
    and buckets in the future (relative to ``today``) are dropped so the current
    month's not-yet-recorded days are not imported as zeros.
    """
    daily: list[DailyEarning] = []

    year_content = await api.fetch_space_statistics_dynamic_earning(space_id)
    for year_bucket in year_content.get("powerEarningsList") or []:
        year = _as_int(year_bucket.get("key"))
        if year is None or year > today.year or not _has_data(year_bucket):
            continue

        month_content = await api.fetch_space_statistics_dynamic_earning(
            space_id, year=year
        )
        for month_bucket in month_content.get("powerEarningsList") or []:
            month = _as_int(month_bucket.get("key"))
            if month is None or not 1 <= month <= 12:
                continue
            if year == today.year and month > today.month:
                continue
            if not _has_data(month_bucket):
                continue

            day_content = await api.fetch_space_statistics_dynamic_earning(
                space_id, year=year, month=month
            )
            for day_bucket in day_content.get("powerEarningsList") or []:
                day = _as_int(day_bucket.get("key"))
                if day is None or not 1 <= day <= 31:
                    continue
                try:
                    bucket_date = date(year, month, day)
                except ValueError:
                    continue
                if bucket_date > today:
                    continue
                daily.append(
                    DailyEarning(
                        date=bucket_date,
                        generation_kwh=_as_float(
                            day_bucket.get("totalPowerGeneration")
                        ),
                        earnings=_as_float(day_bucket.get("totalEarnings")),
                        currency=(day_bucket.get("currency") or "").strip(),
                    )
                )

    daily.sort(key=lambda item: item.date)
    return daily


def build_external_statistics(
    space_id: str | int,
    family_name: str,
    daily: list[DailyEarning],
    currency: str,
) -> list[tuple[StatisticMetaData, list[StatisticData]]]:
    """Turn daily buckets into (metadata, cumulative statistics) pairs.

    Both series are cumulative sums (``has_sum``); the Energy Dashboard derives
    each period's value from the difference of consecutive ``sum`` values.
    """
    energy_meta = StatisticMetaData(
        **_MEAN_META,
        has_sum=True,
        name=f"{family_name} Lifetime Yield (imported history)",
        source=DOMAIN,
        statistic_id=f"{DOMAIN}:{space_id}_lifetime_yield",
        unit_class="energy",
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )
    earnings_meta = StatisticMetaData(
        **_MEAN_META,
        has_sum=True,
        name=f"{family_name} Lifetime Earnings (imported history)",
        source=DOMAIN,
        statistic_id=f"{DOMAIN}:{space_id}_lifetime_earnings",
        unit_class=None,
        unit_of_measurement=currency,
    )

    energy_stats: list[StatisticData] = []
    earnings_stats: list[StatisticData] = []
    running_energy = 0.0
    running_earnings = 0.0
    for item in sorted(daily, key=lambda entry: entry.date):
        start = dt_util.start_of_local_day(item.date)
        running_energy += item.generation_kwh
        running_earnings += item.earnings
        energy_stats.append(
            StatisticData(start=start, state=item.generation_kwh, sum=running_energy)
        )
        earnings_stats.append(
            StatisticData(start=start, state=item.earnings, sum=running_earnings)
        )

    return [(energy_meta, energy_stats), (earnings_meta, earnings_stats)]


async def async_import_family_history(
    hass: HomeAssistant,
    api: SunlitApiClient,
    space_id: str | int,
    family_name: str,
) -> int:
    """Backfill historical generation & earnings statistics for one space.

    Returns the number of days imported.
    """
    today = dt_util.now().date()
    daily = await async_collect_earning_history(api, space_id, today)
    if not daily:
        _LOGGER.warning(
            "No historical earning data returned for space %s (%s)",
            space_id,
            family_name,
        )
        return 0

    currency = next(
        (item.currency for item in reversed(daily) if item.currency),
        _DEFAULT_CURRENCY,
    )
    for metadata, statistics in build_external_statistics(
        space_id, family_name, daily, currency
    ):
        if statistics:
            async_add_external_statistics(hass, metadata, statistics)

    _LOGGER.info(
        "Imported %s day(s) of historical statistics for space %s (%s)",
        len(daily),
        space_id,
        family_name,
    )
    return len(daily)
