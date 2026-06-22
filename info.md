# Yamaha Soundbar

Control Yamaha Linkplay-based soundbars from Home Assistant — playback, volume, source switching, sound modes, Yamaha audio settings (subwoofer, surround, clear voice, bass extension), multiroom and TTS.

A personal, maintained fork of [`osk2/yamaha-soundbar`](https://github.com/osk2/yamaha-soundbar), rebuilt around a UI config flow + `DataUpdateCoordinator` with stability and correctness fixes.

**Tested on** YAS-109 and YAS-209; any Linkplay A118-based Yamaha soundbar should work (ATS-1090, ATS-2090, SR-X40A, SR-X50A, ATS-X500).

## Setup

1. Download via HACS and **restart Home Assistant**.
2. **Settings → Devices & Services → Add Integration → Yamaha Soundbar**.
3. Enter the soundbar's **IP address** (static IP / DHCP reservation recommended).

There is **no YAML configuration** — everything is configured in the UI. After setup, use **Configure** to set the volume step, TTS volume boost, Icecast metadata mode, and LED-off option.

## Entities

A single device with: `media_player` (transport, volume, source, sound mode, multiroom), **Sound program** & **Preset** selects, a **Subwoofer volume** number, **3D surround** / **Clear voice** / **Bass extension** / **LED** switches, and a **WiFi channel** sensor. Multiroom and TTS snapshot/restore are exposed as services.
