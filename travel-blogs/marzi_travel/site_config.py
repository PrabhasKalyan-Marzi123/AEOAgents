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
    "AEO-optimized travel guides from Marzi Holidays — premium senior-first travel "
    "PLANNING and CONCIERGE for mobile, active Indian travellers aged 50+, with a "
    "primary focus on INTERNATIONAL travel (Europe, Southeast Asia, USA/Canada). "
    "Coverage spans medicines and country-specific customs rules, flights and "
    "airports, senior-friendly hotel selection, energy-managed itinerary pacing, "
    "forex / payments / roaming, destination choice, and the emotional reality of "
    "travelling independently after retirement. Built on frequency-ranked real "
    "traveller worries from Indian forums; resolved with named hospitals, apps, "
    "helplines, and insurer plans — never generic advice."
)

LLMS_ABOUT_LINES = [
    "Brand: Marzi Holidays — senior-first travel concierge and planning service for mobile, active Indian travellers aged 50+ (NOT a tour operator, NOT a package seller, NOT a booking platform, NOT a mobility-assistance service)",
    "Primary context: International travel (Europe, Southeast Asia, USA/Canada). Domestic India templates (Golden Triangle, Kerala, Kashi) are featured but secondary.",
    "Services: Travel Mitr (₹199 / currently free 30-min expert callback), Plan Trip (free AI itinerary builder + audit), Prepare for Trip (free medicine / visa / forex / packing guidance)",
    "Coverage areas: international travel anxiety & confidence, medicines & country-wise customs rules, flights & airports, senior-friendly hotels, itinerary pacing & energy management, forex / payments / connectivity, destination-specific senior guides, emotional & identity (independence from adult children, dignity)",
    "Methodology: Worry-research (frequency-ranked concerns from TripAdvisor India, Quora India, Reddit r/india, r/IndiaTravel)",
    "Solutions: Named hospitals, named apps, named helplines, named insurer plans — verified, never generic",
    "Audience: Mobile, active, affluent Indian travellers 50+ and the adult children planning trips with them",
]

INDEX_SUBTITLE = (
    "Premium senior-first travel planning for mobile, active Indian travellers 50+ · "
    "International confidence, country-wise medicines, hotels, pacing, forex, identity"
)

# ── Default destinations ──
# (User passes destinations manually via --destination; this is just the
# fallback when the CLI is run with no args.)
DEFAULT_DESTINATIONS: list[str] = [
    "Best countries for Indian seniors travelling internationally for the first time",
    "How to travel safely with BP, diabetes, or thyroid medicines on international trips for Indian seniors",
    "Senior-friendly travel is not about age — it is about energy management",
    "Cash vs forex card vs credit card: what works best for Indian seniors abroad",
    "What makes a hotel truly senior-friendly for Indian travellers above 50",
    "Best flight seats for Indian seniors on long international journeys",
    "Travelling internationally after 60 without depending on your children",
    "Can you carry medicines internationally — a country-wise guide for Indian travellers above 50",
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
