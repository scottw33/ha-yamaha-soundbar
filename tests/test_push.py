"""End-to-end check of UPnP push: fake YAS-209 renderer + real coordinator."""
import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from aiohttp import web
import pytest

from custom_components.yamaha_soundbar.coordinator import YamahaCoordinator

DESC = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0"><specVersion><major>1</major><minor>0</minor></specVersion>
<device><deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType><friendlyName>YAS_209</friendlyName>
<manufacturer>Yamaha</manufacturer><modelName>YAS-209</modelName><UDN>uuid:FFB8F002-8DB7-82D1-C580-978DFFB8F002</UDN>
<serviceList><service><serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>
<serviceId>urn:upnp-org:serviceId:RenderingControl</serviceId><SCPDURL>/rc.xml</SCPDURL>
<controlURL>/rc/ctrl</controlURL><eventSubURL>/rc/evt</eventSubURL></service>
<service><serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
<serviceId>urn:upnp-org:serviceId:AVTransport</serviceId><SCPDURL>/avt.xml</SCPDURL>
<controlURL>/avt/ctrl</controlURL><eventSubURL>/avt/evt</eventSubURL></service></serviceList></device></root>"""

SCPD = """<?xml version="1.0"?>
<scpd xmlns="urn:schemas-upnp-org:service-1-0"><specVersion><major>1</major><minor>0</minor></specVersion>
<actionList><action><name>GetVolume</name><argumentList>
<argument><name>InstanceID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_InstanceID</relatedStateVariable></argument>
<argument><name>Channel</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Channel</relatedStateVariable></argument>
<argument><name>CurrentVolume</name><direction>out</direction><relatedStateVariable>Volume</relatedStateVariable></argument>
</argumentList></action></actionList>
<serviceStateTable>
<stateVariable sendEvents="yes"><name>LastChange</name><dataType>string</dataType></stateVariable>
<stateVariable sendEvents="no"><name>Volume</name><dataType>ui2</dataType><allowedValueRange><minimum>0</minimum><maximum>100</maximum><step>1</step></allowedValueRange></stateVariable>
<stateVariable sendEvents="no"><name>Mute</name><dataType>boolean</dataType></stateVariable>
<stateVariable sendEvents="no"><name>A_ARG_TYPE_InstanceID</name><dataType>ui4</dataType></stateVariable>
<stateVariable sendEvents="no"><name>A_ARG_TYPE_Channel</name><dataType>string</dataType></stateVariable>
</serviceStateTable></scpd>"""

# The real bar's AVTransport events break its own allowed values, so the
# coordinator must never subscribe to it.
AVT_SCPD = """<?xml version="1.0"?>
<scpd xmlns="urn:schemas-upnp-org:service-1-0"><specVersion><major>1</major><minor>0</minor></specVersion>
<actionList/><serviceStateTable>
<stateVariable sendEvents="yes"><name>LastChange</name><dataType>string</dataType></stateVariable>
<stateVariable sendEvents="no"><name>PlaybackStorageMedium</name><dataType>string</dataType>
<allowedValueList><allowedValue>NONE</allowedValue><allowedValue>NETWORK</allowedValue></allowedValueList></stateVariable>
</serviceStateTable></scpd>"""


def last_change(vol, mute):
    inner = (f'<Event xmlns="urn:schemas-upnp-org:metadata-1-0/RCS/"><InstanceID val="0">'
             f'<Mute channel="Master" val="{mute}"/><Volume channel="Master" val="{vol}"/></InstanceID></Event>')
    esc = inner.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    return ('<?xml version="1.0"?><e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0">'
            f"<e:property><LastChange>{esc}</LastChange></e:property></e:propertyset>")


class FakeBar:
    def __init__(self):
        self.callback = None
        self.subs = 0
        self.unsubs = 0
        self.seq = 0
        self.avt_subs = 0

    async def desc(self, r):
        return web.Response(text=DESC, content_type="text/xml")

    async def scpd(self, r):
        return web.Response(text=SCPD, content_type="text/xml")

    async def avt_scpd(self, r):
        return web.Response(text=AVT_SCPD, content_type="text/xml")

    async def avt_evt(self, r):
        self.avt_subs += 1
        return web.Response(headers={"SID": "uuid:sub-avt", "TIMEOUT": "Second-1800"})

    async def evt(self, r):
        if r.method == "SUBSCRIBE":
            if "CALLBACK" in r.headers:
                self.callback = re.search(r"<(.+?)>", r.headers["CALLBACK"]).group(1)
            self.subs += 1
            return web.Response(headers={"SID": "uuid:sub-1", "TIMEOUT": "Second-1800"})
        if r.method == "UNSUBSCRIBE":
            self.unsubs += 1
            return web.Response()
        return web.Response(status=405)

    async def notify(self, vol, mute):
        async with aiohttp.ClientSession() as s:
            r = await s.request("NOTIFY", self.callback, data=last_change(vol, mute),
                                headers={"NT": "upnp:event", "NTS": "upnp:propchange", "SID": "uuid:sub-1",
                                         "SEQ": str(self.seq), "Content-Type": 'text/xml; charset="utf-8"'})
            self.seq += 1
            return r.status


@pytest.fixture
async def bar(socket_enabled):
    fb = FakeBar()
    app = web.Application()
    app.router.add_get("/description.xml", fb.desc)
    app.router.add_get("/rc.xml", fb.scpd)
    app.router.add_route("*", "/rc/evt", fb.evt)
    app.router.add_get("/avt.xml", fb.avt_scpd)
    app.router.add_route("*", "/avt/evt", fb.avt_evt)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 49152)
    await site.start()
    yield fb
    await runner.cleanup()


async def test_push_updates_volume_and_mute(hass, bar, socket_enabled):
    client = MagicMock()
    client.host = "127.0.0.1"
    client.async_get_device_status = AsyncMock(return_value={"uuid": "U1", "DeviceName": "YAS_209", "firmware": "4.6"})
    client.async_get_player_status = AsyncMock(return_value={"vol": "20", "mute": "0", "mode": "43", "status": "stop"})
    client.async_get_sound_settings = AsyncMock(return_value={"power saving": "1", "sound program": "movie"})
    entry = MagicMock()
    entry.options = {}
    with patch("homeassistant.components.network.async_get_source_ip", AsyncMock(return_value="127.0.0.1")):
        coord = YamahaCoordinator(hass, client, entry)
        await coord.async_refresh()
    assert coord.last_update_success
    assert coord.data.volume == 0.20 and coord.data.muted is False
    assert coord.events_subscribed, "should have subscribed"
    assert bar.subs == 1 and bar.callback.startswith("http://127.0.0.1:")
    assert bar.avt_subs == 0, "AVTransport must not be subscribed"

    updates = []
    coord.async_add_listener(lambda: updates.append((coord.data.volume, coord.data.muted)))

    assert await bar.notify(16, 0) == 200
    await hass.async_block_till_done()
    assert coord.data.volume == 0.16
    assert coord.data.raw_player_status["vol"] == "16"
    assert updates[-1] == (0.16, False)

    await bar.notify(16, 1)
    await hass.async_block_till_done()
    assert coord.data.muted is True and coord.data.raw_player_status["mute"] == "1"

    n = len(updates)
    await bar.notify(16, 1)  # no change -> no update
    await hass.async_block_till_done()
    assert len(updates) == n

    # A later poll keeps the subscription (no re-subscribe)
    await coord.async_refresh()
    assert bar.subs == 1

    await coord.async_shutdown()
    assert bar.unsubs == 1
    assert not coord.events_subscribed
    await coord.async_shutdown()  # idempotent


async def test_no_upnp_events_keeps_polling(hass, socket_enabled):
    """Device without UPnP: coordinator still polls fine."""
    client = MagicMock()
    client.host = "127.0.0.1"
    client.async_get_device_status = AsyncMock(return_value={"uuid": "U1"})
    client.async_get_player_status = AsyncMock(return_value={"vol": "30", "mute": "0"})
    client.async_get_sound_settings = AsyncMock(return_value={})
    entry = MagicMock()
    entry.options = {}
    coord = YamahaCoordinator(hass, client, entry)
    await coord.async_refresh()
    assert coord.last_update_success and coord.data.volume == 0.30
    assert not coord.events_subscribed
    await coord.async_shutdown()


async def test_resubscribes_after_lapse(hass, bar, socket_enabled):
    client = MagicMock()
    client.host = "127.0.0.1"
    client.async_get_device_status = AsyncMock(return_value={"uuid": "U1"})
    client.async_get_player_status = AsyncMock(return_value={"vol": "20", "mute": "0"})
    client.async_get_sound_settings = AsyncMock(return_value={})
    entry = MagicMock()
    entry.options = {}
    with patch("homeassistant.components.network.async_get_source_ip", AsyncMock(return_value="127.0.0.1")):
        coord = YamahaCoordinator(hass, client, entry)
        await coord.async_refresh()
        assert bar.subs == 1
        # Simulate a failed renewal (bar did SSDP byebye): library drops the sid
        coord._dmr._subscriptions.clear()
        coord._handle_upnp_event(MagicMock(), [])
        assert not coord.events_subscribed
        await coord.async_refresh()
        assert bar.subs == 2 and coord.events_subscribed
        assert await bar.notify(40, 0) == 200
        await hass.async_block_till_done()
        assert coord.data.volume == 0.40
    await coord.async_shutdown()
