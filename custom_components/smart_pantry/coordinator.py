"""DataUpdateCoordinator for Smart Pantry Scanner."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN, STORAGE_KEY_PANTRY, STORAGE_VERSION,
    BUILT_IN_RECIPES, BARCODE_DB,
    OFF_API_URL, OFF_TIMEOUT, OFF_CATEGORY_MAP, CATEGORY_DEFAULT_EXPIRY_DAYS,
    EXPIRE_WARNING_DAYS, LOW_STOCK_THRESHOLD,
    CONF_HOUSEHOLD_NAME, CONF_CURRENCY, CONF_WEEKLY_BUDGET, CONF_DIET_PREFERENCE,
    CONF_LOW_STOCK_THRESHOLD, CONF_EXPIRY_WARNING_DAYS, CONF_AUTO_ADD_TO_HA_LIST,
    DEFAULT_HOUSEHOLD_NAME, DEFAULT_CURRENCY, DEFAULT_WEEKLY_BUDGET, DEFAULT_DIET_PREFERENCE,
    DEFAULT_LOW_STOCK_THRESHOLD, DEFAULT_EXPIRY_WARNING_DAYS, DEFAULT_AUTO_ADD_TO_HA_LIST,
)

_LOGGER = logging.getLogger(__name__)


class SmartPantryCoordinator(DataUpdateCoordinator):
    """Smart Pantry data coordinator."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_PANTRY}_{entry.entry_id}")
        self.hass = hass
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(minutes=5))

    # ---- Config helpers ----------------------------------------------------

    @property
    def low_stock_threshold(self) -> float:
        return float(self.entry.options.get(CONF_LOW_STOCK_THRESHOLD, DEFAULT_LOW_STOCK_THRESHOLD))

    @property
    def expiry_warning_days(self) -> int:
        return int(self.entry.options.get(CONF_EXPIRY_WARNING_DAYS, DEFAULT_EXPIRY_WARNING_DAYS))

    @property
    def auto_add_to_ha_list(self) -> bool:
        return bool(self.entry.options.get(CONF_AUTO_ADD_TO_HA_LIST, DEFAULT_AUTO_ADD_TO_HA_LIST))

    # ---- Storage -------------------------------------------------------------

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

    # ---- Pantry CRUD ---------------------------------------------------------

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

    # ---- Barcode scanning ------------------------------------------------------

    async def _lookup_barcode(self, barcode: str) -> dict[str, Any]:
        """Look up a barcode: built-in DB first, then Open Food Facts, else Unknown."""
        if barcode in BARCODE_DB:
            return dict(BARCODE_DB[barcode])
        # Try Open Food Facts (free, no API key).
        try:
            session = async_get_clientsession(self.hass)
            url = OFF_API_URL.format(barcode=barcode)
            async with session.get(url, timeout=OFF_TIMEOUT) as resp:
                if resp.status == 200:
                    payload = await resp.json()
                    product = payload.get("product") or {}
                    name = (product.get("product_name")
                            or product.get("product_name_en")
                            or product.get("generic_name") or "").strip()
                    if payload.get("status") == 1 and name:
                        categories = (product.get("categories") or "").lower()
                        category = "other"
                        for keyword, mapped in OFF_CATEGORY_MAP.items():
                            if keyword in categories:
                                category = mapped
                                break
                        return {
                            "name": name,
                            "category": category,
                            "typical_expiry_days": CATEGORY_DEFAULT_EXPIRY_DAYS.get(category, 30),
                            "source": "openfoodfacts",
                        }
        except Exception as err:  # noqa: BLE001 - network failures are non-fatal
            _LOGGER.debug("Open Food Facts lookup failed for %s: %s", barcode, err)
        unknown = dict(BARCODE_DB["0000000000000"])
        unknown["name"] = f"Unknown Item ({barcode})"
        return unknown

    async def scan_barcode(self, barcode: str, quantity: float = 1,
                           expiration_date: str | None = None) -> None:
        """Scan a barcode from camera, BT/USB scanner, or manual input."""
        barcode = barcode.strip()
        product = await self._lookup_barcode(barcode)
        name = product["name"]
        if expiration_date is None:
            expiry = datetime.now() + timedelta(days=product["typical_expiry_days"])
            expiration_date = expiry.strftime("%Y-%m-%d")
        await self.add_item(name=name, quantity=quantity, category=product["category"],
                            expiration_date=expiration_date, barcode=barcode)
        data = await self._async_update_data()
        item = data["pantry"].get(name.lower().strip(), {})
        qty = item.get("quantity", quantity)
        exp_date = item.get("expiration_date")
        low_stock = qty <= self.low_stock_threshold
        expiring = False
        if exp_date:
            try:
                delta = (datetime.strptime(exp_date, "%Y-%m-%d") - datetime.now()).days
                expiring = delta <= self.expiry_warning_days
            except ValueError:
                pass

        suggest = low_stock or expiring
        # Optionally auto-add to HA's default shopping list when suggested.
        if suggest and self.auto_add_to_ha_list:
            await self.add_to_shopping_list(name=name, quantity=1, unit=item.get("unit", "piece"),
                                            notes="Auto-suggested after scan")

        self.hass.bus.async_fire(f"{DOMAIN}_scan_result", {
            "barcode": barcode,
            "item_name": name,
            "quantity": qty,
            "unit": item.get("unit", "piece"),
            "category": product["category"],
            "expiration_date": exp_date,
            "low_stock": low_stock,
            "expiring": expiring,
            "suggest_shopping_list": suggest,
            "auto_added": bool(suggest and self.auto_add_to_ha_list),
            "source": product.get("source", "local"),
        })

    async def mark_consumed(self, name: str, quantity: float = 1) -> None:
        data = await self._async_update_data()
        key = name.lower().strip()
        if key not in data["pantry"]:
            _LOGGER.warning("Item not found: %s", name)
            return
        item = data["pantry"][key]
        item["quantity"] -= quantity
        item["updated_at"] = datetime.now().isoformat()
        depleted = item["quantity"] <= 0
        remaining_qty = max(0, item["quantity"])
        unit = item.get("unit", "piece")
        if depleted:
            del data["pantry"][key]
        data["stats"]["items_consumed"] = data["stats"].get("items_consumed", 0) + 1
        data["stats"]["meals_cooked"] = data["stats"].get("meals_cooked", 0) + 1
        data["stats"]["money_saved"] = data["stats"].get("money_saved", 0) + 3.0
        data["stats"]["waste_prevented_lbs"] = data["stats"].get("waste_prevented_lbs", 0) + 0.5
        await self.store.async_save(data)
        await self.async_request_refresh()
        # Suggest replenishment when consumption depletes or drops below threshold.
        if depleted or remaining_qty <= self.low_stock_threshold:
            if self.auto_add_to_ha_list:
                await self.add_to_shopping_list(name=name, quantity=1, unit=unit,
                                                notes="Ran low after use")
            self.hass.bus.async_fire(f"{DOMAIN}_low_stock", {
                "item_name": name, "quantity": remaining_qty, "unit": unit,
                "depleted": depleted,
            })
        _LOGGER.info("Marked consumed: %s (qty: %s)", name, quantity)

    # ---- Shopping list ---------------------------------------------------------

    async def add_to_shopping_list(self, name: str, quantity: float = 1,
                                   unit: str = "piece", notes: str | None = None) -> None:
        """Add an item to both the internal list and HA's default Shopping List."""
        data = await self._async_update_data()
        existing = next((i for i in data["shopping_list"] if i["name"].lower() == name.lower()), None)
        if not existing:
            data["shopping_list"].append({
                "name": name, "quantity": quantity, "unit": unit,
                "notes": notes, "added_at": datetime.now().isoformat(), "purchased": False,
            })
            await self.store.async_save(data)
            await self.async_request_refresh()
        await self._ha_shopping_list_add(name, quantity, unit)
        _LOGGER.info("Added to shopping list: %s", name)

    async def _ha_shopping_list_add(self, name: str, quantity: float, unit: str) -> None:
        """Sync a single item into Home Assistant's built-in shopping_list."""
        if not self.hass.services.has_service("shopping_list", "add_item"):
            _LOGGER.warning(
                "HA shopping_list integration not available. "
                "Add 'shopping_list:' to configuration.yaml or enable the Shopping List integration."
            )
            return
        display_name = f"{name} ({quantity:g} {unit})" if quantity != 1 or unit != "piece" else name
        try:
            await self.hass.services.async_call(
                "shopping_list", "add_item", {"name": display_name}, blocking=False,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("HA shopping_list sync failed: %s", err)

    async def sync_suggestions_to_shopping_list(self) -> int:
        """Push all current suggestions (low stock + expiring) to the shopping lists."""
        suggestions = self.get_suggestions()
        for s in suggestions:
            await self.add_to_shopping_list(
                name=s["name"], quantity=1, unit=s.get("unit", "piece"),
                notes=s.get("reason"),
            )
        _LOGGER.info("Synced %d suggestions to shopping list", len(suggestions))
        return len(suggestions)

    async def add_recipe_missing_to_shopping_list(self, recipe_name: str) -> int:
        """Add all missing ingredients of a recipe to the shopping lists."""
        recipes = await self.get_recipes(count=50)
        recipe = next((r for r in recipes if r["name"].lower() == recipe_name.lower()), None)
        if recipe is None:
            _LOGGER.warning("Recipe not found: %s", recipe_name)
            return 0
        missing = recipe.get("missing_ingredients", [])
        for ing in missing:
            await self.add_to_shopping_list(name=ing.title(), quantity=1, unit="piece",
                                            notes=f"For recipe: {recipe['name']}")
        return len(missing)

    def get_low_stock_items(self, threshold: float | None = None) -> list[dict]:
        if threshold is None:
            threshold = self.low_stock_threshold
        data = self.data or {}
        return [
            {"name": i["name"], "quantity": i["quantity"], "unit": i["unit"],
             "category": i.get("category", "other")}
            for i in data.get("pantry", {}).values()
            if i.get("quantity", 0) <= threshold
        ]

    def get_suggestions(self) -> list[dict[str, Any]]:
        """Build shopping list suggestions from low stock and expiring items."""
        data = self.data or {}
        shopping_names = {i["name"].lower() for i in data.get("shopping_list", [])}
        suggestions: dict[str, dict[str, Any]] = {}
        for item in self.get_low_stock_items():
            key = item["name"].lower()
            if key in shopping_names:
                continue
            suggestions[key] = {
                "name": item["name"], "quantity": item["quantity"],
                "unit": item.get("unit", "piece"),
                "reason": "low_stock",
                "detail": f"Only {item['quantity']:g} {item.get('unit', 'piece')} left",
            }
        for item in self.get_expiring_items(self.expiry_warning_days):
            key = item["name"].lower()
            if key in shopping_names:
                continue
            days = item.get("days_until_expiry", 0)
            detail = ("Expired" if days < 0 else
                      "Expires today" if days == 0 else
                      f"Expires in {days} day{'s' if days != 1 else ''}")
            if key in suggestions:
                suggestions[key]["reason"] = "low_stock_and_expiring"
                suggestions[key]["detail"] += f" • {detail}"
            else:
                suggestions[key] = {
                    "name": item["name"], "quantity": item["quantity"],
                    "unit": item.get("unit", "piece"),
                    "reason": "expiring",
                    "detail": detail,
                }
        return sorted(suggestions.values(), key=lambda s: s["name"].lower())

    async def clear_shopping_list(self) -> None:
        data = await self._async_update_data()
        data["shopping_list"] = []
        await self.store.async_save(data)
        await self.async_request_refresh()
        # Also mark HA's default list complete items cleared (leave user list intact
        # unless the shopping_list integration exposes complete/clear services).
        _LOGGER.info("Cleared internal shopping list")

    # ---- Recipes ----------------------------------------------------------------

    async def get_recipes(self, count: int = 5) -> list[dict[str, Any]]:
        data = await self._async_update_data()
        pantry_items = {k for k in data["pantry"].keys()}
        diet = data["config"].get(CONF_DIET_PREFERENCE, DEFAULT_DIET_PREFERENCE)
        scored_recipes = []
        for recipe in BUILT_IN_RECIPES:
            if diet != "none" and diet not in recipe.get("diet", []):
                continue
            ingredients = set(ing.lower() for ing in recipe["ingredients"])
            matched = {ing for ing in ingredients
                       if ing in pantry_items or any(ing in p or p in ing for p in pantry_items)}
            missing = ingredients - matched
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

    # ---- Expiry helpers -----------------------------------------------------------

    def get_expiring_items(self, days: int | None = None) -> list[dict[str, Any]]:
        if days is None:
            days = self.expiry_warning_days
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
