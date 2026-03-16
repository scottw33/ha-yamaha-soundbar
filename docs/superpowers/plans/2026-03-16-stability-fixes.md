# Stability Fixes Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate constant HA log errors by fixing HTTP client lifecycle, error handling, polling intervals, and blocking I/O in the Yamaha Soundbar integration.

**Architecture:** All changes are in a single file (`media_player.py`). Tasks are ordered so each produces a working, independently committable change. Earlier tasks (constants, imports) are prerequisites for later tasks (shared session, availability pattern).

**Tech Stack:** Python 3.14, Home Assistant 2026.3.1, aiohttp, async-upnp-client

**Spec:** `docs/superpowers/specs/2026-03-16-stability-fixes-design.md`

---

## File Structure

All changes are in one file:
- **Modify:** `custom_components/yamaha_soundbar/media_player.py`

No new files are created. No other files are modified.

---

## Chunk 1: Constants, Imports, and Bare Except Cleanup

### Task 1: Update constants and imports

**Files:**
- Modify: `custom_components/yamaha_soundbar/media_player.py:1-138`

- [ ] **Step 1: Update imports — remove unused, add missing**

Remove the unused `CancelledError` import (line 9). Add `import requests` (needed for typed exception at line 2005). Add `import urllib.error` for typed icecast exception.

Change line 9:
```python
# REMOVE this line:
from asyncio import CancelledError
```

Add after `import urllib.request` (line 19):
```python
import urllib.error
import requests
```

- [ ] **Step 2: Update timeout and polling constants**

Change lines 128-138 in `media_player.py`:
```python
UPNP_TIMEOUT = 5
API_TIMEOUT = 5
SCAN_INTERVAL = timedelta(seconds=10)
ICE_THROTTLE = timedelta(seconds=45)
LFM_THROTTLE = timedelta(seconds=4)
UNA_THROTTLE = timedelta(seconds=20)
MROOM_UJWDIR = timedelta(seconds=20)
MROOM_UJWROU = timedelta(seconds=3)
SPOTIFY_PAUSED_TIMEOUT = timedelta(seconds=300)
AUTOIDLE_STATE_TIMEOUT = timedelta(seconds=2)
UPNP_RETRY_INTERVAL = timedelta(seconds=60)
PARALLEL_UPDATES = 1
```

Key changes: `UPNP_TIMEOUT` 2→5, `API_TIMEOUT` 2→5, `SCAN_INTERVAL` 3s→10s, added `UPNP_RETRY_INTERVAL`, uncommented and set `PARALLEL_UPDATES = 1`.

- [ ] **Step 3: Verify the file still parses**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/media_player.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add custom_components/yamaha_soundbar/media_player.py
git commit -m "chore: update constants, imports, and polling intervals

SCAN_INTERVAL 3s→10s, API_TIMEOUT 2s→5s, UPNP_TIMEOUT 2s→5s,
PARALLEL_UPDATES=1. Remove unused CancelledError import, add
urllib.error and requests imports for typed exceptions."
```

---

### Task 2: Replace all 12 bare `except:` clauses with typed exceptions

**Files:**
- Modify: `custom_components/yamaha_soundbar/media_player.py` (lines 478, 616, 1889, 2005, 2678, 2738, 2772, 2781, 2797, 2804, 2811, 2820)

- [ ] **Step 1: Fix line 478 — socket close**

```python
# BEFORE (line 478):
            except:
                pass

# AFTER:
            except OSError:
                pass
```

- [ ] **Step 2: Fix line 616 — UPnP device creation (the main NameError crash)**

```python
# BEFORE (lines 616-619):
                            except:
                                _LOGGER.warning(
                                    "Failed communicating with Yamaha (UPnP) '%s': %s", self._name, type(error)
                                )

# AFTER:
                            except Exception as err:
                                _LOGGER.warning(
                                    "Failed communicating with Yamaha (UPnP) '%s': %s", self._name, err
                                )
