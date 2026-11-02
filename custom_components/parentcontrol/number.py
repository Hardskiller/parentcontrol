"""Age and daily limits of each child profile."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ParentControlConfigEntry, profile_device_info
from .const import LIMITS, MAX_AGE, MAX_LIMIT_MINUTES
from .profiles import limit_loosens


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up age and limits per profile."""
    profiles = entry.runtime_data.profiles
    async_add_entities(
        [
            *(ProfileAgeNumber(entry, profile) for profile in profiles),
            *(ProfileLimitNumber(entry, profile, limit) for profile in profiles for limit in LIMITS),
        ]
    )


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


class ProfileLimitNumber(NumberEntity):
    """Minutes of YouTube per day for one child; 0 means no limit."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_LIMIT_MINUTES
    _attr_native_step = 5
    _attr_native_unit_of_measurement = "min"

    def __init__(self, entry: ParentControlConfigEntry, profile: str, limit: str) -> None:
        self._monitor = entry.runtime_data
        self._profile = profile
        self._limit = limit
        self._attr_translation_key = limit
        self._attr_unique_id = f"{entry.entry_id}_profile_{profile}_{limit}"
        self._attr_device_info = profile_device_info(entry, profile)

    @property
    def native_value(self) -> int:
        """Return the limit."""
        return int(self._monitor.profile_value(self._profile, self._limit, 0))

    async def async_set_native_value(self, value: float) -> None:
        """Change the limit; raising or removing it needs the PIN."""
        await self._monitor.lock.async_authorize(
            self._context, loosens=limit_loosens(self.native_value, int(value))
        )
        self._monitor.async_set_profile_value(self._profile, self._limit, int(value))
        self.async_write_ha_state()
