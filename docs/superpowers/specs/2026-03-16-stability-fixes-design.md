# Yamaha Soundbar Integration — Stability Fixes Design

**Date:** 2026-03-16
**Approach:** B — Fix bugs + proper HTTP client & error handling
**Scope:** Eliminate constant errors in HA logs; make the integration stable and ready for future TTS/settings work

## Context

The integration produces three classes of errors on HA 2026.3.1:

1. **NameError** — bare `except:` at line 616 references unbound variable `error`, crashing the error handler itself (~7,109 occurrences)
2. **Timeout cascade** — 3s `SCAN_INTERVAL` with 2s `API_TIMEOUT`, sequential network calls stack up and exceed the update interval (~24,753 occurrences of "took longer than scheduled")
3. **httpapi TimeoutError** — device timeouts logged as warnings (~4,324 occurrences)

Root causes:
- A new `aiohttp.ClientSession`, `TCPConnector`, and `ssl.SSLContext` created per HTTP call (every 3s)
- UPnP device re-created every poll cycle when `None`
- No backoff on failures
- Bare `except:` clauses swallowing cancellation errors and referencing wrong variable names
- Missing `await` on async calls
- Blocking synchronous I/O on the event loop (TCP socket, `requests.head()`, `urllib`)
- Entity availability managed by setting `self._state = STATE_UNAVAILABLE` instead of the proper `available` property

## Design

### 1. Shared HTTP Client

**Current:** `async_call_yamaha_httpapi` creates a new SSL context (via `run_in_executor`), connector, and session on every call, then closes the session afterward.

**Change:**
- Create the SSL context once in `async_setup_platform`, before entity construction, using `asyncio.get_running_loop()` (not deprecated `get_event_loop()`)
- Pass the SSL context into `YamahaDevice.__init__`
- Use HA's `async_create_clientsession(hass, connector=TCPConnector(ssl=ssl_ctx))` to create a session tied to HA's lifecycle — this handles cleanup automatically on shutdown, eliminating the need for manual `async_will_remove_from_hass` session cleanup
- Store the session as `self._session`
- Create the session in `async_added_to_hass` (deterministic, single location)
- `async_call_yamaha_httpapi` uses `self._session` directly — no per-call SSL/connector/session creation
- Also fix session leak in `async_setup_platform`: initialize `websession = None` before `try` and guard `finally` with `if websession is not None`

**Result:** Eliminates ~60 calls/minute worth of SSL handshakes, connector creation, and session lifecycle overhead.

### 2. UPnP Device Caching

**Current:** Line 612-619 checks `if self._upnp_device is None` every update cycle and attempts to create it. The bare `except:` handler references undefined `error`, causing a `NameError`.

**Change:**
- Create the UPnP device once during initial setup (inside `async_update` on first success)
- Cache it in `self._upnp_device` — do not re-create on every cycle
- If creation fails, record `self._upnp_last_attempt = utcnow()` and skip retries for 60 seconds
- Only set `self._upnp_device = None` when the entity becomes fully unavailable (forcing re-creation on reconnect)
- Fix the except clause: `except Exception as err:` with correct variable reference

**Result:** UPnP creation goes from every-3-seconds-on-failure to once-per-minute-on-failure, once-total-on-success.

### 3. Polling Intervals & Timeouts

**Current:** `SCAN_INTERVAL = 3s`, `API_TIMEOUT = 2s`, `UPNP_TIMEOUT = 2s`. No `PARALLEL_UPDATES` set.

**Change:**
- `SCAN_INTERVAL = timedelta(seconds=10)` — HA docs specify 5s minimum for local polling; 10s is appropriate for volume-control-focused use
- `API_TIMEOUT = 5` — enough headroom for the soundbar's embedded web server
- `UPNP_TIMEOUT = 5` — match API timeout
- `PARALLEL_UPDATES = 1` — serialize updates per entity to prevent stacking

**Behavioral note:** Volume changes from the HA UI will take up to 10s to reflect back in the state (previously ~3s). For a volume-control-focused use case this is acceptable. Service calls (play, join, etc.) may queue behind an in-flight update, adding slight latency to user-initiated actions.

**Result:** Updates no longer exceed their interval. Single update makes 1-2 network calls at 5s timeout max = 10s worst case, well within the 10s interval with `PARALLEL_UPDATES = 1` preventing overlap.

### 4. Entity Availability Pattern

**Current:** Sets `self._state = STATE_UNAVAILABLE` when the device is unreachable. This conflicts with HA's entity lifecycle management.

