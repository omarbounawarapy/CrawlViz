from dataclasses import dataclass

# =========================================================
# NLP PIPELINE TRACE EVENTS
# =========================================================

@dataclass
class NLP_InputReceived:
    trace_id: str
    node_id: str
    link_url: str
    anchor_preview: str          # first 80 chars
    context_preview: str         # first 120 chars
    parent_content_len: int
    space_size: int


@dataclass
class NLP_FeaturesExtracted:
    trace_id: str
    node_id: str
    link_url: str
    features: dict[str, float]   # full feature dict from extract_all()
    embedding_dim: int
    space_size: int
    cluster_count: int


@dataclass
class NLP_SimilarityScored:
    trace_id: str
    node_id: str
    link_url: str
    target_similarity: float
    contextual_consistency: float
    novelty_injection: float
    region_density: float
    cluster_distance: float
    coverage_gap: float


@dataclass
class NLP_VectorComposed:
    trace_id: str
    node_id: str
    link_url: str
    weights_used: dict[str, float]
    weighted_contributions: dict[str, float]
    raw_sum: float
    final_score: float           # after clamp to [0, 1]


@dataclass
class NLP_ScoreEmitted:
    trace_id: str
    node_id: str
    link_url: str
    nlp_score: float
    space_version: int
