"""Device-level data coordinator for Sunlit integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..api_client import SunlitApiClient
from ..const import DEFAULT_SCAN_INTERVAL
from ..event_manager import SunlitEventManager

_LOGGER = logging.getLogger(__name__)


class SunlitDeviceCoordinator(DataUpdateCoordinator):
    """Coordinator for device-level data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: SunlitApiClient,
        family_id: str,
        family_name: str,
        is_global: bool = False,
        event_manager: SunlitEventManager | None = None,
    ) -> None:
        """Initialize the device coordinator."""
        self.api_client = api_client
        self.family_id = family_id
        self.family_name = family_name
        self.is_global = is_global
        self.devices = {}  # Store device info for registry
        self.event_manager = event_manager

        super().__init__(
            hass,
            _LOGGER,
            name=f"Sunlit Devices {family_name}",
            update_interval=DEFAULT_SCAN_INTERVAL,  # 30 seconds
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch device-level data from REST API."""
        try:
            # Fetch device list
            if self.is_global:
                all_devices = await self.api_client.get_device_list()
                devices = [d for d in all_devices if d.get("spaceId") is None]
            else:
                devices = await self.api_client.fetch_device_list(self.family_id)

            _LOGGER.debug(
                "Received %d devices for family %s", len(devices), self.family_name
            )

            # Store device information for device registry
            self.devices = {str(device["deviceId"]): device for device in devices}

            # Process device data
            device_data = {}

            # Aggregates for family-level metrics
            total_grid_export = 0
            daily_grid_export = 0
            total_solar_power = 0
            total_solar_energy = 0

            for device in devices:
                device_id = str(device["deviceId"])
                data = {}

                # Common attributes
                data["status"] = device.get("status", "Unknown")
                data["fault"] = device.get("fault", False)
                data["off"] = device.get("off", False)
                data["deviceType"] = device.get("deviceType")

                device_type = device.get("deviceType")

                if device_type in ["SHELLY_3EM_METER", "SHELLY_PRO3EM_METER"]:
                    await self._process_meter_device(device, device_id, data)
                    # Update aggregates
                    if device.get("totalRetEnergy") is not None:
                        total_grid_export += device["totalRetEnergy"]
                    if device.get("dailyRetEnergy") is not None:
                        daily_grid_export += device["dailyRetEnergy"]

                elif device_type in ["YUNENG_MICRO_INVERTER", "SOLAR_MICRO_INVERTER"]:
                    await self._process_inverter_device(device, device_id, data)
                    # Update aggregates
                    if data.get("current_power") is not None:
                        total_solar_power += data["current_power"]
                    if data.get("total_power_generation") is not None:
                        total_solar_energy += data["total_power_generation"]

                elif device_type == "ENERGY_STORAGE_BATTERY":
                    await self._process_battery_device(device, device_id, data)

                device_data[device_id] = data

            # Add aggregated metrics
            result = {
                "devices": device_data,
                "aggregates": {
                    "total_solar_power": total_solar_power
                    if total_solar_power > 0
                    else None,
                    "total_solar_energy": round(total_solar_energy, 3)
                    if total_solar_energy > 0
                    else 0,
                    "total_grid_export_energy": round(total_grid_export, 2)
                    if total_grid_export > 0
                    else 0,
                    "daily_grid_export_energy": round(daily_grid_export, 2)
                    if daily_grid_export > 0
                    else 0,
                },
            }

            return result

        except Exception as err:
            raise UpdateFailed(
                f"Error fetching device data for {self.family_name}: {err}"
            ) from err

    async def _process_meter_device(
        self, device: dict, device_id: str, data: dict
    ) -> None:
        """Process meter device data."""
        data["total_ac_power"] = device.get("totalAcPower")
        data["daily_buy_energy"] = device.get("dailyBuyEnergy")
        data["daily_ret_energy"] = device.get("dailyRetEnergy")
        data["total_buy_energy"] = device.get("totalBuyEnergy")
        data["total_ret_energy"] = device.get("totalRetEnergy")

        # Fetch detailed statistics for online meters
        if device.get("status") == "Online":
            try:
                stats = await self.api_client.fetch_device_statistics(device_id)
                for key in [
                    "totalAcPower",
                    "dailyBuyEnergy",
                    "dailyRetEnergy",
                    "totalBuyEnergy",
                    "totalRetEnergy",
                ]:
                    if stats.get(key) is not None:
                        data[key.lower()] = stats[key]
            except Exception as err:
                _LOGGER.warning(
                    "Failed to fetch meter statistics for %s: %s",
                    device_id,
                    err,
                )

    async def _process_inverter_device(
        self, device: dict, device_id: str, data: dict
    ) -> None:
        """Process inverter device data."""
        # Handle data structure variations
        if device.get("today"):
            data["current_power"] = device["today"].get("currentPower")
            data["total_power_generation"] = device["today"].get("totalPowerGeneration")
            if device["today"].get("totalEarnings"):
                data["daily_earnings"] = device["today"]["totalEarnings"].get(
                    "earnings"
                )
        else:
            data["current_power"] = device.get("currentPower")
            data["total_power_generation"] = device.get("totalPowerGeneration")
            data["daily_earnings"] = device.get("dailyEarnings")

        # Fetch detailed statistics for online inverters
        if device.get("status") == "Online":
            try:
                stats = await self.api_client.fetch_device_statistics(device_id)
                data["total_yield"] = stats.get("totalYield")
                if stats.get("currentPower") is not None:
                    data["current_power"] = stats["currentPower"]
            except Exception as err:
                _LOGGER.warning(
                    "Failed to fetch inverter statistics for %s: %s",
                    device_id,
                    err,
                )

    async def _process_battery_device(
        self, device: dict, device_id: str, data: dict
    ) -> None:
        """Process battery device data."""
        data["battery_level"] = device.get("batteryLevel")
        data["input_power_total"] = device.get("inputPowerTotal")
        data["output_power_total"] = device.get("outputPowerTotal")

        # Extract actual battery module count from device configuration
        # This represents the number of physical battery modules (1-3), not online status
        device_count = device.get("deviceCount")
        if device_count is not None and device_count > 0:
            # deviceCount represents the number of sub-devices (battery modules)
            data["module_count"] = device_count
        else:
            # Fallback: default to 1 for main battery
            data["module_count"] = 1

        _LOGGER.debug(
            "Battery device %s has %d modules (deviceCount: %s)",
            device_id,
            data["module_count"],
            device_count,
        )

        # Fetch detailed statistics for online batteries
        if device.get("status") == "Online":
            try:
                stats = await self.api_client.fetch_device_statistics(device_id)

                # System-wide battery data
                data["batterySoc"] = stats.get("batterySoc")
                data["chargeRemaining"] = stats.get("chargeRemaining")
                data["dischargeRemaining"] = stats.get("dischargeRemaining")

                # Individual battery module SOCs - only for existing modules
                module_count = data.get("module_count", 1)
                for i in range(1, module_count + 1):
                    soc_key = f"battery{i}Soc"
                    data[soc_key] = stats.get(soc_key)

                # MPPT data
                mppt_fields = [
                    "batteryMppt1InVol",
                    "batteryMppt1InCur",
                    "batteryMppt1InPower",
                    "batteryMppt2InVol",
                    "batteryMppt2InCur",
                    "batteryMppt2InPower",
                ]
                for field in mppt_fields:
                    data[field] = stats.get(field)

                # Battery module MPPT data - only for existing modules
                for module_num in range(1, module_count + 1):
                    for suffix in ["Mppt1InVol", "Mppt1InCur", "Mppt1InPower"]:
                        field = f"battery{module_num}{suffix}"
                        data[field] = stats.get(field)

                # Update power totals
                if stats.get("inputPowerTotal") is not None:
                    data["input_power_total"] = stats["inputPowerTotal"]
                if stats.get("outputPowerTotal") is not None:
                    data["output_power_total"] = stats["outputPowerTotal"]

                # Dispatch SOC events if event manager is available
                if self.event_manager:
                    self._dispatch_soc_events(device_id, data)

            except Exception as err:
                _LOGGER.debug(
                    "Could not fetch detailed statistics for device %s: %s",
                    device_id,
                    err,
                )

    def get_battery_module_count(self, device_id: str) -> int:
        """Get the number of battery modules for a specific battery device.

        Args:
            device_id: The battery device ID

        Returns:
            int: Number of modules for this battery (1 for main battery, up to 3 total)
        """
        if not self.data or "devices" not in self.data:
            return 1

        device_data = self.data["devices"].get(device_id)
        if not device_data:
            return 1

        return device_data.get("module_count", 1)

    def _dispatch_soc_events(self, device_id: str, data: dict) -> None:
        """Dispatch SOC events for battery devices."""
        if not self.event_manager:
            return

        # System-wide SOC event
        system_soc = data.get("batterySoc")
        if system_soc is not None:
            device_key = f"battery_{device_id}_system"
            # Get SOC limits from family coordinator if available
            limits = self._get_soc_limits()
            self.event_manager.update_soc_state(device_key, system_soc, limits)

        # Individual module SOC events
        module_count = data.get("module_count", 1)
        for module_num in range(1, module_count + 1):
            soc_key = f"battery{module_num}Soc"
            module_soc = data.get(soc_key)
            if module_soc is not None:
                device_key = f"battery_{device_id}_module{module_num}"
                self.event_manager.update_soc_state(device_key, module_soc)

    def _get_soc_limits(self) -> dict[str, float] | None:
        """Get SOC limits from hass.data where family coordinator stores them."""
        # Access family coordinator data through hass.data to get SOC limits
        try:
            domain_data = self.hass.data.get("sunlit", {})
            for entry_data in domain_data.values():
                if isinstance(entry_data, dict) and self.family_id in entry_data:
                    family_coordinator = entry_data[self.family_id].get("family")
                    if family_coordinator and family_coordinator.data:
                        family_data = family_coordinator.data.get("family", {})
                        return {
                            "strategy_min": family_data.get("strategy_soc_min"),
                            "strategy_max": family_data.get("strategy_soc_max"),
                            "bms_min": family_data.get("battery_soc_min"),
                            "bms_max": family_data.get("battery_soc_max"),
                            "hw_min": family_data.get("hw_soc_min"),
                            "hw_max": family_data.get("hw_soc_max"),
                        }
        except Exception:
            # Don't break if there are issues accessing family data
            pass
        return None
