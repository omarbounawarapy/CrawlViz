"""The synthetic site is the same graph every time, and a connected one."""
import json
import subprocess
import sys

from pin_paths import PINS_DIR, REPO_ROOT
from synthetic_site import (
    MAX_LINKS_PER_PAGE,
    MIN_LINKS_PER_PAGE,
    PAGE_COUNT,
    TOPICAL_SHARE,
    build_site,
)

from benchmark.runner import PERCENTILE_MIN_LINKS


def test_the_site_has_the_documented_size_and_shape() -> None:
    site = build_site()

    assert len(site.pages) == PAGE_COUNT
    assert len(site.relevant()) == int(TOPICAL_SHARE * PAGE_COUNT)
    assert site.label(site.seed) == 0
    degrees = [len(page["links"]) for page in site.pages.values()]
    assert min(degrees) >= MIN_LINKS_PER_PAGE
    assert max(degrees) >= MAX_LINKS_PER_PAGE  # the spanning links can add to the quota


def test_pages_fall_on_both_sides_of_the_percentile_bucketing_threshold() -> None:
    degrees = [len(page["links"]) for page in build_site().pages.values()]

    assert min(degrees) < PERCENTILE_MIN_LINKS <= max(degrees)


def test_every_page_is_reachable_from_the_seed() -> None:
    site = build_site()

    assert site.reachable() == set(site.pages)


def test_a_different_seed_gives_a_different_site() -> None:
    assert build_site("other").pages != build_site().pages


def test_the_site_does_not_depend_on_the_hash_seed_of_the_process() -> None:
    code = (
        "import json, sys; sys.path.insert(0, sys.argv[1]);"
        "from synthetic_site import build_site;"
        "print(json.dumps(build_site().pages, sort_keys=True))"
    )

    def pages_under(hash_seed: str) -> str:
        env = {"PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(REPO_ROOT)}
        return subprocess.run(
            [sys.executable, "-c", code, str(PINS_DIR)],
            capture_output=True, text=True, check=True, env=env,
        ).stdout

    assert pages_under("1") == pages_under("2")
    assert json.loads(pages_under("3")) == json.loads(json.dumps(build_site().pages))