```

- [ ] **Step 3: Fix line 1889 — urllib icecast request**

```python
# BEFORE (line 1889):
        except:  # (urllib.error.HTTPError)

# AFTER:
        except (urllib.error.URLError, OSError) as err:
```

- [ ] **Step 4: Fix line 2005 — URI redirect detection**

```python
# BEFORE (line 2005):
        except:
            pass

# AFTER:
        except (requests.RequestException, OSError, ValueError):
            pass
```

- [ ] **Step 5: Fix line 2678 — UPnP GetMediaInfo**

```python
# BEFORE (line 2678):
        except:
            _LOGGER.warning("GetMediaInfo/CurrentURIMetaData UPNP error: %s", self.entity_id)

# AFTER:
        except Exception as err:
            _LOGGER.warning("GetMediaInfo/CurrentURIMetaData UPNP error: %s: %s", self.entity_id, err)
```

- [ ] **Step 6: Fix line 2738 — UPnP PlayQueue**

```python
# BEFORE (line 2738):
        except:
            _LOGGER.debug("PlayQueue/QueueContext UPNP error, media not present?: %s", self.entity_id)

# AFTER:
        except Exception as err:
            _LOGGER.debug("PlayQueue/QueueContext UPNP error, media not present?: %s: %s", self.entity_id, err)
```

- [ ] **Step 7: Fix line 2772 — UPnP SetSpotifyPreset (also has unbound `result`)**

Initialize `result = None` before the try block, and fix the bare except:

```python
# BEFORE (lines 2768-2774):
        try:
            media_info = await self._service.action("SetSpotifyPreset").async_call(KeyIndex=int(presetnum))
            _LOGGER.debug("PlayQueue/SetSpotifyPreset for: %s, UPNP media_info:%s", self.entity_id, media_info)
            result = str(media_info.get('Result'))
        except:
            _LOGGER.debug("SetSpotifyPreset UPNP error for: %s, presetnum: %s, result: %s", self.entity_id, presetnum, result)
            return

# AFTER:
        result = None
        try:
            media_info = await self._service.action("SetSpotifyPreset").async_call(KeyIndex=int(presetnum))
            _LOGGER.debug("PlayQueue/SetSpotifyPreset for: %s, UPNP media_info:%s", self.entity_id, media_info)
            result = str(media_info.get('Result'))
        except Exception as err:
            _LOGGER.debug("SetSpotifyPreset UPNP error for: %s, presetnum: %s, result: %s, err: %s", self.entity_id, presetnum, result, err)
            return
```

- [ ] **Step 8: Fix line 2781 — UPnP GetKeyMapping**

```python
# BEFORE (line 2781):
        except:
            _LOGGER.debug("GetKeyMapping UPNP error: %s", self.entity_id)

# AFTER:
        except Exception as err:
            _LOGGER.debug("GetKeyMapping UPNP error: %s: %s", self.entity_id, err)
```

- [ ] **Step 9: Fix lines 2797, 2804, 2811 — XML tree find (three locations)**

All three follow the same pattern. Replace each:

```python
# BEFORE (lines 2797, 2804, 2811 — each one):
        except:

# AFTER (each one):
        except (AttributeError, ET.ParseError):
```

- [ ] **Step 10: Fix line 2820 — UPnP SetKeyMapping**

```python
# BEFORE (line 2820):
        except:
            _LOGGER.debug("SetKeyMapping UPNP error: %s, %s", self.entity_id, preset_map)

# AFTER:
        except Exception as err:
            _LOGGER.debug("SetKeyMapping UPNP error: %s, %s, err: %s", self.entity_id, preset_map, err)
```

- [ ] **Step 11: Verify the file still parses**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/media_player.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 12: Commit**

```bash
git add custom_components/yamaha_soundbar/media_player.py
git commit -m "fix: replace all 12 bare except clauses with typed exceptions

