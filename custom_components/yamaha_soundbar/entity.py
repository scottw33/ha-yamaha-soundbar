"""Base entity for Yamaha Soundbar."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import YamahaCoordinator


class YamahaSoundbarEntity(CoordinatorEntity[YamahaCoordinator]):
    """Base entity for Yamaha Soundbar devices."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: YamahaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.data.uuid)},
            name=coordinator.data.name,
            manufacturer="Yamaha",
            sw_version=f"{coordinator.data.firmware}-{coordinator.data.mcu_ver}",
        )
