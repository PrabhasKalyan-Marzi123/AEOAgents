"""Hero-image generation for travel blogs via Gemini 2.5 Flash Image.

Model: gemini-2.5-flash-image ("Nano Banana") — the cheapest current Gemini
image model (~$0.03/image at the time of writing).

One image per blog, saved to firebase-hosting/public/images/{slug}.png and
referenced from the article HTML.  Failures are non-fatal: the pipeline
continues without the image rather than aborting the run.
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

from google import genai
from google.genai import types as genai_types
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

IMAGE_MODEL = "gemini-2.5-flash-image"

# Web-delivery sizing. Gemini returns ~1.5MB PNGs at native resolution; we
# scale to a hero-friendly width and re-encode as WebP. Typical output is
# 80–150 KB — roughly 10× smaller than the source PNG.
MAX_WIDTH = 1200
WEBP_QUALITY = 78

# Topic → visual cue heuristic. Stays simple — the destination string itself
# carries most of the prompt's signal; this just nudges the model toward
# the right scene type when the title is generic.
_TOPIC_CUES = [
    ("forex", "Indian senior couple at an overseas ATM or holding a forex card and passport, soft daylight; tasteful close-up of cards and currency on a hotel desk"),
    ("medicine", "Indian senior couple organising a transparent medicine pouch with strips of pills and a prescription letter on a hotel bed before a flight"),
    ("flight", "Indian senior couple seated comfortably in a premium-economy or business-class window seat on a wide-body aircraft, warm cabin lighting"),
    ("seat", "Indian senior couple seated comfortably in a premium-economy or business-class window seat on a wide-body aircraft, warm cabin lighting"),
    ("airport", "Indian senior couple walking through a modern international airport terminal with carry-on luggage, calm expression, signage in soft focus"),
    ("hotel", "Indian senior couple checking into an elegant senior-friendly boutique hotel lobby abroad, polished decor, smiling concierge"),
    ("europe", "Indian senior couple walking on a cobbled European street (Lucerne / Paris / Rome) with a backdrop of historic architecture, golden hour"),
    ("itinerary", "Indian senior couple reviewing a printed travel itinerary on a hotel terrace overlooking an iconic international landmark, coffee on the table"),
    ("pace", "Indian senior couple seated leisurely at a continental café in Europe, espresso cups and a map on the table, relaxed body language"),
    ("energy", "Indian senior couple resting on a park bench abroad with a small water bottle, smiling, no fatigue, natural lighting"),
    ("first time", "Indian senior couple with fresh passports and a camera, standing in front of a famous international landmark for the first time, look of quiet wonder"),
    ("kerala", "Mature Indian senior couple on a Kerala houseboat deck at sunrise, calm backwaters, warm tropical light"),
    ("golden triangle", "Mature Indian senior couple in front of the Taj Mahal at golden hour, dignified attire, soft warm light"),
    ("kashi", "Mature Indian senior couple at a Varanasi ghat at sunrise, soft mist, lit diyas on the river"),
    ("varanasi", "Mature Indian senior couple at a Varanasi ghat at sunrise, soft mist, lit diyas on the river"),
    ("independent", "Confident Indian senior couple walking unaided through a modern international airport or city street, no children visible, sense of self-reliance"),
    ("without depending", "Confident Indian senior couple walking unaided through a modern international airport or city street, no children visible, sense of self-reliance"),
]


def _scene_for(topic: str, title: str) -> str:
    haystack = f"{topic} {title}".lower()
    for needle, scene in _TOPIC_CUES:
        if needle in haystack:
            return scene
    return (
        "Mobile, active Indian senior couple (aged 55–65, dignified, well-dressed) "
        f"in a scene that visually represents '{topic}', premium travel context"
    )


def _build_image_prompt(topic: str, title: str) -> str:
    scene = _scene_for(topic, title)
    return (
        "Editorial photograph for a premium senior-travel magazine.\n"
        f"Subject & scene: {scene}.\n"
        "Mood: warm, confident, dignified, hopeful, premium. NOT clinical, NOT medical, NOT melancholic.\n"
        "Photography: high-end travel-magazine style, shallow depth of field, natural light, "
        "golden-hour palette where outdoors, soft warm lighting where indoors.\n"
        "Composition: wide horizontal frame (16:9 aspect ratio), main subject occupying the rule-of-thirds, "
        "ample environmental context, no centred portrait crops.\n"
        "Avoid: wheelchairs (unless the topic explicitly mentions mobility), medical equipment, group-tour "
        "matching uniforms, stereotypical 'sad elderly' framing, tourist clichés.\n"
        "Strict rules: NO text, NO logos, NO words, NO captions, NO watermarks anywhere in the image. "
        "Image is purely visual.\n"
        f"Blog topic for context (do not render as text): {title}"
    )


def generate_hero_image(
    *,
    slug: str,
    title: str,
    topic: str,
    images_dir: Path,
) -> Path | None:
    """Generate one hero image and write it to {images_dir}/{slug}.png.

    Returns the written path on success, None on any failure (non-fatal).
    """
    if not settings.gemini_api_key:
        logger.warning("[ImageGen] No GEMINI_API_KEY — skipping image generation")
        return None

    prompt = _build_image_prompt(topic, title)
    client = genai.Client(api_key=settings.gemini_api_key)

    try:
        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )
    except Exception as e:
        logger.error(f"[ImageGen] API call failed for slug={slug!r}: {e}")
        return None

    candidates = getattr(response, "candidates", None) or []
    for cand in candidates:
        parts = getattr(getattr(cand, "content", None), "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline else None
            if data:
                images_dir.mkdir(parents=True, exist_ok=True)
                out_path = images_dir / f"{slug}.webp"
                try:
                    img = Image.open(io.BytesIO(data)).convert("RGB")
                    if img.width > MAX_WIDTH:
                        new_h = round(img.height * (MAX_WIDTH / img.width))
                        img = img.resize((MAX_WIDTH, new_h), Image.LANCZOS)
                    img.save(out_path, format="WEBP", quality=WEBP_QUALITY, method=6)
                    logger.info(
                        f"[ImageGen] Wrote {out_path.name} "
                        f"({out_path.stat().st_size // 1024} KB, {img.width}×{img.height}) "
                        f"from {len(data) // 1024} KB source"
                    )
                except Exception as e:
                    # Fall back to raw bytes if Pillow choked (very unlikely)
                    logger.warning(f"[ImageGen] WebP compression failed ({e}); writing raw PNG")
                    out_path = images_dir / f"{slug}.png"
                    out_path.write_bytes(data)
                return out_path

    logger.warning(f"[ImageGen] No image returned for slug={slug!r}; response had no inline_data parts")
    return None


def inject_hero_image_into_html(
    html_path: Path | str,
    *,
    image_url: str,
    alt: str,
) -> bool:
    """Insert a <figure> with the hero image immediately after </header>.

    Returns True on success, False if the marker wasn't found.
    Idempotent: skips insertion if the image URL is already present.
    """
    html_path = Path(html_path)
    text = html_path.read_text(encoding="utf-8")
    if image_url in text:
        return True

    safe_alt = (alt or "").replace('"', "&quot;")
    figure = (
        '\n    <figure class="hero-figure" style="margin:1rem auto 2rem;max-width:480px;'
        'padding:0 1rem;">\n'
        f'      <img src="{image_url}" alt="{safe_alt}" '
        'style="width:100%;height:auto;border-radius:12px;display:block;'
        'box-shadow:0 4px 16px rgba(0,0,0,0.08);" loading="eager" '
        'fetchpriority="high" />\n'
        '    </figure>\n'
    )
    new_text, n = re.subn(r"(</header>)", r"\1" + figure, text, count=1)
    if n == 0:
        logger.warning(f"[ImageGen] No </header> found in {html_path.name}; image not injected")
        return False

    # Also patch og:image so social shares pick up the hero image instead of the logo.
    og_re = re.compile(r'<meta property="og:image" content="[^"]*">')
    if og_re.search(new_text):
        new_text = og_re.sub(
            f'<meta property="og:image" content="{image_url}">', new_text, count=1
        )
    else:
        new_text = new_text.replace(
            '<!-- Favicon -->',
            f'<meta property="og:image" content="{image_url}">\n    <!-- Favicon -->',
            1,
        )

    html_path.write_text(new_text, encoding="utf-8")
    return True
