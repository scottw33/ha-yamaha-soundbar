"""Yamaha Soundbar integration."""
from __future__ import annotations

import logging
import ssl
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .client import YamahaClient
from .const import (
    ATTR_MASTER,
    ATTR_SNAP,
    ATTR_TRACK,
    CONF_ANNOUNCE_VOLUME_INCREASE,
    CONF_CERT_FILENAME,
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
    PLATFORMS,
    SERVICE_JOIN,
    SERVICE_PLAY,
    SERVICE_REST,
    SERVICE_SNAP,
    SERVICE_UNJOIN,
    SOURCES_DEFAULT,
)
from .coordinator import YamahaCoordinator

_LOGGER = logging.getLogger(__name__)

type YamahaSoundbarConfigEntry = ConfigEntry[YamahaCoordinator]

# Service schemas
SERVICE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids})

JOIN_SERVICE_SCHEMA = SERVICE_SCHEMA.extend({vol.Required(ATTR_MASTER): cv.entity_id})

SNAP_SERVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.comp_entity_ids,
    vol.Optional(ATTR_SNAP, default=True): cv.boolean,
})

REST_SERVICE_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.comp_entity_ids})

PLYTRK_SERVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    vol.Required(ATTR_TRACK): cv.template,
})


def _build_ssl_context() -> ssl.SSLContext:
    """Create the client SSL context.

    Runs blocking disk I/O (default CA bundle + client.pem), so it must be
    called from an executor, never directly in the event loop.
    """
    certpath = Path(__file__).parent / CONF_CERT_FILENAME
    ssl_ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ssl_ctx.load_cert_chain(certpath)
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    return ssl_ctx


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Yamaha Soundbar integration."""
    hass.data.setdefault(DOMAIN, {"entities": []})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: YamahaSoundbarConfigEntry) -> bool:
    """Set up Yamaha Soundbar from a config entry."""
    host = entry.data["host"]

    # SSL context — built in an executor because create_default_context() and
    # load_cert_chain() do blocking disk I/O (CA bundle + client.pem) that HA
    # flags if run in the event loop.
    ssl_ctx = await hass.async_add_executor_job(_build_ssl_context)

    # HTTP session
    session = async_create_clientsession(hass, verify_ssl=False)

    # Client
    client = YamahaClient(host, session, ssl_ctx)

    # Source config from options
    source_mapping = entry.options.get(CONF_SOURCES, SOURCES_DEFAULT.copy())
    source_ignore = entry.options.get(CONF_SOURCE_IGNORE, [])

    # Coordinator
    coordinator = YamahaCoordinator(
        hass, client, entry,
        source_mapping=source_mapping,
        source_ignore=source_ignore,
    )

    # Set initial LED state from options
    led_off = entry.options.get(CONF_LEDOFF, DEFAULT_LEDOFF)
    coordinator.set_led_state(not led_off)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services on first entry
    if not hass.services.has_service(DOMAIN, SERVICE_JOIN):
        _register_services(hass)

    # Reload on options change
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: YamahaSoundbarConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    def _get_entities(entity_ids):
        """Resolve entity IDs to entity objects."""
        entities = hass.data[DOMAIN]["entities"]
        if entity_ids and entity_ids != "all":
            return [e for e in entities if e.entity_id in entity_ids]
        return entities

    async def async_join_service(call: ServiceCall) -> None:
        entity_ids = call.data.get(ATTR_ENTITY_ID)
        master_id = call.data[ATTR_MASTER]
        all_entities = hass.data[DOMAIN]["entities"]
        master = next((e for e in all_entities if e.entity_id == master_id), None)
        if master:
            slaves = [e for e in _get_entities(entity_ids) if e.entity_id != master_id]
            await master.async_join(slaves)

    async def async_unjoin_service(call: ServiceCall) -> None:
        entities = _get_entities(call.data.get(ATTR_ENTITY_ID))
        masters = [e for e in entities if e.is_master]
        if masters:
            for master in masters:
                await master.async_unjoin_all()
        else:
            for entity in entities:
                await entity.async_unjoin_me()

    async def async_snapshot_service(call: ServiceCall) -> None:
        switchinput = call.data.get(ATTR_SNAP)
        for entity in _get_entities(call.data.get(ATTR_ENTITY_ID)):
            await entity.async_snapshot(switchinput)

    async def async_restore_service(call: ServiceCall) -> None:
        for entity in _get_entities(call.data.get(ATTR_ENTITY_ID)):
            await entity.async_restore()

    async def async_play_track_service(call: ServiceCall) -> None:
        track = call.data.get(ATTR_TRACK)
        for entity in _get_entities(call.data.get(ATTR_ENTITY_ID)):
            await entity.async_play_track(track)

    hass.services.async_register(DOMAIN, SERVICE_JOIN, async_join_service, schema=JOIN_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UNJOIN, async_unjoin_service, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SNAP, async_snapshot_service, schema=SNAP_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REST, async_restore_service, schema=REST_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_PLAY, async_play_track_service, schema=PLYTRK_SERVICE_SCHEMA)
