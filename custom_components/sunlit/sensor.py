"""Platform for sensor integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    PERCENTAGE,
)

from . import SunlitDataUpdateCoordinator
from .const import (
    DOMAIN,
    DEVICE_TYPE_METER,
    DEVICE_TYPE_INVERTER,
    DEVICE_TYPE_BATTERY,
    METER_SENSORS,
    INVERTER_SENSORS,
    BATTERY_SENSORS,
    FAMILY_SENSORS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinators = hass.data[DOMAIN][config_entry.entry_id]

    sensors = []

    # Process multiple family coordinators
    for _, coordinator in coordinators.items():
        if coordinator.data:
            # Create family aggregate sensors
            if "family" in coordinator.data:
                for key in coordinator.data["family"]:
                    if key in FAMILY_SENSORS:
                        sensor_description = SensorEntityDescription(
                            key=key,
                            name=FAMILY_SENSORS[key],
                            device_class=_get_device_class_for_sensor(key),
                            state_class=_get_state_class_for_sensor(key),
                            native_unit_of_measurement=_get_unit_for_sensor(key),
                        )
                        sensors.append(
                            SunlitFamilySensor(
                                coordinator=coordinator,
                                description=sensor_description,
                                entry_id=config_entry.entry_id,
                                family_id=coordinator.family_id,
                                family_name=coordinator.family_name,
                            )
                        )

            # Create individual device sensors
            if "devices" in coordinator.data:
                for device_id, device_data in coordinator.data["devices"].items():
                    if device_id in coordinator.devices:
                        device_info = coordinator.devices[device_id]
                        device_type = device_info.get("deviceType")

                        # Determine which sensors to create based on device type
                        sensor_map = {}
                        if device_type == DEVICE_TYPE_METER:
                            sensor_map = METER_SENSORS
                        elif device_type == DEVICE_TYPE_INVERTER:
                            sensor_map = INVERTER_SENSORS
                        elif device_type == DEVICE_TYPE_BATTERY:
                            sensor_map = BATTERY_SENSORS

                        # Create sensors for this device
                        for key in device_data:
                            if key in sensor_map:
                                sensor_description = SensorEntityDescription(
                                    key=key,
                                    name=sensor_map[key],
                                    device_class=_get_device_class_for_sensor(key),
                                    state_class=_get_state_class_for_sensor(key),
                                    native_unit_of_measurement=_get_unit_for_sensor(
                                        key
                                    ),
                                )
                                sensors.append(
                                    SunlitDeviceSensor(
                                        coordinator=coordinator,
                                        description=sensor_description,
                                        entry_id=config_entry.entry_id,
                                        family_id=coordinator.family_id,
                                        family_name=coordinator.family_name,
                                        device_id=device_id,
                                        device_info_data=device_info,
                                    )
                                )

                        # Add status sensor for all devices
                        if "status" in device_data:
                            sensor_description = SensorEntityDescription(
                                key="status",
                                name="Status",
                            )
                            sensors.append(
                                SunlitDeviceSensor(
                                    coordinator=coordinator,
                                    description=sensor_description,
                                    entry_id=config_entry.entry_id,
                                    family_id=coordinator.family_id,
                                    family_name=coordinator.family_name,
                                    device_id=device_id,
                                    device_info_data=device_info,
                                )
                            )

    async_add_entities(sensors, True)


def _get_device_class_for_sensor(key: str) -> SensorDeviceClass | None:
    """Get the appropriate device class for a sensor."""
    # Check for status fields first (they're text, not numeric)
    if "status" in key.lower():
        return None
    # battery_full is a boolean, not a battery percentage
    elif key == "battery_full":
        return None
    elif "power" in key.lower():
        return SensorDeviceClass.POWER
    elif "energy" in key.lower():
        return SensorDeviceClass.ENERGY
    elif "soc" in key.lower():
        return SensorDeviceClass.BATTERY
    elif "battery" in key.lower() or "level" in key.lower():
        return SensorDeviceClass.BATTERY
    elif key == "last_strategy_change":
        return SensorDeviceClass.TIMESTAMP
    elif key == "has_fault":
        return None  # Binary-like sensor but as regular sensor
    return None


def _get_state_class_for_sensor(key: str) -> SensorStateClass | None:
    """Get the appropriate state class for a sensor."""
    # Energy sensors need special handling
    if "energy" in key.lower():
        if "total" in key.lower():
            # Total energy counters that never reset
            return SensorStateClass.TOTAL_INCREASING
        elif "daily" in key.lower():
            # Daily energy counters that reset each day
            return SensorStateClass.TOTAL
        else:
            # Other energy sensors
            return SensorStateClass.TOTAL_INCREASING
    elif "power" in key.lower():
        return SensorStateClass.MEASUREMENT
    elif key in ["device_count", "online_devices", "offline_devices"]:
        return SensorStateClass.MEASUREMENT
    return None


def _get_unit_for_sensor(key: str) -> str | None:
    """Get the appropriate unit for a sensor."""
    if "power" in key.lower():
        return UnitOfPower.WATT
    elif "energy" in key.lower():
        return UnitOfEnergy.KILO_WATT_HOUR
    elif "soc" in key.lower():
        return PERCENTAGE
    elif "battery_level" in key or "average_battery_level" in key:
        return PERCENTAGE
    elif "earnings" in key:
        return "EUR"  # Could be made configurable
    return None


class SunlitFamilySensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sunlit family aggregate sensor."""

    def __init__(
        self,
        coordinator: SunlitDataUpdateCoordinator,
        description: SensorEntityDescription,
        entry_id: str,
        family_id: str,
        family_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry_id
        self._family_id = family_id
        self._family_name = family_name

        # Include family_id in unique_id to ensure uniqueness across families
        self._attr_unique_id = f"{entry_id}_{family_id}_family_{description.key}"

        # Human-readable name includes family name
        self._attr_name = f"{family_name} {description.name}"

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data and "family" in self.coordinator.data:
            value = self.coordinator.data["family"].get(self.entity_description.key)
            
            # Convert timestamp from milliseconds to datetime for timestamp sensors
            if self.entity_description.key == "last_strategy_change" and value:
                from datetime import datetime, timezone
                return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
            
            return value
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and (
            "family" in (self.coordinator.data or {})
            and self.entity_description.key in (self.coordinator.data.get("family", {}))
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the family hub."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"family_{self._family_id}")},
            name=f"{self._family_name} Solar System",
            manufacturer="Sunlit Solar",
            model="Family Hub",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {
            "family_id": self._family_id,
            "family_name": self._family_name,
        }
        
        # Add strategy history if available
        if (
            self.entity_description.key == "last_strategy_change"
            and self.coordinator.data
            and "family" in self.coordinator.data
        ):
            history = self.coordinator.data["family"].get("strategy_history", [])
            if history:
                # Format history for display
                formatted_history = []
                for entry in history[:10]:  # Last 10 entries
                    if entry.get("modifyDate"):
                        from datetime import datetime
                        timestamp = datetime.fromtimestamp(
                            entry["modifyDate"] / 1000
                        ).isoformat()
                    else:
                        timestamp = "Unknown"
                    
                    formatted_history.append({
                        "timestamp": timestamp,
                        "strategy": entry.get("strategy", "Unknown"),
                        "status": entry.get("status", "Unknown"),
                        "mode": entry.get("smartStrategyMode"),
                        "soc_min": entry.get("socMin"),
                        "soc_max": entry.get("socMax"),
                    })
                attrs["history"] = formatted_history
        
        return attrs


class SunlitDeviceSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sunlit device sensor."""

    def __init__(
        self,
        coordinator: SunlitDataUpdateCoordinator,
        description: SensorEntityDescription,
        entry_id: str,
        family_id: str,
        family_name: str,
        device_id: str,
        device_info_data: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry_id
        self._family_id = family_id
        self._family_name = family_name
        self._device_id = device_id
        self._device_info_data = device_info_data

        # Include device_id in unique_id to ensure uniqueness
        self._attr_unique_id = f"{entry_id}_{device_id}_{description.key}"

        # Human-readable name
        device_type = device_info_data.get("deviceType", "Device")
        self._attr_name = f"{device_type} {device_id} {description.name}"

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if (
            self.coordinator.data
            and "devices" in self.coordinator.data
            and self._device_id in self.coordinator.data["devices"]
        ):
            return self.coordinator.data["devices"][self._device_id].get(
                self.entity_description.key
            )
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and "devices" in (self.coordinator.data or {})
            and self._device_id in self.coordinator.data.get("devices", {})
            and self.entity_description.key
            in self.coordinator.data["devices"][self._device_id]
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this device."""
        device_type = self._device_info_data.get("deviceType", "Unknown")
        device_sn = self._device_info_data.get("deviceSn", self._device_id)

        # Use manufacturer from device data if available, otherwise map by type
        manufacturer = self._device_info_data.get("manufacturer")
        if not manufacturer:
            # Fallback mapping if manufacturer not provided
            if device_type == DEVICE_TYPE_METER:
                manufacturer = "Shelly"
            elif device_type == DEVICE_TYPE_INVERTER:
                manufacturer = "Yuneng"
            elif device_type == DEVICE_TYPE_BATTERY:
                manufacturer = "Highpower"
            else:
                manufacturer = "Unknown"

        device_info = DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            name=f"{device_type} ({self._device_id})",
            manufacturer=manufacturer,
            model=device_type,
            via_device=(DOMAIN, f"family_{self._family_id}"),
        )
        
        # Add firmware version if available
        if "firmwareVersion" in self._device_info_data:
            device_info["sw_version"] = self._device_info_data["firmwareVersion"]
        
        # Add hardware version if available  
        if "hwVersion" in self._device_info_data:
            device_info["hw_version"] = self._device_info_data["hwVersion"]
            
        return device_info

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {
            "device_id": self._device_id,
            "device_type": self._device_info_data.get("deviceType"),
            "device_sn": self._device_info_data.get("deviceSn"),
        }

        # Add device-specific attributes from coordinator data
        if (
            "devices" in (self.coordinator.data or {})
            and self._device_id in self.coordinator.data["devices"]
        ):
            device_data = self.coordinator.data["devices"][self._device_id]
            if "fault" in device_data:
                attrs["fault"] = device_data["fault"]
            if "off" in device_data:
                attrs["off"] = device_data["off"]
        
        # Add additional device info if available
        if "systemMultiStatus" in self._device_info_data:
            attrs["system_status"] = self._device_info_data["systemMultiStatus"]
        if "supportReboot" in self._device_info_data:
            attrs["support_reboot"] = self._device_info_data["supportReboot"]
        if "ssid" in self._device_info_data:
            attrs["wifi_ssid"] = self._device_info_data["ssid"]

        return attrs
