"""Tests for the pydantic schema layer added to
routes/blueprint_translator.py's final validation pass.

These specifically target cases the pre-existing hand-written validators
never checked (they only checked key *presence*, not value *type*), to
demonstrate the schema pass is adding real coverage, not just duplicating
what was already there.
"""
import pytest

from routes.blueprint_schema import Blueprint, StopConditions
from routes.blueprint_translator import BlueprintValidationError
from tests.test_blueprint_translator import base_user_input, manual_fields, translate


class TestSchemaCatchesTypeErrorsHandWrittenChecksMissed:
    def test_max_nodes_wrong_type_rejected(self):
        # The hand-written check only did `if "max_nodes" not in sc`, it
        # never checked that the value was actually an int.
        ui = base_user_input()
        ui["stop_conditions"]["max_nodes"] = "ten"  # str instead of int
        with pytest.raises(BlueprintValidationError, match="schema validation"):
            translate(ui)

    def test_seed_missing_domain_key_rejected_even_if_present_check_passes(self):
        ui = base_user_input()
        ui["seeds"] = [{"url": "https://example.com/a"}]  # missing "domain"
        with pytest.raises(BlueprintValidationError):
            translate(ui)


class TestStopConditionsModelDirectly:
    def test_default_priority_strategy(self):
        sc = StopConditions(max_nodes=1, max_depth=1, max_duration=1, no_progress_timeout=1)
        assert sc.priority_strategy == "balanced"

    def test_rejects_unknown_priority_strategy(self):
        with pytest.raises(Exception):  # pydantic.ValidationError
            StopConditions(
                max_nodes=1, max_depth=1, max_duration=1,
                no_progress_timeout=1, priority_strategy="not_real",
            )


class TestBlueprintModelAcceptsRealAssembledOutput:
    def test_full_translate_output_validates_against_schema_standalone(self):
        # The exact dict translate() produces should also validate on its
        # own if constructed directly -- i.e. Blueprint really is the
        # schema for BlueprintTranslator's actual output, not a fiction.
        result = translate()
        Blueprint.model_validate(result)  # should not raise
