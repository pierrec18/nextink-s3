from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nextink_s3.const import DOMAIN
from custom_components.nextink_s3.coordinator import NextInkCoordinator
from custom_components.nextink_s3.errors import AuthenticationError, ConnectionError, RateLimitError
from custom_components.nextink_s3.parser import parse_quota


async def test_refresh_and_failure_retains_timestamp(hass, quota_html):
    entry = MockConfigEntry(domain=DOMAIN, options={"interval_hours": 12})
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_fetch.return_value = parse_quota(quota_html)
    coordinator = NextInkCoordinator(hass, entry, client)
    assert coordinator.update_interval == timedelta(hours=12)
    await coordinator.async_refresh()
    success = coordinator.last_success
    assert success is not None
    assert coordinator.last_update_success
    client.async_fetch.side_effect = ConnectionError("cannot_connect")
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.last_success == success
    client.async_fetch.side_effect = None
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert client.async_fetch.await_count == 3


async def test_auth_failure(hass):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_fetch.side_effect = AuthenticationError("invalid_auth")
    coordinator = NextInkCoordinator(hass, entry, client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_rate_limit_retry_after(hass):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_fetch.side_effect = RateLimitError(7200)
    coordinator = NextInkCoordinator(hass, entry, client)
    with pytest.raises(UpdateFailed) as err:
        await coordinator._async_update_data()
    assert err.value.retry_after == 7200
