"""Run the 5-Agent AEO Pipeline for marzi.life.

Usage:
    python run_pipeline.py                                    # Generate all 4 default topics + deploy
    python run_pipeline.py --no-deploy                        # Generate only, skip firebase deploy
    python run_pipeline.py --topic "custom topic"             # Single custom topic
    python run_pipeline.py --recommend 5                      # Print 5 topic recommendations, exit
    python run_pipeline.py --auto 3                           # Recommend 3 topics, then run pipeline on them
    python run_pipeline.py --list-blogs                       # Print every published blog with an ID
    python run_pipeline.py --update <id-or-slug> \\
        --comments "make it shorter, add a section on cost"   # Revise an existing blog
"""

import asyncio
import argparse
import logging
import sys
import os

# Ensure backend package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agents.pipeline import run_pipeline, PipelineConfig, TopicConfig, MARZI_TOPICS


def _print_recommendations(recs):
    """Format recommendations as a table for terminal output."""
    if not recs:
        print("\n(No recommendations returned — check logs above)")
        return
    print(f"\n{'#':<3} {'Score':<6} {'Category':<14} Topic")
    print(f"{'-'*3} {'-'*6} {'-'*14} {'-'*60}")
    for i, r in enumerate(recs, 1):
        topic_short = r.topic if len(r.topic) <= 60 else r.topic[:57] + "..."
        print(f"{i:<3} {r.priority_score:<6.2f} {r.target_category:<14} {topic_short}")
    print()
    for i, r in enumerate(recs, 1):
        print(f"  {i}. {r.topic}")
        print(f"     Why: {r.rationale}")
        print(f"     Themes: {', '.join(r.themes_addressed) if r.themes_addressed else '(none)'}")
        print(f"     Max similarity to existing: {r.max_similarity_to_existing}")
        print()


def main():
    parser = argparse.ArgumentParser(description="AEO 5-Agent Pipeline for marzi.life")
    parser.add_argument("--no-deploy", action="store_true", help="Skip firebase deploy")
    parser.add_argument("--topic", type=str, help="Generate for a single custom topic")
    parser.add_argument("--recommend", type=int, metavar="N", help="Print N topic recommendations and exit")
    parser.add_argument("--auto", type=int, metavar="N", help="Recommend N topics, then run the pipeline on them")
    parser.add_argument("--threshold", type=float, default=0.78, help="Cosine similarity threshold for dedup (default 0.78)")
    parser.add_argument("--list-blogs", action="store_true", help="Print every published blog with an ID and exit")
    parser.add_argument("--update", type=str, metavar="ID_OR_SLUG", help="Revise an existing blog (use --list-blogs to find an ID)")
    parser.add_argument("--comments", type=str, default="", help="Editorial feedback for --update (the agent will apply these changes)")
    parser.add_argument("--brand-url", type=str, default="https://marzi.life", help="Brand URL")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── List existing blogs ──
    if args.list_blogs:
        from app.agents.editor import EditorAgent
        blogs = EditorAgent().list_blogs()
        if not blogs:
            print("No published blogs found.")
            return 0
        print(f"\n{'ID':<4} {'Slug':<70} Title")
        print(f"{'-'*4} {'-'*70} {'-'*40}")
        for i, b in enumerate(blogs, 1):
            slug = b['slug'] if len(b['slug']) <= 70 else b['slug'][:67] + "..."
            title = b['title'] if len(b['title']) <= 60 else b['title'][:57] + "..."
            print(f"{i:<4} {slug:<70} {title}")
        print(f"\n{len(blogs)} blog(s). Update one with: --update <ID> --comments \"...\"\n")
        return 0

    # ── Update an existing blog ──
    if args.update:
        if not args.comments.strip():
            print("--update requires --comments \"...\" describing what to change.")
            return 1

        from app.agents.editor import EditorAgent, BlogNotFoundError
        from app.agents.distributor import DistributorAgent

        editor = EditorAgent()
        try:
            print(f"\n{'='*60}\nEditor: revising {args.update!r}\nComments: {args.comments}\n{'='*60}")
            compiled, change_summary = editor.run(args.update, args.comments, brand_url=args.brand_url)
        except BlogNotFoundError as e:
            print(f"Error: {e}")
            return 1

        print(f"\n[Editor] Change summary: {change_summary}")
        print(f"[Editor] File rewritten: {compiled.file_path}")
        print(f"[Editor] New title: {compiled.title}")

        # Refresh sitemap/index/llms.txt and (optionally) deploy.
        distributor = DistributorAgent()
        deployment = distributor.run([compiled], deploy=not args.no_deploy)
        if deployment.deployed:
            print(f"[Editor] Deployed. Live URL ends with /{compiled.slug}")
        elif args.no_deploy:
            print(f"[Editor] Skipped Firebase deploy (--no-deploy).")
        else:
            print(f"[Editor] Deploy did not succeed. Output: {deployment.deploy_output[:300]}")
        return 0

    # ── Recommendation modes (recommender imported lazily — model load is heavy) ──
    if args.recommend or args.auto:
        from app.services.recommender import recommend_topics

        n = args.recommend if args.recommend else args.auto
        print(f"\n{'='*60}\nTopic Recommender (n={n}, threshold={args.threshold})\nBrand: {args.brand_url}\n{'='*60}")
        recs = recommend_topics(brand_url=args.brand_url, n=n, similarity_threshold=args.threshold)

        _print_recommendations(recs)

        if args.recommend:
            print(f"{'='*60}\nDone. Re-run with --auto {n} to feed these into the pipeline.\n{'='*60}")
            return 0

        if not recs:
            print("No survivors after dedup — nothing to feed to the pipeline.")
            return 1

        topics = [TopicConfig(topic=r.topic) for r in recs]

    elif args.topic:
        topics = [TopicConfig(topic=args.topic)]
    else:
        topics = MARZI_TOPICS

    config = PipelineConfig(
        topics=topics,
        brand_url=args.brand_url,
        deploy=not args.no_deploy,
    )

    print(f"\n{'='*60}")
    print(f"AEO 5-Agent Pipeline")
    print(f"Brand: {config.brand_url}")
    print(f"Topics: {len(config.topics)}")
    print(f"Deploy: {config.deploy}")
    print(f"{'='*60}\n")

    result = asyncio.run(run_pipeline(config))

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"Pages compiled: {len(result.pages)}")
    for page in result.pages:
        print(f"  • {page.title}")
        print(f"    → {page.file_path}")

    if result.deployment:
        print(f"\nDeployment: {'SUCCESS' if result.deployment.deployed else 'SKIPPED/FAILED'}")
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
