"""Platform for sensor integration."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BATTERY_MODULE_SENSORS,
    BATTERY_SENSORS,
    DEVICE_TYPE_BATTERY,
    DEVICE_TYPE_INVERTER,
    DEVICE_TYPE_INVERTER_SOLAR,
    DEVICE_TYPE_METER,
    DEVICE_TYPE_METER_PRO,
    DOMAIN,
    FAMILY_SENSORS,
    INVERTER_SENSORS,
    METER_SENSORS,
)
from .entities.battery_module_sensor import SunlitBatteryModuleSensor
from .entities.battery_sensor import SunlitBatterySensor
from .entities.family_sensor import SunlitFamilySensor
from .entities.helpers import (
    get_device_class_for_sensor,
    get_icon_for_sensor,
    get_state_class_for_sensor,
    get_unit_for_sensor,
)
from .entities.inverter_sensor import SunlitInverterSensor
from .entities.meter_sensor import SunlitMeterSensor
from .entities.unknown_device_sensor import SunlitUnknownDeviceSensor

_LOGGER = logging.getLogger(__name__)


def create_device_sensor(device_type: str, **kwargs):
    """Factory function to create appropriate device sensor class."""
    sensor_class_map = {
        DEVICE_TYPE_METER: SunlitMeterSensor,
        DEVICE_TYPE_METER_PRO: SunlitMeterSensor,  # Pro variant uses same sensor class
        DEVICE_TYPE_INVERTER: SunlitInverterSensor,
        DEVICE_TYPE_INVERTER_SOLAR: SunlitInverterSensor,  # Generic variant uses same sensor class
        DEVICE_TYPE_BATTERY: SunlitBatterySensor,
    }

    sensor_class = sensor_class_map.get(device_type, SunlitUnknownDeviceSensor)
    return sensor_class(**kwargs)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    integration_data = hass.data[DOMAIN][config_entry.entry_id]

    # Handle both old and new data structures
    if isinstance(integration_data, dict) and "coordinators" in integration_data:
        coordinators = integration_data["coordinators"]
    else:
        # Fallback for old structure
        coordinators = integration_data

    sensors = []

    # Process multiple family coordinators
    for family_id, coordinator_set in coordinators.items():
        # Use the new specialized coordinators
        if not isinstance(coordinator_set, dict):
            # Handle old coordinator structure for backwards compatibility
            _LOGGER.warning(
                "Old coordinator structure detected, skipping family %s", family_id
            )
            continue

        family_coordinator = coordinator_set.get("family")
        device_coordinator = coordinator_set.get("device")
        strategy_coordinator = coordinator_set.get("strategy")
        mppt_coordinator = coordinator_set.get("mppt")

        # Skip if essential coordinators are missing
        if not family_coordinator or not device_coordinator:
            _LOGGER.warning("Missing essential coordinators for family %s", family_id)
            continue

        if family_coordinator.data:
            # Create family aggregate sensors from family coordinator
            if "family" in family_coordinator.data:
                # Skip binary sensor fields (they're handled by binary_sensor platform)
                skip_fields = {"has_fault", "battery_full"}
                family_data = family_coordinator.data["family"]

                # Add strategy data if available
                if (
                    strategy_coordinator
                    and strategy_coordinator.data
                    and "strategy" in strategy_coordinator.data
                ):
                    family_data.update(strategy_coordinator.data["strategy"])

                # Add MPPT energy data if available
                if (
                    mppt_coordinator
                    and mppt_coordinator.data
                    and "mppt_energy" in mppt_coordinator.data
                ):
                    family_data.update(mppt_coordinator.data["mppt_energy"])

                # Add device aggregates if available
                if (
                    device_coordinator
                    and device_coordinator.data
                    and "aggregates" in device_coordinator.data
                ):
                    family_data.update(device_coordinator.data["aggregates"])

                for key in family_data:
                    if key in FAMILY_SENSORS and key not in skip_fields:
                        sensor_description = SensorEntityDescription(
                            key=key,
                            name=FAMILY_SENSORS[key],
                            device_class=get_device_class_for_sensor(key),
                            state_class=get_state_class_for_sensor(key),
                            native_unit_of_measurement=get_unit_for_sensor(key),
                        )
                        # Use appropriate coordinator based on data source
                        if key in [
                            "last_strategy_type",
                            "last_strategy_change",
                            "last_strategy_status",
                            "strategy_changes_today",
                            "strategy_history",
                        ]:
                            coord = (
                                strategy_coordinator
                                if strategy_coordinator
                                else family_coordinator
                            )
                        elif key.startswith("mppt") and "energy" in key:
                            coord = (
                                mppt_coordinator
                                if mppt_coordinator
                                else family_coordinator
                            )
                        elif key in [
                            "total_solar_power",
                            "total_solar_energy",
                            "total_grid_export_energy",
                            "daily_grid_export_energy",
                        ]:
                            coord = (
                                device_coordinator
                                if device_coordinator
                                else family_coordinator
                            )
                        else:
                            coord = family_coordinator

                        sensor = SunlitFamilySensor(
                            coordinator=coord,
                            description=sensor_description,
                            entry_id=config_entry.entry_id,
                            family_id=family_coordinator.family_id,
                            family_name=family_coordinator.family_name,
                        )
                        # Set icon if available
                        icon = get_icon_for_sensor(key)
                        if icon:
                            sensor._attr_icon = icon
                        sensors.append(sensor)

            # Create individual device sensors from device coordinator
            if device_coordinator.data and "devices" in device_coordinator.data:
                for device_id, device_data in device_coordinator.data[
                    "devices"
                ].items():
                    if (
                        device_coordinator.devices
                        and device_id in device_coordinator.devices
                    ):
                        device_info = device_coordinator.devices[device_id]
                        device_type = device_info.get("deviceType")

                        # Determine which sensors to create based on device type
                        sensor_map = {}
                        if device_type in [DEVICE_TYPE_METER, DEVICE_TYPE_METER_PRO]:
                            sensor_map = METER_SENSORS
                        elif device_type in [
                            DEVICE_TYPE_INVERTER,
                            DEVICE_TYPE_INVERTER_SOLAR,
                        ]:
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
                                    native_unit_of_measurement=get_unit_for_sensor(key),
                                )
                                sensor = create_device_sensor(
                                    device_type=device_type,
                                    coordinator=device_coordinator,
                                    description=sensor_description,
                                    entry_id=config_entry.entry_id,
                                    family_id=device_coordinator.family_id,
                                    family_name=device_coordinator.family_name,
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
                        sensor = create_device_sensor(
                            device_type=device_type,
                            coordinator=device_coordinator,
                            description=sensor_description,
                            entry_id=config_entry.entry_id,
                            family_id=device_coordinator.family_id,
                            family_name=device_coordinator.family_name,
                            device_id=device_id,
                            device_info_data=device_info,
                        )
                        # Set status icon
                        sensor._attr_icon = "mdi:information-outline"
                        sensors.append(sensor)

                        # For battery devices, create virtual devices for battery modules
                        if device_type == DEVICE_TYPE_BATTERY:
                            # Get actual number of battery modules from device coordinator
                            module_count = device_coordinator.get_battery_module_count(
                                device_id
                            )

                            _LOGGER.debug(
                                "Creating battery module sensors for device %s: %d modules",
                                device_id,
                                module_count,
                            )

                            # Create virtual devices only for existing battery modules
                            for module_num in range(1, module_count + 1):
                                # Create sensors for this battery module
                                for (
                                    suffix,
                                    friendly_name,
                                ) in BATTERY_MODULE_SENSORS.items():
                                    sensor_key = f"battery{module_num}{suffix}"

                                    sensor_description = SensorEntityDescription(
                                        key=sensor_key,
                                        name=friendly_name,
                                        device_class=get_device_class_for_sensor(
                                            sensor_key
                                        ),
                                        state_class=get_state_class_for_sensor(
                                            sensor_key
                                        ),
                                        native_unit_of_measurement=get_unit_for_sensor(
                                            sensor_key
                                        ),
                                    )

                                    sensor = SunlitBatteryModuleSensor(
                                        coordinator=device_coordinator,
                                        description=sensor_description,
                                        entry_id=config_entry.entry_id,
                                        family_id=device_coordinator.family_id,
                                        family_name=device_coordinator.family_name,
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
