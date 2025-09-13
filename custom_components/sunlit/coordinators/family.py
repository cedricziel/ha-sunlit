"""Family-level data coordinator for Sunlit integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..api_client import SunlitApiClient
from ..const import DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class SunlitFamilyCoordinator(DataUpdateCoordinator):
    """Coordinator for family-level data and aggregates."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: SunlitApiClient,
        family_id: str,
        family_name: str,
        is_global: bool = False,
    ) -> None:
        """Initialize the family coordinator."""
        self.api_client = api_client
        self.family_id = family_id
        self.family_name = family_name
        self.is_global = is_global
        self.devices = {}  # Empty for compatibility with legacy code

        super().__init__(
            hass,
            _LOGGER,
            name=f"Sunlit Family {family_name}",
            update_interval=DEFAULT_SCAN_INTERVAL,  # 30 seconds
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch family-level data from REST API."""
        try:
            family_data = {}

            if self.is_global:
                # For global/unassigned devices, minimal family data
                all_devices = await self.api_client.get_device_list()
                devices = [d for d in all_devices if d.get("spaceId") is None]

                family_data["device_count"] = len(devices)
                family_data["online_devices"] = sum(
                    1 for d in devices if d.get("status") == "Online"
                )
                family_data["offline_devices"] = sum(
                    1 for d in devices if d.get("status") == "Offline"
                )
                return {"family": family_data}

            # Fetch space index for comprehensive family data
            space_index = {}
            try:
                space_index = await self.api_client.fetch_space_index(self.family_id)
                _LOGGER.debug(
                    "Successfully fetched space index data for family %s",
                    self.family_id,
                )
            except Exception as err:
                _LOGGER.debug("Could not fetch space index data: %s", err)

            # Process space index data
            if space_index:
                await self._process_space_index(space_index, family_data)

            # Fetch SOC limits
            await self._fetch_soc_limits(family_data)

            # Fetch current strategy
            await self._fetch_current_strategy(family_data)

            # Fetch charging box strategy
            await self._fetch_charging_box_strategy(family_data)

            return {"family": family_data}

        except Exception as err:
            raise UpdateFailed(
                f"Error fetching family data for {self.family_name}: {err}"
            ) from err

    async def _process_space_index(self, space_index: dict, family_data: dict) -> None:
        """Process space index data."""
        # Today's metrics
        if "today" in space_index:
            today_data = space_index["today"]
            family_data["daily_yield"] = today_data.get("yield")
            family_data["daily_earnings"] = today_data.get("earning")
            family_data["home_power"] = today_data.get("homePower")
            family_data["currency"] = today_data.get("currency", "EUR")

        # Battery data
        if "battery" in space_index:
            battery_data = space_index["battery"]
            if battery_data.get("deviceStatus") != "NotExist":
                family_data["average_battery_level"] = battery_data.get("batteryLevel")
                family_data["battery_count"] = battery_data.get("batteryCount")
                family_data["battery_bypass"] = battery_data.get("bypass", False)
                family_data["battery_charging_remaining"] = battery_data.get(
                    "chargingRemaining"
                )
                family_data["battery_discharging_remaining"] = battery_data.get(
                    "dischargingRemaining"
                )
                family_data["total_input_power"] = battery_data.get("inputPower")
                family_data["total_output_power"] = battery_data.get("outputPower")

                # Heater status
                heater_status = battery_data.get("heaterStatusList", [])
                for idx, status in enumerate(heater_status, 1):
                    family_data[f"battery_heater_{idx}"] = status

        # Meter data
        if "eleMeter" in space_index:
            meter_data = space_index["eleMeter"]
            if meter_data.get("deviceStatus") != "NotExist":
                family_data["meter_device_status"] = meter_data.get("deviceStatus")
                family_data["total_ac_power"] = meter_data.get("totalAcPower")

        # Inverter data
        if "inverter" in space_index:
            inverter_data = space_index["inverter"]
            if inverter_data.get("deviceStatus") != "NotExist":
                family_data["inverter_device_status"] = inverter_data.get(
                    "deviceStatus"
                )
                family_data["inverter_current_power"] = inverter_data.get(
                    "currentPower"
                )

        # Boost settings
        if "boostSetting" in space_index:
            boost_data = space_index["boostSetting"]
            family_data["boost_mode_enabled"] = boost_data.get("isOn", False)
            family_data["boost_mode_switching"] = boost_data.get("switching", False)

    async def _fetch_soc_limits(self, family_data: dict) -> None:
        """Fetch SOC limits."""
        try:
            space_soc = await self.api_client.fetch_space_soc(self.family_id)
            if space_soc:
                family_data["hw_soc_min"] = space_soc.get("hwSbmsLimitedDiscSocMin")
                family_data["hw_soc_max"] = space_soc.get("hwSbmsLimitedChgSocMax")
                family_data["battery_soc_min"] = space_soc.get("batteryBmsDiscSocMin")
                family_data["battery_soc_max"] = space_soc.get("batteryBmsChgSocMax")
                family_data["strategy_soc_min"] = space_soc.get("strategySocMin")
                family_data["strategy_soc_max"] = space_soc.get("strategySocMax")
        except Exception as err:
            _LOGGER.debug("Could not fetch space SOC data: %s", err)

    async def _fetch_current_strategy(self, family_data: dict) -> None:
        """Fetch current strategy."""
        try:
            current_strategy = await self.api_client.fetch_space_current_strategy(
                self.family_id
            )
            if current_strategy:
                family_data["battery_strategy"] = current_strategy.get("strategy")
                family_data["battery_full"] = current_strategy.get("batteryFull")
                family_data["rated_power"] = current_strategy.get("ratedPower")
                family_data["max_output_power"] = current_strategy.get("maxOutPutPower")
                family_data["battery_status"] = current_strategy.get("batteryStatus")
                family_data["battery_device_status"] = current_strategy.get(
                    "batteryDeviceStatus"
                )
                family_data["current_soc_min"] = current_strategy.get("socMin")
                family_data["current_soc_max"] = current_strategy.get("socMax")
        except Exception as err:
            _LOGGER.debug("Could not fetch current strategy data: %s", err)

    async def _fetch_charging_box_strategy(self, family_data: dict) -> None:
        """Fetch charging box strategy."""
        try:
            charging_box_data = await self.api_client.get_charging_box_strategy(
                self.family_id
            )
            if charging_box_data:
                family_data["ev3600_auto_strategy_mode"] = charging_box_data.get(
                    "ev3600AutoStrategyMode"
                )
                family_data["storage_strategy"] = charging_box_data.get(
                    "storageStrategy"
                )
                family_data["normal_charge_box_mode"] = charging_box_data.get(
                    "normalChargeBoxMode"
                )

                # Inverter serial numbers
                inverter_sn_list = charging_box_data.get("inverterSn", [])
                if inverter_sn_list:
                    family_data["inverter_sn_list"] = ", ".join(inverter_sn_list)

                # Binary flags
                family_data["ev3600_auto_strategy_exist"] = charging_box_data.get(
                    "ev3600AutoStrategyExist", False
                )
                family_data["ev3600_auto_strategy_running"] = charging_box_data.get(
                    "ev3600AutoStrategyRunning", False
                )
                family_data["tariff_strategy_exist"] = charging_box_data.get(
                    "tariffStrategyExist", False
                )
                family_data["enable_local_smart_strategy"] = charging_box_data.get(
                    "enableLocalSmartStrategy", False
                )
                family_data["ac_couple_enabled"] = charging_box_data.get(
                    "acCoupleEnabled", False
                )
                family_data["charging_box_boost_on"] = charging_box_data.get(
                    "boostOn", False
                )
        except Exception as err:
            _LOGGER.debug("Could not fetch charging box strategy: %s", err)
