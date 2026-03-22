# Yamaha Soundbar Integration Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the yamaha_soundbar integration from a monolithic YAML-configured media player into a modern HA integration with config flow, coordinator, extracted API client, and dedicated entities.

**Architecture:** Extract communication into `client.py`, centralize polling via `coordinator.py` with `DataUpdateCoordinator`, add `config_flow.py` for UI setup, and create dedicated entity platforms (select, number, switch, sensor) for soundbar controls. The media player entity is slimmed down to read from the coordinator.

**Tech Stack:** Home Assistant Core APIs, aiohttp, async-upnp-client, Python dataclasses

**Spec:** `docs/superpowers/specs/2026-03-22-integration-redesign-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `custom_components/yamaha_soundbar/const.py` | Create | DOMAIN, defaults, enums, source maps, platform list |
| `custom_components/yamaha_soundbar/client.py` | Create | YamahaClient — all HTTP/TCP/UPnP communication |
| `custom_components/yamaha_soundbar/coordinator.py` | Create | YamahaCoordinator + YamahaData dataclass |
| `custom_components/yamaha_soundbar/entity.py` | Create | YamahaSoundbarEntity base class |
| `custom_components/yamaha_soundbar/config_flow.py` | Create | Config flow + options flow |
| `custom_components/yamaha_soundbar/strings.json` | Create | UI text for flows and entity translations |
| `custom_components/yamaha_soundbar/select.py` | Create | Sound program + preset select entities |
| `custom_components/yamaha_soundbar/number.py` | Create | Subwoofer volume entity |
| `custom_components/yamaha_soundbar/switch.py` | Create | Surround, clear voice, bass extension, LED switches |
| `custom_components/yamaha_soundbar/sensor.py` | Create | WiFi channel diagnostic sensor |
| `custom_components/yamaha_soundbar/__init__.py` | Rewrite | Config entry setup/unload, retained services |
| `custom_components/yamaha_soundbar/media_player.py` | Rewrite | Slimmed entity reading from coordinator |
| `custom_components/yamaha_soundbar/manifest.json` | Modify | config_flow: true, version bump |
| `custom_components/yamaha_soundbar/services.yaml` | Modify | Remove sound_settings, command, preset |

---

### Task 1: Constants Module (`const.py`)

Extract all constants, maps, and enums from media_player.py into a shared constants file.

**Files:**
- Create: `custom_components/yamaha_soundbar/const.py`

- [ ] **Step 1: Create const.py with all constants**

```python
"""Constants for the Yamaha Soundbar integration."""
from datetime import timedelta

DOMAIN = "yamaha_soundbar"

PLATFORMS = ["media_player", "select", "number", "switch", "sensor"]

# Config keys
CONF_UUID = "uuid"
CONF_SOURCES = "sources"
CONF_COMMONSOURCES = "common_sources"
CONF_SOURCE_IGNORE = "source_ignore"
CONF_ICECAST_METADATA = "icecast_metadata"
CONF_VOLUME_STEP = "volume_step"
CONF_LEDOFF = "led_off"
CONF_ANNOUNCE_VOLUME_INCREASE = "announce_volume_increase"
CONF_CERT_FILENAME = "client.pem"

# Defaults
DEFAULT_ICECAST_UPDATE = "StationName"
DEFAULT_LEDOFF = False
DEFAULT_VOLUME_STEP = 5
DEFAULT_ANNOUNCE_VOLUME_INCREASE = 15

# Icons
ICON_DEFAULT = "mdi:soundbar"
ICON_PLAYING = "mdi:speaker-wireless"
ICON_MUTED = "mdi:speaker-off"
ICON_MULTIROOM = "mdi:speaker-multiple"
ICON_BLUETOOTH = "mdi:speaker-bluetooth"
ICON_PUSHSTREAM = "mdi:cast-audio"
ICON_TTS = "mdi:text-to-speech"

# Timing
MAX_VOL = 100
TCPPORT = 8899
UPNP_TIMEOUT = 5
API_TIMEOUT = 5
SCAN_INTERVAL = timedelta(seconds=10)
ICE_THROTTLE = timedelta(seconds=45)
UNA_THROTTLE = timedelta(seconds=20)
MROOM_UJWDIR = timedelta(seconds=20)
MROOM_UJWROU = timedelta(seconds=3)
SPOTIFY_PAUSED_TIMEOUT = timedelta(seconds=300)
AUTOIDLE_STATE_TIMEOUT = timedelta(seconds=2)
UPNP_RETRY_INTERVAL = timedelta(seconds=60)
PARALLEL_UPDATES = 1

# Firmware version thresholds
FW_MROOM_RTR_MIN = "4.2.8020"
FW_RAKOIT_UART_MIN = "4.2.9326"
FW_SLOW_STREAMS = "4.6"
UUID_ARYLIC = "FF31F09E"
ROOTDIR_USB = "/media/sda1/"

# Audio file extensions
CUT_EXTENSIONS = [
    "mp3", "mp2", "m2a", "mpg", "wav", "aac", "flac",
    "flc", "m4a", "ape", "wma", "ac3", "ogg",
]

