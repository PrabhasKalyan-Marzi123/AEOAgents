"""Agent 4: The Static Site Compiler.

Takes WrittenContent from the Writer agent and:
1. Generates category-specific JSON-LD structured data
2. Wraps content into the full HTML page template (navbar, hero, sidebar, footer)
3. Writes the physical .html file to firebase-hosting/public/

Uses existing build_full_page() and generate_jsonld() as its foundation.

Output: CompiledPage with file path and metadata.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from app.services.html_builder import build_full_page
from app.services.jsonld import generate_jsonld
from app.agents.writer import WrittenContent

logger = logging.getLogger(__name__)

# Default output directory — firebase-hosting/public/ relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # backend/app/agents/ → project root
DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "firebase-hosting" / "public"


@dataclass
class CompiledPage:
    """Output from the Compiler agent."""

    file_path: str = ""
    slug: str = ""
    title: str = ""
    category: str = ""
    meta_description: str = ""
    tags: list[str] = None
    jsonld: dict = None
    full_html: str = ""

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.jsonld is None:
            self.jsonld = {}


class CompilerAgent:
    """Agent 4: Static Site Compiler.

    Wraps generated content into complete HTML pages and writes them
    to the firebase-hosting/public/ directory.
    """

    def __init__(self, output_dir: str | Path | None = None):
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR

    def run(self, written: WrittenContent) -> CompiledPage:
        """Compile written content into a deployable HTML file.

        1. Generate JSON-LD structured data
        2. Build complete HTML page
        3. Write to firebase-hosting/public/{slug}.html

        Args:
            written: Content from Agent 3

        Returns:
            CompiledPage with file path and metadata
        """
        logger.info(f"[Compiler] Compiling page: slug='{written.slug}'")

        # 1. Generate JSON-LD
        jsonld = generate_jsonld(
            category=written.category,
            html=written.content_html,
            title=written.title,
            slug=written.slug,
            specific_data=written.jsonld_data,
            meta_description=written.meta_description,
        )
        logger.info(f"[Compiler] JSON-LD generated: @type={jsonld.get('@type', 'unknown')}")

        # 2. Build full HTML page using existing template
        generated_content = written.to_generated_content()
        full_html = build_full_page(generated_content, jsonld)

        # 3. Write to output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{written.slug}.html"
        file_path = self.output_dir / filename

        file_path.write_text(full_html, encoding="utf-8")
        logger.info(f"[Compiler] Written: {file_path} ({len(full_html)} bytes)")

        return CompiledPage(
            file_path=str(file_path),
            slug=written.slug,
            title=written.title,
            category=written.category.value,
            meta_description=written.meta_description,
            tags=written.tags,
            jsonld=jsonld,
            full_html=full_html,
        )
