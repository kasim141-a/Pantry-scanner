# 🥦 Smart Pantry Scanner

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)
[![Version](https://img.shields.io/badge/version-1.4.0-orange.svg)](https://github.com/kasim141-a/Pantry-scanner)

A Home Assistant custom integration for kitchen inventory management with barcode scanning, recipe suggestions from your pantry, and smart shopping list suggestions that sync with Home Assistant's built-in **Shopping List**.

## Features

| Feature | Description |
|---|---|
| Pantry inventory | Track items with quantity, unit, category, storage location, expiry date, and **price** |
| Inventory browser | **New in 1.3:** a full 📦 Inventory view with search, category filters, ± quantity steppers, and inline editing of every field |
| Barcode scanning | Mobile camera (ZXing), Bluetooth/USB keyboard-wedge scanners, or manual entry |
| Product lookup | Built-in barcode database plus automatic **Open Food Facts** fallback for unknown barcodes |
| Item pictures & icons | **New in 1.4:** every item shows a visual avatar — the real **product photo** (fetched automatically from Open Food Facts when you scan a barcode, or set manually via `image_url`) with a category emoji fallback |
| Recipes from pantry | Press **Recipes** to score built-in recipes against what you have; add missing ingredients to the shopping list with one tap |
| Shopping suggestions | Items that are **low in stock** or **expiring soon** are surfaced automatically, with one-tap or bulk add |
| Scan-triggered prompts | When a scanned item is low or expiring, the card prompts (or automatically adds) it to the shopping list |
| HA Shopping List sync | Every shopping list addition is mirrored into Home Assistant's default `shopping_list` integration |
| Waste & savings stats | Track meals cooked, waste prevented, and estimated savings against a weekly budget — savings and budget use **real item prices** when set |

## Installation

### 1. Enable Home Assistant's Shopping List

The integration syncs with HA's built-in Shopping List. Enable it either through **Settings → Devices & Services → Add Integration → Shopping List**, or by adding this line to `configuration.yaml`:

```yaml
shopping_list:
```

### 2. Install the integration

**HACS (recommended):** add this repository as a custom repository (type: Integration), install, and restart Home Assistant.

**Manual:** copy `custom_components/smart_pantry/` into your HA `config/custom_components/` directory and restart.

Then go to **Settings → Devices & Services → Add Integration → Smart Pantry Scanner** and configure:

| Option | Default | Meaning |
|---|---|---|
| Household Name | My Home | Used in entity names |
| Currency / Weekly Budget | USD / 120 | Budget tracking |
| Dietary Preference | none | Filters recipe suggestions |
| Low Stock Threshold | 1 | Suggest restock at or below this quantity |
| Expiry Warning Days | 3 | Suggest replacement within this many days of expiry |
| Auto-add to HA Shopping List | off | When on, low/expiring scanned or consumed items are added to the Shopping List automatically without asking |

All options can be changed later via **Configure** on the integration.

### 3. Install the Lovelace card

Copy `www/smart-pantry-card.js` to your HA `config/www/` folder, then add it as a dashboard resource (**Settings → Dashboards → ⋮ → Resources**):

```yaml
url: /local/smart-pantry-card.js
type: module
```

### 4. Add the card to a dashboard

The card now **auto-discovers** your Smart Pantry sensors, so the minimal config is just:

```yaml
type: custom:smart-pantry-card
```

If you have multiple pantry instances or want to pin an entity explicitly, point it at your `…_total_items` sensor (find the exact ID under **Settings → Devices & Services → Smart Pantry Scanner → Entities**; it usually looks like `sensor.smart_pantry_scanner_smart_pantry_my_home_total_items`):

```yaml
type: custom:smart-pantry-card
title: 🥦 Smart Pantry
entity: sensor.smart_pantry_scanner_smart_pantry_my_home_total_items
```

> The previous "Entity not found" error was caused by configuring a non-existent entity such as `sensor.smart_pantry_inventory`. As of v1.2.0 the card resolves entities automatically, and even a wrong `entity:` value falls back to auto-discovery.

## Using the card

**Main view** shows your stats, weekly budget, a **💡 Suggested for Shopping List** panel (low-stock and expiring items with per-item **🛒 Add** buttons and an **Add all** button), the expiring-soon list, categories, the current shopping list, and total stock value when prices are set. Every item row displays a picture avatar: the product photo when known, otherwise its category emoji. A small **version footer** at the bottom of the card shows which card version your browser is actually running — if it shows an older version than you installed, your browser is serving a **cached copy**: bump the resource URL (e.g. `/local/smart-pantry-card.js?v=1.4.0`) and hard-refresh (Ctrl+Shift+R), or in the Companion App use Settings → Companion App → Debugging → Reset frontend cache. A stale cache is also why buttons added in newer versions (such as 📦 Inventory or 🛒 Add all) can seem to “disappear” in one browser while showing in another.

**📦 Inventory** (new in 1.3) lists every pantry item with a search box and category filter chips. Each row has **− / +** steppers for one-tap quantity changes (stepping to zero asks for confirmation and removes the item) and a **✏️ edit** button that opens an inline form where you can change the **quantity, unit, category, storage location, price, and expiry date**, consume one unit, or delete the item entirely.

**🍳 Recipes** scores recipes against your pantry, shows matched (green) and missing (grey) ingredients, and lets you add all missing ingredients of a recipe to the shopping list in one tap — this uses the `smart_pantry.add_recipe_missing_to_shopping_list` service so both the pantry list and HA's Shopping List stay in sync. Recipes you can fully cook offer a **Mark cooked** button that consumes the matched ingredients.

**📷 Scan** supports four input methods:

1. **Bluetooth/USB scanner** — these behave as keyboards ("keyboard wedge"). Just scan while the Scan view is open; the card captures fast keystroke bursts ending in Enter even when the text field is not focused.
2. **Mobile camera — Live Scan** — tap **📷 Live Scan** for continuous viewfinder scanning (requires HTTPS, e.g. a Nabu Casa remote URL or a reverse proxy with TLS; the HA Companion app on an HTTPS URL works too).
3. **Mobile camera — Take Photo** — **new in 1.3.1:** tap **📸 Take Photo of Barcode** to open your phone's native camera app, snap a picture of the barcode, and the card decodes it locally (multiple scales and rotations are tried automatically). This works in **every** app and browser — including the Companion App over plain HTTP — because it does not need the WebView camera API.
4. **Manual entry** — type the barcode and press Submit. Optional **Quantity** and **Price** fields next to the input apply to whichever scan method you use.

### Camera troubleshooting (Companion App)

If **Live Scan** is unavailable, the card now tells you why: either the connection is not HTTPS (the WebView never exposes the live camera API over `http://` — the warning shows your current origin so you can check at a glance), or the app lacks Camera permission (Android: long-press the HA app icon → App info → Permissions → Camera → Allow; iOS: Settings → Home Assistant → Camera). In every such case, **📸 Take Photo of Barcode** still works: it delegates to the phone's native camera app, which needs no WebView camera API at all. To enable Live Scan in the Companion App, set the server URL (App Configuration → Servers) to your HTTPS/Nabu Casa address.

After each scan the item is added to the pantry, and if it is low in stock or expiring, the card either prompts **Add to Shopping List?** or adds it automatically when the auto-add option is enabled.

## Entities

| Entity (suffix) | Meaning |
|---|---|
| `…_total_items` | Pantry size, with category/location breakdown, `low_stock_items`, and the full `inventory` attribute (all items with price and expiry, plus `inventory_value`) |
| `…_expiring_soon` / `…_expired_items` | Items near or past expiry |
| `…_shopping_suggestions` | **New:** suggested additions (low stock + expiring), deduplicated against the current shopping list |
| `…_shopping_list` | Internal shopping list mirror |
| `…_savings`, `…_waste_prevented`, `…_weekly_budget` | Statistics |
| `button.…_get_recipes`, `button.…_clear_shopping_list`, `button.…_scan_demo_item` | Quick actions |

## Services

| Service | Purpose |
|---|---|
| `smart_pantry.add_item` / `update_item` / `remove_item` | Manage pantry items — all fields including `category` and `price` are editable; `update_item` with `quantity: 0` removes the item |
| `smart_pantry.scan_barcode` | Add an item by barcode (camera, scanner, ESPHome, automations); accepts optional `quantity` and `price` |
| `smart_pantry.get_recipes` | Fire a `smart_pantry_recipes_suggested` event with scored recipes |
| `smart_pantry.add_to_shopping_list` | Add to the pantry list **and** HA's default Shopping List |
| `smart_pantry.sync_suggestions_to_shopping_list` | **New:** push all current low-stock/expiring suggestions to both lists |
| `smart_pantry.add_recipe_missing_to_shopping_list` | **New:** add a recipe's missing ingredients to both lists (`recipe_name` required) |
| `smart_pantry.mark_consumed` | Decrease quantity; fires `smart_pantry_low_stock` when an item runs low or out |
| `smart_pantry.clear_shopping_list` | Clear the internal list (your HA Shopping List is left untouched) |

## Events (for automations)

| Event | Fired when | Useful data |
|---|---|---|
| `smart_pantry_scan_result` | After each scan | `item_name`, `low_stock`, `expiring`, `suggest_shopping_list`, `auto_added` |
| `smart_pantry_low_stock` | Consumption depletes an item or drops it below the threshold | `item_name`, `quantity`, `depleted` |
| `smart_pantry_recipes_suggested` | After `get_recipes` | `recipes` |
| `smart_pantry_suggestions_synced` | After bulk suggestion sync | `count` |

See `custom_components/smart_pantry/example_automations.yaml` for ready-made automations, including a nightly suggestion sync, scan-alert notifications, and forwarding barcodes from ESPHome/tag scanners.

## Barcode lookup

Scanned barcodes are resolved against the built-in database first, then against the free [Open Food Facts](https://world.openfoodfacts.org) API. Unknown barcodes are stored as `Unknown Item (<barcode>)` so you can rename them with `smart_pantry.update_item` or re-scan with details.

## License
MIT License
