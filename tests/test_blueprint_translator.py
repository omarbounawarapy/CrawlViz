"""Unit tests for routes/blueprint_translator.py.

Covers the validation/defaulting logic directly responsible for two bugs
found in this codebase's audit: `priority_strategy` being silently
dropped (fixed by sourcing ALLOWED_PRIORITY_STRATEGIES from
priority.strategy.STRATEGY_REGISTRY instead of a hand-copied set), and
the general "required key missing / invalid enum value" validation path.
"""
import copy

import pytest

from routes.blueprint_translator import (
    ALLOWED_EXPORT_TYPES,
    ALLOWED_PRIORITY_STRATEGIES,
    ALLOWED_STRATEGIES,
    BlueprintValidationError,
    translate_blueprint,
)


def base_user_input():
    """A minimal, valid, manual-mode user_input dict. Tests mutate a deep
    copy of this rather than re-declaring the whole shape each time.
    """
    return {
        "blueprint_id": "test_bp",
        "id": "run_1",
        "target_topic": "test topic",
        "seeds": [{"url": "https://example.com/a", "domain": "https://example.com"}],
        "domains": {
            "example": {"base_url": "https://example.com", "link_selector": "//a"}
        },
        "scoring": {
            "strategy": "TOPICAL",
            "params": {"scoring_type": "openrouter", "model_information": "gpt"},
        },
        "expansion": {
            "style": "rich",
            "num_descriptions": 5,
            "llm_type": "openrouter",
            "llm_model": "gpt",
        },
        "stop_conditions": {
            "max_nodes": 10,
            "max_depth": 2,
            "max_duration": 100,
            "no_progress_timeout": 100,
            "stop_url": "",
        },
    }


def manual_fields():
    return {
        "title": {
            "selector": "//h1",
            "type": "scalar",
            "transform": [],
            "export_type": "text",
        }
    }


def translate(user_input=None, fields=None):
    return translate_blueprint(
        user_input=user_input if user_input is not None else base_user_input(),
        manual_fields=fields if fields is not None else manual_fields(),
        extraction_mode="manual",
    )


class TestPriorityStrategy:
    """The bug this session fixed: priority_strategy was silently
    dropped by the translator even though core.Crawler reads it.
    """

    def test_explicit_value_passes_through(self):
        ui = base_user_input()
        ui["stop_conditions"]["priority_strategy"] = "exploration"
        result = translate(ui)
        assert result["stop_conditions"]["priority_strategy"] == "exploration"

    def test_omitted_falls_back_to_default(self):
        ui = base_user_input()
        assert "priority_strategy" not in ui["stop_conditions"]
        result = translate(ui)
        assert result["stop_conditions"]["priority_strategy"] == "balanced"

    def test_invalid_value_rejected(self):
        ui = base_user_input()
        ui["stop_conditions"]["priority_strategy"] = "not_a_real_strategy"
        with pytest.raises(BlueprintValidationError, match="Unknown priority_strategy"):
            translate(ui)

    def test_allowed_set_matches_strategy_registry(self):
        # Guards against the exact bug class: this set must be *sourced
        # from*, not hand-copied from, priority.strategy.STRATEGY_REGISTRY.
        from priority.strategy import STRATEGY_REGISTRY
        assert ALLOWED_PRIORITY_STRATEGIES == frozenset(STRATEGY_REGISTRY)

    @pytest.mark.parametrize("strategy", sorted(ALLOWED_PRIORITY_STRATEGIES))
    def test_every_registered_strategy_is_accepted(self, strategy):
        ui = base_user_input()
        ui["stop_conditions"]["priority_strategy"] = strategy
        result = translate(ui)
        assert result["stop_conditions"]["priority_strategy"] == strategy


class TestScoringStrategy:
    def test_valid_strategy_passes_through(self):
        ui = base_user_input()
        ui["scoring"]["strategy"] = "PATHFINDING"
        result = translate(ui)
        assert result["scoring"]["strategy"] == "PATHFINDING"

    def test_invalid_strategy_rejected(self):
        ui = base_user_input()
        ui["scoring"]["strategy"] = "NOT_A_REAL_STRATEGY"
        with pytest.raises(BlueprintValidationError, match="Unknown strategy"):
            translate(ui)

    @pytest.mark.parametrize("strategy", sorted(ALLOWED_STRATEGIES))
    def test_every_allowed_strategy_is_accepted(self, strategy):
        ui = base_user_input()
        ui["scoring"]["strategy"] = strategy
        result = translate(ui)
        assert result["scoring"]["strategy"] == strategy


class TestRequiredTopLevelFields:
    @pytest.mark.parametrize(
        "missing_key",
        ["blueprint_id", "id", "target_topic", "seeds", "domains", "scoring", "expansion", "stop_conditions"],
    )
    def test_missing_required_key_rejected(self, missing_key):
        ui = base_user_input()
        del ui[missing_key]
        with pytest.raises(BlueprintValidationError):
            translate(ui)


class TestStopConditions:
    @pytest.mark.parametrize(
        "missing_key",
        ["max_nodes", "max_depth", "max_duration", "no_progress_timeout", "stop_url"],
    )
    def test_missing_required_stop_condition_key_rejected(self, missing_key):
        ui = base_user_input()
        del ui["stop_conditions"][missing_key]
        with pytest.raises(BlueprintValidationError, match="stop_conditions is missing"):
            translate(ui)


class TestManualFieldExportType:
    @pytest.mark.parametrize("export_type", sorted(ALLOWED_EXPORT_TYPES))
    def test_every_allowed_export_type_accepted(self, export_type):
        fields = {"f": {"selector": "//x", "type": "scalar", "transform": [], "export_type": export_type}}
        result = translate(fields=fields)
        assert result["extraction"]["fields"]["f"]["export_type"] == export_type

    def test_invalid_export_type_rejected(self):
        fields = {"f": {"selector": "//x", "type": "scalar", "transform": [], "export_type": "not_a_type"}}
        with pytest.raises(BlueprintValidationError):
            translate(fields=fields)


class TestBlueprintStructureIsPreserved:
    def test_full_translation_produces_expected_top_level_keys(self):
        result = translate()
        for key in ("blueprint_id", "id", "target_topic", "seeds", "domains",
                    "scoring", "expansion", "extraction", "stop_conditions"):
            assert key in result

    def test_does_not_mutate_input_user_input(self):
        ui = base_user_input()
        ui_copy = copy.deepcopy(ui)
        translate(ui)
        assert ui == ui_copy
