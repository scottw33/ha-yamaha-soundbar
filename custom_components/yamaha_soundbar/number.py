"""Number entities for Yamaha Soundbar."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import snap_volume
from .const import MAX_VOL, VOL_STEP_RAW
from .coordinator import YamahaCoordinator
from .entity import YamahaSoundbarEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Yamaha Soundbar number entities."""
    coordinator: YamahaCoordinator = entry.runtime_data
    async_add_entities([YamahaVolume(coordinator), YamahaSubwooferVolume(coordinator)])


class YamahaSubwooferVolume(YamahaSoundbarEntity, NumberEntity):
    """Subwoofer volume number entity."""

    _attr_translation_key = "subwoofer_volume"
    _attr_native_min_value = -4
    _attr_native_max_value = 4
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: YamahaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.uuid}_subwoofer_volume"

    @property
    def native_value(self) -> float:
        return float(self.coordinator.data.subwoofer_volume)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.async_set_subwoofer_volume(int(value))
        await self.coordinator.async_request_refresh()


class YamahaVolume(YamahaSoundbarEntity, NumberEntity):
    """Main volume as its own entity, so changes show in history and the logbook.

    Mirrors the media player's volume (raw 0-100, steps of 2).
    """

    _attr_translation_key = "volume"
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_VOL
    _attr_native_step = VOL_STEP_RAW
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: YamahaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.uuid}_volume"

    @property
    def native_value(self) -> float:
        return float(round(self.coordinator.data.volume * MAX_VOL))

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.async_set_volume(snap_volume(value))
        await self.coordinator.async_request_refresh()
