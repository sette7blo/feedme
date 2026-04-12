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
- **Pantry tracking** — log what you have with quantities
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
PPQ_MODEL=gpt-4o-mini
PPQ_IMAGE_MODEL=dall-e-3
PPQ_VISION_MODEL=gpt-4o

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

Feedme uses any OpenAI-compatible endpoint. The default is [PPQ.ai](https://ppq.ai) which provides access to GPT-4o, DALL-E 3, and other models via a single API key. You can configure the key and models directly in the Settings tab after first launch.

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
