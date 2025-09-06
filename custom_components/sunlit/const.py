"""Constants for the Sunlit REST integration."""
from datetime import timedelta

DOMAIN = "sunlit"

DEFAULT_NAME = "Sunlit REST Sensor"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

# API Configuration
API_BASE_URL = "https://api.sunlitsolar.de/rest"
API_FAMILY_LIST = "/family/list"
API_FAMILY_DATA = "/family/{family_id}/data"
API_DEVICE_DETAILS = "/device/{device_id}"
API_DEVICE_STATISTICS = "/v1.1/statistics/static/device"
API_BATTERY_IO_POWER = "/v1.3/statistics/instantPower/batteryIO"

# Configuration keys
CONF_API_KEY = "api_key"
CONF_FAMILIES = "families"
CONF_FAMILY_ID = "family_id"
CONF_FAMILY_NAME = "family_name"

