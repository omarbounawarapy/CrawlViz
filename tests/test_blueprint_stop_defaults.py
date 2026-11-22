"""A blueprint that omits an optional stop condition runs with the schema's default.

``StopConditions`` (config/blueprint_schema.py) lets ``stop_url`` default to
"", so such a blueprint passes validation. The crawler reads the raw blueprint
dict, so the stages must fill the same defaults in themselves; before they did,
building the stopping stage raised ``KeyError: 'stop_url'`` after the LLM
expansion had already spent calls.
"""

import asyncio
import json
import socket
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from config.blueprint_schema import BlueprintSchemaError, StopConditions, validate_blueprint
from config.paths import RuntimePaths
from config.runtime_config import RuntimeConfig, default_runtime_config
from core import Crawler
from core.stages import StageInputs, priority_strategy_name
from events import NodeAddedEvent, StopCrawlEvent
from offline import build_offline_session
from pipelines import StopConditions as StageStopConditions
from pipelines import StoppingPipeline
from tests.test_stages import BLUEPRINT, inputs

BLUEPRINT_NAME = "offline_demo.json"
CRAWL_TIMEOUT_SECONDS = 60
SMALL_PAGE_BUDGET = 3
NON_DEFAULT_STRATEGY = "aggressive"
STOP_NEVER_SECONDS = 3600.0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _offline_blueprint(templates_dir: Path, drop: str | None = None) -> dict[str, Any]:
    """The offline demo blueprint with a small page budget, written to ``templates_dir``."""
    blueprint: dict[str, Any] = json.loads(
        Path("templates", BLUEPRINT_NAME).read_text(encoding="utf-8")
    )
    blueprint["stop_conditions"]["max_nodes"] = SMALL_PAGE_BUDGET
    if drop is not None:
        del blueprint["stop_conditions"][drop]
    templates_dir.mkdir()
    (templates_dir / BLUEPRINT_NAME).write_text(json.dumps(blueprint), encoding="utf-8")
    return blueprint


def _stage_inputs(tmp_path: Path, stop_conditions: dict[str, Any]) -> StageInputs:
    blueprint = {**BLUEPRINT, "stop_conditions": stop_conditions}
    return replace(inputs(tmp_path), blueprint=blueprint)


def _config_with_strategy(config: RuntimeConfig, strategy: str) -> RuntimeConfig:
    cascade = config.scoring_cascade.model_copy(update={"default_priority_strategy": strategy})
    return config.model_copy(update={"scoring_cascade": cascade})


@pytest.mark.slow
async def test_crawl_without_stop_url_runs_to_its_page_budget(tmp_path: Path) -> None:
    blueprint = _offline_blueprint(tmp_path / "templates", drop="stop_url")
    validate_blueprint(blueprint)  # valid: stop_url has a schema default
    session = build_offline_session(default_runtime_config())
    crawler = Crawler(
        BLUEPRINT_NAME,
        config=session.config,
        paths=RuntimePaths.under(tmp_path, templates_dir=tmp_path / "templates"),
        seed=0,
        ui_port=_free_port(),
        llm=session.llm,
        fetcher=session.fetcher,
    )

    stops: list[StopCrawlEvent] = []
    emit = crawler.event_broker.emit

    async def record_stop(event: object) -> None:
        if isinstance(event, StopCrawlEvent):
            stops.append(event)
        await emit(event)

    crawler.event_broker.emit = record_stop  # type: ignore[method-assign]

    await asyncio.wait_for(crawler.start(), CRAWL_TIMEOUT_SECONDS)

    assert [stop.reason for stop in stops] == ["MAX_NODES_REACHED"]
    # Fetches under way when the stop fires still finish, so it may overshoot the budget.
    assert len(session.fetcher.fetched) >= SMALL_PAGE_BUDGET


def test_missing_stop_conditions_take_the_schema_defaults(tmp_path: Path) -> None:
    required = {"max_nodes": 5, "max_depth": 2, "max_duration": 9.0, "no_progress_timeout": 4.0}

    conditions = _stage_inputs(tmp_path, dict(required)).stop_conditions

    assert conditions["stop_url"] == StopConditions.model_fields["stop_url"].default
    assert {key: conditions[key] for key in required} == required


