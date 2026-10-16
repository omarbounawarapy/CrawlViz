"""Content rules for user-facing settings, checked on the served schema.

Every visible (non-advanced) field needs a plain effect line, every number
needs a unit key (``""`` when it is a count or multiplier), every section in
the guide needs at least one visible field, and the glossary is emitted.
"""


from config.runtime_config import SECTION_GUIDE, RuntimeConfig

SECTIONS = [name for name, _ in SECTION_GUIDE]


def _fields():
    """(model, key, raw, section) for every leaf setting in the schema."""
    schema = RuntimeConfig.model_json_schema()
    defs = schema["$defs"]
    root = schema["properties"]
    out = []
    for top, ref in root.items():
        model = defs[ref["$ref"].split("/")[-1]] if "$ref" in ref else ref
        for key, raw in model.get("properties", {}).items():
            section_ref = raw.get("$ref")
            node = defs[section_ref.split("/")[-1]] if section_ref else raw
            if node.get("type") == "object" and "properties" in node and "ui_widget" not in raw:
                for sub_key, sub in node["properties"].items():
                    out.append((f"{top}.{key}.{sub_key}", sub))
            else:
                out.append((f"{top}.{key}", raw))
    return [(path, raw, raw.get("ui_section")) for path, raw in out]


def _visible():
    return [(path, raw, sec) for path, raw, sec in _fields()
            if not raw.get("ui_advanced") and sec is not None]


def test_every_visible_field_has_an_effect_line():
    missing = [path for path, raw, _ in _visible() if not raw.get("ui_effect")]
    assert not missing, f"fields without ui_effect: {missing}"


def _is_numeric(raw):
    types = [raw.get("type")] + [alt.get("type") for alt in raw.get("anyOf", [])]
    return any(t in ("integer", "number") for t in types)


def test_numeric_fields_declare_a_unit_or_none():
    numeric = [(p, r) for p, r, _ in _visible() if _is_numeric(r)]
    assert numeric, "no numeric fields found"
    missing = [p for p, r in numeric if "ui_unit" not in r]
    assert not missing, f"numeric fields without ui_unit (use \"\" for unitless): {missing}"


def test_every_section_has_a_field():
    # A section whose fields are all advanced (URLs) stays in the guide but has
    # no visible row; the settings nav hides it until Advanced is on.
    present = {sec for _, _, sec in _fields() if sec is not None}
    empty = [s for s in SECTIONS if s not in present]
    assert not empty, f"sections with no fields: {empty}"


def test_glossary_is_emitted_with_plain_definitions():
    glossary = RuntimeConfig.model_json_schema()["ui_glossary"]
    for term in ("percentile", "cascade", "backoff", "jitter", "embedding", "cosine",
                 "top-k", "queue", "flush", "backpressure", "temperature", "demotion",
                 "novelty injection", "coverage gap", "semantic delta", "random fraction",
                 "best-ranked", "key cooldown", "backoff decay"):
        assert glossary.get(term), f"glossary lacks {term!r}"
        assert len(glossary[term]) < 200, f"glossary entry for {term!r} is too long"


def test_every_visible_field_has_a_description():
    missing = [p for p, r, _ in _visible() if not r.get("description")]
    assert not missing, f"fields without a description: {missing}"


def test_glossary_defines_the_terms_the_page_uses():
    from config.runtime_config import GLOSSARY

    for term in ("percentile bucketing", "bucket", "middle band", "high-confidence bucket", "nlp bias",
                 "llm bias", "priority points", "in flight", "politeness", "token", "tokens", "template",
                 "blueprint", "debug trace", "queue bound", "requeue"):
        assert GLOSSARY.get(term), term


def test_default_priority_strategy_is_chosen_on_the_priority_page():
    from config.runtime_config import ScoringCascadeConfig

    field = ScoringCascadeConfig.model_fields["default_priority_strategy"]
    assert field.json_schema_extra["ui_section"] == "Priority"
