"""Brand-specific context that supplements scraped data with accurate product information.

This ensures generated content is factually correct even when the brand website
contains vague taglines or insufficient detail for AI content generation.
"""

# Marzi brand context — authoritative facts about the product
MARZI_BRAND_CONTEXT = {
    "brand_name": "Marzi",
    "brand_url": "https://marzi.life",
    "tagline": "Offline social events for people above 55",
    "what_it_is": (
        "Marzi is an app-based platform that organizes themed offline social events "
        "and meetups specifically for people above 55. The core experience is in-person — "
        "people meet face to face at organized events, not online."
    ),
    "target_audience": "People above 55 (retired, semi-retired, or looking for social connections)",
    "primary_value": "Offline meetups and themed in-person events — NOT an online community",
    "cities": ["Bangalore", "Mumbai"],
    "events_per_month": "20+ events per month in each city (Bangalore and Mumbai)",
    "event_group_size": "20 to 60 participants per event",
    "event_themes": [
        "Music sessions (live performances, sing-alongs, music appreciation)",
        "Dance events (social dancing, choreography workshops, themed dance nights)",
        "Book club discussions (read and discuss with engaged readers)",
        "Storytelling circles (share and listen to personal stories and life experiences)",
        "Upskilling workshops (technology, creative arts, new skills)",
        "Social parties (casual get-togethers, themed celebrations, networking)",
    ],
    "pricing_model": (
        "No subscription. Pay only for the events you choose to attend. "
        "No recurring fees, no commitments."
    ),
    "booking_method": (
        "App-first. Download the Marzi app, browse upcoming events, "
        "select an event, pay for it, and attend."
    ),
    "key_differentiators": [
        "Offline-first: every event is a real, in-person gathering",
        "Age-specific: designed exclusively for people above 55",
        "Themed variety: different event themes every time (music, dance, books, storytelling, upskilling, social parties)",
        "No subscription: pay per event only",
        "App-first booking: browse, pay, show up",
        "Right group size: 20-60 people — intimate enough for real conversations",
        "High frequency: 20+ events per month per city",
    ],
    "what_marzi_is_NOT": [
        "NOT an online community or social media platform",
        "NOT a subscription service",
        "NOT for Gen X (target is specifically people above 55)",
        "NOT focused on 'curated experiences' as a vague tagline — it organizes concrete themed events",
    ],
    "content_guidelines": [
        "Never use 'Gen X' — the audience is 'people above 55'",
        "Never use 'Gen Evergreen' — say 'people above 55' or '55+'",
        "Avoid vague phrases like 'meet your kind of people' or 'curated experiences' without explaining what Marzi actually does",
        "Always include concrete details: 20+ events/month, Bangalore & Mumbai, 20-60 participants, specific themes",
        "Lead with offline meetups as the main hook — the app is just the booking mechanism",
        "Mention specific event themes (music, dance, book clubs, storytelling, upskilling, social parties)",
        "Make clear there is no subscription — pay per event",
        "The app is for booking, not for socializing online",
    ],
}


def get_brand_context(brand_url: str) -> dict | None:
    """Return brand context if available for the given URL.

    Returns None if no specific brand context is configured,
    in which case the system falls back to scraped data only.
    """
    # Match Marzi by URL
    marzi_urls = ["https://marzi.life", "http://marzi.life", "marzi.life"]
    normalized = brand_url.rstrip("/").lower().replace("www.", "")
    for url in marzi_urls:
        if normalized == url or normalized.endswith(url):
            return MARZI_BRAND_CONTEXT
    return None
