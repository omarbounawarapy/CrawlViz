from utils import apply_selector

class ItemExtractor:
    def __init__(self,extraction_blueprint):
        self.blueprint = extraction_blueprint    

    def extract_items(self, html, node):
            blueprint = self.blueprint
            mode = blueprint.get("mode", "document")

            if mode == "document":
                return DocumentStrategy.run(html, blueprint)

            elif mode == "container":
                return ContainerStrategy.run(html, blueprint)

            else:
                raise ValueError(f"Unsupported extraction mode: {mode}")
        

class DocumentStrategy:

    @staticmethod
    def run( html, blueprint):
        fields = blueprint.get("fields", {})

        item = {}

        for field_name, field_spec in fields.items():
            item[field_name] = FieldExtractor.extract(
                context=html,
                field_spec=field_spec
            )

        return [item]
    
class ContainerStrategy:

    @staticmethod
    def run( html, blueprint):
        container_selector = blueprint.get("container")
        fields = blueprint.get("fields", {})

        if not container_selector:
            raise ValueError("Container mode requires 'container' selector")

        containers = apply_selector(html, container_selector)

        items = []

        for container in containers:
            item = {}

            for field_name, field_spec in fields.items():
                item[field_name] = FieldExtractor.extract(
                    context=container,
                    field_spec=field_spec
                )

            items.append(item)

        return items
    

class FieldExtractor:
    @staticmethod
    def extract(context, field_spec):
        selector = field_spec.get("selector")
        field_type = field_spec.get("type", "list")

        if not selector:
            return None if field_type == "scalar" else []

        raw_values = apply_selector(context, selector)
        raw_values = [FieldExtractor._to_text(v) for v in raw_values]

        return FieldNormalizer.normalize(raw_values, field_type)
    @staticmethod
    def _to_text(value):
        # lxml element
        if hasattr(value, "text_content"):
            return value.text_content()

        # attribute or string
        return str(value)
    

class FieldNormalizer:
    @staticmethod
    def normalize(values, field_type):
        if not values:
            return None if field_type == "scalar" else []

        if field_type == "scalar":
            return values[0]

        if field_type == "list":
            return values

        raise ValueError(f"Unknown field type: {field_type}")
    

    