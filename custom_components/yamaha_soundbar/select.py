"""Select entities for Yamaha Soundbar."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import YamahaCoordinator
from .entity import YamahaSoundbarEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Yamaha Soundbar select entities."""
    coordinator: YamahaCoordinator = entry.runtime_data
    async_add_entities([
        YamahaSoundProgramSelect(coordinator),
        YamahaPresetSelect(coordinator),
    ])


class YamahaSoundProgramSelect(YamahaSoundbarEntity, SelectEntity):
    """Sound program select entity (Yamaha DSP, distinct from EQ mode)."""

    _attr_translation_key = "sound_program"
    _attr_options = ["music", "movie", "sports", "game", "tv program", "stereo"]

    def __init__(self, coordinator: YamahaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.uuid}_sound_program"

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.data.sound_program
        if value in self._attr_options:
            return value
        return None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.client.async_set_sound_program(option)
        await self.coordinator.async_request_refresh()


class YamahaPresetSelect(YamahaSoundbarEntity, SelectEntity):
    """Preset select entity."""

    _attr_translation_key = "preset"

    def __init__(self, coordinator: YamahaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.uuid}_preset"
        preset_key = coordinator.data.preset_key
        self._attr_options = [f"Preset {i}" for i in range(1, preset_key + 1)]

    @property
    def current_option(self) -> str | None:
        num = self.coordinator.data.preset_number
        if num is not None and 1 <= num <= len(self._attr_options):
            return f"Preset {num}"
        return None

    async def async_select_option(self, option: str) -> None:
        number = int(option.split(" ")[1])
        await self.coordinator.client.async_recall_preset(number)
        await self.coordinator.async_request_refresh()
