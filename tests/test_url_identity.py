from models.link import Link
from utils.html_utils import normalize_url


def test_fragment_and_trailing_slash_map_to_one_url():
    assert normalize_url("/wiki/X") == normalize_url("/wiki/X#Y") == normalize_url("/wiki/X/")


def test_percent_encoding_is_canonical():
    assert normalize_url("/wiki/%c3%a9") == normalize_url("/wiki/é") == "/wiki/%C3%A9"
    assert normalize_url("/wiki/%41b") == "/wiki/Ab"


def test_root_and_query_survive():
    assert normalize_url("/") == "/"
    assert normalize_url("https://a.org/p/?q=1#f") == "https://a.org/p?q=1"


def test_link_stores_normalized_url():
    assert Link("/wiki/X#Y", "", "").url == "/wiki/X"


def test_storage_treats_relative_and_absolute_links_as_one_page():
    from models.storage import Storage

    base = "https://fr.wikipedia.org"
    storage = Storage()
    storage.add_links([Link("https://fr.wikipedia.org/wiki/Tunis", "", "")], base)

    assert storage.link_seen("/wiki/Tunis", base)
    assert storage.link_seen("/wiki/Tunis#Histoire", base)
    assert not storage.link_seen("/wiki/Sfax", base)
