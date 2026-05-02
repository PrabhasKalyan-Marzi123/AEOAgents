"""Run the 5-Agent AEO Pipeline for marzi.life.

Usage:
    python run_pipeline.py                    # Generate all 4 categories + deploy
    python run_pipeline.py --no-deploy        # Generate only, skip firebase deploy
    python run_pipeline.py --topic "custom topic here"  # Single custom topic
"""

import asyncio
import argparse
import logging
import sys
import os

# Ensure backend package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agents.pipeline import run_pipeline, PipelineConfig, TopicConfig, MARZI_TOPICS


def main():
    parser = argparse.ArgumentParser(description="AEO 5-Agent Pipeline for marzi.life")
    parser.add_argument("--no-deploy", action="store_true", help="Skip firebase deploy")
    parser.add_argument("--topic", type=str, help="Generate for a single custom topic")
    parser.add_argument("--brand-url", type=str, default="https://marzi.life", help="Brand URL")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Build config
    if args.topic:
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

    # Run
    result = asyncio.run(run_pipeline(config))

    # Summary
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
