"""Tariff calendar entities for the Rabot day-ahead price feed.

Two read-only calendars per family (created only when the feed is available):

- ``calendar.sunlit_<family>_cheap_electricity``
- ``calendar.sunlit_<family>_expensive_electricity``

Each contiguous run of hours matching the calendar's tag set becomes one
:class:`~homeassistant.components.calendar.CalendarEvent`. Cheap events fire on
``VERY_CHEAP``/``CHEAP``; expensive on ``EXPENSIVE``/``VERY_EXPENSIVE``;
``NORMAL`` falls into neither so it does not trigger automations.

The entity is automation-friendly: HA's Calendar trigger fires on event
start/end with optional offsets ("when *Cheap electricity* starts -> run
dishwasher", "-15 min before -> preheat").
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
import logging

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinators.tariff_calendar import (
    HourlyPrice,
    SunlitTariffCalendarCoordinator,
)

_LOGGER = logging.getLogger(__name__)

# Tag sets that drive the two calendar entities. NORMAL is intentionally
# excluded — automations should not fire on neutrally-priced hours.
_CHEAP_TAGS: frozenset[str] = frozenset({"VERY_CHEAP", "CHEAP"})
_EXPENSIVE_TAGS: frozenset[str] = frozenset({"EXPENSIVE", "VERY_EXPENSIVE"})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the cheap + expensive calendars for every family that has prices."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    entities: list[SunlitTariffCalendar] = []
    for family_id, family_coordinators in entry_data["coordinators"].items():
        coordinator: SunlitTariffCalendarCoordinator | None = family_coordinators.get(
            "tariff_calendar"
        )
        if coordinator is None:
            continue
        entities.append(
            SunlitTariffCalendar(
                coordinator,
                family_id=family_id,
                family_name=coordinator.family_name,
                key="cheap_electricity",
                name="Cheap Electricity",
                tag_set=_CHEAP_TAGS,
                kind="cheap",
                summary_label="Cheap electricity",
            )
        )
        entities.append(
            SunlitTariffCalendar(
                coordinator,
                family_id=family_id,
                family_name=coordinator.family_name,
                key="expensive_electricity",
                name="Expensive Electricity",
                tag_set=_EXPENSIVE_TAGS,
                kind="expensive",
                summary_label="Expensive electricity",
            )
        )
    if entities:
        async_add_entities(entities)


# ---------------------------------------------------------------------------
# Pure helpers (heavily unit-tested)
# ---------------------------------------------------------------------------


def merge_into_events(
    day: date,
    prices: Iterable[HourlyPrice],
    tag_set: frozenset[str],
    *,
    space_id: int | str,
    kind: str,
    summary_label: str,
) -> list[CalendarEvent]:
    """Merge contiguous matching hours into ``CalendarEvent`` blocks.

    Each event covers ``[start_of_local_day(day) + start_hour h,
    start_of_local_day(day) + (end_hour + 1) h)`` and carries the average
    price of the block in its summary plus the per-hour tags in its
    description.
    """
    sorted_prices = sorted(prices, key=lambda p: p.hour)
    midnight = dt_util.start_of_local_day(day)
    events: list[CalendarEvent] = []
    i = 0
    while i < len(sorted_prices):
        entry = sorted_prices[i]
        if entry.tag not in tag_set:
            i += 1
            continue
        # Extend the run while subsequent hours are contiguous and still match.
        run = [entry]
        j = i + 1
        while (
            j < len(sorted_prices)
            and sorted_prices[j].tag in tag_set
            and sorted_prices[j].hour == run[-1].hour + 1
        ):
            run.append(sorted_prices[j])
            j += 1
        start_hour = run[0].hour
        end_hour_exclusive = run[-1].hour + 1
        avg_price = sum(p.price_ct_per_kwh for p in run) / len(run)
        tags_csv = ", ".join(p.tag for p in run)
        events.append(
            CalendarEvent(
                start=midnight + timedelta(hours=start_hour),
                end=midnight + timedelta(hours=end_hour_exclusive),
                summary=f"{summary_label} · ⌀ {avg_price:.2f} ct/kWh",
                description=(
                    f"{start_hour:02d}:00-{end_hour_exclusive:02d}:00"
                    f" · {len(run)} h · avg {avg_price:.2f} ct/kWh"
                    f" · {tags_csv}"
                ),
                uid=f"sunlit:{space_id}:{kind}:{day.isoformat()}:{start_hour:02d}",
            )
        )
        i = j
    return events


def _select_active_or_next(
    events: Iterable[CalendarEvent], now: datetime
) -> CalendarEvent | None:
    """Return the event containing ``now``, else the soonest future event."""
    active: CalendarEvent | None = None
    soonest_future: CalendarEvent | None = None
    for event in events:
        if event.start <= now < event.end:
            active = event
            break
        if event.start > now and (
            soonest_future is None or event.start < soonest_future.start
        ):
            soonest_future = event
    return active or soonest_future


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------


class SunlitTariffCalendar(
    CoordinatorEntity[SunlitTariffCalendarCoordinator], CalendarEntity
):
    """Read-only calendar of contiguous cheap or expensive tariff windows."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SunlitTariffCalendarCoordinator,
        *,
        family_id: str,
        family_name: str,
        key: str,
        name: str,
        tag_set: frozenset[str],
        kind: str,
        summary_label: str,
    ) -> None:
        """Initialize one of the two tariff calendars."""
        super().__init__(coordinator)
        self._family_id = family_id
        self._family_name = family_name
        self._tag_set = tag_set
        self._kind = kind
        self._summary_label = summary_label
        slug_family = family_name.lower().replace(" ", "_")
        self._attr_unique_id = f"sunlit_{slug_family}_{family_id}_{key}"
        self._attr_name = name

    @property
    def device_info(self) -> DeviceInfo:
        """Attach the calendar to the family hub device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"family_{self._family_id}")},
            name=f"{self._family_name} Solar System",
            manufacturer="Sunlit Solar",
            model="Solar Management Hub",
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the currently active event or the soonest upcoming one."""
        now = dt_util.now()
        today = now.date()
        candidates: list[CalendarEvent] = []
        for day in (today, today + timedelta(days=1)):
            prices = self.coordinator.daily_prices.get(day)
            if prices:
                candidates.extend(self._build_events(day, prices))
        return _select_active_or_next(candidates, now)

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Fetch any uncached days in the requested range and build events."""
        events: list[CalendarEvent] = []
        day = start_date.date()
        end = end_date.date()
        while day <= end:
            prices = await self.coordinator.async_ensure_day(day)
            if prices:
                events.extend(self._build_events(day, prices))
            day += timedelta(days=1)
        return events

    def _build_events(
        self, day: date, prices: list[HourlyPrice]
    ) -> list[CalendarEvent]:
        return merge_into_events(
            day,
            prices,
            self._tag_set,
            space_id=self.coordinator.space_id,
            kind=self._kind,
            summary_label=self._summary_label,
        )
