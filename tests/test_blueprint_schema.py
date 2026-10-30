"""Tests for the pydantic schema layer added to
config/blueprint_translator.py's final validation pass.

These specifically target cases the pre-existing hand-written validators
never checked (they only checked key *presence*, not value *type*), to
demonstrate the schema pass is adding real coverage, not just duplicating
what was already there.
"""

import json

import pytest

from config.blueprint_schema import (
    Blueprint,
    BlueprintSchemaError,
    StopConditions,
    validate_blueprint,
)
from config.blueprint_translator import BlueprintValidationError
from core.boot_strapper import BootStrapper
from tests.test_blueprint_translator import base_user_input, translate


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
                max_nodes=1,
                max_depth=1,
                max_duration=1,
                no_progress_timeout=1,
                priority_strategy="not_real",
            )


class TestCrawlLimitDefaults:
    def test_a_blueprint_without_limits_gets_500_pages_depth_5_and_one_hour(self):
        sc = StopConditions(no_progress_timeout=60)
        assert (sc.max_nodes, sc.max_depth, sc.max_duration) == (500, 5, 3600)

    def test_limits_the_blueprint_sets_are_kept(self):
        sc = StopConditions(max_nodes=7, max_depth=2, max_duration=30, no_progress_timeout=60)
        assert (sc.max_nodes, sc.max_depth, sc.max_duration) == (7, 2, 30)

    def test_the_bootstrapper_fills_in_the_limits_a_blueprint_left_out(self, tmp_path):
        blueprint = translate()
        for limit in ("max_nodes", "max_depth", "max_duration"):
            del blueprint["stop_conditions"][limit]
        (tmp_path / "limits.json").write_text(json.dumps(blueprint))
        bootstrapper = BootStrapper(None, None, "limits.json", templates_dir=tmp_path)

        loaded = bootstrapper.load_template()

        stop = loaded["stop_conditions"]
        assert (stop["max_nodes"], stop["max_depth"], stop["max_duration"]) == (500, 5, 3600)


class TestBlueprintModelAcceptsRealAssembledOutput:
    def test_full_translate_output_validates_against_schema_standalone(self):
        # The exact dict translate() produces should also validate on its
        # own if constructed directly -- i.e. Blueprint really is the
        # schema for BlueprintTranslator's actual output, not a fiction.
        result = translate()
        Blueprint.model_validate(result)  # should not raise


class TestTargetTopicNeedsAWord:
    """A topic with no word character embeds to an all-zero vector, so every
    link scored against it gets priority 0."""

    @pytest.mark.parametrize("topic", ["", "   ", "\t\n", "?!-", "..."])
    def test_topic_without_a_word_character_is_rejected(self, topic):
        blueprint = translate()
        blueprint["target_topic"] = topic
        with pytest.raises(BlueprintSchemaError, match="target_topic"):
            validate_blueprint(blueprint)

    @pytest.mark.parametrize("topic", ["tea", " Type 2 Diabetes ", "AI", "café", "2"])
    def test_topic_with_a_word_character_is_accepted(self, topic):
        blueprint = translate()
        blueprint["target_topic"] = topic
        assert validate_blueprint(blueprint).target_topic == topic
