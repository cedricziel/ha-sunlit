"""Select platform for the Sunlit integration: tariff strategy choice."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api_client import SunlitApiError
from .const import DOMAIN, TARIFF_STRATEGY_OPTIONS
from .coordinators.strategy import SunlitStrategyHistoryCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    integration_data = hass.data[DOMAIN][config_entry.entry_id]

    if isinstance(integration_data, dict) and "coordinators" in integration_data:
        coordinators = integration_data["coordinators"]
    else:
        coordinators = integration_data

    entities: list[SelectEntity] = []

    for family_id, coordinator_set in coordinators.items():
        if not isinstance(coordinator_set, dict):
            continue
        strategy_coord = coordinator_set.get("strategy")
        if not isinstance(strategy_coord, SunlitStrategyHistoryCoordinator):
            continue
        entities.extend(
            [
                SunlitTariffStrategySelect(
                    coordinator=strategy_coord,
                    entry_id=config_entry.entry_id,
                    family_id=family_id,
                    family_name=strategy_coord.family_name,
                    band="low",
                ),
                SunlitTariffStrategySelect(
                    coordinator=strategy_coord,
                    entry_id=config_entry.entry_id,
                    family_id=family_id,
                    family_name=strategy_coord.family_name,
                    band="high",
                ),
            ]
        )

    async_add_entities(entities, True)


class SunlitTariffStrategySelect(
    CoordinatorEntity[SunlitStrategyHistoryCoordinator], SelectEntity, RestoreEntity
):
    """Select entity for the per-band tariff strategy.

    Backs onto the coordinator's cached tariff setup. Selecting an option
    mutates the cache for this band and pushes the full bundle to
    /v1.6/tariffStrategy/add.
    """

    _attr_has_entity_name = True
    _attr_options = TARIFF_STRATEGY_OPTIONS
    _attr_icon = "mdi:battery-sync"

    def __init__(
        self,
        coordinator: SunlitStrategyHistoryCoordinator,
        entry_id: str,
        family_id: str,
        family_name: str,
        band: str,
    ) -> None:
        """Initialize the strategy select."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._family_id = family_id
        self._family_name = family_name
        self._band = band  # "low" | "high"

        slug = family_name.lower().replace(" ", "_")
        self._attr_unique_id = f"sunlit_{slug}_{family_id}_tariff_strategy_{band}"
        nice = "Low Price" if band == "low" else "High Price"
        self._attr_name = f"{nice} Strategy"

    @property
    def current_option(self) -> str | None:
        """Return the cached strategy for this band."""
        return self.coordinator.tariff_setup[self._band].get("strategy")

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to the family device."""
        return DeviceInfo(identifiers={(DOMAIN, f"family_{self._family_id}")})

    async def async_added_to_hass(self) -> None:
        """Restore the previously selected option from state cache."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in TARIFF_STRATEGY_OPTIONS:
            self.coordinator.update_tariff_setup_field(
                self._band, "strategy", last_state.state
            )

    async def async_select_option(self, option: str) -> None:
        """Push the new strategy to the API."""
        if option not in TARIFF_STRATEGY_OPTIONS:
            raise HomeAssistantError(f"Invalid strategy option: {option}")
        previous_option = self.coordinator.tariff_setup[self._band].get("strategy")
        self.coordinator.update_tariff_setup_field(self._band, "strategy", option)
        try:
            await self.coordinator.async_push_tariff_setup()
        except SunlitApiError as err:
            self.coordinator.update_tariff_setup_field(
                self._band, "strategy", previous_option
            )
            raise HomeAssistantError(
                f"Failed to set {self._band}-price strategy: {err}"
            ) from err
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Surface the cached low/high bundle for debugging."""
        setup = self.coordinator.tariff_setup
        return {
            "band": self._band,
            "low_price_strategy": dict(setup["low"]),
            "high_price_strategy": dict(setup["high"]),
        }
