from pathlib import Path

import pytest

from utils import load_json, save_json


def test_saved_json_loads_back_with_non_ascii_text(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "data.json"
    save_json(path, {"title": "Institut supérieur"})
    assert load_json(path) == {"title": "Institut supérieur"}


def test_save_json_honours_indent_and_key_order(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    save_json(path, {"b": 1, "a": 2}, indent=None, sort_keys=True)
    assert path.read_text(encoding="utf-8") == '{"a": 2, "b": 1}'


def test_save_json_converts_unserialisable_values_with_default(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    save_json(path, {"value": {1, 2}}, default=sorted)
    assert load_json(path) == {"value": [1, 2]}


def test_failed_save_keeps_the_previous_file(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    save_json(path, {"keep": True})
    with pytest.raises(TypeError):
        save_json(path, {"bad": object()})
    assert load_json(path) == {"keep": True}
    assert not list(tmp_path.glob("*.tmp"))
