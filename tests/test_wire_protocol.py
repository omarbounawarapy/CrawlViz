"""Every message type the backend emits is documented in docs/crawl_messages.ts, and the
declarations that have a pydantic model agree with it field for field."""

import re
import types
from pathlib import Path
from typing import Literal, Union, get_args, get_origin

import pytest
from pydantic import BaseModel

from crawlviz import contracts

ROOT = Path(__file__).resolve().parent.parent
EMITTERS = ["ui_bridge/telemetry_bridge.py", "ui_bridge/crawl_state_snapshot.py"]
CONTRACT = ROOT / "docs/crawl_messages.ts"

_EMITTED = re.compile(r'"type":\s*"([A-Z_]+)"')
_DOCUMENTED = re.compile(r'^\s*type:\s*"([A-Z_]+)";', re.MULTILINE)
_INTERFACE = re.compile(
    r"^export interface (\w+)(?: extends (\w+))? \{\n(.*?)^\}", re.MULTILINE | re.DOTALL
)
_TYPE_ALIAS = re.compile(r"^export type (\w+) =(.*?);", re.MULTILINE | re.DOTALL)
_FIELD = re.compile(r"^\s*(\w+)\??:\s*([^;]+);", re.MULTILINE)
_STRING_LITERAL = re.compile(r'"([^"]+)"')

# Declared with their pydantic model before the bridge sends them (ADR 8). An entry is
# removed in the commit that makes the bridge emit the type; the test below fails until then.
DECLARED_AHEAD_OF_EMITTER: set[str] = set()

# TypeScript declarations whose pydantic model lives in crawlviz.contracts, by TS name.
MODELLED_INTERFACES: dict[str, type[BaseModel]] = {
    "EmbedderFacts": contracts.EmbedderFacts,
    "SpaceFacts": contracts.SpaceFacts,
    "LlmFacts": contracts.LlmFacts,
    "FetchFacts": contracts.FetchFacts,
    "RobotsFacts": contracts.RobotsFacts,
    "ExportFacts": contracts.ExportFacts,
    "EmbedderStatus": contracts.EmbedderStatus,
    "SpaceStatus": contracts.SpaceStatus,
    "LlmStatus": contracts.LlmStatus,
    "FetchStatus": contracts.FetchStatus,
    "RobotsStatus": contracts.RobotsStatus,
    "ExportStatus": contracts.ExportStatus,
    "StatusBoardSnapshot": contracts.StatusBoardSnapshot,
    "SubsystemStatusMsg": contracts.SubsystemStatusMessage,
}
MODELLED_UNIONS: dict[str, object] = {
    "SubsystemName": contracts.SubsystemName,
    "SubsystemState": contracts.SubsystemState,
    "CrawlState": contracts.CrawlState,
}


def _emitted():
    return {t for f in EMITTERS for t in _EMITTED.findall((ROOT / f).read_text())}


def _documented():
    return set(_DOCUMENTED.findall(CONTRACT.read_text()))


def _interfaces() -> dict[str, dict[str, str]]:
    """Each interface's fields and their TypeScript types, base fields included."""
    found = {
        name: (base, dict(_FIELD.findall(body)))
        for name, base, body in _INTERFACE.findall(CONTRACT.read_text())
    }

    def fields(name: str) -> dict[str, str]:
        base, own = found[name]
        return {**(fields(base) if base else {}), **own}

    return {name: fields(name) for name in found}


def _type_aliases() -> dict[str, str]:
    """Each `export type X = ...;` declaration's right-hand side, by name."""
    return dict(_TYPE_ALIAS.findall(CONTRACT.read_text()))


def _literal_values(annotation: object) -> set[str]:
    """Every string a Literal inside `annotation` allows (through unions and Optional)."""
    if get_origin(annotation) is Literal:
        return {str(value) for value in get_args(annotation)}
    if get_origin(annotation) in (Union, types.UnionType):
        return set().union(*(_literal_values(arg) for arg in get_args(annotation)))
    return set()


def test_every_emitted_message_type_is_documented():
    missing = _emitted() - _documented()
    assert not missing, f"emitted but missing from docs/crawl_messages.ts: {sorted(missing)}"


def test_documented_types_are_all_emitted():
    stale = _documented() - _emitted() - DECLARED_AHEAD_OF_EMITTER
    assert not stale, f"documented but never emitted: {sorted(stale)}"


def test_types_declared_ahead_are_documented_and_not_yet_emitted():
    assert _documented() >= DECLARED_AHEAD_OF_EMITTER
    now_emitted = DECLARED_AHEAD_OF_EMITTER & _emitted()
    assert not now_emitted, (
        f"the bridge emits {sorted(now_emitted)} now: remove them from DECLARED_AHEAD_OF_EMITTER"
    )


@pytest.mark.parametrize("ts_name", sorted(MODELLED_INTERFACES))
def test_interface_fields_match_the_pydantic_model(ts_name):
    model = MODELLED_INTERFACES[ts_name]

    assert set(_interfaces()[ts_name]) == set(model.model_fields)


@pytest.mark.parametrize("ts_name", sorted(MODELLED_INTERFACES))
def test_interface_literals_match_the_pydantic_model(ts_name):
    ts_fields = _interfaces()[ts_name]
    aliases = _type_aliases()
    for field_name, info in MODELLED_INTERFACES[ts_name].model_fields.items():
        allowed = _literal_values(info.annotation)
        if allowed:
            ts_type = ts_fields[field_name].strip()
            ts_type = aliases.get(ts_type, ts_type)
            assert set(_STRING_LITERAL.findall(ts_type)) == allowed, field_name


@pytest.mark.parametrize("ts_name", sorted(MODELLED_UNIONS))
def test_string_unions_match_the_pydantic_literals(ts_name):
    aliases = _type_aliases()

    assert set(_STRING_LITERAL.findall(aliases[ts_name])) == _literal_values(
        MODELLED_UNIONS[ts_name]
    )


def test_the_subsystem_status_union_lists_every_entry_model():
    aliases = _type_aliases()
    members = set(re.findall(r"\|\s*(\w+)", aliases["SubsystemStatus"]))
    entry_models = get_args(get_args(contracts.SubsystemStatus)[0])

    assert members == {model.__name__ for model in entry_models}
