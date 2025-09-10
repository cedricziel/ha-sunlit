"""Platform for binary sensor integration."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entities.device_binary_sensor import SunlitDeviceBinarySensor
from .entities.family_binary_sensor import SunlitFamilyBinarySensor

_LOGGER = logging.getLogger(__name__)


# Define which fields should be binary sensors
FAMILY_BINARY_SENSORS = {
    "has_fault": {
        "name": "Has Fault",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "icon": "mdi:alert-circle",
    },
    "battery_full": {
        "name": "Battery Full",
        "device_class": BinarySensorDeviceClass.BATTERY,
        "icon": "mdi:battery-check",
    },
    # New binary sensors from space/index endpoint
    "battery_bypass": {
        "name": "Battery Bypass",
        "device_class": None,
        "icon": "mdi:battery-off",
    },
    "battery_heater_1": {
        "name": "Battery Heater 1",
        "device_class": BinarySensorDeviceClass.HEAT,
        "icon": "mdi:radiator",
    },
    "battery_heater_2": {
        "name": "Battery Heater 2",
        "device_class": BinarySensorDeviceClass.HEAT,
        "icon": "mdi:radiator",
    },
    "battery_heater_3": {
        "name": "Battery Heater 3",
        "device_class": BinarySensorDeviceClass.HEAT,
        "icon": "mdi:radiator",
    },
    "boost_mode_enabled": {
        "name": "Boost Mode",
        "device_class": None,
        "icon": "mdi:rocket-launch",
    },
    "boost_mode_switching": {
        "name": "Boost Mode Switching",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "icon": "mdi:toggle-switch",
    },
    # Charging box strategy binary sensors
    "ev3600_auto_strategy_exist": {
        "name": "EV3600 Auto Strategy Exists",
        "device_class": None,
        "icon": "mdi:home-battery",
    },
    "ev3600_auto_strategy_running": {
        "name": "EV3600 Auto Strategy Running",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "icon": "mdi:sync",
    },
    "tariff_strategy_exist": {
        "name": "Tariff Strategy Exists",
        "device_class": None,
        "icon": "mdi:currency-usd",
    },
    "enable_local_smart_strategy": {
        "name": "Local Smart Strategy",
        "device_class": None,
        "icon": "mdi:brain",
    },
    "ac_couple_enabled": {
        "name": "AC Coupling",
        "device_class": None,
        "icon": "mdi:power-plug",
    },
    "charging_box_boost_on": {
        "name": "Charging Box Boost",
        "device_class": None,
        "icon": "mdi:lightning-bolt",
    },
}

DEVICE_BINARY_SENSORS = {
    "fault": {
        "name": "Fault",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "icon": "mdi:alert",
    },
    "off": {
        "name": "Power",  # Inverted - "off" field means device is off
        "device_class": BinarySensorDeviceClass.POWER,
        "icon": "mdi:power",
        "inverted": True,  # When "off" is True, binary sensor should be False
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinators = hass.data[DOMAIN][config_entry.entry_id]

    sensors = []

    # Process multiple family coordinators
    for _, coordinator in coordinators.items():
        if coordinator.data:
            # Create family binary sensors
            if "family" in coordinator.data:
                for key, config in FAMILY_BINARY_SENSORS.items():
                    if key in coordinator.data["family"]:
                        sensor_description = BinarySensorEntityDescription(
                            key=key,
                            name=config["name"],
                            device_class=config.get("device_class"),
                        )
                        sensor = SunlitFamilyBinarySensor(
                            coordinator=coordinator,
                            description=sensor_description,
                            entry_id=config_entry.entry_id,
                            family_id=coordinator.family_id,
                            family_name=coordinator.family_name,
                            icon=config.get("icon"),
                        )
                        sensors.append(sensor)

            # Create device binary sensors
            if "devices" in coordinator.data:
                for device_id, device_data in coordinator.data["devices"].items():
                    if device_id in coordinator.devices:
                        device_info = coordinator.devices[device_id]

                        for key, config in DEVICE_BINARY_SENSORS.items():
                            if key in device_data:
                                sensor_description = BinarySensorEntityDescription(
                                    key=key,
                                    name=config["name"],
                                    device_class=config.get("device_class"),
                                )
                                sensor = SunlitDeviceBinarySensor(
                                    coordinator=coordinator,
                                    description=sensor_description,
                                    entry_id=config_entry.entry_id,
                                    family_id=coordinator.family_id,
                                    family_name=coordinator.family_name,
                                    device_id=device_id,
                                    device_info_data=device_info,
                                    icon=config.get("icon"),
                                    inverted=config.get("inverted", False),
                                )
                                sensors.append(sensor)

    async_add_entities(sensors, True)
