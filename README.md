# Sunlit Solar - HomeAssistant Integration

> ⚠️ **EXPERIMENTAL INTEGRATION - USE AT YOUR OWN RISK**
>
> This is an **unofficial** custom integration for HomeAssistant to monitor Sunlit Solar systems.
> This integration is not affiliated with, endorsed by, or supported by Sunlit Solar GmbH.
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

| Sensor                   | Description                       | Unit     | Update |
| ------------------------ | --------------------------------- | -------- | ------ |
| `device_count`           | Total number of devices           | count    | 30s    |
| `online_devices`         | Number of online devices          | count    | 30s    |
| `offline_devices`        | Number of offline devices         | count    | 30s    |
| `total_ac_power`         | Combined AC power from all meters | W        | 30s    |
| `average_battery_level`  | Average SOC across all batteries  | %        | 30s    |
| `total_input_power`      | Total battery charging power      | W        | 30s    |
| `total_output_power`     | Total battery discharging power   | W        | 30s    |
| `battery_strategy`       | Current battery charging strategy | text     | 30s    |
| `battery_status`         | Overall battery system status     | text     | 30s    |
| `rated_power`            | System rated power capacity       | W        | 30s    |
| `max_output_power`       | Maximum output power limit        | W        | 30s    |
| `hw_soc_min`             | Hardware minimum SOC limit        | %        | 30s    |
| `hw_soc_max`             | Hardware maximum SOC limit        | %        | 30s    |
| `strategy_soc_min`       | Strategy minimum SOC              | %        | 30s    |
| `strategy_soc_max`       | Strategy maximum SOC              | %        | 30s    |
| `last_strategy_change`   | Timestamp of last strategy change | datetime | 30s    |
| `strategy_changes_today` | Number of strategy changes in 24h | count    | 30s    |

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

| Sensor               | Description               | Unit |
| -------------------- | ------------------------- | ---- |
| `battery_level`      | Current state of charge   | %    |
| `input_power_total`  | Current charging power    | W    |
| `output_power_total` | Current discharging power | W    |

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
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
pytest tests/

# Run linters
ruff check custom_components/sunlit/
black custom_components/sunlit/
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
