# Feedme Development Notes

Use this file for implementation and release details. Product/spec context lives in `PROJECT.md`; public install docs live in `README.md`; phase tracking lives in `docs/roadmap/lean-refactor.md`.

## Local stack

- Python 3.11+
- Flask
- SQLite via built-in `sqlite3`
- Vanilla browser JavaScript
- Docker and Docker Compose v2

## Repository conventions

- No frontend framework.
- No frontend build step.
- No ORM; use raw parameterized SQLite queries.
- Keep modules broad and domain-oriented; avoid one tiny file per helper.
- Comment only non-obvious logic.
- Do not add AI attribution comments or commit trailers.
- Keep `CLAUDE.md`, `.claude/`, `.env`, `VERSION`, SQLite DBs, recipe JSON, and recipe images out of git.

## Important paths

- `server.py`: Flask app and route wiring.
- `core/config.py`: `.env` read/write helper.
- `core/db.py`: SQLite connection helper.
- `core/schema.py`: idempotent schema migrations.
- `modules/importer.py`: recipe JSON and DB CRUD/sync.
- `modules/ai_chef.py`: AI recipe generation/text extraction/image generation.
- `modules/rss_fetcher.py`: RSS feed import.
- `modules/url_importer.py`: URL import.
- `modules/camera.py`: image/vision import.
- `modules/meal_planner.py`: meal plan CRUD and ingredient aggregation.
- `modules/meal_plan_ai.py`: AI week-plan generation.
- `modules/grocery.py`: pantry diff and shopping list logic.
- `modules/pantry.py`: pantry CRUD.
- `frontend/index.html`: SPA markup.
- `frontend/*.js`: feature modules loaded directly by the browser.
- `frontend/app.css`: app styles.

## Development commands

```bash
python3 -m compileall -q core modules server.py
docker compose up -d --build
docker compose logs -f
docker compose down
```

The compose file is `compose.yaml`.

## GitHub workflow

Use a branch and PR for non-trivial changes:

```bash
git checkout main
git pull --ff-only origin main
git checkout -b docs/example-change
# edit, verify
git add <files>
git commit -m "docs: describe example change"
git push -u origin HEAD
gh pr create --title "docs: describe example change" --body "Closes #N"
```

Commit style in this workspace is imperative, lowercase, no period.

## Release flow

During development, update `[Unreleased]` in `CHANGELOG.md` only for changes a self-hoster upgrading the app would care about.

When releasing:

```bash
git add CHANGELOG.md
git commit -m "release vX.Y.Z"
git tag vX.Y.Z
git push && git push origin vX.Y.Z
```

The tag triggers GitHub Actions to build/publish Docker images and create the GitHub release.

Do not push a release-intent commit without a matching tag.

Release publishing is tag-driven. A plain `main` push does not have semver tag
context, so the release workflow must not try to push Docker images from `main`
unless it also provides a valid non-release tag such as `main` or `edge`.

Cleaner workflow options:

- Preferred: limit Docker image publishing and GitHub release creation to
  `refs/tags/v*.*.*` only.
- Alternative: keep `main` pushes in the workflow, but set `push: false` or use
  a separate development image tag for non-tag refs.

When checking whether a release succeeded, check the tag-triggered run for
`vX.Y.Z`. Do not treat a separate `main` push run with missing semver metadata
as the release result.

## AI configuration notes

The current setting/env names are `PPQ_*` for compatibility:

```env
PPQ_API_KEY=...
PPQ_BASE_URL=https://api.ppq.ai/v1
PPQ_MODEL=...
PPQ_IMAGE_MODEL=...
PPQ_VISION_MODEL=...
AI_VISION_DETAIL=low
GENERATE_IMAGES_BY_DEFAULT=true
```

Do not document fixed recommended model IDs unless they have just been verified. Prefer capability language:

- text/chat model for recipe generation and extraction
- image-generation model for generated food photos
- vision-capable model for camera import

Cost-control settings:

- `AI_VISION_DETAIL`: `low`, `auto`, or `high`; default is `low`.
- `GENERATE_IMAGES_BY_DEFAULT`: `true` or `false`; disables automatic image-generation calls when false.

## Verification checklist

Before opening a PR:

```bash
git diff --check
python3 -m compileall -q core modules server.py
```

When frontend files changed, also run the app and check the browser console.

When import or AI behavior changed, test the specific path manually with safe sample data.

When Docker/runtime behavior changed:

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100
```

## Lean refactor rules

- Each phase must leave Feedme working independently.
- One issue should generally map to one PR.
- Do not merge half-migrations that rely on a later phase to restore behavior.
- Keep old endpoints/settings compatible unless the issue explicitly says to break or migrate them.
