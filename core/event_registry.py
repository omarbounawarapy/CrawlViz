from collections import defaultdict
from typing import Any, Callable, Dict, List, Type


class EventRegistry:
    """Maps event types to the pipelines subscribed to them.

    Used internally by EventBroker; pipelines register interest via
    EventBroker.subscribe() rather than touching this directly.
    """

    def __init__(self):
        self.registry: Dict[Type[Any], List[Callable]] = defaultdict(list)

    def subscribe(self, pipeline, event_types: List[Type[Any]]) -> None:
        for event_type in event_types:
            self.registry[event_type].append(pipeline)

    def event_consumers(self, event: Any) -> List[Callable]:
        return self.registry[type(event)]
