from dataclasses import dataclass
from typing import Literal

# =========================================================
# EXPANSION BOOTSTRAP TRACE EVENTS
# =========================================================

@dataclass
class EXP_Triggered:
    trace_id: str
    node_id: str
    blueprint_id: str
    target_topic: str
    trigger_reason: Literal["new_blueprint", "cache_miss", "forced"]


@dataclass
class EXP_PromptBuilt:
    trace_id: str
    node_id: str
    blueprint_id: str
    style: Literal["concise", "balanced", "rich"]
    num_descriptions: int
    prompt_len: int
    prompt_preview: str          # first 300 chars


@dataclass
class EXP_SeedsGenerated:
    trace_id: str
    node_id: str
    blueprint_id: str
    seed_count: int
    seed_previews: list[str]     # first 80 chars of each description
    source: Literal["llm_expansion"]


@dataclass
class EXP_CandidateScored:
    trace_id: str
    node_id: str
    blueprint_id: str
    seed_preview: str
    target_similarity: float
    space_size_before: int


@dataclass
class EXP_CandidatePruned:
    trace_id: str
    node_id: str
    blueprint_id: str
    seed_preview: str
    reason: Literal["below_threshold", "duplicate", "error"]
    threshold: float | None


@dataclass
class EXP_SpaceBootstrapped:
    trace_id: str
    node_id: str
    blueprint_id: str
    vectors_added: int
    space_version: int
    duration_ms: float
