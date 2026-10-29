"""The stage registry (core/stages.py) is the one list of the crawl's stages."""
from pathlib import Path
from typing import Any

from config.paths import RuntimePaths
from config.runtime_config import PipelinesConfig, RuntimeConfig, default_runtime_config
from core.event_broker import EventBroker
from core.stages import STAGES, StageInputs, build_stages, priority_strategy_name
from infrastructure.call_budget import CallBudget
from models import Storage
from pipelines import FilteringPipeline, RetryProcessor
from pipelines.contracts import CrawlStage

BLUEPRINT: dict[str, Any] = {
    "blueprint_id": "test-bp",
    "extraction": {"fields": []},
    "stop_conditions": {
        "max_nodes": 50, "max_depth": 3, "max_duration": 60,
        "no_progress_timeout": 30, "stop_url": None,
    },
}


class Inert:
    """Stands in for the NLP and scoring services, which no builder calls."""

    async def score_links(self, *args: object) -> list[object]:
        return []

    async def update_space(self, links: list[object]) -> None:
        return None


def inputs(tmp_path: Path, config: RuntimeConfig | None = None) -> StageInputs:
    config = config or default_runtime_config()
    return StageInputs(
        broker=EventBroker(),
        storage=Storage(),
        config=config,
        paths=RuntimePaths.under(tmp_path),
        crawl_id="test-2026",
        blueprint=BLUEPRINT,
        nlp_service=Inert(),
        scoring_service=Inert(),
        call_budget=CallBudget(None),
        fetch_concurrency=2,
        scoring_concurrency=1,
        seed=3,
    )


def test_stage_keys_are_unique() -> None:
    keys = [spec.key for spec in STAGES]
    assert len(keys) == len(set(keys))


def test_every_pipelines_setting_belongs_to_exactly_one_stage() -> None:
    settings = [spec.setting for spec in STAGES if spec.setting is not None]
    assert sorted(settings) == sorted(PipelinesConfig.model_fields)


def test_build_stages_follows_the_registry_order(tmp_path: Path) -> None:
    stages = build_stages(inputs(tmp_path))
    assert list(stages) == [spec.key for spec in STAGES]
    for stage in stages.values():
        assert isinstance(stage, CrawlStage)


def test_settings_reach_the_stage_they_name(tmp_path: Path) -> None:
    config = default_runtime_config()
    config.pipelines.filtering.workers = 7
    stages = build_stages(inputs(tmp_path, config))
    filtering, retry = stages["filtering"], stages["retry"]
    assert isinstance(filtering, FilteringPipeline) and filtering.max_concurrency == 7
    assert isinstance(retry, RetryProcessor) and retry.requests_pipeline is stages["requests"]


def test_priority_strategy_defaults_to_the_configured_one() -> None:
    config = default_runtime_config()
    default = config.scoring_cascade.default_priority_strategy
    assert priority_strategy_name(BLUEPRINT, config) == default
    chosen = {**BLUEPRINT, "stop_conditions": {"priority_strategy": "exploration"}}
    assert priority_strategy_name(chosen, config) == "exploration"


def test_each_stream_is_seeded_by_name(tmp_path: Path) -> None:
    first, second = inputs(tmp_path), inputs(tmp_path)
    assert first.rng("requests").random() == second.rng("requests").random()
    assert first.rng("requests").random() != first.rng("scoring").random()
