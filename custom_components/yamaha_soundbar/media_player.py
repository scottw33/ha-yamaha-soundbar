"""Media player entity for Yamaha Linkplay A118 based devices."""
from __future__ import annotations

import asyncio
import logging
import re
import string
import struct
import urllib.error
import urllib.request
from http import HTTPStatus

import aiohttp
import async_timeout
import chardet
import requests
import xml.etree.ElementTree as ET

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaType,
)
from homeassistant.components.media_player.browse_media import (
    async_process_play_media_url,
)
from homeassistant.components.media_player.const import (
    ATTR_GROUP_MEMBERS,
    ATTR_MEDIA_ANNOUNCE,
    ATTR_MEDIA_CONTENT_ID,
    RepeatMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    STATE_IDLE,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.dt import utcnow

from .const import (
    AUTOIDLE_STATE_TIMEOUT,
    CONF_ANNOUNCE_VOLUME_INCREASE,
    CONF_ICECAST_METADATA,
    CONF_VOLUME_STEP,
    CUT_EXTENSIONS,
    DEFAULT_ANNOUNCE_VOLUME_INCREASE,
    DEFAULT_ICECAST_UPDATE,
    DEFAULT_VOLUME_STEP,
    DOMAIN,
    FW_MROOM_RTR_MIN,
    FW_SLOW_STREAMS,
    ICON_BLUETOOTH,
    ICON_DEFAULT,
    ICON_MULTIROOM,
    ICON_MUTED,
    ICON_PLAYING,
    ICON_PUSHSTREAM,
    ICON_TTS,
    ICE_THROTTLE,
    MAX_VOL,
    MROOM_UJWDIR,
    MROOM_UJWROU,
    PARALLEL_UPDATES,
    ROOTDIR_USB,
    SOUND_MODES,
    SOURCES_LIVEIN,
    SOURCES_LOCALF,
    SOURCES_MAP,
    SOURCES_STREAM,
    SPOTIFY_PAUSED_TIMEOUT,
    UUID_ARYLIC,
    FW_RAKOIT_UART_MIN,
)
from .coordinator import YamahaCoordinator
from .entity import YamahaSoundbarEntity

_LOGGER = logging.getLogger(__name__)

# Attributes for extra state
ATTR_SLAVE = "slave"
ATTR_YAMAHA_GROUP = "yamaha_group"
ATTR_FWVER = "firmware"
ATTR_TRCNT = "tracks_local"
ATTR_TRCRT = "track_current"
ATTR_UUID = "uuid"
ATTR_TTS = "tts_active"
ATTR_SNAPSHOT = "snapshot_active"
ATTR_SNAPSPOT = "snapshot_spotify"
ATTR_DEBUG = "debug_info"
ATTR_MASS_POSITION = "media_position_mass"


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Handle YAML config -- trigger import flow to create config entry."""
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "import"},
            data=dict(config),
        )
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up media player from a config entry."""
    coordinator: YamahaCoordinator = entry.runtime_data
    entity = YamahaDevice(coordinator, entry)
    async_add_entities([entity])
    hass.data[DOMAIN]["entities"].append(entity)


class YamahaDevice(YamahaSoundbarEntity, MediaPlayerEntity):
    """Yamaha Linkplay media player entity."""

    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_media_content_type = MediaType.MUSIC

    def __init__(self, coordinator: YamahaCoordinator, entry: ConfigEntry) -> None:
        """Initialize the media player."""
        super().__init__(coordinator)

        self._entry = entry
        self._attr_unique_id = "yamaha_media_" + coordinator.data.uuid

        # Config options
        self._volume_step = entry.options.get(CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP)
        self._announce_volume_increase = entry.options.get(
            CONF_ANNOUNCE_VOLUME_INCREASE, DEFAULT_ANNOUNCE_VOLUME_INCREASE
        )
        self._icecast_meta = entry.options.get(
            CONF_ICECAST_METADATA, DEFAULT_ICECAST_UPDATE
        )

        # Playback mode tracking (entity-local)
        self._playing_localfile = True
        self._playing_stream = False
        self._playing_liveinput = False
        self._playing_spotify = False
        self._playing_webplaylist = False
        self._playing_tts = False
        self._playing_mediabrowser = False
        self._playing_mass = False
        self._playing_mass_radio = False

        # TTS / Announce state
        self._announce = False
        self._snapshot_active = False
        self._snap_source = None
        self._snap_state = STATE_UNKNOWN
        self._snap_volume = 0
        self._snap_uri = None
        self._snap_spotify = False
        self._snap_spotify_volumeonly = False
        self._snap_mass = False
        self._snap_nometa = False
        self._snap_playing_mediabrowser = False
        self._snap_media_source_uri = None
        self._snap_seek = False
        self._snap_playhead_position = 0

        # Media metadata (entity-local, enriched beyond coordinator)
        self._media_title = None
        self._media_artist = None
        self._media_prev_artist = None
        self._media_album = None
        self._media_prev_title = None
        self._media_image_url = None
        self._media_uri = None
        self._media_uri_final = None
        self._media_source_uri = None
        self._nometa = False
        self._new_song = True
        self._icecast_name = None
        self._ice_skip_throt = False
        self._ice_last_update = None

        # Playback position
        self._playhead_position = 0
        self._mass_position = 0
        self._duration = 0
        self._position_updated_at = None
        self._idletime_updated_at = utcnow()
        self._spotify_paused_at = None

        # State
        self._state = STATE_IDLE
        self._source = None
        self._prev_source = None
        self._features = None
        self._icon = ICON_DEFAULT

        # Track list (USB/local)
        self._trackq = []
        self._trackc = None

        # Multiroom state (entity-local)
        self._slave_mode = False
        self._slave_ip = None
        self._master = None
        self._is_master = False
        self._slave_list = None
        self._multiroom_group = []
        self._multiroom_prevsrc = None
        self._multiroom_unjoinat = None

        # Multiroom wifi direct detection
        self._multiroom_wifidirect = False
        self._wifi_channel = None
        self._ssid = None

        # First update tracking
        self._first_update = True

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        # Listen for Music Assistant bus events
        self.async_on_remove(
            self.hass.bus.async_listen("mass_event", self.handle_event)
        )

    # ------------------------------------------------------------------
    # Coordinator callback — runs after every coordinator poll
    # ------------------------------------------------------------------

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = self.coordinator.data
        if data is None:
            return

        player_status = data.raw_player_status
        if not player_status:
            self.async_write_ha_state()
            return

        # Skip update when in slave mode
        if self._master is None:
            self._slave_mode = False
        if self._slave_mode:
            self.async_write_ha_state()
            return

        # Handle multiroom unjoin wait period
        if self._multiroom_unjoinat is not None:
            waittim = MROOM_UJWDIR if self._multiroom_wifidirect else MROOM_UJWROU
            if utcnow() <= (self._multiroom_unjoinat + waittim):
                self._source = None
                self._media_title = None
                self._media_artist = None
                self._media_uri = None
                self._media_uri_final = None
                self._media_image_url = None
                self._state = STATE_IDLE
                self.async_write_ha_state()
                return
            else:
                self._multiroom_unjoinat = None
                self._playhead_position = 0
                self._duration = 0
                self._position_updated_at = utcnow()
                self._idletime_updated_at = self._position_updated_at
                if self._multiroom_prevsrc:
                    self.hass.async_create_task(self.async_select_source(self._multiroom_prevsrc))
                    self._multiroom_prevsrc = None
                self.async_write_ha_state()
                return

        # First update — detect firmware capabilities, LED, UPnP tracklist
        if self._first_update:
            self._first_update = False
            self._duration = 0
            self._playhead_position = 0
            self._idletime_updated_at = utcnow()
            # Detect wifi direct mode from firmware version
            if not self._multiroom_wifidirect and data.firmware:
                if self._fwvercheck(data.firmware) < self._fwvercheck(FW_MROOM_RTR_MIN):
                    self._multiroom_wifidirect = True
            self._wifi_channel = data.wifi_channel
            # LED off on first update if needed
            if data.uuid and data.uuid.startswith(UUID_ARYLIC):
                if self._fwvercheck(data.firmware) >= self._fwvercheck(FW_RAKOIT_UART_MIN):
                    from .const import CONF_LEDOFF, DEFAULT_LEDOFF
                    if self._entry.options.get(CONF_LEDOFF, DEFAULT_LEDOFF):
                        self.hass.async_create_task(
                            self.hass.async_add_executor_job(
                                self.coordinator.client.set_led_sync, False
                            )
                        )
            # Load USB tracklist if udisk source is available
            source_list = data.source_list
            if "udisk" in source_list:
                self.hass.async_create_task(self.async_tracklist_via_upnp("USB"))

        self._position_updated_at = utcnow()

        # Multiroom group bookkeeping
        if player_status.get("type") == "0":
            self._slave_mode = False
        if not self._multiroom_group:
            self._slave_mode = False
            self._is_master = False
            self._master = None
        if not self._is_master:
            self._master = None
            self._multiroom_group = []

        # State detection
        mode = str(player_status.get("mode", "0"))
        status = str(player_status.get("status", "stop"))

        if mode in ["-1", "0"] or status == "stop":
            if utcnow() >= (self._idletime_updated_at + AUTOIDLE_STATE_TIMEOUT):
                self._state = STATE_IDLE
                self._media_uri_final = None
                self._media_uri = None
        elif status in ["play", "load"]:
            self._state = STATE_PLAYING
        elif status == "pause":
            self._state = STATE_PAUSED

        # Position tracking
        self._mass_position = int(int(player_status.get("curpos", 0)) / 1000)

        if not self._playing_mass:
            if self._state in [STATE_PLAYING, STATE_PAUSED]:
                self._duration = int(int(player_status.get("totlen", 0)) / 1000)
                self._playhead_position = int(int(player_status.get("curpos", 0)) / 1000)
            else:
                self._duration = 0
                self._playhead_position = 0

        # Detect playing modes
        self._playing_spotify = bool(mode == "31")
        self._playing_liveinput = mode in SOURCES_LIVEIN
        self._playing_stream = mode in SOURCES_STREAM
        self._playing_localfile = mode in SOURCES_LOCALF

        # Announce volume increase detection
        if self._announce and self._playing_stream and not self._playing_tts:
            self._playing_stream = False
            self._playing_tts = True
            if self._announce_volume_increase > 0:
                volume = int(self._snap_volume) + int(self._announce_volume_increase)
                if volume > 100:
                    volume = 100
                _LOGGER.debug(
                    "For: %s, Announce started, increasing volume with %s to %s",
                    self.entity_id, self._announce_volume_increase, volume,
                )
                self.hass.async_create_task(
                    self.coordinator.client._async_httpapi(f"setPlayerCmd:vol:{volume}")
                )

        if mode != "10":
            self._playing_mediabrowser = False
            self._playing_mass = False

        if not (self._playing_liveinput or self._playing_stream or self._playing_spotify):
            self._playing_localfile = True

        # URI detection
        try:
            if self._playing_stream and player_status.get("uri", "") != "":
                try:
                    self._media_uri_final = str(
                        bytearray.fromhex(player_status["uri"]).decode("utf-8")
                    )
                except ValueError:
                    self._media_uri_final = player_status["uri"]
                if not self._media_uri:
                    self._media_uri = self._media_uri_final
        except KeyError:
            pass

        # CDN detection for web playlists
        if self._media_uri:
            self._playing_webplaylist = (
                "audio.tidal." in self._media_uri
                or ".dzcdn." in self._media_uri
                or ".deezer." in self._media_uri
            )

        # Source detection
        if not (self._playing_webplaylist or self._playing_mass):
            source_t = SOURCES_MAP.get(mode, "Network")
            source_n = None
            if source_t == "Network":
                if self._media_uri:
                    source_n = data.source_list.get(self._media_uri, "Network")
            else:
                source_n = data.source_list.get(source_t, None)
            self._source = source_n if source_n is not None else source_t
        else:
            self._source = "Web playlist"

        # Live input state handling
        if self._source != "Network" and not (
            self._playing_stream or self._playing_localfile or self._playing_spotify
        ):
            if self._source == "Idle":
                self._state = STATE_IDLE
                self._media_title = None
            else:
                self._state = STATE_PLAYING
                self._media_title = self._source
            self._media_artist = None
            self._media_album = None
            self._media_image_url = None
            self._icecast_name = None

        if mode in ["1", "2", "3"]:
            self._state = STATE_PLAYING
            self._media_title = self._source

        if self._playing_spotify and self._state == STATE_IDLE:
            self._source = None

        # Spotify pause timeout
        if self._spotify_paused_at is not None:
            if utcnow() >= (self._spotify_paused_at + SPOTIFY_PAUSED_TIMEOUT):
                self.hass.async_create_task(self.async_media_stop())
                self.async_write_ha_state()
                return

        # Auto-load tracklist for USB
        if mode in ["11", "16"] and len(self._trackq) <= 0:
            if int(player_status.get("curpos", 0)) > 6000 and self._state == STATE_PLAYING:
                self.hass.async_create_task(self.async_tracklist_via_upnp("USB"))

        # Metadata enrichment tasks
        if self._playing_spotify:
            if self._state != STATE_IDLE:
                self.hass.async_create_task(self.async_update_via_upnp())
            if self._state == STATE_PAUSED:
                if self._spotify_paused_at is None:
                    self._spotify_paused_at = utcnow()
            else:
                self._spotify_paused_at = None

        elif self._playing_webplaylist:
            if self._state != STATE_IDLE:
                self.hass.async_create_task(self.async_update_via_upnp())

        else:
            self._spotify_paused_at = None
            if self._state not in [STATE_PLAYING, STATE_PAUSED]:
                self._media_title = None
                self._media_artist = None
                self._media_album = None
                self._media_image_url = None
                self._icecast_name = None
                if self._announce:
                    self.hass.async_create_task(self.async_restore())

            if (
                self._playing_localfile
                and self._state in [STATE_PLAYING, STATE_PAUSED]
                and not self._playing_tts
                and not self._playing_mass
            ):
                self._parse_playerstatus_metadata(player_status)
                if self._media_title is not None and self._media_artist is None:
                    querywords = self._media_title.split(".")
                    resultwords = [w for w in querywords if w.lower() not in CUT_EXTENSIONS]
                    title = " ".join(resultwords)
                    title = title.replace("_", " ")
                    if " - " in title:
                        titles = title.split(" - ")
                        self._media_artist = string.capwords(titles[0].strip().strip("-"))
                        self._media_title = string.capwords(titles[1].strip().strip("-"))
                    else:
                        self._media_title = string.capwords(title.strip().strip("-"))
                else:
                    self._media_title = self._source

            elif (
                self._state == STATE_PLAYING
                and self._media_uri
                and int(player_status.get("totlen", 0)) > 0
                and not self._snapshot_active
                and not self._playing_tts
                and not self._playing_mediabrowser
                and not self._playing_mass
            ):
                if not self._nometa:
                    self._parse_playerstatus_metadata(player_status)

            elif (
                self._state == STATE_PLAYING
                and self._media_uri_final
                and int(player_status.get("totlen", 0)) <= 0
                and not self._snapshot_active
                and not self._playing_tts
                and not self._playing_mass
            ):
                # Schedule icecast metadata fetch (throttled)
                now = utcnow()
                should_fetch = (
                    self._ice_last_update is None
                    or now >= (self._ice_last_update + ICE_THROTTLE)
                    or self._ice_skip_throt
                )
                if should_fetch:
                    self._ice_skip_throt = False
                    self._ice_last_update = now
                    self.hass.async_create_task(self.async_update_from_icecast())

            elif (
                self._state == STATE_PLAYING
                and self._playing_mediabrowser
                and self._media_source_uri is not None
            ):
                if not self._nometa:
                    self._parse_local_mediasource_metadata_from_path()

            self._new_song = self._is_playing_new_track()

        self._media_prev_artist = self._media_artist
        self._media_prev_title = self._media_title

        # Update icon
        self._icon = self._compute_icon()

        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def icon(self) -> str:
        """Return the icon of the device."""
        return self._icon

    def _compute_icon(self) -> str:
        """Compute the current icon based on state."""
        if self._playing_tts or self._announce:
            return ICON_TTS
        if self._state in [STATE_PAUSED, STATE_IDLE, STATE_UNKNOWN]:
            return ICON_DEFAULT
        if self.coordinator.data.muted:
            return ICON_MUTED
        if self._slave_mode or self._is_master:
            return ICON_MULTIROOM
        if self._source == "Bluetooth":
            return ICON_BLUETOOTH
        if self._source in ("DLNA", "Airplay", "Spotify"):
            return ICON_PUSHSTREAM
        if self._state == STATE_PLAYING:
            return ICON_PLAYING
        return ICON_DEFAULT

    @property
    def state(self) -> str:
        """Return the state of the device."""
        return self._state

    @property
    def volume_level(self) -> float:
        """Volume level of the media player (0..1)."""
        return self.coordinator.data.volume

    @property
    def is_volume_muted(self) -> bool:
        """Return boolean if volume is currently muted."""
        return self.coordinator.data.muted

    @property
    def source(self) -> str | None:
        """Return the current input source."""
        if self._source not in ("Idle", "Network"):
            return self._source
        return None

    @property
    def source_list(self) -> list[str] | None:
        """Return the list of available input sources."""
        source_list = self.coordinator.data.source_list.copy()
        if "wifi" in source_list:
            del source_list["wifi"]
        if len(source_list) > 0:
            return list(source_list.values())
        return None

    @property
    def sound_mode(self) -> str | None:
        """Return the current sound mode (EQ)."""
        return self.coordinator.data.eq_mode

    @property
    def sound_mode_list(self) -> list[str]:
        """Return the available sound modes."""
        return sorted(list(SOUND_MODES.values()))

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Flag media player features that are supported."""
        if self._slave_mode and self._features:
            return self._features

        if self._playing_localfile or self._playing_spotify or self._playing_webplaylist:
            if self._state in [STATE_PLAYING, STATE_PAUSED]:
                self._features = (
                    MediaPlayerEntityFeature.SELECT_SOURCE
                    | MediaPlayerEntityFeature.SELECT_SOUND_MODE
                    | MediaPlayerEntityFeature.PLAY_MEDIA
                    | MediaPlayerEntityFeature.GROUPING
                    | MediaPlayerEntityFeature.BROWSE_MEDIA
                    | MediaPlayerEntityFeature.VOLUME_SET
                    | MediaPlayerEntityFeature.VOLUME_STEP
                    | MediaPlayerEntityFeature.VOLUME_MUTE
                    | MediaPlayerEntityFeature.STOP
                    | MediaPlayerEntityFeature.PLAY
                    | MediaPlayerEntityFeature.PAUSE
                    | MediaPlayerEntityFeature.NEXT_TRACK
                    | MediaPlayerEntityFeature.PREVIOUS_TRACK
                    | MediaPlayerEntityFeature.SHUFFLE_SET
                    | MediaPlayerEntityFeature.REPEAT_SET
                    | MediaPlayerEntityFeature.SEEK
                )
            else:
                self._features = (
                    MediaPlayerEntityFeature.SELECT_SOURCE
                    | MediaPlayerEntityFeature.SELECT_SOUND_MODE
                    | MediaPlayerEntityFeature.PLAY_MEDIA
                    | MediaPlayerEntityFeature.GROUPING
                    | MediaPlayerEntityFeature.BROWSE_MEDIA
                    | MediaPlayerEntityFeature.VOLUME_SET
                    | MediaPlayerEntityFeature.VOLUME_STEP
                    | MediaPlayerEntityFeature.VOLUME_MUTE
                    | MediaPlayerEntityFeature.STOP
                    | MediaPlayerEntityFeature.PLAY
                    | MediaPlayerEntityFeature.PAUSE
                    | MediaPlayerEntityFeature.NEXT_TRACK
                    | MediaPlayerEntityFeature.PREVIOUS_TRACK
                    | MediaPlayerEntityFeature.SHUFFLE_SET
                    | MediaPlayerEntityFeature.REPEAT_SET
                )

        elif self._playing_stream or self._playing_mediabrowser:
            self._features = (
                MediaPlayerEntityFeature.SELECT_SOURCE
                | MediaPlayerEntityFeature.SELECT_SOUND_MODE
                | MediaPlayerEntityFeature.PLAY_MEDIA
                | MediaPlayerEntityFeature.GROUPING
                | MediaPlayerEntityFeature.BROWSE_MEDIA
                | MediaPlayerEntityFeature.VOLUME_SET
                | MediaPlayerEntityFeature.VOLUME_STEP
                | MediaPlayerEntityFeature.VOLUME_MUTE
                | MediaPlayerEntityFeature.STOP
                | MediaPlayerEntityFeature.PLAY
                | MediaPlayerEntityFeature.PAUSE
                | MediaPlayerEntityFeature.SEEK
            )

        elif self._playing_liveinput:
            self._features = (
                MediaPlayerEntityFeature.SELECT_SOURCE
                | MediaPlayerEntityFeature.SELECT_SOUND_MODE
                | MediaPlayerEntityFeature.PLAY_MEDIA
                | MediaPlayerEntityFeature.GROUPING
                | MediaPlayerEntityFeature.BROWSE_MEDIA
                | MediaPlayerEntityFeature.VOLUME_SET
                | MediaPlayerEntityFeature.VOLUME_STEP
                | MediaPlayerEntityFeature.VOLUME_MUTE
                | MediaPlayerEntityFeature.STOP
            )

        return self._features

    @property
    def media_position(self) -> int | None:
        """Time in seconds of current playback head position."""
        if (
            self._playing_localfile
            or self._playing_spotify
            or self._slave_mode
            or self._playing_mediabrowser
            or self._playing_mass
        ) and self.available:
            return self._playhead_position
        return None

    @property
    def media_duration(self) -> int | None:
        """Time in seconds of current song duration."""
        if (
            self._playing_localfile
            or self._playing_spotify
            or self._slave_mode
            or self._playing_mediabrowser
            or self._playing_mass
        ) and self.available:
            return self._duration
        return None

    @property
    def media_position_updated_at(self):
        """When the seek position was last updated."""
        if not self._playing_liveinput and self._state == STATE_PLAYING:
            return self._position_updated_at
        return None

    @property
    def shuffle(self) -> bool:
        """Return True if shuffle mode is enabled."""
        return self.coordinator.data.shuffle

    @property
    def repeat(self) -> str:
        """Return repeat mode."""
        return self.coordinator.data.repeat

    @property
    def media_title(self) -> str | None:
        """Return title of the current track."""
        return self._media_title

    @property
    def media_artist(self) -> str | None:
        """Return name of the current track artist."""
        return self._media_artist

    @property
    def media_album_name(self) -> str | None:
        """Return name of the current track album."""
        return self._media_album

    @property
    def media_image_url(self) -> str | None:
        """Return the image for the current track."""
        return self._media_image_url

    @property
    def media_content_id(self) -> str | None:
        """Content ID of current playing media."""
        return self._media_uri_final

    @property
    def slave(self) -> bool:
        """Return true if it is a slave."""
        return self._slave_mode

    @property
    def master(self):
        """Master entity used in multiroom configuration."""
        return self._master

    @property
    def is_master(self) -> bool:
        """Return true if it is a master."""
        return self._is_master

    @property
    def extra_state_attributes(self) -> dict:
        """List members in group and set master and slave state."""
        attributes = {}
        if self._multiroom_group:
            attributes[ATTR_YAMAHA_GROUP] = self._multiroom_group
            attributes[ATTR_GROUP_MEMBERS] = self._multiroom_group

        attributes["master"] = self._is_master
        if self._slave_mode:
            attributes[ATTR_SLAVE] = self._slave_mode
        if self._media_uri_final:
            attributes[ATTR_MEDIA_CONTENT_ID] = self._media_uri_final
        if len(self._trackq) > 0:
            attributes[ATTR_TRCNT] = len(self._trackq) - 1
        if self._trackc:
            attributes[ATTR_TRCRT] = self._trackc
        if self.coordinator.data.uuid:
            attributes[ATTR_UUID] = self.coordinator.data.uuid

        attributes[ATTR_TTS] = self._playing_tts
        attributes[ATTR_SNAPSHOT] = self._snapshot_active
        attributes[ATTR_SNAPSPOT] = self._snap_spotify
        attributes[ATTR_MASS_POSITION] = self._mass_position

        atrdbg = ""
        if self._playing_localfile:
            atrdbg += " _playing_localfile"
        if self._playing_spotify:
            atrdbg += " _playing_spotify"
        if self._playing_webplaylist:
            atrdbg += " _playing_webplaylist"
        if self._playing_stream:
            atrdbg += " _playing_stream"
        if self._playing_liveinput:
            atrdbg += " _playing_liveinput"
        if self._playing_tts:
            atrdbg += " _playing_tts"
        if self._playing_mediabrowser:
            atrdbg += " _playing_mediabrowser"
        if self._playing_mass:
            atrdbg += " _playing_mass"
        attributes[ATTR_DEBUG] = atrdbg

        if self.available:
            attributes[ATTR_FWVER] = (
                f"{self.coordinator.data.firmware}.{self.coordinator.data.mcu_ver}"
            )

        return attributes

    @property
    def host(self) -> str:
        """Device host IP."""
        return self.coordinator.client.host

    @property
    def track_count(self) -> int:
        """Number of tracks present on the device."""
        return len(self._trackq) - 1 if len(self._trackq) > 0 else 0

    # ------------------------------------------------------------------
    # Playback controls
    # ------------------------------------------------------------------

    async def async_media_next_track(self) -> None:
        """Send media_next command."""
        if not self._slave_mode:
            if not self._playing_mass:
                await self.coordinator.client.async_next()
                self._playhead_position = 0
                self._duration = 0
                self._position_updated_at = utcnow()
                self._trackc = None
            else:
                await self.hass.services.async_call(
                    "mass", "queue_command",
                    service_data={"entity_id": self.entity_id, "command": "next"},
                )
            await self.coordinator.async_request_refresh()
        else:
            await self._master.async_media_next_track()

    async def async_media_previous_track(self) -> None:
        """Send media_previous command."""
        if not self._slave_mode:
            if not self._playing_mass:
                await self.coordinator.client.async_previous()
                self._playhead_position = 0
                self._duration = 0
                self._position_updated_at = utcnow()
                self._trackc = None
            else:
                await self.hass.services.async_call(
                    "mass", "queue_command",
                    service_data={"entity_id": self.entity_id, "command": "previous"},
                )
            await self.coordinator.async_request_refresh()
        else:
            await self._master.async_media_previous_track()

    async def async_media_play(self) -> None:
        """Send media_play command."""
        if not self._slave_mode:
            if self._state == STATE_PAUSED:
                await self.coordinator.client.async_play()
            elif self._prev_source is not None:
                source_list = self.coordinator.data.source_list
                temp_source = next(
                    (k for k in source_list if source_list[k] == self._prev_source), None
                )
                if temp_source is None:
                    return
                if temp_source.startswith("http") or temp_source in ("udisk", "TFcard"):
                    await self.async_select_source(self._prev_source)
                    if self._source is not None:
                        self._source = None
                    return
                else:
                    await self.coordinator.client.async_play()
            else:
                await self.coordinator.client.async_play()

            self._state = STATE_PLAYING
            self._position_updated_at = utcnow()
            self._idletime_updated_at = self._position_updated_at
            if self._slave_list is not None:
                for slave in self._slave_list:
                    await slave.async_set_state(self._state)
                    await slave.async_set_position_updated_at(self.media_position_updated_at)
            await self.coordinator.async_request_refresh()
        else:
            await self._master.async_media_play()

    async def async_media_pause(self) -> None:
        """Send media_pause command."""
        if not self._slave_mode:
            if self._playing_stream and not (self._playing_mediabrowser or self._playing_mass):
                await self.async_media_stop()
                return

            await self.coordinator.client.async_pause()
            self._position_updated_at = utcnow()
            self._idletime_updated_at = self._position_updated_at
            if self._playing_spotify:
                self._spotify_paused_at = utcnow()
            self._state = STATE_PAUSED
            if self._slave_list is not None:
                for slave in self._slave_list:
                    await slave.async_set_state(self._state)
                    await slave.async_set_position_updated_at(self.media_position_updated_at)
            await self.coordinator.async_request_refresh()
        else:
            await self._master.async_media_pause()

    async def async_media_stop(self) -> None:
        """Send stop command."""
        if not self._slave_mode:
            fw = self.coordinator.data.firmware

            if self._playing_spotify or self._playing_liveinput:
                if self._fwvercheck(fw) >= self._fwvercheck(FW_SLOW_STREAMS):
                    await self.coordinator.client.async_pause()
                await self.coordinator.client.async_select_source("wifi")

            if self._playing_stream:
                if self._fwvercheck(fw) >= self._fwvercheck(FW_SLOW_STREAMS):
                    await self.coordinator.client.async_pause()
                    await self.coordinator.client.async_select_source("wifi")

            await self.coordinator.client.async_stop()
            self._state = STATE_IDLE
            self._playhead_position = 0
            self._duration = 0
            self._media_title = None
            self._prev_source = self._source
            self._source = None
            self._nometa = False
            self._media_artist = None
            self._media_album = None
            self._icecast_name = None
            self._media_uri = None
            self._media_uri_final = None
            self._media_source_uri = None
            self._playing_mediabrowser = False
            self._playing_mass = False
            self._playing_stream = False
            self._trackc = None
            self._media_image_url = None
            self._position_updated_at = utcnow()
            self._idletime_updated_at = self._position_updated_at
            self._spotify_paused_at = None
            self._snapshot_active = False
            self.async_write_ha_state()
            if self._slave_list is not None:
                for slave in self._slave_list:
                    await slave.async_set_state(self._state)
                    await slave.async_set_position_updated_at(self.media_position_updated_at)
            await self.coordinator.async_request_refresh()
        else:
            await self._master.async_media_stop()

    async def async_media_seek(self, position: float) -> None:
        """Send media_seek command."""
        if not self._slave_mode:
            if self._duration > 0 and 0 <= position <= self._duration:
                await self.coordinator.client.async_seek(int(position))
                self._position_updated_at = utcnow()
                self._idletime_updated_at = self._position_updated_at
            await self.coordinator.async_request_refresh()
        else:
            await self._master.async_media_seek(position)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, input range 0..1."""
        vol = round(int(volume * MAX_VOL))
        await self.coordinator.client.async_set_volume(vol)
        await self.coordinator.async_request_refresh()

    async def async_volume_up(self) -> None:
        """Increase volume one step."""
        current_vol = int(self.coordinator.data.volume * MAX_VOL)
        if current_vol >= 100 and not self.coordinator.data.muted:
            return
        volume = min(100, current_vol + int(self._volume_step))
        await self.coordinator.client.async_set_volume(volume)
        await self.coordinator.async_request_refresh()

    async def async_volume_down(self) -> None:
        """Decrease volume one step."""
        current_vol = int(self.coordinator.data.volume * MAX_VOL)
        if current_vol <= 0:
            return
        volume = max(0, current_vol - int(self._volume_step))
        await self.coordinator.client.async_set_volume(volume)
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute (true) or unmute (false) media player."""
        await self.coordinator.client.async_mute(mute)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Use unmute instead, because power is not supported."""
        await self.async_mute_volume(False)

    async def async_turn_off(self) -> None:
        """Use mute instead, because power is not supported."""
        await self.async_mute_volume(True)

    async def async_toggle(self) -> None:
        """Toggle mute."""
        await self.async_mute_volume(not self.coordinator.data.muted)

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        if not self._slave_mode:
            self._nometa = False
            source_list = self.coordinator.data.source_list
            temp_source = next((k for k in source_list if source_list[k] == source), None)
            if temp_source is None:
                return

            fw = self.coordinator.data.firmware
            if self._playing_spotify:
                if self._fwvercheck(fw) >= self._fwvercheck(FW_SLOW_STREAMS):
                    await self.coordinator.client.async_pause()
                await self.coordinator.client.async_select_source("wifi")

            if temp_source == "udisk":
                await self.async_tracklist_via_upnp("USB")

            if temp_source.startswith("http"):
                temp_source_final = await self.async_detect_stream_url_redirection(temp_source)

                if self._fwvercheck(fw) >= self._fwvercheck(FW_SLOW_STREAMS) and self._state == STATE_PLAYING:
                    await self.coordinator.client.async_pause()

                await self.coordinator.client.async_play_media(temp_source_final)
                self._state = STATE_PLAYING
                self._playing_tts = False
                self._playing_mass = False
                self._source = source
                self._media_uri = temp_source
                self._media_uri_final = temp_source_final
                self._playhead_position = 0
                self._duration = 0
                self._trackc = None
                self._position_updated_at = utcnow()
                self._idletime_updated_at = self._position_updated_at
                self._media_title = None
                self._media_artist = None
                self._media_album = None
                self._icecast_name = None
                self._media_image_url = None
                self._ice_skip_throt = True
                if self._slave_list is not None:
                    for slave in self._slave_list:
                        await slave.async_set_source(source)
            else:
                await self.coordinator.client.async_select_source(temp_source)
                self._state = STATE_PLAYING
                self._source = source
                self._media_uri = None
                self._media_uri_final = None
                self._playhead_position = 0
                self._duration = 0
                self._trackc = None
                self._position_updated_at = utcnow()
                self._idletime_updated_at = self._position_updated_at
                if self._slave_list is not None:
                    for slave in self._slave_list:
                        await slave.async_set_source(source)

            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        else:
            await self._master.async_select_source(source)

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        """Set Sound Mode (EQ) for device."""
        if not self._slave_mode:
            mode = list(SOUND_MODES.keys())[list(SOUND_MODES.values()).index(sound_mode)]
            await self.coordinator.client.async_set_eq_mode(int(mode))
            if self._slave_list is not None:
                for slave in self._slave_list:
                    await slave.async_set_sound_mode(sound_mode)
            await self.coordinator.async_request_refresh()
        else:
            await self._master.async_select_sound_mode(sound_mode)

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Change the shuffle mode."""
        if not self._slave_mode:
            if shuffle:
                repeat = self.coordinator.data.repeat
                if repeat == RepeatMode.ONE:
                    mode = "4"  # shuffle + repeat one
                else:
                    mode = "2"  # shuffle + repeat all (default)
            else:
                repeat = self.coordinator.data.repeat
                if repeat == RepeatMode.ALL:
                    mode = "0"  # repeat all, no shuffle
                elif repeat == RepeatMode.ONE:
                    mode = "1"  # repeat one, no shuffle
                else:
                    mode = "5"  # no repeat, no shuffle (sequence)
            await self.coordinator.client.async_set_loopmode(mode)
            await self.coordinator.async_request_refresh()
        else:
            await self._master.async_set_shuffle(shuffle)

    async def async_set_repeat(self, repeat: str) -> None:
        """Change the repeat mode."""
        if not self._slave_mode:
            shuffle = self.coordinator.data.shuffle
            if repeat == RepeatMode.OFF:
                mode = "3" if shuffle else "5"  # shuffle-no-repeat or sequence
            elif repeat == RepeatMode.ALL:
                mode = "2" if shuffle else "0"  # shuffle+repeat-all or repeat-all
            elif repeat == RepeatMode.ONE:
                mode = "4" if shuffle else "1"  # shuffle+repeat-one or repeat-one
            else:
                mode = "0"
            await self.coordinator.client.async_set_loopmode(mode)
            await self.coordinator.async_request_refresh()
        else:
            await self._master.async_set_repeat(repeat)

    # ------------------------------------------------------------------
    # Play media (full complexity)
    # ------------------------------------------------------------------

    async def async_play_media(self, media_type, media_id, **kwargs) -> None:
        """Play media from a URL or local file."""
        _LOGGER.debug(
            "Trying to play media. Device: %s, Media_type: %s, Media_id: %s",
            self.entity_id, media_type, media_id,
        )
        if not self._slave_mode:
            if not (
                media_type in [MediaType.MUSIC, MediaType.URL, MediaType.TRACK]
                or media_source.is_media_source_id(media_id)
            ):
                _LOGGER.warning(
                    "For: %s Invalid media type %s. Only %s and %s is supported",
                    self.entity_id, media_type, MediaType.MUSIC, MediaType.URL,
                )
                await self.async_media_stop()
                return

            if not self._snapshot_active:
                self._playing_mediabrowser = False
                self._nometa = False

            if kwargs.get(ATTR_MEDIA_ANNOUNCE):
                _LOGGER.debug("For: %s, Announce parameter set, Media_id: %s", self.entity_id, media_id)
                self._announce = True
                await self.async_snapshot(False)
                self._playing_mediabrowser = False
                self._playing_mass = False
            else:
                self._playing_tts = False
                self._announce = False

            if media_source.is_media_source_id(media_id):
                play_item = await media_source.async_resolve_media(
                    self.hass, media_id, self.entity_id
                )
                if "radio_browser" in media_id:
                    self._playing_mediabrowser = False
                else:
                    self._playing_mediabrowser = True

                if "media_source/local" in media_id:
                    self._media_source_uri = media_id
                else:
                    self._media_source_uri = None

                media_id = play_item.url
                supported_mimes = [
                    "audio/basic", "audio/mpeg", "audio/mp3", "audio/mpeg3",
                    "audio/x-mpeg-3", "audio/x-mpegurl", "audio/mp4", "audio/aac",
                    "audio/x-aac", "audio/x-hx-aac-adts", "audio/x-aiff", "audio/ogg",
                    "audio/vorbis", "application/ogg", "audio/opus", "audio/webm",
                    "audio/wav", "audio/x-wav", "audio/vnd.wav", "audio/flac",
                    "audio/x-flac", "audio/x-ms-wma",
                ]
                if play_item.mime_type not in supported_mimes:
                    _LOGGER.warning(
                        "For: %s Invalid media type, %s is not supported",
                        self.entity_id, play_item.mime_type,
                    )
                    self._playing_mediabrowser = False
                    return

                media_id = async_process_play_media_url(self.hass, media_id)

            media_id_check = media_id.lower()

            if media_id_check.startswith("http"):
                media_type = MediaType.URL

            if "8095/media_player" in media_id_check:
                self._playing_mass = True
            else:
                self._playing_mass = False

            if media_id_check.endswith(".m3u") or media_id_check.endswith(".m3u8"):
                media_id = await self.async_parse_m3u_url(media_id)

            if media_id_check.endswith(".pls"):
                media_id = await self.async_parse_pls_url(media_id)

            media_id_final = media_id
            fw = self.coordinator.data.firmware

            if media_type == MediaType.URL:
                if not (self._playing_mediabrowser or self._playing_mass):
                    media_id_final = await self.async_detect_stream_url_redirection(media_id)

                if self._fwvercheck(fw) >= self._fwvercheck(FW_SLOW_STREAMS) and self._state == STATE_PLAYING:
                    await self.coordinator.client.async_pause()

                if self._playing_spotify:
                    await self.coordinator.client.async_select_source("wifi")

                await self.coordinator.client.async_play_media(media_id_final)

            elif media_type in [MediaType.MUSIC, MediaType.TRACK]:
                await self.coordinator.client._async_httpapi(
                    f"setPlayerCmd:playLocalList:{media_id}"
                )

            self._state = STATE_PLAYING
            self._media_title = None
            self._media_artist = None
            self._media_album = None
            self._icecast_name = None
            self._playhead_position = 0
            self._duration = 0
            self._trackc = None
            self._position_updated_at = utcnow()
            self._idletime_updated_at = self._position_updated_at
            self._media_image_url = None
            self._ice_skip_throt = True
            if media_type == MediaType.URL:
                self._media_uri = media_id
                self._media_uri_final = media_id_final
            elif media_type == MediaType.MUSIC:
                self._media_uri = None
                self._media_uri_final = None
            if self._announce:
                self.async_write_ha_state()
        else:
            if not self._snapshot_active:
                await self._master.async_play_media(media_type, media_id)

    # ------------------------------------------------------------------
    # Music Assistant event handling
    # ------------------------------------------------------------------

    def handle_event(self, event) -> None:
        """Retrieve events from Music Assistant through the event bus."""
        if self.entity_id == event.data.get("object_id"):
            if self._playing_mass:
                self.get_music_assistant_metadata(event)

    def get_music_assistant_metadata(self, event) -> None:
        """Parse Music Assistant event data for metadata."""
        if self._state in [STATE_PLAYING, STATE_PAUSED]:
            if event.data.get("type") == "queue_updated":
                current_item = event.data.get("data", {}).get("current_item", {})

                if current_item.get("media_type") == "radio":
                    self._playing_mass_radio = True
                    try:
                        self._media_title = current_item.get("name")
                    except (ValueError, KeyError):
                        self._media_title = None
                    try:
                        self._media_image_url = current_item.get("image")
                    except (ValueError, KeyError):
                        self._media_image_url = None
                    self._media_artist = None
                    self._duration = 0
                    self._playhead_position = 0
                else:
                    self._playing_mass_radio = False
                    media_item = current_item.get("media_item", {})
                    try:
                        self._media_title = media_item.get("name")
                        version = media_item.get("version", "")
                        if version:
                            self._media_title = f"{self._media_title} ({version})"
                    except (ValueError, KeyError):
                        try:
                            self._media_title = current_item.get("name")
                        except (ValueError, KeyError):
                            self._media_title = None

                    try:
                        artists = media_item.get("artists", [])
                        self._media_artist = " / ".join(a.get("name", "") for a in artists)
                    except (ValueError, KeyError):
                        try:
                            self._media_artist = (
                                media_item.get("album", {}).get("artist", {}).get("name")
                            )
                        except (ValueError, KeyError):
                            self._media_artist = None

                    try:
                        self._media_image_url = current_item.get("image")
                    except (ValueError, KeyError):
                        self._media_image_url = None

                    try:
                        self._duration = current_item.get("duration", 0)
                    except (ValueError, KeyError):
                        self._duration = 0

            elif event.data.get("type") == "queue_time_updated":
                if not self._playing_mass_radio:
                    try:
                        self._playhead_position = event.data.get("data")
                    except (ValueError, KeyError):
                        pass

    # ------------------------------------------------------------------
    # Metadata parsing helpers
    # ------------------------------------------------------------------

    def _parse_playerstatus_metadata(self, plr_stat: dict) -> bool:
        """Parse title/artist/album from player status hex-encoded fields."""
        try:
            if plr_stat.get("uri", "") != "":
                rootdir = ROOTDIR_USB
                try:
                    self._trackc = str(
                        bytearray.fromhex(plr_stat["uri"]).decode("utf-8")
                    ).replace(rootdir, "")
                except ValueError:
                    self._trackc = plr_stat["uri"].replace(rootdir, "")
        except KeyError:
            pass

        if plr_stat.get("Title", "") != "":
            try:
                title = str(bytearray.fromhex(plr_stat["Title"]).decode("utf-8"))
            except ValueError:
                title = plr_stat["Title"]
            if title.lower() != "unknown":
                self._media_title = string.capwords(title)
                if self._trackc is None:
                    self._trackc = self._media_title
            else:
                self._media_title = None

        if plr_stat.get("Artist", "") != "":
            try:
                artist = str(bytearray.fromhex(plr_stat["Artist"]).decode("utf-8"))
            except ValueError:
                artist = plr_stat["Artist"]
            if artist.lower() != "unknown":
                self._media_artist = string.capwords(artist)
            else:
                self._media_artist = None

        if plr_stat.get("Album", "") != "":
            try:
                album = str(bytearray.fromhex(plr_stat["Album"]).decode("utf-8"))
            except ValueError:
                album = plr_stat["Album"]
            if album.lower() != "unknown":
                self._media_album = string.capwords(album)
            else:
                self._media_album = None

        return self._media_title is not None and self._media_artist is not None

    def _parse_local_mediasource_metadata_from_path(self) -> bool:
        """Parse metadata from media source URI path."""
        if self._media_source_uri is not None:
            rootdir = "media-source://media_source/local/"
            self._trackc = self._media_source_uri.replace(rootdir, "")
            titleuri = self._trackc.split("/")
            if len(titleuri) > 1:
                titles = titleuri[-2:]
                self._media_artist = string.capwords(
                    titles[0].strip().strip("-").replace("_", " ")
                )
                self._media_title = string.capwords(
                    titles[1].strip().strip("-").replace("_", " ")
                )
            else:
                self._media_title = string.capwords(
                    titleuri[0].strip().strip("-").replace("_", " ")
                )
            querywords = self._media_title.split(".")
            resultwords = [w for w in querywords if w.lower() not in CUT_EXTENSIONS]
            self._media_title = " ".join(resultwords)
            return True
        return False

    def _is_playing_new_track(self) -> bool:
        """Check if track changed since last update."""
        if self._playing_mediabrowser and self._media_source_uri is not None:
            return False

        if self._icecast_name is not None:
            import unicodedata

            artmed = unicodedata.normalize(
                "NFKD", str(self._media_artist) + str(self._media_title)
            ).lower()
            artmedd = "".join(c for c in artmed if not unicodedata.combining(c))
            if (
                self._icecast_name.lower() in artmedd
                or (self._source and self._source.lower() in artmedd)
            ):
                self._media_image_url = None
                return False

        return (
            self._media_artist != self._media_prev_artist
            or self._media_title != self._media_prev_title
        )

    # ------------------------------------------------------------------
    # Icecast metadata
    # ------------------------------------------------------------------

    async def async_update_from_icecast(self) -> None:
        """Update track info from icecast stream."""
        if self._icecast_meta == "Off":
            return

        def _fetch_icecast():
            """Synchronous icecast fetch (runs in executor)."""
            ORIGINAL_HTTP_CLIENT_READ_STATUS = urllib.request.http.client.HTTPResponse._read_status

            def NiceToICY(self_resp):
                import io

                class InterceptedHTTPResponse:
                    pass

                line = self_resp.fp.readline().replace(b"ICY 200 OK\r\n", b"HTTP/1.0 200 OK\r\n")
                intercepted = InterceptedHTTPResponse()
                intercepted.fp = io.BufferedReader(io.BytesIO(line))
                intercepted.debuglevel = self_resp.debuglevel
                intercepted._close_conn = self_resp._close_conn
                return ORIGINAL_HTTP_CLIENT_READ_STATUS(intercepted)

            urllib.request.http.client.HTTPResponse._read_status = NiceToICY
            try:
                request = urllib.request.Request(
                    self._media_uri_final,
                    headers={"Icy-MetaData": "1", "User-Agent": "VLC/3.0.16 LibVLC/3.0.16"},
                )
                return urllib.request.urlopen(request)
            finally:
                urllib.request.http.client.HTTPResponse._read_status = ORIGINAL_HTTP_CLIENT_READ_STATUS

        try:
            response = await self.hass.async_add_executor_job(_fetch_icecast)
        except (urllib.error.URLError, OSError):
            _LOGGER.debug("For: %s Metadata error: %s", self.entity_id, self._media_uri_final)
            self._media_title = None
            self._media_artist = None
            self._icecast_name = None
            self._media_image_url = None
            return

        icy_name = response.headers.get("icy-name")
        if icy_name and icy_name not in ("no name", "Unspecified name", "-"):
            try:
                self._icecast_name = icy_name.encode("latin1").decode("utf-8")
            except UnicodeDecodeError:
                self._icecast_name = icy_name
        else:
            self._icecast_name = None

        if self._icecast_meta == "StationName":
            self._media_title = self._icecast_name
            self._media_artist = None
            self._media_image_url = None
            return

        icy_metaint_header = response.headers.get("icy-metaint")
        if icy_metaint_header is not None:
            metaint = int(icy_metaint_header)
            for _ in range(10):
                response.read(metaint)
                metadata_length = struct.unpack("B", response.read(1))[0] * 16
                metadata = response.read(metadata_length).rstrip(b"\0")
                m = re.search(rb"StreamTitle='(.*)';", metadata)
                if m:
                    title = m.group(0)
                    if title:
                        code_detect = chardet.detect(title)["encoding"]
                        title = title.decode(code_detect, errors="ignore")
                        titlek = title.split("';")
                        title = titlek[0]
                        titlem = title.split("='")
                        title = titlem[1]
                        title = re.sub(r"\[.*?\]\ *", "", title)
                        if "~~~~~" in title:
                            titles = title.split("~")
                            self._media_artist = string.capwords(titles[0].strip().strip("-"))
                            self._media_title = string.capwords(titles[1].strip().strip("-"))
                        elif " - " in title:
                            titles = title.split(" - ")
                            self._media_artist = string.capwords(titles[0].strip().strip("-"))
                            self._media_title = string.capwords(titles[1].strip().strip("-"))
                        else:
                            self._media_artist = (
                                f"[{self._icecast_name}]" if self._icecast_name else None
                            )
                            self._media_title = string.capwords(title)

                        if self._media_artist == "-":
                            self._media_artist = None
                        if self._media_title == "-":
                            self._media_title = None
                        if self._media_artist:
                            self._media_artist = self._media_artist.replace("/", " / ").replace("  ", " ")
                        if self._media_title:
                            self._media_title = self._media_title.replace("/", " / ").replace("  ", " ")
                        break
                else:
                    self._media_title = self._icecast_name if self._icecast_name else None
                    self._media_artist = None
                    self._media_image_url = None
        else:
            self._media_title = self._icecast_name if self._icecast_name else None
            self._media_artist = None
            self._media_image_url = None

    # ------------------------------------------------------------------
    # URL redirect detection & playlist parsing
    # ------------------------------------------------------------------

    async def async_detect_stream_url_redirection(self, uri: str) -> str:
        """Detect URL redirections."""
        if "tts_proxy" in uri or self._announce:
            return uri
        _LOGGER.debug("For: %s detect URI redirect-from: %s", self.entity_id, uri)
        try:
            check_uri = await self.hass.async_add_executor_job(
                self._detect_redirect_sync, uri
            )
        except (requests.RequestException, OSError, ValueError):
            check_uri = uri
        _LOGGER.debug("For: %s detect URI redirect - to: %s", self.entity_id, check_uri)
        return check_uri

    def _detect_redirect_sync(self, uri: str) -> str:
        """Synchronous redirect detection (runs in executor)."""
        redirect_detect = True
        check_uri = uri
        while redirect_detect:
            response_location = requests.head(
                check_uri,
                allow_redirects=False,
                headers={"User-Agent": "VLC/3.0.16 LibVLC/3.0.16"},
            )
            if (
                response_location.status_code in [301, 302, 303, 307, 308]
                and "Location" in response_location.headers
            ):
                check_uri = response_location.headers["Location"]
            else:
                redirect_detect = False
        return check_uri

    async def async_parse_m3u_url(self, playlist: str) -> str:
        """Parse an M3U playlist URL for actual streams, return the first one."""
        try:
            websession = async_get_clientsession(self.hass)
            async with async_timeout.timeout(10):
                response = await websession.get(playlist)
        except (asyncio.TimeoutError, aiohttp.ClientError):
            _LOGGER.warning("For: %s unable to get the M3U playlist: %s", self.entity_id, playlist)
            return playlist

        if response.status == HTTPStatus.OK:
            data = await response.text()
            lines = [line.strip("\n\r") for line in data.split("\n") if line.strip("\n\r")]
            if lines:
                urls = [u for u in lines if u.startswith("http")]
                if urls:
                    return urls[0]
                else:
                    _LOGGER.error("For: %s M3U playlist: %s No valid http URL!", self.entity_id, playlist)
                    self._nometa = True
            else:
                _LOGGER.error("For: %s M3U playlist: %s No content to parse!", self.entity_id, playlist)
        return playlist

    async def async_parse_pls_url(self, playlist: str) -> str:
        """Parse a PLS playlist URL for actual streams, return the first one."""
        try:
            websession = async_get_clientsession(self.hass)
            async with async_timeout.timeout(10):
                response = await websession.get(playlist)
        except (asyncio.TimeoutError, aiohttp.ClientError):
            _LOGGER.warning("For: %s unable to get the PLS playlist: %s", self.entity_id, playlist)
            return playlist

        if response.status == HTTPStatus.OK:
            data = await response.text()
            lines = [line.strip("\n\r") for line in data.split("\n") if line.strip("\n\r")]
            if lines:
                urls = [u for u in lines if u.startswith("File")]
                if urls:
                    url = urls[0].split("=")
                    if len(url) > 1:
                        return url[1]
                else:
                    _LOGGER.error("For: %s PLS playlist: %s No valid http URL!", self.entity_id, playlist)
                    self._nometa = True
            else:
                _LOGGER.error("For: %s PLS playlist: %s No content to parse!", self.entity_id, playlist)
        return playlist

    # ------------------------------------------------------------------
    # Firmware version comparison
    # ------------------------------------------------------------------

    def _fwvercheck(self, v: str) -> tuple:
        """Compare firmware version strings."""
        return tuple(point.zfill(8) for point in v.split("."))

    # ------------------------------------------------------------------
    # UPnP metadata fetch
    # ------------------------------------------------------------------

    async def async_update_via_upnp(self) -> None:
        """Update track info via UPnP."""
        import validators

        upnp_device = self.coordinator.upnp_device
        if upnp_device is None:
            return

        service = upnp_device.service("urn:schemas-upnp-org:service:AVTransport:1")

        try:
            media_info = await service.action("GetMediaInfo").async_call(InstanceID=0)
            self._trackc = media_info.get("CurrentURI")
            self._media_uri_final = media_info.get("TrackSource")
            media_metadata = media_info.get("CurrentURIMetaData")
        except Exception as err:
            _LOGGER.warning("GetMediaInfo/CurrentURIMetaData UPnP error: %s: %s", self.entity_id, err)
            return

        if media_metadata is None:
            return

        self._media_title = None
        self._media_album = None
        self._media_artist = None
        self._media_image_url = None

        xml_tree = ET.fromstring(media_metadata)
        xml_path = "{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item/"
        title_xml_path = "{http://purl.org/dc/elements/1.1/}title"
        artist_xml_path = "{urn:schemas-upnp-org:metadata-1-0/upnp/}artist"
        album_xml_path = "{urn:schemas-upnp-org:metadata-1-0/upnp/}album"
        image_xml_path = "{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI"

        title_el = xml_tree.find(f"{xml_path}{title_xml_path}")
        if title_el is not None:
            self._media_title = title_el.text
        artist_el = xml_tree.find(f"{xml_path}{artist_xml_path}")
        if artist_el is not None:
            self._media_artist = artist_el.text
        album_el = xml_tree.find(f"{xml_path}{album_xml_path}")
        if album_el is not None:
            self._media_album = album_el.text
        image_el = xml_tree.find(f"{xml_path}{image_xml_path}")
        if image_el is not None:
            self._media_image_url = image_el.text

        if not validators.url(self._media_image_url):
            self._media_image_url = None

    async def async_tracklist_via_upnp(self, media: str) -> None:
        """Retrieve tracks list queue via UPnP."""
        upnp_device = self.coordinator.upnp_device
        if upnp_device is None:
            return

        if media == "USB":
            queuename = "USBDiskQueue"
            rootdir = ROOTDIR_USB
        else:
            _LOGGER.debug(
                "Tracklist retrieval: %s, %s is not supported. Use 'USB'.",
                self.entity_id, media,
            )
            self._trackq = []
            return

        service = upnp_device.service("urn:schemas-wiimu-com:service:PlayQueue:1")

        try:
            media_info = await service.action("BrowseQueue").async_call(QueueName=queuename)
            media_metadata = media_info.get("QueueContext")
        except Exception as err:
            _LOGGER.debug("PlayQueue/QueueContext UPnP error: %s: %s", self.entity_id, err)
            return

        if media_metadata is None:
            return

        xml_tree = ET.fromstring(media_metadata)
        trackq = []
        for playlist in xml_tree:
            for tracks in playlist:
                for track in tracks:
                    if track.tag == "URL":
                        if rootdir in track.text:
                            trackq.append(track.text.replace(rootdir, ""))

        if len(trackq) > 0:
            self._trackq = trackq

    async def async_preset_snap_via_upnp(self, presetnum: str) -> None:
        """Save current playlist to a preset via UPnP."""
        upnp_device = self.coordinator.upnp_device
        if upnp_device is None or not self._playing_spotify:
            return

        service = upnp_device.service("urn:schemas-wiimu-com:service:PlayQueue:1")

        result = None
        try:
            media_info = await service.action("SetSpotifyPreset").async_call(
                KeyIndex=int(presetnum)
            )
            result = str(media_info.get("Result"))
        except Exception as err:
            _LOGGER.debug(
                "SetSpotifyPreset UPnP error for: %s, presetnum: %s, result: %s, err: %s",
                self.entity_id, presetnum, result, err,
            )
            return

        try:
            preset_map_info = await service.action("GetKeyMapping").async_call()
            preset_map = preset_map_info.get("QueueContext")
        except Exception as err:
            _LOGGER.debug("GetKeyMapping UPnP error: %s: %s", self.entity_id, err)
            return

        xml_tree = ET.fromstring(preset_map)

        if xml_tree.find("Key" + presetnum) is None:
            _LOGGER.error(
                "Preset Map error: %s num: %s. Please create a Spotify preset first.",
                self.entity_id, presetnum,
            )
            return

        import time

        tme = time.strftime("%Y-%m-%d %H:%M:%S")

        for tag, value in [
            ("Name", f"Snapshot set by Home Assistant ({result})_#~{tme}"),
            ("Source", "SPOTIFY"),
            ("PicUrl", "https://brands.home-assistant.io/_/media_player/icon.png"),
        ]:
            try:
                xml_tree.find(f"Key{presetnum}/{tag}").text = value
            except (AttributeError, ET.ParseError):
                data = xml_tree.find("Key" + presetnum)
                snap = ET.SubElement(data, tag)
                snap.text = value

        preset_map = ET.tostring(xml_tree, encoding="unicode")

        try:
            await service.action("SetKeyMapping").async_call(QueueContext=preset_map)
        except Exception as err:
            _LOGGER.debug("SetKeyMapping UPnP error: %s, err: %s", self.entity_id, err)

    # ------------------------------------------------------------------
    # Snapshot / Restore (TTS/Announce)
    # ------------------------------------------------------------------

    async def async_snapshot(self, switchinput: bool) -> None:
        """Snapshot the current input source and volume level."""
        if not self.available:
            return

        if not self._slave_mode:
            self._snapshot_active = True
            self._snap_source = self._source
            self._snap_state = self._state
            self._snap_nometa = self._nometa
            self._snap_playing_mediabrowser = self._playing_mediabrowser
            self._snap_media_source_uri = self._media_source_uri
            self._snap_playhead_position = self._playhead_position

            if self._playing_localfile or self._playing_spotify or self._playing_webplaylist:
                if self._state in [STATE_PLAYING, STATE_PAUSED]:
                    self._snap_seek = True
            elif self._playing_stream or self._playing_mediabrowser:
                if self._state in [STATE_PLAYING, STATE_PAUSED] and self._playing_mediabrowser:
                    self._snap_seek = True

            if self._source == "Network":
                self._snap_uri = self._media_uri_final

            current_vol = int(self.coordinator.data.volume * MAX_VOL)

            if self._playing_spotify:
                if not switchinput:
                    preset_key = self.coordinator.data.preset_key
                    await self.async_preset_snap_via_upnp(str(preset_key))
                    await self.coordinator.client.async_stop()
                else:
                    self._snap_spotify_volumeonly = True
                self._snap_spotify = True
                self._snap_volume = current_vol
                return

            elif self._playing_mass:
                await self.hass.services.async_call(
                    "mass", "queue_command",
                    service_data={"entity_id": self.entity_id, "command": "snapshot_create"},
                )
                self._snap_mass = True
                self._snap_volume = current_vol

            elif self._state == STATE_IDLE:
                self._snap_volume = current_vol

            elif switchinput and not self._playing_stream:
                await self.coordinator.client.async_select_source("wifi")
                await asyncio.sleep(0.2)
                await self.coordinator.client.async_stop()
                await asyncio.sleep(2)
                # Re-read volume after source switch
                try:
                    player_status = await self.coordinator.client.async_get_player_status()
                    self._snap_volume = int(player_status.get("vol", 0))
                except Exception:
                    self._snap_volume = 0
            else:
                self._snap_volume = current_vol
                fw = self.coordinator.data.firmware
                if self._playing_stream:
                    if self._fwvercheck(fw) >= self._fwvercheck(FW_SLOW_STREAMS):
                        await self.coordinator.client.async_pause()
                    else:
                        await self.coordinator.client.async_stop()

    async def async_restore(self) -> None:
        """Restore the input source and volume level from snapshot."""
        if not self.available:
            return

        if not self._slave_mode:
            _LOGGER.debug(
                "For %s RESTORE, volume: %s, source: %s, uri: %s, seek: %s, pos: %s",
                self.entity_id, self._snap_volume, self._snap_source,
                self._snap_uri, self._snap_seek, self._snap_playhead_position,
            )

            if self._snap_state != STATE_UNKNOWN:
                self._state = self._snap_state

            self._playing_tts = False
            self._announce = False
            self._playhead_position = self._snap_playhead_position

            if self._snap_spotify:
                self._snap_spotify = False
                if not self._snap_spotify_volumeonly:
                    preset_key = self.coordinator.data.preset_key
                    await self.coordinator.client.async_recall_preset(preset_key)
                self._snapshot_active = False
                self._snap_spotify_volumeonly = False

            elif self._snap_mass:
                self._snap_mass = False
                self._snapshot_active = False
                await self.hass.services.async_call(
                    "mass", "queue_command",
                    service_data={"entity_id": self.entity_id, "command": "snapshot_restore"},
                )

            elif self._snap_source != "Network":
                self._snapshot_active = False
                await self.async_select_source(self._snap_source)
                if self._snap_uri is None:
                    await asyncio.sleep(0.6)
                self._snap_source = None

            elif self._snap_uri is not None:
                self._playing_mediabrowser = self._snap_playing_mediabrowser
                self._media_source_uri = self._snap_media_source_uri
                self._media_uri = self._snap_uri
                self._nometa = self._snap_nometa
                if self._snap_state in [STATE_PLAYING, STATE_PAUSED]:
                    await self.async_play_media(MediaType.URL, self._media_uri)
                self._snapshot_active = False
                self._snap_uri = None

            if self._snap_volume != 0:
                await self.coordinator.client.async_set_volume(self._snap_volume)
                self._snap_volume = 0

            if self._snap_state in [STATE_PLAYING, STATE_PAUSED]:
                await asyncio.sleep(0.5)
                if self._snap_seek and self._snap_playhead_position > 0:
                    await self.coordinator.client.async_seek(self._snap_playhead_position)
                    if self._snap_state == STATE_PAUSED:
                        await self.async_media_pause()

            self._snap_state = STATE_UNKNOWN
            self._snap_seek = False
            self._snap_playhead_position = 0

    # ------------------------------------------------------------------
    # Play track by name
    # ------------------------------------------------------------------

    async def async_play_track(self, track) -> None:
        """Play media track by name found in the tracks list."""
        if not len(self._trackq) > 0 or track is None:
            return

        track.hass = self.hass
        trackn = track.async_render()

        if not self._slave_mode:
            try:
                index = [idx for idx, s in enumerate(self._trackq) if trackn in s][0]
            except IndexError:
                return

            if not index > 0:
                return

            await self.coordinator.client._async_httpapi(
                f"setPlayerCmd:playLocalList:{index}"
            )
            self._state = STATE_PLAYING
            self._playing_tts = False
            self._media_title = None
            self._media_artist = None
            self._media_album = None
            self._trackc = None
            self._icecast_name = None
            self._playhead_position = 0
            self._duration = 0
            self._position_updated_at = utcnow()
            self._media_image_url = None
            self._media_uri = None
            self._media_uri_final = None
            self._ice_skip_throt = False
        else:
            await self._master.async_play_track(track)

    # ------------------------------------------------------------------
    # Multiroom
    # ------------------------------------------------------------------

    async def async_join_players(self, group_members: list[str]) -> None:
        """Join group_members as a player group with the current player (standard HA)."""
        entities = self.hass.data[DOMAIN]["entities"]
        entities = [e for e in entities if e.entity_id in group_members]
        await self.async_join(entities)

    async def async_join(self, slaves) -> None:
        """Add selected slaves to multiroom configuration."""
        _LOGGER.debug("Multiroom JOIN request: Master: %s, Slaves: %s", self.entity_id, slaves)
        if not self.available:
            return

        if self.entity_id not in self._multiroom_group:
            self._multiroom_group.append(self.entity_id)
            self._is_master = True

        for slave in slaves:
            if slave._is_master:
                await slave.async_unjoin_all()

            if slave.entity_id not in self._multiroom_group:
                if slave._slave_mode:
                    await slave.async_unjoin_me()

                await slave.async_set_previous_source(True)
                if self._multiroom_wifidirect:
                    cmd = (
                        f"ConnectMasterAp:ssid={self._ssid}:ch={self._wifi_channel}"
                        ":auth=OPEN:encry=NONE:pwd=:chext=0"
                    )
                    await slave.coordinator.client._async_httpapi(cmd)
                else:
                    await self.coordinator.client.async_multiroom_join(slave.host)

                await slave.async_set_master(self)
                await slave.async_set_is_master(False)
                await slave.async_set_slave_mode(True)
                await slave.async_set_media_title(self._media_title)
                await slave.async_set_media_artist(self._media_artist)
                await slave.async_set_state(self.state)
                await slave.async_set_slave_ip(self.host)
                await slave.async_set_media_image_url(self._media_image_url)
                await slave.async_set_playhead_position(self.media_position)
                await slave.async_set_duration(self.media_duration)
                await slave.async_set_source(self._source)
                await slave.async_set_sound_mode(self.coordinator.data.eq_mode)
                await slave.async_set_features(self._features)
                self._multiroom_group.append(slave.entity_id)

        for slave in slaves:
            if slave.entity_id in self._multiroom_group:
                await slave.async_set_multiroom_group(self._multiroom_group)

        self._position_updated_at = utcnow()

    async def async_unjoin_all(self) -> None:
        """Disconnect everybody from the multiroom group (master action)."""
        if not self.available:
            return

        await self.coordinator.client.async_multiroom_unjoin()
        self._is_master = False
        for slave_id in self._multiroom_group:
            for device in self.hass.data[DOMAIN]["entities"]:
                if device.entity_id == slave_id and device.entity_id != self.entity_id:
                    await device.async_set_slave_mode(False)
                    await device.async_set_is_master(False)
                    await device.async_set_slave_ip(None)
                    await device.async_set_master(None)
                    await device.async_set_multiroom_unjoinat(utcnow())
                    await device.async_set_multiroom_group([])
        self._multiroom_group = []
        self._position_updated_at = utcnow()

    async def async_unjoin_player(self) -> None:
        """Remove this player from any group (standard HA)."""
        if self._is_master:
            await self.async_unjoin_all()
        if self._slave_mode:
            await self.async_unjoin_me()

    async def async_unjoin_me(self) -> None:
        """Disconnect myself from the multiroom configuration."""
        value = None
        if self._multiroom_wifidirect:
            if self._master is not None:
                await self._master.coordinator.client.async_multiroom_kick_slave(self._slave_ip)
                self._master._position_updated_at = utcnow()
                value = "OK"
        else:
            await self.coordinator.client.async_multiroom_unjoin()
            value = "OK"

        if value == "OK":
            if self._master is not None:
                await self._master.async_remove_from_group(self)
            self._multiroom_unjoinat = utcnow()
            self._master = None
            self._is_master = False
            self._slave_mode = False
            self._slave_ip = None
            self._multiroom_group = []
        else:
            _LOGGER.warning("Failed to unjoin_me from multiroom. Device: %s", self.entity_id)

    async def async_remove_from_group(self, device) -> None:
        """Remove a certain device from multiroom lists."""
        if device.entity_id in self._multiroom_group:
            self._multiroom_group.remove(device.entity_id)

        if len(self._multiroom_group) <= 1:
            self._multiroom_group = []
            self._is_master = False
            self._slave_list = None

        for member in self._multiroom_group:
            for player in self.hass.data[DOMAIN]["entities"]:
                if player.entity_id == member and player.entity_id != self.entity_id:
                    await player.async_set_multiroom_group(self._multiroom_group)

    # ------------------------------------------------------------------
    # Multiroom property setters (called by master on slaves)
    # ------------------------------------------------------------------

    async def async_set_multiroom_group(self, multiroom_group):
        self._multiroom_group = multiroom_group

    async def async_set_master(self, master):
        self._master = master

    async def async_set_is_master(self, is_master):
        self._is_master = is_master

    async def async_set_multiroom_unjoinat(self, tme):
        self._multiroom_unjoinat = tme

    async def async_set_slave_mode(self, slave_mode):
        self._slave_mode = slave_mode

    async def async_set_previous_source(self, srcbool):
        if srcbool:
            self._multiroom_prevsrc = self._source
        else:
            self._multiroom_prevsrc = None

    async def async_set_media_title(self, title):
        self._media_title = title

    async def async_set_media_artist(self, artist):
        self._media_artist = artist

    async def async_set_state(self, state):
        self._state = state

    async def async_set_slave_ip(self, slave_ip):
        self._slave_ip = slave_ip

    async def async_set_playhead_position(self, position):
        self._playhead_position = position

    async def async_set_duration(self, duration):
        self._duration = duration

    async def async_set_position_updated_at(self, time):
        self._position_updated_at = time

    async def async_set_source(self, source):
        self._source = source

    async def async_set_sound_mode(self, mode):
        pass  # EQ mode now read from coordinator

    async def async_set_media_image_url(self, url):
        self._media_image_url = url

    async def async_set_features(self, features):
        self._features = features

    # ------------------------------------------------------------------
    # Media browsing
    # ------------------------------------------------------------------

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        """Implement the websocket media browsing helper."""
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )
