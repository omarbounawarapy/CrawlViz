"""
blueprint_translator.py
========================
BlueprintTranslator — converts user input (plus an optional extraction profile
or manual field definitions) into a valid, structure-preserving blueprint dict.

---------------------------------------------------------
- Blueprint structure is NEVER modified.
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
from typing import Any, Dict, List, Optional

# ── STRICT ENUMERATIONS ────────────────────────────────────────────────────────

ALLOWED_STRATEGIES: frozenset[str] = frozenset(
    {
        "TOPICAL",
        "PATHFINDING",
        "EXPLORATION",
        "GOAL_ORIENTED",
        "DENSITY_FOCUSED",
        "UNCERTAINTY_BIASED",
    }
)

ALLOWED_EXPORT_TYPES: frozenset[str] = frozenset({"text", "real", "int", "json"})

# Transforms that require no config parameters
_NO_CONFIG_TRANSFORMS: frozenset[str] = frozenset(
    {"strip", "lowercase", "deduplicate", "join"}
)
# Transforms that require config parameters
_PARAMETERISED_TRANSFORMS: Dict[str, List[str]] = {
    "truncate": ["max_len"],   # max_len: int, default 300
    "regex": ["pattern"],      # pattern: str
    "regex_extract": ["pattern"],
}

ALLOWED_TRANSFORMS: frozenset[str] = frozenset(
    _NO_CONFIG_TRANSFORMS | set(_PARAMETERISED_TRANSFORMS)
)

ALLOWED_FIELD_TYPES: frozenset[str] = frozenset({"scalar", "list"})

# ── PROFILE REGISTRY ──────────────────────────────────────────────────────────

# Profiles are loaded once from the static JSON file that lives alongside this
# module. The registry maps profile_id → profile dict.
_PROFILES_FILE = os.path.join(os.path.dirname(__file__), "extraction_profiles.json")


def _load_profiles() -> Dict[str, Any]:
    """Load profiles from the static JSON file; return empty dict on error."""
    if not os.path.exists(_PROFILES_FILE):
        return {}
    with open(_PROFILES_FILE, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("profiles", {})


_PROFILE_REGISTRY: Dict[str, Any] = _load_profiles()


# ── VALIDATION HELPERS ────────────────────────────────────────────────────────

class BlueprintValidationError(ValueError):
    """Raised when user-supplied data would violate blueprint constraints."""


def _validate_strategy(strategy: str) -> None:
    if strategy not in ALLOWED_STRATEGIES:
        raise BlueprintValidationError(
            f"Unknown strategy '{strategy}'. "
            f"Allowed: {sorted(ALLOWED_STRATEGIES)}"
        )


def _validate_export_type(export_type: str, field_name: str) -> None:
    if export_type not in ALLOWED_EXPORT_TYPES:
        raise BlueprintValidationError(
            f"Invalid export_type '{export_type}' on field '{field_name}'. "
            f"Allowed: {sorted(ALLOWED_EXPORT_TYPES)}"
        )


def _validate_field_type(field_type: str, field_name: str) -> None:
    if field_type not in ALLOWED_FIELD_TYPES:
        raise BlueprintValidationError(
            f"Invalid type '{field_type}' on field '{field_name}'. "
            f"Allowed: {sorted(ALLOWED_FIELD_TYPES)}"
        )


def _validate_transform_step(step: Dict[str, Any], field_name: str) -> None:
    """Validate a single transform step dict."""
    if "type" not in step:
        raise BlueprintValidationError(
            f"Transform step on field '{field_name}' is missing 'type' key."
        )
    t_type = step["type"]
    if t_type not in ALLOWED_TRANSFORMS:
        raise BlueprintValidationError(
            f"Unknown transform '{t_type}' on field '{field_name}'. "
            f"Allowed: {sorted(ALLOWED_TRANSFORMS)}"
        )
    # Validate required params for parameterised transforms
    if t_type in _PARAMETERISED_TRANSFORMS:
        for required_key in _PARAMETERISED_TRANSFORMS[t_type]:
            # Provide default for 'max_len' if missing
            if t_type == "truncate" and required_key == "max_len":
                step.setdefault("max_len", 300)
            elif required_key not in step:
                raise BlueprintValidationError(
                    f"Transform '{t_type}' on field '{field_name}' "
                    f"requires parameter '{required_key}'."
                )
    # No-config transforms must not carry extra params (soft warning skipped — not enforced)


def _validate_transform_pipeline(
    pipeline: List[Dict[str, Any]], field_name: str
) -> None:
    for step in pipeline:
        _validate_transform_step(step, field_name)


def _validate_field_dict(field_name: str, field_def: Dict[str, Any]) -> None:
    """Full validation of a manually supplied field definition."""
    for required in ("selector", "type", "export_type"):
        if required not in field_def:
            raise BlueprintValidationError(
                f"Field '{field_name}' is missing required key '{required}'."
            )
    _validate_field_type(field_def["type"], field_name)
    _validate_export_type(field_def["export_type"], field_name)
    pipeline = field_def.get("transform", [])
    _validate_transform_pipeline(pipeline, field_name)


# ── FIELD BUILDER ─────────────────────────────────────────────────────────────

def _build_field(field_name: str, field_def: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a fully-specified field dict ready for injection into the blueprint.

    Expected keys in field_def (manual mode):
        selector    : str
        type        : "scalar" | "list"
        transform   : list of transform-step dicts  (may be [])
        export_type : "text" | "real" | "int" | "json"
    """
    return {
        "selector": field_def["selector"],
        "type": field_def["type"],
        "transform": list(field_def.get("transform", [])),
        "export_type": field_def["export_type"],
    }


