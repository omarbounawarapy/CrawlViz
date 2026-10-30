"""The long offline demo blueprint: valid, and set up to run for at least two minutes."""

import json
from pathlib import Path
from typing import Any

from config import TEMPLATES_DIR
from config.blueprint_schema import validate_blueprint

BLUEPRINT_FILE = "offline_demo_long.json"
MIN_DEMO_SECONDS = 120


def _load_blueprint() -> dict[str, Any]:  # Any: a blueprint is JSON read from disk
    blueprint: dict[str, Any] = json.loads(
        (Path(TEMPLATES_DIR) / BLUEPRINT_FILE).read_text(encoding="utf-8")
    )
    return blueprint


def test_long_demo_blueprint_validates() -> None:
    blueprint = validate_blueprint(_load_blueprint())

    assert blueprint.blueprint_id == BLUEPRINT_FILE.removesuffix(".json")


def test_long_demo_stops_on_time_not_on_page_count() -> None:
    """A time limit past two minutes is what keeps the demo running that long."""
    conditions = validate_blueprint(_load_blueprint()).stop_conditions

    assert conditions.max_duration >= MIN_DEMO_SECONDS
    assert conditions.no_progress_timeout < conditions.max_duration


def test_long_demo_seed_is_on_the_domain_it_declares() -> None:
    blueprint = validate_blueprint(_load_blueprint())
    domain_urls = {domain.base_url for domain in blueprint.domains.values()}

    for seed in blueprint.seeds:
        assert seed.domain in domain_urls
        assert seed.url.startswith(seed.domain)
