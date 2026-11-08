"""A site script: the data that turns the frozen-site double into a long demo site.

A script is a JSON file in ``offline/scripts/`` named after the blueprint it serves
(``offline_demo_long.json`` serves the blueprint ``offline_demo_long.json``). It holds:

* ``site``: the size of a synthetic site (``benchmark.graph.synthetic_graph``);
* ``rate_limit_episodes``: when the site starts answering 429 Too Many Requests, and how
  many requests it turns away before it recovers;
* ``config``: settings that slow the crawl and shrink its LLM call budget so it runs out,
  as a partial ``RuntimeConfig`` (the shape of the ``overrides`` of ``POST /run``).

Episodes count fetched pages, not seconds, so the same script gives the same episodes
on every machine.
"""

import random
from collections import deque
from pathlib import Path
from typing import Any, Literal

import aiohttp
from pydantic import BaseModel, ConfigDict, Field
from yarl import URL

from benchmark.graph import GENERIC_TERMS, TOPIC_TERMS, FrozenGraph, GraphFetcher, synthetic_graph
from config.runtime_config import RuntimeConfig, default_runtime_config
from config.settings_store import deep_merge, diff

TOO_MANY_REQUESTS = 429
PAGE_TEXT_WORDS = 12


class SiteSpec(BaseModel):
    """The shape of the synthetic site (see ``synthetic_graph``)."""

    model_config = ConfigDict(extra="forbid")

    n_pages: int = Field(ge=2)
    out_degree: int = Field(ge=1)
    relevant_fraction: float = Field(gt=0, lt=1)
    seed: int


class RateLimitEpisode(BaseModel):
    """After ``after_fetches`` pages, the site answers 429 to ``rejected_requests`` requests."""

    model_config = ConfigDict(extra="forbid")

    after_fetches: int = Field(ge=0)
    rejected_requests: int = Field(ge=1)


class SiteScript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    site: SiteSpec
    rate_limit_episodes: list[RateLimitEpisode]
    # Any: a partial RuntimeConfig, so the keys are the config's own; validated when applied.
    config: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "SiteScript":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def build_fetcher(self) -> "RateLimitedFetcher":
        return RateLimitedFetcher(self._build_graph().fetcher(), self.rate_limit_episodes)

    def apply_config(self, config: RuntimeConfig) -> RuntimeConfig:
        """``config`` with the script's settings underneath: anything the caller already
        changed from the defaults (a saved setting, a run override) wins."""
        defaults = default_runtime_config().model_dump()
        changed_by_caller = diff(defaults, config.model_dump())
        return RuntimeConfig.model_validate(
            deep_merge(deep_merge(defaults, self.config), changed_by_caller)
        )

    def _build_graph(self) -> FrozenGraph:
        site = self.site
        graph = synthetic_graph(
            n_pages=site.n_pages,
            out_degree=site.out_degree,
            relevant_fraction=site.relevant_fraction,
            seed=site.seed,
        )
        # Pages with text are served in the markup the blueprint's extraction expects.
        rng = random.Random(f"site-text:{site.seed}")
        for name, page in graph.pages.items():
            terms = TOPIC_TERMS if page["relevant"] else GENERIC_TERMS
            page["title"] = name
            page["text"] = " ".join(rng.choices(terms, k=PAGE_TEXT_WORDS))
        return graph


class RateLimitedFetcher:
    """A ``GraphFetcher`` that turns requests away with 429 during the scripted episodes."""

    def __init__(self, inner: GraphFetcher, episodes: list[RateLimitEpisode]):
        self._inner = inner
        self._upcoming = deque(sorted(episodes, key=lambda episode: episode.after_fetches))
        self._rejections_left = 0  # of the episode under way
        self.rate_limited = 0  # requests answered with 429 so far

    @property
    def fetched(self) -> list[str]:
        return self._inner.fetched

    async def emit_request(self, params: dict[str, Any]) -> str:  # Any: the Fetcher protocol
        if self._turns_away():
            self.rate_limited += 1
            raise _too_many_requests(params["url"])
        return await self._inner.emit_request(params)

    async def close(self) -> None:
        await self._inner.close()

    def _turns_away(self) -> bool:
        episode_due = bool(self._upcoming) and len(self.fetched) >= self._upcoming[0].after_fetches
        if not self._rejections_left and episode_due:
            self._rejections_left = self._upcoming.popleft().rejected_requests
        if not self._rejections_left:
            return False
        self._rejections_left -= 1
        return True


def _too_many_requests(url: str) -> aiohttp.ClientResponseError:
    """The error ``RequestsPipeline`` recognises as a rate limit (``is_rate_limited``)."""
    address = URL(url)
    request_info = aiohttp.RequestInfo(address, "GET", {}, address)  # type: ignore[arg-type]
    return aiohttp.ClientResponseError(
        request_info, (), status=TOO_MANY_REQUESTS, message="Too Many Requests"
    )
