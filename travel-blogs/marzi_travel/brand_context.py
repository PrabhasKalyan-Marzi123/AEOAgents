"""Authoritative facts about Marzi Holidays.

Sourced from holidays.marzi.life + user-provided positioning brief.
Mirrors the SHAPE of MARZI_BRAND_CONTEXT in backend/app/services/brand_context.py
so the existing Strategist + Writer prompts (which read keys like brand_name,
what_it_is, target_audience, key_differentiators, content_guidelines) consume
it unchanged.

The TravelResearcher injects this dict directly into ResearchDossier.curated_context,
bypassing the backend's URL-keyed get_brand_context() lookup (which would
otherwise false-match holidays.marzi.life against the marzi.life events context).

CRITICAL FACTUAL CORRECTNESS — read carefully before changing:

1. Marzi Holidays is a senior-first travel CONCIERGE and PLANNING service.
   It does NOT operate tours, sell packages, or book hotels/flights/transport.

2. Most Marzi travellers are MOBILE, ACTIVE, AFFLUENT seniors 50+. They are
   NOT primarily mobility-impaired. Mobility is one consideration, not the
   anchor. Do NOT default to "wheelchair / step-free / mobility obstacles"
   as the hero worry — most Marzi travellers can walk, climb steps, and
   enjoy full-day sightseeing. The real worries are about CONFIDENCE,
   ENERGY MANAGEMENT, COUNTRY-SPECIFIC RULES (medicine carry, visa, forex),
   INDEPENDENCE FROM CHILDREN, and INTERNATIONAL TRAVEL UNFAMILIARITY.

3. Marzi's audience skews HEAVILY toward INTERNATIONAL travel — Europe,
   Southeast Asia, the first-international-trip-after-retirement moment.
   Domestic India (Golden Triangle / Kerala / Kashi) is featured on the
   site, but the brand voice should treat international travel as the
   dominant context.
"""

