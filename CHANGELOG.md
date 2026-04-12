# Changelog

All notable changes to Feedme will be documented here.
Versions follow [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`

- **MAJOR** — breaking changes (e.g. DB schema requires migration)
- **MINOR** — new features, backwards compatible
- **PATCH** — bug fixes, visual tweaks

---

## [Unreleased]

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

[Unreleased]: https://github.com/sette7blo/feedme/compare/v1.0.0...HEAD
[v1.0.0]: https://github.com/sette7blo/feedme/releases/tag/v1.0.0
