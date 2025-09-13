"""Event manager for SOC change notifications in Sunlit integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Event types following HomeAssistant naming conventions
EVENT_SOC_THRESHOLD = f"{DOMAIN}_soc_threshold"
EVENT_SOC_CHANGE = f"{DOMAIN}_soc_change"
EVENT_SOC_LIMIT = f"{DOMAIN}_soc_limit"

# Default thresholds (configurable via options flow)
DEFAULT_THRESHOLDS = {
    "critical_low": 10,
    "low": 20,
    "high": 90,
    "critical_high": 95,
}

DEFAULT_CHANGE_THRESHOLD = 5  # ±5% change threshold


@dataclass
class SOCState:
    """Represents the SOC state for change detection."""

    value: float
    timestamp: datetime
    last_event_value: float | None = None
    last_event_timestamp: datetime | None = None


class SunlitEventManager:
    """Manages SOC-related events for the Sunlit integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        family_id: str,
        config_options: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the event manager."""
        self.hass = hass
        self.family_id = family_id
        self._soc_states: dict[str, SOCState] = {}

        # Configuration from options flow or defaults
        options = config_options or {}
        self.thresholds = options.get("soc_thresholds", DEFAULT_THRESHOLDS.copy())
        self.change_threshold = options.get(
            "soc_change_threshold", DEFAULT_CHANGE_THRESHOLD
        )
        self.min_event_interval = timedelta(
            seconds=options.get("min_event_interval_seconds", 60)
        )

        # Rate limiting: track last events to prevent spam
        self._last_threshold_events: dict[str, datetime] = {}

    def update_soc_state(
        self,
        device_key: str,
        soc_value: float,
        limits: dict[str, float] | None = None,
    ) -> None:
        """Update SOC state and dispatch events if thresholds are crossed.

        Args:
            device_key: Unique identifier (e.g., "system", "battery_123_module1")
            soc_value: Current SOC percentage (0-100)
            limits: Optional SOC limits (strategy_min/max, bms_min/max, hw_min/max)
        """
        if soc_value is None:
            return

        now = dt_util.utcnow()
        current_state = self._soc_states.get(device_key)

        # Initialize state if first time
        if current_state is None:
            self._soc_states[device_key] = SOCState(value=soc_value, timestamp=now)
            return

        previous_value = current_state.value
        current_state.value = soc_value
        current_state.timestamp = now

        # Check for threshold crossings
        self._check_threshold_events(device_key, previous_value, soc_value, now)

        # Check for significant changes
        self._check_change_events(
            device_key, previous_value, soc_value, now, current_state
        )

        # Check for limit events
        if limits:
            self._check_limit_events(device_key, soc_value, limits, now)

    def _check_threshold_events(
        self,
        device_key: str,
        previous_value: float,
        current_value: float,
        timestamp: datetime,
    ) -> None:
        """Check if SOC crossed predefined thresholds."""
        for threshold_name, threshold_value in self.thresholds.items():
            # Check for crossing (both directions)
            crossed_up = previous_value < threshold_value <= current_value
            crossed_down = previous_value > threshold_value >= current_value

            if crossed_up or crossed_down:
                # Rate limiting check
                last_event_key = f"{device_key}_{threshold_name}"
                last_event_time = self._last_threshold_events.get(last_event_key)

                if (
                    last_event_time is None
                    or timestamp - last_event_time >= self.min_event_interval
                ):
                    direction = "above" if crossed_up else "below"
                    self._fire_event(
                        EVENT_SOC_THRESHOLD,
                        {
                            "device_key": device_key,
                            "family_id": self.family_id,
                            "threshold_name": threshold_name,
                            "threshold_value": threshold_value,
                            "current_soc": current_value,
                            "previous_soc": previous_value,
                            "direction": direction,
                            "timestamp": timestamp.isoformat(),
                        },
                    )

                    self._last_threshold_events[last_event_key] = timestamp

                    _LOGGER.info(
                        "SOC threshold event: %s crossed %s threshold (%s%%) - %s -> %s",
                        device_key,
                        threshold_name,
                        threshold_value,
                        previous_value,
                        current_value,
                    )

    def _check_change_events(
        self,
        device_key: str,
        previous_value: float,
        current_value: float,
        timestamp: datetime,
        current_state: SOCState,
    ) -> None:
        """Check for significant SOC changes."""
        # Use last event value as baseline, or previous if no events yet
        baseline_value = (
            current_state.last_event_value
            if current_state.last_event_value is not None
            else previous_value
        )

        change = abs(current_value - baseline_value)

        if change >= self.change_threshold:
            # Rate limiting check
            last_event_time = current_state.last_event_timestamp

            if (
                last_event_time is None
                or timestamp - last_event_time >= self.min_event_interval
            ):
                direction = "increase" if current_value > baseline_value else "decrease"

                self._fire_event(
                    EVENT_SOC_CHANGE,
                    {
                        "device_key": device_key,
                        "family_id": self.family_id,
                        "change_amount": round(change, 1),
                        "change_threshold": self.change_threshold,
                        "current_soc": current_value,
                        "baseline_soc": baseline_value,
                        "direction": direction,
                        "timestamp": timestamp.isoformat(),
                    },
                )

                # Update last event tracking
                current_state.last_event_value = current_value
                current_state.last_event_timestamp = timestamp

                _LOGGER.info(
                    "SOC change event: %s changed by %s%% (%s -> %s)",
                    device_key,
                    change,
                    baseline_value,
                    current_value,
                )

    def _check_limit_events(
        self,
        device_key: str,
        soc_value: float,
        limits: dict[str, float],
        timestamp: datetime,
    ) -> None:
        """Check if SOC reached configured limits."""
        for limit_type, limit_value in limits.items():
            if limit_value is None:
                continue

            # Check if SOC reached the limit (with small tolerance)
            tolerance = 1.0  # 1% tolerance
            at_limit = abs(soc_value - limit_value) <= tolerance

            if at_limit:
                # Rate limiting
                last_event_key = f"{device_key}_{limit_type}"
                last_event_time = self._last_threshold_events.get(last_event_key)

                if (
                    last_event_time is None
                    or timestamp - last_event_time >= self.min_event_interval
                ):
                    self._fire_event(
                        EVENT_SOC_LIMIT,
                        {
                            "device_key": device_key,
                            "family_id": self.family_id,
                            "limit_type": limit_type,
                            "limit_value": limit_value,
                            "current_soc": soc_value,
                            "tolerance": tolerance,
                            "timestamp": timestamp.isoformat(),
                        },
                    )

                    self._last_threshold_events[last_event_key] = timestamp

                    _LOGGER.info(
                        "SOC limit event: %s reached %s limit (%s%%)",
                        device_key,
                        limit_type,
                        limit_value,
                    )

    def _fire_event(self, event_type: str, event_data: dict[str, Any]) -> None:
        """Fire an event on the HomeAssistant event bus."""
        try:
            self.hass.bus.async_fire(event_type, event_data)
            _LOGGER.debug("Fired event %s with data: %s", event_type, event_data)
        except Exception as err:
            _LOGGER.error("Failed to fire event %s: %s", event_type, err)

    def get_soc_state(self, device_key: str) -> SOCState | None:
        """Get current SOC state for a device."""
        return self._soc_states.get(device_key)

    def update_configuration(self, config_options: dict[str, Any]) -> None:
        """Update event manager configuration from options flow."""
        self.thresholds = config_options.get(
            "soc_thresholds", DEFAULT_THRESHOLDS.copy()
        )
        self.change_threshold = config_options.get(
            "soc_change_threshold", DEFAULT_CHANGE_THRESHOLD
        )
        self.min_event_interval = timedelta(
            seconds=config_options.get("min_event_interval_seconds", 60)
        )
        _LOGGER.info(
            "Updated event manager configuration for family %s", self.family_id
        )
