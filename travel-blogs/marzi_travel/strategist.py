"""Travel-flavoured Strategist.

Two travel-specific tweaks on top of the brand-agnostic backend Strategist:

1. Slug sanitisation: backend's `_generate_slug` does
   `f"{brand_slug}-{text}"` where `brand_slug` is the lowercased brand name.
   For "Marzi Holidays" that produces a slug with an embedded space
   ("marzi holidays-kerala-..."), which breaks URLs.

2. Category override: backend's COMPARISON template hardcodes brand-vs-X
   sections ("How {brand} compares to ...", "Pros and Cons of {brand}",
   "Verdict and recommendation"). For travel destinations/topics this turns
   every "Best X" blog into a brand pitch. We force such intents to
   INFORMATIONAL so the article is destination-first with Marzi only in a
   single closing section, per the editorial stance in brand_context.py.

Backend is not modified.
"""

from __future__ import annotations

import logging
import re

from app.agents.strategist import StrategistAgent, ContentBlueprint, _decide_category
from app.schemas.content import ContentCategory
from app.agents.researcher import ResearchDossier

logger = logging.getLogger(__name__)


class TravelStrategistAgent(StrategistAgent):
    def run(
        self,
        dossier: ResearchDossier,
        category_override: ContentCategory | None = None,
    ) -> ContentBlueprint:
        # Block the COMPARISON category. Backend's COMPARISON outline is
        # brand-anchored ("How {brand} compares to X", "Pros and Cons of
        # {brand}") which produces hard-sell travel blogs. Check BOTH the
        # SERP intent AND the final keyword-fallback decision — phrases like
        # "best X" or "X vs Y" route to COMPARISON via the fallback even when
        # SERP says informational.
        if category_override is None:
            decided = _decide_category(dossier)
            if decided == ContentCategory.COMPARISON:
                logger.info(
                    "[TravelStrategist] Demoting COMPARISON → INFORMATIONAL "
                    f"(topic='{dossier.topic}', destination-first editorial stance)"
                )
                category_override = ContentCategory.INFORMATIONAL

        bp = super().run(dossier, category_override)
        # Replace any whitespace introduced by a multi-word brand name and
        # collapse repeated hyphens. The 80-char cap is preserved.
        cleaned = re.sub(r"\s+", "-", bp.slug)
        cleaned = re.sub(r"-+", "-", cleaned).strip("-")
        bp.slug = cleaned[:80].strip("-")
        return bp
