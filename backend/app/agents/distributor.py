"""Agent 5: The Distribution Agent.

Handles post-compilation tasks:
1. Updates the index.html landing page with links to all published content
2. Generates sitemap.xml for search engine discovery
3. Generates robots.txt allowing AI crawlers
4. Executes firebase deploy --only hosting

Future-proofed with a modular design so social media publishing agents
(Twitter/X, LinkedIn, etc.) can be plugged in later.

Output: DeploymentResult with URLs and deployment status.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from app.config import settings
from app.services.html_builder import build_sitemap, build_robots_txt
from app.agents.compiler import CompiledPage, DEFAULT_OUTPUT_DIR

logger = logging.getLogger(__name__)

# Firebase hosting root (contains firebase.json)
_FIREBASE_ROOT = DEFAULT_OUTPUT_DIR.parent


@dataclass
class DeploymentResult:
    """Output from the Distribution agent."""

    deployed: bool = False
    pages_published: list[dict] = field(default_factory=list)
    index_updated: bool = False
    sitemap_generated: bool = False
    robots_generated: bool = False
    deploy_output: str = ""
    live_urls: list[str] = field(default_factory=list)


# ── Category display config for index page ──
_CATEGORY_DISPLAY = {
    "faq": {"label": "FAQPage schema", "icon": "question-circle"},
    "how-to": {"label": "HowTo schema", "icon": "tools"},
    "comparison": {"label": "Review + ItemList schema", "icon": "bar-chart"},
    "informational": {"label": "Article schema", "icon": "journal-text"},
}


def _build_index_html(pages: list[CompiledPage]) -> str:
    """Build the index.html landing page listing all published content."""
    now_year = datetime.now().year

    cards_html = ""
    for page in pages:
        cat_display = _CATEGORY_DISPLAY.get(page.category, {"label": "Article", "icon": "journal-text"})
        slug = page.slug
        title_esc = escape(page.title, quote=True)
        desc_esc = escape(page.meta_description or "", quote=True)
        tags_str = " &middot; ".join(page.tags[:3]) if page.tags else cat_display["label"]

        cards_html += f"""        <a class="card" href="/{slug}">
            <h2>{title_esc}</h2>
            <span>{cat_display['label']} &middot; {tags_str}</span>
        </a>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(settings.site_name)}</title>
    <meta name="description" content="AEO-optimized content for {escape(settings.organization_name)} — offline events for people above 55 in Bangalore &amp; Mumbai">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="{settings.site_url}/">
    <link rel="sitemap" type="application/xml" href="{settings.site_url}/sitemap.xml">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; background: #f8fafc; color: #1a1a1a; margin: 0; padding: 40px 20px; }}
        .container {{ max-width: 700px; margin: 0 auto; }}
        h1 {{ font-size: 2rem; margin-bottom: 8px; }}
        p.sub {{ color: #64748b; margin-bottom: 32px; }}
        a.card {{ display: block; background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px 24px; margin-bottom: 16px; text-decoration: none; color: #1a1a1a; transition: box-shadow 0.2s; }}
        a.card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
        a.card h2 {{ font-size: 1.1rem; margin: 0 0 6px; }}
        a.card span {{ font-size: 0.85rem; color: #64748b; }}
        .footer {{ margin-top: 48px; text-align: center; color: #94a3b8; font-size: 0.8rem; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{escape(settings.site_name)}</h1>
        <p class="sub">AEO-optimized content &middot; Offline events for people above 55 in Bangalore &amp; Mumbai</p>
{cards_html}
        <div class="footer">&copy; {now_year} {escape(settings.organization_name)} &middot; <a href="https://marzi.life" style="color:#64748b;">marzi.life</a></div>
    </div>
</body>
</html>
"""


class DistributorAgent:
    """Agent 5: Distribution Agent.

    Updates the index, generates SEO files, and deploys to Firebase.
    Designed to be modular — additional distribution channels (social media,
    newsletters, etc.) can be added as methods.
    """

    def __init__(self, output_dir: str | Path | None = None):
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        self.firebase_root = self.output_dir.parent

    def _update_index(self, pages: list[CompiledPage]) -> bool:
        """Regenerate index.html with links to all compiled pages."""
        try:
            index_html = _build_index_html(pages)
            index_path = self.output_dir / "index.html"
            index_path.write_text(index_html, encoding="utf-8")
            logger.info(f"[Distributor] Index updated: {index_path}")
            return True
        except Exception as e:
            logger.error(f"[Distributor] Failed to update index: {e}")
            return False

    def _generate_sitemap(self, pages: list[CompiledPage]) -> bool:
        """Generate sitemap.xml from compiled pages."""
        try:
            entries = [
                {
                    "slug": p.slug,
                    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "category": p.category,
                }
                for p in pages
            ]
            sitemap_xml = build_sitemap(entries)
            sitemap_path = self.output_dir / "sitemap.xml"
            sitemap_path.write_text(sitemap_xml, encoding="utf-8")
            logger.info(f"[Distributor] Sitemap generated: {sitemap_path}")
            return True
        except Exception as e:
            logger.error(f"[Distributor] Failed to generate sitemap: {e}")
            return False

    def _generate_robots(self) -> bool:
        """Generate robots.txt allowing AI crawlers."""
        try:
            robots_txt = build_robots_txt()
            robots_path = self.output_dir / "robots.txt"
            robots_path.write_text(robots_txt, encoding="utf-8")
            logger.info(f"[Distributor] robots.txt generated: {robots_path}")
            return True
        except Exception as e:
            logger.error(f"[Distributor] Failed to generate robots.txt: {e}")
            return False

    def _deploy_firebase(self) -> tuple[bool, str]:
        """Execute firebase deploy --only hosting.

        Returns (success, output_text).
        """
        try:
            result = subprocess.run(
                ["firebase", "deploy", "--only", "hosting"],
                cwd=str(self.firebase_root),
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = result.stdout + result.stderr
            success = result.returncode == 0

            if success:
                logger.info("[Distributor] Firebase deploy succeeded")
            else:
                logger.error(f"[Distributor] Firebase deploy failed: {output}")

            return success, output
        except FileNotFoundError:
            msg = "Firebase CLI not found — install with: npm install -g firebase-tools"
            logger.error(f"[Distributor] {msg}")
            return False, msg
        except subprocess.TimeoutExpired:
            msg = "Firebase deploy timed out after 120s"
            logger.error(f"[Distributor] {msg}")
            return False, msg
        except Exception as e:
            msg = f"Firebase deploy error: {e}"
            logger.error(f"[Distributor] {msg}")
            return False, msg

    def run(self, pages: list[CompiledPage], deploy: bool = True) -> DeploymentResult:
        """Execute the full distribution pipeline.

        1. Update index.html
        2. Generate sitemap.xml
        3. Generate robots.txt
        4. Deploy to Firebase (if deploy=True)

        Args:
            pages: All compiled pages (including any existing ones to keep in index)
            deploy: Whether to run firebase deploy (set False for local-only)

        Returns:
            DeploymentResult with status of each step
        """
        logger.info(f"[Distributor] Starting distribution for {len(pages)} pages")

        result = DeploymentResult()

        # Collect page metadata
        result.pages_published = [
            {"slug": p.slug, "title": p.title, "category": p.category}
            for p in pages
        ]

        # 1. Update index
        result.index_updated = self._update_index(pages)

        # 2. Sitemap
        result.sitemap_generated = self._generate_sitemap(pages)

        # 3. Robots.txt
        result.robots_generated = self._generate_robots()

        # 4. Deploy
        if deploy:
            deployed, output = self._deploy_firebase()
            result.deployed = deployed
            result.deploy_output = output
        else:
            logger.info("[Distributor] Skipping Firebase deploy (deploy=False)")

        # Build live URLs
        result.live_urls = [
            f"{settings.site_url}/{p.slug}" for p in pages
        ]

        logger.info(
            f"[Distributor] Done: index={result.index_updated}, "
            f"sitemap={result.sitemap_generated}, deployed={result.deployed}"
        )
        return result

    # ── Future extension points ──

    def publish_to_twitter(self, page: CompiledPage) -> bool:
        """Placeholder for Twitter/X publishing agent."""
        raise NotImplementedError("Twitter publishing not yet implemented")

    def publish_to_linkedin(self, page: CompiledPage) -> bool:
        """Placeholder for LinkedIn publishing agent."""
        raise NotImplementedError("LinkedIn publishing not yet implemented")
