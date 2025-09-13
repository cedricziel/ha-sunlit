"""Constants for the Sunlit REST integration."""

from datetime import timedelta

DOMAIN = "sunlit"

# Integration metadata
INTEGRATION_NAME = "ha-sunlit"
GITHUB_URL = "https://github.com/cedricziel/ha-sunlit"
VERSION = "1.0.0"  # x-release-please-version

DEFAULT_NAME = "Sunlit REST Sensor"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

# API Configuration
API_BASE_URL = "https://api.sunlitsolar.de/rest"
API_USER_LOGIN = "/user/login"
API_FAMILY_LIST = "/family/list"
API_DEVICE_DETAILS = "/device/{device_id}"
API_DEVICE_STATISTICS = "/v1.1/statistics/static/device"
API_BATTERY_IO_POWER = "/v1.3/statistics/instantPower/batteryIO"
API_DEVICE_LIST = "/v1.2/device/list"
API_SPACE_SOC = "/v1.1/space/soc"
API_SPACE_CURRENT_STRATEGY = "/v1.1/space/currentStrategy"
API_SPACE_STRATEGY_HISTORY = "/v1.1/space/strategyHistory"
API_SPACE_INDEX = "/v1.5/space/index"
API_CHARGING_BOX_CHECK_STRATEGY = "/v1.6/chargingBox/checkSpaceStrategy"

# Configuration keys
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_ACCESS_TOKEN = "access_token"
CONF_FAMILIES = "families"
CONF_FAMILY_ID = "family_id"
CONF_FAMILY_NAME = "family_name"

# Options keys for SOC event management
OPT_ENABLE_SOC_EVENTS = "enable_soc_events"
OPT_SOC_THRESHOLD_CRITICAL_LOW = "soc_threshold_critical_low"
OPT_SOC_THRESHOLD_LOW = "soc_threshold_low"
OPT_SOC_THRESHOLD_HIGH = "soc_threshold_high"
OPT_SOC_THRESHOLD_CRITICAL_HIGH = "soc_threshold_critical_high"
OPT_SOC_CHANGE_THRESHOLD = "soc_change_threshold"
OPT_MIN_EVENT_INTERVAL = "min_event_interval"

# Default option values
DEFAULT_ENABLE_SOC_EVENTS = True
DEFAULT_SOC_THRESHOLD_CRITICAL_LOW = 10
DEFAULT_SOC_THRESHOLD_LOW = 20
DEFAULT_SOC_THRESHOLD_HIGH = 90
DEFAULT_SOC_THRESHOLD_CRITICAL_HIGH = 95
DEFAULT_SOC_CHANGE_THRESHOLD = 5
DEFAULT_MIN_EVENT_INTERVAL = 60

# Default options dictionary for new installations and migrations
DEFAULT_OPTIONS = {
    OPT_ENABLE_SOC_EVENTS: DEFAULT_ENABLE_SOC_EVENTS,
    OPT_SOC_THRESHOLD_CRITICAL_LOW: DEFAULT_SOC_THRESHOLD_CRITICAL_LOW,
    OPT_SOC_THRESHOLD_LOW: DEFAULT_SOC_THRESHOLD_LOW,
    OPT_SOC_THRESHOLD_HIGH: DEFAULT_SOC_THRESHOLD_HIGH,
    OPT_SOC_THRESHOLD_CRITICAL_HIGH: DEFAULT_SOC_THRESHOLD_CRITICAL_HIGH,
    OPT_SOC_CHANGE_THRESHOLD: DEFAULT_SOC_CHANGE_THRESHOLD,
    OPT_MIN_EVENT_INTERVAL: DEFAULT_MIN_EVENT_INTERVAL,
}

# Device Types
DEVICE_TYPE_METER = "SHELLY_3EM_METER"
DEVICE_TYPE_METER_PRO = "SHELLY_PRO3EM_METER"  # Shelly Pro 3EM variant
DEVICE_TYPE_INVERTER = "YUNENG_MICRO_INVERTER"
DEVICE_TYPE_INVERTER_SOLAR = "SOLAR_MICRO_INVERTER"  # Generic solar micro inverter
DEVICE_TYPE_BATTERY = "ENERGY_STORAGE_BATTERY"

# Sensor Types for different devices
METER_SENSORS = {
    "total_ac_power": "Total AC Power",
    "daily_buy_energy": "Daily Buy Energy",
    "daily_ret_energy": "Daily Return Energy",
    "total_buy_energy": "Total Buy Energy",
    "total_ret_energy": "Total Return Energy",
}

