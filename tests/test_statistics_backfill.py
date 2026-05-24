"""Tests for historical long-term statistics backfill."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

from homeassistant.util import dt as dt_util
import pytest

from custom_components.sunlit.statistics import (
    DailyEarning,
    async_collect_earning_history,
    async_import_family_history,
    build_external_statistics,
)


class FakeEarningApi:
    """Minimal fake exposing fetch_space_statistics_dynamic_earning."""

    def __init__(self, years, months, days):
        self._years = years
        self._months = months
        self._days = days
        self.calls: list[tuple[int | None, int | None]] = []

    async def fetch_space_statistics_dynamic_earning(
        self, space_id, year=None, month=None
    ):
        self.calls.append((year, month))
        if year is None:
            return self._years
        if month is None:
            return self._months.get(year, {"powerEarningsList": []})
        return self._days.get((year, month), {"powerEarningsList": []})


def _bucket(key, gen=0.0, earn=0.0, currency="EUR"):
    return {
        "key": key,
        "totalPowerGeneration": gen,
        "totalEarnings": earn,
        "currency": currency,
    }


def _sample_api():
    years = {
        "powerEarningsList": [
            _bucket(2023, gen=0.0, earn=0.0),  # no data -> pruned
            _bucket(2024, gen=12.0, earn=4.0),
            _bucket(2025, gen=99.0, earn=9.0),  # future year -> skipped
        ]
    }
    months = {
        2024: {
            "powerEarningsList": [
                _bucket(1, gen=5.0, earn=1.5),
                _bucket(2, gen=0.0, earn=0.0),  # no data -> pruned
                _bucket(3, gen=7.0, earn=2.5),
                _bucket(4, gen=99.0, earn=9.0),  # future month -> skipped
            ]
        }
    }
    days = {
        (2024, 1): {
            "powerEarningsList": [
                _bucket(1, gen=2.0, earn=0.6),
                _bucket(2, gen=3.0, earn=0.9),
            ]
        },
        (2024, 3): {
            "powerEarningsList": [
                _bucket(9, gen=1.0, earn=0.3),
                _bucket(10, gen=1.5, earn=0.4),
                _bucket(11, gen=99.0, earn=9.0),  # future day -> skipped
            ]
        },
    }
    return FakeEarningApi(years, months, days)


async def test_collect_earning_history_walks_and_caps():
    """Walk year->month->day, pruning empty buckets and future periods."""
    api = _sample_api()
    today = date(2024, 3, 10)

    daily = await async_collect_earning_history(api, "34038", today)

    assert [d.date for d in daily] == [
        date(2024, 1, 1),
        date(2024, 1, 2),
        date(2024, 3, 9),
        date(2024, 3, 10),
    ]
    assert [d.generation_kwh for d in daily] == [2.0, 3.0, 1.0, 1.5]
    assert [d.earnings for d in daily] == [0.6, 0.9, 0.3, 0.4]
    assert all(d.currency == "EUR" for d in daily)

    # Empty month (2024-02) and future periods were never fetched.
    assert (2024, 2) not in api.calls
    assert (2024, 4) not in api.calls
    assert (2025, None) not in api.calls


async def test_collect_earning_history_empty():
    """No history yields an empty list."""
    api = FakeEarningApi({"powerEarningsList": []}, {}, {})
    daily = await async_collect_earning_history(api, "34038", date(2024, 1, 1))
    assert daily == []


def test_build_external_statistics_cumulative_sums():
    """Statistics are cumulative sums with hour-aligned starts."""
    daily = [
        DailyEarning(date(2024, 1, 1), 2.0, 0.6, "EUR"),
        DailyEarning(date(2024, 1, 2), 3.0, 0.9, "EUR"),
        DailyEarning(date(2024, 3, 9), 1.0, 0.3, "EUR"),
        DailyEarning(date(2024, 3, 10), 1.5, 0.4, "EUR"),
    ]

    series = build_external_statistics("34038", "Garage", daily, "EUR")
    assert len(series) == 2
    (energy_meta, energy_stats), (earnings_meta, earnings_stats) = series

    assert energy_meta["statistic_id"] == "sunlit:34038_lifetime_yield"
    assert energy_meta["source"] == "sunlit"
    assert energy_meta["has_sum"] is True
    assert energy_meta["unit_of_measurement"] == "kWh"
    assert earnings_meta["statistic_id"] == "sunlit:34038_lifetime_earnings"
    assert earnings_meta["unit_of_measurement"] == "EUR"

    assert [s["sum"] for s in energy_stats] == pytest.approx([2.0, 5.0, 6.0, 7.5])
    assert [s["state"] for s in energy_stats] == pytest.approx([2.0, 3.0, 1.0, 1.5])
    assert [s["sum"] for s in earnings_stats] == pytest.approx([0.6, 1.5, 1.8, 2.2])

    # Starts are local midnight, ascending and hour-aligned.
    starts = [s["start"] for s in energy_stats]
    assert starts == [dt_util.start_of_local_day(d.date) for d in daily]
    assert all(s.minute == 0 and s.second == 0 for s in starts)
    assert starts == sorted(starts)


async def test_import_family_history_pushes_two_series():
    """The orchestrator imports both energy and earnings series."""
    api = _sample_api()
    now = datetime(2024, 3, 10, 12, tzinfo=UTC)
    with (
        patch("custom_components.sunlit.statistics.dt_util.now", return_value=now),
        patch(
            "custom_components.sunlit.statistics.async_add_external_statistics"
        ) as mock_add,
    ):
        count = await async_import_family_history(MagicMock(), api, "34038", "Garage")

    assert count == 4
    assert mock_add.call_count == 2
    statistic_ids = {call.args[1]["statistic_id"] for call in mock_add.call_args_list}
    assert statistic_ids == {
        "sunlit:34038_lifetime_yield",
        "sunlit:34038_lifetime_earnings",
    }


async def test_import_family_history_no_data_skips():
    """No history imports nothing and returns zero."""
    api = FakeEarningApi({"powerEarningsList": []}, {}, {})
    with patch(
        "custom_components.sunlit.statistics.async_add_external_statistics"
    ) as mock_add:
        count = await async_import_family_history(MagicMock(), api, "34038", "Garage")

    assert count == 0
    mock_add.assert_not_called()