# EQ modes (from getPlayerStatus "eq" field)
SOUND_MODES = {"0": "Normal", "1": "Classic", "2": "Pop", "3": "Jazz", "4": "Vocal"}

# Default source mapping
SOURCES_DEFAULT = {"bluetooth": "Bluetooth", "optical": "Optical", "HDMI": "HDMI"}

# Source mode code to name mapping
SOURCES_MAP = {
    "-1": "Idle", "0": "Idle", "1": "Airplay", "2": "DLNA", "3": "QPlay",
    "10": "Network", "11": "udisk", "16": "TFcard", "20": "API", "21": "udisk",
    "30": "Alarm", "31": "Spotify", "40": "line-in", "41": "bluetooth",
    "43": "optical", "44": "RCA", "45": "co-axial", "46": "FM", "47": "line-in2",
    "48": "XLR", "49": "HDMI", "50": "cd", "51": "Soundcard", "52": "TFcard",
    "60": "Talk", "99": "Idle",
}

# Source categories
SOURCES_LIVEIN = ["-1", "0", "40", "41", "43", "44", "45", "46", "47", "48", "49", "50", "51", "99"]
SOURCES_STREAM = ["1", "2", "3", "10", "30"]
SOURCES_LOCALF = ["11", "16", "20", "21", "52", "60"]

# Service names (retained)
SERVICE_JOIN = "join"
SERVICE_UNJOIN = "unjoin"
SERVICE_SNAP = "snapshot"
SERVICE_REST = "restore"
SERVICE_PLAY = "play_track"

# Service attributes
ATTR_MASTER = "master"
ATTR_SNAP = "switchinput"
ATTR_TRACK = "track"
```

- [ ] **Step 2: Verify the file is syntactically valid**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/const.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/yamaha_soundbar/const.py
git commit -m "feat: extract constants into const.py"
```

---

### Task 2: API Client (`client.py`)

Extract all HTTP, TCP/UART, and UPnP communication from media_player.py into a standalone client class.

**Files:**
- Create: `custom_components/yamaha_soundbar/client.py`
- Reference: `custom_components/yamaha_soundbar/media_player.py:423-492` (httpapi + tcpuart methods)
- Reference: `custom_components/yamaha_soundbar/media_player.py:2648-2687` (YAMAHA_DATA_SET/GET)

- [ ] **Step 1: Create client.py with YamahaClient class**

The client wraps three communication protocols. Extract these methods from media_player.py:

- `async_call_yamaha_httpapi` (line 423) → `_async_httpapi`
- `_call_yamaha_tcpuart_sync` (line 473) → `_tcpuart_sync`
- `async_call_yamaha_tcpuart` (line 460) → kept in coordinator (needs executor)

Build these public methods on top:

