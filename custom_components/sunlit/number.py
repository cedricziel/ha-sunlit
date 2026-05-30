"""Number platform for the Sunlit integration: tariff strategy SOC limits."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api_client import SunlitApiError
from .const import DOMAIN
from .coordinators.strategy import SunlitStrategyHistoryCoordinator

# (band, field, friendly suffix)
_NUMBER_FIELDS: list[tuple[str, str, str]] = [
    ("low", "socMin", "Low Price SOC Min"),
    ("low", "socMax", "Low Price SOC Max"),
    ("high", "socMin", "High Price SOC Min"),
    ("high", "socMax", "High Price SOC Max"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform."""
    integration_data = hass.data[DOMAIN][config_entry.entry_id]

    if isinstance(integration_data, dict) and "coordinators" in integration_data:
        coordinators = integration_data["coordinators"]
    else:
        coordinators = integration_data

    entities: list[NumberEntity] = []
    for family_id, coordinator_set in coordinators.items():
        if not isinstance(coordinator_set, dict):
            continue
        strategy_coord = coordinator_set.get("strategy")
        if not isinstance(strategy_coord, SunlitStrategyHistoryCoordinator):
            continue
        for band, field, suffix in _NUMBER_FIELDS:
            entities.append(
                SunlitTariffSocNumber(
                    coordinator=strategy_coord,
                    entry_id=config_entry.entry_id,
                    family_id=family_id,
                    family_name=strategy_coord.family_name,
                    band=band,
                    field=field,
                    name_suffix=suffix,
                )
            )

    async_add_entities(entities, True)


class SunlitTariffSocNumber(
    CoordinatorEntity[SunlitStrategyHistoryCoordinator], NumberEntity, RestoreEntity
):
    """Number entity controlling one SOC limit field of the tariff strategy."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:battery-charging"

    def __init__(
        self,
        coordinator: SunlitStrategyHistoryCoordinator,
        entry_id: str,
        family_id: str,
        family_name: str,
        band: str,
        field: str,
        name_suffix: str,
    ) -> None:
        """Initialize the SOC number entity."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._family_id = family_id
        self._family_name = family_name
        self._band = band
        self._field = field

        slug = family_name.lower().replace(" ", "_")
        self._attr_unique_id = f"sunlit_{slug}_{family_id}_tariff_{band}_{field}"
        self._attr_name = name_suffix

    @property
    def native_value(self) -> float | None:
        """Return the cached SOC value for this field."""
        value = self.coordinator.tariff_setup[self._band].get(self._field)
        if value is None:
            return None
        return float(value)

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to the family device."""
        return DeviceInfo(identifiers={(DOMAIN, f"family_{self._family_id}")})

    async def async_added_to_hass(self) -> None:
        """Restore last value into the coordinator cache."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                self.coordinator.update_tariff_setup_field(
                    self._band, self._field, int(float(last_state.state))
                )
            except (TypeError, ValueError):
                pass

    async def async_set_native_value(self, value: float) -> None:
        """Push a new SOC limit to the API."""
        int_value = int(value)
        # Basic sanity: keep min < max for a band
        other_field = "socMax" if self._field == "socMin" else "socMin"
        other_value = self.coordinator.tariff_setup[self._band].get(other_field)
        if other_value is not None:
            if self._field == "socMin" and int_value >= int(other_value):
                raise HomeAssistantError(
                    f"{self._band}-price socMin must be < socMax ({other_value})"
                )
            if self._field == "socMax" and int_value <= int(other_value):
                raise HomeAssistantError(
                    f"{self._band}-price socMax must be > socMin ({other_value})"
                )

        previous_value = self.coordinator.tariff_setup[self._band].get(self._field)
        self.coordinator.update_tariff_setup_field(self._band, self._field, int_value)
        try:
            await self.coordinator.async_push_tariff_setup()
        except SunlitApiError as err:
            self.coordinator.update_tariff_setup_field(
                self._band, self._field, previous_value
            )
            raise HomeAssistantError(
                f"Failed to set {self._band}-price {self._field}: {err}"
            ) from err
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose band/field for diagnostics."""
        return {"band": self._band, "field": self._field}
