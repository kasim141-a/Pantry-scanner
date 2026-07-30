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

import aiohttp

from .const import (
    DOMAIN, STORAGE_KEY_PANTRY, STORAGE_VERSION,
    BUILT_IN_RECIPES, BARCODE_DB,
    OFF_API_URL, OFF_API_URL_V0, OFF_TIMEOUT, OFF_USER_AGENT,
    OFF_CATEGORY_MAP, CATEGORY_DEFAULT_EXPIRY_DAYS,
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
            # Personal learned-products catalog (barcode -> product info), like
            # MyPantryTracker's "Archive Items": once a barcode is resolved or
            # named by the user, future scans resolve instantly and offline.
            "product_library": {},
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
                       notes: str | None = None, price: float | None = None,
                       image_url: str | None = None) -> None:
        data = await self._async_update_data()
        key = name.lower().strip()
        item = {
            "name": name, "quantity": quantity, "unit": unit,
            "category": category, "expiration_date": expiration_date,
            "storage_location": storage_location, "barcode": barcode,
            "notes": notes, "price": price, "image_url": image_url,
            "added_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        if key in data["pantry"]:
            existing = data["pantry"][key]
            item["quantity"] = existing["quantity"] + quantity
            item["added_at"] = existing.get("added_at", item["added_at"])
            item["notes"] = notes or existing.get("notes")
            item["price"] = price if price is not None else existing.get("price")
            item["image_url"] = image_url or existing.get("image_url")
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
                          notes: str | None = None, price: float | None = None,
                          image_url: str | None = None) -> None:
        data = await self._async_update_data()
        key = name.lower().strip()
        if key not in data["pantry"]:
            _LOGGER.warning("Item not found for update: %s", name)
            return
        item = data["pantry"][key]
        if quantity is not None:
            item["quantity"] = quantity
            # Setting quantity to zero removes the item.
            if quantity <= 0:
                del data["pantry"][key]
                await self.store.async_save(data)
                await self.async_request_refresh()
                _LOGGER.info("Removed pantry item via zero quantity: %s", name)
                return
        if unit is not None: item["unit"] = unit
        if category is not None: item["category"] = category
        if expiration_date is not None: item["expiration_date"] = expiration_date
        if storage_location is not None: item["storage_location"] = storage_location
        if notes is not None: item["notes"] = notes
        if price is not None: item["price"] = price
        if image_url is not None: item["image_url"] = image_url or None
        item["updated_at"] = datetime.now().isoformat()
        await self.store.async_save(data)
        await self.async_request_refresh()
        _LOGGER.info("Updated pantry item: %s", name)

    # ---- Barcode scanning ------------------------------------------------------

    async def _lookup_barcode(self, barcode: str) -> dict[str, Any]:
        """Look up a barcode: personal library, built-in DB, Open Food Facts, else Unknown."""
        # 1. Personal learned-products library (fast, offline, user-curated).
        data = await self._async_update_data()
        library = data.get("product_library") or {}
        if barcode in library:
            entry = dict(library[barcode])
            entry.setdefault("typical_expiry_days",
                             CATEGORY_DEFAULT_EXPIRY_DAYS.get(entry.get("category", "other"), 30))
            entry["source"] = "library"
            return entry
        # 2. Built-in database.
        if barcode in BARCODE_DB:
            return dict(BARCODE_DB[barcode])
        # 3. Open Food Facts (free, no API key). OFF requires a User-Agent header;
        #    without one it rejects requests, which is why lookups used to fail.
        product = await self._off_fetch(barcode)
        if product:
            return product
        unknown = dict(BARCODE_DB["0000000000000"])
        unknown["name"] = f"Unknown Item ({barcode})" if barcode else "Unknown Item"
        unknown["lookup_failed"] = True
        return unknown

    async def _off_fetch(self, barcode: str) -> dict[str, Any] | None:
        """Fetch product info from Open Food Facts, trying the v2 then v0 API."""
        try:
            session = async_get_clientsession(self.hass)
        except Exception as err:  # noqa: BLE001 - degrade gracefully with no network
            _LOGGER.warning("Could not get HTTP session for OFF lookup: %s", err)
            return None
        headers = {"User-Agent": OFF_USER_AGENT}
        timeout = aiohttp.ClientTimeout(total=OFF_TIMEOUT)
        for url_tpl in (OFF_API_URL, OFF_API_URL_V0):
            url = url_tpl.format(barcode=barcode)
            try:
                async with session.get(url, headers=headers, timeout=timeout) as resp:
                    if resp.status != 200:
                        _LOGGER.warning(
                            "Open Food Facts returned HTTP %s for barcode %s (%s)",
                            resp.status, barcode, url,
                        )
                        continue
                    payload = await resp.json()
            except Exception as err:  # noqa: BLE001 - network failures are non-fatal
                _LOGGER.warning("Open Food Facts lookup failed for %s via %s: %s",
                                barcode, url, err)
                continue
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
                image_url = (product.get("image_front_small_url")
                             or product.get("image_front_url")
                             or product.get("image_url"))
                return {
                    "name": name,
                    "category": category,
                    "typical_expiry_days": CATEGORY_DEFAULT_EXPIRY_DAYS.get(category, 30),
                    "source": "openfoodfacts",
                    "image_url": image_url,
                }
            _LOGGER.info("Open Food Facts has no product data for barcode %s", barcode)
            return None
        return None

    async def _learn_product(self, barcode: str, name: str, category: str,
                             unit: str | None = None, price: float | None = None,
                             image_url: str | None = None) -> None:
        """Remember a barcode->product mapping in the personal library."""
        if not barcode or not name or name.lower().startswith("unknown item"):
            return
        data = await self._async_update_data()
        library = data.setdefault("product_library", {})
        entry = library.get(barcode, {})
        entry.update({
            "name": name,
            "category": category or entry.get("category", "other"),
            "typical_expiry_days": CATEGORY_DEFAULT_EXPIRY_DAYS.get(category or "other", 30),
        })
        if unit: entry["unit"] = unit
        if price is not None: entry["price"] = price
        if image_url: entry["image_url"] = image_url
        library[barcode] = entry
        await self.store.async_save(data)
        _LOGGER.info("Learned product %s for barcode %s", name, barcode)

    async def scan_barcode(self, barcode: str, quantity: float = 1,
                           expiration_date: str | None = None,
                           price: float | None = None) -> None:
        """Scan a barcode from camera, BT/USB scanner, or manual input."""
        barcode = (barcode or "").strip()
        if not barcode:
            # Guard: an empty barcode must never create "Unknown Item ()".
            _LOGGER.warning("Ignoring scan with empty barcode")
            self.hass.bus.async_fire(f"{DOMAIN}_scan_result", {
                "barcode": "", "error": "empty_barcode",
                "item_name": None, "suggest_shopping_list": False,
            })
            return
        product = await self._lookup_barcode(barcode)
        name = product["name"]
        if expiration_date is None:
            expiry = datetime.now() + timedelta(days=product["typical_expiry_days"])
            expiration_date = expiry.strftime("%Y-%m-%d")
        await self.add_item(name=name, quantity=quantity, category=product["category"],
                            expiration_date=expiration_date, barcode=barcode, price=price,
                            image_url=product.get("image_url"))
        # Learn successfully resolved products so future scans work offline.
        if not product.get("lookup_failed"):
            await self._learn_product(barcode, name, product["category"],
                                      price=price, image_url=product.get("image_url"))
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
            "image_url": item.get("image_url"),
            "lookup_failed": bool(product.get("lookup_failed")),
        })

    async def rename_item(self, old_name: str, new_name: str) -> None:
        """Rename a pantry item, keeping all its data; learns the barcode mapping."""
        new_name = (new_name or "").strip()
        if not new_name:
            _LOGGER.warning("rename_item called with empty new name")
            return
        data = await self._async_update_data()
        old_key = old_name.lower().strip()
        if old_key not in data["pantry"]:
            _LOGGER.warning("Item not found for rename: %s", old_name)
            return
        item = data["pantry"].pop(old_key)
        new_key = new_name.lower()
        if new_key in data["pantry"]:
            # Merge quantities if the target name already exists.
            existing = data["pantry"][new_key]
            existing["quantity"] = existing.get("quantity", 0) + item.get("quantity", 0)
            existing["barcode"] = existing.get("barcode") or item.get("barcode")
            existing["image_url"] = existing.get("image_url") or item.get("image_url")
            item = existing
        else:
            item["name"] = new_name
            data["pantry"][new_key] = item
        item["updated_at"] = datetime.now().isoformat()
        await self.store.async_save(data)
        await self.async_request_refresh()
        # Teach the library so this barcode resolves to the user's name next time.
        if item.get("barcode"):
            await self._learn_product(item["barcode"], new_name,
                                      item.get("category", "other"),
                                      unit=item.get("unit"), price=item.get("price"),
                                      image_url=item.get("image_url"))
        _LOGGER.info("Renamed pantry item: %s -> %s", old_name, new_name)

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
        # Use the real item price for savings when known, else fall back to 3.0.
        try:
            saved = float(item.get("price") or 3.0) * quantity
        except (TypeError, ValueError):
            saved = 3.0
        data["stats"]["money_saved"] = data["stats"].get("money_saved", 0) + saved
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
             "category": i.get("category", "other"), "image_url": i.get("image_url")}
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
                "category": item.get("category", "other"),
                "image_url": item.get("image_url"),
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
                    "category": item.get("category", "other"),
                    "image_url": item.get("image_url"),
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
        # Names of items expiring soon, to badge "use it up" recipes.
        expiring_names = {(i.get("name") or "").lower()
                          for i in self.get_expiring_items()}
        scored_recipes = []
        for recipe in BUILT_IN_RECIPES:
            if diet != "none" and diet not in recipe.get("diet", []):
                continue
            ingredients = set(ing.lower() for ing in recipe["ingredients"])
            matched = {ing for ing in ingredients
                       if ing in pantry_items or any(ing in p or p in ing for p in pantry_items)}
            missing = ingredients - matched
            match_pct = len(matched) / len(ingredients) * 100 if ingredients else 0
            uses_expiring = sorted(
                ing for ing in matched
                if any(ing in e or e in ing for e in expiring_names if e)
            )
            scored_recipes.append({
                "name": recipe["name"], "time": recipe["time"],
                "match_percent": round(match_pct, 1),
                "matched_ingredients": sorted(list(matched)),
                "missing_ingredients": sorted(list(missing)),
                "total_ingredients": len(ingredients),
                "uses_expiring": uses_expiring,
            })
        # Recipes that use up expiring food rank first (waste reduction),
        # then by pantry match percentage.
        scored_recipes.sort(key=lambda x: (len(x["uses_expiring"]) > 0, x["match_percent"]),
                            reverse=True)
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

    def get_inventory(self) -> list[dict[str, Any]]:
        """Full inventory with computed expiry info, sorted by name."""
        data = self.data or {}
        now = datetime.now()
        inventory = []
        for item in data.get("pantry", {}).values():
            entry = {
                "name": item.get("name"),
                "quantity": item.get("quantity", 0),
                "unit": item.get("unit", "piece"),
                "category": item.get("category", "other"),
                "storage_location": item.get("storage_location", "pantry"),
                "expiration_date": item.get("expiration_date"),
                "price": item.get("price"),
                "barcode": item.get("barcode"),
                "notes": item.get("notes"),
                "image_url": item.get("image_url"),
                "days_until_expiry": None,
            }
            if entry["expiration_date"]:
                try:
                    exp = datetime.strptime(entry["expiration_date"], "%Y-%m-%d")
                    entry["days_until_expiry"] = (exp - now).days
                except ValueError:
                    pass
            inventory.append(entry)
        inventory.sort(key=lambda i: (i["name"] or "").lower())
        return inventory

    def get_inventory_value(self) -> float:
        """Total value of priced pantry stock (price treated as per-unit)."""
        data = self.data or {}
        total = 0.0
        for item in data.get("pantry", {}).values():
            price = item.get("price")
            if price is not None:
                try:
                    total += float(price) * max(0.0, float(item.get("quantity", 0)))
                except (TypeError, ValueError):
                    continue
        return round(total, 2)
