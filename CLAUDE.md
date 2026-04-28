# AEO Agents — AI Visibility Engine

## Project Overview

Answer Engine Optimization (AEO) content engine that generates, stores, and publishes AI-crawler-optimized blog content with JSON-LD structured data and auto-generated sitemaps.

**Core Loop:** Generate → Store (WordPress) → Approve → Publish (WordPress Pages) → Track → Learn → Improve

## Tech Stack

- **Backend:** Python / FastAPI
- **CMS / Hosting:** WordPress (REST API — stores and hosts full HTML pages directly)
- **AI Generation:** Google Gemini API
- **Deduplication:** HuggingFace `all-MiniLM-L6-v2` (sentence-transformers) for semantic similarity
- **Admin UI:** React + TypeScript + Tailwind CSS (Vite)
- **Infrastructure:** Docker (no Redis)

## Content Categories

Each category has its own JSON-LD schema for AI crawler optimization:

| Category | JSON-LD Schema |
|----------|---------------|
| FAQ / Q&A | `FAQPage` with `Question` + `acceptedAnswer` |
| How-To Guides | `HowTo` with `HowToStep`, `HowToTool`, `totalTime` |
| Comparison / Reviews | `Review`, `ItemList`, `Product`, `AggregateRating` |
| Informational Articles | `Article` / `BlogPosting` with `author`, `publisher` |

## Project Structure

```
AEOAgents/
├── backend/          # FastAPI — content generation + admin API
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── wordpress_client.py
│       ├── api/          # REST endpoints
│       ├── schemas/      # Pydantic models
│       └── services/     # generation, jsonld, dedup, tagging
├── frontend/         # React admin UI (CMS interface)
│   └── src/
│       ├── pages/        # ContentLibrary, ApprovalQueue, GenerateContent
│       ├── components/   # Layout, ContentCard, GenerateModal, JsonLdPreview
│       └── hooks/
```

## Key Architecture Decisions

- **WordPress is CMS + host** — full HTML pages stored and served directly as WordPress pages via REST API
- **Auth via Application Passwords** — WordPress 5.6+ built-in, no plugins needed
- **Content is generic HTML** — specific data (names, numbers, facts) injected via JSON-LD
- **No Redis/queue** — generation is synchronous via Gemini API
- **Dedup uses local model** — `all-MiniLM-L6-v2` runs in Docker container, no external API calls
- **AI crawler friendly** — robots.txt allows GPTBot, PerplexityBot, Google-Extended, etc.

## Running Locally

```bash
docker compose up --build
```

- Backend API: http://localhost:8000 (Swagger: /docs)
- Admin UI: http://localhost:5173
- Public Site: http://localhost:3000

## Environment Variables

See `.env.example` for required variables:
- `WORDPRESS_URL`, `WORDPRESS_USERNAME`, `WORDPRESS_APP_PASSWORD`
- `GEMINI_API_KEY`
- `SITE_URL`
