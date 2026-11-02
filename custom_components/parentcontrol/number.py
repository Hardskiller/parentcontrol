"""Age of each child profile."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ParentControlConfigEntry, profile_device_info
from .const import MAX_AGE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one age per profile."""
    async_add_entities(ProfileAgeNumber(entry, profile) for profile in entry.runtime_data.profiles)


class ProfileAgeNumber(NumberEntity):
    """Age of one child."""

    _attr_has_entity_name = True
    _attr_translation_key = "profile_age"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_AGE
    _attr_native_step = 1

    def __init__(self, entry: ParentControlConfigEntry, profile: str) -> None:
        self._monitor = entry.runtime_data
        self._profile = profile
        self._attr_unique_id = f"{entry.entry_id}_profile_{profile}_age"
        self._attr_device_info = profile_device_info(entry, profile)

    @property
    def native_value(self) -> int:
        """Return the age."""
        return self._monitor.profile_age(self._profile)

    async def async_set_native_value(self, value: float) -> None:
        """Change the age; raising it needs the PIN."""
        await self._monitor.lock.async_authorize(
            self._context, loosens=value > self._monitor.profile_age(self._profile)
        )
        self._monitor.async_set_profile_age(self._profile, int(value))
        self.async_write_ha_state()
