# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a HomeAssistant custom integration called "Sunlit" that fetches data from the Sunlit Solar REST API and exposes them as sensors and binary sensors. It's built as a cloud polling integration with UI-based configuration flow, supporting multiple device types in solar installations.

## Development Commands

### Using Makefile

```bash
# Install dependencies
make setup

# Auto-format code (black, isort, ruff --fix)
make format

# Run linters without changes
make lint

# Clean cache files
make clean

# Show help
make help
```

### Testing HomeAssistant

```bash
# Run HomeAssistant in development mode (port 8123)
hass -c config
```

## Architecture

### System Architecture

**IMPORTANT: Understanding the Sunlit Solar System Components**

- **Solar Panels**: Generate DC power from sunlight, connected ONLY to battery MPPT controllers
- **Battery MPPT Controllers**: Convert solar DC to optimal voltage for battery charging (INPUT)
- **Battery System**: Stores energy, has multiple MPPT inputs for solar panels
- **Inverters (YUNENG/SOLAR_MICRO_INVERTER)**: Convert battery DC to home AC (OUTPUT)
  - **NOT solar generators** - they are DC→AC converters
  - Their "current_power" is battery OUTPUT to home, not solar generation
  - At night, inverter power = battery supplying the home
- **Smart Meters**: Measure grid import/export

**Solar Power Calculation**:
- `total_solar_power` = Sum of MPPT inputs ONLY
- Does NOT include inverter power (that's OUTPUT, not INPUT)
- Solar sources: batteryMppt1InPower, batteryMppt2InPower, battery module MPPT powers

### Integration Structure

The integration follows HomeAssistant's standard custom component pattern:

- **Multiple DataUpdateCoordinators**: Uses specialized coordinators with different update intervals for optimal performance
- **Config Flow**: UI-based configuration through `config_flow.py` with API key authentication
- **Entity Platforms**: Multiple platforms for different entity types:
  - `sensor.py`: Numeric and text sensors
  - `binary_sensor.py`: Boolean state sensors

### Key Components

1. **Coordinators** (in `coordinators/` directory):

   The integration uses multiple specialized DataUpdateCoordinators with different update intervals:

   - **SunlitFamilyCoordinator** (`family.py`):
     - Handles family-level aggregated data
     - Update interval: 30 seconds
     - Fetches: space index, SOC limits, current strategy, charging box strategy
     - Provides: device counts, power totals, battery levels, strategy info

   - **SunlitDeviceCoordinator** (`device.py`):
     - Manages individual device states and readings
     - Update interval: 30 seconds
     - Fetches: device list, device statistics for online devices
     - Provides: device status, meter readings, inverter power, battery SOC
     - Creates virtual battery module devices

   - **SunlitStrategyHistoryCoordinator** (`strategy.py`):
     - Tracks battery strategy changes over time
     - Update interval: 5 minutes (less volatile data)
     - Fetches: strategy history from API
     - Provides: last strategy change, changes today, strategy history

   - **SunlitMpptEnergyCoordinator** (`mppt.py`):
     - Accumulates MPPT energy using trapezoidal integration
     - Update interval: 1 minute (for accurate energy calculation)
     - Depends on: device coordinator for power readings
     - Provides: cumulative MPPT energy for each channel

2. **Config Flow** (`config_flow.py`):

   - Handles UI configuration steps
   - Validates API connectivity during setup
   - Stores API key securely
   - Allows selection of multiple families/spaces

3. **API Client** (`api_client.py`):

   - Handles all API communication
   - Manages authentication headers with User-Agent
   - Provides methods for each API endpoint
   - Error handling and logging

4. **Sensor Platform** (`sensor.py`):

   - Creates family-level aggregate sensors
   - Creates device-specific sensors based on device type
   - Handles virtual devices for battery modules
   - Manages state_class and device_class for Energy Dashboard

5. **Binary Sensor Platform** (`binary_sensor.py`):
   - Creates binary sensors for boolean states
   - Family-level: has_fault, battery_full
   - Device-level: fault, power (inverted from "off" field)

### Data Processing Logic

Each coordinator has its own `_async_update_data()` method with specific responsibilities:

**Family Coordinator**:
- Fetches space index data (today's metrics, battery/inverter/meter status)
- Retrieves SOC limits (hardware, battery BMS, strategy limits)
- Gets current battery strategy and charging box configuration
- Aggregates device counts and online/offline status

**Device Coordinator**:
- Fetches complete device list for the family
- For each online device, retrieves detailed statistics
- Processes device-specific data (meter readings, inverter power, battery SOC)
- Creates virtual battery module entries with MPPT data
- Aggregates total solar power/energy and grid export metrics

**Strategy Coordinator**:
- Fetches strategy history from the API
- Identifies the most recent strategy change
- Counts strategy changes within the current day
- Maintains a history buffer for UI display

**MPPT Energy Coordinator**:
- Reads current MPPT power values from device coordinator
- Applies trapezoidal integration to calculate energy accumulation
- Tracks each MPPT channel independently (battery and module MPPTs)
- Resets accumulation when power drops to zero

### Coordinator Interaction

The coordinators work together to provide complete system data:

1. **Initialization** (`__init__.py`):
   - Creates all coordinators for each configured family
   - Family and Device coordinators are always created
   - Strategy coordinator created for families with battery systems
   - MPPT coordinator depends on Device coordinator for power readings

2. **Sensor Creation** (`sensor.py`):
   - Family sensors use data from Family, Strategy, and MPPT coordinators
   - Device sensors use data from Device coordinator
   - Each sensor is assigned to the appropriate coordinator based on data type
   - Strategy-related sensors update every 5 minutes, others every 30 seconds

3. **Data Flow**:
   - Device coordinator provides device registry for all other components
   - MPPT coordinator reads power values from Device coordinator
   - Sensors combine data from multiple coordinators when needed
   - Binary sensors use Family and Device coordinators

### Entity Design

#### Naming Patterns

All entities use consistent naming with `sunlit` prefix:

- Family: `sunlit_{family_id}_{key}`
- Device: `sunlit_{family_id}_{device_type}_{device_id}_{key}`
- Virtual: `sunlit_{family_id}_battery_{device_id}_module{N}_{key}`

#### Device Hierarchy

1. **Family Hub**: Virtual root device for all entities
2. **Physical Devices**: Actual hardware (meters, inverters, batteries)
3. **Virtual Devices**: Battery modules for modular systems

### Virtual Devices

Battery modules (B215 extension modules 1-3) are created as separate virtual devices to:

- Prevent sensor overload (30+ sensors on single device)
- Provide logical organization in UI
- Track individual module SOC and MPPT data
- Link to main battery via `via_device`
- Each module has 2.15 kWh nominal capacity

## Important Constants

- Update interval: `DEFAULT_SCAN_INTERVAL` (30 seconds)
- Domain: `sunlit`
- Supported platforms: `[Platform.SENSOR, Platform.BINARY_SENSOR]`
- Version: `VERSION` in `const.py` (managed by release-please)
- GitHub URL: `GITHUB_URL` in `const.py`

## Recent Features

- Refactored coordinator architecture with specialized coordinators
- Different update intervals based on data volatility (30s, 1min, 5min)
- Fixed `last_strategy_change` sensor to use TIMESTAMP device class
- MPPT energy accumulation with trapezoidal integration
- Grid export energy tracking (daily and total)
- Total solar energy aggregation across all inverters
- B215 battery module virtual devices
- Makefile for development workflow

## API Reference

If we need to compare API responses, the OpenAPI spec that's included in the project can guide us.
