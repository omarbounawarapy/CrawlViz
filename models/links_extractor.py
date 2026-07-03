import logging

from lxml import html as lxml_html

from utils import build_url, is_relative_url
from .link import Link

logger = logging.getLogger(__name__)

MAX_CONTEXT_LEN = 300


class LinkExtractor:
    """Extracts candidate links plus their anchor text and surrounding
    context (report section 0.3.3's "signal d'ancrage textuel") from a
    page's HTML, using the domain's configured link_selector.
    """

    @staticmethod
    def extract_links(html_content, node):
        link_selector = node.get_link_selector()
        if isinstance(html_content, str):
            tree = lxml_html.fromstring(html_content)
        else:
            tree = html_content
        link_nodes = tree.xpath(link_selector)
        base_url = node.get_domain_base_url()
        results = []
        for link_node in link_nodes:
            try:
                href = link_node.get("href", "").strip()
                if not href:
                    continue
                if is_relative_url(href):
                    href = build_url(base_url, href)
                anchor = "".join(link_node.itertext()).strip()
                if not anchor:
                    anchor = href.split("/")[-1].replace("-", " ")

                context_node = (
                    link_node.xpath("ancestor::li[1]") or
                    link_node.xpath("ancestor::p[1]") or
                    link_node.xpath("ancestor::td[1]") or
                    link_node.xpath("ancestor::div[1]")
                )
                if context_node:
                    context_text = " ".join(context_node[0].itertext()).strip()
                else:
                    context_text = ""

                context_text = context_text[:min(len(context_text), MAX_CONTEXT_LEN)]
                context_text = LinkExtractor._extract_sentence(context_text, anchor)
                link = Link(
                    href,
                    anchor,
                    context_text
                )
                results.append(link)

            except Exception:
                logger.debug("Failed to extract one link from %s", node.get_url(), exc_info=True)
                continue

        logger.debug("Extracted %d links from %s", len(results), node.get_url())
        return results
    
    @staticmethod
    def _extract_sentence(context_text, anchor):
        if not context_text or not anchor:
            return context_text

        sentences = context_text.split(".")

        for s in sentences:
            if anchor.lower() in s.lower():
                return s.strip()

        return context_text
