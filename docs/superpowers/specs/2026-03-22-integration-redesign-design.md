# Yamaha Soundbar Integration Redesign

## Overview

Restructure the `yamaha_soundbar` custom integration from a monolithic YAML-configured media player into a modern HA integration with config flow, options flow, a DataUpdateCoordinator, extracted API client, and dedicated entities for soundbar-specific controls.

## Goals

- Replace YAML configuration with UI-based config flow and options flow
- Extract API communication into a standalone client module
- Centralize polling via DataUpdateCoordinator
- Expose sound settings, subwoofer, and device toggles as proper HA entities
- Remove redundant services replaced by entities
- Slim down media_player.py from ~2,800 lines to a focused entity

## Non-Goals

- SSDP/UPnP auto-discovery (manual IP entry only)
- Custom Lovelace card
- LastFM API key support (dropped)
- Multiroom WiFi Direct option (dropped)
- Device commands service (Rescan, PromptEnable, etc. — dropped)
- Power saving switch (was in `sound_settings` service, not needed as entity)

---

## Architecture

### File Structure

```
custom_components/yamaha_soundbar/
├── __init__.py          # async_setup_entry, async_unload_entry, service registration
├── manifest.json        # config_flow: true, updated metadata
├── const.py             # DOMAIN, defaults, enums, platform list
├── config_flow.py       # Config flow (host entry) + options flow (sources, settings)
├── strings.json         # All UI text for config/options flows and entity translations
├── client.py            # YamahaClient — HTTP/TCP/UPnP communication
├── coordinator.py       # YamahaCoordinator + YamahaData dataclass
├── entity.py            # YamahaSoundbarEntity base class
├── media_player.py      # Media player entity (slimmed down)
├── select.py            # Sound program + preset select entities
├── number.py            # Subwoofer volume entity
├── switch.py            # 3D surround, clear voice, bass extension, LED switches
├── sensor.py            # WiFi channel diagnostic sensor
├── client.pem           # SSL certificate (existing)
└── services.yaml        # Remaining services: join, unjoin, snapshot, restore, play_track
```

### Data Flow

```
YamahaClient (HTTP/TCP/UPnP)
    ↓
YamahaCoordinator (polls every 10s, parses into YamahaData)
    ↓
┌─────────────────────────────────────────────┐
│  MediaPlayer  Select  Number  Switch  Sensor │
│  (all read from coordinator.data)            │
└─────────────────────────────────────────────┘
    ↓ (write operations)
YamahaClient (direct command, then coordinator.async_request_refresh())

    ↑ (push events — not from coordinator)
Music Assistant event bus → MediaPlayer entity (updates coordinator.data via async_set_updated_data)
```

---

## Config Flow

### Initial Setup (`async_step_user`)

1. User adds integration via UI
2. Single form: host IP address
3. Validation:
   - Call `getStatusEx` via the client to confirm device is reachable
   - Extract device name, UUID, firmware from response
4. Set `unique_id` to device UUID → `self._abort_if_unique_id_configured()`
5. Create config entry:
   - `title` = device name from API
   - `data` = `{CONF_HOST: host, CONF_UUID: uuid}`

### YAML Import

- `async_setup_platform` detects existing YAML config
- Auto-creates a config entry with equivalent settings
- YAML config parameters map to:
  - `host`, `uuid` → `entry.data`
  - `sources`, `source_ignore`, `volume_step`, `announce_volume_increase`, `icecast_metadata`, `led_off` → `entry.options`
  - `common_sources` → merged into `sources` option (flattened into the same source mapping dict)
- After import, YAML config is no longer needed

### Options Flow

Two-section form for post-setup configuration:

**Sources section:**
- Source mapping: key-value pairs for renaming inputs (e.g., HDMI → "TV", optical → "Plexamp")
- Source ignore: multi-select list to hide unused sources (new feature — the YAML config accepted this parameter but the current code never applied the filter; this implementation will actually filter the source list)

**Device settings section:**
- Volume step: integer 1-25 (default: 5)
- Announce volume increase: integer 0-50 (default: 15)
- Icecast metadata: select Off / StationName / StationNameSongTitle (default: Off)
- LED off: boolean (default: false)

