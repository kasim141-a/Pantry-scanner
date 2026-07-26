"""DataUpdateCoordinator for Smart Pantry Scanner."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN, STORAGE_KEY_PANTRY, STORAGE_VERSION,
    BUILT_IN_RECIPES, BARCODE_DB,
    EXPIRE_WARNING_DAYS, EXPIRE_CRITICAL_DAYS,
    CONF_HOUSEHOLD_NAME, CONF_CURRENCY, CONF_WEEKLY_BUDGET, CONF_DIET_PREFERENCE,
    DEFAULT_HOUSEHOLD_NAME, DEFAULT_CURRENCY, DEFAULT_WEEKLY_BUDGET, DEFAULT_DIET_PREFERENCE,
)

_LOGGER = logging.getLogger(__name__)


class SmartPantryCoordinator(DataUpdateCoordinator):
    """Smart Pantry data coordinator."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_PANTRY}_{entry.entry_id}")
        self.hass = hass
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(minutes=5))

    async def _async_update_data(self) -> dict[str, Any]:
        data = await self.store.async_load()
        if data is None:
            data = self._default_data()
            await self.store.async_save(data)
        return data

    def _default_data(self) -> dict[str, Any]:
        return {
            "pantry": {},
            "shopping_list": [],
            "stats": {
                "waste_prevented_lbs": 0.0, "money_saved": 0.0,
                "meals_cooked": 0, "items_scanned": 0,
                "items_consumed": 0, "items_wasted": 0,
            },
            "config": {
                CONF_HOUSEHOLD_NAME: self.entry.options.get(CONF_HOUSEHOLD_NAME, DEFAULT_HOUSEHOLD_NAME),
                CONF_CURRENCY: self.entry.options.get(CONF_CURRENCY, DEFAULT_CURRENCY),
                CONF_WEEKLY_BUDGET: self.entry.options.get(CONF_WEEKLY_BUDGET, DEFAULT_WEEKLY_BUDGET),
                CONF_DIET_PREFERENCE: self.entry.options.get(CONF_DIET_PREFERENCE, DEFAULT_DIET_PREFERENCE),
            },
        }

    async def async_shutdown(self) -> None:
        pass

    async def add_item(self, name: str, quantity: float = 1, unit: str = "piece",
                       category: str = "other", expiration_date: str | None = None,
                       storage_location: str = "pantry", barcode: str | None = None,
                       notes: str | None = None) -> None:
        data = await self._async_update_data()
        key = name.lower().strip()
        item = {
            "name": name, "quantity": quantity, "unit": unit,
            "category": category, "expiration_date": expiration_date,
            "storage_location": storage_location, "barcode": barcode,
            "notes": notes, "added_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        if key in data["pantry"]:
            existing = data["pantry"][key]
            item["quantity"] = existing["quantity"] + quantity
            item["added_at"] = existing.get("added_at", item["added_at"])
            item["notes"] = notes or existing.get("notes")
        data["pantry"][key] = item
        data["stats"]["items_scanned"] = data["stats"].get("items_scanned", 0) + 1
        await self.store.async_save(data)
        await self.async_request_refresh()
        _LOGGER.info("Added/updated pantry item: %s (qty: %s %s)", name, quantity, unit)

    async def remove_item(self, name: str) -> None:
        data = await self._async_update_data()
        key = name.lower().strip()
        if key in data["pantry"]:
            del data["pantry"][key]
            await self.store.async_save(data)
            await self.async_request_refresh()
            _LOGGER.info("Removed pantry item: %s", name)
        else:
            _LOGGER.warning("Item not found: %s", name)

    async def update_item(self, name: str, quantity: float | None = None,
                          unit: str | None = None, category: str | None = None,
                          expiration_date: str | None = None,
                          storage_location: str | None = None,
                          notes: str | None = None) -> None:
        data = await self._async_update_data()
        key = name.lower().strip()
        if key not in data["pantry"]:
            _LOGGER.warning("Item not found for update: %s", name)
            return
        item = data["pantry"][key]
        if quantity is not None: item["quantity"] = quantity
        if unit is not None: item["unit"] = unit
        if category is not None: item["category"] = category
        if expiration_date is not None: item["expiration_date"] = expiration_date
        if storage_location is not None: item["storage_location"] = storage_location
        if notes is not None: item["notes"] = notes
        item["updated_at"] = datetime.now().isoformat()
        await self.store.async_save(data)
        await self.async_request_refresh()
        _LOGGER.info("Updated pantry item: %s", name)

    async def scan_barcode(self, barcode: str, quantity: float = 1,
                           expiration_date: str | None = None) -> None:
        product = BARCODE_DB.get(barcode, BARCODE_DB["0000000000000"])
        name = product["name"]
        if expiration_date is None:
            expiry = datetime.now() + timedelta(days=product["typical_expiry_days"])
            expiration_date = expiry.strftime("%Y-%m-%d")
        await self.add_item(name=name, quantity=quantity, category=product["category"],
                            expiration_date=expiration_date, barcode=barcode)

    async def mark_consumed(self, name: str, quantity: float = 1) -> None:
        data = await self._async_update_data()
        key = name.lower().strip()
        if key not in data["pantry"]:
            _LOGGER.warning("Item not found: %s", name)
            return
        item = data["pantry"][key]
        item["quantity"] -= quantity
        item["updated_at"] = datetime.now().isoformat()
        if item["quantity"] <= 0:
            del data["pantry"][key]
        data["stats"]["items_consumed"] = data["stats"].get("items_consumed", 0) + 1
        data["stats"]["meals_cooked"] = data["stats"].get("meals_cooked", 0) + 1
        data["stats"]["money_saved"] = data["stats"].get("money_saved", 0) + 3.0
        data["stats"]["waste_prevented_lbs"] = data["stats"].get("waste_prevented_lbs", 0) + 0.5
        await self.store.async_save(data)
        await self.async_request_refresh()
        _LOGGER.info("Marked consumed: %s (qty: %s)", name, quantity)

    async def add_to_shopping_list(self, name: str, quantity: float = 1,
                                   unit: str = "piece", notes: str | None = None) -> None:
        data = await self._async_update_data()
        data["shopping_list"].append({
            "name": name, "quantity": quantity, "unit": unit,
            "notes": notes, "added_at": datetime.now().isoformat(), "purchased": False,
        })
        await self.store.async_save(data)
        await self.async_request_refresh()
        _LOGGER.info("Added to shopping list: %s", name)

    async def clear_shopping_list(self) -> None:
        data = await self._async_update_data()
        data["shopping_list"] = []
        await self.store.async_save(data)
        await self.async_request_refresh()
        _LOGGER.info("Cleared shopping list")

    async def get_recipes(self, count: int = 5) -> list[dict[str, Any]]:
        data = await self._async_update_data()
        pantry_items = {k for k in data["pantry"].keys()}
        diet = data["config"].get(CONF_DIET_PREFERENCE, DEFAULT_DIET_PREFERENCE)
        scored_recipes = []
        for recipe in BUILT_IN_RECIPES:
            if diet != "none" and diet not in recipe.get("diet", []):
                continue
            ingredients = set(ing.lower() for ing in recipe["ingredients"])
            matched = ingredients & pantry_items
            missing = ingredients - pantry_items
            match_pct = len(matched) / len(ingredients) * 100 if ingredients else 0
            scored_recipes.append({
                "name": recipe["name"], "time": recipe["time"],
                "match_percent": round(match_pct, 1),
                "matched_ingredients": sorted(list(matched)),
                "missing_ingredients": sorted(list(missing)),
                "total_ingredients": len(ingredients),
            })
        scored_recipes.sort(key=lambda x: x["match_percent"], reverse=True)
        return scored_recipes[:count]

    def get_expiring_items(self, days: int = EXPIRE_WARNING_DAYS) -> list[dict[str, Any]]:
        data = self.data or {}
        pantry = data.get("pantry", {})
        now = datetime.now()
        expiring = []
        for item in pantry.values():
            if item.get("expiration_date"):
                try:
                    exp = datetime.strptime(item["expiration_date"], "%Y-%m-%d")
                    delta = (exp - now).days
                    if delta <= days:
                        item_copy = dict(item)
                        item_copy["days_until_expiry"] = delta
                        expiring.append(item_copy)
                except ValueError:
                    continue
        expiring.sort(key=lambda x: x["days_until_expiry"])
        return expiring

    def get_expired_items(self) -> list[dict[str, Any]]:
        return [i for i in self.get_expiring_items(9999) if i["days_until_expiry"] < 0]

    def get_items_by_location(self, location: str) -> list[dict[str, Any]]:
        data = self.data or {}
        return [i for i in data.get("pantry", {}).values() if i.get("storage_location") == location]

    def get_items_by_category(self, category: str) -> list[dict[str, Any]]:
        data = self.data or {}
        return [i for i in data.get("pantry", {}).values() if i.get("category") == category]
