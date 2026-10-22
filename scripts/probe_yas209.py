#!/usr/bin/env python3
"""Night-safe probe of a Yamaha YAS-209 (Linkplay A118) soundbar.

Answers the open questions from the integration research:
  1. What YAMAHA_DATA_GET returns (keys, sound program values, power saving)
  2. Which "power saving" value means standby
  3. Linkplay `vol` vs Yamaha `Master volume` (remote + API changes)
  4. Real subwoofer volume range
  5. Whether a correctly checksummed TCP 8899 LED command works
  6. Which sound program strings the bar accepts

Volume safety: the script never sets volume above the level it finds at the
start. The only volume it sends is a step DOWN and then back to the start
level. Subwoofer is only stepped DOWN (quieter). Every changed setting is
restored at the end, including on Ctrl-C, and a final guard pulls volume
back to the starting level if anything left it higher.

Usage:  python3 probe_yas209.py [IP]   (default 192.168.1.250)
Cert:   client.pem from custom_components/yamaha_soundbar, found relative to
        this script, or set YAS_CERT=/path/to/client.pem
Output: printed and saved to ~/yas209_probe_<timestamp>.txt
"""
import json
import os
import socket
import ssl
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.250"
CERT = os.environ.get("YAS_CERT") or str(
    Path(__file__).resolve().parent.parent
    / "custom_components" / "yamaha_soundbar" / "client.pem"
)
OUT = Path.home() / f"yas209_probe_{datetime.now():%Y%m%d_%H%M%S}.txt"
_log = open(OUT, "w")


def log(msg=""):
    print(msg)
    _log.write(f"{msg}\n")
    _log.flush()


def ask(prompt):
    ans = input(f"\n>>> {prompt} ").strip()
    _log.write(f">>> {prompt} {ans}\n")
    return ans


_ctx = ssl.create_default_context()
_ctx.load_cert_chain(CERT)
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def api(cmd):
    url = f"https://{HOST}/httpapi.asp?command={cmd}"
    with urllib.request.urlopen(url, context=_ctx, timeout=8) as r:
        body = r.read().decode(errors="replace")
    try:
        return json.loads(body)
    except ValueError:
        return body


def ydata():
    return api("YAMAHA_DATA_GET")


def yset(key, value):
    k = key.replace(" ", "%20")
    v = str(value).replace(" ", "%20")
    return api(f"YAMAHA_DATA_SET:{{%22{k}%22:%22{v}%22}}")


def vol():
    return int(api("getPlayerStatus").get("vol", -1))


def tcp(cmd):
    """Send a TCP 8899 passthrough command with a correct checksum."""
    payload = cmd.encode()
    packet = (
        bytes.fromhex("18961820")
        + len(payload).to_bytes(4, "little")
        + (sum(payload) & 0xFFFFFFFF).to_bytes(4, "little")
        + bytes(8)
        + payload
    )
    with socket.create_connection((HOST, 8899), timeout=3) as s:
        s.sendall(packet)
        try:
            return repr(s.recv(1024))
        except socket.timeout:
            return "(no reply)"


# Settings to put back at the end: key -> original value
restore = {}
start_vol = None