INVERTER_SENSORS = {
    "current_power": "Current Power",
    "total_power_generation": "Total Energy Production",  # Actually energy in kWh
    "total_yield": "Total Yield",  # Lifetime energy production
    "daily_earnings": "Daily Earnings",
}

# Main battery unit sensors (system-wide and main unit specific)
BATTERY_SENSORS = {
    # System-wide sensors
    "battery_level": "Battery Level",  # Average/overall level
    "batterySoc": "System Battery SOC",
    "chargeRemaining": "Charge Time Remaining",
    "dischargeRemaining": "Discharge Time Remaining",
    "input_power_total": "Total Input Power",
    "output_power_total": "Total Output Power",
    "battery_capacity": "Nominal Capacity",  # Static 2.15 kWh per unit
    # Main unit MPPT sensors (head unit's solar inputs)
    "batteryMppt1InVol": "MPPT1 Voltage",
    "batteryMppt1InCur": "MPPT1 Current",
    "batteryMppt1InPower": "MPPT1 Power",
    "batteryMppt1Energy": "MPPT1 Total Energy",
    "batteryMppt2InVol": "MPPT2 Voltage",
    "batteryMppt2InCur": "MPPT2 Current",
    "batteryMppt2InPower": "MPPT2 Power",
    "batteryMppt2Energy": "MPPT2 Total Energy",
}

# Battery module specific sensors (will be created for each module 1, 2, 3)
BATTERY_MODULE_SENSORS = {
    # Module-specific data keys mapped to friendly names
    # The actual keys will be battery1Soc, battery2Soc, etc.
    "Soc": "Battery SOC",
    "Mppt1InVol": "MPPT Voltage",
    "Mppt1InCur": "MPPT Current",
    "Mppt1InPower": "MPPT Power",
    "Mppt1Energy": "MPPT Total Energy",
    "capacity": "Nominal Capacity",  # Static 2.15 kWh per module
}

# Family aggregate sensors
FAMILY_SENSORS = {
    "device_count": "Device Count",
    "online_devices": "Online Devices",
    "offline_devices": "Offline Devices",
    "total_ac_power": "Total AC Power",
    "average_battery_level": "Average Battery Level",
    "total_input_power": "Total Input Power",
    "total_output_power": "Total Output Power",
    # has_fault moved to binary_sensor
    # SOC configuration sensors
    "hw_soc_min": "Hardware SOC Minimum",
    "hw_soc_max": "Hardware SOC Maximum",
    "battery_soc_min": "Battery SOC Minimum",
    "battery_soc_max": "Battery SOC Maximum",
    "strategy_soc_min": "Strategy SOC Minimum",
    "strategy_soc_max": "Strategy SOC Maximum",
    "current_soc_min": "Current SOC Minimum",
    "current_soc_max": "Current SOC Maximum",
    # Power configuration sensors
    "rated_power": "Rated Power",
    "max_output_power": "Max Output Power",
    # Status sensors (text state)
    "battery_strategy": "Battery Strategy",
    "battery_status": "Battery Status",
    "battery_device_status": "Battery Device Status",
    "inverter_device_status": "Inverter Device Status",
    "meter_device_status": "Meter Device Status",
    # Strategy history sensors
    "last_strategy_change": "Last Strategy Change",
    "last_strategy_type": "Last Strategy Type",
    "last_strategy_status": "Last Strategy Status",
    "strategy_changes_today": "Strategy Changes Today",
    # New sensors from space/index endpoint
    "daily_yield": "Daily Yield",
    "daily_earnings": "Daily Earnings",
    "home_power": "Home Power",
    "currency": "Currency",
    # Total solar production tracking
    "total_solar_energy": "Total Solar Energy",
    "total_solar_power": "Total Solar Power",
    "battery_count": "Battery Module Count",
    "battery_charging_remaining": "Charging Time Remaining",
    "battery_discharging_remaining": "Discharging Time Remaining",
    "inverter_current_power": "Inverter Current Power",
    # Grid export tracking
    "total_grid_export_energy": "Total Grid Export Energy",
    "daily_grid_export_energy": "Daily Grid Export Energy",
    # Note: has_fault, battery_full, battery_bypass, battery_heater_*,
    # and boost_mode_* moved to binary_sensor
    # Charging box strategy sensors
    "ev3600_auto_strategy_mode": "EV3600 Auto Strategy Mode",
    "storage_strategy": "Storage Strategy",
    "normal_charge_box_mode": "Normal Charge Box Mode",
    "inverter_sn_list": "Inverter Serial Numbers",
}
