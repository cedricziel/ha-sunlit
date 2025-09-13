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

### Integration Structure

The integration follows HomeAssistant's standard custom component pattern:

- **DataUpdateCoordinator Pattern**: Uses `SunlitDataUpdateCoordinator` in `__init__.py` for efficient data fetching with 30-second polling interval
- **Config Flow**: UI-based configuration through `config_flow.py` with API key authentication
- **Entity Platforms**: Multiple platforms for different entity types:
  - `sensor.py`: Numeric and text sensors
  - `binary_sensor.py`: Boolean state sensors

### Key Components

1. **Coordinator** (`__init__.py`):

   - Manages API polling and data caching
   - Fetches data from multiple endpoints (device list, space SOC, strategy, statistics)
   - Aggregates family-level metrics
   - Handles online device statistics

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

The `_async_update_data()` method in `__init__.py`:

- Fetches device list for each family
- Aggregates metrics across all devices
- Fetches additional data for online battery devices
- Creates virtual device data for battery modules
- Processes strategy history for recent changes
- Calculates total solar energy and grid export energy

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

- Grid export energy tracking (daily and total)
- Total solar energy aggregation across all inverters
- B215 battery module virtual devices
- Makefile for development workflow
- if we need to compare api responses, the openapi spec that's included in the project can guide us.
