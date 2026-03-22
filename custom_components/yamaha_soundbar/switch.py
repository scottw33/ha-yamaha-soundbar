"""Switch entities for Yamaha Soundbar."""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import YamahaClient
from .coordinator import YamahaCoordinator, YamahaData
from .entity import YamahaSoundbarEntity


@dataclass(frozen=True, kw_only=True)
class YamahaSwitchEntityDescription(SwitchEntityDescription):
    """Describe a Yamaha switch entity."""

    value_fn: Callable[[YamahaData], bool]
    turn_on_fn: Callable[[YamahaClient], Coroutine[Any, Any, None]]
    turn_off_fn: Callable[[YamahaClient], Coroutine[Any, Any, None]]
    is_led: bool = False


SWITCH_DESCRIPTIONS: tuple[YamahaSwitchEntityDescription, ...] = (
    YamahaSwitchEntityDescription(
        key="surround",
        translation_key="surround",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.surround,
        turn_on_fn=lambda client: client.async_set_surround(True),
        turn_off_fn=lambda client: client.async_set_surround(False),
    ),
    YamahaSwitchEntityDescription(
        key="clear_voice",
        translation_key="clear_voice",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.clear_voice,
        turn_on_fn=lambda client: client.async_set_clear_voice(True),
        turn_off_fn=lambda client: client.async_set_clear_voice(False),
    ),
    YamahaSwitchEntityDescription(
        key="bass_extension",
        translation_key="bass_extension",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.bass_extension,
        turn_on_fn=lambda client: client.async_set_bass_extension(True),
        turn_off_fn=lambda client: client.async_set_bass_extension(False),
    ),
    YamahaSwitchEntityDescription(
        key="led",
        translation_key="led",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.led,
        turn_on_fn=lambda client: client.async_set_surround(True),  # unused, see is_led
        turn_off_fn=lambda client: client.async_set_surround(False),  # unused, see is_led
        is_led=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Yamaha Soundbar switch entities."""
    coordinator: YamahaCoordinator = entry.runtime_data
    async_add_entities(
        YamahaSoundbarSwitch(coordinator, description)
        for description in SWITCH_DESCRIPTIONS
    )


class YamahaSoundbarSwitch(YamahaSoundbarEntity, SwitchEntity):
    """Switch entity for Yamaha Soundbar."""

    entity_description: YamahaSwitchEntityDescription

    def __init__(
        self,
        coordinator: YamahaCoordinator,
        description: YamahaSwitchEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.data.uuid}_{description.key}"

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self.entity_description.is_led:
            await self.hass.async_add_executor_job(
                self.coordinator.client.set_led_sync, True
            )
            self.coordinator.set_led_state(True)
        else:
            await self.entity_description.turn_on_fn(self.coordinator.client)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.entity_description.is_led:
            await self.hass.async_add_executor_job(
                self.coordinator.client.set_led_sync, False
            )
            self.coordinator.set_led_state(False)
        else:
            await self.entity_description.turn_off_fn(self.coordinator.client)
        await self.coordinator.async_request_refresh()
