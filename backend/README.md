# AEO Agents Backend

FastAPI backend for the AEO (Answer Engine Optimization) content engine. Generates AI-optimized blog content with JSON-LD structured data, deduplicates against existing content, and stores everything in Contentful.

## Architecture

```
app/
├── main.py                  # FastAPI app, lifespan, CORS, health check
├── config.py                # Pydantic Settings (env vars)
├── contentful_client.py     # Contentful Management + Delivery API wrapper
├── api/
│   ├── router.py            # /api/v1 router
│   └── content.py           # Content CRUD + generate/publish endpoints
├── schemas/
│   └── content.py           # Pydantic request/response models
└── services/
    ├── generation.py        # Web scraping + Gemini AI content generation
    ├── deduplication.py     # SHA-256 exact + sentence-transformer semantic dedup
    ├── jsonld.py            # JSON-LD generators (FAQPage, HowTo, Article, BlogPosting)
    ├── html_builder.py      # Full HTML page assembly, sitemap.xml, robots.txt
    ├── tagging.py           # Tag normalization
    └── publisher.py         # Orchestration: generate -> dedup -> build -> store
```

## Content Generation Pipeline

1. **Scrape** the brand URL for real data (name, features, pricing, existing JSON-LD)
2. **Generate** content variations via Gemini AI with category-specific prompts
3. **Normalize** tags (lowercase, deduplicate, limit)
4. **Deduplicate** against Contentful — SHA-256 exact match, then sentence-transformer cosine similarity
5. **Build JSON-LD** structured data based on content category
6. **Assemble** full HTML page with meta tags, Open Graph, canonical URL, JSON-LD scripts
7. **Save** to Contentful as a draft entry

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/content/generate` | Generate content from topic + brand URL |
| `GET` | `/api/v1/content/` | List entries (filter by status, category, topic) |
| `GET` | `/api/v1/content/{entry_id}` | Get single entry |
| `PATCH` | `/api/v1/content/{entry_id}` | Update entry fields |
| `POST` | `/api/v1/content/{entry_id}/publish` | Publish entry to Contentful live |
| `GET` | `/api/v1/content/site/sitemap.xml` | Generated sitemap |
| `GET` | `/api/v1/content/site/robots.txt` | AI-crawler-friendly robots.txt |

## Content Categories

| Category | JSON-LD Type | Notes |
|----------|-------------|-------|
| `faq` | `FAQPage` | Q&A pairs extracted from `<h2>` headings |
| `how-to` | `HowTo` | Steps from `<ol>` or `<h3>` tags, tools from prerequisites section |
| `comparison` | `Article` + `ItemList` | Product ratings, pricing as `Offer` |
| `informational` | `BlogPosting` | Key facts as `articleBody`, features as `keywords` |

## Setup

### Prerequisites

- Python 3.12+
- [Poetry](https://python-poetry.org/) for dependency management
- Contentful account (space ID + management/delivery tokens)
- Google Gemini API key

### Install

```bash
cd backend
poetry install
```

### Environment Variables

Copy the example and fill in your credentials:

```bash
cp ../.env.example .env
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CONTENTFUL_SPACE_ID` | Yes | | Contentful space ID |
| `CONTENTFUL_MANAGEMENT_TOKEN` | Yes | | CMA token (write access) |
| `CONTENTFUL_DELIVERY_TOKEN` | Yes | | CDA token (read access) |
| `GEMINI_API_KEY` | Yes | | Google Gemini API key |
| `CONTENTFUL_ENVIRONMENT` | No | `master` | Contentful environment |
| `SITE_URL` | No | `http://localhost:3000` | Public site base URL |
| `SITE_NAME` | No | `AEO Blog` | Site name for meta tags |
| `ORGANIZATION_NAME` | No | | Organization name for JSON-LD publisher |
| `DEFAULT_AUTHOR` | No | | Author name for JSON-LD |
| `NUM_VARIATIONS` | No | `3` | Content variations per request (1-5) |
| `DEDUP_SIMILARITY_THRESHOLD` | No | `0.85` | Cosine similarity threshold for semantic dedup |
| `CORS_ORIGINS` | No | `["http://localhost:5173"]` | Allowed CORS origins |

### Run

```bash
# Development
poetry run uvicorn app.main:app --reload --port 8000

# Or with Docker from the project root
docker compose up --build
```

API docs available at http://localhost:8000/docs (Swagger UI).

## Tests

The test suite covers all services, schemas, and API endpoints (188 tests).

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
cd backend
python -m pytest tests/ -v
```

Tests mock heavy dependencies (Contentful SDK, sentence-transformers, Google Gemini) so they run fast without external services.

### Test Structure

```
tests/
├── conftest.py              # Fixtures, dependency mocking, env setup
├── test_tagging.py          # Tag normalization edge cases
├── test_schemas.py          # Pydantic model validation
├── test_deduplication.py    # Hashing, cosine similarity, async dedup flow
├── test_jsonld.py           # All 4 JSON-LD generators + HTML extraction
├── test_html_builder.py     # Page assembly, sitemap, robots.txt
├── test_generation.py       # Slugify, prompt building, scraping, Gemini parsing
├── test_publisher.py        # Full pipeline orchestration
└── test_api.py              # API endpoint integration tests
```
