from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nextink_s3.const import DOMAIN
from custom_components.nextink_s3.errors import ConnectionError
from custom_components.nextink_s3.parser import parse_quota


async def test_lifecycle_shared_update_and_stable_entities(hass, quota_html):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "synthetic-user", CONF_PASSWORD: "synthetic-password"},
        unique_id="opaque-account",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.nextink_s3.NextInkClient") as cls:
        client = cls.return_value
        client.async_fetch = AsyncMock(return_value=parse_quota(quota_html))
        client.async_close = AsyncMock()
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entities = er.async_entries_for_config_entry(registry, entry.entry_id)
        assert len(entities) == 6
        ids = {e.unique_id: e.entity_id for e in entities}
        assert all("synthetic" not in uid for uid in ids)
        assert len({e.device_id for e in entities}) == 1
        assert client.async_fetch.await_count == 1
        for entity in entities:
            assert hass.states.get(entity.entity_id).state != STATE_UNAVAILABLE
        timestamp = next(e for e in entities if e.unique_id.endswith("last_success"))
        previous = hass.states.get(timestamp.entity_id).state
        client.async_fetch.side_effect = ConnectionError("cannot_connect")
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        for entity in entities:
            state = hass.states.get(entity.entity_id).state
            assert state == (previous if entity == timestamp else STATE_UNAVAILABLE)
        client.async_fetch.side_effect = None
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert all(hass.states.get(e.entity_id).state != STATE_UNAVAILABLE for e in entities)
        # Official options update causes one clean reload, no new entities.
        hass.config_entries.async_update_entry(entry, options={"interval_hours": 12})
        await hass.async_block_till_done()
        assert entry.runtime_data.update_interval == timedelta(hours=12)
        assert {
            e.unique_id: e.entity_id
            for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        } == ids
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert client.async_close.await_count >= 2


async def test_setup_failure_closes_session(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_USERNAME: "synthetic-user", CONF_PASSWORD: "synthetic-password"}
    )
    entry.add_to_hass(hass)
    with patch("custom_components.nextink_s3.NextInkClient") as cls:
        cls.return_value.async_fetch = AsyncMock(side_effect=ConnectionError("cannot_connect"))
        cls.return_value.async_close = AsyncMock()
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        cls.return_value.async_close.assert_awaited_once()
