# Feedme — Recipe Intelligence

A self-hosted recipe management platform. Import recipes from AI generation, RSS feeds, URLs, or photos. Plan meals, track your pantry, and generate grocery lists. Runs entirely in Docker.

---

## Features

- **AI generation** — describe a dish and get a full recipe with photo
- **RSS import** — subscribe to recipe sites; new recipes land automatically
- **URL import** — paste any recipe page URL to extract and save it
- **Image import** — photograph a cookbook page or recipe card; AI extracts it
- **Staging workflow** — all imports require your approval before going active
- **Meal planner** — assign recipes to days across a weekly calendar
- **Pantry tracking** — log what you have with quantities; scan barcodes to look up products instantly via Open Food Facts
- **Cook tonight** — filter your recipe library by what you already have in the pantry, sorted by ingredient coverage
- **Grocery list** — automatically calculates what to buy based on your meal plan and pantry
- No account, no cloud, no tracking — your data stays on your server

---

## Quick Start

No build required — pull straight from Docker Hub.

**1. Create a `docker-compose.yml`:**

```yaml
services:
  feedme:
    image: dockersette/feedme:latest
    ports:
      - "5000:5000"
    volumes:
      - ./recipes:/app/recipes
      - ./images:/app/images
      - ./data:/app/data
      - ./.env:/app/.env
    restart: unless-stopped
```

**2. Create a `.env` file:**

```env
PPQ_API_KEY=your-key-here
PPQ_BASE_URL=https://api.ppq.ai/v1
PPQ_MODEL=your-text-model-id
PPQ_IMAGE_MODEL=your-image-model-id
PPQ_VISION_MODEL=your-vision-capable-model-id

FLASK_SECRET=change-me-to-something-random
```

**3. Start it:**

```bash
docker compose up -d
```

**4. Open it:**

```
http://YOUR_SERVER_IP:5000
```

---

## Updating

```bash
docker compose pull && docker compose up -d
```

---

## AI Provider

Feedme uses OpenAI-compatible endpoints for recipe text, extraction, vision, and image generation. The default configuration names are still `PPQ_*` for compatibility with existing installs, and PPQ.ai is one supported provider.

Configure the key, base URL, and model IDs in the Settings tab after first launch. Choose models by capability rather than by stale examples:

- `PPQ_MODEL`: text/chat model for recipe generation and text extraction
- `PPQ_IMAGE_MODEL`: image-generation model for food photos
- `PPQ_VISION_MODEL`: vision-capable model for camera/image import

Provider model IDs change often, so check your provider's current model list before filling these values.

---

## Port

Default is **5000**. Change the left side of the ports mapping to use a different host port:

```yaml
ports:
  - "8080:5000"   # serve on port 8080 instead
```

---

## Security

Feedme has no authentication. It is designed for **personal / home server use only**, behind a firewall or VPN. Do not expose port 5000 to the public internet without adding an auth layer (e.g. HTTP Basic Auth via an nginx reverse proxy).

---

## License

MIT
