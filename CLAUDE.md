# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a HomeAssistant custom integration called "Sunlit" that fetches data from REST/HTTP APIs and exposes them as sensors. It's built as a cloud polling integration with UI-based configuration flow.

## Development Commands

### Setup
```bash
# Install dependencies
scripts/setup
# Or manually:
python3 -m pip install --requirement requirements.txt
```

### Code Quality
```bash
# Run linters
ruff check custom_components/sunlit/
black --check custom_components/sunlit/
isort --check-only custom_components/sunlit/

# Auto-format code
black custom_components/sunlit/
isort custom_components/sunlit/
ruff check --fix custom_components/sunlit/
```

### Testing HomeAssistant
```bash
# Run HomeAssistant in development mode (port 8123)
hass -c config
```

## Architecture

### Integration Structure
The integration follows HomeAssistant's standard custom component pattern:

- **DataUpdateCoordinator Pattern**: Uses `SunlitDataUpdateCoordinator` in `__init__.py:78-142` for efficient data fetching with 30-second polling interval
- **Config Flow**: UI-based configuration through `config_flow.py` supporting authentication methods (None, Bearer token, API key)
- **Entity Platform**: Sensor entities created dynamically from JSON response in `sensor.py`

### Key Components

1. **Coordinator** (`__init__.py:78-142`): 
   - Manages API polling and data caching
   - Handles authentication headers
   - Processes and flattens JSON responses

2. **Config Flow** (`config_flow.py`):
   - Handles UI configuration steps
   - Validates API connectivity during setup
   - Stores credentials securely

3. **Sensor Platform** (`sensor.py`):
   - Creates individual sensor entities from processed data
   - Each top-level JSON field becomes a sensor

### Data Processing Logic
The `_process_data()` method in `__init__.py:122-142`:
- Flattens nested objects (e.g., `data.temp` → `sensor.sunlit_data_temp`)
- Handles arrays by processing first 10 items
- Only processes primitive types (int, float, str, bool)

## Important Constants
- Update interval: `DEFAULT_SCAN_INTERVAL` in `const.py`
- Domain: `sunlit`
- Supported platforms: `[Platform.SENSOR]`