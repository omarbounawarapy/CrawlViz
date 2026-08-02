"""
blueprint_translator.py
-----------------------
BlueprintTranslator converts user input (plus an optional extraction profile
or manual field definitions) into a valid, structure-preserving blueprint dict.

Constraints:
    - Blueprint structure is never modified; only values are substituted.
    - Only ALLOWED_STRATEGIES are accepted.
    - Only ALLOWED_TRANSFORMS are accepted.
    - Only ALLOWED_EXPORT_TYPES are accepted.
    - Profile mode resolves selectors/transforms automatically.
    - Manual mode requires all field attributes to be supplied explicitly.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any

import pydantic

from config import DEFAULT_PRIORITY_STRATEGY
from priority.strategy import STRATEGY_REGISTRY

from .blueprint_schema import (
    ALLOWED_EXPORT_TYPES,
    ALLOWED_FIELD_TYPES,
    ALLOWED_PRIORITY_STRATEGIES,
    ALLOWED_STRATEGIES,
    ALLOWED_TRANSFORMS,
    Blueprint,
)
from .blueprint_schema import _PARAMETERISED_TRANSFORMS  # noqa: F401 (used below)

# =========================================================
# PROFILE REGISTRY
# =========================================================

# Profiles are loaded once from the static JSON file that lives alongside this
# module. The registry maps profile_id -> profile dict.
_PROFILES_FILE = os.path.join(os.path.dirname(__file__), "extraction_profiles.json")


def _load_profiles() -> dict[str, Any]:
    """Load profiles from the static JSON file; return empty dict on error."""
    if not os.path.exists(_PROFILES_FILE):
        return {}
    with open(_PROFILES_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("profiles", {})


_PROFILE_REGISTRY: dict[str, Any] = _load_profiles()


# =========================================================
# VALIDATION HELPERS
# =========================================================

class BlueprintValidationError(ValueError):
    """Raised when user-supplied data would violate blueprint constraints."""


def _validate_strategy(strategy: str) -> None:
    if strategy not in ALLOWED_STRATEGIES:
        raise BlueprintValidationError(
            f"Unknown strategy {strategy!r}. "
            f"Allowed: {sorted(ALLOWED_STRATEGIES)}"
        )


def _validate_priority_strategy(priority_strategy: str) -> None:
    if priority_strategy not in ALLOWED_PRIORITY_STRATEGIES:
        raise BlueprintValidationError(
            f"Unknown priority_strategy {priority_strategy!r}. "
            f"Allowed: {sorted(ALLOWED_PRIORITY_STRATEGIES)}"
        )


def _validate_export_type(export_type: str, field_name: str) -> None:
    if export_type not in ALLOWED_EXPORT_TYPES:
        raise BlueprintValidationError(
            f"Invalid export_type {export_type!r} on field {field_name!r}. "
            f"Allowed: {sorted(ALLOWED_EXPORT_TYPES)}"
        )


def _validate_field_type(field_type: str, field_name: str) -> None:
    if field_type not in ALLOWED_FIELD_TYPES:
        raise BlueprintValidationError(
            f"Invalid type {field_type!r} on field {field_name!r}. "
            f"Allowed: {sorted(ALLOWED_FIELD_TYPES)}"
        )


def _validate_transform_step(step: dict[str, Any], field_name: str) -> None:
    """Validate a single transform step dict."""
    if "type" not in step:
        raise BlueprintValidationError(
            f"Transform step on field {field_name!r} is missing 'type' key."
        )
    t_type = step["type"]
    if t_type not in ALLOWED_TRANSFORMS:
        raise BlueprintValidationError(
            f"Unknown transform {t_type!r} on field {field_name!r}. "
            f"Allowed: {sorted(ALLOWED_TRANSFORMS)}"
        )
    # Validate required params for parameterised transforms.
    if t_type in _PARAMETERISED_TRANSFORMS:
        for required_key in _PARAMETERISED_TRANSFORMS[t_type]:
            # Provide a default for 'max_len' if missing.
            if t_type == "truncate" and required_key == "max_len":
                step.setdefault("max_len", 300)
            elif required_key not in step:
                raise BlueprintValidationError(
                    f"Transform {t_type!r} on field {field_name!r} "
                    f"requires parameter {required_key!r}."
                )
    # No-config transforms carrying extra params are accepted without warning.


def _validate_transform_pipeline(pipeline: list[dict[str, Any]], field_name: str) -> None:
    for step in pipeline:
        _validate_transform_step(step, field_name)


def _validate_field_dict(field_name: str, field_def: dict[str, Any]) -> None:
    """Full validation of a manually supplied field definition."""
    for required in ("selector", "type", "export_type"):
        if required not in field_def:
            raise BlueprintValidationError(
                f"Field {field_name!r} is missing required key {required!r}."
            )
    _validate_field_type(field_def["type"], field_name)
    _validate_export_type(field_def["export_type"], field_name)
    pipeline = field_def.get("transform", [])
    _validate_transform_pipeline(pipeline, field_name)


# =========================================================
# FIELD BUILDER
# =========================================================

def _build_field(field_name: str, field_def: dict[str, Any]) -> dict[str, Any]:
    """Return a fully-specified field dict ready for injection into the blueprint.

    Expected keys in `field_def` (manual mode):
        selector: str
        type: "scalar" | "list"
        transform: list of transform-step dicts (may be empty)
        export_type: "text" | "real" | "int" | "json"
    """
    return {
        "selector": field_def["selector"],
        "type": field_def["type"],
        "transform": list(field_def.get("transform", [])),
        "export_type": field_def["export_type"],
    }


def _build_field_from_profile(field_name: str, profile_field: dict[str, Any]) -> dict[str, Any]:
    """Return a fully-specified field dict resolved from a profile definition.

    Expected keys in `profile_field`:
        selector: str
        type: "scalar" | "list"
        default_transforms: list of transform-step dicts
        export_type: "text" | "real" | "int" | "json"
    """
    return {
        "selector": profile_field["selector"],
        "type": profile_field["type"],
        "transform": list(profile_field.get("default_transforms", [])),
        "export_type": profile_field["export_type"],
    }


# =========================================================
# MAIN CLASS
# =========================================================

class BlueprintTranslator:
    """Converts user input plus an optional profile or manual fields into
    a valid blueprint.

    Args:
        user_input: Top-level blueprint fields supplied by the user.
            Required keys: blueprint_id, id, target_topic, seeds, domains,
            scoring, expansion, stop_conditions. If an 'extraction' key is
            present it is ignored in favor of the resolved extraction section.
        selected_profile: A profile_id string (e.g. "wikimd_standard").
            Required when `extraction_mode` is "profile".
        manual_fields: Mapping of field_name to field definition dict.
            Required when `extraction_mode` is "manual".
        extraction_mode: Either "profile" or "manual".
        profile_field_checklist: When set, restricts profile mode to only
            these field names; None resolves every field the profile defines.
    """

    def __init__(
        self,
        user_input: dict[str, Any],
        selected_profile: str | None = None,
        manual_fields: dict[str, Any] | None = None,
        extraction_mode: str = "profile",
        profile_field_checklist: list[str] | None = None,
    ) -> None:
        self._user_input = user_input
        self._selected_profile = selected_profile
        self._manual_fields = manual_fields or {}
        self._extraction_mode = extraction_mode
        self._profile_field_checklist = profile_field_checklist  # None means "all fields"

    # =========================================================
    # PUBLIC ENTRY POINT
    # =========================================================

    def translate(self) -> dict[str, Any]:
        """Produce and return a valid blueprint dict.

        Runs, in order: required-field validation, extraction-field
        resolution (profile or manual), structure-preserving assembly,
        and a final validation pass over the assembled blueprint.
        """
        self._validate_required_top_level_fields()
        extraction_fields = self._resolve_extraction_fields()
        blueprint = self._assemble_blueprint(extraction_fields)
        self._final_validation(blueprint)
        return blueprint

    # =========================================================
    # STEP 1: REQUIRED-FIELD VALIDATION
    # =========================================================

    def _validate_required_top_level_fields(self) -> None:
        required_keys = [
            "blueprint_id",
            "id",
            "target_topic",
            "seeds",
            "domains",
            "scoring",
            "expansion",
            "stop_conditions",
        ]
        for key in required_keys:
            if key not in self._user_input:
                raise BlueprintValidationError(
                    f"user_input is missing required top-level key {key!r}."
                )

        # Validate scoring strategy.
        scoring = self._user_input["scoring"]
        if "strategy" not in scoring:
            raise BlueprintValidationError("scoring section is missing 'strategy'.")
        _validate_strategy(scoring["strategy"])

        # Validate scoring params.
        params = scoring.get("params", {})
        for pk in ("scoring_type", "model_information"):
            if pk not in params:
                raise BlueprintValidationError(
                    f"scoring.params is missing required key {pk!r}."
                )

        # Validate expansion.
        expansion = self._user_input["expansion"]
        for ek in ("style", "num_descriptions", "llm_type", "llm_model"):
            if ek not in expansion:
                raise BlueprintValidationError(
                    f"expansion section is missing required key {ek!r}."
                )

        # Validate stop_conditions.
        sc = self._user_input["stop_conditions"]
        for sk in ("max_nodes", "max_depth", "max_duration", "no_progress_timeout", "stop_url"):
            if sk not in sc:
                raise BlueprintValidationError(
                    f"stop_conditions is missing required key {sk!r}."
                )
        # priority_strategy is optional -- falls back to
        # config.DEFAULT_PRIORITY_STRATEGY when omitted -- but if the
        # user did supply one, it must be a real priority/strategy.py entry.
        if "priority_strategy" in sc:
            _validate_priority_strategy(sc["priority_strategy"])

    # =========================================================
    # STEP 2: EXTRACTION FIELD RESOLUTION
    # =========================================================

    def _resolve_extraction_fields(self) -> dict[str, Any]:
        if self._extraction_mode == "profile":
            return self._resolve_profile_fields()
        elif self._extraction_mode == "manual":
            return self._resolve_manual_fields()
        else:
            raise BlueprintValidationError(
                f"Unknown extraction_mode {self._extraction_mode!r}. "
                "Must be 'profile' or 'manual'."
            )

    def _resolve_profile_fields(self) -> dict[str, Any]:
        """Load the selected profile and return its resolved field definitions."""
        if not self._selected_profile:
            raise BlueprintValidationError(
                "extraction_mode is 'profile' but no selected_profile was provided."
            )
        if self._selected_profile not in _PROFILE_REGISTRY:
            raise BlueprintValidationError(
                f"Profile {self._selected_profile!r} not found in registry. "
                f"Available: {list(_PROFILE_REGISTRY)}"
            )
        profile = _PROFILE_REGISTRY[self._selected_profile]
        all_fields: dict[str, Any] = profile["fields"]

        # Apply checklist filter if provided.
        if self._profile_field_checklist is not None:
            unknown = set(self._profile_field_checklist) - set(all_fields)
            if unknown:
                raise BlueprintValidationError(
                    f"Profile {self._selected_profile!r} does not contain "
                    f"field(s): {sorted(unknown)}"
                )
            all_fields = {
                k: v for k, v in all_fields.items()
                if k in self._profile_field_checklist
            }

        resolved: dict[str, Any] = {}
        for field_name, profile_field in all_fields.items():
            resolved[field_name] = _build_field_from_profile(field_name, profile_field)
        return resolved

    def _resolve_manual_fields(self) -> dict[str, Any]:
        """Validate and build field definitions from manually supplied data."""
        if not self._manual_fields:
            raise BlueprintValidationError(
                "extraction_mode is 'manual' but no manual_fields were provided."
            )
        resolved: dict[str, Any] = {}
        for field_name, field_def in self._manual_fields.items():
            _validate_field_dict(field_name, field_def)
            resolved[field_name] = _build_field(field_name, field_def)
        return resolved

    # =========================================================
    # STEP 3: STRUCTURE-PRESERVING ASSEMBLY
    # =========================================================

    def _assemble_blueprint(self, extraction_fields: dict[str, Any]) -> dict[str, Any]:
        """Assemble the final blueprint dict.

        Structure is fixed -- only values are substituted; keys and their
        order are preserved.
        """
        ui = self._user_input

        blueprint: dict[str, Any] = {
            "blueprint_id": ui["blueprint_id"],
            "id": ui["id"],
            "target_topic": ui["target_topic"],
            "seeds": copy.deepcopy(ui["seeds"]),
            "domains": copy.deepcopy(ui["domains"]),
            "scoring": {
                "strategy": ui["scoring"]["strategy"],
                "params": {
                    "scoring_type": ui["scoring"]["params"]["scoring_type"],
                    "model_information": ui["scoring"]["params"]["model_information"],
                },
            },
            "expansion": {
                "style": ui["expansion"]["style"],
                "num_descriptions": ui["expansion"]["num_descriptions"],
                "llm_type": ui["expansion"]["llm_type"],
                "llm_model": ui["expansion"]["llm_model"],
            },
            "extraction": {
                "mode": "document",
                "fields": extraction_fields,
            },
            "stop_conditions": {
                "max_nodes": ui["stop_conditions"]["max_nodes"],
                "max_depth": ui["stop_conditions"]["max_depth"],
                "max_duration": ui["stop_conditions"]["max_duration"],
                "no_progress_timeout": ui["stop_conditions"]["no_progress_timeout"],
                "stop_url": ui["stop_conditions"]["stop_url"],
                "priority_strategy": ui["stop_conditions"].get(
                    "priority_strategy", DEFAULT_PRIORITY_STRATEGY
                ),
            },
        }
        return blueprint

    # =========================================================
    # STEP 4: FINAL VALIDATION
    # =========================================================

    def _final_validation(self, blueprint: dict[str, Any]) -> None:
        """Post-assembly validation pass over the complete blueprint.

        Raises:
            BlueprintValidationError: On any constraint violation.
        """
        # Re-validate strategy (belt-and-suspenders).
        _validate_strategy(blueprint["scoring"]["strategy"])
        _validate_priority_strategy(blueprint["stop_conditions"]["priority_strategy"])

        # Validate every field in extraction.
        for field_name, field_def in blueprint["extraction"]["fields"].items():
            _validate_export_type(field_def.get("export_type", ""), field_name)
            _validate_field_type(field_def.get("type", ""), field_name)
            _validate_transform_pipeline(field_def.get("transform", []), field_name)

        # Validate seeds structure.
        for i, seed in enumerate(blueprint["seeds"]):
            for sk in ("url", "domain"):
                if sk not in seed:
                    raise BlueprintValidationError(
                        f"seeds[{i}] is missing required key {sk!r}."
                    )

        # Validate domains structure.
        for domain_name, domain_cfg in blueprint["domains"].items():
            for dk in ("base_url", "link_selector"):
                if dk not in domain_cfg:
                    raise BlueprintValidationError(
                        f"domains[{domain_name!r}] is missing required key {dk!r}."
                    )

        # Schema pass: validates the *assembled* blueprint against
        # blueprint_schema.Blueprint -- on top of, not instead of, the
        # checks above. This is what actually catches the next instance
        # of the "producer/consumer shape drifted apart" bug class (see
        # blueprint_schema.py's docstring for the three times that's
        # already happened), even for a field nobody remembered to add
        # a hand-written check for above.
        try:
            Blueprint.model_validate(blueprint)
        except pydantic.ValidationError as e:
            raise BlueprintValidationError(
                f"Assembled blueprint failed schema validation: {e}"
            ) from e


# =========================================================
# CONVENIENCE FACTORY
# =========================================================

def translate_blueprint(
    user_input: dict[str, Any],
    selected_profile: str | None = None,
    manual_fields: dict[str, Any] | None = None,
    extraction_mode: str = "profile",
    profile_field_checklist: list[str] | None = None,
) -> dict[str, Any]:
    """Convenience wrapper around BlueprintTranslator.translate().

    Returns:
        A valid blueprint ready to be written to disk and consumed by
        BootStrapper / Crawler.
    """
    translator = BlueprintTranslator(
        user_input=user_input,
        selected_profile=selected_profile,
        manual_fields=manual_fields,
        extraction_mode=extraction_mode,
        profile_field_checklist=profile_field_checklist,
    )
    return translator.translate()


# =========================================================
# USAGE EXAMPLES
# =========================================================

if __name__ == "__main__":

    # Example 1: profile mode
    user_input_profile = {
        "blueprint_id": "wikimd_diabetes_v2",
        "id": "beta_4",
        "target_topic": "TYPE 2 DIABETES",
        "seeds": [
            {
                "url": "https://wikimd.org/wiki/Diabetes_mellitus_type_2",
                "domain": "https://www.wikimd.org",
            }
        ],
        "domains": {
            "wikimd": {
                "base_url": "https://www.wikimd.org",
                "link_selector": (
                    ".//a[starts-with(@href, '/wiki/') and not(contains(@href, ':')) "
                    "and not(contains(@href, 'Main_Page'))]"
                ),
            }
        },
        "scoring": {
            "strategy": "TOPICAL",
            "params": {
                "scoring_type": "openrouter",
                "model_information": "openai/gpt-4o:free",
            },
        },
        "expansion": {
            "style": "rich",
            "num_descriptions": 50,
            "llm_type": "openrouter",
            "llm_model": "openai/gpt-4o:free",
        },
        "stop_conditions": {
            "max_nodes": 120000,
            "max_depth": 6000,
            "max_duration": 900000,
            "no_progress_timeout": 1000000,
            "stop_url": "",
        },
    }

    blueprint_profile = translate_blueprint(
        user_input=user_input_profile,
        selected_profile="wikimd_standard",
        extraction_mode="profile",
        profile_field_checklist=["title", "paragraphs", "categories"],
    )
    print("=== PROFILE MODE BLUEPRINT ===")
    print(json.dumps(blueprint_profile, indent=2))

    # Example 2: manual mode
    manual_fields_example = {
        "title": {
            "selector": "//h1[@id='firstHeading']",
            "type": "scalar",
            "transform": [{"type": "strip"}],
            "export_type": "text",
        },
        "summary": {
            "selector": "//div[@id='mw-content-text']//p[1]",
            "type": "scalar",
            "transform": [
                {"type": "strip"},
                {"type": "truncate", "max_len": 500},
            ],
            "export_type": "text",
        },
    }

    blueprint_manual = translate_blueprint(
        user_input=user_input_profile,
        manual_fields=manual_fields_example,
        extraction_mode="manual",
    )
    print("\n=== MANUAL MODE BLUEPRINT ===")
    print(json.dumps(blueprint_manual, indent=2))
