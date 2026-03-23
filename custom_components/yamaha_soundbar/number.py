"""Number entities for Yamaha Soundbar."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import YamahaCoordinator
from .entity import YamahaSoundbarEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Yamaha Soundbar number entities."""
    coordinator: YamahaCoordinator = entry.runtime_data
    async_add_entities([YamahaSubwooferVolume(coordinator)])


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
