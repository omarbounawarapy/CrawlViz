"""Unit tests for models/item_extractor.py.

Uses real HTML strings through the real lxml-backed apply_selector, since
that's the actual behavior contract (mocking it would just test the mock).
"""
import pytest

from models.item_extractor import (
    ContainerStrategy,
    DocumentStrategy,
    FieldExtractor,
    FieldNormalizer,
    ItemExtractor,
)

DOCUMENT_HTML = """
<html><body>
    <h1>Page Title</h1>
    <span class="price">$19.99</span>
    <a class="tag" href="#">python</a>
    <a class="tag" href="#">testing</a>
</body></html>
"""

CONTAINER_HTML = """
<html><body>
    <div class="item"><h2>Widget A</h2><span class="price">$5</span></div>
    <div class="item"><h2>Widget B</h2><span class="price">$10</span></div>
    <div class="item"><h2>Widget C</h2><span class="price">$15</span></div>
</body></html>
"""


class TestItemExtractorModeDispatch:
    def test_document_mode_dispatches_to_document_strategy(self):
        blueprint = {"mode": "document", "fields": {"title": {"selector": "//h1/text()", "type": "scalar"}}}
        items = ItemExtractor(blueprint).extract_items(DOCUMENT_HTML, node=None)
        assert len(items) == 1
        assert items[0]["title"] == "Page Title"

    def test_defaults_to_document_mode_when_unspecified(self):
        blueprint = {"fields": {"title": {"selector": "//h1/text()", "type": "scalar"}}}
        items = ItemExtractor(blueprint).extract_items(DOCUMENT_HTML, node=None)
        assert len(items) == 1

    def test_container_mode_dispatches_to_container_strategy(self):
        blueprint = {
            "mode": "container",
            "container": "//div[@class='item']",
            "fields": {"name": {"selector": ".//h2/text()", "type": "scalar"}},
        }
        items = ItemExtractor(blueprint).extract_items(CONTAINER_HTML, node=None)
        assert len(items) == 3

    def test_unknown_mode_raises(self):
        blueprint = {"mode": "not_a_real_mode", "fields": {}}
        with pytest.raises(ValueError, match="Unknown extraction mode"):
            ItemExtractor(blueprint).extract_items(DOCUMENT_HTML, node=None)


class TestDocumentStrategy:
    def test_extracts_scalar_and_list_fields(self):
        blueprint = {
            "fields": {
                "title": {"selector": "//h1/text()", "type": "scalar"},
                "tags": {"selector": "//a[@class='tag']/text()", "type": "list"},
            }
        }
        items = DocumentStrategy.run(DOCUMENT_HTML, blueprint)
        assert items == [{"title": "Page Title", "tags": ["python", "testing"]}]

    def test_always_returns_exactly_one_item(self):
        blueprint = {"fields": {}}
        items = DocumentStrategy.run(DOCUMENT_HTML, blueprint)
        assert len(items) == 1


class TestContainerStrategy:
    def test_extracts_one_item_per_container(self):
        blueprint = {
            "container": "//div[@class='item']",
            "fields": {
                "name": {"selector": ".//h2/text()", "type": "scalar"},
                "price": {"selector": ".//span[@class='price']/text()", "type": "scalar"},
            },
        }
        items = ContainerStrategy.run(CONTAINER_HTML, blueprint)
        assert items == [
            {"name": "Widget A", "price": "$5"},
            {"name": "Widget B", "price": "$10"},
            {"name": "Widget C", "price": "$15"},
        ]

    def test_missing_container_selector_raises(self):
        blueprint = {"fields": {}}
        with pytest.raises(ValueError, match="Container mode requires"):
            ContainerStrategy.run(CONTAINER_HTML, blueprint)

    def test_no_matching_containers_returns_empty_list(self):
        blueprint = {"container": "//div[@class='nonexistent']", "fields": {}}
        assert ContainerStrategy.run(CONTAINER_HTML, blueprint) == []

    def test_field_selector_is_relative_to_each_container(self):
        # Sanity check that fields don't leak across containers -- each
        # container's field selector should only see its own subtree.
        blueprint = {
            "container": "//div[@class='item']",
            "fields": {"name": {"selector": ".//h2/text()", "type": "scalar"}},
        }
        items = ContainerStrategy.run(CONTAINER_HTML, blueprint)
        names = [i["name"] for i in items]
        assert names == ["Widget A", "Widget B", "Widget C"]


class TestFieldExtractor:
    def test_no_selector_returns_none_for_scalar(self):
        assert FieldExtractor.extract(DOCUMENT_HTML, {"type": "scalar"}) is None

    def test_no_selector_returns_empty_list_for_list_type(self):
        assert FieldExtractor.extract(DOCUMENT_HTML, {"type": "list"}) == []

    def test_extracts_scalar(self):
        result = FieldExtractor.extract(DOCUMENT_HTML, {"selector": "//h1/text()", "type": "scalar"})
        assert result == "Page Title"

    def test_extracts_list(self):
        result = FieldExtractor.extract(
            DOCUMENT_HTML, {"selector": "//a[@class='tag']/text()", "type": "list"}
        )
        assert result == ["python", "testing"]

    def test_selector_matching_nothing_returns_none_for_scalar(self):
        result = FieldExtractor.extract(
            DOCUMENT_HTML, {"selector": "//nonexistent/text()", "type": "scalar"}
        )
        assert result is None

    def test_selector_matching_nothing_returns_empty_list(self):
        result = FieldExtractor.extract(
            DOCUMENT_HTML, {"selector": "//nonexistent/text()", "type": "list"}
        )
        assert result == []


class TestFieldNormalizer:
    def test_empty_values_scalar(self):
        assert FieldNormalizer.normalize([], "scalar") is None

    def test_empty_values_list(self):
        assert FieldNormalizer.normalize([], "list") == []

    def test_scalar_takes_first_value(self):
        assert FieldNormalizer.normalize(["a", "b", "c"], "scalar") == "a"

    def test_list_keeps_all_values(self):
        assert FieldNormalizer.normalize(["a", "b", "c"], "list") == ["a", "b", "c"]

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown field type"):
            FieldNormalizer.normalize(["a"], "not_a_real_type")
