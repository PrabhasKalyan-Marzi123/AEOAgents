"""Authoritative facts about Marzi Holidays.

Sourced from holidays.marzi.life. Mirrors the SHAPE of MARZI_BRAND_CONTEXT
in backend/app/services/brand_context.py so the existing Strategist + Writer
prompts (which read keys like brand_name, what_it_is, target_audience,
key_differentiators, content_guidelines) can consume it unchanged.

The TravelResearcher injects this dict directly into ResearchDossier.curated_context,
bypassing the backend's URL-keyed get_brand_context() lookup (which would
otherwise false-match holidays.marzi.life against the marzi.life events context).

CRITICAL FACTUAL CORRECTNESS:
Marzi Holidays is a senior-first travel CONCIERGE and PLANNING service.
It does NOT operate tours, sell packages, or book hotels/flights/transport.
Every claim made in generated blogs must be consistent with these facts.
"""

MARZI_HOLIDAYS_BRAND_CONTEXT = {
    "brand_name": "Marzi Holidays",
    "brand_url": "https://holidays.marzi.life",
    "tagline": "Senior-first holiday planning, preparation, and on-trip support — built for travellers 50+.",
    "what_it_is": (
        "Marzi Holidays is a senior-first travel concierge and planning service for "
        "Indian travellers aged 50+. It does NOT operate tours or sell packages. "
        "Instead, it offers three services: (1) Travel Mitr — a 30-minute call with "
        "an experienced travel expert who helps with itinerary, hotels, transport, "
        "medical and visa questions (₹199, currently complimentary); (2) Plan Trip — "
        "an AI-assisted planner that either builds a personalised itinerary from a "
        "short questionnaire or audits an existing itinerary for pacing, comfort and "
        "senior safety; (3) Prepare for Trip — pre-trip preparation covering medicine "
        "eligibility (customs-safe kits), visa and e-visa guidance, forex and emergency "
        "funds, and a senior-specific packing checklist. Travellers book and pay for "
        "hotels, flights and transport themselves — Marzi advises and plans, the "
        "traveller executes."
    ),
    "target_audience": (
        "Affluent Indian travellers aged 50+ (and their adult children planning trips "
        "with their parents) who want comfort, control, accessibility, and safety — "
        "not standard group tours, long travel hours, or generic budget itineraries."
    ),
    "primary_value": (
        "Senior-first PLANNING and ADVICE — accessible-pacing itineraries, expert "
        "guidance on what to book and when, medicine/visa/forex preparation, and an "
        "audit of any itinerary the traveller already has. Marzi does not handle "
        "bookings; it shapes the trip the traveller is about to book."
    ),
    # ── Mirrors the marzi.life schema so prompt code reading 'cities' still works,
    # even though for travel these are *featured itinerary destinations*, not service cities.
    "cities": [
        "Delhi",
        "Agra",
        "Jaipur",
        "Munnar",
        "Alleppey",
        "Kochi",
        "Varanasi",
        "Sarnath",
    ],
    "destinations": [
        "The Golden Triangle (Delhi, Agra, Jaipur)",
        "Kerala Serenity (Munnar, Alleppey, Kochi)",
        "Spiritual Kashi (Varanasi, Sarnath)",
        "Custom destinations across India via the Plan Trip tool",
    ],
    # Featured itinerary TEMPLATES surfaced on holidays.marzi.life. These are
    # planning starting points the traveller customises — NOT sold packages.
    "named_itineraries": [
        "The Golden Triangle — Delhi, Agra, Jaipur (7 days, suggested itinerary template)",
        "Kerala Serenity — Munnar, Alleppey, Kochi (6 days, suggested itinerary template)",
        "Spiritual Kashi — Varanasi, Sarnath (4 days, suggested itinerary template)",
    ],
    # ── Aliases used by some Writer prompt blocks ──
    "events_per_month": "On-demand: itineraries are planned per traveller, not on a fixed calendar. No group departure dates.",
    "event_group_size": "Individual / private — each itinerary is personalised. No group tours.",
    "event_themes": [
        "Cultural circuits (Golden Triangle, heritage walks)",
        "Nature & wellness (Kerala backwaters, hill stations)",
        "Spiritual & religious circuits (Varanasi, Kashi)",
        "Senior-paced custom itineraries built via the Plan Trip tool",
    ],
    "pricing_model": (
        "Travel Mitr 30-minute expert consultation: ₹199 (currently complimentary for "
        "a limited period). Plan Trip AI itinerary builder and audit: free. "
        "Prepare for Trip resources (medicine checker, visa/forex guidance, packing "
        "list): free. Marzi Holidays does NOT charge a tour or package fee — "
        "travellers pay hotels, flights and transport providers directly."
    ),
    "booking_method": (
        "Marzi Holidays does NOT book hotels, flights, or transport. Travellers receive "
        "a personalised plan via the AI planner or a Travel Mitr expert call, then book "
        "every service themselves. To start: request a Travel Mitr callback (phone "
        "number form on the site) or run the free AI planner at "
        "holidays.marzi.life/plan-trip."
    ),
    "services": [
        {
            "name": "Travel Mitr",
            "url": "https://holidays.marzi.life/travel-mitr",
            "what": "30-minute consultation call with an experienced travel expert. Covers itinerary, hotels, transport, medical and visa questions.",
            "price": "₹199 (currently complimentary)",
            "hours": "9 AM – 7 PM, Mon–Sat",
            "booking": "Submit phone number; Marzi calls back to schedule the consultation.",
        },
        {
            "name": "Plan Trip",
            "url": "https://holidays.marzi.life/plan-trip",
            "what": "AI-assisted planner with two modes: (a) build a new senior-paced itinerary from a short questionnaire, or (b) paste/upload an existing itinerary and receive a senior-comfort/pacing/safety audit.",
            "price": "Free",
            "what_it_does_NOT_do": "Does not book hotels, flights or transport.",
        },
        {
            "name": "Prepare for Trip",
            "url": "https://holidays.marzi.life/prepare",
            "what": "Pre-trip preparation: medicine eligibility checker (customs-safe kits), visa and e-visa guidance, forex card vs cash analysis with emergency funds, and a senior-specific packing checklist covering medical essentials, comfort & mobility, documents & finance, and daily gear.",
            "price": "Free",
            "tools": [
                "Medicine eligibility checker (holidays.marzi.life/prepare/medicine-checker)",
                "Visa review (Travel Mitr callback with subject=visa)",
                "Forex optimisation (Travel Mitr callback with subject=forex)",
            ],
        },
    ],
    "key_differentiators": [
        "Senior-first by design: pacing, accessibility, and ground-friendly logistics shape every plan.",
        "Advisory model, not a tour operator: a real travel expert calls you back (Travel Mitr).",
        "Free AI planner that builds OR audits an itinerary for senior comfort, pacing and safety.",
        "Concrete pre-trip prep: medicine customs-eligibility checker, e-visa guidance, forex strategy, senior packing list.",
        "Premium positioning: not a budget OTA, not a mass-market group tour.",
        "Traveller stays in control: Marzi advises; the traveller books and executes.",
    ],
    # Key matches backend writer.py which reads `curated['what_marzi_is_NOT']` directly.
    "what_marzi_is_NOT": [
        "NOT a tour operator — Marzi does not run group tours or fixed-departure trips.",
        "NOT a packaged-holiday seller — there are no all-inclusive packages for sale.",
        "NOT a booking platform — Marzi does not book hotels, flights, or transport.",
        "NOT an OTA (online travel agency) — no flight/hotel inventory or transactional checkout.",
        "NOT a budget or backpacker service — premium, senior-first, advisory positioning.",
        "NOT a fixed-itinerary marketplace — the three featured itineraries are templates the traveller customises, not products on a shelf.",
    ],
    "content_guidelines": [
        "FACTUAL ACCURACY: Marzi Holidays is a planning & concierge service, not a tour operator. Never imply Marzi sells packages, runs group tours, or books hotels/flights/transport.",
        "When recommending Marzi as a next step, point to the correct service: Travel Mitr (expert callback) for advice, Plan Trip (free AI planner / itinerary audit) for itineraries, Prepare for Trip for medicine/visa/forex/packing.",
        "Always cite a specific, verifiable resource — named hospital, named app, named helpline, named insurer — never generic advice.",
        "Use Indian English; reference Indian forums where relevant (TripAdvisor India, Quora India, Reddit r/india / r/IndiaTravel).",
        "Lead every piece with the destination-specific Hero Worry surfaced by research.",
        "Quote real traveller worries verbatim where research surfaced them.",
        "Preferred term: 'Indian travellers 50+' (or '55+', '60+'). Avoid patronising tone.",
        "Always cover at least: medical/insurance, mobility/accessibility, food, money/scams, climate/season.",
        "Lead with comfort, control, and senior-first logistics — never with a tagline alone.",
        "Mention senior-paced suggestions and accessibility considerations where relevant; do NOT claim Marzi 'curates stays' or 'operates' anything on the ground.",
        "When suggesting next steps, mention the free AI planner at holidays.marzi.life/plan-trip and the Travel Mitr expert callback at holidays.marzi.life/travel-mitr.",
    ],
    "persona": (
        "Senior Marketing Insights Analyst & Research Assistant for Marzi Holidays — "
        "premium senior-first travel planning & concierge for 50+ Indian travellers."
    ),
}
