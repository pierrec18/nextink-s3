"""Constants for the read-only Next.ink integration."""

DOMAIN = "nextink_s3"
ORIGIN = "https://next.ink"
STORAGE_URL = f"{ORIGIN}/profile/?tab=storage"
CONF_INTERVAL = "interval_hours"
DEFAULT_INTERVAL = 6
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT = 30
MAX_REDIRECTS = 5
