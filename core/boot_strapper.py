"""Turns a blueprint JSON file into the runtime objects a crawl needs.

See routes/blueprint_translator.py for how a blueprint gets authored,
and templates/*.json for examples. BootStrapper only *consumes* an
already-assembled blueprint: it registers each domain, creates a
Node per seed URL, and emits the NodeAddedEvent that starts the crawl.
"""

import json
import logging

from config import TEMPLATES_DIR
from events import NodeAddedEvent
from models import Domain, Node

logger = logging.getLogger(__name__)


class BootStrapper:
    def __init__(self, event_broker, storage, template_file: str):
        self.event_broker = event_broker
        self.storage = storage
        self.template_file = TEMPLATES_DIR / template_file
        self.template = None

    async def bootstrap(self) -> dict:
        template = self.load_template()

        self.inject_domains(template.get("domains", {}))
        await self.inject_seeds(template.get("seeds", []))

        logger.info("Bootstrapped crawl from %s", self.template_file.name)
        return template

    def load_template(self) -> dict:
        if not self.template_file.exists():
            raise FileNotFoundError(
                f"Blueprint template not found: {self.template_file}"
            )

        with open(self.template_file, "r", encoding="utf-8") as file:
            self.template = json.load(file)

        return self.template

    def inject_domains(self, domains: dict) -> None:
        for name, params in domains.items():
            domain = Domain(
                name=name,
                # The domain's dict key doubles as its base URL.
                base_url=params.get("base_url"),
                link_selector=params.get("link_selector"),
            )
            self.storage.add_domain(domain)

    async def inject_seeds(self, seeds: list) -> None:
        for seed in seeds:
            node_id = self.storage.next_id()
            domain = self.storage.get_domain(seed["domain"])

            node = Node(node_id, url=seed["url"], domain=domain)
            self.storage.add_node(node)

            await self.event_broker.emit(
                NodeAddedEvent(correlation_id=str(node_id), node=node)
            )
