"""Travel-flavoured Strategist.

Backend's `_generate_slug` does `f"{brand_slug}-{text}"` where `brand_slug`
is the lowercased brand name. For "Marzi Holidays" that produces a slug
with an embedded space ("marzi holidays-kerala-..."), which breaks URLs.

This thin subclass calls the backend Strategist and post-sanitizes the slug.
Backend is not modified.
"""

from __future__ import annotations

import re

from app.agents.strategist import StrategistAgent, ContentBlueprint
from app.schemas.content import ContentCategory
from app.agents.researcher import ResearchDossier


class TravelStrategistAgent(StrategistAgent):
    def run(
        self,
        dossier: ResearchDossier,
        category_override: ContentCategory | None = None,
    ) -> ContentBlueprint:
        bp = super().run(dossier, category_override)
        # Replace any whitespace introduced by a multi-word brand name and
        # collapse repeated hyphens. The 80-char cap is preserved.
        cleaned = re.sub(r"\s+", "-", bp.slug)
        cleaned = re.sub(r"-+", "-", cleaned).strip("-")
        bp.slug = cleaned[:80].strip("-")
        return bp
