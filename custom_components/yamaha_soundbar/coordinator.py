"""DataUpdateCoordinator for Yamaha Soundbar."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from async_upnp_client.aiohttp import AiohttpRequester
from async_upnp_client.client_factory import UpnpFactory

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.media_player.const import RepeatMode
from homeassistant.const import STATE_IDLE, STATE_PAUSED, STATE_PLAYING, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.dt import utcnow

from .client import YamahaClient, YamahaCannotConnect
from .const import (
    DOMAIN,
    MAX_VOL,
    SCAN_INTERVAL,
    SOUND_MODES,
    SOURCES_DEFAULT,
    SOURCES_LIVEIN,
    SOURCES_LOCALF,
    SOURCES_MAP,
    SOURCES_STREAM,
    UPNP_RETRY_INTERVAL,
    UPNP_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class YamahaData:
    """Parsed device state from all three API calls."""

    # Device info
    name: str = ""
    uuid: str = ""
    firmware: str = "1.0.0"
    mcu_ver: str = ""
    preset_key: int = 4

    # Playback state
    state: str = STATE_IDLE
    volume: float = 0.0
    muted: bool = False
    source: str | None = None
    source_list: dict[str, str] = field(default_factory=dict)

    # Media metadata
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    image_url: str | None = None
    duration: int | None = None
    position: int | None = None
    shuffle: bool = False
    repeat: str = RepeatMode.OFF

    # EQ mode (from getPlayerStatus "eq" field)
    eq_mode: str = "Normal"

    # Yamaha sound settings (from YAMAHA_DATA_GET)
    sound_program: str = ""
    subwoofer_volume: int = 0
    surround: bool = False
    clear_voice: bool = False
    bass_extension: bool = False

    # LED state (tracked locally — no read-back)
    led: bool = True

    # Multiroom
    group_members: list[str] = field(default_factory=list)
    is_master: bool = False
    slave: bool = False
    slave_ip: str | None = None

    # Internal
    playing_mode: str = "0"
    preset_number: int | None = None
    wifi_channel: int | None = None

    # Raw responses for media_player complex logic
    raw_player_status: dict = field(default_factory=dict)
    raw_device_status: dict = field(default_factory=dict)


class YamahaCoordinator(DataUpdateCoordinator[YamahaData]):
    """Coordinator to poll a Yamaha Linkplay device."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: YamahaClient,
        config_entry: ConfigEntry,
        source_mapping: dict[str, str] | None = None,
        source_ignore: list[str] | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            config_entry=config_entry,
        )
        self.client = client
        self._source_mapping = source_mapping or SOURCES_DEFAULT.copy()
        self._source_ignore = source_ignore or []
        self._upnp_device = None
        self._upnp_last_attempt: float | None = None
        self._first_update = True
        self._led_state: bool = True  # Assume on until told otherwise

        # UPnP factory
        requester = AiohttpRequester(UPNP_TIMEOUT)
        self._upnp_factory = UpnpFactory(requester)

    @property
    def upnp_device(self):
        """Expose UPnP device for media player use."""
        return self._upnp_device

    def set_led_state(self, state: bool) -> None:
        """Update locally tracked LED state (no device read-back available)."""
        self._led_state = state

    async def _async_update_data(self) -> YamahaData:
        """Fetch data from the device."""
        try:
            device_status = await self.client.async_get_device_status()
        except YamahaCannotConnect as err:
            raise UpdateFailed(f"Cannot connect to {self.client.host}") from err

        try:
            player_status = await self.client.async_get_player_status()
        except YamahaCannotConnect:
            player_status = {}

        try:
            sound_settings = await self.client.async_get_sound_settings()
        except YamahaCannotConnect:
            sound_settings = {}

        # Parse device status
        uuid = device_status.get("uuid", "")
        name = device_status.get("DeviceName", "")
        firmware = device_status.get("firmware", "1.0.0")
        mcu_ver = device_status.get("mcu_ver", "")
        wifi_channel = device_status.get("WifiChannel")
        preset_key = int(device_status.get("preset_key", 4))

        # Parse player status
        mode = str(player_status.get("mode", "0"))
        volume_raw = int(player_status.get("vol", "0"))
        volume = volume_raw / MAX_VOL if MAX_VOL > 0 else 0.0
        muted = bool(int(player_status.get("mute", "0")))
        eq_raw = player_status.get("eq", "0")
        eq_mode = SOUND_MODES.get(str(eq_raw), "Normal")

        # State
        status = str(player_status.get("status", "stop"))
        if status == "play":
            state = STATE_PLAYING
        elif status == "pause":
            state = STATE_PAUSED
        elif status in ("stop", "none"):
            state = STATE_IDLE
        else:
            state = STATE_UNKNOWN

        # Shuffle / repeat from loop mode
        # Linkplay loop modes: 0=repeat all, 1=repeat one, 2=shuffle+repeat all,
        # 3=shuffle, 4=repeat one+shuffle, 5=repeat one no shuffle
        loop = str(player_status.get("loop", "0"))
        shuffle = loop in ("2", "3", "5")
        repeat_map = {"0": RepeatMode.ALL, "1": RepeatMode.ONE, "2": RepeatMode.ALL, "5": RepeatMode.ONE}
        repeat = repeat_map.get(loop, RepeatMode.OFF)

        # Source detection
        source = SOURCES_MAP.get(mode, "Network")

        # Source list (filtered)
        source_list = {k: v for k, v in self._source_mapping.items() if k not in self._source_ignore}
        if "wifi" in source_list:
            del source_list["wifi"]

        # Media metadata from player status
        title = player_status.get("Title")
        artist = player_status.get("Artist")
        album = player_status.get("Album")

        # Duration and position
        try:
            duration = int(player_status.get("totlen", 0)) // 1000
        except (ValueError, TypeError):
            duration = 0
        try:
            position = int(player_status.get("curpos", 0)) // 1000
        except (ValueError, TypeError):
            position = 0

        # Multiroom
        is_master = False
        slave_mode = False
        slave_ip = None
        group_members = []
        if player_status.get("type") == "1":
            slave_mode = True
            slave_ip = player_status.get("slave_ip")
        # TODO: Parse multiroom group members from device status

        # Sound settings
        sound_program = sound_settings.get("sound program", "")
        try:
            subwoofer_volume = int(sound_settings.get("subwoofer volume", 0))
        except (ValueError, TypeError):
            subwoofer_volume = 0
        surround = str(sound_settings.get("3D surround", "0")) == "1"
        clear_voice = str(sound_settings.get("clear voice", "0")) == "1"
        bass_extension = str(sound_settings.get("bass extension", "0")) == "1"

        # UPnP device setup (first update or retry)
        if self._upnp_device is None:
            should_retry = (
                self._upnp_last_attempt is None
                or utcnow().timestamp() >= self._upnp_last_attempt + UPNP_RETRY_INTERVAL.total_seconds()
            )
            if should_retry:
                url = f"http://{self.client.host}:49152/description.xml"
                try:
                    self._upnp_device = await self._upnp_factory.async_create_device(url)
                    self._upnp_last_attempt = None
                except Exception as err:
                    self._upnp_last_attempt = utcnow().timestamp()
                    _LOGGER.warning("Failed UPnP setup for '%s': %s", self.client.host, err)

        self._first_update = False

        return YamahaData(
            name=name,
            uuid=uuid,
            firmware=firmware,
            mcu_ver=mcu_ver,
            preset_key=preset_key,
            state=state,
            volume=volume,
            muted=muted,
            source=source,
            source_list=source_list,
            title=title,
            artist=artist,
            album=album,
            image_url=None,
            duration=duration,
            position=position,
            shuffle=shuffle,
            repeat=repeat,
            eq_mode=eq_mode,
            sound_program=sound_program,
            subwoofer_volume=subwoofer_volume,
            surround=surround,
            clear_voice=clear_voice,
            bass_extension=bass_extension,
            led=self._led_state,
            group_members=group_members,
            is_master=is_master,
            slave=slave_mode,
            slave_ip=slave_ip,
            playing_mode=mode,
            preset_number=None,
            wifi_channel=wifi_channel,
            raw_player_status=player_status,
            raw_device_status=device_status,
        )
