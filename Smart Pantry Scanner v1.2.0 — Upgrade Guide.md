# Smart Pantry Scanner v1.2.0 — Upgrade Guide

This guide explains what was fixed and added compared with your installed version (`b21ad68`), and exactly how to apply the update to your Home Assistant instance.

## Why you saw "Entity not found"

Your card configuration pointed at `sensor.smart_pantry_inventory` and `sensor.smart_pantry_recipes`, but the integration never creates those entities. Because you assigned the device to the **Kitchen** area with a household name of **My Home**, your real sensors are named like:

> `sensor.smart_pantry_scanner_smart_pantry_my_home_total_items`

The old card also derived its sibling sensors by replacing the string `total_items` inside the configured entity ID, so a single wrong ID broke the entire card. Version 1.2.0 removes this fragility: the card **auto-discovers** any Smart Pantry `…_total_items` sensor and resolves all sibling sensors from it, so the minimal working configuration is now simply:

```yaml
type: custom:smart-pantry-card
```

Even an incorrect `entity:` value now falls back to auto-discovery instead of failing.

## What's new in v1.2.0

| Area | Change |
|---|---|
| Card | Entity auto-discovery; no `entity:` required |
| Suggestions | New `…_shopping_suggestions` sensor combining **low-stock** and **expiring** items, deduplicated against items already on the shopping list |
| Card main view | New "💡 Suggested for Shopping List" panel with per-item **Add** buttons and an **Add all** button |
| Scanning | Global keyboard-wedge capture: a Bluetooth/USB scanner works anywhere in the Scan view, even if the text box is not focused; mobile camera scanning via ZXing unchanged (HTTPS required) |
| Scan feedback | Scan results now report `low_stock`, `expiring`, and `suggest_shopping_list`; the card shows an "Add to Shopping List?" prompt, or an "automatically added" banner if you enable auto-add |
| Barcode lookup | Unknown barcodes are now resolved through the free Open Food Facts API before falling back to "Unknown Item (barcode)" |
| Recipes | New `smart_pantry.add_recipe_missing_to_shopping_list` service; matching is slightly fuzzier (substring match, e.g. "tomatoes" matches "tomato"); fully-matched recipes get a "Mark cooked" button that consumes ingredients |
| Consumption | `mark_consumed` fires a `smart_pantry_low_stock` event (and optionally auto-adds to the Shopping List) when an item runs low or out |
| HA Shopping List | All additions go through one backend path that mirrors into HA's default `shopping_list`; duplicates are avoided and a clear warning is logged if the Shopping List integration is missing |
| Options | New settings: **Low Stock Threshold**, **Expiry Warning Days**, and **Auto-add to HA Shopping List**; changing options now reloads the integration automatically |
| Services | New `smart_pantry.sync_suggestions_to_shopping_list` for automations (e.g. nightly sync) |

## How to update

1. **Backend** — replace the folder `config/custom_components/smart_pantry/` with the one from this package, then restart Home Assistant.
2. **Card** — replace `config/www/smart-pantry-card.js` with the new file, then hard-refresh your browser (Ctrl+Shift+R) or bump the resource URL to `/local/smart-pantry-card.js?v=1.2.0` to bust the cache.
3. **Card config** — simplify it to:

   ```yaml
   type: custom:smart-pantry-card
   title: 🥦 Smart Pantry
   ```

4. **Shopping List** — make sure HA's built-in Shopping List integration is enabled (Settings → Devices & Services → Add Integration → Shopping List, or `shopping_list:` in `configuration.yaml`).
5. **Options** — open Settings → Devices & Services → Smart Pantry Scanner → Configure to set your low-stock threshold (your old card config used `2`), expiry warning days (`3`), and whether suggestions should be added to the Shopping List automatically.
6. Optionally add the automations from `custom_components/smart_pantry/example_automations.yaml`, replacing entity IDs with yours (e.g. `sensor.smart_pantry_scanner_smart_pantry_my_home_shopping_suggestions`).

## How each of your requirements is met

**Add items to recipes from the pantry.** Pressing **🍳 Recipes** calls `smart_pantry.get_recipes`, which scores every recipe against your pantry contents and returns matched and missing ingredients. Ingredients you own appear as green chips; one tap on "Add missing to list" pushes everything you lack onto both shopping lists via `add_recipe_missing_to_shopping_list`.

**Suggest shopping list additions when low in stock or expiring.** The new suggestions sensor continuously evaluates your pantry against the configurable low-stock threshold and expiry window. The card surfaces these in the "Suggested for Shopping List" panel, and the `sync_suggestions_to_shopping_list` service lets automations push them on a schedule.

**Suggest when scanned.** Every scan fires `smart_pantry_scan_result` with `suggest_shopping_list: true` whenever the scanned item is low or expiring; the card then prompts you inline, or adds it silently when auto-add is enabled.

**Scan input via mobile camera or scanner.** The camera path uses ZXing in the browser (works in the HA Companion app or any browser over HTTPS). Bluetooth and USB scanners act as keyboards, and the card now captures their fast keystroke bursts globally in the Scan view — no need to tap the input box first. ESPHome or HA tag scanners can be wired in with the provided `tag_scanned` example automation.

**Use HA's default Shopping List.** All shopping-list additions are mirrored into the built-in `shopping_list` integration through a single backend code path, so your list appears in the standard HA Shopping List panel, the Companion app, and any voice assistants connected to it.

## Verification performed

All Python modules compile cleanly, JSON/YAML files validate, and the card passes 22 headless-browser tests covering auto-discovery, the suggestions panel, recipe rendering and missing-ingredient adds, manual barcode entry, keyboard-wedge capture, and scan-prompt behavior. The coordinator passes 10 unit tests covering low-stock and expiry suggestion logic, combined reasons, shopping-list sync and deduplication, graceful handling when the Shopping List integration is missing, recipe missing-ingredient service, known/unknown barcode scanning (including offline fallback), and low-stock events on consumption.
