from dataclasses import dataclass
from typing import Any, Literal

# =========================================================
# 1. NODE CREATION (GRAPH CONSTRUCTION CORE)
# =========================================================

@dataclass
class StorageNodeCreatedEvent:
    correlation_id: str
    node_id: str
    parent_id: str
    url: str
    llm_score: float
    priority: float


# =========================================================
# 2. NODE INSERTION INTO STORAGE
# =========================================================

@dataclass
class StorageNodeAddedEvent:
    correlation_id: str
    node: Any


# =========================================================
# 3. NODE STATE UPDATE
# =========================================================

@dataclass
class StorageNodeUpdatedEvent:
    correlation_id: str
    node: Any
    links: list[Any]
    items: list[Any]


# =========================================================
# 4. ITEM PERSISTENCE TRACE
# =========================================================

@dataclass
class StorageItemStoredEvent:
    correlation_id: str
    node_id: str
    item_hash: str


# =========================================================
# 5. LINK PERSISTENCE TRACE
# =========================================================

@dataclass
class StorageLinkStoredEvent:
    correlation_id: str
    node_id: str
    links_count: int


# =========================================================
# 6. GLOBAL NODE ADDITION (DOWNSTREAM COMPATIBILITY)
# =========================================================

@dataclass
class NodeAddedEvent:
    correlation_id: str
    node: Any


# =========================================================
# 7. FAILURE (STRICT DEBUG CONTEXT)
# =========================================================

@dataclass
class StorageOperationFailedEvent:
    correlation_id: str | None
    stage: Literal["WORKER"]
    error_type: str
    error_message: str


# =========================================================
# 8. NODE CONTENT UPDATE
# =========================================================

@dataclass
class NodeContentSetEvent:
    correlation_id: str | None
    node: Any
    content: str
