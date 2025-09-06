"""Constants for the Sunlit REST integration."""
from datetime import timedelta

DOMAIN = "sunlit"

DEFAULT_NAME = "Sunlit REST Sensor"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

# API Configuration
API_BASE_URL = "https://api.sunlitsolar.de/rest"
API_FAMILY_LIST = "/family/list"
API_FAMILY_DATA = "/family/{family_id}/data"

# Configuration keys
CONF_API_KEY = "api_key"
CONF_FAMILIES = "families"
CONF_FAMILY_ID = "family_id"
CONF_FAMILY_NAME = "family_name"

# Legacy configuration keys (kept for compatibility)
CONF_API_URL = "api_url"
CONF_AUTH_TYPE = "auth_type"
CONF_HEADERS = "headers"

AUTH_TYPE_NONE = "none"
AUTH_TYPE_BEARER = "bearer"
AUTH_TYPE_API_KEY = "api_key"

AUTH_TYPES = [AUTH_TYPE_NONE, AUTH_TYPE_BEARER, AUTH_TYPE_API_KEY]