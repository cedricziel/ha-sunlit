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
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTime,
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
    BATTERY_MODULE_SENSORS,
    FAMILY_SENSORS,
)

_LOGGER = logging.getLogger(__name__)


def normalize_device_type(device_type: str) -> str:
    """Normalize device type for use in unique_id.

    Maps device types to short, readable names:
    - ENERGY_STORAGE_BATTERY -> battery
    - YUNENG_MICRO_INVERTER -> inverter
    - SHELLY_3EM_METER -> meter
    """
    type_map = {
        DEVICE_TYPE_BATTERY: "battery",
        DEVICE_TYPE_INVERTER: "inverter",
        DEVICE_TYPE_METER: "meter",
    }
    return type_map.get(
        device_type, device_type.lower().replace("_", "").replace(" ", "")
    )


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
                # Skip binary sensor fields (they're handled by binary_sensor platform)
                skip_fields = {"has_fault", "battery_full"}
                for key in coordinator.data["family"]:
                    if key in FAMILY_SENSORS and key not in skip_fields:
                        sensor_description = SensorEntityDescription(
                            key=key,
                            name=FAMILY_SENSORS[key],
                            device_class=_get_device_class_for_sensor(key),
                            state_class=_get_state_class_for_sensor(key),
                            native_unit_of_measurement=_get_unit_for_sensor(key),
                        )
                        sensor = SunlitFamilySensor(
                            coordinator=coordinator,
                            description=sensor_description,
                            entry_id=config_entry.entry_id,
                            family_id=coordinator.family_id,
                            family_name=coordinator.family_name,
                        )
                        # Set icon if available
                        icon = _get_icon_for_sensor(key)
                        if icon:
                            sensor._attr_icon = icon
                        sensors.append(sensor)

            # Create individual device sensors
            if "devices" in coordinator.data:
                for device_id in coordinator.data["devices"]:
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

                        # Create ALL sensors defined for this device type
                        # This ensures sensors are created even if data is not yet available
                        # Skip binary sensor fields (handled by binary_sensor platform)
                        skip_device_fields = {"fault", "off"}
                        for key, name in sensor_map.items():
                            if key not in skip_device_fields:
                                sensor_description = SensorEntityDescription(
                                    key=key,
                                    name=name,
                                    device_class=_get_device_class_for_sensor(key),
                                    state_class=_get_state_class_for_sensor(key),
                                    native_unit_of_measurement=_get_unit_for_sensor(
                                        key
                                    ),
                                )
                                sensor = SunlitDeviceSensor(
                                    coordinator=coordinator,
                                    description=sensor_description,
                                    entry_id=config_entry.entry_id,
                                    family_id=coordinator.family_id,
                                    family_name=coordinator.family_name,
                                    device_id=device_id,
                                    device_info_data=device_info,
                                )
                                # Set icon if available
                                icon = _get_icon_for_sensor(key, device_type)
                                if icon:
                                    sensor._attr_icon = icon
                                sensors.append(sensor)

                        # Always add status sensor for all devices (text state)
                        sensor_description = SensorEntityDescription(
                            key="status",
                            name="Status",
                        )
                        sensor = SunlitDeviceSensor(
                            coordinator=coordinator,
                            description=sensor_description,
                            entry_id=config_entry.entry_id,
                            family_id=coordinator.family_id,
                            family_name=coordinator.family_name,
                            device_id=device_id,
                            device_info_data=device_info,
                        )
                        # Set status icon
                        sensor._attr_icon = "mdi:information-outline"
                        sensors.append(sensor)
                        
                        # For battery devices, create virtual devices for battery modules
                        if device_type == DEVICE_TYPE_BATTERY:
                            # Check for battery modules (1, 2, 3) and create virtual devices
                            for module_num in [1, 2, 3]:
                                # Check if this module exists (by checking if any of its data is present)
                                module_soc_key = f"battery{module_num}Soc"
                                
                                # Always create module devices for batteries to ensure stable entities
                                # Create sensors for this battery module
                                for suffix, friendly_name in BATTERY_MODULE_SENSORS.items():
                                    sensor_key = f"battery{module_num}{suffix}"
                                    
                                    sensor_description = SensorEntityDescription(
                                        key=sensor_key,
                                        name=friendly_name,
                                        device_class=_get_device_class_for_sensor(sensor_key),
                                        state_class=_get_state_class_for_sensor(sensor_key),
                                        native_unit_of_measurement=_get_unit_for_sensor(sensor_key),
                                    )
                                    
                                    sensor = SunlitBatteryModuleSensor(
                                        coordinator=coordinator,
                                        description=sensor_description,
                                        entry_id=config_entry.entry_id,
                                        family_id=coordinator.family_id,
                                        family_name=coordinator.family_name,
                                        device_id=device_id,
                                        device_info_data=device_info,
                                        module_number=module_num,
                                    )
                                    
                                    # Set icon if available
                                    icon = _get_icon_for_sensor(sensor_key, device_type)
                                    if icon:
                                        sensor._attr_icon = icon
                                    sensors.append(sensor)

    async_add_entities(sensors, True)


