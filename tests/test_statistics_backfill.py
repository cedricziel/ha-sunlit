"""Tests for historical + live long-term statistics (imported onto entities)."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

from homeassistant.util import dt as dt_util
import pytest

from custom_components.sunlit.statistics import (
    DailyEarning,
    _series_specs,
    async_collect_earning_history,
    async_import_family_history,
    async_record_family_live_statistics,
    build_series_statistics,
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


class FakeFamilyCoordinator:
    """Stand-in for SunlitFamilyCoordinator used by the live recorder."""

    def __init__(self, data, family_id="34038", family_name="Garage"):
        self.data = data
        self.family_id = family_id
        self.family_name = family_name


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


def _sample_daily():
    return [
        DailyEarning(date(2024, 1, 1), 2.0, 0.6, "EUR"),
        DailyEarning(date(2024, 1, 2), 3.0, 0.9, "EUR"),
        DailyEarning(date(2024, 3, 9), 1.0, 0.3, "EUR"),
        DailyEarning(date(2024, 3, 10), 1.5, 0.4, "EUR"),
    ]


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


def test_build_series_statistics_cumulative_sums():
    """Series build cumulative sums onto an entity statistic_id (source=recorder)."""
    daily = _sample_daily()
    yield_series, earnings_series = _series_specs("EUR")

    energy_meta, energy_stats = build_series_statistics(
        "sensor.sunlit_garage_34038_lifetime_yield", yield_series, daily
    )
    earn_meta, earn_stats = build_series_statistics(
        "sensor.sunlit_garage_34038_lifetime_earnings", earnings_series, daily
    )

    # Entity statistics: dotted statistic_id, source must be "recorder", no name.
    assert energy_meta["statistic_id"] == "sensor.sunlit_garage_34038_lifetime_yield"
    assert energy_meta["source"] == "recorder"
    assert energy_meta["name"] is None
    assert energy_meta["has_sum"] is True
    assert energy_meta["unit_of_measurement"] == "kWh"
    assert energy_meta["unit_class"] == "energy"
    assert earn_meta["unit_of_measurement"] == "EUR"
    assert earn_meta["unit_class"] is None

    assert [s["sum"] for s in energy_stats] == pytest.approx([2.0, 5.0, 6.0, 7.5])
    assert [s["state"] for s in energy_stats] == pytest.approx([2.0, 3.0, 1.0, 1.5])
    assert [s["sum"] for s in earn_stats] == pytest.approx([0.6, 1.5, 1.8, 2.2])

    starts = [s["start"] for s in energy_stats]
    assert starts == [dt_util.start_of_local_day(d.date) for d in daily]
    assert all(s.minute == 0 and s.second == 0 for s in starts)
    assert starts == sorted(starts)


async def test_import_family_history_imports_onto_entities():
    """History is cleared and re-imported onto the resolved entity ids."""
    api = _sample_api()
    now = datetime(2024, 3, 10, 12, tzinfo=UTC)
    recorder = MagicMock()
    with (
        patch("custom_components.sunlit.statistics.dt_util.now", return_value=now),
        patch(
            "custom_components.sunlit.statistics.resolve_statistic_id",
            side_effect=lambda hass, name, fid, key: f"sensor.sunlit_{fid}_{key}",
        ),
        patch(
            "custom_components.sunlit.statistics.get_instance",
            return_value=recorder,
        ),
        patch(
            "custom_components.sunlit.statistics.async_import_statistics"
        ) as mock_import,
    ):
        count = await async_import_family_history(MagicMock(), api, "34038", "Garage")

    assert count == 4
    assert mock_import.call_count == 2
    statistic_ids = {
        call.args[1]["statistic_id"] for call in mock_import.call_args_list
    }
    assert statistic_ids == {
        "sensor.sunlit_34038_lifetime_yield",
        "sensor.sunlit_34038_lifetime_earnings",
    }
    # Existing recorder statistics are cleared before re-import.
    cleared = {
        call.args[0][0] for call in recorder.async_clear_statistics.call_args_list
    }
    assert cleared == statistic_ids


async def test_import_family_history_no_data_skips():
    """No history imports nothing and returns zero."""
    api = FakeEarningApi({"powerEarningsList": []}, {}, {})
    with (
        patch("custom_components.sunlit.statistics.get_instance"),
        patch(
            "custom_components.sunlit.statistics.async_import_statistics"
        ) as mock_import,
    ):
        count = await async_import_family_history(MagicMock(), api, "34038", "Garage")

    assert count == 0
    mock_import.assert_not_called()


async def test_import_family_history_skips_missing_entity():
    """When an entity is not registered yet, that series is skipped."""
    api = _sample_api()
    now = datetime(2024, 3, 10, 12, tzinfo=UTC)
    with (
        patch("custom_components.sunlit.statistics.dt_util.now", return_value=now),
        patch(
            "custom_components.sunlit.statistics.resolve_statistic_id",
            return_value=None,
        ),
        patch("custom_components.sunlit.statistics.get_instance"),
        patch(
            "custom_components.sunlit.statistics.async_import_statistics"
        ) as mock_import,
    ):
        count = await async_import_family_history(MagicMock(), api, "34038", "Garage")

    assert count == 0
    mock_import.assert_not_called()


def test_record_family_live_statistics_appends_current_hour():
    """The hourly recorder appends one cumulative point per series."""
    coordinator = FakeFamilyCoordinator(
        {"lifetime_yield": 123.4, "lifetime_earnings": 45.6, "currency": "EUR"}
    )
    with (
        patch(
            "custom_components.sunlit.statistics.resolve_statistic_id",
            side_effect=lambda hass, name, fid, key: f"sensor.sunlit_{fid}_{key}",
        ),
        patch(
            "custom_components.sunlit.statistics.async_import_statistics"
        ) as mock_import,
    ):
        async_record_family_live_statistics(MagicMock(), coordinator)

    assert mock_import.call_count == 2
    by_id = {
        call.args[1]["statistic_id"]: call.args[2]
        for call in mock_import.call_args_list
    }
    yield_stats = by_id["sensor.sunlit_34038_lifetime_yield"]
    assert len(yield_stats) == 1
    assert yield_stats[0]["sum"] == 123.4
    assert yield_stats[0]["state"] == 123.4
    assert yield_stats[0]["start"].minute == 0
    assert yield_stats[0]["start"].second == 0
    assert by_id["sensor.sunlit_34038_lifetime_earnings"][0]["sum"] == 45.6


def test_record_family_live_statistics_skips_missing_values():
    """Missing lifetime values are skipped without importing."""
    coordinator = FakeFamilyCoordinator({"currency": "EUR"})
    with (
        patch(
            "custom_components.sunlit.statistics.resolve_statistic_id",
            side_effect=lambda hass, name, fid, key: f"sensor.sunlit_{fid}_{key}",
        ),
        patch(
            "custom_components.sunlit.statistics.async_import_statistics"
        ) as mock_import,
    ):
        async_record_family_live_statistics(MagicMock(), coordinator)

    mock_import.assert_not_called()
