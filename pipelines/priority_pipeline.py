import asyncio
from typing import Any

from events import (
    HighScoreLinksEvent,
    LinksScoredEvent,
    PriorityCalculatedEvent,
    PriorityCalculationFailedEvent,
    PriorityCalculationStartedEvent,
    PriorityInputSnapshotEvent,
)
from models import Node
from priority import StrategyFn, get_strategy


class PriorityPipeline:
    """Computes a priority float for every scored link.

    Architecture rules enforced here:
        - Strategy is injected at init -- no runtime branching.
        - Strategy is a pure function: (node, link, nlp_bias, llm_bias) -> float.
        - No LLM calls, no embedding computation.
        - Input: LinksScoredEvent (links already have nlp_vector + score).
        - Output: PriorityCalculatedEvent (links have priority added).
    """

    def __init__(
        self,
        storage,
        event_broker,
        nlp_bias: float = 60,
        llm_bias: float = 40,
        strategy_name: str = "balanced",
        max_queue_size: int = 0,
        max_concurrency: int = 10,
    ):
        self.event_broker = event_broker
        self.storage = storage
        self.max_concurrency = max_concurrency
        self.nlp_bias = nlp_bias
        self.llm_bias = llm_bias
        # Strategy resolution fails fast at init, not at crawl time.
        self.strategy_name = strategy_name
        self.strategy: StrategyFn = get_strategy(strategy_name)

        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self.workers: list = []

        self.handlers = {
            LinksScoredEvent: self._on_links_scored,
            HighScoreLinksEvent: self._on_links_scored,
        }

    # =========================================================
    # LIFECYCLE
    # =========================================================

    async def start(self) -> None:
        self.workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self.max_concurrency)
        ]
        await asyncio.gather(*self.workers)

    # =========================================================
    # ENTRY POINT (CALLED BY EVENTBROKER)
    # =========================================================

    async def put(self, event: LinksScoredEvent) -> None:
        await self.handlers[type(event)](event)

    # =========================================================
    # HANDLER -- INGESTION + OBSERVABILITY TRACE
    # =========================================================

    async def _on_links_scored(self, event: LinksScoredEvent) -> None:
        links = getattr(event, "scored_links", None) or getattr(event, "links", None)
        await self.event_broker.emit(
            PriorityInputSnapshotEvent(
                correlation_id=str(event.node.get_id()),
                node_id=str(event.node.get_id()),
                scored_links_count=len(links),
            )
        )
        await self.queue.put((event.node, links))

    # =========================================================
    # WORKER
    # =========================================================

    async def _worker(self, worker_id: int) -> None:
        while self.event_broker.running:
            node, links = await self.queue.get()

            try:
                await self.event_broker.emit(
                    PriorityCalculationStartedEvent(
                        correlation_id=str(node.get_id()),
                        worker_id=worker_id,
                        node_id=str(node.get_id()),
                        input_links_count=len(links),
                    )
                )

                calculated = self._compute_priorities(node, links)

                await self.event_broker.emit(
                    PriorityCalculatedEvent(
                        correlation_id=str(node.get_id()),
                        parent=node,
                        links=calculated,
                        output_count=len(calculated),
                    )
                )

            except Exception as e:
                await self.event_broker.emit(
                    PriorityCalculationFailedEvent(
                        correlation_id=str(node.get_id()),
                        node=node,
                        stage="PRIORITY_COMPUTATION",
                        error_type=type(e).__name__,
                        error_message=str(e),
                        input_links_count=len(links),
                    )
                )

            finally:
                self.queue.task_done()

    # =========================================================
    # PRIORITY COMPUTATION -- PURE, NO SIDE EFFECTS
    # =========================================================

    def _compute_priorities(self, node: Node, links: list) -> list[dict[str, Any]]:
        """Apply `self.strategy` to every link.

        Returns:
            A list of ``{"link": Link, "score": int, "priority": float}`` dicts.
        """
        results = []
        for link in links:
            llm = getattr(link, "score", None)
            if llm:
                priority = self.strategy(node, link, self.nlp_bias, self.llm_bias)
            else:
                priority = self.strategy(node, link, 1, 0)

            results.append({
                "link": link,
                "score": getattr(link, "score", 0) or 0,
                "priority": priority,
            })
        return results
