"""Load the whole integration in HA with a mocked client."""
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import STATE_OFF

DS = {"uuid": "FFB8F0028DB782D1C580978D", "DeviceName": "YAS_209", "firmware": "Linkplay.3.6.418924", "mcu_ver": "531", "preset_key": "6"}
PS = {"vol": "20", "mute": "0", "mode": "43", "status": "stop", "type": "0", "loop": "4", "eq": "0", "curpos": "0", "totlen": "0"}
SS = {"power saving": "1", "sound program": "movie", "subwoofer volume": "2", "3D surround": "0", "clear voice": "1", "bass extension": "0"}


async def test_setup_power_volume_unload(hass, socket_enabled):
    ss = dict(SS)
    with patch("custom_components.yamaha_soundbar.client.YamahaClient.async_get_device_status", AsyncMock(return_value=DS)), \
         patch("custom_components.yamaha_soundbar.client.YamahaClient.async_get_player_status", AsyncMock(return_value=PS)), \
         patch("custom_components.yamaha_soundbar.client.YamahaClient.async_get_sound_settings", AsyncMock(side_effect=lambda: dict(ss))), \
         patch("custom_components.yamaha_soundbar.client.YamahaClient._async_httpapi", AsyncMock(return_value="OK")) as api, \
         patch("custom_components.yamaha_soundbar.client.YamahaClient._async_yamaha_data_set", AsyncMock()) as yset:
        entry = MockConfigEntry(domain="yamaha_soundbar", data={"host": "127.0.0.9", "uuid": DS["uuid"]}, unique_id=DS["uuid"])
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        mp = [s for s in hass.states.async_all("media_player")]
        assert len(mp) == 1, mp
        eid = mp[0].entity_id
        st = hass.states.get(eid)
        assert st.attributes["volume_level"] == 0.2
        assert st.attributes["supported_features"] & 128 and st.attributes["supported_features"] & 256  # TURN_ON / TURN_OFF
        assert not [s for s in hass.states.async_all("switch") if "led" in s.entity_id], "LED switch should be gone"
        vols = [s for s in hass.states.async_all("number") if s.entity_id.endswith("_volume") and "subwoofer" not in s.entity_id]
        assert len(vols) == 1 and vols[0].state == "20.0", vols
        assert "unit_of_measurement" not in vols[0].attributes
        await hass.services.async_call("number", "set_value", {"entity_id": vols[0].entity_id, "value": 31}, blocking=True)
        assert any(c.args[0] == "setPlayerCmd:vol:32" for c in api.call_args_list), api.call_args_list

        await hass.services.async_call("media_player", "volume_set", {"entity_id": eid, "volume_level": 0.23}, blocking=True)
        assert any(c.args[0] == "setPlayerCmd:vol:22" or c.args[0] == "setPlayerCmd:vol:24" for c in api.call_args_list), api.call_args_list

        await hass.services.async_call("media_player", "turn_off", {"entity_id": eid}, blocking=True)
        yset.assert_called_with("power saving", "0")
        ss["power saving"] = "0"
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(eid).state == STATE_OFF

        await hass.services.async_call("media_player", "turn_on", {"entity_id": eid}, blocking=True)
        yset.assert_called_with("power saving", "1")

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.data["yamaha_soundbar"]["entities"] == []
