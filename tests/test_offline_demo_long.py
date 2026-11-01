"""The long offline demo blueprint: valid, and its stop conditions agree with each other."""

import json
from pathlib import Path
from typing import Any

from config import TEMPLATES_DIR
from config.blueprint_schema import validate_blueprint

BLUEPRINT_FILE = "offline_demo_long.json"


def _load_blueprint() -> dict[str, Any]:  # Any: a blueprint is JSON read from disk
    blueprint: dict[str, Any] = json.loads(
        (Path(TEMPLATES_DIR) / BLUEPRINT_FILE).read_text(encoding="utf-8")
    )
    return blueprint


def test_long_demo_blueprint_validates() -> None:
    blueprint = validate_blueprint(_load_blueprint())

    assert blueprint.blueprint_id == BLUEPRINT_FILE.removesuffix(".json")


def test_long_demo_gives_up_on_no_progress_before_its_time_limit() -> None:
    conditions = validate_blueprint(_load_blueprint()).stop_conditions

    assert conditions.no_progress_timeout < conditions.max_duration


def test_long_demo_seed_is_on_the_domain_it_declares() -> None:
    blueprint = validate_blueprint(_load_blueprint())
    domain_urls = {domain.base_url for domain in blueprint.domains.values()}

    for seed in blueprint.seeds:
        assert seed.domain in domain_urls
        assert seed.url.startswith(seed.domain)
