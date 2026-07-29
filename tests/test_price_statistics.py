"""Tests for the Rabot price-history backfill."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.util import dt as dt_util
import pytest

from custom_components.sunlit.coordinators.tariff_calendar import HourlyPrice
from custom_components.sunlit.price_statistics import (
    DEFAULT_DAYS,
    MAX_DAYS,
    MIN_DAYS,
    _clamp_days,
    async_collect_price_history,
    async_import_all_price_history,
    async_import_family_price_history,
    build_price_statistics,
)

# ---------------------------------------------------------------------------
# _clamp_days
# ---------------------------------------------------------------------------


def test_clamp_days_clamps_below_min():
    assert _clamp_days(0) == MIN_DAYS
    assert _clamp_days(-100) == MIN_DAYS


def test_clamp_days_clamps_above_max():
    assert _clamp_days(MAX_DAYS + 50) == MAX_DAYS


def test_clamp_days_default_on_garbage():
    assert _clamp_days("not a number") == DEFAULT_DAYS
    assert _clamp_days(None) == DEFAULT_DAYS


def test_clamp_days_accepts_inrange():
    assert _clamp_days(30) == 30
    assert _clamp_days("90") == 90


# ---------------------------------------------------------------------------
# build_price_statistics
# ---------------------------------------------------------------------------


def _prices_for_day(day_offset: int) -> list[HourlyPrice]:
    return [
        HourlyPrice(hour=h, price_ct_per_kwh=10.0 + h, avg_ct_per_kwh=15.0, tag="CHEAP")
        for h in range(24)
    ]


def test_build_price_statistics_one_row_per_hour():
    """Each hour gets a single MEASUREMENT row with mean=min=max=price."""
    d = date(2026, 6, 1)
    daily = {d: _prices_for_day(0)}

    metadata, statistics = build_price_statistics(
        "sensor.sunlit_garage_34038_electricity_price", daily
    )

    assert metadata["statistic_id"] == "sensor.sunlit_garage_34038_electricity_price"
    assert metadata["source"] == "recorder"
    assert metadata["name"] is None
    assert metadata["has_sum"] is False
    assert metadata["unit_of_measurement"] == "ct/kWh"

    assert len(statistics) == 24
    midnight = dt_util.start_of_local_day(d)
    assert statistics[0]["start"] == midnight
    assert statistics[0]["mean"] == 10.0
    assert statistics[0]["min"] == 10.0
    assert statistics[0]["max"] == 10.0
    assert statistics[5]["mean"] == 15.0
    # Hour-aligned, tz-aware, ascending.
    starts = [row["start"] for row in statistics]
    assert all(s.minute == 0 and s.second == 0 for s in starts)
    assert starts == sorted(starts)


def test_build_price_statistics_multiple_days():
    """Across multiple days, rows are emitted in date+hour order."""
    d1 = date(2026, 5, 30)
    d2 = date(2026, 5, 31)
    statistics = build_price_statistics(
        "sensor.x", {d2: _prices_for_day(0), d1: _prices_for_day(0)}
    )[1]
    assert len(statistics) == 48
    # First day comes first in the output even though dict iteration is unordered.
    midnight1 = dt_util.start_of_local_day(d1)
    midnight2 = dt_util.start_of_local_day(d2)
    assert statistics[0]["start"] == midnight1
    assert statistics[24]["start"] == midnight2


# ---------------------------------------------------------------------------
# async_collect_price_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_walks_oldest_to_newest():
    """Walking days N..1 back asks for the right dates in order."""
    coordinator = MagicMock()
    requested: list[date] = []

    async def _ensure(day):
        requested.append(day)
        return _prices_for_day(0) if day.day % 2 == 0 else []

    coordinator.async_ensure_day = AsyncMock(side_effect=_ensure)
    pinned = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)

    collected = await async_collect_price_history(coordinator, days=4, now=pinned)

    today = pinned.date()
    assert requested == [today - timedelta(days=o) for o in (4, 3, 2, 1)]
    # Only days whose date.day is even got data (per side_effect):
    # today=2026-06-05 -> days 06-01..06-04, even ones are 06-02 and 06-04.
    assert set(collected) == {today - timedelta(days=3), today - timedelta(days=1)}


@pytest.mark.asyncio
async def test_collect_empty_when_no_data():
    coordinator = MagicMock()
    coordinator.async_ensure_day = AsyncMock(return_value=[])
    assert await async_collect_price_history(coordinator, days=3) == {}


# ---------------------------------------------------------------------------
# async_import_family_price_history
# ---------------------------------------------------------------------------


def _coord(family_id="34038", family_name="Garage") -> MagicMock:
    coordinator = MagicMock()
    coordinator.family_id = family_id
    coordinator.family_name = family_name
    return coordinator


@pytest.mark.asyncio
async def test_import_family_history_resolves_entity_and_imports():
    """Happy path: resolve entity, collect, build, import."""
    coordinator = _coord()
    coordinator.async_ensure_day = AsyncMock(return_value=_prices_for_day(0))

    with (
        patch(
            "custom_components.sunlit.price_statistics.resolve_price_statistic_id",
            return_value="sensor.sunlit_garage_34038_electricity_price",
        ),
        patch(
            "custom_components.sunlit.price_statistics.async_import_statistics"
        ) as mock_import,
    ):
        count = await async_import_family_price_history(
            MagicMock(), coordinator, days=2
        )

    assert count == 48  # 2 days x 24 hours
    mock_import.assert_called_once()
    metadata, statistics = mock_import.call_args.args[1], mock_import.call_args.args[2]
    assert metadata["statistic_id"] == "sensor.sunlit_garage_34038_electricity_price"
    assert len(statistics) == 48


@pytest.mark.asyncio
async def test_import_family_history_skips_when_entity_missing():
    """No entity_id -> warn + skip, no import call."""
    coordinator = _coord()
    coordinator.async_ensure_day = AsyncMock(return_value=_prices_for_day(0))

    with (
        patch(
            "custom_components.sunlit.price_statistics.resolve_price_statistic_id",
            return_value=None,
        ),
        patch(
            "custom_components.sunlit.price_statistics.async_import_statistics"
        ) as mock_import,
    ):
        count = await async_import_family_price_history(
            MagicMock(), coordinator, days=5
        )

    assert count == 0
    mock_import.assert_not_called()


@pytest.mark.asyncio
async def test_import_family_history_skips_when_no_data_in_window():
    """All days return empty -> nothing imported."""
    coordinator = _coord()
    coordinator.async_ensure_day = AsyncMock(return_value=[])

    with (
        patch(
            "custom_components.sunlit.price_statistics.resolve_price_statistic_id",
            return_value="sensor.x_electricity_price",
        ),
        patch(
            "custom_components.sunlit.price_statistics.async_import_statistics"
        ) as mock_import,
    ):
        count = await async_import_family_price_history(
            MagicMock(), coordinator, days=7
        )

    assert count == 0
    mock_import.assert_not_called()


# ---------------------------------------------------------------------------
# async_import_all_price_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_all_aggregates_across_families():
    """Total rows = sum of per-family imports; per-family errors don't abort."""
    good = _coord(family_id="1", family_name="Family A")
    good.async_ensure_day = AsyncMock(return_value=_prices_for_day(0))

    broken = _coord(family_id="2", family_name="Family B")
    broken.async_ensure_day = AsyncMock(side_effect=RuntimeError("boom"))

    with (
        patch(
            "custom_components.sunlit.price_statistics.resolve_price_statistic_id",
            side_effect=lambda hass, name, fid: f"sensor.x_{fid}",
        ),
        patch(
            "custom_components.sunlit.price_statistics.async_import_statistics"
        ) as mock_import,
    ):
        total = await async_import_all_price_history(
            MagicMock(), [good, broken], days=1
        )

    assert total == 24  # only the good family contributed
    # One import for the good family; broken family's exception was swallowed.
    assert mock_import.call_count == 1
