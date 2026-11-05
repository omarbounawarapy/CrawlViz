from urllib.parse import urljoin


class Domain:
    """A crawlable site: its base URL, link selector, and display name.

    One Domain is created per key in a blueprint's ``domains`` object and
    shared by every Node that belongs to it.

    Args:
        name: The domain's key in the blueprint, also used for display.
        base_url: Root URL that relative links are resolved against.
        link_selector: CSS/XPath selector LinkExtractor uses to find
            outgoing links on pages belonging to this domain.
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        link_selector: str,
    ):
        self.name = name
        self.base_url = base_url
        self._link_selector = link_selector

    # =========================================================
    # BASIC ACCESSORS
    # =========================================================
    def get_name(self) -> str:
        return self.name

    def get_base_url(self) -> str:
        return self.base_url

    def get_link_selector(self) -> str:
        return self._link_selector

    # =========================================================
    # URL NORMALIZATION
    # =========================================================
    def normalize_url(self, url: str) -> str:
        """Resolve `url` (absolute or relative) against this domain's base URL."""
        return urljoin(self.base_url, url)

    # =========================================================
    # DEBUG / INSPECTION
    # =========================================================
    def __repr__(self) -> str:
        return f"<Domain {self.name} base_url={self.base_url}>"
