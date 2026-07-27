import asyncio
import logging
from random import sample

from events import (
    EmptyScoreResultsEvent,
    HighScoreLinksEvent,
    LinksScoredEvent,
    LowScoreLinksEvent,
    NoLinksToScoreEvent,
    NodeAddedEvent,
    ScoreRescheduledEvent,
    ScoringCompletedEvent,
    ScoringEnqueuedEvent,
    ScoringFailedEvent,
    ScoringInputSnapshotEvent,
    ScoringStartedEvent,
)

logger = logging.getLogger(__name__)


class ScoringPipeline:
    """Runs the two-stage NLP -> LLM relevance cascade for a node's links.

    Every link gets a cheap NLP similarity score first (report section
    0.13, "Evaluation multi-etapes"). ``bucket_links`` then decides,
    per score bucket, which links are worth the more expensive LLM call
    and which can be trusted or dropped outright.
    """

    def __init__(
        self,
        scoring_service,
        nlp_service,
        event_broker,
        low_threshold,
        high_threshold,
        high_score_llm_fraction,
        low_score_sample_fraction,
        high_score_random_fraction,
        max_queue_size=0,
        max_concurrency=1,
    ):
        self.event_broker = event_broker
        self.scoring_service = scoring_service
        self.nlp_service = nlp_service
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.high_score_llm_fraction = high_score_llm_fraction
        self.low_score_sample_fraction = low_score_sample_fraction
        self.high_score_random_fraction = high_score_random_fraction
        self.queue = asyncio.PriorityQueue(maxsize=max_queue_size)
        self.max_concurrency = max_concurrency
        self.workers = []

        self.handlers = {
            NodeAddedEvent: self._on_node_added,
            ScoreRescheduledEvent: self._on_node_added,
        }

    # =========================================================
    # START
    # =========================================================
    async def start(self) -> None:
        self.workers = [
            asyncio.create_task(self.worker(i))
            for i in range(self.max_concurrency)
        ]
        await asyncio.gather(*self.workers)

    # =========================================================
    # ENTRY POINT
    # =========================================================
    async def put(self, event: NodeAddedEvent) -> None:
        await self.handlers[type(event)](event)

    # =========================================================
    # HANDLER (ENQUEUE TRACE)
    # =========================================================
    async def _on_node_added(self, event: NodeAddedEvent) -> None:
        await self.event_broker.emit(
            ScoringEnqueuedEvent(
                correlation_id=str(event.node.get_id()),
                node_id=str(event.node.get_id()),
                queue_size=self.queue.qsize(),
            )
        )

        await self.queue.put(event.node)

    # =========================================================
    # WORKER (FULL DECISION TRACE)
    # =========================================================
    async def worker(self, worker_id: int) -> None:
        while True:
            if not self.event_broker.running:
                logger.debug("Scoring worker %s exiting: broker stopped", worker_id)
                break

            node = await self.queue.get()

            try:
                await node.ready

                # Input snapshot
                await self.event_broker.emit(
                    ScoringInputSnapshotEvent(
                        correlation_id=str(node.get_id()),
                        node_id=str(node.get_id()),
                        ready_state=True,
                    )
                )

                links = node.get_links()

                if not links:
                    await self.event_broker.emit(
                        NoLinksToScoreEvent(
                            correlation_id=str(node.get_id()),
                            node=node,
                        )
                    )
                else:
                    await self.event_broker.emit(
                        ScoringStartedEvent(
                            correlation_id=str(node.get_id()),
                            worker_id=worker_id,
                            node_id=str(node.get_id()),
                        )
                    )

                    # NLP scoring always runs first, on every link.
                    await self.nlp_service.score_links(
                        links=links,
                        parent=node,
                    )

                    sampled, llm_skip, drop = self.bucket_links(links)
                    logger.debug(
                        "Node %s: %d sampled, %d high-confidence, %d dropped",
                        node.get_id(), len(sampled), len(llm_skip), len(drop),
                    )

                    await self.event_broker.emit(
                        HighScoreLinksEvent(
                            correlation_id=str(node.get_id()),
                            node=node,
                            links=llm_skip,
                        )
                    )
                    await self.event_broker.emit(
                        LowScoreLinksEvent(
                            correlation_id=str(node.get_id()),
                            node=node,
                            links=drop,
                        )
                    )

                    # Core scoring call (LLM, sampled links only).
                    if not sampled:
                        scored_links = []
                    else:
                        scored_links = await self.scoring_service.score_links(node, sampled)

                    if not scored_links:
                        await self.event_broker.emit(
                            EmptyScoreResultsEvent(
                                correlation_id=str(node.get_id()),
                                node=node,
                            )
                        )
                    else:
                        # Forward any LLM-generated expansions into the
                        # semantic space's update pipeline (see
                        # NLPService.update_space / nlp/space_updater.py).
                        await self.nlp_service.update_space(scored_links)

                    await self.event_broker.emit(
                        ScoringCompletedEvent(
                            correlation_id=str(node.get_id()),
                            node=node,
                            scored_links=scored_links,
                            output_count=len(scored_links),
                        )
                    )

                    await self.event_broker.emit(
                        LinksScoredEvent(
                            correlation_id=str(node.get_id()),
                            node=node,
                            scored_links=scored_links,
                        )
                    )

            except Exception as e:
                await self.event_broker.emit(
                    ScoringFailedEvent(
                        correlation_id=str(node.get_id()),
                        node=node,
                        stage="SCORING_SERVICE",
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
                )

            finally:
                self.queue.task_done()

    def bucket_links(self, links: list) -> tuple[list, list, list]:
        """Split scored links into low/mid/high NLP-confidence buckets,
        then decide which ones actually need an LLM call.

        - "low" links are mostly dropped, keeping a small random sample
          for exploration (report section 0.15.2's bias-correction idea).
        - "mid" links always go to the LLM (the NLP signal is ambiguous).
        - "high" links are confident enough to mostly skip the LLM; only
          a budgeted mix of top-ranked + random ones are re-checked.

        Returns:
            (sampled, skip_llm, dropped): links bound for the LLM, links
            trusted without an LLM call, and links dropped outright.
        """
        high, low, mid = [], [], []

        for link in links:
            score = link._nlp_score
            if score < self.low_threshold:
                low.append(link)
            elif score > self.high_threshold:
                high.append(link)
            else:
                mid.append(link)

        low_budget = min(int(len(low) * self.low_score_sample_fraction), len(low))
        high_budget = min(int(len(high) * self.high_score_llm_fraction), len(high))

        high_random_budget = int(high_budget * self.high_score_random_fraction)
        high_top_budget = max(high_budget - high_random_budget, 0)

        # Low bucket: keep a random sample, drop the rest.
        sampled = []
        dropped = []
        low_indices = set(sample(range(len(low)), low_budget)) if low_budget else set()
        for i, link in enumerate(low):
            (sampled if i in low_indices else dropped).append(link)

        # High bucket: split into a random slice and a top-ranked slice;
        # whatever's left over skips the LLM call entirely.
        high_random_indices = (
            set(sample(range(len(high)), min(high_random_budget, len(high))))
            if high_random_budget
            else set()
        )
        high_random_part = []
        remaining_high = []
        for i, link in enumerate(high):
            (high_random_part if i in high_random_indices else remaining_high).append(link)

        remaining_high.sort(key=lambda link: link._nlp_score, reverse=True)
        high_top_part = remaining_high[:high_top_budget]
        skip_llm = remaining_high[high_top_budget:]

        sampled = sampled + mid + high_random_part + high_top_part
        return sampled, skip_llm, dropped