```python
"""API client for Yamaha Linkplay A118 based devices."""
import asyncio
import logging
import socket
import ssl
from http import HTTPStatus

import aiohttp
import async_timeout

from .const import API_TIMEOUT, MAX_VOL, TCPPORT

_LOGGER = logging.getLogger(__name__)


class YamahaClientError(Exception):
    """Base exception for YamahaClient."""


class YamahaCannotConnect(YamahaClientError):
    """Unable to connect to device."""


class YamahaClient:
    """Communicate with a Yamaha Linkplay device via HTTP, TCP/UART, and UPnP."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        ssl_context: ssl.SSLContext,
    ) -> None:
        self._host = host
        self._session = session
        self._ssl_ctx = ssl_context

    @property
    def host(self) -> str:
        return self._host

    # --- Low-level communication ---

    async def _async_httpapi(self, command: str, timeout: int = API_TIMEOUT) -> str | dict | None:
        """Send command via HTTPS API. Returns text or parsed JSON depending on command."""
        url = f"https://{self._host}/httpapi.asp?command={command}"
        try:
            async with async_timeout.timeout(timeout):
                response = await self._session.get(url, ssl=self._ssl_ctx)
        except (asyncio.TimeoutError, aiohttp.ClientError) as error:
            _LOGGER.warning(
                "Failed communicating with Yamaha '%s': %s", self._host, type(error)
            )
            raise YamahaCannotConnect(f"Cannot connect to {self._host}") from error

        if response.status != HTTPStatus.OK:
            _LOGGER.error(
                "Yamaha API call failed for %s, status: %s", self._host, response.status
            )
            raise YamahaCannotConnect(f"HTTP {response.status} from {self._host}")

        # Commands that return JSON
        json_commands = {"getStatusEx", "getPlayerStatus", "YAMAHA_DATA_GET"}
        if command in json_commands:
            return await response.json(content_type=None)
        return await response.text()

    def _tcpuart_sync(self, cmd: str) -> str:
        """Synchronous TCP UART communication. Caller must wrap in executor."""
        lenc = format(len(cmd), "02x")
        hed1 = "18 96 18 20 "
        hed2 = " 00 00 00 c1 02 00 00 00 00 00 00 00 00 00 00 "
        cmhx = " ".join(hex(ord(c))[2:] for c in cmd)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(API_TIMEOUT)
            s.connect((self._host, TCPPORT))
            s.send(bytes.fromhex(hed1 + lenc + hed2 + cmhx))
            data = str(repr(s.recv(1024))).encode().decode("unicode-escape")

        pos = data.find("AXX")
        if pos == -1:
            pos = data.find("MCU")
        return data[pos : len(data) - 2]

    # --- Status/Query ---

    async def async_get_device_status(self) -> dict:
        """Call getStatusEx — device info, wifi, uuid, firmware, preset_key."""
        result = await self._async_httpapi("getStatusEx")
        if not isinstance(result, dict):
            raise YamahaCannotConnect("Invalid getStatusEx response")
        return result

    async def async_get_player_status(self) -> dict:
        """Call getPlayerStatus — playback state, volume, eq, metadata."""
        result = await self._async_httpapi("getPlayerStatus")
        if not isinstance(result, dict):
            raise YamahaCannotConnect("Invalid getPlayerStatus response")
        return result

    async def async_get_sound_settings(self) -> dict:
        """Call YAMAHA_DATA_GET — sound program, subwoofer, surround, etc."""
        result = await self._async_httpapi("YAMAHA_DATA_GET")
        if not isinstance(result, dict):
            raise YamahaCannotConnect("Invalid YAMAHA_DATA_GET response")
        return result

    # --- Playback Control ---

    async def async_play(self) -> None:
        await self._async_httpapi("setPlayerCmd:resume")

    async def async_pause(self) -> None:
        await self._async_httpapi("setPlayerCmd:pause")

    async def async_stop(self) -> None:
        await self._async_httpapi("setPlayerCmd:stop")

    async def async_next(self) -> None:
        await self._async_httpapi("setPlayerCmd:next")

    async def async_previous(self) -> None:
        await self._async_httpapi("setPlayerCmd:prev")

    async def async_seek(self, position: int) -> None:
        await self._async_httpapi(f"setPlayerCmd:seek:{position}")

    async def async_set_volume(self, level: int) -> None:
        """Set volume level (0-100)."""
        level = max(0, min(MAX_VOL, level))
        await self._async_httpapi(f"setPlayerCmd:vol:{level}")

    async def async_mute(self, mute: bool) -> None:
        await self._async_httpapi(f"setPlayerCmd:mute:{'1' if mute else '0'}")

    async def async_select_source(self, source: str) -> None:
        await self._async_httpapi(f"setPlayerCmd:switchmode:{source}")

    async def async_play_media(self, url: str) -> None:
        await self._async_httpapi(f"setPlayerCmd:play:{url}")

    async def async_set_loopmode(self, mode: str) -> None:
        """Set loop mode directly (0-5). Shuffle and repeat are interleaved in Linkplay.

        Loop modes: 0=repeat all no shuffle, 1=repeat one, 2=shuffle+repeat all,
        3=shuffle no repeat, 4=repeat one+shuffle, 5=repeat one no shuffle

        The media player entity handles the shuffle/repeat → loopmode mapping
        because it needs to consider the current state of both settings.
        """
        await self._async_httpapi(f"setPlayerCmd:loopmode:{mode}")

    # --- EQ Mode (media player sound_mode) ---

    async def async_set_eq_mode(self, mode: int) -> None:
        """Set equalizer mode (0-4). Used by media player select_sound_mode."""
        await self._async_httpapi(f"setPlayerCmd:equalizer:{mode}")

    # --- Yamaha Sound Settings (via YAMAHA_DATA_SET) ---

    async def _async_yamaha_data_set(self, key: str, value: str) -> None:
        """Set a single Yamaha data field with retry-until-confirmed loop.

        The device sometimes doesn't apply settings on first try, so we
        retry up to 10 times with incremental backoff, verifying via
        YAMAHA_DATA_GET after each attempt.
        """
        encoded_key = key.replace(" ", "%20")
        encoded_value = value.replace(" ", "%20")
        sentence = f"%22{encoded_key}%22:%22{encoded_value}%22"
        cmd = f"YAMAHA_DATA_SET:{{{sentence}}}"

        for tentative in range(10):
            await self._async_httpapi("YAMAHA_DATA_GET")  # prime
            await self._async_httpapi(cmd)
            await asyncio.sleep(0.1 * tentative)
            status = await self._async_httpapi("YAMAHA_DATA_GET")
            if isinstance(status, dict) and status.get(key) == value:
                return
            _LOGGER.debug(
                "Tentative %d to set '%s: %s' failed, value is %s",
                tentative, key, value, status.get(key) if isinstance(status, dict) else status,
            )
        _LOGGER.warning("Failed to confirm '%s: %s' after 10 attempts", key, value)

    async def async_set_sound_program(self, program: str) -> None:
        await self._async_yamaha_data_set("sound program", program)

    async def async_set_subwoofer_volume(self, level: int) -> None:
        await self._async_yamaha_data_set("subwoofer volume", str(level))

    async def async_set_surround(self, enabled: bool) -> None:
        await self._async_yamaha_data_set("3D surround", str(int(enabled)))

    async def async_set_clear_voice(self, enabled: bool) -> None:
        await self._async_yamaha_data_set("clear voice", str(int(enabled)))

    async def async_set_bass_extension(self, enabled: bool) -> None:
        await self._async_yamaha_data_set("bass extension", str(int(enabled)))

    def set_led_sync(self, enabled: bool) -> None:
        """Set LED on/off via TCP/UART. Synchronous — caller must wrap in executor."""
        value = "1" if enabled else "0"
        self._tcpuart_sync(f"MCU+PAS+RAKOIT:LED:{value}&")

    async def async_recall_preset(self, number: int) -> None:
        await self._async_httpapi(f"MCUKeyShortClick:{number}")

    # --- Multiroom ---

    async def async_multiroom_join(self, slave_ip: str) -> None:
        """Add a slave to this device's multiroom group."""
        await self._async_httpapi(f"ConnectMasterAp:JoinGroupMaster:eth{slave_ip}:wifi0.0.0.0")

    async def async_multiroom_unjoin(self) -> None:
        """Remove this device from its multiroom group."""
        await self._async_httpapi("multiroom:Ungroup")

    async def async_multiroom_kick_slave(self, slave_ip: str) -> None:
        """Kick a specific slave from this device's group."""
        await self._async_httpapi(f"multiroom:SlaveKickout:{slave_ip}")
```

