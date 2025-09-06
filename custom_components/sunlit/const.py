"""Constants for the Sunlit REST integration."""

from datetime import timedelta

DOMAIN = "sunlit"

DEFAULT_NAME = "Sunlit REST Sensor"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

# API Configuration
API_BASE_URL = "https://api.sunlitsolar.de/rest"
API_FAMILY_LIST = "/family/list"
API_DEVICE_DETAILS = "/device/{device_id}"
API_DEVICE_STATISTICS = "/v1.1/statistics/static/device"
API_BATTERY_IO_POWER = "/v1.3/statistics/instantPower/batteryIO"
API_DEVICE_LIST = "/v1.2/device/list"
API_SPACE_SOC = "/v1.1/space/soc"
API_SPACE_CURRENT_STRATEGY = "/v1.1/space/currentStrategy"
API_SPACE_STRATEGY_HISTORY = "/v1.1/space/strategyHistory"

# Configuration keys
CONF_API_KEY = "api_key"
CONF_FAMILIES = "families"
CONF_FAMILY_ID = "family_id"
CONF_FAMILY_NAME = "family_name"

# Device Types
DEVICE_TYPE_METER = "SHELLY_3EM_METER"
DEVICE_TYPE_INVERTER = "YUNENG_MICRO_INVERTER"
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
    "total_power_generation": "Total Power Generation",
    "daily_earnings": "Daily Earnings",
}

BATTERY_SENSORS = {
    "battery_level": "Battery Level",
    "input_power_total": "Input Power Total",
    "output_power_total": "Output Power Total",
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
    "has_fault": "Has Fault",
    # SOC configuration sensors
    "hw_soc_min": "Hardware SOC Minimum",
    "hw_soc_max": "Hardware SOC Maximum",
    "battery_soc_min": "Battery SOC Minimum",
    "battery_soc_max": "Battery SOC Maximum",
    "strategy_soc_min": "Strategy SOC Minimum",
    "strategy_soc_max": "Strategy SOC Maximum",
    "current_soc_min": "Current SOC Minimum",
    "current_soc_max": "Current SOC Maximum",
    # Strategy and status sensors
    "battery_strategy": "Battery Strategy",
    "battery_full": "Battery Full",
    "rated_power": "Rated Power",
    "max_output_power": "Max Output Power",
    "battery_status": "Battery Status",
    "battery_device_status": "Battery Device Status",
    "inverter_device_status": "Inverter Device Status",
    "meter_device_status": "Meter Device Status",
    # Strategy history sensors
    "last_strategy_change": "Last Strategy Change",
    "last_strategy_type": "Last Strategy Type",
    "last_strategy_status": "Last Strategy Status",
    "strategy_changes_today": "Strategy Changes Today",
}