def section(title):
    log(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main():
    global start_vol
    log(f"probe of {HOST} at {datetime.now()}")
    log(f"cert: {CERT}")

    # ---- 1. Read-only snapshot -------------------------------------------
    section("1. Read-only snapshot")
    d = ydata()
    log("YAMAHA_DATA_GET:\n" + json.dumps(d, indent=2))
    ps = api("getPlayerStatus")
    log("getPlayerStatus:\n" + json.dumps(ps, indent=2))
    sx = api("getStatusEx")
    log("getStatusEx:\n" + json.dumps(sx, indent=2))
    start_vol = int(ps.get("vol", 0))
    log(f"\nStarting Linkplay vol = {start_vol}, Master volume = {d.get('Master volume')}")
    log(f"plm_support = {sx.get('plm_support')}  group = {sx.get('group')}")

    # ---- 2. Power saving -------------------------------------------------
    section("2. Power saving (standby) semantics")
    ps0 = d.get("power saving")
    if ps0 not in ("0", "1"):
        log(f"'power saving' is {ps0!r}, skipping")
    elif ask("Toggle power to test standby? Bar may go off for ~10s. [y/N]").lower() == "y":
        other = "0" if ps0 == "1" else "1"
        restore["power saving"] = ps0
        log(f"power saving was {ps0}; setting {other}: {yset('power saving', other)}")
        time.sleep(5)
        log(f"read back: {ydata().get('power saving')}")
        ask(f"With power saving={other}, is the bar ON or in STANDBY? (type on/standby)")
        log(f"restoring power saving={ps0}: {yset('power saving', ps0)}")
        restore.pop("power saving")
        time.sleep(5)
        log(f"read back: {ydata().get('power saving')}, vol={vol()}")
        ask(f"With power saving={ps0}, is the bar ON or in STANDBY? (type on/standby)")

    # ---- 3. Volume: Linkplay vol vs Master volume ------------------------
    section("3. Linkplay vol vs Yamaha Master volume")
    log(f"before: vol={vol()} Master volume={ydata().get('Master volume')}")
    if ask("Press VOL DOWN twice on the YAMAHA remote, then Enter (s to skip).") != "s":
        time.sleep(2)
        log(f"after Yamaha remote -2: vol={vol()} Master volume={ydata().get('Master volume')}")
    if ask("Press VOL DOWN once on the TV remote (HDMI-CEC), then Enter (s to skip).") != "s":
        time.sleep(2)
        log(f"after TV remote -1: vol={vol()} Master volume={ydata().get('Master volume')}")
    if ask("Press VOL UP on the remote(s) to get back to where you were, then Enter.") is not None:
        time.sleep(2)
        log(f"after restoring by remote: vol={vol()} Master volume={ydata().get('Master volume')}")

    # API-driven change: only ever downward, then back to the start level
    cur = vol()
    target = max(0, min(cur, start_vol) - 2)
    log(f"\nAPI test: setPlayerCmd:vol:{target} (2 below current)")
    api(f"setPlayerCmd:vol:{target}")
    time.sleep(2)
    log(f"after API set: vol={vol()} Master volume={ydata().get('Master volume')}")
    back = min(cur, start_vol)
    api(f"setPlayerCmd:vol:{back}")
    time.sleep(2)
    log(f"back to {back}: vol={vol()} Master volume={ydata().get('Master volume')}")

    # ---- 4. Subwoofer range (quieter direction only) ---------------------
    section("4. Subwoofer volume range (stepping DOWN only)")
    sw0 = ydata().get("subwoofer volume")
    restore["subwoofer volume"] = sw0
    log(f"subwoofer volume starts at {sw0}")
    for v in [x for x in (-4, -5, -6, -8, -12) if x < int(sw0)]:
        r = yset("subwoofer volume", v)
        time.sleep(1)
        log(f"set {v}: reply={r!r} read back={ydata().get('subwoofer volume')}")
    log(f"restoring subwoofer {sw0}: {yset('subwoofer volume', sw0)}")
    time.sleep(1)
    log(f"read back: {ydata().get('subwoofer volume')}")
    restore.pop("subwoofer volume")

    # ---- 5. Sound program strings ----------------------------------------
    section("5. Sound program values")
    sp0 = ydata().get("sound program")
    restore["sound program"] = sp0
    log(f"sound program starts at {sp0!r}")
    for v in ("sport", "sports", "tv", "tv program", "movie", "music", "game", "stereo"):
        r = yset("sound program", v)
        time.sleep(1)
        log(f"set {v!r}: reply={r!r} read back={ydata().get('sound program')!r}")
    log(f"restoring {sp0!r}: {yset('sound program', sp0)}")
    time.sleep(1)
    log(f"read back: {ydata().get('sound program')!r}")
    restore.pop("sound program")

    # ---- 6. LED via TCP 8899 with a correct checksum ---------------------
    section("6. LED over TCP 8899 (correct checksum)")
    log(f"Dimmer before: {ydata().get('Dimmer')}")
    log(f"LED:0 reply: {tcp('MCU+PAS+RAKOIT:LED:0&')}")
    time.sleep(2)
    log(f"Dimmer after LED:0: {ydata().get('Dimmer')}")
    ask("Did the front LEDs go off? (y/n)")
    log(f"LED:1 reply: {tcp('MCU+PAS+RAKOIT:LED:1&')}")
    time.sleep(2)
    log(f"Dimmer after LED:1: {ydata().get('Dimmer')}")
    ask("Did the front LEDs come back? (y/n)")


def cleanup():
    for key, value in restore.items():
        try:
            log(f"cleanup: restoring {key}={value}: {yset(key, value)}")
        except Exception as err:  # noqa: BLE001
            log(f"cleanup: FAILED to restore {key}: {err}")
    if start_vol is not None:
        try:
            now = vol()
            if now > start_vol:
                log(f"cleanup: vol {now} > start {start_vol}, pulling back down")
                api(f"setPlayerCmd:vol:{start_vol}")
            log(f"final vol={vol()} (start was {start_vol})")
        except Exception as err:  # noqa: BLE001
            log(f"cleanup: could not check volume: {err}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\ninterrupted")
    finally:
        cleanup()
        log(f"\nSaved to {OUT}")
        _log.close()
