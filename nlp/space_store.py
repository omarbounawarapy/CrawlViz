import json
import re
from datetime import datetime
from pathlib import Path

from .vector_space import VectorSpace


class SpaceStore:
    """Manages the filesystem layout for VectorSpace persistence.

    Supports versioning: each saved space gets a timestamped snapshot
    alongside the canonical "latest" copy.
    """

    def __init__(self, base_dir: str = ".space_store", model_name: str = ""):
        self.model_name = model_name
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.base_dir / "index.json"
        self._index: dict = self._load_index()

    # =========================================================
    # PATH RESOLUTION
    # =========================================================

    def _dir(self, blueprint_id: str) -> Path:
        """A space is only valid for the embedding model that produced it."""
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", self.model_name) or "default"
        return self.base_dir / blueprint_id / slug

    def _key(self, blueprint_id: str) -> str:
        return f"{blueprint_id}::{self.model_name}"

    def space_path(self, blueprint_id: str) -> str:
        """Return the canonical (latest) base path for a blueprint's space
        (``.npz`` and ``.json`` are appended by VectorSpace)."""
        return str(self._dir(blueprint_id) / "latest")

    def snapshot_path(self, blueprint_id: str) -> str:
        """Return a fresh timestamped snapshot path."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_dir = self._dir(blueprint_id) / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        return str(snap_dir / f"space_{ts}")

    def exists(self, blueprint_id: str) -> bool:
        return VectorSpace.exists(self.space_path(blueprint_id))

    # =========================================================
    # INDEX (LIGHTWEIGHT METADATA)
    # =========================================================

    def _load_index(self) -> dict:
        if self._index_path.exists():
            with open(self._index_path) as f:
                return json.load(f)
        return {}

    def _save_index(self) -> None:
        with open(self._index_path, "w") as f:
            json.dump(self._index, f, indent=2)

    def record_save(self, blueprint_id: str, n_vectors: int, version: int) -> None:
        self._index[self._key(blueprint_id)] = {
            "blueprint_id": blueprint_id,
            "model_name": self.model_name,
            "n_vectors": n_vectors,
            "version": version,
            "saved_at": datetime.now().isoformat(),
        }
        self._save_index()

    def get_metadata(self, blueprint_id: str) -> dict | None:
        return self._index.get(self._key(blueprint_id))

    def list_spaces(self) -> list[str]:
        return list(self._index.keys())