MARZI_HOLIDAYS_BRAND_CONTEXT = {
    "brand_name": "Marzi Holidays",
    "brand_url": "https://holidays.marzi.life",
    "tagline": "Senior-first international travel planning and preparation — built for mobile, active travellers 50+.",
    "what_it_is": (
        "Marzi Holidays is a senior-first travel concierge and planning service for "
        "mobile, active Indian travellers aged 50+ — primarily for international "
        "holidays (Europe, Southeast Asia, and beyond) and select domestic itinerary "
        "templates. It does NOT operate tours or sell packages. Instead, it offers "
        "three services: (1) Travel Mitr — a 30-minute call with an experienced "
        "travel expert covering destination choice, country-specific medicine "
        "rules, visa, forex, hotel selection, flight/seat strategy, and pacing "
        "(₹199, currently complimentary); (2) Plan Trip — an AI-assisted planner "
        "that either builds a personalised itinerary from a short questionnaire "
        "or audits an existing itinerary for pacing, comfort, and senior energy "
        "management; (3) Prepare for Trip — pre-trip preparation covering medicine "
        "eligibility (country-wise customs rules), visa and e-visa guidance, forex "
        "and emergency funds, and a senior-specific packing checklist. Travellers "
        "book and pay for hotels, flights and transport themselves — Marzi advises "
        "and plans, the traveller executes."
    ),
    "target_audience": (
        "Affluent, MOBILE, ACTIVE Indian travellers aged 50+ (and their adult "
        "children planning trips with their parents) who want to travel "
        "internationally with confidence and independence — not standard group "
        "tours, not budget itineraries, and NOT because they need mobility "
        "assistance. Most Marzi travellers can walk, climb steps, and handle "
        "full-day sightseeing. They want energy management, country-specific "
        "expertise, premium comfort, and the dignity of travelling without "
        "depending on their children."
    ),
    "primary_value": (
        "Senior-first PLANNING and ADVICE for international travel — country-specific "
        "medicine rules, visa and forex strategy, energy-managed (not mobility-managed) "
        "itineraries, senior-friendly hotel selection, flight-seat and transit-time "
        "expertise, and an audit of any itinerary the traveller already has. Marzi "
        "does not handle bookings; it shapes the trip the traveller is about to book."
    ),
    # ── Mirrors marzi.life schema so prompt code reading 'cities' still works.
    # For travel these are *traveller's destination contexts*, not service cities.
    "cities": [
        "Europe (Switzerland, Italy, France, UK, Scandinavia)",
        "Southeast Asia (Singapore, Thailand, Vietnam, Japan)",
        "Middle East (Dubai, Doha)",
        "USA & Canada",
        "Australia & New Zealand",
        # Domestic templates also featured on holidays.marzi.life:
        "Delhi, Agra, Jaipur (Golden Triangle)",
        "Munnar, Alleppey, Kochi (Kerala)",
        "Varanasi, Sarnath (Spiritual Kashi)",
    ],
    "destinations": [
        "Europe (especially first-time international destinations after retirement)",
        "Southeast Asia (senior-friendly, short flights, mature infrastructure)",
        "Domestic India templates: Golden Triangle, Kerala Serenity, Spiritual Kashi",
        "Custom destinations worldwide via the Plan Trip tool",
    ],
    # Featured itinerary TEMPLATES on holidays.marzi.life. Starting points
    # the traveller customises — NOT sold packages.
    "named_itineraries": [
        "The Golden Triangle — Delhi, Agra, Jaipur (7 days, suggested itinerary template)",
        "Kerala Serenity — Munnar, Alleppey, Kochi (6 days, suggested itinerary template)",
        "Spiritual Kashi — Varanasi, Sarnath (4 days, suggested itinerary template)",
        "Custom international itineraries — Europe, Southeast Asia, USA/Canada, etc., via Plan Trip",
    ],
    # ── Aliases used by some Writer prompt blocks ──
    "events_per_month": "On-demand: itineraries are planned per traveller, not on a fixed calendar. No group departure dates.",
    "event_group_size": "Individual / private — every plan is personalised. No group tours.",
    "event_themes": [
        "International travel for active seniors (Europe, Southeast Asia, USA/Canada)",
        "Country-specific medicine carry rules and pharmacy access abroad",
        "Visa, forex, roaming, payment strategy for Indian travellers",
        "Energy-managed (not mobility-managed) itineraries — slow pacing, fewer cities, longer stays",
        "Senior-friendly hotel selection: floor, room type, neighbourhood, lift access",
        "Flight strategy: seat choice, transit time, wheelchair-on-request vs walking",
        "Independence from adult children — travelling with confidence after retirement",
        "Domestic templates (Golden Triangle, Kerala, Kashi) as supporting content",
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
        "every service themselves. To start: request a Travel Mitr callback at "
        "holidays.marzi.life/travel-mitr or run the free AI planner at "
        "holidays.marzi.life/plan-trip."
    ),
    "services": [
        {
            "name": "Travel Mitr",
            "url": "https://holidays.marzi.life/travel-mitr",
            "what": "30-minute consultation call with an experienced travel expert. Covers destination choice, country-specific medicine rules, visa, forex, hotel selection, flight/seat strategy, transit time, and pacing.",
            "price": "₹199 (currently complimentary)",
            "hours": "9 AM – 7 PM, Mon–Sat",
            "booking": "Submit phone number; Marzi calls back to schedule.",
        },
        {
            "name": "Plan Trip",
            "url": "https://holidays.marzi.life/plan-trip",
            "what": "AI-assisted planner with two modes: (a) build a new senior-paced itinerary from a short questionnaire, or (b) paste an existing itinerary and receive a senior-comfort / energy-management / safety audit.",
            "price": "Free",
            "what_it_does_NOT_do": "Does not book hotels, flights or transport.",
        },
        {
            "name": "Prepare for Trip",
            "url": "https://holidays.marzi.life/prepare",
            "what": "Pre-trip preparation: medicine eligibility checker (country-wise customs rules), visa and e-visa guidance, forex card vs cash with emergency funds, and a senior packing checklist covering medical essentials, comfort, documents and daily gear.",
            "price": "Free",
            "tools": [
                "Medicine eligibility checker (holidays.marzi.life/prepare/medicine-checker)",
                "Visa review (Travel Mitr callback with subject=visa)",
                "Forex optimisation (Travel Mitr callback with subject=forex)",
            ],
        },
    ],
    # ── Editorial coverage areas — guides Researcher + Writer on what
    # genuinely matters for active senior international travel. Replaces the
    # old mobility-first framing.
    "editorial_coverage_areas": [
        "International travel anxiety, confidence, and the first-trip-after-retirement moment",
        "Medicines & health: country-wise carry rules, BP/diabetes/thyroid management abroad, doctor consultations before flying",
        "Flights & airports: senior-friendly seat choice, transit time, optional wheelchair assistance, airport navigation",
        "Hotels & stays: what makes a hotel actually senior-friendly (floor, room type, lift, neighbourhood, safety), avoiding cheap-hotel traps",
        "Itinerary & pace: energy management (NOT mobility management), slow travel, fewer cities, longer stays, the difference between tourist travel and comfortable travel",
        "Forex, payments & connectivity: forex card vs credit card vs cash, international roaming, safe money handling abroad",
        "Destination-specific senior guides: best first-time international destinations, Europe walkability, comfort-ranked countries, retirement holidays",
        "Emotional & identity: independence from adult children, dignity, why comfortable travel ≠ luxury, why travel matters after retirement",
    ],
    "key_differentiators": [
        "Senior-first by design — for MOBILE, ACTIVE travellers 50+ (energy management, not mobility management).",
        "International-travel expertise: country-specific medicine carry rules, visa, forex, roaming, hotel selection abroad.",
        "Advisory model, not a tour operator: a real travel expert calls you back (Travel Mitr).",
        "Free AI planner that builds OR audits an itinerary for senior comfort, pacing, and safety.",
        "Concrete pre-trip prep: medicine customs-eligibility checker, e-visa guidance, forex strategy, senior packing list.",
        "Premium positioning: not a budget OTA, not a mass-market group tour.",
        "Traveller stays in control: Marzi advises; the traveller books and executes.",
    ],
    "what_marzi_is_NOT": [
        "NOT a tour operator — Marzi does not run group tours or fixed-departure trips.",
        "NOT a packaged-holiday seller — there are no all-inclusive packages for sale.",
        "NOT a booking platform — Marzi does not book hotels, flights, or transport.",
        "NOT an OTA (online travel agency) — no flight/hotel inventory or transactional checkout.",
        "NOT a budget or backpacker service — premium, senior-first, advisory positioning.",
        "NOT a mobility-assistance / wheelchair-tour service — most Marzi travellers are mobile and active. Mobility is one consideration, not the anchor.",
        "NOT a fixed-itinerary marketplace — the featured itineraries are templates the traveller customises, not products on a shelf.",
    ],
    "content_guidelines": [
        "STRUCTURE — DESTINATION/TOPIC FIRST, MARZI LAST: The blog must be at least 80% destination/topic content (real places to see, suggested itineraries, attractions, practical facts) and at most 20% Marzi positioning. Do NOT thread Marzi service mentions through every section. Mention 'Marzi', 'Travel Mitr', 'Plan Trip' or 'Prepare for Trip' in AT MOST ONE dedicated closing section near the end of the article (e.g. 'How Marzi Holidays can help' or 'Planning this trip with Marzi'). The body of the article should read as a genuinely useful destination/topic guide that stands on its own without Marzi.",
        "OPEN WITH VALUE, NOT WITH BRAND: The first 3–4 sections must deliver tangible value about the destination or topic (e.g. 'Top places to see in X', 'Suggested 7-day itinerary', 'What to pack', 'Best month to visit'). Do NOT open with 'Marzi Holidays understands…' or 'At Marzi…'. The reader should feel they got a useful guide first; the Marzi mention at the end is a soft offer, not a pitch.",
        "AVOID HARD-SELL LANGUAGE: Do NOT write phrases like 'Marzi Holidays is the answer', 'Marzi solves this', 'choose Marzi', 'book with Marzi', 'Marzi takes care of everything'. When Marzi is mentioned in the closing section, frame it as a free, optional resource the reader can choose to use — not a sales pitch.",
        "AUDIENCE: Mobile, active, affluent Indian travellers 50+. They walk, climb steps, enjoy full days out. Do NOT default to wheelchair / step-free / mobility-obstacle framing. Lead with ENERGY MANAGEMENT, COUNTRY-SPECIFIC RULES, CONFIDENCE, and INDEPENDENCE — not with mobility limitations.",
        "DEFAULT CONTEXT: International travel (Europe, Southeast Asia, USA/Canada, etc.) — not domestic India, unless the topic explicitly names a domestic destination.",
        "FACTUAL ACCURACY: Marzi Holidays is a planning & concierge service, not a tour operator. Never imply Marzi sells packages, runs group tours, or books hotels/flights/transport.",
        "When the topic is destination-based, ALWAYS include: (a) a 'Top places to see' or 'Highlights' section with 5–7 named real attractions, and (b) a suggested itinerary outline (4–7 days, day-by-day high-level) that a traveller could actually use as a starting point. These are the main content of the blog.",
        "When recommending Marzi as a next step (in the single closing section only), name the correct service: Travel Mitr (expert callback) for advice, Plan Trip (free AI planner / audit) for itineraries, Prepare for Trip for medicine/visa/forex/packing.",
        "Always cite a specific, verifiable resource — named hospital, named app, named helpline, named insurer, named pharmacy chain, named airline policy — never generic advice.",
        "Use Indian English; reference Indian forums where relevant (TripAdvisor India, Quora India, Reddit r/india / r/IndiaTravel).",
        "Quote real traveller worries verbatim where research surfaced them.",
        "Preferred term: 'Indian travellers 50+' (or '55+', '60+'). Avoid patronising tone.",
        "Cover the relevant dimensions for the topic: medicines & health, flights & airports, hotels & stay, itinerary & pace, forex/payments/connectivity, emotional/identity. Pick the dimensions that fit the topic — don't force all.",
        "Mention senior-paced suggestions where relevant; do NOT claim Marzi 'curates stays' or 'operates' anything on the ground.",
    ],
    "persona": (
        "Senior Marketing Insights Analyst & Research Assistant for Marzi Holidays — "
        "premium senior-first INTERNATIONAL travel planning & concierge for mobile, "
        "active Indian travellers 50+."
    ),
}