Note: `async_set_led` calls the synchronous `_tcpuart_sync` directly — the coordinator will wrap this in `hass.async_add_executor_job` before calling it.

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/client.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/yamaha_soundbar/client.py
git commit -m "feat: extract API client into client.py"
```

---

### Task 3: Data Model and Coordinator (`coordinator.py`)

Create the DataUpdateCoordinator that polls the device and exposes parsed data to all entities.

**Files:**
- Create: `custom_components/yamaha_soundbar/coordinator.py`
- Reference: `custom_components/yamaha_soundbar/media_player.py:494-650` (update logic)
- Reference: `custom_components/yamaha_soundbar/client.py` (from Task 2)

- [ ] **Step 1: Create coordinator.py**

```python
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
```

Note: Import `MAX_VOL` from const.py — add it to the const.py imports at the top of this file.

- [ ] **Step 2: Verify `MAX_VOL` import is present in coordinator**

Check: `MAX_VOL` must be in the coordinator's import from `const.py`. Verify the import line includes `MAX_VOL`.

- [ ] **Step 3: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/coordinator.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add custom_components/yamaha_soundbar/coordinator.py
git commit -m "feat: add DataUpdateCoordinator and YamahaData model"
```

---

### Task 4: Base Entity (`entity.py`)

Create the shared base entity class that provides device info and coordinator binding.

**Files:**
- Create: `custom_components/yamaha_soundbar/entity.py`

- [ ] **Step 1: Create entity.py**

```python
"""Base entity for Yamaha Soundbar."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import YamahaCoordinator


class YamahaSoundbarEntity(CoordinatorEntity[YamahaCoordinator]):
    """Base entity for Yamaha Soundbar devices."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: YamahaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.data.uuid)},
            name=coordinator.data.name,
            manufacturer="Yamaha",
            sw_version=f"{coordinator.data.firmware}-{coordinator.data.mcu_ver}",
        )
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/entity.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/yamaha_soundbar/entity.py
git commit -m "feat: add base entity class"
```

---

### Task 5: Config Flow and Options Flow (`config_flow.py` + `strings.json`)

Create the UI configuration flow for initial setup and the options flow for post-setup settings.

**Files:**
- Create: `custom_components/yamaha_soundbar/config_flow.py`
- Create: `custom_components/yamaha_soundbar/strings.json`
- Modify: `custom_components/yamaha_soundbar/manifest.json`

- [ ] **Step 1: Create config_flow.py**

```python
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
```

Note: Source mapping and source_ignore are complex UI elements. For the initial implementation, keep them as simple options. Source mapping can be enhanced later with a more sophisticated UI. The options flow covers the device settings first; source configuration can be added as a follow-up.

- [ ] **Step 2: Create strings.json**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Yamaha Soundbar",
        "data": {
          "host": "Host"
        },
        "data_description": {
          "host": "IP address of the soundbar"
        }
      }
    },
    "error": {
      "cannot_connect": "Cannot connect to the soundbar at this address",
      "unknown": "An unexpected error occurred"
    },
    "abort": {
      "already_configured": "This soundbar is already configured"
    }
  },
  "options": {
    "step": {
      "init": {
        "data": {
          "volume_step": "Volume step",
          "announce_volume_increase": "TTS volume boost",
          "icecast_metadata": "Icecast metadata mode",
          "led_off": "Turn off LED"
        }
      }
    }
  },
  "entity": {
    "select": {
      "sound_program": {
        "name": "Sound program"
      },
      "preset": {
        "name": "Preset"
      }
    },
    "number": {
      "subwoofer_volume": {
        "name": "Subwoofer volume"
      }
    },
    "switch": {
      "surround": {
        "name": "3D surround"
      },
      "clear_voice": {
        "name": "Clear voice"
      },
      "bass_extension": {
        "name": "Bass extension"
      },
      "led": {
        "name": "LED"
      }
    },
    "sensor": {
      "wifi_channel": {
        "name": "WiFi channel"
      }
    }
  }
}
```

- [ ] **Step 3: Update manifest.json**

Change `"config_flow": false` to `"config_flow": true` and bump version to `"4.0.0"`.

Current manifest.json:
```json
{
  "domain": "yamaha_soundbar",
  "name": "Yamaha Soundbar",
  "version": "3.2.3",
  ...
  "config_flow": false,
  ...
}
```

Change to:
```json
{
  "domain": "yamaha_soundbar",
  "name": "Yamaha Soundbar",
  "version": "4.0.0",
  ...
  "config_flow": true,
  ...
}
```

- [ ] **Step 4: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/config_flow.py').read()); print('OK')"`
Run: `python3 -c "import json; json.load(open('custom_components/yamaha_soundbar/strings.json')); print('OK')"`
Expected: Both `OK`