**On change:** Config entry reloads to apply new settings immediately.

---

## API Client (`client.py`)

### Class: `YamahaClient`

```python
class YamahaClient:
    def __init__(self, host: str, session: aiohttp.ClientSession, ssl_context: ssl.SSLContext) -> None
```

Pure Python class, no HA imports. All methods are async except `_tcpuart_sync` which is synchronous (caller must wrap in executor).

### Methods

**Status/Query:**
- `async_get_device_status() -> dict` — calls `getStatusEx`, returns parsed response (device info, volume, source, wifi, preset_key, etc.)
- `async_get_player_status() -> dict` — calls `getPlayerStatus`, returns parsed response (playback state, metadata, eq, position, etc.)
- `async_get_sound_settings() -> dict` — calls `YAMAHA_DATA_GET`, returns parsed Yamaha-specific settings (sound program, subwoofer volume, surround, clear voice, bass extension, mute, power saving)
- `async_get_tracks(upnp_device) -> list` — track listing via UPnP DIDL-Lite

**Playback Control:**
- `async_play() -> None`
- `async_pause() -> None`
- `async_stop() -> None`
- `async_next() -> None`
- `async_previous() -> None`
- `async_seek(position: int) -> None`
- `async_set_volume(level: int) -> None` — 0-100
- `async_mute(mute: bool) -> None`
- `async_select_source(source: str) -> None`
- `async_play_media(url: str) -> None`
- `async_set_shuffle(shuffle: bool) -> None`
- `async_set_repeat(repeat: str) -> None`

**Sound/Device Settings (via `YAMAHA_DATA_SET`):**
- `async_set_sound_program(program: str) -> None` — uses `YAMAHA_DATA_SET` with `"sound program"` key, with retry-until-confirmed loop (existing pattern from `async_set_sound`)
- `async_set_subwoofer_volume(level: int) -> None` — via `YAMAHA_DATA_SET` with `"subwoofer volume"` key, -4 to +4
- `async_set_surround(enabled: bool) -> None` — via `YAMAHA_DATA_SET` with `"3d surround"` key
- `async_set_clear_voice(enabled: bool) -> None` — via `YAMAHA_DATA_SET` with `"clear voice"` key
- `async_set_bass_extension(enabled: bool) -> None` — via `YAMAHA_DATA_SET` with `"bass extension"` key
- `async_set_led(enabled: bool) -> None` — via TCP/UART MCU command (`MCU+PAS+RAKOIT:LED:1`/`0`)
- `async_recall_preset(number: int) -> None` — 1-N (dynamic limit)

**EQ Mode (via `setPlayerCmd:equalizer`):**
- `async_set_eq_mode(mode: int) -> None` — 0-4, used by media player's `select_sound_mode`

**Multiroom:**
- `async_join(slave_ips: list[str]) -> None`
- `async_unjoin() -> None`

**Snapshot/Restore:**
- `async_snapshot(switch_input: bool) -> None`
- `async_restore() -> None`

**Track Playback:**
- `async_play_track(track_name: str, tracks: list) -> None`

**Low-level (private):**
- `_async_httpapi(command: str) -> str` — HTTPS call to `/httpapi.asp`
- `_tcpuart_sync(command: str) -> str` — synchronous TCP socket on port 8899 (caller wraps in executor)

### Communication Details

- **HTTPS:** `https://{host}/httpapi.asp?command={cmd}`, SSL context with `client.pem`, timeout 5s
- **TCP/UART:** Port 8899, synchronous socket (caller wraps in `hass.async_add_executor_job`), timeout 5s
- **UPnP:** Via `async-upnp-client` library, device at `http://{host}:49152/description.xml`

### Note on HA dependency for TCP/UART

The client itself is pure Python, but `_tcpuart_sync` is synchronous. The coordinator (which has access to `hass`) wraps calls to TCP/UART methods in `hass.async_add_executor_job`. The client provides the sync method; the coordinator handles the async wrapping.

---

## Coordinator (`coordinator.py`)

### Class: `YamahaCoordinator`

```python
class YamahaCoordinator(DataUpdateCoordinator[YamahaData]):
    update_interval = timedelta(seconds=10)
```

Accepts `config_entry` parameter.

