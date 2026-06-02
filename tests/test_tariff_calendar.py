"""Tests for the tariff calendar platform (pure logic + entity)."""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.calendar import CalendarEvent
from homeassistant.util import dt as dt_util
import pytest

from custom_components.sunlit.calendar import (
    SunlitTariffCalendar,
    _select_active_or_next,
    merge_into_events,
)
from custom_components.sunlit.coordinators.tariff_calendar import HourlyPrice

# Tag sets matching the calendar.py module constants.
_CHEAP = frozenset({"VERY_CHEAP", "CHEAP"})
_EXPENSIVE = frozenset({"EXPENSIVE", "VERY_EXPENSIVE"})


def _prices(
    tag_per_hour: list[str], price_per_hour: list[float] | None = None
) -> list[HourlyPrice]:
    """Build 24 HourlyPrice entries from a list of tags."""
    assert len(tag_per_hour) == 24
    if price_per_hour is None:
        price_per_hour = [10.0] * 24
    return [
        HourlyPrice(
            hour=h, price_ct_per_kwh=price_per_hour[h], avg_ct_per_kwh=10.0, tag=t
        )
        for h, t in enumerate(tag_per_hour)
    ]


# ---------------------------------------------------------------------------
# merge_into_events
# ---------------------------------------------------------------------------


def test_merge_no_matches_returns_empty():
    """A day with no matching tags produces no events."""
    prices = _prices(["NORMAL"] * 24)
    events = merge_into_events(
        date(2026, 6, 2),
        prices,
        _CHEAP,
        space_id=34038,
        kind="cheap",
        summary_label="Cheap electricity",
    )
    assert events == []


def test_merge_single_hour_block():
    """One isolated CHEAP hour produces a one-hour event."""
    tags = ["NORMAL"] * 24
    tags[3] = "CHEAP"
    events = merge_into_events(
        date(2026, 6, 2),
        _prices(tags),
        _CHEAP,
        space_id=34038,
        kind="cheap",
        summary_label="Cheap electricity",
    )
    assert len(events) == 1
    midnight = dt_util.start_of_local_day(date(2026, 6, 2))
    assert events[0].start == midnight + timedelta(hours=3)
    assert events[0].end == midnight + timedelta(hours=4)
    assert events[0].uid == "sunlit:34038:cheap:2026-06-02:03"


def test_merge_contiguous_matching_hours_collapse_to_one_event():
    """02:00–05:00 (3 CHEAP hours in a row) becomes a single event 02–05."""
    tags = ["NORMAL"] * 24
    tags[2:5] = ["CHEAP", "CHEAP", "VERY_CHEAP"]
    prices = _prices(tags, [10.0] * 24)
    prices[2] = HourlyPrice(2, 3.0, 10.0, "CHEAP")
    prices[3] = HourlyPrice(3, 4.0, 10.0, "CHEAP")
    prices[4] = HourlyPrice(4, 5.0, 10.0, "VERY_CHEAP")
    events = merge_into_events(
        date(2026, 6, 2),
        prices,
        _CHEAP,
        space_id=34038,
        kind="cheap",
        summary_label="Cheap electricity",
    )
    assert len(events) == 1
    midnight = dt_util.start_of_local_day(date(2026, 6, 2))
    assert events[0].start == midnight + timedelta(hours=2)
    assert events[0].end == midnight + timedelta(hours=5)  # exclusive
    # Average of 3.0, 4.0, 5.0 = 4.00
    assert "⌀ 4.00 ct/kWh" in events[0].summary
    # Description includes per-hour tags
    assert "CHEAP, CHEAP, VERY_CHEAP" in events[0].description
    assert "02:00-05:00" in events[0].description


def test_merge_breaks_on_normal_between_two_runs():
    """A NORMAL hour splits CHEAP-CHEAP-NORMAL-CHEAP into two events."""
    tags = ["NORMAL"] * 24
    tags[2:6] = ["CHEAP", "CHEAP", "NORMAL", "CHEAP"]
    events = merge_into_events(
        date(2026, 6, 2),
        _prices(tags),
        _CHEAP,
        space_id=34038,
        kind="cheap",
        summary_label="Cheap electricity",
    )
    assert len(events) == 2
    midnight = dt_util.start_of_local_day(date(2026, 6, 2))
    assert events[0].start == midnight + timedelta(hours=2)
    assert events[0].end == midnight + timedelta(hours=4)
    assert events[1].start == midnight + timedelta(hours=5)
    assert events[1].end == midnight + timedelta(hours=6)


