"""Unified AEO Pipeline — 5-Agent Task Force.

Entry point that chains:
  Agent 1 (Researcher) → Agent 2 (Strategist) → Agent 3 (Writer) →
  Agent 4 (Compiler) → Agent 5 (Distributor)

Usage:
    from app.agents.pipeline import run_pipeline, PipelineConfig

    result = await run_pipeline(PipelineConfig(
        topics=["offline social events for 55+ in Bangalore and Mumbai"],
        brand_url="https://marzi.life",
    ))
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.schemas.content import ContentCategory
from app.agents.researcher import ResearcherAgent, ResearchDossier
from app.agents.strategist import StrategistAgent, ContentBlueprint
from app.agents.writer import WriterAgent, WrittenContent
from app.agents.compiler import CompilerAgent, CompiledPage
from app.agents.distributor import DistributorAgent, DeploymentResult

logger = logging.getLogger(__name__)


@dataclass
class TopicConfig:
    """Configuration for a single content piece."""
    topic: str
    category: ContentCategory | None = None  # None = auto-detect


@dataclass
class PipelineConfig:
    """Configuration for the full pipeline run."""

    # Content to generate
    topics: list[TopicConfig] = field(default_factory=list)
    brand_url: str = "https://marzi.life"

    # Output control
    output_dir: str | Path | None = None   # None = default firebase-hosting/public/
    deploy: bool = True                     # Whether to run firebase deploy

    # Convenience: pass raw topic strings (auto-creates TopicConfig with no category override)
    raw_topics: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Convert raw_topics into TopicConfig objects
        for t in self.raw_topics:
            self.topics.append(TopicConfig(topic=t))


@dataclass
class PipelineResult:
    """Result of a full pipeline run."""

    pages: list[CompiledPage] = field(default_factory=list)
    deployment: DeploymentResult | None = None
    errors: list[str] = field(default_factory=list)


async def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Execute the full 5-agent pipeline.

    Flow:
        For each topic:
            1. Researcher  → ResearchDossier
            2. Strategist  → ContentBlueprint
            3. Writer      → WrittenContent
            4. Compiler    → CompiledPage (HTML file written)
        Then once:
            5. Distributor → index + sitemap + robots + firebase deploy

    Args:
        config: Pipeline configuration

    Returns:
        PipelineResult with all compiled pages and deployment status
    """
    result = PipelineResult()

    if not config.topics:
        result.errors.append("No topics provided")
        return result

    # Initialize agents
    researcher = ResearcherAgent()
    strategist = StrategistAgent()
    writer = WriterAgent()
    compiler = CompilerAgent(output_dir=config.output_dir)
    distributor = DistributorAgent(output_dir=config.output_dir)

    logger.info(f"{'='*60}")
    logger.info(f"AEO Pipeline: {len(config.topics)} topics, brand={config.brand_url}")
    logger.info(f"{'='*60}")

    for i, topic_cfg in enumerate(config.topics, 1):
        topic = topic_cfg.topic
        logger.info(f"\n--- Topic {i}/{len(config.topics)}: {topic} ---")

        try:
            # Agent 1: Research
            logger.info(f"[Pipeline] Agent 1: Researching...")
            dossier = await researcher.run(topic=topic, brand_url=config.brand_url)

            # Agent 2: Strategize
            logger.info(f"[Pipeline] Agent 2: Strategizing...")
            blueprint = strategist.run(dossier, category_override=topic_cfg.category)

            # Agent 3: Write
            logger.info(f"[Pipeline] Agent 3: Writing...")
            written = await writer.run(blueprint)

            # Agent 4: Compile
            logger.info(f"[Pipeline] Agent 4: Compiling...")
            compiled = compiler.run(written)

            result.pages.append(compiled)
            logger.info(f"[Pipeline] ✓ {compiled.title} → {compiled.file_path}")

        except Exception as e:
            error_msg = f"Failed on topic '{topic}': {e}"
            logger.error(f"[Pipeline] ✗ {error_msg}")
            result.errors.append(error_msg)
            import traceback
            traceback.print_exc()

    # Agent 5: Distribute (runs once for all pages)
    if result.pages:
        logger.info(f"\n--- Agent 5: Distributing {len(result.pages)} pages ---")
        try:
            deployment = distributor.run(result.pages, deploy=config.deploy)
            result.deployment = deployment

            if deployment.deployed:
                logger.info("[Pipeline] Deployed to Firebase successfully")
                for url in deployment.live_urls:
                    logger.info(f"  → {url}")
            elif not config.deploy:
                logger.info("[Pipeline] Files compiled locally (deploy=False)")
            else:
                logger.warning(f"[Pipeline] Deploy failed: {deployment.deploy_output[:200]}")
        except Exception as e:
            error_msg = f"Distribution failed: {e}"
            logger.error(f"[Pipeline] ✗ {error_msg}")
            result.errors.append(error_msg)

    logger.info(f"\n{'='*60}")
    logger.info(
        f"Pipeline complete: {len(result.pages)} pages compiled, "
        f"{len(result.errors)} errors"
    )
    logger.info(f"{'='*60}")

    return result


# ── Default Marzi topics ──

MARZI_TOPICS = [
    TopicConfig(
        topic="Marzi offline social events for people above 55 in Bangalore and Mumbai",
        category=ContentCategory.FAQ,
    ),
    TopicConfig(
        topic="How to get started with Marzi — book your first offline event for 55+",
        category=ContentCategory.HOW_TO,
    ),
    TopicConfig(
        topic="Marzi vs other social platforms for people above 55 — offline meetups comparison",
        category=ContentCategory.COMPARISON,
    ),
    TopicConfig(
        topic="What is Marzi — the offline events platform for people above 55",
        category=ContentCategory.INFORMATIONAL,
    ),
]
