"""Preset descriptions are generated from the preset values, so the prose and
the numbers cannot disagree (the frugal "a tenth" wording did, once)."""

import pytest

from routes import config as config_routes


@pytest.mark.parametrize("name", sorted(config_routes.BUILTIN_PRESETS))
def test_every_builtin_preset_has_a_description(name):
    assert config_routes.PRESET_DESCRIPTIONS[name]


def test_polite_and_fast_state_their_pace_and_fetches():
    polite = config_routes.PRESET_DESCRIPTIONS["polite"]
    assert "2 s between requests" in polite and "0.5 s random" in polite and "2 parallel fetches" in polite
    fast = config_routes.PRESET_DESCRIPTIONS["fast"]
    assert "0.2 s between requests" in fast and "8 parallel fetches" in fast


def test_frugal_states_the_percentages_not_a_word():
    frugal = config_routes.PRESET_DESCRIPTIONS["frugal"]
    assert "10 % of the high-confidence bucket" in frugal
    assert "0 % of low-score links" in frugal
    assert "a tenth" not in frugal


def test_preset_labels_match_the_goal_cards():
    labels = config_routes.PRESET_LABELS
    goals = config_routes.goals()
    assert labels["polite"] == goals["gentler"]["label"]
    assert labels["frugal"] == goals["cheaper"]["label"]
    assert set(labels) == set(config_routes.BUILTIN_PRESETS)


def test_list_presets_returns_the_labels():
    body = config_routes.list_presets()
    assert body["labels"] == config_routes.PRESET_LABELS


def test_frugal_names_the_default_it_moves_from():
    from config.runtime_config import default_runtime_config

    base = default_runtime_config().scoring_cascade
    frugal = config_routes.PRESET_DESCRIPTIONS["frugal"]
    assert f"(default {round(base.high_score_llm_fraction * 100):g} %)" in frugal


def test_description_follows_the_values(monkeypatch):
    values = {"scoring_cascade": {"high_score_llm_fraction": 0.25, "low_score_sample_fraction": 0.05}}
    text = config_routes._preset_description("frugal", values)
    assert "25 % of the high-confidence bucket" in text and "5 % of low-score links" in text


@pytest.mark.parametrize("name", ["gentler", "cheaper", "explore"])
def test_goal_descriptions_are_generated_from_their_values(name):
    text = config_routes.goals()[name]["description"]
    assert text.endswith(".")
    if name == "explore":
        assert "with the exploration strategy" in text
        assert "85 to the LLM's 15" in text


def _merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for key, value in patch.items():
        out[key] = _merge(base.get(key, {}), value) if isinstance(value, dict) else value
    return out


@pytest.mark.parametrize("name", ["gentler", "cheaper", "explore"])
def test_goal_patch_validates_against_the_schema(name):
    from config.runtime_config import RuntimeConfig

    merged = _merge(RuntimeConfig().model_dump(mode="json"), config_routes.goals()[name]["values"])
    RuntimeConfig.model_validate(merged)
