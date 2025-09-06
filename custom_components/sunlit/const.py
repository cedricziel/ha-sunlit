"""Constants for the Sunlit REST integration."""
from datetime import timedelta

DOMAIN = "sunlit"

DEFAULT_NAME = "Sunlit REST Sensor"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

CONF_API_URL = "api_url"
CONF_API_KEY = "api_key"
CONF_AUTH_TYPE = "auth_type"
CONF_HEADERS = "headers"

AUTH_TYPE_NONE = "none"
AUTH_TYPE_BEARER = "bearer"
AUTH_TYPE_API_KEY = "api_key"

AUTH_TYPES = [AUTH_TYPE_NONE, AUTH_TYPE_BEARER, AUTH_TYPE_API_KEY]