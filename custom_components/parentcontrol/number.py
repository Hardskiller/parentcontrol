"""Default age and the age of each player."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ParentControlConfigEntry, device_info, player_device_info
from .const import MAX_AGE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the age numbers."""
    async_add_entities(
        [
            AgeNumber(entry),
            *(DeviceAgeNumber(hass, entry, player) for player in entry.runtime_data.players),
        ]
    )


class AgeNumber(NumberEntity):
    """Age used by all players without an own value."""

    _attr_has_entity_name = True
    _attr_translation_key = "age"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_AGE
    _attr_native_step = 1

    def __init__(self, entry: ParentControlConfigEntry) -> None:
        self._monitor = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_age"
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> int:
        """Return the age."""
        return self._monitor.age

    async def async_set_native_value(self, value: float) -> None:
        """Change the age; raising it needs the PIN."""
        await self._monitor.lock.async_authorize(self._context, loosens=value > self._monitor.age)
        self._monitor.async_set_age(int(value))
        self.async_write_ha_state()


class DeviceAgeNumber(AgeNumber):
    """Age of one player; shows the default age until it gets its own."""

    _attr_translation_key = "device_age"

    def __init__(
        self, hass: HomeAssistant, entry: ParentControlConfigEntry, player: str
    ) -> None:
        super().__init__(entry)
        self._player = player
        self._attr_unique_id = f"{entry.entry_id}_{player}_age"
        self._attr_device_info = player_device_info(hass, entry, player)

    @property
    def native_value(self) -> int:
        """Return the age of the player."""
        return self._monitor.device_age(self._player)

    async def async_set_native_value(self, value: float) -> None:
        """Change the age of the player; raising it needs the PIN."""
        await self._monitor.lock.async_authorize(
            self._context, loosens=value > self._monitor.device_age(self._player)
        )
        self._monitor.async_set_device_age(self._player, int(value))
