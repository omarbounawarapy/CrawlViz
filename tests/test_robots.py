import asyncio

from pipelines.robots import RobotsPolicy


class Site:
    def __init__(self, robots):
        self.robots = robots
        self.calls = []

    async def emit_request(self, params):
        self.calls.append(params["url"])
        if isinstance(self.robots, Exception):
            raise self.robots
        return self.robots


def allowed(site, url):
    return asyncio.run(RobotsPolicy(site, "CrawlViz/1.0").allowed(url))


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


def test_unreachable_robots_allows_all():
    assert allowed(Site(OSError("down")), "http://x.test/private")