- [ ] **Step 5: Commit**

```bash
git add custom_components/yamaha_soundbar/config_flow.py custom_components/yamaha_soundbar/strings.json custom_components/yamaha_soundbar/manifest.json
git commit -m "feat: add config flow, options flow, and strings"
```

---

### Task 6: Integration Entry Point (`__init__.py`)

Rewrite the init module for config entry setup/unload and retained services.

**Files:**
- Rewrite: `custom_components/yamaha_soundbar/__init__.py`

- [ ] **Step 1: Rewrite __init__.py**

```python
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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Yamaha Soundbar integration."""
    hass.data.setdefault(DOMAIN, {"entities": []})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: YamahaSoundbarConfigEntry) -> bool:
    """Set up Yamaha Soundbar from a config entry."""
    host = entry.data["host"]

    # SSL context
    certpath = Path(__file__).parent / CONF_CERT_FILENAME
    ssl_ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ssl_ctx.load_cert_chain(certpath)
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

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
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/__init__.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/yamaha_soundbar/__init__.py
git commit -m "feat: rewrite __init__.py for config entry setup"
```

---

### Task 7: Select Entities (`select.py`)

Sound program and preset select entities.

**Files:**
- Create: `custom_components/yamaha_soundbar/select.py`

- [ ] **Step 1: Create select.py**

```python
"""Select entities for Yamaha Soundbar."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import YamahaCoordinator
from .entity import YamahaSoundbarEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Yamaha Soundbar select entities."""
    coordinator: YamahaCoordinator = entry.runtime_data
    async_add_entities([
        YamahaSoundProgramSelect(coordinator),
        YamahaPresetSelect(coordinator),
    ])


class YamahaSoundProgramSelect(YamahaSoundbarEntity, SelectEntity):
    """Sound program select entity (Yamaha DSP, distinct from EQ mode)."""

    _attr_translation_key = "sound_program"
    _attr_options = ["music", "movie", "sports", "game", "tv program", "stereo"]

    def __init__(self, coordinator: YamahaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.uuid}_sound_program"

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.data.sound_program
        if value in self._attr_options:
            return value
        return None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.client.async_set_sound_program(option)
        await self.coordinator.async_request_refresh()


class YamahaPresetSelect(YamahaSoundbarEntity, SelectEntity):
    """Preset select entity."""

    _attr_translation_key = "preset"

    def __init__(self, coordinator: YamahaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.uuid}_preset"
        preset_key = coordinator.data.preset_key
        self._attr_options = [f"Preset {i}" for i in range(1, preset_key + 1)]

    @property
    def current_option(self) -> str | None:
        num = self.coordinator.data.preset_number
        if num is not None and 1 <= num <= len(self._attr_options):
            return f"Preset {num}"
        return None

    async def async_select_option(self, option: str) -> None:
        number = int(option.split(" ")[1])
        await self.coordinator.client.async_recall_preset(number)
        await self.coordinator.async_request_refresh()
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/select.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/yamaha_soundbar/select.py
git commit -m "feat: add sound program and preset select entities"
```

---

### Task 8: Number Entity (`number.py`)

Subwoofer volume slider entity.

**Files:**
- Create: `custom_components/yamaha_soundbar/number.py`

- [ ] **Step 1: Create number.py**

```python
"""Number entities for Yamaha Soundbar."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import YamahaCoordinator
from .entity import YamahaSoundbarEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Yamaha Soundbar number entities."""
    coordinator: YamahaCoordinator = entry.runtime_data
    async_add_entities([YamahaSubwooferVolume(coordinator)])


class YamahaSubwooferVolume(YamahaSoundbarEntity, NumberEntity):
    """Subwoofer volume number entity."""

    _attr_translation_key = "subwoofer_volume"
    _attr_native_min_value = -4
    _attr_native_max_value = 4
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: YamahaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.uuid}_subwoofer_volume"

    @property
    def native_value(self) -> float:
        return float(self.coordinator.data.subwoofer_volume)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.async_set_subwoofer_volume(int(value))
        await self.coordinator.async_request_refresh()
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/number.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/yamaha_soundbar/number.py
git commit -m "feat: add subwoofer volume number entity"
```

