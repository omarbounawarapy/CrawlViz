from urllib.parse import urljoin


class Domain:
    def __init__(
        self,
        name: str,
        base_url: str,
        link_selector: str,
    ):
        self.name = name
        self.base_url = base_url

        # crawler
        self._link_selector = link_selector

    # -------------------------
    # BASIC ACCESSORS
    # -------------------------
    def get_name(self):
        return self.name

    def get_base_url(self):
        return self.base_url

    def get_link_selector(self):
        return self._link_selector


    # -------------------------
    # URL NORMALIZATION
    # -------------------------
    def normalize_url(self, url: str):
        return urljoin(self.base_url, url)

    # -------------------------
    # DEBUG / INSPECTION
    # -------------------------
    def __repr__(self):
        return f"<Domain {self.name} base_url={self.base_url}>"