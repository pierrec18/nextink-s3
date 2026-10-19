"""Next.ink displayed S3 quota, with no S3 API operations."""

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .api import NextInkClient
from .const import CONF_INTERVAL, DEFAULT_INTERVAL
from .coordinator import NextInkCoordinator

type NextInkConfigEntry = ConfigEntry[NextInkCoordinator]
PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: NextInkConfigEntry) -> bool:
    client = NextInkClient(hass, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = NextInkCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await client.async_close()
        raise
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: NextInkConfigEntry) -> None:
    if entry.runtime_data.update_interval != timedelta(
        hours=entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)
    ):
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NextInkConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.async_close()
        return True
    return False
