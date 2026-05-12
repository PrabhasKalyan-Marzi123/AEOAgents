"""Run the Marzi Holidays Travel Pipeline.

Pass destinations manually — there is no recommender for the travel pipeline.

Usage:
    python run_travel_pipeline.py --destination "Kerala backwaters trip for Indian travellers above 55"
    python run_travel_pipeline.py --destination "..." --no-deploy
    python run_travel_pipeline.py                                    # uses DEFAULT_DESTINATIONS

The pipeline:
  TravelResearcher (Gemini grounded GoogleSearch) → Strategist → Writer → Compiler → TravelDistributor

Output lands in travel-blogs/firebase-hosting/public/ and deploys to the
MarziTravelBlogs Firebase site.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path


_TRAVEL_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _TRAVEL_ROOT.parent
_BACKEND_ROOT = _PROJECT_ROOT / "backend"

# Load backend/.env so GEMINI_API_KEY etc. are available regardless of cwd.
# pydantic-settings reads `.env` relative to cwd; the travel CLI lets users
# run from anywhere, so we make the resolution explicit.
try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND_ROOT / ".env")
except ImportError:
    pass

# Backend's `app` package + travel's own `marzi_travel` package are both importable.
# Distinct names so there is no collision.
sys.path.insert(0, str(_BACKEND_ROOT))
sys.path.insert(0, str(_TRAVEL_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Marzi Holidays Travel Pipeline (worry-research → blog)"
    )
    parser.add_argument(
        "--destination",
        type=str,
        action="append",
        help='Destination/topic to generate a blog for (repeatable). E.g. --destination "Kerala backwaters for Indian travellers above 55"',
    )
    parser.add_argument(
        "--no-deploy",
        action="store_true",
        help="Skip firebase deploy (write files locally only)",
    )
    parser.add_argument(
        "--list-blogs",
        action="store_true",
        help="Print every published travel blog (slug, title) and exit",
    )
    parser.add_argument(
        "--update",
        type=str,
        metavar="ID_OR_SLUG",
        help="Revise an existing travel blog by ID or slug (use --list-blogs to find an ID)",
    )
    parser.add_argument(
        "--comments",
        type=str,
        default="",
        help='Editorial feedback for --update ("make it shorter, add a section on monsoon")',
    )
    parser.add_argument(
        "--brand-url",
        type=str,
        default=None,
        help="Override brand URL (default: holidays.marzi.life)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose (DEBUG) logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Import after sys.path is set up so `app.*` resolves correctly.
    from marzi_travel import site_config

    site_config.apply_to_settings()
    brand_url = args.brand_url or site_config.BRAND_URL

    # ── --list-blogs ──
    if args.list_blogs:
        from app.agents.editor import EditorAgent
        editor = EditorAgent(output_dir=site_config.OUTPUT_DIR)
        blogs = editor.list_blogs()
        if not blogs:
            print("No travel blogs published yet.")
            return 0
        print(f"\n{'ID':<4} {'Slug':<70} Title")
        print(f"{'-'*4} {'-'*70} {'-'*40}")
        for i, b in enumerate(blogs, 1):
            slug = b["slug"] if len(b["slug"]) <= 70 else b["slug"][:67] + "..."
            title = b["title"] if len(b["title"]) <= 60 else b["title"][:57] + "..."
            print(f"{i:<4} {slug:<70} {title}")
        print(
            f"\n{len(blogs)} travel blog(s). "
            f'Update with: --update <ID> --comments "..."\n'
        )
        return 0

    # ── --update ──
    if args.update:
        if not args.comments.strip():
            print('--update requires --comments "..." describing what to change.')
            return 1
        from app.agents.editor import EditorAgent, BlogNotFoundError
        from marzi_travel.distributor import TravelDistributorAgent

        editor = EditorAgent(output_dir=site_config.OUTPUT_DIR)
        try:
            print(f"\n{'='*60}\nEditor: revising {args.update!r}\n"
                  f"Comments: {args.comments}\n{'='*60}")
            compiled, change_summary = editor.run(
                args.update, args.comments, brand_url=brand_url
            )
        except BlogNotFoundError as e:
            print(f"Error: {e}")
            return 1

        print(f"\n[Editor] Change summary: {change_summary}")
        print(f"[Editor] File rewritten: {compiled.file_path}")
        print(f"[Editor] New title: {compiled.title}")

        distributor = TravelDistributorAgent(output_dir=site_config.OUTPUT_DIR)
        deployment = distributor.run([compiled], deploy=not args.no_deploy)
        if deployment.deployed:
            print(f"[Editor] Deployed. Live URL ends with /{compiled.slug}")
        elif args.no_deploy:
            print("[Editor] Skipped Firebase deploy (--no-deploy).")
        else:
            print(
                f"[Editor] Deploy did not succeed. "
                f"Output: {deployment.deploy_output[:300]}"
            )
        return 0

    # ── Generate ──
    destinations = args.destination or list(site_config.DEFAULT_DESTINATIONS)
    if not destinations:
        print("No destinations to process. Pass --destination \"...\" or set DEFAULT_DESTINATIONS.")
        return 1

    from marzi_travel.pipeline import run_travel_pipeline, TravelPipelineConfig

    config = TravelPipelineConfig(
        destinations=destinations,
        brand_url=brand_url,
        deploy=not args.no_deploy,
    )

    print(f"\n{'='*60}")
    print("Marzi Holidays Travel Pipeline")
    print(f"Brand: {config.brand_url}")
    print(f"Site:  {site_config.SITE_URL}")
    print(f"Output: {site_config.OUTPUT_DIR}")
    print(f"Destinations: {len(config.destinations)}")
    for i, d in enumerate(config.destinations, 1):
        print(f"  {i}. {d}")
    print(f"Deploy: {config.deploy}")
    print(f"{'='*60}\n")

    result = asyncio.run(run_travel_pipeline(config))

    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    print(f"Pages compiled: {len(result.pages)}")
    for page in result.pages:
        print(f"  • {page.title}")
        print(f"    → {page.file_path}")

    if result.deployment:
        status = "SUCCESS" if result.deployment.deployed else "SKIPPED/FAILED"
        print(f"\nDeployment: {status}")
        if result.deployment.live_urls:
            print("Live URLs:")
            for url in result.deployment.live_urls:
                print(f"  → {url}")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  ✗ {err}")
    print(f"{'='*60}\n")
    return 0 if not result.errors else 1


if __name__ == "__main__":
    sys.exit(main())
