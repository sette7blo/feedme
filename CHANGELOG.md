# Changelog

All notable changes to Feedme will be documented here.
Versions follow [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`

- **MAJOR** — breaking changes (e.g. DB schema requires migration)
- **MINOR** — new features, backwards compatible
- **PATCH** — bug fixes, visual tweaks

---

## [Unreleased]

## [v1.5.1] — 2026-04-25

### Changed
- Cook Mode simplified to a wake lock toggle on the normal recipe drawer — keeps screen on while cooking without opening a fullscreen step-by-step overlay
- README: removed model recommendations table; PPQ model availability changes too frequently to maintain

### Fixed
- Image regeneration: actual API error messages now surfaced instead of generic "AI generation failed"
- Image regeneration: handle both `b64_json` and URL responses from different PPQ models
- Image regeneration: 60s timeout prevents indefinite hang on unresponsive model endpoints
- Image regeneration: non-DALL-E models now receive `size=1:1`; gpt-image-* family receives `quality=low`
- Image regeneration: recipe card and edit preview now update immediately in place after regen
- Image regeneration: saving after a regen no longer shows the old cached image; local images are cache-busted by `updated_at`

## [v1.5.0] — 2026-04-21

### Added
- Recipes: sort dropdown in filter bar (Newest / A-Z / Cook time)
- Recipes: "Showing X of Y recipes" count when filters or search are active
- Favorites: "Surprise me" button picks a random favorite and opens it
- Favorites: quick-add to meal plan button on cards (calendar icon, pick day + meal type)
- Favorites: "Last made X ago" / "Never cooked" shown on each card using cook log data
- Connections: Mealie card shows sync summary (e.g. "11 of 67 recipes exported")
- Connections: RSS feeds show imported recipe count per feed

### Changed
- Recipe card time and servings icons replaced from emoji to SVG line art for consistent cross-platform rendering
- Top-up: removed Lightning payment option; Monero checkout now opens in an embedded iframe instead of broken QR codes
- Top-up: removed ~300 lines of unused QR encoder code

### Fixed
- Recipe grid: filtering to zero results no longer shows "No recipes yet" onboarding message; shows "No recipes match your filters" with a clear-filters link instead

## [v1.4.0] — 2026-04-19

### Added
- Mealie export: browse your Feedme recipes in the Connections section, select and push to Mealie; already-exported recipes shown shaded with "In Mealie" tag
- Grocery list: each item now shows which recipe(s) it comes from as clickable tags; click opens the recipe drawer
- Meal planner: filled slots are now clickable to open the recipe detail drawer directly

### Changed
- Docker image switched from python:3.11-slim to python:3.11-alpine for smaller footprint
- SQLite performance pragmas: NORMAL synchronous, 8MB cache, memory temp store, 64MB mmap
- Cook Mode wake-lock videos extracted from inline base64 to separate cached files

### Fixed
- Grocery list: parenthetical sizes like "1 (24 ounce) jar marinara sauce" now parsed correctly as 24 oz instead of losing the unit
- Grocery list: "ounce"/"pound" spelled-out units now recognized (were only matching abbreviations oz/lb)
- Grocery list: oz treated as fluid ounces (volume) for sauces and liquids instead of weight; display respects original unit (cups stay cups, oz stays oz)
- Grocery list: unicode fractions like 2½ now parse correctly (was reading "2½" as 10.5 instead of 2.5)
- Grocery list: regenerating no longer creates duplicate entries from stale previous data

## [v1.3.0] — 2026-04-18

### Added
- Cook Mode: fullscreen step-by-step overlay launched from the recipe drawer; tap or swipe to advance through instructions, progress dots, ingredients panel toggle, wake lock to keep screen on
- Print view: printer-friendly recipe layout triggered from recipe drawer; ingredients in two columns, clean step list, hides all app chrome via @media print
- Dark mode: full dark colour scheme toggle in Settings → Appearance; preference saved to localStorage; respects system prefers-color-scheme on first visit
- Grocery list: items now grouped by category (Produce, Meat & Fish, Dairy & Eggs, Bakery, Dry Goods, Canned & Jarred, Frozen, Condiments & Spices); categories assigned by keyword lookup at insert time
- AI nutrition estimation: "Estimate nutrition" button in recipe drawer sends ingredient list to AI and populates calories, protein, fat, carbs; stored in recipe JSON; re-estimate available once filled
- Cook log: "Made It" button in recipe drawer logs cook date; history shown below instructions in drawer; add notes and serving count per entry
- AI week plan generator: "AI Plan" button in Planner opens modal with meal/dietary/pantry options; generates a weekly plan from your own recipe library; preview before accepting
- Meal plan templates: "Save Template" in Planner saves current week as a named template; load/delete templates from the panel below the week grid
- RSS auto-fetch: configurable auto-fetch interval (6h / 12h / daily / weekly) in the RSS Feeds card; background thread fetches all configured feeds on schedule
- Meal planner servings: each meal slot now shows a +/- stepper to set how many servings to cook; defaults to the recipe's base yield; grocery list scales quantities accordingly

### Fixed
- Grocery list: "garlic, minced" no longer mis-categorised as Meat & Fish; removed ambiguous "mince" keyword
- Grocery list: bare "oil" now correctly categorised as Condiments & Spices (was missed due to leading-space bug)
- Grocery list: similar ingredients (e.g. "garlic, minced" + "garlic cloves") now merge into one line with summed quantity
- Grocery list: quantities now display in friendly units (cups, tbsp, tsp, oz) instead of raw grams/ml; unit conversion simplified to single-base system (g/ml) with auto-display
- Grocery list: quantities were wrong (e.g. 6 eggs showing as 1.75) because meal plan defaulted to 1 serving instead of the recipe's base yield; fixed default and migrated existing entries
- Print view: recipe image now included at the top of the printed page
- Nutrition estimation: improved AI prompt with recipe name, explicit per-serving division, and realistic calorie range hints for more consistent results
- iOS: content no longer cut off at the bottom on devices with home indicator; uses dynamic viewport height and safe-area-inset padding

---

## [v1.2.0] — 2026-04-15

### Added
- Pantry: barcode scanner using Html5Qrcode (live camera) and Quagga2 (file upload); looks up product name and package size via Open Food Facts and pre-fills the add form
- Recipe drawer: serving stepper scales all ingredient quantities proportionally (session-only, original recipe unchanged)
- Recipe drawer: robot button overlaid on hero image to regenerate AI photo; only visible in edit mode; spinning robot + shimmer overlay while generating
- Recipes: Cook tonight filter — sage-green toggle in the filter bar that fetches pantry contents, shows ingredient coverage badge (e.g. 7/9 ingredients) on each card, hides recipes with no pantry matches, and sorts by coverage descending

### Changed
- Topbar redesigned to two-row layout: logo spans both rows, Add Recipe button on the first row, search bar on the second row — resolves crowding on narrow screens and iOS
- Sidebar section labels (Library, Discover, Planning) removed; replaced with plain hairline dividers
- Sidebar widened from 72px to 80px to prevent badge clipping
- Staging badge now hidden when count is zero

### Fixed
- Pantry scanner: Cancel button unresponsive when camera access is denied; modal now closes immediately in all cases
- Pantry scanner: added image upload fallback for devices where live camera is unavailable (e.g. iOS over HTTP)
- Pantry scanner: image upload silently failing due to DOM conflict with camera scanner div; now uses an isolated throwaway element per scan
- Pantry scanner: image upload changed from direct camera capture to photo library picker to avoid HEIC format issues on iOS; added 10s timeout to prevent indefinite hangs
- Pantry scanner: quantity and unit now pre-filled from Open Food Facts package size when available
- Settings: saving an empty value now clears the setting instead of being silently ignored
- Pantry: `PUT /api/pantry/:id` now whitelists accepted fields at the API boundary
- Grocery: regenerating the shopping list now preserves manually added items
- Sync: `POST /api/recipes/sync` now updates `status` from JSON (source of truth)
- Version check: GitHub release fetch is now non-blocking (runs in background thread)

---

## [v1.1.0] — 2026-04-14
### Added
- Version endpoint (`/api/version`) reads local VERSION file and checks GitHub for latest release
- Sidebar footer shows current version with update indicator when a newer release is available

### Changed
- Selection mode button moved to topbar; selection count replaces search bar when active
- Bulk action bar now only slides up when at least one recipe is selected
- Nostr browser: fixed stale WebSocket callbacks and race conditions; added retry button on connection errors

---

## [v1.0.0] — 2026-04-12
### Added
- Initial release
- AI recipe generation via OpenAI-compatible endpoint (PPQ.ai)
- RSS feed import with quality filtering
- URL recipe import with JSON-LD extraction
- Image/camera import via vision model (1–8 images)
- Raw text import via AI extraction
- Staging workflow — all imports require approval before going active
- Meal planner with weekly calendar view
- Pantry management with quantity tracking
- Grocery list with pantry diff calculation
- Recipe detail drawer with full ingredient and instruction view
- Trash with soft delete, restore, and permanent delete
- Settings tab with API key, model config, and AI connection test
- Generate tab with advanced options (servings, cook time, difficulty, protein, dietary, pantry picker)
- Docker image published to Docker Hub (`dockersette/feedme`)

---

[Unreleased]: https://github.com/sette7blo/feedme/compare/v1.5.1...HEAD
[v1.5.1]: https://github.com/sette7blo/feedme/compare/v1.5.0...v1.5.1
[v1.5.0]: https://github.com/sette7blo/feedme/compare/v1.4.0...v1.5.0
[v1.4.0]: https://github.com/sette7blo/feedme/compare/v1.3.0...v1.4.0
[v1.3.0]: https://github.com/sette7blo/feedme/compare/v1.2.0...v1.3.0
[v1.2.0]: https://github.com/sette7blo/feedme/compare/v1.1.0...v1.2.0
[v1.1.0]: https://github.com/sette7blo/feedme/releases/tag/v1.1.0
[v1.0.0]: https://github.com/sette7blo/feedme/releases/tag/v1.0.0
