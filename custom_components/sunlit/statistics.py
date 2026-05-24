"""Long-term statistics for Sunlit: historical backfill + ongoing import.

Home Assistant only keeps statistics from the moment a sensor starts recording.
The cloud already holds years of generation & earnings history, exposed by the
``/v1.1/space/statistics/dynamic/earning`` endpoint at year/month/day
granularity.

Rather than create a parallel ``sunlit:`` external series, this module imports
the history **onto the integration's own entities** — ``lifetime_yield`` and
``lifetime_earnings`` — so pre-install history appears on the exact sensors the
user already has, as one continuous series in the Energy Dashboard and
Statistics cards.

Because those two sensors therefore opt **out** of the recorder's automatic
statistics (no ``state_class`` — see ``entities/helpers.py``), this module owns
their whole statistics series: a one-shot historical backfill
(:func:`async_import_family_history`) plus an hourly point of the live cumulative
value (:func:`async_record_family_live_statistics`) to keep it current.

The cloud reports the *true lifetime cumulative*, so every imported ``sum`` is an
absolute cumulative value; re-running is idempotent (buckets are keyed by start,
and the historical backfill clears the series first).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
import logging
from typing import Any

from homeassistant.components.recorder import DOMAIN as RECORDER_DOMAIN, get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .api_client import SunlitApiClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ``mean_type`` (Home Assistant 2025.5+) replaced the deprecated ``has_mean``.
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


@dataclass(frozen=True)
class _Series:
    """A statistics series owned by the integration for a family sensor."""

    key: str  # sensor key, e.g. "lifetime_yield"
    unit_class: str | None
    unit: str | None  # None -> resolved to the account currency
    value: Callable[[DailyEarning], float]


def _series_specs(currency: str) -> list[_Series]:
    return [
        _Series(
            "lifetime_yield",
            "energy",
            UnitOfEnergy.KILO_WATT_HOUR,
            lambda item: item.generation_kwh,
        ),
        _Series("lifetime_earnings", None, currency, lambda item: item.earnings),
    ]


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


def resolve_statistic_id(
    hass: HomeAssistant, family_name: str, family_id: str | int, key: str
) -> str | None:
    """Resolve the live entity_id for a family sensor (its statistic_id).

    Users can rename entity_ids, so we look it up from the registry by the
    integration's stable unique_id rather than assuming the slug.
    """
    unique_id = f"sunlit_{family_name.lower().replace(' ', '_')}_{family_id}_{key}"
    return er.async_get(hass).async_get_entity_id(SENSOR_DOMAIN, DOMAIN, unique_id)


def _metadata(
    statistic_id: str, unit_class: str | None, unit: str | None
) -> StatisticMetaData:
    """Build entity-statistics metadata (source must be the recorder domain)."""
    return StatisticMetaData(
        **_MEAN_META,
        has_sum=True,
        name=None,  # entity statistics: HA uses the entity's own friendly name
        source=RECORDER_DOMAIN,
        statistic_id=statistic_id,
        unit_class=unit_class,
        unit_of_measurement=unit,
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


def build_series_statistics(
    statistic_id: str,
    series: _Series,
    daily: list[DailyEarning],
) -> tuple[StatisticMetaData, list[StatisticData]]:
    """Build (metadata, cumulative statistics) for one series.

    Values are cumulative sums (``has_sum``); the Energy Dashboard derives each
    period from the difference of consecutive ``sum`` values.
    """
    metadata = _metadata(statistic_id, series.unit_class, series.unit)
    stats: list[StatisticData] = []
    running = 0.0
    for item in sorted(daily, key=lambda entry: entry.date):
        value = series.value(item)
        running += value
        stats.append(
            StatisticData(
                start=dt_util.start_of_local_day(item.date),
                state=value,
                sum=running,
            )
        )
    return metadata, stats


async def async_import_family_history(
    hass: HomeAssistant,
    api: SunlitApiClient,
    family_id: str | int,
    family_name: str,
) -> int:
    """Backfill historical statistics onto the family's lifetime entities.

    Clears each entity's existing (recorder-compiled) statistics first so the
    imported absolute-cumulative series is internally consistent, then imports
    the full history. Returns the number of days imported.
    """
    today = dt_util.now().date()
    daily = await async_collect_earning_history(api, family_id, today)
    if not daily:
        _LOGGER.warning(
            "No historical earning data returned for space %s (%s)",
            family_id,
            family_name,
        )
        return 0

    currency = next(
        (item.currency for item in reversed(daily) if item.currency),
        _DEFAULT_CURRENCY,
    )
    recorder = get_instance(hass)
    imported = 0
    for series in _series_specs(currency):
        statistic_id = resolve_statistic_id(hass, family_name, family_id, series.key)
        if not statistic_id:
            _LOGGER.warning(
                "Cannot backfill %s for space %s: entity not found",
                series.key,
                family_id,
            )
            continue
        # Replace any recorder-compiled stats so the absolute-cumulative series
        # we import is not interleaved with relative-sum buckets.
        recorder.async_clear_statistics([statistic_id])
        metadata, statistics = build_series_statistics(statistic_id, series, daily)
        async_import_statistics(hass, metadata, statistics)
        imported = max(imported, len(statistics))

    _LOGGER.info(
        "Imported %s day(s) of historical statistics for space %s (%s)",
        imported,
        family_id,
        family_name,
    )
    return imported


@callback
def async_record_family_live_statistics(
    hass: HomeAssistant, family_coordinator: Any
) -> None:
    """Append the current hour's cumulative point for the lifetime entities.

    Called hourly. Because these sensors have no ``state_class``, the recorder
    no longer compiles their statistics, so this keeps the integration-owned
    series current using the already-polled live cumulative values.
    """
    data = family_coordinator.data or {}
    family_id = family_coordinator.family_id
    family_name = family_coordinator.family_name
    currency = data.get("currency") or _DEFAULT_CURRENCY
    hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)

    for series in _series_specs(currency):
        value = data.get(series.key)
        if not isinstance(value, (int, float)):
            continue
        statistic_id = resolve_statistic_id(hass, family_name, family_id, series.key)
        if not statistic_id:
            continue
        metadata = _metadata(statistic_id, series.unit_class, series.unit)
        async_import_statistics(
            hass,
            metadata,
            [StatisticData(start=hour, state=float(value), sum=float(value))],
        )
