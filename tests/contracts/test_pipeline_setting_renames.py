"""The `pipelines.<key>` settings sections move to the one-key names of ADR 6."""

import json
from pathlib import Path
from typing import Any

import pytest

from config.runtime_config import PipelinesConfig
from crawlviz.contracts import StoredFormatError
from crawlviz.contracts.pipeline_settings import (
    PIPELINE_SETTING_RENAMES,
    rename_pipeline_settings,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Sections whose key is already the ADR 6 key.
KEPT_KEYS = {"storage", "retry"}


def _fixture(format_name: str, version: int) -> dict[str, Any]:
    path = FIXTURES / format_name / f"v{version}.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def test_the_renames_are_the_adr_6_keys() -> None:
    assert PIPELINE_SETTING_RENAMES == {
        "processing": "extract",
        "requests": "fetch",
        "scoring": "score",
        "filtering": "filter",
        "priority": "prioritize",
        "transformation": "transform",
        "debugging": "debug_log",
    }


def test_every_pipelines_section_is_renamed_or_kept() -> None:
    # Holds before and after the model's fields take the new names, so no section is
    # forgotten by the migration.
    known = set(PIPELINE_SETTING_RENAMES) | set(PIPELINE_SETTING_RENAMES.values()) | KEPT_KEYS
    assert set(PipelinesConfig.model_fields) <= known


def test_an_old_settings_file_gets_the_new_section_names() -> None:
    old = _fixture("settings", 1)
    renamed = rename_pipeline_settings(old)
    assert renamed["pipelines"] == {"fetch": {"workers": 2}}
    # Everything outside `pipelines` is untouched.
    assert {k: v for k, v in renamed.items() if k != "pipelines"} == {
        k: v for k, v in old.items() if k != "pipelines"
    }


def test_every_old_section_moves_with_its_values() -> None:
    old: dict[str, dict[str, int | None]] = {
        key: {"workers": index + 1} for index, key in enumerate(PIPELINE_SETTING_RENAMES)
    }
    old["storage"] = {"workers": 5, "max_queue_size": None}
    renamed = rename_pipeline_settings({"pipelines": old})["pipelines"]
    assert renamed == {PIPELINE_SETTING_RENAMES.get(key, key): value for key, value in old.items()}


def test_settings_already_on_the_new_names_are_unchanged() -> None:
    new = {"pipelines": {"fetch": {"workers": 8}, "debug_log": {"workers": 1}}}
    assert rename_pipeline_settings(new) == new


def test_a_patch_without_pipeline_settings_is_unchanged() -> None:
    patch = {"fetch": {"min_delay": 3.0}}
    assert rename_pipeline_settings(patch) == patch


def test_a_malformed_pipelines_section_is_left_for_validation_to_report() -> None:
    patch = {"pipelines": ["requests"]}
    assert rename_pipeline_settings(patch) == patch


def test_the_input_is_not_changed() -> None:
    old = {"pipelines": {"requests": {"workers": 2}}}
    rename_pipeline_settings(old)
    assert old == {"pipelines": {"requests": {"workers": 2}}}


def test_an_old_and_a_new_name_for_one_section_is_refused_in_plain_words() -> None:
    both = {"pipelines": {"requests": {"workers": 2}, "fetch": {"workers": 8}}}
    expected = (
        r"pipelines\.requests and pipelines\.fetch are the same setting under its old and "
        r"new name\. Keep only pipelines\.fetch\."
    )
    with pytest.raises(StoredFormatError, match=expected):
        rename_pipeline_settings(both)