Fixes NameError crash at line 616 where bare except handler referenced
unbound 'error' variable. Also fixes unbound 'result' at line 2772.
All bare except: clauses now catch specific exception types to prevent
swallowing CancelledError and breaking async task cancellation."
```

---

### Task 3: Fix minor bugs — missing await, discarded .replace() results

**Files:**
- Modify: `custom_components/yamaha_soundbar/media_player.py` (lines 803, 1962-1967)

- [ ] **Step 1: Add missing `await` at line 803**

```python
# BEFORE (line 803):
                    self.async_update_via_upnp()

# AFTER:
                    await self.async_update_via_upnp()
```

- [ ] **Step 2: Fix discarded .replace() results at lines 1961-1967**

```python
# BEFORE (lines 1961-1967):
                        if self._media_artist is not None:
                            self._media_artist.replace('/', ' / ')
                            self._media_artist.replace('  ', ' ')

                        if self._media_title is not None:
                            self._media_title.replace('/', ' / ')
                            self._media_title.replace('  ', ' ')

# AFTER:
                        if self._media_artist is not None:
                            self._media_artist = self._media_artist.replace('/', ' / ')
                            self._media_artist = self._media_artist.replace('  ', ' ')

                        if self._media_title is not None:
                            self._media_title = self._media_title.replace('/', ' / ')
                            self._media_title = self._media_title.replace('  ', ' ')
```

- [ ] **Step 3: Verify the file still parses**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/media_player.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add custom_components/yamaha_soundbar/media_player.py
git commit -m "fix: add missing await for UPnP update, fix discarded .replace() results

Web playlist UPnP metadata was never fetched because the coroutine was
created but not awaited. Icecast metadata string replacements were
silently discarded because strings are immutable in Python."
```

---

## Chunk 2: Shared HTTP Client and Blocking I/O

### Task 4: Create shared SSL context and HTTP session

**Files:**
- Modify: `custom_components/yamaha_soundbar/media_player.py` (lines 202-281, 286-399, 407-436)

- [ ] **Step 1: Rework `async_setup_platform` — shared SSL context, session leak fix**

Replace the SSL context creation and initial request section (lines 220-265). The SSL context is created once and passed to the entity. Fix the session leak by initializing `websession = None` and guarding the finally block.

```python
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the YamahaDevice platform."""

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = YamahaData()

    name = config.get(CONF_NAME)
    host = config.get(CONF_HOST)
    sources = config.get(CONF_SOURCES)
    common_sources = config.get(CONF_COMMONSOURCES)
    icecast_metadata = config.get(CONF_ICECAST_METADATA)
    multiroom_wifidirect = config.get(CONF_MULTIROOM_WIFIDIRECT)
    led_off = config.get(CONF_LEDOFF)
    volume_step = config.get(CONF_VOLUME_STEP)
    announce_volume_increase = config.get(CONF_ANNOUNCE_VOLUME_INCREASE)
    lastfm_api_key = config.get(CONF_LASTFM_API_KEY)
    uuid = config.get(CONF_UUID)

    available = True
    state = STATE_IDLE

    # Create SSL context once — reused for all HTTP calls
    loop = asyncio.get_running_loop()
    dirname = os.path.dirname(__file__)
    certpath = os.path.join(dirname, CONF_CERT_FILENAME)
    ssl_ctx = await loop.run_in_executor(None, ssl.create_default_context, ssl.Purpose.SERVER_AUTH)
    await loop.run_in_executor(None, ssl_ctx.load_cert_chain, certpath)
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    initurl = "https://{0}/httpapi.asp?command=getStatusEx".format(host)
    websession = None
    try:
        conn = aiohttp.TCPConnector(ssl_context=ssl_ctx)
        websession = aiohttp.ClientSession(connector=conn)
        async with async_timeout.timeout(10):
            response = await websession.get(initurl)

        if response.status == HTTPStatus.OK:
            data = await response.json(content_type=None)
            _LOGGER.debug("HOST: %s DATA response: %s", host, data)

            try:
                uuid = data['uuid']
            except KeyError:
                pass

            if name is None:
                try:
                    name = data['DeviceName']
                except KeyError:
                    pass

        else:
            _LOGGER.warning(
                "Get Status UUID failed, response code: %s Full message: %s",
                response.status,
                response,
            )
            available = False

    except (asyncio.TimeoutError, aiohttp.ClientError) as error:
        _LOGGER.warning(
            "Failed communicating with YamahaDevice (start) '%s': uuid: %s %s", host, uuid, type(error)
        )
        available = False

    finally:
        if websession is not None:
            await websession.close()

    yamaha = YamahaDevice(name,
                            host,
                            sources,
                            common_sources,
                            icecast_metadata,
                            multiroom_wifidirect,
                            led_off,
                            volume_step,
                            announce_volume_increase,
                            lastfm_api_key,
                            uuid,
                            state,
                            available,
                            ssl_ctx,
                            hass)

    async_add_entities([yamaha])
```

