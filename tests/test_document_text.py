import services.nlp_service as nlp_service
from utils.html_utils import document_text

PAGE = (
    "<html><head><style>p{}</style><script>var x=1;</script></head><body>"
    "<nav>Menu</nav><p>First  paragraph.</p><div><p>Second <b>one</b>.</p></div>"
    "</body></html>"
)


def test_keeps_paragraph_text_only():
    assert document_text(PAGE) == "First paragraph. Second one ."


def test_falls_back_to_visible_text_without_paragraphs():
    page = "<html><body><script>x</script><div>Hello world</div></body></html>"
    assert document_text(page) == "Hello world"


def test_empty_input():
    assert document_text("") == ""
    assert document_text("   ") == ""


def test_scoring_uses_this_function():
    # score_links (used by the crawl and by tools/nlp_eval.py) reduces
    # parent.content, which is raw HTML, with this exact function.
    assert nlp_service.document_text is document_text
