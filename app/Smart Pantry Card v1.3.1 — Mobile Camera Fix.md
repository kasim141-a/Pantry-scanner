# Smart Pantry Card v1.3.1 — Mobile Camera Fix

## What your screenshot showed

The card correctly detected that your app's WebView does not expose `navigator.mediaDevices` — the browser API required for live viewfinder scanning. This is almost always because the Companion App is connected to Home Assistant over a plain `http://` address (an IP or `homeassistant.local:8123`): browsers and WebViews only make the camera API available on **secure (https) origins**, so no amount of app permissions can enable it there.

## The fix: photo-capture scanning

Rather than depending on the WebView API, v1.3.1 adds a **📸 Take Photo of Barcode** button that works on every connection and every app:

1. Tap the button — your phone's **native camera app** opens (this uses an HTML file input with `capture="environment"`, which never needs the WebView camera API).
2. Take a photo of the barcode — fill the frame with it, keep the phone flat and the label well lit.
3. The card decodes the photo locally with ZXing, automatically retrying at three resolutions and four rotations, then submits the barcode exactly like a live scan — including your optional Quantity and Price inputs, product lookup, and the low-stock/expiring shopping list prompt.

The camera section now also explains itself accurately:

| Situation | What you see |
|---|---|
| HTTPS + camera API available | **📷 Live Scan** (continuous viewfinder) and **📸 Take Photo** |
| HTTP connection | Warning showing your current origin, advising the HTTPS/Nabu Casa URL for live scanning — plus **📸 Take Photo**, which works anyway |
| HTTPS but WebView lacks the API | Warning pointing you to **📸 Take Photo** |

## Optional: enable Live Scan too

If you would like continuous viewfinder scanning as well, point the Companion App at a secure URL: open the app → **Settings → Companion App → your server → External URL** and use your Nabu Casa address (`https://…ui.nabu.casa`) or any TLS reverse-proxy URL. After reconnecting over HTTPS, the **📷 Live Scan** button appears automatically.

## How to update

Only the card file changed — no backend or HA restart needed:

1. Replace `/config/www/smart-pantry-card.js` with the attached file (transfer **as a file**; correct `md5sum`: `0695bc2f5ef956b4fdb92cd9555c8c62`).
2. Change the dashboard resource URL to `/local/smart-pantry-card.js?v=1.3.1`.
3. Hard-refresh — in the Companion App: **Settings → Companion App → Debugging → Reset frontend cache**, then reopen the dashboard. The console banner should read **SMART-PANTRY-CARD v1.3.1 loaded**.

All 42 automated card tests pass, including a new end-to-end test that decodes a real EAN-13 barcode photo through the new pipeline.
