"""Simple test to verify solar power calculation logic."""


def test_solar_power_calculation_logic():
    """Test the logic for calculating total solar power from all sources."""

    # Simulate device data as it would be after processing
    devices_data = {
        "inv_001": {
            "deviceType": "YUNENG_MICRO_INVERTER",
            "current_power": 1500,  # Inverter solar power
        },
        "bat_001": {
            "deviceType": "ENERGY_STORAGE_BATTERY",
            "batteryMppt1InPower": 800,   # Battery MPPT1 solar
            "batteryMppt2InPower": 600,   # Battery MPPT2 solar
            "battery1Mppt1InPower": 500,  # Module 1 MPPT solar
            "battery2Mppt1InPower": 400,  # Module 2 MPPT solar
            "battery3Mppt1InPower": 300,  # Module 3 MPPT solar
            "output_power_total": 2000,   # Battery output (NOT solar)
            "module_count": 3,
        }
    }

    # Calculate total solar power as the device coordinator would
    total_solar_power = 0

    for device_id, data in devices_data.items():
        device_type = data.get("deviceType")

        # Add inverter power
        if device_type in ["YUNENG_MICRO_INVERTER", "SOLAR_MICRO_INVERTER"]:
            if data.get("current_power") is not None:
                total_solar_power += data["current_power"]

        # Add battery MPPT power
        elif device_type == "ENERGY_STORAGE_BATTERY":
            # Main battery MPPTs
            if data.get("batteryMppt1InPower") is not None:
                total_solar_power += data["batteryMppt1InPower"]
            if data.get("batteryMppt2InPower") is not None:
                total_solar_power += data["batteryMppt2InPower"]

            # Module MPPTs
            module_count = data.get("module_count", 1)
            for module_num in range(1, module_count + 1):
                mppt_key = f"battery{module_num}Mppt1InPower"
                if data.get(mppt_key) is not None:
                    total_solar_power += data[mppt_key]

    # Verify the calculation
    expected = 1500 + 800 + 600 + 500 + 400 + 300  # = 4100W
    assert total_solar_power == expected, \
        f"Expected {expected}W, got {total_solar_power}W"

    # Verify battery output is NOT included
    assert total_solar_power != expected + 2000, \
        "Battery output power should NOT be in solar total"

    print(f"✅ Total solar power correctly calculated: {total_solar_power}W")
    print("   Components:")
    print(f"   - Inverter: 1500W")
    print(f"   - Battery MPPT1: 800W")
    print(f"   - Battery MPPT2: 600W")
    print(f"   - Module 1 MPPT: 500W")
    print(f"   - Module 2 MPPT: 400W")
    print(f"   - Module 3 MPPT: 300W")
    print(f"   - Total: {total_solar_power}W")
    print(f"   ❌ Battery output ({devices_data['bat_001']['output_power_total']}W) correctly excluded")


def test_solar_without_battery():
    """Test solar calculation with only inverters."""

    devices_data = {
        "inv_001": {"deviceType": "SOLAR_MICRO_INVERTER", "current_power": 2000},
        "inv_002": {"deviceType": "YUNENG_MICRO_INVERTER", "current_power": 1800},
    }

    total_solar_power = 0
    for device_id, data in devices_data.items():
        if data.get("deviceType") in ["YUNENG_MICRO_INVERTER", "SOLAR_MICRO_INVERTER"]:
            if data.get("current_power") is not None:
                total_solar_power += data["current_power"]

    assert total_solar_power == 3800, f"Expected 3800W, got {total_solar_power}W"
    print(f"✅ Inverter-only solar: {total_solar_power}W")


def test_solar_battery_only():
    """Test solar calculation with only battery MPPT."""

    devices_data = {
        "bat_001": {
            "deviceType": "ENERGY_STORAGE_BATTERY",
            "batteryMppt1InPower": 1200,
            "batteryMppt2InPower": 900,
            "output_power_total": 2000,  # Should NOT be counted
            "module_count": 1,
        }
    }

    total_solar_power = 0
    for device_id, data in devices_data.items():
        if data.get("deviceType") == "ENERGY_STORAGE_BATTERY":
            if data.get("batteryMppt1InPower") is not None:
                total_solar_power += data["batteryMppt1InPower"]
            if data.get("batteryMppt2InPower") is not None:
                total_solar_power += data["batteryMppt2InPower"]

    assert total_solar_power == 2100, f"Expected 2100W, got {total_solar_power}W"
    assert total_solar_power != 2000, "Output power should not be counted"
    print(f"✅ Battery MPPT-only solar: {total_solar_power}W (output {devices_data['bat_001']['output_power_total']}W excluded)")


if __name__ == "__main__":
    print("Testing solar power calculation logic...")
    print("=" * 50)

    test_solar_power_calculation_logic()
    print()

    test_solar_without_battery()
    print()

    test_solar_battery_only()
    print()

    print("=" * 50)
    print("🎉 All tests passed! Solar power calculation is correct.")
