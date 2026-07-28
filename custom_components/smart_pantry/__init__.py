"""The Smart Pantry Scanner integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN, PLATFORMS,
    SERVICE_ADD_ITEM, SERVICE_REMOVE_ITEM, SERVICE_UPDATE_ITEM,
    SERVICE_SCAN_BARCODE, SERVICE_GET_RECIPES,
    SERVICE_ADD_TO_SHOPPING_LIST, SERVICE_CLEAR_SHOPPING_LIST, SERVICE_MARK_CONSUMED,
    SERVICE_SYNC_SUGGESTIONS, SERVICE_ADD_RECIPE_MISSING, ATTR_RECIPE_NAME,
    ATTR_ITEM_NAME, ATTR_QUANTITY, ATTR_UNIT, ATTR_CATEGORY,
    ATTR_EXPIRATION_DATE, ATTR_STORAGE_LOCATION, ATTR_BARCODE, ATTR_NOTES, ATTR_RECIPE_COUNT,
    CATEGORIES, STORAGE_LOCATIONS, UNITS,
)
from .coordinator import SmartPantryCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_ADD_ITEM_SCHEMA = vol.Schema({
    vol.Required(ATTR_ITEM_NAME): cv.string,
    vol.Optional(ATTR_QUANTITY, default=1): vol.Coerce(float),
    vol.Optional(ATTR_UNIT, default="piece"): vol.In(UNITS),
    vol.Optional(ATTR_CATEGORY, default="other"): vol.In(CATEGORIES),
    vol.Optional(ATTR_EXPIRATION_DATE): cv.string,
    vol.Optional(ATTR_STORAGE_LOCATION, default="pantry"): vol.In(STORAGE_LOCATIONS),
    vol.Optional(ATTR_BARCODE): cv.string,
    vol.Optional(ATTR_NOTES): cv.string,
})

SERVICE_REMOVE_ITEM_SCHEMA = vol.Schema({vol.Required(ATTR_ITEM_NAME): cv.string})

SERVICE_UPDATE_ITEM_SCHEMA = vol.Schema({
    vol.Required(ATTR_ITEM_NAME): cv.string,
    vol.Optional(ATTR_QUANTITY): vol.Coerce(float),
    vol.Optional(ATTR_UNIT): vol.In(UNITS),
    vol.Optional(ATTR_CATEGORY): vol.In(CATEGORIES),
    vol.Optional(ATTR_EXPIRATION_DATE): cv.string,
    vol.Optional(ATTR_STORAGE_LOCATION): vol.In(STORAGE_LOCATIONS),
    vol.Optional(ATTR_NOTES): cv.string,
})

SERVICE_SCAN_BARCODE_SCHEMA = vol.Schema({
    vol.Required(ATTR_BARCODE): cv.string,
    vol.Optional(ATTR_QUANTITY, default=1): vol.Coerce(float),
    vol.Optional(ATTR_EXPIRATION_DATE): cv.string,
})

SERVICE_GET_RECIPES_SCHEMA = vol.Schema({vol.Optional(ATTR_RECIPE_COUNT, default=5): vol.Coerce(int)})

SERVICE_ADD_TO_SHOPPING_LIST_SCHEMA = vol.Schema({
    vol.Required(ATTR_ITEM_NAME): cv.string,
    vol.Optional(ATTR_QUANTITY, default=1): vol.Coerce(float),
    vol.Optional(ATTR_UNIT, default="piece"): vol.In(UNITS),
    vol.Optional(ATTR_NOTES): cv.string,
})

SERVICE_MARK_CONSUMED_SCHEMA = vol.Schema({
    vol.Required(ATTR_ITEM_NAME): cv.string,
    vol.Optional(ATTR_QUANTITY, default=1): vol.Coerce(float),
})

SERVICE_ADD_RECIPE_MISSING_SCHEMA = vol.Schema({
    vol.Required(ATTR_RECIPE_NAME): cv.string,
})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = SmartPantryCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    async def handle_add_item(call: ServiceCall) -> None:
        await coordinator.add_item(
            name=call.data[ATTR_ITEM_NAME], quantity=call.data[ATTR_QUANTITY],
            unit=call.data[ATTR_UNIT], category=call.data[ATTR_CATEGORY],
            expiration_date=call.data.get(ATTR_EXPIRATION_DATE),
            storage_location=call.data[ATTR_STORAGE_LOCATION],
            barcode=call.data.get(ATTR_BARCODE), notes=call.data.get(ATTR_NOTES),
        )

    async def handle_remove_item(call: ServiceCall) -> None:
        await coordinator.remove_item(call.data[ATTR_ITEM_NAME])

    async def handle_update_item(call: ServiceCall) -> None:
        await coordinator.update_item(
            name=call.data[ATTR_ITEM_NAME], quantity=call.data.get(ATTR_QUANTITY),
            unit=call.data.get(ATTR_UNIT), category=call.data.get(ATTR_CATEGORY),
            expiration_date=call.data.get(ATTR_EXPIRATION_DATE),
            storage_location=call.data.get(ATTR_STORAGE_LOCATION),
            notes=call.data.get(ATTR_NOTES),
        )

    async def handle_scan_barcode(call: ServiceCall) -> None:
        await coordinator.scan_barcode(
            barcode=call.data[ATTR_BARCODE], quantity=call.data[ATTR_QUANTITY],
            expiration_date=call.data.get(ATTR_EXPIRATION_DATE),
        )

    async def handle_get_recipes(call: ServiceCall) -> None:
        recipes = await coordinator.get_recipes(call.data[ATTR_RECIPE_COUNT])
        hass.bus.async_fire(f"{DOMAIN}_recipes_suggested", {"recipes": recipes})

    async def handle_add_to_shopping_list(call: ServiceCall) -> None:
        await coordinator.add_to_shopping_list(
            name=call.data[ATTR_ITEM_NAME], quantity=call.data[ATTR_QUANTITY],
            unit=call.data[ATTR_UNIT], notes=call.data.get(ATTR_NOTES),
        )

    async def handle_clear_shopping_list(call: ServiceCall) -> None:
        await coordinator.clear_shopping_list()

    async def handle_mark_consumed(call: ServiceCall) -> None:
        await coordinator.mark_consumed(name=call.data[ATTR_ITEM_NAME], quantity=call.data[ATTR_QUANTITY])

    async def handle_sync_suggestions(call: ServiceCall) -> None:
        count = await coordinator.sync_suggestions_to_shopping_list()
        hass.bus.async_fire(f"{DOMAIN}_suggestions_synced", {"count": count})

    async def handle_add_recipe_missing(call: ServiceCall) -> None:
        count = await coordinator.add_recipe_missing_to_shopping_list(call.data[ATTR_RECIPE_NAME])
        hass.bus.async_fire(f"{DOMAIN}_recipe_missing_added", {
            "recipe_name": call.data[ATTR_RECIPE_NAME], "count": count,
        })

    hass.services.async_register(DOMAIN, SERVICE_ADD_ITEM, handle_add_item, schema=SERVICE_ADD_ITEM_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_ITEM, handle_remove_item, schema=SERVICE_REMOVE_ITEM_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_ITEM, handle_update_item, schema=SERVICE_UPDATE_ITEM_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SCAN_BARCODE, handle_scan_barcode, schema=SERVICE_SCAN_BARCODE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_GET_RECIPES, handle_get_recipes, schema=SERVICE_GET_RECIPES_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ADD_TO_SHOPPING_LIST, handle_add_to_shopping_list, schema=SERVICE_ADD_TO_SHOPPING_LIST_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_SHOPPING_LIST, handle_clear_shopping_list)
    hass.services.async_register(DOMAIN, SERVICE_MARK_CONSUMED, handle_mark_consumed, schema=SERVICE_MARK_CONSUMED_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SYNC_SUGGESTIONS, handle_sync_suggestions)
    hass.services.async_register(DOMAIN, SERVICE_ADD_RECIPE_MISSING, handle_add_recipe_missing, schema=SERVICE_ADD_RECIPE_MISSING_SCHEMA)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
