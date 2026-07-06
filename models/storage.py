from typing import Any

from .domain import Domain
from .node import Node


class Storage:
    """In-memory store for one crawl's graph: nodes, domains, and the
    hashes/links already seen.

    Node IDs are assigned sequentially by `next_id()` and double as the
    node's index in `nodes`, so callers must always store a freshly
    allocated node before requesting the next one.
    """

    def __init__(self):
        self.nodes: list[Node] = []
        self.current_id = 0
        self.link_to_id: dict[str, int] = {}
        self.found_links: set[str] = set()
        self.domains: dict[str, Domain] = {}
        self.items: dict[str, Any] = {}

    def get_node(self, node_id: int) -> Node:
        return self.nodes[node_id]

    def add_domain(self, domain: Domain) -> None:
        base_url = domain.get_base_url()
        self.domains[base_url] = domain

    def get_domain(self, base_url: str) -> Domain:
        return self.domains[base_url]

    def add_node(self, node: Node) -> None:
        self.nodes.append(node)
        self.found_links.add(node.get_link())
        self.link_to_id[node.get_link()] = node.get_id()

    def add_item(self, item: Any, item_hash: str, parent: Node) -> None:
        self.items[item_hash] = parent
        self.nodes[parent.get_id()].add_item(item, item_hash)

    def node_id_from_link(self, link: str) -> int:
        return self.link_to_id[link]

    def add_links(self, links: list[Any]) -> None:
        for link in links:
            self.found_links.add(link.url)

    def next_id(self) -> int:
        self.current_id += 1
        return self.current_id - 1

    def link_seen(self, link: str) -> bool:
        return link in self.found_links

    def item_seen(self, item_hash: str) -> bool:
        return item_hash in self.items
