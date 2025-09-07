# Sunlit Solar - HomeAssistant Integration

> ⚠️ **EXPERIMENTAL INTEGRATION - USE AT YOUR OWN RISK**
>
> This is an **unofficial** custom integration for HomeAssistant to monitor Sunlit Solar systems.
> This integration is not affiliated with, endorsed by, or supported by Sunlit.
>
> **No warranty or support is provided. Use of this integration is entirely at your own risk.**

## Overview

This custom integration connects HomeAssistant to the Sunlit Solar API, enabling real-time monitoring of your solar installation including solar panels, inverters, batteries, and energy meters. It provides comprehensive sensor data for monitoring energy production, consumption, and battery status.

### Key Features

- 📊 **Monitoring** - Updates every 30 seconds
- 🏠 **Family/Space Aggregation** - Combined metrics across all devices
- 🔌 **Device-Specific Sensors** - Individual monitoring for each component
- 🔋 **Battery Management** - SOC limits, strategies, and status tracking
- ⚡ **Energy Dashboard Ready** - Compatible with HA Energy Dashboard
- 🚨 **Fault Detection** - Binary sensors for system health monitoring
- 📈 **Strategy History** - Track battery charging strategy changes

## Requirements

- HomeAssistant 2025.1.0 or newer
- Sunlit Solar Bearer API key (obtain from your Sunlit Solar account)
- Active internet connection for API access

## Installation

### HACS Installation (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on **Integrations**
3. Click the three dots menu in the top right corner and select **Custom repositories**
4. Add this repository URL: `https://github.com/cedricziel/ha-sunlit`
5. Select **Integration** as the category
6. Click **Add**
7. Search for "Sunlit Solar" in HACS
8. Click **Download** and select the latest version
9. Restart Home Assistant
10. Add the integration through the UI: **Settings** → **Devices & Services** → **Add Integration** → Search for "Sunlit"

### Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/sunlit` folder to your HomeAssistant configuration directory:
   ```
   <config_dir>/custom_components/sunlit/
   ```
3. Restart HomeAssistant
4. Add the integration through the UI: **Settings** → **Devices & Services** → **Add Integration** → Search for "Sunlit"

### Directory Structure

```
custom_components/
└── sunlit/
    ├── __init__.py
    ├── api_client.py
    ├── binary_sensor.py
    ├── config_flow.py
    ├── const.py
    ├── manifest.json
    ├── sensor.py
    └── strings.json
```

## Configuration

1. Navigate to **Settings** → **Devices & Services**
2. Click **Add Integration** and search for "Sunlit"
3. Enter your API key when prompted
4. Select the families/spaces you want to monitor
5. Click **Submit**

The integration will create devices and sensors automatically based on your Sunlit Solar system configuration.

## Available Sensors

### Family/Space Level Sensors

| Sensor                     | Description                       | Unit     | Update |
| -------------------------- | --------------------------------- | -------- | ------ |
| `device_count`             | Total number of devices           | count    | 30s    |
| `online_devices`           | Number of online devices          | count    | 30s    |
| `offline_devices`          | Number of offline devices         | count    | 30s    |
| `total_ac_power`           | Combined AC power from all meters | W        | 30s    |
| `average_battery_level`    | Average SOC across all batteries  | %        | 30s    |
| `total_input_power`        | Total battery charging power      | W        | 30s    |
| `total_output_power`       | Total battery discharging power   | W        | 30s    |
| `battery_strategy`         | Current battery charging strategy | text     | 30s    |
| `battery_status`           | Overall battery system status     | text     | 30s    |
| `rated_power`              | System rated power capacity       | W        | 30s    |
| `max_output_power`         | Maximum output power limit        | W        | 30s    |
| `hw_soc_min`               | Hardware minimum SOC limit        | %        | 30s    |
| `hw_soc_max`               | Hardware maximum SOC limit        | %        | 30s    |
| `strategy_soc_min`         | Strategy minimum SOC              | %        | 30s    |
| `strategy_soc_max`         | Strategy maximum SOC              | %        | 30s    |
| `last_strategy_change`     | Timestamp of last strategy change | datetime | 30s    |
| `strategy_changes_today`   | Number of strategy changes in 24h | count    | 30s    |
| `total_solar_energy`       | Total solar energy production     | kWh      | 30s    |
| `total_solar_power`        | Total solar power production      | W        | 30s    |
| `daily_grid_export_energy` | Daily energy exported to grid     | kWh      | 30s    |
| `total_grid_export_energy` | Total energy exported to grid     | kWh      | 30s    |

