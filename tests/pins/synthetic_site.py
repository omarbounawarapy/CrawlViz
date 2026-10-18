"""A seeded 200-page site for the synthetic pin, built in code so it has no data file.

A fifth of the pages are about the topic. Links from topical pages lean towards
topical pages, and anchors to topical pages mostly use topic words, so a
topic-focused crawl has something to find. Every page is reachable from the seed.
"""
import random
from typing import Any

from benchmark.graph import FrozenGraph

SITE_SEED = "pin-site"
PAGE_COUNT = 200
TOPICAL_SHARE = 0.2
TOPICAL_LINK_BIAS = 0.6  # chance a link from a topical page goes to a topical page

# Out-degree range. The cascade buckets by percentile only for a page with at
# least PERCENTILE_MIN_LINKS links, so the range straddles it and the pin
# covers both bucketing modes (test_synthetic_site checks this).
MIN_LINKS_PER_PAGE = 6
MAX_LINKS_PER_PAGE = 16

ANCHOR_WORDS = 2
TEXT_WORDS = 12
TOPICAL_ANCHOR_CHANCE = 0.8  # chance a word of an anchor to a topical page is a topic word
OFF_TOPIC_ANCHOR_CHANCE = 0.1  # the same for an anchor to any other page
TOPICAL_TEXT_CHANCE = 0.7  # chance a word of a topical page's text is a topic word
OFF_TOPIC_TEXT_CHANCE = 0.1  # the same for any other page

TOPIC = "diabetes insulin glucose"
TOPIC_WORDS = [
    "diabetes", "insulin", "glucose", "pancreas", "glycemic",
    "neuropathy", "retinopathy", "metabolic", "hba1c",
]
OTHER_WORDS = [
    "history", "news", "travel", "sports", "music", "weather",
    "politics", "economy", "culture", "education", "software",
]


def _words(rng: random.Random, topical_chance: float, count: int) -> str:
    return " ".join(
        rng.choice(TOPIC_WORDS if rng.random() < topical_chance else OTHER_WORDS)
        for _ in range(count)
    )


def build_site(seed: str = SITE_SEED, page_count: int = PAGE_COUNT) -> FrozenGraph:
    """The site for ``seed``: the same graph on every run and every machine.

    ``random.Random`` seeded with a string hashes it with SHA-512, so the
    result does not depend on ``PYTHONHASHSEED``.
    """
    rng = random.Random(seed)
    names = [f"p{n}" for n in range(page_count)]
    topical = set(rng.sample(names[1:], int(TOPICAL_SHARE * page_count)))
    topical_names = sorted(topical)
    targets: dict[str, list[str]] = {name: [] for name in names}

    for index, name in enumerate(names):
        if index:  # one inbound link from an earlier page keeps every page reachable
            targets[names[rng.randrange(index)]].append(name)
    for name in names:
        quota = rng.randint(MIN_LINKS_PER_PAGE, MAX_LINKS_PER_PAGE)
        while len(targets[name]) < quota:
            leans_topical = name in topical and rng.random() < TOPICAL_LINK_BIAS
            target = rng.choice(topical_names) if leans_topical else rng.choice(names)
            if target != name and target not in targets[name]:
                targets[name].append(target)

    # Any: pages are the JSON a FrozenGraph loads.
    pages: dict[str, dict[str, Any]] = {}
    for name in names:
        is_topical = name in topical
        links = [
            {
                "to": target,
                "anchor": _words(
                    rng,
                    TOPICAL_ANCHOR_CHANCE if target in topical else OFF_TOPIC_ANCHOR_CHANCE,
                    ANCHOR_WORDS,
                ),
            }
            for target in targets[name]
        ]
        text_chance = TOPICAL_TEXT_CHANCE if is_topical else OFF_TOPIC_TEXT_CHANCE
        pages[name] = {
            "label": 1 if is_topical else 0,
            "title": f"Page {name}",
            "text": _words(rng, text_chance, TEXT_WORDS),
            "links": links,
        }
    return FrozenGraph(seed=names[0], pages=pages, topic=TOPIC)
