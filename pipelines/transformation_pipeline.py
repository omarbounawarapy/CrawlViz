import asyncio
import re

from events import (
    TransformationStartedEvent,
    TransformationCompletedEvent,
    TransformationFailedEvent,
)


class TransformationPipeline:

    def __init__(self, event_broker,blueprint, max_queue_size=0, max_concurrency=3):
        self.event_broker = event_broker
        self.blueprint = blueprint
        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.max_concurrency = max_concurrency
        self.workers = []

        # -----------------------------
        # TRANSFORM REGISTRY
        # -----------------------------
        self.transforms = {
        "regex": self._regex,
        "regex_extract": self._regex_extract,
        "lowercase": self._lowercase,
        "strip": self._strip,
        "join": self._join,
        "truncate": self._truncate,
        "deduplicate": self._deduplicate,   
        }

    # =====================================================
    # ENTRY (BROKER COMPATIBLE)
    # =====================================================
    async def put(self, event):
        await self.queue.put(event)

    # =====================================================
    # START
    # =====================================================
    async def start(self):
        self.workers = [
            asyncio.create_task(self.worker(i))
            for i in range(self.max_concurrency)
        ]

        await asyncio.gather(*self.workers)

    # =====================================================
    # WORKER
    # =====================================================
    async def worker(self, worker_id):
        while self.queue and self.event_broker.running:
            event = await self.queue.get()

            node = event.node

            try:

                # -------------------------
                # START EVENT
                # -------------------------
                await self.event_broker.emit(
                    TransformationStartedEvent(
                        worker_id=worker_id,
                        correlation_id=node.get_id(),
                        node_id=node.get_id(),
                        items_count=len(event.items),
                    )
                )

                # -------------------------
                # TRANSFORM
                # -------------------------
                transformed_items = self._transform_items(event.items, node)

                # -------------------------
                # COMPLETED EVENT
                # -------------------------
                await self.event_broker.emit(
                    TransformationCompletedEvent(
                        correlation_id=node.get_id(),
                        node=node,
                        links=event.links,
                        transformed_items=transformed_items,

                        output_count= len(transformed_items)

                    )
                )

            except Exception as e:
                # -------------------------
                # FAILED EVENT
                # -------------------------
                await self.event_broker.emit(
                    TransformationFailedEvent(
                        correlation_id=node.get_id(),
                        node=node,
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
                )

            finally:
                self.queue.task_done()

    # =====================================================
    # CORE TRANSFORM ENGINE
    # =====================================================
    def _transform_items(self, items, node):
        blueprint = self.blueprint

        transformed = []

        for item, item_hash in items:
            new_item = {}

            for field, value in item.items():
                spec = blueprint.get(field, {})
                transforms = spec.get("transform", [])

                new_value = value

                for t in transforms:
                    t_type = t.get("type")
                    handler = self.transforms.get(t_type)

                    if handler:
                        new_value = handler(new_value, t)

                new_item[field] = new_value

            transformed.append((new_item, item_hash))

        return transformed

    # =====================================================
    # TRANSFORM OPERATIONS
    # =====================================================

    def _regex(self, value, config):
        if value is None:
            return None

        pattern = config.get("pattern")
        if not pattern:
            return value

        match = re.search(pattern, str(value))

        if not match:
            return None

        return match.group(1) if match.groups() else match.group(0)

    def _lowercase(self, value, config):
        if isinstance(value, str):
            return value.lower()
        return value

    def _strip(self, value, config):
        if isinstance(value, str):
            return value.strip()
        return value

    def _regex_extract(self, value, config):
        pattern = config.get("pattern")

        if not pattern:
            return value

        text = value if isinstance(value, str) else " ".join(map(str, value))

        return re.findall(pattern, text)
    
    def _deduplicate(self, value, config):
        if not isinstance(value, list):
            return value

        seen = set()
        result = []

        for v in value:
            v_str = str(v).strip().lower()
            if v_str not in seen:
                seen.add(v_str)
                result.append(v)

        return result
    
    def _truncate(self, value, config):
        max_len = config.get("max_len", 300)
    
        if isinstance(value, list):
            value = " ".join([str(v) for v in value])
    
        return str(value)[:max_len]
    
    def _join(self, value, config):
        if isinstance(value, list):
            sep = config.get("sep", " ")
            return sep.join([str(v) for v in value])
        return str(value)