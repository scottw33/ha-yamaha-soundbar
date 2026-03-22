"""Config flow for Yamaha Soundbar."""
from __future__ import annotations

import logging
import ssl
from pathlib import Path
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .client import YamahaCannotConnect, YamahaClient
from .const import (
    CONF_ANNOUNCE_VOLUME_INCREASE,
    CONF_ICECAST_METADATA,
    CONF_LEDOFF,
    CONF_SOURCE_IGNORE,
    CONF_SOURCES,
    CONF_UUID,
    CONF_VOLUME_STEP,
    DEFAULT_ANNOUNCE_VOLUME_INCREASE,
    DEFAULT_ICECAST_UPDATE,
    DEFAULT_LEDOFF,
    DEFAULT_VOLUME_STEP,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class YamahaSoundbarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Yamaha Soundbar."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step — user enters host IP."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]

            # Create temporary SSL context for validation
            certpath = Path(__file__).parent / "client.pem"
            ssl_ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            ssl_ctx.load_cert_chain(certpath)
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            session = aiohttp.ClientSession(connector=connector)
            try:
                client = YamahaClient(host, session, ssl_ctx)
                device_status = await client.async_get_device_status()
                uuid = device_status.get("uuid", "")
                name = device_status.get("DeviceName", host)

                await self.async_set_unique_id(uuid)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=name,
                    data={CONF_HOST: host, CONF_UUID: uuid},
                )
            except YamahaCannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            finally:
                await session.close()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    async def async_step_import(
        self, import_data: dict[str, Any]
    ) -> FlowResult:
        """Handle YAML import — auto-create config entry from existing YAML config."""
        host = import_data.get("host", "")
        uuid = import_data.get("uuid", "")

        if uuid:
            await self.async_set_unique_id(uuid)
            self._abort_if_unique_id_configured()

        # Merge sources and common_sources
        sources = import_data.get("sources", {})
        common_sources = import_data.get("common_sources", {})
        if common_sources:
            sources = {**sources, **common_sources}

        options = {
            CONF_SOURCES: sources or {},
            CONF_SOURCE_IGNORE: import_data.get("source_ignore", []),
            CONF_VOLUME_STEP: import_data.get("volume_step", DEFAULT_VOLUME_STEP),
            CONF_ANNOUNCE_VOLUME_INCREASE: import_data.get(
                "announce_volume_increase", DEFAULT_ANNOUNCE_VOLUME_INCREASE
            ),
            CONF_ICECAST_METADATA: import_data.get("icecast_metadata", DEFAULT_ICECAST_UPDATE),
            CONF_LEDOFF: import_data.get("led_off", DEFAULT_LEDOFF),
        }

        return self.async_create_entry(
            title=import_data.get("name", host),
            data={CONF_HOST: host, CONF_UUID: uuid},
            options=options,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return YamahaSoundbarOptionsFlow()


class YamahaSoundbarOptionsFlow(OptionsFlow):
    """Handle options flow for Yamaha Soundbar."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_VOLUME_STEP,
                        default=options.get(CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP),
                    ): vol.All(int, vol.Range(min=1, max=25)),
                    vol.Optional(
                        CONF_ANNOUNCE_VOLUME_INCREASE,
                        default=options.get(
                            CONF_ANNOUNCE_VOLUME_INCREASE, DEFAULT_ANNOUNCE_VOLUME_INCREASE
                        ),
                    ): vol.All(int, vol.Range(min=0, max=50)),
                    vol.Optional(
                        CONF_ICECAST_METADATA,
                        default=options.get(CONF_ICECAST_METADATA, DEFAULT_ICECAST_UPDATE),
                    ): vol.In(["Off", "StationName", "StationNameSongTitle"]),
                    vol.Optional(
                        CONF_LEDOFF,
                        default=options.get(CONF_LEDOFF, DEFAULT_LEDOFF),
                    ): bool,
                }
            ),
        )
