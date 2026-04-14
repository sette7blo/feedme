# Changelog

All notable changes to Feedme will be documented here.
Versions follow [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`

- **MAJOR** — breaking changes (e.g. DB schema requires migration)
- **MINOR** — new features, backwards compatible
- **PATCH** — bug fixes, visual tweaks

---

## [Unreleased]

### Fixed
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

[Unreleased]: https://github.com/sette7blo/feedme/compare/v1.1.0...HEAD
[v1.1.0]: https://github.com/sette7blo/feedme/releases/tag/v1.1.0
[v1.0.0]: https://github.com/sette7blo/feedme/releases/tag/v1.0.0