def _get_device_class_for_sensor(key: str) -> SensorDeviceClass | None:
    """Get the appropriate device class for a sensor."""
    # Check for status and strategy fields first (they're text, not numeric)
    if "status" in key.lower() or "strategy" in key.lower():
        return None
    # battery_full is a boolean, not a battery percentage
    elif key == "battery_full":
        return None
    # Battery capacity
    elif "capacity" in key.lower():
        return SensorDeviceClass.ENERGY
    # Time remaining sensors
    elif "remaining" in key.lower():
        return SensorDeviceClass.DURATION
    # MPPT voltage sensors
    elif "invol" in key.lower() or "voltage" in key.lower():
        return SensorDeviceClass.VOLTAGE
    # MPPT current sensors
    elif "incur" in key.lower() or "current" in key.lower():
        return SensorDeviceClass.CURRENT
    # total_power_generation is actually energy despite the name
    elif key == "total_power_generation":
        return SensorDeviceClass.ENERGY
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
    # Static configuration values don't need state class
    if key in ["rated_power", "max_output_power"]:
        return None
    # Special case: total_power_generation is cumulative energy
    elif key == "total_power_generation":
        return SensorStateClass.TOTAL_INCREASING
    # Energy sensors need special handling
    elif "energy" in key.lower():
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
    elif key in [
        "device_count",
        "online_devices",
        "offline_devices",
        "strategy_changes_today",
    ]:
        return SensorStateClass.MEASUREMENT
    return None


def _get_unit_for_sensor(key: str) -> str | None:
    """Get the appropriate unit for a sensor."""
    # Battery capacity
    if "capacity" in key.lower():
        return UnitOfEnergy.KILO_WATT_HOUR
    # Special case: total_power_generation is actually energy in kWh
    elif key == "total_power_generation":
        return UnitOfEnergy.KILO_WATT_HOUR
    # Time remaining sensors
    elif "remaining" in key.lower():
        return UnitOfTime.MINUTES
    # MPPT voltage sensors
    elif "invol" in key.lower() or "voltage" in key.lower():
        return UnitOfElectricPotential.VOLT
    # MPPT current sensors  
    elif "incur" in key.lower() or "current" in key.lower():
        return UnitOfElectricCurrent.AMPERE
    # Ensure rated_power and max_output_power get W units
    elif key in ["rated_power", "max_output_power"] or "power" in key.lower():
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


