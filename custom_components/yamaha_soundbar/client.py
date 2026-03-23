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

        The media player entity handles the shuffle/repeat to loopmode mapping
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
