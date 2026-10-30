"""The long offline demo: its site script serves the blueprint, rate limits it, caps its budget."""

import json
from pathlib import Path

import aiohttp
import pytest

from config import TEMPLATES_DIR
from config.blueprint_schema import validate_blueprint
from config.runtime_config import default_runtime_config
from offline import build_offline_session
from offline.session import SITE_SCRIPTS_DIR, find_site_script
from offline.site_script import SiteScript
from pipelines.requests_pipeline import is_rate_limited

LONG_DEMO = "offline_demo_long.json"


def _blueprint() -> dict:
    return json.loads((Path(TEMPLATES_DIR) / LONG_DEMO).read_text(encoding="utf-8"))


def _request(url: str) -> dict:
    return {"url": url, "headers": {}, "data": "", "method": "GET"}


def _script(episodes: list[dict]) -> SiteScript:
    return SiteScript.model_validate(
        {
            "schema_version": 1,
            "site": {"n_pages": 20, "out_degree": 3, "relevant_fraction": 0.3, "seed": 1},
            "rate_limit_episodes": episodes,
            "config": {},
        }
    )


def test_every_script_file_is_a_valid_script() -> None:
    for path in SITE_SCRIPTS_DIR.glob("*.json"):
        SiteScript.load(path)


async def test_the_site_serves_the_seed_page_of_the_long_demo_blueprint() -> None:
    seed_url = validate_blueprint(_blueprint()).seeds[0].url
    session = build_offline_session(default_runtime_config(), LONG_DEMO)

    html = await session.fetcher.emit_request(_request(seed_url))

    assert 'id="firstHeading"' in html
    assert 'href="/' in html


def test_the_site_is_big_enough_to_outlast_the_blueprint_time_limit() -> None:
    script = find_site_script(LONG_DEMO)

    assert script is not None
    assert script.site.n_pages >= validate_blueprint(_blueprint()).stop_conditions.max_nodes


def test_a_blueprint_without_a_script_gets_the_isi_graph() -> None:
    session = build_offline_session(default_runtime_config(), "offline_demo.json")

    assert not hasattr(session.fetcher, "rate_limited")


def test_the_script_budget_and_pace_apply_over_the_defaults() -> None:
    script = find_site_script(LONG_DEMO)
    assert script is not None

    config = script.apply_config(default_runtime_config())

    assert config.llm.max_calls_per_crawl == script.config["llm"]["max_calls_per_crawl"]
    assert config.pipelines.requests.workers == script.config["pipelines"]["requests"]["workers"]


def test_a_setting_the_caller_changed_wins_over_the_script() -> None:
    script = find_site_script(LONG_DEMO)
    assert script is not None
    caller_budget = 7
    chosen = default_runtime_config()
    chosen.llm.max_calls_per_crawl = caller_budget

    config = script.apply_config(chosen)

    assert config.llm.max_calls_per_crawl == caller_budget
    assert config.pipelines.requests.workers == script.config["pipelines"]["requests"]["workers"]


async def test_the_site_answers_429_during_an_episode_then_recovers() -> None:
    fetcher = _script([{"after_fetches": 1, "rejected_requests": 2}]).build_fetcher()
    url = "https://frozen.test/p0"

    await fetcher.emit_request(_request(url))  # the first fetch is served
    for _ in range(2):
        with pytest.raises(aiohttp.ClientResponseError) as refused:
            await fetcher.emit_request(_request(url))
        assert is_rate_limited(refused.value)
    await fetcher.emit_request(_request(url))  # the site has recovered

    assert fetcher.rate_limited == 2
    assert len(fetcher.fetched) == 2


async def test_episodes_start_in_order_of_fetched_pages() -> None:
    fetcher = _script(
        [
            {"after_fetches": 2, "rejected_requests": 1},
            {"after_fetches": 0, "rejected_requests": 1},
        ]
    ).build_fetcher()
    url = "https://frozen.test/p0"

    outcomes = []
    for _ in range(5):
        try:
            await fetcher.emit_request(_request(url))
            outcomes.append("served")
        except aiohttp.ClientResponseError:
            outcomes.append("429")

    assert outcomes == ["429", "served", "served", "429", "served"]


def test_a_script_with_an_unknown_key_is_refused() -> None:
    with pytest.raises(ValueError):
        SiteScript.model_validate(
            {
                "schema_version": 1,
                "site": {"n_pages": 20, "out_degree": 3, "relevant_fraction": 0.3, "seed": 1},
                "rate_limit_episodes": [],
                "config": {},
                "episodes": [],
            }
        )
