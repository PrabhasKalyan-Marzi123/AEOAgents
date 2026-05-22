# Marzi Travel Blogs

AEO (Answer Engine Optimization) content engine for **Marzi Holidays** — generates senior-first travel guides for active Indian travellers aged 50+, hosts them on Firebase (`marzitravelblogs.web.app`), and keeps an accumulating sitemap + `llms.txt` so AI crawlers (ChatGPT, Perplexity, Gemini, Google AI Overviews) can index them.

This module sits on top of the brand-agnostic backend agents under `../backend/app/agents/`. It reuses backend code unchanged and only overrides the travel-specific bits (researcher prompt, strategist category routing, distributor copy, brand context, hero image generation).

## Pipeline

```
TravelResearcher (Gemini grounded GoogleSearch)
        ↓
TravelStrategist  (demotes COMPARISON → INFORMATIONAL — destination-first)
        ↓
Writer            (Gemini 2.5 Flash, Bootstrap-5 HTML, JSON-LD)
        ↓
Compiler          (wraps in site template, writes <slug>.html)
        ↓
TravelDistributor (rebuilds index.html / sitemap.xml / llms.txt / robots.txt,
                   discovers existing pages on disk, deploys to Firebase)
```

Output lands in `firebase-hosting/public/` and is served at `https://marzitravelblogs.web.app`.

## Prerequisites

- Python 3.11+ with `backend/requirements.txt` installed
- `firebase-tools` CLI installed and logged in (`npm i -g firebase-tools && firebase login`)
- `backend/.env` populated with at minimum:
  - `GEMINI_API_KEY=...`
- The Firebase project `marzitravelblogs` accessible to your account

## Common commands

Run all commands from the repo root (`AEOAgents/`).

**Generate the default destinations and deploy:**
```bash
python travel-blogs/run_travel_pipeline.py
```

**Generate one specific destination:**
```bash
python travel-blogs/run_travel_pipeline.py \
  --destination "Kerala backwaters trip for Indian travellers above 55"
```

**Generate multiple destinations in one run:**
```bash
python travel-blogs/run_travel_pipeline.py \
  --destination "Kerala backwaters for seniors" \
  --destination "Senior-friendly Europe destinations"
```

**Generate locally without deploying:**
```bash
python travel-blogs/run_travel_pipeline.py --destination "..." --no-deploy
```

**List every published blog (ID + slug + title):**
```bash
python travel-blogs/run_travel_pipeline.py --list-blogs
```

**Revise an existing blog (Editor agent):**
```bash
python travel-blogs/run_travel_pipeline.py \
  --update 3 \
  --comments "Shorten the medication section and add a paragraph on monsoon timing"
```
`--update` accepts either a numeric ID (from `--list-blogs`) or a slug.

**Verbose logging:**
```bash
python travel-blogs/run_travel_pipeline.py -v --destination "..."
```

## Deploy-only (no regeneration)

If you only want to rebuild `index.html` / `sitemap.xml` / `llms.txt` from whatever HTML files already exist on disk and push to Firebase:

```bash
PYTHONPATH=backend:travel-blogs python -c "
from dotenv import load_dotenv; load_dotenv('backend/.env')
from marzi_travel import site_config; site_config.apply_to_settings()
from marzi_travel.distributor import TravelDistributorAgent
TravelDistributorAgent(output_dir=site_config.OUTPUT_DIR).run([], deploy=True)
"
```

This is useful after editing distributor templates or hand-tweaking an HTML file.

If Firebase CLI 15.x hits the TLS circular-JSON bug, force serial upload:
```bash
cd travel-blogs/firebase-hosting
FIREBASE_HOSTING_UPLOAD_CONCURRENCY=1 firebase deploy --only hosting --project marzitravelblogs
```

## Editorial stance (built into the agents)

The pipeline is configured to produce **destination/topic-first** content with Marzi as a soft closer:
- The body must lead with named places, suggested itineraries, practical facts, and real third-party tools/apps (Airalo, Digit, HDFC ForexPlus, TripIt, Google Maps, etc.).
- Marzi (Travel Mitr / Plan Trip / Prepare for Trip) is mentioned in **one closing section only** — never threaded through.
- `TravelStrategist` blocks the COMPARISON category, which the backend renders with brand-anchored headings ("How {brand} compares to X", "Pros and Cons of {brand}"); travel topics are routed to INFORMATIONAL instead.
- Hard-sell phrases ("Marzi is the answer", "book with Marzi", "Marzi takes care of everything") are explicitly forbidden in `marzi_travel/brand_context.py`.

If you want to change the stance, edit:
- `marzi_travel/brand_context.py` → `content_guidelines` (Writer prompt rules)
- `marzi_travel/researcher.py` → "EDITORIAL STANCE — READ FIRST" + `_to_dossier` ordering
- `marzi_travel/strategist.py` → category routing

## Configuration

`marzi_travel/site_config.py` holds everything brand-specific (no env vars needed):
- `SITE_URL`, `SITE_NAME`, `ORGANIZATION_NAME`, `BRAND_URL`
- `OUTPUT_DIR` — where compiled HTMLs land
- `INDEX_SUBTITLE` — landing-page tagline
- `LLMS_SUMMARY`, `LLMS_ABOUT_LINES` — for `llms.txt`
- `DEFAULT_DESTINATIONS` — fallback topics when `--destination` isn't passed

The `apply_to_settings()` call at CLI startup mutates the backend's `app.config.settings` in memory so the unchanged backend agents emit travel-flavoured URLs / titles / footers.

## Output layout

```
travel-blogs/
├── firebase-hosting/
│   ├── firebase.json
│   └── public/
│       ├── index.html              # auto-generated landing page (card list)
│       ├── sitemap.xml             # accumulates every live page
│       ├── llms.txt                # AI-crawler manifest (markdown)
│       ├── robots.txt              # AI crawlers explicitly allowed
│       ├── images/                 # hero images, one per slug (WebP)
│       └── marzi-holidays-*.html   # one file per blog
├── marzi_travel/                   # travel-specific agent overrides
└── run_travel_pipeline.py          # CLI entry point
```

The Distributor scans `public/*.html` on every run and merges discovered pages with the current batch — old blogs stay listed in the index/sitemap/llms.txt even when you only regenerate one.

## Troubleshooting

- **`firebase: command not found`** — install with `npm install -g firebase-tools` and run `firebase login`.
- **Firebase deploy hangs / TLS circular-JSON error** — set `FIREBASE_HOSTING_UPLOAD_CONCURRENCY=1`.
- **Writer fails with `JSONDecodeError`** — the Writer retries 3× and has a lenient fallback parser. If all three fail, re-run; Gemini occasionally returns malformed JSON on long HTML payloads.
- **Module not found `app.*` or `marzi_travel.*`** — `run_travel_pipeline.py` adds both to `sys.path` automatically, but if you invoke things by hand set `PYTHONPATH=backend:travel-blogs`.
- **Edits to `.py` files aren't reflected** — Python caches imported modules; restart the CLI after editing any agent.

## Live URLs

- Landing page: https://marzitravelblogs.web.app
- Sitemap: https://marzitravelblogs.web.app/sitemap.xml
- AI-crawler manifest: https://marzitravelblogs.web.app/llms.txt
- Robots: https://marzitravelblogs.web.app/robots.txt
