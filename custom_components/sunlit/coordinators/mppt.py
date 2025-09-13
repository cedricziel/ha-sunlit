"""MPPT energy accumulation coordinator for Sunlit integration."""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .device import SunlitDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


class SunlitMpptEnergyCoordinator(DataUpdateCoordinator):
    """Coordinator for MPPT energy accumulation."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_coordinator: SunlitDeviceCoordinator,
        family_id: str,
        family_name: str,
    ) -> None:
        """Initialize the MPPT energy coordinator."""
        self.device_coordinator = device_coordinator
        self.family_id = family_id
        self.family_name = family_name

        # Energy accumulators
        self.mppt_energy = {}
        self.last_mppt_update = {}
        self.last_mppt_power = {}

        super().__init__(
            hass,
            _LOGGER,
            name=f"Sunlit MPPT Energy {family_name}",
            update_interval=timedelta(minutes=1),  # 1 minute updates
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Calculate MPPT energy accumulation."""
        try:
            current_time = time.time()

            mppt_data = {}

            # Get device data from device coordinator
            if not self.device_coordinator.data:
                return {"mppt_energy": {}}

            devices = self.device_coordinator.data.get("devices", {})

            for device_id, device_data in devices.items():
                if device_data.get("deviceType") != "ENERGY_STORAGE_BATTERY":
                    continue

                device_mppt = {}

                # Main unit MPPT energy calculation
                self._calculate_main_mppt_energy(
                    device_id, device_data, device_mppt, current_time
                )

                # Battery module MPPT energy calculation
                self._calculate_module_mppt_energy(
                    device_id, device_data, device_mppt, current_time
                )

                if device_mppt:
                    mppt_data[device_id] = device_mppt

            # Calculate total MPPT energy
            total_mppt_energy = sum(
                self.mppt_energy.get(key, 0) for key in self.mppt_energy
            )

            return {
                "mppt_energy": mppt_data,
                "total_mppt_energy": round(total_mppt_energy, 3),
            }

        except Exception as err:
            _LOGGER.warning(
                "Error calculating MPPT energy for %s: %s", self.family_name, err
            )
            return {"mppt_energy": {}}

    def _calculate_main_mppt_energy(
        self,
        device_id: str,
        device_data: dict,
        device_mppt: dict,
        current_time: float,
    ) -> None:
        """Calculate energy for main unit MPPT inputs."""
        for mppt_num in [1, 2]:
            power_key = f"batteryMppt{mppt_num}InPower"
            energy_key = f"batteryMppt{mppt_num}Energy"

            if device_data.get(power_key) is not None:
                power = device_data[power_key]
                full_key = f"{device_id}_{energy_key}"

                if full_key in self.mppt_energy:
                    if full_key in self.last_mppt_update:
                        time_delta_hours = (
                            current_time - self.last_mppt_update[full_key]
                        ) / 3600

                        # Trapezoidal integration
                        avg_power = (
                            power + self.last_mppt_power.get(full_key, power)
                        ) / 2

                        energy_increment = (avg_power * time_delta_hours) / 1000
                        self.mppt_energy[full_key] += energy_increment
                else:
                    self.mppt_energy[full_key] = 0

                self.last_mppt_update[full_key] = current_time
                self.last_mppt_power[full_key] = power
                device_mppt[energy_key] = round(self.mppt_energy[full_key], 3)

    def _calculate_module_mppt_energy(
        self,
        device_id: str,
        device_data: dict,
        device_mppt: dict,
        current_time: float,
    ) -> None:
        """Calculate energy for battery module MPPT inputs."""
        # Get actual number of battery modules for this device
        module_count = self.device_coordinator.get_battery_module_count(device_id)

        for module_num in range(1, module_count + 1):
            power_key = f"battery{module_num}Mppt1InPower"
            energy_key = f"battery{module_num}Mppt1Energy"

            if device_data.get(power_key) is not None:
                power = device_data[power_key]
                full_key = f"{device_id}_{energy_key}"

                if full_key in self.mppt_energy:
                    if full_key in self.last_mppt_update:
                        time_delta_hours = (
                            current_time - self.last_mppt_update[full_key]
                        ) / 3600

                        avg_power = (
                            power + self.last_mppt_power.get(full_key, power)
                        ) / 2

                        energy_increment = (avg_power * time_delta_hours) / 1000
                        self.mppt_energy[full_key] += energy_increment
                else:
                    self.mppt_energy[full_key] = 0

                self.last_mppt_update[full_key] = current_time
                self.last_mppt_power[full_key] = power
                device_mppt[energy_key] = round(self.mppt_energy[full_key], 3)