def _build_field_from_profile(
    field_name: str, profile_field: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Return a fully-specified field dict resolved from a profile definition.

    Profile field schema:
        selector         : str
        type             : "scalar" | "list"
        default_transforms : list of transform-step dicts
        export_type      : "text" | "real" | "int" | "json"
    """
    return {
        "selector": profile_field["selector"],
        "type": profile_field["type"],
        "transform": list(profile_field.get("default_transforms", [])),
        "export_type": profile_field["export_type"],
    }


# ── MAIN CLASS ────────────────────────────────────────────────────────────────

class BlueprintTranslator:
    """
    Converts user input + optional profile/manual fields into a valid blueprint.

    Parameters
    ----------
    user_input : dict
        Top-level blueprint fields supplied by the user.
        Required keys:
            blueprint_id, id, target_topic, seeds, domains, scoring,
            expansion, stop_conditions
        The 'extraction' key is built by this translator; if present in
        user_input it is IGNORED in favour of the resolved extraction section.

    selected_profile : str or None
        profile_id string (e.g. "wikimd_standard").
        Required when extraction_mode == "profile".

    manual_fields : dict or None
        Mapping of field_name → field definition dict.
        Required when extraction_mode == "manual".

    extraction_mode : str
        Either "profile" or "manual".
    """

    def __init__(
        self,
        user_input: Dict[str, Any],
        selected_profile: Optional[str] = None,
        manual_fields: Optional[Dict[str, Any]] = None,
        extraction_mode: str = "profile",
        profile_field_checklist: Optional[List[str]] = None,
    ) -> None:
        self._user_input = user_input
        self._selected_profile = selected_profile
        self._manual_fields = manual_fields or {}
        self._extraction_mode = extraction_mode
        self._profile_field_checklist = profile_field_checklist  # None → all fields


    # ── PUBLIC ENTRY POINT ────────────────────────────────────────────────────

    def translate(self) -> Dict[str, Any]:

        """
        Produce and return a valid blueprint dict.

        STEP 1 — Validate top-level required fields
        STEP 2 — Resolve extraction fields (profile or manual)
        STEP 3 — Assemble blueprint (structure-preserving)
        STEP 4 — Final validation pass
        """
        self._validate_required_top_level_fields()
        extraction_fields = self._resolve_extraction_fields()
        blueprint = self._assemble_blueprint(extraction_fields)
        self._final_validation(blueprint)
        return blueprint

    # ── STEP 1 ────────────────────────────────────────────────────────────────

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
                    f"user_input is missing required top-level key '{key}'."
                )

        # Validate scoring strategy
        scoring = self._user_input["scoring"]
        if "strategy" not in scoring:
            raise BlueprintValidationError(
                "scoring section is missing 'strategy'."
            )
        _validate_strategy(scoring["strategy"])

        # Validate scoring params
        params = scoring.get("params", {})
        for pk in ("scoring_type", "model_information"):
            if pk not in params:
                raise BlueprintValidationError(
                    f"scoring.params is missing required key '{pk}'."
                )

        # Validate expansion
        expansion = self._user_input["expansion"]
        for ek in ("style", "num_descriptions", "llm_type", "llm_model"):
            if ek not in expansion:
                raise BlueprintValidationError(
                    f"expansion section is missing required key '{ek}'."
                )

        # Validate stop_conditions
        sc = self._user_input["stop_conditions"]
        for sk in ("max_nodes", "max_depth", "max_duration", "no_progress_timeout", "stop_url"):
            if sk not in sc:
                raise BlueprintValidationError(
                    f"stop_conditions is missing required key '{sk}'."
                )

    # ── STEP 2 ────────────────────────────────────────────────────────────────

    def _resolve_extraction_fields(self) -> Dict[str, Any]:
        if self._extraction_mode == "profile":
            return self._resolve_profile_fields()
        elif self._extraction_mode == "manual":
            return self._resolve_manual_fields()
        else:
            raise BlueprintValidationError(
                f"Unknown extraction_mode '{self._extraction_mode}'. "
                "Must be 'profile' or 'manual'."
            )

    def _resolve_profile_fields(self) -> Dict[str, Any]:
        """Load profile and return resolved field definitions."""
        if not self._selected_profile:
            raise BlueprintValidationError(
                "extraction_mode is 'profile' but no selected_profile was provided."
            )
        if self._selected_profile not in _PROFILE_REGISTRY:
            raise BlueprintValidationError(
                f"Profile '{self._selected_profile}' not found in registry. "
                f"Available: {list(_PROFILE_REGISTRY)}"
            )
        profile = _PROFILE_REGISTRY[self._selected_profile]
        all_fields: Dict[str, Any] = profile["fields"]

        # Apply checklist filter if provided
        if self._profile_field_checklist is not None:
            unknown = set(self._profile_field_checklist) - set(all_fields)
            if unknown:
                raise BlueprintValidationError(
                    f"Profile '{self._selected_profile}' does not contain "
                    f"field(s): {sorted(unknown)}"
                )
            all_fields = {
                k: v for k, v in all_fields.items()
                if k in self._profile_field_checklist
            }

        resolved: Dict[str, Any] = {}
        for field_name, profile_field in all_fields.items():
            resolved[field_name] = _build_field_from_profile(field_name, profile_field)
        return resolved

    def _resolve_manual_fields(self) -> Dict[str, Any]:
        """Validate and build field definitions from manually supplied data."""
        if not self._manual_fields:
            raise BlueprintValidationError(
                "extraction_mode is 'manual' but no manual_fields were provided."
            )
        resolved: Dict[str, Any] = {}
        for field_name, field_def in self._manual_fields.items():
            _validate_field_dict(field_name, field_def)
            resolved[field_name] = _build_field(field_name, field_def)
        return resolved

    # ── STEP 3 ────────────────────────────────────────────────────────────────

    def _assemble_blueprint(self, extraction_fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Assemble the final blueprint dict.
        Structure is FIXED — only values are substituted; keys/order are preserved.
        """
        ui = self._user_input

        blueprint: Dict[str, Any] = {
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
            },
        }
        return blueprint

    # ── STEP 4 ────────────────────────────────────────────────────────────────

    def _final_validation(self, blueprint: Dict[str, Any]) -> None:
        """
        Post-assembly validation pass over the complete blueprint.
        Raises BlueprintValidationError on any violation.
        """
        # Re-validate strategy (belt-and-suspenders)
        _validate_strategy(blueprint["scoring"]["strategy"])

        # Validate every field in extraction
        for field_name, field_def in blueprint["extraction"]["fields"].items():
            _validate_export_type(field_def.get("export_type", ""), field_name)
            _validate_field_type(field_def.get("type", ""), field_name)
            _validate_transform_pipeline(field_def.get("transform", []), field_name)

        # Validate seeds structure
        for i, seed in enumerate(blueprint["seeds"]):
            for sk in ("url", "domain"):
                if sk not in seed:
                    raise BlueprintValidationError(
                        f"seeds[{i}] is missing required key '{sk}'."
                    )

        # Validate domains structure
        for domain_name, domain_cfg in blueprint["domains"].items():
            for dk in ("base_url", "link_selector"):
                if dk not in domain_cfg:
                    raise BlueprintValidationError(
                        f"domains['{domain_name}'] is missing required key '{dk}'."
                    )


# ── CONVENIENCE FACTORY ───────────────────────────────────────────────────────

def translate_blueprint(
    user_input: Dict[str, Any],
    selected_profile: Optional[str] = None,
    manual_fields: Optional[Dict[str, Any]] = None,
    extraction_mode: str = "profile",
    profile_field_checklist: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Convenience wrapper around BlueprintTranslator.translate().

    Returns
    -------
    dict
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


# ── USAGE EXAMPLES ────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # ── EXAMPLE 1: Profile Mode ───────────────────────────────────────────────
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
                "link_selector": ".//a[starts-with(@href, '/wiki/') and not(contains(@href, ':')) and not(contains(@href, 'Main_Page'))]",
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

    # ── EXAMPLE 2: Manual Mode ────────────────────────────────────────────────
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
