"""Agent: The Editor.

Updates an already-published blog in place using user feedback.

Flow:
  1. Locate the live HTML file by slug under firebase-hosting/public/
  2. Parse title, meta description, body HTML, JSON-LD @type, and any existing
     specific_data from the embedded JSON-LD
  3. Send the original content + user comments to Gemini and receive a revised
     {title, html, meta_description, tags, jsonld_specific_data}
  4. Build a WrittenContent and re-run the Compiler to overwrite the file
  5. Re-upsert the page into the ChromaDB vector store so similarity dedup
     continues to reflect the latest content

The Distributor (index/sitemap/llms.txt refresh) is the caller's responsibility
— it runs once per CLI invocation rather than per-page.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path

from bs4 import BeautifulSoup
from google import genai

from app.config import settings
from app.schemas.content import ContentCategory
from app.agents.compiler import CompilerAgent, CompiledPage, DEFAULT_OUTPUT_DIR
from app.agents.writer import WrittenContent
from app.agents.researcher import _parse_json_lenient
from app.services.brand_context import get_brand_context
from app.services import vector_store

logger = logging.getLogger(__name__)

_SCHEMA_TO_CATEGORY = {
    "FAQPage": ContentCategory.FAQ,
    "HowTo": ContentCategory.HOW_TO,
    "Article": ContentCategory.COMPARISON,
    "BlogPosting": ContentCategory.INFORMATIONAL,
}

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_DESC_RE = re.compile(
    r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_KEYWORDS_RE = re.compile(
    r'<meta\s+name=["\']keywords["\']\s+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class ExistingPage:
    slug: str
    file_path: Path
    title: str
    meta_description: str
    body_html: str
    category: ContentCategory
    tags: list[str]
    jsonld: dict
    topic: str


class BlogNotFoundError(Exception):
    pass


class EditorAgent:
    """Agent that revises an already-published page based on user comments."""

    def __init__(self, output_dir: str | Path | None = None):
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        self.compiler = CompilerAgent(output_dir=self.output_dir)

    # ── Discovery ──

    def list_blogs(self) -> list[dict]:
        """Enumerate every published blog (slug, title) for ID-style selection."""
        out: list[dict] = []
        if not self.output_dir.exists():
            return out
        for path in sorted(self.output_dir.glob("*.html")):
            if path.name == "index.html":
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            title = ""
            m = _TITLE_RE.search(text)
            if m:
                title = unescape(m.group(1)).strip()
                suffix = f" | {settings.site_name}"
                if title.endswith(suffix):
                    title = title[: -len(suffix)].rstrip()
            out.append({"slug": path.stem, "title": title or path.stem})
        return out

    def _resolve_slug(self, slug_or_id: str) -> Path:
        """Accept an exact slug, a 1-based numeric ID from list_blogs(), or a substring."""
        path = self.output_dir / f"{slug_or_id}.html"
        if path.exists():
            return path
        blogs = self.list_blogs()
        if slug_or_id.isdigit():
            idx = int(slug_or_id) - 1
            if 0 <= idx < len(blogs):
                return self.output_dir / f"{blogs[idx]['slug']}.html"
        # Fuzzy: unique substring match in slug
        matches = [b for b in blogs if slug_or_id.lower() in b["slug"].lower()]
        if len(matches) == 1:
            return self.output_dir / f"{matches[0]['slug']}.html"
        if len(matches) > 1:
            raise BlogNotFoundError(
                f"Ambiguous match for {slug_or_id!r}: "
                + ", ".join(m["slug"] for m in matches[:5])
            )
        raise BlogNotFoundError(f"No blog found for {slug_or_id!r}")

    # ── Parsing ──

    def _load_existing(self, html_path: Path) -> ExistingPage:
        text = html_path.read_text(encoding="utf-8", errors="replace")
        slug = html_path.stem

        # Title
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

        # Tags from keywords meta
        tags: list[str] = []
        m = _KEYWORDS_RE.search(text)
        if m:
            raw = unescape(m.group(1))
            tags = [t.strip() for t in raw.split(",") if t.strip()]

        # JSON-LD — first script is the content schema (Compiler emits it first)
        jsonld: dict = {}
        category = ContentCategory.INFORMATIONAL
        m = _JSONLD_RE.search(text)
        if m:
            try:
                jsonld = json.loads(m.group(1).strip())
                schema_type = jsonld.get("@type") if isinstance(jsonld, dict) else None
                if isinstance(schema_type, str):
                    category = _SCHEMA_TO_CATEGORY.get(schema_type, ContentCategory.INFORMATIONAL)
            except json.JSONDecodeError:
                jsonld = {}

        # Article body — html_builder wraps content in <article class="article-body">
        soup = BeautifulSoup(text, "html.parser")
        article = soup.find("article", class_="article-body")
        body_html = "".join(str(c) for c in article.contents).strip() if article else ""

        # Topic best-guess: first tag, falling back to title
        topic = tags[0] if tags else title

        return ExistingPage(
            slug=slug,
            file_path=html_path,
            title=title,
            meta_description=meta_description,
            body_html=body_html,
            category=category,
            tags=tags,
            jsonld=jsonld,
            topic=topic,
        )

    # ── LLM revision ──

    def _build_prompt(self, page: ExistingPage, comments: str, brand: dict | None) -> str:
        existing_specific_data = self._derive_specific_data(page.jsonld)
        brand_block = ""
        if brand:
            brand_block = (
                "BRAND FACTS (use these exactly — never invent):\n"
                + json.dumps(
                    {
                        k: brand.get(k)
                        for k in [
                            "brand_name",
                            "what_it_is",
                            "target_audience",
                            "cities",
                            "event_themes",
                            "pricing_model",
                            "events_per_month",
                            "event_group_size",
                            "key_differentiators",
                        ]
                        if brand.get(k) is not None
                    },
                    indent=2,
                )
                + "\n"
            )

        return f"""You are an AEO content editor. Revise an existing blog post based on user feedback.

