"""Platform for binary sensor integration."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .dynamic_entities import async_setup_dynamic_entities
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
        # Not BinarySensorDeviceClass.BATTERY: that class means "low battery"
        # (on=Low, off=Normal), which would invert and mislabel this "is full"
        # flag. Leave unclassified so it shows a plain On/Off state.
        "device_class": None,
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
    # Local-mode / UPS status from strategy/device/status endpoint
    "battery_local_mode_enabled": {
        "name": "Battery Local Mode",
        "device_class": None,
        "icon": "mdi:home-lightning-bolt",
    },
    "aio_local_mode_enabled": {
        "name": "AIO Local Mode",
        "device_class": None,
        "icon": "mdi:home-lightning-bolt",
    },
    "aio_ups_enabled": {
        "name": "AIO UPS",
        "device_class": None,
        "icon": "mdi:power-plug-battery",
    },
    # Dynamic tariff status from tariff/index endpoint
    "rabot_has_contract": {
        "name": "Rabot Contract",
        "device_class": None,
        "icon": "mdi:file-document-check",
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
    # Diagnostics from device details (#159)
    "ota_in_progress": {
        "name": "Firmware Update In Progress",
        "device_class": BinarySensorDeviceClass.UPDATE,
        "icon": "mdi:cellphone-arrow-down",
    },
    "has_valid_meter": {
        "name": "Valid Meter",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
        "icon": "mdi:meter-electric",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    integration_data = hass.data[DOMAIN][config_entry.entry_id]

    # Handle both old and new data structures
    if isinstance(integration_data, dict) and "coordinators" in integration_data:
        coordinators = integration_data["coordinators"]
    else:
        # Fallback for old structure
        coordinators = integration_data

    def build_sensors(created_keys: set[str]) -> list[BinarySensorEntity]:
        """Build binary sensors whose keys have appeared but have no entity yet.

        Both loops below are driven by keys the cloud actually reported, so a
        device that was offline at startup contributes nothing on the first
        pass and gets its sensors on a later coordinator update instead.
        """
        sensors: list[BinarySensorEntity] = []

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

            # Skip if essential coordinators are missing
            if not family_coordinator or not device_coordinator:
                _LOGGER.warning(
                    "Missing essential coordinators for family %s", family_id
                )
                continue

            # Create family binary sensors
            if family_coordinator.data and "family" in family_coordinator.data:
                for key, config in FAMILY_BINARY_SENSORS.items():
                    if key in family_coordinator.data["family"]:
                        entity_key = f"{family_id}:family:{key}"
                        if entity_key in created_keys:
                            continue
                        created_keys.add(entity_key)

                        sensor_description = BinarySensorEntityDescription(
                            key=key,
                            name=config["name"],
                            device_class=config.get("device_class"),
                        )
                        sensor = SunlitFamilyBinarySensor(
                            coordinator=family_coordinator,
                            description=sensor_description,
                            entry_id=config_entry.entry_id,
                            family_id=family_coordinator.family_id,
                            family_name=family_coordinator.family_name,
                            icon=config.get("icon"),
                        )
                        sensors.append(sensor)

            # Create device binary sensors
            if device_coordinator.data and "devices" in device_coordinator.data:
                for device_id, device_data in device_coordinator.data[
                    "devices"
                ].items():
                    if (
                        device_coordinator.devices
                        and device_id in device_coordinator.devices
                    ):
                        device_info = device_coordinator.devices[device_id]

                        for key, config in DEVICE_BINARY_SENSORS.items():
                            if key in device_data:
                                entity_key = f"{family_id}:{device_id}:{key}"
                                if entity_key in created_keys:
                                    continue
                                created_keys.add(entity_key)

                                sensor_description = BinarySensorEntityDescription(
                                    key=key,
                                    name=config["name"],
                                    device_class=config.get("device_class"),
                                )
                                sensor = SunlitDeviceBinarySensor(
                                    coordinator=device_coordinator,
                                    description=sensor_description,
                                    entry_id=config_entry.entry_id,
                                    family_id=device_coordinator.family_id,
                                    family_name=device_coordinator.family_name,
                                    device_id=device_id,
                                    device_info_data=device_info,
                                    icon=config.get("icon"),
                                    inverted=config.get("inverted", False),
                                )
                                sensors.append(sensor)

        return sensors

    platform_coordinators: list = []
    for coordinator_set in coordinators.values():
        if isinstance(coordinator_set, dict):
            platform_coordinators.append(coordinator_set.get("family"))
            platform_coordinators.append(coordinator_set.get("device"))

    async_setup_dynamic_entities(
        config_entry,
        platform_coordinators,
        async_add_entities,
        build_sensors,
    )
