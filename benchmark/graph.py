"""A frozen web graph: pages, links with anchor text, and a relevance label.
A recorded page (benchmark/record.py) also carries ``title`` and ``text``.

JSON format (``FrozenGraph.load`` / ``save``)::

    {"seed": "p0",
     "pages": {"p0": {"relevant": false,   # or "label": 0 | 1 | 2
                      "links": [{"to": "p7", "anchor": "insulin therapy"}]}}}

Page names must be URL path segments. The graph is served as HTML by
``FrozenGraph.fetcher()``, so extraction runs through the real
``LinkExtractor`` and nothing about the runtime changes.
"""
import html
import json
import random
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from utils.html_utils import normalize_url

BASE_URL = "https://frozen.test"

TOPIC_TERMS = (
    "diabetes insulin glucose pancreas glycemic neuropathy retinopathy "
    "metabolic hba1c hyperglycemia"
).split()
GENERIC_TERMS = (
    "history news events travel sports music weather politics economy "
    "culture education software television geography"
).split()


def page_key(name: str) -> str:
    """A page name as the crawler identifies it (utils.html_utils.normalize_url).

    The fetcher is asked for the crawler's canonical URL, so a graph keyed by
    raw non-ASCII names would answer 404 for every one of them."""
    return normalize_url("/" + name)[1:]


@dataclass
class FrozenGraph:
    seed: str
    pages: dict[str, dict] = field(default_factory=dict)
    topic: str = ""  # what "relevant" means, in words; set by the labeler
    terms: list[str] = field(default_factory=list)  # topic words for the lexical baseline

    def __post_init__(self) -> None:
        self._canonicalize()

    def _canonicalize(self) -> None:
        """Re-key pages and link targets with ``page_key``. Names that collapse
        to one key keep the first page and pool their links."""
        pages: dict[str, dict] = {}
        for name, page in self.pages.items():
            key = page_key(name)
            if key in pages:
                known = {link["to"] for link in pages[key]["links"]}
                pages[key]["links"] += [
                    link for link in page["links"] if page_key(link["to"]) not in known
                ]
            else:
                pages[key] = page
        for page in pages.values():
            for link in page["links"]:
                link["to"] = page_key(link["to"])
        self.pages = pages
        self.seed = page_key(self.seed)

    def duplicate_titles(self) -> dict[str, list[str]]:
        """Titles shared by several pages: usually a redirect crawled under two
        names, which splits one page's inbound links and double-counts it."""
        by_title: dict[str, list[str]] = {}
        for name, page in self.pages.items():
            if page.get("title"):
                by_title.setdefault(page["title"], []).append(name)
        return {t: names for t, names in by_title.items() if len(names) > 1}

    def merge(self, keep: str, drop: str) -> None:
        """Fold page ``drop`` into ``keep``: its links are pooled and every
        link that pointed at it now points at ``keep``."""
        keep, drop = page_key(keep), page_key(drop)
        known = {link["to"] for link in self.pages[keep]["links"]}
        for link in self.pages.pop(drop)["links"]:
            if link["to"] not in known and link["to"] not in (keep, drop):
                known.add(link["to"])
                self.pages[keep]["links"].append(link)
        for page in self.pages.values():
            seen, links = set(), []
            for link in page["links"]:
                if link["to"] == drop:
                    link["to"] = keep
                if link["to"] not in seen:
                    seen.add(link["to"])
                    links.append(link)
            page["links"] = links
        if self.seed == drop:
            self.seed = keep

    def label(self, name: str) -> int:
        """Graded relevance: 0 irrelevant, 1 topical neighbourhood, 2 direct
        target. Files written before grading carry only ``relevant``."""
        page = self.pages[name]
        if page.get("label") is not None:
            return int(page["label"])
        return 1 if page.get("relevant") else 0

    def relevant(self) -> set[str]:
        """Pages with label 1 or 2."""
        return {p for p in self.pages if self.label(p) >= 1}

    def reachable(self) -> set[str]:
        seen, stack = {self.seed}, [self.seed]
        while stack:
            for link in self.pages[stack.pop()]["links"]:
                if link["to"] in self.pages and link["to"] not in seen:
                    seen.add(link["to"])
                    stack.append(link["to"])
        return seen

    def save(self, path: Path) -> None:
        data = {"seed": self.seed, "pages": self.pages}
        if self.topic:
            data["topic"] = self.topic
        if self.terms:
            data["terms"] = self.terms
        Path(path).write_text(json.dumps(data, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> "FrozenGraph":
        data = json.loads(Path(path).read_text())
        graph = cls(
            seed=data["seed"],
            pages=data["pages"],
            topic=data.get("topic", ""),
            terms=data.get("terms", []),
        )
        duplicates = graph.duplicate_titles()
        if duplicates:
            warnings.warn(
                f"{len(duplicates)} title(s) shared by several pages, e.g. "
                f"{next(iter(duplicates.values()))}; merge them with FrozenGraph.merge",
                stacklevel=2,
            )
        return graph

    def fetcher(self) -> "GraphFetcher":
        return GraphFetcher(self)


class GraphFetcher:
    """Satisfies the ``Fetcher`` protocol from a frozen graph."""

    def __init__(self, graph: FrozenGraph):
        self.graph = graph
        self.fetched: list[str] = []

    async def emit_request(self, params: dict) -> str:
        name = params["url"].rsplit("/", 1)[1]
        page = self.graph.pages.get(name)
        if page is None:
            raise RuntimeError("404 Not Found")
        self.fetched.append(name)
        items = "".join(
            f'<li><a href="/{link["to"]}">{html.escape(link["anchor"])}</a></li>' for link in page["links"]
        )
        if "text" not in page:  # synthetic page: anchors only
            return f"<html><body><h1>{name}</h1><ul>{items}</ul></body></html>"
        # A recorded page: the markup the extraction blueprints expect.
        title, text = html.escape(page["title"]), html.escape(page["text"])
        return (
            f'<html><body><h1 id="firstHeading">{title}</h1>'
            f'<div class="mw-parser-output"><p>{text}</p><ul>{items}</ul></div></body></html>'
        )

    async def close(self) -> None:
        pass


def synthetic_graph(
    n_pages: int = 600,
    out_degree: int = 8,
    relevant_fraction: float = 0.15,
    homophily: float = 0.5,
    anchor_signal: float = 0.7,
    seed: int = 0,
) -> FrozenGraph:
    """Random graph with a planted relevant cluster.

    homophily: chance that a link from a relevant page goes to a relevant page
    (other links, and all links from irrelevant pages, go to a uniformly
    random page).
    anchor_signal: chance that an anchor to a relevant page uses topic words
    (anchors to irrelevant pages use topic words with chance 1 - anchor_signal
    squared, a small false-positive rate).
    """
    rng = random.Random(f"graph:{seed}")
    names = [f"p{i}" for i in range(n_pages)]
    relevant = set(rng.sample(names[1:], int(relevant_fraction * n_pages)))
    rel_list = sorted(relevant)
    false_pos = (1 - anchor_signal) ** 2

    def anchor(target: str) -> str:
        topical = rng.random() < (anchor_signal if target in relevant else false_pos)
        pool = TOPIC_TERMS if topical else GENERIC_TERMS
        return " ".join(rng.sample(pool, 2))

    pages = {}
    for name in names:
        links = []
        for target in rng.sample(names, out_degree):
            if name in relevant and rng.random() < homophily:
                target = rng.choice(rel_list)
            if target != name:
                links.append({"to": target, "anchor": anchor(target)})
        pages[name] = {"relevant": name in relevant, "links": links}
    return FrozenGraph(seed=names[0], pages=pages)
