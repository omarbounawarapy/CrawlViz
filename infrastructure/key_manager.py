import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path

from config import BASE_DIR

logger = logging.getLogger(__name__)


class KeyManager:
    """Rotates API keys per LLM provider, skipping keys still in cooldown.

    Keys are loaded from ``keys.json`` at the repo root (see
    ``keys.example.json`` for the expected shape). That file holds
    secrets and is gitignored -- it is never committed.
    """

    def __init__(self, cooldown: float = 0, keys_file=None):
        self.keys_file = keys_file if keys_file is not None else BASE_DIR / "keys.json"
        self.registry = self.load_keys()
        self.cooldown = cooldown
        self.indexes = {p: 0 for p in self.registry}
        self.timestamps = {p: {k: 0 for k in self.registry[p]} for p in self.registry}
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

    async def mark_invalid(self, provider_name: str, key: str | None) -> bool:
        """Drop a rejected (401/403) key from `provider_name`'s rotation.

        Returns True if another key remains to retry with. The last
        remaining key is never dropped, so a provider always keeps one.
        """
        async with self.lock:
            keys = self.registry.get(provider_name, [])
            if key not in keys or len(keys) <= 1:
                return False
            keys.remove(key)
            self.indexes[provider_name] %= len(keys)
            logger.warning(
                "Dropped rejected API key for '%s'; %d key(s) left",
                provider_name,
                len(keys),
            )
            return True

    @staticmethod
    def fingerprint(key: str) -> str:
        """Stable short id for a key that does not reveal it."""
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

    def snapshot(self) -> dict[str, list[dict]]:
        """Masked view for the UI: ``{provider: [{id, last4, last_used}]}``.
        Full keys never leave this object."""
        out: dict[str, list[dict]] = {}
        for provider, keys in self.registry.items():
            out[provider] = [
                {
                    "id": self.fingerprint(k),
                    "last4": k[-4:] if len(k) >= 8 else "****",
                    "last_used": self.timestamps.get(provider, {}).get(k) or None,
                }
                for k in keys
            ]
        return out

    def add_key(self, provider: str, key: str) -> str:
        """Add `key` to `provider` and persist; returns its id. Re-adding
        an existing key is a no-op."""
        key = key.strip()
        if not key:
            raise ValueError("key must not be empty")
        keys = self.registry.setdefault(provider, [])
        self.indexes.setdefault(provider, 0)
        self.timestamps.setdefault(provider, {})
        if key not in keys:
            keys.append(key)
            self.timestamps[provider][key] = 0
            self.save()
        return self.fingerprint(key)

    def remove_key(self, provider: str, key_id: str) -> bool:
        """Remove the key with id `key_id`; returns whether one was removed.
        Unlike mark_invalid this may remove a provider's last key."""
        keys = self.registry.get(provider, [])
        match = next((k for k in keys if self.fingerprint(k) == key_id), None)
        if match is None:
            return False
        keys.remove(match)
        self.timestamps.get(provider, {}).pop(match, None)
        self.indexes[provider] = self.indexes.get(provider, 0) % len(keys) if keys else 0
        if not keys:
            del self.registry[provider]
            self.indexes.pop(provider, None)
            self.timestamps.pop(provider, None)
        self.save()
        return True

    def reload(self) -> None:
        """Re-read ``keys_file`` into the running registry, keeping rotation
        position and cooldown timestamps of keys that are still present, so
        keys added or removed from the UI reach a crawl in progress."""
        fresh = self.load_keys()
        for provider in list(self.registry):
            if provider not in fresh:
                del self.registry[provider]
                self.indexes.pop(provider, None)
                self.timestamps.pop(provider, None)
        for provider, keys in fresh.items():
            self.registry[provider] = list(keys)
            stamps = self.timestamps.setdefault(provider, {})
            self.timestamps[provider] = {k: stamps.get(k, 0) for k in keys}
            self.indexes[provider] = self.indexes.get(provider, 0) % len(keys) if keys else 0

    def save(self) -> None:
        """Atomically write the registry back to ``keys_file`` (0600)."""
        path = Path(self.keys_file)
        tmp = path.with_suffix(path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.registry, f, indent=2)
        os.replace(tmp, path)

    def load_keys(self) -> dict:
        """Read and validate ``keys.json``.

        Returns:
            The parsed ``{provider: [key, ...]}`` registry.

        Raises:
            FileNotFoundError: If ``keys.json`` does not exist at the repo root.
            ValueError: If the file's contents don't match the expected shape.
        """
        file_path = self.keys_file

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

        logger.info("Loaded API keys for providers: %s", ", ".join(sorted(data.keys())))
        return data