### Data Model: `YamahaData`

```python
@dataclass
class YamahaData:
    # Device info
    name: str
    uuid: str
    firmware: str
    preset_key: int              # max preset number supported by device

    # Playback state
    state: str                   # playing, paused, idle, unknown
    volume: float                # 0.0-1.0
    muted: bool
    source: str
    source_list: list[str]

    # Media metadata
    title: str | None
    artist: str | None
    album: str | None
    image_url: str | None
    duration: int | None
    position: int | None
    shuffle: bool
    repeat: str

    # EQ mode (from getPlayerStatus "eq" field)
    eq_mode: str                 # Normal, Classic, Pop, Jazz, Vocal

    # Yamaha sound settings (from YAMAHA_DATA_GET)
    sound_program: str           # music, movie, sports, game, etc.
    subwoofer_volume: int        # -4 to +4
    surround: bool
    clear_voice: bool
    bass_extension: bool

    # LED state (tracked locally — no read-back from device)
    led: bool

    # Multiroom
    group_members: list[str]
    is_master: bool
    slave: bool

    # Internal
    playing_mode: int
    preset_number: int | None
    wifi_channel: int | None
```

### Important: EQ Mode vs Sound Program

These are **two distinct settings** on the device:

1. **EQ Mode** (`eq` field from `getPlayerStatus`, set via `setPlayerCmd:equalizer:{n}`): 5 modes — Normal, Classic, Pop, Jazz, Vocal. This is the existing `sound_mode` on the media player entity and stays there.

2. **Sound Program** (`"sound program"` field from `YAMAHA_DATA_GET`, set via `YAMAHA_DATA_SET`): Yamaha DSP programs — music, movie, sports, game, tv program, stereo. This is the new select entity.

Both are exposed: EQ mode via the media player's built-in `select_sound_mode`, sound program via a dedicated select entity.

### Update Logic (`_async_update_data`)

1. Call `client.async_get_device_status()` for device-level info (name, uuid, firmware, wifi_channel, preset_key, source, multiroom state)
2. Call `client.async_get_player_status()` for playback state (volume, mute, eq, shuffle, repeat, state, metadata)
3. Call `client.async_get_sound_settings()` for Yamaha-specific settings (sound program, subwoofer volume, surround, clear voice, bass extension)
4. Parse all three responses into a `YamahaData` instance
5. If playing Spotify/DLNA: fetch UPnP metadata (with 60s retry backoff on failure)
6. If playing icecast stream: fetch stream metadata (throttled to 45s)
7. On connection error: raise `UpdateFailed`
8. Return `YamahaData` instance

**Note on LED state:** The LED is controlled via TCP/UART and has no known read-back mechanism. The LED state is tracked locally in the coordinator. On startup, it initializes to the `led_off` option value. When the switch entity toggles it, the coordinator updates its local state. This means LED state may be wrong if changed outside HA (e.g., via the Yamaha app), but this is acceptable since there's no API to query it.

### Multiroom Slave Behavior

Each configured device gets its own coordinator instance. In the current code, slave devices skip their own polling and receive state pushes from the master entity.

In the redesigned architecture:
- Each device's coordinator polls independently (slaves still poll `getStatusEx` to detect their own slave/master state)
- The master media player entity holds references to slave media player entities (looked up via `hass.data[DOMAIN]`)
- When the master sends a playback command, it also pushes relevant state to slave entities (e.g., sound mode propagation)
- The coordinator's `_async_update_data` detects slave mode from the device status and can short-circuit expensive metadata fetches (no UPnP, icecast, or `getPlayerStatus` needed when slaved)

### Music Assistant Event Integration

Music Assistant pushes metadata via `mass_event` on the HA event bus (not via polling). This doesn't fit the coordinator's poll-based model.

Approach:
- The media player entity subscribes to `mass_event` in `async_added_to_hass` (with `async_on_remove` for cleanup)
- When a MASS event arrives, the media player parses the metadata (title, artist, image, duration, position) and calls `coordinator.async_set_updated_data()` with an updated `YamahaData` instance
- This pushes the new data to all entities and triggers a state write without waiting for the next poll cycle

### Write Pattern

Entities send commands through the client directly, then call:
```python
await coordinator.async_request_refresh()
```

