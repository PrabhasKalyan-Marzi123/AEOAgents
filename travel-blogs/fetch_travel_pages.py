"""Fetch all live Marzi Travel Blog pages from Firebase into firebase-hosting/public/.

Run before the pipeline so discover_existing_pages() has real content to index.
Pages are ephemeral — never committed to git.
"""

import re
import sys
from pathlib import Path

import httpx

SITEMAP_URL = "https://marzitravelblogs.web.app/sitemap.xml"
OUTPUT_DIR = Path(__file__).resolve().parent / "firebase-hosting" / "public"


def fetch_pages() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        resp = httpx.get(SITEMAP_URL, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"[fetch_travel_pages] Failed to fetch sitemap: {e}", file=sys.stderr)
        return 1

    urls = re.findall(r"<loc>(.*?)</loc>", resp.text)
    if not urls:
        print("[fetch_travel_pages] No URLs found in sitemap — site may be empty.", file=sys.stderr)
        return 0

    print(f"[fetch_travel_pages] {len(urls)} URLs in sitemap")
    failed = 0

    for url in urls:
        path_part = url.rstrip("/").rsplit("/", 1)[-1]
        # Skip the homepage URL (slug would just be the domain name)
        if not path_part or "." in path_part.split("-")[0]:
            continue
        slug = path_part
        out_path = OUTPUT_DIR / f"{slug}.html"
        try:
            page = httpx.get(url, timeout=30, follow_redirects=True)
            page.raise_for_status()
            out_path.write_text(page.text, encoding="utf-8")
            print(f"  ✓ {slug}")
        except Exception as e:
            print(f"  ✗ {url}: {e}", file=sys.stderr)
            failed += 1

    print(f"[fetch_travel_pages] Done — {len(urls) - failed}/{len(urls)} pages fetched to {OUTPUT_DIR}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(fetch_pages())
