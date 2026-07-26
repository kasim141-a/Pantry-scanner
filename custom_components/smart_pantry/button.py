"""Button platform for Smart Pantry Scanner."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_HOUSEHOLD_NAME, DEFAULT_HOUSEHOLD_NAME
from .coordinator import SmartPantryCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SmartPantryCoordinator = hass.data[DOMAIN][entry.entry_id]
    household_name = coordinator.data.get("config", {}).get(
        CONF_HOUSEHOLD_NAME, DEFAULT_HOUSEHOLD_NAME
    )

    entities = [
        PantryGetRecipesButton(coordinator, entry, household_name),
        PantryClearShoppingListButton(coordinator, entry, household_name),
        PantryScanDemoButton(coordinator, entry, household_name),
    ]
    async_add_entities(entities)


class SmartPantryBaseButton(CoordinatorEntity[SmartPantryCoordinator], ButtonEntity):
    def __init__(self, coordinator, entry, household_name, suffix, name, icon):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
        self._attr_name = f"Smart Pantry {household_name} {name}"
        self._attr_icon = icon
        self._attr_should_poll = False

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Smart Pantry Scanner",
            "manufacturer": "Smart Pantry",
            "model": "Smart Pantry Scanner",
            "entry_type": "service",
        }

    @property
    def available(self):
        return self.coordinator.last_update_success


class PantryGetRecipesButton(SmartPantryBaseButton):
    def __init__(self, coordinator, entry, household_name):
        super().__init__(coordinator, entry, household_name, "get_recipes", "Get Recipes", "mdi:chef-hat")

    async def async_press(self):
        recipes = await self.coordinator.get_recipes(5)
        self.hass.bus.async_fire(f"{DOMAIN}_recipes_suggested", {"recipes": recipes})


class PantryClearShoppingListButton(SmartPantryBaseButton):
    def __init__(self, coordinator, entry, household_name):
        super().__init__(coordinator, entry, household_name, "clear_shopping_list", "Clear Shopping List", "mdi:cart-off")

    async def async_press(self):
        await self.coordinator.clear_shopping_list()


class PantryScanDemoButton(SmartPantryBaseButton):
    def __init__(self, coordinator, entry, household_name):
        super().__init__(coordinator, entry, household_name, "scan_demo", "Scan Demo Item", "mdi:barcode-scan")

    async def async_press(self):
        await self.coordinator.scan_barcode("038000138133", quantity=1)