---

## Entities

### Base Entity (`entity.py`)

```python
class YamahaSoundbarEntity(CoordinatorEntity[YamahaCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: YamahaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.data.uuid)},
            name=coordinator.data.name,
            manufacturer="Yamaha",
            model=<from API if available>,
            sw_version=coordinator.data.firmware,
        )
```

### Media Player (`media_player.py`)

- `_attr_name = None` (uses device name)
- `unique_id = "yamaha_media_" + uuid` (preserves existing unique_id format to avoid entity migration)
- Reads playback state from `coordinator.data`
- Supported features are dynamic based on `playing_mode` (same logic as current, just reading from coordinator)
- **EQ mode** stays on the media player as `sound_mode` / `sound_mode_list` (Normal, Classic, Pop, Jazz, Vocal) — uses `client.async_set_eq_mode()` which calls `setPlayerCmd:equalizer:{n}`
- Playback commands call client directly + request refresh
- Retains: media browsing, playlist parsing, icecast metadata display, Music Assistant event handling, firmware-version-conditional behavior (`_fwvercheck`), Spotify pause timeout (300s auto-stop)
- Removes: all Yamaha sound settings logic (`async_set_sound`), preset logic, internal state tracking for coordinator-owned fields

### TTS/Announce State

The TTS/announce flow (`async_snapshot`, `async_restore`, `ATTR_MEDIA_ANNOUNCE` handling) involves a multi-step state machine that spans multiple update cycles. These fields are **media player entity-local state**, not part of `YamahaData`:

- `_announce: bool` — TTS announce in progress
- `_playing_tts: bool` — TTS audio currently playing
- `_snap_source: str` — snapshotted source
- `_snap_state: str` — snapshotted playback state
- `_snap_volume: int` — snapshotted volume
- `_snap_uri: str` — snapshotted media URI
- `_snap_position: int` — snapshotted playback position
- `_snap_spotify: bool` — was Spotify playing when snapshotted

These don't belong in the coordinator because they're transient workflow state specific to the media player entity.

### Select Entities (`select.py`)

**Sound Program (Yamaha DSP):**
- `unique_id = {uuid}_sound_program`
- `translation_key = "sound_program"`
- Options: determined by device capabilities; common values include `["music", "movie", "sports", "game", "tv program", "stereo"]`
- Read: `coordinator.data.sound_program`
- Write: `client.async_set_sound_program(option)` + refresh (uses `YAMAHA_DATA_SET` with retry-until-confirmed loop)
- Note: this is distinct from the media player's EQ mode (`sound_mode`)

**Preset:**
- `unique_id = {uuid}_preset`
- `translation_key = "preset"`
- Options: dynamically generated from `coordinator.data.preset_key` — `["Preset 1", ..., "Preset N"]` where N = `preset_key` (typically 4-36 depending on device)
- Read: `coordinator.data.preset_number` (mapped to label, or "Unknown" if None)
- Write: `client.async_recall_preset(number)` + refresh
- Note: write-only in practice — value reflects last recalled preset

### Number Entity (`number.py`)

**Subwoofer Volume:**
- `unique_id = {uuid}_subwoofer_volume`
- `translation_key = "subwoofer_volume"`
- `native_min_value = -4`, `native_max_value = 4`, `native_step = 1`
- `mode = NumberMode.SLIDER`
- Read: `coordinator.data.subwoofer_volume`
- Write: `client.async_set_subwoofer_volume(int(value))` + refresh

### Switch Entities (`switch.py`)

All switches use `entity_category = EntityCategory.CONFIG`.

| Entity | unique_id | translation_key | Read field | Write method |
|--------|-----------|-----------------|------------|--------------|
| 3D Surround | `{uuid}_surround` | `surround` | `coordinator.data.surround` | `client.async_set_surround(on)` |
| Clear Voice | `{uuid}_clear_voice` | `clear_voice` | `coordinator.data.clear_voice` | `client.async_set_clear_voice(on)` |
| Bass Extension | `{uuid}_bass_extension` | `bass_extension` | `coordinator.data.bass_extension` | `client.async_set_bass_extension(on)` |
| LED | `{uuid}_led` | `led` | `coordinator.data.led` | `client.async_set_led(on)` |

