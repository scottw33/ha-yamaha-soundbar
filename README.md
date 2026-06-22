[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# Yamaha Soundbar (Home Assistant)

Control Yamaha Linkplay-based soundbars from Home Assistant — playback, volume, source switching, sound modes, the Yamaha-specific audio settings (subwoofer, surround, clear voice, bass extension), multiroom grouping and TTS.

This is a personal, actively-maintained fork of [`osk2/yamaha-soundbar`](https://github.com/osk2/yamaha-soundbar), rebuilt around Home Assistant's modern integration patterns (UI config flow + `DataUpdateCoordinator`) with a number of stability and correctness fixes. See [Changes in this fork](#changes-in-this-fork).

## Supported devices

Tested on the **YAS-109** and **YAS-209**. Any Yamaha soundbar built on the Linkplay A118 module should work, including ATS-1090, ATS-2090, SR-X40A, SR-X50A and ATS-X500. If you have another model, please open an issue with the result — working or not — so the list can be updated.

## What you get

Adding the integration creates one device with these entities:

| Platform | Entities |
| --- | --- |
| `media_player` | Playback transport, volume, mute, source selection, sound mode (EQ), shuffle/repeat, multiroom |
| `select` | **Sound program**, **Preset** |
| `number` | **Subwoofer volume** |
| `switch` | **3D surround**, **Clear voice**, **Bass extension**, **LED** |
| `sensor` | **WiFi channel** |

### Services

`yamaha_soundbar.join` · `yamaha_soundbar.unjoin` — multiroom grouping
`yamaha_soundbar.snapshot` · `yamaha_soundbar.restore` — save/restore state around TTS
`yamaha_soundbar.play_track` — play a track by (partial) name from the device's track list

See the service descriptions in Home Assistant (Developer Tools → Actions) for field details.

## Installation (HACS)

This repository is a HACS **custom repository**.

1. In HACS, open the three-dot menu (top right) → **Custom repositories**.
2. Add `https://github.com/scottw33/ha-yamaha-soundbar` with category **Integration**.
3. Find **Yamaha Soundbar** in HACS and **Download** it.
4. **Restart Home Assistant.**

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=scottw33&repository=ha-yamaha-soundbar&category=integration)

<details>
<summary>Manual installation (without HACS)</summary>

Copy `custom_components/yamaha_soundbar/` into your `<config>/custom_components/` directory, then restart Home Assistant. Note: HACS is the recommended path so you get update notifications.
</details>

## Configuration

Setup is done entirely through the UI — there is **no YAML configuration**.

1. **Settings → Devices & Services → Add Integration → Yamaha Soundbar**.
2. Enter the soundbar's **IP address** (a static IP / DHCP reservation is strongly recommended).

The integration connects to the device, reads its UUID, and creates the entities above.

### Options

After setup, use **Configure** on the integration to adjust:

| Option | Description |
| --- | --- |
| **Volume step** | Step size (1–25) for the volume up/down buttons |
| **TTS volume boost** | Volume increase (0–50) applied when announcing TTS |
| **Icecast metadata mode** | `Off`, `StationName`, or `StationNameSongTitle` |
| **Turn off LED** | Keep the soundbar's LED off |

## Updating

Because it's installed via HACS, updates arrive in the HACS UI whenever a new release is published — **Update**, then restart Home Assistant.

## Changes in this fork

- Rebuilt as a config-flow + `DataUpdateCoordinator` integration (v4.0.0).
- **Poll resilience:** a single transient request failure no longer flips the entity to *unavailable* or logs an error; it retries once and only reports unavailable after several consecutive failed polls.
- **No event-loop blocking:** the SSL context is built in an executor (previously caused repeated blocking-I/O warnings on every setup).
- **Volume mapping:** the device's 0–100 range maps 1:1 to Home Assistant's 0–100% slider for single-unit steps, with the rounding corrected so a level can't land one step low.

## Credits & license

Based on [`osk2/yamaha-soundbar`](https://github.com/osk2/yamaha-soundbar) (MIT). All credit to the original authors and contributors. This fork is maintained for personal use and shared as-is.
