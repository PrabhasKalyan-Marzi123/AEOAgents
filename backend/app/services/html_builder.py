"""HTML page builder that combines generated content + JSON-LD into a complete, publishable page.

Produces a full HTML document with:
- Clean, minimal blog layout (readable article width, generous white space)
- Dynamic brand accent color extracted from the brand website
- Brand logo in a slim navbar
- Proper <head> with meta tags (title, description, Open Graph, robots)
- JSON-LD <script> tag for structured data
- Semantic HTML body content with polished typography
- Sitemap reference in <head>
- AI-crawler-friendly meta directives
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import escape

from app.config import settings
from app.schemas.content import ContentCategory, GeneratedContent
from app.services.jsonld import generate_jsonld


# ── Category display config ──
_CATEGORY_META = {
    ContentCategory.FAQ: {"label": "FAQ", "icon": "bi-question-circle-fill"},
    ContentCategory.HOW_TO: {"label": "How-To Guide", "icon": "bi-tools"},
    ContentCategory.COMPARISON: {"label": "Comparison", "icon": "bi-bar-chart-line"},
    ContentCategory.INFORMATIONAL: {"label": "Article", "icon": "bi-journal-text"},
}

# Reading-time estimate icon sets per category
_CATEGORY_READ_TIME = {
    ContentCategory.FAQ: "3 min read",
    ContentCategory.HOW_TO: "5 min read",
    ContentCategory.COMPARISON: "6 min read",
    ContentCategory.INFORMATIONAL: "4 min read",
}


def _safe(value: str) -> str:
    """Escape for safe use in HTML attributes."""
    return escape(value, quote=True)


def _lighten_hex(hex_color: str, amount: float = 0.92) -> str:
    """Create a very light tint of a hex color (for backgrounds). amount=0.92 → 92% toward white."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def build_full_page(content: GeneratedContent, jsonld: dict | None = None) -> str:
    """Build a complete HTML page from generated content + JSON-LD.

    Clean blog layout with brand accent color, readable typography, and
    full AI-visibility preservation (JSON-LD, meta tags, semantic HTML).
    """
    if jsonld is None:
        jsonld = generate_jsonld(
            category=content.category,
            html=content.content_html,
            title=content.title,
            slug=content.slug,
            specific_data=content.jsonld_data,
            meta_description=content.meta_description,
        )

    # ── Brand data (dynamic) ──
    brand = content.brand_data or {}
    brand_name = brand.get("brand_name", "") or settings.organization_name or settings.site_name
    brand_url = brand.get("brand_url", content.brand_url)
    logo_url = brand.get("logo_url", "")
    favicon_url = brand.get("favicon_url", brand_url.rstrip("/") + "/favicon.ico")
    brand_colors = brand.get("brand_colors", [])

    # Single accent color — keep the palette minimal
    accent = brand_colors[0] if brand_colors else "#2563eb"
    accent_light = _lighten_hex(accent, 0.93)
    accent_muted = _lighten_hex(accent, 0.82)

    # Strip leading <h1> from generated content — the template renders its own
    body_html = re.sub(r"^\s*<h1[^>]*>.*?</h1>\s*", "", content.content_html, count=1, flags=re.DOTALL)

    jsonld_script = json.dumps(jsonld, indent=2, ensure_ascii=False)
    canonical_url = f"{settings.site_url}/{content.slug}"
    tags_str = ", ".join(content.tags) if content.tags else content.topic
    author_name = settings.default_author or settings.organization_name or settings.site_name
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_display = datetime.now(timezone.utc).strftime("%b %d, %Y")

    cat_meta = _CATEGORY_META.get(content.category, {"label": "Article", "icon": "bi-journal-text"})
    read_time = _CATEGORY_READ_TIME.get(content.category, "4 min read")

    # Organization JSON-LD
    org_jsonld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": brand_name,
            "url": brand_url,
            **({"logo": logo_url} if logo_url else {}),
        },
        indent=2,
    )

    # Logo HTML
    if logo_url:
        logo_img = f'<img src="{_safe(logo_url)}" alt="{_safe(brand_name)}" style="height:28px;width:auto;">'
    else:
        logo_img = f'<i class="bi bi-globe2" style="font-size:1.25rem;"></i>'

    # Tag pills
    tag_pills = "".join(
        f'<span style="display:inline-block;padding:4px 12px;margin:0 6px 6px 0;'
        f'font-size:0.8rem;font-weight:500;color:{accent};background:{accent_light};'
        f'border-radius:20px;">{_safe(t)}</span>'
        for t in (content.tags or [])
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

    <!-- SEO Meta -->
    <title>{_safe(content.title)}</title>
    <meta name="description" content="{_safe(content.meta_description)}">
    <meta name="keywords" content="{_safe(tags_str)}">
    <meta name="author" content="{_safe(author_name)}">
    <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
    <meta name="date" content="{now_iso}">

    <!-- Open Graph -->
    <meta property="og:title" content="{_safe(content.title)}">
    <meta property="og:description" content="{_safe(content.meta_description)}">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:type" content="article">
    <meta property="og:site_name" content="{_safe(brand_name)}">
    {f'<meta property="og:image" content="{_safe(logo_url)}">' if logo_url else ""}

    <!-- Favicon -->
    <link rel="icon" href="{_safe(favicon_url)}" type="image/x-icon">

    <!-- Canonical -->
    <link rel="canonical" href="{canonical_url}">

    <!-- Sitemap Reference -->
    <link rel="sitemap" type="application/xml" href="{settings.site_url}/sitemap.xml">

    <!-- Bootstrap 5 CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"
          integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YcnS/1dQY9S3kfE2VH7D5lCDFv1jF1ZKpYV" crossorigin="anonymous">

    <!-- Bootstrap Icons -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">

    <!-- Google Fonts — Inter -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">

    <style>
        /* ── Base ── */
        *, *::before, *::after {{ box-sizing: border-box; }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            color: #1a1a1a;
            background: #fff;
            line-height: 1.8;
            -webkit-font-smoothing: antialiased;
        }}

        /* ── Navbar ── */
        .site-nav {{
            background: #fff;
            border-bottom: 1px solid #eee;
            padding: 14px 0;
        }}
        .site-nav a {{
            text-decoration: none;
            color: #1a1a1a;
            font-weight: 600;
            font-size: 0.95rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .site-nav a:hover {{ color: {accent}; }}

        /* ── Hero ── */
        .hero {{
            padding: 48px 0 40px;
            border-bottom: 1px solid #f0f0f0;
        }}
        .hero .category-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 14px;
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: {accent};
            background: {accent_light};
            border-radius: 20px;
            margin-bottom: 20px;
        }}
        .hero h1 {{
            font-size: 2.5rem;
            font-weight: 800;
            line-height: 1.15;
            color: #0f0f0f;
            letter-spacing: -0.5px;
            margin-bottom: 16px;
            max-width: 720px;
        }}
        .hero .subtitle {{
            font-size: 1.15rem;
            color: #555;
            line-height: 1.6;
            max-width: 640px;
            margin-bottom: 24px;
        }}
        .hero .meta-row {{
            display: flex;
            align-items: center;
            gap: 20px;
            font-size: 0.85rem;
            color: #888;
        }}
        .hero .meta-row i {{ font-size: 0.9rem; }}
        .hero .meta-row .dot {{
            width: 3px;
            height: 3px;
            background: #ccc;
            border-radius: 50%;
        }}

        /* ── Article ── */
        .article-body {{
            max-width: 720px;
            margin: 0 auto;
            padding: 48px 0 64px;
        }}

        .article-body h2 {{
            font-size: 1.55rem;
            font-weight: 700;
            color: #0f0f0f;
            margin-top: 48px;
            margin-bottom: 16px;
            padding-bottom: 10px;
            border-bottom: 2px solid {accent};
        }}

        .article-body h3 {{
            font-size: 1.2rem;
            font-weight: 600;
            color: #2a2a2a;
            margin-top: 32px;
            margin-bottom: 12px;
        }}

        .article-body p {{
            font-size: 1.05rem;
            color: #333;
            margin-bottom: 20px;
        }}

        .article-body ul, .article-body ol {{
            padding-left: 24px;
            margin-bottom: 20px;
        }}

        .article-body li {{
            font-size: 1.02rem;
            color: #333;
            margin-bottom: 8px;
            line-height: 1.7;
        }}

        /* ── Cards ── */
        .article-body .card {{
            border: 1px solid #e8e8e8;
            border-radius: 10px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.04);
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .article-body .card-body {{
            padding: 24px;
        }}
        .article-body .card-title {{
            font-weight: 600;
            font-size: 1.1rem;
        }}

        /* ── Accordion (FAQ) ── */
        .article-body .accordion {{
            border: 1px solid #e8e8e8;
            border-radius: 10px;
            overflow: hidden;
        }}
        .article-body .accordion-item {{
            border: none;
            border-bottom: 1px solid #f0f0f0;
        }}
        .article-body .accordion-item:last-child {{
            border-bottom: none;
        }}
        .article-body .accordion-button {{
            font-weight: 600;
            font-size: 1.05rem;
            color: #1a1a1a;
            padding: 20px 24px;
            background: #fff;
            box-shadow: none !important;
        }}
        .article-body .accordion-button:not(.collapsed) {{
            color: {accent};
            background: {accent_light};
        }}
        .article-body .accordion-button::after {{
            filter: none;
        }}
        .article-body .accordion-body {{
            padding: 16px 24px 24px;
            font-size: 1.02rem;
            color: #444;
            line-height: 1.8;
            background: #fff;
        }}

        /* ── Tables ── */
        .article-body .table {{
            border: 1px solid #e8e8e8;
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 24px;
        }}
        .article-body .table thead th {{
            background: #f8f9fa;
            color: #333;
            font-weight: 600;
            font-size: 0.88rem;
            text-transform: uppercase;
            letter-spacing: 0.3px;
            padding: 14px 16px;
            border-bottom: 2px solid #e8e8e8;
        }}
        .article-body .table tbody td {{
            padding: 14px 16px;
            font-size: 0.97rem;
            color: #444;
            border-color: #f0f0f0;
        }}
        .article-body .table-striped > tbody > tr:nth-of-type(odd) > td {{
            background: #fafbfc;
        }}

        /* ── Badges ── */
        .article-body .badge {{
            font-weight: 500;
            font-size: 0.82rem;
            padding: 5px 12px;
        }}
        .article-body .badge.bg-primary,
        .article-body .badge.rounded-pill.bg-primary {{
            background: {accent} !important;
        }}

        /* ── Alerts ── */
        .article-body .alert {{
            border-radius: 10px;
            border: none;
            padding: 20px 24px;
        }}
        .article-body .alert-success {{
            background: {accent_light};
            color: #1a1a1a;
            border-left: 4px solid {accent};
        }}

        /* ── Blockquotes ── */
        .article-body blockquote,
        .article-body .blockquote {{
            border-left: 3px solid {accent};
            padding: 20px 24px;
            margin: 32px 0;
            background: #f9fafb;
            border-radius: 0 8px 8px 0;
            font-size: 1.08rem;
            color: #333;
            font-style: italic;
        }}

        /* ── List groups ── */
        .article-body .list-group-item {{
            border-color: #f0f0f0;
            padding: 14px 20px;
            font-size: 0.98rem;
            color: #444;
        }}

        /* ── Sidebar ── */
        .sidebar-card {{
            border: 1px solid #eee;
            border-radius: 10px;
            padding: 28px;
            margin-bottom: 24px;
            background: #fff;
        }}
        .sidebar-card h4 {{
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: #999;
            margin-bottom: 16px;
        }}

        /* ── Footer ── */
        .site-footer {{
            border-top: 1px solid #eee;
            padding: 32px 0;
            margin-top: 80px;
            color: #999;
            font-size: 0.85rem;
        }}
        .site-footer a {{
            color: #666;
            text-decoration: none;
        }}
        .site-footer a:hover {{
            color: {accent};
        }}

        /* ── Responsive ── */
        @media (max-width: 767.98px) {{
            .hero h1 {{ font-size: 1.75rem; }}
            .hero {{ padding: 32px 0 28px; }}
            .article-body {{ padding: 32px 0 48px; }}
            .hero .meta-row {{ flex-wrap: wrap; gap: 12px; }}
        }}
    </style>

    <!-- JSON-LD Structured Data (Content) -->
    <script type="application/ld+json">
{jsonld_script}
    </script>

    <!-- JSON-LD Structured Data (Organization) -->
    <script type="application/ld+json">
{org_jsonld}
    </script>
</head>
<body>

    <!-- Navbar -->
    <nav class="site-nav">
        <div class="container">
            <a href="{_safe(brand_url)}">
                {logo_img}
                {_safe(brand_name)}
            </a>
        </div>
    </nav>

    <!-- Hero -->
    <header class="hero">
        <div class="container">
            <span class="category-badge">
                <i class="{cat_meta['icon']}"></i> {cat_meta['label']}
            </span>
            <h1>{_safe(content.title)}</h1>
            <p class="subtitle">{_safe(content.meta_description)}</p>
            <div class="meta-row">
                <span><i class="bi bi-person me-1"></i> {_safe(author_name)}</span>
                <span class="dot"></span>
                <time datetime="{now_iso}"><i class="bi bi-calendar3 me-1"></i> {now_display}</time>
                <span class="dot"></span>
                <span><i class="bi bi-clock me-1"></i> {read_time}</span>
            </div>
        </div>
    </header>

    <!-- Main Content -->
    <main>
        <div class="container">
            <div class="row justify-content-center">

                <!-- Article Body -->
                <div class="col-lg-8">
                    <article class="article-body">
                        {body_html}
                    </article>
                </div>

                <!-- Sidebar -->
                <div class="col-lg-3 offset-lg-1 d-none d-lg-block">
                    <div style="position:sticky;top:32px;padding-top:48px;">

                        {f"""<!-- Brand -->
                        <div class="sidebar-card" style="text-align:center;">
                            <img src="{_safe(logo_url)}" alt="{_safe(brand_name)}" style="height:40px;width:auto;margin-bottom:16px;">
                            <p style="font-size:0.9rem;color:#666;margin-bottom:16px;">{_safe(brand_name)}</p>
                            <a href="{_safe(brand_url)}" target="_blank" rel="noopener"
                               style="display:inline-block;padding:8px 20px;font-size:0.82rem;font-weight:600;
                                      color:{accent};border:1.5px solid {accent};border-radius:6px;
                                      text-decoration:none;">
                                Visit Website <i class="bi bi-arrow-right ms-1"></i>
                            </a>
                        </div>""" if logo_url else ""}

                        <!-- About -->
                        <div class="sidebar-card">
                            <h4>About this {cat_meta['label'].lower()}</h4>
                            <div style="font-size:0.9rem;color:#555;line-height:1.8;">
                                <div style="margin-bottom:12px;">
                                    <i class="bi bi-folder2 me-2" style="color:{accent};"></i>
                                    {cat_meta['label']}
                                </div>
                                <div style="margin-bottom:12px;">
                                    <i class="bi bi-tag me-2" style="color:{accent};"></i>
                                    {_safe(content.topic)}
                                </div>
                                <div>
                                    <i class="bi bi-calendar3 me-2" style="color:{accent};"></i>
                                    {now_display}
                                </div>
                            </div>
                        </div>

                        {"" if not content.tags else f'''
                        <!-- Tags -->
                        <div class="sidebar-card">
                            <h4>Tags</h4>
                            <div>{tag_pills}</div>
                        </div>
                        '''}

                    </div>
                </div>

            </div>
        </div>
    </main>

    <!-- Footer -->
    <footer class="site-footer">
        <div class="container">
            <div class="d-flex flex-column flex-md-row justify-content-between align-items-center">
                <div class="d-flex align-items-center gap-2 mb-2 mb-md-0">
                    {logo_img}
                    <span style="font-weight:500;color:#666;">{_safe(brand_name)}</span>
                </div>
                <div>
                    &copy; {datetime.now().year} {_safe(brand_name)} &middot;
                    <a href="{_safe(brand_url)}">Website</a>
                </div>
            </div>
        </div>
    </footer>

    <!-- Bootstrap 5 JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"
            integrity="sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz" crossorigin="anonymous"></script>
</body>
</html>"""


def build_sitemap(entries: list[dict]) -> str:
    """Generate a sitemap.xml from a list of published content entries."""
    urls = []
    for entry in entries:
        slug = entry.get("slug", "")
        updated = entry.get("updated_at", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        category = entry.get("category", "informational")
        changefreq = "weekly" if category in ("faq", "how-to") else "daily"
        priority = "0.8" if category in ("faq", "how-to") else "0.7"

        urls.append(f"""  <url>
    <loc>{settings.site_url}/{slug}</loc>
    <lastmod>{updated}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>{priority}</priority>
  </url>""")

    urls_xml = "\n".join(urls)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{settings.site_url}/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
{urls_xml}
</urlset>"""


def build_robots_txt() -> str:
    """Generate a robots.txt that allows all AI crawlers."""
    return f"""User-agent: *
Allow: /

# AI Crawlers - explicitly allowed
User-agent: GPTBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: Bytespider
Allow: /

User-agent: CCBot
Allow: /

Sitemap: {settings.site_url}/sitemap.xml
"""