def test_stop_conditions_the_blueprint_sets_win_over_the_defaults(tmp_path: Path) -> None:
    conditions = _stage_inputs(
        tmp_path,
        {**BLUEPRINT["stop_conditions"], "stop_url": "https://example.org/end"},
    ).stop_conditions

    assert conditions["stop_url"] == "https://example.org/end"


def test_priority_strategy_is_not_filled_in_from_the_schema(tmp_path: Path) -> None:
    stage_inputs = _stage_inputs(tmp_path, dict(BLUEPRINT["stop_conditions"]))

    assert "priority_strategy" not in stage_inputs.stop_conditions


def test_blueprint_without_priority_strategy_gets_the_configured_default() -> None:
    config = default_runtime_config()
    assert config.scoring_cascade.default_priority_strategy != NON_DEFAULT_STRATEGY
    configured = _config_with_strategy(config, NON_DEFAULT_STRATEGY)
    blueprint = {"stop_conditions": dict(BLUEPRINT["stop_conditions"])}
    assert "priority_strategy" not in blueprint["stop_conditions"]

    assert priority_strategy_name(blueprint, configured) == NON_DEFAULT_STRATEGY


def test_blueprint_priority_strategy_wins_over_the_configured_default() -> None:
    configured = _config_with_strategy(default_runtime_config(), NON_DEFAULT_STRATEGY)
    blueprint = {
        "stop_conditions": {**BLUEPRINT["stop_conditions"], "priority_strategy": "balanced"}
    }

    assert priority_strategy_name(blueprint, configured) == "balanced"


class _CountingLlm:
    """Records whether the crawl asked the LLM anything."""

    def __init__(self) -> None:
        self.calls = 0

    async def send(self, context: object) -> dict[str, Any]:
        self.calls += 1
        raise AssertionError("no LLM call before the blueprint is accepted")


@pytest.mark.parametrize(
    "required", ["max_nodes", "max_depth", "max_duration", "no_progress_timeout"]
)
async def test_blueprint_missing_a_required_stop_condition_fails_before_any_llm_call(
    tmp_path: Path, required: str
) -> None:
    _offline_blueprint(tmp_path / "templates", drop=required)
    llm = _CountingLlm()
    crawler = Crawler(
        BLUEPRINT_NAME,
        config=default_runtime_config(),
        paths=RuntimePaths.under(tmp_path, templates_dir=tmp_path / "templates"),
        ui_port=_free_port(),
        llm=llm,
    )

    with pytest.raises(BlueprintSchemaError, match=f"stop_conditions.{required}"):
        await crawler.start()

    assert llm.calls == 0


class _Broker:
    """Collects the events a stage emits."""

    def __init__(self) -> None:
        self.emitted: list[StopCrawlEvent] = []

    async def emit(self, event: StopCrawlEvent) -> None:
        self.emitted.append(event)


def _stopping_with_target(target_url: str | None) -> tuple[StoppingPipeline, _Broker]:
    broker = _Broker()
    conditions = StageStopConditions(
        max_nodes=SMALL_PAGE_BUDGET,
        max_duration=STOP_NEVER_SECONDS,
        no_progress_timeout=STOP_NEVER_SECONDS,
        target_url=target_url,  # type: ignore[arg-type]  # a blueprint may hand over None
    )
    return StoppingPipeline(broker, conditions), broker


def _node_added(url: str) -> NodeAddedEvent:
    return NodeAddedEvent(correlation_id="1", node=SimpleNamespace(get_full_url=lambda: url))


@pytest.mark.parametrize("no_target", ["", None])
async def test_no_target_url_never_stops_the_crawl(no_target: str | None) -> None:
    stopping, broker = _stopping_with_target(no_target)

    await stopping._on_node_added(_node_added("https://example.org/any/page"))

    assert broker.emitted == []


async def test_a_node_at_the_target_url_stops_the_crawl() -> None:
    stopping, broker = _stopping_with_target("https://example.org/end")

    await stopping._on_node_added(_node_added("https://example.org/end"))

    assert [event.reason for event in broker.emitted] == ["TARGET_REACHED"]
