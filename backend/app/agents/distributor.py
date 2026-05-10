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

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape, unescape
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
    llms_txt_generated: bool = False
    deploy_output: str = ""
    live_urls: list[str] = field(default_factory=list)


# ── Category display config for index page ──
_CATEGORY_DISPLAY = {
    "faq": {"label": "FAQPage schema", "icon": "question-circle"},
    "how-to": {"label": "HowTo schema", "icon": "tools"},
    "comparison": {"label": "Review + ItemList schema", "icon": "bar-chart"},
    "informational": {"label": "Article schema", "icon": "journal-text"},
}

_LLMS_CATEGORY_HEADINGS = {
    "faq": "FAQ & Q&A",
    "how-to": "How-To Guides",
    "comparison": "Comparisons & Reviews",
    "informational": "Articles",
}

# Inverse of strategist._SCHEMA_MAP — used when reconstructing pages from disk.
_SCHEMA_TO_CATEGORY = {
    "FAQPage": "faq",
    "HowTo": "how-to",
    "Article": "comparison",
    "BlogPosting": "informational",
}

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_DESC_RE = re.compile(
    r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _parse_html_to_page(html_path: Path) -> CompiledPage:
    """Reconstruct a CompiledPage from a previously-written .html file.

    Reads <title>, <meta name="description">, and the JSON-LD @type to fill in
    enough metadata for the index/sitemap/llms.txt builders.
    """
    text = html_path.read_text(encoding="utf-8", errors="replace")
    slug = html_path.stem

    # Title — strip a trailing " | {site_name}" suffix that the template adds.
    title = ""
    m = _TITLE_RE.search(text)
    if m:
        title = unescape(m.group(1)).strip()
        suffix = f" | {settings.site_name}"
        if title.endswith(suffix):
            title = title[: -len(suffix)].rstrip()

    # Meta description
    meta_description = ""
    m = _META_DESC_RE.search(text)
    if m:
        meta_description = unescape(m.group(1)).strip()

    # JSON-LD @type → category
    category = "informational"
    jsonld: dict = {}
    m = _JSONLD_RE.search(text)
    if m:
        try:
            jsonld = json.loads(m.group(1).strip())
            schema_type = jsonld.get("@type") if isinstance(jsonld, dict) else None
            if isinstance(schema_type, str):
                category = _SCHEMA_TO_CATEGORY.get(schema_type, "informational")
        except json.JSONDecodeError:
            jsonld = {}

    return CompiledPage(
        file_path=str(html_path),
        slug=slug,
        title=title or slug,
        category=category,
        meta_description=meta_description,
        tags=[],
        jsonld=jsonld,
        full_html="",
    )


def _build_llms_txt(pages: list[CompiledPage]) -> str:
    """Build llms.txt — a markdown index for AI crawlers (https://llmstxt.org).

    Groups pages by category and lists each as `- [Title](URL): description`.
    """
    site_url = settings.site_url.rstrip("/")
    summary = (
        f"AEO-optimized content for {settings.organization_name} — offline social "
        f"events for people above 55 in Bangalore and Mumbai. Each page is a snippet-ready "
        f"answer aligned to a schema.org type (FAQPage, HowTo, Article, BlogPosting)."
    )

    grouped: dict[str, list[CompiledPage]] = {}
    for p in pages:
        grouped.setdefault(p.category, []).append(p)

    lines = [
        f"# {settings.site_name}",
        "",
        f"> {summary}",
        "",
        "## About",
        "",
        f"- Brand: {settings.organization_name} (https://marzi.life)",
        f"- Format: 20+ themed offline social events per month, group size 20–60",
        f"- Cities: Bangalore, Mumbai",
        f"- Pricing: Pay-per-event (no subscription)",
        "",
    ]

    for category in ["faq", "how-to", "comparison", "informational"]:
        bucket = grouped.get(category)
        if not bucket:
            continue
        heading = _LLMS_CATEGORY_HEADINGS.get(category, category.title())
        lines.append(f"## {heading}")
        lines.append("")
        for p in bucket:
            url = f"{site_url}/{p.slug}"
            desc = (p.meta_description or "").strip().replace("\n", " ")
            if len(desc) > 200:
                desc = desc[:197].rstrip() + "…"
            entry = f"- [{p.title}]({url})"
            if desc:
                entry += f": {desc}"
            lines.append(entry)
        lines.append("")

    lines.extend([
        "## Optional",
        "",
        f"- [Sitemap]({site_url}/sitemap.xml): full machine-readable index of all pages",
        f"- [robots.txt]({site_url}/robots.txt): crawler policy (AI crawlers explicitly allowed)",
        "",
    ])

    return "\n".join(lines)


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

    def _generate_llms_txt(self, pages: list[CompiledPage]) -> bool:
        """Generate llms.txt — markdown index for AI crawlers (llmstxt.org)."""
        try:
            llms_txt = _build_llms_txt(pages)
            llms_path = self.output_dir / "llms.txt"
            llms_path.write_text(llms_txt, encoding="utf-8")
            logger.info(f"[Distributor] llms.txt generated: {llms_path} ({len(llms_txt)} bytes)")
            return True
        except Exception as e:
            logger.error(f"[Distributor] Failed to generate llms.txt: {e}")
            return False

    def discover_existing_pages(self) -> list[CompiledPage]:
        """Scan output_dir for already-published .html files and reconstruct CompiledPage entries.

        Lets index/sitemap/llms.txt accumulate pages across multiple pipeline runs:
        the filesystem is the source of truth for what's live.
        """
        if not self.output_dir.exists():
            return []

        discovered: list[CompiledPage] = []
        for html_path in sorted(self.output_dir.glob("*.html")):
            if html_path.name == "index.html":
                continue
            try:
                discovered.append(_parse_html_to_page(html_path))
            except Exception as e:
                logger.warning(f"[Distributor] Skipping unparseable file {html_path.name}: {e}")
        return discovered

    def _merge_pages(
        self,
        current: list[CompiledPage],
        existing: list[CompiledPage],
    ) -> list[CompiledPage]:
        """Merge discovered pages with current-run pages. Current run wins on slug collision."""
        merged: dict[str, CompiledPage] = {p.slug: p for p in existing if p.slug}
        for p in current:
            if p.slug:
                merged[p.slug] = p
        return sorted(merged.values(), key=lambda p: p.slug)

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

        # Discover already-published pages on disk and merge — sitemap/index/llms.txt
        # accumulate every live page across pipeline runs, not just the current batch.
        existing = self.discover_existing_pages()
        all_pages = self._merge_pages(pages, existing)
        logger.info(
            f"[Distributor] Merged pages: {len(existing)} existing, "
            f"{len(pages)} from current run, {len(all_pages)} total"
        )

        # Collect page metadata for current run only (what got published this time)
        result.pages_published = [
            {"slug": p.slug, "title": p.title, "category": p.category}
            for p in pages
        ]

        # 1. Update index — use the union so old pages stay discoverable
        result.index_updated = self._update_index(all_pages)

        # 2. Sitemap — every live URL
        result.sitemap_generated = self._generate_sitemap(all_pages)

        # 3. Robots.txt
        result.robots_generated = self._generate_robots()

        # 4. llms.txt (AI-crawler markdown index) — every live URL
        result.llms_txt_generated = self._generate_llms_txt(all_pages)

        # 5. Deploy
        if deploy:
            deployed, output = self._deploy_firebase()
            result.deployed = deployed
            result.deploy_output = output
        else:
            logger.info("[Distributor] Skipping Firebase deploy (deploy=False)")

        # Build live URLs from the union — the printed summary lists everything live
        result.live_urls = [
            f"{settings.site_url}/{p.slug}" for p in all_pages
        ]

        logger.info(
            f"[Distributor] Done: index={result.index_updated}, "
            f"sitemap={result.sitemap_generated}, llms_txt={result.llms_txt_generated}, "
            f"deployed={result.deployed}"
        )
        return result

    # ── Future extension points ──

    def publish_to_twitter(self, page: CompiledPage) -> bool:
        """Placeholder for Twitter/X publishing agent."""
        raise NotImplementedError("Twitter publishing not yet implemented")

    def publish_to_linkedin(self, page: CompiledPage) -> bool:
        """Placeholder for LinkedIn publishing agent."""
        raise NotImplementedError("LinkedIn publishing not yet implemented")