### Device-Specific Sensors

#### Smart Meter (SHELLY_3EM_METER)

| Sensor             | Description           | Unit |
| ------------------ | --------------------- | ---- |
| `total_ac_power`   | Current power flow    | W    |
| `daily_buy_energy` | Energy imported today | kWh  |
| `daily_ret_energy` | Energy exported today | kWh  |
| `total_buy_energy` | Total energy imported | kWh  |
| `total_ret_energy` | Total energy exported | kWh  |

#### Inverter (YUNENG_MICRO_INVERTER)

| Sensor                   | Description              | Unit |
| ------------------------ | ------------------------ | ---- |
| `current_power`          | Current power production | W    |
| `total_power_generation` | Total energy produced    | kWh  |
| `daily_earnings`         | Earnings today           | €    |

#### Battery (ENERGY_STORAGE_BATTERY)

##### Main Unit Sensors

| Sensor                | Description                 | Unit    |
| --------------------- | --------------------------- | ------- |
| `battery_level`       | Current state of charge     | %       |
| `batterySoc`          | System battery SOC          | %       |
| `input_power_total`   | Current charging power      | W       |
| `output_power_total`  | Current discharging power   | W       |
| `chargeRemaining`     | Time until fully charged    | minutes |
| `dischargeRemaining`  | Time until fully discharged | minutes |
| `batteryMppt1InVol`   | Main unit MPPT1 voltage     | V       |
| `batteryMppt1InCur`   | Main unit MPPT1 current     | A       |
| `batteryMppt1InPower` | Main unit MPPT1 power       | W       |
| `batteryMppt2InVol`   | Main unit MPPT2 voltage     | V       |
| `batteryMppt2InCur`   | Main unit MPPT2 current     | A       |
| `batteryMppt2InPower` | Main unit MPPT2 power       | W       |

##### Battery Module Sensors (Virtual Devices)

For modular battery systems with B215 extension modules, each additional battery module (1-3) appears as a separate virtual device with:

| Sensor         | Description            | Unit |
| -------------- | ---------------------- | ---- |
| `Soc`          | Module state of charge | %    |
| `Mppt1InVol`   | Module MPPT voltage    | V    |
| `Mppt1InCur`   | Module MPPT current    | A    |
| `Mppt1InPower` | Module MPPT power      | W    |

### Binary Sensors

| Sensor         | Description            | Device Class |
| -------------- | ---------------------- | ------------ |
| `has_fault`    | Any device has a fault | problem      |
| `battery_full` | Battery fully charged  | battery      |
| `fault`        | Device has fault       | problem      |
| `power`        | Device is powered on   | power        |

## Energy Dashboard Integration

To integrate with HomeAssistant's Energy Dashboard:

### Solar Production

1. Go to **Settings** → **Dashboards** → **Energy**
2. Under **Solar Panels**, click **Add Solar Production**
3. Select sensor: `sensor.inverter_[ID]_total_power_generation`

### Grid Consumption

1. Under **Grid**, click **Add Consumption**
2. Select sensor: `sensor.meter_[ID]_total_buy_energy`

### Grid Return

1. Under **Grid**, click **Add Return**
2. Select sensor: `sensor.meter_[ID]_total_ret_energy`

### Battery Energy (using Riemann sum helper)

Since the integration provides power sensors but not energy sensors for batteries:

1. Create a helper: **Settings** → **Devices & Services** → **Helpers** → **Create Helper** → **Integration - Riemann sum**
2. Configure:
   - Name: "Battery Energy Input"
   - Input sensor: `sensor.battery_[ID]_input_power_total`
   - Integration method: Trapezoidal
   - Metric prefix: k (kilo)
   - Time unit: Hours
