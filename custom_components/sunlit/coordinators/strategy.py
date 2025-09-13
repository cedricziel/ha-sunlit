"""Strategy history coordinator for Sunlit integration."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..api_client import SunlitApiClient

_LOGGER = logging.getLogger(__name__)


class SunlitStrategyHistoryCoordinator(DataUpdateCoordinator):
    """Coordinator for strategy history data."""

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

        super().__init__(
            hass,
            _LOGGER,
            name=f"Sunlit Strategy History {family_name}",
            update_interval=timedelta(minutes=5),  # 5 minute updates
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch strategy history data from REST API."""
        try:
            strategy_data = {}

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

        except Exception as err:
            _LOGGER.warning(
                "Error fetching strategy history for %s: %s", self.family_name, err
            )
            # Return empty data instead of failing
            return {"strategy": {}}
