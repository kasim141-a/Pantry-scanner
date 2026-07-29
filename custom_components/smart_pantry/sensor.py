"""Sensor platform for Smart Pantry Scanner."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, ENTITY_TOTAL_ITEMS, ENTITY_EXPIRING_SOON, ENTITY_EXPIRED,
    ENTITY_WASTE_PREVENTED, ENTITY_SAVINGS, ENTITY_SHOPPING_LIST_COUNT, ENTITY_WEEKLY_BUDGET_STATUS,
    ENTITY_SUGGESTIONS,
    CONF_HOUSEHOLD_NAME, CONF_CURRENCY, CONF_WEEKLY_BUDGET,
    DEFAULT_HOUSEHOLD_NAME, DEFAULT_CURRENCY, DEFAULT_WEEKLY_BUDGET,
)
from .coordinator import SmartPantryCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: SmartPantryCoordinator = hass.data[DOMAIN][entry.entry_id]
    household_name = coordinator.data.get("config", {}).get(CONF_HOUSEHOLD_NAME, DEFAULT_HOUSEHOLD_NAME)
    entities = [
        PantryTotalItemsSensor(coordinator, entry, household_name),
        PantryExpiringSoonSensor(coordinator, entry, household_name),
        PantryExpiredSensor(coordinator, entry, household_name),
        PantryWastePreventedSensor(coordinator, entry, household_name),
        PantrySavingsSensor(coordinator, entry, household_name),
        PantryShoppingListCountSensor(coordinator, entry, household_name),
        PantryWeeklyBudgetSensor(coordinator, entry, household_name),
        PantrySuggestionsSensor(coordinator, entry, household_name),
    ]
    async_add_entities(entities)


class SmartPantryBaseSensor(CoordinatorEntity[SmartPantryCoordinator], SensorEntity):
    """Base class for Smart Pantry sensors."""

    def __init__(self, coordinator: SmartPantryCoordinator, entry: ConfigEntry,
                 household_name: str, entity_id_suffix: str, name: str, icon: str,
                 unit: str | None = None) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{entity_id_suffix}"
        self._attr_name = f"Smart Pantry {household_name} {name}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_should_poll = False

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Smart Pantry Scanner",
            "manufacturer": "Smart Pantry",
            "model": "Smart Pantry Scanner",
            "entry_type": "service",
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class PantryTotalItemsSensor(SmartPantryBaseSensor):
    def __init__(self, coordinator, entry, household_name):
        super().__init__(coordinator, entry, household_name, ENTITY_TOTAL_ITEMS, "Total Items", "mdi:fridge")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get("pantry", {}))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        pantry = self.coordinator.data.get("pantry", {})
        categories, locations = {}, {}
        for item in pantry.values():
            cat = item.get("category", "other")
            loc = item.get("storage_location", "other")
            categories[cat] = categories.get(cat, 0) + 1
            locations[loc] = locations.get(loc, 0) + 1
        return {
            "categories": categories,
            "locations": locations,
            "last_updated": datetime.now().isoformat(),
            "low_stock_items": self.coordinator.get_low_stock_items(),
            "inventory": self.coordinator.get_inventory(),
            "inventory_value": self.coordinator.get_inventory_value(),
            "currency": self.coordinator.data.get("config", {}).get("currency", "USD"),
        }


class PantryExpiringSoonSensor(SmartPantryBaseSensor):
    def __init__(self, coordinator, entry, household_name):
        super().__init__(coordinator, entry, household_name, ENTITY_EXPIRING_SOON, "Expiring Soon", "mdi:alert-circle")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.get_expiring_items())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self.coordinator.get_expiring_items()
        return {
            "items": [{"name": i["name"], "quantity": i["quantity"], "unit": i["unit"],
                       "expiration_date": i.get("expiration_date"),
                       "days_until_expiry": i.get("days_until_expiry"),
                       "storage_location": i.get("storage_location")} for i in items[:10]],
            "total_expiring": len(items),
        }

    @property
    def icon(self) -> str:
        count = self.native_value
        if count == 0: return "mdi:check-circle"
        if count <= 2: return "mdi:alert-circle-outline"
        return "mdi:alert-circle"


class PantryExpiredSensor(SmartPantryBaseSensor):
    def __init__(self, coordinator, entry, household_name):
        super().__init__(coordinator, entry, household_name, ENTITY_EXPIRED, "Expired Items", "mdi:delete-alert")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.get_expired_items())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self.coordinator.get_expired_items()
        return {
            "items": [{"name": i["name"], "quantity": i["quantity"], "unit": i["unit"],
                       "expiration_date": i.get("expiration_date"),
                       "days_past_expiry": abs(i.get("days_until_expiry", 0))} for i in items],
            "total_expired": len(items),
        }


class PantryWastePreventedSensor(SmartPantryBaseSensor):
    def __init__(self, coordinator, entry, household_name):
        super().__init__(coordinator, entry, household_name, ENTITY_WASTE_PREVENTED, "Waste Prevented", "mdi:leaf", "lbs")

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.get("stats", {}).get("waste_prevented_lbs", 0), 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stats = self.coordinator.data.get("stats", {})
        return {
            "items_consumed": stats.get("items_consumed", 0),
            "items_wasted": stats.get("items_wasted", 0),
            "meals_cooked": stats.get("meals_cooked", 0),
            "items_scanned": stats.get("items_scanned", 0),
        }


class PantrySavingsSensor(SmartPantryBaseSensor):
    def __init__(self, coordinator, entry, household_name):
        currency = coordinator.data.get("config", {}).get(CONF_CURRENCY, DEFAULT_CURRENCY)
        super().__init__(coordinator, entry, household_name, ENTITY_SAVINGS, "Savings", "mdi:piggy-bank", currency)

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.get("stats", {}).get("money_saved", 0), 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stats = self.coordinator.data.get("stats", {})
        meals = stats.get("meals_cooked", 0)
        avg_saving = round(self.native_value / meals, 2) if meals > 0 else 0
        return {"meals_cooked": meals, "avg_saving_per_meal": avg_saving, "estimated_monthly_savings": round(self.native_value * 4.3, 2)}


class PantryShoppingListCountSensor(SmartPantryBaseSensor):
    def __init__(self, coordinator, entry, household_name):
        super().__init__(coordinator, entry, household_name, ENTITY_SHOPPING_LIST_COUNT, "Shopping List", "mdi:cart")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get("shopping_list", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self.coordinator.data.get("shopping_list", [])
        return {
            "items": [{"name": i["name"], "quantity": i["quantity"], "unit": i["unit"],
                       "notes": i.get("notes"), "purchased": i.get("purchased", False)} for i in items],
            "total_items": len(items),
            "estimated_cost": round(len(items) * 3.5, 2),
        }


class PantrySuggestionsSensor(SmartPantryBaseSensor):
    """Suggested shopping list additions from low stock and expiring items."""

    def __init__(self, coordinator, entry, household_name):
        super().__init__(coordinator, entry, household_name, ENTITY_SUGGESTIONS, "Shopping Suggestions", "mdi:cart-plus")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.get_suggestions())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        suggestions = self.coordinator.get_suggestions()
        return {
            "suggestions": suggestions,
            "low_stock_threshold": self.coordinator.low_stock_threshold,
            "expiry_warning_days": self.coordinator.expiry_warning_days,
            "auto_add_to_ha_shopping_list": self.coordinator.auto_add_to_ha_list,
        }

    @property
    def icon(self) -> str:
        return "mdi:cart-plus" if self.native_value > 0 else "mdi:cart-check"


class PantryWeeklyBudgetSensor(SmartPantryBaseSensor):
    def __init__(self, coordinator, entry, household_name):
        super().__init__(coordinator, entry, household_name, ENTITY_WEEKLY_BUDGET_STATUS, "Weekly Budget", "mdi:wallet", "%")

    def _estimated_spent(self) -> float:
        """Prefer real prices; items without a price fall back to 2.5 each."""
        pantry = self.coordinator.data.get("pantry", {})
        spent = 0.0
        for item in pantry.values():
            price = item.get("price")
            if price is not None:
                try:
                    spent += float(price) * max(0.0, float(item.get("quantity", 0)))
                    continue
                except (TypeError, ValueError):
                    pass
            spent += 2.5
        return round(spent, 2)

    @property
    def native_value(self) -> int:
        budget = self.coordinator.data.get("config", {}).get(CONF_WEEKLY_BUDGET, DEFAULT_WEEKLY_BUDGET)
        spent = self._estimated_spent()
        return min(100, int((spent / budget) * 100)) if budget > 0 else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        budget = self.coordinator.data.get("config", {}).get(CONF_WEEKLY_BUDGET, DEFAULT_WEEKLY_BUDGET)
        spent = self._estimated_spent()
        return {
            "weekly_budget": budget,
            "estimated_spent": spent,
            "remaining": round(max(0, budget - spent), 2),
            "currency": self.coordinator.data.get("config", {}).get(CONF_CURRENCY, DEFAULT_CURRENCY),
        }
