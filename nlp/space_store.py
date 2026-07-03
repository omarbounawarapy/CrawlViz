import json
from pathlib import Path
from datetime import datetime
from typing import Optional


class SpaceStore:
    """
    Manages file-system layout for VectorSpace persistence.
    Supports versioning: each saved space gets a timestamped snapshot.
    """

    def __init__(self, base_dir: str = ".space_store"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.base_dir / "index.json"
        self._index: dict = self._load_index()

    # =========================================================
    # PATH RESOLUTION
    # =========================================================

    def space_path(self, blueprint_id: str) -> str:
        """Returns the canonical (latest) path for a blueprint's space."""
        return str(self.base_dir / blueprint_id / "latest.pkl")

    def snapshot_path(self, blueprint_id: str) -> str:
        """Returns a timestamped snapshot path."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_dir = self.base_dir / blueprint_id / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        return str(snap_dir / f"space_{ts}.pkl")

    def exists(self, blueprint_id: str) -> bool:
        return Path(self.space_path(blueprint_id)).exists()

    # =========================================================
    # INDEX (lightweight metadata)
    # =========================================================

    def _load_index(self) -> dict:
        if self._index_path.exists():
            with open(self._index_path, "r") as f:
                return json.load(f)
        return {}

    def _save_index(self) -> None:
        with open(self._index_path, "w") as f:
            json.dump(self._index, f, indent=2)

    def record_save(self, blueprint_id: str, n_vectors: int, version: int) -> None:
        self._index[blueprint_id] = {
            "blueprint_id": blueprint_id,
            "n_vectors": n_vectors,
            "version": version,
            "saved_at": datetime.now().isoformat(),
        }
        self._save_index()

    def get_metadata(self, blueprint_id: str) -> Optional[dict]:
        return self._index.get(blueprint_id)

    def list_spaces(self) -> list:
        return list(self._index.keys())