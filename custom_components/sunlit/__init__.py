"""The Sunlit REST integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api_client import SunlitApiClient
from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    CONF_API_KEY,
    CONF_FAMILIES,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sunlit REST from a config entry."""

    api_key = entry.data[CONF_API_KEY]
    families = entry.data[CONF_FAMILIES]

    session = async_get_clientsession(hass)
    api_client = SunlitApiClient(session, api_key)

    coordinators = {}
    for family_id, family_info in families.items():
        coordinator = SunlitDataUpdateCoordinator(
            hass,
            api_client=api_client,
            family_id=str(family_info["id"]),
            family_name=family_info["name"],
        )

        await coordinator.async_config_entry_first_refresh()
        coordinators[family_id] = coordinator

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class SunlitDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the REST API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: SunlitApiClient,
        family_id: str,
        family_name: str,
    ) -> None:
        """Initialize."""
        self.api_client = api_client
        self.family_id = family_id
        self.family_name = family_name
        self.devices = {}  # Store device information

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{family_id}",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from REST API."""
        try:
            # Fetch device list for the family
            devices = await self.api_client.fetch_device_list(self.family_id)

            _LOGGER.debug(
                "Received %d devices for family %s", len(devices), self.family_name
            )

            # Store device information for device registry
            self.devices = {str(device["deviceId"]): device for device in devices}

            # Process device list into sensor data
            # Aggregate data from all devices
            sensor_data = {
                "family": {},  # Family aggregate data
                "devices": {},  # Individual device data
            }

            # Count devices by type and status
            device_count = len(devices)
            online_count = sum(1 for d in devices if d.get("status") == "Online")
            offline_count = sum(1 for d in devices if d.get("status") == "Offline")

            sensor_data["family"]["device_count"] = device_count
            sensor_data["family"]["online_devices"] = online_count
            sensor_data["family"]["offline_devices"] = offline_count

            # Aggregate power data
            total_ac_power = 0
            total_battery_level = 0
            battery_count = 0
            total_input_power = 0
            total_output_power = 0

            for device in devices:
                device_id = str(device["deviceId"])
                device_data = {}

                # Store common device attributes
                device_data["status"] = device.get("status", "Unknown")
                device_data["fault"] = device.get("fault", False)
                device_data["off"] = device.get("off", False)

                # Process based on device type
                device_type = device.get("deviceType")

                if device_type == "SHELLY_3EM_METER":
                    device_data["total_ac_power"] = device.get("totalAcPower")
                    device_data["daily_buy_energy"] = device.get("dailyBuyEnergy")
                    device_data["daily_ret_energy"] = device.get("dailyRetEnergy")
                    device_data["total_buy_energy"] = device.get("totalBuyEnergy")
                    device_data["total_ret_energy"] = device.get("totalRetEnergy")

                    if device.get("totalAcPower"):
                        total_ac_power += device["totalAcPower"]

                elif device_type == "YUNENG_MICRO_INVERTER":
                    if device.get("today"):
                        device_data["current_power"] = device["today"].get(
                            "currentPower"
                        )
                        device_data["total_power_generation"] = device["today"].get(
                            "totalPowerGeneration"
                        )
                        if device["today"].get("totalEarnings"):
                            device_data["daily_earnings"] = device["today"][
                                "totalEarnings"
                            ].get("earnings")

                elif device_type == "ENERGY_STORAGE_BATTERY":
                    device_data["battery_level"] = device.get("batteryLevel")
                    device_data["input_power_total"] = device.get("inputPowerTotal")
                    device_data["output_power_total"] = device.get("outputPowerTotal")

                    if device.get("batteryLevel") is not None:
                        total_battery_level += device["batteryLevel"]
                        battery_count += 1
                    if device.get("inputPowerTotal"):
                        total_input_power += device["inputPowerTotal"]
                    if device.get("outputPowerTotal"):
                        total_output_power += device["outputPowerTotal"]

                sensor_data["devices"][device_id] = device_data

            # Set family aggregate values
            sensor_data["family"]["total_ac_power"] = (
                total_ac_power if total_ac_power > 0 else None
            )
            sensor_data["family"]["average_battery_level"] = (
                total_battery_level / battery_count if battery_count > 0 else None
            )
            sensor_data["family"]["total_input_power"] = (
                total_input_power if total_input_power > 0 else None
            )
            sensor_data["family"]["total_output_power"] = (
                total_output_power if total_output_power > 0 else None
            )
            sensor_data["family"]["has_fault"] = any(d.get("fault") for d in devices)

            _LOGGER.debug(
                "Processed sensor data for family %s: %s", self.family_name, sensor_data
            )

            return sensor_data

        except Exception as err:
            raise UpdateFailed(
                f"Error fetching data for family {self.family_name}: {err}"
            ) from err
