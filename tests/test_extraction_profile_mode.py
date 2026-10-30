"""A blueprint saved in profile mode must extract through the profile's fields.

The editor stores `profile_mode`, `profile_id` and `profile_field_checklist` and no `fields`;
the server resolves them when it loads the blueprint, so extraction is never empty.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from config.blueprint_schema import BlueprintSchemaError, validate_blueprint
from core.boot_strapper import BootStrapper
from models.item_extractor import ItemExtractor

with open("templates/wikiMD.json", encoding="utf-8") as _f:
    BASE = json.load(_f)

PAGE = (
    "<html><body><h1 id='firstHeading'>Aspirin</h1>"
    "<div class='mw-parser-output'><p>A pain reliever.</p><h2>Uses</h2></div></body></html>"
)


def profile_blueprint(**extraction: Any) -> dict[str, Any]:  # blueprints are parsed JSON
    blueprint: dict[str, Any] = copy.deepcopy(BASE)
    blueprint["extraction"] = {"mode": "document", "profile_mode": True, **extraction}
    return blueprint


def load(tmp_path: Path, blueprint: dict[str, Any]) -> dict[str, Any]:
    (tmp_path / "bp.json").write_text(json.dumps(blueprint), encoding="utf-8")
    loaded: dict[str, Any] = BootStrapper(
        None, None, "bp.json", templates_dir=tmp_path
    ).load_template()
    return loaded


def test_profile_mode_blueprint_extracts_the_profile_fields(tmp_path: Path) -> None:
    loaded = load(tmp_path, profile_blueprint(profile_id="wikimd_standard"))
    items = ItemExtractor(loaded["extraction"]).extract_items(PAGE, node=None)
    assert items[0]["title"] == "Aspirin"
    assert items[0]["paragraphs"] == ["A pain reliever."]


def test_profile_field_checklist_limits_the_fields(tmp_path: Path) -> None:
    loaded = load(
        tmp_path,
        profile_blueprint(profile_id="wikimd_standard", profile_field_checklist=["title"]),
    )
    assert list(loaded["extraction"]["fields"]) == ["title"]


def test_manual_fields_are_kept_when_profile_mode_is_off(tmp_path: Path) -> None:
    blueprint = copy.deepcopy(BASE)
    blueprint["extraction"]["profile_mode"] = False
    loaded = load(tmp_path, blueprint)
    assert loaded["extraction"]["fields"] == BASE["extraction"]["fields"]


@pytest.mark.parametrize(
    ("extraction", "message"),
    [
        ({}, "profile_id"),
        ({"profile_id": "no_such_profile"}, "no_such_profile"),
        ({"profile_id": "wikimd_standard", "profile_field_checklist": ["nope"]}, "nope"),
    ],
)
def test_profile_mode_errors_are_reported_when_the_blueprint_is_validated(
    extraction: dict[str, Any], message: str
) -> None:
    with pytest.raises(BlueprintSchemaError, match=message):
        validate_blueprint(profile_blueprint(**extraction))
