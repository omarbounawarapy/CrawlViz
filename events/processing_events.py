from dataclasses import dataclass
from typing import Any, List


# =========================================================
# 1. INPUT SNAPSHOT
# =========================================================

@dataclass
class ExtractionInputSnapshotEvent:
    correlation_id: str
    node_id: str
    content_size: int


# =========================================================
# 2. START OF EXTRACTION
# =========================================================

@dataclass
class ExtractionStartedEvent:
    worker_id: int
    correlation_id: str
    node_id: str
    content_size: int


# =========================================================
# 3. LINK EXTRACTION STAGE
# =========================================================

@dataclass
class LinkExtractionCompletedEvent:
    correlation_id: str
    node_id: str
    extracted_links_count: int


# =========================================================
# 4. ITEM EXTRACTION STAGE
# =========================================================

@dataclass
class ItemExtractionCompletedEvent:
    correlation_id: str
    node_id: str
    extracted_items_count: int


# =========================================================
# 5. FINAL OUTPUT EVENT (DOWNSTREAM INPUT)
# =========================================================

@dataclass
class ContentExtractedEvent:
    correlation_id: str
    node: Any
    links: List[str]
    items: List[Any]


# =========================================================
# 6. FAILURE EVENT (STRICT DEBUG CONTEXT)
# =========================================================

@dataclass
class ProcessingExtractionFailedEvent:
    correlation_id: str
    node: Any

    stage: str  # "EXTRACTION"

    error_type: str
    error_message: str


# =========================================================
# 7. OPTIONAL DEBUG / FUTURE-GUI ENHANCEMENT
# =========================================================

@dataclass
class LinkResolvedEvent:
    """
    Optional fine-grained observability event.
    Useful if you want per-link animation in GUI.
    """
    correlation_id: str
    node_id: str

    original_link: str
    resolved_link: str


@dataclass
class ItemFieldExtractedEvent:
    """
    Optional fine-grained observability event.
    Useful for debugging selectors or blueprint issues.
    """
    correlation_id: str
    node_id: str

    field_name: str
    extracted_value: Any