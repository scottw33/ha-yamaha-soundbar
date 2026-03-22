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