- [ ] **Step 2: Update `YamahaDevice.__init__` — accept ssl_ctx and available params**

Update the constructor signature and body. Add `ssl_ctx` and `available` parameters. Store `ssl_ctx`, set `_attr_available`, add `_session = None`, add `_upnp_last_attempt = None`.

```python
class YamahaDevice(MediaPlayerEntity):
    """YamahaDevice Player Object."""

    def __init__(self,
                 name,
                 host,
                 sources,
                 common_sources,
                 icecast_metadata,
                 multiroom_wifidirect,
                 led_off,
                 volume_step,
                 announce_volume_increase,
                 lastfm_api_key,
                 uuid,
                 state,
                 available,
                 ssl_ctx,
                 hass):
        """Initialize the media player."""
        self._ssl_ctx = ssl_ctx
        self._session = None
        self._attr_available = available
        self._uuid = uuid
        # ... rest of __init__ unchanged, except:
        # Remove: self._state = state  (keep it, but set STATE_IDLE always)
        # The state line stays as-is: self._state = state
```

The key additions at the top of `__init__` body are:
```python
        self._ssl_ctx = ssl_ctx
        self._session = None
        self._attr_available = available
```

And add the UPnP retry tracking:
```python
        self._upnp_last_attempt = None
```
(Add this near line 306 where `self._upnp_device = None` is set)

- [ ] **Step 3: Create shared session in `async_added_to_hass`**

Update `async_added_to_hass` (currently line 397-399) to also create the shared session:

```python
    async def async_added_to_hass(self):
        """Record entity and create shared HTTP session."""
        self.hass.data[DOMAIN].entities.append(self)
        conn = aiohttp.TCPConnector(ssl_context=self._ssl_ctx)
        self._session = async_create_clientsession(self.hass, connector=conn)
```

- [ ] **Step 4: Simplify `async_call_yamaha_httpapi` — use shared session**

Replace the entire method (lines 407-452) with:

```python
    async def async_call_yamaha_httpapi(self, cmd, jsn):
        """Get the latest data from HTTPAPI service."""
        url = "https://{0}/httpapi.asp?command={1}".format(self._host, cmd)

        if self._first_update:
            timeout = 10
        else:
            timeout = API_TIMEOUT

        try:
            async with async_timeout.timeout(timeout):
                response = await self._session.get(url)

        except (asyncio.TimeoutError, aiohttp.ClientError) as error:
            _LOGGER.warning(
                "Failed async communicating with YamahaDevice (httpapi) '%s': %s", self._name, type(error)
            )
            return False

        if response.status == HTTPStatus.OK:
            if jsn:
                data = await response.json(content_type=None)
            else:
                data = await response.text()
                _LOGGER.debug("For: %s  cmd: %s  resp: %s", self._name, cmd, data)
        else:
            _LOGGER.error(
                "For: %s (%s) async get failed, response code: %s Full message: %s",
                self._name,
                self._host,
                response.status,
                response,
            )
            return False

        return data
```

This removes: per-call SSL context creation, per-call connector/session creation, the `finally: await websession.close()` block. Note: non-OK HTTP status returns `False` (not `None`) to maintain compatibility with callers that check `if resp is False:`.

