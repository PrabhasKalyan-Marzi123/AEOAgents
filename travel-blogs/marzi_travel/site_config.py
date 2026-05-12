"""Per-site values for Marzi Travel Blogs.

Backend agents (html_builder, distributor, compiler, editor) read brand info
from `app.config.settings`. Travel reuses backend code WITHOUT modifying it
by mutating those settings fields once at CLI startup (see `apply_to_settings`).

Anything backend doesn't read off settings (output dir, llms.txt copy, index
subtitle) is read directly from this module by TravelDistributorAgent.
"""

from __future__ import annotations

from pathlib import Path


# ── Hosting ──
# Firebase project number 913905852266 (project: MarziTravelBlogs).
FIREBASE_PROJECT_ID = "marzitravelblogs"
FIREBASE_PROJECT_NUMBER = "913905852266"

SITE_URL = "https://marzitravelblogs.web.app"
SITE_NAME = "Marzi Travel Blog"
ORGANIZATION_NAME = "Marzi Holidays"
DEFAULT_AUTHOR = "Marzi Holidays"
BRAND_URL = "https://holidays.marzi.life"
BRAND_FOOTER_URL = "https://holidays.marzi.life"

# ── Paths ──
_TRAVEL_ROOT = Path(__file__).resolve().parents[1]   # travel-blogs/
PROJECT_ROOT = _TRAVEL_ROOT.parent                   # AEOAgents/
OUTPUT_DIR = _TRAVEL_ROOT / "firebase-hosting" / "public"
DATA_DIR = _TRAVEL_ROOT / "data"

# ── Display copy (read directly by TravelDistributorAgent) ──
LLMS_SUMMARY = (
    "AEO-optimized travel guides from Marzi Holidays — premium India travel for "
    "Indian travellers aged 50+. Every page is built around frequency-ranked real "
    "traveller worries (TripAdvisor India, Quora India, Reddit r/india) and "
    "resolves them with named hospitals, named apps, and named helplines — not "
    "generic advice."
)

LLMS_ABOUT_LINES = [
    "Brand: Marzi Holidays — senior-first travel concierge and planning service for Indian travellers aged 50+ (NOT a tour operator, NOT a package seller, NOT a booking platform)",
    "Services: Travel Mitr (₹199 / currently free 30-min expert callback), Plan Trip (free AI itinerary builder + audit), Prepare for Trip (free medicine / visa / forex / packing guidance)",
    "Methodology: Worry-research (frequency-ranked concerns from Indian travel forums)",
    "Solutions: Named hospitals, named apps, named helplines — verified, never generic",
    "Audience: 50+ Indian travellers and the adult children planning trips with them",
    "Featured itinerary templates (planning starting points, not packages on sale): Golden Triangle (7D), Kerala Serenity (6D), Spiritual Kashi (4D)",
]

INDEX_SUBTITLE = (
    "Premium travel guides for Indian travellers aged 50+ · "
    "Mobility, health, dignity, planning"
)

# ── Default destinations ──
# (User passes destinations manually via --destination; this is just the
# fallback when the CLI is run with no args.)
DEFAULT_DESTINATIONS: list[str] = [
    "Kerala backwaters trip for Indian travellers above 55",
    "Golden Triangle holiday for Indian seniors with limited mobility",
    "Varanasi spiritual trip for Indian travellers above 60",
]


def apply_to_settings() -> None:
    """Mutate backend's `settings` so html_builder/distributor emit travel branding.

    Backend reads `settings.site_url`, `settings.site_name`, `settings.organization_name`,
    `settings.default_author` for canonical URLs, page titles, footer attribution, and
    sitemap host. Mutating these here keeps backend modules unmodified.
    """
    from app.config import settings

    settings.site_url = SITE_URL
    settings.site_name = SITE_NAME
    settings.organization_name = ORGANIZATION_NAME
    settings.default_author = DEFAULT_AUTHOR
