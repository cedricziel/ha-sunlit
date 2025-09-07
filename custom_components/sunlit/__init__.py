"""The Sunlit REST integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api_client import SunlitApiClient
from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    CONF_ACCESS_TOKEN,
    CONF_FAMILIES,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sunlit REST from a config entry."""

    access_token = entry.data[CONF_ACCESS_TOKEN]
    families = entry.data[CONF_FAMILIES]

    # Get HomeAssistant version for User-Agent
    try:
        from homeassistant.const import __version__ as ha_version
    except ImportError:
        # Fallback if __version__ is not available
        ha_version = getattr(hass, "version", "unknown")

    session = async_get_clientsession(hass)
    api_client = SunlitApiClient(session, access_token, ha_version=str(ha_version))

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
            # Try to fetch comprehensive space data first (more efficient)
            space_index = {}
            try:
                space_index = await self.api_client.fetch_space_index(self.family_id)
                _LOGGER.debug(
                    "Successfully fetched space index data for family %s",
                    self.family_id
                )
            except Exception as err:
                _LOGGER.debug(
                    "Could not fetch space index data (will use fallback): %s", err
                )
            
            # Fetch device list for the family (still needed for device discovery)
            devices = await self.api_client.fetch_device_list(self.family_id)
            
            # Only fetch individual endpoints if space_index is not available
            space_soc = {}
            current_strategy = {}
            strategy_history = {}
            
            if not space_index:
                # Fallback to individual endpoints
                try:
                    space_soc = await self.api_client.fetch_space_soc(self.family_id)
                except Exception as err:
                    _LOGGER.debug("Could not fetch space SOC data: %s", err)
                
                try:
                    current_strategy = (
                        await self.api_client.fetch_space_current_strategy(
                            self.family_id
                        )
                    )
                except Exception as err:
                    _LOGGER.debug("Could not fetch current strategy data: %s", err)
                
                try:
                    strategy_history = (
                        await self.api_client.fetch_space_strategy_history(
                            self.family_id
                        )
                    )
                except Exception as err:
                    _LOGGER.debug("Could not fetch strategy history data: %s", err)

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
                    # Basic battery data (always available)
                    device_data["battery_level"] = device.get("batteryLevel")
                    device_data["input_power_total"] = device.get("inputPowerTotal")
                    device_data["output_power_total"] = device.get("outputPowerTotal")
                    
                    # Try to fetch detailed statistics for online devices
                    if device.get("status") == "Online":
                        try:
                            detailed_stats = (
                                await self.api_client.fetch_device_statistics(
                                    device_id
                                )
                            )
                            
                            # System-wide battery data
                            device_data["batterySoc"] = detailed_stats.get(
                                "batterySoc"
                            )
                            device_data["chargeRemaining"] = detailed_stats.get(
                                "chargeRemaining"
                            )
                            device_data["dischargeRemaining"] = detailed_stats.get(
                                "dischargeRemaining"
                            )
                            
                            # Individual battery module SOCs
                            device_data["battery1Soc"] = detailed_stats.get(
                                "battery1Soc"
                            )
                            device_data["battery2Soc"] = detailed_stats.get(
                                "battery2Soc"
                            )
                            device_data["battery3Soc"] = detailed_stats.get(
                                "battery3Soc"
                            )
                            
                            # Main unit MPPT data (simplified fields)
                            mppt_fields = [
                                "batteryMppt1InVol", "batteryMppt1InCur",
                                "batteryMppt1InPower", "batteryMppt2InVol",
                                "batteryMppt2InCur", "batteryMppt2InPower"
                            ]
                            for field in mppt_fields:
                                device_data[field] = detailed_stats.get(field)
                            
                            # Battery module MPPT data
                            for module_num in [1, 2, 3]:
                                mppt_suffixes = ["Mppt1InVol", "Mppt1InCur", "Mppt1InPower"]
                                for suffix in mppt_suffixes:
                                    field = f"battery{module_num}{suffix}"
                                    device_data[field] = detailed_stats.get(field)
                            
                            # Update power totals if available from detailed stats
                            if detailed_stats.get("inputPowerTotal") is not None:
                                device_data["input_power_total"] = detailed_stats[
                                    "inputPowerTotal"
                                ]
                            if detailed_stats.get("outputPowerTotal") is not None:
                                device_data["output_power_total"] = detailed_stats[
                                    "outputPowerTotal"
                                ]
                                
                        except Exception as err:
                            _LOGGER.debug(
                                "Could not fetch detailed statistics for device %s: %s",
                                device_id, err
                            )
                            # Continue with basic data only

                    if device.get("batteryLevel") is not None:
                        total_battery_level += device["batteryLevel"]
                        battery_count += 1
                    if device_data.get("input_power_total"):
                        total_input_power += device_data["input_power_total"]
                    if device_data.get("output_power_total"):
                        total_output_power += device_data["output_power_total"]

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
            
            # Add space_index data if available (override aggregates with more accurate data)
            if space_index:
                # Today's metrics
                if "today" in space_index:
                    today_data = space_index["today"]
                    sensor_data["family"]["daily_yield"] = today_data.get("yield")
                    sensor_data["family"]["daily_earnings"] = today_data.get("earning")
                    sensor_data["family"]["home_power"] = today_data.get(
                        "homePower"
                    )
                    sensor_data["family"]["currency"] = today_data.get(
                        "currency", "EUR"
                    )
                
                # Battery data from space_index (more accurate than aggregates)
                if "battery" in space_index:
                    battery_data = space_index["battery"]
                    if battery_data.get("deviceStatus") != "NotExist":
                        sensor_data["family"]["average_battery_level"] = (
                            battery_data.get("batteryLevel")
                        )
                        sensor_data["family"]["battery_count"] = battery_data.get(
                            "batteryCount"
                        )
                        sensor_data["family"]["battery_bypass"] = battery_data.get(
                            "bypass", False
                        )
                        sensor_data["family"]["battery_charging_remaining"] = (
                            battery_data.get("chargingRemaining")
                        )
                        sensor_data["family"]["battery_discharging_remaining"] = (
                            battery_data.get("dischargingRemaining")
                        )
                        
                        # Update power data with more accurate values
                        if battery_data.get("inputPower") is not None:
                            sensor_data["family"]["total_input_power"] = (
                                battery_data["inputPower"]
                            )
                        if battery_data.get("outputPower") is not None:
                            sensor_data["family"]["total_output_power"] = (
                                battery_data["outputPower"]
                            )
                        
                        # Heater status (list of booleans for each battery module)
                        heater_status = battery_data.get(
                            "heaterStatusList", []
                        )
                        for idx, status in enumerate(heater_status, 1):
                            sensor_data["family"][f"battery_heater_{idx}"] = status
                
                # Meter data from space_index
                if "eleMeter" in space_index:
                    meter_data = space_index["eleMeter"]
                    if meter_data.get("deviceStatus") != "NotExist":
                        sensor_data["family"]["meter_device_status"] = meter_data.get(
                            "deviceStatus"
                        )
                        if meter_data.get("totalAcPower") is not None:
                            sensor_data["family"]["total_ac_power"] = meter_data[
                                "totalAcPower"
                            ]
                
                # Inverter data from space_index
                if "inverter" in space_index:
                    inverter_data = space_index["inverter"]
                    if inverter_data.get("deviceStatus") != "NotExist":
                        sensor_data["family"]["inverter_device_status"] = (
                            inverter_data.get("deviceStatus")
                        )
                        sensor_data["family"]["inverter_current_power"] = (
                            inverter_data.get("currentPower")
                        )
                
                # Boost settings
                if "boostSetting" in space_index:
                    boost_data = space_index["boostSetting"]
                    sensor_data["family"]["boost_mode_enabled"] = boost_data.get(
                        "isOn", False
                    )
                    sensor_data["family"]["boost_mode_switching"] = boost_data.get(
                        "switching", False
                    )
            
            # Add space SOC data to family sensors
            if space_soc:
                sensor_data["family"]["hw_soc_min"] = space_soc.get(
                    "hwSbmsLimitedDiscSocMin"
                )
                sensor_data["family"]["hw_soc_max"] = space_soc.get(
                    "hwSbmsLimitedChgSocMax"
                )
                sensor_data["family"]["battery_soc_min"] = space_soc.get(
                    "batteryBmsDiscSocMin"
                )
                sensor_data["family"]["battery_soc_max"] = space_soc.get(
                    "batteryBmsChgSocMax"
                )
                sensor_data["family"]["strategy_soc_min"] = space_soc.get(
                    "strategySocMin"
                )
                sensor_data["family"]["strategy_soc_max"] = space_soc.get(
                    "strategySocMax"
                )
            
            # Add current strategy data to family sensors
            if current_strategy:
                sensor_data["family"]["battery_strategy"] = current_strategy.get(
                    "strategy"
                )
                sensor_data["family"]["battery_full"] = current_strategy.get(
                    "batteryFull"
                )
                sensor_data["family"]["rated_power"] = current_strategy.get(
                    "ratedPower"
                )
                sensor_data["family"]["max_output_power"] = current_strategy.get(
                    "maxOutPutPower"
                )
                sensor_data["family"]["battery_status"] = current_strategy.get(
                    "batteryStatus"
                )
                sensor_data["family"]["battery_device_status"] = current_strategy.get(
                    "batteryDeviceStatus"
                )
                sensor_data["family"]["inverter_device_status"] = current_strategy.get(
                    "inverterDeviceStatus"
                )
                sensor_data["family"]["meter_device_status"] = current_strategy.get(
                    "meterDeviceStatus"
                )
                sensor_data["family"]["current_soc_min"] = current_strategy.get(
                    "socMin"
                )
                sensor_data["family"]["current_soc_max"] = current_strategy.get(
                    "socMax"
                )
            
            # Process strategy history data
            if strategy_history and "content" in strategy_history:
                history_entries = strategy_history["content"]
                if history_entries:
                    # Get most recent entry
                    latest_entry = history_entries[0]  # Already sorted by date desc
                    
                    # Add sensors for latest strategy change
                    sensor_data["family"]["last_strategy_change"] = latest_entry.get(
                        "modifyDate"
                    )
                    sensor_data["family"]["last_strategy_type"] = latest_entry.get(
                        "strategy"
                    )
                    sensor_data["family"]["last_strategy_status"] = latest_entry.get(
                        "status"
                    )
                    
                    # Count changes in last 24 hours
                    from datetime import datetime, timedelta
                    now = datetime.now()
                    day_ago = now - timedelta(days=1)
                    day_ago_ms = int(day_ago.timestamp() * 1000)
                    
                    changes_today = sum(
                        1 for entry in history_entries
                        if entry.get("modifyDate", 0) >= day_ago_ms
                    )
                    sensor_data["family"]["strategy_changes_today"] = changes_today
                    
                    # Store last 10 entries in extra attributes
                    sensor_data["family"]["strategy_history"] = history_entries[:10]

            _LOGGER.debug(
                "Processed sensor data for family %s: %s", self.family_name, sensor_data
            )

            return sensor_data

        except Exception as err:
            raise UpdateFailed(
                f"Error fetching data for family {self.family_name}: {err}"
            ) from err
