"""Travel-branded distributor.

Subclasses backend `DistributorAgent` and overrides only the two methods
whose copy is brand-specific: `_update_index` and `_generate_llms_txt`.

Sitemap, robots.txt, page discovery (across runs), and the firebase deploy
flow are all inherited unchanged. The deploy correctly targets the travel
Firebase site because `firebase_root = output_dir.parent` resolves to
`travel-blogs/firebase-hosting/`, which has its own `firebase.json` + `.firebaserc`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from html import escape

from app.agents.compiler import CompiledPage
from app.agents.distributor import (
    DistributorAgent,
    _CATEGORY_DISPLAY,
    _LLMS_CATEGORY_HEADINGS,
)

from marzi_travel import site_config

logger = logging.getLogger(__name__)


def _build_travel_llms_txt(pages: list[CompiledPage]) -> str:
    """Marzi Holidays-flavoured llms.txt."""
    site_url = site_config.SITE_URL.rstrip("/")

    grouped: dict[str, list[CompiledPage]] = {}
    for p in pages:
        grouped.setdefault(p.category, []).append(p)

    lines = [
        f"# {site_config.SITE_NAME}",
        "",
        f"> {site_config.LLMS_SUMMARY}",
        "",
        "## About",
        "",
    ]
    lines.extend(f"- {about}" for about in site_config.LLMS_ABOUT_LINES)
    lines.append("")

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


def _build_travel_index_html(pages: list[CompiledPage]) -> str:
    """Marzi Holidays-flavoured landing page."""
    now_year = datetime.now().year

    cards_html = ""
    for page in pages:
        cat_display = _CATEGORY_DISPLAY.get(
            page.category, {"label": "Article", "icon": "journal-text"}
        )
        slug = page.slug
        title_esc = escape(page.title, quote=True)
        tags_str = (
            " &middot; ".join(page.tags[:3]) if page.tags else cat_display["label"]
        )
        cards_html += f"""        <a class="card" href="/{slug}">
            <h2>{title_esc}</h2>
            <span>{cat_display['label']} &middot; {tags_str}</span>
        </a>
"""

    subtitle = site_config.INDEX_SUBTITLE
    footer_url = site_config.BRAND_FOOTER_URL
    footer_label = (
        footer_url.replace("https://", "").replace("http://", "").rstrip("/")
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <!-- Google Tag Manager -->
    <script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
    new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
    j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
    'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
    }})(window,document,'script','dataLayer','GTM-NKZVBC55');</script>
    <!-- End Google Tag Manager -->
    <title>{escape(site_config.SITE_NAME)}</title>
    <meta name="description" content="{escape(subtitle)}">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="{site_config.SITE_URL}/">
    <link rel="sitemap" type="application/xml" href="{site_config.SITE_URL}/sitemap.xml">
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
        <h1>{escape(site_config.SITE_NAME)}</h1>
        <p class="sub">{escape(subtitle)}</p>
{cards_html}
        <div class="footer">&copy; {now_year} {escape(site_config.ORGANIZATION_NAME)} &middot; <a href="{escape(footer_url, quote=True)}" style="color:#64748b;">{escape(footer_label)}</a></div>
    </div>
</body>
</html>
"""


class TravelDistributorAgent(DistributorAgent):
    """Distributor with Marzi Holidays copy in index.html + llms.txt.

    Inherits sitemap.xml, robots.txt, page-discovery, and Firebase deploy
    behavior from the parent. Backend is not modified.
    """

    def _update_index(self, pages):
        try:
            index_html = _build_travel_index_html(pages)
            index_path = self.output_dir / "index.html"
            index_path.write_text(index_html, encoding="utf-8")
            logger.info(f"[TravelDistributor] Index updated: {index_path}")
            return True
        except Exception as e:
            logger.error(f"[TravelDistributor] Failed to update index: {e}")
            return False

    def _generate_llms_txt(self, pages):
        try:
            llms_txt = _build_travel_llms_txt(pages)
            llms_path = self.output_dir / "llms.txt"
            llms_path.write_text(llms_txt, encoding="utf-8")
            logger.info(
                f"[TravelDistributor] llms.txt generated: {llms_path} "
                f"({len(llms_txt)} bytes)"
            )
            return True
        except Exception as e:
            logger.error(f"[TravelDistributor] Failed to generate llms.txt: {e}")
            return False