---

### Task 9: Switch Entities (`switch.py`)

3D surround, clear voice, bass extension, and LED switch entities.

**Files:**
- Create: `custom_components/yamaha_soundbar/switch.py`

- [ ] **Step 1: Create switch.py**

```python
"""Switch entities for Yamaha Soundbar."""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import YamahaClient
from .coordinator import YamahaCoordinator, YamahaData
from .entity import YamahaSoundbarEntity


@dataclass(frozen=True, kw_only=True)
class YamahaSwitchEntityDescription(SwitchEntityDescription):
    """Describe a Yamaha switch entity."""

    value_fn: Callable[[YamahaData], bool]
    turn_on_fn: Callable[[YamahaClient], Coroutine[Any, Any, None]]
    turn_off_fn: Callable[[YamahaClient], Coroutine[Any, Any, None]]
    is_led: bool = False


SWITCH_DESCRIPTIONS: tuple[YamahaSwitchEntityDescription, ...] = (
    YamahaSwitchEntityDescription(
        key="surround",
        translation_key="surround",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.surround,
        turn_on_fn=lambda client: client.async_set_surround(True),
        turn_off_fn=lambda client: client.async_set_surround(False),
    ),
    YamahaSwitchEntityDescription(
        key="clear_voice",
        translation_key="clear_voice",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.clear_voice,
        turn_on_fn=lambda client: client.async_set_clear_voice(True),
        turn_off_fn=lambda client: client.async_set_clear_voice(False),
    ),
    YamahaSwitchEntityDescription(
        key="bass_extension",
        translation_key="bass_extension",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.bass_extension,
        turn_on_fn=lambda client: client.async_set_bass_extension(True),
        turn_off_fn=lambda client: client.async_set_bass_extension(False),
    ),
    YamahaSwitchEntityDescription(
        key="led",
        translation_key="led",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.led,
        # LED uses TCP/UART sync method — handled via is_led special case in switch entity
        turn_on_fn=lambda client: client.async_set_surround(True),  # unused, see is_led
        turn_off_fn=lambda client: client.async_set_surround(False),  # unused, see is_led
        is_led=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Yamaha Soundbar switch entities."""
    coordinator: YamahaCoordinator = entry.runtime_data
    async_add_entities(
        YamahaSoundbarSwitch(coordinator, description)
        for description in SWITCH_DESCRIPTIONS
    )


class YamahaSoundbarSwitch(YamahaSoundbarEntity, SwitchEntity):
    """Switch entity for Yamaha Soundbar."""

    entity_description: YamahaSwitchEntityDescription

    def __init__(
        self,
        coordinator: YamahaCoordinator,
        description: YamahaSwitchEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.data.uuid}_{description.key}"

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self.entity_description.is_led:
            # LED uses synchronous TCP/UART — wrap in executor
            await self.hass.async_add_executor_job(
                self.coordinator.client.set_led_sync, True
            )
            self.coordinator.set_led_state(True)
        else:
            await self.entity_description.turn_on_fn(self.coordinator.client)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.entity_description.is_led:
            await self.hass.async_add_executor_job(
                self.coordinator.client.set_led_sync, False
            )
            self.coordinator.set_led_state(False)
        else:
            await self.entity_description.turn_off_fn(self.coordinator.client)
        await self.coordinator.async_request_refresh()
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/switch.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/yamaha_soundbar/switch.py
git commit -m "feat: add surround, clear voice, bass extension, LED switches"
```

---

### Task 10: Sensor Entity (`sensor.py`)

WiFi channel diagnostic sensor.

**Files:**
- Create: `custom_components/yamaha_soundbar/sensor.py`

- [ ] **Step 1: Create sensor.py**

```python
"""Sensor entities for Yamaha Soundbar."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import YamahaCoordinator
from .entity import YamahaSoundbarEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Yamaha Soundbar sensor entities."""
    coordinator: YamahaCoordinator = entry.runtime_data
    async_add_entities([YamahaWifiChannelSensor(coordinator)])


class YamahaWifiChannelSensor(YamahaSoundbarEntity, SensorEntity):
    """WiFi channel diagnostic sensor."""

    _attr_translation_key = "wifi_channel"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: YamahaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.uuid}_wifi_channel"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.wifi_channel
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/sensor.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/yamaha_soundbar/sensor.py
git commit -m "feat: add WiFi channel diagnostic sensor"
```

---

### Task 11: Media Player Entity (`media_player.py`)

Rewrite the media player entity to read from the coordinator. This is the largest task — it must retain all existing playback, browsing, TTS, multiroom, and Music Assistant functionality while delegating state to the coordinator.

**Files:**
- Rewrite: `custom_components/yamaha_soundbar/media_player.py`
- Reference: Current `media_player.py` (2,862 lines) — the new version should be significantly shorter

- [ ] **Step 1: Rewrite media_player.py**

This is a large rewrite. The key structural changes:

