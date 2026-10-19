from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nextink_s3.const import DOMAIN
from custom_components.nextink_s3.errors import (
    AuthenticationError,
    ConnectionError,
    DataError,
    FormError,
    InteractiveAuthError,
)
from custom_components.nextink_s3.parser import parse_quota

CREDS = {CONF_USERNAME: "synthetic-user", CONF_PASSWORD: "synthetic-password"}


async def test_success(hass, quota_html):
    with (
        patch("custom_components.nextink_s3.config_flow.NextInkClient") as cls,
        patch("custom_components.nextink_s3.async_setup_entry", return_value=True),
    ):
        cls.return_value.async_fetch = AsyncMock(return_value=parse_quota(quota_html))
        cls.return_value.async_close = AsyncMock()
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data=CREDS
        )
        await hass.async_block_till_done()
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"] == CREDS
        assert "synthetic" not in result["result"].unique_id
        cls.return_value.async_close.assert_awaited_once()


@pytest.mark.parametrize(
    "error,key",
    [
        (AuthenticationError("invalid_auth"), "invalid_auth"),
        (InteractiveAuthError("interactive_auth"), "interactive_auth"),
        (ConnectionError("cannot_connect"), "cannot_connect"),
        (FormError("form"), "incompatible_form"),
        (DataError("missing"), "invalid_statistics"),
    ],
)
async def test_errors_close_session(hass, error, key):
    with patch("custom_components.nextink_s3.config_flow.NextInkClient") as cls:
        cls.return_value.async_fetch = AsyncMock(side_effect=error)
        cls.return_value.async_close = AsyncMock()
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data=CREDS
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": key}
        assert not hass.config_entries.async_entries(DOMAIN)
        cls.return_value.async_close.assert_awaited_once()
        hass.config_entries.flow.async_abort(result["flow_id"])


async def test_duplicate(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=CREDS, unique_id="opaque-test")
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data=CREDS
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_keeps_entry(hass, quota_html):
    entry = MockConfigEntry(domain=DOMAIN, data=CREDS, unique_id="opaque-test")
    entry.add_to_hass(hass)
    original = entry.entry_id
    with (
        patch("custom_components.nextink_s3.config_flow.NextInkClient") as cls,
        patch.object(hass.config_entries, "async_reload", return_value=True) as reload,
    ):
        cls.return_value.async_fetch = AsyncMock(return_value=parse_quota(quota_html))
        cls.return_value.async_close = AsyncMock()
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        assert result["step_id"] == "reauth_confirm"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "synthetic-new-password"}
        )
        await hass.async_block_till_done()
        assert result["type"] == FlowResultType.ABORT
        assert entry.entry_id == original
        assert entry.unique_id == "opaque-test"
        assert entry.data[CONF_PASSWORD] == "synthetic-new-password"
        reload.assert_awaited_once_with(original)
        assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_options(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=CREDS)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"interval_hours": 12}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {"interval_hours": 12}
    assert entry.data == CREDS


async def test_cancel_validation_closes(hass):
    import asyncio

    with patch("custom_components.nextink_s3.config_flow.NextInkClient") as cls:
        cls.return_value.async_fetch = AsyncMock(side_effect=asyncio.CancelledError)
        cls.return_value.async_close = AsyncMock()
        with pytest.raises(asyncio.CancelledError):
            await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": "user"}, data=CREDS
            )
        cls.return_value.async_close.assert_awaited_once()


def test_translations_complete():
    import json
    from pathlib import Path

    root = Path(__file__).parents[1] / "custom_components" / DOMAIN
    base = json.loads((root / "strings.json").read_text())

    def keys(value):
        return {
            key: keys(child) if isinstance(child, dict) else None for key, child in value.items()
        }

    for lang in ("en", "fr"):
        data = json.loads((root / "translations" / f"{lang}.json").read_text())
        assert keys(data) == keys(base)