3. Repeat for output power
4. Add these helpers to Energy Dashboard under **Battery Storage**

## Entity Design

### Entity ID Naming Convention

All entities follow a consistent naming pattern to ensure uniqueness across multiple families and devices:

#### Family/Space Level Entities

Pattern: `sensor.sunlit_{family_id}_{sensor_key}`
Example: `sensor.sunlit_12345_battery_level`

#### Device Level Entities

Pattern: `sensor.sunlit_{family_id}_{device_type}_{device_id}_{sensor_key}`
Example: `sensor.sunlit_12345_battery_456_input_power_total`

#### Virtual Device Entities (Battery Modules)

Pattern: `sensor.sunlit_{family_id}_battery_{device_id}_module{N}_{sensor_key}`
Example: `sensor.sunlit_12345_battery_456_module1_soc`

### Device Hierarchy

The integration creates a hierarchical device structure:

1. **Family Hub** - Virtual device representing the entire solar system

   - Contains aggregate sensors and system-wide metrics
   - All physical devices are linked to this hub

2. **Physical Devices** - Actual hardware components

   - Smart meters (SHELLY_3EM_METER)
   - Inverters (YUNENG_MICRO_INVERTER)
   - Battery units (ENERGY_STORAGE_BATTERY)

3. **Virtual Devices** - Logical representations for better organization
   - Battery modules (1-3) for modular battery systems
   - Each module appears as a separate device linked to the main battery unit
   - Prevents sensor overload on single devices (30+ sensors)

### Modular Battery Architecture

For battery systems with expansion modules:

- **Main Unit (BK215)**: Contains system-wide sensors and dual MPPT inputs
- **B215 Module 1-3**: Additional battery packs (2.15 kWh each) with individual MPPT solar inputs
- Each module tracks its own SOC and solar production independently
- Virtual devices ensure clean organization in HomeAssistant UI

## Known Limitations

- **No Dynamic Device Discovery**: New devices added to your Sunlit system require a HomeAssistant restart to appear
- **No Historical Data**: The integration cannot backfill historical data from before it was installed
- **API Rate Limits**: The 30-second update interval is fixed to avoid API rate limiting
- **Read-Only**: All sensors are read-only; device control is not supported

## Troubleshooting

### Enable Debug Logging

Add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.sunlit: debug
```

### Common Issues

**Sensors showing "unavailable"**

- Check your internet connection
- Verify API key is correct
- Ensure devices are online in Sunlit Solar app

**Missing devices after adding new hardware**

- Restart HomeAssistant to discover new devices
- Check if devices appear in Sunlit Solar app first

**Energy Dashboard not showing data**

- Ensure sensors have `state_class: total_increasing` (check Developer Tools)
- Wait for at least one update cycle (30 seconds)
- Verify units are in kWh for energy sensors

## Development

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/cedricziel/ha-sunlit.git
cd ha-sunlit

# Install dependencies
make setup

# Format code
make format

# Run linters (without making changes)
make lint

# Clean up cache files
make clean

# Show all available commands
make help
```

### Running HomeAssistant locally

```bash
# Start HomeAssistant in development mode
hass -c config
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## Disclaimer

**This integration is provided "as is" without warranty of any kind.** The authors and contributors are not responsible for any damages or losses that may result from using this integration.

This is an experimental, unofficial integration that:

- May stop working if Sunlit Solar changes their API
- Could potentially impact your Sunlit Solar warranty (check your terms)
- Is not endorsed or supported by Sunlit Solar GmbH
- May contain bugs that could affect your HomeAssistant installation

**Use at your own risk and always maintain backups of your HomeAssistant configuration.**

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

This is a community project with no official support. For issues and questions:

- Check existing [GitHub Issues](https://github.com/cedricziel/ha-sunlit/issues)
- Open a new issue with detailed information about your problem
- Join HomeAssistant community forums for general help

Remember: This is an experimental integration maintained by volunteers in their spare time.