def test_merge_cheap_tag_set_ignores_expensive():
    """The cheap calendar only fires on CHEAP/VERY_CHEAP, not EXPENSIVE."""
    tags = ["NORMAL"] * 24
    tags[10] = "EXPENSIVE"
    tags[11] = "VERY_EXPENSIVE"
    tags[14] = "CHEAP"
    cheap_events = merge_into_events(
        date(2026, 6, 2),
        _prices(tags),
        _CHEAP,
        space_id=34038,
        kind="cheap",
        summary_label="Cheap electricity",
    )
    expensive_events = merge_into_events(
        date(2026, 6, 2),
        _prices(tags),
        _EXPENSIVE,
        space_id=34038,
        kind="expensive",
        summary_label="Expensive electricity",
    )
    assert len(cheap_events) == 1
    assert cheap_events[0].uid.startswith("sunlit:34038:cheap:")
    assert len(expensive_events) == 1  # merged EXPENSIVE + VERY_EXPENSIVE
    assert expensive_events[0].uid.startswith("sunlit:34038:expensive:")


def test_merge_uses_local_midnight_for_event_boundaries():
    """Event start aligns to local midnight, regardless of tz tricks."""
    tags = ["NORMAL"] * 24
    tags[0] = "CHEAP"
    events = merge_into_events(
        date(2026, 6, 2),
        _prices(tags),
        _CHEAP,
        space_id=34038,
        kind="cheap",
        summary_label="Cheap electricity",
    )
    midnight = dt_util.start_of_local_day(date(2026, 6, 2))
    assert events[0].start == midnight
    assert events[0].start.tzinfo is not None  # tz-aware


# ---------------------------------------------------------------------------
# _select_active_or_next
# ---------------------------------------------------------------------------


def _event(start_h: int, end_h: int) -> CalendarEvent:
    base = datetime(2026, 6, 2, 0, 0, tzinfo=timezone.utc)
    return CalendarEvent(
        start=base + timedelta(hours=start_h),
        end=base + timedelta(hours=end_h),
        summary="x",
    )


def test_select_returns_active_event_when_now_inside():
    events = [_event(2, 5), _event(9, 11), _event(20, 22)]
    now = datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc)
    selected = _select_active_or_next(events, now)
    assert selected is not None and selected.start.hour == 9


def test_select_returns_soonest_future_when_none_active():
    events = [_event(2, 5), _event(20, 22), _event(15, 17)]
    now = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
    selected = _select_active_or_next(events, now)
    assert selected is not None and selected.start.hour == 15  # soonest, not 20


def test_select_none_when_all_past():
    events = [_event(2, 5)]
    now = datetime(2026, 6, 2, 23, 0, tzinfo=timezone.utc)
    assert _select_active_or_next(events, now) is None


# ---------------------------------------------------------------------------
# SunlitTariffCalendar.async_get_events
# ---------------------------------------------------------------------------


def _make_entity(coordinator) -> SunlitTariffCalendar:
    return SunlitTariffCalendar(
        coordinator,
        family_id="34038",
        family_name="Garage",
        key="cheap_electricity",
        name="Cheap Electricity",
        tag_set=_CHEAP,
        kind="cheap",
        summary_label="Cheap electricity",
    )


@pytest.mark.asyncio
async def test_async_get_events_fetches_each_day_in_range():
    """One ensure_day call per day in [start, end]."""
    today = dt_util.now().date()
    tags = ["NORMAL"] * 24
    tags[2] = "CHEAP"
    coordinator = MagicMock()
    coordinator.daily_prices = {}
    coordinator.space_id = 34038

    async def _ensure(day):
        # Today has data, surrounding days are empty.
        return _prices(tags) if day == today else []

    coordinator.async_ensure_day = AsyncMock(side_effect=_ensure)

    entity = _make_entity(coordinator)
    midnight = dt_util.start_of_local_day(today)
    events = await entity.async_get_events(
        hass=MagicMock(),
        start_date=midnight - timedelta(days=2),
        end_date=midnight + timedelta(days=1),
    )

    assert coordinator.async_ensure_day.call_count == 4  # -2, -1, 0, +1
    assert len(events) == 1
    assert events[0].start == midnight + timedelta(hours=2)
