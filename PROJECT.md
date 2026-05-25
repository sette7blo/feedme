# Feedme Project Notes

Feedme is a self-hosted recipe management and meal-planning app for a personal/home server. It imports recipes from AI generation, RSS feeds, URLs, pasted text, camera images, or manual JSON, then stores them as schema.org `Recipe` JSON and indexes them into SQLite for fast app workflows.

## Product loop

```text
source -> recipe JSON -> SQLite index -> meal plan -> pantry diff -> grocery list
```

## Product principles

- Recipes are portable schema.org JSON.
- `recipes/*.json` is the canonical recipe source of truth.
- SQLite is the query/index layer and can be rebuilt from JSON.
- Imported/generated recipes land in staging first; the user approves them before they become active.
- Images are separate from recipe JSON so image failures do not corrupt recipe data.
- The app is designed for personal/home-network use, not a public multi-user SaaS.

## App identity

- App name: Feedme
- Wordmark: `Feed` dark brown + `me` amber
- Tagline: `RECIPE INTELLIGENCE`
- Logo: steaming bowl mark
- The logo/top banner should remain visible and recognizable.

## Architecture

- Backend: Python 3.11+ and Flask
- Database: SQLite via raw `sqlite3`
- Frontend: single-page vanilla JavaScript, no framework, no build step
- Deployment: Docker container with host-mounted `recipes/`, `images/`, and `data/`
- AI: OpenAI-compatible chat/image endpoints configured by the user

## Data model overview

Main tables:

- `recipes`: SQLite index for recipe JSON files, including status, source, tags, ingredients, and image path.
- `pantry`: foods available at home.
- `meal_plan`: dated breakfast/lunch/dinner recipe assignments.
- `shopping_list`: pantry diff output and manual shopping entries.
- `settings`: app settings persisted by key/value.

Recipe JSON should include the schema.org basics:

- `@context`, `@type`
- `name`, `slug`, `description`
- `image`
- `recipeIngredient`
- `recipeInstructions`
- `prepTime`, `cookTime`, `totalTime`
- `recipeYield`, `recipeCategory`, `recipeCuisine`
- `source_url`, `source_type`, `status`

## Import sources

- AI generation: prompt to staged recipe JSON, optionally with generated image.
- RSS import: feed items become staged recipes after page scrape/normalization.
- URL import: JSON-LD or page content becomes one staged recipe.
- Text import: pasted recipe text becomes one staged recipe.
- Camera import: uploaded recipe images go through a vision-capable model and become one staged recipe.
- Manual import: user-provided recipe JSON can be saved directly.

## AI provider model guidance

Feedme keeps `PPQ_*` setting names for compatibility with existing installs, but the recipe/text/vision calls are intended to work with OpenAI-compatible endpoints.

Do not hardcode current model recommendations in project docs. Provider model IDs change often. Describe model requirements by capability:

- Recipe/text model: supports chat/text generation.
- Vision model: supports image inputs.
- Image model: supports the configured image generation endpoint.

PPQ-specific balance/top-up helpers are convenience features and are separate from the OpenAI-compatible recipe generation path.

## User-visible API areas

- Recipes: list/detail/approve/trash/restore/permanent delete/sync/favorite/cook log.
- AI: provider test, recipe generation, text extraction, nutrition estimation, image regeneration.
- Imports: RSS, URL, camera, manual, text.
- Pantry: CRUD.
- Meal plan: week view, add/update/delete entries, templates, AI planning.
- Grocery: generate list, update items, manual add/delete.
- Maintenance: backup, restore, version check, static assets.

## Non-goals unless explicitly requested

- Frontend framework or build tooling.
- ORM layer.
- Public multi-user authentication system.
- External hosted database.
- Committing personal recipe data, runtime DBs, images, `.env`, or generated `VERSION` files.