- [ ] **Step 5: Verify the file still parses**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/media_player.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add custom_components/yamaha_soundbar/media_player.py
git commit -m "feat: shared SSL context and HTTP session

Create SSL context once at platform setup, pass to entity. Create a
single aiohttp session in async_added_to_hass via HA's
async_create_clientsession (auto-cleanup on shutdown). Eliminates
per-call SSL handshake and session creation overhead."
```

---

### Task 5: Wrap blocking I/O in executor

**Files:**
- Modify: `custom_components/yamaha_soundbar/media_player.py` (lines 455-485, 1993-2006)

- [ ] **Step 1: Wrap `async_call_yamaha_tcpuart` socket operations in executor**

Extract the synchronous socket work into a helper and call via executor:

```python
    async def async_call_yamaha_tcpuart(self, cmd):
        """Get the latest data from TCP UART service."""
        _LOGGER.debug("For: %s Sending to %s TCP UART command: %s", self._name, self._host, cmd)
        try:
            data = await self.hass.async_add_executor_job(
                self._call_yamaha_tcpuart_sync, cmd
            )
        except socket.error as ex:
            _LOGGER.debug("For: %s Error sending TCP UART command: %s with %s", self._name, cmd, ex)
            data = None

        return data

    def _call_yamaha_tcpuart_sync(self, cmd):
        """Synchronous TCP UART communication (runs in executor)."""
        LENC = format(len(cmd), '02x')
        HED1 = '18 96 18 20 '
        HED2 = ' 00 00 00 c1 02 00 00 00 00 00 00 00 00 00 00 '
        CMHX = ' '.join(hex(ord(c))[2:] for c in cmd)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(API_TIMEOUT)
            s.connect((self._host, TCPPORT))
            s.send(bytes.fromhex(HED1 + LENC + HED2 + CMHX))
            data = str(repr(s.recv(1024))).encode().decode("unicode-escape")

        pos = data.find("AXX")
        if pos == -1:
            pos = data.find("MCU")

        data = data[pos:(len(data)-2)]
        _LOGGER.debug("For: %s Received from %s TCP UART command result: %s", self._name, self._host, data)
        return data
```

- [ ] **Step 2: Wrap `async_detect_stream_url_redirection` blocking `requests.head()` in executor**

Extract the synchronous redirect-following loop into a helper:

```python
    async def async_detect_stream_url_redirection(self, uri):
        """Detect URL redirections."""
        if uri.find('tts_proxy') != -1 or self._announce:
            return uri
        _LOGGER.debug('For: %s detect URI redirect-from:   %s', self._name, uri)
        try:
            check_uri = await self.hass.async_add_executor_job(
                self._detect_redirect_sync, uri
            )
        except (requests.RequestException, OSError, ValueError):
            check_uri = uri

        _LOGGER.debug('For: %s detect URI redirect - to:   %s', self._name, check_uri)
        return check_uri

    def _detect_redirect_sync(self, uri):
        """Synchronous redirect detection (runs in executor)."""
        redirect_detect = True
        check_uri = uri
        while redirect_detect:
            response_location = requests.head(
                check_uri,
                allow_redirects=False,
                headers={'User-Agent': 'VLC/3.0.16 LibVLC/3.0.16'}
            )
            if response_location.status_code in [301, 302, 303, 307, 308] and 'Location' in response_location.headers:
                check_uri = response_location.headers['Location']
            else:
                redirect_detect = False
        return check_uri
```

- [ ] **Step 3: Verify the file still parses**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/media_player.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add custom_components/yamaha_soundbar/media_player.py
git commit -m "fix: wrap blocking TCP socket and requests.head() in executor

async_call_yamaha_tcpuart was blocking the event loop with synchronous
socket operations. async_detect_stream_url_redirection was blocking with
synchronous requests.head(). Both now run in the executor thread pool."
```

---

## Chunk 3: Entity Availability and UPnP Caching

### Task 6: Migrate to proper entity availability pattern