**LED note:** State is tracked locally (no read-back from device). See coordinator section for details.

### Sensor Entity (`sensor.py`)

**WiFi Channel:**
- `unique_id = {uuid}_wifi_channel`
- `translation_key = "wifi_channel"`
- `entity_category = EntityCategory.DIAGNOSTIC`
- `entity_registry_enabled_default = False`
- Read: `coordinator.data.wifi_channel`

---

## Services

### Retained Services

Registered in `async_setup_entry` with entity lookup via `hass.data[DOMAIN]`. Services are registered on first entry setup and removed when last entry unloads.

- **`join`** — master + slave entity targeting for multiroom grouping
- **`unjoin`** — remove from multiroom group
- **`snapshot`** — save player state for TTS (with optional `switchinput`)
- **`restore`** — restore player state after TTS
- **`play_track`** — play track by name from device storage

### Removed Services

- **`sound_settings`** — replaced by sound program select, subwoofer number, surround/clear voice/bass extension switches
- **`command`** — LED replaced by switch entity; remaining commands dropped
- **`preset`** — replaced by preset select entity

---

## strings.json Structure

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
          "sources": "Source mapping",
          "source_ignore": "Sources to hide",
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
      "sound_program": { "name": "Sound program" },
      "preset": { "name": "Preset" }
    },
    "number": {
      "subwoofer_volume": { "name": "Subwoofer volume" }
    },
    "switch": {
      "surround": { "name": "3D surround" },
      "clear_voice": { "name": "Clear voice" },
      "bass_extension": { "name": "Bass extension" },
      "led": { "name": "LED" }
    },
    "sensor": {
      "wifi_channel": { "name": "WiFi channel" }
    }
  }
}
```

---

## Migration Strategy

### YAML → Config Entry

1. On load, `async_setup_platform` checks for existing YAML config
2. If found, triggers config flow import:
   - `host` and `uuid` → `entry.data`
   - `sources` and `common_sources` → merged into single `sources` option (common_sources flattened into the source mapping dict)
   - `source_ignore`, `volume_step`, `announce_volume_increase`, `icecast_metadata`, `led_off` → `entry.options`
3. Config entry is created automatically
4. User can then remove YAML config at their leisure

### Entity Unique IDs

- Media player: `"yamaha_media_" + uuid` (preserves existing format to avoid orphaned entities)
- All new entities: `{uuid}_{key}` (e.g., `{uuid}_sound_program`, `{uuid}_subwoofer_volume`)

### Clean Break

- No deprecation period for removed services
- Old `sound_settings`, `command`, `preset` services are simply not registered
- Any automations using these services need manual update to use new entities

---

## Entry Setup Flow

### `async_setup_entry`

1. Create SSL context (load `client.pem`)
2. Create `aiohttp.ClientSession` via `async_create_clientsession`
3. Instantiate `YamahaClient(host, session, ssl_context)`
4. Instantiate `YamahaCoordinator(hass, client, entry)`
5. Call `await coordinator.async_config_entry_first_refresh()`
   - If device unreachable: raises `ConfigEntryNotReady` automatically
6. Store coordinator as `entry.runtime_data`
7. Forward setup to platforms: `media_player`, `select`, `number`, `switch`, `sensor`
8. Register services (if not already registered by another entry)

### `async_unload_entry`

1. Unload all platforms via `hass.config_entries.async_unload_platforms`
2. Unregister services if this was the last entry
3. Session cleanup handled by HA's `async_create_clientsession`

---

## manifest.json Changes

```json
{
  "domain": "yamaha_soundbar",
  "name": "Yamaha Soundbar",
  "version": "4.0.0",
  "documentation": "https://github.com/osk2/yamaha-soundbar",
  "issue_tracker": "https://github.com/osk2/yamaha-soundbar",
  "after_dependencies": ["http", "tts", "media_source"],
  "config_flow": true,
  "iot_class": "local_polling",
  "requirements": [
    "async-upnp-client>=0.27",
    "validators~=0.12",
    "chardet>=4.0.0"
  ]
}
```

Key change: `"config_flow": true` and version bump to `4.0.0` (breaking change).