**Change:**
- Set `self._attr_available = True` in `__init__` (HA's `Entity` base class automatically wires `_attr_available` to the `available` property — no override needed)
- When `async_get_status` detects the device is unreachable (httpapi returns `False`), set `self._attr_available = False`
- When httpapi succeeds after being unavailable, set `self._attr_available = True` and `self._state = STATE_IDLE`
- Remove all direct `self._state = STATE_UNAVAILABLE` assignments
- Replace all `STATE_UNAVAILABLE` checks with `not self.available` at these locations:
  - Line 256: `async_setup_platform` initial state → set `self._attr_available = False` instead
  - Line 262: `async_setup_platform` exception → set `self._attr_available = False` instead
  - Line 492: `async_get_status` unavailable → `self._attr_available = False` (remove `self._state = STATE_UNAVAILABLE`)
  - Line 567: `async_update` first update check → `not self.available` instead of `self._state == STATE_UNAVAILABLE`
  - Line 572: `async_update` recovery → `not self.available`
  - Line 884: `icon` property → `not self.available`
  - Line 1028: `media_position` property → check `self.available`
  - Line 1036: `media_position_updated_at` → check `self.available`
  - Line 1177: `async_set_volume_level` guard → `not self.available`
  - Line 2237: `async_join` guard → `not self.available`
  - Line 2298: `async_unjoin_all` guard → `not self.available`
  - Line 2440: `async_snapshot` guard → `not self.available`
  - Line 2515: `async_restore` guard → `not self.available`
- Remove the `STATE_UNAVAILABLE` import once no longer used

**Result:** HA correctly tracks entity availability. The entity shows as "unavailable" in the UI without corrupting the state machine. Recovery is clean.

### 5. Bare Except Cleanup

**Current:** 12 bare `except:` clauses throughout the file. These swallow `CancelledError`, `KeyboardInterrupt`, and `SystemExit`, which breaks async task cancellation and HA shutdown.

**Change:** Replace each bare `except:` with typed exceptions:

| Location | Context | Exception Type |
|----------|---------|---------------|
| Line 478 | Socket close | `except OSError:` |
| Line 616 | UPnP device creation | `except Exception as err:` |
| Line 1889 | urllib icecast request | `except (urllib.error.URLError, OSError) as err:` |
| Line 2005 | URI redirect detection | `except (requests.RequestException, OSError, ValueError) as err:` |
| Line 2678 | UPnP GetMediaInfo | `except Exception as err:` |
| Line 2738 | UPnP PlayQueue | `except Exception as err:` |
| Line 2772 | UPnP SetSpotifyPreset | `except Exception as err:` |
| Line 2781 | UPnP GetKeyMapping | `except Exception as err:` |
| Line 2797 | XML tree find | `except (AttributeError, ET.ParseError):` |
| Line 2804 | XML tree find | `except (AttributeError, ET.ParseError):` |
| Line 2811 | XML tree find | `except (AttributeError, ET.ParseError):` |
| Line 2820 | UPnP SetKeyMapping | `except Exception as err:` |

Additional NameError fix at line 2772: initialize `result = None` before the try block to prevent unbound variable reference in the except handler.

Each handler that currently references undefined variables will be corrected to use the bound exception name.

**Result:** Async cancellation works correctly. Errors are properly typed and logged. No more `NameError` from unbound exception variables.

### 6. Async & Blocking I/O Cleanup

**Current:**
- Line 803: `self.async_update_via_upnp()` called without `await` — coroutine created but never executed
- Lines 221, 417: `asyncio.get_event_loop()` — deprecated since Python 3.10
- Lines 464-468: `async_call_yamaha_tcpuart` uses synchronous `socket` operations (`connect`, `send`, `recv`) directly on the event loop, blocking for up to `API_TIMEOUT` seconds
- Line 1997: `async_detect_stream_url_redirection` uses synchronous `requests.head()` on the event loop

**Change:**
- Add `await` to line 803: `await self.async_update_via_upnp()`
- In `async_setup_platform`: SSL context creation uses `asyncio.get_running_loop()` instead of `get_event_loop()`
- In `async_call_yamaha_httpapi`: the `get_event_loop()` and `run_in_executor` calls for SSL are eliminated entirely (SSL context is now created once at setup per Section 1)
- In `async_call_yamaha_tcpuart`: wrap the synchronous socket operations in `await self.hass.async_add_executor_job(...)` to avoid blocking the event loop
- In `async_detect_stream_url_redirection`: wrap `requests.head()` in `await self.hass.async_add_executor_job(...)` to avoid blocking the event loop

**Result:** Web playlist UPnP metadata actually gets fetched. No deprecation warnings. Event loop is never blocked by synchronous I/O.

### 7. Minor Bug Fixes

Additional pre-existing bugs to fix alongside the stability work:

- **Lines 1962-1963, 1966-1967:** `.replace()` results discarded (strings are immutable). Fix: `self._media_artist = self._media_artist.replace('/', ' / ')` etc.
- **Line 9:** Remove unused `CancelledError` import
- **Line 803:** Missing `await` (covered in Section 6)

## Files Modified

| File | Changes |
|------|---------|
| `media_player.py` | All seven sections above |
| `__init__.py` | No changes needed |
| `manifest.json` | No changes needed |
| `services.yaml` | No changes needed |

## What This Does NOT Change

- No feature changes — all existing functionality preserved
- No config flow migration — stays YAML-based
- No DataUpdateCoordinator migration — stays with `async_update` pattern
- No new files or dependencies
- No changes to service registration or schema

## Future Work (Out of Scope)

- TTS functionality improvements
- Exposing additional sound settings as entities
- Config flow migration
- DataUpdateCoordinator migration
- Test suite creation