**Files:**
- Modify: `custom_components/yamaha_soundbar/media_player.py` (13 locations)

This task replaces all `STATE_UNAVAILABLE` usage with the `_attr_available` pattern. The `_attr_available` field and constructor changes were already done in Task 4. This task handles all remaining references.

- [ ] **Step 1: Fix `async_get_status` (line 492)**

```python
# BEFORE (line 492):
            self._state = STATE_UNAVAILABLE

# AFTER:
            self._attr_available = False
```

- [ ] **Step 2: Fix `async_update` first-update check (line 567)**

```python
# BEFORE (line 567):
            if self._first_update or (self._state == STATE_UNAVAILABLE or self._multiroom_wifidirect):

# AFTER:
            if self._first_update or (not self.available or self._multiroom_wifidirect):
```

- [ ] **Step 3: Fix `async_update` recovery (line 572)**

```python
# BEFORE (line 572):
                        if self._state == STATE_UNAVAILABLE:
                            self._state = STATE_IDLE

# AFTER:
                        if not self.available:
                            self._attr_available = True
                            self._state = STATE_IDLE
```

- [ ] **Step 4: Fix `icon` property (line 884)**

Remove `STATE_UNAVAILABLE` from the list (unavailable entities won't have their icon queried):

```python
# BEFORE (line 884):
        if self._state in [STATE_PAUSED, STATE_UNAVAILABLE, STATE_IDLE, STATE_UNKNOWN]:

# AFTER:
        if self._state in [STATE_PAUSED, STATE_IDLE, STATE_UNKNOWN]:
```

- [ ] **Step 5: Fix `media_position` property (line 1028)**

```python
# BEFORE (line 1028):
        if (self._playing_localfile or self._playing_spotify or self._slave_mode or self._playing_mediabrowser or self._playing_mass) and self._state != STATE_UNAVAILABLE:

# AFTER:
        if (self._playing_localfile or self._playing_spotify or self._slave_mode or self._playing_mediabrowser or self._playing_mass) and self.available:
```

- [ ] **Step 6: Fix `media_duration` property (line 1036)**

```python
# BEFORE (line 1036):
        if (self._playing_localfile or self._playing_spotify or self._slave_mode or self._playing_mediabrowser or self._playing_mass) and self._state != STATE_UNAVAILABLE:

# AFTER:
        if (self._playing_localfile or self._playing_spotify or self._slave_mode or self._playing_mediabrowser or self._playing_mass) and self.available:
```

- [ ] **Step 7: Fix `extra_state_attributes` (line 1177)**

```python
# BEFORE (line 1177):
        if self._state != STATE_UNAVAILABLE:

# AFTER:
        if self.available:
```

- [ ] **Step 8: Fix `async_join` guard (line 2237)**

```python
# BEFORE (line 2237):
        if self._state == STATE_UNAVAILABLE:
            return

# AFTER:
        if not self.available:
            return
```

- [ ] **Step 9: Fix `async_unjoin_all` guard (line 2298)**

```python
# BEFORE (line 2298):
        if self._state == STATE_UNAVAILABLE:
            return

# AFTER:
        if not self.available:
            return
```

- [ ] **Step 10: Fix `async_snapshot` guard (line 2440)**

```python
# BEFORE (line 2440):
        if self._state == STATE_UNAVAILABLE:
            return

# AFTER:
        if not self.available:
            return
```

- [ ] **Step 11: Fix `async_restore` guard (line 2515)**

```python
# BEFORE (line 2515):
        if self._state == STATE_UNAVAILABLE:
            return

# AFTER:
        if not self.available:
            return
```

- [ ] **Step 12: Remove STATE_UNAVAILABLE import**

Now that all references are replaced, remove `STATE_UNAVAILABLE` from the import at line 73:

```python
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_DEVICE_CLASS,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    STATE_IDLE,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_UNKNOWN,
)
```

- [ ] **Step 13: Verify no remaining STATE_UNAVAILABLE references**

Run: `grep -n "STATE_UNAVAILABLE" custom_components/yamaha_soundbar/media_player.py`

Expected: No output (all references removed including the import)

- [ ] **Step 14: Verify the file still parses**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/media_player.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 15: Commit**

```bash
git add custom_components/yamaha_soundbar/media_player.py
git commit -m "fix: migrate to proper HA entity availability pattern

Replace all self._state = STATE_UNAVAILABLE with self._attr_available.
HA's Entity base class automatically wires _attr_available to the
available property. Removes STATE_UNAVAILABLE import entirely."
```

---

### Task 7: Add UPnP device caching with retry backoff

**Files:**
- Modify: `custom_components/yamaha_soundbar/media_player.py` (lines 612-619, ~492-510)

- [ ] **Step 1: Add UPnP retry backoff to device creation block**

Replace the UPnP creation block (lines 612-619) with backoff logic:

```python
                        if self._upnp_device is None:
                            should_retry = (
                                self._upnp_last_attempt is None
                                or utcnow() >= (self._upnp_last_attempt + UPNP_RETRY_INTERVAL)
                            )
                            if should_retry:
                                url = "http://{0}:49152/description.xml".format(self._host)
                                try:
                                    self._upnp_device = await self._factory.async_create_device(url)
                                    self._upnp_last_attempt = None
                                except Exception as err:
                                    self._upnp_last_attempt = utcnow()
                                    _LOGGER.warning(
                                        "Failed communicating with Yamaha (UPnP) '%s': %s", self._name, err
                                    )
```

- [ ] **Step 2: Reset UPnP device when entity becomes unavailable**

In `async_get_status` (around line 492-510), where the entity is marked unavailable, also reset UPnP state to force re-creation on reconnect:

```python
            self._upnp_device = None
            self._upnp_last_attempt = None
```

These two lines should already be present (line 509 has `self._upnp_device = None`). Ensure `self._upnp_last_attempt = None` is added after it.

- [ ] **Step 3: Verify the file still parses**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/media_player.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add custom_components/yamaha_soundbar/media_player.py
git commit -m "fix: cache UPnP device with 60s retry backoff on failure

UPnP device was re-created every poll cycle when None, hammering the
soundbar. Now caches successfully and retries at most once per 60s on
failure. Resets on full unavailability to allow reconnection."
```

---

### Task 8: Final verification

**Files:**
- Verify: `custom_components/yamaha_soundbar/media_player.py`

- [ ] **Step 1: Verify no bare except clauses remain**

Run: `grep -n "except:" custom_components/yamaha_soundbar/media_player.py | grep -v "except (\\|except [A-Z]\\|except a"`

Expected: No output

- [ ] **Step 2: Verify no STATE_UNAVAILABLE references remain**

Run: `grep -n "STATE_UNAVAILABLE" custom_components/yamaha_soundbar/media_player.py`

Expected: No output

- [ ] **Step 3: Verify no asyncio.get_event_loop() calls remain**

Run: `grep -n "get_event_loop" custom_components/yamaha_soundbar/media_player.py`

Expected: No output

- [ ] **Step 4: Verify file parses cleanly**

Run: `python3 -c "import ast; ast.parse(open('custom_components/yamaha_soundbar/media_player.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 5: Review the complete diff**

Run: `git diff 2aa0a41 -- custom_components/yamaha_soundbar/media_player.py`

(Commit `2aa0a41` is the last commit before implementation began)

Verify:
- `SCAN_INTERVAL` is `timedelta(seconds=10)`
- `API_TIMEOUT` is `5`
- `UPNP_TIMEOUT` is `5`
- `PARALLEL_UPDATES = 1` is present
- No bare `except:` clauses
- No `STATE_UNAVAILABLE` references
- `self._session` is used in `async_call_yamaha_httpapi`
- `async_create_clientsession` is used in `async_added_to_hass`
- Socket operations are in `_call_yamaha_tcpuart_sync` (executor)
- `requests.head` is in `_detect_redirect_sync` (executor)
- UPnP creation has backoff logic
