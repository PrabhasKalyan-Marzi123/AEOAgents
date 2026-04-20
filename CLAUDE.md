# AEO Agents — AI Visibility Engine

## Project Overview

Answer Engine Optimization (AEO) content engine that generates, stores, and publishes AI-crawler-optimized blog content with JSON-LD structured data and auto-generated sitemaps.

**Core Loop:** Generate → Store (Contentful) → Approve → Publish (Static Site) → Track → Learn → Improve

## Tech Stack

- **Backend:** Python / FastAPI
- **CMS / Database:** Contentful (headless CMS — no PostgreSQL)
- **AI Generation:** Google Gemini API
- **Deduplication:** HuggingFace `all-MiniLM-L6-v2` (sentence-transformers) for semantic similarity
- **Admin UI:** React + TypeScript + Tailwind CSS (Vite)
- **Public Site:** Next.js (static site generation) with JSON-LD + sitemaps
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
│       ├── contentful_client.py
│       ├── api/          # REST endpoints
│       ├── schemas/      # Pydantic models
│       └── services/     # generation, jsonld, dedup, tagging
├── frontend/         # React admin UI (CMS interface)
│   └── src/
│       ├── pages/        # ContentLibrary, ApprovalQueue, GenerateContent
│       ├── components/   # Layout, ContentCard, GenerateModal, JsonLdPreview
│       └── hooks/
└── site/             # Next.js static site (public-facing blog)
    └── src/
        ├── app/          # Pages, sitemap.ts, robots.ts
        └── lib/          # Contentful client, JSON-LD renderer
```

## Key Architecture Decisions

- **Contentful is the database** — all content, metadata, and structured data stored there
- **Content is generic HTML** — specific data (names, numbers, facts) injected via JSON-LD
- **No Redis/queue** — generation is synchronous via Gemini API
- **Dedup uses local model** — `all-MiniLM-L6-v2` runs in Docker container, no external API calls
- **Static site generation** — Next.js pulls from Contentful CDA, renders HTML with JSON-LD + sitemaps
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
- `CONTENTFUL_SPACE_ID`, `CONTENTFUL_MANAGEMENT_TOKEN`, `CONTENTFUL_DELIVERY_TOKEN`
- `GEMINI_API_KEY`
- `SITE_URL`
