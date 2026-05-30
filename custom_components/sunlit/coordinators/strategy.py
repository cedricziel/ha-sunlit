"""Strategy history coordinator for Sunlit integration."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..api_client import SunlitApiClient, SunlitApiError
from ..const import (
    DEFAULT_HIGH_PRICE_SOC_MAX,
    DEFAULT_HIGH_PRICE_SOC_MIN,
    DEFAULT_HIGH_PRICE_STRATEGY,
    DEFAULT_LOW_PRICE_INVERTER_OUTPUT,
    DEFAULT_LOW_PRICE_SOC_MAX,
    DEFAULT_LOW_PRICE_SOC_MIN,
    DEFAULT_LOW_PRICE_STRATEGY,
)

_LOGGER = logging.getLogger(__name__)


class SunlitStrategyHistoryCoordinator(DataUpdateCoordinator):
    """Coordinator for strategy history data and tariff-strategy setup cache.

    The /v1.6/tariffStrategy/add endpoint is all-or-nothing: every write must
    carry the full low+high blocks. This coordinator owns the in-memory cache
    of the last sent values so that individual select/number entities can
    mutate one field at a time and the coordinator submits the bundle.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: SunlitApiClient,
        family_id: str,
        family_name: str,
    ) -> None:
        """Initialize the strategy history coordinator."""
        self.api_client = api_client
        self.family_id = family_id
        self.family_name = family_name

        # Cached tariff-strategy setup. Mutated by entity setters and read by
        # set_tariff_strategy(). Initialised with sensible defaults; entities
        # may overwrite via restored state on startup.
        self._tariff_setup: dict[str, dict[str, Any]] = {
            "low": {
                "strategy": DEFAULT_LOW_PRICE_STRATEGY,
                "socMin": DEFAULT_LOW_PRICE_SOC_MIN,
                "socMax": DEFAULT_LOW_PRICE_SOC_MAX,
                "defaultExpectInverterOutput": DEFAULT_LOW_PRICE_INVERTER_OUTPUT,
            },
            "high": {
                "strategy": DEFAULT_HIGH_PRICE_STRATEGY,
                "socMin": DEFAULT_HIGH_PRICE_SOC_MIN,
                "socMax": DEFAULT_HIGH_PRICE_SOC_MAX,
            },
        }

        super().__init__(
            hass,
            _LOGGER,
            name=f"Sunlit Strategy History {family_name}",
            update_interval=timedelta(minutes=5),  # 5 minute updates
        )

    @property
    def tariff_setup(self) -> dict[str, dict[str, Any]]:
        """Return a defensive copy of the cached tariff-strategy setup.

        The copy keeps callers from mutating the cache directly — every
        change must go through :meth:`update_tariff_setup_field` so that
        validation runs and the readback path stays authoritative.
        """
        return {band: dict(fields) for band, fields in self._tariff_setup.items()}

    def update_tariff_setup_field(self, band: str, field: str, value: Any) -> None:
        """Update one field of the cached tariff setup before pushing.

        Args:
            band: ``low`` or ``high``
            field: e.g. ``strategy``, ``socMin``, ``socMax``
            value: new value
        """
        if band not in self._tariff_setup:
            raise ValueError(f"Unknown tariff band: {band}")
        if field not in self._tariff_setup[band]:
            raise ValueError(f"Unknown field '{field}' for tariff band '{band}'")
        self._tariff_setup[band][field] = value

    async def async_push_tariff_setup(self, enable_switch_notice: bool = True) -> None:
        """Push the cached tariff setup to /v1.6/tariffStrategy/add."""
        await self.api_client.set_tariff_strategy(
            self.family_id,
            low_price_strategy=self._tariff_setup["low"],
            high_price_strategy=self._tariff_setup["high"],
            enable_switch_notice=enable_switch_notice,
        )
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch strategy history data from REST API."""
        try:
            strategy_data: dict[str, Any] = {}

            # Fetch strategy history
            strategy_history = await self.api_client.fetch_space_strategy_history(
                self.family_id
            )

            if strategy_history and "content" in strategy_history:
                history_entries = strategy_history["content"]
                if history_entries:
                    # Get most recent entry
                    latest_entry = history_entries[0]

                    strategy_data["last_strategy_change"] = latest_entry.get(
                        "modifyDate"
                    )
                    strategy_data["last_strategy_type"] = latest_entry.get("strategy")
                    strategy_data["last_strategy_status"] = latest_entry.get("status")

                    # Count changes in last 24 hours
                    now = datetime.now()
                    day_ago = now - timedelta(days=1)
                    day_ago_ms = int(day_ago.timestamp() * 1000)

                    changes_today = sum(
                        1
                        for entry in history_entries
                        if entry.get("modifyDate", 0) >= day_ago_ms
                    )
                    strategy_data["strategy_changes_today"] = changes_today

                    # Store last 10 entries
                    strategy_data["strategy_history"] = history_entries[:10]

            return {"strategy": strategy_data}

        except SunlitApiError as err:
            _LOGGER.warning(
                "Error fetching strategy history for %s: %s", self.family_name, err
            )
            # Return empty data instead of failing
            return {"strategy": {}}
