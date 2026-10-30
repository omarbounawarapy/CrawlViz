import asyncio

import aiohttp
import pytest
from yarl import URL

from pipelines.robots import MAX_CRAWL_DELAY_SECONDS, RobotsPolicy, product_token


class Site:
    def __init__(self, robots):
        self.robots = robots
        self.calls = []

    async def emit_request(self, params):
        self.calls.append(params["url"])
        await asyncio.sleep(0)
        if isinstance(self.robots, Exception):
            raise self.robots
        return self.robots


def status_error(status):
    info = aiohttp.RequestInfo(URL("http://x.test/robots.txt"), "GET", {}, URL("http://x.test"))
    return aiohttp.ClientResponseError(info, (), status=status)


def allowed(site, url, user_agent="CrawlViz/1.0"):
    return asyncio.run(RobotsPolicy(site, user_agent).allowed(url))


def test_disallowed_path_is_blocked():
    site = Site("User-agent: *\nDisallow: /private\n")
    assert not allowed(site, "http://x.test/private/a")
    assert allowed(site, "http://x.test/wiki/A")


def test_robots_fetched_once_per_origin():
    site = Site("User-agent: *\nDisallow: /p\n")
    policy = RobotsPolicy(site, "CrawlViz/1.0")

    async def run():
        await policy.allowed("http://x.test/a")
        await policy.allowed("http://x.test/b")

    asyncio.run(run())
    assert site.calls == ["http://x.test/robots.txt"]


def test_concurrent_workers_share_one_robots_fetch():
    site = Site("User-agent: *\nDisallow: /p\n")
    policy = RobotsPolicy(site, "CrawlViz/1.0")

    async def run():
        await asyncio.gather(*(policy.allowed(f"http://x.test/{i}") for i in range(8)))

    asyncio.run(run())
    assert site.calls == ["http://x.test/robots.txt"]


@pytest.mark.parametrize("status", [500, 502, 503])
def test_server_error_on_robots_disallows_everything(status):
    assert not allowed(Site(status_error(status)), "http://x.test/anything")


def test_unreachable_robots_disallows_everything():
    assert not allowed(Site(OSError("down")), "http://x.test/anything")


def test_timeout_on_robots_disallows_everything():
    assert not allowed(Site(TimeoutError()), "http://x.test/anything")


@pytest.mark.parametrize("status", [401, 403, 404, 410])
def test_missing_robots_allows_everything(status):
    assert allowed(Site(status_error(status)), "http://x.test/anything")


def test_failed_read_is_retried_later():
    policy = RobotsPolicy(Site(OSError("down")), "CrawlViz/1.0")

    async def run():
        first = await policy.allowed("http://x.test/a")
        policy._expires_at["http://x.test"] = 0.0  # the retry delay has passed
        policy.fetcher = Site("User-agent: *\nDisallow:\n")
        return first, await policy.allowed("http://x.test/a")

    assert asyncio.run(run()) == (False, True)


def test_crawl_delay_is_read_for_our_product_token():
    site = Site("User-agent: crawlviz\nCrawl-delay: 7\n\nUser-agent: *\nCrawl-delay: 1\n")
    policy = RobotsPolicy(site, "CrawlViz/1.0 (+https://example.org; ops@example.org)")
    assert asyncio.run(policy.crawl_delay("http://x.test/a")) == 7


def test_no_crawl_delay_gives_none():
    policy = RobotsPolicy(Site("User-agent: *\nDisallow: /p\n"), "CrawlViz/1.0")
    assert asyncio.run(policy.crawl_delay("http://x.test/a")) is None


def test_crawl_delay_is_capped():
    policy = RobotsPolicy(Site("User-agent: *\nCrawl-delay: 100000\n"), "CrawlViz/1.0")
    assert asyncio.run(policy.crawl_delay("http://x.test/a")) == MAX_CRAWL_DELAY_SECONDS


def test_rules_match_the_product_token_not_the_whole_user_agent():
    site = Site("User-agent: crawlviz\nDisallow: /secret\n")
    agent = "CrawlViz/2.0 (+https://example.org; ops@example.org)"
    assert not allowed(site, "http://x.test/secret", agent)


@pytest.mark.parametrize(
    ("user_agent", "token"),
    [
        ("CrawlViz/1.0 (+https://example.org)", "CrawlViz"),
        ("my-bot", "my-bot"),
        ("(weird)", "CrawlViz"),
    ],
)
def test_product_token(user_agent, token):
    assert product_token(user_agent) == token