1. **Remove:** `async_setup_platform`, `PLATFORM_SCHEMA`, `YamahaData` class, all constants (moved to const.py)
2. **Remove:** `async_call_yamaha_httpapi`, `async_call_yamaha_tcpuart`, `_call_yamaha_tcpuart_sync` (moved to client.py)
3. **Remove:** `async_get_status`, all state-parsing in `async_update` (moved to coordinator)
4. **Remove:** `async_set_sound` (replaced by switch/select entities)
5. **Remove:** `async_preset_button` (replaced by preset select entity)
6. **Remove:** `async_execute_command` (dropped)
7. **Keep:** All playback control methods, media browsing, TTS/snapshot/restore, multiroom, Music Assistant, UPnP metadata, icecast metadata, firmware checks, Spotify pause timeout
8. **Change:** Entity extends `YamahaSoundbarEntity` (from entity.py) instead of raw `MediaPlayerEntity`
9. **Change:** All state reads come from `self.coordinator.data` instead of `self._*` instance variables
10. **Change:** `unique_id` = `"yamaha_media_" + uuid` (preserved)
11. **Change:** Commands call `self.coordinator.client` instead of `self.async_call_yamaha_httpapi`

The rewritten entity class structure:

```python
"""Media player entity for Yamaha Soundbar."""
from __future__ import annotations

# ... imports ...

from .const import (
    DOMAIN, ICON_DEFAULT, ICON_PLAYING, ICON_MUTED, ICON_BLUETOOTH,
    ICON_MULTIROOM, ICON_PUSHSTREAM, ICON_TTS, SOUND_MODES,
    SOURCES_MAP, SOURCES_LIVEIN, SOURCES_STREAM, SOURCES_LOCALF,
    # ... etc
)
from .coordinator import YamahaCoordinator, YamahaData
from .entity import YamahaSoundbarEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: YamahaCoordinator = entry.runtime_data
    entity = YamahaDevice(coordinator, entry)
    async_add_entities([entity])
    # Register entity for service lookups
    hass.data[DOMAIN]["entities"].append(entity)


class YamahaDevice(YamahaSoundbarEntity, MediaPlayerEntity):
    _attr_name = None  # Uses device name

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"yamaha_media_{coordinator.data.uuid}"
        # Entry options
        self._volume_step = entry.options.get("volume_step", 5)
        self._announce_volume_increase = entry.options.get("announce_volume_increase", 15)
        self._icecast_meta = entry.options.get("icecast_metadata", "StationName")
        # TTS/announce state (entity-local, not in coordinator)
        self._announce = False
        self._playing_tts = False
        self._snapshot_active = False
        self._snap_source = None
        self._snap_state = None
        self._snap_volume = 0
        self._snap_uri = None
        self._snap_spotify = False
        # ... other entity-local state for playback tracking ...

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Subscribe to Music Assistant events
        self.async_on_remove(
            self.hass.bus.async_listen("mass_event", self._handle_mass_event)
        )

    # --- Properties read from coordinator.data ---

    @property
    def state(self):
        return self.coordinator.data.state

    @property
    def volume_level(self):
        return self.coordinator.data.volume

    @property
    def is_volume_muted(self):
        return self.coordinator.data.muted

    @property
    def source(self):
        return self.coordinator.data.source

    @property
    def source_list(self):
        sl = self.coordinator.data.source_list
        return list(sl.values()) if sl else None

    @property
    def sound_mode(self):
        return self.coordinator.data.eq_mode

    @property
    def sound_mode_list(self):
        return list(SOUND_MODES.values())

    # ... media_title, media_artist, etc from coordinator.data ...

    # --- Commands call coordinator.client ---

    async def async_set_volume_level(self, volume):
        await self.coordinator.client.async_set_volume(int(volume * 100))
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute):
        await self.coordinator.client.async_mute(mute)
        await self.coordinator.async_request_refresh()

    async def async_select_sound_mode(self, sound_mode):
        mode = list(SOUND_MODES.keys())[list(SOUND_MODES.values()).index(sound_mode)]
        await self.coordinator.client.async_set_eq_mode(int(mode))
        await self.coordinator.async_request_refresh()

    async def async_set_shuffle(self, shuffle):
        """Set shuffle. Must consider current repeat state — Linkplay interleaves them."""
        if shuffle:
            mode = "2"  # shuffle + repeat all
        else:
            repeat = self.coordinator.data.repeat
            if repeat == RepeatMode.OFF:
                mode = "0"
            elif repeat == RepeatMode.ALL:
                mode = "3"
            elif repeat == RepeatMode.ONE:
                mode = "1"
        await self.coordinator.client.async_set_loopmode(mode)
        await self.coordinator.async_request_refresh()

    async def async_set_repeat(self, repeat):
        """Set repeat. Must consider current shuffle state."""
        shuffle = self.coordinator.data.shuffle
        if repeat == RepeatMode.OFF:
            mode = "0"
        elif repeat == RepeatMode.ALL:
            mode = "2" if shuffle else "3"
        elif repeat == RepeatMode.ONE:
            mode = "1"
        await self.coordinator.client.async_set_loopmode(mode)
        await self.coordinator.async_request_refresh()

    # ... all other playback methods similarly refactored ...

    # --- Retained complex logic ---
    # TTS snapshot/restore, multiroom join/unjoin, media browsing,
    # playlist parsing, icecast metadata, Music Assistant events,
    # firmware version checks, Spotify pause timeout — all stay
    # but use coordinator.client for API calls and coordinator.data for state

    async def async_will_remove_from_hass(self):
        """Remove entity from service lookup list."""
        entities = self.hass.data[DOMAIN]["entities"]
        if self in entities:
            entities.remove(self)
```