{brand_block}
EXISTING POST:
- slug: {page.slug}
- category: {page.category.value}
- title: {page.title}
- meta_description: {page.meta_description}
- tags: {json.dumps(page.tags)}
- existing_jsonld_specific_data: {json.dumps(existing_specific_data)[:1200]}

EXISTING BODY HTML:
{page.body_html[:8000]}

USER COMMENTS / EDIT REQUEST:
\"\"\"
{comments}
\"\"\"

REVISION RULES:
1. Apply the user's feedback faithfully. Preserve everything they did NOT ask to change.
2. Keep the same content category ({page.category.value}) and JSON-LD schema. Do NOT change the slug.
3. Keep the existing Bootstrap 5 / semantic HTML structure. No <html>/<head>/<body>. No <h1>.
4. Maintain AEO snippet style: every section opens with a direct-answer sentence.
5. Use ONLY real brand facts above — never invent features, prices, or claims.
6. If the user asked for new sections/items, integrate them naturally with the existing flow.
7. Update meta_description and tags ONLY if the change of body warrants it.

Return ONLY valid JSON:
{{
  "title": "revised SEO title (60-70 chars)",
  "html": "<div>... revised body ...</div>",
  "meta_description": "revised meta description (150-160 chars)",
  "tags": ["tag1", "tag2"],
  "jsonld_specific_data": {{
    "mentions": [...],
    "features": [...],
    "pricing": {{}},
    "ratings": {{}},
    "key_facts": [...]
  }},
  "change_summary": "one sentence describing what was changed"
}}
"""

    @staticmethod
    def _derive_specific_data(jsonld: dict) -> dict:
        """Best-effort recovery of jsonld_specific_data from a previously-rendered schema."""
        if not isinstance(jsonld, dict):
            return {}
        out: dict = {}
        about = jsonld.get("about")
        if isinstance(about, list):
            mentions = [a.get("name") for a in about if isinstance(a, dict) and a.get("name")]
            if mentions:
                out["mentions"] = mentions
        if jsonld.get("keywords"):
            out["features"] = [k.strip() for k in str(jsonld["keywords"]).split(",") if k.strip()]
        if jsonld.get("articleBody"):
            facts = [s.strip() for s in str(jsonld["articleBody"]).split(".") if s.strip()]
            if facts:
                out["key_facts"] = facts
        return out

    def _call_gemini(self, prompt: str) -> dict:
        if not settings.gemini_api_key:
            raise RuntimeError("[Editor] GEMINI_API_KEY not configured")
        client = genai.Client(api_key=settings.gemini_api_key)
        last_err: Exception | None = None
        for attempt in (1, 2):
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    temperature=0.4,
                    max_output_tokens=12000,
                    response_mime_type="application/json",
                ),
            )
            raw = (response.text or "").strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            try:
                return json.loads(raw)
            except json.JSONDecodeError as e:
                last_err = e
                logger.warning(f"[Editor] Attempt {attempt} JSON parse failed ({e})")
                lenient = _parse_json_lenient(raw)
                if lenient:
                    return lenient
        raise RuntimeError(f"[Editor] Gemini returned invalid JSON twice: {last_err}")

    # ── Public entry point ──

    def run(
        self,
        slug_or_id: str,
        comments: str,
        brand_url: str = "https://marzi.life",
    ) -> tuple[CompiledPage, str]:
        """Revise the page identified by `slug_or_id` using `comments`.

        Returns (CompiledPage, change_summary).
        """
        if not comments or not comments.strip():
            raise ValueError("comments must be a non-empty string")

        html_path = self._resolve_slug(slug_or_id)
        page = self._load_existing(html_path)
        logger.info(
            f"[Editor] Loaded slug='{page.slug}', category={page.category.value}, "
            f"body={len(page.body_html)} chars"
        )

        brand = get_brand_context(brand_url) or {}
        prompt = self._build_prompt(page, comments, brand)
        revised = self._call_gemini(prompt)

        # Build a WrittenContent so the existing Compiler renders the page.
        new_tags = revised.get("tags") or page.tags
        if not isinstance(new_tags, list):
            new_tags = page.tags
        written = WrittenContent(
            title=(revised.get("title") or page.title).strip(),
            slug=page.slug,
            category=page.category,
            content_html=revised.get("html") or page.body_html,
            meta_description=(revised.get("meta_description") or page.meta_description).strip(),
            tags=[str(t).strip() for t in new_tags if str(t).strip()],
            jsonld_data=revised.get("jsonld_specific_data") or {},
            topic=page.topic,
            brand_url=brand_url,
            brand_data=brand or {},
        )

        compiled = self.compiler.run(written)
        logger.info(f"[Editor] Rewrote {compiled.file_path}")

        # Refresh embeddings so the recommender's dedup reflects the new content.
        from app.services.recommender import _extract_body_text  # local import to avoid cycle

        body = _extract_body_text(compiled.full_html)
        embed_source = f"{written.title}\n{written.meta_description}\n{body}"
        result = vector_store.upsert_page(
            slug=page.slug,
            title=written.title,
            category=page.category.value,
            embed_source=embed_source,
        )
        logger.info(f"[Editor] Vector store: {result['action']} ({result['n_chunks']} chunks)")

        change_summary = (revised.get("change_summary") or "").strip() or "Content updated."
        return compiled, change_summary
