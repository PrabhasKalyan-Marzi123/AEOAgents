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
from app.agents.researcher import ResearcherAgent
from app.agents.strategist import StrategistAgent
from app.agents.writer import WriterAgent
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
            logger.info("[Pipeline] Agent 1: Researching...")
            dossier = await researcher.run(topic=topic, brand_url=config.brand_url)
            _log_researcher_result(dossier)

            # Agent 2: Strategize
            logger.info("[Pipeline] Agent 2: Strategizing...")
            blueprint = strategist.run(dossier, category_override=topic_cfg.category)
            _log_strategist_result(blueprint)

            # Agent 3: Write
            logger.info("[Pipeline] Agent 3: Writing...")
            written = await writer.run(blueprint)
            _log_writer_result(written)

            # Agent 4: Compile
            logger.info("[Pipeline] Agent 4: Compiling...")
            compiled = compiler.run(written)
            _log_compiler_result(compiled)

            result.pages.append(compiled)

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
            _log_distributor_result(deployment, requested_deploy=config.deploy)
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


# ── Per-agent result logging ──

def _bullets(items, limit=5, prefix="    • "):
    """Format a list of items as indented bullets, truncated."""
    out = []
    for s in (items or [])[:limit]:
        out.append(f"{prefix}{str(s)[:140]}")
    if items and len(items) > limit:
        out.append(f"{prefix}… (+{len(items) - limit} more)")
    return "\n".join(out) if out else f"{prefix}(none)"


def _log_researcher_result(dossier) -> None:
    logger.info(
        "[Researcher] Result:\n"
        f"  brand: {(dossier.curated_context or {}).get('brand_name') or dossier.brand_data.get('brand_name', 'unknown')}\n"
        f"  serp_intent: {dossier.serp_intent} (confidence={dossier.intent_confidence}, signals={dossier.intent_signals})\n"
        f"  organic_results: {len(dossier.top_competitor_snippets)} | paa: {len(dossier.people_also_ask)} | related: {len(dossier.related_searches)} | answer_box: {'yes' if dossier.answer_box else 'no'}\n"
        f"  people_also_ask:\n{_bullets(dossier.people_also_ask)}\n"
        f"  competitor_topics_covered:\n{_bullets(dossier.competitor_topics_covered)}\n"
        f"  gaps:\n{_bullets(dossier.gaps)}\n"
        f"  unique_angles:\n{_bullets(dossier.unique_angles)}\n"
        f"  suggested_title: {dossier.suggested_title_direction or '(none)'}"
    )


def _log_strategist_result(blueprint) -> None:
    logger.info(
        "[Strategist] Result:\n"
        f"  category: {blueprint.category.value} | schema: {blueprint.schema_type}\n"
        f"  slug: {blueprint.slug}\n"
        f"  title_direction: {blueprint.title_direction}\n"
        f"  primary_entity: {blueprint.primary_entity} | related: {blueprint.related_entities}\n"
        f"  section_outline ({len(blueprint.section_outline)}):\n{_bullets(blueprint.section_outline, limit=12)}\n"
        f"  key_facts ({len(blueprint.key_facts_to_embed)}):\n{_bullets(blueprint.key_facts_to_embed, limit=8)}\n"
        f"  information_gain_angles ({len(blueprint.information_gain_angles)}):\n{_bullets(blueprint.information_gain_angles)}"
    )


def _log_writer_result(written) -> None:
    logger.info(
        "[Writer] Result:\n"
        f"  title: {written.title}\n"
        f"  slug: {written.slug} | category: {written.category.value}\n"
        f"  meta_description: {written.meta_description}\n"
        f"  tags: {written.tags}\n"
        f"  html_length: {len(written.content_html)} chars\n"
        f"  jsonld_specific_data keys: {list(written.jsonld_data.keys())}"
    )


def _log_compiler_result(compiled) -> None:
    logger.info(
        "[Compiler] Result:\n"
        f"  file: {compiled.file_path} ({len(compiled.full_html)} bytes)\n"
        f"  jsonld @type: {compiled.jsonld.get('@type', 'unknown')}\n"
        f"  category: {compiled.category} | tags: {compiled.tags}"
    )


def _log_distributor_result(deployment, requested_deploy: bool) -> None:
    status = "deployed" if deployment.deployed else ("skipped" if not requested_deploy else "failed")
    logger.info(
        "[Distributor] Result:\n"
        f"  index updated: {deployment.index_updated} | sitemap: {deployment.sitemap_generated} | robots: {deployment.robots_generated} | llms.txt: {deployment.llms_txt_generated}\n"
        f"  deploy: {status}\n"
        f"  live_urls ({len(deployment.live_urls)}):\n{_bullets(deployment.live_urls, limit=10)}"
    )
    if not deployment.deployed and requested_deploy and deployment.deploy_output:
        logger.warning(f"[Distributor] Deploy output: {deployment.deploy_output[:300]}")


# ── Default Marzi topics ──
#
# Categories are intentionally NOT pre-set: the Strategist decides each one
# based on live SerpApi intent. Pass an explicit category on TopicConfig only
# when you want to force a specific format.

MARZI_TOPICS = [
    TopicConfig(topic="offline social events for people above 55 in Bangalore"),
    TopicConfig(topic="how to find friends after retirement in India"),
    TopicConfig(topic="best social platforms for people above 55 in Mumbai"),
    TopicConfig(topic="social activities for seniors above 55 in Indian cities"),
]
