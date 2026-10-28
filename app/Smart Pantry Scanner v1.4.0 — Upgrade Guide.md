# Smart Pantry Scanner v1.4.0 — Upgrade Guide

This release addresses the three points you raised: the buttons that vanished in your desktop browser, item picture representation, and the mobile camera behaviour. All 16 backend tests and 47 card UI tests pass.

## 1. Why buttons "disappeared" in the browser (and how it's now impossible to miss)

The 📦 Inventory and 🛒 Add-all buttons exist in card v1.3.x and were never removed — your desktop browser was serving a **cached older copy** of `smart-pantry-card.js` from before those buttons existed, while the Companion App had already refreshed its cache. That is why the same dashboard looked different in two places.

Two things fix and prevent this:

1. After copying the new card file, set the dashboard resource URL to `/local/smart-pantry-card.js?v=1.4.0` (Settings → Dashboards → ⋮ → Resources). Changing the `?v=` query string forces every browser to fetch the new file.
2. The card now renders a small **version footer** ("Smart Pantry Card v1.4.0") at the bottom of the main view. If the footer shows an older number than you installed, that browser is running a stale cache — hard-refresh (Ctrl+Shift+R) or, in the Companion App, Settings → Companion App → Debugging → **Reset frontend cache**.

## 2. Item pictures and icons

Every item list in the card — suggestions, expiring soon, shopping list, the full Inventory view, and the Last Scan result — now shows a 36 px **picture avatar** for each item:

| Situation | What is shown |
|---|---|
| Item scanned by barcode and found on Open Food Facts | The real **product photo**, fetched and stored automatically |
| Item added manually or photo unavailable | Its **category emoji** (🥬 produce, 🥛 dairy, 🍗 meat, 🦐 seafood, 🍞 bakery, 🥫 pantry, 🧊 frozen, 🥤 beverages, 🧂 condiments, 🍿 snacks, 📦 other) |
| Product photo fails to load | Falls back to the category emoji automatically |

You can also set or change a picture yourself: the `smart_pantry.add_item` and `smart_pantry.update_item` services accept a new optional `image_url` field (an empty string clears it). Existing items keep working — they simply show their category emoji until they are re-scanned or given an image.

Note: photos are served from `images.openfoodfacts.org`, so they display whenever the viewing device has internet access.

## 3. Mobile camera scanning

On your current HTTP connection, the WebView cannot provide a live video stream (this is a browser security rule, not an app setting), so **📸 Take Photo** — which uses the phone's native camera app — remains the scanning path there. The photo is decoded instantly on return and now also shows the product photo in the Last Scan panel.

To get the **📷 Live Scan** continuous viewfinder on your phone, point the Companion App at an HTTPS URL (Settings → Companion App → your server → use your Nabu Casa `https://…ui.nabu.casa` address or any TLS reverse proxy). The Live Scan button appears automatically once the connection is secure.

## How to update

1. **Backend:** replace `config/custom_components/smart_pantry/` with the version from the attached zip, then restart Home Assistant. (Required — the product-image support lives in the integration.)
2. **Card:** replace `/config/www/smart-pantry-card.js` with the attached file, transferred **as a file** (correct `md5sum`: `406d1f8e5ff7638a4ffa72777fb4fe77`).
3. Update the resource URL to `/local/smart-pantry-card.js?v=1.4.0` and hard-refresh each browser; reset frontend cache in the Companion App.
4. Verify the footer reads **Smart Pantry Card v1.4.0** on every device.

Your pantry data, options, and dashboards carry over unchanged.