**Implementation guidance for the executing agent:**

This rewrite requires careful method-by-method migration. Work through the current `media_player.py` and for each method:
- If it's a communication method → it's already in `client.py`, use `self.coordinator.client`
- If it's a state-reading property → read from `self.coordinator.data`
- If it's a state-setting command → call `self.coordinator.client.async_*()` then `self.coordinator.async_request_refresh()`
- If it's complex playback logic (TTS, multiroom, browsing, metadata) → keep it, but adapt to use coordinator

The current media_player.py has significant complexity in:
- `async_update()` (lines 528-860) — most of this moves to coordinator; what remains is entity-local state tracking (TTS, Spotify timeout, icon selection)
- `async_play_media()` (lines 1293-1470) — stays but uses coordinator.client
- `async_update_via_upnp()` (lines 2688-2860) — stays, uses `coordinator.upnp_device`
- `async_snapshot()`/`async_restore()` (lines 2180-2450) — stays as entity-local state machine
- `handle_event()`/`get_music_assistant_metadata()` (lines 417-1819) — stays, pushes to coordinator
- Media browsing (`async_browse_media()`) — stays as-is

**YAML import trigger:** The rewritten `media_player.py` must include an `async_setup_platform` function that detects YAML config and triggers config flow import:

```python
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Handle YAML config — trigger import flow to create config entry."""
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "import"},
            data=dict(config),
        )
    )
```

**Do NOT try to write the complete 2000+ line file in one step.** Instead:
1. Start with the class skeleton, properties, and simple command methods
2. Port the complex methods one section at a time (playback, browsing, TTS, multiroom, MASS)
3. Test that the integration loads after each section

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/media_player.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/yamaha_soundbar/media_player.py
git commit -m "feat: rewrite media_player to use coordinator"
```

---

### Task 12: Update services.yaml

Remove the dropped services from services.yaml, keep only retained ones.

**Files:**
- Modify: `custom_components/yamaha_soundbar/services.yaml`

- [ ] **Step 1: Remove dropped services**

Remove these service definitions from `services.yaml`:
- `preset` (replaced by preset select entity)
- `command` (dropped)
- `sound_settings` (replaced by entities)

Keep:
- `join`
- `unjoin`
- `snapshot`
- `restore`
- `play_track`

- [ ] **Step 2: Verify YAML is valid**

Run: `python3 -c "import yaml; yaml.safe_load(open('custom_components/yamaha_soundbar/services.yaml')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/yamaha_soundbar/services.yaml
git commit -m "chore: remove dropped services from services.yaml"
```

---

### Task 13: Integration Testing

Load the integration in Home Assistant and verify everything works.

**Files:**
- All files from Tasks 1-12

- [ ] **Step 1: Verify all files parse correctly**

Run:
```bash
for f in custom_components/yamaha_soundbar/*.py; do
  python3 -c "import ast; ast.parse(open('$f').read()); print('OK: $f')"
done
```
Expected: All files print `OK`

- [ ] **Step 2: Verify JSON files**

Run:
```bash
python3 -c "import json; json.load(open('custom_components/yamaha_soundbar/strings.json')); print('OK: strings.json')"
python3 -c "import json; json.load(open('custom_components/yamaha_soundbar/manifest.json')); print('OK: manifest.json')"
```
Expected: Both `OK`

- [ ] **Step 3: Check for import consistency**

Run:
```bash
python3 -c "
import ast, os
files = [f for f in os.listdir('custom_components/yamaha_soundbar') if f.endswith('.py')]
for f in files:
    tree = ast.parse(open(f'custom_components/yamaha_soundbar/{f}').read())
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    print(f'{f}: {len(imports)} imports')
"
```
Expected: All files listed with import counts, no errors

- [ ] **Step 4: Manual testing in HA**

1. Copy the integration to your HA `custom_components/` directory
2. Restart Home Assistant
3. Go to Settings → Integrations → Add Integration → "Yamaha Soundbar"
4. Enter your soundbar's IP address
5. Verify the device appears with all entities:
   - Media player (with EQ sound mode control)
   - Sound program select
   - Preset select
   - Subwoofer volume slider
   - 3D surround switch
   - Clear voice switch
   - Bass extension switch
   - LED switch
   - WiFi channel sensor (disabled by default)
6. Test playback controls from the media player card
7. Test changing sound program, subwoofer volume, and toggles
8. Test options flow (Settings → Integrations → Yamaha Soundbar → Configure)

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete yamaha_soundbar integration redesign v4.0.0"
```
