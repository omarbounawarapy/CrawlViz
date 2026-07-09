import asyncio
import json
import logging
import time

from config import BASE_DIR

logger = logging.getLogger(__name__)


class KeyManager:
    """Rotates API keys per LLM provider, skipping keys still in cooldown.

    Keys are loaded from ``keys.json`` at the repo root (see
    ``keys.example.json`` for the expected shape). That file holds
    secrets and is gitignored -- it is never committed.
    """

    def __init__(self, cooldown: float = 0):
        self.registry = self.load_keys()
        self.cooldown = cooldown
        self.indexes = {p: 0 for p in self.registry}
        self.timestamps = {
            p: {k: 0 for k in self.registry[p]} for p in self.registry
        }
        self.lock = asyncio.Lock()

    async def next_key(self, provider_name: str) -> str | None:
        """Return the next key due for `provider_name`, or None if it has no keys.

        Cycles through the provider's keys in order, skipping any still
        within `cooldown` seconds of its last use. Falls back to the
        least-recently-used key if every key is still cooling down.
        """
        async with self.lock:
            keys = self.registry.get(provider_name, [])
            if not keys:
                return None

            start_idx = self.indexes[provider_name]
            n = len(keys)
            now = time.time()

            for _ in range(n):
                key = keys[self.indexes[provider_name]]
                self.indexes[provider_name] = (self.indexes[provider_name] + 1) % n
                if now - self.timestamps[provider_name][key] >= self.cooldown:
                    self.timestamps[provider_name][key] = now
                    return key

            return keys[start_idx]

    def load_keys(self) -> dict:
        """Read and validate ``keys.json``.

        Returns:
            The parsed ``{provider: [key, ...]}`` registry.

        Raises:
            FileNotFoundError: If ``keys.json`` does not exist at the repo root.
            ValueError: If the file's contents don't match the expected shape.
        """
        file_path = BASE_DIR / "keys.json"

        if not file_path.exists():
            raise FileNotFoundError(
                f"API keys file not found: {file_path!r}. Copy keys.example.json "
                "to keys.json and fill in your provider API keys."
            )

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("Invalid JSON format: root must be an object")

        for provider, keys in data.items():
            if not isinstance(keys, list):
                raise ValueError(f"Keys for '{provider}' must be a list")
            if not all(isinstance(k, str) for k in keys):
                raise ValueError(f"All keys for '{provider}' must be strings")

        logger.info(
            "Loaded API keys for providers: %s", ", ".join(sorted(data.keys()))
        )
        return data
