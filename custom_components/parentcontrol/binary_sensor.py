"""Whether Ollama and the YouTube lookup work."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ParentControlConfigEntry, device_info
from .const import HEALTH


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one sensor per service."""
    async_add_entities(HealthSensor(entry, name) for name in HEALTH)


class HealthSensor(BinarySensorEntity):
    """On while the service answers; unknown until it was used."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ParentControlConfigEntry, name: str) -> None:
        self._monitor = entry.runtime_data
        self._name = name
        self._attr_translation_key = name
        self._attr_unique_id = f"{entry.entry_id}_{name}_health"
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Follow the monitor."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._monitor.signal, self.async_write_ha_state)
        )

    @property
    def is_on(self) -> bool | None:
        """Return whether the service worked last time."""
        return self._monitor.health[self._name]
