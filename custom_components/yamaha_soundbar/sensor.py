"""Sensor entities for Yamaha Soundbar."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import YamahaCoordinator
from .entity import YamahaSoundbarEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Yamaha Soundbar sensor entities."""
    coordinator: YamahaCoordinator = entry.runtime_data
    async_add_entities([YamahaWifiChannelSensor(coordinator)])


class YamahaWifiChannelSensor(YamahaSoundbarEntity, SensorEntity):
    """WiFi channel diagnostic sensor."""

    _attr_translation_key = "wifi_channel"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: YamahaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.uuid}_wifi_channel"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.wifi_channel
