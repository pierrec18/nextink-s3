"""UI configuration, standard reauthentication and interval options."""

from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api import NextInkClient
from .const import CONF_INTERVAL, DEFAULT_INTERVAL, DOMAIN
from .errors import (
    AuthenticationError,
    ConnectionError,
    DataError,
    FormError,
    InteractiveAuthError,
    StructureError,
)


def credentials_schema(username: str = "") -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=username): str,
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )


class NextInkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Only create an entry after an authenticated complete quota read."""

    VERSION = 1

    async def _validate(self, data: dict) -> str | None:
        client = NextInkClient(self.hass, data[CONF_USERNAME], data[CONF_PASSWORD])
        try:
            await client.async_fetch()
        except InteractiveAuthError:
            return "interactive_auth"
        except AuthenticationError:
            return "invalid_auth"
        except ConnectionError:
            return "cannot_connect"
        except FormError:
            return "incompatible_form"
        except DataError, StructureError:
            return "invalid_statistics"
        finally:
            await client.async_close()
        return None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            user_input = dict(user_input)
            user_input[CONF_USERNAME] = user_input[CONF_USERNAME].strip()
            if any(
                entry.data[CONF_USERNAME].casefold() == user_input[CONF_USERNAME].casefold()
                for entry in self._async_current_entries()
            ):
                return self.async_abort(reason="already_configured")
            if error := await self._validate(user_input):
                errors["base"] = error
            else:
                # Opaque local identity: no email in entry IDs or entity IDs.
                await self.async_set_unique_id(uuid4().hex)
                return self.async_create_entry(title="Next.ink S3", data=user_input)
        return self.async_show_form(step_id="user", data_schema=credentials_schema(), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            # Preserve the account identity; the password alone is replaced.
            data = dict(entry.data) | user_input
            if error := await self._validate(data):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data_updates=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NextInkOptionsFlow()


class NextInkOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INTERVAL,
                        default=self.config_entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=24))
                }
            ),
        )