def _get_icon_for_sensor(key: str, device_type: str = None) -> str | None:
    """Get the appropriate icon for a sensor."""
    # MPPT (Maximum Power Point Tracking) related
    if "mppt" in key.lower():
        if "vol" in key.lower():
            return "mdi:sine-wave"
        elif "cur" in key.lower():
            return "mdi:current-dc"
        elif "power" in key.lower():
            return "mdi:solar-power-variant"
        else:
            return "mdi:solar-panel-large"
    # Time remaining
    elif "remaining" in key.lower():
        if "charge" in key.lower():
            return "mdi:timer-sand"
        elif "discharge" in key.lower():
            return "mdi:timer-sand-empty"
    # Solar/Inverter related
    elif device_type == "YUNENG_MICRO_INVERTER" or "generation" in key:
        return "mdi:solar-power"
    # Battery related
    elif "battery_full" in key:
        return "mdi:battery-check"
    elif "battery_level" in key or "average_battery_level" in key:
        return "mdi:battery-50"
    elif "batterysoc" in key.lower() or "soc" in key.lower():
        return "mdi:battery-outline"
    elif device_type == "ENERGY_STORAGE_BATTERY":
        if "input" in key:
            return "mdi:battery-charging"
        elif "output" in key:
            return "mdi:battery-arrow-down"
        else:
            return "mdi:battery"
    # Grid/Meter related
    elif device_type == "SHELLY_3EM_METER" or "buy" in key or "ret" in key:
        if "buy" in key:
            return "mdi:transmission-tower-import"
        elif "ret" in key or "return" in key:
            return "mdi:transmission-tower-export"
        else:
            return "mdi:transmission-tower"
    # Power related
    elif "power" in key:
        if "rated" in key:
            return "mdi:gauge"
        elif "max" in key:
            return "mdi:gauge-full"
        else:
            return "mdi:flash"
    # Energy related
    elif "energy" in key:
        return "mdi:lightning-bolt"
    # Status related
    elif "battery_device_status" in key:
        return "mdi:battery-sync"
    elif "inverter_device_status" in key:
        return "mdi:solar-panel"
    elif "meter_device_status" in key:
        return "mdi:meter-electric"
    elif "battery_status" in key:
        return "mdi:battery-heart"
    elif "last_strategy_status" in key:
        return "mdi:check-circle"
    elif "status" in key:
        return "mdi:information-outline"
    elif "online" in key:
        return "mdi:check-network"
    elif "offline" in key:
        return "mdi:close-network"
    elif "fault" in key:
        return "mdi:alert-circle"
    # Strategy related
    elif "last_strategy_change" in key:
        return "mdi:clock-outline"
    elif "last_strategy_type" in key:
        return "mdi:history"
    elif "strategy_changes" in key:
        return "mdi:counter"
    elif "strategy" in key:
        return "mdi:cog"
    # Device count
    elif "device_count" in key or "devices" in key:
        return "mdi:counter"
    # Earnings
    elif "earnings" in key:
        return "mdi:cash"
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
        self._attr_unique_id = f"sunlit_{family_id}_{description.key}"

        # Human-readable name
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
            model="Solar Management Hub",
            configuration_url="https://sunlitsolar.de",
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

                    formatted_history.append(
                        {
                            "timestamp": timestamp,
                            "strategy": entry.get("strategy", "Unknown"),
                            "status": entry.get("status", "Unknown"),
                            "mode": entry.get("smartStrategyMode"),
                            "soc_min": entry.get("socMin"),
                            "soc_max": entry.get("socMax"),
                        }
                    )
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

        # Include family_id and normalized device type in unique_id
        device_type = device_info_data.get("deviceType", "Device")
        normalized_type = normalize_device_type(device_type)
        self._attr_unique_id = (
            f"sunlit_{family_id}_{normalized_type}_{device_id}_{description.key}"
        )

        # Human-readable name
        self._attr_name = f"{device_type} {device_id} {description.name}"

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        # Special handling for static battery capacity
        if self.entity_description.key == "battery_capacity":
            device_type = self._device_info_data.get("deviceType")
            if device_type == DEVICE_TYPE_BATTERY:
                return 2.15  # kWh nominal capacity for BK215
            return None
            
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
        # Entity is available as long as the device exists in the data
        # Even if the specific sensor value is not present (None/null)
        return (
            self.coordinator.last_update_success
            and "devices" in (self.coordinator.data or {})
            and self._device_id in self.coordinator.data.get("devices", {})
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this device."""
        device_type = self._device_info_data.get("deviceType", "Unknown")
        device_sn = self._device_info_data.get("deviceSn", self._device_id)

        # Use manufacturer from device data if available, otherwise map by type
        manufacturer = self._device_info_data.get("manufacturer")
        model_name = device_type
        
        if not manufacturer:
            # Fallback mapping if manufacturer not provided
            if device_type == DEVICE_TYPE_METER:
                manufacturer = "Shelly"
                model_name = "3EM Smart Meter"
            elif device_type == DEVICE_TYPE_INVERTER:
                manufacturer = "Yuneng"
                model_name = "Micro Inverter"
            elif device_type == DEVICE_TYPE_BATTERY:
                manufacturer = "Highpower"
                model_name = "BK215 Energy Storage System"
            else:
                manufacturer = "Unknown"

        device_info = DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            name=f"{device_type} ({self._device_id})",
            manufacturer=manufacturer,
            model=model_name,
            serial_number=device_sn if device_sn != self._device_id else None,
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


class SunlitBatteryModuleSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sunlit battery module sensor (virtual device)."""

    def __init__(
        self,
        coordinator: SunlitDataUpdateCoordinator,
        description: SensorEntityDescription,
        entry_id: str,
        family_id: str,
        family_name: str,
        device_id: str,
        device_info_data: dict[str, Any],
        module_number: int,
    ) -> None:
        """Initialize the battery module sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry_id
        self._family_id = family_id
        self._family_name = family_name
        self._device_id = device_id
        self._device_info_data = device_info_data
        self._module_number = module_number

        # Include module number in unique_id
        device_type = device_info_data.get("deviceType", "Device")
        normalized_type = normalize_device_type(device_type)
        self._attr_unique_id = (
            f"sunlit_{family_id}_{normalized_type}_{device_id}_module{module_number}_{description.key}"
        )

        # Human-readable name for module sensor
        self._attr_name = f"Module {module_number} {description.name}"

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        # Special handling for static battery module capacity
        if self.entity_description.key == "capacity":
            return 2.15  # kWh nominal capacity for B215 module
            
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
        # Entity is available as long as the device exists in the data
        return (
            self.coordinator.last_update_success
            and "devices" in (self.coordinator.data or {})
            and self._device_id in self.coordinator.data.get("devices", {})
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this virtual battery module."""
        device_sn = self._device_info_data.get("deviceSn", self._device_id)
        
        # Create a virtual device for this battery module
        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device_sn}_module{self._module_number}")},
            name=f"Battery Module {self._module_number}",
            manufacturer="Highpower",
            model=f"B215 Extension Module {self._module_number}",
            via_device=(DOMAIN, device_sn),  # Links to main battery unit
        )
        
        return device_info

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {
            "main_device_id": self._device_id,
            "module_number": self._module_number,
            "parent_device_sn": self._device_info_data.get("deviceSn"),
        }
        
        return attrs
