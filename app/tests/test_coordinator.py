"""Focused regression tests for coordinator behavior without a running HA server."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest

import voluptuous as vol

ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, **attributes) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


class FakeStore:
    """In-memory asynchronous store that yields to expose write races."""

    def __init__(self, hass, version, key) -> None:
        self.data = None

    async def async_load(self):
        await asyncio.sleep(0)
        return deepcopy(self.data)

    async def async_save(self, data) -> None:
        await asyncio.sleep(0)
        self.data = deepcopy(data)


class FakeDataUpdateCoordinator:
    def __init__(self, hass, logger, **kwargs) -> None:
        self.data = None
        self.last_update_success = True

    def async_set_updated_data(self, data) -> None:
        self.data = data
        self.last_update_success = True


# Load the integration modules without importing Home Assistant itself.
package = _module("custom_components")
package.__path__ = [str(ROOT / "custom_components")]
integration_package = _module("custom_components.smart_pantry")
integration_package.__path__ = [str(ROOT / "custom_components" / "smart_pantry")]
_module("homeassistant")
_module("homeassistant.config_entries", ConfigEntry=object)
_module("homeassistant.core", HomeAssistant=object)
_module("homeassistant.helpers")
_module("homeassistant.helpers.aiohttp_client", async_get_clientsession=lambda hass: None)
_module("homeassistant.helpers.storage", Store=FakeStore)
_module(
    "homeassistant.helpers.update_coordinator",
    DataUpdateCoordinator=FakeDataUpdateCoordinator,
)
dt_module = _module("homeassistant.util.dt", now=datetime.now)
_module("homeassistant.util", dt=dt_module)


class FakeClientTimeout:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


_module("aiohttp", ClientTimeout=FakeClientTimeout)

from custom_components.smart_pantry.const import (  # noqa: E402
    CONF_CURRENCY,
    CONF_DIET_PREFERENCE,
    CONF_HOUSEHOLD_NAME,
    CONF_WEEKLY_BUDGET,
)
from custom_components.smart_pantry.coordinator import (  # noqa: E402
    SmartPantryCoordinator,
    _days_until_expiry,
)
from custom_components.smart_pantry.validation import (  # noqa: E402
    expiration_date,
    non_empty_string,
    non_negative_number,
    positive_number,
)


class FakeBus:
    def __init__(self) -> None:
        self.events = []

    def async_fire(self, event_type, data) -> None:
        self.events.append((event_type, data))


class FakeServices:
    def __init__(self) -> None:
        self.calls = []

    def has_service(self, domain, service) -> bool:
        return True

    async def async_call(self, domain, service, data, blocking=False) -> None:
        self.calls.append((domain, service, data, blocking))


class CoordinatorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.options = {
            CONF_HOUSEHOLD_NAME: "Test Home",
            CONF_CURRENCY: "USD",
            CONF_WEEKLY_BUDGET: 120,
            CONF_DIET_PREFERENCE: "none",
        }
        self.entry = SimpleNamespace(entry_id="test-entry", options=self.options)
        self.hass = SimpleNamespace(bus=FakeBus(), services=FakeServices())
        self.coordinator = SmartPantryCoordinator(self.hass, self.entry)

    def seed(self, data) -> None:
        self.coordinator.store.data = deepcopy(data)
        self.coordinator.data = deepcopy(data)

    def default_data(self):
        return self.coordinator._default_data()

    async def test_options_override_stale_stored_config_and_migrate_stats(self) -> None:
        stored = self.default_data()
        stored["config"].update({
            CONF_HOUSEHOLD_NAME: "Old Home",
            CONF_CURRENCY: "EUR",
            CONF_WEEKLY_BUDGET: 50,
            CONF_DIET_PREFERENCE: "vegan",
        })
        del stored["stats"]["items_scanned"]
        self.options.update({
            CONF_HOUSEHOLD_NAME: "New Home",
            CONF_CURRENCY: "GBP",
            CONF_WEEKLY_BUDGET: 200,
            CONF_DIET_PREFERENCE: "vegetarian",
        })
        self.seed(stored)

        loaded = await self.coordinator._async_update_data()

        self.assertEqual(loaded["config"][CONF_HOUSEHOLD_NAME], "New Home")
        self.assertEqual(loaded["config"][CONF_CURRENCY], "GBP")
        self.assertEqual(loaded["config"][CONF_WEEKLY_BUDGET], 200)
        self.assertEqual(loaded["config"][CONF_DIET_PREFERENCE], "vegetarian")
        self.assertEqual(loaded["stats"]["items_scanned"], 0)

    async def test_today_is_not_reported_as_expired(self) -> None:
        today = datetime.now().date()
        data = self.default_data()
        data["pantry"] = {
            "milk": {
                "name": "Milk",
                "quantity": 1,
                "unit": "l",
                "expiration_date": today.isoformat(),
            },
            "yogurt": {
                "name": "Yogurt",
                "quantity": 1,
                "unit": "piece",
                "expiration_date": (today - timedelta(days=1)).isoformat(),
            },
        }
        self.seed(data)

        expiring = {item["name"]: item for item in self.coordinator.get_expiring_items(3)}
        inventory = {item["name"]: item for item in self.coordinator.get_inventory()}

        self.assertEqual(expiring["Milk"]["days_until_expiry"], 0)
        self.assertEqual(inventory["Milk"]["days_until_expiry"], 0)
        self.assertEqual([item["name"] for item in self.coordinator.get_expired_items()], ["Yogurt"])

    async def test_recipe_exposes_actual_pantry_item_for_fuzzy_match(self) -> None:
        data = self.default_data()
        data["pantry"] = {
            "large brown eggs": {"name": "Large Brown Eggs", "quantity": 6},
            "rice": {"name": "Rice", "quantity": 1},
        }
        self.seed(data)

        recipes = await self.coordinator.get_recipes(50)
        recipe = next(item for item in recipes if item["name"] == "Egg Fried Rice")

        self.assertEqual(recipe["ingredient_items"]["egg"], "Large Brown Eggs")
        self.assertEqual(recipe["ingredient_items"]["rice"], "Rice")
        self.assertIn("egg", recipe["matched_ingredients"])

    async def test_duplicate_shopping_add_is_not_mirrored_twice(self) -> None:
        self.seed(self.default_data())

        await self.coordinator.add_to_shopping_list(" Milk ", 1, "l")
        await self.coordinator.add_to_shopping_list("milk", 1, "l")

        self.assertEqual(len(self.coordinator.data["shopping_list"]), 1)
        self.assertEqual(self.coordinator.data["shopping_list"][0]["name"], "Milk")
        self.assertEqual(len(self.hass.services.calls), 1)
        self.assertTrue(self.hass.services.calls[0][3])

    async def test_concurrent_additions_do_not_lose_items(self) -> None:
        self.seed(self.default_data())

        await asyncio.gather(
            self.coordinator.add_item("Milk"),
            self.coordinator.add_item("Eggs"),
            self.coordinator.add_item("Rice"),
        )

        self.assertEqual(set(self.coordinator.store.data["pantry"]), {"milk", "eggs", "rice"})

    async def test_concurrent_consumption_does_not_restore_quantity(self) -> None:
        data = self.default_data()
        data["pantry"]["rice"] = {
            "name": "Rice", "quantity": 3, "unit": "kg", "price": 2,
        }
        self.seed(data)

        await asyncio.gather(
            self.coordinator.mark_consumed("Rice", 1),
            self.coordinator.mark_consumed("Rice", 1),
        )

        self.assertEqual(self.coordinator.store.data["pantry"]["rice"]["quantity"], 1)
        self.assertEqual(self.coordinator.store.data["stats"]["items_consumed"], 2)

    async def test_invalid_expiry_is_ignored(self) -> None:
        self.assertIsNone(_days_until_expiry("not-a-date"))
        self.assertIsNone(_days_until_expiry(None))


class ValidationTest(unittest.TestCase):
    def test_strings_are_trimmed_and_blank_names_rejected(self) -> None:
        self.assertEqual(non_empty_string("  Milk  "), "Milk")
        with self.assertRaises(vol.Invalid):
            non_empty_string("   ")

    def test_quantities_must_be_finite_and_in_range(self) -> None:
        self.assertEqual(positive_number("1.5"), 1.5)
        self.assertEqual(non_negative_number(0), 0)
        for invalid in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(vol.Invalid):
                positive_number(invalid)
        with self.assertRaises(vol.Invalid):
            non_negative_number(-0.1)

    def test_expiration_requires_iso_calendar_date(self) -> None:
        self.assertEqual(expiration_date("2026-10-28"), "2026-10-28")
        for invalid in ("10/28/2026", "2026-02-30", "20261028"):
            with self.assertRaises(vol.Invalid):
                expiration_date(invalid)


if __name__ == "__main__":
    unittest.main()
