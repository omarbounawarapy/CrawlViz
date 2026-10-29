"""LLM wrappers for the benchmark. All satisfy ``send(context)`` like ``LlmHandler``.

``CachedLlm`` is a disk cache keyed on scope, provider, model, prompt version,
graph SHA-256 and prompt. A
``scope`` separates independent realizations of the same prompt: the cascade
gives every repeat its own scope, so repeat 1 makes live calls instead of
replaying repeat 0, and a later rerun replays each repeat's own answers. The
judge uses no scope (its key is the original one): its labels are frozen once.
With ``replay_only`` a cache miss raises ``ReplayMiss`` and the inner handler
is never called.

``PacedLlm`` keeps live calls under the provider's token-per-minute cap and
waits out 429s, so rate limiting (infrastructure) is not mistaken for scoring
failures (system behavior). It changes wall-clock only, never an answer. It
also records each live call's latency and the time spent waiting, which is the
performance side of the benchmark (the page sequence never depends on it).
"""

import asyncio
import hashlib
import json
import time
from collections import deque
from pathlib import Path

import aiohttp


class ReplayMiss(RuntimeError):
    """A replay-only run needed an LLM answer that was not recorded."""


class CachedLlm:
    def __init__(
        self,
        inner,
        path: Path,
        scope: str = "",
        replay_only: bool = False,
        prompt_version: str = "",
        graph_sha: str = "",
    ):
        self.inner = inner
        self.scope = scope
        self.prompt_version = prompt_version
        self.graph_sha = graph_sha
        self.replay_only = replay_only
        self.path = Path(path)
        self.hits = self.misses = 0
        self.input_tokens = self.output_tokens = (
            0  # tokens behind every answer served, replayed ones included
        )
        self.replay_misses: list[str] = []
        self.miss_prompts: list[
            str
        ] = []  # prompt text of each miss, for diagnosing a diverged replay
        # Answers per key in the order they were given. The same prompt can
        # be answered more than once (an empty answer, then its retry), and a
        # replay must hand them out in that order or the retry logic runs on
        # different input and the visit order drifts.
        self._cache: dict[str, list[dict]] = {}
        self._usage: dict[str, list[tuple[int, int]]] = {}
        self._served: dict[str, int] = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                entry = json.loads(line)
                self._cache.setdefault(entry["key"], []).append(entry["result"])
                self._usage.setdefault(entry["key"], []).append(tuple(entry.get("usage", (0, 0))))

    def key(self, context) -> str:
        raw = f"{context.get_llm_type()}\0{context.get_model_information()}\0{context.get_prompt()}"
        if self.prompt_version or self.graph_sha:
            raw = f"{self.prompt_version}\0{self.graph_sha}\0{raw}"
        if self.scope:  # no scope keeps the original key, so the judge cache stays valid
            raw = f"{self.scope}\0{raw}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @property
    def waiting(self) -> bool:
        """The wrapped handler is asleep on a rate limit (see PacedLlm)."""
        return bool(getattr(self.inner, "waiting", False))

    def _add_usage(self, usage) -> None:
        self.input_tokens += usage[0]
        self.output_tokens += usage[1]

    async def send(self, context) -> dict:
        key = self.key(context)
        n = self._served.get(key, 0)
        recorded = self._cache.get(key, [])
        # Past the last answer a repeat gets that answer again, unless it was
        # empty: then a live run asks the model again (the retry).
        if n < len(recorded) or (recorded and (self.replay_only or recorded[-1])):
            self.hits += 1
            self._served[key] = n + 1
            i = min(n, len(recorded) - 1)  # past the last answer: repeat it
            self._add_usage(self._usage[key][i])
            return json.loads(json.dumps(self._cache[key][i]))
        if self.replay_only:
            # The pipeline may swallow this exception, so it is also recorded
            # here and checked by the caller after the run.
            self.replay_misses.append(key)
            self.miss_prompts.append(context.get_prompt())
            raise ReplayMiss(
                f"scope {self.scope!r}: no recorded answer for {context.get_prompt()[:80]!r}"
            )
        result = await self.inner.send(context)
        self.misses += 1
        usage = context.get_usage() if hasattr(context, "get_usage") else (0, 0)
        self._add_usage(usage)
        # An empty answer is recorded too: the pipeline reschedules it, and a
        # replay that skipped it would never run that retry.
        self._cache.setdefault(key, []).append(result or {})
        self._usage.setdefault(key, []).append(tuple(usage))
        self._served[key] = len(self._cache[key])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "key": key,
                        "result": result or {},
                        "usage": list(usage),
                        "prompt": context.get_prompt(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        return result


class PacedLlm:
    """Sliding one-minute token budget plus bounded 429 retries."""

    def __init__(self, inner, tokens_per_minute: int = 5500, max_429_waits: int = 8):
        self.inner = inner
        self.client = inner.client
        self.budget = tokens_per_minute
        self.max_429_waits = max_429_waits
        self.rate_limit_waits = 0
        self.latencies: list[float] = []  # seconds per live call that returned
        self.wait_seconds = 0.0  # pacing and 429 sleeps, kept out of latencies
        self.rate_limit_seconds = 0.0  # the 429 part of wait_seconds
        self._sleeping = 0  # sleeps in progress (pacing or 429)
        self._window: deque[tuple[float, float]] = deque()

    @staticmethod
    def estimate(context) -> float:
        # Prompt tokens plus room for the answer (reasoning tokens count too).
        return len(context.get_prompt()) / 3.5 + 600

    @property
    def waiting(self) -> bool:
        """True while a call is asleep on pacing or a 429 back-off."""
        return self._sleeping > 0

    async def _sleep(self, seconds: float) -> None:
        self._sleeping += 1
        try:
            await asyncio.sleep(seconds)
        finally:
            self._sleeping -= 1

    async def _wait_for_room(self, cost: float) -> None:
        while True:
            now = time.monotonic()
            while self._window and now - self._window[0][0] > 60:
                self._window.popleft()
            if sum(c for _, c in self._window) + cost <= self.budget or not self._window:
                self._window.append((now, cost))
                return
            pause = max(0.5, 60 - (now - self._window[0][0]))
            self.wait_seconds += pause
            await self._sleep(pause)

    async def send(self, context) -> dict:
        await self._wait_for_room(self.estimate(context))
        for attempt in range(self.max_429_waits + 1):
            started = time.monotonic()
            try:
                result = await self.inner.send(context)
                self.latencies.append(time.monotonic() - started)
                return result
            except aiohttp.ClientResponseError as e:
                if e.status != 429 or attempt == self.max_429_waits:
                    raise
                self.rate_limit_waits += 1
                pause = 15 * (attempt + 1)
                self.wait_seconds += pause
                self.rate_limit_seconds += pause
                await self._sleep(pause)
