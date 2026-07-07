from typing import Any

from utils import apply_selector


class ItemExtractor:
    """Extracts structured items from a page's HTML per its extraction blueprint.

    Args:
        extraction_blueprint: The blueprint's ``extraction`` sub-dict, whose
            ``mode`` ("document" or "container") selects DocumentStrategy
            or ContainerStrategy below.
    """

    def __init__(self, extraction_blueprint: dict):
        self.extraction_blueprint = extraction_blueprint

    def extract_items(self, html: str, node: Any) -> list[dict]:
        extraction_blueprint = self.extraction_blueprint
        mode = extraction_blueprint.get("mode", "document")

        if mode == "document":
            return DocumentStrategy.run(html, extraction_blueprint)

        elif mode == "container":
            return ContainerStrategy.run(html, extraction_blueprint)

        else:
            raise ValueError(f"Unknown extraction mode: {mode!r}")


class DocumentStrategy:
    """Extracts exactly one item from the whole page."""

    @staticmethod
    def run(html: str, extraction_blueprint: dict) -> list[dict]:
        fields = extraction_blueprint.get("fields", {})

        item = {}
        for field_name, field_spec in fields.items():
            item[field_name] = FieldExtractor.extract(
                context=html,
                field_spec=field_spec,
            )

        return [item]


class ContainerStrategy:
    """Extracts one item per repeated container element on the page."""

    @staticmethod
    def run(html: str, extraction_blueprint: dict) -> list[dict]:
        container_selector = extraction_blueprint.get("container")
        fields = extraction_blueprint.get("fields", {})

        if not container_selector:
            raise ValueError("Container mode requires 'container' selector")

        containers = apply_selector(html, container_selector)

        items = []
        for container in containers:
            item = {}
            for field_name, field_spec in fields.items():
                item[field_name] = FieldExtractor.extract(
                    context=container,
                    field_spec=field_spec,
                )
            items.append(item)

        return items


class FieldExtractor:
    """Extracts and normalizes a single field's value from one context node."""

    @staticmethod
    def extract(context: Any, field_spec: dict) -> Any:
        selector = field_spec.get("selector")
        field_type = field_spec.get("type", "list")

        if not selector:
            return None if field_type == "scalar" else []

        raw_values = apply_selector(context, selector)
        raw_values = [FieldExtractor._to_text(v) for v in raw_values]

        return FieldNormalizer.normalize(raw_values, field_type)

    @staticmethod
    def _to_text(value: Any) -> str:
        # lxml element
        if hasattr(value, "text_content"):
            return value.text_content()

        # attribute or string
        return str(value)


class FieldNormalizer:
    """Collapses a field's raw extracted values to its declared type."""

    @staticmethod
    def normalize(values: list[str], field_type: str) -> Any:
        if not values:
            return None if field_type == "scalar" else []

        if field_type == "scalar":
            return values[0]

        if field_type == "list":
            return values

        raise ValueError(f"Unknown field type: {field_type!r}")
