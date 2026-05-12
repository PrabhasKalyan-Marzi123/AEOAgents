"""Travel pipeline: TravelResearcher → Strategist → Writer → Compiler → TravelDistributor.

Mirrors backend's `app.agents.pipeline.run_pipeline` but instantiates the
travel-specific Researcher and Distributor, and routes the Compiler output
to `travel-blogs/firebase-hosting/public/`.

Backend's StrategistAgent, WriterAgent, and CompilerAgent are reused as-is —
they consume a brand-agnostic `ResearchDossier` / `ContentBlueprint` /
`WrittenContent` contract.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.agents.writer import WriterAgent
from app.agents.compiler import CompilerAgent, CompiledPage
from app.agents.distributor import DeploymentResult

from marzi_travel.researcher import TravelResearcherAgent
from marzi_travel.strategist import TravelStrategistAgent
from marzi_travel.distributor import TravelDistributorAgent
from marzi_travel import site_config

logger = logging.getLogger(__name__)


@dataclass
class TravelPipelineConfig:
    destinations: list[str] = field(default_factory=list)
    brand_url: str = site_config.BRAND_URL
    deploy: bool = True


@dataclass
class TravelPipelineResult:
    pages: list[CompiledPage] = field(default_factory=list)
    deployment: DeploymentResult | None = None
    errors: list[str] = field(default_factory=list)


async def run_travel_pipeline(config: TravelPipelineConfig) -> TravelPipelineResult:
    """Execute the travel pipeline for one or more destinations."""
    site_config.apply_to_settings()
    result = TravelPipelineResult()
    if not config.destinations:
        result.errors.append("No destinations provided")
        return result

    researcher = TravelResearcherAgent()
    strategist = TravelStrategistAgent()
    writer = WriterAgent()
    compiler = CompilerAgent(output_dir=site_config.OUTPUT_DIR)
    distributor = TravelDistributorAgent(output_dir=site_config.OUTPUT_DIR)

    logger.info("=" * 60)
    logger.info(
        f"Travel Pipeline: {len(config.destinations)} destinations, "
        f"brand={config.brand_url}"
    )
    logger.info("=" * 60)

    for i, destination in enumerate(config.destinations, 1):
        logger.info(f"\n--- Destination {i}/{len(config.destinations)}: {destination} ---")
        try:
            logger.info("[TravelPipeline] Researching (worry-research)...")
            dossier = await researcher.run(topic=destination, brand_url=config.brand_url)

            logger.info("[TravelPipeline] Strategizing...")
            blueprint = strategist.run(dossier)

            logger.info("[TravelPipeline] Writing...")
            written = await writer.run(blueprint)

            logger.info("[TravelPipeline] Compiling...")
            compiled = compiler.run(written)
            result.pages.append(compiled)
            logger.info(f"[TravelPipeline] Wrote {compiled.file_path}")
        except Exception as e:
            err = f"Failed on destination '{destination}': {e}"
            logger.error(f"[TravelPipeline] ✗ {err}")
            result.errors.append(err)
            import traceback
            traceback.print_exc()

    if result.pages:
        logger.info(f"\n--- Distributing {len(result.pages)} page(s) ---")
        try:
            deployment = distributor.run(result.pages, deploy=config.deploy)
            result.deployment = deployment
        except Exception as e:
            err = f"Distribution failed: {e}"
            logger.error(f"[TravelPipeline] ✗ {err}")
            result.errors.append(err)

    logger.info("=" * 60)
    logger.info(
        f"Travel pipeline complete: {len(result.pages)} pages, "
        f"{len(result.errors)} errors"
    )
    logger.info("=" * 60)
    return result
