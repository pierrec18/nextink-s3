"""A single quota refresh for all six entities."""

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import NextInkClient
from .const import CONF_INTERVAL, DEFAULT_INTERVAL, DOMAIN
from .errors import AuthenticationError, NextInkError, RateLimitError
from .parser import Quota

_LOGGER = logging.getLogger(__name__)


class NextInkCoordinator(DataUpdateCoordinator[Quota]):
    """Store only complete snapshots and the last successful read time."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: NextInkClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(hours=entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
        )
        self.client = client
        self.last_success: datetime | None = None

    async def _async_update_data(self) -> Quota:
        try:
            data = await self.client.async_fetch()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from None
        except RateLimitError as err:
            # Both the client and HA scheduler honor Retry-After.
            raise UpdateFailed("rate_limited", retry_after=err.retry_seconds) from None
        except NextInkError as err:
            raise UpdateFailed(str(err)) from None
        self.last_success = dt_util.utcnow()
        return data
