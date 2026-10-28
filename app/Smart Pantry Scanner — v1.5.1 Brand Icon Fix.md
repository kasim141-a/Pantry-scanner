# Smart Pantry Scanner — v1.5.1 Brand Icon Fix

## Why the icon showed as "icon not available"

Home Assistant does not read an `icon.png` placed loosely in the integration folder. Historically, integration icons could **only** come from the central [home-assistant/brands](https://github.com/home-assistant/brands) repository, which requires a GitHub pull request and review.

That changed in **Home Assistant 2026.3**: custom integrations can now ship their own brand images locally in a `brand/` directory inside the integration folder, and these automatically take priority over the brands CDN ([announcement](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api/)).

## What v1.5.1 adds

The integration now includes the complete brand image set, derived from the project's green pantry-basket-and-barcode artwork:

```
custom_components/smart_pantry/
└── brand/
    ├── icon.png      (256 x 256)
    ├── icon@2x.png   (512 x 512)
    ├── logo.png      (256 x 256)
    └── logo@2x.png   (512 x 512)
```

Home Assistant serves these through its local brands API (`/api/brands/integration/smart_pantry/icon.png`), caches them on disk, and shows them on the Integrations page, config flows, and device pages — no extra configuration needed.

## How to update

1. Replace the `custom_components/smart_pantry/` folder in `/config/custom_components/` with the one from `Pantry-scanner-v1.5.1.zip` (the only functional change from v1.5.0 is the new `brand/` folder plus version bumps).
2. Restart Home Assistant.
3. Open **Settings → Devices & Services** — the Smart Pantry Scanner tile should now show the green basket icon. If you still see the placeholder, hard-refresh the browser (Ctrl+Shift+R); the frontend caches brand images aggressively.

## Requirements

Local brand images need **Home Assistant 2026.3 or newer**. On older versions the only route is submitting the icon to the central brands repository — I can prepare that PR-ready file set if your HA is older, but any current 2026.x install supports the local method.

No card update is strictly required — the card file only had its version string bumped to 1.5.1 for consistency (md5 `694bb05946415b0e9f05beebed0289cc`). All 22 backend and 64 card test assertions still pass.
