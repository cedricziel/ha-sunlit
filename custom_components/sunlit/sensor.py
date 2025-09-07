"""Platform for sensor integration."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
from .entities.family_sensor import SunlitFamilySensor
from .entities.device_sensor import SunlitDeviceSensor
from .entities.battery_module_sensor import SunlitBatteryModuleSensor
from .entities.helpers import (
    get_device_class_for_sensor,
    get_state_class_for_sensor,
    get_unit_for_sensor,
    get_icon_for_sensor,
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
                # Skip binary sensor fields (they're handled by binary_sensor platform)
                skip_fields = {"has_fault", "battery_full"}
                for key in coordinator.data["family"]:
                    if key in FAMILY_SENSORS and key not in skip_fields:
                        sensor_description = SensorEntityDescription(
                            key=key,
                            name=FAMILY_SENSORS[key],
                            device_class=get_device_class_for_sensor(key),
                            state_class=get_state_class_for_sensor(key),
                            native_unit_of_measurement=get_unit_for_sensor(key),
                        )
                        sensor = SunlitFamilySensor(
                            coordinator=coordinator,
                            description=sensor_description,
                            entry_id=config_entry.entry_id,
                            family_id=coordinator.family_id,
                            family_name=coordinator.family_name,
                        )
                        # Set icon if available
                        icon = get_icon_for_sensor(key)
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
                                    device_class=get_device_class_for_sensor(key),
                                    state_class=get_state_class_for_sensor(key),
                                    native_unit_of_measurement=get_unit_for_sensor(
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
                                icon = get_icon_for_sensor(key, device_type)
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
                                        device_class=get_device_class_for_sensor(sensor_key),
                                        state_class=get_state_class_for_sensor(sensor_key),
                                        native_unit_of_measurement=get_unit_for_sensor(sensor_key),
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
                                    icon = get_icon_for_sensor(sensor_key, device_type)
                                    if icon:
                                        sensor._attr_icon = icon
                                    sensors.append(sensor)

    async_add_entities(sensors, True)
